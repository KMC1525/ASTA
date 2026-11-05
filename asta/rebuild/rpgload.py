"""Leitores dos projetos do RPG Maker: MV/MZ (JSON), XP/VX/VX Ace (Marshal do Ruby) e 2000/2003 (LCF) → formato comum de `rpgconv`."""
from __future__ import annotations

import json
import re
import struct
from typing import Any, Dict, List, Optional, Tuple

from . import lcf, marshal
from .rpgconv import Conv

SHAPES = (("slime", "slime|gosma|jelly"), ("bat", "bat|morcego"), ("skull", "skull|skelet|esquelet|undead|zombi"), ("goblin", "goblin|orc|imp|bandit|thief"),
          ("wolf", "wolf|dog|lobo|cao|beast|rat"), ("ghost", "ghost|spirit|fantasm|wraith|spectre"), ("dragon", "dragon|drake|wyrm|dragao"))


def shape_of(name: str) -> str:
    low = (name or "").lower()
    return next((s for s, pat in SHAPES if re.search(pat, low)), "orb")


def cls_of(name: str) -> str:
    low = (name or "").lower()
    if re.search(r"mage|wizard|sorcer|witch|mago|bruxo|black|white mage", low):
        return "mage"
    if re.search(r"thief|rogue|ranger|archer|ladino|ladrao|ninja|hunter", low):
        return "rogue"
    if re.search(r"priest|cleric|healer|monk|saint|padre|clerigo|nun", low):
        return "cleric"
    return "warrior"


def tile_char(ids: List[int], flags: List[int], kind: str = "mv") -> str:
    """ids = camadas de baixo para cima. Passagem pelas flags do tileset (bits 0x0f = bloqueio por direção; 0x10 = «estrela», sem efeito)."""
    if not any(ids):
        return "#"
    solid = None
    for tid in reversed(ids):
        if not tid:
            continue
        f = flags[tid] if 0 <= tid < len(flags) else 0
        if kind == "xp":
            if f & 0x0F:
                solid = True
                break
            continue
        if f & 0x10:
            continue
        solid = (f & 0x0F) == 0x0F
        break
    solid = bool(solid)
    base = ids[0]
    upper = next((t for t in reversed(ids[1:]) if t), 0)
    if kind == "xp":
        if solid:
            return "~" if 0 < base < 384 and base // 48 == 1 else ("T" if upper else "#")
        return "."
    if solid:
        if 2048 <= base <= 2815 and not upper:
            return "~"
        if 5888 <= base <= 8191:
            return "H"
        return "T" if (upper and upper < 1536) else "#"
    if 2816 <= base <= 4351:
        return ","
    if 4352 <= base <= 8191:
        return "_"
    return "."


def _hp(x: Dict[str, Any]) -> Dict[str, Any]:
    return x


# --------------------------------------------------------------------------- MV / MZ


