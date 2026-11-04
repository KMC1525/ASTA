"""Modelos locais do Hugging Face (GGUF) rodando dentro do próprio ASTA.

Requer o extra opcional:  pip install "asta[local]"  (llama-cpp-python).
Para um caminho sem dependências extras, use Ollama / LM Studio / llama.cpp server,
que são suportados como provedores OpenAI-compatíveis.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Iterator, List

from ..util import hardware_info
from .base import Provider, ProviderError, content_text, split_system

_CACHE: Dict[str, Any] = {}
_LOCK = threading.Lock()


def _n_ctx(tier: str) -> int:
    return {"low": 2048, "medium": 4096, "high": 8192}.get(tier, 4096)


class LocalLlamaProvider(Provider):
    def __init__(self, cfg: Dict[str, Any]):
        super().__init__(cfg)
        self.label = cfg.get("label", "Hugging Face local")
        self.models_dir = Path(cfg.get("models_dir", "."))

    def _model_path(self) -> Path:
        name = self.model
        if not name:
            raise ProviderError("Baixe e selecione um modelo GGUF em Configuração → Modelos locais.")
        path = Path(name)
        if not path.is_absolute():
            path = self.models_dir / name
        if not path.exists():
            raise ProviderError(f"Modelo não encontrado: {path}")
        return path

    def _llm(self):
        try:
            from llama_cpp import Llama  # type: ignore
        except ImportError:
            raise ProviderError(
                'Para usar modelos locais embutidos instale o extra:  pip install "asta[local]"  '
                "(ou use Ollama / LM Studio como provedor)."
            ) from None
        path = str(self._model_path())
        with _LOCK:
            llm = _CACHE.get(path)
            if llm is None:
                hw = hardware_info()
                use_gpu = bool(hw.get("gpu")) or (hw["os"] == "Darwin" and "arm" in hw["arch"].lower())
                llm = Llama(
                    model_path=path,
                    n_ctx=_n_ctx(hw["tier"]),
                    n_threads=max(1, hw["cpus"] - 1),
                    n_gpu_layers=-1 if use_gpu else 0,
                    verbose=False,
                )
                _CACHE.clear()  # mantém apenas um modelo na RAM (hardware leve)
                _CACHE[path] = llm
        return llm, path

    def _messages(self, messages: List[dict], system: str) -> List[dict]:
        sys_text, rest = split_system(messages, system)
        out = [{"role": "system", "content": sys_text}] if sys_text else []
        out += [{"role": m["role"], "content": content_text(m.get("content"))} for m in rest]
        return out

    def _chat(self, messages, system, temperature, max_tokens, json_mode) -> str:
        llm, path = self._llm()
        with _LOCK:
            res = llm.create_chat_completion(
                messages=self._messages(messages, system), temperature=temperature, max_tokens=max_tokens
            )
        return (res["choices"][0]["message"].get("content") or "").strip()

    def _stream(self, messages, system, temperature, max_tokens) -> Iterator[str]:
        llm, _ = self._llm()
        with _LOCK:
            for chunk in llm.create_chat_completion(
                messages=self._messages(messages, system), temperature=temperature, max_tokens=max_tokens, stream=True
            ):
                delta = chunk["choices"][0].get("delta", {}).get("content")
                if delta:
                    yield delta

    def list_models(self) -> List[str]:
        return sorted(p.name for p in self.models_dir.glob("*.gguf"))
