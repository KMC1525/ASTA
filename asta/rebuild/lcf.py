"""Leitor (só leitura) dos arquivos binários do RPG Maker 2000/2003 (formato LCF): mapas (.lmu) e a árvore de mapas (RPG_RT.lmt).

O formato é uma sequência de «blocos» (id, tamanho, dados) com números de tamanho variável (BER). Blocos desconhecidos são pulados pelo tamanho,
então diferenças entre versões não quebram a leitura; o que não for encontrado vira aviso, nunca erro.
"""
from __future__ import annotations

import struct
from typing import Any, Dict, Iterator, List, Optional, Tuple


def decode(b: bytes) -> str:
    for enc in ("utf-8", "cp932", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("latin-1")


class Reader:
    def __init__(self, buf: bytes, pos: int = 0, end: Optional[int] = None):
        self.buf, self.pos, self.end = buf, pos, len(buf) if end is None else end

    def eof(self) -> bool:
        return self.pos >= self.end

    def ber(self) -> int:
        v = 0
        for _ in range(10):
            if self.pos >= self.end:
                raise ValueError("arquivo cortado")
            b = self.buf[self.pos]
            self.pos += 1
            v = (v << 7) | (b & 0x7F)
            if not b & 0x80:
                return v
        raise ValueError("número inválido")

    def chunks(self) -> Iterator[Tuple[int, int, int]]:
        """(id, início, fim) de cada bloco até o terminador (id 0) ou o fim."""
        while not self.eof():
            cid = self.ber()
            if cid == 0:
                return
            n = self.ber()
            start = self.pos
            if start + n > self.end:
                raise ValueError("bloco maior que o arquivo")
            self.pos = start + n
            yield cid, start, start + n


def _header(buf: bytes, expect: str) -> int:
    r = Reader(buf)
    n = r.ber()
    name = buf[r.pos:r.pos + n].decode("ascii", "replace")
    if expect not in name:
        raise ValueError(f"não é um arquivo {expect}")
    return r.pos + n


def _int(buf: bytes, s: int, e: int) -> int:
    return Reader(buf, s, e).ber() if e > s else 0


def _array(buf: bytes, s: int, e: int):
    """Vetor LCF: contagem, depois (índice, struct de blocos terminada em 0) por elemento → (índice, início, fim)."""
    r = Reader(buf, s, e)
    out = []
    for _ in range(r.ber()):
        idx = r.ber()
        a = r.pos
        for _c in r.chunks():
            pass
        out.append((idx, a, r.pos))
    return out


def _commands(buf: bytes, s: int, e: int) -> List[Dict[str, Any]]:
    r = Reader(buf, s, e)
    out: List[Dict[str, Any]] = []
    while r.pos < r.end:
        try:
            code, indent = r.ber(), r.ber()
            n = r.ber()
            string = decode(buf[r.pos:r.pos + n])
            r.pos += n
            params = [r.ber() for _ in range(r.ber())]
        except ValueError:
            break
        out.append({"code": code, "indent": indent, "s": string, "p": params})
    return out


def read_map(buf: bytes) -> Dict[str, Any]:
    """Mapa .lmu → {width, height, chipset, lower, upper, events: [{id,name,x,y,pages:[{cond,trigger,list}]}]}."""
    r = Reader(buf, _header(buf, "LcfMapUnit"))
    m: Dict[str, Any] = {"width": 20, "height": 15, "chipset": 1, "lower": [], "upper": [], "events": []}
    for cid, s, e in r.chunks():
        if cid == 0x01:
            m["chipset"] = _int(buf, s, e)
        elif cid == 0x02:
            m["width"] = _int(buf, s, e)
        elif cid == 0x03:
            m["height"] = _int(buf, s, e)
        elif cid in (0x47, 0x48):
            n = (e - s) // 2
            m["lower" if cid == 0x47 else "upper"] = list(struct.unpack_from(f"<{n}H", buf, s))
        elif cid == 0x51:
            for eid, a, b in _array(buf, s, e):
                ev = {"id": eid, "name": "", "x": 0, "y": 0, "pages": []}
                for c2, s2, e2 in Reader(buf, a, b).chunks():
                    if c2 == 0x01:
                        ev["name"] = decode(buf[s2:e2])
                    elif c2 == 0x02:
                        ev["x"] = _int(buf, s2, e2)
                    elif c2 == 0x03:
                        ev["y"] = _int(buf, s2, e2)
                    elif c2 == 0x05:
                        for pid, pa, pb in _array(buf, s2, e2):
                            page: Dict[str, Any] = {"id": pid, "cond": {}, "trigger": 0, "list": []}
                            for c3, s3, e3 in Reader(buf, pa, pb).chunks():
                                if c3 == 0x02:
                                    for c4, s4, e4 in Reader(buf, s3, e3).chunks():
                                        page["cond"][c4] = _int(buf, s4, e4)
                                elif c3 == 0x21:
                                    page["trigger"] = _int(buf, s3, e3)
                                elif c3 == 0x33:
                                    page["list"] = _commands(buf, s3, e3)
                            ev["pages"].append(page)
                m["events"].append(ev)
    return m


def read_tree(buf: bytes) -> Dict[str, Any]:
    """RPG_RT.lmt → {maps: {id: nome}, start: {map, x, y}} (o que não achar fica de fora)."""
    out: Dict[str, Any] = {"maps": {}, "start": {}}
    r = Reader(buf, _header(buf, "LcfMapTree"))
    for cid, s, e in r.chunks():
        if cid == 0x01:
            for mid, a, b in _array(buf, s, e):
                for c2, s2, e2 in Reader(buf, a, b).chunks():
                    if c2 == 0x01:
                        out["maps"][mid] = decode(buf[s2:e2])
        elif cid == 0x04:
            for c2, s2, e2 in Reader(buf, s, e).chunks():
                if c2 in (1, 2, 3):
                    out["start"][{1: "map", 2: "x", 3: "y"}[c2]] = _int(buf, s2, e2)
    return out
