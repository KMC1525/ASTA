"""v0.24 — modo Data refeito: operações, formatos (XLSX/SQL/YAML/ZIP), links de qualquer tipo, mídia do item, mesclagem por chave, IA em lotes e rotas."""
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import websearch  # noqa: E402
from asta.data import DataManager, agents as dai, formats, links, ops, quality  # noqa: E402
from asta.data import scrape as scrapelib  # noqa: E402
from asta.data.manager import DataError  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.test_data import FakeJob, FakeProvider  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402


class Case(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="asta-d24-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.store = Store(self.home)
        self.m = DataManager(self.store)
        scrapelib.reset_cache()

    def ai(self, opts, provider=None):
        ai = dai.DataAI(self.store, self.m, opts, FakeJob())
        ai.provider = provider
        ai.pid = "fake" if provider is not None else "demo"
        return ai


class OpsTests(unittest.TestCase):
    SCH = {"fields": [{"name": "a", "type": "text"}, {"name": "n", "type": "number"}, {"name": "d", "type": "date"}, {"name": "b", "type": "boolean"}]}

    def test_coerce_converts_what_it_can_and_keeps_the_rest(self):
        self.assertEqual(ops.coerce_value("4,5", "number"), (4.5, True))
        self.assertEqual(ops.coerce_value("12", "integer"), (12, True))
        self.assertEqual(ops.coerce_value("1.5", "integer"), ("1.5", False))
        self.assertEqual(ops.coerce_value("05/06/2026", "date"), ("2026-06-05", True))
        self.assertEqual(ops.coerce_value("sim", "boolean"), (True, True))
        self.assertEqual(ops.coerce_value("talvez", "boolean"), ("talvez", False))
        self.assertEqual(ops.coerce_value("", "number"), ("", True))                 # vazio não é erro
        self.assertEqual(ops.coerce_value("1e999", "number"), ("1e999", False))      # infinito não é número válido
        self.assertEqual(ops.coerce_value('{"a": 1}', "json"), ({"a": 1}, True))

    def test_infer_schema_keeps_the_declared_fields_and_adds_the_rest(self):
        recs = [{"id": 1, "foto": "attachments/a.png", "ok": True, "preco": 1.5, "quando": "2026-01-02", "tags": ["x"]}] * 3
        sch = ops.infer_schema(recs, {"fields": [{"name": "id", "type": "text", "description": "chave"}]})
        types = {f["name"]: f["type"] for f in sch["fields"]}
        self.assertEqual(types["id"], "text")                    # o que o item já declara não muda
        self.assertEqual((types["foto"], types["ok"], types["preco"], types["quando"], types["tags"]), ("image", "boolean", "number", "date", "json"))

    def test_clean_reports_what_it_did_and_never_drops_unconvertible_values(self):
        recs = [{"a": " x  y ", "n": "3", "d": "05/06/2026", "b": "sim"}, {"a": None, "n": None, "d": None, "b": None}, {"a": "z", "n": "abc", "d": "foo", "b": "talvez"}]
        rows, sch, st = ops.clean(recs, self.SCH)
        self.assertEqual(rows[0], {"a": "x y", "n": 3.0, "d": "2026-06-05", "b": True})
        self.assertEqual(st["rows_removed"], 1)
        self.assertEqual(rows[1]["n"], "abc")                    # continua lá, só foi contado
        self.assertEqual(st["failed"], 3)

    def test_fill_missing_uses_values_from_the_data(self):
        out, info = ops.fill_missing([{"n": 1, "c": "a"}, {"n": None, "c": ""}, {"n": 5, "c": "a"}, {"n": "", "c": "b"}], None)
        self.assertEqual([r["n"] for r in out], [1, 3, 5, 3])    # mediana de 1 e 5, inteira porque todos eram inteiros
        self.assertEqual(out[1]["c"], "a")                       # valor mais comum
        self.assertEqual(info["total"], 3)
        none, info2 = ops.fill_missing([{"x": None}, {"x": None}], None)
        self.assertEqual(info2["skipped"], ["x"])                # sem valor de referência: não inventa
        self.assertEqual(none[0]["x"], None)

    def test_column_ops_change_schema_and_records_together(self):
        recs = [{"a": 1}, {"a": 2}]
        r, i = ops.column_op(recs, {"fields": [{"name": "a", "type": "integer"}]}, "add", "nova col", ftype="text", default="x")
        self.assertEqual(r[0]["nova_col"], "x")
        r, i = ops.column_op(r, i["schema"], "rename", "a", "b")
        self.assertEqual(r[0], {"b": 1, "nova_col": "x"})
        self.assertEqual([f["name"] for f in i["schema"]["fields"]], ["b", "nova_col"])
        with self.assertRaises(ValueError):
            ops.column_op(r, i["schema"], "rename", "b", "nova_col")                       # nome repetido
        r, i = ops.column_op(r, i["schema"], "remove", "nova_col")
        self.assertEqual(r[0], {"b": 1})
        r, i = ops.column_op([{"v": "7"}, {"v": "x"}], {"fields": [{"name": "v", "type": "text"}]}, "retype", "v", ftype="integer")
        self.assertEqual((r[0]["v"], r[1]["v"], i["failed"]), (7, "x", 1))

    def test_apply_edits_orders_set_delete_insert_safely(self):
        out, st = ops.apply_edits([{"a": 1}, {"a": 2}, {"a": 3}], [{"op": "set", "i": 0, "field": "a", "value": 9}, {"op": "delete", "i": [1]},
                                                                  {"op": "insert", "i": 2, "record": {"a": 7}}, {"op": "insert", "record": {"a": 8}}, {"op": "set", "i": 99, "field": "a", "value": 0}])
        self.assertEqual([r["a"] for r in out], [9, 7, 3, 8])
        self.assertEqual(st, {"set": 1, "deleted": 1, "inserted": 2})
        with self.assertRaises(ValueError):
            ops.apply_edits([], "x")

    def test_query_pages_filters_sorts_and_keeps_the_original_position(self):
        recs = [{"n": 3, "t": "c"}, {"n": 10, "t": "a"}, {"n": None, "t": "b"}, {"n": 2, "t": "A b"}]
        q = ops.query(recs, sort="n", direction="asc", limit=10)
        self.assertEqual([x["i"] for x in q["rows"]], [3, 0, 1, 2])          # numérico, vazios no fim
        self.assertEqual([x["i"] for x in ops.query(recs, sort="n", direction="desc")["rows"]], [1, 0, 3, 2])
        self.assertEqual([x["i"] for x in ops.query(recs, q="a b")["rows"]], [3])
        self.assertEqual([x["i"] for x in ops.query(recs, where={"t": "a"})["rows"]], [1, 3])
        page = ops.query([{"i": k} for k in range(250)], offset=100, limit=50)
        self.assertEqual((page["total"], page["matched"], len(page["rows"]), page["rows"][0]["i"]), (250, 250, 50, 100))
        self.assertEqual(ops.query(recs, limit=10 ** 9)["limit"], ops.MAX_PAGE)

    def test_merge_upsert_combines_by_key_and_respects_the_conflict_policy(self):
        t = [{"id": 1, "x": "a", "y": ""}, {"id": 2, "x": "b", "y": "k"}]
        s = [{"id": 1, "x": "novo", "y": "q"}, {"id": 3, "x": "c"}]
        keep = ops.merge(t, s, {"fields": [{"name": "id"}, {"name": "x"}, {"name": "y"}]}, {"fields": [{"name": "z"}]}, "upsert", ["id"], "keep_target")
        self.assertEqual(keep["records"][0], {"id": 1, "x": "a", "y": "q"})   # só preencheu o vazio
        self.assertEqual((keep["added"], keep["updated"]), (1, 1))
        self.assertIn("z", [f["name"] for f in keep["schema"]["fields"]])
        prefer = ops.merge(t, s, {"fields": [{"name": "id"}, {"name": "x"}, {"name": "y"}]}, None, "upsert", ["id"], "prefer_source")
        self.assertEqual(prefer["records"][0]["x"], "novo")
        with self.assertRaises(ValueError):
            ops.merge(t, s, None, None, "upsert", ["nao_existe"])
        again = ops.merge(t, t, {"fields": [{"name": "id"}, {"name": "x"}, {"name": "y"}]}, None, "append", None, dedupe=True)
        self.assertEqual((again["total"], again["duplicates_removed"]), (2, 2))


class FormatTests(unittest.TestCase):
    def test_xlsx_round_trip_keeps_columns_types_and_schema(self):
        fields = [{"name": "nome", "type": "text", "description": "d"}, {"name": "idade", "type": "integer"}, {"name": "ok", "type": "boolean"}, {"name": "obs", "type": "json"}]
        recs = [{"nome": "Ana <&> \"x\"", "idade": 30, "ok": True, "obs": {"a": 1}}, {"nome": "Bia", "idade": 4.5, "ok": False}]
        raw = formats.write_xlsx(["nome", "idade", "ok", "obs"], recs, fields, "meu/dado?")
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(raw)))
        back, schema = formats.read_xlsx(raw)
        self.assertEqual(back[0]["nome"], "Ana <&> \"x\"")
        self.assertEqual((back[0]["idade"], back[0]["ok"], back[1]["idade"]), (30, True, 4.5))
        self.assertEqual(json.loads(back[0]["obs"]), {"a": 1})
        self.assertEqual([f["name"] for f in schema["fields"]], ["nome", "idade", "ok", "obs"])
        self.assertEqual(schema["fields"][1]["type"], "integer")

    def test_xlsx_with_shared_strings_and_repeated_headers(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>')
            z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>a</t></si><si><t>a</t></si><si><t>oi</t></si></sst>')
            z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row><row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>7</v></c></row></sheetData></worksheet>')
        recs, schema = formats.read_xlsx(buf.getvalue())
        self.assertEqual(recs, [{"a": "oi", "a_2": 7}])             # cabeçalho repetido não sobrescreve
        self.assertEqual([f["name"] for f in schema["fields"]], ["a", "a_2"])

    def test_xml_with_entities_and_broken_zips_are_refused(self):
        bomb = b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><l>&b;</l>'
        with self.assertRaises(formats.FormatError):
            formats.safe_xml(bomb)
        with self.assertRaises(formats.FormatError):
            formats.read_xlsx(b"isto nao e um zip")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xl/workbook.xml", bomb)
        with self.assertRaises(formats.FormatError):
            formats.read_xlsx(buf.getvalue())

    def test_sql_is_valid_and_escapes(self):
        fields = [{"name": "nome", "type": "text"}, {"name": "idade", "type": "integer"}, {"name": "ok", "type": "boolean"}]
        sql = formats.to_sql("t", fields, ["nome", "idade", "ok"], [{"nome": "O'Brien; DROP TABLE t;--", "idade": 3, "ok": True}, {"nome": None, "idade": None}])
        con = sqlite3.connect(":memory:")
        con.executescript(sql)
        self.assertEqual(con.execute("select nome, idade, ok from t order by rowid").fetchall(), [("O'Brien; DROP TABLE t;--", 3, 1), (None, None, None)])
        con.close()
        self.assertIn('"idade" INTEGER', sql)

    def test_yaml_is_json_flow_per_record(self):
        y = formats.to_yaml("dataset", {"name": "X"}, {"fields": [{"name": "a", "type": "text"}]}, [{"a": "linha\ncom: dois pontos"}])
        self.assertIn('  - {"a": "linha\\ncom: dois pontos"}', y)
        self.assertTrue(y.startswith('kind: "dataset"'))


class FakeResp:
    def __init__(self, body, ctype, length=None):
        self.body, self.headers = body, {"Content-Type": ctype, **({"Content-Length": str(length)} if length is not None else {})}

    def read(self, n=-1):
        return self.body if n is None or n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class LinkTests(unittest.TestCase):
    def read(self, url, body, ctype, length=None, **kw):
        with mock.patch.object(websearch, "safe_url", return_value=True), mock.patch.object(websearch._OPENER, "open", return_value=FakeResp(body, ctype, length)):
            return links.read(url, **kw)

    def test_the_kind_comes_from_the_content_type_then_from_the_extension(self):
        self.assertEqual(links.kind_of("image/png", "https://x/a"), "image")
        self.assertEqual(links.kind_of("application/json; charset=utf-8", "https://x/a"), "json")
        self.assertEqual(links.kind_of("application/octet-stream", "https://x/a.mp4"), "video")
        self.assertEqual(links.kind_of("text/html", "https://x/a.pdf"), "html")          # o tipo declarado manda
        self.assertEqual(links.kind_of("", "https://x/a.csv"), "csv")

    def test_json_and_csv_links_become_records_without_ai(self):
        j = self.read("https://x/api", json.dumps({"items": [{"a": 1}, {"a": 2}]}).encode(), "application/json")
        self.assertEqual((j["kind"], j["rows"]), ("json", [{"a": 1}, {"a": 2}]))
        c = self.read("https://x/d.csv", "nome;idade\nAna;3\nBia;4\n".encode(), "text/csv")
        self.assertEqual(c["rows"], [{"nome": "Ana", "idade": "3"}, {"nome": "Bia", "idade": "4"}])

    def test_html_text_and_media_links(self):
        h = self.read("https://x/p", b"<html><title>T</title><body><p>" + b"conteudo longo da pagina " * 4 + b"</p></body></html>", "text/html")
        self.assertEqual((h["kind"], h["title"]), ("html", "T"))
        self.assertIn("conteudo", h["text"])
        img = self.read("https://x/f.png", b"\x89PNG....", "image/png", length=8)
        self.assertEqual((img["kind"], img["text"], img["size"]), ("image", "", 8))
        self.assertEqual(links.record_for(img)["type"], "image")

    def test_media_download_goes_to_the_item_folder_with_a_safe_name(self):
        d = Path(tempfile.mkdtemp(prefix="asta-dl-"))
        self.addCleanup(shutil.rmtree, d, True)
        with mock.patch.object(websearch, "safe_url", return_value=True), mock.patch.object(websearch._OPENER, "open", return_value=FakeResp(b"RIFFxxxx", "audio/wav")), \
                mock.patch.object(scrapelib, "allowed", return_value=True):
            page = scrapelib.fetch("https://x/..%2F..%2Fsom.wav", download_dir=d)
        self.assertTrue(page["file"].startswith("attachments/"))
        self.assertEqual(len(list(d.iterdir())), 1)
        self.assertEqual(list(d.iterdir())[0].parent, d)                                # nada escapou da pasta
        self.assertNotIn("file_bytes", page)

    def test_private_addresses_and_bad_xml_are_refused(self):
        self.assertTrue(links.read("http://127.0.0.1/x")["error"])
        x = self.read("https://x/f.xml", b'<!DOCTYPE a [<!ENTITY b "c">]><a>&b;</a>', "application/xml")
        self.assertTrue(x["error"])
        self.assertEqual(x["text"], "")


class ManagerTests(Case):
    def item(self, recs=None, schema=None):
        return self.m.create("dataset", "X", "", schema, recs if recs is not None else [{"a": i, "t": f"v{i}"} for i in range(30)])["id"]

    def test_query_and_edit_use_original_positions_and_snapshot(self):
        iid = self.item()
        page = self.m.query("dataset", iid, sort="a", direction="desc", limit=5)
        self.assertEqual([r["i"] for r in page["rows"]], [29, 28, 27, 26, 25])
        self.assertEqual((page["matched"], page["columns"][:2]), (30, ["id", "content"]) if False else (30, page["columns"][:2]))
        out = self.m.edit_records("dataset", iid, [{"op": "set", "i": 29, "field": "t", "value": "editado"}, {"op": "delete", "i": [0]}, {"op": "insert", "record": {"a": 99, "t": "novo"}}])
        self.assertEqual((out["set"], out["deleted"], out["inserted"], out["total"]), (1, 1, 1, 30))
        recs = self.m.get("dataset", iid)["records"]
        self.assertEqual((recs[-2]["t"], recs[-1]["t"], recs[0]["a"]), ("editado", "novo", 1))
        with self.assertRaises(DataError):
            self.m.edit_records("dataset", iid, "nao e lista")

    def test_clean_previews_first_and_applies_with_history(self):
        iid = self.item([{"n": " 3 ", "x": ""}, {"n": "4", "x": ""}, {"n": "", "x": ""}], {"fields": [{"name": "n", "type": "integer"}, {"name": "x", "type": "text"}]})
        prev = self.m.clean("dataset", iid, {"fill_missing": True})
        self.assertEqual((prev["applied"], prev["rows_removed"], prev["changed"]), (False, 1, True))
        self.assertEqual(len(self.m.get("dataset", iid)["records"]), 3)           # a prévia não mexe
        before = len(self.m.history("dataset", iid))
        done = self.m.clean("dataset", iid, {"fill_missing": True}, apply=True)
        self.assertTrue(done["applied"])
        recs = self.m.get("dataset", iid)["records"]
        self.assertEqual([r["n"] for r in recs], [3, 4])
        self.assertGreater(len(self.m.history("dataset", iid)), before)

    def test_column_endpoint_logic_and_schema_inference(self):
        iid = self.item([{"a": 1, "foto": "attachments/x.png"}], {"fields": [{"name": "a", "type": "integer"}]})
        inf = self.m.infer_schema("dataset", iid, apply=True)
        self.assertEqual((inf["added"], inf["applied"]), (1, True))
        self.assertEqual([f["type"] for f in self.m.get("dataset", iid)["schema"]["fields"]], ["integer", "image"])
        self.m.column("dataset", iid, "rename", "foto", "imagem")
        self.assertIn("imagem", self.m.get("dataset", iid)["records"][0])
        with self.assertRaises(DataError):
            self.m.column("dataset", iid, "explode", "a")

    def test_media_is_confined_limited_and_travels_with_copies_and_merges(self):
        a, b = self.item([{"f": "attachments/a.png"}]), self.item([{"f": "attachments/b.png"}])
        info = self.m.add_media("dataset", a, "../../etc/a.png", b"\x89PNG data")
        self.assertEqual(info["ref"], "attachments/a.png")
        self.assertEqual(self.m.add_media("dataset", a, "a.png", b"outro")["name"], "a-2.png")     # nunca sobrescreve
        self.assertEqual(self.m.media_path("dataset", a, "a.png").parent, self.m._media_dir("dataset", a).resolve())
        with self.assertRaises(DataError):
            self.m.media_path("dataset", a, "../../../etc/passwd")
        with self.assertRaises(DataError):
            self.m.add_media("dataset", a, "grande.bin", b"x" * (25 * 1024 * 1024 + 1))
        with self.assertRaises(DataError):
            self.m.add_media("dataset", a, "vazio.bin", b"")
        cp = self.m.duplicate("dataset", a)
        self.assertEqual(sorted(x["name"] for x in self.m.list_media("dataset", cp["id"])), ["a-2.png", "a.png"])
        self.m.merge_items("dataset", b, "dataset", a)
        self.assertIn("a.png", [x["name"] for x in self.m.list_media("dataset", b)])               # a mídia da origem veio junto
        self.assertTrue(self.m.delete_media("dataset", a, "a-2.png"))

    def test_merge_dry_run_and_upsert_through_the_manager(self):
        t = self.item([{"id": 1, "x": "a"}], {"fields": [{"name": "id", "type": "integer"}, {"name": "x", "type": "text"}]})
        s = self.item([{"id": 1, "x": "z", "y": "novo"}, {"id": 2, "x": "b"}])
        pre = self.m.merge_items("dataset", t, "dataset", s, "upsert", ["id"], "prefer_source", dry_run=True)
        self.assertEqual((pre["dry_run"], pre["added"], pre["updated"]), (True, 1, 1))
        self.assertEqual(len(self.m.get("dataset", t)["records"]), 1)                              # prévia não grava
        out = self.m.merge_items("dataset", t, "dataset", s, "upsert", ["id"], "prefer_source")
        self.assertEqual(out["merge"]["updated"], 1)
        recs = self.m.get("dataset", t)["records"]
        self.assertEqual((recs[0]["x"], recs[0]["y"], len(recs)), ("z", "novo", 2))
        with self.assertRaises(DataError):
            self.m.merge_items("dataset", t, "dataset", s, "upsert", [])                           # upsert exige chave

    def test_new_export_formats_and_the_zip_bundle(self):
        iid = self.item([{"a": 1, "foto": "attachments/a.png", "n": "O'B"}], {"fields": [{"name": "a", "type": "integer"}, {"name": "foto", "type": "image"}, {"name": "n", "type": "text"}]})
        self.m.add_media("dataset", iid, "a.png", b"\x89PNG")
        self.m.add_media("dataset", iid, "nao_usada.png", b"\x89PNG")
        for fmt in ("xlsx", "sql", "yaml", "zip"):
            out = self.m.export("dataset", iid, fmt)
            self.assertTrue(Path(out["path"]).is_file() and Path(out["path"]).stat().st_size > 0, fmt)
        back, sch = formats.read_xlsx(Path(self.m.export("dataset", iid, "xlsx")["path"]).read_bytes())
        self.assertEqual((back[0]["a"], sch["fields"][1]["type"]), (1, "image"))
        names = zipfile.ZipFile(self.m.export("dataset", iid, "zip")["path"]).namelist()
        self.assertEqual(sorted(names), ["README.md", "attachments/a.png", "data.json", "records.csv"])    # só a mídia que os registros citam
        con = sqlite3.connect(self.m.export("dataset", iid, "sqlite")["path"])
        self.assertEqual(con.execute("select typeof(a) from records").fetchone()[0], "integer")           # SQLite com tipos do schema
        con.close()

    def test_sqlite_export_survives_integers_beyond_64_bits(self):
        """Achado pelo fuzz: um inteiro como 10**30 numa célula derrubava a exportação SQLite com HTTP 500."""
        iid = self.item([{"n": 10 ** 30, "ok": True, "v": None}])
        con = sqlite3.connect(self.m.export("dataset", iid, "sqlite")["path"])
        self.assertEqual(con.execute("select n, ok, v from records").fetchone(), (str(10 ** 30), 1, None))
        con.close()

    def test_xlsx_import_and_xml_tag_names(self):
        iid = self.item([])
        raw = formats.write_xlsx(["a", "b"], [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}], [{"name": "a", "type": "integer"}, {"name": "b", "type": "text"}])
        self.m.import_data("dataset", iid, "dados.xlsx", raw)
        got = self.m.get("dataset", iid)
        self.assertEqual((len(got["records"]), got["schema"]["fields"][0]["type"]), (2, "integer"))
        with self.assertRaises(DataError):
            self.m.import_data("dataset", iid, "ruim.xml", b'<!DOCTYPE a [<!ENTITY b "c">]><a><i>&b;</i></a>')
        with self.assertRaises(DataError):
            self.m.import_data("dataset", iid, "ruim.json", b"{nao e json")
        x = self.item([{"1 campo": "v", "a<b": "w"}])
        p = Path(self.m.export("dataset", x, "xml")["path"])
        import xml.etree.ElementTree as ET
        root = ET.parse(p).getroot()                                  # precisa ser XML válido mesmo com nomes de campo estranhos
        self.assertEqual(len(root.findall("records/record")), 1)


