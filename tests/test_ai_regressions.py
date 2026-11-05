"""Regressões de provedores de IA (nuvem e local) e dos avatars: cada teste aqui cobre um bug que existiu."""
import base64
import contextlib
import io
import json
import os
import random
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import avatar_chat, avatars as av  # noqa: E402
from asta.avatar_chat import ChatEngine  # noqa: E402
from asta.providers import ProviderError, build_provider, http, local_llama  # noqa: E402
from asta.providers.openai_compat import normalize_base  # noqa: E402
from asta.storage import DEFAULT_SETTINGS, Store  # noqa: E402
from tests.helpers import MockProviderServer  # noqa: E402
from tests.test_core import TmpCase  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402


def provider(pid, **user):
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    s["providers"][pid] = user
    return build_provider(s, pid)


@contextlib.contextmanager
def serve(post):
    """Servidor mínimo: `post(handler, body)` responde ao POST."""
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            post(self, json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}"))

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def send_json(h, obj, status=200):
    data = json.dumps(obj).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(data)))
    h.end_headers()
    h.wfile.write(data)


def send_sse(h, chunks):
    h.send_response(200)
    h.send_header("Content-Type", "text/event-stream")
    h.end_headers()
    for c in chunks:
        h.wfile.write(b"data: " + (c if isinstance(c, bytes) else json.dumps(c).encode()) + b"\n\n")
    h.wfile.flush()


class NetworkTests(unittest.TestCase):
    def test_local_servers_never_go_through_the_system_proxy(self):
        """Com HTTP_PROXY definido (rede corporativa), o Ollama/LM Studio em 127.0.0.1 não respondia: o proxy não enxerga a máquina de quem pede."""
        env = {"HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9", "NO_PROXY": "", "no_proxy": ""}
        with MockProviderServer() as m, mock.patch.dict(os.environ, env):
            for pid in ("ollama", "lmstudio", "llamacpp", "custom"):
                p = provider(pid, base_url=m.url + "/v1", model="m")
                self.assertIn("ok", p.chat([{"role": "user", "content": "oi"}]), pid)

    def test_what_counts_as_a_local_host(self):
        for h in ("localhost", "127.0.0.1", "[::1]", "192.168.0.7", "10.1.2.3", "172.16.0.9", "meu-pc.local", "169.254.1.1"):
            self.assertTrue(http.is_local_host(h), h)
        for h in ("api.openai.com", "8.8.8.8", "example.com", "", "172.32.0.1"):
            self.assertFalse(http.is_local_host(h), h)

    def test_address_typed_without_scheme_or_v1(self):
        self.assertEqual(normalize_base("localhost:11434", add_v1=True), "http://localhost:11434/v1")
        self.assertEqual(normalize_base("http://localhost:11434/", add_v1=True), "http://localhost:11434/v1")
        self.assertEqual(normalize_base("http://host:8080/v1/", add_v1=True), "http://host:8080/v1")
        self.assertEqual(normalize_base("https://api.openai.com/v1", add_v1=False), "https://api.openai.com/v1")
        self.assertEqual(normalize_base("https://host/openai", add_v1=True), "https://host/openai")  # com caminho: não mexe
        self.assertEqual(normalize_base("", add_v1=True), "")
        with MockProviderServer() as m:
            for base in (m.url, m.url.replace("http://", ""), m.url + "/"):  # Ollama: o usuário digita a porta e esquece o /v1
                p = provider("ollama", base_url=base, model="m")
                p.chat([{"role": "user", "content": "oi"}])
                self.assertEqual(m.requests[-1]["path"], "/v1/chat/completions", base)
            # provedor hospedado: o endereço do catálogo nunca ganha /v1 a mais
            self.assertEqual(provider("openai", api_key="k").base, "https://api.openai.com/v1")

    def test_invalid_address_gives_a_readable_error(self):
        with self.assertRaises(ProviderError) as cm:
            http.get_json("sem-esquema/aqui")
        self.assertIn("Endereço inválido", str(cm.exception))
        with self.assertRaises(ProviderError) as cm:
            http.get_json("http://127.0.0.1:1/x", timeout=1)
        self.assertIn("127.0.0.1:1", str(cm.exception))  # nome do servidor certo (antes saía só um pedaço do caminho)


