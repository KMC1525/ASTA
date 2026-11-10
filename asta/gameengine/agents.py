"""A IA do Game Engine: equipes pequenas de agentes (planejar → fazer → conferir) para cada aba, todas com **fallback determinístico** — o Game Engine entrega mesmo sem IA ou com resposta inválida.

  • `generate_game`  (Main)    — Planejador → Projetista de cena → Redator → Revisor: do pedido (+anexos, +busca na web) a um jogo completo; ou, num jogo existente, edições por operações validadas.
  • `edit_code`      (Code)    — Planejador de código → Programador → Revisor (confere a sintaxe com o `node`, se houver); alternativa: o modo Code do ASTA.
  • `make_asset`     (Assets)  — Diretor de arte → modelo de imagem (ou desenho vetorial procedural); edição de região com máscara.
  • `make_sound`     (Sound)   — Diretor de som → modelo de áudio/voz (ou síntese procedural).
  • `write_script`   (Scripts) — Escritor: gerar documentos, melhorar/expandir/reescrever um trecho selecionado.
  • `make_map`       (Map)     — Projetista de fases → gerador procedural (2D/3D), região regenerada, objetos extras.
  • `plan_publish`   (Publish) — Publicador: textos de loja, notas de versão, ajustes de exportação.

A IA escreve **dados** (JSON validado em `schema.py`), nunca código — exceto na aba Code, onde os arquivos são escritos de propósito e só rodam dentro do iframe isolado do jogo.
Quantos agentes (1·4·8·12·16) e o esforço (Low…Omni) vêm de `asta/team.py`, como em todas as seções."""
from __future__ import annotations

import base64
import copy
import json
import re
import shutil
import subprocess
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import team as teamlib
from ..agents.llm import call_json
from ..agents.prompts import POLICY_FREE, POLICY_SFW
from ..agents.runner import Cancelled
from ..providers import ProviderError, resolve_provider
from ..util import clamp, slugify, text
from . import art, audio, maps as gmaps, schema as S, templates as tpl
from .manager import EngineError

PROMPTS = Path(__file__).parent / "prompts"
STEP_TOKENS = 2600


@lru_cache(maxsize=32)
def prompt(name: str) -> str:
    try:
        return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def prompt_names() -> List[str]:
    return sorted(p.stem for p in PROMPTS.glob("*.md"))


def normalize_config(raw: Any) -> Dict[str, Any]:
    c = raw if isinstance(raw, dict) else {}
    return {"agents": teamlib.normalize_agents(c.get("agents", 1)), "effort": teamlib.normalize_effort(c.get("effort", "high")),
            "kind": c.get("kind") if c.get("kind") in S.KINDS else "2d", "content": "sfw" if c.get("content") == "sfw" else ("free" if c.get("content") == "free" else ""),
            "web": c.get("web") is True, "undo_keep": int(clamp(float(c.get("undo_keep") or 25), 5, 100)) if isinstance(c.get("undo_keep"), (int, float)) else 25}


ENGINE_API = """GE (global) — engine API for scripts/*.js (loaded after the engine, before the game starts):
GE.behavior(name, {init(n, p, s), update(n, dt, p, s)})   register a behavior; n = node (n.x, n.y, n.z in 3D, n.w, n.h, n.name, n.tags, n.alive), p = behavior params from the scene, s = private state object.
Use it in a scene node:  "behaviors": [{"type": "<name>", ...params}]  (params are free-form for custom behaviors).
GE.input.down('left'|'right'|'up'|'down'|'jump'|'action'|'fire'|'run'), GE.input.hit(key), GE.input.axis('left','right')
GE.state {score, hp, max_hp, coins, total, time, level, keys, flags}; GE.addScore(n); GE.damage(n); GE.heal(n); GE.win(msg); GE.lose(msg); GE.toast(text); GE.say([{speaker,text}])
GE.find(name) -> node; GE.byTag(tag) -> nodes; GE.add(parent, nodeSpec) -> node; GE.remove(node); GE.dist(a, b); GE.overlap(a, b) (2D); GE.sfx('coin'|'jump'|'hit'|'win'|'lose'|'powerup'|'shoot'|'select'|'door'); GE.playSound(key)
GE.R.cam (2D camera {x,y,zoom,shake}); GE.R.pop(x, y, text, color); GE.R.player() (2D). GE.rng(seed), GE.clamp, GE.lerp.
Scenes: scenes/<name>.scene.json {name, kind, settings, rules, root:{type,name,children}}; maps: maps/<name>.map.json; dialogues: data/dialogues.json {id: [{speaker,text}]}."""


def _unpack(res: Any) -> Any:
    if isinstance(res, tuple) and len(res) == 2:
        return res
    return res, {"demo": getattr(res, "id", "") == "demo", "id": getattr(res, "id", ""), "model": getattr(res, "model", "")}


def engine_status(store: Any) -> Dict[str, Any]:
    """O que a tela precisa saber: IA de texto pronta?, mídia (imagem/som/voz) pronta?, node disponível?, equipe padrão."""
    from ..canvas import media as cm

    settings = store.get_settings()
    out: Dict[str, Any] = {"config": normalize_config(settings.get("engine")), "text": {"ai": False, "label": "Demo"}, "media": {}, "tools": {"node": bool(shutil.which("node"))}}
    try:
        provider, info = _unpack(resolve_provider(settings, "generation", store.models_dir))
        out["text"] = {"ai": not (info.get("demo") or getattr(provider, "id", "") == "demo"), "label": info.get("label") or info.get("id") or "", "model": info.get("model", "")}
    except Exception as exc:  # noqa: BLE001
        out["text"] = {"ai": False, "label": "", "error": str(exc)[:160]}
    for cap in ("image", "sound", "voice"):
        try:
            pid = cm.pick_provider(settings, cap)
            out["media"][cap] = {"provider": pid, "demo": pid == "demo", "label": cm.MEDIA_PRESETS.get(pid, {}).get("label", pid)}
        except Exception as exc:  # noqa: BLE001
            out["media"][cap] = {"provider": "", "demo": True, "error": str(exc)[:160]}
    return out


