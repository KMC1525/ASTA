"""Game Engine (v0.19): esquema e validação, gerador sem IA (2D/2.5D/3D/VR/AR), mapas, áudio, arte, gerenciador de projetos (caminhos seguros, histórico),
IA com fallback (agentes simulados), exportações (web, Windows, macOS, Linux, Android, iOS) e a API HTTP — incluindo o jogo isolado em /api/engine/play."""
import base64
import io
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.gameengine import EngineError, EngineManager, agents as eai, art, audio, exporter, maps as gmaps, schema as S, templates  # noqa: E402
from asta.server import make_server  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.helpers import Client  # noqa: E402

COMBOS = [("2d", "platformer"), ("2d", "topdown"), ("2d", "shooter"), ("2.5d", "iso"), ("2.5d", "platformer"), ("3d", "explore"), ("3d", "fps"), ("vr", "vr_explore"), ("vr", "vr_room"), ("ar", "ar_place"), ("ar", "ar_hunt")]


class FakeProvider:
    id, model, vision = "fake", "fake-1", False

    def __init__(self, replies=None, fail=False):
        self.replies, self.fail, self.calls = replies or {}, fail, []

    def chat(self, messages, system="", **kw):
        self.calls.append(system)
        if self.fail:
            return "isto não é json"
        for role, reply in self.replies.items():
            if f"ROLE: {role}" in system:
                return json.dumps(reply)
        return "{}"


class FakeJob:
    cancelled = False

    def __init__(self):
        self.events = []

    def emit(self, ev):
        self.events.append(ev)


class SchemaTests(unittest.TestCase):
    def test_scene_is_validated_and_defaults_are_kept_explicit(self):
        raw = {"root": {"type": "Node2D", "name": "X", "children": [
            {"type": "Sprite2D", "name": "P", "x": 5, "w": 99999, "color": "#abc", "behaviors": [{"type": "player_platformer", "speed": "9999"}, {"type": "inventada"}], "evil": "<script>"},
            {"type": "Mesh3D", "name": "no 2D"}, {"type": "Sprite2D", "id": "n1"}, {"type": "Sprite2D", "id": "n1"}]}}
        sc = S.norm_scene(raw, "2d")
        kids = sc["root"]["children"]
        self.assertEqual(kids[0]["w"], 4096)                       # limitado
        self.assertNotIn("evil", kids[0])                          # propriedade fora do catálogo some
        self.assertEqual(kids[0]["behaviors"], [{"type": "player_platformer", "speed": 900}])   # comportamento inventado some; valor limitado
        self.assertEqual(kids[1]["type"], "Node2D")                # tipo 3D numa cena 2D vira nó comum
        ids = [k["id"] for k in kids] + [sc["root"]["id"]]
        self.assertEqual(len(ids), len(set(ids)))                  # ids únicos

    def test_scene_limits_and_errors(self):
        with self.assertRaises(ValueError):
            S.norm_scene("não é objeto")
        deep = {"type": "Node2D"}
        cur = deep
        for _ in range(40):
            cur["children"] = [{"type": "Node2D"}]
            cur = cur["children"][0]
        sc = S.norm_scene({"root": deep}, "2d")
        self.assertLessEqual(S.count_nodes(sc["root"]), S.MAX_DEPTH + 2)
        many = {"root": {"type": "Node2D", "children": [{"type": "Sprite2D"} for _ in range(S.MAX_NODES + 50)]}}
        self.assertLessEqual(S.count_nodes(S.norm_scene(many, "2d")["root"]), S.MAX_NODES)

    def test_map_validation_cuts_and_cleans(self):
        m = S.norm_map({"kind": "2d", "w": 9999, "h": 3, "palette": {"1": {"color": "red", "solid": True}, "x": {}}, "layers": [{"data": [[1, 7, "a"]]}], "objects": [{"type": "coin", "x": 1, "y": 2}, {"type": "../x"}, {"type": "enemy", "x": "nan"}]})
        self.assertEqual((m["w"], m["h"]), (S.MAP2D_MAX[0], 4))
        self.assertEqual(m["layers"][0]["data"][0][:3], [1, 0, 0])   # 7 não está na paleta; "a" não é número
        self.assertEqual(m["palette"]["1"]["color"], "#888888")
        self.assertEqual([o["type"] for o in m["objects"]], ["coin", "enemy"])
        m3 = S.norm_map({"kind": "3d", "res": 5, "heights": [999, -4, "x"], "size": 99999})
        self.assertEqual(m3["res"], 17)
        self.assertEqual(len(m3["heights"]), 17 * 17)
        self.assertEqual(m3["heights"][:3], [255, 0, 0])
        self.assertEqual(m3["size"], 2000)

    def test_catalog_is_complete(self):
        cat = S.catalog()
        for k, v in cat["node_types"].items():
            self.assertIn(v["dim"], ("2d", "3d", "any"))
            for p in v["props"]:
                self.assertIn(p["t"], ("num", "int", "text", "longtext", "color", "bool", "select", "image", "sound", "map", "node", "scene"))
        for g, v in cat["genres"].items():
            self.assertTrue(set(v["kinds"]) <= set(cat["kinds"]))
        for kind, genre in S.DEFAULT_GENRE.items():
            self.assertIn(kind, S.GENRES[genre]["kinds"])


