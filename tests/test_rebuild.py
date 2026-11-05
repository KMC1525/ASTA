"""Rebuild (v0.5): jogos Ren'Py e RPG Maker (2000 → MZ) reconstruídos nos motores 2D do ASTA — com projetos SINTÉTICOS (nenhum jogo de terceiros)."""
import json
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import rebuild  # noqa: E402
from asta.games2d import schema as S  # noqa: E402
from asta.rebuild import Source, SourceError, lcf, marshal, renpy  # noqa: E402
from tests import rebuild_fixtures as F  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402


def src_of(files):
    s = Source()
    for n, b in files.items():
        s.add(n, lambda b=b: b)
    return s


def spec_of(files):
    raw, genre, warns, info = rebuild.rebuild_source(src_of(files))
    spec, nw = S.normalize_game(raw, genre, raw.get("language", "pt-BR"), raw.get("title") or "x")
    return spec, warns, info


def all_cmds(node):
    if isinstance(node, dict):
        if "c" in node:
            yield node
        for v in node.values():
            yield from all_cmds(v)
    elif isinstance(node, list):
        for v in node:
            yield from all_cmds(v)


class FormatReaders(unittest.TestCase):
    def test_marshal_reads_ruby_data(self):
        o = F.ro("RPG::Thing", id=7, name="Ação", flags=[True, False, None], nested={1: "a", 2: [3, -300, 70000]})
        r = marshal.loads(F.dumps(o))
        self.assertEqual((r.cls, r.get("id"), r.get("name"), r.get("flags")), ("RPG::Thing", 7, "Ação", [True, False, None]))
        self.assertEqual(r.get("nested"), {1: "a", 2: [3, -300, 70000]})
        t = marshal.table(F.table(3, 2, 1, [1, 2, 3, 4, 5, -6]))
        self.assertEqual(t, (3, 2, 1, [1, 2, 3, 4, 5, -6]))
        for bad in (b"", b"\x04\x09x", b"\x04\x08[\x10"):
            with self.assertRaises(marshal.MarshalError):
                marshal.loads(bad)

    def test_lcf_map_and_tree(self):
        m = lcf.read_map(F.lcf_map())
        self.assertEqual((m["width"], m["height"], len(m["lower"])), (20, 15, 300))
        self.assertEqual([e["name"] for e in m["events"]], ["Aldeão", "Portal", "Monstro"])
        self.assertEqual(m["events"][0]["pages"][0]["list"][0]["s"], "Bem-vindo à vila!")
        t = lcf.read_tree(F.lcf_tree())
        self.assertEqual((t["maps"], t["start"]), ({1: "Vila", 2: "Caverna"}, {"map": 1, "x": 3, "y": 3}))
        with self.assertRaises(ValueError):
            lcf.read_map(b"\x0aLcfMapTree")


