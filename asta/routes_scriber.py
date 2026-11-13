"""Rotas HTTP do Scriber (`/api/scriber/…`): projetos, documento, lorebooks, histórico, exportar/importar, ortografia, busca na web e a IA de cada aba.
A lógica fica em `asta/scriber/`; aqui só se valida o corpo, chama o gerenciador e devolve JSON."""
from __future__ import annotations

import json
import urllib.parse
from typing import Any, Callable, Dict

from . import team as teamlib
from .jobs import HttpError, Job
from .scriber import ScriberError, ScriberManager, agents as sai, lore as L, schema as S, spell, stats
from .scriber.manager import EXPORT_FORMATS, MAX_IMPORT
from .util import text

PID = r"(?P<pid>[\w-]+)"
MIME = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "md": "text/markdown; charset=utf-8", "txt": "text/plain; charset=utf-8", "html": "text/html; charset=utf-8"}
DOC_LIMIT = 28 * 1024 * 1024


def _http(exc: ScriberError) -> HttpError:
    return HttpError(exc.status, exc.message)


class ScriberRoutes:
    def __init__(self, app: Any):
        self.app = app
        self.store = app.store
        self.m = ScriberManager(app.store)
        app.scriber = self.m

    # ------------------------------------------------------------------ infra
    @staticmethod
    def _body(req: Any, limit: int = 8 * 1024 * 1024) -> Dict[str, Any]:
        if not hasattr(req, "_sc_body"):
            b = req.body_json(limit)
            req._sc_body = b if isinstance(b, dict) else {}
        return req._sc_body

    def _w(self, fn: Callable[..., Any]) -> Callable[..., None]:
        def run(req: Any, **kw: Any) -> None:
            try:
                fn(req, **kw)
            except ScriberError as exc:
                raise _http(exc) from None
            except ValueError as exc:
                raise HttpError(400, str(exc)) from None
        return run

    def register(self) -> None:
        a, w = self.app.add, self._w
        a("GET", r"/api/scriber/catalog", w(lambda req: req.json(S.catalog())))
        a("GET", r"/api/scriber/status", w(lambda req: req.json(sai.scriber_status(self.store))))
        a("GET", r"/api/scriber/prompts", w(lambda req: req.json({"prompts": [{"name": n, "text": sai.prompt(n)} for n in sai.prompt_names()]})))
        a("POST", r"/api/scriber/estimate", w(lambda req: req.json(sai.estimate(self._body(req)))))
        a("GET", r"/api/scriber/projects", w(lambda req: req.json({"projects": self.m.list()})))
        a("POST", r"/api/scriber/projects", w(self.r_create))
        a("GET", rf"/api/scriber/projects/{PID}", w(self.r_get))
        a("PUT", rf"/api/scriber/projects/{PID}", w(lambda req, pid: req.json(self.m.update_meta(pid, self._body(req)))))
        a("DELETE", rf"/api/scriber/projects/{PID}", w(lambda req, pid: (self.m.delete(pid), req.json({"ok": True}))))
        a("POST", rf"/api/scriber/projects/{PID}/duplicate", w(lambda req, pid: req.json(self.m.duplicate(pid, text(self._body(req).get("name"), "", 100)), 201)))
        # documento
        a("GET", rf"/api/scriber/projects/{PID}/document", w(lambda req, pid: req.json(self.m.get_doc(pid))))
        a("PUT", rf"/api/scriber/projects/{PID}/document", w(self.r_save_doc))
        # histórico
        a("GET", rf"/api/scriber/projects/{PID}/history", w(lambda req, pid: req.json({"items": self.m.history(pid)})))
        a("POST", rf"/api/scriber/projects/{PID}/history/restore", w(lambda req, pid: req.json(self.m.restore(pid, text(self._body(req).get("id"), "", 60)))))
        a("POST", rf"/api/scriber/projects/{PID}/snapshot", w(lambda req, pid: req.json({"id": self.m.snapshot(pid, text(self._body(req).get("label"), "manual", 100))})))
        # lorebooks e fontes
        a("GET", rf"/api/scriber/projects/{PID}/lorebooks", w(lambda req, pid: req.json({"books": self.m.get_books(pid), "kinds": list(L.KINDS)})))
        a("PUT", rf"/api/scriber/projects/{PID}/lorebooks", w(lambda req, pid: req.json({"books": self.m.save_books(pid, self._body(req).get("books"))})))
        a("POST", rf"/api/scriber/projects/{PID}/lorebooks/import", w(self.r_lore_import))
        a("GET", rf"/api/scriber/projects/{PID}/lorebooks/(?P<bid>[\w-]+)/export", w(self.r_lore_export))
        a("GET", rf"/api/scriber/projects/{PID}/sources", w(lambda req, pid: req.json({"sources": self.m.get_sources(pid)})))
        a("PUT", rf"/api/scriber/projects/{PID}/sources", w(lambda req, pid: req.json({"sources": self.m.save_sources(pid, self._body(req).get("sources"))})))
        # importar / exportar
        a("POST", rf"/api/scriber/projects/{PID}/import", w(self.r_import))
        a("GET", rf"/api/scriber/projects/{PID}/exports", w(lambda req, pid: req.json({"items": self.m.list_exports(pid), "formats": list(EXPORT_FORMATS)})))
        a("POST", rf"/api/scriber/projects/{PID}/export", w(self.r_export))
        a("GET", rf"/api/scriber/projects/{PID}/exports/(?P<fname>[\w .+@()%-]+)", w(self.r_export_get))
        a("DELETE", rf"/api/scriber/projects/{PID}/exports/(?P<fname>[\w .+@()%-]+)", w(lambda req, pid, fname: (self.m.delete_export(pid, urllib.parse.unquote(fname)), req.json({"ok": True}))))
        # ortografia (sem IA) e tipografia
        a("POST", r"/api/scriber/proofread", w(self.r_proofread))
        a("POST", r"/api/scriber/stats", w(self.r_stats))
        a("POST", r"/api/scriber/typography", w(self.r_typography))
        # busca na web nativa
        a("POST", r"/api/scriber/web/search", w(self.r_search))
        a("POST", r"/api/scriber/web/read", w(self.r_search_read))
        # IA
        a("POST", rf"/api/scriber/projects/{PID}/generate", w(self.r_generate))
        a("POST", rf"/api/scriber/projects/{PID}/edit", w(self.r_edit))
        a("POST", rf"/api/scriber/projects/{PID}/proofread-ai", w(self.r_proofread_ai))

    # ------------------------------------------------------------------ projetos
    def r_create(self, req: Any) -> None:
        b = self._body(req)
        meta = self.m.create(text(b.get("name"), "", 100), b.get("type") if isinstance(b.get("type"), str) else S.DEFAULT_TYPE, b.get("language") if isinstance(b.get("language"), str) else "",
                             text(b.get("description"), "", 400), b.get("content") if isinstance(b.get("content"), str) else "", b.get("format"), b.get("gen"))
        req.json(meta, 201)

    def r_get(self, req: Any, pid: str) -> None:
        m = self.m.meta(pid)
        m["exports"] = self.m.list_exports(pid)[:10]
        req.json(m)

    def r_save_doc(self, req: Any, pid: str) -> None:
        b = self._body(req, DOC_LIMIT)
        if isinstance(b.get("blocks"), list):
            res = self.m.save_doc(pid, blocks=b["blocks"], label=text(b.get("label"), "", 100))
        elif isinstance(b.get("html"), str):
            res = self.m.save_doc(pid, html_src=b["html"], label=text(b.get("label"), "", 100))
        elif isinstance(b.get("markdown"), str):
            res = self.m.save_doc(pid, markdown=b["markdown"], label=text(b.get("label"), "", 100))
        else:
            raise HttpError(400, "Envie «html», «blocks» ou «markdown».")
        req.json(res)

    # ------------------------------------------------------------------ lorebooks
    def r_lore_import(self, req: Any, pid: str) -> None:
        b = self._body(req, 16 * 1024 * 1024)
        data = b.get("data") if b.get("data") is not None else b.get("text")
        if data is None:
            raise HttpError(400, "Envie o conteúdo em «data» (JSON) ou «text».")
        req.json(self.m.import_book(pid, data, text(b.get("name"), "", 80)), 201)

    def r_lore_export(self, req: Any, pid: str, bid: str) -> None:
        book = next((x for x in self.m.get_books(pid) if x["id"] == bid), None)
        if not book:
            raise HttpError(404, "Lorebook não encontrado.")
        if req.query.get("format", ["json"])[0] == "md":
            data = L.book_to_markdown(book).encode("utf-8")
            req.bytes(data, "text/markdown; charset=utf-8")
        else:
            req.bytes(json.dumps(L.export_book(book), ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8")

    # ------------------------------------------------------------------ importar / exportar
    def r_import(self, req: Any, pid: str) -> None:
        name = urllib.parse.unquote(req.headers.get("X-Filename") or req.query.get("name", [""])[0] or "arquivo")
        mode = "append" if req.query.get("mode", ["replace"])[0] == "append" else "replace"
        data = req.body_bytes(MAX_IMPORT)
        if not data:
            raise HttpError(400, "Arquivo vazio.")
        res = self.m.import_file(pid, name, data, mode)
        res["project"] = self.m.meta(pid)
        req.json(res)

    def r_export(self, req: Any, pid: str) -> None:
        fmt = text(self._body(req).get("format"), "docx", 8)
        if fmt not in EXPORT_FORMATS:
            raise HttpError(400, "Formato inválido: " + ", ".join(EXPORT_FORMATS))
        req.json(self.m.export(pid, fmt))

    def r_export_get(self, req: Any, pid: str, fname: str) -> None:
        p = self.m.export_path(pid, urllib.parse.unquote(fname))
        req.file(p, MIME.get(p.suffix.lstrip(".").lower(), "application/octet-stream"), download_name=p.name, headers={"Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'"})

    # ------------------------------------------------------------------ ortografia / tipografia
    def r_proofread(self, req: Any) -> None:
        b = self._body(req, 16 * 1024 * 1024)
        ps = b.get("paragraphs")
        if not isinstance(ps, list):
            raise HttpError(400, "Envie os parágrafos em «paragraphs».")
        ignore = [x for x in (b.get("ignore") if isinstance(b.get("ignore"), list) else []) if isinstance(x, str)][:500]
        req.json(spell.proofread(ps, b.get("language"), ignore, use_dict=b.get("dictionary") is not False))

    def r_stats(self, req: Any) -> None:
        b = self._body(req, 16 * 1024 * 1024)
        ps = b.get("paragraphs")
        if not isinstance(ps, list):
            raise HttpError(400, "Envie os parágrafos em «paragraphs».")
        req.json(stats.analyze(ps, b.get("language")))

    def r_typography(self, req: Any) -> None:
        b = self._body(req, 16 * 1024 * 1024)
        ps = b.get("paragraphs")
        if not isinstance(ps, list):
            raise HttpError(400, "Envie os parágrafos em «paragraphs».")
        lang = b.get("language")
        out = [spell.typography(spell.normalize_spacing(str(x), lang), lang) for x in ps[:spell.MAX_PARAS]]
        req.json({"paragraphs": out})

    # ------------------------------------------------------------------ busca na web
    def r_search(self, req: Any) -> None:
        from . import websearch

        q = text(self._body(req).get("query"), "", 300)
        if not q:
            raise HttpError(400, "Digite o que pesquisar.")
        try:
            found = websearch.search(q, self.store.get_settings(), ui_lang=(self.store.get_settings().get("language") or "auto"))
        except websearch.SearchError as exc:
            raise HttpError(502, str(exc)) from None
        req.json({"engine": found["engine"], "query": found["query"], "results": [{"title": r["title"][:200], "url": r["url"][:600], "snippet": r["snippet"][:400], "host": (urllib.parse.urlsplit(r["url"]).hostname or "").removeprefix("www.")} for r in found["results"]]})

    def r_search_read(self, req: Any) -> None:
        from . import websearch

        url = text(self._body(req).get("url"), "", 600)
        if not websearch.safe_url(url):
            raise HttpError(400, "Só endereços públicos http(s) podem ser lidos.")
        page = websearch.fetch_page(url, 8000)
        if not page.get("text"):
            raise HttpError(502, "Não consegui ler essa página.")
        req.json({"url": url, "title": page.get("title", "")[:200], "text": page["text"][:8000]})

    # ------------------------------------------------------------------ jobs de IA
    def _job(self, kind: str, pid: str, req: Any, fn: Callable[[Job, sai.ScriberAI], Any], opts: Dict[str, Any]) -> None:
        running = self.app.jobs.running(f"sc_{kind}_{pid}")
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))

        def work(job: Job) -> Any:
            ai = sai.ScriberAI(self.store, self.m, opts, job)
            return fn(job, ai)
        job = self.app.jobs.start(f"sc_{kind}_{pid}", work)
        req.json({"job_id": job.id})

    def _opts(self, req: Any) -> Dict[str, Any]:
        b = self._body(req, 16 * 1024 * 1024)
        ids = b.get("attachment_ids") if isinstance(b.get("attachment_ids"), list) else []
        o: Dict[str, Any] = {"team": teamlib.request_team(b), "web": b.get("web") is True, "attachment_ids": [x for x in ids if isinstance(x, str)][:40], "prompt": text(b.get("prompt"), "", 24000),
                             "language": text(b.get("language"), "", 8), "content": b.get("content") if b.get("content") in ("sfw", "free") else "", "lore": b.get("lore") is not False,
                             "lore_books": [x for x in b["lore_books"] if isinstance(x, str)] if isinstance(b.get("lore_books"), list) else None, "sources_text": text(b.get("sources_text"), "", 12000)}
        for k in ("type", "mode", "style"):
            if isinstance(b.get(k), str):
                o[k] = text(b[k], "", 600)
        for k in ("pages", "words_per_page", "chapters"):
            if isinstance(b.get(k), (int, float)) and not isinstance(b.get(k), bool):
                o[k] = b[k]
        if isinstance(b.get("format"), dict):
            o["format"] = b["format"]
        o["body"] = b
        return o

    def r_generate(self, req: Any, pid: str) -> None:
        o = self._opts(req)
        if not (o["prompt"] or o["attachment_ids"]):
            raise HttpError(400, "Descreva o texto (ou cole um esboço, ou anexe algo) para gerá-lo.")
        self.m.meta(pid)
        self._job("generate", pid, req, lambda job, ai: ai.generate(pid), o)

    def r_edit(self, req: Any, pid: str) -> None:
        o = self._opts(req)
        b = o["body"]
        if not (isinstance(b.get("selection"), str) and b["selection"].strip()) and b.get("action") != "continue":
            raise HttpError(400, "Selecione um trecho do texto (ou use «Continuar»).")
        self.m.meta(pid)
        self._job("edit", pid, req, lambda job, ai: ai.edit_text(pid), o)

    def r_proofread_ai(self, req: Any, pid: str) -> None:
        o = self._opts(req)
        self.m.meta(pid)
        self._job("proofread", pid, req, lambda job, ai: ai.proofread_ai(pid), o)
