"""Provedor para APIs compatíveis com a OpenAI (Chat Completions).

Cobre OpenAI, xAI (Grok), Google Gemini (endpoint compatível), OpenRouter,
Hugging Face Inference, Ollama, LM Studio, llama.cpp server, vLLM e outros.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List

from . import http
from .base import Provider, ProviderError, content_images, content_text, split_system


class OpenAICompatProvider(Provider):
    def __init__(self, cfg: Dict[str, Any]):
        super().__init__(cfg)
        self.base = (cfg.get("base_url") or "").rstrip("/")
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
                data = http.post_json(self._url(), body, self._headers(), timeout=300)
                break
            except ProviderError as err:
                if not self._adapt(body, err):
                    raise
        else:  # pragma: no cover
            raise ProviderError("O provedor rejeitou os parâmetros da requisição.")
        try:
            msg = data["choices"][0]["message"]
            return (msg.get("content") or "").strip()
        except (KeyError, IndexError, TypeError):
            raise ProviderError(f"Resposta inesperada do provedor: {json.dumps(data)[:300]}") from None

    def _stream(self, messages, system, temperature, max_tokens) -> Iterator[str]:
        body = self._payload(messages, system, temperature, max_tokens, False, True)
        for _ in range(4):
            gen = http.stream_sse(self._url(), body, self._headers(), timeout=300)
            try:
                first = True
                for _evt, data in gen:
                    if data == "[DONE]":
                        return
                    try:
                        obj = json.loads(data)
                        choice = (obj.get("choices") or [{}])[0]
                        delta = (choice.get("delta") or {}).get("content")
                    except (json.JSONDecodeError, AttributeError, IndexError):
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
