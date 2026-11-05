"""Projetos de jogo SINTÉTICOS (feitos aqui, sem nenhum jogo de terceiros) nos formatos do Ren'Py e do RPG Maker 2000 → MZ, para testar o Rebuild."""
import io
import json
import struct
import zipfile
from typing import Any, Dict, List

from asta.rebuild.marshal import RObj

# ----------------------------------------------------------------------------- MV / MZ

GRASS, WALL, WATER = 2816, 5888, 2048


def cmd(code, indent=0, *params):
    return {"code": code, "indent": indent, "parameters": list(params)}


def mv_event(eid, x, y, pages, name=""):
    return {"id": eid, "name": name or f"EV{eid:03d}", "x": x, "y": y, "pages": pages}


def mv_page(lst, trigger=0, **cond):
    base = {"switch1Valid": False, "switch1Id": 1, "switch2Valid": False, "switch2Id": 1, "variableValid": False, "variableId": 1, "variableValue": 0, "selfSwitchValid": False,
            "selfSwitchCh": "A", "itemValid": False, "itemId": 1, "actorValid": False, "actorId": 1}
    base.update(cond)
    return {"conditions": base, "list": lst + [cmd(0)], "trigger": trigger}


def mv_map(w, h, events, tileset=1):
    data = [0] * (w * h * 6)
    for y in range(h):
        for x in range(w):
            edge = x in (0, w - 1) or y in (0, h - 1)
            data[(0 * h + y) * w + x] = WALL if edge else (WATER if (x > w - 4 and y < 4) else GRASS)
    return {"tilesetId": tileset, "width": w, "height": h, "data": data, "events": [None] + events, "encounterList": [{"troopId": 1, "weight": 10, "regionSet": []}], "encounterStep": 25,
            "displayName": ""}


