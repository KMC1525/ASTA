"""Rotas HTTP do Code: estado e capacidades, pastas e subpastas, sessões (criar, mandar um pedido, acompanhar, cancelar, responder Sim/Não, desfazer, apagar), o projeto da sessão (arquivos, diff,
abrir no VS Code/Cursor), execuções antigas, GitHub (conta, repositórios), eventos ao vivo (SSE) e os prompts internos (leitura)."""
from __future__ import annotations

import subprocess
from typing import Any, Dict

from .code import CodeError, CodeManager, guard, promptlib
from .code import github as gh
from .code import tools as T
from .jobs import HttpError
from .util import text


def _http(exc: CodeError) -> HttpError:
    return HttpError(exc.status, exc.message)


class CodeRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store
        self.m = CodeManager(app.store)
        app.code = self.m

    def register(self) -> None:
        a = self.app.add
        a("GET", r"/api/code/status", self.r_status)
        a("GET", r"/api/code/prompts", self.r_prompts)
        a("GET", r"/api/code/prompts/(?P<name>[\w/.-]+)", self.r_prompt)
        a("GET", r"/api/code/events", self.r_events)
        a("GET", r"/api/code/github", self.r_github)
        a("GET", r"/api/code/github/repos", self.r_github_repos)
        a("POST", r"/api/code/github/import-gh", self.r_github_import)
        a("GET", r"/api/code/folders", self.r_folders)
        a("POST", r"/api/code/folders", self.r_folder_create)
        a("PUT", r"/api/code/folders/(?P<fid>[\w-]+)", self.r_folder_update)
        a("DELETE", r"/api/code/folders/(?P<fid>[\w-]+)", self.r_folder_delete)
        a("GET", r"/api/code/sessions", self.r_list)
        a("POST", r"/api/code/sessions", self.r_create)
        a("GET", r"/api/code/sessions/(?P<sid>[\w-]+)", self.r_get)
        a("PUT", r"/api/code/sessions/(?P<sid>[\w-]+)", self.r_update)
        a("DELETE", r"/api/code/sessions/(?P<sid>[\w-]+)", self.r_delete)
        a("POST", r"/api/code/sessions/(?P<sid>[\w-]+)/send", self.r_send)
        a("POST", r"/api/code/sessions/(?P<sid>[\w-]+)/cancel", self.r_cancel)
        a("POST", r"/api/code/sessions/(?P<sid>[\w-]+)/answer", self.r_answer)
        a("POST", r"/api/code/sessions/(?P<sid>[\w-]+)/undo", self.r_undo)
        a("POST", r"/api/code/sessions/(?P<sid>[\w-]+)/seen", self.r_seen)
        a("POST", r"/api/code/sessions/(?P<sid>[\w-]+)/editor", self.r_editor)
        a("GET", r"/api/code/sessions/(?P<sid>[\w-]+)/browse", self.r_browse)
        a("GET", r"/api/code/sessions/(?P<sid>[\w-]+)/file", self.r_file)
        a("GET", r"/api/code/sessions/(?P<sid>[\w-]+)/diff", self.r_diff)
        a("GET", r"/api/code/sessions/(?P<sid>[\w-]+)/runs/(?P<rid>[\w-]+)", self.r_run)

    @staticmethod
    def _body(req) -> Dict[str, Any]:
        b = req.body_json()
        return b if isinstance(b, dict) else {}

    # ----- estado
    def r_status(self, req) -> None:
        req.json(self.m.status())

    def r_prompts(self, req) -> None:
        req.json({"prompts": promptlib.names()})

    def r_prompt(self, req, name: str) -> None:
        if name not in promptlib.names():
            raise HttpError(404, "Prompt não encontrado")
        req.json({"name": name, "text": promptlib.read(name)})

    # ----- GitHub
    def r_github(self, req) -> None:
        g = self.m.github()
        out: Dict[str, Any] = {"token": bool(g.token), "api": g.api, "gh_cli": bool(gh.gh_cli_token()) if req.query.get("probe", ["0"])[0] == "1" else None}
        if g.token and req.query.get("check", ["0"])[0] == "1":
            try:
                out["user"] = g.whoami()
            except gh.GitHubError as exc:
                out["error"] = exc.message
        req.json(out)

    def r_github_repos(self, req) -> None:
        g = self.m.github()
        if not g.token:
            raise HttpError(400, "Salve um token do GitHub em Configuração → Code para listar os seus repositórios.")
        try:
            req.json({"repos": g.repos(req.query.get("q", [""])[0], 60)})
        except gh.GitHubError as exc:
            raise HttpError(exc.status if 400 <= exc.status < 600 else 502, exc.message) from None

    def r_github_import(self, req) -> None:
        """O usuário clicou em «Usar o login do gh»: copia o token do GitHub CLI para as configurações (só ele decide isso)."""
        tok = gh.gh_cli_token()
        if not tok:
            raise HttpError(404, "Não achei um login do GitHub CLI (gh). Rode «gh auth login» no terminal ou cole um token.")
        self.store.save_settings({"code": {"github": {"token": tok}}})
        req.json({"ok": True})

    # ----- pastas
    def r_folders(self, req) -> None:
        req.json({"folders": self.m.folders()})

    def r_folder_create(self, req) -> None:
        b = self._body(req)
        try:
            req.json(self.m.create_folder(text(b.get("name"), "", 60), str(b.get("color") or ""), b.get("parent") or None), 201)
        except CodeError as exc:
            raise _http(exc) from None

    def r_folder_update(self, req, fid: str) -> None:
        try:
            req.json(self.m.update_folder(fid, self._body(req)))
        except CodeError as exc:
            raise _http(exc) from None

    def r_folder_delete(self, req, fid: str) -> None:
        try:
            req.json(self.m.delete_folder(fid))
        except CodeError as exc:
            raise _http(exc) from None

    # ----- sessões
    def r_list(self, req) -> None:
        req.json({"sessions": self.m.list(), "folders": self.m.folders(), "status": self.m.status()})

    def r_create(self, req) -> None:
        try:
            req.json(self.m.create_session(self._body(req)), 201)
        except CodeError as exc:
            raise _http(exc) from None

    def r_get(self, req, sid: str) -> None:
        doc = self.m.get(sid)
        if not doc:
            raise HttpError(404, "Sessão não encontrada")
        req.json(self.m.public(doc))

    def r_update(self, req, sid: str) -> None:
        try:
            req.json(self.m.update_session(sid, self._body(req)))
        except CodeError as exc:
            raise _http(exc) from None

    def r_delete(self, req, sid: str) -> None:
        try:
            ok = self.m.delete(sid, purge_workspace=req.query.get("purge", ["0"])[0] in ("1", "true"))
        except CodeError as exc:
            raise _http(exc) from None
        if not ok:
            raise HttpError(404, "Sessão não encontrada")
        req.json({"ok": True})

    def r_send(self, req, sid: str) -> None:
        b = self._body(req)
        try:
            req.json(self.m.send(sid, text(b.get("text"), "", 12000), attachment_ids=b.get("attachment_ids") if isinstance(b.get("attachment_ids"), list) else [],
                                 options=b.get("options") if isinstance(b.get("options"), dict) else {}), 201)
        except CodeError as exc:
            raise _http(exc) from None

    def r_cancel(self, req, sid: str) -> None:
        try:
            req.json(self.m.cancel(sid))
        except CodeError as exc:
            raise _http(exc) from None

    def r_answer(self, req, sid: str) -> None:
        b = self._body(req)
        try:
            req.json(self.m.answer(sid, b.get("approve") is True, b.get("remember") is True, str(b.get("id") or "")))
        except CodeError as exc:
            raise _http(exc) from None

    def r_undo(self, req, sid: str) -> None:
        try:
            req.json(self.m.undo(sid, str(self._body(req).get("run") or "")))
        except CodeError as exc:
            raise _http(exc) from None

    def r_seen(self, req, sid: str) -> None:
        self.m.mark_seen(sid)
        req.json({"ok": True})

    def r_browse(self, req, sid: str) -> None:
        try:
            req.json(self.m.browse(sid, req.query.get("path", ["."])[0]))
        except CodeError as exc:
            raise _http(exc) from None

    def r_file(self, req, sid: str) -> None:
        try:
            req.json(self.m.read_file(sid, req.query.get("path", [""])[0]))
        except CodeError as exc:
            raise _http(exc) from None

    def r_diff(self, req, sid: str) -> None:
        try:
            req.json(self.m.diff(sid, req.query.get("path", [""])[0]))
        except CodeError as exc:
            raise _http(exc) from None

    def r_run(self, req, sid: str, rid: str) -> None:
        run = self.m.run_doc(sid, rid)
        if not run:
            raise HttpError(404, "Execução não encontrada")
        req.json(run)

    def r_editor(self, req, sid: str) -> None:
        """O usuário clicou em «Abrir no VS Code/Cursor»: abre a pasta do projeto (ou um arquivo) no editor, só no computador."""
        if T.IS_ANDROID:
            raise HttpError(409, "Este aparelho não abre o VS Code nem o Cursor. Abra a sessão no computador.")
        b = self._body(req)
        which, exe = T._editor(str(b.get("editor") or self.m.config()["editor"]))
        if not exe:
            raise HttpError(404, "Nem o VS Code (comando «code») nem o Cursor (comando «cursor») foram encontrados no PATH.")
        try:
            w = self.m._ws(sid)
            p = w.check(str(b.get("path") or "."), "read")
        except (CodeError, guard.Blocked) as exc:
            raise HttpError(getattr(exc, "status", 403), getattr(exc, "message", str(exc))) from None
        line = int(b["line"]) if isinstance(b.get("line"), int) and p.is_file() and b["line"] > 0 else 0
        kw: Dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "env": guard.clean_env()}
        import os

        if os.name != "nt":
            kw["start_new_session"] = True
        try:
            subprocess.Popen([exe] + (["-g", f"{p}:{line}"] if line else [str(p)]), **kw)
        except OSError as exc:
            raise HttpError(500, f"Não consegui abrir o editor: {exc.strerror or exc}") from None
        req.json({"ok": True, "editor": which})

    # ----- eventos ao vivo: a tela fica sabendo na hora do que mudou em qualquer sessão
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
            v, items, folders = self.m.wait_events(since, 15.0)
            if items or folders:
                for it in items:
                    req.sse_send({"type": "session", "session": it, "version": v})
                if folders:
                    req.sse_send({"type": "folders", "folders": self.m.folders(), "version": v})
                req.sse_send({"type": "status", "status": self.m.status(), "version": v})
            else:
                req.sse_comment("keepalive")
            since = v
