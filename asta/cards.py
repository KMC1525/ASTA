"""Cards de personagem e de worldbuilding (formato JSON próprio do ASTA).

Cada card é um arquivo .json simples, fácil de editar à mão, exportar e compartilhar.
Também importamos cards no formato "Character Card V2/V3" (SillyTavern/Chub).
"""
from __future__ import annotations

import base64
import json
import re
import struct
import zlib
from typing import Any, Dict, List, Optional

from .util import num, text

CHARACTER_SCHEMA = "asta.character.v1"
WORLDBUILDING_SCHEMA = "asta.worldbuilding.v1"

DEFAULT_APPEARANCE = {
    "skin": "#c68a63",
    "hair": "#2b1b12",
    "hair_style": "short",  # short | long | bald | bun
    "top": "#3b5b7a",
    "bottom": "#2a2a30",
    "height": 1.72,
    "build": 1.0,
    "accessory": "none",  # none | hat | cape | backpack
}

DEFAULT_VOICE = {
    "engine": "auto",  # auto | browser | server
    "name": "",  # nome da voz do navegador (opcional)
    "lang": "auto",  # auto = detecta pelo idioma da conversa
    "pitch": 1.0,
    "rate": 1.0,
    "server_voice": "",  # voz do servidor TTS (ex.: alloy)
}

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _hex(value: Any, default: str) -> str:
    v = str(value or "").strip()
    if HEX_RE.match(v):
        return v.lower()
    if re.match(r"^#[0-9a-fA-F]{3}$", v):
        return "#" + "".join(c * 2 for c in v[1:]).lower()
    return default


def _tags(value: Any, limit: int = 16) -> List[str]:
    if isinstance(value, str):
        value = re.split(r"[,;\n]", value)
    out: List[str] = []
    for item in value or []:
        tag = text(item, "", 40).lower()
        if tag and tag not in out:
            out.append(tag)
    return out[:limit]


def normalize_appearance(value: Any) -> Dict[str, Any]:
    src = value if isinstance(value, dict) else {}
    d = DEFAULT_APPEARANCE
    style = text(src.get("hair_style"), d["hair_style"], 20).lower()
    acc = text(src.get("accessory"), d["accessory"], 20).lower()
    return {
        "skin": _hex(src.get("skin"), d["skin"]),
        "hair": _hex(src.get("hair"), d["hair"]),
        "hair_style": style if style in ("short", "long", "bald", "bun") else "short",
        "top": _hex(src.get("top"), d["top"]),
        "bottom": _hex(src.get("bottom"), d["bottom"]),
        "height": round(num(src.get("height"), d["height"], 1.2, 2.3), 2),
        "build": round(num(src.get("build"), d["build"], 0.75, 1.35), 2),
        "accessory": acc if acc in ("none", "hat", "cape", "backpack") else "none",
    }


def normalize_voice(value: Any) -> Dict[str, Any]:
    src = value if isinstance(value, dict) else {}
    engine = text(src.get("engine"), "auto", 12).lower()
    return {
        "engine": engine if engine in ("auto", "browser", "server") else "auto",
        "name": text(src.get("name"), "", 120),
        "lang": text(src.get("lang"), "auto", 16),
        "pitch": round(num(src.get("pitch"), 1.0, 0.5, 2.0), 2),
        "rate": round(num(src.get("rate"), 1.0, 0.5, 2.0), 2),
        "server_voice": text(src.get("server_voice"), "", 60),
    }


def normalize_character(data: Dict[str, Any], keep_id: Optional[str] = None) -> Dict[str, Any]:
    """Valida/normaliza um card de personagem."""
    data = data if isinstance(data, dict) else {}
    name = text(data.get("name"), "Sem nome", 80)
    role = text(data.get("role"), "npc", 10).lower()
    return {
        "schema": CHARACTER_SCHEMA,
        "id": keep_id or text(data.get("id"), "", 60),
        "name": name,
        "role": role if role in ("npc", "player") else "npc",
        "tags": _tags(data.get("tags")),
        "system_prompt": text(data.get("system_prompt"), "", 12000),
        "greeting": text(data.get("greeting"), "", 600),
        "voice": normalize_voice(data.get("voice")),
        "appearance": normalize_appearance(data.get("appearance")),
        "created": text(data.get("created"), "", 40),
        "updated": text(data.get("updated"), "", 40),
    }


