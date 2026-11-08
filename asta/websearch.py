"""Busca na web nativa do ASTA — funciona com **qualquer** modelo (nuvem ou local) e em qualquer prompt do Chat ou de uma ferramenta de criação.

Só biblioteca padrão. Motores (`chat.web.engine`):
  • `auto` (padrão, sem chave): DuckDuckGo; se falhar ou vier vazio, Wikipédia.
  • `duckduckgo`, `wikipedia`  — sem chave.
  • `brave` (chave), `tavily` (chave), `searxng` (endereço da sua instância).
Depois da busca o ASTA lê o texto das primeiras páginas (`fetch_pages`) e monta um bloco numerado «[1] título — url — trecho» que entra no contexto do
modelo, que cita as fontes como [1], [2]. Segurança: só `http(s)`, endereços que apontam para a própria máquina/rede privada são recusados nas páginas
dos resultados (SSRF), tamanho e tempo limitados.
"""
from __future__ import annotations

import html
import json
import re
import socket
import ipaddress
import ssl
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

from .providers import http
from .providers.base import ProviderError
from .util import ssl_context

MAX_RESULTS = 10
PAGE_BYTES = 400_000
PAGE_CHARS = 2500
CONTEXT_CHARS = 9000
_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0 ASTA", "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8", "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}


class SearchError(Exception):
    pass


# --------------------------------------------------------------------------- configuração
def web_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    c = ((settings.get("chat") or {}).get("web") or {})
    try:
        n = int(c.get("results", 5))
    except (TypeError, ValueError):
        n = 5
    try:
        pages = int(c.get("read_pages", 2))
    except (TypeError, ValueError):
        pages = 2
    engine = str(c.get("engine") or "auto").lower()
    if engine not in ("auto", "duckduckgo", "wikipedia", "brave", "tavily", "searxng"):
        engine = "auto"
    return {"engine": engine, "results": max(1, min(MAX_RESULTS, n)), "read_pages": max(0, min(5, pages)), "default": bool(c.get("default", False)),
            "brave_key": str(c.get("brave_key") or ""), "tavily_key": str(c.get("tavily_key") or ""), "searxng_url": str(c.get("searxng_url") or "").strip().rstrip("/"),
            "language": str(c.get("language") or "auto")}


# --------------------------------------------------------------------------- segurança das URLs
def safe_url(url: str) -> bool:
    """http(s) para um host público: recusa localhost, redes privadas e endereços especiais (o resultado da busca não pode apontar para a máquina do usuário)."""
    try:
        sp = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if sp.scheme not in ("http", "https") or not sp.hostname:
        return False
    host = sp.hostname
    if http.is_local_host(host):
        return False
    try:
        infos = socket.getaddrinfo(host, sp.port or (443 if sp.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
    return True


# --------------------------------------------------------------------------- HTML → texto
class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form", "iframe", "template"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "blockquote", "pre"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def html_to_text(src: str, limit: int = PAGE_CHARS) -> Dict[str, str]:
    p = _Text()
    try:
        p.feed(src)
        p.close()
    except Exception:  # noqa: BLE001  (HTML quebrado: aproveita o que deu)
        pass
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in "".join(p.parts).split("\n")]
    lines = [ln for ln in lines if len(ln) > 25 or (ln and len(lines) < 6)]  # tira menus e rótulos soltos
    txt = re.sub(r"\n{2,}", "\n", "\n".join(lines)).strip()
    return {"title": re.sub(r"\s+", " ", p.title).strip(), "text": txt[:limit]}


# --------------------------------------------------------------------------- motores
def _get(url: str, headers: Optional[dict] = None, timeout: float = 12, payload: Optional[dict] = None, raw: bool = False):
    hdrs = dict(_UA)
    hdrs.update(headers or {})
    try:
        with http.request(url, payload, hdrs, timeout=timeout, raw_body=None) as resp:
            data = resp.read(PAGE_BYTES * 2)
            ctype = resp.headers.get("Content-Type", "")
    except ProviderError as exc:
        raise SearchError(str(exc)) from None
    return data if raw else (data, ctype)


def _decode(data: bytes, ctype: str) -> str:
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    for enc in ([m.group(1)] if m else []) + ["utf-8", "latin-1"]:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "replace")


