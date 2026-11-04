"""Esquema do mundo (spec) + validação determinística + orçamentos de hardware.

Os agentes de IA produzem um *spec* JSON; o motor 3D do ASTA (runtime/) o renderiza.
Como a saída de um LLM nunca é confiável, tudo passa por `normalize_world`, que
corrige tipos, limita valores e aplica o orçamento do hardware do usuário.
"""
from __future__ import annotations

import re
import zlib
from typing import Any, Dict, List, Optional

from ..cards import normalize_appearance
from ..util import clamp, num, slugify, text

SCHEMA = "asta.world.v1"

BIOMES = ["temperate", "forest", "desert", "snow", "tropical", "island", "urban", "wasteland", "swamp", "mountain"]
STRUCTURES = [
    "house", "cabin", "tower", "ruin", "tent", "stall", "lamp", "well", "campfire", "fence",
    "statue", "barn", "bench", "sign", "crates", "pillar", "stone_circle",
]
WEATHER = ["clear", "cloudy", "fog", "rain", "snow", "storm"]
AMBIENCE = ["wind", "forest", "rain", "ocean", "city", "cave", "desert", "night", "none"]
MOODS = ["calm", "tense", "mysterious", "epic", "melancholic", "joyful"]
SCALES = ["major", "minor", "dorian", "phrygian", "pentatonic", "lydian"]
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
BEHAVIORS = ["idle", "wander", "patrol", "stand"]
SIZES = {"small": 240, "medium": 420, "large": 760}

# Orçamentos por nível de hardware. O jogo escolhe o nível pela máquina onde roda
# (e ainda reduz a qualidade dinamicamente se o FPS cair).
BUDGETS: Dict[str, Dict[str, Any]] = {
    "low": {
        "terrain_segments": 96, "trees": 220, "rocks": 80, "grass": 0, "structures": 28, "npcs": 6,
        "shadow": 0, "pixel_ratio": 1.0, "draw_distance": 170, "max_size": 420, "particles": 250,
    },
    "medium": {
        "terrain_segments": 160, "trees": 800, "rocks": 220, "grass": 1600, "structures": 60, "npcs": 12,
        "shadow": 1024, "pixel_ratio": 1.25, "draw_distance": 270, "max_size": 800, "particles": 700,
    },
    "high": {
        "terrain_segments": 224, "trees": 2400, "rocks": 520, "grass": 4200, "structures": 120, "npcs": 24,
        "shadow": 2048, "pixel_ratio": 2.0, "draw_distance": 430, "max_size": 1200, "particles": 1600,
    },
}

BIOME_DEFAULTS: Dict[str, Dict[str, Any]] = {
    #             relief  water  vegetation rocks  ambience  sky      ground
    "temperate": dict(relief=0.35, water=True, vegetation=0.55, rocks=0.3, ambience="forest", sky="#7fb2e5", ground="#5f8a3d"),
    "forest": dict(relief=0.4, water=True, vegetation=0.95, rocks=0.3, ambience="forest", sky="#6f9fc0", ground="#3d6b2b"),
    "desert": dict(relief=0.45, water=False, vegetation=0.12, rocks=0.45, ambience="desert", sky="#9cc3e6", ground="#d2b071"),
    "snow": dict(relief=0.5, water=False, vegetation=0.4, rocks=0.4, ambience="wind", sky="#b9cde0", ground="#e8eef4"),
    "tropical": dict(relief=0.3, water=True, vegetation=0.85, rocks=0.2, ambience="forest", sky="#6ec1e8", ground="#4f9a3f"),
    "island": dict(relief=0.3, water=True, vegetation=0.6, rocks=0.25, ambience="ocean", sky="#76c3ea", ground="#e0cf9a"),
    "urban": dict(relief=0.08, water=False, vegetation=0.12, rocks=0.05, ambience="city", sky="#8aa5c4", ground="#6b6e73"),
    "wasteland": dict(relief=0.4, water=False, vegetation=0.1, rocks=0.6, ambience="wind", sky="#b59a7d", ground="#7a6a55"),
    "swamp": dict(relief=0.15, water=True, vegetation=0.7, rocks=0.15, ambience="night", sky="#7e8f7a", ground="#4a5a34"),
    "mountain": dict(relief=0.95, water=True, vegetation=0.45, rocks=0.7, ambience="wind", sky="#8fb4dc", ground="#6c7a58"),
}


