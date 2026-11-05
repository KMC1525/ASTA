"""Avatars: cards (adulto/menor), importação, diretor de turnos, geração por IA, conversas single/multi e voz."""
import base64
import json
import random
import shutil
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import avatars as av  # noqa: E402
from asta.avatar_chat import ChatEngine, autonomous_speaker, first_speaker, follow_up  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.helpers import MockProviderServer  # noqa: E402
from tests.test_core import TmpCase, make_docx  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402


def tiny_png(color=(200, 80, 80)) -> bytes:
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    raw = b"\x00" + bytes(color)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def png_with_card(card: dict) -> bytes:
    png = tiny_png()
    payload = base64.b64encode(json.dumps(card).encode())
    body = b"chara\x00" + payload
    text_chunk = struct.pack(">I", len(body)) + b"tEXt" + body + struct.pack(">I", zlib.crc32(b"tEXt" + body) & 0xFFFFFFFF)
    iend = png.rfind(b"\x00\x00\x00\x00IEND")
    return png[:iend] + text_chunk + png[iend:]


class DemoGroupLanguageTests(unittest.TestCase):
    def test_short_replies_in_a_group_keep_the_language_of_the_conversation(self):
        from asta.agents.rulebased_avatars import avatar_reply

        mia = av.normalize_avatar({"name": "Mia", "age": 24, "relationship": "friend"})
        others = [av.normalize_avatar({"name": n, "age": 24}) for n in ("Theo", "Caio")]
        system = av.build_system_prompt(mia, others, [], "Você", "", "sfw", group=True)
        transcript = "Você: Pessoal, o que vamos fazer no fim de semana?\nTheo: Haha, Mia, essa foi boa!"
        tail = "Nobody has written for a while: keep the conversation going naturally. Reply only as Mia."
        reply = avatar_reply(system, f"[Group chat so far]\n{transcript}\n\n{tail}")
        for english in ("that was", "good one", "What about you", "Pretty sure"):
            self.assertNotIn(english, reply)


class AvatarCardTests(TmpCase):
    def test_normalization_defaults_and_clamps(self):
        c = av.normalize_avatar({"name": "  Luna ", "age": 29, "relationship": "partner", "content": "nsfw", "tags": "Doce, divertida, doce",
                                 "talkativeness": 9, "voice": {"pitch": 10}, "portrait": "../../etc/passwd"})
        self.assertEqual((c["name"], c["age"], c["relationship"], c["content"]), ("Luna", 29, "partner", "nsfw"))
        self.assertEqual(c["tags"], ["doce", "divertida"])
        self.assertEqual(c["talkativeness"], 1.0)
        self.assertEqual(c["voice"]["pitch"], 2.0)
        self.assertEqual(c["portrait"], "")  # caminho malicioso descartado
        self.assertEqual(c["schema"], av.AVATAR_SCHEMA)
        self.assertEqual(av.normalize_avatar({"relationship": "xxx", "content": "yyy"})["relationship"], "friend")
        self.assertEqual(av.normalize_avatar({})["content"], "sfw")  # NSFW é sempre uma escolha explícita

    def test_minor_is_never_nsfw_or_partner_and_never_aged_up(self):
        for data in ({"name": "A", "age": 16, "content": "nsfw", "relationship": "partner"},
                     {"name": "B", "description": "She is 15 years old.", "content": "nsfw", "relationship": "partner"},
                     {"name": "C", "personality": "idade: 17", "content": "nsfw", "relationship": "custom"},
                     {"name": "D", "scenario": "uma menor de idade", "content": "nsfw", "relationship": "partner"}):
            c = av.normalize_avatar(data)
            self.assertEqual(c["content"], "sfw", data)
            self.assertEqual(c["relationship"], "friend", data)
            self.assertIn("minor_described", c["flags"], data)
        self.assertEqual(av.normalize_avatar({"name": "A", "age": 16})["age"], 16)  # não "envelhece" o personagem
        prompt = av.build_system_prompt(av.normalize_avatar({"name": "A", "age": 16}), [], [], "Você", "", "sfw")
        self.assertIn("minor", prompt)
        self.assertIn("no romance", prompt)
        # adultos e falsos positivos comuns não são afetados
        ok = av.normalize_avatar({"name": "E", "age": 30, "description": "tem 15 anos de experiência; ela tem 25 anos.", "content": "nsfw", "relationship": "partner"})
        self.assertEqual((ok["content"], ok["relationship"], ok["flags"]), ("nsfw", "partner", []))

    def test_import_sillytavern_card_png_and_export_roundtrip(self):
        v2 = {"spec": "chara_card_v2", "data": {"name": "Rin", "description": "Gamer.", "personality": "calma", "scenario": "No Discord.", "first_mes": "Oi!",
                                               "mes_example": "{{user}}: oi\n{{char}}: e aí", "tags": ["gamer"], "system_prompt": "Você é Rin."}}
        c = av.import_avatar(v2)
        self.assertEqual((c["name"], c["greeting"], c["personality"], c["source"]), ("Rin", "Oi!", "calma", "import"))
        self.assertEqual(c["content"], "sfw")
        c2 = av.avatar_from_png(png_with_card(v2["data"]))
        self.assertEqual(c2["name"], "Rin")
        out = av.export_card_v2(av.normalize_avatar(c))
        self.assertEqual(out["spec"], "chara_card_v2")
        self.assertEqual(out["data"]["first_mes"], "Oi!")
        self.assertEqual(av.import_avatar(out)["name"], "Rin")
        with self.assertRaises(ValueError):
            av.import_avatar([1, 2])

    def test_memory_and_portrait_storage(self):
        st = Store(self.tmp)
        card = st.avatars.save({"name": "Mia"})
        self.assertTrue(card["id"].startswith("a_"))
        st.add_memories(card["id"], ["gosta de café", "gosta de café", "tem um gato"], limit=40)
        self.assertEqual(st.get_memories(card["id"]), ["gosta de café", "tem um gato"])
        for i in range(60):
            st.add_memories(card["id"], [f"fato {i}"], limit=10)
        self.assertEqual(len(st.get_memories(card["id"])), 10)
        self.assertEqual(st.get_memories("../x"), [])
        name = st.save_portrait(card["id"], tiny_png(), "png")
        self.assertTrue(st.portrait_path(card["id"]).is_file())
        self.assertIsNone(st.save_portrait(card["id"], b"x", "exe"))
        self.assertTrue(st.delete_avatar(card["id"]))
        self.assertEqual(st.get_memories(card["id"]), [])
        self.assertFalse((st.avatar_portraits_dir / name).exists())