def _ddg(query: str, n: int, lang: str) -> List[Dict[str, str]]:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query, "kl": "br-pt" if lang == "pt" else "wt-wt"})
    data, ctype = _get(url)
    page = _decode(data, ctype)
    out: List[Dict[str, str]] = []
    for m in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="[^"]*result__a|\Z)', page, re.S):
        href, title, rest = html.unescape(m.group(1)), m.group(2), m.group(3)
        if href.startswith("//"):
            href = "https:" + href
        if "duckduckgo.com/l/" in href:  # link de redirecionamento: a URL real vem em uddg=
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get("uddg")
            if not q:
                continue
            href = q[0]
        if "duckduckgo.com/y.js" in href or not href.startswith("http"):  # anúncio
            continue
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>', rest, re.S)
        out.append({"title": _clean(title), "url": href, "snippet": _clean(sn.group(1)) if sn else ""})
        if len(out) >= n:
            break
    if not out and re.search(r"anomaly|captcha|unusual traffic", page, re.I):
        raise SearchError("O DuckDuckGo pediu verificação (muitas buscas seguidas). Tente de novo em instantes ou escolha outro motor em Configuração → Chat.")
    return out


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def _wikipedia(query: str, n: int, lang: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for code in ([lang, "en"] if lang != "en" else ["en"]):
        url = f"https://{code}.wikipedia.org/w/api.php?" + urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": query, "srlimit": n, "format": "json", "utf8": 1})
        data, _ = _get(url)
        for it in (json.loads(data.decode("utf-8", "replace")).get("query", {}).get("search") or []):
            title = it.get("title", "")
            out.append({"title": f"{title} — Wikipédia" if code == "pt" else f"{title} — Wikipedia", "url": f"https://{code}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")), "snippet": _clean(it.get("snippet", ""))})
        if out:
            break
    return out[:n]


def _brave(query: str, n: int, key: str) -> List[Dict[str, str]]:
    if not key:
        raise SearchError("Informe a chave da Brave Search em Configuração → Chat.")
    data, _ = _get("https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": query, "count": n}), {"X-Subscription-Token": key, "Accept": "application/json"})
    res = (json.loads(data.decode("utf-8", "replace")).get("web") or {}).get("results") or []
    return [{"title": _clean(r.get("title", "")), "url": r.get("url", ""), "snippet": _clean(r.get("description", ""))} for r in res[:n] if r.get("url")]


def _tavily(query: str, n: int, key: str) -> List[Dict[str, str]]:
    if not key:
        raise SearchError("Informe a chave da Tavily em Configuração → Chat.")
    try:
        data = http.post_json("https://api.tavily.com/search", {"query": query, "max_results": n}, {"Authorization": f"Bearer {key}"}, timeout=20)
    except ProviderError as exc:
        raise SearchError(str(exc)) from None
    return [{"title": _clean(r.get("title", "")), "url": r.get("url", ""), "snippet": _clean(r.get("content", ""))[:400]} for r in (data.get("results") or [])[:n] if r.get("url")]


def _searxng(query: str, n: int, base: str) -> List[Dict[str, str]]:
    if not base:
        raise SearchError("Informe o endereço da sua instância SearXNG em Configuração → Chat.")
    if "://" not in base:
        base = "http://" + base
    data, _ = _get(base + "/search?" + urllib.parse.urlencode({"q": query, "format": "json"}))
    try:
        res = json.loads(data.decode("utf-8", "replace")).get("results") or []
    except json.JSONDecodeError:
        raise SearchError("A instância SearXNG não devolveu JSON: ative o formato json em settings.yml (search.formats).") from None
    return [{"title": _clean(r.get("title", "")), "url": r.get("url", ""), "snippet": _clean(r.get("content", ""))} for r in res[:n] if r.get("url")]


def guess_lang(text: str, ui_lang: str = "auto") -> str:
    if ui_lang in ("pt", "en"):
        return ui_lang
    t = " " + text.lower() + " "
    pt = sum(t.count(w) for w in (" que ", " não ", " como ", " para ", " uma ", " com ", " qual ", " é ", " do ", " da ", " em ", "ção"))
    en = sum(t.count(w) for w in (" the ", " what ", " how ", " is ", " of ", " and ", " to ", " for ", " with "))
    return "pt" if pt > en else "en"


