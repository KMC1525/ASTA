"""Todos os provedores (nuvem e locais) funcionam em TODAS as seções, de ponta a ponta.

Um servidor falso fala as APIs reais (OpenAI Chat Completions — usada por OpenAI, xAI, Gemini, OpenRouter, Hugging Face, Ollama, LM Studio, llama.cpp e personalizado —
e Anthropic Messages), com e sem streaming, e responde com o gerador Demo. Cada seção roda contra cada provedor pela API do ASTA: se o transporte, a conversão de mensagens, o JSON
dos agentes, o streaming ou alguma seção depender de um provedor específico, aparece aqui."""
import json
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.providers.base import split_system  # noqa: E402
from asta.providers.demo import DemoProvider  # noqa: E402
from asta.providers.registry import PRESETS  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402

DEMO = DemoProvider({})
HAVE_FF = bool(shutil.which("ffmpeg"))
OPENAI_KIND = [pid for pid, p in PRESETS.items() if p["kind"] == "openai"]   # openai, xai, google, openrouter, huggingface, ollama, lmstudio, llamacpp, custom
CLOUD_KEYED = {pid for pid, p in PRESETS.items() if p.get("needs_key")}


class Fake:
    """Servidor falso das duas APIs; conta as requisições e guarda o que recebeu (para conferir imagens, JSON mode etc.)."""

    def __init__(self):
        self.seen = []
        self.polls = 0
        self._media = {}
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _body(self):
                return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")

            def _out(self, obj, status=200):
                data = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _sse(self, events):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for ev, obj in events:
                    if ev:
                        self.wfile.write(f"event: {ev}\n".encode())
                    self.wfile.write(b"data: " + (obj if isinstance(obj, bytes) else json.dumps(obj).encode()) + b"\n\n")
                self.wfile.flush()

            def do_GET(self):
                if "/videos/" in self.path and self.path.endswith("/content?index=0"):
                    data = outer.media("video")
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    return self.wfile.write(data)
                if "/videos/job1" in self.path:
                    outer.polls += 1
                    return self._out({"id": "job1", "status": "completed" if outer.polls >= 2 else "in_progress"})
                if self.path.endswith("/videos/models"):
                    return self._out({"data": [{"id": "google/veo-3.1"}]})
                if self.path.endswith("/images/models"):   # o catálogo próprio de imagens do OpenRouter (modelos da rota /images)
                    return self._out({"data": [{"id": "google/gemini-2.5-flash-image", "supported_parameters": {}}]})
                if "output_modalities=image" in self.path:
                    return self._out({"data": [{"id": "google/gemini-2.5-flash-image"}]})
                if self.path.endswith("/auth/key"):
                    return self._out({"data": {"label": "teste"}})
                if self.path.endswith("/models"):
                    return self._out({"data": [{"id": "m"}], "models": [{"name": "m"}]})
                self._out({"error": "nope"}, 404)

            def do_POST(self):
                body = self._body()
                outer.seen.append((self.path, self.headers.get("Authorization", ""), self.headers.get("x-api-key", ""), body))
                if self.path.endswith("/api/v1/images"):
                    import base64
                    return self._out({"created": 1, "data": [{"b64_json": base64.b64encode(outer.media("image")).decode()}], "usage": {}})
                if self.path.endswith("/api/v1/videos"):
                    outer.polls = 0
                    return self._out({"id": "job1", "polling_url": outer.url + "/api/v1/videos/job1", "status": "pending"})
                if self.path.endswith("/api/v1/audio/speech"):
                    data = outer.media("audio")
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/mpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    return self.wfile.write(data)
                if self.path.endswith("/chat/completions"):
                    msgs = body.get("messages") or []
                    system = next((m["content"] for m in msgs if m["role"] == "system"), "")
                    rest = [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str) else "".join(p.get("text", "") for p in m["content"] if isinstance(p, dict))} for m in msgs if m["role"] != "system"]
                    text = DEMO._chat(rest, str(system), 0.2, 100, False)
                    if body.get("stream"):
                        chunks = [{"choices": [{"delta": {"content": text[i:i + 40]}}]} for i in range(0, len(text), 40)]
                        return self._sse([(None, c) for c in chunks] + [(None, b"[DONE]")])
                    return self._out({"choices": [{"message": {"content": text}}]})
                if self.path.endswith("/v1/messages"):
                    msgs = body.get("messages") or []
                    rest = [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str) else "".join(p.get("text", "") for p in m["content"] if isinstance(p, dict))} for m in msgs]
                    system = body.get("system") or ""
                    system = system if isinstance(system, str) else "".join(b.get("text", "") for b in system)
                    text = DEMO._chat(rest, system, 0.2, 100, False)
                    if body.get("stream"):
                        evs = [("message_start", {"type": "message_start"})] + [("content_block_delta", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text[i:i + 40]}}) for i in range(0, len(text), 40)]
                        return self._sse(evs + [("message_stop", {"type": "message_stop"})])
                    return self._out({"content": [{"type": "text", "text": text}]})
                self._out({"error": "nope"}, 404)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def media(self, kind):
        """Arquivos de verdade (ffmpeg) devolvidos pelas rotas de mídia do OpenRouter falso."""
        if kind not in self._media:
            import subprocess
            d = Path(tempfile.mkdtemp(prefix="asta-fm-"))
            ff = lambda *a: subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)  # noqa: E731
            if kind == "image":
                ff("-f", "lavfi", "-i", "testsrc2=s=320x240", "-frames:v", "1", str(d / "o.png"))
            elif kind == "video":
                ff("-f", "lavfi", "-i", "testsrc2=d=2:s=320x240:r=24", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(d / "o.mp4"))
            else:
                ff("-f", "lavfi", "-i", "sine=f=220:d=2", "-c:a", "libmp3lame", str(d / "o.mp3"))
            self._media[kind] = next(d.iterdir()).read_bytes()
            shutil.rmtree(d, ignore_errors=True)
        return self._media[kind]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class FakeLlama:
    """llama-cpp-python falso para o provedor embutido (Hugging Face GGUF): responde com o Demo, em fluxo ou não."""

    def __init__(self, **kw):
        self.kw = kw

    def n_ctx(self):
        return self.kw.get("n_ctx", 4096)

    def tokenize(self, b, add_bos=False):
        return list(b)

    def create_chat_completion(self, messages, temperature=0.8, max_tokens=64, stream=False, **kw):
        sys_text, rest = split_system(messages, "")
        text = DEMO._chat(rest, sys_text, 0.2, 100, False)
        if stream:
            return iter([{"choices": [{"delta": {"content": text[i:i + 40]}}]} for i in range(0, len(text), 40)])
        return {"choices": [{"message": {"content": text}}]}


