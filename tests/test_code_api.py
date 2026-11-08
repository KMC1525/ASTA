"""Code: a API HTTP (status, pastas, sessões, mensagens, aprovações Sim/Não, desfazer, arquivos/diff, eventos ao vivo), o token do GitHub como segredo (nunca vai ao navegador nem à
exportação) e uma sessão na nuvem (repositório do GitHub por API) de ponta a ponta."""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import uiprefs  # noqa: E402
from asta.code import tools as T  # noqa: E402
from asta.computer import guard as cg  # noqa: E402
from tests.test_code import FakeGitHub  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402

TEST_OK = "import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n"


class CodeApiTests(ServerCase):
    def setUp(self):
        cg.set_home(self.store.home)
        self.addCleanup(cg.set_home, None)
        self.proj = Path(tempfile.mkdtemp(prefix="asta-code-proj-"))
        self.addCleanup(shutil.rmtree, self.proj, ignore_errors=True)
        (self.proj / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        (self.proj / "tests").mkdir()
        (self.proj / "tests" / "__init__.py").write_text("")
        (self.proj / "tests" / "test_calc.py").write_text(TEST_OK)
        self.c.json("PUT", "/api/settings", {"language": "pt-BR", "code": {"mode": "ask", "effort": "high", "agents": 4, "max_sessions": 4, "github": {"api": "", "token": None}, "finalize": {"docs": False, "publish": "none"},
                                                                          "ask_for": ["write", "delete", "run", "install", "git", "publish"], "provider": {"id": "", "model": ""}}})
        for s in self.c.json("GET", "/api/code/sessions")[1]["sessions"]:
            self.c.json("DELETE", f"/api/code/sessions/{s['id']}")
        for f in self.c.json("GET", "/api/code/folders")[1]["folders"]:
            self.c.json("DELETE", f"/api/code/folders/{f['id']}")

    def new_session(self, **kw):
        s, r = self.c.json("POST", "/api/code/sessions", {"workspace": {"type": "local", "path": str(self.proj)}, **kw})
        self.assertEqual(s, 201, r)
        return r

    def wait(self, sid, timeout=25, want=("done", "partial", "failed", "cancelled")):
        end = time.time() + timeout
        while time.time() < end:
            s, d = self.c.json("GET", f"/api/code/sessions/{sid}")
            if s == 200 and d["run"].get("status") in want:
                return d
            time.sleep(0.05)
        self.fail("a execução não terminou")

    # ----- estado
    def test_status_describes_capabilities(self):
        s, st = self.c.json("GET", "/api/code/status")
        self.assertEqual(s, 200)
        self.assertEqual([e["id"] for e in st["efforts"]], ["low", "medium", "high", "extra", "mega", "max", "ultra", "omni"])
        self.assertEqual(len(st["colors"]), 8)
        self.assertEqual((st["limit_agents"], st["limit_sessions"]), (8, 8))
        self.assertEqual(st["publish_modes"], ["none", "commit", "branch", "pr", "main"])
        self.assertIn("python", [x["id"] for x in st["languages"]])
        self.assertIn("publish_changes", st["tools"])
        self.assertIn("editors", st)
        self.assertEqual(st["mode"], "ask")
        s, p = self.c.json("GET", "/api/code/prompts")
        self.assertIn("planner.md", p["prompts"])
        self.assertIn("roles/coder.md", p["prompts"])
        s, one = self.c.json("GET", "/api/code/prompts/planner.md")
        self.assertIn("Planner", one["text"])
        self.assertEqual(self.c.json("GET", "/api/code/prompts/../../etc/passwd")[0], 404)

    # ----- pastas
    def test_folders_over_http(self):
        s, a = self.c.json("POST", "/api/code/folders", {"name": "Trabalho", "color": "orange"})
        self.assertEqual(s, 201)
        s, b = self.c.json("POST", "/api/code/folders", {"name": "Sub", "color": "cyan", "parent": a["id"]})
        self.assertEqual(b["parent"], a["id"])
        s, r = self.c.json("PUT", f"/api/code/folders/{a['id']}", {"name": "Renomeada", "color": "pink", "collapsed": True})
        self.assertEqual((r["name"], r["color"], r["collapsed"]), ("Renomeada", "pink", True))
        self.assertEqual(self.c.json("PUT", f"/api/code/folders/{a['id']}", {"color": "nope"})[0], 400)
        self.assertEqual(self.c.json("POST", "/api/code/folders", {"name": ""})[0], 400)
        self.assertEqual(self.c.json("PUT", "/api/code/folders/fo_none", {"name": "x"})[0], 404)
        s, lst = self.c.json("GET", "/api/code/folders")
        self.assertEqual([f["name"] for f in lst["folders"]], ["Renomeada", "Sub"])
        sess = self.new_session(folder_id=b["id"])
        self.assertEqual(sess["folder_id"], b["id"])
        s, r = self.c.json("DELETE", f"/api/code/folders/{b['id']}")
        self.assertEqual(r["moved_sessions"], 1)
        self.assertEqual(self.c.json("GET", f"/api/code/sessions/{sess['id']}")[1]["folder_id"], a["id"])

    # ----- sessões
    def test_session_lifecycle_with_ask_mode_and_undo(self):
        s = self.new_session(title="Teste", mode="ask", effort="low")
        sid = s["id"]
        self.assertEqual((s["state"], s["mode"], s["effort"]), ("idle", "ask", "low"))
        self.assertEqual(self.c.json("POST", f"/api/code/sessions/{sid}/send", {"text": ""})[0], 400)
        st, r = self.c.json("POST", f"/api/code/sessions/{sid}/send", {"text": "rode os testes"})   # sem IA: as regras entendem
        self.assertEqual(st, 201, r)
        self.assertEqual(self.c.json("POST", f"/api/code/sessions/{sid}/send", {"text": "outra"})[0], 409)
        end = time.time() + 10
        pend = []
        while time.time() < end and not pend:
            d = self.c.json("GET", f"/api/code/sessions/{sid}")[1]
            pend = [p for p in d["run"].get("pendings", []) if p["answer"] is None]
            time.sleep(0.05)
        self.assertEqual(pend[0]["risk"], "run")
        self.assertEqual(self.c.json("GET", "/api/code/sessions")[1]["sessions"][0]["state"], "waiting")
        self.assertEqual(self.c.json("POST", f"/api/code/sessions/{sid}/answer", {"approve": True, "id": pend[0]["id"]})[0], 200)
        d = self.wait(sid)
        self.assertEqual(d["run"]["status"], "done", d["run"])
        self.assertEqual(d["state"], "finished")
        self.assertIn("Ran 1 test", d["run"]["plan"]["steps"][0]["summary"])
        self.assertNotIn("journal", d)
        self.assertEqual(self.c.json("POST", f"/api/code/sessions/{sid}/answer", {"approve": True})[0], 409)
        self.assertEqual(self.c.json("POST", f"/api/code/sessions/{sid}/seen")[0], 200)
        self.assertEqual(self.c.json("GET", f"/api/code/sessions/{sid}")[1]["state"], "idle")
        s2, run = self.c.json("GET", f"/api/code/sessions/{sid}/runs/{d['run']['id']}")
        self.assertEqual(run["id"], d["run"]["id"])
        self.assertEqual(self.c.json("GET", f"/api/code/sessions/{sid}/runs/run_none")[0], 404)
        self.assertEqual(self.c.json("POST", f"/api/code/sessions/{sid}/undo", {})[0], 409)       # os testes não mudaram arquivo
        s3, upd = self.c.json("PUT", f"/api/code/sessions/{sid}", {"title": "Novo título", "mode": "full", "effort": "omni", "agents": 8})
        self.assertEqual((upd["title"], upd["mode"], upd["effort"], upd["agents"]), ("Novo título", "full", "omni", 8))
        self.assertEqual(self.c.json("DELETE", f"/api/code/sessions/{sid}")[0], 200)
        self.assertEqual(self.c.json("GET", f"/api/code/sessions/{sid}")[0], 404)

    def test_full_access_run_cancel_and_files_endpoints(self):
        s = self.new_session(mode="full", effort="low")
        sid = s["id"]
        self.c.json("POST", f"/api/code/sessions/{sid}/send", {"text": "leia calc.py"})
        d = self.wait(sid)
        self.assertEqual(d["run"]["status"], "done")
        s2, b = self.c.json("GET", f"/api/code/sessions/{sid}/browse?path=.")
        self.assertEqual({i["name"] for i in b["items"]}, {"calc.py", "tests"})
        s2, f = self.c.json("GET", f"/api/code/sessions/{sid}/file?path=calc.py")
        self.assertIn("def add", f["text"])
        self.assertEqual(f["language"], "python")
        self.assertEqual(self.c.json("GET", f"/api/code/sessions/{sid}/file?path=../../etc/passwd")[0], 403)
        self.assertEqual(self.c.json("GET", f"/api/code/sessions/{sid}/browse?path=/etc")[0], 403)
        s2, df = self.c.json("GET", f"/api/code/sessions/{sid}/diff")
        self.assertEqual(df["files"], [])
        self.assertEqual(self.c.json("POST", f"/api/code/sessions/{sid}/cancel")[0], 409)       # nada rodando

    def test_unsafe_projects_are_refused_over_http(self):
        for path in (str(Path.home()), str(self.store.home), "/", str(self.proj / "nope")):
            s, r = self.c.json("POST", "/api/code/sessions", {"workspace": {"type": "local", "path": path}})
            self.assertEqual(s, 400, path)
        s, r = self.c.json("POST", "/api/code/sessions", {"workspace": {"type": "github", "repo": "xx"}})
        self.assertEqual(s, 400)

    def test_events_stream_says_hello_with_the_status(self):
        ev = self.c.sse("/api/code/events", limit=1)
        self.assertEqual(ev[0]["type"], "hello")
        self.assertIn("running", ev[0]["status"])

    def test_without_a_project_the_session_gets_its_own_folder(self):
        s, r = self.c.json("POST", "/api/code/sessions", {"title": "Do zero"})
        self.assertEqual(s, 201)
        self.assertEqual(r["workspace"]["kind"], "local")
        self.assertTrue(Path(r["workspace"]["path"]).is_dir())
        self.assertTrue(Path(r["workspace"]["path"]).resolve().is_relative_to((self.store.home / "code" / "workspaces").resolve()))

    # ----- segredos
    def test_github_token_is_a_secret(self):
        s, st = self.c.json("PUT", "/api/settings", {"code": {"github": {"token": "ghp_secrettoken1234567890abcdefABCDEF1234"}}})
        self.assertEqual(s, 200)
        self.assertTrue(st["code"]["github"]["token_set"])
        self.assertEqual(st["code"]["github"]["token"], "")
        state = self.c.json("GET", "/api/state")[1]
        self.assertNotIn("ghp_secret", str(state))
        self.assertTrue(self.c.json("GET", "/api/code/github")[1]["token"])
        self.assertNotIn("ghp_secret", str(self.c.json("GET", "/api/code/status")[1]))
        exp = self.c.json("GET", "/api/settings/export")[1]
        self.assertNotIn("ghp_secret", str(exp))
        self.assertIn("code", exp["settings"])
        s, st2 = self.c.json("POST", "/api/settings/reset", {"section": "code"})
        self.assertEqual(s, 200)
        self.assertTrue(st2["code"]["github"]["token_set"])     # «restaurar padrões» nunca apaga o token
        self.c.json("PUT", "/api/settings", {"code": {"github": {"token": None}}})
        self.assertFalse(self.c.json("GET", "/api/state")[1]["settings"]["code"]["github"]["token_set"])

    def test_imported_settings_never_switch_on_full_access_or_publish_to_main(self):
        patch = uiprefs.import_patch({"schema": uiprefs.EXPORT_SCHEMA, "settings": {"code": {"mode": "full", "ask_for": [], "allow_main": True, "effort": "omni", "agents": 6,
                                                                                            "github": {"token": "x", "api": "http://evil"}, "finalize": {"docs": True, "publish": "main"}, "git_name": "x"}}})
        self.assertEqual(patch["code"], {"effort": "omni", "agents": 6, "finalize": {"docs": True}})
        self.assertNotIn("token", str(uiprefs.export_settings({"code": {"github": {"token": "T", "api": "u"}}})))
        self.assertIn("code", uiprefs.RESETTABLE)
        self.assertIn("code", uiprefs.HIDEABLE)
        self.assertIn("code", uiprefs.START_PAGES)

    def test_github_repos_endpoint_needs_a_token_and_lists_with_one(self):
        self.assertEqual(self.c.json("GET", "/api/code/github/repos")[0], 400)
        fake = FakeGitHub()
        self.addCleanup(fake.close)
        self.c.json("PUT", "/api/settings", {"code": {"github": {"api": fake.url, "token": fake.token}}})
        s, r = self.c.json("GET", "/api/code/github/repos?q=demo")
        self.assertEqual(s, 200)
        self.assertEqual(r["repos"][0]["full_name"], "o/r")
        s, g = self.c.json("GET", "/api/code/github?check=1")
        self.assertEqual(g["user"]["login"], "tester")
        self.c.json("PUT", "/api/settings", {"code": {"github": {"token": "wrong"}}})
        s, g = self.c.json("GET", "/api/code/github?check=1")
        self.assertIn("token", g["error"])
        self.assertEqual(self.c.json("GET", "/api/code/github/repos")[0], 401)
        self.c.json("PUT", "/api/settings", {"code": {"github": {"api": "", "token": None}}})

    def test_cloud_session_end_to_end_over_http(self):
        fake = FakeGitHub()
        self.addCleanup(fake.close)
        self.c.json("PUT", "/api/settings", {"code": {"github": {"api": fake.url, "token": fake.token}, "github_mode": "cloud"}})
        s, r = self.c.json("POST", "/api/code/sessions", {"title": "Nuvem", "workspace": {"type": "github", "repo": "https://github.com/o/r"}, "mode": "full", "effort": "low"})
        self.assertEqual(s, 201, r)
        self.assertEqual(r["workspace"]["status"], "preparing")
        sid = r["id"]
        end = time.time() + 15
        while time.time() < end and self.c.json("GET", f"/api/code/sessions/{sid}")[1]["workspace"]["status"] == "preparing":
            time.sleep(0.05)
        d = self.c.json("GET", f"/api/code/sessions/{sid}")[1]
        self.assertEqual((d["workspace"]["status"], d["workspace"]["kind"]), ("ready", "cloud"))
        self.assertEqual(d["workspace"]["repo"]["owner"], "o")
        b = self.c.json("GET", f"/api/code/sessions/{sid}/browse?path=.")[1]
        self.assertEqual({i["name"] for i in b["items"]}, {"README.md", "src", "old.txt"})
        self.assertIn("print('app')", self.c.json("GET", f"/api/code/sessions/{sid}/file?path=src/app.py")[1]["text"])
        self.assertNotIn(fake.token, str(d))
        # a sessão na nuvem lê o projeto sem IA, pelas regras
        self.c.json("POST", f"/api/code/sessions/{sid}/send", {"text": "leia src/app.py"})
        d = self.wait(sid)
        self.assertEqual(d["run"]["status"], "done", d["run"])
        self.assertIn("print('app')", d["run"]["plan"]["steps"][0]["summary"])
        self.c.json("PUT", "/api/settings", {"code": {"github": {"api": "", "token": None}, "github_mode": "auto"}})

    def test_android_cannot_run_commands_but_can_publish(self):
        names, missing = T.available({"mode": "ask", "vision": True, "git": False, "token": True, "repo": {"kind": "cloud", "owner": "o", "name": "r"}, "android": True, "editor": False})
        self.assertNotIn("run_command", names)
        self.assertNotIn("run_tests", names)
        self.assertIn("publish_changes", names)
        self.assertIn("github_run_workflow", names)      # no celular o CI do GitHub é quem roda os testes
        self.assertIn("github_ci", names)
        old = T.IS_ANDROID
        T.IS_ANDROID = True
        self.addCleanup(setattr, T, "IS_ANDROID", old)
        s, st = self.c.json("GET", "/api/code/status")
        self.assertTrue(st["android"])
        self.assertEqual(self.c.json("POST", "/api/code/sessions/cs_x/editor", {})[0], 409)


if __name__ == "__main__":
    unittest.main()
