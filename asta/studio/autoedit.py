"""Edição automática: vários anexos (vídeos, imagens, áudios) + um prompt + um estilo de edição → uma timeline pronta no Studio, que depois você refina à mão.

Pipeline multi-agente em etapas:
    anexos     importa os arquivos para o projeto e mede cada um (duração, trocas de cena, picos de volume, silêncios)
    analista   decide o papel de cada arquivo (filmagem, b-roll, música, narração) e o foco do vídeo
    diretor    dá as diretrizes (ritmo, ordem, pontos de destaque, trechos a evitar, títulos); o algoritmo do estilo as transforma em cortes
    revisor    confere duração, limites de cada corte e áudio; corrige o que estiver fora
    montagem   escreve a timeline (V1 cortes, A1 narração, A2 música, T1 títulos) como um novo episódio
Cada agente de IA tem um equivalente determinístico (modo Demo, ou resposta inválida): a timeline sempre sai.
"""
from __future__ import annotations

import math
import random
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..agents import prompts
from ..agents.runner import Cancelled, Runner
from ..canvas.media import MIME_EXT, sniff_mime
from ..providers import ProviderError, build_provider
from ..storage import Store
from ..util import num, text
from . import rulebased as rb
from . import schema as S
from . import tools

# Perfis dos estilos de edição. pace = (mín, máx) de segundos por corte; None = grade de batidas (bpm).
EDIT_STYLES: Dict[str, Dict[str, Any]] = {
    "gameplay": {"label": "Gameplay", "hint": "Melhores momentos (picos de volume), cortes rápidos e zoom nos destaques", "pace": (2.5, 6.0), "use": "loud", "fade": 0.0, "punch": 1.12, "punch_every": 3,
                 "grade": "vivid", "orig_vol": 1.0, "music_vol": 0.15, "voice_vol": 1.0, "default_target": 60, "silence": False, "titles": False,
                 "hook": True, "chrono": True, "dedupe": True, "sfx_zoom": True,
                 "craft": "Abra com o melhor momento (gancho no 1º segundo); depois conte em ordem cronológica, cortando tempo morto; zoom só nos picos; música baixa para o áudio do jogo mandar."},
    "documentary": {"label": "Documentário", "hint": "Cortes longos e calmos, transições suaves, narração em destaque e música discreta", "pace": (5.0, 12.0), "use": "sequential", "fade": 0.5, "punch": 1.0, "punch_every": 0,
                    "grade": "cinematic", "orig_vol": 0.8, "music_vol": 0.14, "voice_vol": 1.0, "default_target": 180, "silence": True, "titles": True,
                    "cutaway": 2, "dedupe": True, "pan": True, "pad": 0.25,
                    "craft": "Planos longos e calmos; entre cada 2 planos principais entra um plano de cobertura (b-roll); movimento lento de câmera nas imagens; música discreta que abaixa quando há narração."},
    "phonk": {"label": "Edit Phonk", "hint": "Cortes na batida, câmera lenta/rápida, zoom, filtro granulado e música no talo", "pace": None, "use": "grid", "fade": 0.0, "punch": 1.18, "punch_every": 2, "grade": "phonk",
              "orig_vol": 0.0, "music_vol": 1.0, "voice_vol": 1.0, "default_target": 30, "silence": False, "titles": False, "bpm": 140, "ramps": True,
              "hook": True, "dedupe": True, "buildup": True, "pan": True,
              "craft": "Corte só nas batidas fortes (não em toda subdivisão); introdução mais lenta, 'drop' com cortes de 1–2 batidas e zoom a cada corte; rampas de velocidade com moderação; fecha com câmera lenta."},
    "trailer": {"label": "Trailer", "hint": "Ritmo que acelera, fades, cartelas de texto e música alta", "pace": (4.0, 1.2), "use": "spread", "fade": 0.3, "punch": 1.0, "punch_every": 0, "grade": "cinematic",
                "orig_vol": 0.35, "music_vol": 0.85, "voice_vol": 1.0, "default_target": 60, "silence": False, "titles": True,
                "dedupe": True, "endcard": True,
                "craft": "Começa devagar e acelera até cortes bem curtos no clímax; cartelas de texto curtas; termina com uma cartela final com o título."},
    "vlog": {"label": "Vlog", "hint": "Corta o tempo morto, ritmo médio, cores quentes e música leve", "pace": (3.0, 8.0), "use": "sequential", "fade": 0.15, "punch": 1.0, "punch_every": 0, "grade": "warm",
             "orig_vol": 1.0, "music_vol": 0.1, "voice_vol": 1.0, "default_target": 120, "silence": True, "titles": False,
             "cutaway": 3, "dedupe": True, "pad": 0.12, "pan": True,
             "craft": "Jump cuts: corta pausas e hesitações deixando uma folga mínima na fala; um plano de cobertura a cada 3 cortes; cores quentes e música bem baixa."},
    "tutorial": {"label": "Tutorial", "hint": "Remove pausas, cortes longos e claros, sem efeitos", "pace": (8.0, 20.0), "use": "sequential", "fade": 0.0, "punch": 1.0, "punch_every": 0, "grade": "none",
                 "orig_vol": 1.0, "music_vol": 0.06, "voice_vol": 1.0, "default_target": 300, "silence": True, "titles": True,
                 "dedupe": True, "pad": 0.2, "cutaway": 4,
                 "craft": "Clareza antes de estilo: tira pausas longas sem cortar a frase, cortes longos, sem efeitos, cartelas de passo, música quase inaudível."},
    "music_video": {"label": "Clipe musical", "hint": "Cortes no compasso da música, cores vivas", "pace": None, "use": "grid", "fade": 0.0, "punch": 1.08, "punch_every": 4, "grade": "vivid",
                    "orig_vol": 0.0, "music_vol": 1.0, "voice_vol": 1.0, "default_target": 90, "silence": False, "titles": False, "bpm": 120,
                    "dedupe": True, "pan": True, "buildup": True,
                    "craft": "Cortes no compasso (1, 2 ou 4 batidas), mais lentos na estrofe e mais rápidos no refrão; zoom a cada 4 cortes; nada de repetir o mesmo trecho."},
    "slideshow": {"label": "Apresentação de fotos", "hint": "Imagens com fades e música", "pace": (3.5, 5.0), "use": "sequential", "fade": 0.6, "punch": 1.0, "punch_every": 0, "grade": "none",
                  "orig_vol": 1.0, "music_vol": 0.6, "voice_vol": 1.0, "default_target": 60, "silence": False, "titles": False,
                  "pan": True, "vary": 0.18, "chrono": True,
                  "craft": "Cada foto fica o suficiente para ser vista, com tempos levemente diferentes, movimento lento (zoom e pan alternados) e fades suaves."},
}
ROLES = ("footage", "broll", "music", "voiceover", "ignore")
VOICE_NAME = re.compile(r"(narr|voz|voice|\bvo\b|locu|fala|speech|podcast)", re.I)

