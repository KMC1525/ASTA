"""Acesso de fora de casa ao LM Studio do computador, SEM instalar VPN no celular.

Como funciona (tudo opcional e desligado por padrão):

* **Proxy do LM Studio** (`/lm/<código>/…`): o ASTA do computador repassa, para o LM Studio local, só as rotas `v1/…` e `api/v0/…` — e só para quem
  sabe o código secreto (24 bytes aleatórios, comparado em tempo constante). Nada mais do ASTA fica acessível por esse caminho.
* **Túnel** (Cloudflare «quick tunnel», `cloudflared`): cria um endereço `https://….trycloudflare.com` que chega no computador sem abrir porta no
  roteador e sem conta. O ASTA acha o `cloudflared` (ou baixa o binário oficial para a pasta do ASTA, com a sua confirmação) e o liga/desliga.
* No celular, o provedor LM Studio aponta para `https://….trycloudflare.com/lm/<código>`; a API do LM Studio funciona igual (inclusive streaming).

O endereço do túnel muda a cada vez que ele é ligado; o código só muda se você gerar um novo.
"""
from __future__ import annotations

import atexit
import hmac
import http.client
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import tarfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .providers import lmstudio

PREFIX = "/lm/"
ALLOWED = ("v1/", "api/v0/")          # só a API do LM Studio; nenhum outro caminho do ASTA passa por aqui
MAX_BODY = 64 * 1024 * 1024            # imagens em base64 (visão) cabem
URL_RE = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")   # «api.trycloudflare.com» é o servidor da Cloudflare (aparece nas mensagens de erro), não o túnel
_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade", "content-length", "host"}

DOWNLOADS = {   # binário oficial do cloudflared (https://github.com/cloudflare/cloudflared/releases)
    ("linux", "x86_64"): ("cloudflared-linux-amd64", False), ("linux", "aarch64"): ("cloudflared-linux-arm64", False),
    ("windows", "x86_64"): ("cloudflared-windows-amd64.exe", False), ("darwin", "x86_64"): ("cloudflared-darwin-amd64.tgz", True),
    ("darwin", "aarch64"): ("cloudflared-darwin-arm64.tgz", True),
}
DOWNLOAD_BASE = "https://github.com/cloudflare/cloudflared/releases/latest/download/"


def _platform_key() -> tuple:
    sysname = platform.system().lower()
    m = platform.machine().lower()
    arch = "aarch64" if m in ("arm64", "aarch64") else "x86_64" if m in ("x86_64", "amd64") else m
    return sysname, arch


