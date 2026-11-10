"""Armazenamento de UMA organização do Work, em arquivos comuns (JSON + blobs), dentro de `~/.asta/work/<org>/`:

    org.json                     identidade local (id, quando entrou)         — não sincroniza
    secret.json                  segredo da rede (0600)                       — nunca sai por sincronização; só por convite
    local.json                   preferências desta máquina (escuta, links)   — não sincroniza
    docs/<coleção>/<id>.json     documentos (usuários, cargos, quadro, pedidos, atividades…) — sincronizam
    blobs/<aa>/<sha256>          conteúdo dos arquivos, endereçado pelo hash (qualquer formato) — sincroniza conforme a política
    vault/<usuário>.json         hash da senha (0600)                         — só nesta máquina, ou replicado se o usuário escolheu «todas»
    snapshots/<data>.zip         cópias periódicas dos documentos (máquinas de backup)

Cada documento leva `_m = {rev, ts, by, origin, deleted}`. Na sincronização vale o **mais novo por documento**: compara-se `(rev, ts, origin)` — quem editou mais vezes ganha; empate → o
relógio; empate → o id da máquina. É o modelo de «último vence» por documento (cada nó, ligação, pedido, atividade e arquivo é um documento próprio, então edições em lugares
diferentes nunca se atropelam). Apagar vira uma «lápide» (`deleted`) que também sincroniza.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable, Dict, Iterator, List, Optional, Tuple

from ..util import read_json, write_json
from . import crypto
from .schema import COLLECTIONS, ID_RE

MAX_DOC_BYTES = 1_000_000
SHA_LEN = 64


def _tup(m: Dict[str, Any]) -> Tuple[int, float, str]:
    return (int(m.get("rev") or 0), float(m.get("ts") or 0), str(m.get("origin") or ""))


def is_sha(s: Any) -> bool:
    return isinstance(s, str) and len(s) == SHA_LEN and all(c in "0123456789abcdef" for c in s)


class OrgStore:
    def __init__(self, root: Path, machine_id: str):
        self.root = Path(root)
        self.machine_id = machine_id
        self.lock = threading.RLock()
        self.docs_dir = self.root / "docs"
        self.blobs_dir = self.root / "blobs"
        self.vault_dir = self.root / "vault"
        for d in (self.docs_dir, self.blobs_dir / ".tmp", self.vault_dir):
            d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.vault_dir, 0o700)
        except OSError:
            pass
        self.cache: Dict[str, Dict[str, Dict[str, Any]]] = {c: {} for c in COLLECTIONS}
        self.listeners: List[Callable[[str, Dict[str, Any], str], None]] = []
        self._digest: Optional[str] = None
        self.version = 0
        self._load()

    # ------------------------------------------------------------------ identidade e segredo
    @property
    def id(self) -> str:
        return self.root.name

    def secret(self) -> str:
        s = (read_json(self.root / "secret.json", {}) or {}).get("secret", "")
        return s if isinstance(s, str) and len(s) == 64 else ""

    def set_secret(self, secret: str) -> None:
        write_json(self.root / "secret.json", {"secret": secret}, private=True)

    def local(self) -> Dict[str, Any]:
        d = read_json(self.root / "local.json", {})
        return d if isinstance(d, dict) else {}

    def save_local(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            d = self.local()
            d.update(patch)
            write_json(self.root / "local.json", d)
            return d

    # ------------------------------------------------------------------ documentos
    def _load(self) -> None:
        for coll in COLLECTIONS:
            d = self.docs_dir / coll
            if not d.is_dir():
                continue
            for f in d.glob("*.json"):
                doc = read_json(f)
                if isinstance(doc, dict) and doc.get("id") == f.stem and isinstance(doc.get("_m"), dict):
                    self.cache[coll][f.stem] = doc

    def _write(self, coll: str, doc: Dict[str, Any]) -> None:
        write_json(self.docs_dir / coll / (doc["id"] + ".json"), doc)
        self.cache[coll][doc["id"]] = doc
        self._digest = None
        self.version += 1

    def get(self, coll: str, did: str) -> Optional[Dict[str, Any]]:
        doc = self.cache.get(coll, {}).get(did)
        return doc if doc and not doc["_m"].get("deleted") else None

    def raw(self, coll: str, did: str) -> Optional[Dict[str, Any]]:
        return self.cache.get(coll, {}).get(did)

    def all(self, coll: str) -> List[Dict[str, Any]]:
        return [d for d in list(self.cache.get(coll, {}).values()) if not d["_m"].get("deleted")]

    def map(self, coll: str) -> Dict[str, Dict[str, Any]]:
        return {d["id"]: d for d in self.all(coll)}

    def put(self, coll: str, did: str, fields: Dict[str, Any], by: str = "") -> Dict[str, Any]:
        """Grava (cria ou substitui os campos de) um documento daqui. Devolve o documento gravado."""
        if coll not in self.cache or not ID_RE.match(str(did)):
            raise ValueError("coleção ou id inválido")
        with self.lock:
            old = self.cache[coll].get(did)
            rev = int((old or {}).get("_m", {}).get("rev") or 0) + 1
            doc = {k: v for k, v in fields.items() if k not in ("_m", "id")}
            doc["id"] = did
            doc["_m"] = {"rev": rev, "ts": round(time.time(), 3), "by": by, "origin": self.machine_id, "deleted": False}
            if len(json.dumps(doc, ensure_ascii=False)) > MAX_DOC_BYTES:
                raise ValueError("documento grande demais")
            self._write(coll, doc)
        self._emit(coll, doc, "local")
        return doc

    def remove(self, coll: str, did: str, by: str = "") -> bool:
        with self.lock:
            old = self.cache.get(coll, {}).get(did)
            if not old or old["_m"].get("deleted"):
                return False
            doc = {"id": did, "_m": {"rev": int(old["_m"].get("rev") or 0) + 1, "ts": round(time.time(), 3), "by": by, "origin": self.machine_id, "deleted": True}}
            self._write(coll, doc)
        self._emit(coll, doc, "local")
        return True

    def merge(self, coll: str, doc: Any) -> bool:
        """Aceita um documento vindo de outra máquina se for mais novo que o daqui. Entrada não confiável: tudo é validado."""
        if coll not in self.cache or not isinstance(doc, dict) or not ID_RE.match(str(doc.get("id", ""))):
            return False
        m = doc.get("_m")
        if not isinstance(m, dict) or not isinstance(m.get("rev"), int) or isinstance(m.get("rev"), bool):
            return False
        try:
            if len(json.dumps(doc, ensure_ascii=False)) > MAX_DOC_BYTES or not isinstance(m.get("ts"), (int, float)):
                return False
        except (TypeError, ValueError):
            return False
        clean = {k: v for k, v in doc.items() if k != "_m"}
        clean["_m"] = {"rev": int(m["rev"]), "ts": float(m["ts"]), "by": str(m.get("by") or "")[:80], "origin": str(m.get("origin") or "")[:80], "deleted": bool(m.get("deleted"))}
        with self.lock:
            old = self.cache[coll].get(clean["id"])
            if old and _tup(old["_m"]) >= _tup(clean["_m"]):
                return False
            self._write(coll, clean)
        self._emit(coll, clean, "sync")
        return True

    def _emit(self, coll: str, doc: Dict[str, Any], source: str) -> None:
        for fn in list(self.listeners):
            try:
                fn(coll, doc, source)
            except Exception:  # noqa: BLE001  (um ouvinte com defeito nunca derruba a gravação)
                pass

    def manifest(self, colls: Optional[List[str]] = None) -> Dict[str, List[Any]]:
        out: Dict[str, List[Any]] = {}
        for coll in colls or COLLECTIONS:
            for did, d in list(self.cache[coll].items()):
                m = d["_m"]
                out[f"{coll}/{did}"] = [int(m.get("rev") or 0), float(m.get("ts") or 0), str(m.get("origin") or "")]
        return out

    def digest(self) -> str:
        if self._digest is None:
            h = hashlib.sha256()
            for k, v in sorted(self.manifest().items()):
                h.update(f"{k}:{v[0]}:{v[1]}:{v[2]}\n".encode())
            self._digest = h.hexdigest()
        return self._digest

    def doc_dump(self, key: str) -> Optional[Dict[str, Any]]:
        coll, _, did = key.partition("/")
        return self.cache.get(coll, {}).get(did)

    # ------------------------------------------------------------------ blobs (arquivos de qualquer formato)
    def blob_path(self, sha: str) -> Path:
        if not is_sha(sha):
            raise ValueError("hash inválido")
        return self.blobs_dir / sha[:2] / sha

    def has_blob(self, sha: str) -> bool:
        try:
            return self.blob_path(sha).is_file()
        except ValueError:
            return False

    def blob_size(self, sha: str) -> int:
        try:
            return self.blob_path(sha).stat().st_size
        except (OSError, ValueError):
            return -1

    def add_blob(self, stream: BinaryIO, length: int, *, limit: int = 0, chunk: int = 1 << 20) -> Tuple[str, int]:
        """Grava o corpo lido de `stream` (até `length` bytes) e devolve (sha256, tamanho). Passou do `limit` → ValueError e nada fica no disco."""
        tmp = self.blobs_dir / ".tmp" / f"up-{threading.get_ident()}-{time.time_ns()}"
        h, n, left = hashlib.sha256(), 0, length
        try:
            with open(tmp, "wb") as fh:
                while left > 0:
                    data = stream.read(min(chunk, left))
                    if not data:
                        break
                    n += len(data)
                    if limit and n > limit:
                        raise ValueError("arquivo maior que o limite")
                    h.update(data)
                    fh.write(data)
                    left -= len(data)
            return self._adopt(tmp, h.hexdigest()), n
        finally:
            tmp.unlink(missing_ok=True)

    def add_blob_file(self, path: Path) -> Tuple[str, int]:
        with open(path, "rb") as fh:
            return self.add_blob(fh, os.path.getsize(path))

    def _adopt(self, tmp: Path, sha: str) -> str:
        dest = self.blob_path(sha)
        if dest.is_file():
            return sha
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, dest)
        return sha

    # recebimento por pedaços (sincronização): cada pedaço chega no seu deslocamento; o hash é conferido ao final
    def incoming_path(self, sha: str) -> Path:
        if not is_sha(sha):
            raise ValueError("hash inválido")
        return self.blobs_dir / ".tmp" / (sha + ".part")

    def incoming_write(self, sha: str, offset: int, data: bytes) -> int:
        p = self.incoming_path(sha)
        with self.lock:
            if offset == 0:
                p.unlink(missing_ok=True)   # recomeço: descarta restos de uma tentativa anterior
            size = p.stat().st_size if p.exists() else 0
            if offset != size:
                raise ValueError(f"deslocamento inesperado (tenho {size})")
            with open(p, "ab") as fh:
                fh.write(data)
            return size + len(data)

    def incoming_commit(self, sha: str) -> bool:
        p = self.incoming_path(sha)
        with self.lock:
            if not p.is_file():
                return False
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    h.update(block)
            if h.hexdigest() != sha:
                p.unlink(missing_ok=True)
                return False
            self._adopt(p, sha)
            p.unlink(missing_ok=True)
            return True

    def blob_chunks(self, sha: str, start: int = 0, size: int = 4 << 20) -> bytes:
        with open(self.blob_path(sha), "rb") as fh:
            fh.seek(start)
            return fh.read(size)

    def iter_blobs(self) -> Iterator[str]:
        for d in self.blobs_dir.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                for f in d.iterdir():
                    if is_sha(f.name):
                        yield f.name

    def remove_blob(self, sha: str) -> None:
        try:
            self.blob_path(sha).unlink(missing_ok=True)
        except ValueError:
            pass

    # ------------------------------------------------------------------ cofre de senhas (só hash PBKDF2)
    def _vault(self, uid: str) -> Optional[Path]:
        return self.vault_dir / (uid + ".json") if ID_RE.match(uid or "") else None

    def vault_get(self, uid: str) -> Optional[Dict[str, Any]]:
        p = self._vault(uid)
        d = read_json(p) if p else None
        return d if isinstance(d, dict) else None

    def vault_set(self, uid: str, rec: Dict[str, Any]) -> None:
        p = self._vault(uid)
        if p:
            write_json(p, rec, private=True)

    def vault_del(self, uid: str) -> None:
        p = self._vault(uid)
        if p:
            p.unlink(missing_ok=True)

    # ------------------------------------------------------------------ convites (local; a chave de uso único fica em arquivo 0600 e vale por tempo limitado)
    @staticmethod
    def invite_id(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def invites(self) -> Dict[str, Any]:
        d = read_json(self.root / "invites.json", {})
        now = time.time()
        return {k: v for k, v in (d if isinstance(d, dict) else {}).items() if isinstance(v, dict) and v.get("exp", 0) > now}

    def add_invite(self, key: str, ttl: int, by: str) -> float:
        with self.lock:
            inv = self.invites()
            exp = time.time() + ttl
            inv[self.invite_id(key)] = {"key": key, "exp": exp, "by": by}
            write_json(self.root / "invites.json", inv, private=True)
            return exp

    def invite_key(self, iid: str) -> str:
        v = self.invites().get(str(iid))
        return v["key"] if v and isinstance(v.get("key"), str) else ""

    def burn_invite(self, iid: str) -> None:
        with self.lock:
            inv = self.invites()
            if inv.pop(str(iid), None) is not None:
                write_json(self.root / "invites.json", inv, private=True)

    # ------------------------------------------------------------------ backup (cópia dos documentos)
    def snapshot(self, keep: int = 14) -> Path:
        import zipfile

        d = self.root / "snapshots"
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        path = d / f"{stamp}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for coll in COLLECTIONS:
                for did, doc in list(self.cache[coll].items()):
                    z.writestr(f"docs/{coll}/{did}.json", json.dumps(doc, ensure_ascii=False))
        for old in sorted(d.glob("*.zip"))[:-max(1, keep)]:
            old.unlink(missing_ok=True)
        return path

    def snapshots(self) -> List[Dict[str, Any]]:
        d = self.root / "snapshots"
        return [{"name": p.name, "size": p.stat().st_size, "ts": p.stat().st_mtime} for p in sorted(d.glob("*.zip"), reverse=True)] if d.is_dir() else []

    def destroy(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def secret_ok(secret: str) -> bool:
    return isinstance(secret, str) and len(secret) == 64 and all(c in "0123456789abcdef" for c in secret) and bool(crypto.sign(secret, "x"))
