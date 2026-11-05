"""Pipeline do Rebuild: Arquivos → Leitura → Reconstrução → Validação → Empacotamento (sem IA: é uma conversão determinística)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from ..games2d import GENRES
from ..games2d import schema as S
from ..games2d.builder import build_game_package
from ..storage import Store
from ..util import now_iso, text
from . import NOTICE_EN, NOTICE_PT, Source, SourceError, rebuild_source

STEPS = ["attachments", "analyst", "designer", "reviewer", "package"]


class RebuildPipeline:
    def __init__(self, store: Store, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False):
        self.store, self.emit, self.cancelled = store, emit, cancelled
        self.warnings: List[str] = []

    def _step(self, sid: str, status: str, **detail: Any) -> None:
        self.emit({"type": "step", "id": sid, "status": status, "detail": detail})

    def _check(self) -> None:
        if self.cancelled():
            raise ValueError("cancelado")

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
        project["rebuild"] = {"engine": info["engine"], "engine_name": info["engine_name"], "source": [m["name"] for m in uploads][:5], "when": now_iso()}
        project["versions"].append({"n": 1, "created": now_iso(), "source": "rebuild", "prompt": f"Rebuild · {info['engine_name']}", "summary": summary, "provider": "rebuild", "warnings": self.warnings[:10]})
        project["current"] = 1
        build_game_package(st, project, {"n": 1, "game": spec, "brief": {"rebuild": info, "title": spec["title"], "language": spec["language"], "genre": genre}, "review": review,
                                         "prompt": f"Rebuild · {info['engine_name']} · " + ", ".join(m["name"] for m in uploads), "digest": "", "agent_logs": [("01-rebuild.md", "# Rebuild\n\n" + "\n".join(f"- {w}" for w in self.warnings) + "\n")],
                                         "attachment_files": []})
        for meta in uploads:  # o jogo original não fica guardado no ASTA
            st.delete_upload(meta["id"])
        st.save_project(project)
        self._step("package", "done", version=1)
        result = {"type": "done", "project_id": project["id"], "version": 1, "title": project["name"], "genre": genre, "description": summary, "tags": project["tags"]["auto"],
                  "warnings": self.warnings[:30], "approved": not problems, "rebuild": project["rebuild"], "notice": {"pt": NOTICE_PT, "en": NOTICE_EN}}
        self.emit(result)
        return project
