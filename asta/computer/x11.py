"""Tela, teclado e mouse no Linux/X11 **sem instalar nada**: fala direto com a libX11 e a libXtst (que já vêm em qualquer desktop X11) por `ctypes`.

* captura da tela com `XGetImage` e gravação de PNG com `zlib` (biblioteca padrão);
* digitar e apertar teclas com a extensão XTEST (`XTestFakeKeyEvent`), inclusive acentos e qualquer caractere Unicode (teclas livres são remapeadas por um instante);
* mover, clicar e rolar o mouse com `XTestFakeMotionEvent` / `XTestFakeButtonEvent`.

Se as bibliotecas ou o servidor X não existirem (sem desktop, Wayland puro), `available()` devolve o motivo e o driver cai para ferramentas externas (xdotool, grim…).
Num desktop Wayland com XWayland, o XTEST só alcança janelas X: nesse caso as ferramentas do próprio Wayland têm prioridade (ver `LinuxDriver`).
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import struct
import threading
import time
import zlib
from pathlib import Path
from typing import Optional, Tuple

_lock = threading.Lock()
_libs: Optional[Tuple[ctypes.CDLL, ctypes.CDLL]] = None
_err = ""

SPECIAL = {"Return": 0xFF0D, "Escape": 0xFF1B, "Tab": 0xFF09, "space": 0x20, "BackSpace": 0xFF08, "Delete": 0xFFFF, "Insert": 0xFF63, "Up": 0xFF52, "Down": 0xFF54, "Left": 0xFF51,
           "Right": 0xFF53, "Home": 0xFF50, "End": 0xFF57, "Prior": 0xFF55, "Next": 0xFF56, "Caps_Lock": 0xFFE5, "Print": 0xFF61}
MODS = {"ctrl": 0xFFE3, "alt": 0xFFE9, "shift": 0xFFE1, "super": 0xFFEB}


class X11Error(Exception):
    pass


def _load() -> Tuple[ctypes.CDLL, ctypes.CDLL]:
    global _libs, _err
    if _libs:
        return _libs
    if _err:
        raise X11Error(_err)
    try:
        x = ctypes.util.find_library("X11") or "libX11.so.6"
        t = ctypes.util.find_library("Xtst") or "libXtst.so.6"
        libx, libt = ctypes.CDLL(x), ctypes.CDLL(t)
    except OSError as exc:
        _err = f"libX11/libXtst não encontradas ({exc})"
        raise X11Error(_err) from None
    libx.XOpenDisplay.restype = ctypes.c_void_p
    libx.XOpenDisplay.argtypes = [ctypes.c_char_p]
    libx.XCloseDisplay.argtypes = [ctypes.c_void_p]
    libx.XDefaultRootWindow.restype = ctypes.c_ulong
    libx.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    libx.XDefaultScreen.argtypes = [ctypes.c_void_p]
    libx.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
    libx.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
    libx.XGetImage.restype = ctypes.c_void_p
    libx.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    libx.XDestroyImage.argtypes = [ctypes.c_void_p]
    libx.XKeysymToKeycode.restype = ctypes.c_ubyte
    libx.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    libx.XKeycodeToKeysym.restype = ctypes.c_ulong
    libx.XKeycodeToKeysym.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_int]
    libx.XDisplayKeycodes.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    libx.XGetKeyboardMapping.restype = ctypes.POINTER(ctypes.c_ulong)
    libx.XGetKeyboardMapping.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    libx.XChangeKeyboardMapping.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_ulong), ctypes.c_int]
    libx.XFree.argtypes = [ctypes.c_void_p]
    libx.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    libx.XFlush.argtypes = [ctypes.c_void_p]
    libt.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    libt.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    libt.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
    _libs = (libx, libt)
    return _libs


class _Image(ctypes.Structure):
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int), ("xoffset", ctypes.c_int), ("format", ctypes.c_int), ("data", ctypes.c_void_p), ("byte_order", ctypes.c_int),
                ("bitmap_unit", ctypes.c_int), ("bitmap_bit_order", ctypes.c_int), ("bitmap_pad", ctypes.c_int), ("depth", ctypes.c_int), ("bytes_per_line", ctypes.c_int),
                ("bits_per_pixel", ctypes.c_int), ("red_mask", ctypes.c_ulong), ("green_mask", ctypes.c_ulong), ("blue_mask", ctypes.c_ulong)]


def available() -> str:
    """"" se der para usar o X11 agora; senão, o motivo."""
    if not os.environ.get("DISPLAY"):
        return "sem DISPLAY (nenhum desktop X11 nesta sessão)"
    try:
        libx, libt = _load()
    except X11Error as exc:
        return str(exc)
    with _lock:
        d = libx.XOpenDisplay(None)
        if not d:
            return "não consegui abrir o servidor X (DISPLAY inválido ou sem permissão)"
        libx.XCloseDisplay(d)
    return ""


class _Conn:
    def __enter__(self):
        _lock.acquire()
        try:
            self.x, self.t = _load()
            self.d = self.x.XOpenDisplay(None)
            if not self.d:
                raise X11Error("não consegui abrir o servidor X")
        except BaseException:
            _lock.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            self.x.XCloseDisplay(self.d)
        finally:
            _lock.release()


def screen_size() -> Tuple[int, int]:
    with _Conn() as c:
        s = c.x.XDefaultScreen(c.d)
        return int(c.x.XDisplayWidth(c.d, s)), int(c.x.XDisplayHeight(c.d, s))


def _png(rgb: bytes, w: int, h: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    stride = w * 3
    raw = b"".join(b"\x00" + rgb[y * stride:(y + 1) * stride] for y in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 3)) + chunk(b"IEND", b"")


def screenshot(dest: Path) -> Tuple[int, int]:
    with _Conn() as c:
        s = c.x.XDefaultScreen(c.d)
        w, h = int(c.x.XDisplayWidth(c.d, s)), int(c.x.XDisplayHeight(c.d, s))
        img_p = c.x.XGetImage(c.d, c.x.XDefaultRootWindow(c.d), 0, 0, w, h, ctypes.c_ulong(~0 & 0xFFFFFFFFFFFFFFFF).value, 2)
        if not img_p:
            raise X11Error("o servidor X recusou a captura da tela")
        try:
            img = ctypes.cast(img_p, ctypes.POINTER(_Image)).contents
            bpp, bpl = img.bits_per_pixel, img.bytes_per_line
            if bpp not in (24, 32):
                raise X11Error(f"formato de tela sem suporte ({bpp} bits por pixel)")
            buf = ctypes.string_at(img.data, bpl * h)
            step = bpp // 8
            rm, gm, bm = img.red_mask, img.green_mask, img.blue_mask
            little = img.byte_order == 0
            # posição de cada canal dentro dos bytes do pixel (o caso comum é BGRX: azul no byte 0)
            def pos(mask: int) -> int:
                shift = (mask & -mask).bit_length() - 1
                idx = shift // 8
                return idx if little else step - 1 - idx
            pr, pg, pb = pos(rm), pos(gm), pos(bm)
            out = bytearray(w * h * 3)
            for y in range(h):
                row = buf[y * bpl:y * bpl + w * step]
                o = y * w * 3
                out[o:o + w * 3:3] = row[pr::step][:w]
                out[o + 1:o + w * 3:3] = row[pg::step][:w]
                out[o + 2:o + w * 3:3] = row[pb::step][:w]
        finally:
            c.x.XDestroyImage(img_p)
    dest.write_bytes(_png(bytes(out), w, h))
    return w, h


# ----- teclado

def _keysym_for_char(ch: str) -> int:
    o = ord(ch)
    if ch == "\n":
        return SPECIAL["Return"]
    if ch == "\t":
        return SPECIAL["Tab"]
    if 0x20 <= o <= 0x7E or 0xA0 <= o <= 0xFF:
        return o
    return 0x01000000 + o


def _key(c: _Conn, keysym: int, down: bool) -> None:
    kc = c.x.XKeysymToKeycode(c.d, keysym)
    if kc:
        c.t.XTestFakeKeyEvent(c.d, kc, 1 if down else 0, 0)


def _tap_keysym(c: _Conn, keysym: int, hold: Tuple[int, ...] = ()) -> None:
    """Aperta e solta um keysym (com Shift se ele estiver na camada de cima da tecla). Sem tecla no teclado: usa uma tecla livre por um instante."""
    kc = c.x.XKeysymToKeycode(c.d, keysym)
    shift = False
    temp = None
    if kc:
        shift = c.x.XKeycodeToKeysym(c.d, kc, 0) != keysym and c.x.XKeycodeToKeysym(c.d, kc, 1) == keysym
    else:
        lo, hi = ctypes.c_int(), ctypes.c_int()
        c.x.XDisplayKeycodes(c.d, ctypes.byref(lo), ctypes.byref(hi))
        n = ctypes.c_int()
        m = c.x.XGetKeyboardMapping(c.d, lo.value, hi.value - lo.value + 1, ctypes.byref(n))
        per = n.value
        free = None
        for i in range(hi.value - lo.value, -1, -1):   # de trás para frente: teclas livres costumam ficar no fim
            if all(m[i * per + j] == 0 for j in range(per)):
                free = lo.value + i
                break
        c.x.XFree(ctypes.cast(m, ctypes.c_void_p))
        if free is None:
            raise X11Error("sem tecla livre para digitar este caractere")
        syms = (ctypes.c_ulong * 2)(keysym, keysym)   # nas duas camadas: sem isto o X converte maiúsculas em minúsculas
        c.x.XChangeKeyboardMapping(c.d, free, 2, syms, 1)
        c.x.XSync(c.d, 0)
        time.sleep(0.03)   # o cliente precisa reler o mapa de teclas antes da tecla chegar
        kc, temp = free, free
    for h in hold:
        _key(c, h, True)
    if shift:
        _key(c, MODS["shift"], True)
    c.t.XTestFakeKeyEvent(c.d, kc, 1, 0)
    c.t.XTestFakeKeyEvent(c.d, kc, 0, 0)
    if shift:
        _key(c, MODS["shift"], False)
    for h in reversed(hold):
        _key(c, h, False)
    c.x.XSync(c.d, 0)
    if temp is not None:
        time.sleep(0.03)   # só desfaz o mapeamento depois que o cliente tratou a tecla
        zero = (ctypes.c_ulong * 2)(0, 0)
        c.x.XChangeKeyboardMapping(c.d, temp, 2, zero, 1)
        c.x.XSync(c.d, 0)


def type_text(text: str) -> None:
    with _Conn() as c:
        for ch in text.replace("\r\n", "\n"):
            _tap_keysym(c, _keysym_for_char(ch))
            time.sleep(0.008)


def press_keys(mods: list, key: str) -> None:
    if key in SPECIAL:
        sym = SPECIAL[key]
    elif key.startswith("F") and key[1:].isdigit():
        sym = 0xFFBE + int(key[1:]) - 1
    elif len(key) == 1:
        sym = _keysym_for_char(key)
    else:
        raise X11Error(f"tecla desconhecida: {key}")
    with _Conn() as c:
        _tap_keysym(c, sym, tuple(MODS[m] for m in mods))


# ----- mouse

def click(x: int, y: int, button: int = 1, double: bool = False) -> None:
    with _Conn() as c:
        c.t.XTestFakeMotionEvent(c.d, -1, int(x), int(y), 0)
        c.x.XSync(c.d, 0)
        time.sleep(0.03)
        for _ in range(2 if double else 1):
            c.t.XTestFakeButtonEvent(c.d, button, 1, 0)
            c.t.XTestFakeButtonEvent(c.d, button, 0, 0)
            c.x.XSync(c.d, 0)
            time.sleep(0.05)


def scroll(dy: int) -> None:
    with _Conn() as c:
        for _ in range(max(1, min(30, abs(int(dy))))):
            c.t.XTestFakeButtonEvent(c.d, 5 if dy > 0 else 4, 1, 0)
            c.t.XTestFakeButtonEvent(c.d, 5 if dy > 0 else 4, 0, 0)
        c.x.XSync(c.d, 0)
