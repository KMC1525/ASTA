"""Rotas HTTP do Work (`/api/work/…`): redes e login, pessoas, cargos, quadro, setores e arquivos, pedidos, atividades, notificações (SSE),
máquinas/redes/backups e a IA. A lógica fica em `asta/work/`; aqui só se autentica (cookie `asta_work`), valida o corpo e devolve JSON."""
from __future__ import annotations

import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List

from . import team as teamlib
from .jobs import HttpError
from .util import text
from .work import WorkError, WorkManager, agents as wai, tailscale
from .work.manager import SESSION_COOKIE

CSP = {"Content-Security-Policy": "sandbox; default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'", "X-Frame-Options": "SAMEORIGIN"}


def _http(exc: WorkError) -> HttpError:
    return HttpError(exc.status, exc.message)


class WorkRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store
        self.m = WorkManager(app.store)
        app.work = self.m

    # ------------------------------------------------------------------ infra
    @staticmethod
    def _body(req: Any) -> Dict[str, Any]:
        """O corpo JSON da requisição (lido uma vez; as rotas podem consultá-lo várias vezes)."""
        if not hasattr(req, "_wk_body"):
            b = req.body_json()
            req._wk_body = b if isinstance(b, dict) else {}
        return req._wk_body

    @staticmethod
    def _token(req: Any) -> str:
        for part in (req.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == SESSION_COOKIE:
                return v
        return ""

    def _ctx(self, req: Any) -> Any:
        try:
            return self.m.ctx(self._token(req))
        except WorkError as exc:
            raise _http(exc) from None

    def _wrap(self, fn: Callable[..., Any], touch: bool = True) -> Callable[..., None]:
        """Rota autenticada: resolve a pessoa, chama `fn(req, ctx, **grupos)` e traduz os erros do Work em erros HTTP."""
        def run(req: Any, **kw: Any) -> None:
            ctx = self._ctx(req)
            try:
                if touch:
                    self.m.ping(ctx)
                fn(req, ctx, **kw)
            except WorkError as exc:
                raise _http(exc) from None
            except ValueError as exc:
                raise HttpError(400, str(exc)) from None
        return run

    def register(self) -> None:
        a, w = self.app.add, self._wrap
        # público
        a("GET", r"/api/work/status", self.r_status)
        a("GET", r"/api/work/prompts", self.r_prompts)
        a("POST", r"/api/work/orgs", self.r_create_org)
        a("POST", r"/api/work/join", self.r_join)
        a("GET", r"/api/work/orgs/(?P<oid>[\w-]+)/people", self.r_login_users)
        a("POST", r"/api/work/login", self.r_login)
        a("POST", r"/api/work/logout", self.r_logout)
        a("GET", r"/api/work/tailscale", lambda req: req.json(tailscale.status(refresh=True)))
        # sessão
        a("GET", r"/api/work/me", w(lambda req, c: req.json(self.m.me(c))))
        a("GET", r"/api/work/catalog", w(lambda req, c: req.json(self.m.catalog()), touch=False))
        a("GET", r"/api/work/directory", w(lambda req, c: req.json(self.m.directory(c))))
        a("GET", r"/api/work/events", self.r_events)
        a("POST", r"/api/work/ping", w(lambda req, c: req.json({"ok": True})))
        # pessoas, cargos, funções
        a("POST", r"/api/work/users", w(lambda req, c: req.json(self.m.create_user(c, self._body(req)), 201)))
        a("PUT", r"/api/work/users/(?P<uid>[\w-]+)", w(lambda req, c, uid: req.json(self.m.update_user(c, uid, self._body(req)))))
        a("DELETE", r"/api/work/users/(?P<uid>[\w-]+)", w(lambda req, c, uid: (self.m.delete_user(c, uid), req.json({"ok": True}))))
        a("POST", r"/api/work/users/(?P<uid>[\w-]+)/password", w(self.r_password))
        a("POST", r"/api/work/roles", w(lambda req, c: req.json(self.m.save_role(c, "", self._body(req)), 201)))
        a("PUT", r"/api/work/roles/(?P<rid>[\w-]+)", w(lambda req, c, rid: req.json(self.m.save_role(c, rid, self._body(req)))))
        a("DELETE", r"/api/work/roles/(?P<rid>[\w-]+)", w(lambda req, c, rid: (self.m.delete_role(c, rid), req.json({"ok": True}))))
        a("POST", r"/api/work/functions", w(lambda req, c: req.json(self.m.save_function(c, "", self._body(req)), 201)))
        a("PUT", r"/api/work/functions/(?P<fid>[\w-]+)", w(lambda req, c, fid: req.json(self.m.save_function(c, fid, self._body(req)))))
        a("DELETE", r"/api/work/functions/(?P<fid>[\w-]+)", w(lambda req, c, fid: (self.m.delete_function(c, fid), req.json({"ok": True}))))
        # quadro e setores
        a("GET", r"/api/work/board", w(lambda req, c: req.json(self.m.board(c))))
        a("POST", r"/api/work/board/layout", w(lambda req, c: req.json(self.m.layout_board(c))))
        a("POST", r"/api/work/board/autofill", w(lambda req, c: req.json(self.m.autofill_board(c))))
        a("POST", r"/api/work/board/apply", w(self.r_apply))
        a("POST", r"/api/work/nodes", w(lambda req, c: req.json(self.m.save_node(c, "", self._body(req)), 201)))
        a("PUT", r"/api/work/nodes/(?P<nid>[\w-]+)", w(lambda req, c, nid: req.json(self.m.save_node(c, nid, self._body(req)))))
        a("DELETE", r"/api/work/nodes/(?P<nid>[\w-]+)", w(lambda req, c, nid: (self.m.delete_node(c, nid), req.json({"ok": True}))))
        a("POST", r"/api/work/edges", w(lambda req, c: req.json(self.m.save_edge(c, "", self._body(req)), 201)))
        a("PUT", r"/api/work/edges/(?P<eid>[\w-]+)", w(lambda req, c, eid: req.json(self.m.save_edge(c, eid, self._body(req)))))
        a("DELETE", r"/api/work/edges/(?P<eid>[\w-]+)", w(lambda req, c, eid: (self.m.delete_edge(c, eid), req.json({"ok": True}))))
        a("POST", r"/api/work/folders", w(lambda req, c: req.json(self.m.save_folder(c, "", self._body(req)), 201)))
        a("PUT", r"/api/work/folders/(?P<fid>[\w-]+)", w(lambda req, c, fid: req.json(self.m.save_folder(c, fid, self._body(req)))))
        a("DELETE", r"/api/work/folders/(?P<fid>[\w-]+)", w(lambda req, c, fid: (self.m.delete_folder(c, fid), req.json({"ok": True}))))
        # arquivos
        a("GET", r"/api/work/files", w(lambda req, c: req.json({"files": self.m.list_files(c, req.query.get("folder", [""])[0])})))
        a("POST", r"/api/work/files", w(self.r_upload))
        a("GET", r"/api/work/files/(?P<fid>[\w-]+)/download", w(self.r_download, touch=False))
        a("DELETE", r"/api/work/files/(?P<fid>[\w-]+)", w(lambda req, c, fid: (self.m.delete_file(c, fid), req.json({"ok": True}))))
        a("PUT", r"/api/work/files/(?P<fid>[\w-]+)", w(lambda req, c, fid: req.json(self.m.move_file(c, fid, text(self._body(req).get("folder_id"), "", 80)))))
        a("POST", r"/api/work/files/(?P<fid>[\w-]+)/to-upload", w(lambda req, c, fid: req.json(self.m.to_asta_upload(c, fid))))
        a("POST", r"/api/work/files/from-upload", w(lambda req, c: req.json(self.m.import_upload(c, text(self._body(req).get("upload_id"), "", 80), text(self._body(req).get("folder_id"), "", 80)), 201)))
        a("POST", r"/api/work/files/from-project", w(lambda req, c: req.json(self.m.import_project(c, text(self._body(req).get("project_id"), "", 80), text(self._body(req).get("folder_id"), "", 80)), 201)))
        # pedidos
        a("GET", r"/api/work/requests", w(lambda req, c: req.json({"requests": self.m.list_requests(c, req.query.get("box", ["in"])[0])})))
        a("POST", r"/api/work/requests", w(lambda req, c: req.json(self.m.send_request(c, self._body(req)), 201)))
        a("GET", r"/api/work/requests/(?P<rid>[\w-]+)", w(lambda req, c, rid: req.json(self.m.get_request(c, rid))))
        a("POST", r"/api/work/requests/(?P<rid>[\w-]+)/reply", w(lambda req, c, rid: req.json(self.m.reply_request(c, rid, self._body(req).get("text", ""), self._body(req).get("attachments")))))
        a("POST", r"/api/work/requests/(?P<rid>[\w-]+)/status", w(lambda req, c, rid: req.json(self.m.set_request_status(c, rid, str(self._body(req).get("status")), str(self._body(req).get("note") or "")))))
        a("POST", r"/api/work/requests/(?P<rid>[\w-]+)/computer", w(self.r_to_computer))
        # atividades
        a("GET", r"/api/work/activities", w(self.r_activities))
        a("POST", r"/api/work/activities", w(self.r_act_start))
        a("POST", r"/api/work/activities/(?P<aid>[\w-]+)/(?P<op>progress|pause|finish|cancel)", w(self.r_act_op))
        # notificações
        a("GET", r"/api/work/notifications", w(lambda req, c: req.json(self.m.list_notifications(c, req.query.get("unread", ["0"])[0] == "1")), touch=False))
        a("POST", r"/api/work/notifications/read", w(lambda req, c: req.json({"marked": self.m.mark_read(c, self._body(req).get("ids"), self._body(req).get("all") is True)})))
        a("POST", r"/api/work/notifications/broadcast", w(lambda req, c: req.json({"sent": self.m.broadcast(c, self._body(req).get("title", ""), self._body(req).get("body", ""),
                                                                                                          self._body(req).get("audience") if isinstance(self._body(req).get("audience"), dict) else {})})))
        # máquinas, rede e backups
        a("GET", r"/api/work/network", w(lambda req, c: req.json(self.m.network(c)), touch=False))
        a("PUT", r"/api/work/network", w(lambda req, c: req.json(self.m.set_network_config(c, self._body(req)))))
        a("POST", r"/api/work/network/invite", w(lambda req, c: req.json(self.m.create_invite(c, self._body(req).get("addrs")))))
        a("POST", r"/api/work/network/sync", w(lambda req, c: req.json(self.m.sync_now(c))))
        a("POST", r"/api/work/network/links", w(lambda req, c: req.json({"links": self.m.add_link(c, str(self._body(req).get("kind")), str(self._body(req).get("target") or ""))})))
        a("DELETE", r"/api/work/network/links", w(lambda req, c: req.json({"links": self.m.remove_link(c, req.query.get("target", [""])[0])})))
        a("PUT", r"/api/work/machines/(?P<mid>[\w-]+)", w(lambda req, c, mid: req.json(self.m.update_machine(c, mid, self._body(req)))))
        a("GET", r"/api/work/backup", w(lambda req, c: req.json(self.m.backup_status(c)), touch=False))
        a("POST", r"/api/work/backup/verify", w(lambda req, c: req.json(self.m.verify_backup(c, str(self._body(req).get("machine") or "")))))
        a("POST", r"/api/work/backup/restore", w(lambda req, c: req.json(self.m.restore_from(c, str(self._body(req).get("machine") or ""), str(self._body(req).get("user") or "")))))
        a("POST", r"/api/work/backup/snapshot", w(lambda req, c: req.json(self.m.snapshot_now(c))))
        a("GET", r"/api/work/export", w(self.r_export, touch=False))
        # IA
        a("POST", r"/api/work/ai/request", w(self.r_ai_request))
        a("POST", r"/api/work/ai/flow", w(self.r_ai_flow))
        a("POST", r"/api/work/ai/digest", w(self.r_ai_digest))
        a("POST", r"/api/work/ai/suggest", w(self.r_ai_suggest))
        self.m.start()

    # ------------------------------------------------------------------ público e login
    def r_status(self, req: Any) -> None:
        req.json({**self.m.status(self._token(req)), "config": self.m.config()})

    def r_prompts(self, req: Any) -> None:
        req.json({"prompts": [{"name": n, "text": wai.prompt(n)} for n in wai.prompt_names()]})

    def _session(self, req: Any, token: str, ctx: Any) -> None:
        body = {"token_set": True, **self.m.me(ctx)}
        cookie = f"{SESSION_COOKIE}={token}; Path=/api/work; HttpOnly; SameSite=Strict; Max-Age={self.m.config()['session_hours'] * 3600}"
        import json as _json

        data = _json.dumps(body, ensure_ascii=False).encode("utf-8")
        req._head(200, "application/json; charset=utf-8", len(data), {"Set-Cookie": cookie})
        if req.method != "HEAD":
            req.h.wfile.write(data)

    def r_create_org(self, req: Any) -> None:
        b = self._body(req)
        try:
            st, user = self.m.create_org(str(b.get("name") or ""), b.get("admin") if isinstance(b.get("admin"), dict) else {}, str(b.get("machine_name") or ""))
            token, ctx = self.m.login(st.id, user["username"], str((b.get("admin") or {}).get("password") or ""))
        except WorkError as exc:
            raise _http(exc) from None
        self._session(req, token, ctx)

    def r_join(self, req: Any) -> None:
        b = self._body(req)
        try:
            st = self.m.join(str(b.get("code") or ""), str(b.get("machine_name") or ""))
        except WorkError as exc:
            raise _http(exc) from None
        req.json({"org": st.id, "name": (st.get("meta", "org") or {}).get("name", "")}, 201)

    def r_login_users(self, req: Any, oid: str) -> None:
        try:
            req.json({"people": self.m.login_users(oid)})
        except WorkError as exc:
            raise _http(exc) from None

    def r_login(self, req: Any) -> None:
        b = self._body(req)
        try:
            token, ctx = self.m.login(str(b.get("org") or ""), str(b.get("username") or ""), str(b.get("password") or ""))
        except WorkError as exc:
            raise _http(exc) from None
        self._session(req, token, ctx)

    def r_logout(self, req: Any) -> None:
        self.m.logout(self._token(req))
        data = b'{"ok":true}'
        req._head(200, "application/json; charset=utf-8", len(data), {"Set-Cookie": f"{SESSION_COOKIE}=; Path=/api/work; HttpOnly; SameSite=Strict; Max-Age=0"})
        req.h.wfile.write(data)

    def r_password(self, req: Any, ctx: Any, uid: str) -> None:
        b = self._body(req)
        req.json(self.m.set_password(ctx, uid, str(b.get("password") or ""), str(b.get("mode") or "local"), str(b.get("holder") or ""), str(b.get("current") or "")))

    # ------------------------------------------------------------------ eventos em tempo real
    def r_events(self, req: Any) -> None:
        ctx = self._ctx(req)
        token = self._token(req)
        try:
            since = int(req.query.get("since", ["0"])[0] or 0)
        except ValueError:
            since = 0
        org, uid = ctx.st.id, ctx.uid
        req.sse_start()
        req.sse_send({"type": "hello", "seq": self.m.seq, "unread": self.m.list_notifications(ctx)["unread"]})
        if since <= 0:
            since = self.m.seq
        while True:
            seq, items = self.m.wait_events(since, org, uid, 15.0)
            try:
                ctx = self.m.ctx(token)
                self.m.ping(ctx)
            except WorkError:
                req.sse_send({"type": "logout"})
                return
            if items:
                for e in items:
                    req.sse_send({"type": "change", "kind": e["kind"], "id": e.get("id"), "source": e.get("source"), "seq": e["seq"]})
                req.sse_send({"type": "unread", "n": self.m.list_notifications(ctx)["unread"]})
            else:
                req.sse_comment("keepalive")
            since = seq

    # ------------------------------------------------------------------ quadro, arquivos, pedidos
    def r_apply(self, req: Any, ctx: Any) -> None:
        b = self._body(req)
        draft = wai.normalize_flow(b.get("draft"), [r["id"] for r in ctx.st.all("roles")], [u["id"] for u in ctx.st.all("users")])
        if not draft:
            raise HttpError(400, "Fluxograma inválido.")
        req.json(self.m.apply_draft(ctx, draft, b.get("replace") is True))

    def r_upload(self, req: Any, ctx: Any) -> None:
        name = urllib.parse.unquote(req.headers.get("X-Filename", "arquivo"))
        folder = urllib.parse.unquote(req.headers.get("X-Folder", ""))
        rid = urllib.parse.unquote(req.headers.get("X-Request", ""))
        req.json(self.m.upload_file(ctx, name, req.rfile, req.content_length(), folder, rid, req.headers.get("Content-Type", "")), 201)
        req._body_read = True

    def r_download(self, req: Any, ctx: Any, fid: str) -> None:
        try:
            version = int(req.query.get("v", ["0"])[0] or 0)
        except ValueError:
            version = 0
        path, name, inline_mime = self.m.open_file(ctx, fid, version)
        if req.query.get("inline", ["0"])[0] == "1" and inline_mime:
            req.file(path, inline_mime, headers=CSP)
        else:
            req.file(path, "application/octet-stream", download_name=name, headers=CSP)

    def r_to_computer(self, req: Any, ctx: Any, rid: str) -> None:
        """Entrega o pedido ao Computer Use como tarefa (se ele estiver ligado); os anexos do pedido viram anexos do ASTA."""
        r = self.m.get_request(ctx, rid)
        goal = r["title"] + ("\n\n" + r["body"] if r.get("body") else "") + ("\n\nChecklist:\n- " + "\n- ".join(r["checklist"]) if r.get("checklist") else "")
        ids: List[str] = []
        for fid in list(r.get("files", {}))[:10]:
            try:
                ids.append(self.m.to_asta_upload(ctx, fid)["id"])
            except WorkError:
                continue
        from .computer import ComputerError

        try:
            task = self.app.computer.submit(goal, attachment_ids=ids, origin="work", **teamlib.request_team(self._body(req)))
        except ComputerError as exc:
            raise HttpError(exc.status, exc.message) from None
        self.m.record(ctx, "Enviou o pedido «" + r["title"] + "» ao Computer Use", ref={"type": "request", "id": rid})
        req.json({"task": task}, 201)

    # ------------------------------------------------------------------ atividades
    def r_activities(self, req: Any, ctx: Any) -> None:
        q = req.query
        req.json({"activities": self.m.list_activities(ctx, q.get("user", [""])[0], q.get("state", [""])[0], q.get("auto", ["1"])[0] != "0", int(q.get("limit", ["200"])[0] or 200))})

    def r_act_start(self, req: Any, ctx: Any) -> None:
        b = self._body(req)
        req.json(self.m.start_activity(ctx, str(b.get("title") or ""), str(b.get("request_id") or ""), str(b.get("folder_id") or ""), str(b.get("note") or "")), 201)

    def r_act_op(self, req: Any, ctx: Any, aid: str, op: str) -> None:
        note = str(self._body(req).get("note") or "")
        fn = {"progress": self.m.progress_activity, "pause": self.m.pause_activity, "finish": self.m.finish_activity,
              "cancel": lambda c, a, n: self.m.finish_activity(c, a, n, cancelled=True)}[op]
        req.json(fn(ctx, aid, note))

    # ------------------------------------------------------------------ exportar
    def r_export(self, req: Any, ctx: Any) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = self.m.export_zip(ctx, Path(tmp) / "work-export.zip", req.query.get("files", ["0"])[0] == "1")
            req.file(dest, "application/zip", download_name=f"asta-work-{ctx.st.id}.zip")

    # ------------------------------------------------------------------ IA
    def _ai(self, fn: Callable[..., Dict[str, Any]], ctx: Any, *args: Any, **kw: Any) -> Dict[str, Any]:
        ctx.need("ai.use")
        try:
            return fn(ctx, *args, **kw)
        except ValueError as exc:
            raise HttpError(400, str(exc)) from None

    def r_ai_request(self, req: Any, ctx: Any) -> None:
        b = self._body(req)
        req.json(self._ai(wai.draft_request, ctx, str(b.get("brief") or ""), self._attachments_text(ctx, b.get("attachments")), [x for x in (b.get("to") or []) if isinstance(x, str)], req=b))

    def _attachments_text(self, ctx: Any, ids: Any) -> str:
        """Texto dos arquivos anexados ao rascunho, lido pelo mesmo leitor de anexos de todas as seções (qualquer formato; o que não tem texto vira só nome e tamanho)."""
        from . import attachments as att

        items: List[Dict[str, Any]] = []
        for fid in [i for i in ids if isinstance(i, str)][:6] if isinstance(ids, list) else []:
            try:
                path, name, _ = self.m.open_file(ctx, fid)
                items.append(att.analyze(path, name, max_chars=6000))
            except (WorkError, OSError, ValueError):
                continue
        return att.build_digest(items, max_total=20000)

    def r_ai_flow(self, req: Any, ctx: Any) -> None:
        ctx.need("flow.edit")
        b = self._body(req)
        req.json(self._ai(wai.draft_flow, ctx, str(b.get("description") or ""), req=b))

    def r_ai_digest(self, req: Any, ctx: Any) -> None:
        b = self._body(req)
        req.json(self._ai(wai.digest, ctx, str(b.get("scope") or "me"), str(b.get("period") or "day"), req=b))

    def r_ai_suggest(self, req: Any, ctx: Any) -> None:
        b = self._body(req)
        req.json(self._ai(wai.suggest, ctx, str(b.get("request_id") or ""), str(b.get("brief") or ""), req=b))