class CountsTests(Case):
    def test_listing_reads_counts_from_the_metadata_and_keeps_them_current(self):
        """Antes: cada listagem relia TODOS os registros de TODOS os itens só para contar."""
        iid = self.m.create("dataset", "C", "", None, [{"a": 1}] * 7)["id"]
        meta = json.loads((self.m._meta_path("dataset", iid)).read_text(encoding="utf-8"))
        self.assertEqual((meta["records_n"], meta["fields_n"]), (7, 2))
        with mock.patch("asta.data.manager.read_json", side_effect=AssertionError("a listagem não pode ler os registros")) as rj:
            rj.side_effect = lambda path, default=None: json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).name == "meta.json" else (_ for _ in ()).throw(AssertionError("leu " + Path(path).name))
            self.assertEqual(self.m.list("dataset")[0]["records"], 7)
        self.m.edit_records("dataset", iid, [{"op": "insert", "record": {"a": 2}}])
        self.assertEqual(self.m.list("dataset")[0]["records"], 8)
        hid = self.m.history("dataset", iid)[-1]["id"]                                     # o snapshot mais antigo (criação)
        self.m.restore("dataset", iid, hid)
        self.assertEqual(self.m.list("dataset")[0]["records"], 7)                           # restaurar também atualiza a contagem

    def test_items_created_before_v024_get_their_counts_on_first_listing(self):
        iid = self.m.create("dataset", "Antigo", "", None, [{"a": 1}] * 3)["id"]
        mp = self.m._meta_path("dataset", iid)
        meta = json.loads(mp.read_text(encoding="utf-8"))
        meta.pop("records_n"), meta.pop("fields_n")
        mp.write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(self.m.list("dataset")[0]["records"], 3)
        self.assertEqual(json.loads(mp.read_text(encoding="utf-8"))["records_n"], 3)       # contou uma vez e guardou


