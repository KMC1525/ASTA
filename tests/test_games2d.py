"""Jogos 2D: validadores, geradores offline, pipeline/API, pacote, e a lógica dos motores (Node)."""
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.agents import rulebased_games as rg  # noqa: E402
from asta.games2d import GENRES, schema as S  # noqa: E402
from tests.test_core import TmpCase  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "tests" / "js"
HAS_NODE = bool(shutil.which("node"))


def make(prompt, genre="auto", length="medium"):
    brief = rg.analyst({"prompt": prompt, "genre": genre, "length": length})
    spec, warns = S.normalize_game(rg.designer({"brief": brief}), brief["genre"], brief["language"], brief["title"])
    return brief, spec, warns


class SchemaTests(unittest.TestCase):
    def test_conditions_are_validated_without_eval(self):
        ok = S.parse_cond("afeto >= 3 and not visto or (nome == 'Ana')")
        self.assertEqual(ok[1], ["afeto", "visto", "nome"])
        for bad in ("", "1 +", "and x", "x y", "__import__('os')", "a == ", "x = 1", "(((x)", "x" * 300):
            self.assertIsNone(S.parse_cond(bad), bad)

    def test_vn_repairs_broken_references_and_terminates_every_label(self):
        spec, warns = S.normalize_game({"title": "T", "data": {"labels": {
            "start": [{"c": "say", "who": "Mira", "text": "Oi {player}"}, {"c": "show", "char": "joao", "expr": "furious", "at": "middle"},
                      {"c": "menu", "choices": [{"text": "A", "jump": "a", "set": [{"var": "Afeto Total", "op": "+=", "value": 1}]}, {"text": "B", "jump": "nao_existe"}]},
                      {"c": "if", "cond": "afeto_total >= 1", "then": [{"c": "jump", "label": "a"}], "else": [{"c": "jump", "label": "ghost"}]}],
            "a": [{"c": "say", "text": "fim"}]}}}, "visual_novel")
        d = spec["data"]
        self.assertEqual(set(d["labels"]), {"start", "a"})
        self.assertTrue(S._terminal(d["labels"]["a"]) and S._terminal(d["labels"]["start"]))
        menu = next(s for s in d["labels"]["start"] if s["c"] == "menu")
        self.assertEqual([c["jump"] for c in menu["choices"]], ["a", ""])  # destino inexistente descartado
        self.assertEqual(d["labels"]["start"][1]["expr"], "neutral")
        self.assertEqual(d["labels"]["start"][1]["at"], "center")
        self.assertIn("mira", [c["id"] for c in d["characters"]])  # personagem citado vira card
        self.assertIn("afeto_total", d["variables"])
        self.assertEqual(S.game_problems(spec), [])  # rótulos sem final ganham `end`; há menu e todos os rótulos são alcançáveis
        self.assertFalse(S.is_trivial(spec) and False)

    def test_rpg_references_and_positions_are_fixed(self):
        raw = {"party": [{"name": "Aria", "cls": "mage", "skills": ["fogo", "x"]}], "skills": {"fogo": {"name": "Fogo"}}, "items": {"potion": {"name": "P"}},
               "enemies": {"slime": {"name": "S"}}, "start": {"map": "ghost", "x": 99, "y": 99},
               "maps": {"vila": {"tiles": ["####", "#..#"], "events": [
                   {"id": "n", "kind": "npc", "x": 500, "y": -4, "commands": [{"c": "item", "id": "x"}, {"c": "warp", "map": "ghost"}, {"c": "battle", "enemies": ["slime", "ghost"]}, {"c": "end"}]}]}}}
        spec, warns = S.normalize_game(raw, "rpg")
        d = spec["data"]
        m = d["maps"]["vila"]
        self.assertGreaterEqual(len(m["tiles"]), 10)
        self.assertEqual(len({len(r) for r in m["tiles"]}), 1)  # linhas do mesmo tamanho
        self.assertEqual(d["start"]["map"], "vila")
        self.assertTrue(S._walkable(m["tiles"], d["start"]["x"], d["start"]["y"]))
        self.assertEqual(d["party"][0]["skills"], ["fogo"])
        cmds = m["events"][0]["pages"][0]["commands"]
        self.assertEqual([c["c"] for c in cmds], ["battle", "end"])  # item/warp inválidos removidos
        self.assertEqual(cmds[0]["enemies"], ["slime"])
        self.assertTrue(warns)

    def test_platformer_guarantees_start_goal_ground_and_checkpoint_on_floor(self):
        spec, _ = S.normalize_game({"data": {"levels": [{"tiles": ["....", "...."]}, {"tiles": ["P" + "." * 40, "." * 41, "...K" + "." * 37, "#" * 41]}]}}, "platformer")
        for lv in spec["data"]["levels"]:
            t = lv["tiles"]
            self.assertEqual(sum(r.count("P") for r in t), 1)
            self.assertEqual(sum(r.count("F") for r in t), 1)
            self.assertTrue(any("#" in r for r in t))
            self.assertEqual(len({len(r) for r in t}), 1)
        t = spec["data"]["levels"][1]["tiles"]
        kx = next(r.index("K") for r in t if "K" in r)
        ky = next(i for i, r in enumerate(t) if "K" in r)
        self.assertEqual(t[ky + 1][kx], "#")  # checkpoint sempre apoiado no chão
        # K sobre o vazio é removido (renascer no vazio = morte eterna)
        spec, _ = S.normalize_game({"data": {"levels": [{"tiles": ["." * 40] * 6 + ["...K" + "." * 36] + ["#" * 3 + "." * 37]}]}}, "platformer")
        self.assertEqual(sum(r.count("K") for r in spec["data"]["levels"][0]["tiles"]), 0)

    def test_trivial_games_are_detected_for_every_genre(self):
        for genre in GENRES:
            spec, _ = S.normalize_game({"data": {}}, genre)
            self.assertTrue(S.is_trivial(spec), genre)
        for pr, genre in (("romance", "visual_novel"), ("rpg", "rpg"), ("plataforma", "platformer"), ("nave", "side_scroller"), ("point and click", "point_and_click")):
            self.assertFalse(S.is_trivial(make(pr, genre, "short")[1]), genre)

    def test_side_scroller_and_point_and_click_defaults(self):
        spec, _ = S.normalize_game({"data": {"stages": [{"waves": [{"enemy": "ghost"}, {"enemy": "drone", "count": 99}], "boss": {"hp": 1}}]}}, "side_scroller")
        st = spec["data"]["stages"][0]
        self.assertEqual(len(st["waves"]), 1)
        self.assertEqual(st["waves"][0]["count"], 12)
        self.assertEqual(st["boss"]["hp"], 5)
        spec, w = S.normalize_game({"data": {"scenes": {"sala": {"hotspots": [{"name": "Porta", "x": 0.95, "w": 0.5, "use": [{"c": "goto", "scene": "nada"}, {"c": "say", "text": "ok"}]}]}}}}, "point_and_click")
        h = spec["data"]["scenes"]["sala"]["hotspots"][0]
        self.assertLessEqual(h["x"] + h["w"], 1.0)
        self.assertEqual([c["c"] for c in h["use"]], ["say"])
        with self.assertRaises(ValueError):
            S.normalize_game({}, "tetris")


