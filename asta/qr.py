"""Gerador de QR code (só biblioteca padrão): modo bytes, correção de erros M, versões 1–10 (até 213 bytes — sobra para uma URL de rede local).

Usado pelo pareamento do celular (`asta mobile`, Configuração → Celular e tablet) e pelo README. `matrix(texto)` devolve a grade de módulos (True = escuro);
`svg(texto)` e `terminal(texto)` desenham essa grade.
"""
from __future__ import annotations

from typing import List, Tuple

# versão → (codewords de correção por bloco, [(nº de blocos, codewords de dados por bloco), ...]) para o nível M
_EC_M = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]), 6: (16, [(4, 27)]), 7: (18, [(4, 31)]),
         8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]), 10: (26, [(4, 43), (1, 44)])}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}
MAX_BYTES = 213


def _gf_tables() -> Tuple[List[int], List[int]]:
    exp, log, x = [0] * 512, [0] * 256, 1
    for i in range(255):
        exp[i], log[x] = x, i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


_EXP, _LOG = _gf_tables()


def _mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs_remainder(data: List[int], ndeg: int) -> List[int]:
    gen = [1]
    for i in range(ndeg):  # polinômio gerador (x - α^0)(x - α^1)…
        nxt = [0] * (len(gen) + 1)
        for j, c in enumerate(gen):
            nxt[j] ^= _mul(c, _EXP[i])
            nxt[j + 1] ^= c
        gen = nxt
    gen = list(reversed(gen))[1:]  # sem o coeficiente líder (=1), do maior grau para o menor
    rem = [0] * ndeg
    for b in data:
        f = b ^ rem[0]
        rem = rem[1:] + [0]
        for i in range(ndeg):
            rem[i] ^= _mul(gen[i], f)
    return rem


def _bits(value: int, n: int) -> List[int]:
    return [(value >> i) & 1 for i in range(n - 1, -1, -1)]


def _choose_version(n: int) -> int:
    for v in range(1, 11):
        cap = sum(b * d for b, d in _EC_M[v][1])
        need = 4 + (8 if v < 10 else 16) + 8 * n
        if need <= cap * 8:
            return v
    raise ValueError(f"texto grande demais para o QR ({n} bytes; o máximo é {MAX_BYTES})")


