"""v0.23 — melhorias gerais: correções de execução de tarefas / equipes de agentes e novos recursos (regressões reproduzidas aqui)."""
import http.client
import json
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import jobs, team, uiprefs  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402


def read_sse(port: int, path: str, headers=None, limit: int = 5000):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    conn.request("GET", path, headers=headers or {})
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    events, ids = [], []
    for block in raw.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
            elif line.startswith("id:"):
                ids.append(int(line[3:]))
    return events[:limit], ids


class JobEventTests(unittest.TestCase):
    def test_sequence_numbers_stay_unique_and_absolute_after_trimming(self):
        """Antes: ao passar de 2000 eventos a lista era aparada mas `seq` vinha de len(events) — números repetidos e o consumidor (índice na lista) perdia eventos."""
        job = jobs.Job("t")
        for i in range(jobs.MAX_EVENTS + 600):
            job.emit({"type": "step", "n": i})
        seqs = [e["seq"] for e in job.events]
        self.assertEqual(seqs, sorted(set(seqs)))                 # sem repetidos, em ordem
        self.assertEqual(job.total, jobs.MAX_EVENTS + 600)
        self.assertEqual(job.events[-1]["seq"], job.total - 1)
        self.assertEqual(job.events[-1]["n"], jobs.MAX_EVENTS + 599)
        self.assertLessEqual(len(job.events), jobs.MAX_EVENTS)

    def test_since_returns_the_tail_and_survives_a_trimmed_start(self):
        job = jobs.Job("t")
        for i in range(jobs.MAX_EVENTS + 100):
            job.emit({"type": "step", "n": i})
        tail = job.since(job.total - 3)
        self.assertEqual([e["n"] for e in tail], [jobs.MAX_EVENTS + 97, jobs.MAX_EVENTS + 98, jobs.MAX_EVENTS + 99])
        first = job.since(0)                                       # já descartado: devolve a partir do mais antigo que existe
        self.assertEqual(first[0]["seq"], job.base)
        self.assertEqual(job.since(job.total), [])


class JobStreamTests(ServerCase):
    def _long_job(self, n):
        def work(job):
            for i in range(n):
                job.emit({"type": "step", "n": i})
            return {"ok": True}
        job = self.app.jobs.start("test", work)
        for _ in range(200):
            if job.status != "running":
                break
            time.sleep(0.02)
        self.assertEqual(job.status, "done")
        return job

    def test_stream_of_a_long_job_ends_with_the_last_event_and_the_end_marker(self):
        job = self._long_job(jobs.MAX_EVENTS + 700)
        events, ids = read_sse(self.port, f"/api/jobs/{job.id}/events")
        self.assertEqual(events[-1], {"type": "end", "status": "done"})
        self.assertEqual(events[-2]["n"], jobs.MAX_EVENTS + 699)   # o último evento chega (antes ficava preso/perdido)
        self.assertEqual(ids, sorted(set(ids)))                     # ids do SSE crescentes e únicos

    def test_reconnecting_with_last_event_id_continues_instead_of_replaying(self):
        job = self._long_job(50)
        events, ids = read_sse(self.port, f"/api/jobs/{job.id}/events", {"Last-Event-ID": "47"})
        self.assertEqual([e["n"] for e in events if e["type"] == "step"], [47, 48, 49])
        self.assertEqual(ids[0], 48)
        events, _ = read_sse(self.port, f"/api/jobs/{job.id}/events?from=49")
        self.assertEqual([e["n"] for e in events if e["type"] == "step"], [49])

    def test_job_status_reports_the_absolute_count(self):
        job = self._long_job(jobs.MAX_EVENTS + 10)
        status, r = self.c.json("GET", f"/api/jobs/{job.id}")
        self.assertEqual(status, 200)
        self.assertEqual(r["events"], job.total)
        self.assertGreater(r["events"], jobs.MAX_EVENTS)


class JobListTests(ServerCase):
    def test_lists_running_jobs_first_and_filters_by_status(self):
        gate = threading.Event()

        def slow(job):
            gate.wait(10)
            return {}
        running = self.app.jobs.start("slow-test", slow)
        done = self.app.jobs.start("quick-test", lambda job: {})
        for _ in range(100):
            if done.status != "running":
                break
            time.sleep(0.02)
        try:
            status, r = self.c.json("GET", "/api/jobs")
            self.assertEqual(status, 200)
            ids = [j["id"] for j in r["jobs"]]
            self.assertLess(ids.index(running.id), ids.index(done.id))      # em andamento primeiro
            self.assertGreaterEqual(r["running"], 1)
            only = self.c.json("GET", "/api/jobs?status=running")[1]["jobs"]
            self.assertIn(running.id, [j["id"] for j in only])
            self.assertNotIn(done.id, [j["id"] for j in only])
        finally:
            gate.set()


