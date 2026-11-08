"""Arquivos e pastas para o Computer Use: listar, ler, criar (qualquer formato que o ASTA sabe escrever), copiar, mover, organizar e **apagar para a lixeira do ASTA**.

Regras (princípio 1 — o usuário no controle dos dados dele):
* nada é apagado de verdade: «apagar» move para `~/.asta/computer/trash/<tarefa>/` e dá para restaurar; sobrescrever um arquivo guarda o antigo na lixeira antes;
* toda alteração entra no **diário** da tarefa e `undo()` desfaz tudo na ordem inversa («Desfazer» na tela);
* todo caminho passa por `guard.check_path` (segredos, pastas do sistema e dados do ASTA ficam de fora).
"""
from __future__ import annotations

import base64
import fnmatch
import io
import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from .. import attachments as att
from . import guard


class FileError(Exception):
    pass


MAX_TEXT_WRITE = 5_000_000        # bytes de um arquivo criado de uma vez
MAX_LIST = 300

KINDS: Dict[str, Tuple[str, ...]] = {
    "image": ("png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "tif", "tiff", "heic", "avif", "ico", "psd", "kra", "xcf", "ora", "raw", "cr2", "nef", "arw"),
    "video": ("mp4", "mkv", "mov", "avi", "webm", "flv", "wmv", "m4v", "mpg", "mpeg", "3gp", "ts"),
    "audio": ("mp3", "wav", "ogg", "flac", "m4a", "aac", "opus", "wma", "aup3", "mid", "midi"),
    "document": ("pdf", "doc", "docx", "odt", "rtf", "txt", "md", "epub", "tex", "pages"),
    "spreadsheet": ("xls", "xlsx", "ods", "csv", "tsv", "numbers"),
    "presentation": ("ppt", "pptx", "odp", "key"),
    "archive": ("zip", "rar", "7z", "tar", "gz", "tgz", "bz2", "xz", "iso", "cbz", "cbr", "zst"),
    "code": ("py", "js", "ts", "jsx", "tsx", "html", "css", "json", "xml", "yml", "yaml", "toml", "c", "cpp", "h", "rs", "go", "java", "kt", "cs", "php", "rb", "sh", "bat", "sql", "lua", "gd"),
    "program": ("exe", "msi", "apk", "appimage", "deb", "rpm", "dmg", "pkg", "bin", "run", "jar"),
}
CATEGORY_NAMES = {   # nome da pasta criada por `organize_folder(by="type")`
    "pt": {"image": "Imagens", "video": "Vídeos", "audio": "Áudios", "document": "Documentos", "spreadsheet": "Planilhas", "presentation": "Apresentações", "archive": "Compactados",
           "code": "Código", "program": "Programas e instaladores", "other": "Outros"},
    "en": {"image": "Images", "video": "Videos", "audio": "Audio", "document": "Documents", "spreadsheet": "Spreadsheets", "presentation": "Presentations", "archive": "Archives",
           "code": "Code", "program": "Programs and installers", "other": "Other"},
}


def kind_of(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    for k, exts in KINDS.items():
        if ext in exts:
            return k
    return "other"


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n} B"


def _chk(path: str, op: str, base: Optional[Path] = None) -> Path:
    try:
        return guard.check_path(path, op, base=base)
    except guard.Blocked as exc:
        raise FileError("BLOQUEADO pelo ASTA: " + str(exc)) from None


# --------------------------------------------------------------------------- diário e lixeira


class Journal:
    """Registro desfazível das mudanças de uma tarefa (vai para o JSON da tarefa)."""

    def __init__(self, task_id: str, entries: Optional[List[dict]] = None):
        self.task_id = task_id
        self.entries: List[dict] = entries if entries is not None else []
        self._n = len(self.entries)

    def trash_dir(self) -> Path:
        d = guard.data_dir() / "trash" / self.task_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def stash(self, p: Path) -> str:
        """Guarda `p` (arquivo ou pasta) na lixeira da tarefa e devolve o novo caminho."""
        self._n += 1
        dst = self.trash_dir() / f"{self._n:04d}-{p.name}"
        shutil.move(str(p), str(dst))
        return str(dst)

    def add(self, entry: dict) -> None:
        self.entries.append(entry)


def _unique(p: Path) -> Path:
    if not p.exists():
        return p
    stem, suf = (p.stem, p.suffix) if p.is_file() or not p.is_dir() else (p.name, "")
    for i in range(2, 10000):
        c = p.with_name(f"{stem} ({i}){suf}")
        if not c.exists():
            return c
    raise FileError("Nomes demais repetidos.")


def undo(entries: List[dict]) -> List[str]:
    """Desfaz o diário, do fim para o começo. Devolve o que foi feito (e o que não deu para desfazer)."""
    notes: List[str] = []
    for e in reversed(entries):
        if e.get("undone"):
            continue
        op = e.get("op")
        try:
            if op == "mkdir":
                p = Path(e["path"])
                if p.is_dir() and not any(p.iterdir()):
                    p.rmdir()
                    notes.append(f"pasta removida: {p}")
                elif p.exists():
                    notes.append(f"mantive {p} (tem conteúdo)")
            elif op in ("create", "copy"):
                p = Path(e["path"] if op == "create" else e["dst"])
                if p.exists():
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                    notes.append(f"removido: {p}")
                if e.get("backup") and Path(e["backup"]).exists():
                    shutil.move(e["backup"], str(p))
                    notes.append(f"restaurado o original: {p}")
            elif op == "move":
                src, dst = Path(e["src"]), Path(e["dst"])
                if dst.exists() and not src.exists():
                    src.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(src))
                    notes.append(f"voltou: {src}")
                elif src.exists():
                    notes.append(f"não voltei {dst.name}: já existe algo em {src}")
                if e.get("backup") and Path(e["backup"]).exists() and not dst.exists():
                    shutil.move(e["backup"], str(dst))
            elif op == "trash":
                p, t = Path(e["path"]), Path(e["trash"])
                if t.exists() and not p.exists():
                    p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(t), str(p))
                    notes.append(f"restaurado da lixeira: {p}")
                elif p.exists():
                    notes.append(f"não restaurei {p.name}: já existe algo no lugar")
            e["undone"] = True
        except OSError as exc:
            notes.append(f"não consegui desfazer {op}: {exc}")
    return notes


