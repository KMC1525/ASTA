"""Pipeline do Rebuild: Arquivos → Leitura → Reconstrução → [Perfilador → Polidor → Auditor, com IA] → Validação → Empacotamento.

A conversão é determinística (é ela que mantém a estrutura igual à do original). A camada de IA (`refine.py`) é opcional e só mexe em texto; sem provedor de IA
configurado (modo Demo) ou com `refine: false`, essas etapas são puladas."""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from ..games2d import GENRES
from ..games2d import schema as S
from ..games2d.builder import build_game_package
from ..agents import prompts
from ..agents.runner import Cancelled, Runner
from ..providers import build_provider
from ..storage import Store
from ..util import now_iso, text
from . import NOTICE_EN, NOTICE_PT, Source, SourceError, rebuild_source
from . import refine as R

STEPS = ["attachments", "analyst", "designer", "profiler", "polisher", "auditor", "reviewer", "package"]


class RebuildPipeline(Runner):
    domain = "game2d"

    def __init__(self, store: Store, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False):
        super().__init__(store, emit, cancelled)

    def _refine(self, spec: Dict[str, Any], info: Dict[str, Any], want: bool) -> Dict[str, Any]:
        """Perfilador → Polidor → Auditor (IA, só texto). Devolve o resumo do que foi feito ({} se pulou)."""
        skip = [s for s in ("profiler", "polisher", "auditor")]
        settings = self.store.get_settings()
        pid = settings["active"].get("generation", "demo")
        if not want or pid == "demo":
            for s in skip:
                self._step(s, "skipped")
            if want:
                self.warnings.append("ia: nenhum provedor de IA configurado — o texto só passou pela limpeza automática (sem revisão por IA)")
            n = R.clean_only(spec)
            return {"cleaned": n, "calls": 0} if n else {}
        self.provider = build_provider(settings, pid, self.store.models_dir)
        self.gen = {"temperature": 0.2, "max_tokens": 1800, "content": "free"}
        self.language = prompts.lang_name(spec.get("language") or "pt-BR")
        ref = R.Refiner(self._agent, self._step, self._check, self.warnings.append)
        try:
            stats = ref.run(spec, info)
        except Exception as exc:  # noqa: BLE001  (o modelo caiu/credencial: a conversão determinística já está pronta e segue)
            if isinstance(exc, Cancelled):
                raise
            self.warnings.append(f"ia: o refinamento foi interrompido ({str(exc)[:160]}); ficou o resultado determinístico")
            for s in skip:
                self._step(s, "skipped")
            return {}
        stats["provider"] = f"{pid}:{self.provider.model}"
        return stats

    def run(self, req: Dict[str, Any]) -> Dict[str, Any]:
        st = self.store
        self.emit({"type": "start", "steps": STEPS, "kind": "rebuild"})
        self._step("attachments", "running")
        uploads = [m for m in (st.get_upload(u) for u in (req.get("attachment_ids") or [])[:40]) if m]
        if not uploads:
            raise ValueError("Anexe o ZIP do jogo (ou os arquivos de dados/scripts) para reconstruí-lo.")
        src = Source.from_uploads(uploads)
        stem = str(uploads[0]["name"]).rsplit(".", 1)[0] if uploads else ""
        self._step("attachments", "done", count=len(src.names()))
        self._check()

        self._step("analyst", "running")
        try:
            raw, genre, warns, info = rebuild_source(src, title_hint=stem)
        except SourceError as exc:
            raise ValueError(str(exc)) from None
        self.warnings.extend(warns)
        self._step("analyst", "done", engine=info["engine_name"], title=info.get("title") or stem, count=info.get("maps") or info.get("labels") or 0)
        self._check()

        self._step("designer", "running")
        lang = raw.get("language") or "pt-BR"
        spec, nwarns = S.normalize_game(raw, genre, lang, raw.get("title") or stem or "Jogo reconstruído")
        self.warnings.extend(f"rebuild: {w}" for w in nwarns[:10])
        self.warnings.extend(raw.get("_warnings") or [])
        if S.is_trivial(spec):
            raise ValueError("Não encontrei conteúdo jogável (mapas, eventos ou roteiro) nesse jogo.")
        spec["title"] = text(spec.get("title"), raw.get("title") or stem, 80)
        self._step("designer", "done", genre=genre)
        refined = self._refine(spec, info, req.get("refine", True) is not False)
        self._check()

        problems = S.game_problems(spec)
        review = {"approved": not problems, "score": None, "summary": "Validação automática da reconstrução.", "issues": [{"area": "game", "severity": "high", "problem": p, "fix": ""} for p in problems]}
        self._step("reviewer", "done" if not problems else "warn", approved=not problems, issues=len(problems))
        self.warnings.extend(f"validação: {p}" for p in problems)
        self._check()

        self._step("package", "running")
        label = GENRES[genre]["label"].lower()
        summary = f"Reconstruído de {info['engine_name']}: {spec['title']}"
        project = st.create_project(spec["title"], kind="game2d", genre=genre, description=summary)
        project["tags"]["auto"] = list(dict.fromkeys([label, "rebuild", info["engine"]]))
        project["palette"] = S.palette_for_game(spec)
        project["language"] = spec["language"]
        project["settings"] = {"length": "medium", "content": "free"}
        project["rebuild"] = {"engine": info["engine"], "engine_name": info["engine_name"], "refined": bool(refined), "source": [m["name"] for m in uploads][:5], "when": now_iso()}
        project["versions"].append({"n": 1, "created": now_iso(), "source": "rebuild", "prompt": f"Rebuild · {info['engine_name']}", "summary": summary, "provider": "rebuild", "warnings": self.warnings[:10]})
        project["current"] = 1
        build_game_package(st, project, {"n": 1, "game": spec, "brief": {"rebuild": info, "title": spec["title"], "language": spec["language"], "genre": genre}, "review": review,
                                         "prompt": f"Rebuild · {info['engine_name']} · " + ", ".join(m["name"] for m in uploads), "digest": "", "agent_logs": [("00-rebuild.md", "# Rebuild\n\n" + "\n".join(f"- {w}" for w in self.warnings) + "\n")] + self.logs,
                                         "attachment_files": []})
        for meta in uploads:  # o jogo original não fica guardado no ASTA
            st.delete_upload(meta["id"])
        st.save_project(project)
        self._step("package", "done", version=1)
        result = {"type": "done", "project_id": project["id"], "version": 1, "title": project["name"], "genre": genre, "description": summary, "tags": project["tags"]["auto"],
                  "warnings": self.warnings[:30], "approved": not problems, "rebuild": project["rebuild"], "refine": refined, "notice": {"pt": NOTICE_PT, "en": NOTICE_EN}}
        self.emit(result)
        return project
