"""Formatos do modo Data (v0.24) só com a biblioteca padrão: **XLSX** (ler e escrever), **SQL** (CREATE TABLE + INSERT), **YAML** e XML endurecido.

Entrada é não confiável: o XLSX é um ZIP (limites de tamanho, de quantidade de peças e de linhas; nada é extraído em disco) e todo XML recusa `DOCTYPE`/`ENTITY`
(bombas de expansão). A saída preserva a estrutura: nomes de colunas, ordem e tipos do schema.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

import xml.etree.ElementTree as ET

MAX_XLSX_PARTS = 80
MAX_XLSX_XML = 64 * 1024 * 1024        # cada peça XML, já descomprimida
MAX_XLSX_ROWS = 200_000
MAX_XLSX_COLS = 200
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_BAD_XML = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.I)
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class FormatError(ValueError):
    pass


def safe_xml(raw: bytes) -> ET.Element:
    """Interpreta XML recusando DOCTYPE/ENTITY (expansão de entidades) e peças gigantes."""
    if len(raw) > MAX_XLSX_XML:
        raise FormatError("XML grande demais.")
    if _BAD_XML.search(raw[:4096]) or _BAD_XML.search(raw):
        raise FormatError("XML com DOCTYPE/ENTITY não é aceito.")
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise FormatError("XML inválido.") from None


def _col_name(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _cell_value(v: Any) -> Tuple[str, str]:
    """(tipo da célula, texto XML) — tipos: n número · b booleano · inlineStr texto."""
    if isinstance(v, bool):
        return "b", "1" if v else "0"
    if isinstance(v, (int, float)):
        return "n", repr(v) if isinstance(v, float) else str(v)
    if v is None:
        return "", ""
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)
    return "inlineStr", _CTRL.sub("", str(v))[:32000]


def write_xlsx(columns: Sequence[str], records: Sequence[Any], schema_fields: Sequence[Dict[str, Any]], title: str = "data") -> bytes:
    """Planilha com a aba `data` (cabeçalho + registros) e a aba `schema` (nome, tipo, descrição)."""
    def sheet(rows: Sequence[Sequence[Any]]) -> str:
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="%s"><sheetData>' % NS["m"]]
        for ri, row in enumerate(rows, 1):
            out.append(f'<row r="{ri}">')
            for ci, v in enumerate(row):
                t, txt = _cell_value(v)
                if not t:
                    continue
                ref = f"{_col_name(ci)}{ri}"
                if t == "inlineStr":
                    out.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(txt)}</t></is></c>')
                else:
                    out.append(f'<c r="{ref}" t="{t}"><v>{txt}</v></c>')
            out.append("</row>")
        out.append("</sheetData></worksheet>")
        return "".join(out)

    cols = list(columns)[:MAX_XLSX_COLS]
    data_rows: List[List[Any]] = [cols]
    for r in list(records)[:MAX_XLSX_ROWS]:
        row = r if isinstance(r, dict) else {"value": r}
        data_rows.append([row.get(c) for c in cols])
    schema_rows: List[List[Any]] = [["name", "type", "description"]] + [[f.get("name"), f.get("type"), f.get("description", "")] for f in schema_fields]
    name = escape(re.sub(r"[\[\]:*?/\\]", "_", title)[:31] or "data")
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="{NS["m"]}" xmlns:r="{NS["r"]}"><sheets><sheet name="{name}" sheetId="1" r:id="rId1"/><sheet name="schema" sheetId="2" r:id="rId2"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet(data_rows),
        "xl/worksheets/sheet2.xml": sheet(schema_rows),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, body in parts.items():
            z.writestr(n, body)
    return buf.getvalue()


def read_xlsx(raw: bytes) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Primeira aba → registros (a 1ª linha é o cabeçalho). Se houver uma aba `schema` (como a que o ASTA exporta), os tipos dela voltam junto."""
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise FormatError("Arquivo XLSX inválido.") from None
    infos = z.infolist()
    if len(infos) > MAX_XLSX_PARTS:
        raise FormatError("XLSX com peças demais.")
    if sum(i.file_size for i in infos) > 8 * MAX_XLSX_XML:
        raise FormatError("XLSX grande demais depois de descompactado.")

    def part(name: str) -> Optional[ET.Element]:
        try:
            info = z.getinfo(name)
        except KeyError:
            return None
        if info.file_size > MAX_XLSX_XML:
            raise FormatError("Peça do XLSX grande demais.")
        return safe_xml(z.read(name))

    shared: List[str] = []
    sst = part("xl/sharedStrings.xml")
    if sst is not None:
        for si in sst.findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    wb = part("xl/workbook.xml")
    if wb is None:
        raise FormatError("XLSX sem workbook.")
    rels = part("xl/_rels/workbook.xml.rels")
    targets = {r.get("Id"): r.get("Target") for r in (rels if rels is not None else [])}
    sheets: List[Tuple[str, str]] = []
    for s in wb.findall("m:sheets/m:sheet", NS):
        rid = s.get("{%s}id" % NS["r"])
        tgt = (targets.get(rid) or "").lstrip("/")
        path = tgt if tgt.startswith("xl/") else "xl/" + tgt
        sheets.append((s.get("name") or "", path))
    if not sheets:
        raise FormatError("XLSX sem abas.")

    def rows_of(path: str) -> List[List[Any]]:
        sh = part(path)
        if sh is None:
            return []
        out: List[List[Any]] = []
        for row in sh.findall("m:sheetData/m:row", NS):
            if len(out) >= MAX_XLSX_ROWS + 1:
                break
            cells: Dict[int, Any] = {}
            for c in row.findall("m:c", NS):
                ci = _col_index(c.get("r") or "")
                if ci < 0 or ci >= MAX_XLSX_COLS:
                    continue
                t = c.get("t")
                v = c.find("m:v", NS)
                if t == "inlineStr":
                    val: Any = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
                elif v is None or v.text is None:
                    continue
                elif t == "s":
                    try:
                        val = shared[int(v.text)]
                    except (ValueError, IndexError):
                        val = ""
                elif t == "b":
                    val = v.text.strip() == "1"
                elif t in ("str", "e"):
                    val = v.text
                else:
                    try:
                        f = float(v.text)
                        val = int(f) if f == int(f) and "." not in v.text and "e" not in v.text.lower() else f
                    except ValueError:
                        val = v.text
                cells[ci] = val
            out.append([cells.get(i) for i in range((max(cells) + 1) if cells else 0)])
        return out

    grid = rows_of(sheets[0][1])
    if not grid:
        return [], None
    header = [str(h).strip() if h not in (None, "") else f"coluna_{i + 1}" for i, h in enumerate(grid[0])]
    seen: Dict[str, int] = {}
    cols: List[str] = []
    for h in header:                              # nomes repetidos não podem se sobrescrever
        seen[h] = seen.get(h, 0) + 1
        cols.append(h if seen[h] == 1 else f"{h}_{seen[h]}")
    records = []
    for r in grid[1:]:
        row = {cols[i]: r[i] for i in range(min(len(cols), len(r))) if r[i] not in (None, "")}
        if row:
            records.append(row)
    schema = None
    for name, path in sheets[1:]:
        if name.lower() == "schema":
            sg = rows_of(path)
            if sg and [str(x).lower() for x in sg[0][:2]] == ["name", "type"]:
                schema = {"fields": [{"name": str(r[0]), "type": str(r[1] if len(r) > 1 and r[1] else "text"), "description": str(r[2]) if len(r) > 2 and r[2] else "", "required": False} for r in sg[1:] if r and r[0]]}
    if schema is None:
        schema = {"fields": [{"name": c, "type": "text", "description": "", "required": False} for c in cols]}
    return records, schema