class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.avs = [{"id": "a1", "name": "Luna", "talkativeness": 0.9}, {"id": "a2", "name": "Mia Souza", "talkativeness": 0.5},
                    {"id": "a3", "name": "Theo", "talkativeness": 0.2}]
        self.chat = {"messages": []}

    def test_mentions_pick_who_answers_first(self):
        rng = random.Random(1)
        self.assertEqual(first_speaker(self.chat, self.avs, "Mia, você viu isso?", rng)["id"], "a2")
        self.assertEqual(first_speaker(self.chat, self.avs, "e aí Theo e Luna", rng)["id"], "a3")  # o primeiro citado
        self.assertEqual(first_speaker(self.chat, [self.avs[0]], "qualquer coisa", rng)["id"], "a1")
        self.assertEqual(av.find_mentions("oi MIA!!! tudo bem, luna?", self.avs), ["a2", "a1"])
        self.assertEqual(av.find_mentions("Souza também veio", self.avs), ["a2"])  # sobrenome
        self.assertEqual(av.find_mentions("ninguém aqui", self.avs), [])

    def test_follow_up_answers_mentions_and_respects_chain_limit(self):
        rng = random.Random(3)
        last = {"role": "avatar", "avatar_id": "a1", "text": "Theo, concorda comigo?"}
        self.assertEqual(follow_up(self.chat, self.avs, last, 1, 3, rng)["id"], "a3")  # citado responde sempre
        self.assertIsNone(follow_up(self.chat, self.avs, last, 3, 3, rng))  # limite da rodada
        self.assertIsNone(follow_up(self.chat, [self.avs[0]], last, 1, 3, rng))  # sozinho não há quem responda
        # sem menção: probabilístico, mas nunca o próprio autor da fala
        plain = {"role": "avatar", "avatar_id": "a1", "text": "Que dia bonito."}
        picks = [follow_up(self.chat, self.avs, plain, 1, 3, random.Random(i)) for i in range(60)]
        self.assertTrue(any(picks) and not all(picks))
        self.assertTrue(all(p["id"] != "a1" for p in picks if p))

    def test_autonomous_speaker_never_repeats_last_and_answers_mentions(self):
        chat = {"messages": [{"role": "avatar", "avatar_id": "a1", "name": "Luna", "text": "Mia, e você?"}]}
        self.assertEqual(autonomous_speaker(chat, self.avs, random.Random(5))["id"], "a2")
        chat = {"messages": [{"role": "avatar", "avatar_id": "a1", "name": "Luna", "text": "Que calor."}]}
        self.assertTrue(all(autonomous_speaker(chat, self.avs, random.Random(i))["id"] != "a1" for i in range(40)))

    def test_parse_reply_tags_prefix_and_other_speakers(self):
        p = av.parse_reply("Luna: Oi, *sorri* tudo bem? [[mood: happy]] [[remember: gosta de café]]", "Luna", ["Mia"])
        self.assertEqual((p["say"], p["mood"], p["remember"], p["silence"]), ("Oi, *sorri* tudo bem?", "happy", ["gosta de café"], False))
        self.assertTrue(av.parse_reply("[[silence]]", "Luna", [])["silence"])
        self.assertEqual(av.parse_reply("Verdade!\nMia: eu discordo\nLuna: ok", "Luna", ["Mia"])["say"], "Verdade!")
        self.assertEqual(av.parse_reply("[[mood: bravo]] oi", "Luna", [])["mood"], "")  # humor inválido ignorado


class EngineTests(TmpCase):
    def make(self, n=3, auto_max=10, **avatar_extra):
        st = Store(self.tmp)
        st.save_settings({"avatars": {"auto_talk_max": auto_max}})
        ids = [st.avatars.save({"name": name, "greeting": f"Oi, sou {name}!", "talkativeness": 0.9, **avatar_extra})["id"]
               for name in ("Luna", "Mia", "Theo")[:n]]
        engine = ChatEngine(st, random.Random(7))
        return st, engine, engine.create_chat(ids)

    def collect(self, fn, *args):
        events = []
        fn(*args, events.append)
        return events

    def test_single_chat_persists_history_memory_and_streams(self):
        st, engine, chat = self.make(1)
        self.assertEqual(chat["mode"], "single")
        self.assertEqual(chat["messages"][0]["text"], "Oi, sou Luna!")  # saudação do avatar
        ev = self.collect(engine.send, chat["id"], "Oi! Meu nome é Carlos e estou feliz")
        types = [e["type"] for e in ev]
        self.assertEqual(types[0], "user")
        self.assertIn("typing", types)
        self.assertIn("delta", types)
        self.assertEqual(types[-1], "end")
        msg = next(e for e in ev if e["type"] == "message")["message"]
        self.assertEqual(msg["role"], "avatar")
        self.assertEqual("".join(e["text"] for e in ev if e["type"] == "delta"), msg["text"])
        self.assertTrue(msg["text"] and "[[" not in msg["text"])
        saved = st.avatar_chats.get(chat["id"])
        self.assertEqual([m["role"] for m in saved["messages"]], ["avatar", "user", "avatar"])
        self.assertTrue(any("Carlos" in m for m in st.get_memories(saved["avatar_ids"][0])))  # [[remember: …]] gravado
        # single nunca tem conversa livre
        self.assertEqual(self.collect(engine.tick, chat["id"])[-1]["reason"], "disabled")
        with self.assertRaises(ValueError):
            engine.send(chat["id"], "   ", lambda e: None)

    def test_multi_chat_avatars_talk_to_each_other_without_user(self):
        st, engine, chat = self.make(3, auto_max=3)
        self.assertEqual(chat["mode"], "multi")
        self.assertEqual(len(chat["messages"]), 3)  # cada avatar se apresenta
        # o usuário cita a Mia: ela responde primeiro
        ev = self.collect(engine.send, chat["id"], "Mia, o que vocês vão fazer hoje?")
        speakers = [e["message"]["name"] for e in ev if e["type"] == "message"]
        self.assertEqual(speakers[0], "Mia")
        self.assertLessEqual(len(speakers), 3)
        # sem o usuário escrever nada: os avatars continuam conversando entre si
        before = len(st.avatar_chats.get(chat["id"])["messages"])
        talked = []
        for _ in range(3):
            ev = self.collect(engine.tick, chat["id"])
            talked += [e["message"] for e in ev if e["type"] == "message"]
        after = st.avatar_chats.get(chat["id"])["messages"]
        self.assertEqual(len(after) - before, len(talked))
        self.assertTrue(talked and all(m["role"] == "avatar" for m in talked))
        ids = [m["avatar_id"] for m in after[before:]]
        self.assertTrue(all(a != b for a, b in zip(ids, ids[1:])))  # ninguém fala duas vezes seguidas
        # limite de falas seguidas sem o usuário
        self.assertEqual(self.collect(engine.tick, chat["id"])[-1]["reason"], "limit")
        # uma mensagem do usuário zera o contador
        self.collect(engine.send, chat["id"], "voltei!")
        self.assertEqual(st.avatar_chats.get(chat["id"])["autonomous_turns"], 0)
        self.assertEqual(self.collect(engine.tick, chat["id"])[-1]["reason"], "done")

    def test_auto_talk_can_be_disabled_per_chat(self):
        st, engine, chat = self.make(2)
        chat["auto_talk"] = False
        st.avatar_chats.save(chat, chat["id"])
        self.assertEqual(self.collect(engine.tick, chat["id"])[-1]["reason"], "disabled")

    def test_group_prompt_uses_most_restrictive_content_and_participants(self):
        a = av.normalize_avatar({"name": "Luna", "content": "nsfw", "relationship": "partner", "age": 27})
        b = av.normalize_avatar({"name": "Mia", "content": "sfw"})
        self.assertEqual(av.effective_content({"content": "auto"}, [a, a]), "nsfw")
        self.assertEqual(av.effective_content({"content": "auto"}, [a, b]), "sfw")
        self.assertEqual(av.effective_content({"content": "sfw"}, [a]), "sfw")
        solo = av.build_system_prompt(a, [], [], "Carlos", "", "nsfw")
        self.assertIn("ASTA adds no content filters", solo)
        self.assertIn("adults (18+)", solo)
        self.assertIn("The user is called Carlos", solo)
        self.assertNotIn("## Group chat", solo)
        group = av.build_system_prompt(b, [a], ["gosta de café"], "Carlos", "", "sfw", group=True, silence_ok=True)
        self.assertIn("## Group chat", group)
        self.assertIn("- Luna", group)
        self.assertIn("[[silence]]", group)
        self.assertIn("gosta de café", group)
        self.assertIn("suitable for all audiences", group)

    def test_deleted_avatar_is_reported(self):
        st, engine, chat = self.make(1)
        st.delete_avatar(chat["avatar_ids"][0])
        with self.assertRaises(ValueError):
            engine.send(chat["id"], "oi", lambda e: None)


