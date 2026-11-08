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
        self.assertEqual(loads[0], {"diffusion_model_path": str(self.img / "qwen-image-2.1-Q4_K_M.gguf"), "vae_path": str(self.img / "qwen_image_vae.safetensors"), "llm_path": str(self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"),
                                    "offload_params_to_cpu": True, "diffusion_flash_attn": True})       # memória e atenção como na documentação da stable-diffusion.cpp
        self.assertEqual(runs[0]["cfg_scale"], 2.5)
        self.assertEqual((runs[0]["width"], runs[0]["height"]), (1024, 576))

    def test_the_vae_of_flux_and_z_image_is_never_used_for_qwen_image(self):
        from asta.providers.base import ProviderError

        (self.img / "ae.safetensors").write_bytes(b"flux-vae")          # fica na mesma pasta quando o Z-Image pré-instalado está instalado
        (self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf").write_bytes(b"t")
        mod, loads, _ = self.fake(fail=ValueError("NULL pointer access"))
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}), self.assertRaises(ProviderError) as cm:
            self.prov().image("x")
        self.assertEqual(loads[0], {"model_path": str(self.img / "qwen-image-2.1-Q4_K_M.gguf")})   # sem o VAE certo: não monta o carregamento com o VAE errado
        self.assertIn("VAE do Qwen-Image", str(cm.exception))
        self.assertIn("[[asta-support:", str(cm.exception))

    def test_a_null_pointer_is_retried_without_flash_attention_and_cpu_offload(self):
        from tests.test_canvas import PNG

        from asta.canvas import media as M

        M._SD_LITE.clear()

        (self.img / "qwen_image_vae.safetensors").write_bytes(b"v")
        (self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf").write_bytes(b"t")
        loads = []

        class Img:
            def save(self, buf, format="PNG"):
                buf.write(PNG)

        class SD:
            def __init__(self, **kw):
                self.kw = kw
                loads.append(kw)

            def generate_image(self, **kw):
                if self.kw.get("diffusion_flash_attn"):
                    raise ValueError("NULL pointer access")   # o backend não suporta flash attention
                return [Img()]

        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mock.MagicMock(StableDiffusion=SD)}):
            out = self.prov().image("x", size="512x512")
        self.assertEqual(len(out), 1)
        self.assertEqual(len(loads), 2)
        self.assertNotIn("diffusion_flash_attn", loads[1])
        self.assertNotIn("offload_params_to_cpu", loads[1])
        self.assertIn("llm_path", loads[1])   # os arquivos de apoio continuam
        from asta.canvas import media as M

        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mock.MagicMock(StableDiffusion=SD)}):
            self.prov().image("y", size="512x512")
        self.assertEqual(len(loads), 2)   # na próxima imagem já começa sem as opções: não recarrega o modelo à toa
        M._SD_LITE.clear()

    def test_without_a_log_reason_the_error_lists_the_support_files_that_were_loaded(self):
        from asta.providers.base import ProviderError

        (self.img / "qwen_image_vae.safetensors").write_bytes(b"v")
        (self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf").write_bytes(b"t")
        mod, _, runs = self.fake(fail=ValueError("NULL pointer access"))
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}), self.assertRaises(ProviderError) as cm:
            self.prov().image("x", size="512x512")
        self.assertIn("não registrou nenhum motivo", str(cm.exception))
        self.assertIn("qwen_image_vae.safetensors", str(cm.exception))

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
        self.assertIn("falhou na stable-diffusion.cpp", str(cm.exception))
        self.assertNotIn("Erro inesperado", str(cm.exception))

    def test_the_real_reason_from_the_library_log_is_shown_instead_of_just_null_pointer(self):
        from asta.canvas import media as M
        from asta.providers.base import ProviderError

        (self.img / "qwen_image_vae.safetensors").write_bytes(b"v")
        (self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf").write_bytes(b"t")
        M._SD_CB = None
        M._SD_LOG.clear()
        cbs = []
        mod, _, _ = self.fake(fail=ValueError("NULL pointer access"))
        mod.sd_log_callback = lambda f: f
        mod.sd_set_log_callback = lambda f, d: cbs.append(f)
        orig = mod.StableDiffusion

        class Noisy(orig):
            def generate_image(self, **kw):
                cbs[0](3, b"ggml_backend_cpu_buffer_type_alloc_buffer: failed to allocate buffer of size 12884901888\n", None)
                cbs[0](1, b"info line that is not an error\n", None)
                return super().generate_image(**kw)

        mod.StableDiffusion = Noisy
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}), self.assertRaises(ProviderError) as cm:
            self.prov().image("x")
        msg = str(cm.exception)
        self.assertIn("failed to allocate buffer", msg)
        self.assertNotIn("info line", msg)
        self.assertIn("falta de memória", msg)
        M._SD_CB = None

    def test_a_null_pointer_at_a_big_size_is_retried_once_smaller_and_the_log_callback_is_reinstalled(self):
        from asta.canvas import media as M

        mod, _, runs = self.fake()
        installs = []
        mod.sd_log_callback = lambda f: f
        mod.sd_set_log_callback = lambda f, d: installs.append(f)
        inner = mod.StableDiffusion
        calls = []

        class Flaky(inner):
            def generate_image(self, **kw):
                calls.append((kw["width"], kw["height"]))
                if len(calls) == 1:
                    raise ValueError("NULL pointer access")
                return super().generate_image(**kw)

        mod.StableDiffusion = Flaky
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}):
            out = self.prov().image("x", size="1280x720")
        self.assertEqual(len(out), 1)
        self.assertEqual(calls[0], (1024, 576))
        self.assertLess(calls[1][0], 1024)
        self.assertTrue(calls[1][0] % 16 == 0 and calls[1][1] % 16 == 0)
        self.assertGreaterEqual(len(installs), 2)   # reinstalado antes de cada tentativa
        M._SD_CB = None

    def test_gguf_edit_uses_init_image_or_ref_images_and_keeps_the_aspect(self):
        from asta.canvas import media as M
        from asta.canvas.media import ProviderError
        from tests.test_canvas import PNG

        seen = []

        class Img:
            def save(self, buf, format="PNG"):
                buf.write(PNG)

        class SD:
            def __init__(self, **kw):
                pass

            def generate_image(self, prompt="", width=0, height=0, seed=0, init_image=None, strength=0.0, ref_images=None, **kw):
                seen.append({"w": width, "h": height, "init": init_image, "strength": strength, "refs": ref_images})
                return [Img()]

        class Old:
            def __init__(self, **kw):
                pass

            def generate_image(self, prompt="", width=0, height=0, seed=0, **kw):
                return [Img()]

        mod = mock.MagicMock(StableDiffusion=SD)
        (self.img / "qwen-image-edit-Q4_K_M.gguf").write_bytes(b"g")
        prov = M._KINDS["gguf_local"]({"id": "gguf_local", "label": "g", "models_dir": str(self.tmp), "models": {"image": "qwen-image-edit-Q4_K_M.gguf"}, "needs_key": False})
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}):
            prov.image("x", size="1024x1024", refs=[(PNG, "image/png")])
        self.assertIsNotNone(seen[0]["refs"])
        self.assertIsNone(seen[0]["init"])
        # modelo comum: imagem → imagem
        M._LOCAL_CACHE.clear()
        prov2 = self.prov()
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}):
            prov2.image("x", size="1024x1024", refs=[(PNG, "image/png")])
        self.assertIsNotNone(seen[1]["init"])
        self.assertEqual(seen[1]["strength"], 0.75)
        # biblioteca antiga sem init_image: erro claro, não uma imagem que ignora a referência
        M._LOCAL_CACHE.clear()
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mock.MagicMock(StableDiffusion=Old)}), self.assertRaises(ProviderError) as cm:
            prov2.image("x", refs=[(PNG, "image/png")])
        self.assertIn("init_image", str(cm.exception))

    def test_image_sizes_are_multiples_of_16(self):
        (self.img / "meu-modelo-Q4_K_M.gguf").write_bytes(b"g")
        from asta.canvas import media as M

        mod, _, runs = self.fake()
        prov = M._KINDS["gguf_local"]({"id": "gguf_local", "label": "g", "models_dir": str(self.tmp), "models": {"image": "meu-modelo-Q4_K_M.gguf"}, "needs_key": False})
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}):
            prov.image("x", size="1536x1024")
        self.assertEqual((runs[0]["width"], runs[0]["height"]), (1024, 672))
        self.assertTrue(runs[0]["width"] % 16 == 0 and runs[0]["height"] % 16 == 0)

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