def mv_project(mz: bool = False) -> Dict[str, bytes]:
    flags = [0] * 9000
    flags[WALL] = 0x0F
    flags[WATER] = 0x0F
    system = {"gameTitle": "Vila de Teste", "startMapId": 1, "startX": 3, "startY": 3, "partyMembers": [1, 2], "locale": "pt_BR"}
    if mz:
        system["advanced"] = {"gameId": 1}
        system["tileSize"] = 48
    m1_events = [
        mv_event(1, 5, 5, [mv_page([cmd(101, 0, "", 0, 0, 2, "Velha"), cmd(401, 0, "Olá, \\N[1]! Você já viu o dragão?"), cmd(401, 0, "Cuidado com ele."),
                                    cmd(102, 0, ["Sim", "Não"], 1), cmd(402, 0, 0, "Sim"), cmd(401, 1, "Então você é corajoso."), cmd(121, 1, 5, 5, 0), cmd(0, 1),
                                    cmd(402, 0, 1, "Não"), cmd(401, 1, "Fuja!"), cmd(0, 1), cmd(404, 0)]),
                       mv_page([cmd(101, 0, "", 0, 0, 2, "Velha"), cmd(401, 0, "Boa sorte, herói.")], switch1Valid=True, switch1Id=5)], "Velha"),
        mv_event(2, 18, 7, [mv_page([cmd(201, 0, 0, 2, 2, 7, 2, 0)], trigger=1)], "Portal"),
        mv_event(3, 8, 9, [mv_page([cmd(111, 0, 0, 5, 0), cmd(101, 1, "", 0, 0, 2, ""), cmd(401, 1, "Você já abriu."), cmd(115, 1), cmd(0, 1), cmd(412, 0),
                                    cmd(126, 0, 1, 0, 0, 2), cmd(125, 0, 0, 0, 50), cmd(122, 0, 3, 3, 1, 0, 4), cmd(121, 0, 5, 5, 0), cmd(214, 0)])], "Baú"),
        mv_event(4, 12, 10, [mv_page([cmd(111, 0, 1, 3, 0, 3, 1), cmd(101, 1, "", 0, 0, 2, ""), cmd(401, 1, "A variável chegou a 3."), cmd(411, 0), cmd(101, 1, "", 0, 0, 2, ""),
                                      cmd(401, 1, "Ainda não."), cmd(412, 0), cmd(302, 0, 0, 1, 0, 0, 0), cmd(605, 0, 0, 2, 0, 0, 0), cmd(355, 0, "$gameScreen.shake()")])], "Loja"),
    ]
    m2_events = [
        mv_event(1, 10, 7, [mv_page([cmd(101, 0, "", 0, 0, 2, "Dragão"), cmd(401, 0, "Eu sou o dragão!"), cmd(301, 0, 0, 2, False, False), cmd(601, 0), cmd(101, 1, "", 0, 0, 2, ""),
                                     cmd(401, 1, "Você venceu."), cmd(0, 1), cmd(602, 0), cmd(0, 1), cmd(604, 0)])], "Dragão"),
        mv_event(2, 2, 7, [mv_page([cmd(201, 0, 0, 1, 3, 3, 2, 0)], trigger=1)], "Volta"),
    ]
    files = {
        "System": system,
        "Actors": [None, {"id": 1, "name": "Aria", "classId": 1, "initialLevel": 1}, {"id": 2, "name": "Brom", "classId": 2, "initialLevel": 2}],
        "Classes": [None, {"id": 1, "name": "Guerreira", "params": [[0, 40, 50, 60], [0, 8, 9, 10], [0, 9, 10, 11], [0, 5, 6, 7], [0, 3, 4, 5], [0, 3, 4, 5], [0, 6, 7, 8], [0, 1, 1, 1]]},
                    {"id": 2, "name": "Mago", "params": [[0, 25, 30, 35], [0, 20, 22, 24], [0, 4, 5, 6], [0, 3, 3, 4], [0, 12, 13, 14], [0, 8, 9, 10], [0, 5, 6, 7], [0, 1, 1, 1]]}],
        "Items": [None, {"id": 1, "name": "Poção", "description": "Recupera HP", "price": 30, "itypeId": 1, "effects": [{"code": 11, "dataId": 0, "value1": 0, "value2": 40}]},
                  {"id": 2, "name": "Chave Velha", "description": "Abre algo", "price": 0, "itypeId": 2, "effects": []}],
        "Weapons": [None], "Armors": [None],
        "Enemies": [None, {"id": 1, "name": "Slime Verde", "params": [20, 0, 6, 2, 0, 0, 4, 0], "exp": 5, "gold": 3},
                    {"id": 2, "name": "Dragão Vermelho", "params": [120, 0, 18, 8, 0, 0, 9, 0], "exp": 100, "gold": 200}],
        "Troops": [None, {"id": 1, "name": "Slime", "members": [{"enemyId": 1}]}, {"id": 2, "name": "Dragão", "members": [{"enemyId": 2}]}],
        "CommonEvents": [None],
        "Tilesets": [None, {"id": 1, "name": "Mundo", "flags": flags, "mode": 1}],
        "MapInfos": [None, {"id": 1, "name": "Vila", "parentId": 0}, {"id": 2, "name": "Covil", "parentId": 0}],
        "Map001": mv_map(20, 14, m1_events), "Map002": mv_map(14, 12, m2_events),
    }
    return {f"data/{k}.json": json.dumps(v).encode("utf-8") for k, v in files.items()}


# ----------------------------------------------------------------------------- Marshal (XP / VX / Ace)


def _int(n: int) -> bytes:
    if n == 0:
        return b"\x00"
    if 0 < n < 123:
        return bytes([n + 5])
    if -124 < n < 0:
        return bytes([(n - 5) & 0xFF])
    raw = n.to_bytes(8, "little", signed=True)
    k = 4
    for size in (1, 2, 3, 4):
        if -(1 << (8 * size - 1)) <= n < (1 << (8 * size - 1)) or (n >= 0 and n < (1 << (8 * size))):
            k = size
            break
    body = (n & ((1 << (8 * k)) - 1)).to_bytes(k, "little")
    return bytes([k if n > 0 else (256 - k)]) + body


def _sym(s: str) -> bytes:
    b = s.encode()
    return b":" + _int(len(b)) + b


def dumps(o: Any) -> bytes:
    return b"\x04\x08" + _dump(o)


def _dump(o: Any) -> bytes:
    if o is None:
        return b"0"
    if o is True:
        return b"T"
    if o is False:
        return b"F"
    if isinstance(o, int):
        return b"i" + _int(o)
    if isinstance(o, str):
        b = o.encode()
        return b'I"' + _int(len(b)) + b + _int(1) + _sym("E") + b"T"
    if isinstance(o, list):
        return b"[" + _int(len(o)) + b"".join(_dump(x) for x in o)
    if isinstance(o, dict):
        return b"{" + _int(len(o)) + b"".join(_dump(k) + _dump(v) for k, v in o.items())
    if isinstance(o, RObj):
        if o.data is not None and not o.iv:
            return b"u" + _sym(o.cls) + _int(len(o.data)) + o.data
        return b"o" + _sym(o.cls) + _int(len(o.iv)) + b"".join(_sym(k) + _dump(v) for k, v in o.iv.items())
    raise TypeError(type(o))


