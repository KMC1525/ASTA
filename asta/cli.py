"""Linha de comando do ASTA:  asta [run|update|libs|doctor|version]"""
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


# Bibliotecas opcionais do ASTA (extras do pacote): nome → para que servem. A ordem é da mais leve para a mais pesada.
LIBS = {
    "docs": "extração de PDFs mais precisa",
    "media": "modelos locais de imagem, vídeo, som e voz do Canvas (PyTorch, diffusers, transformers — vários GB)",
    "local": "modelos de linguagem GGUF embutidos (llama-cpp-python; compila código nativo)",
}


def _wanted_libs(spec: str):
    """Extras escolhidos: "" ou "all" = todos; "none" = nenhum; ou uma lista separada por vírgula. Devolve (lista, desconhecidos)."""
    spec = (spec or os.environ.get("ASTA_EXTRAS") or "all").strip().lower()
    if spec in ("none", "core", "no", "0"):
        return [], []
    names = [x.strip() for x in spec.replace(";", ",").split(",") if x.strip()]
    if "all" in names:
        return list(LIBS), []
    return [n for n in LIBS if n in names], [n for n in names if n not in LIBS]


def _lib_requirements(extra: str):
    """Requisitos pip de um extra, lidos dos metadados do ASTA instalado (sempre os da versão atual)."""
    import re
    from importlib import metadata

    out = []
    for line in metadata.requires("asta") or []:
        req, _, marker = line.partition(";")
        if re.search(r"extra\s*==\s*[\"']%s[\"']" % re.escape(extra), marker):
            out.append(req.strip())
    return out


def _libs(args: argparse.Namespace) -> int:
    """Instala/atualiza as bibliotecas opcionais do ASTA. Uma que falhe não impede as outras."""
    chosen, unknown = _wanted_libs(getattr(args, "extras", "") or "")
    if unknown:
        print(f"Bibliotecas desconhecidas: {', '.join(unknown)}. Opções: {', '.join(LIBS)}, all, none.", file=sys.stderr)
        return 2
    if not chosen:
        print("Bibliotecas opcionais: nada a instalar (ASTA_EXTRAS=none).")
        return 0
    failed = []
    for extra in chosen:
        reqs = _lib_requirements(extra)
        if not reqs:
            print(f"Bibliotecas «{extra}»: nenhuma listada nesta versão — pulando.")
            continue
        print(f"\nBibliotecas «{extra}» ({LIBS[extra]}): {', '.join(reqs)}")
        res = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--upgrade-strategy", "eager", "--disable-pip-version-check", *reqs])
        if res.returncode != 0:
            failed.append(extra)
            print(f"⚠  Não foi possível instalar «{extra}». O ASTA funciona sem ela; tente de novo depois com:  asta libs --extras {extra}")
    ok = [e for e in chosen if e not in failed]
    print("\nBibliotecas atualizadas: " + (", ".join(ok) or "nenhuma") + (f" · com falha: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


def _update(args: argparse.Namespace) -> int:
    """Atualiza o ASTA e todas as bibliotecas dele (use --core para atualizar só o ASTA)."""
    print("Atualizando o ASTA…")
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", REPO_ZIP]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        return res.returncode
    if not getattr(args, "core", False):
        # processo novo: lê os metadados da versão recém-instalada (ela pode ter bibliotecas novas)
        lib_cmd = [sys.executable, "-m", "asta", "libs"] + (["--extras", args.extras] if getattr(args, "extras", "") else [])
        subprocess.run(lib_cmd)  # falhas de bibliotecas opcionais viram aviso; o ASTA já está atualizado
    print("\nPronto! Reinicie o ASTA para usar a nova versão.")
    return 0


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
    libs = []
    for mod in ("torch", "diffusers", "transformers"):
        try:
            __import__(mod)
            libs.append(mod)
        except ImportError:
            pass
    if len(libs) == 3:
        print("Modelos locais de mídia do Canvas (torch, diffusers, transformers): disponível")
    else:
        print('Modelos locais de mídia do Canvas: não instalado (opcional: pip install "asta[media]")')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="asta", description="ASTA — central open source de criação com IA: mundos 3D, avatars, jogos 2D e Canvas de mídia")
    sub = parser.add_subparsers(dest="cmd")
    run = sub.add_parser("run", help="inicia a WebUI (padrão)")
    for p in (parser, run):
        p.add_argument("--host", default="127.0.0.1", help="endereço (padrão 127.0.0.1)")
        p.add_argument("--port", type=int, default=8787, help="porta (padrão 8787)")
        p.add_argument("--no-browser", action="store_true", help="não abrir o navegador")
        p.add_argument("--home", help="pasta de dados (padrão ~/.asta)")
    upd = sub.add_parser("update", help="atualiza o ASTA e todas as bibliotecas dele para a versão mais recente")
    upd.add_argument("--core", action="store_true", help="atualiza só o ASTA, sem as bibliotecas opcionais")
    upd.add_argument("--extras", default="", help="bibliotecas a atualizar: all (padrão), none ou lista (docs,media,local)")
    libs = sub.add_parser("libs", help="instala/atualiza as bibliotecas opcionais do ASTA (docs, media, local)")
    libs.add_argument("--extras", default="", help="all (padrão), none ou lista separada por vírgula (docs,media,local)")
    sub.add_parser("doctor", help="mostra diagnóstico do ambiente")
    sub.add_parser("version", help="mostra a versão")
    args = parser.parse_args(argv)
    if args.cmd == "update":
        return _update(args)
    if args.cmd == "libs":
        return _libs(args)
    if args.cmd == "doctor":
        return _doctor(args)
    if args.cmd == "version":
        print(__version__)
        return 0
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
