"""Operações determinísticas do modo Data (v0.24): inferir schema, converter tipos, limpar, preencher vazios, colunas, edição de células/linhas, consulta paginada e mesclagem.

Tudo aqui é puro (recebe listas, devolve listas) e **nunca perde dado em silêncio**: valores que não convertem ficam como estavam e são contados; linhas só saem quando o pedido
diz (apagar, limpar linhas vazias) e o resultado traz as contagens. Funciona sem IA e sem internet. O `DataManager` é quem grava (com snapshot antes).
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import quality
from .schema import FIELD_TYPES

MAX_EDITS = 5000
MAX_PAGE = 500
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$")
_BR_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_URL = re.compile(r"^https?://\S+$", re.I)
_IMG = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".avif")
_AUD = (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".opus")
_VID = (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v")
_TRUE = {"true", "yes", "y", "sim", "s", "1", "verdadeiro", "on"}
_FALSE = {"false", "no", "n", "nao", "não", "0", "falso", "off"}


def media_kind(value: Any) -> str:
    """image | audio | video | '' — pelo final do nome/URL (a extensão decide só o que a tela mostra; nada é executado)."""
    if not isinstance(value, str):
        return ""
    v = value.split("?", 1)[0].split("#", 1)[0].lower()
    if v.endswith(_IMG):
        return "image"
    if v.endswith(_AUD):
        return "audio"
    if v.endswith(_VID):
        return "video"
    return ""


# ----------------------------------------------------------------------------- tipos
def coerce_value(v: Any, ftype: str) -> Tuple[Any, bool]:
    """(valor convertido, deu certo?). Valor vazio (None / texto em branco) fica como está e conta como certo."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return v, True
    try:
        if ftype == "integer":
            if isinstance(v, bool):
                return int(v), True
            if isinstance(v, int):
                return v, True
            f = float(str(v).strip().replace(",", ".")) if not isinstance(v, float) else v
            if math.isfinite(f) and f == int(f):
                return int(f), True
            return v, False
        if ftype == "number":
            if isinstance(v, bool):
                return float(v), True
            if isinstance(v, (int, float)):
                return v, True
            f = float(str(v).strip().replace(",", "."))
            return (f, True) if math.isfinite(f) else (v, False)
        if ftype == "boolean":
            if isinstance(v, bool):
                return v, True
            s = str(v).strip().lower()
            if s in _TRUE:
                return True, True
            if s in _FALSE:
                return False, True
            return v, False
        if ftype == "date":
            s = str(v).strip()
            if _ISO_DATE.match(s):
                return s, True
            m = _BR_DATE.match(s)
            if m:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 1 <= mo <= 12 and 1 <= d <= 31:
                    return f"{y:04d}-{mo:02d}-{d:02d}", True
            return v, False
        if ftype == "json":
            if isinstance(v, (dict, list)):
                return v, True
            if isinstance(v, str):
                try:
                    return json.loads(v), True
                except ValueError:
                    return v, False
            return v, True
        if ftype == "url":
            s = str(v).strip()
            return (s, True) if _URL.match(s) or s.startswith(("attachments/", "/api/data/")) else (v, False)
        if ftype in ("text", "category", "image", "audio", "video", "file"):
            if isinstance(v, str):
                return v, True
            if isinstance(v, (dict, list)):
                return json.dumps(v, ensure_ascii=False), True
            return str(v), True
    except (ValueError, TypeError, OverflowError):
        return v, False
    return v, True


def infer_type(values: Sequence[Any]) -> str:
    """O tipo que melhor descreve os valores (ignora vazios). Mídia por extensão; `category` quando poucos valores se repetem muito."""
    vals = [v for v in values if not quality._is_blank(v)]
    if not vals:
        return "text"
    if all(isinstance(v, bool) for v in vals):
        return "boolean"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
        return "integer" if all(-(2 ** 63) <= v < 2 ** 63 for v in vals) else "text"   # além de 64 bits só texto guarda os dígitos exatos
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return "number"
    if any(isinstance(v, (dict, list)) for v in vals):
        return "json"
    strs = [str(v).strip() for v in vals]
    kinds = {media_kind(s) for s in strs}
    if len(kinds) == 1 and "" not in kinds:
        return kinds.pop()
    if all(_ISO_DATE.match(s) for s in strs):
        return "date"
    if all(_URL.match(s) for s in strs):
        return "url"
    distinct = len(set(strs))
    if len(strs) >= 20 and distinct <= 12 and distinct / len(strs) <= 0.2 and max(len(s) for s in strs) <= 40:
        return "category"
    return "text"


