"""Testes do núcleo: cards, armazenamento, esquema, JSON de LLM, anexos."""
import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import attachments as att  # noqa: E402
from asta import cards  # noqa: E402
from asta.agents import rulebased, schema  # noqa: E402
from asta.agents.llm import extract_json  # noqa: E402
from asta.storage import Store  # noqa: E402


class TmpCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="asta-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class CardsTests(TmpCase):
    def test_character_normalization_clamps_and_defaults(self):
        c = cards.normalize_character({"name": "  Mira ", "tags": "Herbalista, curiosa , herbalista", "appearance": {"height": 99, "skin": "#abc", "hair_style": "afro"},
                                       "voice": {"pitch": 10, "engine": "x"}})
        self.assertEqual(c["name"], "Mira")
        self.assertEqual(c["tags"], ["herbalista", "curiosa"])
        self.assertEqual(c["appearance"]["height"], 2.3)
        self.assertEqual(c["appearance"]["skin"], "#aabbcc")
        self.assertEqual(c["appearance"]["hair_style"], "short")
        self.assertEqual(c["voice"]["pitch"], 2.0)
        self.assertEqual(c["voice"]["engine"], "auto")
        self.assertEqual(c["schema"], cards.CHARACTER_SCHEMA)

    def test_import_sillytavern_v2(self):
        card = cards.import_character({"spec": "chara_card_v2", "data": {"name": "Lia", "description": "Uma maga.", "personality": "calma", "first_mes": "Oi!", "tags": ["fantasia"]}})
        self.assertEqual(card["name"], "Lia")
        self.assertIn("Uma maga.", card["system_prompt"])
        self.assertIn("calma", card["system_prompt"])
        self.assertEqual(card["greeting"], "Oi!")

    def test_import_png_card(self):
        payload = base64.b64encode(json.dumps({"name": "PNG Char", "description": "desc"}).encode())

        def chunk(t, d):
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"tEXt", b"chara\x00" + payload) + chunk(b"IEND", b"")
        self.assertEqual(cards.character_from_png(png)["name"], "PNG Char")
        with self.assertRaises(ValueError):
            cards.character_from_png(b"not a png")

    def test_card_store_crud(self):
        store = Store(self.tmp)
        c = store.characters.save({"name": "A"})
        self.assertTrue(c["id"].startswith("c_"))
        c2 = store.characters.save({"name": "B"}, c["id"])
        self.assertEqual(c2["id"], c["id"])
        self.assertEqual(store.characters.get(c["id"])["name"], "B")
        self.assertIsNone(store.characters.get("../etc/passwd"))
        self.assertTrue(store.characters.delete(c["id"]))
        self.assertEqual(store.characters.list(), [])


class SettingsTests(TmpCase):
    def test_secrets_are_masked_and_semantics(self):
        store = Store(self.tmp)
        store.save_settings({"providers": {"openai": {"api_key": "sk-secret", "model": "m1"}}, "hf": {"token": "hf_x"}})
        pub = store.public_settings()
        self.assertNotIn("sk-secret", json.dumps(pub))
        self.assertTrue(pub["providers"]["openai"]["has_key"])
        self.assertTrue(pub["hf"]["token_set"])
        self.assertEqual(store.get_settings()["providers"]["openai"]["api_key"], "sk-secret")
        # "" mantém; None apaga; flags somente-leitura são ignoradas
        store.save_settings({"providers": {"openai": {"api_key": "", "has_key": True, "model": "m2"}}, "hf": {"token": "", "token_set": True}})
        s = store.get_settings()
        self.assertEqual(s["providers"]["openai"]["api_key"], "sk-secret")
        self.assertEqual(s["providers"]["openai"]["model"], "m2")
        self.assertNotIn("has_key", s["providers"]["openai"])
        store.save_settings({"providers": {"openai": {"api_key": None}}, "hf": {"token": None}})
        s = store.get_settings()
        self.assertNotIn("api_key", s["providers"]["openai"])
        self.assertEqual(s["hf"]["token"], "")

    def test_settings_file_is_private(self):
        store = Store(self.tmp)
        store.save_settings({"language": "en"})
        if os.name == "posix":
            self.assertEqual(oct(store.settings_path.stat().st_mode & 0o777), "0o600")


