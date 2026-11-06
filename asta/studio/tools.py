"""Ferramentas de mídia do Studio (ffprobe/ffmpeg): sonda de arquivos, Ken Burns, cenas, silêncios e picos de volume."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..providers.base import ProviderError


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _run(cmd: List[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def probe(path: Path) -> Dict[str, Any]:
    """{dur, w, h, audio, video} de um arquivo de mídia (zeros se o ffprobe não existir)."""
    out = {"dur": 0.0, "w": 0, "h": 0, "audio": False, "video": False}
    fp = shutil.which("ffprobe")
    if not fp:
        return out
    try:
        r = _run([fp, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,duration", "-of", "json", str(path)], 60)
        j = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return out
    try:
        out["dur"] = float((j.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        pass
    for s in j.get("streams") or []:
        if s.get("codec_type") == "audio":
            out["audio"] = True
        elif s.get("codec_type") == "video":
            out["video"] = True
            out["w"], out["h"] = int(s.get("width") or 0), int(s.get("height") or 0)
            if not out["dur"]:
                try:
                    out["dur"] = float(s.get("duration") or 0)
                except (TypeError, ValueError):
                    pass
    return out


def kenburns(png: bytes, seconds: float, size: Tuple[int, int], seed: int = 0, fps: int = 24) -> bytes:
    """Imagem → MP4 com zoom/pan suave (o movimento «leve» dos planos, sem modelo de vídeo)."""
    from ..canvas import procedural as proc

    return proc.video_from_image(png, max(1, int(round(seconds))), size, fps, seed)


def _stderr_of(cmd: List[str], timeout: int = 900) -> str:
    try:
        return _run(cmd, timeout).stderr.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return ""


def scene_changes(path: Path, threshold: float = 0.3, limit: int = 400) -> List[float]:
    """Instantes (s) de troca de cena de um vídeo — bons pontos de corte."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return []
    err = _stderr_of([ff, "-hide_banner", "-i", str(path), "-an", "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"])
    ts = [float(m.group(1)) for m in re.finditer(r"pts_time:([\d.]+)", err)]
    return ts[:limit]


def silences(path: Path, noise_db: int = -35, min_len: float = 0.6) -> List[Tuple[float, float]]:
    """Trechos de silêncio [(início, fim)] de um áudio/vídeo (para cortar «tempo morto»)."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return []
    err = _stderr_of([ff, "-hide_banner", "-i", str(path), "-vn", "-af", f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return list(zip(starts, ends))[:500]


def loud_moments(path: Path, window: float = 0.5, limit: int = 60) -> List[Tuple[float, float]]:
    """Picos de volume [(instante, nível dB)] ordenados do mais alto — num gameplay costumam ser os momentos de ação."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return []
    n = max(1, int(44100 * window))
    err_out = subprocess.run([ff, "-hide_banner", "-i", str(path), "-vn", "-af", f"aresample=44100,asetnsamples=n={n}:p=0,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
                              "-f", "null", "-"], capture_output=True, timeout=900)
    levels: List[Tuple[float, float]] = []
    t = None
    for line in err_out.stdout.decode("utf-8", "replace").splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
            continue
        m = re.search(r"RMS_level=(-?[\d.]+|-inf)", line)
        if m and t is not None:
            try:
                levels.append((t, float(m.group(1))))
            except ValueError:
                levels.append((t, -90.0))
    levels.sort(key=lambda x: -x[1])
    return levels[:limit]


def thumbnail(path: Path, t: float = 0.5, width: int = 240) -> Optional[bytes]:
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "t.jpg"
        r = _run([ff, "-y", "-loglevel", "error", "-ss", f"{max(0, t):.2f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={width}:-2", str(out)], 60)
        return out.read_bytes() if r.returncode == 0 and out.exists() else None


def need_ffmpeg(what: str = "O Studio") -> None:
    if not have_ffmpeg():
        raise ProviderError(f"{what} precisa do ffmpeg (e do ffprobe) para montar vídeos. Instale-o (https://ffmpeg.org) e tente de novo.")
