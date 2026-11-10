"""Scriber — lorebooks: livros de contexto, no estilo dos *system prompts*, que ficam ao lado do texto e entram nas chamadas da IA.

Um **livro** (`{id, name, enabled, entries}`) guarda **entradas** (`{id, name, kind, keys, content, enabled, always, priority}`):
  • `kind`: `system` (regras de estilo e de voz: valem sempre, vão primeiro, como um system prompt), `character`, `place`, `world`, `rule`, `plot`, `note`.
  • `always` — a entrada entra em toda chamada; senão só entra quando uma das `keys` (ou o nome) aparece no trecho que a IA está lendo (como o World Info do SillyTavern).
  • `priority` (0–100) decide a ordem e quem sobra quando o orçamento de texto acaba.

Importa e exporta JSON aberto (`asta.lorebook`), lê o formato World Info / Character Book do SillyTavern e Markdown (cada «## título» vira uma entrada)."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..util import new_id, text

KINDS = ("system", "character", "place", "world", "rule", "plot", "note")
MAX_BOOKS = 40
MAX_ENTRIES = 400
MAX_CONTENT = 8000
BUDGET = 7000   # caracteres de lore por chamada
ORDER = {k: i for i, k in enumerate(KINDS)}


def norm_entry(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    content = text(raw["content"], "", MAX_CONTENT) if isinstance(raw.get("content"), str) else ""
    name = text(raw["name"], "", 80) if isinstance(raw.get("name"), str) else ""
    if not content and not name:
        return None
    keys_raw = raw.get("keys") if isinstance(raw.get("keys"), list) else (re.split(r"[,;\n]", raw["keys"]) if isinstance(raw.get("keys"), str) else [])
    keys: List[str] = []
    for k in keys_raw:
        k = text(k, "", 60)
        if k and k.lower() not in (x.lower() for x in keys):
            keys.append(k)
    pr = raw.get("priority")
    pr = int(max(0, min(100, pr))) if isinstance(pr, (int, float)) and not isinstance(pr, bool) else 50
    eid = raw.get("id") if isinstance(raw.get("id"), str) and re.match(r"^[\w-]{3,40}$", raw.get("id")) else new_id("e_")
    return {"id": eid, "name": name or content[:40], "kind": raw.get("kind") if isinstance(raw.get("kind"), str) and raw.get("kind") in KINDS else "note",
            "keys": keys[:20], "content": content, "enabled": raw.get("enabled") is not False, "always": bool(raw.get("always")), "priority": pr}


def norm_book(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    entries: List[Dict[str, Any]] = []
    ids = set()
    for e in raw.get("entries") if isinstance(raw.get("entries"), list) else []:
        n = norm_entry(e)
        if n and len(entries) < MAX_ENTRIES:
            while n["id"] in ids:
                n["id"] = new_id("e_")
            ids.add(n["id"])
            entries.append(n)
    bid = raw.get("id") if isinstance(raw.get("id"), str) and re.match(r"^[\w-]{3,40}$", raw.get("id")) else new_id("b_")
    return {"id": bid, "name": text(raw.get("name"), "Lorebook", 80), "enabled": raw.get("enabled") is not False, "entries": entries}


def norm_books(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    ids = set()
    for b in raw if isinstance(raw, list) else []:
        n = norm_book(b)
        if n and len(out) < MAX_BOOKS:
            while n["id"] in ids:
                n["id"] = new_id("b_")
            ids.add(n["id"])
            out.append(n)
    return out


def _hit(keys: List[str], haystack: str) -> bool:
    for k in keys:
        if not k:
            continue
        if re.search(r"(?<![\w])" + re.escape(k) + r"(?![\w])", haystack, re.I | re.U):
            return True
    return False


def select(books: List[Dict[str, Any]], context: str, budget: int = BUDGET, only: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """As entradas que valem para este `context` (o texto que a IA vai ler): sempre-ligadas + as com palavra-chave presente, em ordem de tipo e prioridade, dentro do orçamento."""
    chosen: List[Dict[str, Any]] = []
    ctx = context or ""
    for b in books:
        if not b.get("enabled", True) or (only is not None and b.get("id") not in only):
            continue
        for e in b.get("entries", []):
            if not e.get("enabled", True) or not e.get("content"):
                continue
            if e.get("kind") == "system" or e.get("always") or _hit(list(e.get("keys", [])) + [e.get("name", "")] if e.get("kind") != "system" else [], ctx):
                chosen.append(dict(e, book=b.get("name", "")))
    chosen.sort(key=lambda e: (ORDER.get(e["kind"], 9), -e.get("priority", 50)))
    out, used = [], 0
    for e in chosen:
        size = len(e["content"]) + len(e["name"]) + 8
        if used + size > budget:
            if e["kind"] == "system" and not out:   # a primeira regra de estilo nunca fica de fora: entra cortada
                e = dict(e, content=e["content"][: max(200, budget - 100)])
                out.append(e)
                used += len(e["content"])
            continue
        out.append(e)
        used += size
    return out


def render(entries: List[Dict[str, Any]]) -> str:
    """O bloco de texto que vai para a IA. Vazio se não há nada."""
    if not entries:
        return ""
    rules = [e for e in entries if e["kind"] == "system"]
    canon = [e for e in entries if e["kind"] != "system"]
    parts: List[str] = []
    if rules:
        parts.append("AUTHOR'S STYLE & RULES (system-level instructions from the author; always follow them):\n" + "\n".join(f"- {e['name']}: {e['content']}" for e in rules))
    if canon:
        parts.append("LOREBOOK (canon established by the author; stay consistent with it and never contradict it):\n" + "\n".join(f"[{e['kind']}] {e['name']}: {e['content']}" for e in canon))
    return "\n\n".join(parts)


def lore_for(books: List[Dict[str, Any]], context: str, enabled: bool = True, only: Optional[List[str]] = None, budget: int = BUDGET) -> Dict[str, Any]:
    if not enabled:
        return {"text": "", "used": []}
    ents = select(books, context, budget, only)
    return {"text": render(ents), "used": [{"id": e["id"], "name": e["name"], "kind": e["kind"], "book": e.get("book", "")} for e in ents]}


# ---------------------------------------------------------------------------------------------------- importar / exportar
def export_book(book: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "asta.lorebook", "version": 1, "name": book.get("name", ""), "entries": [{k: e[k] for k in ("name", "kind", "keys", "content", "enabled", "always", "priority")} for e in book.get("entries", [])]}


def book_to_markdown(book: Dict[str, Any]) -> str:
    out = [f"# {book.get('name', 'Lorebook')}", ""]
    for e in book.get("entries", []):
        out += [f"## {e['name']}", f"<!-- kind: {e['kind']}; keys: {', '.join(e['keys'])}; always: {str(e['always']).lower()} -->", "", e["content"], ""]
    return "\n".join(out)


def import_any(data: Any, name: str = "") -> Dict[str, Any]:
    """JSON do ASTA, World Info / Character Book do SillyTavern (ou uma lista de entradas) ou Markdown/texto → um livro válido. Levanta ValueError se não achar nada."""
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "replace")
    if isinstance(data, str):
        s = data.strip().lstrip("﻿")
        if s[:1] in "{[":
            try:
                data = json.loads(s)
            except (ValueError, RecursionError):
                data = s
        if isinstance(data, str):
            return _from_markdown(data, name)
    entries_raw: Any = None
    title = name
    if isinstance(data, dict):
        title = text(data.get("name"), name, 80) or name
        if isinstance(data.get("character_book"), dict):
            data = data["character_book"]
            title = text(data.get("name"), title, 80) or title
        entries_raw = data.get("entries")
        if entries_raw is None and isinstance(data.get("books"), list) and data["books"]:
            return norm_book(data["books"][0]) or _fail()
    elif isinstance(data, list):
        entries_raw = data
    if isinstance(entries_raw, dict):   # World Info do SillyTavern: {"0": {...}, "1": {...}}
        entries_raw = [v for _, v in sorted(entries_raw.items(), key=lambda kv: (len(str(kv[0])), str(kv[0]))) if isinstance(v, dict)]
    if not isinstance(entries_raw, list):
        _fail()
    entries = []
    for e in entries_raw[:MAX_ENTRIES]:
        if not isinstance(e, dict):
            continue
        keys = e.get("keys") if e.get("keys") is not None else e.get("key")
        content = e.get("content") if e.get("content") is not None else e.get("text")
        nm = e.get("name") or e.get("comment") or e.get("title") or ""
        disabled = e.get("disable") is True or e.get("enabled") is False
        entries.append({"name": nm, "kind": e.get("kind") if e.get("kind") in KINDS else "note", "keys": keys if keys is not None else [], "content": content or "",
                        "enabled": not disabled, "always": bool(e.get("always") or e.get("constant")), "priority": e.get("priority", e.get("order", e.get("insertion_order", 50)))})
    book = norm_book({"name": title or "Lorebook", "entries": entries})
    if not book or not book["entries"]:
        _fail()
    return book


def _fail() -> Any:
    raise ValueError("Não encontrei entradas de lorebook nesse arquivo.")


def _from_markdown(md: str, name: str) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    title = name
    cur: Optional[Dict[str, Any]] = None
    for line in md.replace("\r\n", "\n").split("\n"):
        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h and len(h.group(1)) == 1 and not title and not entries and cur is None:
            title = h.group(2).strip()
            continue
        if h:
            cur = {"name": h.group(2).strip(), "content": "", "kind": "note"}
            entries.append(cur)
            continue
        meta = re.match(r"^<!--\s*kind:\s*(\w+);\s*keys:\s*(.*?);\s*always:\s*(true|false)\s*-->$", line.strip())
        if meta and cur is not None:
            cur["kind"] = meta.group(1) if meta.group(1) in KINDS else "note"
            cur["keys"] = [k for k in meta.group(2).split(",") if k.strip()]
            cur["always"] = meta.group(3) == "true"
            continue
        if cur is None and line.strip():
            cur = {"name": text(name, "Notas", 80), "content": "", "kind": "note"}
            entries.append(cur)
        if cur is not None:
            cur["content"] += line + "\n"
    for e in entries:
        e["content"] = e["content"].strip()
    book = norm_book({"name": title or "Lorebook", "entries": [e for e in entries if e["content"]]})
    if not book or not book["entries"]:
        _fail()
    return book
