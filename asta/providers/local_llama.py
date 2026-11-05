"""Modelos locais do Hugging Face (GGUF) rodando dentro do próprio ASTA.

Requer o extra opcional:  pip install "asta[local]"  (llama-cpp-python).
Para um caminho sem dependências extras, use Ollama / LM Studio / llama.cpp server,
que são suportados como provedores OpenAI-compatíveis.
"""
from __future__ import annotations

import gc
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Tuple

from .. import perf
from ..util import hardware_info
from .base import Provider, ProviderError, content_text, split_system

_CACHE: Dict[str, Any] = {}
_LOCK = threading.Lock()


def _n_ctx(tier: str) -> int:
    return {"low": 2048, "medium": 4096, "high": 8192}.get(tier, 4096)


MAX_CTX = 1 << 20


def _unload() -> None:
    with _LOCK:
        _CACHE.clear()
    gc.collect()


_IDLE = perf.IdleUnloader(_unload)


def _load_llama(Llama: Any, base: Dict[str, Any], prof: Dict[str, Any]) -> Any:
    """Carrega o modelo com as opções de economia do modo escolhido; versões antigas do llama-cpp-python que não as conhecem recebem só as básicas."""
    extra: Dict[str, Any] = {"n_batch": prof["n_batch"], "use_mmap": True}
    if prof["flash"]:
        extra["flash_attn"] = True
    if prof["kv_q8"]:
        extra.update(type_k=8, type_v=8, flash_attn=True)  # 8 = GGML_TYPE_Q8_0 (cache de atenção pela metade; exige flash attention)
    basic = {k: v for k, v in extra.items() if k in ("n_batch", "use_mmap")}
    for kw in (extra, basic):
        try:
            return Llama(**base, **kw)
        except Exception:  # noqa: BLE001  (versão/backend sem essas opções: tenta com menos)
            continue
    return Llama(**base)


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


class ContextTooLong(ValueError):
    """A conversa não cabe na janela de contexto. É um ValueError de propósito: os pipelines tratam como "resposta inválida" (caem nas regras)
    e o chat mostra a mensagem com o que fazer, em vez de derrubar a geração inteira."""