# --------------------------------------------------------------------------- leitura


def _entry_line(p: Path, st: os.stat_result) -> str:
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
    if p.is_dir():
        return f"[pasta] {p.name}/  ({when})"
    return f"[{kind_of(p.name)}] {p.name}  ({_fmt_size(st.st_size)}, {when})"


def list_dir(path: str, depth: int = 1, limit: int = 200, show_hidden: bool = False) -> str:
    root = _chk(path, guard.READ)
    if not root.is_dir():
        raise FileError(f"Não é uma pasta: {root}")
    depth, limit = max(1, min(int(depth or 1), 3)), max(1, min(int(limit or 200), MAX_LIST))
    lines: List[str] = [f"{root}"]
    count, hidden_sensitive = 0, 0

    def walk(d: Path, level: int) -> None:
        nonlocal count, hidden_sensitive
        try:
            entries = sorted(os.scandir(d), key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))
        except OSError as exc:
            lines.append("  " * level + f"(sem acesso: {exc.strerror or exc})")
            return
        for e in entries:
            if count >= limit:
                return
            if e.name.startswith(".") and not show_hidden:
                continue
            p = Path(e.path)
            try:
                guard.check_path(str(p), guard.READ)
            except guard.Blocked:
                hidden_sensitive += 1
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            lines.append("  " * level + _entry_line(p, st))
            count += 1
            if e.is_dir(follow_symlinks=False) and level + 1 < depth:
                walk(p, level + 1)

    walk(root, 0)
    if count >= limit:
        lines.append(f"… (parei em {limit} itens; use um caminho mais específico)")
    if hidden_sensitive:
        lines.append(f"({hidden_sensitive} item(ns) protegido(s) não aparecem)")
    if count == 0:
        lines.append("(pasta vazia)")
    return "\n".join(lines)


def read_file(path: str, max_chars: int = 12000) -> str:
    p = _chk(path, guard.READ)
    if not p.is_file():
        raise FileError(f"Não é um arquivo: {p}")
    max_chars = max(500, min(int(max_chars or 12000), 60000))
    item = att.analyze(p, p.name, "", max_chars=max_chars)
    body = item.get("text") or ""
    notes = "; ".join(item.get("notes") or [])
    head = f"{p.name} — {_fmt_size(p.stat().st_size)} ({item.get('kind')})"
    if not body:
        return head + (f"\n({notes})" if notes else "\n(sem texto para mostrar)")
    return head + (f"\n({notes})" if notes else "") + "\n---\n" + body


