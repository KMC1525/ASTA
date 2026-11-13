"""Persistência e operações do modo Data.

Cada item (database ou dataset) fica em ~/.asta/data/<kind>/<id>/ com:
  meta.json, schema.json, records.json (lista de objetos), attachments/, exports/, history/
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import sqlite3
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..util import new_id, now_iso, read_json, safe_filename, slugify, text, write_json
from . import formats, ops, quality
from .schema import EXPORT_FORMATS, IMPORT_FORMATS, KINDS, clean_schema

MAX_ITEMS = 500
MAX_RECORDS = 200000
MAX_IMPORT_BYTES = 50 * 1024 * 1024
MAX_EXPORT_ROWS = 200000
#: mídia guardada no item (imagens, áudios, vídeos, PDFs, qualquer arquivo que os registros citem como `attachments/<nome>`)
MEDIA_MAX_FILE = 25 * 1024 * 1024
MEDIA_MAX_FILES = 500
MEDIA_MAX_TOTAL = 1024 * 1024 * 1024
#: tipos que o navegador pode mostrar dentro da página (sempre com `sandbox`); o resto — inclusive SVG e HTML — só baixa
MEDIA_INLINE = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp", ".avif": "image/avif",
                ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".flac": "audio/flac", ".opus": "audio/ogg",
                ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".m4v": "video/mp4",
                ".txt": "text/plain; charset=utf-8", ".json": "application/json; charset=utf-8", ".csv": "text/csv; charset=utf-8"}


class DataError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = str(message)
        self.status = int(status)


def valid_kind(kind: str) -> str:
    k = str(kind or "").strip().lower()
    if k not in KINDS:
        raise DataError("Tipo inválido (use database ou dataset).", 400)
    return k


def valid_id(value: str) -> str:
    v = str(value or "").strip()
    if not v or "/" in v or "\\" in v or ".." in v:
        raise DataError("ID inválido.", 400)
    return v


class DataManager:
    def __init__(self, store: Any):
        self.store = store
        self.home = Path(store.home)
        self.root = self.home / "data"
        self.lock = threading.RLock()
        for k in KINDS:
            (self.root / k).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths
    def _dir(self, kind: str, item_id: str) -> Path:
        return self.root / valid_kind(kind) / valid_id(item_id)

    def _meta_path(self, kind: str, item_id: str) -> Path:
        return self._dir(kind, item_id) / "meta.json"

    def _schema_path(self, kind: str, item_id: str) -> Path:
        return self._dir(kind, item_id) / "schema.json"

    def _records_path(self, kind: str, item_id: str) -> Path:
        return self._dir(kind, item_id) / "records.json"

    def _history_dir(self, kind: str, item_id: str) -> Path:
        d = self._dir(kind, item_id) / "history"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _exports_dir(self, kind: str, item_id: str) -> Path:
        d = self._dir(kind, item_id) / "exports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------ core
    def list(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        kinds = [valid_kind(kind)] if kind else list(KINDS)
        out: List[Dict[str, Any]] = []
        for k in kinds:
            base = self.root / k
            if not base.is_dir():
                continue
            for p in base.iterdir():
                if not p.is_dir():
                    continue
                meta = read_json(p / "meta.json")
                if isinstance(meta, dict) and meta.get("id"):
                    out.append(self._summary(meta, k))
        out.sort(key=lambda x: x.get("updated", ""), reverse=True)
        return out[:MAX_ITEMS]

    def _counts(self, kind: str, rid: str) -> Tuple[int, int]:
        recs = read_json(self._records_path(kind, rid), []) or []
        schema = read_json(self._schema_path(kind, rid), {"fields": []}) or {"fields": []}
        fields = schema.get("fields") if isinstance(schema, dict) and isinstance(schema.get("fields"), list) else []
        return (len(recs) if isinstance(recs, list) else 0), len(fields)

    def _sync_counts(self, kind: str, rid: str) -> Dict[str, Any]:
        """Guarda a contagem de registros/campos no `meta.json`: as listagens leem só os metadados, não a base inteira."""
        m = read_json(self._meta_path(kind, rid), {}) or {}
        m["records_n"], m["fields_n"] = self._counts(kind, rid)
        write_json(self._meta_path(kind, rid), m)
        return m

    def _summary(self, meta: Dict[str, Any], kind: str) -> Dict[str, Any]:
        rid = meta.get("id", "")
        if "records_n" not in meta or "fields_n" not in meta:   # item criado antes da v0.24: conta uma vez e guarda
            try:
                meta = self._sync_counts(kind, rid)
            except Exception:  # noqa: BLE001
                meta = {**meta, "records_n": 0, "fields_n": 0}
        return {
            "id": rid,
            "kind": kind,
            "name": meta.get("name", ""),
            "description": meta.get("description", ""),
            "tags": meta.get("tags", []),
            "created": meta.get("created", ""),
            "updated": meta.get("updated", ""),
            "records": meta.get("records_n", 0),
            "fields": meta.get("fields_n", 0),
            "modalities": meta.get("modalities", []),
        }

    def meta(self, kind: str, item_id: str) -> Dict[str, Any]:
        m = read_json(self._meta_path(kind, item_id))
        if not isinstance(m, dict):
            raise DataError("Item não encontrado.", 404)
        return m

    def get(self, kind: str, item_id: str) -> Dict[str, Any]:
        with self.lock:
            m = self.meta(kind, item_id)
            schema = read_json(self._schema_path(kind, item_id), {"fields": []}) or {"fields": []}
            records = read_json(self._records_path(kind, item_id), []) or []
            if not isinstance(records, list):
                records = []
            exports = self.list_exports(kind, item_id)
            return {"meta": self._summary(m, valid_kind(kind)), "schema": clean_schema(schema), "records": records, "exports": exports}

    def create(self, kind: str, name: str = "", description: str = "", schema: Any = None, records: Any = None, tags: Any = None, modalities: Any = None) -> Dict[str, Any]:
        k = valid_kind(kind)
        with self.lock:
            item_id = new_id("d_" if k == "database" else "s_")
            d = self._dir(k, item_id)
            d.mkdir(parents=True, exist_ok=False)
            (d / "attachments").mkdir(exist_ok=True)
            (d / "exports").mkdir(exist_ok=True)
            (d / "history").mkdir(exist_ok=True)
            meta = {
                "id": item_id,
                "kind": k,
                "name": text(name, "Novo " + ("database" if k == "database" else "dataset"), 100),
                "description": text(description, "", 1000),
                "tags": [text(t, "", 40) for t in (tags if isinstance(tags, list) else []) if text(t, "", 40)][:30],
                "modalities": [text(t, "", 40) for t in (modalities if isinstance(modalities, list) else []) if text(t, "", 40)][:20],
                "created": now_iso(),
                "updated": now_iso(),
            }
            write_json(self._meta_path(k, item_id), meta)
            write_json(self._schema_path(k, item_id), clean_schema(schema))
            recs = records if isinstance(records, list) else []
            write_json(self._records_path(k, item_id), recs[:MAX_RECORDS])
            meta = self._sync_counts(k, item_id)
            self.snapshot(k, item_id, "create")
            return self._summary(meta, k)

    def update_meta(self, kind: str, item_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            m = self.meta(kind, item_id)
            if isinstance(patch.get("name"), str):
                m["name"] = text(patch["name"], m.get("name", ""), 100)
            if isinstance(patch.get("description"), str):
                m["description"] = text(patch["description"], "", 1000)
            if isinstance(patch.get("tags"), list):
                m["tags"] = [text(t, "", 40) for t in patch["tags"] if text(t, "", 40)][:30]
            if isinstance(patch.get("modalities"), list):
                m["modalities"] = [text(t, "", 40) for t in patch["modalities"] if text(t, "", 40)][:20]
            m["updated"] = now_iso()
            write_json(self._meta_path(kind, item_id), m)
            return self._summary(m, valid_kind(kind))

    def delete(self, kind: str, item_id: str) -> bool:
        with self.lock:
            d = self._dir(kind, item_id)
            if not d.is_dir():
                raise DataError("Item não encontrado.", 404)
            shutil.rmtree(d, ignore_errors=True)
            return True

    def duplicate(self, kind: str, item_id: str, name: str = "") -> Dict[str, Any]:
        with self.lock:
            src = self.get(kind, item_id)
            m = src["meta"]
            nm = text(name, m.get("name", "") + " (cópia)", 100)
            new = self.create(kind, nm, m.get("description", ""), src.get("schema"), src.get("records"), m.get("tags"), m.get("modalities"))
            self._copy_media(kind, item_id, new["kind"], new["id"])   # a cópia também mostra as imagens/áudios/vídeos do original
            return new

    # ------------------------------------------------------------------ records/schema
    def save_records(self, kind: str, item_id: str, records: Any, schema: Any = None, label: str = "edit") -> Dict[str, Any]:
        with self.lock:
            self.meta(kind, item_id)
            recs = records if isinstance(records, list) else []
            # sanitize records to jsonable dict/list/primitive
            clean: List[Any] = []
            for r in recs[:MAX_RECORDS]:
                if isinstance(r, dict):
                    clean.append({str(k)[:80]: self._clean_value(v) for k, v in list(r.items())[:200]})
                else:
                    clean.append({"value": self._clean_value(r)})
            write_json(self._records_path(kind, item_id), clean)
            if schema is not None:
                write_json(self._schema_path(kind, item_id), clean_schema(schema))
            self._sync_counts(kind, item_id)
            self.snapshot(kind, item_id, label or "edit")
            self._touch(kind, item_id)
            return self.get(kind, item_id)

    def _clean_value(self, v: Any, depth: int = 0) -> Any:
        if depth > 6:
            return str(v)[:2000]
        if v is None or isinstance(v, (bool, int)):
            return v
        if isinstance(v, float):
            return v
        if isinstance(v, str):
            return v[:20000]
        if isinstance(v, list):
            return [self._clean_value(x, depth + 1) for x in v[:200]]
        if isinstance(v, dict):
            return {str(k)[:80]: self._clean_value(x, depth + 1) for k, x in list(v.items())[:200]}
        return str(v)[:2000]

    def append_records(self, kind: str, item_id: str, records: Any, label: str = "append") -> Dict[str, Any]:
        with self.lock:
            cur = self.get(kind, item_id)
            base = cur.get("records") if isinstance(cur.get("records"), list) else []
            add = records if isinstance(records, list) else []
            return self.save_records(kind, item_id, base + add, cur.get("schema"), label)

    # ------------------------------------------------------------------ qualidade (v0.23)
    def profile(self, kind: str, item_id: str) -> Dict[str, Any]:
        """Perfil das colunas e achados de qualidade do item (só leitura)."""
        d = self.get(kind, item_id)
        return quality.profile(d.get("records") or [], d.get("schema"))

    def dedupe(self, kind: str, item_id: str, keys: Any = None, ignore_case: bool = True, apply: bool = False) -> Dict[str, Any]:
        """Duplicados do item. Sem `apply` é só a **prévia** (nada muda); com `apply` grava os registros sem repetição depois de um snapshot (dá para restaurar no histórico)."""
        with self.lock:
            d = self.get(kind, item_id)
            res = quality.dedupe(d.get("records") or [], d.get("schema"), keys, ignore_case)
            out = {"total": len(d.get("records") or []), "kept": len(res["kept"]), "removed": len(res["removed"]), "groups": res["groups"][:50], "keys": res["keys"],
                   "skipped_blank": res["skipped_blank"], "ignore_case": res["ignore_case"], "checks": res["checks"], "applied": False}
            if apply and res["removed"]:
                if not res["checks"]["ok"]:
                    raise DataError("A conferência dos duplicados falhou; nada foi alterado.", 409)
                self.save_records(kind, item_id, res["kept"], d.get("schema"), "dedupe")
                out["applied"] = True
            return out

    def merge_items(self, kind: str, target_id: str, source_kind: str, source_id: str, strategy: str = "append", keys: Any = None,
                    conflict: str = "keep_target", dedupe: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        """Mescla o item de origem no de destino. `strategy`: `append` (junta) ou `upsert` (combina por chave; `conflict`: `keep_target` | `prefer_source`). `dry_run` só mostra a conta.
        O schema é a união pelo nome do campo e a mídia da origem vem junto (o destino não perde nenhum arquivo)."""
        with self.lock:
            tgt = self.get(kind, target_id)
            src = self.get(source_kind, source_id)
            try:
                res = ops.merge(tgt.get("records") or [], src.get("records") or [], tgt.get("schema"), src.get("schema"),
                                "upsert" if strategy == "upsert" else "append", keys, "prefer_source" if conflict == "prefer_source" else "keep_target", bool(dedupe))
            except ValueError as exc:
                raise DataError(str(exc)) from None
            stats = {k: res[k] for k in ("added", "updated", "skipped", "duplicates_removed", "total")}
            if dry_run:
                return {"dry_run": True, **stats, "before": len(tgt.get("records") or []), "schema_fields": len(res["schema"]["fields"]), "preview": res["records"][:5]}
            copied = self._copy_media(source_kind, source_id, kind, target_id)
            out = self.save_records(kind, target_id, res["records"], res["schema"], "merge")
            out["merge"] = {**stats, "media_copied": copied}
            return out

    # ------------------------------------------------------------------ consulta, edição, colunas e limpeza (v0.24)
    def _load(self, kind: str, item_id: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[Any]]:
        m = self.meta(kind, item_id)
        schema = clean_schema(read_json(self._schema_path(kind, item_id), {"fields": []}) or {"fields": []})
        records = read_json(self._records_path(kind, item_id), []) or []
        return m, schema, records if isinstance(records, list) else []

    def query(self, kind: str, item_id: str, q: str = "", sort: str = "", direction: str = "asc", offset: int = 0, limit: int = 100, where: Any = None) -> Dict[str, Any]:
        """Uma página dos registros (busca, filtro por campo, ordenação) — a tela não precisa carregar a base inteira. Cada linha traz `i`, a posição original usada nas edições."""
        with self.lock:
            m, schema, records = self._load(kind, item_id)
        out = ops.query(records, text(q, "", 500), text(sort, "", 80), direction, offset, limit, where if isinstance(where, dict) else None)
        out["columns"] = quality.columns(records[:300], schema)
        out["schema"] = schema
        out["meta"] = self._summary(m, valid_kind(kind))
        return out

    def edit_records(self, kind: str, item_id: str, edits: Any, schema: Any = None) -> Dict[str, Any]:
        """Edições da grade (`set` célula · `delete` linhas · `insert` linha). Grava com snapshot; devolve as contagens e o total."""
        with self.lock:
            _m, cur_schema, records = self._load(kind, item_id)
            try:
                new, st = ops.apply_edits(records, edits)
            except ValueError as exc:
                raise DataError(str(exc)) from None
            sch = clean_schema(schema) if isinstance(schema, dict) else ops.infer_schema(new, cur_schema)
            self.save_records(kind, item_id, new, sch, "grid")
            return {**st, "total": len(new)}

    def column(self, kind: str, item_id: str, op: str, name: str, new_name: str = "", ftype: str = "text", default: Any = None) -> Dict[str, Any]:
        """Adiciona, renomeia, remove ou muda o tipo de uma coluna (schema e registros juntos)."""
        with self.lock:
            _m, schema, records = self._load(kind, item_id)
            try:
                new, info = ops.column_op(records, schema, op, name, new_name, ftype, default)
            except ValueError as exc:
                raise DataError(str(exc)) from None
            self.save_records(kind, item_id, new, info["schema"], "column_" + op)
            return {"schema": info["schema"], **{k: v for k, v in info.items() if k != "schema"}}

    def clean(self, kind: str, item_id: str, options: Any = None, apply: bool = False) -> Dict[str, Any]:
        """Limpeza segura (espaços, tipos pelo schema, linhas vazias, opcionalmente colunas vazias e preenchimento de vazios). Sem `apply` é só a **prévia** com as contagens."""
        o = options if isinstance(options, dict) else {}
        with self.lock:
            _m, schema, records = self._load(kind, item_id)
            sch = schema if (o.get("infer") is False) else ops.infer_schema(records, schema)
            rows, sch2, st = ops.clean(records, sch, trim=o.get("trim") is not False, coerce=o.get("coerce") is not False,
                                       drop_empty_rows=o.get("drop_empty_rows") is not False, drop_empty_columns=o.get("drop_empty_columns") is True)
            fill = None
            if o.get("fill_missing"):
                rows, fill = ops.fill_missing(rows, sch2, str(o.get("fill_strategy") or "auto"), o.get("fill_fields") if isinstance(o.get("fill_fields"), list) else None, o.get("fill_constant"))
            changed = rows != records or sch2 != schema
            out = {"before": len(records), "after": len(rows), **st, "fill": fill, "changed": bool(changed), "applied": False}
            if apply and changed:
                self.save_records(kind, item_id, rows, sch2, "clean")
                out["applied"] = True
            return out

    def infer_schema(self, kind: str, item_id: str, apply: bool = False) -> Dict[str, Any]:
        """Schema deduzido dos dados (a partir do que o item já declara, só acrescenta o que falta)."""
        with self.lock:
            _m, schema, records = self._load(kind, item_id)
            new = ops.infer_schema(records, schema)
            if apply and new != schema:
                self.save_records(kind, item_id, records, new, "schema")
            return {"schema": new, "added": len(new["fields"]) - len(schema["fields"]), "applied": bool(apply and new != schema)}

    # ------------------------------------------------------------------ mídia do item (v0.24)
    def _media_dir(self, kind: str, item_id: str) -> Path:
        d = self._dir(kind, item_id) / "attachments"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_media(self, kind: str, item_id: str) -> List[Dict[str, Any]]:
        self.meta(kind, item_id)
        out = []
        for p in sorted(self._media_dir(kind, item_id).iterdir(), key=lambda x: x.name.lower()):
            if p.is_file():
                out.append({"name": p.name, "size": p.stat().st_size, "ref": "attachments/" + p.name, "kind": ops.media_kind(p.name) or "file", "inline": p.suffix.lower() in MEDIA_INLINE})
        return out[:MEDIA_MAX_FILES]

    def add_media(self, kind: str, item_id: str, filename: str, raw: bytes) -> Dict[str, Any]:
        """Guarda um arquivo no item (imagem, áudio, vídeo, PDF…) e devolve a referência `attachments/<nome>` para usar num campo do registro."""
        if not raw:
            raise DataError("Arquivo vazio.")
        if len(raw) > MEDIA_MAX_FILE:
            raise DataError("Arquivo grande demais (máx. 25 MB).", 413)
        with self.lock:
            d = self._media_dir(kind, item_id)
            files = [p for p in d.iterdir() if p.is_file()]
            if len(files) >= MEDIA_MAX_FILES or sum(p.stat().st_size for p in files) + len(raw) > MEDIA_MAX_TOTAL:
                raise DataError("Limite de mídia do item atingido (500 arquivos / 1 GB).", 409)
            name = safe_filename(Path(str(filename or "arquivo").replace("\\", "/")).name, "arquivo")
            stem, ext = Path(name).stem or "arquivo", Path(name).suffix.lower()[:10]
            name, n = stem + ext, 2
            while (d / name).exists():
                name = f"{stem}-{n}{ext}"
                n += 1
            (d / name).write_bytes(raw)
            self._touch(kind, item_id)
            return {"name": name, "ref": "attachments/" + name, "size": len(raw), "kind": ops.media_kind(name) or "file"}

    def media_path(self, kind: str, item_id: str, name: str) -> Path:
        d = self._media_dir(kind, item_id).resolve()
        p = (d / safe_filename(name, "arquivo")).resolve()
        if p.parent != d or not p.is_file():
            raise DataError("Arquivo não encontrado.", 404)
        return p

    def delete_media(self, kind: str, item_id: str, name: str) -> bool:
        with self.lock:
            self.media_path(kind, item_id, name).unlink()
            self._touch(kind, item_id)
            return True

    def _copy_media(self, src_kind: str, src_id: str, dst_kind: str, dst_id: str) -> int:
        """Ao mesclar, a mídia citada pela origem viaja junto (mesmo nome → mantém o do destino)."""
        try:
            sd, dd = self._media_dir(src_kind, src_id), self._media_dir(dst_kind, dst_id)
        except OSError:
            return 0
        n = 0
        for p in sd.iterdir():
            if p.is_file() and not (dd / p.name).exists():
                try:
                    shutil.copy2(p, dd / p.name)
                    n += 1
                except OSError:
                    continue
        return n

    # ------------------------------------------------------------------ history
    def snapshot(self, kind: str, item_id: str, label: str = "snapshot") -> str:
        # microssegundos no id: duas gravações no mesmo segundo (lotes da geração sintética) não podem sobrescrever o mesmo snapshot; a ordem do nome segue a do tempo
        now = datetime.now(timezone.utc)
        base = now.strftime("%Y-%m-%dT%H-%M-%S") + f"-{now.microsecond:06d}Z_" + slugify(label, "snap")[:30]
        hid, n = base, 1
        while (self._history_dir(kind, item_id) / f"{hid}.json").exists():
            n += 1
            hid = f"{base}-{n}"
        p = self._history_dir(kind, item_id) / f"{hid}.json"
        data = {"meta": read_json(self._meta_path(kind, item_id), {}), "schema": read_json(self._schema_path(kind, item_id), {}), "records": read_json(self._records_path(kind, item_id), [])}
        write_json(p, data)
        # keep recent
        snaps = sorted(self._history_dir(kind, item_id).glob("*.json"))
        keep = 30
        for old in snaps[:-keep]:
            old.unlink(missing_ok=True)
        return hid

    def history(self, kind: str, item_id: str) -> List[Dict[str, Any]]:
        out = []
        for p in sorted(self._history_dir(kind, item_id).glob("*.json"), reverse=True)[:30]:
            out.append({"id": p.stem, "name": p.stem})
        return out

    def restore(self, kind: str, item_id: str, hid: str) -> Dict[str, Any]:
        with self.lock:
            self.meta(kind, item_id)
            p = self._history_dir(kind, item_id) / f"{valid_id(hid)}.json"
            data = read_json(p)
            if not isinstance(data, dict):
                raise DataError("Snapshot não encontrado.", 404)
            write_json(self._schema_path(kind, item_id), clean_schema(data.get("schema")))
            write_json(self._records_path(kind, item_id), data.get("records") if isinstance(data.get("records"), list) else [])
            self._sync_counts(kind, item_id)
            self._touch(kind, item_id)
            return self.get(kind, item_id)

    def _touch(self, kind: str, item_id: str) -> None:
        m = self.meta(kind, item_id)
        m["updated"] = now_iso()
        write_json(self._meta_path(kind, item_id), m)

    # ------------------------------------------------------------------ import/export
    def import_data(self, kind: str, item_id: str, name: str, raw: bytes, mode: str = "replace") -> Dict[str, Any]:
        if len(raw) > MAX_IMPORT_BYTES:
            raise DataError("Arquivo muito grande para importar.", 413)
        fmt = self._detect_format(name)
        records, schema = self._parse_import(fmt, raw)
        current = self.get(kind, item_id)
        if mode == "append":
            # os campos do arquivo importado entram no schema do item (união), senão as colunas novas sumiriam
            merged_schema = self._merge_schema(current.get("schema"), schema)
            base = current.get("records") if isinstance(current.get("records"), list) else []
            return self.save_records(kind, item_id, base + (records or []), merged_schema, "import")
        return self.save_records(kind, item_id, records, schema or current.get("schema"), "import")

    @staticmethod
    def _merge_schema(current: Any, extra: Any) -> Dict[str, Any]:
        """Une dois schemas pelo nome do campo (o atual ganha; o importado só acrescenta)."""
        base = current if isinstance(current, dict) else {"fields": []}
        have = {f.get("name") for f in (base.get("fields") or []) if isinstance(f, dict)}
        fields = [f for f in (base.get("fields") or []) if isinstance(f, dict)]
        for f in (extra or {}).get("fields", []) if isinstance(extra, dict) else []:
            if isinstance(f, dict) and f.get("name") and f["name"] not in have:
                have.add(f["name"])
                fields.append(f)
        return clean_schema({"fields": fields})

    def _detect_format(self, name: str) -> str:
        n = (name or "").lower()
        for ext in IMPORT_FORMATS:
            if n.endswith("." + ext):
                return ext
        if n.endswith(".ndjson"):
            return "jsonl"
        return "json"

    def _parse_import(self, fmt: str, raw: bytes) -> Tuple[List[Any], Optional[Dict[str, Any]]]:
        if fmt == "xlsx":
            try:
                return formats.read_xlsx(raw)
            except formats.FormatError as exc:
                raise DataError(str(exc)) from None
        text_data = raw.decode("utf-8-sig", errors="replace")
        if fmt == "json":
            try:
                obj = json.loads(text_data or "null")
            except ValueError as exc:
                raise DataError(f"JSON inválido: {str(exc)[:100]}") from None
            if isinstance(obj, list):
                recs = obj
            elif isinstance(obj, dict):
                if isinstance(obj.get("records"), list):
                    recs = obj["records"]
                elif isinstance(obj.get("data"), list):
                    recs = obj["data"]
                else:
                    recs = [obj]
            else:
                recs = []
            schema = obj.get("schema") if isinstance(obj, dict) and isinstance(obj.get("schema"), dict) else None
            return recs, clean_schema(schema) if schema else None
        if fmt == "jsonl":
            recs = []
            for line in text_data.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except Exception:
                    recs.append({"value": line})
            return recs, None
        if fmt in ("csv", "tsv"):
            delim = "\t" if fmt == "tsv" else ","
            reader = csv.DictReader(io.StringIO(text_data), delimiter=delim)
            recs = [dict(row) for row in reader]
            fields = [{"name": h, "type": "text", "description": "", "required": False} for h in (reader.fieldnames or [])]
            return recs, {"fields": fields} if fields else None
        if fmt == "xml":
            recs, fields = self._parse_xml(text_data)
            return recs, {"fields": fields} if fields else None
        raise DataError("Formato de importação não suportado.")

    def _parse_xml(self, text_data: str) -> Tuple[List[Any], List[Dict[str, Any]]]:
        """XML genérico: cada elemento repetido vira um registro; os atributos e os filhos viram campos."""
        try:
            root = formats.safe_xml((text_data or "<root/>").encode("utf-8"))   # recusa DOCTYPE/ENTITY: bomba de expansão de entidades
        except formats.FormatError as exc:
            raise DataError(str(exc)) from None

        def tag_of(el: Any) -> str:
            return el.tag.split("}")[-1] if isinstance(el.tag, str) else "item"

        # a lista de registros são os filhos repetidos do primeiro nível que têm o mesmo nome
        groups: Dict[str, List[Any]] = {}
        for child in list(root):
            groups.setdefault(tag_of(child), []).append(child)
        rows: List[Any] = []
        names = list(groups.keys())
        key = max(names, key=lambda n: len(groups[n])) if names else ""
        items = groups.get(key, [])
        if not items:
            items = [root]
        for el in items:
            row: Dict[str, Any] = {}
            for attr, val in list(el.attrib.items())[:200]:
                row[str(attr)[:80]] = self._clean_value(val)
            for child in list(el)[:200]:
                name = tag_of(child)[:80]
                value = (child.text or "").strip()
                if list(child):
                    value = {tag_of(g): (g.text or "").strip() for g in list(child)[:200]}
                if name in row:
                    if not isinstance(row[name], list):
                        row[name] = [row[name]]
                    row[name].append(value)
                else:
                    row[name] = value
            rows.append(row)
        fields: List[Dict[str, Any]] = []
        seen = set()
        for row in rows[:50]:
            if isinstance(row, dict):
                for name in row.keys():
                    if name not in seen:
                        seen.add(name)
                        fields.append({"name": name, "type": "text", "description": "", "required": False})
        return rows, fields

    def list_exports(self, kind: str, item_id: str) -> List[Dict[str, Any]]:
        self.meta(kind, item_id)
        out = []
        d = self._exports_dir(kind, item_id)
        if d.is_dir():
            for p in sorted(d.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if p.is_file():
                    out.append({"name": p.name, "size": p.stat().st_size, "updated": p.stat().st_mtime})
        return out[:50]

    def export(self, kind: str, item_id: str, fmt: str) -> Dict[str, Any]:
        fmt = str(fmt or "json").lower().strip()
        if fmt == "ndjson":
            fmt = "jsonl"
        if fmt not in EXPORT_FORMATS:
            raise DataError("Formato de exportação inválido.")
        with self.lock:
            data = self.get(kind, item_id)
            meta = data["meta"]
            schema = data.get("schema") or {"fields": []}
            records = (data.get("records") or [])[:MAX_EXPORT_ROWS]
            base = safe_filename(slugify(meta.get("name") or item_id, item_id), item_id)
            ext = "db" if fmt == "sqlite" else fmt
            out_path = self._exports_dir(kind, item_id) / f"{base}.{ext}"
            cols_all = self._columns(schema, records)
            typed = ops.infer_schema(records, schema)   # SQLite/SQL/XLSX usam os tipos do schema e, para colunas que só existem nos dados, os tipos deduzidos deles
            if fmt == "json":
                payload = {"kind": kind, "meta": meta, "schema": schema, "records": records}
                out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            elif fmt == "jsonl":
                with out_path.open("w", encoding="utf-8") as f:
                    for r in records:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
            elif fmt in ("csv", "tsv"):
                delim = "\t" if fmt == "tsv" else ","
                cols = self._columns(schema, records)
                with out_path.open("w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=cols, delimiter=delim, extrasaction="ignore")
                    w.writeheader()
                    for r in records:
                        row = r if isinstance(r, dict) else {"value": r}
                        w.writerow({c: self._cell(row.get(c)) for c in cols})
            elif fmt == "sqlite":
                self._export_sqlite(out_path, kind, meta, typed, records)
            elif fmt == "xml":
                self._export_xml(out_path, kind, meta, schema, records)
            elif fmt == "html":
                self._export_html(out_path, meta, schema, records)
            elif fmt == "md":
                self._export_markdown(out_path, meta, schema, records)
            elif fmt == "xlsx":
                out_path.write_bytes(formats.write_xlsx(cols_all, records, typed.get("fields") or [], meta.get("name") or "data"))
            elif fmt == "sql":
                table = re.sub(r"[^A-Za-z0-9_]+", "_", slugify(meta.get("name") or "records", "records")).strip("_") or "records"
                out_path.write_text(formats.to_sql(table, typed.get("fields") or [], cols_all, records), encoding="utf-8")
            elif fmt == "yaml":
                out_path.write_text(formats.to_yaml(kind, {k: meta.get(k) for k in ("id", "name", "description", "tags", "modalities", "created", "updated")}, schema, records), encoding="utf-8")
            elif fmt == "zip":
                self._export_bundle(out_path, kind, item_id, meta, schema, records, cols_all)
            self._touch(kind, item_id)
            return {"name": out_path.name, "path": str(out_path), "format": fmt, "records": len(records)}

    def _export_bundle(self, path: Path, kind: str, item_id: str, meta: Dict[str, Any], schema: Dict[str, Any], records: List[Any], cols: List[str]) -> None:
        """Pacote ZIP para levar o item inteiro: `data.json` (com schema), `records.csv`, `README.md` (ficha dos dados) e a **mídia** que os registros citam (`attachments/…`)."""
        used = {v for r in records if isinstance(r, dict) for v in r.values() if isinstance(v, str) and v.startswith("attachments/")}
        media = [p for p in self._media_dir(kind, item_id).iterdir() if p.is_file() and "attachments/" + p.name in used]
        csv_buf = io.StringIO()
        w = csv.DictWriter(csv_buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in records:
            row = r if isinstance(r, dict) else {"value": r}
            w.writerow({c: self._cell(row.get(c)) for c in cols})
        fields = schema.get("fields") or []
        readme = [f"# {meta.get('name') or 'ASTA Data'}", "", meta.get("description") or "", "", f"- Tipo: {kind}", f"- Registros: {len(records)}", f"- Campos: {len(fields)}",
                  f"- Arquivos de mídia: {len(media)}", f"- Criado: {meta.get('created', '')} · atualizado: {meta.get('updated', '')}", "", "## Campos", "", "| campo | tipo | descrição |", "|---|---|---|"]
        readme += [f"| {self._md(f.get('name'))} | {self._md(f.get('type'))} | {self._md(f.get('description'))} |" for f in fields]
        readme += ["", "Gerado pelo ASTA Data. Campos de mídia apontam para a pasta `attachments/` deste pacote.", ""]
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("data.json", json.dumps({"kind": kind, "meta": meta, "schema": schema, "records": records}, ensure_ascii=False, indent=2))
            z.writestr("records.csv", csv_buf.getvalue())
            z.writestr("README.md", "\n".join(readme))
            for p in media:
                z.write(p, "attachments/" + p.name)

    # ------------------------------------------------------------------ exportadores de texto
    def _rows(self, schema: Dict[str, Any], records: List[Any]) -> List[Dict[str, Any]]:
        """Os registros como linhas (dicts) — um registro que não é objeto vira «value»."""
        return [r if isinstance(r, dict) else {"value": r} for r in records]

    def _export_xml(self, path: Path, kind: str, meta: Dict[str, Any], schema: Dict[str, Any], records: List[Any]) -> None:
        import xml.etree.ElementTree as ET

        root = ET.Element(kind, {"name": str(meta.get("name", "")), "records": str(len(records))})
        fields = ET.SubElement(root, "fields")
        for f in (schema.get("fields") or []):
            if isinstance(f, dict) and f.get("name"):
                ET.SubElement(fields, "field", {"name": str(f["name"]), "type": str(f.get("type") or "text")})
        items = ET.SubElement(root, "records")
        for row in self._rows(schema, records):
            el = ET.SubElement(items, "record")
            for key, val in list(row.items())[:200]:
                name = re.sub(r"[^\w.\-]", "_", str(key))[:80] or "campo"   # nome de tag XML válido (não começa com número/ponto/hífen)
                if not (name[0].isalpha() or name[0] == "_"):
                    name = "f_" + name
                child = ET.SubElement(el, name)
                if name != str(key):
                    child.set("field", str(key))
                if isinstance(val, (dict, list)):
                    child.text = json.dumps(val, ensure_ascii=False)
                    child.set("type", "json")
                else:
                    child.text = "" if val is None else str(val)
                    if isinstance(val, bool):
                        child.set("type", "boolean")
                    elif isinstance(val, int):
                        child.set("type", "integer")
                    elif isinstance(val, float):
                        child.set("type", "number")
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

    def _export_html(self, path: Path, meta: Dict[str, Any], schema: Dict[str, Any], records: List[Any]) -> None:
        cols = self._columns(schema, records)
        head = "".join(f"<th>{self._esc(c)}</th>" for c in cols)
        body = []
        for row in self._rows(schema, records):
            cells = "".join(f"<td>{self._esc(self._cell(row.get(c)))}</td>" for c in cols)
            body.append(f"<tr>{cells}</tr>")
        html = (
            "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>{self._esc(meta.get('name') or 'ASTA Data')}</title>\n"
            "<style>body{font-family:system-ui,sans-serif;margin:24px;background:#0f1115;color:#e8e8e8}"
            "table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #2a2f3a;padding:6px 8px;text-align:left;vertical-align:top}"
            "th{background:#1a1f28}caption{text-align:left;font-weight:600;padding-bottom:8px}</style>\n</head>\n<body>\n"
            f"<table>\n<caption>{self._esc(meta.get('name') or '')} — {len(records)} registro(s)</caption>\n"
            f"<thead><tr>{head}</tr></thead>\n<tbody>\n" + "\n".join(body) + "\n</tbody>\n</table>\n</body>\n</html>\n"
        )
        path.write_text(html, encoding="utf-8")

    def _export_markdown(self, path: Path, meta: Dict[str, Any], schema: Dict[str, Any], records: List[Any]) -> None:
        cols = self._columns(schema, records)
        lines = [f"# {meta.get('name') or 'ASTA Data'}", "", f"Registros: {len(records)}", "",
                 "| " + " | ".join(self._md(c) for c in cols) + " |",
                 "| " + " | ".join("---" for _ in cols) + " |"]
        for row in self._rows(schema, records):
            lines.append("| " + " | ".join(self._md(self._cell(row.get(c))) for c in cols) + " |")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _esc(v: Any) -> str:
        s = "" if v is None else str(v)
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    @staticmethod
    def _md(v: Any) -> str:
        s = "" if v is None else str(v)
        return s.replace("|", "\\|").replace("\r", " ").replace("\n", " ")

    def _columns(self, schema: Dict[str, Any], records: List[Any]) -> List[str]:
        cols = [f["name"] for f in (schema.get("fields") or []) if isinstance(f, dict) and f.get("name")]
        seen = set(cols)
        for r in records[:200]:
            if isinstance(r, dict):
                for k in r.keys():
                    ks = str(k)
                    if ks not in seen:
                        seen.add(ks); cols.append(ks)
        return cols[:200] or ["value"]

    def _cell(self, v: Any) -> Any:
        if v is None:
            return ""
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return v

    def _sqlite_value(self, v: Any) -> Any:
        """Vazio vira NULL (não texto vazio numa coluna numérica); inteiro maior que 64 bits vira texto (o SQLite não o guarda como número)."""
        if v is None:
            return None
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, int) and not (-(2 ** 63) <= v < 2 ** 63):
            return str(v)
        return self._cell(v)

    def _export_sqlite(self, path: Path, kind: str, meta: Dict[str, Any], schema: Dict[str, Any], records: List[Any]) -> None:
        if path.exists():
            path.unlink()
        con = sqlite3.connect(str(path))
        try:
            cur = con.cursor()
            cur.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            cur.execute("INSERT INTO meta(key,value) VALUES(?,?)", ("kind", kind))
            cur.execute("INSERT INTO meta(key,value) VALUES(?,?)", ("name", str(meta.get("name", ""))))
            cur.execute("INSERT INTO meta(key,value) VALUES(?,?)", ("schema", json.dumps(schema, ensure_ascii=False)))
            cols = self._columns(schema, records)
            sqltypes = {f.get("name"): {"integer": "INTEGER", "number": "REAL", "boolean": "INTEGER"}.get(f.get("type"), "TEXT") for f in (schema.get("fields") or []) if isinstance(f, dict)}
            coldefs = ", ".join([f'"{c.replace(chr(34), chr(34)+chr(34))}" {sqltypes.get(c, "TEXT")}' for c in cols])
            cur.execute(f'CREATE TABLE records ({coldefs})' if coldefs else 'CREATE TABLE records (value TEXT)')
            placeholders = ",".join(["?"] * len(cols))
            colnames = ",".join([f'"{c.replace(chr(34), chr(34)+chr(34))}"' for c in cols])
            for r in records:
                row = r if isinstance(r, dict) else {"value": r}
                vals = [self._sqlite_value(row.get(c)) for c in cols]
                cur.execute(f'INSERT INTO records ({colnames}) VALUES ({placeholders})', vals)
            con.commit()
        finally:
            con.close()

    def export_path(self, kind: str, item_id: str, name: str) -> Path:
        p = (self._exports_dir(kind, item_id) / safe_filename(name, "export")).resolve()
        if self._exports_dir(kind, item_id).resolve() not in p.parents and p.parent != self._exports_dir(kind, item_id).resolve():
            raise DataError("Arquivo inválido.", 400)
        if not p.is_file():
            raise DataError("Exportação não encontrada.", 404)
        return p

    # ------------------------------------------------------------------ import existing (upgrade tab helper)
    def create_from_upload(self, kind: str, name: str, filename: str, raw: bytes) -> Dict[str, Any]:
        fmt = self._detect_format(filename)
        records, schema = self._parse_import(fmt, raw)
        return self.create(kind, name or filename, f"Importado de {filename}", schema, records)