def table(xs, ys, zs, vals) -> RObj:
    return RObj("Table", data=struct.pack("<5i", 3, xs, ys, zs, len(vals)) + struct.pack(f"<{len(vals)}h", *vals))


def ro(cls, **iv) -> RObj:
    return RObj(cls, {"@" + k: v for k, v in iv.items()})


def ecmd(code, indent, *params):
    return ro("RPG::EventCommand", code=code, indent=indent, parameters=list(params))


def rg_project(ext: str = "rvdata2") -> Dict[str, bytes]:
    xp = ext == "rxdata"
    w, h = 16, 12
    flags = [0] * 9000
    flags[WALL] = 0x0F
    if xp:
        flags = [0] * 600
        flags[400] = 0x0F
    wall, floor = (400, 385) if xp else (WALL, GRASS)
    vals = []
    for z in range(3):
        for y in range(h):
            for x in range(w):
                edge = x in (0, w - 1) or y in (0, h - 1)
                vals.append((wall if edge else floor) if z == 0 else 0)
    cond = lambda **k: ro("RPG::Event::Page::Condition", **{**dict(switch1_valid=False, switch1_id=1, switch2_valid=False, switch2_id=1, variable_valid=False, variable_id=1, variable_value=0,
                                                                    self_switch_valid=False, self_switch_ch="A"), **k})
    say = (lambda t: [ecmd(101, 0, t)]) if xp else (lambda t: [ecmd(101, 0, "", 0, 0, 2), ecmd(401, 0, t)])
    page = lambda lst, trig=0, **c: ro("RPG::Event::Page", condition=cond(**c), list=lst + [ecmd(0, 0)], trigger=trig)
    ev = lambda i, x, y, pages: ro("RPG::Event", id=i, name=f"EV{i}", x=x, y=y, pages=pages)
    battle = ecmd(301, 0, 1, True, False) if xp else ecmd(301, 0, 0, 1, True, False)
    mp = ro("RPG::Map", width=w, height=h, tileset_id=1, data=table(w, h, 3, vals), encounter_step=30, encounter_list=[],
            events={1: ev(1, 5, 5, [page(say("Olá, viajante!") + [ecmd(102, 0, ["Sim", "Não"], 0), ecmd(402, 0, 0), ecmd(121, 1, 3, 3, 0), ecmd(0, 1), ecmd(402, 0, 1), ecmd(0, 1), ecmd(404, 0)])]),
                    2: ev(2, 9, 6, [page([battle, ecmd(601, 0), ecmd(0, 1), ecmd(602, 0), ecmd(0, 1), ecmd(604, 0)], 1)])})
    tileset = ro("RPG::Tileset", id=1, **({"passages": table(len(flags), 1, 1, flags), "priorities": table(len(flags), 1, 1, [0] * len(flags))} if xp else {"flags": table(len(flags), 1, 1, flags)}))
    actor = ro("RPG::Actor", id=1, name="Rin", class_id=1, initial_level=1)
    cls = ro("RPG::Class", id=1, name="Mage")
    enemy = ro("RPG::Enemy", id=1, name="Bat", **({"maxhp": 30, "atk": 9, "pdef": 3, "agi": 6} if xp else {"params": [30, 0, 9, 3, 0, 0, 6, 0]}), exp=7, gold=4)
    troop = ro("RPG::Troop", id=1, name="T1", members=[ro("RPG::Troop::Member", enemy_id=1)])
    system = ro("RPG::System", start_map_id=1, start_x=3, start_y=3, party_members=[1], game_title="Teste Marshal")
    data = {"System": system, "Actors": [None, actor], "Classes": [None, cls], "Items": [None], "Weapons": [None], "Armors": [None], "Enemies": [None, enemy], "Troops": [None, troop],
            "CommonEvents": [None], "Tilesets": [None, tileset], "MapInfos": {1: ro("RPG::MapInfo", name="Campo")}, "Map001": mp}
    return {f"Data/{k}.{ext}": dumps(v) for k, v in data.items()}


# ----------------------------------------------------------------------------- LCF (2000 / 2003)


