"""Rotas HTTP do modo Data (`/api/data/...`)."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any, Callable, Dict

from . import team as teamlib
from .data import DataError, DataManager, agents as dai
from .data import schema as dschema
from .data.manager import MEDIA_INLINE
from .jobs import HttpError, Job
from .util import text

KIND = r"(?P<kind>database|dataset)"
IID = r"(?P<iid>[\w-]+)"


def _http(exc: DataError) -> HttpError:
    return HttpError(exc.status, exc.message)


class DataRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store
        self.m = DataManager(app.store)
        app.data = self.m

    @staticmethod
    def _body(req: Any, limit: int = 8 * 1024 * 1024) -> Dict[str, Any]:
        if not hasattr(req, "_dt_body"):
            b = req.body_json(limit)
            req._dt_body = b if isinstance(b, dict) else {}
        return req._dt_body

    def _w(self, fn: Callable[..., Any]) -> Callable[..., None]:
        def run(req: Any, **kw: Any) -> None:
            try:
                fn(req, **kw)
            except DataError as exc:
                raise _http(exc) from None
            except ValueError as exc:
                raise HttpError(400, str(exc)) from None
        return run

    def register(self) -> None:
        a, w = self.app.add, self._w
        a("GET", r"/api/data/catalog", w(lambda req: req.json(dschema.catalog())))
        a("GET", r"/api/data/status", w(lambda req: req.json(dai.provider_status(self.store))))
        a("GET", r"/api/data/items", w(self.r_list))
        a("POST", r"/api/data/items", w(self.r_create))
        a("GET", rf"/api/data/items/{KIND}/{IID}", w(self.r_get))
        a("PUT", rf"/api/data/items/{KIND}/{IID}", w(self.r_update))
        a("DELETE", rf"/api/data/items/{KIND}/{IID}", w(self.r_delete))
        a("POST", rf"/api/data/items/{KIND}/{IID}/duplicate", w(self.r_duplicate))
        a("POST", rf"/api/data/items/{KIND}/{IID}/records", w(self.r_save_records))
        a("POST", rf"/api/data/items/{KIND}/{IID}/merge", w(self.r_merge))
        a("GET", rf"/api/data/items/{KIND}/{IID}/rows", w(self.r_rows))
        a("POST", rf"/api/data/items/{KIND}/{IID}/edit", w(self.r_edit))
        a("POST", rf"/api/data/items/{KIND}/{IID}/columns", w(self.r_column))
        a("POST", rf"/api/data/items/{KIND}/{IID}/clean", w(self.r_clean))
        a("POST", rf"/api/data/items/{KIND}/{IID}/schema/infer", w(lambda req, kind, iid: req.json(self.m.infer_schema(kind, iid, self._body(req).get("apply") is True))))
        a("GET", rf"/api/data/items/{KIND}/{IID}/media", w(lambda req, kind, iid: req.json({"items": self.m.list_media(kind, iid)})))
        a("POST", rf"/api/data/items/{KIND}/{IID}/media", w(self.r_media_add))
        a("GET", rf"/api/data/items/{KIND}/{IID}/media/(?P<fname>[\w .+@()%-]+)", w(self.r_media_get))
        a("DELETE", rf"/api/data/items/{KIND}/{IID}/media/(?P<fname>[\w .+@()%-]+)", w(lambda req, kind, iid, fname: (self.m.delete_media(kind, iid, urllib.parse.unquote(fname)), req.json({"ok": True}))[1]))
        a("GET", rf"/api/data/items/{KIND}/{IID}/profile", w(lambda req, kind, iid: req.json(self.m.profile(kind, iid))))
        a("POST", rf"/api/data/items/{KIND}/{IID}/dedupe", w(self.r_dedupe))
        a("GET", rf"/api/data/items/{KIND}/{IID}/history", w(lambda req, kind, iid: req.json({"items": self.m.history(kind, iid)})))
        a("POST", rf"/api/data/items/{KIND}/{IID}/history/restore", w(self.r_restore))
        a("POST", rf"/api/data/items/{KIND}/{IID}/import", w(self.r_import))
        a("POST", rf"/api/data/items/{KIND}/{IID}/export", w(self.r_export))
        a("GET", rf"/api/data/items/{KIND}/{IID}/exports", w(lambda req, kind, iid: req.json({"items": self.m.list_exports(kind, iid)})))
        a("GET", rf"/api/data/items/{KIND}/{IID}/exports/(?P<fname>[\w .+@()%-]+)", w(self.r_export_get))
        # upgrade: create from uploaded file (new item)
        a("POST", r"/api/data/upgrade/import", w(self.r_upgrade_import))
        # AI jobs
        a("POST", rf"/api/data/items/{KIND}/{IID}/synthetic", w(self.r_synthetic))
        a("POST", rf"/api/data/items/{KIND}/{IID}/scrape", w(self.r_scrape))
        a("POST", rf"/api/data/items/{KIND}/{IID}/upgrade", w(self.r_upgrade_ai))

    # ------------------------------------------------------------------ CRUD
    def r_list(self, req: Any) -> None:
        kind = req.query.get("kind", [None])[0]
        req.json({"items": self.m.list(kind)})

    def r_create(self, req: Any) -> None:
        b = self._body(req)
        kind = text(b.get("kind"), "dataset", 16)
        item = self.m.create(kind, text(b.get("name"), "", 100), text(b.get("description"), "", 1000), b.get("schema"), b.get("records"), b.get("tags"), b.get("modalities"))
        req.json(item, 201)

    def r_get(self, req: Any, kind: str, iid: str) -> None:
        req.json(self.m.get(kind, iid))

    def r_update(self, req: Any, kind: str, iid: str) -> None:
        req.json(self.m.update_meta(kind, iid, self._body(req)))

    def r_delete(self, req: Any, kind: str, iid: str) -> None:
        self.m.delete(kind, iid)
        req.json({"ok": True})

    def r_duplicate(self, req: Any, kind: str, iid: str) -> None:
        b = self._body(req)
        req.json(self.m.duplicate(kind, iid, text(b.get("name"), "", 100)), 201)

    def r_save_records(self, req: Any, kind: str, iid: str) -> None:
        b = self._body(req, 20 * 1024 * 1024)
        mode = text(b.get("mode"), "replace", 16)
        if mode == "append":
            req.json(self.m.append_records(kind, iid, b.get("records") if isinstance(b.get("records"), list) else [], text(b.get("label"), "append", 40)))
        else:
            req.json(self.m.save_records(kind, iid, b.get("records") if isinstance(b.get("records"), list) else [], b.get("schema"), text(b.get("label"), "edit", 40)))

    def r_merge(self, req: Any, kind: str, iid: str) -> None:
        b = self._body(req)
        sk = text(b.get("source_kind"), kind, 16)
        sid = text(b.get("source_id"), "", 80)
        if not sid:
            raise HttpError(400, "Informe o item de origem para mesclar.")
        keys = b.get("keys") if isinstance(b.get("keys"), list) else None
        req.json(self.m.merge_items(kind, iid, sk, sid, text(b.get("strategy"), "append", 16), keys, text(b.get("conflict"), "keep_target", 16), b.get("dedupe") is True, b.get("dry_run") is True))

    def r_rows(self, req: Any, kind: str, iid: str) -> None:
        q = req.query
        where = None
        raw = (q.get("where", [""])[0] or "").strip()
        if raw:
            try:
                where = json.loads(raw)
            except ValueError:
                raise HttpError(400, "Filtro inválido (esperado um JSON {campo: texto}).") from None

        def num(name: str, default: int) -> int:
            try:
                return int(q.get(name, [str(default)])[0] or default)
            except ValueError:
                return default
        req.json(self.m.query(kind, iid, q.get("q", [""])[0], q.get("sort", [""])[0], q.get("dir", ["asc"])[0], num("offset", 0), num("limit", 100), where))

    def r_edit(self, req: Any, kind: str, iid: str) -> None:
        b = self._body(req, 20 * 1024 * 1024)
        req.json(self.m.edit_records(kind, iid, b.get("edits"), b.get("schema")))

    def r_column(self, req: Any, kind: str, iid: str) -> None:
        b = self._body(req)
        req.json(self.m.column(kind, iid, text(b.get("op"), "", 12), text(b.get("name"), "", 80), text(b.get("new_name"), "", 80), text(b.get("type"), "text", 16), b.get("default")))

    def r_clean(self, req: Any, kind: str, iid: str) -> None:
        b = self._body(req)
        req.json(self.m.clean(kind, iid, b.get("options"), b.get("apply") is True))

    def r_media_add(self, req: Any, kind: str, iid: str) -> None:
        name = urllib.parse.unquote(req.headers.get("X-Filename") or req.query.get("name", ["arquivo"])[0] or "arquivo")
        raw = req.body_bytes(26 * 1024 * 1024)
        req.json(self.m.add_media(kind, iid, name, raw), 201)

    def r_media_get(self, req: Any, kind: str, iid: str, fname: str) -> None:
        p = self.m.media_path(kind, iid, urllib.parse.unquote(fname))
        mime = MEDIA_INLINE.get(p.suffix.lower())
        # só tipos conhecidos aparecem dentro da página (e sempre isolados); SVG, HTML e o resto só baixam
        req.file(p, mime or "application/octet-stream", download_name="" if mime else p.name,
                 headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'; img-src 'self' data:; media-src 'self'"})

    def r_dedupe(self, req: Any, kind: str, iid: str) -> None:
        b = self._body(req)
        req.json(self.m.dedupe(kind, iid, b.get("keys"), b.get("ignore_case") is not False, b.get("apply") is True))

    def r_restore(self, req: Any, kind: str, iid: str) -> None:
        b = self._body(req)
        hid = text(b.get("id") or b.get("history_id"), "", 80)
        if not hid:
            raise HttpError(400, "Snapshot inválido.")
        req.json(self.m.restore(kind, iid, hid))

    # ------------------------------------------------------------------ import/export
    def r_import(self, req: Any, kind: str, iid: str) -> None:
        name = urllib.parse.unquote(req.headers.get("X-Filename") or req.query.get("name", ["arquivo"])[0] or "arquivo")
        mode = "append" if req.query.get("mode", ["replace"])[0] == "append" else "replace"
        raw = req.body_bytes(50 * 1024 * 1024)
        if not raw:
            raise HttpError(400, "Arquivo vazio.")
        req.json(self.m.import_data(kind, iid, name, raw, mode))

    def r_export(self, req: Any, kind: str, iid: str) -> None:
        b = self._body(req)
        fmt = text(b.get("format"), "json", 16)
        req.json(self.m.export(kind, iid, fmt))

    def r_export_get(self, req: Any, kind: str, iid: str, fname: str) -> None:
        p = self.m.export_path(kind, iid, urllib.parse.unquote(fname))
        mime = "application/octet-stream"
        if p.suffix == ".json":
            mime = "application/json; charset=utf-8"
        elif p.suffix == ".jsonl":
            mime = "application/x-ndjson; charset=utf-8"
        elif p.suffix == ".csv":
            mime = "text/csv; charset=utf-8"
        elif p.suffix == ".tsv":
            mime = "text/tab-separated-values; charset=utf-8"
        elif p.suffix == ".db":
            mime = "application/vnd.sqlite3"
        elif p.suffix == ".xlsx":
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif p.suffix == ".sql":
            mime = "application/sql; charset=utf-8"
        elif p.suffix in (".yaml", ".yml"):
            mime = "application/yaml; charset=utf-8"
        elif p.suffix == ".zip":
            mime = "application/zip"
        req.file(p, mime, download_name=p.name)

    def r_upgrade_import(self, req: Any) -> None:
        name = urllib.parse.unquote(req.headers.get("X-Filename") or req.query.get("name", ["arquivo"])[0] or "arquivo")
        kind = text(req.query.get("kind", ["dataset"])[0], "dataset", 16)
        raw = req.body_bytes(50 * 1024 * 1024)
        if not raw:
            raise HttpError(400, "Arquivo vazio.")
        req.json(self.m.create_from_upload(kind, text(req.query.get("item_name", [""])[0], "", 100), name, raw), 201)

    # ------------------------------------------------------------------ jobs
    def _job(self, key: str, req: Any, fn: Callable[[Job, dai.DataAI], Any], opts: Dict[str, Any]) -> None:
        running = self.app.jobs.running(key)
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))
        def work(job: Job) -> Any:
            ai = dai.DataAI(self.store, self.m, opts, job)
            return fn(job, ai)
        job = self.app.jobs.start(key, work)
        req.json({"job_id": job.id})

    def _opts(self, req: Any) -> Dict[str, Any]:
        b = self._body(req, 16 * 1024 * 1024)
        o: Dict[str, Any] = {
            "team": teamlib.request_team(b),
            "prompt": text(b.get("prompt"), "", 20000),
            "count": b.get("count"),
            "mode": text(b.get("mode"), "single", 16),
            "action": text(b.get("action"), "enrich", 20),
            "fields": [x for x in b.get("fields") if isinstance(x, str)][:40] if isinstance(b.get("fields"), list) else [],
            "language": text(b.get("language"), "", 40),
            "download_media": b.get("download_media") is True,
            "schema": b.get("schema") if isinstance(b.get("schema"), dict) else None,
            "urls": b.get("urls") if isinstance(b.get("urls"), list) else [],
            "attachment_ids": [x for x in b.get("attachment_ids") if isinstance(x, str)] if isinstance(b.get("attachment_ids"), list) else [],
        }
        return o

    def r_synthetic(self, req: Any, kind: str, iid: str) -> None:
        self.m.meta(kind, iid)
        self._job(f"data_synth_{kind}_{iid}", req, lambda job, ai: ai.generate_synthetic(kind, iid), self._opts(req))

    def r_scrape(self, req: Any, kind: str, iid: str) -> None:
        self.m.meta(kind, iid)
        b = self._body(req, 16 * 1024 * 1024)
        # o aviso de uso (open source, não comercial) precisa ser aceito antes de raspar
        if not _as_bool(b.get("ack")) and not _as_bool(req.query.get("ack", [""])[0]):
            raise HttpError(400, dschema.catalog()["web_scraping_notice"]["text"])
        self._job(f"data_scrape_{kind}_{iid}", req, lambda job, ai: ai.scrape(kind, iid), self._opts(req))

    def r_upgrade_ai(self, req: Any, kind: str, iid: str) -> None:
        self.m.meta(kind, iid)
        self._job(f"data_upgrade_{kind}_{iid}", req, lambda job, ai: ai.upgrade(kind, iid), self._opts(req))


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v or "").strip().lower() in ("1", "true", "yes", "sim", "on")
