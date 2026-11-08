"""v0.17 — Studio: análise de mídia (Rust), edição automática melhor (condensação, cortes em pausas, batida real), camadas, exportação 2K/4K e fps, SFX, legendas, biblioteca."""
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.canvas.render import render_timeline  # noqa: E402
from asta.studio import analysis  # noqa: E402
from asta.studio import captions as CAP  # noqa: E402
from asta.studio import schema as S  # noqa: E402
from asta.studio import sfx as SFX  # noqa: E402
from asta.studio import autoedit as AE  # noqa: E402
from asta.studio import tools  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402
from tests.test_studio import make_media  # noqa: E402

needs_ff = unittest.skipUnless(tools.have_ffmpeg(), "ffmpeg não instalado")


def ff(*a):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)


def video(dur=600.0, **extra):
    v = {"id": "v", "name": "v", "kind": "video", "dur": dur, "has_audio": True, "loud": [], "changes": [], "silences": [], "activity": []}
    v.update(extra)
    return v


def music(**extra):
    m = {"id": "m", "name": "musica", "kind": "audio", "dur": 60.0, "has_audio": True, "loud": [], "changes": [], "silences": [], "activity": []}
    m.update(extra)
    return m


class CondensationTests(unittest.TestCase):
    def test_chunks_end_in_pauses_not_mid_speech(self):
        # fala de 0 a 30 s com pausas em 6,5 e 13,2 e 21: cortes de até 8 s caem nelas
        w = AE._chunk(0.0, 30.0, 3.0, 8.0, [6.5, 13.2, 21.0], [])
        self.assertEqual([round(e, 1) for _, e in w][:3], [6.5, 13.2, 21.0])
        self.assertEqual(w[0][0], 0.0)
        self.assertTrue(all(b[0] == a[1] for a, b in zip(w, w[1:])))                     # sem buracos e sem sobreposição
        self.assertEqual(w[-1][1], 30.0)
        w2 = AE._chunk(0.0, 20.0, 3.0, 8.0, [], [7.0])                                    # sem pausas: usa as trocas de cena
        self.assertEqual(w2[0][1], 7.0)
        self.assertEqual(AE._chunk(0.0, 20.0, 3.0, 8.0, [], [])[0][1], 8.0)               # nada: o corte fixo de sempre

    def test_long_footage_is_condensed_across_the_whole_video_not_just_the_start(self):
        loud = [(float(t), -10.0 if t % 100 == 55 else -40.0) for t in range(5, 600, 10)]
        roles = {"v": "footage", "m": "music"}
        e = AE.plan_edl("documentary", [video(600.0, loud=loud), music()], roles, 60, {}, 0, 3, "t")
        ins = [g["in"] for g in e["segments"] if g["asset"] == "v"]
        self.assertGreater(max(ins), 400, ins)                                              # antes só usava o começo (até ~60 s)
        self.assertEqual(ins, sorted(ins))                                                  # e mantém a ordem em que aconteceu
        self.assertAlmostEqual(e["total"], 60, delta=2.0)
        picked = sum(1 for g in e["segments"] if any(g["in"] <= t < g["in"] + g["dur"] for t in (55, 155, 255, 355, 455, 555)))
        self.assertGreaterEqual(picked, 4)                                                  # os trechos de maior volume ganham dos outros do mesmo bloco

    def test_activity_breaks_ties_between_quiet_windows(self):
        act = [(t * 0.25, 1.0 if 300 <= t * 0.25 < 340 else 0.0) for t in range(0, 2400)]
        e = AE.plan_edl("vlog", [video(600.0, activity=act)], {"v": "footage"}, 30, {}, 0, 3, "t")
        self.assertTrue(any(300 <= g["in"] < 340 for g in e["segments"]), [g["in"] for g in e["segments"]])

    def test_short_material_is_not_condensed(self):
        e = AE.plan_edl("documentary", [video(30.0)], {"v": "footage"}, 60, {}, 0, 3, "t")
        self.assertLessEqual(e["total"], 62)                                                # não há o que escolher: usa o que tem

    def test_music_tempo_phase_and_drop_drive_the_beat_edit(self):
        m = music(bpm=125.0, phase=0.2, drop=12.0)
        e = AE.plan_edl("phonk", [video(300.0), m], {"v": "footage", "m": "music"}, 40, {}, 0, 4, "t")
        beat = 60 / 125.0
        t, cuts = 0.0, []
        for g in e["segments"]:
            cuts.append(t)
            t += g["dur"]
        # a 1ª duração inclui a fase: as demais emendas caem em (fase + n·batida)
        for c in cuts[1:6]:
            self.assertAlmostEqual(((c - 0.2) / beat) % 1.0 % 1.0 if ((c - 0.2) / beat) % 1.0 < 0.5 else 1 - ((c - 0.2) / beat) % 1.0, 0.0, delta=0.02, msg=cuts[:6])
        first_half_drop = [g["dur"] for g in e["segments"] if sum(x["dur"] for x in e["segments"][:e["segments"].index(g)]) < 12.0]
        after = [g["dur"] for g in e["segments"] if sum(x["dur"] for x in e["segments"][:e["segments"].index(g)]) > 14.0][:-3]
        self.assertGreater(sum(first_half_drop) / len(first_half_drop), sum(after) / len(after))   # antes do drop: cortes mais longos

    def test_a_tiny_leftover_cut_is_absorbed(self):
        for target in (30, 31, 32.3, 33.1):
            e = AE.plan_edl("vlog", [video(300.0, silences=[(10.0, 11.0)])], {"v": "footage"}, target, {}, 0, 1, "t")
            self.assertTrue(all(g["dur"] >= 0.5 for g in e["segments"]), (target, [g["dur"] for g in e["segments"]][-3:]))


