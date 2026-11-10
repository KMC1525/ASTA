"""Arte procedural (sem IA e sem dependências): sprites em SVG para os jogos gerados e ícones PNG para as exportações.

Serve de reserva quando não há modelo de imagem configurado: o Assets gera um desenho de verdade a partir do que o pedido diz (herói, inimigo, moeda, árvore…),
em camadas que o usuário pode editar. Com um modelo de imagem, a IA desenha; aqui fica o caminho que nunca falha."""
from __future__ import annotations

import html
import re
import struct
import unicodedata
import zlib
from typing import Dict, List, Optional, Tuple

from .. import util

OUT = "#1b1b2f"


def _shade(c: str, amt: float) -> str:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        r, g, b = 128, 128, 128
    f = (lambda x: int(round(x + (255 - x) * amt))) if amt > 0 else (lambda x: int(round(x * (1 + amt))))
    return "#%02x%02x%02x" % (max(0, min(255, f(r))), max(0, min(255, f(g))), max(0, min(255, f(b))))


def _svg(body: str, w: int = 64, h: int = 64) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">{body}</svg>'


def _eyes(y: float = 26, gap: float = 9, r: float = 5, angry: bool = False) -> str:
    s = f'<circle cx="{32 - gap}" cy="{y}" r="{r}" fill="#fff" stroke="{OUT}" stroke-width="1.5"/><circle cx="{32 + gap}" cy="{y}" r="{r}" fill="#fff" stroke="{OUT}" stroke-width="1.5"/>'
    s += f'<circle cx="{32 - gap + 1.5}" cy="{y + 0.5}" r="{r * 0.45}" fill="{OUT}"/><circle cx="{32 + gap + 1.5}" cy="{y + 0.5}" r="{r * 0.45}" fill="{OUT}"/>'
    if angry:
        s += f'<path d="M{32 - gap - r - 1} {y - r - 1} L{32 - gap + r} {y - r + 3} M{32 + gap + r + 1} {y - r - 1} L{32 + gap - r} {y - r + 3}" stroke="{OUT}" stroke-width="2.4" stroke-linecap="round"/>'
    return s


def _blob(c: str, angry: bool = False) -> str:
    return (f'<ellipse cx="32" cy="58" rx="18" ry="3.5" fill="rgba(0,0,0,.22)"/><path d="M10 52 C8 30 18 12 32 12 C46 12 56 30 54 52 Z" fill="{c}" stroke="{OUT}" stroke-width="2.5" stroke-linejoin="round"/>'
            f'<path d="M18 26 C20 19 25 16 30 16" stroke="{_shade(c, .45)}" stroke-width="3" fill="none" stroke-linecap="round"/>' + _eyes(32, 9, 5.5, angry) +
            f'<path d="M25 44 Q32 {40 if angry else 49} 39 44" stroke="{OUT}" stroke-width="2.4" fill="none" stroke-linecap="round"/>')


SUBJECTS: Dict[str, str] = {}


def _reg(name: str, words: str):
    def deco(fn):
        for w in words.split():
            SUBJECTS[w] = name
        SUBJECTS[name] = name
        return fn
    return deco


_DRAW = {}


def _sub(name: str, words: str):
    def deco(fn):
        _DRAW[name] = fn
        for w in words.split():
            SUBJECTS[w] = name
        SUBJECTS[name] = name
        return fn
    return deco


@_sub("player", "heroi hero jogador player personagem character cavaleiro knight menino garota girl boy aventureiro adventurer")
def _player(c: str) -> str:
    return (f'<ellipse cx="32" cy="60" rx="14" ry="3" fill="rgba(0,0,0,.22)"/><rect x="18" y="30" width="28" height="26" rx="9" fill="{c}" stroke="{OUT}" stroke-width="2.5"/>'
            f'<circle cx="32" cy="22" r="14" fill="#f6d2a8" stroke="{OUT}" stroke-width="2.5"/><path d="M18 20 Q32 2 46 20 Q38 12 32 14 Q24 12 18 20Z" fill="{_shade(c, -.35)}" stroke="{OUT}" stroke-width="2"/>'
            + _eyes(24, 6, 3.4) + f'<path d="M28 31 Q32 34 36 31" stroke="{OUT}" stroke-width="2" fill="none" stroke-linecap="round"/><rect x="21" y="52" width="9" height="8" rx="3" fill="{_shade(c, -.5)}" stroke="{OUT}" stroke-width="2"/><rect x="34" y="52" width="9" height="8" rx="3" fill="{_shade(c, -.5)}" stroke="{OUT}" stroke-width="2"/>')


