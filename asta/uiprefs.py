"""Preferências de interface (aparência, atalhos, barra lateral, chat) — `settings.ui`.

Tudo que o usuário personaliza na tela vive aqui, validado: um valor inválido (por API ou edição manual) volta ao padrão em vez de quebrar a interface.
O padrão reproduz exatamente a aparência de sempre (tema escuro, cor de destaque branca, tamanho 100%).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

THEMES = ("dark", "light", "auto")  # auto = segue o sistema operacional
SCALES = (90, 100, 110, 125, 150)  # % da interface
DENSITIES = ("comfortable", "compact")
MOTIONS = ("auto", "reduce", "full")  # auto = respeita o sistema; reduce = sem animações; full = sempre animar
FONTS = ("system", "serif", "mono")
CHAT_SIZES = ("small", "medium", "large")
SEND_KEYS = ("enter", "ctrl_enter")  # enter: Enter envia (Shift+Enter quebra a linha) · ctrl_enter: Ctrl/⌘+Enter envia (Enter quebra a linha)
START_PAGES = ("last", "main", "engine", "scriber", "worlds", "avatars", "games", "canvas", "studio", "computer", "code", "work", "library")
HIDEABLE = ("engine", "scriber", "worlds", "avatars", "games", "canvas", "studio", "computer", "code", "work", "rebuild", "library")  # "Chat" e "Configuração" nunca somem da barra lateral
LANGS = ("auto", "pt-BR", "en")

DEFAULT_UI: Dict[str, Any] = {
    "theme": "dark",
    "accent": "",  # "" = padrão do tema (branco no escuro, quase preto no claro) · ou "#rrggbb"
    "scale": 100,
    "density": "comfortable",
    "motion": "auto",
    "font": "system",
    "chat_size": "medium",
    "send_key": "enter",
    "start_page": "main",
    "sidebar_hidden": [],
    "shortcuts": True,
    "welcome_done": False,
}

_HEX = re.compile(r"^#([0-9a-f]{3}|[0-9a-f]{6})$")


def _choice(value: Any, allowed: tuple, default: Any) -> Any:
    return value if isinstance(value, (str, int)) and not isinstance(value, bool) and value in allowed else default


def normalize_accent(value: Any) -> str:
    s = str(value or "").strip().lower()
    if not _HEX.match(s):
        return ""
    return "#" + "".join(c * 2 for c in s[1:]) if len(s) == 4 else s


def normalize_ui(data: Any) -> Dict[str, Any]:
    """Preferências válidas (todas as chaves presentes); o que for inválido volta ao padrão."""
    d = data if isinstance(data, dict) else {}
    try:
        scale = int(float(d.get("scale", 100)))
    except (TypeError, ValueError):
        scale = 100
    hidden: List[str] = []
    for x in d.get("sidebar_hidden") if isinstance(d.get("sidebar_hidden"), list) else []:
        if x in HIDEABLE and x not in hidden:
            hidden.append(x)
    return {
        "theme": _choice(d.get("theme"), THEMES, DEFAULT_UI["theme"]),
        "accent": normalize_accent(d.get("accent")),
        "scale": scale if scale in SCALES else 100,
        "density": _choice(d.get("density"), DENSITIES, DEFAULT_UI["density"]),
        "motion": _choice(d.get("motion"), MOTIONS, DEFAULT_UI["motion"]),
        "font": _choice(d.get("font"), FONTS, DEFAULT_UI["font"]),
        "chat_size": _choice(d.get("chat_size"), CHAT_SIZES, DEFAULT_UI["chat_size"]),
        "send_key": _choice(d.get("send_key"), SEND_KEYS, DEFAULT_UI["send_key"]),
        "start_page": _choice(d.get("start_page"), START_PAGES, DEFAULT_UI["start_page"]),
        "sidebar_hidden": hidden,
        "shortcuts": d.get("shortcuts") is not False,
        "welcome_done": d.get("welcome_done") is True,
    }


# --------------------------------------------------------------------------- exportar / importar configurações (sem segredos)

EXPORT_SCHEMA = "asta.settings.v1"
EXPORT_SECTIONS = ("language", "ui", "generation", "characters", "avatars", "games", "studio", "rebuild", "canvas", "computer", "code", "work", "engine", "scriber", "data", "performance", "active")
RESETTABLE = ("ui", "generation", "characters", "avatars", "games", "studio", "rebuild", "canvas", "computer", "code", "work", "engine", "scriber", "data", "performance")  # voz tem chaves de API: não entra no "restaurar padrões"
_PROVIDER_FIELDS = ("base_url", "model", "vision", "n_ctx")  # nunca `api_key`


def export_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Configurações para levar a outro computador: as preferências e o que dá para reaproveitar. **Nunca** chaves de API nem tokens."""
    out: Dict[str, Any] = {k: settings[k] for k in EXPORT_SECTIONS if k in settings}
    if isinstance(out.get("code"), dict):   # o token do GitHub nunca sai do computador
        code = dict(out["code"])
        code["github"] = {k: v for k, v in (code.get("github") or {}).items() if k != "token"} if isinstance(code.get("github"), dict) else {}
        out["code"] = code
    if isinstance(out.get("work"), dict):   # onde a máquina escuta na rede é decisão de quem está nela: não viaja no arquivo
        out["work"] = {k: v for k, v in out["work"].items() if k != "peer"}
    out["providers"] = {pid: {k: v for k, v in (cfg or {}).items() if k in _PROVIDER_FIELDS and v not in (None, "")}
                        for pid, cfg in (settings.get("providers") or {}).items() if isinstance(cfg, dict)}
    voice = settings.get("voice") or {}
    out["voice"] = {part: {k: v for k, v in (voice.get(part) or {}).items() if k != "api_key"} for part in ("stt", "tts")}
    return {"schema": EXPORT_SCHEMA, "settings": out}


