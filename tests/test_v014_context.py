"""v0.14 — janelas de contexto longas (256K/512K/1M) e tamanho das respostas: limites aprendidos, continuação automática, planejador."""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import assistant_chat as ac  # noqa: E402
from asta import avatars as av  # noqa: E402
from asta import native  # noqa: E402
from asta.providers import limits  # noqa: E402
from asta.providers.base import ProviderError  # noqa: E402
from asta.providers.openai_compat import OpenAICompatProvider  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.test_core import TmpCase  # noqa: E402

G = 1 << 30


class LimitsTests(unittest.TestCase):
    def test_reads_the_output_ceiling_from_real_provider_errors(self):
        cases = [
            ("max_tokens is too large: 200000. This model supports at most 16384 completion tokens, whereas you provided 200000.", 200000, 16384),
            ("max_tokens: 100000 > 64000, which is the maximum allowed number of output tokens for claude-sonnet-4-5", 100000, 64000),
            ("Unable to submit request because it has a maxOutputTokens value of 100000 but the supported range is from 1 (inclusive) to 8193 (exclusive)", 100000, 8192),
            ("Invalid max_tokens value, the valid range of max_tokens is [1, 8192]", 20000, 8192),
            ("maximum context length is 128000 tokens. However, you requested 138000 tokens (100000 in the messages, 38000 in the completion)", 38000, 27968),
        ]
        for msg, requested, expected in cases:
            self.assertEqual(limits.fit_from_error(msg, requested), expected, msg)

    def test_ignores_errors_that_are_not_about_the_output_size(self):
        self.assertIsNone(limits.fit_from_error("Rate limited, try again in 20 seconds", 5000))
        self.assertIsNone(limits.fit_from_error("Incorrect API key provided", 5000))
        self.assertIsNone(limits.fit_from_error("maximum context length is 128000 tokens. However, you requested 140000 tokens (130000 in the messages, 10000 in the completion)", 10000))  # o texto enviado já passa da janela
        self.assertIsNone(limits.fit_from_error("max_tokens must be positive", 0))

    def test_known_context_table_is_conservative(self):
        self.assertEqual(limits.known_context("gemini-2.5-pro"), 1_000_000)
        self.assertEqual(limits.known_context("gpt-4.1-mini"), 1_000_000)
        self.assertEqual(limits.known_context("claude-3-5-haiku"), 200_000)
        self.assertEqual(limits.known_context("modelo-que-nao-conheco"), 0)


class _Server:
    """Servidor OpenAI-compatível que recusa `max_tokens` acima de 16384 (como a OpenAI faz) e devolve o motivo de parada."""

    def __init__(self, finish="stop"):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.requests.append(body)
                if int(body.get("max_tokens") or 0) > 16384:
                    data = json.dumps({"error": {"message": f"max_tokens is too large: {body['max_tokens']}. This model supports at most 16384 completion tokens, whereas you provided {body['max_tokens']}."}}).encode()
                    self.send_response(400)
                elif body.get("stream"):
                    data = (b'data: {"choices":[{"delta":{"content":"Texto "}}]}\n\n' + b'data: {"choices":[{"delta":{"content":"cortado"},"finish_reason":"' + finish.encode() + b'"}]}\n\n' + b"data: [DONE]\n\n")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                else:
                    data = json.dumps({"choices": [{"message": {"content": "ok"}, "finish_reason": finish}]}).encode()
                    self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class OutputCeilingTests(unittest.TestCase):
    def setUp(self):
        limits.forget()
        self.srv = _Server()
        self.addCleanup(self.srv.close)
        self.addCleanup(limits.forget)

    def provider(self, model="modelo-limitado"):
        return OpenAICompatProvider({"id": "openai", "base_url": self.srv.url, "api_key": "k", "model": model})

    def test_a_too_large_reply_size_is_retried_at_the_models_ceiling_and_remembered(self):
        p = self.provider()
        self.assertEqual(p.chat([{"role": "user", "content": "oi"}], max_tokens=64000), "ok")
        self.assertEqual([r["max_tokens"] for r in self.srv.requests], [64000, 16384])   # recusou, refez com o teto lido do erro
        self.assertTrue(any("16.384" in n for n in p.notes))
        p2 = self.provider()
        p2.chat([{"role": "user", "content": "de novo"}], max_tokens=64000)
        self.assertEqual(self.srv.requests[-1]["max_tokens"], 16384)   # lembrou: sem nova ida e volta
        self.assertEqual(len(self.srv.requests), 3)

    def test_the_streaming_path_adapts_too(self):
        p = self.provider("outro-modelo")
        self.assertEqual("".join(p.chat([{"role": "user", "content": "oi"}], max_tokens=50000, stream=True)), "Texto cortado")
        self.assertEqual(self.srv.requests[-1]["max_tokens"], 16384)

    def test_the_stop_reason_is_reported(self):
        self.srv.close()
        self.srv = _Server(finish="length")
        p = self.provider("m3")
        self.assertEqual(p.chat([{"role": "user", "content": "oi"}], max_tokens=1000), "ok")
        self.assertEqual(p.last_stop, "length")
        list(p.chat([{"role": "user", "content": "oi"}], max_tokens=1000, stream=True))
        self.assertEqual(p.last_stop, "length")
        self.srv.close()
        self.srv = _Server(finish="stop")
        p = self.provider("m4")
        p.chat([{"role": "user", "content": "oi"}], max_tokens=1000)
        self.assertEqual(p.last_stop, "stop")


