"""OpenRouter no Canvas: imagens (rota /images ou chat com modalities, edição com referências), transcrição por chat com áudio, modelos listados pelas modalidades e erros claros."""
import base64
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.canvas import media as M  # noqa: E402
from asta.providers import ProviderError  # noqa: E402
from tests.test_canvas import PNG, provider  # noqa: E402


class FakeOR:
    def __init__(self, images_route=True, chat_status=200, catalog=None, video_models=None, bad_params=(), ref_limit=None):
        self.seen = []
        self.images_route, self.chat_status = images_route, chat_status
        self.ref_limit = ref_limit   # a rota /images recusa mais referências do que isso (como a xAI)
        self.catalog, self.video_models, self.bad_params = catalog, video_models, set(bad_params)   # catalog: modelos de /images/models; bad_params: campos que /images e /videos recusam com 400
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj, status=200):
                data = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                outer.seen.append(("GET", self.path, None))
                if self.path.endswith("/images/models") and outer.catalog is not None:
                    return self._send({"data": outer.catalog})
                if self.path.endswith("/videos/models") and outer.video_models is not None:
                    return self._send({"data": outer.video_models})
                if "/videos/job1/content" in self.path:
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", "4")
                    self.end_headers()
                    return self.wfile.write(b"MP4!")
                if self.path.endswith("/videos/job1"):
                    return self._send({"id": "job1", "status": "completed", "unsigned_urls": [outer.url + "/videos/job1/content?index=0"]})
                if self.path.startswith("/api/v1/models"):
                    models = [
                        {"id": "google/gemini-2.5-flash-image", "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["image", "text"]}},
                        {"id": "google/gemini-2.5-flash", "architecture": {"input_modalities": ["text", "image", "audio"], "output_modalities": ["text"]}},
                        {"id": "openai/gpt-4o-audio-preview", "architecture": {"input_modalities": ["text", "audio"], "output_modalities": ["text", "audio"]}},
                        {"id": "meta/llama", "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}},
                    ]
                    return self._send({"data": [m for m in models if "image" in m["architecture"]["output_modalities"]] if "output_modalities=image" in self.path else models})
                self._send({"error": "nope"}, 404)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.seen.append(("POST", self.path, body))
                if self.path.endswith("/videos"):
                    bad = [k for k in body if k in outer.bad_params]
                    if bad:
                        return self._send({"error": {"message": "Invalid request parameters: " + ",".join(bad)}}, 400)
                    return self._send({"id": "job1", "polling_url": outer.url + "/videos/job1", "status": "pending"}, 202)
                if self.path.endswith("/images"):
                    bad = [k for k in body if k in outer.bad_params]
                    if bad:
                        return self._send({"error": {"message": "Invalid request parameters: " + ",".join(bad)}}, 400)
                    if outer.ref_limit is not None and len(body.get("input_references") or []) > outer.ref_limit:
                        return self._send({"error": {"message": f"No provider for {body['model']} supports the requested parameter(s): input_references ({len(body['input_references'])} items). Provider rejections: xAI: input_references: must have between 0 and {outer.ref_limit} items"}}, 400)
                    if not outer.images_route:
                        return self._send({"error": {"message": "not found"}}, 404)
                    return self._send({"data": [{"b64_json": base64.b64encode(PNG).decode()}]})
                if self.path.endswith("/chat/completions"):
                    if outer.chat_status != 200:
                        return self._send({"error": {"message": "Insufficient credits"}}, outer.chat_status)
                    if str(body.get("model", "")).endswith("-flare"):
                        return self._send({"error": {"message": body["model"] + " is an image generation model and cannot be used with the chat/completions endpoint. Use the /api/v1/images endpoint instead.", "code": 400}}, 400)
                    if body.get("modalities") == ["image", "text"] and "image_config" in body and body.get("model") == "only-image":
                        return self._send({"error": {"message": "modalities not supported"}}, 400)
                    if body.get("modalities") == ["text"]:
                        return self._send({"choices": [{"message": {"content": "só texto"}}]})
                    if "modalities" in body:
                        return self._send({"choices": [{"message": {"content": "aqui está", "images": [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(PNG).decode()}}]}}]})
                    content = body["messages"][0]["content"]
                    if isinstance(content, list) and any(p.get("type") == "input_audio" for p in content):
                        return self._send({"choices": [{"message": {"content": "  olá mundo  "}}]})
                    return self._send({"choices": [{"message": {"content": "sem imagem"}}]})
                self._send({"error": "nope"}, 404)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/api/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def paths(self):
        return [(m, p) for m, p, _ in self.seen]


