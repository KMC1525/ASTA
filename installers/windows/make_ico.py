"""Gera o asta.ico (vários tamanhos) a partir do PNG do ASTA. Uso: make_ico.py <icon.png> <saida.ico>  (precisa do Pillow)."""
import sys

from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
img = Image.open(src).convert("RGBA")
img.save(dst, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("ícone gerado:", dst)
