"""Servidor HTTP do ASTA (somente biblioteca padrão).

- Serve a WebUI (asta/web) e os mundos gerados em /play/<projeto>/.
- API JSON em /api/*, com Server-Sent Events para progresso e conversa.
- Escuta apenas em 127.0.0.1 por padrão; valida Host/Origin (anti DNS-rebinding/CSRF).
"""
from __future__ import annotations

import json
import mimetypes
import re
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import __version__, builder, hf, native, team, voice
from .agents.llm import call_json
from .agents.pipeline import Cancelled, Pipeline, create_edit_version  # noqa: F401
from .cards import character_from_png, import_character, normalize_character
from .games2d.builder import rebuild_game
from .jobs import HttpError, Job, JobManager  # noqa: F401  (reexportados)
from .providers import ProviderError, build_provider, describe_presets, provider_config, resolve_provider
from .routes_avatars import AvatarRoutes
from .routes_chat import ChatRoutes
from .routes_code import CodeRoutes
from .routes_computer import ComputerRoutes
from .routes_canvas import CanvasRoutes
from .routes_studio import StudioRoutes
from .routes_mobile import MobileRoutes
from .routes_auth import AuthRoutes
from .mobile import Mobile, PAIR_REQUIRED_HTML, is_loopback, _FORWARD_HEADERS
from .remote import Remote
from .routes_games import GameRoutes
from .routes_preinstalled import PreinstalledRoutes
from .storage import Store
from .util import hardware_info, new_id, safe_filename, slugify, text, write_json

WEB_DIR = Path(__file__).parent / "web"
PLAY_ALLOWED = ("Game.html", "code/", "chars/", "sound/", "ui/", "data/", "assets/", "README.md", "CHANGELOG.md")

MIME = {
    ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".md": "text/markdown; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".ogg": "audio/ogg", ".webm": "audio/webm", ".zip": "application/zip", ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8",
    ".mp4": "video/mp4", ".m4a": "audio/mp4", ".webp": "image/webp", ".gif": "image/gif", ".flac": "audio/flac", ".opus": "audio/ogg",
    ".mov": "video/quicktime", ".mkv": "video/x-matroska", ".webmanifest": "application/manifest+json",
}


def _disk_version() -> str:
    """Versão que está instalada em disco agora (lida de asta/__init__.py). Difere de `__version__` quando o ASTA foi atualizado e este processo ainda é o antigo."""
    try:
        m = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", (Path(__file__).parent / "__init__.py").read_text(encoding="utf-8"))
        return m.group(1) if m else __version__
    except OSError:
        return __version__


def guess_mime(path: str) -> str:
    ext = Path(path).suffix.lower()
    return MIME.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"


# --------------------------------------------------------------------------- aplicação


def _native_status() -> dict:
    try:
        from . import native

        st = native.status()
        si = native.sys_info()
        return {"active": st["active"], "cargo": st["cargo"], "models": st.get("models", False), "ops": st.get("ops", False), "abi": st.get("abi", 0), "last": st.get("last", {}),
                "cores": [si.get("physical"), si.get("logical")], "features": si.get("features", [])}
    except Exception:  # noqa: BLE001
        return {"active": False, "cargo": False}