class ScriberStatsTests(ServerCase):
    def test_stats_numbers_and_readability(self):
        from asta.scriber import stats

        text = ["Era uma vez um rei que morava em um castelo muito grande. Ele gostava do castelo, do castelo e do jardim do castelo.", "O rei saiu. Voltou cedo."] * 8
        r = stats.analyze(text, "pt-BR")
        self.assertEqual((r["paragraphs"], r["sentences"], r["words"]), (16, 32, 224))
        self.assertEqual(r["top_words"][0], {"word": "castelo", "count": 32})
        self.assertEqual(r["level"], "very_easy")
        self.assertTrue(r["checks"]["words_ok"])
        self.assertEqual(r["reading_minutes"], round(224 / stats.WPM, 1))

    def test_short_texts_have_no_readability_and_long_sentences_are_reported(self):
        from asta.scriber import stats

        self.assertIsNone(stats.analyze(["Oi."], "pt")["readability"])
        long = " ".join(["palavra"] * 45) + "."
        r = stats.analyze([long, "Curta."], "pt")
        self.assertEqual((r["long_sentence_count"], r["long_sentences"][0]["words"]), (1, 45))
        self.assertEqual(stats.analyze([], None)["words"], 0)

    def test_stats_endpoint_validates_input(self):
        status, r = self.c.json("POST", "/api/scriber/stats", {"paragraphs": ["Um dois três quatro cinco seis sete oito nove dez."] * 5, "language": "en"})
        self.assertEqual((status, r["words"]), (200, 50))
        self.assertEqual(self.c.json("POST", "/api/scriber/stats", {"paragraphs": "x"})[0], 400)


class TeamInputTests(unittest.TestCase):
    def test_huge_or_infinite_agent_counts_saturate_instead_of_crashing(self):
        """Antes: `agents: 1e999` / «inf» / 10**400 levantava OverflowError (HTTP 500) em qualquer seção."""
        for v in (float("inf"), "1e999", "inf", 10 ** 400):
            self.assertEqual(team.normalize_agents(v), team.MAX_AGENTS, v)
        for v in (float("-inf"), "-1e999", -(10 ** 400)):
            self.assertEqual(team.normalize_agents(v), 1, v)
        self.assertEqual(team.normalize_agents(float("nan")), team.DEFAULT_AGENTS)
        self.assertEqual(team.from_config({"agents": float("inf")}, {"effort": 3}).agents, team.MAX_AGENTS)
        self.assertEqual(team.request_team({"agents": "1e999"}), {})            # texto não numérico: ignorado
        self.assertEqual(team.request_team({"team": {"agents": 10 ** 400}}), {"agents": team.MAX_AGENTS})


class PriorityInheritanceTests(unittest.TestCase):
    def test_team_agent_threads_inherit_the_background_priority_of_their_job(self):
        """Antes: set_priority é por thread e os agentes da mesa rodavam em threads novas — voltavam a ser «interativos» e furavam a fila do modelo local."""
        from asta import scheduler

        seen = []

        def ask(instruction, payload):
            seen.append(scheduler.priority())
            return {"ok": True, "n": len(seen)}

        scheduler.set_priority(scheduler.BACKGROUND)
        try:
            team.ensemble_json(ask, team.make(8, "high"), "x", {})
            team.team_notes(type("P", (), {"chat": lambda self, *a, **k: seen.append(scheduler.priority()) or "nota"})(), [{"role": "user", "content": "oi"}], team.make(4, "low"))
        finally:
            scheduler.set_priority(scheduler.INTERACTIVE)
        self.assertGreaterEqual(len(seen), 12)
        self.assertEqual(set(seen), {scheduler.BACKGROUND})

    def test_interactive_threads_stay_interactive(self):
        from asta import scheduler

        seen = []
        scheduler.set_priority(scheduler.INTERACTIVE)
        team.ensemble_json(lambda i, p: seen.append(scheduler.priority()) or {"a": 1}, team.make(4, "low"), "x", {})
        self.assertEqual(set(seen), {scheduler.INTERACTIVE})


