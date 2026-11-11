"""Persistência em disco: configurações, cards, projetos (biblioteca) e uploads.

Tudo é JSON/arquivos comuns dentro de ASTA_HOME (padrão ~/.asta):

    settings.json
    characters/<id>.json                cards de NPC (mundos 3D)
    worldbuildings/<id>.json
    avatars/<id>.json                   avatars de chat/voz (amigo/namorada…)
    avatars/portraits/<id>.<ext>        retrato do avatar (opcional)
    avatar_chats/<id>.json              conversas (single/multi) com histórico
    avatar_memory/<avatar_id>.json      memórias de longo prazo de cada avatar
    projects/<id>/project.json          kind: "world" (3D) | "game2d"
    projects/<id>/attachments/<arquivo>
    projects/<id>/v<N>/{world,characters,sound,ux,brief,plan,review}.json   (mundos 3D)
    projects/<id>/v<N>/{game,brief,plan,review}.json                        (jogos 2D)
    projects/<id>/v<N>/package/...      (pasta do jogo, também servida em /play/<id>/)
    projects/<id>/v<N>/world.zip | game.zip
    projects/<id>/saves/default.json    (estado persistente do jogo)
    studio/<id>/project.json            um projeto do Studio (vídeo único ou série)
    canvases/<id>/canvas.json           um Canvas (nós, conexões, ativos)
    canvases/<id>/assets/<arquivo>      mídias geradas ou enviadas
    uploads/<id>/                       (anexos aguardando uso)
    models/                             (modelos GGUF baixados do Hugging Face)
"""
from __future__ import annotations

import copy
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .avatars import normalize_avatar, normalize_chat
from .assistant_chat import normalize_chat as normalize_assistant_chat
from .uiprefs import DEFAULT_UI, normalize_ui
from .canvas.store import CanvasStore
from .cards import normalize_character, normalize_worldbuilding
from .util import asta_home, deep_merge, new_id, now_iso, read_json, safe_filename, write_json

