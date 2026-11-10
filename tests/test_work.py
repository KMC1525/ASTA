"""Work (v0.18): permissões, senhas, store com «mais novo vence», sincronização entre máquinas (HTTP cifrado e pasta de nuvem), backups, pedidos, atividades,
notificações, IA com fallback e a API HTTP. Tudo local (portas em 127.0.0.1); nada de rede externa."""
import io
import json
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.server import make_server  # noqa: E402
from asta.storage import Store  # noqa: E402
from asta.work import WorkError, WorkManager, agents as wai, board, crypto, normalize_config, perms as P, schema as S, tailscale  # noqa: E402
from asta.work.store import OrgStore  # noqa: E402
from asta.work.sync import FolderPool, HttpPeer, PeerError, make_invite, parse_invite  # noqa: E402
from tests.helpers import Client  # noqa: E402


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class FakeProvider:
    """Responde JSON conforme o papel que aparece no prompt de sistema (o Work usa «ROLE: …»)."""
    id, model, vision = "fake", "fake-1", False

    def __init__(self, replies=None, fail=False):
        self.replies, self.fail, self.calls = replies or {}, fail, []

    def chat(self, messages, system="", **kw):
        self.calls.append(system)
        if self.fail:
            return "isto não é json"
        for role, reply in self.replies.items():
            if f"ROLE: {role}" in system:
                return json.dumps(reply(system) if callable(reply) else reply)
        return "{}"


class Box:
    """Uma «máquina» do Work: pasta de dados própria + gerenciador. `listen=True` abre o servidor de sincronização em 127.0.0.1."""
    def __init__(self, name: str, listen: bool = True, **cfg):
        self.tmp = Path(tempfile.mkdtemp(prefix="asta-work-"))
        self.store = Store(self.tmp)
        self.port = free_port()
        self.store.save_settings({"work": {"peer": {"listen": "127.0.0.1" if listen else "off", "port": self.port}, "auto_sync": False, **cfg}})
        self.m = WorkManager(self.store)
        self.m.rename_machine(name)

    def close(self):
        self.m.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class WorkCase(unittest.TestCase):
    def setUp(self):
        self.boxes = []

    def tearDown(self):
        for b in self.boxes:
            b.close()

    def box(self, name="PC", **kw) -> Box:
        b = Box(name, **kw)
        self.boxes.append(b)
        return b

    def org(self, box: Box, password: str = "", mode: str = "synced"):
        st, _ = box.m.create_org("Acme", {"username": "ana", "display_name": "Ana", "password": password, "auth_mode": mode}, box.m.ident["name"])
        token, ctx = box.m.login(st.id, "ana", password)
        return st, token, ctx

    def pair(self):
        a, b = self.box("PC-A"), self.box("PC-B")
        st, token, ctx = self.org(a, "segredo1")
        inv = a.m.create_invite(ctx)
        stb = b.m.join(inv["code"], "PC-B")
        return a, b, st, stb, ctx

    def sync(self, *boxes_and_orgs):
        for box, st in boxes_and_orgs:
            box.m.sync.run_org(st.id)


class CryptoAndPermsTests(unittest.TestCase):
    def test_password_hash_and_seal(self):
        rec = crypto.hash_password("senha-forte")
        self.assertTrue(crypto.verify_password("senha-forte", rec))
        self.assertFalse(crypto.verify_password("errada", rec))
        self.assertFalse(crypto.verify_password("x", {"alg": "x"}))
        self.assertIn("pelo menos", crypto.check_password_strength("123"))
        self.assertEqual(crypto.check_password_strength("123456"), "")
        key = crypto.new_secret()
        data = os.urandom(5000)
        blob = crypto.seal(key, data, b"aad")
        self.assertNotIn(data[:40], blob)
        self.assertEqual(crypto.unseal(key, blob, b"aad"), data)
        for bad in (lambda: crypto.unseal(key, blob, b"outro"), lambda: crypto.unseal(crypto.new_secret(), blob, b"aad"),
                    lambda: crypto.unseal(key, blob[:-1] + bytes([blob[-1] ^ 1]), b"aad"), lambda: crypto.unseal(key, blob[:10], b"aad")):
            with self.assertRaises(ValueError):
                bad()
        self.assertEqual(crypto.unseal(key, crypto.seal(key, b""), b""), b"")

    def test_effective_permissions_role_function_and_person(self):
        roles = {r["id"]: {**r} for r in P.BUILTIN_ROLES}
        fns = {"fin": {"id": "fin", "grant": ["files.delete"], "deny": ["ai.use"]}}
        worker = {"id": "u1", "role_id": "worker", "function_ids": ["fin"], "grant": ["flow.edit"], "deny": ["files.upload"]}
        perms = P.effective(worker, roles, fns)
        self.assertIn("files.delete", perms)       # concedida pela função
        self.assertNotIn("ai.use", perms)          # negada pela função
        self.assertIn("flow.edit", perms)          # concedida à pessoa
        self.assertNotIn("files.upload", perms)    # negada à pessoa
        self.assertIn("*", P.effective({"id": "a", "role_id": "admin"}, roles, fns))
        self.assertEqual(P.effective({"id": "a", "role_id": "admin", "disabled": True}, roles, fns), set())
        self.assertEqual(P.clean_perms(["files.view", "inventada", "*", 3]), ["files.view", "*"])

    def test_invite_code_roundtrip_and_garbage(self):
        key = crypto.new_secret()
        code = make_invite("org_1", "Acme", key, ["100.64.0.1:8790"])
        self.assertEqual(parse_invite(code), {"org": "org_1", "name": "Acme", "key": key, "addrs": ["100.64.0.1:8790"]})
        for bad in ("", "xyz", "AW1.", "AW1.!!!", "AW1." + "e30"):
            with self.assertRaises(ValueError):
                parse_invite(bad)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.a, self.b = OrgStore(self.tmp / "a", "m_a"), OrgStore(self.tmp / "b", "m_b")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_newest_edit_wins_and_deletes_travel(self):
        d1 = self.a.put("folders", "f1", {"name": "Um"}, "u")
        self.assertTrue(self.b.merge("folders", d1))
        self.assertFalse(self.b.merge("folders", d1))                                   # mesmo documento: nada muda
        d2 = self.a.put("folders", "f1", {"name": "Dois"}, "u")
        e = self.b.put("folders", "f1", {"name": "Editado em B"}, "u")                  # rev 2 também: empate resolvido por relógio/máquina
        self.assertEqual(e["_m"]["rev"], d2["_m"]["rev"])
        self.b.merge("folders", d2)
        self.a.merge("folders", e)
        self.assertEqual(self.a.get("folders", "f1")["name"], self.b.get("folders", "f1")["name"])   # os dois convergem
        self.a.remove("folders", "f1", "u")
        self.b.merge("folders", self.a.raw("folders", "f1"))
        self.assertIsNone(self.b.get("folders", "f1"))
        self.assertEqual(self.a.digest(), self.b.digest())

    def test_merge_rejects_hostile_documents(self):
        for coll, doc in (("folders", "texto"), ("folders", {"id": "../x", "_m": {"rev": 1, "ts": 1}}), ("folders", {"id": "ok"}), ("nada", {"id": "ok", "_m": {"rev": 1, "ts": 1}}),
                          ("folders", {"id": "ok", "_m": {"rev": "1", "ts": 1}}), ("folders", {"id": "ok", "_m": {"rev": True, "ts": 1}}), ("folders", {"id": "ok", "_m": {"rev": 1, "ts": "x"}}),
                          ("folders", {"id": "ok", "big": "x" * 1_100_000, "_m": {"rev": 1, "ts": 1}})):
            self.assertFalse(self.a.merge(coll, doc), (coll, str(doc)[:40]))
        with self.assertRaises(ValueError):
            self.a.put("folders", "../escape", {}, "u")

    def test_blobs_are_content_addressed_limited_and_verified(self):
        data = os.urandom(3000)
        sha, n = self.a.add_blob(io.BytesIO(data), len(data))
        self.assertEqual((n, self.a.has_blob(sha)), (3000, True))
        self.assertEqual(self.a.add_blob(io.BytesIO(data), len(data))[0], sha)          # mesmo conteúdo: um só arquivo
        with self.assertRaises(ValueError):
            self.a.add_blob(io.BytesIO(data), len(data), limit=100)
        self.assertEqual(list((self.a.blobs_dir / ".tmp").iterdir()), [])               # nada sobra no disco
        self.b.incoming_write(sha, 0, data[:1000])
        self.b.incoming_write(sha, 1000, data[1000:])
        self.assertTrue(self.b.incoming_commit(sha))
        self.b.incoming_write("0" * 64, 0, b"lixo")
        self.assertFalse(self.b.incoming_commit("0" * 64))                              # hash não confere → descartado
        with self.assertRaises(ValueError):
            self.b.blob_path("../../etc/passwd")

    def test_secret_and_vault_files_are_private(self):
        self.a.set_secret(crypto.new_secret())
        self.a.vault_set("u1", crypto.hash_password("abcdef"))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE((self.a.root / "secret.json").stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE((self.a.vault_dir / "u1.json").stat().st_mode), 0o600)


