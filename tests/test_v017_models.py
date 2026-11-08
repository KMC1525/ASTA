"""v0.17.3 — seletor de modelos dos nós do Canvas: o que está instalado neste computador (GGUF e Hugging Face local)."""
import json
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


class GGUFApiCompatTests(unittest.TestCase):
    """v0.17.5 — a stable-diffusion-cpp-python nova gera com `generate_image`; a antiga, com `txt2img` (erro «object has no attribute 'txt2img'»)."""

    def run_with(self, sd_cls):
        import tempfile

        from asta.canvas import media as M
        from tests.test_canvas import PNG

        tmp = Path(tempfile.mkdtemp())
        (tmp / "image").mkdir()
        (tmp / "image" / "z-image-Q4_K_M.gguf").write_bytes(b"g")
        M._LOCAL_CACHE.clear()

        class Img:
            def save(self, buf, format="PNG"):
                buf.write(PNG)

        runs = []
        sd = sd_cls(Img, runs)
        mod = mock.MagicMock(StableDiffusion=lambda **kw: sd)
        prov = M._KINDS["gguf_local"]({"id": "gguf_local", "label": "g", "models_dir": str(tmp), "models": {"image": "z-image-Q4_K_M.gguf"}, "needs_key": False})
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}):
            return prov.image("um gato", size="1280x720", seed=3), runs

    def test_new_api_generate_image(self):
        class New:
            def __init__(self, img, runs):
                self.img, self.runs = img, runs

            def generate_image(self, **kw):
                self.runs.append(kw)
                return [self.img()]

        out, runs = self.run_with(New)
        self.assertEqual((out[0].mime, runs[0]["width"], runs[0]["height"], runs[0]["seed"]), ("image/png", 1024, 576, 3))

    def test_old_api_txt2img_and_a_clear_error_when_neither_exists(self):
        class Old:
            def __init__(self, img, runs):
                self.img, self.runs = img, runs

            def txt2img(self, **kw):
                self.runs.append(kw)
                return self.img()   # uma imagem só, sem lista, também é aceita

        out, runs = self.run_with(Old)
        self.assertEqual(out[0].mime, "image/png")

        class Neither:
            def __init__(self, img, runs):
                pass

        from asta.providers.base import ProviderError

        with self.assertRaises(ProviderError) as cm:
            self.run_with(Neither)
        self.assertIn("generate_image", str(cm.exception))


class QwenImageGGUFTests(unittest.TestCase):
    """v0.17.6 — «NULL pointer access»: um GGUF só de difusão (Qwen-Image, FLUX…) carregado como arquivo único não sobe; o ASTA acha os arquivos de apoio ao lado."""

    def setUp(self):
        import tempfile

        from asta.canvas import media as M

        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "image").mkdir()
        self.img = self.tmp / "image"
        (self.img / "qwen-image-2.1-Q4_K_M.gguf").write_bytes(b"g")
        M._LOCAL_CACHE.clear()

    def prov(self):
        from asta.canvas import media as M

        return M._KINDS["gguf_local"]({"id": "gguf_local", "label": "g", "models_dir": str(self.tmp), "models": {"image": "qwen-image-2.1-Q4_K_M.gguf"}, "needs_key": False})

    def fake(self, fail=None):
        from tests.test_canvas import PNG

        loads, runs = [], []

        class Img:
            def save(self, buf, format="PNG"):
                buf.write(PNG)

        class SD:
            def __init__(self, **kw):
                loads.append(kw)

            def generate_image(self, **kw):
                if fail:
                    raise fail
                runs.append(kw)
                return [Img()]

        return mock.MagicMock(StableDiffusion=SD), loads, runs

    def test_companions_next_to_the_model_are_found_and_loaded(self):
        (self.img / "qwen_image_vae.safetensors").write_bytes(b"v")
        (self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf").write_bytes(b"t")
        mod, loads, runs = self.fake()
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}):
            out = self.prov().image("um gato", size="1280x720")
        self.assertEqual(out[0].mime, "image/png")
        self.assertEqual(loads[0], {"diffusion_model_path": str(self.img / "qwen-image-2.1-Q4_K_M.gguf"), "vae_path": str(self.img / "qwen_image_vae.safetensors"), "llm_path": str(self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf")})
        self.assertEqual(runs[0]["cfg_scale"], 2.5)

    def test_missing_companions_fall_back_to_the_single_file_and_the_error_says_what_to_download(self):
        from asta.providers.base import ProviderError

        mod, loads, _ = self.fake(fail=ValueError("NULL pointer access"))
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}), self.assertRaises(ProviderError) as cm:
            self.prov().image("x")
        msg = str(cm.exception)
        self.assertEqual(loads[0], {"model_path": str(self.img / "qwen-image-2.1-Q4_K_M.gguf")})   # sem os apoios: carrega como arquivo único (como antes)
        self.assertIn("Qwen2.5-VL", msg)
        self.assertIn("VAE do Qwen-Image", msg)
        self.assertIn("[[asta-support:qwen-image-2.1-Q4_K_M.gguf]]", msg)                  # a tela troca isto pelo botão «Baixar os arquivos de apoio»

    def test_a_null_pointer_from_the_library_becomes_a_clear_message(self):
        from asta.providers.base import ProviderError

        (self.img / "qwen_image_vae.safetensors").write_bytes(b"v")
        (self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf").write_bytes(b"t")
        mod, _, _ = self.fake(fail=ValueError("NULL pointer access"))
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}), self.assertRaises(ProviderError) as cm:
            self.prov().image("x")
        self.assertIn("não carregou", str(cm.exception))
        self.assertNotIn("Erro inesperado", str(cm.exception))

    def test_other_models_keep_loading_as_a_single_file_and_support_files_are_not_listed_as_models(self):
        from asta.canvas import installed as INST

        (self.img / "meu-modelo-Q4_K_M.gguf").write_bytes(b"g")
        (self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf").write_bytes(b"t")
        (self.img / "t5xxl_fp16.gguf").write_bytes(b"t")
        mod, loads, _ = self.fake()
        from asta.canvas import media as M

        prov = M._KINDS["gguf_local"]({"id": "gguf_local", "label": "g", "models_dir": str(self.tmp), "models": {"image": "meu-modelo-Q4_K_M.gguf"}, "needs_key": False})
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}):
            prov.image("x")
        self.assertEqual(loads[0], {"model_path": str(self.img / "meu-modelo-Q4_K_M.gguf")})
        names = {i["model"] for i in INST.installed({}, self.tmp, "image") if i["provider"] == "gguf_local"}
        self.assertEqual(names, {"qwen-image-2.1-Q4_K_M.gguf", "meu-modelo-Q4_K_M.gguf"})


