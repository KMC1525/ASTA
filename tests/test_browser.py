"""Interface no navegador (Chromium via Playwright): telas, hub, Canvas e Editor de vídeo. Pulado se Playwright/Chromium não existirem."""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from asta.server import make_server
from asta.storage import Store

ROOT = Path(__file__).resolve().parent.parent
BROWSER = Path(__file__).resolve().parent / "browser"


def _playwright_ok() -> bool:
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, text=True, cwd=str(ROOT))
    return r.returncode == 0


@unittest.skipUnless(_playwright_ok(), "Playwright (Node) não disponível")
class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="asta-browser-"))
        cls.httpd, _ = make_server("127.0.0.1", 0, Store(cls.tmp))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_script(self, name: str) -> None:
        r = subprocess.run(["node", str(BROWSER / name)], capture_output=True, text=True, timeout=300, env={**os.environ, "ASTA_PORT": str(self.port)})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        failed = [k for k, v in out["checks"].items() if not v]
        self.assertEqual(out["errors"], [])
        self.assertEqual(failed, [], f"verificações que falharam: {failed}")
        self.assertGreater(len(out["checks"]), 3)

    def test_01_every_screen_loads_on_desktop_and_mobile(self):
        self.run_script("smoke_ui.js")

    def test_02_hub_generates_game_and_avatar_and_opens_canvas(self):
        self.run_script("hub_ui.js")

    def test_03_canvas_editor_and_video_timeline(self):
        self.run_script("canvas_ui.js")

    def test_04_local_models_quantization_picker(self):
        from unittest import mock

        from asta import hf
        from tests.test_hf import FakeHF

        fake = FakeHF()
        try:
            with mock.patch.object(hf, "HF", fake.url):
                self.run_script("models_ui.js")
        finally:
            fake.close()

    def test_05_local_canvas_models_ask_for_the_precision_first(self):
        import sys
        from unittest import mock

        from tests.test_canvas import FakeHub

        with mock.patch.dict(sys.modules, {"huggingface_hub": FakeHub(self.tmp).module}):
            self.run_script("local_models_ui.js")


if __name__ == "__main__":
    unittest.main()