ANALYST = """ROLE: Edit analyst.
INPUT_JSON lists the attached files of a video edit (id, name, kind, duration, has_audio, loud_peaks, scene_changes) plus the user's prompt and the edit style.
Assign each file a role: "footage" (main video to cut), "broll" (supporting images/clips), "music" (background track), "voiceover" (narration) or "ignore" (unusable/duplicate).
Also give a short video "title" and "focus": up to 4 keywords of what the edit should highlight.
Keep it SHORT (no explanations, no reasoning). Output JSON: {"title": str, "focus": [str], "roles": {"<id>": "footage|broll|music|voiceover|ignore"}}"""

DIRECTOR = """ROLE: Edit director.
Given the file roles, the edit style profile, target_seconds and the user's prompt (INPUT_JSON), give DIRECTIVES for the cutting algorithm (do not list every cut):
"pace": "fast"|"medium"|"slow" (relative to the style default); "order": file ids in the order they should appear (footage/broll); "highlights": up to 8 {"asset": id, "t": seconds} moments that must be included;
"avoid": up to 6 {"asset": id, "from": s, "to": s} stretches to skip; "titles": up to 4 short title cards (empty if the style does not use them).
Follow the style's "craft" note (the technique references editors of that genre use). "highlights"[0] is the HOOK: the single best moment, used to open the video.
Keep it SHORT (no explanations, no reasoning). Output JSON: {"pace": str, "order": [str], "highlights": [{"asset": str, "t": number}], "avoid": [{"asset": str, "from": number, "to": number}], "titles": [str]}"""

