"""Provedores de mídia do Canvas: geram imagens, vídeos, sons, vozes e transcrições.

Cada provedor declara o que sabe fazer (`caps`: "image", "video", "sound", "voice", "stt") e implementa só isso.
Há três famílias, todas sem dependências obrigatórias (urllib):

* **Offline** — "Demo" (geradores procedurais, para testar fluxos inteiros sem chave e sem internet).
* **APIs de empresas** — OpenAI e compatíveis (xAI, Together, servidores locais…), ElevenLabs, Google (Gemini/Veo),
  Stability AI, Replicate (catálogo enorme de modelos) e Hugging Face Inference.
* **Modelos locais** — Stable Diffusion WebUI (A1111/Forge) e modelos do Hugging Face rodando dentro do ASTA
  (`pip install "asta[media]"`: diffusers + transformers, carregados só quando você usa).

Os adaptadores de APIs externas seguem a documentação pública de cada serviço e são testados com servidores simulados;
o campo "extra" (JSON) de cada nó permite ajustar qualquer parâmetro específico de um modelo.
"""
from __future__ import annotations

import base64
import gc
import io
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .. import native as _native
from .. import perf
from .. import perf as _perf
from ..util import hardware_info
from ..providers import http
from ..providers.base import ProviderError
from . import procedural as proc

CAP_LABELS = {"image": "imagens", "video": "vídeos", "sound": "sons e músicas", "voice": "vozes", "stt": "transcrição de áudio"}
Ref = Tuple[bytes, str]  # (bytes, mime) de uma imagem de referência
RETRY_DELAY = 2.0  # espera antes de repetir uma chamada recusada por excesso de uso (os testes reduzem)

MIME_EXT = {
    "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp", "image/gif": "gif",
    "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav", "audio/ogg": "ogg", "audio/opus": "ogg",
    "audio/flac": "flac", "audio/x-flac": "flac", "audio/mp4": "m4a", "audio/aac": "aac", "audio/webm": "weba",
    "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov", "video/x-msvideo": "avi",
}
DEFAULT_MIME = {"image": "image/png", "audio": "audio/mpeg", "video": "video/mp4"}


# --------------------------------------------------------------------------- utilidades


