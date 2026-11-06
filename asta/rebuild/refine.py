"""Refinamento por IA do Rebuild: uma equipe de agentes pequenos e bem vigiados que só mexe no TEXTO do jogo reconstruído.

A conversão (leitura → motores 2D) continua sendo determinística e é ela que garante a estrutura igual à do original. A IA entra depois, em etapas curtas,
pensadas para modelos locais pequenos (poucos bilhões de parâmetros, janela de contexto curta):

1. **Limpeza** (sem IA): tira restos de códigos do motor (``\\C[2]``, ``{w}``…), conserta texto com acentos quebrados (UTF-8 lido como Latin-1) e espaços.
2. **Perfilador** (1 chamada, entrada de poucas centenas de tokens): resume tom/cenário e dá nomes legíveis a eventos/mapas com nome genérico (``EV012``, ``Map003``).
3. **Polidor** (várias chamadas, lotes de até 6 falas): corrige erros de digitação, maiúsculas, pontuação e símbolos soltos nas falas que parecem ter problema.
   Nunca traduz, nunca acrescenta nem tira frases; cada fala devolvida passa por validadores (marcadores ``{x}``, números, tamanho, semelhança) e a que falha volta ao original.
   Lote que falha é dividido em falas avulsas (uma vez); sem resposta válida, fica o original.
4. **Auditor** (1 chamada com os antes/depois): segunda opinião sobre o que mudou; as mudanças que ele recusa são desfeitas.
5. **Trava estrutural** (sem IA): a «impressão digital» do jogo sem os textos precisa ser idêntica à de antes — senão tudo volta ao original.

Qualquer falha de um agente (JSON inválido, modelo fora do ar) deixa o resultado determinístico intacto: a IA só pode melhorar, nunca estragar a estrutura.
"""
from __future__ import annotations

import copy
import difflib
import json
import re
from collections import Counter
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

TEXT_KEYS = ("text", "name", "prompt", "desc", "title", "intro")  # os únicos campos que o refinamento pode alterar
MAX_CALLS = 40  # teto de chamadas ao modelo por reconstrução (o resto fica como está)
BATCH_LINES, BATCH_CHARS = 6, 900

CODE_RE = re.compile(r"\\[A-Za-z]{1,3}\[\d*\]|\\[.!|^<>{}$]|\{(?:w|p|nw|fast|cps|i|b|u|s|a|k|plain|art|rt|font|size|color|alpha|outlinecolor|image|space|vspace|rb|rt|clear|done|noalt)\b[^}]*\}|\{/(?:w|p|i|b|u|s|a|k|color|size|font|alpha|rb|rt)\}")
MOJIBAKE_RE = re.compile(r"[ÃÂ][\x80-\xbf]|â€|Ã£|Ã©|Ã§|Ãª|Ã³|Ã¡|Ã­|Ãº|�")
PLACEHOLDER_RE = re.compile(r"\{[^{}\s]{1,30}\}|\[[A-Za-z_][A-Za-z0-9_]{0,30}\]|%\(\w+\)s")
GENERIC_NAME_RE = re.compile(r"^\s*(?:ev|event|evento|map|mapa|npc|obj|object|objeto)?\s*[-_#]?\s*\d{1,4}\s*$", re.I)


