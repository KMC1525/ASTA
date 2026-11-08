#!/bin/bash
# ASTA — gera o instalador do macOS (.pkg) que coloca o ASTA.app em /Applications.
#
#   build-pkg.sh <versão> <saída.pkg> <núcleo-arm64.dylib> <núcleo-x86_64.dylib>
#
# O .app traz o código do ASTA, o instalador (install.sh) e o núcleo Rust para Apple Silicon e Intel; na primeira abertura ele instala o ASTA para o usuário (sem sudo).
# Sem certificado de desenvolvedor da Apple o pacote não é assinado: na primeira vez, clique com o botão direito no .pkg → Abrir (ou Ajustes → Privacidade e Segurança → «Abrir mesmo assim»).
set -euo pipefail
VERSION="${1:?versão}"; OUT="${2:?saída}"; CORE_ARM="${3:?núcleo arm64}"; CORE_X86="${4:?núcleo x86_64}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
APPDIR="$WORK/root/Applications/ASTA.app/Contents"
mkdir -p "$APPDIR/MacOS" "$APPDIR/Resources/native" "$APPDIR/Resources/asta-src"

sed "s/@VERSION@/$VERSION/g" "$HERE/Info.plist.in" > "$APPDIR/Info.plist"
cp "$HERE/launcher.sh" "$APPDIR/MacOS/ASTA"
chmod +x "$APPDIR/MacOS/ASTA"
cp "$ROOT/install.sh" "$APPDIR/Resources/install.sh"
cp "$CORE_ARM" "$APPDIR/Resources/native/asta-core-macos-aarch64.dylib"
cp "$CORE_X86" "$APPDIR/Resources/native/asta-core-macos-x86_64.dylib"
# o código do ASTA que o instalador usa (pip instala desta pasta)
cp "$ROOT/pyproject.toml" "$ROOT/LICENSE" "$ROOT/README.md" "$APPDIR/Resources/asta-src/"
rsync -a --exclude '__pycache__' --exclude 'target' --exclude '*.pyc' --exclude 'native/src' "$ROOT/asta" "$APPDIR/Resources/asta-src/"
mkdir -p "$APPDIR/Resources/asta-src/asta/native/src" && cp "$ROOT/asta/native/Cargo.toml" "$ROOT/asta/native/Cargo.lock" "$APPDIR/Resources/asta-src/asta/native/" && cp "$ROOT"/asta/native/src/*.rs "$APPDIR/Resources/asta-src/asta/native/src/"

# ícone (.icns) a partir do PNG do ASTA
ICONSET="$WORK/asta.iconset"
mkdir -p "$ICONSET"
for s in 16 32 64 128 256 512; do
  sips -z $s $s "$ROOT/asta/web/icons/icon-512.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$ROOT/asta/web/icons/icon-512.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
done
iconutil -c icns "$ICONSET" -o "$APPDIR/Resources/asta.icns"

mkdir -p "$(dirname "$OUT")"
pkgbuild --root "$WORK/root" --identifier org.asta.app --version "$VERSION" --install-location / "$WORK/ASTA-component.pkg"
productbuild --package "$WORK/ASTA-component.pkg" "$OUT"
echo "pronto: $OUT ($(du -h "$OUT" | cut -f1))"
