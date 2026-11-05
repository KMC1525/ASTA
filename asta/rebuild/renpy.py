"""Ren'Py (.rpy) → visual novel do ASTA.

Lê os scripts de texto (`game/*.rpy`) e reconstrói a estrutura: rótulos, falas, cenas, personagens, escolhas (`menu`), saltos, variáveis e condições.
Menus e `if` com escolhas dentro viram rótulos auxiliares que continuam o fluxo; `call` é incorporado quando possível. Python embutido, telas e transformações
não são convertidos (aviso). Arquivos compilados (`.rpyc`) e arquivos (`.rpa`) não são lidos — use os scripts `.rpy`. A arte e o áudio originais não são copiados.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..games2d import schema as S
from .rpgconv import _split

KEYWORDS = {"label", "jump", "call", "scene", "show", "hide", "play", "stop", "queue", "pause", "with", "window", "define", "default", "image", "python", "init", "if", "elif", "else",
            "menu", "return", "transform", "screen", "style", "renpy", "voice", "nvl", "pass", "while", "for", "translate", "layeredimage", "camera", "rpy", "testcase"}
SKIP_BLOCKS = {"python", "init", "transform", "screen", "style", "translate", "layeredimage", "testcase", "camera"}
EXPRS = ("happy", "sad", "angry", "surprised", "shy", "neutral")
EXPR_WORDS = {"happy": "happy|smile|laugh|joy|grin|feliz", "sad": "sad|cry|tear|upset|triste", "angry": "angry|mad|annoy|furious|bravo", "surprised": "surpris|shock|wow|gasp",
              "shy": "shy|blush|embarrass|tim"}
SCENE_WORDS = (("cafe", "cafe|coffee|restaurant|bar"), ("school", "school|class|escola"), ("bedroom", "bedroom|quarto"), ("kitchen", "kitchen|cozinha"), ("beach", "beach|sea|ocean|praia"),
               ("forest", "forest|wood|floresta"), ("city", "city|town|cidade"), ("street", "street|road|rua"), ("night_sky", "night|sky|stars|noite|black"), ("castle", "castle|palace|castelo"),
               ("cave", "cave|dungeon"), ("library", "library|biblioteca"), ("garden", "garden|park|jardim"), ("sunset", "sunset|dusk"), ("office", "office|escritorio"),
               ("field", "field|meadow|campo"), ("lab", "lab"), ("ship", "ship|boat|navio"), ("cellar", "cellar|basement"), ("room", "room|house|home|sala|casa|interior"))
MOOD_WORDS = (("tense", "tense|battle|fight|danger|suspense"), ("mysterious", "myster|dark|creepy|night"), ("epic", "epic|hero|final|boss"), ("melancholic", "sad|melanch|tears|rain|lonely"),
              ("joyful", "happy|joy|fun|cheer|festival"), ("calm", "calm|peace|soft|relax|theme"))


class Node:
    def __init__(self, kind: str, text: str = "", children: Optional[List["Node"]] = None, line: int = 0):
        self.kind, self.text, self.children, self.line = kind, text, children or [], line
        self.options: List[Tuple[str, str, "Node"]] = []  # menu: (texto, condição, nó com o bloco)


def _strip_comment(line: str) -> str:
    q = ""
    for i, ch in enumerate(line):
        if q:
            if ch == "\\":
                continue
            if ch == q:
                q = ""
        elif ch in "\"'":
            q = ch
        elif ch == "#":
            return line[:i]
    return line


def _lines(src: str) -> List[Tuple[int, int, str]]:
    out = []
    for no, raw in enumerate(src.replace("\t", "    ").splitlines(), 1):
        t = _strip_comment(raw).rstrip()
        if t.strip():
            out.append((no, len(t) - len(t.lstrip()), t.strip()))
    return out


def parse(src: str, warn) -> List[Node]:
    lines = _lines(src)

    def block(i: int, indent: int) -> Tuple[List[Node], int]:
        nodes: List[Node] = []
        while i < len(lines):
            no, ind, t = lines[i]
            if ind < indent:
                break
            if ind > indent:  # linha mais recuada que o esperado (continuação que não entendemos)
                i += 1
                continue
            i += 1
            head = t.split(None, 1)[0].rstrip(":(") if t else ""
            opens = t.endswith(":")
            child: List[Node] = []
            if opens and i < len(lines) and lines[i][1] > indent:
                if head in SKIP_BLOCKS or (head == "label" and False):
                    j = i
                    while j < len(lines) and lines[j][1] > indent:
                        j += 1
                    if head in ("python", "init", "screen", "transform"):
                        warn(f"bloco «{head}» não convertido (linha {no})")
                    i = j
                    nodes.append(Node("skip", t, line=no))
                    continue
                if head == "menu":
                    n = Node("menu", t, line=no)
                    bind = lines[i][1]
                    while i < len(lines) and lines[i][1] >= bind:
                        l2no, l2ind, l2t = lines[i]
                        i += 1
                        if l2ind > bind:
                            continue
                        if l2t.endswith(":"):
                            m = re.match(r"""^(?P<q>"|')(?P<tx>(?:[^"'\\]|\\.)*)(?P=q)\s*(?:if\s+(?P<cond>.+?))?:$""", l2t)
                            body: List[Node] = []
                            if i < len(lines) and lines[i][1] > bind:
                                body, i = block(i, lines[i][1])
                            if m:
                                n.options.append((m.group("tx"), m.group("cond") or "", Node("block", children=body, line=l2no)))
                        else:
                            mm = re.match(r"""^(?:\w+\s+)?(?P<q>"|')(?P<tx>(?:[^"'\\]|\\.)*)(?P=q)$""", l2t)
                            if mm and not n.text.startswith("caption"):
                                n.text = "caption " + mm.group("tx")
                    nodes.append(n)
                    continue
                child, i = block(i, lines[i][1])
            elif opens and head == "menu":
                nodes.append(Node("menu", t, line=no))
                continue
            nodes.append(Node(head if head in KEYWORDS or t.startswith("$") else "line", t, child, no))
        return nodes, i

    nodes, _ = block(0, lines[0][1] if lines else 0)
    return nodes


_TAG = re.compile(r"\{/?[a-zA-Z]+(?:=[^}]*)?\}")


def clean(s: str) -> str:
    s = s.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\").replace("{{", "\x00").replace("[[", "\x01")
    s = _TAG.sub("", s)
    s = re.sub(r"\[([A-Za-z_]\w*)(?:![a-z])?\]", r"{\1}", s)
    return s.replace("\x00", "{").replace("\x01", "[").strip()


def _lit(v: str) -> Tuple[bool, Any]:
    v = v.strip()
    if v in ("True", "False"):
        return True, v == "True"
    if re.fullmatch(r"-?\d+", v):
        return True, int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return True, float(v)
    m = re.fullmatch(r"""(["'])((?:[^"'\\]|\\.)*)\1""", v)
    if m:
        return True, clean(m.group(2))
    return False, None


def cond_of(expr: str, warn) -> str:
    e = re.sub(r"\bTrue\b", "true", expr.strip())
    e = re.sub(r"\bFalse\b", "false", e)
    e = re.sub(r"\bis not\b", "!=", e)
    e = re.sub(r"\bis\b", "==", e)
    e = re.sub(r"\bnot\s+in\b|\bin\b", "==", e) if False else e
    if S.parse_cond(e):
        return e
    warn(f"condição não convertida: «{expr[:60]}» (tratada como verdadeira)")
    return "true"


class Compiler:
    def __init__(self, nodes: List[Node], warn):
        self.nodes, self.warn = nodes, warn
        self.labels: Dict[str, List[Node]] = {}
        self.order: List[str] = []
        self.out: Dict[str, List[dict]] = {}
        self.chars: Dict[str, Dict[str, Any]] = {}
        self.tags: Dict[str, str] = {}
        self.bgs: Dict[str, Dict[str, str]] = {}
        self.vars: Dict[str, Any] = {}
        self.n = 0
        self.title = ""
        self.sample: List[str] = []
        self.skipped = 0
        self.collect(nodes)

    def collect(self, nodes: List[Node]) -> None:
        for nd in nodes:
            t = nd.text
            if nd.kind == "label":
                m = re.match(r"label\s+([A-Za-z_]\w*)", t)
                if m and m.group(1) not in self.labels:
                    self.labels[m.group(1)] = nd.children
                    self.order.append(m.group(1))
            elif nd.kind == "define" or nd.kind == "default":
                m = re.match(r"(?:define|default)\s+(?:\w+\.)?(\w+)\s*=\s*(.+)$", t)
                if not m:
                    continue
                name, val = m.group(1), m.group(2)
                cm = re.match(r"""Character\(\s*(None|"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')\s*(?:,(.*))?\)\s*$""", val)
                if cm:
                    nm = cm.group(2) if cm.group(2) is not None else (cm.group(3) or "")
                    col = re.search(r"""color\s*=\s*["'](#[0-9a-fA-F]{3,8})["']""", cm.group(4) or "")
                    img = re.search(r"""image\s*=\s*["'](\w+)["']""", cm.group(4) or "")
                    self.chars[name] = {"id": name, "name": clean(nm) or name.title(), "color": (col.group(1)[:7] if col else "#c8d6ff")}
                    if img:
                        self.tags[img.group(1)] = name
                elif name == "config_name" or t.startswith("define config.name"):
                    pass
                else:
                    ok, v = _lit(val)
                    if ok and nd.kind == "default" or (ok and isinstance(v, (int, float, bool))):
                        self.vars[name] = v
                    if t.startswith("define config.name"):
                        ok, v = _lit(val)
                        self.title = v if ok else self.title
            elif nd.kind == "line" and nd.text.startswith("define config.name"):
                pass
            if nd.children and nd.kind not in ("label",):
                self.collect(nd.children)
        for nd in nodes:
            if nd.kind == "define":
                m = re.match(r"define\s+config\.name\s*=\s*_?\(?\s*(.+?)\)?\s*$", nd.text)
                if m:
                    ok, v = _lit(m.group(1))
                    if ok and isinstance(v, str):
                        self.title = v

    # ---------------------------------------------------------------- compilação
    def new_label(self) -> str:
        self.n += 1
        return f"_r{self.n}"

    def has_menu(self, nodes: List[Node]) -> bool:
        return any(n.kind == "menu" or self.has_menu(n.children) for n in nodes)

    @staticmethod
    def terminal(stmts: List[dict]) -> bool:
        return bool(stmts) and stmts[-1]["c"] in ("jump", "end", "menu")

    def char_id(self, tag: str) -> str:
        tag = self.tags.get(tag, tag)
        if tag not in self.chars:
            self.chars[tag] = {"id": tag, "name": tag.replace("_", " ").title(), "color": "#c8d6ff"}
        return tag

    def bg(self, words: List[str]) -> str:
        key = "_".join(words) or "bg"
        if key not in self.bgs:
            joined = " ".join(words).lower()
            self.bgs[key] = {"scene": next((s for s, pat in SCENE_WORDS if re.search(pat, joined)), "room")}
        return key

    def comp(self, nodes: List[Node], cont: Optional[str], inline: bool = False, depth: int = 0) -> List[dict]:
        out: List[dict] = []
        for idx, nd in enumerate(nodes):
            k, t = nd.kind, nd.text
            if k == "menu":
                rest = nodes[idx + 1:]
                after = cont
                if rest:
                    after = self.new_label()
                    self.out[after] = self._finish(self.comp(rest, cont, inline, depth), cont)
                choices = []
                for text, cond, body in nd.options[:6]:
                    lbl = self.new_label()
                    self.out[lbl] = self._finish(self.comp(body.children, after, inline, depth), after)
                    ch: Dict[str, Any] = {"text": clean(text)[:100], "jump": lbl}
                    if cond:
                        ch["if"] = cond_of(cond, self.warn)
                    choices.append(ch)
                if len(nd.options) > 6:
                    self.warn("menu com mais de 6 opções: as demais foram cortadas")
                prompt = clean(t[8:]) if t.startswith("caption ") else ""
                if choices:
                    out.append({"c": "menu", "prompt": prompt[:160], "choices": choices})
                return out
            if k == "if":
                m = re.match(r"if\s+(.+?):$", t)
                branches = [(m.group(1) if m else "true", nd.children)]
                # elif/else seguintes fazem parte deste if
                j = idx + 1
                while j < len(nodes) and nodes[j].kind in ("elif", "else"):
                    mm = re.match(r"elif\s+(.+?):$", nodes[j].text)
                    branches.append((mm.group(1) if mm else None, nodes[j].children))
                    j += 1
                consumed = j - idx - 1
                rest_nodes = nodes[idx + 1 + consumed:]
                split = any(self.has_menu(b) for _, b in branches)
                after = cont
                if split and rest_nodes:
                    after = self.new_label()
                    self.out[after] = self._finish(self.comp(rest_nodes, cont, inline, depth), cont)

                def chain(bs):
                    cnd, body = bs[0]
                    stm = self.comp(body, after if split else None, inline, depth)
                    if split:
                        stm = self._finish(stm, after)
                    els = chain(bs[1:]) if len(bs) > 1 else ([self._finish([], after)] if split and after else [])
                    if cnd is None:
                        return stm
                    return [{"c": "if", "cond": cond_of(cnd, self.warn), "then": stm, "else": [x for x in els if x]}]
                out.extend(chain(branches))
                if split:
                    return out
                nodes = nodes[:idx + 1] + [Node("skip")] * consumed + rest_nodes if consumed else nodes
                for q in range(consumed):
                    nodes[idx + 1 + q] = Node("skip")
                continue
            if k in ("elif", "else", "skip", "define", "default", "image", "init", "python", "transform", "screen", "style", "pass", "window", "voice", "nvl", "translate", "rpy", "label"):
                if k == "label" and nd is not None and False:
                    pass
                continue
            if k == "jump":
                m = re.match(r"jump\s+([A-Za-z_]\w*)", t)
                if m and m.group(1) in self.labels:
                    out.append({"c": "jump", "label": m.group(1)})
                    return out
                self.warn(f"jump para destino desconhecido/dinâmico ignorado: «{t[:40]}»")
            elif k == "call":
                m = re.match(r"call\s+([A-Za-z_]\w*)", t)
                tgt = m.group(1) if m else ""
                if tgt in self.labels and depth < 3 and not self.has_menu(self.labels[tgt]):
                    out.extend(self.comp(self.labels[tgt], None, True, depth + 1))
                elif tgt in self.labels:
                    self.warn(f"call «{tgt}» com escolhas virou jump (o retorno não é reproduzido)")
                    out.append({"c": "jump", "label": tgt})
                    return out
            elif k == "return":
                if inline:
                    return out
                out.append({"c": "end", "title": "Fim"})
                return out
            elif k == "scene":
                words = [w for w in re.split(r"\s+", t[5:].strip()) if w and w not in ("with", "at", "onlayer", "master") and not w.startswith("with")]
                words = words[:3] if "with" not in t[5:].split() else t[5:].split("with")[0].split()[:3]
                if words and words[0] == "bg":
                    words = words[1:]
                out.append({"c": "scene", "bg": self.bg(words)})
            elif k == "show":
                parts = t[4:].strip().split()
                if parts and parts[0] not in ("screen", "text", "layer"):
                    tag = parts[0]
                    attrs = " ".join(parts[1:])
                    at = re.search(r"\bat\s+(\w+)", attrs)
                    pos = {"left": "left", "right": "right", "center": "center", "truecenter": "center", "centre": "center"}.get(at.group(1) if at else "center", "center")
                    expr = next((e for e, pat in EXPR_WORDS.items() if re.search(pat, attrs.split(" at ")[0].lower())), "neutral")
                    out.append({"c": "show", "char": self.char_id(tag), "expr": expr, "at": pos})
            elif k == "hide":
                parts = t[4:].strip().split()
                if parts:
                    out.append({"c": "hide", "char": self.char_id(parts[0])})
            elif k == "play":
                parts = t.split(None, 2)
                if len(parts) >= 2 and parts[1] == "music":
                    name = parts[2] if len(parts) > 2 else ""
                    out.append({"c": "music", "mood": next((m for m, pat in MOOD_WORDS if re.search(pat, name.lower())), "calm")})
                elif len(parts) >= 2 and parts[1] in ("sound", "audio"):
                    out.append({"c": "sfx", "name": "chime"})
            elif k == "stop" and t.startswith("stop music"):
                out.append({"c": "music", "mood": "stop"})
            elif k == "pause":
                m = re.match(r"pause\s+([\d.]+)", t)
                out.append({"c": "wait", "seconds": min(5.0, float(m.group(1))) if m else 1.0})
            elif t.startswith("$"):
                m = re.match(r"\$\s*(\w+)\s*(=|\+=|-=)\s*(.+)$", t)
                if m:
                    ok, v = _lit(m.group(3))
                    if ok and (m.group(2) == "=" or isinstance(v, (int, float))):
                        self.vars.setdefault(m.group(1), False if isinstance(v, bool) else ("" if isinstance(v, str) else 0))
                        out.append({"c": "set", "var": m.group(1), "op": m.group(2), "value": v})
                        continue
                self.skipped += 1
                self.warn("linhas «$ …» (Python) com funções/expressões não foram convertidas", once=True) if False else self.warn("linhas «$ …» (Python) com funções/expressões não foram convertidas")
            elif k == "line":
                say = self.say(t)
                if say:
                    out.extend(say)
                elif not re.match(r"^(with|renpy\.|config\.|gui\.|style\.|persistent\.|extend)", t):
                    self.skipped += 1
        if cont and not self.terminal(out) and not inline:
            out.append({"c": "jump", "label": cont})
        return out

    def _finish(self, stmts: List[dict], cont: Optional[str]) -> List[dict]:
        if cont and not self.terminal(stmts):
            stmts = stmts + [{"c": "jump", "label": cont}]
        return stmts

    def say(self, t: str) -> List[dict]:
        m = re.match(r"""^(?:(?P<w>[A-Za-z_]\w*)(?:\s+[\w@]+)*\s+)?(?P<s1>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')(?:\s+(?P<s2>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'))?(?:\s+(?:with|nointeract)\b.*)?$""", t)
        if not m or (m.group("w") and m.group("w") in KEYWORDS):
            return []
        s1, s2, who = m.group("s1")[1:-1], m.group("s2"), m.group("w")
        if s2 is not None:  # "Nome" "fala"
            text, speaker = s2[1:-1], clean(s1)
            cid = next((c["id"] for c in self.chars.values() if c["name"] == speaker), None) or self.char_id(re.sub(r"\W+", "_", speaker.lower()).strip("_") or "x")
            if cid in self.chars and self.chars[cid]["name"] == cid.title():
                self.chars[cid]["name"] = speaker
            who = cid
        else:
            text = s1
            who = self.char_id(who) if who and (who in self.chars or who in self.tags or len(who) <= 12) else None
        body = clean(text)
        self.sample.append(body)
        return [{"c": "say", "who": who or "", "text": piece} for piece in _split(body) if piece]

    @staticmethod
    def _targets(stmts: List[dict]):
        for x in stmts:
            if x["c"] == "jump":
                yield x["label"]
            elif x["c"] == "menu":
                for ch in x["choices"]:
                    yield ch["jump"]
            elif x["c"] == "if":
                yield from Compiler._targets(x["then"])
                yield from Compiler._targets(x["else"])

    def _prune(self, labels: Dict[str, List[dict]], start: str) -> Dict[str, List[dict]]:
        """Fica só o que o jogo alcança a partir do início (rótulos só usados por `call` já foram incorporados)."""
        seen, todo = set(), [start]
        while todo:
            n = todo.pop()
            if n in seen or n not in labels:
                continue
            seen.add(n)
            todo.extend(self._targets(labels[n]))
        return {k: v for k, v in labels.items() if k in seen}

    def build(self) -> Dict[str, Any]:
        if not self.labels:
            raise ValueError("nenhum «label» encontrado nos scripts .rpy")
        start = "start" if "start" in self.labels else self.order[0]
        labels: Dict[str, List[dict]] = {}
        for i, name in enumerate(self.order):
            nxt = self.order[i + 1] if i + 1 < len(self.order) else None
            body = self.comp(self.labels[name], None)
            if not self.terminal(body):
                body.append({"c": "jump", "label": nxt} if nxt else {"c": "end", "title": "Fim"})
            labels[name] = body
        labels.update(self.out)
        labels = self._prune(labels, start)
        return {"characters": list(self.chars.values())[:12], "backgrounds": self.bgs, "variables": self.vars, "start": start, "labels": labels}


def convert(files: List[Tuple[str, str]]) -> Tuple[Dict[str, Any], List[str], Dict[str, Any]]:
    """[(nome, texto .rpy)] → (dicionário bruto do jogo, avisos, informações)."""
    warns: List[str] = []
    seen = set()

    def warn(m: str) -> None:
        if m not in seen and len(warns) < 60:
            seen.add(m)
            warns.append(m)

    nodes: List[Node] = []
    for name, txt in sorted(files, key=lambda x: (0 if x[0].lower().endswith("script.rpy") else 1, x[0].lower())):
        if "/renpy/" in name.lower() or name.lower().startswith("renpy/"):
            continue
        try:
            nodes.extend(parse(txt, warn))
        except Exception as exc:  # noqa: BLE001  (script malformado: segue com os outros arquivos)
            warn(f"{name}: não foi possível ler ({exc})")
    comp = Compiler(nodes, warn)
    data = comp.build()
    if comp.skipped:
        warn(f"{comp.skipped} linha(s) de script não reconhecidas foram ignoradas")
    lang = "pt-BR" if re.search(r"[ãõçáéíóú]|\b(você|não|para|uma)\b", " ".join(comp.sample[:200]).lower()) else "en"
    raw = {"title": comp.title, "language": lang, "style": {"theme": "cozy"}, "data": data}
    return raw, warns, {"labels": len(comp.labels), "characters": len(comp.chars)}
