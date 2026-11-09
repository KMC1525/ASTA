"""Studio: esquema (durações, estilos, série), armazenamento, render (modos/velocidade/mudo/filtros), pipeline cena a cena (Demo e com um «LLM» roteirizado),
retomada/refazer cena, edição automática por estilo e a API HTTP (geração, timeline, exportação completo/vídeo/áudio)."""
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.agents.runner import Cancelled  # noqa: E402
from asta.canvas.render import render_timeline  # noqa: E402
from asta.providers.base import ProviderError  # noqa: E402
from asta.storage import Store  # noqa: E402
from asta.studio import autoedit as AE  # noqa: E402
from asta.studio import rulebased as rb  # noqa: E402
from asta.studio import schema as S  # noqa: E402
from asta.studio import tools  # noqa: E402
from asta.studio.export import export_episode  # noqa: E402
from asta.studio.pipeline import StudioPipeline  # noqa: E402
from tests.test_core import TmpCase  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402

FF = tools.have_ffmpeg()
needs_ff = unittest.skipUnless(FF, "ffmpeg não instalado")


def make_media(folder: Path) -> dict:
    """Mídias sintéticas: vídeo de 40 s com picos de volume (8–10 s de cada 10) e silêncio no resto, música, narração e uma imagem."""
    def ff(*a):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)

    out = {k: folder / v for k, v in {"game": "game.mp4", "music": "phonk_music.wav", "voice": "narracao_voz.wav", "pic": "pic.png"}.items()}
    ff("-f", "lavfi", "-i", "testsrc2=d=40:s=320x240:r=24", "-f", "lavfi", "-i", "sine=f=300:d=40,volume='if(gt(mod(t,10),8),1.0,0.02)':eval=frame", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out["game"]))
    ff("-f", "lavfi", "-i", "sine=f=110:d=45", "-c:a", "pcm_s16le", str(out["music"]))
    ff("-f", "lavfi", "-i", "sine=f=200:d=20", "-c:a", "pcm_s16le", str(out["voice"]))
    ff("-f", "lavfi", "-i", "color=c=red:s=320x240", "-frames:v", "1", str(out["pic"]))
    return out


def upload(store: Store, path: Path) -> str:
    b = path.read_bytes()
    return store.save_upload_stream(path.name, "", io.BytesIO(b), len(b))["id"]


class SchemaTests(unittest.TestCase):
    def test_duration_types_and_custom_durations(self):
        d = {x["id"]: x for x in S.describe()["durations"]}
        self.assertEqual((d["shorts"]["max"], d["short"]["max"], d["long"]["max"]), (120, 1800, 5400))
        self.assertEqual(S.duration_type_for(60, "shorts"), "shorts")
        self.assertEqual(S.duration_type_for(200, "shorts"), "short")      # passou do teto: sobe para o tipo que cabe
        self.assertEqual(S.duration_type_for(3000, "short"), "long")
        self.assertEqual(S.duration_type_for(9000, "long"), "custom")      # acima de 90 min vira personalizada
        self.assertEqual(S.duration_type_for(100, "short"), "short")       # o usuário escolheu «curta» com 100 s: vale
        p = S.normalize_project({"target_seconds": 7200, "duration_type": "long"})
        self.assertEqual((p["duration_type"], p["target_seconds"]), ("custom", 7200))
        self.assertEqual(S.normalize_project({"target_seconds": 1})["target_seconds"], S.MIN_SECONDS)
        self.assertEqual(S.normalize_project({"target_seconds": 10 ** 9})["target_seconds"], S.MAX_SECONDS)
        self.assertEqual(S.normalize_project({"duration_type": "shorts"})["aspect"], "9:16")
        self.assertEqual(S.normalize_project({"duration_type": "long", "target_seconds": 3600})["aspect"], "16:9")

    def test_styles_and_series(self):
        self.assertEqual([k for k in S.STYLES], ["realistic", "cartoon", "anime", "custom"])
        self.assertIn("anime", S.style_look({"style": "anime"})["look"])
        self.assertEqual(S.style_look({"style": "custom", "style_custom": "aquarela suave"})["look"], "aquarela suave")
        single = S.normalize_project({"kind": "single", "episodes": [{}, {}, {}]})
        self.assertEqual(len(single["episodes"]), 1)
        series = S.normalize_project({"kind": "series", "episodes": [{}, {}, {}]})
        self.assertEqual([e["n"] for e in series["episodes"]], [1, 2, 3])
        self.assertEqual(S.normalize_project({"kind": "x", "style": "x", "motion": "x"})["style"], "realistic")

    def test_timeline_normalization(self):
        tl = S.normalize_timeline({"tracks": [{"id": "v", "kind": "video"}, {"id": "a", "kind": "audio"}, {"id": "t", "kind": "text"}],
                                   "clips": [{"id": "c1", "track": "v", "asset": "a_1", "start": 1, "dur": 2, "speed": 9, "filter": "nope", "mute": 1, "volume": 5},
                                             {"id": "c1", "track": "a", "asset": "a_2"}, {"track": "zz", "asset": "x"}, {"track": "v"}, {"track": "t", "text": "oi", "start": 0, "dur": 1}],
                                   "markers": [{"t": 3, "label": "x"}, "lixo"]})
        c = {x["id"]: x for x in tl["clips"]}
        self.assertEqual(len(tl["clips"]), 3)                       # clipe sem ativo e de trilha inexistente somem; id repetido é renomeado
        self.assertEqual((c["c1"]["speed"], c["c1"]["filter"], c["c1"]["mute"], c["c1"]["volume"]), (4, "none", True, 2))
        self.assertEqual(tl["duration"], 3.0)
        self.assertEqual(len(tl["markers"]), 1)
        self.assertEqual([t["name"] for t in S.normalize_timeline({})["tracks"]], ["T1", "V2", "V1", "A1", "A2", "A3"])


class RulebasedTests(unittest.TestCase):
    def test_narration_budget_and_secs(self):
        self.assertEqual(rb.trim_words("um dois três quatro cinco seis sete oito nove dez onze doze", 5), "um dois três quatro cinco…")
        self.assertEqual(rb.trim_words("Primeira frase longa aqui. Segunda frase vai passar do limite de palavras permitido agora.", 6), "Primeira frase longa aqui.")
        s = rb.scale_secs([1, 1, 2], 20)
        self.assertAlmostEqual(sum(s), 20, places=1)
        self.assertTrue(rb.scene_checks({"narration": "palavra " * 200, "shots": [{"visual": "x"}]}, 10))
        self.assertFalse(rb.scene_checks({"narration": "curta", "shots": [{"visual": "x"}]}, 10))


