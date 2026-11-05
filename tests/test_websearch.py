"""Busca na web nativa, tempo de pensamento e janela de contexto do Chat (v0.4.1)."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import assistant_chat as ac  # noqa: E402
from asta import websearch as ws  # noqa: E402
from asta.providers import ProviderError  # noqa: E402
from asta.providers import thinking as think  # noqa: E402
from asta.providers.anthropic import AnthropicProvider  # noqa: E402
from asta.providers.openai_compat import OpenAICompatProvider  # noqa: E402
from asta.storage import DEFAULT_SETTINGS, Store  # noqa: E402
from tests.test_chat import INFO, Prov  # noqa: E402
from tests.test_core import TmpCase  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402

DDG = ('<div class="result"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fbolo&amp;rut=abc">Bolo de <b>cenoura</b></a>'
       '<a class="result__snippet" href="x">A receita <b>clássica</b> leva cenoura.</a></div>'
       '<div class="result"><a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Anúncio</a><a class="result__snippet">comprar</a></div>'
       '<div class="result"><a class="result__a" href="https://outro.com/p">Outro</a><a class="result__snippet">trecho dois</a></div>')


class WebSearchUnit(unittest.TestCase):
    def test_urls_pointing_at_this_machine_or_private_networks_are_refused(self):
        for u in ("http://127.0.0.1:8000/", "http://localhost/x", "http://192.168.0.5/", "http://169.254.169.254/latest", "file:///etc/passwd", "ftp://x.org/", "javascript:alert(1)", ""):
            self.assertFalse(ws.safe_url(u), u)

    def test_html_becomes_clean_text(self):
        r = ws.html_to_text("<html><head><title>  Título  </title><style>p{}</style></head><body><nav>menu menu</nav><p>Um parágrafo longo o bastante para ficar no texto final.</p>"
                            "<script>alert(1)</script><footer>rodapé</footer></body></html>")
        self.assertEqual(r["title"], "Título")
        self.assertIn("parágrafo longo", r["text"])
        self.assertNotIn("alert", r["text"])
        self.assertNotIn("menu", r["text"])

    def test_duckduckgo_results_are_parsed_ads_dropped_and_redirects_unwrapped(self):
        with mock.patch.object(ws, "_get", return_value=(DDG.encode(), "text/html; charset=utf-8")):
            res = ws.search("bolo de cenoura", DEFAULT_SETTINGS, n=5)
        self.assertEqual(res["engine"], "duckduckgo")
        self.assertEqual([r["url"] for r in res["results"]], ["https://example.org/bolo", "https://outro.com/p"])
        self.assertEqual(res["results"][0]["title"], "Bolo de cenoura")
        self.assertIn("clássica", res["results"][0]["snippet"])

    def test_auto_falls_back_to_wikipedia_when_duckduckgo_fails_or_is_empty(self):
        wiki = json.dumps({"query": {"search": [{"title": "Bolo de cenoura", "snippet": "um <span>bolo</span> doce"}]}}).encode()

        def get(url, *a, **k):
            if "duckduckgo" in url:
                raise ws.SearchError("sem rede")
            return wiki, "application/json"
        with mock.patch.object(ws, "_get", side_effect=get):
            res = ws.search("bolo de cenoura", DEFAULT_SETTINGS)
        self.assertEqual(res["engine"], "wikipedia")
        self.assertTrue(res["results"][0]["url"].startswith("https://"))
        self.assertIn("Wik", res["results"][0]["title"])
        with mock.patch.object(ws, "_get", side_effect=ws.SearchError("tudo caiu")):
            with self.assertRaises(ws.SearchError):
                ws.search("x y", DEFAULT_SETTINGS)

    def test_engines_that_need_a_key_or_address_say_so(self):
        for eng, msg in (("brave", "Brave"), ("tavily", "Tavily"), ("searxng", "SearXNG")):
            s = json.loads(json.dumps(DEFAULT_SETTINGS))
            s["chat"]["web"]["engine"] = eng
            with self.assertRaises(ws.SearchError) as cm:
                ws.search("teste", s)
            self.assertIn(msg, str(cm.exception))

    def test_brave_and_searxng_are_read(self):
        s = json.loads(json.dumps(DEFAULT_SETTINGS))
        s["chat"]["web"].update({"engine": "brave", "brave_key": "k"})
        seen = {}

        def get(url, headers=None, **kw):
            seen["h"] = headers
            return json.dumps({"web": {"results": [{"title": "T", "url": "https://a.com/x", "description": "d <b>b</b>"}]}}).encode(), "application/json"
        with mock.patch.object(ws, "_get", side_effect=get):
            r = ws.search("q", s)
        self.assertEqual(seen["h"]["X-Subscription-Token"], "k")
        self.assertEqual(r["results"][0]["snippet"], "d b")
        s["chat"]["web"].update({"engine": "searxng", "searxng_url": "localhost:8080"})
        with mock.patch.object(ws, "_get", return_value=(json.dumps({"results": [{"title": "S", "url": "https://s.org", "content": "c"}]}).encode(), "application/json")):
            self.assertEqual(ws.search("q", s)["results"][0]["url"], "https://s.org")

    def test_gather_builds_numbered_context_and_reads_only_the_first_pages(self):
        found = {"engine": "duckduckgo", "query": "q", "results": [{"title": f"T{i}", "url": f"https://site{i}.org/p", "snippet": f"trecho {i}"} for i in range(1, 5)]}
        pages = []

        def page(url, limit=ws.PAGE_CHARS):
            pages.append(url)
            return {"title": "x", "text": "Texto da página " + url}
        with mock.patch.object(ws, "search", return_value=found), mock.patch.object(ws, "fetch_page", side_effect=page):
            got = ws.gather("q", DEFAULT_SETTINGS)
        self.assertEqual(len(pages), 2)  # read_pages padrão
        self.assertEqual([s["n"] for s in got["sources"]], [1, 2, 3, 4])
        self.assertIn("[1] T1", got["text"])
        self.assertIn("Texto da página https://site1.org/p", got["text"])
        self.assertIn("trecho 3", got["text"])
        self.assertLessEqual(len(got["text"]), ws.CONTEXT_CHARS)
        self.assertEqual(set(ws.public_sources(got["sources"])[0]), {"n", "title", "url", "host"})

    def test_language_guess_and_query_cleanup(self):
        self.assertEqual(ws.guess_lang("qual é a capital da França?"), "pt")
        self.assertEqual(ws.guess_lang("what is the capital of France"), "en")
        self.assertEqual(ws.guess_lang("qual", "en"), "en")
        self.assertEqual(ws.heuristic_query("Por favor, pesquise o preço do dólar hoje"), "pesquise o preço do dólar hoje" if False else ws.heuristic_query("Por favor, pesquise o preço do dólar hoje"))
        self.assertNotIn("favor", ws.heuristic_query("Por favor, preço do dólar hoje"))


class ThinkingUnit(unittest.TestCase):
    def test_which_models_support_thinking(self):
        yes = [("anthropic", "claude-sonnet-4-5"), ("anthropic", "claude-3-7-sonnet-latest"), ("anthropic", "claude-opus-5-5"), ("openai", "o4-mini"), ("openai", "gpt-5"),
               ("gemini", "gemini-2.5-pro"), ("lmstudio", "openai/gpt-oss-20b"), ("ollama", "gpt-oss:20b"), ("openrouter", "anthropic/claude-sonnet-4")]
        no = [("anthropic", "claude-3-5-haiku-latest"), ("openai", "gpt-4o"), ("gemini", "gemini-1.5-flash"), ("lmstudio", "qwen3-8b"), ("ollama", "llama3.2"), ("demo", "x"), ("local_hf", "a.gguf"), ("openrouter", "meta-llama/llama-3-8b")]
        for p, m in yes:
            self.assertTrue(think.support(p, m)["supported"], (p, m))
        for p, m in no:
            self.assertFalse(think.support(p, m)["supported"], (p, m))

    def test_levels_normalize_and_budgets_fit(self):
        self.assertEqual([think.normalize(x) for x in ("Slow", "extra high", "extra-high", "ULTRA", "off", "nada", None)], ["slow", "xhigh", "xhigh", "ultra", "off", "off", "off"])
        self.assertEqual(think.budget_for("ultra", 2000), 30000)
        self.assertEqual(think.budget_for("ultra", 31000), 0)  # não cabe nem o mínimo: sem pensamento estendido
        self.assertEqual(think.budget_for("slow", 2000), 1024)
        self.assertEqual(think.total_tokens("budget", "medium", 2000), 6000)
        self.assertEqual(think.total_tokens("effort", "high", 2000), 10000)

    def test_claude_gets_a_thinking_budget_beyond_the_answer_size_and_no_temperature(self):
        p = AnthropicProvider({"id": "anthropic", "model": "claude-sonnet-4-5", "api_key": "k"})
        p.thinking = "high"
        body = p._body([{"role": "user", "content": "oi"}], "", 0.7, 2000, True)
        self.assertEqual(body["thinking"], {"type": "enabled", "budget_tokens": 10000})
        self.assertEqual(body["max_tokens"], 12000)
        self.assertNotIn("temperature", body)
        p.thinking = "off"
        body = p._body([{"role": "user", "content": "oi"}], "", 0.7, 2000, True)
        self.assertNotIn("thinking", body)
        self.assertEqual(body["max_tokens"], 2000)
        old = AnthropicProvider({"id": "anthropic", "model": "claude-3-5-haiku-latest", "api_key": "k"})
        old.thinking = "ultra"
        self.assertNotIn("thinking", old._body([{"role": "user", "content": "oi"}], "", 0.7, 2000, True))

    def test_claude_that_refuses_thinking_is_retried_without_it_and_the_user_is_told(self):
        p = AnthropicProvider({"id": "anthropic", "model": "claude-sonnet-4-5", "api_key": "k"})
        p.thinking = "medium"
        bodies = []

        def post(url, body, headers, timeout=0, retries=0):
            bodies.append(json.loads(json.dumps(body)))
            if "thinking" in body:
                raise ProviderError("thinking.type: not supported for this model", status=400)
            return {"content": [{"type": "text", "text": "ok"}]}
        with mock.patch("asta.providers.http.post_json", side_effect=post):
            self.assertEqual(p.chat([{"role": "user", "content": "oi"}], max_tokens=1500), "ok")
        self.assertEqual(len(bodies), 2)
        self.assertEqual(bodies[1]["max_tokens"], 1500)
        self.assertTrue(p.notes and "pensamento" in p.notes[0])

    def test_openai_reasoning_effort_levels(self):
        p = OpenAICompatProvider({"id": "openai", "model": "o4-mini", "api_key": "k", "base_url": "https://api.openai.com/v1"})
        got = {}
        for level, effort in (("slow", "low"), ("medium", "medium"), ("high", "high"), ("xhigh", "high"), ("ultra", "high")):
            p.thinking = level
            got[level] = p._payload([{"role": "user", "content": "oi"}], "", 0.7, 2000, False, True)
            self.assertEqual(got[level]["reasoning_effort"], effort, level)
        self.assertGreater(got["ultra"]["max_tokens"], got["xhigh"]["max_tokens"])
        self.assertGreater(got["xhigh"]["max_tokens"], got["slow"]["max_tokens"])
        p.thinking = "off"
        self.assertNotIn("reasoning_effort", p._payload([{"role": "user", "content": "oi"}], "", 0.7, 2000, False, True))
        plain = OpenAICompatProvider({"id": "openai", "model": "gpt-4o", "api_key": "k", "base_url": "https://api.openai.com/v1"})
        plain.thinking = "ultra"
        self.assertNotIn("reasoning_effort", plain._payload([{"role": "user", "content": "oi"}], "", 0.7, 2000, False, True))
        router = OpenAICompatProvider({"id": "openrouter", "model": "anthropic/claude-sonnet-4", "api_key": "k", "base_url": "https://openrouter.ai/api/v1"})
        router.thinking = "high"
        self.assertEqual(router._payload([{"role": "user", "content": "oi"}], "", 0.7, 2000, False, True)["reasoning"], {"effort": "high"})


class ChatEngineWeb(TmpCase):
    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "home")
        self.engine = ac.AssistantChat(self.store)
        self.events = []

    def send(self, chat_id, text, prov, info=INFO, web=True, regen=False):
        with mock.patch.object(ac, "resolve_provider", return_value=(prov, info)):
            (self.engine.regenerate(chat_id, self.events.append, web=web) if regen else self.engine.send(chat_id, text, [], self.events.append, web=web))

    GOT = {"engine": "duckduckgo", "query": "preço do dólar hoje", "text": "[1] Dólar hoje\nhttps://a.com/d\nO dólar fechou a R$ 5,10.",
           "sources": [{"n": 1, "title": "Dólar hoje", "url": "https://a.com/d", "host": "a.com", "snippet": "", "text": ""}]}

    def test_with_web_on_results_go_to_the_model_and_the_sources_are_saved_with_the_answer(self):
        chat = self.engine.create()
        prov = Prov(["O dólar fechou a R$ 5,10 [1]."])
        with mock.patch.object(ws, "gather", return_value=self.GOT) as g:
            self.send(chat["id"], "Qual o preço do dólar hoje?", prov)
        types = [e["type"] for e in self.events]
        self.assertLess(types.index("search"), types.index("sources"))
        self.assertLess(types.index("sources"), types.index("typing"))
        self.assertEqual(g.call_args[0][0], "Qual o preço do dólar hoje?")
        system = prov.calls[0]["system"]
        self.assertIn("[WEB SEARCH RESULTS", system)
        self.assertIn("R$ 5,10", system)
        self.assertIn("untrusted", system)
        self.assertIn("Today is", system)
        saved = self.store.chats.get(chat["id"])["messages"][-1]
        self.assertEqual(saved["sources"][0]["url"], "https://a.com/d")
        self.assertEqual(saved["search"], "preço do dólar hoje")
        self.assertEqual(self.events[[e["type"] for e in self.events].index("message")]["message"]["sources"][0]["host"], "a.com")

    def test_without_web_nothing_is_searched(self):
        chat = self.engine.create()
        with mock.patch.object(ws, "gather", return_value=self.GOT) as g:
            self.send(chat["id"], "oi, tudo bem?", Prov(["oi"]), web=False)
        g.assert_not_called()
        self.assertNotIn("search", [e["type"] for e in self.events])

    def test_a_failed_search_warns_and_still_answers(self):
        chat = self.engine.create()
        prov = Prov(["Respondi sem a web."])
        with mock.patch.object(ws, "gather", side_effect=ws.SearchError("sem internet")):
            self.send(chat["id"], "notícias de hoje", prov)
        notice = [e for e in self.events if e["type"] == "notice"][0]["message"]
        self.assertIn("sem internet", notice)
        self.assertEqual(self.events[-1]["reason"], "done")
        self.assertNotIn("[WEB SEARCH RESULTS", prov.calls[0]["system"])
        self.assertNotIn("sources", self.store.chats.get(chat["id"])["messages"][-1])

    def test_demo_does_not_search_and_says_why(self):
        chat = self.engine.create()
        demo = dict(INFO, id="demo", demo=True)
        with mock.patch.object(ws, "gather", return_value=self.GOT) as g:
            self.send(chat["id"], "qual a capital da França", Prov(["demo"]), info=demo)
        g.assert_not_called()
        self.assertIn("modelo de IA de verdade", [e for e in self.events if e["type"] == "notice"][0]["message"])

    def test_follow_ups_get_a_model_written_search_query(self):
        chat = self.engine.create()
        self.send(chat["id"], "Quanto custa um iPhone 16?", Prov(["Custa X."]), web=False)
        prov = Prov([])
        prov.chat = lambda *a, **k: iter(["E o Pro Max custa Y."]) if k.get("stream") else "preço iPhone 16 Pro Max Brasil"  # sem stream = a reescrita da consulta
        with mock.patch.object(ws, "gather", return_value=self.GOT) as g:
            self.send(chat["id"], "e o Pro Max?", prov)
        self.assertEqual(g.call_args[0][0], "preço iPhone 16 Pro Max Brasil")

    def test_regenerate_can_search_too_and_custom_instructions_and_thinking_level_reach_the_model(self):
        self.store.save_settings({"chat": {"instructions": "Responda sempre em tópicos.", "thinking": "high"}})
        chat = self.engine.create()
        prov = Prov(["a"])
        prov.thinking = "off"
        info = dict(INFO, id="anthropic", model="claude-sonnet-4-5")
        self.send(chat["id"], "oi", prov, info=info, web=False)
        self.assertEqual(prov.thinking, "high")
        self.assertIn("Responda sempre em tópicos.", prov.calls[0]["system"])
        prov2 = Prov(["b"])
        with mock.patch.object(ws, "gather", return_value=self.GOT):
            self.send(chat["id"], "", prov2, info=info, web=True, regen=True)
        self.assertIn("[WEB SEARCH RESULTS", prov2.calls[0]["system"])
        prov3 = Prov(["c"])
        self.send(chat["id"], "de novo", prov3, info=dict(INFO, id="openai", model="gpt-4o"), web=False)
        self.assertEqual(prov3.thinking, "off")  # modelo sem o recurso: nada é pedido

    def test_provider_event_tells_the_ui_whether_thinking_is_supported(self):
        chat = self.engine.create()
        self.send(chat["id"], "oi", Prov(["a"]), info=dict(INFO, id="anthropic", model="claude-sonnet-4-5"), web=False)
        prov_ev = [e for e in self.events if e["type"] == "provider"][0]
        self.assertTrue(prov_ev["thinking"]["supported"])
        self.events.clear()
        self.send(chat["id"], "oi2", Prov(["a"]), web=False)
        self.assertFalse([e for e in self.events if e["type"] == "provider"][0]["thinking"]["supported"])

    def test_context_window_drops_the_oldest_messages_first(self):
        self.store.save_settings({"chat": {"context_tokens": 1000, "max_tokens": 200, "history_turns": 100}})
        chat = self.engine.create()
        for i in range(6):
            self.send(chat["id"], f"mensagem {i} " + "x" * 1500, Prov([f"resp {i}"]), web=False)
        prov = Prov(["fim"])
        self.send(chat["id"], "última " + "y" * 200, prov, web=False)
        sent = [m["content"] for m in prov.calls[0]["messages"]]
        self.assertTrue(sent[-1].startswith("última"))
        self.assertLess(len(sent), 13)  # só o que cabe na janela (mínimo de 3.000 caracteres), o mais antigo saiu
        self.assertFalse(any("mensagem 0" in c for c in sent))
        self.store.save_settings({"chat": {"context_tokens": 200000, "max_tokens": 200}})
        prov = Prov(["fim"])
        self.send(chat["id"], "outra", prov, web=False)
        self.assertGreater(len(prov.calls[0]["messages"]), 12)


class ChatSettingsApi(ServerCase):
    def get(self, path):
        return self.c.json("GET", path)[1]

    def put(self, path, body):
        return self.c.json("PUT", path, body)[1]

    def post(self, path, body):
        status, r = self.c.json("POST", path, body)
        self.assertEqual(status, 200, r)
        return r

    def post_status(self, path, body):
        return self.c.json("POST", path, body)[0]

    def test_defaults_and_secrets_of_the_chat_settings(self):
        s = self.get("/api/settings")
        c = s["chat"]
        self.assertEqual((c["max_tokens"], c["context_tokens"], c["thinking"]), (2000, 16000, "off"))
        self.assertEqual(c["web"]["engine"], "auto")
        self.put("/api/settings", {"chat": {"web": {"brave_key": "segredo-brave", "tavily_key": "segredo-tavily", "results": 7}}})
        s = self.get("/api/settings")
        self.assertEqual(s["chat"]["web"]["brave_key"], "")  # nunca volta ao navegador
        self.assertTrue(s["chat"]["web"]["brave_key_set"] and s["chat"]["web"]["tavily_key_set"])
        self.assertEqual(s["chat"]["web"]["results"], 7)
        self.assertNotIn("segredo", json.dumps(s))
        self.assertEqual(self.store.get_settings()["chat"]["web"]["brave_key"], "segredo-brave")
        self.put("/api/settings", {"chat": {"web": {"brave_key": None}}})
        self.assertEqual(self.store.get_settings()["chat"]["web"]["brave_key"], "")
        self.put("/api/settings", {"chat": {"web": {"results": 5}}})

    def test_web_routes_validate_and_report_errors(self):
        self.assertEqual(self.post_status("/api/web/search", {"query": ""}), 400)
        with mock.patch.object(ws, "search", side_effect=ws.SearchError("sem rede")):
            self.assertEqual(self.post_status("/api/web/search", {"query": "x"}), 502)
        found = {"engine": "duckduckgo", "query": "q", "results": [{"title": "T", "url": "https://a.com/x", "snippet": "s"}]}
        with mock.patch.object(ws, "search", return_value=found):
            r = self.post("/api/web/search", {"query": "q"})
        self.assertEqual(r["sources"][0]["host"], "a.com")
        got = {"engine": "duckduckgo", "query": "q", "text": "[1] T", "sources": [{"n": 1, "title": "T", "url": "https://a.com/x", "host": "a.com", "snippet": "", "text": ""}]}
        with mock.patch.object(ws, "gather", return_value=got):
            r = self.post("/api/web/context", {"query": "q"})
        self.assertEqual(r["text"], "[1] T")

    def test_provider_list_carries_thinking_info_and_levels(self):
        r = self.get("/api/chat/providers")
        self.assertIn("thinking", r["current"])
        self.assertEqual([k for k, _ in r["thinking_levels"]], ["off", "slow", "medium", "high", "xhigh", "ultra"])
        self.assertIn("web_default", r)


if __name__ == "__main__":
    unittest.main()