def infer_schema(records: Sequence[Any], current: Any = None, sample: int = 500) -> Dict[str, Any]:
    """Schema a partir dos registros: mantém o que o `current` já declara (nome, tipo, descrição) e acrescenta as colunas que só existem nos dados."""
    cur = {f["name"]: f for f in ((current or {}).get("fields") or []) if isinstance(f, dict) and f.get("name")} if isinstance(current, dict) else {}
    fields: List[Dict[str, Any]] = [dict(f) for f in cur.values()]
    seen = set(cur)
    rows = list(records)[:sample]
    for name in quality.columns(rows, None):
        if name in seen:
            continue
        seen.add(name)
        vals = [r.get(name) for r in rows if isinstance(r, dict)]
        fields.append({"name": name, "type": infer_type(vals), "description": "", "required": False})
    return {"fields": fields[:80]}


def coerce_records(records: Sequence[Any], schema: Any) -> Tuple[List[Any], Dict[str, int]]:
    """Converte cada valor ao tipo do schema. O que não converte fica como estava (contado em `failed`)."""
    types = {f["name"]: f.get("type", "text") for f in ((schema or {}).get("fields") or []) if isinstance(f, dict) and f.get("name")}
    changed = failed = 0
    out: List[Any] = []
    for r in records:
        if not isinstance(r, dict):
            out.append(r)
            continue
        row = dict(r)
        for k, ft in types.items():
            if k not in row or ft not in FIELD_TYPES:
                continue
            nv, ok = coerce_value(row[k], ft)
            if not ok:
                failed += 1
            elif nv != row[k] or type(nv) is not type(row[k]):
                row[k] = nv
                changed += 1
        out.append(row)
    return out, {"changed": changed, "failed": failed}


def clean(records: Sequence[Any], schema: Any = None, *, trim: bool = True, coerce: bool = True, drop_empty_rows: bool = True, drop_empty_columns: bool = False) -> Tuple[List[Any], Dict[str, Any], Dict[str, int]]:
    """Limpeza segura: tira espaços das pontas e repetidos, converte tipos, remove linhas totalmente vazias (e, se pedido, colunas sem nenhum valor).
    Devolve (registros, schema, contagens)."""
    stats = {"trimmed": 0, "converted": 0, "failed": 0, "rows_removed": 0, "columns_removed": 0}
    rows: List[Any] = []
    for r in records:
        if isinstance(r, dict):
            row = {}
            for k, v in r.items():
                if trim and isinstance(v, str):
                    nv = " ".join(v.split()) if "\n" not in v else v.strip()
                    if nv != v:
                        stats["trimmed"] += 1
                    v = nv
                row[k] = v
            if drop_empty_rows and all(quality._is_blank(v) for v in row.values()):
                stats["rows_removed"] += 1
                continue
            rows.append(row)
        else:
            rows.append(r)
    sch = schema if isinstance(schema, dict) else {"fields": []}
    if coerce:
        sch = infer_schema(rows, sch) if not (sch.get("fields")) else sch
        rows, st = coerce_records(rows, sch)
        stats["converted"], stats["failed"] = st["changed"], st["failed"]
    if drop_empty_columns:
        cols = quality.columns(rows, sch)
        empty = {c for c in cols if all(quality._is_blank(r.get(c)) for r in rows if isinstance(r, dict))} if rows else set()
        if empty:
            stats["columns_removed"] = len(empty)
            rows = [{k: v for k, v in r.items() if k not in empty} if isinstance(r, dict) else r for r in rows]
            sch = {"fields": [f for f in sch.get("fields", []) if f.get("name") not in empty]}
    return rows, sch, stats