class StoreTests(TmpCase):
    def test_projects_assets_and_clip_cleanup(self):
        st = Store(self.tmp / "home")
        p = st.studio.create({"name": "A", "kind": "series", "prompt": "oi"})
        self.assertEqual(len(p["episodes"]), 1)
        from asta.canvas import procedural as proc

        rec = st.studio.add_asset(p["id"], proc.image("x", "64x64", 1), "png", "image", name="x.png")
        self.assertEqual((rec["kind"], rec["w"]), ("image", 64))
        self.assertTrue(st.studio.media_path(p["id"], rec["file"]))
        self.assertIsNone(st.studio.media_path(p["id"], "../project.json"))
        eid = p["episodes"][0]["id"]
        st.studio.update(p["id"], lambda pr: pr["episodes"][0].update(timeline={"clips": [{"id": "c", "track": "t_v1", "asset": rec["id"], "dur": 2}]}))
        self.assertEqual(len(st.studio.get(p["id"])["episodes"][0]["timeline"]["clips"]), 1)
        self.assertTrue(st.studio.delete_asset(p["id"], rec["id"]))
        self.assertEqual(st.studio.get(p["id"])["episodes"][0]["timeline"]["clips"], [])
        self.assertIsNone(st.studio.media_path(p["id"], rec["file"]))
        self.assertEqual(st.studio.list()[0]["id"], p["id"])
        self.assertTrue(st.studio.delete(p["id"]))
        self.assertIsNone(st.studio.get(p["id"]))
        self.assertIsNone(st.studio.get("../x"))


class MixerSchemaTests(unittest.TestCase):
    def test_track_volume_and_master_are_normalized_and_default_to_unity(self):
        t = S.normalize_timeline({"tracks": [{"id": "a", "kind": "audio", "volume": 1.5}, {"id": "b", "kind": "audio", "volume": 9}, {"id": "c", "kind": "audio", "volume": "x"}, {"id": "d", "kind": "video", "collapsed": True}], "master": 0.5})
        self.assertEqual([x["volume"] for x in t["tracks"]], [1.5, 2.0, 1.0, 1.0])
        self.assertEqual((t["master"], [x["collapsed"] for x in t["tracks"]]), (0.5, [False, False, False, True]))
        d = S.normalize_timeline({})
        self.assertEqual(d["master"], 1.0)
        self.assertTrue(all(x["volume"] == 1.0 for x in d["tracks"]))


@needs_ff
class RenderTests(TmpCase):
    def test_mixer_track_volume_and_master_scale_the_exported_audio(self):
        m = make_media(self.tmp)
        res = lambda c: {"path": m["music"], "kind": "audio", "duration": 40}  # noqa: E731

        def loud(**kw):
            tl = S.normalize_timeline({"tracks": [{"id": "t_a1", "kind": "audio", "name": "A1", "volume": kw.get("track", 1.0)}], "master": kw.get("master", 1.0),
                                       "clips": [{"id": "a", "track": "t_a1", "asset": "m", "start": 0, "dur": 3, "volume": 1.0}]})
            out = self.tmp / f"v{len(list(self.tmp.glob('v*.wav')))}.wav"
            render_timeline(tl, 320, 180, 12, "#000000", res, out, mode="audio")
            r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(out), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
            return float(re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr).group(1))
        base, half_track, half_master = loud(), loud(track=0.5), loud(master=0.5)
        self.assertAlmostEqual(base - half_track, 6.0, delta=0.6)     # metade do volume = -6 dB
        self.assertAlmostEqual(base - half_master, 6.0, delta=0.6)
        self.assertAlmostEqual(base - loud(track=0.5, master=0.5), 12.0, delta=0.8)   # os dois se multiplicam

    def test_modes_speed_mute_and_grades(self):
        m = make_media(self.tmp)
        res = lambda c: {"path": m["game"] if c["asset"] == "v" else m["music"], "kind": "video" if c["asset"] == "v" else "audio", "duration": 40}  # noqa: E731

        def tl(**kw):
            return S.normalize_timeline({"clips": [{"id": "a", "track": "t_v1", "asset": "v", "start": 0, "dur": 3, "in": 8, "filter": kw.get("f", "none"), "speed": kw.get("sp", 1), "mute": kw.get("mute", False)},
                                                   {"id": "b", "track": "t_a2", "asset": "m", "start": 0, "dur": 3, "volume": 0.5}, {"id": "t", "track": "t_t1", "text": "Oi", "start": 0, "dur": 2}]})
        out = self.tmp / "o.mp4"
        render_timeline(tl(), 320, 180, 12, "#000000", res, out, mode="full")
        i = tools.probe(out)
        self.assertTrue(i["video"] and i["audio"])
        render_timeline(tl(), 320, 180, 12, "#000000", res, out, mode="video")
        i = tools.probe(out)
        self.assertTrue(i["video"] and not i["audio"])
        for ext in ("m4a", "mp3", "wav"):
            a = self.tmp / f"o.{ext}"
            render_timeline(tl(), 320, 180, 12, "#000000", res, a, mode="audio")
            i = tools.probe(a)
            self.assertTrue(i["audio"] and not i["video"], ext)
            self.assertAlmostEqual(i["dur"], 3.0, delta=0.15)
        # tudo mudo + só áudio: erro claro
        silent = S.normalize_timeline({"clips": [{"id": "a", "track": "t_v1", "asset": "v", "start": 0, "dur": 2, "mute": True}]})
        with self.assertRaises(ProviderError) as cm:
            render_timeline(silent, 320, 180, 12, "#000000", res, self.tmp / "s.m4a", mode="audio")
        self.assertIn("áudio", str(cm.exception))
        render_timeline(silent, 320, 180, 12, "#000000", res, out, mode="full")      # clipe mudo: sem áudio no resultado
        self.assertFalse(tools.probe(out)["audio"])
        for g in ("bw", "warm", "cool", "vivid", "vhs", "cinematic", "phonk"):
            render_timeline(tl(f=g), 320, 180, 12, "#000000", res, out)
            self.assertTrue(tools.probe(out)["video"], g)
        for sp in (0.5, 2, 4):  # a duração na timeline é a do clipe, qualquer que seja a velocidade
            render_timeline(tl(sp=sp), 320, 180, 12, "#000000", res, out)
            self.assertAlmostEqual(tools.probe(out)["dur"], 3.0, delta=0.2)

    def test_tools_detect_loud_moments_scenes_and_silence(self):
        m = make_media(self.tmp)
        info = tools.probe(m["game"])
        self.assertAlmostEqual(info["dur"], 40, delta=0.5)
        self.assertTrue(info["audio"] and info["video"])
        peaks = tools.loud_moments(m["game"], 0.5)
        self.assertTrue(peaks and all(8 <= (t % 10) <= 10 or (t % 10) < 0.6 for t, _ in peaks[:8]), peaks[:8])
        sil = tools.silences(m["game"])
        self.assertTrue(any(s < 1 and e > 7 for s, e in sil), sil[:3])