class Remote:
    def __init__(self, home: Path, local_port: int = 0):
        self.home = Path(home)
        self.file = self.home / "remote.json"
        self.bin_dir = self.home / "bin"
        self.local_port = local_port
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self.state = "off"        # off | installing | starting | on | error
        self.url = ""
        self.error = ""
        self._cfg: Dict[str, Any] = {}
        atexit.register(self.stop)   # o túnel nunca sobrevive ao ASTA
        try:
            self._cfg = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._cfg = {}

    # ----- configuração (código secreto e liga/desliga do proxy)
    def _save(self) -> None:
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._cfg), encoding="utf-8")
            os.replace(tmp, self.file)
            try:
                os.chmod(self.file, 0o600)
            except OSError:
                pass
        except OSError:
            pass

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.get("enabled"))

    def set_enabled(self, on: bool) -> None:
        self._cfg["enabled"] = bool(on)
        if on and not self._cfg.get("token"):
            self._cfg["token"] = secrets.token_urlsafe(24)
        self._save()
        if not on:
            self.stop()

    def token(self) -> str:
        if not self._cfg.get("token"):
            self._cfg["token"] = secrets.token_urlsafe(24)
            self._save()
        return str(self._cfg["token"])

    def rotate(self) -> str:
        self._cfg["token"] = secrets.token_urlsafe(24)
        self._save()
        return self.token()

    def token_ok(self, given: str) -> bool:
        return self.enabled and bool(given) and hmac.compare_digest(given.encode(), self.token().encode())

    # ----- cloudflared
    def find_binary(self) -> str:
        exe = shutil.which("cloudflared")
        if exe:
            return exe
        name = "cloudflared.exe" if platform.system().lower() == "windows" else "cloudflared"
        p = self.bin_dir / name
        return str(p) if p.is_file() else ""

    def install(self) -> None:
        """Baixa o binário oficial do cloudflared para a pasta do ASTA (a pedido do usuário). Roda em segundo plano."""
        with self._lock:
            if self.state == "installing":
                return
            self.state, self.error = "installing", ""
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self) -> None:
        try:
            key = _platform_key()
            if key not in DOWNLOADS:
                raise RuntimeError(f"Sem binário oficial para {key[0]}/{key[1]}: instale o cloudflared pelo gerenciador de pacotes do sistema.")
            asset, is_tgz = DOWNLOADS[key]
            self.bin_dir.mkdir(parents=True, exist_ok=True)
            target = self.bin_dir / ("cloudflared.exe" if key[0] == "windows" else "cloudflared")
            tmp = self.bin_dir / (asset + ".part")
            req = urllib.request.Request(DOWNLOAD_BASE + asset, headers={"User-Agent": "ASTA"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            if is_tgz:
                with tarfile.open(tmp) as tf:
                    member = next((m for m in tf.getmembers() if m.isfile() and m.name.rsplit("/", 1)[-1] == "cloudflared"), None)
                    if member is None:
                        raise RuntimeError("Arquivo do cloudflared inesperado.")
                    src = tf.extractfile(member)
                    with open(target, "wb") as out:
                        shutil.copyfileobj(src, out)  # type: ignore[arg-type]
                tmp.unlink(missing_ok=True)
            else:
                os.replace(tmp, target)
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            self.state = "off"
        except Exception as exc:  # noqa: BLE001
            self.state, self.error = "error", f"Não consegui baixar o cloudflared: {exc}"

    # ----- túnel
    def start(self) -> None:
        with self._lock:
            if self.state in ("starting", "on", "installing"):
                return
            exe = self.find_binary()
            if not exe:
                self.state, self.error = "error", "O cloudflared não está instalado: use «Baixar o cloudflared»."
                return
            if not self.local_port:
                self.state, self.error = "error", "Porta do ASTA desconhecida."
                return
            self.state, self.error, self.url = "starting", "", ""
        self.set_enabled(True)
        cmd = [exe, "tunnel", "--no-autoupdate", "--http-host-header", f"127.0.0.1:{self.local_port}", "--url", f"http://127.0.0.1:{self.local_port}"]
        try:
            kw: Dict[str, Any] = {}
            if os.name == "nt":
                kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **kw)
        except OSError as exc:
            self.state, self.error = "error", f"Não consegui iniciar o cloudflared: {exc}"
            return
        threading.Thread(target=self._watch, args=(self._proc,), daemon=True).start()

    def _watch(self, proc: subprocess.Popen) -> None:
        assert proc.stderr is not None
        tail: List[str] = []
        try:
            for line in proc.stderr:   # o cloudflared escreve o endereço do túnel no stderr
                if line.strip():
                    tail = (tail + [line.strip()])[-3:]
                m = URL_RE.search(line)
                if m and self.state == "starting":
                    self.url, self.state = m.group(0), "on"
        except (ValueError, OSError):   # «Desligar» fechou o pipe
            pass
        finally:
            try:
                proc.stderr.close()
            except (ValueError, OSError):
                pass
        if self._proc is proc:     # o processo terminou sozinho (não foi o «Desligar»)
            if self.state != "on":
                why = re.sub(r"^\S+\s+(ERR|INF|WRN)\s+", "", tail[-1])[:200] if tail else ""
                self.error = "O túnel não ficou pronto (sem internet, ou a Cloudflare recusou). Tente de novo." + (f" ({why})" if why else "")
                self.state = "error"
            else:
                self.state = "off"
            self.url, self._proc = "", None

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        self.state, self.url = "off", ""
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                try:
                    proc.kill()
                except OSError:
                    pass

    # ----- estado para a tela
    def status(self) -> Dict[str, Any]:
        link = f"{self.url}{PREFIX}{self.token()}" if self.url and self.enabled else ""
        return {"enabled": self.enabled, "state": self.state, "installed": bool(self.find_binary()), "url": self.url, "link": link, "error": self.error,
                "can_download": _platform_key() in DOWNLOADS}

    def tunnel_active(self) -> bool:
        return self.state == "on" and self._proc is not None

    # ----- proxy
    def lm_root(self, settings: Dict[str, Any]) -> str:
        base = ((settings.get("providers") or {}).get("lmstudio") or {}).get("base_url") or ""
        root = lmstudio.root_url(base)
        host = urllib.parse.urlsplit(root).hostname or ""
        if host and host not in ("127.0.0.1", "localhost", "::1") and not re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", host):
            root = lmstudio.DEFAULT_URL   # nunca vira um repassador para a internet: só o LM Studio do próprio computador ou da rede de casa
        return root

    def handle(self, req: Any, settings: Dict[str, Any]) -> None:
        """Repassa `/lm/<código>/<v1|api/v0>/…` ao LM Studio, devolvendo a resposta aos poucos (streaming)."""
        rest = req.path[len(PREFIX):]
        token, _, sub = rest.partition("/")
        if not self.token_ok(token):
            req.json({"error": "Código inválido ou acesso desligado."}, 403)
            return
        if not sub.startswith(ALLOWED) or ".." in sub:
            req.json({"error": "Caminho não permitido."}, 404)
            return
        n = req.content_length()
        if n > MAX_BODY:
            req.json({"error": "Corpo muito grande."}, 413)
            return
        body = req.rfile.read(n) if n else None
        req._body_read = True
        u = urllib.parse.urlsplit(self.lm_root(settings))
        path = "/" + sub + (("?" + urllib.parse.urlsplit(req.h.path).query) if urllib.parse.urlsplit(req.h.path).query else "")
        headers = {k: v for k, v in req.headers.items() if k.lower() not in _HOP and k.lower() not in ("cookie", "authorization", "origin", "referer", "x-forwarded-for", "forwarded", "x-real-ip")
                   and not k.lower().startswith(("cf-", "x-forwarded"))}
        if body is not None:
            headers["Content-Length"] = str(len(body))
        conn = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=600) if u.scheme == "https" else http.client.HTTPConnection(u.hostname, u.port or 80, timeout=600)
        try:
            conn.request(req.method, path, body=body, headers=headers)
            resp = conn.getresponse()
        except (OSError, http.client.HTTPException) as exc:
            conn.close()
            req.json({"error": f"LM Studio não respondeu: {exc}"}, 502)
            return
        h = req.h
        h.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() not in _HOP:
                h.send_header(k, v)
        h.send_header("Cache-Control", "no-store")
        h.send_header("Connection", "close")
        h.end_headers()
        try:
            if req.method != "HEAD":
                while True:
                    chunk = resp.read1(8192) if hasattr(resp, "read1") else resp.read(8192)
                    if not chunk:
                        break
                    h.wfile.write(chunk)
                    h.wfile.flush()
        finally:
            conn.close()
            h.close_connection = True
        req._sse = True   # a resposta já foi enviada: nenhum tratamento de erro pode escrever de novo
