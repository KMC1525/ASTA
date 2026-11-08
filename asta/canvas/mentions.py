"""Menções com «@» nos prompts do Canvas (v0.17.2): `@nome-da-imagem` aponta para uma imagem **específica** do projeto e a usa como referência da geração.

* Cada imagem do canvas (enviada ou gerada) tem um *apelido* — o nome sem extensão, em minúsculas, sem acentos e com hífens (`Foto Perfil.png` → `foto-perfil`).
  Nomes repetidos ficam com `-2`, `-3`… (a mais antiga mantém o apelido simples), então um apelido sempre aponta para uma imagem só.
* Na hora de gerar, cada `@apelido` achado no prompt vira `apelido (reference image N)` e a imagem entra como referência N (na ordem em que foi citada).
* Um `@` que não casa com nenhuma imagem fica como está no texto e vira aviso; e-mails (`a@b.com`) nunca são tomados por menção.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Tuple

MENTION_RE = re.compile(r"(?<![\w@.])@([A-Za-z0-9][A-Za-z0-9_-]*)")
MAX_REFS = 6


def slug(name: str) -> str:
    base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name or "")
    s = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-") or "imagem"


def table(canvas: Dict[str, Any]) -> List[Dict[str, Any]]:
    """As imagens do canvas com o apelido único de cada uma, da mais nova para a mais antiga."""
    imgs = sorted((a for a in canvas.get("assets", []) if a.get("kind") == "image"), key=lambda a: (a.get("created", ""), a.get("id", "")))
    seen: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    for a in imgs:
        base = slug(a.get("name", ""))
        seen[base] = seen.get(base, 0) + 1
        out.append({"id": a["id"], "slug": base if seen[base] == 1 else f"{base}-{seen[base]}", "name": a.get("name", ""), "file": a.get("file", ""), "created": a.get("created", ""), "node": a.get("node", "")})
    out.reverse()
    return out


def resolve(canvas: Dict[str, Any], prompt: str) -> Tuple[str, List[str], List[str]]:
    """(prompt reescrito, ids das imagens citadas na ordem da 1ª citação, menções sem imagem). Sem `@` válido o prompt volta igual."""
    by = {m["slug"]: m["id"] for m in table(canvas)}
    by_id = {m["id"]: m["id"] for m in table(canvas)}
    order: List[str] = []
    missing: List[str] = []

    def sub(m: "re.Match[str]") -> str:
        tok = m.group(1)
        aid = by.get(tok.lower()) or by_id.get(tok)
        if not aid:
            if tok not in missing:
                missing.append(tok)
            return m.group(0)
        if aid not in order:
            order.append(aid)
        return f"{tok} (reference image {order.index(aid) + 1})"

    return MENTION_RE.sub(sub, prompt or ""), order[:MAX_REFS], missing


def ids_in(canvas: Dict[str, Any], prompt: str) -> List[str]:
    return resolve(canvas, prompt)[1]
