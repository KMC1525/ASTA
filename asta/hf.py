"""Busca e download de modelos GGUF no Hugging Face (sem dependências externas)."""
from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .providers import http
from .providers.base import ProviderError

HF = "https://huggingface.co"
REPO_RE = re.compile(r"^[A-Za-z0-9][\w.-]{0,95}/[A-Za-z0-9][\w.-]{0,95}$")
FILE_RE = re.compile(r"^[\w][\w .+()=-]{0,200}\.gguf$")


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def search(query: str, token: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    params = {"search": query, "filter": "gguf", "sort": "downloads", "direction": "-1", "limit": str(limit)}
    data = http.get_json(f"{HF}/api/models?{urllib.parse.urlencode(params)}", _headers(token), timeout=20)
    return [
        {"id": m.get("id") or m.get("modelId"), "downloads": m.get("downloads", 0), "likes": m.get("likes", 0)}
        for m in data if isinstance(m, dict)
    ]


def list_files(repo: str, token: str = "") -> List[Dict[str, Any]]:
    if not REPO_RE.match(repo or ""):
        raise ProviderError("Repositório inválido (use o formato dono/nome).")
    data = http.get_json(f"{HF}/api/models/{repo}/tree/main?recursive=1", _headers(token), timeout=20)
    files = []
    for it in data:
        path = it.get("path", "")
        if it.get("type") == "file" and path.lower().endswith(".gguf"):
            size = (it.get("lfs") or {}).get("size") or it.get("size") or 0
            files.append({"name": path, "size": size})
    files.sort(key=lambda f: f["size"])
    return files


def local_models(models_dir: Path) -> List[Dict[str, Any]]:
    out = []
    for p in sorted(models_dir.glob("*.gguf")):
        out.append({"name": p.name, "size": p.stat().st_size})
    return out


def download(
    repo: str, filename: str, models_dir: Path, token: str = "",
    progress: Optional[Callable[[int, int], None]] = None, cancelled: Callable[[], bool] = lambda: False,
) -> Path:
    if not REPO_RE.match(repo or "") or not FILE_RE.match(Path(filename).name) or ".." in filename:
        raise ProviderError("Repositório ou arquivo inválido.")
    dest = models_dir / Path(filename).name
    part = dest.with_suffix(dest.suffix + ".part")
    start = part.stat().st_size if part.exists() else 0
    headers = _headers(token)
    if start:
        headers["Range"] = f"bytes={start}-"
    url = f"{HF}/{repo}/resolve/main/{urllib.parse.quote(filename)}"
    resp = http.request(url, headers=headers, timeout=60)
    try:
        total = int(resp.headers.get("Content-Length") or 0)
        if resp.status == 206:
            total += start
        else:
            start = 0  # servidor ignorou o Range
        mode = "ab" if start else "wb"
        done = start
        with open(part, mode) as fh:
            while True:
                if cancelled():
                    raise ProviderError("cancelado")
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    finally:
        resp.close()
    os.replace(part, dest)
    return dest
