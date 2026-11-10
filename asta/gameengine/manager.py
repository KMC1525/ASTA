"""Game Engine — projetos em disco, árvore de arquivos, pacote jogável (data.js + index.html) e histórico para desfazer.

Cada projeto é uma pasta comum em `~/.asta/gameengine/<id>/`:

    project.json     nome, tipo (2D/2.5D/3D/VR/AR), gênero, tema, configurações, registro
    game/            o jogo: scenes/ maps/ scripts/ assets/images/ assets/sound/ data/   ← é isto que a aba Code mostra e que as exportações levam
    docs/            roteiros, GDD e diálogos (aba Scripts)
    editor/          documentos de edição (imagens em camadas, projetos de áudio) — não vão para o jogo
    history/         instantâneos (.zip) antes de cada mudança grande da IA
    exports/         pacotes gerados pela aba Publish

O motor (JavaScript) NÃO fica na pasta do projeto: é acrescentado na hora de jogar/exportar, então atualizar o ASTA atualiza o motor de todos os jogos.
Arquivos e respostas da IA são entrada não confiável: caminhos são validados (nada de `..`), tamanhos limitados e o JSON passa pelo `schema`."""
from __future__ import annotations

import html
import io
import json
import os
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import __version__
from ..util import new_id, now_iso, read_json, safe_filename, slugify, text, write_json
from . import schema as S

RUNTIME = Path(__file__).parent / "runtime"
THREE = Path(__file__).parent.parent / "runtime" / "vendor" / "three.min.js"
ENGINE_FILES = ("ge_core.js", "ge_2d.js", "ge_3d.js", "ge.css")
EDIT_FILES = ("ge_edit.js",)

MAX_PROJECTS = 300
MAX_FILE = 64 * 1024 * 1024
MAX_PROJECT = 1024 * 1024 * 1024
MAX_DEPTH = 12
MAX_ENTRIES = 6000
AREAS = ("game", "docs", "editor")
TEXT_EXT = {".js", ".mjs", ".json", ".css", ".md", ".txt", ".svg", ".html", ".xml", ".csv", ".yml", ".yaml", ".toml", ".glsl", ".frag", ".vert", ".gdd", ".dialogue"}
BIN_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".wav", ".mp3", ".ogg", ".m4a", ".flac", ".glb", ".gltf", ".bin", ".ttf", ".woff", ".woff2", ".ico", ".mp4", ".webm"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
SND_EXT = {".wav", ".mp3", ".ogg", ".m4a", ".flac"}
SEG = re.compile(r"^[\w][\w .+@()\-]{0,95}$", re.U)
CSP = ("sandbox allow-scripts allow-pointer-lock allow-modals allow-popups allow-forms; default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' data: blob:; connect-src 'self' data: blob:; font-src 'self' data:; worker-src blob:; frame-ancestors 'self'")


class EngineError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _under(target: Path, root: Path) -> bool:
    root = Path(root).resolve()
    return target == root or root in target.parents


def valid_id(pid: Any) -> bool:
    return isinstance(pid, str) and re.match(r"^[a-z0-9_-]{3,40}$", pid) is not None


def clean_rel(rel: Any) -> str:
    """Caminho relativo seguro dentro de uma área («pasta/sub/arquivo.ext»); levanta EngineError em qualquer coisa suspeita."""
    s = str(rel or "").replace("\\", "/").strip().strip("/")
    if not s:
        return ""
    if "\x00" in s or len(s) > 400:
        raise EngineError(400, "Caminho inválido.")
    parts = s.split("/")
    if len(parts) > MAX_DEPTH:
        raise EngineError(400, "Pastas demais aninhadas.")
    for p in parts:
        if p in (".", "..") or not SEG.match(p) or p.startswith(".") or p.endswith((".", " ")):
            raise EngineError(400, f"Nome inválido: «{p[:40]}». Use letras, números, espaço, ponto, hífen e sublinhado.")
    return "/".join(parts)


