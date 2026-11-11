"""Perfil do usuário do ASTA (v0.21).

Dados pessoais e preferências gerais de trabalho, salvos em arquivos abertos
(JSON + retrato) dentro da pasta do ASTA. Nada sai do computador sem o usuário
pedir. A exportação leva o perfil e os «presets gerais do fluxo de trabalho»
(configurações, sem chaves/tokens) para facilitar trocar de PC.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .util import now_iso, read_json, text, write_json

PROFILE_SCHEMA = "asta.profile.v1"
EXPORT_SCHEMA = "asta.profile-export.v1"

# campos livres de texto (curtos) que o usuário pode preencher; a interface
# mostra os principais e aceita outros em `extra`
FIELDS = ("name", "bio", "gender", "pronouns", "tastes", "studies", "profession", "location", "language", "interests", "website")
LIMITS = {"name": 120, "bio": 4000, "gender": 80, "pronouns": 80, "tastes": 2000, "studies": 2000, "profession": 2000, "location": 160, "language": 120, "interests": 2000, "website": 300}

IMAGE_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}


def sniff_image(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpg"
    if data[:4] == b"GIF8":
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return ""


def default_profile() -> Dict[str, Any]:
    base = {k: "" for k in FIELDS}
    base.update({"schema": PROFILE_SCHEMA, "portrait": "", "extra": {}, "created": "", "updated": ""})
    return base


def normalize(data: Any) -> Dict[str, Any]:
    d = data if isinstance(data, dict) else {}
    out = default_profile()
    for k in FIELDS:
        out[k] = text(d.get(k), "", LIMITS[k])
    extra = d.get("extra")
    if isinstance(extra, dict):
        clean: Dict[str, str] = {}
        for i, (k, v) in enumerate(extra.items()):
            if i >= 40:
                break
            kk = text(k, "", 60)
            if kk:
                clean[kk] = text(v, "", 1000)
        out["extra"] = clean
    portrait = str(d.get("portrait") or "")
    if "/" in portrait or "\\" in portrait or ".." in portrait:
        portrait = ""
    out["portrait"] = portrait[:120]
    out["created"] = text(d.get("created"), "", 40)
    out["updated"] = text(d.get("updated"), "", 40)
    return out


def load(path: Path) -> Dict[str, Any]:
    data = read_json(path, None)
    prof = normalize(data)
    if not prof["created"]:
        prof["created"] = now_iso()
    if not prof["updated"]:
        prof["updated"] = prof["created"]
    return prof


def save(path: Path, data: Any, keep_portrait: Optional[str] = None) -> Dict[str, Any]:
    existing = load(path) if path.exists() else default_profile()
    prof = normalize(data)
    prof["created"] = existing.get("created") or prof["created"] or now_iso()
    prof["updated"] = now_iso()
    if keep_portrait is not None:
        prof["portrait"] = keep_portrait
    elif not prof["portrait"]:
        prof["portrait"] = existing.get("portrait", "")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, prof, private=True)
    return prof


def export_bundle(profile: Dict[str, Any], settings: Dict[str, Any], portrait_bytes: Optional[bytes] = None) -> Dict[str, Any]:
    """Pacote de exportação: perfil + presets gerais do fluxo de trabalho (sem segredos)."""
    from . import uiprefs

    bundle: Dict[str, Any] = {
        "schema": EXPORT_SCHEMA,
        "profile": {k: v for k, v in profile.items() if k != "portrait"},
        "workflow": uiprefs.export_settings(settings),
    }
    if portrait_bytes:
        import base64

        bundle["portrait_b64"] = base64.b64encode(portrait_bytes).decode("ascii")
        bundle["portrait_name"] = profile.get("portrait") or "portrait.png"
    return bundle


def import_bundle(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Arquivo de perfil inválido.")
    if payload.get("schema") == EXPORT_SCHEMA:
        prof = normalize(payload.get("profile"))
        workflow = payload.get("workflow")
        portrait_b64 = payload.get("portrait_b64")
        portrait_name = str(payload.get("portrait_name") or "portrait.png")
        return {"profile": prof, "workflow": workflow, "portrait_b64": portrait_b64 if isinstance(portrait_b64, str) else "", "portrait_name": portrait_name}
    # aceita também um perfil simples
    if payload.get("schema") == PROFILE_SCHEMA or any(k in payload for k in ("name", "bio", "profession")):
        return {"profile": normalize(payload), "workflow": None, "portrait_b64": "", "portrait_name": ""}
    raise ValueError("Este arquivo não é um perfil do ASTA.")


def summary_text(profile: Dict[str, Any]) -> str:
    """Resumo curto do perfil para dar contexto aos modelos (sem segredos; pode ir no prompt)."""
    parts: List[str] = []
    labels = {"name": "Nome", "gender": "Gênero", "pronouns": "Pronomes", "profession": "Profissão", "studies": "Estudos", "location": "Local", "language": "Idioma", "interests": "Interesses", "tastes": "Gostos", "website": "Site"}
    for k, label in labels.items():
        v = str(profile.get(k) or "").strip()
        if v:
            parts.append(f"{label}: {v}")
    bio = str(profile.get("bio") or "").strip()
    if bio:
        parts.append("Bio: " + bio[:400])
    extra = profile.get("extra") or {}
    if isinstance(extra, dict):
        for k, v in list(extra.items())[:8]:
            if str(v).strip():
                parts.append(f"{k}: {str(v).strip()[:120]}")
    return "\n".join(parts)
