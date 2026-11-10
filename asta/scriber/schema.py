"""Scriber — catálogo único: tipos de escrita, idiomas, formatação (páginas, fonte, margens…) e a conta de páginas × palavras.

A tela monta os seletores a partir de `catalog()`, então um tipo novo nasce aqui (e em `web/js/en.js` para a tradução do nome)."""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

from ..util import clamp, text

# ---------------------------------------------------------------------------------------------------- tipos de escrita
# label/hint em português (chave de tradução da tela); `guide` é o que o agente lê (inglês, porque os modelos seguem melhor);
# `sections` é o esqueleto padrão (pt, en) usado pelo Planejador e pelo método automático; `preset` é a formatação padrão; `wpp` as palavras por página padrão.
WRITING_TYPES: Dict[str, Dict[str, Any]] = {
    "romance": {"label": "Romance", "group": "fiction", "preset": "book", "wpp": 300, "pages": 40, "unit": "chapter", "mature": True, "cite": False,
                "hint": "Romance e ficção longa em capítulos, SFW ou NSFW (adulto), com personagens, cenas e diálogos.",
                "guide": "Write long-form fiction (a novel) in chapters. Show, don't tell: scenes, sensory detail, subtext, natural dialogue, a distinct voice per character, rising stakes and a satisfying arc. "
                         "Keep names, timeline, places and tone consistent across chapters. Dialogue goes on its own paragraph. Never summarize a scene that should be played out.",
                "sections": {"pt": ["Capítulo {n}"], "en": ["Chapter {n}"]}, "words_per_section": 2800},
    "fiction": {"label": "Conto / ficção curta", "group": "fiction", "preset": "manuscript", "wpp": 300, "pages": 8, "unit": "section", "mature": True, "cite": False,
                "hint": "Contos, crônicas, fanfics e histórias curtas.",
                "guide": "Write a short story: a tight arc, a strong opening line, economy, one clear emotional turn and an ending that lands. Natural dialogue on its own paragraphs.",
                "sections": {"pt": ["Abertura", "Desenvolvimento", "Virada", "Desfecho"], "en": ["Opening", "Development", "Turn", "Ending"]}, "words_per_section": 900},
    "memoir": {"label": "Biografia / memórias", "group": "fiction", "preset": "book", "wpp": 300, "pages": 30, "unit": "chapter", "mature": False, "cite": True,
               "hint": "Biografias, memórias e relatos de vida (fatos só dos que você fornecer).",
               "guide": "Write a biography or memoir in a warm, vivid narrative voice. Use ONLY facts, dates and quotes present in the user's material or sources; where something is unknown, write around it or mark [verificar]. Never invent events about real people.",
               "sections": {"pt": ["Origens", "Formação", "Viradas", "Legado"], "en": ["Origins", "Formation", "Turning points", "Legacy"]}, "words_per_section": 2200},
    "journalism": {"label": "Jornalismo", "group": "professional", "preset": "article", "wpp": 450, "pages": 3, "unit": "section", "mature": False, "cite": True,
                   "hint": "Reportagem, notícia, entrevista e coluna: título, lide, fontes e fatos.",
                   "guide": "Write journalism: a precise headline, a lead answering who/what/when/where/why/how, the inverted pyramid, short paragraphs, attributed claims, neutral tone (unless it is a column). "
                            "NEVER invent quotes, sources, numbers or names: use only what the user or the web sources provide; mark gaps as [apurar]. Separate fact from opinion.",
                   "sections": {"pt": ["Lide", "Contexto", "Desdobramentos", "Fontes e vozes", "Encerramento"], "en": ["Lead", "Context", "Developments", "Sources and voices", "Close"]}, "words_per_section": 350},
    "analysis": {"label": "Análises", "group": "professional", "preset": "report", "wpp": 450, "pages": 6, "unit": "section", "mature": False, "cite": True,
                 "hint": "Análises de mercado, de obras, de dados, de cenário ou de desempenho.",
                 "guide": "Write an analysis: state the question, the evidence, the reasoning, the counter-arguments, the limits and a clear conclusion with recommendations. Quantify when data exists; never invent data or sources.",
                 "sections": {"pt": ["Resumo executivo", "Contexto", "Análise", "Riscos e limites", "Conclusão e recomendações"], "en": ["Executive summary", "Context", "Analysis", "Risks and limits", "Conclusion and recommendations"]}, "words_per_section": 600},
    "copywriting": {"label": "Copywriting", "group": "professional", "preset": "copy", "wpp": 250, "pages": 2, "unit": "section", "mature": False, "cite": False,
                    "hint": "Anúncios, páginas de venda, e-mails, roteiros de vendas e slogans.",
                    "guide": "Write persuasive copy: a hook headline, the audience's pain and desire, benefits before features, proof, objection handling and one clear call to action. Short sentences, concrete words, "
                             "AIDA/PAS where it fits. Offer headline variants when asked. Do not invent testimonials, statistics or guarantees.",
                    "sections": {"pt": ["Título", "Gancho", "Benefícios", "Prova", "Chamada para ação"], "en": ["Headline", "Hook", "Benefits", "Proof", "Call to action"]}, "words_per_section": 180},
    "academic": {"label": "Livro / trabalho acadêmico", "group": "academic", "preset": "academic", "wpp": 400, "pages": 20, "unit": "chapter", "mature": False, "cite": True,
                 "hint": "Livros didáticos, monografias, TCCs e artigos acadêmicos com referências.",
                 "guide": "Write academic prose: formal register, a clear thesis, argued structure, defined terms, hedged claims, and in-text citations ONLY for sources the user or the web search provided. "
                         "NEVER fabricate references, authors, DOIs, page numbers or quotations: when a citation would be needed and none is available write [citação necessária]. End with a References section listing only real, provided sources.",
                 "sections": {"pt": ["Resumo", "Introdução", "Referencial teórico", "Metodologia", "Desenvolvimento", "Considerações finais", "Referências"], "en": ["Abstract", "Introduction", "Theoretical framework", "Method", "Development", "Final remarks", "References"]}, "words_per_section": 1500},
    "scientific": {"label": "Pesquisa científica", "group": "academic", "preset": "academic", "wpp": 450, "pages": 12, "unit": "section", "mature": False, "cite": True,
                   "hint": "Artigos e relatórios científicos (resumo, métodos, resultados, discussão, referências).",
                   "guide": "Write a scientific paper (IMRaD): precise, passive/impersonal where the field expects it, every claim backed by the user's data or provided sources. NEVER invent data, results, p-values, "
                            "sample sizes, references or DOIs: if the user gave no results, write the Results section as a clearly marked template with [dados do autor]. Report limitations honestly.",
                   "sections": {"pt": ["Resumo", "Introdução", "Métodos", "Resultados", "Discussão", "Conclusão", "Referências"], "en": ["Abstract", "Introduction", "Methods", "Results", "Discussion", "Conclusion", "References"]}, "words_per_section": 900},
    "essay": {"label": "Ensaio / artigo de opinião", "group": "professional", "preset": "article", "wpp": 400, "pages": 4, "unit": "section", "mature": False, "cite": False,
              "hint": "Ensaios, colunas e artigos de opinião com tese e argumentos.",
              "guide": "Write an essay with a personal, argued voice: a sharp thesis, escalating arguments with concrete examples, a fair treatment of the best counter-argument and a resonant ending.",
              "sections": {"pt": ["Tese", "Argumento 1", "Argumento 2", "Contraponto", "Conclusão"], "en": ["Thesis", "Argument 1", "Argument 2", "Counterpoint", "Conclusion"]}, "words_per_section": 500},
    "blog": {"label": "Blog / artigo web", "group": "professional", "preset": "article", "wpp": 400, "pages": 3, "unit": "section", "mature": False, "cite": False,
             "hint": "Posts, guias e artigos para a web, com subtítulos escaneáveis.",
             "guide": "Write a web article: a clear promise in the title and intro, scannable subheadings, short paragraphs, concrete examples and a useful takeaway. Conversational but precise.",
             "sections": {"pt": ["Introdução", "Ponto 1", "Ponto 2", "Ponto 3", "Conclusão"], "en": ["Introduction", "Point 1", "Point 2", "Point 3", "Conclusion"]}, "words_per_section": 400},
    "technical": {"label": "Documentação técnica / manual", "group": "professional", "preset": "report", "wpp": 400, "pages": 10, "unit": "section", "mature": False, "cite": False,
                  "hint": "Manuais, tutoriais, relatórios técnicos e documentação.",
                  "guide": "Write technical documentation: task-oriented, exact, numbered steps, prerequisites, expected results, warnings and examples. One idea per paragraph; consistent terms; no marketing language.",
                  "sections": {"pt": ["Visão geral", "Requisitos", "Passo a passo", "Solução de problemas", "Referência"], "en": ["Overview", "Requirements", "Step by step", "Troubleshooting", "Reference"]}, "words_per_section": 500},
    "business": {"label": "Relatório / plano de negócios", "group": "professional", "preset": "report", "wpp": 450, "pages": 8, "unit": "section", "mature": False, "cite": False,
                 "hint": "Relatórios, propostas, planos de negócio e apresentações em texto.",
                 "guide": "Write a business document: decision-oriented, executive summary first, clear sections, numbers labelled as assumptions unless provided, actions with owners and dates left as [definir] when unknown.",
                 "sections": {"pt": ["Sumário executivo", "Problema e oportunidade", "Solução", "Mercado", "Plano de ação", "Finanças", "Riscos"], "en": ["Executive summary", "Problem and opportunity", "Solution", "Market", "Action plan", "Finance", "Risks"]}, "words_per_section": 500},
    "script": {"label": "Roteiro (cinema, TV, vídeo)", "group": "fiction", "preset": "manuscript", "wpp": 220, "pages": 12, "unit": "section", "mature": True, "cite": False,
               "hint": "Roteiros com cenas, ações e falas.",
               "guide": "Write a screenplay in plain text: scene headings (INT./EXT. — place — time) in capitals, action lines in the present tense, character names in capitals above their lines. Visual, economical, no camera directions unless essential.",
               "sections": {"pt": ["Ato 1", "Ato 2", "Ato 3"], "en": ["Act 1", "Act 2", "Act 3"]}, "words_per_section": 900},
    "speech": {"label": "Discurso / apresentação", "group": "professional", "preset": "article", "wpp": 130, "pages": 3, "unit": "section", "mature": False, "cite": False,
               "hint": "Discursos, palestras e falas para falar em voz alta.",
               "guide": "Write for the ear: short sentences, rhythm, repetition, signposting, a memorable opening and close, pauses marked with line breaks. About 130 words per spoken minute.",
               "sections": {"pt": ["Abertura", "Mensagem central", "Histórias e exemplos", "Fechamento"], "en": ["Opening", "Core message", "Stories and examples", "Close"]}, "words_per_section": 350},
    "poetry": {"label": "Poesia / letras", "group": "fiction", "preset": "book", "wpp": 120, "pages": 6, "unit": "section", "mature": True, "cite": False,
               "hint": "Poemas, letras de música e prosa poética.",
               "guide": "Write poetry: precise images, fresh metaphors, deliberate line breaks, sound and rhythm; avoid clichés. Respect any form requested (sonnet, haiku, rhymed verse). Each line is its own line.",
               "sections": {"pt": ["Poema {n}"], "en": ["Poem {n}"]}, "words_per_section": 120},
    "custom": {"label": "Outro (livre)", "group": "professional", "preset": "article", "wpp": 350, "pages": 5, "unit": "section", "mature": True, "cite": False,
               "hint": "Qualquer outro texto: descreva o que quer e a IA escolhe a estrutura.",
               "guide": "Write exactly the kind of text the user describes, choosing the structure and register that fit it best.",
               "sections": {"pt": ["Introdução", "Desenvolvimento", "Conclusão"], "en": ["Introduction", "Development", "Conclusion"]}, "words_per_section": 500},
}
DEFAULT_TYPE = "romance"
GROUPS = ("fiction", "professional", "academic")

