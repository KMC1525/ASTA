"""Efeitos sonoros do Studio (v0.17): um catálogo de efeitos para pôr na timeline, gerados no próprio ASTA (sem internet nem modelo), com a síntese do Canvas (núcleo Rust).

Cada efeito é determinístico para a mesma semente. Os conhecidos do Canvas (explosão, laser, moeda, pulo, impacto…) são reaproveitados; os de edição de vídeo
(whoosh, riser, estalo, glitch, rebobinar…) são feitos aqui.
"""
from __future__ import annotations

import random
from typing import Any, Callable, Dict, List

from ..canvas import procedural as P

# id → (rótulo, duração padrão em segundos)
CATALOG: Dict[str, Any] = {
    "whoosh": ("Whoosh (passagem)", 0.9), "riser": ("Riser (tensão subindo)", 3.0), "impact": ("Impacto grave", 1.4), "boom": ("Explosão", 1.8), "click": ("Clique", 0.12),
    "pop": ("Pop", 0.18), "ding": ("Sino (ding)", 1.2), "glitch": ("Glitch digital", 0.7), "rewind": ("Rebobinar", 1.2), "laser": ("Laser", 0.45), "coin": ("Moeda", 0.45),
    "jump": ("Pulo", 0.3), "magic": ("Magia", 1.0), "alarm": ("Alarme", 2.0), "knock": ("Batidas na porta", 1.0), "steps": ("Passos", 3.0), "rain": ("Chuva", 5.0),
    "wind": ("Vento", 5.0), "thunder": ("Trovão", 3.0), "bird": ("Pássaros", 2.0),
}


def _whoosh(d: float, rnd: random.Random) -> List[float]:
    n = int(d * P.SR)
    base = P._noise(d, rnd, 0.9, 0.35)
    env = [min(1.0, i / (n * 0.45)) ** 1.6 * min(1.0, (n - i) / (n * 0.55)) ** 1.2 for i in range(n)]   # sobe rápido e some devagar: a «passagem»
    return [v * e for v, e in zip(base, env)]


def _riser(d: float, rnd: random.Random) -> List[float]:
    n = int(d * P.SR)
    tone = P._tone(180, d, "saw", 0.25, 1800)
    noise = P._noise(d, rnd, 0.35, 0.3)
    return [(a + b) * (i / n) ** 2 for i, (a, b) in enumerate(zip(tone, noise))]


def _impact(d: float, rnd: random.Random) -> List[float]:
    return P._mixdown([P._tone(70, d, "sine", 0.9, 28), P._noise(min(d, 0.5), rnd, 0.8, 0.15, 6)])


def _click(d: float, rnd: random.Random) -> List[float]:
    return P._mixdown([P._noise(0.03, rnd, 0.7, 0.6, 60), P._tone(1800, 0.05, "square", 0.25)])


def _pop(d: float, rnd: random.Random) -> List[float]:
    return P._tone(520, d, "sine", 0.6, 160)


def _ding(d: float, rnd: random.Random) -> List[float]:
    n = int(d * P.SR)
    parts = [P._tone(f, d, "sine", v) for f, v in ((1320, 0.5), (1980, 0.22), (2640, 0.12))]
    mixed = P._mixdown(parts, n)
    return [v * (1 - i / n) ** 2 for i, v in enumerate(mixed)]


def _glitch(d: float, rnd: random.Random) -> List[float]:
    out: List[float] = []
    while len(out) < d * P.SR:
        step = rnd.choice((0.03, 0.05, 0.08))
        out += P._tone(rnd.choice((220, 440, 880, 1760, 3300)), step, rnd.choice(("square", "saw")), 0.3) if rnd.random() < 0.7 else P._noise(step, rnd, 0.5, 0.7)
    return out[: int(d * P.SR)]


def _rewind(d: float, rnd: random.Random) -> List[float]:
    n = int(d * P.SR)
    a = P._tone(2400, d, "saw", 0.22, 300)
    b = P._noise(d, rnd, 0.3, 0.5, 0, 22)
    return [(x + y) * min(1.0, (n - i) / (n * 0.2)) for i, (x, y) in enumerate(zip(a, b))]


_OWN: Dict[str, Callable[[float, random.Random], List[float]]] = {"whoosh": _whoosh, "riser": _riser, "impact": _impact, "click": _click, "pop": _pop, "ding": _ding, "glitch": _glitch, "rewind": _rewind}
_CANVAS = {"boom": "explosion", "laser": "laser", "coin": "coin", "jump": "jump", "magic": "magic", "alarm": "alarm", "knock": "knock", "steps": "steps", "rain": "rain",
           "wind": "wind", "thunder": "thunder", "bird": "bird"}


def describe() -> List[Dict[str, Any]]:
    return [{"id": k, "label": v[0], "dur": v[1]} for k, v in CATALOG.items()]


def render(kind: str, duration: float = 0.0, seed: int = 0) -> bytes:
    """O efeito `kind` como WAV mono. `duration` 0 = a duração padrão do efeito (0,1 a 30 s)."""
    if kind not in CATALOG:
        raise ValueError("Efeito desconhecido.")
    d = max(0.1, min(30.0, float(duration) if duration else float(CATALOG[kind][1])))
    rnd = random.Random(P.seed_of("studio-sfx", kind, seed))
    if kind in _OWN:
        samples = _OWN[kind](d, rnd)
    else:
        samples = P._fx(_CANVAS[kind], d, rnd)
        if kind in ("steps", "rain", "wind", "alarm", "bird"):
            samples = (samples + [0.0] * int(d * P.SR))[: int(d * P.SR)]
    # fade curto nas pontas: sem estalo ao cortar
    n = len(samples)
    f = min(n // 2, int(0.01 * P.SR))
    for i in range(f):
        samples[i] *= i / f
        samples[n - 1 - i] *= i / f
    return P.wav_bytes(samples)