class GeneratorTests(unittest.TestCase):
    def test_every_kind_builds_a_valid_and_playable_game(self):
        for kind, genre in COMBOS:
            b = templates.build("um jogo de teste", kind, genre, "", "short")
            self.assertEqual(b["meta"]["kind"], kind)
            self.assertEqual(b["meta"]["genre"], genre)
            ai = eai.EngineAI.__new__(eai.EngineAI)
            problems = eai.EngineAI.check_game(ai, b["scenes"], b["maps"], kind)
            self.assertEqual(problems, [], f"{kind}/{genre}")
            self.assertIn("coin", b["sounds"])
            self.assertTrue(b["sounds"]["theme"][:4] == b["sounds"]["coin"][:4] == b"RIFF")
            for sc in b["scenes"].values():
                S.norm_scene(sc, kind)
            for m in b["maps"].values():
                S.norm_map(m)
            self.assertIn("gdd.md", b["docs"])

    def test_detection_from_the_request(self):
        self.assertEqual(templates.detect("quero um jogo de realidade virtual numa sala para arremessar objetos")[:2], ("vr", "vr_room"))
        self.assertEqual(templates.detect("jogo AR realidade aumentada para colocar móveis")[0], "ar")
        self.assertEqual(templates.detect("aventura 3D de primeira pessoa no deserto")[:1], ("3d",))
        self.assertEqual(templates.detect("nave espacial atirando em aliens")[1:], ("shooter", "space"))
        self.assertEqual(templates.detect("jogo isométrico 2.5d numa ilha")[:2], ("2.5d", "iso"))
        self.assertEqual(templates.detect("", "3d", "fps", "lava")[:3], ("3d", "fps", "lava"))   # o que o usuário escolheu vence

    def test_deterministic_and_language(self):
        a = templates.build("a platform game with coins", "2d", "platformer", "", "short")
        b = templates.build("a platform game with coins", "2d", "platformer", "", "short")
        self.assertEqual(a["maps"], b["maps"])
        self.assertEqual(a["meta"]["language"], "en")
        self.assertEqual(templates.build("jogo de plataforma com moedas", "2d")["meta"]["language"], "pt")

    def test_rule_based_edit(self):
        b = templates.build("plataforma", "2d", "platformer", "forest", "short")
        done, ch = templates.apply_edit("deixe de noite e adicione mais inimigos e 7 vidas", b["scenes"], b["maps"], b["meta"], b["settings"])
        self.assertIn("tema → night", done)
        self.assertEqual(ch["settings"]["hp"], 7)
        self.assertTrue(ch["maps"])
        n0 = sum(1 for o in b["maps"]["maps/level1.map.json"]["objects"] if o["type"] in ("enemy", "chaser", "flyer"))
        n1 = sum(1 for o in ch["maps"]["maps/level1.map.json"]["objects"] if o["type"] in ("enemy", "chaser", "flyer"))
        self.assertGreater(n1, n0)


