"""Linha de comando do ASTA:  asta [run|update|libs|models|doctor|version]"""
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
    "local": "modelos GGUF embutidos: texto, imagem e vídeo (llama-cpp-python e stable-diffusion-cpp-python; compilam código nativo)",
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


def _req_name(req: str) -> str:
    import re

    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", req)
    return m.group(1) if m else req.strip()


def _installed_version(req: str):
    """Versão instalada da biblioteca de um requisito pip, ou None se ela não está neste ambiente."""
    from importlib import metadata

    try:
        return metadata.version(_req_name(req))
    except Exception:  # noqa: BLE001  (PackageNotFoundError e metadados quebrados)
        return None


def _libs(args: argparse.Namespace) -> int:
    """Instala o que falta e atualiza (só se houver versão mais nova) as bibliotecas opcionais do ASTA. Uma que falhe não impede as outras.
    O que já está instalado não é instalado de novo: o pip só mexe nele se existir uma versão mais nova."""
    chosen, unknown = _wanted_libs(getattr(args, "extras", "") or "")
    if unknown:
        print(f"Bibliotecas desconhecidas: {', '.join(unknown)}. Opções: {', '.join(LIBS)}, all, none.", file=sys.stderr)
        return 2
    if not chosen:
        print("Bibliotecas opcionais: nada a instalar (ASTA_EXTRAS=none).")
        return 0
    failed, present = [], []
    for extra in chosen:
        reqs = _lib_requirements(extra)
        if not reqs:
            print(f"Bibliotecas «{extra}»: nenhuma listada nesta versão — pulando.")
            continue
        have = {r: _installed_version(r) for r in reqs}
        missing = [r for r in reqs if not have[r]]
        base = [sys.executable, "-m", "pip", "install", "--upgrade", "--upgrade-strategy", "eager", "--disable-pip-version-check"]
        if not missing:
            print(f"\nBibliotecas «{extra}» ({LIBS[extra]}): já instaladas ({', '.join(f'{_req_name(r)} {v}' for r, v in have.items())}) — só atualizo se houver versão mais nova.")
            res = subprocess.run([*base, "--quiet", *reqs])
            if res.returncode != 0:
                print(f"⚠  Não consegui verificar atualizações de «{extra}» agora (sem internet?); sigo com as versões instaladas.")
            present.append(extra)
            continue
        ok_now = [r for r in reqs if have[r]]
        print(f"\nBibliotecas «{extra}» ({LIBS[extra]}): instalando {', '.join(missing)}" + (f" · já instaladas (só atualizo se precisar): {', '.join(ok_now)}" if ok_now else ""))
        res = subprocess.run([*base, *reqs])
        if res.returncode != 0:
            failed.append(extra)
            print(f"⚠  Não foi possível instalar «{extra}». O ASTA funciona sem ela; tente de novo depois com:  asta libs --extras {extra}")
    ok = [e for e in chosen if e not in failed]
    print("\nBibliotecas prontas: " + (", ".join(ok) or "nenhuma") + (f" (já estavam instaladas: {', '.join(present)})" if present else "")
          + (f" · com falha: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


RAW = "https://raw.githubusercontent.com/KMC1525/ASTA/main/"


def _version_tuple(v: str):
    import re

    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4])


def _remote_version(timeout: float = 20.0):
    """Versão do ASTA publicada na branch principal (ASTA_VERSION_URL troca o endereço), ou None se não deu para consultar."""
    import re
    import urllib.request

    try:
        with urllib.request.urlopen(os.environ.get("ASTA_VERSION_URL") or RAW + "asta/__init__.py", timeout=timeout) as resp:
            m = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", resp.read(8192).decode("utf-8", "replace"))
        return m.group(1) if m else None
    except Exception:  # noqa: BLE001
        return None


def _asta_is_current(force: bool = False) -> bool:
    """True se o ASTA instalado já é a versão publicada (ou mais nova): nesse caso não há o que baixar nem reinstalar."""
    if force or os.environ.get("ASTA_FORCE", "") not in ("", "0"):
        return False
    remote = _remote_version()
    return bool(remote) and _version_tuple(remote) <= _version_tuple(__version__)


def _managed_app_dir():
    """Pasta do programa se este ASTA foi instalado pelo instalador oficial (…/app/venv); None se foi instalado à mão (pip, editável)."""
    from pathlib import Path

    prefix = Path(sys.prefix).resolve()
    if prefix.name != "venv":
        return None
    default = (Path(os.environ["LOCALAPPDATA"]) / "ASTA" / "app") if os.name == "nt" and os.environ.get("LOCALAPPDATA") else Path.home() / ".asta" / "app"
    app = Path(os.environ.get("ASTA_APP_DIR") or default).expanduser().resolve()
    return app if prefix == app / "venv" else None


