#!/bin/sh
# ASTA — instalador/atualizador para Linux e macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/KMC1525/ASTA/main/install.sh | sh
#
# O MESMO comando instala e atualiza. Seus dados (~/.asta: personagens, mundos,
# configurações) nunca são tocados. Opções (variáveis de ambiente):
#   ASTA_EXTRAS=all|none|docs,media,local   bibliotecas opcionais do ASTA. Padrão: all (instala/atualiza TODAS: PDFs mais
#                                       precisos, modelos locais de imagem/vídeo/som/voz do Canvas e modelos GGUF embutidos).
#                                       "none" instala só o ASTA (sem dependências). Uma biblioteca que falhe não aborta a instalação.
#   ASTA_SOURCE=<url|pasta|requisito>   instala de outra origem (padrão: GitHub, branch main)
#   ASTA_APP_DIR=<pasta>                onde fica o programa (padrão: ~/.asta/app)
#   ASTA_BIN_DIR=<pasta>                onde fica o comando `asta` (padrão: ~/.local/bin)
#   ASTA_MODELS=all|none|text|image     modelos locais pré-instalados: Qwen3.8 2B Distill (texto, Q8_0, ~2 GB) e Z-Image (imagem, Q4_K_M, ~6 GB
#                                       com o VAE e o codificador de texto). Sem esta variável o instalador PERGUNTA no terminal (sim/não) antes de
#                                       baixar; "all"/"text"/"image" baixa sem perguntar e "none" pula.
#   ASTA_PYTHON=auto|keep               auto (padrão): instala o Python se faltar e o atualiza (com pip, venv, setuptools e wheel)
#                                       pelo gerenciador de pacotes do sistema (apt, dnf, yum, pacman, zypper, apk, Homebrew).
#                                       keep: nunca mexe no Python do sistema.
#   ASTA_FORCE=1                        reinstala o ASTA mesmo que a versão instalada já seja a mais recente.
#   ASTA_RUST=ask|yes|no                Rust (deixa o ASTA mais rápido e leve): ask (padrão) PERGUNTA no terminal antes de instalar o Rust (e, se ele já existe, atualiza e
#                                       recompila o núcleo); yes instala/atualiza sem perguntar; no pula. Sem terminal, nunca instala sem permissão.
#   ASTA_LANG=pt|en                     idioma dos textos (padrão: o idioma do computador).
# O que já está instalado NÃO é instalado de novo: o Python só é atualizado se o gerenciador de pacotes tiver versão nova, o ambiente
# (venv) é reaproveitado, o ASTA só é baixado se houver versão mais nova, e as bibliotecas/modelos já presentes só são atualizados se precisar.
# Argumentos: sh -s -- --run            inicia o ASTA ao terminar.
#             sh -s -- --python-only    só instala/atualiza o Python e as ferramentas dele (pip, setuptools, wheel).
set -eu

SOURCE="${ASTA_SOURCE:-https://github.com/KMC1525/ASTA/archive/refs/heads/main.zip}"
APP_DIR="${ASTA_APP_DIR:-$HOME/.asta/app}"
BIN_DIR="${ASTA_BIN_DIR:-$HOME/.local/bin}"
EXTRAS="${ASTA_EXTRAS:-}"
RUN=0
PYONLY=0
for arg in "$@"; do [ "$arg" = "--run" ] && RUN=1; [ "$arg" = "--python-only" ] && PYONLY=1; done