def normalize_worldbuilding(data: Dict[str, Any], keep_id: Optional[str] = None) -> Dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    return {
        "schema": WORLDBUILDING_SCHEMA,
        "id": keep_id or text(data.get("id"), "", 60),
        "name": text(data.get("name"), "Sem nome", 80),
        "tags": _tags(data.get("tags")),
        "system_prompt": text(data.get("system_prompt"), "", 20000),
        "created": text(data.get("created"), "", 40),
        "updated": text(data.get("updated"), "", 40),
    }


# --------------------------------------------------------------------------- importação


def import_character(data: Any) -> Dict[str, Any]:
    """Aceita card ASTA ou Character Card V2/V3 (SillyTavern) e devolve card ASTA."""
    if not isinstance(data, dict):
        raise ValueError("JSON de personagem inválido")
    if data.get("schema") == CHARACTER_SCHEMA:
        card = normalize_character(data)
        card["id"] = ""  # novo id ao importar
        return card
    if "data" in data and isinstance(data["data"], dict) and str(data.get("spec", "")).startswith("chara_card"):
        d = data["data"]
    else:
        d = data
    parts = [d.get("system_prompt"), d.get("description"), d.get("personality"), d.get("scenario")]
    labels = ["", "Descrição", "Personalidade", "Cenário"]
    chunks: List[str] = []
    for label, part in zip(labels, parts):
        part = text(part, "", 8000)
        if part:
            chunks.append(f"{label}: {part}" if label else part)
    if d.get("mes_example"):
        chunks.append("Exemplos de fala:\n" + text(d.get("mes_example"), "", 4000))
    return normalize_character(
        {
            "name": d.get("name") or d.get("char_name"),
            "tags": d.get("tags"),
            "system_prompt": "\n\n".join(chunks),
            "greeting": d.get("first_mes") or d.get("greeting"),
        }
    )


def character_from_png(raw: bytes) -> Dict[str, Any]:
    """Lê o card embutido (chunk tEXt 'chara'/'ccv3') de um PNG de personagem."""
    return import_character(png_card_data(raw))


def png_card_data(raw: bytes) -> Dict[str, Any]:
    """Devolve o JSON do Character Card embutido num PNG (SillyTavern/Janitor/Chub)."""
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Arquivo não é PNG")
    pos = 8
    found: Dict[str, bytes] = {}
    while pos + 8 <= len(raw):
        (length,) = struct.unpack(">I", raw[pos:pos + 4])
        ctype = raw[pos + 4:pos + 8]
        body = raw[pos + 8:pos + 8 + length]
        if ctype == b"tEXt" and b"\x00" in body:
            key, _, val = body.partition(b"\x00")
            found[key.decode("latin-1")] = val
        elif ctype == b"iTXt" and b"\x00" in body:
            key, _, rest = body.partition(b"\x00")
            flag, method = rest[0:1], rest[1:2]
            rest = rest[2:]
            parts = rest.split(b"\x00", 2)
            if len(parts) == 3:
                val = parts[2]
                if flag == b"\x01" and method == b"\x00":
                    try:
                        val = zlib.decompress(val)
                    except zlib.error:
                        continue
                found[key.decode("latin-1")] = val
        pos += 12 + length
    payload = found.get("ccv3") or found.get("chara")
    if not payload:
        raise ValueError("Nenhum card de personagem encontrado no PNG")
    try:
        data = json.loads(base64.b64decode(payload).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Card do PNG está corrompido") from exc
    if not isinstance(data, dict):
        raise ValueError("Card do PNG está corrompido")
    return data