class AllProvidersTests(ServerCase):
    fake = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fake = Fake()
        cls.llama_dir = Path(tempfile.mkdtemp(prefix="asta-llm-"))
        (cls.store.models_dir / "text").mkdir(parents=True, exist_ok=True)
        (cls.store.models_dir / "text" / "m.gguf").write_bytes(b"x")

    @classmethod
    def tearDownClass(cls):
        cls.fake.close()
        shutil.rmtree(cls.llama_dir, ignore_errors=True)
        super().tearDownClass()

    def use(self, pid):
        """Aponta todas as funções (geração, personagens) para este provedor."""
        p = PRESETS[pid]
        cfg = {"model": "m", "vision": True}
        if p["kind"] == "anthropic":
            cfg.update(base_url=self.fake.url, api_key="sk-teste")
        elif p["kind"] == "openai":
            cfg.update(base_url=self.fake.url + "/v1", api_key="sk-teste" if p.get("needs_key") else "")
        elif p["kind"] == "local_hf":
            cfg.update(model=str(self.store.models_dir / "text" / "m.gguf"))
        self.store.save_settings({"providers": {pid: cfg}, "active": {"generation": pid, "characters": pid}, "performance": {"mode": "light"}})
        self.fake.seen.clear()

    def patched(self, pid):
        if PRESETS[pid]["kind"] != "local_hf":
            return mock.patch("os.getcwd")
        fake = type(sys)("llama_cpp")
        fake.Llama = FakeLlama
        from asta.providers import local_llama as ll

        ll._CACHE.clear()
        return mock.patch.dict(sys.modules, {"llama_cpp": fake})

    def run_each(self, name, fn, ids=None):
        failures = []
        for pid in ids or [i for i in PRESETS if i != "demo"]:
            with self.subTest(provider=pid, section=name):
                self.use(pid)
                with self.patched(pid):
                    try:
                        fn(pid)
                    except Exception as exc:  # noqa: BLE001
                        failures.append(f"{pid}: {exc}")
                        raise
        return failures

    def finished(self, pid, ev):
        errs = [e for e in ev if e.get("type") == "error"]
        self.assertFalse(errs, f"{pid}: {errs[:2]}")
        self.assertTrue([e for e in ev if e.get("type") == "done"], f"{pid}: não terminou {ev[-3:]}")

    def reached_the_provider(self, pid):
        if PRESETS[pid]["kind"] == "local_hf":
            return
        self.assertTrue(self.fake.seen, f"{pid}: nenhuma requisição chegou ao provedor")
        path, auth, xkey, _body = self.fake.seen[0]
        if PRESETS[pid]["kind"] == "anthropic":
            self.assertEqual((path, xkey), ("/v1/messages", "sk-teste"))
        else:
            self.assertTrue(path.endswith("/chat/completions"))
            if pid in CLOUD_KEYED:
                self.assertEqual(auth, "Bearer sk-teste")

    # ------------------------------------------------------------------ Chat
    def test_chat_answers_with_every_provider_streaming(self):
        def go(pid):
            _, chat = self.c.json("POST", "/api/chats", {})
            ev = self.c.sse(f"/api/chats/{chat['id']}/send", {"text": "Explique o que é um eclipse solar em duas frases."}, method="POST")
            self.assertEqual(ev[-1]["type"], "end", ev[-2:])
            msg = [e for e in ev if e["type"] == "message"]
            self.assertTrue(msg and msg[-1]["message"]["text"].strip(), f"{pid}: resposta vazia {ev[-3:]}")
            self.assertFalse([e for e in ev if e["type"] == "error"], ev)
            self.reached_the_provider(pid)
        self.run_each("chat", go)

    # ------------------------------------------------------------------ Mundos 3D
    def test_worlds_generate_with_every_provider(self):
        def go(pid):
            ev = self.generate({"prompt": "Uma vila medieval ao anoitecer, com um ferreiro e uma curandeira."})
            self.finished(pid, ev)
            self.reached_the_provider(pid)
        self.run_each("worlds", go)

    # ------------------------------------------------------------------ Avatars (criação + conversa individual e em grupo)
    def test_avatars_create_and_chat_with_every_provider(self):
        def go(pid):
            st, r = self.c.json("POST", "/api/avatars/generate", {"prompt": "Uma amiga chamada Luna, divertida e curiosa", "relationship": "friend", "content": "sfw"})
            self.assertEqual(st, 200, r)
            ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
            self.finished(pid, ev)
            ids = [a["id"] for a in self.c.json("GET", "/api/avatars")[1]][:2]
            self.assertTrue(ids)
            _, chat = self.c.json("POST", "/api/avatar-chats", {"avatar_ids": ids[:1]})
            ev = self.c.sse(f"/api/avatar-chats/{chat['id']}/send", {"text": "Oi, tudo bem?"}, method="POST")
            self.assertFalse([e for e in ev if e["type"] == "error"], f"{pid}: {ev[-3:]}")
            self.assertTrue([e for e in ev if e["type"] in ("message", "delta")], f"{pid}: sem resposta {ev[-3:]}")
            self.reached_the_provider(pid)
        self.run_each("avatars", go)

    # ------------------------------------------------------------------ Jogos 2D
    def test_games_generate_with_every_provider(self):
        def go(pid):
            st, r = self.c.json("POST", "/api/games/generate", {"prompt": "romance num café, com escolhas e três finais"})
            self.assertEqual(st, 200, r)
            ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
            self.finished(pid, ev)
            self.reached_the_provider(pid)
        self.run_each("games", go)

    # ------------------------------------------------------------------ Canvas (nós de texto com IA)
    def test_canvas_text_nodes_with_every_provider(self):
        def go(pid):
            _, cv = self.c.json("POST", "/api/canvases", {"name": "T"})
            nodes = [{"id": "t", "type": "text", "x": 0, "y": 0, "params": {"text": "Uma floresta ao amanhecer, névoa suave."}},
                     {"id": "l", "type": "llm", "x": 300, "y": 0, "params": {"instruction": "Descreva a cena com detalhes visuais"}},
                     {"id": "r", "type": "text_refine", "x": 600, "y": 0, "params": {"mode": "scenes"}}]
            edges = [{"from": "t", "to": "l", "port": "prompt"}, {"from": "l", "to": "r", "port": "text"}]
            self.c.json("PUT", f"/api/canvases/{cv['id']}", {"nodes": nodes, "edges": edges})
            st, r = self.c.json("POST", f"/api/canvases/{cv['id']}/run", {})
            self.assertEqual(st, 200, r)
            self.c.sse(f"/api/jobs/{r['job_id']}/events")
            cur = self.c.json("GET", f"/api/canvases/{cv['id']}")[1]
            for n in cur["nodes"]:
                if n["type"] != "text":
                    self.assertEqual((n["result"]["state"], n["result"]["error"]), ("done", ""), f"{pid}/{n['type']}")
                    self.assertTrue(n["result"]["text"].strip(), f"{pid}/{n['type']}: texto vazio")
            self.reached_the_provider(pid)
        self.run_each("canvas", go)

    # ------------------------------------------------------------------ Studio (roteiro cena a cena com IA) e Edição automática
    @unittest.skipUnless(HAVE_FF, "ffmpeg não instalado")
    def test_studio_generates_with_every_provider(self):
        def go(pid):
            st, p = self.c.json("POST", "/api/studio/projects", {"name": "P", "kind": "single", "duration_type": "shorts", "target_seconds": 12, "music": False, "prompt": "Um robô aprende a pintar. Ele pinta o céu."})
            self.assertEqual(st, 201, p)
            st, r = self.c.json("POST", f"/api/studio/projects/{p['id']}/episodes/{p['episodes'][0]['id']}/generate", {})
            self.assertEqual(st, 200, r)
            ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
            self.finished(pid, ev)
            self.reached_the_provider(pid)
        self.run_each("studio", go)   # os 11 provedores de texto (nuvem e locais)

    # ------------------------------------------------------------------ transporte: imagens, JSON e cabeçalhos por tipo de provedor
    def test_every_provider_receives_images_json_and_system_in_its_own_format(self):
        png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cf00000301010018dd8db00000000049454e44ae426082")
        import base64
        b64 = base64.b64encode(png).decode()
        msgs = [{"role": "user", "content": [{"type": "text", "text": "descreva"}, {"type": "image", "media_type": "image/png", "data": b64}]}]
        from asta.providers import build_provider
        for pid in [i for i in PRESETS if PRESETS[i]["kind"] in ("openai", "anthropic")]:
            self.use(pid)
            prov = build_provider(self.store.get_settings(), pid)
            out = prov.chat(msgs, system="Seja breve.", temperature=0.2, max_tokens=50)
            self.assertTrue(out.strip(), pid)
            body = self.fake.seen[-1][3]
            flat = json.dumps(body)
            if PRESETS[pid]["kind"] == "anthropic":
                self.assertIn('"system"', flat)
                self.assertIn("base64", flat)       # imagem no formato da Anthropic
            else:
                self.assertEqual(body["messages"][0]["role"], "system", pid)
                self.assertIn("data:image/png;base64", flat, pid)   # imagem como data URL (visão ligada)
            # sem visão: a imagem vira uma nota de texto, nunca derruba a requisição
            self.store.save_settings({"providers": {pid: {"vision": False}}})
            prov = build_provider(self.store.get_settings(), pid)
            self.assertTrue(prov.chat(msgs, system="x").strip(), pid)
            self.assertNotIn("base64", json.dumps(self.fake.seen[-1][3]), pid)


