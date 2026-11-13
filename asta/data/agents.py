"""IA do modo Data (v0.24): geração sintética em massa, extração por scraping de qualquer tipo de link e melhoria (upgrade) de bases existentes.

Cada tarefa é **planejar → fazer → conferir**: um Planejador define a estrutura, os lotes geram/extraem/transformam, e a conferência valida (tipos, ids, duplicados, contagens) e
completa com o método determinístico o que a IA não entregou — dizendo isso nos avisos. A IA só produz JSON que o ASTA valida (nunca código) e **nunca apaga dado**: o que ela
devolve de inválido é descartado e o registro original fica. Usa a equipe/esforço (`team.py`/`efforts.py`) e o mesmo `call_json` das outras seções (`agents/llm.py`).
"""

from __future__ import annotations

import time
from pathlib import Path
import json
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import attachments as att
from .. import efforts, team as teamlib
from ..agents.llm import call_json
from ..providers import resolve_provider
from ..util import text
from . import links, ops, quality
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

    def _system(self, role: str = "") -> str:
        """Prompt de sistema: regras comuns (`core.md`) + o papel do agente (`<role>.md`, com o marcador `ROLE:`) + o esforço."""
        base = _prompt("core") or "You output only valid JSON."
        part = _prompt(role) if role else ""
        return base + ("\n\n" + part if part else "") + "\n\n" + efforts.guidance(self.team.effort)

    def _ask_json(self, instruction: str, payload: Dict[str, Any], creative: bool = True,
                  images: Optional[List[dict]] = None, tokens: int = TOKENS, role: str = "") -> Optional[Dict[str, Any]]:
        """Chama a IA (ou a mesa de agentes) pedindo JSON. None = a IA não respondeu."""
        if not self.live:
            return None
        sys = self._system(role)

        def ask(ins: str, pl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            try:
                obj, _raw = call_json(self.provider, sys, ins, pl, images=images,
                                      temperature=0.6, max_tokens=int(tokens * max(1, self.team.tokens_mult)),
                                      attempts=2, cancelled=self.cancelled)
                return obj if isinstance(obj, dict) else None
            except Exception as exc:  # noqa: BLE001  (segue com o gerador determinístico, mas o motivo real — chave inválida, rede, limite — aparece nos avisos)
                if not self.cancelled():
                    why = str(exc)[:160] or exc.__class__.__name__
                    msg = f"a IA falhou: {why}"
                    if msg not in self.warnings:
                        self.warnings.append(msg)
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

    # ================================================================ utilidades de validação (plano → fazer → conferir)
    @staticmethod
    def _is_default_schema(schema: Dict[str, Any]) -> bool:
        names = [f.get("name") for f in (schema.get("fields") or []) if isinstance(f, dict)]
        return not names or names == ["id", "content"]

    def _plan_schema(self, kind: str, item_id: str, prompt: str, mode: str, schema: Dict[str, Any], atts: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Passo 1 (planejar): o Planejador define os campos e os eixos de variedade. Sem IA ou resposta inválida, vale o schema que o item já tem."""
        plan: Dict[str, Any] = {"style_notes": "", "diversity_axes": []}
        if not self.live or not (self._is_default_schema(schema) or mode == "multi" or atts["text"]):
            return schema, plan
        obj = self._step("planejar", lambda: self._ask_json(
            "Design the structure for the requested synthetic data. Keep the fields of the current schema (same names and types) and add what the prompt needs.",
            {"prompt": prompt, "mode": mode, "schema": schema, "attachments": atts["text"][:8000]}, creative=True, images=atts["images"], role="planner"))
        if isinstance(obj, dict):
            if isinstance(obj.get("schema"), dict) and (obj["schema"].get("fields") or []):
                schema = ops._union_schema(schema if not self._is_default_schema(schema) else {"fields": []}, clean_schema(obj["schema"]))
            plan["style_notes"] = text(obj.get("style_notes"), "", 400)
            plan["diversity_axes"] = [text(x, "", 80) for x in (obj.get("diversity_axes") if isinstance(obj.get("diversity_axes"), list) else [])][:8]
        return schema, plan

    @staticmethod
    def _shape_rows(rows: Any, schema: Dict[str, Any], mode: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Valida o que a IA devolveu: só objetos (listas viram objetos pela ordem dos campos); campos fora do schema só no modo «multi»; tipos convertidos; obrigatórios presentes."""
        names = [f["name"] for f in schema.get("fields") or [] if isinstance(f, dict) and f.get("name")]
        required = {f["name"] for f in schema.get("fields") or [] if isinstance(f, dict) and f.get("required")}
        out: List[Dict[str, Any]] = []
        st = {"dropped": 0, "extra_fields": 0, "invalid": 0}
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, list):
                r = {names[i]: v for i, v in enumerate(r[:len(names)])}
            if not isinstance(r, dict) or not r:
                st["invalid"] += 1
                continue
            row = {str(k)[:80]: v for k, v in r.items()}
            if mode != "multi" and names:
                extra = [k for k in row if k not in names and k != "_i"]
                if extra:
                    st["extra_fields"] += len(extra)
                    row = {k: v for k, v in row.items() if k in names}
            if any(quality._is_blank(row.get(k)) for k in required):
                st["dropped"] += 1
                continue
            out.append(row)
        out, cst = ops.coerce_records(out, schema)
        st["converted"] = cst["changed"]
        st["unconvertible"] = cst["failed"]
        return out, st

    @staticmethod
    def _unique_ids(rows: List[Dict[str, Any]], existing: List[Any], schema: Dict[str, Any]) -> int:
        """Se o schema tem `id`, nenhum id repete (nem entre lotes, nem com o que o item já tinha). Devolve quantos foram renumerados."""
        idf = next((f["name"] for f in schema.get("fields") or [] if isinstance(f, dict) and str(f.get("name", "")).lower() in quality.ID_FIELDS), "")
        if not idf:
            return 0
        used = {str(r.get(idf)) for r in existing if isinstance(r, dict) and not quality._is_blank(r.get(idf))}
        itype = next((f.get("type") for f in schema["fields"] if f.get("name") == idf), "text")
        n = len(used)
        fixed = 0
        for r in rows:
            v = r.get(idf)
            if quality._is_blank(v) or str(v) in used:
                n += 1
                while str(n) in used:
                    n += 1
                r[idf] = n if itype == "integer" else str(n)
                fixed += 1
            used.add(str(r[idf]))
        return fixed

    # ================================================================ sintéticos
    def generate_synthetic(self, kind: str, item_id: str) -> Dict[str, Any]:
        prompt = text(self.opts.get("prompt"), "", 20000)
        try:
            count = max(1, min(int(self.opts.get("count") or 20), MAX_SYNTH_COUNT))
        except (TypeError, ValueError):
            count = 20
        mode = "multi" if self.opts.get("mode") == "multi" else "single"
        target = self.manager.get(kind, item_id)
        schema = target.get("schema") or {"fields": []}
        existing = target.get("records") or []
        atts = self._attachments()
        self.emit({"type": "stage", "stage": "synthetic", "message": "Planejando a estrutura dos dados..."})
        schema, plan = self._plan_schema(kind, item_id, prompt, mode, schema, atts)
        keys = quality.resolve_keys([], schema, None)
        seen = {quality._dump([quality._norm(r.get(k), True) for k in keys]) for r in existing if isinstance(r, dict)}

        def fresh(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            out = []
            for r in rows:
                sig = quality._dump([quality._norm(r.get(k), True) for k in keys])
                if sig in seen:
                    continue
                seen.add(sig)
                out.append(r)
            return out

        records: List[Dict[str, Any]] = []
        stats = {"dropped": 0, "extra_fields": 0, "invalid": 0, "converted": 0, "unconvertible": 0, "duplicates": 0}
        batch = max(1, SYNTH_BATCH)
        rounds = (count + batch - 1) // batch + 3          # lotes previstos + até 3 repescagens: a conta fecha, mas o laço nunca é infinito
        r = 0
        self.emit({"type": "stage", "stage": "synthetic", "message": "Gerando dados sintéticos com IA..."})
        while len(records) < count and r < rounds and self.live:
            if self.cancelled():
                self.warnings.append("cancelado: guardei o que já estava pronto.")
                break
            r += 1
            want = min(batch, count - len(records))
            payload = {"prompt": prompt, "count": want, "mode": mode, "schema": schema, "style_notes": plan["style_notes"], "diversity_axes": plan["diversity_axes"],
                       "batch": r, "existing_sample": existing[:3], "already_generated_sample": records[-5:],
                       "avoid_values": [str(x.get(keys[0]))[:40] for x in records[-30:] if keys and keys[0] in x] if keys else [], "attachments": atts["text"][:10000]}
            obj = self._step(f"lote {r}", lambda: self._ask_json(
                f"Generate exactly {want} synthetic records that follow the schema. Make them different from each other and from the samples. No real personal data. Same language as the prompt.",
                payload, creative=True, images=atts["images"], role="generator"))
            got: List[Dict[str, Any]] = []
            if isinstance(obj, dict):
                if mode == "multi" and isinstance(obj.get("schema"), dict) and (obj["schema"].get("fields") or []):
                    schema = ops._union_schema(schema, clean_schema(obj["schema"]))   # campos novos entram; os que já existiam não mudam entre lotes
                    keys = quality.resolve_keys([], schema, None)
                rows, st = self._shape_rows(obj.get("records"), schema, mode)
                for k in ("dropped", "extra_fields", "invalid", "converted", "unconvertible"):
                    stats[k] += st[k]
                got = fresh(rows)
                stats["duplicates"] += len(rows) - len(got)
            if not got:
                self.warnings.append(f"lote {r}: a IA não devolveu registros novos e válidos.")
            records.extend(got[:count - len(records)])
            self.emit({"type": "progress", "stage": "synthetic", "done": len(records), "total": count, "message": f"{len(records)}/{count} registros gerados"})
        ai_count = len(records)
        if len(records) < count and not self.cancelled():
            # passo 3 (conferir): o que a IA não entregou é completado pelo gerador determinístico, e isso fica dito
            if self.live:
                self.warnings.append(f"a IA entregou {ai_count} de {count}; completei {count - ai_count} com o gerador determinístico.")
            filler = self._fallback_synthetic(prompt, schema, count - len(records), mode, len(existing) + len(records))
            records.extend(fresh(filler) or filler)
        fixed = self._unique_ids(records, existing, schema)
        if mode == "multi":
            schema = ops.infer_schema(records, schema)
        if stats["duplicates"]:
            self.warnings.append(f"{stats['duplicates']} registro(s) repetido(s) da IA foram descartados.")
        if fixed:
            self.warnings.append(f"{fixed} id(s) repetido(s) foram renumerados.")
        if stats["extra_fields"]:
            self.warnings.append(f"{stats['extra_fields']} valor(es) de campos fora do schema foram ignorados (modo «um tipo»).")
        if stats["unconvertible"]:
            self.warnings.append(f"{stats['unconvertible']} valor(es) não puderam ser convertidos ao tipo do campo e foram mantidos como vieram.")
        cur_schema = self.manager.get(kind, item_id).get("schema") or {"fields": []}
        final_schema = clean_schema(ops._union_schema(cur_schema if not self._is_default_schema(cur_schema) else {"fields": []}, schema)) if records else cur_schema
        self.manager.save_records(kind, item_id, (self.manager.get(kind, item_id).get("records") or []) + records, final_schema, "synthetic")
        out = self.manager.get(kind, item_id)
        checks = {"requested": count, "generated": len(records), "from_ai": ai_count if self.live else 0, "schema_fields": len(final_schema["fields"]), **{k: v for k, v in stats.items() if v}}
        self.emit({"type": "done", "generated": len(records), "records": len(out.get("records") or []), "warnings": self.warnings, "checks": checks})
        return {"generated": len(records), "records": len(out.get("records") or []), "item": out["meta"], "ai": self.live, "warnings": self.warnings, "checks": checks, "report": self.report()}

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
                    row[name] = f"{base_slug(base)}-{i + 1}.{ {'image': 'png', 'audio': 'wav', 'video': 'mp4'}.get(ftype, 'bin') }"
                else:
                    row[name] = f"{base} {i + 1}" if j <= 1 else ""
            if mode == "multi" and not any(k in row for k in ("type", "modalidade")):
                row["type"] = "text"
                row["tags"] = [base[:30]] if base else []
            out.append(row)
        return out

    # ================================================================ scraping (qualquer tipo de link)
    def scrape(self, kind: str, item_id: str) -> Dict[str, Any]:
        prompt = text(self.opts.get("prompt"), "", 12000)
        urls = self.opts.get("urls") if isinstance(self.opts.get("urls"), list) else []
        urls = list(dict.fromkeys(str(u).strip() for u in urls if str(u).strip()))[:MAX_SCRAPE_URLS]
        if not urls:
            raise ValueError("Forneça ao menos um link/URL para fazer scraping.")
        target = self.manager.get(kind, item_id)
        schema = target.get("schema") or {"fields": []}
        atts = self._attachments()
        download = bool(self.opts.get("download_media"))

        self.emit({"type": "stage", "stage": "scrape", "message": f"Lendo {len(urls)} link(s)..."})
        pages = scrapelib.fetch_many(urls, on_page=lambda i, total, page: self.emit(
            {"type": "progress", "stage": "scrape", "done": i, "total": total, "message": f"{i}/{total}: {page.get('url', '')}"}),
            download_dir=self.manager._media_dir(kind, item_id) if download else None)
        skipped = [p for p in pages if p.get("skipped")]
        failed = [p for p in pages if p.get("error") and not p.get("skipped") and not p.get("text") and not p.get("rows") and not p.get("kind")]
        for p in pages:
            if p.get("skipped"):
                self.warnings.append(f"{p.get('url', '')}: o robots.txt do site não permite.")
            elif p.get("error") and not p.get("text") and not p.get("rows"):
                self.warnings.append(f"{p.get('url', '')}: {str(p.get('error'))[:120]}")

        def kind_of(p: Dict[str, Any]) -> str:
            return p.get("kind") or ("html" if p.get("text") else "")

        records: List[Any] = []
        counts = {"structured": 0, "media": 0, "extracted": 0, "raw": 0}
        textual: List[Dict[str, Any]] = []
        for p in pages:
            k = kind_of(p)
            if not k:
                continue
            if p.get("rows"):                                              # JSON/CSV: já são registros, sem IA e sem inventar nada
                for row in p["rows"]:
                    if isinstance(row, dict):
                        records.append({**row, "source_url": p["url"]})
                        counts["structured"] += 1
            elif k in ("image", "audio", "video", "pdf", "file"):
                records.append(links.record_for({**p, "kind": k}))
                counts["media"] += 1
            elif p.get("text"):
                textual.append({**p, "kind": k})
        new_schema = schema
        batch = max(1, SCRAPE_BATCH)
        for start in range(0, len(textual), batch):
            if self.cancelled():
                break
            chunk = textual[start:start + batch]
            self.emit({"type": "stage", "stage": "extract", "message": f"Extraindo dados estruturados ({start + 1}-{start + len(chunk)})..."})
            slim = [{"url": c["url"], "title": c.get("title", ""), "kind": c["kind"], "text": c.get("text", "")[:6000]} for c in chunk]
            obj = self._step(f"extrair {start + 1}-{start + len(chunk)}", lambda: self._ask_json(
                "Extract structured records from the scraped pages according to the prompt and the schema. Use only information present in the page text.",
                {"prompt": prompt, "pages": slim, "schema": schema, "attachments": atts["text"][:6000]}, creative=False, images=atts["images"], role="extractor"))
            got = [x for x in (obj.get("records") if isinstance(obj, dict) and isinstance(obj.get("records"), list) else []) if isinstance(x, dict) and x]
            if got:
                for x in got:
                    if not any(k in x for k in ("source_url", "url")) and len(chunk) == 1:
                        x["source_url"] = chunk[0]["url"]
                records.extend(got)
                counts["extracted"] += len(got)
                if isinstance(obj.get("schema"), dict) and (obj["schema"].get("fields") or []):
                    new_schema = ops._union_schema(new_schema if not self._is_default_schema(new_schema) else {"fields": []}, clean_schema(obj["schema"]))
            else:
                # sem IA (ou a IA falhou neste lote): guarda o texto cru de cada página — nada é inventado
                for c in chunk:
                    records.append(links.record_for(c))
                    counts["raw"] += 1
        # conferir: sem repetidos (mesma URL + mesmo conteúdo), e tudo é objeto
        dd = quality.dedupe(records, None, None, True)
        records = dd["kept"]
        if dd["removed"]:
            self.warnings.append(f"{len(dd['removed'])} registro(s) repetido(s) foram descartados.")
        if records:
            new_schema = ops.infer_schema(records, new_schema if not self._is_default_schema(new_schema) else {"fields": []})
            cur = self.manager.get(kind, item_id)
            final_schema = clean_schema(ops._union_schema(cur.get("schema") if not self._is_default_schema(cur.get("schema") or {}) else {"fields": []}, new_schema))
            self.manager.save_records(kind, item_id, (cur.get("records") or []) + records, final_schema, "scrape")
        out = self.manager.get(kind, item_id)
        by_kind = Counter(kind_of(p) or "erro" for p in pages)
        checks = {"links": len(urls), "read": len(pages) - len(failed) - len(skipped), "skipped_robots": len(skipped), "failed": len(failed), "by_kind": dict(by_kind), **{k: v for k, v in counts.items() if v}}
        self.emit({"type": "done", "generated": len(records), "records": len(out.get("records") or []), "pages": len(pages) - len(failed) - len(skipped), "skipped": len(skipped), "warnings": self.warnings, "checks": checks})
        return {"generated": len(records), "pages": len(pages) - len(failed) - len(skipped), "skipped": len(skipped), "failed": len(failed), "records": len(out.get("records") or []),
                "item": out["meta"], "ai": self.live, "warnings": self.warnings, "checks": checks, "report": self.report()}

    # ================================================================ upgrade (importar e melhorar)
    #: ações do Upgrade; `det` = funciona sem IA
    ACTIONS = ("enrich", "fill_missing", "classify", "translate", "clean", "generate")

    def upgrade(self, kind: str, item_id: str) -> Dict[str, Any]:
        action = text(self.opts.get("action"), "enrich", 20)
        action = {"add_more": "generate", "normalize": "clean"}.get(action, action)
        if action not in self.ACTIONS:
            action = "enrich"
        try:
            count = max(0, min(int(self.opts.get("count") or 0), MAX_SYNTH_COUNT))
        except (TypeError, ValueError):
            count = 0
        if action == "generate":
            if count <= 0:
                count = 20
            self.opts["count"] = count
            return self.generate_synthetic(kind, item_id)
        prompt = text(self.opts.get("prompt"), "", 20000)
        mode = "multi" if self.opts.get("mode") == "multi" else "single"
        fields = [f for f in (self.opts.get("fields") if isinstance(self.opts.get("fields"), list) else []) if isinstance(f, str)][:40]
        target = self.manager.get(kind, item_id)
        schema = target.get("schema") or {"fields": []}
        recs = target.get("records") or []
        self.emit({"type": "stage", "stage": "upgrade", "message": "Melhorando os registros..."})
        info: Dict[str, Any] = {"action": action, "total": len(recs), "changed": 0, "unchanged": 0, "batches": 0, "failed_batches": 0}
        new_recs: List[Any] = recs
        new_schema = schema
        if action == "clean":
            new_recs, new_schema, st = ops.clean(recs, ops.infer_schema(recs, schema))
            info.update(st)
            info["changed"] = sum(1 for a, b in zip(recs, new_recs) if a != b) if len(new_recs) == len(recs) else len(new_recs)
        elif not recs:
            self.warnings.append("o item não tem registros para melhorar; use «Gerar mais dados» para criar.")
        else:
            new_recs, new_schema, st = self._transform(action, recs, schema, prompt, fields, mode, self.opts.get("language") or "")
            info.update(st)
        changed = new_recs != recs or new_schema != schema
        if changed:
            self.manager.save_records(kind, item_id, new_recs, clean_schema(new_schema), "upgrade_" + action)
        # conferir: a conta fecha, ids intactos
        idf = next((f["name"] for f in schema.get("fields") or [] if isinstance(f, dict) and str(f.get("name", "")).lower() in quality.ID_FIELDS), "")
        ids_ok = True
        if idf and action != "clean" and len(new_recs) == len(recs):
            ids_ok = all((a.get(idf) == b.get(idf)) for a, b in zip(recs, new_recs) if isinstance(a, dict) and isinstance(b, dict))
        info["checks"] = {"count_ok": action == "clean" or len(new_recs) == len(recs), "ids_ok": ids_ok}
        out = self.manager.get(kind, item_id)
        self.emit({"type": "done", "records": len(out.get("records") or []), "warnings": self.warnings, "checks": info})
        return {"records": len(out.get("records") or []), "item": out["meta"], "ai": self.live, "warnings": self.warnings, "checks": info, "report": self.report()}

    def _transform(self, action: str, recs: List[Any], schema: Dict[str, Any], prompt: str, fields: List[str], mode: str, language: str) -> Tuple[List[Any], Dict[str, Any], Dict[str, int]]:
        """Passa a base INTEIRA pela IA em lotes (antes só os 40 primeiros eram melhorados). Cada registro volta com o mesmo `_i`; ids e campos fora do pedido são protegidos;
        o que a IA não devolver (ou devolver inválido) fica como estava. Sem IA: `fill_missing` usa o preenchimento determinístico; as outras ações avisam que precisam de IA."""
        st = {"changed": 0, "unchanged": 0, "batches": 0, "failed_batches": 0}
        if not self.live:
            if action == "fill_missing":
                out, fill = ops.fill_missing(recs, schema, "auto", fields or None)
                st["changed"] = fill["total"]
                self.warnings.append("sem IA: preenchi vazios com a mediana/valor mais comum de cada coluna." + (f" Sem valor de referência: {', '.join(fill['skipped'])}." if fill["skipped"] else ""))
                return out, schema, st
            self.warnings.append(f"a ação «{action}» precisa de uma IA configurada; nada foi alterado.")
            st["unchanged"] = len(recs)
            return recs, schema, st
        protected = {f.get("name") for f in schema.get("fields") or [] if isinstance(f, dict) and str(f.get("name", "")).lower() in quality.ID_FIELDS}
        target_field = (fields[0] if fields else "label") if action == "classify" else ""
        out: List[Any] = [dict(r) if isinstance(r, dict) else r for r in recs]
        new_schema = schema
        size = max(5, min(25, 12000 // max(200, len(json.dumps(recs[:5], ensure_ascii=False)) // max(1, min(5, len(recs))))))
        batches = [list(range(i, min(i + size, len(out)))) for i in range(0, len(out), size)]
        if self.team.multi and len(batches) > 8:
            self.warnings.append(f"{len(batches)} lotes: a equipe de {self.team.agents} agentes trabalha no plano; cada lote usa uma chamada para não multiplicar o custo.")
        instruction = {
            "enrich": "Improve and enrich the records following the instruction. Keep existing values unless the instruction asks to change them; you may fill empty fields.",
            "fill_missing": "Fill ONLY the empty or null fields with plausible values consistent with the rest of each record. Never change a non-empty value.",
            "classify": f"Add the field '{target_field}' with one label per record, following the instruction.",
            "translate": f"Translate the text of the listed fields to {language or 'the language asked in the instruction'}. Leave ids, numbers, dates and URLs untouched.",
        }[action]
        for bi, idxs in enumerate(batches):
            if self.cancelled():
                self.warnings.append("cancelado: guardei as melhorias dos lotes já prontos.")
                break
            st["batches"] += 1
            payload = {"action": action, "instruction": prompt, "fields": fields, "target_field": target_field, "language": language, "schema": schema,
                       "new_fields": mode == "multi" or action in ("classify", "enrich"),
                       "records": [{"_i": i, **(out[i] if isinstance(out[i], dict) else {"value": out[i]})} for i in idxs]}
            obj = self._step(f"lote {bi + 1}/{len(batches)}", lambda: self._ask_json(instruction, payload, creative=len(batches) <= 8, role="transformer"))
            rows = obj.get("records") if isinstance(obj, dict) and isinstance(obj.get("records"), list) else None
            if not rows:
                st["failed_batches"] += 1
                continue
            idf = next(iter(protected), "")
            by_id = {str(out[i].get(idf)): i for i in idxs if idf and isinstance(out[i], dict) and not quality._is_blank(out[i].get(idf))}
            for pos, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                i = row.get("_i")
                if not (isinstance(i, int) and i in idxs):
                    i = by_id.get(str(row.get(idf))) if idf and not quality._is_blank(row.get(idf)) else None
                    if i is None and len(rows) == len(idxs):
                        i = idxs[pos]                                   # sem `_i` nem id: só confia na posição quando a contagem bate
                if i is None or not isinstance(out[i], dict):
                    continue
                change = {k: v for k, v in row.items() if k != "_i" and k not in protected}
                if action in ("fill_missing",):
                    change = {k: v for k, v in change.items() if quality._is_blank(out[i].get(k))}
                elif action == "translate" and fields:
                    change = {k: v for k, v in change.items() if k in fields}
                elif action == "classify":
                    change = {k: v for k, v in change.items() if k == target_field}
                if any(out[i].get(k) != v for k, v in change.items()):
                    out[i].update({str(k)[:80]: v for k, v in change.items()})
                    st["changed"] += 1
            if isinstance(obj, dict) and isinstance(obj.get("schema"), dict) and (obj["schema"].get("fields") or []) and action != "fill_missing":
                new_schema = ops._union_schema(new_schema, clean_schema(obj["schema"]))
        st["unchanged"] = len(out) - st["changed"]
        new_schema = ops.infer_schema(out, new_schema)
        out, cst = ops.coerce_records(out, new_schema)
        if cst["failed"]:
            self.warnings.append(f"{cst['failed']} valor(es) não puderam ser convertidos ao tipo do campo e foram mantidos como vieram.")
        if st["failed_batches"]:
            self.warnings.append(f"{st['failed_batches']} lote(s) sem resposta válida da IA: esses registros ficaram como estavam.")
        return out, new_schema, st


def base_slug(text_value: str) -> str:
    """Um pedaço de texto virando um pedaço de URL/nome de arquivo."""
    out = "".join(c if c.isalnum() else "-" for c in (text_value or "").lower())
    return "-".join(p for p in out.split("-") if p)[:40] or "item"
