"""Linha de comando do ASTA:  asta [run|update|doctor|version]"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
import webbrowser

from . import __version__

REPO_ZIP = "https://github.com/KMC1525/ASTA/archive/refs/heads/main.zip"
BANNER = r"""
   ___   ______ _____  ___
  / _ | / __/_  __/ / _ |
 / __ |_\ \  / /   / __ |
/_/ |_/___/ /_/   /_/ |_|   v{version}
"""


def _run(args: argparse.Namespace) -> int:
    if args.home:
        os.environ["ASTA_HOME"] = args.home
    from .server import make_server
    from .storage import Store

    store = Store()
    httpd = None
    port = args.port
    for candidate in range(port, port + 20):
        try:
            httpd, app = make_server(args.host, candidate, store)
            port = candidate
            break
        except OSError:
            continue
    if httpd is None:
        print(f"Não foi possível abrir nenhuma porta entre {args.port} e {args.port + 19}.", file=sys.stderr)
        return 1
    shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0", "::") else args.host
    url = f"http://{shown}:{port}/"
    print(BANNER.format(version=__version__))
    print(f"  WebUI:   {url}")
    print(f"  Dados:   {store.home}")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("  ⚠  Escutando fora do localhost: qualquer pessoa na sua rede poderá usar o ASTA e suas chaves de API.")
    print("  Pare com Ctrl+C.\n")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\nAté logo!")
    finally:
        httpd.server_close()
    return 0


def _update(_args: argparse.Namespace) -> int:
    print("Atualizando o ASTA…")
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", REPO_ZIP]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print("Pronto! Reinicie o ASTA para usar a nova versão.")
    return res.returncode


def _doctor(_args: argparse.Namespace) -> int:
    from .util import asta_home, hardware_info

    hw = hardware_info(refresh=True)
    print(f"ASTA {__version__}")
    print(f"Python {hw['python']} · {hw['os']} {hw['arch']}")
    print(f"CPU: {hw['cpus']} núcleos · RAM: {hw['ram_gb']} GB · GPU: {hw['gpu'] or 'não detectada (NVIDIA)'}")
    print(f"Nível de hardware: {hw['tier']}")
    print(f"ffmpeg: {'sim' if hw['ffmpeg'] else 'não (opcional: análise de vídeo/áudio)'}")
    print(f"Pasta de dados: {asta_home()}")
    try:
        import llama_cpp  # type: ignore  # noqa: F401

        print("Modelos locais embutidos (llama-cpp-python): disponível")
    except ImportError:
        print('Modelos locais embutidos: não instalado (opcional: pip install "asta[local]")')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="asta", description="ASTA — mundos virtuais jogáveis com personagens de IA")
    sub = parser.add_subparsers(dest="cmd")
    run = sub.add_parser("run", help="inicia a WebUI (padrão)")
    for p in (parser, run):
        p.add_argument("--host", default="127.0.0.1", help="endereço (padrão 127.0.0.1)")
        p.add_argument("--port", type=int, default=8787, help="porta (padrão 8787)")
        p.add_argument("--no-browser", action="store_true", help="não abrir o navegador")
        p.add_argument("--home", help="pasta de dados (padrão ~/.asta)")
    sub.add_parser("update", help="atualiza o ASTA para a versão mais recente")
    sub.add_parser("doctor", help="mostra diagnóstico do ambiente")
    sub.add_parser("version", help="mostra a versão")
    args = parser.parse_args(argv)
    if args.cmd == "update":
        return _update(args)
    if args.cmd == "doctor":
        return _doctor(args)
    if args.cmd == "version":
        print(__version__)
        return 0
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
