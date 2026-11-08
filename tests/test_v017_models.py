"""v0.17.3 — seletor de modelos dos nós do Canvas: o que está instalado neste computador (GGUF e Hugging Face local)."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.canvas import installed as INST  # noqa: E402
from asta.canvas.localmodels import MARKER  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402


def fake_hf_cache(root: Path, models):
    for repo, prec in models:
        snap = root / ("models--" + repo.replace("/", "--")) / "snapshots" / "abc123"
        snap.mkdir(parents=True, exist_ok=True)
        if prec:
            (snap / MARKER).write_text(prec, encoding="utf-8")


class InstalledTests(ServerCase):
    def setUp(self):
        d = self.store.models_dir
        for kind, name in (("image", "z-image-Q4_K_M.gguf"), ("image", "flux-Q8_0.gguf"), ("video", "wan-Q4_0.gguf")):
            (d / kind).mkdir(parents=True, exist_ok=True)
            (d / kind / name).write_bytes(b"GGUF" * 10)
        (d / "texto-Q4.gguf").write_bytes(b"GGUF")
        self.cache = self.tmp / "hfcache"
        fake_hf_cache(self.cache, [("stabilityai/sd-turbo", "fp16"), ("acme/outro-modelo", "fp32"), ("acme/sem-marcador", None)])
        self.env = mock.patch.dict(os.environ, {"HF_HUB_CACHE": str(self.cache)})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_image_lists_gguf_files_and_downloaded_hf_models(self):
        s, r = self.c.json("GET", "/api/media/installed?cap=image")
        self.assertEqual(s, 200, r)
        by = {(i["provider"], i["model"]): i for i in r["items"]}
        self.assertIn(("gguf_local", "z-image-Q4_K_M.gguf"), by)
        self.assertEqual(by[("gguf_local", "z-image-Q4_K_M.gguf")]["detail"], "Q4_K_M · GGUF")
        self.assertIn(("gguf_local", "flux-Q8_0.gguf"), by)
        self.assertNotIn(("gguf_local", "wan-Q4_0.gguf"), by)                         # o GGUF de vídeo não aparece na imagem
        self.assertNotIn(("gguf_local", "texto-Q4.gguf"), by)                         # nem os de texto (são da conversa)
        self.assertTrue(by[("local_hf", "stabilityai/sd-turbo")]["match"])            # é o modelo sugerido de imagem
        self.assertIn("fp16", by[("local_hf", "stabilityai/sd-turbo")]["detail"])
        self.assertIn(("local_hf", "acme/outro-modelo"), by)
        self.assertFalse(by[("local_hf", "acme/outro-modelo")]["match"])
        self.assertNotIn(("local_hf", "acme/sem-marcador"), by)                       # sem o marcador do ASTA: não foi baixado por ele

    def test_other_types(self):
        v = {i["model"] for i in self.c.json("GET", "/api/media/installed?cap=video")[1]["items"] if i["provider"] == "gguf_local"}
        self.assertEqual(v, {"wan-Q4_0.gguf"})
        so = self.c.json("GET", "/api/media/installed?cap=sound")[1]["items"]
        self.assertTrue(so and all(i["provider"] == "local_hf" for i in so))           # som: só o Hugging Face local (não há GGUF de som)
        self.assertEqual(self.c.json("GET", "/api/media/installed?cap=nada")[0], 400)

    def test_empty_cache_and_missing_folders_are_fine(self):
        with mock.patch.dict(os.environ, {"HF_HUB_CACHE": str(self.tmp / "nao-existe")}):
            r = self.c.json("GET", "/api/media/installed?cap=voice")[1]
        self.assertEqual(r["items"], [])
        self.assertEqual(INST.downloaded_hf_models.__name__, "downloaded_hf_models")


if __name__ == "__main__":
    unittest.main()