class SchemaTests(unittest.TestCase):
    def test_world_normalization_respects_budget(self):
        raw = {
            "title": "X", "environment": {"biome": "lava", "size": 99999, "weather": "rain", "time_of_day": 30},
            "structures": [{"type": "house", "x": 1e9, "z": -1e9}] * 500 + [{"type": "spaceship", "x": 0, "z": 0}],
            "npcs": [{"id": "a", "char": "a", "x": 5, "z": 5}, {"id": "ghost", "char": "ghost"}] + [{"id": f"n{i}", "char": "a"} for i in range(30)],
            "audio": {"ambience": "lasers", "music": {"tempo": 1000, "file": "evil.mp3"}},
        }
        w = schema.normalize_world(raw, "low", {"max_npcs": 0}, ["a"], [])
        b = schema.BUDGETS["low"]
        self.assertEqual(w["environment"]["biome"], "temperate")
        self.assertLessEqual(w["environment"]["size"], b["max_size"])
        self.assertLessEqual(len(w["structures"]), b["structures"])
        self.assertTrue(all(s["type"] in schema.STRUCTURES for s in w["structures"]))
        half = w["environment"]["size"] / 2
        self.assertTrue(all(abs(s["x"]) <= half and abs(s["z"]) <= half for s in w["structures"]))
        self.assertLessEqual(len(w["npcs"]), b["npcs"])
        self.assertTrue(all(n["char"] == "a" for n in w["npcs"]))
        self.assertEqual(len({n["id"] for n in w["npcs"]}), len(w["npcs"]))
        self.assertLess(w["environment"]["time_of_day"], 24)
        self.assertEqual(w["audio"]["ambience"], "rain")  # inválido → derivado do clima
        self.assertEqual(w["audio"]["music"]["tempo"], 160)
        self.assertEqual(w["audio"]["music"]["file"], "")  # arquivo não anexado é descartado
        self.assertIn("high", w["quality"]["tiers"])

    def test_user_npc_cap(self):
        raw = {"npcs": [{"id": f"n{i}", "char": "a"} for i in range(10)]}
        self.assertEqual(len(schema.normalize_world(raw, "high", {"max_npcs": 3}, ["a"])["npcs"]), 3)


