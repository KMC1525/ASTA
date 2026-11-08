"""Transcrição no Studio (v0.17): áudio ou vídeo de um projeto → texto (provedor de transcrição de Configuração → Mídia) → legendas com horário.

O provedor devolve só o texto; os horários vêm de `captions.align`, que distribui as frases pelos trechos em que há fala (medidos no próprio áudio).
Sem provedor de transcrição (Demo), vale o texto que a pessoa colar: `text` dispensa o provedor e só faz o alinhamento.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..canvas.media import Ctl, build_media, pick_provider
from ..providers import ProviderError
from . import analysis, captions, tools


def _audio_bytes(path: Any, kind: str, ctl: Ctl) -> Any:
    from ..canvas.engine import _audio_of_video

    if kind == "video":   # só o áudio (arquivos de vídeo costumam passar do limite dos serviços)
        got = _audio_of_video(path, ctl)
        if got:
            return got
    data = path.read_bytes()
    return data, "audio/mpeg" if path.suffix.lower() == ".mp3" else ("audio/wav" if path.suffix.lower() == ".wav" else "application/octet-stream"), path.name


def transcribe_asset(store: Any, pid: str, aid: str, language: str = "", given_text: str = "", offset: float = 0.0, ctl: Optional[Ctl] = None) -> Dict[str, Any]:
    """{text, cues:[{start,end,text}], duration}. `offset` soma segundos aos horários (onde o clipe está na timeline)."""
    ctl = ctl or Ctl()
    p = store.studio.get(pid)
    a = store.studio.asset(p, aid) if p else None
    path = store.studio.media_path(pid, a["file"]) if a else None
    if not a or not path or a["kind"] not in ("audio", "video"):
        raise ValueError("Escolha um áudio ou vídeo do projeto para transcrever.")
    if a["kind"] == "video" and not a["audio"]:
        raise ValueError("Este vídeo não tem áudio.")
    tools.need_ffmpeg("A transcrição")
    ctl.check()
    text = (given_text or "").strip()
    if not text:
        settings = store.get_settings()
        prov = build_media(settings, pick_provider(settings, "stt"), ctl, store.models_dir)
        data, mime, name = _audio_bytes(path, a["kind"], ctl)
        ctl.note("Transcrevendo…")
        try:
            text = str(prov.transcribe(data, name, mime, language=language)).strip()
        except ProviderError:
            raise
    if not text:
        raise ValueError("Nada foi transcrito (o áudio está em silêncio?).")
    ctl.check()
    info = analysis.analyze_audio(path, silence=True)
    dur = info.get("dur") or a.get("dur") or 0.0
    cues = captions.align(text, captions.speech_spans(info.get("silences", []), dur), offset)
    return {"text": text, "cues": cues, "duration": dur}