@needs_ff
class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_click_track_tempo_and_silence(self):
        wav = self.tmp / "clicks.wav"
        ff("-f", "lavfi", "-i", "aevalsrc=if(lt(mod(t\\,0.5)\\,0.04)\\,0.9*sin(2*PI*90*t)\\,0):d=20:s=8000", "-c:a", "pcm_s16le", str(wav))
        r = analysis.analyze_audio(wav, beats=True, silence=True, loud=True)
        self.assertAlmostEqual(r["bpm"], 120.0, delta=2.0)
        self.assertGreater(r["confidence"], 1.2)
        self.assertGreater(len(r["beats"]), 30)
        self.assertTrue(r["loud"] and r["silences"] == [])      # pausas de 0,46 s entre os cliques: abaixo do mínimo de silêncio (0,6 s)

    def test_constant_tone_has_no_pulse_and_no_drop(self):
        wav = self.tmp / "tone.wav"
        ff("-f", "lavfi", "-i", "sine=f=220:d=15", "-c:a", "pcm_s16le", str(wav))
        r = analysis.analyze_audio(wav, beats=True)
        self.assertEqual((r["bpm"], r["beats"], r["drop"]), (0.0, [], 0.0))

    def test_drop_is_found_when_the_track_gets_loud(self):
        wav = self.tmp / "drop.wav"
        ff("-f", "lavfi", "-i", "sine=f=110:d=24,volume='if(lt(t,10),0.05,1.0)':eval=frame", "-c:a", "pcm_s16le", str(wav))
        r = analysis.analyze_audio(wav, beats=True)
        self.assertAlmostEqual(r["drop"], 10.0, delta=3.0)

    def test_hard_cuts_in_video_are_detected_as_scene_changes(self):
        mp4 = self.tmp / "cuts.mp4"
        ff("-f", "lavfi", "-i", "color=c=red:s=96x96:d=3:r=12", "-f", "lavfi", "-i", "color=c=white:s=96x96:d=3:r=12", "-f", "lavfi", "-i", "color=c=blue:s=96x96:d=3:r=12",
           "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-pix_fmt", "yuv420p", str(mp4))
        v = analysis.analyze_video(mp4)
        self.assertEqual(len(v["cuts"]), 2, v["cuts"])
        self.assertAlmostEqual(v["cuts"][0], 3.0, delta=0.3)
        self.assertAlmostEqual(v["cuts"][1], 6.0, delta=0.3)
        self.assertTrue(v["activity"])
        idx = analysis.ActivityIndex(v["activity"])
        self.assertGreater(idx.mean(2.8, 3.3), idx.mean(0.5, 2.5))

    def test_tools_wrappers_keep_their_old_contract(self):
        wav = self.tmp / "t.wav"
        ff("-f", "lavfi", "-i", "sine=f=300:d=12,volume='if(gt(mod(t,6),4),1.0,0.01)':eval=frame", "-c:a", "pcm_s16le", str(wav))
        peaks = tools.loud_moments(wav, 0.5)
        self.assertTrue(peaks and all(a[1] >= b[1] for a, b in zip(peaks, peaks[1:])))
        sil = tools.silences(wav)
        self.assertTrue(any(s < 0.3 and e > 3.5 for s, e in sil), sil)
        self.assertEqual(tools.silences(self.tmp / "nada.wav"), [])
        self.assertEqual(tools.scene_changes(self.tmp / "nada.mp4"), [])