class AvatarApiTests(ServerCase):
    def wait_job(self, jid):
        return self.c.sse(f"/api/jobs/{jid}/events")

    def test_generate_one_avatar_from_text_image_and_document(self):
        img = tiny_png()
        status, up_img = self.c.json("POST", "/api/uploads", raw=img, headers={"X-Filename": "foto.png", "Content-Type": "image/png"})
        doc = self.tmp / "ficha.docx"
        make_docx(doc, "Luna gosta de astronomia e sempre carrega um caderno de estrelas.")
        status, up_doc = self.c.json("POST", "/api/uploads", raw=doc.read_bytes(), headers={"X-Filename": "ficha.docx"})
        status, r = self.c.json("POST", "/api/avatars/generate", {"prompt": "Uma amiga chamada Luna, divertida e carinhosa", "attachment_ids": [up_img["id"], up_doc["id"]],
                                                                    "content": "sfw", "count": 1})
        self.assertEqual(status, 200, r)
        ev = self.wait_job(r["job_id"])
        steps = [e["id"] for e in ev if e["type"] == "step" and e["status"] in ("done", "skipped", "warn")]
        for sid in ("attachments", "analyst", "designer", "reviewer", "save"):
            self.assertIn(sid, steps)
        done = next(e for e in ev if e["type"] == "done")
        self.assertEqual(len(done["avatar_ids"]), 1)
        status, card = self.c.json("GET", f"/api/avatars/{done['avatar_ids'][0]}")
        self.assertEqual((card["name"], card["relationship"], card["content"], card["source"]), ("Luna", "friend", "sfw", "ai"))
        self.assertGreaterEqual(card["age"], 18)
        self.assertIn("astronomia", card["system_prompt"])  # o documento anexado entrou no avatar
        self.assertTrue(card["system_prompt"] and card["greeting"] and card["examples"])
        status, headers, body = self.c.req("GET", f"/api/avatars/{card['id']}/portrait")  # a imagem anexada virou o retrato
        self.assertEqual((status, headers["Content-Type"], body[:4]), (200, "image/png", b"\x89PNG"))
        self.assertEqual(self.c.json("GET", f"/api/uploads/{up_img['id']}")[0], 404)  # anexos consumidos

    def test_generate_several_avatars_at_once_with_choices(self):
        status, r = self.c.json("POST", "/api/avatars/generate", {"prompt": "Três amigos de faculdade: Theo, Mia e Caio", "count": 3, "relationship": "friend", "content": "sfw"})
        done = next(e for e in self.wait_job(r["job_id"]) if e["type"] == "done")
        self.assertEqual([a["name"] for a in done["avatars"]], ["Theo", "Mia", "Caio"])
        self.assertTrue(done["group"])
        cards = [self.c.json("GET", f"/api/avatars/{i}")[1] for i in done["avatar_ids"]]
        self.assertTrue(all(c["relationship"] == "friend" and c["content"] == "sfw" for c in cards))
        self.assertIn("Mia", cards[0]["system_prompt"])  # sabem uns dos outros
        status, r = self.c.json("POST", "/api/avatars/generate", {"prompt": "Uma namorada carinhosa chamada Aurora", "relationship": "partner", "content": "nsfw"})
        done = next(e for e in self.wait_job(r["job_id"]) if e["type"] == "done")
        card = self.c.json("GET", f"/api/avatars/{done['avatar_ids'][0]}")[1]
        self.assertEqual((card["relationship"], card["content"]), ("partner", "nsfw"))

    def test_generate_minor_request_stays_platonic_and_sfw(self):
        status, r = self.c.json("POST", "/api/avatars/generate", {"prompt": "Uma namorada de 16 anos chamada Bia", "content": "nsfw", "relationship": "partner"})
        ev = self.wait_job(r["job_id"])
        done = next(e for e in ev if e["type"] == "done")
        card = self.c.json("GET", f"/api/avatars/{done['avatar_ids'][0]}")[1]
        self.assertEqual((card["age"], card["content"], card["relationship"]), (16, "sfw", "friend"))
        self.assertTrue(any("menor" in w for w in done["warnings"]))

    def test_generate_validation(self):
        self.assertEqual(self.c.json("POST", "/api/avatars/generate", {"prompt": "  "})[0], 400)

    def test_cards_crud_portrait_memory_export_import(self):
        status, card = self.c.json("POST", "/api/avatars", {"name": "Nina", "age": 30, "portrait": "../../hack", "relationship": "partner", "content": "nsfw"})
        self.assertEqual((status, card["portrait"], card["age"]), (200, "", 30))
        aid = card["id"]
        self.assertEqual(self.c.json("PUT", f"/api/avatars/{aid}", {"name": "Nina 2"})[1]["name"], "Nina 2")
        self.assertEqual(self.c.json("GET", f"/api/avatars/{aid}/portrait")[0], 404)
        self.assertEqual(self.c.req("PUT", f"/api/avatars/{aid}/portrait", raw=b"nao sou imagem")[0], 400)
        self.assertEqual(self.c.req("PUT", f"/api/avatars/{aid}/portrait", raw=tiny_png(), headers={"Content-Type": "image/png"})[0], 200)
        self.assertTrue(self.c.json("PUT", f"/api/avatars/{aid}", {"name": "Nina 3"})[1]["portrait"])  # editar não perde o retrato
        status, headers, body = self.c.req("GET", f"/api/avatars/{aid}/portrait")
        self.assertEqual(status, 200)
        # exportar como Character Card V2 e importar de volta (JSON e PNG)
        status, v2 = self.c.json("GET", f"/api/avatars/{aid}/export?format=card_v2")
        self.assertEqual(v2["spec"], "chara_card_v2")
        status, imp = self.c.json("POST", "/api/avatars/import", raw=json.dumps(v2).encode())
        self.assertEqual((status, imp["name"], imp["source"]), (200, "Nina 3", "import"))
        status, impng = self.c.json("POST", "/api/avatars/import", raw=png_with_card({"name": "Do PNG", "description": "d", "first_mes": "oi"}))
        self.assertEqual(impng["name"], "Do PNG")
        self.assertEqual(self.c.req("GET", f"/api/avatars/{impng['id']}/portrait")[0], 200)  # o PNG vira o retrato
        self.assertEqual(self.c.json("POST", "/api/avatars/import", raw=b"{{{")[0], 400)
        self.store.add_memories(aid, ["gosta de chuva"])
        self.assertEqual(self.c.json("GET", f"/api/avatars/{aid}/memory")[1]["memories"], ["gosta de chuva"])
        self.assertEqual(self.c.json("DELETE", f"/api/avatars/{aid}/memory")[0], 200)
        self.assertEqual(self.c.json("GET", f"/api/avatars/{aid}/memory")[1]["memories"], [])
        self.assertEqual(self.c.json("DELETE", f"/api/avatars/{aid}")[0], 200)
        self.assertEqual(self.c.json("GET", f"/api/avatars/{aid}")[0], 404)
        self.assertEqual(self.c.json("GET", "/api/avatars/..%2f..")[0], 404)

    def test_chat_over_sse_single_and_multi(self):
        ids = [self.c.json("POST", "/api/avatars", {"name": n, "greeting": f"Oi, {n}"})[1]["id"] for n in ("Luna", "Mia")]
        status, chat = self.c.json("POST", "/api/avatar-chats", {"avatar_ids": ids[:1], "reuse": True})
        self.assertEqual((status, chat["mode"]), (200, "single"))
        self.assertEqual(self.c.json("POST", "/api/avatar-chats", {"avatar_ids": ids[:1], "reuse": True})[1]["id"], chat["id"])  # reaproveita
        ev = self.c.sse(f"/api/avatar-chats/{chat['id']}/send", {"text": "Oi, tudo bem?"}, method="POST")
        self.assertEqual([e["type"] for e in ev if e["type"] in ("user", "message", "end")], ["user", "message", "end"])
        self.assertEqual(self.c.json("POST", f"/api/avatar-chats/{chat['id']}/send", {"text": ""})[0], 400)
        self.assertEqual(self.c.json("POST", "/api/avatar-chats/ch_nope/send", {"text": "x"})[0], 404)
        status, full = self.c.json("GET", f"/api/avatar-chats/{chat['id']}")
        self.assertEqual([m["role"] for m in full["messages"]], ["avatar", "user", "avatar"])
        self.assertEqual(full["avatars"][0]["name"], "Luna")
        # grupo
        status, group = self.c.json("POST", "/api/avatar-chats", {"avatar_ids": ids, "auto_talk": True, "user_name": "Carlos"})
        self.assertEqual(group["mode"], "multi")
        ev = self.c.sse(f"/api/avatar-chats/{group['id']}/tick", {}, method="POST")
        self.assertEqual(ev[-1]["type"], "end")
        self.assertTrue(any(e["type"] == "message" for e in ev))
        status, listing = self.c.json("GET", "/api/avatar-chats")
        self.assertIn(group["id"], [c["id"] for c in listing])
        self.assertEqual(self.c.json("PUT", f"/api/avatar-chats/{group['id']}", {"title": "Galera", "auto_talk": False})[1]["title"], "Galera")
        self.assertEqual(self.c.sse(f"/api/avatar-chats/{group['id']}/tick", {}, method="POST")[-1]["reason"], "disabled")
        self.assertEqual(self.c.json("POST", f"/api/avatar-chats/{group['id']}/reset")[1]["count"], 0)
        self.assertEqual(self.c.json("DELETE", f"/api/avatar-chats/{group['id']}")[0], 200)
        self.assertEqual(self.c.json("POST", "/api/avatar-chats", {"avatar_ids": []})[0], 400)
        self.assertEqual(self.c.json("POST", "/api/avatar-chats", {"avatar_ids": ["a_naoexiste"]})[0], 400)

    def test_chat_prompt_reaches_real_provider_with_mode_and_group(self):
        with MockProviderServer() as mock:
            self.c.json("PUT", "/api/settings", {"providers": {"custom": {"base_url": mock.url + "/v1", "model": "m", "api_key": "k"}}, "active": {"characters": "custom"}})
            try:
                ids = [self.c.json("POST", "/api/avatars", {"name": n, "age": 26, "content": "nsfw", "relationship": "partner", "greeting": ""})[1]["id"] for n in ("Aya", "Bea")]
                solo = self.c.json("POST", "/api/avatar-chats", {"avatar_ids": ids[:1]})[1]
                ev = self.c.sse(f"/api/avatar-chats/{solo['id']}/send", {"text": "oi"}, method="POST")
                self.assertEqual("".join(e.get("text", "") for e in ev if e["type"] == "delta"), "Olá, mundo")  # SSE do provedor → SSE do chat
                sys_msg = mock.requests[-1]["body"]["messages"][0]["content"]
                self.assertIn("# You are Aya.", sys_msg)
                self.assertIn("ASTA adds no content filters", sys_msg)  # NSFW (único avatar NSFW)
                self.assertTrue(mock.requests[-1]["body"]["stream"])
                grp = self.c.json("POST", "/api/avatar-chats", {"avatar_ids": ids, "content": "sfw"})[1]
                self.c.sse(f"/api/avatar-chats/{grp['id']}/send", {"text": "Aya, oi"}, method="POST")
                body = mock.requests[-1]["body"]["messages"]
                self.assertIn("## Group chat", body[0]["content"])
                self.assertIn("suitable for all audiences", body[0]["content"])  # o chat forçou SFW
                self.assertIn("[Group chat so far]", body[-1]["content"])
            finally:
                self.c.json("PUT", "/api/settings", {"active": {"characters": "demo"}, "providers": {"custom": {"api_key": None}}})

    def test_provider_error_is_reported_as_event(self):
        with MockProviderServer() as mock:
            self.c.json("PUT", "/api/settings", {"providers": {"custom": {"base_url": mock.url + "/v1", "model": "bad-key", "api_key": "k"}}, "active": {"characters": "custom"}})
            try:
                aid = self.c.json("POST", "/api/avatars", {"name": "Zed"})[1]["id"]
                cid = self.c.json("POST", "/api/avatar-chats", {"avatar_ids": [aid]})[1]["id"]
                ev = self.c.sse(f"/api/avatar-chats/{cid}/send", {"text": "oi"}, method="POST")
                err = [e for e in ev if e["type"] == "error"]
                self.assertTrue(err and err[0]["kind"] == "provider")
                self.assertNotIn("k\"", err[0]["message"])
            finally:
                self.c.json("PUT", "/api/settings", {"active": {"characters": "demo"}, "providers": {"custom": {"api_key": None}}})


