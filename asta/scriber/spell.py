"""Scriber — correção ortográfica e tipográfica em camadas. Nenhuma depende de internet; todas funcionam sem IA:

  1. **Regras** (sempre): espaços duplicados, espaço antes de pontuação, falta de espaço depois dela, palavra repetida, frase começando em minúscula, reticências e travessões.
  2. **Dicionário do sistema** (se existir): `hunspell` ou `aspell` instalados no computador, no idioma do documento (protocolo `-a`, igual nos dois). Palavras que o dicionário não conhece
     viram achados com sugestões. Sem o programa ou sem o dicionário do idioma, essa camada some (e a tela avisa).
  3. **Navegador**: o editor liga o `spellcheck` nativo com o `lang` do documento (sublinhado vermelho enquanto se digita) — isso é da tela, não daqui.
  4. **IA** (`agents.proofread_ai`): ortografia, gramática, concordância e pontuação com motivo, trecho a trecho — por cima das camadas acima.

Cada achado: `{p, start, end, found, fix, kind, msg, source}` — `p` é o índice do parágrafo na lista enviada, `start/end` posições nele."""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .schema import LANGUAGES, lang_base, norm_lang

MAX_PARAS = 4000
MAX_CHARS = 400_000
ABBR = {"sr", "sra", "srta", "dr", "dra", "prof", "profa", "etc", "ex", "mr", "mrs", "ms", "st", "vs", "av", "pág", "pag", "cap", "fig", "eg", "ie", "no", "nº", "art", "inc", "ltd", "jr", "sto", "sta", "obs"}
_WORD = re.compile(r"[^\W\d_][\w'’\-]*", re.U)


def _issue(p: int, start: int, end: int, found: str, fix: str, kind: str, msg: str, source: str = "rules") -> Dict[str, Any]:
    return {"p": p, "start": start, "end": end, "found": found, "fix": fix, "kind": kind, "msg": msg, "source": source}


# ---------------------------------------------------------------------------------------------------- camada 1: regras
def rule_issues(paragraphs: List[str], lang: str = "pt-BR") -> List[Dict[str, Any]]:
    base = lang_base(lang)
    out: List[Dict[str, Any]] = []
    for pi, s in enumerate(paragraphs):
        if not s.strip():
            continue
        for m in re.finditer(r"(?<=\S)[ \t]{2,}(?=\S)", s):
            out.append(_issue(pi, m.start(), m.end(), m.group(0), " ", "spacing", "Espaço duplicado"))
        if base != "fr":
            for m in re.finditer(r"(?<=[\w\)\]”\"»])[ \t]+([,.;:!?…])(?=\s|$|[^\W\d_])", s):
                if m.group(1) == "." and (re.search(r"\d\s*$", s[: m.start()]) or not re.match(r"(?:\s|$)", s[m.end():m.end() + 1])):
                    continue
                out.append(_issue(pi, m.start(), m.end(), m.group(0), m.group(1), "spacing", "Espaço antes da pontuação"))
        for m in re.finditer(r"(?<=[^\W\d_])([,;!?])(?=[^\W\d_])", s):   # «olá,mundo» (não mexe em 3,14 nem em URLs)
            out.append(_issue(pi, m.start(), m.end(), m.group(0), m.group(1) + " ", "spacing", "Falta espaço depois da pontuação"))
        for m in re.finditer(r"(?<![\w.])([^\W\d_]{2,})\.(?=[^\W\d_]{3,}\b)(?![^\s]*[/@])", s):   # «fim.Começo»
            word = m.group(1).lower()
            if word in ABBR or re.match(r"^(www|http|https|com|org|net)$", word):
                continue
            if re.match(r"^[a-zà-ÿ]", s[m.end():m.end() + 1]):
                continue   # «arquivo.txt», «site.com»: minúscula depois do ponto = provavelmente nome de arquivo
            out.append(_issue(pi, m.start() + len(m.group(1)), m.start() + len(m.group(1)) + 1, ".", ". ", "spacing", "Falta espaço depois do ponto"))
        for m in re.finditer(r"\b([^\W\d_]{2,})(\s+)\1\b", s, re.I | re.U):
            if m.group(1).lower() in ("que", "ha", "nós", "very", "had", "that", "bye", "so", "no", "blah", "tchau", "bem", "tão", "mais", "muito", "ta", "pa", "ah", "oh", "oi", "não"):
                continue   # repetições que a língua admite («bem bem», «não, não»)
            out.append(_issue(pi, m.start(), m.end(), m.group(0), m.group(1), "repeat", "Palavra repetida"))
        for m in re.finditer(r"(?:(?<=[.!?…])|(?<=[.!?…][\"”»’)]))[ \t]+([a-zà-ÿ])", s):
            before = re.search(r"([^\W\d_]+)[.!?…][\"”»’)]?\s*$", s[: m.start()])
            if before and (before.group(1).lower() in ABBR or len(before.group(1)) < 2):
                continue
            if re.match(r"^[a-zà-ÿ]\.[a-zà-ÿ]\.", s[m.start():].lstrip()):
                continue   # «e.g.», «a.m.»
            out.append(_issue(pi, m.start(1), m.end(1), m.group(1), m.group(1).upper(), "capital", "Frase começando em minúscula"))
        if re.search(r"\.{4,}", s):
            for m in re.finditer(r"\.{4,}", s):
                out.append(_issue(pi, m.start(), m.end(), m.group(0), "…", "typography", "Reticências em excesso"))
        if re.search(r"[!?]{4,}", s):
            for m in re.finditer(r"([!?])\1{3,}", s):
                out.append(_issue(pi, m.start(), m.end(), m.group(0), m.group(1) * 3, "typography", "Pontuação repetida demais"))
    return out


