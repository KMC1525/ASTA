"""Rotas HTTP dos jogos 2D: gêneros e geração por IA (a biblioteca/jogar/baixar reaproveitam /api/projects e /play)."""
from __future__ import annotations

import json
from typing import Any

from .agents.game_pipeline import GamePipeline
from .games2d import GENRES
from .games2d import schema as S
from .jobs import HttpError, Job
from .util import text


class GameRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store

    def register(self) -> None:
        self.app.add("GET", r"/api/games/genres", self.r_genres)
        self.app.add("POST", r"/api/games/generate", self.r_generate)

    def r_genres(self, req) -> None:
        req.json([{"id": k, **v} for k, v in GENRES.items()])

    def r_generate(self, req) -> None:
        body = req.body_json()
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        running = self.app.jobs.running("game_generate")
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))
        if not (text(body.get("prompt"), "") or body.get("attachment_ids")):
            raise HttpError(400, "Descreva o jogo que você quer criar (ou anexe algo) para gerá-lo.")
        pipeline_req = {
            "prompt": text(body.get("prompt"), "", 20000), "attachment_ids": list(body.get("attachment_ids") or [])[:40],
            "genre": body.get("genre") if body.get("genre") in S.GENRE_IDS else "auto",
            "length": body.get("length") if body.get("length") in S.LENGTHS else "",
            "content": "sfw" if body.get("content") == "sfw" else ("free" if body.get("content") == "free" else ""),
            "project_id": text(body.get("project_id"), "", 60), "language": text(body.get("language"), "", 12),
        }

        def work(job: Job) -> None:
            GamePipeline(self.store, job.emit, lambda: job.cancelled).run(pipeline_req)

        job = self.app.jobs.start("game_generate", work)
        req.json({"job_id": job.id})
