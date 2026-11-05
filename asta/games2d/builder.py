"""Monta o pacote do jogo 2D (pasta + ZIP) a partir do spec validado.

    Game.html            abra no navegador (funciona via file:// e via ASTA)
    README.md  CHANGELOG.md
    code/                motor 2D (HTML5 canvas, JS puro): common.js + o motor do gênero + main.js
    data/                game.js (o jogo como dados) e game.json
    ui/theme.css         estilo da interface
    prompts/             seu pedido, anexos e o registro de cada agente
"""
from __future__ import annotations

import html
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from .. import __version__
from ..builder import changelog_text, js_data
from ..util import now_iso, safe_filename, slugify
from . import GENRES

RUNTIME2D = Path(__file__).parent.parent / "runtime2d"
ENGINES = {"visual_novel": "vn.js", "rpg": "rpg.js", "platformer": "platformer.js", "side_scroller": "sidescroller.js", "point_and_click": "adventure.js"}
CONTROLS = {
    "visual_novel": ("Clique, **Espaço** ou **Enter** avança · **A** liga o modo automático · **Ctrl** pula texto já lido · **H** histórico · **S** salva · **L** carrega.",
                     "Click, **Space** or **Enter** to advance · **A** auto mode · **Ctrl** skips read text · **H** history · **S** save · **L** load."),
    "rpg": ("**Setas/WASD** movem · **Espaço/Enter** interage e confirma · **Esc/X** abre o menu e volta · toque na tela no celular.",
            "**Arrows/WASD** move · **Space/Enter** interact and confirm · **Esc/X** menu and back · touch controls on phones."),
    "platformer": ("**Setas/A-D** movem · **Espaço/W/↑** pula (segure para pular mais alto) · **R** reinicia a fase · botões na tela no celular.",
                   "**Arrows/A-D** move · **Space/W/↑** jump (hold to jump higher) · **R** restart the level · on-screen buttons on phones."),
    "side_scroller": ("**Setas/WASD** movem · **Espaço** atira (shooter) ou pula (runner) · **↓/S** desliza (runner) · botões na tela no celular.",
                      "**Arrows/WASD** move · **Space** shoots (shooter) or jumps (runner) · **Down/S** slides (runner) · on-screen buttons on phones."),
    "point_and_click": ("Clique/toque nos objetos para Olhar, Pegar, Usar ou Falar · selecione um item do inventário e clique em um objeto para usá-lo nele.",
                        "Click/tap objects to Look, Take, Use or Talk · select an inventory item and click an object to use it on it."),
}


def _readme(project: Dict[str, Any], data: Dict[str, Any]) -> str:
    spec = data["game"]
    pt = str(spec.get("language", "pt")).lower().startswith("pt")
    g = GENRES[spec["genre"]]
    ctl = CONTROLS[spec["genre"]][0 if pt else 1]
    lines = [
        f"# {spec['title']}", "", spec.get("description") or "", "",
        "> Jogo gerado com [ASTA](https://github.com/KMC1525/ASTA) — central open source de criação de conteúdo criativo com IA." if pt else
        "> Game generated with [ASTA](https://github.com/KMC1525/ASTA) — open source creative content hub.", "",
        f"**{'Gênero' if pt else 'Genre'}:** {g['label']}", "",
        "## Como jogar" if pt else "## How to play", "",
        "1. Abra `Game.html` no navegador (Chrome, Edge, Firefox ou Safari recentes). Não precisa de servidor nem de instalação." if pt
        else "1. Open `Game.html` in a browser (recent Chrome, Edge, Firefox or Safari). No server or install needed.",
        f"2. {ctl}", "",
        "## Estrutura" if pt else "## Structure", "", "```", "Game.html   code/   data/   ui/   prompts/", "```", "",
        "- `code/` motor 2D em HTML5 canvas (JavaScript puro, sem dependências)." if pt else "- `code/` 2D engine on HTML5 canvas (plain JavaScript, no dependencies).",
        "- `data/` o jogo como dados (`game.json`): você pode editar textos, mapas e fases à mão." if pt else "- `data/` the game as data (`game.json`): you can hand-edit texts, maps and levels.",
        "- `prompts/` seu pedido original e o registro de cada agente de IA." if pt else "- `prompts/` your original request and every AI agent's log.", "",
        "Veja o [CHANGELOG](CHANGELOG.md) para o histórico de versões." if pt else "See the [CHANGELOG](CHANGELOG.md) for the version history.", "",
    ]
    return "\n".join(lines)


