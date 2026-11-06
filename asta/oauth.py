"""Entrar com a conta do provedor de IA (sem copiar chave).

Só o **OpenRouter** oferece um login OAuth aberto a qualquer app (PKCE, sem cadastro de aplicativo): o usuário entra na conta dele, autoriza, e o ASTA recebe uma chave dele,
guardada como qualquer outra chave. Anthropic (Claude), OpenAI (ChatGPT), xAI e Google **não** permitem que apps de terceiros usem o login da conta/assinatura (Claude Pro, ChatGPT Plus…):
para eles o ASTA abre a página de login do provedor já no lugar de criar a chave, e a chave criada é colada de volta.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
import urllib.parse
from typing import Any, Dict, Optional

from .providers import http

OPENROUTER_AUTH = "https://openrouter.ai/auth"
OPENROUTER_EXCHANGE = "https://openrouter.ai/api/v1/auth/keys"
TTL = 600.0
_pending: Dict[str, Dict[str, Any]] = {}


def _post_json(url: str, payload: dict) -> Any:  # separado para os testes trocarem por um servidor falso
    return http.post_json(url, payload, timeout=30)


def start_openrouter(host: str) -> str:
    """URL de login do OpenRouter. `host` = endereço que o navegador usa para falar com o ASTA (localhost:porta)."""
    now = time.time()
    for k in [k for k, v in _pending.items() if now - v["t"] > TTL]:
        _pending.pop(k, None)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(18)
    _pending[state] = {"verifier": verifier, "t": now}
    callback = f"http://{host}/api/auth/openrouter/callback?state={state}"
    return OPENROUTER_AUTH + "?" + urllib.parse.urlencode({"callback_url": callback, "code_challenge": challenge, "code_challenge_method": "S256"})


def finish_openrouter(state: str, code: str) -> Optional[str]:
    """Troca o código pela chave. Devolve a chave ou levanta ValueError com o motivo."""
    entry = _pending.pop(state or "", None)
    if not entry or time.time() - entry["t"] > TTL:
        raise ValueError("Login expirado ou desconhecido: comece de novo em Configuração → Provedores.")
    if not code:
        raise ValueError("O OpenRouter não devolveu o código de login.")
    try:
        r = _post_json(OPENROUTER_EXCHANGE, {"code": code, "code_verifier": entry["verifier"], "code_challenge_method": "S256"})
    except Exception as exc:  # noqa: BLE001 — rede/HTTP: mostra o motivo
        raise ValueError(f"Não consegui concluir o login no OpenRouter: {exc}") from None
    key = r.get("key") if isinstance(r, dict) else None
    if not isinstance(key, str) or len(key) < 10:
        raise ValueError("O OpenRouter não devolveu uma chave.")
    return key
