"""Os agentes do Computer Use: chamadas à IA com saída em JSON **validada** e fallback determinístico para cada um.

Planejador → Operador (uma ação por vez) → Revisor → Relator. A IA só devolve dados (`{"tool": …, "args": …}`); quem valida e executa é o motor (`engine.py`).
Resposta inválida depois do reparo = o agente usa o método automático (regras) e registra o aviso: a tarefa não cai por culpa do modelo. Erro de rede/credencial do provedor falha a tarefa com mensagem clara.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..agents.llm import call_json
from ..providers import ProviderError
from . import promptlib

TRANSIENT = (408, 409, 425, 429, 500, 502, 503, 504, 529)
KINDS = ("files", "apps", "games", "research", "writing", "mixed")


class Cancelled(Exception):
    pass


class Brain:
    """Liga os agentes ao provedor escolhido: repete em erro passageiro, respeita o cancelamento e anota os avisos."""

    def __init__(self, provider: Any, cancelled: Callable[[], bool], warn: Callable[[str], None], temperature: float = 0.3):
        self.provider, self.cancelled, self.warn, self.temperature = provider, cancelled, warn, temperature
        self.calls = 0

    def ask(self, agent: str, system: str, instruction: str, payload: Dict[str, Any], *, images: Optional[List[dict]] = None, max_tokens: int = 1800) -> Optional[Dict[str, Any]]:
        """Chama a IA e devolve o objeto JSON, ou None se ela não conseguiu devolver um JSON utilizável (o chamador usa o fallback)."""
        last: Optional[Exception] = None
        for attempt in range(3):
            if self.cancelled():
                raise Cancelled()
            try:
                self.calls += 1
                obj, _ = call_json(self.provider, system, instruction, payload, images=images, temperature=self.temperature, max_tokens=max_tokens, attempts=2, cancelled=self.cancelled)
                return obj
            except ProviderError as exc:
                if str(exc) == "cancelado":
                    raise Cancelled() from None
                last = exc
                if exc.status in TRANSIENT and attempt < 2:
                    for _ in range(6 * (attempt + 1)):   # espera cancelável
                        if self.cancelled():
                            raise Cancelled()
                        time.sleep(0.5)
                    continue
                raise
            except ValueError as exc:   # JSON inválido mesmo depois do reparo
                last = exc
                break
        self.warn(f"{agent}: a IA não devolveu um JSON válido ({str(last)[:120]})")
        return None


# --------------------------------------------------------------------------- normalizadores


def _s(v: Any, n: int = 400) -> str:
    return str(v if v is not None else "").strip()[:n]


def _list(v: Any, n: int = 12, m: int = 300) -> List[str]:
    return [_s(x, m) for x in v if _s(x, m)][:n] if isinstance(v, list) else []


def normalize_plan(obj: Optional[Dict[str, Any]], goal: str) -> Dict[str, Any]:
    obj = obj if isinstance(obj, dict) else {}
    steps = []
    for i, st in enumerate(obj.get("steps") if isinstance(obj.get("steps"), list) else [], 1):
        if isinstance(st, str):
            st = {"title": st}
        if not isinstance(st, dict) or not _s(st.get("title"), 200):
            continue
        steps.append({"id": f"s{len(steps) + 1}", "title": _s(st.get("title"), 200), "tools": _list(st.get("tools"), 6, 40), "done_when": _s(st.get("done_when"), 240), "status": "pending"})
        if len(steps) >= 10:
            break
    kind = _s(obj.get("kind"), 20).lower()
    return {"summary": _s(obj.get("summary"), 300) or _s(goal, 300), "kind": kind if kind in KINDS else "mixed", "needs_gui": bool(obj.get("needs_gui")), "steps": steps,
            "assumptions": _list(obj.get("assumptions"), 6), "risks": _list(obj.get("risks"), 6), "blocked": _s(obj.get("blocked"), 400)}


def fallback_plan(goal: str) -> Dict[str, Any]:
    return {"summary": _s(goal, 300), "kind": "mixed", "needs_gui": False, "assumptions": [], "risks": [], "blocked": "",
            "steps": [{"id": "s1", "title": _s(goal, 200) or "Executar o pedido", "tools": [], "done_when": "", "status": "pending"}]}


def normalize_turn(obj: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Saída do Operador → {"kind": "action"|"finish"|"bad", …}. Aceita os formatos que modelos pequenos costumam devolver."""
    if not isinstance(obj, dict):
        return {"kind": "bad", "why": "resposta vazia"}
    thought, step, memo = _s(obj.get("thought"), 400), _s(obj.get("step"), 12), _s(obj.get("memo"), 240)
    fin = obj.get("finish")
    if isinstance(fin, dict) or obj.get("done") is True and not obj.get("action"):
        fin = fin if isinstance(fin, dict) else {"success": obj.get("success", True), "summary": obj.get("summary", "")}
        return {"kind": "finish", "success": fin.get("success") is not False, "summary": _s(fin.get("summary"), 1500), "thought": thought, "step": step, "memo": memo}
    act = obj.get("action")
    if isinstance(act, str):
        act = {"tool": act, "args": obj.get("args") or {}}
    if not isinstance(act, dict) and (obj.get("tool") or obj.get("name")):
        act = {"tool": obj.get("tool") or obj.get("name"), "args": obj.get("args") or obj.get("arguments") or {}}
    if isinstance(act, dict):
        tool = _s(act.get("tool") or act.get("name"), 40)
        if tool == "finish":
            a = act.get("args") if isinstance(act.get("args"), dict) else {}
            return {"kind": "finish", "success": a.get("success") is not False, "summary": _s(a.get("summary"), 1500), "thought": thought, "step": step, "memo": memo}
        if tool:
            args = act.get("args") if isinstance(act.get("args"), dict) else (act.get("arguments") if isinstance(act.get("arguments"), dict) else {})
            return {"kind": "action", "tool": tool, "args": args, "thought": thought, "step": step, "memo": memo}
    return {"kind": "bad", "why": "nem «action» nem «finish» na resposta"}