def import_patch(payload: Any) -> Dict[str, Any]:
    """Transforma um arquivo exportado em um *patch* seguro para `save_settings`: só seções conhecidas, sem segredos, UI validada."""
    if not isinstance(payload, dict) or payload.get("schema") != EXPORT_SCHEMA or not isinstance(payload.get("settings"), dict):
        raise ValueError("Este arquivo não é uma exportação de configurações do ASTA.")
    src = payload["settings"]
    patch: Dict[str, Any] = {}
    for key in ("generation", "characters", "avatars", "games", "studio", "rebuild", "canvas", "performance"):
        if isinstance(src.get(key), dict):
            patch[key] = src[key]
    if isinstance(src.get("computer"), dict):   # um arquivo importado nunca liga o Computer Use, nem troca o modo, nem tira as perguntas do modo Ask: isso só quem está na frente do computador decide
        patch["computer"] = {k: v for k, v in src["computer"].items() if k in ("max_parallel", "max_steps", "team", "revisions", "app_wait", "agents", "effort")}
    if isinstance(src.get("code"), dict):   # idem Computer Use: um arquivo importado nunca troca o modo (Full Access), as perguntas do Ask, o token do GitHub nem a publicação direta na main
        c = {k: v for k, v in src["code"].items() if k in ("effort", "agents", "max_sessions", "run_timeout", "max_download_mb", "branch_prefix", "clone_depth", "github_mode", "editor", "provider")}
        if isinstance(src["code"].get("finalize"), dict):
            c["finalize"] = {"docs": src["code"]["finalize"].get("docs") is True}
        patch["code"] = c
    if isinstance(src.get("scriber"), dict):
        patch["scriber"] = {k: v for k, v in src["scriber"].items() if k in ("agents", "effort", "type", "language", "content", "web", "pages", "words_per_page", "undo_keep", "expand_words", "dialogue_words", "spellcheck", "autosave")}
    if isinstance(src.get("data"), dict):   # o raspador (`web`) só liga por decisão de quem está na frente do computador
        patch["data"] = {k: v for k, v in src["data"].items() if k in ("agents", "effort", "default_kind", "synthetic_count", "synthetic_mode")}
    if isinstance(src.get("engine"), dict):
        patch["engine"] = {k: v for k, v in src["engine"].items() if k in ("agents", "effort", "kind", "content", "web", "undo_keep")}
    if isinstance(src.get("work"), dict):   # idem: um arquivo importado nunca abre a máquina para a rede nem liga a sincronização
        patch["work"] = {k: v for k, v in src["work"].items() if k in ("agents", "effort", "interval", "max_file_mb", "backup_keep", "session_hours")}
    if src.get("language") in LANGS:
        patch["language"] = src["language"]
    if isinstance(src.get("ui"), dict):
        ui = normalize_ui(src["ui"])
        ui["welcome_done"] = True  # quem importa configurações já conhece o ASTA
        patch["ui"] = ui
    if isinstance(src.get("active"), dict):
        patch["active"] = {k: v for k, v in src["active"].items() if k in ("generation", "characters") and isinstance(v, str)}
    if isinstance(src.get("providers"), dict):
        patch["providers"] = {pid: {k: v for k, v in cfg.items() if k in _PROVIDER_FIELDS}
                              for pid, cfg in src["providers"].items() if isinstance(pid, str) and isinstance(cfg, dict)}
    if isinstance(src.get("voice"), dict):
        patch["voice"] = {part: {k: v for k, v in src["voice"][part].items() if k != "api_key"}
                          for part in ("stt", "tts") if isinstance(src["voice"].get(part), dict)}
    return patch
