"""Modelos pré-instalados (texto e imagem): catálogo, instalação (com um Hugging Face simulado), configuração automática, CLI e API."""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import cli, hf, preinstalled as pre  # noqa: E402
from asta.providers.base import ProviderError  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.test_core import TmpCase  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class FakeHub:
    """Serve qualquer `/dono/repo/resolve/main/arquivo` com 16 bytes e registra o que foi pedido."""

    def __init__(self):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                m = re.match(r"^/([^/]+/[^/]+)/resolve/main/(.+)$", self.path)
                if not m:
                    self.send_response(404)
                    self.end_headers()
                    return
                outer.requests.append((m.group(1), urllib.parse.unquote(m.group(2))))
                body = b"GGUF" + b"x" * 12
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class CatalogTests(unittest.TestCase):
    def test_exactly_the_two_requested_models_with_their_quantizations(self):
        by_kind = {e["kind"]: e for e in pre.CATALOG}
        self.assertEqual(set(by_kind), {"text", "image"})
        self.assertEqual(len(pre.CATALOG), 2)  # "somente estes dois inicialmente"
        text, image = by_kind["text"], by_kind["image"]
        self.assertEqual((text["source"], text["quant"], text["file"]), ("empero-ai/Qwen3.8-2B-Distill", "Q8_0", "Qwen3.8-2B-Q8_0.gguf"))
        self.assertEqual((image["source"], image["quant"]), ("Tongyi-MAI/Z-Image", "Q4_K_M"))
        for e in pre.CATALOG:  # a quantização declarada é a do nome do arquivo
            self.assertEqual(hf.parse_quant(e["file"])["quant"], e["quant"])
            self.assertTrue(hf.REPO_RE.match(e["repo"]))
            for f in e["companions"]:
                self.assertTrue(hf.REPO_RE.match(f["repo"]) and ".." not in f["file"])
        self.assertEqual([c["file"].rsplit("/", 1)[-1] for c in image["companions"]], ["ae.safetensors", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"])

    def test_english_translation_exists_for_every_hint(self):
        if not shutil.which("node"):
            self.skipTest("Node.js não instalado")
        script = "import EN from '%s'; console.log(JSON.stringify(%s.filter((h) => !(h in EN))));" % ((ROOT / "asta/web/js/en.js").as_posix(), json.dumps([e["hint"] for e in pre.CATALOG]))
        r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(json.loads(r.stdout), [])

    def test_canvas_defaults_only_for_catalog_models(self):
        d = pre.defaults_for("image", "z-image-Q4_K_M.gguf")
        self.assertEqual(d["load"]["diffusion_model_path"], "@model")
        self.assertEqual(d["run"], {"cfg_scale": 4.0, "sample_steps": 30})
        self.assertEqual(pre.defaults_for("image", "outro.gguf"), {})
        self.assertEqual(pre.defaults_for("text", "z-image-Q4_K_M.gguf"), {})


class InstallTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.hub = FakeHub()
        self.addCleanup(self.hub.close)
        for p in (mock.patch.object(hf, "HF", self.hub.url), mock.patch("asta.hf.shutil.disk_usage", return_value=mock.Mock(free=10 ** 13))):
            p.start()
            self.addCleanup(p.stop)
        self.store = Store(self.tmp / "home")

    def libs(self, **present):
        real = pre._lib
        return mock.patch.object(pre, "_lib", side_effect=lambda m: present.get(m, real(m)))

    def test_text_model_is_installed_and_becomes_the_default_when_the_library_is_there(self):
        with self.libs(llama_cpp=True):
            r = pre.install(self.store, "text-qwen3.8-2b-distill")
        self.assertEqual(r["downloaded"], ["Qwen3.8-2B-Q8_0.gguf"])
        self.assertTrue((self.store.models_dir / "Qwen3.8-2B-Q8_0.gguf").is_file())  # texto: na raiz, como os demais
        s = self.store.get_settings()
        self.assertEqual(s["providers"]["local_hf"]["model"], "Qwen3.8-2B-Q8_0.gguf")
        self.assertEqual((s["active"]["generation"], s["active"]["characters"]), ("local_hf", "local_hf"))
        self.assertEqual(self.hub.requests, [("empero-ai/Qwen3.8-2B-Distill-GGUF", "Qwen3.8-2B-Q8_0.gguf")])

    def test_the_default_provider_is_not_touched_without_the_library_or_if_the_user_already_chose_one(self):
        with self.libs(llama_cpp=False):
            r = pre.install(self.store, "text-qwen3.8-2b-distill")
        self.assertEqual(self.store.get_settings()["active"]["generation"], "demo")  # sem llama-cpp-python não adianta ativar
        self.assertTrue(any("asta libs" in n for n in r["notes"]))
        self.store.save_settings({"active": {"generation": "anthropic"}})
        with self.libs(llama_cpp=True):
            pre.apply(self.store, pre.entry("text-qwen3.8-2b-distill"))
        self.assertEqual(self.store.get_settings()["active"]["generation"], "anthropic")  # escolha do usuário é respeitada
        self.assertEqual(self.store.get_settings()["providers"]["local_hf"]["model"], "Qwen3.8-2B-Q8_0.gguf")

    def test_image_model_comes_with_its_vae_and_text_encoder(self):
        with self.libs(stable_diffusion_cpp=True):
            r = pre.install(self.store, "image-z-image")
        folder = self.store.models_dir / "image"
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "ae.safetensors", "z-image-Q4_K_M.gguf"])
        self.assertEqual(len(r["downloaded"]), 3)
        self.assertEqual({req[0] for req in self.hub.requests}, {"unsloth/Z-Image-GGUF", "Comfy-Org/z_image_turbo", "unsloth/Qwen3-4B-Instruct-2507-GGUF"})
        self.assertIn(("Comfy-Org/z_image_turbo", "split_files/vae/ae.safetensors"), self.hub.requests)
        s = self.store.get_settings()["media"]
        self.assertEqual((s["models"]["gguf_local"]["image"], s["active"]["image"]), ("z-image-Q4_K_M.gguf", "gguf_local"))
        self.assertTrue(next(m for m in pre.status(self.store.models_dir) if m["id"] == "image-z-image")["installed"])

    def test_installing_again_downloads_nothing_and_a_partial_install_resumes(self):
        with self.libs(llama_cpp=True, stable_diffusion_cpp=True):
            self.assertEqual(pre.install_selected(self.store, "all", log=lambda m: None), 0)
            n = len(self.hub.requests)
            self.assertEqual(n, 4)
            lines = []
            self.assertEqual(pre.install_selected(self.store, "all", log=lines.append), 0)
            self.assertEqual(len(self.hub.requests), n)  # nada baixado de novo
            self.assertTrue(all("já instalado" in x for x in lines))
            (self.store.models_dir / "image" / "ae.safetensors").unlink()  # um arquivo faltando: só ele volta
            pre.install_selected(self.store, "image", log=lambda m: None)
            self.assertEqual(self.hub.requests[n:], [("Comfy-Org/z_image_turbo", "split_files/vae/ae.safetensors")])

    def test_selection_none_text_image_and_unknown(self):
        with self.libs(llama_cpp=True, stable_diffusion_cpp=True):
            self.assertEqual(pre.install_selected(self.store, "none", log=lambda m: None), 0)
            self.assertEqual(self.hub.requests, [])
            pre.install_selected(self.store, "text", log=lambda m: None)
            self.assertEqual({r[0] for r in self.hub.requests}, {"empero-ai/Qwen3.8-2B-Distill-GGUF"})
            self.assertEqual(pre.install_selected(self.store, "xyz", log=lambda m: None), 2)

    def test_failures_become_a_warning_with_a_retry_hint(self):
        lines = []
        with mock.patch.object(hf, "HF", "http://127.0.0.1:9"), self.libs(llama_cpp=True):
            self.assertEqual(pre.install_selected(self.store, "text", log=lines.append), 1)
        self.assertTrue(any("asta models install" in x for x in lines))
        self.assertFalse(list(self.store.models_dir.glob("*.gguf")))

    def test_disk_space_is_checked_before_downloading(self):
        with mock.patch("asta.hf.shutil.disk_usage", return_value=mock.Mock(free=1000)), self.assertRaises(ProviderError) as cm:
            pre.install(self.store, "text-qwen3.8-2b-distill")
        self.assertIn("espaço", str(cm.exception))
        self.assertEqual(self.hub.requests, [])

    def test_only_the_catalog_may_download_non_gguf_files(self):
        with self.assertRaises(ProviderError):
            hf.download("dono/modelo", "split_files/vae/ae.safetensors", self.store.models_dir)  # fora do catálogo: só .gguf
        with self.assertRaises(ProviderError):
            hf.download("dono/modelo", "../evil.safetensors", self.store.models_dir, any_file=True)

    def test_cli_models_list_and_install(self):
        env = {"ASTA_MODELS": "text"}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), self.libs(llama_cpp=True), contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["models", "install", "--home", str(self.tmp / "home2")]), 0)
            cli.main(["models", "list", "--home", str(self.tmp / "home2")])
        text = out.getvalue()
        self.assertIn("Qwen3.8 2B Distill (Q8_0): pronto", text)
        self.assertRegex(text, r"✓ text-qwen3\.8-2b-distill")
        self.assertRegex(text, r"· image-z-image")  # ASTA_MODELS=text: a imagem não foi baixada


