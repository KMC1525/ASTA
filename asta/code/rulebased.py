"""O Code sem IA (provedor Demo ou nenhuma IA configurada): um conjunto pequeno de pedidos que dá para atender só com regras — ver o projeto, ler um arquivo, buscar um trecho,
rodar os testes/build/lint, ver as mudanças do git. Qualquer outra coisa pede uma IA (configure um provedor — nuvem, LM Studio ou modelo local). É o *fallback determinístico* do motor:
a sessão nunca cai por falta de IA; ela diz exatamente o que dá para fazer sem ela.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

NEEDS_AI_PT = ("Sem uma IA configurada o Code só consegue: mostrar a visão geral do projeto, ler um arquivo («leia src/app.py»), buscar um trecho («procure por login»), "
               "rodar os testes / o build / o linter e mostrar as mudanças do git. Para escrever, corrigir e revisar código, configure um provedor em Configuração → Provedores (nuvem, LM Studio ou modelo local).")
NEEDS_AI_EN = ("Without a configured AI, Code can only: show a project overview, read a file (\"read src/app.py\"), search for text (\"search for login\"), "
               "run the tests / build / linter and show git changes. To write, fix and review code, set up a provider in Configuration → Providers (cloud, LM Studio or a local model).")

_FILE = re.compile(r"[`'\"]?((?:[\w.-]+[/\\])*[\w.-]+\.[A-Za-z0-9]{1,8})[`'\"]?")


def lang_of(text: str, pref: str = "auto") -> str:
    pref = (pref or "auto").lower()
    if pref.startswith("pt"):
        return "pt"
    if pref.startswith("en"):
        return "en"
    return "pt" if re.search(r"[ãõçáéíóúâêôà]|\b(rod(e|ar)|leia|procure|mostre|projeto|testes?|mudan[cç]as|vis[aã]o|estrutura|corrija|crie)\b", text or "", re.I) else "en"


def build_script(goal: str) -> Optional[Dict[str, Any]]:
    g = (goal or "").strip()
    low = g.lower()
    calls: List[Dict[str, Any]] = []
    titles: List[str] = []
    if re.search(r"\b(rod(e|ar|a)|execut(e|ar|a)|run)\b.*\b(tests?|testes?)\b|\btestar\b|\bpytest\b|\bunittest\b", low):
        calls.append({"tool": "run_tests", "args": {"kind": "test"}})
        titles.append("Rodar os testes do projeto")
    elif re.search(r"\blint(er)?\b|\bformat(ar|e)?\b", low):
        calls.append({"tool": "run_tests", "args": {"kind": "lint"}})
        titles.append("Rodar o linter")
    elif re.search(r"\b(build|compil(ar|e)|compile)\b", low):
        calls.append({"tool": "run_tests", "args": {"kind": "build"}})
        titles.append("Rodar o build")
    elif re.search(r"\b(git )?(status|diff)\b|mudan[cç]as|what changed|changes\b", low):
        calls.append({"tool": "git", "args": {"args": ["status", "--short"]}})
        calls.append({"tool": "git", "args": {"args": ["diff", "--stat"]}})
        titles.append("Ver as mudanças do git")
    elif re.search(r"\b(le(r|ia)|read|mostr(e|ar)|show|abr(a|ir)|open)\b", low) and _FILE.search(g):
        path = _FILE.search(g).group(1)
        calls.append({"tool": "read_file", "args": {"path": path}})
        titles.append(f"Ler {path}")
    elif re.search(r"\b(procur(e|ar)|busc(ar|ue)|search|grep|find)\b", low):
        term = re.sub(r"^\s*(procur(e|ar)|busc(ar|ue)|search|grep|find)\s+((for|por|pelo|pela|pelos|pelas|o|a|os|as|the)\s+)?", "", g, flags=re.I).strip(" .?!`'\"“”")[:80]
        if term:
            calls.append({"tool": "search_code", "args": {"pattern": re.escape(term), "ignore_case": True, "limit": 40}})
            titles.append(f"Buscar «{term}»")
    elif re.search(r"estrutura|vis[aã]o geral|resumo|overview|structure|explain|explique|o que (é|faz)|what (is|does)", low):
        calls.append({"tool": "project_info", "args": {}})
        titles.append("Visão geral do projeto")
    if not calls:
        return None
    return {"summary": g[:300], "kind": "research", "steps": [{"title": t, "role": "researcher" if c["tool"] in ("read_file", "search_code", "project_info") else "coder"} for t, c in zip(titles, calls[:1])], "calls": calls}
