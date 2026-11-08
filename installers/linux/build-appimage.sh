#!/bin/sh
# ASTA — gera o AppImage (Linux): um arquivo só, com o Python e o ASTA dentro, sem instalar nada.
#
#   build-appimage.sh <versão> <saída.AppImage> <pasta-do-python-portátil> <biblioteca-do-núcleo-rust.so> [arquitetura]
#
# O Python portátil vem do python-build-standalone (a pasta que contém bin/python3 e lib/): ele traz pip e ssl, então `asta update` e `asta libs` funcionam dentro do AppImage
# (as bibliotecas opcionais vão para a pasta do usuário, ~/.asta/pyuser, porque o AppImage em si é somente leitura).
# Variáveis: APPIMAGETOOL=<caminho> usa uma appimagetool já baixada; sem ela o script baixa a oficial.
set -eu

VERSION="${1:?versão}"; OUT="${2:?arquivo de saída}"; PYDIR="${3:?pasta do python portátil}"; CORE="${4:?biblioteca do núcleo rust (.so)}"; ARCH="${5:-$(uname -m)}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
APPDIR="$WORK/ASTA.AppDir"

[ -x "$PYDIR/bin/python3" ] || { echo "python3 não encontrado em $PYDIR/bin" >&2; exit 1; }
[ -f "$CORE" ] || { echo "núcleo rust não encontrado: $CORE" >&2; exit 1; }

mkdir -p "$APPDIR/usr/python" "$APPDIR/usr/lib/asta-core"
cp -a "$PYDIR"/. "$APPDIR/usr/python/"

# o ASTA entra no site-packages do Python portátil (só a biblioteca padrão: sem dependências)
"$APPDIR/usr/python/bin/python3" -m pip install --no-deps --no-warn-script-location --disable-pip-version-check --quiet "$ROOT"
"$APPDIR/usr/python/bin/python3" -c "import asta; print('ASTA', asta.__version__, 'dentro do AppImage')"

cp "$CORE" "$APPDIR/usr/lib/asta-core/libasta_core.so"
cp "$HERE/AppRun" "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
sed "s/@VERSION@/$VERSION/" "$HERE/asta.desktop" > "$APPDIR/asta.desktop"
cp "$ROOT/asta/web/icons/icon-512.png" "$APPDIR/asta.png"
ln -sf asta.png "$APPDIR/.DirIcon"
mkdir -p "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp "$APPDIR/asta.desktop" "$APPDIR/usr/share/applications/asta.desktop"
cp "$ROOT/asta/web/icons/icon-512.png" "$APPDIR/usr/share/icons/hicolor/512x512/apps/asta.png"

# enxuga o que o ASTA não usa (testes, ferramentas de interface gráfica, caches): o arquivo final fica bem menor
find "$APPDIR/usr/python" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$APPDIR/usr/python/share" "$APPDIR/usr/python/lib/python3"*/test "$APPDIR/usr/python/lib/python3"*/idlelib "$APPDIR/usr/python/lib/python3"*/turtledemo \
       "$APPDIR/usr/python/lib/python3"*/tkinter "$APPDIR/usr/python/lib/tcl"* "$APPDIR/usr/python/lib/tk"* "$APPDIR/usr/python/lib/itcl"* 2>/dev/null || true

TOOL="${APPIMAGETOOL:-}"
if [ -z "$TOOL" ]; then
  TOOL="$WORK/appimagetool"
  curl -fsSL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$(uname -m).AppImage"
  chmod +x "$TOOL"
fi
mkdir -p "$(dirname "$OUT")"
# --appimage-extract-and-run: roda a appimagetool sem precisar do FUSE (contêineres e CI)
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
chmod +x "$OUT"
echo "AppImage pronto: $OUT ($(du -h "$OUT" | cut -f1))"
