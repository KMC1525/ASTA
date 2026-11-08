"""Biblioteca dos system prompts internos do Code (arquivos `.md` em `prompts/`).

Cada agente (Planejador, Operador/Trabalhador, Revisor, Relator) tem um `.md`; o Trabalhador ainda recebe o guia do **papel** do passo (coder, debugger, tester, ui, docs…), o guia das
**linguagens** do projeto (`langs/*.md`) e a orientação do **nível de esforço**. Os arquivos ficam em texto simples para qualquer pessoa ler e melhorar — são parte do código aberto do ASTA.
Os prompts são em inglês (os modelos seguem melhor instruções estruturadas em inglês); o texto que o usuário lê sai no idioma dele.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from ..agents.prompts import POLICY_FREE, POLICY_SFW
from . import efforts

DIR = Path(__file__).parent / "prompts"
AGENTS = ("planner", "operator", "reviewer", "reporter")


@lru_cache(maxsize=96)
def _read(rel: str) -> str:
    p = DIR / rel
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def names() -> List[str]:
    """Todos os prompts empacotados (para os testes e para a tela mostrar o que existe)."""
    return sorted(str(p.relative_to(DIR)).replace("\\", "/") for p in DIR.rglob("*.md"))


def read(rel: str) -> str:
    return _read(rel)


def _fill(text: str, values: Dict[str, str]) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), ""), text)


def content_policy(mode: str) -> str:
    return POLICY_SFW if mode == "sfw" else POLICY_FREE


def compose(agent: str, *, language: str, os_label: str, project: str, content: str = "free", mode: str = "ask", role: str = "coder", lang_guides: List[str] = (),
            tools: str = "", unavailable: str = "", effort: str = "high", agents: int = 4, plan_steps: int = 7, finalize: str = "") -> str:
    """O system prompt completo de um agente."""
    if agent not in AGENTS:
        raise ValueError(f"agente desconhecido: {agent}")
    lv = efforts.normalize(effort)
    values = {"language": language, "os": os_label, "project": project, "content_policy": content_policy(content), "safety": _read("safety.md"), "agents": str(agents), "plan_steps": str(plan_steps),
              "finalize": finalize or "no finalization requested", "effort": "\n## Effort\n" + efforts.guidance(lv), "role": role}
    extra: Dict[str, str] = {}
    if agent == "operator":
        guides = [_read(f"langs/{g}.md") for g in (lang_guides or ["generic"]) if _read(f"langs/{g}.md")]
        if "generic" not in (lang_guides or []) and _read("langs/generic.md"):
            guides.append(_read("langs/generic.md"))
        extra = {"mode_rules": _read("mode_full.md" if mode == "full" else "mode_ask.md"), "tools": tools, "role_guide": _read(f"roles/{role}.md") or _read("roles/coder.md"),
                 "unavailable": ("\n## Not available right now\n" + unavailable) if unavailable else "", "lang_guides": "\n".join(guides)}
    parts = [_fill(_read("core.md"), values), _fill(_read(f"{agent}.md"), {**values, **extra})]
    return f"[[ASTA_AGENT:code_{agent}]]\n" + "\n\n".join(p for p in parts if p)
