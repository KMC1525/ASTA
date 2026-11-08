"""Celular e tablet: pareamento por QR code.

O app mobile do ASTA é o próprio ASTA instalado no aparelho (PWA, "Adicionar à tela inicial"): ele fala com o ASTA que roda no seu computador, na mesma rede Wi-Fi
(ou em qualquer rede que alcance o computador). Para isso o servidor precisa escutar na rede (`asta mobile`), e então **só aparelhos pareados** entram:
o QR code carrega um código secreto; ao abrir, o aparelho ganha um cookie e passa a ser reconhecido. Quem está no próprio computador (localhost) nunca precisa parear.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import os
import secrets
import re
import socket
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from . import qr

COOKIE = "asta_pair"
PAIR_PATH = "/api/mobile/pair"
APP_RELEASES_URL = "https://github.com/KMC1525/ASTA/releases/latest"  # onde fica o APK do app mobile (anexado a cada Release)
_FORWARD_HEADERS = ("x-forwarded-for", "forwarded", "x-real-ip", "cf-connecting-ip")


def is_loopback(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address((addr or "").split("%")[0])
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_loopback


_LAN_CACHE: Dict[str, object] = {"t": 0.0, "ips": []}


def _hostname_ips(timeout: float = 1.0) -> List[str]:
    """IPv4 do nome do computador. `getaddrinfo(gethostname())` pode travar por muitos segundos (macOS sem DNS para o próprio nome, mDNS): roda numa thread e desiste depois de `timeout`."""
    box: List[str] = []

    def work() -> None:
        try:
            box.extend(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
        except OSError:
            pass

    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout)
    return list(box)


def _tailscale_ips() -> List[str]:
    """IPs do Tailscale deste computador (`tailscale ip -4`), se estiver instalado: é por eles que o celular alcança o ASTA/LM Studio de FORA de casa."""
    import shutil
    import subprocess

    exe = shutil.which("tailscale")
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=2, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return []
    return [x.strip() for x in r.stdout.split() if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", x.strip())] if r.returncode == 0 else []


def lan_ips() -> List[str]:
    """Endereços IPv4 do computador na rede local (o primeiro é o da saída padrão), sem loopback. O resultado vale por 30 s (a tela consulta isto com frequência)."""
    if time.time() - float(_LAN_CACHE["t"]) < 30 and _LAN_CACHE["ips"]:
        return list(_LAN_CACHE["ips"])  # type: ignore[arg-type]
    found: List[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("10.255.255.255", 1))  # UDP: não envia nada, só descobre qual interface seria usada
        found.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    found.extend(_hostname_ips())
    found.extend(_tailscale_ips())   # por último: a rede de casa continua sendo o primeiro endereço
    out: List[str] = []
    for ip in found:
        if ip and not ip.startswith(("127.", "0.", "169.254.")) and ip not in out:
            out.append(ip)
    _LAN_CACHE.update(t=time.time(), ips=list(out))
    return out


class Mobile:
    def __init__(self, home: Path, bind_host: str):
        self.file = Path(home) / "mobile.json"
        self.bind_host = bind_host

    # ----- código de pareamento (guardado em ~/.asta/mobile.json; o app instalado continua pareado depois de reiniciar)
    def token(self) -> str:
        try:
            tok = json.loads(self.file.read_text(encoding="utf-8")).get("token")
            if isinstance(tok, str) and len(tok) >= 20:
                return tok
        except (OSError, ValueError):
            pass
        return self.rotate()

    def rotate(self) -> str:
        tok = secrets.token_urlsafe(24)
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.write_text(json.dumps({"token": tok}), encoding="utf-8")
            self.file.chmod(0o600)
        except OSError:
            pass
        return tok

    @property
    def exposed(self) -> bool:
        return self.bind_host not in ("127.0.0.1", "localhost", "::1")

    @property
    def strict(self) -> bool:
        """Modo do app Android (ASTA_STRICT_LOOPBACK=1): o ASTA roda DENTRO do celular, e no Android qualquer outro app (ou página) do aparelho alcança 127.0.0.1. Por isso até o endereço local
        exige o cookie de pareamento, que só o app conhece (o código fica na pasta privada dele)."""
        return os.environ.get("ASTA_STRICT_LOOPBACK", "") not in ("", "0")

    # ----- controle de acesso
    def is_remote(self, client_ip: str, headers) -> bool:
        """Remoto = veio de outro endereço OU passou por um proxy/túnel (que faz tudo parecer localhost). No modo estrito, tudo é remoto."""
        if self.strict:
            return True
        if not is_loopback(client_ip):
            return True
        present = {k.lower() for k, v in headers.items() if v}
        return any(h in present for h in _FORWARD_HEADERS)

    def cookie_ok(self, cookie_header: str) -> bool:
        for part in (cookie_header or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE and hmac.compare_digest(v.encode(), self.token().encode()):
                return True
        return False

    def allowed(self, client_ip: str, headers, path: str) -> bool:
        if not self.is_remote(client_ip, headers):
            return True
        return path == PAIR_PATH or self.cookie_ok(headers.get("Cookie", ""))

    def pair_ok(self, code: str) -> bool:
        return bool(code) and hmac.compare_digest(code.encode(), self.token().encode())

    # ----- o que a tela do computador mostra
    def info(self, port: int) -> Dict[str, object]:
        ips = lan_ips()
        urls = [f"http://{ip}:{port}/" for ip in ips]
        pair = [f"http://{ip}:{port}{PAIR_PATH}?code={self.token()}" for ip in ips]
        return {"exposed": self.exposed, "port": port, "urls": urls, "pair_urls": pair if self.exposed else [],
                "qr_svg": qr.svg(pair[0], scale=5, border=3) if self.exposed and pair else "", "has_network": bool(ips),
                "app_url": APP_RELEASES_URL, "app_qr_svg": qr.svg(APP_RELEASES_URL, scale=4, border=3)}


PAIR_REQUIRED_HTML = """<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASTA</title><body style="font-family:system-ui;background:#000;color:#eee;max-width:30em;margin:12vh auto;padding:0 20px;line-height:1.5">
<h1 style="font-weight:600">ASTA</h1>
<p>Este aparelho ainda não está pareado. No computador onde o ASTA está rodando, abra <b>Configuração → Celular e tablet</b> (ou rode <code>asta mobile</code>) e <b>escaneie o QR code</b> com a câmera deste aparelho.</p>
<p style="color:#999">This device is not paired yet. On the computer running ASTA open <b>Configuration → Mobile and tablet</b> (or run <code>asta mobile</code>) and scan the QR code with this device's camera.</p>"""
