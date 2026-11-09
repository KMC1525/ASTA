"""O gerenciador do Code: **pastas e subpastas** (nome, uma de 8 cores vivas, recolher/expandir) que organizam as **sessões** de vibe coding; cada sessão tem o seu projeto (pasta do computador,
projeto novo ou repositório do GitHub), o seu modo (Ask/Full Access), o seu esforço e o seu provedor; **várias sessões trabalham ao mesmo tempo em segundo plano**, sem o usuário por perto,
cada uma com até 8 agentes; o estado de cada uma tem uma cor na tela (cinza: parada · cinza piscando: trabalhando · azul-claro: terminou · laranja: esperando a sua resposta).

Tudo é arquivo comum e legível em `~/.asta/code/`: `folders.json`, `sessions/<id>/session.json` (+ `inputs/`, `backups/` do desfazer, `runs/<run>.json`) e `workspaces/` (projetos novos e cópias de repositórios).
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import attachments as att
from ..computer import guard as cg
from ..providers import build_provider, resolve_provider
from ..providers.registry import PRESETS
from ..util import new_id, now_iso, num, read_json, slugify, text, write_json
from . import efforts, guard, langs, tools as T
from .engine import FINAL, MAX_AGENTS, Runner
from .github import GitHub, GitHubError, git_auth_env, parse_repo
from .workspace import Workspace

SCHEMA = "asta.code.session.v1"
MAX_SESSIONS = 8
MAX_QUEUE = 40
MAX_DEPTH = 3
COLORS = [("red", "Vermelho", "#ef4444"), ("orange", "Laranja", "#f97316"), ("yellow", "Amarelo", "#eab308"), ("green", "Verde", "#22c55e"),
          ("cyan", "Ciano", "#06b6d4"), ("blue", "Azul", "#3b82f6"), ("purple", "Roxo", "#a855f7"), ("pink", "Rosa", "#ec4899")]
COLOR_IDS = [c[0] for c in COLORS]
PUBLISH_MODES = ("none", "commit", "branch", "pr", "main")
_ID = re.compile(r"^[\w-]+$")


class CodeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def normalize_config(raw: Any) -> Dict[str, Any]:
    """`settings.code` válido (valor errado volta ao padrão)."""
    d = raw if isinstance(raw, dict) else {}
    ask = [r for r in (d.get("ask_for") if isinstance(d.get("ask_for"), list) else T.DEFAULT_ASK) if r in T.RISKS and r != T.READ]
    gh = d.get("github") if isinstance(d.get("github"), dict) else {}
    fin = d.get("finalize") if isinstance(d.get("finalize"), dict) else {}
    prov = d.get("provider") if isinstance(d.get("provider"), dict) else {}
    return {
        "mode": d.get("mode") if d.get("mode") in ("ask", "full") else "ask",
        "effort": efforts.normalize(d.get("effort")),
        "agents": int(num(d.get("agents"), 4, 1, MAX_AGENTS)),
        "max_sessions": int(num(d.get("max_sessions"), 4, 1, MAX_SESSIONS)),
        "ask_for": list(dict.fromkeys(ask)),
        "run_timeout": int(num(d.get("run_timeout"), 180, 10, 1800)),
        "max_download_mb": int(num(d.get("max_download_mb"), 200, 1, 2000)),
        "allow_main": d.get("allow_main") is not False,
        "branch_prefix": re.sub(r"[^\w/.-]", "", str(d.get("branch_prefix") or "asta/"))[:30] or "asta/",
        "git_name": text(d.get("git_name"), "", 80), "git_email": text(d.get("git_email"), "", 120),
        "credit_asta": d.get("credit_asta") is True, "credit_name": text(d.get("credit_name"), "", 80), "credit_email": text(d.get("credit_email"), "", 120),   # ASTA como co-autor dos commits
        "clone_depth": int(num(d.get("clone_depth"), 20, 0, 2000)),
        "github_mode": d.get("github_mode") if d.get("github_mode") in ("auto", "cloud", "git") else "auto",
        "github": {"api": text(gh.get("api"), "", 200), "token": str(gh.get("token") or "")[:300]},
        "finalize": {"docs": fin.get("docs") is True, "publish": fin.get("publish") if fin.get("publish") in PUBLISH_MODES else "none"},
        "editor": d.get("editor") if d.get("editor") in ("auto", "vscode", "cursor") else "auto",
        "provider": {"id": text(prov.get("id"), "", 40), "model": text(prov.get("model"), "", 120)},
    }


def _finalize(raw: Any, default: Dict[str, Any]) -> Dict[str, Any]:
    d = raw if isinstance(raw, dict) else {}
    pub = d.get("publish", default.get("publish"))
    return {"docs": bool(d.get("docs", default.get("docs"))), "publish": pub if pub in PUBLISH_MODES else "none"}


class CodeManager:
    def __init__(self, store: Any, resolve: Optional[Callable[[dict], Any]] = None):
        self.store = store
        cg.set_home(getattr(store, "home", None))   # os dados do Code ficam na mesma pasta do ASTA em uso (e essa pasta nunca é acessível à IA)
        self.lock = threading.RLock()
        self.runners: Dict[str, Runner] = {}
        self.active: set = set()
        self.queue: List[str] = []
        self.snap: Dict[str, str] = {}
        self.cv = threading.Condition()
        self.version = 0
        self.touched: Dict[str, int] = {}
        self._resolve = resolve
        self.on_finish: List[Callable[[Dict[str, Any]], None]] = []
        self.root = guard.code_dir()
        self.sessions_dir = self.root / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        guard.managed_workspaces().mkdir(parents=True, exist_ok=True)
        self.folders_file = self.root / "folders.json"
        self.fl = threading.RLock()
        self._recover()

    # ----------------------------------------------------------------- peças
    def config(self) -> Dict[str, Any]:
        return normalize_config(self.store.get_settings().get("code"))

    def github(self, settings: Optional[dict] = None) -> GitHub:
        c = normalize_config((settings or self.store.get_settings()).get("code"))["github"]
        return GitHub(c["token"], c["api"])

    def provider_for(self, settings: dict, doc: Dict[str, Any]):
        if self._resolve:
            return self._resolve(settings)
        ov = doc.get("provider") if isinstance(doc.get("provider"), dict) else {}
        if not ov.get("id"):
            ov = normalize_config(settings.get("code"))["provider"]
        pid = str(ov.get("id") or "")
        if pid and pid in PRESETS and pid != "demo":
            s = copy.deepcopy(settings)
            if ov.get("model"):
                s.setdefault("providers", {}).setdefault(pid, {})["model"] = ov["model"]
            provider = build_provider(s, pid, self.store.models_dir)
            return provider, {"id": pid, "label": PRESETS[pid].get("label", pid), "model": getattr(provider, "model", "") or "", "demo": False}
        return resolve_provider(settings, "generation", self.store.models_dir)

    def session_dir(self, sid: str) -> Path:
        return self.sessions_dir / sid

    def _file(self, sid: str) -> Optional[Path]:
        return self.sessions_dir / sid / "session.json" if _ID.match(sid or "") else None

    # ----------------------------------------------------------------- persistência e eventos
    def persist(self, doc: Dict[str, Any]) -> None:
        data = json.dumps(doc, ensure_ascii=False)
        sid = doc["id"]
        if sid in self.runners:
            self.snap[sid] = data
        else:
            self.snap.pop(sid, None)
        f = self._file(sid)
        if f:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_name(f".tmp-{threading.get_ident()}.json")
            try:
                tmp.write_text(data, encoding="utf-8")
                tmp.replace(f)
            except OSError:
                try:
                    tmp.unlink()
                except OSError:
                    pass
        self._bump(sid)

    def _bump(self, key: str) -> None:
        with self.cv:
            self.version += 1
            self.touched[key] = self.version
            if len(self.touched) > 400:
                for k in sorted(self.touched, key=self.touched.get)[:100]:  # type: ignore[arg-type]
                    self.touched.pop(k, None)
            self.cv.notify_all()

    def wait_events(self, since: int, timeout: float = 15.0) -> tuple:
        with self.cv:
            if self.version <= since:
                self.cv.wait(timeout)
            v = self.version
            keys = [k for k, ver in self.touched.items() if ver > since]
        items = [s for s in (self.summary_of(k) for k in keys if k != "folders") if s]
        return v, items, "folders" in keys

    def _recover(self) -> None:
        """Execuções que estavam rodando quando o ASTA foi fechado não continuam sozinhas: a sessão volta a ficar parada, com o aviso (o que já foi feito continua valendo e dá para desfazer)."""
        for d in self.sessions_dir.iterdir() if self.sessions_dir.is_dir() else []:
            doc = read_json(d / "session.json")
            if not isinstance(doc, dict):
                continue
            run = doc.get("run") or {}
            dirty = False
            if run.get("status") in ("queued", "running", "waiting"):
                run.update(status="failed", pendings=[], now="", finished=time.time(), error="interrompida",
                           summary=run.get("summary") or "O ASTA foi fechado durante a execução; ela foi interrompida. O que já foi feito continua valendo (dá para desfazer).")
                doc["run"], doc["state"], dirty = run, "finished", True
            if doc.get("workspace", {}).get("status") == "preparing":
                doc["workspace"].update(status="error", error="O ASTA foi fechado enquanto o repositório era preparado. Crie a sessão de novo.")
                dirty = True
            if dirty:
                try:
                    (d / "session.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
                except OSError:
                    pass

    # ----------------------------------------------------------------- pastas
    def _load_folders(self) -> List[Dict[str, Any]]:
        d = read_json(self.folders_file)
        out = []
        for f in (d.get("folders") if isinstance(d, dict) else []) or []:
            if isinstance(f, dict) and _ID.match(str(f.get("id", ""))):
                out.append({"id": f["id"], "name": text(f.get("name"), "Pasta", 60) or "Pasta", "color": f.get("color") if f.get("color") in COLOR_IDS else "blue",
                            "parent": f.get("parent") if f.get("parent") else None, "collapsed": f.get("collapsed") is True, "order": int(num(f.get("order"), 0, -1e6, 1e6))})
        ids = {f["id"] for f in out}
        for f in out:
            if f["parent"] not in ids:
                f["parent"] = None
        return out

    def _save_folders(self, folders: List[Dict[str, Any]]) -> None:
        write_json(self.folders_file, {"folders": folders})
        self._bump("folders")

    def folders(self) -> List[Dict[str, Any]]:
        with self.fl:
            return sorted(self._load_folders(), key=lambda f: (f["order"], f["name"].lower()))

    def _depth(self, folders: List[Dict[str, Any]], fid: Optional[str]) -> int:
        by = {f["id"]: f for f in folders}
        n = 0
        while fid and fid in by and n < 20:
            n += 1
            fid = by[fid]["parent"]
        return n

    def _descendants(self, folders: List[Dict[str, Any]], fid: str) -> set:
        out = {fid}
        grew = True
        while grew:
            grew = False
            for f in folders:
                if f["parent"] in out and f["id"] not in out:
                    out.add(f["id"])
                    grew = True
        return out

    def create_folder(self, name: str, color: str = "", parent: Optional[str] = None) -> Dict[str, Any]:
        name = text(name, "", 60).strip()
        if not name:
            raise CodeError(400, "Dê um nome à pasta.")
        with self.fl:
            fs = self._load_folders()
            if parent and parent not in {f["id"] for f in fs}:
                raise CodeError(404, "Pasta principal não encontrada.")
            if self._depth(fs, parent) >= MAX_DEPTH:
                raise CodeError(400, f"Dá para aninhar pastas em até {MAX_DEPTH} níveis.")
            f = {"id": new_id("fo_"), "name": name, "color": color if color in COLOR_IDS else COLOR_IDS[len(fs) % len(COLOR_IDS)], "parent": parent or None, "collapsed": False,
                 "order": max([x["order"] for x in fs] + [0]) + 1}
            fs.append(f)
            self._save_folders(fs)
            return f

    def update_folder(self, fid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self.fl:
            fs = self._load_folders()
            f = next((x for x in fs if x["id"] == fid), None)
            if not f:
                raise CodeError(404, "Pasta não encontrada.")
            if "name" in patch:
                nm = text(patch["name"], "", 60).strip()
                if not nm:
                    raise CodeError(400, "O nome da pasta não pode ficar vazio.")
                f["name"] = nm
            if "color" in patch:
                if patch["color"] not in COLOR_IDS:
                    raise CodeError(400, "Cor inválida. Escolha uma das 8 cores.")
                f["color"] = patch["color"]
            if "collapsed" in patch:
                f["collapsed"] = patch["collapsed"] is True
            if "order" in patch:
                f["order"] = int(num(patch["order"], f["order"], -1e6, 1e6))
            if "parent" in patch:
                p = patch["parent"] or None
                if p and p not in {x["id"] for x in fs}:
                    raise CodeError(404, "Pasta principal não encontrada.")
                if p and p in self._descendants(fs, fid):
                    raise CodeError(400, "Não dá para colocar uma pasta dentro dela mesma.")
                sub_depth = max(self._depth(fs, x) - self._depth(fs, fid) for x in self._descendants(fs, fid)) + 1
                if self._depth(fs, p) + sub_depth > MAX_DEPTH:
                    raise CodeError(400, f"Dá para aninhar pastas em até {MAX_DEPTH} níveis.")
                f["parent"] = p
            self._save_folders(fs)
            return f

    def delete_folder(self, fid: str) -> Dict[str, Any]:
        """Apaga a pasta; as sessões e subpastas dela sobem para a pasta de cima (nada de sessão é perdido)."""
        with self.fl:
            fs = self._load_folders()
            f = next((x for x in fs if x["id"] == fid), None)
            if not f:
                raise CodeError(404, "Pasta não encontrada.")
            for x in fs:
                if x["parent"] == fid:
                    x["parent"] = f["parent"]
            fs = [x for x in fs if x["id"] != fid]
            self._save_folders(fs)
        moved = 0
        for s in self._all_docs():
            if s.get("folder_id") == fid:
                self._set_folder(s["id"], f["parent"])
                moved += 1
        return {"ok": True, "moved_sessions": moved}

    def _set_folder(self, sid: str, folder_id: Optional[str]) -> None:
        r = self.runners.get(sid)
        doc = r.doc if r else read_json(self._file(sid))
        if isinstance(doc, dict):
            with (r.lock if r else self.lock):
                doc["folder_id"] = folder_id
                self.persist(doc)

    # ----------------------------------------------------------------- consulta
    def _all_docs(self) -> List[Dict[str, Any]]:
        out = []
        try:
            dirs = [d for d in self.sessions_dir.iterdir() if d.is_dir()]
        except OSError:
            dirs = []
        for d in dirs:
            sid = d.name
            raw = self.snap.get(sid)
            doc: Any = None
            if raw is not None and sid in self.runners:
                try:
                    doc = json.loads(raw)
                except ValueError:
                    doc = None
            if doc is None:
                doc = read_json(d / "session.json")
            if isinstance(doc, dict) and doc.get("id") == sid:
                out.append(doc)
        return out

    def get(self, sid: str) -> Optional[Dict[str, Any]]:
        if not _ID.match(sid or ""):
            return None
        raw = self.snap.get(sid)
        if raw is not None and sid in self.runners:
            try:
                return json.loads(raw)
            except ValueError:
                pass
        f = self._file(sid)
        doc = read_json(f) if f else None
        return doc if isinstance(doc, dict) and doc.get("id") == sid else None

    @staticmethod
    def summary(doc: Dict[str, Any]) -> Dict[str, Any]:
        run = doc.get("run") or {}
        steps = (run.get("plan") or {}).get("steps", [])
        ws = doc.get("workspace") or {}
        repo = ws.get("repo") or {}
        return {"id": doc["id"], "title": doc.get("title", ""), "folder_id": doc.get("folder_id"), "state": doc.get("state", "idle"), "last_status": doc.get("last_status", ""), "seen": doc.get("seen", True),
                "created": doc.get("created", ""), "updated": doc.get("updated", ""), "mode": doc.get("mode", "ask"), "effort": doc.get("effort", "high"), "agents": doc.get("agents", 4),
                "workspace": {"kind": ws.get("kind", ""), "label": ws.get("label", ""), "status": ws.get("status", "ready"), "repo": f"{repo['owner']}/{repo['name']}" if repo.get("owner") else ""},
                "goal": str(run.get("goal", ""))[:200], "run_status": run.get("status", ""), "now": run.get("now", ""), "waiting": any(p.get("answer") is None for p in run.get("pendings", [])),
                "plan_done": sum(1 for s in steps if s.get("status") == "done"), "plan_total": len(steps), "working": sum(1 for a in run.get("agents", []) if a.get("status") == "running" and str(a.get("id", "")).startswith("w")),
                "provider": (run.get("provider") or {}).get("label", ""), "messages": len(doc.get("messages", []))}

    def summary_of(self, sid: str) -> Optional[Dict[str, Any]]:
        doc = self.get(sid)
        return self.summary(doc) if doc else None

    def public(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        out = {k: v for k, v in doc.items() if k not in ("journal", "inputs_digest")}
        out["undo"] = any(not e.get("undone") for e in doc.get("journal", []))
        out["journal_size"] = len(doc.get("journal", []))
        ws = doc.get("workspace") or {}
        try:
            out["files"] = Workspace(Path(ws["path"]), self.session_dir(doc["id"]), copy.deepcopy(doc.get("journal", []))).changed_files() if ws.get("path") and Path(ws["path"]).is_dir() else []
        except (OSError, KeyError):
            out["files"] = []
        return out

    def list(self) -> List[Dict[str, Any]]:
        items = sorted(self._all_docs(), key=lambda x: x.get("updated", ""), reverse=True)
        return [self.summary(x) for x in items]

    def status(self) -> Dict[str, Any]:
        cfg = self.config()
        self._pump()
        with self.lock:
            running = sum(1 for sid in self.active if (self.get(sid) or {}).get("state") == "working")
            waiting = sum(1 for sid in self.active if (self.get(sid) or {}).get("state") == "waiting")
            queued = len(self.queue)
        finished = sum(1 for d in self._all_docs() if d.get("state") == "finished")
        git = shutil.which("git")
        ed = {k: bool(T._editor(k)[1]) for k in ("vscode", "cursor")}
        return {"mode": cfg["mode"], "effort": cfg["effort"], "agents": cfg["agents"], "max_sessions": cfg["max_sessions"], "running": running, "waiting": waiting, "queued": queued, "finished": finished,
                "limit_agents": MAX_AGENTS, "limit_sessions": MAX_SESSIONS, "android": T.IS_ANDROID, "git": bool(git), "editors": ed, "github": {"token": bool(cfg["github"]["token"]), "api": cfg["github"]["api"] or "https://api.github.com"},
                "huggingface": bool((self.store.get_settings().get("hf") or {}).get("token")), "efforts": efforts.listing(), "colors": [{"id": c[0], "label": c[1], "hex": c[2]} for c in COLORS],
                "languages": langs.catalog(), "tools": sorted(T.TOOLS), "publish_modes": list(PUBLISH_MODES), "max_depth": MAX_DEPTH}

    # ----------------------------------------------------------------- criar sessão
    def create_session(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        cfg = self.config()
        spec = spec if isinstance(spec, dict) else {}
        folder_id = spec.get("folder_id") or None
        if folder_id and folder_id not in {f["id"] for f in self.folders()}:
            raise CodeError(404, "Pasta não encontrada.")
        sid = new_id("cs_")
        ws_spec = spec.get("workspace") if isinstance(spec.get("workspace"), dict) else {}
        wtype = ws_spec.get("type") or ("local" if ws_spec.get("path") else "github" if ws_spec.get("repo") else "new")
        wsd: Dict[str, Any] = {"kind": "", "path": "", "label": "", "status": "ready", "repo": {}}
        repo_spec = ""
        if wtype == "local":
            try:
                root = guard.check_root(str(ws_spec.get("path") or ""))
            except guard.Blocked as exc:
                raise CodeError(400, str(exc)) from None
            wsd.update(kind="local", path=str(root), label=root.name)
            self._detect_git(wsd)
        elif wtype == "github":
            repo_spec = str(ws_spec.get("repo") or "")
            try:
                owner, name, ref = parse_repo(repo_spec)
            except GitHubError as exc:
                raise CodeError(400, exc.message) from None
            wsd.update(kind="cloud", path="", label=f"{owner}/{name}", status="preparing", repo={"kind": "cloud", "owner": owner, "name": name, "base_branch": ref, "branch": "", "remote": ""})
        else:
            nm = text(ws_spec.get("name"), "", 60) or text(spec.get("title"), "", 40) or "projeto"
            dest = guard.managed_workspaces() / f"{slugify(nm, 'projeto', 32)}-{sid[-6:]}"
            dest.mkdir(parents=True, exist_ok=True)
            wsd.update(kind="local", path=str(dest), label=dest.name)
        prov = spec.get("provider") if isinstance(spec.get("provider"), dict) else {}
        doc: Dict[str, Any] = {"schema": SCHEMA, "id": sid, "title": text(spec.get("title"), "", 120) or "Nova sessão", "folder_id": folder_id, "created": now_iso(), "updated": now_iso(),
                               "workspace": wsd, "mode": spec.get("mode") if spec.get("mode") in ("ask", "full") else cfg["mode"], "effort": efforts.normalize(spec.get("effort") or cfg["effort"]),
                               "agents": int(num(spec.get("agents"), cfg["agents"], 1, MAX_AGENTS)), "provider": {"id": text(prov.get("id"), "", 40), "model": text(prov.get("model"), "", 120)},
                               "finalize": _finalize(spec.get("finalize"), cfg["finalize"]), "allowed": [], "state": "idle", "seen": True, "last_status": "", "messages": [], "run": {}, "runs": [], "journal": []}
        self.persist(doc)
        if wtype == "github":
            threading.Thread(target=self._prepare_github, args=(sid, repo_spec), daemon=True, name=f"code-prep-{sid}").start()
        return self.public(doc)

    def _detect_git(self, wsd: Dict[str, Any]) -> None:
        root = Path(wsd["path"])
        if not (root / ".git").exists() or not shutil.which("git"):
            return
        env = guard.clean_env()
        try:
            br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root), capture_output=True, text=True, timeout=15, env=env, stdin=subprocess.DEVNULL).stdout.strip()
            rm = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(root), capture_output=True, text=True, timeout=15, env=env, stdin=subprocess.DEVNULL).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return
        repo: Dict[str, Any] = {"kind": "git", "branch": br, "base_branch": br if br in ("main", "master") else "main", "remote": guard.redact(rm, [])}
        try:
            o, n, _ = parse_repo(rm)
            repo.update(owner=o, name=n)
        except GitHubError:
            pass
        wsd["kind"], wsd["repo"] = "git", repo

    def _update_ws(self, sid: str, **kw: Any) -> None:
        with self.lock:
            doc = self.get(sid)
            if not doc:
                return
            repo = kw.pop("repo", None)
            doc["workspace"].update(kw)
            if repo:
                doc["workspace"].setdefault("repo", {}).update(repo)
            doc["updated"] = now_iso()
            self.persist(doc)

    def _prepare_github(self, sid: str, spec: str) -> None:
        """Baixa/clona o repositório para uma pasta do ASTA. Com `git` instalado (e fora do Android) usa `git clone`; senão baixa o ZIP pela API (modo nuvem, sem git)."""
        try:
            settings = self.store.get_settings()
            cfg = normalize_config(settings.get("code"))
            gh = self.github(settings)
            owner, name, ref = parse_repo(spec)
            info = gh.repo(owner, name)
            base = ref or info["default_branch"]
            dest = guard.managed_workspaces() / f"{owner}__{name}-{sid[-6:]}"
            shutil.rmtree(dest, ignore_errors=True)
            use_git = bool(shutil.which("git")) and not T.IS_ANDROID and cfg["github_mode"] != "cloud"
            if cfg["github_mode"] == "git" and not use_git:
                raise GitHubError("O modo «git» foi escolhido, mas o git não está instalado.")
            if use_git:
                url = f"{gh.web}/{owner}/{name}.git"
                cmd = ["git", "clone", "--quiet"] + (["--depth", str(cfg["clone_depth"])] if cfg["clone_depth"] else []) + ["--branch", base, url, str(dest)]
                env = guard.clean_env(git_auth_env(gh.token, gh.web) if gh.token else {})
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, env=env, stdin=subprocess.DEVNULL)
                except (OSError, subprocess.SubprocessError) as exc:
                    raise GitHubError(f"Não consegui rodar o git clone: {exc}") from None
                if r.returncode != 0:
                    raise GitHubError("git clone falhou: " + guard.redact((r.stderr or r.stdout)[-400:], [gh.token]))
                self._update_ws(sid, kind="git", path=str(dest), status="ready", error="", repo={"kind": "git", "owner": owner, "name": name, "base_branch": base, "branch": base, "remote": f"{gh.web}/{owner}/{name}.git"})
            else:
                gh.download_repo(owner, name, base, dest)
                self._update_ws(sid, kind="cloud", path=str(dest), status="ready", error="", repo={"kind": "cloud", "owner": owner, "name": name, "base_branch": base, "branch": "", "remote": f"{gh.web}/{owner}/{name}"})
        except GitHubError as exc:
            self._update_ws(sid, status="error", error=guard.redact(exc.message, []))
        except Exception as exc:  # noqa: BLE001
            self._update_ws(sid, status="error", error=f"{exc.__class__.__name__}: {exc}"[:300])

    # ----------------------------------------------------------------- editar sessão
    def update_session(self, sid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        r = self.runners.get(sid)
        doc = r.doc if r else self.get(sid)
        if not doc:
            raise CodeError(404, "Sessão não encontrada.")
        lock = r.lock if r else self.lock
        with lock:
            if "title" in patch:
                t = text(patch["title"], "", 120).strip()
                if not t:
                    raise CodeError(400, "O título não pode ficar vazio.")
                doc["title"] = t
            if "folder_id" in patch:
                fid = patch["folder_id"] or None
                if fid and fid not in {f["id"] for f in self.folders()}:
                    raise CodeError(404, "Pasta não encontrada.")
                doc["folder_id"] = fid
            if "mode" in patch and patch["mode"] in ("ask", "full"):
                doc["mode"] = patch["mode"]
                if r:
                    r.doc["mode"] = patch["mode"]
                    if r.ctx:
                        r.ctx.mode = patch["mode"]
            if "effort" in patch:
                doc["effort"] = efforts.normalize(patch["effort"])
            if "agents" in patch:
                doc["agents"] = int(num(patch["agents"], doc.get("agents", 4), 1, MAX_AGENTS))
            if "provider" in patch and isinstance(patch["provider"], dict):
                doc["provider"] = {"id": text(patch["provider"].get("id"), "", 40), "model": text(patch["provider"].get("model"), "", 120)}
            if "finalize" in patch:
                doc["finalize"] = _finalize(patch["finalize"], doc.get("finalize") or {})
            if patch.get("reset_allowed"):
                doc["allowed"] = []
                if r:
                    r.allowed = set()
            doc["updated"] = now_iso()
            self.persist(doc)
        return self.public(doc)

    def mark_seen(self, sid: str) -> None:
        r = self.runners.get(sid)
        doc = r.doc if r else self.get(sid)
        if not doc:
            return
        with (r.lock if r else self.lock):
            if doc.get("state") == "finished" or not doc.get("seen", True):
                doc["seen"] = True
                if doc.get("state") == "finished":
                    doc["state"] = "idle"
                self.persist(doc)

    # ----------------------------------------------------------------- enviar uma mensagem (começa uma execução)
    def send(self, sid: str, message: str, *, attachment_ids: Optional[List[str]] = None, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        doc = self.get(sid)
        if not doc:
            raise CodeError(404, "Sessão não encontrada.")
        ws = doc.get("workspace") or {}
        if ws.get("status") == "preparing":
            raise CodeError(409, "O repositório ainda está sendo preparado. Espere um instante.")
        if ws.get("status") == "error" or not ws.get("path"):
            raise CodeError(409, "O projeto desta sessão não está pronto: " + (ws.get("error") or "sem pasta de projeto") + " Crie a sessão de novo.")
        if doc.get("state") in ("working", "waiting") or sid in self.runners:
            raise CodeError(409, "A sessão ainda está trabalhando: espere terminar ou cancele.")
        message = text(message, "", 12000)
        ids = [x for x in (attachment_ids or []) if isinstance(x, str)][:30]
        if not message and not ids:
            raise CodeError(400, "Escreva o que o Code deve fazer.")
        with self.lock:
            if len(self.queue) >= MAX_QUEUE:
                raise CodeError(429, "Há execuções demais na fila. Espere algumas terminarem.")
        opts = options if isinstance(options, dict) else {}
        digest, images, names = self._take_inputs(sid, ids)
        rid = new_id("run_")
        goal = message or ("(" + ", ".join(names[:5]) + ")")
        cfg = self.config()
        doc["mode"] = opts["mode"] if opts.get("mode") in ("ask", "full") else doc.get("mode", cfg["mode"])
        if opts.get("effort"):
            doc["effort"] = efforts.normalize(opts["effort"])
        if opts.get("agents"):
            doc["agents"] = int(num(opts["agents"], doc.get("agents", 4), 1, MAX_AGENTS))
        fin = _finalize(opts.get("finalize"), doc.get("finalize") or cfg["finalize"]) if "finalize" in opts else (doc.get("finalize") or cfg["finalize"])
        doc["finalize"] = fin
        if doc.get("title") in ("", "Nova sessão"):
            doc["title"] = (goal[:57] + "…") if len(goal) > 58 else goal
        ts = now_iso()
        doc.setdefault("messages", []).append({"id": new_id("m_"), "role": "user", "text": goal, "ts": ts, "run": rid, "attachments": [{"name": n} for n in names]})
        doc["run"] = {"id": rid, "goal": goal, "status": "queued", "created": ts, "started": None, "finished": None, "plan": {"summary": "", "kind": "mixed", "steps": []}, "steps": [], "agents": [],
                      "warnings": [], "pendings": [], "checks": [], "review": None, "summary": "", "error": "", "now": "", "finalize": fin, "effort": doc["effort"], "agents_n": doc["agents"]}
        doc["state"], doc["seen"] = "working", True
        runner = Runner(self, doc, digest, images)
        with self.lock:
            self.runners[sid] = runner
            self.queue.append(sid)
        self.persist(doc)
        self._pump()
        return self.public(doc)

    def _take_inputs(self, sid: str, ids: List[str]):
        """Anexos do pedido (multimodais): os arquivos vão para `inputs/` da sessão (a IA os copia para o projeto com `use_attachment`) e o texto/imagens deles vão ao Planejador e aos agentes."""
        if not ids:
            return "", [], []
        metas = self.store.get_uploads(ids, limit=30, expand=True)
        dest = self.session_dir(sid) / "inputs"
        analyzed, names = [], []
        transcribe = None
        try:
            from .. import voice

            transcribe = voice.transcriber(self.store.get_settings())
        except Exception:  # noqa: BLE001
            transcribe = None
        for m in metas:
            src = Path(m["path"])
            if not src.is_file():
                continue
            name = re.sub(r"[\\/:*?\"<>|]+", "_", m["name"].replace("\\", "/").split("/")[-1])[:120] or "arquivo"
            try:
                dest.mkdir(parents=True, exist_ok=True)
                target = dest / name
                n = 2
                while target.exists():
                    target = dest / f"{Path(name).stem} ({n}){Path(name).suffix}"
                    n += 1
                shutil.copy2(src, target)
            except OSError:
                continue
            names.append(target.name)
            try:
                analyzed.append(att.analyze(src, m["name"], m.get("mime", ""), max_chars=12000, transcribe=transcribe))
            except Exception:  # noqa: BLE001
                continue
        for uid in {str(i).split(":", 1)[0] for i in ids}:
            self.store.delete_upload(uid)
        return att.build_digest(analyzed, max_total=40000), att.collect_images(analyzed, 4), names

    # ----------------------------------------------------------------- fila
    def _pump(self) -> None:
        with self.lock:
            cap = self.config()["max_sessions"]
            while self.queue and len(self.active) < cap:
                sid = self.queue.pop(0)
                r = self.runners.get(sid)
                if not r or r.run.get("status") != "queued":
                    continue
                self.active.add(sid)
                threading.Thread(target=r.go, daemon=True, name=f"code-{sid}").start()

    def finished(self, runner: Runner) -> None:
        doc, run = runner.doc, runner.run
        sid = doc["id"]
        with self.lock:
            self.active.discard(sid)
        with runner.lock:
            status = run.get("status") if run.get("status") in FINAL else "failed"
            doc["state"], doc["seen"], doc["last_status"] = "finished", False, status
            doc.setdefault("messages", []).append({"id": new_id("m_"), "role": "assistant", "text": (run.get("summary") or "").strip() or "—", "ts": now_iso(), "run": run["id"], "status": status})
            doc.setdefault("runs", []).append({"id": run["id"], "goal": run.get("goal", ""), "status": status, "summary": str(run.get("summary", ""))[:1500], "started": run.get("started"), "finished": run.get("finished"),
                                               "files": (run.get("files") or [])[:30], "checks": [{k: c.get(k) for k in ("label", "ok")} for c in run.get("checks", [])]})
            doc["runs"] = doc["runs"][-30:]
            rd = self.session_dir(sid) / "runs"
            try:
                rd.mkdir(parents=True, exist_ok=True)
                write_json(rd / f"{run['id']}.json", run)
            except OSError:
                pass
            self.persist(doc)
        for cb in list(self.on_finish):
            try:
                cb(self.summary(doc))
            except Exception:  # noqa: BLE001
                import traceback

                traceback.print_exc()
        with self.lock:
            self.runners.pop(sid, None)
        self.snap.pop(sid, None)
        self._pump()

    # ----------------------------------------------------------------- controle
    def cancel(self, sid: str) -> Dict[str, Any]:
        with self.lock:
            r = self.runners.get(sid)
            if r is None:
                raise CodeError(409, "A sessão não está trabalhando.")
            if sid in self.queue:
                self.queue.remove(sid)
                self.runners.pop(sid, None)
                with r.lock:
                    r.run.update(status="cancelled", finished=time.time(), summary="Cancelada antes de começar.")
                    r.doc["state"], r.doc["seen"], r.doc["last_status"] = "idle", True, "cancelled"
                    self.persist(r.doc)
                return self.public(r.doc)
        r.cancel()
        return self.get(sid) or {}

    def answer(self, sid: str, approve: bool, remember: bool = False, qid: str = "") -> Dict[str, Any]:
        r = self.runners.get(sid)
        if r is None:
            raise CodeError(409, "A sessão não está esperando resposta.")
        if not r.answer(qid, approve, remember):
            raise CodeError(409, "Não há pergunta pendente nesta sessão.")
        return {"ok": True}

    def delete(self, sid: str, purge_workspace: bool = False) -> bool:
        if sid in self.runners:
            raise CodeError(409, "A sessão ainda está trabalhando: cancele antes de apagar.")
        f = self._file(sid)
        if not f or not f.parent.is_dir():
            return False
        doc = self.get(sid) or {}
        ws = (doc.get("workspace") or {}).get("path", "")
        shutil.rmtree(f.parent, ignore_errors=True)
        if purge_workspace and ws and guard._inside(Path(ws).resolve(), guard.managed_workspaces()):   # só apaga o que o próprio ASTA criou (nunca a pasta de um projeto do usuário)
            shutil.rmtree(ws, ignore_errors=True)
        self.snap.pop(sid, None)
        self._bump(sid)
        return True

    def undo(self, sid: str, run: str = "") -> Dict[str, Any]:
        if sid in self.runners:
            raise CodeError(409, "Espere a execução terminar (ou cancele) para desfazer.")
        doc = self.get(sid)
        if not doc:
            raise CodeError(404, "Sessão não encontrada.")
        ws = doc.get("workspace") or {}
        if not ws.get("path"):
            raise CodeError(409, "A sessão não tem projeto.")
        w = Workspace(Path(ws["path"]), self.session_dir(sid), doc.setdefault("journal", []))
        if not w.undoable(run):
            raise CodeError(409, "Não há nada para desfazer.")
        notes = w.undo(run)
        doc["updated"] = now_iso()
        self.persist(doc)
        self.snap.pop(sid, None)
        return {"notes": notes, "session": self.public(doc)}

    # ----------------------------------------------------------------- navegar no projeto
    def _ws(self, sid: str) -> Workspace:
        doc = self.get(sid)
        if not doc:
            raise CodeError(404, "Sessão não encontrada.")
        ws = doc.get("workspace") or {}
        if not ws.get("path") or not Path(ws["path"]).is_dir():
            raise CodeError(409, "O projeto desta sessão não está disponível.")
        return Workspace(Path(ws["path"]), self.session_dir(sid), copy.deepcopy(doc.get("journal", [])), extra_read=[self.session_dir(sid) / "inputs"])

    def browse(self, sid: str, path: str = ".") -> Dict[str, Any]:
        w = self._ws(sid)
        try:
            p = w.check(path or ".", "read")
        except guard.Blocked as exc:
            raise CodeError(403, str(exc)) from None
        if not p.is_dir():
            raise CodeError(400, "Não é uma pasta.")
        items = []
        try:
            for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if e.name == ".git":
                    continue
                try:
                    size = e.stat().st_size if e.is_file() else 0
                except OSError:
                    size = 0
                items.append({"name": e.name, "dir": e.is_dir(), "size": size, "path": w.rel(e)})
        except OSError:
            pass
        return {"path": w.rel(p), "items": items[:500], "truncated": len(items) > 500}

    def read_file(self, sid: str, path: str) -> Dict[str, Any]:
        w = self._ws(sid)
        try:
            p = w.check(path, "read")
        except guard.Blocked as exc:
            raise CodeError(403, str(exc)) from None
        if not p.is_file():
            raise CodeError(404, "Arquivo não encontrado.")
        data = p.read_bytes()[:400_000]
        from .workspace import is_binary

        if is_binary(data):
            return {"path": w.rel(p), "binary": True, "size": p.stat().st_size, "text": ""}
        return {"path": w.rel(p), "binary": False, "size": p.stat().st_size, "text": data.decode("utf-8", "replace"), "language": langs.language_of(p.name), "truncated": p.stat().st_size > 400_000}

    def diff(self, sid: str, path: str = "") -> Dict[str, Any]:
        w = self._ws(sid)
        return {"diff": w.diff(path, 200_000), "files": w.changed_files()}

    def run_doc(self, sid: str, rid: str) -> Optional[Dict[str, Any]]:
        if not _ID.match(rid or "") or not _ID.match(sid or ""):
            return None
        doc = self.get(sid)
        if doc and (doc.get("run") or {}).get("id") == rid:
            return doc["run"]
        d = read_json(self.session_dir(sid) / "runs" / f"{rid}.json")
        return d if isinstance(d, dict) else None

    def shutdown(self) -> None:
        for r in list(self.runners.values()):
            r.cancel()
