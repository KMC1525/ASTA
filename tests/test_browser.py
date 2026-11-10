"""Interface no navegador (Chromium via Playwright): telas, hub, Canvas e Editor de vídeo. Pulado se Playwright/Chromium não existirem."""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
from pathlib import Path

from asta.server import make_server
from asta.storage import Store

ROOT = Path(__file__).resolve().parent.parent
BROWSER = Path(__file__).resolve().parent / "browser"


def _playwright_ok() -> bool:
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, text=True, cwd=str(ROOT))
    return r.returncode == 0


@unittest.skipUnless(_playwright_ok(), "Playwright (Node) não disponível")
class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="asta-browser-"))
        cls.store_dir = cls.tmp
        cls.httpd, _ = make_server("127.0.0.1", 0, Store(cls.tmp))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_script(self, name: str, extra_env=None) -> None:
        r = subprocess.run(["node", str(BROWSER / name)], capture_output=True, text=True, timeout=300, env={**os.environ, "ASTA_PORT": str(self.port), **(extra_env or {})})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        failed = [k for k, v in out["checks"].items() if not v]
        self.assertEqual(out["errors"], [])
        self.assertEqual(failed, [], f"verificações que falharam: {failed}")
        self.assertGreater(len(out["checks"]), 3)

    def test_01_every_screen_loads_on_desktop_and_mobile(self):
        self.run_script("smoke_ui.js")

    def test_02_hub_generates_game_and_avatar_and_opens_canvas(self):
        self.run_script("hub_ui.js")

    def test_03_canvas_editor_and_video_timeline(self):
        self.run_script("canvas_ui.js")

    def test_04_local_models_quantization_picker(self):
        from unittest import mock

        from asta import hf
        from tests.test_hf import FakeHF

        fake = FakeHF()
        try:
            with mock.patch.object(hf, "HF", fake.url):
                self.run_script("models_ui.js")
        finally:
            fake.close()

    def test_05_local_canvas_models_ask_for_the_precision_first(self):
        import sys
        from unittest import mock

        from tests.test_canvas import FakeHub

        with mock.patch.dict(sys.modules, {"huggingface_hub": FakeHub(self.tmp).module}):
            self.run_script("local_models_ui.js")

    def test_06_preinstalled_models_card_installs_with_one_click(self):
        from unittest import mock

        from asta import hf, preinstalled
        from tests.test_preinstalled import FakeHub

        hub = FakeHub()
        try:
            with mock.patch.object(hf, "HF", hub.url), mock.patch("asta.hf.shutil.disk_usage", return_value=mock.Mock(free=10 ** 13)), mock.patch.object(preinstalled, "_lib", return_value=False):
                self.run_script("preinstalled_ui.js")
        finally:
            hub.close()
            (self.store_dir / "models" / "Qwen3.8-2B-Q8_0.gguf").unlink(missing_ok=True)

    def test_07_library_lists_local_models_and_deletes_several_at_once(self):
        models = self.store_dir / "models"
        (models / "image").mkdir(parents=True, exist_ok=True)
        for rel in ("Qwen3.8-2B-Q8_0.gguf", "outro-Q4_K_M.gguf", "image/z-image-Q4_K_M.gguf", "image/Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "image/ae.safetensors"):
            (models / rel).write_bytes(b"x" * 2048)
        self.run_script("library_ui.js")
        self.assertTrue((models / "Qwen3.8-2B-Q8_0.gguf").exists())
        self.assertFalse((models / "outro-Q4_K_M.gguf").exists())
        for name in ("z-image-Q4_K_M.gguf", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "ae.safetensors"):
            self.assertFalse((models / "image" / name).exists(), name)  # o Z-Image levou o VAE e o codificador de texto junto
        (models / "Qwen3.8-2B-Q8_0.gguf").unlink()

    def test_08_a_screen_whose_files_fail_to_load_recovers_or_explains(self):
        self.run_script("resilience_ui.js")

    def test_09_avatar_editor_generates_the_system_prompt_and_real_people_stay_sfw(self):
        self.run_script("avatar_prompt_ui.js")

    def test_10_avatar_chat_tells_which_ai_answers_or_that_it_is_only_demo(self):
        self.run_script("avatar_engine_ui.js")

    def test_11_lm_studio_card_detects_the_server_and_picks_a_model(self):
        from tests.test_lmstudio import FakeLMStudio

        fake = FakeLMStudio()
        try:
            self.run_script("lmstudio_ui.js", {"ASTA_FAKE_LM": fake.url})
        finally:
            fake.close()

    def test_12_customization_theme_accent_scale_palette_shortcuts_and_more(self):
        self.run_script("customization_ui.js")
        # a personalização não vaza para os demais testes: tudo de volta ao padrão
        self.assertEqual(Store(self.tmp).get_settings()["ui"]["theme"], "dark")

    def test_13_welcome_shows_only_on_a_fresh_install(self):
        tmp = Path(tempfile.mkdtemp(prefix="asta-welcome-"))
        httpd, _ = make_server("127.0.0.1", 0, Store(tmp))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            r = subprocess.run(["node", str(BROWSER / "welcome_ui.js")], capture_output=True, text=True, timeout=300, env={**os.environ, "ASTA_PORT": str(httpd.server_address[1])})
            self.assertEqual(r.returncode, 0, r.stderr[-1500:])
            out = json.loads(r.stdout.strip().splitlines()[-1])
            failed = [k for k, v in out["checks"].items() if not v]
            self.assertEqual((out["errors"], failed), ([], []))
            self.assertGreater(len(out["checks"]), 4)
        finally:
            httpd.shutdown()
            httpd.server_close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_14_relationship_options_girlfriend_boyfriend_wife_husband(self):
        self.run_script("relationships_ui.js")

    def test_15_chat_interaction_stop_regenerate_edit_delete_draft_scroll_memories(self):
        from tests.test_lmstudio import FakeLMStudio

        def reply(n, body):
            last = str(body["messages"][-1]["content"])
            return ["parte "] * 25 if "[lento]" in last else [f"Resposta {n}"]

        fake = FakeLMStudio(reply=reply, delay=0.12)
        try:
            self.run_script("chat_interaction_ui.js", {"ASTA_FAKE_LM": fake.url})
        finally:
            fake.close()
            from asta.providers import lmstudio

            lmstudio.forget()

    def test_16_chat_2_clean_layout_markdown_model_picker_and_tools_only_run_when_activated(self):
        from tests.test_lmstudio import FakeLMStudio

        def reply(n, body):
            last = str(body["messages"][-1]["content"])
            if "[lento]" in last:
                return ["parte "] * 25
            return ["Aqui vai:\n\n- **item** um\n- item dois com `codigo`\n\n", f"(resposta {n})"]

        fake = FakeLMStudio(reply=reply, delay=0.12)
        try:
            self.run_script("chat_ui.js", {"ASTA_FAKE_LM": fake.url})
        finally:
            fake.close()
            from asta.providers import lmstudio

            lmstudio.forget()

    def test_17_chat_settings_tab_web_search_with_sources_and_thinking_level_next_to_the_model(self):
        from tests.test_lmstudio import MODELS, FakeLMStudio

        found = {"engine": "duckduckgo", "query": "dólar", "results": [{"title": "Dólar hoje", "url": "https://a.com/d", "snippet": "O dólar fechou a R$ 5,10."}]}
        got = {"engine": "duckduckgo", "query": "dólar", "text": "[1] Dólar hoje\nhttps://a.com/d\nO dólar fechou a R$ 5,10.",
               "sources": [{"n": 1, "title": "Dólar hoje", "url": "https://a.com/d", "host": "a.com", "snippet": "", "text": ""}]}
        fake = FakeLMStudio(models=MODELS + [{"id": "openai/gpt-oss-20b", "type": "llm", "state": "loaded"}], reply=lambda n, body: ["Segundo a fonte [1], o dólar fechou a R$ 5,10."])
        try:
            with mock.patch("asta.websearch.search", return_value=found), mock.patch("asta.websearch.gather", return_value=got) as gather:
                self.run_script("chat_settings_ui.js", {"ASTA_FAKE_LM": fake.url})
            posts = [r[2] for r in fake.requests if r[0] == "POST" and r[2]]
            self.assertTrue(any("[WEB SEARCH RESULTS" in str(b["messages"][0]["content"]) and "R$ 5,10" in str(b["messages"][0]["content"]) for b in posts))
            self.assertTrue(any("Responda sempre em tópicos." in str(b["messages"][0]["content"]) for b in posts))
            think = [b for b in posts if b.get("reasoning_effort")]
            self.assertTrue(think and think[-1]["reasoning_effort"] == "high" and think[-1]["max_tokens"] == 3000 + 24000)  # Ultra: esforço high + folga; tamanho da resposta 3.000
            self.assertGreaterEqual(gather.call_count, 2)  # uma no Chat, outra no prompt da ferramenta de criação
            self.assertTrue(any("dólar" in c[0][0] for c in gather.call_args_list))
        finally:
            fake.close()
            from asta.providers import lmstudio

            lmstudio.forget()

    def test_18_chat_streaming_send_bugs_and_the_sources_panel_on_the_right(self):
        import time

        from tests.test_lmstudio import FakeLMStudio

        def reply(n, body):
            c = body["messages"][-1]["content"]
            last = c if isinstance(c, str) else " ".join(p.get("text", "") for p in c)
            if "[stream]" in last:
                return ["palavra "] * 34
            if "[think]" in last:
                return ["<th", "ink>", "6*7 ", "é 42", "</think>", "Resposta ", "limpa."]
            if "[md]" in last:
                return ["## Lista\n\n- a\n  - sub a1\n  - sub a2\n- b\n- c\n- d\n\nVeja https://example.org/x. e [1] sem fonte."]
            if "[lento]" in last:
                return ["parte "] * 30
            if "[web]" in last:
                return ["Segundo [1] e também [2, 3]."]
            return [f"Resposta {n}"]

        srcs = [{"n": i + 1, "title": f"Fonte {'ABCDE'[i]}", "url": f"https://site{i + 1}.org/p", "host": f"site{i + 1}.org", "snippet": f"Trecho da fonte {i + 1}.", "text": "página lida" if i < 2 else ""} for i in range(5)]

        def gather(query, settings, ui_lang="auto"):
            time.sleep(1.0)
            return {"engine": "duckduckgo", "query": query, "text": "[1] Fonte A", "sources": srcs}

        fake = FakeLMStudio(reply=reply, delay=0.1)
        try:
            with mock.patch("asta.websearch.gather", side_effect=gather):
                self.run_script("chat_stream_ui.js", {"ASTA_FAKE_LM": fake.url})
        finally:
            fake.close()
            from asta.providers import lmstudio

            lmstudio.forget()

    def test_19_chat_tabs_new_tab_command_background_answers_and_persistence(self):
        from tests.test_lmstudio import FakeLMStudio

        def reply(n, body):
            c = body["messages"][-1]["content"]
            last = c if isinstance(c, str) else " ".join(p.get("text", "") for p in c)
            return ["parte "] * 24 if "[lento]" in last else [f"Resposta {n}"]

        fake = FakeLMStudio(reply=reply, delay=0.1)
        try:
            self.run_script("chat_tabs_ui.js", {"ASTA_FAKE_LM": fake.url})
        finally:
            fake.close()
            from asta.providers import lmstudio

            lmstudio.forget()

    def test_20_audit_worlds_list_only_worlds_translations_titles_and_config_tabs(self):
        self.run_script("audit_ui.js")

    def test_21_rebuild_tool_rebuilds_a_game_shows_the_legal_notice_and_the_game_runs(self):
        from tests import rebuild_fixtures as F

        d = self.tmp / "rb"
        d.mkdir(exist_ok=True)
        (d / "mv.zip").write_bytes(F.zip_bytes(F.mv_project()))
        (d / "vn.zip").write_bytes(F.zip_bytes({"game/script.rpy": F.RPY.encode()}, "VN"))
        (d / "lixo.zip").write_bytes(F.zip_bytes({"leiame.txt": b"oi"}))
        self.run_script("rebuild_ui.js", {"ASTA_REBUILD_MV": str(d / "mv.zip"), "ASTA_REBUILD_RPY": str(d / "vn.zip"), "ASTA_REBUILD_BAD": str(d / "lixo.zip")})

    def test_22_every_section_creates_inside_its_own_page_without_going_to_the_chat(self):
        from tests import rebuild_fixtures as F

        d = self.tmp / "rb2"
        d.mkdir(exist_ok=True)
        (d / "mv.zip").write_bytes(F.zip_bytes(F.mv_project()))
        self.run_script("sections_inline_ui.js", {"ASTA_REBUILD_MV": str(d / "mv.zip")})

    def test_23_tab_strip_slides_sideways_and_right_click_splits_the_view_in_two(self):
        from tests.test_lmstudio import FakeLMStudio

        fake = FakeLMStudio(reply=lambda n, body: [f"Resposta {n}"], delay=0.1)
        try:
            self.run_script("chat_split_ui.js", {"ASTA_FAKE_LM": fake.url})
        finally:
            fake.close()
            from asta.providers import lmstudio

            lmstudio.forget()

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg não instalado")
    def test_24_studio_create_generate_scene_by_scene_timeline_export_and_autoedit(self):
        from tests.test_studio import make_media

        d = self.tmp / "studio"
        d.mkdir(exist_ok=True)
        m = make_media(d)
        self.run_script("studio_ui.js", {"ASTA_AE_VIDEO": str(m["game"]), "ASTA_AE_MUSIC": str(m["music"])})

    def test_25_config_sections_groups_defaults_and_reset(self):
        self.run_script("config_sections_ui.js")

    def test_26_mobile_device_adaptation_install_update_prompt_and_settings_tab(self):
        self.run_script("mobile_ui.js")

    def test_27_android_app_shell_connects_remembers_and_offers_the_new_apk(self):
        self.run_script("mobile_shell_ui.js")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg não instalado")
    def test_28_canvas_new_nodes_palette_controls_and_a_real_chain(self):
        self.run_script("canvas_nodes_ui.js")

    def test_29_studio_manual_timeline_without_generating(self):
        self.run_script("studio_manual_ui.js")

    def test_30_studio_timeline_mixer_zoom_bar_bin_menu_and_collapsible_tracks(self):
        self.run_script("studio_mixer_ui.js")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg não instalado")
    def test_31_studio_manual_edit_track_choice_speed_and_saving(self):
        self.run_script("studio_edit_ui.js")


    def test_32_computer_use_section_ask_mode_chat_card_settings_and_phone(self):
        home = Path(tempfile.mkdtemp(prefix="asta-cu-home-"))
        (home / "Documents").mkdir()
        try:
            # sem IA de verdade: outros testes deixam provedores/modelos locais configurados e o modo automático os usaria; aqui o Demo (regras) é o que se quer exercitar
            from asta.providers import build_provider

            mgr = self.httpd.RequestHandlerClass.app.computer
            mgr._resolve = lambda settings: (build_provider(settings, "demo", self.store_dir / "models"), {"id": "demo", "label": "Demo", "model": "demo", "demo": True})
            try:
                self.run_script("computer_ui.js", {"ASTA_TEST_HOME": str(home)})   # caminhos absolutos: a pasta pessoal de verdade não é tocada
            finally:
                mgr._resolve = None
            self.assertTrue((home / "Documents" / "UiNegada").exists() is False)
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_33_code_section_folders_colors_states_ask_mode_settings_and_phone(self):
        from asta.providers import build_provider

        mgr = self.httpd.RequestHandlerClass.app.code
        mgr._resolve = lambda settings: (build_provider(settings, "demo", self.store_dir / "models"), {"id": "demo", "label": "Demo", "model": "demo", "demo": True})   # sem IA: as regras entendem «rode os testes»
        try:
            self.run_script("code_ui.js")
        finally:
            mgr._resolve = None

    def test_33b_work_people_board_files_requests_activities_and_network(self):
        from asta.providers import build_provider

        mgr = self.httpd.RequestHandlerClass.app.work
        mgr._resolve = lambda settings: (build_provider(settings, "demo", self.store_dir / "models"), {"id": "demo", "label": "Demo", "model": "demo", "demo": True})   # sem IA: o Work usa as regras automáticas
        try:
            self.run_script("work_ui.js")
        finally:
            mgr._resolve = None
            mgr.stop()

    def test_34_code_team_shows_agents_plan_actions_diff_files_and_undo(self):
        from tests.test_code_team import Scripted, act, fin, per_step, plan, step

        llm = Scripted(planner=lambda p, s: plan(step("s1", "Criar a.py", files=["a.py"]), step("s2", "Criar b.py", files=["b.py"]), step("s3", "Ajustar keep.txt", "docs", files=["keep.txt"])),
                       worker=per_step(s1=[act("write_file", path="a.py", content="A = 1\n"), fin("a.py criado")], s2=[act("write_file", path="b.py", content="B = 2\n"), fin("b.py criado")],
                                       s3=[act("edit_file", path="keep.txt", old="antes", new="depois"), fin("keep.txt ajustado")]))
        mgr = self.httpd.RequestHandlerClass.app.code
        mgr._resolve = lambda settings: (llm, {"id": "fake", "label": "Fake", "model": "fake-model", "demo": False})
        try:
            self.run_script("code_team_ui.js")
        finally:
            mgr._resolve = None

    def test_35_studio_tools_layers_shift_a_effects_sfx_captions_waveform_and_many_clips(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg não instalado")
        self.run_script("studio_tools_ui.js")

    def test_36_canvas_model_search_bar_quantizations_download_use_and_send_to_studio(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg não instalado")
        self.run_script("canvas_hub_ui.js")

    def test_37_canvas_media_nodes_show_only_model_and_resolution(self):
        self.run_script("canvas_simple_nodes_ui.js")

    def test_38_canvas_at_mentions_pick_images_for_the_prompt(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg não instalado")
        self.run_script("canvas_mention_ui.js")

    def test_39_canvas_model_picker_lists_installed_and_cloud_models(self):
        self.run_script("canvas_model_picker_ui.js")

    def test_40_canvas_missing_gguf_support_files_offer_a_download_button(self):
        self.run_script("canvas_support_ui.js")
    def test_41_team_of_agents_in_every_section_effort_levels_and_1_4_8_12_16_agents(self):
        self.run_script("team_ui.js")

    def test_42_canvas_prompt_box_generates_a_flow_and_minimizes(self):
        self.run_script("canvas_flow_ui.js")

    def test_43_creation_toolbar_with_many_options_stays_inside_the_box(self):
        self.run_script("composer_overflow_ui.js")

    def test_44_no_screen_writes_the_text_null(self):
        self.run_script("null_text_ui.js")

    def test_45_game_engine_all_seven_tabs(self):
        self.run_script("engine_ui.js")

    def test_46_studio_timeline_resize_four_sides_swap_windows_and_json_layout_presets(self):
        self.run_script("studio_layout_ui.js")


if __name__ == "__main__":
    unittest.main()
