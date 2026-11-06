"""Rotas HTTP do Studio: projetos (único/série), episódios, geração cena a cena, edição automática, mídias, timeline e exportação."""
from __future__ import annotations

import json
import mimetypes
import urllib.parse
from typing import Any, Dict

from .canvas.media import MIME_EXT, sniff_mime
from .jobs import HttpError, Job
from .studio import schema as S
from .studio.autoedit import AutoEditPipeline, describe_styles
from .studio.export import AUDIO_FORMATS, QUALITY, export_episode
from .studio.pipeline import StudioPipeline
from .util import safe_filename, text

META_FIELDS = ("name", "kind", "duration_type", "target_seconds", "style", "style_custom", "aspect", "language", "motion", "voice", "music", "captions", "revisions", "premise")


class StudioRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store
        self.ss = app.store.studio

    def register(self) -> None:
        a = self.app.add
        a("GET", r"/api/studio/meta", self.r_meta)
        a("GET", r"/api/studio/projects", self.r_list)
        a("POST", r"/api/studio/projects", self.r_create)
        a("POST", r"/api/studio/autoedit", self.r_autoedit)
        a("GET", r"/api/studio/projects/(?P<pid>[\w-]+)/job", self.r_job)
        a("GET", r"/api/studio/projects/(?P<pid>[\w-]+)", self.r_get)
        a("POST", r"/api/studio/projects/(?P<pid>[\w-]+)/meta", self.r_save_meta)
        a("DELETE", r"/api/studio/projects/(?P<pid>[\w-]+)", self.r_delete)
        a("POST", r"/api/studio/projects/(?P<pid>[\w-]+)/episodes", self.r_ep_create)
        a("POST", r"/api/studio/projects/(?P<pid>[\w-]+)/episodes/(?P<eid>[\w-]+)/meta", self.r_ep_meta)
        a("DELETE", r"/api/studio/projects/(?P<pid>[\w-]+)/episodes/(?P<eid>[\w-]+)", self.r_ep_delete)
        a("PUT", r"/api/studio/projects/(?P<pid>[\w-]+)/episodes/(?P<eid>[\w-]+)/timeline", self.r_timeline)
        a("POST", r"/api/studio/projects/(?P<pid>[\w-]+)/episodes/(?P<eid>[\w-]+)/generate", self.r_generate)
        a("POST", r"/api/studio/projects/(?P<pid>[\w-]+)/episodes/(?P<eid>[\w-]+)/export", self.r_export)
        a("GET", r"/api/studio/projects/(?P<pid>[\w-]+)/exports/(?P<fname>[\w][\w.-]*)", self.r_export_get)
        a("DELETE", r"/api/studio/projects/(?P<pid>[\w-]+)/exports/(?P<fname>[\w][\w.-]*)", self.r_export_delete)
        a("POST", r"/api/studio/projects/(?P<pid>[\w-]+)/media", self.r_media_upload)
        a("GET", r"/api/studio/projects/(?P<pid>[\w-]+)/media/(?P<fname>[\w][\w.-]*)", self.r_media_get)
        a("DELETE", r"/api/studio/projects/(?P<pid>[\w-]+)/media/(?P<aid>[\w-]+)", self.r_media_delete)
        a("GET", r"/api/studio/projects/(?P<pid>[\w-]+)/thumb/(?P<aid>[\w-]+)", self.r_thumb)

    # ------------------------------------------------------------------ util
    def _project(self, pid: str) -> Dict[str, Any]:
        p = self.ss.get(pid)
        if not p:
            raise HttpError(404, "Projeto não encontrado")
        return p

    def _episode(self, p: Dict[str, Any], eid: str) -> Dict[str, Any]:
        ep = next((e for e in p["episodes"] if e["id"] == eid), None)
        if not ep:
            raise HttpError(404, "Episódio não encontrado")
        return ep

    def _busy(self, pid: str):
        return self.app.jobs.running(f"studio:{pid}") or self.app.jobs.running(f"studio-export:{pid}")

    def _guard(self, pid: str) -> None:
        running = self._busy(pid)
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))

    @staticmethod
    def _body(req) -> Dict[str, Any]:
        b = req.body_json()
        return b if isinstance(b, dict) else {}

    @staticmethod
    def _meta_of(b: Dict[str, Any]) -> Dict[str, Any]:
        return {k: b[k] for k in META_FIELDS if k in b}

    # ------------------------------------------------------------------ catálogo e projetos
    def r_meta(self, req) -> None:
        d = S.describe()
        d["edit_styles"] = describe_styles()
        d["quality"] = list(QUALITY)
        d["audio_formats"] = list(AUDIO_FORMATS)
        req.json(d)

    def r_list(self, req) -> None:
        req.json(self.ss.list())

    def r_create(self, req) -> None:
        b = self._body(req)
        meta = self._meta_of(b)
        meta["premise"] = text(b.get("premise") or b.get("prompt"), "", 4000)
        p = self.ss.create({**meta, "prompt": text(b.get("prompt"), "", 8000)})
        req.json(p, 201)

    def r_job(self, req, pid: str) -> None:
        """O job de geração/exportação em andamento do projeto (para a tela retomar o acompanhamento depois de recarregar)."""
        self._project(pid)
        j = self.app.jobs.running(f"studio:{pid}")
        kind = "generate"
        if not j:
            j, kind = self.app.jobs.running(f"studio-export:{pid}"), "export"
        req.json({"job_id": j.id if j else None, "kind": kind if j else ""})

    def r_get(self, req, pid: str) -> None:
        req.json(self._project(pid))

    def r_save_meta(self, req, pid: str) -> None:
        self._project(pid)
        meta = self._meta_of(self._body(req))
        if not meta:
            raise HttpError(400, "Nada para salvar.")
        p = self.ss.update(pid, lambda pr: pr.update(meta))
        req.json(p)

    def r_delete(self, req, pid: str) -> None:
        self._project(pid)
        self._guard(pid)
        req.json({"ok": self.ss.delete(pid)})

    # ------------------------------------------------------------------ episódios
    def r_ep_create(self, req, pid: str) -> None:
        p = self._project(pid)
        if p["kind"] != "series" and p["episodes"]:
            raise HttpError(400, "Um projeto único tem um só vídeo. Crie uma série para ter vários episódios.")
        b = self._body(req)
        ep = S.normalize_episode({"title": text(b.get("title"), "", 120) or f"Episódio {len(p['episodes']) + 1}", "prompt": text(b.get("prompt"), "", 8000), "target": b.get("target") or 0}, len(p["episodes"]))
        self.ss.update(pid, lambda pr: pr["episodes"].append(ep))
        req.json(self._project(pid), 201)

    def r_ep_meta(self, req, pid: str, eid: str) -> None:
        self._episode(self._project(pid), eid)
        b = self._body(req)

        def fn(pr: Dict[str, Any]) -> None:
            e = next(x for x in pr["episodes"] if x["id"] == eid)
            for k in ("title", "prompt", "target"):
                if k in b:
                    e[k] = b[k]

        req.json(self.ss.update(pid, fn))

    def r_ep_delete(self, req, pid: str, eid: str) -> None:
        p = self._project(pid)
        self._episode(p, eid)
        if len(p["episodes"]) <= 1:
            raise HttpError(400, "O projeto precisa ter pelo menos um episódio.")
        self._guard(pid)
        req.json(self.ss.update(pid, lambda pr: pr.update(episodes=[e for e in pr["episodes"] if e["id"] != eid])))

    def r_timeline(self, req, pid: str, eid: str) -> None:
        self._episode(self._project(pid), eid)
        b = self._body(req)
        tl = b.get("timeline") if isinstance(b.get("timeline"), dict) else b

        def fn(pr: Dict[str, Any]) -> None:
            e = next(x for x in pr["episodes"] if x["id"] == eid)
            e["timeline"] = S.normalize_timeline(tl)
            ids = {a["id"] for a in pr["assets"]}
            e["timeline"]["clips"] = [c for c in e["timeline"]["clips"] if not c["asset"] or c["asset"] in ids]  # clipe de ativo apagado some
            if e["origin"] != "autoedit" and e["status"] in ("draft", "planned"):
                e["origin"] = "manual" if not e["scenes"] else e["origin"]

        p = self.ss.update(pid, fn)
        req.json({"ok": True, "duration": next(e["timeline"]["duration"] for e in p["episodes"] if e["id"] == eid)})

    # ------------------------------------------------------------------ geração / edição automática / exportação
    def r_generate(self, req, pid: str, eid: str) -> None:
        p = self._project(pid)
        self._episode(p, eid)
        self._guard(pid)
        b = self._body(req)
        prompt = text(b.get("prompt"), "", 8000)
        ids = [x for x in (b.get("attachment_ids") or []) if isinstance(x, str)][:20] if isinstance(b.get("attachment_ids"), list) else []
        redo = [text(x, "", 24) for x in (b.get("redo") or [])][:120] if isinstance(b.get("redo"), list) else []
        if not prompt and not self._episode(p, eid)["prompt"] and not p["premise"] and not ids and not self._episode(p, eid)["scenes"]:
            raise HttpError(400, "Descreva o vídeo que você quer criar (ou anexe algo) para gerá-lo.")
        req_body = {"project_id": pid, "episode_id": eid, "prompt": prompt, "attachment_ids": ids, "redo": redo, "replan": bool(b.get("replan"))}

        def work(job: Job) -> None:
            StudioPipeline(self.store, job.emit, lambda: job.cancelled).run(req_body)

        job = self.app.jobs.start(f"studio:{pid}", work)
        req.json({"job_id": job.id})

    def r_autoedit(self, req) -> None:
        b = self._body(req)
        ids = [x for x in (b.get("attachment_ids") or []) if isinstance(x, str)][:60] if isinstance(b.get("attachment_ids"), list) else []
        if not ids:
            raise HttpError(400, "Anexe os vídeos, imagens e áudios que você quer editar.")
        pid = text(b.get("project_id"), "", 40)
        if pid:
            self._project(pid)
            self._guard(pid)
        running = self.app.jobs.running("studio-autoedit")
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))
        body = {"attachment_ids": ids, "prompt": text(b.get("prompt"), "", 4000), "style": b.get("style"), "target_seconds": b.get("target_seconds") or 0, "aspect": b.get("aspect"),
                "bpm": b.get("bpm") or 0, "name": text(b.get("name"), "", 100), "project_id": pid, "language": text(b.get("language"), "pt-BR", 12)}

        def work(job: Job) -> None:
            AutoEditPipeline(self.store, job.emit, lambda: job.cancelled).run(body)

        job = self.app.jobs.start("studio-autoedit", work)
        req.json({"job_id": job.id})

    def r_export(self, req, pid: str, eid: str) -> None:
        self._episode(self._project(pid), eid)
        self._guard(pid)
        b = self._body(req)
        mode = b.get("mode") if b.get("mode") in S.EXPORT_MODES else "full"
        quality = b.get("quality") if b.get("quality") in QUALITY else "720p"
        fmt = b.get("format") if b.get("format") in AUDIO_FORMATS else "m4a"

        def work(job: Job) -> None:
            from .canvas.media import Ctl

            ctl = Ctl(check=lambda: (_ for _ in ()).throw(ValueError("cancelado")) if job.cancelled else None, note=lambda m: job.emit({"type": "note", "message": m}))
            job.emit({"type": "start", "mode": mode})
            rec = export_episode(self.store, pid, eid, mode, quality, fmt, 24, ctl)
            job.emit({"type": "done", "project_id": pid, "episode_id": eid, "export": rec, "url": f"/api/studio/projects/{pid}/exports/{rec['file']}"})

        job = self.app.jobs.start(f"studio-export:{pid}", work)
        req.json({"job_id": job.id})

    def r_export_get(self, req, pid: str, fname: str) -> None:
        self._project(pid)
        path = self.ss.export_path(pid, fname)
        if not path:
            raise HttpError(404, "Exportação não encontrada")
        mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        req.file(path, mime, download_name=fname if "1" in (req.query.get("download") or []) else "", cache=True)

    def r_export_delete(self, req, pid: str, fname: str) -> None:
        self._project(pid)
        path = self.ss.export_path(pid, fname)
        if path:
            path.unlink(missing_ok=True)

        def fn(pr: Dict[str, Any]) -> None:
            for e in pr["episodes"]:
                e["exports"] = [x for x in e["exports"] if x.get("file") != fname]

        self.ss.update(pid, fn)
        req.json({"ok": True})

    # ------------------------------------------------------------------ mídias
    def r_media_upload(self, req, pid: str) -> None:
        self._project(pid)
        limit = int(self.store.get_settings()["server"].get("max_upload_mb", 200)) * 1024 * 1024
        if req.content_length() > limit:
            raise HttpError(413, f"Arquivo maior que o limite de {limit // 1024 // 1024} MB")
        name = safe_filename(urllib.parse.unquote(req.headers.get("X-Filename", "arquivo")), "arquivo")
        data = req.body_bytes(limit)
        mime = sniff_mime(data)
        kind = mime.split("/")[0] if mime.split("/")[0] in ("image", "audio", "video") else ""
        if not data or not kind:
            raise HttpError(400, "Envie uma imagem, um vídeo ou um áudio válido.")
        rec = self.ss.add_asset(pid, data, MIME_EXT.get(mime, "bin"), kind, name=name, mime=mime, source="upload")
        if not rec:
            raise HttpError(400, "Não foi possível salvar o arquivo.")
        req.json(rec, 201)

    def r_media_get(self, req, pid: str, fname: str) -> None:
        p = self._project(pid)
        path = self.ss.media_path(pid, fname)
        if not path:
            raise HttpError(404, "Arquivo não encontrado")
        rec = next((a for a in p["assets"] if a["file"] == fname), None)
        mime = (rec or {}).get("mime") or mimetypes.guess_type(fname)[0] or "application/octet-stream"
        if mime.split("/")[0] not in ("image", "audio", "video"):
            mime = "application/octet-stream"
        req.file(path, mime, download_name=(rec or {}).get("name", fname) if "1" in (req.query.get("download") or []) else "", cache=True)

    def r_thumb(self, req, pid: str, aid: str) -> None:
        self._project(pid)
        path = self.ss.thumb(pid, aid)
        if not path:
            raise HttpError(404, "Sem miniatura")
        req.file(path, "image/jpeg", cache=True)

    def r_media_delete(self, req, pid: str, aid: str) -> None:
        self._project(pid)
        self._guard(pid)
        req.json({"ok": self.ss.delete_asset(pid, aid)})
