"""Mapas do Game Engine: geradores procedurais (2D de blocos, 2.5D isométrico com alturas e 3D com mapa de alturas) e edição por região.

Tudo determinístico por `seed` e sem dependências: o mesmo pedido gera o mesmo mundo, e uma região escolhida pode ser gerada de novo sem mexer no resto.
A IA (aba Map / Main) escolhe tema, tamanho e objetos; este módulo desenha o terreno e garante que o jogo é possível (objetivo e itens alcançáveis)."""
from __future__ import annotations

import math
import random
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from . import schema as S


def _num(v: Any, default: float = 0.0, lo: float = -1e9, hi: float = 1e9) -> float:
    """Número finito dentro de [lo, hi]: texto, NaN e infinito (que o JSON do navegador pode trazer) viram o padrão."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(x) or math.isinf(x) else max(lo, min(hi, x))

# ============================================================================ ruído
def _hash(ix: int, iz: int, seed: int) -> float:
    n = (ix * 374761393 + iz * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    n ^= n >> 16
    return (n & 0xFFFFFF) / 0xFFFFFF


def vnoise(x: float, z: float, seed: int) -> float:
    ix, iz = math.floor(x), math.floor(z)
    fx, fz = x - ix, z - iz
    fx, fz = fx * fx * (3 - 2 * fx), fz * fz * (3 - 2 * fz)
    a, b = _hash(ix, iz, seed), _hash(ix + 1, iz, seed)
    c, d = _hash(ix, iz + 1, seed), _hash(ix + 1, iz + 1, seed)
    return (a * (1 - fx) + b * fx) * (1 - fz) + (c * (1 - fx) + d * fx) * fz


def fbm(x: float, z: float, seed: int, octaves: int = 4, gain: float = 0.5) -> float:
    amp, tot, norm, f = 1.0, 0.0, 0.0, 1.0
    for o in range(octaves):
        tot += vnoise(x * f, z * f, seed + o * 101) * amp
        norm += amp
        amp *= gain
        f *= 2
    return tot / norm


# ============================================================================ 2D de blocos
PALETTES: Dict[str, Dict[str, Dict[str, Any]]] = {}


def palette2d(theme: str) -> Dict[str, Dict[str, Any]]:
    c = S.THEME_COLORS.get(theme, S.THEME_COLORS["forest"])
    return {
        "1": {"name": "chão", "color": c["ground"], "solid": True, "kind": "grass"},
        "2": {"name": "terra", "color": c["dirt"], "solid": True, "kind": "dirt"},
        "3": {"name": "pedra", "color": c["stone"], "solid": True, "kind": "stone"},
        "4": {"name": "madeira", "color": "#a0784f", "solid": True, "kind": "wood"},
        "5": {"name": "água", "color": c["water"], "solid": False, "kind": "water"},
        "6": {"name": "caminho", "color": _mix(c["ground"], c["dirt"], 0.5), "solid": False, "kind": "dirt"},
        "7": {"name": "tijolo", "color": "#b5483a", "solid": True, "kind": "brick"},
        "8": {"name": "lava", "color": "#e8541c", "solid": False, "kind": "lava"},
    }


def _mix(a: str, b: str, t: float) -> str:
    def p(c: str) -> Tuple[int, int, int]:
        c = c.lstrip("#")
        c = "".join(ch * 2 for ch in c) if len(c) == 3 else c
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    x, y = p(a), p(b)
    return "#%02x%02x%02x" % tuple(int(x[i] + (y[i] - x[i]) * t) for i in range(3))


SIZES = {"short": 1, "medium": 1.5, "long": 2.2}


def gen_platformer(seed: int, theme: str = "forest", length: str = "medium", enemies: float = 1.0, coins: float = 1.0) -> Dict[str, Any]:
    rnd = random.Random(seed)
    w = int(70 * SIZES.get(length, 1.5))
    h = 20
    grid = [[0] * w for _ in range(h)]
    ground = 14
    gaps: List[int] = []
    heights = []
    x = 0
    while x < w:
        if 8 < x < w - 10 and rnd.random() < 0.12 and not gaps[-1:] == [x - 1]:
            gl = rnd.choice((2, 2, 3))
            for k in range(gl):
                heights.append(None)
            x += gl
            continue
        step = rnd.choice((-1, 0, 0, 0, 1)) if x > 4 and x < w - 6 else 0
        ground = max(10, min(16, ground + (step if rnd.random() < 0.35 else 0)))
        heights.append(ground)
        x += 1
    heights = heights[:w] + [14] * max(0, w - len(heights))
    for cx, g in enumerate(heights):
        if g is None:
            continue
        for cy in range(g, h):
            grid[cy][cx] = 1 if cy == g else 2
    platforms: List[Tuple[int, int, int]] = []
    for _ in range(int(w / 7)):
        px = rnd.randint(6, w - 12)
        base = heights[px] if heights[px] is not None else 14
        py = max(5, base - rnd.randint(4, 6))
        ln = rnd.randint(3, 5)
        platforms.append((px, py, ln))
        for k in range(ln):
            if px + k < w:
                grid[py][px + k] = 4
    objs: List[Dict[str, Any]] = [{"type": "player", "x": 2, "y": (heights[2] or 14) - 1}]
    for px, py, ln in platforms:
        if rnd.random() < coins * 0.9:
            for k in range(ln):
                objs.append({"type": "coin", "x": px + k, "y": py - 1})
    for cx in range(8, w - 6):
        g = heights[cx]
        if g is None:
            continue
        if rnd.random() < 0.035 * enemies and heights[cx - 1] is not None and heights[cx + 1] is not None:
            objs.append({"type": "enemy", "x": cx, "y": g - 1, "range": rnd.choice((70, 90, 120))})
        elif rnd.random() < 0.02 * enemies:
            objs.append({"type": "spike", "x": cx, "y": g - 1})
        elif rnd.random() < 0.012:
            objs.append({"type": "spring", "x": cx, "y": g - 1})
        elif rnd.random() < 0.05 * coins:
            objs.append({"type": "coin", "x": cx, "y": g - 2})
    for cx in range(10, w - 8, 9):
        if rnd.random() < 0.55 and heights[cx] is not None:
            objs.append({"type": "heart" if rnd.random() < 0.18 else "gem", "x": cx, "y": (heights[cx] or 14) - 4})
    objs.append({"type": "goal", "x": w - 3, "y": (heights[w - 3] or 14) - 2})
    return {"kind": "2d", "name": "Fase 1", "theme": theme, "seed": seed, "genre": "platformer", "tile": 32, "w": w, "h": h, "palette": palette2d(theme), "layers": [{"name": "chão", "data": grid}], "objects": objs}


def _bfs(grid: List[List[int]], solid: set, start: Tuple[int, int]) -> set:
    h, w = len(grid), len(grid[0])
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen and grid[ny][nx] not in solid:
                seen.add((nx, ny))
                q.append((nx, ny))
    return seen


def gen_topdown(seed: int, theme: str = "forest", length: str = "medium", enemies: float = 1.0, coins: float = 1.0) -> Dict[str, Any]:
    rnd = random.Random(seed)
    k = SIZES.get(length, 1.5)
    w, h = int(34 * k), int(24 * k)
    grid = [[0] * w for _ in range(h)]
    solid_ids = {3, 4, 7}
    for y in range(h):
        for x in range(w):
            if x in (0, w - 1) or y in (0, h - 1):
                grid[y][x] = 3
                continue
            n = fbm(x / 6.0, y / 6.0, seed, 3)
            if n < 0.30:
                grid[y][x] = 5
            elif n > 0.74:
                grid[y][x] = 3
            elif rnd.random() < 0.05:
                grid[y][x] = 4
            else:
                grid[y][x] = 1
    sx, sy = 3, h // 2
    gx, gy = w - 4, rnd.randint(4, h - 5)
    for (cx, cy) in ((sx, sy), (gx, gy)):               # clareiras de início e fim
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if 0 < cx + dx < w - 1 and 0 < cy + dy < h - 1:
                    grid[cy + dy][cx + dx] = 1
    x, y = sx, sy                                       # caminho garantido do início ao objetivo
    while (x, y) != (gx, gy):
        if x != gx and (y == gy or rnd.random() < 0.65):
            x += 1 if gx > x else -1
        else:
            y += 1 if gy > y else -1
        for dy, dx in ((0, 0), (1, 0), (0, 1)):
            if 0 < x + dx < w - 1 and 0 < y + dy < h - 1:
                grid[y + dy][x + dx] = 6
    # água nunca bloqueia (é só perigo visual): só pedra/madeira bloqueiam; água vira passagem lenta? — mantém intransponível para dar forma ao mapa
    reach = sorted(_bfs(grid, solid_ids | {5}, (sx, sy)))
    free = [c for c in reach if abs(c[0] - sx) + abs(c[1] - sy) > 4 and abs(c[0] - gx) + abs(c[1] - gy) > 2]
    rnd.shuffle(free)
    objs: List[Dict[str, Any]] = [{"type": "player", "x": sx, "y": sy}, {"type": "goal", "x": gx, "y": gy}]
    n_coin, n_enemy = int(len(free) * 0.025 * coins) + 6, int(len(free) * 0.012 * enemies) + 2
    for c in free[:n_coin]:
        objs.append({"type": "coin", "x": c[0], "y": c[1]})
    for c in free[n_coin:n_coin + n_enemy]:
        objs.append({"type": rnd.choice(("enemy", "chaser")), "x": c[0], "y": c[1], "range": 80})
    for c in free[n_coin + n_enemy:n_coin + n_enemy + 3]:
        objs.append({"type": "gem", "x": c[0], "y": c[1]})
    if len(free) > n_coin + n_enemy + 5:
        c = free[n_coin + n_enemy + 3]
        objs.append({"type": "npc", "x": c[0], "y": c[1], "name": "Guia", "dialogue": "guia"})
        objs.append({"type": "heart", "x": free[n_coin + n_enemy + 4][0], "y": free[n_coin + n_enemy + 4][1]})
    return {"kind": "2d", "name": "Mapa 1", "theme": theme, "seed": seed, "genre": "topdown", "tile": 32, "w": w, "h": h, "palette": palette2d(theme), "layers": [{"name": "chão", "data": grid}], "objects": objs}


def gen_shooter(seed: int, theme: str = "space", length: str = "medium", enemies: float = 1.0, coins: float = 1.0) -> Dict[str, Any]:
    rnd = random.Random(seed)
    w, h = int(110 * SIZES.get(length, 1.5)), 17
    grid = [[0] * w for _ in range(h)]
    for _ in range(int(w / 9)):                          # asteroides sólidos
        ax, ay = rnd.randint(14, w - 8), rnd.randint(1, h - 3)
        for dy in range(rnd.randint(1, 2)):
            for dx in range(rnd.randint(1, 3)):
                if ay + dy < h - 1 and ax + dx < w:
                    grid[ay + dy][ax + dx] = 3
    objs: List[Dict[str, Any]] = [{"type": "player", "x": 2, "y": h // 2}, {"type": "goal", "x": w - 3, "y": h // 2}]
    for cx in range(10, w - 6, 3):
        if rnd.random() < 0.5 * coins:
            objs.append({"type": "coin", "x": cx, "y": rnd.randint(2, h - 3)})
        if rnd.random() < 0.28 * enemies:
            objs.append({"type": "flyer", "x": cx + 1, "y": rnd.randint(2, h - 3), "range": rnd.choice((80, 120))})
    pal = palette2d(theme)
    pal["3"]["name"] = "asteroide"
    return {"kind": "2d", "name": "Setor 1", "theme": theme, "seed": seed, "genre": "shooter", "tile": 32, "w": w, "h": h, "palette": pal, "layers": [{"name": "espaço", "data": grid}], "objects": objs, "walls": False}


def gen_iso(seed: int, theme: str = "forest", length: str = "medium", enemies: float = 1.0, coins: float = 1.0) -> Dict[str, Any]:
    rnd = random.Random(seed)
    n = int(18 * (SIZES.get(length, 1.5) ** 0.7))
    grid = [[0] * n for _ in range(n)]
    heights = [[0] * n for _ in range(n)]
    for y in range(n):
        for x in range(n):
            d = max(abs(x - n / 2), abs(y - n / 2)) / (n / 2)
            v = fbm(x / 4.0, y / 4.0, seed, 3) - d * 0.55
            if v < 0.0 - 0.02:
                grid[y][x] = 0                                    # fora da ilha
            elif v < 0.12:
                grid[y][x] = 5                                    # água: não se anda nela
                heights[y][x] = 0
            else:
                grid[y][x] = 1 if v < 0.55 else 3
                heights[y][x] = 1 if v < 0.38 else 2 if v < 0.55 else 3
    # rampas: diferença máxima de 1 bloco entre vizinhos andáveis
    for _ in range(4):
        for y in range(n):
            for x in range(n):
                if grid[y][x] in (1, 3):
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < n and 0 <= ny < n and grid[ny][nx] in (1, 3) and heights[y][x] - heights[ny][nx] > 1:
                            heights[y][x] = heights[ny][nx] + 1
    cx, cy = n // 2, n // 2
    for r in range(0, 2):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                grid[cy + dy][cx + dx] = 1
                heights[cy + dy][cx + dx] = 1
    walk = lambda c: grid[c[1]][c[0]] in (1, 3)          # noqa: E731
    h, w = n, n
    reach = [c for c in _bfs_walk(grid, heights, (cx, cy)) if abs(c[0] - cx) + abs(c[1] - cy) > 2]
    rnd.shuffle(reach)
    objs: List[Dict[str, Any]] = [{"type": "player", "x": cx, "y": cy}]
    far = sorted(reach, key=lambda c: -(abs(c[0] - cx) + abs(c[1] - cy)))
    if far:
        objs.append({"type": "goal", "x": far[0][0], "y": far[0][1]})
    pool = [c for c in reach if not far or c != far[0]]
    nc, ne = max(6, int(len(pool) * 0.07 * coins)), max(2, int(len(pool) * 0.03 * enemies))
    for c in pool[:nc]:
        objs.append({"type": "coin", "x": c[0], "y": c[1]})
    for c in pool[nc:nc + ne]:
        objs.append({"type": "enemy", "x": c[0], "y": c[1], "range": 2})
    for c in pool[nc + ne:nc + ne + 2]:
        objs.append({"type": "gem", "x": c[0], "y": c[1]})
    if len(pool) > nc + ne + 3:
        c = pool[nc + ne + 2]
        objs.append({"type": "npc", "x": c[0], "y": c[1], "name": "Guia", "dialogue": "guia"})
    pal = palette2d(theme)
    pal["1"]["solid"] = False
    pal["3"]["solid"] = False
    pal["5"]["solid"] = True
    return {"kind": "2d", "name": "Ilha 1", "theme": theme, "seed": seed, "genre": "iso", "tile": 32, "w": w, "h": h, "palette": pal, "layers": [{"name": "chão", "data": grid}], "heights": heights, "objects": objs}


def _bfs_walk(grid: List[List[int]], heights: List[List[int]], start: Tuple[int, int]) -> set:
    n_h, n_w = len(grid), len(grid[0])
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < n_w and 0 <= ny < n_h and (nx, ny) not in seen and grid[ny][nx] in (1, 3) and heights[ny][nx] - heights[y][x] <= 1:
                seen.add((nx, ny))
                q.append((nx, ny))
    return seen


GEN2D = {"platformer": gen_platformer, "topdown": gen_topdown, "shooter": gen_shooter, "iso": gen_iso}


def generate_2d(genre: str, seed: int, theme: str = "forest", length: str = "medium", enemies: float = 1.0, coins: float = 1.0) -> Dict[str, Any]:
    fn = GEN2D.get(genre) or gen_platformer
    return S.norm_map(fn(seed, theme, length, _num(enemies, 1.0, 0, 20), _num(coins, 1.0, 0, 20)))


def regen_region_2d(m: Dict[str, Any], region: Dict[str, int], seed: int = 0, prompt_hint: str = "") -> Dict[str, Any]:
    """Gera de novo só um retângulo do mapa 2D (x0,y0,x1,y1 em blocos): usa um mapa novo do mesmo gênero/tema e recorta o pedaço, mantendo objetos de fora."""
    genre = m.get("genre") or "platformer"
    theme = m.get("theme") or "forest"
    fresh = GEN2D.get(genre, gen_platformer)(seed or random.randint(1, 1 << 30), theme, "long", 1.0, 1.0)
    x0, y0, x1, y1 = [int(region.get(k, 0)) for k in ("x0", "y0", "x1", "y1")]
    x0, x1 = sorted((max(0, x0), min(m["w"] - 1, x1)))
    y0, y1 = sorted((max(0, y0), min(m["h"] - 1, y1)))
    grid = [row[:] for row in m["layers"][0]["data"]]
    fg = fresh["layers"][0]["data"]
    oy = max(0, (fresh["h"] - m["h"]) // 2) if genre == "topdown" else 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            fy = min(len(fg) - 1, y + oy) if genre != "platformer" else y
            fx = (x + (seed % max(1, fresh["w"] - m["w"])) if fresh["w"] > m["w"] else x) if genre != "platformer" else x + (fresh["w"] - m["w"]) // 2
            if 0 <= fy < len(fg) and 0 <= fx < len(fg[0]):
                grid[y][x] = fg[fy][fx]
    keep = [o for o in m.get("objects", []) if not (x0 <= o.get("x", -1) <= x1 and y0 <= o.get("y", -1) <= y1) or o.get("type") in ("player", "goal")]
    rnd = random.Random(seed or 1)
    solid = {int(k) for k, v in m["palette"].items() if v.get("solid")}
    add = []
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if grid[y][x] in solid and y > 0 and grid[y - 1][x] not in solid and genre == "platformer" and rnd.random() < 0.14:
                add.append({"type": rnd.choice(("coin", "coin", "enemy")), "x": x, "y": y - 1})
            elif genre in ("topdown", "iso") and grid[y][x] in (1, 6) and rnd.random() < 0.05:
                add.append({"type": rnd.choice(("coin", "coin", "enemy", "gem")), "x": x, "y": y})
    out = dict(m)
    out["layers"] = [dict(m["layers"][0], data=grid)]
    out["objects"] = keep + add
    return S.norm_map(out)


# ============================================================================ 3D: mapa de alturas
BIOME_COLORS = {
    "temperate": {"low": "#d8c690", "mid": "#5e9c4a", "high": "#8a7b6a", "peak": "#f2f2f2", "shore": "#cdb87a", "water": "#2f7fbf"},
    "forest": {"low": "#b8a878", "mid": "#3f7d3a", "high": "#6e6a55", "peak": "#e6e6e6", "shore": "#b8a878", "water": "#2c6a9a"},
    "desert": {"low": "#e8cf8c", "mid": "#d9a860", "high": "#b9824a", "peak": "#e8d0a0", "shore": "#f0dca0", "water": "#3d9fb8"},
    "snow": {"low": "#dbe9f6", "mid": "#f1f7fc", "high": "#c4d6e8", "peak": "#ffffff", "shore": "#b8cde0", "water": "#5aa7d6"},
    "tropical": {"low": "#f0dca0", "mid": "#3fa34d", "high": "#6b8f4a", "peak": "#d8e6c0", "shore": "#f0dca0", "water": "#1fb5c9"},
    "island": {"low": "#f0dca0", "mid": "#58a84a", "high": "#7a8a5a", "peak": "#cfd6c0", "shore": "#f4e4b0", "water": "#1f9fd0"},
    "mountain": {"low": "#7d8a6a", "mid": "#8b8f7a", "high": "#9a9a9a", "peak": "#ffffff", "shore": "#a09a80", "water": "#3b6ea5"},
    "swamp": {"low": "#5d6b3a", "mid": "#4a6b3a", "high": "#6b5a3a", "peak": "#8a8a6a", "shore": "#6b6b3a", "water": "#3a5a4a"},
    "wasteland": {"low": "#8a7a68", "mid": "#7a6a58", "high": "#5a4a40", "peak": "#9a8a78", "shore": "#8a7a68", "water": "#5a4a3a"},
    "volcanic": {"low": "#3a2f2c", "mid": "#4a3a34", "high": "#2c2220", "peak": "#8a3a1a", "shore": "#3a2f2c", "water": "#e8541c"},
}
BIOME_PARAMS = {  # relevo, nível da água, árvores, pedras
    "temperate": (0.55, 0.18, 0.5, 0.2), "forest": (0.5, 0.15, 1.0, 0.2), "desert": (0.4, 0.04, 0.03, 0.35), "snow": (0.6, 0.1, 0.25, 0.3), "tropical": (0.5, 0.25, 0.8, 0.15),
    "island": (0.6, 0.32, 0.5, 0.15), "mountain": (1.0, 0.1, 0.25, 0.45), "swamp": (0.2, 0.32, 0.4, 0.1), "wasteland": (0.5, 0.0, 0.0, 0.5), "volcanic": (0.9, 0.12, 0.0, 0.5),
}
BIOME_OF_THEME = {"forest": "forest", "desert": "desert", "snow": "snow", "night": "temperate", "cave": "mountain", "city": "wasteland", "space": "wasteland", "sea": "island", "candy": "tropical", "lava": "volcanic", "retro": "temperate", "sunset": "temperate"}


def gen_terrain(seed: int, biome: str = "temperate", res: int = 65, size: float = 200.0, height: float = 26.0, objects: bool = True, density: float = 1.0, coins: int = 14, enemies: int = 4) -> Dict[str, Any]:
    biome = biome if biome in S.BIOMES else "temperate"
    relief, wl, trees, rocks = BIOME_PARAMS[biome]
    rnd = random.Random(seed)
    res = max(17, min(S.MAP3D_MAX_RES, res))
    hm: List[int] = []
    for j in range(res):
        for i in range(res):
            u, v = i / (res - 1), j / (res - 1)
            d = max(abs(u - 0.5), abs(v - 0.5)) * 2                        # 0 no centro, 1 na borda
            n = fbm(u * 3.2, v * 3.2, seed, 5, 0.52)
            ridge = 1 - abs(2 * fbm(u * 2.4 + 9, v * 2.4 + 4, seed + 7, 4) - 1)
            val = n * (1 - relief * 0.5) + ridge * relief * 0.5
            val = val * (1 - d ** 2.2 * (0.9 if biome == "island" else 0.55)) + 0.1
            flat = max(0.0, 1 - math.hypot(u - 0.5, v - 0.5) / 0.09)           # planalto de partida no centro
            val = val * (1 - flat) + max(val, wl + 0.07) * flat * 0.9 + (wl + 0.07) * flat * 0.1
            hm.append(int(max(0, min(255, val * 255))))
    objs: List[Dict[str, Any]] = []
    half = size / 2

    def h_at(i: int, j: int) -> float:
        return hm[j * res + i] / 255

    def slope(i: int, j: int) -> float:
        a = h_at(i, j)
        return max(abs(a - h_at(min(res - 1, i + 1), j)), abs(a - h_at(i, min(res - 1, j + 1))), abs(a - h_at(max(0, i - 1), j)), abs(a - h_at(i, max(0, j - 1))))

    cells = [(i, j) for j in range(2, res - 2) for i in range(2, res - 2) if h_at(i, j) > wl + 0.03 and slope(i, j) < 0.045]
    rnd.shuffle(cells)

    def pos(c: Tuple[int, int]) -> Tuple[float, float]:
        return round((c[0] / (res - 1) - 0.5) * size, 2), round((c[1] / (res - 1) - 0.5) * size, 2)

    cx, cz = pos((res // 2, res // 2))
    objs.append({"type": "player", "x": cx, "z": cz})
    if objects:
        far = sorted(cells, key=lambda c: -math.hypot(c[0] - res // 2, c[1] - res // 2))[:20]
        gx, gz = pos(far[0]) if far else (half - 8, half - 8)
        objs.append({"type": "goal", "x": gx, "z": gz})
        used: List[Tuple[float, float]] = [(cx, cz), (gx, gz)]

        def free(x: float, z: float, r: float) -> bool:
            return all(math.hypot(x - ux, z - uz) > r for ux, uz in used)
        want_trees = int(res * res * 0.012 * trees * density)
        for c in cells:
            if want_trees <= 0:
                break
            x, z = pos(c)
            if free(x, z, 4) and h_at(*c) < 0.62:
                objs.append({"type": "tree", "x": x, "z": z, "s": round(0.8 + rnd.random() * 0.7, 2), "ry": rnd.randint(0, 359)})
                used.append((x, z))
                want_trees -= 1
        want_rocks = int(res * res * 0.004 * rocks * density)
        for c in reversed(cells):
            if want_rocks <= 0:
                break
            x, z = pos(c)
            if free(x, z, 3):
                objs.append({"type": "rock", "x": x, "z": z, "s": round(0.6 + rnd.random() * 1.6, 2), "ry": rnd.randint(0, 359)})
                used.append((x, z))
                want_rocks -= 1
        flats = [c for c in cells if slope(*c) < 0.012 and math.hypot(c[0] - res // 2, c[1] - res // 2) > 6]
        for c in flats[:2]:
            x, z = pos(c)
            if free(x, z, 12):
                objs.append({"type": "house", "x": x, "z": z, "ry": rnd.choice((0, 90, 180, 270))})
                used.append((x, z))
                if len(objs) and not any(o["type"] == "npc" for o in objs):
                    objs.append({"type": "npc", "x": round(x + 4.5, 2), "z": round(z + 2, 2), "name": "Guia", "dialogue": "guia"})
        k = 0
        for c in cells[::3]:
            if k >= coins:
                break
            x, z = pos(c)
            if free(x, z, 3):
                objs.append({"type": "gem" if k % 6 == 5 else "coin", "x": x, "z": z})
                used.append((x, z))
                k += 1
        e = 0
        for c in cells[1::5]:
            if e >= enemies:
                break
            x, z = pos(c)
            if free(x, z, 10) and math.hypot(x - cx, z - cz) > 25:
                objs.append({"type": "chaser" if e % 2 else "enemy", "x": x, "z": z, "range": 6})
                used.append((x, z))
                e += 1
    return {"kind": "3d", "name": "Mundo 1", "theme": "forest", "seed": seed, "genre": "", "res": res, "size": size, "height": height, "water_level": wl, "heights": hm, "biome": biome, "colors": BIOME_COLORS[biome], "objects": objs}


def generate_3d(seed: int, theme: str = "forest", biome: str = "", size: float = 200.0, res: int = 65, coins: int = 14, enemies: int = 4, density: float = 1.0) -> Dict[str, Any]:
    biome = biome if biome in S.BIOMES else BIOME_OF_THEME.get(theme, "temperate")
    m = gen_terrain(seed, biome, res, size, 26.0, True, density, coins, enemies)
    m["theme"] = theme if theme in S.THEMES else "forest"
    return S.norm_map(m)


def edit_region_3d(m: Dict[str, Any], op: str, cx: float, cz: float, radius: float, strength: float = 0.5, seed: int = 0) -> Dict[str, Any]:
    """Ferramenta de pincel no mapa de alturas: raise, lower, smooth, flatten, noise, regen (cx, cz e radius em metros do mundo)."""
    res, size = m["res"], m["size"]
    hm = list(m["heights"])
    rnd = random.Random(seed or 1)
    cx, cz = _num(cx, 0.0, -1e6, 1e6), _num(cz, 0.0, -1e6, 1e6)
    radius, strength = _num(radius, 1.0, 0.0, 1e6), _num(strength, 0.5, -10.0, 10.0)
    ci, cj = (cx / size + 0.5) * (res - 1), (cz / size + 0.5) * (res - 1)
    r_cells = max(1.0, radius / size * (res - 1))
    base = hm[int(max(0, min(res - 1, round(cj)))) * res + int(max(0, min(res - 1, round(ci))))]
    new = list(hm)
    for j in range(max(0, int(cj - r_cells) - 1), min(res, int(cj + r_cells) + 2)):
        for i in range(max(0, int(ci - r_cells) - 1), min(res, int(ci + r_cells) + 2)):
            d = math.hypot(i - ci, j - cj)
            if d > r_cells:
                continue
            fall = (1 - d / r_cells) ** 1.5
            idx = j * res + i
            v = hm[idx]
            if op == "raise":
                v += 40 * strength * fall
            elif op == "lower":
                v -= 40 * strength * fall
            elif op == "smooth":
                nb = [hm[min(res - 1, max(0, j + dj)) * res + min(res - 1, max(0, i + di))] for dj in (-1, 0, 1) for di in (-1, 0, 1)]
                v = v + (sum(nb) / 9 - v) * min(1.0, strength * 1.4) * fall
            elif op == "flatten":
                v = v + (base - v) * min(1.0, strength * 1.5) * fall
            elif op == "noise":
                v += (rnd.random() - 0.5) * 60 * strength * fall
            elif op == "regen":
                nz = fbm(i / res * 3.2, j / res * 3.2, (seed or 1) + 13, 5) * 255
                v = v + (nz - v) * min(1.0, strength + 0.3) * fall
            new[idx] = int(max(0, min(255, v)))
    out = dict(m)
    out["heights"] = new
    wl = m.get("water_level", 0.18)
    kept = []
    for o in m.get("objects", []):        # objetos presos ao terreno ficam onde estão (a altura é recalculada pelo motor); remove os que ficaram debaixo d'água
        i, j = int(max(0, min(res - 1, (o.get("x", 0) / size + 0.5) * (res - 1)))), int(max(0, min(res - 1, (o.get("z", 0) / size + 0.5) * (res - 1))))
        if o.get("type") in ("player", "goal") or new[j * res + i] / 255 > wl + 0.01:
            kept.append(o)
    out["objects"] = kept
    return S.norm_map(out)


def edit_objects(m: Dict[str, Any], add: Optional[List[Dict[str, Any]]] = None, remove_near: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    out = dict(m)
    objs = list(m.get("objects", []))
    if isinstance(remove_near, dict) and remove_near:
        rx, rz, rr = _num(remove_near.get("x"), 0), _num(remove_near.get("z", remove_near.get("y", 0)), 0), _num(remove_near.get("r"), 1)
        key = "z" if m.get("kind") == "3d" else "y"
        objs = [o for o in objs if o.get("type") in ("player",) or math.hypot(o.get("x", 0) - rx, o.get(key, 0) - rz) > rr]
    objs.extend(o for o in (add if isinstance(add, list) else []) if isinstance(o, dict))
    out["objects"] = objs
    return S.norm_map(out)
