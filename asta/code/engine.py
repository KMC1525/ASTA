"""O motor de uma execução do Code: a equipe **Planejador → Trabalhadores (até 8 ao mesmo tempo) → Testes → Revisor → Relator** trabalhando no projeto da sessão.

* **Planejador** lê o pedido (texto + anexos multimodais), a visão geral do projeto e a conversa até aqui, e escreve um plano curto: tarefas com papel, arquivos prováveis e dependências.
* **Trabalhadores** executam as tarefas **em paralelo** (até `agents`, no máximo 8): cada um é um laço *observar → agir → conferir* com **uma ação por vez** do catálogo fechado (`tools.py`); o motor valida,
  confere os limites fixos (`guard.py`), pergunta ao usuário no modo Ask e só então executa. Duas tarefas que mexem nos mesmos arquivos nunca rodam juntas.
* **Testes:** o próprio motor roda os testes/build/lint do projeto (sem depender do que o agente diz) e guarda a saída como evidência.
* **Revisor** confere o diff e as evidências contra o pedido; se achar problema (ou os testes falharem) e ainda houver rodadas de correção (nível de esforço), um agente corrige e tudo é conferido de novo.
* **Publicação** (commit/push/PR/release, se o usuário pediu) só acontece **depois** de testes e revisão sem problema.
* **Relator** escreve o resumo final no idioma do usuário.

Cada agente tem **fallback determinístico**: sem IA (provedor Demo) ou com resposta inválida, as regras de `rulebased.py` e relatórios automáticos assumem; a sessão nunca cai por culpa do modelo.
O estado vive no documento JSON da sessão (`~/.asta/code/sessions/<id>/session.json`): é o que a tela mostra, passo a passo.
"""
from __future__ import annotations

import base64
import json
import platform
import re
import shutil
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..providers import ProviderError
from ..providers import thinking as think
from ..util import new_id, now_iso
from . import agents as A
from . import efforts, guard, langs, promptlib, rulebased, tools as T
from .workspace import Workspace

AGENT_LABELS = {"planner": "Planejador", "reviewer": "Revisor", "reporter": "Relator", "tests": "Testes", "engine": "Motor"}
FINAL = ("done", "partial", "failed", "cancelled")
OUT_LIMIT = 2500
MUTATING = {"write_file", "edit_file", "delete_path", "make_dir", "move", "copy", "run_command", "run_tests", "install_packages", "write_system_prompts"}
UNCLEAR_RE = re.compile(r"clare[zs]|ambig|intenç|intent\b|unclear|not clear|esclarec|clarif|exat[ao]|specific|especific|nova seção ou|which one|qual dos", re.I)   # «falta de clareza», «ambíguo», «unclear»…
MAX_AGENTS = 8


def _overlap(a: List[str], b: List[str]) -> bool:
    for x in a:
        for y in b:
            x2, y2 = x.strip("/").lower(), y.strip("/").lower()
            if x2 and y2 and (x2 == y2 or x2.startswith(y2 + "/") or y2.startswith(x2 + "/")):
                return True
    return False


def _short_args(args: Dict[str, Any], n: int = 160) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (args or {}).items():
        out[k] = (v[:n] + "…") if isinstance(v, str) and len(v) > n else ([str(x)[:80] for x in v[:8]] if isinstance(v, list) else v)
    return out