class AvatarFromReferenceImageTests(ServerCase):
    """Avatars criados a partir de foto/arte: a imagem é a base (e o retrato); texto e anexos só complementam."""

    def upload(self, name, color=(180, 90, 60)):
        status, up = self.c.json("POST", "/api/uploads", raw=tiny_png(color), headers={"X-Filename": name, "Content-Type": "image/png"})
        self.assertEqual(status, 200)
        return up["id"]

    def generate(self, **body):
        status, r = self.c.json("POST", "/api/avatars/generate", body)
        self.assertEqual(status, 200, r)
        ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        done = [e for e in ev if e["type"] == "done"]
        self.assertTrue(done, [e for e in ev if e["type"] == "error"])
        return done[0], ev

    def test_only_the_image_is_enough_and_it_becomes_the_portrait(self):
        done, _ = self.generate(attachment_ids=[self.upload("luna_azul-01.png")], from_images=True)
        self.assertEqual(len(done["avatar_ids"]), 1)
        card = self.c.json("GET", f"/api/avatars/{done['avatar_ids'][0]}")[1]
        self.assertEqual(card["name"], "Luna Azul")  # nome sugerido pelo arquivo (a imagem não é usada para "reconhecer" ninguém)
        self.assertTrue(card["portrait"])
        self.assertTrue(card["looks"] or card["appearance"])
        status, headers, body = self.c.req("GET", f"/api/avatars/{card['id']}/portrait")
        self.assertEqual((status, body[:4]), (200, b"\x89PNG"))

    def test_one_avatar_per_image_or_a_single_person_from_all_images(self):
        ids = [self.upload("theo.png", (20, 40, 200)), self.upload("mia.png", (200, 40, 120)), self.upload("caio.png", (30, 160, 60))]
        done, _ = self.generate(attachment_ids=ids, from_images=True, images_mode="each")
        names = [self.c.json("GET", f"/api/avatars/{i}")[1] for i in done["avatar_ids"]]
        self.assertEqual([c["name"] for c in names], ["Theo", "Mia", "Caio"])
        self.assertTrue(all(c["portrait"] for c in names))
        self.assertEqual(len({c["portrait"] for c in names}), 3)  # cada um com a própria imagem
        ids = [self.upload("a.png"), self.upload("b.png", (1, 2, 3))]
        done, _ = self.generate(attachment_ids=ids, prompt="Uma amiga chamada Nina, tímida e curiosa", from_images=True, images_mode="one")
        self.assertEqual(len(done["avatar_ids"]), 1)
        self.assertEqual(self.c.json("GET", f"/api/avatars/{done['avatar_ids'][0]}")[1]["name"], "Nina")  # o texto complementa a imagem

    def test_extra_prompt_and_attachments_complement_the_image(self):
        status, doc = self.c.json("POST", "/api/uploads", raw="Ela adora astronomia e cresceu num farol.".encode(), headers={"X-Filename": "historia.txt", "Content-Type": "text/plain"})
        done, _ = self.generate(attachment_ids=[self.upload("ref.png"), doc["id"]], prompt="Uma amiga chamada Luna, divertida", from_images=True, relationship="friend")
        card = self.c.json("GET", f"/api/avatars/{done['avatar_ids'][0]}")[1]
        self.assertEqual((card["name"], card["relationship"]), ("Luna", "friend"))
        self.assertTrue(card["portrait"])

    def test_photos_and_unidentified_images_are_never_nsfw(self):
        done, _ = self.generate(attachment_ids=[self.upload("ela.png")], prompt="Uma namorada chamada Aurora", from_images=True, relationship="partner", content="nsfw")
        self.assertEqual(self.c.json("GET", f"/api/avatars/{done['avatar_ids'][0]}")[1]["content"], "sfw")
        self.assertTrue(any("apenas SFW" in w for w in done["warnings"]))
        # sem a opção "foto como base", o comportamento anterior continua: NSFW é escolha do usuário
        done, _ = self.generate(prompt="Uma namorada carinhosa chamada Aurora", relationship="partner", content="nsfw")
        self.assertEqual(self.c.json("GET", f"/api/avatars/{done['avatar_ids'][0]}")[1]["content"], "nsfw")

    def test_vision_model_can_mark_art_and_the_structure_is_enforced(self):
        from asta.agents import avatar_pipeline as ap

        fitted = ap._fit_to_images([{"name": "X", "source_kind": "art"}, {"name": "Y", "source_kind": "????"}], ["A", "B", "C"], "each", [])
        self.assertEqual([(a["name"], a["image_index"], a["source_kind"]) for a in fitted], [("X", 0, "art"), ("Y", 1, "unknown"), ("C", 2, "unknown")])
        self.assertEqual(len(ap._fit_to_images([{"name": "X"}, {"name": "Y"}], ["A", "B"], "one", [])), 1)
        self.assertEqual(ap._pretty_name("IMG_2031.JPG"), "")
        self.assertEqual(ap._pretty_name("maria-souza_foto.webp"), "Maria Souza")

    def test_validation(self):
        self.assertEqual(self.c.json("POST", "/api/avatars/generate", {"prompt": "Luna", "from_images": True})[0], 400)  # sem imagem
        status, r = self.c.json("POST", "/api/avatars/generate", {"from_images": True, "prompt": "Luna", "attachment_ids": [self.upload("x.png")][:0] or ["nao_existe"]})
        ev = self.c.sse(f"/api/jobs/{r['job_id']}/events") if status == 200 else []
        self.assertTrue(status == 400 or any(e["type"] == "error" for e in ev))


