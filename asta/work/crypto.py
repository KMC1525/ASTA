"""Criptografia do Work — **só biblioteca padrão** (princípio do ASTA: nenhuma dependência obrigatória).

• Senhas: PBKDF2-HMAC-SHA256 com sal aleatório (`hash_password` / `verify_password`).
• Mensagens e arquivos entre máquinas (e na pasta de nuvem): `seal`/`unseal` — cifra de fluxo com SHAKE-256 (XOF com chave e *nonce*) + MAC HMAC-SHA256 (cifrar-depois-autenticar),
  com chaves separadas derivadas do segredo da rede. É uma construção padrão feita com primitivas da biblioteca padrão, **sem auditoria externa**: dentro do Tailscale o tráfego já vai
  cifrado pelo WireGuard; na pasta de nuvem é esta cifra que protege os dados. Quem precisa de garantia formal deve usar um volume cifrado (VeraCrypt, LUKS, BitLocker).
• Assinatura dos pedidos entre máquinas: `sign` / `check_sig` (HMAC-SHA256 com a chave do segredo da rede).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any, Dict

PBKDF2_ITERATIONS = 240_000
MIN_PASSWORD = 6
NONCE = 16
MAC = 32


# ----------------------------------------------------------------------------- senhas
def hash_password(password: str, *, salt: bytes = b"", iterations: int = PBKDF2_ITERATIONS) -> Dict[str, Any]:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {"alg": "pbkdf2-sha256", "iter": iterations, "salt": salt.hex(), "hash": dk.hex()}


def verify_password(password: str, rec: Any) -> bool:
    try:
        if not isinstance(rec, dict) or rec.get("alg") != "pbkdf2-sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), bytes.fromhex(rec["salt"]), int(rec["iter"]))
        return hmac.compare_digest(dk, bytes.fromhex(rec["hash"]))
    except (ValueError, TypeError, KeyError):
        return False


def check_password_strength(password: str) -> str:
    """Vazio se a senha é aceitável; senão a frase do problema."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        return f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres."
    if len(password) > 256:
        return "Senha longa demais (máximo 256 caracteres)."
    return ""


# ----------------------------------------------------------------------------- segredo da rede
def new_secret() -> str:
    return secrets.token_hex(32)


def _key(secret_hex: str, label: bytes) -> bytes:
    return hmac.new(bytes.fromhex(secret_hex), b"asta-work/" + label, hashlib.sha256).digest()


def _xor(data: bytes, stream: bytes) -> bytes:
    if not data:
        return b""
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")).to_bytes(len(data), "big")


def seal(secret_hex: str, data: bytes, aad: bytes = b"") -> bytes:
    """nonce(16) ‖ texto cifrado ‖ MAC(32). `aad` é autenticado mas não vai na mensagem (amarra a mensagem a um pedido/nome)."""
    nonce = secrets.token_bytes(NONCE)
    stream = hashlib.shake_256(_key(secret_hex, b"enc") + nonce).digest(len(data))
    ct = _xor(data, stream)
    mac = hmac.new(_key(secret_hex, b"mac"), aad + b"\x00" + nonce + ct, hashlib.sha256).digest()
    return nonce + ct + mac


def unseal(secret_hex: str, blob: bytes, aad: bytes = b"") -> bytes:
    if len(blob) < NONCE + MAC:
        raise ValueError("mensagem cifrada curta demais")
    nonce, ct, mac = blob[:NONCE], blob[NONCE:-MAC], blob[-MAC:]
    want = hmac.new(_key(secret_hex, b"mac"), aad + b"\x00" + nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, want):
        raise ValueError("mensagem adulterada ou chave errada")
    stream = hashlib.shake_256(_key(secret_hex, b"enc") + nonce).digest(len(ct))
    return _xor(ct, stream)


def blob_alias(secret_hex: str, sha: str) -> str:
    """Nome do arquivo cifrado na pasta de nuvem: não revela o hash do conteúdo."""
    return hmac.new(_key(secret_hex, b"alias"), sha.encode(), hashlib.sha256).hexdigest()


# ----------------------------------------------------------------------------- assinatura dos pedidos entre máquinas
def sign(secret_hex: str, *parts: str) -> str:
    return hmac.new(_key(secret_hex, b"sig"), "\n".join(parts).encode("utf-8"), hashlib.sha256).hexdigest()


def check_sig(secret_hex: str, sig: str, *parts: str) -> bool:
    try:
        return hmac.compare_digest(sign(secret_hex, *parts), str(sig))
    except (ValueError, TypeError):
        return False


def token(n: int = 24) -> str:
    return secrets.token_urlsafe(n)
