"""Web scraping do modo Data: leitura de páginas e respeito ao robots.txt.

Aviso do modo: **somente uso open source, não usar para uso comercial**. Aqui isso não é
só um aviso na tela: o scraping lê o ``robots.txt`` de cada site e não baixa o que o
site proíbe. O resto das regras (termos de uso, licença dos dados) é do usuário.

Redes privadas, localhost e endereços especiais são recusados (`websearch.safe_url`).
"""

from __future__ import annotations

import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from pathlib import Path

from .. import websearch
from . import links

USER_AGENT = "ASTA-Data/1.0 (+https://github.com/asta; open-source, non-commercial use)"

#: robots.txt por origem (host), guardado em memória durante o trabalho
_ROBOTS: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}


def robots_for(url: str) -> Optional[urllib.robotparser.RobotFileParser]:
    """O parser do robots.txt da origem do link (None se o site não tem robots.txt)."""
    sp = urllib.parse.urlsplit(url)
    if not sp.hostname:
        return None
    if not websearch.safe_url(url):
        return None   # endereços privados/locais: nada de buscar robots.txt (e nada de baixar)
    origin = f"{sp.scheme}://{sp.netloc}"
    if origin in _ROBOTS:
        return _ROBOTS[origin]
    parser: Optional[urllib.robotparser.RobotFileParser] = None
    try:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(origin + "/robots.txt")
        req = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=6) as resp:
            raw = resp.read(200000).decode("utf-8", errors="replace")
        parser.parse(raw.splitlines())
    except Exception:
        # sem robots.txt (404) ou erro de rede: o site não definiu regras → nada a bloquear.
        # um robots.txt ilegível também não bloqueia, mas fica registrado como «sem regras».
        parser = None
    _ROBOTS[origin] = parser
    return parser


def allowed(url: str) -> bool:
    """O robots.txt desta origem permite baixar este link? (sem robots.txt → permite)"""
    if not websearch.safe_url(url):
        return False
    parser = robots_for(url)
    if parser is None:
        return True
    try:
        return bool(parser.can_fetch(USER_AGENT, url))
    except Exception:
        return True


def fetch(url: str, limit: int = 12000, download_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Lê um link de **qualquer tipo** (v0.24: HTML, JSON, CSV, XML, texto, imagem, áudio, vídeo, PDF…): `{url, kind, title, text, rows, error, skipped, …}` (ver `links.read`).
    Com `download_dir`, mídia/arquivos pequenos são guardados lá e o achado ganha `file`."""
    if not websearch.safe_url(url):
        return {"url": url, "kind": "", "title": "", "text": "", "rows": [], "error": "URL não permitida (apenas http/https públicos)."}
    if not allowed(url):
        return {"url": url, "kind": "", "title": "", "text": "", "rows": [], "error": "robots.txt do site não permite este link.", "skipped": True}
    page = links.read(url, limit, download_dir)
    if page.get("error") and not page.get("kind"):
        return page
    if download_dir is not None:
        page["file"] = links.save_download(page, Path(download_dir))
    page.pop("file_bytes", None)
    page["text"] = (page.get("text") or "")[:limit]
    return page


def fetch_many(urls: List[str], on_page: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
               workers: int = 6, limit: int = 12000, download_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Lê muitos links em paralelo (scraping em massa). `on_page(i, total, page)` avança o progresso."""
    total = len(urls)
    out: List[Optional[Dict[str, Any]]] = [None] * total

    def one(i: int) -> None:
        try:
            out[i] = fetch(urls[i], limit) if download_dir is None else fetch(urls[i], limit, download_dir)
        except Exception as exc:  # noqa: BLE001  (um link quebrado não derruba o lote)
            out[i] = {"url": urls[i], "kind": "", "title": "", "text": "", "rows": [], "error": str(exc)[:200]}
        if on_page:
            try:
                on_page(i + 1, total, out[i] or {})
            except Exception:
                pass

    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, total))) as ex:
        list(ex.map(one, range(total)))
    return [p for p in out if p is not None]


def reset_cache() -> None:
    """Limpa o cache de robots.txt (usado nos testes)."""
    _ROBOTS.clear()
