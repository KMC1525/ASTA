"""Rotas HTTP do Game Engine (`/api/engine/…`): projetos, cenas, mapas, arquivos, jogar, histórico e a IA de cada aba.
A lógica fica em `asta/gameengine/`; aqui só se valida o corpo, chama o gerenciador e devolve JSON."""
from __future__ import annotations

import json
import mimetypes
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict

from . import team as teamlib
from .gameengine import EngineError, EngineManager, agents as eai, exporter, maps as gmaps, schema as S
from .gameengine.manager import CSP, IMG_EXT, SND_EXT
from .jobs import HttpError, Job
from .util import text

PID = r"(?P<pid>[\w-]+)"


def _http(exc: EngineError) -> HttpError:
    return HttpError(exc.status, exc.message)


class EngineRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store
        self.m = EngineManager(app.store)
        app.engine = self.m

    # ------------------------------------------------------------------ infra
    @staticmethod
    def _body(req: Any) -> Dict[str, Any]:
        if not hasattr(req, "_ge_body"):
            b = req.body_json()
            req._ge_body = b if isinstance(b, dict) else {}
        return req._ge_body

    def _w(self, fn: Callable[..., Any]) -> Callable[..., None]:
        def run(req: Any, **kw: Any) -> None:
            try:
                fn(req, **kw)
            except EngineError as exc:
                raise _http(exc) from None
            except ValueError as exc:
                raise HttpError(400, str(exc)) from None
        return run

    def register(self) -> None:
        a, w = self.app.add, self._w
        a("GET", r"/api/engine/catalog", w(self.r_catalog))
        a("GET", r"/api/engine/status", w(self.r_status))
        a("GET", r"/api/engine/prompts", w(self.r_prompts))
        a("GET", r"/api/engine/projects", w(lambda req: req.json({"projects": self.m.list()})))
        a("POST", r"/api/engine/projects", w(self.r_create))
        a("GET", rf"/api/engine/projects/{PID}", w(self.r_get))
        a("PUT", rf"/api/engine/projects/{PID}", w(lambda req, pid: req.json(self.m.update_meta(pid, self._body(req)))))
        a("DELETE", rf"/api/engine/projects/{PID}", w(lambda req, pid: (self.m.delete(pid), req.json({"ok": True}))))
        a("POST", rf"/api/engine/projects/{PID}/duplicate", w(lambda req, pid: req.json(self.m.duplicate(pid, text(self._body(req).get("name"), "", 60)), 201)))
        # cenas e mapas
        a("GET", rf"/api/engine/projects/{PID}/scenes", w(lambda req, pid: req.json({"scenes": self.m.list_scenes(pid), "start": self.m.meta(pid).get("start")})))
        a("GET", rf"/api/engine/projects/{PID}/scenes/(?P<name>[\w .+@()%-]+)", w(lambda req, pid, name: req.json(self.m.get_scene(pid, urllib.parse.unquote(name)))))
        a("PUT", rf"/api/engine/projects/{PID}/scenes/(?P<name>[\w .+@()%-]+)", w(lambda req, pid, name: req.json(self.m.save_scene(pid, urllib.parse.unquote(name), self._body(req)))))
        a("DELETE", rf"/api/engine/projects/{PID}/scenes/(?P<name>[\w .+@()%-]+)", w(lambda req, pid, name: (self.m.delete_scene(pid, urllib.parse.unquote(name)), req.json({"ok": True}))))
        a("GET", rf"/api/engine/projects/{PID}/maps", w(lambda req, pid: req.json({"maps": self.m.list_maps(pid)})))
        a("GET", rf"/api/engine/projects/{PID}/map", w(lambda req, pid: req.json(self.m.get_map(pid, req.query.get("path", [""])[0]))))
        a("PUT", rf"/api/engine/projects/{PID}/map", w(lambda req, pid: req.json(self.m.save_map(pid, req.query.get("path", [""])[0], self._body(req)))))
        a("DELETE", rf"/api/engine/projects/{PID}/map", w(lambda req, pid: (self.m.delete_map(pid, req.query.get("path", [""])[0]), req.json({"ok": True}))))
        # arquivos
        a("GET", rf"/api/engine/projects/{PID}/tree", w(lambda req, pid: req.json(self.m.tree(pid, req.query.get("area", ["game"])[0]))))
        a("GET", rf"/api/engine/projects/{PID}/file", w(lambda req, pid: req.json(self.m.read_file(pid, req.query.get("area", ["game"])[0], req.query.get("path", [""])[0]))))
        a("PUT", rf"/api/engine/projects/{PID}/file", w(self.r_write))
        a("DELETE", rf"/api/engine/projects/{PID}/file", w(lambda req, pid: (self.m.delete_path(pid, req.query.get("area", ["game"])[0], req.query.get("path", [""])[0]), req.json({"ok": True}))))
        a("POST", rf"/api/engine/projects/{PID}/mkdir", w(lambda req, pid: req.json(self.m.mkdir(pid, text(self._body(req).get("area"), "game", 10), text(self._body(req).get("path"), "", 400)), 201)))
        a("POST", rf"/api/engine/projects/{PID}/rename", w(lambda req, pid: req.json(self.m.rename(pid, text(self._body(req).get("area"), "game", 10), text(self._body(req).get("path"), "", 400), text(self._body(req).get("to"), "", 400)))))
        a("POST", rf"/api/engine/projects/{PID}/upload", w(self.r_upload))
        a("POST", rf"/api/engine/projects/{PID}/import-zip", w(self.r_import_zip))
        a("GET", rf"/api/engine/projects/{PID}/raw", w(self.r_raw))
        # histórico
        a("GET", rf"/api/engine/projects/{PID}/history", w(lambda req, pid: req.json({"items": self.m.history(pid)})))
        a("POST", rf"/api/engine/projects/{PID}/history/restore", w(lambda req, pid: (self.m.restore(pid, text(self._body(req).get("id"), "", 60)), req.json({"ok": True}))))
        a("POST", rf"/api/engine/projects/{PID}/snapshot", w(lambda req, pid: req.json({"id": self.m.snapshot(pid, text(self._body(req).get("label"), "manual", 100))})))
        # jogar
        a("GET", rf"/api/engine/play/{PID}", w(lambda req, pid: req.redirect(f"/api/engine/play/{pid}/index.html")))
        a("GET", rf"/api/engine/play/{PID}/(?P<rest>.*)", w(self.r_play))
        # IA por aba
        a("POST", rf"/api/engine/projects/{PID}/generate", w(self.r_generate))
        a("POST", rf"/api/engine/projects/{PID}/code", w(self.r_code))
        a("POST", rf"/api/engine/projects/{PID}/asset", w(self.r_asset))
        a("POST", rf"/api/engine/projects/{PID}/sound", w(self.r_sound))
        a("POST", rf"/api/engine/projects/{PID}/script", w(self.r_script))
        a("POST", rf"/api/engine/projects/{PID}/map-ai", w(self.r_map_ai))
        a("POST", rf"/api/engine/projects/{PID}/map-brush", w(self.r_map_brush))
        a("POST", rf"/api/engine/projects/{PID}/publish-ai", w(self.r_publish_ai))
        # conexões opcionais
        a("POST", rf"/api/engine/projects/{PID}/code-link", w(self.r_code_link))
        a("POST", rf"/api/engine/projects/{PID}/studio-link", w(self.r_studio_link))
        a("POST", rf"/api/engine/projects/{PID}/canvas-link", w(self.r_canvas_link))
        # exportar
        a("GET", rf"/api/engine/projects/{PID}/exports", w(lambda req, pid: req.json({"items": exporter.list_exports(self.m, pid), "platforms": exporter.PLATFORMS})))
        a("POST", rf"/api/engine/projects/{PID}/export", w(self.r_export))
        a("GET", rf"/api/engine/projects/{PID}/exports/(?P<fname>[\w .+@()%-]+)", w(self.r_export_get))
        a("DELETE", rf"/api/engine/projects/{PID}/exports/(?P<fname>[\w .+@()%-]+)", w(lambda req, pid, fname: (exporter.delete_export(self.m, pid, urllib.parse.unquote(fname)), req.json({"ok": True}))))

    # ------------------------------------------------------------------ catálogo / estado
    def r_catalog(self, req: Any) -> None:
        req.json(S.catalog())

    def r_prompts(self, req: Any) -> None:
        req.json({"prompts": [{"name": n, "text": eai.prompt(n)} for n in eai.prompt_names()]})

    def r_status(self, req: Any) -> None:
        req.json(eai.engine_status(self.store))

    # ------------------------------------------------------------------ projetos
    def r_create(self, req: Any) -> None:
        b = self._body(req)
        kind = b.get("kind") if isinstance(b.get("kind"), str) and b.get("kind") in S.KINDS else "2d"
        meta = self.m.create(text(b.get("name"), "", 60), kind, text(b.get("genre"), "", 30), text(b.get("theme"), "forest", 20), text(b.get("description"), "", 400), text(b.get("language"), "pt", 5))
        if b.get("starter") is not False:   # nasce com um jogo mínimo já jogável (as regras do gerador, sem IA)
            from .gameengine import templates as tpl
            build = tpl.build(text(b.get("prompt"), meta["description"] or meta["name"], 2000), meta["kind"], meta["genre"], meta["theme"], "short", 0, meta["name"], meta["language"])
            self.m.apply_build(meta["id"], build)
            meta = self.m.meta(meta["id"])
        req.json(meta, 201)

    def r_get(self, req: Any, pid: str) -> None:
        m = self.m.meta(pid)
        m["scenes"] = self.m.list_scenes(pid)
        m["maps"] = self.m.list_maps(pid)
        m["size"] = self.m.project_size(pid)
        req.json(m)

    # ------------------------------------------------------------------ arquivos
    def r_write(self, req: Any, pid: str) -> None:
        b = self._body(req)
        area = req.query.get("area", [b.get("area") or "game"])[0]
        path = req.query.get("path", [b.get("path") or ""])[0]
        if not isinstance(b.get("content"), str):
            raise HttpError(400, "Envie o texto em «content».")
        req.json(self.m.write_file(pid, area, path, b["content"], overwrite=b.get("overwrite") is not False))

    def r_upload(self, req: Any, pid: str) -> None:
        area = req.query.get("area", ["game"])[0]
        path = req.query.get("path", [""])[0]
        data = req.body_bytes(64 * 1024 * 1024)
        if not data:
            raise HttpError(400, "Arquivo vazio.")
        req.json(self.m.write_file(pid, area, path, data), 201)

    def r_import_zip(self, req: Any, pid: str) -> None:
        data = req.body_bytes(256 * 1024 * 1024)
        req.json(self.m.import_zip(pid, req.query.get("area", ["game"])[0], data, req.query.get("into", [""])[0]))

    def r_raw(self, req: Any, pid: str) -> None:
        area = req.query.get("area", ["game"])[0]
        p = self.m.raw_path(pid, area, req.query.get("path", [""])[0])
        ext = p.suffix.lower()
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if ext in (".svg", ".html", ".js", ".json", ".css", ".xml", ".md", ".txt"):
            req.file(p, "text/plain; charset=utf-8" if ext != ".svg" else "image/svg+xml", headers={"Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"})
        else:
            req.file(p, mime, headers={"Content-Security-Policy": "sandbox"})

    # ------------------------------------------------------------------ jogar (isolado: iframe sem acesso à API do ASTA)
    def r_play(self, req: Any, pid: str, rest: str) -> None:
        rest = urllib.parse.unquote(rest)
        kind, payload = self.m.play_file(pid, rest)
        headers = {"Content-Security-Policy": CSP, "X-Frame-Options": "SAMEORIGIN"}
        if kind == "text":
            body, mime = payload
            data = body.encode("utf-8")
            req._head(200, mime, len(data), headers)
            if req.method != "HEAD":
                req.h.wfile.write(data)
            return
        mime = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".wav": "audio/wav", ".png": "image/png", ".json": "application/json"}.get(payload.suffix.lower()) or mimetypes.guess_type(payload.name)[0] or "application/octet-stream"
        req.file(payload, mime, headers=headers, cache=rest.startswith("game/assets/"))   # mídias levam ?v=<data> no endereço: o navegador pode guardá-las

    # ------------------------------------------------------------------ jobs de IA
    def _job(self, kind: str, pid: str, req: Any, fn: Callable[[Job, eai.EngineAI], Any], opts: Dict[str, Any]) -> None:
        running = self.app.jobs.running(f"ge_{kind}_{pid}")
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))

        def work(job: Job) -> Any:
            ai = eai.EngineAI(self.store, self.m, opts, job)
            return fn(job, ai)
        job = self.app.jobs.start(f"ge_{kind}_{pid}", work)
        req.json({"job_id": job.id})

    def _opts(self, req: Any) -> Dict[str, Any]:
        b = self._body(req)
        o: Dict[str, Any] = {"team": teamlib.request_team(b), "web": b.get("web") is True, "attachment_ids": [x for x in (b.get("attachment_ids") if isinstance(b.get("attachment_ids"), list) else []) if isinstance(x, str)][:40],
                             "prompt": text(b.get("prompt"), "", 20000), "language": text(b.get("language"), "", 5), "content": "sfw" if b.get("content") == "sfw" else ""}
        for k in ("kind", "genre", "theme", "length", "mode", "scene"):
            if isinstance(b.get(k), str):
                o[k] = text(b[k], "", 60)
        o["body"] = b
        return o

    def r_generate(self, req: Any, pid: str) -> None:
        o = self._opts(req)
        if not (o["prompt"] or o["attachment_ids"]):
            raise HttpError(400, "Descreva o jogo (ou anexe algo) para gerá-lo.")
        self.m.meta(pid)
        self._job("generate", pid, req, lambda job, ai: ai.generate_game(pid), o)

    def r_code(self, req: Any, pid: str) -> None:
        o = self._opts(req)
        if not o["prompt"]:
            raise HttpError(400, "Descreva o que quer no código.")
        self.m.meta(pid)
        self._job("code", pid, req, lambda job, ai: ai.edit_code(pid), o)

    def r_asset(self, req: Any, pid: str) -> None:
        o = self._opts(req)
        if not o["prompt"]:
            raise HttpError(400, "Descreva a imagem.")
        self.m.meta(pid)
        self._job("asset", pid, req, lambda job, ai: ai.make_asset(pid), o)

    def r_sound(self, req: Any, pid: str) -> None:
        o = self._opts(req)
        if not o["prompt"] and o["body"].get("action") != "event_map":
            raise HttpError(400, "Descreva o som.")
        self.m.meta(pid)
        self._job("sound", pid, req, lambda job, ai: ai.make_sound(pid), o)

    def r_script(self, req: Any, pid: str) -> None:
        o = self._opts(req)
        if not (o["prompt"] or o["body"].get("selection")):
            raise HttpError(400, "Escreva o pedido ou selecione um trecho.")
        self.m.meta(pid)
        self._job("script", pid, req, lambda job, ai: ai.write_script(pid), o)

    def r_map_ai(self, req: Any, pid: str) -> None:
        o = self._opts(req)
        if not (o["prompt"] or o["body"].get("action") in ("regen_region", "generate")):
            raise HttpError(400, "Descreva o mapa.")
        self.m.meta(pid)
        self._job("map", pid, req, lambda job, ai: ai.make_map(pid), o)

    def r_publish_ai(self, req: Any, pid: str) -> None:
        o = self._opts(req)
        if not o["prompt"]:
            raise HttpError(400, "Diga o que quer na publicação.")
        self.m.meta(pid)
        self._job("publish", pid, req, lambda job, ai: ai.plan_publish(pid), o)

    def r_map_brush(self, req: Any, pid: str) -> None:
        """Pincel do mapa 3D (subir, descer, suavizar, aplainar, ruído, regenerar): rápido e sem IA."""
        b = self._body(req)
        m = self.m.get_map(pid, text(b.get("path"), "", 200))
        if m.get("kind") != "3d":
            raise HttpError(400, "O pincel é do mapa 3D.")
        if b.get("op") not in ("raise", "lower", "smooth", "flatten", "noise", "regen"):
            raise HttpError(400, "Operação inválida.")
        out = gmaps.edit_region_3d(m, b["op"], float(b.get("x") or 0), float(b.get("z") or 0), float(b.get("radius") or 10), float(b.get("strength") or 0.5), int(b.get("seed") or 0))
        req.json(self.m.save_map(pid, text(b.get("path"), "", 200), out) if b.get("save") is not False else out)

    # ------------------------------------------------------------------ conexões opcionais
    def r_code_link(self, req: Any, pid: str) -> None:
        """Abre (ou reaproveita) uma sessão do modo Code apontada para a pasta `game/` do projeto."""
        code = getattr(self.app, "code", None)
        if code is None:
            raise HttpError(400, "O modo Code não está disponível.")
        m = self.m.meta(pid)
        game = str(self.m.area_dir(pid, "game"))
        link = (m.get("connections") or {}).get("code_session", "")
        if link and code.get(link):
            req.json({"session_id": link, "reused": True})
            return
        from .code.manager import CodeError
        try:
            doc = code.create_session({"title": f"Game Engine · {m['name']}"[:100], "workspace": {"type": "local", "path": game}})
        except CodeError as exc:
            raise HttpError(exc.status, exc.message) from None
        self.m.update_meta(pid, {"connections": {"code_session": doc["id"]}})
        req.json({"session_id": doc["id"], "reused": False})

    def r_studio_link(self, req: Any, pid: str) -> None:
        req.json(exporter.send_audio_to_studio(self.app, self.m, pid, self._body(req)))

    def r_canvas_link(self, req: Any, pid: str) -> None:
        req.json(exporter.send_media_to_canvas(self.app, self.m, pid, self._body(req)))

    # ------------------------------------------------------------------ exportar
    def r_export(self, req: Any, pid: str) -> None:
        b = self._body(req)
        platform = text(b.get("platform"), "web", 12)
        if platform not in exporter.PLATFORMS:
            raise HttpError(400, "Plataforma inválida: " + ", ".join(exporter.PLATFORMS))
        req.json(exporter.export(self.m, pid, platform, b))

    def r_export_get(self, req: Any, pid: str, fname: str) -> None:
        p = exporter.export_path(self.m, pid, urllib.parse.unquote(fname))
        req.file(p, "application/zip", download_name=p.name)
