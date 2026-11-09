"""Rotas HTTP do Computer Use: estado e capacidades do computador, tarefas (criar, acompanhar, cancelar, responder Sim/Não, desfazer, repetir, apagar), histórico, eventos ao vivo (SSE),
capturas de tela, os prompts internos (leitura) e o inventário de programas e jogos."""
from __future__ import annotations

from typing import Any, Dict

from . import team as teamlib
from .computer import ComputerError, ComputerManager, promptlib
from .computer import osdrv, rulebased
from .jobs import HttpError
from .util import new_id, now_iso, text


def _http(exc: ComputerError) -> HttpError:
    return HttpError(exc.status, exc.message)


class ComputerRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store
        self.m = ComputerManager(app.store)
        app.computer = self.m
        self.m.on_finish.append(self._sync_chat)

    def register(self) -> None:
        a = self.app.add
        a("GET", r"/api/computer/status", self.r_status)
        a("GET", r"/api/computer/inventory", self.r_inventory)
        a("GET", r"/api/computer/prompts", self.r_prompts)
        a("GET", r"/api/computer/prompts/(?P<name>[\w/.-]+)", self.r_prompt)
        a("GET", r"/api/computer/events", self.r_events)
        a("GET", r"/api/computer/tasks", self.r_list)
        a("POST", r"/api/computer/tasks", self.r_create)
        a("GET", r"/api/computer/tasks/(?P<tid>[\w-]+)", self.r_get)
        a("DELETE", r"/api/computer/tasks/(?P<tid>[\w-]+)", self.r_delete)
        a("POST", r"/api/computer/tasks/(?P<tid>[\w-]+)/cancel", self.r_cancel)
        a("POST", r"/api/computer/tasks/(?P<tid>[\w-]+)/answer", self.r_answer)
        a("POST", r"/api/computer/tasks/(?P<tid>[\w-]+)/undo", self.r_undo)
        a("POST", r"/api/computer/tasks/(?P<tid>[\w-]+)/retry", self.r_retry)
        a("GET", r"/api/computer/tasks/(?P<tid>[\w-]+)/shots/(?P<name>[\w-]+\.(?:png|jpg))", self.r_shot)
        a("POST", r"/api/computer/history/clear", self.r_clear)

    @staticmethod
    def _body(req) -> Dict[str, Any]:
        b = req.body_json()
        return b if isinstance(b, dict) else {}

    # ----- estado
    def r_status(self, req) -> None:
        req.json(self.m.status())

    def r_inventory(self, req) -> None:
        """O que o ASTA achou neste computador (programas e jogos): ajuda o usuário a saber o que o Computer Use enxerga."""
        drv = self.m.driver
        cfg = self.m.config()
        try:
            apps = drv.apps(refresh=True)
        except Exception:  # noqa: BLE001
            apps = []
        try:
            games = drv.games(cfg["game_dirs"])
        except Exception:  # noqa: BLE001
            games = []
        req.json({"platform": drv.label, "apps": len(apps), "app_names": [a["name"] for a in apps[:60]], "games": [{"name": g["name"], "source": g["source"]} for g in games[:80]],
                  "game_count": len(games), "folders": {k: str(v) for k, v in rulebased.known_folders().items()}})

    def r_prompts(self, req) -> None:
        req.json({"prompts": promptlib.names()})

    def r_prompt(self, req, name: str) -> None:
        if name not in promptlib.names():
            raise HttpError(404, "Prompt não encontrado")
        req.json({"name": name, "text": promptlib.read(name)})

    # ----- tarefas
    def r_list(self, req) -> None:
        try:
            limit = max(1, min(int(req.query.get("limit", ["200"])[0] or 200), 500))
        except ValueError:
            limit = 200
        req.json({"tasks": self.m.list(limit), "status": self.m.status()})

    def r_get(self, req, tid: str) -> None:
        doc = self.m.get(tid)
        if not doc:
            raise HttpError(404, "Tarefa não encontrada")
        req.json(self.m.public(doc))

    def r_create(self, req) -> None:
        b = self._body(req)
        chat_id = text(b.get("chat_id"), "", 60)
        engine = self.app.chat_routes.engine
        if chat_id and not self.store.chats.get(chat_id):
            raise HttpError(404, "Conversa não encontrada")
        out: Dict[str, Any] = {}

        def attach(doc: Dict[str, Any]) -> None:
            if not chat_id:
                return
            ts = now_iso()
            ref = {"task_id": doc["id"], "mode": doc["mode"], "status": "queued"}
            with engine._lock_for(chat_id):
                chat = self.store.chats.get(chat_id) or {}
                user = {"id": new_id("m_"), "role": "user", "text": doc["goal"], "ts": ts, "attachments": [{"name": i["name"], "kind": "file"} for i in doc.get("inputs", [])], "context": "", "computer": ref}
                ai = {"id": new_id("m_"), "role": "assistant", "text": "Computer Use…", "ts": ts, "model": "Computer Use", "computer": ref}
                chat.setdefault("messages", []).extend([user, ai])
                if not chat.get("title"):
                    chat["title"] = (doc["goal"][:57] + "…") if len(doc["goal"]) > 58 else doc["goal"]
                self.store.chats.save(chat, chat_id)
            out["messages"] = [user, ai]

        try:
            doc = self.m.submit(text(b.get("goal"), "", 8000), mode=str(b.get("mode") or ""), attachment_ids=b.get("attachment_ids") if isinstance(b.get("attachment_ids"), list) else [],
                                chat_id=chat_id, origin="chat" if chat_id else "section", before_start=attach,
                                agents=teamlib.request_team(b).get("agents"), effort=teamlib.request_team(b).get("effort"))
        except ComputerError as exc:
            raise _http(exc) from None
        out["task"] = doc
        req.json(out, 201)

    def r_cancel(self, req, tid: str) -> None:
        try:
            req.json(self.m.cancel(tid))
        except ComputerError as exc:
            raise _http(exc) from None

    def r_answer(self, req, tid: str) -> None:
        b = self._body(req)
        try:
            req.json(self.m.answer(tid, b.get("approve") is True, b.get("remember") is True))
        except ComputerError as exc:
            raise _http(exc) from None

    def r_undo(self, req, tid: str) -> None:
        try:
            req.json(self.m.undo(tid))
        except ComputerError as exc:
            raise _http(exc) from None

    def r_retry(self, req, tid: str) -> None:
        old = self.m.get(tid)
        if not old:
            raise HttpError(404, "Tarefa não encontrada")
        b = self._body(req)
        try:
            req.json({"task": self.m.submit(old["goal"], mode=str(b.get("mode") or old.get("mode") or ""), agents=old.get("agents_n"), effort=old.get("effort"))}, 201)
        except ComputerError as exc:
            raise _http(exc) from None

    def r_delete(self, req, tid: str) -> None:
        try:
            ok = self.m.delete(tid, purge=req.query.get("purge", ["0"])[0] in ("1", "true"))
        except ComputerError as exc:
            raise _http(exc) from None
        if not ok:
            raise HttpError(404, "Tarefa não encontrada")
        req.json({"ok": True})

    def r_clear(self, req) -> None:
        b = self._body(req)
        req.json({"deleted": self.m.clear_history(purge=b.get("purge") is True)})

    def r_shot(self, req, tid: str, name: str) -> None:
        p = self.m.shot_path(tid, name)
        if not p:
            raise HttpError(404, "Captura não encontrada")
        req.file(p, "image/png" if name.endswith(".png") else "image/jpeg", cache=True)

    # ----- eventos ao vivo: a tela fica sabendo na hora do que mudou em qualquer tarefa
    def r_events(self, req) -> None:
        try:
            since = int(req.query.get("since", ["0"])[0] or 0)
        except ValueError:
            since = 0
        req.sse_start()
        req.sse_send({"type": "hello", "version": self.m.version, "status": self.m.status()})
        if since <= 0:
            since = self.m.version
        while True:
            v, items = self.m.wait_events(since, 15.0)
            if items:
                for it in items:
                    req.sse_send({"type": "task", "task": it, "version": v})
                req.sse_send({"type": "status", "status": self.m.status(), "version": v})
            else:
                req.sse_comment("keepalive")
            since = v

    # ----- o cartão do Chat acompanha a tarefa: quando ela termina, a mensagem vira o resumo
    def _sync_chat(self, doc: Dict[str, Any]) -> None:
        cid = doc.get("chat_id")
        if not cid:
            return
        engine = self.app.chat_routes.engine
        with engine._lock_for(cid):
            chat = self.store.chats.get(cid)
            if not chat:
                return
            for m in chat.get("messages", []):
                c = m.get("computer")
                if m.get("role") == "assistant" and isinstance(c, dict) and c.get("task_id") == doc["id"]:
                    m["text"] = (doc.get("summary") or "").strip() or "Computer Use"
                    c["status"] = doc.get("status", "")
            self.store.chats.save(chat, cid)
