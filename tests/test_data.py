"""Modo Data: schemas e tipos, o gerenciador (CRUD, registros, mesclagem, histórico, importação/exportação),
a robots.txt do scraping, a IA (geração sintética em massa com tabela de agentes, extração, upgrade — com e
sem provedor) e a API HTTP de ponta a ponta."""
import json
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.data import agents as dai  # noqa: E402
from asta.data import scrape as scrapelib  # noqa: E402
from asta.data import schema as S  # noqa: E402
from asta.data.manager import DataError, DataManager  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402


class FakeProvider:
    """Provedor de mentira: devolve JSON válido e anota as chamadas."""

    id, model, vision = "fake", "fake-1", False

    def __init__(self, records=None, bad=False):
        self.calls = []
        self.records = records
        self.bad = bad

    def chat(self, messages, system="", temperature=0.8, max_tokens=1024, json_mode=False, stream=False):
        self.calls.append({"system": system, "content": messages[-1]["content"], "json_mode": json_mode})
        if self.bad:
            return "isto não é json"
        n = 3 if self.records is None else len(self.records)
        recs = self.records if self.records is not None else [{"id": str(i + 1), "nome": f"Pessoa {i + 1}"} for i in range(n)]
        return json.dumps({"schema": {"fields": [{"name": "id", "type": "text"}, {"name": "nome", "type": "text"}]}, "records": recs})


class FakeJob:
    cancelled = False

    def __init__(self):
        self.events = []

    def emit(self, ev):
        self.events.append(ev)


class DataCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="asta-data-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.store = Store(self.home)
        self.m = DataManager(self.store)
        scrapelib.reset_cache()


class SchemaTests(DataCase):
    def test_catalog_lists_the_tabs_in_order(self):
        cat = S.catalog()
        self.assertEqual([x["id"] for x in cat["tabs"]], ["main", "databases", "datasets", "synthetic_data", "web_scraping", "upgrade", "export"])
        self.assertEqual([x["label"] for x in cat["tabs"]], ["Main", "Databases", "Datasets", "Synthetic data", "Web scraping", "Upgrade", "Export"])
        self.assertEqual(cat["kinds"], ["database", "dataset"])
        self.assertEqual(cat["synth_modes"], ["single", "multi"])

    def test_catalog_has_the_bulk_limits(self):
        limits = S.catalog()["limits"]
        self.assertEqual(limits["synthetic_count"], 5000)
        self.assertEqual(limits["scrape_urls"], 500)

    def test_clean_schema_keeps_valid_types_and_drops_the_rest(self):
        out = S.clean_schema({"fields": [
            {"name": "nome do campo", "type": "text"},
            {"name": "idade", "type": "integer"},
            {"name": "foto", "type": "image"},
            {"name": "quando", "type": "date"},
            {"name": "x", "type": "inventado"},
            {"name": "", "type": "text"},
        ]})
        names = [f["name"] for f in out["fields"]]
        self.assertEqual(names, ["nome_do_campo", "idade", "foto", "quando", "x"])
        self.assertEqual(out["fields"][3]["type"], "date")
        self.assertEqual(out["fields"][4]["type"], "text")   # tipo desconhecido vira texto

    def test_clean_schema_without_fields_has_a_default(self):
        self.assertEqual([f["name"] for f in S.clean_schema({})["fields"]], ["id", "content"])