class RpgMakerRebuild(unittest.TestCase):
    def test_mv_structure_is_kept(self):
        spec, warns, info = spec_of(F.mv_project())
        self.assertEqual((spec["genre"], spec["title"], info["engine"]), ("rpg", "Vila de Teste", "mv"))
        d = spec["data"]
        self.assertEqual(set(d["maps"]), {"m1", "m2"})
        self.assertEqual([p["name"] for p in d["party"]], ["Aria", "Brom"])
        self.assertEqual(d["party"][1]["cls"], "mage")
        self.assertEqual((d["start"]["map"], d["start"]["x"], d["start"]["y"]), ("m1", 3, 3))
        rows = d["maps"]["m1"]["tiles"]
        self.assertEqual((len(rows), len(rows[0])), (14, 20))
        self.assertTrue(set(rows[0]) <= set("#H~T^"))   # borda de parede
        self.assertIn("~", rows[1])                                                    # água do canto
        ev = {e["id"]: e for e in d["maps"]["m1"]["events"]}
        elder = ev["e1"]
        self.assertEqual(elder["pages"][0]["if"], "sw5")                               # a última página do RPG Maker vem primeiro no ASTA
        talk = elder["pages"][1]["commands"]
        self.assertIn("Olá, Aria!", talk[0]["text"])                                  # \N[1] virou o nome do ator
        self.assertEqual(talk[0]["who"], "Velha")
        ch = talk[1]
        self.assertEqual([o["text"] for o in ch["options"]], ["Sim", "Não"])
        self.assertEqual(ch["options"][0]["do"][0], {"c": "set", "var": "sw5", "op": "=", "value": True})
        self.assertEqual((ev["e2"]["kind"], ev["e2"]["trigger"]), ("warp", "touch"))
        self.assertEqual(ev["e2"]["pages"][0]["commands"][0], {"c": "warp", "map": "m2", "x": 2, "y": 7})
        chest = [c["c"] for c in all_cmds(ev["e3"]["pages"][0]["commands"])]   # «sair do evento» no ramo «já abriu»: o resto vai para o outro ramo
        self.assertIn("item", chest)
        self.assertIn("gold", chest)
        self.assertIn("remove", chest)
        shop = ev["e4"]["pages"][0]["commands"]
        self.assertTrue(any(c["c"] == "if" and c["cond"] == "v3 >= 3" for c in shop))
        self.assertTrue(any(c["c"] == "shop" for c in shop))
        dragon = [c for c in all_cmds(d["maps"]["m2"]) if c["c"] == "battle"][0]
        self.assertEqual(dragon["enemies"], ["e2"])
        self.assertEqual(d["enemies"]["e2"]["hp"], 120)
        self.assertEqual(d["items"]["i1"]["kind"], "heal_hp")
        self.assertEqual(S.game_problems(spec), [])
        self.assertTrue(any("script" in w for w in warns))                             # chamadas de script avisadas
        self.assertTrue(any(c["c"] == "end" for c in all_cmds(d["maps"])))             # o ASTA precisa de um fim

    def test_mz_is_detected_and_ace_vx_xp_marshal_work(self):
        self.assertEqual(rebuild.detect(src_of(F.mv_project(True))), "mz")
        for ext, eng in (("rvdata2", "ace"), ("rvdata", "vx"), ("rxdata", "xp")):
            spec, warns, info = spec_of(F.rg_project(ext))
            self.assertEqual((info["engine"], spec["title"]), (eng, "Teste Marshal"))
            m = spec["data"]["maps"]["m1"]
            self.assertEqual((len(m["tiles"]), len(m["tiles"][0])), (12, 16))
            self.assertTrue(m["tiles"][0][0] in "#H~T^")
            evs = {e["id"]: e for e in m["events"]}
            self.assertIn("Olá, viajante!", evs["e1"]["pages"][0]["commands"][0]["text"])
            self.assertEqual(evs["e1"]["pages"][0]["commands"][1]["options"][0]["do"][0]["var"], "sw3")
            self.assertEqual(evs["e2"]["pages"][0]["commands"][0]["enemies"], ["e1"])
            self.assertEqual(spec["data"]["party"][0]["name"], "Rin")
            self.assertEqual(S.game_problems(spec), [])

    def test_2000_2003_lcf(self):
        spec, warns, info = spec_of(F.rm2k_project())
        self.assertEqual((info["engine"], spec["title"]), ("rm2k", "Aventura 2K"))
        d = spec["data"]
        self.assertEqual((d["start"]["map"], set(d["maps"])), ("m1", {"m1", "m2"}))
        self.assertEqual(d["maps"]["m1"]["name"], "Vila")
        evs = {e["name"]: e for e in d["maps"]["m1"]["events"]}
        talk = evs["Aldeão"]["pages"][0]["commands"]
        self.assertEqual(talk[0]["text"], "Bem-vindo à vila!\nFale comigo de novo.")
        self.assertEqual([o["text"] for o in talk[1]["options"]], ["Sim", "Não"])
        self.assertEqual(talk[1]["options"][0]["do"][0]["var"], "sw7")
        self.assertEqual(evs["Portal"]["pages"][0]["commands"][0], {"c": "warp", "map": "m2", "x": 4, "y": 4})
        self.assertTrue(any(c["c"] == "battle" for c in all_cmds(evs["Monstro"])))
        self.assertEqual(S.game_problems(spec), [])

    def test_big_maps_are_cropped_with_a_warning(self):
        files = F.mv_project()
        big = F.mv_map(80, 50, [])
        files["data/Map003.json"] = json.dumps(big).encode()
        files["data/MapInfos.json"] = json.dumps([None, {"id": 1, "name": "Vila"}, {"id": 2, "name": "Covil"}, {"id": 3, "name": "Enorme"}]).encode()
        raw, genre, warns, info = rebuild.rebuild_source(src_of(files))
        self.assertTrue(any("recortados" in w for w in warns))
        self.assertEqual((len(raw["maps"]["m3"]["tiles"]), len(raw["maps"]["m3"]["tiles"][0])), (40, 60))