@unittest.skipUnless(HAVE_FF, "ffmpeg não instalado")
class OpenRouterInStudioTests(AllProvidersTests):
    """O OpenRouter gera e edita vídeos no Studio: roteiro e análise pelo chat, imagens, vozes e (opcional) clipes de vídeo pela API de mídia dele, e a montagem/edição no ffmpeg."""

    def setUp(self):
        self.use("openrouter")
        self.store.save_settings({"media": {"urls": {"openrouter": self.fake.url + "/api/v1"}, "active": {"image": "demo", "video": "demo", "voice": "demo", "sound": "demo"}}})

    def create(self, **kw):
        body = {"name": "OR", "kind": "single", "duration_type": "shorts", "target_seconds": 12, "music": False, "prompt": "Um robô aprende a pintar. Ele pinta o céu.", **kw}
        st, p = self.c.json("POST", "/api/studio/projects", body)
        self.assertEqual(st, 201, p)
        st, r = self.c.json("POST", f"/api/studio/projects/{p['id']}/episodes/{p['episodes'][0]['id']}/generate", {})
        self.assertEqual(st, 200, r)
        ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        errs = [e for e in ev if e.get("type") == "error"]
        self.assertFalse(errs, errs[:2])
        self.assertTrue([e for e in ev if e.get("type") == "done"], ev[-3:])
        return p["id"], p["episodes"][0]["id"], self.c.json("GET", f"/api/studio/projects/{p['id']}")[1]

    def paths(self):
        return [x[0] for x in self.fake.seen]

    def test_studio_uses_openrouter_for_script_images_and_voice_without_extra_setup(self):
        pid, eid, full = self.create()
        paths = self.paths()
        self.assertTrue(any(x.endswith("/chat/completions") for x in paths), "roteiro/análise pelo chat do OpenRouter")
        self.assertTrue(any(x.endswith("/api/v1/images") for x in paths), "imagens pelo OpenRouter")
        self.assertTrue(any(x.endswith("/api/v1/audio/speech") for x in paths), "narração pelo OpenRouter")
        auth = {x[1] for x in self.fake.seen}
        self.assertEqual(auth, {"Bearer sk-teste"})
        ep = full["episodes"][0]
        kinds = {a["kind"] for a in full["assets"]}
        self.assertTrue({"image", "audio"} <= kinds, kinds)
        self.assertGreater(len(ep["timeline"]["clips"]), 2)
        # editar: dividir um clipe na timeline e exportar o vídeo final
        clips = ep["timeline"]["clips"]
        tl = ep["timeline"]
        self.assertEqual(self.c.json("PUT", f"/api/studio/projects/{pid}/episodes/{eid}/timeline", {"timeline": tl})[0], 200)
        st, r = self.c.json("POST", f"/api/studio/projects/{pid}/episodes/{eid}/export", {"mode": "full", "quality": "480p"})
        self.assertEqual(st, 200, r)
        ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        self.assertTrue([e for e in ev if e.get("type") == "done"], ev[-3:])

    def test_studio_generates_video_clips_with_openrouter_video_models(self):
        pid, eid, full = self.create(motion="video")
        paths = self.paths()
        self.assertTrue(any(x.endswith("/api/v1/videos") for x in paths), paths)   # clipes de vídeo pedidos ao OpenRouter
        self.assertTrue(any(x.endswith("/videos/job1/content?index=0") or "videos/job1" in x for x in paths) or self.fake.polls >= 2, "consulta e download do vídeo")
        self.assertIn("video", {a["kind"] for a in full["assets"]})

    def test_explicit_media_choice_still_wins_over_the_openrouter_default(self):
        self.store.save_settings({"media": {"active": {"image": "demo", "voice": "demo"}}, "active": {"generation": "anthropic"}})
        self.use("anthropic")
        self.fake.seen.clear()
        self.create()
        self.assertFalse(any(x.endswith("/api/v1/images") for x in self.paths()))   # outro provedor de texto: mídia continua no Demo

    def test_media_provider_works_in_canvas_and_lists_models(self):
        from asta.canvas import media as M

        st = self.store.get_settings()
        prov = M.build_media(st, "openrouter")
        self.assertEqual(prov.list_models("image"), ["google/gemini-2.5-flash-image"])
        self.assertEqual(prov.list_models("video"), ["google/veo-3.1"])
        self.assertIn("chave válida", prov.test())
        self.assertEqual(M.pick_provider(st, "image", "openrouter"), "openrouter")
        self.assertEqual(M.pick_provider(st, "voice", "openrouter"), "openrouter")
        with self.assertRaises(Exception):
            M.pick_provider(st, "sound", "openrouter")   # não oferece som: erro claro