class ManagerTests(DataCase):
    def test_create_list_get_update_delete(self):
        it = self.m.create("dataset", "Clientes", "desc", {"fields": [{"name": "id"}]})
        self.assertEqual(it["kind"], "dataset")
        self.assertTrue(it["id"].startswith("s_"))
        self.assertEqual(len(self.m.list("dataset")), 1)
        self.assertEqual(len(self.m.list("database")), 0)
        got = self.m.get("dataset", it["id"])
        self.assertEqual(got["meta"]["name"], "Clientes")
        self.assertEqual(got["meta"]["fields"], 1)
        upd = self.m.update_meta("dataset", it["id"], {"name": "Novo", "tags": ["a", "b"], "modalities": ["text"]})
        self.assertEqual(upd["name"], "Novo")
        self.assertEqual(upd["tags"], ["a", "b"])
        self.assertTrue(self.m.delete("dataset", it["id"]))
        self.assertEqual(self.m.list("dataset"), [])

    def test_invalid_kind_and_id_are_refused(self):
        with self.assertRaises(DataError):
            self.m.create("planilha", "x")
        with self.assertRaises(DataError):
            self.m.get("dataset", "../escape")

    def test_save_and_append_records(self):
        it = self.m.create("dataset", "X")
        self.m.save_records("dataset", it["id"], [{"a": 1}, {"a": 2}], {"fields": [{"name": "a", "type": "integer"}]})
        self.assertEqual(self.m.get("dataset", it["id"])["meta"]["records"], 2)
        self.m.append_records("dataset", it["id"], [{"a": 3}])
        self.assertEqual(self.m.get("dataset", it["id"])["meta"]["records"], 3)

    def test_merge_unions_the_schema_and_adds_the_records(self):
        a = self.m.create("dataset", "A", "", {"fields": [{"name": "id"}]}, [{"id": "1"}])
        b = self.m.create("database", "B", "", {"fields": [{"name": "id"}, {"name": "cidade"}]}, [{"id": "2", "cidade": "SP"}])
        out = self.m.merge_items("dataset", a["id"], "database", b["id"])
        self.assertEqual(out["meta"]["records"], 2)
        names = [f["name"] for f in out["schema"]["fields"]]
        self.assertIn("cidade", names)
        self.assertEqual(len(names), len(set(names)))   # sem campos duplicados

    def test_duplicate_copies_records(self):
        it = self.m.create("dataset", "X", "d", {"fields": [{"name": "id"}]}, [{"id": "1"}])
        cp = self.m.duplicate("dataset", it["id"])
        self.assertNotEqual(cp["id"], it["id"])
        self.assertEqual(self.m.get("dataset", cp["id"])["meta"]["records"], 1)

    def test_history_and_restore(self):
        it = self.m.create("dataset", "X")
        self.m.save_records("dataset", it["id"], [{"v": 1}], label="primeiro")
        snap = self.m.snapshot("dataset", it["id"], "antes")
        self.m.save_records("dataset", it["id"], [{"v": 2}], label="depois")
        self.assertEqual(self.m.get("dataset", it["id"])["records"], [{"v": 2}])
        self.m.restore("dataset", it["id"], snap)
        self.assertEqual(self.m.get("dataset", it["id"])["records"], [{"v": 1}])

    def test_import_json_jsonl_csv_tsv_and_xml(self):
        it = self.m.create("dataset", "X")
        self.m.import_data("dataset", it["id"], "a.json", b'[{"a": 1}, {"a": 2}]')
        self.assertEqual(self.m.get("dataset", it["id"])["meta"]["records"], 2)
        self.m.import_data("dataset", it["id"], "b.jsonl", b'{"a": 3}\n{"a": 4}\n', "append")
        self.assertEqual(self.m.get("dataset", it["id"])["meta"]["records"], 4)
        self.m.import_data("dataset", it["id"], "c.csv", b"a,b\n1,2\n3,4\n", "append")
        got = self.m.get("dataset", it["id"])
        self.assertEqual(got["meta"]["records"], 6)
        self.assertIn("b", [f["name"] for f in got["schema"]["fields"]])
        self.m.import_data("dataset", it["id"], "d.tsv", b"a\tb\n5\t6\n", "append")
        self.assertEqual(self.m.get("dataset", it["id"])["meta"]["records"], 7)
        self.m.import_data("dataset", it["id"], "e.xml", b"<root><item><a>1</a><b>x</b></item><item><a>2</a><b>y</b></item></root>", "append")
        got = self.m.get("dataset", it["id"])
        self.assertEqual(got["meta"]["records"], 9)
        self.assertIn({"a": "1", "b": "x"}, got["records"])

    def test_import_xml_reads_attributes_and_children(self):
        it = self.m.create("dataset", "X")
        self.m.import_data("dataset", it["id"], "e.xml", b'<r><i id="7"><n>z</n></i></r>')
        recs = self.m.get("dataset", it["id"])["records"]
        self.assertEqual(recs[0]["id"], "7")
        self.assertEqual(recs[0]["n"], "z")

    def test_export_keeps_the_structure_in_every_format(self):
        it = self.m.create("dataset", "Meu Dataset", "", {"fields": [{"name": "id"}, {"name": "nome"}]}, [{"id": "1", "nome": "Ana"}, {"id": "2", "nome": "Bia"}])
        for fmt in S.EXPORT_FORMATS:
            out = self.m.export("dataset", it["id"], fmt)
            path = Path(out["path"])
            self.assertTrue(path.is_file(), fmt)
            self.assertEqual(out["records"], 2, fmt)
            data = path.read_bytes()
            self.assertTrue(data.strip(), fmt)
            if fmt == "json":
                obj = json.loads(data.decode())
                self.assertEqual(len(obj["records"]), 2)
                self.assertEqual(obj["schema"]["fields"][0]["name"], "id")
            elif fmt in ("jsonl", "ndjson"):
                lines = [x for x in data.decode().splitlines() if x.strip()]
                self.assertEqual(len(lines), 2)
            elif fmt == "csv":
                self.assertIn("nome", data.decode().splitlines()[0])
                self.assertIn("Ana", data.decode())
            elif fmt == "tsv":
                self.assertIn("Ana", data.decode())
            elif fmt == "xml":
                root = ET.fromstring(data.decode())
                self.assertEqual(len(root.find("records")), 2)
                self.assertEqual(root.find("records/record/nome").text, "Ana")
            elif fmt == "html":
                self.assertIn("<table>", data.decode())
                self.assertIn("Ana", data.decode())
            elif fmt == "md":
                self.assertIn("| id | nome |", data.decode())
            elif fmt == "sqlite":
                import sqlite3

                con = sqlite3.connect(str(path))
                try:
                    rows = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
                    self.assertEqual(rows, 2)
                finally:
                    con.close()

    def test_export_rejects_an_unknown_format(self):
        it = self.m.create("dataset", "X")
        with self.assertRaises(DataError):
            self.m.export("dataset", it["id"], "parquet")

    def test_export_path_does_not_escape_the_folder(self):
        it = self.m.create("dataset", "X")
        self.m.export("dataset", it["id"], "json")
        with self.assertRaises(DataError):
            self.m.export_path("dataset", it["id"], "../../../etc/passwd")

    def test_create_from_upload(self):
        out = self.m.create_from_upload("dataset", "Importado", "dados.csv", b"a,b\n1,2\n")
        self.assertEqual(out["records"], 1)
        self.assertIn("dados.csv", self.m.get("dataset", out["id"])["meta"]["description"])


