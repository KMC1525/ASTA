#!/bin/bash
# ASTA.app (macOS): na primeira vez instala o ASTA para o seu usuário (com progresso à vista, numa janela do Terminal); depois só abre. Fechar a janela do Terminal encerra o ASTA.
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
ASTA_DIR="$HOME/.asta"
APP="$ASTA_DIR/app"
mkdir -p "$ASTA_DIR"
CMD="$ASTA_DIR/launch.command"
case "$(uname -m)" in arm64) CORE="$RES/native/asta-core-macos-aarch64.dylib" ;; *) CORE="$RES/native/asta-core-macos-x86_64.dylib" ;; esac
if [ -x "$APP/venv/bin/asta" ]; then
  # já instalado: abre (o próprio asta se atualiza quando há versão nova)
  printf '#!/bin/bash\nclear\nexec "%s"\n' "$APP/venv/bin/asta" > "$CMD"
else
  # primeira vez: o instalador do ASTA a partir do que vem dentro deste app (sem baixar o ASTA; baixa só o Python, se faltar, e as bibliotecas opcionais)
  printf '#!/bin/bash\nclear\necho "ASTA — primeira instalação / first-time setup"\nASTA_SOURCE="%s" ASTA_NATIVE_FILE="%s" sh "%s" --run\n' "$RES/asta-src" "$CORE" "$RES/install.sh" > "$CMD"
fi
chmod +x "$CMD"
exec open -a Terminal "$CMD"