# Idioma dos textos = idioma do computador (pt ou en). ASTA_LANG=pt|en força. Vale também para o `asta` chamado daqui (ele lê ASTA_LANG).
detect_lang() {
  for v in "${ASTA_LANG:-}" "${LC_ALL:-}" "${LC_MESSAGES:-}" "${LANGUAGE:-}" "${LANG:-}"; do
    case "$v" in ""|C|POSIX|C.*) continue ;; pt*|PT*) echo pt; return ;; *) echo en; return ;; esac
  done
  if [ "$(uname -s)" = "Darwin" ] && command -v defaults >/dev/null 2>&1; then
    case "$(defaults read -g AppleLanguages 2>/dev/null | tr -d '() ",\n' | cut -c1-2)" in pt) echo pt; return ;; esac
  fi
  echo en
}
ASTA_L="$(detect_lang)"
export ASTA_LANG="$ASTA_L"
L() { if [ "$ASTA_L" = "pt" ]; then printf '%s' "$1"; else printf '%s' "$2"; fi; }

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
note() { printf '  %s\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

say "$(L "ASTA — instalação/atualização" "ASTA — install/update")"

# 1) Python 3.9+ — instala se faltar e atualiza (com o pip, o venv e as ferramentas de empacotamento) usando o gerenciador
#    de pacotes do sistema. Pode pedir a sua senha (sudo). ASTA_PYTHON=keep: nunca mexe no Python do sistema.
find_python() {
  PY=""
  for cand in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      PY="$cand"; return 0
    fi
  done
  return 1
}
as_root() {
  if [ "$(id -u)" = "0" ]; then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  else return 1; fi
}
# pkg_python install|upgrade → 0 se um gerenciador de pacotes concluiu; 1 se não há gerenciador/permissão/falhou
pkg_python() {
  mode="$1"
  case "$(uname -s)" in
    Darwin)
      command -v brew >/dev/null 2>&1 || return 1
      if [ "$mode" = "install" ]; then brew install python
      elif brew list --formula python >/dev/null 2>&1; then brew upgrade python || true; fi ;;
    *)
      if command -v apt-get >/dev/null 2>&1; then
        as_root apt-get update -qq && as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip
      elif command -v dnf >/dev/null 2>&1; then
        as_root dnf install -y python3 python3-pip && { [ "$mode" = "install" ] || as_root dnf upgrade -y python3 python3-pip; }
      elif command -v yum >/dev/null 2>&1; then
        as_root yum install -y python3 python3-pip && { [ "$mode" = "install" ] || as_root yum update -y python3 python3-pip; }
      elif command -v pacman >/dev/null 2>&1; then
        as_root pacman -S --noconfirm --needed python python-pip
      elif command -v zypper >/dev/null 2>&1; then
        as_root zypper --non-interactive install --no-recommends python3 python3-pip && { [ "$mode" = "install" ] || as_root zypper --non-interactive update python3 python3-pip; }
      elif command -v apk >/dev/null 2>&1; then
        as_root apk add --upgrade python3 py3-pip
      else return 1; fi ;;
  esac
}
python_hint() {
  case "$(uname -s)" in
    Darwin) echo "brew install python   (ou https://www.python.org/downloads/)" ;;
    *)      echo "sudo apt install python3 python3-venv python3-pip   (Debian/Ubuntu)  ·  sudo dnf install python3   (Fedora)  ·  sudo pacman -S python   (Arch)" ;;
  esac
}
PYMODE="${ASTA_PYTHON:-auto}"
if find_python; then
  if [ "$PYMODE" != "keep" ]; then
    PYBEFORE="$($PY --version 2>&1)"
    note "$(L "Python já instalado ($PYBEFORE) — verificando se há versão mais nova …" "Python already installed ($PYBEFORE) — checking for a newer version …")"
    pkg_python upgrade >/dev/null || note "$(L "Não foi possível atualizar o Python automaticamente (sem gerenciador de pacotes ou permissão); seguindo com o atual." "Could not update Python automatically (no package manager or permission); continuing with the current one.")"
    find_python || true   # a atualização pode ter trazido uma versão mais nova
    if [ "$($PY --version 2>&1)" != "$PYBEFORE" ]; then note "$(L "Python atualizado: $PYBEFORE → $($PY --version 2>&1)" "Python updated: $PYBEFORE → $($PY --version 2>&1)")"; else note "$(L "Python já está na versão mais recente disponível." "Python is already at the latest available version.")"; fi
  fi
else
  [ "$PYMODE" = "keep" ] && die "$(L "Python 3.9 ou superior não encontrado. Instale com: $(python_hint)" "Python 3.9 or newer not found. Install with: $(python_hint)")"
  note "$(L "Python 3.9+ não encontrado — instalando …" "Python 3.9+ not found — installing …")"
  pkg_python install >/dev/null || true
  find_python || die "$(L "Não consegui instalar o Python 3.9+ automaticamente. Instale com: $(python_hint)" "Could not install Python 3.9+ automatically. Install with: $(python_hint)")"
fi
note "$(L "Python: $($PY --version 2>&1)" "Python: $($PY --version 2>&1)")"

# 2) ambiente isolado (não suja o Python do sistema). Se o Python foi atualizado para uma versão mais nova, o ambiente é recriado.
mkdir -p "$APP_DIR"
PYV="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
VENVPY="$APP_DIR/venv/bin/python"
if [ -e "$APP_DIR/venv" ]; then
  VV="$("$VENVPY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
  if [ -z "$VV" ] || "$PY" -c 'import sys; a, b = (tuple(map(int, v.split("."))) for v in sys.argv[1:3]); sys.exit(0 if a < b else 1)' "$VV" "$PYV"; then
    note "$(L "Recriando o ambiente para o Python $PYV (antes: ${VV:-quebrado}) — as bibliotecas serão reinstaladas …" "Recreating the environment for Python $PYV (before: ${VV:-broken}) — the libraries will be reinstalled …")"
    rm -rf "$APP_DIR/venv"
  fi