DEFAULT_SETTINGS: Dict[str, Any] = {
    "language": "auto",  # auto | pt-BR | en
    # Chat geral (a tela «Chat»): tamanho da resposta, janela de contexto, tempo de pensamento e busca na web
    "chat": {"history_turns": 20, "temperature": 0.7, "max_tokens": 2000, "context_tokens": 16000, "thinking": "off", "instructions": "",
             "reply_style": "detailed",  # balanced | detailed (padrão: respostas completas e de qualidade) | epic (longas e profundas)
             "effort": "low", "team_agents": 1,  # Low … Omni (os níveis do Code) e 1/2/4/8/12/16/20/24/28/32 agentes (notas privadas para a resposta): ver team.py
             "auto_continue": True, "continue_rounds": 3,  # resposta cortada pelo limite de tokens → continua sozinha de onde parou
             "agents": "off",  # off | plan (Planejador → Redator) | review (Planejador → Redator → Revisor → Redator): equipe de agentes para respostas mais completas

             "web": {"default": False, "engine": "auto", "results": 5, "read_pages": 2, "language": "auto", "brave_key": "", "tavily_key": "", "searxng_url": ""}},
    "ui": DEFAULT_UI,  # aparência, atalhos, barra lateral, chat (ver uiprefs.py)
    "active": {"generation": "demo", "characters": "auto"},  # characters "auto": IA de verdade sempre que houver (ver providers/auto.py)
    "providers": {},
    "generation": {
        "perspective": "third",  # first | third
        "realism": 0.7,
        "size": "medium",  # small | medium | large
        "quality": "auto",  # auto | low | medium | high
        "max_npcs": 0,  # 0 = automático
        "revisions": 1,  # rodadas de revisão do agente Revisor (0-3)
        "temperature": 0.8,
        "max_tokens": 6000,
        "content": "free",  # free (SFW e NSFW, sem filtros do ASTA) | sfw
        "day_cycle": True,
        "npc_autonomy": "off",  # off | low | high
        "include_attachments": True,
        "agents": 1, "effort": "high",  # equipe: 1/2/4/8/12/16/20/24/28/32 agentes em paralelo por etapa · esforço Low … Omni (ver team.py)
    },
    "characters": {
        "detail": "detailed",  # short | detailed
        "player_character": True,
        "temperature": 0.9,
        "max_tokens": 700,
        "history_turns": 16,
        "memory_limit": 30,
    },
    "voice": {
        "stt": {"engine": "browser", "base_url": "", "api_key": "", "model": "whisper-1", "lang": "auto"},
        "tts": {"engine": "browser", "base_url": "", "api_key": "", "model": "tts-1", "voice": "alloy"},
    },
    "avatars": {
        "content": "sfw",  # padrão ao criar avatars: sfw | nsfw (o usuário escolhe por avatar)
        "user_name": "",  # como os avatars chamam você ("" = automático)
        "user_persona": "",
        "temperature": 0.9,
        "max_tokens": 500,
        "history_turns": 24,
        "memory_limit": 40,
        "auto_talk": True,  # multi: os avatars conversam entre si sem você pedir
        "auto_talk_max": 10,  # máximo de falas seguidas sem uma mensagem sua
        "auto_talk_delay": 6,  # segundos entre falas autônomas
        "voice_reply": True,
        "agents": 1, "effort": "high",  # equipe da CRIAÇÃO de avatars (ver team.py)
        "chat_agents": 1, "chat_effort": "low",  # equipe da CONVERSA com os avatars (notas privadas + pensamento); Low = sem pensamento, para responder rápido
    },
    "games": {
        "length": "medium",  # short | medium | long (tamanho pedido aos agentes)
        "revisions": 1,
        "temperature": 0.8,
        "max_tokens": 9000,
        "agents": 1, "effort": "high",
    },
    "media": {
        # provedor padrão de cada capacidade do Canvas (cada nó pode escolher outro)
        "active": {"image": "demo", "video": "demo", "sound": "demo", "voice": "demo", "stt": "voice_settings"},  # transcrição: usa Configuração → Voz
        "models": {},  # {"openai": {"image": "gpt-image-1"}} — modelo por provedor e capacidade
        "urls": {},  # {"a1111": "http://127.0.0.1:7860"} — endereço de servidores (locais ou compatíveis)
    },
    # Padrões por seção (Configuração → Seções): o que já vem marcado ao criar algo novo
    "studio": {"kind": "single", "duration_type": "shorts", "target_seconds": 60, "style": "realistic", "style_custom": "", "aspect": "auto",
               "language": "auto", "motion": "auto", "captions": True, "music": True, "revisions": 1, "voice": "",
               "export_quality": "720p", "export_fps": 24, "audio_format": "m4a", "autoedit_style": "gameplay", "autoedit_target": 0,
               "agents": 1, "effort": "high"},
    "rebuild": {"refine": True, "max_calls": 40, "agents": 1, "effort": "high"},
    # Computer Use (opcional, desligado por padrão): equipe de agentes que faz tarefas no computador. Ver computer/manager.py (normalize_config)
    "computer": {"enabled": False, "mode": "ask",  # ask = pergunta Sim/Não antes de agir · full = Full Access, executa tudo sem perguntar
                 "max_parallel": 8, "max_steps": 40, "team": "full",  # team: full (Planejador → Operador → Revisor → Relator) | fast (só o Operador; para modelos locais lentos)
                 "revisions": 1, "ask_for": ["write", "delete", "run", "input", "screen"], "game_dirs": [], "app_wait": 2.0,
                 "agents": 1, "effort": "high"},  # agents: 1/4 a 32 (mesa de agentes no Planejador e no Verificador) · effort: Low … Omni (ver team.py)
    # Code (vibe coding com equipes de agentes): ver code/manager.py (normalize_config). O token do GitHub é segredo (SECRET_PATHS): nunca vai ao navegador nem à exportação.
    "code": {"mode": "ask",  # ask = pergunta Sim/Não antes de agir · full = Full Access, executa tudo sem perguntar
             "effort": "high", "agents": 4, "max_sessions": 4, "ask_for": ["write", "delete", "run", "install", "git", "publish"], "run_timeout": 180, "max_download_mb": 200,
             "allow_main": True, "branch_prefix": "asta/", "git_name": "", "git_email": "", "credit_asta": False, "credit_name": "", "credit_email": "", "clone_depth": 20, "github_mode": "auto", "editor": "auto",
             "github": {"api": "", "token": ""}, "finalize": {"docs": False, "publish": "none"}, "provider": {"id": "", "model": ""}},
    # Work (v0.18): equipe, pessoas e sincronização entre máquinas. Ver work/manager.py (normalize_config). Os segredos da rede ficam em ~/.asta/work/<rede>/secret.json, nunca aqui.
    "work": {"peer": {"listen": "off", "port": 8790},  # off = não escuta · auto = só no IP do Tailscale · lan = rede local · ou um IP. Desligado por padrão.
             "auto_sync": True, "interval": 15, "max_file_mb": 4096, "session_hours": 12, "backup_keep": 14, "agents": 1, "effort": "high"},
    # Game Engine (v0.19): jogos 2D/2.5D/3D/VR/AR com IA. Ver gameengine/agents.py (normalize_config). Projetos em ~/.asta/gameengine/<id>/.
    "engine": {"agents": 1, "effort": "high", "kind": "2d", "content": "", "web": False, "undo_keep": 25},
    # Scriber (v0.20): escrita criativa e profissional (geração automática + edição). Ver scriber/agents.py (normalize_config). Projetos em ~/.asta/scriber/<id>/.
    "scriber": {"agents": 1, "effort": "high", "type": "romance", "language": "pt-BR", "content": "", "web": False, "pages": 40, "words_per_page": 300, "undo_keep": 25, "expand_words": 150, "dialogue_words": 60, "spellcheck": True, "autosave": True},
    "canvas": {"template": "text_image", "agents": 1, "effort": "high"},  # equipe dos nós de texto (IA) do Canvas
    "performance": {"mode": "auto", "idle_unload_min": 10},  # auto | light | balanced | max — veja perf.py
    "server": {"max_upload_mb": 200},
    "hf": {"token": ""},
}