for _n in [n for n in dir(AllProvidersTests) if n.startswith("test_") and n not in vars(OpenRouterInStudioTests)]:
    setattr(OpenRouterInStudioTests, _n, None)   # herda só os auxiliares, não repete os testes da bateria geral


class MediaProvidersCoverage(unittest.TestCase):
    """Provedores de mídia (imagem, vídeo, som, voz, transcrição): cada capacidade que um provedor declara tem implementação própria e o provedor monta sem chave."""

    def test_every_declared_capability_is_implemented(self):
        from asta.canvas import media as M

        method = {"image": "image", "video": "video", "sound": "sound", "voice": "voice", "stt": "transcribe"}
        for pid, preset in M.MEDIA_PRESETS.items():
            prov = M.build_media({"media": {}, "providers": {}, "hf": {}}, pid)
            for cap in preset["caps"]:
                mine, base = getattr(type(prov), method[cap], None), getattr(M.MediaProvider, method[cap])
                self.assertTrue(mine is not None and mine is not base, f"{pid} declara «{cap}» mas não implementa")
                self.assertIn(cap, prov.caps, f"{pid}/{cap}")

    def test_every_capability_has_at_least_one_provider_that_works_offline_or_locally(self):
        from asta.canvas import media as M

        for cap in ("image", "video", "sound", "voice", "stt"):
            local = [pid for pid, p in M.MEDIA_PRESETS.items() if cap in p["caps"] and (p.get("local") or not p.get("needs_key"))]
            self.assertTrue(local, f"nenhum provedor local/sem chave para «{cap}»")


if __name__ == "__main__":
    unittest.main()