class PreinstalledApiTests(ServerCase):
    def test_list_and_one_click_install_with_progress(self):
        hub = FakeHub()
        try:
            with mock.patch.object(hf, "HF", hub.url), mock.patch("asta.hf.shutil.disk_usage", return_value=mock.Mock(free=10 ** 13)), mock.patch.object(pre, "_lib", return_value=False):
                status, r = self.c.json("GET", "/api/preinstalled")
                self.assertEqual(status, 200)
                self.assertEqual([(m["kind"], m["quant"], m["installed"]) for m in r["models"]], [("text", "Q8_0", False), ("image", "Q4_K_M", False)])
                self.assertEqual(self.c.json("POST", "/api/preinstalled/install", {"id": "nada"})[0], 404)
                status, job = self.c.json("POST", "/api/preinstalled/install", {"id": "text-qwen3.8-2b-distill"})
                self.assertEqual(status, 200)
                ev = self.c.sse(f"/api/jobs/{job['job_id']}/events")
                self.assertEqual([e["type"] for e in ev if e["type"] in ("start", "done")], ["start", "done"])
                self.assertTrue(next(m for m in self.c.json("GET", "/api/preinstalled")[1]["models"] if m["kind"] == "text")["installed"])
                self.assertEqual([m["name"] for m in self.c.json("GET", "/api/hf/local")[1]["models"]], ["Qwen3.8-2B-Q8_0.gguf"])  # aparece em "Baixados"
        finally:
            hub.close()
            (self.store.models_dir / "Qwen3.8-2B-Q8_0.gguf").unlink(missing_ok=True)


