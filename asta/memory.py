"""Memória unificada universal do ASTA (v0.21).

Registra, em JSON aberto e editável, o que é feito dentro do ASTA (Chat,
Avatars, Canvas, Studio, Scriber, Game Engine, Code, Work, Computer Use,
arquivos, configurações etc.), para que o contexto possa ser retomado depois.

Organização em pastas: `~/.asta/memory/AAAA/MM/semana-SS/AAAA-MM-DD.json`
(ano, mês, semana ISO e dia) — fácil de abrir, copiar e editar à mão ou pela
WebUI. Nada sai do computador; os dados são do usuário.
"""
from __future__ import annotations

import copy
import datetime
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .util import new_id, now_iso, read_json, text, write_json

SCHEMA_DAY = "asta.memory.day.v1"
_MAX_ITEMS_DAY = 5000  # proteção: um dia anormalmente barulhento não cria arquivo infinito
_LOCK = threading.RLock()


def _dt(ts: Optional[str] = None) -> datetime.datetime:
    if ts:
        try:
            return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone()
        except ValueError:
            pass
    return datetime.datetime.now().astimezone()


def day_parts(ts: Optional[str] = None) -> Tuple[str, str, str, str]:
    """(ano, mes, semana-SS, dia) — pastas ano/mês/semana e nome do arquivo do dia."""
    d = _dt(ts)
    iso_year, iso_week, _ = d.isocalendar()
    return f"{d.year:04d}", f"{d.month:02d}", f"semana-{iso_week:02d}", d.strftime("%Y-%m-%d")


def day_path(root: Path, ts: Optional[str] = None) -> Path:
    y, m, w, day = day_parts(ts)
    return root / y / m / w / f"{day}.json"


def _load_day(path: Path) -> Dict[str, Any]:
    data = read_json(path, None)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        # tenta também migrar arquivo antigo se alguém editar manualmente para lista pura
        if isinstance(data, list):
            items = [x for x in data if isinstance(x, dict)]
            day = path.stem
            return {"schema": SCHEMA_DAY, "date": day, "items": items}
        return {"schema": SCHEMA_DAY, "date": path.stem, "items": []}
    out = {"schema": SCHEMA_DAY, "date": text(data.get("date"), path.stem, 20), "items": [x for x in data["items"] if isinstance(x, dict)]}
    return out


def _save_day(path: Path, doc: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, doc, private=True)


def normalize_item(data: Any) -> Dict[str, Any]:
    d = data if isinstance(data, dict) else {}
    ts = text(d.get("ts"), "", 40) or now_iso()
    detail = d.get("detail")
    if not isinstance(detail, dict):
        detail = {"text": text(detail, "", 8000)} if detail not in (None, "") else {}
    tags = [text(t, "", 40) for t in (d.get("tags") or []) if str(t).strip()][:20] if isinstance(d.get("tags"), list) else []
    return {
        "id": text(d.get("id"), "", 60) or new_id("m_"),
        "ts": ts,
        "section": text(d.get("section"), "asta", 40),
        "action": text(d.get("action"), "event", 60),
        "title": text(d.get("title"), "", 200),
        "summary": text(d.get("summary"), "", 2000),
        "detail": detail,
        "tags": tags,
    }


def record(root: Path, section: str, action: str, title: str = "", summary: str = "", detail: Any = None, tags: Optional[List[str]] = None, ts: Optional[str] = None) -> Dict[str, Any]:
    """Acrescenta uma memória. Seguro para chamar de várias threads."""
    item = normalize_item({"ts": ts or now_iso(), "section": section, "action": action, "title": title, "summary": summary, "detail": detail or {}, "tags": tags or []})
    path = day_path(root, item["ts"])
    with _LOCK:
        doc = _load_day(path)
        doc["items"].append(item)
        if len(doc["items"]) > _MAX_ITEMS_DAY:
            doc["items"] = doc["items"][-_MAX_ITEMS_DAY:]
        doc["date"] = path.stem
        _save_day(path, doc)
    return item


def _iter_day_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    # YYYY/MM/semana-WW/YYYY-MM-DD.json
    return sorted(root.glob("*/*/semana-*/*.json"))


def list_days(root: Path, limit: int = 400) -> List[Dict[str, Any]]:
    """Dias que têm memória (mais recentes primeiro), com contagem."""
    days: List[Dict[str, Any]] = []
    files = list(_iter_day_files(root))
    for p in reversed(files):
        doc = _load_day(p)
        parts = day_parts(doc.get("date") or p.stem)
        days.append({"date": p.stem, "year": parts[0], "month": parts[1], "week": parts[2], "path": str(p.relative_to(root)) if _is_under(p, root) else str(p), "count": len(doc.get("items") or []), "items": None})
        if len(days) >= limit:
            break
    return days


