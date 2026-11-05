"""Base comum dos pipelines multi-agentes (mundos 3D, avatars, jogos 2D).

Cada etapa é um *agente*: recebe instruções + JSON de entrada e devolve um objeto JSON.
Resposta inválida → fallback determinístico (a entrega nunca falha por culpa do modelo);
erro de rede/credencial → o job falha com uma mensagem clara.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..providers import ProviderError
from . import prompts
from .llm import call_json

TRANSIENT = (408, 409, 425, 429, 500, 502, 503, 504, 529)


class Cancelled(Exception):
    pass


class Runner:
    #: domínio do pipeline: define o preâmbulo do prompt de sistema dos agentes
    domain = "world"

    def __init__(self, store, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False):
        self.store = store
        self.emit = emit
        self.cancelled = cancelled
        self.logs: List[Tuple[str, str]] = []
        self.warnings: List[str] = []
        self._log_n = 0
        # preenchidos por cada pipeline em run()
        self.provider: Any = None
        self.gen: Dict[str, Any] = {}
        self.language = "the same language as the user's prompt"

    # ------------------------------------------------------------------ helpers
    def _check(self) -> None:
        if self.cancelled():
            raise Cancelled()

    def _step(self, sid: str, status: str, **detail: Any) -> None:
        self.emit({"type": "step", "id": sid, "status": status, "detail": detail, "t": time.time()})

    def _log(self, agent: str, system: str, instruction: str, payload: Any, output: str) -> None:
        self._log_n += 1
        body = (
            f"# Agente: {agent}\n\n## Instruções\n\n```\n{system}{instruction}\n```\n\n"
            f"## Entrada (JSON)\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)[:20000]}\n```\n\n"
            f"## Saída\n\n```json\n{output}\n```\n"
        )
        self.logs.append((f"{self._log_n:02d}-{agent}.md", body))

    def _agent(
        self, step: str, agent: str, instruction: str, payload: Dict[str, Any], fallback: Callable[[Dict[str, Any]], Dict[str, Any]],
        *, images: Optional[List[dict]] = None, tokens_mult: float = 1.0, feedback: bool = False,
    ) -> Tuple[Dict[str, Any], bool]:
        """Executa um agente. JSON inválido → fallback determinístico. Erro de rede/credencial → falha o job."""
        self._check()
        self._step(step, "running", revision=feedback)
        system = prompts.system_prompt(agent, self.language, self.gen.get("content", "free"), self.domain)
        last: Optional[Exception] = None
        for attempt in range(3):
            try:
                obj, raw = call_json(
                    self.provider, system, instruction, payload, images=images,
                    temperature=float(self.gen.get("temperature", 0.8)),
                    max_tokens=int(int(self.gen.get("max_tokens", 6000)) * tokens_mult),
                    cancelled=self.cancelled,
                )
                self._log(agent, system, instruction, payload, raw)
                return obj, False
            except ProviderError as exc:
                if str(exc) == "cancelado":
                    raise Cancelled() from None
                last = exc
                if exc.status in TRANSIENT and attempt < 2:
                    for _ in range(int(3 * (attempt + 1) * 2)):  # espera cancelável
                        self._check()
                        time.sleep(0.5)
                    continue
                raise
            except ValueError as exc:  # JSON inválido mesmo após reparo
                last = exc
                break
        self.warnings.append(f"{agent}: fallback ({last})")
        out = fallback(payload)
        self._log(agent, system, instruction, payload, "// FALLBACK determinístico: " + str(last) + "\n" + json.dumps(out, ensure_ascii=False, indent=2))
        return out, True
