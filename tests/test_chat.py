"""Chat geral (tela «Chat»): conversa de uso geral com o modelo escolhido; criação (mundo/avatar/jogo/canvas) só com o ativador."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import assistant_chat as ac  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.test_avatars import tiny_png  # noqa: E402
from tests.test_core import TmpCase  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402

INFO = {"id": "x", "label": "Modelo X", "model": "m1", "demo": False, "auto": False, "reason": ""}


class Prov:
    def __init__(self, reply, vision=False):
        self.reply, self.vision, self.calls = reply, vision, []

    def chat(self, messages, system="", temperature=0.8, max_tokens=100, json_mode=False, stream=False):
        self.calls.append({"messages": messages, "system": system, "max_tokens": max_tokens})
        return iter(self.reply if isinstance(self.reply, list) else [self.reply])


class PureTests(unittest.TestCase):
    def test_title_and_normalization(self):
        self.assertEqual(ac.title_from("\n\n  Como faço um bolo de cenoura?\nOutra linha"), "Como faço um bolo de cenoura?")
        self.assertEqual(len(ac.title_from("x" * 200)), 58)
        self.assertTrue(ac.title_from("x" * 200).endswith("…"))
        c = ac.normalize_chat({"messages": [{"role": "user", "text": "oi"}, {"role": "robot", "text": "x"}, {"role": "assistant", "text": "  "}, "lixo", {"role": "assistant", "text": "olá"}], "title": "t" * 200})
        self.assertEqual([m["role"] for m in c["messages"]], ["user", "assistant"])
        self.assertEqual(len(c["title"]), 80)

    def test_the_activator_only_suggests_creation_for_creation_requests(self):
        yes = {"Crie um jogo de plataforma numa floresta": "game", "faça um avatar de uma amiga divertida": "avatar", "Quero criar um mundo 3D medieval": "world",
               "gere uma imagem de um farol ao entardecer": "canvas", "Create a visual novel about a café": "game", "make me a girlfriend avatar named Luna": "avatar",
               "monte um canvas com vídeo e narração": "canvas", "build a 3D world with a dragon": "world"}
        for text, tool in yes.items():
            self.assertEqual(ac.detect_tool(text), tool, text)
        for text in ("Como faço um bolo de cenoura?", "Me explique a fotossíntese", "Como criar um jogo em Python?", "What is a world map?", "Qual a capital da França?",
                     "Me ajude a estudar para a prova de história", "obrigado!", "", "o jogo de ontem foi ótimo", "How do I make a game?", "traduza 'good morning' para o português"):
            self.assertIsNone(ac.detect_tool(text), text)


class EngineTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "home")
        self.engine = ac.AssistantChat(self.store)
        self.events = []

    def run_send(self, chat_id, text, prov, ids=(), cancelled=lambda: False, info=INFO):
        with mock.patch.object(ac, "resolve_provider", return_value=(prov, info)):
            self.engine.send(chat_id, text, list(ids), self.events.append, cancelled)

    def types(self):
        return [e["type"] for e in self.events]

    def test_a_normal_question_is_answered_streamed_and_saved(self):
        chat = self.engine.create()
        prov = Prov(["A receita ", "de bolo de cenoura ", "leva 3 cenouras."])
        self.run_send(chat["id"], "Qual a receita de bolo de cenoura?", prov)
        self.assertEqual(self.types(), ["user", "title", "provider", "typing", "delta", "delta", "delta", "message", "end"])
        saved = self.store.chats.get(chat["id"])
        self.assertEqual(saved["title"], "Qual a receita de bolo de cenoura?")
        self.assertEqual([(m["role"], m["text"]) for m in saved["messages"]], [("user", "Qual a receita de bolo de cenoura?"), ("assistant", "A receita de bolo de cenoura leva 3 cenouras.")])
        self.assertEqual(saved["messages"][1]["model"], "Modelo X · m1")
        call = prov.calls[0]
        self.assertIn("general-purpose", call["system"])
        self.assertIn("ONLY when the user turns on a creation tool", call["system"])  # o assistente sabe que criar exige o ativador
        self.assertEqual(call["messages"], [{"role": "user", "content": "Qual a receita de bolo de cenoura?"}])

    def test_every_reply_gets_at_least_2k_tokens_of_room(self):
        for configured in (100, 0, 500, 1999, 2000, 4000):
            self.store.save_settings({"chat": {"max_tokens": configured}})
            chat = self.engine.create()
            prov = Prov(["ok"])
            self.run_send(chat["id"], "oi", prov)
            self.assertEqual(prov.calls[0]["max_tokens"], max(2000, configured), configured)   # valores menores (antigos ou digitados) sobem para 2.000; maiores valem

    def test_history_is_sent_and_always_starts_with_the_user(self):
        chat = self.engine.create()
        self.run_send(chat["id"], "primeira", Prov("resposta 1"))
        self.events.clear()
        prov = Prov("resposta 2")
        self.run_send(chat["id"], "segunda", prov)
        self.assertEqual([(m["role"], m["content"]) for m in prov.calls[0]["messages"]], [("user", "primeira"), ("assistant", "resposta 1"), ("user", "segunda")])
        self.assertNotIn("title", self.types())  # o título vem só da primeira mensagem

    def test_reasoning_blocks_are_hidden_and_an_empty_answer_is_an_error(self):
        chat = self.engine.create()
        self.run_send(chat["id"], "oi", Prov(["<think>vou pensar", " bastante</think>", "Olá!"]))
        self.assertEqual(self.store.chats.get(chat["id"])["messages"][-1]["text"], "Olá!")
        self.assertEqual("".join(e["text"] for e in self.events if e["type"] == "delta"), "Olá!")
        self.events.clear()
        self.run_send(chat["id"], "de novo", Prov(["<think>só pensando</think>"]))
        err = next(e for e in self.events if e["type"] == "error")
        self.assertIn("pensando", err["message"])
        self.assertEqual([m["role"] for m in self.store.chats.get(chat["id"])["messages"]], ["user", "assistant", "user"])  # nada vazio no histórico
        self.events.clear()
        self.run_send(chat["id"], "mais uma", Prov(""))
        self.assertIn("nenhum texto", next(e for e in self.events if e["type"] == "error")["message"])

    def test_stopping_does_not_save_a_half_answer(self):
        chat = self.engine.create()
        flag = {"n": 0}

        def stream():
            for c in ("um ", "dois ", "três "):
                flag["n"] += 1
                yield c

        prov = Prov([])
        prov.chat = lambda *a, **k: stream()
        self.run_send(chat["id"], "conta até três", prov, cancelled=lambda: flag["n"] >= 2)
        self.assertEqual([m["role"] for m in self.store.chats.get(chat["id"])["messages"]], ["user"])
        self.assertEqual(self.events[-1], {"type": "end", "reason": "cancelled"})

    def test_regenerate_replaces_the_last_answer(self):
        chat = self.engine.create()
        self.run_send(chat["id"], "me conte uma piada", Prov("piada antiga"))
        self.events.clear()
        prov = Prov("piada nova")
        with mock.patch.object(ac, "resolve_provider", return_value=(prov, INFO)):
            self.engine.regenerate(chat["id"], self.events.append)
        self.assertEqual([(m["role"], m["text"]) for m in self.store.chats.get(chat["id"])["messages"]], [("user", "me conte uma piada"), ("assistant", "piada nova")])
        self.assertEqual(len(next(e for e in self.events if e["type"] == "removed")["ids"]), 1)
        self.assertEqual(prov.calls[0]["messages"], [{"role": "user", "content": "me conte uma piada"}])
        with self.assertRaises(ValueError):
            self.engine.regenerate(self.engine.create()["id"], self.events.append)

    def test_creation_requests_are_only_suggested_never_run(self):
        chat = self.engine.create()
        self.run_send(chat["id"], "Crie um jogo de plataforma numa floresta encantada", Prov("Para isso, ative a ferramenta Jogo 2D (✦) e aperte Run."))
        sug = next(e for e in self.events if e["type"] == "suggest")
        self.assertEqual((sug["tool"], sug["prompt"]), ("game", "Crie um jogo de plataforma numa floresta encantada"))
        self.assertEqual(self.store.list_projects(), [])  # nenhum pipeline rodou
        self.events.clear()
        self.run_send(chat["id"], "Como faço um bolo?", Prov("Misture os ingredientes."))
        self.assertNotIn("suggest", self.types())

    def test_validation_and_unknown_chat(self):
        chat = self.engine.create()
        with self.assertRaises(ValueError):
            self.engine.send(chat["id"], "   ", [], self.events.append)
        with self.assertRaises(ValueError):
            self.engine.send("nao-existe", "oi", [], self.events.append)

    def test_link_read_failure_is_reported_and_answer_still_sent(self):
        chat = self.engine.create()
        prov = Prov("respondi mesmo assim")
        with mock.patch.object(ac.websearch, "extract_urls", return_value=["https://example.com/a"]), \
             mock.patch.object(ac.websearch, "links_context", side_effect=RuntimeError("falha de rede")):
            self.run_send(chat["id"], "veja https://example.com/a", prov)
        kinds = self.types()
        self.assertIn("notice", kinds)
        self.assertIn("message", kinds)
        self.assertFalse(any(e["type"] == "links" for e in self.events))
        self.assertTrue(any("Não consegui ler os links" in str(e.get("message", "")) for e in self.events if e["type"] == "notice"))
        self.assertEqual(self.store.chats.get(chat["id"])["messages"][-1]["text"], "respondi mesmo assim")


class ApiTests(ServerCase):
    def sse_send(self, cid, text, ids=None):
        return self.c.sse(f"/api/chats/{cid}/send", {"text": text, "attachment_ids": ids or []}, method="POST")

    def test_crud_and_titles(self):
        st, chat = self.c.json("POST", "/api/chats", {})
        self.assertEqual(st, 200)
        self.assertEqual(self.c.json("GET", f"/api/chats/{chat['id']}")[1]["messages"], [])
        self.sse_send(chat["id"], "Explique a fotossíntese")
        lst = self.c.json("GET", "/api/chats")[1]
        mine = next(c for c in lst if c["id"] == chat["id"])
        self.assertEqual((mine["title"], mine["count"]), ("Explique a fotossíntese", 2))
        self.assertEqual(self.c.json("PUT", f"/api/chats/{chat['id']}", {"title": "Biologia"})[1]["title"], "Biologia")
        self.assertEqual(self.c.json("DELETE", f"/api/chats/{chat['id']}")[0], 200)
        for method, path in (("GET", "/api/chats/nao-existe"), ("DELETE", "/api/chats/nao-existe"), ("PUT", "/api/chats/nao-existe"), ("POST", "/api/chats/nao-existe/send")):
            self.assertEqual(self.c.json(method, path, {"text": "x"})[0], 404, path)

    def test_demo_mode_is_honest_about_not_being_an_ai(self):
        chat = self.c.json("POST", "/api/chats", {})[1]
        with mock.patch("asta.assistant_chat.resolve_provider") as rp:
            from asta.providers import build_provider
            from asta.storage import DEFAULT_SETTINGS

            rp.return_value = (build_provider(DEFAULT_SETTINGS, "demo"), {"id": "demo", "label": "Demo", "model": "demo", "demo": True, "auto": True, "reason": "x"})
            ev = self.sse_send(chat["id"], "Qual a capital da França?")
        reply = next(e for e in ev if e["type"] == "message")["message"]["text"]
        self.assertIn("modo Demo", reply)
        self.assertIn("Run", reply)
        self.assertTrue(next(e for e in ev if e["type"] == "provider")["demo"])
        ev = None
        with mock.patch("asta.assistant_chat.resolve_provider") as rp:
            rp.return_value = (build_provider(DEFAULT_SETTINGS, "demo"), {"id": "demo", "label": "Demo", "model": "demo", "demo": True, "auto": True, "reason": "x"})
            ev = self.sse_send(chat["id"], "What is the capital of France?")
        self.assertIn("Demo mode", next(e for e in ev if e["type"] == "message")["message"]["text"])

    def test_validation_and_creation_requests_start_nothing(self):
        chat = self.c.json("POST", "/api/chats", {})[1]
        self.assertEqual(self.c.json("POST", f"/api/chats/{chat['id']}/send", {"text": ""})[0], 400)
        self.assertEqual(self.c.json("POST", f"/api/chats/{chat['id']}/send", ["x"])[0], 400)
        before = len(self.c.json("GET", "/api/projects")[1])
        ev = self.sse_send(chat["id"], "Crie um mundo 3D medieval com um dragão")
        self.assertEqual(next(e for e in ev if e["type"] == "suggest")["tool"], "world")
        self.assertEqual(len(self.c.json("GET", "/api/projects")[1]), before)
        for kind in ("generate", "avatar_generate", "game_generate"):
            self.assertIsNone(self.app.jobs.running(kind))

    def test_attachments_feed_the_answer_and_stay_in_the_context(self):
        chat = self.c.json("POST", "/api/chats", {})[1]
        st, up = self.c.json("POST", "/api/uploads", raw="Receita secreta da vovó: 3 ovos, 2 xícaras de farinha.".encode(), headers={"X-Filename": "receita.txt", "Content-Type": "text/plain"})
        prov = Prov("Você precisa de 3 ovos.")
        with mock.patch("asta.assistant_chat.resolve_provider", return_value=(prov, INFO)):
            ev = self.sse_send(chat["id"], "Quantos ovos tem na receita anexada?", [up["id"]])
            sent = prov.calls[0]["messages"][-1]["content"]
            self.assertIn("Quantos ovos", sent)
            self.assertIn("3 ovos, 2 xícaras de farinha", sent)
            user = next(e for e in ev if e["type"] == "user")["message"]
            self.assertEqual(user["attachments"], [{"name": "receita.txt", "kind": "text"}])
            self.assertEqual(self.c.json("GET", f"/api/uploads/{up['id']}")[0], 404)  # anexo consumido
            # a próxima pergunta ainda enxerga o documento
            prov2 = Prov("ok")
            with mock.patch("asta.assistant_chat.resolve_provider", return_value=(prov2, INFO)):
                self.sse_send(chat["id"], "E quanta farinha?")
            self.assertIn("2 xícaras de farinha", prov2.calls[0]["messages"][0]["content"])

    def test_images_go_to_vision_models_and_others_get_a_notice(self):
        chat = self.c.json("POST", "/api/chats", {})[1]
        up = self.c.json("POST", "/api/uploads", raw=tiny_png(), headers={"X-Filename": "foto.png", "Content-Type": "image/png"})[1]
        seeing = Prov("É um pixel.", vision=True)
        with mock.patch("asta.assistant_chat.resolve_provider", return_value=(seeing, INFO)):
            ev = self.sse_send(chat["id"], "O que tem na imagem?", [up["id"]])
        content = seeing.calls[0]["messages"][-1]["content"]
        self.assertEqual([p["type"] for p in content], ["text", "image"])
        self.assertFalse([e for e in ev if e["type"] == "notice"])
        up = self.c.json("POST", "/api/uploads", raw=tiny_png(), headers={"X-Filename": "foto2.png", "Content-Type": "image/png"})[1]
        blind = Prov("Não enxergo.", vision=False)
        with mock.patch("asta.assistant_chat.resolve_provider", return_value=(blind, INFO)):
            ev = self.sse_send(chat["id"], "E nesta?", [up["id"]])
        self.assertTrue(any(e["type"] == "notice" and "visão" in e["message"] for e in ev))
        self.assertIsInstance(blind.calls[0]["messages"][-1]["content"], str)

    def test_model_picker_lists_providers_and_marks_the_current_one(self):
        self.c.json("PUT", "/api/settings", {"providers": {"anthropic": {"api_key": "k", "model": "claude-x"}}, "active": {"generation": "anthropic"}})
        try:
            r = self.c.json("GET", "/api/chat/providers")[1]
        finally:
            self.c.json("PUT", "/api/settings", {"active": {"generation": "demo"}, "providers": {"anthropic": {"api_key": None, "model": ""}}})
        self.assertEqual((r["current"]["id"], r["current"]["model"]), ("anthropic", "claude-x"))
        ids = [p["id"] for p in r["providers"]]
        self.assertNotIn("demo", ids)
        self.assertEqual(ids[0], "anthropic")  # o atual vem primeiro
        a = r["providers"][0]
        self.assertEqual((a["selected"], a["usable"], a["has_key"], a["local"], a["model"]), (True, True, True, False, "claude-x"))
        other = next(p for p in r["providers"] if p["id"] == "openai")
        self.assertEqual((other["usable"], other["needs_key"]), (False, True))
        self.assertTrue(all(k in a for k in ("label", "kind", "needs_key")))
        self.assertNotIn("api_key", str(r))


if __name__ == "__main__":
    unittest.main()