class OrgAndAuthTests(WorkCase):
    def test_create_org_gives_roles_admin_and_first_machine(self):
        box = self.box(listen=False)
        st, token, ctx = self.org(box)
        self.assertEqual(sorted(r["id"] for r in st.all("roles")), ["admin", "manager", "worker"])
        self.assertIn("*", ctx.perms)
        self.assertEqual([m["name"] for m in st.all("machines")], ["PC"])
        self.assertTrue(len(st.secret()) == 64)
        with self.assertRaises(WorkError):
            box.m.create_org("", {"username": "x1"})
        with self.assertRaises(WorkError):
            box.m.create_org("Z", {"username": "A B"})

    def test_password_modes(self):
        box = self.box(listen=False)
        st, token, ctx = self.org(box)
        ana = ctx.user
        self.assertEqual(box.m.login(st.id, "ana", "")[1].uid, ana["id"])               # sem senha: entra
        for mode in ("local", "synced"):
            box.m.set_password(ctx, ana["id"], "senha-" + mode, mode)
            for pw in ("", "errada"):
                with self.assertRaises(WorkError) as cm:
                    box.m.login(st.id, "ana", pw)
                self.assertEqual(cm.exception.status, 401)
            box.m.login(st.id, "ana", "senha-" + mode)
        self.assertIsNotNone(st.get("users", ana["id"]).get("pw"))                      # «synced» replica o hash no documento
        box.m.set_password(ctx, ana["id"], "senha-local", "local")
        self.assertIsNone(st.get("users", ana["id"]).get("pw"))                         # trocar de lugar apaga o hash do lugar antigo
        self.assertIsNotNone(st.vault_get(ana["id"]))
        with self.assertRaises(WorkError):
            box.m.set_password(ctx, ana["id"], "123", "local")
        box.m.set_password(ctx, ana["id"], "", "none")
        self.assertIsNone(st.vault_get(ana["id"]))
        box.m.login(st.id, "ana", "")

    def test_login_is_throttled_after_repeated_failures(self):
        box = self.box(listen=False)
        st, token, ctx = self.org(box, "segredo1")
        for _ in range(5):
            with self.assertRaises(WorkError):
                box.m.login(st.id, "ana", "x")
        with self.assertRaises(WorkError) as cm:
            box.m.login(st.id, "ana", "segredo1")
        self.assertEqual(cm.exception.status, 429)

    def test_roles_levels_and_the_last_admin(self):
        box = self.box(listen=False)
        st, token, ctx = self.org(box)
        mgr = box.m
        boss = mgr.create_user(ctx, {"username": "chefe", "display_name": "Chefe", "role_id": "manager"})
        w = mgr.create_user(ctx, {"username": "joao", "display_name": "João", "role_id": "worker"})
        with self.assertRaises(WorkError):
            mgr.create_user(ctx, {"username": "joao"})                                   # nome repetido
        _, boss_ctx = mgr.login(st.id, "chefe")[0], mgr.login(st.id, "chefe")[1]
        with self.assertRaises(WorkError):
            mgr.create_user(boss_ctx, {"username": "x1", "role_id": "worker"})            # gerente não tem users.manage
        mgr.save_role(ctx, "", {"name": "RH", "level": 40, "perms": ["users.manage", "files.view"]})
        rh = [r for r in st.all("roles") if r["name"] == "RH"][0]
        mgr.update_user(ctx, boss["id"], {"role_id": rh["id"]})
        _, boss_ctx = mgr.login(st.id, "chefe")
        self.assertTrue(boss_ctx.has("users.manage"))
        with self.assertRaises(WorkError):
            mgr.update_user(boss_ctx, w["id"], {"role_id": "admin"})                     # não pode dar um cargo acima do seu
        with self.assertRaises(WorkError):
            mgr.save_role(boss_ctx, "", {"name": "X", "perms": ["*"]})
        with self.assertRaises(WorkError):
            mgr.update_user(ctx, ctx.uid, {"disabled": True})                             # último administrador
        with self.assertRaises(WorkError):
            mgr.delete_role(ctx, "admin")
        with self.assertRaises(WorkError):
            mgr.delete_role(ctx, rh["id"])                                                # ainda tem gente com o cargo
        # o trabalhador edita só o próprio perfil
        _, wctx = mgr.login(st.id, "joao")
        out = mgr.update_user(wctx, w["id"], {"bio": "Oi", "role_id": "admin", "grant": ["*"]})
        self.assertEqual((out["bio"], out["role_id"]), ("Oi", "worker"))
        with self.assertRaises(WorkError):
            mgr.update_user(wctx, boss["id"], {"bio": "x"})
        self.assertEqual(st.get("users", w["id"])["grant"], [])

    def test_function_permissions_apply_to_the_person(self):
        box = self.box(listen=False)
        st, token, ctx = self.org(box)
        fn = box.m.save_function(ctx, "", {"name": "Financeiro", "grant": ["files.delete", "requests.send"]})
        u = box.m.create_user(ctx, {"username": "fin", "role_id": "worker", "function_ids": [fn["id"]]})
        _, fctx = box.m.login(st.id, "fin")
        self.assertTrue(fctx.has("requests.send"))
        box.m.delete_function(ctx, fn["id"])
        _, fctx = box.m.login(st.id, "fin")
        self.assertFalse(fctx.has("requests.send"))