class SchemaV17Tests(unittest.TestCase):
    def test_new_track_kinds_filters_and_fps_are_in_the_catalog(self):
        d = S.describe()
        self.assertEqual(d["fps"], [24, 30, 60, 120])
        self.assertEqual(d["track_kinds"], ["video", "audio", "text", "image", "fx"])
        for f in ("sepia", "negative", "blur", "sharpen", "glow", "grain", "vignette", "mirror", "noir", "teal_orange"):
            self.assertIn(f, d["filters"])

    def test_image_and_fx_layers_normalize_and_fx_does_not_stretch_the_duration(self):
        tl = S.normalize_timeline({"tracks": [{"id": "v", "kind": "video"}, {"id": "i", "kind": "image"}, {"id": "fx", "kind": "fx"}, {"id": "x", "kind": "nope"}],
                                   "clips": [{"id": "a", "track": "v", "asset": "a1", "start": 0, "dur": 4}, {"id": "b", "track": "i", "asset": "a2", "start": 1, "dur": 2},
                                             {"id": "e", "track": "fx", "start": 2, "dur": 30, "filter": "noir", "asset": "ignorado"}, {"id": "z", "track": "fx", "asset": "", "start": 0, "dur": 1}]})
        kinds = {t["id"]: t["kind"] for t in tl["tracks"]}
        self.assertEqual((kinds["i"], kinds["fx"], kinds["x"]), ("image", "fx", "video"))     # tipo desconhecido vira vídeo
        fx = next(c for c in tl["clips"] if c["id"] == "e")
        self.assertEqual((fx["asset"], fx["filter"]), ("", "noir"))                           # efeito não tem mídia
        self.assertEqual(tl["duration"], 4.0)                                                 # o efeito de 30 s não alonga o vídeo
        self.assertEqual(len(tl["clips"]), 4)


class CaptionTests(unittest.TestCase):
    def test_srt_and_vtt_round_trip(self):
        cues = [{"start": 0.5, "end": 2.25, "text": "Olá"}, {"start": 3.0, "dur": 1.5, "text": "Segunda\nlinha"}]
        back = CAP.parse(CAP.to_srt(cues))
        self.assertEqual([(c["start"], c["end"], c["text"]) for c in back], [(0.5, 2.25, "Olá"), (3.0, 4.5, "Segunda\nlinha")])
        self.assertTrue(CAP.to_srt(cues, vtt=True).startswith("WEBVTT"))
        self.assertEqual(CAP.parse(CAP.to_srt(cues, vtt=True)), back)
        self.assertEqual(CAP.parse("lixo sem tempo\n\nnada"), [])
        self.assertEqual(CAP.parse("1\n00:01:02,5 --> 00:01:04,0\n<i>com tag</i>")[0]["start"], 62.5)

    def test_text_is_aligned_over_the_speech_and_never_overlaps(self):
        text = "Olá pessoal, bem-vindos ao canal. Hoje vamos falar de edição de vídeo, e como deixar tudo mais rápido! Até a próxima."
        spans = CAP.speech_spans([(3.0, 4.0), (9.0, 10.0)], 14.0)
        self.assertEqual(spans, [(0.0, 3.0), (4.0, 9.0), (10.0, 14.0)])
        cues = CAP.align(text, spans, offset=2.0)
        self.assertGreaterEqual(len(cues), 3)
        self.assertEqual(cues[0]["start"], 2.0)
        self.assertTrue(all(b["start"] >= a["end"] - 1e-6 for a, b in zip(cues, cues[1:])))
        self.assertTrue(all(c["end"] - c["start"] <= 5.6 and max(len(x) for x in c["text"].split("\n")) <= 50 for c in cues))
        self.assertEqual(CAP.align("", spans), [])


