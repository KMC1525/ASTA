"""Linha de comando do ASTA:  asta [run|update|libs|models|doctor|version]"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

from . import __version__
from .termi18n import _, system_lang

REPO_ZIP = "https://github.com/KMC1525/ASTA/archive/refs/heads/main.zip"
BANNER = r"""
   ___   ______ _____  ___
  / _ | / __/_  __/ / _ |
 / __ |_\ \  / /   / __ |
/_/ |_/___/ /_/   /_/ |_|   v{version}
"""


def _windows() -> bool:
    return os.name == "nt"


def _auto_update(args: argparse.Namespace, argv) -> object:
    """Ao abrir o ASTA pelo comando `asta`: atualiza/instala tudo como o comando de instalação (Python, ASTA, bibliotecas, modelos pré-instalados).
    Roda quando há versão nova publicada e, mesmo sem ela, a cada ASTA_UPDATE_EVERY horas (padrão 24; 0 = a cada abertura) — o instalador pula o que já está em dia.
    Só vale para o ASTA instalado pelo instalador oficial (instalação manual/editável nunca é mexida); sem internet, abre normalmente.
    Devolve None para seguir abrindo; um número para encerrar com esse código (Windows: o instalador continua numa janela nova)."""
    import time
    from pathlib import Path

    if getattr(args, "no_update", False) or os.environ.get("ASTA_NO_UPDATE", "") not in ("", "0"):
        return None
    if _managed_app_dir() is None:
        if os.environ.get("ASTA_INSTALLER"):   # instalador do Windows / AppImage: não se atualizam sozinhos, mas avisam (uma linha) quando há versão nova
            remote = _remote_version(timeout=4.0)
            if remote and _version_tuple(remote) > _version_tuple(__version__):
                print(_("Há uma versão nova do ASTA ({v}). Para atualizar: asta update  (ou baixe o instalador novo em https://github.com/KMC1525/ASTA/releases/latest)", v=remote) + "\n")
        return None
    home = Path(args.home or os.environ.get("ASTA_HOME") or Path.home() / ".asta").expanduser()
    stamp = home / ".last-update"
    try:
        hours = float(os.environ.get("ASTA_UPDATE_EVERY", "24"))
    except ValueError:
        hours = 24.0
    remote = _remote_version(timeout=6.0)
    if remote is None:  # sem internet (ou GitHub fora do ar): abre do jeito que está
        return None
    newer = _version_tuple(remote) > _version_tuple(__version__)
    try:
        due = time.time() - stamp.stat().st_mtime >= hours * 3600
    except OSError:
        due = True
    if not newer and not due:
        return None
    print(f"ASTA {__version__}: " + (_("há uma versão nova ({v}). ", v=remote) if newer else _("verificando atualizações. ")) + _("Atualizando o Python, o ASTA e as bibliotecas (para pular: asta --no-update)…"))
    code = _update_with_installer(argparse.Namespace(force=False, core=False, extras="", no_python=False, rust=""))
    if code != 0:
        print(_("Não foi possível atualizar agora; abrindo o ASTA como está."))
        return None
    try:
        home.mkdir(parents=True, exist_ok=True)
        stamp.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass
    if _windows():
        return 0  # o instalador segue numa janela nova e o ASTA precisa estar fechado para ele trocar os arquivos
    print("\n" + _("Abrindo o ASTA atualizado…") + "\n")
    sys.stdout.flush()
    os.execve(sys.executable, [sys.executable, "-m", "asta", *list(argv)], dict(os.environ, ASTA_NO_UPDATE="1"))
    return None  # pragma: no cover


def _print_mobile_qr(app, port: int) -> None:
    from . import qr

    info = app.mobile.info(port)
    if not info["pair_urls"]:
        print(_("  Celular: não encontrei uma rede local (Wi-Fi/Ethernet) neste computador."))
        return
    print("\n" + _("  Celular ou tablet: escaneie com a câmera para instalar e parear o app ASTA") + "\n")
    print("\n".join("    " + line for line in qr.terminal(info["pair_urls"][0]).splitlines()))
    print("\n" + _("  (o aparelho precisa estar na mesma rede Wi-Fi; endereço: {u})", u=info["urls"][0]))


def _run(args: argparse.Namespace) -> int:
    if args.home:
        os.environ["ASTA_HOME"] = args.home
    from . import native
    from .server import make_server
    from .storage import Store

    if not getattr(args, "no_update", False):
        native.ensure()   # núcleo Rust obrigatório: sem ele, baixa a biblioteca pré-compilada em segundo plano (sem compilador, no máximo 1 vez por dia)
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
        print(_("Não foi possível abrir nenhuma porta entre {a} e {b}.", a=args.port, b=args.port + 19), file=sys.stderr)
        return 1
    shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0", "::") else args.host
    url = f"http://{shown}:{port}/"
    print(BANNER.format(version=__version__))
    print(f"  WebUI:   {url}")
    print(_("  Dados:   {p}", p=store.home))
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(_("  Rede:    só aparelhos pareados por QR code entram (o computador local não precisa parear)."))
        _print_mobile_qr(app, port)
    else:
        print(_("  Celular: rode «asta mobile» para usar o ASTA no celular ou tablet (QR code)."))
    print(_("  Pare com Ctrl+C.") + "\n")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\n" + _("Até logo!"))
    finally:
        httpd.server_close()
    return 0


# Bibliotecas opcionais do ASTA (extras do pacote): nome → para que servem. A ordem é da mais leve para a mais pesada.
LIBS = {
    "docs": "extração de PDFs mais precisa",
    "media": "modelos locais de imagem, vídeo, som e voz do Canvas (PyTorch, diffusers, transformers — vários GB)",
    "local": "modelos GGUF embutidos: texto, imagem e vídeo (llama-cpp-python e stable-diffusion-cpp-python; compilam código nativo)",
}


def _lib_desc(extra: str) -> str:
    return _(LIBS[extra])


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


def _ensure_pip() -> bool:
    """O Python embutido do instalador do Windows não traz o pip: instala (ensurepip ou, se faltar, o get-pip.py oficial). True se o pip está disponível."""
    import importlib.util

    if importlib.util.find_spec("pip") is not None:
        return True
    print(_("Instalando o pip neste Python (uma vez) …"))
    try:
        import ensurepip  # noqa: F401

        if subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], capture_output=True).returncode == 0:
            return True
    except ImportError:
        pass
    import tempfile
    import urllib.request

    from .util import ssl_context

    try:
        with urllib.request.urlopen("https://bootstrap.pypa.io/get-pip.py", timeout=60, context=ssl_context()) as resp:
            data = resp.read()
        with tempfile.NamedTemporaryFile("wb", suffix=".py", delete=False) as fh:
            fh.write(data)
            path = fh.name
        try:
            return subprocess.run([sys.executable, path, "--no-warn-script-location", "--disable-pip-version-check"]).returncode == 0
        finally:
            os.unlink(path)
    except Exception as exc:  # noqa: BLE001  (sem internet…)
        print(_("Não consegui instalar o pip ({e}). Sem ele não dá para instalar bibliotecas opcionais nem atualizar por aqui; baixe o instalador novo em https://github.com/KMC1525/ASTA/releases/latest", e=str(exc)[:120]))
        return False


def _sd_cli_install() -> int:
    """`asta libs --sd-cli`: baixa o sd-cli pré-compilado da stable-diffusion.cpp (sem git nem compilador) para a pasta de dados."""
    from .canvas import sdcli
    from .providers import ProviderError

    last = [0.0]

    def progress(done: int, total: int) -> None:
        if total and time.time() - last[0] > 2:
            last[0] = time.time()
            print("  " + _("{p}% baixado", p=int(100 * done / total)), flush=True)

    try:
        exe = sdcli.install(progress, lambda: False, lambda m: print(m, flush=True))
    except ProviderError as exc:
        print("⚠  " + str(exc), file=sys.stderr)
        return 1
    print(_("sd-cli instalado em {p}. O Canvas o usa nos modelos que a biblioteca Python não reconhece.", p=exe))
    return 0


def _libs(args: argparse.Namespace) -> int:
    """Instala o que falta e atualiza (só se houver versão mais nova) as bibliotecas opcionais do ASTA. Uma que falhe não impede as outras.
    O que já está instalado não é instalado de novo: o pip só mexe nele se existir uma versão mais nova."""
    if getattr(args, "sd_cli", False):
        return _sd_cli_install()
    chosen, unknown = _wanted_libs(getattr(args, "extras", "") or "")
    sd_force = bool(getattr(args, "sd_latest", False))
    if unknown:
        print(_("Bibliotecas desconhecidas: {u}. Opções: {o}, all, none.", u=", ".join(unknown), o=", ".join(LIBS)), file=sys.stderr)
        return 2
    if not chosen and not sd_force:
        print(_("Bibliotecas opcionais: nada a instalar (ASTA_EXTRAS=none)."))
        return 0
    if not _ensure_pip():
        return 1
    failed, present = [], []
    for extra in chosen:
        reqs = _lib_requirements(extra)
        if not reqs:
            print(_("Bibliotecas «{x}»: nenhuma listada nesta versão — pulando.", x=extra))
            continue
        have = {r: _installed_version(r) for r in reqs}
        missing = [r for r in reqs if not have[r]]
        base = [sys.executable, "-m", "pip", "install", "--upgrade", "--upgrade-strategy", "eager", "--disable-pip-version-check"]
        if not missing:
            print("\n" + _("Bibliotecas «{x}» ({d}): já instaladas ({v}) — só atualizo se houver versão mais nova.", x=extra, d=_lib_desc(extra), v=", ".join(f"{_req_name(r)} {v}" for r, v in have.items())))
            res = subprocess.run([*base, "--quiet", *reqs])
            if res.returncode != 0:
                print(_("⚠  Não consegui verificar atualizações de «{x}» agora (sem internet?); sigo com as versões instaladas.", x=extra))
            present.append(extra)
            continue
        ok_now = [r for r in reqs if have[r]]
        print("\n" + _("Bibliotecas «{x}» ({d}): instalando {m}", x=extra, d=_lib_desc(extra), m=", ".join(missing)) + (_(" · já instaladas (só atualizo se precisar): {k}", k=", ".join(ok_now)) if ok_now else ""))
        res = subprocess.run([*base, *reqs])
        if res.returncode != 0:
            failed.append(extra)
            print(_("⚠  Não foi possível instalar «{x}». O ASTA funciona sem ela; tente de novo depois com:  asta libs --extras {x}", x=extra))
    if ("local" in chosen or sd_force) and not _sd_latest(sd_force):
        failed.append("local (stable-diffusion.cpp mais nova)")
    if not chosen:   # só a stable-diffusion.cpp (botão do Canvas): sem o resumo das outras bibliotecas
        return 1 if failed else 0
    ok = [e for e in chosen if e not in failed]
    print("\n" + _("Bibliotecas prontas: {l}", l=", ".join(ok) or _("nenhuma")) + (_(" (já estavam instaladas: {p})", p=", ".join(present)) if present else "")
          + (_(" · com falha: {f}", f=", ".join(failed)) if failed else ""))
    return 1 if failed else 0


SD_GIT = "stable-diffusion-cpp-python @ git+https://github.com/william-murray1204/stable-diffusion-cpp-python.git"   # a versão do PyPI (0.4.7) pode ser mais antiga que os modelos novos; a do GitHub traz a stable-diffusion.cpp mais recente


def _sd_dir():
    from .util import asta_home

    return asta_home()


def _sd_marker():
    return _sd_dir() / "sd_needs_newer"   # escrito pelo Canvas quando a stable-diffusion.cpp instalada não reconhece um modelo («get sd version from file failed»)


def _sd_remote_sha() -> str:
    """O commit mais novo da stable-diffusion-cpp-python no GitHub (vazio se não deu para consultar)."""
    try:
        r = subprocess.run(["git", "ls-remote", SD_GIT.split("@ git+", 1)[1], "HEAD"], capture_output=True, text=True, timeout=30)
        return str(r.stdout).split()[0] if r.returncode == 0 and str(r.stdout).split() else ""
    except Exception:  # noqa: BLE001  (sem git, sem rede, tempo esgotado…)
        return ""


def _uses_diffusion_ggufs() -> bool:
    """A pessoa tem GGUF de difusão de imagem (Qwen-Image, FLUX…) baixado? Esses modelos dependem da stable-diffusion.cpp mais nova."""
    from .canvas import support

    folder = _sd_dir() / "models" / "image"
    try:
        return any(support.family_of(f.name) for f in folder.glob("*.gguf"))
    except OSError:
        return False


def _build_tools_missing() -> list:
    """O que falta para compilar a stable-diffusion.cpp: git e um compilador C/C++. (O cmake e o ninja o próprio pip baixa na hora de compilar, não precisam estar instalados.)"""
    if os.name == "nt":
        return []   # no Windows o compilador (Visual Studio Build Tools) é conferido pelo próprio pip, que mostra o erro
    return [t for t in ("git",) if not shutil.which(t)] + ([] if any(shutil.which(c) for c in ("cc", "gcc", "clang")) else ["compilador C/C++"])


def _build_tools_hint() -> str:
    if sys.platform == "darwin":
        return "xcode-select --install"
    return "sudo apt install git build-essential" if shutil.which("apt") else "sudo dnf install git gcc-c++" if shutil.which("dnf") else "instale git e um compilador C/C++"


def _sd_latest(force: bool = False) -> bool:
    """Mantém a stable-diffusion-cpp-python na versão mais nova do GitHub (compila a stable-diffusion.cpp: precisa de git e de um compilador C/C++, e leva alguns minutos). O PyPI parou na 0.4.7.
    ASTA_SD_LATEST=auto (padrão): na instalação e na atualização, quando o Canvas avisou que um modelo não foi reconhecido ou a pessoa tem GGUF de difusão (Qwen-Image, FLUX…) — e só se o GitHub
    tem commit novo desde a última compilação; =always: sempre que houver commit novo; =never: nunca. `force` (asta libs --sd-latest) compila sem perguntar.
    True se instalou ou não era preciso; False se tentou e falhou (o ASTA continua com a versão que já tinha)."""
    mode = (os.environ.get("ASTA_SD_LATEST") or "auto").strip().lower()
    marker, built = _sd_marker(), _sd_dir() / "sd_built_sha"
    if mode in ("never", "no", "0") and not force:
        return True
    wanted = force or mode in ("always", "yes", "1") or marker.exists() or _uses_diffusion_ggufs()
    if not wanted:
        return True
    remote = _sd_remote_sha()
    try:
        have = built.read_text(encoding="utf-8").strip()
    except OSError:
        have = ""
    if not force and not marker.exists() and remote and remote == have:
        print("\n" + _("stable-diffusion-cpp-python: já está na versão mais recente do GitHub."))
        return True
    miss = _build_tools_missing()
    if miss:
        print("\n" + _("⚠  Para compilar a stable-diffusion.cpp mais nova falta: {m}. Instale com:  {c}  — e rode de novo:  asta libs --sd-latest", m=", ".join(miss), c=_build_tools_hint()))
        return False
    print("\n" + _("Instalando a stable-diffusion-cpp-python mais nova (do GitHub): compila código nativo e pode levar vários minutos…"))
    res = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall", "--no-deps", "--no-cache-dir", "--disable-pip-version-check", SD_GIT])
    if res.returncode != 0:
        print(_("⚠  Não consegui compilar a versão mais nova. O ASTA segue com a que já está instalada; tente de novo depois com:  asta libs --sd-latest"))
        return False
    for f in (marker,):
        try:
            f.unlink()
        except OSError:
            pass
    if remote:
        try:
            built.write_text(remote, encoding="utf-8")
        except OSError:
            pass
    print(_("stable-diffusion-cpp-python atualizada. Abra o ASTA de novo para usá-la."))
    return True


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
        if not os.environ.get("ASTA_INSTALLER"):   # Windows (.exe) e AppImage têm o próprio Python: atualizam o ASTA com o pip, sem esta mensagem
            print(_("Este ASTA não foi instalado pelo instalador oficial: o Python do sistema não é gerenciado por ele (atualize-o pelo gerenciador de pacotes do seu sistema)."))
        return -1
    windows = os.name == "nt"
    name = "install.ps1" if windows else "install.sh"
    try:
        with urllib.request.urlopen(RAW + name, timeout=30) as resp:
            script = resp.read()
    except Exception as exc:  # noqa: BLE001
        print(_("Não foi possível baixar o instalador ({e}); atualizando só o ASTA e as bibliotecas.", e=exc))
        return -1
    env = dict(os.environ, ASTA_APP_DIR=str(app), ASTA_LANG=system_lang())   # o instalador fala o mesmo idioma
    if getattr(args, "rust", ""):
        env["ASTA_RUST"] = args.rust
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
        print(_("A atualização continua numa nova janela (Python, ASTA e bibliotecas). Quando terminar, abra o ASTA de novo."))
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


def _ask_terminal(question: str, default: bool = False):
    """Pergunta sim/não no terminal e devolve True/False; None se não há um terminal para perguntar. Funciona também com `curl … | sh`,
    em que o stdin é o próprio script: nesse caso lê do terminal de verdade (/dev/tty, ou CONIN$ no Windows). Enter = o padrão (`default`, normalmente não)."""
    stream, opened = None, None
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            stream = sys.stdin
        else:
            opened = stream = open("CONIN$" if os.name == "nt" else "/dev/tty", "r", encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    try:
        print(f"\n{question} " + ("[S/n]" if default and system_lang() == "pt" else "[s/N]" if system_lang() == "pt" else "[Y/n]" if default else "[y/N]") + " ", end="", flush=True)
        for _try in range(3):
            line = stream.readline()
            if not line:  # fim da entrada: ninguém para responder
                print()
                return None
            answer = line.strip().lower()
            if answer in YES:
                return True
            if answer == "":
                return default
            if answer in NO:
                return False
            print(_("Responda s (sim) ou n (não): "), end="", flush=True)
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
        print(_("Atualizando o Python, o ASTA e as bibliotecas dele…"))
        code = _update_with_installer(args)
        if code >= 0:
            if code == 0 and os.name != "nt":
                print("\n" + _("Pronto! Reinicie o ASTA para usar a nova versão."))
            return code
    print(_("Verificando as ferramentas do Python e o ASTA…"))
    if not _ensure_pip():
        return 1
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", "--disable-pip-version-check", "pip", "setuptools", "wheel"])  # já atualizadas = nada a fazer; falha = aviso
    if _asta_is_current(getattr(args, "force", False)):
        print(_("ASTA {v} já é a versão mais recente — nada a baixar. (Para reinstalar mesmo assim: asta update --force)", v=__version__))
    else:
        res = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", REPO_ZIP])
        if res.returncode != 0:
            return res.returncode
    if not getattr(args, "core", False):
        # processo novo: lê os metadados da versão recém-instalada (ela pode ter bibliotecas novas)
        lib_cmd = [sys.executable, "-m", "asta", "libs"] + (["--extras", args.extras] if getattr(args, "extras", "") else [])
        subprocess.run(lib_cmd)  # falhas de bibliotecas opcionais viram aviso; o ASTA já está atualizado
        subprocess.run([sys.executable, "-m", "asta", "models", "install", "--ask"])  # modelos pré-instalados: pergunta antes de baixar (pula o que já existe)
        subprocess.run([sys.executable, "-m", "asta", "native", "setup"] + (["--rust", args.rust] if getattr(args, "rust", "") else []))  # Rust: instala/atualiza (pergunta) e recompila o núcleo
    print("\n" + _("Pronto! Reinicie o ASTA para usar a nova versão."))
    return 0


def _native(args: argparse.Namespace) -> int:
    """`asta native status|build|install|update|setup`: o núcleo Rust opcional e o próprio Rust (instalar/atualizar)."""
    from . import native

    if args.action == "build":
        return native.build()
    if args.action == "install":
        code = native.install_rust()
        return code if code else native.build()
    if args.action == "update":
        native.update_rust()
        return native.build()
    if args.action == "setup":
        return native.setup(getattr(args, "rust", "") or os.environ.get("ASTA_RUST") or "yes", ask=_ask_terminal)
    st = native.status()
    print(_("Núcleo Rust: ") + (_("ativo") if st["active"] else _("inativo — usando Python puro, mais lento (rode: asta native setup)")) + (f" — {_(st['reason'])}" if st["reason"] else ""))
    print("cargo: " + (native.rust_version() if st["cargo"] else _("não encontrado (opcional: o ASTA baixa a biblioteca pronta)")) + ("" if not st["cargo"] else " · rustup: " + (_("sim") if st["rustup"] else _("não"))))
    print(_("Interface: {a} · plataforma: {p} · biblioteca pronta da Release: {n}", a=st["abi"], p=native.platform_tag(), n=native.prebuilt_name()))
    return 0


def _folder(args: argparse.Namespace) -> int:
    """`asta folder`: abre a pasta dos dados locais do ASTA (conversas, projetos, mídias, modelos, configurações) no gerenciador de arquivos.
    `--print` só mostra o caminho; `--app` abre a pasta do programa instalado em vez da dos dados."""
    from pathlib import Path

    from .util import asta_home

    if getattr(args, "home", None):
        os.environ["ASTA_HOME"] = args.home
    if getattr(args, "app", False):
        target = _managed_app_dir() or Path(__file__).resolve().parent
    else:
        target = Path(asta_home())
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    print(target)
    if getattr(args, "print", False):
        return 0
    try:
        if os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=True)
        else:
            subprocess.run(["xdg-open", str(target)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        print(_("Não consegui abrir o gerenciador de arquivos aqui; abra o caminho acima manualmente."))
        return 1
    return 0


def _doctor(_args: argparse.Namespace) -> int:
    from .util import asta_home, hardware_info

    hw = hardware_info(refresh=True)
    print(f"ASTA {__version__}")
    print(f"Python {hw['python']} · {hw['os']} {hw['arch']}")
    print(_("CPU: {n} núcleos · RAM: {r} GB · GPU: {g}", n=hw["cpus"], r=hw["ram_gb"], g=hw["gpu"] or _("não detectada (NVIDIA)")))
    print(_("Nível de hardware: {t}", t=hw["tier"]))
    try:
        from importlib import metadata

        print(f"pip {metadata.version('pip')} · setuptools {metadata.version('setuptools')}")
    except Exception:  # noqa: BLE001
        print(_("pip: não encontrado neste ambiente"))
    print("ffmpeg: " + (_("sim") if hw["ffmpeg"] else _("não (opcional: análise de vídeo/áudio)")))
    print(_("Pasta de dados: {p}", p=asta_home()))
    try:
        from . import native, perf

        nst = native.status()
        print(_("Núcleo Rust: ") + (_("ativo") if nst["active"] else _("inativo — usando Python puro, mais lento (rode: asta native setup)")))
        print("Rust: " + (native.rust_version() if nst["cargo"] else _("não instalado (não precisa: o ASTA baixa o núcleo pronto)")))
        print(_("Modo de desempenho: ") + _(perf.describe(perf.profile({}, hw))))
    except Exception:  # noqa: BLE001
        pass
    print(_("Idioma do terminal: {l}", l=system_lang()))
    try:
        import llama_cpp  # type: ignore  # noqa: F401

        print(_("Modelos locais embutidos (llama-cpp-python): disponível"))
    except ImportError:
        print(_('Modelos locais embutidos: não instalado (opcional: pip install "asta[local]")'))
    try:
        from .providers import lmstudio

        lm = lmstudio.probe(timeout=1.5)
        if lm["running"]:
            print(_("LM Studio: rodando em {u} · modelo carregado: {m}", u=lm["url"], m=", ".join(lm["loaded"]) or _("nenhum (carregue um no LM Studio)")))
        else:
            print(_("LM Studio: não detectado em {u} (opcional: abra o LM Studio e ligue o servidor em Developer → Start Server)", u=lm["url"]))
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
        print(_("Modelos locais de mídia do Canvas (torch, diffusers, transformers): disponível"))
    else:
        print(_('Modelos locais de mídia do Canvas: não instalado (opcional: pip install "asta[media]")'))
    return 0


def _work(args: argparse.Namespace) -> int:
    """`asta work`: mostra o estado do Work (máquina, Tailscale, redes e quem entrou) sem abrir a WebUI."""
    if getattr(args, "home", None):
        os.environ["ASTA_HOME"] = args.home
    from .storage import Store
    from .work import WorkManager, tailscale

    store = Store()
    mgr = WorkManager(store)
    ts = tailscale.status(refresh=True)
    print(_("Máquina: {n} ({i})", n=mgr.ident["name"], i=mgr.machine_id))
    if not ts["installed"]:
        print(_("Tailscale: não instalado (opcional — o Work também sincroniza pela rede local ou por uma pasta de nuvem)."))
    elif ts["running"]:
        print(_("Tailscale: conectado · IP {ip} · {n} máquina(s) na tailnet", ip=ts["ip"], n=len(ts["peers"])))
    else:
        print(_("Tailscale: instalado, mas {s}", s=ts.get("state") or _("desconectado")))
    if not mgr.orgs:
        print(_("Nenhuma rede do Work ainda: crie ou entre em uma na seção Work."))
    for oid, st in sorted(mgr.orgs.items()):
        meta = st.get("meta", "org") or {}
        print(_("Rede «{n}» ({i}): {u} pessoa(s), {m} máquina(s), {f} arquivo(s)", n=meta.get("name", oid), i=oid, u=len(st.all("users")), m=len(st.all("machines")), f=len(st.all("files"))))
    print(_("Dados do Work: {p}", p=mgr.root))
    return 0


def main(argv=None) -> int:
    from .util import fix_default_certs

    fix_default_certs()   # macOS + Python do python.org: sem isto toda chamada HTTPS (atualização, modelos, Rust) falhava por falta de certificados
    parser = argparse.ArgumentParser(prog="asta", description=_("ASTA — o primeiro super app open source: chat com IA, busca na web, mundos 3D, avatars, jogos 2D, Canvas de mídia e Studio de vídeo"))
    sub = parser.add_subparsers(dest="cmd")
    run = sub.add_parser("run", help=_("inicia a WebUI (padrão)"))
    for p in (parser, run):
        p.add_argument("--host", default="127.0.0.1", help=_("endereço (padrão 127.0.0.1)"))
        p.add_argument("--port", type=int, default=8787, help=_("porta (padrão 8787)"))
        p.add_argument("--no-browser", action="store_true", help=_("não abrir o navegador"))
        p.add_argument("--home", help=_("pasta de dados (padrão ~/.asta)"))
        p.add_argument("--no-update", action="store_true", help=_("não atualiza/instala nada ao abrir (também ASTA_NO_UPDATE=1)"))
    run.add_argument("--mobile", action="store_true", help=_("libera o uso pelo celular/tablet na sua rede (só aparelhos pareados por QR code)"))
    parser.add_argument("--mobile", action="store_true", help=argparse.SUPPRESS)
    mob = sub.add_parser("mobile", help=_("inicia o ASTA liberado para celular/tablet e mostra o QR code de pareamento"))
    mob.add_argument("--port", type=int, default=8787, help=_("porta (padrão 8787)"))
    mob.add_argument("--no-browser", action="store_true", help=_("não abrir o navegador"))
    mob.add_argument("--home", help=_("pasta de dados (padrão ~/.asta)"))
    mob.add_argument("--no-update", action="store_true", help=_("não atualiza/instala nada ao abrir (também ASTA_NO_UPDATE=1)"))
    upd = sub.add_parser("update", help=_("atualiza o Python, o ASTA, as bibliotecas dele e (opcional) o Rust para a versão mais recente"))
    upd.add_argument("--core", action="store_true", help=_("atualiza só o ASTA (e pip/setuptools/wheel), sem o Python do sistema nem as bibliotecas opcionais"))
    upd.add_argument("--no-python", action="store_true", help=_("não atualiza o Python do sistema (atualiza o ASTA, o pip e as bibliotecas)"))
    upd.add_argument("--extras", default="", help=_("bibliotecas a atualizar: all (padrão), none ou lista (docs,media,local)"))
    upd.add_argument("--force", action="store_true", help=_("reinstala o ASTA mesmo que já esteja na versão mais recente"))
    upd.add_argument("--rust", choices=("ask", "yes", "no"), default="", help=_("Rust (núcleo rápido do ASTA): yes = instala/atualiza sozinho (padrão), ask = pergunta, no = pula (também ASTA_RUST)"))
    mod = sub.add_parser("models", help=_("modelos locais pré-instalados (texto e imagem): list | install"))
    mod.add_argument("action", choices=("list", "install"), nargs="?", default="list")
    mod.add_argument("--which", default="", help=_("all (padrão), none, text, image ou ids (também ASTA_MODELS)"))
    mod.add_argument("--ask", action="store_true", help=_("pergunta no terminal (sim/não) antes de baixar o que falta; sem efeito se --which ou ASTA_MODELS já disseram o que fazer"))
    mod.add_argument("--home", help=_("pasta de dados (padrão ~/.asta)"))
    libs = sub.add_parser("libs", help=_("instala/atualiza as bibliotecas opcionais do ASTA (docs, media, local)"))
    libs.add_argument("--extras", default="", help=_("all (padrão), none ou lista separada por vírgula (docs,media,local)"))
    libs.add_argument("--sd-cli", action="store_true", help=_("baixa o executável pronto da stable-diffusion.cpp (sd-cli), sem compilar, para modelos de imagem que a biblioteca Python não reconhece"))
    libs.add_argument("--sd-latest", action="store_true", help=_("compila a stable-diffusion-cpp-python mais nova do GitHub (para modelos de imagem novos que a do PyPI não reconhece)"))
    nat = sub.add_parser("native", help=_("Rust e núcleo rápido do ASTA: status | build | install | update | setup"))
    nat.add_argument("action", choices=("status", "build", "install", "update", "setup"), nargs="?", default="status")
    nat.add_argument("--rust", choices=("ask", "yes", "no"), default="", help=_("com setup: yes = faz sozinho (padrão), ask = pergunta, no = pula (também ASTA_RUST)"))
    fol = sub.add_parser("folder", help=_("abre a pasta dos dados locais do ASTA no seu computador"))
    fol.add_argument("--print", action="store_true", help=_("só mostra o caminho, sem abrir"))
    fol.add_argument("--app", action="store_true", help=_("abre a pasta do programa instalado em vez da dos dados"))
    fol.add_argument("--home", help=_("pasta de dados (padrão ~/.asta)"))
    wk = sub.add_parser("work", help=_("mostra o estado do Work (redes, máquinas e Tailscale)"))
    wk.add_argument("action", choices=("status",), nargs="?", default="status")
    wk.add_argument("--home", help=_("pasta de dados (padrão ~/.asta)"))
    sub.add_parser("doctor", help=_("mostra diagnóstico do ambiente"))
    sub.add_parser("version", help=_("mostra a versão"))
    args = parser.parse_args(argv)
    if args.cmd == "update":
        return _update(args)
    if args.cmd == "models":
        return _models(args)
    if args.cmd == "libs":
        return _libs(args)
    if args.cmd == "native":
        return _native(args)
    if args.cmd == "folder":
        return _folder(args)
    if args.cmd == "work":
        return _work(args)
    if args.cmd == "doctor":
        return _doctor(args)
    if args.cmd == "version":
        print(__version__)
        return 0
    if args.cmd == "mobile":
        args.host, args.mobile = "0.0.0.0", True
    elif getattr(args, "mobile", False):
        args.host = "0.0.0.0"
    done = _auto_update(args, list(argv) if argv is not None else sys.argv[1:])
    if done is not None:
        return done
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
