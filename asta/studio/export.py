"""Exportação do Studio: completo (vídeo + áudio), somente vídeo ou somente áudio — direto da timeline do episódio."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..canvas.media import Ctl, size_of_aspect
from ..canvas.render import render_timeline
from ..providers import ProviderError
from ..util import now_iso, slugify
from . import schema as S
from . import tools

QUALITY = {"480p": 854, "720p": 1280, "1080p": 1920}  # lado maior
AUDIO_FORMATS = ("m4a", "mp3", "wav")


def export_episode(store: Any, pid: str, eid: str, mode: str = "full", quality: str = "720p", fmt: str = "m4a", fps: int = 24, ctl: Optional[Ctl] = None) -> Dict[str, Any]:
    """Renderiza a timeline do episódio e guarda em studio/<id>/exports. Devolve o registro da exportação."""
    ss = store.studio
    ctl = ctl or Ctl()
    if mode not in S.EXPORT_MODES:
        raise ValueError("Escolha o que exportar: completo, somente vídeo ou somente áudio.")
    tools.need_ffmpeg("A exportação")
    p = ss.get(pid)
    ep = next((e for e in (p or {}).get("episodes", []) if e["id"] == eid), None)
    if not p or not ep:
        raise ValueError("Episódio não encontrado")
    tl = ep["timeline"]
    if not tl["clips"]:
        raise ValueError("A timeline está vazia — gere o episódio (ou adicione clipes) antes de exportar.")
    assets = {a["id"]: a for a in p["assets"]}

    def resolve(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        a = assets.get(c["asset"])
        path = ss.media_path(pid, a["file"]) if a else None
        return {"path": path, "kind": a["kind"], "duration": a["dur"]} if path else None

    long_side = QUALITY.get(quality, 1280)
    w, h = size_of_aspect(p["aspect"], long_side)
    ext = "mp4" if mode != "audio" else (fmt if fmt in AUDIO_FORMATS else "m4a")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    fname = f"{slugify(p['name'], 'video', 40)}-ep{ep['n']}-{mode}-{stamp}.{ext}"
    out = ss.export_dir(pid) / fname
    try:
        warnings = render_timeline(tl, w, h, fps, "#000000", resolve, out, ctl, mode=mode, top_first=True)   # na timeline do Studio a primeira trilha da lista é a de cima (V2 sobre V1), como na prévia
    except ProviderError as exc:
        out.unlink(missing_ok=True)
        raise ProviderError(str(exc).replace("do Editor", "da timeline").replace("O Editor", "A exportação")) from None
    info = tools.probe(out)
    rec = {"file": fname, "mode": mode, "quality": quality if mode != "audio" else "", "format": ext, "size": out.stat().st_size, "dur": round(info["dur"], 2), "created": now_iso(), "warnings": warnings[:10]}

    def fn(pr: Dict[str, Any]) -> None:
        e = next((x for x in pr["episodes"] if x["id"] == eid), None)
        if e is not None:
            e["exports"] = (e["exports"] + [rec])[-30:]

    ss.update(pid, fn)
    return rec