class _Prov:
    """Provedor falso: a primeira resposta é cortada pelo limite de tokens; a continuação termina."""

    def __init__(self, parts, stops):
        self.parts, self.stops, self.calls, self.vision, self.last_stop, self.thinking = parts, stops, [], False, "", "off"

    def chat(self, messages, system="", temperature=0.8, max_tokens=100, json_mode=False, stream=False):
        i = len(self.calls)
        self.calls.append({"messages": messages, "system": system, "max_tokens": max_tokens, "thinking": self.thinking})
        self.last_stop = self.stops[i]
        return iter(self.parts[i])


INFO = {"id": "x", "label": "Modelo X", "model": "m1", "demo": False, "auto": False, "reason": ""}


class AutoContinueTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "home")
        self.engine = ac.AssistantChat(self.store)
        self.events = []

    def send(self, prov, text="Explique a fotossíntese em detalhes"):
        chat = self.engine.create()
        with mock.patch.object(ac, "resolve_provider", return_value=(prov, INFO)):
            self.engine.send(chat["id"], text, [], self.events.append, lambda: False)
        return self.store.chats.get(chat["id"])

    def test_a_reply_cut_by_the_token_limit_continues_by_itself(self):
        prov = _Prov([["A fotossíntese ", "é o processo em que as plantas conver"], ["tem luz em energia."]], ["length", "stop"])
        saved = self.send(prov)
        self.assertEqual(saved["messages"][-1]["text"], "A fotossíntese é o processo em que as plantas convertem luz em energia.")   # emendado, sem pedir «continue»
        self.assertEqual(len(prov.calls), 2)
        cont = prov.calls[1]["messages"]
        self.assertEqual(cont[-2], {"role": "assistant", "content": "A fotossíntese é o processo em que as plantas conver"})
        self.assertEqual(cont[-1]["role"], "user")
        self.assertIn("Continue EXACTLY", cont[-1]["content"])
        self.assertEqual(prov.calls[1]["thinking"], "off")   # a continuação não pensa de novo
        self.assertTrue(any(e["type"] == "notice" and "continuando" in e["message"] for e in self.events))
        self.assertEqual([e["type"] for e in self.events][-2:], ["message", "end"])

    def test_it_stops_after_the_configured_number_of_rounds(self):
        self.store.save_settings({"chat": {"continue_rounds": 2}})
        prov = _Prov([["a"], ["b"], ["c"], ["nunca"]], ["length"] * 4)
        saved = self.send(prov)
        self.assertEqual(len(prov.calls), 3)   # 1 resposta + 2 continuações
        self.assertEqual(saved["messages"][-1]["text"], "abc")
        self.assertTrue(any(e["type"] == "notice" and "cortada pelo limite" in e["message"] for e in self.events))   # ainda cortada: avisa o que fazer

    def test_auto_continue_can_be_turned_off(self):
        self.store.save_settings({"chat": {"auto_continue": False}})
        prov = _Prov([["resposta cortada"], ["x"]], ["length", "stop"])
        saved = self.send(prov)
        self.assertEqual(len(prov.calls), 1)
        self.assertEqual(saved["messages"][-1]["text"], "resposta cortada")

    def test_a_normal_reply_does_not_continue(self):
        prov = _Prov([["Tudo certo."]], ["stop"])
        self.send(prov)
        self.assertEqual(len(prov.calls), 1)

    def test_reply_style_changes_the_length_rule_and_detailed_is_the_default(self):
        prov = _Prov([["ok"]], ["stop"])
        self.send(prov)
        self.assertIn("complete, high-quality answers", prov.calls[0]["system"])
        self.assertNotIn("a short question gets a short answer", prov.calls[0]["system"])
        self.store.save_settings({"chat": {"reply_style": "balanced"}})
        prov = _Prov([["ok"]], ["stop"])
        self.send(prov)
        self.assertIn("a short question gets a short answer", prov.calls[0]["system"])
        self.store.save_settings({"chat": {"reply_style": "epic"}})
        prov = _Prov([["ok"]], ["stop"])
        self.send(prov)
        self.assertIn("long, comprehensive", prov.calls[0]["system"])
        self.store.save_settings({"chat": {"reply_style": "lixo"}})   # valor inválido volta ao padrão
        prov = _Prov([["ok"]], ["stop"])
        self.send(prov)
        self.assertIn("complete, high-quality answers", prov.calls[0]["system"])

    def test_reply_size_goes_up_to_128k_and_the_context_to_1m(self):
        self.store.save_settings({"chat": {"max_tokens": 100000, "context_tokens": 1000000, "history_turns": 500}})
        cfg = self.engine._settings()
        self.assertEqual((cfg["max_tokens"], cfg["context_tokens"], cfg["turns"]), (100000, 1000000, 500))
        self.store.save_settings({"chat": {"max_tokens": 9000000}})
        self.assertEqual(self.engine._settings()["max_tokens"], ac.MAX_REPLY_TOKENS)


