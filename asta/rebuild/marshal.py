"""Leitor do formato Marshal do Ruby (versão 4.8) — o que o RPG Maker XP, VX e VX Ace usam nos arquivos .rxdata/.rvdata/.rvdata2.

Só leitura, sem executar nada: objetos viram `RObj` (classe + variáveis de instância), tabelas (`Table`) viram listas.
"""
from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional


class RObj:
    __slots__ = ("cls", "iv", "data")

    def __init__(self, cls: str, iv: Optional[Dict[str, Any]] = None, data: Any = None):
        self.cls, self.iv, self.data = cls, iv if iv is not None else {}, data

    def get(self, name: str, default: Any = None) -> Any:
        return self.iv.get(name if name.startswith("@") else "@" + name, default)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.cls} {list(self.iv)[:6]}>"


class MarshalError(ValueError):
    pass


def _text(b: bytes, utf8: Optional[bool]) -> str:
    if utf8 is not False:
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            pass
    for enc in ("cp932", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("latin-1")


def loads(data: bytes, max_objects: int = 3_000_000) -> Any:
    if data[:2] != b"\x04\x08":
        raise MarshalError("não é um arquivo Marshal do Ruby (4.8)")
    pos = 2
    syms: List[str] = []
    objs: List[Any] = []

    def byte() -> int:
        nonlocal pos
        if pos >= len(data):
            raise MarshalError("arquivo cortado")
        b = data[pos]
        pos += 1
        return b

    def integer() -> int:
        nonlocal pos
        c = byte()
        c = c - 256 if c > 127 else c
        if c == 0:
            return 0
        if 4 < c < 128:
            return c - 5
        if -129 < c < -4:
            return c + 5
        n = abs(c)
        raw = data[pos:pos + n]
        if len(raw) < n:
            raise MarshalError("arquivo cortado")
        pos += n
        x = int.from_bytes(raw, "little")
        if c < 0:
            x -= 1 << (8 * n)
        return x

    def raw_bytes() -> bytes:
        nonlocal pos
        n = integer()
        if n < 0 or pos + n > len(data):
            raise MarshalError("arquivo cortado")
        b = data[pos:pos + n]
        pos += n
        return b

    def symbol() -> str:
        t = chr(byte())
        if t == ":":
            s = _text(raw_bytes(), True)
            syms.append(s)
            return s
        if t == ";":
            return syms[integer()]
        raise MarshalError("símbolo esperado")

    def reg(o: Any) -> int:
        if len(objs) > max_objects:
            raise MarshalError("arquivo grande demais")
        objs.append(o)
        return len(objs) - 1

    def ivars(target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for _ in range(integer()):
            k = symbol()
            out[k] = value()
        if target is not None:
            target.update(out)
        return out

    def value() -> Any:
        t = chr(byte())
        if t == "0":
            return None
        if t == "T":
            return True
        if t == "F":
            return False
        if t == "i":
            return integer()
        if t == ":":
            nonlocal pos
            pos -= 1
            return symbol()
        if t == ";":
            pos -= 1
            return symbol()
        if t == "@":
            return objs[integer()]
        if t == "I":
            # objeto com variáveis de instância (strings guardam a codificação aqui)
            start = pos
            inner_t = chr(data[pos]) if pos < len(data) else ""
            if inner_t == '"':
                pos += 1
                idx = reg(None)
                b = raw_bytes()
                iv = ivars(None)
                enc = iv.get("E", iv.get("encoding"))
                s = _text(b, True if enc is True else (False if enc is False else None))
                objs[idx] = s
                return s
            obj = value()
            ivars(obj.iv if isinstance(obj, RObj) else None)
            return obj
        if t == '"':
            idx = reg(None)
            s = _text(raw_bytes(), None)
            objs[idx] = s
            return s
        if t == "[":
            arr: List[Any] = []
            reg(arr)
            for _ in range(integer()):
                arr.append(value())
            return arr
        if t in "{}":
            h: Dict[Any, Any] = {}
            reg(h)
            for _ in range(integer()):
                k = value()
                h[k if isinstance(k, (str, int, float, bool, type(None))) else repr(k)] = value()
            if t == "}":
                value()
            return h
        if t == "o":
            name = symbol()
            o = RObj(name)
            reg(o)
            ivars(o.iv)
            return o
        if t == "u":
            name = symbol()
            o = RObj(name, data=raw_bytes())
            reg(o)
            return o
        if t == "U":
            name = symbol()
            o = RObj(name)
            reg(o)
            o.data = value()
            return o
        if t == "S":
            name = symbol()
            o = RObj(name)
            reg(o)
            ivars(o.iv)
            return o
        if t == "C":
            symbol()
            return value()
        if t == "e":
            symbol()
            return value()
        if t == "f":
            s = raw_bytes().decode("ascii", "replace")
            f = {"inf": float("inf"), "-inf": float("-inf"), "nan": float("nan")}.get(s)
            if f is None:
                try:
                    f = float(s)
                except ValueError:
                    f = 0.0
            reg(f)
            return f
        if t == "l":
            sign = chr(byte())
            n = integer() * 2
            x = int.from_bytes(data[pos:pos + n], "little")
            pos += n
            x = -x if sign == "-" else x
            reg(x)
            return x
        if t in "cmM":
            s = _text(raw_bytes(), True)
            reg(s)
            return s
        if t == "/":
            s = _text(raw_bytes(), None)
            byte()
            reg(s)
            return s
        raise MarshalError(f"tipo desconhecido no Marshal: {t!r}")

    return value()


def table(o: Any):
    """Decodifica um RPG::Table: devolve (xsize, ysize, zsize, valores) — índice = x + y*xsize + z*xsize*ysize."""
    if not isinstance(o, RObj) or not isinstance(o.data, (bytes, bytearray)) or len(o.data) < 20:
        return 0, 0, 0, []
    _dim, xs, ys, zs, size = struct.unpack_from("<5i", o.data, 0)
    size = max(0, min(size, (len(o.data) - 20) // 2))
    return xs, ys, zs, list(struct.unpack_from(f"<{size}h", o.data, 20))