def _codewords(data: bytes, version: int) -> List[int]:
    ec_len, groups = _EC_M[version]
    cap = sum(b * d for b, d in groups) * 8
    bits = _bits(0b0100, 4) + _bits(len(data), 8 if version < 10 else 16)
    for byte in data:
        bits += _bits(byte, 8)
    bits += [0] * min(4, cap - len(bits))
    bits += [0] * (-len(bits) % 8)
    pad = [0xEC, 0x11]
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    while len(words) * 8 < cap:
        words.append(pad[(len(words) - len(bits) // 8) % 2])
    blocks, pos = [], 0
    for count, dlen in groups:
        for _ in range(count):
            blocks.append(words[pos:pos + dlen])
            pos += dlen
    ecs = [_rs_remainder(b, ec_len) for b in blocks]
    out: List[int] = []
    for i in range(max(len(b) for b in blocks)):  # intercala os blocos de dados e depois os de correção
        out += [b[i] for b in blocks if i < len(b)]
    for i in range(ec_len):
        out += [e[i] for e in ecs]
    return out


def _bch(value: int, poly: int, deg: int, shift: int) -> int:
    v = value << shift
    for i in range(deg + shift - 1, shift - 1, -1):
        if (v >> i) & 1:
            v ^= poly << (i - shift)
    return (value << shift) | v


def _build(version: int, words: List[int], mask: int) -> List[List[bool]]:
    size = version * 4 + 17
    mod = [[False] * size for _ in range(size)]
    fn = [[False] * size for _ in range(size)]  # módulos de função (não recebem dados nem máscara)

    def put(x: int, y: int, dark: bool) -> None:
        mod[y][x], fn[y][x] = dark, True

    def finder(cx: int, cy: int) -> None:
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    d = max(abs(dx), abs(dy))
                    put(x, y, d not in (2, 4))

    finder(3, 3), finder(size - 4, 3), finder(3, size - 4)
    for i in range(size):  # tempo
        if not fn[6][i]:
            put(i, 6, i % 2 == 0)
        if not fn[i][6]:
            put(6, i, i % 2 == 0)
    pts = _ALIGN[version]
    for ai, ay in enumerate(pts):
        for bi, ax in enumerate(pts):
            if (ai == 0 and bi == 0) or (ai == 0 and bi == len(pts) - 1) or (ai == len(pts) - 1 and bi == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
    # formato: nível M = 00; reserva e preenche depois da máscara
    fmt = _bch((0b00 << 3) | mask, 0x537, 10, 10) ^ 0x5412
    # as duas cópias da informação de formato (15 bits, nível M + máscara)
    bits_fmt = [(fmt >> i) & 1 == 1 for i in range(15)]
    for i in range(0, 6):
        put(8, i, bits_fmt[i])
    put(8, 7, bits_fmt[6]), put(8, 8, bits_fmt[7]), put(7, 8, bits_fmt[8])
    for i in range(9, 15):
        put(14 - i, 8, bits_fmt[i])
    for i in range(0, 8):
        put(size - 1 - i, 8, bits_fmt[i])
    for i in range(8, 15):
        put(8, size - 15 + i, bits_fmt[i])
    put(8, size - 8, True)  # módulo escuro fixo
    if version >= 7:
        info = _bch(version, 0x1F25, 12, 12)
        for i in range(18):
            bit = (info >> i) & 1 == 1
            a, b = size - 11 + i % 3, i // 3
            put(a, b, bit)
            put(b, a, bit)
    # dados em zigue-zague, de baixo para cima, em colunas duplas da direita para a esquerda
    bits = [b for w in words for b in _bits(w, 8)]
    i = 0
    x = size - 1
    up = True
    while x > 0:
        if x == 6:
            x -= 1
        for k in range(size):
            y = size - 1 - k if up else k
            for xx in (x, x - 1):
                if not fn[y][xx]:
                    dark = bits[i] == 1 if i < len(bits) else False
                    i += 1
                    cond = [(xx + y) % 2 == 0, y % 2 == 0, xx % 3 == 0, (xx + y) % 3 == 0, (xx // 3 + y // 2) % 2 == 0,
                            (xx * y) % 2 + (xx * y) % 3 == 0, ((xx * y) % 2 + (xx * y) % 3) % 2 == 0, ((xx + y) % 2 + (xx * y) % 3) % 2 == 0][mask]
                    mod[y][xx] = dark != cond
        x -= 2
        up = not up
    return mod


def _penalty(m: List[List[bool]]) -> int:
    n = len(m)
    score = 0
    for grid in (m, [list(r) for r in zip(*m)]):  # regra 1 (sequências) e 3 (padrão tipo localizador) em linhas e colunas
        for row in grid:
            run, prev = 0, None
            for c in row:
                if c == prev:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run, prev = 1, c
            if run >= 5:
                score += run - 2
            s = "".join("1" if c else "0" for c in row)
            score += 40 * (s.count("10111010000") + s.count("00001011101"))
    for y in range(n - 1):  # regra 2 (blocos 2×2)
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark = sum(c for r in m for c in r)
    score += (abs(dark * 20 - n * n * 10) // (n * n)) * 10  # regra 4 (proporção de escuros)
    return score


def matrix(text: str) -> List[List[bool]]:
    data = text.encode("utf-8")
    version = _choose_version(len(data))
    words = _codewords(data, version)
    return min((_build(version, words, mk) for mk in range(8)), key=_penalty)


def svg(text: str, scale: int = 6, border: int = 4, dark: str = "#000", light: str = "#fff") -> str:
    m = matrix(text)
    n = len(m) + border * 2
    cells = "".join(f"M{x + border},{y + border}h1v1h-1z" for y, row in enumerate(m) for x, c in enumerate(row) if c)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{n * scale}" height="{n * scale}" shape-rendering="crispEdges" role="img" aria-label="QR code">'
            f'<rect width="{n}" height="{n}" fill="{light}"/><path d="{cells}" fill="{dark}"/></svg>')


def terminal(text: str, border: int = 2) -> str:
    """O QR em blocos Unicode (2 linhas de módulos por linha de texto), com fundo claro para qualquer tema de terminal."""
    m = matrix(text)
    n = len(m)
    pad = [[False] * (n + border * 2)] * border
    g = pad + [[False] * border + r + [False] * border for r in m] + pad
    if len(g) % 2:
        g.append([False] * len(g[0]))
    out = []
    for y in range(0, len(g), 2):
        out.append("".join({(False, False): "█", (True, False): "▄", (False, True): "▀", (True, True): " "}[(g[y][x], g[y + 1][x])] for x in range(len(g[0]))))
    return "\n".join(out)