def _update_with_installer(args: argparse.Namespace) -> int:
    """Roda o instalador oficial: ele atualiza o Python (e o pip/setuptools/wheel), o ASTA e as bibliotecas — o mesmo que o comando de instalação.
    Devolve o código de saída, ou -1 se não foi possível usar o instalador (sem internet, instalação manual…)."""
    import tempfile
    import urllib.request

    app = _managed_app_dir()
    if app is None:
        print("Este ASTA não foi instalado pelo instalador oficial: o Python do sistema não é gerenciado por ele (atualize-o pelo gerenciador de pacotes do seu sistema).")
        return -1
    windows = os.name == "nt"
    name = "install.ps1" if windows else "install.sh"
    try:
        with urllib.request.urlopen(RAW + name, timeout=30) as resp:
            script = resp.read()
    except Exception as exc:  # noqa: BLE001
        print(f"Não foi possível baixar o instalador ({exc}); atualizando só o ASTA e as bibliotecas.")
        return -1
    env = dict(os.environ, ASTA_APP_DIR=str(app))
    if getattr(args, "force", False):
        env["ASTA_FORCE"] = "1"
    if getattr(args, "core", False):
        env["ASTA_EXTRAS"] = "none"
    elif getattr(args, "extras", ""):
        env["ASTA_EXTRAS"] = args.extras
    with tempfile.NamedTemporaryFile("wb", suffix=os.path.splitext(name)[1], delete=False) as fh:
        fh.write(script)
        path = fh.name
    if windows:
        # o instalador recria arquivos que este processo está usando: ele continua numa janela nova, depois que o asta.exe terminar
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path], env=env, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        print("A atualização continua numa nova janela (Python, ASTA e bibliotecas). Quando terminar, abra o ASTA de novo.")
        return 0
    try:
        return subprocess.run(["sh", path], env=env).returncode
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


YES = ("s", "sim", "y", "yes")
NO = ("", "n", "nao", "não", "no")