class MapTests(unittest.TestCase):
    def test_2d_maps_have_reachable_goal(self):
        for genre in ("topdown", "iso"):
            m = gmaps.generate_2d(genre, 11, "forest", "short")
            grid = m["layers"][0]["data"]
            player = next(o for o in m["objects"] if o["type"] == "player")
            goal = next(o for o in m["objects"] if o["type"] == "goal")
            if genre == "topdown":
                solid = {int(k) for k, v in m["palette"].items() if v["solid"]} | {5}
                reach = gmaps._bfs(grid, solid, (player["x"], player["y"]))
            else:
                reach = gmaps._bfs_walk(grid, m["heights"], (player["x"], player["y"]))
            self.assertIn((goal["x"], goal["y"]), reach, genre)

    def test_3d_terrain_and_brush(self):
        m = gmaps.generate_3d(5, "forest", "", 140.0, 33, 6, 2)
        self.assertEqual(len(m["heights"]), 33 * 33)
        self.assertTrue(any(o["type"] == "tree" for o in m["objects"]))
        up = gmaps.edit_region_3d(m, "raise", 0, 0, 20, 1.0, 1)
        mid = (33 // 2) * 33 + 33 // 2
        self.assertGreater(up["heights"][mid], m["heights"][mid])
        flat = gmaps.edit_region_3d(m, "flatten", 0, 0, 30, 1.0, 1)
        self.assertEqual(len(flat["heights"]), len(m["heights"]))
        self.assertEqual(up["heights"][0], m["heights"][0])         # fora do raio nada muda

    def test_region_regeneration_keeps_the_rest(self):
        m = gmaps.generate_2d("platformer", 3, "forest", "short")
        out = gmaps.regen_region_2d(m, {"x0": 20, "y0": 0, "x1": 30, "y1": 19}, 99)
        a, b = m["layers"][0]["data"], out["layers"][0]["data"]
        self.assertEqual([r[:20] for r in a], [r[:20] for r in b])
        self.assertTrue(any(o["type"] == "player" for o in out["objects"]))


class MediaTests(unittest.TestCase):
    def test_audio_is_valid_wav(self):
        for n in audio.SFX_NAMES:
            info = audio.wav_info(audio.sfx(n))
            self.assertTrue(info and info["seconds"] > 0.02, n)
        mus = audio.music("epic", 2, 3)
        info = audio.wav_info(mus)
        self.assertTrue(info and 2 < info["seconds"] < 8)
        peaks = audio.wav_peaks(mus, 50)
        self.assertTrue(peaks and max(peaks) <= 1)
        self.assertIsNone(audio.wav_info(b"nada"))
        self.assertEqual(audio.wav_peaks(b"nada"), [])
        self.assertTrue(audio.wav_info(audio.voice_babble("olá mundo")))

    def test_art_and_icons(self):
        for subject in ("player", "enemy", "coin", "tree", "goal", "ship"):
            svg = art.sprite_svg(subject, "#336699")
            self.assertTrue(svg.startswith("<svg") and "</svg>" in svg)
        self.assertEqual(art.pick_subject("quero uma moeda dourada"), "coin")
        self.assertEqual(art.pick_color("um herói vermelho"), "#ef476f")
        png = art.icon_png(64, "Zé")
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png), 100)


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="asta-ge-"))
        self.store = Store(self.tmp)
        self.m = EngineManager(self.store)
        self.meta = self.m.create("Meu Jogo", "2d", "platformer", "forest", "desc")
        self.pid = self.meta["id"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_paths_are_confined(self):
        for bad in ("../x.js", "a/../../x.js", "/etc/passwd", ".hidden.js", "a//b.js", "..\\x.js", "x\x00.js", "a/" + "b/" * 20 + "c.js"):
            with self.assertRaises(EngineError, msg=bad):
                self.m.write_file(self.pid, "game", bad, "x")
        with self.assertRaises(EngineError):
            self.m.write_file(self.pid, "game", "scripts/a.exe", "x")          # tipo não permitido
        with self.assertRaises(EngineError):
            self.m.read_file(self.pid, "game", "../project.json")
        with self.assertRaises(EngineError):
            self.m.write_file(self.pid, "segredo", "a.js", "x")
        with self.assertRaises(EngineError):
            self.m.dir("../../etc")
        link = self.m.dir(self.pid) / "game" / "scripts" / "link.js"
        try:
            link.symlink_to("/etc/hostname")
            with self.assertRaises(EngineError):
                self.m.read_file(self.pid, "game", "scripts/link.js")
        except OSError:
            pass

    def test_file_operations(self):
        self.assertEqual(self.m.write_file(self.pid, "game", "scripts/a.js", "GE.behavior('a', {});")["warnings"], [])
        self.assertIn("JSON com erro", self.m.write_file(self.pid, "game", "data/x.json", "{quebrado")["warnings"][0])
        with self.assertRaises(EngineError):
            self.m.write_file(self.pid, "game", "assets/images/f.png", b"nao e png")
        with self.assertRaises(EngineError):
            self.m.write_file(self.pid, "game", "assets/sound/f.wav", b"nao e wav")
        with self.assertRaises(EngineError):
            self.m.write_file(self.pid, "game", "assets/images/f.svg", "<html>")
        self.m.mkdir(self.pid, "game", "scripts/sub")
        self.m.rename(self.pid, "game", "scripts/a.js", "scripts/sub/b.js")
        self.assertEqual(self.m.read_file(self.pid, "game", "scripts/sub/b.js")["type"], "text")
        with self.assertRaises(EngineError):
            self.m.rename(self.pid, "game", "scripts/sub", "scripts/sub/dentro")
        with self.assertRaises(EngineError):
            self.m.delete_path(self.pid, "game", "scenes")                       # pastas do motor não se apagam
        self.m.delete_path(self.pid, "game", "scripts/sub")
        tree = self.m.tree(self.pid, "game")
        self.assertTrue(any(n["name"] == "scripts" for n in tree["children"]))

    def test_scene_and_map_writes_are_validated(self):
        with self.assertRaises(EngineError):
            self.m.write_file(self.pid, "game", "scenes/main.scene.json", "não json")
        with self.assertRaises(EngineError):
            self.m.write_file(self.pid, "game", "maps/m.map.json", "[1,2]")
        sc = self.m.save_scene(self.pid, "main", {"root": {"type": "Node2D", "children": [{"type": "UILabel", "text": "oi"}]}})
        self.assertEqual(sc["root"]["children"][0]["type"], "UILabel")
        self.assertEqual(self.m.list_scenes(self.pid), ["main"])
        with self.assertRaises(EngineError):
            self.m.delete_scene(self.pid, "main")                                # precisa de ao menos uma cena

    def test_build_bundle_and_history(self):
        build = templates.build("plataforma de floresta", "2d", "platformer", "forest", "short")
        self.m.apply_build(self.pid, build)
        b = self.m.bundle(self.pid)
        self.assertIn("main", b["scenes"])
        self.assertIn("coin", b["assets"]["sounds"])
        self.assertIn("player", b["assets"]["images"])
        js = self.m.data_js(self.pid)
        self.assertTrue(js.startswith("window.GE_DATA=") and "</" not in js)
        html = self.m.index_html(self.pid)
        self.assertIn("engine/ge_2d.js", html)
        self.assertNotIn("three.min.js", html)
        sid = self.m.snapshot(self.pid, "antes")
        self.m.write_file(self.pid, "game", "scripts/novo.js", "// novo")
        self.m.restore(self.pid, sid)
        with self.assertRaises(EngineError):
            self.m.read_file(self.pid, "game", "scripts/novo.js")
        self.assertTrue(self.m.history(self.pid))
        self.m.delete(self.pid)
        with self.assertRaises(EngineError):
            self.m.meta(self.pid)

    def test_zip_import_blocks_traversal(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("proj/scripts/ok.js", "// ok")
            zf.writestr("proj/../../evil.js", "// mau")
            zf.writestr("proj/run.exe", "MZ")
        r = self.m.import_zip(self.pid, "game", buf.getvalue())
        self.assertEqual(r["written"], 1)
        self.assertEqual(r["skipped"], 2)
        self.assertFalse((self.tmp / "evil.js").exists())
        with self.assertRaises(EngineError):
            self.m.import_zip(self.pid, "game", b"isto nao e zip")

    def test_play_files_are_limited(self):
        self.m.apply_build(self.pid, templates.build("x", "2d", "platformer", "", "short"))
        self.assertEqual(self.m.play_file(self.pid, "index.html")[0], "text")
        self.assertEqual(self.m.play_file(self.pid, "engine/ge_core.js")[0], "file")
        for bad in ("engine/../../server.py", "engine/outro.js", "game/../project.json", "../x", "project.json"):
            with self.assertRaises(EngineError, msg=bad):
                self.m.play_file(self.pid, bad)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="asta-ge-ai-"))
        self.store = Store(self.tmp)
        self.m = EngineManager(self.store)
        self.pid = self.m.create("IA", "2d", "platformer", "forest")["id"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ai(self, provider=None, **opts):
        job = FakeJob()
        ai = eai.EngineAI(self.store, self.m, opts, job)
        ai.provider = provider
        ai.error = "" if provider else "sem IA"
        return ai, job

    def test_generate_without_ai_uses_the_rules(self):
        ai, job = self.ai(prompt="aventura 3D num vulcão", language="pt")
        res = ai.generate_game(self.pid)
        self.assertEqual(res["mode"], "new")
        meta = self.m.meta(self.pid)
        self.assertEqual((meta["kind"], meta["theme"]), ("3d", "lava"))
        self.assertTrue(self.m.list_maps(self.pid))
        self.assertTrue(any(e["type"] == "result" for e in job.events))
        self.assertFalse(res["report"]["ai"])
        self.assertTrue(self.m.history(self.pid))

    def test_generate_with_ai_and_invalid_parts_fall_back(self):
        plan = {"title": "Vulcão Sombrio", "pitch": "x", "kind": "3d", "genre": "explore", "theme": "lava", "length": "short", "language": "pt", "enemies": 9, "coins": 1, "hp": 5}
        design = {"summary": "ok", "extras": [{"type": "Label3D", "name": "Placa", "text": "Cuidado", "x": 3, "z": 3}, {"type": "NaoExiste"}, {"type": "Terrain3D"}], "rules": {"win": "collect_all"}}
        writing = {"intro": "Fuja do vulcão!", "dialogues": {"guia": [{"speaker": "Guia", "text": "Corra!"}]}, "gdd_notes": "nota"}
        p = FakeProvider({"Game Planner": plan, "Scene Designer": design, "Writer": writing, "Reviewer": {"approved": True, "summary": "Feito."}})
        ai, job = self.ai(p, prompt="jogo de vulcão")
        res = ai.generate_game(self.pid)
        meta = self.m.meta(self.pid)
        self.assertEqual((meta["name"], meta["kind"], meta["theme"]), ("Vulcão Sombrio", "3d", "lava"))
        sc = self.m.get_scene(self.pid, "main")
        names = [n.get("name") for n in S.walk(sc["root"])]
        self.assertIn("Placa", names)
        self.assertNotIn("NaoExiste", [n["type"] for n in S.walk(sc["root"])])
        self.assertEqual(self.m.bundle(self.pid)["dialogues"]["guia"][0]["text"], "Corra!")
        self.assertEqual(res["summary"], "Feito.")
        self.assertTrue(res["report"]["ai"])
        # IA devolvendo lixo: cada etapa cai no fallback e o jogo sai igual
        ai2, _ = self.ai(FakeProvider(fail=True), prompt="plataforma", mode="new")
        r2 = ai2.generate_game(self.pid)
        self.assertEqual(self.m.meta(self.pid)["kind"], "2d")
        self.assertTrue(all(s["status"] == "fallback" for s in r2["report"]["agents"]))

    def test_choices_beat_the_ai_and_edit_mode_applies_ops(self):
        self.m.apply_build(self.pid, templates.build("plataforma", "2d", "platformer", "forest", "short"))
        sc = self.m.get_scene(self.pid, "main")
        label = next(n for n in S.walk(sc["root"]) if n["type"] == "UILabel")
        ops = {"summary": "feito", "ops": [{"op": "update", "scene": "main", "id": label["id"], "props": {"text": "Placar novo"}},
                                          {"op": "add", "scene": "main", "parent": "", "node": {"type": "Label2D", "name": "Aviso", "text": "oi", "x": 10, "y": 10}},
                                          {"op": "remove", "scene": "main", "id": "id-que-nao-existe"}], "map": {"theme": "", "enemies": "less", "coins": "same"}}
        p = FakeProvider({"Game Planner": {"title": "x", "kind": "2d", "genre": "platformer", "theme": "forest"}, "Scene Designer": ops})
        ai, _ = self.ai(p, prompt="mude o placar e adicione um aviso", mode="edit")
        res = ai.generate_game(self.pid)
        self.assertEqual(res["mode"], "edit")
        sc2 = self.m.get_scene(self.pid, "main")
        texts = [n.get("text") for n in S.walk(sc2["root"])]
        self.assertIn("Placar novo", texts)
        self.assertIn("Aviso", [n.get("name") for n in S.walk(sc2["root"])])
        self.assertTrue(any("menos enemies" in c for c in res["changes"]))

    def test_code_lint_and_rules(self):
        probs = eai.EngineAI.lint_files([{"path": "scripts/a.js", "content": "GE.behavior('a', {"}, {"path": "data/x.json", "content": "{"}, {"path": "scripts/b.js", "content": "fetch('http://x')"}, {"path": "scripts/c.js", "content": "var a = 1;"}])
        self.assertEqual(sum(1 for p in probs if p.startswith("scripts/a.js")), 1)
        self.assertTrue(any(p.startswith("data/x.json") for p in probs))
        self.assertTrue(any("não permitido" in p for p in probs))
        self.assertFalse(any(p.startswith("scripts/c.js") for p in probs))
        ai, job = self.ai(prompt="faça o inimigo pulsar", body={"files": []})
        res = ai.edit_code(self.pid)
        self.assertTrue(res["files"] and res["files"][0].startswith("scripts/"))
        src = self.m.read_file(self.pid, "game", res["files"][0])["content"]
        self.assertIn("GE.behavior('pulsar'", src)
        self.assertEqual(res["problems"], [])
        # a IA não escreve fora das pastas permitidas
        bad = FakeProvider({"Code Planner": {"files": [{"path": "../../etc/x.js", "action": "create"}, {"path": "scripts/ok.js", "action": "create"}]},
                            "Coder": {"files": [{"path": "scripts/ok.js", "content": "GE.behavior('ok', {});"}, {"path": "scripts/outro.js", "content": "x"}]}})
        ai2, _ = self.ai(bad, prompt="crie ok", body={"files": []})
        r2 = ai2.edit_code(self.pid)
        self.assertEqual(r2["files"], ["scripts/ok.js"])

    def test_asset_sound_script_map_publish_fallbacks(self):
        ai, _ = self.ai(prompt="uma moeda dourada", body={"transparent": True})
        img = ai.make_asset(self.pid)["image"]
        self.assertEqual(img["mime"], "image/svg+xml")
        self.assertIn(b"<svg", base64.b64decode(img["data"]))
        self.assertEqual(img["brief"]["subject"], "coin")
        ai, _ = self.ai(prompt="som de moeda", body={})
        snd = ai.make_sound(self.pid)["sound"]
        self.assertEqual((snd["kind"], snd["mime"]), ("sfx", "audio/wav"))
        self.assertTrue(audio.wav_info(base64.b64decode(snd["data"])))
        ai, _ = self.ai(prompt="música épica de batalha", body={"duration": 8})
        self.assertEqual(ai.make_sound(self.pid)["sound"]["kind"], "music")
        ai, _ = self.ai(prompt="gdd do jogo", body={"action": "generate"})
        self.assertIn("#", ai.write_script(self.pid)["text"])
        ai, _ = self.ai(prompt="", body={"action": "fix", "selection": "ola  ,mundo . isto  e um teste"})
        self.assertEqual(ai.write_script(self.pid)["text"], "Ola,mundo. Isto e um teste")
        self.m.apply_build(self.pid, templates.build("plataforma", "2d", "platformer", "forest", "short"))
        ai, _ = self.ai(prompt="fase de caverna com 6 inimigos e 8 moedas", body={"action": "generate", "save": True})
        res = ai.make_map(self.pid)
        self.assertEqual(res["map"]["kind"], "2d")
        self.assertTrue(res["path"].endswith(".map.json"))
        self.assertEqual(self.m.get_map(self.pid, res["path"])["name"], res["map"]["name"])
        ai, _ = self.ai(prompt="texto de loja", body={})
        pub = ai.plan_publish(self.pid)["publish"]
        self.assertRegex(pub["version"], r"^\d+\.\d+\.\d+$")


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="asta-ge-ex-"))
        self.m = EngineManager(Store(self.tmp))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_platform_exports_a_playable_package(self):
        pid = self.m.create("Super Jogo", "3d", "explore", "forest")["id"]
        self.m.apply_build(pid, templates.build("explore", "3d", "explore", "forest", "short"))
        self.m.write_file(pid, "game", "scripts/x.js", "GE.behavior('x', {});")
        names = {}
        for plat in exporter.PLATFORMS:
            r = exporter.export(self.m, pid, plat, {"version": "2.1.0", "package": "com.teste.superjogo"})
            zf = zipfile.ZipFile(self.m.dir(pid) / "exports" / r["file"])
            names[plat] = set(zf.namelist())
            self.assertIsNone(zf.testzip())
        web = names["web"]
        self.assertTrue({"index.html", "data.js", "engine/ge_core.js", "engine/ge_3d.js", "vendor/three.min.js", "manifest.webmanifest", "sw.js", "game/scripts/x.js"} <= web)
        self.assertFalse(any(n.startswith("game/scenes") for n in web))       # as cenas já vão dentro do data.js
        for plat in ("win", "macos", "linux"):
            self.assertIn("app/index.html", names[plat])
            self.assertIn("package.json", names[plat])
            self.assertIn(".github/workflows/build.yml", names[plat])
        self.assertIn("Jogar.bat", names["win"])
        self.assertIn("Jogar.command", names["macos"])
        self.assertIn("jogar.sh", names["linux"])
        for plat in ("android", "ios"):
            self.assertIn("www/index.html", names[plat])
            self.assertIn("capacitor.config.json", names[plat])
        self.assertIn("build-android.sh", names["android"])
        self.assertIn("build-ios.sh", names["ios"])
        cap = json.loads(zipfile.ZipFile(self.m.dir(pid) / "exports" / exporter.list_exports(self.m, pid)[0]["file"]).read("capacitor.config.json")) if False else None
        z = zipfile.ZipFile(self.m.dir(pid) / "exports" / next(x["file"] for x in exporter.list_exports(self.m, pid) if x["platform"] == "android"))
        self.assertEqual(json.loads(z.read("capacitor.config.json"))["appId"], "com.teste.superjogo")
        zw = zipfile.ZipFile(self.m.dir(pid) / "exports" / next(x["file"] for x in exporter.list_exports(self.m, pid) if x["platform"] == "win"))
        self.assertEqual(json.loads(zw.read("package.json"))["version"], "2.1.0")
        self.assertEqual(exporter.list_exports(self.m, pid)[0]["platform"] in exporter.PLATFORMS, True)
        with self.assertRaises(EngineError):
            exporter.export_path(self.m, pid, "../project.json")

    def test_2d_package_has_no_three(self):
        pid = self.m.create("Plat", "2d", "platformer", "forest")["id"]
        self.m.apply_build(pid, templates.build("x", "2d", "platformer", "", "short"))
        r = exporter.export(self.m, pid, "web", {})
        names = zipfile.ZipFile(self.m.dir(pid) / "exports" / r["file"]).namelist()
        self.assertNotIn("vendor/three.min.js", names)
        self.assertIn("engine/ge_2d.js", names)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="asta-ge-api-"))
        cls.httpd, cls.app = make_server("127.0.0.1", 0, Store(cls.tmp))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.c = Client(cls.httpd.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def job(self, path, body):
        st, r = self.c.json("POST", path, body)
        self.assertEqual(st, 200, r)
        ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        self.assertEqual(ev[-1]["type"], "end")
        return ev

    def test_projects_scenes_files_play_and_export(self):
        st, cat = self.c.json("GET", "/api/engine/catalog")
        self.assertEqual(st, 200)
        self.assertIn("Sprite2D", cat["node_types"])
        st, p = self.c.json("POST", "/api/engine/projects", {"name": "Teste API", "kind": "2.5d"})
        self.assertEqual(st, 201)
        pid = p["id"]
        self.assertEqual(p["genre"], "iso")
        st, full = self.c.json("GET", f"/api/engine/projects/{pid}")
        self.assertEqual(full["scenes"][0], "main")
        # cena
        st, sc = self.c.json("GET", f"/api/engine/projects/{pid}/scenes/main")
        sc["root"]["children"].append({"type": "Label2D", "name": "Oi", "text": "oi"})
        st, saved = self.c.json("PUT", f"/api/engine/projects/{pid}/scenes/main", sc)
        self.assertEqual(st, 200)
        st, bad = self.c.json("PUT", f"/api/engine/projects/{pid}/scenes/main", {"root": 5})
        self.assertEqual(st, 400)
        # arquivos
        st, _ = self.c.json("PUT", f"/api/engine/projects/{pid}/file?area=game&path=scripts/a.js", {"content": "GE.behavior('a', {});"})
        self.assertEqual(st, 200)
        st, f = self.c.json("GET", f"/api/engine/projects/{pid}/file?area=game&path=scripts/a.js")
        self.assertEqual(f["content"], "GE.behavior('a', {});")
        st, _ = self.c.json("GET", f"/api/engine/projects/{pid}/file?area=game&path=../project.json")
        self.assertEqual(st, 400)
        st, _, _ = self.c.req("POST", f"/api/engine/projects/{pid}/upload?area=game&path=assets/images/x.png", raw=b"\x89PNG\r\n\x1a\n" + b"0" * 30)
        self.assertEqual(st, 201)
        st, hd, data = self.c.req("GET", f"/api/engine/projects/{pid}/raw?area=game&path=assets/images/x.png")
        self.assertEqual(st, 200)
        self.assertEqual(hd.get("Content-Type"), "image/png")
        # jogar: HTML isolado (CSP com sandbox), motor e dados
        st, hd, html = self.c.req("GET", f"/api/engine/play/{pid}/index.html")
        self.assertEqual(st, 200)
        self.assertIn("sandbox", hd["Content-Security-Policy"])
        self.assertNotIn("allow-same-origin", hd["Content-Security-Policy"])
        self.assertIn(b"ge_2d.js", html)
        st, hd, js = self.c.req("GET", f"/api/engine/play/{pid}/data.js")
        self.assertTrue(js.startswith(b"window.GE_DATA="))
        self.assertEqual(self.c.req("GET", f"/api/engine/play/{pid}/engine/ge_core.js")[0], 200)
        self.assertEqual(self.c.req("GET", f"/api/engine/play/{pid}/engine/../../server.py")[0], 404)
        self.assertEqual(self.c.req("GET", f"/api/engine/play/{pid}/game/scripts/a.js")[0], 200)
        # exportar
        st, ex = self.c.json("POST", f"/api/engine/projects/{pid}/export", {"platform": "linux"})
        self.assertEqual(st, 200)
        st, hd, zdata = self.c.req("GET", ex["url"])
        self.assertEqual(st, 200)
        self.assertTrue(zipfile.ZipFile(io.BytesIO(zdata)).namelist())
        self.assertEqual(self.c.json("POST", f"/api/engine/projects/{pid}/export", {"platform": "palm"})[0], 400)
        # Origin forjado não escreve
        st, _ = self.c.json("PUT", f"/api/engine/projects/{pid}/scenes/main", sc, headers={"Origin": "http://evil.example"})
        self.assertEqual(st, 403)
        # duplicar e apagar
        st, dup = self.c.json("POST", f"/api/engine/projects/{pid}/duplicate", {})
        self.assertEqual(st, 201)
        self.assertEqual(self.c.json("DELETE", f"/api/engine/projects/{dup['id']}")[0], 200)
        self.assertEqual(self.c.json("GET", f"/api/engine/projects/{dup['id']}")[0], 404)
        self.assertEqual(self.c.json("GET", "/api/engine/projects/ab")[0], 404)

    def test_generate_job_streams_and_map_brush(self):
        st, p = self.c.json("POST", "/api/engine/projects", {"name": "Gen", "kind": "3d", "starter": False})
        pid = p["id"]
        ev = self.job(f"/api/engine/projects/{pid}/generate", {"prompt": "mundo 3D de neve com gemas", "kind": "3d", "mode": "new"})
        kinds = [e["type"] for e in ev]
        self.assertIn("start", kinds)
        self.assertIn("result", kinds)
        self.assertEqual(sum(1 for e in ev if e["type"] == "step" and e["status"] in ("done", "warn")) >= 4, True)
        st, full = self.c.json("GET", f"/api/engine/projects/{pid}")
        self.assertEqual((full["kind"], full["theme"]), ("3d", "snow"))
        path = full["maps"][0]["path"]
        st, out = self.c.json("POST", f"/api/engine/projects/{pid}/map-brush", {"path": path, "op": "raise", "x": 0, "z": 0, "radius": 20, "strength": 1, "save": False})
        self.assertEqual(st, 200)
        self.assertEqual(len(out["heights"]), full["maps"][0]["size"][0] ** 2)
        self.assertEqual(self.c.json("POST", f"/api/engine/projects/{pid}/map-brush", {"path": path, "op": "explodir"})[0], 400)
        self.assertEqual(self.c.json("POST", f"/api/engine/projects/{pid}/generate", {})[0], 400)
        # asset e som por job
        ev = self.job(f"/api/engine/projects/{pid}/asset", {"prompt": "árvore", "transparent": True})
        res = [e for e in ev if e["type"] == "result"][0]["data"]
        self.assertTrue(res["image"]["data"])
        ev = self.job(f"/api/engine/projects/{pid}/sound", {"prompt": "som de pulo", "kind": "sfx"})
        self.assertTrue([e for e in ev if e["type"] == "result"][0]["data"]["sound"]["data"])
        self.assertEqual(self.c.json("GET", "/api/engine/status")[1]["text"]["ai"], False)
        self.assertTrue(self.c.json("GET", "/api/engine/prompts")[1]["prompts"])

    def test_settings_section_and_studio_canvas_links(self):
        st, s = self.c.json("GET", "/api/settings")
        self.assertEqual(s["engine"]["agents"], 1)
        st, p = self.c.json("POST", "/api/engine/projects", {"name": "Links", "kind": "2d"})
        pid = p["id"]
        st, r = self.c.json("POST", f"/api/engine/projects/{pid}/studio-link", {"paths": ["assets/sound/coin.wav", "assets/sound/theme.wav"]})
        self.assertEqual((st, r["added"]), (200, 2))
        st, r = self.c.json("POST", f"/api/engine/projects/{pid}/canvas-link", {"paths": ["assets/sound/coin.wav", "assets/images/player.svg"]})
        self.assertEqual((st, r["added"]), (200, 1))      # SVG não é mídia do Canvas
        self.assertEqual(self.c.json("POST", f"/api/engine/projects/{pid}/studio-link", {"paths": []})[0], 400)
        st, link = self.c.json("POST", f"/api/engine/projects/{pid}/code-link", {})
        self.assertEqual(st, 200)
        self.assertTrue(link["session_id"])
        st, again = self.c.json("POST", f"/api/engine/projects/{pid}/code-link", {})
        self.assertTrue(again["reused"])


if __name__ == "__main__":
    unittest.main()