# ---------------------------------------------------------------------------------------------------- limpeza determinística
def clean_text(s: str) -> str:
    """Tira restos de códigos do motor, repara acentos quebrados e arruma espaços. Devolve o texto limpo (igual ao original se não havia o que limpar)."""
    out = str(s)
    if MOJIBAKE_RE.search(out):
        try:
            fixed = out.encode("latin-1").decode("utf-8")
            if not MOJIBAKE_RE.search(fixed):
                out = fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    out = CODE_RE.sub("", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +\n", "\n", out)
    return out.strip()


def looks_rough(s: str) -> bool:
    """O texto parece precisar de revisão (depois da limpeza): sobrou acento quebrado, só maiúsculas, símbolos soltos, letras repetidas, sem pontuação final…"""
    t = s.strip()
    if len(t) < 4:
        return False
    letters = [c for c in t if c.isalpha()]
    if MOJIBAKE_RE.search(t):
        return True
    if len(letters) >= 8 and all(c.isupper() for c in letters):
        return True
    if re.search(r"([^\W\d_])\1{4,}", t) or re.search(r"[#*_~<>|^]{2,}", t):
        return True
    if len(t) > 40 and not re.search(r"[.!?…:;»”\"')\]]$", t) and not t.endswith(("...", "—")):
        return True
    if re.search(r"\s[,.;:!?]", t) or re.search(r"[,;][^\s\d]", t):
        return True
    return False


# ---------------------------------------------------------------------------------------------------- unidades de texto
class Unit:
    """Um texto do jogo que o refinamento pode alterar (guarda onde ele mora para gravar de volta)."""

    def __init__(self, uid: int, kind: str, holder: dict, key: str, who: str = "", hint: str = ""):
        self.id, self.kind, self.holder, self.key, self.who, self.hint = uid, kind, holder, key, who, hint
        self.original = str(holder.get(key) or "")

    @property
    def text(self) -> str:
        return str(self.holder.get(self.key) or "")

    def set(self, value: str) -> None:
        self.holder[self.key] = value


def _walk(node: Any, ctx: Dict[str, str]) -> Iterator[Tuple[dict, str, str, Dict[str, str]]]:
    """Percorre o jogo e devolve (dict, chave, tipo, contexto) de cada texto alterável: falas, opções de escolha e nomes de eventos/mapas."""
    if isinstance(node, dict):
        if node.get("c") == "say" and isinstance(node.get("text"), str):
            yield node, "text", "line", dict(ctx, who=str(node.get("who") or ""))
        if node.get("c") == "menu" and isinstance(node.get("prompt"), str) and node.get("prompt"):
            yield node, "prompt", "line", ctx
        if isinstance(node.get("options"), list) or isinstance(node.get("choices"), list):
            for o in (node.get("options") or node.get("choices") or []):
                if isinstance(o, dict) and isinstance(o.get("text"), str):
                    yield o, "text", "choice", ctx
        if "pages" in node and "kind" in node and "x" in node:  # evento de mapa
            nm = str(node.get("name") or "")
            if not nm or GENERIC_NAME_RE.match(nm):
                yield node, "name", "event", dict(ctx, event=str(node.get("id") or ""))
        if "tiles" in node and "events" in node:  # mapa
            nm = str(node.get("name") or "")
            if GENERIC_NAME_RE.match(nm) or re.match(r"^\s*(?:map|mapa)\s*[-_#]?\s*\d+\s*$", nm, re.I):
                yield node, "name", "map", dict(ctx, map=str(node.get("id") or ""))
            ctx = dict(ctx, map=str(node.get("name") or node.get("id") or ""))
        for k, v in node.items():
            if k in ("tiles", "appearance"):
                continue
            yield from _walk(v, ctx)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, ctx)


def collect_units(spec: Dict[str, Any]) -> List[Unit]:
    out: List[Unit] = []
    for holder, key, kind, ctx in _walk(spec.get("data") or {}, {}):
        hint = ""
        if kind in ("event", "map"):
            hint = _first_line(holder)
        out.append(Unit(len(out) + 1, kind, holder, key, who=ctx.get("who", ""), hint=hint))
        out[-1].map_name = ctx.get("map", "")  # type: ignore[attr-defined]
    return out


def _first_line(node: Any) -> str:
    for h, k, kind, _ in _walk(node, {}):
        if kind == "line" and k == "text" and h.get("text"):
            return str(h["text"])[:100]
    return ""


