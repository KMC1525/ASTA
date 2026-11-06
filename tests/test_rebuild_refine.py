"""Rebuild multi-agente: limpeza, Perfilador, Polidor em lotes pequenos, Auditor e a trava estrutural (com um provedor falso, sem rede)."""
import copy
import json
import re
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from asta.rebuild import refine as R
from asta.rebuild.pipeline import RebuildPipeline
from tests import rebuild_fixtures as F
from tests.test_server import ServerCase


class Validators(unittest.TestCase):
    def test_clean_removes_engine_codes_and_fixes_mojibake(self):
        self.assertEqual(R.clean_text("\\C[2]Olá\\C[0], \\N[1]!  Tudo{w} bem?"), "Olá, ! Tudo bem?")
        self.assertEqual(R.clean_text("VocÃª jÃ¡ viu?"), "Você já viu?")
        self.assertEqual(R.clean_text("Texto normal."), "Texto normal.")
        self.assertEqual(R.clean_text("{i}Oi{/i} {color=#f00}vermelho{/color}"), "Oi vermelho")

    def test_rough_detection(self):
        for t in ("OLA TUDO BEM COM VOCE", "oi , tudo bem ?", "aaaaaaa que susto", "texto ### estranho", "Uma frase longa demais sem nenhuma pontuacao no final dela mesmo"):
            self.assertTrue(R.looks_rough(t), t)
        for t in ("Olá, tudo bem?", "Sim.", "ok", "Boa sorte, herói."):
            self.assertFalse(R.looks_rough(t), t)

    def test_accept_line_only_accepts_proofreading(self):
        old = "OLA {player}, voce tem 3 pocoes?"
        self.assertEqual(R.accept_line(old, "Olá {player}, você tem 3 poções?"), "Olá {player}, você tem 3 poções?")
        self.assertIsNone(R.accept_line(old, "Hello {player}, do you have 3 potions?"))  # traduziu
        self.assertIsNone(R.accept_line(old, "Olá, você tem 3 poções?"))  # perdeu o marcador
        self.assertIsNone(R.accept_line(old, "Olá {player}, você tem 4 poções?"))  # mudou número
        self.assertIsNone(R.accept_line(old, old))  # igual
        self.assertIsNone(R.accept_line(old, "Olá {player}, você tem 3 poções? " + "bla " * 30))  # cresceu demais
        self.assertIsNone(R.accept_line(old, ""))
        self.assertIsNone(R.accept_line(old, None))
        self.assertIsNone(R.accept_line("Oi\nTudo?", "Oi Tudo?"))  # quebra de linha
        self.assertIsNone(R.accept_line("MUITO BEM AGORA", "Aqui está: Muito bem agora"))

    def test_accept_name(self):
        self.assertEqual(R.accept_name("EV012", " Velha do mercado "), "Velha do mercado")
        for bad in ("EV013", "", "x", "a" * 40, "<b>x</b>", None, 5):
            self.assertIsNone(R.accept_name("EV012", bad))


def rpg_spec():
    ev = lambda i, name, text: {"id": i, "kind": "npc", "x": 1, "y": 1, "name": name, "trigger": "action", "pages": [{"if": "", "commands": [{"c": "say", "who": name, "text": text}]}]}
    return {"genre": "rpg", "title": "T", "language": "pt-BR", "data": {"party": [{"id": "a", "name": "Aria"}], "maps": {"m1": {"id": "m1", "name": "Map001", "tiles": ["..."], "events": [
        ev("e1", "EV001", "OLA VIAJANTE BEM VINDO A VILA"), ev("e2", "Guarda", "Tudo bem por aqui."), ev("e3", "", "Voce ja viu o dragao ?")]}}}}


class FakeAgents:
    """Imita o Runner._agent: responde conforme o agente; `script` troca as respostas."""

    def __init__(self, polish=None, profile=None, audit=None, fail_batches=0):
        self.polish, self.profile, self.audit, self.fail_batches = polish or {}, profile, audit, fail_batches
        self.calls = []
        self.steps = []

    def step(self, sid, status, **d):
        self.steps.append((sid, status))

    def agent(self, step, name, instruction, payload, fallback, **kw):
        self.calls.append((name, payload))
        if name == "rebuild_profiler":
            return (self.profile if self.profile is not None else {"summary": "s", "tone": "leve", "setting": "vila", "names": []}), False
        if name == "rebuild_polisher":
            if self.fail_batches and len(payload["lines"]) > 1:
                self.fail_batches -= 1
                return fallback(payload), True
            return {"lines": [{"id": x["id"], "text": self.polish.get(x["text"], x["text"])} for x in payload["lines"]]}, False
        return (self.audit or {"reject": []}), False