def normalize_review(obj: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return None
    verdict = _s(obj.get("verdict"), 12).lower()
    if verdict not in ("pass", "partial", "fail"):
        return None
    try:
        score = max(0, min(10, int(float(obj.get("score", 7 if verdict == "pass" else 4)))))
    except (TypeError, ValueError):
        score = 7 if verdict == "pass" else 4
    return {"verdict": verdict, "score": score, "issues": _list(obj.get("issues"), 8), "fix": _s(obj.get("fix"), 500)}


# --------------------------------------------------------------------------- chamadas


def system_for(agent: str, *, language: str, os_label: str, home: str, content: str, mode: str, kind: str = "mixed", goal: str = "", tools: str = "", unavailable: str = "", uses_gui: bool = False) -> str:
    return promptlib.compose(agent, language=language, os_label=os_label, home=home, content=content, mode=mode, kind=kind, goal=goal, tools=tools, unavailable=unavailable, uses_gui=uses_gui)


PLAN_INSTR = ("Write the plan for the user's goal in INPUT_JSON.goal. Output JSON: "
              '{"summary": str, "kind": "files|apps|games|research|writing|mixed", "needs_gui": bool, "steps": [{"id": "s1", "title": str, "tools": [str], "done_when": str}], "assumptions": [str], "risks": [str], "blocked": ""}')
TURN_INSTR = ("Decide the single next action (or finish) for the goal in INPUT_JSON. Output JSON: "
              '{"thought": str, "step": "s1", "action": {"tool": str, "args": {}} | null, "finish": null | {"success": bool, "summary": str}, "memo": ""}')
REVIEW_INSTR = ("Check whether the goal in INPUT_JSON.goal was really reached, using INPUT_JSON.evidence. Output JSON: "
                '{"verdict": "pass|partial|fail", "score": 0-10, "issues": [str], "fix": str}')
REPORT_INSTR = ('Write the final message for the user from INPUT_JSON. Output JSON: {"summary": str, "next_steps": [str]}')


def trim_obs(text: str, limit: int) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    head = int(limit * 0.6)
    return text[:head] + f"\n… ({len(text) - limit} caracteres omitidos) …\n" + text[-(limit - head):]


def deterministic_report(goal: str, status: str, steps: List[dict], files: List[str], review: Optional[dict], undo_available: bool, lang: str, summary_hint: str = "") -> str:
    pt = lang == "pt"
    ok = [s for s in steps if s.get("status") == "ok"]
    denied = [s for s in steps if s.get("status") == "denied"]
    bad = [s for s in steps if s.get("status") == "error"]
    head = {"done": ("Pronto.", "Done."), "partial": ("Fiz uma parte do pedido.", "I did part of the request."), "failed": ("Não consegui concluir o pedido.", "I could not finish the request."),
            "cancelled": ("A tarefa foi cancelada.", "The task was cancelled.")}.get(status, ("Terminei.", "Finished."))[0 if pt else 1]
    lines = [head]
    if summary_hint:
        lines.append(summary_hint)
    if ok:
        lines.append((f"{len(ok)} ação(ões) executada(s) com sucesso." if pt else f"{len(ok)} action(s) completed."))
    if files:
        more = (f"\n… (+{len(files) - 8})" if len(files) > 8 else "")
        lines.append(("Arquivos e pastas envolvidos:" if pt else "Files and folders involved:") + "\n" + "\n".join(f"- {f}" for f in files[:8]) + more)
    if denied:
        lines.append(f"{len(denied)} ação(ões) você negou." if pt else f"You denied {len(denied)} action(s).")
    if bad and status != "done":
        lines.append((f"Último erro: {bad[-1].get('output', '')[:200]}" if pt else f"Last error: {bad[-1].get('output', '')[:200]}"))
    if review and review.get("issues") and status != "done":
        lines.append(("Pendências: " if pt else "Open issues: ") + "; ".join(review["issues"][:3]))
    if undo_available:
        lines.append("Você pode desfazer as mudanças em arquivos pelo botão «Desfazer»." if pt else "You can undo the file changes with the Undo button.")
    return "\n".join(lines)


def looks_like_json_noise(s: str) -> bool:
    return bool(re.match(r"^\s*[{\[]", s or ""))
