"""RPG Maker (2000 → MZ) → jogo RPG do ASTA: converte comandos de evento, páginas, mapas e banco de dados já lidos em um formato comum.

Os leitores (MV/MZ em JSON, XP/VX/Ace em Marshal, 2000/2003 em LCF) entregam os eventos como listas de {code, indent, p:[parâmetros]} com a numeração
do MV/MZ; este módulo transforma isso nos comandos do motor RPG do ASTA (`say`, `choice`, `set`, `if`, `warp`, `battle`, `shop`…).
Só a estrutura (mapas, eventos, diálogos, variáveis, itens, inimigos) é reconstruída: a arte e o áudio originais não são copiados.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

MAX_TEXT = 200


class Conv:
    """Estado da conversão de um jogo: nomes, itens usados, tropas, avisos."""

    def __init__(self, project: Dict[str, Any]):
        self.p = project
        self.items: Dict[str, Dict[str, Any]] = {}
        self.warnings: List[str] = []
        self._warned: set = set()
        self.unsupported = 0
        self.has_end = False

    def warn(self, msg: str, once: bool = True) -> None:
        if once and msg in self._warned:
            return
        self._warned.add(msg)
        if len(self.warnings) < 60:
            self.warnings.append(msg)

    def item(self, kind: str, iid: int) -> str:
        """Garante o item no jogo (nome vindo do banco de dados) e devolve o id do ASTA."""
        key = f"{kind}{iid}"
        if key not in self.items and len(self.items) < 40:
            src = (self.p.get({"i": "items", "w": "weapons", "a": "armors"}[kind]) or {}).get(iid) or {}
            self.items[key] = {"name": src.get("name") or {"i": "Item", "w": "Arma", "a": "Armadura"}[kind] + f" {iid}",
                               "kind": src.get("kind", "key" if kind != "i" else "heal_hp"), "amount": src.get("amount", 20), "price": src.get("price", 10), "desc": src.get("desc", "")}
        return key if key in self.items else ""


def clean_text(s: str, p: Dict[str, Any]) -> str:
    """Códigos de texto do RPG Maker (\\N[1], \\V[3], \\C[2]…) → texto do ASTA."""
    actors = {a["id"]: a["name"] for a in p.get("actors", [])}
    s = re.sub(r"\\[Nn]\[(\d+)\]", lambda m: actors.get(int(m.group(1)), "Herói"), s)
    s = re.sub(r"\\[Vv]\[(\d+)\]", lambda m: "{v" + m.group(1) + "}", s)
    s = re.sub(r"\\[Pp]\[\d+\]", "Herói", s)
    s = re.sub(r"\\(?:[Cc]|[Ii]|[Ff][Ss]?|[Ff][Bb]?|[Ff][Ii]?|[Ww][Ss]?)\[\d+\]", "", s)
    s = re.sub(r"\\[GgHh{}.|!<>^$]", "", s).replace("\\\\", "\\")
    return re.sub(r"[ \t]+", " ", s).strip()


def _split(text: str) -> List[str]:
    if len(text) <= MAX_TEXT:
        return [text]
    out, cur = [], ""
    for part in re.split(r"(?<=[.!?…])\s+", text):
        if cur and len(cur) + len(part) + 1 > MAX_TEXT:
            out.append(cur)
            cur = ""
        cur = (cur + " " + part).strip()
    return out + [cur] if cur else out


_CMP = {0: "==", 1: ">=", 2: "<=", 3: ">", 4: "<", 5: "!="}


def _cond(c: Conv, params: List[Any], ctx: Tuple[int, int]) -> Optional[str]:
    t = params[0] if params else -1
    try:
        if t == 0:
            return ("not " if params[2] else "") + f"sw{params[1]}"
        if t == 1 and params[2] == 0:
            return f"v{params[1]} {_CMP.get(params[4], '>=')} {int(params[3])}"
        if t == 2:
            return ("not " if params[2] == 1 else "") + f"ss{ctx[0]}x{ctx[1]}{str(params[1]).lower()}"
    except (IndexError, TypeError, ValueError):
        return None
    return None


def convert_list(c: Conv, cmds: List[Dict[str, Any]], ctx: Tuple[int, int], depth: int = 0) -> List[Dict[str, Any]]:
    out, _exit = _block(c, cmds, 0, 0, ctx, depth)
    return out


def _block(c: Conv, cmds: List[Dict[str, Any]], i: int, indent: int, ctx: Tuple[int, int], depth: int) -> Tuple[List[Dict[str, Any]], bool]:
    out: List[Dict[str, Any]] = []
    n = len(cmds)
    while i < n:
        cm = cmds[i]
        if cm["indent"] < indent:
            break
        code, p = cm["code"], cm.get("p") or []
        i += 1
        if cm["indent"] > indent:
            continue  # restos de blocos que não entendemos
        if code == 101:
            lines = []
            if cm.get("legacy_text") and p:
                lines.append(str(p[0]))
            while i < n and cmds[i]["code"] == 401 and cmds[i]["indent"] == indent:
                lines.append(str((cmds[i].get("p") or [""])[0]))
                i += 1
            who = clean_text(str(p[4]), c.p) if len(p) > 4 and isinstance(p[4], str) else ""
            body = clean_text("\n".join(lines), c.p)
            for piece in _split(body):
                if piece:
                    out.append({"c": "say", "who": who, "text": piece})
        elif code == 102:
            opts = [clean_text(str(o), c.p) for o in (p[0] if p and isinstance(p[0], list) else [])][:5]
            branches: Dict[int, List[Dict[str, Any]]] = {}
            exits = []
            while i < n:
                nx = cmds[i]
                if nx["indent"] == indent and nx["code"] in (402, 403):
                    idx = (nx.get("p") or [0])[0] if nx["code"] == 402 else -1
                    body, ex = _block(c, cmds, i + 1, indent + 1, ctx, depth)
                    i = _skip(cmds, i + 1, indent + 1)
                    if idx >= 0:
                        branches[idx] = body
                        exits.append(ex)
                elif nx["indent"] == indent and nx["code"] == 404:
                    i += 1
                    break
                else:
                    i += 1
            if opts:
                out.append({"c": "choice", "options": [{"text": t or f"Opção {k + 1}", "do": branches.get(k, [])} for k, t in enumerate(opts)]})
            else:
                c.warn("escolha sem opções legíveis ignorada")
        elif code == 111:
            cond = _cond(c, p, ctx)
            then, t_exit = _block(c, cmds, i, indent + 1, ctx, depth)
            i = _skip(cmds, i, indent + 1)
            els: List[Dict[str, Any]] = []
            e_exit = False
            if i < n and cmds[i]["code"] == 411 and cmds[i]["indent"] == indent:
                els, e_exit = _block(c, cmds, i + 1, indent + 1, ctx, depth)
                i = _skip(cmds, i + 1, indent + 1)
            if i < n and cmds[i]["code"] == 412 and cmds[i]["indent"] == indent:
                i += 1
            if cond is None:
                c.unsupported += 1
                c.warn("condição de evento sem equivalente (ex.: dinheiro, item, ator); o ramo «então» foi mantido")
                out.extend(then)
                if t_exit:
                    return out, True
                continue
            tail: List[Dict[str, Any]] = []
            if t_exit != e_exit:  # «sair do evento» dentro de um ramo: o resto só roda no outro ramo
                tail, ex = _block(c, cmds, i, indent, ctx, depth)
                i = n
                (els if t_exit else then).extend(tail)
                out.append({"c": "if", "cond": cond, "then": then, "else": els})
                return out, ex
            out.append({"c": "if", "cond": cond, "then": then, "else": els})
            if t_exit and e_exit:
                return out, True
        elif code == 121:
            a, b = int(p[0]), int(p[1]) if len(p) > 1 else int(p[0])
            for sid in range(a, min(b, a + 20) + 1):
                out.append({"c": "set", "var": f"sw{sid}", "op": "=", "value": (p[2] if len(p) > 2 else 0) == 0})
        elif code == 122:
            a, b = int(p[0]), int(p[1]) if len(p) > 1 else int(p[0])
            op, otype = (p[2] if len(p) > 2 else 0), (p[3] if len(p) > 3 else 0)
            val = p[4] if len(p) > 4 else 0
            if otype == 0 and op in (0, 1, 2) and isinstance(val, (int, float)):
                for vid in range(a, min(b, a + 20) + 1):
                    out.append({"c": "set", "var": f"v{vid}", "op": ("=", "+=", "-=")[op], "value": int(val)})
            else:
                c.unsupported += 1
                c.warn("operação de variável complexa (variável/aleatório/multiplicar) ignorada")
        elif code == 123:
            out.append({"c": "set", "var": f"ss{ctx[0]}x{ctx[1]}{str(p[0]).lower()}", "op": "=", "value": (p[1] if len(p) > 1 else 0) == 0})
        elif code == 125:
            if len(p) > 2 and p[1] == 0:
                out.append({"c": "gold", "n": int(p[2]) * (1 if p[0] == 0 else -1)})
        elif code in (126, 127, 128):
            kind = {126: "i", 127: "w", 128: "a"}[code]
            if len(p) > 3 and p[2] == 0:
                iid = c.item(kind, int(p[0]))
                if iid:
                    out.append({"c": "item", "id": iid, "n": int(p[3]) * (1 if p[1] == 0 else -1)})
        elif code == 129:
            if len(p) > 1 and p[1] == 0:
                out.append({"c": "recruit", "id": f"a{p[0]}"})
        elif code == 201:
            if len(p) > 3 and p[0] == 0:
                out.append({"c": "warp", "map": f"m{p[1]}", "x": int(p[2]), "y": int(p[3])})
            else:
                c.warn("teletransporte por variável ignorado")
        elif code == 301:
            troop = None
            if cm.get("legacy_battle"):
                troop = p[0] if p else None
            elif len(p) > 1 and p[0] == 0:
                troop = p[1]
            win: List[Dict[str, Any]] = []
            while i < n:
                nx = cmds[i]
                if nx["indent"] == indent and nx["code"] == 601:
                    win, _ = _block(c, cmds, i + 1, indent + 1, ctx, depth)
                    i = _skip(cmds, i + 1, indent + 1)
                elif nx["indent"] == indent and nx["code"] in (602, 603):
                    i = _skip(cmds, i + 1, indent + 1)
                elif nx["indent"] == indent and nx["code"] == 604:
                    i += 1
                    break
                elif nx["indent"] > indent:
                    i += 1
                else:
                    break
            enemies = (c.p.get("troops") or {}).get(troop) if troop is not None else None
            if enemies:
                out.append({"c": "battle", "enemies": [f"e{e}" for e in enemies[:4]], "boss": False, "win": win, "lose": "gameover"})
            else:
                c.warn("batalha por variável/tropa desconhecida ignorada")
                out.extend(win)
        elif code == 302:
            ids = []
            first = p[1] if len(p) > 1 and p[0] == 0 else None
            if first is not None:
                ids.append(c.item("i", int(first)))
            while i < n and cmds[i]["code"] == 605 and cmds[i]["indent"] == indent:
                q = cmds[i].get("p") or []
                if len(q) > 1 and q[0] == 0:
                    ids.append(c.item("i", int(q[1])))
                i += 1
            ids = [x for x in ids if x]
            if ids:
                out.append({"c": "shop", "items": ids})
        elif code == 214:
            out.append({"c": "remove"})
        elif code in (313, 314):
            out.append({"c": "heal"})
        elif code == 117 and depth < 3:
            ce = (c.p.get("common") or {}).get(p[0] if p else 0)
            if ce:
                out.extend(convert_list(c, ce, ctx, depth + 1))
        elif code == 115:
            return out, True
        elif code in (355, 655, 356):
            c.unsupported += 1
            c.warn("chamadas de script (Ruby/JavaScript) não foram convertidas", once=True)
        elif code == 353:  # game over
            pass
    return out, False


def _skip(cmds: List[Dict[str, Any]], i: int, indent: int) -> int:
    while i < len(cmds) and cmds[i]["indent"] >= indent:
        i += 1
    return i


# --------------------------------------------------------------------------- páginas, eventos, mapas


def page_cond(cond: Dict[str, Any], ctx: Tuple[int, int]) -> str:
    parts = []
    if cond.get("switch1_valid"):
        parts.append(f"sw{cond.get('switch1_id')}")
    if cond.get("switch2_valid"):
        parts.append(f"sw{cond.get('switch2_id')}")
    if cond.get("variable_valid"):
        parts.append(f"v{cond.get('variable_id')} >= {int(cond.get('variable_value') or 0)}")
    if cond.get("self_switch_valid"):
        parts.append(f"ss{ctx[0]}x{ctx[1]}{str(cond.get('self_switch_ch') or 'a').lower()}")
    return " and ".join(parts)


def convert_event(c: Conv, mid: int, ev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ctx = (mid, int(ev["id"]))
    pages = []
    kinds: List[str] = []
    trigger = "action"
    for pg in reversed(ev.get("pages") or []):  # o RPG Maker usa a ÚLTIMA página cujas condições valem; o ASTA, a PRIMEIRA
        cmds = convert_list(c, pg.get("list") or [], ctx)
        if not cmds:
            continue
        pages.append({"if": page_cond(pg.get("cond") or {}, ctx), "commands": cmds})
        t = int(pg.get("trigger") or 0)
        trigger = "touch" if t in (1, 2) else ("auto" if t in (3, 4) else "action")
        flat = " ".join(x["c"] for x in _walk(cmds))
        kinds.append("warp" if ("warp" in flat and "say" not in flat) else "enemy" if ("battle" in flat and "say" not in flat and trigger == "touch") else "npc")
    if not pages:
        return None
    kind = kinds[-1] if kinds else "npc"
    return {"id": f"e{ev['id']}", "kind": kind, "x": int(ev.get("x") or 0), "y": int(ev.get("y") or 0), "name": ev.get("name") or "", "trigger": trigger, "pages": pages}


def _walk(cmds: List[Dict[str, Any]]):
    for x in cmds:
        yield x
        for key in ("then", "else", "win"):
            if isinstance(x.get(key), list):
                yield from _walk(x[key])
        for o in x.get("options") or []:
            yield from _walk(o.get("do") or [])


def build_rpg(p: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Projeto lido (formato comum) → dicionário bruto para `normalize_game(..., "rpg")` + avisos."""
    c = Conv(p)
    maps: Dict[str, Any] = {}
    cropped = 0
    for mid, m in sorted(p.get("maps", {}).items())[:40]:
        w, h = int(m["w"]), int(m["h"])
        rows = [str(r) for r in m["tiles"]]
        cw, ch = min(w, 60), min(h, 40)
        if (cw, ch) != (w, h):
            cropped += 1
        rows = [r[:cw].ljust(12, "#") for r in rows[:ch]]
        rows += ["#" * max(12, cw)] * max(0, 10 - len(rows))
        evs = []
        for ev in m.get("events", []):
            if int(ev.get("x") or 0) >= cw or int(ev.get("y") or 0) >= ch:
                continue
            e = convert_event(c, mid, ev)
            if e:
                evs.append(e)
        groups = [[f"e{x}" for x in (p.get("troops") or {}).get(t, [])[:4]] for t in (m.get("troops") or [])[:6]]
        groups = [g for g in groups if g]
        maps[f"m{mid}"] = {"id": f"m{mid}", "name": m.get("name") or f"Mapa {mid}", "theme": m.get("theme", "grass"), "music": "calm", "tiles": rows, "events": evs,
                           "encounters": {"rate": float(m.get("rate", 0.06)) if groups else 0.0, "groups": groups}}
    if cropped:
        c.warn(f"{cropped} mapa(s) maiores que o limite do ASTA (60×40) foram recortados")
    # inimigos usados + inimigos dos grupos de encontro
    used = set()
    for m in maps.values():
        for grp in m["encounters"]["groups"]:
            used.update(grp)
        for x in _walk([cmd for e in m["events"] for pg in e["pages"] for cmd in pg["commands"]]):
            if x["c"] == "battle":
                used.update(x["enemies"])
    enemies = {}
    for key in sorted(used)[:30]:
        src = (p.get("enemies") or {}).get(int(key[1:])) or {}
        enemies[key] = {"name": src.get("name") or f"Monstro {key[1:]}", "hp": src.get("hp", 30), "atk": src.get("atk", 8), "def": src.get("def", 3), "spd": src.get("spd", 5),
                        "xp": src.get("xp", 8), "gold": src.get("gold", 5), "shape": src.get("shape", "orb"), "color": src.get("color", "#8aa0d6"), "boss": bool(src.get("boss"))}
    # o último chefe vencido leva ao fim do jogo; sem nenhum, o último evento de batalha encerra
    party = [{"id": f"a{a['id']}", "name": a["name"], "cls": a.get("cls", "warrior"), "level": a.get("level", 1), "hp": a.get("hp", 30), "mp": a.get("mp", 8), "atk": a.get("atk", 8),
              "def": a.get("def", 4), "mag": a.get("mag", 5), "spd": a.get("spd", 5), "skills": []} for a in p.get("actors", [])[:5]]
    start = p.get("start") or {}
    smap = f"m{start.get('map')}" if f"m{start.get('map')}" in maps else (next(iter(maps)) if maps else "")
    members = [f"a{i}" for i in (p.get("party") or []) if any(x["id"] == f"a{i}" for x in party)] or ([party[0]["id"]] if party else [])
    raw = {"start": {"map": smap, "x": int(start.get("x") or 1), "y": int(start.get("y") or 1)}, "party": party, "start_party": members, "items": c.items, "enemies": enemies, "maps": maps}
    if not _has_end(maps):
        _add_ending(maps, c)
    return raw, c.warnings


def _has_end(maps: Dict[str, Any]) -> bool:
    return any(x["c"] == "end" for m in maps.values() for e in m["events"] for pg in e["pages"] for x in _walk(pg["commands"]))


def _add_ending(maps: Dict[str, Any], c: Conv) -> None:
    """O RPG Maker não tem «fim do jogo» como comando: o ASTA precisa de um — vai no último combate vencível (ou no último evento com diálogo)."""
    last = None
    for m in maps.values():
        for e in m["events"]:
            for pg in e["pages"]:
                for x in _walk(pg["commands"]):
                    if x["c"] == "battle":
                        last = x
    if last is not None:
        last.setdefault("win", []).append({"c": "end", "title": "Fim"})
        c.warn("o jogo original não tem um comando de «fim»; o ASTA encerra o jogo ao vencer o último combate")
        return
    for m in reversed(list(maps.values())):
        for e in reversed(m["events"]):
            if e["pages"]:
                e["pages"][0]["commands"].append({"c": "end", "title": "Fim"})
                c.warn("o jogo original não tem um comando de «fim»; o ASTA encerra o jogo no último evento convertido")
                return