def budget_for(tier: str) -> Dict[str, Any]:
    return dict(BUDGETS.get(tier, BUDGETS["medium"]))


def _choice(value: Any, allowed: List[str], default: str) -> str:
    v = str(value or "").strip().lower()
    return v if v in allowed else default


def _hex(value: Any, default: str) -> str:
    v = str(value or "").strip()
    if re.match(r"^#[0-9a-fA-F]{6}$", v):
        return v.lower()
    if re.match(r"^#[0-9a-fA-F]{3}$", v):
        return "#" + "".join(c * 2 for c in v[1:]).lower()
    return default


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "sim", "on")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def seed_from(title: str) -> int:
    return zlib.crc32(title.encode("utf-8")) & 0x7FFFFFFF


# --------------------------------------------------------------------------- áudio / UX


def normalize_audio(raw: Any, biome: str, weather: str, audio_files: Optional[List[str]] = None) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    default_amb = "rain" if weather in ("rain", "storm") else BIOME_DEFAULTS[biome]["ambience"]
    music = raw.get("music") if isinstance(raw.get("music"), dict) else {}
    fname = text(music.get("file"), "", 120)
    if fname not in (audio_files or []):
        fname = ""
    return {
        "ambience": _choice(raw.get("ambience"), AMBIENCE, default_amb),
        "ambience_volume": round(num(raw.get("ambience_volume"), 0.5, 0, 1), 2),
        "music": {
            "enabled": _bool(music.get("enabled"), True),
            "mood": _choice(music.get("mood"), MOODS, "calm"),
            "tempo": int(num(music.get("tempo"), 72, 40, 160)),
            "root": _choice(str(music.get("root", "C")).upper().replace("♯", "#"), NOTES, "C"),
            "scale": _choice(music.get("scale"), SCALES, "minor"),
            "volume": round(num(music.get("volume"), 0.35, 0, 1), 2),
            "file": fname,
        },
        "footsteps": _bool(raw.get("footsteps"), True),
    }


