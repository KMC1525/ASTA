"""v0.17.2 — «@imagem» nos prompts do Canvas: apelidos, reescrita do prompt, imagens como referência (imagem e vídeo), hash e rota."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.canvas import mentions as M  # noqa: E402
from asta.canvas import procedural as proc  # noqa: E402
from asta.canvas.engine import CanvasEngine  # noqa: E402
from asta.canvas.media import DemoMedia  # noqa: E402
from asta.studio import tools  # noqa: E402
from tests.test_canvas import edge, node  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402
from tests.test_v017_canvas import Base  # noqa: E402


def asset(i, name, created, kind="image"):
    return {"id": i, "kind": kind, "name": name, "file": f"{i}.png", "created": created, "mime": "image/png"}


class SlugTests(unittest.TestCase):
    def test_slugs_drop_extension_accents_and_symbols(self):
        self.assertEqual([M.slug(x) for x in ("Foto Perfil.png", "fnaf-1-office.JPG", "Ação & Reação!!.webp", "  ", "__.png", "kaua22")], ["foto-perfil", "fnaf-1-office", "acao-reacao", "imagem", "imagem", "kaua22"])

    def test_repeated_names_get_numbers_and_the_oldest_keeps_the_simple_slug(self):
        cv = {"assets": [asset("b", "gato.png", "2026-02"), asset("a", "Gato.jpg", "2026-01"), asset("c", "gato.png", "2026-03"), asset("v", "clip.mp4", "2026-01", "video")]}
        t = M.table(cv)
        self.assertEqual([(m["id"], m["slug"]) for m in t], [("c", "gato-3"), ("b", "gato-2"), ("a", "gato")])      # só imagens, da mais nova para a mais antiga
        self.assertEqual(len({m["slug"] for m in t}), 3)

    def test_resolve_rewrites_orders_and_reports_unknowns(self):
        cv = {"assets": [asset("a", "fnaf-1-office.png", "1"), asset("b", "foto-perfil.png", "2")]}
        out, ids, missing = M.resolve(cv, "thumb com fundo @fnaf-1-office e o jovem @Foto-Perfil, de novo @fnaf-1-office, e @fantasma; mail a@b.com @@x")
        self.assertEqual(ids, ["a", "b"])
        self.assertEqual(missing, ["fantasma"])
        self.assertIn("fnaf-1-office (reference image 1)", out)
        self.assertIn("Foto-Perfil (reference image 2)", out)
        self.assertIn("@fantasma", out)
        self.assertIn("a@b.com", out)
        self.assertEqual(M.resolve(cv, "sem menção")[0], "sem menção")
        self.assertEqual(M.resolve(cv, "pelo id @b")[1], ["b"])
        many = {"assets": [asset(f"i{k}", f"img{k}.png", str(k)) for k in range(9)]}
        self.assertEqual(len(M.resolve(many, " ".join(f"@img{k}" for k in range(9)))[1]), M.MAX_REFS)


class EngineMentionTests(Base):
    def setUp(self):
        super().setUp()
        self.c = self.cs.create("m")
        self.a = self.cs.add_asset(self.c["id"], proc.image("escritorio", "64x64", 1), "png", "image", name="fnaf-1-office.png", mime="image/png", w=64, h=64)
        self.b = self.cs.add_asset(self.c["id"], proc.image("perfil", "64x64", 2), "png", "image", name="foto-perfil.png", mime="image/png", w=64, h=64)

    def build(self, prompt, extra_nodes=(), edges=()):
        return self.cs.save_layout(self.c["id"], {"nodes": [node("image", nid="img", prompt=prompt), *extra_nodes], "edges": list(edges)})

    def run_image(self):
        seen = {}
        orig = DemoMedia.image

        def spy(self_, prompt, **kw):
            seen["prompt"], seen["refs"] = prompt, kw.get("refs")
            return orig(self_, prompt, **kw)

        with mock.patch.object(DemoMedia, "image", spy):
            stats, ev = self.run_engine(self.c["id"])
        node_ = next(n for n in self.cs.get(self.c["id"])["nodes"] if n["id"] == "img")
        return seen, node_, ev

    def test_mentioned_images_become_the_references_in_order_and_the_prompt_is_rewritten(self):
        self.build("thumb: fundo @fnaf-1-office, o jovem @foto-perfil sentado")
        seen, n, _ = self.run_image()
        self.assertEqual(n["result"]["state"], "done", n["result"])
        self.assertEqual(len(seen["refs"]), 2)
        self.assertEqual(seen["refs"][0][0], self.cs.asset_path(self.c["id"], self.a["file"]).read_bytes())
        self.assertEqual(seen["refs"][1][0], self.cs.asset_path(self.c["id"], self.b["file"]).read_bytes())
        self.assertIn("fnaf-1-office (reference image 1)", seen["prompt"])
        self.assertIn("foto-perfil (reference image 2)", seen["prompt"])

    def test_connected_references_come_after_the_mentions_and_edit_mode_accepts_mentions_alone(self):
        self.cs.save_layout(self.c["id"], {"nodes": [node("upload", nid="u", files=[self.b["id"]]), node("image", nid="img", prompt="no cenário @fnaf-1-office", mode="edit")], "edges": [edge("u", "img", "refs")]})
        seen, n, _ = self.run_image()
        self.assertEqual(n["result"]["state"], "done", n["result"])
        self.assertEqual(len(seen["refs"]), 2)
        self.assertEqual(seen["refs"][0][0], self.cs.asset_path(self.c["id"], self.a["file"]).read_bytes())    # a citada primeiro
        self.build("só @foto-perfil", ())
        self.cs.patch_node_params(self.c["id"], "img", {"mode": "edit"})
        _, n, _ = self.run_image()
        self.assertEqual(n["result"]["state"], "done", n["result"])                                            # no modo Editar, a menção basta como imagem a editar

    def test_unknown_mentions_warn_and_stay_as_text(self):
        self.build("praia com @fantasma")
        seen, n, ev = self.run_image()
        self.assertEqual(n["result"]["state"], "done")
        self.assertIn("@fantasma", seen["prompt"])
        self.assertTrue(any("fantasma" in w for e in ev if e.get("type") == "node" for w in e.get("warnings", [])), ev[-2:])

    def test_citing_another_image_or_removing_the_prompt_mention_makes_the_node_stale(self):
        self.build("fundo @fnaf-1-office")
        self.run_image()
        eng = lambda: CanvasEngine(self.store, self.c["id"])  # noqa: E731
        self.assertEqual(eng().stale_ids(self.cs.get(self.c["id"])), [])
        self.cs.patch_node_params(self.c["id"], "img", {"prompt": "fundo @foto-perfil"})
        self.assertEqual(eng().stale_ids(self.cs.get(self.c["id"])), ["img"])

    @unittest.skipUnless(tools.have_ffmpeg(), "ffmpeg não instalado")
    def test_video_uses_the_first_mentioned_image_as_the_start_image(self):
        self.cs.save_layout(self.c["id"], {"nodes": [node("video", nid="vid", prompt="a câmera se aproxima de @foto-perfil e depois @fnaf-1-office", duration=1)], "edges": []})
        seen = {}
        orig = DemoMedia.video

        def spy(self_, prompt, **kw):
            seen["prompt"], seen["image"] = prompt, kw.get("image")
            return orig(self_, prompt, **kw)

        with mock.patch.object(DemoMedia, "video", spy):
            _, ev = self.run_engine(self.c["id"])
        n = next(x for x in self.cs.get(self.c["id"])["nodes"] if x["id"] == "vid")
        self.assertEqual(n["result"]["state"], "done", n["result"])
        self.assertEqual(seen["image"][0], self.cs.asset_path(self.c["id"], self.b["file"]).read_bytes())
        self.assertIn("foto-perfil (reference image 1)", seen["prompt"])
        self.assertTrue(any("uma só imagem inicial" in w for e in ev if e.get("type") == "node" for w in e.get("warnings", [])))


class MentionApi(ServerCase):
    def test_route_lists_images_with_filter_and_404(self):
        cv = self.store.canvases.create("M")
        self.store.canvases.add_asset(cv["id"], proc.image("a", "32x32", 1), "png", "image", name="Foto Perfil.png", mime="image/png")
        self.store.canvases.add_asset(cv["id"], proc.image("b", "32x32", 2), "png", "image", name="fnaf-office.png", mime="image/png")
        s, r = self.c.json("GET", f"/api/canvases/{cv['id']}/mentions")
        self.assertEqual((s, sorted(i["slug"] for i in r["items"])), (200, ["fnaf-office", "foto-perfil"]))
        self.assertTrue(all(i["url"].startswith(f"/api/canvases/{cv['id']}/assets/") for i in r["items"]))
        self.assertEqual([i["slug"] for i in self.c.json("GET", f"/api/canvases/{cv['id']}/mentions?q=fnaf")[1]["items"]], ["fnaf-office"])
        self.assertEqual(self.c.json("GET", "/api/canvases/nao_existe/mentions")[0], 404)


if __name__ == "__main__":
    unittest.main()