def search(query: str, settings: Dict[str, Any], n: Optional[int] = None, ui_lang: str = "auto") -> Dict[str, Any]:
    """{engine, query, results:[{title,url,snippet}]}. Levanta SearchError com mensagem útil."""
    cfg = web_config(settings)
    query = re.sub(r"\s+", " ", str(query or "")).strip()[:300]
    if not query:
        raise SearchError("Nada para pesquisar.")
    n = max(1, min(MAX_RESULTS, n or cfg["results"]))
    lang = guess_lang(query, cfg["language"] if cfg["language"] != "auto" else ui_lang)
    eng = cfg["engine"]
    errors: List[str] = []
    order = ["duckduckgo", "wikipedia"] if eng == "auto" else [eng]
    for name in order:
        try:
            if name == "duckduckgo":
                res = _ddg(query, n, lang)
            elif name == "wikipedia":
                res = _wikipedia(query, n, lang)
            elif name == "brave":
                res = _brave(query, n, cfg["brave_key"])
            elif name == "tavily":
                res = _tavily(query, n, cfg["tavily_key"])
            else:
                res = _searxng(query, n, cfg["searxng_url"])
        except SearchError as exc:
            errors.append(f"{name}: {exc}")
            continue
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        res = [r for r in res if r.get("url", "").startswith(("http://", "https://"))]
        if res:
            return {"engine": name, "query": query, "results": res[:n]}
    raise SearchError("Não encontrei resultados na web." + ((" " + " · ".join(errors)) if errors else ""))


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Cada redirecionamento também precisa apontar para um host público."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl):
            raise urllib.error.HTTPError(newurl, 403, "redirecionamento para endereço não público", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SafeRedirect, urllib.request.HTTPSHandler(context=ssl_context()))


def fetch_page(url: str, limit: int = PAGE_CHARS) -> Dict[str, str]:
    """Texto principal de uma página pública ({title, text}); {} se não deu."""
    if not safe_url(url):
        return {}
    try:
        with _OPENER.open(urllib.request.Request(url, headers=_UA), timeout=8) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if ctype and not re.search(r"html|text|xml", ctype, re.I):
                return {}
            data = resp.read(PAGE_BYTES)
    except (urllib.error.URLError, OSError, ValueError):
        return {}
    return html_to_text(_decode(data, ctype), limit)


def gather(query: str, settings: Dict[str, Any], ui_lang: str = "auto") -> Dict[str, Any]:
    """Busca + leitura das primeiras páginas. {engine, query, sources:[{n,title,url,host,snippet,text}], text}: `text` é o bloco para o contexto do modelo."""
    cfg = web_config(settings)
    found = search(query, settings, ui_lang=ui_lang)
    sources: List[Dict[str, Any]] = []
    for i, r in enumerate(found["results"], 1):
        host = (urllib.parse.urlsplit(r["url"]).hostname or "").removeprefix("www.")
        sources.append({"n": i, "title": r["title"] or host, "url": r["url"], "host": host, "snippet": r["snippet"], "text": ""})
    for s in sources[:cfg["read_pages"]]:
        page = fetch_page(s["url"])
        s["text"] = page.get("text", "")
    return {"engine": found["engine"], "query": found["query"], "sources": sources, "text": context_block(sources)}


def context_block(sources: List[Dict[str, Any]], limit: int = CONTEXT_CHARS) -> str:
    parts: List[str] = []
    used = 0
    for s in sources:
        remaining = limit - used
        if remaining < 200:
            break
        body = (s.get("text") or "").strip() or s.get("snippet", "")
        chunk = f"[{s['n']}] {s['title']}\n{s['url']}\n{body}".strip()[:remaining]
        parts.append(chunk)
        used += len(chunk) + 2
    return "\n\n".join(parts)


def public_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fontes para a interface (na ordem em que a busca devolveu): título, link, host, trecho e se a página foi lida por inteiro."""
    return [{"n": s["n"], "title": s["title"][:140], "url": s["url"][:500], "host": s["host"][:80], "snippet": (s.get("snippet") or "")[:300], "read": bool(s.get("text"))} for s in sources]


def heuristic_query(text: str) -> str:
    """Consulta de busca a partir da pergunta quando não dá para pedir ao modelo: tira a pontuação sobrando e limita o tamanho."""
    q = re.sub(r"\s+", " ", text or "").strip()
    q = re.sub(r"^(por favor|please|me diga|me explique|pesquise|busque|procure|search for|search|look up|tell me)[, ]+", "", q, flags=re.I)
    return q[:200]