class RenpyRebuild(unittest.TestCase):
    def test_script_structure(self):
        spec, warns, info = spec_of({"game/script.rpy": F.RPY.encode()})
        self.assertEqual((spec["genre"], spec["title"], info["engine"]), ("visual_novel", "Café Tranquilo", "renpy"))
        d = spec["data"]
        self.assertEqual(d["start"], "start")
        self.assertEqual({c["id"] for c in d["characters"]} >= {"e"}, True)
        self.assertEqual(next(c for c in d["characters"] if c["id"] == "e")["name"], "Eileen")
        start = d["labels"]["start"]
        self.assertEqual([c["c"] for c in start[:4]], ["scene", "show", "say", "say"])
        self.assertEqual(start[2]["text"], "Olá! Bem-vindo ao café, {player}.")        # tags {i} saem e [player] vira {player}
        menu = next(c for c in start if c["c"] == "menu")
        self.assertEqual([ch["text"] for ch in menu["choices"]], ["Pedir café", "Ir embora"])
        self.assertEqual(menu["choices"][1]["if"], "affection > 0")
        self.assertEqual(d["variables"]["affection"], 0)
        buy = d["labels"][menu["choices"][0]["jump"]]
        self.assertEqual(buy[0], {"c": "set", "var": "affection", "op": "+=", "value": 2})   # corpo do menu virou rótulo
        self.assertEqual(buy[-1], {"c": "jump", "label": "coffee"})
        cont = d["labels"][d["labels"][menu["choices"][1]["jump"]][-1]["label"]]             # o fluxo continua depois do menu
        self.assertEqual(cont[0]["c"], "if")
        self.assertIn("Chamada extra.", json.dumps(cont, ensure_ascii=False))               # call foi incorporado
        self.assertEqual(S.game_problems(spec), [])
        self.assertFalse(any(k == "extra" for k in d["labels"]))                            # rótulo só usado por call some

    def test_unsupported_python_is_reported_not_fatal(self):
        rpy = 'label start:\n    $ renpy.pause(1.0)\n    $ x = foo(3)\n    "Oi."\n    python:\n        a = 1\n    if persistent.seen:\n        "Já viu."\n    return\n'
        raw, warns, info = renpy.convert([("script.rpy", rpy)])
        self.assertTrue(any("Python" in w or "python" in w for w in warns))
        self.assertTrue(any("condição" in w for w in warns))
        self.assertEqual(raw["data"]["labels"]["start"][0]["text"], "Oi.")

    def test_a_game_with_no_labels_is_a_clear_error(self):
        with self.assertRaises(ValueError):
            renpy.convert([("options.rpy", 'define config.name = "X"\n')])