class Runner:
    def __init__(self, manager: Any, doc: Dict[str, Any], digest: str = "", images: Optional[List[dict]] = None):
        self.m = manager
        self.doc = doc
        self.run: Dict[str, Any] = doc["run"]
        self.digest, self.input_images = digest, images or []
        self.lock = threading.RLock()
        self.cv = threading.Condition(self.lock)
        self.sched = threading.Condition()
        self._cancel = threading.Event()
        self.allowed: Set[str] = set(doc.get("allowed") or [])
        self.settings: Dict[str, Any] = {}
        self.cfg: Dict[str, Any] = {}
        self.prof: Dict[str, Any] = {}
        self.lang = "pt"
        self.env: Dict[str, Any] = {}
        self.names: List[str] = []
        self.missing: Dict[str, str] = {}
        self.ws: Optional[Workspace] = None
        self.ctx: Optional[T.Context] = None
        self.brain: Optional[A.Brain] = None
        self.provider: Any = None
        self.info: Dict[str, Any] = {}
        self.demo = False
        self.vision = False
        self.project: Dict[str, Any] = {}
        self.n_agents = 4
        self.tail: List[Dict[str, Any]] = []
        self.board: Dict[str, Dict[str, Any]] = {}
        self.step_n = 0
        self.script: Optional[Dict[str, Any]] = None

    # ----------------------------------------------------------------- controle externo
    def cancel(self) -> None:
        self._cancel.set()
        with self.cv:
            self.cv.notify_all()

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def answer(self, qid: str, approve: bool, remember: bool = False) -> bool:
        with self.cv:
            pend = [p for p in self.run.get("pendings", []) if p.get("answer") is None and (not qid or p["id"] == qid)]
            if not pend:
                return False
            pend[0]["answer"], pend[0]["remember"] = bool(approve), bool(remember)
            self.cv.notify_all()
        self._save()
        return True

    # ----------------------------------------------------------------- estado
    def _save(self) -> None:
        with self.lock:
            self.doc["updated"] = now_iso()
            self.m.persist(self.doc)

    def _agent(self, aid: str, status: str, note: str = "", **extra: Any) -> None:
        with self.lock:
            ags = self.run.setdefault("agents", [])
            a = next((x for x in ags if x["id"] == aid), None)
            if a is None:
                a = {"id": aid, "label": AGENT_LABELS.get(aid) or (f"Agente {aid[1:]}" if aid.startswith("w") else aid), "status": "pending", "note": "", "role": "", "step": "", "t0": 0, "t1": 0}
                ags.append(a)
            a["status"] = status
            a.update(extra)
            if note is not None:
                a["note"] = note[:300]
            if status == "running" and not a["t0"]:
                a["t0"] = time.time()
            if status in ("done", "warn", "error", "skipped", "idle"):
                a["t1"] = time.time()
        self._save()

    def _warn(self, msg: str) -> None:
        with self.lock:
            w = self.run.setdefault("warnings", [])
            if msg not in w:
                w.append(msg)
                self.run["warnings"] = w[-12:]

    # ----------------------------------------------------------------- preparação
    def _prepare(self) -> None:
        d, r = self.doc, self.run
        self.settings = self.m.store.get_settings()
        self.cfg = self.m.config()
        self.prof = efforts.profile(d.get("effort") or self.cfg["effort"])
        self.n_agents = max(1, min(int(d.get("agents") or self.cfg["agents"]), MAX_AGENTS))
        self.lang = rulebased.lang_of(r["goal"], self.settings.get("language", "auto"))
        self.provider, self.info = self.m.provider_for(self.settings, d)
        self.demo = bool(self.info.get("demo")) or getattr(self.provider, "id", "") == "demo"
        self.vision = bool(getattr(self.provider, "vision", False))
        self._tune(self.provider)
        r["provider"] = {"id": self.info.get("id", ""), "label": self.info.get("label", ""), "model": self.info.get("model", ""), "vision": self.vision, "demo": self.demo}
        wsd = d["workspace"]
        root = guard.check_root(wsd["path"])
        sdir = self.m.session_dir(d["id"])
        self.ws = Workspace(root, sdir, d.setdefault("journal", []), extra_read=[sdir / "inputs"])
        self.ws.run = r["id"]
        gh = self.m.github(self.settings)
        repo = wsd.setdefault("repo", {})
        self.ctx = T.Context(sid=d["id"], settings=self.settings, cfg=self.cfg, ws=self.ws, inputs_dir=sdir / "inputs", scratch_dir=sdir / "scratch", lang=self.lang, cancelled=self.cancelled,
                             ask=self._ask_yes_no, mode=d["mode"], vision=self.vision, web=self._web, llm_text=None if self.demo else self._llm_text, gh=gh, repo=repo,
                             on_repo=lambda rp: self._save(), hf_token=(self.settings.get("hf") or {}).get("token", ""))
        info = {"mode": d["mode"], "vision": self.vision, "git": bool(shutil.which("git")), "token": bool(gh.token), "repo": repo, "android": T.IS_ANDROID, "editor": bool(T._editor("auto")[1])}
        self.names, self.missing = T.available(info)
        self.project = T.project_summary(self.ctx)
        self.env = {"os": f"{platform.system()} {platform.release()}".strip(), "now": time.strftime("%Y-%m-%d %H:%M"), "root": root.name}
        r["team"] = "rules" if self.demo else "full"
        r["tools"] = list(self.names)
        r["effort"] = self.prof["id"]
        r["agents_n"] = self.n_agents
        self.brain = A.Brain(self.provider, self.cancelled, self._warn, temperature=0.3)

    def _tune(self, provider: Any) -> None:
        sup = think.support(self.info.get("id", ""), self.info.get("model", ""))
        try:
            provider.thinking = self.prof["thinking"] if sup.get("supported") else "off"
        except AttributeError:
            pass

    def _web(self, query: str) -> Dict[str, Any]:
        from .. import websearch

        return websearch.gather(query, self.settings, ui_lang="pt" if self.lang == "pt" else "auto")

    def _llm_text(self, system: str, user: str, max_tokens: int = 4000) -> str:
        if self.cancelled():
            raise A.Cancelled()
        out = self.provider.chat([{"role": "user", "content": user}], system=system, temperature=0.4, max_tokens=max_tokens)
        return str(out or "")

    def _language_name(self) -> str:
        pref = str(self.settings.get("language", "auto")).lower()
        if pref.startswith("pt"):
            return "Brazilian Portuguese"
        if pref.startswith("en"):
            return "English"
        return "the same language as the user's request"

    def _finalize_text(self) -> str:
        f = self.run.get("finalize") or {}
        parts = []
        if f.get("docs"):
            parts.append("update README/changelog/version notes following the project's own rules")
        pub = f.get("publish", "none")
        parts.append({"none": "", "commit": "commit locally", "branch": "publish on a work branch", "pr": "publish on a branch and open a pull request", "main": "commit straight to the base branch"}.get(pub, ""))
        return "; ".join(p for p in parts if p)

    def _system(self, agent: str, **kw: Any) -> str:
        content = "sfw" if (self.settings.get("generation") or {}).get("content") == "sfw" else "free"
        proj = f"`{self.env.get('root', '')}` — " + ", ".join(x["label"] for x in self.project.get("languages", [])[:5]) if self.project.get("languages") else f"`{self.env.get('root', '')}`"
        return promptlib.compose(agent, language=self._language_name(), os_label=self.env.get("os", ""), project=proj, content=content, mode=self.doc["mode"], effort=self.prof["id"], agents=self.n_agents,
                                 plan_steps=self.prof["plan_steps"], finalize=self._finalize_text(), **kw)

    # ----------------------------------------------------------------- aprovação (modo Ask)
    def _wait_answer(self, pend: Dict[str, Any]) -> bool:
        with self.cv:
            self.run.setdefault("pendings", []).append(pend)
            self.run["status"], self.doc["state"] = "waiting", "waiting"
        self._save()
        with self.cv:
            while pend["answer"] is None and not self._cancel.is_set():
                self.cv.wait(0.5)
            ans = pend["answer"]
            self.run["pendings"] = [p for p in self.run.get("pendings", []) if p is not pend]
            if not any(p.get("answer") is None for p in self.run["pendings"]):
                self.run["status"], self.doc["state"] = "running", "working"
        if self._cancel.is_set() and ans is None:
            raise A.Cancelled()
        if ans and pend.get("remember") and pend.get("risk"):
            self.allowed.add(pend["risk"])
            self.doc["allowed"] = sorted(self.allowed)
        self._save()
        return bool(ans)

    def _ask_yes_no(self, question: str) -> bool:
        return self._wait_answer({"id": new_id("q_"), "kind": "question", "agent": "", "tool": "ask_user", "risk": "read", "question": question[:400], "args": {}, "ts": time.time(), "answer": None, "remember": False})

    # ----------------------------------------------------------------- fluxo principal
    def go(self) -> None:
        from .. import scheduler

        scheduler.set_priority(scheduler.BACKGROUND)   # a conversa que o usuário espera passa na frente (modelo local embutido)
        d, r = self.doc, self.run
        try:
            r["status"], r["started"] = "running", time.time()
            d["state"] = "working"
            self._save()
            self._prepare()
            self._plan()
            checks: List[Dict[str, Any]] = []
            review: Optional[Dict[str, Any]] = None
            if r.get("blocked"):
                status = "failed"
            elif self.demo:
                self._run_script()
                status = self._status(checks, review)
            else:
                self._run_steps([s for s in r["plan"]["steps"] if s["role"] != "publisher"])
                checks, review = self._verify_loop()
                status = self._status(checks, review)
                if self.tail and not self.cancelled():
                    self._publish_tail(status, checks, review)
            self._report(status, checks, review)
            r["status"] = status
        except A.Cancelled:
            r["status"] = "cancelled"
            r["summary"] = r.get("summary") or A.deterministic_report(r["goal"], "cancelled", r.get("plan", {}).get("steps", []), self._files(), None, r.get("checks", []), self._undoable(), self.lang)
            self._agent("reporter", "skipped")
        except ProviderError as exc:
            r["status"], r["error"] = "failed", str(exc)
            r["summary"] = ("A IA não respondeu: " if self.lang == "pt" else "The AI did not answer: ") + str(exc)
        except guard.Blocked as exc:
            r["status"], r["error"] = "failed", str(exc)
            r["summary"] = str(exc)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            r["status"], r["error"] = "failed", str(exc) or exc.__class__.__name__
            r["summary"] = ("Erro inesperado: " if self.lang == "pt" else "Unexpected error: ") + (str(exc) or exc.__class__.__name__)
        finally:
            with self.lock:
                r["pendings"], r["now"] = [], ""
                r["finished"] = time.time()
                r["files"] = self._files()
                for s in r.get("plan", {}).get("steps", []):
                    if s["status"] in ("running", "pending"):
                        s["status"] = "skipped"
                for a in r.get("agents", []):
                    if a["status"] in ("running", "pending"):
                        a["status"] = "skipped"
            self._save()
            self.m.finished(self)

    # ----- 1. Planejador
    def _plan(self) -> None:
        d, r = self.doc, self.run
        self._agent("planner", "running")
        goal = r["goal"]
        if self.demo:
            self.script = rulebased.build_script(goal)
            if not self.script:
                r["blocked"] = rulebased.NEEDS_AI_PT if self.lang == "pt" else rulebased.NEEDS_AI_EN
                r["plan"] = {"summary": goal[:300], "kind": "mixed", "steps": [], "assumptions": [], "risks": [], "blocked": r["blocked"]}
                self._agent("planner", "error", "sem IA")
                return
            plan = A.normalize_plan({"summary": self.script["summary"], "kind": self.script["kind"], "steps": self.script["steps"]}, goal, 3)
            r["plan"] = plan
            self._agent("planner", "done", "regras (sem IA)")
            return
        payload = {"goal": goal, "attachments": self.digest, "inputs": self._inputs_list(), "project": self._compact_project(), "conversation": self._conversation(), "environment": self.env,
                   "tools_available": self.names, "tools_unavailable": self.missing, "mode": d["mode"], "finalize": r.get("finalize"), "effort": self.prof["id"], "max_parallel_workers": self.n_agents, "vision": self.vision}
        sys = self._system("planner")
        obj = self.brain.ask("planner", sys, A.PLAN_INSTR, payload, images=self.input_images or None, max_tokens=2200)
        plan = A.normalize_plan(obj, goal, self.prof["plan_steps"]) if obj else A.fallback_plan(goal)
        if self.prof["critique_plan"] and obj and plan["steps"] and not plan["blocked"]:
            obj2 = self.brain.ask("planner", sys, A.CRITIQUE_INSTR, {**payload, "plan": plan}, max_tokens=2200)
            better = A.normalize_plan(obj2, goal, self.prof["plan_steps"]) if obj2 else None
            if better and better["steps"] and not better["blocked"]:
                plan = better
        if plan["blocked"]:
            r["blocked"] = plan["blocked"]
        elif not plan["steps"]:
            plan = A.fallback_plan(goal)
        if not r.get("blocked"):
            self._apply_finalize(plan)
        r["plan"] = plan
        self._agent("planner", "warn" if obj is None else "done", "" if obj is not None else "método automático")
        self.tail = [s for s in plan["steps"] if s["role"] == "publisher"]

    def _apply_finalize(self, plan: Dict[str, Any]) -> None:
        fin = self.run.get("finalize") or {}
        steps = plan["steps"]
        if fin.get("publish", "none") == "none":
            plan["steps"] = steps = [s for s in steps if s["role"] != "publisher"]   # sem pedido de publicar, ninguém publica
        ids = [s["id"] for s in steps]
        if fin.get("docs") and not any(s["role"] == "docs" for s in steps) and len(steps) < 20:
            nid = f"s{len(steps) + 1}"
            steps.append({"id": nid, "title": "Atualizar README, changelogs e notas de versão" if self.lang == "pt" else "Update README, changelogs and release notes", "role": "docs", "files": [],
                          "depends_on": list(ids), "done_when": "docs describe exactly what the diff does", "status": "pending"})
            ids.append(nid)
        if fin.get("publish", "none") != "none" and not any(s["role"] == "publisher" for s in steps) and len(steps) < 21:
            steps.append({"id": f"s{len(steps) + 1}", "title": "Publicar as mudanças" if self.lang == "pt" else "Publish the changes", "role": "publisher", "files": [], "depends_on": list(ids), "done_when": "changes are published", "status": "pending"})

    def _compact_project(self) -> Dict[str, Any]:
        p = self.project or {}
        cmds = {k: [f"{c['label']}: {' '.join(c['argv'])}" for c in v[:2]] for k, v in (p.get("commands") or {}).items() if v}
        return {"name": self.env.get("root"), "languages": [f"{x['label']} ({x['files']})" for x in p.get("languages", [])[:6]], "manifests": p.get("manifests", [])[:10], "commands": cmds, "git": p.get("git"),
                "repo": p.get("repo"), "tree": self.ws.list_dir(".", 2, 60) if self.ws else ""}

    def _inputs_list(self) -> List[str]:
        d = self.m.session_dir(self.doc["id"]) / "inputs"
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []

    def _conversation(self) -> List[Dict[str, str]]:
        out = []
        for h in (self.doc.get("runs") or [])[-4:]:
            out.append({"request": str(h.get("goal", ""))[:300], "result": str(h.get("summary", ""))[:500], "files": [f["path"] for f in h.get("files", [])[:10]]})
        return out

    # ----- 2. Trabalhadores em paralelo
    def _run_steps(self, steps: List[Dict[str, Any]], label: str = "") -> None:
        by_id = {s["id"]: s for s in self.run["plan"]["steps"]}
        pending = [s for s in steps if s["status"] == "pending"]
        running: Dict[str, threading.Thread] = {}
        slots: Dict[str, int] = {}
        errors: List[BaseException] = []

        def work(st: Dict[str, Any], slot: int) -> None:
            try:
                self._worker(st, slot)
            except A.Cancelled:
                st["status"] = "skipped"
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
                with self.lock:
                    st["status"], st["summary"] = "failed", f"{exc.__class__.__name__}: {exc}"[:300]
            finally:
                with self.sched:
                    running.pop(st["id"], None)
                    slots.pop(st["id"], None)
                    self.sched.notify_all()

        while (pending or running) and not self.cancelled():
            started = False
            had_running = bool(running)
            for st in list(pending):
                if len(running) >= self.n_agents:
                    break
                deps = [by_id.get(x) for x in st["depends_on"] if by_id.get(x)]
                if any(x["status"] in ("pending", "running") for x in deps):
                    continue
                if any(x["status"] in ("failed",) for x in deps):
                    with self.lock:
                        st["status"], st["summary"] = "skipped", ("Pulada: depende de «" + next(x["title"] for x in deps if x["status"] == "failed") + "», que não terminou.") if self.lang == "pt" else "Skipped: a task it depends on did not finish."
                    pending.remove(st)
                    self._save()
                    started = True
                    continue
                if any(_overlap(st["files"], by_id[i]["files"]) for i in list(running) if i in by_id):
                    continue   # mesmos arquivos de uma tarefa em andamento: espera
                slot = next(i for i in range(1, self.n_agents + 1) if i not in list(slots.values()))
                slots[st["id"]] = slot
                with self.lock:
                    st["status"] = "running"
                pending.remove(st)
                th = threading.Thread(target=work, args=(st, slot), daemon=True, name=f"code-{self.doc['id']}-{st['id']}")
                running[st["id"]] = th
                th.start()
                started = True
            if not started:
                with self.sched:
                    if running or pending:
                        self.sched.wait(0.3)
            if not had_running and not running and pending and not started:   # nada pode começar (dependência travada): fecha como pulada
                with self.lock:
                    for st in pending:
                        st["status"], st["summary"] = "skipped", "Pulada: dependência não resolvida."
                pending = []
        for th in list(running.values()):
            th.join(30)
        if self.cancelled():
            raise A.Cancelled()
        if errors and not any(s["status"] == "done" for s in steps):
            raise errors[0]

    def _tools_for(self, role: str) -> List[str]:
        return [n for n in self.names if T.role_allows(role, n)]

    def _worker(self, st: Dict[str, Any], slot: int) -> None:
        aid = f"w{slot}"
        role = st["role"]
        self._agent(aid, "running", st["title"][:120], role=role, step=st["id"])
        provider, info = self.m.provider_for(self.settings, self.doc)
        self._tune_other(provider, info)
        brain = A.Brain(provider, self.cancelled, self._warn, temperature=0.3)
        names = self._tools_for(role)
        system = self._system("operator", role=role, tools=T.catalog_text(names), lang_guides=langs.guides_for([x["id"] for x in self.project.get("languages", [])[:4]]),
                              unavailable="\n".join(f"- {n}: {w}" for n, w in self.missing.items()))
        history: List[Dict[str, Any]] = []
        memo: List[str] = []
        failures: Dict[str, int] = {}
        denied = bad = 0
        pending_image: Optional[Path] = None
        selfchecked = False
        nudged = acted = False   # nudged: já empurrei o trabalhador que desistiu por «falta de clareza»; acted: já fez alguma mudança que deu certo
        outcome: Optional[Dict[str, Any]] = None
        max_turns = self.prof["turns"]
        hist_n = self.prof["history"]
        turn, extended = 0, False
        while True:
            if turn >= max_turns:
                if acted and not extended and any(h.get("ok") for h in history[-3:]):
                    # o limite chegou, mas o trabalhador está avançando (mudou arquivos e as últimas ações deram certo): uma única prorrogação, em vez de jogar fora o trabalho feito
                    extended = True
                    extra = max(6, max_turns // 3)
                    max_turns += extra
                    history.append({"action": "(limite de ações)", "ok": True, "output": f"Você ganhou mais {extra} ações porque está progredindo. Termine só o que falta e finalize."})
                else:
                    break
            turn += 1
            if self.cancelled():
                raise A.Cancelled()
            payload = self._worker_payload(st, history[-hist_n:], memo, turn, max_turns, turn == max_turns)
            images = None
            if pending_image is not None:
                images, pending_image = self._img(pending_image), None
            elif turn == 1 and self.input_images and self.vision and role in ("ui", "coder", "architect", "prompts", "docs"):
                images = self.input_images
            obj = brain.ask(aid, system, A.TURN_INSTR, payload, images=images, max_tokens=self.prof["op_tokens"])
            t = A.normalize_turn(obj)
            if t["kind"] == "bad":
                bad += 1
                history.append({"action": "(resposta inválida)", "ok": False, "output": f"{t['why']}. Responda com UM objeto JSON com «action» ou «finish»."})
                if bad >= 3:
                    outcome = {"success": False, "summary": "O modelo não conseguiu responder no formato esperado.", "files": []}
                    break
                continue
            bad = 0
            if t.get("memo"):
                memo = (memo + [t["memo"]])[-8:]
            if t["kind"] == "finish":
                if not t["success"] and not nudged and not acted and turn < max_turns and UNCLEAR_RE.search(t["summary"]):
                    nudged = True   # desistir de uma tarefa por «não ficou claro» sem ter tentado nada não é um bloqueio de verdade: decide com o que o projeto já mostra e segue
                    history.append({"action": "finish (recusado)", "ok": False, "output": "Falta de clareza não é um bloqueio" + (" e ninguém vai responder perguntas" if self.doc["mode"] == "full" else "") +
                                    ". Escolha a interpretação mais razoável do pedido (o que o projeto já faz é a melhor pista: leia os arquivos relacionados), anote a suposição em «memo» e FAÇA o trabalho. "
                                    "Só termine com success=false se uma ferramenta, uma permissão ou um arquivo realmente impedir."})
                    continue
                if self.prof["self_check"] and not selfchecked and t["success"] and turn < max_turns:
                    selfchecked = True
                    history.append({"action": "finish (pedido)", "ok": True, "output": "Antes de encerrar: confira com uma ação (ler o resultado, rodar o teste) que «done_when» foi atendido. Se estiver tudo certo, finalize de novo."})
                    continue
                outcome = {"success": t["success"], "summary": t["summary"], "files": t["files"]}
                break
            tool, args = t["tool"], t["args"]
            if tool not in T.TOOLS or tool not in self.names or not T.role_allows(role, tool, args):
                why = "ferramenta desconhecida" if tool not in T.TOOLS else (self.missing.get(tool) or f"não é permitida para o papel «{role}» neste momento")
                history.append({"action": tool, "ok": False, "output": f"«{tool}» não pode ser usada: {why}. Ferramentas disponíveis: {', '.join(names)}."})
                continue
            key = tool + json.dumps(args, sort_keys=True, default=str)
            if failures.get(key, 0) >= 1:
                history.append({"action": tool, "ok": False, "output": "Você já tentou exatamente isto e falhou. Mude o caminho, o texto ou a ferramenta."})
                failures[key] += 1
                if failures[key] >= 4:
                    outcome = {"success": False, "summary": "Preso repetindo a mesma ação que falha.", "files": []}
                    break
                continue
            res, step = self._act(aid, st, tool, args)
            if step["status"] == "denied":
                denied += 1
                history.append({"action": tool, "args": _short_args(args), "ok": False, "output": "O usuário NEGOU esta ação. Não tente de novo; escolha outro caminho ou finalize explicando o que falta."})
                if denied >= 3:
                    outcome = {"success": False, "summary": "O usuário negou várias ações.", "files": []}
                    break
                continue
            if not res.ok:
                failures[key] = failures.get(key, 0) + 1
            if res.image is not None and self.vision:
                pending_image = res.image
            if res.ok and tool in MUTATING:
                acted = True
            history.append({"action": tool, "args": _short_args(args), "ok": res.ok, "output": A.trim_obs(res.output, self.prof["obs_chars"])})
        incomplete = False
        if outcome is None:
            mine = [x["path"] for x in self.ws.changed_files()][:12] if acted else []
            if acted:   # o limite acabou, mas há trabalho feito: a tarefa fica «incompleta» (as seguintes — testes, revisão — rodam sobre o que existe) em vez de «falhou» e derrubar tudo o que dependia dela
                incomplete = True
                outcome = {"success": True, "summary": (f"Atingi o limite de {max_turns} ações antes de terminar: o que já foi feito está nos arquivos ({', '.join(mine) or 'veja as mudanças'}), mas a tarefa pode estar incompleta."
                                                        if self.lang == "pt" else f"Reached the limit of {max_turns} actions before finishing: what was done is in the files ({', '.join(mine) or 'see the changes'}), but the task may be incomplete."), "files": mine}
            else:
                outcome = {"success": False, "summary": f"Atingi o limite de {max_turns} ações sem terminar a tarefa." if self.lang == "pt" else f"Reached the limit of {max_turns} actions without finishing the task.", "files": []}
        with self.lock:
            st["incomplete"] = incomplete
            st["status"] = "done" if outcome["success"] else "failed"
            st["summary"] = outcome["summary"]
            st["result_files"] = outcome["files"]
            self.board[st["id"]] = {"title": st["title"], "summary": outcome["summary"][:500], "files": outcome["files"][:10], "ok": outcome["success"]}
        self._agent(aid, "done" if outcome["success"] and not incomplete else "warn", outcome["summary"][:200], role=role, step=st["id"])
        self._agent(aid, "idle", "", role=role, step="")

    def _tune_other(self, provider: Any, info: Dict[str, Any]) -> None:
        sup = think.support(info.get("id", ""), info.get("model", ""))
        try:
            provider.thinking = self.prof["thinking"] if sup.get("supported") else "off"
        except AttributeError:
            pass

    @staticmethod
    def _img(p: Path) -> Optional[List[dict]]:
        try:
            media = "image/png" if p.suffix.lower() == ".png" else "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/" + p.suffix.lower().lstrip(".")
            return [{"media_type": media, "data": base64.b64encode(p.read_bytes()).decode("ascii")}]
        except OSError:
            return None

    def _worker_payload(self, st: Dict[str, Any], history: List[Dict[str, Any]], memo: List[str], turn: int, max_turns: int, last_chance: bool) -> Dict[str, Any]:
        hist = []
        for i, h in enumerate(history):
            full = i >= len(history) - 2
            hist.append({**h, "output": h["output"] if full else h["output"][:500] + ("…" if len(h["output"]) > 500 else "")})
        with self.lock:
            plan = [{"id": s["id"], "title": s["title"], "role": s["role"], "status": s["status"]} for s in self.run["plan"]["steps"]]
            board = [{"id": k, **v} for k, v in self.board.items()]
        payload: Dict[str, Any] = {"goal": self.run["goal"], "step": {k: st.get(k) for k in ("id", "title", "role", "files", "done_when", "feedback") if st.get(k)}, "plan": plan, "board": board,
                                   "project": {"languages": [x["label"] for x in self.project.get("languages", [])[:5]], "commands": {k: [" ".join(c["argv"]) for c in v[:2]] for k, v in (self.project.get("commands") or {}).items() if v}},
                                   "changed_files": self.ws.changed_files()[:30], "history": hist, "memo": memo, "turn": f"{turn}/{max_turns}"}
        if turn == 1:
            payload["attachments"] = self.digest
            payload["attachment_files"] = self._inputs_list()
            payload["conversation"] = self._conversation()
        if max_turns - turn <= 3:
            payload["note"] = "You are almost out of actions for this step: wrap up now and finish with an honest summary."
        if last_chance:
            payload["note"] = "Last turn: finish now."
        return payload

    # ----- uma ação do trabalhador (valida → pergunta → executa → registra)
    def _act(self, aid: str, st: Dict[str, Any], tool: str, args: Dict[str, Any]):
        risk = T.risk_of(tool, args)
        with self.lock:
            self.step_n += 1
            step = {"n": self.step_n, "agent": aid, "plan_step": st["id"], "tool": tool, "risk": risk, "args": T.describe(tool, args)["args"], "status": "running", "output": "", "ts": time.time(), "dur": 0.0}
            steps = self.run.setdefault("steps", [])
            steps.append(step)
            if len(steps) > 600:   # o registro não cresce sem limite: a tela mostra as últimas ações e o resto do que importa está nos arquivos desfazíveis
                del steps[:len(steps) - 600]
            self.run["now"] = f"{st['title'][:80]}"
        self._save()
        if T.needs_approval(tool, args, self.doc["mode"], self.cfg["ask_for"], self.allowed):
            pend = {"id": new_id("q_"), "kind": "action", "step": step["n"], "agent": aid, "tool": tool, "risk": risk, "args": T.describe(tool, args)["args"], "ts": time.time(), "answer": None, "remember": False}
            ans = self._wait_answer(pend)
            with self.lock:
                step["approval"] = {"asked": True, "answer": ans, "remember": bool(pend.get("remember"))}
            if not ans:
                with self.lock:
                    step.update(status="denied", output="negada pelo usuário", dur=time.time() - step["ts"])
                self._save()
                return T.Result(False, "negada"), step
        res = T.execute(self.ctx, tool, args)
        with self.lock:
            step.update(status="ok" if res.ok else "error", output=A.trim_obs(res.output, OUT_LIMIT), dur=round(time.time() - step["ts"], 2))
            if res.meta.get("sources"):
                step["sources"] = [{"title": s.get("title", ""), "url": s.get("url", "")} for s in res.meta["sources"][:6]]
        self._save()
        return res, step

    # ----- 3. testes, revisão e correção
    def _check_cmds(self) -> List[Dict[str, Any]]:
        if T.IS_ANDROID or "run_tests" not in self.names or not self.ws.changed_files():
            return []
        cmds = langs.commands(self.ctx.root)
        kinds = ["test"] + (["build"] if self.prof["id"] in ("mega", "max", "ultra", "omni") and cmds.get("build") else []) + (["lint"] if self.prof["id"] in ("max", "ultra", "omni") and cmds.get("lint") else [])
        return [{"kind": k, "label": cmds[k][0]["label"]} for k in kinds if cmds.get(k)]

    def _run_checks(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not self.prof["tests"]:
            return out
        plan = self._check_cmds()
        if not plan:
            return out
        self._agent("tests", "running", ", ".join(p["label"] for p in plan))
        for p in plan:
            args = {"kind": p["kind"]}
            if T.needs_approval("run_tests", args, self.doc["mode"], self.cfg["ask_for"], self.allowed):
                pend = {"id": new_id("q_"), "kind": "action", "step": 0, "agent": "tests", "tool": "run_tests", "risk": "run", "args": {"kind": p["kind"], "command": p["label"]}, "ts": time.time(), "answer": None, "remember": False}
                if not self._wait_answer(pend):
                    out.append({"kind": p["kind"], "label": p["label"], "ok": False, "exit": None, "skipped": True, "output": "O usuário negou rodar este comando."})
                    continue
            res = T.execute(self.ctx, "run_tests", args)
            out.append({"kind": p["kind"], "label": res.meta.get("command") or p["label"], "ok": bool(res.ok), "exit": res.meta.get("exit"), "output": A.trim_obs(res.output, 3500)})
        self._agent("tests", "done" if all(c["ok"] for c in out) else "warn", "; ".join(f"{c['label']}: {'ok' if c['ok'] else 'falhou'}" for c in out))
        with self.lock:
            self.run["checks"] = out
        self._save()
        return out

    def _review(self, checks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not self.prof["review"] or self.demo:
            return None
        self._agent("reviewer", "running")
        diff = self.ws.diff(max_chars=self.prof["obs_chars"] * 6)
        steps = [{"id": s["id"], "title": s["title"], "status": s["status"], "summary": str(s.get("summary", ""))[:400]} for s in self.run["plan"]["steps"]]
        evidence = {"diff": diff or "(nenhum arquivo foi alterado)", "files": self.ws.changed_files()[:60], "checks": [{k: c.get(k) for k in ("kind", "label", "ok", "exit")} | {"output": str(c.get("output", ""))[-1800:]} for c in checks]}
        obj = self.brain.ask("reviewer", self._system("reviewer"), A.REVIEW_INSTR, {"goal": self.run["goal"], "plan": steps, "evidence": evidence, "attachments": self.digest[:6000]}, max_tokens=1600)
        rv = A.normalize_review(obj)
        if rv is None:
            self._agent("reviewer", "warn", "método automático")
            return None
        with self.lock:
            self.run["review"] = rv
        self._agent("reviewer", "done" if rv["verdict"] == "pass" else "warn", f"{rv['verdict']} · {rv['score']}/10")
        return rv

    def _verify_loop(self):
        checks: List[Dict[str, Any]] = []
        review: Optional[Dict[str, Any]] = None
        rounds = self.prof["revisions"]
        for r in range(rounds + 1):
            if self.cancelled():
                raise A.Cancelled()
            checks = self._run_checks()
            review = self._review(checks)
            failed = [c for c in checks if not c["ok"] and not c.get("skipped")]
            unfinished = [x for x in self.run["plan"]["steps"] if x.get("incomplete") and not x.get("resumed")]   # tarefas que bateram no limite de ações
            needs_fix = bool(failed) or bool(unfinished) or bool(review and review["verdict"] != "pass" and review["fix"])
            if not needs_fix or r == rounds:
                break
            with self.lock:
                self.run["revisions"] = self.run.get("revisions", 0) + 1
                plan = self.run["plan"]["steps"]
                notes = ("; ".join(review["issues"][:6]) if review else "") + (" | " + review["fix"] if review and review["fix"] else "")
                fb = ("Failing checks:\n" + "\n".join(f"{c['label']}:\n{str(c.get('output', ''))[-1800:]}" for c in failed) + "\n") if failed else ""
                if unfinished:
                    fb += "Unfinished tasks (they ran out of actions): " + "; ".join(f"{x['title']}" for x in unfinished) + ". Finish exactly what is missing.\n"
                    for x in unfinished:
                        x["resumed"] = True
                st = {"id": f"s{len(plan) + 1}", "title": "Corrigir o que os testes/a revisão apontaram" if self.lang == "pt" else "Fix what the tests/review reported", "role": "debugger", "files": [], "depends_on": [],
                      "done_when": "the failing checks pass and the review issues are resolved", "feedback": (fb + "Review: " + notes)[:4000], "status": "pending"}
                plan.append(st)
            self._save()
            self._run_steps([st])
        return checks, review

    def _status(self, checks: List[Dict[str, Any]], review: Optional[Dict[str, Any]]) -> str:
        steps = [s for s in self.run.get("plan", {}).get("steps", []) if s["role"] != "publisher" or s["status"] != "pending"]
        if self.run.get("blocked"):
            return "failed"
        done = [s for s in steps if s["status"] == "done"]
        if not done:
            return "failed"
        if any(s["status"] == "failed" or s.get("incomplete") for s in steps) or any(not c["ok"] for c in checks) or (review and review["verdict"] == "fail"):
            return "partial"
        if review and review["verdict"] == "partial":
            return "partial"
        return "done"

    # ----- 4. publicação (só depois de tudo certo)
    def _publish_tail(self, status: str, checks: List[Dict[str, Any]], review: Optional[Dict[str, Any]]) -> None:
        fin = self.run.get("finalize") or {}
        for st in self.tail:
            if status != "done":
                st["status"] = "skipped"
                st["summary"] = self._not_published(checks, review)
                self.run.setdefault("notes", []).append(st["summary"])
                continue
            st["feedback"] = f"Publish setting: {fin.get('publish')}. Use publish_changes with " + {"pr": "pull_request=true, draft=true", "branch": "pull_request=false", "main": "main=true", "commit": "commit_local (local git commit only)"}.get(fin.get("publish"), "") + "."
            with self.lock:
                st["status"] = "running"
            self._worker(st, 1)
            steps = self.run.get("steps", [])
            published = any(x.get("tool") in ("publish_changes", "commit_local") and x["status"] == "ok" for x in steps)
            refused = any(x.get("tool") in ("publish_changes", "commit_local") and x["status"] == "denied" for x in steps)
            if not published and not refused:
                self._direct_publish(fin, st)

    def _not_published(self, checks: List[Dict[str, Any]], review: Optional[Dict[str, Any]]) -> str:
        """Por que a publicação foi pulada, dito como foi (antes dizia sempre «os testes/a revisão acusaram problemas», mesmo quando uma tarefa tinha falhado ou nada tinha sido verificado)."""
        pt = self.lang == "pt"
        steps = [x for x in self.run.get("plan", {}).get("steps", []) if x["role"] != "publisher"]
        why: List[str] = []
        bad = [x for x in steps if x["status"] == "failed"]
        if bad:
            why.append((f"uma tarefa do plano não terminou («{bad[0]['title'][:70]}»" + (f" e mais {len(bad) - 1}" if len(bad) > 1 else "") + ")") if pt else
                       (f"a plan task did not finish («{bad[0]['title'][:70]}»" + (f" and {len(bad) - 1} more" if len(bad) > 1 else "") + ")"))
        todo = [x for x in steps if x.get("incomplete")]
        if todo:
            why.append((f"uma tarefa do plano ficou incompleta («{todo[0]['title'][:70]}»)") if pt else (f"a plan task is incomplete («{todo[0]['title'][:70]}»)"))
        failed = [c for c in checks if not c.get("ok") and not c.get("skipped")]
        if failed:
            why.append(("os testes falharam (" + ", ".join(str(c.get("label")) for c in failed[:2]) + ")") if pt else ("tests failed (" + ", ".join(str(c.get("label")) for c in failed[:2]) + ")"))
        if review and review.get("verdict") != "pass":
            why.append("a revisão apontou problemas" if pt else "the review reported problems")
        if not why:
            why.append("o resultado não foi concluído por completo" if pt else "the result was not fully completed")
        return (("Não publiquei: " + "; ".join(why) + ". Corrija e peça de novo.") if pt else ("Not published: " + "; ".join(why) + ". Fix it and ask again."))

    def _direct_publish(self, fin: Dict[str, Any], st: Dict[str, Any]) -> None:
        mode = fin.get("publish", "branch")
        title = (self.run.get("plan", {}).get("summary") or self.run["goal"]).strip().splitlines()[0][:70]
        body = "\n".join(f"- {s['title']}" for s in self.run["plan"]["steps"] if s["status"] == "done" and s["role"] != "publisher")[:2000]
        if mode == "commit" and (self.run.get("repo") or self.doc["workspace"].get("repo", {})).get("kind") != "cloud":
            tool, args = "commit_local", {"message": title}
        else:
            tool, args = "publish_changes", {"message": title + ("\n\n" + body if body else ""), "pull_request": mode == "pr", "main": mode == "main", "title": title, "body": body}
        if tool not in self.names:
            return
        res, _ = self._act("w1", st, tool, args)
        st["status"] = "done" if res.ok else "failed"
        st["summary"] = res.output[:400]

    # ----- 5. relatório
    def _links(self) -> List[str]:
        out = []
        for s in self.run.get("steps", []):
            if s["status"] == "ok" and s["tool"] in ("publish_changes", "github_release", "github_create_pr", "github_create_repo"):
                out += re.findall(r"https?://\S+", s.get("output", ""))
        return list(dict.fromkeys(out))[:6]

    def _report(self, status: str, checks: List[Dict[str, Any]], review: Optional[Dict[str, Any]]) -> None:
        r = self.run
        steps = r.get("plan", {}).get("steps", [])
        files = self._files()
        notes = list(r.get("notes", []))
        if r.get("blocked"):
            r["summary"] = r["blocked"]
            self._agent("reporter", "skipped")
            return
        self._agent("reporter", "running")
        denied = sum(1 for x in r.get("steps", []) if x["status"] == "denied")
        fallback = A.deterministic_report(r["goal"], status, steps, files, review, checks, self._undoable(), self.lang, notes, self._links(), denied)
        if self.demo or status == "cancelled":
            r["summary"] = fallback
            self._agent("reporter", "done", "automático")
            return
        payload = {"goal": r["goal"], "status": status, "steps": [{"title": s["title"], "role": s["role"], "status": s["status"], "summary": str(s.get("summary", ""))[:500]} for s in steps], "files": files[:40],
                   "checks": [{k: c.get(k) for k in ("label", "ok", "exit")} for c in checks], "review": review, "links": self._links(), "notes": notes, "undo_available": self._undoable(), "denied_actions": sum(1 for s in r.get("steps", []) if s["status"] == "denied")}
        obj = self.brain.ask("reporter", self._system("reporter"), A.REPORT_INSTR, payload, max_tokens=1400)
        summary = str(obj.get("summary", "")).strip() if isinstance(obj, dict) else ""
        r["next_steps"] = A._list(obj.get("next_steps"), 5, 200) if isinstance(obj, dict) else []
        if len(summary) > 20 and not A.looks_like_json_noise(summary):
            foot = A.evidence_lines(status, checks, review, self.lang, notes, denied)   # a evidência vem do motor: o texto da IA nunca a contradiz
            links = self._links()
            r["summary"] = summary + ("\n\n" + "\n".join(foot + [u for u in links if u not in summary]) if foot or links else "")
        else:
            r["summary"] = fallback
        self._agent("reporter", "done" if summary else "warn", "" if summary else "método automático")

    # ----- 6. sem IA
    def _run_script(self) -> None:
        r = self.run
        st = r["plan"]["steps"][0]
        st["status"] = "running"
        self._agent("w1", "running", st["title"], role=st["role"], step=st["id"])
        outs = []
        ok_all = True
        for call in self.script["calls"]:
            if self.cancelled():
                raise A.Cancelled()
            res, step = self._act("w1", st, call["tool"], call["args"])
            ok_all = ok_all and res.ok
            outs.append(res.output)
        st["status"] = "done" if ok_all else "failed"
        st["summary"] = "\n\n".join(outs)[:1800]
        self._agent("w1", "done" if ok_all else "warn", st["title"], role=st["role"], step="")

    # ----------------------------------------------------------------- utilidades
    def _files(self) -> List[Dict[str, str]]:
        try:
            return self.ws.changed_files()[:200] if self.ws else []
        except OSError:
            return []

    def _undoable(self) -> bool:
        return bool(self.ws and self.ws.undoable(self.run["id"]))
