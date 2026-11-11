"""Persistência e operações do modo Data.

Cada item (database ou dataset) fica em ~/.asta/data/<kind>/<id>/ com:
  meta.json, schema.json, records.json (lista de objetos), attachments/, exports/, history/
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import sqlite3
import threading
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..util import new_id, now_iso, read_json, safe_filename, slugify, text, write_json
from .schema import EXPORT_FORMATS, IMPORT_FORMATS, KINDS, clean_schema

MAX_ITEMS = 500
MAX_RECORDS = 200000
MAX_IMPORT_BYTES = 50 * 1024 * 1024
MAX_EXPORT_ROWS = 200000


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

    def _summary(self, meta: Dict[str, Any], kind: str) -> Dict[str, Any]:
        rid = meta.get("id", "")
        recs = []
        try:
            recs = read_json(self._records_path(kind, rid), []) or []
            if not isinstance(recs, list):
                recs = []
        except Exception:
            recs = []
        schema = read_json(self._schema_path(kind, rid), {"fields": []}) or {"fields": []}
        fields = schema.get("fields") if isinstance(schema, dict) and isinstance(schema.get("fields"), list) else []
        return {
            "id": rid,
            "kind": kind,
            "name": meta.get("name", ""),
            "description": meta.get("description", ""),
            "tags": meta.get("tags", []),
            "created": meta.get("created", ""),
            "updated": meta.get("updated", ""),
            "records": len(recs),
            "fields": len(fields),
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
            return self.create(kind, nm, m.get("description", ""), src.get("schema"), src.get("records"), m.get("tags"), m.get("modalities"))

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

    def merge_items(self, kind: str, target_id: str, source_kind: str, source_id: str) -> Dict[str, Any]:
        with self.lock:
            tgt = self.get(kind, target_id)
            src = self.get(source_kind, source_id)
            # merge schemas (union by name)
            tf = {f["name"]: f for f in (tgt.get("schema", {}).get("fields") or []) if isinstance(f, dict)}
            for f in (src.get("schema", {}).get("fields") or []):
                if isinstance(f, dict) and f.get("name") and f["name"] not in tf:
                    tf[f["name"]] = f
            schema = {"fields": list(tf.values())[:120]}
            recs = (tgt.get("records") or []) + (src.get("records") or [])
            return self.save_records(kind, target_id, recs, schema, "merge")

    # ------------------------------------------------------------------ history
    def snapshot(self, kind: str, item_id: str, label: str = "snapshot") -> str:
        hid = now_iso().replace(":", "-") + "_" + slugify(label, "snap")[:30]
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
        if mode == "append":
            return self.append_records(kind, item_id, records, "import")
        return self.save_records(kind, item_id, records, schema or self.get(kind, item_id).get("schema"), "import")

    def _detect_format(self, name: str) -> str:
        n = (name or "").lower()
        for ext in IMPORT_FORMATS:
            if n.endswith("." + ext):
                return ext
        if n.endswith(".ndjson"):
            return "jsonl"
        return "json"

    def _parse_import(self, fmt: str, raw: bytes) -> Tuple[List[Any], Optional[Dict[str, Any]]]:
        text_data = raw.decode("utf-8-sig", errors="replace")
        if fmt == "json":
            obj = json.loads(text_data or "null")
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
        raise DataError("Formato de importação não suportado.")

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
                self._export_sqlite(out_path, kind, meta, schema, records)
            self._touch(kind, item_id)
            return {"name": out_path.name, "path": str(out_path), "format": fmt, "records": len(records)}

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
            coldefs = ", ".join([f'"{c.replace(chr(34), chr(34)+chr(34))}" TEXT' for c in cols])
            cur.execute(f'CREATE TABLE records ({coldefs})' if coldefs else 'CREATE TABLE records (value TEXT)')
            placeholders = ",".join(["?"] * len(cols))
            colnames = ",".join([f'"{c.replace(chr(34), chr(34)+chr(34))}"' for c in cols])
            for r in records:
                row = r if isinstance(r, dict) else {"value": r}
                vals = [self._cell(row.get(c)) for c in cols]
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