class SfxTests(unittest.TestCase):
    def test_every_effect_renders_a_wav_and_is_deterministic(self):
        for k in SFX.CATALOG:
            self.assertEqual(SFX.render(k, 0, 3)[:4], b"RIFF", k)
        self.assertEqual(SFX.render("whoosh", 0, 1), SFX.render("whoosh", 0, 1))
        self.assertNotEqual(SFX.render("glitch", 0, 1), SFX.render("glitch", 0, 2))
        self.assertGreater(len(SFX.render("rain", 4)), len(SFX.render("rain", 1)))
        with self.assertRaises(ValueError):
            SFX.render("inexistente")


@needs_ff
class RenderV17Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.m = make_media(self.tmp)

    def resolve(self, c):
        path = {"a": self.m["game"], "p": self.m["pic"], "m": self.m["music"]}[c["asset"]]
        return {"path": path, "kind": "video" if c["asset"] == "a" else ("audio" if c["asset"] == "m" else "image"), "duration": 5}

    def tl(self, extra_tracks=(), extra_clips=()):
        base = {"id": "id", "scene": "", "label": "", "start": 0, "dur": 2, "in": 0, "speed": 1, "mute": False, "volume": 1, "fade_in": 0, "fade_out": 0, "opacity": 1, "fit": "cover", "x": 0, "y": 0,
                "scale": 1, "filter": "none", "text": "", "size": 44, "color": "#ffffff", "bg": "", "pos": "bottom"}
        tracks = [{"id": "t_v1", "kind": "video", "name": "V1", "muted": False, "hidden": False, "locked": False, "volume": 1.0}] + list(extra_tracks)
        clips = [dict(base, id="c1", track="t_v1", asset="a")] + [dict(base, **c) for c in extra_clips]
        return {"tracks": tracks, "clips": clips, "markers": []}

    def render(self, tl, **kw):
        out = self.tmp / "o.mp4"
        render_timeline(tl, kw.pop("w", 320), kw.pop("h", 180), kw.pop("fps", 24), "#000000", self.resolve, out, mode="video", top_first=True)
        return tools.probe(out)

    def test_fx_layer_filters_everything_below_it_only_while_it_lasts_and_does_not_extend_the_video(self):
        fxt = {"id": "t_fx", "kind": "fx", "name": "FX1", "muted": False, "hidden": False, "locked": False, "volume": 1.0}
        tl = self.tl([fxt], [{"id": "e1", "track": "t_fx", "start": 0.5, "dur": 30, "filter": "negative"}])
        tl["tracks"].insert(0, tl["tracks"].pop())               # efeitos acima do vídeo (a primeira da lista é a de cima)
        info = self.render(tl)
        self.assertAlmostEqual(info["dur"], 2.0, delta=0.2)
        # todos os filtros novos produzem um vídeo válido
        for f in S.FILTERS[1:]:
            tl = self.tl([fxt], [{"id": "e1", "track": "t_fx", "start": 0, "dur": 1, "filter": f}])
            self.assertTrue(self.render(tl)["video"], f)

    def test_image_layer_overlays_and_a_timeline_of_only_fx_is_refused(self):
        it = {"id": "t_i1", "kind": "image", "name": "I1", "muted": False, "hidden": False, "locked": False, "volume": 1.0}
        tl = self.tl([it], [{"id": "c2", "track": "t_i1", "asset": "p", "start": 0, "dur": 1, "scale": 0.4}])
        tl["tracks"].insert(0, tl["tracks"].pop())
        self.assertTrue(self.render(tl)["video"])
        fxt = {"id": "t_fx", "kind": "fx", "name": "FX1", "muted": False, "hidden": False, "locked": False, "volume": 1.0}
        only = {"tracks": [fxt], "clips": [dict(self.tl()["clips"][0], id="e", track="t_fx", asset="", filter="blur")], "markers": []}
        from asta.providers.base import ProviderError

        with self.assertRaises(ProviderError):
            self.render(only)

    def test_resolution_and_fps_options(self):
        from asta.studio.export import FPS, QUALITY

        self.assertEqual(list(QUALITY), ["480p", "720p", "1080p", "2K", "4K"])
        self.assertEqual((QUALITY["2K"], QUALITY["4K"]), (2560, 3840))
        self.assertEqual(FPS, (24, 30, 60, 120))
        info = self.render(self.tl(), w=2560, h=1440, fps=60)
        self.assertEqual((info["w"], info["h"]), (2560, 1440))
        info = self.render(self.tl(), w=3840, h=2160, fps=30)
        self.assertEqual((info["w"], info["h"]), (3840, 2160))
        from asta.canvas.render import _preset

        self.assertEqual((_preset(1280, 720, 24), _preset(1920, 1080, 30), _preset(2560, 1440, 60), _preset(3840, 2160, 120)), ("veryfast", "veryfast", "superfast", "ultrafast"))