# ----------------------------------------------------------------------------- SQL
_SQL_TYPES = {"integer": "INTEGER", "number": "REAL", "boolean": "INTEGER"}


def _ident(s: str) -> str:
    return '"' + str(s).replace('"', '""') + '"'


def _sql_value(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)
    return "'" + str(v).replace("'", "''").replace("\x00", "") + "'"


def to_sql(table: str, fields: Sequence[Dict[str, Any]], columns: Sequence[str], records: Sequence[Any]) -> str:
    """Script SQL padrão (SQLite/PostgreSQL/MySQL): um `CREATE TABLE` com os tipos do schema e um `INSERT` por registro."""
    types = {f.get("name"): _SQL_TYPES.get(f.get("type"), "TEXT") for f in fields}
    lines = [f"-- ASTA Data · tabela {table} · {len(records)} registro(s)", f"CREATE TABLE {_ident(table)} ("]
    lines.append(",\n".join(f"  {_ident(c)} {types.get(c, 'TEXT')}" for c in columns))
    lines.append(");")
    cols = ", ".join(_ident(c) for c in columns)
    for r in records:
        row = r if isinstance(r, dict) else {"value": r}
        lines.append(f"INSERT INTO {_ident(table)} ({cols}) VALUES ({', '.join(_sql_value(row.get(c)) for c in columns)});")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- YAML
def to_yaml(kind: str, meta: Dict[str, Any], schema: Dict[str, Any], records: Sequence[Any]) -> str:
    """YAML válido: texto e coleções em estilo JSON (que o YAML 1.2 aceita), então nada precisa de escape especial."""
    j = lambda v: json.dumps(v, ensure_ascii=False)  # noqa: E731
    out = [f"kind: {j(kind)}", f"meta: {j(meta)}", "schema:"]
    for f in schema.get("fields") or []:
        out.append(f"  - {j(f)}")
    out.append("records:" if records else "records: []")
    for r in records:
        out.append(f"  - {j(r)}")
    return "\n".join(out) + "\n"
