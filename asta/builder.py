"""Monta o pacote do jogo (pasta + ZIP) a partir do spec gerado pelos agentes.

Estrutura do ZIP:

    Game.html                 abra no navegador (funciona via file:// e via ASTA)
    README.md  CHANGELOG.md   documentação e histórico de versões deste mundo
    code/                     motor 3D (three.js) + dados do mundo
    chars/                    cards dos personagens/NPCs (.json) + chars.js
    sound/                    áudio procedural (sound.json) + trilhas anexadas
    prompts/                  prompt original, anexos e registro de cada agente
    ui/ux/                    tema e configuração da interface do jogo
"""
from __future__ import annotations

import html
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from .util import now_iso, safe_filename, slugify

RUNTIME = Path(__file__).parent / "runtime"
CODE_FILES = ["core.js", "scene.js", "actors.js", "audio.js", "agent.js", "main.js"]


def js_data(var: str, obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    raw = raw.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return f"window.{var}={raw};\n"


def theme_css(ux: Dict[str, Any]) -> str:
    theme = ux.get("theme", {})
    css_vars = (
        ":root{"
        f"--bg:{theme.get('bg', '#000000')};--text:{theme.get('text', '#ececec')};--accent:{theme.get('accent', '#ffffff')};"
        "}\n"
    )
    return css_vars + (RUNTIME / "game.css").read_text("utf-8")


def _readme(project: Dict[str, Any], data: Dict[str, Any]) -> str:
    world = data["world"]
    chars = data["characters"]
    env = world["environment"]
    lines = [
        f"# {world['title']}",
        "",
        world.get("description") or "",
        "",
        "> Mundo gerado com [ASTA](https://github.com/KMC1525/ASTA) — mundos virtuais jogáveis com personagens de IA.",
        "",
        "## Como jogar",
        "",
        "1. Abra `Game.html` no navegador (Chrome, Edge, Firefox ou Safari recentes).",
        "2. Clique na tela para capturar o mouse. **WASD** move, **Shift** corre, **Espaço** pula, **V** alterna 1ª/3ª pessoa,",
        "   **E** (ou clique) conversa com o personagem à frente, **M** mostra/oculta o minimapa, **Esc** libera o mouse.",
        "3. Para conversar com os personagens, rode o mundo pelo ASTA (botão *Jogar*) — ele usa os provedores que você configurou —",
        "   ou, abrindo o `Game.html` direto, informe um endpoint de IA em **⚙ Configurações do jogo** (guardado só no seu navegador).",
        "",
        "## Mundo",
        "",
        f"- Bioma: **{env['biome']}** · tamanho: **{env['size']} m** · clima: **{env['weather']}** · hora inicial: **{env['time_of_day']}h**",
        f"- Perspectiva inicial: **{'primeira' if world['perspective'] == 'first' else 'terceira'} pessoa**",
        f"- {len(world['structures'])} estruturas · {len(world['npcs'])} NPCs",
        "",
        "## Personagens",
        "",
    ]
    for c in chars:
        lines.append(f"- **{c['name']}** ({'jogador' if c.get('role') == 'player' else 'NPC'}) — {', '.join(c.get('tags') or []) or 'sem tags'}")
    lines += [
        "",
        "## Estrutura",
        "",
        "```",
        "Game.html   code/   chars/   sound/   prompts/   ui/ux/",
        "```",
        "",
        "- `code/` motor 3D (three.js r159, MIT) e dados do mundo — o jogo se adapta ao hardware (qualidade dinâmica).",
        "- `chars/` cards dos personagens (nome, tags, system prompt, voz).",
        "- `sound/` áudio procedural e trilhas anexadas.",
        "- `prompts/` seu prompt original, anexos e o raciocínio de cada agente.",
        "- `ui/ux/` tema e configuração da interface.",
        "",
        "Veja o [CHANGELOG](CHANGELOG.md) para o histórico de versões.",
        "",
    ]
    return "\n".join(lines)


def changelog_text(project: Dict[str, Any]) -> str:
    lines = ["# Changelog", "", f"Histórico de versões de **{project['name']}**. A versão mais recente aparece primeiro.", ""]
    for v in sorted(project.get("versions", []), key=lambda x: x["n"], reverse=True):
        kind = "atualização por IA" if v.get("source") == "ai" else "edição manual"
        if v["n"] == 1:
            kind = "criação"
        lines.append(f"## v{v['n']} — {v['created'][:10]} ({kind})")
        lines.append("")
        if v.get("prompt"):
            prompt = " ".join(str(v["prompt"]).split())
            lines.append(f"- Pedido: {prompt[:300]}{'…' if len(prompt) > 300 else ''}")
        if v.get("summary"):
            lines.append(f"- {v['summary']}")
        lines.append("")
    return "\n".join(lines)


def build_package(store, project: Dict[str, Any], data: Dict[str, Any]) -> Path:
    """Escreve v<N>/package e v<N>/world.zip. `data` traz world, characters, brief, plan, review, ..."""
    n = int(data["n"])
    vdir = store.version_dir(project["id"], n)
    pkg = vdir / "package"
    if pkg.exists():
        shutil.rmtree(pkg)
    for sub in ("code/vendor", "chars", "sound", "prompts/agents", "ui/ux"):
        (pkg / sub).mkdir(parents=True, exist_ok=True)

    world: Dict[str, Any] = data["world"]
    chars: List[Dict[str, Any]] = data["characters"]
    meta = {
        "id": project["id"], "name": project["name"], "version": n, "asta_version": __version__,
        "generated": now_iso(), "tags": project["tags"]["auto"] + project["tags"]["custom"],
        "content": data.get("content_mode", "free"),
        "worldbuilding": data.get("worldbuilding") or None,
        "chat": data.get("chat") or {},
    }

    # ---- código do motor
    for fname in CODE_FILES:
        shutil.copyfile(RUNTIME / fname, pkg / "code" / fname)
    shutil.copyfile(RUNTIME / "vendor" / "three.min.js", pkg / "code" / "vendor" / "three.min.js")
    shutil.copyfile(RUNTIME / "vendor" / "THREE_LICENSE.txt", pkg / "code" / "vendor" / "THREE_LICENSE.txt")
    (pkg / "code" / "config.js").write_text(
        js_data("ASTA_CONFIG", {"mode": "standalone", "project": project["id"], "version": n}), "utf-8")
    (pkg / "code" / "world.data.js").write_text(js_data("ASTA_WORLD", world) + js_data("ASTA_META", meta), "utf-8")

    # ---- personagens
    for c in chars:
        (pkg / "chars" / f"{safe_filename(c['id'])}.json").write_text(json.dumps(c, ensure_ascii=False, indent=2), "utf-8")
    (pkg / "chars" / "chars.js").write_text(js_data("ASTA_CHARS", chars), "utf-8")

    # ---- som
    sound = dict(world["audio"])
    (pkg / "sound" / "sound.json").write_text(json.dumps(sound, ensure_ascii=False, indent=2), "utf-8")
    (pkg / "sound" / "sound.js").write_text(js_data("ASTA_SOUND", sound), "utf-8")
    music_file = sound.get("music", {}).get("file")
    if music_file:
        for name, path in data.get("audio_files", []):
            if name == music_file and Path(path).exists():
                (pkg / "sound" / "user").mkdir(exist_ok=True)
                shutil.copyfile(path, pkg / "sound" / "user" / safe_filename(name))

    # ---- UI/UX
    ux = world["ux"]
    (pkg / "ui" / "ux" / "theme.css").write_text(theme_css(ux), "utf-8")
    (pkg / "ui" / "ux" / "ux.json").write_text(json.dumps(ux, ensure_ascii=False, indent=2), "utf-8")
    (pkg / "ui" / "ux" / "ux.js").write_text(js_data("ASTA_UX", ux), "utf-8")

    # ---- prompts (prompt original, anexos, registro dos agentes)
    prompts = pkg / "prompts"
    src_prompts: Optional[Path] = data.get("copy_prompts_from")
    if src_prompts and Path(src_prompts).exists():
        shutil.copytree(src_prompts, prompts, dirs_exist_ok=True)
    if data.get("prompt") is not None:
        (prompts / "prompt.md").write_text(f"# Prompt\n\n{data['prompt']}\n", "utf-8")
    if data.get("digest") is not None:
        (prompts / "attachments.md").write_text(f"# Anexos\n\n{data['digest'] or '(nenhum)'}\n", "utf-8")
    wb = data.get("worldbuilding")
    if wb:
        (prompts / "worldbuilding.md").write_text(f"# {wb.get('name', '')}\n\n{wb.get('system_prompt', '')}\n", "utf-8")
    for fname, text in data.get("agent_logs", []):
        (prompts / "agents" / safe_filename(fname)).write_text(text, "utf-8")
    for c in chars:
        (prompts / f"char-{safe_filename(c['id'])}.md").write_text(f"# {c['name']}\n\n{c.get('system_prompt', '')}\n", "utf-8")
    kept = [(nm, p) for nm, p in data.get("attachment_files", []) if Path(p).exists()]
    total = 0
    if kept:
        (prompts / "attachments").mkdir(exist_ok=True)
    for nm, p in kept:
        size = Path(p).stat().st_size
        if total + size > 20 * 1024 * 1024:
            continue  # evita ZIPs gigantes; o original continua na biblioteca do ASTA
        total += size
        shutil.copyfile(p, prompts / "attachments" / safe_filename(nm))

    # ---- raiz
    title = html.escape(world["title"])
    page = (RUNTIME / "game.html").read_text("utf-8")
    page = page.replace("{{TITLE}}", title).replace("{{LANG}}", html.escape(world.get("language", "pt-BR")))
    page = page.replace("{{BG}}", ux["theme"]["bg"])
    (pkg / "Game.html").write_text(page, "utf-8")
    (pkg / "README.md").write_text(_readme(project, data), "utf-8")
    (pkg / "CHANGELOG.md").write_text(changelog_text(project), "utf-8")

    # ---- cópia dos JSONs na pasta da versão (fonte de verdade p/ edição sem IA)
    for key, obj in (
        ("world", world), ("characters", chars), ("sound", sound), ("ux", ux),
        ("brief", data.get("brief")), ("plan", data.get("plan")), ("review", data.get("review")),
    ):
        (vdir / f"{key}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), "utf-8")

    # ---- ZIP
    zip_path = vdir / "world.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file in sorted(pkg.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(pkg).as_posix())
    return zip_path


def zip_name(project: Dict[str, Any], n: int) -> Tuple[str, str]:
    return f"{slugify(project['name'], 'mundo')}-v{n}.zip", "application/zip"