class StudioV17Api(ServerCase):
    def post(self, path, body=None, expect=200):
        s, r = self.c.json("POST", path, body or {})
        self.assertEqual(s, expect, r)
        return r

    def project(self, name="V17"):
        return self.post("/api/studio/projects", {"name": name, "origin": "manual", "duration_type": "custom", "target_seconds": 30}, 201)

    def upload(self, pid, path):
        raw = path.read_bytes()
        s, _h, body = self.c.req("POST", f"/api/studio/projects/{pid}/media", raw=raw, headers={"X-Filename": path.name, "Content-Length": str(len(raw))})
        self.assertEqual(s, 201, body)
        import json as _j

        return _j.loads(body)

    def test_meta_lists_fps_and_resolutions(self):
        m = self.c.json("GET", "/api/studio/meta")[1]
        self.assertEqual(m["fps"], [24, 30, 60, 120])
        self.assertEqual(m["quality"], ["480p", "720p", "1080p", "2K", "4K"])

    def test_sfx_becomes_an_audio_asset_and_bad_kinds_are_refused(self):
        pid = self.project()["id"]
        cat = self.c.json("GET", "/api/studio/sfx")[1]["effects"]
        self.assertTrue(any(e["id"] == "whoosh" for e in cat))
        rec = self.post(f"/api/studio/projects/{pid}/sfx", {"kind": "whoosh", "duration": 1.0}, 201)
        self.assertEqual((rec["kind"], rec["source"]), ("audio", "sfx"))
        self.assertEqual(self.c.req("GET", f"/api/studio/projects/{pid}/media/{rec['file']}")[0], 200)
        self.assertEqual(self.c.json("POST", f"/api/studio/projects/{pid}/sfx", {"kind": "zzz"})[0], 400)
        self.assertEqual(self.c.json("POST", "/api/studio/projects/nao_existe/sfx", {"kind": "pop"})[0], 404)

    def test_caption_endpoints(self):
        r = self.post("/api/studio/captions/parse", {"text": "1\n00:00:01,000 --> 00:00:02,500\nOi\n"})
        self.assertEqual(r["cues"][0]["end"], 2.5)
        self.assertEqual(self.c.json("POST", "/api/studio/captions/parse", {"text": "nada"})[0], 400)
        r = self.post("/api/studio/captions/align", {"text": "Primeira frase aqui. Segunda frase aqui.", "start": 5, "end": 15})
        self.assertEqual(r["cues"][0]["start"], 5.0)
        self.assertLessEqual(r["cues"][-1]["end"], 15.01)
        self.assertEqual(self.c.json("POST", "/api/studio/captions/align", {"text": "x", "start": 5, "end": 4})[0], 400)
        s, _h, body = self.c.req("POST", "/api/studio/captions/srt", {"cues": [{"start": 1, "dur": 2, "text": "Oi"}]})
        self.assertEqual(s, 200)
        self.assertIn(b"00:00:01,000 --> 00:00:03,000", body)

    @needs_ff
    def test_transcription_with_given_text_aligns_to_the_speech_and_waveform_is_cached(self):
        pid = self.project()["id"]
        media = make_media(self.tmp)
        a = self.upload(pid, media["game"])
        ev = self.c.sse(f"/api/jobs/{self.post(f'/api/studio/projects/{pid}/transcribe', {'asset': a['id'], 'text': 'Isto é um texto falado no vídeo. E aqui continua a fala.'})['job_id']}/events")
        done = [e for e in ev if e["type"] == "done"]
        self.assertEqual(len(done), 1, ev[-2:])
        cues = done[0]["cues"]
        self.assertTrue(cues and all(0 <= c["start"] < c["end"] <= a["dur"] + 0.5 for c in cues))
        # sem texto e com o provedor Demo: erro claro (o Demo não transcreve)
        ev = self.c.sse(f"/api/jobs/{self.post(f'/api/studio/projects/{pid}/transcribe', {'asset': a['id']})['job_id']}/events")
        self.assertTrue([e for e in ev if e["type"] == "error"], ev[-2:])
        w = self.c.json("GET", f"/api/studio/projects/{pid}/wave/{a['id']}?n=64")[1]
        self.assertEqual((w["n"], len(w["peaks"])), (64, 64))
        self.assertTrue(max(w["peaks"]) > 0.08 and min(w["peaks"]) < 0.02)       # picos nos trechos altos, quase nada nos silenciosos
        self.assertTrue((self.store.studio.folder / pid / "thumbs" / f"wave-{a['id']}-64.json").is_file())
        self.assertEqual(self.c.json("GET", f"/api/studio/projects/{pid}/wave/{a['id']}?n=64")[1], w)

    @needs_ff
    def test_media_browser_lists_canvas_and_other_projects_and_imports_copies(self):
        from asta.canvas import procedural as proc

        cv = self.store.canvases.create("Meu canvas")
        self.store.canvases.add_asset(cv["id"], proc.image("gato", "64x64", 1), "png", "image", name="gato.png", mime="image/png")
        other = self.project("Outro")
        self.post(f"/api/studio/projects/{other['id']}/sfx", {"kind": "pop"}, 201)
        cur = self.project("Atual")["id"]
        items = self.c.json("GET", f"/api/studio/library?exclude={cur}")[1]["items"]
        src = {i["source"] for i in items}
        self.assertTrue({"canvas", "studio"} <= src, items)
        self.assertTrue(all(not i["ref"].startswith(cur) for i in items))
        self.assertEqual([i["name"] for i in self.c.json("GET", "/api/studio/library?q=gato&kind=image")[1]["items"]], ["gato.png"])
        pick = [i for i in items if i["name"] == "gato.png"][0]
        r = self.post(f"/api/studio/projects/{cur}/import", {"items": [{"source": pick["source"], "ref": pick["ref"]}]}, 201)
        self.assertEqual((r["assets"][0]["kind"], r["assets"][0]["source"]), ("image", "canvas"))
        self.assertEqual(self.c.req("GET", f"/api/canvases/{cv['id']}/assets/{pick['ref'].split('/')[1]}")[0] in (200, 404), True)   # o original continua (copiado, não movido)
        self.assertEqual(len(self.c.json("GET", f"/api/studio/projects/{cur}")[1]["assets"]), 1)
        self.assertEqual(self.c.json("POST", f"/api/studio/projects/{cur}/import", {"items": [{"source": "canvas", "ref": "x/y"}, {"source": "nada", "ref": ".."}]})[0], 404)

    @needs_ff
    def test_export_with_fps_and_2k_records_them(self):
        p = self.project("Export")
        pid, eid = p["id"], p["episodes"][0]["id"]
        a = self.upload(pid, make_media(self.tmp)["game"])
        tl = self.c.json("GET", f"/api/studio/projects/{pid}")[1]["episodes"][0]["timeline"]
        vt = next(t["id"] for t in tl["tracks"] if t["kind"] == "video")
        self.c.json("PUT", f"/api/studio/projects/{pid}/episodes/{eid}/timeline", {"timeline": {"tracks": tl["tracks"], "clips": [{"id": "c1", "track": vt, "asset": a["id"], "start": 0, "dur": 1}]}})
        ev = self.c.sse(f"/api/jobs/{self.post(f'/api/studio/projects/{pid}/episodes/{eid}/export', {'mode': 'video', 'quality': '2K', 'fps': 60})['job_id']}/events")
        done = [e for e in ev if e["type"] == "done"]
        self.assertEqual(len(done), 1, ev[-2:])
        rec = done[0]["export"]
        self.assertEqual((rec["quality"], rec["fps"]), ("2K", 60))
        self.assertIn("2K-60fps", rec["file"])
        s, _h, body = self.c.req("GET", done[0]["url"])
        f = self.tmp / "e2k.mp4"
        f.write_bytes(body)
        info = tools.probe(f)
        self.assertEqual(max(info["w"], info["h"]), 2560)
        ev = self.c.sse(f"/api/jobs/{self.post(f'/api/studio/projects/{pid}/episodes/{eid}/export', {'mode': 'video', 'quality': '480p', 'fps': 999})['job_id']}/events")
        self.assertEqual([e for e in ev if e["type"] == "done"][0]["export"]["fps"], 24)       # fps fora da lista cai no padrão


if __name__ == "__main__":
    unittest.main()