def ber(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def chunk(cid: int, data: bytes) -> bytes:
    return ber(cid) + ber(len(data)) + data


def lcf_array(items: List[bytes]) -> bytes:
    """items: dados já com índice+struct; aqui cada struct termina com o 0."""
    return ber(len(items)) + b"".join(items)


def lcf_elem(idx: int, chunks: bytes) -> bytes:
    return ber(idx) + chunks + b"\x00"


def lcf_cmds(cmds) -> bytes:
    out = b""
    for code, indent, s, params in cmds + [(0, 0, "", [])]:
        sb = s.encode("utf-8")
        out += ber(code) + ber(indent) + ber(len(sb)) + sb + ber(len(params)) + b"".join(ber(p) for p in params)
    return out


def lcf_map(w=20, h=15) -> bytes:
    lower = struct.pack(f"<{w * h}H", *[(5000 if (x in (0, w - 1) or y in (0, h - 1)) else 3000) for y in range(h) for x in range(w)])
    upper = struct.pack(f"<{w * h}H", *[(10001 if (x in (0, w - 1) or y in (0, h - 1)) else 10000) for y in range(h) for x in range(w)])
    talk = lcf_cmds([(10110, 0, "Bem-vindo à vila!", []), (20110, 0, "Fale comigo de novo.", []), (10140, 0, "", [0]), (20140, 0, "Sim", [0]), (10210, 1, "", [0, 7, 7, 0]),
                     (20140, 0, "Não", [1]), (20141, 0, "", [])])
    tele = lcf_cmds([(10810, 0, "", [2, 4, 4, 0])])
    fight = lcf_cmds([(10710, 0, "", [0, 3]), (20710, 0, "", []), (10110, 1, "Venceu!", []), (20713, 0, "", [])])
    def page(cmds, trigger):
        return lcf_elem(1, chunk(0x02, chunk(0x01, ber(1)) + chunk(0x02, ber(7))) + chunk(0x21, ber(trigger)) + chunk(0x33, cmds))
    def event(i, name, x, y, cmds, trigger):
        return lcf_elem(i, chunk(0x01, name.encode()) + chunk(0x02, ber(x)) + chunk(0x03, ber(y)) + chunk(0x05, lcf_array([page(cmds, trigger)])))
    events = lcf_array([event(1, "Aldeão", 5, 5, talk, 0), event(2, "Portal", 10, 5, tele, 1), event(3, "Monstro", 7, 8, fight, 1)])
    body = chunk(0x01, ber(1)) + chunk(0x02, ber(w)) + chunk(0x03, ber(h)) + chunk(0x47, lower) + chunk(0x48, upper) + chunk(0x51, events)
    return ber(10) + b"LcfMapUnit" + body


def lcf_tree() -> bytes:
    maps = lcf_array([lcf_elem(1, chunk(0x01, "Vila".encode())), lcf_elem(2, chunk(0x01, "Caverna".encode()))])
    start = chunk(0x01, ber(1)) + chunk(0x02, ber(3)) + chunk(0x03, ber(3))
    return ber(10) + b"LcfMapTree" + chunk(0x01, maps) + chunk(0x04, start)


def rm2k_project() -> Dict[str, bytes]:
    return {"RPG_RT.ini": b"[RPG_RT]\r\nGameTitle=Aventura 2K\r\n", "RPG_RT.lmt": lcf_tree(), "Map0001.lmu": lcf_map(), "Map0002.lmu": lcf_map(16, 12)}


# ----------------------------------------------------------------------------- empacotar


def zip_bytes(files: Dict[str, bytes], root: str = "MeuJogo") -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(f"{root}/{name}" if root else name, data)
    return bio.getvalue()


RPY = '''define e = Character("Eileen", color="#c8ffc8")
define config.name = _("Café Tranquilo")
default affection = 0
label start:
    scene bg cafe with dissolve
    show eileen happy at left
    e "Olá! {i}Bem-vindo{/i} ao café, [player]."
    "Marta" "Eu sou a Marta."
    $ affection += 1
    menu:
        "Escolha:"
        "Pedir café":
            $ affection += 2
            e "Ótimo!"
            jump coffee
        "Ir embora" if affection > 0:
            e "Que pena."
    if affection >= 2:
        e "Gosto de você."
    else:
        e "Hm."
    call extra
    return
label coffee:
    e "Aqui está."
    menu:
        "Obrigado":
            e "De nada."
        "Nada":
            pass
    jump finale
label extra:
    e "Chamada extra."
    return
label finale:
    "Fim da história."
    return
'''