class EngineManager:
    def __init__(self, store: Any):
        self.store = store
        self.root = Path(store.home) / "gameengine"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    # ------------------------------------------------------------------ projetos
    def dir(self, pid: str) -> Path:
        if not valid_id(pid):
            raise EngineError(404, "Projeto não encontrado.")
        d = self.root / pid
        if not (d / "project.json").is_file():
            raise EngineError(404, "Projeto não encontrado.")
        return d

    def meta(self, pid: str) -> Dict[str, Any]:
        m = read_json(self.dir(pid) / "project.json")
        if not isinstance(m, dict):
            raise EngineError(500, "project.json ilegível.")
        return m

    def _write_meta(self, pid: str, meta: Dict[str, Any]) -> None:
        meta["updated"] = now_iso()
        write_json(self.root / pid / "project.json", meta)

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for d in self.root.iterdir():
            if d.is_dir() and (d / "project.json").is_file():
                m = read_json(d / "project.json")
                if isinstance(m, dict) and valid_id(m.get("id")):
                    out.append(self.summary(m))
        out.sort(key=lambda x: x.get("updated", ""), reverse=True)
        return out

    def summary(self, m: Dict[str, Any]) -> Dict[str, Any]:
        theme = m.get("theme") if m.get("theme") in S.THEMES else "forest"
        c = S.THEME_COLORS[theme]
        d = self.root / m["id"]
        return {"id": m["id"], "name": m.get("name", ""), "kind": m.get("kind", "2d"), "genre": m.get("genre", ""), "theme": theme, "description": m.get("description", ""), "created": m.get("created", ""), "updated": m.get("updated", ""),
                "scenes": len(list((d / "game" / "scenes").glob("*.scene.json"))) if (d / "game" / "scenes").is_dir() else 0, "colors": [c["top"], c["bottom"], c["ground"]], "language": m.get("language", "pt")}

    def create(self, name: str = "", kind: str = "2d", genre: str = "", theme: str = "forest", description: str = "", language: str = "pt") -> Dict[str, Any]:
        with self.lock:
            if sum(1 for _ in self.root.iterdir()) >= MAX_PROJECTS:
                raise EngineError(400, f"Limite de {MAX_PROJECTS} projetos. Apague algum para criar outro.")
            kind = kind if kind in S.KINDS else "2d"
            genre = genre if genre in S.GENRES and kind in S.GENRES[genre]["kinds"] else S.DEFAULT_GENRE[kind]
            pid = (slugify(name or "jogo", "jogo", 24) + "-" + new_id()[:6]).lower()
            d = self.root / pid
            for sub in ("game/scenes", "game/maps", "game/scripts", "game/assets/images", "game/assets/sound", "game/data", "docs", "editor/assets", "editor/sound", "history", "exports"):
                (d / sub).mkdir(parents=True, exist_ok=True)
            meta = {"schema": S.SCHEMA_PROJECT, "id": pid, "name": text(name, "Meu jogo", 60), "kind": kind, "genre": genre, "theme": theme if theme in S.THEMES else "forest", "language": language if language in ("pt", "en") else "pt",
                    "description": text(description, "", 400), "created": now_iso(), "updated": now_iso(), "start": "main", "settings": S.norm_project_settings({}, kind), "version": 1, "engine": __version__, "log": [], "connections": {}, "publish": {}}
            write_json(d / "project.json", meta)
            return meta

    def update_meta(self, pid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            m = self.meta(pid)
            if "name" in patch:
                m["name"] = text(patch["name"], m["name"], 60)
            if "description" in patch:
                m["description"] = text(patch["description"], "", 400)
            if patch.get("theme") in S.THEMES:
                m["theme"] = patch["theme"]
            if patch.get("language") in ("pt", "en"):
                m["language"] = patch["language"]
            if patch.get("kind") in S.KINDS and patch["kind"] != m["kind"]:
                if self.list_scenes(pid):
                    raise EngineError(400, "O tipo do jogo não muda depois de criado (as cenas são diferentes em 2D e 3D). Crie um jogo novo.")
                m["kind"] = patch["kind"]
                m["genre"] = S.DEFAULT_GENRE[m["kind"]]
            if patch.get("genre") in S.GENRES and m["kind"] in S.GENRES[patch["genre"]]["kinds"]:
                m["genre"] = patch["genre"]
            if isinstance(patch.get("settings"), dict):
                m["settings"] = S.norm_project_settings(dict(m.get("settings") or {}, **patch["settings"]), m["kind"])
            if isinstance(patch.get("publish"), dict):
                m["publish"] = {k: text(v, "", 200) if isinstance(v, str) else v for k, v in patch["publish"].items() if isinstance(k, str) and len(k) < 40 and isinstance(v, (str, int, float, bool))}
            if isinstance(patch.get("connections"), dict):
                m["connections"] = {k: text(v, "", 80) for k, v in patch["connections"].items() if k in ("code_session", "studio_project", "canvas") and isinstance(v, str)}
            if isinstance(patch.get("start"), str) and (self.dir(pid) / "game" / "scenes" / f"{clean_rel(patch['start'])}.scene.json").is_file():
                m["start"] = patch["start"]
            self._write_meta(pid, m)
            return m

    def log(self, pid: str, kind: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        with self.lock:
            m = self.meta(pid)
            m.setdefault("log", []).append(dict({"t": now_iso(), "kind": kind, "msg": text(message, "", 300)}, **(extra or {})))
            m["log"] = m["log"][-60:]
            self._write_meta(pid, m)

    def delete(self, pid: str) -> None:
        with self.lock:
            d = self.dir(pid)
            if not _under(d.resolve(), self.root):
                raise EngineError(400, "Caminho inválido.")
            shutil.rmtree(d, ignore_errors=True)

    def duplicate(self, pid: str, name: str = "") -> Dict[str, Any]:
        with self.lock:
            src = self.dir(pid)
            m = self.meta(pid)
            new = self.create((name or m["name"] + " (cópia)"), m["kind"], m["genre"], m["theme"], m.get("description", ""), m.get("language", "pt"))
            dst = self.root / new["id"]
            for area in ("game", "docs", "editor"):
                shutil.rmtree(dst / area, ignore_errors=True)
                if (src / area).is_dir():
                    shutil.copytree(src / area, dst / area)
            new.update({k: m[k] for k in ("start", "settings", "publish") if k in m})
            self._write_meta(new["id"], new)
            return new

    # ------------------------------------------------------------------ cenas e mapas
    def list_scenes(self, pid: str) -> List[str]:
        d = self.dir(pid) / "game" / "scenes"
        names = sorted(p.name[: -len(".scene.json")] for p in d.glob("*.scene.json")) if d.is_dir() else []
        m = self.meta(pid)
        if m.get("start") in names:
            names.remove(m["start"])
            names.insert(0, m["start"])
        return names

    def get_scene(self, pid: str, name: str) -> Dict[str, Any]:
        p = self.dir(pid) / "game" / "scenes" / f"{clean_rel(name)}.scene.json"
        sc = read_json(p)
        if not isinstance(sc, dict):
            raise EngineError(404, "Cena não encontrada.")
        return sc

    def save_scene(self, pid: str, name: str, scene: Any, snapshot: bool = False) -> Dict[str, Any]:
        with self.lock:
            m = self.meta(pid)
            name = clean_rel(name) or "main"
            if "/" in name:
                raise EngineError(400, "O nome da cena não pode ter pasta.")
            try:
                sc = S.norm_scene(scene, m["kind"], name)
            except ValueError as exc:
                raise EngineError(400, str(exc)) from None
            if S.count_nodes(sc["root"]) > S.MAX_NODES:
                raise EngineError(400, "Cena grande demais.")
            write_json(self.dir(pid) / "game" / "scenes" / f"{name}.scene.json", sc)
            if not self.list_scenes(pid)[:1] or m.get("start") not in self.list_scenes(pid):
                m["start"] = name
            self._write_meta(pid, m)
            return sc

    def delete_scene(self, pid: str, name: str) -> None:
        with self.lock:
            p = self.dir(pid) / "game" / "scenes" / f"{clean_rel(name)}.scene.json"
            if not p.is_file():
                raise EngineError(404, "Cena não encontrada.")
            if len(self.list_scenes(pid)) <= 1:
                raise EngineError(400, "O jogo precisa de pelo menos uma cena.")
            p.unlink()
            m = self.meta(pid)
            if m.get("start") == name:
                m["start"] = self.list_scenes(pid)[0]
                self._write_meta(pid, m)

    def list_maps(self, pid: str) -> List[Dict[str, Any]]:
        d = self.dir(pid) / "game" / "maps"
        out = []
        for p in sorted(d.glob("*.map.json")) if d.is_dir() else []:
            m = read_json(p)
            if isinstance(m, dict):
                out.append({"path": f"maps/{p.name}", "name": m.get("name", p.stem), "kind": m.get("kind", "2d"), "theme": m.get("theme", ""), "objects": len(m.get("objects", [])), "size": [m.get("w"), m.get("h")] if m.get("kind") != "3d" else [m.get("res"), m.get("res")]})
        return out

    def get_map(self, pid: str, path: str) -> Dict[str, Any]:
        rel = clean_rel(path)
        if not rel.startswith("maps/") or not rel.endswith(".map.json"):
            raise EngineError(400, "Caminho de mapa inválido (use maps/nome.map.json).")
        m = read_json(self.dir(pid) / "game" / rel)
        if not isinstance(m, dict):
            raise EngineError(404, "Mapa não encontrado.")
        return m

    def save_map(self, pid: str, path: str, data: Any) -> Dict[str, Any]:
        with self.lock:
            rel = clean_rel(path)
            if not rel.startswith("maps/") or not rel.endswith(".map.json") or rel.count("/") != 1:
                raise EngineError(400, "Caminho de mapa inválido (use maps/nome.map.json).")
            try:
                m = S.norm_map(data)
            except (ValueError, TypeError) as exc:
                raise EngineError(400, str(exc)) from None
            write_json(self.dir(pid) / "game" / rel, m)
            self._touch(pid)
            return m

    def delete_map(self, pid: str, path: str) -> None:
        with self.lock:
            rel = clean_rel(path)
            if not rel.startswith("maps/") or not rel.endswith(".map.json"):
                raise EngineError(400, "Caminho de mapa inválido.")
            p = self.dir(pid) / "game" / rel
            if p.is_file():
                p.unlink()
                self._touch(pid)

    def _touch(self, pid: str) -> None:
        m = self.meta(pid)
        self._write_meta(pid, m)

    # ------------------------------------------------------------------ arquivos
    def area_dir(self, pid: str, area: str) -> Path:
        if area not in AREAS:
            raise EngineError(400, "Área inválida.")
        d = self.dir(pid) / area
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _target(self, pid: str, area: str, rel: str, must_exist: bool = False) -> Path:
        base = self.area_dir(pid, area).resolve()
        rel = clean_rel(rel)
        t = (base / rel).resolve() if rel else base
        if not _under(t, base):
            raise EngineError(400, "Caminho fora do projeto.")
        if must_exist and not t.exists():
            raise EngineError(404, "Arquivo não encontrado.")
        return t

    def tree(self, pid: str, area: str = "game") -> Dict[str, Any]:
        base = self.area_dir(pid, area).resolve()
        count = [0]

        def walk(p: Path, depth: int) -> List[Dict[str, Any]]:
            out = []
            try:
                items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
            except OSError:
                return out
            for it in items:
                if it.name.startswith(".") or it.is_symlink():
                    continue
                count[0] += 1
                if count[0] > MAX_ENTRIES:
                    break
                rel = it.relative_to(base).as_posix()
                if it.is_dir():
                    out.append({"name": it.name, "path": rel, "type": "dir", "children": walk(it, depth + 1) if depth < MAX_DEPTH else []})
                else:
                    out.append({"name": it.name, "path": rel, "type": "file", "size": it.stat().st_size, "ext": it.suffix.lower()})
            return out
        return {"area": area, "children": walk(base, 0), "truncated": count[0] > MAX_ENTRIES}

    def read_file(self, pid: str, area: str, rel: str) -> Dict[str, Any]:
        t = self._target(pid, area, rel, True)
        if not t.is_file():
            raise EngineError(400, "Isso é uma pasta.")
        ext = t.suffix.lower()
        size = t.stat().st_size
        if ext in TEXT_EXT or ext == "":
            if size > 4 * 1024 * 1024:
                return {"path": clean_rel(rel), "type": "big", "size": size, "ext": ext}
            data = t.read_bytes()
            try:
                return {"path": clean_rel(rel), "type": "text", "ext": ext, "size": size, "content": data.decode("utf-8")}
            except UnicodeDecodeError:
                return {"path": clean_rel(rel), "type": "binary", "ext": ext, "size": size}
        return {"path": clean_rel(rel), "type": "image" if ext in IMG_EXT else "audio" if ext in SND_EXT else "binary", "ext": ext, "size": size}

    def raw_path(self, pid: str, area: str, rel: str) -> Path:
        t = self._target(pid, area, rel, True)
        if not t.is_file():
            raise EngineError(404, "Arquivo não encontrado.")
        return t

    def project_size(self, pid: str) -> int:
        total = 0
        for area in ("game", "docs", "editor"):
            for p in (self.dir(pid) / area).rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
        return total

    def write_file(self, pid: str, area: str, rel: str, data: Any, overwrite: bool = True) -> Dict[str, Any]:
        """Grava texto ou bytes. Cenas e mapas passam pela validação; JSON comum só avisa se estiver quebrado."""
        with self.lock:
            rel = clean_rel(rel)
            if not rel:
                raise EngineError(400, "Informe o caminho do arquivo.")
            ext = Path(rel).suffix.lower()
            if ext not in TEXT_EXT and ext not in BIN_EXT:
                raise EngineError(400, f"Tipo de arquivo não permitido: «{ext or 'sem extensão'}».")
            t = self._target(pid, area, rel)
            if t.exists() and not overwrite:
                raise EngineError(409, "Já existe um arquivo com esse nome.")
            if t.is_dir():
                raise EngineError(400, "Já existe uma pasta com esse nome.")
            raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
            if len(raw) > MAX_FILE:
                raise EngineError(413, "Arquivo grande demais (máximo 64 MB).")
            if self.project_size(pid) + len(raw) > MAX_PROJECT:
                raise EngineError(413, "O projeto passou do limite de 1 GB.")
            warnings: List[str] = []
            if area == "game" and rel.startswith("scenes/") and rel.endswith(".scene.json"):
                try:
                    sc = S.norm_scene(json.loads(raw.decode("utf-8")), self.meta(pid)["kind"], Path(rel).name[: -len(".scene.json")])
                except (ValueError, UnicodeDecodeError) as exc:
                    raise EngineError(400, f"Cena inválida: {exc}") from None
                raw = json.dumps(sc, ensure_ascii=False, indent=2).encode("utf-8")
            elif area == "game" and rel.startswith("maps/") and rel.endswith(".map.json"):
                try:
                    mp = S.norm_map(json.loads(raw.decode("utf-8")))
                except (ValueError, UnicodeDecodeError, TypeError) as exc:
                    raise EngineError(400, f"Mapa inválido: {exc}") from None
                raw = json.dumps(mp, ensure_ascii=False).encode("utf-8")
            elif ext == ".json":
                try:
                    json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    warnings.append(f"JSON com erro: {exc}")
            elif ext == ".png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                raise EngineError(400, "O arquivo não é um PNG de verdade.")
            elif ext in (".jpg", ".jpeg") and not raw.startswith(b"\xff\xd8\xff"):
                raise EngineError(400, "O arquivo não é um JPEG de verdade.")
            elif ext == ".wav" and not (raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"):
                raise EngineError(400, "O arquivo não é um WAV de verdade.")
            elif ext == ".svg":
                low = raw[:200000].decode("utf-8", "ignore").lower()
                if "<svg" not in low:
                    raise EngineError(400, "O arquivo não é um SVG.")
            t.parent.mkdir(parents=True, exist_ok=True)
            tmp = t.with_name(t.name + ".tmp")
            tmp.write_bytes(raw)
            os.replace(tmp, t)
            self._touch(pid)
            return {"path": rel, "size": len(raw), "warnings": warnings}

    def mkdir(self, pid: str, area: str, rel: str) -> Dict[str, Any]:
        with self.lock:
            rel = clean_rel(rel)
            if not rel:
                raise EngineError(400, "Informe o nome da pasta.")
            t = self._target(pid, area, rel)
            if t.exists():
                raise EngineError(409, "Já existe algo com esse nome.")
            t.mkdir(parents=True)
            return {"path": rel}

    def rename(self, pid: str, area: str, rel: str, new_rel: str) -> Dict[str, Any]:
        """Renomeia/move um arquivo ou pasta (dentro da mesma área)."""
        with self.lock:
            src = self._target(pid, area, rel, True)
            dst = self._target(pid, area, new_rel)
            if not clean_rel(rel) or not clean_rel(new_rel):
                raise EngineError(400, "Caminho inválido.")
            if dst.exists():
                raise EngineError(409, "Já existe algo com esse nome.")
            if src.is_dir() and _under(dst, src.resolve()):
                raise EngineError(400, "Não dá para mover uma pasta para dentro dela mesma.")
            if src.is_file() and src.suffix.lower() != Path(new_rel).suffix.lower() and src.suffix.lower() in (".png", ".wav", ".json", ".svg", ".js"):
                raise EngineError(400, "Não troque a extensão do arquivo.")
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
            self._touch(pid)
            return {"path": clean_rel(new_rel)}

    def delete_path(self, pid: str, area: str, rel: str) -> None:
        with self.lock:
            rel = clean_rel(rel)
            if not rel:
                raise EngineError(400, "Não dá para apagar a pasta raiz.")
            if area == "game" and rel in ("scenes", "maps", "scripts", "assets", "data"):
                raise EngineError(400, "Esta pasta é do motor; apague os arquivos de dentro.")
            t = self._target(pid, area, rel, True)
            if t.is_dir():
                shutil.rmtree(t)
            else:
                t.unlink()
            self._touch(pid)

    def import_zip(self, pid: str, area: str, data: bytes, into: str = "") -> Dict[str, Any]:
        """Extrai um .zip para dentro do projeto com as proteções de sempre (zip-slip, tamanho, tipos permitidos)."""
        written, skipped = 0, 0
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise EngineError(400, "ZIP inválido.") from None
        infos = [i for i in zf.infolist() if not i.is_dir()][:3000]
        if sum(i.file_size for i in infos) > MAX_PROJECT // 2:
            raise EngineError(413, "O ZIP descompactado é grande demais.")
        prefix = ""
        names = [i.filename for i in infos]
        if names and all(n.split("/")[0] == names[0].split("/")[0] and "/" in n for n in names):
            prefix = names[0].split("/")[0] + "/"
        for i in infos:
            name = i.filename[len(prefix):] if prefix and i.filename.startswith(prefix) else i.filename
            try:
                rel = clean_rel((into + "/" if into else "") + name)
                ext = Path(rel).suffix.lower()
                if not rel or ext not in TEXT_EXT | BIN_EXT or i.file_size > MAX_FILE:
                    raise EngineError(400, "x")
                self.write_file(pid, area, rel, zf.read(i))
                written += 1
            except EngineError:
                skipped += 1
        return {"written": written, "skipped": skipped}

    # ------------------------------------------------------------------ histórico (desfazer)
    def snapshot(self, pid: str, label: str = "") -> Optional[str]:
        with self.lock:
            d = self.dir(pid)
            hist = d / "history"
            hist.mkdir(exist_ok=True)
            sid = time.strftime("%Y%m%d-%H%M%S") + "-" + new_id()[:3]
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for area in ("game", "docs"):
                    for p in (d / area).rglob("*"):
                        if p.is_file() and p.stat().st_size < 24 * 1024 * 1024:
                            zf.write(p, p.relative_to(d).as_posix())
                zf.write(d / "project.json", "project.json")
                zf.writestr("snapshot.json", json.dumps({"id": sid, "label": text(label, "", 200), "t": now_iso()}))
            (hist / f"{sid}.zip").write_bytes(buf.getvalue())
            for old in sorted(hist.glob("*.zip"))[:-25]:
                old.unlink()
            return sid

    def history(self, pid: str) -> List[Dict[str, Any]]:
        out = []
        for p in sorted((self.dir(pid) / "history").glob("*.zip"), reverse=True):
            try:
                with zipfile.ZipFile(p) as zf:
                    info = json.loads(zf.read("snapshot.json").decode("utf-8"))
                out.append({"id": p.stem, "label": info.get("label", ""), "t": info.get("t", ""), "size": p.stat().st_size})
            except (OSError, KeyError, ValueError, zipfile.BadZipFile):
                continue
        return out

    def restore(self, pid: str, sid: str) -> None:
        with self.lock:
            d = self.dir(pid)
            p = d / "history" / f"{clean_rel(sid)}.zip"
            if not p.is_file():
                raise EngineError(404, "Instantâneo não encontrado.")
            self.snapshot(pid, "antes de desfazer")
            with zipfile.ZipFile(p) as zf:
                for area in ("game", "docs"):
                    shutil.rmtree(d / area, ignore_errors=True)
                for info in zf.infolist():
                    if info.is_dir() or info.filename in ("snapshot.json",):
                        continue
                    target = (d / info.filename).resolve()
                    if not _under(target, d.resolve()):
                        continue
                    if info.filename == "project.json":
                        old = self.meta(pid)
                        saved = json.loads(zf.read(info).decode("utf-8"))
                        saved["log"] = old.get("log", [])
                        write_json(d / "project.json", saved)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(info))
            for sub in ("game/scenes", "game/maps", "game/scripts", "game/assets/images", "game/assets/sound", "game/data", "docs"):
                (d / sub).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ gravar o resultado de um gerador
    def apply_build(self, pid: str, build: Dict[str, Any], replace: bool = True) -> Dict[str, Any]:
        """Escreve o jogo gerado (cenas, mapas, diálogos, imagens, sons, documentos). `replace`: apaga cenas/mapas anteriores."""
        with self.lock:
            d = self.dir(pid)
            m = self.meta(pid)
            if replace:
                for sub in ("scenes", "maps"):
                    for p in (d / "game" / sub).glob("*.json"):
                        p.unlink()
            for name, sc in (build.get("scenes") or {}).items():
                self.save_scene(pid, name, sc)
            for path, mp in (build.get("maps") or {}).items():
                self.save_map(pid, path, mp)
            for key, svg in (build.get("images") or {}).items():
                self.write_file(pid, "game", f"assets/images/{safe_filename(key)}.svg", svg)
            for key, wav in (build.get("sounds") or {}).items():
                self.write_file(pid, "game", f"assets/sound/{safe_filename(key)}.wav", wav)
            if build.get("dialogues") is not None:
                self.write_file(pid, "game", "data/dialogues.json", json.dumps(build["dialogues"], ensure_ascii=False, indent=2))
            for name, body in (build.get("docs") or {}).items():
                self.write_file(pid, "docs", safe_filename(name), body)
            m = self.meta(pid)
            for k, v in (build.get("meta") or {}).items():
                if k in ("name", "kind", "genre", "theme", "language", "description", "seed", "length"):
                    m[k] = v
            if build.get("settings"):
                m["settings"] = S.norm_project_settings(dict(m.get("settings") or {}, **build["settings"]), m["kind"])
            names = self.list_scenes(pid)
            m["start"] = m.get("start") if m.get("start") in names else (names[0] if names else "main")
            m["version"] = int(m.get("version", 1)) + 1
            self._write_meta(pid, m)
            return m

    # ------------------------------------------------------------------ pacote jogável
    def _asset_urls(self, d: Path, sub: str, exts: set, base: str, bust: bool = False) -> Dict[str, str]:
        out: Dict[str, str] = {}
        root = d / "game" / sub
        if root.is_dir():
            for p in sorted(root.rglob("*")):
                if p.is_file() and p.suffix.lower() in exts and not p.name.startswith("."):
                    rel = p.relative_to(d / "game").as_posix()
                    out[p.stem] = base + "game/" + rel + (f"?v={int(p.stat().st_mtime)}" if bust else "")
        return out

    def bundle(self, pid: str, base: str = "", bust: bool = False) -> Dict[str, Any]:
        """Tudo o que o motor lê (`window.GE_DATA`): configurações, cenas, mapas, diálogos e a lista de imagens e sons."""
        d = self.dir(pid)
        m = self.meta(pid)
        scenes = {}
        for n in self.list_scenes(pid):
            sc = read_json(d / "game" / "scenes" / f"{n}.scene.json")
            if isinstance(sc, dict):
                scenes[n] = sc
        maps_ = {}
        for p in sorted((d / "game" / "maps").glob("*.map.json")):
            mp = read_json(p)
            if isinstance(mp, dict):
                maps_[f"maps/{p.name}"] = mp
        dlg = read_json(d / "game" / "data" / "dialogues.json", {})
        return {"project": {"id": pid, "name": m.get("name", ""), "kind": m.get("kind", "2d"), "genre": m.get("genre", ""), "theme": m.get("theme", ""), "language": m.get("language", "pt"), "description": m.get("description", ""),
                            "settings": m.get("settings", {}), "audio": (m.get("settings") or {}).get("audio", {}), "hp": (m.get("settings") or {}).get("hp", 3), "engine": __version__},
                "start": m.get("start", "main"), "scenes": scenes, "maps": maps_, "dialogues": dlg if isinstance(dlg, dict) else {},
                "assets": {"images": self._asset_urls(d, "assets/images", IMG_EXT, base, bust), "sounds": self._asset_urls(d, "assets/sound", SND_EXT, base, bust)}}

    def data_js(self, pid: str, base: str = "", bust: bool = False) -> str:
        raw = json.dumps(self.bundle(pid, base, bust), ensure_ascii=False, separators=(",", ":"))
        raw = raw.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        return "window.GE_DATA=" + raw + ";\n"

    def user_scripts(self, pid: str) -> List[str]:
        d = self.dir(pid) / "game" / "scripts"
        return [p.relative_to(self.dir(pid) / "game").as_posix() for p in sorted(d.rglob("*.js")) if p.is_file()] if d.is_dir() else []

    def index_html(self, pid: str, base: str = "", edit: bool = False, standalone: bool = False, autostart: bool = False) -> str:
        """A página do jogo. `base`: prefixo das URLs («» = relativas, como no pacote exportado)."""
        m = self.meta(pid)
        tpl = (RUNTIME / "game.html").read_text("utf-8")
        lang = m.get("language", "pt")
        kind = m.get("kind", "2d")
        dim3 = S.KINDS.get(kind, S.KINDS["2d"])["dim"] == "3d"
        scripts = []
        if dim3:
            scripts.append(f'<script src="{base}vendor/three.min.js"></script>')
        scripts += [f'<script src="{base}data.js"></script>', f'<script src="{base}engine/ge_core.js"></script>']
        scripts.append(f'<script src="{base}engine/ge_3d.js"></script>' if dim3 else f'<script src="{base}engine/ge_2d.js"></script>')
        if edit:
            scripts.append(f'<script src="{base}engine/ge_edit.js"></script>')
        for s in self.user_scripts(pid):
            scripts.append(f'<script src="{base}game/{html.escape(s)}"></script>')
        head = '<script>window.GE_EDIT=true;</script>' if edit else ""
        brand = "ASTA"
        help_ = {"pt": {"2d": "Setas/WASD · Espaço · E", "2.5d": "Setas/WASD · Espaço · E", "3d": "WASD · mouse · Espaço · E", "vr": "VR: botão «Entrar em VR» (ou WASD + mouse)", "ar": "AR: botão «Entrar em AR» (ou WASD + mouse)"},
                 "en": {"2d": "Arrows/WASD · Space · E", "2.5d": "Arrows/WASD · Space · E", "3d": "WASD · mouse · Space · E", "vr": "VR: «Enter VR» button (or WASD + mouse)", "ar": "AR: «Enter AR» button (or WASD + mouse)"}}[lang if lang in ("pt", "en") else "pt"].get(kind, "")
        out = (tpl.replace("{{LANG}}", "pt-BR" if lang == "pt" else "en").replace("{{TITLE}}", html.escape(m.get("name", "Jogo"))).replace("{{DESC}}", html.escape(m.get("description", "")[:200])).replace("{{HEAD}}", head)
               .replace("{{BASE}}", base).replace("{{BRAND}}", brand).replace("{{HELP}}", html.escape(help_)).replace("{{SCRIPTS}}", "\n".join(scripts)).replace("{{AUTOSTART}}", "true" if autostart or edit else "false"))
        return out

    def play_file(self, pid: str, rel: str) -> Tuple[str, Any]:
        """O que servir em /api/engine/play/<id>/<rel>: ('text', str, mime) | ('file', Path)."""
        rel = rel.strip("/") or "index.html"
        base = ""
        if rel in ("index.html", "edit.html"):
            return "text", (self.index_html(pid, base, edit=(rel == "edit.html")), "text/html; charset=utf-8")
        if rel == "data.js":
            return "text", (self.data_js(pid, base, bust=True), "text/javascript; charset=utf-8")
        if rel.startswith("engine/"):
            name = rel[len("engine/"):]
            if name in ENGINE_FILES + EDIT_FILES:
                return "file", RUNTIME / name
            raise EngineError(404, "Arquivo não encontrado.")
        if rel == "vendor/three.min.js":
            return "file", THREE
        if rel.startswith("game/"):
            clean = clean_rel(rel[len("game/"):])
            t = self._target(pid, "game", clean, True)
            if not t.is_file():
                raise EngineError(404, "Arquivo não encontrado.")
            return "file", t
        raise EngineError(404, "Arquivo não encontrado.")
