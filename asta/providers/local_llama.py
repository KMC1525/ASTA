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


MAX_CTX = 1 << 20


def context_size(configured: Any, model_name: str, tier: str) -> int:
    """Janela de contexto (tokens): o valor que o usuário definiu; senão o padrão do modelo pré-instalado (32K para os de texto); senão pelo hardware."""
    try:
        n = int(configured or 0)
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        return max(512, min(n, MAX_CTX))
    from .. import preinstalled  # import tardio: evita ciclo (preinstalled → hf → providers)

    return preinstalled.default_n_ctx(model_name) or _n_ctx(tier)


class LocalLlamaProvider(Provider):
    def __init__(self, cfg: Dict[str, Any]):
        super().__init__(cfg)
        self.label = cfg.get("label", "Hugging Face local")
        self.models_dir = Path(cfg.get("models_dir", "."))
        self.n_ctx_cfg = cfg.get("n_ctx")

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
        hw = hardware_info()
        ctx = context_size(self.n_ctx_cfg, Path(path).name, hw["tier"])
        key = f"{path}|{ctx}"  # mudar a janela de contexto recarrega o modelo
        with _LOCK:
            llm = _CACHE.get(key)
            if llm is None:
                use_gpu = bool(hw.get("gpu")) or (hw["os"] == "Darwin" and "arm" in hw["arch"].lower())
                llm = Llama(
                    model_path=path,
                    n_ctx=ctx,
                    n_threads=max(1, hw["cpus"] - 1),
                    n_gpu_layers=-1 if use_gpu else 0,
                    verbose=False,
                )
                _CACHE.clear()  # mantém apenas um modelo na RAM (hardware leve)
                _CACHE[key] = llm
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