def conform(defaults: Any, value: Any) -> Any:
    """Força `value` a ter a «forma» de `defaults`: onde o padrão é um objeto, o valor precisa ser um objeto (senão volta ao padrão); onde o padrão é um número/texto/booleano,
    um valor de outro tipo é descartado. Um settings.json editado à mão (ou uma chamada de API errada) não derruba mais a tela inteira."""
    if not isinstance(defaults, dict):
        return value
    out = dict(value) if isinstance(value, dict) else {}
    for key, dv in defaults.items():
        if key not in out:
            out[key] = copy.deepcopy(dv)
        elif isinstance(dv, dict):
            out[key] = conform(dv, out[key]) if isinstance(out[key], dict) else copy.deepcopy(dv)
        elif isinstance(dv, bool):
            if not isinstance(out[key], bool):
                out[key] = bool(out[key]) if isinstance(out[key], (int, float)) else dv
        elif isinstance(dv, (int, float)):
            if isinstance(out[key], bool) or not isinstance(out[key], (int, float)):
                out[key] = dv
        elif isinstance(dv, str):
            if not isinstance(out[key], str):
                out[key] = dv
    providers = out.get("providers")
    if isinstance(providers, dict):
        out["providers"] = {k: v for k, v in providers.items() if isinstance(v, dict)}
    return out


def _normalize_teams(settings: dict) -> None:
    """Equipe de cada seção (agentes 1/4 a 32 e esforço Low … Omni): valor fora da lista (edição manual, API) vira o valor aceito mais próximo. O Code mantém qualquer número de 1 a 32."""
    from . import team

    for key in team.SECTIONS:
        sec = settings.get(key)
        if not isinstance(sec, dict):
            continue
        akey = "team_agents" if key == "chat" else "agents"
        if key == "code":
            try:
                sec[akey] = max(1, min(int(sec.get(akey) or 4), team.MAX_AGENTS))
            except (TypeError, ValueError):
                sec[akey] = 4
        else:
            sec[akey] = team.normalize_agents(sec.get(akey))
        sec["effort"] = team.normalize_effort(sec.get("effort"), "low" if key == "chat" else team.DEFAULT_EFFORT)


# Caminhos (dentro de settings) que contêm segredos e nunca são enviados ao navegador.
SECRET_PATHS = [
    ("hf", "token"),
    ("code", "github", "token"),
    ("voice", "stt", "api_key"),
    ("voice", "tts", "api_key"),
    ("chat", "web", "brave_key"),
    ("chat", "web", "tavily_key"),
]


