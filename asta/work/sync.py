"""Sincronização do Work entre máquinas — sem servidor central.

Transportes (todos fazem a mesma coisa: trazer o que é mais novo, mandar o que é mais novo, e levar/trazer os arquivos conforme a política de cada máquina):
  • **HTTP entre máquinas** (`HttpPeer` ↔ `PeerServer`): pela tailnet do Tailscale, pela rede local ou por qualquer endereço alcançável. O servidor de sincronização é **separado** da
    WebUI (que continua só em 127.0.0.1) e só responde a `/peer/v1/…`. Toda mensagem vai assinada (HMAC) e cifrada (`crypto.seal`) com o segredo da rede.
  • **Pasta de nuvem** (`FolderPool`): uma pasta que o usuário já sincroniza (Drive, Dropbox, NAS…); tudo que o ASTA grava lá vai cifrado.

Quem manda: cada lado pode iniciar. Uma máquina que não escuta (atrás de NAT) sincroniza do mesmo jeito, por iniciativa própria, a cada poucos segundos.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import platform
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..util import new_id
from . import crypto, perms as P
from .store import OrgStore, is_sha

PROTO = "peer/v1"
CHUNK = 4 << 20
BATCH = 150
SKEW = 300
JSON_LIMIT = 24 << 20
INVITE_TTL = 24 * 3600
DEFAULT_PORT = 8790


class PeerError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


# ============================================================================ convite
def make_invite(org_id: str, org_name: str, key: str, addrs: List[str]) -> str:
    raw = json.dumps({"o": org_id, "n": org_name, "k": key, "a": addrs[:8]}, separators=(",", ":")).encode()
    return "AW1." + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def parse_invite(code: str) -> Dict[str, Any]:
    code = (code or "").strip()
    if not code.startswith("AW1."):
        raise ValueError("Código de convite inválido.")
    try:
        body = code[4:]
        d = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if not (isinstance(d, dict) and isinstance(d.get("o"), str) and isinstance(d.get("k"), str) and len(d["k"]) == 64 and isinstance(d.get("a"), list)):
            raise ValueError
        return {"org": d["o"], "name": str(d.get("n") or "")[:80], "key": d["k"], "addrs": [str(a)[:120] for a in d["a"] if isinstance(a, str)][:8]}
    except (ValueError, TypeError):
        raise ValueError("Código de convite inválido.") from None


# ============================================================================ cliente HTTP
def _split(addr: str) -> Tuple[str, int]:
    u = urllib.parse.urlsplit("//" + addr.strip().replace("http://", ""))
    if not u.hostname:
        raise PeerError("endereço inválido: " + addr)
    return u.hostname, u.port or DEFAULT_PORT


class HttpPeer:
    """Fala com o servidor de sincronização de outra máquina. `secret` é o da rede (ou a chave do convite, no `join`)."""

    def __init__(self, org_id: str, secret: str, machine_id: str, addr: str, timeout: float = 20.0, invite_id: str = ""):
        self.org, self.secret, self.mid, self.addr, self.timeout, self.iid = org_id, secret, machine_id, addr, timeout, invite_id
        self.host, self.port = _split(addr)
        self.peer_machine = ""

    def _request(self, method: str, op: str, query: Dict[str, Any], body: bytes) -> bytes:
        nonce = crypto.token(12)
        ts = str(int(time.time()))
        path = f"/{PROTO}/{self.org}/{op}" + ("?" + urllib.parse.urlencode(query) if query else "")
        sealed = crypto.seal(self.secret, body, (nonce + "|req").encode()) if body else b""
        sig = crypto.sign(self.secret, method, path, ts, nonce, hashlib.sha256(sealed).hexdigest())
        headers = {"X-Work-M": self.mid, "X-Work-T": ts, "X-Work-N": nonce, "X-Work-S": sig, "Content-Type": "application/octet-stream", "Content-Length": str(len(sealed))}
        if self.iid:
            headers["X-Work-I"] = self.iid
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            conn.request(method, path, body=sealed or None, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
        except (OSError, http.client.HTTPException) as exc:
            raise PeerError(f"sem conexão com {self.addr}: {exc}") from None
        finally:
            conn.close()
        if resp.status != 200:
            try:
                msg = json.loads(data).get("error", "")
            except ValueError:
                msg = ""
            raise PeerError(msg or f"erro {resp.status} de {self.addr}", resp.status)
        try:
            return crypto.unseal(self.secret, data, (nonce + "|resp").encode()) if data else b""
        except ValueError as exc:
            raise PeerError(f"resposta de {self.addr} não confere ({exc}): a chave da rede é outra?") from None

    def call(self, op: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raw = self._request("POST", op, {}, json.dumps(payload or {}, ensure_ascii=False).encode())
        try:
            d = json.loads(raw or b"{}")
        except ValueError:
            raise PeerError("resposta inválida") from None
        return d if isinstance(d, dict) else {}

    def get_chunk(self, sha: str, off: int, size: int = CHUNK) -> bytes:
        return self._request("GET", "blob", {"sha": sha, "off": off, "len": size}, b"")

    def put_chunk(self, sha: str, off: int, data: bytes) -> None:
        self._request("POST", "blob", {"sha": sha, "off": off}, data)

    def commit(self, sha: str) -> bool:
        return bool(self.call("blob_commit", {"sha": sha}).get("ok"))

    def have(self, shas: List[str]) -> List[str]:
        out: List[str] = []
        for i in range(0, len(shas), 500):
            out += [s for s in self.call("have", {"shas": shas[i:i + 500]}).get("have", []) if isinstance(s, str)]
        return out


# ============================================================================ política de réplica dos arquivos
def should_hold(st: OrgStore, machine: Dict[str, Any], fdoc: Dict[str, Any], _cache: Optional[Dict[str, Any]] = None) -> bool:
    """Esta máquina deve guardar o conteúdo deste arquivo? (calculado igual nos dois lados, só com dados sincronizados)

    «all» guarda tudo (servidor/hub). «needed» guarda o que importa para quem usa a máquina: os arquivos das pessoas que entram nela, os dos setores que elas enxergam, os dos pedidos
    em que participam e os de quem escolheu esta máquina como backup."""
    if not machine or machine.get("revoked"):
        return False
    if machine.get("hold") == "all":
        return True
    mid = machine["id"]
    users = st.map("users")
    owner = users.get(fdoc.get("owner") or "")
    if owner and mid in (owner.get("backup_machines") or []):
        return True
    cache = _cache if _cache is not None else {}
    homed = cache.get(("homed", mid))
    if homed is None:
        roles, fns = st.map("roles"), st.map("functions")
        homed = [(u, P.effective(u, roles, fns)) for u in users.values() if mid in (u.get("home_machines") or []) and not u.get("disabled")]
        cache[("homed", mid)] = homed
    if owner and any(u["id"] == owner["id"] for u, _ in homed):
        return True
    rid = fdoc.get("request_id")
    if rid:
        req = st.get("requests", rid)
        if req:
            people = {req.get("from")} | set(req.get("to") or [])
            return any(u["id"] in people for u, _ in homed)
        return False
    folder = st.get("folders", fdoc.get("folder_id") or "")
    if folder:
        return any(P.folder_visible(folder, u, pr) for u, pr in homed)
    return False


def file_shas(fdoc: Dict[str, Any]) -> List[str]:
    return [v["sha"] for v in (fdoc.get("versions") or []) if isinstance(v, dict) and is_sha(v.get("sha"))]


def plan_blobs(st: OrgStore, my_mid: str, peer_mid: str) -> Tuple[List[str], List[str]]:
    """(o que enviar ao par, o que buscar nele), só pela política e pelo que cada lado precisa."""
    machines = st.map("machines")
    me, other = machines.get(my_mid), machines.get(peer_mid)
    push: List[str] = []
    pull: List[str] = []
    cache: Dict[str, Any] = {}
    for f in st.all("files"):
        for sha in file_shas(f):
            if st.has_blob(sha):
                if other and should_hold(st, other, f, cache) and sha not in push:
                    push.append(sha)
            elif me and should_hold(st, me, f, cache) and sha not in pull:
                pull.append(sha)
    return push, pull


# ============================================================================ sincronização com um par HTTP
def sync_http(st: OrgStore, peer: HttpPeer, my_mid: str, cancelled: Callable[[], bool] = lambda: False) -> Dict[str, Any]:
    rep = {"docs_in": 0, "docs_out": 0, "blobs_in": 0, "blobs_out": 0, "peer": ""}
    hello = peer.call("hello")
    rep["peer"] = peer.peer_machine = str(hello.get("machine") or "")
    r = peer.call("manifest", {"digest": st.digest()})
    if not r.get("same"):
        remote = {k: tuple(v) for k, v in (r.get("manifest") or {}).items() if isinstance(v, list) and len(v) == 3}
        local = {k: tuple(v) for k, v in st.manifest().items()}
        want = [k for k, v in remote.items() if k not in local or v > local[k]]
        send = [k for k, v in local.items() if k not in remote or v > remote[k]]
        for i in range(0, len(want), BATCH):
            if cancelled():
                return rep
            for item in peer.call("docs", {"keys": want[i:i + BATCH]}).get("docs", []):
                if isinstance(item, dict) and st.merge(str(item.get("c")), item.get("doc")):
                    rep["docs_in"] += 1
        for i in range(0, len(send), BATCH):
            if cancelled():
                return rep
            batch = [{"c": k.partition("/")[0], "doc": st.doc_dump(k)} for k in send[i:i + BATCH] if st.doc_dump(k)]
            rep["docs_out"] += int(peer.call("push", {"docs": batch}).get("merged") or 0)
    push, pull = plan_blobs(st, my_mid, rep["peer"])
    if push:
        have = set(peer.have(push))
        for sha in push:
            if cancelled():
                return rep
            if sha in have:
                continue
            _upload(st, peer, sha)
            rep["blobs_out"] += 1
    if pull:
        have = set(peer.have(pull))
        for sha in pull:
            if cancelled():
                return rep
            if sha in have and _download(st, peer, sha):
                rep["blobs_in"] += 1
    return rep


def _upload(st: OrgStore, peer: HttpPeer, sha: str) -> None:
    off = 0
    size = st.blob_size(sha)
    while off < size:
        data = st.blob_chunks(sha, off, CHUNK)
        if not data:
            break
        peer.put_chunk(sha, off, data)
        off += len(data)
    if not peer.commit(sha):
        raise PeerError("o par recusou o arquivo (hash não confere)")


def _download(st: OrgStore, peer: HttpPeer, sha: str) -> bool:
    st.incoming_path(sha).unlink(missing_ok=True)
    off = 0
    while True:
        data = peer.get_chunk(sha, off, CHUNK)
        if not data:
            break
        off = st.incoming_write(sha, off, data)
        if len(data) < CHUNK:
            break
    return st.incoming_commit(sha)


# ============================================================================ servidor do par (lado de quem recebe)
class PeerService:
    """A lógica das rotas `/peer/v1/<rede>/<op>`. `manager` fornece as redes abertas aqui (`org_store(id)`) e as ações de senha."""

    def __init__(self, manager: Any):
        self.m = manager
        self._nonces: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _fresh(self, ts: str, nonce: str) -> bool:
        try:
            if abs(time.time() - int(ts)) > SKEW or not nonce or len(nonce) > 64:
                return False
        except ValueError:
            return False
        with self._lock:
            now = time.time()
            if len(self._nonces) > 5000:
                self._nonces = {k: v for k, v in self._nonces.items() if v > now}
            if nonce in self._nonces:
                return False
            self._nonces[nonce] = now + SKEW * 2
        return True

    def handle(self, method: str, raw_path: str, headers: Any, body: bytes) -> Tuple[int, bytes]:
        u = urllib.parse.urlsplit(raw_path)
        parts = u.path.strip("/").split("/")
        if len(parts) != 4 or "/".join(parts[:2]) != PROTO:
            return 404, _err("não encontrado")
        org, op = parts[2], parts[3]
        st = self.m.org_store(org)
        if st is None:
            return 404, _err("rede desconhecida aqui")
        mid, ts, nonce, sig = (headers.get("X-Work-M") or ""), (headers.get("X-Work-T") or ""), (headers.get("X-Work-N") or ""), (headers.get("X-Work-S") or "")
        key = st.secret()
        iid = headers.get("X-Work-I") or ""
        if op == "join":
            key = st.invite_key(iid)
            if not key:
                return 403, _err("convite inválido, usado ou vencido")
        if not key or not crypto.check_sig(key, sig, method, raw_path, ts, nonce, hashlib.sha256(body).hexdigest()):
            return 401, _err("assinatura inválida")
        if not self._fresh(ts, nonce):
            return 401, _err("pedido vencido ou repetido")
        if op != "join":
            m = st.get("machines", mid)
            if not m or m.get("revoked"):
                return 403, _err("esta máquina não faz parte da rede (ou foi revogada)")
            self.m.touch(mid)
        try:
            plain = crypto.unseal(key, body, (nonce + "|req").encode()) if body else b""
            out = self._dispatch(st, op, mid, dict(urllib.parse.parse_qsl(u.query)), plain, iid)
        except PeerError as exc:
            return exc.status or 400, _err(str(exc))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            return 400, _err(f"pedido inválido: {exc}")
        return 200, crypto.seal(key, out if isinstance(out, bytes) else json.dumps(out, ensure_ascii=False).encode(), (nonce + "|resp").encode())

    def _dispatch(self, st: OrgStore, op: str, mid: str, q: Dict[str, str], plain: bytes, iid: str) -> Any:
        data: Dict[str, Any] = {}
        if op not in ("blob",) and plain:
            data = json.loads(plain)
            if not isinstance(data, dict):
                raise PeerError("corpo inválido")
        if op == "hello":
            return {"machine": self.m.machine_id, "org": st.id, "digest": st.digest(), "proto": 1}
        if op == "manifest":
            if data.get("digest") == st.digest():
                return {"same": True}
            return {"same": False, "digest": st.digest(), "manifest": st.manifest()}
        if op == "docs":
            keys = [k for k in data.get("keys", []) if isinstance(k, str)][:BATCH * 2]
            return {"docs": [{"c": k.partition("/")[0], "doc": st.doc_dump(k)} for k in keys if st.doc_dump(k)]}
        if op == "push":
            n = sum(1 for it in data.get("docs", []) if isinstance(it, dict) and st.merge(str(it.get("c")), it.get("doc")))
            return {"merged": n}
        if op == "have":
            return {"have": [s for s in data.get("shas", []) if is_sha(s) and st.has_blob(s)]}
        if op == "blob":
            sha = q.get("sha", "")
            if not is_sha(sha):
                raise PeerError("hash inválido")
            if plain or "len" not in q:   # envio de um pedaço (POST) ou leitura (GET sem corpo)
                return {"size": st.incoming_write(sha, int(q.get("off", "0")), plain)} if plain else b""
            if not st.has_blob(sha):
                raise PeerError("não tenho esse arquivo", 404)
            return st.blob_chunks(sha, max(0, int(q.get("off", "0"))), min(int(q["len"]), CHUNK))
        if op == "blob_commit":
            return {"ok": st.incoming_commit(str(data.get("sha")))}
        if op == "verify_password":
            return {"ok": self.m.verify_local_password(st, str(data.get("user")), str(data.get("password")))}
        if op == "vault_put":
            return {"ok": self.m.accept_vault(st, str(data.get("user")), data.get("rec"), mid)}
        if op == "join":
            return self.m.accept_join(st, iid, data)
        raise PeerError("operação desconhecida", 404)


def _err(msg: str) -> bytes:
    return json.dumps({"error": msg}, ensure_ascii=False).encode()


class PeerServer:
    """Escuta só `/peer/v1/…` num endereço escolhido (IP da tailnet, rede local ou outro). A WebUI NÃO é servida aqui."""

    def __init__(self, service: PeerService, host: str, port: int):
        outer = service

        class H(BaseHTTPRequestHandler):
            server_version = "ASTA-Work"
            sys_version = ""
            protocol_version = "HTTP/1.1"

            def log_message(self, *a: Any) -> None:
                pass

            def _go(self, method: str) -> None:
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n < 0 or n > JSON_LIMIT:
                        self._send(413, _err("corpo grande demais"))
                        return
                    body = self.rfile.read(n) if n else b""
                    status, data = outer.handle(method, self.path, self.headers, body)
                except Exception as exc:  # noqa: BLE001
                    status, data = 500, _err(f"erro interno: {exc}")
                self._send(status, data)

            def _send(self, status: int, data: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/octet-stream" if status == 200 else "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                self._go("GET")

            def do_POST(self) -> None:
                self._go("POST")

        class S(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        self.httpd = S((host, port), H)
        self.host, self.port = host, self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.3}, daemon=True, name="asta-work-peer")
        self.thread.start()

    def stop(self) -> None:
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except OSError:
            pass


# ============================================================================ pasta de nuvem (cifrada)
class FolderPool:
    """Sincroniza por uma pasta compartilhada qualquer. Cada máquina grava `state-<id>.sealed` (seus documentos) e `blobs/<apelido>` (arquivos em quadros cifrados)."""

    def __init__(self, st: OrgStore, path: str, my_mid: str):
        self.st, self.mid = st, my_mid
        self.dir = Path(path).expanduser() / st.id
        self.secret = st.secret()

    def _write_atomic(self, p: Path, data: bytes) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)

    def sync(self, cancelled: Callable[[], bool] = lambda: False) -> Dict[str, Any]:
        rep = {"docs_in": 0, "docs_out": 0, "blobs_in": 0, "blobs_out": 0, "peer": "pasta"}
        self.dir.mkdir(parents=True, exist_ok=True)
        # 1) traz o que os outros gravaram
        for f in sorted(self.dir.glob("state-*.sealed")):
            if f.name == f"state-{self.mid}.sealed":
                continue
            try:
                state = json.loads(crypto.unseal(self.secret, f.read_bytes(), b"state|" + f.stem[6:].encode()))
            except (OSError, ValueError):
                continue   # arquivo ainda sendo enviado pelo serviço de nuvem, ou de outra rede
            for item in state.get("docs", []):
                if isinstance(item, dict) and self.st.merge(str(item.get("c")), item.get("doc")):
                    rep["docs_in"] += 1
        # 2) grava o meu estado se mudou
        dig = self.st.digest()
        mine = self.dir / f"state-{self.mid}.sealed"
        if not mine.exists() or (self.st.local().get("folder_digest") or {}).get(str(self.dir)) != dig:
            docs = [{"c": k.partition("/")[0], "doc": self.st.doc_dump(k)} for k in self.st.manifest()]
            self._write_atomic(mine, crypto.seal(self.secret, json.dumps({"docs": docs}, ensure_ascii=False).encode(), b"state|" + self.mid.encode()))
            fd = dict(self.st.local().get("folder_digest") or {})
            fd[str(self.dir)] = dig
            self.st.save_local({"folder_digest": fd})
            rep["docs_out"] = len(docs)
        # 3) arquivos
        machines = self.st.map("machines")
        me = machines.get(self.mid)
        cache: Dict[str, Any] = {}
        for f in self.st.all("files"):
            for sha in file_shas(f):
                if cancelled():
                    return rep
                alias = self.dir / "blobs" / crypto.blob_alias(self.secret, sha)
                if self.st.has_blob(sha):
                    if not alias.exists() and any(should_hold(self.st, m, f, cache) for m in machines.values() if m["id"] != self.mid):
                        self._put_blob(sha, alias)
                        rep["blobs_out"] += 1
                elif alias.exists() and me and should_hold(self.st, me, f, cache) and self._get_blob(sha, alias):
                    rep["blobs_in"] += 1
        return rep

    def _put_blob(self, sha: str, alias: Path) -> None:
        out = bytearray()
        i, off, size = 0, 0, self.st.blob_size(sha)
        while off < size:
            data = self.st.blob_chunks(sha, off, CHUNK)
            sealed = crypto.seal(self.secret, data, alias.name.encode() + b"|" + str(i).encode())
            out += len(sealed).to_bytes(4, "big") + sealed
            off, i = off + len(data), i + 1
            if len(out) > (256 << 20):   # arquivos enormes: grava aos poucos
                self._append(alias, bytes(out))
                out.clear()
        self._append(alias, bytes(out), final=True)

    def _append(self, alias: Path, data: bytes, final: bool = False) -> None:
        tmp = alias.with_name(f".{alias.name}.{os.getpid()}.part")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "ab") as fh:
            fh.write(data)
        if final:
            os.replace(tmp, alias)

    def _get_blob(self, sha: str, alias: Path) -> bool:
        part = self.st.incoming_path(sha)
        part.unlink(missing_ok=True)
        try:
            with open(alias, "rb") as fh:
                i = 0
                while True:
                    head = fh.read(4)
                    if not head:
                        break
                    sealed = fh.read(int.from_bytes(head, "big"))
                    self.st.incoming_write(sha, part.stat().st_size if part.exists() else 0, crypto.unseal(self.secret, sealed, alias.name.encode() + b"|" + str(i).encode()))
                    i += 1
        except (OSError, ValueError):
            part.unlink(missing_ok=True)
            return False
        return self.st.incoming_commit(sha)


# ============================================================================ o serviço em segundo plano
class SyncService:
    """Roda a sincronização de todas as redes abertas: a cada `interval` segundos e logo após uma mudança local (`nudge`)."""

    def __init__(self, manager: Any, interval: float = 15.0):
        self.m = manager
        self.interval = interval
        self.wake = threading.Event()
        self.stop_ev = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.status: Dict[str, Dict[str, Any]] = {}
        self.locks: Dict[str, threading.Lock] = {}

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_ev.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="asta-work-sync")
        self.thread.start()

    def stop(self) -> None:
        self.stop_ev.set()
        self.wake.set()

    def nudge(self) -> None:
        self.wake.set()

    def _loop(self) -> None:
        while not self.stop_ev.is_set():
            self.wake.wait(self.interval)
            if self.stop_ev.is_set():
                return
            if self.wake.is_set():
                self.wake.clear()
                time.sleep(0.6)   # junta várias mudanças seguidas num envio só
            try:
                self.m.maintenance()
            except Exception:  # noqa: BLE001
                pass
            if not self.m.auto_sync_enabled():
                continue
            for oid in self.m.org_ids():
                try:
                    self.run_org(oid)
                except Exception as exc:  # noqa: BLE001
                    self.status.setdefault(oid, {})["error"] = str(exc)[:200]

    def targets(self, st: OrgStore) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for m in st.all("machines"):
            if m["id"] == self.m.machine_id or m.get("revoked"):
                continue
            for a in m.get("addrs") or []:
                out.append({"kind": "peer", "addr": a, "machine": m["id"]})
        for lk in st.local().get("links") or []:
            if isinstance(lk, dict) and lk.get("kind") == "peer" and lk.get("addr"):
                out.append({"kind": "peer", "addr": lk["addr"], "machine": ""})
            elif isinstance(lk, dict) and lk.get("kind") == "folder" and lk.get("path"):
                out.append({"kind": "folder", "path": lk["path"]})
        uniq = []
        for t in out:
            k = t.get("addr") or t.get("path")
            if k not in seen:
                seen.add(k)
                uniq.append(t)
        return uniq

    def run_org(self, oid: str, only: str = "") -> Dict[str, Any]:
        st = self.m.org_store(oid)
        if st is None or not st.secret():
            return {}
        lock = self.locks.setdefault(oid, threading.Lock())
        if not lock.acquire(blocking=False):
            return self.status.get(oid, {})
        results: List[Dict[str, Any]] = []
        try:
            self.m.refresh_self(st)
            by_machine_ok = set()
            for t in self.targets(st):
                if only and (t.get("addr") or t.get("path")) != only:
                    continue
                if t.get("machine") and t["machine"] in by_machine_ok:
                    continue
                label = t.get("addr") or t.get("path")
                try:
                    if t["kind"] == "peer":
                        rep = sync_http(st, HttpPeer(oid, st.secret(), self.m.machine_id, t["addr"], timeout=12), self.m.machine_id)
                        by_machine_ok.add(rep.get("peer") or t.get("machine"))
                    else:
                        rep = FolderPool(st, t["path"], self.m.machine_id).sync()
                    results.append({"target": label, "ok": True, **rep})
                except (PeerError, OSError) as exc:
                    results.append({"target": label, "ok": False, "error": str(exc)[:200]})
            snap = {"ts": time.time(), "results": results, "error": ""}
            self.status[oid] = snap
            if results and any(r.get("ok") for r in results):
                st.save_local({"last_sync": snap["ts"]})
            return snap
        finally:
            lock.release()


def local_machine_info(name: str = "") -> Dict[str, Any]:
    return {"name": name or platform.node() or "Máquina", "os": f"{platform.system()} {platform.release()}"[:40]}


def new_machine_id() -> str:
    return new_id("m_")