@_sub("enemy", "inimigo enemy monstro monster slime vilao villain criatura creature")
def _enemy(c: str) -> str:
    return _blob(c, True)


@_sub("flyer", "morcego bat voador flyer fantasma ghost passaro bird")
def _flyer(c: str) -> str:
    return (f'<path d="M4 22 Q16 10 28 28 L28 38 Q14 30 4 22Z M60 22 Q48 10 36 28 L36 38 Q50 30 60 22Z" fill="{_shade(c, -.25)}" stroke="{OUT}" stroke-width="2.4" stroke-linejoin="round"/>'
            f'<ellipse cx="32" cy="34" rx="12" ry="14" fill="{c}" stroke="{OUT}" stroke-width="2.5"/>' + _eyes(31, 5, 3.6, True) + f'<path d="M26 22 L24 14 L30 20 M38 22 L40 14 L34 20" fill="{c}" stroke="{OUT}" stroke-width="2"/>')


@_sub("coin", "moeda coin ouro gold dinheiro money")
def _coin(c: str) -> str:
    return (f'<circle cx="32" cy="32" r="22" fill="{c}" stroke="{OUT}" stroke-width="3"/><circle cx="32" cy="32" r="15" fill="none" stroke="{_shade(c, -.3)}" stroke-width="3"/>'
            f'<path d="M32 22 L35 29 L43 30 L37 35 L39 43 L32 39 L25 43 L27 35 L21 30 L29 29Z" fill="{_shade(c, .4)}" stroke="{_shade(c, -.35)}" stroke-width="1.5"/><path d="M16 22 Q20 14 28 12" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" opacity=".7"/>')


@_sub("gem", "gema gem diamante diamond cristal crystal joia jewel")
def _gem(c: str) -> str:
    return (f'<path d="M32 6 L56 24 L32 58 L8 24Z" fill="{c}" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/><path d="M8 24 H56 M32 6 L22 24 L32 58 L42 24Z" fill="none" stroke="{OUT}" stroke-width="2" stroke-linejoin="round"/>'
            f'<path d="M32 6 L42 24 H22Z" fill="{_shade(c, .5)}" opacity=".85"/>')


@_sub("heart", "coracao heart vida life saude health")
def _heart(c: str) -> str:
    return f'<path d="M32 56 C8 38 6 22 16 14 C24 8 32 14 32 20 C32 14 40 8 48 14 C58 22 56 38 32 56Z" fill="{c}" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/><path d="M16 22 Q18 16 24 15" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" opacity=".7"/>'


@_sub("key", "chave key")
def _key(c: str) -> str:
    return (f'<circle cx="20" cy="22" r="13" fill="{c}" stroke="{OUT}" stroke-width="3"/><circle cx="20" cy="22" r="5" fill="#fff" stroke="{OUT}" stroke-width="2"/>'
            f'<path d="M29 30 L56 56 M46 46 L52 40 M40 40 L46 34" stroke="{OUT}" stroke-width="9" stroke-linecap="round"/><path d="M29 30 L56 56 M46 46 L52 40 M40 40 L46 34" stroke="{c}" stroke-width="4.5" stroke-linecap="round"/>')


@_sub("door", "porta door portao gate")
def _door(c: str) -> str:
    return (f'<rect x="12" y="4" width="40" height="58" rx="18" fill="{c}" stroke="{OUT}" stroke-width="3"/><rect x="19" y="14" width="26" height="46" rx="12" fill="{_shade(c, -.3)}" stroke="{OUT}" stroke-width="2"/>'
            f'<circle cx="40" cy="38" r="3.2" fill="#ffd23f" stroke="{OUT}" stroke-width="1.5"/>')


@_sub("tree", "arvore tree pinheiro pine floresta forest")
def _tree(c: str) -> str:
    return (f'<rect x="27" y="40" width="10" height="22" rx="3" fill="#7a5a3a" stroke="{OUT}" stroke-width="2.5"/><circle cx="32" cy="26" r="20" fill="{c}" stroke="{OUT}" stroke-width="3"/>'
            f'<circle cx="23" cy="20" r="6" fill="{_shade(c, .3)}" opacity=".8"/><circle cx="40" cy="30" r="8" fill="{_shade(c, -.2)}" opacity=".7"/>')


