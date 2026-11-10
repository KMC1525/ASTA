"""Scriber — grava e lê arquivos .docx (Word) só com a biblioteca padrão (zip + XML), sem dependências.

`build_docx` gera um documento Office Open XML válido: tamanho de página e margens, fonte, tamanho, entrelinha, recuo da primeira linha, alinhamento, títulos (estilos Heading 1–3),
citações, listas com marcadores e numeradas, quebras de página, capa, sumário (campo TOC que o Word atualiza ao abrir, com uma lista estática de reserva), cabeçalho, número de página
e o **idioma do texto** (`w:lang`) — assim o corretor ortográfico do Word já abre no idioma certo.
`parse_docx` lê de volta o que importa (parágrafos, títulos, negrito/itálico/sublinhado/riscado, listas, quebras de página, tabelas achatadas) — o arquivo é entrada não confiável:
tamanho descompactado limitado, nada de DOCTYPE/entidades (billion laughs), só as partes conhecidas do pacote são lidas."""
from __future__ import annotations

import datetime as _dt
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as _esc

from . import docmodel as D
from .schema import PAGES, norm_format, norm_lang

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CM = 567   # twips por centímetro
MAX_UNZIPPED = 96 * 1024 * 1024
MAX_PARTS = 800


class DocxError(ValueError):
    pass


def _x(s: Any) -> str:
    return _esc(D.clean(s), {'"': "&quot;"})


# ---------------------------------------------------------------------------------------------------- gerar
def _lang_xml(code: str) -> str:
    return f'<w:lang w:val="{code}" w:eastAsia="{code}" w:bidi="ar-SA"/>'


def _styles(fmt: Dict[str, Any], lang: str) -> str:
    font, size = fmt["font"], int(round(fmt["size"] * 2))
    line = int(round(fmt["line"] * 240))
    after = int(round(fmt["space_after"] * 20))
    ind = int(round(fmt["indent"] * CM))
    jc = {"justify": "both"}.get(fmt["align"], fmt["align"])
    hfont = font

    def head(i: int, sz: int, before: int, aft: int) -> str:
        return (f'<w:style w:type="paragraph" w:styleId="Heading{i}"><w:name w:val="heading {i}"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="9"/><w:qFormat/>'
                f'<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="{before}" w:after="{aft}" w:line="{int(round(max(1.0, fmt["line"] * 0.85) * 240))}" w:lineRule="auto"/><w:ind w:firstLine="0"/><w:jc w:val="left"/><w:outlineLvl w:val="{i - 1}"/></w:pPr>'
                f'<w:rPr><w:rFonts w:ascii="{_x(hfont)}" w:hAnsi="{_x(hfont)}" w:cs="{_x(hfont)}"/><w:b/><w:bCs/><w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/></w:rPr></w:style>')

    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:styles xmlns:w="{W}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{_x(font)}" w:hAnsi="{_x(font)}" w:cs="{_x(font)}" w:eastAsia="{_x(font)}"/>'
            f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>{_lang_xml(lang)}</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
            f'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="{after}" w:line="{line}" w:lineRule="auto"/><w:ind w:firstLine="{ind}"/><w:jc w:val="{jc}"/></w:pPr></w:style>'
            '<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont"><w:name w:val="Default Paragraph Font"/><w:uiPriority w:val="1"/><w:semiHidden/></w:style>'
            + head(1, int(round(size * 1.6)), 480, 240) + head(2, int(round(size * 1.3)), 360, 160) + head(3, int(round(size * 1.12)), 280, 120) +
            f'<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="10"/><w:qFormat/><w:pPr><w:spacing w:before="3200" w:after="240" w:line="240" w:lineRule="auto"/><w:ind w:firstLine="0"/><w:jc w:val="center"/></w:pPr>'
            f'<w:rPr><w:rFonts w:ascii="{_x(hfont)}" w:hAnsi="{_x(hfont)}"/><w:b/><w:sz w:val="{int(round(size * 2.6))}"/><w:szCs w:val="{int(round(size * 2.6))}"/></w:rPr></w:style>'
            f'<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="11"/><w:qFormat/><w:pPr><w:spacing w:after="480"/><w:ind w:firstLine="0"/><w:jc w:val="center"/></w:pPr><w:rPr><w:i/><w:sz w:val="{int(round(size * 1.3))}"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="29"/><w:qFormat/><w:pPr><w:spacing w:before="120" w:after="120"/><w:ind w:left="720" w:right="720" w:firstLine="0"/></w:pPr><w:rPr><w:i/><w:iCs/></w:rPr></w:style>'
            f'<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:uiPriority w:val="34"/><w:qFormat/><w:pPr><w:spacing w:after="{min(after, 80)}"/><w:ind w:firstLine="0"/></w:pPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="TOCHeading"><w:name w:val="TOC Heading"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="39"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="240"/><w:ind w:firstLine="0"/><w:jc w:val="left"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="39"/><w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="8500"/></w:tabs><w:spacing w:after="100"/><w:ind w:firstLine="0"/><w:jc w:val="left"/></w:pPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="TOC2"><w:name w:val="toc 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="39"/><w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="8500"/></w:tabs><w:spacing w:after="80"/><w:ind w:left="220" w:firstLine="0"/><w:jc w:val="left"/></w:pPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="TOC3"><w:name w:val="toc 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="39"/><w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="8500"/></w:tabs><w:spacing w:after="60"/><w:ind w:left="440" w:firstLine="0"/><w:jc w:val="left"/></w:pPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Header"><w:name w:val="header"/><w:basedOn w:val="Normal"/><w:uiPriority w:val="99"/><w:pPr><w:ind w:firstLine="0"/><w:spacing w:after="0"/><w:jc w:val="right"/></w:pPr><w:rPr><w:i/><w:sz w:val="18"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:basedOn w:val="Normal"/><w:uiPriority w:val="99"/><w:pPr><w:ind w:firstLine="0"/><w:spacing w:after="0"/><w:jc w:val="center"/></w:pPr><w:rPr><w:sz w:val="20"/></w:rPr></w:style>'
            '</w:styles>')