class AnthropicLongContextTests(unittest.TestCase):
    def test_the_1m_beta_header_is_only_sent_when_asked(self):
        from asta.providers.anthropic import LONG_CONTEXT_BETA, AnthropicProvider
        from tests.helpers import MockProviderServer

        with MockProviderServer() as srv:
            p = AnthropicProvider({"base_url": srv.url, "api_key": "k", "model": "claude-x"})
            p.chat([{"role": "user", "content": "oi"}], max_tokens=100)
            self.assertNotIn("anthropic-beta", srv.requests[-1]["headers"])
            p.long_context = True
            p.chat([{"role": "user", "content": "oi"}], max_tokens=100)
            self.assertEqual(srv.requests[-1]["headers"]["anthropic-beta"], LONG_CONTEXT_BETA)


class LocalLoadTests(TmpCase):
    """O provedor local carrega o modelo com a janela certa: a automática acompanha a resposta pedida, e janelas longas usam o cache de atenção compacto."""

    def provider(self, ll, loads, **cfg):
        class Llama:
            def __init__(self, **kw):
                loads.append(kw)

            def n_ctx(self):
                return loads[-1]["n_ctx"]

            def tokenize(self, b, add_bos=False):
                return list(b)

            def create_chat_completion(self, messages, temperature=0.8, max_tokens=64, stream=False, **kw):
                return {"choices": [{"message": {"content": "ok"}, "finish_reason": "length"}]}

        m = self.tmp / "m.gguf"
        m.write_bytes(b"x")
        ll._CACHE.clear()
        ll._CTX_FLOOR.clear()
        fake = type(sys)("llama_cpp")
        fake.Llama = Llama
        self.addCleanup(ll._CACHE.clear)
        return fake, ll.LocalLlamaProvider({"model": str(m), "models_dir": str(self.tmp), **cfg})

    def test_the_automatic_window_grows_to_fit_the_reply_size_and_never_shrinks(self):
        from asta.providers import local_llama as ll

        loads = []
        fake, p = self.provider(ll, loads)
        hw = {"tier": "low", "ram_gb": 4, "cpus": 2, "gpu": "", "os": "Linux", "arch": "x86_64"}
        with mock.patch.dict(sys.modules, {"llama_cpp": fake}), mock.patch.object(ll, "hardware_info", return_value=hw), mock.patch.object(ll.perf, "memory_state", return_value={"ram_total": 64 << 30, "ram_avail": 48 << 30, "vram_total": 0, "vram_free": 0, "unified": False, "phys": 4, "logical": 8, "features": []}):
            p.chat([{"role": "user", "content": "oi"}], max_tokens=300)
            small = loads[-1]["n_ctx"]
            p.chat([{"role": "user", "content": "oi"}], max_tokens=6000)   # resposta de 6K: a janela automática (2048 no PC fraco) não cabe
            big = loads[-1]["n_ctx"]
            self.assertGreaterEqual(big, 2 * 6000)
            self.assertGreater(big, small)
            n = len(loads)
            p.chat([{"role": "user", "content": "oi"}], max_tokens=300)   # voltar a uma resposta curta não recarrega o modelo
            self.assertEqual(len(loads), n)
            self.assertEqual(p.last_stop, "length")

    def test_an_explicit_window_is_never_changed_by_the_reply_size(self):
        from asta.providers import local_llama as ll

        loads = []
        fake, p = self.provider(ll, loads, n_ctx=8192)
        with mock.patch.dict(sys.modules, {"llama_cpp": fake}), mock.patch.object(ll, "hardware_info", return_value={"tier": "low", "ram_gb": 4, "cpus": 2, "gpu": "", "os": "Linux", "arch": "x86_64"}):
            p.chat([{"role": "user", "content": "oi"}], max_tokens=6000)
        self.assertEqual(loads[-1]["n_ctx"], 8192)

    def test_a_1m_window_loads_with_the_4_bit_attention_cache(self):
        from asta.providers import local_llama as ll

        loads = []
        fake, p = self.provider(ll, loads, n_ctx=1048576)
        info = {"bytes": 5 * G, "layers": 32, "kv_bytes_per_token": 131072, "ctx_train": 1048576, "arch": "llama", "name": "x", "quant": "Q4_K_M", "params": 8e9}
        mem = {"ram_total": 64 * G, "ram_avail": 64 * G, "vram_total": 0, "vram_free": 0, "unified": False, "phys": 8, "logical": 16, "features": []}
        with mock.patch.dict(sys.modules, {"llama_cpp": fake}), mock.patch.object(ll.native, "model_info", return_value=info), mock.patch.object(ll.perf, "memory_state", return_value=mem), \
                mock.patch.object(ll, "hardware_info", return_value={"tier": "high", "ram_gb": 64, "cpus": 16, "gpu": "", "os": "Linux", "arch": "x86_64"}):
            p.chat([{"role": "user", "content": "oi"}], max_tokens=2000)
        kw = loads[-1]
        self.assertEqual(kw["n_ctx"], 1048576)
        self.assertEqual((kw["type_k"], kw["type_v"], kw["flash_attn"]), (2, 2, True))   # 2 = GGML_TYPE_Q4_0


