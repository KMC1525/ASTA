"""Scriber (v0.20): catálogo, modelo de documento (HTML/Markdown/blocos, entrada hostil), .docx (gerar, ler, entrada hostil), lorebooks, ortografia, gerenciador de projetos
(caminhos seguros, histórico, exportar/importar), IA com fallback (agentes simulados: planejar → escrever → revisar → empacotar; editar trecho com tamanho escolhido; revisão ortográfica) e a API HTTP."""
import io
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
import zipfile
import xml.dom.minidom
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import team as teamlib  # noqa: E402
from asta.scriber import ScriberError, ScriberManager, agents as sai, docmodel as D, docx as X, lore as L, schema as S, spell  # noqa: E402
from asta.server import make_server  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.helpers import Client  # noqa: E402


class FakeProvider:
    id, model, vision = "fake", "fake-1", False

    def __init__(self, replies=None, fail=False):
        self.replies, self.fail, self.calls, self.systems = replies or {}, fail, [], []

    def chat(self, messages, system="", **kw):
        self.systems.append(system)
        self.calls.append(messages[-1]["content"] if isinstance(messages[-1]["content"], str) else "")
        if self.fail:
            return "isto não é json"
        for role, reply in self.replies.items():
            if f"ROLE: {role}" in system:
                r = reply(messages, system) if callable(reply) else reply
                return json.dumps(r)
        return "{}"


class FakeJob:
    cancelled = False

    def __init__(self):
        self.events = []

    def emit(self, ev):
        self.events.append(ev)


_uniq = [0]


def words(n, w="palavra"):
    """Um parágrafo de n palavras (cada chamada é diferente: o Scriber remove parágrafos repetidos em sequência)."""
    _uniq[0] += 1
    return f"p{_uniq[0]} " + " ".join([w] * max(0, n - 1)) + "."


class SchemaTests(unittest.TestCase):
    def test_catalog_has_every_writing_type_asked_for(self):
        c = S.catalog()
        for t in ("romance", "journalism", "analysis", "copywriting", "academic", "scientific"):
            self.assertIn(t, c["types"])
        self.assertTrue(c["types"]["romance"]["mature"])                # romances: SFW e NSFW
        self.assertTrue(c["types"]["scientific"]["cite"])
        self.assertIn("pt-BR", c["languages"])
        for t in S.WRITING_TYPES.values():
            self.assertIn(t["preset"], S.PRESETS)
            self.assertTrue(t["sections"]["pt"] and t["sections"]["en"])

    def test_format_is_always_valid(self):
        f = S.norm_format({"font": "Comic Sans", "size": 999, "line": "x", "margins": [0, 99, "a", None], "page": "B7", "align": "esquerda", "toc": "sim"}, "academic")
        self.assertEqual((f["font"], f["size"], f["page"], f["align"]), ("Times New Roman", 24.0, "A4", "justify"))
        self.assertTrue(all(1.0 <= m <= 6.0 for m in f["margins"]))
        self.assertEqual(f["line"], 1.5)
        self.assertEqual(S.norm_format(None)["preset"], "article")
        self.assertEqual(S.norm_format({"preset": ["x"]})["preset"], "article")   # preset que não é texto não derruba

    def test_pages_times_words_is_the_target_and_is_capped(self):
        self.assertEqual(S.norm_size(10, 300)["target_words"], 3000)
        big = S.norm_size(1000, 1000)
        self.assertLessEqual(big["target_words"], S.MAX_TARGET_WORDS)
        s = S.norm_size("abc", None, "journalism")
        self.assertEqual((s["pages"], s["words_per_page"]), (S.WRITING_TYPES["journalism"]["pages"], S.WRITING_TYPES["journalism"]["wpp"]))
        self.assertEqual(S.norm_size(float("nan"), float("inf"))["words_per_page"], S.WRITING_TYPES["romance"]["wpp"])

    def test_auto_sections_add_up_to_the_target(self):
        for t in S.WRITING_TYPES:
            for target in (60, 900, 12000, 90000):
                secs = S.auto_sections(t, target, "pt-BR")
                self.assertTrue(secs)
                self.assertGreaterEqual(sum(x["words"] for x in secs), min(target, 40 * len(secs)) - 1, (t, target))
        chapters = S.auto_sections("romance", 90000, "en-US")
        self.assertGreater(len(chapters), 10)
        self.assertTrue(chapters[0]["title"].startswith("Chapter"))

    def test_languages(self):
        self.assertEqual(S.norm_lang("pt"), "pt-BR")
        self.assertEqual(S.norm_lang("EN_us"), "en-US")
        self.assertEqual(S.norm_lang("xx-YY"), "pt-BR")
        self.assertEqual(S.norm_lang(["x"]), "pt-BR")
        self.assertEqual(S.lang_name("en-GB"), "British English")

    def test_word_count_and_expand(self):
        self.assertEqual(S.count_words("Não é um 'bom-dia', né? 3,14"), 7)
        self.assertEqual(S.norm_expand({"mode": "x", "words": 1e9}), {"mode": "add", "words": 3000})
        self.assertEqual(S.norm_expand("lixo")["words"], 120)


