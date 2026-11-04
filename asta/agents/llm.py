"""Chamadas estruturadas (JSON) a um provedor, com reparo e novas tentativas."""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..providers.base import Provider, ProviderError


def extract_json(raw: str) -> Any:
    """Extrai o primeiro objeto JSON de um texto (tolera cercas ```json e texto em volta)."""
    if raw is None:
        raise ValueError("resposta vazia")
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    if fence and "{" in fence.group(1):
        text = fence.group(1).strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("nenhum objeto JSON na resposta")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunk = text[start:i + 1]
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    repaired = re.sub(r",\s*([}\]])", r"\1", chunk)
                    return json.loads(repaired)
    raise ValueError("objeto JSON incompleto (resposta cortada?)")


def build_user_message(instruction: str, payload: Dict[str, Any], images: Optional[List[dict]], vision: bool):
    text = f"{instruction}\n\nINPUT_JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    if images and vision:
        parts: List[dict] = [{"type": "text", "text": text}]
        for img in images:
            parts.append({"type": "image", "media_type": img["media_type"], "data": img["data"]})
        return parts
    return text


def call_json(
    provider: Provider,
    system: str,
    instruction: str,
    payload: Dict[str, Any],
    *,
    images: Optional[List[dict]] = None,
    temperature: float = 0.8,
    max_tokens: int = 4096,
    attempts: int = 2,
    cancelled: Optional[Callable[[], bool]] = None,
) -> Tuple[Dict[str, Any], str]:
    """Chama o provedor esperando JSON. Devolve (objeto, texto_bruto)."""
    messages: List[dict] = [
        {"role": "user", "content": build_user_message(instruction, payload, images, provider.vision)}
    ]
    last_err = "desconhecido"
    raw = ""
    for attempt in range(attempts):
        if cancelled and cancelled():
            raise ProviderError("cancelado")
        raw = provider.chat(messages, system=system, temperature=temperature, max_tokens=max_tokens, json_mode=True)
        try:
            obj = extract_json(str(raw))
            if not isinstance(obj, dict):
                raise ValueError("o JSON não é um objeto")
            return obj, str(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            last_err = str(exc)
            messages.append({"role": "assistant", "content": str(raw)[:6000]})
            messages.append({
                "role": "user",
                "content": f"Your reply was not valid JSON ({last_err}). Reply again with ONLY the corrected, complete JSON object.",
            })
            temperature = max(0.2, temperature - 0.3)
    raise ValueError(f"JSON inválido após {attempts} tentativas: {last_err}")
