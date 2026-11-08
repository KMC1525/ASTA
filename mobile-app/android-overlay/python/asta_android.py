"""Motor do ASTA dentro do app Android (v0.14): o app NÃO depende do ASTA do computador.

O Chaquopy roda o Python do app; este módulo liga o servidor do ASTA em 127.0.0.1 (porta livre a partir de 8787), com a pasta de dados privada do app, e o WebView abre a interface
nesse endereço. É o MESMO ASTA do computador (mesmo código Python, mesma interface, mesmos provedores de IA, busca na web, mundos 3D, avatars, jogos 2D, Canvas e Studio), então
tudo que não precisa de um programa que o Android não tem funciona sem computador. Modelos locais pesados (GGUF/PyTorch) e programas externos (ffmpeg) dependem do aparelho:
o app usa o `libffmpeg.so`/`libffprobe.so` se o APK os trouxer, e modelos de um servidor local (Ollama, LM Studio) na rede continuam funcionando como provedores.

Segurança: no Android qualquer app do aparelho alcança 127.0.0.1; por isso o servidor roda em modo estrito (ASTA_STRICT_LOOPBACK=1): só quem tem o cookie de pareamento, que o app
conhece pelo código guardado na pasta privada dele, entra.
"""
from __future__ import annotations

import os
import threading

_STATE = {}
_LOCK = threading.Lock()


def _link_tools(files_dir: str, native_lib_dir: str) -> None:
    """Se o APK trouxe o ffmpeg/ffprobe como bibliotecas nativas (libffmpeg.so, libffprobe.so), expõe-os como programas `ffmpeg`/`ffprobe` no PATH do ASTA."""
    if not native_lib_dir:
        return
    bindir = os.path.join(files_dir, "bin")
    for name in ("ffmpeg", "ffprobe"):
        lib = os.path.join(native_lib_dir, f"lib{name}.so")
        if not os.path.isfile(lib):
            continue
        os.makedirs(bindir, exist_ok=True)
        link = os.path.join(bindir, name)
        try:
            if os.path.lexists(link):
                os.unlink(link)
            os.symlink(lib, link)
        except OSError:
            continue
    if os.path.isdir(bindir):
        os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")


def start(files_dir: str, native_lib_dir: str = "") -> str:
    """Liga o ASTA (uma vez por processo) e devolve o endereço que o WebView deve abrir: o de pareamento, que grava o cookie do app e segue para a interface."""
    with _LOCK:
        if _STATE.get("pair"):
            return _STATE["pair"]
        home = os.path.join(files_dir, "asta")
        os.makedirs(home, exist_ok=True)
        os.environ.update({"ASTA_HOME": home, "ASTA_NO_UPDATE": "1", "ASTA_ANDROID": "1", "ASTA_STRICT_LOOPBACK": "1", "ASTA_NO_NATIVE_FETCH": "1", "ASTA_LANG": os.environ.get("ASTA_LANG", "")})
        lib = os.path.join(native_lib_dir, "libasta_core.so") if native_lib_dir else ""
        if lib and os.path.isfile(lib):
            os.environ["ASTA_NATIVE_LIB"] = lib   # núcleo Rust compilado para o Android (arm64/x86_64)
        _link_tools(files_dir, native_lib_dir)
        from asta.server import make_server
        from asta.storage import Store

        store = Store(home)
        httpd = app = None
        port = 0
        for candidate in range(8787, 8830):
            try:
                httpd, app = make_server("127.0.0.1", candidate, store)
                port = candidate
                break
            except OSError:
                continue
        if httpd is None:
            raise RuntimeError("Nenhuma porta livre entre 8787 e 8829 para o ASTA deste aparelho.")
        threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.3}, name="asta-http", daemon=True).start()
        _STATE.update(port=port, httpd=httpd, app=app, store=store, pair=f"http://127.0.0.1:{port}/api/mobile/pair?code={app.mobile.token()}")
        return _STATE["pair"]


def stop() -> None:
    with _LOCK:
        httpd = _STATE.pop("httpd", None)
        _STATE.clear()
    if httpd is not None:
        httpd.shutdown()
        httpd.server_close()