class OpenRouterMediaTests(unittest.TestCase):
    def setUp(self):
        M.OpenRouterMedia._no_images.clear()
        M.OpenRouterMedia._learned_refs.clear()

    def run_with(self, **kw):
        fake = FakeOR(**kw)
        self.addCleanup(fake.close)
        return fake, provider("openrouter", fake.url, {})

    def test_declares_image_video_voice_and_transcription_with_references(self):
        _, p = self.run_with()
        self.assertEqual(p.caps, ("image", "video", "voice", "stt"))
        self.assertTrue(p.supports_refs)
        self.assertEqual(p.max_refs(), 4)
        d = {x["id"]: x for x in M.describe_media_presets({"media": {}})}["openrouter"]
        self.assertEqual(d["caps"], ["image", "video", "voice", "stt"])

    def test_image_uses_the_images_route_when_the_server_has_it(self):
        fake, p = self.run_with()
        out = p.image("um gato", size="1024x576")
        self.assertEqual((out[0].mime, out[0].data), ("image/png", PNG))
        self.assertEqual([x for x in fake.paths() if x[0] == "POST"], [("POST", "/api/v1/images")])

    def test_image_falls_back_to_chat_with_modalities_and_remembers_it(self):
        fake, p = self.run_with(images_route=False)
        out = p.image("um gato", size="1792x1024", negative="borrado")
        self.assertEqual(out[0].data, PNG)
        chat = [b for m, path, b in fake.seen if path.endswith("/chat/completions")][0]
        self.assertEqual(chat["modalities"], ["image", "text"])
        self.assertEqual(chat["image_config"], {"aspect_ratio": "16:9", "image_size": "2K"})
        self.assertIn("Evite: borrado", chat["messages"][0]["content"])
        fake.seen.clear()
        p.image("outro")   # lembrou: não tenta /images de novo
        self.assertEqual([path for m, path in fake.paths() if m == "POST"], ["/api/v1/chat/completions"])

    def test_references_edit_through_the_images_route_with_input_references(self):
        fake, p = self.run_with()
        out = p.image("troque o fundo por uma praia", refs=[(PNG, "image/png"), (PNG, "image/png")], size="1024x1024")
        self.assertEqual(out[0].data, PNG)
        posts = [(path, b) for m, path, b in fake.seen if m == "POST"]
        self.assertEqual([x[0] for x in posts], ["/api/v1/images"])   # a rota dedicada também edita
        refs = posts[0][1]["input_references"]
        self.assertEqual([r["type"] for r in refs], ["image_url", "image_url"])
        self.assertTrue(refs[0]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_references_edit_through_chat_when_the_server_has_no_images_route(self):
        fake, p = self.run_with(images_route=False)
        out = p.image("troque o fundo por uma praia", refs=[(PNG, "image/png"), (PNG, "image/png")], size="1024x1024")
        self.assertEqual(out[0].data, PNG)
        chat = [b for m, path, b in fake.seen if path.endswith("/chat/completions")][0]
        self.assertEqual([x["type"] for x in chat["messages"][0]["content"]], ["text", "image_url", "image_url"])

    def test_the_catalog_decides_the_parameters_and_the_route(self):
        cat = [{"id": "openai/gpt-image-2.6-flare", "supported_parameters": {"aspect_ratio": {"type": "enum", "values": ["1:1", "3:2", "2:3"]}, "resolution": {"type": "enum", "values": ["1K", "2K"]}, "seed": {"type": "boolean"}}},
               {"id": "x-ai/grok-imagine", "supported_parameters": {"aspect_ratio": {"type": "enum", "values": ["1:1", "16:9", "9:16"]}}}]
        fake, p = self.run_with(catalog=cat)
        p.image("uma thumb", model="openai/gpt-image-2.6-flare", size="1920x1080", seed=7, refs=[(PNG, "image/png")])
        p.image("outra", model="x-ai/grok-imagine", size="1920x1080")
        posts = [b for m, path, b in fake.seen if m == "POST"]
        self.assertEqual([x for x in posts[0] if x not in ("input_references",)], ["model", "prompt", "aspect_ratio", "resolution", "seed"])
        self.assertEqual((posts[0]["aspect_ratio"], posts[0]["resolution"], posts[0]["seed"]), ("3:2", "2K", 7))   # 16:9 não existe neste modelo: a mais próxima
        self.assertNotIn("size", posts[1])                                   # a xAI recusa «size» em pixels
        self.assertEqual((posts[1]["aspect_ratio"], "resolution" in posts[1], "seed" in posts[1]), ("16:9", False, False))

    def test_a_refused_option_gets_one_retry_with_only_the_essentials(self):
        cat = [{"id": "m/x", "supported_parameters": {"aspect_ratio": {"type": "enum", "values": ["1:1"]}}}]
        fake, p = self.run_with(catalog=cat, bad_params=["aspect_ratio"])
        out = p.image("x", model="m/x", refs=[(PNG, "image/png")])
        self.assertEqual(out[0].data, PNG)
        posts = [b for m, path, b in fake.seen if m == "POST"]
        self.assertEqual([sorted(b) for b in posts], [["aspect_ratio", "input_references", "model", "prompt"], ["input_references", "model", "prompt"]])

    def test_a_model_that_is_image_only_is_redirected_from_chat_to_the_images_route(self):
        fake, p = self.run_with(catalog=[{"id": "outro/modelo"}])   # o modelo não está no catálogo: vai pelo chat; a mensagem do OpenRouter manda usar /images
        out = p.image("x", model="openai/gpt-image-2.6-flare")
        self.assertEqual(out[0].data, PNG)
        self.assertEqual([path for m, path in fake.paths() if m == "POST"], ["/api/v1/chat/completions", "/api/v1/images"])

    def test_xai_models_use_at_most_three_references_by_default(self):
        fake, p = self.run_with(ref_limit=3)
        self.assertEqual(p.max_refs("x-ai/grok-imagine-image-2.0"), 3)
        self.assertEqual(p.max_refs("openai/gpt-image-1"), 4)
        refs = [(PNG, "image/png")] * 4
        out = p.image("x", model="x-ai/grok-imagine-image-2.0", refs=refs[:3])
        self.assertEqual(out[0].data, PNG)

    def test_the_catalog_limit_for_references_wins(self):
        cat = [{"id": "m/y", "supported_parameters": {"input_references": {"type": "range", "min": 0, "max": 6}}}]
        _, p = self.run_with(catalog=cat)
        self.assertEqual(p.max_refs("m/y"), 6)

    def test_a_reference_limit_in_the_provider_error_is_learned_and_applied(self):
        M.OpenRouterMedia._learned_refs.clear()
        fake, p = self.run_with(ref_limit=2)
        out = p.image("x", model="m/z", refs=[(PNG, "image/png")] * 4)   # o catálogo não diz nada: a recusa («between 0 and 2 items») ensina o limite
        self.assertEqual(out[0].data, PNG)
        posts = [b for m, path, b in fake.seen if m == "POST"]
        self.assertEqual([len(b["input_references"]) for b in posts], [4, 2])
        self.assertEqual(p.max_refs("m/z"), 2)   # e as próximas imagens já saem com o limite
        M.OpenRouterMedia._learned_refs.clear()

    def test_video_follows_the_catalog_and_downloads_from_the_signed_url_list(self):
        vm = [{"id": "x-ai/grok-imagine-video", "supported_durations": [5, 8, 10], "supported_aspect_ratios": ["16:9", "9:16"], "supported_resolutions": ["480p", "720p"]}]
        fake, p = self.run_with(video_models=vm)
        out = p.video("um farol", duration=6, aspect="9:16", model="x-ai/grok-imagine-video", image=(PNG, "image/png"))
        self.assertEqual((out.mime, out.data), ("video/mp4", b"MP4!"))
        body = [b for m, path, b in fake.seen if m == "POST"][0]
        self.assertEqual((body["duration"], body["aspect_ratio"], body["resolution"]), (5, "9:16", "720p"))   # 6 s → 5 s (a mais próxima); ~720p
        self.assertEqual(body["frame_images"][0]["frame_type"], "first_frame")

    def test_video_drops_options_the_model_refuses_one_at_a_time(self):
        fake, p = self.run_with(video_models=[], bad_params=["frame_images", "resolution"])
        out = p.video("x", model="m/v", image=(PNG, "image/png"))
        self.assertEqual(out.data, b"MP4!")
        posts = [b for m, path, b in fake.seen if m == "POST"]
        self.assertNotIn("frame_images", posts[-1])

    def test_models_that_only_make_images_get_a_simpler_retry(self):
        fake, p = self.run_with(images_route=False)
        out = p.image("x", model="only-image")
        self.assertEqual(out[0].data, PNG)
        chats = [b for m, path, b in fake.seen if path.endswith("/chat/completions")]
        self.assertEqual((chats[1]["modalities"], chats[1]["image_config"]), (["image"], {"aspect_ratio": "1:1"}))

    def test_a_model_without_image_output_and_missing_credits_explain_themselves(self):
        _, p = self.run_with(images_route=False)
        with self.assertRaises(ProviderError) as cm:
            p._image_via_chat("x", "1024x1024", 1, "", [], "so-texto", {"modalities": ["text"]})
        self.assertIn("não devolveu imagem", str(cm.exception))
        _, p = self.run_with(images_route=False, chat_status=402)
        with self.assertRaises(ProviderError) as cm:
            p.image("x")
        self.assertIn("sem créditos", str(cm.exception))
        self.assertEqual(cm.exception.status, 402)

    def test_transcription_sends_input_audio_to_a_chat_model(self):
        fake, p = self.run_with()
        text = p.transcribe(b"RIFFxxxxWAVE", "fala.wav", "audio/wav", language="pt-BR")
        self.assertEqual(text, "olá mundo")
        body = [b for m, path, b in fake.seen if path.endswith("/chat/completions")][0]
        self.assertEqual(body["model"], "google/gemini-2.5-flash")
        parts = body["messages"][0]["content"]
        self.assertEqual(parts[1]["type"], "input_audio")
        self.assertEqual((parts[1]["input_audio"]["format"], base64.b64decode(parts[1]["input_audio"]["data"])), ("wav", b"RIFFxxxxWAVE"))
        self.assertIn("«pt»", parts[0]["text"])
        self.assertEqual(body["temperature"], 0)

    def test_transcription_of_an_unsupported_format_needs_ffmpeg_or_says_so(self):
        from unittest import mock

        _, p = self.run_with()
        with mock.patch.object(M.proc, "ffmpeg_path", return_value=None):
            with self.assertRaises(ProviderError) as cm:
                p.transcribe(b"x", "fala.webm", "audio/webm")
        self.assertIn("ffmpeg", str(cm.exception))

    def test_models_are_listed_by_the_modalities_openrouter_declares(self):
        fake, p = self.run_with()
        self.assertEqual(p.list_models("image"), ["google/gemini-2.5-flash-image"])
        self.assertEqual(p.list_models("stt"), ["google/gemini-2.5-flash", "openai/gpt-4o-audio-preview"])   # entrada de áudio, saída de texto (sem os modelos só de texto)
        self.assertIn("openai/gpt-4o-audio-preview", p.list_models("voice"))   # saída de áudio (+ as sugestões)
        self.assertIn("openai/tts-1", p.list_models("voice"))
        self.assertEqual(p.list_models("sound"), [])


if __name__ == "__main__":
    unittest.main()