class SyncTests(WorkCase):
    def test_join_by_invite_is_single_use_and_secret_never_in_synced_docs(self):
        a, b, st, stb, ctx = self.pair()
        self.assertEqual(stb.secret(), st.secret())
        self.assertEqual(sorted(m["name"] for m in stb.all("machines")), ["PC-A", "PC-B"])
        code = a.m.create_invite(ctx)["code"]
        c = self.box("PC-C")
        c.m.join(code, "PC-C")
        d = self.box("PC-D")
        with self.assertRaises(WorkError):
            d.m.join(code, "PC-D")                                                       # convite de uso único
        with self.assertRaises(WorkError):
            d.m.join("AW1.lixo", "x")
        for p in (st.docs_dir).rglob("*.json"):
            self.assertNotIn(st.secret(), p.read_text())

    def test_documents_and_files_flow_both_ways(self):
        a, b, st, stb, ctx = self.pair()
        folder = a.m.save_folder(ctx, "", {"name": "Financeiro"})
        data = os.urandom(300_000)
        a.m.upload_file(ctx, "balanco.bin", io.BytesIO(data), len(data), folder["id"])
        self.sync((a, st), (b, stb))
        _, bctx = b.m.login(stb.id, "ana", "segredo1")                                   # a senha «synced» chegou com o usuário
        files = b.m.list_files(bctx, folder["id"])
        self.assertEqual([f["name"] for f in files], ["balanco.bin"])
        self.assertFalse(files[0]["local"])                                              # B ainda não tem o conteúdo (só quem precisa)
        path, name, _ = b.m.open_file(bctx, files[0]["id"])                              # buscado sob demanda no A
        self.assertEqual(path.read_bytes(), data)
        # B cria algo e o A recebe
        b.m.save_folder(bctx, "", {"name": "Criado em B"})
        self.sync((b, stb), (a, st))
        self.assertIn("Criado em B", [f["name"] for f in a.m.folders(ctx)])

    def test_hold_all_machine_gets_every_file_automatically_and_backup_choice_replicates(self):
        a, b, st, stb, ctx = self.pair()
        _, bctx = b.m.login(stb.id, "ana", "segredo1") if False else (None, None)
        self.sync((a, st), (b, stb))
        # B vira «guarda tudo» + backup
        a.m.update_machine(ctx, b.m.machine_id, {"hold": "all", "backup": True})
        data = b"conteudo importante" * 5000
        a.m.upload_file(ctx, "p.txt", io.BytesIO(data), len(data))                       # arquivo pessoal (sem setor)
        self.sync((a, st), (b, stb))
        sha = st.get("files", [f for f in st.all("files")][0]["id"])["versions"][-1]["sha"]
        self.assertTrue(stb.has_blob(sha))                                               # B guarda tudo → recebeu sem ninguém pedir
        status = a.m.backup_status(ctx)
        self.assertEqual([t["name"] for t in status["targets"]], ["PC-B"])
        ver = a.m.verify_backup(ctx, b.m.machine_id)
        self.assertEqual((ver["expected"], ver["present"], ver["missing"]), (1, 1, []))
        # a pessoa escolhe B como backup; um arquivo novo vai para lá mesmo com B em «needed»
        a.m.update_machine(ctx, b.m.machine_id, {"hold": "needed"})
        a.m.update_user(ctx, ctx.uid, {"backup_machines": [b.m.machine_id]})
        a.m.upload_file(ctx, "q.txt", io.BytesIO(b"abc" * 100), 300)
        self.sync((a, st), (b, stb))
        sha_q = [f for f in st.all("files") if f["name"] == "q.txt"][0]["versions"][-1]["sha"]
        self.assertTrue(stb.has_blob(sha_q))
        # restaurar: A perde o conteúdo e recupera de B
        st.remove_blob(sha_q)
        self.assertFalse(st.has_blob(sha_q))
        res = a.m.restore_from(ctx, b.m.machine_id)
        self.assertEqual((res["restored"], res["failed"]), (1, 0))
        self.assertTrue(st.has_blob(sha_q))

    def test_machine_that_does_not_listen_syncs_by_initiative(self):
        a = self.box("PC-A")
        b = self.box("PC-B", listen=False)
        st, token, ctx = self.org(a, "segredo1")
        stb = b.m.join(a.m.create_invite(ctx)["code"], "PC-B")
        a.m.save_folder(ctx, "", {"name": "Novo"})
        self.sync((b, stb))
        _, bctx = b.m.login(stb.id, "ana", "segredo1")
        self.assertIn("Novo", [f["name"] for f in b.m.folders(bctx)])
        b.m.save_folder(bctx, "", {"name": "De B"})
        self.sync((b, stb))                                                              # B empurra por conta própria
        self.assertIn("De B", [f["name"] for f in a.m.folders(ctx)])

    def test_peer_protocol_rejects_strangers_replays_and_revoked_machines(self):
        a, b, st, stb, ctx = self.pair()
        addr = f"127.0.0.1:{a.port}"
        with self.assertRaises(PeerError) as cm:
            HttpPeer(st.id, crypto.new_secret(), b.m.machine_id, addr).call("hello")      # chave de outra rede
        self.assertEqual(cm.exception.status, 401)
        good = HttpPeer(st.id, st.secret(), b.m.machine_id, addr)
        self.assertEqual(good.call("hello")["machine"], a.m.machine_id)
        with self.assertRaises(PeerError) as cm:
            HttpPeer(st.id, st.secret(), "m_intruso", addr).call("hello")                 # chave certa, máquina que não está na rede
        self.assertEqual(cm.exception.status, 403)
        with self.assertRaises(PeerError):
            HttpPeer("org_inexistente", st.secret(), b.m.machine_id, addr).call("hello")
        # repetir exatamente o mesmo pedido é recusado
        import http.client
        import hashlib
        nonce, ts = "n-" + crypto.token(6), str(int(time.time()))
        sealed = crypto.seal(st.secret(), b"{}", (nonce + "|req").encode())
        path = f"/peer/v1/{st.id}/hello"
        sig = crypto.sign(st.secret(), "POST", path, ts, nonce, hashlib.sha256(sealed).hexdigest())
        codes = []
        for _ in range(2):
            c = http.client.HTTPConnection("127.0.0.1", a.port, timeout=5)
            c.request("POST", path, body=sealed, headers={"X-Work-M": b.m.machine_id, "X-Work-T": ts, "X-Work-N": nonce, "X-Work-S": sig, "Content-Length": str(len(sealed))})
            r = c.getresponse()
            r.read()
            codes.append(r.status)
            c.close()
        self.assertEqual(codes, [200, 401])
        # revogada: nada mais passa
        a.m.update_machine(ctx, b.m.machine_id, {"revoked": True})
        with self.assertRaises(PeerError) as cm:
            good.call("hello")
        self.assertEqual(cm.exception.status, 403)

    def test_peer_server_serves_nothing_but_the_peer_protocol(self):
        a = self.box("PC-A")
        self.org(a)
        import http.client
        for path in ("/", "/api/state", "/api/work/status", "/peer/v1", "/peer/v1/x/y/z"):
            c = http.client.HTTPConnection("127.0.0.1", a.port, timeout=5)
            c.request("GET", path)
            r = c.getresponse()
            body = r.read()
            c.close()
            self.assertEqual(r.status, 404, path)
            self.assertNotIn(b"ASTA", body.replace(b"ASTA-Work", b""))

    def test_machine_held_password_is_verified_remotely(self):
        a, b, st, stb, ctx = self.pair()
        self.sync((a, st), (b, stb))
        bia = a.m.create_user(ctx, {"username": "bia", "role_id": "worker"})
        a.m.set_password(ctx, bia["id"], "so-na-maquina-b", "machine", b.m.machine_id)
        self.assertIsNone(st.vault_get(bia["id"]))                                       # o hash não ficou no A…
        self.assertIsNotNone(stb.vault_get(bia["id"]))                                   # …está no B
        self.sync((a, st), (b, stb))
        self.assertEqual(a.m.login(st.id, "bia", "so-na-maquina-b")[1].uid, bia["id"])   # A confere perguntando ao B
        with self.assertRaises(WorkError):
            a.m.login(st.id, "bia", "errada")
        b.m.stop()                                                                       # B cai
        with self.assertRaises(WorkError) as cm:
            a.m.login(st.id, "bia", "so-na-maquina-b")
        self.assertEqual(cm.exception.status, 503)

    def test_local_password_does_not_work_on_other_machines(self):
        a, b, st, stb, ctx = self.pair()
        bia = a.m.create_user(ctx, {"username": "bia", "role_id": "worker"})
        a.m.set_password(ctx, bia["id"], "senha-local", "local")
        self.sync((a, st), (b, stb))
        with self.assertRaises(WorkError) as cm:
            b.m.login(stb.id, "bia", "senha-local")
        self.assertEqual(cm.exception.status, 409)
        self.assertIn("só vale na máquina", cm.exception.message)

    def test_cloud_folder_transport_is_encrypted_and_carries_files(self):
        a, b, st, stb, ctx = self.pair()
        self.sync((a, st), (b, stb))
        a.m.update_machine(ctx, b.m.machine_id, {"hold": "all"})
        pool = Path(tempfile.mkdtemp(prefix="asta-pool-"))
        self.addCleanup(shutil.rmtree, pool, True)
        folder = a.m.save_folder(ctx, "", {"name": "Nuvem"})
        data = b"segredo da empresa " * 20000
        a.m.upload_file(ctx, "plano.txt", io.BytesIO(data), len(data), folder["id"])
        FolderPool(st, str(pool), a.m.machine_id).sync()
        raw = b"".join(p.read_bytes() for p in pool.rglob("*") if p.is_file())
        self.assertNotIn(b"segredo da empresa", raw)
        self.assertNotIn(b"Financeiro", raw)
        self.assertNotIn(b"plano.txt", raw)                                              # nem o nome do arquivo nem o hash vazam
        rep = FolderPool(stb, str(pool), b.m.machine_id).sync()
        self.assertGreaterEqual(rep["docs_in"], 1)
        fid = [f for f in stb.all("files")][0]
        self.assertEqual(stb.blob_path(fid["versions"][-1]["sha"]).read_bytes(), data)
        other = OrgStore(Path(tempfile.mkdtemp()) / st.id, "m_x")
        other.set_secret(crypto.new_secret())
        self.assertEqual(FolderPool(other, str(pool), "m_x").sync()["docs_in"], 0)       # com outra chave nada é lido
        shutil.rmtree(other.root.parent, ignore_errors=True)

    def test_background_sync_service_converges_on_its_own(self):
        a, b, st, stb, ctx = self.pair()
        b.m.sync.interval = 0.3
        b.m.config = lambda: {**normalize_config({}), "auto_sync": True}                 # type: ignore[method-assign]
        b.m.sync.start()
        a.m.save_folder(ctx, "", {"name": "Automático"})
        for _ in range(60):
            if "Automático" in [f["name"] for f in stb.all("folders")]:
                break
            time.sleep(0.2)
        self.assertIn("Automático", [f["name"] for f in stb.all("folders")])