def fill_missing(records: Sequence[Any], schema: Any = None, strategy: str = "auto", fields: Optional[Sequence[str]] = None, constant: Any = None) -> Tuple[List[Any], Dict[str, Any]]:
    """Preenche vazios com um valor **calculado dos próprios dados**: `auto` (número → mediana; o resto → valor mais comum), `median`, `mean`, `mode` ou `constant`.
    Colunas sem nenhum valor não têm de onde calcular e ficam como estão (listadas em `skipped`)."""
    recs = [dict(r) if isinstance(r, dict) else r for r in records]
    cols = [c for c in quality.columns(recs, schema) if not fields or c in fields]
    filled: Dict[str, int] = {}
    skipped: List[str] = []
    for c in cols:
        vals = [r.get(c) for r in recs if isinstance(r, dict) and not quality._is_blank(r.get(c))]
        missing = [r for r in recs if isinstance(r, dict) and quality._is_blank(r.get(c))]
        if not missing:
            continue
        nums = [float(v) for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        numeric = bool(vals) and len(nums) == len(vals)
        if strategy == "constant":
            fill = constant
        elif not vals:
            skipped.append(c)
            continue
        elif (strategy in ("auto", "median") and numeric) or (strategy == "median" and numeric):
            s = sorted(nums)
            mid = len(s) // 2
            fill = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
            if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
                fill = int(round(fill))
        elif strategy == "mean" and numeric:
            fill = sum(nums) / len(nums)
        else:
            fill = Counter(quality._dump(v) for v in vals).most_common(1)[0][0]
            try:
                fill = json.loads(fill)
            except ValueError:
                pass
        for r in missing:
            r[c] = fill
        filled[c] = len(missing)
    return recs, {"filled": filled, "total": sum(filled.values()), "skipped": skipped}


# ----------------------------------------------------------------------------- colunas e células
def column_op(records: Sequence[Any], schema: Any, op: str, name: str, new_name: str = "", ftype: str = "text", default: Any = None) -> Tuple[List[Any], Dict[str, Any]]:
    """add | rename | remove | retype uma coluna: schema e registros mudam juntos."""
    sch = {"fields": [dict(f) for f in ((schema or {}).get("fields") or []) if isinstance(f, dict)]}
    name = str(name or "").strip().replace(" ", "_")[:60]
    if not name:
        raise ValueError("Informe o nome da coluna.")
    names = [f["name"] for f in sch["fields"]]
    recs = [dict(r) if isinstance(r, dict) else r for r in records]
    if ftype not in FIELD_TYPES:
        ftype = "text"
    if op == "add":
        if name in names:
            raise ValueError("Já existe uma coluna com esse nome.")
        sch["fields"].append({"name": name, "type": ftype, "description": "", "required": False})
        if default is not None:
            for r in recs:
                if isinstance(r, dict):
                    r.setdefault(name, default)
    elif op == "rename":
        nn = str(new_name or "").strip().replace(" ", "_")[:60]
        if not nn:
            raise ValueError("Informe o novo nome.")
        if nn in names and nn != name:
            raise ValueError("Já existe uma coluna com esse nome.")
        for f in sch["fields"]:
            if f["name"] == name:
                f["name"] = nn
        for r in recs:
            if isinstance(r, dict) and name in r:
                r[nn] = r.pop(name)
    elif op == "remove":
        sch["fields"] = [f for f in sch["fields"] if f["name"] != name]
        for r in recs:
            if isinstance(r, dict):
                r.pop(name, None)
    elif op == "retype":
        for f in sch["fields"]:
            if f["name"] == name:
                f["type"] = ftype
        recs, st = coerce_records(recs, {"fields": [{"name": name, "type": ftype}]})
        return recs, {"schema": sch, **st}
    else:
        raise ValueError("Operação de coluna inválida.")
    return recs, {"schema": sch}


def apply_edits(records: Sequence[Any], edits: Any) -> Tuple[List[Any], Dict[str, int]]:
    """Edições vindas da grade da tela, com índices do estado que ela viu: `set` (célula), `delete` (linhas), `insert` (linha nova no fim ou antes de `i`). Ordem segura: sets → deletes → inserts."""
    if not isinstance(edits, list):
        raise ValueError("Envie a lista de edições.")
    edits = edits[:MAX_EDITS]
    recs = [dict(r) if isinstance(r, dict) else {"value": r} for r in records]
    n = len(recs)
    sets = deletes = inserts = 0
    for e in edits:
        if isinstance(e, dict) and e.get("op") == "set" and isinstance(e.get("i"), int) and 0 <= e["i"] < n and isinstance(e.get("field"), str) and e["field"]:
            recs[e["i"]][e["field"][:80]] = e.get("value")
            sets += 1
    gone = set()
    for e in edits:
        if isinstance(e, dict) and e.get("op") == "delete":
            for i in (e.get("i") if isinstance(e.get("i"), list) else [e.get("i")]):
                if isinstance(i, int) and 0 <= i < n:
                    gone.add(i)
    ins = [e for e in edits if isinstance(e, dict) and e.get("op") == "insert"]
    out = [r for i, r in enumerate(recs) if i not in gone]
    deletes = len(gone)
    remap = {}
    k = 0
    for i in range(n):
        if i not in gone:
            remap[i] = k
            k += 1
    for e in ins:
        row = e.get("record") if isinstance(e.get("record"), dict) else {}
        pos = e.get("i")
        at = remap.get(pos, len(out)) if isinstance(pos, int) else len(out)
        out.insert(at, dict(row))
        for kk, vv in list(remap.items()):
            if vv >= at:
                remap[kk] = vv + 1
        inserts += 1
    return out, {"set": sets, "deleted": deletes, "inserted": inserts}


# ----------------------------------------------------------------------------- consulta paginada
def _cell_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _sort_key(v: Any) -> Tuple[int, Any]:
    if v is None or (isinstance(v, str) and not v.strip()):
        return (2, 0)          # vazios sempre no fim
    if isinstance(v, bool):
        return (1, str(v))
    if isinstance(v, (int, float)):
        return (0, float(v))
    s = _cell_text(v)
    try:
        return (0, float(s))
    except ValueError:
        return (1, s.lower())


def query(records: Sequence[Any], q: str = "", sort: str = "", direction: str = "asc", offset: int = 0, limit: int = 100, where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Uma página dos registros (`rows`: `{"i": posição original, "r": registro}`), com busca em todos os campos, filtro por campo (`where`) e ordenação por uma coluna.
    A posição original (`i`) é o que a grade devolve nas edições, então a ordenação da tela nunca embaralha o que é salvo."""
    limit = max(1, min(int(limit or 100), MAX_PAGE))
    offset = max(0, int(offset or 0))
    needle = str(q or "").strip().lower()
    idx = list(range(len(records)))
    if where and isinstance(where, dict):
        wh = {str(k): str(v).lower() for k, v in where.items() if str(v).strip()}
        if wh:
            idx = [i for i in idx if isinstance(records[i], dict) and all(w in _cell_text(records[i].get(k)).lower() for k, w in wh.items())]
    if needle:
        idx = [i for i in idx if needle in _cell_text(records[i]).lower()]
    if sort:
        rev = str(direction).lower() == "desc"
        keyed = [(_sort_key(records[i].get(sort) if isinstance(records[i], dict) else None), i) for i in idx]
        blanks = [x for x in keyed if x[0][0] == 2]
        rest = sorted([x for x in keyed if x[0][0] != 2], key=lambda x: (x[0], x[1]), reverse=rev)
        idx = [i for _, i in rest + blanks]
    page = idx[offset:offset + limit]
    return {"total": len(records), "matched": len(idx), "offset": offset, "limit": limit, "rows": [{"i": i, "r": records[i]} for i in page]}


# ----------------------------------------------------------------------------- mesclagem
def _union_schema(a: Any, b: Any) -> Dict[str, Any]:
    fields = [dict(f) for f in ((a or {}).get("fields") or []) if isinstance(f, dict)]
    have = {f.get("name") for f in fields}
    for f in ((b or {}).get("fields") or []) if isinstance(b, dict) else []:
        if isinstance(f, dict) and f.get("name") and f["name"] not in have:
            have.add(f["name"])
            fields.append(dict(f))
    return {"fields": fields[:120]}


def merge(target: Sequence[Any], source: Sequence[Any], target_schema: Any, source_schema: Any, strategy: str = "append", keys: Any = None, conflict: str = "keep_target", dedupe: bool = False) -> Dict[str, Any]:
    """Estratégias: `append` (junta tudo) · `upsert` (registros com a mesma chave são combinados; `conflict`: `keep_target` só preenche vazios do destino, `prefer_source` a origem vence;
    os sem par entram no fim). `dedupe` remove repetidos no final. O schema é a união pelo nome do campo (o destino vence). Devolve `records`, `schema` e as contagens."""
    sch = _union_schema(target_schema, source_schema)
    recs = [dict(r) if isinstance(r, dict) else {"value": r} for r in target]
    added = updated = skipped = 0
    if strategy == "upsert":
        cols = [c["name"] for c in sch["fields"]]
        ks = [k for k in (keys if isinstance(keys, list) else []) if isinstance(k, str) and k in cols]
        if not ks:
            raise ValueError("Escolha ao menos um campo-chave existente para combinar por chave.")

        def sig(r: Dict[str, Any]) -> Optional[str]:
            vals = [quality._norm(r.get(k), True) for k in ks]
            return None if all(quality._is_blank(v) for v in vals) else quality._dump(vals)

        index: Dict[str, int] = {}
        for i, r in enumerate(recs):
            s = sig(r)
            if s is not None:
                index.setdefault(s, i)
        for sr in source:
            row = dict(sr) if isinstance(sr, dict) else {"value": sr}
            s = sig(row)
            if s is not None and s in index:
                tr = recs[index[s]]
                changed = False
                for k, v in row.items():
                    if quality._is_blank(v):
                        continue
                    if quality._is_blank(tr.get(k)) or (conflict == "prefer_source" and tr.get(k) != v):
                        tr[k] = v
                        changed = True
                if changed:
                    updated += 1
                else:
                    skipped += 1
            else:
                recs.append(row)
                if s is not None:
                    index[s] = len(recs) - 1
                added += 1
    else:
        for sr in source:
            recs.append(dict(sr) if isinstance(sr, dict) else {"value": sr})
            added += 1
    removed = 0
    if dedupe:
        dd = quality.dedupe(recs, sch)
        recs, removed = dd["kept"], len(dd["removed"])
    return {"records": recs, "schema": sch, "added": added, "updated": updated, "skipped": skipped, "duplicates_removed": removed, "total": len(recs)}
