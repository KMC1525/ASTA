"""Limites fixos do Computer Use. Valem em **qualquer** modo, inclusive o Full Access.

O modo (Full Access / Ask) decide *quando perguntar* ao usuário; este módulo decide o que **nunca** acontece:

* ler, escrever ou apagar o que guarda segredos (chaves SSH/GPG/nuvem, perfis de navegador, cofres de senha) e a **pasta de dados do próprio ASTA** — lá estão as chaves de API e
  a configuração do próprio Computer Use: a IA não pode ligar o Full Access para si mesma;
* escrever, mover ou apagar dentro de pastas do sistema (Windows, Program Files, /usr, /etc, /System…) ou apagar a pasta pessoal, um disco inteiro ou as pastas-raiz do usuário;
* rodar interpretadores e shells (a IA escreve **ações validadas**, nunca código para o ASTA executar), instaladores de privilégio (`sudo`), apagadores/formatadores de disco
  e desligar/reiniciar o computador.

Caminhos são resolvidos (links simbólicos seguidos) antes de conferir, então um atalho para fora não vale.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Iterable, Optional

READ, WRITE, DELETE = "read", "write", "delete"


class Blocked(Exception):
    """Ação proibida pelos limites fixos (a mensagem diz por quê, para a IA escolher outro caminho)."""


_SENSITIVE_DIRS = {".ssh", ".gnupg", ".aws", ".azure", ".kube", ".password-store", ".config/gcloud", ".config/gh", ".config/git/credentials", ".docker", ".mozilla", ".thunderbird",
                   ".config/google-chrome", ".config/chromium", ".config/BraveSoftware", ".config/microsoft-edge", ".config/vivaldi", ".config/opera", ".config/keepassxc", ".local/share/keyrings",
                   ".local/share/kwalletd", ".config/Bitwarden", ".electrum", ".bitcoin", ".monero", ".ethereum",
                   "library/keychains", "library/application support/google/chrome", "library/application support/firefox", "library/application support/microsoft edge",
                   "library/application support/bravesoftware", "library/safari", "library/cookies", "library/messages",
                   "appdata/local/google/chrome", "appdata/local/microsoft/edge", "appdata/roaming/mozilla", "appdata/roaming/microsoft/credentials", "appdata/local/microsoft/credentials",
                   "appdata/roaming/microsoft/protect", "appdata/local/bravesoftware", "appdata/roaming/opera software"}
_SENSITIVE_FILES = {".netrc", ".npmrc", ".pypirc", ".git-credentials", ".pgpass", ".my.cnf", ".boto", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "login data", "web data", "cookies", "logins.json",
                    "key3.db", "key4.db", "cert9.db", "wallet.dat", "secring.gpg", "credentials.json", "client_secret.json", "service-account.json", ".env", "ntuser.dat", "sam", "shadow", "master.passwd"}
_SENSITIVE_EXT = (".pem", ".key", ".p12", ".pfx", ".kdbx", ".keystore", ".jks", ".ppk", ".asc")

_SYSTEM_POSIX = ("/bin", "/boot", "/dev", "/etc", "/lib", "/lib32", "/lib64", "/libx32", "/proc", "/run", "/sbin", "/sys", "/usr", "/var/lib", "/var/log", "/var/run", "/root",
                 "/system", "/vendor", "/apex", "/product", "/data/data", "/data/system", "/efi")
_SYSTEM_MAC = ("/System", "/Library", "/Applications", "/private/etc", "/private/var/db", "/usr", "/bin", "/sbin", "/cores", "/opt/homebrew/Cellar")
_SYSTEM_WIN = ("windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "system volume information", "recovery", "boot", "perflogs")

# programas que o Computer Use nunca executa (nem no Full Access): interpretadores/shells, escalada de privilégio, apagar/formatar/particionar, desligar, baixadores e encadeadores de comandos
DENIED_PROGRAMS = {
    "sh", "bash", "zsh", "fish", "dash", "csh", "tcsh", "ksh", "ash", "busybox", "cmd", "command", "powershell", "pwsh", "wscript", "cscript", "mshta", "regsvr32", "rundll32", "wmic", "bitsadmin", "certutil",
    "python", "python2", "python3", "py", "pythonw", "perl", "ruby", "node", "nodejs", "deno", "bun", "php", "lua", "tclsh", "wish", "osascript", "jshell", "java", "javaw", "groovy", "julia", "rscript", "awk", "gawk", "sed",
    "sudo", "su", "doas", "pkexec", "runas", "gsudo", "setuid", "chroot", "nsenter", "unshare",
    "rm", "rmdir", "del", "erase", "rd", "shred", "wipe", "srm", "unlink", "truncate", "dd", "mkfs", "format", "fdisk", "sfdisk", "cfdisk", "parted", "gparted", "diskpart", "wipefs", "cryptsetup", "lvremove", "vgremove",
    "shutdown", "reboot", "halt", "poweroff", "init", "telinit", "systemctl", "service", "launchctl", "reg", "regedit", "schtasks", "at", "crontab", "bcdedit", "diskutil", "tmutil",
    "chmod", "chown", "chgrp", "icacls", "takeown", "cacls", "attrib", "mount", "umount", "kill", "killall", "pkill", "taskkill",
    "curl", "wget", "nc", "ncat", "netcat", "telnet", "ssh", "scp", "sftp", "ftp", "rsync", "socat", "nmap",
    "xargs", "find", "env", "nohup", "eval", "exec", "time", "timeout", "start", "open", "xdg-open", "call", "forfiles", "xcopy", "robocopy", "move", "ren", "mklink", "ln",
}


def _norm(p: Path) -> str:
    s = str(p).replace("\\", "/")
    return s.lower() if (os.name == "nt" or sys.platform == "darwin") else s


def home() -> Path:
    return Path.home().resolve()


def resolve(path: str, base: Optional[Path] = None) -> Path:
    """Caminho absoluto, `~` expandido e links seguidos (o alvo real é o que vale). Variáveis de ambiente não são expandidas (a IA não escolhe segredos pelo nome)."""
    raw = str(path or "").strip().strip('"').strip("'")
    if not raw or "\x00" in raw:
        raise Blocked("Caminho vazio ou inválido.")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (base or home()) / p
    try:
        return p.resolve(strict=False)
    except (OSError, RuntimeError):
        raise Blocked("Caminho inválido.") from None


def _under(p: Path, root: Path) -> bool:
    a, b = _norm(p), _norm(root).rstrip("/")
    return a == b or a.startswith(b + "/")


def _sensitive(p: Path) -> Optional[str]:
    s = _norm(p)
    low = s.lower()
    for d in _SENSITIVE_DIRS:
        d = d.lower()
        if re.search(r"(^|/)" + re.escape(d) + r"(/|$)", low):
            return "guarda segredos (senhas, chaves ou perfis de navegador)"
    name = p.name.lower()
    if name in _SENSITIVE_FILES or name.startswith("id_rsa") or name.startswith(".env.") or name.endswith(_SENSITIVE_EXT):
        return "é um arquivo de segredos (chave, certificado ou credencial)"
    return None


_home_override: Optional[Path] = None


def set_home(path: Optional[Path]) -> None:
    """A pasta de dados do ASTA em uso (a do `Store`). Normalmente é a padrão; os testes e `--home` usam outra."""
    global _home_override
    _home_override = Path(path).resolve() if path else None


def asta_home() -> Path:
    if _home_override is not None:
        return _home_override
    from ..util import asta_home as _h

    return _h().resolve()


def _asta_homes() -> list:
    from ..util import asta_home as _h

    out = [asta_home()]
    try:
        d = _h().resolve()
        if d not in out:
            out.append(d)
    except OSError:
        pass
    return out


def data_dir() -> Path:
    """Onde o Computer Use guarda o que é dele (tarefas, capturas de tela, lixeira)."""
    return (asta_home() / "computer").resolve()


def workspace() -> Path:
    """Área de rascunho: a única parte dos dados do ASTA que a IA pode ler e escrever."""
    return (data_dir() / "workspace").resolve()


def _system_reason(p: Path) -> Optional[str]:
    if _under(p, home()):   # a pasta pessoal nunca é «do sistema» (quem roda como root tem a casa em /root)
        return None
    s = _norm(p)
    if os.name == "nt":
        parts = [x for x in s.split("/") if x]
        if len(parts) >= 2 and re.match(r"^[a-z]:$", parts[0]) and parts[1] in _SYSTEM_WIN:
            return "pasta do sistema (Windows/Program Files)"
        return None
    roots = list(_SYSTEM_MAC if sys.platform == "darwin" else _SYSTEM_POSIX)
    for r in roots:
        if _under(p, Path(r)):
            return "pasta do sistema"
    return None


def check_path(path: str, op: str, *, base: Optional[Path] = None, extra_allowed: Iterable[Path] = ()) -> Path:
    """Resolve `path` e confere se `op` ("read" | "write" | "delete") é permitido. Devolve o caminho real ou levanta `Blocked`."""
    p = resolve(path, base)
    ws = workspace()
    allowed = [ws] + [Path(a).resolve() for a in extra_allowed]
    if any(_under(p, ah) for ah in _asta_homes()) and not any(_under(p, a) for a in allowed):
        raise Blocked("É a pasta de dados do ASTA (chaves de API e configurações): o Computer Use não acessa. Use outra pasta.")
    why = _sensitive(p)
    if why:
        raise Blocked(f"Acesso negado: {why}.")
    if op in (WRITE, DELETE):
        why = _system_reason(p)
        if why:
            raise Blocked(f"Não mexo em {why}.")
        h = home()
        if op == DELETE:   # apagar/mover a pasta inteira é o que não vale; criar e mexer DENTRO dela (organizar Downloads, por exemplo) é o uso normal
            roots = {h} | {h / sub for sub in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos", "Movies", "Public", "Templates", "Área de Trabalho", "Documentos", "Imagens", "Músicas", "Vídeos", "Público")}
            if any(_norm(p) == _norm(x) for x in roots):
                raise Blocked("Esta pasta (a pessoal ou uma pasta-raiz do usuário) não pode ser apagada nem movida inteira; mexa no que está dentro dela.")
        if p.parent == p or (os.name == "nt" and re.match(r"^[a-zA-Z]:/?$", str(p).replace("\\", "/"))):
            raise Blocked("Não altero um disco inteiro.")
        if any(_under(p, h / sub) for sub in ("Library", "AppData", ".config", ".local", ".cache", ".var", ".steam")):
            raise Blocked("As configurações dos aplicativos e do sistema ficam fora do alcance do Computer Use.")
    return p


def check_program(program: str) -> str:
    """Confere o nome do programa de `run_program`. Devolve o nome base (sem pasta e sem .exe)."""
    raw = str(program or "").strip()
    if not raw or "\x00" in raw or "\n" in raw:
        raise Blocked("Programa inválido.")
    base = re.split(r"[\\/]", raw)[-1].lower()
    base = re.sub(r"\.(exe|com|bat|cmd|ps1|sh|py|app)$", "", base)
    if base in DENIED_PROGRAMS or re.match(r"^(python|pypy|perl|ruby|node|php|lua)[\d.]*$", base) or base.startswith("mkfs"):
        raise Blocked(f"O programa «{base}» é bloqueado (interpretador, shell, apagador de disco, privilégio, rede crua ou encadeador de comandos). Use as ferramentas do Computer Use.")
    if re.search(r"\.(bat|cmd|ps1|vbs|vbe|wsf|js|jse|sh|command)$", raw.lower()):
        raise Blocked("Scripts não são executados pelo Computer Use.")
    return base


def check_args(args: Iterable[str], cwd: Optional[Path] = None) -> list:
    """Argumentos de `run_program`: sem NUL e sem tamanho absurdo; e **qualquer argumento que pareça caminho** passa pelo mesmo crivo dos arquivos (não vale ler/escrever a pasta de
    dados do ASTA nem segredos por dentro de um argumento de `tar`, `7z`, `ffmpeg`…). `--opcao=valor` confere o valor."""
    out = []
    ws = workspace()
    for a in args:
        s = str(a)
        if "\x00" in s or len(s) > 4000:
            raise Blocked("Argumento inválido.")
        cand = s.split("=", 1)[1] if s.startswith("-") and "=" in s else s
        if cand and not cand.startswith("-") and (re.search(r"[\\/]", cand) or cand.startswith("~") or re.match(r"^[a-zA-Z]:", cand)):
            try:
                p = resolve(cand.split("?")[0], cwd) if "://" not in cand else None
            except Blocked:
                p = None
            if p is not None and "://" not in cand:
                if any(_under(p, ah) for ah in _asta_homes()) and not _under(p, ws):
                    raise Blocked("Um argumento aponta para a pasta de dados do ASTA (chaves de API e configurações): bloqueado.")
                why = _sensitive(p)
                if why:
                    raise Blocked(f"Um argumento aponta para algo protegido: {why}.")
        out.append(s)
    return out[:60]


_URL_OK = re.compile(r"^(https?://|mailto:)[^\s]+$", re.I)


def check_url(url: str) -> str:
    u = str(url or "").strip()
    if not _URL_OK.match(u) or len(u) > 2000 or any(c in u for c in "\r\n\x00"):
        raise Blocked("Só abro endereços http(s) e mailto.")
    return u
