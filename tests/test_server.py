"""Integração: API HTTP, pipeline multi-agentes, pacote do jogo e segurança."""
import io
import json
import re
import shutil
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.server import make_server  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.helpers import Client, MockProviderServer  # noqa: E402
from tests.test_core import make_docx  # noqa: E402


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="asta-srv-"))
        cls.store = Store(cls.tmp)
        cls.httpd, cls.app = make_server("127.0.0.1", 0, cls.store)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.c = Client(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def generate(self, body):
        status, r = self.c.json("POST", "/api/generate", body)
        self.assertEqual(status, 200, r)
        events = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        return events


class ApiBasicsTests(ServerCase):
    def test_state_and_webui(self):
        status, s = self.c.json("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(s["settings"]["active"]["generation"], "demo")
        self.assertIn("anthropic", [p["id"] for p in s["presets"]])
        self.assertIn(s["hardware"]["tier"], ("low", "medium", "high"))
        status, headers, body = self.c.req("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>ASTA</title>", body)
        status, headers, body = self.c.req("GET", "/js/main.js")
        self.assertIn("javascript", headers["Content-Type"])
        status, _, _ = self.c.req("GET", "/#/library")
        self.assertEqual(status, 200)

    def test_settings_never_expose_keys(self):
        self.c.json("PUT", "/api/settings", {"providers": {"openai": {"api_key": "sk-TOPSECRET", "model": "x"}}})
        status, raw = self.c.json("GET", "/api/settings")
        self.assertNotIn("TOPSECRET", json.dumps(raw))
        self.assertTrue(raw["providers"]["openai"]["has_key"])
        status, st = self.c.json("GET", "/api/state")
        self.assertNotIn("TOPSECRET", json.dumps(st))
        self.c.json("PUT", "/api/settings", {"providers": {"openai": {"api_key": None}}})

    def test_cards_crud_and_import(self):
        status, c = self.c.json("POST", "/api/characters", {"name": "Teste", "tags": ["a", "b"], "system_prompt": "Você é X."})
        self.assertEqual(status, 200)
        status, c2 = self.c.json("PUT", f"/api/characters/{c['id']}", {"name": "Teste 2"})
        self.assertEqual(c2["name"], "Teste 2")
        status, lst = self.c.json("GET", "/api/characters")
        self.assertIn(c["id"], [x["id"] for x in lst])
        status, imp = self.c.json("POST", "/api/characters/import", raw=json.dumps({"name": "Importado", "description": "d"}).encode())
        self.assertEqual(imp["name"], "Importado")
        self.assertEqual(self.c.json("DELETE", f"/api/characters/{c['id']}")[0], 200)
        self.assertEqual(self.c.json("GET", f"/api/characters/{c['id']}")[0], 404)
        status, wb = self.c.json("POST", "/api/worldbuildings", {"name": "Reino", "system_prompt": "Magia rara."})
        self.assertEqual(wb["schema"], "asta.worldbuilding.v1")
        self.assertEqual(self.c.json("GET", "/api/worldbuildings")[1][0]["id"], wb["id"])

    def test_ai_draft_endpoints_work_with_demo(self):
        status, card = self.c.json("POST", "/api/ai/character", {"description": "Uma ferreira rabugenta chamada Brita."})
        self.assertEqual(status, 200)
        self.assertTrue(card["name"])
        self.assertEqual(self.c.json("POST", "/api/ai/character", {"description": ""})[0], 400)


class SecurityTests(ServerCase):
    def test_host_header_must_be_local(self):
        status, _, _ = self.c.req("GET", "/api/state", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403)
        status, _, _ = self.c.req("GET", "/api/state", headers={"Host": f"localhost:{self.port}"})
        self.assertEqual(status, 200)

    def test_cross_origin_writes_are_rejected(self):
        status, _, _ = self.c.req("PUT", "/api/settings", {"language": "en"}, headers={"Origin": "https://evil.example.com"})
        self.assertEqual(status, 403)
        status, _, _ = self.c.req("POST", "/api/generate", {"prompt": "x"}, headers={"Origin": "null"})
        self.assertEqual(status, 403)
        self.assertEqual(self.store.get_settings()["language"], "auto")
        status, _, _ = self.c.req("PUT", "/api/settings", {"language": "auto"}, headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)

    def test_path_traversal_is_blocked(self):
        for path in ("/../../etc/passwd", "/..%2f..%2fetc/passwd", "/css/..%2f..%2f..%2fsettings.json", "/%2e%2e/%2e%2e/etc/passwd"):
            status, _, body = self.c.req("GET", path)
            self.assertNotEqual(b"root:", body[:5], path)
            self.assertIn(status, (200, 403, 404), path)  # 200 = SPA index.html, nunca o arquivo pedido
            if status == 200:
                self.assertIn(b"<title>ASTA</title>", body)
        status, _, _ = self.c.req("GET", "/api/projects/..%2f..%2fsettings.json")
        self.assertEqual(status, 404)
        status, _, _ = self.c.req("GET", "/api/characters/..%2f..")
        self.assertEqual(status, 404)


class GenerationFlowTests(ServerCase):
    def test_full_flow_with_attachment_zip_play_save_and_chat(self):
        # anexo (docx) enviado em corpo cru + X-Filename (acentos)
        docx = io.BytesIO()
        tmp = self.tmp / "lore.docx"
        make_docx(tmp, "A vila de Alder tem uma torre assombrada.")
        data = tmp.read_bytes()
        status, up = self.c.json("POST", "/api/uploads", raw=data, headers={"X-Filename": "hist%C3%B3ria.docx", "Content-Type": "application/octet-stream"})
        self.assertEqual(status, 200)
        self.assertEqual(up["name"], "história.docx")
        status, wb = self.c.json("POST", "/api/worldbuildings", {"name": "Alder", "system_prompt": "Fantasia sombria."})

        events = self.generate({"prompt": "Uma vila medieval na floresta ao anoitecer", "attachment_ids": [up["id"]], "worldbuilding_id": wb["id"], "settings": {"perspective": "first"}})
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "start")
        self.assertIn("done", types)
        self.assertEqual(types[-1], "end")
        steps_done = [e["id"] for e in events if e["type"] == "step" and e["status"] in ("done", "skipped", "warn")]
        for sid in ("attachments", "analyst", "planner", "characters", "architect", "sound_ux", "reviewer", "package"):
            self.assertIn(sid, steps_done)
        done = next(e for e in events if e["type"] == "done")
        pid = done["project_id"]

        # biblioteca
        status, projects = self.c.json("GET", "/api/projects")
        self.assertIn(pid, [p["id"] for p in projects])
        status, proj = self.c.json("GET", f"/api/projects/{pid}")
        self.assertEqual(proj["world"]["perspective"], "first")
        self.assertEqual(proj["attachments"][0]["kind"], "document")
        self.assertTrue(len(proj["characters"]) >= 2)

        # ZIP com a estrutura pedida
        status, headers, zbytes = self.c.req("GET", f"/api/projects/{pid}/download")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        z = zipfile.ZipFile(io.BytesIO(zbytes))
        names = set(z.namelist())
        for must in ("Game.html", "README.md", "CHANGELOG.md", "code/main.js", "code/world.data.js", "code/vendor/three.min.js", "chars/chars.js",
                     "sound/sound.json", "ui/ux/theme.css", "ui/ux/ux.json", "prompts/prompt.md", "prompts/attachments.md", "prompts/worldbuilding.md"):
            self.assertIn(must, names)
        self.assertTrue(any(n.startswith("prompts/agents/01-analyst") for n in names))
        self.assertTrue(any(n.startswith("chars/") and n.endswith(".json") for n in names))
        self.assertTrue(any(n.startswith("prompts/attachments/") for n in names))
        # todo recurso referenciado em Game.html existe no ZIP
        html = z.read("Game.html").decode()
        refs = re.findall(r'(?:src|href)="([^"]+)"', html)
        self.assertGreaterEqual(len(refs), 10)
        for r in refs:
            self.assertIn(r, names, r)
        self.assertIn("A vila de Alder", z.read("prompts/attachments.md").decode())
        self.assertIn("v1", z.read("CHANGELOG.md").decode())
        # dados do mundo embutidos como JS (funciona via file://)
        wd = z.read("code/world.data.js").decode()
        self.assertTrue(wd.startswith("window.ASTA_WORLD="))
        self.assertIn("window.ASTA_META=", wd)
        self.assertIn("Fantasia sombria", wd)

        # jogo hospedado
        status, headers, body = self.c.req("GET", f"/play/{pid}/")
        self.assertEqual(status, 200)
        self.assertIn(b"three.min.js", body)
        status, _, cfg = self.c.req("GET", f"/play/{pid}/code/config.js")
        self.assertIn(b'"mode":"hosted"', cfg)
        self.assertEqual(self.c.req("GET", f"/play/{pid}/prompts/prompt.md")[0], 404)  # só pastas do jogo
        self.assertEqual(self.c.req("GET", f"/play/{pid}/../project.json")[0], 404)
        self.assertEqual(self.c.req("GET", f"/play/{pid}/code/..%2f..%2fproject.json")[0], 404)

        # salvamento persistente do mundo
        self.assertEqual(self.c.json("GET", f"/api/play/{pid}/save")[1], {})
        self.assertEqual(self.c.json("PUT", f"/api/play/{pid}/save", {"v": 1, "player": {"x": 3}})[0], 200)
        self.assertEqual(self.c.json("GET", f"/api/play/{pid}/save")[1]["player"]["x"], 3)

        # conversa de NPC via provedor de personagens (stream SSE)
        evs = self.c.sse(f"/api/play/{pid}/llm", {"messages": [{"role": "system", "content": "# You are Mira.\nRole: herbalista"}, {"role": "user", "content": "Pode me seguir?"}]}, method="POST", limit=100)
        text = "".join(e.get("delta", "") for e in evs)
        self.assertIn("[[action:follow]]", text)
        self.assertTrue(evs[-1].get("done"))
        status, info = self.c.json("GET", f"/api/play/{pid}/info")
        self.assertEqual(info["provider"], "demo")
        self.assertEqual(self.c.json("POST", f"/api/play/{pid}/llm", {"messages": []})[0], 400)

        # atualização por IA → nova versão, ids de personagens estáveis
        before = [c["id"] for c in proj["characters"]]
        events = self.generate({"prompt": "Adicione uma torre ao norte", "project_id": pid})
        self.assertEqual([e for e in events if e["type"] == "done"][0]["version"], 2)
        status, proj2 = self.c.json("GET", f"/api/projects/{pid}")
        self.assertEqual([c["id"] for c in proj2["characters"]][: len(before)], before)
        self.assertEqual(len(proj2["world"]["structures"]), len(proj["world"]["structures"]) + 1)
        z2 = zipfile.ZipFile(io.BytesIO(self.c.req("GET", f"/api/projects/{pid}/download")[2]))
        self.assertIn("v2", z2.read("CHANGELOG.md").decode())
        self.assertIn("Adicione uma torre", z2.read("CHANGELOG.md").decode())
        self.assertEqual(self.c.req("GET", f"/play/{pid}/v1/Game.html")[0], 200)  # versão antiga continua jogável

        # edição manual (sem IA) → v3
        status, edited = self.c.json("POST", f"/api/projects/{pid}/edit", {"environment": {"weather": "storm", "time_of_day": 3}, "perspective": "third",
                                                                          "npcs": [{"id": proj2["world"]["npcs"][0]["id"], "behavior": "idle"}]})
        self.assertEqual(edited["current"], 3)
        status, proj3 = self.c.json("GET", f"/api/projects/{pid}")
        self.assertEqual(proj3["world"]["environment"]["weather"], "storm")
        self.assertEqual(proj3["world"]["environment"]["time_of_day"], 3)
        self.assertEqual(proj3["world"]["npcs"][0]["behavior"], "idle")
        self.assertEqual(proj3["world"]["environment"]["biome"], proj2["world"]["environment"]["biome"])
        # rebuild com o motor atual
        self.assertEqual(self.c.json("POST", f"/api/projects/{pid}/rebuild")[1]["current"], 4)

        # tags e renomear
        status, pr = self.c.json("PUT", f"/api/projects/{pid}", {"name": "Alder v2", "tags_custom": ["favorito", "Teste"]})
        self.assertEqual(pr["tags"]["custom"], ["favorito", "teste"])
        self.assertEqual(self.c.json("DELETE", f"/api/projects/{pid}")[0], 200)
        self.assertEqual(self.c.json("GET", f"/api/projects/{pid}")[0], 404)

    def test_single_generation_at_a_time_and_validation(self):
        status, r = self.c.json("POST", "/api/generate", {"prompt": "  "})
        self.assertEqual(status, 400)  # nada para gerar
        status, r = self.c.json("POST", "/api/generate", {"prompt": "x", "project_id": "p_inexistente"})
        events = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        self.assertEqual([e for e in events if e["type"] == "error"][0]["kind"], "validation")
        status, big = self.c.json("POST", "/api/uploads", raw=b"", headers={"X-Filename": "a.txt"})
        self.assertEqual(status, 200)
        self.assertEqual(self.c.json("DELETE", f"/api/uploads/{big['id']}")[1]["ok"], True)

    def test_pipeline_survives_junk_model_output_and_reports_auth_errors(self):
        with MockProviderServer() as mock:
            # o mock responde {"ok": true, "text": "olá"} para tudo → agentes recebem JSON sem os campos esperados
            self.c.json("PUT", "/api/settings", {"providers": {"custom": {"base_url": mock.url + "/v1", "model": "m", "api_key": "k"}}, "active": {"generation": "custom", "characters": "custom"}})
            try:
                events = self.generate({"prompt": "Um acampamento no deserto ao meio-dia"})
                done = [e for e in events if e["type"] == "done"]
                self.assertTrue(done, events[-3:])
                status, proj = self.c.json("GET", f"/api/projects/{done[0]['project_id']}")
                w = proj["world"]
                self.assertGreaterEqual(len(w["structures"]), 3)  # completado por regras
                npc_chars = [c["id"] for c in proj["characters"] if c["role"] == "npc"]
                self.assertEqual(sorted(n["char"] for n in w["npcs"]), sorted(npc_chars))  # todo NPC tem posição
                self.assertTrue(all(c["system_prompt"] for c in proj["characters"]))

                # credencial inválida: falha clara (sem mundo "fantasma")
                self.c.json("PUT", "/api/settings", {"providers": {"custom": {"model": "bad-key"}}})
                n_before = len(self.c.json("GET", "/api/projects")[1])
                events = self.generate({"prompt": "outro mundo"})
                err = [e for e in events if e["type"] == "error"]
                self.assertTrue(err)
                self.assertEqual(err[0]["kind"], "provider")
                self.assertNotIn("k\"", err[0]["message"])
                self.assertEqual(len(self.c.json("GET", "/api/projects")[1]), n_before)
            finally:
                self.c.json("PUT", "/api/settings", {"active": {"generation": "demo", "characters": "demo"}, "providers": {"custom": {"api_key": None}}})


if __name__ == "__main__":
    unittest.main()
