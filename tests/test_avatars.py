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