def load_mvmz(src) -> Dict[str, Any]:
    def jread(name: str, default: Any = None) -> Any:
        f = src.find(f"data/{name}.json")
        if not f:
            return default
        try:
            return json.loads(src.text(f))
        except ValueError:
            return default

    sysd = jread("System", {}) or {}
    p: Dict[str, Any] = {"engine": "mz" if ("advanced" in sysd or "tileSize" in sysd) else "mv", "title": sysd.get("gameTitle") or "", "actors": [], "items": {}, "weapons": {}, "armors": {},
                         "enemies": {}, "troops": {}, "common": {}, "maps": {}, "start": {"map": sysd.get("startMapId"), "x": sysd.get("startX"), "y": sysd.get("startY")},
                         "party": sysd.get("partyMembers") or []}
    classes = {c["id"]: c for c in (jread("Classes", []) or []) if c}
    for a in jread("Actors", []) or []:
        if not a:
            continue
        lvl = int(a.get("initialLevel") or 1)
        params = (classes.get(a.get("classId")) or {}).get("params") or []

        def par(i, d):
            try:
                return int(params[i][lvl])
            except (IndexError, TypeError, ValueError):
                return d
        p["actors"].append({"id": a["id"], "name": a.get("name") or f"Herói {a['id']}", "cls": cls_of((classes.get(a.get("classId")) or {}).get("name", "")), "level": lvl,
                            "hp": par(0, 30), "mp": par(1, 8), "atk": par(2, 8), "def": par(3, 4), "mag": par(4, 5), "spd": par(6, 5)})
    for key, fname in (("items", "Items"), ("weapons", "Weapons"), ("armors", "Armors")):
        for it in jread(fname, []) or []:
            if not it:
                continue
            kind, amount = "heal_hp", 25
            if key != "items" or it.get("itypeId") == 2:
                kind = "key"
            for ef in it.get("effects") or []:
                if ef.get("code") == 11:
                    amount, kind = int(ef.get("value2") or 0) or 25, "heal_hp"
                elif ef.get("code") == 12:
                    amount, kind = int(ef.get("value2") or 0) or 10, "heal_mp"
            p[key][it["id"]] = {"name": it.get("name") or f"{key} {it['id']}", "kind": kind, "amount": amount, "price": int(it.get("price") or 0), "desc": it.get("description") or ""}
    for e in jread("Enemies", []) or []:
        if e:
            pr = e.get("params") or [30, 0, 8, 3, 0, 0, 5, 0]
            p["enemies"][e["id"]] = {"name": e.get("name") or f"Monstro {e['id']}", "hp": int(pr[0]), "atk": int(pr[2]), "def": int(pr[3]), "spd": int(pr[6]) if len(pr) > 6 else 5,
                                     "xp": int(e.get("exp") or 0), "gold": int(e.get("gold") or 0), "shape": shape_of(e.get("name", ""))}
    for t in jread("Troops", []) or []:
        if t:
            p["troops"][t["id"]] = [m["enemyId"] for m in t.get("members") or []]
    for ce in jread("CommonEvents", []) or []:
        if ce:
            p["common"][ce["id"]] = _mv_list(ce.get("list"))
    tilesets = {t["id"]: t for t in (jread("Tilesets", []) or []) if t}
    infos = {m["id"]: m for m in (jread("MapInfos", []) or []) if m}
    for f in src.find_all(r"data/map(\d+)\.json$"):
        mid = int(re.search(r"map(\d+)\.json$", f.lower()).group(1))
        try:
            m = json.loads(src.text(f))
        except ValueError:
            continue
        w, h, data = int(m.get("width", 0)), int(m.get("height", 0)), m.get("data") or []
        if w <= 0 or h <= 0 or len(data) < w * h * 4:
            continue
        flags = (tilesets.get(m.get("tilesetId")) or {}).get("flags") or []
        rows = ["".join(tile_char([data[(z * h + y) * w + x] for z in range(4)], flags) for x in range(w)) for y in range(h)]
        step = int(m.get("encounterStep") or 30)
        p["maps"][mid] = {"name": m.get("displayName") or (infos.get(mid) or {}).get("name") or f"Mapa {mid}", "w": w, "h": h, "tiles": rows,
                          "troops": [e.get("troopId") for e in (m.get("encounterList") or [])], "rate": min(0.3, 1.0 / max(5, step)),
                          "events": [_mv_event(ev) for ev in (m.get("events") or []) if ev]}
    return p


def _mv_list(lst: Any) -> List[Dict[str, Any]]:
    return [{"code": int(c.get("code", 0)), "indent": int(c.get("indent", 0)), "p": c.get("parameters") or []} for c in (lst or []) if isinstance(c, dict)]