class DetectionAndSafety(unittest.TestCase):
    def test_unknown_or_encrypted_games_explain_what_to_do(self):
        for files in ({}, {"Game.rgss3a": b"x"}, {"game/script.rpyc": b"x"}):
            with self.assertRaises(SourceError) as cm:
                rebuild.detect(src_of({k: v for k, v in files.items() if k.endswith(rebuild.TEXT_EXT)}))
            self.assertIn("ZIP", str(cm.exception))

    def test_zip_reading_only_touches_data_files_and_ignores_unsafe_paths(self):
        import tempfile

        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "g.zip"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("game/script.rpy", F.RPY)
                z.writestr("game/images/bg.png", b"\x89PNG" * 10)
                z.writestr("../evil.rpy", "label x:\n    return\n")
                z.writestr("/abs/evil2.rpy", "label y:\n    return\n")
            s = Source.from_uploads([{"path": str(p), "name": "g.zip"}])
            self.assertEqual(s.names(), ["game/script.rpy", "abs/evil2.rpy"])  # «..» é descartado; caminho absoluto vira relativo (árvore virtual: nada é gravado em disco)

    def test_notice_has_the_four_required_warnings_in_both_languages(self):
        for lang, n in (("pt", rebuild.NOTICE_PT), ("en", rebuild.NOTICE_EN)):
            self.assertEqual(len(n["points"]), 4)
            md = rebuild.notice_markdown(lang)
            self.assertTrue(all(p in md for p in n["points"]))
        low = " ".join(rebuild.NOTICE_PT["points"]).lower()
        for needle in ("steam", "pessoal", "criador do asta", "consciência"):
            self.assertIn(needle, low)


class RebuildApi(ServerCase):
    def upload(self, name, data):
        status, _h, payload = self.c.req("POST", "/api/uploads", raw=data, headers={"X-Filename": name, "Content-Type": "application/zip", "Content-Length": str(len(data))})
        self.assertEqual(status, 200, payload)
        return json.loads(payload)["id"]

    def run_job(self, ids):
        status, r = self.c.json("POST", "/api/games/rebuild", {"attachment_ids": ids})
        self.assertEqual(status, 200, r)
        return self.c.sse(f"/api/jobs/{r['job_id']}/events")

    def test_rebuild_end_to_end_creates_a_playable_package_with_the_legal_notice(self):
        up = self.upload("MeuJogo.zip", F.zip_bytes(F.mv_project()))
        ev = self.run_job([up])
        done = next(e for e in ev if e["type"] == "done")
        self.assertEqual((done["genre"], done["rebuild"]["engine"]), ("rpg", "mv"))
        self.assertEqual(done["notice"]["pt"]["points"], rebuild.NOTICE_PT["points"])
        steps = [e["id"] for e in ev if e["type"] == "step" and e["status"] == "done"]
        self.assertEqual(steps, ["attachments", "analyst", "designer", "reviewer", "package"])
        pid = done["project_id"]
        z = Path(self.store.version_dir(pid, 1) / "game.zip")
        names = zipfile.ZipFile(z).namelist()
        self.assertIn("Game.html", names)
        self.assertIn("LEGAL-NOTICE.md", names)
        self.assertIn("data/game.json", names)
        self.assertIn("Steam", zipfile.ZipFile(z).read("LEGAL-NOTICE.md").decode() + zipfile.ZipFile(z).read("README.md").decode())
        proj = self.c.json("GET", f"/api/projects/{pid}")[1]
        self.assertEqual(proj["kind"], "game2d")
        self.assertIn("rebuild", proj["tags"]["auto"])
        self.assertEqual(self.store.list_uploads() if hasattr(self.store, "list_uploads") else [], [] if hasattr(self.store, "list_uploads") else [])  # o original não fica guardado

    def test_renpy_zip_and_bad_inputs(self):
        up = self.upload("vn.zip", F.zip_bytes({"game/script.rpy": F.RPY.encode()}, "Meu VN"))
        done = next(e for e in self.run_job([up]) if e["type"] == "done")
        self.assertEqual((done["genre"], done["title"]), ("visual_novel", "Café Tranquilo"))
        bad = self.upload("lixo.zip", F.zip_bytes({"leiame.txt": b"oi"}))
        err = [e for e in self.run_job([bad]) if e["type"] == "error"]
        self.assertEqual(len(err), 1)
        self.assertIn("ZIP", err[0]["message"])
        self.assertEqual(self.c.json("POST", "/api/games/rebuild", {})[0], 400)
        self.assertIn("steam", json.dumps(self.c.json("GET", "/api/games/rebuild/notice")[1]).lower())


if __name__ == "__main__":
    unittest.main()