# ---------------------------------------------------------------------------------------------------- idiomas
# code → (nome em português, nome em inglês para os prompts, código do Word `w:lang`, `lang` do HTML)
LANGUAGES: Dict[str, Dict[str, str]] = {
    "pt-BR": {"label": "Português (Brasil)", "english": "Brazilian Portuguese", "dict": "pt_BR"},
    "pt-PT": {"label": "Português (Portugal)", "english": "European Portuguese", "dict": "pt_PT"},
    "en-US": {"label": "Inglês (EUA)", "english": "American English", "dict": "en_US"},
    "en-GB": {"label": "Inglês (Reino Unido)", "english": "British English", "dict": "en_GB"},
    "es-ES": {"label": "Espanhol", "english": "Spanish", "dict": "es_ES"},
    "fr-FR": {"label": "Francês", "english": "French", "dict": "fr_FR"},
    "de-DE": {"label": "Alemão", "english": "German", "dict": "de_DE"},
    "it-IT": {"label": "Italiano", "english": "Italian", "dict": "it_IT"},
    "nl-NL": {"label": "Holandês", "english": "Dutch", "dict": "nl_NL"},
    "pl-PL": {"label": "Polonês", "english": "Polish", "dict": "pl_PL"},
    "ru-RU": {"label": "Russo", "english": "Russian", "dict": "ru_RU"},
    "tr-TR": {"label": "Turco", "english": "Turkish", "dict": "tr_TR"},
    "sv-SE": {"label": "Sueco", "english": "Swedish", "dict": "sv_SE"},
}
DEFAULT_LANG = "pt-BR"
_LANG_ALIASES = {"pt": "pt-BR", "en": "en-US", "es": "es-ES", "fr": "fr-FR", "de": "de-DE", "it": "it-IT", "nl": "nl-NL", "pl": "pl-PL", "ru": "ru-RU", "tr": "tr-TR", "sv": "sv-SE", "pt_br": "pt-BR", "en_us": "en-US"}