class WorkflowTests(WorkCase):
    def setUp(self):
        super().setUp()
        self.box_ = self.box(listen=False)
        self.st, self.token, self.ctx = self.org(self.box_)
        self.m = self.box_.m
        self.w = self.m.create_user(self.ctx, {"username": "joao", "display_name": "João", "role_id": "worker"})
        self.mg = self.m.create_user(self.ctx, {"username": "maria", "display_name": "Maria", "role_id": "manager"})
        self.wctx = self.m.login(self.st.id, "joao")[1]
        self.mctx = self.m.login(self.st.id, "maria")[1]

    def test_request_text_files_or_both_and_its_lifecycle(self):
        with self.assertRaises(WorkError):
            self.m.send_request(self.wctx, {"to": [self.mg["id"]], "body": "oi"})          # trabalhador não tem requests.send
        with self.assertRaises(WorkError):
            self.m.send_request(self.mctx, {"to": [self.w["id"]]})                          # sem texto nem arquivo
        with self.assertRaises(WorkError):
            self.m.send_request(self.mctx, {"body": "oi"})                                  # sem destinatário
        only_text = self.m.send_request(self.mctx, {"to": [self.w["id"]], "body": "Fazer o relatório. Urgente!", "priority": "urgent"})
        self.assertEqual(only_text["title"], "Fazer o relatório")
        fid = self.m.upload_file(self.mctx, "briefing.pdf", io.BytesIO(b"%PDF-1.4 x"), 10)["id"]
        both = self.m.send_request(self.mctx, {"to": [self.w["id"]], "body": "Veja o anexo", "attachments": [fid]})
        only_file = self.m.send_request(self.mctx, {"to": [self.w["id"]], "attachments": [fid]})
        self.assertEqual(only_file["title"], "Arquivos enviados")
        self.assertIn(fid, both["files"])
        self.assertEqual(self.m.list_notifications(self.wctx)["unread"], 4)                  # bem-vindo + 3 pedidos
        self.assertTrue(self.m.list_requests(self.wctx, "in")[0]["unread"])
        got = self.m.get_request(self.wctx, only_text["id"])                                # abrir marca como visto e avisa o remetente
        self.assertEqual(got["status"], "seen")
        self.assertEqual(self.m.list_notifications(self.mctx)["unread"], 2)                  # bem-vindo + «viu o seu pedido»
        # o trabalhador enxerga o anexo do pedido (mesmo sem setor) e o resto não
        self.assertEqual(self.m.open_file(self.wctx, fid)[1], "briefing.pdf")
        with self.assertRaises(WorkError):
            self.m.open_file(self.m.login(self.st.id, "ana")[1], "fl_inexistente")
        # estados
        with self.assertRaises(WorkError):
            self.m.set_request_status(self.mctx, only_text["id"], "done")                   # quem enviou não conclui
        self.m.set_request_status(self.wctx, only_text["id"], "in_progress")
        acts = [a for a in self.m.list_activities(self.wctx, self.w["id"]) if a["request_id"] == only_text["id"]]
        self.assertEqual([a["state"] for a in acts], ["started"])                           # começar o pedido abre uma atividade sozinha
        self.m.reply_request(self.wctx, only_text["id"], "Começando agora")
        self.m.set_request_status(self.wctx, only_text["id"], "done", "Entregue")
        acts = [a for a in self.m.list_activities(self.wctx, self.w["id"]) if a["request_id"] == only_text["id"]]
        self.assertEqual([a["state"] for a in acts], ["finished"])
        self.assertEqual(self.m.get_request(self.mctx, only_text["id"])["status"], "done")
        with self.assertRaises(WorkError):
            self.m.get_request(self.m.login(self.st.id, "ana")[1], "rq_nao_existe")
        stranger = self.m.create_user(self.ctx, {"username": "ze", "role_id": "worker"})
        with self.assertRaises(WorkError):
            self.m.get_request(self.m.login(self.st.id, "ze")[1], only_text["id"])          # quem não participa não vê

    def test_activities_started_continuing_finished_and_stale(self):
        a = self.m.start_activity(self.wctx, "Montar planilha")
        self.assertEqual(a["state"], "started")
        a = self.m.progress_activity(self.wctx, a["id"], "Metade pronta")
        self.assertEqual(a["state"], "continuing")
        self.assertEqual([e["kind"] for e in a["log"]], ["start", "progress"])
        a = self.m.pause_activity(self.wctx, a["id"])
        a = self.m.progress_activity(self.wctx, a["id"])
        self.assertEqual(a["state"], "continuing")
        with self.assertRaises(WorkError):
            self.m.progress_activity(self.mctx, a["id"])                                    # só a dona atualiza
        with mock.patch("asta.work.manager.time.time", return_value=time.time() + 3600):
            self.assertTrue(self.m.list_activities(self.wctx, self.w["id"], "continuing")[0]["stale"])   # sem sinal há muito tempo
        done = self.m.finish_activity(self.wctx, a["id"], "Pronto")
        self.assertEqual((done["state"], done["log"][-1]["kind"]), ("finished", "finish"))
        with self.assertRaises(WorkError):
            self.m.finish_activity(self.wctx, a["id"])
        with self.assertRaises(WorkError):
            self.m.list_activities(self.wctx, self.mg["id"])                                # trabalhador não vê a de outros
        self.assertTrue(self.m.list_activities(self.mctx, self.w["id"]))                    # gerente vê (activities.view_all)
        with self.assertRaises(WorkError):
            self.m.start_activity(self.wctx, "  ")

    def test_uploads_record_automatic_activity_and_versions_and_restricted_folders(self):
        sec = self.m.save_folder(self.ctx, "", {"name": "Diretoria", "access": {"mode": "restricted", "roles": ["manager"]}})
        pub = self.m.save_folder(self.ctx, "", {"name": "Geral"})
        self.m.upload_file(self.mctx, "ata.txt", io.BytesIO(b"v1"), 2, sec["id"])
        up = self.m.upload_file(self.mctx, "ata.txt", io.BytesIO(b"v2 maior"), 8, sec["id"])
        self.assertEqual([v["n"] for v in up["versions"]], [1, 2])                           # mesmo nome na mesma pasta = nova versão
        self.assertEqual(self.m.open_file(self.mctx, up["id"], 1)[0].read_bytes(), b"v1")
        self.assertEqual(self.m.open_file(self.mctx, up["id"])[0].read_bytes(), b"v2 maior")
        with self.assertRaises(WorkError):
            self.m.list_files(self.wctx, sec["id"])                                          # trabalhador não entra no setor restrito
        with self.assertRaises(WorkError):
            self.m.upload_file(self.wctx, "x.txt", io.BytesIO(b"x"), 1, sec["id"])
        with self.assertRaises(WorkError):
            self.m.open_file(self.wctx, up["id"])
        self.assertNotIn(sec["id"], [f["id"] for f in self.m.folders(self.wctx)])
        self.m.upload_file(self.wctx, "foto.png", io.BytesIO(b"\x89PNG"), 4, pub["id"])
        self.assertEqual([f["name"] for f in self.m.list_files(self.mctx, pub["id"])], ["foto.png"])
        with self.assertRaises(WorkError):
            self.m.delete_file(self.mctx, self.m.list_files(self.mctx, pub["id"])[0]["id"]) if False else self.m.delete_file(self.wctx, up["id"])
        autos = [a["title"] for a in self.m.list_activities(self.ctx, "", "", True)]
        self.assertTrue(any("nova versão de ata.txt" in t for t in autos))
        for f in ("a" * 5, "../../etc/passwd", "con\x00.txt"):
            self.m.upload_file(self.mctx, f, io.BytesIO(b"1"), 1, pub["id"])
        names = [f["name"] for f in self.m.list_files(self.mctx, pub["id"])]
        self.assertTrue(all("/" not in n and "\x00" not in n for n in names))
        self.box_.store.save_settings({"work": {"max_file_mb": 1}})
        with self.assertRaises(WorkError) as cm:
            self.m.upload_file(self.mctx, "grande.bin", io.BytesIO(b"0" * 10), 2 * 1024 * 1024, pub["id"])
        self.assertEqual(cm.exception.status, 413)

    def test_board_nodes_edges_layout_autofill_and_route(self):
        board_ = self.m.autofill_board(self.ctx)
        kinds = [n["kind"] for n in board_["nodes"]]
        self.assertEqual(kinds.count("person"), 3)
        self.assertEqual(len(board_["edges"]), 2)                                            # admin → gerente → trabalhador
        ys = {n["label"]: n["y"] for n in board_["nodes"]}
        self.assertLess(ys["Ana"], ys["Maria"])
        self.assertLess(ys["Maria"], ys["João"])                                             # chefia em cima
        again = self.m.autofill_board(self.ctx)
        self.assertEqual(len(again["nodes"]), 3)                                             # não duplica
        route = self.m.route_between(self.st, self.w["id"], self.ctx.uid)
        self.assertEqual([r["label"] for r in route], ["João", "Maria", "Ana"])
        req = self.m.send_request(self.mctx, {"to": [self.w["id"]], "body": "olá"})
        self.assertEqual([r["label"] for r in req["route"]], ["Maria", "João"])
        with self.assertRaises(WorkError):
            self.m.save_node(self.wctx, "", {"kind": "note", "label": "x"})                  # trabalhador só vê o quadro
        with self.assertRaises(WorkError):
            self.m.save_edge(self.ctx, "", {"from": "n_nada", "to": "n_nada2"})
        n = board_["nodes"][0]
        self.m.delete_node(self.ctx, n["id"])
        self.assertNotIn(n["id"], [e["from"] for e in self.m.board(self.ctx)["edges"]] + [e["to"] for e in self.m.board(self.ctx)["edges"]])

    def test_notifications_broadcast_and_read(self):
        n = self.m.broadcast(self.mctx, "Reunião às 15h", "Sala 2", {"all": True})
        self.assertEqual(n, 2)                                                               # todos menos quem enviou
        self.assertEqual(self.m.list_notifications(self.wctx)["unread"], 1 + 1)              # + o «bem-vindo»
        with self.assertRaises(WorkError):
            self.m.broadcast(self.wctx, "x", "", {"all": True})
        ids = [i["id"] for i in self.m.list_notifications(self.wctx)["items"]][:1]
        self.assertEqual(self.m.mark_read(self.wctx, ids), 1)
        self.assertEqual(self.m.mark_read(self.wctx, everything=True), 1)
        self.assertEqual(self.m.list_notifications(self.wctx)["unread"], 0)
        self.assertEqual(self.m.mark_read(self.mctx, [i["id"] for i in self.m.list_notifications(self.wctx)["items"]]), 0)   # não marca as dos outros
        seq, items = self.m.wait_events(0, self.st.id, self.w["id"], 0.01)
        self.assertTrue(any(e["kind"] == "notifications" for e in items))
        _, others = self.m.wait_events(0, self.st.id, self.mg["id"], 0.01)
        self.assertFalse(any(e["kind"] == "notifications" and e.get("id") in ids for e in others))   # notificação de um não vai pelo canal do outro

    def test_export_has_documents_and_no_secrets(self):
        self.m.set_password(self.ctx, self.ctx.uid, "abcdef", "synced")
        dest = Path(tempfile.mkdtemp()) / "x.zip"
        self.addCleanup(shutil.rmtree, dest.parent, True)
        self.m.upload_file(self.ctx, "a.txt", io.BytesIO(b"oi"), 2)
        self.m.export_zip(self.ctx, dest, with_files=True)
        with zipfile.ZipFile(dest) as z:
            names = z.namelist()
            blob = b"".join(z.read(n) for n in names)
        self.assertTrue(any(n.startswith("docs/users/") for n in names))
        self.assertTrue(any(n.endswith("a.txt") for n in names))
        self.assertNotIn(self.st.secret().encode(), blob)
        self.assertNotIn(b"pbkdf2", blob)
        with self.assertRaises(WorkError):
            self.m.export_zip(self.wctx, dest)