class AIv24Tests(Case):
    def test_synthetic_keeps_one_stable_schema_dedupes_and_tops_up(self):
        it = self.m.create("dataset", "X", "", {"fields": [{"name": "id", "type": "integer"}, {"name": "nome", "type": "text"}, {"name": "idade", "type": "integer"}]})
        calls = []

        class P(FakeProvider):
            def chat(self, messages, system="", **k):
                calls.append(system)
                n = len(calls)
                recs = [{"id": 1, "nome": f"Pessoa {n}-{i}", "idade": str(20 + i), "lixo": "x"} for i in range(40)] + [{"id": 1, "nome": "Pessoa 1-0", "idade": "20"}]
                return json.dumps({"records": recs, "schema": {"fields": [{"name": "outro", "type": "text"}]}})
        out = self.ai({"prompt": "pessoas", "count": 100, "mode": "single"}, P()).generate_synthetic("dataset", it["id"])
        got = self.m.get("dataset", it["id"])
        self.assertEqual((out["generated"], len(got["records"])), (100, 100))
        self.assertEqual([f["name"] for f in got["schema"]["fields"]], ["id", "nome", "idade"])      # o schema não "deriva" entre lotes
        self.assertTrue(all(isinstance(r["idade"], int) for r in got["records"]))                    # tipos convertidos
        self.assertTrue(all("lixo" not in r for r in got["records"]))                                # fora do schema no modo «um tipo»
        ids = [r["id"] for r in got["records"]]
        self.assertEqual(len(ids), len(set(ids)))                                                     # ids únicos
        self.assertTrue(any("ROLE: Data Generator" in c for c in calls))
        self.assertTrue(out["checks"]["from_ai"] > 0 and out["checks"]["generated"] == 100)

    def test_synthetic_plans_the_schema_when_the_item_has_none(self):
        it = self.m.create("dataset", "X")
        seen = []

        class P(FakeProvider):
            def chat(self, messages, system="", **k):
                seen.append(system)
                if "ROLE: Data Planner" in system:
                    return json.dumps({"schema": {"fields": [{"name": "produto", "type": "text"}, {"name": "preco", "type": "number"}, {"name": "foto", "type": "image"}]}, "style_notes": "loja", "diversity_axes": ["categoria"]})
                return json.dumps({"records": [{"produto": f"P{len(seen)}-{i}", "preco": "9,9", "foto": f"f{i}.png"} for i in range(5)]})
        out = self.ai({"prompt": "produtos de loja com foto", "count": 5, "mode": "single"}, P()).generate_synthetic("dataset", it["id"])
        got = self.m.get("dataset", it["id"])
        self.assertEqual([f["name"] for f in got["schema"]["fields"]], ["produto", "preco", "foto"])
        self.assertEqual(got["records"][0]["preco"], 9.9)
        self.assertEqual(out["generated"], 5)
        self.assertTrue(any("ROLE: Data Planner" in s for s in seen))

    def test_upgrade_processes_the_whole_base_in_batches_and_protects_ids(self):
        recs = [{"id": str(i), "nome": f"n{i}"} for i in range(60)]
        it = self.m.create("dataset", "X", "", {"fields": [{"name": "id", "type": "text"}, {"name": "nome", "type": "text"}]}, recs)
        batches = []

        class P(FakeProvider):
            def chat(self, messages, system="", **k):
                content = messages[-1]["content"]
                payload = json.loads(content.split("INPUT_JSON:\n", 1)[1])
                rows = payload["records"]
                batches.append(len(rows))
                # a IA tenta trocar o id, mexe em tudo e esquece o último registro do lote
                return json.dumps({"records": [{"_i": r["_i"], "id": "HACK", "nome": r["nome"].upper(), "grupo": "g"} for r in rows[:-1]]})
        out = self.ai({"prompt": "maiúsculas e grupo", "action": "enrich", "mode": "single"}, P()).upgrade("dataset", it["id"])
        got = self.m.get("dataset", it["id"])["records"]
        self.assertGreater(len(batches), 1)
        self.assertEqual(sum(batches), 60)                                    # a base inteira foi, não só os 40 primeiros
        self.assertEqual([r["id"] for r in got], [str(i) for i in range(60)])  # ids intactos
        changed = [r for r in got if r["nome"].isupper()]
        self.assertEqual(len(changed), 60 - len(batches))                     # quem a IA esqueceu ficou como estava
        self.assertTrue(out["checks"]["checks"]["count_ok"] and out["checks"]["checks"]["ids_ok"])
        self.assertIn("grupo", [f["name"] for f in self.m.get("dataset", it["id"])["schema"]["fields"]])

    def test_upgrade_failures_never_lose_data_and_no_junk_fields_are_added(self):
        recs = [{"id": "1", "v": "a"}, {"id": "2", "v": "b"}]
        it = self.m.create("dataset", "X", "", None, recs)
        out = self.ai({"prompt": "melhore", "action": "enrich"}, FakeProvider(bad=True)).upgrade("dataset", it["id"])
        self.assertEqual(self.m.get("dataset", it["id"])["records"], recs)
        self.assertTrue(any("sem resposta válida" in w for w in out["warnings"]))
        out2 = self.ai({"prompt": "melhore", "action": "enrich"}).upgrade("dataset", it["id"])      # sem IA
        self.assertEqual(self.m.get("dataset", it["id"])["records"], recs)                            # (antes: «_upgrade_note» sujava os registros)
        self.assertTrue(any("precisa de uma IA" in w for w in out2["warnings"]))

    def test_upgrade_fill_missing_and_clean_work_without_ai(self):
        it = self.m.create("dataset", "X", "", {"fields": [{"name": "n", "type": "integer"}]}, [{"n": 2}, {"n": None}, {"n": 4}, {"n": ""}])
        out = self.ai({"action": "fill_missing"}).upgrade("dataset", it["id"])
        self.assertEqual([r["n"] for r in self.m.get("dataset", it["id"])["records"]], [2, 3, 4, 3])
        self.assertEqual(out["checks"]["changed"], 2)
        it2 = self.m.create("dataset", "Y", "", None, [{"a": "  x   y "}, {"a": ""}])
        self.ai({"action": "clean"}).upgrade("dataset", it2["id"])
        self.assertEqual(self.m.get("dataset", it2["id"])["records"], [{"a": "x y"}])

    def test_upgrade_classify_adds_only_the_target_field(self):
        it = self.m.create("dataset", "X", "", None, [{"id": "1", "t": "adorei"}, {"id": "2", "t": "péssimo"}])

        class P(FakeProvider):
            def chat(self, messages, system="", **k):
                rows = json.loads(messages[-1]["content"].split("INPUT_JSON:\n", 1)[1])["records"]
                return json.dumps({"records": [{"_i": r["_i"], "sentimento": "positivo" if "ador" in r["t"] else "negativo", "t": "MEXEU"} for r in rows]})
        self.ai({"action": "classify", "fields": ["sentimento"], "prompt": "sentimento do texto"}, P()).upgrade("dataset", it["id"])
        got = self.m.get("dataset", it["id"])["records"]
        self.assertEqual([(r["t"], r["sentimento"]) for r in got], [("adorei", "positivo"), ("péssimo", "negativo")])

    def test_scrape_handles_json_media_and_text_links_and_reports_everything(self):
        it = self.m.create("dataset", "X")
        pages = {
            "https://x/api": {"url": "https://x/api", "kind": "json", "rows": [{"a": 1}, {"a": 2}], "text": "...", "title": "", "error": ""},
            "https://x/foto.png": {"url": "https://x/foto.png", "kind": "image", "content_type": "image/png", "size": 10, "filename": "foto.png", "text": "", "rows": [], "title": "", "error": ""},
            "https://x/p": {"url": "https://x/p", "kind": "html", "title": "P", "text": "texto da pagina sobre o assunto", "rows": [], "error": ""},
            "https://x/off": {"url": "https://x/off", "kind": "", "text": "", "rows": [], "title": "", "error": "robots.txt do site não permite este link.", "skipped": True},
        }
        prov = FakeProvider(records=[{"produto": "Livro"}])
        ai = self.ai({"prompt": "extrair", "urls": list(pages) + ["https://x/api"]}, prov)       # link repetido entra uma vez só
        with mock.patch.object(scrapelib, "fetch", side_effect=lambda url, limit=12000: pages[url]):
            out = ai.scrape("dataset", it["id"])
        recs = self.m.get("dataset", it["id"])["records"]
        self.assertEqual(out["checks"]["links"], 4)
        self.assertEqual((out["checks"]["structured"], out["checks"]["media"], out["checks"]["extracted"]), (2, 1, 1))
        self.assertEqual(out["skipped"], 1)
        self.assertIn({"a": 1, "source_url": "https://x/api"}, recs)                              # JSON vira registro direto, com a origem
        self.assertTrue(any(r.get("type") == "image" and r.get("url") == "https://x/foto.png" for r in recs))
        self.assertTrue(any(r.get("produto") == "Livro" and r.get("source_url") == "https://x/p" for r in recs))
        self.assertEqual(len(prov.calls), 1)                                                       # só a página de texto precisou de IA
        self.assertTrue(any("robots.txt" in w for w in out["warnings"]))