class _TeamProv:
    """Provedor falso para a equipe de agentes: responde conforme o papel (planejador, revisor ou redator), olhando o prompt de sistema."""

    def __init__(self, review_notes="OK", planner_fails=False):
        self.calls, self.vision, self.last_stop, self.thinking = [], False, "", "off"
        self.review_notes, self.planner_fails = review_notes, planner_fails

    def chat(self, messages, system="", temperature=0.8, max_tokens=100, json_mode=False, stream=False):
        role = "planner" if "Planner of a team" in system else "reviewer" if "Reviewer of a team" in system else "revise" if "Reviewer found" in str(messages[-1]["content"]) else "writer"
        self.calls.append({"role": role, "stream": stream, "system": system, "messages": messages})
        if role == "planner":
            if self.planner_fails:
                from asta.providers.base import ProviderError
                raise ProviderError("planejador fora do ar")
            return "1. Conceito\n2. Passo a passo\n3. Cuidados"
        if role == "reviewer":
            return self.review_notes
        return iter(["Rascunho." if role == "writer" else "Texto melhorado e completo."])


class AgentTeamTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "home")
        self.engine = ac.AssistantChat(self.store)
        self.events = []

    def send(self, prov, mode):
        self.store.save_settings({"chat": {"agents": mode}})
        chat = self.engine.create()
        with mock.patch.object(ac, "resolve_provider", return_value=(prov, INFO)):
            self.engine.send(chat["id"], "Como faço pão caseiro?", [], self.events.append, lambda: False)
        return self.store.chats.get(chat["id"])["messages"][-1]["text"]

    def test_off_is_the_default_and_calls_only_the_writer(self):
        prov = _TeamProv()
        self.assertEqual(self.send(prov, "off"), "Rascunho.")
        self.assertEqual([c["role"] for c in prov.calls], ["writer"])

    def test_plan_mode_hands_the_outline_to_the_writer(self):
        prov = _TeamProv()
        self.assertEqual(self.send(prov, "plan"), "Rascunho.")
        self.assertEqual([c["role"] for c in prov.calls], ["planner", "writer"])
        self.assertIn("ANSWER PLAN", prov.calls[1]["system"])
        self.assertIn("2. Passo a passo", prov.calls[1]["system"])
        self.assertFalse(prov.calls[0]["stream"])   # o planejador não é mostrado ao usuário
        self.assertTrue(any(e["type"] == "notice" and "Planejador" in e["message"] for e in self.events))

    def test_review_mode_keeps_a_good_draft(self):
        prov = _TeamProv(review_notes="OK")
        self.assertEqual(self.send(prov, "review"), "Rascunho.")
        self.assertEqual([c["role"] for c in prov.calls], ["planner", "writer", "reviewer"])

    def test_review_mode_rewrites_once_when_the_reviewer_finds_gaps(self):
        prov = _TeamProv(review_notes="- falta o tempo de forno\n- passo 3 vago")
        self.assertEqual(self.send(prov, "review"), "Texto melhorado e completo.")
        self.assertEqual([c["role"] for c in prov.calls], ["planner", "writer", "reviewer", "revise"])
        self.assertIn("falta o tempo de forno", str(prov.calls[3]["messages"][-1]["content"]))
        types = [e["type"] for e in self.events]
        self.assertIn("reset", types)   # a tela troca o rascunho pelo texto melhorado
        self.assertEqual(types[-2:], ["message", "end"])

    def test_a_failing_planner_never_breaks_the_conversation(self):
        prov = _TeamProv(planner_fails=True)
        self.assertEqual(self.send(prov, "review"), "Rascunho.")
        self.assertNotIn("ANSWER PLAN", prov.calls[-1]["system"])

    def test_invalid_mode_falls_back_to_off(self):
        self.store.save_settings({"chat": {"agents": "lixo"}})
        self.assertEqual(self.engine._settings()["agents"], "off")