class JsonExtractTests(unittest.TestCase):
    def test_variants(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(extract_json('Claro! ```json\n{"a": [1,2,{"b":"}"}]}\n``` fim'), {"a": [1, 2, {"b": "}"}]})
        self.assertEqual(extract_json('texto {"a": 1,} depois'), {"a": 1})
        self.assertEqual(extract_json('{"s": "com \\" aspas e { chave"}'), {"s": 'com " aspas e { chave'})
        with self.assertRaises(ValueError):
            extract_json("sem json aqui")
        with self.assertRaises(ValueError):
            extract_json('{"cortado": [1, 2')


class DemoGeneratorTests(unittest.TestCase):
    def test_language_and_keywords(self):
        self.assertEqual(rulebased.detect_lang("Uma vila na floresta com você"), "pt")
        self.assertEqual(rulebased.detect_lang("A village in the forest with you"), "en")
        b = rulebased.analyst({"prompt": "Um deserto à noite com tempestade de areia, clima tenso"})
        self.assertEqual(b["biome"], "desert")
        self.assertEqual(b["mood"], "tense")
        self.assertGreaterEqual(b["time_of_day"], 20)

    def test_npc_reply_actions(self):
        sys = "# You are Mira.\nRole: herbalista\nWeather: rain"
        self.assertIn("[[action:follow]]", rulebased.npc_reply(sys, "Venha comigo, por favor"))
        self.assertIn("[[action:stay]]", rulebased.npc_reply(sys, "Fique aqui"))
        self.assertIn("Mira", rulebased.npc_reply(sys, "Quem é você?"))
        self.assertIn("[[action:follow]]", rulebased.npc_reply(sys, "please follow me"))


def make_docx(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="x"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p><w:p><w:r><w:t>Segundo &amp; parágrafo</w:t></w:r></w:p></w:body></w:document>')


class AttachmentTests(TmpCase):
    def test_text_and_csv(self):
        p = self.tmp / "lore.md"
        p.write_text("# Lore\nO reino de Alder.", "utf-8")
        a = att.analyze(p, "lore.md")
        self.assertEqual(a["kind"], "text")
        self.assertIn("reino de Alder", a["text"])
        c = self.tmp / "d.csv"
        c.write_text("a,b\n1,2", "utf-8")
        self.assertEqual(att.analyze(c, "d.csv")["kind"], "spreadsheet")

    def test_truncation_note(self):
        p = self.tmp / "big.txt"
        p.write_text("x" * 50000, "utf-8")
        a = att.analyze(p, "big.txt", max_chars=1000)
        self.assertEqual(len(a["text"]), 1000)
        self.assertTrue(any("truncado" in n for n in a["notes"]))

    def test_docx_xlsx_pptx(self):
        d = self.tmp / "a.docx"
        make_docx(d, "Olá docx")
        a = att.analyze(d, "a.docx")
        self.assertEqual(a["kind"], "document")
        self.assertIn("Olá docx", a["text"])
        self.assertIn("Segundo & parágrafo", a["text"])

        x = self.tmp / "b.xlsx"
        with zipfile.ZipFile(x, "w") as z:
            z.writestr("xl/workbook.xml", '<workbook xmlns="m"><sheets><sheet name="Itens"/></sheets></workbook>')
            z.writestr("xl/sharedStrings.xml", '<sst xmlns="m"><si><t>Espada</t></si><si><t>Escudo</t></si></sst>')
            z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="m"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>10</v></c></row><row r="2"><c r="A2" t="s"><v>1</v></c><c r="C2"><v>7</v></c></row></sheetData></worksheet>')
        a = att.analyze(x, "b.xlsx")
        self.assertEqual(a["kind"], "spreadsheet")
        self.assertIn("[Itens]", a["text"])
        self.assertIn("Espada,10", a["text"])
        self.assertIn("Escudo,,7", a["text"])

        p = self.tmp / "c.pptx"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("ppt/slides/slide1.xml", '<p:sld xmlns:a="a" xmlns:p="p"><a:p><a:r><a:t>Título do slide</a:t></a:r></a:p></p:sld>')
            z.writestr("ppt/slides/slide2.xml", '<p:sld xmlns:a="a" xmlns:p="p"><a:p><a:r><a:t>Segundo</a:t></a:r></a:p></p:sld>')
        a = att.analyze(p, "c.pptx")
        self.assertEqual(a["kind"], "presentation")
        self.assertLess(a["text"].index("Título do slide"), a["text"].index("Segundo"))

    def test_pdf_naive_text(self):
        p = self.tmp / "t.pdf"
        content = b"BT /F1 12 Tf (Ola PDF mundo) Tj ET"
        comp = zlib.compress(content)
        p.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Length " + str(len(comp)).encode() + b" /Filter /FlateDecode >>\nstream\n" + comp + b"\nendstream\nendobj\n%%EOF")
        a = att.analyze(p, "t.pdf")
        self.assertEqual(a["kind"], "document")
        self.assertIn("Ola PDF mundo", a["text"])

    def test_image_size_and_vision_payload(self):
        png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 640, 480) + b"\x08\x02\x00\x00\x00" + b"\x00" * 4
        self.assertEqual(att.image_size(png), (640, 480))
        p = self.tmp / "i.png"
        p.write_bytes(png)
        a = att.analyze(p, "i.png")
        self.assertEqual(a["kind"], "image")
        self.assertEqual(len(a["images"]), 1)
        self.assertEqual(a["images"][0]["media_type"], "image/png")
        self.assertTrue(any("640×480" in n for n in a["notes"]))

    def test_audio_transcription_callback(self):
        p = self.tmp / "voz.wav"
        import wave

        with wave.open(str(p), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000)
            w.writeframes(b"\x00\x00" * 8000)
        a = att.analyze(p, "voz.wav", transcribe=lambda path: "uma narração de teste")
        self.assertEqual(a["kind"], "audio")
        self.assertIn("uma narração de teste", a["text"])
        no = att.analyze(p, "voz.wav")
        self.assertTrue(any("transcrição" in n for n in no["notes"]))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg não instalado")
    def test_video_frames_with_ffmpeg(self):
        v = self.tmp / "clip.mp4"
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=2", "-pix_fmt", "yuv420p", str(v)])
        self.assertEqual(r.returncode, 0)
        a = att.analyze(v, "clip.mp4")
        self.assertEqual(a["kind"], "video")
        self.assertGreaterEqual(len(a["images"]), 2)
        self.assertEqual(a["images"][0]["media_type"], "image/jpeg")

    def test_digest_and_corrupt_files(self):
        bad = self.tmp / "x.docx"
        bad.write_bytes(b"isto nao e zip")
        a = att.analyze(bad, "x.docx")
        self.assertTrue(any("não foi possível" in n for n in a["notes"]))
        digest = att.build_digest([a])
        self.assertIn("Anexo 1: x.docx", digest)
        self.assertEqual(att.build_digest([]), "")


if __name__ == "__main__":
    unittest.main()