class RealOrFictionalCharacterTests(TmpCase):
    """Qualquer personagem, real ou fictício: fictício adulto pode ser SFW/NSFW; pessoa real é sempre SFW; menor é sempre SFW e platônico."""

    def test_real_person_is_always_sfw_even_when_imported_or_edited_by_hand(self):
        c = av.normalize_avatar({"name": "Pessoa Real", "character_type": "real", "content": "nsfw", "relationship": "partner"})
        self.assertEqual((c["character_type"], c["content"]), ("real", "sfw"))
        self.assertIn("real_person", c["flags"])
        f = av.normalize_avatar({"name": "Heroína de anime", "character_type": "fictional", "content": "nsfw", "age": 27})
        self.assertEqual((f["character_type"], f["content"], f["flags"]), ("fictional", "nsfw", []))
        self.assertEqual(av.normalize_avatar({"name": "X", "content": "nsfw"})["character_type"], "fictional")  # padrão
        self.assertEqual(av.normalize_avatar({"name": "X", "character_type": "alien"})["character_type"], "fictional")
        # cartão V2 exportado e importado mantém o tipo (e a regra continua valendo)
        card = av.export_card_v2(c)
        self.assertEqual(card["data"]["extensions"]["asta"]["character_type"], "real")
        again = av.import_avatar(card)
        self.assertEqual((again["character_type"], again["content"]), ("real", "sfw"))
        tampered = json.loads(json.dumps(card))
        tampered["data"]["extensions"]["asta"]["content"] = "nsfw"
        self.assertEqual(av.import_avatar(tampered)["content"], "sfw")

    def test_chat_prompt_of_a_real_person_portrays_a_fiction_and_forbids_sexual_content(self):
        c = av.normalize_avatar({"name": "Pessoa Real", "character_type": "real", "content": "nsfw"})
        prompt = av.build_system_prompt(c, [], [], "Ana", "", c["content"])
        self.assertIn("portrayal of a real person", prompt)
        self.assertIn("never write sexual content about them", prompt)
        self.assertNotIn("ASTA adds no content filters", prompt)  # o modo NSFW não vale para ela
        fic = av.normalize_avatar({"name": "Rainha Elfa", "content": "nsfw"})
        self.assertNotIn("portrayal of a real person", av.build_system_prompt(fic, [], [], "Ana", "", fic["content"]))
        self.assertIn("ASTA adds no content filters", av.build_system_prompt(fic, [], [], "Ana", "", fic["content"]))


class ScriptedProvider:
    """Provedor falso para os agentes: responde por papel ([[ASTA_AGENT:nome]]) com o que o teste mandar."""

    vision = False
    model = "scripted"

    def __init__(self, script):
        self.script, self.calls = script, []

    def chat(self, messages, system="", temperature=0.8, max_tokens=1000, json_mode=False):
        import re

        agent = re.search(r"\[\[ASTA_AGENT:(\w+)\]\]", system).group(1)
        self.calls.append((agent, messages[-1]["content"]))
        reply = self.script[agent]
        reply = reply.pop(0) if isinstance(reply, list) and len(reply) > 1 else (reply[0] if isinstance(reply, list) else reply)
        return json.dumps(reply) if not isinstance(reply, str) else reply


