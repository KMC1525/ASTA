"""Pipeline do Studio: gera um episódio CENA A CENA (nunca tudo de uma vez).

Planejamento (Showrunner): roteiro em cenas (em atos, se forem muitas) → depois, para cada cena, os mesmos cinco passos:

    recebe   reúne o briefing da cena + contexto (bíblia da série, estilo, continuidade da cena anterior)
    analisa  o Analista divide em planos, ajusta a narração à duração e define música/efeito
    gera     voz, imagens, movimento (Ken Burns ou modelo de vídeo), música e efeito pelos provedores de mídia
    revisa   verificações objetivas + Revisor (IA); se reprovar, aplica a correção e refaz só o que mudou
    entrega  coloca os clipes na timeline do episódio (já editável) e segue para a próxima cena

Cena entregue fica salva: um job cancelado/falho pode ser retomado de onde parou e uma cena pode ser refeita sozinha. Sem IA de texto (modo Demo) ou com uma resposta inválida,
os agentes determinísticos de `rulebased.py` assumem — a entrega nunca falha por culpa do modelo de texto.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import attachments as att
from .. import voice
from ..agents import prompts
from ..agents.runner import Cancelled, Runner
from ..canvas import procedural as proc
from ..canvas.media import Ctl, Media, build_media, pick_provider, size_of_aspect
from ..providers import ProviderError, build_provider
from ..storage import Store
from ..util import num, text
from . import rulebased as rb
from . import schema as S
from . import tools

PLANNER = """ROLE: Showrunner (episode planner).
Write the scene-by-scene script of ONE video from INPUT_JSON: prompt, attachments digest, style, series bible and recaps of previous episodes, target_seconds and scene_count.
If `act_summary` is present you are writing ONLY the scenes of that act (INPUT_JSON.scene_count scenes), continuing right after `previous_scene`.
Rules: exactly scene_count scenes; the sum of "secs" must be about target_seconds; "narration" is spoken voice-over (about 2.4 words per second of the scene; empty when a scene is silent);
"visual" is a concrete description for an image generator (subject, setting, light, framing) WITHOUT style words (the style is added later); keep characters and looks consistent with the bible;
in a series, continue the story from the recaps and never repeat them. Write all texts in the user's language.
Output JSON: {"title": str, "logline": str, "scenes": [{"title": str, "summary": str, "narration": str, "visual": str, "sound": str, "secs": number}],
 "bible": {"tone": str, "world": str, "characters": [{"name": str, "look": str}]}}"""

OUTLINER = """ROLE: Showrunner (outline).
The episode is long, so first outline it in acts. From INPUT_JSON (prompt, digest, bible, recaps, scene_count, per_act) split the story into acts of at most per_act scenes each.
Output JSON: {"title": str, "logline": str, "acts": [{"title": str, "summary": "2-3 sentences", "scenes": int}]}  (the "scenes" values must add up to scene_count)"""

ANALYST = """ROLE: Scene analyst.
Prepare ONE scene for production from INPUT_JSON: scene brief, context (style look, bible, previous scene continuity), secs and shot_len.
Split the scene into shots (about secs/shot_len shots, each "secs" between 2 and 30 and summing to secs). Each shot "visual" is a concrete image description (no style words), consistent with the context.
Trim the narration so it fits the scene (at most words_budget words), keeping its meaning; give a music mood and an optional sound effect; "continuity" is one sentence the next scene must respect.
Output JSON: {"shots": [{"visual": str, "camera": str, "secs": number}], "narration": str, "music": str, "sfx": str, "continuity": str}"""

REVIEWER = """ROLE: Scene reviewer.
Check ONE produced scene (INPUT_JSON: brief, shots, narration, secs, objective checks). Approve when it follows the brief, is coherent and fits its duration.
If something must change, list the issues and give a "fix" with ONLY the fields to replace: "narration" (shorter/clearer text) and/or "shots" (a new full list). Never change the story.
Output JSON: {"approved": bool, "score": 0-10, "issues": [str], "fix": {"narration": str|null, "shots": [{"visual": str, "camera": str, "secs": number}]|null}}"""

RECAP = """ROLE: Continuity editor.
Summarize the finished episode (INPUT_JSON: title, scenes) in at most 3 sentences ("recap", spoiler-friendly for a future "previously on…") and list what the series bible must remember.
Output JSON: {"recap": str, "bible_update": {"characters": [{"name": str, "look": str}], "facts": [str]}}"""

MAX_CONSECUTIVE_ERRORS = 3


class StudioPipeline(Runner):
    domain = "studio"

    def __init__(self, store: Store, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False):
        super().__init__(store, emit, cancelled)
        self.ss = store.studio
        self.pid = ""
        self.eid = ""
        self.demo = True
        self.media: Dict[str, Any] = {}
        self.settings: Dict[str, Any] = {}
        self.ctl = Ctl(check=self._check, note=lambda m: self.emit({"type": "note", "message": m}))

    # ------------------------------------------------------------------ acesso ao documento
    def _project(self) -> Dict[str, Any]:
        p = self.ss.get(self.pid)
        if not p:
            raise ValueError("Projeto não encontrado")
        return p

    @staticmethod
    def _find(ep_list: List[Dict[str, Any]], eid: str) -> Optional[Dict[str, Any]]:
        return next((e for e in ep_list if e["id"] == eid), None)

    def _mut(self, fn: Callable[[Dict[str, Any], Dict[str, Any]], Any]) -> Dict[str, Any]:
        out = self.ss.update(self.pid, lambda p: fn(p, self._find(p["episodes"], self.eid) or {}))
        if out is None:
            raise ValueError("Projeto não encontrado")
        return out

    def _scene(self, sid: str) -> Dict[str, Any]:
        ep = self._find(self._project()["episodes"], self.eid) or {}
        return next((s for s in ep.get("scenes", []) if s["id"] == sid), {})

    def _stage(self, sid: str, n: int, stage: str, status: str, detail: str = "") -> None:
        def fn(p: Dict[str, Any], ep: Dict[str, Any]) -> None:
            for s in ep.get("scenes", []):
                if s["id"] == sid:
                    s["stages"][stage] = status
                    if stage == "receive" and status == "running":
                        s["status"] = "running"
                        s["stages"] = {k: ("pending" if k != "receive" else "running") for k in S.STAGES}

        self._mut(fn)
        self.emit({"type": "scene", "id": sid, "n": n, "stage": stage, "status": status, "detail": detail})

    # ------------------------------------------------------------------ agentes (Demo/falha → determinístico)
    def _ask(self, step: str, agent: str, instruction: str, payload: Dict[str, Any], fallback: Callable[[Dict[str, Any]], Dict[str, Any]], tokens: float = 1.0) -> Tuple[Dict[str, Any], bool]:
        if self.demo:
            self._check()
            return fallback(payload), False
        n0 = len(self.warnings)
        obj, fb = self._agent(step, agent, instruction, payload, fallback, tokens_mult=tokens)
        if len(self.warnings) > n0 and len(self.warnings) > 30:
            del self.warnings[30:]
        return obj, fb

    # ------------------------------------------------------------------ mídia
    def _media_pid(self, cap: str) -> str:
        """Provedor de mídia de um tipo. Se o usuário nunca escolheu um (Demo) mas usa o OpenRouter no chat e ele já tem chave, o Studio usa o próprio OpenRouter para imagem,
        vídeo e voz — assim o OpenRouter funciona no Studio sem configurar nada além da chave/login."""
        pid = pick_provider(self.settings, cap)
        if pid == "demo" and self.settings["active"].get("generation") == "openrouter" and ((self.settings.get("providers") or {}).get("openrouter") or {}).get("api_key"):
            return "openrouter"
        return pid

    def _provider(self, cap: str) -> Any:
        if cap not in self.media:
            pid = self._media_pid(cap)
            self.media[cap] = (pid, build_media(self.settings, pid, self.ctl, self.store.models_dir))
        return self.media[cap][1]

    def _save(self, m: Media, kind: str, name: str, sid: str, prompt: str = "") -> Dict[str, Any]:
        rec = self.ss.add_asset(self.pid, m.data, m.ext, kind, name=name, mime=m.mime, source="generated", scene=sid, prompt=prompt[:600])
        if not rec:
            raise ProviderError("Não foi possível salvar a mídia gerada.")
        return rec

    # ------------------------------------------------------------------ execução
    def run(self, req: Dict[str, Any]) -> Dict[str, Any]:
        self.pid, self.eid = str(req.get("project_id") or ""), str(req.get("episode_id") or "")
        p = self._project()
        ep = self._find(p["episodes"], self.eid)
        if not ep:
            raise ValueError("Episódio não encontrado")
        self.settings = self.store.get_settings()
        gid = self.settings["active"].get("generation", "demo")
        self.demo = gid == "demo"
        self.provider = build_provider(self.settings, gid, self.store.models_dir)
        self.gen = {"temperature": 0.7, "max_tokens": 3500, "content": self.settings["generation"].get("content") if self.settings["generation"].get("content") == "sfw" else "free"}
        self.language = prompts.lang_name(p["language"])
        tools.need_ffmpeg("O Studio")
        prompt = text(req.get("prompt"), "", 8000) or ep["prompt"] or p["premise"]
        digest = self._attachments(req)
        redo = [str(x) for x in (req.get("redo") or [])] if isinstance(req.get("redo"), list) else []
        self.emit({"type": "start", "project": self.pid, "episode": self.eid, "demo": self.demo, "provider": f"{gid}:{self.provider.model}"})

        if req.get("replan") or not ep["scenes"]:
            self._plan(p, ep, prompt, digest)
        ep = self._find(self._project()["episodes"], self.eid) or ep
        scenes = ep["scenes"]
        self.emit({"type": "plan", "title": ep["title"], "scenes": [{"id": s["id"], "n": i + 1, "title": s["title"], "secs": s["secs"], "status": s["status"], "stages": s["stages"]} for i, s in enumerate(scenes)]})
        todo = [s["id"] for s in scenes if (s["id"] in redo if redo else s["status"] != "delivered")]
        errors, done_n = 0, 0
        for sid in todo:
            self._check()
            i = next(k for k, s in enumerate(self._find(self._project()["episodes"], self.eid)["scenes"]) if s["id"] == sid)
            try:
                self._run_scene(sid, i + 1, len(scenes), prompt)
                errors = 0
                done_n += 1
            except Cancelled:
                raise
            except (ProviderError, ValueError, OSError) as exc:
                if str(exc) == "cancelado":
                    raise Cancelled() from None
                errors += 1
                self.warnings.append(f"cena {i + 1}: {str(exc)[:200]}")
                self._mut(lambda p, e, sid=sid: [s.update(status="error") for s in e.get("scenes", []) if s["id"] == sid])
                self.emit({"type": "scene", "id": sid, "n": i + 1, "stage": "error", "status": "error", "detail": str(exc)[:300]})
                if errors >= MAX_CONSECUTIVE_ERRORS or (done_n == 0 and errors >= 1 and len(todo) == 1):
                    raise ProviderError(f"A geração parou na cena {i + 1}: {str(exc)[:300]}") from None
            self.emit({"type": "progress", "done": sum(1 for s in self._find(self._project()["episodes"], self.eid)["scenes"] if s["status"] == "delivered"), "total": len(scenes)})
        ep = self._find(self._project()["episodes"], self.eid) or ep
        if all(s["status"] == "delivered" for s in ep["scenes"]):
            self._finish_episode(ep)
        p = self._project()
        ep = self._find(p["episodes"], self.eid) or ep
        result = {"type": "done", "project_id": self.pid, "episode_id": self.eid, "scenes": len(ep["scenes"]), "delivered": sum(1 for s in ep["scenes"] if s["status"] == "delivered"),
                  "duration": ep["timeline"]["duration"], "target": ep["target"] or p["target_seconds"], "warnings": self.warnings[:30]}
        self.emit(result)
        return result

    def _attachments(self, req: Dict[str, Any]) -> str:
        ids = [x for x in (req.get("attachment_ids") or []) if isinstance(x, str)][:20] if isinstance(req.get("attachment_ids"), list) else []
        metas = [m for m in (self.store.get_upload(u) for u in ids) if m]
        if not metas:
            return ""
        tr = voice.transcriber(self.settings)
        analyzed = [att.analyze(Path(m["path"]), m["name"], m.get("mime", ""), transcribe=tr) for m in metas]
        for m in metas:
            self.store.delete_upload(m["id"])
        return att.build_digest(analyzed)[:8000]

    # ------------------------------------------------------------------ planejamento
    def _plan(self, p: Dict[str, Any], ep: Dict[str, Any], prompt: str, digest: str) -> None:
        target = float(ep["target"] or p["target_seconds"])
        spec = S.DURATION_TYPES[p["duration_type"]]
        n = max(1, min(S.MAX_SCENES, int(round(target / spec["scene_len"]))))
        recaps = [{"episode": e["n"], "title": e["title"], "recap": e["recap"]} for e in p["episodes"] if e["id"] != ep["id"] and e["recap"]][-6:]
        base = {"prompt": prompt[:4000], "digest": digest[:5000], "title": ep["title"], "language": p["language"], "style": S.STYLES[p["style"]]["label"], "kind": p["kind"], "episode": ep["n"],
                "recaps": recaps, "bible": p["bible"], "premise": p["premise"][:1500], "target_seconds": target, "scene_count": n}
        self._step("planner", "running")
        scenes: List[Dict[str, Any]] = []
        title, logline, bible = ep["title"], "", {}
        if n <= 12:
            obj, fb = self._ask("planner", "studio_planner", PLANNER, base, rb.planner, 1.4)
            title, logline, bible = obj.get("title") or title, obj.get("logline", ""), obj.get("bible") or {}
            scenes = self._norm_scenes(obj.get("scenes"), n, target) or self._norm_scenes(rb.planner(base)["scenes"], n, target)
        else:
            per = 10
            out, fb = self._ask("planner", "studio_outliner", OUTLINER, {**base, "per_act": per}, rb.outliner)
            acts = [a for a in (out.get("acts") or []) if isinstance(a, dict)] or rb.outliner({**base, "per_act": per})["acts"]
            counts = [max(1, int(num(a.get("scenes"), per, 1, 16))) for a in acts]
            if sum(counts) != n:  # o modelo errou a soma: redistribui
                k = len(acts)
                counts = [n // k + (1 if i < n % k else 0) for i in range(k)]
            title, logline = out.get("title") or title, out.get("logline", "")
            prev = None
            for ai, (a, cnt) in enumerate(zip(acts, counts)):
                self._check()
                payload = {**base, "act_title": text(a.get("title"), "", 100), "act_summary": text(a.get("summary"), "", 600) or prompt[:300], "scene_count": cnt, "previous_scene": prev,
                           "target_seconds": target * cnt / n, "first_index": len(scenes)}
                obj, fb2 = self._ask("planner", "studio_planner", PLANNER, payload, rb.planner, 1.4)
                part = self._norm_scenes(obj.get("scenes"), cnt, target * cnt / n) or self._norm_scenes(rb.planner(payload)["scenes"], cnt, target * cnt / n)
                scenes += part
                prev = {"title": part[-1]["title"], "summary": part[-1]["summary"]} if part else prev
                bible = bible or obj.get("bible") or {}
                fb = fb or fb2
                self.emit({"type": "note", "message": f"Ato {ai + 1}/{len(acts)} planejado ({len(scenes)}/{n} cenas)"})
        scenes = self._timings(scenes, target)

        def fn(pr: Dict[str, Any], e: Dict[str, Any]) -> None:
            e["title"] = text(title, e["title"], 120)
            e["logline"] = text(logline, "", 600)
            e["prompt"] = prompt
            e["target"] = target
            e["scenes"] = scenes
            e["status"] = "planned"
            e["timeline"] = {"tracks": e["timeline"]["tracks"], "clips": [], "markers": []}
            if not pr["premise"]:
                pr["premise"] = text(prompt, "", 4000)
            self._merge_bible(pr, bible)

        self._mut(fn)
        self._step("planner", "warn" if fb else "done", scenes=len(scenes), title=title)

    @staticmethod
    def _norm_scenes(raw: Any, n: int, target: float) -> List[Dict[str, Any]]:
        out = []
        for i, s in enumerate(raw if isinstance(raw, list) else []):
            if not isinstance(s, dict):
                continue
            out.append(S.normalize_scene({"title": s.get("title") or f"Cena {i + 1}", "summary": s.get("summary") or s.get("visual"), "narration": s.get("narration"), "visual": s.get("visual") or s.get("summary"),
                                          "sound": s.get("sound"), "secs": num(s.get("secs"), target / max(1, n), 1, 7200)}, i))
        if not out:
            return []
        return out[:n] + [S.normalize_scene({**out[-1], "id": "", "title": f"{out[-1]['title']} (cont.)", "narration": ""}, len(out) + k) for k in range(max(0, n - len(out)))]

    @staticmethod
    def _timings(scenes: List[Dict[str, Any]], target: float) -> List[Dict[str, Any]]:
        secs = rb.scale_secs([s["secs"] for s in scenes], target, lo=2.0)
        t = 0.0
        for i, (s, d) in enumerate(zip(scenes, secs)):
            s["n"], s["secs"], s["start"] = i + 1, round(d, 2), round(t, 2)
            t += s["secs"]
        return scenes

    @staticmethod
    def _merge_bible(p: Dict[str, Any], upd: Any) -> None:
        if not isinstance(upd, dict):
            return
        b = p["bible"]
        b["tone"] = text(upd.get("tone"), b.get("tone", ""), 200) or b.get("tone", "")
        b["world"] = text(upd.get("world"), b.get("world", ""), 800) or b.get("world", "")
        have = {c["name"].lower(): c for c in b["characters"]}
        for c in (upd.get("characters") if isinstance(upd.get("characters"), list) else []):
            if isinstance(c, dict) and text(c.get("name"), "", 40):
                nm = text(c["name"], "", 40)
                if nm.lower() in have:
                    have[nm.lower()]["look"] = text(c.get("look"), have[nm.lower()].get("look", ""), 300)
                elif len(b["characters"]) < 20:
                    b["characters"].append({"name": nm, "look": text(c.get("look"), "", 300)})
        for f in (upd.get("facts") if isinstance(upd.get("facts"), list) else []):
            f = text(f, "", 200)
            if f and f not in b["facts"]:
                b["facts"].append(f)
        b["facts"] = b["facts"][-40:]

    # ------------------------------------------------------------------ uma cena
    def _look_for(self, p: Dict[str, Any], visual: str, extra: str = "") -> Tuple[str, str]:
        st = S.style_look(p)
        who = [f"{c['name']}: {c['look']}" for c in p["bible"]["characters"] if c["look"] and c["name"].lower() in (visual + " " + extra).lower()][:4]
        prompt = ", ".join(x for x in [visual.strip().rstrip("."), "; ".join(who), st["look"], p["bible"].get("tone", "")] if x)
        return prompt[:1500], st["negative"]

    def _run_scene(self, sid: str, n: int, total: int, prompt: str) -> None:
        p = self._project()
        ep = self._find(p["episodes"], self.eid) or {}
        scenes = ep["scenes"]
        idx = n - 1
        sc = scenes[idx]
        spec = S.DURATION_TYPES[p["duration_type"]]
        secs = float(sc["secs"])
        # ---- recebe
        self._stage(sid, n, "receive", "running")
        prev = scenes[idx - 1] if idx > 0 else None
        nxt = scenes[idx + 1] if idx + 1 < total else None
        context = {"style": S.STYLES[p["style"]]["label"], "look": S.style_look(p)["look"], "bible": p["bible"], "episode": ep["title"], "logline": ep["logline"], "language": p["language"],
                   "previous": {"title": prev["title"], "summary": prev["summary"], "continuity": prev["continuity"]} if prev else None, "next": {"title": nxt["title"], "summary": nxt["summary"]} if nxt else None}
        self._stage(sid, n, "receive", "done", f"{secs:.0f}s")
        # ---- analisa
        self._stage(sid, n, "analyze", "running")
        brief = {k: sc[k] for k in ("title", "summary", "narration", "visual", "sound", "music")}
        shot_len = min(spec["shot_len"], max(2, secs / 2)) if secs > 2 else secs
        budget = rb.word_budget(secs)
        obj, fb = self._ask("scene_analyst", "studio_analyst", ANALYST, {"scene": brief, "context": context, "secs": secs, "shot_len": shot_len, "words_budget": budget, "tone": p["bible"].get("tone", "")}, rb.analyst)
        shots = self._shots(obj.get("shots"), secs) or self._shots(rb.analyst({"scene": brief, "secs": secs, "shot_len": shot_len})["shots"], secs)
        narration = rb.trim_words(text(obj.get("narration"), sc["narration"], 3000), budget) if sc["narration"] or obj.get("narration") else ""
        plan = {"shots": shots, "narration": narration, "music": text(obj.get("music"), "", 200) or sc["music"] or p["bible"].get("tone", "") or "cinematic ambient", "sfx": text(obj.get("sfx"), "", 200) or sc["sound"],
                "continuity": text(obj.get("continuity"), "", 400) or sc["summary"]}
        self._mut(lambda pr, e: [s.update(shots=[dict(x) for x in shots], narration=narration, music=plan["music"], continuity=plan["continuity"]) for s in e["scenes"] if s["id"] == sid])
        self._stage(sid, n, "analyze", "warn" if fb else "done", f"{len(shots)} planos")
        # ---- gera
        self._stage(sid, n, "generate", "running")
        gen = self._generate(p, sid, n, plan, secs, idx)
        self._stage(sid, n, "generate", "done", f"{len(gen['shot_assets'])} planos, voz {gen['voice_dur']:.0f}s")
        # ---- revisa
        self._stage(sid, n, "review", "running")
        score, notes, revised = self._review(p, sid, n, plan, gen, secs, brief, idx)
        self._stage(sid, n, "review", "warn" if notes else "done", f"nota {score}" if score is not None else "")
        # ---- entrega
        self._stage(sid, n, "deliver", "running")
        actual = self._deliver(p, sid, n, plan, gen, secs, score, notes)
        self._stage(sid, n, "deliver", "done", f"{actual:.1f}s")
        self.emit({"type": "scene_done", "id": sid, "n": n, "actual": actual, "score": score, "revised": revised})

    @staticmethod
    def _shots(raw: Any, secs: float) -> List[Dict[str, Any]]:
        out = []
        for s in (raw if isinstance(raw, list) else [])[:S.MAX_SHOTS]:
            if isinstance(s, dict) and text(s.get("visual"), "", 600):
                out.append({"visual": text(s["visual"], "", 600), "camera": text(s.get("camera"), "", 80), "secs": float(num(s.get("secs"), secs / 3, 0.5, 600)), "asset": "", "image": ""})
        if not out:
            return []
        for s, d in zip(out, rb.scale_secs([x["secs"] for x in out], secs, lo=1.0)):
            s["secs"] = d
        return out

    def _generate(self, p: Dict[str, Any], sid: str, n: int, plan: Dict[str, Any], secs: float, idx: int, only: str = "") -> Dict[str, Any]:
        """Voz, planos (imagem → movimento), música e efeito. `only`: "voice" | "shots" refaz só isso (revisão)."""
        w, h = size_of_aspect(p["aspect"], 1280)
        out: Dict[str, Any] = {"shot_assets": [], "voice": [], "voice_dur": 0.0, "music": None, "sfx": None}
        old = self._scene(sid)
        # voz
        if only in ("", "voice") and plan["narration"].strip():
            prov = self._provider("voice")
            chunks = _chunks(plan["narration"], 700)
            for ci, ch in enumerate(chunks):
                self._check()
                self.emit({"type": "note", "message": f"Cena {n}: voz {ci + 1}/{len(chunks)}"})
                m = prov.voice(ch, voice=p["voice"])
                rec = self._save(m, "audio", f"cena{n}-voz{ci + 1}", sid, ch)
                out["voice"].append(rec)
                out["voice_dur"] += rec["dur"] or max(1.0, len(ch.split()) / rb.WORDS_PER_SECOND)
        # planos
        if only in ("", "shots"):
            img, vid = self._provider("image"), None
            use_video = p["motion"] == "video" and self._media_pid("video") != "demo"
            if use_video:
                vid = self._provider("video")
            for si, shot in enumerate(plan["shots"]):
                self._check()
                self.emit({"type": "note", "message": f"Cena {n}: plano {si + 1}/{len(plan['shots'])}"})
                vp, neg = self._look_for(p, shot["visual"], plan["continuity"])
                seed = proc.seed_of(self.pid, sid, si) % 2 ** 31
                m = img.image(vp, size=f"{w}x{h}", count=1, seed=seed, negative=neg)[0]
                irec = self._save(m, "image", f"cena{n}-plano{si + 1}", sid, vp)
                vrec = None
                if vid is not None:
                    try:
                        mv = vid.video(vp, duration=max(1, int(round(shot["secs"]))), aspect=p["aspect"], image=(m.data, m.mime), seed=seed)
                        vrec = self._save(mv, "video", f"cena{n}-plano{si + 1}-video", sid, vp)
                    except ProviderError as exc:
                        self.warnings.append(f"cena {n}: o modelo de vídeo falhou ({str(exc)[:120]}); usei movimento leve")
                if vrec is None:
                    kb = tools.kenburns(m.data, shot["secs"], (w // 2 * 2, h // 2 * 2), seed)
                    vrec = self._save(Media(kb, "video/mp4"), "video", f"cena{n}-plano{si + 1}", sid, vp)
                out["shot_assets"].append({"asset": vrec["id"], "dur": vrec["dur"] or shot["secs"], "image": irec["id"], "secs": shot["secs"]})
        elif old.get("shots"):
            out["shot_assets"] = [{"asset": s["asset"], "dur": next((a["dur"] for a in p["assets"] if a["id"] == s["asset"]), s["secs"]) or s["secs"], "image": s.get("image", ""), "secs": s["secs"]} for s in old["shots"] if s.get("asset")]
        # música e efeito (uma vez por cena; a revisão só refaz voz/planos)
        if only == "":
            if p["music"]:
                try:
                    m = self._provider("sound").sound(plan["music"], kind="music", duration=int(min(60, max(5, secs))), seed=idx)
                    out["music"] = self._save(m, "audio", f"cena{n}-musica", sid, plan["music"])
                except ProviderError as exc:
                    self.warnings.append(f"cena {n}: sem música ({str(exc)[:120]})")
            if plan["sfx"]:
                try:
                    m = self._provider("sound").sound(plan["sfx"], kind="sfx", duration=4, seed=idx + 7)
                    out["sfx"] = self._save(m, "audio", f"cena{n}-efeito", sid, plan["sfx"])
                except ProviderError as exc:
                    self.warnings.append(f"cena {n}: sem efeito sonoro ({str(exc)[:120]})")
        else:
            prev = self._scene(sid)
            keep = {a["id"]: a for a in p["assets"]}
            out["music"] = next((keep[a] for a in prev.get("assets", []) if a in keep and keep[a]["name"].endswith("-musica")), None)
            out["sfx"] = next((keep[a] for a in prev.get("assets", []) if a in keep and keep[a]["name"].endswith("-efeito")), None)
        for key in ("voice",):
            pass
        self._remember_assets(sid, out, plan)
        return out

    def _remember_assets(self, sid: str, out: Dict[str, Any], plan: Dict[str, Any]) -> None:
        ids = [x["asset"] for x in out["shot_assets"]] + [x["image"] for x in out["shot_assets"] if x["image"]] + [v["id"] for v in out["voice"]]
        ids += [out[k]["id"] for k in ("music", "sfx") if out.get(k)]

        def fn(p: Dict[str, Any], e: Dict[str, Any]) -> None:
            for s in e["scenes"]:
                if s["id"] == sid:
                    s["assets"] = (s["assets"] + [i for i in ids if i not in s["assets"]])[-60:]
                    for sh, g in zip(s["shots"], out["shot_assets"]):
                        sh["asset"], sh["image"] = g["asset"], g["image"]

        self._mut(fn)

    # ------------------------------------------------------------------ revisão
    def _review(self, p: Dict[str, Any], sid: str, n: int, plan: Dict[str, Any], gen: Dict[str, Any], secs: float, brief: Dict[str, Any], idx: int) -> Tuple[Optional[float], List[str], bool]:
        revised, notes, score = False, [], None
        rounds = int(p["revisions"])
        for r in range(rounds + 1):
            fresh = self._project()
            ids = {a["id"] for a in fresh["assets"]}
            ok = all(g["asset"] in ids for g in gen["shot_assets"]) and all(v["id"] in ids for v in gen["voice"])
            checks = rb.scene_checks({"narration": plan["narration"], "shots": plan["shots"]}, secs, ok, gen["voice_dur"])
            obj, fb = self._ask("scene_reviewer", "studio_reviewer", REVIEWER, {"brief": brief, "shots": plan["shots"], "narration": plan["narration"], "secs": secs, "checks": checks, "scene": {"narration": plan["narration"]}}, rb.reviewer)
            score = float(num(obj.get("score"), 7, 0, 10)) if obj.get("score") is not None else None
            issues = [text(x, "", 200) for x in (obj.get("issues") if isinstance(obj.get("issues"), list) else [])][:6]
            approved = bool(obj.get("approved", not issues and not checks)) and not checks
            notes = issues or checks
            if approved or r >= rounds:
                break
            fix = obj.get("fix") if isinstance(obj.get("fix"), dict) else {}
            changed = ""
            if isinstance(fix.get("narration"), str) and fix["narration"].strip() and fix["narration"].strip() != plan["narration"]:
                plan["narration"] = rb.trim_words(text(fix["narration"], "", 3000), rb.word_budget(secs))
                changed = "voice"
            if isinstance(fix.get("shots"), list):
                ns = self._shots(fix["shots"], secs)
                if ns:
                    plan["shots"] = ns
                    changed = "shots" if not changed else ""
            if not changed and "narração longa" in " ".join(checks):
                plan["narration"] = rb.trim_words(plan["narration"], rb.word_budget(secs))
                changed = "voice"
            if not changed:
                break
            revised = True
            self.emit({"type": "note", "message": f"Cena {n}: o Revisor pediu ajustes — refazendo ({changed})"})
            old_ids = [v["id"] for v in gen["voice"]] if changed == "voice" else []
            new = self._generate(p, sid, n, plan, secs, idx, only=changed or "")
            if changed == "voice":
                gen["voice"], gen["voice_dur"] = new["voice"], new["voice_dur"]
                for a in old_ids:
                    self.ss.delete_asset(self.pid, a)
            else:
                gen["shot_assets"] = new["shot_assets"]
            self._mut(lambda pr, e: [s.update(narration=plan["narration"], shots=[dict(x, asset=g["asset"], image=g["image"]) for x, g in zip(plan["shots"], gen["shot_assets"])], revisions=s["revisions"] + 1)
                                     for s in e["scenes"] if s["id"] == sid])
        return score, [] if (score or 0) >= 8 and not notes else notes, revised

    # ------------------------------------------------------------------ entrega
    def _deliver(self, p: Dict[str, Any], sid: str, n: int, plan: Dict[str, Any], gen: Dict[str, Any], secs: float, score: Optional[float], notes: List[str]) -> float:
        fresh = self._project()
        assets = {a["id"]: a for a in fresh["assets"]}
        voice_total = sum((assets.get(v["id"]) or {}).get("dur") or v["dur"] or 0 for v in gen["voice"])
        actual = round(max(secs, voice_total + 0.5 if voice_total else secs), 2)
        cap_size = 50 if p["aspect"] == "9:16" else 42
        gap = 0.15

        def fn(pr: Dict[str, Any], e: Dict[str, Any]) -> None:
            tl = e["timeline"]
            sc = next((s for s in e["scenes"] if s["id"] == sid), None)
            if sc is None:
                return
            start = sc["start"]
            old_slot = (sc["actual"] or sc["secs"]) if sc["status"] == "delivered" else sc["secs"]
            tl["clips"] = [c for c in tl["clips"] if c.get("scene") != sid]
            delta = actual - old_slot
            if abs(delta) > 1e-3:  # a cena ficou mais longa/curta que a reserva: empurra o que vem depois (ripple)
                for c in tl["clips"]:
                    if c["start"] >= start + old_slot - 1e-6:
                        c["start"] = round(max(0.0, c["start"] + delta), 3)
                t = 0.0
                for s in e["scenes"]:
                    s["start"] = round(t, 2)
                    t += (actual if s["id"] == sid else (s["actual"] or s["secs"]))
            tid = {k: next((t["id"] for t in tl["tracks"] if t["kind"] == kind and t["name"] == nm), "") for k, kind, nm in (("v", "video", "V1"), ("a1", "audio", "A1"), ("a2", "audio", "A2"), ("a3", "audio", "A3"), ("t", "text", "T1"))}
            clips = tl["clips"]
            # planos (V1): sequenciais, esticando/encurtando cada um à sua fatia da cena
            slots = rb.scale_secs([g["secs"] for g in gen["shot_assets"]], actual, lo=0.5) if gen["shot_assets"] else []
            t = start
            for i, (g, d) in enumerate(zip(gen["shot_assets"], slots)):
                media = (assets.get(g["asset"]) or {}).get("dur") or g["dur"] or d
                speed = 1.0
                if media and media < d * 0.9:
                    speed = max(0.5, round(media / d, 2))
                clips.append({"id": f"{sid}_v{i}", "track": tid["v"], "asset": g["asset"], "scene": sid, "label": f"C{n}·P{i + 1}", "start": round(t, 3), "dur": round(d, 3), "in": 0, "speed": speed, "mute": True,
                              "fade_in": 0.25 if i == 0 else 0, "fade_out": 0.25 if i == len(slots) - 1 else 0, "fit": "cover"})
                t += d
            # voz (A1)
            t = start + gap
            for i, v in enumerate(gen["voice"]):
                d = (assets.get(v["id"]) or {}).get("dur") or v["dur"] or 3
                clips.append({"id": f"{sid}_a{i}", "track": tid["a1"], "asset": v["id"], "scene": sid, "label": f"Voz {n}", "start": round(t, 3), "dur": round(d, 3), "in": 0, "volume": 1.0})
                t += d
            # música (A2), repetida se o arquivo for mais curto que a cena
            if gen.get("music"):
                md = (assets.get(gen["music"]["id"]) or {}).get("dur") or gen["music"]["dur"] or actual
                t, k = start, 0
                while t < start + actual - 0.05 and k < 40:
                    d = min(md, start + actual - t)
                    clips.append({"id": f"{sid}_m{k}", "track": tid["a2"], "asset": gen["music"]["id"], "scene": sid, "label": f"Música {n}", "start": round(t, 3), "dur": round(d, 3), "in": 0, "volume": 0.25,
                                  "fade_in": 0.6 if k == 0 else 0, "fade_out": 0.8 if t + d >= start + actual - 0.06 else 0})
                    t += d
                    k += 1
            if gen.get("sfx"):
                clips.append({"id": f"{sid}_s0", "track": tid["a3"], "asset": gen["sfx"]["id"], "scene": sid, "label": "Efeito", "start": round(start, 3), "dur": round(min(4.0, actual), 3), "in": 0, "volume": 0.7})
            # legendas (T1): frases da narração distribuídas pelo tempo da voz
            if p["captions"] and plan["narration"].strip() and tid["t"]:
                sents = _split_sentences(plan["narration"])
                span = voice_total or min(actual, len(plan["narration"].split()) / rb.WORDS_PER_SECOND)
                total_chars = sum(len(x) for x in sents) or 1
                t = start + gap
                for i, sx in enumerate(sents):
                    d = max(0.8, span * len(sx) / total_chars)
                    clips.append({"id": f"{sid}_t{i}", "track": tid["t"], "scene": sid, "label": "", "start": round(t, 3), "dur": round(d, 3), "text": sx, "size": cap_size, "color": "#ffffff", "bg": "#000000", "pos": "bottom"})
                    t += d
            sc.update(actual=actual, status="delivered", score=score, notes=notes[:8])
            tl["duration"] = max([c["start"] + c["dur"] for c in clips] + [0])
            e["status"] = "ready" if all(s["status"] == "delivered" for s in e["scenes"]) else "generating"

        self._mut(fn)
        return actual

    # ------------------------------------------------------------------ fim do episódio
    def _finish_episode(self, ep: Dict[str, Any]) -> None:
        p = self._project()
        self._step("recap", "running")
        obj, fb = self._ask("recap", "studio_recap", RECAP, {"title": ep["title"], "scenes": [{"title": s["title"], "summary": s["summary"]} for s in ep["scenes"]], "language": p["language"]}, rb.recap)

        def fn(pr: Dict[str, Any], e: Dict[str, Any]) -> None:
            e["recap"] = text(obj.get("recap"), "", 800) or rb.recap({"scenes": e["scenes"]})["recap"]
            e["status"] = "ready"
            self._merge_bible(pr, obj.get("bible_update"))

        self._mut(fn)
        self._step("recap", "warn" if fb else "done")


def _chunks(src: str, limit: int) -> List[str]:
    parts, cur = [], ""
    for s in _split_sentences(src):
        if cur and len(cur) + len(s) + 1 > limit:
            parts.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        parts.append(cur)
    return parts or [src[:limit]]


def _split_sentences(src: str) -> List[str]:
    parts = [x.strip() for x in re.split(r"(?<=[.!?…])\s+|\n+", src) if x.strip()]
    out: List[str] = []
    for x in parts:  # frase gigante: quebra em pedaços legíveis para legenda/voz
        while len(x) > 120:
            cut = max(x.rfind(",", 0, 110), x.rfind(" ", 0, 110))
            cut = cut if cut > 40 else 110
            out.append(x[:cut + 1].strip())
            x = x[cut + 1:].strip()
        if x:
            out.append(x)
    return out
