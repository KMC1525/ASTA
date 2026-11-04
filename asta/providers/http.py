"""Cliente HTTP mínimo (urllib) com JSON e SSE. Sem dependências externas."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Iterator, Optional, Tuple

from .base import ProviderError

USER_AGENT = "ASTA/0.1 (+https://github.com/KMC1525/ASTA)"


def _ctx() -> ssl.SSLContext:
    return ssl.create_default_context()


def _read_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        body = ""
    try:
        data = json.loads(body)
        err = data.get("error", data)
        if isinstance(err, dict):
            err = err.get("message") or json.dumps(err, ensure_ascii=False)
        return str(err)[:600]
    except Exception:  # noqa: BLE001
        return body[:600]


def request(
    url: str,
    payload: Optional[dict] = None,
    headers: Optional[Dict[str, str]] = None,
    method: Optional[str] = None,
    timeout: float = 120,
    raw_body: Optional[bytes] = None,
):
    """Abre uma requisição e devolve a resposta (file-like). Levanta ProviderError."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    hdrs.update(headers or {})
    data = raw_body
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method or ("POST" if data is not None else "GET"))
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=_ctx())
    except urllib.error.HTTPError as exc:
        raise ProviderError(_read_error(exc) or exc.reason, status=exc.code) from None
    except urllib.error.URLError as exc:
        raise ProviderError(f"Não foi possível conectar a {url.split('/')[2]}: {exc.reason}") from None
    except (TimeoutError, OSError) as exc:
        raise ProviderError(f"Falha de rede: {exc}") from None


def get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 30) -> Any:
    with request(url, headers=headers, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def post_json(url: str, payload: dict, headers: Optional[Dict[str, str]] = None, timeout: float = 120) -> Any:
    with request(url, payload, headers, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def post_bytes(url: str, payload: dict, headers: Optional[Dict[str, str]] = None, timeout: float = 120) -> Tuple[bytes, str]:
    with request(url, payload, headers, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("Content-Type", "application/octet-stream")


def post_multipart(
    url: str, fields: Dict[str, str], file_field: str, filename: str, file_bytes: bytes, file_mime: str,
    headers: Optional[Dict[str, str]] = None, timeout: float = 180,
) -> Any:
    boundary = "----asta" + uuid.uuid4().hex
    parts = []
    for key, val in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{val}\r\n'.encode("utf-8")
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {file_mime}\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(file_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    hdrs = dict(headers or {})
    hdrs["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    with request(url, headers=hdrs, method="POST", timeout=timeout, raw_body=b"".join(parts)) as resp:
        body = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"text": body}


def stream_sse(
    url: str, payload: dict, headers: Optional[Dict[str, str]] = None, timeout: float = 300
) -> Iterator[Tuple[str, str]]:
    """Gera tuplas (evento, dados) de uma resposta Server-Sent Events."""
    hdrs = {"Accept": "text/event-stream"}
    hdrs.update(headers or {})
    resp = request(url, payload, hdrs, timeout=timeout)
    event = "message"
    try:
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                event = "message"
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                yield event, line[5:].strip()
    finally:
        resp.close()
