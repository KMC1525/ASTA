"""Exporta a linha do tempo do nó Editor para um MP4 usando o ffmpeg (que precisa estar instalado).

O Editor simula um editor de vídeo: trilhas de vídeo (imagens e vídeos em camadas), áudio (volume, fade, vários sons ao mesmo tempo)
e texto (legendas). Cada clipe tem início, duração, ponto de corte, opacidade, posição, escala e fades.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..providers.base import ProviderError
from .media import Ctl

Resolved = Dict[str, Any]  # {"path": Path, "kind": "image"|"video"|"audio", "duration": float}
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf", "C:/Windows/Fonts/arial.ttf",
]


def _even(v: float) -> int:
    return max(2, int(v) // 2 * 2)


def find_font() -> str:
    return next((f for f in FONT_CANDIDATES if Path(f).is_file()), "")


def _esc_path(p: str) -> str:
    """Caminho dentro de uma opção de filtro do ffmpeg (a barra e os dois-pontos precisam de escape)."""
    return p.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def has_audio(path: Path) -> bool:
    probe = shutil.which("ffprobe")
    if not probe:
        return False
    try:
        r = subprocess.run([probe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)], capture_output=True, timeout=30)
        return b"audio" in r.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def _run(cmd: List[str], ctl: Ctl, timeout: int = 3600) -> Tuple[int, str]:
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err)
        start = time.time()
        try:
            while proc.poll() is None:
                ctl.check()
                if time.time() - start > timeout:
                    proc.kill()
                    raise ProviderError("A exportação demorou demais e foi interrompida.")
                time.sleep(0.2)
        except BaseException:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            raise
        err.seek(0)
        return proc.returncode, err.read().decode("utf-8", "replace")[-1500:]


def render_timeline(tl: Dict[str, Any], width: int, height: int, fps: int, bg: str, resolve: Callable[[Dict[str, Any]], Optional[Resolved]], out_path: Path,
                    ctl: Optional[Ctl] = None) -> List[str]:
    """Renderiza `tl` em `out_path`. Devolve avisos (clipes ignorados, legendas sem fonte…). Levanta ProviderError se não der."""
    ctl = ctl or Ctl()
    ff = shutil.which("ffmpeg")
    if not ff:
        raise ProviderError("O Editor precisa do ffmpeg para exportar o vídeo. Instale-o (https://ffmpeg.org) e tente de novo.")
    W, H = _even(width), _even(height)
    tracks = {t["id"]: t for t in tl["tracks"]}
    order = {t["id"]: i for i, t in enumerate(tl["tracks"])}
    warnings: List[str] = []
    items: List[Tuple[Dict[str, Any], Dict[str, Any], Optional[Resolved]]] = []
    for c in sorted(tl["clips"], key=lambda c: (order.get(c["track"], 0), c["start"])):
        t = tracks.get(c["track"])
        if not t:
            continue
        if t["kind"] == "text":
            if c["text"].strip() and not t["hidden"]:
                items.append((t, c, None))
            continue
        r = resolve(c)
        if not r:
            warnings.append(f"Um clipe da trilha {t['name']} aponta para um arquivo que não existe mais — ignorado.")
            continue
        items.append((t, c, r))
    total = max([c["start"] + c["dur"] for _, c, _ in items] + [0.0])
    if total <= 0:
        raise ProviderError("A linha do tempo está vazia — adicione clipes ao Editor (ou ligue nós a ele e use \"Montar automaticamente\").")
    total = round(min(total, 3600.0), 3)

    def attempt(with_text: bool, normalize: bool) -> Tuple[int, str, List[str]]:
        warn: List[str] = []
        args: List[str] = [ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x{bg.lstrip('#') or '000000'}:s={W}x{H}:r={fps}:d={total}"]
        filters: List[str] = []
        label = "[0:v]"
        n_in = 1
        audio_labels: List[str] = []
        texts: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        tmpdir = tempfile.TemporaryDirectory()
        try:
            for t, c, r in items:
                if r is None:
                    if with_text and not t["hidden"]:
                        texts.append((t, c))
                    continue
                dur, start = c["dur"], c["start"]
                if r["kind"] in ("image", "video") and t["kind"] == "video" and not t["hidden"]:
                    k = n_in
                    n_in += 1
                    if r["kind"] == "image":
                        args += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(r["path"])]
                        chain = f"[{k}:v]setpts=PTS-STARTPTS"
                    else:
                        args += ["-ss", f"{c['in']:.3f}", "-t", f"{dur:.3f}", "-i", str(r["path"])]
                        chain = f"[{k}:v]setpts=PTS-STARTPTS,fps={fps},tpad=stop_mode=clone:stop_duration={dur:.3f},trim=duration={dur:.3f},setpts=PTS-STARTPTS"
                    sw, sh = _even(W * c["scale"]), _even(H * c["scale"])
                    if c["fit"] == "stretch":
                        chain += f",scale={sw}:{sh}"
                    elif c["fit"] == "cover":
                        chain += f",scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh}"
                    else:
                        chain += f",scale={sw}:{sh}:force_original_aspect_ratio=decrease"
                    chain += ",setsar=1,format=rgba"
                    if c["opacity"] < 0.999:
                        chain += f",colorchannelmixer=aa={c['opacity']}"
                    if c["fade_in"] > 0:
                        chain += f",fade=t=in:st=0:d={min(c['fade_in'], dur):.3f}:alpha=1"
                    if c["fade_out"] > 0:
                        fo = min(c["fade_out"], dur)
                        chain += f",fade=t=out:st={dur - fo:.3f}:d={fo:.3f}:alpha=1"
                    chain += f",setpts=PTS+{start:.3f}/TB[v{k}]"
                    filters.append(chain)
                    nxt = f"[o{k}]"
                    filters.append(f"{label}[v{k}]overlay=x='(W-w)/2+({c['x']}*W/2)':y='(H-h)/2+({c['y']}*H/2)':enable='between(t,{start:.3f},{start + dur:.3f})':eof_action=pass{nxt}")
                    label = nxt
                    if r["kind"] == "video" and not t["muted"] and c["volume"] > 0 and has_audio(r["path"]):
                        audio_labels.append(_audio_chain(filters, k, c, dur, start))
                elif r["kind"] in ("audio", "video") and t["kind"] == "audio" and not t["muted"] and c["volume"] > 0:
                    if r["kind"] == "video" and not has_audio(r["path"]):
                        warn.append("Um vídeo na trilha de áudio não tem som — ignorado.")
                        continue
                    k = n_in
                    n_in += 1
                    args += ["-ss", f"{c['in']:.3f}", "-t", f"{dur:.3f}", "-i", str(r["path"])]
                    audio_labels.append(_audio_chain(filters, k, c, dur, start))
                elif r["kind"] == "audio" and t["kind"] == "video" and not t["muted"] and c["volume"] > 0:  # áudio solto numa trilha de vídeo: toca normalmente
                    k = n_in
                    n_in += 1
                    args += ["-ss", f"{c['in']:.3f}", "-t", f"{dur:.3f}", "-i", str(r["path"])]
                    audio_labels.append(_audio_chain(filters, k, c, dur, start))
            font = find_font()
            for i, (t, c) in enumerate(texts):
                tf = Path(tmpdir.name) / f"t{i}.txt"
                cols = max(8, int(W / max(8, c["size"] * 0.58)))
                tf.write_text("\n".join(textwrap.fill(line, cols) for line in c["text"].splitlines() or [c["text"]]), encoding="utf-8")
                y = {"top": "h*0.07", "center": "(h-text_h)/2", "bottom": "h-text_h-h*0.07"}[c["pos"]]
                opts = [f"textfile='{_esc_path(str(tf))}'", f"fontsize={c['size']}", f"fontcolor={c['color']}", f"x=(w-text_w)/2+({c['x']}*w/2)", f"y={y}", "line_spacing=6",
                        f"enable='between(t,{c['start']:.3f},{c['start'] + c['dur']:.3f})'"]
                if font:
                    opts.insert(1, f"fontfile='{_esc_path(font)}'")
                if c["bg"]:
                    opts += ["box=1", f"boxcolor={c['bg']}@0.65", "boxborderw=14"]
                nxt = f"[x{i}]"
                filters.append(f"{label}drawtext={':'.join(opts)}{nxt}")
                label = nxt
            maps = ["-map", label]
            codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-r", str(fps)]
            if audio_labels:
                if len(audio_labels) == 1:
                    filters.append(f"{audio_labels[0]}apad=whole_dur={total:.3f}[aout]")
                else:
                    mix = f"amix=inputs={len(audio_labels)}:duration=longest:dropout_transition=0" + (":normalize=0" if normalize else "")
                    tail = "" if normalize else f",volume={len(audio_labels)}"
                    filters.append("".join(audio_labels) + f"{mix}{tail},apad=whole_dur={total:.3f}[aout]")
                maps += ["-map", "[aout]"]
                codec += ["-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2"]
            else:
                codec += ["-an"]
            if not filters:
                filters.append(f"{label}null[vfinal]")
                maps[1] = "[vfinal]"
            args += ["-filter_complex", ";".join(filters)] + maps + codec + ["-t", f"{total:.3f}", "-movflags", "+faststart", str(out_path)]
            code, err = _run(args, ctl)
            return code, err, warn
        finally:
            tmpdir.cleanup()

    has_text = any(r is None for _, _, r in items)
    code, err, extra = attempt(True, True)
    if code != 0 and "normalize" in err:
        code, err, extra = attempt(True, False)
    if code != 0 and has_text:  # sem fonte/drawtext no ffmpeg: exporta sem as legendas
        code2, err2, extra2 = attempt(False, "normalize" not in err)
        if code2 == 0:
            code, err, extra = 0, "", extra2 + ["As legendas foram ignoradas: este ffmpeg não conseguiu desenhar texto (falta o filtro drawtext ou uma fonte)."]
    if code != 0 or not out_path.exists():
        raise ProviderError("O ffmpeg não conseguiu montar o vídeo: " + (err.strip().splitlines()[-1] if err.strip() else f"código {code}"))
    return warnings + extra


def _audio_chain(filters: List[str], k: int, c: Dict[str, Any], dur: float, start: float) -> str:
    chain = f"[{k}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS"
    if abs(c["volume"] - 1) > 0.01:
        chain += f",volume={c['volume']}"
    if c["fade_in"] > 0:
        chain += f",afade=t=in:st=0:d={min(c['fade_in'], dur):.3f}"
    if c["fade_out"] > 0:
        fo = min(c["fade_out"], dur)
        chain += f",afade=t=out:st={dur - fo:.3f}:d={fo:.3f}"
    ms = int(round(start * 1000))
    if ms > 0:
        chain += f",adelay={ms}|{ms}"
    out = f"[a{k}]"
    filters.append(chain + out)
    return out