class ContextWindowTests(TmpCase):
    """Modelos de texto pré-instalados começam com 32K de contexto; o usuário pode ajustar depois."""

    def test_preinstalled_text_model_defaults_to_32k_and_other_models_follow_the_hardware(self):
        from asta.providers.local_llama import MAX_CTX, context_size

        self.assertEqual(pre.DEFAULT_TEXT_CTX, 32768)
        self.assertEqual(pre.default_n_ctx("Qwen3.8-2B-Q8_0.gguf"), 32768)
        self.assertEqual(pre.default_n_ctx("outro-modelo.gguf"), 0)
        self.assertEqual(pre.default_n_ctx(""), 0)
        for tier in ("low", "medium", "high"):  # o padrão do modelo pré-instalado vale em qualquer hardware
            self.assertEqual(context_size(None, "Qwen3.8-2B-Q8_0.gguf", tier), 32768)
        self.assertEqual([context_size(None, "outro.gguf", t) for t in ("low", "medium", "high")], [2048, 4096, 8192])
        self.assertEqual(next(m for m in pre.status(Path(self.tmp)) if m["kind"] == "text")["n_ctx"], 32768)
        self.assertEqual(next(m for m in pre.status(Path(self.tmp)) if m["kind"] == "image")["n_ctx"], 0)

    def test_the_user_value_wins_and_is_clamped_and_invalid_values_fall_back_to_automatic(self):
        from asta.providers.local_llama import MAX_CTX, context_size

        self.assertEqual(context_size(8192, "Qwen3.8-2B-Q8_0.gguf", "low"), 8192)
        self.assertEqual(context_size("65536", "outro.gguf", "low"), 65536)
        self.assertEqual(context_size(100, "outro.gguf", "low"), 512)
        self.assertEqual(context_size(10 ** 12, "outro.gguf", "low"), MAX_CTX)
        for bad in (0, -5, "", None, "abc", [1]):
            self.assertEqual(context_size(bad, "Qwen3.8-2B-Q8_0.gguf", "low"), 32768, bad)

    def test_provider_config_carries_the_user_value_but_never_stores_the_default(self):
        from asta.providers import provider_config
        from asta.providers.local_llama import LocalLlamaProvider

        self.assertNotIn("n_ctx", provider_config({}, "local_hf"))  # o 32K é calculado na hora, nunca gravado nas configurações
        cfg = provider_config({"providers": {"local_hf": {"n_ctx": 16384}}}, "local_hf")
        self.assertEqual(LocalLlamaProvider(cfg).n_ctx_cfg, 16384)
        self.assertIsNone(LocalLlamaProvider(provider_config({}, "local_hf")).n_ctx_cfg)
        # 0 gravado pelo botão «Usar o automático» = automático
        self.assertEqual(LocalLlamaProvider(provider_config({"providers": {"local_hf": {"n_ctx": 0}}}, "local_hf")).n_ctx_cfg, 0)

    def test_installing_the_model_does_not_overwrite_a_context_the_user_already_chose(self):
        store = Store(Path(self.tmp) / "home")
        store.save_settings({"providers": {"local_hf": {"n_ctx": 4096}}})
        e = pre.entry("text-qwen3.8-2b-distill")
        pre.apply(store, e)
        self.assertEqual(store.get_settings()["providers"]["local_hf"]["n_ctx"], 4096)
        self.assertEqual(store.get_settings()["providers"]["local_hf"]["model"], "Qwen3.8-2B-Q8_0.gguf")

    def test_the_model_is_loaded_with_the_context_window_and_cached_per_size(self):
        from asta.providers import local_llama

        loaded = []

        class FakeLlama:
            def __init__(self, **kw):
                loaded.append(kw["n_ctx"])

        fake = mock.Mock(Llama=FakeLlama)
        model = Path(self.tmp) / "Qwen3.8-2B-Q8_0.gguf"
        model.write_bytes(b"x")
        local_llama._CACHE.clear()
        with mock.patch.dict(sys.modules, {"llama_cpp": fake}), mock.patch.object(local_llama, "hardware_info", return_value={"tier": "low", "ram_gb": 8, "cpus": 2, "gpu": "", "os": "Linux", "arch": "x86_64"}):
            from asta.providers import provider_config

            for ctx in (None, None, 8192, 8192):
                cfg = provider_config({"providers": {"local_hf": {"model": str(model), **({"n_ctx": ctx} if ctx else {})}}}, "local_hf")
                p = local_llama.LocalLlamaProvider(cfg)
                p._llm()
        self.assertEqual(loaded, [32768, 8192])  # 32K por padrão; mudar o valor recarrega; o mesmo valor reaproveita o modelo em memória
        local_llama._CACHE.clear()


if __name__ == "__main__":
    unittest.main()