def norm_lang(value: Any, default: str = DEFAULT_LANG) -> str:
    if not isinstance(value, str):
        return default
    v = value.strip().replace("_", "-")
    if v in LANGUAGES:
        return v
    low = v.lower()
    for code in LANGUAGES:
        if code.lower() == low:
            return code
    return _LANG_ALIASES.get(low, _LANG_ALIASES.get(low.split("-")[0], default))


def lang_name(code: str) -> str:
    return LANGUAGES[norm_lang(code)]["english"]


def lang_base(code: str) -> str:
    return norm_lang(code).split("-")[0]


# ---------------------------------------------------------------------------------------------------- formatação
FONTS = ("Times New Roman", "Georgia", "Garamond", "Cambria", "Palatino Linotype", "Book Antiqua", "Calibri", "Arial", "Verdana", "Helvetica", "Courier New", "Trebuchet MS", "Tahoma", "Segoe UI")
PAGES = {"A4": (21.0, 29.7), "A5": (14.8, 21.0), "Letter": (21.59, 27.94), "Legal": (21.59, 35.56)}   # cm
ALIGNS = ("left", "justify", "center", "right")
PRESETS: Dict[str, Dict[str, Any]] = {
    "book": {"label": "Livro", "font": "Georgia", "size": 11.0, "line": 1.4, "indent": 1.0, "align": "justify", "space_after": 0.0, "page": "A5", "margins": [2.0, 2.0, 2.2, 2.0], "chapter_break": True, "title_page": True, "toc": False, "page_numbers": True},
    "manuscript": {"label": "Manuscrito", "font": "Times New Roman", "size": 12.0, "line": 2.0, "indent": 1.25, "align": "left", "space_after": 0.0, "page": "A4", "margins": [2.5, 2.5, 2.5, 2.5], "chapter_break": True, "title_page": True, "toc": False, "page_numbers": True},
    "article": {"label": "Artigo", "font": "Calibri", "size": 11.0, "line": 1.15, "indent": 0.0, "align": "left", "space_after": 8.0, "page": "A4", "margins": [2.5, 2.5, 2.5, 2.5], "chapter_break": False, "title_page": False, "toc": False, "page_numbers": True},
    "report": {"label": "Relatório", "font": "Calibri", "size": 11.0, "line": 1.15, "indent": 0.0, "align": "left", "space_after": 8.0, "page": "A4", "margins": [2.5, 2.5, 2.5, 2.5], "chapter_break": False, "title_page": True, "toc": True, "page_numbers": True},
    "academic": {"label": "Acadêmico (ABNT/APA)", "font": "Times New Roman", "size": 12.0, "line": 1.5, "indent": 1.25, "align": "justify", "space_after": 0.0, "page": "A4", "margins": [3.0, 2.0, 3.0, 2.0], "chapter_break": True, "title_page": True, "toc": True, "page_numbers": True},
    "copy": {"label": "Copy", "font": "Arial", "size": 11.0, "line": 1.15, "indent": 0.0, "align": "left", "space_after": 10.0, "page": "A4", "margins": [2.5, 2.5, 2.5, 2.5], "chapter_break": False, "title_page": False, "toc": False, "page_numbers": False},
}
# margens: [topo, base, esquerda, direita] em cm


