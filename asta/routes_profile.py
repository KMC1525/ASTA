"""Rotas HTTP do perfil do usuário (v0.21): dados, retrato e importar/exportar."""
from __future__ import annotations

import base64
import json
from typing import Any

from . import profile as prof
from .jobs import HttpError


class ProfileRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store

    def register(self) -> None:
        a = self.app.add
        a("GET", r"/api/profile", self.r_get)
        a("PUT", r"/api/profile", self.r_put)
        a("GET", r"/api/profile/portrait", self.r_portrait_get)
        a("PUT", r"/api/profile/portrait", self.r_portrait_put)
        a("POST", r"/api/profile/portrait", self.r_portrait_put)
        a("DELETE", r"/api/profile/portrait", self.r_portrait_delete)
        a("GET", r"/api/profile/export", self.r_export)
        a("POST", r"/api/profile/import", self.r_import)

    def r_get(self, req) -> None:
        p = self.store.get_profile()
        req.json(p)

    def r_put(self, req) -> None:
        body = req.body_json()
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        saved = self.store.save_profile(body)
        self.store.remember("profile", "atualizar", saved.get("name") or "Perfil", "Perfil do usuário atualizado", {"fields": [k for k in body.keys() if k != "portrait"][:20]})
        req.json(saved)

    def r_portrait_get(self, req) -> None:
        path = self.store.profile_portrait_path()
        if not path:
            raise HttpError(404, "Sem foto de perfil")
        ext = path.suffix.lower().lstrip(".")
        mime = prof.IMAGE_EXT.get(ext, "application/octet-stream")
        req.bytes(path.read_bytes(), mime)

    def r_portrait_put(self, req) -> None:
        raw = req.body_bytes(12 * 1024 * 1024)
        kind = prof.sniff_image(raw)
        if not kind:
            raise HttpError(400, "Envie uma imagem PNG, JPG, WEBP ou GIF.")
        name = self.store.save_profile_portrait(raw, kind)
        if not name:
            raise HttpError(400, "Não foi possível salvar a foto.")
        req.json(self.store.get_profile())

    def r_portrait_delete(self, req) -> None:
        self.store.clear_profile_portrait()
        req.json(self.store.get_profile())

    def r_export(self, req) -> None:
        """Exporta o perfil + presets gerais do fluxo de trabalho (sem chaves/tokens)."""
        profile = self.store.get_profile()
        portrait = self.store.profile_portrait_path()
        data = prof.export_bundle(profile, self.store.get_settings(), portrait.read_bytes() if portrait else None)
        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        req.bytes(raw, "application/json; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="asta-perfil.json"'})

    def r_import(self, req) -> None:
        body = req.body_json()
        try:
            bundle = prof.import_bundle(body)
        except ValueError as exc:
            raise HttpError(400, str(exc))
        # perfil
        p = self.store.save_profile(bundle["profile"])
        # retrato (opcional)
        pb64 = bundle.get("portrait_b64") or ""
        if isinstance(pb64, str) and pb64:
            try:
                raw = base64.b64decode(pb64, validate=False)
                kind = prof.sniff_image(raw)
                if kind:
                    self.store.save_profile_portrait(raw, kind)
                    p = self.store.get_profile()
            except Exception:
                pass
        # workflow presets (opcional, sem segredos)
        imported = []
        wf = bundle.get("workflow")
        if isinstance(wf, dict):
            try:
                from . import uiprefs
                patch = uiprefs.import_patch(wf)
                self.store.save_settings(patch)
                imported = sorted(patch)
            except Exception:
                imported = []
        self.store.remember("profile", "importar", p.get("name") or "Perfil", "Perfil importado", {"imported_settings": imported})
        req.json({"profile": p, "imported_settings": imported})
