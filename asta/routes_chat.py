"""Rotas do Chat geral: conversas, envio com streaming (SSE), responder de novo e a lista de provedores/modelos do seletor."""
from __future__ import annotations

import traceback
from typing import Any

from .assistant_chat import AssistantChat, title_from
from .jobs import HttpError
from .providers import PRESETS, ProviderError, provider_config, resolve_provider
from .providers import auto
from .util import text


class ChatRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store
        self.engine = AssistantChat(app.store)

    def register(self) -> None:
        a = self.app.add
        a("GET", r"/api/chats", self.r_list)
        a("POST", r"/api/chats", self.r_create)
        a("GET", r"/api/chats/(?P<cid>[\w-]+)", self.r_get)
        a("PUT", r"/api/chats/(?P<cid>[\w-]+)", self.r_rename)
        a("DELETE", r"/api/chats/(?P<cid>[\w-]+)", self.r_delete)
        a("POST", r"/api/chats/(?P<cid>[\w-]+)/send", self.r_send)
        a("POST", r"/api/chats/(?P<cid>[\w-]+)/regenerate", self.r_regenerate)
        a("GET", r"/api/chat/providers", self.r_providers)

    # ----- conversas
    def _chat(self, cid: str):
        chat = self.store.chats.get(cid)
        if not chat:
            raise HttpError(404, "Conversa não encontrada")
        return chat

    @staticmethod
    def _summary(c: dict) -> dict:
        last = c["messages"][-1] if c["messages"] else None
        return {"id": c["id"], "title": c["title"] or "Novo chat", "updated": c["updated"], "count": len(c["messages"]), "last": last["text"][:100] if last else ""}

    def r_list(self, req) -> None:
        req.json([self._summary(c) for c in self.store.chats.list()])

    def r_create(self, req) -> None:
        body = req.body_json()
        req.json(self.engine.create(text(body.get("title"), "", 80) if isinstance(body, dict) else ""))

    def r_get(self, req, cid: str) -> None:
        req.json(self._chat(cid))

    def r_rename(self, req, cid: str) -> None:
        chat = self._chat(cid)
        body = req.body_json()
        title = text(body.get("title"), "", 80) if isinstance(body, dict) else ""
        chat["title"] = title or title_from(chat["messages"][0]["text"] if chat["messages"] else "")
        req.json(self._summary(self.store.chats.save(chat, cid)))

    def r_delete(self, req, cid: str) -> None:
        self._chat(cid)
        self.store.chats.delete(cid)
        req.json({"ok": True})

    def _stream(self, req, fn) -> None:
        """Roda `fn(emit)` respondendo em SSE; erros viram eventos (a resposta já começou)."""
        req.sse_start()
        try:
            fn(req.sse_send)
        except ProviderError as exc:
            req.sse_send({"type": "error", "message": str(exc), "kind": "provider"})
        except ValueError as exc:
            req.sse_send({"type": "error", "message": str(exc), "kind": "validation"})
        except (BrokenPipeError, ConnectionResetError):  # o navegador fechou a conexão (botão Parar): a resposta cortada não é salva
            raise
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            req.sse_send({"type": "error", "message": f"Erro inesperado: {str(exc) or exc.__class__.__name__}", "kind": "internal"})

    def r_send(self, req, cid: str) -> None:
        self._chat(cid)
        body = req.body_json()
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        message = text(body.get("text"), "", 12000)
        ids = [text(i, "", 60) for i in body.get("attachment_ids")][:20] if isinstance(body.get("attachment_ids"), list) else []
        if not message and not ids:
            raise HttpError(400, "Escreva uma mensagem.")
        self._stream(req, lambda emit: self.engine.send(cid, message, ids, emit))

    def r_regenerate(self, req, cid: str) -> None:
        self._chat(cid)
        self._stream(req, lambda emit: self.engine.regenerate(cid, emit))

    # ----- seletor de modelo
    def r_providers(self, req) -> None:
        """Provedores para o seletor de modelo do Chat: o que está em uso agora e o que dá para escolher (com o modelo de cada um)."""
        settings = self.store.get_settings()
        try:
            _, current = resolve_provider(settings, "generation", self.store.models_dir)
        except ProviderError as exc:
            current = {"id": settings["active"].get("generation", "demo"), "label": "", "model": "", "demo": False, "auto": False, "reason": str(exc)}
        items = []
        for pid, preset in PRESETS.items():
            if pid == "demo":
                continue
            cfg = provider_config(settings, pid)
            items.append({"id": pid, "label": preset["label"], "kind": preset["kind"], "local": bool(preset.get("local")), "needs_key": bool(preset.get("needs_key")),
                          "has_key": bool(cfg.get("api_key")), "model": cfg.get("model") or "", "usable": auto.usable(settings, pid, self.store.models_dir),
                          "selected": current.get("id") == pid})
        items.sort(key=lambda i: (not i["selected"], not i["usable"], not i["local"], i["label"].lower()))
        req.json({"current": current, "providers": items})
