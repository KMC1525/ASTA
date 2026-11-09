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
    def __init__(self, images_route=True, chat_status=200):
        self.seen = []
        self.images_route, self.chat_status = images_route, chat_status
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
                if self.path.endswith("/images"):
                    if not outer.images_route:
                        return self._send({"error": {"message": "not found"}}, 404)
                    return self._send({"data": [{"b64_json": base64.b64encode(PNG).decode()}]})
                if self.path.endswith("/chat/completions"):
                    if outer.chat_status != 200:
                        return self._send({"error": {"message": "Insufficient credits"}}, outer.chat_status)
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

    def test_references_edit_through_chat_with_image_url_parts(self):
        fake, p = self.run_with()
        out = p.image("troque o fundo por uma praia", refs=[(PNG, "image/png"), (PNG, "image/png")], size="1024x1024")
        self.assertEqual(out[0].data, PNG)
        posts = [(path, b) for m, path, b in fake.seen if m == "POST"]
        self.assertEqual([x[0] for x in posts], ["/api/v1/chat/completions"])   # com referências, direto pelo chat
        parts = posts[0][1]["messages"][0]["content"]
        self.assertEqual([x["type"] for x in parts], ["text", "image_url", "image_url"])
        self.assertTrue(parts[1]["image_url"]["url"].startswith("data:image/png;base64,"))

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
