"""Leitura de **qualquer tipo de link** para o web scraping do Data (v0.24): páginas HTML, JSON, CSV/TSV, XML/RSS, texto, e arquivos de mídia (imagem, áudio, vídeo, PDF…).

Cada link vira um *achado* com `kind` (html · json · csv · xml · text · image · audio · video · pdf · file), tipo de conteúdo, tamanho e — para o que tem texto — o texto
ou as linhas já estruturadas (`rows`: JSON/CSV viram registros sem precisar de IA). Arquivos binários só têm seus metadados lidos; baixar o arquivo para dentro do item é
opcional (`download_dir`) e limitado. Mesmas barreiras do resto do ASTA: só http/https de host público (inclusive nos redirecionamentos), tamanho máximo, conteúdo tratado como
dado, nunca executado. O `robots.txt` é checado por quem chama (`scrape.allowed`).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import websearch
from . import formats

MAX_TEXT_BYTES = 2 * 1024 * 1024        # o que se lê de um link de texto
MAX_DOWNLOAD = 20 * 1024 * 1024         # arquivo de mídia guardado no item
MAX_ROWS = 5000
KINDS = ("html", "json", "csv", "xml", "text", "image", "audio", "video", "pdf", "file")
_EXT = {".json": "json", ".csv": "csv", ".tsv": "csv", ".xml": "xml", ".rss": "xml", ".atom": "xml", ".txt": "text", ".md": "text", ".html": "html", ".htm": "html", ".pdf": "pdf",
        ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".webp": "image", ".svg": "image", ".avif": "image", ".bmp": "image",
        ".mp3": "audio", ".wav": "audio", ".ogg": "audio", ".m4a": "audio", ".flac": "audio", ".opus": "audio",
        ".mp4": "video", ".webm": "video", ".mov": "video", ".mkv": "video", ".m4v": "video"}
_HEADERS = {"User-Agent": "ASTA-Data/1.0 (open-source, non-commercial use)", "Accept": "text/html,application/json,text/csv,*/*;q=0.5"}


def kind_of(content_type: str, url: str) -> str:
    """O tipo do link pelo `Content-Type` (que manda) e, na falta dele, pela extensão."""
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("audio/"):
        return "audio"
    if ct.startswith("video/"):
        return "video"
    if ct == "application/pdf":
        return "pdf"
    if "json" in ct:
        return "json"
    if ct in ("text/csv", "text/tab-separated-values", "application/csv"):
        return "csv"
    if "xml" in ct and "html" not in ct:
        return "xml"
    if "html" in ct:
        return "html"
    if ct.startswith("text/"):
        return "text"
    ext = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if ext in _EXT and (not ct or ct in ("application/octet-stream", "binary/octet-stream")):
        return _EXT[ext]
    return "file" if ct else _EXT.get(ext, "html")


def _filename(url: str) -> str:
    name = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
    return re.sub(r"[^\w.\- ]+", "_", name)[:100]


def _rows_from_json(obj: Any) -> List[Dict[str, Any]]:
    if isinstance(obj, list):
        items = obj
    elif isinstance(obj, dict):
        items = next((v for v in obj.values() if isinstance(v, list) and v and isinstance(v[0], dict)), None)
        if items is None:
            return [obj]
    else:
        return []
    return [r if isinstance(r, dict) else {"value": r} for r in items[:MAX_ROWS]]


def _rows_from_csv(text: str) -> List[Dict[str, Any]]:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rd = csv.DictReader(io.StringIO(text), dialect=dialect)
    out: List[Dict[str, Any]] = []
    for row in rd:
        out.append({str(k): v for k, v in row.items() if k is not None})
        if len(out) >= MAX_ROWS:
            break
    return out


def read(url: str, limit: int = 12000, download_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Lê um link. Devolve `{url, kind, content_type, size, title, text, rows, filename, file, error}` (campos vazios quando não se aplicam)."""
    out: Dict[str, Any] = {"url": url, "kind": "", "content_type": "", "size": 0, "title": "", "text": "", "rows": [], "filename": _filename(url), "file": "", "error": ""}
    if not websearch.safe_url(url):
        out["error"] = "URL não permitida (apenas http/https públicos)."
        return out
    try:
        with websearch._OPENER.open(urllib.request.Request(url, headers=_HEADERS), timeout=12) as resp:
            ctype = resp.headers.get("Content-Type", "")
            try:
                size = int(resp.headers.get("Content-Length") or 0)
            except ValueError:
                size = 0
            kind = kind_of(ctype, url)
            out.update(kind=kind, content_type=ctype.split(";", 1)[0].strip().lower(), size=size)
            textual = kind in ("html", "json", "csv", "xml", "text")
            if textual:
                data = resp.read(MAX_TEXT_BYTES)
                out["size"] = out["size"] or len(data)
            elif download_dir is not None and (not size or size <= MAX_DOWNLOAD):
                data = resp.read(MAX_DOWNLOAD + 1)
                out["size"] = len(data)
                if len(data) > MAX_DOWNLOAD:
                    out["error"] = "Arquivo grande demais para guardar (máx. 20 MB); só os metadados foram lidos."
                    data = b""
                else:
                    out["file_bytes"] = data
            else:
                data = b""
    except (urllib.error.URLError, OSError, ValueError) as exc:
        out["error"] = f"Não foi possível ler o link: {str(exc)[:120]}"
        return out
    kind = out["kind"]
    if kind in ("html", "json", "csv", "xml", "text"):
        txt = websearch._decode(data, ctype)
        if kind == "html":
            page = websearch.html_to_text(txt, limit)
            out["title"], out["text"] = page.get("title", ""), page.get("text", "")
        elif kind == "json":
            try:
                obj = json.loads(txt)
                out["rows"] = _rows_from_json(obj)
                out["text"] = json.dumps(obj, ensure_ascii=False)[:limit]
            except ValueError:
                out["kind"], out["text"] = "text", txt[:limit]
        elif kind == "csv":
            out["rows"] = _rows_from_csv(txt)
            out["text"] = txt[:limit]
        elif kind == "xml":
            try:
                root = formats.safe_xml(data)
                out["text"] = " ".join(" ".join(root.itertext()).split())[:limit]
                out["title"] = (root.findtext(".//title") or "")[:200]
            except formats.FormatError:
                out["text"] = ""
                out["error"] = "XML recusado (DOCTYPE/ENTITY ou inválido)."
        else:
            out["text"] = txt[:limit]
    return out