class AITests(DataCase):
    def _ai(self, opts, provider=None):
        ai = dai.DataAI(self.store, self.m, opts, FakeJob())
        # o provedor é sempre controlado pelo teste: sem ele, a IA fica desligada (sem chamada de rede)
        ai.provider = provider
        ai.pid = "fake" if provider is not None else "demo"
        return ai

    def test_synthetic_uses_the_provider_and_keeps_the_schema(self):
        it = self.m.create("dataset", "X")
        prov = FakeProvider()
        ai = self._ai({"prompt": "pessoas", "count": 3, "mode": "single"}, prov)
        out = ai.generate_synthetic("dataset", it["id"])
        self.assertTrue(prov.calls, "a IA não foi chamada")
        self.assertTrue(prov.calls[0]["json_mode"])
        self.assertIn("INPUT_JSON", prov.calls[0]["content"])
        self.assertEqual(out["generated"], 3)
        self.assertTrue(out["ai"])
        recs = self.m.get("dataset", it["id"])["records"]
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[0]["nome"], "Pessoa 1")

    def test_synthetic_in_bulk_asks_the_ai_in_batches(self):
        it = self.m.create("dataset", "X")
        prov = FakeProvider()
        ai = self._ai({"prompt": "pessoas", "count": 120, "mode": "single"}, prov)
        out = ai.generate_synthetic("dataset", it["id"])
        self.assertEqual(out["generated"], 120)
        self.assertGreater(len(prov.calls), 1, "a geração em massa não foi fatiada")
        self.assertEqual(self.m.get("dataset", it["id"])["meta"]["records"], 120)

    def test_synthetic_without_ai_falls_back_to_the_deterministic_generator(self):
        it = self.m.create("dataset", "X", "", {"fields": [{"name": "id", "type": "text"}, {"name": "idade", "type": "integer"}]})
        ai = self._ai({"prompt": "clientes", "count": 4, "mode": "single"})
        out = ai.generate_synthetic("dataset", it["id"])
        self.assertFalse(out["ai"])
        recs = self.m.get("dataset", it["id"])["records"]
        self.assertEqual(len(recs), 4)
        self.assertEqual(recs[0]["id"], "1")
        self.assertIsInstance(recs[0]["idade"], int)

    def test_synthetic_fallback_uses_the_requested_types(self):
        it = self.m.create("dataset", "X", "", {"fields": [{"name": "nome", "type": "text"}, {"name": "ativo", "type": "boolean"},
                                                          {"name": "link", "type": "url"}, {"name": "quando", "type": "date"}]})
        ai = self._ai({"prompt": "x", "count": 2, "mode": "single"})
        ai.generate_synthetic("dataset", it["id"])
        row = self.m.get("dataset", it["id"])["records"][0]
        self.assertIsInstance(row["ativo"], bool)
        self.assertTrue(row["link"].startswith("https://"))
        self.assertRegex(row["quando"], r"^\d{4}-\d{2}-\d{2}$")

    def test_synthetic_multi_mode_marks_the_data_type(self):
        it = self.m.create("dataset", "X")
        ai = self._ai({"prompt": "x", "count": 2, "mode": "multi"})
        ai.generate_synthetic("dataset", it["id"])
        row = self.m.get("dataset", it["id"])["records"][0]
        self.assertIn("type", row)

    def test_synthetic_when_the_ai_answers_garbage_uses_the_fallback(self):
        it = self.m.create("dataset", "X")
        prov = FakeProvider(bad=True)
        ai = self._ai({"prompt": "x", "count": 3}, prov)
        out = ai.generate_synthetic("dataset", it["id"])
        self.assertEqual(out["generated"], 3)
        self.assertEqual(self.m.get("dataset", it["id"])["meta"]["records"], 3)

    def test_upgrade_enriches_the_existing_records(self):
        it = self.m.create("dataset", "X", "", {"fields": [{"name": "id"}]}, [{"id": "1"}, {"id": "2"}])
        prov = FakeProvider(records=[{"id": "1", "nome": "Ana"}, {"id": "2", "nome": "Bia"}])
        ai = self._ai({"prompt": "enriquecer", "action": "enrich", "mode": "single"}, prov)
        out = ai.upgrade("dataset", it["id"])
        self.assertEqual(out["records"], 2)
        recs = self.m.get("dataset", it["id"])["records"]
        self.assertEqual(recs[0]["nome"], "Ana")

    def test_upgrade_with_action_generate_adds_more_data(self):
        it = self.m.create("dataset", "X", "", {"fields": [{"name": "id"}]}, [{"id": "1"}])
        prov = FakeProvider(records=[{"id": "9", "nome": "Novo"}])
        ai = self._ai({"prompt": "mais", "action": "generate", "count": 3, "mode": "single"}, prov)
        ai.upgrade("dataset", it["id"])
        self.assertGreaterEqual(self.m.get("dataset", it["id"])["meta"]["records"], 2)

    def test_scrape_reads_the_pages_and_extracts(self):
        it = self.m.create("dataset", "X")
        pages = [{"url": "https://exemplo.org/a", "title": "A", "text": "conteúdo da página A sobre o assunto", "error": ""}]
        prov = FakeProvider(records=[{"url": "https://exemplo.org/a", "titulo": "A"}])
        ai = self._ai({"prompt": "extrair", "urls": ["https://exemplo.org/a"]}, prov)
        orig = scrapelib.fetch
        scrapelib.fetch = lambda url, limit=12000: pages[0]
        try:
            out = ai.scrape("dataset", it["id"])
        finally:
            scrapelib.fetch = orig
        self.assertEqual(out["pages"], 1)
        self.assertEqual(out["generated"], 1)
        self.assertEqual(self.m.get("dataset", it["id"])["records"][0]["titulo"], "A")

    def test_scrape_without_links_is_refused(self):
        it = self.m.create("dataset", "X")
        ai = self._ai({"prompt": "x", "urls": []})
        with self.assertRaises(ValueError):
            ai.scrape("dataset", it["id"])

    def test_scrape_without_ai_keeps_the_raw_page_text(self):
        """Sem IA, o scraping guarda o texto da página (não inventa nada)."""
        it = self.m.create("dataset", "X")
        pages = [{"url": "https://exemplo.org/a", "title": "A", "text": "o texto real da página", "error": ""}]
        ai = self._ai({"prompt": "extrair", "urls": ["https://exemplo.org/a"]})
        orig = scrapelib.fetch
        scrapelib.fetch = lambda url, limit=12000: pages[0]
        try:
            out = ai.scrape("dataset", it["id"])
        finally:
            scrapelib.fetch = orig
        self.assertEqual(out["generated"], 1)
        rec = self.m.get("dataset", it["id"])["records"][0]
        self.assertEqual(rec["url"], "https://exemplo.org/a")
        self.assertEqual(rec["content"], "o texto real da página")

    def test_the_attachment_reaches_the_ai_in_the_multimodal_prompt(self):
        """Regressão: os anexos do prompt multimodal precisam chegar à IA (antes não chegavam)."""
        import io

        it = self.m.create("dataset", "X")
        meta = self.store.save_upload_stream("notas.txt", "text/plain", io.BytesIO(b"linha um\nlinha dois\n"), 19)
        prov = FakeProvider()
        ai = self._ai({"prompt": "use as notas", "count": 2, "attachment_ids": [meta["id"]]}, prov)
        ai.generate_synthetic("dataset", it["id"])
        self.assertTrue(prov.calls, "a IA não foi chamada")
        sent = prov.calls[0]["content"]
        self.assertIn("linha um", sent)
        self.assertIn("notas.txt", sent)

    def test_an_unreadable_attachment_does_not_break_the_generation(self):
        it = self.m.create("dataset", "X")
        ai = self._ai({"prompt": "x", "count": 2, "attachment_ids": ["u_nao_existe"]}, FakeProvider())
        out = ai.generate_synthetic("dataset", it["id"])
        self.assertEqual(out["generated"], 2)

    def test_the_agents_are_logged(self):
        """Cada passo registra os agentes que trabalharam (como nas outras seções)."""
        it = self.m.create("dataset", "X")
        ai = self._ai({"prompt": "x", "count": 2, "team": {"agents": 4}}, FakeProvider())
        out = ai.generate_synthetic("dataset", it["id"])
        report = out["report"]
        self.assertTrue(report["agents"])
        self.assertEqual(report["agents"][0]["agents"], 4)
        self.assertEqual(report["agents"][0]["status"], "ok")
        self.assertEqual(report["team"]["agents"], 4)