class SystemPromptPipelineTests(TmpCase):
    """Pipeline Analisa → Gera → Revisa → Entrega do system prompt."""

    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "home")
        self.events = []

    def run_pipeline(self, req, provider=None):
        from unittest import mock

        from asta.agents import avatar_prompt

        pipe = avatar_prompt.AvatarPromptPipeline(self.store, self.events.append)
        if provider is None:
            return pipe.run(req)
        with mock.patch.object(avatar_prompt, "resolve_provider", return_value=(provider, {"id": "scripted", "demo": False, "reason": ""})):
            return pipe.run(req)

    def steps(self):
        return [(e["id"], e["status"]) for e in self.events if e["type"] == "step" and e["status"] != "running"]

    def test_demo_runs_the_four_stages_in_order_and_delivers_a_prompt(self):
        r = self.run_pipeline({"draft": {"name": "Luna", "personality": "carinhosa, curiosa, divertida", "relationship": "friend", "age": 26}, "instructions": "Gosta de astronomia."})
        self.assertEqual([s[0] for s in self.steps() if s[1] in ("done", "warn")], ["analyze", "generate", "review", "deliver"])
        self.assertEqual(self.events[0]["steps"], ["analyze", "generate", "review", "deliver"])
        self.assertIn("Luna", r["system_prompt"])
        self.assertIn("astronomia", r["system_prompt"])
        self.assertEqual((r["character_type"], r["content"], r["applied"]), ("fictional", "sfw", False))
        self.assertTrue(r["approved"])
        self.assertEqual(self.events[-1]["type"], "done")

    def test_apply_saves_the_prompt_into_the_existing_avatar(self):
        saved = self.store.avatars.save(av.normalize_avatar({"name": "Theo", "personality": "calmo e sábio", "age": 30}))
        r = self.run_pipeline({"avatar_id": saved["id"], "apply": True, "content": "nsfw"})
        card = self.store.avatars.get(saved["id"])
        self.assertTrue(r["applied"])
        self.assertEqual(card["system_prompt"], r["system_prompt"])
        self.assertIn("Theo", card["system_prompt"])
        self.assertEqual(card["content"], "nsfw")  # personagem fictício adulto pode ser NSFW
        # sem apply, o avatar não muda
        before = card["system_prompt"]
        self.run_pipeline({"avatar_id": saved["id"], "instructions": "mais tímido"})
        self.assertEqual(self.store.avatars.get(saved["id"])["system_prompt"], before)

    def test_real_person_is_forced_to_sfw_with_a_warning_and_a_fictional_portrayal(self):
        r = self.run_pipeline({"draft": {"name": "Pessoa Famosa", "personality": "carismática"}, "character_type": "real", "content": "nsfw", "apply": False})
        self.assertEqual((r["character_type"], r["content"]), ("real", "sfw"))
        self.assertIn("real_person", r["flags"])
        self.assertTrue(any("pessoa real" in w for w in r["warnings"]))
        self.assertRegex(r["system_prompt"], r"interpretação ficcional|fictional, respectful interpretation")  # o prompt a apresenta como retrato ficcional, nunca como a pessoa

    def test_minor_is_forced_to_sfw_by_code_even_if_the_model_says_otherwise(self):
        script = {"avatar_prompt_analyst": {"character_type": "fictional", "is_minor": False, "age": 16, "traits": ["curiosa"], "language": "pt-BR"},
                  "avatar_prompt_writer": {"system_prompt": "Você é Bia, uma amiga curiosa de 16 anos."},
                  "avatar_prompt_reviewer": {"approved": True, "score": 9, "issues": []}}
        r = self.run_pipeline({"draft": {"name": "Bia", "age": 16}, "content": "nsfw"}, ScriptedProvider(script))
        self.assertTrue(r["is_minor"])
        self.assertEqual(r["content"], "sfw")
        self.assertTrue(any("menor" in w for w in r["warnings"]))

    def test_fictional_adult_keeps_nsfw_and_the_user_choice_beats_the_model_guess(self):
        script = {"avatar_prompt_analyst": {"character_type": "fictional", "is_minor": False, "age": 29, "traits": ["sedutora"], "language": "pt-BR"},
                  "avatar_prompt_writer": {"system_prompt": "Você é Morgana, uma feiticeira sedutora."},
                  "avatar_prompt_reviewer": {"approved": True, "score": 8, "issues": []}}
        r = self.run_pipeline({"draft": {"name": "Morgana", "age": 29}, "content": "nsfw"}, ScriptedProvider(script))
        self.assertEqual((r["character_type"], r["content"]), ("fictional", "nsfw"))
        # o modelo chuta "fictional", mas o usuário disse que é pessoa real: vale o usuário (e fica SFW)
        r2 = self.run_pipeline({"draft": {"name": "Alguém", "age": 40}, "content": "nsfw", "character_type": "real"}, ScriptedProvider(script))
        self.assertEqual((r2["character_type"], r2["content"]), ("real", "sfw"))
        # o modelo diz "real" sozinho: também vira SFW
        script["avatar_prompt_analyst"]["character_type"] = "real"
        r3 = self.run_pipeline({"draft": {"name": "Alguém", "age": 40}, "content": "nsfw"}, ScriptedProvider(script))
        self.assertEqual((r3["character_type"], r3["content"]), ("real", "sfw"))

    def test_the_reviewer_can_send_the_prompt_back_once_and_the_fix_is_delivered(self):
        script = {"avatar_prompt_analyst": {"character_type": "fictional", "age": 25, "traits": ["tímida"], "language": "pt-BR"},
                  "avatar_prompt_writer": [{"system_prompt": "Você é Lia."}, {"system_prompt": "```\nVocê é Lia, uma jovem tímida que fala baixinho e adora livros.\n```"}],
                  "avatar_prompt_reviewer": [{"approved": False, "score": 3, "issues": [{"problem": "genérico", "fix": "descreva a voz"}]}, {"approved": True, "score": 8, "issues": []}]}
        prov = ScriptedProvider(script)
        r = self.run_pipeline({"draft": {"name": "Lia", "age": 25}}, prov)
        self.assertTrue(r["revised"])
        self.assertEqual(r["system_prompt"], "Você é Lia, uma jovem tímida que fala baixinho e adora livros.")  # cercas de markdown removidas
        self.assertTrue(r["approved"])
        self.assertEqual([c[0] for c in prov.calls], ["avatar_prompt_analyst", "avatar_prompt_writer", "avatar_prompt_reviewer", "avatar_prompt_writer", "avatar_prompt_reviewer"])
        self.assertIn("FEEDBACK TO FIX", prov.calls[3][1])
        self.assertIn("descreva a voz", prov.calls[3][1])
        self.assertTrue(any(e["type"] == "revision" for e in self.events))

    def test_still_not_approved_after_the_fix_is_delivered_with_a_warning(self):
        script = {"avatar_prompt_analyst": {"character_type": "fictional", "age": 25}, "avatar_prompt_writer": {"system_prompt": "Você é Lia."},
                  "avatar_prompt_reviewer": {"approved": False, "score": 2, "issues": [{"problem": "curto", "fix": "alongue"}]}}
        r = self.run_pipeline({"draft": {"name": "Lia"}}, ScriptedProvider(script))
        self.assertFalse(r["approved"])
        self.assertTrue(any("não aprovado" in w for w in r["warnings"]))
        self.assertEqual(r["system_prompt"], "Você é Lia.")

    def test_garbage_or_empty_model_answers_fall_back_to_rules(self):
        script = {"avatar_prompt_analyst": "isto não é JSON", "avatar_prompt_writer": {"system_prompt": "   "}, "avatar_prompt_reviewer": "nope"}
        r = self.run_pipeline({"draft": {"name": "Nina", "personality": "animada"}}, ScriptedProvider(script))
        self.assertIn("Nina", r["system_prompt"])
        self.assertTrue(r["warnings"])
        self.assertTrue(r["approved"])

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.run_pipeline({})
        with self.assertRaises(ValueError):
            self.run_pipeline({"avatar_id": "nao-existe"})


