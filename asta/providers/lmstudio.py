"""LM Studio (https://lmstudio.ai): detecção do servidor local, lista de modelos (carregados ou não) e provedor de chat.

O LM Studio expõe uma API compatível com a OpenAI em `http://127.0.0.1:1234/v1` e uma API própria em `/api/v0` que diz, para cada modelo, se está
**carregado**, o tipo (`llm`, `vlm` = com visão, `embeddings`), a quantização e o contexto. O ASTA usa as duas:

* detecta se o servidor está rodando (e onde), sem configuração;
* lista só os modelos de chat (sem os de embeddings), com os carregados primeiro;
* se nenhum modelo foi escolhido, usa o que estiver carregado (e a visão vem do tipo `vlm`);
* se o servidor não responde, explica como iniciá-lo (Developer → Start Server, ou `lms server start`).

Versões antigas sem `/api/v0` continuam funcionando pela lista de `/v1/models`.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Iterator, List, Optional

from . import http
from .base import ProviderError
from .openai_compat import OpenAICompatProvider

DEFAULT_URL = "http://127.0.0.1:1234"
HOW_TO_START = ("Abra o LM Studio, vá em «Developer» e ligue «Start Server» (ou rode  lms server start ) e carregue um modelo "
                "(botão «Load» / «Select a model to load»).")
_CACHE: Dict[str, Any] = {}
_LOCK = threading.Lock()


def root_url(base: str = "") -> str:
    """Endereço do servidor sem `/v1` nem `/api/v0` ("" → o padrão do LM Studio)."""
    b = (base or DEFAULT_URL).strip().rstrip("/")
    for suffix in ("/api/v0", "/api/v1", "/v1"):
        if b.endswith(suffix):
            b = b[: -len(suffix)]
    return b or DEFAULT_URL


def _headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _model(item: Dict[str, Any], native: bool = True) -> Optional[Dict[str, Any]]:
    mid = str(item.get("id") or item.get("modelKey") or "")
    if not mid:
        return None
    kind = str(item.get("type") or ("embeddings" if "embed" in mid.lower() else "llm")).lower()  # versões antigas não dizem o tipo
    state = str(item.get("state") or "unknown").lower()
    return {"id": mid, "type": kind, "state": state, "loaded": state == "loaded" or (not native and state == "unknown"), "vision": kind == "vlm", "arch": str(item.get("arch") or ""),
            "quant": str(item.get("quantization") or ""), "publisher": str(item.get("publisher") or ""),
            "max_ctx": int(item.get("max_context_length") or 0), "ctx": int(item.get("loaded_context_length") or 0)}


def probe(base_url: str = "", api_key: str = "", timeout: float = 2.0) -> Dict[str, Any]:
    """Estado do LM Studio: {running, url, models: [...só chat...], loaded: [ids], native, error}. Nunca levanta exceção."""
    root = root_url(base_url)
    out: Dict[str, Any] = {"running": False, "url": root, "models": [], "loaded": [], "native": False, "error": ""}
    items: Optional[List[Any]] = None
    try:
        data = http.get_json(root + "/api/v0/models", _headers(api_key), timeout=timeout)
        items = data.get("data") if isinstance(data, dict) else data
        out["native"] = True
    except ProviderError as exc:
        if exc.status is None:  # sem conexão: não adianta tentar a outra rota
            out["error"] = str(exc)
        else:  # servidor respondeu mas é uma versão sem /api/v0 (ou exige chave): tenta a rota compatível
            try:
                data = http.get_json(root + "/v1/models", _headers(api_key), timeout=timeout)
                items = data.get("data") if isinstance(data, dict) else data
            except ProviderError as exc2:
                out["error"] = str(exc2)
                out["running"] = exc2.status is not None  # respondeu (ex.: 401): está rodando, só falta a chave
    if items is not None:
        out["running"] = True
        # sem a API nativa (versões antigas) não há como saber o que está carregado: a lista de /v1/models é tratada como disponível
        models = [m for m in (_model(i, out["native"]) for i in items if isinstance(i, dict)) if m and m["type"] not in ("embeddings", "embedding")]
        models.sort(key=lambda m: (not m["loaded"], m["id"].lower()))
        out["models"] = models
        out["loaded"] = [m["id"] for m in models if m["loaded"]]
    return out


def detect(base_url: str = "", api_key: str = "", max_age: float = 8.0, timeout: float = 1.0) -> Dict[str, Any]:
    """`probe` com cache curto (cada mensagem de chat consulta isto; o servidor desligado não pode atrasar a conversa)."""
    key = root_url(base_url)
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < max_age:
            return hit[1]
    info = probe(base_url, api_key, timeout=timeout)
    with _LOCK:
        _CACHE[key] = (now, info)
    return info


def scan(hosts: Optional[List[str]] = None, port: int = 1234, timeout: float = 0.4, budget: float = 8.0) -> List[Dict[str, Any]]:
    """Procura servidores do LM Studio na rede local (a /24 de cada IP deste aparelho; ou `hosts`): só a porta do LM Studio, só leitura da lista de modelos.
    Serve para o celular achar o LM Studio do computador sem digitar o IP. Devolve [{url, running, loaded:[ids]}]."""
    import socket
    from concurrent.futures import ThreadPoolExecutor

    if hosts is None:
        from ..mobile import lan_ips

        hosts = []
        for ip in lan_ips():
            parts = ip.split(".")
            if len(parts) == 4 and not ip.startswith("127."):
                hosts += [".".join(parts[:3] + [str(i)]) for i in range(1, 255) if str(i) != parts[3]]
    hosts = list(dict.fromkeys(hosts))[:1024]
    t0 = time.time()

    def open_port(h: str) -> Optional[str]:
        if time.time() - t0 > budget:
            return None
        try:
            with socket.create_connection((h, port), timeout=timeout):
                return h
        except OSError:
            return None

    with ThreadPoolExecutor(max_workers=64) as ex:
        found = [h for h in ex.map(open_port, hosts) if h]
    out: List[Dict[str, Any]] = []
    for h in found[:8]:
        info = probe(f"http://{h}:{port}", timeout=2.0)
        if info["running"]:
            out.append({"url": info["url"], "running": True, "loaded": info["loaded"], "models": len(info["models"])})
    return out


def forget() -> None:
    with _LOCK:
        _CACHE.clear()


class LMStudioProvider(OpenAICompatProvider):
    """Chat via LM Studio. Sem modelo escolhido, usa o carregado no LM Studio; a visão vem do tipo do modelo (`vlm`)."""

    def __init__(self, cfg: Dict[str, Any]):
        cfg = dict(cfg)
        self.root = root_url(cfg.get("base_url") or "")
        cfg["base_url"] = self.root + "/v1"
        super().__init__(cfg)
        self.label = cfg.get("label", "LM Studio")
        self._vision_set = bool(cfg.get("vision_user"))

    def prepare(self) -> None:
        """Resolve o modelo (o carregado no LM Studio, se nenhum foi escolhido) e a visão. Levanta ProviderError com instruções se não der."""
        info = detect(self.root, self.key)
        if not info["running"]:
            raise ProviderError(f"Não consegui falar com o LM Studio em {self.root}. {HOW_TO_START}")
        by_id = {m["id"]: m for m in info["models"]}
        if not self.model:
            if not info["loaded"]:
                names = ", ".join(m["id"] for m in info["models"][:4])
                raise ProviderError("O LM Studio está rodando, mas nenhum modelo está carregado. Carregue um no LM Studio" + (f" (instalados: {names})" if names else " (baixe um na aba «Discover»)") + ", ou escolha o modelo em Configuração → Provedores.")
            self.model = info["loaded"][0]
        meta = by_id.get(self.model)
        if meta and meta["vision"] and not self._vision_set:
            self.vision = True

    # chat: antes de tudo garante servidor + modelo; erros de conexão ganham instruções
    def _payload(self, messages, system, temperature, max_tokens, json_mode, stream) -> dict:
        self.prepare()
        return super()._payload(messages, system, temperature, max_tokens, json_mode, stream)

    def _chat(self, messages, system, temperature, max_tokens, json_mode) -> str:
        try:
            return super()._chat(messages, system, temperature, max_tokens, json_mode)
        except ProviderError as exc:
            raise self._friendly(exc) from None

    def _stream(self, messages, system, temperature, max_tokens) -> Iterator[str]:
        try:
            yield from super()._stream(messages, system, temperature, max_tokens)
        except ProviderError as exc:
            raise self._friendly(exc) from None

    def _friendly(self, exc: ProviderError) -> ProviderError:
        if exc.status is None and ("conectar" in str(exc) or "rede" in str(exc).lower()):
            forget()
            return ProviderError(f"Perdi a conexão com o LM Studio em {self.root}. {HOW_TO_START}")
        if exc.status in (404, 400) and "model" in str(exc).lower():
            return ProviderError(f"O LM Studio não achou o modelo «{self.model}»: carregue-o no LM Studio ou escolha outro em Configuração → Provedores. ({exc})", status=exc.status)
        return exc

    def list_models(self) -> List[str]:
        info = probe(self.root, self.key, timeout=5)
        if not info["running"]:
            raise ProviderError(f"Não consegui falar com o LM Studio em {self.root}. {HOW_TO_START}")
        return [m["id"] for m in info["models"]]
