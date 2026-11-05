"""Relações dos avatars: namorada, namorado, esposa e marido (além das de antes) — todas podem ser SFW ou NSFW; menor de idade nunca tem uma delas."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import avatars as av  # noqa: E402
from asta.agents import rulebased_avatars as rb  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402

NEW = ("girlfriend", "boyfriend", "wife", "husband")


class CardTests(unittest.TestCase):
    def test_the_new_relationships_exist_and_old_ones_still_do(self):
        for r in NEW + ("friend", "partner", "companion", "mentor", "custom"):
            self.assertIn(r, av.RELATIONSHIPS)
            self.assertEqual(av.normalize_avatar({"name": "X", "age": 30, "relationship": r})["relationship"], r)
        self.assertEqual(av.normalize_avatar({"name": "X", "relationship": "amante"})["relationship"], "friend")  # inválida: amigo, como sempre
        for r in NEW:
            self.assertIn(r, av.ROMANTIC)

    def test_gender_is_suggested_by_the_relationship_only_when_the_card_does_not_say(self):
        g = lambda rel, gender="": av.normalize_avatar({"name": "X", "age": 30, "relationship": rel, "gender": gender})["gender"]  # noqa: E731
        self.assertEqual([g(r) for r in NEW], ["female", "male", "female", "male"])
        self.assertEqual(g("girlfriend", "não-binário"), "não-binário")  # o que o card diz vale
        self.assertEqual(g("husband", "female"), "female")
        self.assertEqual(g("friend"), "")

    def test_each_of_them_can_be_sfw_or_nsfw_for_adults(self):
        for r in NEW:
            for mode in ("sfw", "nsfw"):
                c = av.normalize_avatar({"name": "X", "age": 29, "relationship": r, "content": mode})
                self.assertEqual((c["relationship"], c["content"], c["flags"]), (r, mode, []), (r, mode))

    def test_minors_never_get_a_romantic_relationship_and_stay_sfw(self):
        for r in NEW + ("partner", "custom"):
            c = av.normalize_avatar({"name": "X", "age": 16, "relationship": r, "content": "nsfw"})
            self.assertEqual((c["relationship"], c["content"]), ("friend", "sfw"), r)
            c = av.normalize_avatar({"name": "X", "description": "uma garota de 15 anos", "relationship": r, "content": "nsfw"})
            self.assertEqual((c["relationship"], c["content"]), ("friend", "sfw"), r)

    def test_real_people_keep_the_relationship_but_are_always_sfw(self):
        for r in ("girlfriend", "wife"):
            c = av.normalize_avatar({"name": "X", "age": 40, "relationship": r, "content": "nsfw", "character_type": "real"})
            self.assertEqual((c["relationship"], c["content"]), (r, "sfw"))

    def test_chat_prompt_describes_the_relationship_in_sfw_and_nsfw(self):
        for r, label, hint in (("girlfriend", "the user's girlfriend", "loving girlfriend"), ("boyfriend", "the user's boyfriend", "loving boyfriend"),
                               ("wife", "the user's wife", "devoted wife"), ("husband", "the user's husband", "devoted husband")):
            c = av.normalize_avatar({"name": "Aya", "age": 30, "relationship": r, "content": "nsfw"})
            nsfw = av.build_system_prompt(c, [], [], "Kaua", "", "nsfw")
            sfw = av.build_system_prompt(c, [], [], "Kaua", "", "sfw")
            for p in (nsfw, sfw):
                self.assertIn(f"Relationship with the user: {label}", p)
                self.assertIn(hint, p)
            self.assertIn("ASTA adds no content filters", nsfw)
            self.assertNotIn("ASTA adds no content filters", sfw)
            self.assertIn("suitable for all audiences", sfw)
            self.assertIn("never write sexual content involving minors", nsfw)  # a regra fixa vale no NSFW de qualquer relação
        self.assertEqual(len({v for v in av.REL_LABEL.values()}), len(av.REL_LABEL))  # rótulos únicos (o Demo reconhece a relação pelo rótulo)


class DemoTests(unittest.TestCase):
    def analyst(self, prompt, rel="auto"):
        return rb.analyst({"prompt": prompt, "relationship": rel, "count_hint": 1})["avatars"][0]

    def test_the_demo_recognizes_each_relationship_in_the_request_and_infers_the_gender(self):
        cases = [("Uma namorada carinhosa chamada Aurora", "girlfriend", "female"), ("Meu namorado, o Caio, calmo e protetor", "boyfriend", "male"),
                 ("Uma esposa dedicada chamada Marta", "wife", "female"), ("Meu marido Theo, divertido", "husband", "male"),
                 ("A wife named Helena", "wife", "female"), ("My boyfriend Leo", "boyfriend", "male"), ("My girlfriend Nina", "girlfriend", "female"), ("A husband called Noah", "husband", "male"),
                 ("Uma amiga divertida", "friend", "female")]
        for prompt, rel, gender in cases:
            a = self.analyst(prompt)
            self.assertEqual((a["relationship"], a["gender"]), (rel, gender), prompt)

    def test_explicit_choice_wins_and_fills_the_gender(self):
        for rel, gender in (("girlfriend", "female"), ("boyfriend", "male"), ("wife", "female"), ("husband", "male")):
            a = self.analyst("Uma pessoa simpática chamada Alex", rel)
            self.assertEqual((a["relationship"], a["gender"]), (rel, gender))

    def test_cards_and_replies_exist_for_every_relationship(self):
        for rel in av.RELATIONSHIPS:
            card = rb.designer({"brief": {"language": "pt-BR", "avatars": [{"name": "Ana", "relationship": rel, "gender": "female", "age": 30, "traits": ["calma"]}]}, "content": "nsfw"})["avatars"][0]
            self.assertEqual(card["relationship"], rel)
            self.assertTrue(card["system_prompt"] and card["greeting"])
            p = av.build_system_prompt(av.normalize_avatar(card), [], [], "Kaua", "", "nsfw")
            self.assertTrue(rb.avatar_reply(p, "te amo muito"))
        wife = rb.designer({"brief": {"language": "pt-BR", "avatars": [{"name": "Ana", "relationship": "wife", "gender": "female", "age": 30}]}, "content": "sfw"})["avatars"][0]
        self.assertIn("esposa", wife["system_prompt"])
        husband = rb.designer({"brief": {"language": "en", "avatars": [{"name": "Leo", "relationship": "husband", "gender": "male", "age": 30}]}, "content": "sfw"})["avatars"][0]
        self.assertIn("husband", husband["system_prompt"])


class ApiTests(ServerCase):
    def test_creating_avatars_with_each_relationship_in_sfw_and_nsfw(self):
        for rel in NEW:
            for mode in ("sfw", "nsfw"):
                st, r = self.c.json("POST", "/api/avatars/generate", {"prompt": "Uma pessoa simpática chamada Alex", "relationship": rel, "content": mode, "count": 1})
                done = next(e for e in self.c.sse(f"/api/jobs/{r['job_id']}/events") if e["type"] == "done")
                card = self.c.json("GET", f"/api/avatars/{done['avatar_ids'][0]}")[1]
                self.assertEqual((card["relationship"], card["content"]), (rel, mode), (rel, mode))
                self.assertEqual(card["gender"], {"girlfriend": "female", "wife": "female", "boyfriend": "male", "husband": "male"}[rel])

    def test_a_minor_requested_as_wife_or_girlfriend_becomes_a_sfw_friend(self):
        for rel in ("wife", "girlfriend"):
            st, r = self.c.json("POST", "/api/avatars/generate", {"prompt": "Uma garota de 16 anos chamada Bia", "relationship": rel, "content": "nsfw"})
            done = next(e for e in self.c.sse(f"/api/jobs/{r['job_id']}/events") if e["type"] == "done")
            card = self.c.json("GET", f"/api/avatars/{done['avatar_ids'][0]}")[1]
            self.assertEqual((card["relationship"], card["content"]), ("friend", "sfw"))

    def test_editing_a_card_keeps_the_relationship(self):
        aid = self.c.json("POST", "/api/avatars", {"name": "Marta", "age": 34, "relationship": "wife", "content": "nsfw"})[1]["id"]
        card = self.c.json("GET", f"/api/avatars/{aid}")[1]
        self.assertEqual((card["relationship"], card["content"], card["gender"]), ("wife", "nsfw", "female"))
        self.assertEqual(self.c.json("PUT", f"/api/avatars/{aid}", {**card, "relationship": "husband"})[1]["relationship"], "husband")
        v2 = self.c.json("GET", f"/api/avatars/{aid}/export?format=card_v2")[1]
        self.assertEqual(v2["data"]["extensions"]["asta"]["relationship"], "husband")


if __name__ == "__main__":
    unittest.main()
