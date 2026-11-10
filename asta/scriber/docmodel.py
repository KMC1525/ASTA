"""Scriber — o documento: uma lista de **blocos** em JSON (aberto, legível, sem formato fechado).

    {"t": "p"|"h1"|"h2"|"h3"|"quote"|"li"|"hr"|"pb",     tipo do bloco (parágrafo, títulos, citação, item de lista, linha, quebra de página)
     "a": ""|"left"|"center"|"right"|"justify",           alinhamento (vazio = o da formatação do documento)
     "l": "ul"|"ol", "lv": 0..2,                          só para itens de lista
     "runs": [{"x": "texto", "b": 1, "i": 1, "u": 1, "s": 1}, …]}   trechos com negrito, itálico, sublinhado e riscado

O editor (HTML), o Markdown, o texto puro e o .docx são todos **derivados** disso. HTML vindo do navegador, texto da IA e arquivos importados são entrada não confiável:
`html_to_blocks` é uma lista de permissões (nada de scripts, estilos, imagens ou links entra) e tudo é limitado em tamanho."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

from .schema import ALIGNS, count_words

MAX_BLOCKS = 30000
MAX_CHARS = 6_000_000
MAX_RUN = 200_000
TYPES = ("p", "h1", "h2", "h3", "quote", "li", "hr", "pb")
TEXT_TYPES = ("p", "h1", "h2", "h3", "quote", "li")
FLAGS = ("b", "i", "u", "s")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]|[\ud800-\udfff]")


def clean(s: Any) -> str:
    return _CTRL.sub("", str(s if s is not None else ""))


def run(x: str, **flags: Any) -> Dict[str, Any]:
    r: Dict[str, Any] = {"x": clean(x)[:MAX_RUN]}
    for k in FLAGS:
        if flags.get(k):
            r[k] = 1
    return r


def block(t: str = "p", runs: Optional[List[Dict[str, Any]]] = None, a: str = "", l: str = "", lv: int = 0) -> Dict[str, Any]:
    b: Dict[str, Any] = {"t": t if t in TYPES else "p"}
    if a in ALIGNS:
        b["a"] = a
    if b["t"] == "li":
        b["l"] = l if l in ("ul", "ol") else "ul"
        b["lv"] = max(0, min(2, int(lv or 0)))
    if b["t"] in TEXT_TYPES:
        b["runs"] = merge_runs(runs or [])
    return b


def merge_runs(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in runs:
        if not isinstance(r, dict) or not r.get("x"):
            continue
        key = tuple(1 if r.get(k) else 0 for k in FLAGS)
        if out and tuple(1 if out[-1].get(k) else 0 for k in FLAGS) == key:
            out[-1]["x"] += r["x"]
        else:
            out.append(dict(r))
    return out


def text_of(b: Dict[str, Any]) -> str:
    return "".join(r.get("x", "") for r in b.get("runs", []) if isinstance(r, dict))


def norm_blocks(raw: Any) -> List[Dict[str, Any]]:
    """Valida uma lista de blocos qualquer (API, arquivo, IA): tipos conhecidos, runs só com texto e as quatro marcas, tamanhos limitados."""
    out: List[Dict[str, Any]] = []
    total = 0
    for b in raw if isinstance(raw, list) else []:
        if not isinstance(b, dict) or len(out) >= MAX_BLOCKS:
            continue
        t = b.get("t") if isinstance(b.get("t"), str) and b.get("t") in TYPES else "p"
        runs = []
        for r in b.get("runs") if isinstance(b.get("runs"), list) else []:
            if isinstance(r, dict) and isinstance(r.get("x"), str) and r["x"]:
                runs.append(run(r["x"], **{k: r.get(k) for k in FLAGS}))
        total += sum(len(r["x"]) for r in runs)
        if total > MAX_CHARS:
            break
        a = b.get("a") if isinstance(b.get("a"), str) else ""
        lv = b.get("lv") if isinstance(b.get("lv"), (int, float)) and not isinstance(b.get("lv"), bool) else 0
        out.append(block(t, runs, a, b.get("l") if isinstance(b.get("l"), str) else "ul", int(lv)))
    return out


# ---------------------------------------------------------------------------------------------------- estatísticas
def stats(blocks: List[Dict[str, Any]]) -> Dict[str, int]:
    words = chars = paras = heads = 0
    for b in blocks:
        if b.get("t") in TEXT_TYPES:
            s = text_of(b)
            if s.strip():
                paras += 1
                words += count_words(s)
                chars += len(s)
                heads += b["t"] in ("h1", "h2", "h3")
    return {"words": words, "chars": chars, "paragraphs": paras, "headings": heads, "blocks": len(blocks)}


def blocks_to_text(blocks: List[Dict[str, Any]]) -> str:
    out: List[str] = []
    n = 0
    prev_list = ""
    for b in blocks:
        t = b.get("t")
        if t == "pb":
            out.append("\f")
        elif t == "hr":
            out.append("* * *")
        elif t == "li":
            n = n + 1 if prev_list == b.get("l") and b.get("l") == "ol" else 1
            out.append("  " * b.get("lv", 0) + (f"{n}. " if b.get("l") == "ol" else "• ") + text_of(b))
        else:
            out.append(text_of(b))
        prev_list = b.get("l") if t == "li" else ""
    # lista seguida de lista fica junta; o resto é separado por linha em branco
    return "\n\n".join(out).replace("\n\n\f\n\n", "\n\f\n") if out else ""


# ---------------------------------------------------------------------------------------------------- HTML (editor)
def _runs_html(runs: List[Dict[str, Any]]) -> str:
    parts = []
    for r in runs:
        s = html.escape(r.get("x", ""), quote=False).replace("\n", "<br>")
        for k, tag in (("s", "s"), ("u", "u"), ("i", "i"), ("b", "b")):
            if r.get(k):
                s = f"<{tag}>{s}</{tag}>"
        parts.append(s)
    return "".join(parts)


def blocks_to_html(blocks: List[Dict[str, Any]]) -> str:
    out: List[str] = []
    stack: List[str] = []   # listas abertas (ul/ol), do mais externo ao mais interno

    def close_to(depth: int) -> None:
        while len(stack) > depth:
            out.append(f"</{stack.pop()}>")

    for b in blocks:
        t = b.get("t")
        if t != "li":
            close_to(0)
        style = f' style="text-align:{b["a"]}"' if b.get("a") in ALIGNS else ""
        if t == "li":
            lv, kind = b.get("lv", 0), b.get("l", "ul")
            while len(stack) < lv + 1:
                out.append(f"<{kind}>")
                stack.append(kind)
            close_to(lv + 1)
            if stack[lv] != kind:
                out.append(f"</{stack[lv]}><{kind}>")
                stack[lv] = kind
            out.append(f"<li{style}>{_runs_html(b.get('runs', []))}</li>")
        elif t == "hr":
            out.append("<hr>")
        elif t == "pb":
            out.append('<div class="pb"></div>')
        elif t == "quote":
            out.append(f"<blockquote{style}>{_runs_html(b.get('runs', []))}</blockquote>")
        else:
            tag = t if t in ("h1", "h2", "h3") else "p"
            out.append(f"<{tag}{style}>{_runs_html(b.get('runs', [])) or '<br>'}</{tag}>")
    close_to(0)
    return "".join(out)


class _Html(HTMLParser):
    """Lista de permissões: só estas marcas viram blocos; tudo o mais perde a marca e fica com o texto. `script`/`style` somem com o conteúdo."""
    SKIP = {"script", "style", "head", "title", "template", "noscript", "iframe", "object", "embed", "svg", "math", "textarea", "select", "button", "form"}
    BLOCK = {"p": "p", "div": "p", "h1": "h1", "h2": "h2", "h3": "h3", "h4": "h3", "h5": "h3", "h6": "h3", "blockquote": "quote", "li": "li", "pre": "p", "section": "p", "article": "p", "address": "p", "figcaption": "p", "tr": "p"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: List[Dict[str, Any]] = []
        self.cur: Optional[Dict[str, Any]] = None
        self.flags = {k: 0 for k in FLAGS}
        self.fstack: List[Any] = []
        self.skip = 0
        self.lists: List[str] = []
        self.chars = 0

    # ----- blocos
    def _open(self, t: str, align: str = "") -> None:
        self._close()
        self.cur = {"t": t, "a": align, "runs": []}
        if t == "li":
            self.cur["l"] = self.lists[-1] if self.lists else "ul"
            self.cur["lv"] = max(0, len(self.lists) - 1)

    def _close(self) -> None:
        c, self.cur = self.cur, None
        if c is None or len(self.blocks) >= MAX_BLOCKS:
            return
        c["runs"] = merge_runs(c["runs"])
        if c["runs"] or c["t"] in ("p", "h1", "h2", "h3") and c.get("keep"):
            self.blocks.append(block(c["t"], c["runs"], c["a"], c.get("l", ""), c.get("lv", 0)))
        elif c["t"] == "p":
            self.blocks.append(block("p", [], c["a"]))   # parágrafo vazio (linha em branco no editor)

    @staticmethod
    def _align(attrs: Dict[str, Any]) -> str:
        m = re.search(r"text-align\s*:\s*(left|right|center|justify)", attrs.get("style") or "", re.I)
        a = (m.group(1) if m else attrs.get("align") or "").lower()
        return a if a in ALIGNS else ""

    def handle_starttag(self, tag: str, attrs_l: List[Any]) -> None:
        attrs = {k: (v or "") for k, v in attrs_l}
        if self.skip or tag in self.SKIP:
            if tag in self.SKIP and tag not in ("br",):
                self.skip += 1
            return
        cls = attrs.get("class", "")
        if tag == "br":
            if self.cur is None:
                self._open("p")
            self.cur["runs"].append(run("\n", **self.flags))
            return
        if tag in ("hr",) or (tag == "div" and re.search(r"\bpb\b", cls)):
            self._close()
            if len(self.blocks) < MAX_BLOCKS:
                self.blocks.append(block("pb" if "pb" in cls.split() or "page-break" in cls else "hr"))
            if tag == "div":
                self.skip += 1   # o conteúdo da quebra de página não conta
                self.fstack.append(("skipdiv",))
            return
        if tag in ("ul", "ol"):
            self._close()
            self.lists.append(tag)
            return
        if tag in self.BLOCK and tag != "tr":
            style = attrs.get("style", "")
            if re.search(r"page-break-(before|after)\s*:\s*always", style, re.I) and tag == "div" and not self.cur:
                pass
            self._open(self.BLOCK[tag], self._align(attrs))
            self.cur["keep"] = tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6")
            return
        if tag == "tr":
            self._open("p")
            return
        if tag in ("td", "th"):
            if self.cur is not None and self.cur["runs"]:
                self.cur["runs"].append(run(" | ", **self.flags))
            return
        # marcas de texto
        new = {}
        if tag in ("b", "strong"):
            new["b"] = 1
        elif tag in ("i", "em", "cite", "dfn"):
            new["i"] = 1
        elif tag in ("u", "ins"):
            new["u"] = 1
        elif tag in ("s", "strike", "del"):
            new["s"] = 1
        elif tag in ("span", "font", "a", "code", "mark", "small", "big", "sub", "sup"):
            st = attrs.get("style", "")
            if re.search(r"font-weight\s*:\s*(bold|[6-9]00)", st, re.I):
                new["b"] = 1
            if re.search(r"font-style\s*:\s*italic", st, re.I):
                new["i"] = 1
            if re.search(r"text-decoration[^;]*underline", st, re.I):
                new["u"] = 1
            if re.search(r"text-decoration[^;]*line-through", st, re.I):
                new["s"] = 1
        self.fstack.append((tag, dict(self.flags)))
        for k in new:
            self.flags[k] = 1

    def handle_endtag(self, tag: str) -> None:
        if self.skip:
            if tag in self.SKIP:
                self.skip -= 1
            elif tag == "div" and self.fstack and self.fstack[-1] == ("skipdiv",):
                self.fstack.pop()
                self.skip -= 1
            return
        if tag in ("ul", "ol"):
            self._close()
            if self.lists:
                self.lists.pop()
            return
        if tag in self.BLOCK:
            self._close()
            return
        if tag in ("td", "th", "br", "hr"):
            return
        for i in range(len(self.fstack) - 1, -1, -1):   # fecha a última marca aberta com esse nome (HTML torto não desbalanceia as marcas)
            if self.fstack[i][0] == tag:
                self.flags = self.fstack[i][1]
                del self.fstack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self.skip or not data:
            return
        data = clean(data).replace("\xa0", " ")
        if self.cur is None:
            if not data.strip():
                return
            self._open("li" if self.lists else "p")
        data = re.sub(r"[ \t\r\n]+", " ", data)
        if not self.cur["runs"] and data.startswith(" "):
            data = data.lstrip(" ")
        self.chars += len(data)
        if self.chars > MAX_CHARS:
            return
        if data:
            self.cur["runs"].append(run(data, **self.flags))


def html_to_blocks(src: Any) -> List[Dict[str, Any]]:
    """HTML do editor (ou colado) → blocos, por lista de permissões."""
    p = _Html()
    s = str(src or "")[: MAX_CHARS * 2]
    try:
        p.feed(s)
        p.close()
    except (AssertionError, ValueError, RecursionError):   # HTML malformado demais: o que já foi lido vale
        pass
    p._close()
    out = p.blocks
    while out and out[-1].get("t") == "p" and not out[-1].get("runs"):   # o editor deixa um parágrafo vazio no fim
        out.pop()
    for b in out:   # espaço no fim do parágrafo não conta
        if b.get("runs"):
            last = b["runs"][-1]
            last["x"] = last["x"].rstrip(" ")
            b["runs"] = [r for r in b["runs"] if r["x"]]
    return out


# ---------------------------------------------------------------------------------------------------- Markdown (IA, importar, exportar)
_INLINE = re.compile(r"(\*\*\*(?P<bi>.+?)\*\*\*)|(\*\*(?P<b>.+?)\*\*)|(__(?P<u>.+?)__)|(~~(?P<s>.+?)~~)|(\*(?P<i>[^*\s](?:[^*]*[^*\s])?)\*)|(?<![\w])_(?P<i2>[^_\s](?:[^_]*[^_\s])?)_(?![\w])")


def inline_runs(s: str, flags: Optional[Dict[str, Any]] = None, depth: int = 0) -> List[Dict[str, Any]]:
    """**negrito**, *itálico*, __sublinhado__, ~~riscado~~ → runs (sem aninhar além de 3 níveis)."""
    flags = dict(flags or {})
    s = clean(s)
    runs: List[Dict[str, Any]] = []
    pos = 0
    for m in _INLINE.finditer(s):
        if m.start() > pos:
            runs.append(run(s[pos:m.start()], **flags))
        kind = next(k for k in ("bi", "b", "u", "s", "i", "i2") if m.group(k) is not None)
        inner = m.group(kind)
        add = {"bi": {"b": 1, "i": 1}, "b": {"b": 1}, "u": {"u": 1}, "s": {"s": 1}, "i": {"i": 1}, "i2": {"i": 1}}[kind]
        nf = {**flags, **add}
        runs.extend(inline_runs(inner, nf, depth + 1) if depth < 3 else [run(inner, **nf)])
        pos = m.end()
    if pos < len(s):
        runs.append(run(s[pos:], **flags))
    return merge_runs(runs)


_MD_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_MD_LI = re.compile(r"^(\s*)([-*+•]|\d{1,3}[.)])\s+(.*)$")
_MD_HR = re.compile(r"^\s*(?:[-*_]\s*){3,}$|^\s*\*\s*\*\s*\*\s*$")
_PB = re.compile(r"^\s*(?:<!--\s*pagebreak\s*-->|\\pagebreak|\\newpage|\f)\s*$", re.I)


def markdown_to_blocks(md: Any, *, join_lines: bool = False, shift: int = 0, lists: bool = True) -> List[Dict[str, Any]]:
    """Markdown simples (o que a IA escreve) → blocos. Cada linha não vazia é um parágrafo (diálogos ficam um por linha), a menos que `join_lines`.
    `shift` desce os títulos (1 = «#» vira h2). `lists=False` (ficção): «- fala» vira travessão em vez de item de lista. Cercas ``` e HTML são tratados como texto."""
    lines = str(md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: List[Dict[str, Any]] = []
    para: List[str] = []

    def flush() -> None:
        if para:
            txt = " ".join(x.strip() for x in para) if join_lines else "\n".join(para)
            for ln in ([txt] if join_lines else txt.split("\n")):
                if ln.strip():
                    out.append(block("p", inline_runs(ln.strip())))
            para.clear()

    in_fence = False
    for raw in lines:
        if len(out) >= MAX_BLOCKS:
            break
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            para.append(raw)
            continue
        if not raw.strip():
            flush()
            continue
        if _PB.match(raw):
            flush()
            out.append(block("pb"))
            continue
        if _MD_HR.match(raw) and len(raw.strip()) >= 3:
            flush()
            out.append(block("hr"))
            continue
        h = _MD_HEAD.match(raw)
        if h:
            flush()
            lvl = min(3, len(h.group(1)) + shift)
            out.append(block(f"h{lvl}", inline_runs(h.group(2), {}) if len(h.group(2)) < 400 else [run(h.group(2))]))
            continue
        if raw.lstrip().startswith(">"):
            flush()
            out.append(block("quote", inline_runs(raw.lstrip()[1:].strip())))
            continue
        li = _MD_LI.match(raw)
        if li:
            if lists:
                flush()
                lv = min(2, len(li.group(1).replace("\t", "    ")) // 2)
                out.append(block("li", inline_runs(li.group(3)), l="ol" if li.group(2)[0].isdigit() else "ul", lv=lv))
                continue
            if li.group(2) in ("-", "•"):   # na ficção «- Olá» é fala (travessão), não item de lista
                raw = "— " + li.group(3)
        para.append(raw)
    flush()
    return out


def blocks_to_markdown(blocks: List[Dict[str, Any]]) -> str:
    out: List[str] = []
    n = 0
    prev = ""
    for b in blocks:
        t = b.get("t")
        s = "".join(_md_run(r) for r in b.get("runs", []))
        if t in ("h1", "h2", "h3"):
            out.append("#" * int(t[1]) + " " + s)
        elif t == "quote":
            out.append("> " + s)
        elif t == "hr":
            out.append("---")
        elif t == "pb":
            out.append("<!-- pagebreak -->")
        elif t == "li":
            n = n + 1 if prev == "ol" and b.get("l") == "ol" else 1
            out.append("  " * b.get("lv", 0) + (f"{n}. " if b.get("l") == "ol" else "- ") + s)
        else:
            out.append(s)
        prev = b.get("l", "") if t == "li" else ""
    # itens de lista seguidos ficam colados; o resto tem linha em branco entre os blocos
    res = ""
    for i, line in enumerate(out):
        if i:
            res += "\n" if blocks[i].get("t") == "li" and blocks[i - 1].get("t") == "li" else "\n\n"
        res += line
    return res + "\n" if res else ""


def _md_run(r: Dict[str, Any]) -> str:
    s = r.get("x", "")
    if not s.strip():
        return s
    lead, core, tail = s[: len(s) - len(s.lstrip())], s.strip(), s[len(s.rstrip()):]
    for k, m in (("s", "~~"), ("u", "__"), ("i", "*"), ("b", "**")):
        if r.get(k):
            core = m + core + m
    return lead + core + tail


# ---------------------------------------------------------------------------------------------------- texto puro de um trecho (para o editor: seleção → IA → volta)
def plain_paragraphs(blocks: List[Dict[str, Any]]) -> List[str]:
    return [text_of(b) for b in blocks if b.get("t") in TEXT_TYPES]


def title_of(blocks: List[Dict[str, Any]], default: str = "") -> str:
    for b in blocks:
        if b.get("t") in ("h1", "h2") and text_of(b).strip():
            return text_of(b).strip()[:120]
    return default