class CreationUsesThePromptPipelineTests(TmpCase):
    """Ao criar avatars, cada um passa pelo pipeline de system prompt (analisa, gera, revisa, entrega)."""

    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "home")
        self.events = []

    def run_creation(self, req, script):
        from unittest import mock

        from asta.agents import avatar_pipeline

        prov = ScriptedProvider(script)
        with mock.patch.object(avatar_pipeline, "resolve_provider", return_value=(prov, {"id": "scripted", "demo": False, "reason": ""})):
            res = avatar_pipeline.AvatarPipeline(self.store, self.events.append).run(req)
        return res, prov

    @staticmethod
    def script(**over):
        brief = {"language": "pt-BR", "group": True, "tone": "amigos", "avatars": [
            {"name": "Ana", "relationship": "friend", "gender": "female", "age": 25, "traits": ["alegre"], "talkativeness": 0.7},
            {"name": "Beto", "relationship": "friend", "gender": "male", "age": 27, "traits": ["calmo"], "talkativeness": 0.5}]}
        cards = {"avatars": [{"name": n, "relationship": "friend", "age": a, "system_prompt": f"Você é {n} (rascunho do designer).", "greeting": "Oi!", "examples": "Usuário: oi", "personality": "x", "content": "nsfw"}
                             for n, a in (("Ana", 25), ("Beto", 27))]}
        base = {"avatar_analyst": brief, "avatar_designer": cards, "avatar_reviewer": {"approved": True, "score": 9, "issues": []},
                "avatar_prompt_analyst": {"character_type": "fictional", "age": 25, "is_minor": False, "traits": ["alegre"], "language": "pt-BR"},
                "avatar_prompt_writer": [{"system_prompt": "Você é Ana, alegre e falante; conhece o Beto."}, {"system_prompt": "Você é Beto, calmo; amigo da Ana."}],
                "avatar_prompt_reviewer": {"approved": True, "score": 8, "issues": []}}
        base.update(over)
        return base

    def test_every_avatar_gets_its_own_analysis_generation_and_review(self):
        res, prov = self.run_creation({"prompt": "Dois amigos: Ana e Beto", "content": "nsfw", "count": 2}, self.script())
        steps = [e["id"] for e in self.events if e["type"] == "step" and e["status"] in ("done", "warn", "skipped")]
        self.assertEqual([x for x in steps if x in ("analyst", "designer", "reviewer", "prompts", "save")], ["analyst", "designer", "reviewer", "prompts", "save"])
        self.assertEqual([c[0] for c in prov.calls].count("avatar_prompt_analyst"), 2)
        self.assertEqual([c[0] for c in prov.calls].count("avatar_prompt_writer"), 2)
        self.assertEqual([c[0] for c in prov.calls].count("avatar_prompt_reviewer"), 2)
        cards = [self.store.avatars.get(i) for i in res["avatar_ids"]]
        self.assertEqual(cards[0]["system_prompt"], "Você é Ana, alegre e falante; conhece o Beto.")  # o texto do pipeline substitui o rascunho do designer
        self.assertEqual(cards[1]["system_prompt"], "Você é Beto, calmo; amigo da Ana.")
        self.assertEqual([c["content"] for c in cards], ["nsfw", "nsfw"])  # fictícios adultos mantêm NSFW
        writer_calls = [c[1] for c in prov.calls if c[0] == "avatar_prompt_writer"]
        self.assertIn("Beto", writer_calls[0])  # em grupo, sabe com quem convive ("knows")
        self.assertIn("rascunho do designer", writer_calls[0])  # o rascunho entra como ponto de partida
        prompts_done = next(e for e in self.events if e["type"] == "step" and e["id"] == "prompts" and e["status"] in ("done", "warn"))
        self.assertEqual((prompts_done["detail"]["count"], prompts_done["detail"]["approved"]), (2, 2))
        progress = [e["detail"].get("current") for e in self.events if e["type"] == "step" and e["id"] == "prompts" and e["status"] == "running" and e["detail"].get("current")]
        self.assertEqual(progress, ["Ana", "Beto"])

    def test_the_reviewer_of_the_prompt_pipeline_can_send_one_avatar_back(self):
        script = self.script(avatar_prompt_reviewer=[{"approved": False, "score": 3, "issues": [{"problem": "genérico", "fix": "mais voz"}]}, {"approved": True, "score": 8, "issues": []}],
                             avatar_prompt_writer=[{"system_prompt": "Você é Ana."}, {"system_prompt": "Você é Ana, falante e cheia de gírias."}, {"system_prompt": "Você é Beto, calmo."}])
        res, prov = self.run_creation({"prompt": "Dois amigos: Ana e Beto", "count": 2}, script)
        self.assertEqual(self.store.avatars.get(res["avatar_ids"][0])["system_prompt"], "Você é Ana, falante e cheia de gírias.")
        done = next(e for e in self.events if e["type"] == "step" and e["id"] == "prompts" and e["status"] in ("done", "warn"))
        self.assertEqual(done["detail"]["revised"], 1)

    def test_it_can_be_turned_off(self):
        res, prov = self.run_creation({"prompt": "Dois amigos: Ana e Beto", "count": 2, "prompt_pipeline": False}, self.script())
        self.assertFalse(any(c[0].startswith("avatar_prompt_") for c in prov.calls))
        self.assertTrue(any(e["type"] == "step" and e["id"] == "prompts" and e["status"] == "skipped" for e in self.events))
        self.assertIn("rascunho do designer", self.store.avatars.get(res["avatar_ids"][0])["system_prompt"])

    def test_rules_still_hold_after_the_prompt_pipeline(self):
        # o analista do pipeline marca "pessoa real": o avatar vira SFW mesmo que o designer e o usuário tenham pedido NSFW
        script = self.script(avatar_prompt_analyst={"character_type": "real", "age": 40, "is_minor": False, "traits": ["x"], "language": "pt-BR"})
        res, prov = self.run_creation({"prompt": "Dois amigos: Ana e Beto", "content": "nsfw", "count": 2}, script)
        cards = [self.store.avatars.get(i) for i in res["avatar_ids"]]
        self.assertEqual([(c["character_type"], c["content"]) for c in cards], [("real", "sfw")] * 2)
        self.assertTrue(any("pessoa real" in w for w in res["warnings"]))
        # menor de idade segundo o pipeline: SFW e amigo
        script = self.script(avatar_prompt_analyst={"character_type": "fictional", "age": 15, "is_minor": True, "traits": ["x"], "language": "pt-BR"})
        res, prov = self.run_creation({"prompt": "Dois amigos: Ana e Beto", "content": "nsfw", "count": 2}, script)
        self.assertTrue(all(self.store.avatars.get(i)["content"] == "sfw" for i in res["avatar_ids"]))

    def test_demo_mode_keeps_the_designer_text_and_runs_every_stage(self):
        from asta.agents.avatar_pipeline import AvatarPipeline

        res = AvatarPipeline(self.store, self.events.append).run({"prompt": "Uma amiga chamada Luna, gosta de astronomia"})
        done = next(e for e in self.events if e["type"] == "step" and e["id"] == "prompts" and e["status"] in ("done", "warn"))
        self.assertEqual(done["detail"]["count"], 1)
        self.assertIn("Luna", self.store.avatars.get(res["avatar_ids"][0])["system_prompt"])
        self.assertNotIn("..", self.store.avatars.get(res["avatar_ids"][0])["system_prompt"])


class SystemPromptApiTests(ServerCase):
    def test_api_runs_the_pipeline_as_a_job_and_validates(self):
        status, r = self.c.json("POST", "/api/avatars/system-prompt", {"draft": {"name": "Mira", "personality": "gentil"}, "instructions": "ama jardinagem"})
        self.assertEqual(status, 200, r)
        ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        self.assertEqual([e["id"] for e in ev if e["type"] == "step" and e["status"] == "done"], ["analyze", "generate", "review", "deliver"])
        done = next(e for e in ev if e["type"] == "done")
        self.assertIn("Mira", done["system_prompt"])
        self.assertEqual(self.c.json("POST", "/api/avatars/system-prompt", {"avatar_id": "nao-existe"})[0], 404)
        status, r = self.c.json("POST", "/api/avatars/system-prompt", {})
        ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        self.assertTrue(any(e["type"] == "error" and e.get("kind") == "validation" for e in ev))

    def test_api_apply_to_a_saved_avatar_and_real_person_stays_sfw(self):
        status, card = self.c.json("POST", "/api/avatars", {"name": "Quem", "age": 33, "content": "nsfw", "personality": "misteriosa"})
        status, r = self.c.json("POST", "/api/avatars/system-prompt", {"avatar_id": card["id"], "apply": True, "content": "nsfw", "character_type": "real"})
        done = next(e for e in self.c.sse(f"/api/jobs/{r['job_id']}/events") if e["type"] == "done")
        saved = self.c.json("GET", f"/api/avatars/{card['id']}")[1]
        self.assertEqual((saved["character_type"], saved["content"]), ("real", "sfw"))
        self.assertEqual(saved["system_prompt"], done["system_prompt"])

    def test_creating_avatars_real_person_is_sfw_and_fictional_can_be_nsfw(self):
        for ctype, want in (("real", "sfw"), ("fictional", "nsfw")):
            status, r = self.c.json("POST", "/api/avatars/generate", {"prompt": "Uma amiga chamada Vera, divertida", "content": "nsfw", "character_type": ctype})
            done = next(e for e in self.c.sse(f"/api/jobs/{r['job_id']}/events") if e["type"] == "done")
            card = self.c.json("GET", f"/api/avatars/{done['avatar_ids'][0]}")[1]
            self.assertEqual((card["character_type"], card["content"]), (ctype, want), ctype)
            if ctype == "real":
                self.assertTrue(any("pessoa real" in w for w in done["warnings"]))