def _get_path(data: dict, path: tuple) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _set_path(data: dict, path: tuple, value: Any) -> None:
    cur = data
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value


def _strip_flags(data: Any) -> None:
    """Remove flags somente-leitura (`*_set`, `has_key`) que o navegador pode devolver."""
    if isinstance(data, dict):
        for key in list(data.keys()):
            if key == "has_key" or key.endswith("_set"):
                data.pop(key, None)
            else:
                _strip_flags(data[key])


class CardStore:
    """Uma pasta de cards .json (personagens ou worldbuildings)."""

    def __init__(self, folder: Path, normalize, prefix: str):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self._normalize = normalize
        self._prefix = prefix
        self._lock = threading.RLock()

    def list(self) -> List[dict]:
        items = []
        for path in self.folder.glob("*.json"):
            data = read_json(path)
            if isinstance(data, dict) and data.get("id"):
                items.append(data)
        items.sort(key=lambda c: c.get("updated", ""), reverse=True)
        return items

    def get(self, card_id: str) -> Optional[dict]:
        if not card_id or "/" in card_id or "\\" in card_id or ".." in card_id:
            return None
        return read_json(self.folder / f"{card_id}.json")

    def save(self, data: dict, card_id: Optional[str] = None) -> dict:
        with self._lock:
            existing = self.get(card_id) if card_id else None
            card = self._normalize(data, keep_id=card_id or None)
            card["id"] = card_id or card.get("id") or new_id(self._prefix)
            if self.get(card["id"]) is None and (self.folder / f"{card['id']}.json").exists():
                card["id"] = new_id(self._prefix)
            card["created"] = (existing or {}).get("created") or card.get("created") or now_iso()
            card["updated"] = now_iso()
            write_json(self.folder / f"{card['id']}.json", card)
            return card

    def delete(self, card_id: str) -> bool:
        if self.get(card_id) is None:
            return False
        (self.folder / f"{card_id}.json").unlink(missing_ok=True)
        return True