def _numbering(n_ol: int) -> str:
    def lvls(kind: str) -> str:
        out = []
        for i in range(3):
            left = 720 + 360 * i
            if kind == "ul":
                char = ("•", "◦", "▪")[i]
                out.append(f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="{char}"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{left}" w:hanging="360"/></w:pPr></w:lvl>')
            else:
                fmt = ("decimal", "lowerLetter", "lowerRoman")[i]
                out.append(f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="%{i + 1}."/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{left}" w:hanging="360"/></w:pPr></w:lvl>')
        return "".join(out)

    nums = '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
    for i in range(n_ol):   # cada lista numerada recomeça do 1
        nums += f'<w:num w:numId="{i + 2}"><w:abstractNumId w:val="1"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>'
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:numbering xmlns:w="{W}"><w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>{lvls("ul")}</w:abstractNum>'
            f'<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>{lvls("ol")}</w:abstractNum>{nums}</w:numbering>')


def _runs_xml(runs: List[Dict[str, Any]]) -> str:
    out = []
    for r in runs:
        rpr = ("<w:b/><w:bCs/>" if r.get("b") else "") + ("<w:i/><w:iCs/>" if r.get("i") else "") + ("<w:strike/>" if r.get("s") else "") + ('<w:u w:val="single"/>' if r.get("u") else "")
        parts = re.split(r"(\n|\t)", r.get("x", ""))
        inner = ""
        for p in parts:
            if p == "\n":
                inner += "<w:br/>"
            elif p == "\t":
                inner += "<w:tab/>"
            elif p:
                inner += f'<w:t xml:space="preserve">{_x(p)}</w:t>'
        if inner:
            out.append(f'<w:r>{"<w:rPr>" + rpr + "</w:rPr>" if rpr else ""}{inner}</w:r>')
    return "".join(out)


def _para(style: str, runs_xml: str, ppr_extra: str = "") -> str:
    ppr = (f'<w:pStyle w:val="{style}"/>' if style else "") + ppr_extra
    return f'<w:p>{"<w:pPr>" + ppr + "</w:pPr>" if ppr else ""}{runs_xml}</w:p>'


def _sect(fmt: Dict[str, Any], header: bool, title_page: bool) -> str:
    w_cm, h_cm = PAGES[fmt["page"]]
    top, bottom, left, right = fmt["margins"]
    refs = ""
    if header:
        refs += '<w:headerReference w:type="default" r:id="rIdHdr"/>'
    if fmt["page_numbers"]:
        refs += '<w:footerReference w:type="default" r:id="rIdFtr"/>'
    if title_page and (fmt["page_numbers"] or header):
        refs += '<w:headerReference w:type="first" r:id="rIdHdrEmpty"/><w:footerReference w:type="first" r:id="rIdFtrEmpty"/>'
    return (f'<w:sectPr>{refs}<w:pgSz w:w="{int(round(w_cm * CM))}" w:h="{int(round(h_cm * CM))}"/>'
            f'<w:pgMar w:top="{int(round(top * CM))}" w:right="{int(round(right * CM))}" w:bottom="{int(round(bottom * CM))}" w:left="{int(round(left * CM))}" w:header="{CM}" w:footer="{CM}" w:gutter="0"/>'
            f'{"<w:titlePg/>" if title_page and (fmt["page_numbers"] or header) else ""}</w:sectPr>')


def build_docx(blocks: List[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None, fmt: Any = None, lang: Any = None) -> bytes:
    """Blocos + metadados (`title`, `author`) + formatação → bytes de um .docx."""
    meta = meta or {}
    fmt = norm_format(fmt)
    lang = norm_lang(lang)
    blocks = D.norm_blocks(blocks)
    title = (str(meta.get("title") or "").strip() or D.title_of(blocks, "Documento"))[:200]
    author = str(meta.get("author") or fmt["author"] or "").strip()[:100]
    subtitle = fmt["subtitle"]
    body: List[str] = []
    headings: List[Tuple[int, str]] = []
    n_ol = 0
    prev_li = ""   # "ul" | "ol:<numId>"
    cur_ol = 1

    if blocks and blocks[0].get("t") in ("h1", "h2") and D.text_of(blocks[0]).strip().lower() == title.strip().lower():
        blocks = blocks[1:]   # o título já vai na capa / no alto: não repete como primeiro título do corpo
    if not fmt["title_page"] and meta.get("title"):   # sem capa: o título abre a primeira página
        body.append(_para("Title", _runs_xml([D.run(title)]), '<w:spacing w:before="0" w:after="360"/>'))
        if subtitle:
            body.append(_para("Subtitle", _runs_xml([D.run(subtitle)]), '<w:spacing w:before="0" w:after="360"/>'))
    if fmt["title_page"]:
        body.append(_para("Title", _runs_xml([D.run(title)])))
        if subtitle:
            body.append(_para("Subtitle", _runs_xml([D.run(subtitle)])))
        if author:
            body.append(_para("Subtitle", _runs_xml([D.run(author)]), '<w:spacing w:before="1200"/>'))
        body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
    if fmt["toc"]:
        toc_items = [(int(b["t"][1]), D.text_of(b).strip()) for b in blocks if b.get("t") in ("h1", "h2", "h3") and D.text_of(b).strip()]
        toc_title = {"pt": "Sumário", "es": "Índice", "fr": "Sommaire", "de": "Inhalt", "it": "Indice", "nl": "Inhoud", "pl": "Spis treści", "ru": "Содержание", "tr": "İçindekiler", "sv": "Innehåll"}.get(lang[:2], "Contents")
        body.append(_para("TOCHeading", _runs_xml([D.run(toc_title)])))
        first = True
        for lv, tx in toc_items[:400]:
            begin = ('<w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r><w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>') if first else ""
            body.append(_para(f"TOC{lv}", begin + _runs_xml([D.run(tx)])))
            first = False
        if toc_items:
            body.append('<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
        else:
            body.append(_para("Normal", _runs_xml([D.run("")])))
        body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    first_block = True
    for b in blocks:
        t = b.get("t")
        jc = ""
        if b.get("a"):
            jc = '<w:jc w:val="%s"/>' % {"justify": "both"}.get(b["a"], b["a"])
        if t != "li":
            prev_li = ""
        if t == "pb":
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        elif t == "hr":
            body.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="808080"/></w:pBdr><w:ind w:firstLine="0"/></w:pPr></w:p>')
        elif t in ("h1", "h2", "h3"):
            extra = ""
            if t == "h1" and fmt["chapter_break"] and not first_block:
                extra = "<w:pageBreakBefore/>"
            lvl = int(t[1])
            txt = D.text_of(b).strip()
            if txt:
                headings.append((lvl, txt))
            body.append(_para(f"Heading{lvl}", _runs_xml(b.get("runs", [])), extra + jc))
        elif t == "quote":
            body.append(_para("Quote", _runs_xml(b.get("runs", [])), jc))
        elif t == "li":
            kind = b.get("l", "ul")
            if kind == "ol":
                if prev_li != "ol":
                    n_ol += 1
                    cur_ol = n_ol + 1
                num = cur_ol
            else:
                num = 1
            prev_li = kind
            body.append(_para("ListParagraph", _runs_xml(b.get("runs", [])), f'<w:numPr><w:ilvl w:val="{b.get("lv", 0)}"/><w:numId w:val="{num}"/></w:numPr>' + jc))
        else:
            body.append(_para("", _runs_xml(b.get("runs", [])) or "", jc))
        if t in ("p", "h1", "h2", "h3", "quote", "li") and D.text_of(b).strip():
            first_block = False
    if not body:
        body.append(_para("", ""))

    has_header = bool(fmt["header"])
    sect = _sect(fmt, has_header, fmt["title_page"])
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{"".join(body)}{sect}</w:body></w:document>')
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    words = D.stats(blocks)["words"]

    overrides = [("/word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"), ("/word/styles.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"),
                 ("/word/numbering.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"), ("/word/settings.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"),
                 ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"), ("/docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml")]
    rels = [("rIdStyles", "styles", "styles.xml"), ("rIdNum", "numbering", "numbering.xml"), ("rIdSet", "settings", "settings.xml")]
    parts: Dict[str, str] = {}

    def hf(kind: str, inner: str) -> str:
        tag = "w:hdr" if kind == "hdr" else "w:ftr"
        return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><{tag} xmlns:w="{W}" xmlns:r="{R}">{inner}</{tag}>'

    if has_header:
        parts["header1.xml"] = hf("hdr", _para("Header", _runs_xml([D.run(fmt["header"])])))
        overrides.append(("/word/header1.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"))
        rels.append(("rIdHdr", "header", "header1.xml"))
    if fmt["page_numbers"]:
        parts["footer1.xml"] = hf("ftr", _para("Footer", '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'))
        overrides.append(("/word/footer1.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"))
        rels.append(("rIdFtr", "footer", "footer1.xml"))
    if fmt["title_page"] and (fmt["page_numbers"] or has_header):
        parts["header2.xml"] = hf("hdr", _para("Header", ""))
        parts["footer2.xml"] = hf("ftr", _para("Footer", ""))
        overrides += [("/word/header2.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"), ("/word/footer2.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml")]
        rels += [("rIdHdrEmpty", "header", "header2.xml"), ("rIdFtrEmpty", "footer", "footer2.xml")]

    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
              + "".join(f'<Override PartName="{p}" ContentType="{c}"/>' for p, c in overrides) + "</Types>")
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                 '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(f'<Relationship Id="{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{t}" Target="{target}"/>' for i, t, target in rels) + "</Relationships>")
    update_fields = '<w:updateFields w:val="true"/>' if fmt["toc"] and headings else ""
    decimal = "," if lang[:2] in ("pt", "es", "fr", "de", "it", "nl", "pl", "ru", "tr", "sv") else "."
    settings = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:settings xmlns:w="{W}">{update_fields}<w:defaultTabStop w:val="720"/><w:characterSpacingControl w:val="doNotCompress"/>'
                f'<w:themeFontLang w:val="{lang}"/><w:decimalSymbol w:val="{decimal}"/><w:listSeparator w:val=";"/></w:settings>')
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{_x(title)}</dc:title><dc:creator>{_x(author or "ASTA Scriber")}</dc:creator><dc:language>{lang}</dc:language>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>')
    app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
           f'<Application>ASTA Scriber</Application><Words>{words}</Words></Properties>')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/styles.xml", _styles(fmt, lang))
        z.writestr("word/numbering.xml", _numbering(n_ol))
        z.writestr("word/settings.xml", settings)
        for name, xml in parts.items():
            z.writestr("word/" + name, xml)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------------- ler
def _q(tag: str) -> str:
    return "{%s}%s" % (W, tag)


def _on(el: Optional[ET.Element]) -> bool:
    """Marca de execução ligada: <w:b/> sim; <w:b w:val="0|false|off"/> não."""
    if el is None:
        return False
    v = el.get(_q("val"))
    return v is None or v.lower() not in ("0", "false", "off", "none")


def _read(z: zipfile.ZipFile, name: str, limit: int = 40 * 1024 * 1024) -> Optional[bytes]:
    try:
        info = z.getinfo(name)
    except KeyError:
        return None
    if info.file_size > limit:
        raise DocxError("O arquivo .docx tem uma parte grande demais.")
    data = z.read(name)
    if b"<!DOCTYPE" in data[:4000].upper() or b"<!ENTITY" in data[:4000].upper():
        raise DocxError("Arquivo .docx recusado (declaração XML não permitida).")
    return data


def parse_docx(data: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """bytes de um .docx → (blocos, {title, author, language})."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError):
        raise DocxError("Isso não parece um arquivo .docx válido.") from None
    with z:
        infos = z.infolist()
        if len(infos) > MAX_PARTS or sum(i.file_size for i in infos) > MAX_UNZIPPED:
            raise DocxError("O arquivo .docx é grande demais para abrir.")
        doc = _read(z, "word/document.xml")
        if doc is None:
            raise DocxError("Não encontrei o texto do documento (word/document.xml).")
        styles = _read(z, "word/styles.xml")
        numbering = _read(z, "word/numbering.xml")
        core = _read(z, "docProps/core.xml")
    try:
        root = ET.fromstring(doc)
    except ET.ParseError:
        raise DocxError("O texto do .docx está corrompido.") from None

    style_names: Dict[str, str] = {}
    lang = ""
    if styles:
        try:
            sroot = ET.fromstring(styles)
            for st in sroot.iter(_q("style")):
                nm = st.find(_q("name"))
                if nm is not None:
                    style_names[st.get(_q("styleId"), "")] = (nm.get(_q("val")) or "").lower()
            lg = sroot.find(f".//{_q('rPrDefault')}//{_q('lang')}")
            if lg is not None:
                lang = lg.get(_q("val")) or ""
        except ET.ParseError:
            pass
    num_kind: Dict[str, str] = {}
    if numbering:
        try:
            nroot = ET.fromstring(numbering)
            abstract: Dict[str, str] = {}
            for an in nroot.iter(_q("abstractNum")):
                lvl = an.find(_q("lvl"))
                nf = lvl.find(_q("numFmt")) if lvl is not None else None
                abstract[an.get(_q("abstractNumId"), "")] = (nf.get(_q("val")) if nf is not None else "") or ""
            for n in nroot.iter(_q("num")):
                aid = n.find(_q("abstractNumId"))
                fmtv = abstract.get(aid.get(_q("val"), "") if aid is not None else "", "")
                num_kind[n.get(_q("numId"), "")] = "ul" if fmtv == "bullet" else "ol"
        except ET.ParseError:
            pass
    meta: Dict[str, Any] = {"title": "", "author": "", "language": norm_lang(lang, "") if lang else ""}
    if core:
        try:
            croot = ET.fromstring(core)
            for el in croot:
                nm = el.tag.rsplit("}", 1)[-1]
                if nm == "title" and el.text:
                    meta["title"] = el.text.strip()[:200]
                elif nm == "creator" and el.text and "ASTA" not in el.text:
                    meta["author"] = el.text.strip()[:100]
        except ET.ParseError:
            pass

    blocks: List[Dict[str, Any]] = []

    def runs_of(p: ET.Element) -> Tuple[List[Dict[str, Any]], bool]:
        runs: List[Dict[str, Any]] = []
        page_break = False
        for r in p.iter(_q("r")):
            rpr = r.find(_q("rPr"))
            flags = {}
            if rpr is not None:
                flags = {"b": _on(rpr.find(_q("b"))), "i": _on(rpr.find(_q("i"))), "s": _on(rpr.find(_q("strike"))) or _on(rpr.find(_q("dstrike"))),
                         "u": (rpr.find(_q("u")) is not None and (rpr.find(_q("u")).get(_q("val")) or "single") != "none")}
            for ch in r:
                tag = ch.tag.rsplit("}", 1)[-1]
                if tag == "t" and ch.text:
                    runs.append(D.run(ch.text, **flags))
                elif tag == "tab":
                    runs.append(D.run("\t", **flags))
                elif tag == "br":
                    if ch.get(_q("type")) == "page":
                        page_break = True
                    else:
                        runs.append(D.run("\n", **flags))
        return runs, page_break

    def add_par(p: ET.Element) -> None:
        if len(blocks) >= D.MAX_BLOCKS:
            return
        ppr = p.find(_q("pPr"))
        sid, jc, numid, lvl, pbb = "", "", "", 0, False
        if ppr is not None:
            ps = ppr.find(_q("pStyle"))
            sid = ps.get(_q("val"), "") if ps is not None else ""
            j = ppr.find(_q("jc"))
            jc = (j.get(_q("val")) or "") if j is not None else ""
            npr = ppr.find(_q("numPr"))
            if npr is not None:
                ni, il = npr.find(_q("numId")), npr.find(_q("ilvl"))
                numid = (ni.get(_q("val")) or "") if ni is not None else ""
                try:
                    lvl = int(il.get(_q("val")) or 0) if il is not None else 0
                except ValueError:
                    lvl = 0
            pbb = ppr.find(_q("pageBreakBefore")) is not None
        runs, pb_inside = runs_of(p)
        name = style_names.get(sid, sid.lower())
        align = {"both": "justify", "left": "left", "right": "right", "center": "center", "start": "left", "end": "right"}.get(jc, "")
        if pbb:
            blocks.append(D.block("pb"))
        text = "".join(r["x"] for r in runs)
        m = re.match(r"^(?:heading|título|titulo)\s*(\d)$", name)
        if m or name in ("title",):
            lvl_h = min(3, int(m.group(1))) if m else 1
            if text.strip():
                blocks.append(D.block(f"h{lvl_h}", runs, align))
        elif name in ("subtitle",) or name.startswith("toc"):
            if text.strip() and not name.startswith("toc"):
                blocks.append(D.block("p", runs, "center"))
        elif name in ("quote", "intense quote", "block text", "citação"):
            if text.strip():
                blocks.append(D.block("quote", runs, align))
        elif numid and numid != "0" or name == "list paragraph" and numid:
            blocks.append(D.block("li", runs, align, num_kind.get(numid, "ul"), lvl))
        elif name.startswith("list bullet") or name.startswith("list number"):
            blocks.append(D.block("li", runs, align, "ol" if "number" in name else "ul", 0))
        elif text.strip():
            blocks.append(D.block("p", runs, align))
        elif ppr is not None and ppr.find(_q("pBdr")) is not None and not pb_inside:
            blocks.append(D.block("hr"))   # parágrafo vazio com borda = linha horizontal
        elif not pb_inside:
            blocks.append(D.block("p", [], ""))   # linha em branco
        if pb_inside:
            blocks.append(D.block("pb"))

    body = root.find(_q("body"))
    if body is None:
        raise DocxError("Documento vazio.")

    def walk(parent: ET.Element) -> None:
        for el in parent:
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "p":
                add_par(el)
            elif tag == "tbl":
                for tr in el.iter(_q("tr")):
                    cells = []
                    for tc in tr.findall(_q("tc")):
                        runs: List[Dict[str, Any]] = []
                        for p in tc.iter(_q("p")):
                            rr, _ = runs_of(p)
                            if rr:
                                runs += rr + [D.run(" ")]
                        cells.append("".join(r["x"] for r in runs).strip())
                    if any(cells):
                        blocks.append(D.block("p", [D.run(" | ".join(cells))]))
            elif tag in ("sdt", "sdtContent", "ins", "customXml"):
                walk(el if tag != "sdt" else (el.find(_q("sdtContent")) if el.find(_q("sdtContent")) is not None else el))

    walk(body)
    # a capa/sumário que o próprio Scriber gerou voltam como texto comum: sem tratamento especial (o que importa é o conteúdo)
    while blocks and blocks[-1]["t"] == "p" and not blocks[-1].get("runs"):
        blocks.pop()
    return D.norm_blocks(blocks), meta
