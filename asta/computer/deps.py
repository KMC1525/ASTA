"""Bibliotecas e ferramentas de que o Computer Use depende — o que está instalado e o que falta (com o comando para instalar).

O núcleo não exige nenhuma biblioteca Python além da padrão. O resto são **opcionais**: melhoram a qualidade ou servem de plano B.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import importlib.util
import os
import shutil
import sys
from typing import Any, Dict, List


def _lib(name: str) -> bool:
    try:
        ctypes.CDLL(ctypes.util.find_library(name) or f"lib{name}.so.6")
        return True
    except OSError:
        return False


def report(driver_name: str) -> List[Dict[str, Any]]:
    """Cada item: {id, label, ok, required, hint, for}. `required` = o recurso não funciona sem isso neste sistema."""
    out: List[Dict[str, Any]] = []

    def add(i: str, label: str, ok: bool, required: bool, hint: str, use: str) -> None:
        out.append({"id": i, "label": label, "ok": bool(ok), "required": required, "hint": "" if ok else hint, "for": use})

    add("python", "Python 3.9+ (biblioteca padrão)", True, True, "", "todo o Computer Use")
    if driver_name == "linux":
        x = bool(os.environ.get("DISPLAY"))
        add("x11", "libX11 + libXtst (tela, teclado e mouse no X11)", _lib("X11") and _lib("Xtst"), x, "sudo apt install libx11-6 libxtst6  (Fedora: libX11 libXtst)", "ver a tela, digitar, teclas e mouse")
        add("xdg-open", "xdg-open (abrir arquivos e sites)", bool(shutil.which("xdg-open") or shutil.which("gio")), True, "sudo apt install xdg-utils", "abrir arquivos, sites e jogos de navegador")
        if os.environ.get("WAYLAND_DISPLAY"):
            add("wayland", "grim ou gnome-screenshot (captura no Wayland)", bool(shutil.which("grim") or shutil.which("gnome-screenshot")), False, "sudo apt install grim", "captura de tela no Wayland")
            add("ydotool", "ydotool ou wtype (teclado e mouse no Wayland)", bool(shutil.which("ydotool") or shutil.which("wtype")), False, "sudo apt install ydotool wtype", "teclado e mouse no Wayland")
    elif driver_name == "macos":
        add("screencapture", "screencapture e osascript (já vêm no macOS)", bool(shutil.which("screencapture") and shutil.which("osascript")), True, "Ferramentas do macOS ausentes: rode xcode-select --install ou reinstale o sistema", "ver a tela, digitar e teclas")
        add("cliclick", "cliclick (cliques mais firmes)", bool(shutil.which("cliclick")), False, "brew install cliclick", "clique com o botão direito e duplo clique")
    elif driver_name == "windows":
        add("powershell", "PowerShell (já vem no Windows)", bool(shutil.which("powershell") or shutil.which("pwsh")), True, "winget install Microsoft.PowerShell", "captura de tela e lista de programas")
    add("pillow", "Pillow (reduz a captura em telas grandes)", importlib.util.find_spec("PIL") is not None, False, 'pip install pillow   (ou: pip install "asta[computer]")', "enviar capturas leves ao modelo com visão")
    add("ffmpeg", "ffmpeg (plano B para reduzir a captura; converter mídia)", bool(shutil.which("ffmpeg")), False, "instale o ffmpeg (apt install ffmpeg · brew install ffmpeg · winget install ffmpeg)", "reduzir capturas, converter áudio e vídeo")
    add("pypdf", "pypdf (ler PDFs com mais precisão)", importlib.util.find_spec("pypdf") is not None, False, 'pip install pypdf   (ou: pip install "asta[docs]")', "ler PDFs")
    return out