class Store:
    def __init__(self, home: Optional[Path] = None):
        self.home = Path(home) if home else asta_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.home / "settings.json"
        self.characters = CardStore(self.home / "characters", normalize_character, "c_")
        self.worldbuildings = CardStore(self.home / "worldbuildings", normalize_worldbuilding, "w_")
        self.avatars = CardStore(self.home / "avatars", normalize_avatar, "a_")
        self.chats = CardStore(self.home / "chats", normalize_assistant_chat, "t_")  # conversas do Chat geral
        self.avatar_chats = CardStore(self.home / "avatar_chats", normalize_chat, "ch_")
        self.avatar_portraits_dir = self.home / "avatars" / "portraits"
        self.avatar_memory_dir = self.home / "avatar_memory"
        self.profile_dir = self.home / "profile"
        self.profile_path = self.home / "profile.json"
        self.memory_dir = self.home / "memory"
        self.canvases = CanvasStore(self.home / "canvases")
        from .studio.store import StudioStore

        self.studio = StudioStore(self.home / "studio")
        self.projects_dir = self.home / "projects"
        self.uploads_dir = self.home / "uploads"
        self.models_dir = self.home / "models"
        for d in (self.projects_dir, self.uploads_dir, self.models_dir, self.avatar_portraits_dir, self.avatar_memory_dir, self.profile_dir, self.memory_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        from . import perf

        perf.configure(self.get_settings().get("performance"))

    # ------------------------------------------------------------------ settings
    def get_settings(self) -> dict:
        saved = read_json(self.settings_path, {}) or {}
        merged = conform(DEFAULT_SETTINGS, deep_merge(copy.deepcopy(DEFAULT_SETTINGS), saved if isinstance(saved, dict) else {}))
        _normalize_teams(merged)
        merged["ui"] = normalize_ui(merged.get("ui"))  # valor inválido (API/edição manual) volta ao padrão em vez de quebrar a interface
        return merged

    def save_settings(self, patch: dict) -> dict:
        """Mescla `patch` nas configurações.

        Segredos: "" ou ausente = manter; null = apagar; texto = definir.
        """
        with self._lock:
            current = self.get_settings()
            patch = copy.deepcopy(patch or {})
            # provedores: tratados à parte (chave por id)
            prov_patch = patch.pop("providers", None) or {}
            for pid, pcfg in prov_patch.items():
                if not isinstance(pcfg, dict):
                    continue
                cur = current["providers"].setdefault(pid, {})
                for k, v in pcfg.items():
                    if k == "has_key" or k.endswith("_set"):
                        continue
                    if k == "api_key":
                        if v is None:
                            cur.pop("api_key", None)
                        elif isinstance(v, str) and v.strip():
                            cur["api_key"] = v.strip()
                        continue
                    cur[k] = v
            # demais segredos: "" = manter, null = apagar, texto = definir
            for path in SECRET_PATHS:
                parent = _get_path(patch, path[:-1])
                if not isinstance(parent, dict) or path[-1] not in parent:
                    continue
                val = parent.pop(path[-1])
                if val is None:
                    _set_path(current, path, "")
                elif isinstance(val, str) and val.strip():
                    _set_path(current, path, val.strip())
            _strip_flags(patch)
            merged = conform(DEFAULT_SETTINGS, deep_merge(current, patch))  # valor do tipo errado (API/edição manual) nunca chega ao disco
            merged["ui"] = normalize_ui(merged.get("ui"))
            write_json(self.settings_path, merged, private=True)
            from . import perf

            perf.configure(merged.get("performance"))
            return merged

    def public_settings(self) -> dict:
        """Configurações para o navegador: segredos viram flags `has_key`."""
        s = copy.deepcopy(self.get_settings())
        for pid, pcfg in s.get("providers", {}).items():
            key = pcfg.pop("api_key", "")
            pcfg["has_key"] = bool(key)
        for path in SECRET_PATHS:
            val = _get_path(s, path)
            _set_path(s, path[:-1] + (path[-1] + "_set",), bool(val))
            _set_path(s, path, "")
        return s

    # ------------------------------------------------------------------ projetos
    def project_dir(self, pid: str) -> Optional[Path]:
        if not pid or "/" in pid or "\\" in pid or ".." in pid:
            return None
        return self.projects_dir / pid

    def list_projects(self, kind: Optional[str] = None) -> List[dict]:
        """Projetos da biblioteca. `kind`: "world" (3D) | "game2d" | None (todos)."""
        items = []
        for d in self.projects_dir.iterdir():
            meta = read_json(d / "project.json") if d.is_dir() else None
            if isinstance(meta, dict) and meta.get("id"):
                meta.setdefault("kind", "world")  # projetos da v0.1 não tinham `kind`
                if kind is None or meta["kind"] == kind:
                    items.append(meta)
        items.sort(key=lambda p: p.get("updated", ""), reverse=True)
        return items

    def get_project(self, pid: str) -> Optional[dict]:
        d = self.project_dir(pid)
        project = read_json(d / "project.json") if d else None
        if isinstance(project, dict):
            project.setdefault("kind", "world")
        return project

    def save_project(self, project: dict) -> dict:
        with self._lock:
            project["updated"] = now_iso()
            write_json(self.projects_dir / project["id"] / "project.json", project)
            return project

    def create_project(self, name: str, **extra: Any) -> dict:
        pid = new_id("p_")
        project = {
            "id": pid,
            "kind": "world",
            "name": name,
            "description": "",
            "tags": {"auto": [], "custom": []},
            "created": now_iso(),
            "updated": now_iso(),
            "current": 0,
            "versions": [],
            "settings": {},
            "worldbuilding_id": "",
            "character_ids": [],
            "attachments": [],
            "palette": {},
        }
        project.update(extra)
        (self.projects_dir / pid).mkdir(parents=True, exist_ok=True)
        return self.save_project(project)

    def delete_project(self, pid: str) -> bool:
        d = self.project_dir(pid)
        if not d or not d.exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True

    def version_dir(self, pid: str, n: int) -> Path:
        d = self.project_dir(pid)
        if d is None:
            raise ValueError("id de projeto inválido")
        return d / f"v{int(n)}"

    def package_dir(self, pid: str, n: Optional[int] = None) -> Optional[Path]:
        project = self.get_project(pid)
        if not project:
            return None
        n = n or project.get("current") or 0
        if not n:
            return None
        p = self.version_dir(pid, n) / "package"
        return p if p.exists() else None

    def zip_path(self, pid: str, n: Optional[int] = None) -> Optional[Path]:
        project = self.get_project(pid)
        if not project:
            return None
        n = n or project.get("current") or 0
        if not n:
            return None
        for fname in ("world.zip", "game.zip"):
            p = self.version_dir(pid, n) / fname
            if p.exists():
                return p
        return None

    def load_version(self, pid: str, n: Optional[int] = None) -> Optional[Dict[str, Any]]:
        project = self.get_project(pid)
        if not project:
            return None
        n = n or project.get("current") or 0
        if not n:
            return None
        vd = self.version_dir(pid, n)
        out: Dict[str, Any] = {"n": n}
        for key in ("world", "characters", "sound", "ux", "brief", "plan", "review"):
            out[key] = read_json(vd / f"{key}.json")
        return out if out.get("world") else None

    def load_game_version(self, pid: str, n: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Versão de um projeto `game2d`: {n, game, brief, plan, review}."""
        project = self.get_project(pid)
        if not project:
            return None
        n = n or project.get("current") or 0
        if not n:
            return None
        vd = self.version_dir(pid, n)
        out: Dict[str, Any] = {"n": n}
        for key in ("game", "brief", "plan", "review"):
            out[key] = read_json(vd / f"{key}.json")
        return out if out.get("game") else None

    def save_path(self, pid: str, slot: str = "default") -> Optional[Path]:
        d = self.project_dir(pid)
        if d is None:
            return None
        return d / "saves" / f"{safe_filename(slot, 'default')}.json"

    # ------------------------------------------------------------------ avatars
    def _avatar_file(self, folder: Path, avatar_id: str, suffix: str) -> Optional[Path]:
        if not avatar_id or any(c in avatar_id for c in "/\\.") or not avatar_id.replace("_", "").replace("-", "").isalnum():
            return None
        return folder / f"{avatar_id}{suffix}"

    def get_memories(self, avatar_id: str) -> List[str]:
        path = self._avatar_file(self.avatar_memory_dir, avatar_id, ".json")
        data = read_json(path, {}) if path else {}
        items = data.get("memories") if isinstance(data, dict) else None
        return [str(m) for m in items] if isinstance(items, list) else []

    def add_memories(self, avatar_id: str, new: List[str], limit: int = 40) -> List[str]:
        """Acrescenta memórias de longo prazo (sem repetir); mantém só as `limit` mais recentes."""
        path = self._avatar_file(self.avatar_memory_dir, avatar_id, ".json")
        if path is None:
            return []
        with self._lock:
            items = self.get_memories(avatar_id)
            for m in new:
                m = " ".join(str(m).split())[:240]
                if m and m not in items:
                    items.append(m)
            items = items[-max(5, int(limit)):]
            write_json(path, {"memories": items})
            return items

    def delete_memory(self, avatar_id: str, index: int) -> List[str]:
        """Esquece uma lembrança só (posição `index` da lista). Devolve a lista nova."""
        path = self._avatar_file(self.avatar_memory_dir, avatar_id, ".json")
        if path is None:
            return []
        with self._lock:
            items = self.get_memories(avatar_id)
            if 0 <= index < len(items):
                items.pop(index)
                write_json(path, {"memories": items})
            return items

    def clear_memories(self, avatar_id: str) -> None:
        path = self._avatar_file(self.avatar_memory_dir, avatar_id, ".json")
        if path:
            path.unlink(missing_ok=True)

    def portrait_path(self, avatar_id: str) -> Optional[Path]:
        card = self.avatars.get(avatar_id)
        name = (card or {}).get("portrait") or ""
        if not name or "/" in name or "\\" in name or ".." in name:
            return None
        p = self.avatar_portraits_dir / name
        return p if p.is_file() else None

    def save_portrait(self, avatar_id: str, data: bytes, ext: str) -> Optional[str]:
        """Grava o retrato do avatar e atualiza o card. `ext`: png|jpg|webp|gif."""
        card = self.avatars.get(avatar_id)
        ext = ext.lower().lstrip(".")
        if not card or ext not in ("png", "jpg", "jpeg", "webp", "gif") or not data:
            return None
        old = card.get("portrait") or ""
        name = f"{avatar_id}-{new_id()}.{'jpg' if ext == 'jpeg' else ext}"
        (self.avatar_portraits_dir / name).write_bytes(data)
        card["portrait"] = name
        self.avatars.save(card, avatar_id)
        if old and old != name:
            (self.avatar_portraits_dir / old).unlink(missing_ok=True)
        return name

    def clear_portrait(self, avatar_id: str) -> bool:
        card = self.avatars.get(avatar_id)
        if not card:
            return False
        old = card.get("portrait") or ""
        if old and "/" not in old and ".." not in old:
            (self.avatar_portraits_dir / old).unlink(missing_ok=True)
        card["portrait"] = ""
        self.avatars.save(card, avatar_id)
        return True

    def delete_avatar(self, avatar_id: str) -> bool:
        card = self.avatars.get(avatar_id)
        if not card:
            return False
        self.clear_portrait(avatar_id)
        self.clear_memories(avatar_id)
        self.avatars.delete(avatar_id)
        # conversas: a dois, somem; em grupo, o avatar sai e a conversa segue (com 1 só, vira conversa a dois). Antes ficavam conversas fantasma que travavam a tela.
        for chat in self.avatar_chats.list():
            if avatar_id not in chat.get("avatar_ids", []):
                continue
            left = [i for i in chat["avatar_ids"] if i != avatar_id]
            if not left:
                self.avatar_chats.delete(chat["id"])
                continue
            chat["avatar_ids"] = left
            chat["messages"] = [m for m in chat.get("messages", []) if m.get("avatar_id") != avatar_id]
            self.avatar_chats.save(chat, chat["id"])
        return True


    # ------------------------------------------------------------------ perfil do usuário
    def get_profile(self) -> dict:
        from . import profile as p
        return p.load(self.profile_path)

    def save_profile(self, data: dict) -> dict:
        from . import profile as p
        return p.save(self.profile_path, data)

    def profile_portrait_path(self) -> Optional[Path]:
        prof = self.get_profile()
        name = prof.get("portrait") or ""
        if not name or "/" in name or "\\" in name or ".." in name:
            return None
        p = self.profile_dir / name
        return p if p.is_file() else None

    def save_profile_portrait(self, data: bytes, ext: str) -> Optional[str]:
        from . import profile as p
        prof = self.get_profile()
        ext = ext.lower().lstrip(".")
        if ext not in ("png", "jpg", "jpeg", "webp", "gif") or not data:
            return None
        old = prof.get("portrait") or ""
        name = f"portrait-{new_id()}.{'jpg' if ext == 'jpeg' else ext}"
        (self.profile_dir / name).write_bytes(data)
        prof["portrait"] = name
        p.save(self.profile_path, prof, keep_portrait=name)
        if old and old != name and "/" not in old and ".." not in old:
            (self.profile_dir / old).unlink(missing_ok=True)
        return name

    def clear_profile_portrait(self) -> bool:
        from . import profile as p
        prof = self.get_profile()
        old = prof.get("portrait") or ""
        if old and "/" not in old and ".." not in old:
            (self.profile_dir / old).unlink(missing_ok=True)
        prof["portrait"] = ""
        p.save(self.profile_path, prof, keep_portrait="")
        return True

    # ------------------------------------------------------------------ memória unificada universal
    def remember(self, section: str, action: str, title: str = "", summary: str = "", detail: Any = None, tags: Optional[List[str]] = None) -> Optional[dict]:
        """Registra um evento na memória unificada (JSON por ano/mês/semana/dia). Nunca levanta erro para não atrapalhar a ação principal."""
        try:
            from . import memory
            return memory.record(self.memory_dir, section, action, title, summary, detail, tags)
        except Exception:
            return None

    def memory_days(self, limit: int = 400) -> list:
        from . import memory
        return memory.list_days(self.memory_dir, limit)

    def memory_day(self, date: str) -> Optional[dict]:
        from . import memory
        return memory.read_day(self.memory_dir, date)

    def memory_write_day(self, date: str, doc: Any) -> dict:
        from . import memory
        return memory.write_day(self.memory_dir, date, doc)

    def memory_update_item(self, date: str, item_id: str, patch: Any) -> dict:
        from . import memory
        return memory.update_item(self.memory_dir, date, item_id, patch)

    def memory_delete_item(self, date: str, item_id: str) -> bool:
        from . import memory
        return memory.delete_item(self.memory_dir, date, item_id)

    def memory_search(self, query: str = "", section: str = "", limit: int = 200) -> list:
        from . import memory
        return memory.search(self.memory_dir, query, section, limit)

    def memory_sections(self) -> list:
        from . import memory
        return memory.sections(self.memory_dir)

    # ------------------------------------------------------------------ uploads
    def save_upload_stream(self, name: str, mime: str, stream, length: int, chunk: int = 1 << 20) -> dict:
        uid = new_id("u_")
        folder = self.uploads_dir / uid
        folder.mkdir(parents=True, exist_ok=True)
        fname = safe_filename(name, "arquivo")
        target = folder / fname
        remaining = length
        with open(target, "wb") as fh:
            while remaining > 0:
                data = stream.read(min(chunk, remaining))
                if not data:
                    break
                fh.write(data)
                remaining -= len(data)
        meta = {"id": uid, "name": fname, "mime": mime or "", "size": target.stat().st_size, "created": now_iso()}
        write_json(folder / "meta.json", meta)
        return meta

    def get_upload(self, uid: str) -> Optional[dict]:
        if not uid or "/" in uid or "\\" in uid or ".." in uid:
            return None
        folder = self.uploads_dir / uid
        meta = read_json(folder / "meta.json")
        if not isinstance(meta, dict):
            return None
        meta["path"] = str(folder / meta["name"])
        return meta

    def delete_upload(self, uid: str) -> bool:
        uid = str(uid or "").split(":", 1)[0]   # «u_abc:3» = um arquivo de dentro de um pacote: apagar o anexo apaga o pacote inteiro
        if not self.get_upload(uid):
            return False
        shutil.rmtree(self.uploads_dir / uid, ignore_errors=True)
        return True

    def get_uploads(self, ids, limit: int = 40, expand: bool = True, max_members: int = 120) -> list:
        """Os anexos de uma lista de ids. Com `expand`, um pacote (ZIP, RAR, 7z, TAR…) é aberto e **cada arquivo de dentro vira um anexo** (id «u_abc:3», nome «pacote.zip/pasta/arquivo.txt»),
        então todas as seções tratam o conteúdo do pacote como se o usuário tivesse anexado os arquivos soltos. Pacote ilegível/com senha vira um anexo só, com `error`."""
        from . import archives

        out: list = []
        for uid in [u for u in (ids or []) if isinstance(u, str)][:limit]:
            meta = self.get_upload(uid)
            if not meta:
                continue
            kind = archives.archive_kind(meta["name"], Path(meta["path"])) if expand else ""
            if not kind:
                out.append(meta)
                continue
            try:
                members = self._unpack(meta, max_members)
            except archives.ArchiveError as exc:
                out.append(dict(meta, error=str(exc), archive_kind=kind))
                continue
            if not members:
                out.append(dict(meta, error="O pacote não tem nenhum arquivo utilizável.", archive_kind=kind))
                continue
            out.extend(members)
        return out

    def _unpack(self, meta: dict, max_members: int) -> list:
        """Abre o pacote do anexo `meta` (uma vez; fica em uploads/<id>/_unpacked) e devolve os arquivos de dentro como metadados de anexo."""
        from . import archives

        folder = self.uploads_dir / meta["id"] / "_unpacked"
        index = folder / "_index.json"
        data = read_json(index) if index.is_file() else None
        if not isinstance(data, dict):
            shutil.rmtree(folder, ignore_errors=True)
            res = archives.expand(meta["path"], folder, meta["name"])   # resolve() abaixo: no macOS /var é um link para /private/var
            data = {"files": [{"name": f["name"], "path": str(Path(f["path"]).resolve().relative_to(folder.resolve())).replace("\\", "/"), "size": f["size"]} for f in res["files"]], "skipped": res["skipped"]}
            write_json(index, data)
        out = []
        for i, f in enumerate(data["files"][:max_members]):
            p = folder / f["path"]
            if p.is_file():
                out.append({"id": f"{meta['id']}:{i}", "name": f"{meta['name']}/{f['name']}", "mime": "", "size": f["size"], "created": meta.get("created", ""), "path": str(p),
                            "archive": meta["name"], "skipped": data["skipped"] if i == 0 else []})
        return out
