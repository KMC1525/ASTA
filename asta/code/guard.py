"""Limites fixos do Code. Valem em **qualquer** modo, inclusive o Full Access.

O modo (Full Access / Ask) decide *quando perguntar*; este módulo decide o que **nunca** acontece:

* **tudo fica dentro da pasta do projeto** (o *workspace* da sessão): caminhos são resolvidos (links simbólicos seguidos) antes de conferir, então um atalho para fora não vale;
* a pasta de dados do ASTA (chaves de API, configurações) é inalcançável — a única exceção é a área de workspaces do próprio Code (`<dados>/code/workspaces/`);
* segredos (chaves SSH, `.env`, certificados, perfis de navegador…) não são lidos nem escritos; `.env.example`/`.sample` são liberados;
* a pasta `.git/` só é mexida pela ferramenta `git` (um hook escrito à mão executaria código sem passar pelo Ask);
* **comandos são uma lista de argumentos** (`argv`), nunca texto de shell: sem `&&`, pipes ou redirecionamento; o programa precisa estar numa lista de ferramentas de desenvolvimento
  (python, node, cargo, go, mvn, dotnet, gcc, make…); shells, `sudo`, apagadores de disco, `curl`/`ssh` e afins são bloqueados; o ambiente do comando é limpo de chaves e tokens;
* o `git` tem subcomandos permitidos e nada de `-c`, `--exec`, `--upload-pack`, `push --force`, `reset --hard` ou `clean`.

**Honestidade:** rodar testes e programas escritos pela IA dá a esse código as permissões do seu usuário no computador — não há como isolá-lo por completo só com o Python. Por isso o modo Ask
pergunta antes de cada comando e mostra o comando inteiro; o Full Access é confiança total. Estes limites impedem os caminhos acidentais e óbvios, não um código malicioso.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..computer import guard as cg

Blocked = cg.Blocked
READ, WRITE, DELETE = "read", "write", "delete"

# programas de desenvolvimento que o `run_command` aceita (nome base, sem .exe); o que não está aqui é bloqueado
ALLOWED_PROGRAMS = {
    "python", "python3", "py", "pip", "pip3", "pytest", "ruff", "black", "flake8", "mypy", "pylint", "isort", "uv", "poetry", "pipenv", "tox", "nox",
    "node", "npm", "npx", "yarn", "pnpm", "bun", "deno", "tsc", "eslint", "prettier", "vite", "jest", "vitest", "mocha", "playwright",
    "cargo", "rustc", "rustfmt", "clippy-driver", "go", "gofmt", "java", "javac", "jar", "mvn", "gradle", "kotlinc", "kotlin", "sbt", "scala",
    "dotnet", "msbuild", "csc", "gcc", "g++", "cc", "c++", "clang", "clang++", "make", "gmake", "cmake", "ctest", "ninja", "meson", "nmake", "cl",
    "php", "composer", "phpunit", "ruby", "bundle", "bundler", "gem", "rake", "rspec", "swift", "swiftc", "dart", "flutter", "lua", "luajit", "luarocks", "Rscript",
    "sqlite3", "tree", "wc", "diff", "uname", "which", "where",
}
# subcomandos de `git` aceitos e a classe de risco de cada um (read = só olha; git = muda o repositório local; publish = fala com o servidor remoto)
GIT_SUBCOMMANDS = {
    "status": "read", "diff": "read", "log": "read", "show": "read", "branch": "read", "remote": "read", "rev-parse": "read", "ls-files": "read", "blame": "read", "describe": "read",
    "shortlog": "read", "grep": "read", "ls-remote": "publish", "add": "git", "commit": "git", "switch": "git", "checkout": "git", "restore": "git", "stash": "git", "tag": "git", "merge": "git",
    "mv": "git", "rm": "git", "init": "git", "cherry-pick": "git", "revert": "git", "reset": "git", "fetch": "publish", "pull": "publish", "push": "publish", "clone": "publish",
}
_GIT_BAD_FLAGS = ("-c", "-C", "--exec", "--upload-pack", "--receive-pack", "--git-dir", "--work-tree", "--config", "--config-env", "--exec-path", "--super-prefix", "--namespace", "--paginate", "-p")
_GIT_BAD_FOR = {"push": ("--force", "-f", "--force-with-lease", "--mirror", "--delete", "-d", "--prune"), "reset": ("--hard", "--merge", "--keep"), "checkout": ("--force", "-f", "--orphan"),
                "switch": ("--force", "-f", "--discard-changes"), "stash": ("drop", "clear"), "branch": ("-D", "--force", "-f"), "tag": ("-d", "-f", "--force")}
_ENV_DROP = re.compile(r"(KEY|TOKEN|SECRET|PASSW|CREDENTIAL|AUTH|COOKIE|SESSION|PRIVATE|^ASTA_|^AWS_|^AZURE_|^GOOGLE_|^GH_|^GITHUB_|^HF_|^OPENAI|^ANTHROPIC|^NPM_CONFIG__)", re.I)
_ENV_KEEP_ALWAYS = {"PATH", "HOME", "USERPROFILE", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT", "COMSPEC", "PATHEXT", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMDATA", "USER", "USERNAME", "SHELL",
                    "JAVA_HOME", "GOPATH", "GOROOT", "CARGO_HOME", "RUSTUP_HOME", "NVM_DIR", "PYENV_ROOT", "DOTNET_ROOT", "ANDROID_HOME", "ANDROID_SDK_ROOT"}
_EXAMPLE_ENV = re.compile(r"^\.env\.(example|sample|template|dist|defaults?)$|^\.env\.[\w-]+\.(example|sample|template)$", re.I)


def code_dir() -> Path:
    """Onde o Code guarda o que é dele (pastas, sessões, backups de desfazer, checkouts na nuvem)."""
    return (cg.asta_home() / "code").resolve()


def managed_workspaces() -> Path:
    """Pasta dos workspaces criados pelo próprio ASTA (projeto novo e cópias de repositórios do GitHub)."""
    return (code_dir() / "workspaces").resolve()


def resolve(path: str, root: Path) -> Path:
    """Caminho absoluto dentro do projeto: relativo conta a partir da raiz; `~` e variáveis não são expandidos."""
    raw = str(path or "").strip().strip('"').strip("'")
    if not raw or "\x00" in raw:
        raise Blocked("Caminho vazio ou inválido.")
    if raw.startswith("~"):
        raise Blocked("Use caminhos relativos à pasta do projeto (sem «~»).")
    p = Path(raw)
    if not p.is_absolute():
        p = root / p
    try:
        return p.resolve(strict=False)
    except (OSError, RuntimeError):
        raise Blocked("Caminho inválido.") from None


def _inside(p: Path, root: Path) -> bool:
    return cg._under(p, root)


def check_root(path: str) -> Path:
    """Confere a pasta escolhida como projeto. Devolve o caminho real ou levanta `Blocked` (disco inteiro, pasta pessoal inteira, sistema, dados do ASTA)."""
    p = cg.resolve(path)
    if not p.is_dir():
        raise Blocked("A pasta do projeto não existe.")
    if p.parent == p or (os.name == "nt" and re.match(r"^[a-zA-Z]:/?$", str(p).replace("\\", "/"))):
        raise Blocked("Escolha uma pasta de projeto, não um disco inteiro.")
    if cg._norm(p) == cg._norm(cg.home()):
        raise Blocked("Escolha uma pasta dentro da sua pasta pessoal, não ela inteira.")
    why = cg._system_reason(p)
    if why:
        raise Blocked(f"É uma {why}: escolha outra pasta.")
    managed = managed_workspaces()
    if any(_inside(p, h) for h in cg._asta_homes()) and not _inside(p, managed):
        raise Blocked("É a pasta de dados do ASTA (chaves de API e configurações): o Code não trabalha nela.")
    if cg._sensitive(p):
        raise Blocked("Esta pasta guarda segredos (senhas, chaves ou perfis de navegador).")
    return p


def check_path(path: str, op: str, root: Path, *, extra_read: Iterable[Path] = ()) -> Path:
    """Resolve `path` dentro do projeto e confere a operação (`read` | `write` | `delete`). Devolve o caminho real ou levanta `Blocked`."""
    p = resolve(path, root)
    extra = [Path(x).resolve() for x in extra_read]
    inside = _inside(p, root)
    if not inside and not (op == READ and any(_inside(p, e) for e in extra)):
        raise Blocked("Fora da pasta do projeto: o Code só mexe nos arquivos do projeto da sessão.")
    if inside and ".git" in p.relative_to(root).parts:
        raise Blocked("A pasta .git só é alterada pela ferramenta «git» (commits, branches…), não por arquivos.")
    managed = managed_workspaces()
    if any(_inside(p, h) for h in cg._asta_homes()) and not _inside(p, managed) and not any(_inside(p, e) for e in extra):
        raise Blocked("É a pasta de dados do ASTA (chaves de API e configurações): o Code não acessa.")
    if not _EXAMPLE_ENV.match(p.name):
        why = cg._sensitive(p)
        if why:
            raise Blocked(f"Acesso negado: {why}.")
    if op == DELETE and p == root:
        raise Blocked("Não apago a pasta inteira do projeto.")
    return p


# ------------------------------------------------------------------------------------------------ comandos


def check_program(program: str) -> str:
    """Nome base do programa de `run_command`; levanta `Blocked` se não for uma ferramenta de desenvolvimento conhecida."""
    raw = str(program or "").strip()
    if not raw or "\x00" in raw or "\n" in raw or " " in raw.strip():
        raise Blocked("Programa inválido: passe só o nome do programa em «program» e os argumentos em «args» (nada de comandos encadeados).")
    if re.search(r"[\\/]", raw):
        raise Blocked("Passe só o nome do programa (python, node, cargo…), sem pasta.")
    base = re.sub(r"\.(exe|cmd|bat|com)$", "", raw.lower())
    base = re.sub(r"^(python|pip)3(\.\d+)?$", lambda m: m.group(1), base)
    if base not in {x.lower() for x in ALLOWED_PROGRAMS} and not re.match(r"^python3?\.\d+$", base):
        raise Blocked(f"O programa «{raw}» não está na lista de ferramentas de desenvolvimento do Code (python, node, npm, cargo, go, mvn, gradle, dotnet, gcc, make, cmake…). "
                      "Shells, sudo, curl/ssh e apagadores de disco são sempre bloqueados.")
    return base


def check_args(program: str, args: Iterable[str], root: Path) -> List[str]:
    """Argumentos de um comando: sem NUL, tamanho razoável, e **todo argumento que parece caminho** passa pelo crivo dos arquivos (nada de ler a pasta do ASTA nem segredos por argumento)."""
    out: List[str] = []
    base = Path(root)
    for a in args:
        s = str(a)
        if "\x00" in s or len(s) > 8000:
            raise Blocked("Argumento inválido.")
        cands = [s.split("=", 1)[1]] if s.startswith("-") and "=" in s else [s]
        for cand in cands:
            if not cand or "://" in cand or cand.startswith("-") or not re.search(r"[\\/]|^~|^[a-zA-Z]:", cand):
                continue
            if "\n" in cand or (" " in cand and not os.path.exists(os.path.join(root, cand))):
                continue
            try:
                if cand.startswith("~"):
                    raise Blocked("Use caminhos relativos à pasta do projeto (sem «~»).")
                p = resolve(cand.split("?")[0], base)
            except Blocked:
                if cand.startswith("~"):
                    raise
                continue
            if any(_inside(p, h) for h in cg._asta_homes()) and not _inside(p, managed_workspaces()):
                raise Blocked("Um argumento aponta para a pasta de dados do ASTA (chaves de API e configurações): bloqueado.")
            if not _EXAMPLE_ENV.match(p.name) and cg._sensitive(p):
                raise Blocked("Um argumento aponta para algo protegido (segredos).")
        out.append(s)
    if len(out) > 80:
        raise Blocked("Argumentos demais.")
    return out


def check_git(args: Iterable[str]) -> tuple:
    """(subcomando, argumentos, classe de risco) de uma chamada de git; levanta `Blocked` se algo não for permitido."""
    items = [str(a) for a in args]
    if not items:
        raise Blocked("Diga o subcomando do git (status, diff, add, commit…).")
    sub, rest = items[0].lower(), items[1:]
    if sub not in GIT_SUBCOMMANDS:
        raise Blocked(f"O subcomando «git {sub}» não é permitido. Permitidos: {', '.join(sorted(GIT_SUBCOMMANDS))}.")
    for a in rest:
        if "\x00" in a or "\n" in a and sub != "commit":
            raise Blocked("Argumento inválido.")
        low = a.split("=", 1)[0]
        if low in _GIT_BAD_FLAGS or any(low.startswith(f + "=") for f in _GIT_BAD_FLAGS if f.startswith("--")):
            raise Blocked(f"A opção «{low}» do git é bloqueada.")
        if low in _GIT_BAD_FOR.get(sub, ()):
            raise Blocked(f"«git {sub} {low}» é bloqueado (pode perder trabalho ou reescrever o histórico). Faça isso à mão, se for o caso.")
        if a.startswith("-c") and len(a) > 2 and sub != "commit":
            raise Blocked("A opção «-c» do git é bloqueada.")
    return sub, rest, _git_risk(sub, rest)


_BRANCH_READ = {"-a", "-r", "-v", "-vv", "--list", "-l", "--show-current", "--all", "--remotes", "--merged", "--no-merged", "--contains", "--verbose"}


def _git_risk(sub: str, rest: List[str]) -> str:
    """A classe de risco de uma chamada de git: listar branches/tags/remotes e ver o stash só olha; criar/mudar/apagar muda o repositório."""
    base = GIT_SUBCOMMANDS[sub]
    if sub == "remote" and rest and rest[0] in ("add", "remove", "rm", "rename", "set-url", "set-head", "set-branches", "prune", "update"):
        return "git"
    if sub == "branch":
        return "read" if all(a in _BRANCH_READ or (not a.startswith("-") and rest and rest[0] in ("--contains", "--merged", "--no-merged")) for a in rest) else "git"
    if sub == "tag":
        return "read" if not rest or all(a in ("-l", "--list", "-n") for a in rest) else "git"
    if sub == "stash":
        return "read" if rest and rest[0] in ("list", "show") else "git"
    return base


def clean_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Ambiente dos comandos: o do usuário sem chaves/tokens/segredos (e sem as variáveis do ASTA), mais ajustes para rodar sem terminal interativo."""
    env = {k: v for k, v in os.environ.items() if (k in _ENV_KEEP_ALWAYS or not _ENV_DROP.search(k)) and not k.startswith("GIT_CONFIG")}   # GIT_CONFIG_*: pode trazer cabeçalhos de autenticação do ambiente
    env.update({"CI": "1", "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1", "GIT_TERMINAL_PROMPT": "0",
                "GIT_EDITOR": "true", "GIT_PAGER": "cat", "PAGER": "cat", "NPM_CONFIG_UPDATE_NOTIFIER": "false", "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "ASTA_CODE": "1"})
    env.update(extra or {})
    return env


def python_for(root: Path) -> str:
    """O Python do projeto (`.venv`/`venv` dentro dele) ou o do sistema; por último o próprio Python do ASTA."""
    for d in (".venv", "venv"):
        for sub in (("Scripts", "python.exe"), ("bin", "python")):
            p = root / d / Path(*sub)
            if p.is_file():
                return str(p)
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found and "WindowsApps" not in found:
            return found
    return sys.executable


def which(program: str, root: Path) -> Optional[str]:
    """Caminho do executável (o Python do projeto para `python`/`pip`), ou None se o programa não estiver instalado."""
    low = program.lower()
    if low in ("python", "python3", "py"):
        return python_for(root)
    if low in ("pip", "pip3"):
        return None   # use «python -m pip»: garante o pip do Python certo
    return shutil.which(program) or shutil.which(program + ".exe")


def redact(text: str, secrets: Iterable[str]) -> str:
    """Troca por `***` qualquer segredo conhecido (token do GitHub…) que apareça num texto — saída de comando, erro, log."""
    out = str(text or "")
    for s in secrets:
        if s and len(s) >= 6:
            out = out.replace(s, "***")
    return re.sub(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})", "***", out)