class GeneratorTests(unittest.TestCase):
    PROMPTS = ["Um romance no café com Luna e Theo", "rpg de masmorra com dragão", "plataforma na floresta", "jogo de nave shooter no espaço",
               "point and click escape room", "corrida infinita runner", "a cozy visual novel at school", "magic RPG adventure"]

    def test_every_genre_and_length_is_valid_and_playable(self):
        seen = set()
        for pr in self.PROMPTS:
            for length in S.LENGTHS:
                brief, spec, warns = make(pr, "auto", length)
                self.assertEqual(warns, [], (pr, length))
                self.assertEqual(S.game_problems(spec), [], (pr, length, spec["genre"]))
                self.assertIn(spec["genre"], GENRES)
                seen.add(spec["genre"])
        self.assertEqual(seen, set(GENRES))

    def test_genre_detection_and_explicit_choice(self):
        self.assertEqual(rg.analyst({"prompt": "um rpg com dragão"})["genre"], "rpg")
        self.assertEqual(rg.analyst({"prompt": "Um RPG", "genre": "platformer"})["genre"], "platformer")
        self.assertEqual(rg.analyst({"prompt": "corrida infinita"})["mode"], "runner")
        self.assertEqual(rg.analyst({"prompt": "Luna e Theo no café"})["names"], [])  # sem gatilho de nome → nenhum
        self.assertEqual(rg.analyst({"prompt": "romance com personagens chamados Luna e Theo"})["names"], ["Luna", "Theo"])
        self.assertEqual(rg.analyst({"prompt": "my game"})["language"], "en")

    def test_vn_story_has_branches_and_three_endings(self):
        _, spec, _ = make("romance no café", "visual_novel", "long")
        d = spec["data"]
        ends = {s["title"] for stmts in d["labels"].values() for s in stmts if s["c"] == "end"}
        self.assertGreaterEqual(len(ends), 3)
        self.assertGreaterEqual(sum(1 for stmts in d["labels"].values() for s in stmts if s["c"] == "menu"), 3)
        self.assertTrue(any(s["c"] == "input" for s in d["labels"]["start"]))

    def test_rpg_is_winnable_by_design(self):
        _, spec, _ = make("rpg", "rpg", "short")
        d = spec["data"]
        self.assertEqual({"village", "forest", "cave"}, set(d["maps"]))
        boss = next(e for e in d["maps"]["cave"]["events"] if e["id"] == "boss")
        battle = next(c for p in boss["pages"] for c in p["commands"] if c["c"] == "battle")
        self.assertTrue(battle["boss"] and any(c["c"] == "end" for c in battle["win"]))
        self.assertTrue(d["enemies"]["boss"]["boss"])
        # todos os warps têm volta
        for mid, m in d["maps"].items():
            for e in m["events"]:
                if e["kind"] == "warp":
                    tgt = e["pages"][0]["commands"][0]["map"]
                    self.assertTrue(any(w["kind"] == "warp" and w["pages"][0]["commands"][0]["map"] == mid for w in d["maps"][tgt]["events"]), (mid, tgt))


