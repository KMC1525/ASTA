"""Persistência dos projetos do Studio.

    studio/<id>/project.json      o documento (metadados, cenas, ativos, timelines dos episódios)
    studio/<id>/media/<arquivo>   ativos (gerados ou enviados)
    studio/<id>/exports/<arquivo> exportações (completo, só vídeo, só áudio)
"""
from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..util import new_id, now_iso, read_json, write_json
from . import schema as S
from . import tools

_ID_RE = re.compile(r"^[\w-]+$")
_FILE_RE = re.compile(r"^[\w][\w.-]*$")
MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif", "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov",
            "audio/wav": "wav", "audio/mpeg": "mp3", "audio/ogg": "ogg", "audio/flac": "flac", "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac", "audio/webm": "weba"}


class StudioStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    # ---- caminhos
    def _dir(self, pid: str) -> Optional[Path]:
        return self.folder / pid if pid and _ID_RE.match(pid) and ".." not in pid else None

    def media_dir(self, pid: str) -> Path:
        d = self._dir(pid)
        if not d:
            raise ValueError("projeto inválido")
        (d / "media").mkdir(parents=True, exist_ok=True)
        return d / "media"

    def export_dir(self, pid: str) -> Path:
        d = self._dir(pid)
        if not d:
            raise ValueError("projeto inválido")
        (d / "exports").mkdir(parents=True, exist_ok=True)
        return d / "exports"

    def _file(self, pid: str, sub: str, fname: str) -> Optional[Path]:
        d = self._dir(pid)
        if not d or not _FILE_RE.match(fname or "") or ".." in fname:
            return None
        p = d / sub / fname
        return p if p.is_file() else None

    def media_path(self, pid: str, fname: str) -> Optional[Path]:
        return self._file(pid, "media", fname)

    def thumb(self, pid: str, aid: str) -> Optional[Path]:
        """Miniatura (JPEG) de um ativo de vídeo/imagem, criada na primeira vez e guardada em studio/<id>/thumbs."""
        d = self._dir(pid)
        p = self.get(pid)
        a = self.asset(p, aid) if p else None
        if not d or not a or a["kind"] == "audio" or not re.match(r"^[\w-]+$", aid or ""):
            return None
        out = d / "thumbs" / f"{aid}.jpg"
        if out.is_file():
            return out
        src = self.media_path(pid, a["file"])
        if not src:
            return None
        data = tools.thumbnail(src, min(0.5, max(0.0, a["dur"] / 2)), 240)
        if not data:
            return None
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return out

    def export_path(self, pid: str, fname: str) -> Optional[Path]:
        return self._file(pid, "exports", fname)

    # ---- documentos
    def get(self, pid: str) -> Optional[Dict[str, Any]]:
        d = self._dir(pid)
        data = read_json(d / "project.json") if d else None
        return S.normalize_project(data, keep_id=pid) if isinstance(data, dict) else None

    def _write(self, p: Dict[str, Any]) -> Dict[str, Any]:
        p["updated"] = now_iso()
        write_json(self.folder / p["id"] / "project.json", p)
        return p

    def update(self, pid: str, fn: Callable[[Dict[str, Any]], Any]) -> Optional[Dict[str, Any]]:
        """Lê → `fn(projeto)` altera → normaliza e grava, tudo sob a trava (jobs e navegador não se atropelam)."""
        with self.lock:
            p = self.get(pid)
            if not p:
                return None
            fn(p)
            p = S.normalize_project(p, keep_id=pid)
            return self._write(p)

    def summary(self, p: Dict[str, Any]) -> Dict[str, Any]:
        eps = p["episodes"]
        thumb = next((f"/api/studio/projects/{p['id']}/media/{a['file']}" for a in p["assets"] if a["kind"] == "image"), "")
        return {"id": p["id"], "name": p["name"], "kind": p["kind"], "duration_type": p["duration_type"], "target_seconds": p["target_seconds"], "style": p["style"], "aspect": p["aspect"],
                "episodes": len(eps), "scenes": sum(len(e["scenes"]) for e in eps), "duration": round(sum(e["timeline"]["duration"] for e in eps), 1), "created": p["created"], "updated": p["updated"], "thumb": thumb,
                "origin": eps[0]["origin"] if eps else "generated"}

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for d in self.folder.iterdir():
            p = self.get(d.name) if d.is_dir() else None
            if p:
                out.append(self.summary(p))
        out.sort(key=lambda x: x.get("updated", ""), reverse=True)
        return out

    def create(self, body: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            pid = new_id("st_")
            (self.folder / pid / "media").mkdir(parents=True, exist_ok=True)
            p = S.normalize_project({**body, "id": pid}, keep_id=pid)
            if not p["episodes"]:
                manual = p["origin"] == "manual"   # projeto para editar na mão: o episódio já nasce «pronto» e vazio, sem roteiro nem geração
                p["episodes"] = [S.normalize_episode({"title": p["name"], "prompt": body.get("prompt", ""), "target": p["target_seconds"], **({"status": "ready", "origin": "manual"} if manual else {})}, 0)]
            p["created"] = now_iso()
            return self._write(p)

    def delete(self, pid: str) -> bool:
        d = self._dir(pid)
        if not d or not d.exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True

    # ---- ativos
    def add_asset(self, pid: str, data: bytes, ext: str, kind: str, *, name: str = "", mime: str = "", source: str = "upload", scene: str = "", prompt: str = "") -> Optional[Dict[str, Any]]:
        if kind not in ("image", "video", "audio") or not self._dir(pid):
            return None
        aid = new_id("a_")
        fname = f"{aid}.{ext}"
        path = self.media_dir(pid) / fname
        path.write_bytes(data)
        info = tools.probe(path) if kind != "image" else {"dur": 0, "w": 0, "h": 0, "audio": False}
        if kind == "image":
            try:
                from ..attachments import image_size

                wh = image_size(data)
                if wh:
                    info["w"], info["h"] = wh
            except Exception:  # noqa: BLE001
                pass
        rec = {"id": aid, "file": fname, "kind": kind, "name": name or fname, "mime": mime, "dur": round(float(info.get("dur") or 0), 3), "w": info.get("w", 0), "h": info.get("h", 0),
               "audio": bool(info.get("audio")), "source": source, "scene": scene, "prompt": prompt, "created": now_iso()}
        if self.update(pid, lambda p: p["assets"].append(rec)) is None:
            path.unlink(missing_ok=True)
            return None
        return rec

    def add_asset_file(self, pid: str, src: Path, ext: str, kind: str, *, name: str = "", mime: str = "", source: str = "upload") -> Optional[Dict[str, Any]]:
        """Como `add_asset`, mas copia de um arquivo em disco (vídeos grandes não passam pela memória)."""
        if kind not in ("image", "video", "audio") or not self._dir(pid):
            return None
        aid = new_id("a_")
        fname = f"{aid}.{re.sub(r'[^a-z0-9]', '', ext.lower())[:5] or 'bin'}"
        path = self.media_dir(pid) / fname
        shutil.copyfile(src, path)
        info = tools.probe(path) if kind != "image" else {"dur": 0, "w": 0, "h": 0, "audio": False}
        if kind == "image":
            try:
                from ..attachments import image_size

                wh = image_size(path.read_bytes())
                if wh:
                    info["w"], info["h"] = wh
            except Exception:  # noqa: BLE001
                pass
        rec = {"id": aid, "file": fname, "kind": kind, "name": name or fname, "mime": mime, "dur": round(float(info.get("dur") or 0), 3), "w": info.get("w", 0), "h": info.get("h", 0),
               "audio": bool(info.get("audio")), "source": source, "scene": "", "prompt": "", "created": now_iso()}
        if self.update(pid, lambda p: p["assets"].append(rec)) is None:
            path.unlink(missing_ok=True)
            return None
        return rec

    def delete_asset(self, pid: str, aid: str) -> bool:
        found: List[Dict[str, Any]] = []

        def fn(p: Dict[str, Any]) -> None:
            found.extend(a for a in p["assets"] if a["id"] == aid)
            p["assets"] = [a for a in p["assets"] if a["id"] != aid]
            for e in p["episodes"]:
                e["timeline"]["clips"] = [c for c in e["timeline"]["clips"] if c["asset"] != aid]

        if self.update(pid, fn) is None or not found:
            return False
        path = self.media_path(pid, found[0]["file"])
        if path:
            path.unlink(missing_ok=True)
        return True

    def asset(self, p: Dict[str, Any], aid: str) -> Optional[Dict[str, Any]]:
        return next((a for a in p["assets"] if a["id"] == aid), None)