def run_refiner(spec, fake, **kw):
    warns = []
    ref = R.Refiner(fake.agent, fake.step, lambda: None, warns.append, **kw)
    return ref.run(spec, {"engine_name": "RPG Maker MV"}), warns


class RefinerTests(unittest.TestCase):
    def test_names_and_polish_are_applied_and_structure_is_untouched(self):
        spec = rpg_spec()
        fp = R.fingerprint(spec)
        units = R.collect_units(spec)
        ev1 = next(u for u in units if u.kind == "event" and u.text == "EV001")
        mp = next(u for u in units if u.kind == "map")
        fake = FakeAgents(polish={"OLA VIAJANTE BEM VINDO A VILA": "Olá, viajante! Bem-vindo à vila.", "Voce ja viu o dragao ?": "Você já viu o dragão?"},
                          profile={"summary": "x", "tone": "t", "setting": "s", "names": [{"id": ev1.id, "name": "Moça da vila"}, {"id": mp.id, "name": "Vila inicial"}, {"id": 999, "name": "Fantasma"}, {"id": ev1.id + 1, "name": "x"}]})
        stats, warns = run_refiner(spec, fake)
        ev = spec["data"]["maps"]["m1"]["events"]
        self.assertEqual(spec["data"]["maps"]["m1"]["name"], "Vila inicial")
        self.assertEqual(ev[0]["name"], "Moça da vila")
        self.assertEqual(ev[0]["pages"][0]["commands"][0]["text"], "Olá, viajante! Bem-vindo à vila.")
        self.assertEqual(ev[2]["pages"][0]["commands"][0]["text"], "Você já viu o dragão?")
        self.assertEqual(ev[1]["pages"][0]["commands"][0]["text"], "Tudo bem por aqui.")  # já estava bom: nem foi enviado
        self.assertEqual((stats["named"], stats["polished"], stats["reverted"]), (2, 2, False))
        self.assertEqual(R.fingerprint(spec), fp)
        sent = [p for n, p in fake.calls if n == "rebuild_polisher"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(sent[0]["lines"]), 2)
        self.assertEqual([s for s in fake.steps if s[1] != "running"], [("profiler", "done"), ("polisher", "done"), ("auditor", "done")])

    def test_bad_model_output_keeps_the_original(self):
        spec = rpg_spec()
        before = copy.deepcopy(spec)
        fake = FakeAgents(polish={"OLA VIAJANTE BEM VINDO A VILA": "Hello traveler, welcome to the village.", "Voce ja viu o dragao ?": "Você ainda não viu o dragão? Cuidado com ele!"},
                          profile={"names": [{"id": 1, "name": "<script>"}, {"id": "x"}, "lixo", None]})
        stats, _ = run_refiner(spec, fake)
        self.assertEqual(spec, before)
        self.assertEqual((stats["polished"], stats["named"]), (0, 0))

    def test_failed_batch_is_retried_line_by_line(self):
        spec = rpg_spec()
        fake = FakeAgents(polish={"OLA VIAJANTE BEM VINDO A VILA": "Olá, viajante! Bem-vindo à vila.", "Voce ja viu o dragao ?": "Você já viu o dragão?"}, fail_batches=1)
        stats, _ = run_refiner(spec, fake)
        sent = [len(p["lines"]) for n, p in fake.calls if n == "rebuild_polisher"]
        self.assertEqual(sent, [2, 1, 1])
        self.assertEqual(stats["polished"], 2)

    def test_auditor_can_revert_changes(self):
        spec = rpg_spec()
        fake = FakeAgents(polish={"OLA VIAJANTE BEM VINDO A VILA": "Olá, viajante! Bem-vindo à vila.", "Voce ja viu o dragao ?": "Você já viu o dragão?"})
        first = next(u for u in R.collect_units(spec) if u.kind == "line" and u.text.startswith("OLA"))
        fake.audit = {"reject": [first.id, "x", 12345]}
        stats, _ = run_refiner(spec, fake)
        self.assertEqual(spec["data"]["maps"]["m1"]["events"][0]["pages"][0]["commands"][0]["text"], "OLA VIAJANTE BEM VINDO A VILA")
        self.assertEqual((stats["rejected"], stats["polished"]), (1, 1))

    def test_call_budget_is_respected(self):
        spec = rpg_spec()
        fake = FakeAgents()
        stats, warns = run_refiner(spec, fake, max_calls=1)  # só o Perfilador cabe
        self.assertEqual(stats["calls"], 1)
        self.assertTrue(any("limite" in w for w in warns))

    def test_structure_change_reverts_everything(self):
        spec = rpg_spec()
        before = copy.deepcopy(spec)
        fake = FakeAgents(polish={"OLA VIAJANTE BEM VINDO A VILA": "Olá, viajante! Bem-vindo à vila."})
        orig = fake.agent

        def evil(step, name, *a, **k):
            out = orig(step, name, *a, **k)
            if name == "rebuild_polisher":
                spec["data"]["maps"]["m1"]["events"].pop()  # um «agente» que mexe na estrutura
            return out

        fake.agent = evil
        stats, warns = run_refiner(spec, fake)
        self.assertTrue(stats["reverted"])
        self.assertEqual(spec, before)
        self.assertTrue(any("estrutura" in w for w in warns))

    def test_vn_choices_and_lines(self):
        spec = {"genre": "visual_novel", "data": {"labels": {"start": [{"c": "say", "who": "", "text": "SOCORRO ALGUEM ME AJUDE"},
                                                                         {"c": "menu", "prompt": "", "choices": [{"text": "SIM  ,claro", "jump": "a"}, {"text": "Não", "jump": "a"}]}], "a": [{"c": "end", "title": "Fim"}]}}}
        fake = FakeAgents(polish={"SOCORRO ALGUEM ME AJUDE": "Socorro, alguém me ajude!", "SIM  ,claro": "Sim, claro"})
        fp = R.fingerprint(spec)
        stats, _ = run_refiner(spec, fake)
        self.assertEqual(spec["data"]["labels"]["start"][0]["text"], "Socorro, alguém me ajude!")
        self.assertEqual(R.fingerprint(spec), fp)
        self.assertEqual(spec["data"]["labels"]["start"][1]["choices"][0]["jump"], "a")

    def test_clean_only_never_breaks_structure(self):
        spec = rpg_spec()
        spec["data"]["maps"]["m1"]["events"][1]["pages"][0]["commands"][0]["text"] = "\\C[2]Oi\\C[0]  aí"
        fp = R.fingerprint(spec)
        self.assertEqual(R.clean_only(spec), 1)
        self.assertEqual(spec["data"]["maps"]["m1"]["events"][1]["pages"][0]["commands"][0]["text"], "Oi aí")
        self.assertEqual(R.fingerprint(spec), fp)


