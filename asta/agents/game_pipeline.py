"""Pipeline multi-agentes que cria (e atualiza) jogos 2D: Anexos → Analista → Designer → Revisor → Empacotador."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from .. import attachments as att
from .. import voice
from ..games2d import GENRES
from ..games2d import schema as S
from ..games2d.builder import build_game_package
from ..providers import build_provider
from ..storage import Store
from ..util import now_iso, safe_filename, text
from . import prompts, prompts_game as P
from . import rulebased_games as rb
from .runner import Runner

STEPS = ["attachments", "analyst", "designer", "reviewer", "package"]


def game_summary(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Resumo compacto do jogo (o Revisor não precisa dos mapas inteiros)."""
    d, g = spec["data"], spec["genre"]
    base = {"genre": g, "title": spec["title"], "theme": spec["style"]["theme"]}
    if g == "visual_novel":
        ends = [s["title"] for stmts in d["labels"].values() for s in stmts if s["c"] == "end"]
        return {**base, "characters": [c["name"] for c in d["characters"]], "labels": list(d["labels"]), "variables": d["variables"], "endings": ends,
                "choices": sum(1 for stmts in d["labels"].values() for s in stmts if s["c"] == "menu"), "lines": sum(len(v) for v in d["labels"].values())}
    if g == "rpg":
        return {**base, "party": [p["name"] for p in d["party"]], "maps": {m["id"]: {"events": [f"{e['kind']}:{e['name'] or e['id']}" for e in m["events"]], "size": f"{len(m['tiles'][0])}x{len(m['tiles'])}"} for m in d["maps"].values()},
                "enemies": list(d["enemies"]), "items": list(d["items"])}
    if g == "platformer":
        return {**base, "levels": [{"name": lv["name"], "width": len(lv["tiles"][0]), "height": len(lv["tiles"]), "enemies": sum(r.count("E") + r.count("B") + r.count("J") for r in lv["tiles"]),
                                    "coins": sum(r.count("C") for r in lv["tiles"])} for lv in d["levels"]]}
    if g == "side_scroller":
        return {**base, "mode": d["mode"], "stages": [{"name": s["name"], "length": s["length"], "waves": len(s["waves"]), "obstacles": len(s["obstacles"]), "boss": bool(s["boss"])} for s in d["stages"]]}
    return {**base, "scenes": {k: {"hotspots": [h["name"] or h["id"] for h in s["hotspots"]]} for k, s in d["scenes"].items()}, "items": list(d["items"])}