class DataProviderErrorTests(unittest.TestCase):
    def test_the_real_provider_error_reaches_the_warnings_instead_of_vanishing(self):
        """Antes: qualquer exceção do provedor (chave inválida, 401, rede) virava só «a IA não respondeu»."""
        import shutil
        import tempfile

        from asta.data import DataManager, agents as dai
        from asta.providers import ProviderError
        from asta.storage import Store
        from tests.test_data import FakeJob

        class Broken:
            id, model, vision = "broken", "b", False

            def chat(self, *a, **k):
                raise ProviderError("Chave de API inválida", 401)

        home = Path(tempfile.mkdtemp(prefix="asta-data-err-"))
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        store = Store(home)
        m = DataManager(store)
        it = m.create("dataset", "E")
        ai = dai.DataAI(store, m, {"prompt": "pessoas", "count": 3, "mode": "single"}, FakeJob())
        ai.provider, ai.pid = Broken(), "broken"
        out = ai.generate_synthetic("dataset", it["id"])
        self.assertTrue(any("Chave de API inválida" in w for w in ai.report()["warnings"]), ai.report())
        self.assertEqual(len(m.get("dataset", it["id"])["records"]), 3)   # e o gerador determinístico entregou mesmo assim
        self.assertIsNotNone(out)


class CodeFindTodosTests(unittest.TestCase):
    def test_find_todos_lists_markers_read_only_and_is_a_read_tool(self):
        import tempfile

        from asta.code import tools as T
        from asta.code import normalize_config
        from asta.code.workspace import Workspace

        root = Path(tempfile.mkdtemp(prefix="asta-todo-"))
        self.addCleanup(__import__("shutil").rmtree, root, True)
        proj = root / "proj"
        proj.mkdir()
        (proj / "a.py").write_text("x = 1\n# TODO: trocar isto\ny = 2  # FIXME quebra com None\n", encoding="utf-8")
        (proj / "b.js").write_text("// HACK temporario\nlet todoList = [];\n", encoding="utf-8")   # «todoList» não é um marcador
        ws = Workspace(proj, root / "sess", [])
        ctx = T.Context(sid="s", settings={}, cfg=normalize_config({}), ws=ws, inputs_dir=root / "i", scratch_dir=root / "sc")
        out = T.execute(ctx, "find_todos", {}).output
        self.assertIn("a.py:2", out)
        self.assertIn("a.py:3", out)
        self.assertIn("b.js:1", out)
        self.assertNotIn("b.js:2", out)
        self.assertEqual(T.TOOLS["find_todos"].risk, T.READ)
        for role in ("architect", "researcher", "reviewer"):   # os papéis somente-leitura podem usar
            self.assertIn(T.READ, T.ROLE_RISKS[role])


class BadInputTests(ServerCase):
    def test_non_list_attachment_ids_do_not_crash_the_generators(self):
        """Antes: `attachment_ids: 5` levantava TypeError (HTTP 500) em /api/avatars/generate e /api/games/generate."""
        for path in ("/api/avatars/generate", "/api/games/generate", "/api/generate"):
            for bad in (5, "x", {"a": 1}, True, [1, None, "ok"]):
                status, r = self.c.json("POST", path, {"prompt": "uma ideia", "attachment_ids": bad})
                self.assertLess(status, 500, (path, bad, r))

    def test_absurd_team_values_do_not_crash_any_section(self):
        status, r = self.c.json("POST", "/api/games/generate", {"prompt": "jogo simples", "team": {"agents": 10 ** 400, "effort": ["x"]}})
        self.assertLess(status, 500, r)
        status, r = self.c.json("POST", "/api/avatars/generate", {"prompt": "uma amiga", "agents": "1e999"})
        self.assertLess(status, 500, r)


class DataSectionTests(unittest.TestCase):
    def test_data_is_a_team_section_with_normalized_values(self):
        from asta import storage

        self.assertIn("data", team.SECTIONS)
        s = {"data": {"agents": 13, "effort": "nope"}}
        storage._normalize_teams(s)
        self.assertEqual(s["data"]["agents"], 12)
        self.assertEqual(s["data"]["effort"], "high")

    def test_data_settings_export_import_and_reset(self):
        self.assertIn("data", uiprefs.EXPORT_SECTIONS)
        self.assertIn("data", uiprefs.RESETTABLE)
        payload = {"schema": uiprefs.EXPORT_SCHEMA, "settings": {"data": {"agents": 8, "effort": "max", "web": True, "synthetic_count": 40, "evil": 1}}}
        patch = uiprefs.import_patch(payload)
        self.assertEqual(patch["data"], {"agents": 8, "effort": "max", "synthetic_count": 40})   # o raspador não liga por arquivo importado