CRITIC = """ROLE: Edit reviewer.
INPUT_JSON summarizes a finished automatic edit: style, target_seconds, total seconds, cut count, average cut length, whether music/voice exist, and objective checks.
Say whether it matches the requested style and prompt, with up to 3 short improvement tips for the human editor.
Output JSON: {"approved": bool, "tips": [str]}"""


def describe_styles() -> List[Dict[str, Any]]:
    return [{"id": k, "label": v["label"], "hint": v["hint"], "bpm": v.get("bpm", 0), "default_target": v["default_target"], "craft": v.get("craft", "")} for k, v in EDIT_STYLES.items()]


# ---------------------------------------------------------------------------------------------------- algoritmo dos cortes
def guess_roles(inv: List[Dict[str, Any]]) -> Dict[str, str]:
    roles: Dict[str, str] = {}
    for a in inv:
        if a["kind"] == "audio":
            roles[a["id"]] = "voiceover" if VOICE_NAME.search(a["name"]) else "music"
        elif a["kind"] == "image":
            roles[a["id"]] = "broll"
        else:
            roles[a["id"]] = "footage"
    if not any(r == "footage" for r in roles.values()):  # só imagens/áudio: as imagens viram a «filmagem» (apresentação)
        for a in inv:
            if a["kind"] == "image":
                roles[a["id"]] = "footage"
    return roles


def _windows(a: Dict[str, Any], style: Dict[str, Any], lo: float, hi: float, directives: Dict[str, Any], rnd: random.Random) -> List[Tuple[float, float]]:
    """Janelas candidatas [início, fim) de um vídeo, na ordem de preferência do estilo."""
    dur = a["dur"]
    avoid = [(float(x.get("from", 0)), float(x.get("to", 0))) for x in directives.get("avoid", []) if x.get("asset") == a["id"]]
    ok = lambda s, e: not any(s < ae and e > as_ for as_, ae in avoid)  # noqa: E731
    out: List[Tuple[float, float]] = []
    pace = (lo + hi) / 2
    for h in directives.get("highlights", []):
        if h.get("asset") == a["id"]:
            t = float(num(h.get("t"), 0, 0, dur))
            out.append((max(0.0, t - pace * 0.4), min(dur, t + pace * 0.6)))
    use = style["use"]
    if use == "loud":
        peaks, taken = sorted(a.get("loud", []), key=lambda x: -x[1]), []
        for t, _db in peaks:
            if all(abs(t - u) > pace for u in taken):
                taken.append(t)
                out.append((max(0.0, t - pace * 0.4), min(dur, t + pace * 0.6)))
        cuts = a.get("changes", [])
        out += [(max(0.0, c - 0.2), min(dur, c - 0.2 + pace)) for c in cuts]
    elif use in ("sequential",):
        bounds = [0.0] + [c for c in a.get("changes", []) if 0 < c < dur] + [dur]
        keep: List[Tuple[float, float]] = []
        if style.get("silence") and a.get("silences"):
            t = 0.0
            pad = float(style.get("pad", 0.0))
            for s, e in sorted(a["silences"]):
                if s - t > 0.8:
                    keep.append((max(0.0, t - pad if t else 0.0), min(dur, s + pad)))  # folga nas pontas: a fala não é cortada seca
                t = max(t, e)
            if dur - t > 0.8:
                keep.append((max(0.0, t - pad), dur))
        else:
            keep = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] - bounds[i] > 0.5] or [(0.0, dur)]
        for s, e in keep:
            t = s
            while t < e - 0.3:
                out.append((t, min(e, t + hi)))
                t += hi
    else:  # grid / spread: janelas espalhadas pelo vídeo (começando pelos picos de volume)
        step = max(pace, dur / 24)
        out += [(t, min(dur, t + step)) for t in [x for x, _ in sorted(a.get("loud", []), key=lambda p: -p[1])[:30]]]
        t = 0.0
        while t < dur - 0.3:
            out.append((t, min(dur, t + step)))
            t += step
        if use == "grid":
            rnd.shuffle(out[len(out) - int(dur / step) - 1:])
    out = [(s, e) for s, e in out if e - s >= 0.3 and ok(s, e)]
    return out or [(0.0, dur)]