def sniff_mime(data: bytes, fallback: str = "") -> str:
    """Descobre o tipo da mídia pelos primeiros bytes (alguns provedores devolvem Content-Type genérico)."""
    h = data[:16]
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if h[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if h[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if h[:4] == b"GIF8":
        return "image/gif"
    if h[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if h[:4] == b"RIFF" and data[8:12] == b"AVI ":
        return "video/x-msvideo"
    if h[:4] == b"OggS":
        return "audio/ogg"
    if h[:4] == b"fLaC":
        return "audio/flac"
    if h[:3] == b"ID3" or (len(h) > 1 and h[0] == 0xFF and (h[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if data[4:8] == b"ftyp":
        return "audio/mp4" if data[8:12] in (b"M4A ", b"M4B ") else "video/mp4"
    if h[:4] == b"\x1aE\xdf\xa3":
        return "video/webm"
    return fallback


class Media:
    """Um arquivo gerado por um provedor."""

    def __init__(self, data: bytes, mime: str = "", meta: Optional[Dict[str, Any]] = None):
        self.data = data
        self.mime = (mime or sniff_mime(data) or "application/octet-stream").split(";")[0].strip().lower()
        self.meta = meta or {}

    @property
    def kind(self) -> str:
        return self.mime.split("/")[0] if self.mime.split("/")[0] in ("image", "audio", "video") else "file"

    @property
    def ext(self) -> str:
        return MIME_EXT.get(self.mime, "bin")


def expect_media(data: bytes, mime: str, kind: str, who: str = "O provedor") -> Media:
    """Garante que a resposta é mesmo uma mídia do tipo esperado — e não um JSON/HTML de erro com status 200."""
    real = sniff_mime(data) or (mime or "").split(";")[0].strip().lower()
    if not data or real.endswith("json") or real.startswith("text/") or data[:1] in (b"{", b"<", b"["):
        detail = ""
        try:
            obj = json.loads(data.decode("utf-8", "replace"))
            err = obj.get("error", obj.get("detail", obj)) if isinstance(obj, dict) else obj
            detail = err.get("message", json.dumps(err, ensure_ascii=False)) if isinstance(err, dict) else str(err)
        except (ValueError, AttributeError):
            detail = data[:200].decode("utf-8", "replace")
        raise ProviderError(f"{who} não devolveu {'uma ' + kind if kind != 'any' else 'a mídia'}: {detail[:300] or 'resposta vazia'}")
    if kind != "any" and not real.startswith(kind + "/"):
        if real in ("application/octet-stream", "binary/octet-stream", ""):
            real = DEFAULT_MIME.get(kind, real)
        else:
            raise ProviderError(f"{who} devolveu um arquivo inesperado ({real}) em vez de {kind}.")
    return Media(data, real)


def data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def parse_wh(size: str) -> Tuple[int, int]:
    m = re.match(r"^(\d{2,5})x(\d{2,5})$", size or "")
    return (int(m.group(1)), int(m.group(2))) if m else (1024, 1024)


_ASPECTS = {"1:1": 1.0, "16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3, "3:4": 3 / 4, "3:2": 3 / 2, "2:3": 2 / 3}


def aspect_of(size: str) -> str:
    """Proporção (como "16:9") mais próxima de um tamanho "WxH"."""
    w, h = parse_wh(size)
    return min(_ASPECTS, key=lambda k: abs(_ASPECTS[k] - w / h))


def size_of_aspect(aspect: str, long_side: int = 1280) -> Tuple[int, int]:
    try:
        a, b = [float(x) for x in aspect.split(":")]
    except (ValueError, AttributeError):
        a, b = 16.0, 9.0
    w, h = (long_side, long_side * b / a) if a >= b else (long_side * a / b, long_side)
    return int(w) // 2 * 2, int(h) // 2 * 2


def _nearest(value: float, options: Sequence[float]) -> float:
    return min(options, key=lambda o: abs(o - value))


class Ctl:
    """Ligação do provedor com o job: cancelamento e mensagens de progresso."""

    def __init__(self, check: Optional[Callable[[], None]] = None, note: Optional[Callable[[str], None]] = None):
        self._check, self._note = check, note

    def check(self) -> None:
        if self._check:
            self._check()

    def note(self, msg: str) -> None:
        if self._note:
            self._note(msg)

    def sleep(self, secs: float) -> None:
        end = time.time() + secs
        while time.time() < end:
            self.check()
            time.sleep(min(0.4, max(0.0, end - time.time())))


def _retry(ctl: Ctl, fn: Callable[[], Any], tries: int = 3, statuses: Tuple[int, ...] = (429, 502, 503, 504)) -> Any:
    """Repete chamadas recusadas por excesso de uso/indisponibilidade temporária (nunca erros de conteúdo ou de chave)."""
    delay = RETRY_DELAY
    for i in range(tries):
        ctl.check()
        try:
            return fn()
        except ProviderError as exc:
            if exc.status not in statuses or i == tries - 1:
                raise
            ctl.note(f"Provedor ocupado ({exc.status}); tentando de novo em {delay:.0f}s…")
            ctl.sleep(delay)
            delay *= 2.5
    return None


def _auth(key: str, header: str = "Authorization", scheme: str = "Bearer ") -> Dict[str, str]:
    return {header: f"{scheme}{key}"} if key else {}


# --------------------------------------------------------------------------- base


class MediaProvider:
    id = "media"
    label = "Provedor"
    caps: Tuple[str, ...] = ()
    supports_refs = False  # aceita imagens de referência (edição/estilo) no nó Imagem

    def __init__(self, cfg: Dict[str, Any], ctl: Optional[Ctl] = None):
        self.cfg = cfg
        self.id = cfg.get("id", self.id)
        self.label = cfg.get("label", self.label)
        self.base = (cfg.get("base_url") or "").rstrip("/")
        self.key = (cfg.get("api_key") or "").strip()
        self.models: Dict[str, str] = dict(cfg.get("models") or {})
        self.ctl = ctl or Ctl()

    # utilidades
    def model_for(self, cap: str, override: str = "") -> str:
        return (override or self.models.get(cap) or "").strip()

    def poll(self, default: float) -> float:
        """Intervalo (s) entre consultas de trabalhos assíncronos (vídeo etc.)."""
        return float(self.cfg.get("poll_seconds") or default)

    def need_key(self) -> None:
        if self.cfg.get("needs_key") and not self.key:
            raise ProviderError(f"{self.label}: informe a chave de API em Configuração → Mídia.")

    def need_url(self) -> None:
        if not self.base:
            raise ProviderError(f"{self.label}: informe o endereço do servidor em Configuração → Mídia.")

    def _no(self, cap: str) -> ProviderError:
        return ProviderError(f"{self.label} não oferece geração de {CAP_LABELS.get(cap, cap)}. Escolha outro provedor no nó (ou em Configuração → Mídia).")

    # API pública (as subclasses implementam o que suportam)
    def image(self, prompt: str, *, size: str = "1024x1024", count: int = 1, seed: int = 0, negative: str = "", refs: Sequence[Ref] = (),
              model: str = "", extra: Optional[Dict[str, Any]] = None) -> List[Media]:
        raise self._no("image")

    def video(self, prompt: str, *, duration: int = 5, aspect: str = "16:9", image: Optional[Ref] = None, model: str = "",
              extra: Optional[Dict[str, Any]] = None, seed: int = 0) -> Media:
        raise self._no("video")

    def sound(self, prompt: str, *, kind: str = "sfx", duration: int = 5, model: str = "", extra: Optional[Dict[str, Any]] = None, seed: int = 0) -> Media:
        raise self._no("sound")

    def voice(self, text: str, *, voice: str = "", speed: float = 1.0, model: str = "", extra: Optional[Dict[str, Any]] = None, instructions: str = "") -> Media:
        raise self._no("voice")

    def transcribe(self, data: bytes, filename: str, mime: str, *, language: str = "", model: str = "") -> str:
        raise self._no("stt")

    def list_models(self, cap: str) -> List[str]:
        return []

    def test(self) -> str:
        return "ok"


# --------------------------------------------------------------------------- Demo (offline)


class DemoMedia(MediaProvider):
    id, label = "demo", "Demo (offline)"
    caps = ("image", "video", "sound", "voice")
    supports_refs = True

    def image(self, prompt, *, size="1024x1024", count=1, seed=0, negative="", refs=(), model="", extra=None):
        w, h = parse_wh(size)
        mix = proc.seed_of(*[len(r[0]) for r in refs]) if refs else 0  # com referência, o resultado muda (não edita de verdade)
        return [Media(proc.image(prompt, f"{w}x{h}", seed + i + mix), "image/png", {"note": "demo"}) for i in range(max(1, count))]

    def video(self, prompt, *, duration=5, aspect="16:9", image=None, model="", extra=None, seed=0):
        w, h = size_of_aspect(aspect, 640)
        png = image[0] if image and sniff_mime(image[0]) == "image/png" else proc.image(prompt, f"{w}x{h}", seed)
        return Media(proc.video_from_image(png, duration, (w, h), 24, seed), "video/mp4", {"note": "demo"})

    def sound(self, prompt, *, kind="sfx", duration=5, model="", extra=None, seed=0):
        data = proc.music(prompt, float(duration), seed) if kind == "music" else proc.sound_fx(prompt, float(duration), seed)
        return Media(data, "audio/wav", {"note": "demo"})

    def voice(self, text, *, voice="", speed=1.0, model="", extra=None, instructions=""):
        return Media(proc.babble(text, speed, proc.seed_of(voice)), "audio/wav", {"note": "demo"})

    def transcribe(self, data, filename, mime, *, language="", model=""):
        raise ProviderError("O provedor Demo não transcreve áudio. Escolha um provedor de transcrição (OpenAI, Groq, Whisper local…) em Configuração → Mídia.")

    def test(self) -> str:
        return "Demo pronto" + ("" if proc.ffmpeg_path() else " (vídeo precisa do ffmpeg)")


# --------------------------------------------------------------------------- OpenAI e compatíveis


class OpenAIMedia(MediaProvider):
    """OpenAI e qualquer servidor com a mesma API (xAI, Together, LocalAI, Kokoro-FastAPI, faster-whisper-server…)."""

    id, label = "openai", "OpenAI"
    caps = ("image", "video", "voice", "stt")
    supports_refs = True

    def _h(self) -> Dict[str, str]:
        self.need_key()
        self.need_url()
        return _auth(self.key)

    @staticmethod
    def _size(model: str, size: str) -> str:
        w, h = parse_wh(size)
        if model.startswith("dall-e-3"):
            return "1024x1024" if w == h else ("1792x1024" if w > h else "1024x1792")
        if model.startswith("dall-e-2"):
            return "512x512" if max(w, h) <= 512 else "1024x1024"
        if model.startswith("gpt-image"):
            return "1024x1024" if w == h else ("1536x1024" if w > h else "1024x1536")
        return f"{w}x{h}"

    def _images_from(self, res: Any) -> List[Media]:
        out: List[Media] = []
        for item in (res.get("data") if isinstance(res, dict) else None) or []:
            if item.get("b64_json"):
                out.append(expect_media(base64.b64decode(item["b64_json"]), "", "image", self.label))
            elif item.get("url"):
                data, mime = http.get_bytes(item["url"])
                out.append(expect_media(data, mime, "image", self.label))
        if not out:
            raise ProviderError(f"{self.label} não devolveu nenhuma imagem.")
        return out

    def image(self, prompt, *, size="1024x1024", count=1, seed=0, negative="", refs=(), model="", extra=None):
        h = self._h()
        model = self.model_for("image", model)
        extra = extra or {}
        prompt = prompt + (f"\n\nEvite: {negative}" if negative else "")
        calls = count if model.startswith("dall-e-3") else 1  # dall-e-3 só aceita n=1
        n = 1 if calls > 1 else count
        out: List[Media] = []
        for _ in range(calls):
            if refs:
                fields: Dict[str, Any] = {"prompt": prompt, "n": str(n)}
                if model:
                    fields["model"] = model
                if not self.cfg.get("no_size"):
                    fields["size"] = self._size(model, size)
                fields.update({k: v for k, v in extra.items() if isinstance(v, (str, int, float))})
                field = "image[]" if model.startswith("gpt-image") or not model else "image"
                files = [(field, f"ref{i}.{MIME_EXT.get(m, 'png')}", d, m) for i, (d, m) in enumerate(refs[:8])]
                res = _retry(self.ctl, lambda: http.post_multipart_files(self.base + "/images/edits", fields, files, h, timeout=400))
            else:
                body: Dict[str, Any] = {"prompt": prompt, "n": n}
                if model:
                    body["model"] = model
                if not self.cfg.get("no_size"):
                    body["size"] = self._size(model, size)
                if not model.startswith("gpt-image"):
                    body["response_format"] = "b64_json"
                body.update(extra)
                res = _retry(self.ctl, lambda: http.post_json(self.base + "/images/generations", body, h, timeout=400))
            out += self._images_from(res)
        return out[:max(1, count)]

    def voice(self, text, *, voice="", speed=1.0, model="", extra=None, instructions=""):
        h = self._h()
        model = self.model_for("voice", model) or "tts-1"
        body: Dict[str, Any] = {"model": model, "input": text[:4096], "voice": voice or self.cfg.get("voice") or "alloy", "response_format": "mp3"}
        if abs(speed - 1) > 0.01:
            body["speed"] = max(0.25, min(4.0, speed))
        if instructions and model.startswith("gpt-4o"):
            body["instructions"] = instructions[:1000]
        body.update(extra or {})
        data, mime = _retry(self.ctl, lambda: http.post_bytes(self.base + "/audio/speech", body, {**h, "Accept": "audio/*"}, timeout=240))
        return expect_media(data, mime, "audio", self.label)

    def transcribe(self, data, filename, mime, *, language="", model=""):
        h = self._h()
        fields = {"model": self.model_for("stt", model) or "whisper-1", "response_format": "json"}
        if language and language != "auto":
            fields["language"] = language.split("-")[0]
        out = _retry(self.ctl, lambda: http.post_multipart(self.base + "/audio/transcriptions", fields, "file", filename or "audio.mp3", data, mime or "audio/mpeg", h, timeout=600))
        return str(out.get("text", "") if isinstance(out, dict) else out).strip()

    def video(self, prompt, *, duration=5, aspect="16:9", image=None, model="", extra=None, seed=0):
        """Sora (API de vídeos da OpenAI): cria o trabalho, acompanha até concluir e baixa o MP4."""
        h = self._h()
        model = self.model_for("video", model) or "sora-2"
        w, hh = size_of_aspect(aspect, 1280)
        landscape = w >= hh
        fields: Dict[str, Any] = {"model": model, "prompt": prompt, "seconds": str(int(_nearest(duration, (4, 8, 12)))), "size": "1280x720" if landscape else "720x1280"}
        fields.update({k: v for k, v in (extra or {}).items() if isinstance(v, (str, int, float))})
        files = [("input_reference", "start.png", image[0], image[1])] if image else []
        job = _retry(self.ctl, lambda: http.post_multipart_files(self.base + "/videos", fields, files, h, timeout=120))
        vid = job.get("id") if isinstance(job, dict) else None
        if not vid:
            raise ProviderError(f"{self.label}: resposta inesperada ao criar o vídeo.")
        deadline = time.time() + 1500
        while True:
            self.ctl.check()
            st = http.get_json(f"{self.base}/videos/{vid}", h, timeout=60)
            status = st.get("status")
            if status == "completed":
                break
            if status in ("failed", "cancelled", "canceled"):
                err = st.get("error") or {}
                raise ProviderError(f"{self.label}: o vídeo falhou — {err.get('message') if isinstance(err, dict) else err or status}")
            if time.time() > deadline:
                raise ProviderError(f"{self.label}: o vídeo demorou demais (mais de 25 minutos).")
            self.ctl.note(f"Gerando vídeo… {int(st.get('progress') or 0)}%")
            self.ctl.sleep(self.poll(5))
        data, mime = http.get_bytes(f"{self.base}/videos/{vid}/content", {**h, "Accept": "video/*"}, timeout=900)
        return expect_media(data, mime, "video", self.label)

    def list_models(self, cap: str) -> List[str]:
        res = http.get_json(self.base + "/models", self._h(), timeout=30)
        ids = sorted({m.get("id", "") for m in (res.get("data") if isinstance(res, dict) else res) or [] if isinstance(m, dict)})
        pat = {"image": r"image|dall-e|flux|stable|sdxl", "voice": r"tts|speech|kokoro|piper|voice", "stt": r"whisper|transcribe|stt", "video": r"sora|video"}.get(cap, r".")
        return [i for i in ids if re.search(pat, i, re.I)] or ids[:50]

    def test(self) -> str:
        res = http.get_json(self.base + "/models", self._h(), timeout=30)
        n = len((res.get("data") if isinstance(res, dict) else res) or [])
        return f"conectado ({n} modelos)"


# --------------------------------------------------------------------------- ElevenLabs


class ElevenLabsMedia(MediaProvider):
    id, label = "elevenlabs", "ElevenLabs"
    caps = ("voice", "sound", "stt")
    DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"

    def __init__(self, cfg, ctl=None):
        super().__init__(cfg, ctl)
        self._voices: Optional[List[Dict[str, Any]]] = None

    def _h(self) -> Dict[str, str]:
        self.need_key()
        return {"xi-api-key": self.key}

    def _voice_list(self) -> List[Dict[str, Any]]:
        if self._voices is None:
            res = http.get_json(self.base + "/voices", self._h(), timeout=30)
            self._voices = [v for v in (res.get("voices") if isinstance(res, dict) else []) or [] if isinstance(v, dict)]
        return self._voices

    def _voice_id(self, voice: str) -> str:
        voice = (voice or "").strip()
        if not voice:
            return self.DEFAULT_VOICE
        if re.match(r"^[A-Za-z0-9]{18,24}$", voice):
            return voice
        for v in self._voice_list():
            if (v.get("name") or "").strip().lower() == voice.lower():
                return v["voice_id"]
        names = ", ".join(v.get("name", "") for v in self._voice_list()[:8])
        raise ProviderError(f"ElevenLabs: voz \"{voice}\" não encontrada. Algumas disponíveis: {names or '(nenhuma)'}.")

    def voice(self, text, *, voice="", speed=1.0, model="", extra=None, instructions=""):
        h = self._h()
        body: Dict[str, Any] = {"text": text[:5000], "model_id": self.model_for("voice", model) or "eleven_multilingual_v2",
                                "voice_settings": {"speed": max(0.7, min(1.2, speed))}}
        body.update(extra or {})
        url = f"{self.base}/text-to-speech/{self._voice_id(voice)}?output_format=mp3_44100_128"
        data, mime = _retry(self.ctl, lambda: http.post_bytes(url, body, {**h, "Accept": "audio/mpeg"}, timeout=240))
        return expect_media(data, mime, "audio", self.label)

    def sound(self, prompt, *, kind="sfx", duration=5, model="", extra=None, seed=0):
        h = self._h()
        if kind == "music":  # API de música (recente): enviada tal como documentada; ajuste com o campo "extra" se mudar
            body: Dict[str, Any] = {"prompt": prompt, "music_length_ms": int(max(10, min(300, duration)) * 1000)}
            if model:
                body["model_id"] = model
            body.update(extra or {})
            url = f"{self.base}/music?output_format=mp3_44100_128"
        else:
            body = {"text": prompt, "duration_seconds": round(max(0.5, min(22.0, float(duration))), 1), "prompt_influence": 0.4}
            if model:
                body["model_id"] = model
            body.update(extra or {})
            url = f"{self.base}/sound-generation?output_format=mp3_44100_128"
        data, mime = _retry(self.ctl, lambda: http.post_bytes(url, body, {**h, "Accept": "audio/mpeg"}, timeout=400))
        return expect_media(data, mime, "audio", self.label)

    def transcribe(self, data, filename, mime, *, language="", model=""):
        h = self._h()
        fields = {"model_id": self.model_for("stt", model) or "scribe_v1"}
        if language and language != "auto":
            fields["language_code"] = language.split("-")[0]
        out = _retry(self.ctl, lambda: http.post_multipart_files(self.base + "/speech-to-text", fields, [("file", filename or "audio.mp3", data, mime or "audio/mpeg")], h, timeout=900))
        return str(out.get("text", "") if isinstance(out, dict) else out).strip()

    def list_models(self, cap: str) -> List[str]:
        return [f"{v.get('name', '')}" for v in self._voice_list()] if cap == "voice" else []

    def test(self) -> str:
        n = len(self._voice_list())
        return f"conectado ({n} vozes)"


# --------------------------------------------------------------------------- Google (Gemini / Veo)


class GoogleMedia(MediaProvider):
    id, label = "google", "Google (Gemini / Veo)"
    caps = ("image", "video")
    supports_refs = True

    def _h(self) -> Dict[str, str]:
        self.need_key()
        return {"x-goog-api-key": self.key}

    def image(self, prompt, *, size="1024x1024", count=1, seed=0, negative="", refs=(), model="", extra=None):
        h = self._h()
        model = self.model_for("image", model) or "gemini-2.5-flash-image"
        prompt = prompt + (f"\n\nEvite: {negative}" if negative else "")
        parts: List[Dict[str, Any]] = [{"text": prompt}] + [{"inline_data": {"mime_type": m, "data": base64.b64encode(d).decode("ascii")}} for d, m in refs[:6]]
        out: List[Media] = []
        for _ in range(max(1, count)):
            gen: Dict[str, Any] = {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"aspectRatio": aspect_of(size)}}
            gen.update((extra or {}).get("generationConfig", {}) if isinstance((extra or {}).get("generationConfig"), dict) else {})
            body = {"contents": [{"parts": parts}], "generationConfig": gen}
            url = f"{self.base}/models/{model}:generateContent"
            try:
                res = _retry(self.ctl, lambda: http.post_json(url, body, h, timeout=300))
            except ProviderError as exc:
                if exc.status == 400 and "imageConfig" in str(exc):  # modelo sem controle de proporção
                    gen.pop("imageConfig", None)
                    res = _retry(self.ctl, lambda: http.post_json(url, body, h, timeout=300))
                else:
                    raise
            out += self._images_from(res)
        return out[:max(1, count)]

    def _images_from(self, res: Any) -> List[Media]:
        imgs: List[Media] = []
        texts: List[str] = []
        for cand in (res.get("candidates") if isinstance(res, dict) else None) or []:
            for part in (cand.get("content") or {}).get("parts", []):
                inl = part.get("inlineData") or part.get("inline_data")
                if inl and inl.get("data"):
                    imgs.append(expect_media(base64.b64decode(inl["data"]), inl.get("mimeType") or inl.get("mime_type") or "", "image", self.label))
                elif part.get("text"):
                    texts.append(part["text"])
        if not imgs:
            block = ((res or {}).get("promptFeedback") or {}).get("blockReason") if isinstance(res, dict) else ""
            raise ProviderError(f"{self.label}: nenhuma imagem devolvida" + (f" (bloqueado: {block})" if block else f" — o modelo respondeu: {' '.join(texts)[:200]}" if texts else "."))
        return imgs

    def video(self, prompt, *, duration=5, aspect="16:9", image=None, model="", extra=None, seed=0):
        h = self._h()
        model = self.model_for("video", model) or "veo-3.0-fast-generate-001"
        inst: Dict[str, Any] = {"prompt": prompt}
        if image:
            inst["image"] = {"bytesBase64Encoded": base64.b64encode(image[0]).decode("ascii"), "mimeType": image[1]}
        params: Dict[str, Any] = {"aspectRatio": "9:16" if aspect in ("9:16", "3:4") else "16:9", "durationSeconds": int(_nearest(duration, (4, 6, 8)))}
        params.update(extra or {})
        op = _retry(self.ctl, lambda: http.post_json(f"{self.base}/models/{model}:predictLongRunning", {"instances": [inst], "parameters": params}, h, timeout=120))
        name = op.get("name") if isinstance(op, dict) else None
        if not name:
            raise ProviderError(f"{self.label}: resposta inesperada ao criar o vídeo.")
        deadline = time.time() + 1500
        while True:
            self.ctl.check()
            st = http.get_json(f"{self.base}/{name}", h, timeout=60)
            if st.get("done"):
                break
            if time.time() > deadline:
                raise ProviderError(f"{self.label}: o vídeo demorou demais (mais de 25 minutos).")
            self.ctl.note("Gerando vídeo…")
            self.ctl.sleep(self.poll(8))
        if st.get("error"):
            raise ProviderError(f"{self.label}: {(st['error'] or {}).get('message', st['error'])}")
        resp = st.get("response") or {}
        samples = (resp.get("generateVideoResponse") or resp).get("generatedSamples") or resp.get("videos") or []
        uri = ((samples[0].get("video") or {}).get("uri") if samples and isinstance(samples[0], dict) else "") or ""
        if not uri:
            reasons = (resp.get("generateVideoResponse") or {}).get("raiMediaFilteredReasons")
            raise ProviderError(f"{self.label}: nenhum vídeo devolvido" + (f" (filtrado: {reasons[0]})" if reasons else "."))
        data, mime = http.get_bytes(uri, {**h, "Accept": "video/*"}, timeout=900)
        return expect_media(data, mime, "video", self.label)

    def list_models(self, cap: str) -> List[str]:
        res = http.get_json(self.base + "/models?pageSize=200", self._h(), timeout=30)
        names = [m.get("name", "").replace("models/", "") for m in res.get("models", []) if isinstance(m, dict)]
        pat = {"image": r"image|imagen", "video": r"veo"}.get(cap, r".")
        return [n for n in names if re.search(pat, n, re.I)]

    def test(self) -> str:
        res = http.get_json(self.base + "/models?pageSize=5", self._h(), timeout=30)
        return f"conectado ({len(res.get('models', []))}+ modelos)"


class OpenRouterMedia(MediaProvider):
    """OpenRouter: imagens (POST /images), vídeos (POST /videos, assíncrono: envia, consulta e baixa) e voz (POST /audio/speech, formato da OpenAI) com a MESMA chave do OpenRouter.
    Serve ao Studio e ao Canvas. Os modelos disponíveis mudam sempre: «Carregar modelos» lista os atuais."""

    id, label = "openrouter", "OpenRouter"
    caps = ("image", "video", "voice")
    supports_refs = False

    def _h(self) -> Dict[str, str]:
        self.need_key()
        return {"Authorization": f"Bearer {self.key}", "X-Title": "ASTA"}

    def image(self, prompt, *, size="1024x1024", count=1, seed=0, negative="", refs=(), model="", extra=None):
        h = self._h()
        model = self.model_for("image", model) or "google/gemini-2.5-flash-image"
        body: Dict[str, Any] = {"model": model, "prompt": prompt + (f"\n\nEvite: {negative}" if negative else ""), "aspect_ratio": aspect_of(size)}
        body.update(extra or {})
        out: List[Media] = []
        for _ in range(max(1, count)):
            res = _retry(self.ctl, lambda: http.post_json(f"{self.base}/images", body, h, timeout=300))
            items = (res.get("data") if isinstance(res, dict) else None) or []
            got = 0
            for it in items:
                b64 = it.get("b64_json") if isinstance(it, dict) else None
                if b64:
                    out.append(expect_media(base64.b64decode(b64), (it.get("media_type") or "image/png"), "image", self.label))
                    got += 1
                elif isinstance(it, dict) and it.get("url"):
                    data, mime = http.get_bytes(it["url"], h, timeout=300)
                    out.append(expect_media(data, mime, "image", self.label))
                    got += 1
            if not got:
                err = res.get("error") if isinstance(res, dict) else None
                raise ProviderError(f"{self.label}: nenhuma imagem devolvida" + (f" ({err.get('message', err) if isinstance(err, dict) else err})." if err else "."))
            if len(out) >= count:
                break
        return out[:max(1, count)]

    def video(self, prompt, *, duration=5, aspect="16:9", image=None, model="", extra=None, seed=0):
        h = self._h()
        model = self.model_for("video", model) or "google/veo-3.1"
        body: Dict[str, Any] = {"model": model, "prompt": prompt, "duration": int(duration), "aspect_ratio": aspect}
        body.update(extra or {})
        if image:
            body["frame_images"] = [{"type": "image_url", "image_url": {"url": f"data:{image[1]};base64,{base64.b64encode(image[0]).decode('ascii')}"}, "frame_type": "first_frame"}]
        try:
            job = _retry(self.ctl, lambda: http.post_json(f"{self.base}/videos", body, h, timeout=120))
        except ProviderError as exc:
            if image and exc.status in (400, 422):  # o modelo não aceita imagem inicial: segue só com o texto
                body.pop("frame_images", None)
                self.ctl.note("Este modelo de vídeo não aceitou a imagem inicial: gerando só pelo texto.")
                job = _retry(self.ctl, lambda: http.post_json(f"{self.base}/videos", body, h, timeout=120))
            else:
                raise
        vid, poll = (job.get("id") if isinstance(job, dict) else None), (job.get("polling_url") if isinstance(job, dict) else None)
        if not vid and not poll:
            raise ProviderError(f"{self.label}: resposta inesperada ao criar o vídeo.")
        poll = poll or f"{self.base}/videos/{vid}"
        deadline = time.time() + 1800
        while True:
            self.ctl.check()
            st = http.get_json(poll, h, timeout=60)
            status = str((st or {}).get("status", "")).lower()
            if status == "completed":
                break
            if status in ("failed", "cancelled", "expired"):
                raise ProviderError(f"{self.label}: vídeo {status}" + (f" — {st.get('error')}" if st.get("error") else "."))
            if time.time() > deadline:
                raise ProviderError(f"{self.label}: o vídeo demorou demais (mais de 30 minutos).")
            self.ctl.note("Gerando vídeo…")
            self.ctl.sleep(self.poll(10))
        vid = vid or st.get("id")
        data, mime = http.get_bytes(f"{self.base}/videos/{vid}/content?index=0", {**h, "Accept": "video/*"}, timeout=900)
        return expect_media(data, mime, "video", self.label)

    def voice(self, text, *, voice="", speed=1.0, model="", extra=None, instructions=""):
        h = self._h()
        model = self.model_for("voice", model) or "openai/gpt-4o-mini-tts"
        body: Dict[str, Any] = {"model": model, "input": text[:4000], "voice": voice or "alloy", "response_format": "mp3", "speed": speed}
        body.update(extra or {})
        data, mime = _retry(self.ctl, lambda: http.post_bytes(f"{self.base}/audio/speech", body, h, timeout=300))
        return expect_media(data, mime or "audio/mpeg", "audio", self.label)

    def list_models(self, cap: str) -> List[str]:
        self.need_key()
        if cap == "video":
            res = http.get_json(f"{self.base}/videos/models", self._h(), timeout=30)
            return sorted({m.get("id") for m in (res.get("data") or []) if isinstance(m, dict) and m.get("id")})
        if cap == "image":
            res = http.get_json(f"{self.base}/models?output_modalities=image", self._h(), timeout=30)
            return sorted({m.get("id") for m in (res.get("data") or []) if isinstance(m, dict) and m.get("id")})
        return list(MEDIA_PRESETS["openrouter"]["suggest"].get(cap, []))

    def test(self) -> str:
        res = http.get_json(f"{self.base}/auth/key", self._h(), timeout=30)
        return "chave válida" + (f" ({(res.get('data') or {}).get('label')})" if isinstance(res, dict) and isinstance(res.get("data"), dict) and res["data"].get("label") else "")


# --------------------------------------------------------------------------- Stability AI


class StabilityMedia(MediaProvider):
    id, label = "stability", "Stability AI"
    caps = ("image",)
    supports_refs = True

    def image(self, prompt, *, size="1024x1024", count=1, seed=0, negative="", refs=(), model="", extra=None):
        self.need_key()
        model = (self.model_for("image", model) or "core").lower()
        endpoint = "core" if model == "core" else "ultra" if model == "ultra" else "sd3"
        fields: Dict[str, Any] = {"prompt": prompt, "output_format": "png", "aspect_ratio": aspect_of(size) if aspect_of(size) in ("1:1", "16:9", "9:16", "3:2", "2:3", "4:3") else "1:1"}
        if aspect_of(size) == "4:3":
            fields["aspect_ratio"] = "5:4"
        elif aspect_of(size) == "3:4":
            fields["aspect_ratio"] = "4:5"
        if negative:
            fields["negative_prompt"] = negative
        if endpoint == "sd3":
            fields["model"] = model
        files: List[Tuple[str, str, bytes, str]] = []
        if refs and endpoint != "core":
            fields.update({"mode": "image-to-image", "strength": 0.6} if endpoint == "sd3" else {"strength": 0.6})
            fields.pop("aspect_ratio", None)
            files.append(("image", "ref.png", refs[0][0], refs[0][1]))
        fields.update({k: v for k, v in (extra or {}).items() if isinstance(v, (str, int, float))})
        out: List[Media] = []
        for i in range(max(1, count)):
            if seed or i:
                fields["seed"] = (seed + i) % 4294967294
            data, mime = _retry(self.ctl, lambda: http.post_multipart_files(f"{self.base}/v2beta/stable-image/generate/{endpoint}", fields, files,
                                                                              {**_auth(self.key), "Accept": "image/*"}, timeout=300, raw=True))
            out.append(expect_media(data, mime, "image", self.label))
        return out

    def test(self) -> str:
        self.need_key()
        res = http.get_json(self.base + "/v1/user/balance", _auth(self.key), timeout=30)
        return f"conectado (créditos: {res.get('credits', '?')})"


# --------------------------------------------------------------------------- Replicate


class ReplicateMedia(MediaProvider):
    """Replicate roda milhares de modelos de várias empresas. Informe o modelo como `dono/nome` (ou `dono/nome:versão`)."""

    id, label = "replicate", "Replicate"
    caps = ("image", "video", "sound", "voice")
    supports_refs = True
    _info: Dict[str, Tuple[Optional[Dict[str, Any]], Optional[str]]] = {}
    IMAGE_KEYS = ("image", "input_image", "first_frame_image", "start_image", "init_image", "image_url", "input_images")

    def _h(self, wait: bool = False) -> Dict[str, str]:
        self.need_key()
        return {**_auth(self.key), **({"Prefer": "wait=45"} if wait else {})}

    def _model_info(self, slug: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """(propriedades de entrada do modelo, id da versão mais recente) — para só enviar parâmetros que o modelo aceita."""
        key = self.base + "|" + slug
        if key not in self._info:
            props, latest = None, None
            try:
                info = http.get_json(f"{self.base}/models/{slug}", self._h(), timeout=30)
                ver = info.get("latest_version") or {}
                latest = ver.get("id")
                inp = (((ver.get("openapi_schema") or {}).get("components") or {}).get("schemas") or {}).get("Input") or {}
                props = inp.get("properties") or None
            except ProviderError:
                pass
            self._info[key] = (props, latest)
        return self._info[key]

    def _run(self, slug: str, wanted: Dict[str, Any], extra: Optional[Dict[str, Any]], kind: str, image_value: Any = None) -> List[Media]:
        if not slug:
            raise ProviderError("Replicate: informe o modelo (ex.: black-forest-labs/flux-schnell) no nó ou em Configuração → Mídia.")
        name, _, version = slug.partition(":")
        props, latest = self._model_info(name)
        inp = dict(wanted)
        if image_value is not None:
            key = next((k for k in self.IMAGE_KEYS if props and k in props), "image")
            inp[key] = [image_value] if key == "input_images" else image_value
        if props is not None:
            inp = {k: v for k, v in inp.items() if k in props}
        inp.update(extra or {})
        h = self._h(wait=True)
        if version:
            url, body = f"{self.base}/predictions", {"version": version, "input": inp}
        else:
            url, body = f"{self.base}/models/{name}/predictions", {"input": inp}
        try:
            pred = _retry(self.ctl, lambda: http.post_json(url, body, h, timeout=120))
        except ProviderError as exc:
            if exc.status == 404 and latest and not version:  # modelo da comunidade: precisa de versão
                pred = _retry(self.ctl, lambda: http.post_json(f"{self.base}/predictions", {"version": latest, "input": inp}, h, timeout=120))
            else:
                raise
        return self._collect(pred, kind)

    def _collect(self, pred: Any, kind: str) -> List[Media]:
        deadline = time.time() + 1800
        while isinstance(pred, dict) and pred.get("status") in ("starting", "processing"):
            if time.time() > deadline:
                raise ProviderError("Replicate: a geração demorou demais (mais de 30 minutos).")
            try:
                self.ctl.check()
            except BaseException:
                cancel = (pred.get("urls") or {}).get("cancel")
                if cancel:
                    try:
                        http.post_json(cancel, {}, self._h(), timeout=20)
                    except ProviderError:
                        pass
                raise
            self.ctl.note("Replicate: gerando…")
            self.ctl.sleep(self.poll(2.5))
            pred = http.get_json(pred["urls"]["get"], self._h(), timeout=60)
        if not isinstance(pred, dict) or pred.get("status") != "succeeded":
            raise ProviderError(f"Replicate: {(pred or {}).get('error') or 'a geração não foi concluída'}" if isinstance(pred, dict) else "Replicate: resposta inesperada.")
        urls: List[str] = []

        def walk(v: Any) -> None:
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                urls.append(v)
            elif isinstance(v, list):
                for i in v:
                    walk(i)
            elif isinstance(v, dict):
                for i in v.values():
                    walk(i)

        walk(pred.get("output"))
        if not urls:
            raise ProviderError("Replicate: o modelo não devolveu arquivos.")
        out = []
        for u in urls[:8]:
            data, mime = http.get_bytes(u, timeout=600)
            out.append(expect_media(data, mime, kind, self.label))
        return out

    def image(self, prompt, *, size="1024x1024", count=1, seed=0, negative="", refs=(), model="", extra=None):
        wanted: Dict[str, Any] = {"prompt": prompt, "aspect_ratio": aspect_of(size), "output_format": "png"}
        w, h = parse_wh(size)
        wanted.update({"width": w, "height": h})
        if count > 1:
            wanted["num_outputs"] = count
        if seed:
            wanted["seed"] = seed
        if negative:
            wanted["negative_prompt"] = negative
        props, _ = self._model_info(self.model_for("image", model).partition(":")[0]) if self.model_for("image", model) else (None, None)
        if props is not None and "aspect_ratio" in props:
            wanted.pop("width", None)
            wanted.pop("height", None)
        elif props is None:  # sem esquema conhecido: manda só o essencial
            for k in ("width", "height", "output_format"):
                wanted.pop(k, None)
        return self._run(self.model_for("image", model), wanted, extra, "image", data_uri(*refs[0]) if refs else None)[:max(1, count)]

    def video(self, prompt, *, duration=5, aspect="16:9", image=None, model="", extra=None, seed=0):
        wanted: Dict[str, Any] = {"prompt": prompt, "duration": int(duration), "aspect_ratio": aspect}
        if seed:
            wanted["seed"] = seed
        return self._run(self.model_for("video", model), wanted, extra, "video", data_uri(*image) if image else None)[0]

    def sound(self, prompt, *, kind="sfx", duration=5, model="", extra=None, seed=0):
        wanted: Dict[str, Any] = {"prompt": prompt, "duration": int(duration)}
        if seed:
            wanted["seed"] = seed
        return self._run(self.model_for("sound", model), wanted, extra, "audio")[0]

    def voice(self, text, *, voice="", speed=1.0, model="", extra=None, instructions=""):
        wanted: Dict[str, Any] = {"text": text, "prompt": text, "speed": speed}
        if voice:
            wanted["voice"] = voice
        slug = self.model_for("voice", model)
        props, _ = self._model_info(slug.partition(":")[0]) if slug else (None, None)
        if props is not None and "text" in props:
            wanted.pop("prompt", None)
        elif props is None:
            wanted.pop("prompt", None)
        return self._run(slug, wanted, extra, "audio")[0]

    def test(self) -> str:
        res = http.get_json(self.base + "/account", self._h(), timeout=30)
        return f"conectado ({res.get('username', 'conta')})"


# --------------------------------------------------------------------------- Hugging Face Inference


class HFInferenceMedia(MediaProvider):
    id, label = "huggingface", "Hugging Face (Inference)"
    caps = ("image", "sound", "voice", "stt")

    def _call(self, model: str, payload: Optional[Dict[str, Any]] = None, raw: Optional[bytes] = None, ctype: str = "", accept: str = "*/*") -> Tuple[bytes, str]:
        self.need_key()
        if not model:
            raise ProviderError("Hugging Face: informe o modelo (ex.: black-forest-labs/FLUX.1-schnell) no nó ou em Configuração → Mídia.")
        url = f"{self.base}/{model}"
        headers = {**_auth(self.key), "Accept": accept}
        if raw is not None:
            headers["Content-Type"] = ctype or "application/octet-stream"

        def go() -> Tuple[bytes, str]:
            with http.request(url, payload, headers, raw_body=raw, timeout=600) as resp:
                return resp.read(), resp.headers.get("Content-Type", "application/octet-stream")

        return _retry(self.ctl, go, tries=4, statuses=(429, 502, 503, 504))

    def image(self, prompt, *, size="1024x1024", count=1, seed=0, negative="", refs=(), model="", extra=None):
        model = self.model_for("image", model)
        w, h = parse_wh(size)
        out = []
        for i in range(max(1, count)):
            params: Dict[str, Any] = {"width": w, "height": h}
            if negative:
                params["negative_prompt"] = negative
            if seed or i:
                params["seed"] = seed + i
            params.update(extra or {})
            data, mime = self._call(model, {"inputs": prompt, "parameters": params, "options": {"wait_for_model": True}}, accept="image/*")
            out.append(expect_media(data, mime, "image", self.label))
        return out

    def sound(self, prompt, *, kind="sfx", duration=5, model="", extra=None, seed=0):
        data, mime = self._call(self.model_for("sound", model), {"inputs": prompt, "parameters": dict(extra or {}), "options": {"wait_for_model": True}}, accept="audio/*")
        return expect_media(data, mime, "audio", self.label)

    def voice(self, text, *, voice="", speed=1.0, model="", extra=None, instructions=""):
        data, mime = self._call(self.model_for("voice", model), {"inputs": text, "parameters": dict(extra or {}), "options": {"wait_for_model": True}}, accept="audio/*")
        return expect_media(data, mime, "audio", self.label)

    def transcribe(self, data, filename, mime, *, language="", model=""):
        body, _ = self._call(self.model_for("stt", model), raw=data, ctype=mime or "audio/mpeg", accept="application/json")
        try:
            out = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            raise ProviderError("Hugging Face: resposta de transcrição inválida.") from None
        if isinstance(out, dict) and out.get("error"):
            raise ProviderError(f"Hugging Face: {out['error']}")
        return str(out.get("text", "") if isinstance(out, dict) else out).strip()

    def test(self) -> str:
        self.need_key()
        res = http.get_json("https://huggingface.co/api/whoami-v2", _auth(self.key), timeout=30)
        return f"conectado ({res.get('name', 'conta')})"


# --------------------------------------------------------------------------- Stable Diffusion WebUI (A1111 / Forge, local)


class A1111Media(MediaProvider):
    id, label = "a1111", "Stable Diffusion WebUI (local)"
    caps = ("image",)
    supports_refs = True

    def image(self, prompt, *, size="1024x1024", count=1, seed=0, negative="", refs=(), model="", extra=None):
        self.need_url()
        w, h = parse_wh(size)
        body: Dict[str, Any] = {"prompt": prompt, "negative_prompt": negative, "width": w, "height": h, "seed": seed if seed else -1, "batch_size": max(1, min(4, count)), "n_iter": 1,
                                "steps": 25, "send_images": True, "save_images": False}
        model = self.model_for("image", model)
        if model:
            body["override_settings"] = {"sd_model_checkpoint": model}
        path = "txt2img"
        if refs:
            path = "img2img"
            body.update({"init_images": [base64.b64encode(refs[0][0]).decode("ascii")], "denoising_strength": 0.6})
        body.update(extra or {})
        res = _retry(self.ctl, lambda: http.post_json(f"{self.base}/sdapi/v1/{path}", body, _auth(self.key), timeout=900))
        imgs = [expect_media(base64.b64decode(b.split(",", 1)[-1]), "", "image", self.label) for b in (res.get("images") if isinstance(res, dict) else None) or []]
        if not imgs:
            raise ProviderError("Stable Diffusion WebUI não devolveu imagens (a WebUI foi iniciada com --api?).")
        return imgs[:max(1, count)]

    def list_models(self, cap: str) -> List[str]:
        self.need_url()
        res = http.get_json(self.base + "/sdapi/v1/sd-models", _auth(self.key), timeout=30)
        return [m.get("title", "") for m in res if isinstance(m, dict)]

    def test(self) -> str:
        return f"conectado ({len(self.list_models('image'))} modelos)"


# --------------------------------------------------------------------------- Modelos do Hugging Face rodando localmente

_LOCAL_LOCK = threading.Lock()
_LOCAL_CACHE: Dict[Tuple[str, str], Any] = {}


def _local_import(*names: str, extra: str = "media") -> List[Any]:
    try:
        return [__import__(n, fromlist=["_"]) for n in names]
    except ImportError as exc:
        raise ProviderError(f'Modelos locais precisam das bibliotecas opcionais ({exc.name}). Instale com:  pip install "asta[' + extra + ']"  (ou rode: asta libs)') from None


def _device() -> Tuple[str, Any]:
    (torch,) = _local_import("torch")
    if torch.cuda.is_available():
        return "cuda", torch.float16
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps", torch.float16
    return "cpu", torch.float32


def _give_back_memory() -> None:
    """Depois de descarregar um modelo de mídia: tira os pesos do cache de páginas e devolve ao sistema a RAM que o alocador ainda segura (núcleo Rust)."""
    try:
        for f in (_PLAN.get("files") or [])[:64]:
            _native.evict_file(f)
        _native.release_memory()
    except Exception:  # noqa: BLE001
        pass


def _media_unload() -> None:
    with _LOCAL_LOCK:
        _LOCAL_CACHE.clear()
    gc.collect()
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    _give_back_memory()


_MEDIA_IDLE = _perf.IdleUnloader(_media_unload)
PERF: Dict[str, Any] = {}  # settings["performance"], preenchido pela rota/engine antes de gerar


_PLAN: Dict[str, Any] = {}   # plano de carga do modelo que está sendo carregado (núcleo Rust): estratégia de GPU/descarga, fatias de atenção e VAE


def _media_plan(model: str) -> Dict[str, Any]:
    """Plano de carga a partir do tamanho REAL dos pesos baixados e da memória livre agora. Qualquer falha devolve {} (comportamento antigo)."""
    try:
        from . import localmodels as lm

        snap = lm._snapshot(model)
        weights = _native.dir_weight_bytes(snap) if snap else 0
        if not weights:
            return {}
        mem = _perf.memory_state()
        mode = _perf.MODE_NUM[_perf.profile(PERF, hardware_info())["mode"]]
        plan = _native.plan_media(weights, mem["vram_free"], mem["ram_avail"], mem["unified"], mode)
        plan.update(weights=weights, files=_native.weight_files(snap))
        return plan
    except Exception:  # noqa: BLE001
        return {}


def _slim(pipe: Any, dev: str) -> Any:
    """Coloca o modelo no dispositivo seguindo o plano: tudo na GPU, descarga do modelo, descarga sequencial (cabe em pouca VRAM) ou CPU; fatias de atenção/VAE quando o plano pede.
    Sem plano (tamanho desconhecido), vale o modo de desempenho como antes."""
    plan = dict(_PLAN)
    prof = _perf.profile(PERF, hardware_info())
    if not plan.get("strategy"):
        plan = {"strategy": "model_offload" if prof["media_offload"] and dev == "cuda" else "gpu", "slicing": prof["media_offload"], "tiling": prof["media_offload"]}
    for flag, fns in (("slicing", ("enable_attention_slicing", "enable_vae_slicing")), ("tiling", ("enable_vae_tiling",))):
        if plan.get(flag):
            for fn in fns:
                try:
                    getattr(pipe, fn)()
                except Exception:  # noqa: BLE001
                    pass
    if dev == "cuda" and plan["strategy"] in ("model_offload", "sequential_offload"):
        for fn in (("enable_sequential_cpu_offload", "enable_model_cpu_offload") if plan["strategy"] == "sequential_offload" else ("enable_model_cpu_offload",)):
            try:
                getattr(pipe, fn)()
                return pipe
            except Exception:  # noqa: BLE001
                pass
    return pipe.to(dev)


def _local_load(cap: str, model: str, loader: Callable[[], Any]) -> Any:
    """Mantém só um modelo local na memória por vez (hardware modesto). Antes de carregar: plano (núcleo Rust) e pré-carga paralela dos pesos para o cache do sistema."""
    _MEDIA_IDLE.touch(_perf.profile(PERF, hardware_info())["idle_s"])
    with _LOCAL_LOCK:
        key = (cap, model)
        if key not in _LOCAL_CACHE:
            had = bool(_LOCAL_CACHE)
            _LOCAL_CACHE.clear()
            gc.collect()
            try:
                import torch  # type: ignore

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            if had:
                _give_back_memory()   # trocou de modelo: a RAM do anterior volta antes de carregar o novo
            plan = _media_plan(model)
            _PLAN.clear()
            _PLAN.update(plan)
            if plan.get("prefetch") and plan.get("files"):
                _native.prefetch(plan["files"])   # leitura paralela: o from_pretrained acha os pesos já em RAM
            try:
                _LOCAL_CACHE[key] = loader()
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                if "torchvision" in str(exc).lower():  # ex.: processadores de visão do Qwen-Image/Qwen3-VL pedem a torchvision
                    raise ProviderError("Este modelo precisa da biblioteca torchvision, que não está instalada. Instale com:  pip install torchvision  (ou rode: asta libs --extras media) e tente de novo; depois de instalar, reinicie o ASTA.") from None
                raise
            if plan:
                _native.record("media", cap=cap, model=model, strategy=plan.get("strategy"), weights=plan.get("weights"), slicing=plan.get("slicing"), tiling=plan.get("tiling"))
        return _LOCAL_CACHE[key]


def _wav_from_array(arr: Any, rate: int) -> bytes:
    (np,) = _local_import("numpy")
    a = np.asarray(arr, dtype="float32")
    a = np.squeeze(a)
    if a.ndim == 2 and a.shape[0] <= 8 < a.shape[1]:
        a = a.T
    if a.ndim > 2:
        a = a.reshape(-1)
    peak = float(np.max(np.abs(a))) or 1.0
    if peak > 1.0:
        a = a / peak
    pcm = (np.clip(a, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1 if pcm.ndim == 1 else pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class LocalHFMedia(MediaProvider):
    """Modelos do Hugging Face dentro do próprio ASTA (diffusers/transformers).

    Nada é baixado em silêncio: o usuário escolhe a precisão (quantização) e baixa o modelo em Configuração → Mídia (veja `localmodels.py`);
    aqui só são carregados modelos já baixados, na precisão escolhida.
    """

    id, label = "local_hf", "Hugging Face local (embutido)"
    caps = ("image", "video", "sound", "voice", "stt")
    supports_refs = False

    def _pick(self, cap: str, model: str, default: str) -> str:
        """O modelo pedido; se ele ainda não foi baixado, usa outro já baixado da mesma função (o padrão ou uma sugestão) em vez de falhar. Se nenhum foi baixado, devolve o pedido
        (e `_ready` explica como baixar). Nada é baixado em silêncio."""
        from . import localmodels as lm

        want = self.model_for(cap, model) or default
        try:
            if lm.downloaded_precision(want):
                return want
            for alt in [default] + list((MEDIA_PRESETS.get("local_hf") or {}).get("suggest", {}).get(cap, [])):
                if alt != want and lm.downloaded_precision(alt):
                    self.ctl.note(f'O modelo "{want}" ainda não foi baixado: usando "{alt}", que já está baixado.')
                    return alt
        except ProviderError:
            pass  # sem as bibliotecas de modelos locais: `_ready` mostra a mensagem de instalação
        return want

    def _ready(self, model: str) -> Dict[str, Any]:
        """Argumentos de carregamento do modelo (precisão escolhida, só arquivos locais). Recusa modelos que ainda não foram baixados."""
        from . import localmodels as lm

        prec = lm.downloaded_precision(model)
        if not prec:
            raise ProviderError(f'O modelo local "{model}" ainda não foi baixado. Em Configuração → Mídia, escolha a precisão (quantização) e baixe-o antes de usar.', status=424)
        low = prec in ("fp16", "bf16")
        self.ctl.note(f"Modelo local {model} ({prec})")
        return {"precision": prec, "dtype": lm.torch_dtype(prec), "variant": "fp16" if low and lm.has_fp16_variant(model) else None}

    def image(self, prompt, *, size="1024x1024", count=1, seed=0, negative="", refs=(), model="", extra=None):
        model = self._pick("image", model, "stabilityai/sd-turbo")
        (diffusers,) = _local_import("diffusers")
        dev, _ = _device()
        ready = self._ready(model)

        def load() -> Any:
            kw: Dict[str, Any] = {"torch_dtype": ready["dtype"], "local_files_only": True}
            if ready["variant"]:
                kw["variant"] = ready["variant"]
            pipe = diffusers.AutoPipelineForText2Image.from_pretrained(model, **kw)
            return _slim(pipe, dev)

        pipe = _local_load("image", model, load)
        (torch,) = _local_import("torch")
        fast = any(k in model.lower() for k in ("turbo", "lightning", "schnell", "lcm"))
        w, h = parse_wh(size)
        w, h = (min(w, 768), min(h, 768)) if dev == "cpu" else (w, h)
        w, h = max(256, w // 8 * 8), max(256, h // 8 * 8)
        out = []
        for i in range(max(1, count)):
            self.ctl.check()
            self.ctl.note("Gerando imagem localmente…")
            kw = {"prompt": prompt, "width": w, "height": h, "num_inference_steps": 2 if fast else 25, "guidance_scale": 0.0 if fast else 7.0,
                  "generator": torch.Generator("cpu").manual_seed(int(seed + i) if seed else int(time.time() * 1000) % (2 ** 31) + i)}
            if negative and not fast:
                kw["negative_prompt"] = negative
            kw.update(extra or {})
            img = pipe(**kw).images[0]
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            out.append(Media(buf.getvalue(), "image/png"))
        return out

    def sound(self, prompt, *, kind="sfx", duration=5, model="", extra=None, seed=0):
        model = self._pick("sound", model, "facebook/musicgen-small")
        (tf,) = _local_import("transformers")
        ready = self._ready(model)
        pipe = _local_load("sound", model, lambda: tf.pipeline("text-to-audio", model=model, torch_dtype=ready["dtype"], model_kwargs={"local_files_only": True}))
        self.ctl.note("Gerando som localmente…")
        res = pipe(prompt, forward_params={"do_sample": True, "max_new_tokens": int(max(1, min(30, duration)) * 50), **(extra or {})})
        return Media(_wav_from_array(res["audio"], res["sampling_rate"]), "audio/wav")

    def voice(self, text, *, voice="", speed=1.0, model="", extra=None, instructions=""):
        model = self._pick("voice", model, "suno/bark-small")
        (tf,) = _local_import("transformers")
        ready = self._ready(model)
        pipe = _local_load("voice", model, lambda: tf.pipeline("text-to-speech", model=model, torch_dtype=ready["dtype"], model_kwargs={"local_files_only": True}))
        self.ctl.note("Sintetizando voz localmente…")
        res = pipe(text, **(extra or {}))
        return Media(_wav_from_array(res["audio"], res["sampling_rate"]), "audio/wav")

    def transcribe(self, data, filename, mime, *, language="", model=""):
        model = self._pick("stt", model, "openai/whisper-small")
        (tf,) = _local_import("transformers")
        ready = self._ready(model)
        pipe = _local_load("stt", model, lambda: tf.pipeline("automatic-speech-recognition", model=model, torch_dtype=ready["dtype"], model_kwargs={"local_files_only": True}))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ("audio." + (MIME_EXT.get(mime, "") or (filename.rsplit(".", 1)[-1] if "." in filename else "wav")))
            p.write_bytes(data)
            kw: Dict[str, Any] = {"return_timestamps": True}
            if language and language != "auto":
                kw["generate_kwargs"] = {"language": language.split("-")[0]}
            res = pipe(str(p), **kw)
        return str(res.get("text", "")).strip()

    def video(self, prompt, *, duration=5, aspect="16:9", image=None, model="", extra=None, seed=0):
        """Vídeo local exige GPU com bastante memória. Os quadros viram MP4 pelo ffmpeg."""
        model = self._pick("video", model, "Lightricks/LTX-Video")
        (diffusers,) = _local_import("diffusers")
        ff = proc.ffmpeg_path()
        if not ff:
            raise ProviderError("O vídeo local precisa do ffmpeg para montar o arquivo (instale-o).")
        dev, _ = _device()
        ready = self._ready(model)
        vkw = {"torch_dtype": ready["dtype"], "local_files_only": True, **({"variant": ready["variant"]} if ready["variant"] else {})}
        pipe = _local_load("video", model, lambda: _slim(diffusers.DiffusionPipeline.from_pretrained(model, **vkw), dev))
        w, h = size_of_aspect(aspect, 704 if dev != "cpu" else 384)
        w, h = w // 32 * 32 or 32, h // 32 * 32 or 32
        fps = 24
        kw: Dict[str, Any] = {"prompt": prompt, "width": w, "height": h, "num_frames": int(max(9, min(161, duration * fps)) // 8 * 8 + 1)}
        if image:
            from PIL import Image  # type: ignore

            kw["image"] = Image.open(io.BytesIO(image[0])).convert("RGB").resize((w, h))
        kw.update(extra or {})
        self.ctl.note("Gerando vídeo localmente (pode demorar)…")
        frames = pipe(**kw).frames[0]
        return _frames_to_mp4(frames, fps)

    def test(self) -> str:
        _local_import("torch")
        dev, _ = _device()
        have = [m for m in ("diffusers", "transformers") if shutil.which("python") is not None and _has(m)]
        return f"torch ok · dispositivo: {dev} · bibliotecas: {', '.join(have) or 'nenhuma'}"


def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


# --------------------------------------------------------------------------- Voz da Configuração (STT/TTS por servidor)


def _frames_to_mp4(frames: Any, fps: int) -> Media:
    """Quadros (imagens PIL) → MP4 pelo ffmpeg."""
    ff = proc.ffmpeg_path()
    if not ff:
        raise ProviderError("Montar o vídeo precisa do ffmpeg (instale-o).")
    with tempfile.TemporaryDirectory() as tmp:
        for i, fr in enumerate(frames):
            fr.save(Path(tmp) / f"f{i:05d}.png")
        dst = Path(tmp) / "o.mp4"
        r = perf.run([ff, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(Path(tmp) / "f%05d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)],
                           capture_output=True, timeout=600)
        if r.returncode != 0 or not dst.exists():
            raise ProviderError("ffmpeg falhou ao montar o vídeo: " + r.stderr.decode("utf-8", "replace")[-200:])
        return Media(dst.read_bytes(), "video/mp4")


class GGUFMedia(MediaProvider):
    """Modelos GGUF de imagem e vídeo (FLUX, Stable Diffusion, Wan…) rodando dentro do ASTA pela stable-diffusion.cpp (`pip install "asta[local]"`).

    Os arquivos são baixados em Configuração → Modelos locais (aba Imagem ou Vídeo, com a quantização à sua escolha) e ficam em
    `<dados>/models/image` e `<dados>/models/video`. O campo "extra" do nó aceita `{"load": {...}}` (argumentos do modelo; o texto "@model" vira o arquivo
    escolhido e nomes de arquivo viram caminhos na mesma pasta, ex.: {"diffusion_model_path": "@model", "vae_path": "ae.safetensors"}) e, fora de "load",
    argumentos da geração (steps, cfg_scale…).
    """

    id, label = "gguf_local", "GGUF local (stable-diffusion.cpp)"
    caps = ("image", "video")
    supports_refs = False

    def _path(self, cap: str, model: str) -> Path:
        name = Path(self.model_for(cap, model)).name
        if not name:
            raise ProviderError(f"Escolha um modelo GGUF de {CAP_LABELS[cap]} em Configuração → Modelos locais ({'Imagem' if cap == 'image' else 'Vídeo'}).")
        path = Path(self.cfg.get("models_dir") or ".") / cap / name
        if not path.is_file():
            raise ProviderError(f"Modelo GGUF não encontrado: {path}. Baixe-o em Configuração → Modelos locais.")
        return path

    def _engine(self, cap: str, path: Path, load: Dict[str, Any]) -> Any:
        (sdc,) = _local_import("stable_diffusion_cpp", extra="local")
        kw: Dict[str, Any] = {}
        for k, v in load.items():
            if isinstance(v, str) and v == "@model":
                kw[k] = str(path)
            elif isinstance(v, str) and k.endswith("_path") and (path.parent / Path(v).name).is_file():
                kw[k] = str(path.parent / Path(v).name)
            else:
                kw[k] = v
        if not kw:
            kw["model_path"] = str(path)
        return _local_load("gguf-" + cap, f"{path}|{sorted(kw.items())}", lambda: sdc.StableDiffusion(**kw))

    def image(self, prompt, *, size="1024x1024", count=1, seed=0, negative="", refs=(), model="", extra=None):
        from .. import preinstalled

        path = self._path("image", model)
        base = preinstalled.defaults_for("image", path.name)  # modelos pré-instalados já vêm com o jeito certo de carregar; o "extra" do nó sobrescreve
        extra = {**base.get("run", {}), **(extra or {})}
        sd = self._engine("image", path, {**base.get("load", {}), **(extra.pop("load", None) or {})})
        w, h = parse_wh(size)
        w, h = max(256, min(w, 1024) // 8 * 8), max(256, min(h, 1024) // 8 * 8)
        out = []
        for i in range(max(1, count)):
            self.ctl.check()
            self.ctl.note("Gerando imagem com o modelo GGUF…")
            kw = {"prompt": prompt, "width": w, "height": h, "seed": int(seed + i) if seed else int(time.time() * 1000) % (2 ** 31) + i, **extra}
            if negative:
                kw.setdefault("negative_prompt", negative)
            for img in sd.txt2img(**kw)[:1]:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                out.append(Media(buf.getvalue(), "image/png"))
        return out

    def video(self, prompt, *, duration=5, aspect="16:9", image=None, model="", extra=None, seed=0):
        extra = dict(extra or {})
        path = self._path("video", model)
        sd = self._engine("video", path, extra.pop("load", None) or {})
        fn = getattr(sd, "txt2vid", None) or getattr(sd, "generate_video", None)
        if fn is None:
            raise ProviderError("A versão instalada da stable-diffusion-cpp-python não gera vídeo. Atualize-a (asta libs) ou use outro provedor de vídeo.")
        w, h = size_of_aspect(aspect, 640)
        self.ctl.note("Gerando vídeo com o modelo GGUF (pode demorar)…")
        frames = fn(prompt=prompt, width=w // 8 * 8, height=h // 8 * 8, seed=int(seed) if seed else -1, **extra)
        return _frames_to_mp4(frames, 16)

    def test(self) -> str:
        _local_import("stable_diffusion_cpp", extra="local")
        have = {k: len(list((Path(self.cfg.get("models_dir") or ".") / k).glob("*.gguf"))) for k in ("image", "video")}
        return f"stable-diffusion-cpp-python ok · modelos GGUF: {have['image']} de imagem, {have['video']} de vídeo"


class VoiceSettingsMedia(MediaProvider):
    """Usa o servidor de voz já configurado em Configuração → Voz (OpenAI-compatível: nuvem ou local)."""

    id, label = "voice_settings", "Voz da Configuração"
    caps = ("voice", "stt")

    def voice(self, text, *, voice="", speed=1.0, model="", extra=None, instructions=""):
        from .. import voice as vc

        settings = self.cfg.get("settings") or {}
        if not vc.tts_enabled(settings):
            raise ProviderError("Configure um servidor de síntese de voz em Configuração → Voz (modo servidor).")
        data, mime = vc.synthesize(settings, text, voice)
        return expect_media(data, mime, "audio", self.label)

    def transcribe(self, data, filename, mime, *, language="", model=""):
        from .. import voice as vc

        settings = self.cfg.get("settings") or {}
        if not vc.stt_enabled(settings):
            raise ProviderError("Configure um servidor de transcrição em Configuração → Voz (modo servidor).")
        return vc.transcribe_bytes(settings, data, filename or "audio.mp3", mime or "audio/mpeg", language).strip()

    def test(self) -> str:
        from .. import voice as vc

        s = self.cfg.get("settings") or {}
        return f"síntese {'ativa' if vc.tts_enabled(s) else 'desligada'} · transcrição {'ativa' if vc.stt_enabled(s) else 'desligada'}"


# --------------------------------------------------------------------------- catálogo

MEDIA_PRESETS: Dict[str, Dict[str, Any]] = {
    "demo": {
        "label": "Demo (offline, sem IA)", "kind": "demo", "caps": ["image", "video", "sound", "voice"], "local": True, "needs_key": False,
        "hint": "Gera paisagens abstratas, sons sintetizados e vídeos simples sem chave e sem internet — ótimo para testar fluxos inteiros (vídeo precisa do ffmpeg).",
    },
    "openai": {
        "label": "OpenAI", "kind": "openai", "caps": ["image", "video", "voice", "stt"], "base_url": "https://api.openai.com/v1", "needs_key": True,
        "docs": "https://platform.openai.com/api-keys", "models": {"image": "gpt-image-1", "video": "sora-2", "voice": "tts-1", "stt": "whisper-1"},
        "suggest": {"image": ["gpt-image-1", "dall-e-3"], "video": ["sora-2", "sora-2-pro"], "voice": ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"], "stt": ["whisper-1", "gpt-4o-transcribe"]},
        "hint": "Imagens (com edição e referências), vozes, transcrição e vídeo (Sora, experimental).",
    },
    "xai": {
        "label": "xAI (Grok Imagine)", "kind": "openai", "caps": ["image"], "base_url": "https://api.x.ai/v1", "needs_key": True, "no_size": True,
        "docs": "https://console.x.ai", "models": {"image": "grok-2-image"}, "suggest": {"image": ["grok-2-image"]},
    },
    "elevenlabs": {
        "label": "ElevenLabs", "kind": "elevenlabs", "caps": ["voice", "sound", "stt"], "base_url": "https://api.elevenlabs.io/v1", "needs_key": True,
        "docs": "https://elevenlabs.io/app/settings/api-keys",
        "models": {"voice": "eleven_multilingual_v2", "stt": "scribe_v1"}, "suggest": {"voice": ["eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_v3"], "stt": ["scribe_v1"]},
        "hint": 'Vozes realistas (no nó Voz use o nome ou o ID da voz), efeitos sonoros e música (experimental).',
    },
    "openrouter": {
        "label": "OpenRouter", "kind": "openrouter", "caps": ["image", "video", "voice"], "base_url": "https://openrouter.ai/api/v1", "needs_key": True,
        "docs": "https://openrouter.ai/keys", "models": {"image": "google/gemini-2.5-flash-image", "video": "google/veo-3.1", "voice": "openai/gpt-4o-mini-tts"},
        "suggest": {"image": ["google/gemini-2.5-flash-image", "openai/gpt-image-1"], "video": ["google/veo-3.1"], "voice": ["openai/gpt-4o-mini-tts", "openai/tts-1"]},
        "hint": "Imagens, vídeos e vozes com a mesma chave (ou login) do OpenRouter, a mesma do chat. Use «Carregar modelos» para ver os modelos atuais de cada tipo.",
    },
    "google": {
        "label": "Google (Gemini / Veo)", "kind": "google", "caps": ["image", "video"], "base_url": "https://generativelanguage.googleapis.com/v1beta", "needs_key": True,
        "docs": "https://aistudio.google.com/apikey", "models": {"image": "gemini-2.5-flash-image", "video": "veo-3.0-fast-generate-001"},
        "suggest": {"image": ["gemini-2.5-flash-image", "imagen-4.0-generate-001"], "video": ["veo-3.0-fast-generate-001", "veo-3.0-generate-001"]},
        "hint": "A mesma chave do Gemini. Vídeo (Veo) é experimental e pode exigir plano pago.",
    },
    "stability": {
        "label": "Stability AI", "kind": "stability", "caps": ["image"], "base_url": "https://api.stability.ai", "needs_key": True,
        "docs": "https://platform.stability.ai/account/keys", "models": {"image": "core"}, "suggest": {"image": ["core", "ultra", "sd3.5-large", "sd3.5-large-turbo", "sd3.5-medium"]},
    },
    "replicate": {
        "label": "Replicate (milhares de modelos)", "kind": "replicate", "caps": ["image", "video", "sound", "voice"], "base_url": "https://api.replicate.com/v1", "needs_key": True,
        "docs": "https://replicate.com/account/api-tokens",
        "models": {"image": "black-forest-labs/flux-schnell", "video": "minimax/video-01", "sound": "meta/musicgen", "voice": "jaaari/kokoro-82m"},
        "suggest": {"image": ["black-forest-labs/flux-schnell", "black-forest-labs/flux-dev", "stability-ai/sdxl"], "video": ["minimax/video-01", "kwaivgi/kling-v2.1", "wan-video/wan-2.2-t2v-fast"],
                    "sound": ["meta/musicgen"], "voice": ["jaaari/kokoro-82m"]},
        "hint": "Informe o modelo como dono/nome. O ASTA lê o esquema do modelo e só envia os parâmetros que ele aceita.",
    },
    "huggingface": {
        "label": "Hugging Face (Inference)", "kind": "huggingface", "caps": ["image", "sound", "voice", "stt"], "base_url": "https://router.huggingface.co/hf-inference/models", "needs_key": True,
        "docs": "https://huggingface.co/settings/tokens",
        "models": {"image": "black-forest-labs/FLUX.1-schnell", "sound": "facebook/musicgen-small", "voice": "facebook/mms-tts-eng", "stt": "openai/whisper-large-v3"},
        "suggest": {"image": ["black-forest-labs/FLUX.1-schnell", "stabilityai/stable-diffusion-xl-base-1.0"], "voice": ["facebook/mms-tts-eng", "facebook/mms-tts-por", "suno/bark-small"],
                    "sound": ["facebook/musicgen-small"], "stt": ["openai/whisper-large-v3", "openai/whisper-small"]},
        "hint": "Usa a mesma chave do Hugging Face (Configuração → Provedores). A disponibilidade de cada modelo depende do serviço.",
    },
    "a1111": {
        "label": "Stable Diffusion WebUI (local)", "kind": "a1111", "caps": ["image"], "base_url": "http://127.0.0.1:7860", "needs_key": False, "local": True,
        "docs": "https://github.com/AUTOMATIC1111/stable-diffusion-webui", "hint": "AUTOMATIC1111 ou Forge, iniciado com a opção --api. Gera no seu computador.",
    },
    "local_hf": {
        "label": "Hugging Face local (embutido)", "kind": "local_hf", "caps": ["image", "video", "sound", "voice", "stt"], "needs_key": False, "local": True,
        "models": {"image": "stabilityai/sd-turbo", "video": "Lightricks/LTX-Video", "sound": "facebook/musicgen-small", "voice": "suno/bark-small", "stt": "openai/whisper-small"},
        "suggest": {"image": ["stabilityai/sd-turbo", "stabilityai/sdxl-turbo", "black-forest-labs/FLUX.1-schnell"], "video": ["Lightricks/LTX-Video"],
                    "sound": ["facebook/musicgen-small"], "voice": ["suno/bark-small", "facebook/mms-tts-por"], "stt": ["openai/whisper-small", "openai/whisper-large-v3-turbo"]},
        "hint": 'Roda modelos do Hugging Face dentro do ASTA. Requer:  pip install "asta[media]". Antes de usar, escolha a precisão (quantização) e baixe cada modelo aqui mesmo — nada é baixado em silêncio. Vídeo exige GPU.',
    },
    "gguf_local": {
        "label": "GGUF local (stable-diffusion.cpp)", "kind": "gguf_local", "caps": ["image", "video"], "needs_key": False, "local": True,
        "hint": 'Modelos GGUF de imagem e vídeo (FLUX, Stable Diffusion, Wan…) quantizados, rodando no ASTA. Requer:  pip install "asta[local]". Baixe-os em Configuração → Modelos locais (abas Imagem e Vídeo) escolhendo a quantização.',
    },
    "voice_settings": {
        "label": "Voz da Configuração", "kind": "voice_settings", "caps": ["voice", "stt"], "needs_key": False, "local": True,
        "hint": "Usa o servidor de voz já configurado em Configuração → Voz (Whisper, Kokoro, OpenAI…).",
    },
    "custom": {
        "label": "Servidor compatível com OpenAI (personalizado)", "kind": "openai", "caps": ["image", "voice", "stt"], "base_url": "", "needs_key": False, "local": True,
        "hint": "Qualquer servidor com /images/generations, /audio/speech ou /audio/transcriptions (LocalAI, Kokoro-FastAPI, faster-whisper-server, Together…).",
    },
}

_KINDS = {"demo": DemoMedia, "openrouter": OpenRouterMedia, "openai": OpenAIMedia, "elevenlabs": ElevenLabsMedia, "google": GoogleMedia, "stability": StabilityMedia, "replicate": ReplicateMedia,
          "huggingface": HFInferenceMedia, "a1111": A1111Media, "local_hf": LocalHFMedia, "gguf_local": GGUFMedia, "voice_settings": VoiceSettingsMedia}


def media_config(settings: Dict[str, Any], pid: str) -> Dict[str, Any]:
    preset = MEDIA_PRESETS.get(pid)
    if not preset:
        raise ProviderError(f"Provedor de mídia desconhecido: {pid}")
    cfg = {k: v for k, v in preset.items() if k not in ("models", "suggest")}
    media = settings.get("media") or {}
    url = ((media.get("urls") or {}).get(pid) or "").strip()
    if url:
        cfg["base_url"] = url
    key = ((settings.get("providers") or {}).get(pid) or {}).get("api_key", "")
    if pid == "huggingface" and not key:
        key = (settings.get("hf") or {}).get("token", "")
    cfg["api_key"] = key
    models = dict(preset.get("models") or {})
    models.update({k: v for k, v in ((media.get("models") or {}).get(pid) or {}).items() if v})
    cfg["models"] = models
    cfg["id"] = pid
    if pid == "voice_settings":
        cfg["settings"] = settings
    return cfg


def build_media(settings: Dict[str, Any], pid: str, ctl: Optional[Ctl] = None, models_dir: Optional[Path] = None) -> MediaProvider:
    cfg = media_config(settings, pid)
    if models_dir:
        cfg["models_dir"] = str(models_dir)
    return _KINDS.get(cfg["kind"], OpenAIMedia)(cfg, ctl)


def pick_provider(settings: Dict[str, Any], cap: str, node_pid: str = "") -> str:
    """Provedor de um nó: o escolhido nele, senão o padrão da capacidade (Configuração → Mídia), senão o Demo."""
    pid = node_pid or ((settings.get("media") or {}).get("active") or {}).get(cap) or "demo"
    preset = MEDIA_PRESETS.get(pid)
    if not preset:
        raise ProviderError(f"Provedor de mídia desconhecido: {pid}")
    if cap not in preset["caps"]:
        raise ProviderError(f"{preset['label']} não oferece {CAP_LABELS.get(cap, cap)}. Escolha outro provedor no nó (ou em Configuração → Mídia).")
    return pid


def describe_media_presets(settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for pid, p in MEDIA_PRESETS.items():
        cfg = media_config(settings, pid)
        out.append({"id": pid, "label": p["label"], "caps": p["caps"], "base_url": cfg.get("base_url", ""), "default_url": p.get("base_url", ""), "needs_key": p.get("needs_key", False),
                    "has_key": bool(cfg.get("api_key")), "local": p.get("local", False), "docs": p.get("docs", ""), "hint": p.get("hint", ""),
                    "models": cfg["models"], "suggest": p.get("suggest", {})})
    return out
