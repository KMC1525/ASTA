"""Documento de um projeto do Studio (`asta.studio.v1`): projeto único ou série, episódios, cenas, ativos e a timeline de edição.

O servidor é dono de cenas e ativos (o navegador só salva metadados e a timeline), assim o salvamento do editor nunca apaga o que um job acabou de gerar.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..util import new_id, now_iso, num, slugify, text

SCHEMA = "asta.studio.v1"
MAX_SECONDS = 6 * 3600  # teto absoluto de um episódio (6 h)
MIN_SECONDS = 5
MAX_SCENES = 120
MAX_SHOTS = 16
MAX_CLIPS = 6000
MAX_EPISODES = 200

# Tipos de duração: o tipo escolhe valores iniciais e o teto «oficial»; o usuário pode ajustar a duração à vontade (acima do teto o tipo vira «custom»).
DURATION_TYPES: Dict[str, Dict[str, Any]] = {
    "shorts": {"label": "Shorts/Reels", "hint": "Até 2 minutos", "max": 120, "default": 60, "aspect": "9:16", "scene_len": 8, "shot_len": 4},
    "short": {"label": "Curta", "hint": "Até 30 minutos", "max": 1800, "default": 600, "aspect": "16:9", "scene_len": 40, "shot_len": 8},
    "long": {"label": "Longa", "hint": "Até 90 minutos", "max": 5400, "default": 3600, "aspect": "16:9", "scene_len": 90, "shot_len": 12},
    "custom": {"label": "Personalizada", "hint": "Qualquer duração", "max": MAX_SECONDS, "default": 300, "aspect": "16:9", "scene_len": 60, "shot_len": 10},
}
STYLES: Dict[str, Dict[str, str]] = {
    "realistic": {"label": "Realista", "look": "photorealistic, cinematic lighting, natural colors, shallow depth of field, 35mm film look, high detail",
                  "negative": "cartoon, anime, illustration, drawing, deformed, blurry, text, watermark"},
    "cartoon": {"label": "Cartoon", "look": "2D cartoon style, bold clean outlines, flat vibrant colors, expressive characters, playful shapes",
                "negative": "photorealistic, photo, blurry, text, watermark"},
    "anime": {"label": "Anime", "look": "anime style, cel shading, detailed backgrounds, dynamic framing, soft gradients, expressive eyes",
              "negative": "photorealistic, western cartoon, blurry, text, watermark"},
    "custom": {"label": "Custom", "look": "", "negative": ""},
}
ASPECTS = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1024, 1024), "4:3": (960, 720)}
KINDS = ("single", "series")
MOTIONS = ("auto", "video")  # auto: Ken Burns sobre a imagem (leve); video: usa o modelo de vídeo em cada plano
EXPORT_MODES = ("full", "video", "audio")
STAGES = ("receive", "analyze", "generate", "review", "deliver")  # recebe → analisa → gera → revisa → entrega
STAGE_LABEL = {"receive": "Recebe", "analyze": "Analisa", "generate": "Gera", "review": "Revisa", "deliver": "Entrega"}
FILTERS = ("none", "bw", "warm", "cool", "vivid", "vhs", "cinematic", "phonk")
TRANSITIONS = ("cut", "fade")


def describe() -> Dict[str, Any]:
    return {"schema": SCHEMA, "durations": [{"id": k, **v} for k, v in DURATION_TYPES.items()], "styles": [{"id": k, "label": v["label"]} for k, v in STYLES.items()],
            "aspects": list(ASPECTS), "kinds": list(KINDS), "motions": list(MOTIONS), "export_modes": list(EXPORT_MODES), "stages": list(STAGES), "filters": list(FILTERS),
            "limits": {"min_seconds": MIN_SECONDS, "max_seconds": MAX_SECONDS, "max_scenes": MAX_SCENES}}


def duration_type_for(seconds: float, preferred: str = "") -> str:
    """O tipo que cabe na duração: o escolhido se couber; senão o menor que couber; acima de 90 min vira «custom»."""
    spec = DURATION_TYPES.get(preferred)
    if spec and seconds <= spec["max"] and preferred != "custom":
        return preferred
    for k in ("shorts", "short", "long"):
        if seconds <= DURATION_TYPES[k]["max"]:
            return k if not preferred or preferred == "custom" else k
    return "custom"


def style_look(project: Dict[str, Any]) -> Dict[str, str]:
    st = STYLES.get(project.get("style"), STYLES["realistic"])
    if project.get("style") == "custom":
        return {"look": text(project.get("style_custom"), "", 400) or "cinematic, detailed", "negative": ""}
    return {"look": st["look"], "negative": st["negative"]}


def _color(v: Any, d: str) -> str:
    s = str(v or "").strip()
    return s if s.startswith("#") and len(s) in (4, 7) else d


# --------------------------------------------------------------------------- timeline
def normalize_timeline(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    tracks, ids = [], set()
    for t in (raw.get("tracks") if isinstance(raw.get("tracks"), list) else [])[:16]:
        t = t if isinstance(t, dict) else {}
        tid = slugify(t.get("id") or "", "", 16).replace("-", "_") or f"t{len(tracks) + 1}"
        kind = t.get("kind") if t.get("kind") in ("video", "audio", "text") else "video"
        if tid in ids:
            continue
        ids.add(tid)
        tracks.append({"id": tid, "kind": kind, "name": text(t.get("name"), tid.upper(), 12), "muted": bool(t.get("muted")), "hidden": bool(t.get("hidden")), "locked": bool(t.get("locked"))})
    if not tracks:
        tracks = default_tracks()
    kinds = {t["id"]: t["kind"] for t in tracks}
    clips: List[Dict[str, Any]] = []
    seen = set()
    for c in (raw.get("clips") if isinstance(raw.get("clips"), list) else [])[:MAX_CLIPS]:
        c = c if isinstance(c, dict) else {}
        tr = c.get("track") if c.get("track") in kinds else None
        if not tr:
            continue
        cid = slugify(c.get("id") or "", "", 24).replace("-", "_") or new_id("c_")
        if cid in seen:
            cid = new_id("c_")
        seen.add(cid)
        is_text = kinds[tr] == "text"
        clips.append({
            "id": cid, "track": tr, "asset": "" if is_text else text(c.get("asset"), "", 60), "scene": text(c.get("scene"), "", 24), "label": text(c.get("label"), "", 60),
            "start": round(num(c.get("start"), 0, 0, 86400), 3), "dur": round(num(c.get("dur"), 3, 0.1, 86400), 3), "in": round(num(c.get("in"), 0, 0, 86400), 3),
            "speed": round(num(c.get("speed"), 1, 0.25, 4), 2), "mute": bool(c.get("mute")), "volume": round(num(c.get("volume"), 1, 0, 2), 2),
            "fade_in": round(num(c.get("fade_in"), 0, 0, 30), 2), "fade_out": round(num(c.get("fade_out"), 0, 0, 30), 2), "opacity": round(num(c.get("opacity"), 1, 0, 1), 2),
            "fit": c.get("fit") if c.get("fit") in ("contain", "cover", "stretch") else "cover", "x": round(num(c.get("x"), 0, -1, 1), 3), "y": round(num(c.get("y"), 0, -1, 1), 3),
            "scale": round(num(c.get("scale"), 1, 0.1, 4), 2), "filter": c.get("filter") if c.get("filter") in FILTERS else "none",
            "text": text(c.get("text"), "", 300) if is_text else "", "size": int(num(c.get("size"), 44, 8, 300)), "color": _color(c.get("color"), "#ffffff"),
            "bg": _color(c.get("bg"), "") if c.get("bg") else "", "pos": c.get("pos") if c.get("pos") in ("top", "center", "bottom") else "bottom",
        })
    clips = [c for c in clips if kinds[c["track"]] == "text" or c["asset"]]
    markers = []
    for m in (raw.get("markers") if isinstance(raw.get("markers"), list) else [])[:200]:
        if isinstance(m, dict):
            markers.append({"t": round(num(m.get("t"), 0, 0, 86400), 3), "label": text(m.get("label"), "", 40)})
    duration = round(max([c["start"] + c["dur"] for c in clips] + [0.0]), 3)
    return {"tracks": tracks, "clips": clips, "markers": markers, "duration": duration}


def default_tracks() -> List[Dict[str, Any]]:
    mk = lambda i, k, n: {"id": i, "kind": k, "name": n, "muted": False, "hidden": False, "locked": False}  # noqa: E731
    return [mk("t_t1", "text", "T1"), mk("t_v2", "video", "V2"), mk("t_v1", "video", "V1"), mk("t_a1", "audio", "A1"), mk("t_a2", "audio", "A2"), mk("t_a3", "audio", "A3")]


# --------------------------------------------------------------------------- cenas / episódios
def normalize_scene(raw: Any, idx: int = 0) -> Dict[str, Any]:
    r = raw if isinstance(raw, dict) else {}
    shots = []
    for s in (r.get("shots") if isinstance(r.get("shots"), list) else [])[:MAX_SHOTS]:
        s = s if isinstance(s, dict) else {}
        shots.append({"visual": text(s.get("visual"), "", 600), "camera": text(s.get("camera"), "", 80), "secs": round(num(s.get("secs"), 4, 0.5, 600), 2),
                      "asset": text(s.get("asset"), "", 60), "image": text(s.get("image"), "", 60)})
    stages = {k: (r.get("stages") or {}).get(k) if (r.get("stages") or {}).get(k) in ("pending", "running", "done", "warn", "error", "skipped") else "pending" for k in STAGES}
    return {
        "id": slugify(r.get("id") or "", "", 24).replace("-", "_") or new_id("s_"), "n": int(num(r.get("n"), idx + 1, 1, 9999)),
        "title": text(r.get("title"), f"Cena {idx + 1}", 100), "summary": text(r.get("summary"), "", 800), "narration": text(r.get("narration"), "", 3000),
        "visual": text(r.get("visual"), "", 800), "sound": text(r.get("sound"), "", 300), "music": text(r.get("music"), "", 300), "secs": round(num(r.get("secs"), 10, 1, 7200), 2),
        "actual": round(num(r.get("actual"), 0, 0, 7200), 2), "start": round(num(r.get("start"), 0, 0, 86400), 2), "shots": shots, "continuity": text(r.get("continuity"), "", 400),
        "stages": stages, "status": r.get("status") if r.get("status") in ("pending", "running", "delivered", "error") else "pending", "score": num(r.get("score"), 0, 0, 10) if r.get("score") is not None else None,
        "notes": [text(x, "", 300) for x in (r.get("notes") if isinstance(r.get("notes"), list) else [])[:8]], "assets": [text(x, "", 60) for x in (r.get("assets") if isinstance(r.get("assets"), list) else [])[:60]],
        "revisions": int(num(r.get("revisions"), 0, 0, 5)),
    }


def normalize_episode(raw: Any, idx: int = 0) -> Dict[str, Any]:
    r = raw if isinstance(raw, dict) else {}
    scenes = [normalize_scene(s, i) for i, s in enumerate((r.get("scenes") if isinstance(r.get("scenes"), list) else [])[:MAX_SCENES])]
    ids = set()
    for s in scenes:
        if s["id"] in ids:
            s["id"] = new_id("s_")
        ids.add(s["id"])
    status = r.get("status") if r.get("status") in ("draft", "planned", "generating", "ready", "error") else ("planned" if scenes else "draft")
    return {"id": slugify(r.get("id") or "", "", 24).replace("-", "_") or new_id("e_"), "n": int(num(r.get("n"), idx + 1, 1, 9999)), "title": text(r.get("title"), f"Episódio {idx + 1}", 120),
            "prompt": text(r.get("prompt"), "", 8000), "logline": text(r.get("logline"), "", 600), "recap": text(r.get("recap"), "", 800), "status": status, "scenes": scenes,
            "timeline": normalize_timeline(r.get("timeline")), "target": round(num(r.get("target"), 0, 0, MAX_SECONDS), 1), "exports": [e for e in (r.get("exports") if isinstance(r.get("exports"), list) else [])[:30] if isinstance(e, dict)],
            "origin": r.get("origin") if r.get("origin") in ("generated", "autoedit", "manual") else "generated", "edit": r.get("edit") if isinstance(r.get("edit"), dict) else {}}


def normalize_asset(a: Any) -> Optional[Dict[str, Any]]:
    a = a if isinstance(a, dict) else {}
    if not a.get("id") or not a.get("file") or a.get("kind") not in ("image", "video", "audio"):
        return None
    return {"id": text(a["id"], "", 60), "file": text(a["file"], "", 80), "kind": a["kind"], "name": text(a.get("name"), "", 120), "mime": text(a.get("mime"), "", 60), "dur": round(num(a.get("dur"), 0, 0, 86400), 3),
            "w": int(num(a.get("w"), 0, 0, 20000)), "h": int(num(a.get("h"), 0, 0, 20000)), "audio": bool(a.get("audio")), "source": text(a.get("source"), "upload", 20), "scene": text(a.get("scene"), "", 24),
            "prompt": text(a.get("prompt"), "", 600), "created": text(a.get("created"), "", 40)}


def normalize_project(raw: Any, keep_id: Optional[str] = None) -> Dict[str, Any]:
    r = raw if isinstance(raw, dict) else {}
    target = round(num(r.get("target_seconds"), DURATION_TYPES["shorts"]["default"], MIN_SECONDS, MAX_SECONDS), 1)
    dtype = r.get("duration_type") if r.get("duration_type") in DURATION_TYPES else "shorts"
    dtype = duration_type_for(target, dtype)
    aspect = r.get("aspect") if r.get("aspect") in ASPECTS else DURATION_TYPES[dtype]["aspect"]
    kind = r.get("kind") if r.get("kind") in KINDS else "single"
    episodes = [normalize_episode(e, i) for i, e in enumerate((r.get("episodes") if isinstance(r.get("episodes"), list) else [])[:MAX_EPISODES])]
    if kind == "single":
        episodes = episodes[:1]
    for i, e in enumerate(episodes):
        e["n"] = i + 1
    bible = r.get("bible") if isinstance(r.get("bible"), dict) else {}
    assets = [x for x in (normalize_asset(a) for a in (r.get("assets") if isinstance(r.get("assets"), list) else [])[:4000]) if x]
    return {
        "schema": SCHEMA, "id": keep_id or text(r.get("id"), "", 40) or new_id("st_"), "name": text(r.get("name"), "Novo projeto", 100), "kind": kind, "duration_type": dtype, "target_seconds": target,
        "style": r.get("style") if r.get("style") in STYLES else "realistic", "style_custom": text(r.get("style_custom"), "", 400), "aspect": aspect, "language": text(r.get("language"), "pt-BR", 12),
        "motion": r.get("motion") if r.get("motion") in MOTIONS else "auto", "voice": text(r.get("voice"), "", 60), "music": r.get("music") is not False, "captions": r.get("captions") is not False,
        "revisions": int(num(r.get("revisions"), 1, 0, 2)), "origin": r.get("origin") if r.get("origin") in ("generated", "manual") else "generated", "premise": text(r.get("premise"), "", 4000), "created": text(r.get("created"), "", 40) or now_iso(), "updated": text(r.get("updated"), "", 40) or now_iso(),
        "bible": {"world": text(bible.get("world"), "", 800), "tone": text(bible.get("tone"), "", 200), "characters": [{"name": text(c.get("name"), "", 40), "look": text(c.get("look"), "", 300)}
                                                                                                        for c in (bible.get("characters") if isinstance(bible.get("characters"), list) else [])[:20] if isinstance(c, dict) and c.get("name")],
                  "facts": [text(x, "", 200) for x in (bible.get("facts") if isinstance(bible.get("facts"), list) else [])[:40]]},
        "episodes": episodes, "assets": assets,
    }
