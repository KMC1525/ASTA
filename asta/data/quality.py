"""Qualidade dos dados do modo Data (v0.23): **perfil** das colunas e **remoção de duplicados**.

Desenho em três passos, sem IA (rápido, repetível, funciona offline): planejar (quais campos valem como chave) → fazer (agrupar e contar) → conferir (a conta fecha:
mantidos + removidos = total; todo removido é igual ao que ficou). Nada é apagado aqui: `dedupe` só **calcula** — quem grava (e só depois da prévia) é o `DataManager`.
Os resultados trazem *códigos* de achados (`empty_column`, `duplicates`…) e números; a tela escreve as frases (e as traduz).
"""

from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any, Dict, List, Sequence, Tuple

MAX_KEYS = 50
TOP = 5
#: campos que identificam o registro mas não o conteúdo: ficam fora da comparação de duplicados (a menos que o usuário os escolha como chave)
ID_FIELDS = ("id", "_id", "uuid")
MAX_DISTINCT_TRACKED = 20000


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v == [] or v == {}


def _type_of(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "text"
    if isinstance(v, list):
        return "list"
    return "object"


def _norm(v: Any, ignore_case: bool) -> Any:
    """Forma comparável: texto sem espaços sobrando (e sem diferença de maiúsculas, se pedido); números iguais valem iguais (1 == 1.0)."""
    if isinstance(v, str):
        s = " ".join(v.split())
        return s.lower() if ignore_case else s
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(float(v)) else str(v)
    if isinstance(v, list):
        return [_norm(x, ignore_case) for x in v]
    if isinstance(v, dict):
        return {str(k): _norm(x, ignore_case) for k, x in v.items()}
    return str(v)


def _dump(v: Any) -> str:
    try:
        return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(v)


def columns(records: Sequence[Any], schema: Any = None) -> List[str]:
    """Os campos do schema (na ordem dele) seguidos dos que só aparecem nos registros."""
    cols: List[str] = []
    seen = set()
    fields = (schema or {}).get("fields") if isinstance(schema, dict) else None
    for f in fields if isinstance(fields, list) else []:
        name = f.get("name") if isinstance(f, dict) else None
        if isinstance(name, str) and name and name not in seen:
            seen.add(name)
            cols.append(name)
    for r in records:
        if isinstance(r, dict):
            for k in r:
                if k not in seen:
                    seen.add(k)
                    cols.append(str(k))
    return cols


def _declared(schema: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    fields = (schema or {}).get("fields") if isinstance(schema, dict) else None
    for f in fields if isinstance(fields, list) else []:
        if isinstance(f, dict) and isinstance(f.get("name"), str):
            out[f["name"]] = str(f.get("type") or "text")
    return out


# ----------------------------------------------------------------------------- duplicados

def resolve_keys(records: Sequence[Any], schema: Any, keys: Any) -> List[str]:
    """Passo 1 (planejar): os campos que decidem se dois registros são o mesmo. Sem escolha: todos, menos os de identificação (`id`…). Nomes que não existem são ignorados."""
    cols = columns(records, schema)
    if isinstance(keys, (list, tuple)):
        chosen = [str(k) for k in keys if isinstance(k, str)][:MAX_KEYS]
        chosen = [k for k in dict.fromkeys(chosen) if k in cols]
        if chosen:
            return chosen
    return [c for c in cols if c.lower() not in ID_FIELDS] or cols


def dedupe(records: Sequence[Any], schema: Any = None, keys: Any = None, ignore_case: bool = True) -> Dict[str, Any]:
    """Calcula (sem gravar) quais registros são repetidos: o **primeiro** de cada grupo fica. Devolve `kept` (registros), `removed` (posições originais),
    `groups` (`{"keep": posição, "dups": [posições]}`), os `keys` usados, `skipped_blank` (registros sem nenhum valor nos campos-chave: nunca são removidos) e `checks`."""
    recs = list(records)
    use = resolve_keys(recs, schema, keys)
    first: Dict[str, int] = {}
    dups: Dict[int, List[int]] = {}
    removed: List[int] = []
    skipped = 0
    for i, r in enumerate(recs):
        row = r if isinstance(r, dict) else {"value": r}
        vals = [_norm(row.get(k), ignore_case) for k in use]
        if all(_is_blank(v) for v in vals):
            skipped += 1
            continue
        sig = _dump(vals)
        j = first.setdefault(sig, i)
        if j != i:
            removed.append(i)
            dups.setdefault(j, []).append(i)
    gone = set(removed)
    kept = [r for i, r in enumerate(recs) if i not in gone]
    groups = [{"keep": k, "dups": v} for k, v in sorted(dups.items())]
    # passo 3 (conferir): a conta fecha e cada removido é de fato igual ao que ficou no lugar dele
    same = all(_dump([_norm((recs[d] if isinstance(recs[d], dict) else {"value": recs[d]}).get(k), ignore_case) for k in use])
               == _dump([_norm((recs[g["keep"]] if isinstance(recs[g["keep"]], dict) else {"value": recs[g["keep"]]}).get(k), ignore_case) for k in use])
               for g in groups for d in g["dups"])
    checks = {"total_ok": len(kept) + len(removed) == len(recs), "equal_ok": same, "order_ok": removed == sorted(removed)}
    checks["ok"] = all(checks.values())
    return {"kept": kept, "removed": removed, "groups": groups, "keys": use, "skipped_blank": skipped, "ignore_case": bool(ignore_case), "checks": checks}


# ----------------------------------------------------------------------------- perfil

def profile(records: Sequence[Any], schema: Any = None) -> Dict[str, Any]:
    """O retrato do conjunto: por coluna, quantos valores há/faltam/são distintos, tipos vistos, valores mais comuns e (para números e textos) intervalos. Mais os achados
    (`issues`: `empty_column`, `constant_column`, `mixed_types`, `type_mismatch`, `sparse_column`, `duplicates`, `no_records`)."""
    recs = list(records)
    cols = columns(recs, schema)
    declared = _declared(schema)
    out_cols: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    n = len(recs)
    for c in cols:
        types: Counter = Counter()
        filled = 0
        distinct: Counter = Counter()
        nums: List[float] = []
        lens: List[int] = []
        tracked_full = True
        for r in recs:
            v = r.get(c) if isinstance(r, dict) else None
            if _is_blank(v):
                continue
            filled += 1
            t = _type_of(v)
            types[t] += 1
            if t in ("integer", "number") and math.isfinite(float(v)):
                nums.append(float(v))
            if t == "text":
                lens.append(len(v))
            key = _dump(v)[:200]
            if key in distinct or len(distinct) < MAX_DISTINCT_TRACKED:
                distinct[key] += 1
            else:
                tracked_full = False
        col: Dict[str, Any] = {"name": c, "declared": declared.get(c, ""), "filled": filled, "missing": n - filled, "distinct": len(distinct), "distinct_exact": tracked_full,
                               "types": dict(types), "top": [{"value": _show(k), "count": cnt} for k, cnt in distinct.most_common(TOP)]}
        if nums:
            col["min"], col["max"], col["mean"] = min(nums), max(nums), round(sum(nums) / len(nums), 6)
        if lens:
            col["len_min"], col["len_max"] = min(lens), max(lens)
        out_cols.append(col)
        if n and filled == 0:
            issues.append({"code": "empty_column", "field": c})
        elif n > 1 and col["distinct"] == 1 and filled == n:
            issues.append({"code": "constant_column", "field": c})
        elif n >= 5 and filled / n < 0.5:
            issues.append({"code": "sparse_column", "field": c, "filled": filled, "total": n})
        if len([t for t in types if t not in ("integer", "number")]) + (1 if ("integer" in types or "number" in types) else 0) > 1:
            issues.append({"code": "mixed_types", "field": c, "types": sorted(types)})
        d = declared.get(c, "")
        if d in ("number", "integer") and any(t not in ("integer", "number") for t in types):
            issues.append({"code": "type_mismatch", "field": c, "declared": d})
        elif d == "boolean" and any(t != "boolean" for t in types):
            issues.append({"code": "type_mismatch", "field": c, "declared": d})
    if not n:
        issues.append({"code": "no_records"})
    dd = dedupe(recs, schema) if n else {"removed": []}
    if dd["removed"]:
        issues.append({"code": "duplicates", "count": len(dd["removed"])})
    return {"records": n, "columns": out_cols, "duplicates": len(dd["removed"]), "issues": issues}


def _show(key: str) -> Any:
    try:
        v = json.loads(key)
    except ValueError:
        return key
    return v if not isinstance(v, (dict, list)) else key


def summary_line(p: Dict[str, Any]) -> Tuple[int, int, int]:
    """(registros, colunas, achados) — para listas e logs."""
    return int(p.get("records") or 0), len(p.get("columns") or []), len(p.get("issues") or [])
