"""Provedor para APIs compatíveis com a OpenAI (Chat Completions).

Cobre OpenAI, xAI (Grok), Google Gemini (endpoint compatível), OpenRouter,
Hugging Face Inference, Ollama, LM Studio, llama.cpp server, vLLM e outros.
"""
from __future__ import annotations

import json
import urllib.parse
from typing import Any, Dict, Iterator, List

from . import http
from .base import Provider, ProviderError, content_images, content_text, split_system


def normalize_base(base: str, add_v1: bool = False) -> str:
    """Endereço da API como o usuário costuma digitar: sem esquema ("localhost:11434" → http://…) e, nos servidores locais, sem o /v1
    (o Ollama e o llama.cpp respondem em /v1: "http://localhost:11434" vira "http://localhost:11434/v1")."""
    b = (base or "").strip().rstrip("/")
    if not b:
        return ""
    if "://" not in b:
        b = "http://" + b
    if add_v1 and urllib.parse.urlsplit(b).path in ("", "/"):
        b += "/v1"
    return b


def _text(content: Any) -> str:
    """O texto da resposta: alguns servidores devolvem uma lista de partes em vez de uma string."""
    if isinstance(content, list):
        return "".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in content)
    return str(content or "")


class OpenAICompatProvider(Provider):
    #: provedores em que o usuário digita o endereço do servidor (e costuma esquecer o /v1)
    LOCAL_IDS = ("ollama", "llamacpp", "custom", "lmstudio")

    def __init__(self, cfg: Dict[str, Any]):
        super().__init__(cfg)
        self.base = normalize_base(cfg.get("base_url") or "", add_v1=cfg.get("id") in self.LOCAL_IDS)
        self.key = cfg.get("api_key") or ""
        self.use_json_mode = bool(cfg.get("json"))
        self.label = cfg.get("label", "OpenAI-compatível")

    # ------------------------------------------------------------ helpers
    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self.key:
            h["Authorization"] = f"Bearer {self.key}"
        return h

    def _convert(self, messages: List[dict], system: str) -> List[dict]:
        sys_text, rest = split_system(messages, system)
        out: List[dict] = []
        if sys_text:
            out.append({"role": "system", "content": sys_text})
        for m in rest:
            content = m.get("content")
            imgs = content_images(content)
            if imgs and self.vision:
                parts: List[dict] = []
                txt = content_text(content)
                if txt:
                    parts.append({"type": "text", "text": txt})
                for img in imgs:
                    url = f"data:{img.get('media_type', 'image/png')};base64,{img.get('data', '')}"
                    parts.append({"type": "image_url", "image_url": {"url": url}})
                out.append({"role": m["role"], "content": parts})
            else:
                txt = content_text(content)
                if imgs and not self.vision:
                    txt += f"\n[{len(imgs)} imagem(ns) anexada(s) — este provedor está sem visão]"
                out.append({"role": m["role"], "content": txt})
        return out

    def _payload(self, messages, system, temperature, max_tokens, json_mode, stream) -> dict:
        if not self.model:
            raise ProviderError("Nenhum modelo selecionado. Escolha um modelo em Configuração → Provedores.")
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": self._convert(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if json_mode and self.use_json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    def _adapt(self, body: dict, err: ProviderError) -> bool:
        """Ajusta parâmetros que o modelo rejeita (modelos de raciocínio, etc.). True = tentar de novo."""
        msg = str(err).lower()
        if err.status not in (400, 422):
            return False
        if "max_completion_tokens" in msg and "max_tokens" in body:
            body["max_completion_tokens"] = body.pop("max_tokens")
            return True
        if "temperature" in msg and "temperature" in body:
            body.pop("temperature")
            return True
        if "response_format" in msg and "response_format" in body:
            body.pop("response_format")
            return True
        return False

    def _url(self) -> str:
        if not self.base:
            raise ProviderError("Informe a URL base do provedor em Configuração → Provedores.")
        return self.base + "/chat/completions"

    # ------------------------------------------------------------ chat
    def _chat(self, messages, system, temperature, max_tokens, json_mode) -> str:
        body = self._payload(messages, system, temperature, max_tokens, json_mode, False)
        for _ in range(4):
            try:
                data = http.post_json(self._url(), body, self._headers(), timeout=300, retries=2)
                break
            except ProviderError as err:
                if not self._adapt(body, err):
                    raise
        else:  # pragma: no cover
            raise ProviderError("O provedor rejeitou os parâmetros da requisição.")
        try:
            msg = data["choices"][0]["message"]
            return _text(msg.get("content")).strip()
        except (KeyError, IndexError, TypeError):
            raise ProviderError(f"Resposta inesperada do provedor: {json.dumps(data)[:300]}") from None

    def _stream(self, messages, system, temperature, max_tokens) -> Iterator[str]:
        body = self._payload(messages, system, temperature, max_tokens, False, True)
        for _ in range(4):
            gen = http.stream_sse(self._url(), body, self._headers(), timeout=300, retries=2)
            try:
                first = True
                for _evt, data in gen:
                    if data == "[DONE]":
                        return
                    try:
                        obj = json.loads(data)
                        if isinstance(obj, dict) and obj.get("error"):  # erro no meio do streaming (limite, modelo caiu…)
                            err_obj = obj["error"]
                            raise ProviderError(str(err_obj.get("message") if isinstance(err_obj, dict) else err_obj)[:400] or "O provedor interrompeu a resposta.")
                        choice = (obj.get("choices") or [{}])[0]
                        delta = _text((choice.get("delta") or {}).get("content"))
                    except (json.JSONDecodeError, AttributeError, IndexError, TypeError):
                        continue
                    if delta:
                        first = False
                        yield delta
                return
            except ProviderError as err:
                if first and self._adapt(body, err):
                    continue
                raise
        raise ProviderError("O provedor rejeitou os parâmetros da requisição.")

    def list_models(self) -> List[str]:
        if not self.base:
            return []
        data = http.get_json(self.base + "/models", self._headers(), timeout=20)
        items = data.get("data", data.get("models", [])) if isinstance(data, dict) else data
        ids = []
        for it in items or []:
            mid = it.get("id") or it.get("name") if isinstance(it, dict) else str(it)
            if mid:
                ids.append(str(mid).replace("models/", "", 1))
        return sorted(set(ids))