class GamePipeline(Runner):
    domain = "game2d"

    def __init__(self, store: Store, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False):
        super().__init__(store, emit, cancelled)

    def run(self, req: Dict[str, Any]) -> Dict[str, Any]:
        st = self.store
        settings = st.get_settings()
        gcfg = settings["games"]
        content = "sfw" if req.get("content", settings["generation"].get("content")) == "sfw" else "free"
        length = req.get("length") if req.get("length") in S.LENGTHS else gcfg.get("length", "medium")
        want = req.get("genre") if req.get("genre") in S.GENRE_IDS else "auto"
        self.gen = {"temperature": gcfg.get("temperature", 0.8), "max_tokens": int(gcfg.get("max_tokens", 9000)), "content": content}
        pid = settings["active"].get("generation", "demo")
        self.provider = build_provider(settings, pid, st.models_dir)
        self.configure_team(gcfg, req, pid)   # equipe: agentes em paralelo + esforço (settings.games / pedido)
        prompt = str(req.get("prompt") or "").strip()
        project = st.get_project(req["project_id"]) if req.get("project_id") else None
        if req.get("project_id") and (not project or project.get("kind") != "game2d"):
            raise ValueError("Projeto não encontrado")
        previous = st.load_game_version(project["id"]) if project else None
        self.emit({"type": "start", "steps": STEPS, "provider": pid, "model": self.provider.model, "update": bool(project), "genre": want})

        # ---------- anexos
        self._step("attachments", "running")
        uploads = st.get_uploads(req.get("attachment_ids") or [])   # pacotes (ZIP, RAR…) já vêm abertos: cada arquivo de dentro é um anexo
        analyzed: List[Dict[str, Any]] = []
        transcribe = voice.transcriber(settings)
        for meta in uploads:
            self._check()
            analyzed.append(att.analyze(Path(meta["path"]), meta["name"], meta.get("mime", ""), transcribe=transcribe))
        digest = att.build_digest(analyzed)
        images = att.collect_images(analyzed)
        self._step("attachments", "done" if uploads else "skipped", count=len(uploads), images=len(images))
        if not prompt and not digest and not previous:
            raise ValueError("Descreva o jogo que você quer criar (ou anexe algo) para gerá-lo.")

        # ---------- 1. Analista
        prev_spec = previous["game"] if previous else None
        genre_locked = prev_spec["genre"] if prev_spec else want
        brief, fb = self._agent(
            "analyst", "game_analyst", P.ANALYST,
            {"prompt": prompt, "attachments_digest": digest, "genre": genre_locked, "length": length, "language_hint": text(req.get("language"), "", 12),
             "previous": ({"title": prev_spec["title"], "summary": game_summary(prev_spec)} if prev_spec else None)},
            rb.analyst, images=images,
        )
        # gênero: atualização mantém o do jogo; escolha explícita do usuário vence; senão o do Analista (ou detectado por regras)
        if prev_spec:
            brief["genre"] = prev_spec["genre"]
        elif want != "auto":
            brief["genre"] = want
        elif brief.get("genre") not in S.GENRE_IDS:
            brief["genre"] = rb.analyst({"prompt": prompt, "attachments_digest": digest})["genre"]
        brief["title"] = text(brief.get("title"), "", 80) or (prev_spec["title"] if prev_spec else rb.analyst({"prompt": prompt})["title"])
        brief["language"] = text(brief.get("language"), "pt-BR", 12)
        brief["length"] = length
        self.language = prompts.lang_name(brief["language"])
        genre = brief["genre"]
        self._step("analyst", "warn" if fb else "done", genre=genre, title=brief["title"])

        # ---------- 2. Designer
        payload = {"brief": brief, "length": length, "sizes": S.LENGTH[length], "previous_game": prev_spec, "attachments_digest": digest[:6000], "request": prompt[:3000]}
        mult = {"short": 0.8, "medium": 1.0, "long": 1.7}[length]
        spec, fb = self._design(genre, payload, mult, brief, None)
        self._step("designer", "warn" if fb else "done", genre=genre)

        # ---------- 3. Revisor (+ rodadas de correção)
        review = self._review(spec, brief, prompt)
        rounds = self.team.revisions(int(gcfg.get("revisions", 1)))
        for r in range(rounds):
            issues = [i for i in (review.get("issues") or []) if isinstance(i, dict)]
            if review.get("approved", True) or not issues:
                break
            self.emit({"type": "revision", "round": r + 1, "issues": len(issues)})
            fb_text = "\n".join(f"- [{i.get('area')}] {i.get('problem')} → {i.get('fix')}" for i in issues)[:3000]
            spec, _ = self._design(genre, payload, mult, brief, fb_text, keep=spec)
            self._step("designer", "done", genre=genre, revision=True)
            review = self._review(spec, brief, prompt)
        if not review.get("approved", True):
            self.warnings.append("reviewer: not approved after revisions")

        # ---------- 4. Empacotador
        return self._package(req, project, prompt, digest, analyzed, uploads, brief, spec, review, pid)

    # ------------------------------------------------------------------ etapas
    def _design(self, genre, payload, mult, brief, feedback, keep=None) -> Tuple[Dict[str, Any], bool]:
        instruction = P.designer_instruction(genre) + (("\n\nFEEDBACK TO FIX:\n" + feedback) if feedback else "")
        raw, fb = self._agent("designer", "game_designer", instruction, {**payload, "feedback": feedback}, rb.designer, tokens_mult=mult, feedback=bool(feedback))
        spec, warns = S.normalize_game(raw, genre, brief["language"], brief["title"])
        for w in warns[:6]:
            self.warnings.append(f"designer: {w}")
        if S.is_trivial(spec):
            self.warnings.append("designer: jogo vazio/inválido → gerado pelo gerador de regras")
            spec, _ = S.normalize_game(rb.designer({"brief": brief}), genre, brief["language"], brief["title"])
            fb = True
        elif keep is not None and S.game_problems(spec) and not S.game_problems(keep):
            spec = keep  # a correção piorou o jogo: mantém a versão anterior
        spec["title"] = text(spec.get("title"), brief["title"], 80)
        return spec, fb

    def _review(self, spec, brief, prompt) -> Dict[str, Any]:
        problems = S.game_problems(spec)
        payload = {"request": prompt[:1500], "brief": {k: brief.get(k) for k in ("genre", "title", "premise", "language", "theme")}, "game": game_summary(spec), "problems": problems}
        review, fb = self._agent("reviewer", "game_reviewer", P.REVIEWER, payload, rb.reviewer)
        review["approved"] = bool(review.get("approved", True)) and not problems
        if problems and not review.get("issues"):
            review["issues"] = [{"area": "game", "severity": "high", "problem": p, "fix": "corrigir"} for p in problems]
        self._step("reviewer", "warn" if fb else "done", approved=review["approved"], score=review.get("score"), issues=len(review.get("issues") or []))
        return review

    def _package(self, req, project, prompt, digest, analyzed, uploads, brief, spec, review, pid) -> Dict[str, Any]:
        self._check()
        self._step("package", "running")
        st = self.store
        genre = spec["genre"]
        tags = [GENRES[genre]["label"].lower(), spec["style"]["theme"]] + [text(t, "", 30).lower() for t in (brief.get("tags") or [])]
        tags = list(dict.fromkeys(t for t in tags if t))[:10]
        summary = text(spec.get("description"), "", 240) or text(brief.get("premise"), "", 240)
        if project is None:
            project = st.create_project(spec["title"], kind="game2d", genre=genre, description=summary)
        else:
            project["description"] = summary or project.get("description", "")
            project["name"] = spec["title"]
        n = int(project.get("current") or 0) + 1
        project["genre"] = genre
        project["tags"]["auto"] = tags if n == 1 else list(dict.fromkeys(tags + project["tags"].get("auto", [])))[:12]
        project["palette"] = S.palette_for_game(spec)
        project["language"] = spec["language"]
        project["settings"] = {"length": brief.get("length", "medium"), "content": self.gen.get("content", "free")}
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
        project["versions"].append({"n": n, "created": now_iso(), "source": "ai", "prompt": prompt, "summary": summary, "provider": f"{pid}:{self.provider.model}",
                                    "warnings": self.warnings[:10]})
        project["current"] = n
        build_game_package(st, project, {"n": n, "game": spec, "brief": brief, "review": review, "prompt": prompt, "digest": digest, "agent_logs": self.logs,
                                         "attachment_files": [(a["name"], adir / a["name"]) for a in project["attachments"]]})
        st.save_project(project)
        self._step("package", "done", version=n)
        result = {"type": "done", "project_id": project["id"], "version": n, "title": project["name"], "genre": genre, "description": project.get("description", ""),
                  "tags": project["tags"]["auto"] + project["tags"]["custom"], "warnings": self.warnings, "approved": review.get("approved", True)}
        self.emit(result)
        return project
