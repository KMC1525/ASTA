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

    if getattr(args, "no_update", False) or os.environ.get("ASTA_NO_UPDATE", "") not in ("", "0") or _managed_app_dir() is None:
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
        print(_("Não foi possível abrir nenhuma porta entre {a} e {b}.", a=args.port, b=args.port + 19), file=sys.stderr)
        return 1
    shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0", "::") else args.host
    url = f"http://{shown}:{port}/"
    print(BANNER.format(version=__version__))
    print(f"  WebUI:   {url}")
    print(_("  Dados:   {p}", p=store.home))
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(_("  ⚠  Escutando fora do localhost: qualquer pessoa na sua rede poderá usar o ASTA e suas chaves de API."))
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


def _libs(args: argparse.Namespace) -> int:
    """Instala o que falta e atualiza (só se houver versão mais nova) as bibliotecas opcionais do ASTA. Uma que falhe não impede as outras.
    O que já está instalado não é instalado de novo: o pip só mexe nele se existir uma versão mais nova."""
    chosen, unknown = _wanted_libs(getattr(args, "extras", "") or "")
    if unknown:
        print(_("Bibliotecas desconhecidas: {u}. Opções: {o}, all, none.", u=", ".join(unknown), o=", ".join(LIBS)), file=sys.stderr)
        return 2
    if not chosen:
        print(_("Bibliotecas opcionais: nada a instalar (ASTA_EXTRAS=none)."))
        return 0
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
    ok = [e for e in chosen if e not in failed]
    print("\n" + _("Bibliotecas prontas: {l}", l=", ".join(ok) or _("nenhuma")) + (_(" (já estavam instaladas: {p})", p=", ".join(present)) if present else "")
          + (_(" · com falha: {f}", f=", ".join(failed)) if failed else ""))
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
    print(_("Núcleo Rust: ") + (_("ativo") if st["active"] else _("inativo (usando Python puro)")) + (f" — {_(st['reason'])}" if st["reason"] else ""))
    print("cargo: " + (native.rust_version() if st["cargo"] else _("não encontrado (opcional: asta native install)")) + ("" if not st["cargo"] else " · rustup: " + (_("sim") if st["rustup"] else _("não"))))
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
        print(_("Núcleo Rust: ") + (_("ativo") if nst["active"] else _("inativo — usando Python puro (opcional: asta native setup)")))
        print("Rust: " + (native.rust_version() if nst["cargo"] else _("não instalado (opcional: asta native install)")))
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="asta", description=_("ASTA — o primeiro super app open source: chat com IA, busca na web, mundos 3D, avatars, jogos 2D, Canvas de mídia e Studio de vídeo"))
    sub = parser.add_subparsers(dest="cmd")
    run = sub.add_parser("run", help=_("inicia a WebUI (padrão)"))
    for p in (parser, run):
        p.add_argument("--host", default="127.0.0.1", help=_("endereço (padrão 127.0.0.1)"))
        p.add_argument("--port", type=int, default=8787, help=_("porta (padrão 8787)"))
        p.add_argument("--no-browser", action="store_true", help=_("não abrir o navegador"))
        p.add_argument("--home", help=_("pasta de dados (padrão ~/.asta)"))
        p.add_argument("--no-update", action="store_true", help=_("não atualiza/instala nada ao abrir (também ASTA_NO_UPDATE=1)"))
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
    nat = sub.add_parser("native", help=_("Rust e núcleo rápido do ASTA: status | build | install | update | setup"))
    nat.add_argument("action", choices=("status", "build", "install", "update", "setup"), nargs="?", default="status")
    nat.add_argument("--rust", choices=("ask", "yes", "no"), default="", help=_("com setup: yes = faz sozinho (padrão), ask = pergunta, no = pula (também ASTA_RUST)"))
    fol = sub.add_parser("folder", help=_("abre a pasta dos dados locais do ASTA no seu computador"))
    fol.add_argument("--print", action="store_true", help=_("só mostra o caminho, sem abrir"))
    fol.add_argument("--app", action="store_true", help=_("abre a pasta do programa instalado em vez da dos dados"))
    fol.add_argument("--home", help=_("pasta de dados (padrão ~/.asta)"))
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
    if args.cmd == "doctor":
        return _doctor(args)
    if args.cmd == "version":
        print(__version__)
        return 0
    done = _auto_update(args, list(argv) if argv is not None else sys.argv[1:])
    if done is not None:
        return done
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
