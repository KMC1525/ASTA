"""Linha de comando: instalar/atualizar o ASTA e todas as bibliotecas dele (asta libs / asta update)."""
import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import cli  # noqa: E402

REQUIRES = [
    'pypdf>=4.0; extra == "docs"', 'torch; extra == "media"', 'diffusers>=0.30; extra == "media"', 'llama-cpp-python>=0.2.90; extra == "local"',
    'pypdf>=4.0; extra == "all"', 'torch; extra == "all"',
]


def run_cli(argv, env=None, results=None):
    """Executa `asta ...` simulando o pip. `results`: {palavra do requisito: código de saída}. Devolve (código, comandos, saída)."""
    calls, results = [], results or {}

    def fake_run(cmd, *a, **k):
        calls.append(cmd)
        code = next((c for word, c in results.items() if any(word in part for part in cmd)), 0)
        return mock.Mock(returncode=code)

    out = io.StringIO()
    with mock.patch("importlib.metadata.requires", return_value=REQUIRES), mock.patch.object(cli.subprocess, "run", side_effect=fake_run), \
            mock.patch.dict(os.environ, env or {}, clear=False), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        if not env or "ASTA_EXTRAS" not in env:
            os.environ.pop("ASTA_EXTRAS", None)
        code = cli.main(argv)
    return code, calls, out.getvalue()


def pip_installs(calls):
    return [c for c in calls if "pip" in c and "install" in c]


class LibsTests(unittest.TestCase):
    def test_requirements_come_from_the_installed_metadata_per_extra(self):
        with mock.patch("importlib.metadata.requires", return_value=REQUIRES):
            self.assertEqual(cli._lib_requirements("media"), ["torch", "diffusers>=0.30"])
            self.assertEqual(cli._lib_requirements("docs"), ["pypdf>=4.0"])
            self.assertEqual(cli._lib_requirements("nada"), [])

    def test_default_installs_and_upgrades_every_library(self):
        code, calls, out = run_cli(["libs"])
        self.assertEqual(code, 0)
        installs = pip_installs(calls)
        self.assertEqual(len(installs), 3)  # docs, media e local, nessa ordem (da mais leve à mais pesada)
        flat = [" ".join(c) for c in installs]
        self.assertIn("pypdf>=4.0", flat[0])
        self.assertIn("torch diffusers>=0.30", flat[1])
        self.assertIn("llama-cpp-python>=0.2.90", flat[2])
        for c in installs:
            self.assertIn("--upgrade", c)
            self.assertEqual(c[c.index("--upgrade-strategy") + 1], "eager")  # atualiza também as dependências das bibliotecas
        self.assertIn("Bibliotecas atualizadas: docs, media, local", out)

    def test_one_failing_library_does_not_block_the_others(self):
        code, calls, out = run_cli(["libs"], results={"llama-cpp-python": 1})
        self.assertEqual(code, 1)
        self.assertEqual(len(pip_installs(calls)), 3)
        self.assertIn("com falha: local", out)
        self.assertIn("asta libs --extras local", out)

    def test_choosing_libraries_and_the_environment_variable(self):
        self.assertEqual(len(pip_installs(run_cli(["libs", "--extras", "docs,media"])[1])), 2)
        self.assertEqual(len(pip_installs(run_cli(["libs"], env={"ASTA_EXTRAS": "docs"})[1])), 1)
        code, calls, out = run_cli(["libs", "--extras", "none"])
        self.assertEqual((code, pip_installs(calls)), (0, []))
        code, calls, out = run_cli(["libs"], env={"ASTA_EXTRAS": "none"})
        self.assertEqual(pip_installs(calls), [])
        code, calls, out = run_cli(["libs", "--extras", "docs,xyz"])
        self.assertEqual((code, calls), (2, []))
        self.assertIn("xyz", out)


class UpdateTests(unittest.TestCase):
    def test_update_upgrades_asta_and_then_all_libraries_in_a_fresh_process(self):
        code, calls, out = run_cli(["update"])
        self.assertEqual(code, 0)
        self.assertEqual(calls[0][-1], cli.REPO_ZIP)
        self.assertIn("--upgrade", calls[0])
        self.assertEqual(calls[1][1:4], ["-m", "asta", "libs"])  # processo novo: lê as bibliotecas da versão recém-instalada
        self.assertIn("Pronto", out)

    def test_update_flags(self):
        calls = run_cli(["update", "--core"])[1]
        self.assertEqual(len(calls), 1)
        calls = run_cli(["update", "--extras", "docs"])[1]
        self.assertEqual(calls[1][-2:], ["--extras", "docs"])

    def test_library_failures_do_not_fail_the_update_but_asta_failure_does(self):
        self.assertEqual(run_cli(["update"], results={"llama": 1})[0], 0)  # simulado: a chamada de libs é um processo à parte
        code, calls, _ = run_cli(["update"], results={cli.REPO_ZIP: 3})
        self.assertEqual((code, len(calls)), (3, 1))  # sem ASTA novo, nem tenta as bibliotecas


class InstallerTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent

    def test_installers_install_libraries_by_default_and_never_abort_for_them(self):
        sh = (self.ROOT / "install.sh").read_text(encoding="utf-8")
        ps = (self.ROOT / "install.ps1").read_text(encoding="utf-8")
        for src in (sh, ps):
            self.assertIn("asta libs" if src is sh else "libs", src)
            self.assertIn("none", src)  # dá para pular com ASTA_EXTRAS=none
        self.assertIn("LIBS_FAILED", sh)  # falha de biblioteca = aviso
        self.assertIn("$libsFailed", ps)
        self.assertNotIn('SPEC="asta[$EXTRAS]"', sh)


if __name__ == "__main__":
    unittest.main()