def fingerprint(spec: Dict[str, Any]) -> str:
    """Estrutura do jogo sem os textos alteráveis: tem de ser idêntica antes e depois do refinamento."""
    def strip(n: Any) -> Any:
        if isinstance(n, dict):
            return {k: ("" if k in TEXT_KEYS and isinstance(v, str) else strip(v)) for k, v in n.items()}
        if isinstance(n, list):
            return [strip(v) for v in n]
        return n

    return json.dumps(strip({"data": spec.get("data"), "genre": spec.get("genre")}), sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------------------------------- validadores
def _fold(s: str) -> str:
    """Minúsculas, sem acentos, marcadores, números e pontuação (para comparar só as palavras)."""
    import unicodedata

    s = PLACEHOLDER_RE.sub(" ", s)
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z]+", " ", s).strip()


def accept_line(old: str, new: Any) -> Optional[str]:
    """Aceita a fala devolvida pelo modelo só se for uma revisão do original (não uma reescrita, tradução ou invenção). Devolve o texto limpo ou None."""
    if not isinstance(new, str):
        return None
    cand = new.strip().strip("`").strip()
    if len(cand) >= 2 and cand[0] == cand[-1] and cand[0] in "\"'“" and old.strip()[:1] not in "\"'“":
        cand = cand[1:-1].strip()
    if not cand or cand == old or "```" in cand or "\n\n\n" in cand:
        return None
    if Counter(PLACEHOLDER_RE.findall(old)) != Counter(PLACEHOLDER_RE.findall(cand)):
        return None
    if Counter(re.findall(r"\d+", old)) != Counter(re.findall(r"\d+", cand)):
        return None
    lo, ln = len(old), len(cand)
    if ln > max(lo * 1.4, lo + 12) or ln < min(lo * 0.6, lo - 12):
        return None
    if old.count("\n") != cand.count("\n"):
        return None
    if difflib.SequenceMatcher(None, _fold(old), _fold(cand)).ratio() < 0.7:  # sem acentos/marcadores/números: uma tradução ou reescrita não passa
        return None
    if re.match(r"^(here\b|aqui est|claro|sure|ok[,:!])", cand, re.I) and not re.match(r"^(here\b|aqui est|claro|sure|ok[,:!])", old, re.I):
        return None
    return cand


def accept_name(old: str, new: Any) -> Optional[str]:
    if not isinstance(new, str):
        return None
    n = re.sub(r"\s+", " ", new).strip().strip("\"'`")
    if not (2 <= len(n) <= 30) or GENERIC_NAME_RE.match(n) or CODE_RE.search(n) or any(c in n for c in "{}[]<>\\/"):
        return None
    return n


# ---------------------------------------------------------------------------------------------------- prompts dos agentes
PROFILER = """ROLE: Profiler (rebuild of an existing game).
INPUT_JSON describes a game that was already converted. Do NOT change its structure. Read the sample lines and the character list, then:
1. Write "summary" (max 2 short sentences), "tone" (1-3 words) and "setting" (1-3 words), in the game's language.
2. In "generic", each entry is an event or map with a placeholder name (like "EV012" or "Map003"). Give each a short, natural name (2-4 words, max 30 characters)
   based on its hint/where/kind, in the game's language. If you cannot tell, OMIT that entry. Use ONLY the ids given.
Output JSON: {"summary": str, "tone": str, "setting": str, "names": [{"id": int, "name": str}]}"""

POLISHER = """ROLE: Polisher (proofreader of already-written game text).
Fix ONLY: typos, broken characters, wrong capitalization (e.g. ALL CAPS shouting that is not meant), spacing, punctuation and stray symbols.
STRICT RULES: keep the same language (never translate); keep the same meaning, voice and number of sentences; keep names, numbers and any {placeholder}/[placeholder] exactly;
keep line breaks; do not add notes, quotes or explanations. If a line is already fine, return it unchanged.
INPUT_JSON.style gives the game's tone. Reply with EVERY id: {"lines": [{"id": int, "text": str}]}"""

