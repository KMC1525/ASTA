"""Rotas do Chat geral: conversas, envio com streaming (SSE), responder de novo e a lista de provedores/modelos do seletor."""
from __future__ import annotations

import traceback
from typing import Any

from . import websearch
from .assistant_chat import MAX_USER_CHARS, AssistantChat, title_from
from .jobs import HttpError
from .providers import PRESETS, ProviderError, provider_config, resolve_provider
from .providers import auto
from .providers import thinking as think
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
        a("POST", r"/api/web/search", self.r_web_search)
        a("POST", r"/api/web/context", self.r_web_context)

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
        message = text(body.get("text"), "", MAX_USER_CHARS)
        ids = [text(i, "", 60) for i in body.get("attachment_ids")][:20] if isinstance(body.get("attachment_ids"), list) else []
        if not message and not ids:
            raise HttpError(400, "Escreva uma mensagem.")
        self._stream(req, lambda emit: self.engine.send(cid, message, ids, emit, web=bool(body.get("web"))))

    def r_regenerate(self, req, cid: str) -> None:
        self._chat(cid)
        body = req.body_json()
        web = bool(body.get("web")) if isinstance(body, dict) else False
        self._stream(req, lambda emit: self.engine.regenerate(cid, emit, web=web))

    # ----- busca na web (também usada pelas ferramentas de criação: «pesquisar na web» entra no prompt)
    def _query(self, req) -> str:
        body = req.body_json()
        q = text(body.get("query"), "", 300) if isinstance(body, dict) else ""
        if not q:
            raise HttpError(400, "Escreva o que pesquisar.")
        return q

    def _ui_lang(self) -> str:
        return "pt" if str(self.store.get_settings().get("language") or "auto").lower().startswith("pt") else "auto"

    def r_web_search(self, req) -> None:
        """Só a busca (títulos, links e trechos) — usado pelo botão «Testar busca» em Configuração → Chat."""
        try:
            found = websearch.search(self._query(req), self.store.get_settings(), ui_lang=self._ui_lang())
        except websearch.SearchError as exc:
            raise HttpError(502, str(exc)) from None
        req.json({"engine": found["engine"], "query": found["query"], "sources": [{"n": i, "title": r["title"], "url": r["url"], "snippet": r["snippet"],
                                                                                    "host": (r["url"].split("/")[2] if r["url"].count("/") >= 2 else "")} for i, r in enumerate(found["results"], 1)]})

    def r_web_context(self, req) -> None:
        """Busca + leitura das páginas: devolve o bloco de texto com fontes numeradas, para anexar ao prompt de uma ferramenta de criação."""
        try:
            got = websearch.gather(self._query(req), self.store.get_settings(), ui_lang=self._ui_lang())
        except websearch.SearchError as exc:
            raise HttpError(502, str(exc)) from None
        req.json({"engine": got["engine"], "query": got["query"], "text": got["text"], "sources": websearch.public_sources(got["sources"])})

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
        sup = think.support(current.get("id", ""), current.get("model", ""))
        chat_cfg = settings.get("chat") or {}
        current = dict(current, thinking={**sup, "level": think.normalize(chat_cfg.get("thinking")) if sup["supported"] else "off"})
        req.json({"current": current, "providers": items, "web_default": bool((chat_cfg.get("web") or {}).get("default")), "thinking_levels": [[k, think.LABELS[k]] for k in think.LEVELS]})