fi
if [ -x "$VENVPY" ]; then
  note "$(L "Ambiente já existe ($APP_DIR/venv) — reaproveitando." "Environment already exists ($APP_DIR/venv) — reusing it.")"
else
  note "$(L "Criando ambiente em $APP_DIR/venv …" "Creating environment in $APP_DIR/venv …")"
  "$PY" -m venv "$APP_DIR/venv" >/dev/null 2>&1 || {
    rm -rf "$APP_DIR/venv"
    # Debian/Ubuntu: o módulo venv vem num pacote separado
    if [ "$PYMODE" != "keep" ] && pkg_python install >/dev/null 2>&1 && "$PY" -m venv "$APP_DIR/venv" >/dev/null 2>&1; then :; else
      rm -rf "$APP_DIR/venv"
      die "$(L "Não foi possível criar o ambiente virtual. No Debian/Ubuntu instale: sudo apt install python3-venv" "Could not create the virtual environment. On Debian/Ubuntu install: sudo apt install python3-venv")"
    fi
  }
fi
# ferramentas do Python (pip, setuptools, wheel) sempre na versão mais recente
"$VENVPY" -m pip install --upgrade --quiet --disable-pip-version-check pip setuptools wheel >/dev/null 2>&1 \
  || note "$(L "⚠ Não foi possível atualizar o pip/setuptools/wheel agora (sem internet?); seguindo." "⚠ Could not update pip/setuptools/wheel right now (no internet?); continuing.")"
if [ "${ASTA_STEP:-}" = "python" ] || [ "$PYONLY" = "1" ]; then say "$(L "✓ Python $PYV e ferramentas (pip, setuptools, wheel) prontos." "✓ Python $PYV and tools (pip, setuptools, wheel) ready.")"; exit 0; fi