# ---------------------------------------------------------------------------------------------------- camada 2: dicionário do sistema
_dict_cache: Dict[str, Optional[Tuple[str, str]]] = {}


def _tool_for(lang: str) -> Optional[Tuple[str, str]]:
    """(programa, dicionário) que funciona para este idioma, ou None. O resultado fica em cache por idioma."""
    lang = norm_lang(lang)
    if lang in _dict_cache:
        return _dict_cache[lang]
    found: Optional[Tuple[str, str]] = None
    d = LANGUAGES[lang]["dict"]
    for prog, names in (("hunspell", [d, lang.replace("-", "_")]), ("aspell", [lang.replace("-", "_"), lang_base(lang)])):
        exe = shutil.which(prog)
        if not exe:
            continue
        for name in names:
            try:
                r = subprocess.run([exe, "-d", name, "-a"], input="^teste\n", capture_output=True, text=True, timeout=8)
            except (OSError, subprocess.SubprocessError):
                continue
            first = (r.stdout or "").splitlines()[:1]
            if r.returncode == 0 and first and first[0].startswith("@(#)") and "Can't open" not in (r.stderr or ""):
                found = (exe, name)
                break
        if found:
            break
    _dict_cache[lang] = found
    return found


def dictionary_available(lang: str) -> bool:
    return _tool_for(lang) is not None


def parse_ispell(output: str) -> List[Tuple[str, List[str]]]:
    """Saída do modo `-a` (hunspell/aspell): «& palavra N offset: s1, s2» e «# palavra offset» → [(palavra, sugestões)]."""
    res: List[Tuple[str, List[str]]] = []
    for line in output.splitlines():
        m = re.match(r"^&\s+(\S+)\s+\d+\s+\d+:\s*(.*)$", line)
        if m:
            res.append((m.group(1), [x.strip() for x in m.group(2).split(",") if x.strip()][:5]))
            continue
        m = re.match(r"^#\s+(\S+)\s+\d+\s*$", line)
        if m:
            res.append((m.group(1), []))
    return res


