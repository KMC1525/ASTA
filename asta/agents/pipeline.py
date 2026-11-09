"""Pipeline multi-agentes: recebe prompt + anexos, analisa, planeja, cria, revisa e empacota."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import attachments as att
from .. import builder, voice
from ..cards import normalize_character
from ..providers import ProviderError, build_provider
from ..storage import Store
from ..util import hardware_info, new_id, now_iso, safe_filename, slugify, text
from . import prompts, rulebased
from .runner import TRANSIENT, Cancelled, Runner  # noqa: F401  (reexportados)
from .schema import (
    BIOME_DEFAULTS, BUDGETS, budget_for, normalize_audio, normalize_ux, normalize_world, palette_for,
)

STEPS = ["attachments", "analyst", "planner", "characters", "architect", "sound_ux", "reviewer", "package"]


class Pipeline(Runner):
    domain = "world"

    def __init__(self, store: Store, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False):
        super().__init__(store, emit, cancelled)

    # ------------------------------------------------------------------ execução
    def run(self, req: Dict[str, Any]) -> Dict[str, Any]:
        st = self.store
        settings = st.get_settings()
        self.gen = dict(settings["generation"])
        for k, v in (req.get("settings") or {}).items():
            if k in self.gen and v is not None:
                self.gen[k] = v
        chars_cfg = settings["characters"]
        pid = settings["active"].get("generation", "demo")
        self.provider = build_provider(settings, pid, st.models_dir)
        self.configure_team(self.gen, None, pid)   # equipe: agentes em paralelo + esforço (settings.generation / pedido)
        hw = hardware_info()
        tier = self.gen.get("quality") if self.gen.get("quality") in BUDGETS else hw["tier"]
        budget = budget_for(tier)
        prompt = str(req.get("prompt") or "").strip()
        project = st.get_project(req["project_id"]) if req.get("project_id") else None
        if req.get("project_id") and (not project or project.get("kind", "world") != "world"):
            raise ValueError("Projeto não encontrado")
        previous = st.load_version(project["id"]) if project else None
        self.language = "the same language as the user's prompt"
        self.lang_code = "pt-BR"
        self.emit({"type": "start", "steps": STEPS, "provider": pid, "model": self.provider.model, "tier": tier,
                   "update": bool(project)})

        # ---------- anexos
        self._step("attachments", "running")
        uploads = st.get_uploads(req.get("attachment_ids") or [])   # pacotes (ZIP, RAR…) já vêm abertos: cada arquivo de dentro é um anexo
        analyzed = []
        transcribe = voice.transcriber(settings)
        for meta in uploads:
            self._check()
            analyzed.append(att.analyze(Path(meta["path"]), meta["name"], meta.get("mime", ""), transcribe=transcribe))
        digest = att.build_digest(analyzed) if self.gen.get("include_attachments", True) else ""
        images = att.collect_images(analyzed) if self.gen.get("include_attachments", True) else []
        self._step("attachments", "done" if uploads else "skipped", count=len(uploads), images=len(images))

        wb = st.worldbuildings.get(req.get("worldbuilding_id") or "") if req.get("worldbuilding_id") else None
        if not wb and project and project.get("worldbuilding_id"):
            wb = st.worldbuildings.get(project["worldbuilding_id"])
        wb_payload = {"name": wb["name"], "system_prompt": wb["system_prompt"]} if wb else None
        chosen_ids = req.get("character_ids") or (project or {}).get("character_ids") or []
        chosen = [c for c in (st.characters.get(i) for i in chosen_ids) if c]
        if not prompt and not wb and not chosen and not digest:
            raise ValueError("Escreva um prompt ou anexe algo para gerar o mundo.")
        prev_world = previous["world"] if previous else None
        prev_chars = previous["characters"] if previous else []

        # ---------- 1. Analista
        brief, fb = self._agent(
            "analyst", "analyst", prompts.ANALYST,
            {
                "prompt": prompt, "attachments_digest": digest, "worldbuilding": wb_payload,
                "characters": [{"name": c["name"], "role": c["role"], "tags": c["tags"], "system_prompt": c["system_prompt"][:600]} for c in chosen],
                "settings": {k: self.gen.get(k) for k in ("perspective", "size", "max_npcs", "realism")},
                "previous": {"title": prev_world["title"], "brief": previous.get("brief")} if previous else None,
            },
            rulebased.analyst, images=images,
        )
        if not text(brief.get("title"), ""):  # modelo omitiu o título → deriva do pedido
            brief["title"] = (prev_world["title"] if prev_world else
                              rulebased._sentence_title(prompt, rulebased.detect_lang(prompt)) if prompt else
                              (wb_payload or {}).get("name") or "Novo mundo")
        if not text(brief.get("summary"), ""):
            brief["summary"] = prompt[:300]
        brief["language"] = text(brief.get("language"), "pt-BR", 12)
        self.language = prompts.lang_name(brief["language"])
        self.lang_code = brief["language"]
        self._step("analyst", "warn" if fb else "done", title=brief.get("title", ""))

        # ---------- 2. Planejador
        plan, fb = self._agent(
            "planner", "planner", prompts.PLANNER,
            {"brief": brief, "settings": {k: self.gen.get(k) for k in ("perspective", "size", "realism", "day_cycle")},
             "budget": budget, "previous_world": _world_summary(prev_world) if prev_world else None},
            rulebased.planner,
        )
        self._step("planner", "warn" if fb else "done", landmarks=len(plan.get("landmarks") or []))

        # ---------- 3. Personagens
        world_chars, need = self._plan_characters(brief, chosen, prev_chars, budget, chars_cfg)
        if need:
            gen_cards, fb = self._agent(
                "characters", "characters", prompts.CHARACTERS,
                {"brief": brief, "need": need, "existing": [{"id": c["id"], "name": c["name"], "role": c["role"]} for c in world_chars],
                 "worldbuilding": wb_payload, "detail": chars_cfg.get("detail", "detailed")},
                rulebased.characters, tokens_mult=1.4,
            )
            self._merge_generated(world_chars, gen_cards.get("characters"), need)
            self._step("characters", "warn" if fb else "done", count=len(need))
        else:
            self._step("characters", "skipped", count=0)
        generated_ids = [c["id"] for c in world_chars if not c.get("source_id") and c["id"] not in {p["id"] for p in prev_chars}]

        # ---------- 4. Arquiteto
        audio_files = _audio_names(project, analyzed)
        world, fb_arch = self._architect(brief, plan, world_chars, budget, tier, prev_world, audio_files, None)
        self._step("architect", "warn" if fb_arch else "done", structures=len(world["structures"]), npcs=len(world["npcs"]))

        # ---------- 5. Som & UX
        world, fb = self._sound_ux(brief, plan, world, audio_files, None)
        self._step("sound_ux", "warn" if fb else "done", music=world["audio"]["music"]["mood"], ambience=world["audio"]["ambience"])

        # ---------- 6. Revisor (+ revisões)
        review = self._review(brief, world, world_chars, budget, prompt)
        rounds = self.team.revisions(int(self.gen.get("revisions", 1)))
        for r in range(rounds):
            issues = [i for i in (review.get("issues") or []) if isinstance(i, dict)]
            if review.get("approved", True) or not issues:
                break
            self.emit({"type": "revision", "round": r + 1, "issues": len(issues)})
            areas = {str(i.get("area", "")).lower() for i in issues}
            fb_text = "\n".join(f"- [{i.get('area')}] {i.get('problem')} → {i.get('fix')}" for i in issues)[:3000]
            if "characters" in areas and generated_ids:
                redo = [n for n in need if _slug_id(n) in generated_ids or n.get("is_player")]
                if redo:
                    cards, _ = self._agent(
                        "characters", "characters", prompts.CHARACTERS + "\n\nFEEDBACK TO FIX:\n" + fb_text,
                        {"brief": brief, "need": redo, "existing": [], "worldbuilding": wb_payload, "detail": chars_cfg.get("detail", "detailed")},
                        rulebased.characters, tokens_mult=1.4, feedback=True,
                    )
                    self._merge_generated(world_chars, cards.get("characters"), redo, replace=True)
            if areas & {"world", "characters"}:
                world, _ = self._architect(brief, plan, world_chars, budget, tier, prev_world, audio_files, fb_text, keep=world)
                self._step("architect", "done", structures=len(world["structures"]), npcs=len(world["npcs"]), revision=True)
            if areas & {"audio", "ux"}:
                world, _ = self._sound_ux(brief, plan, world, audio_files, fb_text)
                self._step("sound_ux", "done", revision=True)
            review = self._review(brief, world, world_chars, budget, prompt)
        if not review.get("approved", True):
            self.warnings.append("reviewer: not approved after revisions")

        # ---------- 7. Empacotador
        return self._package(req, project, prompt, digest, analyzed, uploads, brief, plan, world, world_chars, review, wb_payload, tier, pid)

    # ------------------------------------------------------------------ sub-etapas
    def _plan_characters(self, brief, chosen, prev_chars, budget, chars_cfg):
        """Decide quais personagens já existem e quais precisam ser criados."""
        cap = budget["npcs"]
        user_cap = int(self.gen.get("max_npcs") or 0)
        if user_cap:
            cap = min(cap, user_cap)
        world_chars: List[Dict[str, Any]] = []
        used_ids: set = set()

        def add(card: Dict[str, Any], source: str = "", fixed_id: str = "") -> None:
            card = dict(card)
            base = fixed_id or slugify(card.get("name", "npc"), "npc")
            cid, k = base, 2
            while cid in used_ids:
                cid, k = f"{base}-{k}", k + 1
            used_ids.add(cid)
            card["id"] = cid
            if source:
                card["source_id"] = source
            world_chars.append(card)

        for c in prev_chars:  # atualização: mantém quem já existia (ids estáveis → memórias preservadas)
            add(c, c.get("source_id", ""), fixed_id=c["id"])
        existing_names = {c["name"].strip().lower() for c in world_chars}
        for c in chosen:
            if c["name"].strip().lower() in existing_names:
                # substitui o snapshot antigo pelo card atualizado, mantendo o id
                for i, w in enumerate(world_chars):
                    if w["name"].strip().lower() == c["name"].strip().lower():
                        keep = w["id"]
                        world_chars[i] = dict(c, id=keep, source_id=c["id"])
            else:
                add(c, c["id"])
                existing_names.add(c["name"].strip().lower())
        npc_count = sum(1 for c in world_chars if c.get("role") != "player")
        need: List[Dict[str, Any]] = []
        for want in brief.get("characters") or []:
            if not isinstance(want, dict) or npc_count + len([n for n in need if not n.get("is_player")]) >= cap:
                break
            name = text(want.get("name"), "", 60)
            if not name or name.strip().lower() in existing_names:
                continue
            need.append({"id": slugify(name, "npc"), "name": name, "role": text(want.get("role"), "", 80),
                         "personality": text(want.get("personality"), "", 300),
                         "relationship_to_player": text(want.get("relationship_to_player"), "", 200)})
        has_player = any(c.get("role") == "player" for c in world_chars)
        if chars_cfg.get("player_character", True) and not has_player:
            pl = brief.get("player") if isinstance(brief.get("player"), dict) else {}
            need.append({"id": "player", "name": text(pl.get("name"), "Você", 60), "is_player": True,
                         "description": text(pl.get("description"), "", 300)})
        return world_chars, need

    def _merge_generated(self, world_chars, cards, need, replace: bool = False) -> None:
        cards = [c for c in (cards or []) if isinstance(c, dict)]
        by_name = {c.get("name", "").strip().lower(): c for c in cards}
        for n in need:
            raw = by_name.get(n["name"].strip().lower())
            if raw is None:  # o modelo esqueceu este personagem → gera por regras
                raw = rulebased.characters({"brief": {"language": self.lang_code}, "need": [n], "detail": "short"})["characters"][0]
            raw = dict(raw)
            raw["role"] = "player" if n.get("is_player") else "npc"
            card = normalize_character(raw)
            card["id"] = n["id"]
            if replace:
                world_chars[:] = [c for c in world_chars if c["id"] != n["id"]]
            used = {c["id"] for c in world_chars}
            base, k = card["id"], 2
            while card["id"] in used:
                card["id"], k = f"{base}-{k}", k + 1
            world_chars.append(card)

    def _architect(self, brief, plan, world_chars, budget, tier, prev_world, audio_files, feedback, keep=None):
        payload = {
            "brief": brief, "plan": plan,
            "characters": [{"id": c["id"], "name": c["name"], "role": c["role"], "tags": c["tags"]} for c in world_chars],
            "budget": budget,
            "settings": {k: self.gen.get(k) for k in ("perspective", "realism", "size", "day_cycle", "npc_autonomy", "max_npcs")},
            "previous_world": prev_world, "feedback": feedback,
        }
        raw, fb = self._agent("architect", "architect", prompts.ARCHITECT, payload, rulebased.architect, tokens_mult=1.3, feedback=bool(feedback))
        ids = [c["id"] for c in world_chars]
        world = normalize_world(raw, tier, self.gen, ids, audio_files, default_title=brief.get("title", "Mundo"))
        by_id = {c["id"]: c for c in world_chars}
        world["npcs"] = [n for n in world["npcs"] if by_id[n["char"]].get("role") != "player"]
        if world["player"].get("char") and by_id[world["player"]["char"]].get("role") != "player":
            world["player"]["char"] = ""
        if not world["player"].get("char"):
            world["player"]["char"] = next((c["id"] for c in world_chars if c.get("role") == "player"), "")
        # reparos determinísticos: nunca entregar mundo vazio ou NPC sem posição
        fallback_raw = rulebased.architect({**payload, "settings": self.gen})
        if len(world["structures"]) < 3:
            fixed = normalize_world({**fallback_raw}, tier, self.gen, ids, audio_files, default_title=brief.get("title", "Mundo"))
            world["structures"] = fixed["structures"]
            self.warnings.append("architect: structures completed by fallback")
        placed = {n["char"] for n in world["npcs"]}
        cap = budget["npcs"] if not int(self.gen.get("max_npcs") or 0) else min(budget["npcs"], int(self.gen["max_npcs"]))
        missing = [c for c in world_chars if c.get("role") != "player" and c["id"] not in placed]
        if missing and len(world["npcs"]) < cap:
            extra = normalize_world(
                {"npcs": [n for n in fallback_raw["npcs"] if n["char"] in {m["id"] for m in missing}], "environment": {"size": world["environment"]["size"]}},
                tier, self.gen, ids, audio_files)
            existing_ids = {n["id"] for n in world["npcs"]}
            for n in extra["npcs"]:
                if n["id"] not in existing_ids and len(world["npcs"]) < cap:
                    world["npcs"].append(n)
        if keep:  # na revisão preserva áudio/UX já definidos
            world["audio"], world["ux"] = keep["audio"], keep["ux"]
        return world, fb

    def _sound_ux(self, brief, plan, world, audio_files, feedback):
        payload = {
            "brief": brief, "plan": {"audio_plan": plan.get("audio_plan"), "ux_plan": plan.get("ux_plan")},
            "world_summary": {"biome": world["environment"]["biome"], "weather": world["environment"]["weather"],
                              "time_of_day": world["environment"]["time_of_day"], "title": world["title"]},
            "attachments_audio": audio_files, "feedback": feedback,
        }
        raw, fb = self._agent("sound_ux", "sound_ux", prompts.SOUND_UX, payload, rulebased.sound_ux, feedback=bool(feedback))
        env = world["environment"]
        world["audio"] = normalize_audio(raw.get("audio"), env["biome"], env["weather"], audio_files)
        world["ux"] = normalize_ux(raw.get("ux"))
        if not world["ux"]["intro"]:
            world["ux"]["intro"] = world["title"]
        return world, fb

    def _review(self, brief, world, world_chars, budget, prompt):
        payload = {
            "request": prompt[:1500], "brief": brief, "budget": budget,
            "world": {**_world_summary(world), "structures": world["structures"][:80], "npcs": world["npcs"]},
            "characters": [{"id": c["id"], "name": c["name"], "role": c["role"], "tags": c["tags"], "system_prompt": c["system_prompt"][:500]} for c in world_chars],
            "audio": world["audio"], "ux": world["ux"],
        }
        review, fb = self._agent("reviewer", "reviewer", prompts.REVIEWER, payload, rulebased.reviewer)
        review["approved"] = bool(review.get("approved", True))
        self._step("reviewer", "warn" if fb else "done", approved=review["approved"], score=review.get("score"),
                   issues=len(review.get("issues") or []))
        return review

    def _package(self, req, project, prompt, digest, analyzed, uploads, brief, plan, world, world_chars, review, wb_payload, tier, pid):
        self._check()
        self._step("package", "running")
        st = self.store
        auto_tags = [t for t in (text(x, "", 30).lower() for x in (brief.get("tags") or [])) if t]
        if len(auto_tags) < 3:
            pt = str(world.get("language", "pt")).lower().startswith("pt")
            auto_tags.append(rulebased.BIOME_TAG.get(world["environment"]["biome"], ("", ""))[0 if pt else 1] or world["environment"]["biome"])
        auto_tags += sorted({a["kind"] for a in analyzed if a["kind"] not in ("text", "file")})
        auto_tags = list(dict.fromkeys(auto_tags))[:12]
        summary = text(brief.get("summary"), "", 240) or text(review.get("summary"), "", 240)
        if project is None:
            project = st.create_project(
                world["title"], description=world.get("description") or summary,
                worldbuilding_id=req.get("worldbuilding_id") or "", character_ids=list(req.get("character_ids") or []),
            )
        else:
            if req.get("worldbuilding_id"):
                project["worldbuilding_id"] = req["worldbuilding_id"]
            if req.get("character_ids"):
                project["character_ids"] = list(req["character_ids"])
            project["description"] = world.get("description") or project.get("description", "")
        n = int(project.get("current") or 0) + 1
        project["tags"]["auto"] = list(dict.fromkeys(auto_tags + project["tags"].get("auto", [])))[:14] if n > 1 else auto_tags
        project["settings"] = {k: self.gen.get(k) for k in ("perspective", "realism", "size", "quality", "content", "npc_autonomy")}
        project["palette"] = palette_for(world)
        project["language"] = brief.get("language", "pt-BR")

        # anexos → pasta do projeto (permanecem p/ futuras atualizações)
        adir = st.project_dir(project["id"]) / "attachments"
        adir.mkdir(parents=True, exist_ok=True)
        for meta in uploads:
            name, k = safe_filename(meta["name"]), 1
            while (adir / name).exists():
                stem, dot, ext = meta["name"].rpartition(".")
                name = f"{stem or meta['name']}-{k}{dot}{ext}" if dot else f"{meta['name']}-{k}"
                k += 1
            shutil.copyfile(meta["path"], adir / name)
            kind = next((a["kind"] for a in analyzed if a["name"] == meta["name"]), "file")
            project["attachments"].append({"name": name, "size": meta["size"], "kind": kind})
        for meta in uploads:
            st.delete_upload(meta["id"])
        project["versions"].append({
            "n": n, "created": now_iso(), "source": "ai", "prompt": prompt, "summary": summary,
            "provider": f"{pid}:{self.provider.model}", "warnings": self.warnings[:10],
        })
        project["current"] = n

        settings = st.get_settings()
        data = {
            "n": n, "world": world, "characters": world_chars, "brief": brief, "plan": plan, "review": review,
            "prompt": prompt, "digest": digest, "worldbuilding": wb_payload, "content_mode": self.gen.get("content", "free"),
            "agent_logs": self.logs,
            "chat": {k: settings["characters"].get(k) for k in ("temperature", "max_tokens", "history_turns", "memory_limit")},
            "audio_files": [(a["name"], adir / a["name"]) for a in project["attachments"] if a["kind"] == "audio"],
            "attachment_files": [(a["name"], adir / a["name"]) for a in project["attachments"]],
        }
        builder.build_package(st, project, data)
        st.save_project(project)
        self._step("package", "done", version=n)
        result = {
            "type": "done", "project_id": project["id"], "version": n, "title": project["name"],
            "description": project.get("description", ""), "tags": project["tags"]["auto"] + project["tags"]["custom"],
            "warnings": self.warnings, "approved": review.get("approved", True),
        }
        self.emit(result)
        return project


# --------------------------------------------------------------------------- utilitários


def _slug_id(need: Dict[str, Any]) -> str:
    return slugify(need.get("id") or need.get("name", "npc"), "npc")


def _world_summary(world: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not world:
        return None
    env = world["environment"]
    return {
        "title": world["title"], "biome": env["biome"], "size": env["size"], "weather": env["weather"],
        "time_of_day": env["time_of_day"], "structure_count": len(world["structures"]), "npc_count": len(world["npcs"]),
        "structure_labels": [s["label"] for s in world["structures"] if s.get("label")][:30],
    }


def _audio_names(project: Optional[Dict[str, Any]], analyzed: List[Dict[str, Any]]) -> List[str]:
    names = [a["name"] for a in analyzed if a["kind"] == "audio"]
    if project:
        names += [a["name"] for a in project.get("attachments", []) if a["kind"] == "audio"]
    return list(dict.fromkeys(names))


# --------------------------------------------------------------------------- edição sem IA


def create_edit_version(store: Store, project_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica edições manuais (aba Mundos) e gera uma nova versão sem chamar a IA."""
    project = store.get_project(project_id)
    cur = store.load_version(project_id) if project else None
    if not project or not cur:
        raise ValueError("Projeto não encontrado")
    world = json.loads(json.dumps(cur["world"]))
    chars = json.loads(json.dumps(cur["characters"]))
    for key in ("title", "description", "perspective", "realism"):
        if key in patch:
            world[key] = patch[key]
    for key in ("environment", "audio", "ux", "gameplay"):
        if isinstance(patch.get(key), dict):
            for k, v in patch[key].items():
                if isinstance(v, dict) and isinstance(world.get(key, {}).get(k), dict):
                    world[key][k].update(v)
                else:
                    world.setdefault(key, {})[k] = v
    if isinstance(patch.get("quality"), dict):
        world["quality"]["target"] = patch["quality"].get("target", world["quality"].get("target"))
    if isinstance(patch.get("npcs"), list):
        edits = {n.get("id"): n for n in patch["npcs"] if isinstance(n, dict)}
        for npc in world["npcs"]:
            e = edits.get(npc["id"])
            if e:
                for k in ("behavior", "radius", "x", "z"):
                    if k in e:
                        npc[k] = e[k]
    if isinstance(patch.get("characters"), dict):  # trocar o card de um personagem por um da biblioteca
        for cid, source_id in patch["characters"].items():
            card = store.characters.get(source_id)
            for i, c in enumerate(chars):
                if c["id"] == cid and card:
                    chars[i] = dict(card, id=cid, source_id=card["id"])
    settings = store.get_settings()
    tier = world.get("quality", {}).get("generated_for") or hardware_info()["tier"]
    gen = dict(settings["generation"])
    gen["quality"] = patch.get("quality", {}).get("target") if isinstance(patch.get("quality"), dict) else world["quality"].get("target", "auto")
    audio_files = [a["name"] for a in project.get("attachments", []) if a["kind"] == "audio"]
    world = normalize_world(world, tier, gen, [c["id"] for c in chars], audio_files, default_title=project["name"])
    n = int(project["current"]) + 1
    summary = text(patch.get("_summary"), "Ajustes manuais nas configurações do mundo.", 200)
    project["versions"].append({"n": n, "created": now_iso(), "source": "edit", "prompt": "", "summary": summary})
    project["current"] = n
    if "title" in patch:
        project["name"] = world["title"]
    project["description"] = world.get("description", project.get("description", ""))
    project["palette"] = palette_for(world)
    wb_id = project.get("worldbuilding_id")
    wb = store.worldbuildings.get(wb_id) if wb_id else None
    prev_pkg = store.version_dir(project_id, n - 1) / "package" / "prompts"
    data = {
        "n": n, "world": world, "characters": chars, "brief": cur.get("brief"), "plan": cur.get("plan"), "review": cur.get("review"),
        "prompt": None, "digest": None, "worldbuilding": {"name": wb["name"], "system_prompt": wb["system_prompt"]} if wb else None,
        "content_mode": project.get("settings", {}).get("content", "free"), "agent_logs": [], "copy_prompts_from": prev_pkg,
        "chat": {k: settings["characters"].get(k) for k in ("temperature", "max_tokens", "history_turns", "memory_limit")},
        "audio_files": [(a["name"], store.project_dir(project_id) / "attachments" / a["name"]) for a in project["attachments"] if a["kind"] == "audio"],
    }
    # preserva o worldbuilding do pacote anterior caso o card tenha sido apagado
    if not data["worldbuilding"]:
        old = store.version_dir(project_id, n - 1) / "package" / "code" / "world.data.js"
        try:
            m = re.search(r"window\.ASTA_META=(\{.*\});", old.read_text("utf-8"))
            if m:
                data["worldbuilding"] = json.loads(m.group(1)).get("worldbuilding")
        except (OSError, ValueError):
            pass
    builder.build_package(store, project, data)
    store.save_project(project)
    return project