# 3) instala / atualiza
SPEC="asta"
case "$SOURCE" in
  *://*|git+*) REQ="$SPEC @ $SOURCE" ;;
  /*|./*|../*|~*) REQ="$SPEC @ file://$(cd "$SOURCE" && pwd)" ;;
  *) REQ="$SOURCE" ;;
esac
OLD="$("$APP_DIR/venv/bin/python" -I -c 'import asta; print(asta.__version__)' 2>/dev/null || true)"
# Só baixa o ASTA se ele não está instalado ou se há uma versão mais nova. Com a origem padrão (ou ASTA_VERSION_URL) a versão publicada é
# consultada; com outra origem (ASTA_SOURCE) não há como saber, então instala. ASTA_FORCE=1 sempre reinstala.
SKIP_ASTA=0
if [ -n "$OLD" ] && [ -x "$APP_DIR/venv/bin/asta" ] && { [ "${ASTA_FORCE:-0}" = "0" ] || [ -z "${ASTA_FORCE:-}" ]; } && { [ -z "${ASTA_SOURCE:-}" ] || [ -n "${ASTA_VERSION_URL:-}" ]; }; then
  REMOTE="$(ASTA_VERSION_URL="${ASTA_VERSION_URL:-https://raw.githubusercontent.com/KMC1525/ASTA/main/asta/__init__.py}" "$APP_DIR/venv/bin/python" -I -c '
import os, re, urllib.request
try:
    with urllib.request.urlopen(os.environ["ASTA_VERSION_URL"], timeout=20) as r:
        m = re.search(r"__version__\s*=\s*[\"\x27]([^\"\x27]+)", r.read(8192).decode("utf-8", "replace"))
    print(m.group(1) if m else "")
except Exception:
    print("")
' 2>/dev/null || true)"
  if [ -n "$REMOTE" ] && "$APP_DIR/venv/bin/python" -I -c 'import re, sys
t = lambda v: tuple(int(x) for x in re.findall(r"\d+", v)[:4])
sys.exit(0 if t(sys.argv[1]) <= t(sys.argv[2]) else 1)' "$REMOTE" "$OLD"; then
    SKIP_ASTA=1
  fi
fi
if [ "$SKIP_ASTA" = "1" ]; then
  note "$(L "ASTA $OLD já instalado e na versão mais recente — nada a baixar." "ASTA $OLD already installed and up to date — nothing to download.")"
else
  note "$(L "Baixando e instalando ASTA …" "Downloading and installing ASTA …")"
  "$APP_DIR/venv/bin/python" -m pip install --upgrade --disable-pip-version-check --quiet --no-cache-dir "$REQ" \
    || die "$(L "Falha ao instalar. Verifique sua conexão e tente de novo." "Installation failed. Check your connection and try again.")"
fi
NEW="$("$APP_DIR/venv/bin/python" -I -c 'import asta; print(asta.__version__)')"

# 4) comando `asta`
mkdir -p "$BIN_DIR"
ln -sf "$APP_DIR/venv/bin/asta" "$BIN_DIR/asta"

# 5) bibliotecas do ASTA (todas, a menos que ASTA_EXTRAS diga outra coisa). A lista vem da versão recém-instalada.
LIBS_FAILED=0
case "$EXTRAS" in
  none|core) note "$(L "Bibliotecas opcionais: puladas (ASTA_EXTRAS=$EXTRAS)." "Optional libraries: skipped (ASTA_EXTRAS=$EXTRAS).")" ;;
  *) say "$(L "Bibliotecas do ASTA: instalo o que falta e atualizo o que tiver versão mais nova (a primeira vez pode demorar e baixar vários GB) …" "ASTA libraries: installing what is missing and updating what has a newer version (the first time can take long and download several GB) …")"
     if [ -n "$EXTRAS" ]; then ASTA_EXTRAS="$EXTRAS" "$APP_DIR/venv/bin/asta" libs || LIBS_FAILED=1
     else "$APP_DIR/venv/bin/asta" libs || LIBS_FAILED=1; fi ;;
esac

if [ -z "$OLD" ]; then say "$(L "✓ ASTA $NEW instalado." "✓ ASTA $NEW installed.")"; elif [ "$OLD" = "$NEW" ]; then say "$(L "✓ ASTA $NEW já estava atualizado." "✓ ASTA $NEW was already up to date.")"; else say "$(L "✓ ASTA atualizado: $OLD → $NEW." "✓ ASTA updated: $OLD → $NEW.")"; fi
# 6) modelos locais pré-instalados (texto e imagem). Sem ASTA_MODELS, o ASTA PERGUNTA no terminal (sim/não) antes de baixar; o que já está na pasta é pulado
MODELS_FAILED=0
case "${ASTA_MODELS:-ask}" in
  none|no|0) note "$(L "Modelos pré-instalados: pulados (ASTA_MODELS=${ASTA_MODELS})." "Pre-installed models: skipped (ASTA_MODELS=${ASTA_MODELS}).")" ;;
  ask) "$APP_DIR/venv/bin/asta" models install --ask || MODELS_FAILED=1 ;;
  *) say "$(L "Modelos locais pré-instalados: baixo só o que ainda não está na pasta (vários GB na primeira vez) …" "Pre-installed local models: downloading only what is not in the folder yet (several GB the first time) …")"
     "$APP_DIR/venv/bin/asta" models install || MODELS_FAILED=1 ;;
esac

# 7) Rust (opcional, deixa o ASTA mais rápido e leve): instala o Rust se faltar, atualiza se já existir e recompila o núcleo do ASTA.
#    ASTA_RUST=ask (padrão: pergunta no terminal; sem terminal só atualiza o que já existe, nunca instala sem permissão) | yes | no.
ASTA_RUST="${ASTA_RUST:-ask}" "$APP_DIR/venv/bin/asta" native setup || note "$(L "Rust: não foi possível concluir agora (opcional; o ASTA usa Python). Tente depois:  asta native setup" "Rust: could not finish right now (optional; ASTA uses Python). Try later:  asta native setup")"

if [ "$MODELS_FAILED" = "1" ]; then
  note "$(L "⚠ Alguns modelos pré-instalados não foram baixados (veja acima). O ASTA já funciona; para tentar de novo: asta models install" "⚠ Some pre-installed models were not downloaded (see above). ASTA already works; to try again: asta models install")"
fi
if [ "$LIBS_FAILED" = "1" ]; then
  note "$(L "⚠ Algumas bibliotecas opcionais não foram instaladas (veja acima). O ASTA já funciona; para tentar de novo: asta libs" "⚠ Some optional libraries were not installed (see above). ASTA already works; to try again: asta libs")"
fi
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) note "$(L "Adicione ao seu PATH para usar o comando 'asta':" "Add this to your PATH to use the 'asta' command:")"
     note "  echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.profile   $(L "(e abra um novo terminal)" "(and open a new terminal)")"
     note "$(L "Até lá, abra a WebUI com o caminho completo:  $BIN_DIR/asta" "Until then, open the WebUI with the full path:  $BIN_DIR/asta")" ;;
esac
echo
note "$(L "Para abrir a WebUI:   asta" "To open the WebUI:   asta")"
note "$(L "Para atualizar:       rode este mesmo comando de novo (ou: asta update) — atualiza o ASTA e as bibliotecas dele" "To update:            run this same command again (or: asta update) — it updates ASTA, its libraries and (optionally) Rust")"
echo

if [ "$RUN" = "1" ]; then exec "$APP_DIR/venv/bin/asta"; fi