def plan_edl(style_id: str, inv: List[Dict[str, Any]], roles: Dict[str, str], target: float, directives: Dict[str, Any], bpm: float = 0, seed: int = 0, title: str = "") -> Dict[str, Any]:
    """Cortes (EDL) do estilo: [{asset, in, dur, speed, filter, scale, fade_in, fade_out, mute, volume}] + música/narração/títulos. Determinístico."""
    st = EDIT_STYLES[style_id]
    rnd = random.Random(seed)
    by = {a["id"]: a for a in inv}
    footage = [by[i] for i in directives.get("order", []) if i in by and roles.get(i) in ("footage", "broll")] or []
    footage += [a for a in inv if roles.get(a["id"]) in ("footage",) and a not in footage]
    footage += [a for a in inv if roles.get(a["id"]) == "broll" and a not in footage]
    music = [a for a in inv if roles.get(a["id"]) == "music"]
    voice = [a for a in inv if roles.get(a["id"]) == "voiceover"]
    if not footage:
        raise ValueError("Não encontrei vídeo ou imagem para editar — anexe pelo menos uma filmagem ou foto.")
    pace = st["pace"]
    fast = {"fast": 0.7, "slow": 1.4}.get(directives.get("pace"), 1.0)
    beat = 60.0 / float(bpm or st.get("bpm") or 120)
    segs: List[Dict[str, Any]] = []
    t = 0.0
    k = 0
    cand: List[Tuple[Dict[str, Any], float, float]] = []
    for a in footage:
        if a["kind"] == "image":
            cand.append((a, 0.0, 0.0))
            continue
        lo, hi = (beat * 2, beat * 4) if pace is None else (min(pace) * fast, max(pace) * fast)
        for s, e in _windows(a, st, lo, hi, directives, rnd):
            cand.append((a, s, e))
    if st["use"] in ("spread", "loud") and len(footage) > 1:  # intercala os arquivos para não ficar só num
        buckets: Dict[str, List[Tuple[Dict[str, Any], float, float]]] = {}
        for c in cand:
            buckets.setdefault(c[0]["id"], []).append(c)
        mixed = []
        while any(buckets.values()):
            for key in list(buckets):
                if buckets[key]:
                    mixed.append(buckets[key].pop(0))
        cand = mixed
    if st.get("cutaway") and any(roles.get(c[0]["id"]) == "broll" for c in cand) and any(roles.get(c[0]["id"]) == "footage" for c in cand):
        main = [c for c in cand if roles.get(c[0]["id"]) != "broll"]  # um plano de cobertura (b-roll) a cada N planos principais
        cover = [c for c in cand if roles.get(c[0]["id"]) == "broll"]
        cand = []
        for i, c in enumerate(main):
            cand.append(c)
            if cover and i % int(st["cutaway"]) == int(st["cutaway"]) - 1:
                cand.append(cover[(i // int(st["cutaway"])) % len(cover)])
    hl = next((h for h in directives.get("highlights", []) if h.get("asset") in by), None)
    if st.get("hook") and hl:  # gancho: o diretor escolheu o melhor momento para abrir
        hook = next((c for c in cand if c[0]["id"] == hl["asset"] and c[1] - 0.01 <= float(hl.get("t", 0)) <= c[2] + 0.01), None)
        if hook:
            cand.remove(hook)
            cand.insert(0, hook)
    used: List[Tuple[str, float, float]] = []

    def reused(a: Dict[str, Any], s0: float, e0: float) -> bool:
        return any(u[0] == a["id"] and min(e0, u[2]) - max(s0, u[1]) > 0.5 * max(0.1, e0 - s0) for u in used)

    guard = 0
    while t < target - 0.05 and guard < 4000:
        guard += 1
        if not cand:
            break
        tries = 0
        while True:  # não repete o mesmo trecho enquanto houver material novo
            a, s, e = cand[k % len(cand)]
            k += 1
            tries += 1
            if not st.get("dedupe") or a["kind"] == "image" or not reused(a, s, e) or tries >= len(cand):
                break
        progress = t / max(1.0, target)
        n = len(segs)
        if a["kind"] == "image":
            d = (rnd.uniform(*pace) if pace else beat * 4) * fast
            if st.get("vary"):
                d *= 1 + rnd.uniform(-st["vary"], st["vary"])
            d = min(d, max(target - t, 0.4))
            seg = {"asset": a["id"], "in": 0.0, "dur": round(d, 3), "speed": 1.0}
        else:
            if pace is None:
                if st.get("buildup"):  # introdução/estrofe mais lenta, «drop»/refrão com cortes de 1-2 batidas, fecho calmo
                    choices = (4, 4, 2) if progress < 0.25 else ((2, 4) if progress > 0.9 else (1, 2, 2, 1))
                else:
                    choices = (1, 2, 2, 4)
                d = beat * rnd.choice(choices) if st["use"] == "grid" else beat * 4
            elif st["use"] == "spread" and pace[0] > pace[1]:  # trailer: do mais longo ao mais curto
                d = pace[0] + (pace[1] - pace[0]) * progress
            else:
                d = min(max(e - s, min(pace)), max(pace)) * fast if e - s > 0 else min(pace)
            d = max(0.4, min(d, target - t) if target - t > 0.4 else d)
            speed = 1.0
            if st.get("ramps"):
                speed = 0.5 if progress > 0.92 else (0.6, 1.0, 1.5, 1.0)[n % 4]  # rampas com moderação; fecha em câmera lenta
                if progress < 0.25:
                    speed = 1.0
            src_len = d * speed
            if e - s < src_len:
                s = max(0.0, min(s, a["dur"] - src_len))
            if s + src_len > a["dur"] + 1e-6:
                src_len = max(0.3, a["dur"] - s)
                d = src_len / speed
            seg = {"asset": a["id"], "in": round(s, 3), "dur": round(d, 3), "speed": speed}
            used.append((a["id"], s, s + src_len))
        zoom_now = st["punch"] if st["punch_every"] and (n % st["punch_every"] == st["punch_every"] - 1) else 1.0
        if st.get("hook") and n == 0:
            zoom_now = max(zoom_now, st["punch"])  # o gancho já abre com um zoom
        if st.get("buildup") and st["use"] == "grid" and st.get("ramps") and 0.25 <= progress <= 0.9:
            zoom_now = st["punch"] if n % 2 == 0 else 1.0  # no «drop» o zoom bate a cada corte
        px = py = 0.0
        if st.get("pan") and (a["kind"] == "image" or zoom_now > 1.0 or st["use"] == "sequential"):
            zoom_now = max(zoom_now, 1.06)
            px = (0.3, -0.3, 0.0, 0.2)[n % 4] * (zoom_now - 1) / 0.12 if zoom_now > 1 else 0.0
            py = (0.0, 0.15, -0.15, 0.0)[n % 4] * (zoom_now - 1) / 0.12
            px, py = max(-0.5, min(0.5, px)), max(-0.5, min(0.5, py))
        seg.update(scale=round(zoom_now, 2), x=round(px, 3), y=round(py, 3), filter=st["grade"], fade_in=st["fade"] if t == 0 or st["fade"] else 0, fade_out=st["fade"], mute=st["orig_vol"] <= 0.001, volume=st["orig_vol"])
        segs.append(seg)
        t += seg["dur"]
    if st.get("chrono") and len(segs) > 2:  # gancho primeiro; o resto na ordem em que aconteceu
        order = {a["id"]: i for i, a in enumerate(footage)}
        segs = segs[:1] + sorted(segs[1:], key=lambda g: (order.get(g["asset"], 0), g["in"]))
    total = round(sum(s["dur"] for s in segs), 3)
    titles: List[Dict[str, Any]] = []
    if st["titles"]:
        cards = [x for x in directives.get("titles", []) if isinstance(x, str) and x.strip()][:4] or ([title] if title else [])
        for i, c in enumerate(cards):
            at = 0.5 if i == 0 else total * i / max(1, len(cards))
            titles.append({"text": c[:90], "start": round(at, 2), "dur": 2.8 if i == 0 else 2.2})
    if st.get("endcard") and title and total > 6:
        titles.append({"text": title[:90], "start": round(max(0.0, total - 2.4), 2), "dur": 2.3})  # trailer: cartela final
    return {"segments": segs, "total": total, "music": music, "voice": voice, "titles": titles, "style": style_id}


# ---------------------------------------------------------------------------------------------------- pipeline
class AutoEditPipeline(Runner):
    domain = "studio"

    def __init__(self, store: Store, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False):
        super().__init__(store, emit, cancelled)
        self.ss = store.studio
        self.demo = True

    def _ask(self, step: str, agent: str, instruction: str, payload: Dict[str, Any], fallback: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Tuple[Dict[str, Any], bool]:
        if self.demo:
            self._check()
            return fallback(payload), False
        return self._agent(step, agent, instruction, payload, fallback, salvage=True)

    def run(self, req: Dict[str, Any]) -> Dict[str, Any]:
        tools.need_ffmpeg("A edição automática")
        style_id = req.get("style") if req.get("style") in EDIT_STYLES else "gameplay"
        st = EDIT_STYLES[style_id]
        settings = self.store.get_settings()
        gid = settings["active"].get("generation", "demo")
        self.demo = gid == "demo"
        self.provider = build_provider(settings, gid, self.store.models_dir)
        self.gen = {"temperature": 0.3, "max_tokens": 3000, "content": "free"}
        prompt = text(req.get("prompt"), "", 4000)
        self.emit({"type": "start", "steps": ["attachments", "analyst", "director", "reviewer", "assemble"], "style": style_id, "demo": self.demo})

        # ---- anexos
        self._step("attachments", "running")
        metas = [m for m in (self.store.get_upload(u) for u in (req.get("attachment_ids") or [])[:60] if isinstance(u, str)) if m]
        if not metas:
            raise ValueError("Anexe os vídeos, imagens e áudios que você quer editar.")
        aspect = req.get("aspect") if req.get("aspect") in S.ASPECTS else ("9:16" if style_id in ("phonk",) else "16:9")
        name = text(req.get("name"), "", 100) or text(prompt.splitlines()[0] if prompt else "", "", 60) or f"Edição {st['label']}"
        existing = self.ss.get(str(req.get("project_id") or "")) if req.get("project_id") else None
        if existing:
            pid = existing["id"]
        else:
            proj = self.ss.create({"name": name, "kind": "single", "duration_type": "custom", "target_seconds": max(S.MIN_SECONDS, float(num(req.get("target_seconds"), 0, 0, S.MAX_SECONDS)) or st["default_target"]),
                                   "aspect": aspect, "style": "realistic", "language": text(req.get("language"), "pt-BR", 12), "premise": prompt})
            pid = proj["id"]
        inv: List[Dict[str, Any]] = []
        for m in metas:
            self._check()
            path = Path(m["path"])
            with open(path, "rb") as f:
                head = f.read(4096)
            mime = sniff_mime(head) or str(m.get("mime") or "")
            kind = mime.split("/")[0] if mime.split("/")[0] in ("image", "video", "audio") else ""
            if not kind:
                self.warnings.append(f"{m['name']}: formato não reconhecido — ignorado")
                continue
            rec = self.ss.add_asset_file(pid, path, MIME_EXT.get(mime) or path.suffix.lstrip(".") or "bin", kind, name=m["name"], mime=mime)
            if not rec:
                continue
            item = {"id": rec["id"], "name": m["name"], "kind": kind, "dur": rec["dur"], "has_audio": rec["audio"], "path": self.ss.media_path(pid, rec["file"]), "loud": [], "changes": [], "silences": []}
            if kind == "video":
                src = item["path"]
                item["changes"] = tools.scene_changes(src, 0.3) if st["use"] in ("loud", "sequential") else []
                if rec["audio"]:
                    item["loud"] = tools.loud_moments(src, 0.5) if st["use"] in ("loud", "grid", "spread") else []
                    item["silences"] = tools.silences(src) if st["silence"] else []
            inv.append(item)
            self.emit({"type": "note", "message": f"Analisado: {m['name']} ({rec['dur']:.0f}s)"})
        if not inv:
            raise ValueError("Nenhum dos arquivos é um vídeo, imagem ou áudio que eu consiga editar.")
        for m in metas:
            self.store.delete_upload(m["id"])
        self._step("attachments", "done", count=len(inv))

        # ---- analista
        self._step("analyst", "running")
        light = [{k: (v if k not in ("loud", "changes", "silences") else len(v)) for k, v in a.items() if k != "path"} for a in inv]
        obj, fb = self._ask("analyst", "studio_edit_analyst", ANALYST, {"files": light, "prompt": prompt, "style": st["label"]}, lambda pl: {"title": "", "focus": [], "roles": guess_roles(inv)})
        roles = {a["id"]: (obj.get("roles") or {}).get(a["id"]) if (obj.get("roles") or {}).get(a["id"]) in ROLES else None for a in inv}
        guessed = guess_roles(inv)
        roles = {i: (r or guessed[i]) for i, r in roles.items()}
        if not any(r == "footage" for r in roles.values()):
            roles = guessed
        title = text(obj.get("title"), "", 90) or name
        self._step("analyst", "warn" if fb else "done", footage=sum(r == "footage" for r in roles.values()), music=sum(r == "music" for r in roles.values()))

        # ---- diretor
        self._step("director", "running")
        footage_total = sum(a["dur"] for a in inv if roles[a["id"]] == "footage" and a["kind"] == "video") or sum(1 for a in inv if a["kind"] == "image") * 4.0
        music_dur = max([a["dur"] for a in inv if roles[a["id"]] == "music"] + [0.0])
        target = float(num(req.get("target_seconds"), 0, 0, S.MAX_SECONDS))
        if target <= 0:
            target = st["default_target"]
            if st["use"] == "grid" and music_dur:
                target = min(music_dur, 180)
            target = min(target, max(5.0, footage_total if st["use"] != "grid" else target))
        dp = {"roles": roles, "style": {k: st.get(k) for k in ("label", "hint", "pace", "use", "craft")}, "target_seconds": target, "prompt": prompt, "files": [{"id": a["id"], "name": a["name"], "dur": a["dur"], "role": roles[a["id"]]} for a in inv]}
        dobj, fb2 = self._ask("director", "studio_edit_director", DIRECTOR, dp, lambda pl: {"pace": "medium", "order": [], "highlights": [], "avoid": [], "titles": []})
        directives = {"pace": dobj.get("pace") if dobj.get("pace") in ("fast", "medium", "slow") else "medium",
                      "order": [i for i in (dobj.get("order") or []) if isinstance(i, str)], "highlights": [h for h in (dobj.get("highlights") or []) if isinstance(h, dict)][:8],
                      "avoid": [h for h in (dobj.get("avoid") or []) if isinstance(h, dict)][:6], "titles": [t for t in (dobj.get("titles") or []) if isinstance(t, str)][:4]}
        seed = sum(ord(c) for c in (prompt + style_id + title))
        edl = plan_edl(style_id, inv, roles, target, directives, float(num(req.get("bpm"), 0, 0, 300)), seed, title)
        self._step("director", "warn" if fb2 else "done", cuts=len(edl["segments"]), seconds=round(edl["total"], 1))

        # ---- revisor
        self._step("reviewer", "running")
        issues = self._check_edl(edl, inv, target)
        avg = edl["total"] / max(1, len(edl["segments"]))
        cobj, fb3 = self._ask("reviewer", "studio_edit_reviewer", CRITIC, {"style": st["label"], "prompt": prompt, "target_seconds": target, "total": edl["total"], "cuts": len(edl["segments"]), "avg_cut": round(avg, 2),
                                                                           "music": bool(edl["music"]), "voice": bool(edl["voice"]), "checks": issues}, lambda pl: {"approved": not issues, "tips": []})
        tips = [text(x, "", 160) for x in (cobj.get("tips") or [])][:3] if isinstance(cobj.get("tips"), list) else []
        self.warnings.extend(issues)
        self.warnings.extend(f"dica: {x}" for x in tips)
        self._step("reviewer", "warn" if issues else "done", issues=len(issues))

        # ---- montagem
        self._step("assemble", "running")
        eid = self._assemble(pid, name, title, prompt, st, edl, inv, target, style_id)
        self._step("assemble", "done", seconds=round(edl["total"], 1))
        result = {"type": "done", "project_id": pid, "episode_id": eid, "duration": round(edl["total"], 2), "cuts": len(edl["segments"]), "style": style_id, "warnings": self.warnings[:20]}
        self.emit(result)
        return result

    @staticmethod
    def _check_edl(edl: Dict[str, Any], inv: List[Dict[str, Any]], target: float) -> List[str]:
        issues = []
        by = {a["id"]: a for a in inv}
        if abs(edl["total"] - target) > max(2.0, target * 0.12):
            issues.append(f"a edição ficou com {edl['total']:.0f}s para um alvo de {target:.0f}s (faltou material)")
        for s in edl["segments"]:
            a = by[s["asset"]]
            if a["kind"] == "video" and s["in"] + s["dur"] * s["speed"] > a["dur"] + 0.05:
                issues.append("um corte passa do fim do arquivo")
                break
        segs = edl["segments"]
        dup = sum(1 for i, g in enumerate(segs) for h in segs[:i] if g["asset"] == h["asset"] and min(g["in"] + g["dur"] * g["speed"], h["in"] + h["dur"] * h["speed"]) - max(g["in"], h["in"]) > 0.5 * g["dur"] * g["speed"])
        if dup > max(1, len(segs) // 6) and EDIT_STYLES[edl["style"]].get("dedupe"):
            issues.append(f"{dup} cortes repetem trechos já usados (faltou material novo: anexe mais vídeos ou reduza a duração)")
        if not edl["music"] and EDIT_STYLES[edl["style"]]["use"] == "grid":
            issues.append("estilo de batida sem música: anexe uma faixa para os cortes seguirem o compasso")
        return issues

    def _assemble(self, pid: str, name: str, title: str, prompt: str, st: Dict[str, Any], edl: Dict[str, Any], inv: List[Dict[str, Any]], target: float, style_id: str) -> str:
        by = {a["id"]: a for a in inv}
        eid_box: List[str] = []

        def fn(p: Dict[str, Any]) -> None:
            tr = {nm: next(t["id"] for t in S.default_tracks() if t["name"] == nm) for nm in ("V1", "V2", "A1", "A2", "A3", "T1")}
            clips: List[Dict[str, Any]] = []
            t = 0.0
            for i, s in enumerate(edl["segments"]):
                a = by[s["asset"]]
                clips.append({"id": f"cut{i}", "track": tr["V1"], "asset": s["asset"], "label": a["name"][:40], "start": round(t, 3), "dur": round(s["dur"], 3), "in": s["in"], "speed": s["speed"],
                              "mute": s["mute"] or a["kind"] == "image", "volume": s["volume"], "fade_in": s["fade_in"], "fade_out": s["fade_out"], "scale": s["scale"], "x": s.get("x", 0.0), "y": s.get("y", 0.0), "filter": s["filter"], "fit": "cover"})
                t += s["dur"]
            total = t
            vt = 0.0
            for i, v in enumerate(edl["voice"]):
                if vt >= total:
                    break
                d = min(v["dur"] or total, total - vt)
                clips.append({"id": f"voz{i}", "track": tr["A1"], "asset": v["id"], "label": v["name"][:40], "start": round(vt, 3), "dur": round(d, 3), "volume": st["voice_vol"]})
                vt += d
            mt, k = 0.0, 0
            while edl["music"] and mt < total - 0.05 and k < 60:
                m = edl["music"][k % len(edl["music"])]
                d = min(m["dur"] or total, total - mt)
                clips.append({"id": f"mus{k}", "track": tr["A2"], "asset": m["id"], "label": m["name"][:40], "start": round(mt, 3), "dur": round(d, 3), "volume": round(st["music_vol"] * (0.45 if edl["voice"] else 1.0), 3),  # abaixa a música quando há narração
                              "fade_in": 0.5 if k == 0 else 0, "fade_out": 1.5 if mt + d >= total - 0.06 else 0})
                mt += d
                k += 1
            for i, c in enumerate(edl["titles"]):
                clips.append({"id": f"tit{i}", "track": tr["T1"], "start": c["start"], "dur": min(c["dur"], max(0.5, total - c["start"])), "text": c["text"], "size": 60 if p["aspect"] != "9:16" else 54,
                              "color": "#ffffff", "bg": "#000000", "pos": "center"})
            ep_raw = {"title": title, "prompt": prompt, "target": target, "status": "ready", "origin": "autoedit", "edit": {"style": style_id, "label": st["label"], "cuts": len(edl["segments"])},
                      "timeline": {"tracks": S.default_tracks(), "clips": clips, "markers": []}}
            if p["kind"] == "series" and p["episodes"] and any(e["timeline"]["clips"] for e in p["episodes"]):
                ep = S.normalize_episode(ep_raw, len(p["episodes"]))
                p["episodes"].append(ep)
            elif p["episodes"]:
                ep = S.normalize_episode({**ep_raw, "id": p["episodes"][0]["id"]}, 0)
                p["episodes"][0] = ep
            else:
                ep = S.normalize_episode(ep_raw, 0)
                p["episodes"].append(ep)
            eid_box.append(ep["id"])
            if p["name"].startswith("Novo projeto"):
                p["name"] = name

        self.ss.update(pid, fn)
        return eid_box[0]
