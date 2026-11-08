"""Análise de mídia do Studio (v0.17): volume, silêncios, momentos fortes, atividade visual, cortes de cena, andamento (BPM), batidas e forma de onda.

Antes, cada análise rodava um filtro do ffmpeg e lia o texto que ele imprimia. Agora o áudio é decodificado **uma vez** (mono, 8 kHz) e as contas rodam no núcleo Rust
(`asta.native`, com o equivalente em Python); o vídeo é lido uma vez em miniaturas cinza de 32×18 a 4 quadros por segundo. É bem mais rápido e gasta bem menos CPU, e dá
dados novos que a edição automática usa: atividade visual por trecho, andamento real da música e o ponto em que ela «explode» (o *drop*).
"""
from __future__ import annotations

import shutil
import sys
from array import array
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import native, perf

SR = 8000                 # taxa da análise de áudio (basta para volume e pulsação)
FRAME_W, FRAME_H, FRAME_FPS = 32, 18, 4
MAX_SECONDS = 6 * 3600


def _ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def decode_pcm(path: Path, sr: int = SR, limit_s: int = MAX_SECONDS) -> "array[int]":
    """Áudio de um arquivo (de áudio ou vídeo) em PCM de 16 bits mono. Vazio se não há áudio ou o ffmpeg falhou."""
    ff = _ffmpeg()
    out: "array[int]" = array("h")
    if not ff:
        return out
    try:
        r = perf.run([ff, "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-t", str(limit_s), "-f", "s16le", "-"], capture_output=True, timeout=3600)
    except Exception:  # noqa: BLE001 — ffmpeg ausente, tempo esgotado…
        return out
    data = r.stdout or b""
    out.frombytes(data[: len(data) // 2 * 2])
    if sys.byteorder == "big":  # pragma: no cover
        out.byteswap()
    return out


def audio_levels_of(pcm: "array[int]", window: float) -> "array[float]":
    return native.audio_levels(pcm, max(1, int(round(SR * window))))


def analyze_audio(path: Path, *, loud: bool = False, silence: bool = False, beats: bool = False, waveform: int = 0, window: float = 0.5, limit: int = 60) -> Dict[str, Any]:
    """Uma decodificação, várias análises. Chaves devolvidas (só as pedidas):
    `dur`, `loud` [(instante, dB)] do mais forte para o mais fraco com `window` s entre eles, `silences` [(início, fim)],
    `bpm`/`phase`/`confidence`/`beats`/`drop` (música) e `wave` (picos 0–1 por bloco)."""
    pcm = decode_pcm(path)
    res: Dict[str, Any] = {"dur": round(len(pcm) / SR, 3)}
    if not len(pcm):
        return res
    if loud:
        lv = audio_levels_of(pcm, window)
        res["loud"] = native.pick_peaks(lv, window, window, limit)
    if silence:
        res["silences"] = native.silence_ranges(audio_levels_of(pcm, 0.05), 0.05, -35.0, 0.6, 1000)
    if beats:
        res.update(_beats(pcm))
    if waveform:
        res["wave"] = list(native.waveform(pcm, int(waveform)))
    return res


def _beats(pcm: "array[int]") -> Dict[str, Any]:
    dur = len(pcm) / SR
    lv10 = audio_levels_of(pcm, 0.01)
    env = native.onset_env(lv10)
    tr = native.tempo(env, 0.01, 70.0, 200.0) if len(env) and max(env) >= 3.0 else None   # sem ataques claros (tom contínuo, ruído): não há pulso para seguir
    out: Dict[str, Any] = {"bpm": 0.0, "phase": 0.0, "confidence": 0.0, "beats": [], "drop": 0.0}
    if tr and tr["confidence"] >= 1.2:
        period = 60.0 / tr["bpm"]
        n = int((dur - tr["phase"]) / period) + 1
        out.update(bpm=round(tr["bpm"], 2), phase=round(tr["phase"], 4), confidence=round(tr["confidence"], 2), beats=[round(tr["phase"] + k * period, 3) for k in range(max(0, min(n, 20000)))])
    out["drop"] = drop_time(audio_levels_of(pcm, 0.5), 0.5)
    return out


def drop_time(levels: "array[float]", win_s: float, span_s: float = 4.0) -> float:
    """O instante em que a música «explode»: a primeira média móvel de `span_s` segundos a chegar perto (3 dB) do máximo — se a faixa tem uma introdução bem mais baixa. 0 se o volume é parelho."""
    n = len(levels)
    k = max(1, int(round(span_s / win_s)))
    if n < k * 3:
        return 0.0
    avgs = [sum(levels[i:i + k]) / k for i in range(0, n - k + 1)]
    top = max(avgs)
    first = next(i for i, a in enumerate(avgs) if a >= top - 3.0)
    quiet = sum(avgs[:max(1, first)]) / max(1, first) if first else top
    return round(first * win_s, 2) if first and top - quiet >= 4.0 else 0.0


# --------------------------------------------------------------------------- vídeo
def frame_stream(path: Path, fps: int = FRAME_FPS) -> Tuple["array[float]", float]:
    """Atividade visual (0–1) de um vídeo: diferença média entre quadros consecutivos de miniaturas cinza. Devolve (curva, passo em segundos)."""
    ff = _ffmpeg()
    if not ff:
        return array("d"), 1.0 / fps
    try:
        r = perf.run([ff, "-v", "error", "-nostdin", "-i", str(path), "-an", "-t", str(MAX_SECONDS), "-vf", f"fps={fps},scale={FRAME_W}:{FRAME_H}:flags=area,format=gray", "-f", "rawvideo", "-"],
                     capture_output=True, timeout=3600)
    except Exception:  # noqa: BLE001
        return array("d"), 1.0 / fps
    return native.frame_activity(r.stdout or b"", FRAME_W * FRAME_H), 1.0 / fps


def analyze_video(path: Path, threshold: float = 0.3) -> Dict[str, Any]:
    """`cuts` (instantes de troca de cena) e `activity` [(instante, 0–1)] — a atividade serve para escolher os trechos mais movimentados."""
    act, step = frame_stream(path)
    if len(act) < 2:
        return {"cuts": [], "activity": []}
    cuts = native.scene_cuts(act, step, 2.5, max(0.06, threshold * 0.5), 0.75, 400)
    return {"cuts": cuts, "activity": [(round(i * step, 3), round(v, 4)) for i, v in enumerate(act)], "step": step}


class ActivityIndex:
    """Atividade visual média de qualquer trecho em O(log n) (somas acumuladas sobre a curva [(instante, atividade)])."""

    def __init__(self, activity: List[Tuple[float, float]]):
        from itertools import accumulate

        self.t = [t for t, _ in activity]
        self.acc = [0.0] + list(accumulate(a for _, a in activity))

    def mean(self, s: float, e: float) -> float:
        from bisect import bisect_left

        i, j = bisect_left(self.t, s), bisect_left(self.t, e)
        return (self.acc[j] - self.acc[i]) / (j - i) if j > i else 0.0
