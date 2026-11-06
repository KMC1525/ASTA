"""Rotas do login com a conta do provedor (OpenRouter por OAuth). Só no computador onde o ASTA roda."""
from __future__ import annotations

import html
from typing import Any

from . import oauth
from .jobs import HttpError

DONE_HTML = """<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ASTA</title>
<body style="font-family:system-ui;background:#000;color:#eee;max-width:30em;margin:14vh auto;padding:0 20px;line-height:1.5"><h1 style="font-weight:600">{title}</h1><p>{msg}</p>
<p><a style="color:#9cf" href="/#/config">ASTA → Configuração</a></p>{script}"""


class AuthRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store

    def register(self) -> None:
        self.app.add("POST", r"/api/auth/openrouter/start", self.r_start)
        self.app.add("GET", r"/api/auth/openrouter/callback", self.r_callback)

    def _local_only(self, req) -> None:
        if self.app.mobile.is_remote(req.h.client_address[0], req.headers):
            raise HttpError(403, "O login da conta só pode ser feito no computador onde o ASTA roda.")

    def r_start(self, req) -> None:
        self._local_only(req)
        host = req.headers.get("Host", "") or f"localhost:{req.h.server.server_address[1]}"
        req.json({"url": oauth.start_openrouter(host)})

    def r_callback(self, req) -> None:
        self._local_only(req)
        state = (req.query.get("state") or [""])[0]
        code = (req.query.get("code") or [""])[0]
        try:
            key = oauth.finish_openrouter(state, code)
            self.store.save_settings({"providers": {"openrouter": {"api_key": key, "auth": "account"}}})
            page = DONE_HTML.format(title="Conta conectada ✓", msg="Sua conta do OpenRouter está conectada ao ASTA. Pode fechar esta aba.",
                                    script="<script>try{window.opener&&window.opener.postMessage('asta-auth-ok','*')}catch(e){}setTimeout(function(){try{window.close()}catch(e){}},1200)</script>")
            status = 200
        except ValueError as exc:
            page = DONE_HTML.format(title="Não deu certo", msg=html.escape(str(exc)), script="")
            status = 400
        req.bytes(page.encode("utf-8"), "text/html; charset=utf-8", status)
