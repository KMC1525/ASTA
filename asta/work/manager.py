"""O gerenciador do Work: redes (organizações) abertas nesta máquina, sessões de login, regras de permissão e as operações de cada área
(pessoas, cargos, quadro, setores, arquivos, pedidos, atividades, notificações, máquinas, redes e backups).

As rotas HTTP (`routes_work.py`) são finas: autenticam, chamam um método daqui e devolvem JSON. Tudo que muda dados passa por `OrgStore.put` (um documento por coisa) e, por isso,
sincroniza sozinho com as outras máquinas (sync.py).
"""
from __future__ import annotations

import collections
import json
import mimetypes
import os
import re
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, BinaryIO, Callable, Deque, Dict, List, Optional, Set, Tuple

from .. import team as teamlib
from ..util import new_id, num, read_json, safe_filename, text, write_json
from . import board, crypto, perms as P, schema as S, tailscale
from .store import OrgStore, is_sha
from .sync import (DEFAULT_PORT, INVITE_TTL, FolderPool, HttpPeer, PeerError, PeerServer, PeerService, SyncService, _download, file_shas, local_machine_info, make_invite,
                   new_machine_id, parse_invite, should_hold)

ONLINE_SECS = 150
PRESENCE_EVERY = 45
INLINE_OK = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".mp3": "audio/mpeg", ".wav": "audio/wav",
             ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".mp4": "video/mp4", ".webm": "video/webm", ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8"}
SESSION_COOKIE = "asta_work"


class WorkError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def normalize_config(raw: Any) -> Dict[str, Any]:
    """`settings.work` válido (valor errado volta ao padrão)."""
    d = raw if isinstance(raw, dict) else {}
    peer = d.get("peer") if isinstance(d.get("peer"), dict) else {}
    listen = str(peer.get("listen") or "off")
    if listen not in ("off", "auto", "lan") and not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", listen):
        listen = "off"
    return {
        "peer": {"listen": listen, "port": int(num(peer.get("port"), DEFAULT_PORT, 1024, 65535))},
        "auto_sync": d.get("auto_sync") is not False,
        "interval": int(num(d.get("interval"), 15, 5, 600)),
        "max_file_mb": int(num(d.get("max_file_mb"), 4096, 1, 102400)),
        "session_hours": int(num(d.get("session_hours"), 12, 1, 168)),
        "backup_keep": int(num(d.get("backup_keep"), 14, 1, 90)),
        "agents": teamlib.normalize_agents(d.get("agents")),
        "effort": teamlib.normalize_effort(d.get("effort")),
    }


class Ctx:
    """Quem está pedindo: a rede, a pessoa e as permissões dela. Toda operação começa por `ctx.need(...)`."""

    def __init__(self, mgr: "WorkManager", st: OrgStore, user: Dict[str, Any], perms: Set[str]):
        self.mgr, self.st, self.user, self.perms = mgr, st, user, perms

    @property
    def uid(self) -> str:
        return self.user["id"]

    def has(self, perm: str) -> bool:
        return P.can(self.perms, perm)

    def need(self, perm: str) -> None:
        if not self.has(perm):
            raise WorkError(403, "Sem permissão para isto: " + S_PERM_NAME(perm))

    @property
    def level(self) -> int:
        return P.level_of(self.user, self.st.map("roles"))

    @property
    def admin(self) -> bool:
        return "*" in self.perms


def S_PERM_NAME(perm: str) -> str:
    return (P.CATALOG.get(perm) or ("", perm))[1]


def _public_user(u: Dict[str, Any], full: bool = False) -> Dict[str, Any]:
    keys = ["id", "username", "display_name", "role_id", "title", "function_ids", "bio", "avatar_color", "disabled", "email"]
    out = {k: u.get(k) for k in keys}
    out["auth"] = {"mode": (u.get("auth") or {}).get("mode", "none"), "set": bool((u.get("auth") or {}).get("set"))}
    out["created"] = (u.get("created") or 0)
    if full:
        out.update(grant=u.get("grant") or [], deny=u.get("deny") or [], backup_machines=u.get("backup_machines") or [], home_machines=u.get("home_machines") or [],
                   auth=dict(u.get("auth") or {"mode": "none"}))
    return out


