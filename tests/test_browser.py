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
        cls.store_dir = cls.tmp
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

    def test_06_preinstalled_models_card_installs_with_one_click(self):
        from unittest import mock

        from asta import hf, preinstalled
        from tests.test_preinstalled import FakeHub

        hub = FakeHub()
        try:
            with mock.patch.object(hf, "HF", hub.url), mock.patch("asta.hf.shutil.disk_usage", return_value=mock.Mock(free=10 ** 13)), mock.patch.object(preinstalled, "_lib", return_value=False):
                self.run_script("preinstalled_ui.js")
        finally:
            hub.close()
            (self.store_dir / "models" / "Qwen3.8-2B-Q8_0.gguf").unlink(missing_ok=True)

    def test_07_library_lists_local_models_and_deletes_several_at_once(self):
        models = self.store_dir / "models"
        (models / "image").mkdir(parents=True, exist_ok=True)
        for rel in ("Qwen3.8-2B-Q8_0.gguf", "outro-Q4_K_M.gguf", "image/z-image-Q4_K_M.gguf", "image/Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "image/ae.safetensors"):
            (models / rel).write_bytes(b"x" * 2048)
        self.run_script("library_ui.js")
        self.assertTrue((models / "Qwen3.8-2B-Q8_0.gguf").exists())
        self.assertFalse((models / "outro-Q4_K_M.gguf").exists())
        for name in ("z-image-Q4_K_M.gguf", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "ae.safetensors"):
            self.assertFalse((models / "image" / name).exists(), name)  # o Z-Image levou o VAE e o codificador de texto junto
        (models / "Qwen3.8-2B-Q8_0.gguf").unlink()

    def test_08_a_screen_whose_files_fail_to_load_recovers_or_explains(self):
        self.run_script("resilience_ui.js")

    def test_09_avatar_editor_generates_the_system_prompt_and_real_people_stay_sfw(self):
        self.run_script("avatar_prompt_ui.js")


if __name__ == "__main__":
    unittest.main()