class FakeProvider:
    """«LLM» roteirizado: devolve JSON por agente (e conta chamadas)."""
    vision, model = False, "fake"

    def __init__(self, script=None):
        self.script, self.calls = script or {}, []

    def chat(self, messages, system="", temperature=0.2, max_tokens=512, json_mode=False, stream=False):
        agent = re.search(r"\[\[ASTA_AGENT:(\w+)\]\]", system).group(1)
        payload = json.loads(str(messages[0]["content"]).split("INPUT_JSON:\n", 1)[1])
        self.calls.append((agent, payload))
        out = self.script.get(agent)
        out = out(payload) if callable(out) else out
        if out == "garbage":
            return "isto não é json"
        return json.dumps(out if out is not None else {}, ensure_ascii=False)


class PipelineTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "home")
        self.events = []

    def project(self, **kw):
        base = {"name": "Teste", "kind": "single", "duration_type": "shorts", "target_seconds": 24, "style": "anime", "music": False, "prompt": "Uma raposa viaja pela floresta. Ela encontra um rio. Ela chega em casa."}
        return self.store.studio.create({**base, **kw})

    def run_pipe(self, p, **req):
        pipe = StudioPipeline(self.store, self.events.append, req.pop("cancelled", lambda: False))
        return pipe.run({"project_id": p["id"], "episode_id": p["episodes"][0]["id"], **req})

    @needs_ff
    def test_scene_by_scene_in_demo_mode_builds_an_editable_timeline(self):
        p = self.project()
        r = self.run_pipe(p)
        self.assertEqual((r["scenes"], r["delivered"]), (3, 3))
        e = self.store.studio.get(p["id"])["episodes"][0]
        self.assertEqual(e["status"], "ready")
        self.assertAlmostEqual(e["timeline"]["duration"], 24, delta=0.6)
        # cada cena passou pelos 5 passos, na ordem, ANTES de a próxima começar
        seq = [(ev["id"], ev["stage"]) for ev in self.events if ev["type"] == "scene" and ev["status"] == "running"]
        ids = [s["id"] for s in e["scenes"]]
        self.assertEqual(seq, [(sid, st) for sid in ids for st in S.STAGES])
        self.assertTrue(all(s["status"] == "delivered" and all(v == "done" for v in s["stages"].values()) for s in e["scenes"]))
        done = [ev["id"] for ev in self.events if ev["type"] == "scene_done"]
        self.assertEqual(done, ids)
        kinds = {c["track"] for c in e["timeline"]["clips"]}
        self.assertTrue({"t_v1", "t_a1", "t_t1"} <= kinds)                       # vídeo, voz e legendas
        for sc in e["scenes"]:                                                    # cada cena tem clipes no seu trecho, sem sair dele
            cl = [c for c in e["timeline"]["clips"] if c["scene"] == sc["id"] and c["track"] == "t_v1"]
            self.assertTrue(cl)
            self.assertAlmostEqual(min(c["start"] for c in cl), sc["start"], delta=0.05)
            self.assertAlmostEqual(max(c["start"] + c["dur"] for c in cl), sc["start"] + sc["actual"], delta=0.1)
        p2 = self.store.studio.get(p["id"])
        self.assertTrue(all(self.store.studio.media_path(p["id"], a["file"]) for a in p2["assets"]))
        self.assertEqual({a["kind"] for a in p2["assets"]}, {"image", "video", "audio"})

    @needs_ff
    def test_cancel_then_resume_keeps_delivered_scenes_and_redo_one_scene(self):
        p = self.project(target_seconds=24)
        n = {"scenes": 0}

        def cancelled():
            return n["scenes"] >= 1

        orig = self.events.append

        def emit(ev):
            if ev["type"] == "scene_done":
                n["scenes"] += 1
            orig(ev)

        pipe = StudioPipeline(self.store, emit, cancelled)
        with self.assertRaises(Cancelled):
            pipe.run({"project_id": p["id"], "episode_id": p["episodes"][0]["id"]})
        e = self.store.studio.get(p["id"])["episodes"][0]
        self.assertEqual([s["status"] for s in e["scenes"]].count("delivered"), 1)
        first_assets = {c["asset"] for c in e["timeline"]["clips"] if c["scene"] == e["scenes"][0]["id"]}
        self.events.clear()
        self.run_pipe(p)                                                          # retoma: a cena entregue não é refeita
        e = self.store.studio.get(p["id"])["episodes"][0]
        self.assertTrue(all(s["status"] == "delivered" for s in e["scenes"]))
        self.assertEqual(first_assets, {c["asset"] for c in e["timeline"]["clips"] if c["scene"] == e["scenes"][0]["id"]})
        self.assertEqual([ev["n"] for ev in self.events if ev["type"] == "scene_done"], [2, 3])
        # refazer só a cena 2: as outras ficam idênticas
        before = {s["id"]: sorted(c["asset"] for c in e["timeline"]["clips"] if c["scene"] == s["id"]) for s in e["scenes"]}
        sid = e["scenes"][1]["id"]
        self.events.clear()
        self.run_pipe(p, redo=[sid])
        e2 = self.store.studio.get(p["id"])["episodes"][0]
        after = {s["id"]: sorted(c["asset"] for c in e2["timeline"]["clips"] if c["scene"] == s["id"]) for s in e2["scenes"]}
        self.assertEqual([k for k in before if before[k] != after[k]], [sid])
        self.assertEqual([ev["id"] for ev in self.events if ev["type"] == "scene_done"], [sid])

    def test_planning_uses_acts_for_long_episodes_and_scene_counts_follow_the_duration_type(self):
        p = self.project(duration_type="short", target_seconds=1500)               # curta: cenas de ~40 s → 38 cenas → em atos
        pipe = StudioPipeline(self.store, self.events.append)
        pipe.pid, pipe.eid, pipe.demo, pipe.settings = p["id"], p["episodes"][0]["id"], True, self.store.get_settings()
        ep = p["episodes"][0]
        pipe._plan(p, ep, "Uma história épica. Com muitos acontecimentos. E um final surpreendente.", "")
        e = self.store.studio.get(p["id"])["episodes"][0]
        self.assertEqual(len(e["scenes"]), 38)
        self.assertAlmostEqual(sum(s["secs"] for s in e["scenes"]), 1500, delta=1)
        self.assertEqual([s["n"] for s in e["scenes"]], list(range(1, 39)))
        self.assertAlmostEqual(e["scenes"][-1]["start"] + e["scenes"][-1]["secs"], 1500, delta=1)
        notes = [ev["message"] for ev in self.events if ev["type"] == "note"]
        self.assertTrue(any(m.startswith("Ato 1/") for m in notes))
        short = self.project(duration_type="shorts", target_seconds=60)
        self.assertEqual(max(1, round(60 / S.DURATION_TYPES["shorts"]["scene_len"])), 8)
        self.assertEqual(round(5400 / S.DURATION_TYPES["long"]["scene_len"]), 60)
        self.assertEqual(short["episodes"][0]["target"], 60)

    @needs_ff
    def test_text_agents_reviewer_fix_and_invalid_json_fallback(self):
        self.store.save_settings({"active": {"generation": "openai"}})
        long_text = "palavra " * 90
        calls = {"rev": 0}

        def reviewer(payload):
            calls["rev"] += 1
            if calls["rev"] == 1:
                return {"approved": False, "score": 4, "issues": ["narração longa"], "fix": {"narration": "Texto curto e certo."}}
            return {"approved": True, "score": 9, "issues": [], "fix": {}}

        prov = FakeProvider({
            "studio_planner": {"title": "Raposa", "logline": "x", "scenes": [{"title": "Única", "summary": "s", "narration": long_text, "visual": "uma raposa", "sound": "", "secs": 10}],
                               "bible": {"tone": "leve", "world": "floresta", "characters": [{"name": "Raposa", "look": "pelo laranja"}]}},
            "studio_analyst": "garbage", "studio_reviewer": reviewer, "studio_recap": {"recap": "A raposa voltou.", "bible_update": {"characters": [{"name": "Lobo", "look": "cinza"}], "facts": ["Moram no rio"]}}})
        p = self.project(target_seconds=10, revisions=1)
        with mock.patch("asta.studio.pipeline.build_provider", return_value=prov):
            r = self.run_pipe(p)
        e = self.store.studio.get(p["id"])
        ep = e["episodes"][0]
        self.assertEqual(ep["title"], "Raposa")
        self.assertEqual(ep["recap"], "A raposa voltou.")
        self.assertEqual(ep["scenes"][0]["narration"], "Texto curto e certo.")      # a correção do Revisor foi aplicada e a voz refeita
        self.assertEqual(ep["scenes"][0]["revisions"], 1)
        self.assertEqual(calls["rev"], 2)
        self.assertEqual({c["name"] for c in e["bible"]["characters"]}, {"Raposa", "Lobo"})
        self.assertIn("Moram no rio", e["bible"]["facts"])
        self.assertTrue(any("fallback" in w for w in r["warnings"]))                  # o Analista devolveu lixo: caiu no determinístico
        voice = [a for a in e["assets"] if a["name"].endswith("voz1")]
        self.assertGreaterEqual(len(voice), 1)
        # o prompt do estilo e a aparência dos personagens chegam ao gerador de imagem
        imgs = [a["prompt"] for a in e["assets"] if a["kind"] == "image"]
        self.assertTrue(imgs and all("anime style" in x for x in imgs))
        self.assertTrue(any("pelo laranja" in x for x in imgs))
        self.assertTrue(any(c[0] == "studio_planner" for c in prov.calls))

    @needs_ff
    def test_series_episodes_get_the_bible_and_recaps(self):
        self.store.save_settings({"active": {"generation": "openai"}})
        prov = FakeProvider({"studio_planner": lambda pl: {"title": f"Ep {pl['episode']}", "logline": "", "scenes": [{"title": "A", "summary": "s", "narration": "Oi.", "visual": "v", "secs": 8}], "bible": {"characters": []}},
                             "studio_recap": {"recap": "Resumo do primeiro episódio.", "bible_update": {"facts": ["fato"]}}})
        p = self.project(kind="series", target_seconds=8)
        with mock.patch("asta.studio.pipeline.build_provider", return_value=prov):
            self.run_pipe(p)
            p = self.store.studio.get(p["id"])
            ep2 = S.normalize_episode({"title": "Segundo", "prompt": "continua", "target": 8}, 1)
            self.store.studio.update(p["id"], lambda pr: pr["episodes"].append(ep2))
            pipe = StudioPipeline(self.store, self.events.append)
            pipe.run({"project_id": p["id"], "episode_id": ep2["id"]})
        plan2 = [pl for n, pl in prov.calls if n == "studio_planner"][-1]
        self.assertEqual(plan2["episode"], 2)
        self.assertEqual(plan2["recaps"][0]["recap"], "Resumo do primeiro episódio.")
        self.assertIn("fato", plan2["bible"]["facts"])
        self.assertEqual(len(self.store.studio.get(p["id"])["episodes"]), 2)

    @needs_ff
    def test_media_errors_stop_after_three_scenes_with_a_clear_message(self):
        p = self.project(target_seconds=40, duration_type="shorts")
        with mock.patch("asta.studio.pipeline.StudioPipeline._provider", side_effect=ProviderError("Chave de API ausente")):
            with self.assertRaises(ProviderError) as cm:
                self.run_pipe(p)
        self.assertIn("Chave de API ausente", str(cm.exception))
        e = self.store.studio.get(p["id"])["episodes"][0]
        self.assertEqual([s["status"] for s in e["scenes"]].count("error"), 3)       # parou na terceira falha seguida