class TrimTests(unittest.TestCase):
    def test_a_cut_reply_ends_at_the_last_complete_sentence(self):
        self.assertEqual(av.trim_to_sentence("Olá! Tudo bem? Eu estava pensando em voc"), "Olá! Tudo bem?")
        self.assertEqual(av.trim_to_sentence("Frase completa."), "Frase completa.")
        self.assertEqual(av.trim_to_sentence("Sem pontuação alguma e cortada"), "Sem pontuação alguma e cortada")   # nada a aparar: mantém


class LongContextPlannerTests(unittest.TestCase):
    def plan(self, **kw):
        a = dict(weights=5 * G, layers=32, kv_per_token=131072, ctx_train=1048576, ctx_want=1048576, explicit=True, ctx_cap=0, ram_avail=64 * G, vram_free=0, unified=False, phys=8, logical=16, mode=1)
        a.update(kw)
        return native.plan_llm(**a)

    def test_1m_context_falls_back_to_a_4_bit_cache_when_8_bit_does_not_fit(self):
        r = self.plan(ram_avail=64 * G)   # 1M tokens × 128 KiB = 128 GiB em f16, 68 GiB em 8 bits, ≈ 36 GiB em 4 bits
        self.assertTrue(r["kv_q8"] and r["kv_q4"] and r["flash"])
        self.assertEqual(r["n_ctx"], 1048576)   # o que o usuário pediu vale
        self.assertTrue(any("4 bits" in n for n in r["notes"]))
        self.assertGreater(r["ctx_max"], 700000)

    def test_a_256k_window_only_needs_the_8_bit_cache_with_enough_memory(self):
        r = self.plan(ctx_want=262144, ram_avail=40 * G)   # f16 (32 GiB + pesos) não cabe; em 8 bits cabe
        self.assertTrue(r["kv_q8"] and not r["kv_q4"])

    def test_a_short_window_never_uses_the_4_bit_cache(self):
        r = self.plan(ctx_want=16384, ctx_train=32768, ram_avail=4 * G, explicit=False)
        self.assertFalse(r["kv_q4"])

    def test_asking_for_more_than_the_model_was_trained_on_warns(self):
        r = self.plan(ctx_want=524288, ctx_train=131072, ram_avail=256 * G)
        self.assertEqual(r["n_ctx"], 524288)   # nunca contraria o usuário
        self.assertTrue(any("foi treinado" in n for n in r["notes"]))

    def test_the_automatic_window_is_capped_at_what_was_trained(self):
        r = self.plan(ctx_want=1048576, ctx_train=131072, explicit=False, ram_avail=256 * G)
        self.assertEqual(r["n_ctx"], 131072)


if __name__ == "__main__":
    unittest.main()
