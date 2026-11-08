"""v0.14 — todos os provedores (nuvem e locais) em todas as seções: continuação automática de respostas longas, teto de tokens aprendido e edição automática do Studio."""
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.providers import limits  # noqa: E402
from asta.providers.registry import PRESETS  # noqa: E402
from tests import test_all_providers as base  # noqa: E402  (módulo, não as classes: o loader não repete a bateria geral aqui)

HAVE_FF = base.HAVE_FF

CONTINUE_MARK = "Continue EXACTLY where it stopped"


def _text_of(content):
    return content if isinstance(content, str) else "".join(p.get("text", "") for p in content if isinstance(p, dict))


class LongReplyFake:
    """Servidor falso das duas APIs cuja primeira resposta é cortada pelo limite de tokens («length» / «max_tokens»); a continuação (pedida pelo ASTA) termina."""

    def __init__(self, ceiling=0):
        self.seen = []
        self.ceiling = ceiling   # 0 = sem teto; senão recusa max_tokens maior (como a OpenAI/Anthropic fazem)
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.seen.append((self.path, body))
                anthropic = self.path.endswith("/v1/messages")
                msgs = body.get("messages") or []
                last = _text_of(msgs[-1]["content"]) if msgs else ""
                cont = CONTINUE_MARK in last
                text, reason = ("e o fim da resposta.", "stop") if cont else ("Era uma vez uma resposta muito longa que ", "length")
                mt = int(body.get("max_tokens") or 0)
                if outer.ceiling and mt > outer.ceiling:
                    msg = (f"max_tokens: {mt} > {outer.ceiling}, which is the maximum allowed number of output tokens for this model" if anthropic
                           else f"max_tokens is too large: {mt}. This model supports at most {outer.ceiling} completion tokens, whereas you provided {mt}.")
                    data = json.dumps({"error": {"message": msg}} if not anthropic else {"type": "error", "error": {"type": "invalid_request_error", "message": msg}}).encode()
                    self.send_response(400)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    return self.wfile.write(data)
                if body.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    if anthropic:
                        evs = [("message_start", {"type": "message_start"}), ("content_block_delta", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}}),
                               ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "max_tokens" if reason == "length" else "end_turn"}}), ("message_stop", {"type": "message_stop"})]
                        for ev, obj in evs:
                            self.wfile.write(f"event: {ev}\n".encode() + b"data: " + json.dumps(obj).encode() + b"\n\n")
                    else:
                        for chunk in ({"choices": [{"delta": {"content": text}}]}, {"choices": [{"delta": {}, "finish_reason": reason}]}):
                            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                        self.wfile.write(b"data: [DONE]\n\n")
                    return self.wfile.flush()
                data = json.dumps({"content": [{"type": "text", "text": text}], "stop_reason": "max_tokens" if reason == "length" else "end_turn"} if anthropic
                                  else {"choices": [{"message": {"content": text}, "finish_reason": reason}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class LongLlama:
    """llama-cpp-python falso: primeiro corta pelo limite (finish_reason=length), na continuação termina."""

    def __init__(self, **kw):
        self.kw = kw

    def n_ctx(self):
        return self.kw.get("n_ctx", 4096)

    def tokenize(self, b, add_bos=False):
        return list(b)

    def create_chat_completion(self, messages, temperature=0.8, max_tokens=64, stream=False, **kw):
        cont = CONTINUE_MARK in str(messages[-1]["content"])
        text, reason = ("e o fim da resposta.", "stop") if cont else ("Era uma vez uma resposta muito longa que ", "length")
        if stream:
            return iter([{"choices": [{"delta": {"content": text}}]}, {"choices": [{"delta": {}, "finish_reason": reason}]}])
        return {"choices": [{"message": {"content": text}, "finish_reason": reason}]}


class V014ProvidersTests(base.AllProvidersTests):
    """Reaproveita os auxiliares da bateria geral (use/patched/run_each) com um servidor que corta as respostas."""

    long_fake = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.long_fake = LongReplyFake()

    @classmethod
    def tearDownClass(cls):
        cls.long_fake.close()
        super().tearDownClass()

    def use_long(self, pid, fake=None):
        fake = fake or self.long_fake
        p = PRESETS[pid]
        cfg = {"model": "m", "vision": True}
        if p["kind"] == "anthropic":
            cfg.update(base_url=fake.url, api_key="sk-teste")
        elif p["kind"] == "openai":
            cfg.update(base_url=fake.url + "/v1", api_key="sk-teste" if p.get("needs_key") else "")
        elif p["kind"] == "local_hf":
            cfg.update(model=str(self.store.models_dir / "text" / "m.gguf"))
        self.store.save_settings({"providers": {pid: cfg}, "active": {"generation": pid, "characters": pid}, "performance": {"mode": "light"}, "chat": {"max_tokens": 3000, "continue_rounds": 3, "auto_continue": True}})
        fake.seen.clear()
        limits.forget()

    def patched_long(self, pid):
        if PRESETS[pid]["kind"] != "local_hf":
            return mock.patch("os.getcwd")
        fake = type(sys)("llama_cpp")
        fake.Llama = LongLlama
        from asta.providers import local_llama as ll

        ll._CACHE.clear()
        return mock.patch.dict(sys.modules, {"llama_cpp": fake})

    def test_a_long_reply_continues_by_itself_with_every_provider(self):
        for pid in [i for i in PRESETS if i != "demo"]:
            with self.subTest(provider=pid):
                self.use_long(pid)
                with self.patched_long(pid):
                    _, chat = self.c.json("POST", "/api/chats", {})
                    ev = self.c.sse(f"/api/chats/{chat['id']}/send", {"text": "Escreva uma história bem longa."}, method="POST")
                self.assertFalse([e for e in ev if e["type"] == "error"], f"{pid}: {ev[-3:]}")
                msgs = [e["message"]["text"] for e in ev if e["type"] == "message"]
                self.assertEqual(msgs, ["Era uma vez uma resposta muito longa que e o fim da resposta."], f"{pid}: {msgs}")
                self.assertTrue(any(e["type"] == "notice" and "continuando" in e["message"] for e in ev), pid)
                if PRESETS[pid]["kind"] != "local_hf":
                    self.assertEqual(len(self.long_fake.seen), 2, f"{pid}: a continuação é uma segunda chamada")

    def test_a_reply_size_above_the_models_ceiling_is_adjusted_with_every_cloud_provider(self):
        fake = LongReplyFake(ceiling=4096)
        self.addCleanup(fake.close)
        for pid in [i for i in PRESETS if PRESETS[i]["kind"] in ("openai", "anthropic")]:
            with self.subTest(provider=pid):
                self.use_long(pid, fake)
                self.store.save_settings({"chat": {"max_tokens": 64000, "auto_continue": False}})
                _, chat = self.c.json("POST", "/api/chats", {})
                ev = self.c.sse(f"/api/chats/{chat['id']}/send", {"text": "Escreva muito."}, method="POST")
                self.assertFalse([e for e in ev if e["type"] == "error"], f"{pid}: {ev[-3:]}")
                self.assertTrue([e for e in ev if e["type"] == "message"], pid)
                sizes = [b.get("max_tokens") for _, b in fake.seen]
                self.assertEqual(sizes[0], 64000, pid)       # pediu o que o usuário configurou
                self.assertEqual(sizes[-1], 4096, pid)       # e refez com o teto do modelo, lido do erro
                self.assertTrue(any("4.096" in e["message"] for e in ev if e["type"] == "notice"), pid)
        limits.forget()

    @unittest.skipUnless(HAVE_FF, "ffmpeg não instalado")
    def test_studio_auto_edit_runs_with_every_provider(self):
        from asta.studio import autoedit as AE

        d = Path(tempfile.mkdtemp(prefix="asta-ae-"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=d=6:s=160x90:r=24", "-f", "lavfi", "-i", "sine=f=440:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", str(d / "jogo.mp4")], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=220:d=8", "-c:a", "libmp3lame", str(d / "musica.mp3")], check=True)

        def go(pid):
            ids = []
            for name in ("jogo.mp4", "musica.mp3"):
                data = (d / name).read_bytes()
                import io
                ids.append(self.store.save_upload_stream(name, "", io.BytesIO(data), len(data))["id"])
            ev = []
            result = AE.AutoEditPipeline(self.store, ev.append).run({"attachment_ids": ids, "prompt": "melhores momentos", "style": "gameplay", "target_seconds": 12})
            self.assertTrue(result.get("project_id"), f"{pid}: {result}")
            self.assertFalse([e for e in ev if e.get("type") == "error"], f"{pid}: {ev[-2:]}")
            self.assertTrue(self.store.studio.get(result["project_id"])["episodes"][0]["timeline"]["clips"], pid)
            self.reached_the_provider(pid)
        self.run_each("studio-autoedit", go)


for _n in [n for n in dir(base.AllProvidersTests) if n.startswith("test_") and n not in vars(V014ProvidersTests)]:
    setattr(V014ProvidersTests, _n, None)   # herda só os auxiliares, não repete a bateria geral


if __name__ == "__main__":
    unittest.main()