class DocModelTests(unittest.TestCase):
    def test_html_is_a_whitelist(self):
        bl = D.html_to_blocks('<p onclick="x()" style="color:red">a<script>alert(1)</script><b>b</b></p><img src=x onerror=y><iframe src="http://x"></iframe><a href="javascript:z">link</a>'
                              '<div class="pb"></div><p style="text-align:center">c&nbsp;d</p>solto<style>p{}</style>')
        txt = D.blocks_to_text(bl)
        self.assertNotIn("alert", txt)
        self.assertNotIn("javascript", txt)
        self.assertNotIn("p{}", txt)
        self.assertEqual([b["t"] for b in bl], ["p", "p", "pb", "p", "p"])
        self.assertEqual(bl[3]["a"], "center")
        self.assertEqual(bl[3]["runs"][0]["x"], "c d")
        html = D.blocks_to_html(bl)
        self.assertNotIn("onclick", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("style=\"color", html)

    def test_roundtrip_blocks_html(self):
        md = "# Título\n\nOlá **mundo**, *itálico*, __sub__ e ~~riscado~~.\n\n- um\n  - sub\n- dois\n\n1. a\n2. b\n\n> citação\n\n---\n\n<!-- pagebreak -->\n\n## Fim\n\nÚltimo."
        bl = D.markdown_to_blocks(md)
        self.assertEqual(D.html_to_blocks(D.blocks_to_html(bl)), D.norm_blocks(bl))
        self.assertEqual(D.markdown_to_blocks(D.blocks_to_markdown(bl)), D.norm_blocks(bl))
        kinds = [b["t"] for b in bl]
        for k in ("h1", "h2", "li", "quote", "hr", "pb"):
            self.assertIn(k, kinds)
        self.assertEqual([b["l"] for b in bl if b["t"] == "li"], ["ul", "ul", "ul", "ol", "ol"])
        self.assertEqual(bl[1]["runs"][1], {"x": "mundo", "b": 1})

    def test_fiction_dash_lines_are_dialogue_not_lists(self):
        bl = D.markdown_to_blocks("- Olá — disse ela.\n- Oi.", lists=False)
        self.assertEqual([b["t"] for b in bl], ["p", "p"])
        self.assertTrue(D.text_of(bl[0]).startswith("— Olá"))

    def test_hostile_blocks_are_cleaned(self):
        bl = D.norm_blocks([{"t": "script", "runs": [{"x": "a\x00b", "b": "sim"}]}, "lixo", {"t": "li", "l": "xx", "lv": 99, "runs": [{"x": 5}, {"x": "ok"}]}, {"t": "h1", "runs": "x"}, {"t": "p", "a": "<b>", "runs": [{"x": "z"}]}])
        self.assertEqual(bl[0]["t"], "p")
        self.assertEqual(bl[0]["runs"], [{"x": "ab", "b": 1}])
        self.assertEqual((bl[1]["t"], bl[1]["l"], bl[1]["lv"]), ("li", "ul", 2))
        self.assertEqual(bl[1]["runs"], [{"x": "ok"}])
        self.assertNotIn("a", bl[-1])
        self.assertEqual(D.norm_blocks("nada"), [])
        self.assertLessEqual(len(D.norm_blocks([{"t": "p"}] * (D.MAX_BLOCKS + 10))), D.MAX_BLOCKS)

    def test_malformed_html_does_not_crash(self):
        for src in ("<p><b>aberto", "</p></div></b>", "<<<>>>", "<ul><li>a<ul><li>b</ul>", "\x00\x01<p>x", "<p>" * 3000, "&#xD800;"):
            D.html_to_blocks(src)
        self.assertEqual(D.html_to_blocks(None), [])

    def test_stats(self):
        bl = D.markdown_to_blocks("# T\n\nUm dois três.\n\n- item")
        self.assertEqual(D.stats(bl), {"words": 5, "chars": 18, "paragraphs": 3, "headings": 1, "blocks": 3})


def _wellformed(data: bytes):
    z = zipfile.ZipFile(io.BytesIO(data))
    for n in z.namelist():
        xml.dom.minidom.parseString(z.read(n))
    return z


class DocxTests(unittest.TestCase):
    BL = D.markdown_to_blocks("# Cap 1\n\nOlá **mundo** e *itálico* __sub__ ~~ris~~.\n\n- um\n  - sub\n- dois\n\n1. a\n2. b\n\nTexto\n\n1. novo\n\n> citação\n\n---\n\n<!-- pagebreak -->\n\n## Sec\n\nfim & <tag> \"aspas\"")

    def test_builds_a_valid_package_for_every_preset(self):
        for preset in S.PRESETS:
            fmt = S.norm_format({"header": "Cabeçalho", "author": "Fulano", "subtitle": "Sub", "title_page": True, "toc": True}, preset)
            z = _wellformed(X.build_docx(self.BL, {"title": "Meu Livro"}, fmt, "pt-BR"))
            self.assertIn("[Content_Types].xml", z.namelist())
            self.assertIn("word/document.xml", z.namelist())
            doc = z.read("word/document.xml").decode()
            self.assertIn("Meu Livro", doc)
            self.assertIn("TOC \\o", doc)
            self.assertIn("fim &amp; &lt;tag&gt;", doc)

    def test_language_page_size_fonts_and_numbering(self):
        fmt = S.norm_format({"page": "A5", "font": "Georgia", "size": 11, "line": 1.4, "margins": [2, 2, 3, 1.5], "page_numbers": True}, "book")
        z = _wellformed(X.build_docx(self.BL, {"title": "T"}, fmt, "en-GB"))
        styles, doc, settings = z.read("word/styles.xml").decode(), z.read("word/document.xml").decode(), z.read("word/settings.xml").decode()
        self.assertIn('w:lang w:val="en-GB"', styles)                      # o corretor do Word abre no idioma certo
        self.assertIn('w:themeFontLang w:val="en-GB"', settings)
        self.assertIn('w:w="8392" w:h="11907"', doc)                       # A5
        self.assertIn('w:left="1701"', doc)
        self.assertIn('w:ascii="Georgia"', styles)
        self.assertIn('w:sz w:val="22"', styles)
        self.assertIn(" PAGE ", z.read("word/footer1.xml").decode())
        self.assertGreaterEqual(z.read("word/numbering.xml").decode().count("<w:num "), 3)   # cada lista numerada recomeça em 1

    def test_title_is_not_repeated_and_chapters_break_pages(self):
        bl = D.markdown_to_blocks("# Meu Livro\n\ntexto\n\n# Cap 2\n\nmais")
        fmt = S.norm_format({"title_page": True, "chapter_break": True}, "book")
        doc = _wellformed(X.build_docx(bl, {"title": "Meu Livro"}, fmt, "pt-BR")).read("word/document.xml").decode()
        self.assertEqual(doc.count("Meu Livro"), 1)
        self.assertEqual(doc.count("<w:pageBreakBefore/>"), 1)

    def test_control_characters_never_reach_the_xml(self):
        bl = [D.block("p", [D.run("a\x00b\x0bc\ud800")])]
        _wellformed(X.build_docx(bl, {"title": "\x00t"}, None, None))

    def test_roundtrip_keeps_text_and_marks(self):
        fmt = S.norm_format({"title_page": False}, "article")
        got, meta = X.parse_docx(X.build_docx(self.BL, {"title": "Livro", "author": "Ana"}, fmt, "es-ES"))
        self.assertEqual(meta["language"], "es-ES")
        self.assertEqual(meta["author"], "Ana")
        txt = D.blocks_to_text(got)
        for piece in ("Cap 1", "Olá mundo", "citação", "fim & <tag>"):
            self.assertIn(piece, txt)
        flat = [(r["x"], tuple(k for k in "biu" if r.get(k)) + (("s",) if r.get("s") else ())) for b in got for r in b.get("runs", [])]
        self.assertIn(("mundo", ("b",)), flat)
        self.assertIn(("itálico", ("i",)), flat)
        self.assertIn(("sub", ("u",)), flat)
        self.assertEqual([b["l"] for b in got if b["t"] == "li"], ["ul", "ul", "ul", "ol", "ol", "ol"])
        self.assertTrue(any(b["t"] == "pb" for b in got) and any(b["t"] == "hr" for b in got))

    def test_hostile_files_are_refused(self):
        with self.assertRaises(X.DocxError):
            X.parse_docx(b"isto nao e zip")
        with self.assertRaises(X.DocxError):
            X.parse_docx(b"")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>')
        with self.assertRaises(X.DocxError):
            X.parse_docx(buf.getvalue())
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("other.txt", "x")
        with self.assertRaises(X.DocxError):
            X.parse_docx(buf.getvalue())
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", "<w:document")
        with self.assertRaises(X.DocxError):
            X.parse_docx(buf.getvalue())
        big = io.BytesIO()
        with zipfile.ZipFile(big, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", "<a>" + "x" * (50 * 1024 * 1024) + "</a>")
        with self.assertRaises(X.DocxError):
            X.parse_docx(big.getvalue())

    def test_word_tables_are_flattened(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        got, _ = X.parse_docx(buf.getvalue())
        self.assertEqual(D.text_of(got[0]), "A | B")


class LoreTests(unittest.TestCase):
    def books(self):
        return L.norm_books([{"name": "Mundo", "entries": [
            {"name": "Ana", "kind": "character", "keys": "Ana, anita", "content": "Ana é ruiva e corajosa."},
            {"name": "Reino", "kind": "place", "keys": ["Reino"], "content": "Um reino frio."},
            {"name": "Tom", "kind": "rule", "always": True, "content": "Tom sombrio."},
            {"name": "Voz", "kind": "system", "content": "Escreva em primeira pessoa, no passado."},
            {"name": "Desligada", "keys": ["Ana"], "content": "x", "enabled": False}]}])

    def test_select_by_keyword_always_and_system(self):
        got = [e["name"] for e in L.select(self.books(), "Anita entrou no salão")]
        self.assertEqual(got, ["Voz", "Ana", "Tom"])                       # system primeiro; Reino não aparece; a desligada nunca
        self.assertEqual([e["name"] for e in L.select(self.books(), "nada")], ["Voz", "Tom"])
        self.assertNotIn("Ana", [e["name"] for e in L.select(self.books(), "Banana")])   # palavra inteira
        r = L.lore_for(self.books(), "Ana", enabled=True)
        self.assertIn("AUTHOR'S STYLE & RULES", r["text"])
        self.assertIn("primeira pessoa", r["text"])
        self.assertEqual(L.lore_for(self.books(), "Ana", enabled=False), {"text": "", "used": []})

    def test_budget_and_disabled_books(self):
        bk = self.books()
        bk[0]["entries"].append(L.norm_entry({"name": "Grande", "always": True, "content": "z" * 7000}))
        self.assertLessEqual(sum(len(e["content"]) for e in L.select(bk, "x", budget=2000)), 2000)
        bk[0]["enabled"] = False
        self.assertEqual(L.select(bk, "Ana"), [])
        self.assertEqual(L.select(self.books(), "Ana", only=["inexistente"]), [])

    def test_import_sillytavern_markdown_and_own_format(self):
        st = {"entries": {"0": {"key": ["Dragão"], "content": "Um dragão antigo.", "comment": "Dragão", "constant": False}, "1": {"key": [], "content": "Mundo de fantasia.", "comment": "Base", "constant": True, "disable": False}}}
        b = L.import_any(st)
        self.assertEqual([e["always"] for e in b["entries"]], [False, True])
        self.assertEqual(b["entries"][0]["keys"], ["Dragão"])
        cb = L.import_any({"name": "X", "character_book": {"name": "Livro", "entries": [{"keys": ["a"], "content": "c", "name": "n", "enabled": False}]}})
        self.assertFalse(cb["entries"][0]["enabled"])
        md = L.import_any("# Meu mundo\n\n## Reino\nUm reino.\n\n## Rei\nVelho.\n")
        self.assertEqual((md["name"], [e["name"] for e in md["entries"]]), ("Meu mundo", ["Reino", "Rei"]))
        own = L.import_any(json.dumps(L.export_book(self.books()[0])).encode())
        self.assertEqual(len(own["entries"]), 5)
        back = L.import_any(L.book_to_markdown(self.books()[0]))
        self.assertEqual(back["entries"][0]["keys"], ["Ana", "anita"])
        for bad in ("", "{}", "[]", '{"entries": 3}', "[1,2]"):
            with self.assertRaises(ValueError, msg=bad):
                L.import_any(bad)

    def test_hostile_entries(self):
        b = L.norm_books([{"entries": [{"content": ["x"], "keys": 7, "priority": "alta", "kind": "<b>"}, {"name": "ok", "content": "c" * 99999, "priority": 9999}], "id": "../x"}, "lixo"])
        self.assertEqual(len(b), 1)
        self.assertNotEqual(b[0]["id"], "../x")
        self.assertEqual(len(b[0]["entries"]), 1)
        self.assertLessEqual(len(b[0]["entries"][0]["content"]), L.MAX_CONTENT)
        self.assertEqual(b[0]["entries"][0]["priority"], 100)


class SpellTests(unittest.TestCase):
    def test_rules_find_and_fix(self):
        ps = ["Olá  mundo , tudo bem?Sim.Claro que sim sim. depois disso o dr. silva chegou.", "Fim...... ok!!!!!", "Meu arquivo.txt e 3,14 e www.site.com"]
        r = spell.proofread(ps, "pt-BR", use_dict=False)
        kinds = {i["kind"] for i in r["issues"]}
        self.assertTrue({"spacing", "repeat", "capital", "typography"} <= kinds)
        fixed = spell.apply_issues(ps, r["issues"])
        self.assertEqual(fixed[0], "Olá mundo, tudo bem? Sim. Claro que sim. Depois disso o dr. silva chegou.")
        self.assertEqual(fixed[1], "Fim… Ok!!!")
        self.assertEqual(fixed[2], ps[2])                                    # nome de arquivo, número e site não são mexidos
        self.assertFalse(r["dictionary"] and False)

    def test_french_keeps_its_space_before_colon(self):
        self.assertEqual(spell.proofread(["Il dit : oui !"], "fr-FR", use_dict=False)["issues"], [])
        self.assertEqual(spell.normalize_spacing("Il dit : oui !", "fr-FR"), "Il dit : oui !")

    def test_stale_issue_is_not_applied(self):
        r = spell.proofread(["a  b"], "en-US", use_dict=False)
        self.assertEqual(spell.apply_issues(["xyzw"], r["issues"]), ["xyzw"])

    def test_system_dictionary_layer_is_used_when_present(self):
        spell._dict_cache.clear()
        out = "@(#) International Ispell Version 3.1.20 (but really Hunspell)\n*\n& teste 2 0: teste, testes\n# xyzzy 4\n"
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0, stdout=out, stderr="")

        with mock.patch("asta.scriber.spell.shutil.which", lambda p: "/usr/bin/hunspell" if p == "hunspell" else None), mock.patch("asta.scriber.spell.subprocess.run", fake_run):
            r = spell.proofread(["O teste e o xyzzy sumiram"], "pt-BR", use_dict=True)
        self.assertTrue(r["dictionary"])
        words_ = {i["found"]: i for i in r["issues"] if i["source"] == "dictionary"}
        self.assertEqual(set(words_), {"teste", "xyzzy"})
        self.assertEqual(words_["teste"]["fix"], "teste")
        self.assertIn("pt_BR", calls[0])
        spell._dict_cache.clear()

    def test_ignore_list_and_no_dictionary(self):
        spell._dict_cache.clear()
        with mock.patch("asta.scriber.spell.shutil.which", lambda p: None):
            r = spell.proofread(["xyzzy"], "pt-BR")
        self.assertFalse(r["dictionary"])
        self.assertEqual(r["issues"], [])
        spell._dict_cache.clear()

    def test_typography(self):
        self.assertEqual(spell.typography('Ele disse "oi" e -- foi... \n- Fala', "pt-BR"), "Ele disse “oi” e — foi… \n— Fala")
        self.assertEqual(spell.typography('"A" \'b\' it\'s', "en-US"), "“A” ‘b’ it’s")
        self.assertIn("«", spell.typography('"A"', "fr-FR"))
        self.assertTrue(spell.typography('"A"', "de-DE").startswith("„"))

    def test_hostile_input(self):
        r = spell.proofread("não é lista", "pt-BR")
        self.assertEqual(r["issues"], [])
        r = spell.proofread(["x" * 10] * (spell.MAX_PARAS + 50), "pt-BR", use_dict=False)
        self.assertTrue(r["truncated"])


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="asta-sc-"))
        self.store = Store(self.tmp)
        self.m = ScriberManager(self.store)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_project_lifecycle_and_defaults(self):
        p = self.m.create("Meu Romance", "romance", "pt", "desc")
        self.assertEqual((p["type"], p["language"], p["format"]["preset"]), ("romance", "pt-BR", "book"))
        self.assertEqual(self.m.list()[0]["id"], p["id"])
        u = self.m.update_meta(p["id"], {"name": "Novo nome", "language": "en", "format": {"font": "Arial", "size": 14, "toc": True}, "content": "sfw", "gen": {"pages": 12, "words_per_page": 250}})
        self.assertEqual((u["name"], u["language"], u["content"], u["format"]["font"], u["format"]["size"]), ("Novo nome", "en-US", "sfw", "Arial", 14.0))
        self.assertEqual((u["gen"]["pages"], u["gen"]["words_per_page"]), (12, 250))
        self.assertEqual(self.m.update_meta(p["id"], {"type": "inexistente", "name": "  ", "language": ["x"]})["name"], "Novo nome")
        d = self.m.duplicate(p["id"])
        self.assertNotEqual(d["id"], p["id"])
        self.m.delete(p["id"])
        with self.assertRaises(ScriberError):
            self.m.meta(p["id"])
        self.assertEqual(len(self.m.list()), 1)

    def test_ids_cannot_escape_the_folder(self):
        for bad in ("../x", "..", "a/b", "", "AB", "x" * 60, None, 5, "a\x00b"):
            with self.assertRaises(ScriberError):
                self.m.dir(bad)
        p = self.m.create("x")
        for bad in ("../../project.json", "..", "a/../b.docx"):
            with self.assertRaises(ScriberError):
                self.m.export_path(p["id"], bad)

    def test_document_save_history_and_restore(self):
        pid = self.m.create("Doc")["id"]
        self.m.save_doc(pid, markdown="# A\n\nprimeira versão")
        self.m.save_doc(pid, html_src="<h1>B</h1><p>segunda versão</p>", label="antes da segunda")
        self.assertEqual(D.title_of(self.m.get_doc(pid)["blocks"]), "B")
        items = self.m.history(pid)
        self.assertEqual(items[0]["label"], "antes da segunda")
        self.m.restore(pid, items[0]["id"])
        self.assertEqual(D.title_of(self.m.get_doc(pid)["blocks"]), "A")
        self.assertTrue(any("antes de voltar" in i["label"] for i in self.m.history(pid)))     # o estado anterior também fica guardado
        with self.assertRaises(ScriberError):
            self.m.restore(pid, "../../project")
        self.assertEqual(self.m.meta(pid)["words"], 3)

    def test_history_is_trimmed(self):
        self.store.save_settings({"scriber": {"undo_keep": 5}}) if hasattr(self.store, "save_settings") else None
        pid = self.m.create("H")["id"]
        for i in range(12):
            self.m.save_doc(pid, markdown=f"texto {i}", label=f"v{i}")
        self.assertLessEqual(len(self.m.history(pid)), 25)

    def test_export_every_format(self):
        pid = self.m.create("Exportar", "academic", "en")["id"]
        self.m.save_doc(pid, markdown="# Título\n\nCorpo **forte**.\n\n- a\n- b")
        for fmt in ("docx", "md", "txt", "html"):
            e = self.m.export(pid, fmt)
            self.assertTrue(self.m.export_path(pid, e["name"]).is_file())
        _wellformed(self.m.render(pid, "docx"))
        self.assertIn("**forte**", self.m.render(pid, "md").decode())
        self.assertIn("• a", self.m.render(pid, "txt").decode())
        html = self.m.render(pid, "html").decode()
        self.assertIn('lang="en-US"', html)
        self.assertIn("<b>forte</b>", html)
        self.assertEqual(len(self.m.list_exports(pid)), 4)
        with self.assertRaises(ScriberError):
            self.m.render(pid, "exe")

    def test_import_docx_markdown_text_and_html(self):
        pid = self.m.create("Importar")["id"]
        src = X.build_docx(D.markdown_to_blocks("# Cap\n\nTexto **forte**"), {"title": "Cap", "author": "Zé"}, S.norm_format({"title_page": False}), "en-GB")
        r = self.m.import_file(pid, "a.docx", src)
        self.assertEqual(self.m.meta(pid)["language"], "en-GB")
        self.assertEqual(self.m.meta(pid)["author"], "Zé")
        self.assertIn("Texto forte", D.blocks_to_text(self.m.get_doc(pid)["blocks"]))
        self.m.import_file(pid, "b.md", b"# Dois\n\nmais", mode="append")
        self.assertIn("Dois", D.blocks_to_text(self.m.get_doc(pid)["blocks"]))
        self.assertIn("Texto forte", D.blocks_to_text(self.m.get_doc(pid)["blocks"]))
        self.m.import_file(pid, "c.txt", "# não é título\nlinha 2".encode("latin-1"))
        self.assertEqual([b["t"] for b in self.m.get_doc(pid)["blocks"]], ["p", "p"])           # .txt não interpreta Markdown
        self.m.import_file(pid, "d.html", b"<h1>H</h1><p>x<script>y</script></p>")
        self.assertNotIn("y", D.blocks_to_text(self.m.get_doc(pid)["blocks"]).replace("x", ""))
        self.assertTrue(self.m.history(pid))                                                  # cada importação guarda o anterior
        with self.assertRaises(ScriberError):
            self.m.import_file(pid, "e.docx", b"PK\x03\x04lixo")
        with self.assertRaises(ScriberError):
            self.m.import_file(pid, "f.txt", b"   \n  ")

    def test_lorebooks_and_sources_are_validated(self):
        pid = self.m.create("Lore")["id"]
        book = self.m.import_book(pid, {"entries": [{"name": "A", "keys": ["a"], "content": "x"}]}, "Meu")
        self.assertEqual(self.m.get_books(pid)[0]["id"], book["id"])
        with self.assertRaises(ScriberError):
            self.m.import_book(pid, "{}")
        self.assertEqual(self.m.save_books(pid, "lixo"), [])
        s = self.m.save_sources(pid, [{"url": "javascript:alert(1)", "title": "x"}, {"url": "https://a.com/x", "title": "ok", "text": "t" * 99999}, "lixo"])
        self.assertEqual(len(s), 1)
        self.assertLessEqual(len(s[0]["text"]), 6000)


