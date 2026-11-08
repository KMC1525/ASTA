"""Legendas do Studio (v0.17): ler/gerar SRT e WebVTT, quebrar um texto em legendas e alinhá-lo ao áudio pela fala (sem precisar de horários vindos do provedor).

Os provedores de transcrição devolvem só o texto; para virar legenda ele precisa de horários. `align` distribui as palavras pelos trechos em que há fala
(o inverso dos silêncios medidos no áudio), então as legendas começam e terminam onde a pessoa realmente fala.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

MAX_LINE = 42           # caracteres por linha
MAX_CUE_S = 5.5         # duração máxima de uma legenda
MIN_CUE_S = 0.8
_TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})")


def _secs(m: "re.Match[str]") -> float:
    h, mi, s, ms = int(m.group(1) or 0), int(m.group(2)), int(m.group(3)), int(m.group(4).ljust(3, "0")[:3])
    return h * 3600 + mi * 60 + s + ms / 1000.0


def parse(text: str, limit: int = 4000) -> List[Dict[str, Any]]:
    """Legendas de um arquivo SRT ou WebVTT: [{start, end, text}] em segundos. Linhas de numeração, cabeçalho e marcas HTML são ignorados; blocos inválidos são pulados."""
    out: List[Dict[str, Any]] = []
    for block in re.split(r"\r?\n\s*\r?\n", (text or "").replace("﻿", "").strip()):
        lines = [x for x in block.splitlines() if x.strip()]
        ix = next((i for i, x in enumerate(lines) if "-->" in x), -1)
        if ix < 0:
            continue
        a, _, b = lines[ix].partition("-->")
        ma, mb = _TIME.search(a), _TIME.search(b)
        if not ma or not mb:
            continue
        start, end = _secs(ma), _secs(mb)
        body = re.sub(r"<[^>]+>", "", "\n".join(lines[ix + 1:])).strip()
        if end > start and body:
            out.append({"start": round(start, 3), "end": round(end, 3), "text": body[:300]})
        if len(out) >= limit:
            break
    return out


def _stamp(t: float, sep: str) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def to_srt(cues: List[Dict[str, Any]], vtt: bool = False) -> str:
    """SRT (ou WebVTT) das legendas [{start, end|dur, text}] em ordem de tempo."""
    rows = sorted(({"s": float(c["start"]), "e": float(c["end"]) if "end" in c else float(c["start"]) + float(c["dur"]), "t": str(c["text"]).strip()} for c in cues if str(c.get("text", "")).strip()),
                  key=lambda r: r["s"])
    sep = "." if vtt else ","
    body = "\n".join(f"{i + 1}\n{_stamp(r['s'], sep)} --> {_stamp(r['e'], sep)}\n{r['t']}\n" for i, r in enumerate(rows))
    return ("WEBVTT\n\n" if vtt else "") + body


def split_cues(text: str) -> List[str]:
    """Quebra um texto em legendas curtas: frases, e frases longas em pedaços de até ~2 linhas de 42 caracteres, preferindo cortar em vírgulas e conjunções."""
    words_out: List[str] = []
    for sent in re.split(r"(?<=[.!?…])\s+|\n+", re.sub(r"[ \t]+", " ", text or "").strip()):
        sent = sent.strip()
        if not sent:
            continue
        cur: List[str] = []
        for w in sent.split():
            cur.append(w)
            line = " ".join(cur)
            if len(line) >= MAX_LINE * 2 - 8 or (len(line) >= MAX_LINE and w.endswith((",", ";", ":"))):
                words_out.append(line)
                cur = []
        if cur:
            tail = " ".join(cur)
            if words_out and len(tail) < 12 and len(words_out[-1]) + len(tail) < MAX_LINE * 2 and not words_out[-1].endswith((".", "!", "?", "…")):
                words_out[-1] += " " + tail   # sobra curtinha: junta à legenda anterior
            else:
                words_out.append(tail)
    return words_out


def wrap(text: str, width: int = MAX_LINE) -> str:
    """Quebra uma legenda em até duas linhas equilibradas."""
    if len(text) <= width or "\n" in text:
        return text
    words = text.split()
    best, best_d = text, 1 << 30
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        d = abs(len(a) - len(b))
        if max(len(a), len(b)) <= width + 8 and d < best_d:
            best, best_d = a + "\n" + b, d
    return best


def speech_spans(silences: List[Tuple[float, float]], total: float) -> List[Tuple[float, float]]:
    """O contrário dos silêncios: os trechos [início, fim] em que há fala."""
    spans: List[Tuple[float, float]] = []
    t = 0.0
    for s, e in sorted(silences):
        if s - t > 0.15:
            spans.append((t, s))
        t = max(t, e)
    if total - t > 0.15:
        spans.append((t, total))
    return spans or [(0.0, max(total, MIN_CUE_S))]


def align(text: str, spans: List[Tuple[float, float]], offset: float = 0.0) -> List[Dict[str, Any]]:
    """Legendas com horário: cada legenda recebe tempo de fala proporcional às suas letras e é colocada sobre os trechos com fala (nunca sobre o silêncio).
    `offset`: segundos somados a todos os horários (posição do clipe na timeline)."""
    pieces = split_cues(text)
    if not pieces:
        return []
    weights = [max(3, len(p)) for p in pieces]
    speech = sum(e - s for s, e in spans) or 1.0
    # posição de cada legenda no «tempo de fala» (sem silêncios), depois mapeada de volta ao tempo real
    def at(x: float) -> float:
        for s, e in spans:
            if x <= e - s + 1e-9:
                return s + x
            x -= e - s
        return spans[-1][1]

    out: List[Dict[str, Any]] = []
    done = 0.0
    total_w = float(sum(weights))
    for p, w in zip(pieces, weights):
        a, b = done / total_w * speech, (done + w) / total_w * speech
        done += w
        start, end = at(a), at(b)
        if end - start < MIN_CUE_S:
            end = start + MIN_CUE_S
        end = min(end, start + MAX_CUE_S) if end - start > MAX_CUE_S else end
        out.append({"start": round(start + offset, 3), "end": round(end + offset, 3), "text": wrap(p)})
    for a, b in zip(out, out[1:]):   # sem sobreposição entre legendas
        if a["end"] > b["start"]:
            a["end"] = round(max(a["start"] + 0.3, b["start"] - 0.02), 3)
    return out