class RetryTests(unittest.TestCase):
    """Uma resposta «sobrecarregado» (429/529) no meio da conversa não pode derrubar a mensagem do avatar."""

    def flaky(self, codes, message="Overloaded"):
        calls = []

        def post(h, body):
            calls.append(1)
            code = codes[len(calls) - 1] if len(calls) <= len(codes) else 200
            if code == 200:
                if body.get("stream"):
                    return send_sse(h, [{"choices": [{"delta": {"content": "Oi!"}}]}, b"[DONE]"])
                return send_json(h, {"choices": [{"message": {"content": "Oi!"}}]})
            send_json(h, {"error": {"message": message}}, code)

        return post, calls

    def test_overloaded_responses_are_retried_for_chat_and_stream(self):
        for code in (529, 429, 503):
            post, calls = self.flaky([code])
            with serve(post) as url, mock.patch.object(http.time, "sleep"):
                p = provider("custom", base_url=url + "/v1", model="m")
                self.assertEqual(p.chat([{"role": "user", "content": "oi"}]), "Oi!", code)
                self.assertEqual(len(calls), 2)
        post, calls = self.flaky([529, 529])
        with serve(post) as url, mock.patch.object(http.time, "sleep"):
            p = provider("custom", base_url=url + "/v1", model="m")
            self.assertEqual("".join(p.chat([{"role": "user", "content": "oi"}], stream=True)), "Oi!")
            self.assertEqual(len(calls), 3)

    def test_exhausted_quota_and_other_errors_are_not_retried(self):
        post, calls = self.flaky([429, 429], "You exceeded your current quota, please check your plan and billing details.")
        with serve(post) as url, mock.patch.object(http.time, "sleep") as sleep:
            p = provider("custom", base_url=url + "/v1", model="m")
            with self.assertRaises(ProviderError) as cm:
                p.chat([{"role": "user", "content": "oi"}])
            self.assertEqual((cm.exception.status, len(calls)), (429, 1))
            sleep.assert_not_called()
        post, calls = self.flaky([401, 401], "Incorrect API key")
        with serve(post) as url, mock.patch.object(http.time, "sleep"):
            with self.assertRaises(ProviderError):
                provider("custom", base_url=url + "/v1", model="m").chat([{"role": "user", "content": "oi"}])
            self.assertEqual(len(calls), 1)
        post, calls = self.flaky([503, 503, 503, 503])  # desiste depois de 3 tentativas
        with serve(post) as url, mock.patch.object(http.time, "sleep"):
            with self.assertRaises(ProviderError):
                provider("custom", base_url=url + "/v1", model="m").chat([{"role": "user", "content": "oi"}])
            self.assertEqual(len(calls), 3)

    def test_anthropic_retries_overloaded_too(self):
        calls = []

        def post(h, body):
            calls.append(1)
            if len(calls) == 1:
                return send_json(h, {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}, 529)
            send_json(h, {"content": [{"type": "text", "text": "ok"}]})

        with serve(post) as url, mock.patch.object(http.time, "sleep"):
            self.assertEqual(provider("anthropic", base_url=url, api_key="k", model="c").chat([{"role": "user", "content": "oi"}]), "ok")
        self.assertEqual(len(calls), 2)


class OpenAICompatTests(unittest.TestCase):
    def test_error_in_the_middle_of_the_stream_is_reported_not_swallowed(self):
        def post(h, body):
            send_sse(h, [{"choices": [{"delta": {"content": "Oi"}}]}, {"error": {"message": "rate limit exceeded"}}])

        with serve(post) as url:
            p = provider("custom", base_url=url + "/v1", model="m")
            got = []
            with self.assertRaises(ProviderError) as cm:
                for chunk in p.chat([{"role": "user", "content": "oi"}], stream=True):
                    got.append(chunk)
            self.assertEqual(got, ["Oi"])
            self.assertIn("rate limit", str(cm.exception))

    def test_reply_as_a_list_of_parts_and_null_content(self):
        replies = iter([{"choices": [{"message": {"content": [{"type": "text", "text": "Olá, "}, {"type": "text", "text": "mundo"}]}}]},
                        {"choices": [{"message": {"content": None}}]}])
        with serve(lambda h, b: send_json(h, next(replies))) as url:
            p = provider("custom", base_url=url + "/v1", model="m")
            self.assertEqual(p.chat([{"role": "user", "content": "oi"}]), "Olá, mundo")
            self.assertEqual(p.chat([{"role": "user", "content": "oi"}]), "")