@_sub("crate", "caixa crate bau box barril barrel")
def _crate(c: str) -> str:
    return (f'<rect x="6" y="6" width="52" height="52" rx="4" fill="{c}" stroke="{OUT}" stroke-width="3"/><rect x="12" y="12" width="40" height="40" fill="none" stroke="{_shade(c, -.35)}" stroke-width="3"/>'
            f'<path d="M12 12 L52 52 M52 12 L12 52" stroke="{_shade(c, -.35)}" stroke-width="3"/>')


@_sub("goal", "objetivo goal bandeira flag meta portal")
def _goal(c: str) -> str:
    return (f'<rect x="12" y="4" width="5" height="58" rx="2" fill="#adb5bd" stroke="{OUT}" stroke-width="2"/><path d="M17 8 L56 18 L17 32Z" fill="{c}" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/><circle cx="14.5" cy="5" r="4" fill="#ffd23f" stroke="{OUT}" stroke-width="2"/>')


@_sub("npc", "npc aldeao villager mercador merchant mago wizard velho sage")
def _npc(c: str) -> str:
    return (f'<ellipse cx="32" cy="60" rx="14" ry="3" fill="rgba(0,0,0,.22)"/><path d="M14 58 L20 28 Q32 20 44 28 L50 58Z" fill="{c}" stroke="{OUT}" stroke-width="2.5" stroke-linejoin="round"/>'
            f'<circle cx="32" cy="20" r="12" fill="#f6d2a8" stroke="{OUT}" stroke-width="2.5"/><path d="M18 18 Q32 -2 46 18Z" fill="{_shade(c, -.4)}" stroke="{OUT}" stroke-width="2"/>' + _eyes(21, 5, 3) + f'<path d="M28 27 Q32 30 36 27" stroke="{OUT}" stroke-width="2" fill="none"/>')


@_sub("rock", "pedra rock rocha boulder")
def _rock(c: str) -> str:
    return f'<path d="M6 54 L10 32 L24 16 L42 20 L56 36 L58 54Z" fill="{c}" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/><path d="M24 16 L28 34 L10 32 M28 34 L42 20 M28 34 L56 36" fill="none" stroke="{OUT}" stroke-width="1.8"/><path d="M12 36 L24 20" stroke="#fff" stroke-width="3" opacity=".4" stroke-linecap="round"/>'


@_sub("star", "estrela star")
def _star(c: str) -> str:
    return f'<path d="M32 4 L40 24 L61 25 L45 38 L50 59 L32 47 L14 59 L19 38 L3 25 L24 24Z" fill="{c}" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/>'


@_sub("ship", "nave ship foguete rocket espaco space")
def _ship(c: str) -> str:
    return (f'<path d="M4 32 L22 18 L52 26 L60 32 L52 38 L22 46Z" fill="{c}" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/><path d="M22 18 L14 8 L30 22M22 46 L14 56 L30 42" fill="{_shade(c, -.3)}" stroke="{OUT}" stroke-width="2.5" stroke-linejoin="round"/>'
            f'<ellipse cx="40" cy="32" rx="8" ry="5" fill="#9ad9ff" stroke="{OUT}" stroke-width="2"/><path d="M4 32 L-2 28 M4 32 L-2 36" stroke="#ffb703" stroke-width="3" stroke-linecap="round"/>')


@_sub("sword", "espada sword arma weapon")
def _sword(c: str) -> str:
    return f'<path d="M14 50 L44 20 L52 12 L50 22 L22 54Z" fill="#e5e5ea" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/><path d="M10 46 L24 60 M8 56 L18 46" stroke="{c}" stroke-width="6" stroke-linecap="round"/><path d="M8 56 L14 50" stroke="{OUT}" stroke-width="2"/>'


@_sub("potion", "pocao potion frasco elixir")
def _potion(c: str) -> str:
    return (f'<path d="M26 6 H38 V22 L52 52 Q54 60 46 60 H18 Q10 60 12 52 L26 22Z" fill="#dff4ff" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/><path d="M18 44 Q32 38 46 44 L50 54 Q50 58 46 58 H18 Q14 58 14 54Z" fill="{c}"/><rect x="24" y="2" width="16" height="8" rx="2" fill="#a0784f" stroke="{OUT}" stroke-width="2.4"/>')


