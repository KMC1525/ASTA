"""Code: pastas vazias (ou que ainda não existem) viram um projeto novo para escrever código depois; o endereço «file:///…» do gerenciador de arquivos vale."""
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.code import CodeError, guard, langs  # noqa: E402
from tests.test_code_team import Scripted, TeamCase, act, fin, per_step, plan, step  # noqa: E402


class GuardTests(TeamCase):
    def test_file_uri_becomes_a_plain_path(self):
        self.assertEqual(guard.from_uri("file:///home/voce/Meu%20Projeto"), "/home/voce/Meu Projeto")
        self.assertEqual(guard.from_uri("file:///C:/projetos/app"), "C:/projetos/app")
        self.assertEqual(guard.from_uri("  /home/voce/x  "), "/home/voce/x")
        self.assertEqual(guard.from_uri('"file://localhost/tmp/x"'), "/tmp/x")

    def test_an_empty_existing_folder_is_valid_and_missing_ones_need_create(self):
        empty = self.home / "vazia"
        empty.mkdir()
        self.assertEqual(guard.check_root(str(empty)), empty.resolve())
        self.assertTrue(langs.is_empty(empty))
        (empty / ".git").mkdir()
        self.assertTrue(langs.is_empty(empty))   # só o .git: continua sem código
        (empty / "a.py").write_text("x = 1\n")
        self.assertFalse(langs.is_empty(empty))
        new = self.home / "a" / "b" / "nova"
        with self.assertRaises(guard.Blocked) as cm:
            guard.check_root(str(new))
        self.assertIn("Criar a pasta", str(cm.exception))
        self.assertFalse(new.exists())
        self.assertEqual(guard.check_root(str(new), create=True), new.resolve())
        self.assertTrue(new.is_dir())

    def test_create_still_obeys_the_fixed_limits(self):
        for bad in (str(self.home), "/", "/etc/asta-novo", str(self.home / ".ssh" / "x")):
            with self.assertRaises(guard.Blocked, msg=bad):
                guard.check_root(bad, create=True)
        self.assertFalse((self.home / ".ssh" / "x").exists())
        f = self.home / "arquivo.txt"
        f.write_text("oi")
        with self.assertRaises(guard.Blocked):
            guard.check_root(str(f), create=True)
        with self.assertRaises(guard.Blocked):
            guard.check_root(str(f / "sub"), create=True)


class SessionTests(TeamCase):
    def test_session_on_a_new_folder_via_file_uri_builds_the_project_from_scratch(self):
        dest = self.home / "meu app"
        seen = {}

        def planner(p, s):
            seen["project"] = p["project"]
            return plan(step("s1", "Criar o projeto", files=["main.py"]))

        llm = Scripted(planner=planner, worker=per_step(s1=[act("write_file", path="main.py", content="print('oi')\n"), fin("main.py criado", files=["main.py"])]))
        m = self.manager(llm, mode="full", agents=1)
        s = m.create_session({"workspace": {"type": "local", "path": "file://" + str(dest).replace(" ", "%20"), "create": True}})
        self.assertTrue(dest.is_dir())
        self.assertEqual(s["workspace"]["path"], str(dest.resolve()))
        m.send(s["id"], "crie um programa que diz oi")
        d = self.wait(m, s["id"])
        self.assertTrue(seen["project"]["empty"])
        self.assertEqual((dest / "main.py").read_text(), "print('oi')\n")
        self.assertIn(d["run"]["status"], ("done", "partial"))

    def test_without_create_a_missing_folder_is_an_error_that_explains_the_option(self):
        m = self.manager(Scripted())
        with self.assertRaises(CodeError) as cm:
            m.create_session({"workspace": {"type": "local", "path": str(self.home / "nao-existe")}})
        self.assertEqual(cm.exception.status, 400)
        self.assertIn("Criar a pasta", cm.exception.message)
        self.assertFalse((self.home / "nao-existe").exists())

    def test_an_empty_existing_folder_works_without_create(self):
        empty = self.home / "vazia2"
        empty.mkdir()
        m = self.manager(Scripted())
        self.assertEqual(m.create_session({"workspace": {"type": "local", "path": str(empty)}})["workspace"]["label"], "vazia2")

    def test_planner_prompt_and_core_explain_empty_projects(self):
        base = Path(__file__).resolve().parent.parent / "asta" / "code" / "prompts"
        self.assertIn("project.empty", (base / "planner.md").read_text())
        self.assertIn("Empty folder = new project", (base / "core.md").read_text())


if __name__ == "__main__":
    unittest.main()
