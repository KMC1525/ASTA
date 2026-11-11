"""Rotas HTTP da memória unificada universal (v0.21)."""
from __future__ import annotations

from typing import Any

from .jobs import HttpError


class MemoryRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store

    def register(self) -> None:
        a = self.app.add
        a("GET", r"/api/memory/days", self.r_days)
        a("GET", r"/api/memory/search", self.r_search)
        a("GET", r"/api/memory/sections", self.r_sections)
        a("GET", r"/api/memory/day", self.r_day_get)
        a("PUT", r"/api/memory/day", self.r_day_put)
        a("POST", r"/api/memory/item", self.r_item_add)
        a("PUT", r"/api/memory/item", self.r_item_update)
        a("DELETE", r"/api/memory/item", self.r_item_delete)

    def r_days(self, req) -> None:
        try:
            limit = int(req.query.get("limit", ["400"])[0])
        except ValueError:
            limit = 400
        req.json(self.store.memory_days(max(1, min(2000, limit))))

    def r_search(self, req) -> None:
        q = req.query.get("q", [""])[0]
        section = req.query.get("section", [""])[0]
        try:
            limit = int(req.query.get("limit", ["200"])[0])
        except ValueError:
            limit = 200
        req.json(self.store.memory_search(q, section, max(1, min(1000, limit))))

    def r_sections(self, req) -> None:
        req.json({"sections": self.store.memory_sections()})

    def _date(self, req, body: Any = None) -> str:
        date = req.query.get("date", [""])[0]
        if not date and isinstance(body, dict):
            date = str(body.get("date") or "")
        if not date:
            raise HttpError(400, "Informe a data (YYYY-MM-DD).")
        return date

    def r_day_get(self, req) -> None:
        date = self._date(req)
        day = self.store.memory_day(date)
        if day is None:
            raise HttpError(400, "Data inválida.")
        req.json(day)

    def r_day_put(self, req) -> None:
        body = req.body_json()
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        date = self._date(req, body)
        try:
            req.json(self.store.memory_write_day(date, body))
        except ValueError as exc:
            raise HttpError(400, str(exc))

    def r_item_add(self, req) -> None:
        body = req.body_json()
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        item = self.store.remember(str(body.get("section") or "asta"), str(body.get("action") or "note"), str(body.get("title") or ""), str(body.get("summary") or ""), body.get("detail"), body.get("tags"), str(body.get("ts") or "") or None)
        if not item:
            raise HttpError(500, "Não foi possível salvar a memória.")
        req.json(item)

    def r_item_update(self, req) -> None:
        body = req.body_json()
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        date = self._date(req, body)
        item_id = str(body.get("id") or "")
        if not item_id:
            raise HttpError(400, "Informe o id da memória.")
        try:
            req.json(self.store.memory_update_item(date, item_id, body))
        except ValueError as exc:
            raise HttpError(404 if "encontr" in str(exc).lower() else 400, str(exc))

    def r_item_delete(self, req) -> None:
        body = req.body_json()
        date = self._date(req, body if isinstance(body, dict) else None)
        item_id = req.query.get("id", [""])[0]
        if not item_id and isinstance(body, dict):
            item_id = str(body.get("id") or "")
        if not item_id:
            raise HttpError(400, "Informe o id da memória.")
        ok = self.store.memory_delete_item(date, item_id)
        req.json({"ok": ok})