@needs_ff
class PlanQualityTests(unittest.TestCase):
    """Técnicas de edição (gancho, sem repetição, cobertura, estrutura da batida) no planejador determinístico."""

    @staticmethod
    def inv(**extra):
        v = {"id": "v", "name": "v", "kind": "video", "dur": 120.0, "has_audio": True, "loud": [(100.0, -5.0), (30.0, -8.0), (60.0, -9.0), (10.0, -12.0), (80.0, -13.0), (45.0, -14.0), (20.0, -15.0), (70.0, -16.0), (90.0, -17.0), (110.0, -18.0), (5.0, -19.0), (55.0, -20.0)], "changes": [20.0, 50.0, 90.0], "silences": [(5.0, 9.0), (40.0, 44.0)]}
        v.update(extra)
        return [v, {"id": "p", "name": "p", "kind": "image", "dur": 0.0, "has_audio": False, "loud": [], "changes": [], "silences": []},
                {"id": "m", "name": "musica", "kind": "audio", "dur": 60.0, "has_audio": True, "loud": [], "changes": [], "silences": []}]

    def test_gameplay_opens_with_the_hook_then_follows_the_story_order(self):
        roles = {"v": "footage", "p": "broll", "m": "music"}
        e = AE.plan_edl("gameplay", self.inv(), roles, 40, {"highlights": [{"asset": "v", "t": 100.0}]}, 0, 1, "t")
        segs = e["segments"]
        self.assertTrue(segs[0]["in"] <= 100.0 <= segs[0]["in"] + segs[0]["dur"] + 0.01)
        self.assertGreaterEqual(segs[0]["scale"], 1.1)  # o gancho abre com zoom
        rest = [g["in"] for g in segs[1:] if g["asset"] == "v"]
        self.assertEqual(rest, sorted(rest))

    def test_no_clip_repeats_while_there_is_new_material(self):
        roles = {"v": "footage", "p": "broll", "m": "music"}
        for style in ("gameplay", "vlog", "documentary"):
            e = AE.plan_edl(style, self.inv(), roles, 40, {}, 0, 2, "t")
            vid = [g for g in e["segments"] if g["asset"] == "v"]
            for i, g in enumerate(vid):
                for h in vid[:i]:
                    self.assertLessEqual(min(g["in"] + g["dur"], h["in"] + h["dur"]) - max(g["in"], h["in"]), 0.5 * g["dur"] + 0.01, style)

    def test_documentary_and_vlog_insert_cutaways_between_main_shots(self):
        roles = {"v": "footage", "p": "broll", "m": "music"}
        e = AE.plan_edl("documentary", self.inv(), roles, 60, {}, 0, 3, "t")
        ids = [g["asset"] for g in e["segments"]]
        self.assertNotEqual(ids[0], "p")
        self.assertEqual(ids.count("p"), 0)   # com um vídeo principal comprido, a foto não entra na V1: vira cobertura na V2
        self.assertTrue(e["overlays"] and all(o["asset"] == "p" and o["mode"] == "cutaway" for o in e["overlays"]))
        self.assertTrue(all(g["scale"] >= 1.0 for g in e["segments"]))

    def test_layers_short_material_goes_to_V2_and_the_main_footage_stays_alone_on_V1(self):
        main = {"id": "v", "name": "v", "kind": "video", "dur": 120.0, "has_audio": True, "loud": [(float(x), -10.0) for x in range(5, 115, 9)], "changes": [], "silences": []}
        meme = {"id": "m", "name": "meme", "kind": "video", "dur": 3.0, "has_audio": True, "loud": [], "changes": [], "silences": []}
        pic = {"id": "p", "name": "p", "kind": "image", "dur": 0.0, "has_audio": False, "loud": [], "changes": [], "silences": []}
        roles = {"v": "footage", "m": "broll", "p": "broll"}
        g = AE.plan_edl("gameplay", [main, meme, pic], roles, 60, {}, 0, 1, "t")
        self.assertTrue(all(s["asset"] == "v" for s in g["segments"]))              # a V1 é só o principal
        ov = g["overlays"]
        self.assertTrue(ov and {o["mode"] for o in ov} == {"pip"} and all(o["scale"] < 0.5 for o in ov))   # janelinhas nos cantos
        self.assertEqual({o["asset"] for o in ov} <= {"m", "p"}, True)
        starts = sorted((o["start"], o["start"] + o["dur"]) for o in ov)
        self.assertTrue(all(a[1] <= b[0] for a, b in zip(starts, starts[1:])))      # sem sobreposição entre elas
        self.assertTrue(all(0 <= a < g["total"] for a, _ in starts))
        d = AE.plan_edl("documentary", [main, pic], {"v": "footage", "p": "broll"}, 60, {}, 0, 1, "t")
        self.assertTrue(d["overlays"] and {o["mode"] for o in d["overlays"]} == {"cutaway"} and d["overlays"][0]["scale"] == 1.0)
        # vários vídeos de tamanho parecido: continuam em sequência na V1 (nada de camadas à toa)
        a, b = dict(main, id="a", dur=30.0), dict(main, id="b", dur=28.0)
        s = AE.plan_edl("gameplay", [a, b], {"a": "footage", "b": "footage"}, 40, {}, 0, 1, "t")
        self.assertEqual(s["overlays"], [])
        self.assertEqual({x["asset"] for x in s["segments"]}, {"a", "b"})
        # estilos sem camadas (batida) não sobrepõem
        self.assertEqual(AE.plan_edl("phonk", [main, meme], {"v": "footage", "m": "broll"}, 30, {}, 140, 1, "t")["overlays"], [])

    def test_silence_cuts_keep_a_breathing_pad(self):
        pad = AE.EDIT_STYLES["vlog"]["pad"]
        w = AE._windows(self.inv()[0], AE.EDIT_STYLES["vlog"], 3, 8, {}, __import__("random").Random(1))
        self.assertTrue(any(abs(e - (5.0 + pad)) < 0.01 for s, e in w) or any(e <= 5.0 + pad + 0.01 for s, e in w))

    def test_phonk_builds_up_then_drops_and_closes_in_slow_motion(self):
        roles = {"v": "footage", "m": "music"}
        e = AE.plan_edl("phonk", self.inv(), roles, 30, {}, 140, 4, "t")
        segs = e["segments"]
        q = max(1, len(segs) // 4)
        intro = sum(g["dur"] for g in segs[:q]) / q
        drop = sum(g["dur"] for g in segs[q:-q]) / max(1, len(segs) - 2 * q)
        self.assertGreater(intro, drop)  # introdução mais lenta que o «drop»
        self.assertTrue(any(g["speed"] == 0.5 for g in segs[-3:]))
        t, early = 0.0, []
        for g in segs:
            if t < 0.2 * e["total"]:
                early.append(g)
            t += g["dur"]
        self.assertTrue(all(g["speed"] == 1.0 for g in early))  # rampas só depois da introdução

    def test_trailer_ends_with_a_title_card_and_every_style_has_a_craft_note(self):
        roles = {"v": "footage", "m": "music"}
        e = AE.plan_edl("trailer", self.inv(), roles, 60, {}, 0, 5, "Meu Filme")
        self.assertTrue(any(t["text"] == "Meu Filme" and t["start"] >= e["total"] - 3 for t in e["titles"]))
        self.assertTrue(all(x["craft"] for x in AE.describe_styles()))


@needs_ff
class AutoEditTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "home")
        self.media = make_media(self.tmp)

    def edit(self, style, files=("game", "music"), **kw):
        ids = [upload(self.store, self.media[k]) for k in files]
        ev = []
        r = AE.AutoEditPipeline(self.store, ev.append).run({"attachment_ids": ids, "prompt": "melhores momentos", "style": style, "target_seconds": 20, **kw})
        p = self.store.studio.get(r["project_id"])
        return r, p, p["episodes"][0], ev

    def test_every_style_builds_a_timeline_close_to_the_target(self):
        for style in AE.EDIT_STYLES:
            r, p, e, ev = self.edit(style, ("game", "music", "pic"))
            self.assertAlmostEqual(e["timeline"]["duration"], 20, delta=2.5, msg=style)
            self.assertEqual(e["origin"], "autoedit")
            self.assertEqual(e["edit"]["style"], style)
            steps = [x["id"] for x in ev if x["type"] == "step" and x["status"] in ("done", "warn")]
            self.assertEqual(steps, ["attachments", "analyst", "director", "reviewer", "assemble"], style)
            cl = e["timeline"]["clips"]
            self.assertTrue(all(c["asset"] in {a["id"] for a in p["assets"]} for c in cl if c["asset"]))
            for c in cl:
                a = next((x for x in p["assets"] if x["id"] == c["asset"]), None)
                if a and a["kind"] == "video":
                    self.assertLessEqual(c["in"] + c["dur"] * c["speed"], a["dur"] + 0.1, style)
            # o resultado exporta de verdade
            rec = export_episode(self.store, p["id"], e["id"], "full", "480p")
            self.assertTrue(tools.probe(self.store.studio.export_path(p["id"], rec["file"]))["video"])
        self.assertEqual(self.store.uploads_dir.exists() and len(list(self.store.uploads_dir.iterdir())), 0)  # anexos não ficam duplicados

    def test_styles_behave_differently(self):
        _, p, ph, _ = self.edit("phonk")
        _, _, gp, _ = self.edit("gameplay")
        _, _, doc, _ = self.edit("documentary")
        cuts = lambda e: [c for c in e["timeline"]["clips"] if c["track"] == "t_v1"]  # noqa: E731
        self.assertTrue(all(c["mute"] for c in cuts(ph)))                              # phonk: só a música
        self.assertTrue(all(c["filter"] == "phonk" for c in cuts(ph)))
        self.assertTrue({c["speed"] for c in cuts(ph)} >= {0.6, 1.5})                  # câmera lenta e rápida
        beat = 60 / 140
        self.assertTrue(all(abs(c["dur"] / beat - round(c["dur"] / beat)) < 0.06 or c is cuts(ph)[-1] for c in cuts(ph)))   # cortes na grade da batida
        self.assertTrue(any(c["scale"] > 1 for c in cuts(ph)))
        self.assertFalse(any(c["mute"] for c in cuts(gp)))                             # gameplay mantém o som original
        self.assertGreater(len(cuts(ph)), len(cuts(gp)))                               # phonk corta mais que gameplay
        self.assertGreater(len(cuts(gp)), len(cuts(doc)))                              # documentário é o mais calmo
        self.assertTrue(all(c["fade_in"] > 0 for c in cuts(doc)))                      # transições suaves
        self.assertTrue([c for c in doc["timeline"]["clips"] if c["track"] == "t_t1"]) # cartela de título
        # gameplay busca os picos de volume (8–10 s de cada 10)
        hits = sum(1 for c in cuts(gp) if any(8 <= (c["in"] + k * 0.1) % 10 <= 10 for k in range(int(c["dur"] * 10))))
        self.assertGreaterEqual(hits, len(cuts(gp)) - 2)

    def test_roles_voiceover_music_and_silence_removal(self):
        _, p, e, _ = self.edit("tutorial", ("game", "voice", "music"))
        tr = {c["track"] for c in e["timeline"]["clips"]}
        self.assertIn("t_a1", tr)                                                      # «narracao_voz» virou narração (A1)
        self.assertIn("t_a2", tr)                                                      # a outra faixa é música (A2)
        sil = tools.silences(self.media["game"])
        for c in [c for c in e["timeline"]["clips"] if c["track"] == "t_v1"]:           # tutorial remove pausas: nenhum corte começa dentro de um silêncio longo
            self.assertFalse(any(s + 0.3 < c["in"] < en - 0.3 for s, en in sil), (c["in"], sil[:4]))

    @needs_ff
    def test_layered_edit_puts_memes_on_V2_and_renders_them_over_the_main_video(self):
        from asta.studio.export import export_episode

        meme = self.tmp / "meme_reacao.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=d=3:s=160x120:r=24", "-f", "lavfi", "-i", "sine=f=500:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(meme)], check=True)
        self.media["meme"] = meme
        r, p, e, ev = self.edit("gameplay", ("game", "music", "meme", "pic"), target_seconds=30)
        tl = e["timeline"]
        tracks = {t["id"]: t["name"] for t in tl["tracks"]}
        by = {}
        for c in tl["clips"]:
            by.setdefault(tracks[c["track"]], []).append(c)
        names = {a["id"]: a["name"] for a in p["assets"]}
        self.assertTrue(all("game" in names[c["asset"]] for c in by["V1"]))           # a V1 é só o vídeo principal
        self.assertTrue(by.get("V2"), tracks)                                         # memes e foto em outra camada
        self.assertTrue(all(c["scale"] < 0.5 for c in by["V2"]))
        self.assertIn("A2", by)                                                       # a música continua na própria trilha
        out = export_episode(self.store, p["id"], e["id"], "video", "480p")
        self.assertTrue(out)

    def test_roles_can_be_chosen_by_the_text_agents_and_bad_answers_are_ignored(self):
        self.store.save_settings({"active": {"generation": "openai"}})
        ids = [upload(self.store, self.media[k]) for k in ("game", "music")]
        prov = FakeProvider({"studio_edit_analyst": "garbage", "studio_edit_director": {"pace": "fast", "order": ["x"], "highlights": [{"asset": "x", "t": 3}], "avoid": [], "titles": ["Meu título"]},
                             "studio_edit_reviewer": {"approved": True, "tips": ["use mais zoom"]}})
        ev = []
        with mock.patch("asta.studio.autoedit.build_provider", return_value=prov):
            r = AE.AutoEditPipeline(self.store, ev.append).run({"attachment_ids": ids, "style": "documentary", "target_seconds": 20, "prompt": "x"})
        e = self.store.studio.get(r["project_id"])["episodes"][0]
        self.assertTrue(any("dica: use mais zoom" in w for w in r["warnings"]))
        self.assertTrue(any(c["text"] == "Meu título" for c in e["timeline"]["clips"] if c["track"] == "t_t1"))

    def test_truncated_agent_answers_are_recovered_and_failures_are_explained(self):
        """Resposta cortada (modelo que «pensa» e estoura os tokens) é recuperada; resposta inútil vira nota visível, não só um ⚠ mudo."""
        from asta.agents.llm import call_json, salvage_json

        obj = salvage_json('<think>hmm</think>```json\n{"title":"T","focus":["a"],"roles":{"x":"footage","y":"mu')
        self.assertEqual((obj["title"], obj["roles"]["x"]), ("T", "footage"))

        class Cut:
            vision = False
            seen = []

            def chat(self, messages, system="", temperature=0.2, max_tokens=512, json_mode=False, stream=False):
                Cut.seen.append(max_tokens)
                return '{"pace":"fast","order":["a"],"highlights":[{"asset":"a","t":3},{"asset":"a","t'
        o, _ = call_json(Cut(), "s", "i", {}, max_tokens=900, salvage=True)
        self.assertEqual(o["pace"], "fast")
        self.assertEqual(Cut.seen, [900, 1800])  # a 2ª tentativa tem mais espaço
        with self.assertRaises(ValueError):
            call_json(Cut(), "s", "i", {}, max_tokens=900)  # sem salvage (outros agentes) continua exigindo JSON completo

        self.store.save_settings({"active": {"generation": "openai"}})
        ids = [upload(self.store, self.media[k]) for k in ("game", "music")]
        prov = FakeProvider({"studio_edit_analyst": "garbage", "studio_edit_director": "garbage"})
        ev = []
        with mock.patch("asta.studio.autoedit.build_provider", return_value=prov):
            AE.AutoEditPipeline(self.store, ev.append).run({"attachment_ids": ids, "style": "vlog", "target_seconds": 20, "prompt": "x"})
        notes = [x["message"] for x in ev if x["type"] == "note" and "JSON válido" in x["message"]]
        self.assertEqual(len(notes), 2)

    def test_answers_with_no_visible_json_are_rescued_or_explained(self):
        from asta.agents.llm import call_json, extract_json

        self.assertEqual(extract_json('<think>penso... {"pace":"fast"} pronto', lenient=True)["pace"], "fast")  # <think> que nunca fechou
        self.assertEqual(extract_json('<think>{"a":1}</think>', lenient=True)["a"], 1)  # resposta escrita dentro do raciocínio

        class Seq:
            vision = False

            def __init__(self, *outs):
                self.outs, self.msgs = list(outs), []

            def chat(self, messages, **kw):
                self.msgs.append(messages)
                return self.outs.pop(0)
        p = Seq("isto não é JSON", '{"ok": true}')
        o, _ = call_json(p, "s", 'x\nOutput JSON: {"ok": bool}', {})
        self.assertTrue(o["ok"])
        self.assertIn('Expected format: {"ok": bool}', p.msgs[1][-1]["content"])  # a nova tentativa repete o formato
        p = Seq("", '{"ok": true}')   # resposta VAZIA: a mesma pergunta é repetida (sem mensagem vazia da IA no meio)
        o, _ = call_json(p, "s", 'x\nOutput JSON: {"ok": bool}', {})
        self.assertEqual((o["ok"], p.msgs[1]), (True, p.msgs[0]))
        with self.assertRaises(ValueError) as cm:
            call_json(Seq("Claro! Segue a análise.", "Claro de novo."), "s", "x", {})
        self.assertIn("Claro de novo", str(cm.exception))  # o erro mostra o que a IA respondeu

    def test_errors_for_unusable_inputs(self):
        junk = self.tmp / "x.bin"
        junk.write_bytes(b"nada")
        with self.assertRaises(ValueError):
            AE.AutoEditPipeline(self.store, lambda e: None).run({"attachment_ids": [upload(self.store, junk)], "style": "vlog"})
        with self.assertRaises(ValueError):
            AE.AutoEditPipeline(self.store, lambda e: None).run({"attachment_ids": [], "style": "vlog"})