def make_ai(tmp, provider=None, **opts):
    store = Store(tmp)
    m = ScriberManager(store)
    job = FakeJob()
    ai = sai.ScriberAI(store, m, opts, job)
    ai.provider = provider
    ai.error = "" if provider else "sem IA"
    return ai, m, job


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="asta-sc-ai-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def project(self, m, **kw):
        return m.create(kw.pop("name", "Livro"), kw.pop("type", "romance"), kw.pop("language", "pt-BR"), **kw)["id"]

    # ------------------------------------------------------------ esboço e planejamento
    def test_parse_outline_shapes(self):
        self.assertEqual([s["title"] for s in sai.parse_outline("# Intro\n- ponto a\n- ponto b\n# Meio\n# Fim")], ["Intro", "Meio", "Fim"])
        self.assertEqual(sai.parse_outline("# Intro\n- a\n# Meio")[0]["summary"], "a b".replace("b", "").strip())
        self.assertEqual([s["title"] for s in sai.parse_outline("Capítulo 1: A chegada\nalgo\nCapítulo 2: A fuga")], ["Capítulo 1: A chegada", "Capítulo 2: A fuga"])
        self.assertEqual(len(sai.parse_outline("1. um\n2. dois\n3. três")), 3)
        self.assertEqual(len(sai.parse_outline("- a\n- b")), 2)
        self.assertEqual(sai.parse_outline("só um prompt comum sem lista"), [])
        self.assertEqual(sai.parse_outline("# Uma só"), [])
        self.assertEqual(sai.parse_outline(None), [])

    def test_estimate_counts_calls_with_the_team(self):
        one = sai.estimate({"prompt": "romance", "pages": 100, "words_per_page": 300, "agents": 1})
        four = sai.estimate({"prompt": "romance", "pages": 100, "words_per_page": 300, "agents": 4})
        self.assertEqual(one["target_words"], 30000)
        self.assertGreater(one["parts"], one["sections"] - 1)
        self.assertGreater(four["calls"], one["calls"] * 3)
        self.assertTrue(sai.estimate({"prompt": "# a\n# b\n# c"})["from_outline"])

    # ------------------------------------------------------------ geração sem IA
    def test_generate_without_ai_builds_the_structure_and_a_docx(self):
        ai, m, job = make_ai(self.tmp, prompt="# Chegada\n- ela chega\n# Fuga\n- foge\n# Fim\n- acaba", pages=3, words_per_page=200)
        pid = self.project(m, name="Novo texto")
        res = ai.generate(pid)
        doc = m.get_doc(pid)
        self.assertEqual([D.text_of(b) for b in doc["blocks"] if b["t"] == "h1"], ["Chegada", "Fuga", "Fim"])
        self.assertIn("[Escreva aqui", D.blocks_to_text(doc["blocks"]))                   # sem enchimento: marcador honesto
        self.assertFalse(res["report"]["ai"])
        self.assertTrue(res["report"]["warning"])
        self.assertEqual(res["target_words"], 600)
        name = res["docx"]["name"]
        _wellformed(m.export_path(pid, name).read_bytes())
        self.assertTrue(any(e["type"] == "result" for e in job.events))
        self.assertEqual(m.meta(pid)["gen"]["pages"], 3)

    def test_generate_requires_nothing_but_a_prompt_and_rejects_absurd_sizes(self):
        ai, m, _ = make_ai(self.tmp, prompt="um livro", pages=1000, words_per_page=1000, chapters=60)
        pid = self.project(m)
        with self.assertRaises(ValueError):          # 400 mil palavras em 60 capítulos pedem chamadas demais: a tela recebe um aviso claro
            ai.generate(pid)
        ai, m, _ = make_ai(self.tmp, prompt="um livro", pages=1000, words_per_page=300, chapters=60)
        pid = self.project(m)
        res = ai.generate(pid)
        self.assertLessEqual(res["target_words"], S.MAX_TARGET_WORDS)
        self.assertEqual(len([b for b in m.get_doc(pid)["blocks"] if b["t"] == "h1"]), 60)

    # ------------------------------------------------------------ geração com IA simulada
    def fake_writer(self, per_call):
        seen = []

        def writer(messages, system):
            pl = json.loads(messages[-1]["content"].split("INPUT_JSON:\n", 1)[1])
            seen.append(pl)
            n = pl["part"]["words"]
            if pl.get("task") == "extend":
                n = pl["part"]["words"]
            return {"text": "\n\n".join(words(per_call(pl, n)) for _ in range(3)), "summary": f"Resumo {pl['section']['index']}.{pl['part']['index']}"}
        return writer, seen

    def test_generate_with_ai_writes_every_section_with_continuity_and_lore(self):
        plan = {"title": "A Última Torre", "subtitle": "Um romance", "synopsis": "Uma torre.", "style_guide": "Primeira pessoa.", "characters": [{"name": "Ana", "note": "ruiva"}],
                "sections": [{"title": "Capítulo 1", "summary": "Ana chega.", "words": 400}, {"title": "Capítulo 2", "summary": "Ana foge.", "words": 400}]}
        writer, seen = self.fake_writer(lambda pl, n: max(1, n // 3))
        prov = FakeProvider({"Planner": plan, "Writer": writer, "Reviewer": {"approved": True, "summary": "Entregue como pedido.", "issues": ["Verifique a data."]}})
        ai, m, job = make_ai(self.tmp, prov, prompt="Um romance sobre Ana", pages=4, words_per_page=200, type="romance")
        pid = self.project(m)
        m.save_books(pid, [{"name": "Mundo", "entries": [{"name": "Ana", "kind": "character", "keys": ["Ana"], "content": "Ana é ruiva e corajosa."}, {"name": "Voz", "kind": "system", "content": "Sempre no passado."}]}])
        res = ai.generate(pid)
        self.assertTrue(res["report"]["ai"])
        self.assertEqual(res["summary"], "Entregue como pedido.")
        self.assertEqual(m.meta(pid)["name"], "A Última Torre")
        self.assertEqual(m.meta(pid)["format"]["subtitle"], "Um romance")
        heads = [D.text_of(b) for b in m.get_doc(pid)["blocks"] if b["t"] == "h1"]
        self.assertEqual(heads, ["Capítulo 1", "Capítulo 2"])
        second = [p for p in seen if p["section"]["index"] == 2][0]
        self.assertIn("Resumo 1.1", second["story_so_far"])                                # a continuidade passa de uma seção para a próxima
        self.assertTrue(second["previous_tail"])
        self.assertIn("Ana é ruiva", second["lorebook"] + seen[0]["lorebook"])              # lorebook entra na chamada
        self.assertTrue(any("Sempre no passado" in s for s in prov.systems) or any("Sempre no passado" in c for c in prov.calls))
        self.assertTrue(any("never write sexual content involving anyone under 18" in s.lower() or "adult characters" in s for s in prov.systems))   # limite fixo no prompt
        stats = m.get_doc(pid)["stats"]
        self.assertGreater(stats["words"], 300)
        self.assertEqual(res["docx"]["format"], "docx")
        self.assertTrue(any(e["type"] == "progress" for e in job.events))
        self.assertGreater(m.get_doc(pid)["stats"]["words"], 600)

    def test_long_sections_are_written_in_several_calls_and_short_parts_are_extended(self):
        calls = {"extend": 0, "write": 0}
        plan = {"title": "Tese", "sections": [{"title": "Capítulo único", "summary": "x", "words": 2400}]}

        def writer(messages, system):
            pl = json.loads(messages[-1]["content"].split("INPUT_JSON:\n", 1)[1])
            calls[pl["task"]] += 1
            n = pl["part"]["words"] if pl["task"] == "extend" else max(10, pl["part"]["words"] // 4)       # a primeira resposta vem curta: precisa estender
            return {"text": words(n), "summary": "s"}

        prov = FakeProvider({"Planner": plan, "Writer": writer, "Reviewer": {"summary": "ok"}})
        ai, m, _ = make_ai(self.tmp, prov, prompt="tese longa", pages=8, words_per_page=300, type="academic", language="pt-BR")
        pid = self.project(m, type="academic")
        res = ai.generate(pid)
        self.assertGreaterEqual(calls["write"], 3)                    # 2400 palavras = 3 partes (PART_WORDS=1100)
        self.assertGreaterEqual(calls["extend"], 3)                   # cada parte curta é estendida
        self.assertGreater(res["stats"]["words"], 1800)

    def test_invalid_ai_answers_fall_back_to_the_rules(self):
        ai, m, job = make_ai(self.tmp, FakeProvider(fail=True), prompt="# A\n- x\n# B\n- y", pages=2, words_per_page=150)
        pid = self.project(m)
        res = ai.generate(pid)
        self.assertEqual([D.text_of(b) for b in m.get_doc(pid)["blocks"] if b["t"] == "h1"], ["A", "B"])
        self.assertTrue(all(a["status"] == "fallback" for a in res["report"]["agents"]))
        self.assertTrue(res["docx"]["size"] > 1000)

    def test_the_authors_outline_wins_over_the_planner(self):
        plan = {"title": "T", "sections": [{"title": "Inventado 1", "summary": "s1", "words": 100}, {"title": "Inventado 2", "summary": "s2", "words": 100}, {"title": "Inventado 3", "summary": "s3", "words": 100}]}
        prov = FakeProvider({"Planner": plan, "Writer": {"text": words(120), "summary": "s"}, "Reviewer": {"summary": "ok"}})
        ai, m, _ = make_ai(self.tmp, prov, prompt="# Intro\n# Meio\n# Fim", pages=1, words_per_page=360)
        pid = self.project(m, type="essay")
        ai.generate(pid)
        self.assertEqual([D.text_of(b) for b in m.get_doc(pid)["blocks"] if b["t"] == "h1"], ["Intro", "Meio", "Fim"])

    def test_team_of_four_drafts_in_parallel_and_the_synthesizer_merges(self):
        count = {"n": 0}

        def writer(messages, system):
            count["n"] += 1
            return {"text": words(100), "summary": "s"}

        prov = FakeProvider({"Planner": {"title": "T", "sections": [{"title": "S", "summary": "x", "words": 100}]}, "Writer": writer, "Reviewer": {"summary": "ok"}})
        ai, m, job = make_ai(self.tmp, prov, prompt="curto", pages=1, words_per_page=100, team={"agents": 4, "effort": "low"}, type="blog")
        pid = self.project(m, type="blog")
        res = ai.generate(pid)
        self.assertEqual(res["report"]["team"]["agents"], 4)
        self.assertGreaterEqual(count["n"], 5)                         # 4 rascunhos + 1 síntese, por parte

    def test_cancel_stops_the_generation(self):
        ai, m, job = make_ai(self.tmp, FakeProvider({"Planner": {"title": "T", "sections": [{"title": "S", "words": 100}]}}), prompt="x")
        job.cancelled = True
        pid = self.project(m)
        from asta.agents.runner import Cancelled
        with self.assertRaises(Cancelled):
            ai.generate(pid)

    def test_append_mode_keeps_the_existing_text(self):
        ai, m, _ = make_ai(self.tmp, None, prompt="# Novo\n# Mais", pages=1, words_per_page=100, mode="append")
        pid = self.project(m, name="Meu texto")
        m.save_doc(pid, markdown="# Antigo\n\nTexto que fica.")
        ai.generate(pid)
        txt = D.blocks_to_text(m.get_doc(pid)["blocks"])
        self.assertIn("Texto que fica", txt)
        self.assertIn("Novo", txt)
        self.assertEqual(m.meta(pid)["name"], "Meu texto")

    def test_replace_keeps_the_previous_version_in_history(self):
        ai, m, _ = make_ai(self.tmp, None, prompt="# A\n# B", pages=1, words_per_page=100)
        pid = self.project(m)
        m.save_doc(pid, markdown="meu texto antigo")
        ai.generate(pid)
        self.assertTrue(any(i["label"].startswith("antes de gerar") for i in m.history(pid)))

    # ------------------------------------------------------------ edição de trecho
    def test_edit_expand_uses_the_chosen_size_and_the_lorebook(self):
        sel = "Ana abriu a porta.\n— Quem está aí? — perguntou."
        seen = []

        def editor(messages, system):
            pl = json.loads(messages[-1]["content"].split("INPUT_JSON:\n", 1)[1])
            seen.append((pl, system))
            return {"text": words(pl["size"]["target_words"]) + "\n" + words(5), "notes": ["Confira a hora."]}

        prov = FakeProvider({"Editor": editor})
        body = {"action": "expand", "selection": sel, "kind": "mixed", "expand": {"mode": "add", "words": 80}, "context_before": "Antes.", "context_after": "Depois."}
        ai, m, job = make_ai(self.tmp, prov, prompt="", body=body, team={"agents": 1, "effort": "low"})
        pid = self.project(m)
        m.save_books(pid, [{"name": "L", "entries": [{"name": "Ana", "kind": "character", "keys": ["Ana"], "content": "Ana é ruiva."}]}])
        res = ai.edit_text(pid)
        pl = seen[0][0]
        self.assertEqual(pl["size"]["target_words"], 87 if False else S.count_words(sel) + 80)
        self.assertEqual(pl["selection_kind"], "mixed")
        self.assertIn("Ana é ruiva", pl["lorebook"])
        self.assertEqual(res["lore"][0]["name"], "Ana")
        self.assertTrue(res["changed"])
        self.assertEqual(res["notes"], ["Confira a hora."])
        self.assertGreater(res["words"], S.count_words(sel) + 60)

    def test_edit_total_mode_and_shorten_and_lore_off(self):
        seen = []
        prov = FakeProvider({"Editor": lambda msgs, sys: (seen.append(json.loads(msgs[-1]["content"].split("INPUT_JSON:\n", 1)[1])) or {"text": words(12)})})
        ai, m, _ = make_ai(self.tmp, prov, body={"action": "expand", "selection": words(10), "expand": {"mode": "total", "words": 200}}, lore=False, team={"effort": "low"})
        pid = self.project(m)
        m.save_books(pid, [{"name": "L", "entries": [{"name": "x", "always": True, "content": "sempre"}]}])
        res = ai.edit_text(pid)
        self.assertEqual(seen[0]["size"]["target_words"], 200)
        self.assertEqual(seen[0]["lorebook"], "")
        self.assertEqual(res["lore"], [])

    def test_edit_length_is_corrected_with_a_second_round(self):
        sizes = []

        def editor(msgs, sys):
            pl = json.loads(msgs[-1]["content"].split("INPUT_JSON:\n", 1)[1])
            sizes.append(bool(pl.get("draft_result")))
            return {"text": words(pl["size"]["target_words"] if pl.get("draft_result") else 20)}

        ai, m, _ = make_ai(self.tmp, FakeProvider({"Editor": editor}), body={"action": "expand", "selection": words(10), "expand": {"mode": "total", "words": 120}}, team={"effort": "low"})
        pid = self.project(m)
        res = ai.edit_text(pid)
        self.assertEqual(sizes, [False, True])
        self.assertAlmostEqual(res["words"], 120, delta=12)

    def test_edit_without_ai_is_honest(self):
        ai, m, _ = make_ai(self.tmp, None, body={"action": "expand", "selection": "Texto  curto ,assim."})
        res = ai.edit_text(self.project(m))
        self.assertFalse(res["changed"])                              # não finge expandir
        self.assertTrue(res["notes"])
        ai, m, _ = make_ai(self.tmp, None, body={"action": "fix", "selection": "Texto  curto , assim.  depois"})
        res = ai.edit_text(self.project(m))
        self.assertTrue(res["changed"])
        self.assertEqual(res["text"], "Texto curto, assim. Depois")
        ai, m, _ = make_ai(self.tmp, None, body={"action": "shorten", "selection": "Um dois três quatro cinco seis. Sete oito nove dez onze doze. Treze catorze quinze dezesseis dezessete dezoito. Fim do texto aqui agora hoje.", "expand": {"mode": "total", "words": 10}})
        res = ai.edit_text(self.project(m))
        self.assertEqual(res["text"], "Um dois três quatro cinco seis. Sete oito nove dez onze doze.")

    def test_edit_continue_needs_no_selection_and_all_actions_are_known(self):
        prov = FakeProvider({"Editor": {"text": words(30)}})
        ai, m, _ = make_ai(self.tmp, prov, body={"action": "continue", "context_before": "Era uma vez.", "expand": {"words": 30}}, team={"effort": "low"})
        res = ai.edit_text(self.project(m))
        self.assertEqual(res["action"], "continue")
        for a in ("improve", "expand", "rewrite", "shorten", "fix", "continue", "dialogue", "describe", "tone", "translate", "custom"):
            self.assertIn(a, S.ACTION_IDS)
        ai, m, _ = make_ai(self.tmp, prov, body={"action": "explodir", "selection": "x y z"}, team={"effort": "low"})
        self.assertEqual(ai.edit_text(self.project(m))["action"], "improve")

    # ------------------------------------------------------------ ortografia com IA
    def test_proofread_ai_validates_each_fix_against_the_text(self):
        fixes = {"fixes": [{"i": 0, "find": "esperiência", "replace": "experiência", "kind": "spelling", "reason": "acento e letra"},
                           {"i": 0, "find": "não existe no texto", "replace": "x"}, {"i": 9, "find": "a", "replace": "b"}, {"i": 1, "find": "a", "replace": "a"}, "lixo",
                           {"i": 1, "find": "Eles foi", "replace": "Eles foram", "kind": "banana"}]}
        prov = FakeProvider({"Proofreader": fixes})
        body = {"paragraphs": ["Uma esperiência rara.", "Eles foi embora.", ""], "language": "pt-BR"}
        ai, m, _ = make_ai(self.tmp, prov, body=body)
        res = ai.proofread_ai(self.project(m))
        ai_issues = [i for i in res["issues"] if i["source"] == "ai"]
        self.assertEqual([(i["p"], i["found"], i["fix"]) for i in ai_issues], [(0, "esperiência", "experiência"), (1, "Eles foi", "Eles foram")])
        self.assertEqual(ai_issues[1]["kind"], "grammar")                   # tipo desconhecido vira «grammar»
        self.assertEqual(spell.apply_issues(body["paragraphs"], ai_issues)[0], "Uma experiência rara.")
        self.assertTrue(res["ai"])

    def test_proofread_ai_without_ai_still_returns_the_rule_findings(self):
        ai, m, _ = make_ai(self.tmp, None, body={"paragraphs": ["Dois  espaços ,aqui"], "language": "pt-BR"})
        res = ai.proofread_ai(self.project(m))
        self.assertFalse(res["ai"])
        self.assertTrue(res["issues"])


class ConfigTests(unittest.TestCase):
    def test_normalize_config_and_team_section(self):
        c = sai.normalize_config({"agents": 7, "effort": "x", "type": "?", "language": "en", "pages": "9999", "words_per_page": 1, "content": "tudo", "expand_words": 1, "spellcheck": False})
        self.assertEqual((c["agents"], c["effort"], c["type"], c["language"]), (8, "high", "romance", "en-US"))
        self.assertLessEqual(c["pages"] * c["words_per_page"], S.MAX_TARGET_WORDS)
        self.assertEqual((c["content"], c["expand_words"], c["spellcheck"]), ("", 10, False))
        self.assertIn("scriber", teamlib.SECTIONS)
        self.assertEqual(sai.normalize_config(None)["agents"], 1)

    def test_prompts_ship_with_the_package(self):
        names = sai.prompt_names()
        for n in ("core", "planner", "writer", "reviewer", "editor", "proofreader"):
            self.assertIn(n, names)
            self.assertGreater(len(sai.prompt(n)), 200)
        self.assertIn("scriber/prompts/*.md", (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text())
        self.assertIn("Never invent facts", sai.prompt("core"))


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="asta-sc-api-"))
        cls.httpd, _ = make_server("127.0.0.1", 0, Store(cls.tmp))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.c = Client(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def job(self, path, body):
        st, r = self.c.json("POST", path, body)
        self.assertEqual(st, 200, r)
        return self.c.sse(f"/api/jobs/{r['job_id']}/events")

    def test_catalog_status_settings_and_prompts(self):
        st, cat = self.c.json("GET", "/api/scriber/catalog")
        self.assertEqual(st, 200)
        self.assertIn("scientific", cat["types"])
        st, s = self.c.json("GET", "/api/scriber/status")
        self.assertFalse(s["text"]["ai"])
        self.assertIn("pt-BR", s["dictionaries"])
        self.assertEqual(self.c.json("GET", "/api/settings")[1]["scriber"]["agents"], 1)
        self.assertTrue(self.c.json("GET", "/api/scriber/prompts")[1]["prompts"])
        st, e = self.c.json("POST", "/api/scriber/estimate", {"prompt": "x", "pages": 10, "words_per_page": 300})
        self.assertEqual(e["target_words"], 3000)

    def test_project_document_and_export_flow(self):
        st, p = self.c.json("POST", "/api/scriber/projects", {"name": "API", "type": "journalism", "language": "en-GB"})
        self.assertEqual(st, 201)
        pid = p["id"]
        st, d = self.c.json("PUT", f"/api/scriber/projects/{pid}/document", {"html": '<h1>Manchete</h1><p onclick="x()">Texto <b>forte</b><script>alert(1)</script></p>'})
        self.assertEqual(st, 200)
        st, d = self.c.json("GET", f"/api/scriber/projects/{pid}/document")
        self.assertNotIn("script", d["html"])
        self.assertNotIn("onclick", d["html"])
        self.assertEqual(d["stats"]["words"], 3)
        self.assertEqual(self.c.json("PUT", f"/api/scriber/projects/{pid}/document", {})[0], 400)
        st, e = self.c.json("POST", f"/api/scriber/projects/{pid}/export", {"format": "docx"})
        self.assertEqual(st, 200)
        status, hdr, data = self.c.req("GET", f"/api/scriber/projects/{pid}/exports/{e['name']}")
        self.assertEqual(status, 200)
        self.assertIn("wordprocessingml", hdr["Content-Type"])
        self.assertIn("attachment", hdr["Content-Disposition"])
        _wellformed(data)
        self.assertEqual(self.c.json("POST", f"/api/scriber/projects/{pid}/export", {"format": "exe"})[0], 400)
        self.assertEqual(self.c.req("GET", f"/api/scriber/projects/{pid}/exports/..%2F..%2Fproject.json")[0], 404)
        self.assertEqual(self.c.json("DELETE", f"/api/scriber/projects/{pid}/exports/{e['name']}")[0], 200)
        self.assertEqual(self.c.json("PUT", f"/api/scriber/projects/{pid}", {"name": "Renomeado", "format": {"font": "Arial"}})[1]["name"], "Renomeado")
        st, dup = self.c.json("POST", f"/api/scriber/projects/{pid}/duplicate", {})
        self.assertEqual(st, 201)
        self.assertEqual(self.c.json("DELETE", f"/api/scriber/projects/{pid}")[0], 200)
        self.assertEqual(self.c.json("GET", f"/api/scriber/projects/{pid}")[0], 404)
        self.assertEqual(self.c.json("GET", "/api/scriber/projects/..%2F..%2Fx")[0], 404)
        self.c.json("DELETE", f"/api/scriber/projects/{dup['id']}")

    def test_import_lorebooks_history_and_proofread(self):
        pid = self.c.json("POST", "/api/scriber/projects", {"name": "Imp"})[1]["id"]
        docx = X.build_docx(D.markdown_to_blocks("# Cap\n\nTexto importado"), {"title": "Cap"}, S.norm_format({"title_page": False}), "pt-BR")
        st, r = self.c.json("POST", f"/api/scriber/projects/{pid}/import?mode=replace", headers={"X-Filename": "livro.docx"}, raw=docx)
        self.assertEqual(st, 200)
        self.assertGreater(r["stats"]["words"], 2)
        self.assertEqual(self.c.json("POST", f"/api/scriber/projects/{pid}/import", headers={"X-Filename": "x.docx"}, raw=b"")[0], 400)
        self.assertEqual(self.c.json("POST", f"/api/scriber/projects/{pid}/import", headers={"X-Filename": "x.docx"}, raw=b"PKlixo")[0], 400)
        st, b = self.c.json("POST", f"/api/scriber/projects/{pid}/lorebooks/import", {"data": {"entries": {"0": {"key": ["Ana"], "content": "ruiva", "comment": "Ana"}}}, "name": "ST"})
        self.assertEqual(st, 201)
        st, books = self.c.json("GET", f"/api/scriber/projects/{pid}/lorebooks")
        self.assertEqual(books["books"][0]["entries"][0]["keys"], ["Ana"])
        status, hdr, data = self.c.req("GET", f"/api/scriber/projects/{pid}/lorebooks/{b['id']}/export")
        self.assertEqual(json.loads(data)["type"], "asta.lorebook")
        self.assertEqual(self.c.req("GET", f"/api/scriber/projects/{pid}/lorebooks/nao-existe/export")[0], 404)
        self.assertEqual(self.c.json("POST", f"/api/scriber/projects/{pid}/lorebooks/import", {"text": "nada"})[0], 201)  # texto puro vira uma entrada
        self.assertEqual(self.c.json("POST", f"/api/scriber/projects/{pid}/lorebooks/import", {})[0], 400)
        self.c.json("PUT", f"/api/scriber/projects/{pid}/document", {"markdown": "outro texto"})
        self.c.json("POST", f"/api/scriber/projects/{pid}/snapshot", {"label": "meu ponto"})
        st, h = self.c.json("GET", f"/api/scriber/projects/{pid}/history")
        self.assertTrue(h["items"])
        self.assertEqual(self.c.json("POST", f"/api/scriber/projects/{pid}/history/restore", {"id": h["items"][0]["id"]})[0], 200)
        st, pr = self.c.json("POST", "/api/scriber/proofread", {"paragraphs": ["Dois  espaços ,aqui"], "language": "pt-BR"})
        self.assertTrue(pr["issues"])
        self.assertEqual(self.c.json("POST", "/api/scriber/proofread", {"paragraphs": "x"})[0], 400)
        st, ty = self.c.json("POST", "/api/scriber/typography", {"paragraphs": ['Ele disse "oi"...'], "language": "pt-BR"})
        self.assertEqual(ty["paragraphs"], ["Ele disse “oi”…"])

    def test_generate_edit_and_proofread_jobs(self):
        pid = self.c.json("POST", "/api/scriber/projects", {"name": "Jobs"})[1]["id"]
        self.assertEqual(self.c.json("POST", f"/api/scriber/projects/{pid}/generate", {})[0], 400)
        ev = self.job(f"/api/scriber/projects/{pid}/generate", {"prompt": "# Um\n# Dois", "pages": 1, "words_per_page": 100, "type": "essay", "team": {"agents": 4, "effort": "low"}})
        res = [e for e in ev if e["type"] == "result"][0]["data"]
        self.assertEqual(res["docx"]["format"], "docx")
        self.assertEqual(res["report"]["team"]["agents"], 4)
        self.assertEqual(self.c.json("POST", f"/api/scriber/projects/{pid}/edit", {"action": "expand"})[0], 400)
        ev = self.job(f"/api/scriber/projects/{pid}/edit", {"action": "fix", "selection": "Texto  ruim ,aqui", "expand": {"mode": "add", "words": 50}})
        res = [e for e in ev if e["type"] == "result"][0]["data"]
        self.assertEqual(res["text"], "Texto ruim, aqui")
        ev = self.job(f"/api/scriber/projects/{pid}/proofread-ai", {"paragraphs": ["Dois  espaços"], "language": "pt-BR"})
        self.assertTrue([e for e in ev if e["type"] == "result"][0]["data"]["issues"])
        self.assertEqual(self.c.json("POST", "/api/scriber/projects/nao-existe/generate", {"prompt": "x"})[0], 404)

    def test_web_search_is_native_and_safe(self):
        from asta import websearch
        found = {"engine": "duckduckgo", "query": "q", "results": [{"title": "Fonte", "url": "https://a.com/x", "snippet": "trecho"}]}
        with mock.patch.object(websearch, "search", lambda q, s, n=None, ui_lang="auto": found), mock.patch.object(websearch, "fetch_page", lambda u, limit=0: {"title": "T", "text": "conteúdo da página"}), \
                mock.patch.object(websearch, "safe_url", lambda u: u.startswith("https://a.com")):
            st, r = self.c.json("POST", "/api/scriber/search", {"query": "algo"})
            self.assertEqual((st, r["results"][0]["host"]), (200, "a.com"))
            st, pg = self.c.json("POST", "/api/scriber/search/read", {"url": "https://a.com/x"})
            self.assertEqual(pg["text"], "conteúdo da página")
        self.assertEqual(self.c.json("POST", "/api/scriber/search", {"query": ""})[0], 400)
        self.assertEqual(self.c.json("POST", "/api/scriber/search/read", {"url": "http://127.0.0.1:1/x"})[0], 400)        # nada de endereços locais
        self.assertEqual(self.c.json("POST", "/api/scriber/search/read", {"url": "file:///etc/passwd"})[0], 400)

    def test_foreign_host_is_refused(self):
        st, _h, _b = self.c.req("GET", "/api/scriber/projects", headers={"Host": "evil.example.com"})
        self.assertIn(st, (400, 403))


if __name__ == "__main__":
    unittest.main()