class WorkManager:
    def __init__(self, store: Any, resolve: Optional[Callable[[dict], Any]] = None):
        self.store = store
        self._resolve = resolve
        self.root = Path(store.home) / "work"
        self.root.mkdir(parents=True, exist_ok=True)
        ident = read_json(self.root / "machine.json", {}) or {}
        if not isinstance(ident, dict) or not S.valid_id(ident.get("id")):
            info = local_machine_info()
            ident = {"id": new_machine_id(), "name": info["name"], "os": info["os"]}
            write_json(self.root / "machine.json", ident)
        self.ident = ident
        self.machine_id = ident["id"]
        self.lock = threading.RLock()
        self.orgs: Dict[str, OrgStore] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.fails: Dict[Tuple[str, str], Tuple[int, float]] = {}
        self.contact: Dict[str, float] = {}
        self.cv = threading.Condition()
        self.seq = 0
        self.events: Deque[Dict[str, Any]] = collections.deque(maxlen=1000)
        self.service = PeerService(self)
        self.peer_server: Optional[PeerServer] = None
        self.sync = SyncService(self)
        self._presence_at: Dict[str, float] = {}
        for d in sorted(self.root.iterdir()):
            if d.is_dir() and S.valid_id(d.name) and (d / "docs").is_dir():
                self._open(d.name)

    # ------------------------------------------------------------------ redes abertas
    def config(self) -> Dict[str, Any]:
        return normalize_config(self.store.get_settings().get("work"))

    def resolve_provider(self, settings: dict) -> Any:
        if self._resolve:
            return self._resolve(settings)
        from ..providers import resolve_provider

        return resolve_provider(settings, "generation", self.store.models_dir)

    def org_ids(self) -> List[str]:
        return sorted(self.orgs)

    def org_store(self, oid: str) -> Optional[OrgStore]:
        return self.orgs.get(oid) if S.valid_id(oid) else None

    def _open(self, oid: str) -> OrgStore:
        st = OrgStore(self.root / oid, self.machine_id)
        st.listeners.append(lambda c, d, src, st=st: self._on_change(st, c, d, src))
        self.orgs[oid] = st
        return st

    def auto_sync_enabled(self) -> bool:
        return self.config()["auto_sync"] and bool(self.orgs)

    def start(self) -> None:
        """Liga a sincronização em segundo plano e (se o usuário escolheu) o servidor de sincronização."""
        self.sync.interval = float(self.config()["interval"])
        self.apply_network()
        if self.orgs:
            self.sync.start()

    def stop(self) -> None:
        self.sync.stop()
        if self.peer_server:
            self.peer_server.stop()
            self.peer_server = None

    def listen_address(self, cfg: Optional[Dict[str, Any]] = None) -> Tuple[str, List[str]]:
        """(endereço onde escutar, endereços «ip:porta» para anunciar às outras máquinas)."""
        cfg = cfg or self.config()
        mode, port = cfg["peer"]["listen"], cfg["peer"]["port"]
        if mode == "off":
            return "", []
        if mode == "auto":
            ip = tailscale.my_ip()
            return (ip, [f"{ip}:{port}"]) if ip else ("", [])
        if mode == "lan":
            from ..mobile import lan_ips

            return "0.0.0.0", [f"{ip}:{port}" for ip in lan_ips()]
        return mode, [f"{mode}:{port}"]

    def apply_network(self) -> Dict[str, Any]:
        cfg = self.config()
        host, addrs = self.listen_address(cfg)
        cur = self.peer_server
        if cur and (not host or (cur.host, cur.port) != (host, cfg["peer"]["port"])):
            cur.stop()
            self.peer_server = cur = None
        err = ""
        if host and cur is None and self.orgs:
            try:
                self.peer_server = PeerServer(self.service, host, cfg["peer"]["port"])
            except OSError as exc:
                err = f"Não foi possível escutar em {host}:{cfg['peer']['port']}: {exc}"
        self.sync.interval = float(cfg["interval"])
        for st in self.orgs.values():
            self.refresh_self(st)
        return {"listening": bool(self.peer_server), "addrs": addrs if self.peer_server else [], "error": err}

    def my_addrs(self) -> List[str]:
        return self.listen_address()[1] if self.peer_server else []

    def refresh_self(self, st: OrgStore) -> None:
        """Mantém o documento desta máquina na rede (nome, sistema, endereços) — só grava se algo mudou."""
        cur = st.get("machines", self.machine_id) or {}
        want = S.norm_machine({"name": self.ident["name"], "os": self.ident["os"], "addrs": self.my_addrs(), "tailnet": tailscale.status().get("tailnet", "")}, cur)
        if cur and all(cur.get(k) == want[k] for k in ("name", "os", "addrs", "tailnet")):
            return
        st.put("machines", self.machine_id, {**want, "added": cur.get("added") or time.time()}, self.machine_id)

    def touch(self, mid: str) -> None:
        self.contact[mid] = time.time()

    # ------------------------------------------------------------------ eventos em tempo real (SSE)
    def emit(self, org: str, kind: str, data: Optional[Dict[str, Any]] = None, users: Optional[List[str]] = None) -> None:
        with self.cv:
            self.seq += 1
            self.events.append({"seq": self.seq, "org": org, "kind": kind, "users": users, "ts": time.time(), **(data or {})})
            self.cv.notify_all()

    def wait_events(self, since: int, org: str, uid: str, timeout: float = 15.0) -> Tuple[int, List[Dict[str, Any]]]:
        with self.cv:
            if self.seq <= since:
                self.cv.wait(timeout)
            seq = self.seq
            items = [e for e in self.events if e["seq"] > since and e["org"] == org and (e["users"] is None or uid in e["users"])]
        return seq, items

    def _on_change(self, st: OrgStore, coll: str, doc: Dict[str, Any], source: str) -> None:
        if coll == "presence":
            return
        users: Optional[List[str]] = None
        if coll == "notifications" and doc.get("to"):
            users = [doc["to"]]
        elif coll == "requests" and doc.get("from"):
            users = list({doc["from"], *(doc.get("to") or [])})
        self.emit(st.id, coll, {"id": doc["id"], "source": source, "deleted": bool(doc["_m"].get("deleted"))}, users)
        if source == "local":
            self.sync.nudge()

    # ------------------------------------------------------------------ criar e entrar em redes
    def status(self, token: str = "") -> Dict[str, Any]:
        orgs = []
        for oid, st in sorted(self.orgs.items()):
            meta = st.get("meta", "org") or {}
            orgs.append({"id": oid, "name": meta.get("name") or oid, "users": len([u for u in st.all("users") if not u.get("disabled")]), "machines": len(st.all("machines"))})
        sess = self.sessions.get(token) if token else None
        return {"machine": {"id": self.machine_id, "name": self.ident["name"], "os": self.ident["os"]}, "orgs": orgs, "tailscale": tailscale.status(),
                "session": {"org": sess["org"], "user": sess["uid"]} if sess and sess["exp"] > time.time() else None, "listening": bool(self.peer_server)}

    def create_org(self, name: str, admin: Dict[str, Any], machine_name: str = "") -> Tuple[OrgStore, Dict[str, Any]]:
        name = text(name, "", 80)
        if not name:
            raise WorkError(400, "Dê um nome à organização.")
        username = S.norm_username(admin.get("username"))
        if not username:
            raise WorkError(400, "Nome de usuário inválido: use 2 a 32 letras minúsculas, números, ponto, hífen ou sublinhado.")
        if machine_name.strip():
            self.rename_machine(machine_name)
        oid = new_id("org_")
        with self.lock:
            st = self._open(oid)
        st.set_secret(crypto.new_secret())
        st.put("meta", "org", {"name": name, "created": time.time(), "schema": S.SCHEMA}, self.machine_id)
        for r in P.BUILTIN_ROLES:
            st.put("roles", r["id"], {k: v for k, v in r.items() if k != "id"}, self.machine_id)
        uid = new_id("u_")
        st.put("users", uid, {**S.norm_user({"username": username, "display_name": admin.get("display_name") or username, "role_id": "admin", "title": admin.get("title") or "Administrador"}),
                              "created": time.time()}, self.machine_id)
        self.refresh_self(st)
        user = st.get("users", uid)
        assert user
        if admin.get("password"):
            self._set_password(st, user, str(admin["password"]), str(admin.get("auth_mode") or "local"), str(admin.get("holder") or ""))
        self.sync.start()
        self.apply_network()
        return st, st.get("users", uid) or user

    def rename_machine(self, name: str) -> None:
        self.ident["name"] = text(name, self.ident["name"], 60)
        write_json(self.root / "machine.json", self.ident)
        for st in self.orgs.values():
            self.refresh_self(st)

    def create_invite(self, ctx: Ctx, extra_addrs: Optional[List[str]] = None) -> Dict[str, Any]:
        ctx.need("network.manage")
        addrs = [a for a in (extra_addrs or []) if isinstance(a, str) and a.strip()] or self.my_addrs()
        if not addrs:
            raise WorkError(409, "Esta máquina ainda não escuta na rede. Em Work → Rede, escolha «Tailscale» ou «Rede local» e ligue a sincronização antes de convidar.")
        key = crypto.new_secret()
        exp = ctx.st.add_invite(key, INVITE_TTL, ctx.uid)
        meta = ctx.st.get("meta", "org") or {}
        return {"code": make_invite(ctx.st.id, meta.get("name", ""), key, addrs), "expires": exp, "addrs": addrs}

    def accept_join(self, st: OrgStore, iid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Lado de quem convidou: o convite é de uso único. Registra a máquina nova e entrega o segredo da rede (cifrado com a chave do convite)."""
        m = data.get("machine") if isinstance(data.get("machine"), dict) else {}
        mid = m.get("id")
        if not S.valid_id(mid):
            raise PeerError("máquina inválida")
        st.burn_invite(iid)
        st.put("machines", mid, {**S.norm_machine(m), "added": time.time()}, self.machine_id)
        self.touch(mid)
        meta = st.get("meta", "org") or {}
        return {"secret": st.secret(), "name": meta.get("name", ""), "host": self.machine_id, "host_name": self.ident["name"]}

    def join(self, code: str, machine_name: str = "") -> OrgStore:
        try:
            inv = parse_invite(code)
        except ValueError as exc:
            raise WorkError(400, str(exc)) from None
        if inv["org"] in self.orgs:
            raise WorkError(409, "Esta máquina já faz parte dessa rede.")
        if machine_name.strip():
            self.rename_machine(machine_name)
        last = ""
        for addr in inv["addrs"]:
            peer = HttpPeer(inv["org"], inv["key"], self.machine_id, addr, timeout=15, invite_id=OrgStore.invite_id(inv["key"]))
            try:
                reply = peer.call("join", {"machine": {"id": self.machine_id, "name": self.ident["name"], "os": self.ident["os"], "addrs": self.my_addrs()}})
            except PeerError as exc:
                last = str(exc)
                continue
            secret = str(reply.get("secret") or "")
            if len(secret) != 64:
                last = "resposta sem a chave da rede"
                continue
            with self.lock:
                st = self._open(inv["org"])
            st.set_secret(secret)
            st.save_local({"links": [{"kind": "peer", "addr": addr}], "joined": time.time()})
            try:
                self.sync.run_org(inv["org"])
            except PeerError as exc:
                last = str(exc)
            self.refresh_self(st)
            self.sync.start()
            self.apply_network()
            return st
        raise WorkError(502, "Não foi possível entrar na rede: " + (last or "nenhum endereço respondeu") + ". Confira se a outra máquina está ligada e com a sincronização ativa.")

    # ------------------------------------------------------------------ login e sessões
    def login_users(self, oid: str) -> List[Dict[str, Any]]:
        st = self._org(oid)
        roles = st.map("roles")
        return [{"username": u["username"], "display_name": u.get("display_name"), "role": (roles.get(u.get("role_id")) or {}).get("name", ""), "color": u.get("avatar_color"),
                 "auth": (u.get("auth") or {}).get("mode", "none")} for u in sorted(st.all("users"), key=lambda u: u.get("username", "")) if not u.get("disabled")]

    def _org(self, oid: str) -> OrgStore:
        st = self.org_store(oid)
        if st is None:
            raise WorkError(404, "Rede não encontrada nesta máquina.")
        return st

    def find_user(self, st: OrgStore, username: str) -> Optional[Dict[str, Any]]:
        name = S.norm_username(username)
        found = [u for u in st.all("users") if u.get("username") == name]
        return sorted(found, key=lambda u: (u.get("created") or 0, u["id"]))[0] if found else None

    def login(self, oid: str, username: str, password: str = "") -> Tuple[str, Ctx]:
        st = self._org(oid)
        key = (oid, S.norm_username(username))
        n, until = self.fails.get(key, (0, 0.0))
        if until > time.time():
            raise WorkError(429, f"Muitas tentativas. Espere {int(until - time.time()) + 1} s.")
        user = self.find_user(st, username)
        ok = bool(user) and not user.get("disabled") and self._check_password(st, user, password)
        if not ok:
            n += 1
            self.fails[key] = (n, time.time() + min(900, 2 ** n) if n >= 5 else 0.0)
            raise WorkError(401, "Usuário ou senha incorretos.")
        self.fails.pop(key, None)
        assert user
        token = crypto.token(32)
        with self.lock:
            self.sessions = {t: s for t, s in self.sessions.items() if s["exp"] > time.time()}
            self.sessions[token] = {"org": oid, "uid": user["id"], "exp": time.time() + self.config()["session_hours"] * 3600}
        ctx = self.ctx(token)
        self._home(ctx)
        self.ping(ctx, force=True)
        return token, ctx

    def logout(self, token: str) -> None:
        self.sessions.pop(token, None)

    def ctx(self, token: str) -> Ctx:
        s = self.sessions.get(token or "")
        if not s or s["exp"] < time.time():
            raise WorkError(401, "Entre no Work para continuar.")
        st = self.org_store(s["org"])
        user = st.get("users", s["uid"]) if st else None
        if not st or not user or user.get("disabled"):
            self.sessions.pop(token, None)
            raise WorkError(401, "Esta conta não está mais ativa.")
        return Ctx(self, st, user, P.effective(user, st.map("roles"), st.map("functions")))

    def _home(self, ctx: Ctx) -> None:
        """Registra que a pessoa usa esta máquina (a política de réplica dos arquivos usa isso)."""
        if self.machine_id not in (ctx.user.get("home_machines") or []):
            ctx.st.put("users", ctx.uid, {**ctx.user, "home_machines": (ctx.user.get("home_machines") or []) + [self.machine_id]}, ctx.uid)

    def ping(self, ctx: Ctx, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._presence_at.get(ctx.uid, 0) < PRESENCE_EVERY:
            return
        self._presence_at[ctx.uid] = now
        ctx.st.put("presence", ctx.uid, {"seen": now, "machine": self.machine_id}, ctx.uid)

    # ------------------------------------------------------------------ senhas (4 lugares possíveis)
    def _check_password(self, st: OrgStore, user: Dict[str, Any], password: str) -> bool:
        auth = user.get("auth") or {}
        mode = auth.get("mode", "none")
        if mode == "none" or not auth.get("set"):
            return True
        if mode == "synced":
            return crypto.verify_password(password, user.get("pw"))
        if mode == "local" or (mode == "machine" and auth.get("holder") == self.machine_id):
            rec = st.vault_get(user["id"])
            if not rec:
                raise WorkError(409, "A senha desta pessoa só vale na máquina em que foi criada. Entre por lá ou peça ao administrador para trocar o local da senha.")
            return crypto.verify_password(password, rec)
        holder = st.get("machines", auth.get("holder") or "")
        if not holder:
            raise WorkError(409, "A máquina que guarda esta senha não está na rede.")
        for addr in holder.get("addrs") or []:
            try:
                return bool(HttpPeer(st.id, st.secret(), self.machine_id, addr, timeout=8).call("verify_password", {"user": user["id"], "password": password}).get("ok"))
            except PeerError:
                continue
        raise WorkError(503, f"A máquina «{holder.get('name')}», que guarda a senha, está fora do ar. Tente quando ela voltar.")

    def verify_local_password(self, st: OrgStore, uid: str, password: str) -> bool:
        rec = st.vault_get(uid)
        return bool(rec) and crypto.verify_password(password, rec)

    def accept_vault(self, st: OrgStore, uid: str, rec: Any, caller: str) -> bool:
        if not S.valid_id(uid) or not isinstance(rec, dict) or rec.get("alg") != "pbkdf2-sha256":
            return False
        st.vault_set(uid, {k: rec[k] for k in ("alg", "iter", "salt", "hash") if k in rec})
        return True

    def _set_password(self, st: OrgStore, user: Dict[str, Any], password: str, mode: str, holder: str = "") -> Dict[str, Any]:
        mode = mode if mode in S.AUTH_MODES else "local"
        if mode == "none" or not password:
            st.vault_del(user["id"])
            new = {**user, "auth": {"mode": "none", "holder": "", "set": False}}
            new.pop("pw", None)
            return st.put("users", user["id"], new, user["id"])
        bad = crypto.check_password_strength(password)
        if bad:
            raise WorkError(400, bad)
        rec = crypto.hash_password(password)
        new = dict(user)
        new.pop("pw", None)
        st.vault_del(user["id"])
        if mode == "synced":
            new["pw"] = rec
        elif mode == "local" or (mode == "machine" and (holder or self.machine_id) == self.machine_id):
            st.vault_set(user["id"], rec)
            holder = self.machine_id if mode == "machine" else ""
        else:
            machine = st.get("machines", holder)
            if not machine or machine.get("revoked"):
                raise WorkError(400, "Escolha uma máquina da rede para guardar a senha.")
            ok = False
            for addr in machine.get("addrs") or []:
                try:
                    ok = bool(HttpPeer(st.id, st.secret(), self.machine_id, addr, timeout=8).call("vault_put", {"user": user["id"], "rec": rec}).get("ok"))
                    break
                except PeerError:
                    continue
            if not ok:
                raise WorkError(503, f"Não consegui falar com a máquina «{machine.get('name')}» para guardar a senha lá.")
        new["auth"] = {"mode": mode, "holder": holder if mode == "machine" else "", "set": True}
        return st.put("users", user["id"], new, user["id"])

    def set_password(self, ctx: Ctx, uid: str, password: str, mode: str, holder: str = "", current: str = "") -> Dict[str, Any]:
        user = ctx.st.get("users", uid)
        if not user:
            raise WorkError(404, "Pessoa não encontrada.")
        if uid != ctx.uid:
            ctx.need("users.manage")
        elif (user.get("auth") or {}).get("set") and not ctx.has("users.manage") and not self._check_password(ctx.st, user, current):
            raise WorkError(401, "A senha atual não confere.")
        out = self._set_password(ctx.st, user, password, mode, holder)
        self.record(ctx, "Alterou a senha de " + (user.get("display_name") or user["username"]) if uid != ctx.uid else "Alterou a própria senha")
        return _public_user(out, True)

    # ------------------------------------------------------------------ visão geral (a tela inicial do Work)
    def me(self, ctx: Ctx) -> Dict[str, Any]:
        roles = ctx.st.map("roles")
        meta = ctx.st.get("meta", "org") or {}
        return {"org": {"id": ctx.st.id, "name": meta.get("name", "")}, "user": _public_user(ctx.user, True), "perms": sorted(ctx.perms), "level": ctx.level,
                "role": roles.get(ctx.user.get("role_id") or "", {}).get("name", ""), "machine": {"id": self.machine_id, "name": self.ident["name"]}}

    def catalog(self) -> Dict[str, Any]:
        return {"perms": [{"id": k, "group": g, "label": d} for k, (g, d) in P.CATALOG.items()], "statuses": list(S.REQ_STATUS), "priorities": list(S.PRIORITIES),
                "auth_modes": list(S.AUTH_MODES)}

    def directory(self, ctx: Ctx) -> Dict[str, Any]:
        """Pessoas, cargos, funções e quem está online — o que quase toda tela precisa."""
        now = time.time()
        pres = {p["id"]: p for p in ctx.st.all("presence")}
        full = ctx.has("users.manage")
        users = []
        busy: Dict[str, int] = {}
        for a in ctx.st.all("activities"):
            if a.get("state") in ("started", "continuing"):
                busy[a.get("user")] = busy.get(a.get("user"), 0) + 1
        for u in sorted(ctx.st.all("users"), key=lambda u: (u.get("display_name") or "").lower()):
            pu = _public_user(u, full or u["id"] == ctx.uid)
            pu["online"] = now - float((pres.get(u["id"]) or {}).get("seen") or 0) < ONLINE_SECS
            pu["last_seen"] = float((pres.get(u["id"]) or {}).get("seen") or 0)
            pu["busy"] = busy.get(u["id"], 0)
            users.append(pu)
        return {"users": users, "roles": sorted(ctx.st.all("roles"), key=lambda r: -int(r.get("level") or 0)), "functions": sorted(ctx.st.all("functions"), key=lambda f: f.get("name", "")),
                "folders": self.folders(ctx)}

    # ------------------------------------------------------------------ pessoas, cargos e funções
    def _admins(self, st: OrgStore, skip: str = "") -> List[Dict[str, Any]]:
        roles = st.map("roles")
        return [u for u in st.all("users") if u["id"] != skip and not u.get("disabled") and "*" in (roles.get(u.get("role_id") or "") or {}).get("perms", [])]

    def create_user(self, ctx: Ctx, spec: Dict[str, Any]) -> Dict[str, Any]:
        ctx.need("users.manage")
        username = S.norm_username(spec.get("username"))
        if not username:
            raise WorkError(400, "Nome de usuário inválido: use 2 a 32 letras minúsculas, números, ponto, hífen ou sublinhado.")
        if self.find_user(ctx.st, username):
            raise WorkError(409, "Já existe uma pessoa com esse nome de usuário.")
        data = S.norm_user({k: v for k, v in spec.items() if k != "auth"})
        self._check_assignable(ctx, data)
        uid = new_id("u_")
        ctx.st.put("users", uid, {**data, "username": username, "created": time.time()}, ctx.uid)
        user = ctx.st.get("users", uid)
        assert user
        if spec.get("password"):
            user = self._set_password(ctx.st, user, str(spec["password"]), str(spec.get("auth_mode") or "synced"), str(spec.get("holder") or ""))
        self.record(ctx, "Criou o perfil de " + data["display_name"], ref={"type": "user", "id": uid})
        self.notify(ctx.st, [uid], "welcome", "Bem-vindo(a) ao Work", f"{ctx.user.get('display_name')} criou o seu perfil.", {"type": "user", "id": uid}, ctx.uid)
        return _public_user(user, True)

    def _check_assignable(self, ctx: Ctx, data: Dict[str, Any]) -> None:
        roles = ctx.st.map("roles")
        role = roles.get(data["role_id"])
        if not role:
            raise WorkError(400, "Cargo inexistente.")
        if not ctx.admin and int(role.get("level") or 0) >= ctx.level:
            raise WorkError(403, "Você só pode atribuir cargos de nível menor que o seu.")
        fns = ctx.st.map("functions")
        data["function_ids"] = [f for f in data["function_ids"] if f in fns]
        machines = ctx.st.map("machines")
        data["backup_machines"] = [m for m in data["backup_machines"] if m in machines]

    SELF_FIELDS = ("display_name", "title", "bio", "avatar_color", "email")

    def update_user(self, ctx: Ctx, uid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        user = ctx.st.get("users", uid)
        if not user:
            raise WorkError(404, "Pessoa não encontrada.")
        manage = ctx.has("users.manage")
        if uid != ctx.uid and not manage:
            raise WorkError(403, "Só você ou quem gerencia pessoas pode editar este perfil.")
        allowed = set(patch) if manage else set(self.SELF_FIELDS)
        if uid == ctx.uid or ctx.has("backup.manage"):
            allowed |= {"backup_machines"}
        data = S.norm_user({k: v for k, v in patch.items() if k in allowed and k != "auth"}, user)
        data["username"] = user["username"]
        if manage:
            self._check_assignable(ctx, data)
            if (data["disabled"] or data["role_id"] != user.get("role_id")) and not self._admins(ctx.st, uid) and "*" in (ctx.st.get("roles", user["role_id"]) or {}).get("perms", []):
                raise WorkError(409, "A organização precisa de pelo menos um administrador ativo.")
        else:
            data["role_id"], data["function_ids"], data["grant"], data["deny"], data["disabled"] = (user.get(k) for k in ("role_id", "function_ids", "grant", "deny", "disabled"))
        data["backup_machines"] = [m for m in data["backup_machines"] if ctx.st.get("machines", m)]
        keep = {k: user.get(k) for k in ("created", "pw", "auth", "home_machines") if k in user}
        out = ctx.st.put("users", uid, {**data, **keep}, ctx.uid)
        if manage and uid != ctx.uid:
            self.record(ctx, "Editou o perfil de " + (out.get("display_name") or out["username"]), ref={"type": "user", "id": uid})
        return _public_user(out, True)

    def delete_user(self, ctx: Ctx, uid: str) -> None:
        ctx.need("users.manage")
        user = ctx.st.get("users", uid)
        if not user:
            raise WorkError(404, "Pessoa não encontrada.")
        if uid == ctx.uid:
            raise WorkError(409, "Você não pode remover a si mesmo.")
        if "*" in (ctx.st.get("roles", user.get("role_id") or "") or {}).get("perms", []) and not self._admins(ctx.st, uid):
            raise WorkError(409, "A organização precisa de pelo menos um administrador ativo.")
        ctx.st.vault_del(uid)
        ctx.st.remove("users", uid, ctx.uid)
        for n in ctx.st.all("nodes"):
            if n.get("kind") == "person" and n.get("ref") == uid:
                self._drop_node(ctx.st, n["id"], ctx.uid)
        self.record(ctx, "Removeu " + (user.get("display_name") or user["username"]))

    def save_role(self, ctx: Ctx, rid: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        ctx.need("roles.manage")
        old = ctx.st.get("roles", rid) if rid else None
        if rid and not old:
            raise WorkError(404, "Cargo não encontrado.")
        data = S.norm_role(spec, old)
        if not ctx.admin and (int(data["level"]) >= ctx.level or "*" in data["perms"] or not set(data["perms"]) <= ctx.perms):
            raise WorkError(403, "Você só pode criar cargos com nível e permissões que você mesmo tem.")
        rid = rid or "r_" + new_id("")[:8]
        return ctx.st.put("roles", rid, data, ctx.uid)

    def delete_role(self, ctx: Ctx, rid: str) -> None:
        ctx.need("roles.manage")
        role = ctx.st.get("roles", rid)
        if not role:
            raise WorkError(404, "Cargo não encontrado.")
        if rid in ("admin", "worker"):
            raise WorkError(409, "Os cargos Administrador e Trabalhador são fixos.")
        if any(u.get("role_id") == rid for u in ctx.st.all("users")):
            raise WorkError(409, "Há pessoas com este cargo. Mude o cargo delas antes de apagar.")
        ctx.st.remove("roles", rid, ctx.uid)

    def save_function(self, ctx: Ctx, fid: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        ctx.need("roles.manage")
        old = ctx.st.get("functions", fid) if fid else None
        if fid and not old:
            raise WorkError(404, "Função não encontrada.")
        data = S.norm_function(spec, old)
        if not ctx.admin and not (set(data["grant"]) <= ctx.perms):
            raise WorkError(403, "Você só pode conceder permissões que você mesmo tem.")
        return ctx.st.put("functions", fid or "fn_" + new_id("")[:8], data, ctx.uid)

    def delete_function(self, ctx: Ctx, fid: str) -> None:
        ctx.need("roles.manage")
        if not ctx.st.remove("functions", fid, ctx.uid):
            raise WorkError(404, "Função não encontrada.")
        for u in ctx.st.all("users"):
            if fid in (u.get("function_ids") or []):
                ctx.st.put("users", u["id"], {**u, "function_ids": [f for f in u["function_ids"] if f != fid]}, ctx.uid)

    # ------------------------------------------------------------------ setores/pastas e o quadro
    def folders(self, ctx: Ctx) -> List[Dict[str, Any]]:
        return [f for f in sorted(ctx.st.all("folders"), key=lambda f: f.get("name", "").lower()) if P.folder_visible(f, ctx.user, ctx.perms) or ctx.has("folders.manage")]

    def save_folder(self, ctx: Ctx, fid: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        ctx.need("folders.manage")
        old = ctx.st.get("folders", fid) if fid else None
        if fid and not old:
            raise WorkError(404, "Setor não encontrado.")
        data = S.norm_folder(spec, old)
        if data["parent"] and (data["parent"] == fid or not ctx.st.get("folders", data["parent"])):
            data["parent"] = ""
        fid = fid or "f_" + new_id("")[:8]
        out = ctx.st.put("folders", fid, data, ctx.uid)
        if not old:
            self.record(ctx, "Criou o setor «" + data["name"] + "»", ref={"type": "folder", "id": fid})
        return out

    def delete_folder(self, ctx: Ctx, fid: str) -> None:
        ctx.need("folders.manage")
        if not ctx.st.get("folders", fid):
            raise WorkError(404, "Setor não encontrado.")
        if any(f.get("folder_id") == fid for f in ctx.st.all("files")):
            raise WorkError(409, "O setor ainda tem arquivos. Mova ou apague os arquivos antes.")
        for f in ctx.st.all("folders"):
            if f.get("parent") == fid:
                ctx.st.put("folders", f["id"], {**f, "parent": ""}, ctx.uid)
        for n in ctx.st.all("nodes"):
            if n.get("kind") == "sector" and n.get("ref") == fid:
                self._drop_node(ctx.st, n["id"], ctx.uid)
        ctx.st.remove("folders", fid, ctx.uid)

    def board(self, ctx: Ctx) -> Dict[str, Any]:
        ctx.need("flow.view")
        return {"nodes": ctx.st.all("nodes"), "edges": ctx.st.all("edges"), "folders": self.folders(ctx), "can_edit": ctx.has("flow.edit")}

    def save_node(self, ctx: Ctx, nid: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        ctx.need("flow.edit")
        old = ctx.st.get("nodes", nid) if nid else None
        data = S.norm_node(spec, old)
        if data["kind"] == "person" and not ctx.st.get("users", data["ref"]):
            raise WorkError(400, "Escolha uma pessoa existente para este cartão.")
        if data["kind"] == "role" and not ctx.st.get("roles", data["ref"]):
            raise WorkError(400, "Escolha um cargo existente para este cartão.")
        if data["kind"] == "sector" and not ctx.st.get("folders", data["ref"]):
            raise WorkError(400, "Escolha um setor existente para este cartão.")
        if not data["label"]:
            ref = {"person": ctx.st.get("users", data["ref"]), "role": ctx.st.get("roles", data["ref"]), "sector": ctx.st.get("folders", data["ref"])}.get(data["kind"]) or {}
            data["label"] = ref.get("display_name") or ref.get("name") or "Cartão"
        return ctx.st.put("nodes", nid or "n_" + new_id("")[:8], data, ctx.uid)

    def _drop_node(self, st: OrgStore, nid: str, by: str) -> None:
        for e in st.all("edges"):
            if nid in (e.get("from"), e.get("to")):
                st.remove("edges", e["id"], by)
        st.remove("nodes", nid, by)

    def delete_node(self, ctx: Ctx, nid: str) -> None:
        ctx.need("flow.edit")
        if not ctx.st.get("nodes", nid):
            raise WorkError(404, "Cartão não encontrado.")
        self._drop_node(ctx.st, nid, ctx.uid)

    def save_edge(self, ctx: Ctx, eid: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        ctx.need("flow.edit")
        old = ctx.st.get("edges", eid) if eid else None
        data = S.norm_edge(spec, old)
        if not (ctx.st.get("nodes", data["from"]) and ctx.st.get("nodes", data["to"])) or data["from"] == data["to"]:
            raise WorkError(400, "A ligação precisa de dois cartões diferentes.")
        if not eid:
            for e in ctx.st.all("edges"):
                if e["from"] == data["from"] and e["to"] == data["to"]:
                    return e
        return ctx.st.put("edges", eid or "e_" + new_id("")[:8], data, ctx.uid)

    def delete_edge(self, ctx: Ctx, eid: str) -> None:
        ctx.need("flow.edit")
        if not ctx.st.remove("edges", eid, ctx.uid):
            raise WorkError(404, "Ligação não encontrada.")

    def layout_board(self, ctx: Ctx) -> Dict[str, Any]:
        """Organiza o quadro em camadas (chefia em cima). Só mexe nos cartões, nunca nas caixas dos setores."""
        ctx.need("flow.edit")
        nodes, edges = ctx.st.all("nodes"), ctx.st.all("edges")
        pos = board.auto_layout(nodes, edges)
        for n in nodes:
            x, y = pos[n["id"]]
            if (n.get("x"), n.get("y")) != (x, y):
                ctx.st.put("nodes", n["id"], {**n, "x": x, "y": y}, ctx.uid)
        return self.board(ctx)

    def autofill_board(self, ctx: Ctx) -> Dict[str, Any]:
        """Põe no quadro um cartão para cada pessoa que ainda não tem e liga cada uma a um superior do nível acima. Não mexe no que já existe."""
        ctx.need("flow.edit")
        have = {n.get("ref") for n in ctx.st.all("nodes") if n.get("kind") == "person"}
        roles = ctx.st.map("roles")
        newcomers = [u for u in ctx.st.all("users") if not u.get("disabled") and u["id"] not in have]
        tpl = board.template("org", list(roles.values()), newcomers, [])
        made: Dict[str, str] = {}
        for n in tpl["nodes"]:
            u = ctx.st.get("users", n["ref"])
            color = (roles.get(u.get("role_id") if u else "") or {}).get("color", "#3e9bff")
            made[n["id"]] = self.save_node(ctx, "", {**n, "color": color, "id": None})["id"]
        for e in tpl["edges"]:
            self.save_edge(ctx, "", {**e, "from": made[e["from"]], "to": made[e["to"]]})
        return self.layout_board(ctx)

    def apply_draft(self, ctx: Ctx, draft: Dict[str, Any], replace: bool = False) -> Dict[str, Any]:
        """Aplica um fluxograma proposto pela IA (já validado): cria cargos novos, setores, cartões e ligações. `replace` limpa o quadro antes."""
        ctx.need("flow.edit")
        if replace:
            for n in ctx.st.all("nodes"):
                self._drop_node(ctx.st, n["id"], ctx.uid)
        sector_ids: Dict[str, str] = {}
        if ctx.has("folders.manage"):
            for sec in draft.get("sectors", []):
                sector_ids[sec["key"]] = self.save_folder(ctx, "", {"name": sec["name"], "color": sec.get("color"), "description": sec.get("description", "")})["id"]
        made: Dict[str, str] = {}
        for n in draft.get("nodes", []):
            spec = {"kind": n.get("kind", "note"), "label": n.get("label", ""), "text": n.get("text", ""), "color": n.get("color")}
            if n.get("kind") == "sector":
                ref = sector_ids.get(n.get("sector", ""))
                if not ref:
                    spec["kind"] = "note"
                else:
                    spec["ref"] = ref
            elif n.get("kind") == "role":
                spec["ref"] = n.get("ref") if ctx.st.get("roles", n.get("ref")) else ""
                if not spec["ref"]:
                    spec["kind"] = "note"
            elif n.get("kind") == "person":
                spec["ref"] = n.get("ref") if ctx.st.get("users", n.get("ref")) else ""
                if not spec["ref"]:
                    spec["kind"] = "note"
            made[n["key"]] = self.save_node(ctx, "", spec)["id"]
        for e in draft.get("edges", []):
            if e.get("from") in made and e.get("to") in made:
                self.save_edge(ctx, "", {"from": made[e["from"]], "to": made[e["to"]], "label": e.get("label", ""), "kind": e.get("kind", "reports")})
        self.record(ctx, "Aplicou um fluxograma ao quadro")
        return self.layout_board(ctx)

    # ------------------------------------------------------------------ arquivos (qualquer formato)
    def _folder_for(self, ctx: Ctx, folder_id: str, write: bool = False) -> Optional[Dict[str, Any]]:
        if not folder_id:
            return None
        f = ctx.st.get("folders", folder_id)
        if not f or not P.folder_visible(f, ctx.user, ctx.perms):
            raise WorkError(404, "Setor não encontrado ou sem acesso.")
        return f

    def can_see_file(self, ctx: Ctx, f: Dict[str, Any]) -> bool:
        if f.get("owner") == ctx.uid:
            return True
        if f.get("request_id"):
            req = ctx.st.get("requests", f["request_id"])
            return bool(req) and self.can_see_request(ctx, req)
        if f.get("folder_id"):
            folder = ctx.st.get("folders", f["folder_id"])
            return bool(folder) and P.folder_visible(folder, ctx.user, ctx.perms)
        return False

    def public_file(self, ctx: Ctx, f: Dict[str, Any]) -> Dict[str, Any]:
        vs = f.get("versions") or []
        last = vs[-1] if vs else {}
        return {"id": f["id"], "name": f.get("name"), "folder_id": f.get("folder_id", ""), "owner": f.get("owner"), "size": last.get("size", 0), "mime": f.get("mime", ""), "updated": last.get("ts", 0),
                "request_id": f.get("request_id", ""), "versions": [{"n": v.get("n"), "size": v.get("size"), "ts": v.get("ts"), "by": v.get("by")} for v in vs],
                "local": all(ctx.st.has_blob(s) for s in file_shas(f)[-1:]), "can_delete": f.get("owner") == ctx.uid or ctx.has("files.delete")}

    def list_files(self, ctx: Ctx, folder_id: str = "") -> List[Dict[str, Any]]:
        ctx.need("files.view")
        self._folder_for(ctx, folder_id)
        out = [f for f in ctx.st.all("files") if (f.get("folder_id") or "") == folder_id and not f.get("request_id") and self.can_see_file(ctx, f)]
        return [self.public_file(ctx, f) for f in sorted(out, key=lambda f: f.get("name", "").lower())]

    def upload_file(self, ctx: Ctx, name: str, stream: BinaryIO, length: int, folder_id: str = "", request_id: str = "", mime: str = "") -> Dict[str, Any]:
        ctx.need("files.upload")
        self._folder_for(ctx, folder_id)
        if request_id:
            req = ctx.st.get("requests", request_id)
            if not req or not self.can_see_request(ctx, req):
                raise WorkError(404, "Pedido não encontrado.")
        limit = self.config()["max_file_mb"] * 1024 * 1024
        if length > limit:
            raise WorkError(413, f"Arquivo maior que o limite de {limit // 1024 // 1024} MB.")
        try:
            sha, size = ctx.st.add_blob(stream, length, limit=limit)
        except ValueError:
            raise WorkError(413, "Arquivo maior que o limite.") from None
        name = safe_filename(name, "arquivo")
        now = time.time()
        old = None if request_id else next((f for f in ctx.st.all("files") if f.get("name") == name and (f.get("folder_id") or "") == folder_id and not f.get("request_id")
                                           and (f.get("owner") == ctx.uid or ctx.has("files.delete"))), None)
        ver = {"n": len(old["versions"]) + 1 if old else 1, "sha": sha, "size": size, "ts": now, "by": ctx.uid}
        fid = old["id"] if old else "fl_" + new_id("")[:9]
        doc = {"name": name, "folder_id": folder_id, "owner": old["owner"] if old else ctx.uid, "mime": mime or mimetypes.guess_type(name)[0] or "application/octet-stream",
               "request_id": request_id, "versions": ((old or {}).get("versions") or [])[-49:] + [ver]}
        out = ctx.st.put("files", fid, doc, ctx.uid)
        self.record(ctx, ("Enviou uma nova versão de " if old else "Enviou o arquivo ") + name, ref={"type": "file", "id": fid})
        folder = ctx.st.get("folders", folder_id) if folder_id else None
        if folder and (folder.get("access") or {}).get("mode") == "restricted":
            acc = folder["access"]
            targets = set(acc.get("users") or []) | {u["id"] for u in ctx.st.all("users") if u.get("role_id") in (acc.get("roles") or []) or set(u.get("function_ids") or []) & set(acc.get("functions") or [])}
            self.notify(ctx.st, list(targets), "file", f"Novo arquivo em {folder['name']}", name, {"type": "file", "id": fid}, ctx.uid)
        return self.public_file(ctx, out)

    def file_doc(self, ctx: Ctx, fid: str) -> Dict[str, Any]:
        f = ctx.st.get("files", fid)
        if not f or not self.can_see_file(ctx, f):
            raise WorkError(404, "Arquivo não encontrado ou sem acesso.")
        return f

    def open_file(self, ctx: Ctx, fid: str, version: int = 0) -> Tuple[Path, str, str]:
        ctx.need("files.view")
        f = self.file_doc(ctx, fid)
        vs = f.get("versions") or []
        v = next((x for x in vs if x.get("n") == version), None) if version else (vs[-1] if vs else None)
        if not v or not is_sha(v.get("sha")):
            raise WorkError(404, "Versão não encontrada.")
        if not ctx.st.has_blob(v["sha"]) and not self.fetch_blob(ctx.st, v["sha"]):
            raise WorkError(503, "O conteúdo deste arquivo está em outra máquina que não está respondendo agora. Tente de novo quando ela estiver ligada.")
        ext = Path(f["name"]).suffix.lower()
        return ctx.st.blob_path(v["sha"]), f["name"], INLINE_OK.get(ext, "")

    def fetch_blob(self, st: OrgStore, sha: str) -> bool:
        """Busca um arquivo que não está aqui: tenta cada máquina da rede (as que responderam há pouco primeiro) e as pastas de nuvem."""
        machines = sorted((m for m in st.all("machines") if m["id"] != self.machine_id and not m.get("revoked")), key=lambda m: -self.contact.get(m["id"], 0))
        for m in machines:
            for addr in m.get("addrs") or []:
                try:
                    peer = HttpPeer(st.id, st.secret(), self.machine_id, addr, timeout=10)
                    if sha in peer.have([sha]) and _download(st, peer, sha):
                        return True
                    break
                except PeerError:
                    continue
        for lk in st.local().get("links") or []:
            if isinstance(lk, dict) and lk.get("kind") == "folder" and lk.get("path"):
                try:
                    FolderPool(st, lk["path"], self.machine_id).sync()
                except OSError:
                    continue
                if st.has_blob(sha):
                    return True
        return st.has_blob(sha)

    def delete_file(self, ctx: Ctx, fid: str) -> None:
        f = self.file_doc(ctx, fid)
        if f.get("owner") != ctx.uid:
            ctx.need("files.delete")
        ctx.st.remove("files", fid, ctx.uid)
        self.record(ctx, "Apagou o arquivo " + f.get("name", ""))

    def move_file(self, ctx: Ctx, fid: str, folder_id: str) -> Dict[str, Any]:
        f = self.file_doc(ctx, fid)
        if f.get("owner") != ctx.uid:
            ctx.need("files.delete")
        self._folder_for(ctx, folder_id)
        return self.public_file(ctx, ctx.st.put("files", fid, {**f, "folder_id": folder_id}, ctx.uid))

    def import_upload(self, ctx: Ctx, upload_id: str, folder_id: str = "") -> Dict[str, Any]:
        """Traz para o Work um anexo do ASTA (qualquer seção) — a ponte Chat/Canvas/Studio → Work."""
        meta = self.store.get_upload(upload_id)
        if not meta:
            raise WorkError(404, "Anexo não encontrado.")
        with open(meta["path"], "rb") as fh:
            return self.upload_file(ctx, meta["name"], fh, os.path.getsize(meta["path"]), folder_id, mime=meta.get("mime", ""))

    def import_project(self, ctx: Ctx, project_id: str, folder_id: str = "") -> Dict[str, Any]:
        """Traz o ZIP de um projeto da Biblioteca (mundo 3D ou jogo 2D) para um setor."""
        project = self.store.get_project(project_id)
        path = self.store.zip_path(project_id, None) if project else None
        if not project or not path:
            raise WorkError(404, "Projeto não encontrado na Biblioteca.")
        with open(path, "rb") as fh:
            return self.upload_file(ctx, safe_filename(project.get("name", "projeto")) + ".zip", fh, os.path.getsize(path), folder_id, mime="application/zip")

    def to_asta_upload(self, ctx: Ctx, fid: str) -> Dict[str, Any]:
        """Copia um arquivo do Work para os anexos do ASTA: dali ele vale em Chat, Mundos, Avatars, Jogos, Canvas, Studio, Code…"""
        path, name, _ = self.open_file(ctx, fid)
        with open(path, "rb") as fh:
            meta = self.store.save_upload_stream(name, mimetypes.guess_type(name)[0] or "", fh, os.path.getsize(path))
        return meta

    # ------------------------------------------------------------------ pedidos
    def can_see_request(self, ctx: Ctx, r: Dict[str, Any]) -> bool:
        return ctx.uid == r.get("from") or ctx.uid in (r.get("to") or []) or ctx.has("requests.view_all")

    def expand_recipients(self, ctx: Ctx, spec: Dict[str, Any]) -> List[str]:
        ids: List[str] = list(S.id_list(spec.get("to")))
        roles, fns = set(S.id_list(spec.get("to_roles"))), set(S.id_list(spec.get("to_functions")))
        for u in ctx.st.all("users"):
            if u.get("role_id") in roles or set(u.get("function_ids") or []) & fns:
                ids.append(u["id"])
        return [i for i in S.dedupe(ids) if ctx.st.get("users", i) and not ctx.st.get("users", i).get("disabled") and i != ctx.uid]

    def send_request(self, ctx: Ctx, spec: Dict[str, Any]) -> Dict[str, Any]:
        ctx.need("requests.send")
        body = text(spec.get("body"), "", 20000)
        atts = [a for a in S.id_list(spec.get("attachments"), 30) if (ctx.st.get("files", a) or {}).get("owner") == ctx.uid or self._visible_file(ctx, a)]
        if not body and not atts:
            raise WorkError(400, "Escreva o pedido, anexe arquivos, ou os dois.")
        to = self.expand_recipients(ctx, spec)
        if not to:
            raise WorkError(400, "Escolha para quem enviar o pedido.")
        title = text(spec.get("title"), "", 120) or (re.split(r"[\n.!?]", body, maxsplit=1)[0].strip()[:90] if body else "Arquivos enviados") or "Pedido"
        rid = "rq_" + new_id("")[:9]
        now = time.time()
        for a in atts:   # o anexo passa a pertencer ao pedido (visível a quem participa dele)
            f = ctx.st.get("files", a)
            if f and not f.get("request_id") and f.get("owner") == ctx.uid:
                ctx.st.put("files", a, {**f, "request_id": rid}, ctx.uid)
        route = self.route_between(ctx.st, ctx.uid, to[0])
        first = S.norm_message({"text": body, "attachments": atts}, ctx.uid, now)
        doc = {"from": ctx.uid, "to": to, "title": title, "body": body, "attachments": atts, "priority": S.pick(spec.get("priority"), S.PRIORITIES, "normal"),
               "due": text(spec.get("due"), "", 40), "status": "sent", "thread": [first], "seen_by": [], "created": now, "route": route,
               "ai": spec.get("ai") if isinstance(spec.get("ai"), dict) else {}, "checklist": [text(c, "", 200) for c in (spec.get("checklist") or [])[:30]] if isinstance(spec.get("checklist"), list) else []}
        out = ctx.st.put("requests", rid, doc, ctx.uid)
        urgent = doc["priority"] in ("high", "urgent")
        self.notify(ctx.st, to, "request", ("🔴 " if urgent else "") + "Novo pedido de " + (ctx.user.get("display_name") or ctx.user["username"]), title, {"type": "request", "id": rid}, ctx.uid)
        self.record(ctx, "Enviou o pedido «" + title + "»", ref={"type": "request", "id": rid})
        return self.public_request(ctx, out)

    def _visible_file(self, ctx: Ctx, fid: str) -> bool:
        f = ctx.st.get("files", fid)
        return bool(f) and self.can_see_file(ctx, f)

    def route_between(self, st: OrgStore, a: str, b: str) -> List[Dict[str, Any]]:
        nodes, edges = st.all("nodes"), st.all("edges")
        anchors = board.anchor_nodes(st.map("users"), nodes)
        ids = board.find_path(nodes, edges, anchors.get(a, []), anchors.get(b, []))
        by = {n["id"]: n for n in nodes}
        return [{"node": i, "label": by[i].get("label", "")} for i in ids]

    def public_request(self, ctx: Ctx, r: Dict[str, Any]) -> Dict[str, Any]:
        files = {}
        for m in r.get("thread") or []:
            for a in m.get("attachments") or []:
                f = ctx.st.get("files", a)
                if f:
                    files[a] = self.public_file(ctx, f)
        route = self.route_between(ctx.st, r["from"], (r.get("to") or [""])[0]) if r.get("to") else []   # o caminho acompanha o quadro: se o fluxograma mudar, ele muda
        return {**{k: r.get(k) for k in ("id", "from", "to", "title", "body", "priority", "due", "status", "thread", "seen_by", "created", "ai", "checklist", "attachments")}, "route": route, "files": files,
                "updated": max([m.get("ts", 0) for m in r.get("thread") or []] + [r.get("created", 0)])}

    def list_requests(self, ctx: Ctx, box: str = "in") -> List[Dict[str, Any]]:
        allr = ctx.st.all("requests")
        if box == "all":
            ctx.need("requests.view_all")
            sel = allr
        elif box == "out":
            sel = [r for r in allr if r.get("from") == ctx.uid]
        else:
            sel = [r for r in allr if ctx.uid in (r.get("to") or [])]
        sel.sort(key=lambda r: max([m.get("ts", 0) for m in r.get("thread") or []] + [r.get("created", 0)]), reverse=True)
        return [{k: v for k, v in self.public_request(ctx, r).items() if k not in ("thread", "files", "body")} | {"unread": ctx.uid not in (r.get("seen_by") or []) and ctx.uid in (r.get("to") or [])} for r in sel[:300]]

    def get_request(self, ctx: Ctx, rid: str) -> Dict[str, Any]:
        r = ctx.st.get("requests", rid)
        if not r or not self.can_see_request(ctx, r):
            raise WorkError(404, "Pedido não encontrado.")
        if ctx.uid in (r.get("to") or []) and ctx.uid not in (r.get("seen_by") or []):
            r = ctx.st.put("requests", rid, {**r, "seen_by": (r.get("seen_by") or []) + [ctx.uid], "status": "seen" if r.get("status") == "sent" else r.get("status")}, ctx.uid)
            if r["status"] == "seen":
                self.notify(ctx.st, [r["from"]], "request_seen", (ctx.user.get("display_name") or "") + " viu o seu pedido", r.get("title", ""), {"type": "request", "id": rid}, ctx.uid)
        return self.public_request(ctx, r)

    def reply_request(self, ctx: Ctx, rid: str, body: str, attachments: Optional[List[str]] = None) -> Dict[str, Any]:
        r = ctx.st.get("requests", rid)
        if not r or not self.can_see_request(ctx, r):
            raise WorkError(404, "Pedido não encontrado.")
        if ctx.uid != r["from"]:
            ctx.need("requests.reply")
        atts = [a for a in S.id_list(attachments, 30) if self._visible_file(ctx, a)]
        body = text(body, "", 20000)
        if not body and not atts:
            raise WorkError(400, "Escreva uma resposta ou anexe arquivos.")
        for a in atts:
            f = ctx.st.get("files", a)
            if f and not f.get("request_id") and f.get("owner") == ctx.uid:
                ctx.st.put("files", a, {**f, "request_id": rid}, ctx.uid)
        msg = S.norm_message({"text": body, "attachments": atts}, ctx.uid, time.time())
        out = ctx.st.put("requests", rid, {**r, "thread": (r.get("thread") or [])[-199:] + [msg]}, ctx.uid)
        self.notify(ctx.st, [x for x in [r["from"], *r.get("to", [])] if x != ctx.uid], "reply", (ctx.user.get("display_name") or "") + " respondeu", r.get("title", ""), {"type": "request", "id": rid}, ctx.uid)
        return self.public_request(ctx, out)

    TRANSITIONS_TO = {"seen", "accepted", "in_progress", "done", "rejected"}

    def set_request_status(self, ctx: Ctx, rid: str, status: str, note: str = "") -> Dict[str, Any]:
        r = ctx.st.get("requests", rid)
        if not r or not self.can_see_request(ctx, r):
            raise WorkError(404, "Pedido não encontrado.")
        if status not in S.REQ_STATUS:
            raise WorkError(400, "Estado inválido.")
        is_to, is_from = ctx.uid in (r.get("to") or []), ctx.uid == r.get("from")
        if status in self.TRANSITIONS_TO and not is_to and not ctx.admin:
            raise WorkError(403, "Só quem recebeu o pedido muda este estado.")
        if status in ("cancelled", "sent") and not (is_from or ctx.has("requests.view_all")):
            raise WorkError(403, "Só quem enviou o pedido (ou a gerência) pode cancelar ou reabrir.")
        msg = S.norm_message({"text": note or ""}, ctx.uid, time.time(), "status")
        msg["status"] = status
        out = ctx.st.put("requests", rid, {**r, "status": status, "thread": (r.get("thread") or [])[-199:] + [msg]}, ctx.uid)
        label = {"accepted": "aceitou", "in_progress": "começou", "done": "concluiu", "rejected": "recusou", "cancelled": "cancelou", "sent": "reabriu", "seen": "viu"}[status]
        self.notify(ctx.st, [x for x in [r["from"], *r.get("to", [])] if x != ctx.uid], "request_status", f"{ctx.user.get('display_name')} {label} o pedido", r.get("title", ""), {"type": "request", "id": rid}, ctx.uid)
        mine = [a for a in ctx.st.all("activities") if a.get("request_id") == rid and a.get("user") == ctx.uid and a.get("state") in ("started", "continuing", "paused")]
        if status == "in_progress" and not mine:
            self.start_activity(ctx, "Pedido: " + r.get("title", ""), request_id=rid)
        elif status in ("done", "rejected", "cancelled"):
            for a in mine:
                self.finish_activity(ctx, a["id"], note or {"done": "Pedido concluído", "rejected": "Pedido recusado", "cancelled": "Pedido cancelado"}[status])
        return self.public_request(ctx, out)

    # ------------------------------------------------------------------ atividades (começou · continuando · terminou)
    def _act_public(self, a: Dict[str, Any], now: float) -> Dict[str, Any]:
        stale = a.get("state") in ("started", "continuing") and now - float(a.get("beat") or a.get("updated") or 0) > S.BEAT_STALE
        return {**{k: a.get(k) for k in ("id", "user", "title", "state", "request_id", "folder_id", "auto", "started", "finished", "log", "beat")}, "stale": stale,
                "elapsed": round((a.get("finished") or now) - (a.get("started") or now))}

    def start_activity(self, ctx: Ctx, title: str, request_id: str = "", folder_id: str = "", note: str = "") -> Dict[str, Any]:
        title = text(title, "", 160)
        if not title:
            raise WorkError(400, "Dê um nome à atividade.")
        now = time.time()
        aid = "a_" + new_id("")[:9]
        doc = {"user": ctx.uid, "title": title, "state": "started", "request_id": request_id if S.valid_id(request_id) else "", "folder_id": folder_id if S.valid_id(folder_id) else "", "auto": False,
               "started": now, "finished": 0, "beat": now, "log": [{"ts": now, "kind": "start", "text": text(note, "", 500)}]}
        return self._act_public(ctx.st.put("activities", aid, doc, ctx.uid), now)

    def _my_act(self, ctx: Ctx, aid: str) -> Dict[str, Any]:
        a = ctx.st.get("activities", aid)
        if not a:
            raise WorkError(404, "Atividade não encontrada.")
        if a.get("user") != ctx.uid:
            raise WorkError(403, "Só a pessoa dona da atividade pode atualizá-la.")
        if a.get("state") in ("finished", "cancelled"):
            raise WorkError(409, "Esta atividade já terminou.")
        return a

    def progress_activity(self, ctx: Ctx, aid: str, note: str = "") -> Dict[str, Any]:
        a = self._my_act(ctx, aid)
        now = time.time()
        log = a.get("log") or []
        if note.strip():
            log = log[-199:] + [{"ts": now, "kind": "progress", "text": text(note, "", 500)}]
        elif a["state"] == "started" or a["state"] == "paused":
            log = log[-199:] + [{"ts": now, "kind": "continue", "text": ""}]
        if a["state"] == "continuing" and not note.strip() and now - float(a.get("beat") or 0) < 40:   # sinal de vida muito frequente: não regrava
            return self._act_public(a, now)
        return self._act_public(ctx.st.put("activities", aid, {**a, "state": "continuing", "beat": now, "log": log}, ctx.uid), now)

    def pause_activity(self, ctx: Ctx, aid: str, note: str = "") -> Dict[str, Any]:
        a = self._my_act(ctx, aid)
        now = time.time()
        return self._act_public(ctx.st.put("activities", aid, {**a, "state": "paused", "beat": now, "log": (a.get("log") or [])[-199:] + [{"ts": now, "kind": "pause", "text": text(note, "", 500)}]}, ctx.uid), now)

    def finish_activity(self, ctx: Ctx, aid: str, note: str = "", cancelled: bool = False) -> Dict[str, Any]:
        a = self._my_act(ctx, aid)
        now = time.time()
        out = ctx.st.put("activities", aid, {**a, "state": "cancelled" if cancelled else "finished", "finished": now, "beat": now,
                                             "log": (a.get("log") or [])[-199:] + [{"ts": now, "kind": "cancel" if cancelled else "finish", "text": text(note, "", 500)}]}, ctx.uid)
        return self._act_public(out, now)

    def record(self, ctx: Ctx, title: str, ref: Optional[Dict[str, Any]] = None) -> None:
        """Registro automático (já terminado) de algo que a pessoa fez no Work: aparece na linha do tempo de atividades."""
        now = time.time()
        try:
            ctx.st.put("activities", "a_" + new_id("")[:9], {"user": ctx.uid, "title": text(title, "", 160), "state": "finished", "request_id": "", "folder_id": "", "auto": True, "started": now,
                                                              "finished": now, "beat": now, "ref": ref or {}, "log": [{"ts": now, "kind": "auto", "text": ""}]}, ctx.uid)
        except ValueError:
            pass

    def list_activities(self, ctx: Ctx, user: str = "", state: str = "", auto: bool = True, limit: int = 200) -> List[Dict[str, Any]]:
        if user and user != ctx.uid:
            ctx.need("activities.view_all")
        if not user and not ctx.has("activities.view_all"):
            user = ctx.uid
        now = time.time()
        rows = [a for a in ctx.st.all("activities") if (not user or a.get("user") == user) and (not state or a.get("state") == state) and (auto or not a.get("auto"))]
        rows.sort(key=lambda a: a["_m"]["ts"], reverse=True)
        return [self._act_public(a, now) for a in rows[:max(1, min(limit, 500))]]

    # ------------------------------------------------------------------ notificações
    def notify(self, st: OrgStore, uids: List[str], kind: str, title: str, body: str = "", ref: Optional[Dict[str, Any]] = None, by: str = "") -> int:
        n = 0
        now = time.time()
        for uid in S.dedupe([u for u in uids if u and u != by]):
            if not st.get("users", uid):
                continue
            st.put("notifications", "nt_" + new_id("")[:9], {"to": uid, "kind": kind, "title": text(title, "", 160), "body": text(body, "", 600), "ref": ref or {}, "by": by, "ts": now, "read": False}, by)
            n += 1
        return n

    def list_notifications(self, ctx: Ctx, unread: bool = False, limit: int = 100) -> Dict[str, Any]:
        mine = [n for n in ctx.st.all("notifications") if n.get("to") == ctx.uid]
        mine.sort(key=lambda n: n.get("ts", 0), reverse=True)
        items = [n for n in mine if not unread or not n.get("read")][:max(1, min(limit, 300))]
        return {"items": [{k: n.get(k) for k in ("id", "kind", "title", "body", "ref", "by", "ts", "read")} for n in items], "unread": sum(1 for n in mine if not n.get("read"))}

    def mark_read(self, ctx: Ctx, ids: Optional[List[str]] = None, everything: bool = False) -> int:
        n = 0
        want = set(S.id_list(ids, 500))
        for d in ctx.st.all("notifications"):
            if d.get("to") == ctx.uid and not d.get("read") and (everything or d["id"] in want):
                ctx.st.put("notifications", d["id"], {**d, "read": True}, ctx.uid)
                n += 1
        return n

    def broadcast(self, ctx: Ctx, title: str, body: str, audience: Dict[str, Any]) -> int:
        ctx.need("notifications.broadcast")
        title = text(title, "", 160)
        if not title:
            raise WorkError(400, "Escreva o aviso.")
        users = ctx.st.all("users")
        if audience.get("all"):
            ids = [u["id"] for u in users]
        else:
            roles, fns = set(S.id_list(audience.get("roles"))), set(S.id_list(audience.get("functions")))
            ids = S.id_list(audience.get("users")) + [u["id"] for u in users if u.get("role_id") in roles or set(u.get("function_ids") or []) & fns]
        n = self.notify(ctx.st, [i for i in ids if not (ctx.st.get("users", i) or {}).get("disabled")], "broadcast", title, body, {}, ctx.uid)
        self.record(ctx, f"Enviou o aviso «{title}» a {n} pessoa(s)")
        return n

    # ------------------------------------------------------------------ máquinas, redes e sincronização
    def network(self, ctx: Ctx) -> Dict[str, Any]:
        now = time.time()
        machines = []
        for m in sorted(ctx.st.all("machines"), key=lambda m: (m["id"] != self.machine_id, m.get("name", "").lower())):
            last = now if m["id"] == self.machine_id else self.contact.get(m["id"], 0)
            machines.append({**{k: m.get(k) for k in ("id", "name", "os", "addrs", "backup", "hold", "revoked", "tailnet", "added")}, "self": m["id"] == self.machine_id,
                             "online": now - last < 120, "last_contact": last,
                             "users": [u["display_name"] for u in ctx.st.all("users") if m["id"] in (u.get("home_machines") or [])][:12]})
        st = self.sync.status.get(ctx.st.id, {})
        host, addrs = self.listen_address()
        cfg = self.config()
        return {"machine": {"id": self.machine_id, "name": self.ident["name"], "os": self.ident["os"]}, "machines": machines, "tailscale": tailscale.status(), "listening": bool(self.peer_server),
                "listen": {**cfg["peer"], "host": host, "addrs": addrs}, "links": ctx.st.local().get("links") or [], "sync": st, "auto_sync": cfg["auto_sync"], "interval": cfg["interval"],
                "last_sync": ctx.st.local().get("last_sync", 0), "can_manage": ctx.has("network.manage"), "invites": len(ctx.st.invites())}

    def update_machine(self, ctx: Ctx, mid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        m = ctx.st.get("machines", mid)
        if not m:
            raise WorkError(404, "Máquina não encontrada.")
        if mid == self.machine_id and set(patch) <= {"name"}:
            self.rename_machine(patch.get("name", ""))
            return ctx.st.get("machines", mid) or m
        ctx.need("network.manage")
        if mid == self.machine_id:   # o nome e o endereço vêm do que a máquina é de fato; o resto (backup, política) o gerente decide
            patch = {k: v for k, v in patch.items() if k in ("backup", "hold")}
        data = S.norm_machine({k: v for k, v in patch.items() if k in ("name", "backup", "hold", "revoked")}, m)
        if mid == self.machine_id:
            data["revoked"] = False
        return ctx.st.put("machines", mid, {**data, "added": m.get("added")}, ctx.uid)

    def add_link(self, ctx: Ctx, kind: str, target: str) -> List[Dict[str, Any]]:
        ctx.need("network.manage")
        target = text(target, "", 400)
        if kind not in ("peer", "folder") or not target:
            raise WorkError(400, "Informe o endereço (ip:porta) ou a pasta.")
        if kind == "folder":
            p = Path(target).expanduser()
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise WorkError(400, f"Não consegui usar essa pasta: {exc}") from None
            target = str(p)
        links = [lk for lk in (ctx.st.local().get("links") or []) if lk.get("addr", lk.get("path")) != target]
        links.append({"kind": kind, "addr" if kind == "peer" else "path": target})
        ctx.st.save_local({"links": links})
        self.sync.nudge()
        return links

    def remove_link(self, ctx: Ctx, target: str) -> List[Dict[str, Any]]:
        ctx.need("network.manage")
        links = [lk for lk in (ctx.st.local().get("links") or []) if lk.get("addr", lk.get("path")) != target]
        ctx.st.save_local({"links": links})
        return links

    def sync_now(self, ctx: Ctx) -> Dict[str, Any]:
        ctx.need("network.manage")
        return self.sync.run_org(ctx.st.id)

    def set_network_config(self, ctx: Ctx, patch: Dict[str, Any]) -> Dict[str, Any]:
        ctx.need("network.manage")
        cur = self.store.get_settings().get("work") or {}
        new = normalize_config({**cur, **{k: v for k, v in patch.items() if k in ("auto_sync", "interval", "peer")}, "peer": {**(cur.get("peer") or {}), **(patch.get("peer") or {})}})
        self.store.save_settings({"work": new})
        res = self.apply_network()
        if self.orgs:
            self.sync.start()
        return {**res, "config": new}

    # ------------------------------------------------------------------ backup
    def my_files(self, st: OrgStore, uid: str = "") -> List[Dict[str, Any]]:
        return [f for f in st.all("files") if not uid or f.get("owner") == uid]

    def backup_status(self, ctx: Ctx) -> Dict[str, Any]:
        machines = {m["id"]: m for m in ctx.st.all("machines") if not m.get("revoked")}
        targets = [{"id": m["id"], "name": m["name"], "hold": m.get("hold"), "online": time.time() - self.contact.get(m["id"], time.time() if m["id"] == self.machine_id else 0) < 120,
                    "self": m["id"] == self.machine_id} for m in machines.values() if m.get("backup")]
        users = []
        for u in ctx.st.all("users"):
            if u["id"] != ctx.uid and not ctx.has("backup.manage"):
                continue
            files = self.my_files(ctx.st, u["id"])
            users.append({"id": u["id"], "name": u.get("display_name"), "files": len(files), "bytes": sum((f["versions"][-1]["size"] if f.get("versions") else 0) for f in files),
                          "backup_machines": [m for m in u.get("backup_machines") or [] if m in machines]})
        return {"targets": targets, "users": users, "snapshots": ctx.st.snapshots() if (machines.get(self.machine_id) or {}).get("backup") else [], "this_is_backup": bool((machines.get(self.machine_id) or {}).get("backup"))}

    def verify_backup(self, ctx: Ctx, mid: str) -> Dict[str, Any]:
        """Pergunta à máquina de backup quais arquivos que deviam estar lá estão lá."""
        if not ctx.has("backup.manage"):
            ctx.need("backup.manage")
        m = ctx.st.get("machines", mid)
        if not m or not m.get("backup"):
            raise WorkError(404, "Essa não é uma máquina de backup.")
        wanted = [(f, sha) for f in ctx.st.all("files") if should_hold(ctx.st, m, f) for sha in file_shas(f)[-1:]]
        shas = [s for _, s in wanted]
        have: Set[str] = set()
        if mid == self.machine_id:
            have = {s for s in shas if ctx.st.has_blob(s)}
        else:
            ok = False
            for addr in m.get("addrs") or []:
                try:
                    have = set(HttpPeer(ctx.st.id, ctx.st.secret(), self.machine_id, addr, timeout=10).have(shas))
                    ok = True
                    break
                except PeerError:
                    continue
            if not ok:
                raise WorkError(503, f"A máquina «{m.get('name')}» não respondeu.")
        missing = [{"id": f["id"], "name": f.get("name")} for f, s in wanted if s not in have]
        return {"machine": mid, "expected": len(shas), "present": len(have), "missing": missing[:100]}

    def restore_from(self, ctx: Ctx, mid: str, uid: str = "") -> Dict[str, Any]:
        """Traz de volta, de uma máquina de backup, os arquivos que faltam aqui (de uma pessoa ou de todas)."""
        ctx.need("backup.manage")
        m = ctx.st.get("machines", mid)
        if not m or mid == self.machine_id:
            raise WorkError(404, "Escolha outra máquina da rede.")
        got = failed = 0
        for f in self.my_files(ctx.st, uid):
            for sha in file_shas(f):
                if ctx.st.has_blob(sha):
                    continue
                done = False
                for addr in m.get("addrs") or []:
                    try:
                        peer = HttpPeer(ctx.st.id, ctx.st.secret(), self.machine_id, addr, timeout=15)
                        if sha in peer.have([sha]):
                            done = _download(ctx.st, peer, sha)
                        break
                    except PeerError:
                        continue
                got, failed = got + int(done), failed + int(not done)
        self.record(ctx, f"Restaurou {got} arquivo(s) da máquina de backup «{m.get('name')}»")
        return {"restored": got, "failed": failed}

    def snapshot_now(self, ctx: Ctx) -> Dict[str, Any]:
        ctx.need("backup.manage")
        p = ctx.st.snapshot(self.config()["backup_keep"])
        return {"name": p.name, "size": p.stat().st_size}

    def maintenance(self) -> None:
        """Chamado pelo ciclo de sincronização: máquinas de backup guardam uma cópia dos documentos por dia."""
        for st in self.orgs.values():
            me = st.get("machines", self.machine_id)
            if me and me.get("backup"):
                snaps = st.snapshots()
                if not snaps or time.time() - snaps[0]["ts"] > 86400:
                    st.snapshot(self.config()["backup_keep"])

    # ------------------------------------------------------------------ exportar tudo (o usuário leva os dados quando quiser)
    def export_zip(self, ctx: Ctx, dest: Path, with_files: bool = False) -> Path:
        ctx.need("org.manage")
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for coll in S.COLLECTIONS:
                for d in ctx.st.all(coll):
                    clean = {k: v for k, v in d.items() if k != "pw"}
                    z.writestr(f"docs/{coll}/{d['id']}.json", json.dumps(clean, ensure_ascii=False, indent=1))
            if with_files:
                for f in ctx.st.all("files"):
                    for v in f.get("versions") or []:
                        if ctx.st.has_blob(v["sha"]):
                            z.write(ctx.st.blob_path(v["sha"]), f"files/{f['id']}/v{v['n']}/{safe_filename(f.get('name', 'arquivo'))}")
            z.writestr("LEIAME.txt", "Exportação do ASTA Work. docs/ = documentos (JSON aberto); files/ = arquivos. Senhas e a chave da rede não vão neste pacote.\n")
        return dest