class PipelineApiTests(ServerCase):
    def gen(self, body):
        status, r = self.c.json("POST", "/api/games/generate", body)
        self.assertEqual(status, 200, r)
        return self.c.sse(f"/api/jobs/{r['job_id']}/events")

    def test_genres_endpoint_and_validation(self):
        status, genres = self.c.json("GET", "/api/games/genres")
        self.assertEqual([g["id"] for g in genres], list(GENRES))
        self.assertEqual(self.c.json("POST", "/api/games/generate", {"prompt": "  "})[0], 400)

    def test_generate_every_genre_zip_play_save_update_rebuild(self):
        cases = {"visual_novel": "romance no café", "rpg": "rpg com dragão", "platformer": "plataforma", "side_scroller": "nave shooter", "point_and_click": "point and click"}
        ids = {}
        for genre, prompt in cases.items():
            ev = self.gen({"prompt": prompt, "genre": genre, "length": "short"})
            steps = [e["id"] for e in ev if e["type"] == "step" and e["status"] in ("done", "skipped", "warn")]
            for sid in ("attachments", "analyst", "designer", "reviewer", "package"):
                self.assertIn(sid, steps, genre)
            done = next(e for e in ev if e["type"] == "done")
            self.assertEqual(done["genre"], genre)
            ids[genre] = done["project_id"]
            # biblioteca: o jogo aparece com kind/genre; mundos 3D não são afetados
            proj = self.c.json("GET", f"/api/projects/{done['project_id']}")[1]
            self.assertEqual((proj["kind"], proj["genre"]), ("game2d", genre))
            self.assertEqual(proj["game"]["genre"], genre)
            zbytes = self.c.req("GET", f"/api/projects/{done['project_id']}/download")[2]
            z = zipfile.ZipFile(io.BytesIO(zbytes))
            names = set(z.namelist())
            engine = {"visual_novel": "vn.js", "rpg": "rpg.js", "platformer": "platformer.js", "side_scroller": "sidescroller.js", "point_and_click": "adventure.js"}[genre]
            for must in ("Game.html", "README.md", "CHANGELOG.md", "code/common.js", f"code/{engine}", "code/main.js", "code/config.js", "data/game.js", "data/game.json", "ui/theme.css", "prompts/prompt.md"):
                self.assertIn(must, names, (genre, must))
            self.assertFalse(any(n.startswith("code/") and n.endswith(".js") and n.split("/")[1] in {"vn.js", "rpg.js", "platformer.js", "sidescroller.js", "adventure.js"} - {engine} for n in names))  # só o motor do gênero
            html = z.read("Game.html").decode()
            import re
            for r in re.findall(r'(?:src|href)="([^"]+)"', html):
                self.assertIn(r, names, r)
            self.assertTrue(z.read("data/game.js").decode().startswith("window.ASTA_GAME="))
            self.assertEqual(json.loads(z.read("data/game.json"))["genre"], genre)
        kinds = {p["id"]: p["kind"] for p in self.c.json("GET", "/api/projects")[1]}
        self.assertTrue(all(kinds[i] == "game2d" for i in ids.values()))
        self.assertTrue(set(self.c.json("GET", "/api/projects?kind=game2d")[1][0]) >= {"id", "genre", "kind"})
        self.assertEqual({p["kind"] for p in self.c.json("GET", "/api/projects?kind=world")[1]} & {"game2d"}, set())

        pid = ids["rpg"]
        # hospedado: HTML, dados e arquivos do jogo; nada fora das pastas permitidas
        self.assertIn(b'code/rpg.js', self.c.req("GET", f"/play/{pid}/")[2])
        self.assertIn(b"ASTA_GAME", self.c.req("GET", f"/play/{pid}/data/game.js")[2])
        self.assertEqual(self.c.req("GET", f"/play/{pid}/prompts/prompt.md")[0], 404)
        self.assertEqual(self.c.req("GET", f"/play/{pid}/data/..%2f..%2fproject.json")[0], 404)
        # salvamento persistente (mesma API dos mundos 3D)
        self.assertEqual(self.c.json("PUT", f"/api/play/{pid}/save", {"rpg_auto": {"map": "forest"}})[0], 200)
        self.assertEqual(self.c.json("GET", f"/api/play/{pid}/save")[1]["rpg_auto"]["map"], "forest")
        # atualização por IA: mesmo gênero (mesmo que o pedido fale de outro), v2 no changelog
        ev = self.gen({"prompt": "adicione mais inimigos; agora com ar de plataforma", "project_id": pid, "genre": "platformer"})
        done = next(e for e in ev if e["type"] == "done")
        self.assertEqual((done["version"], done["genre"]), (2, "rpg"))
        z2 = zipfile.ZipFile(io.BytesIO(self.c.req("GET", f"/api/projects/{pid}/download")[2]))
        self.assertIn("v2", z2.read("CHANGELOG.md").decode())
        self.assertEqual(self.c.req("GET", f"/play/{pid}/v1/Game.html")[0], 200)
        # rebuild com o motor atual → v3; edição "3D" é recusada para jogos
        self.assertEqual(self.c.json("POST", f"/api/projects/{pid}/rebuild")[1]["current"], 3)
        self.assertEqual(self.c.json("POST", f"/api/projects/{pid}/edit", {"title": "x"})[0], 400)
        # projeto de jogo não é aceito como base de um mundo 3D e vice-versa
        ev = self.c.sse(f"/api/jobs/{self.c.json('POST', '/api/generate', {'prompt': 'x', 'project_id': pid})[1]['job_id']}/events")
        self.assertEqual([e for e in ev if e["type"] == "error"][0]["kind"], "validation")
        self.assertEqual(self.c.json("DELETE", f"/api/projects/{pid}")[0], 200)

    def test_pipeline_survives_junk_model_output(self):
        from tests.helpers import MockProviderServer

        with MockProviderServer() as mock:
            self.c.json("PUT", "/api/settings", {"providers": {"custom": {"base_url": mock.url + "/v1", "model": "m", "api_key": "k"}}, "active": {"generation": "custom"}})
            try:
                for genre in ("visual_novel", "platformer"):
                    ev = self.gen({"prompt": "um jogo qualquer", "genre": genre, "length": "short"})
                    done = [e for e in ev if e["type"] == "done"]
                    self.assertTrue(done, ev[-3:])
                    self.assertTrue(done[0]["warnings"])  # agentes usaram o gerador de regras
                    game = self.c.json("GET", f"/api/projects/{done[0]['project_id']}")[1]["game"]
                    self.assertEqual(S.game_problems(game), [])
                self.c.json("PUT", "/api/settings", {"providers": {"custom": {"model": "bad-key"}}})
                n = len(self.c.json("GET", "/api/projects")[1])
                ev = self.gen({"prompt": "outro", "genre": "rpg"})
                self.assertEqual([e for e in ev if e["type"] == "error"][0]["kind"], "provider")
                self.assertEqual(len(self.c.json("GET", "/api/projects")[1]), n)
            finally:
                self.c.json("PUT", "/api/settings", {"active": {"generation": "demo"}, "providers": {"custom": {"api_key": None}}})

    def test_attachments_feed_the_game(self):
        status, up = self.c.json("POST", "/api/uploads", raw="A cafeteria da Dona Nina fica no porto.".encode(), headers={"X-Filename": "lore.txt"})
        ev = self.gen({"prompt": "visual novel", "genre": "visual_novel", "attachment_ids": [up["id"]], "length": "short"})
        done = next(e for e in ev if e["type"] == "done")
        zbytes = self.c.req("GET", f"/api/projects/{done['project_id']}/download")[2]
        self.assertIn("Dona Nina", zipfile.ZipFile(io.BytesIO(zbytes)).read("prompts/attachments.md").decode())


