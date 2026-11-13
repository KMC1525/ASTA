"""Rotas HTTP dos jogos 2D: gêneros e geração por IA (a biblioteca/jogar/baixar reaproveitam /api/projects e /play)."""
from __future__ import annotations

import json
from typing import Any

from .agents.game_pipeline import GamePipeline
from .games2d import GENRES
from .games2d import schema as S
from .jobs import HttpError, Job
from .team import request_team as _team_of
from .util import text


class GameRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store

    def register(self) -> None:
        self.app.add("GET", r"/api/games/genres", self.r_genres)
        self.app.add("POST", r"/api/games/generate", self.r_generate)
        self.app.add("POST", r"/api/games/rebuild", self.r_rebuild)
        self.app.add("GET", r"/api/games/rebuild/notice", self.r_notice)

    def r_genres(self, req) -> None:
        req.json([{"id": k, **v} for k, v in GENRES.items()])

    def r_notice(self, req) -> None:
        from .rebuild import ENGINES, NOTICE_EN, NOTICE_PT

        req.json({"pt": NOTICE_PT, "en": NOTICE_EN, "engines": ENGINES})

    def r_rebuild(self, req) -> None:
        """Reconstrói um jogo Ren'Py / RPG Maker (2000 → MZ) enviado como ZIP (ou arquivos soltos) nos motores 2D do ASTA. Job com SSE; sem IA."""
        from .rebuild.pipeline import RebuildPipeline

        body = req.body_json()
        running = self.app.jobs.running("game_rebuild")
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))
        ids = [x for x in (body.get("attachment_ids") if isinstance(body.get("attachment_ids"), list) else []) if isinstance(x, str)][:40]
        if not ids:
            raise HttpError(400, "Anexe o ZIP do jogo (ou os arquivos de dados/scripts) para reconstruí-lo.")

        def work(job: Job) -> None:
            RebuildPipeline(self.store, job.emit, lambda: job.cancelled).run({"attachment_ids": ids, "team": _team_of(body), "refine": (body["refine"] is not False) if "refine" in body else bool((self.store.get_settings().get("rebuild") or {}).get("refine", True))})

        job = self.app.jobs.start("game_rebuild", work)
        req.json({"job_id": job.id})

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
            "prompt": text(body.get("prompt"), "", 20000), "attachment_ids": [x for x in (body.get("attachment_ids") if isinstance(body.get("attachment_ids"), list) else []) if isinstance(x, str)][:40],
            "genre": body.get("genre") if body.get("genre") in S.GENRE_IDS else "auto",
            "length": body.get("length") if body.get("length") in S.LENGTHS else "",
            "content": "sfw" if body.get("content") == "sfw" else ("free" if body.get("content") == "free" else ""),
            "project_id": text(body.get("project_id"), "", 60), "language": text(body.get("language"), "", 12),
            "team": _team_of(body),
        }

        def work(job: Job) -> None:
            GamePipeline(self.store, job.emit, lambda: job.cancelled).run(pipeline_req)

        job = self.app.jobs.start("game_generate", work)
        req.json({"job_id": job.id})
