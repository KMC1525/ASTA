"""Personalização da interface: preferências validadas (`settings.ui`), exportar/importar/restaurar configurações sem segredos."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import uiprefs  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.test_core import TmpCase  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402


class NormalizeTests(unittest.TestCase):
    def test_defaults_keep_the_look_the_project_always_had(self):
        d = uiprefs.normalize_ui(None)
        self.assertEqual((d["theme"], d["accent"], d["scale"], d["density"], d["send_key"], d["start_page"]), ("dark", "", 100, "comfortable", "enter", "main"))
        self.assertEqual(set(d), set(uiprefs.DEFAULT_UI))  # todas as chaves, sempre
        self.assertEqual(uiprefs.normalize_ui(d), d)  # idempotente
        self.assertTrue(d["shortcuts"])
        self.assertFalse(d["welcome_done"])

    def test_valid_values_are_kept(self):
        ui = uiprefs.normalize_ui({"theme": "light", "accent": "#4F8CFF", "scale": 125, "density": "compact", "motion": "reduce", "font": "serif", "chat_size": "large",
                                   "send_key": "ctrl_enter", "start_page": "avatars", "sidebar_hidden": ["games", "canvas"], "shortcuts": False, "welcome_done": True})
        self.assertEqual((ui["theme"], ui["accent"], ui["scale"], ui["density"], ui["motion"], ui["font"], ui["chat_size"]),
                         ("light", "#4f8cff", 125, "compact", "reduce", "serif", "large"))
        self.assertEqual((ui["send_key"], ui["start_page"], ui["sidebar_hidden"], ui["shortcuts"], ui["welcome_done"]), ("ctrl_enter", "avatars", ["games", "canvas"], False, True))

    def test_invalid_values_fall_back_instead_of_breaking_the_interface(self):
        ui = uiprefs.normalize_ui({"theme": "neon", "accent": "red; background:url(x)", "scale": "gigante", "density": 3, "motion": None, "font": ["x"], "chat_size": "xl",
                                   "send_key": "space", "start_page": "../../etc", "sidebar_hidden": ["main", "config", "games", "games", 7, "xyz"], "shortcuts": "no", "welcome_done": "yes"})
        self.assertEqual((ui["theme"], ui["accent"], ui["scale"], ui["density"], ui["motion"], ui["font"], ui["chat_size"], ui["send_key"], ui["start_page"]),
                         ("dark", "", 100, "comfortable", "auto", "system", "medium", "enter", "main"))
        self.assertEqual(ui["sidebar_hidden"], ["games"])  # "Principal" e "Configuração" nunca somem; sem repetição
        self.assertTrue(ui["shortcuts"])  # só `false` de verdade desliga
        self.assertFalse(ui["welcome_done"])
        self.assertEqual(uiprefs.normalize_ui({"scale": 137})["scale"], 100)
        self.assertEqual(uiprefs.normalize_ui({"scale": "110"})["scale"], 110)
        self.assertEqual(uiprefs.normalize_ui({"scale": True})["scale"], 100)

    def test_accent_accepts_only_hex_colors(self):
        self.assertEqual(uiprefs.normalize_accent("#abc"), "#aabbcc")
        self.assertEqual(uiprefs.normalize_accent(" #FFAA00 "), "#ffaa00")
        for bad in ("", None, "red", "#12345", "#gggggg", "rgb(1,2,3)", "#fff;x", "url(#fff)"):
            self.assertEqual(uiprefs.normalize_accent(bad), "", bad)


class StorageTests(TmpCase):
    def test_settings_are_sanitized_on_save_and_on_load(self):
        st = Store(self.tmp / "home")
        saved = st.save_settings({"ui": {"theme": "light", "accent": "javascript:alert(1)", "scale": 125}})
        self.assertEqual((saved["ui"]["theme"], saved["ui"]["accent"], saved["ui"]["scale"]), ("light", "", 125))
        # edição manual do settings.json com lixo: a interface continua abrindo com valores válidos
        raw = json.loads(st.settings_path.read_text())
        raw["ui"] = {"theme": "x", "scale": "yy", "sidebar_hidden": "tudo"}
        st.settings_path.write_text(json.dumps(raw))
        ui = st.get_settings()["ui"]
        self.assertEqual((ui["theme"], ui["scale"], ui["sidebar_hidden"]), ("dark", 100, []))
        # um patch parcial não apaga o resto das preferências
        st.save_settings({"ui": {"theme": "light"}})
        st.save_settings({"ui": {"density": "compact"}})
        ui = st.get_settings()["ui"]
        self.assertEqual((ui["theme"], ui["density"]), ("light", "compact"))
        self.assertIn("ui", st.public_settings())


class ExportImportTests(ServerCase):
    def setUp(self):
        self.c.json("PUT", "/api/settings", {"ui": {"theme": "light", "accent": "#4f8cff", "send_key": "ctrl_enter", "sidebar_hidden": ["games"]},
                                              "providers": {"anthropic": {"api_key": "sk-ant-SEGREDO", "model": "claude-x"}, "lmstudio": {"base_url": "http://127.0.0.1:1234", "model": "qwen"}},
                                              "hf": {"token": "hf_SEGREDO"}, "voice": {"tts": {"engine": "server", "base_url": "http://v", "api_key": "voz-SEGREDO", "voice": "alloy"}},
                                              "generation": {"realism": 0.2}, "avatars": {"user_name": "Kaua", "temperature": 0.5}})

    def test_export_has_the_preferences_and_never_a_secret(self):
        st, hdr, body = self.c.req("GET", "/api/settings/export")
        self.assertEqual(st, 200)
        text = body.decode()
        for secret in ("sk-ant-SEGREDO", "hf_SEGREDO", "voz-SEGREDO", "api_key", '"token"'):
            self.assertNotIn(secret, text, secret)
        data = json.loads(text)
        self.assertEqual(data["schema"], "asta.settings.v1")
        s = data["settings"]
        self.assertEqual((s["ui"]["theme"], s["ui"]["accent"], s["ui"]["send_key"], s["ui"]["sidebar_hidden"]), ("light", "#4f8cff", "ctrl_enter", ["games"]))
        self.assertEqual(s["providers"]["anthropic"], {"model": "claude-x"})  # sem a chave
        self.assertEqual(s["providers"]["lmstudio"]["base_url"], "http://127.0.0.1:1234")
        self.assertEqual((s["avatars"]["user_name"], s["generation"]["realism"]), ("Kaua", 0.2))
        self.assertEqual(s["voice"]["tts"]["voice"], "alloy")

    def test_import_applies_a_clean_patch_and_keeps_existing_keys(self):
        payload = {"schema": "asta.settings.v1", "settings": {
            "ui": {"theme": "dark", "accent": "red;x", "scale": 110}, "language": "en", "avatars": {"user_name": "Ana"},
            "providers": {"anthropic": {"api_key": "sk-INVADER", "model": "claude-novo"}, "openai": {"model": "gpt-x", "api_key": "sk-X"}},
            "voice": {"tts": {"api_key": "voz-INVADER", "voice": "nova"}}, "hf": {"token": "hf_INVADER"}, "active": {"characters": "lmstudio", "evil": "x"},
            "unknown_section": {"a": 1}}}
        st, r = self.c.json("POST", "/api/settings/import", payload)
        self.assertEqual(st, 200, r)
        s = self.store.get_settings()
        self.assertEqual((s["ui"]["theme"], s["ui"]["accent"], s["ui"]["scale"], s["language"], s["avatars"]["user_name"]), ("dark", "", 110, "en", "Ana"))
        self.assertTrue(s["ui"]["welcome_done"])  # quem importa já conhece o ASTA
        self.assertEqual(s["providers"]["anthropic"]["api_key"], "sk-ant-SEGREDO")  # a chave de quem importa não é trocada
        self.assertEqual(s["providers"]["anthropic"]["model"], "claude-novo")
        self.assertNotIn("api_key", s["providers"].get("openai", {}))
        self.assertEqual(s["voice"]["tts"]["api_key"], "voz-SEGREDO")
        self.assertEqual(s["voice"]["tts"]["voice"], "nova")
        self.assertEqual(s["hf"]["token"], "hf_SEGREDO")
        self.assertEqual(s["active"]["characters"], "lmstudio")
        self.assertNotIn("unknown_section", s)
        self.assertNotIn("evil", s["active"])
        self.assertNotIn("sk-", json.dumps(r))  # a resposta nunca devolve segredos

    def test_import_rejects_files_that_are_not_exports(self):
        for bad in ({"settings": {}}, {"schema": "outro", "settings": {}}, {"schema": "asta.settings.v1"}, ["x"], "texto"):
            self.assertEqual(self.c.json("POST", "/api/settings/import", bad)[0], 400, bad)

    def test_export_then_import_round_trips_on_a_fresh_install(self):
        data = json.loads(self.c.req("GET", "/api/settings/export")[2])
        other = Store(tempfile.mkdtemp())
        other.save_settings(uiprefs.import_patch(data))
        a, b = self.store.get_settings(), other.get_settings()
        self.assertEqual({k: a["ui"][k] for k in a["ui"] if k != "welcome_done"}, {k: b["ui"][k] for k in b["ui"] if k != "welcome_done"})
        self.assertEqual(b["providers"]["lmstudio"]["model"], "qwen")
        self.assertFalse(b["providers"].get("anthropic", {}).get("api_key"))

    def test_reset_sections_never_touches_secrets(self):
        st, r = self.c.json("POST", "/api/settings/reset", {"section": "ui"})
        self.assertEqual(st, 200)
        self.assertEqual((r["ui"]["theme"], r["ui"]["accent"], r["ui"]["send_key"], r["ui"]["sidebar_hidden"]), ("dark", "", "enter", []))
        self.assertTrue(r["ui"]["welcome_done"])
        self.assertEqual(self.store.get_settings()["providers"]["anthropic"]["api_key"], "sk-ant-SEGREDO")
        st, r = self.c.json("POST", "/api/settings/reset", {"section": "avatars"})
        self.assertEqual(r["avatars"]["user_name"], "")
        self.assertEqual(self.c.json("POST", "/api/settings/reset", {"section": "voice"})[0], 400)  # voz tem chaves
        self.assertEqual(self.c.json("POST", "/api/settings/reset", {"section": "providers"})[0], 400)
        self.assertEqual(self.c.json("POST", "/api/settings/reset", {})[0], 400)
        self.assertEqual(self.store.get_settings()["voice"]["tts"]["api_key"], "voz-SEGREDO")


if __name__ == "__main__":
    unittest.main()