def _mv_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    pages = []
    for pg in ev.get("pages") or []:
        cd = pg.get("conditions") or {}
        pages.append({"cond": {"switch1_valid": cd.get("switch1Valid"), "switch1_id": cd.get("switch1Id"), "switch2_valid": cd.get("switch2Valid"), "switch2_id": cd.get("switch2Id"),
                               "variable_valid": cd.get("variableValid"), "variable_id": cd.get("variableId"), "variable_value": cd.get("variableValue"),
                               "self_switch_valid": cd.get("selfSwitchValid"), "self_switch_ch": cd.get("selfSwitchCh")},
                      "trigger": pg.get("trigger", 0), "list": _mv_list(pg.get("list"))})
    return {"id": ev.get("id"), "name": ev.get("name") or "", "x": ev.get("x", 0), "y": ev.get("y", 0), "pages": pages}


# --------------------------------------------------------------------------- XP / VX / VX Ace (Marshal)


def load_rgss(src, ext: str) -> Dict[str, Any]:
    """ext: rxdata (XP), rvdata (VX) ou rvdata2 (VX Ace)."""
    xp = ext == "rxdata"

    def rread(name: str) -> Any:
        f = src.find(f"data/{name}.{ext}")
        if not f:
            return None
        try:
            return marshal.loads(src.read(f))
        except (marshal.MarshalError, ValueError, IndexError, RecursionError):
            return None

    sysd = rread("System")
    p: Dict[str, Any] = {"engine": {"rxdata": "xp", "rvdata": "vx", "rvdata2": "ace"}[ext], "title": "", "actors": [], "items": {}, "weapons": {}, "armors": {}, "enemies": {}, "troops": {},
                         "common": {}, "maps": {}, "start": {}, "party": []}
    if isinstance(sysd, marshal.RObj):
        p["title"] = sysd.get("game_title") or ""
        p["start"] = {"map": sysd.get("start_map_id"), "x": sysd.get("start_x"), "y": sysd.get("start_y")}
        p["party"] = list(sysd.get("party_members") or [])
    classes = {o.get("id"): o for o in (rread("Classes") or []) if isinstance(o, marshal.RObj)}
    for a in rread("Actors") or []:
        if isinstance(a, marshal.RObj):
            p["actors"].append({"id": a.get("id"), "name": a.get("name") or "Herói", "cls": cls_of((classes.get(a.get("class_id")) or marshal.RObj("x")).get("name") or ""),
                                "level": int(a.get("initial_level") or 1)})
    for key, fname in (("items", "Items"), ("weapons", "Weapons"), ("armors", "Armors")):
        for it in rread(fname) or []:
            if not isinstance(it, marshal.RObj):
                continue
            kind, amount = ("heal_hp" if key == "items" else "key"), 25
            hp = it.get("recover_hp") or it.get("hp_recovery") or 0
            if key == "items" and hp:
                amount = int(hp)
            if key == "items" and (it.get("itype_id") == 2):
                kind = "key"
            for ef in it.get("effects") or []:
                if isinstance(ef, marshal.RObj) and ef.get("code") == 11:
                    amount = int(ef.get("value2") or 0) or 25
            p[key][it.get("id")] = {"name": it.get("name") or f"{key} {it.get('id')}", "kind": kind, "amount": amount, "price": int(it.get("price") or 0), "desc": it.get("description") or ""}
    for e in rread("Enemies") or []:
        if isinstance(e, marshal.RObj):
            pr = e.get("params")
            if xp:
                hp, atk, df, spd = e.get("maxhp"), e.get("atk"), e.get("pdef"), e.get("agi")
            else:
                hp, atk, df, spd = (list(marshal.table(pr)[3]) + [0] * 8)[:4] if isinstance(pr, marshal.RObj) else (e.get("mhp"), e.get("atk"), e.get("def"), e.get("agi"))
                if isinstance(pr, list):
                    hp, atk, df, spd = (pr + [0] * 8)[0], (pr + [0] * 8)[2], (pr + [0] * 8)[3], (pr + [0] * 8)[6]
            p["enemies"][e.get("id")] = {"name": e.get("name") or "Monstro", "hp": int(hp or 30), "atk": int(atk or 8), "def": int(df or 3), "spd": int(spd or 5),
                                         "xp": int(e.get("exp") or 0), "gold": int(e.get("gold") or 0), "shape": shape_of(e.get("name") or "")}
    for t in rread("Troops") or []:
        if isinstance(t, marshal.RObj):
            p["troops"][t.get("id")] = [m.get("enemy_id") for m in (t.get("members") or []) if isinstance(m, marshal.RObj)]
    for ce in rread("CommonEvents") or []:
        if isinstance(ce, marshal.RObj):
            p["common"][ce.get("id")] = _rg_list(ce.get("list"), xp)
    tilesets = {o.get("id"): o for o in (rread("Tilesets") or []) if isinstance(o, marshal.RObj)}
    infos = rread("MapInfos") or {}
    for f in src.find_all(rf"data/map(\d+)\.{ext}$"):
        mid = int(re.search(r"map(\d+)\.", f.lower()).group(1))
        try:
            m = marshal.loads(src.read(f))
        except (marshal.MarshalError, ValueError, IndexError, RecursionError):
            continue
        if not isinstance(m, marshal.RObj):
            continue
        w, h = int(m.get("width") or 0), int(m.get("height") or 0)
        xs, ys, zs, vals = marshal.table(m.get("data"))
        if w <= 0 or h <= 0 or xs != w or ys != h or len(vals) < w * h:
            continue
        ts = tilesets.get(m.get("tileset_id")) or marshal.RObj("x")
        flags = marshal.table(ts.get("passages") if xp else ts.get("flags"))[3]
        layers = max(1, min(zs, 4))
        rows = ["".join(tile_char([vals[x + y * w + z * w * h] for z in range(layers)], flags, "xp" if xp else "mv") for x in range(w)) for y in range(h)]
        step = int(m.get("encounter_step") or 30)
        name = ((infos.get(mid) if isinstance(infos, dict) else None) or marshal.RObj("x")).get("name") or f"Mapa {mid}"
        evs = []
        for ev in (m.get("events") or {}).values():
            if isinstance(ev, marshal.RObj):
                pages = []
                for pg in ev.get("pages") or []:
                    cd = pg.get("condition") or marshal.RObj("x")
                    pages.append({"cond": {k: cd.get(k) for k in ("switch1_valid", "switch1_id", "switch2_valid", "switch2_id", "variable_valid", "variable_id", "variable_value",
                                                                  "self_switch_valid", "self_switch_ch")},
                                  "trigger": pg.get("trigger") or 0, "list": _rg_list(pg.get("list"), xp)})
                evs.append({"id": ev.get("id"), "name": ev.get("name") or "", "x": ev.get("x") or 0, "y": ev.get("y") or 0, "pages": pages})
        troops = [(g.get("troop_id") if isinstance(g, marshal.RObj) else g) for g in (m.get("encounter_list") or [])]
        p["maps"][mid] = {"name": name, "w": w, "h": h, "tiles": rows, "troops": troops, "rate": min(0.3, 1.0 / max(5, step)), "events": evs}
    return p