def normalize_ux(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    theme = raw.get("theme") if isinstance(raw.get("theme"), dict) else {}
    hud = raw.get("hud") if isinstance(raw.get("hud"), dict) else {}
    return {
        "theme": {
            "bg": _hex(theme.get("bg"), "#000000"),
            "text": _hex(theme.get("text"), "#ececec"),
            "accent": _hex(theme.get("accent"), "#ffffff"),
        },
        "hud": {
            "crosshair": _bool(hud.get("crosshair"), True),
            "minimap": _bool(hud.get("minimap"), True),
            "compass": _bool(hud.get("compass"), True),
            "clock": _bool(hud.get("clock"), True),
            "hints": _bool(hud.get("hints"), True),
        },
        "intro": text(raw.get("intro"), "", 500),
        "controls_hint": text(raw.get("controls_hint"), "", 300),
    }


# --------------------------------------------------------------------------- mundo


def normalize_world(
    raw: Any,
    tier: str,
    settings: Optional[Dict[str, Any]] = None,
    character_ids: Optional[List[str]] = None,
    audio_files: Optional[List[str]] = None,
    default_title: str = "Mundo sem nome",
) -> Dict[str, Any]:
    """Valida o spec do mundo e o ajusta ao orçamento do hardware."""
    raw = raw if isinstance(raw, dict) else {}
    gen = settings or {}
    budget = budget_for(tier)
    env_raw = raw.get("environment") if isinstance(raw.get("environment"), dict) else {}

    title = text(raw.get("title"), default_title, 80)
    biome = _choice(env_raw.get("biome"), BIOMES, "temperate")
    bd = BIOME_DEFAULTS[biome]
    size_default = SIZES.get(str(gen.get("size", "medium")), SIZES["medium"])
    size = num(env_raw.get("size"), size_default, 120, budget["max_size"])
    size = min(size, budget["max_size"])
    half = size / 2 - 8
    weather = _choice(env_raw.get("weather"), WEATHER, "clear")
    if biome == "snow" and weather == "rain":
        weather = "snow"

    spec: Dict[str, Any] = {
        "schema": SCHEMA,
        "title": title,
        "description": text(raw.get("description"), "", 600),
        "language": text(raw.get("language"), "pt-BR", 12),
        "seed": int(num(raw.get("seed"), seed_from(title), 0, 2 ** 31 - 1)),
        "perspective": _choice(raw.get("perspective") or gen.get("perspective"), ["first", "third"], "third"),
        "realism": round(num(raw.get("realism", gen.get("realism")), 0.7, 0, 1), 2),
        "environment": {
            "biome": biome,
            "size": round(size),
            "relief": round(num(env_raw.get("relief"), bd["relief"], 0, 1), 2),
            "water": _bool(env_raw.get("water"), bd["water"]),
            "time_of_day": round(num(env_raw.get("time_of_day"), 10, 0, 24), 2) % 24,
            "day_cycle": _bool(env_raw.get("day_cycle"), bool(gen.get("day_cycle", True))),
            "day_length_min": round(num(env_raw.get("day_length_min"), 12, 2, 60), 1),
            "weather": weather,
            "vegetation": round(num(env_raw.get("vegetation"), bd["vegetation"], 0, 1), 2),
            "rocks": round(num(env_raw.get("rocks"), bd["rocks"], 0, 1), 2),
        },
        "structures": [],
        "npcs": [],
        "player": {},
        "audio": {},
        "ux": {},
        "gameplay": {},
        "quality": {},
    }

    # estruturas
    structs: List[Dict[str, Any]] = []
    for item in (raw.get("structures") or [])[: budget["structures"]]:
        if not isinstance(item, dict):
            continue
        stype = _choice(item.get("type"), STRUCTURES, "")
        if not stype:
            continue
        structs.append(
            {
                "type": stype,
                "x": round(num(item.get("x"), 0, -half, half), 1),
                "z": round(num(item.get("z"), 0, -half, half), 1),
                "rot": round(num(item.get("rot"), 0, 0, 360), 0),
                "scale": round(num(item.get("scale"), 1, 0.5, 2.5), 2),
                "variant": int(num(item.get("variant"), 0, 0, 3)),
                "label": text(item.get("label"), "", 40),
            }
        )
    spec["structures"] = structs

    # NPCs
    ids = set(character_ids or [])
    max_npcs = budget["npcs"]
    user_cap = int(num(gen.get("max_npcs"), 0, 0, 64))
    if user_cap:
        max_npcs = min(max_npcs, user_cap)
    seen = set()
    npcs: List[Dict[str, Any]] = []
    for item in raw.get("npcs") or []:
        if not isinstance(item, dict) or len(npcs) >= max_npcs:
            continue
        cid = text(item.get("char") or item.get("id"), "", 60)
        if cid not in ids:
            continue
        nid = slugify(item.get("id") or cid)
        base, k = nid, 2
        while nid in seen:
            nid, k = f"{base}-{k}", k + 1
        seen.add(nid)
        patrol = []
        for pt in (item.get("patrol") or [])[:8]:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                patrol.append([round(num(pt[0], 0, -half, half), 1), round(num(pt[1], 0, -half, half), 1)])
        behavior = _choice(item.get("behavior"), BEHAVIORS, "wander")
        if behavior == "patrol" and len(patrol) < 2:
            behavior = "wander"
        entry = {
            "id": nid,
            "char": cid,
            "x": round(num(item.get("x"), 0, -half, half), 1),
            "z": round(num(item.get("z"), 0, -half, half), 1),
            "behavior": behavior,
            "radius": round(num(item.get("radius"), 8, 2, 60), 1),
            "patrol": patrol,
        }
        if isinstance(item.get("appearance"), dict):
            entry["appearance"] = normalize_appearance(item["appearance"])
        npcs.append(entry)
    spec["npcs"] = npcs

    # jogador
    pl = raw.get("player") if isinstance(raw.get("player"), dict) else {}
    pchar = text(pl.get("char"), "", 60)
    player: Dict[str, Any] = {
        "char": pchar if pchar in ids else "",
        "x": round(num(pl.get("x"), 0, -half, half), 1),
        "z": round(num(pl.get("z"), 0, -half, half), 1),
        "yaw": round(num(pl.get("yaw"), 0, 0, 360), 0),
    }
    if isinstance(pl.get("appearance"), dict):
        player["appearance"] = normalize_appearance(pl["appearance"])
    spec["player"] = player

    spec["audio"] = normalize_audio(raw.get("audio"), biome, weather, audio_files)
    spec["ux"] = normalize_ux(raw.get("ux"))
    gp = raw.get("gameplay") if isinstance(raw.get("gameplay"), dict) else {}
    spec["gameplay"] = {
        "npc_autonomy": _choice(gp.get("npc_autonomy") or gen.get("npc_autonomy"), ["off", "low", "high"], "off"),
        "interaction_distance": round(num(gp.get("interaction_distance"), 3.8, 2, 8), 1),
        "rules": text(gp.get("rules"), "", 1200),
    }
    spec["quality"] = {
        "target": _choice(gen.get("quality") or (raw.get("quality") or {}).get("target"), ["auto", "low", "medium", "high"], "auto"),
        "tiers": {k: dict(v) for k, v in BUDGETS.items()},
        "generated_for": tier,
    }
    return spec


def palette_for(spec: Dict[str, Any]) -> Dict[str, str]:
    bd = BIOME_DEFAULTS.get(spec.get("environment", {}).get("biome", "temperate"), BIOME_DEFAULTS["temperate"])
    return {"sky": bd["sky"], "ground": bd["ground"]}


WORLD_SCHEMA_DOC = f"""World spec JSON schema (all coordinates in meters; x = east(+)/west(-), z = south(+)/north(-);
the player spawns near (0,0); keep everything inside +-(environment.size/2 - 10)):
{{
  "title": str, "description": str (1-3 sentences), "language": "pt-BR"|"en"|..., "seed": int,
  "perspective": "first"|"third", "realism": 0..1,
  "environment": {{
    "biome": one of {BIOMES}, "size": 120..1200, "relief": 0..1, "water": bool,
    "time_of_day": 0..24, "day_cycle": bool, "day_length_min": 2..60,
    "weather": one of {WEATHER}, "vegetation": 0..1, "rocks": 0..1
  }},
  "structures": [{{"type": one of {STRUCTURES}, "x": num, "z": num, "rot": 0..360, "scale": 0.5..2.5, "variant": 0..3, "label": str}}],
  "npcs": [{{"id": str, "char": <character id>, "x": num, "z": num, "behavior": one of {BEHAVIORS},
             "radius": 2..60 (wander radius), "patrol": [[x,z],...] (only for behavior "patrol")}}],
  "player": {{"char": <character id or "">, "x": num, "z": num, "yaw": 0..360}},
  "gameplay": {{"npc_autonomy": "off"|"low"|"high", "interaction_distance": 2..8, "rules": str}}
}}"""

AUDIO_UX_SCHEMA_DOC = f"""Audio/UX JSON schema:
{{
  "audio": {{
    "ambience": one of {AMBIENCE}, "ambience_volume": 0..1, "footsteps": bool,
    "music": {{"enabled": bool, "mood": one of {MOODS}, "tempo": 40..160, "root": one of {NOTES},
              "scale": one of {SCALES}, "volume": 0..1, "file": optional name of an attached audio file}}
  }},
  "ux": {{
    "theme": {{"bg": "#hex", "text": "#hex", "accent": "#hex"}},
    "hud": {{"crosshair": bool, "minimap": bool, "compass": bool, "clock": bool, "hints": bool}},
    "intro": str (short opening text shown when the game starts), "controls_hint": str
  }}
}}"""