def dict_issues(paragraphs: List[str], lang: str, ignore: Iterable[str] = ()) -> List[Dict[str, Any]]:
    tool = _tool_for(lang)
    if not tool:
        return []
    skip = {w.lower() for w in ignore}
    words: Set[str] = set()
    for s in paragraphs:
        for m in _WORD.finditer(s):
            w = m.group(0).strip("'’-")
            if len(w) > 1 and not w.isupper():
                words.add(w)
    if not words:
        return []
    batch = "\n".join("^" + w for w in sorted(words)) + "\n"
    try:
        r = subprocess.run([tool[0], "-d", tool[1], "-a"], input=batch, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    bad = {w: sug for w, sug in parse_ispell(r.stdout or "") if w.lower() not in skip}
    out: List[Dict[str, Any]] = []
    for pi, s in enumerate(paragraphs):
        for m in _WORD.finditer(s):
            w = m.group(0).strip("'’-")
            if w in bad:
                st = m.start() + m.group(0).find(w)
                out.append(_issue(pi, st, st + len(w), w, bad[w][0] if bad[w] else "", "spelling", "Palavra fora do dicionário" + (": " + ", ".join(bad[w][:3]) if bad[w] else ""), "dictionary"))
    return out


# ---------------------------------------------------------------------------------------------------- junção
def merge_issues(*lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Junta achados de camadas diferentes: o primeiro de cada trecho vence os que se sobrepõem; ordem do texto."""
    allv = [i for lst in lists for i in lst]
    allv.sort(key=lambda i: (i["p"], i["start"], -(i["end"] - i["start"])))
    out: List[Dict[str, Any]] = []
    for i in allv:
        if out and out[-1]["p"] == i["p"] and i["start"] < out[-1]["end"]:
            continue
        out.append(i)
    return out


def proofread(paragraphs: Any, lang: Any = None, ignore: Iterable[str] = (), use_dict: bool = True) -> Dict[str, Any]:
    """Ortografia/tipografia sem IA. `paragraphs`: lista de textos. Devolve {issues, dictionary, truncated}."""
    lang = norm_lang(lang)
    ps = [str(x).replace("\xa0", " ") for x in paragraphs] if isinstance(paragraphs, list) else []   # espaço sem quebra conta como espaço (mesmo tamanho: as posições valem)
    truncated = len(ps) > MAX_PARAS or sum(len(x) for x in ps) > MAX_CHARS
    ps = ps[:MAX_PARAS]
    total = 0
    for i, s in enumerate(ps):
        total += len(s)
        if total > MAX_CHARS:
            ps = ps[: i + 1]
            ps[-1] = s[: max(0, len(s) - (total - MAX_CHARS))]
            break
    have_dict = use_dict and dictionary_available(lang)
    issues = merge_issues(dict_issues(ps, lang, ignore) if have_dict else [], rule_issues(ps, lang))
    return {"issues": issues[:2000], "dictionary": bool(have_dict), "language": lang, "truncated": truncated, "paragraphs": len(ps)}


def apply_issues(paragraphs: List[str], issues: List[Dict[str, Any]]) -> List[str]:
    """Aplica os `fix` (de trás para a frente em cada parágrafo, para as posições não mudarem). Só aplica o que ainda bate com o texto."""
    out = list(paragraphs)
    for i in sorted(issues, key=lambda x: (x["p"], -x["start"])):
        p = i.get("p", -1)
        if not (0 <= p < len(out)) or i.get("fix") is None:
            continue
        s = out[p]
        if s[i["start"]:i["end"]] == i.get("found"):
            out[p] = s[: i["start"]] + i["fix"] + s[i["end"]:]
    return out


# ---------------------------------------------------------------------------------------------------- tipografia (opcional, por pedido)
def typography(s: str, lang: Any = None) -> str:
    """Aspas curvas conforme o idioma, travessão de fala, reticências e travessões. Não mexe em palavras."""
    base = lang_base(norm_lang(lang))
    s = s.replace("...", "…")
    s = re.sub(r"(?<=\w)\s--\s(?=\w)", " — ", s)
    if base in ("pt", "es"):
        s = re.sub(r"(?m)^[ \t]*[-–][ \t]+(?=\S)", "— ", s)
    if base == "fr":
        op, cl, sop, scl = "« ", " »", "‹", "›"
    elif base == "de":
        op, cl, sop, scl = "„", "“", "‚", "‘"
    else:
        op, cl, sop, scl = "“", "”", "‘", "’"
    s = re.sub(r'(^|[\s(\[—–])"(?=\S)', lambda m: m.group(1) + op, s)
    s = s.replace('"', cl)
    s = re.sub(r"(^|[\s(\[—–])'(?=\w)", lambda m: m.group(1) + sop, s)
    s = re.sub(r"(?<=\w)'(?=\w)", "’", s)
    s = s.replace("'", scl)
    return s


def normalize_spacing(s: str, lang: Any = None) -> str:
    """Limpeza que nunca muda palavras: espaços duplicados, espaço antes de pontuação (menos em francês), espaços no fim da linha."""
    s = re.sub(r"(?<=\S)[ \t]{2,}(?=\S)", " ", s)
    if lang_base(norm_lang(lang)) != "fr":
        s = re.sub(r"(?<=\S)[ \t]+([,.;:!?])", r"\1", s)
    s = re.sub(r"[ \t]+$", "", s, flags=re.M)
    return s
