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
#   ASTA_PYTHON=auto|keep               auto (padrão): instala o Python se faltar e o atualiza (com pip, venv, setuptools e wheel)
#                                       pelo gerenciador de pacotes do sistema (apt, dnf, yum, pacman, zypper, apk, Homebrew).
#                                       keep: nunca mexe no Python do sistema.
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

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
note() { printf '  %s\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

say "ASTA — instalação/atualização"

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
    note "Verificando atualizações do Python ($($PY --version 2>&1)) …"
    pkg_python upgrade >/dev/null || note "Não foi possível atualizar o Python automaticamente (sem gerenciador de pacotes ou permissão); seguindo com o atual."
    find_python || true   # a atualização pode ter trazido uma versão mais nova
  fi
else
  [ "$PYMODE" = "keep" ] && die "Python 3.9 ou superior não encontrado. Instale com: $(python_hint)"
  note "Python 3.9+ não encontrado — instalando …"
  pkg_python install >/dev/null || true
  find_python || die "Não consegui instalar o Python 3.9+ automaticamente. Instale com: $(python_hint)"
fi
note "Python: $($PY --version 2>&1)"

# 2) ambiente isolado (não suja o Python do sistema). Se o Python foi atualizado para uma versão mais nova, o ambiente é recriado.
mkdir -p "$APP_DIR"
PYV="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
VENVPY="$APP_DIR/venv/bin/python"
if [ -e "$APP_DIR/venv" ]; then
  VV="$("$VENVPY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
  if [ -z "$VV" ] || "$PY" -c 'import sys; a, b = (tuple(map(int, v.split("."))) for v in sys.argv[1:3]); sys.exit(0 if a < b else 1)' "$VV" "$PYV"; then
    note "Recriando o ambiente para o Python $PYV (antes: ${VV:-quebrado}) — as bibliotecas serão reinstaladas …"
    rm -rf "$APP_DIR/venv"
  fi
fi
if [ ! -x "$VENVPY" ]; then
  note "Criando ambiente em $APP_DIR/venv …"
  "$PY" -m venv "$APP_DIR/venv" >/dev/null 2>&1 || {
    rm -rf "$APP_DIR/venv"
    # Debian/Ubuntu: o módulo venv vem num pacote separado
    if [ "$PYMODE" != "keep" ] && pkg_python install >/dev/null 2>&1 && "$PY" -m venv "$APP_DIR/venv" >/dev/null 2>&1; then :; else
      rm -rf "$APP_DIR/venv"
      die "Não foi possível criar o ambiente virtual. No Debian/Ubuntu instale: sudo apt install python3-venv"
    fi
  }
fi
# ferramentas do Python (pip, setuptools, wheel) sempre na versão mais recente
"$VENVPY" -m pip install --upgrade --quiet --disable-pip-version-check pip setuptools wheel >/dev/null 2>&1 \
  || note "⚠ Não foi possível atualizar o pip/setuptools/wheel agora (sem internet?); seguindo."
if [ "${ASTA_STEP:-}" = "python" ] || [ "$PYONLY" = "1" ]; then say "✓ Python $PYV e ferramentas (pip, setuptools, wheel) prontos."; exit 0; fi

# 3) instala / atualiza
SPEC="asta"
case "$SOURCE" in
  *://*|git+*) REQ="$SPEC @ $SOURCE" ;;
  /*|./*|../*|~*) REQ="$SPEC @ file://$(cd "$SOURCE" && pwd)" ;;
  *) REQ="$SOURCE" ;;
esac
OLD="$("$APP_DIR/venv/bin/python" -I -c 'import asta; print(asta.__version__)' 2>/dev/null || true)"
note "Baixando e instalando ASTA …"
"$APP_DIR/venv/bin/python" -m pip install --upgrade --disable-pip-version-check --quiet --no-cache-dir "$REQ" \
  || die "Falha ao instalar. Verifique sua conexão e tente de novo."
NEW="$("$APP_DIR/venv/bin/python" -I -c 'import asta; print(asta.__version__)')"

# 4) comando `asta`
mkdir -p "$BIN_DIR"
ln -sf "$APP_DIR/venv/bin/asta" "$BIN_DIR/asta"

# 5) bibliotecas do ASTA (todas, a menos que ASTA_EXTRAS diga outra coisa). A lista vem da versão recém-instalada.
LIBS_FAILED=0
case "$EXTRAS" in
  none|core) note "Bibliotecas opcionais: puladas (ASTA_EXTRAS=$EXTRAS)." ;;
  *) say "Instalando/atualizando as bibliotecas do ASTA (a primeira vez pode demorar e baixar vários GB) …"
     if [ -n "$EXTRAS" ]; then ASTA_EXTRAS="$EXTRAS" "$APP_DIR/venv/bin/asta" libs || LIBS_FAILED=1
     else "$APP_DIR/venv/bin/asta" libs || LIBS_FAILED=1; fi ;;
esac

if [ -z "$OLD" ]; then say "✓ ASTA $NEW instalado."; elif [ "$OLD" = "$NEW" ]; then say "✓ ASTA $NEW já estava atualizado (arquivos reinstalados)."; else say "✓ ASTA atualizado: $OLD → $NEW."; fi
if [ "$LIBS_FAILED" = "1" ]; then
  note "⚠ Algumas bibliotecas opcionais não foram instaladas (veja acima). O ASTA já funciona; para tentar de novo: asta libs"
fi
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) note "Adicione ao seu PATH para usar o comando 'asta':"
     note "  echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.profile   (e abra um novo terminal)" ;;
esac
echo
note "Para abrir a WebUI:   asta"
note "Para atualizar:       rode este mesmo comando de novo (ou: asta update) — atualiza o ASTA e as bibliotecas dele"
echo

if [ "$RUN" = "1" ]; then exec "$APP_DIR/venv/bin/asta"; fi