def _is_under(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def read_day(root: Path, date: str) -> Optional[Dict[str, Any]]:
    date = text(date, "", 20)
    if not re_date(date):
        return None
    path = _find_day(root, date)
    if path is None:
        # calcula caminho esperado
        try:
            d = datetime.date.fromisoformat(date)
            path = day_path(root, datetime.datetime(d.year, d.month, d.day).isoformat())
        except ValueError:
            return None
    doc = _load_day(path)
    doc["date"] = date
    doc["path"] = str(path.relative_to(root)) if path.exists() and _is_under(path, root) else ""
    return doc


def re_date(s: str) -> bool:
    import re

    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s or ""))


def _find_day(root: Path, date: str) -> Optional[Path]:
    # procura pelo nome do arquivo em qualquer semana (a semana pode mudar se alguém mover)
    found = list(root.glob(f"*/*/semana-*/{date}.json"))
    if found:
        return found[0]
    try:
        d = datetime.date.fromisoformat(date)
        p = day_path(root, datetime.datetime(d.year, d.month, d.day).isoformat())
        return p if p.exists() else (found[0] if found else None)
    except ValueError:
        return None


def write_day(root: Path, date: str, doc: Any) -> Dict[str, Any]:
    if not re_date(date):
        raise ValueError("Data inválida")
    items = []
    if isinstance(doc, dict):
        raw = doc.get("items")
        items = raw if isinstance(raw, list) else []
    elif isinstance(doc, list):
        items = doc
    cleaned = [normalize_item(x) for x in items][: _MAX_ITEMS_DAY]
    out = {"schema": SCHEMA_DAY, "date": date, "items": cleaned}
    path = _find_day(root, date)
    if path is None:
        try:
            d = datetime.date.fromisoformat(date)
            path = day_path(root, datetime.datetime(d.year, d.month, d.day).isoformat())
        except ValueError as exc:
            raise ValueError("Data inválida") from exc
    with _LOCK:
        _save_day(path, out)
    out["path"] = str(path.relative_to(root)) if _is_under(path, root) else ""
    return out


def update_item(root: Path, date: str, item_id: str, patch: Any) -> Dict[str, Any]:
    path = _find_day(root, date)
    if path is None or not path.exists():
        raise ValueError("Dia não encontrado")
    with _LOCK:
        doc = _load_day(path)
        items = doc.get("items") or []
        for i, it in enumerate(items):
            if str(it.get("id")) == str(item_id):
                if not isinstance(patch, dict):
                    raise ValueError("Item inválido")
                merged = copy.deepcopy(it)
                for k in ("section", "action", "title", "summary", "detail", "tags", "ts"):
                    if k in patch:
                        merged[k] = patch[k]
                items[i] = normalize_item(merged)
                doc["items"] = items
                _save_day(path, doc)
                return items[i]
    raise ValueError("Memória não encontrada")


def delete_item(root: Path, date: str, item_id: str) -> bool:
    path = _find_day(root, date)
    if path is None or not path.exists():
        return False
    with _LOCK:
        doc = _load_day(path)
        items = doc.get("items") or []
        new_items = [it for it in items if str(it.get("id")) != str(item_id)]
        if len(new_items) == len(items):
            return False
        doc["items"] = new_items
        _save_day(path, doc)
    return True


def search(root: Path, query: str = "", section: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    q = (query or "").strip().lower()
    sec = (section or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for p in reversed(list(_iter_day_files(root))):
        doc = _load_day(p)
        for it in reversed(doc.get("items") or []):
            if sec and str(it.get("section", "")).lower() != sec:
                continue
            if q:
                hay = " ".join([str(it.get("title", "")), str(it.get("summary", "")), str(it.get("action", "")), str(it.get("section", ""))]).lower()
                if q not in hay:
                    # tenta detalhe texto
                    det = it.get("detail")
                    if not (isinstance(det, dict) and q in str(det.get("text", "")).lower()):
                        continue
            x = copy.deepcopy(it)
            x["date"] = p.stem
            out.append(x)
            if len(out) >= limit:
                return out
    return out


def sections(root: Path) -> List[str]:
    seen = set()
    for p in _iter_day_files(root):
        for it in (_load_day(p).get("items") or [])[-200:]:
            s = str(it.get("section") or "").strip()
            if s:
                seen.add(s)
    return sorted(seen)
