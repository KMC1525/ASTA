"""Game Engine — formatos de dados e catálogos (única fonte de verdade: o servidor valida; o Inspetor da tela é montado a partir daqui).

A IA escreve **dados**: uma cena é uma árvore de nós (como no Godot) e cada nó pode ter *comportamentos* de uma lista fechada (código revisado, no motor).
Código novo só entra pela aba Code (arquivos `scripts/*.js`), que roda dentro de um iframe isolado.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..util import clamp, text

SCHEMA_SCENE = "asta.ge.scene.v1"
SCHEMA_MAP = "asta.ge.map.v1"
SCHEMA_PROJECT = "asta.ge.project.v1"
SCHEMA_ASSET = "asta.ge.asset.v1"      # imagem em camadas (aba Assets)
SCHEMA_SOUND = "asta.ge.sound.v1"      # projeto de áudio em faixas (aba Sound)

MAX_NODES = 3000
MAX_DEPTH = 20
MAX_NAME = 60

KINDS: Dict[str, Dict[str, Any]] = {
    "2d": {"label": "2D", "dim": "2d", "hint": "Plataforma, aventura vista de cima, nave — canvas, leve em qualquer aparelho."},
    "2.5d": {"label": "2.5D", "dim": "2d", "hint": "Isométrico com alturas ou 2D com camadas de profundidade (paralaxe)."},
    "3d": {"label": "3D", "dim": "3d", "hint": "Mundo 3D com terreno, céu, luzes e câmera em 1ª ou 3ª pessoa (three.js)."},
    "vr": {"label": "VR", "dim": "3d", "hint": "Realidade virtual (WebXR): teletransporte, pegar e arremessar objetos; prévia no computador."},
    "ar": {"label": "AR", "dim": "3d", "hint": "Realidade aumentada (WebXR): marcador de chão e objetos colocados no mundo real; prévia no computador."},
}
GENRES: Dict[str, Dict[str, Any]] = {
    "platformer": {"kinds": ["2d", "2.5d"], "label": "Plataforma", "hint": "Pule, desvie de inimigos e chegue ao objetivo."},
    "topdown": {"kinds": ["2d"], "label": "Aventura (vista de cima)", "hint": "Explore, pegue itens, converse e evite inimigos."},
    "shooter": {"kinds": ["2d"], "label": "Nave (side scroller)", "hint": "Atire em ondas de inimigos que avançam."},
    "iso": {"kinds": ["2.5d"], "label": "Isométrico", "hint": "Aventura isométrica em blocos com alturas."},
    "explore": {"kinds": ["3d"], "label": "Exploração 3D", "hint": "Terceira pessoa: explore o mundo, colete e converse."},
    "fps": {"kinds": ["3d"], "label": "Primeira pessoa", "hint": "Primeira pessoa: colete tudo antes dos perseguidores."},
    "vr_explore": {"kinds": ["vr"], "label": "VR: exploração", "hint": "Terreno com teletransporte e itens para coletar."},
    "vr_room": {"kinds": ["vr"], "label": "VR: sala", "hint": "Uma sala com objetos para pegar e arremessar."},
    "ar_place": {"kinds": ["ar"], "label": "AR: colocar objetos", "hint": "Aponte para o chão e toque para colocar objetos."},
    "ar_hunt": {"kinds": ["ar"], "label": "AR: caça aos itens", "hint": "Itens flutuam ao seu redor: ande e colete."},
}
DEFAULT_GENRE = {"2d": "platformer", "2.5d": "iso", "3d": "explore", "vr": "vr_explore", "ar": "ar_place"}
THEMES = ("forest", "desert", "snow", "night", "cave", "city", "space", "sea", "candy", "lava", "retro", "sunset")
THEME_COLORS: Dict[str, Dict[str, str]] = {   # céu em cima/embaixo, chão, destaque
    "forest": {"top": "#4a90d9", "bottom": "#cfe8ff", "ground": "#5e9c4a", "dirt": "#7a5a3a", "stone": "#8a8d93", "accent": "#ffd23f", "water": "#2f7fbf"},
    "desert": {"top": "#e9a860", "bottom": "#fbe3b0", "ground": "#d9b36a", "dirt": "#b98a45", "stone": "#a8794a", "accent": "#06d6a0", "water": "#3d9fb8"},
    "snow": {"top": "#8fb7e0", "bottom": "#eaf4ff", "ground": "#eef6ff", "dirt": "#a9c4de", "stone": "#7e94ad", "accent": "#ff6b6b", "water": "#5aa7d6"},
    "night": {"top": "#050a24", "bottom": "#1c2a5a", "ground": "#2c4a3e", "dirt": "#33332f", "stone": "#505a70", "accent": "#ffe66d", "water": "#1b3b6f"},
    "cave": {"top": "#0b0a10", "bottom": "#231c2c", "ground": "#4a4256", "dirt": "#34303c", "stone": "#6a6478", "accent": "#7bf1a8", "water": "#244a6e"},
    "city": {"top": "#3b4a6b", "bottom": "#a8b9d6", "ground": "#6b7280", "dirt": "#4b5563", "stone": "#9ca3af", "accent": "#fca311", "water": "#3b6ea5"},
    "space": {"top": "#02030f", "bottom": "#14123a", "ground": "#4b4e6d", "dirt": "#2e3050", "stone": "#7c82a8", "accent": "#4cc9f0", "water": "#202a5a"},
    "sea": {"top": "#2a8fd0", "bottom": "#bfe9ff", "ground": "#e3cf94", "dirt": "#c4a96b", "stone": "#7e8a94", "accent": "#ff9f1c", "water": "#1f78b8"},
    "candy": {"top": "#ff9ecb", "bottom": "#fff0f7", "ground": "#ffc8dd", "dirt": "#e49ab8", "stone": "#c8a2e8", "accent": "#7bdff2", "water": "#a2d2ff"},
    "lava": {"top": "#2a0a08", "bottom": "#7a2210", "ground": "#4a3a36", "dirt": "#2c2220", "stone": "#6b5a54", "accent": "#ffd166", "water": "#e8541c"},
    "retro": {"top": "#ff6a88", "bottom": "#2b1b4a", "ground": "#3a2f6b", "dirt": "#241b45", "stone": "#7a6ab0", "accent": "#00f5d4", "water": "#4d3b8f"},
    "sunset": {"top": "#ff8a5c", "bottom": "#ffd29a", "ground": "#6a8f46", "dirt": "#6b4a3a", "stone": "#8a7a7a", "accent": "#f9c74f", "water": "#d1638c"},
}
BIOMES = ("temperate", "forest", "desert", "snow", "tropical", "island", "mountain", "swamp", "wasteland", "volcanic")


# ============================================================================ catálogo de nós e comportamentos (Inspetor)
def P(key: str, typ: str, default: Any = None, **kw: Any) -> Dict[str, Any]:
    d = {"k": key, "t": typ, "d": default}
    d.update(kw)
    return d


T2D = [P("x", "num", 0, step=1), P("y", "num", 0, step=1), P("rotation", "num", 0, min=-360, max=360), P("sx", "num", 1, min=-20, max=20, step=0.1), P("sy", "num", 1, min=-20, max=20, step=0.1), P("z", "num", 0, step=1, hint="camada"), P("visible", "bool", True)]
T3D = [P("x", "num", 0, step=0.25), P("y", "num", 0, step=0.25), P("z", "num", 0, step=0.25), P("rx", "num", 0, min=-360, max=360), P("ry", "num", 0, min=-360, max=360), P("rz", "num", 0, min=-360, max=360),
       P("sx", "num", 1, min=0.01, max=100, step=0.1), P("sy", "num", 1, min=0.01, max=100, step=0.1), P("sz", "num", 1, min=0.01, max=100, step=0.1), P("visible", "bool", True)]
ANCHORS = ["top-left", "top-center", "top-right", "center", "bottom-left", "bottom-center", "bottom-right"]
SHAPES_2D = ["rect", "circle", "tri", "diamond", "block", "flag", "emoji", "none"]
SHAPES_3D = ["box", "sphere", "cylinder", "cone", "capsule", "torus", "plane", "octa", "icosa"]

NODE_TYPES: Dict[str, Dict[str, Any]] = {
    # ---- 2D
    "Node2D": {"dim": "2d", "icon": "node", "label": "Nó 2D", "props": T2D, "container": True},
    "Sprite2D": {"dim": "2d", "icon": "image", "label": "Sprite", "props": T2D + [P("w", "num", 32, min=1, max=4096), P("h", "num", 32, min=1, max=4096), P("color", "color", "#cccccc"), P("shape", "select", "rect", options=SHAPES_2D), P("image", "image", ""), P("emoji", "text", ""),
                                                                                  P("opacity", "num", 1, min=0, max=1, step=0.05), P("solid", "bool", False, hint="bloqueia o movimento"), P("flip", "bool", False), P("shadow", "bool", False)]},
    "Area2D": {"dim": "2d", "icon": "box", "label": "Área", "props": T2D + [P("w", "num", 32, min=1, max=4096), P("h", "num", 32, min=1, max=4096), P("color", "color", "#80ed99"), P("shape", "select", "none", options=SHAPES_2D), P("image", "image", "")]},
    "Label2D": {"dim": "2d", "icon": "type", "label": "Texto", "props": T2D + [P("text", "text", "Olá"), P("size", "num", 18, min=6, max=200), P("color", "color", "#ffffff"), P("align", "select", "center", options=["left", "center", "right"])]},
    "TileMap": {"dim": "2d", "icon": "grid", "label": "Mapa de blocos", "props": [P("map", "map", ""), P("objects", "bool", True, hint="cria os objetos do mapa (moedas, inimigos…)"), P("visible", "bool", True)]},
    "Camera2D": {"dim": "2d", "icon": "eye", "label": "Câmera 2D", "props": [P("follow", "node", ""), P("zoom", "num", 1, min=0.2, max=5, step=0.1), P("smooth", "num", 1, min=0.1, max=10, step=0.1)]},
    "Parallax2D": {"dim": "2d", "icon": "layers", "label": "Fundo com paralaxe", "props": [P("style", "select", "hills", options=["hills", "mountains", "clouds", "stars", "city", "trees", "solid"]), P("color", "color", "#2b3a55"), P("color2", "color", "#3d5075"),
                                                                                        P("factor", "num", 0.3, min=0, max=1, step=0.05), P("y", "num", 0.75, min=0, max=1.2, step=0.05, hint="altura (0 topo … 1 base)"), P("h", "num", 0.3, min=0.05, max=1, step=0.05), P("opacity", "num", 1, min=0, max=1, step=0.05), P("seed", "int", 0), P("visible", "bool", True)]},
    # ---- 3D
    "Node3D": {"dim": "3d", "icon": "node", "label": "Nó 3D", "props": T3D, "container": True},
    "Mesh3D": {"dim": "3d", "icon": "box", "label": "Malha 3D", "props": T3D + [P("shape", "select", "box", options=SHAPES_3D), P("w", "num", 1, min=0.01, max=500, step=0.25), P("h", "num", 1, min=0.01, max=500, step=0.25), P("d", "num", 1, min=0.01, max=500, step=0.25), P("color", "color", "#9aa7b5"),
                                                                                 P("image", "image", ""), P("emissive", "color", ""), P("rough", "num", 0.78, min=0, max=1, step=0.05), P("metal", "num", 0, min=0, max=1, step=0.05), P("opacity", "num", 1, min=0, max=1, step=0.05), P("solid", "bool", False), P("shadow", "bool", True)]},
    "Light3D": {"dim": "3d", "icon": "sun", "label": "Luz", "props": [P("kind", "select", "directional", options=["directional", "point", "spot", "ambient", "hemisphere"]), P("color", "color", "#ffffff"), P("intensity", "num", 1, min=0, max=10, step=0.1), P("x", "num", 30), P("y", "num", 50), P("z", "num", 20), P("range", "num", 30, min=1, max=500), P("shadow", "bool", True)]},
    "Camera3D": {"dim": "3d", "icon": "eye", "label": "Câmera 3D", "props": [P("mode", "select", "third", options=["first", "third", "orbit", "fixed"]), P("fov", "num", 70, min=20, max=120), P("distance", "num", 6.5, min=1, max=60), P("height", "num", 2, min=0, max=30), P("x", "num", 0), P("y", "num", 5), P("z", "num", 10), P("target", "node", "")]},
    "Terrain3D": {"dim": "3d", "icon": "mountain", "label": "Terreno", "props": [P("map", "map", ""), P("objects", "bool", True), P("color_low", "color", ""), P("color_mid", "color", ""), P("color_high", "color", "")]},
    "Sky3D": {"dim": "3d", "icon": "sun", "label": "Céu", "props": [P("top", "color", "#4a90d9"), P("bottom", "color", "#cfe8ff"), P("stars", "bool", False), P("fog", "num", 0.35, min=0, max=1, step=0.05)]},
    "Water3D": {"dim": "3d", "icon": "drop", "label": "Água", "props": [P("level", "num", 0, step=0.25), P("color", "color", "#2f7fbf"), P("opacity", "num", 0.78, min=0, max=1, step=0.05), P("size", "num", 400, min=10, max=4000)]},
    "Humanoid3D": {"dim": "3d", "icon": "user", "label": "Personagem 3D", "props": T3D + [P("color", "color", "#4cc9f0"), P("skin", "color", "#f1c27d"), P("scale", "num", 1, min=0.2, max=5, step=0.1)]},
    "Label3D": {"dim": "3d", "icon": "type", "label": "Texto 3D", "props": T3D + [P("text", "text", "Olá"), P("size", "num", 1.2, min=0.2, max=10, step=0.1), P("color", "color", "#ffffff")]},
    "XRRig": {"dim": "3d", "icon": "vr", "label": "Plataforma VR/AR", "props": [P("teleport", "bool", True), P("hands", "bool", True)]},
    # ---- comuns (HUD e áudio)
    "UILabel": {"dim": "any", "icon": "type", "label": "Texto de tela (HUD)", "props": [P("text", "text", "Pontos: {score}", hint="{score} {coins} {total} {hp} {time} {level}"), P("anchor", "select", "top-left", options=ANCHORS), P("size", "num", 18, min=8, max=96), P("color", "color", "#ffffff")]},
    "UIBar": {"dim": "any", "icon": "bar", "label": "Barra de tela (vida)", "props": [P("bind", "select", "hp", options=["hp"]), P("anchor", "select", "top-right", options=ANCHORS), P("w", "num", 120, min=20, max=600), P("color", "color", "#ff4d6d")]},
    "AudioPlayer": {"dim": "any", "icon": "audio", "label": "Som", "props": [P("sound", "sound", ""), P("loop", "bool", True), P("volume", "num", 0.6, min=0, max=1, step=0.05)]},
}
# bases que um tipo pode ter em cada dimensão (usado para corrigir cenas inválidas)
ROOT_TYPE = {"2d": "Node2D", "3d": "Node3D"}

B2 = ["2d"]
B3 = ["3d"]
BA = ["2d", "3d"]
BEHAVIORS: Dict[str, Dict[str, Any]] = {
    "player_platformer": {"dims": B2, "label": "Jogador: plataforma", "params": [P("speed", "num", 190, min=20, max=900), P("jump", "num", 540, min=100, max=1400), P("double_jump", "bool", False)]},
    "player_topdown": {"dims": B2, "label": "Jogador: vista de cima", "params": [P("speed", "num", 170, min=20, max=900)]},
    "player_ship": {"dims": B2, "label": "Jogador: nave", "params": [P("speed", "num", 260, min=40, max=900), P("fire_rate", "num", 0.22, min=0.05, max=2, step=0.01)]},
    "player_iso": {"dims": B2, "label": "Jogador: isométrico", "params": [P("speed", "num", 3.2, min=0.5, max=12, step=0.1)]},
    "player_fps": {"dims": B3, "label": "Jogador: 1ª pessoa", "params": [P("speed", "num", 5, min=1, max=30), P("jump", "num", 8, min=0, max=30)]},
    "player_third": {"dims": B3, "label": "Jogador: 3ª pessoa", "params": [P("speed", "num", 5, min=1, max=30), P("jump", "num", 8, min=0, max=30)]},
    "player_vr": {"dims": B3, "label": "Jogador: VR", "params": [P("speed", "num", 3, min=0.5, max=12, step=0.1)]},
    "wander": {"dims": BA, "label": "Vagar", "params": [P("speed", "num", 40, min=0, max=600), P("radius", "num", 80, min=0, max=1000)]},
    "patrol": {"dims": BA, "label": "Patrulhar", "params": [P("range", "num", 90, min=0, max=2000), P("speed", "num", 55, min=0, max=600), P("axis", "select", "x", options=["x", "y", "z"])]},
    "chase": {"dims": BA, "label": "Perseguir o jogador", "params": [P("speed", "num", 70, min=0, max=600), P("range", "num", 220, min=1, max=2000)]},
    "follow": {"dims": BA, "label": "Seguir um nó", "params": [P("target", "node", "Jogador"), P("speed", "num", 120, min=0, max=600), P("gap", "num", 40, min=0, max=500)]},
    "drift": {"dims": B2, "label": "Deslizar pela tela", "params": [P("vx", "num", -90, min=-900, max=900)]},
    "bounce": {"dims": B2, "label": "Quicar", "params": [P("vx", "num", 120), P("vy", "num", 90)]},
    "spin": {"dims": BA, "label": "Girar", "params": [P("speed", "num", 90, min=-720, max=720), P("axis", "select", "y", options=["x", "y", "z"])]},
    "float": {"dims": BA, "label": "Flutuar", "params": [P("amp", "num", 4, min=0, max=100, step=0.1), P("speed", "num", 3, min=0, max=20, step=0.1)]},
    "collectible": {"dims": BA, "label": "Coletável", "params": [P("value", "int", 10, min=0, max=100000)]},
    "health_pickup": {"dims": BA, "label": "Cura", "params": [P("amount", "int", 1, min=1, max=20)]},
    "hazard": {"dims": BA, "label": "Perigo", "params": [P("damage", "int", 1, min=1, max=20)]},
    "enemy": {"dims": BA, "label": "Inimigo", "params": [P("hp", "int", 1, min=1, max=100), P("damage", "int", 1, min=1, max=20), P("score", "int", 20, min=0, max=100000)]},
    "shoot_at": {"dims": B2, "label": "Atirar no jogador", "params": [P("interval", "num", 2, min=0.2, max=20), P("speed", "num", 180, min=20, max=900), P("damage", "int", 1, min=1, max=20)]},
    "goal": {"dims": BA, "label": "Objetivo (fase)", "params": [P("next", "scene", "", hint="cena seguinte (vazio = próxima/fim)")]},
    "spring": {"dims": B2, "label": "Mola", "params": [P("power", "num", 780, min=100, max=2000)]},
    "key": {"dims": B2, "label": "Chave", "params": [P("id", "text", "a")]},
    "door": {"dims": B2, "label": "Porta com chave", "params": [P("key", "text", "a")]},
    "dialogue": {"dims": BA, "label": "Diálogo", "params": [P("id", "text", "npc1", hint="id em data/dialogues.json"), P("range", "num", 60, min=1, max=500)]},
    "spawner": {"dims": B2, "label": "Gerador de inimigos", "params": [P("template", "node", ""), P("interval", "num", 1.4, min=0.1, max=60), P("max", "int", 12, min=1, max=200)]},
    "grab": {"dims": B3, "label": "Pegável (VR)", "params": []},
    "place_on_tap": {"dims": B3, "label": "Modelo para colocar (AR)", "params": []},
    "teleport_pad": {"dims": B3, "label": "Teletransporte", "params": [P("to_x", "num", 0), P("to_z", "num", 0)]},
    "audio_loop": {"dims": BA, "label": "Som em laço", "params": [P("sound", "sound", ""), P("volume", "num", 0.6, min=0, max=1, step=0.05)]},
}
RULE_WINS = ("none", "reach_goal", "collect_all")
PROJECTIONS = ("flat", "iso")
CAMERAS = ("first", "third")

_ID = re.compile(r"[^A-Za-z0-9_-]")
_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def catalog() -> Dict[str, Any]:
    """O que a tela precisa para montar o Inspetor, a lista de tipos de nó e os comportamentos."""
    return {"kinds": KINDS, "genres": GENRES, "themes": list(THEMES), "biomes": list(BIOMES), "default_genre": DEFAULT_GENRE, "node_types": NODE_TYPES, "behaviors": BEHAVIORS,
            "theme_colors": THEME_COLORS, "rule_wins": list(RULE_WINS)}


# ============================================================================ validação
def _coerce(spec: Dict[str, Any], value: Any) -> Any:
    t = spec["t"]
    d = spec.get("d")
    if t in ("num", "int"):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return d
        if v != v or v in (float("inf"), float("-inf")):
            return d
        lo, hi = spec.get("min", -1e6), spec.get("max", 1e6)
        v = clamp(v, lo, hi)
        return int(round(v)) if t == "int" else round(v, 4)
    if t == "bool":
        return bool(value) if isinstance(value, bool) else d
    if t == "color":
        s = str(value or "").strip()
        return s if _COLOR.match(s) else ("" if d == "" and not s else d)
    if t == "select":
        s = str(value or "")
        opts = spec.get("options") or []
        return s if (s in opts or not opts) else d
    if t in ("text", "image", "sound", "map", "node", "scene", "longtext"):
        return text(value, d or "", 4000 if t == "longtext" else 400)
    return d


def norm_behavior(b: Any, dim: str) -> Optional[Dict[str, Any]]:
    if not isinstance(b, dict):
        return None
    name = str(b.get("type") or "")
    spec = BEHAVIORS.get(name)
    if not spec:
        return None
    out: Dict[str, Any] = {"type": name}
    for p in spec["params"]:
        if p["k"] in b:
            out[p["k"]] = _coerce(p, b[p["k"]])
    return out


def norm_node(raw: Any, dim: str, seen: set, counter: List[int], depth: int = 0) -> Optional[Dict[str, Any]]:
    """Valida um nó (e os filhos): tipo conhecido, propriedades da lista, ids únicos, limites de tamanho e profundidade."""
    if not isinstance(raw, dict) or counter[0] >= MAX_NODES or depth > MAX_DEPTH:
        return None
    typ = str(raw.get("type") or "")
    if typ not in NODE_TYPES or NODE_TYPES[typ]["dim"] not in (dim, "any"):
        typ = ROOT_TYPE[dim]
    spec = NODE_TYPES[typ]
    counter[0] += 1
    nid = _ID.sub("", str(raw.get("id") or ""))[:32]
    if not nid or nid in seen:
        n = counter[0]
        nid = f"n{n}"
        while nid in seen:
            n += 1
            nid = f"n{n}"
    seen.add(nid)
    node: Dict[str, Any] = {"id": nid, "type": typ, "name": text(raw.get("name"), spec["label"], MAX_NAME)}
    for p in spec["props"]:
        if p["k"] in raw:
            v = _coerce(p, raw[p["k"]])
            if v is not None:   # o que o autor escreveu fica explícito (o padrão do motor pode mudar entre versões)
                node[p["k"]] = v
    tags = [text(x, "", 24) for x in (raw.get("tags") if isinstance(raw.get("tags"), list) else [])][:8]
    tags = [x for x in tags if x]
    if tags:
        node["tags"] = tags
    behaviors = []
    for b in (raw.get("behaviors") if isinstance(raw.get("behaviors"), list) else [])[:12]:
        nb = norm_behavior(b, dim)
        if nb and dim in BEHAVIORS[nb["type"]]["dims"]:
            behaviors.append(nb)
    if behaviors:
        node["behaviors"] = behaviors
    if typ in ("Mesh3D", "Sprite2D", "Area2D") and raw.get("solid") is True:
        node["solid"] = True
    if raw.get("script") and isinstance(raw.get("script"), str):
        node["script"] = text(raw.get("script"), "", 200)
    kids = []
    for c in (raw.get("children") if isinstance(raw.get("children"), list) else []):
        nk = norm_node(c, dim, seen, counter, depth + 1)
        if nk:
            kids.append(nk)
    if kids:
        node["children"] = kids
    return node


def norm_settings(raw: Any, kind: str) -> Dict[str, Any]:
    s = raw if isinstance(raw, dict) else {}
    out: Dict[str, Any] = {}
    for key in ("bg", "sky_top", "sky_bottom"):
        v = str(s.get(key) or "").strip()
        if _COLOR.match(v):
            out[key] = v
    for key, lo, hi in (("gravity", 0, 5000), ("view_h", 120, 4000), ("autoscroll", 0, 600)):
        if key in s:
            try:
                out[key] = round(clamp(float(s[key]), lo, hi), 3)
            except (TypeError, ValueError):
                pass
    if s.get("projection") in PROJECTIONS:
        out["projection"] = s["projection"]
    if kind == "2.5d" and "projection" not in out:
        out["projection"] = "iso"
    if s.get("camera") in CAMERAS:
        out["camera"] = s["camera"]
    for key in ("ysort", "shadows", "vignette", "cam_bounds"):
        if isinstance(s.get(key), bool):
            out[key] = s[key]
    if isinstance(s.get("genre"), str) and s["genre"] in GENRES:
        out["genre"] = s["genre"]
    return out


def norm_scene(raw: Any, kind: str = "2d", name: str = "") -> Dict[str, Any]:
    """Cena válida (ou ValueError): árvore de nós, configurações, regras."""
    if not isinstance(raw, dict):
        raise ValueError("A cena precisa ser um objeto JSON.")
    kind = kind if kind in KINDS else "2d"
    dim = KINDS[kind]["dim"]
    if "root" in raw and not isinstance(raw["root"], dict):
        raise ValueError("A raiz da cena precisa ser um nó (objeto).")
    root = norm_node(raw.get("root") if isinstance(raw.get("root"), dict) else {"type": ROOT_TYPE[dim], "name": "Main", "children": raw.get("nodes") if isinstance(raw.get("nodes"), list) else []}, dim, set(), [0])
    if not root:
        raise ValueError("A cena não tem uma raiz válida.")
    rules = raw.get("rules") if isinstance(raw.get("rules"), dict) else {}
    out = {"schema": SCHEMA_SCENE, "name": text(raw.get("name"), name or "Main", MAX_NAME), "kind": kind, "settings": norm_settings(raw.get("settings"), kind),
           "rules": {"win": rules.get("win") if rules.get("win") in RULE_WINS else "reach_goal"}, "root": root}
    if isinstance(raw.get("notes"), str):
        out["notes"] = text(raw["notes"], "", 2000)
    return out


def count_nodes(node: Dict[str, Any]) -> int:
    return 1 + sum(count_nodes(c) for c in node.get("children", []))


def walk(node: Dict[str, Any]):
    yield node
    for c in node.get("children", []):
        yield from walk(c)


# ============================================================================ mapas
MAP2D_MAX = (160, 100)
MAP3D_MAX_RES = 129


def norm_map(raw: Any) -> Dict[str, Any]:
    """Mapa válido (2D de blocos ou 3D de alturas). Grades fora do tamanho máximo são cortadas; células inválidas viram vazio."""
    if not isinstance(raw, dict):
        raise ValueError("O mapa precisa ser um objeto JSON.")
    kind = "3d" if raw.get("kind") == "3d" else "2d"
    out: Dict[str, Any] = {"schema": SCHEMA_MAP, "kind": kind, "name": text(raw.get("name"), "Mapa", 60), "theme": raw.get("theme") if raw.get("theme") in THEMES else "forest",
                           "seed": int(clamp(float(raw.get("seed") or 0), 0, 2 ** 31)) if isinstance(raw.get("seed"), (int, float)) else 0,
                           "genre": raw.get("genre") if raw.get("genre") in GENRES else ""}
    objs = []
    for o in (raw.get("objects") if isinstance(raw.get("objects"), list) else [])[:1500]:
        if isinstance(o, dict) and isinstance(o.get("type"), str) and re.match(r"^[a-z_]{1,20}$", o["type"]):
            item: Dict[str, Any] = {"type": o["type"]}
            for k in ("x", "y", "z", "s", "ry"):
                if k in o:
                    try:
                        v = round(clamp(float(o[k]), -1e5, 1e5), 3)
                        item[k] = int(v) if v == int(v) else v   # blocos do mapa 2D são inteiros
                    except (TypeError, ValueError, OverflowError):
                        pass
            for k in ("name", "dialogue"):
                if isinstance(o.get(k), str):
                    item[k] = text(o[k], "", 60)
            if isinstance(o.get("range"), (int, float)):
                item["range"] = round(clamp(float(o["range"]), 0, 5000), 2)
            objs.append(item)
    out["objects"] = objs
    if kind == "2d":
        w = int(clamp(float(raw.get("w") or 0), 4, MAP2D_MAX[0]))
        h = int(clamp(float(raw.get("h") or 0), 4, MAP2D_MAX[1]))
        pal_in = raw.get("palette") if isinstance(raw.get("palette"), dict) else {}
        pal: Dict[str, Any] = {}
        for k, v in list(pal_in.items())[:64]:
            if re.match(r"^\d{1,3}$", str(k)) and isinstance(v, dict):
                e: Dict[str, Any] = {"name": text(v.get("name"), f"bloco {k}", 40), "color": v.get("color") if _COLOR.match(str(v.get("color") or "")) else "#888888", "solid": v.get("solid") is True}
                if v.get("kind") in ("water", "grass", "stone", "dirt", "sand", "snow", "wood", "lava", "brick", "ice"):
                    e["kind"] = v["kind"]
                if isinstance(v.get("image"), str):
                    e["image"] = text(v["image"], "", 60)
                pal[str(k)] = e
        layers_in = raw.get("layers") if isinstance(raw.get("layers"), list) else []
        data_in = (layers_in[0].get("data") if layers_in and isinstance(layers_in[0], dict) else raw.get("grid")) or []
        grid = []
        for y in range(h):
            row_in = data_in[y] if y < len(data_in) and isinstance(data_in[y], list) else []
            row = []
            for x in range(w):
                try:
                    v = int(row_in[x]) if x < len(row_in) else 0
                except (TypeError, ValueError):
                    v = 0
                row.append(v if str(v) in pal or v == 0 else 0)
            grid.append(row)
        out.update({"tile": int(clamp(float(raw.get("tile") or 32), 8, 128)), "w": w, "h": h, "palette": pal, "layers": [{"name": "chão", "data": grid}]})
        hts = raw.get("heights")
        if isinstance(hts, list):
            hh = []
            for y in range(h):
                row_in = hts[y] if y < len(hts) and isinstance(hts[y], list) else []
                hh.append([int(clamp(float(row_in[x]), 0, 16)) if x < len(row_in) and isinstance(row_in[x], (int, float)) else 1 for x in range(w)])
            out["heights"] = hh
        if raw.get("walls") is False:
            out["walls"] = False
    else:
        res = int(clamp(float(raw.get("res") or 65), 17, MAP3D_MAX_RES))
        hm_in = raw.get("heights") if isinstance(raw.get("heights"), list) else []
        hm = []
        for i in range(res * res):
            try:
                v = int(clamp(float(hm_in[i]), 0, 255)) if i < len(hm_in) else 0
            except (TypeError, ValueError):
                v = 0
            hm.append(v)
        cols_in = raw.get("colors") if isinstance(raw.get("colors"), dict) else {}
        out.update({"res": res, "size": round(clamp(float(raw.get("size") or 200), 20, 2000), 1), "height": round(clamp(float(raw.get("height") or 24), 1, 300), 1), "water_level": round(clamp(float(raw.get("water_level") if raw.get("water_level") is not None else 0.18), 0, 0.9), 3),
                    "heights": hm, "biome": raw.get("biome") if raw.get("biome") in BIOMES else "temperate", "colors": {k: v for k, v in cols_in.items() if k in ("low", "mid", "high", "peak", "shore", "water") and _COLOR.match(str(v))}})
    return out


# ============================================================================ projeto
def norm_project_settings(raw: Any, kind: str) -> Dict[str, Any]:
    s = raw if isinstance(raw, dict) else {}
    audio = s.get("audio") if isinstance(s.get("audio"), dict) else {}
    ev = audio.get("events") if isinstance(audio.get("events"), dict) else {}
    return {"hp": int(clamp(float(s.get("hp") or 3), 1, 99)) if isinstance(s.get("hp"), (int, float)) else 3,
            "audio": {"music": text(audio.get("music"), "", 60), "events": {text(k, "", 24): text(v, "", 60) for k, v in list(ev.items())[:24] if isinstance(k, str)}},
            "orientation": s.get("orientation") if s.get("orientation") in ("any", "landscape", "portrait") else "landscape",
            "fullscreen": s.get("fullscreen") is not False,
            "package": re.sub(r"[^a-z0-9.]", "", str(s.get("package") or "").lower())[:60]}