class SupportFilesTests(ServerCase):
    """v0.17.7 — baixar os arquivos de apoio (VAE, codificador de texto) de um GGUF de difusão, a pedido."""

    def setUp(self):
        self.img = self.store.models_dir / "image"
        self.img.mkdir(parents=True, exist_ok=True)
        for f in list(self.img.iterdir()):
            f.unlink()
        (self.img / "qwen-image-2.1-Q4_K_M.gguf").write_bytes(b"g")

    def fake_download(self, calls):
        def fake(repo, files, dest, token="", sizes=None, progress=None, cancelled=lambda: False, any_file=False):
            calls.append((repo, files[0], any_file))
            (Path(dest) / Path(files[0]).name).write_bytes(b"x")
            if progress:
                progress(10, 10)
            return Path(dest) / Path(files[0]).name

        return fake

    def test_missing_lists_what_to_download_and_find_companions_matches_names(self):
        from asta.canvas import support

        m = support.missing(self.img, "qwen-image-2.1-Q4_K_M.gguf")
        self.assertEqual((m["family"], [x["key"] for x in m["missing"]]), ("qwen-image", ["vae_path", "llm_path"]))
        self.assertGreater(m["approx_gb"], 4)
        self.assertEqual(support.missing(self.img, "meu-modelo.gguf")["family"], "")
        (self.img / "qwen_image_vae.safetensors").write_bytes(b"v")
        self.assertEqual([x["key"] for x in support.missing(self.img, "qwen-image-2.1-Q4_K_M.gguf")["missing"]], ["llm_path"])

    def test_route_downloads_only_what_is_missing_and_then_refuses(self):
        calls = []
        with mock.patch("asta.hf.download_many", side_effect=self.fake_download(calls)):
            s, r = self.c.json("POST", "/api/media/support/download", {"model": "qwen-image-2.1-Q4_K_M.gguf"})
            self.assertEqual(s, 200, r)
            ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        done = [e for e in ev if e["type"] == "done"]
        self.assertEqual(len(done), 1, ev[-3:])
        self.assertEqual(sorted(done[0]["files"]), ["Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf", "qwen_image_vae.safetensors"])
        self.assertEqual({c[0] for c in calls}, {"Comfy-Org/Qwen-Image_ComfyUI", "unsloth/Qwen2.5-VL-7B-Instruct-GGUF"})
        self.assertTrue(all(c[2] for c in calls))                                      # arquivos que não são .gguf também (any_file)
        self.assertTrue((self.img / "qwen_image_vae.safetensors").is_file())
        s, r = self.c.json("POST", "/api/media/support/download", {"model": "qwen-image-2.1-Q4_K_M.gguf"})
        self.assertEqual(s, 400)                                                       # agora está tudo lá
        self.assertIn("já estão", json.dumps(r, ensure_ascii=False))

    def test_route_validation(self):
        self.assertEqual(self.c.json("POST", "/api/media/support/download", {"model": "../x.gguf"})[0], 400)
        self.assertEqual(self.c.json("POST", "/api/media/support/download", {"model": "meu-modelo.gguf"})[0], 400)
        self.assertEqual(self.c.json("POST", "/api/media/support/download", {})[0], 400)


if __name__ == "__main__":
    unittest.main()