@unittest.skipUnless(HAS_NODE, "Node.js não instalado")
class RuntimeLogicTests(TmpCase):
    def node(self, script, *args, timeout=180):
        r = subprocess.run(["node", str(JS / script), *map(str, args)], capture_output=True, text=True, timeout=timeout)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_conditions_themes_and_rpg_math_match_python(self):
        cases = [["afeto >= 3 and not visto", {"afeto": 4, "visto": False}], ["afeto >= 3 and not visto", {"afeto": 4, "visto": True}],
                 ["a == 'x' or (b < 2)", {"a": "y", "b": 1}], ["a == 'x' or (b < 2)", {"a": "y", "b": 5}], ["nome == \"Ana\"", {"nome": "Ana"}],
                 ["true", {}], ["false or x", {"x": 1}], ["not (a and b)", {"a": 1, "b": 0}], ["a or b and c", {"a": 0, "b": 1, "c": 0}], ["", {}], ["desconhecida", {}]]
        out = self.node("common_parity.js", json.dumps(cases))
        self.assertEqual(out["cond"], [True, False, True, False, True, True, True, True, False, True, False])
        for expr, _ in cases:
            if expr:
                self.assertIsNotNone(S.parse_cond(expr), expr)  # o que o JS executa, o Python valida
        self.assertEqual(out["themes"], list(S.THEMES))  # mesmos temas nos dois lados
        self.assertEqual(out["fmt"], "Oi Ana, {x}")
        self.assertEqual(out["levels"], [2, 3, 4])
        self.assertEqual(out["dmg"], [9, 5, 1])
        self.assertEqual(out["flee"], [0.5, 0.0])

    def test_visual_novel_random_playthroughs_end_and_restore(self):
        for length in ("short", "long"):
            _, spec, _ = make("romance no café", "visual_novel", length)
            f = self.tmp / f"vn-{length}.json"
            f.write_text(json.dumps(spec), "utf-8")
            out = self.node("vn_playthrough.js", f)
            self.assertEqual(out["bad"], [], length)
            self.assertGreaterEqual(len(out["endings"]), 3, out)

    def test_generated_platformer_levels_are_completable_by_a_bot(self):
        specs = []
        for i, pr in enumerate(["plataforma floresta", "a forest platformer", "platformer castle", "plataforma deserto", "platformer cave", "plataforma neve"]):
            for length in ("short", "medium"):
                specs.append(make(pr + f" {i}", "platformer", length)[1])
        f = self.tmp / "plat.json"
        f.write_text(json.dumps(specs), "utf-8")
        out = self.node("plat_bot.js", f, timeout=420)
        self.assertEqual(out["respawnOverVoid"], 0)
        self.assertEqual(out["failed"], [], out)

    def test_all_runtime2d_js_parse(self):
        files = sorted((ROOT / "asta" / "runtime2d").glob("*.js"))
        self.assertGreaterEqual(len(files), 7)
        for f in files:
            r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, f"{f.name}: {r.stderr}")


if __name__ == "__main__":
    unittest.main()