class DataQualityTests(ServerCase):
    RECS = [{"id": 1, "nome": "Ana", "idade": 30, "email": "ana@x.com"}, {"id": 2, "nome": " ana ", "idade": 30, "email": "ANA@x.com"},
            {"id": 3, "nome": "Bia", "idade": "vinte", "email": ""}, {"id": 4, "nome": "Caio", "idade": 41, "email": None}, {"id": 5, "nome": "Ana", "idade": 30.0, "email": "ana@x.com"}]
    SCHEMA = {"fields": [{"name": "id", "type": "integer"}, {"name": "nome", "type": "text"}, {"name": "idade", "type": "number"}, {"name": "email", "type": "text"}]}

    def _item(self, records=None):
        status, it = self.c.json("POST", "/api/data/items", {"kind": "dataset", "name": "Q", "schema": self.SCHEMA, "records": records if records is not None else self.RECS})
        self.assertEqual(status, 201, it)
        return it["id"]

    def test_profile_counts_columns_and_reports_findings(self):
        from asta.data import quality

        p = quality.profile(self.RECS, self.SCHEMA)
        cols = {c["name"]: c for c in p["columns"]}
        self.assertEqual(p["records"], 5)
        self.assertEqual((cols["email"]["filled"], cols["email"]["missing"]), (3, 2))   # vazio e None contam como faltando
        self.assertEqual(cols["idade"]["min"], 30.0)
        self.assertEqual(cols["idade"]["max"], 41.0)
        codes = {(i["code"], i.get("field")) for i in p["issues"]}
        self.assertIn(("type_mismatch", "idade"), codes)    # «vinte» num campo numérico
        self.assertIn(("mixed_types", "idade"), codes)
        self.assertIn(("duplicates", None), codes)
        self.assertEqual(quality.profile([], {"fields": []})["issues"], [{"code": "no_records"}])

    def test_dedupe_keeps_the_first_ignores_id_and_case_and_checks_the_count(self):
        from asta.data import quality

        r = quality.dedupe(self.RECS, self.SCHEMA)
        self.assertEqual(r["removed"], [1, 4])                    # ids diferentes, mesmo conteúdo (espaços/maiúsculas/30 == 30.0)
        self.assertEqual([x["id"] for x in r["kept"]], [1, 3, 4])
        self.assertTrue(r["checks"]["ok"])
        self.assertNotIn("id", r["keys"])
        strict = quality.dedupe(self.RECS, self.SCHEMA, ignore_case=False)
        self.assertEqual(strict["removed"], [4])                  # sem ignorar maiúsculas só o registro 5 repete o 1
        by_key = quality.dedupe(self.RECS, self.SCHEMA, keys=["nome"])
        self.assertEqual(by_key["keys"], ["nome"])
        self.assertEqual(by_key["removed"], [1, 4])
        blank = quality.dedupe([{"a": ""}, {"a": None}, {"a": ""}], {"fields": [{"name": "a"}]})
        self.assertEqual((blank["removed"], blank["skipped_blank"]), ([], 3))   # registros sem nenhum valor nunca são removidos

    def test_api_preview_changes_nothing_and_apply_snapshots_first(self):
        iid = self._item()
        status, prev = self.c.json("POST", f"/api/data/items/dataset/{iid}/dedupe", {})
        self.assertEqual(status, 200)
        self.assertEqual((prev["removed"], prev["applied"], prev["total"]), (2, False, 5))
        self.assertEqual(len(self.c.json("GET", f"/api/data/items/dataset/{iid}")[1]["records"]), 5)
        status, done = self.c.json("POST", f"/api/data/items/dataset/{iid}/dedupe", {"apply": True})
        self.assertTrue(done["applied"])
        self.assertEqual(len(self.c.json("GET", f"/api/data/items/dataset/{iid}")[1]["records"]), 3)
        hist = self.c.json("GET", f"/api/data/items/dataset/{iid}/history")[1]["items"]
        self.assertTrue(any("dedupe" in h["id"] for h in hist))
        status, p = self.c.json("GET", f"/api/data/items/dataset/{iid}/profile")
        self.assertEqual((status, p["duplicates"]), (200, 0))
        self.assertEqual(self.c.json("POST", "/api/data/items/dataset/nao_existe/dedupe", {})[0], 404)

    def test_snapshots_in_the_same_second_do_not_overwrite_each_other(self):
        """Antes: o id do snapshot tinha resolução de segundos; lotes seguidos com o mesmo rótulo sobrescreviam o histórico."""
        from asta.data import DataManager

        m = DataManager(self.store)
        it = m.create("dataset", "H")
        for i in range(6):
            m.append_records("dataset", it["id"], [{"v": i}], "append")
        ids = [h["id"] for h in m.history("dataset", it["id"])]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 7)                     # create + 6 gravações
        self.assertEqual(ids, sorted(ids, reverse=True))        # do mais novo para o mais antigo


if __name__ == "__main__":
    unittest.main()