@_sub("cloud", "nuvem cloud")
def _cloud(c: str) -> str:
    return f'<path d="M14 46 Q2 46 4 34 Q6 24 18 26 Q22 12 36 14 Q48 14 50 28 Q62 28 60 40 Q58 46 50 46Z" fill="{c}" stroke="{OUT}" stroke-width="2.5" stroke-linejoin="round"/>'


@_sub("house", "casa house cabana hut castelo castle")
def _house(c: str) -> str:
    return (f'<rect x="10" y="28" width="44" height="30" fill="{c}" stroke="{OUT}" stroke-width="3"/><path d="M4 30 L32 6 L60 30Z" fill="#b5483a" stroke="{OUT}" stroke-width="3" stroke-linejoin="round"/>'
            f'<rect x="26" y="40" width="12" height="18" rx="5" fill="#6b4226" stroke="{OUT}" stroke-width="2"/><rect x="14" y="34" width="9" height="9" fill="#9ad9ff" stroke="{OUT}" stroke-width="2"/>')


@_sub("button", "botao button ui")
def _button(c: str) -> str:
    return f'<rect x="4" y="14" width="56" height="36" rx="12" fill="{c}" stroke="{OUT}" stroke-width="3"/><rect x="9" y="18" width="46" height="10" rx="5" fill="#fff" opacity=".28"/>'


@_sub("spike", "espinho spike armadilha trap")
def _spike(c: str) -> str:
    return f'<path d="M2 58 L12 22 L22 58 L32 18 L42 58 L52 22 L62 58Z" fill="{c}" stroke="{OUT}" stroke-width="2.5" stroke-linejoin="round"/>'


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


def pick_subject(prompt: str, default: str = "star") -> str:
    """O assunto do desenho que o pedido descreve (a primeira palavra conhecida)."""
    for w in re.findall(r"[a-z]+", _norm(prompt)):
        if w in SUBJECTS:
            return SUBJECTS[w]
    return default


def pick_color(prompt: str, default: str = "#4cc9f0") -> str:
    names = {"vermelh": "#ef476f", "red": "#ef476f", "azul": "#3a86ff", "blue": "#3a86ff", "verde": "#52b788", "green": "#52b788", "amarel": "#ffd23f", "yellow": "#ffd23f", "roxo": "#9d4edd", "purple": "#9d4edd",
             "laranja": "#fb8500", "orange": "#fb8500", "rosa": "#ff8fab", "pink": "#ff8fab", "preto": "#343a40", "black": "#343a40", "branco": "#f1f3f5", "white": "#f1f3f5", "dourad": "#ffb703", "gold": "#ffb703", "cinza": "#8d99ae", "gray": "#8d99ae", "grey": "#8d99ae", "marrom": "#9c6644", "brown": "#9c6644", "ciano": "#4cc9f0", "cyan": "#4cc9f0"}
    p = _norm(prompt)
    m = re.search(r"#[0-9a-f]{6}\b", p)
    if m:
        return m.group(0)
    for k, v in names.items():
        if k in p:
            return v
    return default


def sprite_svg(subject: str, color: str = "#4cc9f0") -> str:
    subject = subject if isinstance(subject, str) else ""
    if not isinstance(color, str) or not color:
        color = default_color(SUBJECTS.get(subject, subject))
    fn = _DRAW.get(SUBJECTS.get(subject, subject)) or _DRAW["star"]
    return _svg(fn(color))


def default_color(subject: str) -> str:
    return {"player": "#ffd166", "enemy": "#ef476f", "flyer": "#9d4edd", "coin": "#ffd23f", "gem": "#4cc9f0", "heart": "#ff4d6d", "key": "#ffbe0b", "door": "#8d5524", "tree": "#2d6a4f", "crate": "#b08968", "goal": "#80ed99",
            "npc": "#90e0ef", "rock": "#8a8d93", "star": "#ffd23f", "ship": "#4cc9f0", "sword": "#a0784f", "potion": "#ef476f", "cloud": "#f1f5f9", "house": "#d9c7a1", "button": "#3a86ff", "spike": "#adb5bd"}.get(subject, "#4cc9f0")