def _num(v: Any, d: float, lo: float, hi: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return d
    if f != f or f in (math.inf, -math.inf):
        return d
    return clamp(f, lo, hi)


def norm_format(raw: Any, preset: Optional[str] = None) -> Dict[str, Any]:
    """Formatação do documento, sempre válida (a IA e a API mandam qualquer coisa). `preset` fornece o ponto de partida; o que vier em `raw` vence."""
    r = raw if isinstance(raw, dict) else {}
    pid = r.get("preset") if isinstance(r.get("preset"), str) and r.get("preset") in PRESETS else (preset if preset in PRESETS else "article")
    base = PRESETS[pid]
    m = r.get("margins") if isinstance(r.get("margins"), (list, tuple)) and len(r.get("margins")) == 4 else base["margins"]
    return {
        "preset": pid,
        "font": r.get("font") if isinstance(r.get("font"), str) and r.get("font") in FONTS else base["font"],
        "size": round(_num(r.get("size"), base["size"], 8, 24) * 2) / 2,
        "line": round(_num(r.get("line"), base["line"], 1.0, 3.0), 2),
        "indent": round(_num(r.get("indent"), base["indent"], 0.0, 3.0), 2),
        "align": r.get("align") if isinstance(r.get("align"), str) and r.get("align") in ALIGNS else base["align"],
        "space_after": round(_num(r.get("space_after"), base["space_after"], 0, 36), 1),
        "page": r.get("page") if isinstance(r.get("page"), str) and r.get("page") in PAGES else base["page"],
        "margins": [round(_num(x, base["margins"][i], 1.0, 6.0), 2) for i, x in enumerate(m)],
        "chapter_break": bool(r.get("chapter_break")) if "chapter_break" in r else base["chapter_break"],
        "title_page": bool(r.get("title_page")) if "title_page" in r else base["title_page"],
        "toc": bool(r.get("toc")) if "toc" in r else base["toc"],
        "page_numbers": bool(r.get("page_numbers")) if "page_numbers" in r else base["page_numbers"],
        "header": text(r.get("header"), "", 120),
        "author": text(r.get("author"), "", 80),
        "subtitle": text(r.get("subtitle"), "", 160),
    }


# ---------------------------------------------------------------------------------------------------- páginas × palavras
MAX_PAGES = 1000
MAX_WORDS_PER_PAGE = 1000
MAX_TARGET_WORDS = 400_000


def norm_size(pages: Any, wpp: Any, type_id: str = DEFAULT_TYPE) -> Dict[str, int]:
    """Quantidade de páginas e de palavras por página → meta de palavras (limitada: uma geração muito longa precisa de muitas chamadas à IA)."""
    t = WRITING_TYPES.get(type_id) or WRITING_TYPES[DEFAULT_TYPE]
    p = int(_num(pages, t["pages"], 1, MAX_PAGES))
    w = int(_num(wpp, t["wpp"], 50, MAX_WORDS_PER_PAGE))
    if p * w > MAX_TARGET_WORDS:
        p = max(1, MAX_TARGET_WORDS // w)
    return {"pages": p, "words_per_page": w, "target_words": p * w}


def pages_for(words: int, wpp: int) -> float:
    return round(words / max(1, wpp), 1)


def auto_sections(type_id: str, target_words: int, lang: str) -> List[Dict[str, Any]]:
    """Esqueleto padrão de um tipo para uma meta de palavras: seções do tipo (ou capítulos numerados) com palavras repartidas. Usado sem IA e como base do Planejador."""
    t = WRITING_TYPES.get(type_id) or WRITING_TYPES[DEFAULT_TYPE]
    base = lang_base(lang)
    names = list(t["sections"].get(base) or t["sections"]["en"])
    target = max(40, int(target_words))
    if len(names) == 1 or "{n}" in names[0]:   # capítulos / poemas numerados: o número depende do tamanho
        per = t["words_per_section"]
        n = int(clamp(round(target / per), 1, 60)) if t["unit"] == "chapter" or "{n}" in names[0] else 1
        tpl = names[0]
        names = [tpl.replace("{n}", str(i + 1)) for i in range(n)]
    elif target < 120 * len(names):   # meta curta: menos seções
        keep = max(1, target // 120)
        names = names[:keep]
    each = max(40, target // len(names))
    out = [{"title": n, "summary": "", "words": each} for n in names]
    out[-1]["words"] = max(40, target - each * (len(out) - 1))
    return out


def catalog() -> Dict[str, Any]:
    return {
        "types": {k: {"label": v["label"], "group": v["group"], "hint": v["hint"], "preset": v["preset"], "wpp": v["wpp"], "pages": v["pages"], "mature": v["mature"], "cite": v["cite"], "unit": v["unit"]} for k, v in WRITING_TYPES.items()},
        "groups": list(GROUPS), "languages": {k: v["label"] for k, v in LANGUAGES.items()},
        "fonts": list(FONTS), "pages": {k: list(v) for k, v in PAGES.items()}, "aligns": list(ALIGNS),
        "presets": {k: dict(v) for k, v in PRESETS.items()},
        "limits": {"max_pages": MAX_PAGES, "max_words_per_page": MAX_WORDS_PER_PAGE, "max_target_words": MAX_TARGET_WORDS},
        "actions": [a for a, _ in ACTIONS],
    }


# ações de edição sobre um trecho selecionado (rótulo em português na tela)
ACTIONS = (("improve", "Melhorar"), ("expand", "Expandir"), ("rewrite", "Reescrever"), ("shorten", "Encurtar"), ("fix", "Corrigir"), ("continue", "Continuar"),
           ("dialogue", "Virar diálogo"), ("describe", "Descrever mais"), ("tone", "Mudar o tom"), ("translate", "Traduzir"), ("custom", "Pedir…"))
ACTION_IDS = tuple(a for a, _ in ACTIONS)
SELECTION_KINDS = ("paragraph", "dialogue", "mixed")


def norm_expand(raw: Any) -> Dict[str, Any]:
    """Tamanho da expansão: `mode` = «add» (acrescentar N palavras) ou «total» (o resultado deve ter ~N palavras); `words` 10 … 3000."""
    r = raw if isinstance(raw, dict) else {}
    return {"mode": r.get("mode") if r.get("mode") in ("add", "total") else "add", "words": int(_num(r.get("words"), 120, 10, 3000))}


_WORD = re.compile(r"[^\W_][\w'’\-]*", re.U)


def count_words(s: str) -> int:
    return len(_WORD.findall(s or ""))
