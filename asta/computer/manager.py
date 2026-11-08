"""O gerenciador do Computer Use: **até 8 tarefas ao mesmo tempo**, fila das que passam disso, histórico em disco, aprovações do modo Ask, desfazer e eventos para a tela.

Cada tarefa é um `TaskRunner` (engine.py) numa thread própria, com prioridade baixa na fila do modelo local. O estado de cada uma é um documento JSON em
`~/.asta/computer/tasks/<id>/task.json` (arquivos comuns, abertos e legíveis — o histórico passo a passo pertence ao usuário e pode ser apagado a qualquer momento).
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import attachments as att
from ..providers import resolve_provider
from ..util import new_id, now_iso, num, read_json, text
from . import files as F
from . import guard, osdrv, tools as T
from .engine import FINAL, GuiLease, TaskRunner

SCHEMA = "asta.computer.task.v1"
MAX_PARALLEL = 8
MAX_QUEUE = 40
_ID = re.compile(r"^[\w-]+$")


class ComputerError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def normalize_config(raw: Any) -> Dict[str, Any]:
    """`settings.computer` válido (valor errado volta ao padrão)."""
    d = raw if isinstance(raw, dict) else {}
    ask = [r for r in (d.get("ask_for") if isinstance(d.get("ask_for"), list) else T.DEFAULT_ASK) if r in T.RISKS and r != T.READ]
    return {
        "enabled": d.get("enabled") is True,
        "mode": d.get("mode") if d.get("mode") in ("ask", "full") else "ask",
        "max_parallel": int(num(d.get("max_parallel"), MAX_PARALLEL, 1, MAX_PARALLEL)),
        "max_steps": int(num(d.get("max_steps"), 40, 5, 200)),
        "team": "fast" if d.get("team") == "fast" else "full",
        "revisions": int(num(d.get("revisions"), 1, 0, 2)),
        "ask_for": list(dict.fromkeys(ask)),
        "game_dirs": [str(x)[:500] for x in (d.get("game_dirs") if isinstance(d.get("game_dirs"), list) else []) if isinstance(x, str) and x.strip()][:20],
        "app_wait": float(num(d.get("app_wait"), 2.0, 0, 15)),
    }


class ComputerManager:
    def __init__(self, store: Any, resolve: Optional[Callable[[dict], Any]] = None):
        self.store = store
        guard.set_home(getattr(store, "home", None))   # os dados do Computer Use ficam na mesma pasta do ASTA em uso (e essa pasta nunca é acessível à IA)
        self.gui = GuiLease()
        self.lock = threading.RLock()
        self.runners: Dict[str, TaskRunner] = {}
        self.active: set = set()
        self.queue: List[str] = []
        self.snap: Dict[str, str] = {}
        self.cv = threading.Condition()
        self.version = 0
        self.touched: Dict[str, int] = {}
        self.on_finish: List[Callable[[Dict[str, Any]], None]] = []
        self._resolve = resolve
        self.tasks_dir = guard.data_dir() / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._recover()

    # ----------------------------------------------------------------- piezas
    @property
    def driver(self) -> osdrv.Driver:
        return osdrv.get_driver()

    def config(self) -> Dict[str, Any]:
        return normalize_config(self.store.get_settings().get("computer"))

    def resolve_provider(self, settings: dict):
        if self._resolve:
            return self._resolve(settings)
        return resolve_provider(settings, "generation", self.store.models_dir)

    def _file(self, tid: str) -> Optional[Path]:
        return self.tasks_dir / tid / "task.json" if _ID.match(tid or "") else None

    # ----------------------------------------------------------------- persistência e eventos
    def persist(self, doc: Dict[str, Any]) -> None:
        data = json.dumps(doc, ensure_ascii=False)
        tid = doc["id"]
        self.snap[tid] = data
        f = self._file(tid)
        if f:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_name(f".tmp-{threading.get_ident()}.json")
            try:
                tmp.write_text(data, encoding="utf-8")
                tmp.replace(f)
            except OSError:
                try:
                    tmp.unlink()
                except OSError:
                    pass
        with self.cv:
            self.version += 1
            self.touched[tid] = self.version
            if len(self.touched) > 400:
                for k in sorted(self.touched, key=self.touched.get)[:100]:  # type: ignore[arg-type]
                    self.touched.pop(k, None)
            self.cv.notify_all()

    def wait_events(self, since: int, timeout: float = 15.0) -> tuple:
        with self.cv:
            if self.version <= since:
                self.cv.wait(timeout)
            v = self.version
            ids = [t for t, ver in self.touched.items() if ver > since]
        return v, [s for s in (self.summary_of(t) for t in ids) if s]

    def _recover(self) -> None:
        """Tarefas que estavam rodando quando o ASTA foi fechado não continuam sozinhas: ficam marcadas como interrompidas (e o que elas fizeram ainda pode ser desfeito)."""
        for d in self.tasks_dir.iterdir() if self.tasks_dir.is_dir() else []:
            doc = read_json(d / "task.json")
            if isinstance(doc, dict) and doc.get("status") in ("queued", "running", "waiting"):
                doc.update(status="failed", pending=None, now="", note="", finished=time.time(), error="interrompida",
                           summary=doc.get("summary") or "O ASTA foi fechado durante a tarefa; ela foi interrompida. O que já foi feito continua valendo (dá para desfazer).")
                try:
                    (d / "task.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
                except OSError:
                    pass

    # ----------------------------------------------------------------- consulta
    def get(self, tid: str) -> Optional[Dict[str, Any]]:
        if not _ID.match(tid or ""):
            return None
        raw = self.snap.get(tid)
        if raw is not None and tid in self.runners:
            try:
                return json.loads(raw)
            except ValueError:
                pass
        f = self._file(tid)
        doc = read_json(f) if f else None
        return doc if isinstance(doc, dict) and doc.get("id") == tid else None

    @staticmethod
    def summary(doc: Dict[str, Any]) -> Dict[str, Any]:
        steps = doc.get("steps") or []
        pend = doc.get("pending")
        return {"id": doc["id"], "goal": str(doc.get("goal", ""))[:240], "mode": doc.get("mode", "ask"), "status": doc.get("status", ""), "created": doc.get("created", ""),
                "started": doc.get("started"), "finished": doc.get("finished"), "steps": len(steps), "ok": sum(1 for s in steps if s.get("status") == "ok"),
                "errors": sum(1 for s in steps if s.get("status") == "error"), "denied": sum(1 for s in steps if s.get("status") == "denied"),
                "waiting": bool(pend and pend.get("answer") is None), "now": doc.get("now", ""), "note": doc.get("note", ""), "chat_id": doc.get("chat_id", ""),
                "provider": (doc.get("provider") or {}).get("label", ""), "summary": str(doc.get("summary", ""))[:220], "undo": any(not e.get("undone") for e in doc.get("journal", [])),
                "plan_done": sum(1 for p in (doc.get("plan") or {}).get("steps", []) if p.get("status") == "done"), "plan_total": len((doc.get("plan") or {}).get("steps", []))}

    def summary_of(self, tid: str) -> Optional[Dict[str, Any]]:
        doc = self.get(tid)
        return self.summary(doc) if doc else None

    @staticmethod
    def public(doc: Dict[str, Any]) -> Dict[str, Any]:
        out = {k: v for k, v in doc.items() if k not in ("journal", "inputs_digest")}
        out["undo"] = any(not e.get("undone") for e in doc.get("journal", []))
        out["journal_size"] = len(doc.get("journal", []))
        out["files"] = _files_of(doc)
        return out

    def list(self, limit: int = 200) -> List[Dict[str, Any]]:
        docs: Dict[str, Dict[str, Any]] = {}
        try:
            dirs = sorted((d for d in self.tasks_dir.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime, reverse=True)[:max(limit, 1) * 2]
        except OSError:
            dirs = []
        for d in dirs:
            doc = read_json(d / "task.json")
            if isinstance(doc, dict) and doc.get("id"):
                docs[doc["id"]] = doc
        for tid in list(self.runners):
            live = self.get(tid)
            if live:
                docs[tid] = live
        items = sorted(docs.values(), key=lambda x: x.get("created", ""), reverse=True)[:limit]
        return [self.summary(x) for x in items]

    def status(self) -> Dict[str, Any]:
        cfg = self.config()
        drv = self.driver
        with self.lock:
            running = sum(1 for tid in self.active if (self.get(tid) or {}).get("status") == "running")
            waiting = sum(1 for tid in self.active if (self.get(tid) or {}).get("status") == "waiting")
            queued = len(self.queue)
        return {"enabled": cfg["enabled"], "mode": cfg["mode"], "max_parallel": cfg["max_parallel"], "running": running, "waiting": waiting, "queued": queued,
                "platform": drv.name, "platform_label": drv.label, "capabilities": drv.capabilities(), "gui_owner": self.gui.owner, "limit": MAX_PARALLEL}

    # ----------------------------------------------------------------- criar
    def submit(self, goal: str, *, mode: str = "", attachment_ids: Optional[List[str]] = None, chat_id: str = "", origin: str = "section",
               before_start: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        cfg = self.config()
        if not cfg["enabled"]:
            raise ComputerError(403, "O Computer Use está desligado. Ligue em Configuração → Computer Use.")
        goal = text(goal, "", 8000)
        ids = [x for x in (attachment_ids or []) if isinstance(x, str)][:20]
        if not goal and not ids:
            raise ComputerError(400, "Escreva o que o Computer Use deve fazer.")
        mode = mode if mode in ("ask", "full") else cfg["mode"]
        with self.lock:
            if len(self.queue) >= MAX_QUEUE:
                raise ComputerError(429, "Há tarefas demais na fila. Espere algumas terminarem.")
        tid = new_id("cu_")
        inputs, digest, images = self._take_inputs(tid, ids)
        doc: Dict[str, Any] = {"schema": SCHEMA, "id": tid, "goal": goal or "(anexos)", "mode": mode, "status": "queued", "created": now_iso(), "started": None, "finished": None,
                               "origin": origin, "chat_id": text(chat_id, "", 60), "inputs": inputs, "inputs_digest": digest, "plan": {"summary": "", "kind": "mixed", "steps": []},
                               "steps": [], "agents": [], "warnings": [], "journal": [], "pending": None, "review": None, "summary": "", "error": "", "now": "", "note": ""}
        runner = TaskRunner(self, doc, images)
        with self.lock:
            self.runners[tid] = runner
            self.queue.append(tid)
        self.persist(doc)
        if before_start:
            before_start(self.public(doc))
        self._pump()
        return self.public(doc)

    def _take_inputs(self, tid: str, ids: List[str]):
        """Anexos do pedido: os arquivos vão para a pasta de rascunho da tarefa (a IA pode copiá-los de lá) e o texto/imagens deles vão ao Planejador."""
        if not ids:
            return [], "", []
        metas = self.store.get_uploads(ids, limit=20, expand=True)
        dest = guard.workspace() / tid / "inputs"
        inputs, analyzed = [], []
        transcribe = None
        try:
            from .. import voice

            transcribe = voice.transcriber(self.store.get_settings())
        except Exception:  # noqa: BLE001
            transcribe = None
        for m in metas:
            src = Path(m["path"])
            if not src.is_file():
                continue
            name = re.sub(r"[\\/:*?\"<>|]+", "_", m["name"].replace("\\", "/").split("/")[-1])[:120] or "arquivo"
            try:
                dest.mkdir(parents=True, exist_ok=True)
                target = dest / name
                n = 2
                while target.exists():
                    target = dest / f"{Path(name).stem} ({n}){Path(name).suffix}"
                    n += 1
                shutil.copy2(src, target)
            except OSError:
                continue
            inputs.append({"name": m["name"], "path": str(target), "size": m.get("size", 0)})
            try:
                analyzed.append(att.analyze(src, m["name"], m.get("mime", ""), max_chars=8000, transcribe=transcribe))
            except Exception:  # noqa: BLE001
                continue
        for uid in {str(i).split(":", 1)[0] for i in ids}:
            self.store.delete_upload(uid)
        return inputs, att.build_digest(analyzed, max_total=30000), att.collect_images(analyzed, 4)

    # ----------------------------------------------------------------- fila
    def _pump(self) -> None:
        with self.lock:
            cap = self.config()["max_parallel"]
            while self.queue and len(self.active) < cap:
                tid = self.queue.pop(0)
                r = self.runners.get(tid)
                if not r or r.doc.get("status") != "queued":
                    continue
                self.active.add(tid)
                threading.Thread(target=r.run, daemon=True, name=f"computer-{tid}").start()

    def finished(self, runner: TaskRunner) -> None:
        tid = runner.doc["id"]
        with self.lock:
            self.active.discard(tid)
        self.persist(runner.doc)
        for cb in list(self.on_finish):
            try:
                cb(self.public(runner.doc))
            except Exception:  # noqa: BLE001 - um ouvinte com defeito não pode derrubar o gerenciador
                import traceback

                traceback.print_exc()
        with self.lock:
            self.runners.pop(tid, None)
        self.snap.pop(tid, None)
        self._pump()

    # ----------------------------------------------------------------- controle
    def cancel(self, tid: str) -> Dict[str, Any]:
        with self.lock:
            r = self.runners.get(tid)
            if r is None:
                raise ComputerError(404 if not self.get(tid) else 409, "Tarefa não encontrada" if not self.get(tid) else "A tarefa já terminou.")
            if tid in self.queue:
                self.queue.remove(tid)
                doc = r.doc
                doc.update(status="cancelled", finished=time.time(), summary="Cancelada antes de começar.")
                self.runners.pop(tid, None)
                self.persist(doc)
                for cb in list(self.on_finish):
                    try:
                        cb(self.public(doc))
                    except Exception:  # noqa: BLE001
                        pass
                return self.public(doc)
        r.cancel()
        return self.get(tid) or {}

    def answer(self, tid: str, approve: bool, remember: bool = False) -> Dict[str, Any]:
        r = self.runners.get(tid)
        if r is None:
            raise ComputerError(409, "A tarefa não está esperando resposta.")
        if not r.answer(approve, remember):
            raise ComputerError(409, "Não há pergunta pendente nesta tarefa.")
        return {"ok": True}

    def delete(self, tid: str, purge: bool = False) -> bool:
        if tid in self.runners:
            raise ComputerError(409, "A tarefa ainda está em andamento: cancele antes de apagar.")
        f = self._file(tid)
        if not f or not f.parent.is_dir():
            return False
        shutil.rmtree(f.parent, ignore_errors=True)
        shutil.rmtree(guard.workspace() / tid, ignore_errors=True)
        if purge:
            shutil.rmtree(guard.data_dir() / "trash" / tid, ignore_errors=True)
        self.snap.pop(tid, None)
        return True

    def clear_history(self, purge: bool = False) -> int:
        n = 0
        for s in self.list(1000):
            if s["status"] in FINAL and self.delete(s["id"], purge):
                n += 1
        return n

    def undo(self, tid: str) -> Dict[str, Any]:
        if tid in self.runners:
            raise ComputerError(409, "Espere a tarefa terminar (ou cancele) para desfazer.")
        doc = self.get(tid)
        if not doc:
            raise ComputerError(404, "Tarefa não encontrada")
        entries = doc.get("journal") or []
        if not any(not e.get("undone") for e in entries):
            raise ComputerError(409, "Não há nada para desfazer nesta tarefa.")
        notes = F.undo(entries)
        doc.setdefault("undone_notes", []).extend(notes[-40:])
        doc["updated"] = now_iso()
        self.persist(doc)
        self.snap.pop(tid, None)
        return {"notes": notes, "task": self.public(doc)}

    def shot_path(self, tid: str, name: str) -> Optional[Path]:
        if not _ID.match(tid or "") or not re.fullmatch(r"[\w-]+\.(png|jpg)", name or ""):
            return None
        p = self.tasks_dir / tid / "shots" / name
        return p if p.is_file() else None

    def shutdown(self) -> None:
        for r in list(self.runners.values()):
            r.cancel()


def _files_of(doc: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for e in doc.get("journal", []):
        for k in ("path", "dst"):
            p = e.get(k)
            if p and p not in out and e.get("op") in ("create", "move", "copy", "mkdir") and not e.get("undone"):
                out.append(p)
    return out[:80]
