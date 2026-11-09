"""v0.17.3 — seletor de modelos dos nós do Canvas: o que está instalado neste computador (GGUF e Hugging Face local)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.canvas import installed as INST  # noqa: E402
from asta.canvas.localmodels import MARKER  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402


def write_gguf(path: Path, names):
    """Um GGUF mínimo (só o cabeçalho e as informações dos tensores) para testar a leitura dos nomes."""
    import struct

    def string(t):
        b = t.encode()
        return struct.pack("<Q", len(b)) + b

    out = b"GGUF" + struct.pack("<I", 3) + struct.pack("<QQ", len(names), 2)
    out += string("general.architecture") + struct.pack("<I", 8) + string("qwen_image")
    out += string("tokenizer.ggml.tokens") + struct.pack("<I", 9) + struct.pack("<IQ", 8, 2) + string("a") + string("bb")   # array de strings
    for n in names:
        out += string(n) + struct.pack("<I", 2) + struct.pack("<QQ", 4, 4) + struct.pack("<I", 0) + struct.pack("<Q", 0)
    path.write_bytes(out + b"\0" * 64)


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
        (self.img / "qwen-image-2512-Q4_K_M.gguf").write_bytes(b"g")
        M._LOCAL_CACHE.clear()

    def prov(self):
        from asta.canvas import media as M

        return M._KINDS["gguf_local"]({"id": "gguf_local", "label": "g", "models_dir": str(self.tmp), "models": {"image": "qwen-image-2512-Q4_K_M.gguf"}, "needs_key": False})

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
        self.assertEqual(loads[0], {"diffusion_model_path": str(self.img / "qwen-image-2512-Q4_K_M.gguf"), "vae_path": str(self.img / "qwen_image_vae.safetensors"), "llm_path": str(self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"),
                                    "offload_params_to_cpu": True, "diffusion_flash_attn": True})       # memória e atenção como na documentação da stable-diffusion.cpp
        self.assertEqual(runs[0]["cfg_scale"], 2.5)
        self.assertEqual((runs[0]["width"], runs[0]["height"]), (1024, 576))

    def test_gguf_header_names_are_read_and_non_gguf_files_are_left_alone(self):
        from asta.canvas import gguf_info

        f = self.img / "m.gguf"
        write_gguf(f, ["transformer_blocks.0.img_mod.1.weight", "x.y"])
        self.assertEqual(gguf_info.tensor_names(f), ["transformer_blocks.0.img_mod.1.weight", "x.y"])
        (self.img / "nao.gguf").write_bytes(b"isto nao e gguf")
        self.assertIsNone(gguf_info.tensor_names(self.img / "nao.gguf"))
        self.assertIsNone(gguf_info.tensor_names(self.img / "nao-existe.gguf"))

    FAKE_LIB = '''
import ctypes, os
from types import SimpleNamespace
sd_log_callback = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)
_cb = None
def sd_set_log_callback(f, d):
    global _cb
    _cb = f
def _log(level, text):
    if _cb:
        _cb(level, text.encode(), None)
def sd_get_system_info():
    return b"SSE3 = 1"
class StableDiffusion:
    def __init__(self, **kw):
        mode = os.environ.get("FAKE_SD_MODE", "ok")
        _log(1, "loading diffusion model")
        if mode == "crash":
            _log(3, "get sd version from file failed: ''")
            ctypes.string_at(0)   # falha de segmentação de verdade
        if mode == "refuse":
            _log(3, "ggml_backend_cpu_buffer_type_alloc_buffer: failed to allocate buffer of size 12884901888")
            self._model = SimpleNamespace(model=None)
            return
        self._model = SimpleNamespace(model=1)
    def generate_image(self, prompt="", width=64, height=64, seed=0, init_image=None, ref_images=None, strength=0.75, **kw):
        if os.environ.get("FAKE_SD_MODE") == "gencrash":
            ctypes.string_at(0)
        from PIL import Image
        if init_image is not None:
            assert isinstance(init_image, str) and os.path.isfile(init_image)   # no processo à parte a imagem chega como arquivo
        return [Image.new("RGB", (width, height), (10, 20, 30))]
'''

    def real_worker(self, mode):
        """Instala uma «stable_diffusion_cpp» de mentira, mas de ARQUIVO (como a de verdade): o ASTA então roda o modelo no processo à parte, de verdade."""
        import importlib

        from asta.canvas import media as M

        d = Path(tempfile.mkdtemp())
        (d / "stable_diffusion_cpp").mkdir()
        (d / "stable_diffusion_cpp" / "__init__.py").write_text(self.FAKE_LIB)
        sys.path.insert(0, str(d))
        old = sys.modules.pop("stable_diffusion_cpp", None)
        self.addCleanup(lambda: (sys.path.remove(str(d)), sys.modules.pop("stable_diffusion_cpp", None), old and sys.modules.__setitem__("stable_diffusion_cpp", old), M._LOCAL_CACHE.clear(), setattr(M, "_SD_CB", None)))
        env = mock.patch.dict(os.environ, {"FAKE_SD_MODE": mode, "PYTHONPATH": str(d), "ASTA_HOME": str(d)})
        env.start()
        self.addCleanup(env.stop)
        importlib.import_module("stable_diffusion_cpp")
        M._LOCAL_CACHE.clear()
        return d

    def test_the_model_runs_in_a_separate_process_and_stays_loaded_between_images(self):
        from asta.canvas import media as M

        self.real_worker("ok")
        prov = self.prov()
        out = prov.image("x", size="512x512")
        self.assertEqual(out[0].mime, "image/png")
        proxy = next(iter(M._LOCAL_CACHE.values()))
        self.assertIsInstance(proxy, M._SDProxy)
        prov.image("y", size="512x512")
        self.assertIs(next(iter(M._LOCAL_CACHE.values())), proxy)   # o mesmo processo: não recarrega o modelo
        proxy.close()

    def test_a_segfault_while_loading_does_not_take_asta_down(self):
        from asta.canvas import media as M
        from asta.providers.base import ProviderError

        d = self.real_worker("crash")
        with self.assertRaises(ProviderError) as cm:
            self.prov().image("x", size="512x512")
        msg = str(cm.exception)
        self.assertIn("não reconhece o modelo", msg)
        self.assertIn("código -11", msg)           # o processo dela caiu (-11), o do teste (o ASTA) continua aqui
        self.assertEqual(M._LOCAL_CACHE, {})
        self.assertTrue((d / "sd_needs_newer").is_file())

    def test_a_refused_model_reports_the_log_of_the_separate_process(self):
        from asta.providers.base import ProviderError

        self.real_worker("refuse")
        with self.assertRaises(ProviderError) as cm:
            self.prov().image("x", size="512x512")
        self.assertIn("failed to allocate buffer", str(cm.exception))
        self.assertIn("falta de memória", str(cm.exception))

    def test_a_segfault_while_generating_is_reported_and_the_next_image_reloads(self):
        from asta.canvas import media as M
        from asta.providers.base import ProviderError

        self.real_worker("gencrash")
        prov = self.prov()
        with self.assertRaises(ProviderError) as cm:
            prov.image("x", size="512x512")
        self.assertIn("fechou de repente", str(cm.exception))
        self.assertEqual(M._LOCAL_CACHE, {})
        os.environ["FAKE_SD_MODE"] = "ok"                      # o worker novo herda o ambiente: agora funciona
        out = prov.image("x", size="512x512")
        self.assertEqual(len(out), 1)
        next(iter(M._LOCAL_CACHE.values())).close()

    def test_image_to_image_sends_the_reference_as_a_file_to_the_separate_process(self):
        from asta.canvas import media as M
        from tests.test_canvas import PNG

        self.real_worker("ok")
        out = self.prov().image("x", size="512x512", refs=[(PNG, "image/png")])
        self.assertEqual(len(out), 1)
        proxy = next(iter(M._LOCAL_CACHE.values()))
        self.assertIn("init_image", proxy._params)             # os parâmetros aceitos vêm da biblioteca, lidos na carga
        proxy.close()

    def test_the_vae_of_flux_and_z_image_is_never_used_for_qwen_image(self):
        from asta.providers.base import ProviderError

        (self.img / "ae.safetensors").write_bytes(b"flux-vae")          # fica na mesma pasta quando o Z-Image pré-instalado está instalado
        (self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf").write_bytes(b"t")
        mod, loads, _ = self.fake(fail=ValueError("NULL pointer access"))
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}), self.assertRaises(ProviderError) as cm:
            self.prov().image("x")
        self.assertEqual(loads[0], {"model_path": str(self.img / "qwen-image-2512-Q4_K_M.gguf")})   # sem o VAE certo: não monta o carregamento com o VAE errado
        self.assertIn("VAE do Qwen-Image", str(cm.exception))
        self.assertIn("[[asta-support:", str(cm.exception))

    def test_a_model_that_failed_to_load_is_reported_with_the_load_log_and_never_cached(self):
        from types import SimpleNamespace

        from asta.canvas import media as M
        from asta.providers.base import ProviderError

        M._SD_LITE.clear()
        M._LOCAL_CACHE.clear()
        (self.img / "qwen_image_vae.safetensors").write_bytes(b"v")
        (self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf").write_bytes(b"t")
        cbs, loads = [], []

        class Broken:
            def __init__(self, **kw):
                loads.append(kw)
                cbs[0](3, b"ggml_backend_cpu_buffer_type_alloc_buffer: failed to allocate buffer of size 12884901888\n", None)
                self._model = SimpleNamespace(model=None)   # a biblioteca não levanta erro: segue com o contexto nulo

            def generate_image(self, **kw):
                raise AssertionError("não deveria gerar com um modelo que não carregou")

        mod = mock.MagicMock(StableDiffusion=Broken)
        mod.sd_log_callback = lambda f: f
        mod.sd_set_log_callback = lambda f, d: cbs.append(f)
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}), self.assertRaises(ProviderError) as cm:
            self.prov().image("x", size="512x512")
        msg = str(cm.exception)
        self.assertIn("não carregou", msg)
        self.assertIn("failed to allocate buffer", msg)      # o motivo vem do log da carga, não é apagado antes
        self.assertIn("falta de memória", msg)
        self.assertIn("qwen_image_vae.safetensors", msg)
        self.assertEqual(len(loads), 2)                      # 2ª tentativa, sem flash attention/offload
        self.assertNotIn("diffusion_flash_attn", loads[1])
        self.assertEqual(M._LOCAL_CACHE, {})                 # nunca guarda um modelo quebrado
        M._SD_LITE.clear()
        M._SD_CB = None

    def test_an_unrecognized_model_version_asks_to_update_the_library_and_is_not_retried(self):
        from types import SimpleNamespace

        from asta.canvas import media as M
        from asta.providers.base import ProviderError

        M._SD_LITE.clear()
        M._LOCAL_CACHE.clear()
        (self.img / "qwen_image_vae.safetensors").write_bytes(b"v")
        (self.img / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf").write_bytes(b"t")
        cbs, loads, gens = [], [], []

        class Old:
            def __init__(self, **kw):
                loads.append(kw)
                cbs[0](2, b"stable-diffusion.cpp:299  - get sd version from file failed: ''\n", None)
                self._model = SimpleNamespace(model=None)

            def generate_image(self, **kw):
                gens.append(kw)   # gerar com um contexto nulo derruba o programa inteiro (falha de segmentação)

        mod = mock.MagicMock(StableDiffusion=Old)
        mod.sd_log_callback = lambda f: f
        mod.sd_set_log_callback = lambda f, d: cbs.append(f)
        home = Path(tempfile.mkdtemp())
        with mock.patch.dict(os.environ, {"ASTA_HOME": str(home)}), mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mod}), self.assertRaises(ProviderError) as cm:
            self.prov().image("x", size="512x512")
        self.assertTrue((home / "sd_needs_newer").is_file())   # avisa o `asta libs`: na próxima instalação/atualização ele compila a biblioteca mais nova
        self.assertIn("não reconhece o modelo", str(cm.exception))
        self.assertIn("[[asta-sd-update]]", str(cm.exception))   # a tela troca isto pelo botão «Atualizar a biblioteca»
        self.assertEqual((len(loads), gens), (1, []))   # sem nova tentativa e sem chamar a geração
        M._SD_CB = None

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
        self.assertEqual(loads[0], {"model_path": str(self.img / "qwen-image-2512-Q4_K_M.gguf")})   # sem os apoios: carrega como arquivo único (como antes)
        self.assertIn("Qwen2.5-VL", msg)
        self.assertIn("VAE do Qwen-Image", msg)
        self.assertIn("[[asta-support:qwen-image-2512-Q4_K_M.gguf]]", msg)                  # a tela troca isto pelo botão «Baixar os arquivos de apoio»

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
        self.assertEqual(names, {"qwen-image-2512-Q4_K_M.gguf", "meu-modelo-Q4_K_M.gguf"})


class SupportFilesTests(ServerCase):
    """v0.17.7 — baixar os arquivos de apoio (VAE, codificador de texto) de um GGUF de difusão, a pedido."""

    def setUp(self):
        self.img = self.store.models_dir / "image"
        self.img.mkdir(parents=True, exist_ok=True)
        for f in list(self.img.iterdir()):
            f.unlink()
        (self.img / "qwen-image-2512-Q4_K_M.gguf").write_bytes(b"g")

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

        m = support.missing(self.img, "qwen-image-2512-Q4_K_M.gguf")
        self.assertEqual((m["family"], [x["key"] for x in m["missing"]]), ("qwen-image", ["vae_path", "llm_path"]))
        self.assertGreater(m["approx_gb"], 4)
        self.assertEqual(support.missing(self.img, "meu-modelo.gguf")["family"], "")
        (self.img / "qwen_image_vae.safetensors").write_bytes(b"v")
        self.assertEqual([x["key"] for x in support.missing(self.img, "qwen-image-2512-Q4_K_M.gguf")["missing"]], ["llm_path"])

    def test_route_downloads_only_what_is_missing_and_then_refuses(self):
        calls = []
        with mock.patch("asta.hf.download_many", side_effect=self.fake_download(calls)):
            s, r = self.c.json("POST", "/api/media/support/download", {"model": "qwen-image-2512-Q4_K_M.gguf"})
            self.assertEqual(s, 200, r)
            ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        done = [e for e in ev if e["type"] == "done"]
        self.assertEqual(len(done), 1, ev[-3:])
        self.assertEqual(sorted(done[0]["files"]), ["Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf", "qwen_image_vae.safetensors"])
        self.assertEqual({c[0] for c in calls}, {"Comfy-Org/Qwen-Image_ComfyUI", "unsloth/Qwen2.5-VL-7B-Instruct-GGUF"})
        self.assertTrue(all(c[2] for c in calls))                                      # arquivos que não são .gguf também (any_file)
        self.assertTrue((self.img / "qwen_image_vae.safetensors").is_file())
        s, r = self.c.json("POST", "/api/media/support/download", {"model": "qwen-image-2512-Q4_K_M.gguf"})
        self.assertEqual(s, 400)                                                       # agora está tudo lá
        self.assertIn("já estão", json.dumps(r, ensure_ascii=False))

    def test_sd_latest_route_runs_asta_libs_in_a_job_and_reports_the_outcome(self):
        cmds = []

        def fake_popen(cmd, **kw):
            cmds.append(cmd)
            code = 1 if len(cmds) == 2 else 0
            return mock.Mock(stdout=iter([b"Instalando a stable-diffusion-cpp-python mais nova\n", b"ERRO: cmake nao encontrado\n" if code else b"pronto\n"]), wait=lambda: code)

        with mock.patch("subprocess.Popen", side_effect=fake_popen), mock.patch("asta.canvas.media._media_unload") as unload:
            s, r = self.c.json("POST", "/api/media/sd-latest", {})
            self.assertEqual(s, 200, r)
            ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
            self.assertEqual([e["type"] for e in ev if e["type"] in ("done", "error")], ["done"])
            s, r = self.c.json("POST", "/api/media/sd-latest", {})
            ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        err = [e for e in ev if e["type"] == "error"]
        self.assertEqual(len(err), 1)
        self.assertIn("cmake", err[0]["message"])
        self.assertEqual(cmds[0][-3:], ["--extras", "none", "--sd-latest"])
        self.assertEqual(unload.call_count, 2)               # fecha o processo da biblioteca antiga antes de compilar

    def test_flux2_klein_is_its_own_family_with_the_flux2_vae_and_a_qwen3_text_encoder(self):
        from asta.canvas import support

        k4, k9 = support.family_of("flux-2-klein-4b-Q4_K_M.gguf"), support.family_of("FLUX.2-klein-base-9B-Q8_0.gguf")
        self.assertEqual((k4["id"], k9["id"]), ("flux2-klein-4b", "flux2-klein-9b"))
        self.assertEqual(support.family_of("flux1-dev-Q4_0.gguf")["id"], "flux")             # FLUX.1 continua pedindo clip_l e t5xxl
        self.assertIsNone(support.family_of("flux-2-dev-Q4_0.gguf"))                         # FLUX.2 dev (Mistral 24B) não é de nenhuma família: não é tratado como FLUX.1
        self.assertEqual(support.run_for(k4, "flux-2-klein-4b-Q4_K_M.gguf"), {"cfg_scale": 1.0, "sample_steps": 4, "sample_method": "euler"})   # destilado: 4 passos, sem CFG
        self.assertEqual(support.run_for(k9, "flux-2-klein-base-9b-Q8_0.gguf")["sample_steps"], 50)                                                # «base»: 50 passos, CFG 4
        d = Path(tempfile.mkdtemp())
        for n in ("flux2-vae.safetensors", "Qwen3-4B-Q4_K_M.gguf", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "Qwen3-8B-Q4_K_M.gguf", "ae.safetensors", "flux-2-klein-4b-Q4_K_M.gguf"):
            (d / n).write_bytes(b"x")
        f4 = support.find_companions(d, d / "flux-2-klein-4b-Q4_K_M.gguf", k4)
        self.assertEqual(f4, {"vae_path": "flux2-vae.safetensors", "llm_path": "Qwen3-4B-Q4_K_M.gguf"})   # o Instruct-2507 do Z-Image e o ae.safetensors do FLUX.1 não servem
        f9 = support.find_companions(d, d / "x.gguf", k9)
        self.assertEqual(f9["llm_path"], "Qwen3-8B-Q4_K_M.gguf")                                            # o klein 9B usa o Qwen3 de 8B
        info = support.missing(self.img, "flux-2-klein-4b-Q4_K_M.gguf")
        self.assertEqual({m["key"] for m in info["missing"]}, {"vae_path", "llm_path"})
        self.assertEqual({m["repo"] for m in info["missing"]}, {"Comfy-Org/flux2-dev", "unsloth/Qwen3-4B-GGUF"})

    def test_flux2_klein_gguf_loads_with_its_companions_and_edits_with_several_images(self):
        from tests.test_canvas import PNG, proc

        root = Path(tempfile.mkdtemp())
        img = root / "image"
        img.mkdir()
        for n in ("flux2-vae.safetensors", "Qwen3-4B-Q4_K_M.gguf", "flux-2-klein-4b-Q4_K_M.gguf"):
            (img / n).write_bytes(b"x")
        loads, seen = [], []

        class Img:
            def save(self, buf, format="PNG"):
                buf.write(PNG)

        class SD:
            def __init__(self, **kw):
                loads.append(kw)

            def generate_image(self, prompt="", width=0, height=0, seed=0, ref_images=None, init_image=None, cfg_scale=0, sample_steps=0, sample_method="", **kw):
                seen.append({"refs": ref_images, "init": init_image, "cfg": cfg_scale, "steps": sample_steps})
                return [Img()]

        from asta.canvas import media as M

        M._LOCAL_CACHE.clear()
        prov = M._KINDS["gguf_local"]({"id": "gguf_local", "label": "g", "models_dir": str(root), "models": {"image": "flux-2-klein-4b-Q4_K_M.gguf"}, "needs_key": False})
        refs = [(proc.image(f"r{i}", "64x64", i + 1), "image/png") for i in range(3)]
        with mock.patch.dict(sys.modules, {"stable_diffusion_cpp": mock.MagicMock(StableDiffusion=SD)}):
            prov.image("x", size="512x512", refs=refs)
            self.assertEqual(prov.max_refs(""), 4)
        self.assertEqual(loads[0]["diffusion_model_path"], str(img / "flux-2-klein-4b-Q4_K_M.gguf"))
        self.assertEqual((loads[0]["vae_path"], loads[0]["llm_path"]), (str(img / "flux2-vae.safetensors"), str(img / "Qwen3-4B-Q4_K_M.gguf")))
        self.assertNotIn("clip_l_path", loads[0])                                    # nada de clip_l/t5xxl do FLUX.1
        self.assertEqual((seen[0]["cfg"], seen[0]["steps"]), (1.0, 4))
        self.assertEqual(len(seen[0]["refs"]), 3)                                    # klein edita com ref_images (todas as imagens)
        self.assertIsNone(seen[0]["init"])
        M._LOCAL_CACHE.clear()

    def test_flux3_image_klein_is_its_own_gguf_family_with_a_qwen3_vl_text_encoder(self):
        from asta.canvas import support

        f = support.family_of("flux-3-image-klein-UD-Q4_K_XL.gguf")
        self.assertEqual(f["id"], "flux3-klein")
        self.assertEqual(support.family_of("flux3-image-klein-Q4_K.gguf")["id"], "flux3-klein")
        self.assertIsNone(support.family_of("flux-3-image-klein-pup-Q4_K_M.gguf"))          # o expansor de prompt é um modelo de texto, não de imagem
        self.assertEqual(support.family_of("flux1-dev-Q4_0.gguf")["id"], "flux")             # FLUX.1 não é confundido com o 2 nem com o 3
        self.assertEqual(support.run_for(f, "flux-3-image-klein-Q4_K_M.gguf"), {"cfg_scale": 1.0, "sample_steps": 16})   # destilado: 16 passos, sem guidance
        self.assertEqual(support.run_for(f, "flux-3-image-klein-base-Q8_0.gguf"), {"cfg_scale": 3.5, "sample_steps": 50})
        d = Path(tempfile.mkdtemp())
        for n in ("flux2-vae.safetensors", "Qwen3-VL-4B-Instruct-Q4_K_M.gguf", "mmproj-F16.gguf", "Qwen3-4B-Q4_K_M.gguf", "ae.safetensors"):
            (d / n).write_bytes(b"x")
        self.assertEqual(support.find_companions(d, d / "m.gguf", f), {"vae_path": "flux2-vae.safetensors", "llm_path": "Qwen3-VL-4B-Instruct-Q4_K_M.gguf"})   # o mmproj, o Qwen3 de texto e o VAE do FLUX.1 não servem
        info = support.missing(self.img, "flux-3-image-klein-Q4_K_M.gguf")
        self.assertEqual({m["repo"] for m in info["missing"]}, {"Comfy-Org/flux2-dev", "unsloth/Qwen3-VL-4B-Instruct-GGUF"})

    def test_flux3_modular_repo_downloads_one_copy_of_the_weights_and_gated_errors_are_explained(self):
        from asta.canvas import localmodels as lm

        names = ["modular_model_index.json", "config.json", "model.safetensors", "ae.safetensors", "README.md", "text_encoder/model-00001-of-00002.safetensors", "text_encoder/config.json",
                 "transformer/diffusion_pytorch_model-00001-of-00002.safetensors", "vae/diffusion_pytorch_model.safetensors", "variants/fp8r/model.safetensors", "variants/nvfp4/config.json"]
        got = [f["name"] for f in lm.select_files([{"name": n, "size": 1} for n in names], "bf16")]
        self.assertNotIn("model.safetensors", got)             # o arquivo da raiz repete transformer/
        self.assertNotIn("ae.safetensors", got)                # e este repete vae/
        self.assertFalse([n for n in got if n.startswith("variants/")])   # fp8/nvfp4 são cópias alternativas: baixar dobraria o download
        self.assertIn("transformer/diffusion_pytorch_model-00001-of-00002.safetensors", got)
        self.assertIn("text_encoder/model-00001-of-00002.safetensors", got)

        class GatedRepoError(Exception):
            pass

        hub = mock.Mock()
        hub.HfApi.return_value.model_info.side_effect = GatedRepoError("401 Client Error: Cannot access gated repo")
        with mock.patch.object(lm, "_hub", return_value=hub), self.assertRaises(lm.ProviderError) as cm:
            lm.download("black-forest-labs/flux-3-image-klein", "bf16", token="")
        msg = str(cm.exception)
        self.assertIn("restrito", msg)
        self.assertIn("aceite a licença", msg)
        self.assertIn("https://huggingface.co/black-forest-labs/flux-3-image-klein", msg)
        self.assertIn("nenhum token", msg)

    def test_route_validation(self):
        self.assertEqual(self.c.json("POST", "/api/media/support/download", {"model": "../x.gguf"})[0], 400)
        self.assertEqual(self.c.json("POST", "/api/media/support/download", {"model": "meu-modelo.gguf"})[0], 400)
        self.assertEqual(self.c.json("POST", "/api/media/support/download", {})[0], 400)


if __name__ == "__main__":
    unittest.main()
