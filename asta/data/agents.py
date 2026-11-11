"""IA do modo Data: geração sintética em massa, extração por scraping e enriquecimento/upgrade.

Produz apenas JSON validado; usa a equipe/esforço (`team.py`/`efforts.py`) e o mesmo
`call_json` das outras seções (`agents/llm.py`), com fallback determinístico quando não
há IA (ou quando a IA devolve lixo).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import attachments as att
from .. import efforts, team as teamlib
from ..agents.llm import call_json
from ..providers import resolve_provider
from ..util import text
from . import scrape as scrapelib
from .schema import (MAX_SCRAPE_URLS, MAX_SYNTH_COUNT, SCRAPE_BATCH, SYNTH_BATCH, clean_schema)

PROMPTS = Path(__file__).parent / "prompts"

#: tokens por chamada de IA (o teto real vem do provedor)
TOKENS = 4096


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
        self.error = ""
        self.log: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        try:
            provider, info = _unpack(resolve_provider(self.settings, "generation", store.models_dir))
            self.pid = info.get("id") or getattr(provider, "id", "demo")
            self.model = info.get("model") or getattr(provider, "model", "")
            if info.get("demo") or self.pid == "demo":
                self.error = info.get("reason") or "Nenhuma IA configurada: usei o gerador determinístico."
            else:
                self.provider = provider
                try:
                    teamlib.apply_thinking(provider, self.team, self.pid, self.model)
                except Exception:
                    pass
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)[:200]
            self.provider = None
            self.pid = "demo"

    # ------------------------------------------------------------------ infra
    @property
    def live(self) -> bool:
        return self.provider is not None

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

    def _system(self) -> str:
        return (_prompt("core") or "You output only valid JSON.") + "\n" + efforts.guidance(self.team.effort)

    def _ask_json(self, instruction: str, payload: Dict[str, Any], creative: bool = True,
                  images: Optional[List[dict]] = None, tokens: int = TOKENS) -> Optional[Dict[str, Any]]:
        """Chama a IA (ou a mesa de agentes) pedindo JSON. None = a IA não respondeu."""
        if not self.live:
            return None
        sys = self._system()

        def ask(ins: str, pl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            try:
                obj, _raw = call_json(self.provider, sys, ins, pl, images=images,
                                      temperature=0.6, max_tokens=int(tokens * max(1, self.team.tokens_mult)),
                                      attempts=2, cancelled=self.cancelled)
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None

        if creative and self.team.multi:
            try:
                return teamlib.ensemble_json(ask, self.team, instruction, payload, cancelled=self.cancelled)
            except Exception:
                return ask(instruction, payload)
        return ask(instruction, payload)

    def _step(self, label: str, fn: Callable[[], Any]) -> Any:
        """Roda um passo (uma chamada ou uma mesa de agentes) e registra na lista de agentes."""
        started = time.time()
        status, note = "ok", ""
        try:
            out = fn()
        except Exception as exc:  # noqa: BLE001
            out, status, note = None, "erro", str(exc)[:160]
        if out is None:
            status = "fallback"
            note = note or "a IA não respondeu; usei o gerador determinístico."
        self.log.append({"step": label, "agents": self.team.agents, "status": status,
                         "note": note, "ms": int((time.time() - started) * 1000)})
        self.emit({"type": "step", "label": label, "status": status, "note": note,
                   "agents": self.team.agents, "ms": int((time.time() - started) * 1000)})
        return out

    def report(self) -> Dict[str, Any]:
        """O que os agentes fizeram (para a interface e para o histórico do trabalho)."""
        return {"ai": self.live, "agents": self.log, "team": self.team.public(),
                "warning": "" if self.live else (self.error or "Sem IA: usei o gerador determinístico."),
                "warnings": self.warnings}

    def _attachments(self) -> Dict[str, Any]:
        """Os anexos do pedido: texto (digest) e imagens (multimodal)."""
        ids = self.opts.get("attachment_ids") if isinstance(self.opts.get("attachment_ids"), list) else []
        ids = [x for x in ids if isinstance(x, str)][:20]
        if not ids:
            return {"text": "", "images": []}
        analyzed: List[Dict[str, Any]] = []
        try:
            metas = self.store.get_uploads(ids, limit=20)
        except Exception:
            return {"text": "", "images": []}
        for meta in metas:
            try:
                analyzed.append(att.analyze(Path(meta["path"]), meta["name"], meta.get("mime", "")))
            except Exception as exc:  # noqa: BLE001  (um anexo ilegível não derruba o pedido)
                self.warnings.append(f"anexo «{meta.get('name', '?')}»: {str(exc)[:100]}")
        return {"text": att.build_digest(analyzed, max_total=24000), "images": att.collect_images(analyzed, 4)}

    # ================================================================ sintéticos
    def generate_synthetic(self, kind: str, item_id: str) -> Dict[str, Any]:
        prompt = text(self.opts.get("prompt"), "", 20000)
        count = max(1, min(int(self.opts.get("count") or 20), MAX_SYNTH_COUNT))
        mode = "multi" if self.opts.get("mode") == "multi" else "single"
        target = self.manager.get(kind, item_id)
        schema = target.get("schema") or {"fields": []}
        existing = target.get("records") or []
        atts = self._attachments()
        self.emit({"type": "stage", "stage": "synthetic", "message": "Gerando dados sintéticos com IA..."})

        records: List[Any] = []
        new_schema = schema
        done = 0
        batch = max(1, SYNTH_BATCH)
        while done < count:
            if self.cancelled():
                break
            want = min(batch, count - done)
            payload = {
                "prompt": prompt,
                "count": want,
                "mode": mode,
                "schema": schema,
                "existing_sample": existing[:5],
                "generated_so_far": len(records),
                "already_generated_sample": records[-3:],
                "attachments": atts["text"][:12000],
            }
            obj = self._step(f"lote {done // batch + 1}", lambda: self._ask_json(
                "Generate synthetic records for a database/dataset. "
                "Respect the requested schema when possible; if mode is 'multi' you may add coherent fields/types for multiple modalities. "
                f"Generate exactly {want} records that are DIFFERENT from the ones already generated (keep them varied and unique). "
                "Use the same language as the prompt. No real personal data. "
                'Output JSON: {"schema": {"fields": [{"name": str, "type": str}]}, "records": [{...}]}',
                payload, creative=True, images=atts["images"],
            ))
            got: List[Any] = []
            if isinstance(obj, dict):
                if isinstance(obj.get("records"), list):
                    got = [r for r in obj["records"] if isinstance(r, (dict, list))][:want]
                if isinstance(obj.get("schema"), dict):
                    new_schema = clean_schema(obj["schema"])
            if not got:
                # a IA falhou neste lote: preenche com o gerador determinístico e segue
                got = self._fallback_synthetic(prompt, new_schema, want, mode, len(records))
                self.warnings.append(f"lote {done // batch + 1}: a IA não respondeu; usei o gerador determinístico.")
            records.extend(got)
            done += len(got)
            self.emit({"type": "progress", "stage": "synthetic", "done": done, "total": count,
                       "message": f"{done}/{count} registros gerados"})
        if not records:
            records = self._fallback_synthetic(prompt, schema, count, mode, 0)
            done = len(records)

        self.manager.append_records(kind, item_id, records, "synthetic")
        cur = self.manager.get(kind, item_id)
        if clean_schema(new_schema) != cur.get("schema"):
            self.manager.save_records(kind, item_id, cur.get("records") or [], new_schema, "synthetic_schema")
        out = self.manager.get(kind, item_id)
        self.emit({"type": "done", "generated": len(records), "records": len(out.get("records") or []),
                   "warnings": self.warnings})
        return {"generated": len(records), "records": len(out.get("records") or []), "item": out["meta"],
                "ai": self.live, "warnings": self.warnings, "report": self.report()}

    def _fallback_synthetic(self, prompt: str, schema: Dict[str, Any], count: int, mode: str, offset: int = 0) -> List[Dict[str, Any]]:
        """Gerador determinístico (sem IA): registros coerentes com o schema e com o pedido."""
        fields = [f for f in (schema.get("fields") or []) if isinstance(f, dict) and f.get("name")]
        if not fields:
            fields = [{"name": "id", "type": "text"}, {"name": "content", "type": "text"}]
        base = prompt.strip()[:120] or "sample"
        out: List[Dict[str, Any]] = []
        for i in range(offset, offset + count):
            row: Dict[str, Any] = {}
            for j, f in enumerate(fields):
                name = f.get("name")
                ftype = f.get("type") or "text"
                if name.lower() in ("id", "uid", "key"):
                    row[name] = str(i + 1)
                elif ftype in ("number", "integer"):
                    row[name] = i + 1 if ftype == "integer" else round(1.5 + (i % 50) * 0.75, 2)
                elif ftype == "boolean":
                    row[name] = bool(i % 2)
                elif ftype == "url":
                    row[name] = f"https://example.org/{base_slug(base)}/{i + 1}"
                elif ftype == "category":
                    row[name] = ["alpha", "beta", "gama", "delta"][i % 4]
                elif ftype == "date":
                    row[name] = f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}"
                elif ftype == "json":
                    row[name] = {"base": base[:40], "n": i + 1}
                elif ftype in ("image", "audio", "video", "file"):
                    row[name] = f"{base_slug(base)}-{i + 1}.{'png' if ftype == 'image' else 'bin'}"
                else:
                    row[name] = f"{base} {i + 1}" if j <= 1 else ""
            if mode == "multi" and not any(k in row for k in ("type", "modalidade")):
                row["type"] = "text"
                row["tags"] = [base[:30]] if base else []
            out.append(row)
        return out

    # ================================================================ scraping
    def scrape(self, kind: str, item_id: str) -> Dict[str, Any]:
        prompt = text(self.opts.get("prompt"), "", 12000)
        urls = self.opts.get("urls") if isinstance(self.opts.get("urls"), list) else []
        urls = [str(u).strip() for u in urls if str(u).strip()][:MAX_SCRAPE_URLS]
        if not urls:
            raise ValueError("Forneça ao menos um link/URL para fazer scraping.")
        target = self.manager.get(kind, item_id)
        schema = target.get("schema") or {"fields": []}
        atts = self._attachments()

        self.emit({"type": "stage", "stage": "scrape", "message": f"Lendo {len(urls)} link(s)..."})
        pages = scrapelib.fetch_many(urls, on_page=lambda i, total, page: self.emit(
            {"type": "progress", "stage": "scrape", "done": i, "total": total,
             "message": f"{i}/{total}: {page.get('url', '')}"}))
        skipped = [p for p in pages if p.get("skipped") or p.get("error")]
        good = [p for p in pages if p.get("text")]

        records: List[Any] = []
        new_schema = schema
        batch = max(1, SCRAPE_BATCH)
        for start in range(0, len(good), batch):
            if self.cancelled():
                break
            chunk = good[start:start + batch]
            self.emit({"type": "stage", "stage": "extract", "message": f"Extraindo dados estruturados ({start + 1}-{start + len(chunk)})..."})
            obj = self._step(f"extrair {start + 1}-{start + len(chunk)}", lambda: self._ask_json(
                "Extract structured records from scraped pages according to the prompt and schema. "
                "Only use information present in the pages; do not invent facts. "
                'Output JSON: {"schema": {"fields": [{"name": str, "type": str}]}, "records": [{...}]}',
                {"prompt": prompt, "pages": chunk, "schema": schema, "attachments": atts["text"][:6000]},
                creative=False, images=atts["images"],
            ))
            if isinstance(obj, dict):
                if isinstance(obj.get("records"), list):
                    records.extend([r for r in obj["records"] if isinstance(r, (dict, list))])
                if isinstance(obj.get("schema"), dict):
                    new_schema = clean_schema(obj["schema"])
            if not isinstance(obj, dict) or not (obj.get("records") or []):
                # a IA falhou neste lote: guarda o texto cru das páginas (nada é inventado)
                for p in chunk:
                    records.append({"url": p.get("url"), "title": p.get("title", ""), "content": p.get("text", "")[:4000]})
        if not records:
            for p in good:
                records.append({"url": p.get("url"), "title": p.get("title", ""), "content": p.get("text", "")[:4000]})
        self.manager.append_records(kind, item_id, records, "scrape")
        cur = self.manager.get(kind, item_id)
        if clean_schema(new_schema) != cur.get("schema"):
            self.manager.save_records(kind, item_id, cur.get("records") or [], clean_schema(new_schema), "scrape_schema")
        out = self.manager.get(kind, item_id)
        self.emit({"type": "done", "generated": len(records), "records": len(out.get("records") or []),
                   "pages": len(good), "skipped": len(skipped), "warnings": self.warnings})
        return {"generated": len(records), "pages": len(good), "skipped": len(skipped),
                "records": len(out.get("records") or []), "item": out["meta"], "ai": self.live,
                "report": self.report()}

    # ================================================================ upgrade
    def upgrade(self, kind: str, item_id: str) -> Dict[str, Any]:
        prompt = text(self.opts.get("prompt"), "", 20000)
        count = max(0, min(int(self.opts.get("count") or 0), MAX_SYNTH_COUNT))
        mode = "multi" if self.opts.get("mode") == "multi" else "single"
        action = text(self.opts.get("action"), "enrich", 20)  # enrich | generate
        target = self.manager.get(kind, item_id)
        schema = target.get("schema") or {"fields": []}
        recs = target.get("records") or []
        atts = self._attachments()
        self.emit({"type": "stage", "stage": "upgrade", "message": "Melhorando/enriquecendo com IA..."})
        if action == "generate" and count > 0:
            return self.generate_synthetic(kind, item_id)
        sample = recs[:40]
        obj = self._step("melhorar", lambda: self._ask_json(
            "Improve and enrich an existing dataset/database. The records are improved/enriched versions (keep ids when present) and may include additional coherent fields. "
            "If mode is 'multi', you may generate multiple data types/modalities consistently. Preserve existing meaning; do not invent sensitive personal data. "
            'Output JSON: {"schema": {"fields": [{"name": str, "type": str}]}, "records": [{...}]}',
            {"prompt": prompt, "mode": mode, "schema": schema, "records": sample,
             "total_records": len(recs), "attachments": atts["text"][:8000]},
            creative=True, images=atts["images"],
        ))
        if isinstance(obj, dict) and isinstance(obj.get("records"), list) and obj["records"]:
            new_schema = clean_schema(obj.get("schema") if isinstance(obj.get("schema"), dict) else schema)
            improved = obj["records"]
            merged = list(improved) + recs[len(improved):]
            self.manager.save_records(kind, item_id, merged, new_schema, "upgrade")
        elif prompt:
            # sem IA: enrich determinístico — marca os registros e guarda a instrução
            for r in recs[:200]:
                if isinstance(r, dict):
                    r.setdefault("_upgrade_note", prompt[:200])
            self.manager.save_records(kind, item_id, recs, schema, "upgrade")
        out = self.manager.get(kind, item_id)
        self.emit({"type": "done", "records": len(out.get("records") or []), "warnings": self.warnings})
        return {"records": len(out.get("records") or []), "item": out["meta"], "ai": self.live,
                "report": self.report()}


def base_slug(text_value: str) -> str:
    """Um pedaço de texto virando um pedaço de URL/nome de arquivo."""
    out = "".join(c if c.isalnum() else "-" for c in (text_value or "").lower())
    return "-".join(p for p in out.split("-") if p)[:40] or "item"
