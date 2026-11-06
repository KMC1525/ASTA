"""Rotas HTTP do Canvas: documentos, execução (job + SSE), mídias do canvas e provedores de mídia."""
from __future__ import annotations

import json
import mimetypes
import tempfile
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any, Dict

from .canvas.engine import CanvasEngine
from .canvas.media import MIME_EXT, build_media, describe_media_presets, sniff_mime
from .canvas.schema import ASPECTS, CAPS, NODE_TYPES, SIZES, TEMPLATES, describe_types, normalize_params, normalize_result
from .jobs import HttpError, Job
from .providers import ProviderError
from .hf import REPO_RE
from .util import hardware_info, new_id, safe_filename, text


class CanvasRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store
        self.cs = app.store.canvases

    def register(self) -> None:
        a = self.app.add
        a("GET", r"/api/canvas-templates", self.r_templates)
        a("GET", r"/api/canvases", self.r_list)
        a("POST", r"/api/canvases", self.r_create)
        a("GET", r"/api/canvases/(?P<cid>[\w-]+)", self.r_get)
        a("PUT", r"/api/canvases/(?P<cid>[\w-]+)", self.r_save)
        a("DELETE", r"/api/canvases/(?P<cid>[\w-]+)", self.r_delete)
        a("POST", r"/api/canvases/(?P<cid>[\w-]+)/meta", self.r_meta)
        a("POST", r"/api/canvases/(?P<cid>[\w-]+)/duplicate", self.r_duplicate)
        a("POST", r"/api/canvases/(?P<cid>[\w-]+)/run", self.r_run)
        a("POST", r"/api/canvases/(?P<cid>[\w-]+)/nodes/(?P<nid>[\w-]+)/autofill", self.r_autofill)
        a("GET", r"/api/canvases/(?P<cid>[\w-]+)/download", self.r_download)
        a("POST", r"/api/canvases/(?P<cid>[\w-]+)/assets", self.r_asset_upload)
        a("GET", r"/api/canvases/(?P<cid>[\w-]+)/assets/(?P<fname>[\w][\w.-]*)", self.r_asset_get)
        a("DELETE", r"/api/canvases/(?P<cid>[\w-]+)/assets/(?P<aid>[\w-]+)", self.r_asset_delete)

        a("GET", r"/api/media/providers", self.r_media_providers)
        a("POST", r"/api/media/test", self.r_media_test)
        a("GET", r"/api/media/models", self.r_media_models)
        a("GET", r"/api/media/local/state", self.r_local_state)
        a("GET", r"/api/media/local/options", self.r_local_options)
        a("GET", r"/api/media/local/quants", self.r_local_quants)
        a("POST", r"/api/media/local/download", self.r_local_download)

    # ------------------------------------------------------------------ documentos
    def _canvas(self, cid: str) -> Dict[str, Any]:
        c = self.cs.get(cid)
        if not c:
            raise HttpError(404, "Canvas não encontrado")
        return c

    def _job(self, cid: str):
        return self.app.jobs.running(f"canvas:{cid}")

    def r_templates(self, req) -> None:
        req.json({"templates": TEMPLATES, "types": describe_types(), "caps": list(CAPS), "sizes": list(SIZES), "aspects": list(ASPECTS),
                  "defaults": {k: normalize_params(k, {}) for k in NODE_TYPES}, "default_result": normalize_result({})})

    def r_list(self, req) -> None:
        req.json(self.cs.list())

    def r_create(self, req) -> None:
        body = req.body_json()
        body = body if isinstance(body, dict) else {}
        c = self.cs.create(text(body.get("name"), "", 80), text(body.get("template"), "blank", 20), text(body.get("prompt"), "", 6000))
        ids = [text(i, "", 60) for i in body.get("attachment_ids")][:20] if isinstance(body.get("attachment_ids"), list) else []
        if ids:
            c = self._attach_uploads(c["id"], ids) or c
        req.json(c, 201)

    def _attach_uploads(self, cid: str, ids: list):
        """Anexos do compositor viram nós: imagens/vídeos/áudios → um nó "Mídia"; documentos com texto → um nó "Texto" cada."""
        from . import attachments as att

        limit = int(self.store.get_settings()["server"].get("max_upload_mb", 200)) * 1024 * 1024
        files, texts = [], []
        for uid in ids:
            meta = self.store.get_upload(uid)
            if not meta:
                continue
            path = Path(meta["path"])
            if not path.is_file() or path.stat().st_size > limit:
                continue
            data = path.read_bytes()
            mime = sniff_mime(data)
            kind = mime.split("/")[0]
            if kind in ("image", "audio", "video"):
                a = self.cs.add_asset(cid, data, MIME_EXT.get(mime, "bin"), kind, name=meta["name"], mime=mime, provider="upload")
                if a:
                    files.append(a["id"])
            else:
                item = att.analyze(path, meta["name"], meta.get("mime", ""), max_chars=6000)
                if item.get("text"):
                    texts.append((meta["name"], item["text"]))
        nodes, y = [], 40
        if files:
            nodes.append({"id": new_id("n_"), "type": "upload", "x": -360, "y": y, "title": "Anexos", "params": {"files": files}})
            y += 300
        for name, body_text in texts[:6]:
            nodes.append({"id": new_id("n_"), "type": "text", "x": -360, "y": y, "title": name[:40], "params": {"text": body_text}})
            y += 240
        return self.cs.append_nodes(cid, nodes) if nodes else None

    def r_get(self, req, cid: str) -> None:
        self._canvas(cid)
        job = self._job(cid)
        if not job:
            self.cs.reset_running(cid)  # nó "em execução" sem tarefa: a execução foi interrompida
        c = self._canvas(cid)
        c["stale"] = CanvasEngine(self.store, cid).stale_ids(c)
        c["job_id"] = job.id if job else ""
        req.json(c)

    def r_save(self, req, cid: str) -> None:
        body = req.body_json(32 * 1024 * 1024)
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        saved = self.cs.save_layout(cid, body)
        if not saved:
            raise HttpError(404, "Canvas não encontrado")
        req.json({"id": cid, "updated": saved["updated"], "stale": CanvasEngine(self.store, cid).stale_ids(saved)})

    def r_meta(self, req, cid: str) -> None:
        body = req.body_json()
        c = self.cs.update_meta(cid, body.get("name") if "name" in body else None, body.get("description") if "description" in body else None)
        if not c:
            raise HttpError(404, "Canvas não encontrado")
        req.json(self.cs.summary(c))

    def r_delete(self, req, cid: str) -> None:
        if self._job(cid):
            raise HttpError(409, "Este canvas está gerando. Cancele a geração antes de apagá-lo.")
        req.json({"ok": self.cs.delete(cid)})

    def r_duplicate(self, req, cid: str) -> None:
        c = self.cs.duplicate(cid)
        if not c:
            raise HttpError(404, "Canvas não encontrado")
        req.json(self.cs.summary(c), 201)

    # ------------------------------------------------------------------ execução
    def r_run(self, req, cid: str) -> None:
        self._canvas(cid)
        body = req.body_json()
        body = body if isinstance(body, dict) else {}
        running = self._job(cid)
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))
        nodes = [text(n, "", 24) for n in (body.get("nodes") or [])][:200] if isinstance(body.get("nodes"), list) else None
        force = bool(body.get("force"))

        def work(job: Job) -> None:
            CanvasEngine(self.store, cid, job.emit, lambda: job.cancelled).run(nodes or None, force)

        job = self.app.jobs.start(f"canvas:{cid}", work)
        req.json({"job_id": job.id})

    def r_autofill(self, req, cid: str, nid: str) -> None:
        c = self._canvas(cid)
        node = next((n for n in c["nodes"] if n["id"] == nid), None)
        if not node or node["type"] != "editor":
            raise HttpError(404, "Nó Editor não encontrado")
        eng = CanvasEngine(self.store, cid)
        tl = eng.auto_timeline(c, node)
        self.cs.patch_node_params(cid, nid, {"timeline": tl})
        node = next(n for n in self._canvas(cid)["nodes"] if n["id"] == nid)
        req.json({"timeline": node["params"]["timeline"]})

    # ------------------------------------------------------------------ mídias do canvas
    def r_asset_upload(self, req, cid: str) -> None:
        self._canvas(cid)
        limit = int(self.store.get_settings()["server"].get("max_upload_mb", 200)) * 1024 * 1024
        if req.content_length() > limit:
            raise HttpError(413, f"Arquivo maior que o limite de {limit // 1024 // 1024} MB")
        name = safe_filename(urllib.parse.unquote(req.headers.get("X-Filename", "arquivo")), "arquivo")
        data = req.body_bytes(limit)
        mime = sniff_mime(data)  # o tipo vem do conteúdo, nunca do nome nem do Content-Type enviado
        kind = mime.split("/")[0] if mime.split("/")[0] in ("image", "audio", "video") else ""
        if not data or not kind:
            raise HttpError(400, "Envie uma imagem, um vídeo ou um áudio válido (PNG, JPG, WebP, GIF, MP4, WebM, MP3, WAV, OGG, FLAC, M4A…).")
        file_ext = MIME_EXT.get(mime, "bin")
        a = self.cs.add_asset(cid, data, file_ext, kind, name=name, mime=mime, node=text(req.query.get("node", [""])[0], "", 24), provider="upload")
        if not a:
            raise HttpError(400, "Não foi possível salvar o arquivo.")
        node_id = text(req.query.get("node", [""])[0], "", 24)
        if node_id:  # já anexa ao nó (Mídia ou Style Folder)
            c = self._canvas(cid)
            node = next((n for n in c["nodes"] if n["id"] == node_id), None)
            if node and node["type"] in ("upload", "style_folder"):
                self.cs.patch_node_params(cid, node_id, {"files": node["params"]["files"] + [a["id"]]})
        req.json(a, 201)

    def r_asset_get(self, req, cid: str, fname: str) -> None:
        c = self._canvas(cid)
        path = self.cs.asset_path(cid, fname)
        if not path:
            raise HttpError(404, "Arquivo não encontrado")
        rec = next((a for a in c["assets"] if a["file"] == fname), None)
        mime = (rec or {}).get("mime") or mimetypes.guess_type(fname)[0] or "application/octet-stream"
        if mime.split("/")[0] not in ("image", "audio", "video"):
            mime = "application/octet-stream"
        dl = "1" in (req.query.get("download") or [])
        req.file(path, mime, download_name=(rec or {}).get("name", fname) if dl else "", cache=True)

    def r_asset_delete(self, req, cid: str, aid: str) -> None:
        self._canvas(cid)
        if self._job(cid):
            raise HttpError(409, "Este canvas está gerando. Aguarde terminar ou cancele.")
        req.json({"ok": self.cs.delete_asset(cid, aid)})

    def r_download(self, req, cid: str) -> None:
        c = self._canvas(cid)
        with tempfile.TemporaryDirectory() as tmp:
            zp = Path(tmp) / "canvas.zip"
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:
                z.writestr("canvas.json", json.dumps(c, ensure_ascii=False, indent=2))
                for a in c["assets"]:
                    p = self.cs.asset_path(cid, a["file"])
                    if p:
                        z.write(p, f"assets/{a['file']}")
            req.file(zp, "application/zip", download_name=f"{safe_filename(c['name'], 'canvas')}.zip")

    # ------------------------------------------------------------------ provedores de mídia
    def r_media_providers(self, req) -> None:
        req.json({"providers": describe_media_presets(self.store.get_settings()), "active": self.store.get_settings()["media"]["active"]})

    def r_media_test(self, req) -> None:
        body = req.body_json()
        pid = text(body.get("provider"), "", 40)
        try:
            prov = build_media(self.store.get_settings(), pid, models_dir=self.store.models_dir)
            req.json({"ok": True, "message": prov.test()})
        except ProviderError as exc:
            raise HttpError(502, str(exc))

    def r_media_models(self, req) -> None:
        pid = text(req.query.get("provider", [""])[0], "", 40)
        cap = text(req.query.get("cap", ["image"])[0], "image", 12)
        try:
            req.json({"models": build_media(self.store.get_settings(), pid, models_dir=self.store.models_dir).list_models(cap)})
        except ProviderError as exc:
            raise HttpError(502, str(exc))

    # ------------------------------------------------------------------ modelos locais do Canvas: a precisão é escolhida antes do download
    def _hf_token(self) -> str:
        return (self.store.get_settings().get("hf") or {}).get("token", "")

    def r_local_state(self, req) -> None:
        from .canvas import localmodels as lm
        from .canvas.media import media_config

        cfg = media_config(self.store.get_settings(), "local_hf")
        try:
            lm._hub()
            libs = True
        except ProviderError:
            libs = False
        out = {}
        for cap, model in cfg["models"].items():
            out[cap] = {"model": model, "precision": lm.downloaded_precision(model) if libs and model else ""}
        req.json({"libs": libs, "models": out})

    def r_local_options(self, req) -> None:
        from .canvas import localmodels as lm

        model = text(req.query.get("model", [""])[0], "", 200)
        if not REPO_RE.match(model):
            raise HttpError(400, "Informe o modelo no formato dono/nome.")
        try:
            req.json(lm.options(model, self._hf_token(), bool(hardware_info().get("gpu"))))
        except ProviderError as exc:
            raise HttpError(502, str(exc))
        except Exception as exc:  # noqa: BLE001 — erros da biblioteca do Hugging Face (repositório inexistente, sem rede…)
            raise HttpError(502, f"Não foi possível consultar o modelo: {exc}")

    def r_local_quants(self, req) -> None:
        """Versões menores (quantizadas, da comunidade) do modelo, para baixar no lugar do original."""
        from .canvas import localmodels as lm

        model = text(req.query.get("model", [""])[0], "", 200)
        if not REPO_RE.match(model):
            raise HttpError(400, "Informe o modelo no formato dono/nome.")
        try:
            req.json({"model": model, "variants": lm.quantized_variants(model, self._hf_token())})
        except Exception as exc:  # noqa: BLE001 — sem rede / Hugging Face fora do ar
            raise HttpError(502, f"Não foi possível procurar versões menores: {exc}")

    def r_local_download(self, req) -> None:
        from .canvas import localmodels as lm

        body = req.body_json()
        model, precision = text(body.get("model"), "", 200), text(body.get("precision"), "", 8)
        if not REPO_RE.match(model):
            raise HttpError(400, "Informe o modelo no formato dono/nome.")
        if precision not in lm.PRECISIONS:
            raise HttpError(400, "Escolha a precisão (quantização) do modelo antes de baixar.")
        running = self.app.jobs.running("local_model")
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))

        def work(job: Job) -> None:
            import time

            job.emit({"type": "start", "model": model, "precision": precision})
            last = [0.0]

            def progress(done: int, total: int) -> None:
                if time.time() - last[0] > 0.4:
                    last[0] = time.time()
                    job.emit({"type": "progress", "done": done, "total": total})

            lm.download(model, precision, self._hf_token(), progress, lambda: job.cancelled)
            job.emit({"type": "done", "model": model, "precision": precision})

        job = self.app.jobs.start("local_model", work)
        req.json({"job_id": job.id})
