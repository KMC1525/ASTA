"""Rotas do celular/tablet: pareamento por QR, informação para a tela do computador e a versão (para o app avisar de atualizações)."""
from __future__ import annotations

from typing import Any

from . import __version__
from .jobs import HttpError
from .mobile import COOKIE, Mobile, is_loopback


class MobileRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.mobile: Mobile = app.mobile

    def register(self) -> None:
        self.app.add("GET", r"/api/version", self.r_version)
        self.app.add("GET", r"/api/mobile", self.r_info)
        self.app.add("POST", r"/api/mobile/rotate", self.r_rotate)
        self.app.add("GET", r"/api/mobile/pair", self.r_pair)

    def r_version(self, req) -> None:
        req.json({"version": __version__})

    def _local_only(self, req) -> None:
        if self.mobile.strict and self.mobile.cookie_ok(req.headers.get("Cookie", "")):
            return   # app Android: quem tem o cookie do app é o dono do aparelho
        if self.mobile.is_remote(req.h.client_address[0], req.headers):
            raise HttpError(403, "Só no computador onde o ASTA roda.")

    def r_info(self, req) -> None:
        self._local_only(req)
        d = self.mobile.info(req.h.server.server_address[1])
        d["version"] = __version__
        req.json(d)

    def r_rotate(self, req) -> None:
        """Gera um código novo: todos os aparelhos pareados precisam escanear de novo."""
        self._local_only(req)
        self.mobile.rotate()
        req.json(self.mobile.info(req.h.server.server_address[1]))

    def r_pair(self, req) -> None:
        code = (req.query.get("code") or [""])[0]
        if not self.mobile.pair_ok(code):
            raise HttpError(403, "Código de pareamento inválido ou antigo: escaneie o QR code atual no computador.")
        h = req.h
        h.send_response(302)
        h.send_header("Location", "/")
        h.send_header("Set-Cookie", f"{COOKIE}={self.mobile.token()}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax")
        h.send_header("Cache-Control", "no-store")
        h.send_header("Content-Length", "0")
        h.end_headers()
