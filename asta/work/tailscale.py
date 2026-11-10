"""Tailscale (opcional) como rede entre as máquinas do Work.

O ASTA **não** instala nem controla o Tailscale: ele só lê o estado (`tailscale status --json`) para achar o IP da tailnet desta máquina e as outras máquinas da mesma tailnet, e escuta
nesse IP (e só nele) para a sincronização. Sem Tailscale o Work funciona igual na rede local (LAN), por endereço digitado ou por uma pasta de nuvem — o Tailscale é uma comodidade
(atravessa NAT e firewall, cifra o tráfego com WireGuard), não um requisito.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

_CACHE: Dict[str, Any] = {"t": 0.0, "v": None}
_CANDIDATES = ("/Applications/Tailscale.app/Contents/MacOS/Tailscale", r"C:\Program Files\Tailscale\tailscale.exe", "/usr/bin/tailscale", "/usr/local/bin/tailscale")


def executable() -> str:
    env = os.environ.get("ASTA_TAILSCALE", "")
    if env:
        return env if os.path.exists(env) else ""
    found = shutil.which("tailscale")
    if found:
        return found
    for c in _CANDIDATES:
        if os.path.isfile(c):
            return c
    return ""


def _node(n: Any) -> Dict[str, Any]:
    n = n if isinstance(n, dict) else {}
    ips = [str(i) for i in (n.get("TailscaleIPs") or []) if isinstance(i, str)]
    v4 = [i for i in ips if "." in i]
    return {"name": str(n.get("HostName") or ""), "dns": str(n.get("DNSName") or "").rstrip("."), "ips": v4 or ips, "online": bool(n.get("Online")), "os": str(n.get("OS") or "")}


def parse(raw: Any) -> Dict[str, Any]:
    """Transforma a saída JSON do `tailscale status --json` no que a tela usa."""
    d = raw if isinstance(raw, dict) else {}
    state = str(d.get("BackendState") or "")
    me = _node(d.get("Self"))
    peers = [_node(p) for p in (d.get("Peer") or {}).values()] if isinstance(d.get("Peer"), dict) else []
    peers.sort(key=lambda p: (not p["online"], p["name"].lower()))
    tn = d.get("CurrentTailnet") if isinstance(d.get("CurrentTailnet"), dict) else {}
    return {"installed": True, "running": state == "Running", "state": state, "self": me, "ip": (me["ips"] or [""])[0], "peers": peers,
            "tailnet": str(tn.get("Name") or d.get("MagicDNSSuffix") or "")}


def status(refresh: bool = False) -> Dict[str, Any]:
    """Estado do Tailscale agora (guardado por 5 s: a tela consulta com frequência)."""
    if not refresh and _CACHE["v"] is not None and time.time() - _CACHE["t"] < 5:
        return _CACHE["v"]
    exe = executable()
    out: Dict[str, Any] = {"installed": False, "running": False, "state": "", "self": {}, "ip": "", "peers": [], "tailnet": "", "error": ""}
    if exe:
        try:
            r = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=4, encoding="utf-8", errors="replace")
            if r.stdout.strip():
                out = {**out, **parse(json.loads(r.stdout))}
            elif r.returncode:
                out.update(installed=True, error=(r.stderr or "").strip()[:200])
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            out.update(installed=True, error=str(exc)[:200])
    _CACHE.update(t=time.time(), v=out)
    return out


def my_ip() -> str:
    st = status()
    return st["ip"] if st.get("running") else ""


def peer_ips() -> List[str]:
    return [ip for p in status().get("peers", []) if p.get("online") for ip in p["ips"][:1]]


def label(st: Optional[Dict[str, Any]] = None) -> str:
    st = st or status()
    if not st.get("installed"):
        return "não instalado"
    return "conectado" if st.get("running") else (st.get("state") or "desconectado").lower()
