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
from .canvas.store import CanvasStore
from .cards import normalize_character, normalize_worldbuilding
from .util import asta_home, deep_merge, new_id, now_iso, read_json, safe_filename, write_json

DEFAULT_SETTINGS: Dict[str, Any] = {
    "language": "auto",  # auto | pt-BR | en
    "active": {"generation": "demo", "characters": "demo"},
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
    },
    "games": {
        "length": "medium",  # short | medium | long (tamanho pedido aos agentes)
        "revisions": 1,
        "temperature": 0.8,
        "max_tokens": 9000,
    },
    "media": {
        # provedor padrão de cada capacidade do Canvas (cada nó pode escolher outro)
        "active": {"image": "demo", "video": "demo", "sound": "demo", "voice": "demo", "stt": "demo"},
        "models": {},  # {"openai": {"image": "gpt-image-1"}} — modelo por provedor e capacidade
        "urls": {},  # {"a1111": "http://127.0.0.1:7860"} — endereço de servidores (locais ou compatíveis)
    },
    "server": {"max_upload_mb": 200},
    "hf": {"token": ""},
}

# Caminhos (dentro de settings) que contêm segredos e nunca são enviados ao navegador.
SECRET_PATHS = [
    ("hf", "token"),
    ("voice", "stt", "api_key"),
    ("voice", "tts", "api_key"),
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
        self.avatar_chats = CardStore(self.home / "avatar_chats", normalize_chat, "ch_")
        self.avatar_portraits_dir = self.home / "avatars" / "portraits"
        self.avatar_memory_dir = self.home / "avatar_memory"
        self.canvases = CanvasStore(self.home / "canvases")
        self.projects_dir = self.home / "projects"
        self.uploads_dir = self.home / "uploads"
        self.models_dir = self.home / "models"
        for d in (self.projects_dir, self.uploads_dir, self.models_dir, self.avatar_portraits_dir, self.avatar_memory_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ settings
    def get_settings(self) -> dict:
        saved = read_json(self.settings_path, {}) or {}
        return deep_merge(copy.deepcopy(DEFAULT_SETTINGS), saved)

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
            merged = deep_merge(current, patch)
            write_json(self.settings_path, merged, private=True)
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
        return True

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
        if not self.get_upload(uid):
            return False
        shutil.rmtree(self.uploads_dir / uid, ignore_errors=True)
        return True
