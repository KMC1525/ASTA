"""O motor de uma tarefa do Computer Use: a equipe **Planejador → Operador → Revisor → Relator** trabalhando no computador do usuário.

* **Planejador** lê o pedido (e os anexos) e escreve um roteiro curto.
* **Operador** é o único que age: a cada volta recebe a situação e devolve UMA ação do catálogo fechado (`tools.py`); o motor valida, confere os limites fixos (`guard.py`), pergunta ao
  usuário no modo Ask, executa e devolve o resultado como observação. Com o guia do especialista (arquivos, programas com tela, jogos, pesquisa, escrita) e do programa citado (Krita, OBS…).
* **Revisor** confere o resultado com evidências que o próprio motor coleta (os arquivos existem agora?) e pode mandar o Operador corrigir uma vez.
* **Relator** escreve o resumo final no idioma do usuário.

Cada agente tem **fallback determinístico**: sem IA (provedor Demo) ou com resposta inválida, as regras de `rulebased.py` e relatórios automáticos assumem; a tarefa nunca cai por culpa do modelo.
O estado inteiro vive num documento JSON (`~/.asta/computer/tasks/<id>/task.json`): é o histórico passo a passo que a tela mostra.
"""
from __future__ import annotations

import base64
import json
import platform
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..providers import ProviderError, resolve_provider
from ..util import new_id, now_iso
from . import agents as A
from . import files as F
from . import guard, osdrv, rulebased, tools as T

AGENT_LABELS = {"planner": "Planejador", "operator": "Operador", "verifier": "Revisor", "reporter": "Relator"}
FINAL = ("done", "partial", "failed", "cancelled")
OUT_LIMIT = 2500        # caracteres de resultado guardados por passo
OBS_LIMIT = 4500        # caracteres da observação enviada ao Operador


class GuiLease:
    """Tela, teclado e mouse são **um só** para o computador inteiro: com várias tarefas em paralelo, só uma por vez usa a interface gráfica (as de arquivos, pesquisa e linha de comando seguem juntas)."""

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self.owner = ""
        self.last = 0.0

    def acquire(self, task_id: str, cancelled, on_wait=None, timeout: float = 900) -> None:
        end = time.time() + timeout
        with self._cv:
            while self.owner and self.owner != task_id:
                if cancelled():
                    raise T.ToolError("cancelado")
                if time.time() > end:
                    raise T.ToolError("A tela e o teclado ficaram ocupados por outra tarefa por tempo demais.")
                if on_wait:
                    on_wait(self.owner)
                self._cv.wait(0.5)
            self.owner, self.last = task_id, time.time()

    def release(self, task_id: str) -> None:
        with self._cv:
            if self.owner == task_id:
                self.owner = ""
                self._cv.notify_all()

    def held_by(self, task_id: str) -> bool:
        return self.owner == task_id

    def idle_for(self) -> float:
        return time.time() - self.last if self.owner else 0.0


