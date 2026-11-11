"""IA do modo Data: geração sintética, extração por scraping e enriquecimento/upgrade.

Produz apenas JSON validado; usa equipe/esforço (team.py/efforts.py) com fallback determinístico.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import attachments, efforts, team as teamlib, websearch
from ..providers import ProviderError, resolve_provider
from ..util import text

PROMPTS = Path(__file__).parent / "prompts"


def _prompt(name: str) -> str:
    try:
        return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _unpack(res: Any) -> Any:
    if isinstance(res, tuple) and len(res) == 2:
        return res
    return res, {"demo": getattr(res, "id", "") == "demo", "id": getattr(res, "id", ""), "model": getattr(res, "model", "")}


def provider_status(store: Any) -> Dict[str, Any]:
    settings = store.get_settings()
    try:
        provider, info = _unpack(resolve_provider(settings, "generation", store.models_dir))
        pid = info.get("id") or getattr(provider, "id", "")
        demo = bool(info.get("demo") or pid == "demo")
        return {"provider": pid, "model": info.get("model") or getattr(provider, "model", ""), "ai": not demo}
    except Exception:
        return {"provider": "demo", "model": "", "ai": False}


class DataAI:
    def __init__(self, store: Any, manager: Any, opts: Dict[str, Any], job: Any):
        self.store = store
        self.manager = manager
        self.opts = opts or {}
        self.job = job
        self.settings = store.get_settings()
        self.cfg = self.settings.get("data") or {}
        self.team = teamlib.from_config(self.cfg, self.opts)
        self.provider: Any = None
        self.pid = "demo"
        self.model = ""
        try:
            provider, info = _unpack(resolve_provider(self.settings, "generation", store.models_dir))
            self.pid = info.get("id") or getattr(provider, "id", "demo")
            self.model = info.get("model") or getattr(provider, "model", "")
            if not (info.get("demo") or self.pid == "demo"):
                self.provider = provider
                try:
                    teamlib.apply_thinking(provider, self.team, self.pid, self.model)
                except Exception:
                    pass
        except Exception:
            self.provider = None
            self.pid = "demo"
            self.model = ""

    def emit(self, event: Dict[str, Any]) -> None:
        try:
            self.job.emit(event)
        except Exception:
            pass

    def cancelled(self) -> bool:
        try:
            return bool(self.job.cancelled)
        except Exception:
            return False

    def _ask_json(self, instruction: str, payload: Dict[str, Any], creative: bool = True) -> Optional[Dict[str, Any]]:
        if not self.provider or self.pid == "demo":
            return None
        sys = (_prompt("core") or "You output only valid JSON.") + "\n" + efforts.guidance(self.team.effort)
        def ask(ins: str, pl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            msg = ins + "\nINPUT_JSON:\n" + json.dumps(pl, ensure_ascii=False)
            try:
                raw = self.provider.generate(msg, system=sys, json_mode=True)
                if isinstance(raw, dict):
                    return raw
                return json.loads(str(raw))
            except Exception:
                return None
        if creative and self.team.multi:
            try:
                return teamlib.ensemble_json(ask, self.team, instruction, payload, cancelled=self.cancelled)
            except Exception:
                return ask(instruction, payload)
        return ask(instruction, payload)

    # -------------------------------------------------------------- synthetic
    def generate_synthetic(self, kind: str, item_id: str) -> Dict[str, Any]:
        prompt = text(self.opts.get("prompt"), "", 12000)
        count = max(1, min(int(self.opts.get("count") or 20), 500))
        mode = "multi" if self.opts.get("mode") == "multi" else "single"
        target = self.manager.get(kind, item_id)
        schema = target.get("schema") or {"fields": []}
        atts = self._attachments()
        payload = {"prompt": prompt, "count": count, "mode": mode, "schema": schema, "existing_sample": (target.get("records") or [])[:5], "attachments": atts["text"][:12000]}
        self.emit({"type": "stage", "stage": "synthetic", "message": "Gerando dados sintéticos com IA..."})
        obj = self._ask_json(
            "Generate synthetic records for a database/dataset. Return JSON {\"schema\": {\"fields\":[...]}, \"records\": [ {...}, ... ]}. "
            "Respect the requested schema when possible; if mode is 'multi' you may add coherent fields/types for multiple modalities. "
            f"Generate exactly up to {count} records. Use the same language as the prompt. No real personal data.",
            payload, creative=True,
        )
        records: List[Any] = []
        new_schema = schema
        if isinstance(obj, dict):
            if isinstance(obj.get("records"), list):
                records = obj["records"]
            if isinstance(obj.get("schema"), dict):
                from .schema import clean_schema
                new_schema = clean_schema(obj["schema"])
        if not records:
            records = self._fallback_synthetic(prompt, schema, count, mode)
        self.manager.append_records(kind, item_id, records, "synthetic")
        if new_schema != schema:
            cur = self.manager.get(kind, item_id)
            self.manager.save_records(kind, item_id, cur.get("records") or [], new_schema, "synthetic_schema")
        out = self.manager.get(kind, item_id)
        self.emit({"type": "done", "generated": len(records), "records": len(out.get("records") or [])})
        return {"generated": len(records), "item": out["meta"]}

    def _fallback_synthetic(self, prompt: str, schema: Dict[str, Any], count: int, mode: str) -> List[Dict[str, Any]]:
        fields = [f.get("name") for f in (schema.get("fields") or []) if isinstance(f, dict) and f.get("name")] or ["id", "content"]
        base = prompt.strip()[:120] or "sample"
        out = []
        for i in range(count):
            row: Dict[str, Any] = {}
            for j, f in enumerate(fields):
                if f.lower() in ("id", "uid", "key"):
                    row[f] = f"{i+1}"
                elif mode == "multi" and j == 1:
                    row[f] = f"{base} — variante {i+1}"
                else:
                    row[f] = f"{base} {i+1}" if j <= 1 else ""
            if mode == "multi":
                row.setdefault("type", "text")
                row.setdefault("tags", [base[:30]]) if base else None
            out.append(row)
        return out

    # -------------------------------------------------------------- scraping
    def scrape(self, kind: str, item_id: str) -> Dict[str, Any]:
        prompt = text(self.opts.get("prompt"), "", 8000)
        urls = self.opts.get("urls") if isinstance(self.opts.get("urls"), list) else []
        urls = [str(u).strip() for u in urls if str(u).strip()][:50]
        if not urls:
            raise ValueError("Forneça ao menos um link/URL para fazer scraping.")
        pages: List[Dict[str, Any]] = []
        for url in urls:
            if self.cancelled():
                break
            safe = websearch.safe_url(url)
            if not safe:
                pages.append({"url": url, "error": "URL não permitida (apenas http/https públicos)."})
                continue
            self.emit({"type": "stage", "stage": "scrape", "message": f"Lendo: {url}"})
            page = websearch.fetch_page(url, 12000)
            pages.append({"url": url, "title": page.get("title", ""), "text": (page.get("text") or "")[:12000], "error": page.get("error", "")})
        target = self.manager.get(kind, item_id)
        schema = target.get("schema") or {"fields": []}
        self.emit({"type": "stage", "stage": "extract", "message": "Extraindo dados estruturados com IA..."})
        obj = self._ask_json(
            "Extract structured records from scraped pages according to the prompt and schema. "
            "Return JSON {\"schema\": {\"fields\":[...]}, \"records\":[...]}. Only use information present in the pages; do not invent facts.",
            {"prompt": prompt, "urls": urls, "pages": pages, "schema": schema}, creative=False,
        )
        records = obj.get("records") if isinstance(obj, dict) and isinstance(obj.get("records"), list) else []
        new_schema = obj.get("schema") if isinstance(obj, dict) and isinstance(obj.get("schema"), dict) else schema
        if not records:
            for p in pages:
                if p.get("text"):
                    records.append({"url": p.get("url"), "title": p.get("title", ""), "content": p.get("text", "")[:4000]})
        from .schema import clean_schema
        self.manager.append_records(kind, item_id, records, "scrape")
        cur = self.manager.get(kind, item_id)
        if clean_schema(new_schema) != cur.get("schema"):
            self.manager.save_records(kind, item_id, cur.get("records") or [], clean_schema(new_schema), "scrape_schema")
        out = self.manager.get(kind, item_id)
        self.emit({"type": "done", "generated": len(records), "records": len(out.get("records") or [])})
        return {"generated": len(records), "pages": len(pages), "item": out["meta"]}

    # -------------------------------------------------------------- upgrade/enrich
    def upgrade(self, kind: str, item_id: str) -> Dict[str, Any]:
        prompt = text(self.opts.get("prompt"), "", 12000)
        count = max(0, min(int(self.opts.get("count") or 0), 500))
        mode = "multi" if self.opts.get("mode") == "multi" else "single"
        action = text(self.opts.get("action"), "enrich", 20)  # enrich | generate
        target = self.manager.get(kind, item_id)
        schema = target.get("schema") or {"fields": []}
        recs = target.get("records") or []
        atts = self._attachments()
        self.emit({"type": "stage", "stage": "upgrade", "message": "Melhorando/enriquecendo com IA..."})
        if action == "generate" and count > 0:
            return self.generate_synthetic(kind, item_id)
        sample = recs[:20]
        obj = self._ask_json(
            "Improve and enrich an existing dataset/database. Return JSON {\"schema\": {\"fields\":[...]}, \"records\":[...]} "
            "where records are improved/enriched versions (keep ids when present) and may include additional coherent fields. "
            "If mode is 'multi', you may generate multiple data types/modalities consistently. Preserve existing meaning; do not invent sensitive personal data.",
            {"prompt": prompt, "mode": mode, "schema": schema, "records": sample, "total_records": len(recs), "attachments": atts["text"][:8000]}, creative=True,
        )
        if isinstance(obj, dict) and isinstance(obj.get("records"), list) and obj["records"]:
            from .schema import clean_schema
            new_schema = clean_schema(obj.get("schema") if isinstance(obj.get("schema"), dict) else schema)
            # merge improved sample back: replace first N with improved, keep rest
            improved = obj["records"]
            merged = list(improved) + recs[len(improved):]
            self.manager.save_records(kind, item_id, merged, new_schema, "upgrade")
        else:
            # deterministic enrich: add a note field if prompt provided
            if prompt:
                for r in recs[:200]:
                    if isinstance(r, dict):
                        r.setdefault("_upgrade_note", prompt[:200])
                self.manager.save_records(kind, item_id, recs, schema, "upgrade")
        out = self.manager.get(kind, item_id)
        self.emit({"type": "done", "records": len(out.get("records") or [])})
        return {"records": len(out.get("records") or []), "item": out["meta"]}

    def _attachments(self) -> Dict[str, Any]:
        ids = self.opts.get("attachment_ids") if isinstance(self.opts.get("attachment_ids"), list) else []
        if not ids:
            return {"text": "", "images": []}
        try:
            metas = self.store.get_uploads(ids)
            return attachments.read_many(metas)
        except Exception:
            return {"text": "", "images": []}
