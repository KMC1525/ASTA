"""Contrato de dados dos jogos 2D + validação determinística.

A IA escreve DADOS; os motores (runtime2d/*.js) são código revisado. Tudo que um modelo produz passa
por aqui: tipos, limites, referências (mapas, itens, rótulos…) e expressões de condição são validados
e consertados — um jogo jogável é sempre entregue.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..cards import normalize_appearance
from ..util import num, slugify, text
from . import GENRES

SCHEMA = "asta.game2d.v1"
GENRE_IDS = tuple(GENRES)
THEMES = ("fantasy", "forest", "night", "desert", "snow", "dungeon", "city", "space", "sea", "retro", "horror", "cozy", "sunset")
THEME_COLORS = {  # (céu, chão) — só para o card da biblioteca; as paletas completas ficam em runtime2d/common.js
    "fantasy": ("#3a2f6b", "#1c1838"), "forest": ("#2c5a4a", "#16301f"), "night": ("#101840", "#0a0f26"), "desert": ("#e0a458", "#a8692f"),
    "snow": ("#a9c7e8", "#e8f1fa"), "dungeon": ("#2a2630", "#141218"), "city": ("#3b4a6b", "#1b2236"), "space": ("#0b0b2a", "#05050f"),
    "sea": ("#1f6f9f", "#0d3b5c"), "retro": ("#ff6a88", "#2b1b4a"), "horror": ("#2a0f14", "#0d0507"), "cozy": ("#f2b97d", "#7a4a2b"),
    "sunset": ("#ff8a5c", "#3b2145"),
}
MOODS = ("calm", "tense", "mysterious", "epic", "melancholic", "joyful")
SCALES = ("major", "minor", "dorian", "phrygian", "pentatonic", "lydian")
SFX = ("chime", "door", "hit", "jump", "coin", "select", "step", "wind", "magic", "powerup", "explosion", "laser", "error")
EXPRESSIONS = ("neutral", "happy", "sad", "angry", "surprised", "shy")
SCENES = ("forest", "room", "city", "beach", "school", "cafe", "night_sky", "castle", "cave", "street", "library", "garden", "sunset",
          "office", "bedroom", "field", "lab", "ship", "kitchen", "cellar")
RPG_TILES = ".,=_#H~T^SBFD"
RPG_SOLID = "#H~T^"
PLAT_TILES = ".#=^CPFEBJKHS"
SHAPES = ("door", "chest", "table", "window", "plant", "npc", "sign", "item", "painting", "lamp", "box", "bed", "book", "key", "machine",
          "tree", "rock", "shelf", "fireplace", "clock", "statue", "gate")
ENEMY_SHAPES = ("slime", "bat", "skull", "goblin", "wolf", "ghost", "dragon", "orb")
SS_SHAPES = ("saucer", "blob", "fish", "bird", "ship", "rock")
CLASSES = ("warrior", "mage", "rogue", "cleric")
RPG_KINDS = {"npc": "action", "chest": "action", "sign": "action", "warp": "touch", "enemy": "touch", "trigger": "touch", "heal": "action"}
LENGTHS = ("short", "medium", "long")
# tamanhos pedidos aos agentes por duração (a validação usa os limites rígidos de HARD)
LENGTH = {
    "short": {"vn_stmts": 90, "rpg_maps": 3, "plat_levels": 2, "ss_stages": 2, "pc_scenes": 3},
    "medium": {"vn_stmts": 200, "rpg_maps": 4, "plat_levels": 3, "ss_stages": 3, "pc_scenes": 4},
    "long": {"vn_stmts": 420, "rpg_maps": 6, "plat_levels": 5, "ss_stages": 5, "pc_scenes": 6},
}
HARD = {"vn_stmts": 900, "vn_labels": 90, "vn_chars": 12, "rpg_maps": 12, "rpg_events": 40, "cmds": 80, "plat_levels": 10, "ss_stages": 8,
        "ss_waves": 60, "pc_scenes": 12, "pc_hotspots": 16, "text": 700}

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_VAR = re.compile(r"^[a-z_][a-z0-9_]{0,30}$")


def _hex(v: Any, default: str) -> str:
    v = str(v or "").strip()
    return v.lower() if _HEX.match(v) else default


def _id(v: Any, default: str = "x", n: int = 32) -> str:
    return slugify(str(v or ""), default, n).replace("-", "_")


def _var(v: Any) -> str:
    s = _id(v, "", 31)
    return s if _VAR.match(s) and s not in ("and", "or", "not", "true", "false") else ""


def _pick(v: Any, options, default):
    v = str(v or "").strip().lower()
    return v if v in options else default


def _list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


# --------------------------------------------------------------------------- condições (sem eval)

_TOK = re.compile(r"""\s*(?:(?P<num>\d+(?:\.\d+)?)|(?P<str>'[^']*'|"[^"]*")|(?P<id>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>==|!=|<=|>=|<|>|\(|\)))""")


def parse_cond(expr: Any) -> Optional[Tuple[str, List[str]]]:
    """Valida uma condição (`afeto >= 3 and not visto`) e devolve (texto normalizado, variáveis usadas) ou None."""
    src = str(expr or "").strip()
    if not src or len(src) > 200:
        return None
    toks: List[Tuple[str, str]] = []
    pos = 0
    while pos < len(src):
        m = _TOK.match(src, pos)
        if not m or m.end() == pos:
            return None
        pos = m.end()
        kind = m.lastgroup or ""
        toks.append((kind, m.group(kind)))
        if src[pos:].strip() == "":
            break
    idents: List[str] = []
    i = 0

    def peek() -> Tuple[str, str]:
        return toks[i] if i < len(toks) else ("", "")

    def atom() -> bool:
        nonlocal i
        k, v = peek()
        if k in ("num", "str"):
            i += 1
            return True
        if k == "id" and v not in ("and", "or", "not"):
            i += 1
            if v not in ("true", "false"):
                idents.append(v)
            return True
        if (k, v) == ("op", "("):
            i += 1
            if not orx() or peek() != ("op", ")"):
                return False
            i += 1
            return True
        return False

    def cmp() -> bool:
        nonlocal i
        if peek() == ("id", "not"):
            i += 1
            return cmp()
        if not atom():
            return False
        if peek()[0] == "op" and peek()[1] in ("==", "!=", "<", "<=", ">", ">="):
            i += 1
            return atom()
        return True

    def andx() -> bool:
        nonlocal i
        if not cmp():
            return False
        while peek() == ("id", "and"):
            i += 1
            if not cmp():
                return False
        return True

    def orx() -> bool:
        nonlocal i
        if not andx():
            return False
        while peek() == ("id", "or"):
            i += 1
            if not andx():
                return False
        return True

    if not orx() or i != len(toks):
        return None
    return " ".join(v for _, v in toks), idents


class Ctx:
    """Referências compartilhadas durante a validação (variáveis, itens, mapas…)."""

    def __init__(self, **refs: Any):
        self.vars: Dict[str, Any] = {}
        self.warnings: List[str] = []
        self.__dict__.update(refs)

    def declare(self, name: str, value: Any = 0) -> None:
        if name and name not in self.vars and len(self.vars) < 80:
            self.vars[name] = value

    def cond(self, expr: Any) -> str:
        r = parse_cond(expr)
        if not r:
            return ""
        for v in r[1]:
            self.declare(_var(v) or "x")
        return r[0]

    def warn(self, msg: str) -> None:
        if len(self.warnings) < 40:
            self.warnings.append(msg)


def _value(v: Any) -> Any:
    if isinstance(v, bool) or isinstance(v, (int, float)):
        return v
    s = str(v if v is not None else "").strip()
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return s[:80]


def _set_cmd(c: dict, ctx: Ctx) -> Optional[dict]:
    name = _var(c.get("var") or c.get("flag"))
    if not name:
        return None
    op = _pick(c.get("op"), ("=", "+=", "-="), "=")
    val = _value(c.get("value", True if op == "=" else 1))
    if op != "=" and (isinstance(val, bool) or not isinstance(val, (int, float))):
        op = "="  # += / -= só fazem sentido com números
    ctx.declare(name, False if isinstance(val, bool) else ("" if isinstance(val, str) else 0))
    return {"c": "set", "var": name, "op": op, "value": val}


def _txt(v: Any, n: int = HARD["text"]) -> str:
    return text(v, "", n)


def _ckey(c: dict) -> str:
    return str(c.get("c") or c.get("type") or c.get("t") or c.get("cmd") or "").lower()


# --------------------------------------------------------------------------- comandos de evento (RPG e point & click)


def norm_cmds(cmds: Any, ctx: Ctx, kind: str, depth: int = 0) -> List[dict]:
    out: List[dict] = []
    for c in _list(cmds)[: HARD["cmds"]]:
        c = _dict(c)
        k = _ckey(c)
        if k == "say":
            body = _txt(c.get("text"))
            if body:
                out.append({"c": "say", "who": text(c.get("who"), "", 40), "text": body})
        elif k == "choice" and depth < 3:
            opts = []
            for o in _list(c.get("options") or c.get("choices"))[:5]:
                o = _dict(o)
                if text(o.get("text"), ""):
                    opts.append({"text": text(o.get("text"), "", 100), "do": norm_cmds(o.get("do") or o.get("commands"), ctx, kind, depth + 1)})
            if opts:
                out.append({"c": "choice", "options": opts})
        elif k == "set":
            s = _set_cmd(c, ctx)
            if s:
                out.append(s)
        elif k == "item":
            iid = _id(c.get("id") or c.get("item"), "")
            n = int(num(c.get("n", 1), 1, -99, 99))
            if iid in ctx.items and n:
                out.append({"c": "item", "id": iid, "n": n})
            elif iid and kind == "rpg":
                ctx.warn(f"comando item: '{iid}' não existe")
        elif k == "gold" and kind == "rpg":
            out.append({"c": "gold", "n": int(num(c.get("n"), 0, -9999, 9999))})
        elif k == "heal" and kind == "rpg":
            out.append({"c": "heal"})
        elif k == "warp" and kind == "rpg":
            mid = _id(c.get("map"), "")
            if mid in ctx.maps:
                out.append({"c": "warp", "map": mid, "x": int(num(c.get("x"), 1, 0, 99)), "y": int(num(c.get("y"), 1, 0, 99))})
            else:
                ctx.warn(f"warp para mapa inexistente '{mid}' removido")
        elif k == "battle" and kind == "rpg":
            enemies = [e for e in [_id(x, "") for x in _list(c.get("enemies"))[:4]] if e in ctx.enemies]
            if enemies:
                out.append({"c": "battle", "enemies": enemies, "boss": bool(c.get("boss")), "win": norm_cmds(c.get("win"), ctx, kind, depth + 1),
                            "lose": _pick(c.get("lose"), ("gameover", "continue"), "gameover")})
        elif k == "shop" and kind == "rpg":
            its = [i for i in [_id(x, "") for x in _list(c.get("items"))[:10]] if i in ctx.items]
            if its:
                out.append({"c": "shop", "items": its})
        elif k == "recruit" and kind == "rpg":
            pid = _id(c.get("id"), "")
            if pid in ctx.party_ids:
                out.append({"c": "recruit", "id": pid})
        elif k == "remove" and kind == "rpg":
            out.append({"c": "remove"})
        elif k == "hide" and kind == "pc":
            out.append({"c": "hide"})
        elif k == "goto" and kind == "pc":
            sid = _id(c.get("scene"), "")
            if sid in ctx.scenes:
                out.append({"c": "goto", "scene": sid})
            else:
                ctx.warn(f"goto para cena inexistente '{sid}' removido")
        elif k == "if" and depth < 3:
            cond = ctx.cond(c.get("cond"))
            if cond:
                out.append({"c": "if", "cond": cond, "then": norm_cmds(c.get("then"), ctx, kind, depth + 1), "else": norm_cmds(c.get("else"), ctx, kind, depth + 1)})
        elif k == "end":
            out.append({"c": "end", "title": text(c.get("title"), "", 80)})
        elif k == "sfx":
            out.append({"c": "sfx", "name": _pick(c.get("name"), SFX, "chime")})
    return out


# --------------------------------------------------------------------------- cabeçalho comum


def _header(raw: dict, genre: str, language: str, fallback_title: str) -> dict:
    style = _dict(raw.get("style"))
    audio = _dict(raw.get("audio"))
    music = _dict(audio.get("music"))
    theme = _pick(style.get("theme"), THEMES, "fantasy")
    return {
        "schema": SCHEMA, "genre": genre, "title": text(raw.get("title"), fallback_title, 80), "description": text(raw.get("description"), "", 400),
        "language": text(raw.get("language"), language, 12),
        "style": {"theme": theme, "accent": _hex(style.get("accent"), "#ffd166"), "pixel": bool(style.get("pixel", True))},
        "audio": {"music": {"enabled": music.get("enabled", True) is not False, "mood": _pick(music.get("mood"), MOODS, "calm"),
                            "scale": _pick(music.get("scale"), SCALES, "major"), "tempo": int(num(music.get("tempo"), 90, 50, 170))},
                  "sfx": audio.get("sfx", True) is not False},
    }


# --------------------------------------------------------------------------- visual novel


def _vn_stmts(stmts: Any, ctx: Ctx, depth: int = 0) -> List[dict]:
    out: List[dict] = []
    for s in _list(stmts):
        if ctx.count >= HARD["vn_stmts"]:
            break
        s = _dict(s)
        k = _ckey(s)
        ctx.count += 1
        if k == "scene":
            bg = _id(s.get("bg") or s.get("background"), "room")
            if bg not in ctx.bgs:
                ctx.bgs[bg] = {"scene": bg if bg in SCENES else "room"}
            out.append({"c": "scene", "bg": bg})
        elif k == "show":
            cid = ctx.char(s.get("char") or s.get("who"))
            out.append({"c": "show", "char": cid, "expr": _pick(s.get("expr") or s.get("expression"), EXPRESSIONS, "neutral"), "at": _pick(s.get("at"), ("left", "center", "right"), "center")})
        elif k == "hide":
            out.append({"c": "hide", "char": ctx.char(s.get("char") or s.get("who"))})
        elif k == "say":
            body = _txt(s.get("text"))
            who = str(s.get("who") or "").strip()
            if not body:
                continue
            narrator = who.lower() in ("", "narrator", "narrador", "narradora", "nobody", "none")
            out.append({"c": "say", "who": "" if narrator else ctx.char(who), "text": body})
        elif k == "menu" and depth < 4:
            choices = []
            for ch in _list(s.get("choices"))[:6]:
                ch = _dict(ch)
                label = text(ch.get("text"), "", 140)
                if not label:
                    continue
                sets = [x for x in (_set_cmd(_dict(a), ctx) for a in _list(ch.get("set"))[:4]) if x]
                choices.append({"text": label, "jump": _id(ch.get("jump") or ch.get("label"), ""), "set": sets, "if": ctx.cond(ch.get("if")) if ch.get("if") else ""})
            if choices:
                out.append({"c": "menu", "prompt": text(s.get("prompt"), "", 200), "choices": choices})
        elif k == "jump":
            out.append({"c": "jump", "label": _id(s.get("label") or s.get("to"), "")})
        elif k == "set":
            x = _set_cmd(s, ctx)
            if x:
                out.append(x)
        elif k == "if" and depth < 4:
            cond = ctx.cond(s.get("cond"))
            if cond:
                out.append({"c": "if", "cond": cond, "then": _vn_stmts(s.get("then"), ctx, depth + 1), "else": _vn_stmts(s.get("else"), ctx, depth + 1)})
        elif k == "input":
            name = _var(s.get("var")) or "player"
            ctx.declare(name, text(s.get("default"), "", 30))
            out.append({"c": "input", "var": name, "prompt": text(s.get("prompt"), "", 120), "default": text(s.get("default"), "", 30)})
        elif k == "music":
            m = str(s.get("mood") or "").lower()
            out.append({"c": "music", "mood": m if m in MOODS or m == "stop" else "calm"})
        elif k == "sfx":
            out.append({"c": "sfx", "name": _pick(s.get("name"), SFX, "chime")})
        elif k == "wait":
            out.append({"c": "wait", "seconds": round(num(s.get("seconds"), 1, 0.2, 5), 1)})
        elif k == "end":
            out.append({"c": "end", "title": text(s.get("title"), "", 80)})
    return out


class _VnCtx(Ctx):
    def __init__(self) -> None:
        super().__init__(count=0, bgs={}, chars={}, items={}, maps={}, enemies={}, party_ids=set(), scenes={})

    def char(self, ref: Any) -> str:
        cid = _id(ref, "x")
        if cid not in self.chars and len(self.chars) < HARD["vn_chars"]:
            self.chars[cid] = {"id": cid, "name": text(ref, cid.title(), 40), "color": "#e8e8e8", "appearance": normalize_appearance({})}
        return cid if cid in self.chars else next(iter(self.chars), cid)


def _terminal(stmts: List[dict]) -> bool:
    if not stmts:
        return False
    last = stmts[-1]
    if last["c"] in ("jump", "end"):
        return True
    if last["c"] == "menu":
        return all(ch.get("jump") for ch in last["choices"])
    if last["c"] == "if":
        return _terminal(last["then"]) and _terminal(last["else"])
    return False


def _fix_jumps(stmts: List[dict], labels: Set[str]) -> List[dict]:
    out = []
    for s in stmts:
        if s["c"] == "jump":
            out.append(s if s["label"] in labels else {"c": "end", "title": ""})
        elif s["c"] == "menu":
            for ch in s["choices"]:
                if ch["jump"] and ch["jump"] not in labels:
                    ch["jump"] = ""
            out.append(s)
        elif s["c"] == "if":
            s["then"], s["else"] = _fix_jumps(s["then"], labels), _fix_jumps(s["else"], labels)
            out.append(s)
        else:
            out.append(s)
    return out


def normalize_vn(raw: dict, ctx: Optional[_VnCtx] = None) -> dict:
    ctx = ctx or _VnCtx()
    for c in _list(raw.get("characters"))[: HARD["vn_chars"]]:
        c = _dict(c)
        cid = _id(c.get("id") or c.get("name"), "x")
        ctx.chars[cid] = {"id": cid, "name": text(c.get("name"), cid.title(), 40), "color": _hex(c.get("color"), "#e8e8e8"),
                          "appearance": normalize_appearance(c.get("appearance"))}
    bgs = raw.get("backgrounds")
    items = bgs.items() if isinstance(bgs, dict) else [((_dict(b).get("id") or _dict(b).get("scene")), b) for b in _list(bgs)]
    for bid, b in items:
        b = b if isinstance(b, dict) else {"scene": b}
        bid = _id(bid, "room")
        ctx.bgs[bid] = {"scene": _pick(b.get("scene") or b.get("theme") or bid, SCENES, "room"), **({"tint": _hex(b.get("tint"), "")} if _hex(b.get("tint"), "") else {})}
    for k, v in _dict(raw.get("variables")).items():
        name = _var(k)
        if name:
            ctx.declare(name, _value(v))
    labels: Dict[str, List[dict]] = {}
    for name, stmts in list(_dict(raw.get("labels")).items())[: HARD["vn_labels"]]:
        lab = _id(name, "")
        if lab:
            labels[lab] = _vn_stmts(stmts, ctx)
    if not labels:
        labels["start"] = [{"c": "say", "who": "", "text": "..."}]
    start = _id(raw.get("start"), "start")
    if start not in labels:
        start = next(iter(labels))
    names = set(labels)
    for lab in labels:
        labels[lab] = _fix_jumps(labels[lab], names)
        if not _terminal(labels[lab]):
            labels[lab].append({"c": "end", "title": ""})
    if not ctx.bgs:
        ctx.bgs["room"] = {"scene": "room"}
    return {"characters": list(ctx.chars.values()), "backgrounds": ctx.bgs, "variables": ctx.vars, "start": start, "labels": labels}


# --------------------------------------------------------------------------- RPG


def _norm_map_rows(rows: Any, legend: str, default: str, min_w: int, max_w: int, min_h: int, max_h: int) -> List[str]:
    rs = [str(r) for r in _list(rows) if isinstance(r, str)][:max_h]
    if not rs:
        rs = [default * min_w for _ in range(min_h)]
    w = max(min_w, min(max(len(r) for r in rs), max_w))
    rs = [("".join(ch if ch in legend else default for ch in r))[:w].ljust(w, default) for r in rs]
    while len(rs) < min_h:
        rs.append(default * w)
    return rs


def _walkable(rows: List[str], x: int, y: int) -> bool:
    return 0 <= y < len(rows) and 0 <= x < len(rows[0]) and rows[y][x] not in RPG_SOLID


def _nearest_walkable(rows: List[str], x: int, y: int) -> Tuple[int, int]:
    x, y = max(0, min(x, len(rows[0]) - 1)), max(0, min(y, len(rows) - 1))
    for r in range(0, max(len(rows), len(rows[0]))):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if max(abs(dx), abs(dy)) == r and _walkable(rows, x + dx, y + dy):
                    return x + dx, y + dy
    rows[y] = rows[y][:x] + "." + rows[y][x + 1:]
    return x, y


def normalize_rpg(raw: dict) -> dict:
    ctx = Ctx(items={}, maps={}, enemies={}, party_ids=set(), scenes={})
    items = _dict(raw.get("items"))
    for iid, it in list(items.items())[:40]:
        it, iid = _dict(it), _id(iid, "")
        if iid:
            ctx.items[iid] = {"name": text(it.get("name"), iid.title(), 40), "kind": _pick(it.get("kind"), ("heal_hp", "heal_mp", "key"), "heal_hp"),
                              "amount": int(num(it.get("amount"), 20, 0, 999)), "price": int(num(it.get("price"), 10, 0, 9999)), "desc": text(it.get("desc"), "", 120)}
    enemies = _dict(raw.get("enemies"))
    for eid, e in list(enemies.items())[:30]:
        e, eid = _dict(e), _id(eid, "")
        if eid:
            ctx.enemies[eid] = {"name": text(e.get("name"), eid.title(), 40), "hp": int(num(e.get("hp"), 14, 1, 9999)), "atk": int(num(e.get("atk"), 5, 1, 999)),
                                "def": int(num(e.get("def"), 1, 0, 999)), "spd": int(num(e.get("spd"), 4, 1, 99)), "xp": int(num(e.get("xp"), 6, 0, 9999)),
                                "gold": int(num(e.get("gold"), 3, 0, 9999)), "color": _hex(e.get("color"), "#6bd16b"), "shape": _pick(e.get("shape"), ENEMY_SHAPES, "slime"),
                                "boss": bool(e.get("boss"))}
    if not ctx.enemies:
        ctx.enemies["slime"] = {"name": "Slime", "hp": 12, "atk": 4, "def": 1, "spd": 3, "xp": 6, "gold": 3, "color": "#6bd16b", "shape": "slime", "boss": False}
    if not ctx.items:
        ctx.items["potion"] = {"name": "Potion", "kind": "heal_hp", "amount": 25, "price": 12, "desc": ""}
    skills: Dict[str, dict] = {}
    for sid, s in list(_dict(raw.get("skills")).items())[:30]:
        s, sid = _dict(s), _id(sid, "")
        if sid:
            skills[sid] = {"name": text(s.get("name"), sid.title(), 40), "mp": int(num(s.get("mp"), 3, 0, 99)), "kind": _pick(s.get("kind"), ("damage", "heal"), "damage"),
                           "power": round(num(s.get("power"), 1.5, 0.3, 6), 2), "stat": _pick(s.get("stat"), ("atk", "mag"), "mag"),
                           "target": _pick(s.get("target"), ("enemy", "all_enemies", "ally", "all_allies"), "enemy")}
    party = []
    for p in _list(raw.get("party"))[:5]:
        p = _dict(p)
        pid = _id(p.get("id") or p.get("name"), "hero")
        cls = _pick(p.get("cls") or p.get("class"), CLASSES, "warrior")
        party.append({"id": pid, "name": text(p.get("name"), pid.title(), 30), "cls": cls, "level": int(num(p.get("level"), 1, 1, 50)),
                      "hp": int(num(p.get("hp"), 30, 5, 999)), "mp": int(num(p.get("mp"), 8, 0, 999)), "atk": int(num(p.get("atk"), 7, 1, 99)),
                      "def": int(num(p.get("def"), 3, 0, 99)), "mag": int(num(p.get("mag"), 4, 0, 99)), "spd": int(num(p.get("spd"), 5, 1, 99)),
                      "skills": [s for s in (_id(x, "") for x in _list(p.get("skills"))[:5]) if s in skills], "appearance": normalize_appearance(p.get("appearance"))})
    if not party:
        party = [{"id": "hero", "name": "Hero", "cls": "warrior", "level": 1, "hp": 30, "mp": 8, "atk": 7, "def": 3, "mag": 4, "spd": 5, "skills": [], "appearance": normalize_appearance({})}]
    ctx.party_ids = {p["id"] for p in party}
    start_party = [i for i in (_id(x, "") for x in _list(raw.get("start_party"))) if i in ctx.party_ids] or [party[0]["id"]]

    raw_maps = raw.get("maps")
    entries = list(raw_maps.items()) if isinstance(raw_maps, dict) else [(_dict(m).get("id") or _dict(m).get("name"), m) for m in _list(raw_maps)]
    entries = entries[: HARD["rpg_maps"]]
    for mid, m in entries:
        ctx.maps[_id(mid, "map")] = _dict(m)
    maps: Dict[str, dict] = {}
    for mid, m in ctx.maps.items():
        rows = _norm_map_rows(m.get("tiles"), RPG_TILES, ".", 12, 60, 10, 40)
        events = []
        for e in _list(m.get("events"))[: HARD["rpg_events"]]:
            e = _dict(e)
            kind = _pick(e.get("kind") or e.get("type"), RPG_KINDS, "npc")
            x, y = int(num(e.get("x"), 1, 0, len(rows[0]) - 1)), int(num(e.get("y"), 1, 0, len(rows) - 1))
            pages_raw = _list(e.get("pages")) or [{"commands": e.get("commands") or e.get("dialog")}]
            pages = []
            for pg in pages_raw[:6]:
                pg = _dict(pg)
                cond = ctx.cond(pg.get("if")) if pg.get("if") else ""
                cmds = norm_cmds(pg.get("commands") if pg.get("commands") is not None else pg.get("do"), ctx, "rpg")
                if cmds or kind in ("heal", "trigger"):
                    pages.append({"if": cond, "commands": cmds})
            if not pages and kind != "heal":
                continue
            events.append({"id": _id(e.get("id"), f"e{len(events) + 1}"), "kind": kind, "x": x, "y": y, "name": text(e.get("name"), "", 30),
                           "trigger": _pick(e.get("trigger"), ("action", "touch", "auto"), RPG_KINDS[kind]), "pages": pages,
                           "appearance": normalize_appearance(e.get("appearance")), "icon": text(e.get("icon"), "", 4),
                           "solid": e.get("solid", kind in ("npc", "chest", "sign", "enemy", "heal")) is not False})
        enc = _dict(m.get("encounters"))
        groups = [[g for g in [_id(x, "") for x in _list(grp)[:4]] if g in ctx.enemies] for grp in _list(enc.get("groups"))[:6]]
        groups = [g for g in groups if g]
        maps[mid] = {"id": mid, "name": text(m.get("name"), mid.title(), 40), "theme": _pick(m.get("theme"), ("grass", "snow", "desert", "dungeon", "town", "cave", "forest", "castle"), "grass"),
                     "music": _pick(m.get("music"), MOODS, "calm"), "tiles": rows, "events": events,
                     "encounters": {"rate": round(num(enc.get("rate"), 0.0, 0, 0.3), 2) if groups else 0.0, "groups": groups}}
    if not maps:
        maps["start"] = {"id": "start", "name": "Start", "theme": "grass", "music": "calm", "tiles": ["." * 16] * 12, "events": [], "encounters": {"rate": 0.0, "groups": []}}
    st = _dict(raw.get("start"))
    smap = _id(st.get("map"), "")
    if smap not in maps:
        smap = next(iter(maps))
    sx, sy = _nearest_walkable(maps[smap]["tiles"], int(num(st.get("x"), 2, 0, 99)), int(num(st.get("y"), 2, 0, 99)))
    # warps apontam para tiles caminháveis
    for m in maps.values():
        for e in m["events"]:
            _fix_warps(e, maps)
    return {"tile_size": 32, "start": {"map": smap, "x": sx, "y": sy}, "party": party, "start_party": start_party, "skills": skills, "items": ctx.items,
            "enemies": ctx.enemies, "maps": maps, "variables": ctx.vars, "_warnings": ctx.warnings}


def _fix_warps(node: Any, maps: Dict[str, dict]) -> None:
    if isinstance(node, dict):
        if node.get("c") == "warp" and node.get("map") in maps:
            rows = maps[node["map"]]["tiles"]
            node["x"], node["y"] = _nearest_walkable(rows, node["x"], node["y"])
        for v in node.values():
            _fix_warps(v, maps)
    elif isinstance(node, list):
        for v in node:
            _fix_warps(v, maps)


# --------------------------------------------------------------------------- plataforma


def _plat_level(raw: dict, idx: int, width_hint: int = 0) -> dict:
    rows = _norm_map_rows(raw.get("tiles"), PLAT_TILES, ".", 30, 260, 8, 26)
    h, w = len(rows), len(rows[0])
    grid = [list(r) for r in rows]
    if not any(ch == "#" for r in grid for ch in r):  # sem chão: cria
        grid[-1] = ["#"] * w
        grid[-2] = grid[-2]
    # checkpoint (K) sem chão embaixo faria o jogador renascer no vazio: desce até o chão ou remove
    for y in range(h):
        for x in range(w):
            if grid[y][x] == "K":
                below = next((yy for yy in range(y, h) if grid[yy][x] in "#="), None)
                grid[y][x] = "."
                if below is not None and below > 0:
                    grid[below - 1][x] = "K"
    # exatamente um P (início)
    starts = [(x, y) for y, r in enumerate(grid) for x, ch in enumerate(r) if ch == "P"]
    for x, y in starts[1:]:
        grid[y][x] = "."
    if not starts:
        placed = False
        for x in range(1, w):
            col = [grid[y][x] for y in range(h)]
            if "#" in col:
                top = col.index("#")
                if top >= 2:
                    grid[top - 1][x], placed = "P", True
                    break
        if not placed:
            grid[h - 2][1] = "P"
    if not any(ch == "F" for r in grid for ch in r):  # bandeira de chegada perto do fim
        for x in range(w - 2, 0, -1):
            col = [grid[y][x] for y in range(h)]
            if "#" in col and col.index("#") >= 2:
                grid[col.index("#") - 1][x] = "F"
                break
        else:
            grid[h - 2][w - 2] = "F"
    return {"name": text(raw.get("name"), f"Fase {idx + 1}", 40), "theme": _pick(raw.get("theme"), THEMES, "fantasy"), "intro": text(raw.get("intro"), "", 200),
            "tiles": ["".join(r) for r in grid]}


def normalize_platformer(raw: dict) -> dict:
    levels = [_plat_level(_dict(lv), i) for i, lv in enumerate(_list(raw.get("levels"))[: HARD["plat_levels"]])]
    pl = _dict(raw.get("player"))
    return {"player": {"appearance": normalize_appearance(pl.get("appearance")), "lives": int(num(pl.get("lives"), 3, 1, 9)), "hp": int(num(pl.get("hp"), 3, 1, 9)),
                       "double_jump": bool(pl.get("double_jump", False)), "speed": round(num(pl.get("speed"), 1.0, 0.7, 1.5), 2), "jump": round(num(pl.get("jump"), 1.0, 0.8, 1.4), 2)},
            "levels": levels, "ending": text(raw.get("ending"), "", 300)}


# --------------------------------------------------------------------------- side scroller


def normalize_side_scroller(raw: dict) -> dict:
    mode = _pick(raw.get("mode"), ("shooter", "runner"), "shooter")
    enemies: Dict[str, dict] = {}
    for eid, e in list(_dict(raw.get("enemies")).items())[:12]:
        e, eid = _dict(e), _id(eid, "")
        if eid:
            enemies[eid] = {"hp": int(num(e.get("hp"), 1, 1, 200)), "speed": round(num(e.get("speed"), 1.0, 0.3, 3), 2), "score": int(num(e.get("score"), 100, 0, 9999)),
                            "shoots": bool(e.get("shoots", False)), "shape": _pick(e.get("shape"), SS_SHAPES, "saucer"), "color": _hex(e.get("color"), "#ff6b6b")}
    if not enemies:
        enemies["drone"] = {"hp": 1, "speed": 1.0, "score": 100, "shoots": False, "shape": "saucer", "color": "#ff6b6b"}
    stages = []
    for i, st in enumerate(_list(raw.get("stages"))[: HARD["ss_stages"]]):
        st = _dict(st)
        waves = []
        for w in _list(st.get("waves"))[: HARD["ss_waves"]]:
            w = _dict(w)
            eid = _id(w.get("enemy"), "")
            if eid in enemies:
                waves.append({"t": round(num(w.get("t"), 2, 0, 600), 1), "enemy": eid, "count": int(num(w.get("count"), 3, 1, 12)),
                              "pattern": _pick(w.get("pattern"), ("line", "sine", "zigzag", "v", "swarm"), "line"), "y": round(num(w.get("y"), 0.5, 0.05, 0.95), 2),
                              "gap": round(num(w.get("gap"), 0.5, 0.15, 2), 2)})
        obstacles = [{"t": round(num(_dict(o).get("t"), 3, 0, 600), 1), "type": _pick(_dict(o).get("type"), ("rock", "crate", "pit", "flyer"), "rock")} for o in _list(st.get("obstacles"))[:120]]
        pickups = [{"t": round(num(_dict(p).get("t"), 8, 0, 600), 1), "type": _pick(_dict(p).get("type"), ("power", "shield", "heart", "coin"), "coin"), "y": round(num(_dict(p).get("y"), 0.5, 0.05, 0.95), 2)}
                   for p in _list(st.get("pickups"))[:60]]
        boss = _dict(st.get("boss"))
        length = int(num(st.get("length"), 45, 15, 240))
        stages.append({"name": text(st.get("name"), f"Stage {i + 1}", 40), "theme": _pick(st.get("theme"), ("space", "sea", "forest", "city", "desert", "sky", "cave"), "space"),
                       "length": length, "speed": int(num(st.get("speed"), 120, 60, 260)), "waves": sorted(waves, key=lambda w: w["t"]), "obstacles": sorted(obstacles, key=lambda o: o["t"]),
                       "pickups": sorted(pickups, key=lambda p: p["t"]),
                       "boss": ({"t": round(num(boss.get("t"), max(10, length - 12), 5, 600), 1), "name": text(boss.get("name"), "Boss", 40), "hp": int(num(boss.get("hp"), 30, 5, 500)),
                                 "pattern": _pick(boss.get("pattern"), ("strafe", "sweep", "rain"), "strafe"), "color": _hex(boss.get("color"), "#ff4d6d")} if boss and mode == "shooter" else None)})
    pl = _dict(raw.get("player"))
    return {"mode": mode, "player": {"appearance": normalize_appearance(pl.get("appearance")), "hp": int(num(pl.get("hp"), 3, 1, 9)), "speed": round(num(pl.get("speed"), 1.0, 0.7, 1.6), 2),
                                     "fire_rate": round(num(pl.get("fire_rate"), 1.0, 0.5, 2.5), 2), "ship": _pick(pl.get("ship"), ("ship", "girl", "robot", "bird", "fish"), "ship")},
            "stages": stages, "enemies": enemies, "ending": text(raw.get("ending"), "", 300)}


# --------------------------------------------------------------------------- point & click


def normalize_point_and_click(raw: dict) -> dict:
    ctx = Ctx(items={}, maps={}, enemies={}, party_ids=set(), scenes={})
    for iid, it in list(_dict(raw.get("items")).items())[:30]:
        it, iid = _dict(it), _id(iid, "")
        if iid:
            ctx.items[iid] = {"name": text(it.get("name"), iid.title(), 40), "emoji": text(it.get("emoji"), "📦", 4), "desc": text(it.get("desc"), "", 140)}
    raw_scenes = raw.get("scenes")
    entries = list(raw_scenes.items()) if isinstance(raw_scenes, dict) else [(_dict(s).get("id") or _dict(s).get("name"), s) for s in _list(raw_scenes)]
    for sid, s in entries[: HARD["pc_scenes"]]:
        ctx.scenes[_id(sid, "scene")] = _dict(s)
    scenes: Dict[str, dict] = {}
    for sid, s in ctx.scenes.items():
        hs = []
        for hsp in _list(s.get("hotspots"))[: HARD["pc_hotspots"]]:
            hsp = _dict(hsp)
            w, h = num(hsp.get("w"), 0.12, 0.03, 0.6), num(hsp.get("h"), 0.2, 0.03, 0.8)
            verbs = {k: norm_cmds(hsp.get(k), ctx, "pc") for k in ("use", "talk", "take")}
            use_item = {}
            for iid, cmds in list(_dict(hsp.get("use_item")).items())[:8]:
                if _id(iid, "") in ctx.items:
                    use_item[_id(iid, "")] = norm_cmds(cmds, ctx, "pc")
            hs.append({"id": _id(hsp.get("id") or hsp.get("name"), f"h{len(hs) + 1}"), "name": text(hsp.get("name"), "", 40), "x": round(num(hsp.get("x"), 0.4, 0, 1 - w), 3),
                       "y": round(num(hsp.get("y"), 0.3, 0, 1 - h), 3), "w": round(w, 3), "h": round(h, 3), "shape": _pick(hsp.get("shape"), SHAPES, "box"),
                       "look": text(hsp.get("look"), "", 240), **verbs, "use_item": use_item, "if": ctx.cond(hsp.get("if")) if hsp.get("if") else "",
                       "appearance": normalize_appearance(hsp.get("appearance")), "fail": text(hsp.get("fail"), "", 140)})
        scenes[sid] = {"id": sid, "name": text(s.get("name"), sid.title(), 40), "theme": _pick(s.get("theme") or s.get("scene"), SCENES, "room"), "tone": _pick(s.get("tone"), THEMES, "cozy"),
                       "intro": text(s.get("intro"), "", 300), "hotspots": hs}
    if not scenes:
        scenes["room"] = {"id": "room", "name": "Room", "theme": "room", "tone": "cozy", "intro": "", "hotspots": []}
    start = _id(raw.get("start"), "")
    if start not in scenes:
        start = next(iter(scenes))
    return {"start": start, "items": ctx.items, "scenes": scenes, "variables": ctx.vars, "_warnings": ctx.warnings}


# --------------------------------------------------------------------------- entrada

NORMALIZERS = {"visual_novel": normalize_vn, "rpg": normalize_rpg, "platformer": normalize_platformer, "side_scroller": normalize_side_scroller,
               "point_and_click": normalize_point_and_click}


def normalize_game(raw: Any, genre: str, language: str = "pt-BR", fallback_title: str = "Novo jogo") -> Tuple[dict, List[str]]:
    """Valida o spec completo de um jogo. Devolve (spec, avisos)."""
    raw = _dict(raw)
    if genre not in NORMALIZERS:
        raise ValueError(f"Gênero desconhecido: {genre}")
    data = NORMALIZERS[genre](_dict(raw.get("data")) if "data" in raw else raw)
    warnings = list(data.pop("_warnings", []))
    spec = _header(raw, genre, language, fallback_title)
    spec["data"] = data
    return spec, warnings


def game_problems(spec: dict) -> List[str]:
    """Problemas de jogabilidade que o validador não consegue consertar (usado pelo Revisor determinístico)."""
    g, d = spec.get("genre"), spec.get("data", {})
    out: List[str] = []
    if g == "visual_novel":
        ends = _count_cmd(d.get("labels"), "end")
        if not ends:
            out.append("nenhum final (`end`) no roteiro")
        reachable = _vn_reachable(d)
        dead = [l for l in d.get("labels", {}) if l not in reachable]
        if dead:
            out.append("rótulos inalcançáveis: " + ", ".join(dead[:6]))
        if not any(c["c"] == "menu" for stmts in d.get("labels", {}).values() for c in stmts):
            out.append("o roteiro não tem escolhas (`menu`)")
    elif g == "rpg":
        if not _count_cmd(d.get("maps"), "end"):
            out.append("não há como terminar o jogo (nenhum comando `end`)")
        if len(d.get("maps", {})) > 1 and not _count_cmd(d.get("maps"), "warp"):
            out.append("há vários mapas mas nenhum `warp` liga um ao outro")
    elif g == "platformer":
        if not d.get("levels"):
            out.append("nenhuma fase")
    elif g == "side_scroller":
        if not d.get("stages") or not any(st["waves"] or st["obstacles"] for st in d["stages"]):
            out.append("as fases não têm ondas/obstáculos")
    elif g == "point_and_click":
        if not _count_cmd(d.get("scenes"), "end"):
            out.append("não há como terminar o jogo (nenhum comando `end`)")
        if len(d.get("scenes", {})) > 1 and not _count_cmd(d.get("scenes"), "goto"):
            out.append("há várias cenas mas nenhum `goto` liga uma à outra")
    return out


def is_trivial(spec: dict) -> bool:
    """True se o jogo está praticamente vazio (típico de resposta inválida do modelo): vale mais o gerador de regras."""
    g, d = spec.get("genre"), spec.get("data", {})
    if g == "visual_novel":
        return sum(len(v) for v in d.get("labels", {}).values()) < 6
    if g == "rpg":
        return sum(len(m["events"]) for m in d.get("maps", {}).values()) == 0
    if g == "platformer":
        return not d.get("levels")
    if g == "side_scroller":
        return not d.get("stages") or not any(st["waves"] or st["obstacles"] for st in d["stages"])
    if g == "point_and_click":
        return sum(len(sc["hotspots"]) for sc in d.get("scenes", {}).values()) == 0
    return False


def _count_cmd(node: Any, name: str) -> int:
    if isinstance(node, dict):
        return (1 if node.get("c") == name else 0) + sum(_count_cmd(v, name) for v in node.values())
    if isinstance(node, list):
        return sum(_count_cmd(v, name) for v in node)
    return 0


def _vn_reachable(d: dict) -> Set[str]:
    labels = d.get("labels", {})
    seen: Set[str] = set()
    todo = [d.get("start")]

    def targets(stmts: List[dict]) -> List[str]:
        out = []
        for s in stmts:
            if s["c"] == "jump":
                out.append(s["label"])
            elif s["c"] == "menu":
                out += [ch["jump"] for ch in s["choices"] if ch.get("jump")]
            elif s["c"] == "if":
                out += targets(s["then"]) + targets(s["else"])
        return out

    while todo:
        cur = todo.pop()
        if cur in seen or cur not in labels:
            continue
        seen.add(cur)
        todo += targets(labels[cur])
    return seen


def palette_for_game(spec: dict) -> Dict[str, str]:
    """{sky, ground} para o card da biblioteca (mesma forma da paleta dos mundos 3D)."""
    theme = spec.get("style", {}).get("theme", "fantasy")
    sky, ground = THEME_COLORS.get(theme, THEME_COLORS["fantasy"])
    return {"sky": sky, "ground": ground}
