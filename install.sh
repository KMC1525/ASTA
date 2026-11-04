#!/bin/sh
# ASTA — instalador/atualizador para Linux e macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/KMC1525/ASTA/main/install.sh | sh
#
# O MESMO comando instala e atualiza. Seus dados (~/.asta: personagens, mundos,
# configurações) nunca são tocados. Opções (variáveis de ambiente):
#   ASTA_EXTRAS=local|docs|local,docs   instala extras opcionais (modelos GGUF locais / PDFs)
#   ASTA_SOURCE=<url|pasta|requisito>   instala de outra origem (padrão: GitHub, branch main)
#   ASTA_APP_DIR=<pasta>                onde fica o programa (padrão: ~/.asta/app)
#   ASTA_BIN_DIR=<pasta>                onde fica o comando `asta` (padrão: ~/.local/bin)
# Argumento:  sh -s -- --run   → inicia o ASTA ao terminar.
set -eu

SOURCE="${ASTA_SOURCE:-https://github.com/KMC1525/ASTA/archive/refs/heads/main.zip}"
APP_DIR="${ASTA_APP_DIR:-$HOME/.asta/app}"
BIN_DIR="${ASTA_BIN_DIR:-$HOME/.local/bin}"
EXTRAS="${ASTA_EXTRAS:-}"
RUN=0
for arg in "$@"; do [ "$arg" = "--run" ] && RUN=1; done

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
note() { printf '  %s\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

say "ASTA — instalação/atualização"

# 1) Python 3.9+
PY=""
for cand in python3 python python3.13 python3.12 python3.11 python3.10 python3.9; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  case "$(uname -s)" in
    Darwin) hint="brew install python   (ou https://www.python.org/downloads/)" ;;
    *)      hint="sudo apt install python3 python3-venv   (Debian/Ubuntu)  ·  sudo dnf install python3   (Fedora)  ·  sudo pacman -S python   (Arch)" ;;
  esac
  die "Python 3.9 ou superior não encontrado. Instale com: $hint"
fi
note "Python: $($PY --version 2>&1)"

# 2) ambiente isolado (não suja o Python do sistema)
mkdir -p "$APP_DIR"
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  note "Criando ambiente em $APP_DIR/venv …"
  "$PY" -m venv "$APP_DIR/venv" >/dev/null 2>&1 || {
    rm -rf "$APP_DIR/venv"
    die "Não foi possível criar o ambiente virtual. No Debian/Ubuntu instale: sudo apt install python3-venv"
  }
fi

# 3) instala / atualiza
SPEC="asta"
[ -n "$EXTRAS" ] && SPEC="asta[$EXTRAS]"
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

if [ -z "$OLD" ]; then say "✓ ASTA $NEW instalado."; elif [ "$OLD" = "$NEW" ]; then say "✓ ASTA $NEW já estava atualizado (arquivos reinstalados)."; else say "✓ ASTA atualizado: $OLD → $NEW."; fi
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) note "Adicione ao seu PATH para usar o comando 'asta':"
     note "  echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.profile   (e abra um novo terminal)" ;;
esac
echo
note "Para abrir a WebUI:   asta"
note "Para atualizar:       rode este mesmo comando de novo (ou: asta update)"
echo

if [ "$RUN" = "1" ]; then exec "$APP_DIR/venv/bin/asta"; fi
