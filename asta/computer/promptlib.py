"""Biblioteca dos system prompts internos do Computer Use (arquivos `.md` em `prompts/`).

Cada agente (Planejador, Operador, Revisor, Relator) tem um `.md`; o Operador ainda recebe o guia do **especialista** da tarefa (arquivos, programas com tela, jogos, pesquisa, escrita)
e o guia do **programa** citado (Krita, OBS, Audacity…). Os arquivos ficam em texto simples para qualquer pessoa ler e melhorar — são parte do código aberto do ASTA.
Os prompts são em inglês (os modelos seguem melhor instruções estruturadas em inglês); o texto que o usuário lê sai no idioma dele.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from ..agents.prompts import POLICY_FREE, POLICY_SFW

DIR = Path(__file__).parent / "prompts"
AGENTS = ("planner", "operator", "verifier", "reporter")
SPECIALISTS = {"files": "files", "apps": "gui", "games": "games", "research": "research", "writing": "writing"}

# palavra no pedido → guia do programa
APP_GUIDES = (
    (re.compile(r"\bkrita\b", re.I), "krita"),
    (re.compile(r"\bobs\b|obs studio", re.I), "obs"),
    (re.compile(r"audacity", re.I), "audacity"),
    (re.compile(r"\bsteam\b|lutris|\bjogo|\bjogar|\bgame\b|\bplay\b", re.I), "steam"),
    (re.compile(r"navegador|browser|chrome|firefox|\bedge\b|brave|safari|\bsite\b|https?://", re.I), "browser"),
    (re.compile(r"bloco de notas|notepad|gedit|\bkate\b|textedit|writer|libreoffice|\bword\b|\bexcel\b|\bcalc\b|documento|planilha|spreadsheet|document", re.I), "texteditor"),
    (re.compile(r"explorer|finder|nautilus|dolphin|thunar|gerenciador de arquivos|file manager", re.I), "filemanager"),
)


@lru_cache(maxsize=64)
def _read(rel: str) -> str:
    p = DIR / rel
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def names() -> List[str]:
    """Todos os prompts empacotados (para os testes e para a tela de Configuração mostrar o que existe)."""
    return sorted(str(p.relative_to(DIR)).replace("\\", "/") for p in DIR.rglob("*.md"))


def read(rel: str) -> str:
    return _read(rel)


def _fill(text: str, values: Dict[str, str]) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), ""), text)


def content_policy(mode: str) -> str:
    return POLICY_SFW if mode == "sfw" else POLICY_FREE


def app_guides(goal: str, uses_gui: bool) -> List[str]:
    out: List[str] = []
    for rx, name in APP_GUIDES:
        if rx.search(goal or "") and name not in out:
            out.append(name)
    if uses_gui and not out:
        out.append("generic")
    return out


def compose(agent: str, *, language: str, os_label: str, home: str, content: str = "free", mode: str = "ask", kind: str = "mixed", goal: str = "",
            tools: str = "", unavailable: str = "", uses_gui: bool = False) -> str:
    """O system prompt completo de um agente."""
    if agent not in AGENTS:
        raise ValueError(f"agente desconhecido: {agent}")
    values = {"language": language, "os": os_label, "home": home, "content_policy": content_policy(content), "safety": _read("safety.md")}
    head = f"[[ASTA_AGENT:computer_{agent}]]\n"
    extra: Dict[str, str] = {}
    if agent == "operator":
        spec = SPECIALISTS.get(kind)
        specs = [spec] if spec else list(dict.fromkeys(SPECIALISTS.values()))
        guide_names = app_guides(goal, uses_gui)
        extra = {
            "mode_rules": _read("mode_full.md" if mode == "full" else "mode_ask.md"),
            "tools": tools,
            "unavailable": ("\n## Not available on this computer right now\n" + unavailable) if unavailable else "",
            "specialists": "\n".join(_fill(_read(f"specialists/{s}.md"), values) for s in specs if _read(f"specialists/{s}.md")),
            "app_guides": ("\n## Program guides\n" + "\n".join(_read(f"apps/{g}.md") for g in guide_names if _read(f"apps/{g}.md"))) if guide_names else "",
        }
    parts = [_fill(_read("core.md"), values), _fill(_read(f"{agent}.md"), {**values, **extra})]
    return head + "\n\n".join(p for p in parts if p)
