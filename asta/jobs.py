"""Tarefas em segundo plano (com eventos para SSE) e o erro HTTP usado pelas rotas.

Fica separado do servidor para que os módulos de rotas (avatars, jogos 2D, canvas)
possam usá-lo sem import circular.
"""
from __future__ import annotations

import threading
import time
import traceback
from typing import Callable, Dict, List, Optional

from .agents.runner import Cancelled
from .providers import ProviderError
from .util import new_id


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Job:
    def __init__(self, kind: str):
        self.id = new_id("j_")
        self.kind = kind
        self.events: List[dict] = []
        self.status = "running"  # running | done | error | cancelled
        self.cond = threading.Condition()
        self._cancel = threading.Event()
        self.created = time.time()
        self.result: Optional[dict] = None

    def emit(self, ev: dict) -> None:
        with self.cond:
            ev = dict(ev)
            ev["seq"] = len(self.events)
            self.events.append(ev)
            if len(self.events) > 2000:
                del self.events[:500]
            self.cond.notify_all()

    def finish(self, status: str, result: Optional[dict] = None) -> None:
        with self.cond:
            self.status = status
            self.result = result
            self.cond.notify_all()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()


class JobManager:
    def __init__(self) -> None:
        self.jobs: Dict[str, Job] = {}
        self.lock = threading.Lock()

    def start(self, kind: str, fn: Callable[[Job], Optional[dict]]) -> Job:
        job = Job(kind)
        with self.lock:
            for jid in [j for j, x in self.jobs.items() if x.status != "running" and time.time() - x.created > 3600]:
                self.jobs.pop(jid, None)
            self.jobs[job.id] = job

        def run() -> None:
            from . import scheduler

            scheduler.set_priority(scheduler.BACKGROUND)   # a conversa que o usuário espera passa na frente de uma geração longa no modelo local embutido
            try:
                res = fn(job)
                job.finish("done", res)
            except Cancelled:
                job.emit({"type": "cancelled"})
                job.finish("cancelled")
            except ProviderError as exc:
                if str(exc) == "cancelado":
                    job.emit({"type": "cancelled"})
                    job.finish("cancelled")
                else:
                    job.emit({"type": "error", "message": str(exc), "kind": "provider"})
                    job.finish("error")
            except ValueError as exc:  # entrada inválida: mensagem para o usuário, sem traceback
                job.emit({"type": "error", "message": str(exc), "kind": "validation"})
                job.finish("error")
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                job.emit({"type": "error", "message": str(exc) or exc.__class__.__name__, "kind": "internal"})
                job.finish("error")

        threading.Thread(target=run, daemon=True, name=f"job-{job.id}").start()
        return job

    def get(self, jid: str) -> Optional[Job]:
        return self.jobs.get(jid)

    def running(self, kind: str) -> Optional[Job]:
        return next((j for j in self.jobs.values() if j.kind == kind and j.status == "running"), None)