def find_files(root: str, pattern: str = "", kind: str = "", limit: int = 100, max_depth: int = 6) -> str:
    base = _chk(root, guard.READ)
    if not base.is_dir():
        raise FileError(f"Não é uma pasta: {base}")
    pat = str(pattern or "").strip()
    wild = any(c in pat for c in "*?[")
    want_kind = kind if kind in KINDS else ""
    limit = max(1, min(int(limit or 100), 300))
    hits: List[str] = []
    base_depth = len(base.parts)
    for r, dnames, fnames in os.walk(base):
        rp = Path(r)
        if len(rp.parts) - base_depth >= max_depth:
            dnames[:] = []
        dnames[:] = [d for d in dnames if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
        for n in fnames + dnames:
            if pat and not (fnmatch.fnmatch(n.lower(), pat.lower()) if wild else pat.lower() in n.lower()):
                continue
            if want_kind and kind_of(n) != want_kind:
                continue
            p = rp / n
            try:
                guard.check_path(str(p), guard.READ)
                st = p.stat()
            except (guard.Blocked, OSError):
                continue
            hits.append(f"{p}  ({'pasta' if p.is_dir() else _fmt_size(st.st_size)})")
            if len(hits) >= limit:
                return "\n".join(hits) + f"\n… (limite de {limit} resultados)"
    return "\n".join(hits) if hits else "(nada encontrado)"


# --------------------------------------------------------------------------- escrita


def make_dir(path: str, journal: Journal) -> str:
    p = _chk(path, guard.WRITE)
    if p.exists():
        if p.is_dir():
            return f"A pasta já existe: {p}"
        raise FileError(f"Já existe um arquivo com esse nome: {p}")
    missing = [q for q in [p, *p.parents] if not q.exists()]
    p.mkdir(parents=True, exist_ok=True)
    for q in reversed(missing):   # a mais externa primeiro: desfazer remove de dentro para fora
        journal.add({"op": "mkdir", "path": str(q)})
    return f"Pasta criada: {p}"


def _xml_p(line: str, heading: bool) -> str:
    rpr = '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr>' if heading else ""
    return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>'


def build_docx(text: str) -> bytes:
    paras = []
    for line in str(text).replace("\r\n", "\n").split("\n"):
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        paras.append(_xml_p(m.group(2) if m else line, bool(m)))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(paras) + "</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def _rows(text: str) -> List[List[str]]:
    import csv
    import json

    s = str(text).strip()
    if s.startswith("["):
        try:
            data = json.loads(s)
            if data and all(isinstance(r, list) for r in data):
                return [[("" if c is None else str(c)) for c in r] for r in data]
            if data and all(isinstance(r, dict) for r in data):
                keys = list(dict.fromkeys(k for r in data for k in r))
                return [keys] + [[("" if r.get(k) is None else str(r.get(k))) for k in keys] for r in data]
        except ValueError:
            pass
    dialect = "excel-tab" if s.count("\t") > s.count(",") else "excel"
    return [row for row in csv.reader(io.StringIO(s), dialect=dialect)]


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def build_xlsx(text: str) -> bytes:
    rows = _rows(text)
    out = []
    for ri, row in enumerate(rows, 1):
        cells = []
        for ci, val in enumerate(row):
            ref = f"{_col(ci)}{ri}"
            if re.fullmatch(r"-?\d+(\.\d+)?", val.strip() or "x"):
                cells.append(f'<c r="{ref}"><v>{val.strip()}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(val)}</t></is></c>')
        out.append(f'<row r="{ri}">{"".join(cells)}</row>')
    sheet = '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(out) + "</sheetData></worksheet>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Planilha1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def build_pdf(text: str) -> bytes:
    """PDF simples (texto em Helvetica, Latin-1, várias páginas). Caracteres fora do Latin-1 viram «?»."""
    lines: List[str] = []
    for raw in str(text).replace("\r\n", "\n").split("\n"):
        raw = raw.replace("\t", "    ")
        while len(raw) > 92:
            cut = raw.rfind(" ", 0, 92)
            cut = cut if cut > 40 else 92
            lines.append(raw[:cut])
            raw = raw[cut:].lstrip()
        lines.append(raw)
    per_page = 52
    pages = [lines[i:i + per_page] for i in range(0, max(len(lines), 1), per_page)] or [[""]]
    objs: List[bytes] = []

    def pdf_str(s: str) -> bytes:
        b = s.encode("latin-1", "replace")
        return b"(" + b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"

    n_pages = len(pages)
    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    font_id = 3 + n_pages * 2
    for i, pg in enumerate(pages):
        content = b"BT /F1 11 Tf 14 TL 50 790 Td " + b"".join(pdf_str(l) + b" Tj T* " for l in pg) + b"ET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {4 + i * 2} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode())
        objs.append(f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


BINARY_EXT = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff", "heic", "psd", "kra", "xcf", "mp3", "mp4", "mkv", "mov", "avi", "webm", "wav", "ogg", "flac", "m4a", "aac", "7z", "rar", "gz", "tar",
              "exe", "msi", "dmg", "iso", "pptx", "odt", "ods", "odp", "epub", "sqlite", "db"}


def render_content(path: Path, content: str, encoding: str = "text") -> bytes:
    """Converte o conteúdo pedido nos bytes do formato do arquivo (pela extensão). Texto puro serve para txt, md, csv, json, html, svg, código, legendas…; docx, xlsx e pdf o ASTA escreve sozinho."""
    ext = path.suffix.lower().lstrip(".")
    if encoding == "base64":
        try:
            return base64.b64decode(re.sub(r"\s+", "", content), validate=True)
        except (ValueError, base64.binascii.Error):
            raise FileError("base64 inválido.") from None
    if ext == "docx":
        return build_docx(content)
    if ext == "xlsx":
        return build_xlsx(content)
    if ext == "pdf":
        return build_pdf(content)
    if ext in BINARY_EXT:
        raise FileError(f"O formato .{ext} é binário e não se escreve como texto. Crie-o com um programa (open_app ou run_program: ffmpeg, pandoc, soffice, magick…) ou envie o conteúdo em base64 (encoding=\"base64\").")
    return content.encode("utf-8")


def create_file(path: str, content: str, journal: Journal, overwrite: bool = False, encoding: str = "text", make_parents: bool = True) -> str:
    p = _chk(path, guard.WRITE)
    if p.is_dir():
        raise FileError(f"Já existe uma pasta com esse nome: {p}")
    data = render_content(p, str(content or ""), encoding)
    if len(data) > MAX_TEXT_WRITE:
        raise FileError("Conteúdo grande demais para criar de uma vez (limite 5 MB).")
    backup = ""
    if p.exists():
        if not overwrite:
            raise FileError(f"Já existe: {p}. Escolha outro nome ou peça para sobrescrever (overwrite=true; o original vai para a lixeira do ASTA).")
        backup = journal.stash(p)
    if not p.parent.exists():
        if not make_parents:
            raise FileError(f"A pasta {p.parent} não existe.")
        _mk_parents(p.parent, journal)
    p.write_bytes(data)
    journal.add({"op": "create", "path": str(p), "backup": backup})
    return f"Arquivo criado: {p} ({_fmt_size(len(data))})" + (" — o original foi para a lixeira do ASTA" if backup else "")


def _mk_parents(d: Path, journal: Journal) -> None:
    guard.check_path(str(d), guard.WRITE)
    missing = [q for q in [d, *d.parents] if not q.exists()]
    d.mkdir(parents=True, exist_ok=True)
    for q in reversed(missing):
        journal.add({"op": "mkdir", "path": str(q)})


def _dest(src: Path, dst: str, overwrite: bool, journal: Journal, op: str) -> Tuple[Path, str]:
    d = _chk(dst, guard.WRITE)
    if d.is_dir() and not (src.is_dir() and d == src):
        d = d / src.name
        d = guard.check_path(str(d), guard.WRITE)
    if _inside(d, src) and src.is_dir():
        raise FileError("Não dá para colocar uma pasta dentro dela mesma.")
    backup = ""
    if d.exists():
        if d.resolve() == src.resolve():
            raise FileError("Origem e destino são o mesmo lugar.")
        if not overwrite:
            raise FileError(f"Já existe: {d}. Use outro nome/pasta ou overwrite=true (o original vai para a lixeira).")
        _chk(str(d), guard.DELETE)
        backup = journal.stash(d)
    if not d.parent.exists():
        _mk_parents(d.parent, journal)
    return d, backup


def _inside(a: Path, b: Path) -> bool:
    try:
        a.resolve().relative_to(b.resolve())
        return True
    except ValueError:
        return False


def copy_item(src: str, dst: str, journal: Journal, overwrite: bool = False) -> str:
    s = _chk(src, guard.READ)
    if not s.exists():
        raise FileError(f"Não existe: {s}")
    d, backup = _dest(s, dst, overwrite, journal, "copy")
    if s.is_dir():
        shutil.copytree(s, d, symlinks=True)
    else:
        shutil.copy2(s, d)
    journal.add({"op": "copy", "src": str(s), "dst": str(d), "backup": backup})
    return f"Copiado: {s} → {d}"


def move_item(src: str, dst: str, journal: Journal, overwrite: bool = False) -> str:
    s = _chk(src, guard.DELETE)
    if not s.exists():
        raise FileError(f"Não existe: {s}")
    d, backup = _dest(s, dst, overwrite, journal, "move")
    shutil.move(str(s), str(d))
    journal.add({"op": "move", "src": str(s), "dst": str(d), "backup": backup})
    return f"Movido: {s} → {d}"


def trash_item(path: str, journal: Journal) -> str:
    p = _chk(path, guard.DELETE)
    if not p.exists() and not p.is_symlink():
        raise FileError(f"Não existe: {p}")
    t = journal.stash(p)
    journal.add({"op": "trash", "path": str(p), "trash": t})
    return f"Enviado para a lixeira do ASTA (dá para restaurar em Desfazer): {p}"


# --------------------------------------------------------------------------- organizar


def organize_plan(path: str, by: str = "type", lang: str = "pt", recursive: bool = False, limit: int = 2000) -> List[Tuple[Path, Path]]:
    root = _chk(path, guard.WRITE)
    if not root.is_dir():
        raise FileError(f"Não é uma pasta: {root}")
    names = CATEGORY_NAMES.get(lang, CATEGORY_NAMES["pt"])
    by = by if by in ("type", "extension", "date", "name") else "type"
    plan: List[Tuple[Path, Path]] = []
    walker = os.walk(root) if recursive else [(str(root), [], [e.name for e in os.scandir(root) if e.is_file(follow_symlinks=False)])]
    skip_dirs = set(names.values())
    for r, dnames, fnames in walker:
        rp = Path(r)
        if rp != root and rp.parent == root and rp.name in skip_dirs:
            dnames[:] = []
            continue
        dnames[:] = [d for d in dnames if not d.startswith(".") and d not in skip_dirs]
        for n in sorted(fnames):
            if n.startswith("."):
                continue
            p = rp / n
            try:
                guard.check_path(str(p), guard.DELETE)
                st = p.stat()
            except (guard.Blocked, OSError):
                continue
            if by == "type":
                folder = names[kind_of(n)]
            elif by == "extension":
                folder = (n.rsplit(".", 1)[-1].upper() if "." in n else ("SEM-EXTENSAO" if lang == "pt" else "NO-EXTENSION"))
            elif by == "date":
                folder = time.strftime("%Y-%m", time.localtime(st.st_mtime))
            else:
                ch = n[:1].upper()
                folder = ch if ch.isalnum() else "#"
            target = root / folder / n
            if target.parent == p.parent:
                continue
            plan.append((p, target))
            if len(plan) >= limit:
                return plan
    return plan


def organize_apply(plan: List[Tuple[Path, Path]], journal: Journal) -> int:
    n = 0
    for src, dst in plan:
        if not src.exists():
            continue
        if not dst.parent.exists():
            _mk_parents(dst.parent, journal)
        final = _unique(dst)
        shutil.move(str(src), str(final))
        journal.add({"op": "move", "src": str(src), "dst": str(final), "backup": ""})
        n += 1
    return n


def zip_items(paths: List[str], dst: str, journal: Journal) -> str:
    d = _chk(dst, guard.WRITE)
    if d.suffix.lower() != ".zip":
        d = d.with_suffix(".zip")
    if d.exists():
        raise FileError(f"Já existe: {d}")
    srcs = [_chk(p, guard.READ) for p in paths][:500]
    if not srcs:
        raise FileError("Nenhum arquivo para compactar.")
    if not d.parent.exists():
        _mk_parents(d.parent, journal)
    count = 0
    with zipfile.ZipFile(d, "w", zipfile.ZIP_DEFLATED) as z:
        for s in srcs:
            if s.is_dir():
                for r, _, fnames in os.walk(s):
                    for n in fnames:
                        fp = Path(r) / n
                        try:
                            guard.check_path(str(fp), guard.READ)
                        except guard.Blocked:
                            continue
                        z.write(fp, str(Path(s.name) / fp.relative_to(s)))
                        count += 1
                        if count > 20000:
                            raise FileError("Arquivos demais para compactar.")
            elif s.is_file():
                z.write(s, s.name)
                count += 1
    journal.add({"op": "create", "path": str(d), "backup": ""})
    return f"Compactado: {d} ({count} arquivo(s), {_fmt_size(d.stat().st_size)})"


def exists_report(paths: List[str]) -> List[Tuple[str, bool]]:
    """Para o Revisor: cada caminho citado ainda existe?"""
    out = []
    for p in paths[:60]:
        try:
            out.append((p, Path(p).expanduser().exists()))
        except OSError:
            out.append((p, False))
    return out
