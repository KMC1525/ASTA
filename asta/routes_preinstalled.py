"""Rotas dos modelos pré-instalados (texto e imagem): estado e instalação com um clique."""
from __future__ import annotations

import json
import time
from typing import Any

from . import preinstalled
from .jobs import HttpError, Job
from .providers import ProviderError
from .util import text


class PreinstalledRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store

    def register(self) -> None:
        self.app.add("GET", r"/api/preinstalled", self.r_list)
        self.app.add("POST", r"/api/preinstalled/install", self.r_install)

    def r_list(self, req) -> None:
        req.json({"models": preinstalled.status(self.store.models_dir)})

    def r_install(self, req) -> None:
        body = req.body_json()
        try:
            e = preinstalled.entry(text(body.get("id"), "", 60))
        except ProviderError as exc:
            raise HttpError(404, str(exc))
        running = self.app.jobs.running("preinstalled")
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))
        token = (self.store.get_settings().get("hf") or {}).get("token", "")

        def work(job: Job) -> None:
            job.emit({"type": "start", "id": e["id"], "label": e["label"], "quant": e["quant"]})
            last = [0.0]

            def progress(done: int, total: int) -> None:
                if time.time() - last[0] > 0.4:
                    last[0] = time.time()
                    job.emit({"type": "progress", "done": done, "total": total})

            r = preinstalled.install(self.store, e["id"], token, progress, lambda: job.cancelled)
            job.emit({"type": "done", "id": e["id"], "notes": r["notes"]})

        job = self.app.jobs.start("preinstalled", work)
        req.json({"job_id": job.id})
