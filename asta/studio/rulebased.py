"""Agentes determinísticos do Studio: o que roda no modo Demo (sem IA) e o que substitui um agente cuja resposta veio inválida."""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List

from ..util import num, text
from . import schema as S

BEATS = {
    "pt": ["Abertura", "Apresentação", "O problema", "A virada", "Clímax", "Desfecho"],
    "en": ["Opening", "Introduction", "The problem", "The turn", "Climax", "Resolution"],
}
CAMERAS = ["wide establishing shot", "medium shot", "close-up", "slow tracking shot", "over-the-shoulder shot", "low angle shot", "aerial view", "detail shot"]
WORDS_PER_SECOND = 2.4  # narração falada em ritmo natural


def lang_key(language: str) -> str:
    return "en" if str(language or "").lower().startswith("en") else "pt"


def sentences(src: str) -> List[str]:
    parts = [s.strip() for s in re.split(r"(?<=[.!?…])\s+|\n+", src or "") if s.strip()]
    return parts


def word_budget(secs: float) -> int:
    return max(4, int(secs * WORDS_PER_SECOND))


def trim_words(narration: str, budget: int) -> str:
    """Corta a narração no limite de palavras, preferindo terminar numa frase completa."""
    words = narration.split()
    if len(words) <= budget:
        return narration.strip()
    cut = " ".join(words[:budget])
    last = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"), cut.rfind("…"))
    return (cut[:last + 1] if last > len(cut) * 0.5 else cut.rstrip(",;: ") + "…").strip()


def scale_secs(secs: List[float], total: float, lo: float = 0.5) -> List[float]:
    """Reescala durações para somarem `total`, respeitando um mínimo."""
    s = sum(secs) or 1.0
    out = [max(lo, x * total / s) for x in secs]
    s2 = sum(out)
    return [round(x * total / s2, 2) for x in out] if s2 else out


# ---------------------------------------------------------------------------------------------------- Showrunner / planejador
def planner(payload: Dict[str, Any]) -> Dict[str, Any]:
    n = int(num(payload.get("scene_count"), 4, 1, S.MAX_SCENES))
    lang = lang_key(payload.get("language", "pt-BR"))
    beats = BEATS[lang]
    prompt = text(payload.get("act_summary") or payload.get("prompt"), "", 3000) or text(payload.get("title"), "", 100) or ("Uma história" if lang == "pt" else "A story")
    sents = sentences(prompt) or [prompt]
    total = float(payload.get("target_seconds") or n * 10)
    scenes = []
    base = int(num(payload.get("first_index"), 0, 0, 10000))
    for i in range(n):
        beat = beats[min(len(beats) - 1, int(i * len(beats) / max(1, n)))] if not payload.get("act_summary") else (payload.get("act_title") or beats[0])
        sent = sents[i % len(sents)]
        scenes.append({"title": f"{beat}" + (f" {base + i + 1}" if n > len(beats) or payload.get("act_summary") else ""), "summary": sent[:300], "narration": sent[:400],
                       "visual": f"{sent[:200]}, {beat.lower()}", "sound": "", "secs": total / n})
    title = text(payload.get("title"), "", 100) or sents[0][:60]
    return {"title": title, "logline": sents[0][:200], "scenes": scenes, "bible": {"tone": "", "world": "", "characters": []}}


def outliner(payload: Dict[str, Any]) -> Dict[str, Any]:
    n = int(num(payload.get("scene_count"), 24, 1, S.MAX_SCENES))
    per = int(num(payload.get("per_act"), 10, 2, 16))
    k = max(1, math.ceil(n / per))
    lang = lang_key(payload.get("language", "pt-BR"))
    beats = BEATS[lang]
    prompt = text(payload.get("prompt"), "", 3000) or text(payload.get("title"), "", 100)
    sents = sentences(prompt) or [prompt or "—"]
    acts, left = [], n
    for i in range(k):
        cnt = min(per, left) if i < k - 1 else left
        left -= cnt
        acts.append({"title": (f"Ato {i + 1} — " if lang == "pt" else f"Act {i + 1} — ") + beats[min(len(beats) - 1, int(i * len(beats) / k))], "summary": sents[i % len(sents)][:300], "scenes": cnt})
    return {"title": text(payload.get("title"), "", 100) or sents[0][:60], "logline": sents[0][:200], "acts": acts}


# ---------------------------------------------------------------------------------------------------- analista de cena
def analyst(payload: Dict[str, Any]) -> Dict[str, Any]:
    sc = payload.get("scene") or {}
    secs = float(num(payload.get("secs"), sc.get("secs", 8), 1, 7200))
    shot_len = float(num(payload.get("shot_len"), 6, 2, 60))
    n = max(1, min(S.MAX_SHOTS, int(math.ceil(secs / shot_len))))
    visual = text(sc.get("visual") or sc.get("summary") or sc.get("title"), "", 500)
    shots = [{"visual": f"{visual}, {CAMERAS[i % len(CAMERAS)]}", "camera": CAMERAS[i % len(CAMERAS)], "secs": secs / n} for i in range(n)]
    return {"shots": shots, "narration": trim_words(text(sc.get("narration"), "", 3000), word_budget(secs)), "music": text(sc.get("music") or payload.get("tone"), "", 200) or "cinematic ambient",
            "sfx": text(sc.get("sound"), "", 200), "continuity": text(sc.get("summary"), "", 300)}


def scene_checks(scene: Dict[str, Any], secs: float, files_ok: bool = True, voice_dur: float = 0.0) -> List[str]:
    """Verificações objetivas de uma cena gerada (as mesmas valem com ou sem IA)."""
    issues = []
    words = len(scene.get("narration", "").split())
    if words > word_budget(secs) * 1.25:
        issues.append(f"narração longa demais para {secs:.0f}s ({words} palavras; cabem ~{word_budget(secs)})")
    if not scene.get("shots"):
        issues.append("a cena não tem planos")
    elif any(not s.get("visual") for s in scene["shots"]):
        issues.append("há plano sem descrição visual")
    if not files_ok:
        issues.append("faltam arquivos de mídia gerados")
    if voice_dur and voice_dur > secs * 1.3:
        issues.append(f"a voz ({voice_dur:.0f}s) passa muito da duração da cena ({secs:.0f}s)")
    return issues


def reviewer(payload: Dict[str, Any]) -> Dict[str, Any]:
    issues = [str(x) for x in (payload.get("checks") or [])]
    sc = payload.get("scene") or {}
    fix: Dict[str, Any] = {}
    if any("narração longa" in i for i in issues):
        fix["narration"] = trim_words(text(sc.get("narration"), "", 3000), word_budget(float(num(payload.get("secs"), 8, 1, 7200))))
    return {"approved": not issues, "score": 9 if not issues else 6, "issues": issues, "fix": fix}


def recap(payload: Dict[str, Any]) -> Dict[str, Any]:
    scs = [text(s.get("summary") or s.get("title"), "", 160) for s in (payload.get("scenes") or []) if isinstance(s, dict)]
    return {"recap": " ".join(x for x in scs[:3] if x)[:600], "bible_update": {"characters": [], "facts": []}}