class StudioApi(ServerCase):
    def post(self, path, body=None, expect=200):
        s, r = self.c.json("POST", path, body or {})
        self.assertEqual(s, expect, r)
        return r

    def run_job(self, path, body):
        r = self.post(path, body)
        return self.c.sse(f"/api/jobs/{r['job_id']}/events")

    @needs_ff
    def test_manual_project_edit_on_the_timeline_import_cut_and_export_without_any_generation(self):
        p = self.post("/api/studio/projects", {"name": "Na mão", "origin": "manual", "duration_type": "custom", "target_seconds": 30, "aspect": "9:16"}, 201)
        pid, ep = p["id"], p["episodes"][0]
        self.assertEqual((p["origin"], p["aspect"], ep["status"], ep["scenes"], ep["timeline"]["clips"]), ("manual", "9:16", "ready", [], []))
        self.assertIsNone(self.c.json("GET", f"/api/studio/projects/{pid}/job")[1]["job_id"])        # nenhuma geração foi iniciada
        media = make_media(self.tmp)
        raw = media["game"].read_bytes()
        s, _h, a = self.c.req("POST", f"/api/studio/projects/{pid}/media", raw=raw, headers={"X-Filename": "game.mp4", "Content-Length": str(len(raw))})
        self.assertEqual(s, 201)
        full = self.c.json("GET", f"/api/studio/projects/{pid}")[1]
        vid = next(x for x in full["assets"] if x["kind"] == "video")
        vt = next(t["id"] for t in full["episodes"][0]["timeline"]["tracks"] if t["kind"] == "video")
        clips = [{"id": "c1", "track": vt, "asset": vid["id"], "start": 0, "dur": 4, "in": 2}, {"id": "c2", "track": vt, "asset": vid["id"], "start": 4, "dur": 3, "in": 12}]
        s, r = self.c.json("PUT", f"/api/studio/projects/{pid}/episodes/{ep['id']}/timeline", {"timeline": {"tracks": full["episodes"][0]["timeline"]["tracks"], "clips": clips}})
        self.assertEqual(s, 200, r)
        s, r = self.c.json("POST", f"/api/studio/projects/{pid}/episodes/{ep['id']}/export", {"mode": "video", "quality": "480p"})
        self.assertEqual(s, 200, r)
        ev = self.c.sse(f"/api/jobs/{r['job_id']}/events")
        self.assertTrue([e for e in ev if e.get("type") == "done"], ev[-3:])
        self.assertEqual(self.c.json("GET", f"/api/studio/projects/{pid}")[1]["episodes"][0]["scenes"], [])    # continua sem cenas geradas

    def test_meta_catalog(self):
        s, m = self.c.json("GET", "/api/studio/meta")
        self.assertEqual(s, 200)
        self.assertEqual([d["id"] for d in m["durations"]], ["shorts", "short", "long", "custom"])
        self.assertEqual([x["id"] for x in m["styles"]], ["realistic", "cartoon", "anime", "custom"])
        self.assertEqual(m["export_modes"], ["full", "video", "audio"])
        self.assertEqual([x["id"] for x in m["edit_styles"]][:3], ["gameplay", "documentary", "phonk"])
        self.assertEqual(m["stages"], ["receive", "analyze", "generate", "review", "deliver"])

    @needs_ff
    def test_generate_edit_export_all_modes_and_media(self):
        p = self.post("/api/studio/projects", {"name": "API", "kind": "series", "duration_type": "shorts", "target_seconds": 16, "style": "cartoon", "music": False, "prompt": "Um robô aprende a pintar. Ele pinta o céu."}, 201)
        pid, eid = p["id"], p["episodes"][0]["id"]
        self.assertEqual((p["duration_type"], p["style"], p["kind"]), ("shorts", "cartoon", "series"))
        ev = self.run_job(f"/api/studio/projects/{pid}/episodes/{eid}/generate", {})
        done = [e for e in ev if e["type"] == "done"]
        self.assertEqual(len(done), 1, ev[-3:])
        s, full = self.c.json("GET", f"/api/studio/projects/{pid}")
        ep = full["episodes"][0]
        self.assertEqual(ep["status"], "ready")
        # 409 enquanto gera é coberto pela guarda; aqui confirma que depois de terminar dá para gerar de novo
        # ---- edição: salvar a timeline (cortar, silenciar, apagar) pela API
        tl = ep["timeline"]
        v = [c for c in tl["clips"] if c["track"] == "t_v1"]
        first = v[0]
        cut = dict(first, id="cut_a", dur=round(first["dur"] / 2, 3))
        cut_b = dict(first, id="cut_b", start=round(first["start"] + cut["dur"], 3), dur=round(first["dur"] - cut["dur"], 3), mute=True)
        new = [c for c in tl["clips"] if c["id"] != first["id"]] + [cut, cut_b]
        s, r = self.c.json("PUT", f"/api/studio/projects/{pid}/episodes/{eid}/timeline", {"timeline": {**tl, "clips": new}})
        self.assertEqual(s, 200)
        ep = self.c.json("GET", f"/api/studio/projects/{pid}")[1]["episodes"][0]
        self.assertEqual({c["id"] for c in ep["timeline"]["clips"]} >= {"cut_a", "cut_b"}, True)
        self.assertTrue(next(c for c in ep["timeline"]["clips"] if c["id"] == "cut_b")["mute"])
        # ---- exportação: completo / somente vídeo / somente áudio
        got = {}
        for mode, ext in (("full", "mp4"), ("video", "mp4"), ("audio", "wav")):
            ev = self.run_job(f"/api/studio/projects/{pid}/episodes/{eid}/export", {"mode": mode, "quality": "480p", "format": "wav"})
            d = [e for e in ev if e["type"] == "done"]
            self.assertEqual(len(d), 1, (mode, ev[-2:]))
            self.assertTrue(d[0]["export"]["file"].endswith("." + ext))
            st, hd, body = self.c.req("GET", d[0]["url"])
            self.assertEqual(st, 200)
            f = Path(self.tmp) / f"exp_{mode}.{ext}"
            f.write_bytes(body)
            got[mode] = tools.probe(f)
        self.assertTrue(got["full"]["video"] and got["full"]["audio"])
        self.assertTrue(got["video"]["video"] and not got["video"]["audio"])
        self.assertTrue(got["audio"]["audio"] and not got["audio"]["video"])
        st, hd, part = self.c.req("GET", d[0]["url"], headers={"Range": "bytes=0-99"})
        self.assertEqual((st, len(part)), (206, 100))
        ep = self.c.json("GET", f"/api/studio/projects/{pid}")[1]["episodes"][0]
        self.assertEqual([x["mode"] for x in ep["exports"]], ["full", "video", "audio"])
        self.assertEqual(self.c.json("DELETE", f"/api/studio/projects/{pid}/exports/{ep['exports'][0]['file']}")[0], 200)
        # ---- mídia: enviar e apagar (some da timeline)
        from asta.canvas import procedural as proc

        s, h, body = self.c.req("POST", f"/api/studio/projects/{pid}/media", raw=proc.image("x", "64x64", 1), headers={"X-Filename": "foto.png", "Content-Length": str(len(proc.image('x', '64x64', 1)))})
        self.assertEqual(s, 201)
        rec = json.loads(body)
        self.assertEqual(rec["kind"], "image")
        self.assertEqual(self.c.req("GET", f"/api/studio/projects/{pid}/media/{rec['file']}")[0], 200)
        used = next(c for c in ep["timeline"]["clips"] if c["track"] == "t_v1")["asset"]
        self.assertEqual(self.c.json("DELETE", f"/api/studio/projects/{pid}/media/{used}")[0], 200)
        ep = self.c.json("GET", f"/api/studio/projects/{pid}")[1]["episodes"][0]
        self.assertFalse(any(c["asset"] == used for c in ep["timeline"]["clips"]))
        # ---- série: novo episódio / projeto único recusa
        self.post(f"/api/studio/projects/{pid}/episodes", {"title": "Dois", "prompt": "continua"}, 201)
        self.assertEqual(len(self.c.json("GET", f"/api/studio/projects/{pid}")[1]["episodes"]), 2)
        single = self.post("/api/studio/projects", {"name": "U", "kind": "single"}, 201)
        s, r = self.c.json("POST", f"/api/studio/projects/{single['id']}/episodes", {})
        self.assertEqual(s, 400)
        self.assertEqual(self.c.json("DELETE", f"/api/studio/projects/{pid}")[0], 200)
        self.assertEqual(self.c.json("GET", f"/api/studio/projects/{pid}")[0], 404)

    def test_validation_and_empty_timeline_errors(self):
        p = self.post("/api/studio/projects", {"name": "V"}, 201)
        pid, eid = p["id"], p["episodes"][0]["id"]
        s, r = self.c.json("POST", f"/api/studio/projects/{pid}/episodes/{eid}/generate", {})
        self.assertEqual(s, 400)                                                        # sem prompt nem premissa
        if FF:
            ev = self.run_job(f"/api/studio/projects/{pid}/episodes/{eid}/export", {"mode": "full"})
            self.assertTrue([e for e in ev if e["type"] == "error" and "vazia" in e["message"]])
        self.assertEqual(self.c.json("POST", "/api/studio/autoedit", {})[0], 400)
        self.assertEqual(self.c.json("GET", "/api/studio/projects/nao_existe")[0], 404)
        s, h, b = self.c.req("POST", f"/api/studio/projects/{pid}/media", raw=b"nao e midia", headers={"X-Filename": "x.txt", "Content-Length": "11"})
        self.assertEqual(s, 400)
        self.assertEqual(self.c.json("POST", f"/api/studio/projects/{pid}/meta", {"duration_type": "long", "target_seconds": 4000, "style": "anime"})[1]["duration_type"], "long")
        self.assertEqual(self.c.json("POST", f"/api/studio/projects/{pid}/meta", {"target_seconds": 9000})[1]["duration_type"], "custom")

    @needs_ff
    def test_autoedit_endpoint_creates_a_project_with_the_timeline(self):
        m = make_media(Path(self.tmp))
        ids = []
        for k in ("game", "music"):
            data = m[k].read_bytes()
            s, h, body = self.c.req("POST", "/api/uploads", raw=data, headers={"X-Filename": m[k].name, "Content-Type": "application/octet-stream", "Content-Length": str(len(data))})
            self.assertEqual(s, 200, body)
            ids.append(json.loads(body)["id"])
        ev = self.run_job("/api/studio/autoedit", {"attachment_ids": ids, "style": "phonk", "prompt": "edit dos melhores momentos", "target_seconds": 12})
        done = [e for e in ev if e["type"] == "done"]
        self.assertEqual(len(done), 1, ev[-3:])
        self.assertEqual(done[0]["style"], "phonk")
        p = self.c.json("GET", f"/api/studio/projects/{done[0]['project_id']}")[1]
        self.assertEqual((p["episodes"][0]["origin"], p["aspect"]), ("autoedit", "9:16"))


if __name__ == "__main__":
    unittest.main()