def theme_svg_set(theme_colors: Dict[str, str], genre: str) -> Dict[str, str]:
    """Os sprites de um jogo, nas cores do tema. Chaves = nomes de imagem usados pelo motor."""
    acc = theme_colors.get("accent", "#ffd23f")
    out = {"player": sprite_svg("player", "#ffd166"), "enemy": sprite_svg("enemy", "#ef476f"), "flyer": sprite_svg("flyer", "#9d4edd"), "coin": sprite_svg("coin", acc), "gem": sprite_svg("gem", "#4cc9f0"),
           "heart": sprite_svg("heart", "#ff4d6d"), "key": sprite_svg("key", "#ffbe0b"), "door": sprite_svg("door", "#8d5524"), "tree": sprite_svg("tree", _shade(theme_colors.get("ground", "#5e9c4a"), -.25)),
           "crate": sprite_svg("crate", "#b08968"), "goal": sprite_svg("goal", "#80ed99"), "npc": sprite_svg("npc", "#90e0ef")}
    if genre == "shooter":
        out["player"] = sprite_svg("ship", "#4cc9f0")
        out["enemy"] = sprite_svg("flyer", "#ef476f")
    return out


# ============================================================================ PNG (ícones de exportação) — escritor mínimo
def _png(w: int, h: int, rgba: bytearray) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def _rgb(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return 90, 120, 200


_GLYPH = {  # fonte 5x7 mínima para a inicial do jogo no ícone
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110", "C": "01110 10001 10000 10000 10000 10001 01110", "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111", "F": "11111 10000 10000 11110 10000 10000 10000", "G": "01110 10001 10000 10111 10001 10001 01111", "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "01110 00100 00100 00100 00100 00100 01110", "J": "00111 00010 00010 00010 10010 10010 01100", "K": "10001 10010 10100 11000 10100 10010 10001", "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001", "N": "10001 11001 10101 10011 10001 10001 10001", "O": "01110 10001 10001 10001 10001 10001 01110", "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101", "R": "11110 10001 10001 11110 10100 10010 10001", "S": "01111 10000 10000 01110 00001 00001 11110", "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110", "V": "10001 10001 10001 10001 10001 01010 00100", "W": "10001 10001 10001 10101 10101 11011 10001", "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100", "Z": "11111 00001 00010 00100 01000 10000 11111", "0": "01110 10011 10101 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00110 01000 10000 11111", "3": "11110 00001 00001 01110 00001 00001 11110", "4": "00010 00110 01010 10010 11111 00010 00010", "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110", "7": "11111 00001 00010 00100 01000 01000 01000", "8": "01110 10001 10001 01110 10001 10001 01110", "9": "01110 10001 10001 01111 00001 00010 01100",
}


def icon_png(size: int, title: str, color: str = "#3a86ff", color2: str = "#9d4edd") -> bytes:
    """Ícone quadrado com degradê diagonal, cantos arredondados e a inicial do jogo."""
    size = max(16, min(1024, int(size)))
    c1, c2 = _rgb(color), _rgb(color2)
    buf = bytearray(size * size * 4)
    r = size * 0.22
    ch = (unicodedata.normalize("NFKD", str(title or "A")).encode("ascii", "ignore").decode().upper().strip()[:1]) or "A"
    glyph = [row for row in _GLYPH.get(ch, _GLYPH["A"]).split()]
    cell = size * 0.07
    gw, gh = 5 * cell, 7 * cell
    gx, gy = (size - gw) / 2, (size - gh) / 2
    for y in range(size):
        for x in range(size):
            dx = max(r - x, 0, x - (size - 1 - r))
            dy = max(r - y, 0, y - (size - 1 - r))
            if dx * dx + dy * dy > r * r:
                continue
            t = (x + y) / (2 * size)
            col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
            gxi, gyi = int((x - gx) / cell), int((y - gy) / cell)
            if 0 <= gxi < 5 and 0 <= gyi < 7 and (x - gx) >= 0 and (y - gy) >= 0 and glyph[gyi][gxi] == "1":
                col = (255, 255, 255)
            o = (y * size + x) * 4
            buf[o:o + 4] = bytes((col[0], col[1], col[2], 255))
    return _png(size, size, buf)
