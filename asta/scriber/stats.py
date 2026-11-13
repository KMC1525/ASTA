"""Scriber — estatísticas do texto (v0.23): palavras, frases, tempo de leitura, legibilidade (Flesch), palavras mais repetidas e frases longas.

Determinístico, sem IA e sem internet (planejar → contar → conferir: a soma das palavras dos parágrafos bate com o total). Os resultados são números e *códigos*
(`level`), a tela escreve e traduz as frases. A legibilidade usa a fórmula de Flesch com a constante de cada idioma (en: 206,835; pt/es/fr…: ajustes publicados)
e uma contagem de sílabas por grupos de vogais — é uma **estimativa**, boa para comparar versões do mesmo texto, não um número exato."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List

from .schema import lang_base, norm_lang

MAX_PARAS = 4000
MAX_CHARS = 400_000
WPM = 200                  # leitura silenciosa média (palavras por minuto)
LONG_SENTENCE = 40         # palavras
TOP_WORDS = 12
_WORD = re.compile(r"[^\W\d_][\w'’\-]*", re.U)
_SENT = re.compile(r"[^.!?…]+[.!?…]*", re.U)
_VOWELS = re.compile(r"[aeiouyáàâãäéèêëíìîïóòôõöúùûü]+", re.I)
#: constante de Flesch por idioma (206,835 em inglês; 248,835 em português — Martins et al.; espanhol/francês/italiano: ajustes usuais)
_FLESCH = {"en": 206.835, "pt": 248.835, "es": 206.84, "fr": 207.0, "it": 217.0, "de": 180.0}
_STOP = {
    "pt": "que de da do das dos para com uma uns umas por mais mas como foi era ele ela eles elas seu sua seus suas nos nas num numa isso isto esse essa esses essas aquele aquela quando onde porque também ainda já só então muito muita depois antes sobre entre até sem sob".split(),
    "en": "that this with have from they were been their there which would about could should into than then them these those what when where while will your you and the for are but not was had has his her its our out all can one just also only very over more some such".split(),
    "es": "que los las del con una unos unas por para como más pero fue era ellos ellas sus nos esto eso este esta esos esas cuando donde porque también ya solo entonces muy después antes sobre entre hasta sin".split(),
}


def syllables(word: str) -> int:
    """Sílabas por grupos de vogais (mínimo 1). Boa para estimar legibilidade em idiomas latinos e no inglês."""
    return max(1, len(_VOWELS.findall(word)))


def _label(score: float) -> str:
    if score >= 90:
        return "very_easy"
    if score >= 70:
        return "easy"
    if score >= 50:
        return "medium"
    if score >= 30:
        return "hard"
    return "very_hard"


def analyze(paragraphs: Any, language: Any = None) -> Dict[str, Any]:
    ps = [str(x) for x in (paragraphs if isinstance(paragraphs, list) else [])][:MAX_PARAS]
    truncated = len(paragraphs or []) > MAX_PARAS if isinstance(paragraphs, list) else False
    used, budget = [], MAX_CHARS
    for x in ps:
        if budget <= 0:
            truncated = True
            break
        used.append(x.replace(" ", " ")[:budget])
        budget -= len(x)
    lang = lang_base(norm_lang(language)) if language else "pt"
    words_total, sentences, syl_total, chars = 0, 0, 0, 0
    counts: Counter = Counter()
    longest: List[Dict[str, Any]] = []
    para_words = []
    for pi, para in enumerate(used):
        ws = _WORD.findall(para)
        para_words.append(len(ws))
        words_total += len(ws)
        chars += sum(len(w) for w in ws)
        stop = set(_STOP.get(lang, _STOP["pt"] + _STOP["en"]))
        for w in ws:
            syl_total += syllables(w)
            lw = w.lower().strip("'’-")
            if len(lw) >= 4 and lw not in stop:
                counts[lw] += 1
        for m in _SENT.finditer(para):
            s = m.group(0).strip()
            n = len(_WORD.findall(s))
            if n == 0:
                continue
            sentences += 1
            if n > LONG_SENTENCE:
                longest.append({"p": pi, "words": n, "text": s[:160] + ("…" if len(s) > 160 else "")})
    longest.sort(key=lambda x: -x["words"])
    out: Dict[str, Any] = {"language": lang, "paragraphs": len([x for x in used if x.strip()]), "words": words_total, "sentences": sentences, "characters": chars,
                           "reading_minutes": round(words_total / WPM, 1), "avg_sentence_words": round(words_total / sentences, 1) if sentences else 0.0,
                           "avg_word_letters": round(chars / words_total, 2) if words_total else 0.0, "long_sentences": longest[:10], "long_sentence_count": len(longest),
                           "top_words": [{"word": w, "count": c} for w, c in counts.most_common(TOP_WORDS) if c > 1], "truncated": truncated}
    if words_total >= 30 and sentences:
        base = _FLESCH.get(lang, _FLESCH["en"])
        score = base - 1.015 * (words_total / sentences) - 84.6 * (syl_total / words_total)
        score = max(0.0, min(100.0, score))
        out["readability"] = round(score, 1)
        out["level"] = _label(score)
    else:
        out["readability"], out["level"] = None, ""   # texto curto demais para estimar
    out["checks"] = {"words_ok": sum(para_words) == words_total}
    return out
