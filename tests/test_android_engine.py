"""v0.14 — o motor do app Android (ASTA dentro do aparelho): sobe sem computador, só aceita quem tem o cookie do app, e o projeto Android sai pronto pelo patcher."""
import http.client
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
OVERLAY = ROOT / "mobile-app" / "android-overlay"
sys.path.insert(0, str(ROOT))


def load_engine():
    spec = importlib.util.spec_from_file_location("asta_android", OVERLAY / "python" / "asta_android.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get(port, path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path, headers=headers or {})
    r = conn.getresponse()
    body = r.read()
    out = (r.status, dict(r.getheaders()), body)
    conn.close()
    return out


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="asta-android-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        patcher = mock.patch.dict(os.environ, {}, clear=False)   # o motor mexe no ambiente do processo: restaura no fim
        patcher.start()
        self.addCleanup(patcher.stop)
        self.eng = load_engine()
        self.addCleanup(self.eng.stop)

    def test_the_engine_starts_without_a_computer_and_serves_the_ui(self):
        pair = self.eng.start(str(self.tmp / "files"), "")
        self.assertRegex(pair, r"^http://127\.0\.0\.1:\d+/api/mobile/pair\?code=[\w-]{20,}$")
        port = int(pair.split(":")[2].split("/")[0])
        self.assertTrue((self.tmp / "files" / "asta").is_dir())   # dados na pasta privada do app
        self.assertEqual(self.eng.start(str(self.tmp / "files"), ""), pair)   # chamar de novo (a activity recriada) devolve o mesmo motor
        st, hdrs, _ = get(port, pair.split(str(port), 1)[1])
        self.assertEqual(st, 302)
        cookie = hdrs["Set-Cookie"].split(";")[0]
        self.assertTrue(cookie.startswith("asta_pair="))
        st, _, body = get(port, "/api/version", {"Cookie": cookie})
        self.assertEqual(st, 200)
        self.assertIn(b"version", body)
        st, _, body = get(port, "/", {"Cookie": cookie})
        self.assertEqual(st, 200)
        self.assertIn(b"<html", body.lower())

    def test_other_apps_on_the_phone_cannot_use_the_loopback_server(self):
        pair = self.eng.start(str(self.tmp / "files"), "")
        port = int(pair.split(":")[2].split("/")[0])
        for path in ("/api/version", "/api/chats", "/api/settings", "/"):
            st, _, _ = get(port, path)   # sem o cookie do app: nem o endereço local entra
            self.assertEqual(st, 401, path)
        st, _, _ = get(port, "/api/mobile/pair?code=errado")
        self.assertEqual(st, 403)
        st, _, _ = get(port, "/api/version", {"Cookie": "asta_pair=errado"})
        self.assertEqual(st, 401)

    def test_ffmpeg_shipped_as_native_libraries_is_exposed_on_the_path(self):
        libs = self.tmp / "nativelibs"
        libs.mkdir()
        (libs / "libffmpeg.so").write_bytes(b"\x7fELF")
        (libs / "libffprobe.so").write_bytes(b"\x7fELF")
        self.eng.start(str(self.tmp / "files"), str(libs))
        bindir = self.tmp / "files" / "bin"
        self.assertTrue((bindir / "ffmpeg").is_symlink() and (bindir / "ffprobe").is_symlink())
        self.assertTrue(os.environ["PATH"].startswith(str(bindir)))


class StrictModeTests(unittest.TestCase):
    def test_strict_loopback_is_off_by_default_so_the_desktop_is_unchanged(self):
        from asta.mobile import Mobile

        with mock.patch.dict(os.environ, {"ASTA_STRICT_LOOPBACK": ""}):
            m = Mobile(Path(tempfile.mkdtemp()), "127.0.0.1")
            self.assertFalse(m.strict)
            self.assertTrue(m.allowed("127.0.0.1", {}, "/api/chats"))
        with mock.patch.dict(os.environ, {"ASTA_STRICT_LOOPBACK": "1"}):
            m = Mobile(Path(tempfile.mkdtemp()), "127.0.0.1")
            self.assertTrue(m.strict)
            self.assertFalse(m.allowed("127.0.0.1", {}, "/api/chats"))
            self.assertTrue(m.allowed("127.0.0.1", {}, "/api/mobile/pair"))


class PatcherTests(unittest.TestCase):
    """O patcher prepara o projeto que o Capacitor gera (Capacitor 6): Chaquopy, Python do ASTA, MainActivity e manifest. Idempotente."""

    def make_project(self, root: Path):
        (root / "android" / "app" / "src" / "main").mkdir(parents=True)
        (root / "android" / "build.gradle").write_text("buildscript {\n    repositories {\n        google()\n        mavenCentral()\n    }\n    dependencies {\n        classpath 'com.android.tools.build:gradle:8.2.1'\n    }\n}\n"
                                                         "allprojects {\n    repositories {\n        google()\n        mavenCentral()\n    }\n}\n")
        (root / "android" / "variables.gradle").write_text("ext {\n    minSdkVersion = 22\n    compileSdkVersion = 34\n}\n")
        (root / "android" / "app" / "build.gradle").write_text("apply plugin: 'com.android.application'\n\nandroid {\n    defaultConfig {\n        applicationId \"org.asta.mobile\"\n    }\n}\n")
        (root / "android" / "app" / "src" / "main" / "AndroidManifest.xml").write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n    <application android:label="ASTA">\n    </application>\n</manifest>\n')
        shutil.copytree(OVERLAY, root / "android-overlay")

    def test_patch_is_complete_and_idempotent(self):
        tmp = Path(tempfile.mkdtemp(prefix="asta-patch-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.make_project(tmp)
        spec = importlib.util.spec_from_file_location("patch_android", OVERLAY / "patch_android.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for _ in range(2):
            self.assertEqual(mod.main(["patch_android.py", str(tmp), str(ROOT)]), 0)
        app = (tmp / "android" / "app" / "build.gradle").read_text()
        self.assertEqual(app.count("com.chaquo.python"), 1)
        self.assertIn("arm64-v8a", app)
        self.assertEqual((tmp / "android" / "build.gradle").read_text().count("com.chaquo.python:gradle"), 1)
        self.assertIn("minSdkVersion = 24", (tmp / "android" / "variables.gradle").read_text())
        man = (tmp / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text()
        self.assertEqual(man.count("usesCleartextTraffic"), 1)
        self.assertEqual(man.count("android.permission.INTERNET"), 1)
        py = tmp / "android" / "app" / "src" / "main" / "python"
        self.assertTrue((py / "asta_android.py").is_file() and (py / "asta" / "server.py").is_file())
        self.assertFalse((py / "asta" / "native" / "src").exists() or (py / "asta" / "native" / "target").exists())
        self.assertIn("addJavascriptInterface", (tmp / "android" / "app" / "src" / "main" / "java" / "org" / "asta" / "mobile" / "MainActivity.java").read_text())

    def test_patch_fails_loudly_on_an_unexpected_project(self):
        tmp = Path(tempfile.mkdtemp(prefix="asta-patch-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "android" / "app").mkdir(parents=True)
        shutil.copytree(OVERLAY, tmp / "android-overlay")
        spec = importlib.util.spec_from_file_location("patch_android", OVERLAY / "patch_android.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with self.assertRaises(SystemExit):
            mod.main(["patch_android.py", str(tmp), str(ROOT)])


if __name__ == "__main__":
    unittest.main()