class RobotsTests(DataCase):
    """O robots.txt é lido de verdade (com a rede simulada): o aviso do modo Data não é só texto."""

    class _Resp:
        def __init__(self, body):
            self._body = body

        def read(self, n=-1):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _with_robots(self, body):
        from unittest import mock

        scrapelib.reset_cache()
        resp = self._Resp(body)
        opener = mock.MagicMock()
        opener.return_value.__enter__.return_value = resp
        patcher = mock.patch("urllib.request.urlopen", opener)
        patcher.start()
        self.addCleanup(patcher.stop)
        # `exemplo.org` não existe: sem isto `safe_url` falha ao resolver o DNS em ambientes sem rede e o teste dependeria da internet
        real_safe = scrapelib.websearch.safe_url
        safe = mock.patch.object(scrapelib.websearch, "safe_url", side_effect=lambda u, *a, **k: True if "exemplo.org" in u else real_safe(u, *a, **k))
        safe.start()
        self.addCleanup(safe.stop)
        return opener

    def test_robots_that_disallows_the_path_blocks_the_download(self):
        self._with_robots(b"User-agent: *\nDisallow: /privado\n")
        self.assertFalse(scrapelib.allowed("https://exemplo.org/privado/x"))
        self.assertTrue(scrapelib.allowed("https://exemplo.org/publico/x"))

    def test_robots_that_allows_everything_lets_the_download_through(self):
        self._with_robots(b"User-agent: *\nAllow: /\n")
        self.assertTrue(scrapelib.allowed("https://exemplo.org/qualquer"))

    def test_without_robots_txt_the_download_is_allowed(self):
        self._with_robots(b"")
        self.assertTrue(scrapelib.allowed("https://exemplo.org/x"))

    def test_private_addresses_are_refused(self):
        self.assertFalse(scrapelib.allowed("http://127.0.0.1/x"))
        self.assertFalse(scrapelib.allowed("http://192.168.0.1/x"))
        self.assertFalse(scrapelib.allowed("file:///etc/passwd"))