ROUGH_RPY = '''define e = Character("Eileen")
label start:
    e "OLA TUDO BEM COM VOCE AQUI"
    e "Voce ja  viu o dragao ?"
    menu:
        "Sim"/"x":
            jump fim
    return
label fim:
    "Fim."
    return
'''.replace('"Sim"/"x":', '"Sim":')


class FakeProvider:
    vision = False
    model = "fake-small"

    def chat(self, messages, system="", temperature=0.2, max_tokens=512, json_mode=False):
        agent = re.search(r"\[\[ASTA_AGENT:(\w+)\]\]", system).group(1)
        payload = json.loads(str(messages[-1]["content"]).split("INPUT_JSON:\n", 1)[1])
        if agent == "rebuild_profiler":
            return json.dumps({"summary": "Um café.", "tone": "leve", "setting": "café", "names": []})
        if agent == "rebuild_polisher":
            fix = {"OLA TUDO BEM COM VOCE AQUI": "Olá, tudo bem com você aqui?", "Voce ja viu o dragao ?": "Você já viu o dragão?"}
            return json.dumps({"lines": [{"id": x["id"], "text": fix.get(re.sub(r" +", " ", x["text"]), x["text"])} for x in payload["lines"]]})
        return json.dumps({"reject": []})


class RefinePipelineApi(ServerCase):
    def upload(self, name, data):
        status, _h, payload = self.c.req("POST", "/api/uploads", raw=data, headers={"X-Filename": name, "Content-Type": "application/zip", "Content-Length": str(len(data))})
        self.assertEqual(status, 200, payload)
        return json.loads(payload)["id"]

    def run_job(self, ids, **extra):
        status, r = self.c.json("POST", "/api/games/rebuild", {"attachment_ids": ids, **extra})
        self.assertEqual(status, 200, r)
        return self.c.sse(f"/api/jobs/{r['job_id']}/events")

    def lines(self, done):
        z = zipfile.ZipFile(self.store.version_dir(done["project_id"], 1) / "game.zip")
        game = json.loads(z.read("data/game.json"))
        return [s["text"] for s in game["data"]["labels"]["start"] if s["c"] == "say"], z.namelist()

    def test_pipeline_runs_the_agents_with_a_provider_and_skips_them_without(self):
        up = self.upload("vn.zip", F.zip_bytes({"game/script.rpy": ROUGH_RPY.encode()}, "Meu VN"))
        # sem provedor de IA (Demo): só a limpeza determinística; etapas de IA puladas
        ev = self.run_job([up])
        done = next(e for e in ev if e["type"] == "done")
        self.assertEqual([e["status"] for e in ev if e["type"] == "step" and e["id"] in ("profiler", "polisher", "auditor")], ["skipped"] * 3)
        lines, _ = self.lines(done)
        self.assertEqual(lines[0], "OLA TUDO BEM COM VOCE AQUI")
        self.assertEqual(lines[1], "Voce ja viu o dragao ?")  # a limpeza arrumou o espaço duplo
        # com um provedor (falso) ativo: Perfilador → Polidor → Auditor
        self.store.save_settings({"active": {"generation": "openai"}})
        up2 = self.upload("vn2.zip", F.zip_bytes({"game/script.rpy": ROUGH_RPY.encode()}, "Meu VN"))
        with mock.patch("asta.rebuild.pipeline.build_provider", return_value=FakeProvider()):
            ev = self.run_job([up2])
        done = next(e for e in ev if e["type"] == "done")
        steps = [e["id"] for e in ev if e["type"] == "step" and e["status"] in ("done", "warn")]
        self.assertEqual(steps, ["attachments", "analyst", "designer", "profiler", "polisher", "auditor", "reviewer", "package"])
        lines, names = self.lines(done)
        self.assertEqual(lines[:2], ["Olá, tudo bem com você aqui?", "Você já viu o dragão?"])
        self.assertEqual(done["refine"]["polished"], 2)
        self.assertTrue(done["rebuild"]["refined"])
        z = zipfile.ZipFile(self.store.version_dir(done["project_id"], 1) / "game.zip")
        self.assertTrue(any("rebuild_polisher" in n for n in z.namelist() + [""]) or any("polisher" in n for n in z.namelist()))
        # refine:false desliga a IA mesmo com provedor
        up3 = self.upload("vn3.zip", F.zip_bytes({"game/script.rpy": ROUGH_RPY.encode()}, "Meu VN"))
        with mock.patch("asta.rebuild.pipeline.build_provider", side_effect=AssertionError("não deveria chamar o provedor")):
            ev = self.run_job([up3], refine=False)
        self.assertTrue(any(e["type"] == "done" for e in ev))

    def test_provider_outage_does_not_fail_the_rebuild(self):
        from asta.providers import ProviderError

        class Down(FakeProvider):
            def chat(self, *a, **k):
                raise ProviderError("sem conexão", status=401)

        self.store.save_settings({"active": {"generation": "openai"}})
        up = self.upload("vn.zip", F.zip_bytes({"game/script.rpy": ROUGH_RPY.encode()}, "Meu VN"))
        with mock.patch("asta.rebuild.pipeline.build_provider", return_value=Down()):
            ev = self.run_job([up])
        done = next((e for e in ev if e["type"] == "done"), None)
        self.assertIsNotNone(done, ev[-3:])
        self.assertTrue(any("interrompido" in w for w in done["warnings"]))


if __name__ == "__main__":
    unittest.main()