class App:
    def __init__(self, store: Store, bind_host: str = "127.0.0.1"):
        self.store = store
        self.jobs = JobManager()
        self.bind_host = bind_host
        self.routes: List[Tuple[str, "re.Pattern[str]", Callable]] = []
        self._register()

    # ----- roteamento
    def add(self, method: str, pattern: str, fn: Callable) -> None:
        self.routes.append((method, re.compile("^" + pattern + "$"), fn))

    def dispatch(self, req: "Request") -> bool:
        for method, rx, fn in self.routes:
            if method != req.method and not (req.method == "HEAD" and method == "GET"):  # HEAD = GET sem corpo
                continue
            m = rx.match(req.path)
            if m:
                fn(req, **m.groupdict())
                return True
        return False

    def host_allowed(self, host_header: str) -> bool:
        host = (host_header or "").strip().lower()
        if host.startswith("["):
            name = host[1:host.find("]")] if "]" in host else host
        else:
            name = host.split(":")[0]
        if name in ("localhost", "127.0.0.1", "::1"):
            return True
        return self.bind_host not in ("127.0.0.1", "localhost", "::1")  # exposto na rede por escolha do usuário

    # ----- helpers de provedor
    def provider(self, role: str = "generation", settings: Optional[dict] = None):
        settings = settings or self.store.get_settings()
        if role == "characters":  # conversas: IA de verdade sempre que houver alguma (ver providers/auto.py)
            provider, info = resolve_provider(settings, role, self.store.models_dir)
            return provider, info["id"]
        pid = settings["active"].get(role, "demo")
        return build_provider(settings, pid, self.store.models_dir), pid

    def _provider_from_request(self, body: dict):
        settings = self.store.get_settings()
        pid = body.get("id") or "demo"
        cfg = body.get("config") or {}
        override = settings["providers"].setdefault(pid, {})
        for k in ("base_url", "model"):
            if k in cfg and isinstance(cfg[k], str):  # campo vazio vale: testar sem modelo escolhido (ex.: LM Studio em automático) não pode herdar o salvo
                override[k] = cfg[k].strip()
        if cfg.get("api_key"):
            override["api_key"] = cfg["api_key"]
        if "vision" in cfg:
            override["vision"] = bool(cfg["vision"])
        if cfg.get("n_ctx"):
            override["n_ctx"] = cfg["n_ctx"]
        return build_provider(settings, pid, self.store.models_dir)

    # ------------------------------------------------------------------ rotas
    def _register(self) -> None:
        a = self.add
        a("GET", r"/api/state", self.r_state)
        a("GET", r"/api/settings", self.r_settings_get)
        a("GET", r"/api/team", self.r_team)
        a("PUT", r"/api/settings", self.r_settings_put)
        a("GET", r"/api/settings/export", self.r_settings_export)
        a("POST", r"/api/settings/import", self.r_settings_import)
        a("POST", r"/api/settings/reset", self.r_settings_reset)
        a("POST", r"/api/providers/test", self.r_provider_test)
        a("POST", r"/api/providers/models", self.r_provider_models)
        a("GET", r"/api/lmstudio", self.r_lmstudio)
        a("POST", r"/api/lmstudio/scan", self.r_lmstudio_scan)

        for kind, store in (("characters", self.store.characters), ("worldbuildings", self.store.worldbuildings)):
            a("GET", rf"/api/{kind}", self._cards_list(store))
            a("POST", rf"/api/{kind}", self._cards_save(store, None))
            a("GET", rf"/api/{kind}/(?P<cid>[\w-]+)", self._cards_get(store))
            a("PUT", rf"/api/{kind}/(?P<cid>[\w-]+)", self._cards_save(store, True))
            a("DELETE", rf"/api/{kind}/(?P<cid>[\w-]+)", self._cards_delete(store))
        a("POST", r"/api/characters/import", self.r_char_import)
        a("POST", r"/api/ai/character", self.r_ai_character)
        a("POST", r"/api/ai/worldbuilding", self.r_ai_worldbuilding)

        a("POST", r"/api/uploads", self.r_upload)
        a("DELETE", r"/api/uploads/(?P<uid>[\w-]+)", self.r_upload_delete)
        a("POST", r"/api/generate", self.r_generate)
        a("GET", r"/api/jobs/(?P<jid>[\w-]+)", self.r_job_get)
        a("GET", r"/api/jobs/(?P<jid>[\w-]+)/events", self.r_job_events)
        a("POST", r"/api/jobs/(?P<jid>[\w-]+)/cancel", self.r_job_cancel)

        a("GET", r"/api/projects", self.r_projects)
        a("GET", r"/api/projects/(?P<pid>[\w-]+)", self.r_project_get)
        a("PUT", r"/api/projects/(?P<pid>[\w-]+)", self.r_project_put)
        a("DELETE", r"/api/projects/(?P<pid>[\w-]+)", self.r_project_delete)
        a("POST", r"/api/projects/(?P<pid>[\w-]+)/edit", self.r_project_edit)
        a("POST", r"/api/projects/(?P<pid>[\w-]+)/rebuild", self.r_project_rebuild)
        a("GET", r"/api/projects/(?P<pid>[\w-]+)/download", self.r_project_download)

        a("GET", r"/api/hf/search", self.r_hf_search)
        a("GET", r"/api/hf/files", self.r_hf_files)
        a("GET", r"/api/hf/local", self.r_hf_local)
        a("GET", r"/api/storage", self.r_storage)
        a("POST", r"/api/storage/optimize", self.r_storage_optimize)
        a("POST", r"/api/hf/download", self.r_hf_download)
        a("DELETE", r"/api/hf/local/(?P<name>[^/]+)", self.r_hf_delete)

        a("POST", r"/api/voice/tts", self.r_tts)
        a("POST", r"/api/voice/stt", self.r_stt)

        a("GET", r"/api/play/(?P<pid>[\w-]+)/info", self.r_play_info)
        a("POST", r"/api/play/(?P<pid>[\w-]+)/llm", self.r_play_llm)
        a("GET", r"/api/play/(?P<pid>[\w-]+)/save", self.r_play_save_get)
        a("PUT", r"/api/play/(?P<pid>[\w-]+)/save", self.r_play_save_put)
        a("POST", r"/api/play/(?P<pid>[\w-]+)/save", self.r_play_save_put)
        a("POST", r"/api/play/(?P<pid>[\w-]+)/tts", self.r_tts)
        a("POST", r"/api/play/(?P<pid>[\w-]+)/stt", self.r_stt)
        a("GET", r"/play/(?P<pid>[\w-]+)", self.r_play_redirect)
        a("GET", r"/play/(?P<pid>[\w-]+)/(?:v(?P<n>\d+)/)?(?P<rest>.*)", self.r_play_file)

        self.avatar_routes = AvatarRoutes(self)
        self.avatar_routes.register()
        self.chat_routes = ChatRoutes(self)
        self.chat_routes.register()
        self.game_routes = GameRoutes(self)
        self.game_routes.register()
        self.canvas_routes = CanvasRoutes(self)
        self.canvas_routes.register()
        self.mobile = Mobile(self.store.home, self.bind_host)
        self.mobile_routes = MobileRoutes(self)
        self.mobile_routes.register()
        self.remote = Remote(self.store.home)
        a = self.add
        a("GET", r"/api/remote", self.r_remote)
        a("POST", r"/api/remote", self.r_remote_do)
        self.auth_routes = AuthRoutes(self)
        self.auth_routes.register()
        self.studio_routes = StudioRoutes(self)
        self.studio_routes.register()
        self.preinstalled_routes = PreinstalledRoutes(self)
        self.preinstalled_routes.register()
        self.computer_routes = ComputerRoutes(self)   # cria `self.computer` (o gerenciador de tarefas)
        self.computer_routes.register()
        self.code_routes = CodeRoutes(self)   # cria `self.code` (pastas, sessões e execuções do Code)
        self.code_routes.register()

    # ----- estado / configurações
    def r_state(self, req: "Request") -> None:
        s = self.store.get_settings()
        req.json({
            "version": __version__, "disk_version": _disk_version(), "hardware": hardware_info(), "native": _native_status(), "home": str(self.store.home),
            "presets": describe_presets(), "settings": self.store.public_settings(),
            "configured": [pid for pid in s["providers"] if s["providers"][pid].get("api_key") or s["providers"][pid].get("model") or s["providers"][pid].get("base_url")],
        })

    def r_team(self, req: "Request") -> None:
        """As opções de equipe de TODAS as seções: 1/4/8/12/16 agentes e os oito níveis de esforço (Low … Omni)."""
        req.json(team.options())

    def r_settings_get(self, req: "Request") -> None:
        req.json(self.store.public_settings())

    def r_settings_put(self, req: "Request") -> None:
        body = req.body_json()
        if not isinstance(body, dict):
            raise HttpError(400, "JSON inválido")
        self.store.save_settings(body)
        req.json(self.store.public_settings())

    def r_settings_export(self, req: "Request") -> None:
        """Baixa as configurações como arquivo, sem chaves de API nem tokens."""
        from . import uiprefs

        data = uiprefs.export_settings(self.store.get_settings())
        req.bytes(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8")

    def r_settings_import(self, req: "Request") -> None:
        from . import uiprefs

        body = req.body_json()
        try:
            patch = uiprefs.import_patch(body)
        except ValueError as exc:
            raise HttpError(400, str(exc))
        self.store.save_settings(patch)
        req.json({"imported": sorted(patch), "settings": self.store.public_settings()})

    def r_settings_reset(self, req: "Request") -> None:
        """Volta uma seção das configurações ao padrão (ui, generation, characters, avatars, games). Chaves de API nunca são tocadas."""
        import copy

        from . import uiprefs
        from .storage import DEFAULT_SETTINGS

        body = req.body_json()
        section = str(body.get("section") or "") if isinstance(body, dict) else ""
        if section not in uiprefs.RESETTABLE:
            raise HttpError(400, "Seção inválida. Opções: " + ", ".join(uiprefs.RESETTABLE))
        with self.store._lock:
            current = self.store.get_settings()
            keep = (current.get("code") or {}).get("github", {}).get("token", "") if section == "code" else ""
            current[section] = copy.deepcopy(DEFAULT_SETTINGS[section])
            if keep:   # «restaurar padrões» nunca apaga chaves/tokens
                current["code"]["github"]["token"] = keep
            if section == "ui":
                current["ui"]["welcome_done"] = True  # restaurar a aparência não reabre as boas-vindas
            write_json(self.store.settings_path, current, private=True)
        req.json(self.store.public_settings())

    def r_provider_test(self, req: "Request") -> None:
        body = req.body_json()
        try:
            provider = self._provider_from_request(body)
            started = time.time()
            reply = provider.test()
            req.json({"ok": True, "reply": reply, "ms": int((time.time() - started) * 1000), "model": provider.model})
        except ProviderError as exc:
            req.json({"ok": False, "error": str(exc)})

    def r_provider_models(self, req: "Request") -> None:
        body = req.body_json()
        try:
            provider = self._provider_from_request(body)
            req.json({"ok": True, "models": provider.list_models()})
        except ProviderError as exc:
            req.json({"ok": False, "error": str(exc), "models": []})

    def r_lmstudio(self, req: "Request") -> None:
        """Estado do LM Studio agora: servidor rodando?, modelos de chat (carregados primeiro) e o que o ASTA vai usar."""
        from .providers import lmstudio

        cfg = provider_config(self.store.get_settings(), "lmstudio")
        info = lmstudio.probe(req.query.get("url", [""])[0] or cfg.get("base_url") or "", cfg.get("api_key") or "", timeout=3)
        lmstudio.forget()  # o usuário acabou de pedir: o cache não pode esconder o que mudou (ligou o servidor, carregou um modelo)
        info["selected"] = cfg.get("model") or (info["loaded"][0] if info["loaded"] else "")
        info["hint"] = lmstudio.HOW_TO_START
        req.json(info)

    def _remote_guard(self, req: "Request") -> None:
        if self.mobile.strict and self.mobile.cookie_ok(req.headers.get("Cookie", "")):
            return
        if self.mobile.is_remote(req.h.client_address[0], req.headers):
            raise HttpError(403, "Só no computador onde o ASTA roda.")
        self.remote.local_port = req.h.server.server_address[1]

    def r_remote(self, req: "Request") -> None:
        """Acesso de fora de casa ao LM Studio (túnel + proxy com código): estado."""
        self._remote_guard(req)
        req.json(self.remote.status())

    def r_remote_do(self, req: "Request") -> None:
        self._remote_guard(req)
        body = req.body_json()
        act = str(body.get("action") or "")
        if act == "enable":
            self.remote.set_enabled(bool(body.get("on", True)))
        elif act == "install":
            self.remote.install()
        elif act == "start":
            self.remote.start()
        elif act == "stop":
            self.remote.stop()
        elif act == "rotate":
            self.remote.rotate()
        else:
            raise HttpError(400, "Ação desconhecida")
        req.json(self.remote.status())

    def r_lmstudio_scan(self, req: "Request") -> None:
        """Procura o LM Studio de outro computador na rede local (a pedido do usuário; o celular usa isto para achar o do computador)."""
        from .providers import lmstudio

        req.body_json()
        req.json({"servers": lmstudio.scan()})

    # ----- cards
    def _cards_list(self, store):
        return lambda req: req.json(store.list())

    def _cards_get(self, store):
        def fn(req, cid):
            card = store.get(cid)
            if not card:
                raise HttpError(404, "Card não encontrado")
            req.json(card)
        return fn

    def _cards_save(self, store, update):
        def fn(req, cid=None):
            body = req.body_json()
            if update and not store.get(cid):
                raise HttpError(404, "Card não encontrado")
            req.json(store.save(body, cid if update else None))
        return fn

    def _cards_delete(self, store):
        def fn(req, cid):
            if not store.delete(cid):
                raise HttpError(404, "Card não encontrado")
            req.json({"ok": True})
        return fn

    def r_char_import(self, req: "Request") -> None:
        raw = req.body_bytes(10 * 1024 * 1024)
        try:
            card = character_from_png(raw) if raw[:4] == b"\x89PNG" else import_character(json.loads(raw.decode("utf-8")))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HttpError(400, f"Não foi possível importar: {exc}")
        req.json(self.store.characters.save(card))

    def _ai_card(self, req: "Request", kind: str) -> None:
        body = req.body_json()
        desc = text(body.get("description"), "", 4000)
        if not desc:
            raise HttpError(400, "Descreva o que você quer criar.")
        settings = self.store.get_settings()
        provider, _ = self.provider("generation", settings)
        mode = settings["generation"].get("content", "free")
        from .agents import prompts, rulebased

        try:
            if provider.id == "demo":
                raise ValueError("demo")  # sem IA: cai no rascunho simples abaixo
            if kind == "character":
                wb = self.store.worldbuildings.get(body.get("worldbuilding_id") or "") if body.get("worldbuilding_id") else None
                system = prompts.system_prompt("characters", "the same language as the user's description", mode)
                obj, _ = call_json(
                    provider, system,
                    "Create ONE character card from the description in INPUT_JSON.need[0].description. "
                    'Output {"characters": [ ...exactly one card... ]} following the usual schema.' + prompts.CHARACTERS.split("Output JSON:")[1],
                    {"brief": {"language": "auto"}, "need": [{"id": slugify(desc[:24], "npc"), "name": "", "role": "", "description": desc}],
                     "existing": [], "worldbuilding": {"name": wb["name"], "system_prompt": wb["system_prompt"]} if wb else None,
                     "detail": settings["characters"].get("detail", "detailed")},
                    max_tokens=2500,
                )
                cards = obj.get("characters") or []
                if not cards:
                    raise ValueError("sem card")
                card = normalize_character(cards[0])
            else:
                system = prompts.system_prompt("worldbuilding", "the same language as the user's description", mode)
                obj, _ = call_json(
                    provider, system,
                    "Write worldbuilding rules for virtual worlds from the description in INPUT_JSON.description. "
                    'Output {"name": str, "tags": [str], "system_prompt": str}. The system_prompt states the setting, tone, physical and social '
                    "rules, tech/magic level, factions, taboos and how characters should speak and behave (150-400 words).",
                    {"description": desc}, max_tokens=2500,
                )
                from .cards import normalize_worldbuilding

                card = normalize_worldbuilding(obj)
        except ValueError:
            # provedor Demo ou resposta inválida: cria um rascunho editável simples
            if kind == "character":
                card = normalize_character({"name": desc.split(".")[0][:40] or "Novo personagem", "system_prompt": desc})
            else:
                from .cards import normalize_worldbuilding

                card = normalize_worldbuilding({"name": desc.split(".")[0][:40] or "Novo worldbuilding", "system_prompt": desc})
        req.json(card)  # rascunho: o navegador mostra no editor e o usuário salva

    def r_ai_character(self, req: "Request") -> None:
        try:
            self._ai_card(req, "character")
        except ProviderError as exc:
            raise HttpError(502, str(exc))

    def r_ai_worldbuilding(self, req: "Request") -> None:
        try:
            self._ai_card(req, "worldbuilding")
        except ProviderError as exc:
            raise HttpError(502, str(exc))

    # ----- uploads e geração
    def r_upload(self, req: "Request") -> None:
        settings = self.store.get_settings()
        limit = int(settings["server"].get("max_upload_mb", 200)) * 1024 * 1024
        length = req.content_length()
        if length > limit:
            raise HttpError(413, f"Arquivo maior que o limite de {limit // 1024 // 1024} MB")
        name = urllib.parse.unquote(req.headers.get("X-Filename", "arquivo"))
        meta = self.store.save_upload_stream(name, req.headers.get("Content-Type", ""), req.rfile, length)
        req.json(meta)

    def r_upload_delete(self, req: "Request", uid: str) -> None:
        req.json({"ok": self.store.delete_upload(uid)})

    def r_generate(self, req: "Request") -> None:
        body = req.body_json()
        running = self.jobs.running("generate")
        if running:
            raise HttpError(409, json.dumps({"job_id": running.id}))
        if not (text(body.get("prompt"), "") or body.get("attachment_ids") or body.get("worldbuilding_id") or body.get("character_ids")):
            raise HttpError(400, "Escreva um prompt ou anexe algo para gerar o mundo.")
        pipeline_req = {
            "prompt": text(body.get("prompt"), "", 20000), "attachment_ids": [x for x in _as_list(body.get("attachment_ids")) if isinstance(x, str)][:40],
            "worldbuilding_id": text(body.get("worldbuilding_id"), "", 60), "character_ids": [x for x in _as_list(body.get("character_ids")) if isinstance(x, str)][:24],
            "settings": {**(body.get("settings") if isinstance(body.get("settings"), dict) else {}), **team.request_team(body)},
            "project_id": text(body.get("project_id"), "", 60),
        }

        def work(job: Job) -> None:
            Pipeline(self.store, job.emit, lambda: job.cancelled).run(pipeline_req)

        job = self.jobs.start("generate", work)
        req.json({"job_id": job.id})

    def r_job_get(self, req: "Request", jid: str) -> None:
        job = self.jobs.get(jid)
        if not job:
            raise HttpError(404, "Tarefa não encontrada")
        req.json({"id": job.id, "kind": job.kind, "status": job.status, "events": len(job.events)})

    def r_job_cancel(self, req: "Request", jid: str) -> None:
        job = self.jobs.get(jid)
        if not job:
            raise HttpError(404, "Tarefa não encontrada")
        job.cancel()
        req.json({"ok": True})

    def r_job_events(self, req: "Request", jid: str) -> None:
        job = self.jobs.get(jid)
        if not job:
            raise HttpError(404, "Tarefa não encontrada")
        idx = int(req.query.get("from", ["0"])[0] or 0)
        req.sse_start()
        while True:
            with job.cond:
                while idx >= len(job.events) and job.status == "running":
                    job.cond.wait(timeout=10)
                    if idx >= len(job.events) and job.status == "running":
                        break
                batch = job.events[idx:]
                status = job.status
            for ev in batch:
                req.sse_send(ev)
            idx += len(batch)
            if not batch and status == "running":
                req.sse_comment("keepalive")
            if status != "running" and idx >= len(job.events):
                req.sse_send({"type": "end", "status": status})
                return

    # ----- projetos
    def _summary(self, p: dict) -> dict:
        return {
            "id": p["id"], "kind": p.get("kind", "world"), "genre": p.get("genre", ""), "name": p["name"], "description": p.get("description", ""), "tags": p["tags"],
            "created": p["created"], "updated": p["updated"], "current": p["current"], "versions": len(p["versions"]),
            "palette": p.get("palette", {}), "settings": p.get("settings", {}), "language": p.get("language", ""),
            "attachments": p.get("attachments", []),
            "last": (p["versions"][-1] if p["versions"] else None),
        }

    def r_projects(self, req: "Request") -> None:
        kind = req.query.get("kind", [""])[0] or None
        req.json([self._summary(p) for p in self.store.list_projects(kind)])

    def r_project_get(self, req: "Request", pid: str) -> None:
        project = self.store.get_project(pid)
        if not project:
            raise HttpError(404, "Projeto não encontrado")
        if project["kind"] == "game2d":
            gver = self.store.load_game_version(pid)
            req.json({**self._summary(project), "versions_list": project["versions"], "game": gver["game"] if gver else None})
            return
        ver = self.store.load_version(pid)
        req.json({**self._summary(project), "versions_list": project["versions"], "worldbuilding_id": project.get("worldbuilding_id", ""),
                  "character_ids": project.get("character_ids", []),
                  "world": ver["world"] if ver else None, "characters": ver["characters"] if ver else []})

    def r_project_put(self, req: "Request", pid: str) -> None:
        project = self.store.get_project(pid)
        if not project:
            raise HttpError(404, "Projeto não encontrado")
        body = req.body_json()
        if "name" in body:
            project["name"] = text(body["name"], project["name"], 80)
        if "description" in body:
            project["description"] = text(body["description"], "", 600)
        if "tags_custom" in body:
            project["tags"]["custom"] = list(dict.fromkeys(text(t, "", 30).lower() for t in body["tags_custom"] if text(t, "", 30)))[:20]
        if "tags_auto" in body:
            project["tags"]["auto"] = list(dict.fromkeys(text(t, "", 30).lower() for t in body["tags_auto"] if text(t, "", 30)))[:20]
        self.store.save_project(project)
        req.json(self._summary(project))

    def r_project_delete(self, req: "Request", pid: str) -> None:
        if not self.store.delete_project(pid):
            raise HttpError(404, "Projeto não encontrado")
        req.json({"ok": True})

    def r_project_edit(self, req: "Request", pid: str) -> None:
        body = req.body_json()
        if (self.store.get_project(pid) or {}).get("kind") == "game2d":
            raise HttpError(400, "Jogos 2D são atualizados pela IA (botão Atualizar) ou editando data/game.json no ZIP.")
        try:
            project = create_edit_version(self.store, pid, body if isinstance(body, dict) else {})
        except ValueError as exc:
            raise HttpError(404, str(exc))
        req.json(self._summary(project))

    def r_project_rebuild(self, req: "Request", pid: str) -> None:
        """Gera uma nova versão com o motor mais recente (3D ou 2D), sem chamar a IA."""
        if (self.store.get_project(pid) or {}).get("kind") == "game2d":
            try:
                req.json(self._summary(rebuild_game(self.store, pid, f"Motor do jogo atualizado (ASTA {__version__}).")))
            except ValueError as exc:
                raise HttpError(404, str(exc))
            return
        try:
            project = create_edit_version(self.store, pid, {"_summary": f"Motor do jogo atualizado (ASTA {__version__})."})
        except ValueError as exc:
            raise HttpError(404, str(exc))
        req.json(self._summary(project))

    def r_project_download(self, req: "Request", pid: str) -> None:
        project = self.store.get_project(pid)
        n = int(req.query.get("v", ["0"])[0] or 0) or None
        path = self.store.zip_path(pid, n)
        if not project or not path:
            raise HttpError(404, "ZIP não encontrado")
        fname, mime = builder.zip_name(project, n or project["current"])
        req.file(path, mime, download_name=fname)

    # ----- Hugging Face
    def _hf_token(self) -> str:
        return self.store.get_settings()["hf"].get("token", "")

    def r_hf_search(self, req: "Request") -> None:
        q = (req.query.get("q", [""])[0] or "gguf").strip()
        try:
            req.json({"results": hf.search(q, self._hf_token(), kind=hf.check_kind(req.query.get("kind", ["text"])[0] or "text"))})
        except ProviderError as exc:
            raise HttpError(502, str(exc))

    def r_hf_files(self, req: "Request") -> None:
        try:
            req.json({"files": hf.list_files(req.query.get("repo", [""])[0], self._hf_token(), hardware_info().get("ram_gb") or 0)})
        except ProviderError as exc:
            raise HttpError(502, str(exc))

    def r_hf_local(self, req: "Request") -> None:
        kind = req.query.get("kind", ["text"])[0] or "text"  # sem `kind`: só os de texto (o que o provedor de IA lista)
        try:
            models = hf.local_models(self.store.models_dir, kind if kind == "all" else hf.check_kind(kind))
            for m in models:
                if m.get("kind") == "text":   # contexto em que o modelo foi treinado e custo do cache de atenção (lidos do cabeçalho, sem carregar os pesos): a tela mostra até onde dá para ir
                    info = native.model_info(hf.kind_dir(self.store.models_dir, "text") / m["name"]) or {}
                    m["ctx_train"], m["kv_bytes_per_token"] = int(info.get("ctx_train") or 0), int(info.get("kv_bytes_per_token") or 0)
            req.json({"models": models, "kinds": {k: v["label"] for k, v in hf.GGUF_KINDS.items()}})
        except ProviderError as exc:
            raise HttpError(400, str(exc))

    def r_storage(self, req: "Request") -> None:
        """Uso do disco por área, sobras e arquivos duplicados (só leitura)."""
        from . import storage_opt

        req.json(storage_opt.report(self.store.home))

    def r_storage_optimize(self, req: "Request") -> None:
        """Libera espaço: remove sobras e troca duplicados por links físicos. `apply: false` (padrão) só mostra a prévia."""
        from . import storage_opt

        b = req.body_json()
        b = b if isinstance(b, dict) else {}
        if self.jobs.running("generate"):
            raise HttpError(409, "Há uma geração em andamento. Espere terminar para otimizar o armazenamento.")
        req.json(storage_opt.optimize(self.store.home, dedupe=b.get("dedupe") is not False, clean=b.get("clean") is not False, apply=b.get("apply") is True))

    def r_hf_delete(self, req: "Request", name: str) -> None:
        name = urllib.parse.unquote(name)
        try:
            folder = hf.kind_dir(self.store.models_dir, req.query.get("kind", ["text"])[0] or "text")
        except ProviderError as exc:
            raise HttpError(400, str(exc))
        path = folder / safe_filename(name)
        if not path.exists() or path.suffix != ".gguf":
            raise HttpError(404, "Modelo não encontrado")
        for p in hf.shard_files(folder, path.name):  # modelo dividido: apaga todas as partes
            p.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        req.json({"ok": True})

    def r_hf_download(self, req: "Request") -> None:
        body = req.body_json()
        repo = text(body.get("repo"), "", 200)
        if not text(body.get("quant"), "", 40):  # o ASTA nunca escolhe a quantização pelo usuário
            raise HttpError(400, "Escolha a quantização antes de baixar (campo quant, ex.: Q4_K_M).")
        names = [text(f, "", 260) for f in body.get("files")][:99] if isinstance(body.get("files"), list) else [text(body.get("file"), "", 260)]
        names = [n for n in names if n]
        if not names:
            raise HttpError(400, "Escolha uma quantização para baixar.")
        try:
            kind = text(body.get("kind"), "text", 8) or "text"
            dest = hf.kind_dir(self.store.models_dir, kind, create=True)
        except ProviderError as exc:
            raise HttpError(400, str(exc))
        sizes = {n: int(body["sizes"].get(n, 0)) for n in names} if isinstance(body.get("sizes"), dict) and all(isinstance(v, (int, float)) for v in body["sizes"].values()) else {}

        def work(job: Job) -> None:
            job.emit({"type": "start", "file": names[0], "parts": len(names)})
            last = [0.0]

            def progress(done: int, total: int) -> None:
                if time.time() - last[0] > 0.4:
                    last[0] = time.time()
                    job.emit({"type": "progress", "done": done, "total": total})

            path = hf.download_many(repo, names, dest, self._hf_token(), sizes, progress, lambda: job.cancelled)
            extra: list = []
            if kind in ("image", "video") and path.suffix.lower() == ".gguf":   # modelo de difusão de família conhecida (Qwen-Image, FLUX, Z-Image, Wan…): baixa junto o VAE e o codificador de texto
                from .canvas import support

                info = support.missing(dest, path.name)
                if info["missing"]:
                    job.emit({"type": "note", "message": "Baixando também os arquivos de apoio: " + ", ".join(m["label"] for m in info["missing"]) + f" (≈ {info['approx_gb']} GB)…"})
                    try:
                        extra = support.download_missing(dest, path.name, self._hf_token(), progress, lambda: job.cancelled, lambda m: job.emit({"type": "note", "message": m}))
                    except ProviderError as exc:   # o modelo já está baixado: a falha dos apoios não o desfaz (o nó oferece o botão de baixar depois)
                        job.emit({"type": "note", "message": f"Os arquivos de apoio não baixaram ({exc}); use «Baixar os arquivos de apoio» no nó."})
            job.emit({"type": "done", "name": path.name, "support": extra})

        job = self.jobs.start("download", work)
        req.json({"job_id": job.id})

    # ----- voz
    def r_tts(self, req: "Request", pid: str = "") -> None:
        body = req.body_json()
        try:
            audio, mime = voice.synthesize(self.store.get_settings(), text(body.get("text"), "", 2000), text(body.get("voice"), "", 60))
        except ProviderError as exc:
            raise HttpError(502, str(exc))
        req.bytes(audio, mime)

    def r_stt(self, req: "Request", pid: str = "") -> None:
        data = req.body_bytes(30 * 1024 * 1024)
        mime = req.headers.get("Content-Type", "audio/webm").split(";")[0]
        ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav"}.get(mime, "webm")
        try:
            txt = voice.transcribe_bytes(self.store.get_settings(), data, f"audio.{ext}", mime, req.headers.get("X-Lang", ""))
        except ProviderError as exc:
            raise HttpError(502, str(exc))
        req.json({"text": txt})

    # ----- jogo hospedado (/play)
    def _project_or_404(self, pid: str) -> dict:
        project = self.store.get_project(pid)
        if not project or not project.get("current"):
            raise HttpError(404, "Mundo não encontrado")
        return project

    def r_play_info(self, req: "Request", pid: str) -> None:
        self._project_or_404(pid)
        settings = self.store.get_settings()
        provider, prov_id = self.provider("characters", settings)
        req.json({"provider": prov_id, "model": provider.model, "tts": voice.tts_enabled(settings), "stt": voice.stt_enabled(settings),
                  "tts_voice": settings["voice"]["tts"].get("voice", "")})

    def r_play_llm(self, req: "Request", pid: str) -> None:
        self._project_or_404(pid)
        body = req.body_json()
        msgs = [{"role": m["role"], "content": str(m["content"])} for m in (body.get("messages") or [])[-80:]
                if isinstance(m, dict) and m.get("role") in ("system", "user", "assistant") and isinstance(m.get("content"), str)]
        if not msgs or sum(len(m["content"]) for m in msgs) > 80000:
            raise HttpError(400, "Mensagens inválidas")
        settings = self.store.get_settings()
        provider, _ = self.provider("characters", settings)
        max_tokens = int(min(max(int(body.get("max_tokens") or 500), 16), 2000))
        temperature = float(min(max(float(body.get("temperature") if body.get("temperature") is not None else 0.9), 0), 2))
        req.sse_start()
        try:
            for chunk in provider.chat(msgs, temperature=temperature, max_tokens=max_tokens, stream=True):  # type: ignore[union-attr]
                req.sse_send({"delta": chunk})
            req.sse_send({"done": True})
        except ProviderError as exc:
            req.sse_send({"error": str(exc)})

    def r_play_save_get(self, req: "Request", pid: str) -> None:
        self._project_or_404(pid)
        from .util import read_json

        path = self.store.save_path(pid)
        req.json(read_json(path, {}) if path else {})

    def r_play_save_put(self, req: "Request", pid: str) -> None:
        self._project_or_404(pid)
        data = req.body_json(limit=4 * 1024 * 1024)
        from .util import write_json

        path = self.store.save_path(pid)
        if path is None:
            raise HttpError(400, "Projeto inválido")
        write_json(path, data)
        req.json({"ok": True})

    def r_play_redirect(self, req: "Request", pid: str) -> None:
        req.redirect(f"/play/{pid}/")

    def r_play_file(self, req: "Request", pid: str, n: Optional[str], rest: str) -> None:
        project = self._project_or_404(pid)
        ver = int(n) if n else project["current"]
        pkg = self.store.package_dir(pid, ver)
        if not pkg:
            raise HttpError(404, "Versão não encontrada")
        rest = urllib.parse.unquote(rest) or "Game.html"
        if rest == "code/config.js":
            cfg = {"mode": "hosted", "project": pid, "version": ver, "api": f"/api/play/{pid}"}
            req.bytes(builder.js_data("ASTA_CONFIG", cfg).encode("utf-8"), MIME[".js"])
            return
        if not any(rest == a or (a.endswith("/") and rest.startswith(a)) for a in PLAY_ALLOWED):
            raise HttpError(404, "Arquivo não encontrado")
        req.static(pkg, rest)

    # ----- web ui estática
    def serve_static(self, req: "Request") -> None:
        rel = urllib.parse.unquote(req.path.lstrip("/")) or "index.html"
        if rel == "sw.js":  # service worker do app mobile, carimbado com a versão (muda quando o ASTA é atualizado)
            data = (WEB_DIR / "sw.js").read_text(encoding="utf-8").replace("__ASTA_VERSION__", __version__).encode("utf-8")
            req._head(200, "text/javascript; charset=utf-8", len(data), {"Service-Worker-Allowed": "/"})
            if req.method != "HEAD":
                req.h.wfile.write(data)
            return
        target = (WEB_DIR / rel).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            if "." in rel.rsplit("/", 1)[-1]:
                raise HttpError(404, "Não encontrado")
            target = WEB_DIR / "index.html"
        req.file(target, guess_mime(str(target)))


# --------------------------------------------------------------------------- requisição


def _as_list(v):
    """Lista vinda do JSON do navegador/API: qualquer outra coisa vira lista vazia (em vez de um erro 500)."""
    return v if isinstance(v, list) else []


class Request:
    def __init__(self, handler: "Handler", method: str):
        self.h = handler
        self.method = method
        parsed = urllib.parse.urlsplit(handler.path)
        self.path = parsed.path
        self.query = urllib.parse.parse_qs(parsed.query)
        self.headers = handler.headers
        self.rfile = handler.rfile
        self._sse = False

    # entrada
    def content_length(self) -> int:
        try:
            return max(0, int(self.headers.get("Content-Length") or 0))
        except ValueError:
            return 0

    def body_bytes(self, limit: int = 8 * 1024 * 1024) -> bytes:
        n = self.content_length()
        if n > limit:
            raise HttpError(413, "Corpo da requisição muito grande")
        self._body_read = True
        return self.rfile.read(n) if n else b""

    def body_json(self, limit: int = 8 * 1024 * 1024) -> Any:
        raw = self.body_bytes(limit)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise HttpError(400, "JSON inválido")
        if not isinstance(data, dict):  # todas as rotas esperam um objeto: lista/texto/número virariam um erro 500 lá dentro
            raise HttpError(400, "JSON inválido: esperava um objeto {…}")
        return data

    # saída
    def _head(self, status: int, mime: str, length: Optional[int], extra: Optional[Dict[str, str]] = None) -> None:
        h = self.h
        h.send_response(status)
        headers = {"Content-Type": mime, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
        if length is not None:
            headers["Content-Length"] = str(length)
        headers.update(extra or {})  # `extra` pode sobrescrever (ex.: Cache-Control de mídias imutáveis)
        for k, v in headers.items():
            h.send_header(k, v)
        h.end_headers()

    def json(self, obj: Any, status: int = 200) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._head(status, "application/json; charset=utf-8", len(data))
        if self.method != "HEAD":
            self.h.wfile.write(data)

    def bytes(self, data: bytes, mime: str, status: int = 200) -> None:
        self._head(status, mime, len(data))
        if self.method != "HEAD":
            self.h.wfile.write(data)

    def file(self, path: Path, mime: str, download_name: str = "", cache: bool = False) -> None:
        """Envia um arquivo, com suporte a `Range` (necessário p/ buscar em <video>/<audio>)."""
        size = path.stat().st_size
        extra = {"Accept-Ranges": "bytes"}
        if cache:  # arquivos com id único (nunca mudam)
            extra["Cache-Control"] = "private, max-age=3600"
        if download_name:
            extra["Content-Disposition"] = f'attachment; filename="{safe_filename(download_name)}"'
        status, start, end = 200, 0, size - 1
        rng = (self.headers.get("Range") or "").strip()
        m = re.match(r"^bytes=(\d*)-(\d*)$", rng)
        if m and size and (m.group(1) or m.group(2)):
            a, b = m.groups()
            if not a:  # sufixo: os últimos N bytes
                start, end = max(0, size - int(b)), size - 1
            else:
                start, end = int(a), min(int(b), size - 1) if b else size - 1
            if start > end or start >= size:
                self._head(416, "text/plain", 0, {"Content-Range": f"bytes */{size}"})
                return
            status = 206
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        length = max(0, end - start + 1) if size else 0
        self._head(status, mime, length, extra)
        if self.method == "HEAD":
            return
        with open(path, "rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk:
                    break
                self.h.wfile.write(chunk)
                left -= len(chunk)

    def static(self, root: Path, rel: str) -> None:
        target = (root / rel).resolve()
        if not str(target).startswith(str(root.resolve())) or not target.is_file():
            raise HttpError(404, "Arquivo não encontrado")
        self.file(target, guess_mime(rel))

    def redirect(self, url: str) -> None:
        self._head(302, "text/plain", 0, {"Location": url})

    def sse_start(self) -> None:
        if not getattr(self, "_body_read", False):  # corpo não lido (ex.: «regenerar» manda {}): fechar o socket com dados pendentes dá RST (macOS) e corta a resposta
            try:
                n = self.content_length()
                if 0 < n <= 1024 * 1024:
                    self._body_read = True
                    self.rfile.read(n)
            except (HttpError, OSError, ValueError):
                pass
        self._sse = True
        self.h.send_response(200)
        self.h.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.h.send_header("Cache-Control", "no-cache, no-transform")
        self.h.send_header("X-Accel-Buffering", "no")
        self.h.send_header("Connection", "close")
        self.h.end_headers()
        self.h.wfile.flush()

    def sse_send(self, obj: Any) -> None:
        self.h.wfile.write(b"data: " + json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n\n")
        self.h.wfile.flush()

    def sse_comment(self, text_: str) -> None:
        self.h.wfile.write(f": {text_}\n\n".encode("utf-8"))
        self.h.wfile.flush()


def is_tunnel_request(client_ip: str, headers) -> bool:
    """Veio pelo túnel do cloudflared: ele conecta de 127.0.0.1 e acrescenta os cabeçalhos «cf-…»."""
    return is_loopback(client_ip) and any(k.lower().startswith("cf-") or k.lower() in _FORWARD_HEADERS for k, v in headers.items() if v)


class Handler(BaseHTTPRequestHandler):
    app: App
    server_version = "ASTA/" + __version__
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:  # silencioso; erros vão para stderr via handler
        pass

    def _handle(self, method: str) -> None:
        req = Request(self, method)
        try:
            if not self.app.host_allowed(self.headers.get("Host", "")):
                raise HttpError(403, "Host não permitido")
            if method in ("POST", "PUT", "DELETE"):
                origin = self.headers.get("Origin")
                if origin:
                    if urllib.parse.urlsplit(origin).netloc != self.headers.get("Host", ""):
                        raise HttpError(403, "Origem não permitida")
            path = req.path
            if path.startswith("/lm/"):   # LM Studio do computador para fora de casa: tem código próprio (ver remote.py), não usa o cookie de pareamento
                self.app.remote.handle(req, self.app.store.get_settings())
                return
            if self.app.remote.tunnel_active() and is_tunnel_request(self.client_address[0], self.headers):   # pelo túnel só passa o LM Studio
                raise HttpError(404, "Rota não encontrada")
            if not self.app.mobile.allowed(self.client_address[0], self.headers, path):  # fora do computador, só aparelhos pareados (QR)
                if method in ("GET", "HEAD") and not path.startswith("/api/"):
                    req.bytes(PAIR_REQUIRED_HTML.encode("utf-8"), "text/html; charset=utf-8", 401)
                    return
                raise HttpError(401, "Aparelho não pareado: escaneie o QR code no computador.")
            if path.startswith("/api/") or path.startswith("/play/"):
                if not self.app.dispatch(req):
                    raise HttpError(404, "Rota não encontrada")
            elif method in ("GET", "HEAD"):
                self.app.serve_static(req)
            else:
                raise HttpError(405, "Método não permitido")
        except HttpError as exc:
            if req._sse:
                return
            payload: Any = {"error": exc.message}
            if exc.status == 409:
                try:
                    payload.update(json.loads(exc.message))
                except ValueError:
                    pass
            req.json(payload, exc.status)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            if not req._sse:
                try:
                    req.json({"error": f"Erro interno: {exc}"}, 500)
                except OSError:
                    pass

    def do_GET(self) -> None:
        self._handle("GET")

    def do_HEAD(self) -> None:
        self._handle("HEAD")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_DELETE(self) -> None:
        self._handle("DELETE")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64


def make_server(host: str, port: int, store: Optional[Store] = None) -> Tuple[Server, App]:
    store = store or Store()
    app = App(store, host)

    class BoundHandler(Handler):
        pass

    BoundHandler.app = app
    httpd = Server((host, port), BoundHandler)
    return httpd, app
