"""Scriber — projetos de escrita em disco. Cada projeto é uma pasta comum em `~/.asta/scriber/<id>/`:

    project.json     nome, tipo de escrita, idioma, conteúdo (livre/SFW), formatação, dados da última geração
    document.json    o documento: blocos (ver docmodel.py) — formato aberto, legível, sem banco de dados
    lorebooks.json   os lorebooks (livros de contexto, estilo system prompt)
    sources.json     fontes da web guardadas pela pessoa para citar
    history/         instantâneos do documento antes de cada mudança grande (geração, importação, restauração)
    exports/         .docx, .md, .txt e .html gerados

Tudo é arquivo normal que a pessoa pode abrir, copiar e levar embora. Texto vindo da tela, da IA ou de arquivos importados é entrada não confiável (docmodel/docx validam)."""
from __future__ import annotations

import html
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..util import new_id, now_iso, read_json, safe_filename, slugify, text, write_json
from . import docmodel as D, docx as X, lore as L, schema as S

MAX_PROJECTS = 300
MAX_IMPORT = 48 * 1024 * 1024
MAX_EXPORTS = 60
HISTORY_KEEP = 40
EXPORT_FORMATS = ("docx", "md", "txt", "html")


class ScriberError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def valid_id(pid: Any) -> bool:
    return isinstance(pid, str) and re.match(r"^[a-z0-9_-]{3,40}$", pid) is not None