def _rg_list(lst: Any, xp: bool) -> List[Dict[str, Any]]:
    out = []
    for c in lst or []:
        if isinstance(c, marshal.RObj):
            d = {"code": int(c.get("code") or 0), "indent": int(c.get("indent") or 0), "p": list(c.get("parameters") or [])}
            if xp and d["code"] == 101:
                d["legacy_text"] = True
            if xp and d["code"] == 301:
                d["legacy_battle"] = True
            out.append(d)
    return out


# --------------------------------------------------------------------------- 2000 / 2003 (LCF)

_LCF = {10110: "msg", 20110: "msg2", 10140: "choice", 20140: "opt", 20141: "optend", 10210: "sw", 10220: "var", 10310: "gold", 10320: "item", 10810: "tele", 10710: "battle",
        20710: "win", 20711: "esc", 20712: "lose", 20713: "bend", 10720: "shop", 20720: "shopitem", 12010: "if", 22010: "else", 12011: "endif", 12310: "exit", 12320: "erase", 12330: "call"}
_LCF_CMP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


def lcf_to_mv(cmds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Comandos do 2000/2003 → numeração do MV/MZ (o que for desconhecido é descartado)."""
    out: List[Dict[str, Any]] = []
    i, n = 0, len(cmds)
    while i < n:
        c = cmds[i]
        k, ind, s, pp = _LCF.get(c["code"]), c["indent"], c["s"], c["p"]
        i += 1
        if k == "msg":
            out.append({"code": 101, "indent": ind, "p": []})
            out.append({"code": 401, "indent": ind, "p": [s]})
            while i < n and cmds[i]["code"] == 20110 and cmds[i]["indent"] == ind:
                out.append({"code": 401, "indent": ind, "p": [cmds[i]["s"]]})
                i += 1
        elif k == "choice":
            opts = []
            j = i
            while j < n and not (cmds[j]["code"] == 20141 and cmds[j]["indent"] == ind):
                if cmds[j]["code"] == 20140 and cmds[j]["indent"] == ind:
                    opts.append(cmds[j]["s"])
                j += 1
            out.append({"code": 102, "indent": ind, "p": [opts, 0]})
            branch = -1
            sub: List[Dict[str, Any]] = []

            def flush(br: int, body: List[Dict[str, Any]]) -> None:
                if br >= 0:
                    out.append({"code": 402, "indent": ind, "p": [br, opts[br] if br < len(opts) else ""]})
                    out.extend(lcf_to_mv(body))

            while i < n:
                cc = cmds[i]
                i += 1
                if cc["indent"] == ind and cc["code"] == 20140:
                    flush(branch, sub)
                    branch, sub = (cc["p"][0] if cc["p"] else branch + 1), []
                elif cc["indent"] == ind and cc["code"] == 20141:
                    flush(branch, sub)
                    out.append({"code": 404, "indent": ind, "p": []})
                    break
                else:
                    sub.append(cc)
        elif k == "sw" and len(pp) >= 4:
            a, b = (pp[1], pp[1]) if pp[0] == 0 else (pp[1], pp[2])
            out.append({"code": 121, "indent": ind, "p": [a, b, 0 if pp[3] == 0 else 1]})
        elif k == "var" and len(pp) >= 6:
            a, b = (pp[1], pp[1]) if pp[0] == 0 else (pp[1], pp[2])
            out.append({"code": 122, "indent": ind, "p": [a, b, pp[3], pp[4], pp[5]]})
        elif k == "gold" and len(pp) >= 3:
            out.append({"code": 125, "indent": ind, "p": [pp[0], 0, pp[2]]})
        elif k == "item" and len(pp) >= 3:
            out.append({"code": 126, "indent": ind, "p": [pp[2], pp[0], 0, pp[4] if len(pp) > 4 else 1]})
        elif k == "tele" and len(pp) >= 3:
            out.append({"code": 201, "indent": ind, "p": [0, pp[0], pp[1], pp[2]]})
        elif k == "battle":
            out.append({"code": 301, "indent": ind, "p": [0, pp[1] if len(pp) > 1 else 0]})
        elif k in ("win", "esc", "lose"):
            out.append({"code": {"win": 601, "esc": 602, "lose": 603}[k], "indent": ind, "p": []})
        elif k == "bend":
            out.append({"code": 604, "indent": ind, "p": []})
        elif k == "shop":
            out.append({"code": 302, "indent": ind, "p": [0, 0]})
        elif k == "shopitem":
            out.append({"code": 605, "indent": ind, "p": [0, pp[0] if pp else 0]})
        elif k == "if" and pp:
            t = pp[0]
            if t == 0 and len(pp) >= 3:
                out.append({"code": 111, "indent": ind, "p": [0, pp[1], pp[2]]})
            elif t == 1 and len(pp) >= 5 and pp[2] == 0:
                out.append({"code": 111, "indent": ind, "p": [1, pp[1], 0, pp[3], _LCF_CMP.get(pp[4], 1)]})
            else:
                out.append({"code": 111, "indent": ind, "p": [99]})  # sem equivalente
        elif k == "else":
            out.append({"code": 411, "indent": ind, "p": []})
        elif k == "endif":
            out.append({"code": 412, "indent": ind, "p": []})
        elif k == "exit":
            out.append({"code": 115, "indent": ind, "p": []})
        elif k == "erase":
            out.append({"code": 214, "indent": ind, "p": []})
        elif k == "call" and pp:
            out.append({"code": 117, "indent": ind, "p": [pp[1] if len(pp) > 1 else 0]})
    return out


def load_lcf(src) -> Dict[str, Any]:
    p: Dict[str, Any] = {"engine": "rm2k", "title": "", "actors": [], "items": {}, "weapons": {}, "armors": {}, "enemies": {}, "troops": {}, "common": {}, "maps": {}, "start": {}, "party": []}
    ini = src.find("rpg_rt.ini")
    if ini:
        m = re.search(r"(?im)^\s*GameTitle\s*=\s*(.+?)\s*$", lcf.decode(src.read(ini)))
        p["title"] = m.group(1) if m else ""
    names: Dict[int, str] = {}
    lmt = src.find("rpg_rt.lmt")
    if lmt:
        try:
            tree = lcf.read_tree(src.read(lmt))
            names, p["start"] = tree["maps"], {"map": tree["start"].get("map"), "x": tree["start"].get("x"), "y": tree["start"].get("y")}
        except ValueError:
            pass
    used_troops: Dict[int, int] = {}
    for f in src.find_all(r"map(\d{4})\.lmu$"):
        mid = int(re.search(r"map(\d{4})\.lmu$", f.lower()).group(1))
        try:
            m = lcf.read_map(src.read(f))
        except (ValueError, struct.error):
            continue
        w, h = m["width"], m["height"]
        low, up = m["lower"], m["upper"]
        if w <= 0 or h <= 0 or len(low) < w * h:
            continue
        rows = []
        for y in range(h):
            r = []
            for x in range(w):
                lo, hi = low[x + y * w], (up[x + y * w] if len(up) >= w * h else 10000)
                r.append("~" if lo < 1000 else ("#" if hi > 10000 else ("," if lo < 4000 else ".")))
            rows.append("".join(r))
        evs = []
        for ev in m["events"]:
            pages = []
            for pg in ev["pages"]:
                cd = pg["cond"]
                flags = cd.get(1, 0)
                cond = {"switch1_valid": bool(flags & 1), "switch1_id": cd.get(2), "switch2_valid": bool(flags & 2), "switch2_id": cd.get(3), "variable_valid": bool(flags & 4),
                        "variable_id": cd.get(4), "variable_value": cd.get(5, 0)}
                lst = lcf_to_mv(pg["list"])
                for c in lst:
                    if c["code"] == 301 and len(c["p"]) > 1:
                        used_troops[c["p"][1]] = 1
                pages.append({"cond": cond, "trigger": {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}.get(pg["trigger"], 0), "list": lst})
            evs.append({"id": ev["id"], "name": ev["name"], "x": ev["x"], "y": ev["y"], "pages": pages})
        p["maps"][mid] = {"name": names.get(mid) or f"Mapa {mid}", "w": w, "h": h, "tiles": rows, "troops": [], "rate": 0.0, "events": evs}
    for t in used_troops:  # o banco de dados (RPG_RT.ldb) não é lido: monstros genéricos
        p["troops"][t] = [t]
        p["enemies"][t] = {"name": f"Monstro {t}", "hp": 25 + 3 * (t % 10), "atk": 8, "def": 3, "spd": 5, "xp": 8, "gold": 6, "shape": "orb"}
    p["actors"] = [{"id": 1, "name": p["title"] or "Herói", "cls": "warrior", "level": 1}]
    p["party"] = [1]
    if not p["start"].get("map") and p["maps"]:
        p["start"] = {"map": min(p["maps"], key=lambda k: (not p["maps"][k]["events"], k)), "x": 1, "y": 1}
    return p


