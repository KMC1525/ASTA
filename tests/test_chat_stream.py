"""Chat: texto visível durante o streaming (tags <think> chegando aos poucos), respostas longas, textos colados grandes e falhas no meio da resposta (v0.4.2)."""
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import assistant_chat as ac  # noqa: E402
from asta.providers import ProviderError  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.test_chat import INFO, Prov  # noqa: E402
from tests.test_core import TmpCase  # noqa: E402


def play(chunks):
    """Passa os pedaços por Visible e devolve (texto montado como a tela monta, eventos)."""
    v, shown, events = ac.Visible(), "", []
    for c in chunks:
        ev = v.feed(c)
        if ev:
            events.append(ev)
            shown = shown + ev[1] if ev[0] == "delta" else ev[1]
    return shown, events


class VisibleTests(unittest.TestCase):
    def test_plain_text_streams_as_is(self):
        shown, ev = play(["  Olá", ", ", "mundo", "!"])
        self.assertEqual(shown, "Olá, mundo!")
        self.assertTrue(all(k == "delta" for k, _ in ev))

    def test_think_tag_arriving_in_pieces_never_shows_up_on_screen(self):
        chunks = ["<", "thi", "nk>", "pensando", " muito", "</", "think", ">", "\n\nA resposta ", "é 42."]
        v, seen = ac.Visible(), []
        for c in chunks:
            ev = v.feed(c)
            if ev:
                seen.append(ev)
            self.assertNotIn("<", v.sent, c)       # nem o começo da tag aparece
            self.assertNotIn("pensando", v.sent)
        shown, _ = play(chunks)
        self.assertEqual(shown, "A resposta é 42.")

    def test_a_closing_tag_without_opening_resets_the_screen_instead_of_corrupting_it(self):
        """Qwen3 e cia. começam já «pensando» e só emitem o </think>: o que veio antes não é resposta."""
        shown, ev = play(["Vou pensar ", "no problema ", "com calma.", "</think>", "Resposta: ", "sim."])
        self.assertEqual(shown, "Resposta: sim.")
        self.assertIn("reset", [k for k, _ in ev])

    def test_angle_brackets_that_are_not_reasoning_tags_still_show(self):
        shown, _ = play(["Use a tag <", "div> para blocos e a < b quando ", "2 <", "3. Fim <th", "ead>"])
        self.assertEqual(shown, "Use a tag <div> para blocos e a < b quando 2 <3. Fim <thead>")
        self.assertEqual(play(["x <think", "ing>segredo</thinking> y"])[0], "x  y")

    def test_equivalent_to_cleaning_the_whole_text_for_any_way_of_cutting_it(self):
        from asta import avatars as av

        full = "<think>Primeiro, vejo que 2 < 3.</think>\n\nOlá! Aqui vai `<div>` e a<b.\n\n<thinking>outro</thinking>Fim."
        want = av.strip_reasoning(full).lstrip()
        for size in (1, 2, 3, 5, 8, 13, len(full)):
            shown, _ = play([full[i:i + size] for i in range(0, len(full), size)])
            self.assertEqual(shown.strip(), want.strip(), size)

    def test_long_answers_stay_linear(self):
        t0 = time.time()
        shown, _ = play(["palavra "] * 40000)
        self.assertEqual(len(shown), 40000 * 8 - 0 if shown.endswith(" ") else len(shown))
        self.assertLess(time.time() - t0, 2.0)
        t0 = time.time()
        play(["código <b>x</b> "] * 3000)   # com "<" em todo pedaço o caminho é o lento: ainda razoável
        self.assertLess(time.time() - t0, 5.0)


class EngineStreamTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "home")
        self.engine = ac.AssistantChat(self.store)
        self.events = []

    def send(self, chat_id, text, prov, info=INFO):
        with mock.patch.object(ac, "resolve_provider", return_value=(prov, info)):
            self.engine.send(chat_id, text, [], self.events.append)

    def test_deltas_rebuild_the_exact_final_message_even_with_think_tags_in_pieces(self):
        chat = self.engine.create()
        self.send(chat["id"], "quanto é 6x7?", Prov(["<th", "ink>", "6*7", "</think>", "É ", "**42**."]))
        shown = ""
        for e in self.events:
            if e["type"] == "delta":
                shown += e["text"]
            elif e["type"] == "reset":
                shown = e["text"]
        final = [e for e in self.events if e["type"] == "message"][0]["message"]["text"]
        self.assertEqual((shown, final), ("É **42**.", "É **42**."))

    def test_a_pasted_text_larger_than_12k_is_kept_whole(self):
        chat = self.engine.create()
        big = "linha de texto colado. " * 2000  # ~46 mil caracteres
        self.send(chat["id"], big, Prov(["ok"]))
        saved = self.store.chats.get(chat["id"])["messages"][0]["text"]
        self.assertEqual(len(saved), len(big.strip()))

    def test_a_failure_in_the_middle_keeps_the_question_drops_the_half_answer_and_retry_works(self):
        chat = self.engine.create()

        class Broken(Prov):
            def chat(self, *a, **k):
                def gen():
                    yield "Metade da "
                    raise ProviderError("conexão caiu")
                return gen()
        with self.assertRaises(ProviderError):
            self.send(chat["id"], "me conte algo", Broken([]))
        msgs = self.store.chats.get(chat["id"])["messages"]
        self.assertEqual([m["role"] for m in msgs], ["user"])  # a pergunta fica; nada pela metade
        self.events.clear()
        with mock.patch.object(ac, "resolve_provider", return_value=(Prov(["Agora foi."]), INFO)):
            self.engine.regenerate(chat["id"], self.events.append)
        self.assertEqual([m["text"] for m in self.store.chats.get(chat["id"])["messages"]], ["me conte algo", "Agora foi."])
        self.assertEqual([e for e in self.events if e["type"] == "removed"][0]["ids"], [])


if __name__ == "__main__":
    unittest.main()