class EngineAI:
    """Uma execução da IA do Game Engine: guarda o provedor, a equipe e o registro (log) de cada agente; emite eventos para a tela."""

    def __init__(self, store: Any, mgr: Any, opts: Dict[str, Any], job: Any):
        self.store, self.mgr, self.opts, self.job = store, mgr, opts or {}, job
        settings = store.get_settings()
        self.settings = settings
        self.cfg = normalize_config(settings.get("engine"))
        self.team = teamlib.from_config(self.cfg, self.opts)
        self.content = self.opts.get("content") or self.cfg["content"] or (settings.get("generation") or {}).get("content", "free")
        self.provider: Any = None
        self.error = ""
        self.pinfo: Dict[str, Any] = {}
        try:
            provider, info = _unpack(resolve_provider(settings, "generation", store.models_dir))
            self.pinfo = info
            if info.get("demo") or getattr(provider, "id", "") == "demo":
                self.error = info.get("reason") or "Nenhuma IA configurada: usei as regras automáticas do Game Engine."
            else:
                self.provider = provider
                teamlib.apply_thinking(provider, self.team, info.get("id", ""), info.get("model", ""))
        except (ProviderError, Exception) as exc:  # noqa: BLE001
            self.error = str(exc)[:200]
        self.log: List[Dict[str, Any]] = []
        self.warnings: List[str] = []

    @property
    def live(self) -> bool:
        return self.provider is not None

    def emit(self, ev: Dict[str, Any]) -> None:
        if self.job is not None:
            self.job.emit(ev)

    def check(self) -> None:
        if self.job is not None and self.job.cancelled:
            raise Cancelled()

    def note(self, msg: str) -> None:
        self.emit({"type": "note", "message": msg})

    def start(self, steps: List[Tuple[str, str]]) -> None:
        self.emit({"type": "start", "steps": [{"id": a, "label": b} for a, b in steps], "ai": self.live, "team": self.team.public(), "warning": "" if self.live else (self.error or "Sem IA: usei as regras automáticas do Game Engine.")})

    # ---------------------------------------------------------------- uma chamada de agente
    def _ask(self, role: str, instruction: str, payload: Dict[str, Any], tokens: int = STEP_TOKENS, images: Optional[List[dict]] = None) -> Optional[Dict[str, Any]]:
        system = prompt("core") + "\n\n" + prompt(role) + "\n\n" + (POLICY_SFW if self.content == "sfw" else POLICY_FREE)
        obj, _ = call_json(self.provider, system, instruction + "\nOutput JSON: see the format in your role description.", payload, images=images, max_tokens=int(tokens * self.team.tokens_mult), temperature=0.5, attempts=2,
                           cancelled=lambda: bool(self.job is not None and self.job.cancelled))
        return obj

    def step(self, sid: str, role: str, label: str, payload: Dict[str, Any], validate: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]], fallback: Callable[[], Dict[str, Any]], *,
             creative: bool = True, critique: bool = False, tokens: int = STEP_TOKENS, images: Optional[List[dict]] = None) -> Dict[str, Any]:
        """Roda um agente (ou a mesa de N agentes) e devolve o resultado **validado**; se a IA falha ou devolve lixo, vale o `fallback`."""
        self.check()
        started = time.time()
        note = ""
        out: Optional[Dict[str, Any]] = None
        self.emit({"type": "step", "id": sid, "label": label, "status": "running"})
        if self.live:
            instruction = f"Do your role for this input ({label})."
            ask = lambda ins, pl: self._ask(role, ins, pl, tokens, images)   # noqa: E731
            try:
                raw = teamlib.ensemble_json(ask, self.team, instruction, payload, cancelled=lambda: bool(self.job is not None and self.job.cancelled), fatal=(Cancelled,)) if creative and self.team.multi else ask(instruction, payload)
                if raw and critique and self.team.critique:
                    raw = teamlib.critique_json(ask, instruction, payload, raw)
                out = validate(raw) if isinstance(raw, dict) else None
                if out is None:
                    note = "resposta inválida da IA"
            except Cancelled:
                raise
            except ProviderError as exc:
                if str(exc) == "cancelado":
                    raise Cancelled() from None
                note = str(exc)[:160]
            except ValueError as exc:
                note = str(exc)[:160]
        else:
            note = self.error or "sem IA"
        status = "ok"
        if out is None:
            out = fallback()
            status = "fallback"
        self.log.append({"agent": role, "label": label, "status": status, "note": note, "ms": int((time.time() - started) * 1000)})
        self.emit({"type": "step", "id": sid, "label": label, "status": "done" if status == "ok" else "warn", "note": note})
        return out

    def report(self) -> Dict[str, Any]:
        return {"ai": self.live and any(s["status"] == "ok" for s in self.log), "agents": self.log, "team": self.team.public(), "warnings": self.warnings,
                "warning": "" if self.live else (self.error or "Sem IA: usei as regras automáticas do Game Engine.")}

    def done(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(result)
        result["report"] = self.report()
        self.emit({"type": "result", "data": result})
        return result

    # ---------------------------------------------------------------- contexto: anexos e web
    def context(self, prompt_text: str) -> Dict[str, Any]:
        from .. import attachments as att, voice

        ids = self.opts.get("attachment_ids") or []
        digest, images = "", []
        if ids:
            self.emit({"type": "step", "id": "attachments", "label": "Anexos", "status": "running"})
            analyzed = []
            transcribe = voice.transcriber(self.settings)
            for meta in self.store.get_uploads(ids):
                self.check()
                try:
                    analyzed.append(att.analyze(Path(meta["path"]), meta["name"], meta.get("mime", ""), transcribe=transcribe))
                except Exception as exc:  # noqa: BLE001  (um anexo ilegível não derruba a geração)
                    self.warnings.append(f"anexo «{meta.get('name', '?')}»: {str(exc)[:100]}")
            digest = att.build_digest(analyzed, max_total=30000)
            images = att.collect_images(analyzed)
            self.emit({"type": "step", "id": "attachments", "label": "Anexos", "status": "done", "note": f"{len(analyzed)} arquivo(s)"})
        web = ""
        if self.opts.get("web") and prompt_text:
            self.emit({"type": "step", "id": "web", "label": "Busca na web", "status": "running"})
            try:
                from .. import websearch

                found = websearch.gather(websearch.heuristic_query(prompt_text) or prompt_text[:200], self.settings, ui_lang=(self.settings.get("language") or "auto"))
                web = found.get("text", "")[:9000]
                self.emit({"type": "sources", "sources": websearch.public_sources(found.get("sources", []))})
                self.emit({"type": "step", "id": "web", "label": "Busca na web", "status": "done", "note": f"{len(found.get('sources', []))} fonte(s)"})
            except Exception as exc:  # noqa: BLE001
                self.warnings.append("busca na web: " + str(exc)[:120])
                self.emit({"type": "step", "id": "web", "label": "Busca na web", "status": "warn", "note": str(exc)[:120]})
        return {"digest": digest, "images": images, "web": web}

    def lang_of(self, project: Dict[str, Any], prompt_text: str) -> str:
        l = text(self.opts.get("language"), "", 5) or project.get("language") or tpl.detect_lang(prompt_text)
        return l if l in ("pt", "en") else "pt"

    # ================================================================ MAIN: gerar / editar o jogo
    def generate_game(self, pid: str) -> Dict[str, Any]:
        mgr = self.mgr
        meta = mgr.meta(pid)
        prompt_text = text(self.opts.get("prompt"), "", 20000)
        has_game = bool(mgr.list_scenes(pid))
        mode = self.opts.get("mode") or ("edit" if has_game else "new")
        if mode == "edit" and not has_game:
            mode = "new"
        steps = [("plan", "Planejador"), ("design", "Projetista de cena"), ("write", "Redator"), ("review", "Revisor"), ("save", "Salvar")]
        self.start(steps)
        ctx = self.context(prompt_text)
        if mode == "edit":
            return self._edit_game(pid, meta, prompt_text, ctx)
        lang = self.lang_of(meta, prompt_text)
        # ---------- 1. Planejador
        cat = {"genres": {k: {"kinds": v["kinds"], "label": v["label"]} for k, v in S.GENRES.items()}, "themes": list(S.THEMES)}
        want_kind = self.opts.get("kind") if self.opts.get("kind") in S.KINDS else ""
        payload = {"request": prompt_text[:6000], "attachments_digest": ctx["digest"][:12000], "web_notes": ctx["web"][:5000], "catalog": cat, "user_choices": {k: self.opts.get(k) for k in ("kind", "genre", "theme", "length") if self.opts.get(k)}}
        fb_plan = lambda: self._plan_rules(prompt_text, lang)   # noqa: E731
        plan = self.step("plan", "game_planner", "Planejador", payload, lambda raw: self._valid_plan(raw, prompt_text, lang), fb_plan, critique=True, images=ctx["images"] or None)
        plan = self._apply_choices(plan, prompt_text)
        self.emit({"type": "plan", "plan": {k: plan[k] for k in ("title", "kind", "genre", "theme", "length", "pitch") if k in plan}})
        # ---------- 2. Gerador (determinístico) + Projetista de cena (extras)
        build = tpl.build(prompt_text or plan["pitch"], plan["kind"], plan["genre"], plan["theme"], plan["length"], int(plan.get("seed") or 0), plan["title"], plan["language"], plan.get("enemies"), plan.get("coins"), plan.get("hp"), plan.get("music_mood", ""))
        sc_main = build["scenes"]["main"]
        d_payload = {"plan": plan, "catalog": self._mini_catalog(sc_main["kind"]), "scene": self._compact(sc_main), "ops_mode": False}
        design = self.step("design", "game_designer", "Projetista de cena", d_payload, lambda raw: self._valid_design(raw, sc_main["kind"]), lambda: {"summary": "", "extras": [], "settings": {}, "rules": {}}, critique=False)
        if design.get("extras") or design.get("settings") or design.get("rules"):
            sc = copy.deepcopy(sc_main)
            sc["root"]["children"] = list(sc["root"].get("children", [])) + design["extras"]
            sc["settings"] = dict(sc.get("settings", {}), **design.get("settings", {}))
            if design.get("rules", {}).get("win") in S.RULE_WINS:
                sc["rules"] = {"win": design["rules"]["win"]}
            try:
                build["scenes"]["main"] = S.norm_scene(sc, sc["kind"], "main")
            except ValueError as exc:
                self.warnings.append("designer: " + str(exc)[:100])
        # ---------- 3. Redator
        w_payload = {"plan": plan, "request": prompt_text[:3000], "attachments_digest": ctx["digest"][:6000], "language": plan["language"]}
        writing = self.step("write", "game_writer", "Redator", w_payload, self._valid_writing, lambda: {"intro": "", "dialogues": {}, "win": "", "lose": "", "gdd_notes": ""})
        if writing.get("dialogues"):
            build["dialogues"] = dict(build["dialogues"], **writing["dialogues"])
            build["docs"]["dialogues.md"] = tpl.dialogues_md(build["dialogues"])
        if writing.get("gdd_notes"):
            build["docs"]["gdd.md"] += "\n## " + ("Notas do redator" if plan["language"] == "pt" else "Writer notes") + "\n\n" + writing["gdd_notes"] + "\n"
        if writing.get("intro"):
            build["meta"]["description"] = writing["intro"]
        # ---------- 4. Revisor (checagens do programa + resumo)
        problems = self.check_game(build["scenes"], build["maps"], build["meta"]["kind"])
        rounds = self.team.revisions(1)
        for _ in range(rounds):
            if not problems:
                break
            self.note("Corrigindo: " + "; ".join(problems[:3]))
            fix = tpl.build(prompt_text or plan["pitch"], plan["kind"], plan["genre"], plan["theme"], plan["length"], int(plan.get("seed") or 0) + 1, plan["title"], plan["language"], plan.get("enemies"), plan.get("coins"), plan.get("hp"))
            build["scenes"], build["maps"] = fix["scenes"], fix["maps"]
            problems = self.check_game(build["scenes"], build["maps"], build["meta"]["kind"])
        review = self.step("review", "game_reviewer", "Revisor", {"problems": problems, "game": self._game_summary(build), "request": prompt_text[:1500]}, self._valid_review,
                           lambda: {"approved": not problems, "summary": self._fallback_summary(build, lang), "issues": []}, creative=False)
        if problems:
            self.warnings += problems
        # ---------- 5. Salvar (com instantâneo para desfazer)
        self.emit({"type": "step", "id": "save", "label": "Salvar", "status": "running"})
        mgr.snapshot(pid, "antes de gerar: " + prompt_text[:60])
        build["meta"]["name"] = plan["title"]
        mgr.apply_build(pid, build, replace=True)
        mgr.log(pid, "generate", prompt_text[:200] or plan["title"])
        self.emit({"type": "step", "id": "save", "label": "Salvar", "status": "done"})
        return self.done({"project": mgr.meta(pid), "summary": review.get("summary") or self._fallback_summary(build, lang), "plan": plan, "problems": problems, "mode": "new"})

    # ---- planejamento
    def _plan_rules(self, prompt_text: str, lang: str) -> Dict[str, Any]:
        kind, genre, theme = tpl.detect(prompt_text, self.opts.get("kind", ""), self.opts.get("genre", ""), self.opts.get("theme", ""))
        return {"title": tpl.make_title(prompt_text, genre, theme, lang), "pitch": (prompt_text.strip()[:200] or S.GENRES[genre]["hint"]), "kind": kind, "genre": genre, "theme": theme, "length": self.opts.get("length") or "medium",
                "language": lang, "difficulty": "normal", "enemies": 1.0, "coins": 1.0, "hp": 3, "mechanics": [], "characters": [], "tone": "", "art_style": "", "music_mood": ""}

    def _valid_plan(self, raw: Dict[str, Any], prompt_text: str, lang: str) -> Optional[Dict[str, Any]]:
        base = self._plan_rules(prompt_text, lang)
        kind = raw.get("kind") if raw.get("kind") in S.KINDS else base["kind"]
        genre = raw.get("genre") if raw.get("genre") in S.GENRES and kind in S.GENRES[raw.get("genre")]["kinds"] else S.DEFAULT_GENRE[kind]
        theme = raw.get("theme") if raw.get("theme") in S.THEMES else base["theme"]
        diff = raw.get("difficulty") if raw.get("difficulty") in ("easy", "normal", "hard") else "normal"
        try:
            enemies = clamp(float(raw.get("enemies", 1.0)), 0.2, 2.5)
            coins = clamp(float(raw.get("coins", 1.0)), 0.2, 2.5)
            hp = int(clamp(float(raw.get("hp", 3)), 1, 9))
        except (TypeError, ValueError):
            enemies, coins, hp = 1.0, 1.0, 3
        out = {"title": text(raw.get("title"), base["title"], 60), "pitch": text(raw.get("pitch"), base["pitch"], 400), "kind": kind, "genre": genre, "theme": theme,
               "length": raw.get("length") if raw.get("length") in gmaps.SIZES else base["length"], "language": raw.get("language") if raw.get("language") in ("pt", "en") else lang, "difficulty": diff,
               "enemies": round(enemies * (0.7 if diff == "easy" else 1.3 if diff == "hard" else 1.0), 2), "coins": round(coins, 2), "hp": hp + (1 if diff == "easy" else 0),
               "mechanics": [text(x, "", 80) for x in (raw.get("mechanics") if isinstance(raw.get("mechanics"), list) else [])][:8],
               "characters": [{"name": text(c.get("name"), "", 40), "role": text(c.get("role"), "npc", 12), "description": text(c.get("description"), "", 160)} for c in (raw.get("characters") if isinstance(raw.get("characters"), list) else []) if isinstance(c, dict)][:8],
               "tone": text(raw.get("tone"), "", 60), "art_style": text(raw.get("art_style"), "", 60), "music_mood": raw.get("music_mood") if raw.get("music_mood") in audio.MOODS else ""}
        return out

    def _apply_choices(self, plan: Dict[str, Any], prompt_text: str) -> Dict[str, Any]:
        """O que o usuário escolheu nos controles da tela vence o que a IA sugeriu."""
        o = self.opts
        if o.get("kind") in S.KINDS:
            plan["kind"] = o["kind"]
            if plan["genre"] not in S.GENRES or plan["kind"] not in S.GENRES[plan["genre"]]["kinds"]:
                plan["genre"] = S.DEFAULT_GENRE[plan["kind"]]
        if o.get("genre") in S.GENRES and plan["kind"] in S.GENRES[o["genre"]]["kinds"]:
            plan["genre"] = o["genre"]
        if o.get("theme") in S.THEMES:
            plan["theme"] = o["theme"]
        if o.get("length") in gmaps.SIZES:
            plan["length"] = o["length"]
        if o.get("language") in ("pt", "en"):
            plan["language"] = o["language"]
        return plan

    # ---- projetista
    def _mini_catalog(self, kind: str) -> Dict[str, Any]:
        dim = S.KINDS[kind]["dim"]
        return {"node_types": {k: {"props": [p["k"] for p in v["props"]]} for k, v in S.NODE_TYPES.items() if v["dim"] in (dim, "any")},
                "behaviors": {k: [p["k"] for p in v["params"]] for k, v in S.BEHAVIORS.items() if dim in v["dims"]}, "themes": list(S.THEMES), "biomes": list(S.BIOMES)}

    def _compact(self, scene: Dict[str, Any], limit: int = 160) -> List[str]:
        out = []
        for n in S.walk(scene["root"]):
            if len(out) >= limit:
                out.append("…")
                break
            extra = ", ".join(f"{k}={n[k]}" for k in ("x", "y", "z", "text", "map", "shape", "color") if k in n)
            b = ",".join(x["type"] for x in n.get("behaviors", []))
            out.append(f"{n['id']}|{n['type']}|{n.get('name', '')}|{extra}" + (f"|b:{b}" if b else ""))
        return out

    def _valid_design(self, raw: Dict[str, Any], kind: str) -> Optional[Dict[str, Any]]:
        dim = S.KINDS[kind]["dim"]
        extras = []
        seen: set = set()
        counter = [0]
        for e in (raw.get("extras") if isinstance(raw.get("extras"), list) else [])[:20]:
            n = S.norm_node(e, dim, seen, counter)
            if n and n["type"] not in ("Terrain3D", "TileMap", "Camera2D", "Camera3D", "Sky3D"):
                n["id"] = "x" + n["id"].lstrip("n")
                extras.append(n)
        return {"summary": text(raw.get("summary"), "", 300), "extras": extras, "settings": S.norm_settings(raw.get("settings"), kind), "rules": raw.get("rules") if isinstance(raw.get("rules"), dict) else {}}

    def _valid_writing(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        d_out: Dict[str, List[Dict[str, str]]] = {}
        for k, lines in (raw.get("dialogues") if isinstance(raw.get("dialogues"), dict) else {}).items():
            if not isinstance(lines, list) or not re.match(r"^[\w-]{1,30}$", str(k)):
                continue
            ls = [{"speaker": text(l.get("speaker"), "", 40), "text": text(l.get("text"), "", 200)} for l in lines if isinstance(l, dict) and text(l.get("text"), "")][:8]
            if ls:
                d_out[str(k)] = ls
        if d_out and "guia" in d_out and "npc1" not in d_out:
            d_out["npc1"] = d_out["guia"]
        if not d_out and not raw.get("intro"):
            return None
        return {"intro": text(raw.get("intro"), "", 240), "dialogues": d_out, "win": text(raw.get("win"), "", 80), "lose": text(raw.get("lose"), "", 80), "gdd_notes": text(raw.get("gdd_notes"), "", 1200)}

    def _valid_review(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if "summary" not in raw and "approved" not in raw:
            return None
        return {"approved": raw.get("approved") is not False, "summary": text(raw.get("summary"), "", 400), "issues": [i for i in (raw.get("issues") if isinstance(raw.get("issues"), list) else []) if isinstance(i, dict)][:6]}

    def _game_summary(self, build: Dict[str, Any]) -> Dict[str, Any]:
        m = build["meta"]
        objs: Dict[str, int] = {}
        for mp in build["maps"].values():
            for o in mp.get("objects", []):
                objs[o["type"]] = objs.get(o["type"], 0) + 1
        return {"title": m["name"], "kind": m["kind"], "genre": m["genre"], "theme": m["theme"], "scenes": list(build["scenes"]), "objects": objs, "hud": [n["name"] for n in S.walk(build["scenes"]["main"]["root"]) if n["type"].startswith("UI")]}

    def _fallback_summary(self, build: Dict[str, Any], lang: str) -> str:
        m = build["meta"]
        n = sum(len(mp.get("objects", [])) for mp in build["maps"].values())
        return (f"Criei «{m['name']}» ({S.KINDS[m['kind']]['label']} · {S.GENRES[m['genre']]['label']} · tema {m['theme']}) com {len(build['scenes'])} cena(s) e {n} objetos. Aperte ▶ para jogar." if lang == "pt"
                else f"Built “{m['name']}” ({S.KINDS[m['kind']]['label']} · {S.GENRES[m['genre']]['label']} · {m['theme']} theme) with {len(build['scenes'])} scene(s) and {n} objects. Press ▶ to play.")

    # ---- conferências objetivas do jogo
    def check_game(self, scenes: Dict[str, Dict[str, Any]], maps_: Dict[str, Dict[str, Any]], kind: str) -> List[str]:
        """O que o programa consegue provar sozinho: jogo jogável (jogador, objetivo, mapas existentes, vida)."""
        p: List[str] = []
        if not scenes:
            return ["o jogo não tem cenas"]
        for name, sc in scenes.items():
            nodes = list(S.walk(sc["root"]))
            if S.count_nodes(sc["root"]) > S.MAX_NODES:
                p.append(f"cena {name}: nós demais")
            for n in nodes:
                if n["type"] in ("TileMap", "Terrain3D"):
                    mp = maps_.get(n.get("map", ""))
                    if not mp:
                        p.append(f"cena {name}: mapa «{n.get('map', '')}» não existe")
                    elif not any(o["type"] == "player" for o in mp.get("objects", [])):
                        p.append(f"mapa {n.get('map')}: sem ponto de partida do jogador")
                    elif sc.get("rules", {}).get("win") == "reach_goal" and not any(o["type"] in ("goal", "portal") for o in mp.get("objects", [])):
                        p.append(f"mapa {n.get('map')}: sem objetivo para vencer")
            has_player_node = any("player" in (n.get("tags") or []) for n in nodes)
            has_map = any(n["type"] in ("TileMap", "Terrain3D") for n in nodes)
            if not has_player_node and not has_map:
                p.append(f"cena {name}: sem jogador")
        return p

    # ---- edição de um jogo existente (operações validadas)
    def _edit_game(self, pid: str, meta: Dict[str, Any], prompt_text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        mgr = self.mgr
        lang = self.lang_of(meta, prompt_text)
        scenes = {n: mgr.get_scene(pid, n) for n in mgr.list_scenes(pid)}
        maps_ = {m["path"]: mgr.get_map(pid, m["path"]) for m in mgr.list_maps(pid)}
        kind = meta["kind"]
        cur = {"title": meta["name"], "kind": kind, "genre": meta["genre"], "theme": meta["theme"], "scenes": {n: self._compact(s) for n, s in list(scenes.items())[:4]}}
        plan = self.step("plan", "game_planner", "Planejador", {"request": prompt_text[:5000], "current": cur, "attachments_digest": ctx["digest"][:8000], "web_notes": ctx["web"][:4000]},
                         lambda raw: self._valid_plan(dict(raw, kind=kind), prompt_text, lang), lambda: self._plan_rules(prompt_text, lang), critique=True, images=ctx["images"] or None)
        done_rules, ch = tpl.apply_edit(prompt_text, scenes, maps_, meta, meta.get("settings", {}))
        design = self.step("design", "game_designer", "Projetista de cena", {"plan": plan, "request": prompt_text[:4000], "catalog": self._mini_catalog(kind), "ops_mode": True, "scenes": {n: self._compact(s) for n, s in scenes.items()}},
                           lambda raw: self._valid_ops(raw, scenes, kind), lambda: {"summary": "", "ops": [], "map": {}}, critique=False)
        new_scenes = copy.deepcopy(scenes)
        new_scenes.update({k: v for k, v in ch["scenes"].items()})
        applied = self._apply_ops(new_scenes, design.get("ops", []), kind)
        new_maps = dict(maps_)
        new_maps.update(ch["maps"])
        if design.get("map"):
            new_maps, notes = self._apply_map_changes(new_maps, design["map"])
            applied += notes
        problems = self.check_game(new_scenes, new_maps, kind)
        if problems:   # edição que quebra o jogo é descartada
            self.warnings += problems
            new_scenes, new_maps, applied = scenes, maps_, []
        writing = self.step("write", "game_writer", "Redator", {"plan": plan, "request": prompt_text[:2000], "language": lang}, self._valid_writing, lambda: {"intro": "", "dialogues": {}, "win": "", "lose": "", "gdd_notes": ""})
        did = done_rules + applied
        review = self.step("review", "game_reviewer", "Revisor", {"problems": problems, "changes": did, "request": prompt_text[:1500]}, self._valid_review,
                           lambda: {"approved": not problems, "summary": ("Feito: " + "; ".join(did[:8]) + ".") if did else ("Não encontrei o que mudar com regras simples. Configure uma IA em Configuração → Provedores para pedidos livres." if lang == "pt" else "I found nothing to change with simple rules. Set up an AI provider for free-form requests."), "issues": []}, creative=False)
        self.emit({"type": "step", "id": "save", "label": "Salvar", "status": "running"})
        if did or writing.get("dialogues"):
            mgr.snapshot(pid, "antes de editar: " + prompt_text[:60])
            build: Dict[str, Any] = {"scenes": new_scenes, "maps": new_maps, "meta": ch["meta"], "settings": ch["settings"], "images": ch["images"], "sounds": ch["sounds"]}
            if writing.get("dialogues"):
                old = json.loads(json.dumps(mgr.bundle(pid).get("dialogues", {})))
                old.update(writing["dialogues"])
                build["dialogues"] = old
            mgr.apply_build(pid, build, replace=False)
            mgr.log(pid, "edit", prompt_text[:200])
        self.emit({"type": "step", "id": "save", "label": "Salvar", "status": "done"})
        return self.done({"project": mgr.meta(pid), "summary": review.get("summary") or "", "changes": did, "problems": problems, "mode": "edit"})

    def _valid_ops(self, raw: Dict[str, Any], scenes: Dict[str, Any], kind: str) -> Optional[Dict[str, Any]]:
        ops = []
        for o in (raw.get("ops") if isinstance(raw.get("ops"), list) else [])[:40]:
            if isinstance(o, dict) and o.get("op") in ("add", "update", "remove", "add_behavior", "scene_settings") and (o.get("scene") in scenes or not o.get("scene")):
                ops.append(o)
        mp = raw.get("map") if isinstance(raw.get("map"), dict) else {}
        if not ops and not mp:
            return None
        return {"summary": text(raw.get("summary"), "", 300), "ops": ops, "map": {"theme": mp.get("theme") if mp.get("theme") in S.THEMES else "", "enemies": mp.get("enemies") if mp.get("enemies") in ("more", "less") else "same", "coins": mp.get("coins") if mp.get("coins") in ("more", "less") else "same"}}

    def _apply_ops(self, scenes: Dict[str, Dict[str, Any]], ops: List[Dict[str, Any]], kind: str) -> List[str]:
        dim = S.KINDS[kind]["dim"]
        done: List[str] = []
        for o in ops:
            sc = scenes.get(o.get("scene") or next(iter(scenes), ""))
            if not sc:
                continue
            nodes = {n["id"]: n for n in S.walk(sc["root"])}
            try:
                if o["op"] == "add":
                    parent = nodes.get(o.get("parent") or "") or sc["root"]
                    new = S.norm_node(o.get("node"), dim, set(nodes), [len(nodes)])
                    if new and new["type"] not in ("Terrain3D", "TileMap") and S.count_nodes(sc["root"]) < S.MAX_NODES - 50:
                        parent.setdefault("children", []).append(new)
                        done.append(f"adicionou {new['name']}")
                elif o["op"] == "update" and o.get("id") in nodes and isinstance(o.get("props"), dict):
                    n = nodes[o["id"]]
                    merged = dict(n, **{k: v for k, v in o["props"].items() if k not in ("id", "type", "children")})
                    fixed = S.norm_node(dict(merged, children=[]), dim, set(), [0])
                    if fixed:
                        for k in list(n):
                            if k not in ("id", "type", "children"):
                                n.pop(k)
                        n.update({k: v for k, v in fixed.items() if k not in ("id", "type", "children")})
                        done.append(f"alterou {n.get('name', n['id'])}")
                elif o["op"] == "remove" and o.get("id") in nodes and nodes[o["id"]] is not sc["root"]:
                    for n in nodes.values():
                        n["children"] = [c for c in n.get("children", []) if c["id"] != o["id"]]
                        if not n["children"]:
                            n.pop("children")
                    done.append(f"removeu {o['id']}")
                elif o["op"] == "add_behavior" and o.get("id") in nodes:
                    b = S.norm_behavior(o.get("behavior"), dim)
                    if b and dim in S.BEHAVIORS[b["type"]]["dims"]:
                        nodes[o["id"]].setdefault("behaviors", []).append(b)
                        done.append(f"comportamento {b['type']}")
                elif o["op"] == "scene_settings" and isinstance(o.get("settings"), dict):
                    sc["settings"] = dict(sc.get("settings", {}), **S.norm_settings(o["settings"], kind))
                    done.append("configurações da cena")
            except (KeyError, TypeError, ValueError):
                continue
        for name, sc in list(scenes.items()):
            try:
                scenes[name] = S.norm_scene(sc, kind, name)
            except ValueError:
                pass
        return done

    def _apply_map_changes(self, maps_: Dict[str, Dict[str, Any]], mp: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
        import random
        out = {}
        notes: List[str] = []
        for path, m in maps_.items():
            m = copy.deepcopy(m)
            rnd = random.Random(len(m.get("objects", [])) + 7)
            objs = m["objects"]
            for what, types in (("enemies", ("enemy", "chaser", "flyer")), ("coins", ("coin", "gem"))):
                sel = [o for o in objs if o["type"] in types]
                if mp.get(what) == "less" and sel:
                    drop = set(id(o) for o in sel[: max(1, len(sel) // 2)])
                    objs = [o for o in objs if id(o) not in drop]
                    notes.append(f"menos {what}")
                elif mp.get(what) == "more" and sel:
                    for o in sel[: max(2, len(sel))]:
                        c = dict(o)
                        if m["kind"] == "3d":
                            c["x"] = round(o.get("x", 0) + rnd.choice((-6, 6)), 2)
                        else:
                            c["x"] = max(1, min(m["w"] - 2, o.get("x", 1) + rnd.choice((-3, 3))))
                        objs.append(c)
                    notes.append(f"mais {what}")
            m["objects"] = objs
            out[path] = S.norm_map(m)
        return out, notes

    # ================================================================ CODE
    def edit_code(self, pid: str) -> Dict[str, Any]:
        mgr = self.mgr
        prompt_text = text(self.opts.get("prompt"), "", 20000)
        body = self.opts.get("body") or {}
        self.start([("plan", "Planejador de código"), ("code", "Programador"), ("review", "Revisor")])
        files_in = []
        for rel in [x for x in (body.get("files") if isinstance(body.get("files"), list) else []) if isinstance(x, str)][:6]:
            try:
                f = mgr.read_file(pid, "game", rel)
                if f.get("type") == "text":
                    files_in.append({"path": rel, "content": f["content"][:14000]})
            except EngineError:
                continue
        tree = [x["path"] for x in self._flat(mgr.tree(pid, "game")["children"])][:200]
        ctx = self.context(prompt_text)
        meta = mgr.meta(pid)
        info = {"kind": meta["kind"], "genre": meta["genre"], "scenes": mgr.list_scenes(pid)}
        plan = self.step("plan", "code_planner", "Planejador de código", {"request": prompt_text[:6000], "files": files_in, "tree": tree, "engine_api": ENGINE_API, "project": info, "attachments_digest": ctx["digest"][:6000]},
                         self._valid_code_plan, lambda: self._code_plan_rules(prompt_text, files_in), critique=True)
        written = self.step("code", "coder", "Programador", {"request": prompt_text[:6000], "plan": plan, "files": files_in, "engine_api": ENGINE_API, "project": info},
                            lambda raw: self._valid_files(raw, plan), lambda: self._code_rules(prompt_text, plan, files_in, info))
        probs = self.lint_files(written["files"])
        reviewed = self.step("review", "code_reviewer", "Revisor", {"files": written["files"], "syntax_problems": probs}, lambda raw: self._valid_files(raw, None, allow_empty=True),
                             lambda: {"files": [], "summary": written.get("summary", "")}, creative=False) if probs else {"files": [], "summary": written.get("summary", "")}
        final = {f["path"]: f for f in written["files"]}
        for f in reviewed["files"]:
            final[f["path"]] = f
        left = self.lint_files(list(final.values()))
        # grava (com instantâneo); arquivo que ainda tem erro de sintaxe é gravado mesmo assim, mas avisado
        mgr.snapshot(pid, "antes do código: " + prompt_text[:60])
        saved = []
        for f in final.values():
            try:
                mgr.write_file(pid, "game", f["path"], f["content"])
                saved.append(f["path"])
            except EngineError as exc:
                self.warnings.append(f"{f['path']}: {exc.message}")
        mgr.log(pid, "code", prompt_text[:200])
        summary = reviewed.get("summary") or written.get("summary") or ("Gravei: " + ", ".join(saved))
        return self.done({"files": saved, "summary": summary, "problems": left, "plan": plan})

    def _flat(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for n in nodes:
            if n["type"] == "file":
                out.append(n)
            else:
                out += self._flat(n.get("children", []))
        return out

    ALLOWED_CODE = re.compile(r"^(scripts/[\w./ -]+\.js|data/[\w./ -]+\.json|scenes/[\w -]+\.scene\.json|maps/[\w -]+\.map\.json)$")

    def _valid_code_plan(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        fs = []
        for f in (raw.get("files") if isinstance(raw.get("files"), list) else [])[:6]:
            if isinstance(f, dict) and isinstance(f.get("path"), str) and self.ALLOWED_CODE.match(f["path"]) and ".." not in f["path"]:
                fs.append({"path": f["path"], "action": "change" if f.get("action") == "change" else "create", "why": text(f.get("why"), "", 200)})
        return {"goal": text(raw.get("goal"), "", 300), "files": fs, "notes": [text(x, "", 160) for x in (raw.get("notes") if isinstance(raw.get("notes"), list) else [])][:5]} if fs else None

    def _valid_files(self, raw: Dict[str, Any], plan: Optional[Dict[str, Any]], allow_empty: bool = False) -> Optional[Dict[str, Any]]:
        fs = []
        allowed = {f["path"] for f in plan["files"]} if plan else None
        for f in (raw.get("files") if isinstance(raw.get("files"), list) else [])[:8]:
            if isinstance(f, dict) and isinstance(f.get("path"), str) and isinstance(f.get("content"), str) and self.ALLOWED_CODE.match(f["path"]) and ".." not in f["path"] and len(f["content"]) < 400000 and (allowed is None or f["path"] in allowed):
                fs.append({"path": f["path"], "content": f["content"], "why": text(f.get("why"), "", 200)})
        if not fs and not allow_empty:
            return None
        return {"files": fs, "summary": text(raw.get("summary"), "", 500)}

    def _code_plan_rules(self, prompt_text: str, files_in: List[Dict[str, Any]]) -> Dict[str, Any]:
        low = tpl._norm(prompt_text)
        snip = next((nm for words, nm, _b in self.SNIPPETS if any(w in low for w in words)), "")
        name = snip or slugify(prompt_text, "comportamento", 24).replace("-", "_") or "comportamento"
        path = files_in[0]["path"] if files_in and files_in[0]["path"].endswith(".js") else f"scripts/{name}.js"
        return {"goal": prompt_text[:200], "files": [{"path": path, "action": "change" if files_in and files_in[0]["path"] == path else "create", "why": "esqueleto de comportamento (sem IA)"}], "notes": []}

    SNIPPETS = (
        (("pulsar", "pulse", "respirar", "crescer e diminuir"), "pulsar", "const k = 1 + Math.sin(GE.state.time * (p.speed || 4)) * (p.amount || 0.12); n.sx = k; n.sy = k;"),
        (("girar", "rodar", "spin", "rotate"), "girar", "n.rotation = ((n.rotation || 0) + (p.speed || 90) * dt) % 360; if (n.ry !== undefined) n.ry = (n.ry + (p.speed || 90) * dt) % 360;"),
        (("seguir o mouse", "follow mouse", "mouse"), "seguir_mouse", "if (GE.dim === '2d' && GE.R.toWorld) { const w = GE.R.toWorld(GE.input.mouse.x, GE.input.mouse.y); n.x += (w.x - n.x) * Math.min(1, dt * (p.speed || 5)); n.y += (w.y - n.y) * Math.min(1, dt * (p.speed || 5)); }"),
        (("tremer", "shake", "tremor"), "tremer", "if (GE.R.cam) GE.R.cam.shake = Math.max(GE.R.cam.shake || 0, p.power || 0.3);"),
        (("dash", "investida", "correr rapido", "impulso"), "dash", "if (GE.input.hit('run')) { n.x += (n.flip ? -1 : 1) * (p.distance || 90); GE.sfx('jump'); }"),
        (("teletransport", "teleport"), "teletransportar", "if (GE.input.hit('action')) { n.x = p.x || 0; n.y = p.y || 0; GE.sfx('door'); }"),
    )

    def _code_rules(self, prompt_text: str, plan: Dict[str, Any], files_in: List[Dict[str, Any]], info: Dict[str, Any]) -> Dict[str, Any]:
        p = tpl._norm(prompt_text)
        pick = next(((nm, body) for words, nm, body in self.SNIPPETS if any(w in p for w in words)), None)
        path = plan["files"][0]["path"]
        name, body = pick or (re.sub(r"\W+", "_", Path(path).stem) or "meu_comportamento", "// TODO: escreva aqui o que este comportamento faz a cada quadro.\n    // Exemplo: n.x += 30 * dt;")
        content = (f"// {prompt_text.strip()[:120] or name}\n// Comportamento «{name}». Use na cena: \"behaviors\": [{{\"type\": \"{name}\"}}]\n"
                   f"GE.behavior('{name}', {{\n  init: function (n, p, s) {{\n    // roda uma vez quando o nó nasce\n  }},\n  update: function (n, dt, p, s) {{\n    {body}\n  }},\n}});\n")
        if files_in and files_in[0]["path"] == path and path.endswith(".js"):
            content = files_in[0]["content"].rstrip() + "\n\n" + content
        return {"files": [{"path": path, "content": content, "why": "esqueleto"}], "summary": f"Sem IA: criei o comportamento «{name}» em {path}. Use-o em um nó da cena com {{\"type\": \"{name}\"}}."}

    @staticmethod
    def lint_files(files: List[Dict[str, Any]]) -> List[str]:
        """Confere a sintaxe: JSON com json.loads; JS com `node --check` (se houver) ou, sem ele, balanço de chaves."""
        probs: List[str] = []
        node = shutil.which("node")
        for f in files:
            path, content = f["path"], f["content"]
            if path.endswith(".json"):
                try:
                    json.loads(content)
                except ValueError as exc:
                    probs.append(f"{path}: JSON inválido — {exc}")
            elif path.endswith(".js"):
                if node:
                    with tempfile.TemporaryDirectory() as td:
                        tmp = Path(td) / "check.js"
                        tmp.write_text(content, encoding="utf-8")
                        try:
                            r = subprocess.run([node, "--check", str(tmp)], capture_output=True, text=True, timeout=15)
                        except (OSError, subprocess.SubprocessError):
                            r = None
                        if r is not None and r.returncode != 0:
                            probs.append(f"{path}: " + (r.stderr.strip().splitlines() or ["erro de sintaxe"])[-1][:200])
                else:
                    stack = []
                    pairs = {")": "(", "]": "[", "}": "{"}
                    clean = re.sub(r"//.*|/\*.*?\*/|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`", "", content, flags=re.S)
                    for ch in clean:
                        if ch in "([{":
                            stack.append(ch)
                        elif ch in ")]}":
                            if not stack or stack.pop() != pairs[ch]:
                                probs.append(f"{path}: parênteses/chaves desbalanceados")
                                break
                    else:
                        if stack:
                            probs.append(f"{path}: parênteses/chaves sem fechar")
            if re.search(r"\b(eval|importScripts|XMLHttpRequest|WebSocket|document\.cookie|localStorage|sendBeacon)\b|\bfetch\s*\(", content) and path.endswith(".js"):
                probs.append(f"{path}: usa recurso não permitido nos jogos do ASTA (rede/armazenamento/eval)")
        return probs

    # ================================================================ ASSETS
    def make_asset(self, pid: str) -> Dict[str, Any]:
        from ..canvas import media as cm

        prompt_text = text(self.opts.get("prompt"), "", 4000)
        b = self.opts.get("body") or {}
        edit = b.get("action") == "edit"
        self.start([("brief", "Diretor de arte"), ("draw", "Desenhar")])
        ctx = self.context(prompt_text)
        fb = lambda: self._art_rules(prompt_text, b)   # noqa: E731
        brief = self.step("brief", "art_director", "Diretor de arte", {"request": prompt_text, "attachments_digest": ctx["digest"][:3000], "mode": "edit" if edit else "generate", "want_transparent": b.get("transparent") is True, "size": b.get("size", "")},
                          lambda raw: self._valid_brief(raw, prompt_text, b), fb, creative=False)
        if b.get("transparent") is True:
            brief["transparent"] = True
        elif b.get("transparent") is False:
            brief["transparent"] = False
        self.check()
        self.emit({"type": "step", "id": "draw", "label": "Desenhar", "status": "running"})
        settings = self.settings
        result: Optional[Dict[str, Any]] = None
        err = ""
        try:
            pid_media = cm.pick_provider(settings, "image")
        except Exception as exc:  # noqa: BLE001
            pid_media, err = "demo", str(exc)
        if pid_media != "demo":
            try:
                media = cm.build_media(settings, pid_media, cm.Ctl(check=self.check), self.store.models_dir)
                refs = []
                for key in ("image", "reference"):
                    d = self._data_url(b.get(key))
                    if d:
                        refs.append(d)
                prompt_full = brief["prompt"] + (", isolated on a plain solid white background, no shadow, centered" if brief["transparent"] else "")
                if edit and refs:
                    prompt_full = "Edit the image: " + prompt_text + ". Keep everything else exactly the same."
                imgs = media.image(prompt_full, size=brief["size"], count=1, negative=brief.get("negative", ""), refs=refs[: media.max_refs()] if media.supports_refs else [])
                m = imgs[0]
                result = {"mime": m.mime, "data": base64.b64encode(m.data).decode("ascii"), "source": "ai", "provider": pid_media, "needs_cutout": bool(brief["transparent"])}
            except (ProviderError, Exception) as exc:  # noqa: BLE001
                if isinstance(exc, Cancelled):
                    raise
                err = str(exc)[:200]
                self.warnings.append("imagem: " + err + " — usei o desenho vetorial do ASTA")
        if result is None:
            subject = art.pick_subject(prompt_text + " " + brief.get("subject", ""), "star")
            color = (brief.get("palette") or [None])[0] or art.pick_color(prompt_text, art.default_color(subject))
            svg = art.sprite_svg(subject, color)
            result = {"mime": "image/svg+xml", "data": base64.b64encode(svg.encode("utf-8")).decode("ascii"), "source": "procedural", "provider": "asta", "needs_cutout": False, "subject": subject}
        self.emit({"type": "step", "id": "draw", "label": "Desenhar", "status": "done" if result["source"] == "ai" else "warn", "note": err})
        result["name"] = slugify(brief.get("name") or prompt_text, "imagem", 28)
        result["brief"] = {k: brief.get(k) for k in ("subject", "style", "palette", "transparent", "size")}
        return self.done({"image": result})

    def _art_rules(self, prompt_text: str, b: Dict[str, Any]) -> Dict[str, Any]:
        subject = art.pick_subject(prompt_text, "")
        trans = b.get("transparent") is True or (b.get("transparent") is None and bool(subject))
        return {"subject": subject or prompt_text[:60], "prompt": prompt_text[:300], "style": "flat vector", "palette": [art.pick_color(prompt_text, "")] if art.pick_color(prompt_text, "") else [], "transparent": trans,
                "size": b.get("size") if b.get("size") in ("512x512", "1024x1024", "1024x512", "512x1024") else "1024x1024", "negative": "", "name": subject or "imagem"}

    def _valid_brief(self, raw: Dict[str, Any], prompt_text: str, b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not raw.get("prompt"):
            return None
        base = self._art_rules(prompt_text, b)
        pal = [c for c in (raw.get("palette") if isinstance(raw.get("palette"), list) else []) if isinstance(c, str) and re.match(r"^#[0-9a-fA-F]{6}$", c)][:5]
        return {"subject": text(raw.get("subject"), base["subject"], 80), "prompt": text(raw.get("prompt"), base["prompt"], 600), "style": text(raw.get("style"), "", 40), "palette": pal, "transparent": raw.get("transparent") is True,
                "size": raw.get("size") if raw.get("size") in ("512x512", "1024x1024", "1024x512", "512x1024") else base["size"], "negative": text(raw.get("negative"), "", 200), "name": text(raw.get("name"), base["name"], 40)}

    @staticmethod
    def _data_url(v: Any) -> Optional[Tuple[bytes, str]]:
        if not isinstance(v, str) or not v.startswith("data:") or ";base64," not in v:
            return None
        head, _, b64 = v.partition(",")
        try:
            raw = base64.b64decode(b64, validate=False)
        except (ValueError, TypeError):
            return None
        mime = head[5:].split(";")[0]
        return (raw, mime) if mime in ("image/png", "image/jpeg", "image/webp") and 0 < len(raw) < 12 * 1024 * 1024 else None

    # ================================================================ SOUND
    def make_sound(self, pid: str) -> Dict[str, Any]:
        from ..canvas import media as cm
        from .. import voice as voicelib

        prompt_text = text(self.opts.get("prompt"), "", 2000)
        b = self.opts.get("body") or {}
        self.start([("brief", "Diretor de som"), ("make", "Gerar")])
        want_kind = b.get("kind") if b.get("kind") in ("sfx", "music", "voice") else ""
        brief = self.step("brief", "sound_director", "Diretor de som", {"request": prompt_text, "kind": want_kind, "duration": b.get("duration"), "text": b.get("text", "")}, lambda raw: self._valid_sbrief(raw, prompt_text, want_kind, b),
                          lambda: self._sound_rules(prompt_text, want_kind, b), creative=False)
        if want_kind:
            brief["kind"] = want_kind
        self.check()
        self.emit({"type": "step", "id": "make", "label": "Gerar", "status": "running"})
        settings = self.settings
        data, mime, source, provider, err = b"", "audio/wav", "procedural", "asta", ""
        cap = "sound" if brief["kind"] in ("sfx", "music") else "voice"
        try:
            pm = cm.pick_provider(settings, cap)
        except Exception as exc:  # noqa: BLE001
            pm, err = "demo", str(exc)
        if brief["kind"] == "voice" and pm == "demo" and voicelib.tts_enabled(settings):
            try:
                data, mime = voicelib.synthesize(settings, brief.get("text") or prompt_text, brief.get("voice", ""))
                source, provider = "ai", "voz da Configuração"
            except Exception as exc:  # noqa: BLE001
                err = str(exc)[:160]
        elif pm != "demo":
            try:
                media = cm.build_media(settings, pm, cm.Ctl(check=self.check), self.store.models_dir)
                if brief["kind"] == "voice":
                    m = media.voice(brief.get("text") or prompt_text, voice=brief.get("voice", ""))
                else:
                    m = media.sound(brief["prompt"], kind="music" if brief["kind"] == "music" else "sfx", duration=int(max(1, min(60, brief["duration"]))))
                data, mime, source, provider = m.data, m.mime, "ai", pm
            except (ProviderError, Exception) as exc:  # noqa: BLE001
                if isinstance(exc, Cancelled):
                    raise
                err = str(exc)[:200]
                self.warnings.append("áudio: " + err + " — usei a síntese do ASTA")
        if not data:
            seed = abs(hash(prompt_text)) % 100000
            if brief["kind"] == "music":
                data = audio.music(brief["mood"], max(2, int(brief["duration"] / 2)), seed, 196.0 + seed % 5 * 14)
            elif brief["kind"] == "voice":
                data = audio.voice_babble(brief.get("text") or prompt_text, seed)
            else:
                data = audio.sfx(brief.get("sfx") or "select", seed)
            mime = "audio/wav"
        info = audio.wav_info(data) if mime in ("audio/wav", "audio/x-wav") else None
        self.emit({"type": "step", "id": "make", "label": "Gerar", "status": "done" if source == "ai" else "warn", "note": err})
        ext = {"audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/flac": "flac"}.get(mime, "wav")
        return self.done({"sound": {"name": slugify(brief.get("name") or prompt_text, "som", 28), "kind": brief["kind"], "mime": mime, "ext": ext, "data": base64.b64encode(data).decode("ascii"), "source": source, "provider": provider,
                                    "seconds": (info or {}).get("seconds", 0), "brief": {k: brief.get(k) for k in ("kind", "mood", "sfx", "duration")}}})

    def _sound_rules(self, prompt_text: str, kind: str, b: Dict[str, Any]) -> Dict[str, Any]:
        p = tpl._norm(prompt_text)
        sfx_words = (("coin", ("moeda", "coin", "ouro")), ("jump", ("pulo", "jump", "pular")), ("hit", ("dano", "hit", "bater", "soco")), ("win", ("vitoria", "win", "venceu")), ("lose", ("derrota", "lose", "perdeu", "game over")),
                     ("powerup", ("power", "upgrade", "item", "cura")), ("shoot", ("tiro", "shoot", "atirar")), ("laser", ("laser",)), ("explosion", ("explosao", "explosion", "bomba")), ("door", ("porta", "door")), ("step", ("passo", "step")),
                     ("magic", ("magia", "magic", "feitico")), ("select", ("clique", "click", "menu", "selecionar")), ("error", ("erro", "error")), ("place", ("colocar", "place")), ("pickup", ("pegar", "pickup")))
        sfx = next((k for k, ws in sfx_words if any(w in p for w in ws)), "")
        if not kind:
            kind = "voice" if any(w in p for w in ("voz", "fala", "narr", "voice", "dizendo", "fale")) else "music" if any(w in p for w in ("musica", "trilha", "tema", "music", "soundtrack", "loop", "ambiente")) else "sfx"
        mood = next((m for m, ws in (("epic", ("epic", "epico", "batalha", "boss")), ("tense", ("tens", "suspense", "perigo", "terror")), ("mysterious", ("misteri", "mystery", "noite")), ("melancholic", ("triste", "melanc", "sad")), ("joyful", ("alegre", "feliz", "happy", "festa", "joyful")), ("calm", ("calm", "relax", "suave", "paz"))) if any(w in p for w in ws)), "calm")
        dur = b.get("duration")
        try:
            dur = float(dur) if dur else (16 if kind == "music" else 3 if kind == "voice" else 1)
        except (TypeError, ValueError):
            dur = 16 if kind == "music" else 1
        return {"kind": kind, "name": sfx or slugify(prompt_text, "som", 24), "prompt": prompt_text[:300], "mood": mood, "duration": dur, "sfx": sfx or "select", "text": text(b.get("text"), prompt_text if kind == "voice" else "", 600), "voice": ""}

    def _valid_sbrief(self, raw: Dict[str, Any], prompt_text: str, kind: str, b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if raw.get("kind") not in ("sfx", "music", "voice"):
            return None
        base = self._sound_rules(prompt_text, kind, b)
        try:
            dur = clamp(float(raw.get("duration") or base["duration"]), 0.2, 60)
        except (TypeError, ValueError):
            dur = base["duration"]
        return {"kind": raw["kind"], "name": text(raw.get("name"), base["name"], 40), "prompt": text(raw.get("prompt"), base["prompt"], 400), "mood": raw.get("mood") if raw.get("mood") in audio.MOODS else base["mood"], "duration": dur,
                "sfx": raw.get("sfx") if raw.get("sfx") in audio.SFX_NAMES else base["sfx"], "text": text(raw.get("text"), base["text"], 800), "voice": text(raw.get("voice"), "", 40)}

    # ================================================================ SCRIPTS
    def write_script(self, pid: str) -> Dict[str, Any]:
        meta = self.mgr.meta(pid)
        b = self.opts.get("body") or {}
        action = b.get("action") if b.get("action") in ("generate", "improve", "expand", "rewrite", "shorten", "fix", "dialogue", "translate") else ("improve" if b.get("selection") else "generate")
        instruction = text(self.opts.get("prompt"), "", 4000)
        selection = text(b.get("selection"), "", 12000)
        self.start([("write", "Escritor"), ("edit", "Revisão")])
        ctx = self.context(instruction)
        payload = {"action": action, "instruction": instruction, "selection": selection, "context": text(b.get("context"), "", 6000), "kind": text(b.get("doc"), "", 40),
                   "project": {"name": meta["name"], "kind": meta["kind"], "genre": meta["genre"], "theme": meta["theme"], "description": meta.get("description", "")}, "attachments_digest": ctx["digest"][:8000], "web_notes": ctx["web"][:4000], "language": self.lang_of(meta, instruction + selection)}
        out = self.step("write", "script_writer", "Escritor", payload, lambda raw: ({"text": text(raw.get("text"), "", 60000), "title": text(raw.get("title"), "", 60), "notes": [text(x, "", 200) for x in (raw.get("notes") if isinstance(raw.get("notes"), list) else [])][:5]} if text(raw.get("text"), "") else None),
                        lambda: self._script_rules(action, instruction, selection, meta, payload["language"], b), critique=False, tokens=3600)
        self.emit({"type": "step", "id": "edit", "label": "Revisão", "status": "done"})
        return self.done({"text": out["text"], "title": out.get("title") or slugify(instruction, "roteiro", 30), "notes": out.get("notes", []), "action": action, "ai": self.live})

    def _script_rules(self, action: str, instruction: str, selection: str, meta: Dict[str, Any], lang: str, b: Dict[str, Any]) -> Dict[str, Any]:
        L = (lambda a, c: a if lang == "pt" else c)
        if action == "generate":
            doc = text(b.get("doc"), "", 30) or ("gdd" if re.search(r"gdd|design|documento", instruction, re.I) else "dialogo" if re.search(r"di[aá]logo|dialogue|fala", instruction, re.I) else "roteiro")
            if doc == "gdd":
                body = tpl.gdd({"name": meta["name"], "kind": meta["kind"], "genre": meta["genre"], "theme": meta["theme"]}, lang, instruction)
            elif doc in ("dialogo", "dialogue"):
                body = tpl.dialogues_md(tpl.dialogues(lang, meta["name"], meta["genre"]))
            else:
                body = "\n".join([f"# {meta['name']} — {L('Roteiro', 'Script')}", "", f"> {instruction[:300] or meta.get('description', '')}", "", f"## {L('Ato 1 — Chamado', 'Act 1 — The call')}", "", L("Apresente o herói, o mundo e o problema que muda tudo.", "Introduce the hero, the world and the problem that changes everything."), "",
                                  f"## {L('Ato 2 — Jornada', 'Act 2 — Journey')}", "", L("Obstáculos crescentes, aliados, uma perda e a virada.", "Growing obstacles, allies, a loss and the turn."), "", f"## {L('Ato 3 — Desfecho', 'Act 3 — Resolution')}", "", L("O confronto final e o que mudou.", "The final confrontation and what changed."), ""])
            return {"text": body, "title": doc, "notes": [L("Sem IA: modelo pronto para você preencher.", "No AI: ready-made outline for you to fill in.")]}
        s = selection or instruction
        if action == "fix":
            fixed = re.sub(r"[ \t]+", " ", s)
            fixed = re.sub(r"\s+([,.;:!?])", r"\1", fixed)
            fixed = re.sub(r"([.!?]\s+)([a-zà-ÿ])", lambda m: m.group(1) + m.group(2).upper(), fixed)
            fixed = (fixed[:1].upper() + fixed[1:]) if fixed else fixed
            return {"text": fixed, "title": "", "notes": [L("Sem IA: só espaços, pontuação e maiúsculas.", "No AI: spacing, punctuation and capitals only.")]}
        if action == "shorten":
            sentences = re.split(r"(?<=[.!?])\s+", s.strip())
            return {"text": " ".join(sentences[: max(1, (len(sentences) + 1) // 2)]), "title": "", "notes": [L("Sem IA: mantive a primeira metade das frases.", "No AI: kept the first half of the sentences.")]}
        if action == "expand":
            return {"text": s.rstrip() + "\n\n" + L("<!-- Continue aqui: o que o personagem sente? O que o cenário mostra? Que detalhe revela o mundo? -->", "<!-- Continue here: what does the character feel? What does the setting show? What detail reveals the world? -->"), "title": "", "notes": [L("Sem IA não dá para expandir de verdade: deixei perguntas-guia.", "Without AI I cannot truly expand: left guiding questions.")]}
        if action == "dialogue":
            who = [w for w in re.findall(r"[A-ZÀ-Ý][\wà-ÿ]+", s)[:2]] or [L("Herói", "Hero"), L("Guia", "Guide")]
            return {"text": "\n".join([f"{who[0]}: …", f"{who[-1]}: …", f"{who[0]}: …"]), "title": "", "notes": [L("Sem IA: esqueleto de diálogo.", "No AI: dialogue skeleton.")]}
        return {"text": s, "title": "", "notes": [L("Sem IA: não consegui reescrever; o texto ficou igual.", "No AI: could not rewrite; text unchanged.")]}

    # ================================================================ MAP
    def make_map(self, pid: str) -> Dict[str, Any]:
        mgr = self.mgr
        meta = mgr.meta(pid)
        b = self.opts.get("body") or {}
        prompt_text = text(self.opts.get("prompt"), "", 4000)
        action = b.get("action") if b.get("action") in ("generate", "regen_region", "edit") else "generate"
        path = text(b.get("path"), "", 200)
        self.start([("design", "Projetista de fases"), ("build", "Construir")])
        ctx = self.context(prompt_text)
        cur = None
        if path:
            try:
                cur = mgr.get_map(pid, path)
            except EngineError:
                cur = None
        dim = S.KINDS[meta["kind"]]["dim"]
        payload = {"request": prompt_text, "action": action, "region": b.get("region"), "current": ({"kind": cur.get("kind"), "theme": cur.get("theme"), "genre": cur.get("genre"), "objects": len(cur.get("objects", []))} if cur else None),
                   "project": {"kind": meta["kind"], "genre": meta["genre"], "theme": meta["theme"]}, "catalog": {"themes": list(S.THEMES), "biomes": list(S.BIOMES)}, "attachments_digest": ctx["digest"][:4000], "web_notes": ctx["web"][:3000]}
        design = self.step("design", "map_designer", "Projetista de fases", payload, lambda raw: self._valid_mdesign(raw, meta, cur, prompt_text, b), lambda: self._map_rules(prompt_text, meta, cur, b), critique=False)
        o = self.opts   # o que o usuário escolheu nos controles da tela vence a sugestão da IA
        if o.get("theme") in S.THEMES:
            design["theme"] = o["theme"]
        if o.get("genre") in gmaps.GEN2D and design["kind"] == "2d":
            design["genre"] = o["genre"]
        if o.get("length") in gmaps.SIZES:
            design["size"] = o["length"]
        self.check()
        self.emit({"type": "step", "id": "build", "label": "Construir", "status": "running"})
        seed = int(b.get("seed") or 0) or (abs(hash(prompt_text + str(time.time()))) % (2 ** 31))
        if design["kind"] == "3d":
            if action == "regen_region" and cur and cur.get("kind") == "3d" and isinstance(b.get("region"), dict):
                r = b["region"]
                m = gmaps.edit_region_3d(cur, "regen", float(r.get("x") or 0), float(r.get("z") or 0), float(r.get("radius") or 20), 0.9, seed)
            elif action == "edit" and cur and cur.get("kind") == "3d":
                m = dict(cur, theme=design["theme"], biome=design["biome"] or cur.get("biome"), colors=gmaps.BIOME_COLORS.get(design["biome"] or cur.get("biome"), cur.get("colors")))
            else:
                m = gmaps.generate_3d(seed, design["theme"], design["biome"], 200.0 if design["size"] != "short" else 140.0, 65, int(14 * design["coins"]), int(4 * design["enemies"]), 1.0)
        else:
            genre = design["genre"] or (cur or {}).get("genre") or "platformer"
            if action == "regen_region" and cur and cur.get("kind") == "2d" and isinstance(b.get("region"), dict):
                m = gmaps.regen_region_2d(cur, b["region"], seed)
            elif action == "edit" and cur and cur.get("kind") == "2d":
                m = copy.deepcopy(cur)
                m["theme"] = design["theme"]
                pal = gmaps.palette2d(design["theme"])
                for k, v in m["palette"].items():
                    if k in pal:
                        v["color"] = pal[k]["color"]
            else:
                m = gmaps.generate_2d(genre, seed, design["theme"], design["size"], design["enemies"], design["coins"])
        m["name"] = design["name"] or (cur or {}).get("name") or "Mapa"
        added = self._add_objects(m, design.get("objects", []), seed)
        m = S.norm_map(m)
        problems = []
        if not any(o["type"] == "player" for o in m["objects"]):
            problems.append("sem ponto de partida")
        if added:
            self.note(f"{added} objeto(s) novos")
        self.emit({"type": "step", "id": "build", "label": "Construir", "status": "done"})
        if not path:
            path = "maps/" + slugify(m["name"], "mapa", 24) + ".map.json"
        if b.get("save") is not False and (b.get("save") is True or action != "edit" or not cur):
            if action == "generate" and not b.get("overwrite") and (mgr.dir(pid) / "game" / path).exists():
                path = "maps/" + slugify(m["name"], "mapa", 20) + "-" + str(seed % 1000) + ".map.json"
            mgr.snapshot(pid, "antes do mapa: " + prompt_text[:60]) if (mgr.dir(pid) / "game" / path).exists() else None
            m = mgr.save_map(pid, path, m)
            mgr.log(pid, "map", prompt_text[:200] or action)
        return self.done({"map": m, "path": path, "problems": problems, "summary": design.get("notes") or f"Mapa «{m['name']}» pronto: {len(m['objects'])} objetos."})

    def _map_rules(self, prompt_text: str, meta: Dict[str, Any], cur: Optional[Dict[str, Any]], b: Dict[str, Any]) -> Dict[str, Any]:
        p = tpl._norm(prompt_text)
        kind = "3d" if (cur or {}).get("kind") == "3d" or (not cur and S.KINDS[meta["kind"]]["dim"] == "3d") else "2d"
        _, genre, theme = tpl.detect(prompt_text, "", "", "")
        theme = theme if any(w in p for w in sum((list(ws) for t, ws in tpl.THEME_WORDS), [])) else ((cur or {}).get("theme") or meta["theme"])
        genre = (cur or {}).get("genre") or (meta["genre"] if meta["genre"] in gmaps.GEN2D else "platformer")
        size = "long" if re.search(r"grande|enorme|longo|big|large|huge|long", p) else "short" if re.search(r"pequen|curto|small|short|tiny", p) else "medium"
        objs = []
        counts = {"casa": ("house", 2), "house": ("house", 2), "arvore": ("tree", 12), "tree": ("tree", 12), "pedra": ("rock", 8), "rock": ("rock", 8), "inimigo": ("enemy", 5), "enemy": ("enemy", 5), "moeda": ("coin", 10), "coin": ("coin", 10),
                  "gema": ("gem", 4), "gem": ("gem", 4), "npc": ("npc", 1), "espinho": ("spike", 4), "spike": ("spike", 4), "caixa": ("crate", 4), "crate": ("crate", 4), "chave": ("key", 1), "mola": ("spring", 3), "voador": ("flyer", 3), "portal": ("portal", 1)}
        for w, (tp, n) in counts.items():
            if w in p and not any(o["type"] == tp for o in objs):
                m = re.search(r"(\d+)\s*(?:" + w + ")", p)
                objs.append({"type": tp, "count": int(m.group(1)) if m else n, "near": "random"})
        return {"name": text(b.get("name"), "", 40) or (cur or {}).get("name") or ("Mundo" if kind == "3d" else "Fase"), "kind": kind, "genre": genre, "theme": theme, "biome": (cur or {}).get("biome") or "", "size": size,
                "enemies": 0.4 if re.search(r"sem inimigo|no enem|pac", p) else 1.0, "coins": 1.0, "objects": objs, "notes": ""}

    def _valid_mdesign(self, raw: Dict[str, Any], meta: Dict[str, Any], cur: Optional[Dict[str, Any]], prompt_text: str, b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        base = self._map_rules(prompt_text, meta, cur, b)
        kind = raw.get("kind") if raw.get("kind") in ("2d", "3d") else base["kind"]
        if cur:
            kind = cur.get("kind", kind)
        objs = []
        for o in (raw.get("objects") if isinstance(raw.get("objects"), list) else [])[:12]:
            if isinstance(o, dict) and re.match(r"^[a-z_]{2,20}$", str(o.get("type") or "")):
                try:
                    n = int(clamp(float(o.get("count") or 1), 1, 30))
                except (TypeError, ValueError):
                    n = 1
                objs.append({"type": o["type"], "count": n, "near": o.get("near") if o.get("near") in ("center", "edge", "spawn", "goal", "random") else "random"})
        try:
            en, co = clamp(float(raw.get("enemies", 1)), 0, 2.5), clamp(float(raw.get("coins", 1)), 0, 2.5)
        except (TypeError, ValueError):
            en, co = 1.0, 1.0
        return {"name": text(raw.get("name"), base["name"], 40), "kind": kind, "genre": raw.get("genre") if raw.get("genre") in gmaps.GEN2D else base["genre"], "theme": raw.get("theme") if raw.get("theme") in S.THEMES else base["theme"],
                "biome": raw.get("biome") if raw.get("biome") in S.BIOMES else base["biome"], "size": raw.get("size") if raw.get("size") in gmaps.SIZES else base["size"], "enemies": en, "coins": co, "objects": objs or base["objects"], "notes": text(raw.get("notes"), "", 300)}

    def _add_objects(self, m: Dict[str, Any], wanted: List[Dict[str, Any]], seed: int) -> int:
        import random
        rnd = random.Random(seed)
        n_added = 0
        region = (self.opts.get("body") or {}).get("region") if isinstance((self.opts.get("body") or {}).get("region"), dict) else None
        for w in wanted:
            for _ in range(w["count"]):
                if m["kind"] == "3d":
                    half = m["size"] / 2
                    if region and region.get("radius"):
                        a, rr = rnd.random() * 6.283, rnd.random() * float(region["radius"])
                        x, z = float(region.get("x") or 0) + rr * __import__("math").cos(a), float(region.get("z") or 0) + rr * __import__("math").sin(a)
                    else:
                        x, z = rnd.uniform(-half * 0.85, half * 0.85), rnd.uniform(-half * 0.85, half * 0.85)
                    res = m["res"]
                    i, j = int(max(0, min(res - 1, (x / m["size"] + 0.5) * (res - 1)))), int(max(0, min(res - 1, (z / m["size"] + 0.5) * (res - 1))))
                    if m["heights"][j * res + i] / 255 <= m.get("water_level", 0.18) + 0.02:
                        continue
                    m["objects"].append({"type": w["type"], "x": round(x, 2), "z": round(z, 2), "ry": rnd.randint(0, 359)})
                else:
                    grid = m["layers"][0]["data"]
                    solid = {int(k) for k, v in m["palette"].items() if v.get("solid")}
                    if region and "x0" in region:
                        x0, x1, y0, y1 = sorted((int(region["x0"]), int(region["x1"])))[0], sorted((int(region["x0"]), int(region["x1"])))[1], sorted((int(region["y0"]), int(region["y1"])))[0], sorted((int(region["y0"]), int(region["y1"])))[1]
                    else:
                        x0, x1, y0, y1 = 2, m["w"] - 3, 1, m["h"] - 2
                    for _try in range(30):
                        x, y = rnd.randint(max(0, x0), min(m["w"] - 1, x1)), rnd.randint(max(0, y0), min(m["h"] - 1, y1))
                        free_cell = grid[y][x] not in solid
                        on_floor = m.get("genre") != "platformer" or (y + 1 < m["h"] and grid[y + 1][x] in solid)
                        if free_cell and on_floor and not any(o.get("x") == x and o.get("y") == y for o in m["objects"]):
                            m["objects"].append({"type": w["type"], "x": x, "y": y})
                            break
                    else:
                        continue
                n_added += 1
        return n_added

    # ================================================================ PUBLISH
    def plan_publish(self, pid: str) -> Dict[str, Any]:
        mgr = self.mgr
        meta = mgr.meta(pid)
        prompt_text = text(self.opts.get("prompt"), "", 3000)
        self.start([("write", "Publicador")])
        bundle = mgr.bundle(pid)
        summary = {"name": meta["name"], "kind": meta["kind"], "genre": meta["genre"], "theme": meta["theme"], "scenes": list(bundle["scenes"]), "images": len(bundle["assets"]["images"]), "sounds": len(bundle["assets"]["sounds"]),
                   "description": meta.get("description", ""), "publish": meta.get("publish", {})}
        lang = self.lang_of(meta, prompt_text)
        out = self.step("write", "publisher", "Publicador", {"request": prompt_text, "project": summary, "language": lang}, lambda raw: self._valid_pub(raw, meta, lang), lambda: self._pub_rules(meta, lang, prompt_text), creative=True)
        return self.done({"publish": out})

    def _pub_rules(self, meta: Dict[str, Any], lang: str, prompt_text: str) -> Dict[str, Any]:
        L = (lambda a, c: a if lang == "pt" else c)
        g = S.GENRES.get(meta["genre"], {"label": meta["genre"]})["label"]
        return {"short": L(f"{g} {S.KINDS[meta['kind']]['label']}: {meta['name']}", f"{S.KINDS[meta['kind']]['label']} {g}: {meta['name']}")[:80],
                "description": f"**{meta['name']}**\n\n" + (meta.get("description") or L("Um jogo feito com o ASTA Game Engine.", "A game made with the ASTA Game Engine.")) + "\n\n" + L("Colete itens, evite inimigos e chegue ao objetivo.", "Collect items, avoid enemies and reach the goal."),
                "tags": [meta["kind"], meta["genre"], meta["theme"], "asta"][:8], "release_notes": L("- Primeira versão jogável\n- Controles de teclado e toque", "- First playable version\n- Keyboard and touch controls"), "version": "1.0.0",
                "orientation": "landscape", "fullscreen": True, "checklist": [L("Teste o jogo inteiro em ▶ Jogar", "Play the whole game with ▶ Play"), L("Escolha o ícone (Assets)", "Pick the icon (Assets)"), L("Defina versão e identificador", "Set version and identifier")]}

    def _valid_pub(self, raw: Dict[str, Any], meta: Dict[str, Any], lang: str) -> Optional[Dict[str, Any]]:
        base = self._pub_rules(meta, lang, "")
        if not raw.get("description") and not raw.get("short"):
            return None
        ver = str(raw.get("version") or "1.0.0")
        return {"short": text(raw.get("short"), base["short"], 90), "description": text(raw.get("description"), base["description"], 4000), "tags": [slugify(t, "tag", 20) for t in (raw.get("tags") if isinstance(raw.get("tags"), list) else [])][:8] or base["tags"],
                "release_notes": text(raw.get("release_notes"), base["release_notes"], 2000), "version": ver if re.match(r"^\d+\.\d+\.\d+$", ver) else "1.0.0", "orientation": raw.get("orientation") if raw.get("orientation") in ("landscape", "portrait", "any") else "landscape",
                "fullscreen": raw.get("fullscreen") is not False, "checklist": [text(x, "", 160) for x in (raw.get("checklist") if isinstance(raw.get("checklist"), list) else [])][:8] or base["checklist"]}