def save_download(page: Dict[str, Any], media_dir: Path) -> str:
    """Guarda o arquivo baixado (se houver) em `media_dir` com nome seguro e único; devolve o nome relativo (`attachments/…`) ou ''. Remove os bytes do achado."""
    raw = page.pop("file_bytes", b"")
    if not raw:
        return ""
    media_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(page.get("filename") or "arquivo").stem[:60] or "arquivo"
    ext = Path(page.get("filename") or "").suffix.lower()[:8]
    name = f"{stem}-{hashlib.sha1(page['url'].encode()).hexdigest()[:8]}{ext}"
    (media_dir / name).write_bytes(raw)
    return "attachments/" + name


def record_for(page: Dict[str, Any]) -> Dict[str, Any]:
    """O registro que descreve o link sem precisar de IA (usado para mídia/arquivos e como reserva quando a extração falha)."""
    rec: Dict[str, Any] = {"url": page["url"], "type": page.get("kind") or "file", "content_type": page.get("content_type", ""), "size": page.get("size", 0)}
    if page.get("title"):
        rec["title"] = page["title"]
    if page.get("filename"):
        rec["filename"] = page["filename"]
    if page.get("file"):
        rec["file"] = page["file"]
    if page.get("text") and page.get("kind") in ("html", "text", "xml"):
        rec["content"] = page["text"][:4000]
    return rec