class TaskRunner:
    def __init__(self, manager: Any, doc: Dict[str, Any], images: Optional[List[dict]] = None):
        self.m = manager
        self.doc = doc
        self.input_images = images or []     # imagens anexadas ao pedido (só o Planejador as vê)
        self.rules_only = False
        self.cv = threading.Condition()
        self._cancel = threading.Event()
        self.allowed: Set[str] = set()      # classes de risco que o usuário liberou «para o resto desta tarefa»
        self.journal = F.Journal(doc["id"], doc.setdefault("journal", []))
        self.touched: List[str] = []
        self.memo: List[str] = []
        self.pending_image: Optional[Path] = None
        self.last_shot: Optional[Path] = None
        self.fail_count: Dict[str, int] = {}
        self.brain: Optional[A.Brain] = None
        self.provider: Any = None
        self.demo = False
        self.vision = False
        self.script: Optional[Dict[str, Any]] = None
        self.script_i = 0
        self.names: List[str] = []
        self.missing: Dict[str, str] = {}
        self.op_system = ""
        self.ctx: Optional[T.Context] = None
        self.settings: Dict[str, Any] = {}
        self.cfg: Dict[str, Any] = {}
        self.env: Dict[str, Any] = {}
        self.lang = "pt"
        self.turns = 0

    # ----------------------------------------------------------------- controle externo
    def cancel(self) -> None:
        self._cancel.set()
        with self.cv:
            self.cv.notify_all()

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def answer(self, approve: bool, remember: bool = False) -> bool:
        with self.cv:
            p = self.doc.get("pending")
            if not p or p.get("answer") is not None:
                return False
            p["answer"], p["remember"] = bool(approve), bool(remember)
            self.cv.notify_all()
        self._save()   # quem consulta já enxerga a pergunta como respondida (sem cartão velho na tela)
        return True

    # ----------------------------------------------------------------- estado
    def _save(self) -> None:
        self.doc["updated"] = now_iso()
        self.m.persist(self.doc)

    def _agent(self, aid: str, status: str, note: str = "") -> None:
        ags = self.doc.setdefault("agents", [])
        a = next((x for x in ags if x["id"] == aid), None)
        if a is None:
            a = {"id": aid, "label": AGENT_LABELS.get(aid, aid), "status": "pending", "note": "", "t0": 0, "t1": 0}
            ags.append(a)
        a["status"] = status
        if note:
            a["note"] = note[:300]
        if status == "running" and not a["t0"]:
            a["t0"] = time.time()
        if status in ("done", "warn", "error", "skipped"):
            a["t1"] = time.time()
        self._save()

    def _warn(self, msg: str) -> None:
        w = self.doc.setdefault("warnings", [])
        if msg not in w:
            w.append(msg)
            self.doc["warnings"] = w[-12:]

    # ----------------------------------------------------------------- preparação
    def _prepare(self) -> None:
        d = self.doc
        self.settings = self.m.store.get_settings()
        self.cfg = self.m.config()
        driver = self.m.driver
        goal = d["goal"]
        self.lang = rulebased.lang_of(goal, self.settings.get("language", "auto"))
        self.provider, info = self.m.resolve_provider(self.settings)
        self.demo = bool(info.get("demo")) or getattr(self.provider, "id", "") == "demo"
        self.vision = bool(getattr(self.provider, "vision", False))
        d["provider"] = {"id": info.get("id", ""), "label": info.get("label", ""), "model": info.get("model", ""), "vision": self.vision, "demo": self.demo}
        folders = rulebased.known_folders()
        self.env = {"os": f"{driver.label} {platform.release()}".strip(), "home": str(guard.home()), "folders": {k: str(v) for k, v in folders.items() if k != "home"},
                    "now": time.strftime("%Y-%m-%d %H:%M"), "screen": list(driver.screen_size() or [])}
        self.names, self.missing = T.available(driver, d["mode"], self.vision)
        shots = guard.data_dir() / "tasks" / d["id"] / "shots"
        self.ctx = T.Context(task_id=d["id"], settings=self.settings, journal=self.journal, driver=driver, shots_dir=shots, lang=self.lang, cancelled=self.cancelled,
                             gui_lease=self.m.gui, mode=d["mode"], ask=self._ask_yes_no, web=self._web)
        self.ctx.cfg = self.cfg
        self.brain = A.Brain(self.provider, self.cancelled, self._warn, temperature=0.3)
        self.rules_only = self.demo
        d["team"] = "rules" if self.rules_only else self.cfg["team"]
        d["tools"] = list(self.names)

    def _web(self, query: str) -> Dict[str, Any]:
        from .. import websearch

        return websearch.gather(query, self.settings, ui_lang="pt" if self.lang == "pt" else "auto")

    def _language_name(self) -> str:
        pref = str(self.settings.get("language", "auto")).lower()
        if pref.startswith("pt"):
            return "Brazilian Portuguese"
        if pref.startswith("en"):
            return "English"
        return "the same language as the user's request"

    def _system(self, agent: str, **kw: Any) -> str:
        content = "sfw" if (self.settings.get("generation") or {}).get("content") == "sfw" else "free"
        return A.system_for(agent, language=self._language_name(), os_label=self.env.get("os", ""), home=self.env.get("home", ""), content=content, mode=self.doc["mode"], goal=self.doc["goal"], **kw)

    # ----------------------------------------------------------------- aprovação (modo Ask)
    def _wait_answer(self, pend: Dict[str, Any]) -> bool:
        d = self.doc
        with self.cv:
            d["pending"] = pend
            d["status"] = "waiting"
        self._release_gui()
        self._save()
        with self.cv:
            while pend["answer"] is None and not self._cancel.is_set():
                self.cv.wait(0.5)
            ans = pend["answer"]
            d["pending"] = None
            d["status"] = "running"
        if self._cancel.is_set() and ans is None:
            raise A.Cancelled()
        if ans and pend.get("remember") and pend.get("risk"):
            self.allowed.add(pend["risk"])
        self._save()
        return bool(ans)

    def _approve(self, step: Dict[str, Any], tool: str, args: Dict[str, Any], risk: str) -> bool:
        d = T.describe(tool, args)
        pend = {"id": new_id("q_"), "kind": "action", "step": step["n"], "tool": tool, "risk": risk, "args": d["args"], "ts": time.time(), "answer": None, "remember": False}
        ans = self._wait_answer(pend)
        step["approval"] = {"asked": True, "answer": ans, "remember": bool(pend.get("remember"))}
        return ans

    def _ask_yes_no(self, question: str) -> bool:
        return self._wait_answer({"id": new_id("q_"), "kind": "question", "step": len(self.doc["steps"]), "tool": "ask_user", "risk": "read", "question": question[:400], "args": {}, "ts": time.time(), "answer": None, "remember": False})

    # ----------------------------------------------------------------- tela/teclado/mouse compartilhados
    def _take_gui(self) -> None:
        def waiting(owner: str) -> None:
            self.doc["note"] = "Esperando a tela e o teclado: outra tarefa está usando."
        self.m.gui.acquire(self.doc["id"], self.cancelled, waiting)
        self.doc["note"] = ""

    def _release_gui(self) -> None:
        self.m.gui.release(self.doc["id"])

    def _idle_gui(self) -> None:
        if self.m.gui.held_by(self.doc["id"]) and self.m.gui.idle_for() > 25:
            self._release_gui()

    # ----------------------------------------------------------------- fluxo principal
    def run(self) -> None:
        from .. import scheduler

        scheduler.set_priority(scheduler.BACKGROUND)   # a conversa que o usuário espera passa na frente (modelo local embutido)
        d = self.doc
        try:
            d["status"], d["started"] = "running", time.time()
            self._save()
            self._prepare()
            self._plan()
            outcome: Optional[Dict[str, Any]] = None
            if not d.get("blocked"):
                outcome = self._operate()
                review = self._review(outcome)
                if review and review["verdict"] != "pass" and review["fix"] and self.cfg["revisions"] > 0 and not self.rules_only and not self.cancelled() and outcome is not None:
                    self.doc["revisions"] = self.doc.get("revisions", 0) + 1
                    outcome = self._operate(feedback=review["fix"], extra=12) or outcome
                    review = self._review(outcome)
            else:
                review = None
            status = self._status(outcome, review)
            self._report(status, outcome, review)
            d["status"] = status
        except A.Cancelled:
            d["status"] = "cancelled"
            d["summary"] = d.get("summary") or A.deterministic_report(d["goal"], "cancelled", d["steps"], self._files(), None, self._undoable(), self.lang)
            self._agent("reporter", "skipped")
        except ProviderError as exc:
            d["status"], d["error"] = "failed", str(exc)
            d["summary"] = ("A IA não respondeu: " if self.lang == "pt" else "The AI did not answer: ") + str(exc)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            d["status"], d["error"] = "failed", str(exc) or exc.__class__.__name__
            d["summary"] = ("Erro inesperado: " if self.lang == "pt" else "Unexpected error: ") + (str(exc) or exc.__class__.__name__)
        finally:
            self._release_gui()
            d["pending"], d["note"], d["now"] = None, "", ""
            d["finished"] = time.time()
            for p in d.get("plan", {}).get("steps", []):
                if p["status"] in ("running",):
                    p["status"] = "done" if d["status"] in ("done", "partial") else "skipped"
            for a in d.get("agents", []):
                if a["status"] in ("running", "pending"):
                    a["status"] = "skipped"
            self._save()
            self.m.finished(self)

    # ----- 1. Planejador
    def _plan(self) -> None:
        d = self.doc
        self._agent("planner", "running")
        goal = d["goal"]
        if self.rules_only:
            self.script = rulebased.build_script(goal)
            if not self.script:
                d["blocked"] = rulebased.NEEDS_AI_PT if self.lang == "pt" else rulebased.NEEDS_AI_EN
                d["plan"] = {"summary": goal[:300], "kind": "mixed", "needs_gui": False, "steps": [], "assumptions": [], "risks": [], "blocked": d["blocked"]}
                self._agent("planner", "error", "sem IA")
                return
            plan = A.normalize_plan({"summary": self.script["summary"], "kind": self.script["kind"], "steps": self.script["steps"]}, goal)
            d["plan"] = plan
            self._agent("planner", "done", "regras (sem IA)")
        elif self.cfg["team"] == "fast":
            d["plan"] = A.fallback_plan(goal)
            self._agent("planner", "skipped", "equipe rápida")
        else:
            payload = {"goal": goal, "attachments": d.get("inputs_digest", ""), "inputs": d.get("inputs", []), "environment": self.env, "tools_available": self.names, "tools_unavailable": self.missing,
                       "vision": self.vision, "mode": d["mode"],
                       "known_apps": [a["name"] for a in self.m.driver.apps()[:60]] if self.m.driver.capabilities()["apps"]["ok"] else [],
                       "known_games": [g["name"] for g in self._games()[:40]]}
            obj = self.brain.ask("planner", self._system("planner", tools="", unavailable=""), A.PLAN_INSTR, payload, images=self.input_images or None, max_tokens=1500)
            plan = A.normalize_plan(obj, goal) if obj else A.fallback_plan(goal)
            if plan["blocked"]:
                d["blocked"] = plan["blocked"]
            elif not plan["steps"]:
                plan = A.fallback_plan(goal)
            d["plan"] = plan
            self._agent("planner", "warn" if obj is None else "done", "" if obj is not None else "método automático")
        d["plan_ready"] = True
        self._save()

    def _games(self) -> List[dict]:
        try:
            return self.m.driver.games([x for x in self.cfg.get("game_dirs", []) if isinstance(x, str)])
        except Exception:  # noqa: BLE001
            return []

    # ----- 2. Operador
    def _operate(self, feedback: str = "", extra: int = 0) -> Optional[Dict[str, Any]]:
        d = self.doc
        plan = d["plan"]
        if not self.op_system and not self.rules_only:
            uses_gui = bool(plan.get("needs_gui")) or any(n in self.names for n in ("screenshot",)) and plan.get("kind") in ("apps", "games", "writing", "mixed")
            self.op_system = self._system("operator", kind=plan.get("kind", "mixed"), tools=T.catalog_text(self.names),
                                          unavailable="\n".join(f"- {n}: {w}" for n, w in self.missing.items()), uses_gui=uses_gui)
        self._agent("operator", "running", "")
        max_turns = self.cfg["max_steps"] + extra
        local_turns, bad = 0, 0
        while True:
            if self.cancelled():
                raise A.Cancelled()
            if local_turns >= max_turns:
                self._agent("operator", "warn", "limite de passos")
                return None
            local_turns += 1
            self.turns += 1
            self._idle_gui()
            if self.rules_only:
                turn = self._scripted_turn()
            else:
                payload = self._turn_payload(feedback, max_turns - local_turns)
                images = self._take_image()
                obj = self.brain.ask("operator", self.op_system, A.TURN_INSTR, payload, images=images, max_tokens=1600)
                turn = A.normalize_turn(obj)
            if turn["kind"] == "bad":
                bad += 1
                self._record_reject(turn.get("why", "resposta inválida"))
                if bad >= 4:
                    self._agent("operator", "error", "formato inválido")
                    return {"success": False, "summary": "A IA não conseguiu responder no formato esperado." if self.lang == "pt" else "The AI could not answer in the expected format."}
                continue
            bad = 0
            if turn.get("memo"):
                self.memo = (self.memo + [turn["memo"]])[-14:]
            if turn["kind"] == "finish":
                self._mark_plan(turn.get("step"), final=True, ok=turn["success"])
                self._agent("operator", "done" if turn["success"] else "warn", turn.get("summary", "")[:200])
                return {"success": turn["success"], "summary": turn.get("summary", "")}
            if self._execute(turn) == "stop":
                self._agent("operator", "error", "repetiu a mesma ação com erro")
                return {"success": False, "summary": "Parei porque a mesma ação falhou várias vezes seguidas." if self.lang == "pt" else "I stopped because the same action kept failing."}

    def _scripted_turn(self) -> Dict[str, Any]:
        acts = (self.script or {}).get("actions", [])
        if self.script_i >= len(acts):
            n_err = sum(1 for s in self.doc["steps"] if s["status"] in ("error", "denied"))
            ok = n_err == 0
            return {"kind": "finish", "success": ok, "summary": "", "step": acts[-1]["step"] if acts else "", "thought": "", "memo": ""}
        a = acts[self.script_i]
        self.script_i += 1
        return {"kind": "action", "tool": a["tool"], "args": a["args"], "thought": "", "step": a["step"], "memo": ""}

    def _turn_payload(self, feedback: str, left: int) -> Dict[str, Any]:
        steps = self.doc["steps"]
        hist = [{"n": s["n"], "step": s.get("plan_step", ""), "tool": s["tool"], "args": _short(s["args"]), "status": s["status"], "result": A.trim_obs(s.get("output", ""), 420)} for s in steps[-10:]]
        last = steps[-1] if steps else None
        return {"goal": self.doc["goal"], "plan": [{"id": p["id"], "title": p["title"], "status": p["status"]} for p in self.doc["plan"]["steps"]], "inputs": self.doc.get("inputs", []),
                "environment": {"os": self.env["os"], "home": self.env["home"], "folders": self.env["folders"], "now": time.strftime("%Y-%m-%d %H:%M")},
                "history": hist[:-1] if last else hist, "memo": self.memo, "last_observation": ({"n": last["n"], "tool": last["tool"], "status": last["status"], "result": A.trim_obs(last.get("output_full", last.get("output", "")), OBS_LIMIT)} if last else None),
                "vision": self.vision, "mode": self.doc["mode"], "review_feedback": feedback, "turn": self.turns, "turns_left": left,
                "assumptions": self.doc["plan"].get("assumptions", [])}

    def _take_image(self) -> Optional[List[dict]]:
        p, self.pending_image = self.pending_image, None
        if not p or not self.vision or not p.exists():
            return None
        try:
            media = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
            return [{"media_type": media, "data": base64.b64encode(p.read_bytes()).decode("ascii")}]
        except OSError:
            return None

    def _mark_plan(self, step_id: Optional[str], final: bool = False, ok: bool = True) -> None:
        steps = self.doc["plan"]["steps"]
        if final:
            for p in steps:
                p["status"] = "done" if ok else ("done" if p["status"] == "done" else "skipped")
            return
        idx = next((i for i, p in enumerate(steps) if p["id"] == step_id), None)
        if idx is None:
            return
        for i, p in enumerate(steps):
            if i < idx and p["status"] in ("pending", "running"):
                p["status"] = "done"
        if steps[idx]["status"] == "pending":
            steps[idx]["status"] = "running"

    def _new_step(self, turn: Dict[str, Any], tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        tl = T.TOOLS.get(tool)
        step = {"n": len(self.doc["steps"]) + 1, "plan_step": turn.get("step", ""), "thought": turn.get("thought", ""), "tool": tool, "args": _short(args), "risk": tl.risk if tl else "run",
                "status": "running", "output": "", "t0": time.time(), "t1": 0, "approval": None, "shot": ""}
        self.doc["steps"].append(step)
        self.doc["now"] = T.describe(tool, args)["tool"]
        if turn.get("step"):
            self._mark_plan(turn["step"])
        self._save()
        return step

    def _record_reject(self, why: str) -> None:
        step = {"n": len(self.doc["steps"]) + 1, "plan_step": "", "thought": "", "tool": "—", "args": {}, "risk": "read", "status": "error", "output": f"Resposta do Operador rejeitada: {why}",
                "t0": time.time(), "t1": time.time(), "approval": None, "shot": ""}
        self.doc["steps"].append(step)
        self._save()

    def _execute(self, turn: Dict[str, Any]) -> str:
        d = self.doc
        tool, raw_args = turn["tool"], turn.get("args") or {}
        step = self._new_step(turn, tool, raw_args if isinstance(raw_args, dict) else {})
        tl = T.TOOLS.get(tool)
        key = tool + json.dumps(raw_args, sort_keys=True, default=str)[:300]

        def fail(msg: str, status: str = "error") -> str:
            step.update(status=status, output=msg, output_full=msg, t1=time.time())
            self.fail_count[key] = self.fail_count.get(key, 0) + (1 if status == "error" else 0)
            if status == "error" and self.fail_count[key] == 2:
                step["output_full"] = msg + "\n(Esta mesma ação já falhou 2 vezes: mude de abordagem.)"
            self._save()
            return "stop" if self.fail_count.get(key, 0) >= 4 else "ok"

        if tl is None or tool not in self.names:
            why = self.missing.get(tool) or "ferramenta desconhecida"
            return fail(f"A ferramenta «{tool}» não está disponível ({why}). Ferramentas válidas: {', '.join(self.names)}.")
        try:
            args = T.coerce(tl, raw_args)
        except T.ToolError as exc:
            return fail(str(exc))
        step["args"] = _short(args)
        if T.needs_approval(tool, d["mode"], self.cfg["ask_for"], self.allowed):
            if not self._approve(step, tool, args, tl.risk):
                return fail("NEGADO pelo usuário. Não repita esta ação nem tente contorná-la: escolha outro caminho ou finalize explicando.", "denied")
        try:
            if tl.gui:
                self._take_gui()
            res = tl.fn(self.ctx, args)
        except A.Cancelled:
            raise
        except T.ToolError as exc:
            if str(exc) == "cancelado":
                raise A.Cancelled() from None
            return fail(str(exc))
        except guard.Blocked as exc:
            return fail("BLOQUEADO pelo ASTA: " + str(exc))
        except (F.FileError, osdrv.DriverError) as exc:
            return fail(str(exc))
        except OSError as exc:
            return fail(f"Erro do sistema: {exc.strerror or exc}")
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return fail(f"Erro inesperado em {tool}: {exc}")
        out = res.output or ("(sem saída)" if res.ok else "(falhou)")
        step.update(status="ok" if res.ok else "error", output=A.trim_obs(out, OUT_LIMIT), output_full=A.trim_obs(out, OBS_LIMIT), t1=time.time())
        if not res.ok:
            self.fail_count[key] = self.fail_count.get(key, 0) + 1
        for p in res.paths:
            try:
                rp = str(guard.resolve(p))
            except guard.Blocked:
                continue
            if rp not in self.touched:
                self.touched.append(rp)
        if res.meta.get("shot"):
            step["shot"] = res.meta["shot"]
        if res.image:
            self.pending_image = res.image
            self.last_shot = res.image
        if tl.gui:
            self.m.gui.last = time.time()
        self._save()
        return "stop" if self.fail_count.get(key, 0) >= 4 else "ok"

    # ----- 3. Revisor
    def _files(self) -> List[str]:
        out = list(self.touched)
        for e in self.journal.entries:
            for k in ("path", "dst"):
                p = e.get(k)
                if p and p not in out and e.get("op") in ("create", "move", "copy", "mkdir"):
                    out.append(p)
        return out[:60]

    def _undoable(self) -> bool:
        return any(not e.get("undone") for e in self.journal.entries)

    def _evidence(self) -> List[dict]:
        ev = []
        for p in self._files()[:40]:
            try:
                pp = Path(p)
                ev.append({"path": p, "exists": pp.exists(), "kind": "folder" if pp.is_dir() else "file", "size": pp.stat().st_size if pp.is_file() else None})
            except OSError:
                ev.append({"path": p, "exists": False})
        return ev

    def _review(self, outcome: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        d = self.doc
        if d.get("blocked"):
            return None
        self._agent("verifier", "running")
        evidence = self._evidence()
        missing = [e["path"] for e in evidence if not e["exists"] and any(j.get("op") in ("create", "mkdir") and j.get("path") == e["path"] and not j.get("undone") for j in self.journal.entries)]
        denied = [s for s in d["steps"] if s["status"] == "denied"]
        errors = [s for s in d["steps"] if s["status"] == "error"]
        det = {"verdict": "pass", "score": 9, "issues": [], "fix": ""}
        if outcome is None:
            det.update(verdict="partial", score=4, issues=["A tarefa passou do limite de passos sem concluir."])
        elif not outcome["success"]:
            det.update(verdict="fail" if not any(s["status"] == "ok" for s in d["steps"]) else "partial", score=3, issues=[outcome.get("summary") or "O Operador disse que não conseguiu."])
        if missing:
            det.update(verdict="fail", score=2, issues=det["issues"] + [f"Não existe mais ou não foi criado: {m}" for m in missing[:4]], fix="Crie de novo o que está faltando e confira com list_dir.")
        if denied and det["verdict"] == "pass":
            det.update(verdict="partial", score=6, issues=det["issues"] + [f"{len(denied)} ação(ões) foram negadas pelo usuário."])
        if self.rules_only or self.cfg["team"] == "fast" or outcome is None:
            d["review"] = det
            self._agent("verifier", "skipped" if self.rules_only or self.cfg["team"] == "fast" else "done", det["verdict"])
            self._save()
            return det
        payload = {"goal": d["goal"], "plan": [{"id": p["id"], "title": p["title"], "status": p["status"]} for p in d["plan"]["steps"]], "claimed": outcome.get("summary", ""),
                   "steps": [{"n": s["n"], "tool": s["tool"], "args": _short(s["args"]), "status": s["status"], "result": A.trim_obs(s.get("output", ""), 300)} for s in d["steps"][-40:]],
                   "evidence": evidence, "denied": [{"tool": s["tool"], "args": _short(s["args"])} for s in denied], "errors": len(errors)}
        images = None
        if self.vision and self.last_shot and self.last_shot.exists():
            self.pending_image = self.last_shot
            images = self._take_image()
        obj = self.brain.ask("verifier", self._system("verifier"), A.REVIEW_INSTR, payload, images=images, max_tokens=900)
        rev = A.normalize_review(obj)
        if rev is None:
            rev = det
            self._agent("verifier", "warn", "método automático")
        else:
            rank = {"pass": 0, "partial": 1, "fail": 2}
            if rank[det["verdict"]] > rank[rev["verdict"]]:   # as evidências do motor (arquivo sumiu, ação negada, Operador desistiu) vencem um «tudo certo» sem base
                rev = {**det, "issues": det["issues"] + rev["issues"], "fix": det["fix"] or rev["fix"]}
            self._agent("verifier", "done", rev["verdict"])
        d["review"] = rev
        self._save()
        return rev

    # ----- 4. Relator
    def _status(self, outcome: Optional[Dict[str, Any]], review: Optional[Dict[str, Any]]) -> str:
        d = self.doc
        if d.get("blocked"):
            return "failed"
        ok_steps = any(s["status"] == "ok" for s in d["steps"])
        if outcome is None:
            return "partial" if ok_steps else "failed"
        if not outcome["success"]:
            return "partial" if ok_steps and review and review["verdict"] != "fail" else "failed"
        if review and review["verdict"] == "fail":
            return "failed" if not ok_steps else "partial"
        if review and review["verdict"] == "partial":
            return "partial"
        return "done"

    def _report(self, status: str, outcome: Optional[Dict[str, Any]], review: Optional[Dict[str, Any]]) -> None:
        d = self.doc
        files = self._files()
        hint = (outcome or {}).get("summary", "") if (self.rules_only or self.cfg["team"] == "fast") else ""
        if d.get("blocked"):
            d["summary"] = d["blocked"]
            self._agent("reporter", "skipped")
            return
        self._agent("reporter", "running")
        text = ""
        if not self.rules_only and self.cfg["team"] != "fast":
            payload = {"goal": d["goal"], "status": status, "steps": [{"tool": s["tool"], "args": _short(s["args"]), "status": s["status"], "result": A.trim_obs(s.get("output", ""), 200)} for s in d["steps"][-40:]],
                       "files_touched": files, "denied": [{"tool": s["tool"]} for s in d["steps"] if s["status"] == "denied"], "review": review, "operator_summary": (outcome or {}).get("summary", ""),
                       "trash_note": any(e.get("op") == "trash" for e in self.journal.entries), "undo_available": self._undoable()}
            obj = self.brain.ask("reporter", self._system("reporter"), A.REPORT_INSTR, payload, max_tokens=900)
            if isinstance(obj, dict) and str(obj.get("summary") or "").strip() and not A.looks_like_json_noise(str(obj.get("summary"))):
                text = str(obj["summary"]).strip()
                steps_next = [str(x) for x in (obj.get("next_steps") or []) if str(x).strip()][:3]
                if steps_next:
                    text += "\n\n" + "\n".join(f"- {x}" for x in steps_next)
        if not text:
            text = A.deterministic_report(d["goal"], status, d["steps"], files, review, self._undoable(), self.lang, hint)
            self._agent("reporter", "warn" if not self.rules_only and self.cfg["team"] != "fast" else "done", "" if self.rules_only else "relatório automático")
        else:
            self._agent("reporter", "done")
        d["summary"] = text[:6000]


def _short(args: Any) -> Any:
    if not isinstance(args, dict):
        return {}
    out = {}
    for k, v in args.items():
        if isinstance(v, str):
            out[k] = v if len(v) <= 600 else v[:600] + f"… (+{len(v) - 600})"
        elif isinstance(v, list):
            out[k] = [str(x)[:200] for x in v[:30]]
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)[:200]
    return out
