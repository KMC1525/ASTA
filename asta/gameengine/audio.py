"""Áudio procedural do Game Engine (só biblioteca padrão): efeitos, trilhas em laço e utilidades de WAV.

É o caminho que nunca falha: sem modelo de áudio configurado, a aba Sound e o gerador de jogos ainda entregam sons de verdade
(moeda, pulo, dano, vitória… e uma trilha por clima). Com um modelo (Canvas/provedores de mídia), a IA gera; isto serve de reserva."""
from __future__ import annotations

import io
import math
import random
import struct
import wave
from typing import Dict, Iterable, List, Optional, Tuple

RATE = 22050
TAU = math.tau


# ============================================================================ WAV
def to_wav(samples: Iterable[float], rate: int = RATE) -> bytes:
    """Mono 16 bits. Os valores são recortados em [-1, 1]."""
    data = bytearray()
    for s in samples:
        v = -1.0 if s < -1.0 else 1.0 if s > 1.0 else s
        data += struct.pack("<h", int(v * 32767))
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(data))
    return bio.getvalue()


def wav_info(data: bytes) -> Optional[Dict[str, float]]:
    """Taxa, canais e duração de um WAV PCM (None se não for um WAV legível)."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
            if rate <= 0:
                return None
            return {"rate": rate, "channels": ch, "frames": n, "seconds": round(n / rate, 3), "bits": w.getsampwidth() * 8}
    except (wave.Error, EOFError, struct.error, OSError, ValueError):
        return None


def wav_peaks(data: bytes, bins: int = 400) -> List[float]:
    """Envelope (0..1) para desenhar a forma de onda sem baixar o áudio inteiro."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            ch, sw, n = w.getnchannels(), w.getsampwidth(), w.getnframes()
            if sw != 2 or n == 0 or n > 20_000_000:
                return []
            raw = w.readframes(n)
    except (wave.Error, EOFError, OSError, ValueError):
        return []
    vals = struct.unpack("<%dh" % (len(raw) // 2), raw[:len(raw) // 2 * 2])
    step = max(1, len(vals) // bins)
    out = []
    for i in range(0, len(vals), step):
        seg = vals[i:i + step]
        out.append(round(max(abs(v) for v in seg) / 32768, 3))
    return out[:bins]


# ============================================================================ osciladores
def osc(kind: str, ph: float) -> float:
    p = ph % 1.0
    if kind == "square":
        return 0.6 if p < 0.5 else -0.6
    if kind == "saw":
        return 2 * p - 1
    if kind == "tri":
        return 4 * abs(p - 0.5) - 1
    return math.sin(TAU * p)


def env(i: int, n: int, a: float = 0.01, r: float = 0.2) -> float:
    t = i / RATE
    d = n / RATE
    if t < a:
        return t / a if a else 1.0
    if t > d - r:
        return max(0.0, (d - t) / r) if r else 1.0
    return 1.0


def tone(freq: float, dur: float, kind: str = "sine", vol: float = 0.5, glide: float = 0.0, a: float = 0.005, r: float = 0.08, vibrato: float = 0.0) -> List[float]:
    n = int(dur * RATE)
    out = []
    ph = 0.0
    for i in range(n):
        f = freq + glide * (i / max(1, n))
        if vibrato:
            f *= 1 + 0.01 * math.sin(TAU * vibrato * i / RATE)
        ph += f / RATE
        out.append(osc(kind, ph) * vol * env(i, n, a, r))
    return out


def mix(*tracks: List[float]) -> List[float]:
    n = max((len(t) for t in tracks), default=0)
    out = [0.0] * n
    for t in tracks:
        for i, v in enumerate(t):
            out[i] += v
    return out


def seq(*parts: List[float]) -> List[float]:
    out: List[float] = []
    for p in parts:
        out.extend(p)
    return out


def noise(dur: float, vol: float = 0.4, seed: int = 1, decay: float = 6.0) -> List[float]:
    rnd = random.Random(seed)
    n = int(dur * RATE)
    return [(rnd.random() * 2 - 1) * vol * math.exp(-decay * i / n) for i in range(n)]


def lowpass(x: List[float], k: float = 0.15) -> List[float]:
    out, y = [], 0.0
    for v in x:
        y += (v - y) * k
        out.append(y)
    return out


# ============================================================================ efeitos
SFX_NAMES = ("coin", "jump", "hit", "win", "lose", "powerup", "shoot", "select", "step", "door", "place", "explosion", "laser", "magic", "error", "pickup")


def sfx(name: str, seed: int = 1) -> bytes:
    name = name if name in SFX_NAMES else "select"
    if name == "coin":
        w = seq(tone(988, 0.07, "square", 0.35), tone(1319, 0.28, "square", 0.35, r=0.2))
    elif name == "pickup":
        w = seq(tone(660, 0.06, "tri", 0.45), tone(880, 0.12, "tri", 0.45))
    elif name == "jump":
        w = tone(300, 0.2, "square", 0.3, glide=420, r=0.1)
    elif name == "hit":
        w = mix(tone(180, 0.22, "saw", 0.4, glide=-120, r=0.15), noise(0.22, 0.4, seed, 9))
    elif name == "win":
        w = seq(*[tone(f, 0.14, "square", 0.3) for f in (523, 659, 784)], tone(1047, 0.5, "square", 0.3, r=0.3))
    elif name == "lose":
        w = seq(tone(330, 0.2, "saw", 0.35), tone(262, 0.2, "saw", 0.35), tone(196, 0.5, "saw", 0.35, glide=-60, r=0.4))
    elif name == "powerup":
        w = seq(*[tone(f, 0.07, "square", 0.3) for f in (392, 523, 659, 784, 1047)])
    elif name == "shoot":
        w = mix(tone(900, 0.14, "square", 0.25, glide=-650, r=0.05), noise(0.08, 0.15, seed, 20))
    elif name == "laser":
        w = tone(1400, 0.25, "saw", 0.25, glide=-1200, r=0.08, vibrato=30)
    elif name == "select":
        w = tone(720, 0.07, "sine", 0.4)
    elif name == "step":
        w = lowpass(noise(0.07, 0.5, seed, 25), 0.25)
    elif name == "door":
        w = mix(tone(160, 0.35, "saw", 0.25, glide=-60, r=0.25), lowpass(noise(0.35, 0.3, seed, 4), 0.1))
    elif name == "place":
        w = seq(tone(520, 0.06, "sine", 0.4), tone(780, 0.1, "sine", 0.4))
    elif name == "explosion":
        w = mix(lowpass(noise(0.9, 0.9, seed, 3.5), 0.08), tone(70, 0.7, "saw", 0.4, glide=-40, r=0.5))
    elif name == "magic":
        w = mix(*[tone(f, 0.5, "sine", 0.18, vibrato=7, r=0.4) for f in (880, 1108, 1318)])
    else:
        w = seq(tone(200, 0.12, "square", 0.3), tone(150, 0.2, "square", 0.3))
    return to_wav(w)


# ============================================================================ música em laço
MOODS = {
    "calm": {"scale": [0, 2, 4, 7, 9], "tempo": 84, "prog": [0, 5, 3, 4], "lead": "sine", "bass": "tri", "drums": 0},
    "joyful": {"scale": [0, 2, 4, 5, 7, 9, 11], "tempo": 128, "prog": [0, 4, 5, 3], "lead": "square", "bass": "tri", "drums": 1},
    "epic": {"scale": [0, 2, 3, 5, 7, 8, 10], "tempo": 104, "prog": [0, 5, 6, 4], "lead": "saw", "bass": "saw", "drums": 2},
    "tense": {"scale": [0, 1, 3, 5, 6, 8, 10], "tempo": 112, "prog": [0, 1, 0, 6], "lead": "saw", "bass": "square", "drums": 2},
    "mysterious": {"scale": [0, 2, 3, 5, 7, 8, 11], "tempo": 76, "prog": [0, 3, 5, 1], "lead": "sine", "bass": "tri", "drums": 0},
    "melancholic": {"scale": [0, 2, 3, 5, 7, 8, 10], "tempo": 70, "prog": [0, 5, 2, 6], "lead": "tri", "bass": "sine", "drums": 0},
}
THEME_MOOD = {"forest": "joyful", "desert": "mysterious", "snow": "calm", "night": "mysterious", "cave": "tense", "city": "tense", "space": "epic", "sea": "calm", "candy": "joyful", "lava": "epic", "retro": "joyful", "sunset": "melancholic"}


def music(mood: str = "calm", bars: int = 8, seed: int = 1, root: float = 220.0, tempo: int = 0) -> bytes:
    cfg = MOODS.get(mood) or MOODS["calm"]
    rnd = random.Random(seed)
    try:
        bars = max(1, min(64, int(bars)))   # sem limite, 500 compassos travavam a geração por minutos
    except (TypeError, ValueError, OverflowError):
        bars = 8
    bpm = tempo or cfg["tempo"]
    beat = 60.0 / bpm
    scale = cfg["scale"]
    total = int(bars * 4 * beat * RATE)
    out = [0.0] * total

    def add(w: List[float], at: float) -> None:
        i0 = int(at * RATE)
        for i, v in enumerate(w):
            if i0 + i < total:
                out[i0 + i] += v
    def note(deg: int, octave: int = 0) -> float:
        o, d = divmod(deg, len(scale))
        return root * 2 ** ((scale[d] + 12 * (o + octave)) / 12)
    t = 0.0
    for bar in range(bars):
        ch = cfg["prog"][bar % len(cfg["prog"])]
        add(tone(note(ch, -1), 4 * beat * 0.95, cfg["bass"], 0.26, a=0.01, r=0.3), t)       # baixo
        for k, off in enumerate((0, 2, 4)):                                                  # acorde suave
            add(tone(note(ch + off, 0), 4 * beat * 0.98, "sine", 0.07, a=0.12, r=0.5), t)
        for s in range(8):                                                                    # melodia em colcheias
            if rnd.random() < 0.72:
                deg = ch + rnd.choice((0, 2, 4, 4, 7, 1, 3))
                add(tone(note(deg, 1), beat * 0.45, cfg["lead"], 0.13, a=0.01, r=0.12), t + s * beat * 0.5)
        if cfg["drums"]:
            for b in range(4):
                add(mix(tone(110, 0.12, "sine", 0.45, glide=-60, r=0.1)), t + b * beat) if (b % 2 == 0 or cfg["drums"] == 2) else None
                add(lowpass(noise(0.05, 0.18, rnd.randrange(1 << 20), 30), 0.4), t + b * beat + beat * 0.5)
        t += 4 * beat
    fade = int(0.03 * RATE)   # laço sem estalo
    for i in range(min(fade, total)):
        k = i / fade
        out[i] *= k
        out[total - 1 - i] *= k
    peak = max((abs(v) for v in out), default=1) or 1
    return to_wav([v / peak * 0.8 for v in out])


def voice_babble(text: str, seed: int = 1) -> bytes:
    """Voz de reserva (balbucio): sílabas curtas ao ritmo do texto. Só para ter um áudio; a IA/TTS faz a voz de verdade."""
    rnd = random.Random(seed or sum(map(ord, text or "x")))
    syl = max(3, min(60, len(text or "") // 3))
    parts = []
    for _ in range(syl):
        f = rnd.choice((150, 170, 190, 210, 230)) * (1 + rnd.random() * 0.4)
        parts.append(tone(f, 0.09, "saw", 0.3, glide=rnd.choice((-30, 30)), r=0.05))
        parts.append([0.0] * int(RATE * rnd.choice((0.02, 0.03, 0.06))))
    return to_wav(lowpass(seq(*parts), 0.3))