class AITests(WorkCase):
    def setUp(self):
        super().setUp()
        self.b = self.box(listen=False)
        self.st, self.token, self.ctx = self.org(self.b)
        self.m = self.b.m
        self.dev = self.m.create_user(self.ctx, {"username": "dev", "display_name": "Davi", "role_id": "worker", "bio": "programação backend python"})
        self.fin = self.m.create_user(self.ctx, {"username": "fin", "display_name": "Fátima", "role_id": "worker", "bio": "contabilidade e relatórios financeiros"})

    def use(self, provider):
        self.m._resolve = lambda settings: (provider, {"demo": False, "id": "fake", "model": "fake-1"})

    def test_without_ai_the_request_draft_falls_back_to_rules(self):
        out = wai.draft_request(self.ctx, "Preciso do relatório financeiro do mês, urgente!\n- conferir contas\n- enviar ao diretor")
        self.assertFalse(out["ai"])
        self.assertTrue(out["warning"])
        self.assertEqual(out["priority"], "urgent")
        self.assertEqual(out["checklist"], ["conferir contas", "enviar ao diretor"])
        self.assertEqual(out["recipients"][0], self.fin["id"])                                # afinidade de palavras: financeiro
        self.assertEqual([s["status"] for s in out["agents"]], ["fallback"] * 3)
        with self.assertRaises(ValueError):
            wai.draft_request(self.ctx, "")

    def test_three_agents_write_the_request_and_invalid_output_falls_back_per_step(self):
        prov = FakeProvider({
            "Planner": {"goal": "Relatório mensal", "deliverables": ["PDF"], "priority": "high", "due": "2026-12-01", "recipients": [self.fin["id"], "u_inventado"]},
            "Writer": {"title": "Preparar o relatório mensal", "body": "Contexto e prazo.", "checklist": ["PDF final"]},
            "Reviewer": {"title": "Preparar o relatório mensal", "body": "Contexto, entrega e prazo.", "checklist": ["PDF final"], "priority": "bogus", "due": "amanhã", "issues": ["prazo explícito"]}})
        self.use(prov)
        out = wai.draft_request(self.ctx, "relatório do mês")
        self.assertTrue(out["ai"])
        self.assertEqual((out["title"], out["priority"], out["due"]), ("Preparar o relatório mensal", "high", "2026-12-01"))   # prioridade inválida herda a do plano; data inválida some
        self.assertEqual(out["recipients"], [self.fin["id"]])                                  # id inventado é descartado
        self.assertEqual([s["status"] for s in out["agents"]], ["ok"] * 3)
        self.use(FakeProvider(fail=True))
        bad = wai.draft_request(self.ctx, "algo qualquer para fazer")
        self.assertFalse(bad["ai"])
        self.assertEqual(bad["body"], "algo qualquer para fazer")                              # a entrega acontece mesmo assim

    def test_team_of_agents_runs_a_table_and_a_synthesizer(self):
        prov = FakeProvider({"Planner": {"goal": "g", "deliverables": [], "priority": "normal", "due": "", "recipients": []},
                             "Writer": {"title": "Título", "body": "Corpo", "checklist": []}, "Reviewer": {"title": "T", "body": "B", "checklist": [], "priority": "normal", "due": "", "issues": []}})
        self.use(prov)
        out = wai.draft_request(self.ctx, "faça algo", req={"agents": 4, "effort": "mega"})
        self.assertEqual(out["team"]["agents"], 4)
        planner_calls = [c for c in prov.calls if "ROLE: Planner" in c]
        self.assertEqual(len(planner_calls), 5)                                                # 4 agentes + o Sintetizador

    def test_flow_draft_is_validated_and_has_a_deterministic_fallback(self):
        out = wai.draft_flow(self.ctx, "Empresa com financeiro, vendas e suporte ao cliente")
        names = [s["name"] for s in out["draft"]["sectors"]]
        self.assertEqual(names, ["Financeiro", "Comercial", "Atendimento"])
        keys = {n["key"] for n in out["draft"]["nodes"]}
        self.assertTrue(all(e["from"] in keys and e["to"] in keys for e in out["draft"]["edges"]))
        self.assertTrue(all("x" in n and "y" in n for n in out["draft"]["nodes"]))
        raw = {"sectors": [{"name": "TI"}, {"name": "TI"}], "nodes": [{"key": "a", "kind": "role", "label": "A", "ref": "nao-existe"}, {"key": "b", "kind": "person", "label": "B", "ref": self.dev["id"]},
                                                                         {"key": "b", "label": "dup"}, {"key": "c", "kind": "sector", "label": "C", "sector": "ti"}],
               "edges": [{"from": "a", "to": "b"}, {"from": "a", "to": "zzz"}, {"from": "b", "to": "b"}, {"from": "a", "to": "b"}]}
        ok = wai.normalize_flow(raw, ["admin"], [self.dev["id"]])
        self.assertEqual([s["name"] for s in ok["sectors"]], ["TI"])
        self.assertEqual([(n["key"], n["kind"]) for n in ok["nodes"]], [("a", "note"), ("b", "person"), ("c", "sector")])
        self.assertEqual(len(ok["edges"]), 1)
        self.assertIsNone(wai.normalize_flow({"nodes": [{"label": "só um"}]}, [], []))
        self.assertIsNone(wai.normalize_flow("lixo", [], []))

    def test_applying_a_flow_creates_sectors_cards_and_links(self):
        draft = wai.draft_flow(self.ctx, "financeiro e vendas")["draft"]
        board_ = self.m.apply_draft(self.ctx, draft)
        self.assertEqual(len(board_["folders"]), 2)
        self.assertGreaterEqual(len(board_["nodes"]), 7)
        self.assertEqual(len([e for e in board_["edges"]]), len(draft["edges"]))
        sector_nodes = [n for n in board_["nodes"] if n["kind"] == "sector"]
        self.assertTrue(all(self.m.board(self.ctx) and n["ref"] in {f["id"] for f in board_["folders"]} for n in sector_nodes))

    def test_digest_numbers_come_from_the_program_not_the_model(self):
        a = self.m.start_activity(self.ctx, "Tarefa A")
        self.m.finish_activity(self.ctx, a["id"], "ok")
        self.m.start_activity(self.ctx, "Tarefa B")
        out = wai.digest(self.ctx, "me", "day")
        self.assertEqual(out["stats"]["by_state"], {"finished": 1, "started": 1})
        self.assertIn("1 concluída", out["summary"])
        self.use(FakeProvider({"Analyst and Writer": {"summary": "Dia produtivo.", "highlights": ["Tarefa A"], "risks": [], "next_steps": ["Fechar B"]}}))
        ai = wai.digest(self.ctx, "me", "week")
        self.assertEqual((ai["summary"], ai["ai"]), ("Dia produtivo.", True))
        self.assertEqual(ai["stats"]["activities"], 2)
        wctx = self.m.login(self.st.id, "dev")[1]
        with self.assertRaises(WorkError):
            wai.digest(wctx, "org", "day")                                                    # visão da organização exige activities.view_all

    def test_router_ranks_people_by_fit_then_by_workload(self):
        out = wai.suggest(self.ctx, brief="Corrigir um bug no backend em python")
        self.assertEqual(out["recipients"][0]["user"], self.dev["id"])
        self.m.save_function(self.ctx, "", {"name": "Python"})
        people = [{"id": "x", "name": "X", "role": "", "title": "", "functions": [], "bio": "python", "busy": 3}, {"id": "y", "name": "Y", "role": "", "title": "", "functions": [], "bio": "python", "busy": 0}]
        self.assertEqual([r["user"] for r in wai.rank_people("python", people)], ["y", "x"])

    def test_prompts_are_packaged(self):
        self.assertEqual(sorted(wai.prompt_names()), ["core", "digest", "flow_analyst", "flow_designer", "flow_reviewer", "planner", "reviewer", "router", "writer"])
        self.assertIn("pyproject", "pyproject")
        text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
        self.assertIn("work/prompts/*.md", text)