AUDITOR = """ROLE: Auditor (checks a proofreader's work).
INPUT_JSON.changes lists {id, before, after}. Reject a change (put its id in "reject") when "after" changes the meaning, translates, adds or removes information,
alters a name or number, or sounds worse than "before". Accept pure fixes of typos, characters, case and punctuation.
Output JSON: {"reject": [int], "notes": str}  (an empty list means all are fine)"""


def clean_only(spec: Dict[str, Any]) -> int:
    """Só a limpeza determinística (sem IA), com a mesma trava estrutural. Devolve quantos textos foram arrumados."""
    fp, n = fingerprint(spec), 0
    before = copy.deepcopy(spec)
    for u in collect_units(spec):
        if u.kind in ("line", "choice"):
            c = clean_text(u.text)
            if c and c != u.text:
                u.set(c)
                n += 1
    if fingerprint(spec) != fp:
        spec.clear()
        spec.update(before)
        return 0
    return n


# ---------------------------------------------------------------------------------------------------- orquestração
class Refiner:
    """Roda o Perfilador → Polidor → Auditor sobre um jogo. `agent(step, name, instruction, payload, fallback, tokens_mult)` é o `Runner._agent` do pipeline."""

    def __init__(self, agent: Callable[..., Tuple[Dict[str, Any], bool]], step: Callable[..., None], check: Callable[[], None], warn: Callable[[str], None],
                 max_calls: int = MAX_CALLS):
        self.agent, self.step, self.check, self.warn, self.max_calls = agent, step, check, warn, max_calls
        self.calls = 0
        self.stats: Dict[str, Any] = {"cleaned": 0, "polished": 0, "named": 0, "rejected": 0, "calls": 0, "reverted": False, "model_failed": 0}

    # ---- passos
    def run(self, spec: Dict[str, Any], info: Dict[str, Any]) -> Dict[str, Any]:
        before = copy.deepcopy(spec)
        fp = fingerprint(spec)
        units = collect_units(spec)
        self._clean(units)
        style = self._profile(spec, info, units)
        changes = self._polish(units, style)
        self._audit(units, changes)
        if fingerprint(spec) != fp:  # nunca deveria acontecer; se acontecer, a estrutura original vence
            spec.clear()
            spec.update(before)
            self.stats["reverted"] = True
            self.warn("refinamento: a estrutura mudou — voltei ao resultado determinístico")
        self.stats["calls"] = self.calls
        return self.stats

    def _clean(self, units: List[Unit]) -> None:
        for u in units:
            if u.kind in ("event", "map"):
                continue
            c = clean_text(u.text)
            if c and c != u.text:
                u.set(c)
                u.original = c  # a limpeza não conta como «mudança da IA»: não passa pelo Auditor
                self.stats["cleaned"] += 1

    def _budget(self) -> bool:
        return self.calls < self.max_calls

    def _profile(self, spec: Dict[str, Any], info: Dict[str, Any], units: List[Unit]) -> Dict[str, str]:
        generic = [u for u in units if u.kind in ("event", "map")][:30]
        d = spec.get("data") or {}
        chars = [c.get("name") for c in (d.get("characters") or d.get("party") or []) if isinstance(c, dict)][:12]
        samples = [u.text[:120] for u in units if u.kind == "line" and len(u.text) > 12][:12]
        if not generic and not samples:
            self.step("profiler", "skipped")
            return {}
        payload = {"engine": info.get("engine_name", ""), "title": spec.get("title", ""), "language": spec.get("language", ""), "characters": chars, "samples": samples,
                   "generic": [{"id": u.id, "kind": u.kind, "where": getattr(u, "map_name", ""), "hint": u.hint} for u in generic]}
        self.calls += 1
        obj, fb = self.agent("profiler", "rebuild_profiler", PROFILER, payload, lambda p: {"summary": "", "tone": "", "setting": "", "names": []}, tokens_mult=0.15)
        if fb:
            self.stats["model_failed"] += 1
        by_id = {u.id: u for u in generic}
        for ent in (obj.get("names") if isinstance(obj.get("names"), list) else []):
            if not isinstance(ent, dict):
                continue
            try:
                u = by_id.get(int(ent.get("id")))
            except (TypeError, ValueError):
                continue
            nm = accept_name(u.text, ent.get("name")) if u else None
            if u and nm:
                u.set(nm)
                self.stats["named"] += 1
        style = {k: str(obj.get(k) or "")[:80] for k in ("tone", "setting")}
        self.step("profiler", "warn" if fb else "done", named=self.stats["named"], tone=style.get("tone", ""))
        return style

    def _batches(self, units: List[Unit]) -> List[List[Unit]]:
        out: List[List[Unit]] = []
        cur: List[Unit] = []
        size = 0
        for u in units:
            if cur and (len(cur) >= BATCH_LINES or size + len(u.text) > BATCH_CHARS):
                out.append(cur)
                cur, size = [], 0
            cur.append(u)
            size += len(u.text)
        if cur:
            out.append(cur)
        return out

    def _polish(self, units: List[Unit], style: Dict[str, str]) -> List[Unit]:
        todo = [u for u in units if u.kind in ("line", "choice") and u.text and len(u.text) <= 600 and looks_rough(u.text)]
        if not todo:
            self.step("polisher", "skipped")
            return []
        self.step("polisher", "running", total=len(todo))
        changed: List[Unit] = []
        queue = self._batches(todo)
        failed_batches = 0
        while queue:
            self.check()
            if not self._budget():
                self.warn(f"polidor: limite de {self.max_calls} chamadas atingido; o restante das falas ficou como estava")
                break
            batch = queue.pop(0)
            payload = {"style": style, "lines": [{"id": u.id, "who": u.who, "text": u.text} for u in batch]}
            self.calls += 1
            obj, fb = self.agent("polisher", "rebuild_polisher", POLISHER, payload, lambda p: {"lines": []}, tokens_mult=0.12 * max(1, len(batch)) + 0.1)
            got = {}
            for ent in (obj.get("lines") if isinstance(obj.get("lines"), list) else []):
                if isinstance(ent, dict):
                    try:
                        got[int(ent.get("id"))] = ent.get("text")
                    except (TypeError, ValueError):
                        pass
            if (fb or not got) and len(batch) > 1:  # lote que falhou: tenta de novo, uma fala por vez (modelos pequenos erram menos com entrada curta)
                failed_batches += 1
                self.stats["model_failed"] += 1
                queue = [[u] for u in batch] + queue
                continue
            if fb:
                self.stats["model_failed"] += 1
            for u in batch:
                new = accept_line(u.text, got.get(u.id))
                if new:
                    u.set(new)
                    changed.append(u)
                    self.stats["polished"] += 1
        self.step("polisher", "warn" if failed_batches else "done", polished=self.stats["polished"], total=len(todo))
        return changed

    def _audit(self, units: List[Unit], changed: List[Unit]) -> None:
        if not changed or not self._budget():
            self.step("auditor", "skipped")
            return
        sample = changed[:24]
        self.calls += 1
        obj, fb = self.agent("auditor", "rebuild_auditor", AUDITOR, {"changes": [{"id": u.id, "before": u.original, "after": u.text} for u in sample]}, lambda p: {"reject": []}, tokens_mult=0.15)
        ids = set()
        for x in (obj.get("reject") if isinstance(obj.get("reject"), list) else []):
            try:
                ids.add(int(x))
            except (TypeError, ValueError):
                pass
        for u in sample:
            if u.id in ids:
                u.set(u.original)
                self.stats["rejected"] += 1
                self.stats["polished"] -= 1
        self.step("auditor", "warn" if fb else "done", rejected=self.stats["rejected"])