def build_game_package(store, project: Dict[str, Any], data: Dict[str, Any]) -> Path:
    """Escreve v<N>/package e v<N>/game.zip. `data`: n, game, brief, review, prompt, digest, agent_logs, attachment_files."""
    n = int(data["n"])
    spec = data["game"]
    genre = spec["genre"]
    vdir = store.version_dir(project["id"], n)
    pkg = vdir / "package"
    if pkg.exists():
        shutil.rmtree(pkg)
    for sub in ("code", "data", "ui", "prompts/agents"):
        (pkg / sub).mkdir(parents=True, exist_ok=True)
    meta = {"id": project["id"], "name": project["name"], "version": n, "asta_version": __version__, "generated": now_iso(), "tags": project["tags"]["auto"] + project["tags"]["custom"]}

    for fname in ("common.js", ENGINES[genre], "main.js"):
        src = RUNTIME2D / fname
        if not src.exists():
            raise ValueError(f"Motor 2D incompleto: falta {fname}")
        shutil.copyfile(src, pkg / "code" / fname)
    (pkg / "code" / "config.js").write_text(js_data("ASTA_CONFIG", {"mode": "standalone", "project": project["id"], "version": n}), "utf-8")
    (pkg / "data" / "game.js").write_text(js_data("ASTA_GAME", spec) + js_data("ASTA_META", meta), "utf-8")
    (pkg / "data" / "game.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), "utf-8")
    (pkg / "ui" / "theme.css").write_text((RUNTIME2D / "game.css").read_text("utf-8"), "utf-8")

    prompts = pkg / "prompts"
    if data.get("prompt") is not None:
        (prompts / "prompt.md").write_text(f"# Prompt\n\n{data['prompt']}\n", "utf-8")
    if data.get("digest") is not None:
        (prompts / "attachments.md").write_text(f"# Anexos\n\n{data['digest'] or '(nenhum)'}\n", "utf-8")
    for fname, text_ in data.get("agent_logs", []):
        (prompts / "agents" / safe_filename(fname)).write_text(text_, "utf-8")
    kept = [(nm, p) for nm, p in data.get("attachment_files", []) if Path(p).exists()]
    total = 0
    if kept:
        (prompts / "attachments").mkdir(exist_ok=True)
    for nm, p in kept:
        size = Path(p).stat().st_size
        if total + size > 20 * 1024 * 1024:
            continue
        total += size
        shutil.copyfile(p, prompts / "attachments" / safe_filename(nm))

    page = (RUNTIME2D / "game.html").read_text("utf-8")
    page = page.replace("{{TITLE}}", html.escape(spec["title"])).replace("{{LANG}}", html.escape(spec.get("language", "pt-BR"))).replace("{{ENGINE}}", ENGINES[genre])
    (pkg / "Game.html").write_text(page, "utf-8")
    (pkg / "README.md").write_text(_readme(project, data), "utf-8")
    (pkg / "CHANGELOG.md").write_text(changelog_text(project), "utf-8")

    for key, obj in (("game", spec), ("brief", data.get("brief")), ("review", data.get("review"))):
        (vdir / f"{key}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), "utf-8")
    zip_path = vdir / "game.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file in sorted(pkg.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(pkg).as_posix())
    return zip_path


def rebuild_game(store, project_id: str, summary: str) -> Dict[str, Any]:
    """Nova versão do mesmo jogo com o motor 2D mais recente (sem chamar a IA)."""
    project = store.get_project(project_id)
    cur = store.load_game_version(project_id) if project and project.get("kind") == "game2d" else None
    if not project or not cur:
        raise ValueError("Projeto não encontrado")
    n = int(project["current"]) + 1
    project["versions"].append({"n": n, "created": now_iso(), "source": "edit", "prompt": "", "summary": summary})
    project["current"] = n
    prev = store.version_dir(project_id, n - 1) / "package" / "prompts"
    build_game_package(store, project, {"n": n, "game": cur["game"], "brief": cur.get("brief"), "review": cur.get("review"), "prompt": None, "digest": None,
                                        "agent_logs": [], "attachment_files": []})
    if prev.exists():  # preserva o registro de prompts/agentes da versão anterior
        shutil.copytree(prev, store.version_dir(project_id, n) / "package" / "prompts", dirs_exist_ok=True)
    store.save_project(project)
    return project