class SmallThingsTests(unittest.TestCase):
    def test_board_math(self):
        nodes = [{"id": i, "label": i} for i in "abcd"]
        edges = [{"from": "a", "to": "b"}, {"from": "a", "to": "c"}, {"from": "c", "to": "d"}, {"from": "d", "to": "a"}]   # tem ciclo
        d = board.depths(nodes, edges)
        self.assertEqual(set(d.values()), {0})                                               # só ciclo: ninguém é raiz → todos no nível 0, sem travar
        d = board.depths(nodes, edges[:3])
        self.assertEqual((d["a"], d["b"], d["d"]), (0, 1, 2))
        pos = board.auto_layout(nodes, edges[:3])
        self.assertEqual(len(pos), 4)
        self.assertEqual(board.find_path(nodes, edges[:3], ["b"], ["d"]), ["b", "a", "c", "d"])
        self.assertEqual(board.find_path(nodes, [], ["a"], ["d"]), [])

    def test_config_normalization(self):
        self.assertEqual(normalize_config({})["peer"], {"listen": "off", "port": 8790})
        self.assertEqual(normalize_config({"peer": {"listen": "rm -rf", "port": 1}})["peer"], {"listen": "off", "port": 1024})
        self.assertEqual(normalize_config({"peer": {"listen": "100.64.1.2", "port": "9000"}})["peer"], {"listen": "100.64.1.2", "port": 9000})
        self.assertEqual(normalize_config({"agents": 7, "effort": "zzz"})["agents"], 8)

    def test_tailscale_status_is_parsed_from_the_cli(self):
        sample = {"BackendState": "Running", "Self": {"HostName": "meu-pc", "DNSName": "meu-pc.tail.ts.net.", "TailscaleIPs": ["100.64.0.5", "fd7a::5"], "Online": True, "OS": "linux"},
                  "Peer": {"k1": {"HostName": "zeta", "TailscaleIPs": ["100.64.0.9"], "Online": False}, "k2": {"HostName": "alfa", "TailscaleIPs": ["100.64.0.7"], "Online": True, "OS": "windows"}},
                  "CurrentTailnet": {"Name": "acme.ts.net"}}
        st = tailscale.parse(sample)
        self.assertEqual((st["running"], st["ip"], st["tailnet"]), (True, "100.64.0.5", "acme.ts.net"))
        self.assertEqual([p["name"] for p in st["peers"]], ["alfa", "zeta"])                  # online primeiro
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        exe = tmp / "tailscale"
        exe.write_text("#!/bin/sh\ncat <<'EOF'\n" + json.dumps(sample) + "\nEOF\n")
        exe.chmod(0o755)
        with mock.patch.dict(os.environ, {"ASTA_TAILSCALE": str(exe)}):
            real = tailscale.status(refresh=True)
            self.assertEqual((real["installed"], real["running"], real["ip"]), (True, True, "100.64.0.5"))
        with mock.patch.dict(os.environ, {"ASTA_TAILSCALE": str(tmp / "nao-existe")}), mock.patch("shutil.which", return_value=None):
            gone = tailscale.status(refresh=True)
            self.assertFalse(gone["installed"])
            self.assertEqual(tailscale.label(gone), "não instalado")
        tailscale.status(refresh=True)

    def test_import_and_export_settings_never_open_the_network(self):
        from asta import uiprefs

        patch = uiprefs.import_patch({"schema": uiprefs.EXPORT_SCHEMA, "settings": {"work": {"peer": {"listen": "lan"}, "agents": 4, "auto_sync": False}}})
        self.assertEqual(patch["work"], {"agents": 4})
        out = uiprefs.export_settings({"work": {"peer": {"listen": "lan"}, "agents": 4}})
        self.assertEqual(out["settings"]["work"], {"agents": 4})


class HttpApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="asta-workapi-"))
        cls.store = Store(cls.tmp)
        cls.httpd, cls.app = make_server("127.0.0.1", 0, cls.store)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.c = Client(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def call(self, method, path, body=None, cookie="", raw=None, headers=None):
        import http.client

        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        h = dict(headers or {})
        if cookie:
            h["Cookie"] = cookie
        data = raw
        if body is not None:
            data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        payload = r.read()
        out = (r.status, dict(r.getheaders()), payload)
        c.close()
        return out

    def j(self, *a, **kw):
        s, h, p = self.call(*a, **kw)
        return s, (json.loads(p) if p[:1] in (b"{", b"[") else p), h

    def test_full_session_over_http(self):
        s, d, h = self.j("GET", "/api/work/status")
        self.assertEqual((s, d["orgs"], d["tailscale"]["installed"]), (200, [], d["tailscale"]["installed"]))
        self.assertEqual(self.j("GET", "/api/work/me")[0], 401)
        s, d, h = self.j("POST", "/api/work/orgs", {"name": "Acme", "admin": {"username": "ana", "password": "segredo1", "auth_mode": "synced"}, "machine_name": "PC-API"})
        self.assertEqual(s, 200)
        cookie = h["Set-Cookie"].split(";")[0]
        self.assertIn("HttpOnly", h["Set-Cookie"])
        self.assertIn("SameSite=Strict", h["Set-Cookie"])
        oid = d["org"]["id"]
        self.assertEqual(self.j("GET", "/api/work/me", cookie=cookie)[1]["user"]["username"], "ana")
        self.assertEqual(self.j("POST", "/api/work/login", {"org": oid, "username": "ana", "password": "x"})[0], 401)
        self.assertEqual(self.j("GET", f"/api/work/orgs/{oid}/people")[1]["people"][0]["username"], "ana")
        # pessoas e pedido
        s, w, _ = self.j("POST", "/api/work/users", {"username": "joao", "role_id": "worker", "display_name": "João"}, cookie)
        self.assertEqual(s, 201)
        self.assertEqual(self.j("POST", "/api/work/users", {"username": "joao"}, cookie)[0], 409)
        s, r, _ = self.j("POST", "/api/work/requests", {"to": [w["id"]], "body": "Fechar o caixa", "priority": "high"}, cookie)
        self.assertEqual((s, r["status"]), (201, "sent"))
        # upload binário (qualquer formato) + download + inline seguro
        blob = bytes(range(256)) * 40
        s, f, _ = self.j("POST", "/api/work/files", cookie=cookie, raw=blob, headers={"X-Filename": "dados.xyz", "Content-Type": "application/x-weird"})
        self.assertEqual(s, 201)
        s, h, p = self.call("GET", f"/api/work/files/{f['id']}/download", cookie=cookie)
        self.assertEqual((s, p), (200, blob))
        self.assertIn("attachment", h["Content-Disposition"])
        self.assertIn("sandbox", h["Content-Security-Policy"])
        s, f2, _ = self.j("POST", "/api/work/files", cookie=cookie, raw=b"<script>alert(1)</script>", headers={"X-Filename": "x.html"})
        s, h, p = self.call("GET", f"/api/work/files/{f2['id']}/download?inline=1", cookie=cookie)
        self.assertIn("attachment", h.get("Content-Disposition", ""))                          # HTML nunca é servido inline (XSS)
        s, f3, _ = self.j("POST", "/api/work/files", cookie=cookie, raw=b"\x89PNG", headers={"X-Filename": "a.png"})
        s, h, p = self.call("GET", f"/api/work/files/{f3['id']}/download?inline=1", cookie=cookie)
        self.assertEqual(h["Content-Type"], "image/png")
        self.assertNotIn("Content-Disposition", h)
        self.assertEqual(self.call("GET", f"/api/work/files/{f['id']}/download")[0], 401)       # sem sessão não baixa
        # permissão: o trabalhador entra (sem senha) mas não envia pedidos
        s, _, h2 = self.j("POST", "/api/work/login", {"org": oid, "username": "joao"})
        wcookie = h2["Set-Cookie"].split(";")[0]
        self.assertEqual(self.j("POST", "/api/work/requests", {"to": [w["id"]], "body": "x"}, wcookie)[0], 403)
        self.assertEqual(self.j("GET", "/api/work/notifications?unread=1", cookie=wcookie)[1]["unread"], 2)   # bem-vindo + pedido
        # IA sem provedor: fallback com aviso
        s, d, _ = self.j("POST", "/api/work/ai/request", {"brief": "Revisar o contrato, prazo 2026-12-31"}, cookie)
        self.assertEqual((s, d["ai"], d["due"]), (200, False, "2026-12-31"))
        s, d, _ = self.j("POST", "/api/work/ai/flow", {"description": "loja com vendas e estoque"}, cookie)
        self.assertEqual(s, 200)
        s, b, _ = self.j("POST", "/api/work/board/apply", {"draft": d["draft"]}, cookie)
        self.assertEqual(s, 200)
        self.assertEqual(self.j("POST", "/api/work/board/apply", {"draft": {"nodes": []}}, cookie)[0], 400)
        self.assertEqual(self.j("POST", "/api/work/ai/flow", {"description": ""}, cookie)[0], 400)
        # rede: convite exige escutar
        self.assertEqual(self.j("POST", "/api/work/network/invite", {}, cookie)[0], 409)
        s, n, _ = self.j("GET", "/api/work/network", cookie=cookie)
        self.assertEqual((s, n["machines"][0]["name"], n["listening"]), (200, "PC-API", False))
        self.assertEqual(self.j("GET", "/api/work/network", cookie=wcookie)[1]["can_manage"], False)
        # exportação
        s, h, p = self.call("GET", "/api/work/export", cookie=cookie)
        self.assertEqual(s, 200)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(p)))
        # configurações: 'work' entra no padrão e na normalização de equipe
        st = self.j("GET", "/api/settings")[1]
        self.assertEqual(st["work"]["peer"]["listen"], "off")
        self.assertEqual(self.j("GET", "/api/work/prompts")[1]["prompts"][0]["name"], "core")
        # sair
        s, _, hl = self.j("POST", "/api/work/logout", {}, cookie)
        self.assertIn("Max-Age=0", hl["Set-Cookie"])
        self.assertEqual(self.j("GET", "/api/work/me", cookie=cookie)[0], 401)

    def test_live_events_deliver_notifications_to_the_right_person(self):
        s, d, h = self.j("POST", "/api/work/orgs", {"name": "Live", "admin": {"username": "chefe1"}})
        cookie = h["Set-Cookie"].split(";")[0]
        oid = d["org"]["id"]
        s, w, _ = self.j("POST", "/api/work/users", {"username": "func1", "role_id": "worker"}, cookie)
        wcookie = self.j("POST", "/api/work/login", {"org": oid, "username": "func1"})[2]["Set-Cookie"].split(";")[0]
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", "/api/work/events", headers={"Cookie": wcookie})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        first = resp.fp.readline()
        self.assertIn(b"hello", first)
        resp.fp.readline()
        threading.Timer(0.3, lambda: self.j("POST", "/api/work/requests", {"to": [w["id"]], "body": "Chegou agora"}, cookie)).start()
        seen = b""
        deadline = time.time() + 8
        while time.time() < deadline and b'"unread"' not in seen:
            seen += resp.fp.readline()
        conn.close()
        self.assertIn(b'"kind": "requests"', seen)
        self.assertIn(b'"type": "unread"', seen)

    def test_handoff_to_computer_use_needs_it_turned_on(self):
        s, d, h = self.j("POST", "/api/work/orgs", {"name": "Hand", "admin": {"username": "chefe2"}})
        cookie = h["Set-Cookie"].split(";")[0]
        s, w, _ = self.j("POST", "/api/work/users", {"username": "func2", "role_id": "worker"}, cookie)
        s, r, _ = self.j("POST", "/api/work/requests", {"to": [w["id"]], "body": "Organizar a pasta Downloads"}, cookie)
        wcookie = self.j("POST", "/api/work/login", {"org": d["org"]["id"], "username": "func2"})[2]["Set-Cookie"].split(";")[0]
        s, e, _ = self.j("POST", f"/api/work/requests/{r['id']}/computer", {}, wcookie)
        self.assertEqual(s, 403)
        self.assertIn("desligado", e["error"])


if __name__ == "__main__":
    unittest.main()