def _ask_terminal(question: str):
    """Pergunta sim/não no terminal e devolve True/False; None se não há um terminal para perguntar. Funciona também com `curl … | sh`,
    em que o stdin é o próprio script: nesse caso lê do terminal de verdade (/dev/tty, ou CONIN$ no Windows). Enter = não."""
    stream, opened = None, None
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            stream = sys.stdin
        else:
            opened = stream = open("CONIN$" if os.name == "nt" else "/dev/tty", "r", encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    try:
        print(f"\n{question} [s/N] ", end="", flush=True)
        for _ in range(3):
            line = stream.readline()
            if not line:  # fim da entrada: ninguém para responder
                print()
                return None
            answer = line.strip().lower()
            if answer in YES:
                return True
            if answer in NO:
                return False
            print("Responda s (sim) ou n (não): ", end="", flush=True)
        return False
    finally:
        if opened is not None:
            opened.close()


def _models(args: argparse.Namespace) -> int:
    """`asta models list|install`: os modelos locais pré-instalados (texto e imagem). `install --ask` pergunta (sim/não) antes de baixar;
    com ASTA_MODELS definido (all, text, image…) a resposta já foi dada e não pergunta."""
    if getattr(args, "home", None):
        os.environ["ASTA_HOME"] = args.home
    from . import preinstalled
    from .storage import Store

    store = Store()
    if args.action == "list":
        for m in preinstalled.status(store.models_dir):
            print(f"{'✓' if m['installed'] else '·'} {m['id']:<26} {m['kind']:<6} {m['label']} ({m['quant']}) · {m['size'] / 1024 ** 3:.1f} GB · {m['repo']}")
        return 0
    token = (store.get_settings().get("hf") or {}).get("token", "")
    explicit = args.which or os.environ.get("ASTA_MODELS") or ""
    ask = _ask_terminal if getattr(args, "ask", False) and not explicit else None
    return preinstalled.install_selected(store, explicit or "all", token, ask=ask)


def _update(args: argparse.Namespace) -> int:
    """Atualiza o Python, o ASTA e todas as bibliotecas dele — só o que ainda não está instalado ou tem versão mais nova. --core: só o ASTA e as ferramentas do Python; --no-python: sem mexer no Python."""
    if not getattr(args, "no_python", False) and not getattr(args, "core", False) and os.environ.get("ASTA_PYTHON", "auto") != "keep":
        print("Atualizando o Python, o ASTA e as bibliotecas dele…")
        code = _update_with_installer(args)
        if code >= 0:
            if code == 0 and os.name != "nt":
                print("\nPronto! Reinicie o ASTA para usar a nova versão.")
            return code
    print("Verificando as ferramentas do Python e o ASTA…")
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", "--disable-pip-version-check", "pip", "setuptools", "wheel"])  # já atualizadas = nada a fazer; falha = aviso
    if _asta_is_current(getattr(args, "force", False)):
        print(f"ASTA {__version__} já é a versão mais recente — nada a baixar. (Para reinstalar mesmo assim: asta update --force)")
    else:
        res = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", REPO_ZIP])
        if res.returncode != 0:
            return res.returncode
    if not getattr(args, "core", False):
        # processo novo: lê os metadados da versão recém-instalada (ela pode ter bibliotecas novas)
        lib_cmd = [sys.executable, "-m", "asta", "libs"] + (["--extras", args.extras] if getattr(args, "extras", "") else [])
        subprocess.run(lib_cmd)  # falhas de bibliotecas opcionais viram aviso; o ASTA já está atualizado
        subprocess.run([sys.executable, "-m", "asta", "models", "install", "--ask"])  # modelos pré-instalados: pergunta antes de baixar (pula o que já existe)
    print("\nPronto! Reinicie o ASTA para usar a nova versão.")
    return 0


def _doctor(_args: argparse.Namespace) -> int:
    from .util import asta_home, hardware_info

    hw = hardware_info(refresh=True)
    print(f"ASTA {__version__}")
    print(f"Python {hw['python']} · {hw['os']} {hw['arch']}")
    print(f"CPU: {hw['cpus']} núcleos · RAM: {hw['ram_gb']} GB · GPU: {hw['gpu'] or 'não detectada (NVIDIA)'}")
    print(f"Nível de hardware: {hw['tier']}")
    try:
        from importlib import metadata

        print(f"pip {metadata.version('pip')} · setuptools {metadata.version('setuptools')}")
    except Exception:  # noqa: BLE001
        print("pip: não encontrado neste ambiente")
    print(f"ffmpeg: {'sim' if hw['ffmpeg'] else 'não (opcional: análise de vídeo/áudio)'}")
    print(f"Pasta de dados: {asta_home()}")
    try:
        import llama_cpp  # type: ignore  # noqa: F401

        print("Modelos locais embutidos (llama-cpp-python): disponível")
    except ImportError:
        print('Modelos locais embutidos: não instalado (opcional: pip install "asta[local]")')
    try:
        from .providers import lmstudio

        lm = lmstudio.probe(timeout=1.5)
        if lm["running"]:
            print(f"LM Studio: rodando em {lm['url']} · modelo carregado: {', '.join(lm['loaded']) or 'nenhum (carregue um no LM Studio)'}")
        else:
            print("LM Studio: não detectado em " + lm["url"] + " (opcional: abra o LM Studio e ligue o servidor em Developer → Start Server)")
    except Exception:  # noqa: BLE001
        pass
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
    upd = sub.add_parser("update", help="atualiza o Python, o ASTA e todas as bibliotecas dele para a versão mais recente")
    upd.add_argument("--core", action="store_true", help="atualiza só o ASTA (e pip/setuptools/wheel), sem o Python do sistema nem as bibliotecas opcionais")
    upd.add_argument("--no-python", action="store_true", help="não atualiza o Python do sistema (atualiza o ASTA, o pip e as bibliotecas)")
    upd.add_argument("--extras", default="", help="bibliotecas a atualizar: all (padrão), none ou lista (docs,media,local)")
    upd.add_argument("--force", action="store_true", help="reinstala o ASTA mesmo que já esteja na versão mais recente")
    mod = sub.add_parser("models", help="modelos locais pré-instalados (texto e imagem): list | install")
    mod.add_argument("action", choices=("list", "install"), nargs="?", default="list")
    mod.add_argument("--which", default="", help="all (padrão), none, text, image ou ids (também ASTA_MODELS)")
    mod.add_argument("--ask", action="store_true", help="pergunta no terminal (sim/não) antes de baixar o que falta; sem efeito se --which ou ASTA_MODELS já disseram o que fazer")
    mod.add_argument("--home", help="pasta de dados (padrão ~/.asta)")
    libs = sub.add_parser("libs", help="instala/atualiza as bibliotecas opcionais do ASTA (docs, media, local)")
    libs.add_argument("--extras", default="", help="all (padrão), none ou lista separada por vírgula (docs,media,local)")
    sub.add_parser("doctor", help="mostra diagnóstico do ambiente")
    sub.add_parser("version", help="mostra a versão")
    args = parser.parse_args(argv)
    if args.cmd == "update":
        return _update(args)
    if args.cmd == "models":
        return _models(args)
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
