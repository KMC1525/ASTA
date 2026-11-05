"""Rotas HTTP dos avatars: cards, retrato, memória, geração por IA e conversas (SSE)."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from .agents.avatar_pipeline import AvatarPipeline
from .agents.avatar_prompt import AvatarPromptPipeline
from .avatar_chat import ChatEngine
from .avatars import MAX_CHAT_AVATARS, avatar_from_png, export_card_v2, import_avatar
from .jobs import HttpError, Job
from .providers import ProviderError, resolve_provider
from .util import text

IMAGE_MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}


def sniff_image(data: bytes) -> str:
    """Tipo da imagem pelos bytes iniciais (não confia em Content-Type nem em extensão)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpg"
    if data[:4] == b"GIF8":
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return ""


class AvatarRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store
        self.engine = ChatEngine(app.store)

    def register(self) -> None:
        a = self.app.add
        a("GET", r"/api/avatars", self.r_list)
        a("POST", r"/api/avatars", self.r_create)
        a("POST", r"/api/avatars/import", self.r_import)
        a("POST", r"/api/avatars/generate", self.r_generate)
        a("POST", r"/api/avatars/system-prompt", self.r_system_prompt)
        a("GET", r"/api/avatars/engine", self.r_engine)
        a("GET", r"/api/avatars/(?P<aid>[\w-]+)", self.r_get)
        a("PUT", r"/api/avatars/(?P<aid>[\w-]+)", self.r_update)
        a("DELETE", r"/api/avatars/(?P<aid>[\w-]+)", self.r_delete)
        a("GET", r"/api/avatars/(?P<aid>[\w-]+)/export", self.r_export)
        a("GET", r"/api/avatars/(?P<aid>[\w-]+)/portrait", self.r_portrait_get)
        a("PUT", r"/api/avatars/(?P<aid>[\w-]+)/portrait", self.r_portrait_put)
        a("POST", r"/api/avatars/(?P<aid>[\w-]+)/portrait", self.r_portrait_put)
        a("DELETE", r"/api/avatars/(?P<aid>[\w-]+)/portrait", self.r_portrait_delete)
        a("GET", r"/api/avatars/(?P<aid>[\w-]+)/memory", self.r_memory_get)
        a("DELETE", r"/api/avatars/(?P<aid>[\w-]+)/memory", self.r_memory_delete)

        a("GET", r"/api/avatar-chats", self.r_chats)
        a("POST", r"/api/avatar-chats", self.r_chat_create)
        a("GET", r"/api/avatar-chats/(?P<cid>[\w-]+)", self.r_chat_get)
        a("PUT", r"/api/avatar-chats/(?P<cid>[\w-]+)", self.r_chat_update)
        a("DELETE", r"/api/avatar-chats/(?P<cid>[\w-]+)", self.r_chat_delete)
        a("POST", r"/api/avatar-chats/(?P<cid>[\w-]+)/send", self.r_chat_send)
        a("POST", r"/api/avatar-chats/(?P<cid>[\w-]+)/tick", self.r_chat_tick)
        a("POST", r"/api/avatar-chats/(?P<cid>[\w-]+)/reset", self.r_chat_reset)

    # ------------------------------------------------------------------ cards
    def _avatar(self, aid: str) -> Dict[str, Any]:
        card = self.store.avatars.get(aid)
        if not card:
            raise HttpError(404, "Avatar não encontrado")
        return card

    def r_list(self, req) -> None:
        req.json(self.store.avatars.list())

    def r_create(self, req) -> None:
        body = req.body_json()
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        body = dict(body, portrait="")  # o retrato só entra pelo endpoint próprio
        req.json(self.store.avatars.save(body, None))

    def r_get(self, req, aid: str) -> None:
        req.json(self._avatar(aid))

    def r_update(self, req, aid: str) -> None:
        old = self._avatar(aid)
        body = req.body_json()
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        body = dict(body, portrait=old.get("portrait", ""))
        req.json(self.store.avatars.save(body, aid))

    def r_delete(self, req, aid: str) -> None:
        if not self.store.delete_avatar(aid):
            raise HttpError(404, "Avatar não encontrado")
        req.json({"ok": True})

    def r_import(self, req) -> None:
        raw = req.body_bytes(12 * 1024 * 1024)
        try:
            card = avatar_from_png(raw) if raw[:4] == b"\x89PNG" else import_avatar(json.loads(raw.decode("utf-8")))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HttpError(400, f"Não foi possível importar: {exc}")
        saved = self.store.avatars.save(card)
        if raw[:4] == b"\x89PNG":  # o PNG do card já é a imagem do personagem
            self.store.save_portrait(saved["id"], raw, "png")
            saved = self.store.avatars.get(saved["id"]) or saved
        req.json(saved)

    def r_export(self, req, aid: str) -> None:
        card = self._avatar(aid)
        fmt = req.query.get("format", ["asta"])[0]
        req.json(export_card_v2(card) if fmt in ("card_v2", "v2", "sillytavern") else card)

    # ------------------------------------------------------------------ retrato
    def r_portrait_get(self, req, aid: str) -> None:
        self._avatar(aid)
        path = self.store.portrait_path(aid)
        if not path:
            raise HttpError(404, "Sem retrato")
        req.file(path, IMAGE_MIME.get(path.suffix.lstrip(".").lower(), "application/octet-stream"), cache=True)

    def r_portrait_put(self, req, aid: str) -> None:
        self._avatar(aid)
        data = req.body_bytes(8 * 1024 * 1024)
        kind = sniff_image(data)
        if not kind:
            raise HttpError(400, "Envie uma imagem PNG, JPG, WebP ou GIF (até 8 MB).")
        self.store.save_portrait(aid, data, kind)
        req.json(self._avatar(aid))

    def r_portrait_delete(self, req, aid: str) -> None:
        self._avatar(aid)
        self.store.clear_portrait(aid)
        req.json(self._avatar(aid))

    # ------------------------------------------------------------------ memória
    def r_memory_get(self, req, aid: str) -> None:
        self._avatar(aid)
        req.json({"memories": self.store.get_memories(aid)})

    def r_memory_delete(self, req, aid: str) -> None:
        self._avatar(aid)
        self.store.clear_memories(aid)
        req.json({"ok": True})

    # ------------------------------------------------------------------ geração por IA
    def r_generate(self, req) -> None:
        body = req.body_json()
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        if self.app.jobs.running("avatar_generate"):
            raise HttpError(409, json.dumps({"job_id": self.app.jobs.running("avatar_generate").id}))
        if not (text(body.get("prompt"), "") or body.get("attachment_ids")):
            raise HttpError(400, "Descreva o avatar ou anexe algo (imagem, texto, documento…) para criá-lo.")
        if body.get("from_images") and not body.get("attachment_ids"):
            raise HttpError(400, "Anexe pelo menos uma imagem (foto ou arte) para usá-la como base do avatar.")
        pipeline_req = {
            "prompt": text(body.get("prompt"), "", 12000), "attachment_ids": list(body.get("attachment_ids") or [])[:40],
            "from_images": bool(body.get("from_images")), "images_mode": "one" if body.get("images_mode") == "one" else "each",
            "count": body.get("count") or 0, "relationship": text(body.get("relationship"), "auto", 12),
            "content": "nsfw" if body.get("content") == "nsfw" else "sfw", "language": text(body.get("language"), "", 12),
            "character_type": text(body.get("character_type"), "auto", 10), "prompt_pipeline": body.get("prompt_pipeline") is not False,
            "detail": text(body.get("detail"), "detailed", 10),
        }

        def work(job: Job) -> None:
            AvatarPipeline(self.store, job.emit, lambda: job.cancelled).run(pipeline_req)

        job = self.app.jobs.start("avatar_generate", work)
        req.json({"job_id": job.id})

    def r_engine(self, req) -> None:
        """Qual IA responde nas conversas dos avatars agora (e, se for só o Demo, por quê)."""
        try:
            _, info = resolve_provider(self.store.get_settings(), "characters", self.store.models_dir)
        except ProviderError as exc:
            raise HttpError(400, str(exc))
        req.json(info)

    def r_system_prompt(self, req) -> None:
        """Pipeline Analisa → Gera → Revisa → Entrega do system prompt de um avatar (existente ou rascunho do editor)."""
        body = req.body_json()
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        running = self.app.jobs.running("avatar_prompt")
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))
        draft = body.get("draft") if isinstance(body.get("draft"), dict) else {}
        pipeline_req = {
            "avatar_id": text(body.get("avatar_id"), "", 60), "draft": {k: v for k, v in draft.items() if isinstance(k, str)},
            "instructions": text(body.get("instructions"), "", 4000), "content": "nsfw" if body.get("content") == "nsfw" else "sfw",
            "character_type": text(body.get("character_type"), "auto", 10), "detail": text(body.get("detail"), "detailed", 10), "apply": bool(body.get("apply")),
        }
        if pipeline_req["avatar_id"] and not self.store.avatars.get(pipeline_req["avatar_id"]):
            raise HttpError(404, "Avatar não encontrado")

        def work(job: Job) -> None:
            AvatarPromptPipeline(self.store, job.emit, lambda: job.cancelled).run(pipeline_req)

        job = self.app.jobs.start("avatar_prompt", work)
        req.json({"job_id": job.id})

    # ------------------------------------------------------------------ conversas
    def _chat(self, cid: str) -> Dict[str, Any]:
        chat = self.store.avatar_chats.get(cid)
        if not chat:
            raise HttpError(404, "Conversa não encontrada")
        return chat

    def _summary(self, chat: Dict[str, Any]) -> Dict[str, Any]:
        last = chat["messages"][-1] if chat["messages"] else None
        return {"id": chat["id"], "title": chat["title"], "mode": chat["mode"], "avatar_ids": chat["avatar_ids"], "content": chat["content"],
                "auto_talk": chat["auto_talk"], "updated": chat["updated"], "count": len(chat["messages"]),
                "last": {"name": last["name"], "text": last["text"][:120], "role": last["role"]} if last else None}

    def r_chats(self, req) -> None:
        req.json([self._summary(c) for c in self.store.avatar_chats.list()])

    def r_chat_create(self, req) -> None:
        body = req.body_json()
        ids: List[str] = [text(i, "", 60) for i in (body.get("avatar_ids") or [])][:MAX_CHAT_AVATARS]
        if not ids:
            raise HttpError(400, "Escolha pelo menos um avatar.")
        if len(ids) == 1 and body.get("reuse"):  # "Conversar" volta à conversa single já existente do avatar
            for c in self.store.avatar_chats.list():
                if c["avatar_ids"] == ids:
                    req.json(c)
                    return
        try:
            chat = self.engine.create_chat(ids, title=text(body.get("title"), "", 80), content=text(body.get("content"), "auto", 6),
                                           user_name=text(body.get("user_name"), "", 40), user_persona=text(body.get("user_persona"), "", 1000),
                                           **({"auto_talk": bool(body["auto_talk"])} if "auto_talk" in body else {}))
        except ValueError as exc:
            raise HttpError(400, str(exc))
        req.json(chat)

    def r_chat_get(self, req, cid: str) -> None:
        chat = self._chat(cid)
        avatars = [a for a in (self.store.avatars.get(i) for i in chat["avatar_ids"]) if a]
        req.json({**chat, "avatars": avatars})

    def r_chat_update(self, req, cid: str) -> None:
        chat = self._chat(cid)
        body = req.body_json()
        for key in ("title", "content", "user_name", "user_persona", "auto_talk"):
            if key in body:
                chat[key] = body[key]
        req.json(self._summary(self.store.avatar_chats.save(chat, cid)))

    def r_chat_delete(self, req, cid: str) -> None:
        self._chat(cid)
        self.store.avatar_chats.delete(cid)
        req.json({"ok": True})

    def r_chat_reset(self, req, cid: str) -> None:
        chat = self._chat(cid)
        chat["messages"], chat["autonomous_turns"] = [], 0
        req.json(self._summary(self.store.avatar_chats.save(chat, cid)))

    def _stream(self, req, fn) -> None:
        """Roda `fn(emit)` respondendo em SSE; erros viram eventos (a resposta já começou)."""
        req.sse_start()
        try:
            fn(req.sse_send)
        except ProviderError as exc:
            req.sse_send({"type": "error", "message": str(exc), "kind": "provider"})
        except ValueError as exc:
            req.sse_send({"type": "error", "message": str(exc), "kind": "validation"})

    def r_chat_send(self, req, cid: str) -> None:
        self._chat(cid)
        body = req.body_json()
        message = text(body.get("text"), "", 6000)
        if not message:
            raise HttpError(400, "Escreva uma mensagem.")
        self._stream(req, lambda emit: self.engine.send(cid, message, emit))

    def r_chat_tick(self, req, cid: str) -> None:
        self._chat(cid)
        more = bool(req.body_json().get("more"))
        self._stream(req, lambda emit: self.engine.tick(cid, emit, more=more))