class ApiTests(ServerCase):
    def _new(self, kind="dataset", name="Item"):
        s, r = self.c.json("POST", "/api/data/items", {"kind": kind, "name": name})
        self.assertEqual(s, 201, r)
        return r

    def test_catalog_and_status(self):
        s, cat = self.c.json("GET", "/api/data/catalog")
        self.assertEqual(s, 200)
        self.assertEqual([x["id"] for x in cat["tabs"]], ["main", "databases", "datasets", "synthetic_data", "web_scraping", "upgrade", "export"])
        s, st = self.c.json("GET", "/api/data/status")
        self.assertEqual(s, 200)
        self.assertIn("ai", st)

    def test_crud_over_http(self):
        it = self._new()
        s, got = self.c.json("GET", f"/api/data/items/dataset/{it['id']}")
        self.assertEqual(s, 200)
        s, lst = self.c.json("GET", "/api/data/items?kind=dataset")
        self.assertTrue(any(x["id"] == it["id"] for x in lst["items"]))
        s, _ = self.c.json("PUT", f"/api/data/items/dataset/{it['id']}", {"name": "Renomeado"})
        self.assertEqual(s, 200)
        s, dup = self.c.json("POST", f"/api/data/items/dataset/{it['id']}/duplicate", {})
        self.assertEqual(s, 201)
        s, _ = self.c.json("DELETE", f"/api/data/items/dataset/{it['id']}")
        self.assertEqual(s, 200)

    def test_records_and_merge_over_http(self):
        a = self._new("dataset", "A")
        b = self._new("database", "B")
        self.c.json("POST", f"/api/data/items/dataset/{a['id']}/records", {"records": [{"id": "1"}], "schema": {"fields": [{"name": "id"}]}, "mode": "replace"})
        self.c.json("POST", f"/api/data/items/database/{b['id']}/records", {"records": [{"id": "2"}], "schema": {"fields": [{"name": "id"}]}, "mode": "replace"})
        s, merged = self.c.json("POST", f"/api/data/items/dataset/{a['id']}/merge", {"source_kind": "database", "source_id": b["id"]})
        self.assertEqual(s, 200)
        self.assertEqual(merged["meta"]["records"], 2)

    def test_export_and_download(self):
        it = self._new()
        self.c.json("POST", f"/api/data/items/dataset/{it['id']}/records", {"records": [{"id": "1", "n": "x"}], "schema": {"fields": [{"name": "id"}, {"name": "n"}]}, "mode": "replace"})
        s, out = self.c.json("POST", f"/api/data/items/dataset/{it['id']}/export", {"format": "csv"})
        self.assertEqual(s, 200)
        status, _h, payload = self.c.req("GET", f"/api/data/items/dataset/{it['id']}/exports/{out['name']}")
        self.assertEqual(status, 200)
        self.assertIn(b"x", payload)

    def test_scrape_requires_the_notice_acknowledgement(self):
        it = self._new()
        s, err = self.c.json("POST", f"/api/data/items/dataset/{it['id']}/scrape", {"urls": ["https://exemplo.org"], "prompt": "x"})
        self.assertEqual(s, 400)
        self.assertIn("open source", json.dumps(err, ensure_ascii=False).lower())

    def test_unknown_item_is_404(self):
        s, _ = self.c.json("GET", "/api/data/items/dataset/nao_existe")
        self.assertEqual(s, 404)

    def test_import_an_existing_dataset(self):
        status, _h, payload = self.c.req("POST", "/api/data/upgrade/import?kind=dataset&item_name=Import&name=d.csv",
                                         raw=b"a,b\n1,2\n", headers={"X-Filename": "d.csv"})
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(payload)["records"], 1)

    def test_import_inside_an_existing_item_keeps_the_data_and_adds_the_columns(self):
        it = self._new("dataset", "Alvo")
        self.c.json("POST", f"/api/data/items/dataset/{it['id']}/records",
                    {"records": [{"a": "1"}], "schema": {"fields": [{"name": "a"}]}, "mode": "replace"})
        status, _h, payload = self.c.req("POST", f"/api/data/items/dataset/{it['id']}/import?mode=append&name=d.csv",
                                         raw=b"a,b\n1,2\n3,4\n", headers={"X-Filename": "d.csv"})
        self.assertEqual(status, 200, payload)
        s, got = self.c.json("GET", f"/api/data/items/dataset/{it['id']}")
        self.assertEqual(got["meta"]["records"], 3)
        names = [f["name"] for f in got["schema"]["fields"]]
        self.assertIn("b", names)      # a coluna nova do arquivo entra no schema


if __name__ == "__main__":
    unittest.main()
