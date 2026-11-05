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
    def test_manual_install_updates_tooling_asta_and_then_all_libraries(self):
        with mock.patch.object(cli, "_managed_app_dir", return_value=None):
            code, calls, out = run_cli(["update"])
        self.assertEqual(code, 0)
        self.assertEqual(calls[0][-3:], ["pip", "setuptools", "wheel"])  # derivados do Python: pip, setuptools e wheel
        self.assertEqual(calls[1][-1], cli.REPO_ZIP)
        self.assertIn("--upgrade", calls[1])
        self.assertEqual(calls[2][1:4], ["-m", "asta", "libs"])  # processo novo: lê as bibliotecas da versão recém-instalada
        self.assertIn("Pronto", out)
        self.assertIn("gerenciador de pacotes", out)  # explica que o Python do sistema não é gerenciado nesse caso

    def test_flags_that_keep_the_system_python_alone(self):
        with mock.patch.object(cli, "_managed_app_dir", return_value=Path("/x/app")), mock.patch.object(cli, "_update_with_installer") as inst:
            calls = run_cli(["update", "--core"])[1]
            self.assertEqual(len(calls), 2)  # pip+setuptools+wheel e ASTA; nada de bibliotecas
            calls = run_cli(["update", "--no-python", "--extras", "docs"])[1]
            self.assertEqual(calls[-1][-2:], ["--extras", "docs"])
            run_cli(["update"], env={"ASTA_PYTHON": "keep"})
            inst.assert_not_called()

    def test_official_install_runs_the_installer_that_updates_python_too(self):
        script = b"#!/bin/sh\necho instalador\n"
        seen = {}

        def fake_run(cmd, *a, **k):
            seen["cmd"], seen["env"], seen["script"] = cmd, k.get("env"), Path(cmd[1]).read_bytes()
            return mock.Mock(returncode=0)

        urlopen = mock.MagicMock()
        urlopen.return_value.__enter__.return_value.read.return_value = script
        out = io.StringIO()
        with mock.patch.object(cli, "_managed_app_dir", return_value=Path("/home/u/.asta/app")), mock.patch("urllib.request.urlopen", urlopen), \
                mock.patch.object(cli.subprocess, "run", side_effect=fake_run), mock.patch.object(cli.os, "name", "posix"), contextlib.redirect_stdout(out):
            code = cli.main(["update", "--extras", "docs,media"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["cmd"][0], "sh")
        self.assertEqual(seen["script"], script)
        self.assertTrue(urlopen.call_args[0][0].endswith("/main/install.sh"))
        self.assertEqual((seen["env"]["ASTA_APP_DIR"], seen["env"]["ASTA_EXTRAS"]), ("/home/u/.asta/app", "docs,media"))
        self.assertFalse(os.path.exists(seen["cmd"][1]))  # arquivo temporário apagado
        self.assertIn("Atualizando o Python", out.getvalue())

    def test_falls_back_when_the_installer_cannot_be_downloaded(self):
        with mock.patch.object(cli, "_managed_app_dir", return_value=Path("/home/u/.asta/app")), mock.patch("urllib.request.urlopen", side_effect=OSError("sem rede")):
            code, calls, out = run_cli(["update"])
        self.assertEqual(code, 0)
        self.assertEqual(calls[1][-1], cli.REPO_ZIP)
        self.assertIn("Não foi possível baixar o instalador", out)

    def test_library_failures_do_not_fail_the_update_but_asta_failure_does(self):
        with mock.patch.object(cli, "_managed_app_dir", return_value=None):
            self.assertEqual(run_cli(["update"], results={"llama": 1})[0], 0)
            code, calls, _ = run_cli(["update"], results={cli.REPO_ZIP: 3})
        self.assertEqual((code, len(calls)), (3, 2))  # sem ASTA novo, nem tenta as bibliotecas

    def test_managed_app_dir_only_for_the_official_layout(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp).resolve() / "app"
            (app / "venv").mkdir(parents=True)
            (Path(tmp) / ".venv").mkdir()
            with mock.patch.dict(os.environ, {"ASTA_APP_DIR": str(app)}):
                with mock.patch.object(cli.sys, "prefix", str(app / "venv")):
                    self.assertEqual(cli._managed_app_dir(), app)
                with mock.patch.object(cli.sys, "prefix", str(Path(tmp) / ".venv")):
                    self.assertIsNone(cli._managed_app_dir())  # ambiente de desenvolvimento / instalação manual


@unittest.skipUnless(sys.platform.startswith("linux") and os.path.exists("/bin/sh"), "instalador sh só em Linux")
class PythonInstallerTests(unittest.TestCase):
    """O install.sh instala/atualiza o Python pelo gerenciador de pacotes do sistema (simulado por comandos falsos no PATH)."""

    ROOT = Path(__file__).resolve().parent.parent

    def setUp(self):
        import shutil
        import tempfile

        self.tmp = Path(tempfile.mkdtemp(prefix="asta-inst-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for tool in ("uname", "mkdir", "rm", "ln", "id", "cat", "dirname", "env"):
            real = shutil.which(tool)
            if real:
                (self.bin / tool).symlink_to(real)
        self.log = self.tmp / "apt.log"
        (self.bin / "sudo").write_text('#!/bin/sh\nexec "$@"\n')
        (self.bin / "apt-get").write_text(f'#!/bin/sh\necho "$@" >> {self.log}\ncase "$1" in install) [ -e {self.bin}/python3 ] || ln -s {sys.executable} {self.bin}/python3;; esac\nexit 0\n')
        for f in ("sudo", "apt-get"):
            (self.bin / f).chmod(0o755)

    def with_python(self):
        (self.bin / "python3").symlink_to(sys.executable)

    def install(self, **env):
        import subprocess

        e = {"PATH": str(self.bin), "HOME": str(self.tmp / "home"), "ASTA_APP_DIR": str(self.tmp / "app"), "ASTA_BIN_DIR": str(self.tmp / "ubin"), "ASTA_STEP": "python",
             "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1", **env}
        (self.tmp / "home").mkdir(exist_ok=True)
        r = subprocess.run(["/bin/sh", str(self.ROOT / "install.sh")], capture_output=True, text=True, env=e, timeout=300)
        return r.returncode, r.stdout + r.stderr

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_missing_python_is_installed_with_its_venv_and_pip_packages(self):
        code, out = self.install()
        self.assertEqual(code, 0, out)
        self.assertIn("instalando", out)
        self.assertIn("install -y python3 python3-venv python3-pip", " ".join(self.calls()))
        self.assertTrue((self.tmp / "app" / "venv" / "bin" / "python").exists())
        self.assertIn("prontos", out)

    def test_existing_python_is_upgraded_by_default(self):
        self.with_python()
        code, out = self.install()
        self.assertEqual(code, 0, out)
        self.assertIn("Verificando atualizações do Python", out)
        self.assertTrue(any(c.startswith("install -y python3 python3-venv python3-pip") for c in self.calls()))

    def test_keep_mode_never_touches_the_package_manager(self):
        self.with_python()
        code, out = self.install(ASTA_PYTHON="keep")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.calls(), [])
        code, out = self.install(ASTA_PYTHON="keep", PATH=str(self.tmp / "vazio"))  # sem Python e sem permissão para instalar
        self.assertNotEqual(code, 0)
        self.assertIn("Python 3.9 ou superior não encontrado", out)

    @unittest.skipIf(sys.version_info < (3, 10), "precisa de um Python mais novo que o 3.9 simulado")
    def test_a_venv_built_with_an_older_python_is_recreated(self):
        self.with_python()
        old = self.tmp / "app" / "venv" / "bin"
        old.mkdir(parents=True)
        (old / "python").write_text("#!/bin/sh\necho 3.8\n")
        (old / "python").chmod(0o755)
        code, out = self.install(ASTA_PYTHON="keep")
        self.assertEqual(code, 0, out)
        self.assertIn("Recriando o ambiente", out)
        import subprocess

        ver = subprocess.run([str(self.tmp / "app" / "venv" / "bin" / "python"), "-c", "import sys; print(sys.version_info[:2] >= (3, 10))"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(ver, "True")

    def test_python_only_flag_stops_before_installing_asta(self):
        import subprocess

        self.with_python()
        r = subprocess.run(["/bin/sh", str(self.ROOT / "install.sh"), "--python-only"], capture_output=True, text=True,
                           env={"PATH": str(self.bin), "HOME": str(self.tmp / "home"), "ASTA_APP_DIR": str(self.tmp / "app"), "ASTA_PYTHON": "keep", "PIP_NO_INDEX": "1"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("prontos", r.stdout)
        self.assertNotIn("Baixando e instalando ASTA", r.stdout)


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
        # PowerShell 5.1: com ErrorActionPreference=Stop, o stderr de programas externos (mesmo com 2>$null) vira NativeCommandError
        self.assertNotRegex(ps, r"(?m)^\$ErrorActionPreference\s*=\s*'Stop'")
        self.assertIn("$ErrorActionPreference = 'Continue'", ps)
        # o comando `asta` precisa funcionar logo após instalar: PATH do usuário (aceitando Path vazio) e PATH deste terminal, antes das bibliotecas
        self.assertIn("if ($userPath)", ps)
        self.assertIn("$env:Path = $env:Path.TrimEnd(';')", ps)
        self.assertLess(ps.index("$env:Path = $env:Path.TrimEnd(';')"), ps.index("& $asta libs"))
        self.assertNotIn("$userPath.TrimEnd", ps)  # com Path vazio (null) isso falha em silêncio e o PATH nunca era configurado
        for needle in ("winget install --id Python.Python.3.12", "winget upgrade", "ASTA_PYTHON", "pip setuptools wheel", "Recriando o ambiente"):
            self.assertIn(needle, ps)  # Windows: instala/atualiza o Python pelo winget e as ferramentas dele
        for needle in ("apt-get", "dnf", "pacman", "brew", "ASTA_PYTHON", "pip setuptools wheel", "Recriando o ambiente"):
            self.assertIn(needle, sh)
        self.assertNotIn('SPEC="asta[$EXTRAS]"', sh)


if __name__ == "__main__":
    unittest.main()