def fit_messages(msgs: List[dict], count: Callable[[str], int], ctx: int, max_tokens: int) -> Tuple[List[dict], int]:
    """Cabe a conversa na janela de contexto: mantém a mensagem de sistema e a última, e descarta as mais antigas até sobrar espaço para a resposta.
    Devolve (mensagens, max_tokens ajustado). Sem isto, uma conversa longa estoura o contexto (ValueError do llama.cpp) e o avatar para de responder."""
    max_tokens = max(64, min(int(max_tokens), ctx // 2))
    budget = ctx - max_tokens - 16
    sizes = [count(str(m.get("content") or "")) + 8 for m in msgs]
    system = [i for i, m in enumerate(msgs) if m.get("role") == "system"][:1]
    keep = set(system)
    used = sum(sizes[i] for i in keep)
    for i in range(len(msgs) - 1, -1, -1):  # das mais novas para as mais antigas
        if i in keep:
            continue
        if used + sizes[i] > budget and i != len(msgs) - 1:
            break  # a última (a pergunta atual) entra sempre
        keep.add(i)
        used += sizes[i]
    out = [m for i, m in enumerate(msgs) if i in keep]
    while len(out) > 1 and out[1 if out[0].get("role") == "system" else 0].get("role") == "assistant":
        out.pop(1 if out[0].get("role") == "system" else 0)  # modelos com template estrito exigem começar pelo usuário
    return out, max_tokens


class LocalLlamaProvider(Provider):
    def __init__(self, cfg: Dict[str, Any]):
        super().__init__(cfg)
        self.label = cfg.get("label", "Hugging Face local")
        self.models_dir = Path(cfg.get("models_dir", "."))
        self.n_ctx_cfg = cfg.get("n_ctx")
        self.perf_cfg = cfg.get("performance") or {}

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
        prof = perf.profile(self.perf_cfg, hw)
        ctx = perf.cap_context(context_size(self.n_ctx_cfg, Path(path).name, hw["tier"]), prof, explicit=bool(self.n_ctx_cfg))
        key = f"{path}|{ctx}|{prof['mode']}"  # mudar a janela de contexto ou o modo recarrega o modelo
        with _LOCK:
            llm = _CACHE.get(key)
            if llm is None:
                use_gpu = bool(hw.get("gpu")) or (hw["os"] == "Darwin" and "arm" in hw["arch"].lower())
                base = dict(model_path=path, n_ctx=ctx, n_threads=max(1, hw["cpus"] - 1), n_gpu_layers=-1 if use_gpu else 0, verbose=False)
                _CACHE.clear()  # mantém apenas um modelo na RAM (hardware leve)
                gc.collect()
                llm = _load_llama(Llama, base, prof)
                _CACHE[key] = llm
        _IDLE.touch(prof["idle_s"])
        return llm, path

    def _messages(self, messages: List[dict], system: str) -> List[dict]:
        sys_text, rest = split_system(messages, system)
        out = [{"role": "system", "content": sys_text}] if sys_text else []
        out += [{"role": m["role"], "content": content_text(m.get("content"))} for m in rest]
        return out

    def _prepare(self, llm: Any, messages: List[dict], system: str, max_tokens: int) -> Tuple[List[dict], int]:
        ctx = int(llm.n_ctx()) if callable(getattr(llm, "n_ctx", None)) else 2048
        count = lambda t: len(llm.tokenize(t.encode("utf-8"), add_bos=False)) if hasattr(llm, "tokenize") else len(t) // 3 + 1  # noqa: E731
        return fit_messages(self._messages(messages, system), count, ctx, max_tokens)

    @staticmethod
    def _wrap(exc: Exception) -> Exception:
        msg = str(exc)
        if "context" in msg.lower() or "exceed" in msg.lower():
            return ContextTooLong("A conversa não cabe na janela de contexto do modelo local. Aumente a janela em Configuração → Provedores → "
                                 "Hugging Face GGUF → Janela de contexto, ou reinicie a conversa.")
        return ProviderError(f"O modelo local falhou: {msg[:300]}")

    def _chat(self, messages, system, temperature, max_tokens, json_mode) -> str:
        llm, path = self._llm()
        msgs, max_tokens = self._prepare(llm, messages, system, max_tokens)
        with _LOCK:
            try:
                try:
                    res = llm.create_chat_completion(messages=msgs, temperature=temperature, max_tokens=max_tokens,
                                                     **({"response_format": {"type": "json_object"}} if json_mode else {}))
                except (TypeError, KeyError):  # versão do llama-cpp-python sem response_format: segue sem a gramática JSON
                    if not json_mode:
                        raise
                    res = llm.create_chat_completion(messages=msgs, temperature=temperature, max_tokens=max_tokens)
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001  (ValueError de contexto, RuntimeError do llama.cpp…)
                raise self._wrap(exc) from None
        return (res["choices"][0]["message"].get("content") or "").strip()

    def _stream(self, messages, system, temperature, max_tokens) -> Iterator[str]:
        llm, _ = self._llm()
        msgs, max_tokens = self._prepare(llm, messages, system, max_tokens)
        with _LOCK:
            try:
                for chunk in llm.create_chat_completion(messages=msgs, temperature=temperature, max_tokens=max_tokens, stream=True):
                    delta = chunk["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
            except GeneratorExit:
                raise
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise self._wrap(exc) from None

    def list_models(self) -> List[str]:
        """Os GGUF de texto baixados (um modelo dividido em partes aparece uma vez; arquivos de visão/mmproj ficam de fora)."""
        from .. import hf

        return sorted(m["name"] for m in hf.local_models(self.models_dir, "text"))