class ChatProviderChoiceTests(TmpCase):
    """As conversas usam IA de verdade sempre que houver alguma (nuvem ou local); o Demo só entra quando nada está disponível."""

    def settings(self, active=None, providers=None):
        from asta.storage import DEFAULT_SETTINGS
        import copy

        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["active"].update(active or {})
        s["providers"].update(providers or {})
        return s

    def resolve(self, settings, llama=False):
        from unittest import mock

        from asta.providers import auto, lmstudio

        off = {"running": False, "loaded": [], "models": [], "url": "", "native": False, "error": "off"}  # nenhum LM Studio rodando na máquina de testes
        with mock.patch.object(auto, "_llama_installed", return_value=llama), mock.patch.object(lmstudio, "detect", return_value=off):
            return auto.resolve(settings, "characters", self.tmp)

    def test_default_is_auto_and_falls_back_to_demo_with_a_reason_when_nothing_is_available(self):
        s = self.settings()
        self.assertEqual(s["active"]["characters"], "auto")
        provider, info = self.resolve(s)
        self.assertEqual((info["id"], info["demo"], info["auto"]), ("demo", True, True))
        self.assertIn("Nenhum provedor de IA", info["reason"])
        self.assertEqual(self.resolve(self.settings({"characters": "demo"}))[1]["id"], "demo")  # valor antigo = auto

    def test_follows_the_generation_provider_when_it_is_usable(self):
        for chars in ("auto", "demo"):  # "demo" é o valor antigo, que também passa a seguir a IA configurada
            provider, info = self.resolve(self.settings({"generation": "anthropic", "characters": chars}, {"anthropic": {"api_key": "k"}}))
            self.assertEqual((info["id"], info["demo"], info["auto"]), ("anthropic", False, True), chars)
        # sem a chave não é usável: não finge que é IA
        self.assertTrue(self.resolve(self.settings({"generation": "anthropic"}))[1]["demo"])
        # servidor local sem chave: precisa do modelo
        self.assertTrue(self.resolve(self.settings({"generation": "ollama"}))[1]["demo"])
        self.assertEqual(self.resolve(self.settings({"generation": "ollama"}, {"ollama": {"model": "llama3"}}))[1]["id"], "ollama")

    def test_an_explicit_choice_is_always_respected(self):
        provider, info = self.resolve(self.settings({"generation": "anthropic", "characters": "openai"}, {"anthropic": {"api_key": "k"}}))
        self.assertEqual((info["id"], info["auto"], info["demo"]), ("openai", False, False))  # sem chave, o erro aparece na conversa: nada de trocar por outro

    def test_local_model_is_used_when_the_library_is_there(self):
        (self.tmp / "Qwen3.8-2B-Q8_0.gguf").write_bytes(b"x")  # o pré-instalado, já baixado
        provider, info = self.resolve(self.settings(), llama=True)
        self.assertEqual((info["id"], info["model"], info["demo"], info["auto"]), ("local_hf", "Qwen3.8-2B-Q8_0.gguf", False, True))
        # o modelo escolhido pelo usuário tem prioridade sobre o pré-instalado, se o arquivo existir
        (self.tmp / "meu-Q4_K_M.gguf").write_bytes(b"x")
        self.assertEqual(self.resolve(self.settings({}, {"local_hf": {"model": "meu-Q4_K_M.gguf"}}), llama=True)[1]["model"], "meu-Q4_K_M.gguf")
        # escolhido, mas o arquivo sumiu: cai no pré-instalado
        self.assertEqual(self.resolve(self.settings({}, {"local_hf": {"model": "sumiu.gguf"}}), llama=True)[1]["model"], "Qwen3.8-2B-Q8_0.gguf")

    def test_installed_model_without_the_library_explains_what_to_do(self):
        (self.tmp / "Qwen3.8-2B-Q8_0.gguf").write_bytes(b"x")
        provider, info = self.resolve(self.settings(), llama=False)
        self.assertTrue(info["demo"])
        self.assertIn("llama-cpp-python", info["reason"])
        self.assertIn("Qwen3.8-2B-Q8_0.gguf", info["reason"])
        # gerador local escolhido mas sem a biblioteca: não é usável
        self.assertTrue(self.resolve(self.settings({"generation": "local_hf"}, {"local_hf": {"model": "Qwen3.8-2B-Q8_0.gguf"}}), llama=False)[1]["demo"])


class AvatarCreationUsesAiTests(ServerCase):
    def setUp(self):
        from unittest import mock

        from asta.providers import lmstudio

        p = mock.patch.object(lmstudio, "detect", return_value={"running": False, "loaded": [], "models": [], "url": "", "native": False, "error": "off"})
        p.start()
        self.addCleanup(p.stop)

    def test_creation_uses_the_configured_ai_even_when_generation_is_still_demo_and_warns_when_there_is_none(self):
        # sem nenhuma IA: cria no Demo, mas avisa
        status, r = self.c.json("POST", "/api/avatars/generate", {"prompt": "Uma amiga chamada Luna"})
        done = next(e for e in self.c.sse(f"/api/jobs/{r['job_id']}/events") if e["type"] == "done")
        self.assertTrue(any("modo Demo" in w for w in done["warnings"]))
        # com um modelo local instalado e a biblioteca: usa o modelo (geração continua "demo" nas configurações)
        from unittest import mock

        from asta.providers import auto

        (self.store.models_dir / "Qwen3.8-2B-Q8_0.gguf").write_bytes(b"x")
        self.addCleanup((self.store.models_dir / "Qwen3.8-2B-Q8_0.gguf").unlink)
        with mock.patch.object(auto, "_llama_installed", return_value=True):
            eng = self.c.json("GET", "/api/avatars/engine")[1]
        self.assertEqual((eng["id"], eng["demo"]), ("local_hf", False))


class ChatUsesRealAiTests(ServerCase):
    def test_chat_answers_come_from_the_configured_ai_without_touching_the_characters_role(self):
        with MockProviderServer() as mock:
            self.c.json("PUT", "/api/settings", {"providers": {"custom": {"base_url": mock.url + "/v1", "model": "m", "api_key": "k"}}, "active": {"generation": "custom"}})
            try:
                self.assertEqual(self.c.json("GET", "/api/state")[1]["settings"]["active"]["characters"], "auto")
                eng = self.c.json("GET", "/api/avatars/engine")[1]
                self.assertEqual((eng["id"], eng["demo"], eng["model"]), ("custom", False, "m"))
                aid = self.c.json("POST", "/api/avatars", {"name": "Aya", "age": 26, "greeting": ""})[1]["id"]
                chat = self.c.json("POST", "/api/avatar-chats", {"avatar_ids": [aid]})[1]
                ev = self.c.sse(f"/api/avatar-chats/{chat['id']}/send", {"text": "oi, tudo bem?"}, method="POST")
                self.assertEqual("".join(e.get("text", "") for e in ev if e["type"] == "delta"), "Olá, mundo")  # veio da IA, não de uma resposta pronta
                prov = next(e for e in ev if e["type"] == "provider")
                self.assertEqual((prov["id"], prov["demo"]), ("custom", False))
                self.assertTrue(mock.requests[-1]["body"]["stream"])
            finally:
                self.c.json("PUT", "/api/settings", {"active": {"generation": "demo"}, "providers": {"custom": {"api_key": None}}})

    def test_without_any_ai_the_chat_says_it_is_demo_and_why(self):
        from unittest import mock

        from asta.providers import lmstudio

        with mock.patch.object(lmstudio, "detect", return_value={"running": False, "loaded": [], "models": [], "url": "", "native": False, "error": "off"}):
            self._demo_check()

    def _demo_check(self):
        eng = self.c.json("GET", "/api/avatars/engine")[1]
        self.assertTrue(eng["demo"])
        self.assertTrue(eng["reason"])
        aid = self.c.json("POST", "/api/avatars", {"name": "Aya", "age": 26, "greeting": ""})[1]["id"]
        chat = self.c.json("POST", "/api/avatar-chats", {"avatar_ids": [aid]})[1]
        ev = self.c.sse(f"/api/avatar-chats/{chat['id']}/send", {"text": "oi"}, method="POST")
        prov = next(e for e in ev if e["type"] == "provider")
        self.assertTrue(prov["demo"] and prov["reason"])
        self.assertTrue(any(e["type"] == "message" for e in ev))  # o Demo ainda responde, mas a interface avisa


class HttpRangeTests(ServerCase):
    def test_range_requests_for_media(self):
        aid = self.c.json("POST", "/api/avatars", {"name": "R"})[1]["id"]
        data = tiny_png() + b"\x00" * 200
        self.c.req("PUT", f"/api/avatars/{aid}/portrait", raw=data)
        path = f"/api/avatars/{aid}/portrait"
        status, h, body = self.c.req("GET", path)
        self.assertEqual((status, h["Accept-Ranges"]), (200, "bytes"))
        full = body
        status, h, body = self.c.req("GET", path, headers={"Range": "bytes=0-9"})
        self.assertEqual((status, body, h["Content-Range"]), (206, full[:10], f"bytes 0-9/{len(full)}"))
        status, h, body = self.c.req("GET", path, headers={"Range": "bytes=10-"})
        self.assertEqual((status, body), (206, full[10:]))
        status, h, body = self.c.req("GET", path, headers={"Range": "bytes=-5"})
        self.assertEqual((status, body), (206, full[-5:]))
        status, h, body = self.c.req("GET", path, headers={"Range": "bytes=99999-"})
        self.assertEqual((status, h["Content-Range"]), (416, f"bytes */{len(full)}"))
        status, h, body = self.c.req("GET", path, headers={"Range": "lixo"})
        self.assertEqual((status, body), (200, full))  # cabeçalho inválido: ignora
        status, h, body = self.c.req("HEAD", path)
        self.assertEqual((status, body, int(h["Content-Length"])), (200, b"", len(full)))


if __name__ == "__main__":
    unittest.main()