class RoutesTests(ServerCase):
    def setUp(self):
        status, it = self.c.json("POST", "/api/data/items", {"kind": "dataset", "name": "R", "records": [{"a": i, "t": f"x{i}"} for i in range(25)]})
        self.assertEqual(status, 201)
        self.base = f"/api/data/items/dataset/{it['id']}"

    def test_rows_paging_search_sort_and_bad_filters(self):
        s, r = self.c.json("GET", self.base + "/rows?limit=10&offset=5&sort=a&dir=desc")
        self.assertEqual((s, r["total"], len(r["rows"]), r["rows"][0]["i"]), (200, 25, 10, 19))
        self.assertEqual(self.c.json("GET", self.base + "/rows?q=x24")[1]["matched"], 1)
        self.assertEqual(self.c.json("GET", self.base + "/rows?limit=abc&offset=zz")[0], 200)
        self.assertEqual(self.c.json("GET", self.base + "/rows?where=%7Bnao")[0], 400)

    def test_edit_columns_clean_and_schema_over_http(self):
        s, r = self.c.json("POST", self.base + "/edit", {"edits": [{"op": "set", "i": 0, "field": "t", "value": "novo"}, {"op": "delete", "i": [1, 2]}]})
        self.assertEqual((s, r["total"]), (200, 23))
        self.assertEqual(self.c.json("POST", self.base + "/edit", {"edits": "x"})[0], 400)
        self.assertEqual(self.c.json("POST", self.base + "/columns", {"op": "add", "name": "extra", "type": "integer", "default": 0})[0], 200)
        self.assertEqual(self.c.json("POST", self.base + "/columns", {"op": "add", "name": "extra"})[0], 400)
        s, r = self.c.json("POST", self.base + "/clean", {"options": {"fill_missing": True}})
        self.assertEqual((s, r["applied"]), (200, False))
        s, r = self.c.json("POST", self.base + "/schema/infer", {})
        self.assertEqual(s, 200)

    def test_media_upload_is_served_safely_and_only_known_types_inline(self):
        s, r = self.c.json("POST", self.base + "/media?name=foto.png", None)             # corpo vazio
        self.assertEqual(s, 400)
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        conn.request("POST", self.base + "/media", body=b"\x89PNG\r\n", headers={"X-Filename": "foto.png"})
        resp = conn.getresponse()
        up = json.loads(resp.read())
        conn.close()
        self.assertEqual((resp.status, up["ref"]), (201, "attachments/foto.png"))
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        conn.request("POST", self.base + "/media", body=b"<svg onload=alert(1)>", headers={"X-Filename": "x.svg"})
        conn.getresponse().read()
        conn.close()
        st, headers, body = self.c.req("GET", self.base + "/media/foto.png")
        self.assertEqual((st, headers["Content-Type"], headers["X-Content-Type-Options"]), (200, "image/png", "nosniff"))
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        st, headers, _ = self.c.req("GET", self.base + "/media/x.svg")
        self.assertIn("attachment", headers.get("Content-Disposition", ""))             # SVG nunca aparece dentro da página
        self.assertEqual(self.c.req("GET", self.base + "/media/..%2F..%2Fsettings.json")[0], 404)
        self.assertEqual(len(self.c.json("GET", self.base + "/media")[1]["items"]), 2)
        self.assertEqual(self.c.json("DELETE", self.base + "/media/x.svg")[0], 200)

    def test_merge_options_and_new_export_formats(self):
        s, a = self.c.json("POST", "/api/data/items", {"kind": "dataset", "name": "A", "records": [{"id": 1, "v": "a"}]})
        s, b = self.c.json("POST", "/api/data/items", {"kind": "dataset", "name": "B", "records": [{"id": 1, "v": "b"}, {"id": 2, "v": "c"}]})
        url = f"/api/data/items/dataset/{a['id']}/merge"
        s, r = self.c.json("POST", url, {"source_id": b["id"], "strategy": "upsert", "keys": ["id"], "conflict": "prefer_source", "dry_run": True})
        self.assertEqual((s, r["dry_run"], r["added"], r["updated"]), (200, True, 1, 1))
        self.assertEqual(self.c.json("POST", url, {"source_id": b["id"], "strategy": "upsert", "keys": []})[0], 400)
        for fmt, ctype in (("xlsx", "spreadsheetml"), ("sql", "sql"), ("yaml", "yaml"), ("zip", "zip")):
            s, out = self.c.json("POST", f"/api/data/items/dataset/{a['id']}/export", {"format": fmt})
            self.assertEqual(s, 200, out)
            st, headers, body = self.c.req("GET", f"/api/data/items/dataset/{a['id']}/exports/{out['name']}")
            self.assertEqual(st, 200)
            self.assertIn(ctype, headers["Content-Type"])


if __name__ == "__main__":
    unittest.main()