class ScriberManager:
    def __init__(self, store: Any):
        self.store = store
        self.root = Path(store.home) / "scriber"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    # ------------------------------------------------------------------ projetos
    def dir(self, pid: str) -> Path:
        if not valid_id(pid):
            raise ScriberError(404, "Projeto não encontrado.")
        d = self.root / pid
        if not (d / "project.json").is_file():
            raise ScriberError(404, "Projeto não encontrado.")
        return d

    def meta(self, pid: str) -> Dict[str, Any]:
        m = read_json(self.dir(pid) / "project.json")
        if not isinstance(m, dict):
            raise ScriberError(500, "project.json ilegível.")
        return self._norm_meta(m)

    def _norm_meta(self, m: Dict[str, Any]) -> Dict[str, Any]:
        t = m.get("type") if isinstance(m.get("type"), str) and m.get("type") in S.WRITING_TYPES else S.DEFAULT_TYPE
        g = m.get("gen") if isinstance(m.get("gen"), dict) else {}
        size = S.norm_size(g.get("pages"), g.get("words_per_page"), t)
        return {"id": m.get("id", ""), "name": text(m.get("name"), "Sem título", 100), "type": t, "language": S.norm_lang(m.get("language")),
                "content": m.get("content") if m.get("content") in ("sfw", "free") else "", "format": S.norm_format(m.get("format"), S.WRITING_TYPES[t]["preset"]),
                "gen": {"prompt": text(g.get("prompt"), "", 20000), "pages": size["pages"], "words_per_page": size["words_per_page"], "style": text(g.get("style"), "", 600), "chapters": int(max(0, min(60, g.get("chapters") or 0))) if isinstance(g.get("chapters"), (int, float)) else 0},
                "ignore": [text(w, "", 60) for w in (m.get("ignore") if isinstance(m.get("ignore"), list) else [])][:500], "author": text(m.get("author"), "", 80),
                "description": text(m.get("description"), "", 400), "created": m.get("created", ""), "updated": m.get("updated", ""), "words": int(m.get("words") or 0), "connections": m.get("connections") if isinstance(m.get("connections"), dict) else {}}

    def _write_meta(self, pid: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        meta = dict(meta)
        meta["updated"] = now_iso()
        write_json(self.root / pid / "project.json", meta)
        return meta

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for d in self.root.iterdir():
            if d.is_dir() and (d / "project.json").is_file():
                m = read_json(d / "project.json")
                if isinstance(m, dict) and valid_id(m.get("id")):
                    n = self._norm_meta(m)
                    item = {k: n[k] for k in ("id", "name", "type", "language", "content", "description", "created", "updated", "words")}
                    item["pages"] = round(n["words"] / max(1, n["gen"]["words_per_page"]), 1)
                    out.append(item)
        out.sort(key=lambda x: x.get("updated", ""), reverse=True)
        return out

    def create(self, name: str = "", type_id: str = S.DEFAULT_TYPE, language: str = "", description: str = "", content: str = "", fmt: Any = None, gen: Any = None) -> Dict[str, Any]:
        with self.lock:
            if sum(1 for _ in self.root.iterdir()) >= MAX_PROJECTS:
                raise ScriberError(400, f"Limite de {MAX_PROJECTS} projetos. Apague algum para criar outro.")
            t = type_id if isinstance(type_id, str) and type_id in S.WRITING_TYPES else S.DEFAULT_TYPE
            name = text(name, "", 100) or {"pt": "Novo texto", "en": "New text"}.get(S.lang_base(language or S.DEFAULT_LANG), "Novo texto")
            pid = (slugify(name, "texto", 24) + "-" + new_id()[:6]).lower()
            d = self.root / pid
            for sub in ("history", "exports"):
                (d / sub).mkdir(parents=True, exist_ok=True)
            meta = {"id": pid, "name": name, "type": t, "language": S.norm_lang(language), "content": content if content in ("sfw", "free") else "",
                    "format": S.norm_format(fmt, S.WRITING_TYPES[t]["preset"]), "gen": gen if isinstance(gen, dict) else {}, "ignore": [], "description": text(description, "", 400),
                    "created": now_iso(), "words": 0, "connections": {}}
            self._write_meta(pid, meta)
            write_json(d / "document.json", {"v": 1, "blocks": []})
            write_json(d / "lorebooks.json", {"v": 1, "books": []})
            return self.meta(pid)

    def update_meta(self, pid: str, patch: Any) -> Dict[str, Any]:
        p = patch if isinstance(patch, dict) else {}
        with self.lock:
            m = read_json(self.dir(pid) / "project.json") or {}
            if isinstance(p.get("name"), str) and p["name"].strip():
                m["name"] = text(p["name"], m.get("name", ""), 100)
            if isinstance(p.get("type"), str) and p["type"] in S.WRITING_TYPES:
                m["type"] = p["type"]
            if isinstance(p.get("language"), str):
                m["language"] = S.norm_lang(p["language"])
            if p.get("content") in ("", "sfw", "free"):
                m["content"] = p["content"]
            if isinstance(p.get("format"), dict):
                m["format"] = S.norm_format({**(m.get("format") if isinstance(m.get("format"), dict) else {}), **p["format"]}, S.WRITING_TYPES.get(m.get("type"), S.WRITING_TYPES[S.DEFAULT_TYPE])["preset"])
            if isinstance(p.get("gen"), dict):
                m["gen"] = {**(m.get("gen") if isinstance(m.get("gen"), dict) else {}), **p["gen"]}
            if isinstance(p.get("description"), str):
                m["description"] = text(p["description"], "", 400)
            if isinstance(p.get("author"), str):
                m["author"] = text(p["author"], "", 80)
            if isinstance(p.get("ignore"), list):
                m["ignore"] = [text(w, "", 60) for w in p["ignore"] if isinstance(w, str) and w.strip()][:500]
            if isinstance(p.get("connections"), dict):
                m["connections"] = {**(m.get("connections") if isinstance(m.get("connections"), dict) else {}), **{k: v for k, v in p["connections"].items() if isinstance(k, str) and isinstance(v, (str, int, bool))}}
            self._write_meta(pid, m)
            return self.meta(pid)

    def delete(self, pid: str) -> None:
        with self.lock:
            shutil.rmtree(self.dir(pid))

    def duplicate(self, pid: str, name: str = "") -> Dict[str, Any]:
        with self.lock:
            src = self.meta(pid)
            n = self.create(name or (src["name"] + " (cópia)"), src["type"], src["language"], src["description"], src["content"], src["format"], src["gen"])
            doc = self.get_doc(pid)
            self.save_doc(n["id"], blocks=doc["blocks"], snapshot=False)
            write_json(self.root / n["id"] / "lorebooks.json", {"v": 1, "books": self.get_books(pid)})
            self.update_meta(n["id"], {"ignore": src["ignore"], "author": src["author"]})
            return self.meta(n["id"])

    # ------------------------------------------------------------------ documento
    def get_doc(self, pid: str) -> Dict[str, Any]:
        d = read_json(self.dir(pid) / "document.json")
        blocks = D.norm_blocks(d.get("blocks") if isinstance(d, dict) else [])
        return {"blocks": blocks, "html": D.blocks_to_html(blocks), "stats": D.stats(blocks), "updated": self.meta(pid).get("updated", "")}

    def save_doc(self, pid: str, blocks: Any = None, html_src: Optional[str] = None, markdown: Optional[str] = None, snapshot: bool = True, label: str = "") -> Dict[str, Any]:
        """Grava o documento (de blocos, HTML do editor ou Markdown). `snapshot` guarda o anterior no histórico (se mudou)."""
        if blocks is None:
            blocks = D.html_to_blocks(html_src) if html_src is not None else D.markdown_to_blocks(markdown or "") if markdown is not None else []
        nb = D.norm_blocks(blocks)
        with self.lock:
            d = self.dir(pid)
            if snapshot:
                cur = D.norm_blocks((read_json(d / "document.json") or {}).get("blocks"))
                if cur and cur != nb and label:
                    self._snapshot_blocks(pid, cur, label)
            write_json(d / "document.json", {"v": 1, "blocks": nb})
            m = read_json(d / "project.json") or {}
            m["words"] = D.stats(nb)["words"]
            self._write_meta(pid, m)
        return {"stats": D.stats(nb), "updated": self.meta(pid)["updated"]}

    # ------------------------------------------------------------------ histórico (desfazer mudanças grandes)
    def _snapshot_blocks(self, pid: str, blocks: List[Dict[str, Any]], label: str) -> str:
        hid = time.strftime("%Y%m%d-%H%M%S") + "-" + new_id()[:4]
        write_json(self.root / pid / "history" / (hid + ".json"), {"v": 1, "id": hid, "label": text(label, "", 100), "t": now_iso(), "words": D.stats(blocks)["words"], "blocks": blocks})
        keep = int(max(5, min(100, ((self.store.get_settings().get("scriber") or {}).get("undo_keep") or 25))))
        files = sorted((self.root / pid / "history").glob("*.json"))
        for f in files[: max(0, len(files) - keep)]:
            f.unlink(missing_ok=True)
        return hid

    def snapshot(self, pid: str, label: str = "manual") -> str:
        with self.lock:
            self.dir(pid)
            return self._snapshot_blocks(pid, self.get_doc(pid)["blocks"], label)

    def history(self, pid: str) -> List[Dict[str, Any]]:
        out = []
        for f in sorted(self.dir(pid).joinpath("history").glob("*.json"), reverse=True):
            d = read_json(f)
            if isinstance(d, dict):
                out.append({"id": d.get("id", f.stem), "label": d.get("label", ""), "t": d.get("t", ""), "words": d.get("words", 0)})
        return out[:HISTORY_KEEP * 3]

    def restore(self, pid: str, hid: str) -> Dict[str, Any]:
        if not re.match(r"^[\w-]{6,40}$", hid or ""):
            raise ScriberError(404, "Ponto de retorno não encontrado.")
        with self.lock:
            f = self.dir(pid) / "history" / (hid + ".json")
            d = read_json(f) if f.is_file() else None
            if not isinstance(d, dict):
                raise ScriberError(404, "Ponto de retorno não encontrado.")
            self._snapshot_blocks(pid, self.get_doc(pid)["blocks"], "antes de voltar a " + text(d.get("label"), "", 40))
            return self.save_doc(pid, blocks=d.get("blocks"), snapshot=False)

    # ------------------------------------------------------------------ lorebooks
    def get_books(self, pid: str) -> List[Dict[str, Any]]:
        d = read_json(self.dir(pid) / "lorebooks.json")
        return L.norm_books(d.get("books") if isinstance(d, dict) else [])

    def save_books(self, pid: str, books: Any) -> List[Dict[str, Any]]:
        nb = L.norm_books(books)
        with self.lock:
            write_json(self.dir(pid) / "lorebooks.json", {"v": 1, "books": nb})
        return nb

    def import_book(self, pid: str, data: Any, name: str = "") -> Dict[str, Any]:
        try:
            book = L.import_any(data, name)
        except ValueError as exc:
            raise ScriberError(400, str(exc)) from None
        with self.lock:
            books = self.get_books(pid)
            if len(books) >= L.MAX_BOOKS:
                raise ScriberError(400, f"Limite de {L.MAX_BOOKS} lorebooks por projeto.")
            books.append(book)
            self.save_books(pid, books)
        return book

    # ------------------------------------------------------------------ fontes da web guardadas
    def get_sources(self, pid: str) -> List[Dict[str, Any]]:
        d = read_json(self.dir(pid) / "sources.json")
        out = []
        for s in (d.get("sources") if isinstance(d, dict) else []) or []:
            if isinstance(s, dict) and isinstance(s.get("url"), str) and s["url"].startswith(("http://", "https://")):
                out.append({"title": text(s.get("title"), "", 200), "url": text(s.get("url"), "", 600), "note": text(s.get("note"), "", 800), "text": text(s.get("text"), "", 6000), "pinned": bool(s.get("pinned"))})
        return out[:60]

    def save_sources(self, pid: str, sources: Any) -> List[Dict[str, Any]]:
        ns = []
        for s in sources if isinstance(sources, list) else []:
            if isinstance(s, dict) and isinstance(s.get("url"), str) and s["url"].startswith(("http://", "https://")):
                ns.append({"title": text(s.get("title"), "", 200), "url": text(s.get("url"), "", 600), "note": text(s.get("note"), "", 800), "text": text(s.get("text"), "", 6000), "pinned": bool(s.get("pinned"))})
        with self.lock:
            write_json(self.dir(pid) / "sources.json", {"v": 1, "sources": ns[:60]})
        return ns[:60]

    # ------------------------------------------------------------------ exportar / importar
    def _export_name(self, pid: str, fmt: str) -> str:
        m = self.meta(pid)
        return f"{slugify(m['name'], 'texto', 40)}-{time.strftime('%Y%m%d-%H%M%S')}.{fmt}"

    def render(self, pid: str, fmt: str) -> bytes:
        if fmt not in EXPORT_FORMATS:
            raise ScriberError(400, "Formato inválido: " + ", ".join(EXPORT_FORMATS))
        m = self.meta(pid)
        blocks = self.get_doc(pid)["blocks"]
        if fmt == "docx":
            return X.build_docx(blocks, {"title": m["name"], "author": m["author"] or m["format"]["author"]}, m["format"], m["language"])
        if fmt == "md":
            return D.blocks_to_markdown(blocks).encode("utf-8")
        if fmt == "txt":
            return D.blocks_to_text(blocks).replace("\f", "\n\n").encode("utf-8")
        f = m["format"]
        css = (f"body{{font-family:'{f['font']}',serif;font-size:{f['size']}pt;line-height:{f['line']};max-width:42em;margin:2em auto;padding:0 1em}}p{{margin:0 0 {f['space_after']}pt;text-indent:{f['indent']}cm;text-align:{f['align']}}}"
               "h1,h2,h3{text-indent:0}blockquote{margin:1em 2em;font-style:italic}.pb{break-after:page}")
        doc = f'<!doctype html><html lang="{m["language"]}"><head><meta charset="utf-8"><title>{html.escape(m["name"])}</title><style>{css}</style></head><body>{D.blocks_to_html(blocks)}</body></html>'
        return doc.encode("utf-8")

    def export(self, pid: str, fmt: str) -> Dict[str, Any]:
        data = self.render(pid, fmt)
        with self.lock:
            name = self._export_name(pid, fmt)
            ed = self.dir(pid) / "exports"
            ed.mkdir(exist_ok=True)
            (ed / name).write_bytes(data)
            files = sorted(ed.iterdir(), key=lambda p: p.stat().st_mtime)
            for f in files[: max(0, len(files) - MAX_EXPORTS)]:
                f.unlink(missing_ok=True)
        return {"name": name, "size": len(data), "format": fmt}

    def list_exports(self, pid: str) -> List[Dict[str, Any]]:
        ed = self.dir(pid) / "exports"
        out = [{"name": p.name, "size": p.stat().st_size, "t": p.stat().st_mtime} for p in ed.iterdir() if p.is_file()] if ed.is_dir() else []
        out.sort(key=lambda x: -x["t"])
        return out

    def export_path(self, pid: str, name: str) -> Path:
        name = safe_filename(name)
        p = self.dir(pid) / "exports" / name
        if not p.is_file() or p.parent != (self.dir(pid) / "exports"):
            raise ScriberError(404, "Arquivo não encontrado.")
        return p

    def delete_export(self, pid: str, name: str) -> None:
        self.export_path(pid, name).unlink(missing_ok=True)

    def import_file(self, pid: str, filename: str, data: bytes, mode: str = "replace") -> Dict[str, Any]:
        """Importa .docx, .md, .txt ou .html para o projeto: `replace` (guarda o anterior no histórico) ou `append`."""
        if len(data) > MAX_IMPORT:
            raise ScriberError(413, "Arquivo grande demais para importar.")
        ext = Path(str(filename or "")).suffix.lower()
        meta: Dict[str, Any] = {}
        if ext == ".docx" or data[:2] == b"PK":
            try:
                blocks, meta = X.parse_docx(data)
            except X.DocxError as exc:
                raise ScriberError(400, str(exc)) from None
        else:
            try:
                s = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                s = data.decode("latin-1")
            if ext in (".html", ".htm"):
                blocks = D.html_to_blocks(s)
            elif ext in (".md", ".markdown"):
                blocks = D.markdown_to_blocks(s)
            else:
                blocks = _plain_blocks(s)
        if not blocks:
            raise ScriberError(400, "Não achei texto nesse arquivo.")
        with self.lock:
            cur = self.get_doc(pid)["blocks"]
            nb = (cur + blocks) if mode == "append" else blocks
            if cur:
                self._snapshot_blocks(pid, cur, "antes de importar " + text(filename, "arquivo", 40))
            self.save_doc(pid, blocks=nb, snapshot=False)
            patch: Dict[str, Any] = {}
            if meta.get("language") and mode != "append":
                patch["language"] = meta["language"]
            if meta.get("author") and not self.meta(pid)["author"]:
                patch["author"] = meta["author"]
            if patch:
                self.update_meta(pid, patch)
        return {"stats": D.stats(nb), "added": len(blocks), "meta": meta}


def _plain_blocks(s: str) -> List[Dict[str, Any]]:
    """Texto puro: cada linha não vazia é um parágrafo (sem interpretar Markdown)."""
    return [D.block("p", [D.run(ln.strip())]) for ln in s.replace("\r\n", "\n").split("\n") if ln.strip()][: D.MAX_BLOCKS]