class AnthropicTests(unittest.TestCase):
    def test_temperature_above_one_is_clamped(self):
        """A API da Anthropic só aceita 0 a 1; a interface de avatars deixa até 1,5 (dava erro 400 em toda mensagem)."""
        seen = []

        def post(h, body):
            seen.append(body)
            send_json(h, {"content": [{"type": "text", "text": "ok"}]})

        with serve(post) as url:
            p = provider("anthropic", base_url=url, api_key="k", model="claude-x")
            self.assertEqual(p.chat([{"role": "user", "content": "oi"}], temperature=1.5), "ok")
            p.chat([{"role": "user", "content": "oi"}], temperature=-1)
        self.assertEqual([b["temperature"] for b in seen], [1.0, 0.0])

    def test_stream_error_event_shows_the_message(self):
        def post(h, body):
            h.send_response(200)
            h.send_header("Content-Type", "text/event-stream")
            h.end_headers()
            h.wfile.write(b'event: error\ndata: {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}\n\n')
            h.wfile.flush()

        with serve(post) as url:
            p = provider("anthropic", base_url=url, api_key="k", model="claude-x")
            with self.assertRaises(ProviderError) as cm:
                list(p.chat([{"role": "user", "content": "oi"}], stream=True))
            self.assertEqual(str(cm.exception), "Overloaded")


class FakeLlama:
    """Imita o llama_cpp.Llama: contexto pequeno, tokenizador de 1 token por 4 caracteres e o erro real de estouro de contexto."""

    def __init__(self, ctx=256, fail_response_format=False, boom=None):
        self.ctx, self.fail_rf, self.boom, self.calls = ctx, fail_response_format, boom, []

    def n_ctx(self):
        return self.ctx

    def tokenize(self, data, add_bos=True):
        return list(range(len(data) // 4 + 1))

    def create_chat_completion(self, messages, temperature=0.8, max_tokens=100, stream=False, **kw):
        self.calls.append({"messages": messages, "max_tokens": max_tokens, "kw": kw, "stream": stream})
        if self.boom:
            raise self.boom
        if "response_format" in kw and self.fail_rf:
            raise TypeError("unexpected keyword argument 'response_format'")
        used = sum(len(m["content"]) // 4 + 9 for m in messages)
        if used + 1 > self.ctx:
            raise ValueError(f"Requested tokens ({used}) exceed context window of {self.ctx}")
        if stream:
            return iter([{"choices": [{"delta": {"content": c}}]} for c in ("Oi", "!")])
        return {"choices": [{"message": {"content": "Oi!"}}]}


class LocalLlamaTests(TmpCase):
    def prov(self, llm):
        p = local_llama.LocalLlamaProvider({"model": "m.gguf", "models_dir": str(self.tmp)})
        p._llm = lambda: (llm, "m.gguf")  # type: ignore[method-assign]
        return p

    def test_long_conversations_are_trimmed_to_fit_the_context(self):
        """Antes: conversa longa → ValueError do llama.cpp e o avatar parava de responder."""
        llm = FakeLlama(ctx=256)
        history = []
        for i in range(30):
            history += [{"role": "user", "content": f"pergunta {i} " + "x" * 60}, {"role": "assistant", "content": f"resposta {i} " + "y" * 60}]
        history.append({"role": "user", "content": "última pergunta"})
        p = self.prov(llm)
        self.assertEqual(p.chat(history, system="Você é a Aya.", max_tokens=400), "Oi!")
        sent = llm.calls[0]["messages"]
        self.assertEqual(sent[0], {"role": "system", "content": "Você é a Aya."})  # o prompt do avatar nunca é cortado
        self.assertEqual(sent[-1]["content"], "última pergunta")
        self.assertLess(len(sent), len(history) + 1)
        self.assertEqual(sent[1]["role"], "user")  # depois do sistema vem o usuário (templates estritos)
        self.assertLessEqual(llm.calls[0]["max_tokens"], 128)  # a resposta pedida (400) não pode ocupar mais da metade do contexto
        # streaming também
        self.assertEqual("".join(p.chat(history, system="Você é a Aya.", stream=True)), "Oi!")

    def test_fit_messages_unit(self):
        count = lambda t: len(t)  # noqa: E731
        msgs = [{"role": "system", "content": "s" * 10}] + [{"role": "user" if i % 2 == 0 else "assistant", "content": "m" * 20} for i in range(10)] + [{"role": "user", "content": "fim"}]
        out, mt = local_llama.fit_messages(msgs, count, ctx=200, max_tokens=80)
        self.assertEqual((out[0]["role"], out[-1]["content"]), ("system", "fim"))
        self.assertEqual(mt, 80)
        self.assertLess(len(out), len(msgs))
        self.assertEqual(local_llama.fit_messages(msgs[:3], count, ctx=10_000, max_tokens=50)[0], msgs[:3])  # cabendo, nada muda
        only, _ = local_llama.fit_messages([{"role": "user", "content": "x" * 5000}], count, ctx=100, max_tokens=50)
        self.assertEqual(len(only), 1)  # a pergunta atual entra sempre (o erro de contexto fica por conta do modelo)

    def test_llama_errors_become_provider_errors_with_advice(self):
        with self.assertRaises(local_llama.ContextTooLong) as cm:  # ValueError: os pipelines caem nas regras em vez de falhar o job inteiro
            self.prov(FakeLlama(ctx=64)).chat([{"role": "user", "content": "x" * 4000}], system="s")
        self.assertIsInstance(cm.exception, ValueError)
        self.assertIn("janela de contexto", str(cm.exception))
        with self.assertRaises(ProviderError) as cm:
            list(self.prov(FakeLlama(boom=RuntimeError("llama_decode returned -1"))).chat([{"role": "user", "content": "oi"}], stream=True))
        self.assertIn("modelo local falhou", str(cm.exception))

    def test_json_mode_uses_the_json_grammar_and_falls_back_on_old_versions(self):
        llm = FakeLlama()
        self.prov(llm).chat([{"role": "user", "content": "json"}], json_mode=True)
        self.assertEqual(llm.calls[0]["kw"], {"response_format": {"type": "json_object"}})
        old = FakeLlama(fail_response_format=True)
        self.assertEqual(self.prov(old).chat([{"role": "user", "content": "json"}], json_mode=True), "Oi!")
        self.assertEqual([("response_format" in c["kw"]) for c in old.calls], [True, False])
        plain = FakeLlama()
        self.prov(plain).chat([{"role": "user", "content": "oi"}])
        self.assertEqual(plain.calls[0]["kw"], {})

    def test_list_models_hides_shards_and_vision_projectors(self):
        for n in ("a-Q4_K_M.gguf", "grande-00001-of-00002.gguf", "grande-00002-of-00002.gguf", "mmproj-visao-f16.gguf"):
            (self.tmp / n).write_bytes(b"x")
        self.assertEqual(self.prov(FakeLlama()).list_models(), ["a-Q4_K_M.gguf", "grande-00001-of-00002.gguf"])


class AvatarTextTests(unittest.TestCase):
    def test_markdown_name_prefix_is_removed_completely(self):
        for raw in ("**Aya:** oi tudo bem", "**Aya**: oi tudo bem", "Aya: oi tudo bem", "[Aya]: oi tudo bem", "aya : oi tudo bem", "*Aya:* oi tudo bem"):
            self.assertEqual(av.parse_reply(raw, "Aya", [])["say"], "oi tudo bem", raw)
        self.assertEqual(av.parse_reply("*sorri* Aya: é o meu nome", "Aya", [])["say"], "*sorri* Aya: é o meu nome")  # só o prefixo, e só no começo
        self.assertEqual(av.parse_reply("**Importante:** leve água", "Aya", [])["say"], "**Importante:** leve água")

    def test_mentions_ignore_accents_and_case(self):
        avs = [{"id": "1", "name": "Ana Júlia"}, {"id": "2", "name": "Théo"}]
        self.assertEqual(av.find_mentions("oi julia e theo!", avs), ["1", "2"])
        self.assertEqual(av.find_mentions("OI JÚLIA", avs), ["1"])
        self.assertEqual(av.find_mentions("fala, Theo", avs), ["2"])
        self.assertEqual(av.find_mentions("nada a ver", avs), [])
        self.assertEqual(av.find_mentions("analista", avs), [])  # "ana" só vale como palavra inteira

    def test_minor_detection_catches_how_people_really_write_ages(self):
        for t in ("uma garota de 15 anos", "jovem com 17 anos", "chica de 15 años", "mulher de 16 anos", "15 aninhos", "uma menininha tímida", "a teenager",
                  "adolescente tímida", "colegial de uniforme", "high school student", "criança de 8 anos", "under 18", "menos de 18 anos", "She is 17 years old",
                  "tem 17 anos", "idade: 16", "17 y/o"):
            self.assertTrue(av.declares_minor(t), t)
            c = av.normalize_avatar({"name": "X", "description": t, "content": "nsfw", "relationship": "partner"})
            self.assertEqual((c["content"], c["relationship"]), ("sfw", "friend"), t)  # menor: sempre SFW e só amigo

    def test_minor_detection_does_not_flag_adults_with_numbers_in_the_text(self):
        for t in ("casados há 12 anos", "um casamento de 12 anos", "10 anos de experiência", "Ela tem 30 anos e 2 filhos de 12 anos", "she graduated from high school",
                  "19 anos", "18 years old", "uma amiga de 25 anos", "mother of a 9-year-old son", "a 120 year old wizard", "uma amizade de 15 anos",
                  "tem 2 filhas de 10 anos", "a woman in her twenties", "idade: 24", "mulher de 30 anos"):
            self.assertFalse(av.declares_minor(t), t)

    def test_sillytavern_macros_are_filled_in_prompt_and_greeting(self):
        c = av.normalize_avatar({"name": "Aya", "system_prompt": "Você é {{char}}. {{user}} é seu amigo. <BOT> e <USER>.", "examples": "<START>\n{{user}}: oi\n{{char}}: oi {{user}}!",
                                 "greeting": "Oi, {{user}}! Eu sou a {{char}}."})
        prompt = av.build_system_prompt(c, [], [], "Kaua", "", "sfw")
        self.assertNotIn("{{", prompt)
        self.assertNotIn("<START>", prompt)
        self.assertIn("Você é Aya. Kaua é seu amigo. Aya e Kaua.", prompt)
        self.assertIn("Kaua: oi\nAya: oi Kaua!", prompt)
        self.assertEqual(av.fill_macros("{{ Char }} / {{USER}}", "Aya", r"K\1"), r"Aya / K\1")  # nomes com barra/grupo não quebram a troca
        # o card guardado mantém as macros (a exportação continua compatível)
        self.assertIn("{{char}}", c["system_prompt"])


class ScriptedChat:
    vision = False
    model = "x"

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat(self, messages, system="", temperature=0.8, max_tokens=100, json_mode=False, stream=False):
        self.calls.append(messages)
        return iter(self.reply if isinstance(self.reply, list) else [self.reply])


class ChatEngineTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "home")
        self.engine = ChatEngine(self.store, random.Random(1))
        self.events = []

    def say(self, chat_id, text, reply, cancelled=lambda: False):
        prov = ScriptedChat(reply)
        info = {"id": "x", "label": "x", "model": "x", "demo": False, "auto": False, "reason": ""}
        with mock.patch.object(avatar_chat, "resolve_provider", return_value=(prov, info)):
            self.engine.send(chat_id, text, self.events.append, cancelled)
        return prov

    def avatar(self, name, **kw):
        return self.store.avatars.save({"name": name, "age": 26, **kw})

    def test_empty_answer_in_a_one_to_one_chat_is_an_error_not_silence(self):
        chat = self.engine.create_chat([self.avatar("Aya", greeting="")["id"]])
        self.say(chat["id"], "oi", "")
        err = [e for e in self.events if e["type"] == "error"]
        self.assertEqual(len(err), 1)
        self.assertEqual(err[0]["kind"], "empty")
        self.assertIn("nenhum texto", err[0]["message"])
        self.events.clear()
        self.say(chat["id"], "oi de novo", ["<think>pensando muito", " e nada mais</think>"])  # o limite de tokens acabou no raciocínio
        err = [e for e in self.events if e["type"] == "error"]
        self.assertIn("pensando", err[0]["message"])
        self.assertIn("Máximo de tokens", err[0]["message"])
        self.assertEqual([m["role"] for m in self.store.avatar_chats.get(chat["id"])["messages"]], ["user", "user"])  # nada de mensagem vazia no histórico

    def test_empty_answer_in_a_group_is_just_silence(self):
        a, b = self.avatar("Aya", greeting="")["id"], self.avatar("Bia", greeting="")["id"]
        chat = self.engine.create_chat([a, b])
        self.say(chat["id"], "Aya, oi", "")
        self.assertFalse([e for e in self.events if e["type"] == "error"])
        self.assertTrue([e for e in self.events if e["type"] == "silence"])

    def test_history_never_starts_with_the_avatars_own_greeting(self):
        """Templates estritos (Gemma, Mistral…) exigem começar pelo usuário: a saudação inicial do avatar ficava em primeiro lugar."""
        chat = self.engine.create_chat([self.avatar("Aya", greeting="Oi, eu sou a Aya!")["id"]])
        prov = self.say(chat["id"], "oi", "Oi!")
        roles = [m["role"] for m in prov.calls[0]]
        self.assertEqual(roles, ["user", "assistant", "user"])
        self.assertEqual(prov.calls[0][1]["content"], "Oi, eu sou a Aya!")

    def test_greeting_macros_use_the_user_name(self):
        a = self.avatar("Aya", greeting="Oi, {{user}}! Eu sou a {{char}}.")["id"]
        chat = self.engine.create_chat([a], user_name="Kaua")
        self.assertEqual(self.store.avatar_chats.get(chat["id"])["messages"][0]["text"], "Oi, Kaua! Eu sou a Aya.")

    def test_a_reply_cut_off_by_the_user_is_not_saved(self):
        chat = self.engine.create_chat([self.avatar("Aya", greeting="")["id"]])
        flag = {"stop": False}

        def stream():
            yield "Eu estava dizendo que"
            flag["stop"] = True  # o usuário falou no meio da fala
            yield " isso é importante"

        prov = ScriptedChat([])
        prov.chat = lambda *a, **k: stream()  # type: ignore[method-assign]
        info = {"id": "x", "label": "x", "model": "x", "demo": False, "auto": False, "reason": ""}
        with mock.patch.object(avatar_chat, "resolve_provider", return_value=(prov, info)):
            self.engine.send(chat["id"], "oi", self.events.append, lambda: flag["stop"])
        self.assertEqual([m["role"] for m in self.store.avatar_chats.get(chat["id"])["messages"]], ["user"])
        self.assertTrue([e for e in self.events if e["type"] == "silence"])


class DeleteAvatarTests(TmpCase):
    def test_deleting_an_avatar_cleans_its_conversations(self):
        """Antes ficava uma conversa fantasma que, ao abrir, quebrava a tela do chat."""
        st = Store(self.tmp / "home")
        eng = ChatEngine(st, random.Random(1))
        a, b, c = (st.avatars.save({"name": n, "age": 26, "greeting": f"Oi, sou {n}"})["id"] for n in ("Aya", "Bia", "Caio"))
        solo = eng.create_chat([a])
        pair = eng.create_chat([a, b])
        trio = eng.create_chat([a, b, c])
        other = eng.create_chat([b])
        self.assertTrue(st.delete_avatar(a))
        self.assertIsNone(st.avatar_chats.get(solo["id"]))  # conversa a dois com o avatar apagado some
        p = st.avatar_chats.get(pair["id"])
        self.assertEqual((p["avatar_ids"], p["mode"]), ([b], "single"))  # sobrou um: vira conversa a dois
        t = st.avatar_chats.get(trio["id"])
        self.assertEqual((t["avatar_ids"], t["mode"]), ([b, c], "multi"))
        self.assertNotIn(a, [m.get("avatar_id") for m in t["messages"]])  # as falas do avatar apagado saem do histórico
        self.assertIsNotNone(st.avatar_chats.get(other["id"]))


GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
STRICT_ERR = "'url' field must be a base64 encoded image."


def strict_server(mode="strict"):
    """LM Studio/Ollama exigente: aceita só PNG/JPEG em data URL (mode "strict") ou recusa qualquer imagem (mode "none"), com o erro real."""
    seen = []

    def post(h, body):
        seen.append(body)
        for m in body.get("messages", []):
            if isinstance(m.get("content"), list):
                for part in m["content"]:
                    if part.get("type") != "image_url":
                        continue
                    url = part["image_url"]["url"]
                    head, _, data = url.partition(",")
                    raw = base64.b64decode(data) if data else b""
                    ok = head in ("data:image/png;base64", "data:image/jpeg;base64") and (raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:3] == b"\xff\xd8\xff")
                    if mode == "none" or not ok:
                        return send_json(h, {"error": {"message": STRICT_ERR}}, 400)
        send_json(h, {"choices": [{"message": {"content": "ok"}}]})

    return post, seen


def img(data, media="image/png"):
    return {"type": "image", "media_type": media, "data": base64.b64encode(data).decode()}


def vision_msg(*images):
    return [{"role": "user", "content": [{"type": "text", "text": "descreva"}, *images]}]


class VisionImageTests(unittest.TestCase):
    """Foto no avatar via LM Studio dava «'url' field must be a base64 encoded image» e derrubava a criação."""

    def lm(self, url, **user):
        return provider("lmstudio", base_url=url + "/v1", model="vlm-x", vision=True, **user)

    def test_gif_is_converted_to_png_for_strict_local_servers(self):
        from asta.providers import images as imgs

        if not imgs.shutil.which("ffmpeg"):
            self.skipTest("ffmpeg ausente")
        post, seen = strict_server()
        with serve(post) as url:
            p = self.lm(url)
            self.assertEqual(p.chat(vision_msg(img(GIF, "image/gif"))), "ok")
        part = [x for x in seen[-1]["messages"][-1]["content"] if x.get("type") == "image_url"][0]
        self.assertTrue(part["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(p.images_dropped, 0)

    def test_declared_type_is_replaced_by_the_real_one(self):
        from tests.test_avatars import tiny_png

        post, seen = strict_server()
        with serve(post) as url:
            self.lm(url).chat(vision_msg(img(tiny_png(), "image/jpeg")))  # PNG de verdade, declarado como JPEG
        self.assertTrue([x for x in seen[-1]["messages"][-1]["content"] if x.get("type") == "image_url"][0]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_unconvertible_image_is_left_out_with_a_note_instead_of_failing(self):
        post, seen = strict_server()
        with serve(post) as url:
            with mock.patch("asta.providers.images.to_png", return_value=None):
                p = self.lm(url)
                self.assertEqual(p.chat(vision_msg(img(GIF, "image/gif"))), "ok")
        content = seen[-1]["messages"][-1]["content"]
        self.assertIsInstance(content, str)
        self.assertIn("não pôde", content)
        self.assertEqual(p.images_dropped, 1)

    def test_server_that_refuses_images_gets_a_text_only_retry(self):
        from tests.test_avatars import tiny_png

        post, seen = strict_server("none")
        with serve(post) as url:
            p = self.lm(url)
            self.assertEqual(p.chat(vision_msg(img(tiny_png()))), "ok")
            self.assertEqual(len(seen), 2)
            self.assertIsInstance(seen[1]["messages"][-1]["content"], str)  # sem imagens
            self.assertIn("descreva", seen[1]["messages"][-1]["content"])
            self.assertEqual(p.images_dropped, 1)
            seen.clear()
            self.assertEqual("".join(self.lm(url).chat(vision_msg(img(tiny_png())), stream=True)), "")  # o stream também recua (a resposta de teste não é SSE)
        self.assertEqual(len(seen), 2)

    def test_cloud_providers_keep_every_format(self):
        seen = []

        def post(h, body):
            seen.append(body)
            send_json(h, {"choices": [{"message": {"content": "ok"}}]})

        with serve(post) as url:
            p = provider("custom", base_url=url + "/v1", model="m", vision=True)
            p.allowed_images = None  # como um provedor de nuvem: sem restrição de formato
            p.chat(vision_msg(img(GIF, "image/gif")))
        part = [x for x in seen[-1]["messages"][-1]["content"] if x.get("type") == "image_url"][0]
        self.assertTrue(part["image_url"]["url"].startswith("data:image/gif;base64,"))

    def test_anthropic_gets_the_real_media_type(self):
        from tests.test_avatars import tiny_png

        seen = []

        def post(h, body):
            seen.append(body)
            send_json(h, {"content": [{"type": "text", "text": "ok"}]})

        with serve(post) as url:
            provider("anthropic", base_url=url, api_key="k", model="c").chat(vision_msg(img(tiny_png(), "image/jpeg")))
        self.assertEqual(seen[0]["messages"][0]["content"][0]["source"]["media_type"], "image/png")

    def test_normalize_unit(self):
        from asta.providers import images as imgs

        self.assertEqual(imgs.sniff(GIF), "image/gif")
        self.assertIsNone(imgs.normalize({"media_type": "image/png", "data": ""}))
        self.assertEqual(imgs.normalize({"media_type": "image/png", "data": base64.b64encode(b"\xff\xd8\xffxyz").decode()})["media_type"], "image/jpeg")


class AvatarFromPhotoTests(ServerCase):
    def test_a_server_that_rejects_images_does_not_kill_the_avatar_creation(self):
        """O erro «'url' field must be a base64 encoded image» aparecia no Analista e a criação parava."""
        from tests.test_avatars import tiny_png

        post, seen = strict_server("none")
        with serve(post) as url:
            self.c.json("PUT", "/api/settings", {"providers": {"lmstudio": {"base_url": url + "/v1", "model": "vlm-x", "vision": True}}, "active": {"generation": "lmstudio"}})
            try:
                st, up = self.c.json("POST", "/api/uploads", raw=tiny_png(), headers={"X-Filename": "foto.png", "Content-Type": "image/png"})
                st, r = self.c.json("POST", "/api/avatars/generate", {"prompt": "Uma amiga chamada Luna", "attachment_ids": [up["id"]], "from_images": True, "prompt_pipeline": False})
                ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
            finally:
                self.c.json("PUT", "/api/settings", {"active": {"generation": "demo"}, "providers": {"lmstudio": {"base_url": "", "model": ""}}})
        self.assertFalse([e for e in ev if e["type"] == "error"], [e for e in ev if e["type"] == "error"])
        done = next(e for e in ev if e["type"] == "done")
        self.assertTrue(done["avatar_ids"])
        self.assertTrue(any("imagem" in w and "não puderam" in w for w in done["warnings"]), done["warnings"])


class ChatRoutesTests(ServerCase):
    def test_unexpected_provider_failures_become_an_event_instead_of_a_cut_stream(self):
        aid = self.c.json("POST", "/api/avatars", {"name": "Aya", "age": 26, "greeting": ""})[1]["id"]
        chat = self.c.json("POST", "/api/avatar-chats", {"avatar_ids": [aid]})[1]
        with mock.patch.object(self.app.avatar_routes.engine, "send", side_effect=RuntimeError("llama_decode falhou")), contextlib.redirect_stderr(io.StringIO()):
            ev = self.c.sse(f"/api/avatar-chats/{chat['id']}/send", {"text": "oi"}, method="POST")
        err = next(e for e in ev if e["type"] == "error")
        self.assertEqual(err["kind"], "internal")
        self.assertIn("llama_decode falhou", err["message"])

    def test_malformed_bodies_are_400_not_500(self):
        aid = self.c.json("POST", "/api/avatars", {"name": "Aya", "age": 26})[1]["id"]
        chat = self.c.json("POST", "/api/avatar-chats", {"avatar_ids": [aid]})[1]
        self.assertEqual(self.c.json("POST", "/api/avatar-chats", ["x"])[0], 400)
        self.assertEqual(self.c.json("PUT", f"/api/avatar-chats/{chat['id']}", ["x"])[0], 400)
        self.assertEqual(self.c.json("POST", f"/api/avatar-chats/{chat['id']}/send", ["x"])[0], 400)

    def test_testing_a_provider_with_the_model_field_cleared_does_not_reuse_the_saved_model(self):
        with MockProviderServer() as m:
            self.c.json("PUT", "/api/settings", {"providers": {"custom": {"base_url": m.url + "/v1", "model": "salvo"}}})
            try:
                st, r = self.c.json("POST", "/api/providers/test", {"id": "custom", "config": {"base_url": m.url + "/v1", "model": ""}})
                self.assertFalse(r["ok"])  # sem modelo escolhido: o erro certo, em vez de testar o modelo antigo escondido
                self.assertIn("Nenhum modelo", r["error"])
                st, r = self.c.json("POST", "/api/providers/test", {"id": "custom", "config": {"base_url": m.url + "/v1", "model": "outro"}})
                self.assertTrue(r["ok"])
                self.assertEqual(m.requests[-1]["body"]["model"], "outro")
            finally:
                self.c.json("PUT", "/api/settings", {"providers": {"custom": {"base_url": "", "model": ""}}})


if __name__ == "__main__":
    unittest.main()
