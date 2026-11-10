"""A IA do Scriber: equipes pequenas de agentes (planejar → escrever → conferir → empacotar), todas com **fallback determinístico** — o Scriber entrega mesmo sem IA ou com resposta inválida.

  • `generate`      (Geração automática) — Planejador → Redator (uma ou mais chamadas por seção, com a continuidade da história) → Revisor → Empacotador (documento + .docx).
  • `edit_text`     (Edição)             — Editor: melhorar / expandir / reescrever / encurtar / corrigir / continuar / diálogo / descrever / tom / traduzir um trecho selecionado, com o tamanho escolhido.
  • `proofread_ai`  (Edição)             — Revisor ortográfico: erros reais com o trecho exato e o motivo (por cima das regras e do dicionário do sistema: `spell.py`).

A IA escreve **texto e dados validados**; nada que ela devolva é executado. Quantos agentes (1·4·8·12·16·20·24·28·32) e o esforço (Low…Omni) vêm de `asta/team.py`, como em todas as seções.
Os lorebooks (`lore.py`) entram em cada chamada como bloco de contexto/regras, e a busca na web (`websearch.py`) e os anexos (`attachments.py`) são opcionais."""
from __future__ import annotations

import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import team as teamlib
from ..agents.llm import call_json
from ..agents.prompts import POLICY_FREE, POLICY_SFW
from ..agents.runner import Cancelled
from ..providers import ProviderError, resolve_provider
from ..util import clamp, text
from . import docmodel as D, lore as L, schema as S, spell
from .manager import ScriberError

PROMPTS = Path(__file__).parent / "prompts"
PART_WORDS = 1100        # palavras por chamada de escrita (partes maiores são escritas em várias chamadas, sempre continuando da anterior)
MAX_PARTS = 400
POLICY_FIXED = " Never write sexual content about real, identifiable people."


@lru_cache(maxsize=32)
def prompt(name: str) -> str:
    try:
        return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def prompt_names() -> List[str]:
    return sorted(p.stem for p in PROMPTS.glob("*.md"))


def normalize_config(raw: Any) -> Dict[str, Any]:
    c = raw if isinstance(raw, dict) else {}
    t = c.get("type") if isinstance(c.get("type"), str) and c.get("type") in S.WRITING_TYPES else S.DEFAULT_TYPE
    size = S.norm_size(c.get("pages"), c.get("words_per_page"), t)
    return {"agents": teamlib.normalize_agents(c.get("agents", 1)), "effort": teamlib.normalize_effort(c.get("effort", "high")), "type": t, "language": S.norm_lang(c.get("language")),
            "content": "sfw" if c.get("content") == "sfw" else ("free" if c.get("content") == "free" else ""), "web": c.get("web") is True,
            "pages": size["pages"], "words_per_page": size["words_per_page"], "undo_keep": int(clamp(float(c.get("undo_keep") or 25), 5, 100)) if isinstance(c.get("undo_keep"), (int, float)) else 25,
            "expand_words": int(clamp(float(c.get("expand_words") or 150), 10, 3000)) if isinstance(c.get("expand_words"), (int, float)) else 150,
            "dialogue_words": int(clamp(float(c.get("dialogue_words") or 60), 10, 3000)) if isinstance(c.get("dialogue_words"), (int, float)) else 60,
            "spellcheck": c.get("spellcheck") is not False, "autosave": c.get("autosave") is not False}


def _unpack(res: Any) -> Any:
    if isinstance(res, tuple) and len(res) == 2:
        return res
    return res, {"demo": getattr(res, "id", "") == "demo", "id": getattr(res, "id", ""), "model": getattr(res, "model", "")}


def scriber_status(store: Any) -> Dict[str, Any]:
    """O que a tela precisa saber: IA de texto pronta?, dicionário do sistema (hunspell/aspell) por idioma, equipe padrão."""
    settings = store.get_settings()
    out: Dict[str, Any] = {"config": normalize_config(settings.get("scriber")), "text": {"ai": False, "label": "Demo"}, "dictionaries": {}}
    try:
        provider, info = _unpack(resolve_provider(settings, "generation", store.models_dir))
        out["text"] = {"ai": not (info.get("demo") or getattr(provider, "id", "") == "demo"), "label": info.get("label") or info.get("id") or "", "model": info.get("model", "")}
    except Exception as exc:  # noqa: BLE001
        out["text"] = {"ai": False, "label": "", "error": str(exc)[:160]}
    for lang in S.LANGUAGES:
        out["dictionaries"][lang] = spell.dictionary_available(lang)
    return out


# ---------------------------------------------------------------------------------------------------- esboço (outline) escrito pelo autor
def parse_outline(raw: str) -> List[Dict[str, Any]]:
    """Esboço em texto (títulos «#», «Capítulo 1: …», «1. …» ou marcadores «-») → seções `{title, summary, words: 0}`. Vazio se não parece um esboço (menos de 2 itens)."""
    lines = [ln.rstrip() for ln in str(raw or "").replace("\r\n", "\n").split("\n")]
    secs: List[Dict[str, Any]] = []

    def mk(title: str) -> Dict[str, Any]:
        s = {"title": re.sub(r"\s+", " ", title).strip(" :-–—*_#")[:120], "points": []}
        secs.append(s)
        return s

    heads = [i for i, ln in enumerate(lines) if re.match(r"^\s{0,3}#{1,3}\s+\S", ln)]
    chap = [i for i, ln in enumerate(lines) if re.match(r"^\s*(?:cap[ií]tulo|chapter|parte|part|ato|act|se[cç][aã]o|section)\s+[\dIVXLC]+\b", ln, re.I)]
    nums = [i for i, ln in enumerate(lines) if re.match(r"^\d{1,3}[.)]\s+\S", ln)]
    bullets = [i for i, ln in enumerate(lines) if re.match(r"^\s*[-*•]\s+\S", ln)]
    if heads:
        mode = "head"
    elif len(chap) >= 2:
        mode = "chap"
    elif len(nums) >= 2:
        mode = "num"
    elif len(bullets) >= 2:
        mode = "bullet"
    else:
        return []
    cur: Optional[Dict[str, Any]] = None
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        if mode == "head":
            m = re.match(r"^\s{0,3}#{1,3}\s+(.*)$", ln)
            if m:
                cur = mk(m.group(1))
                continue
        elif mode == "chap" and i in chap:
            cur = mk(ln)
            continue
        elif mode == "num" and i in nums and not ln.startswith((" ", "\t")):
            cur = mk(re.sub(r"^\d{1,3}[.)]\s+", "", ln))
            continue
        elif mode == "bullet" and i in bullets and not ln.startswith((" ", "\t")):
            cur = mk(re.sub(r"^\s*[-*•]\s+", "", ln))
            continue
        if cur is not None:
            cur["points"].append(re.sub(r"^\s*(?:[-*•]|\d{1,3}[.)])\s+", "", ln).strip())
    out = [{"title": s["title"], "summary": " ".join(s["points"])[:600], "words": 0} for s in secs if s["title"]]
    return out if len(out) >= 2 else []


def _title_guess(prompt_text: str, type_id: str, lang: str) -> str:
    m = re.search(r"[\"“”«»']([^\"“”«»']{3,70})[\"“”«»']", prompt_text or "")
    if m:
        return m.group(1).strip()
    first = next((ln.strip(" #*-") for ln in (prompt_text or "").split("\n") if ln.strip()), "")
    if 3 <= len(first) <= 70 and not first.endswith((".", "?", "!")) and len(first.split()) <= 9:
        return first
    return S.WRITING_TYPES[type_id]["label"]


def _alloc(sections: List[Dict[str, Any]], target: int) -> List[Dict[str, Any]]:
    """Reparte a meta de palavras entre as seções (proporcional ao que já tinham; as sem valor recebem a média); a soma bate com a meta."""
    n = len(sections)
    ws = [max(0, int(s.get("words") or 0)) for s in sections]
    known = [w for w in ws if w > 0]
    avg = (sum(known) / len(known)) if known else target / max(1, n)
    ws = [w if w > 0 else avg for w in ws]
    total = sum(ws) or 1
    scaled = [max(40, int(round(w * target / total))) for w in ws]
    scaled[-1] = max(40, target - sum(scaled[:-1])) if n > 1 else max(40, target)
    for s, w in zip(sections, scaled):
        s["words"] = w
    return sections


def estimate(opts: Dict[str, Any]) -> Dict[str, Any]:
    """Quantas seções, partes e chamadas à IA uma geração deve custar (para a tela mostrar antes de começar)."""
    type_id = opts.get("type") if opts.get("type") in S.WRITING_TYPES else S.DEFAULT_TYPE
    size = S.norm_size(opts.get("pages"), opts.get("words_per_page"), type_id)
    lang = S.norm_lang(opts.get("language"))
    outline = parse_outline(opts.get("prompt") or "")
    n_chap = int(clamp(float(opts.get("chapters") or 0), 0, 60)) if isinstance(opts.get("chapters"), (int, float)) else 0
    secs = outline or S.auto_sections(type_id, size["target_words"], lang)
    if n_chap and not outline:
        secs = S.auto_sections(type_id, size["target_words"], lang)
        per = max(1, size["target_words"] // n_chap)
        secs = [{"title": "", "words": per} for _ in range(n_chap)]
    secs = _alloc([dict(s) for s in secs], size["target_words"])
    parts = sum(max(1, -(-s["words"] // PART_WORDS)) for s in secs)
    team = teamlib.from_config({"agents": opts.get("agents"), "effort": opts.get("effort")}, {})
    per = teamlib.calls_per_step(team.agents)
    return {"sections": len(secs), "parts": parts, "target_words": size["target_words"], "pages": size["pages"], "words_per_page": size["words_per_page"], "calls": per * (parts + 1) + 1, "agents": team.agents, "from_outline": bool(outline)}


# ---------------------------------------------------------------------------------------------------- execução
class ScriberAI:
    """Uma execução da IA do Scriber: guarda o provedor, a equipe e o registro (log) de cada agente; emite eventos para a tela."""

    def __init__(self, store: Any, mgr: Any, opts: Dict[str, Any], job: Any):
        self.store, self.mgr, self.opts, self.job = store, mgr, opts or {}, job
        settings = store.get_settings()
        self.settings = settings
        self.cfg = normalize_config(settings.get("scriber"))
        self.team = teamlib.from_config(self.cfg, self.opts)
        self.content = self.opts.get("content") or self.cfg["content"] or (settings.get("generation") or {}).get("content", "free")
        self.provider: Any = None
        self.error = ""
        self.pinfo: Dict[str, Any] = {}
        try:
            provider, info = _unpack(resolve_provider(settings, "generation", store.models_dir))
            self.pinfo = info
            if info.get("demo") or getattr(provider, "id", "") == "demo":
                self.error = info.get("reason") or "Nenhuma IA configurada: usei as regras automáticas do Scriber."
            else:
                self.provider = provider
                teamlib.apply_thinking(provider, self.team, info.get("id", ""), info.get("model", ""))
        except (ProviderError, Exception) as exc:  # noqa: BLE001
            self.error = str(exc)[:200]
        self.log: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        self.sources: List[Dict[str, Any]] = []

    @property
    def live(self) -> bool:
        return self.provider is not None

    def emit(self, ev: Dict[str, Any]) -> None:
        if self.job is not None:
            self.job.emit(ev)

    def check(self) -> None:
        if self.job is not None and self.job.cancelled:
            raise Cancelled()

    def note(self, msg: str) -> None:
        self.emit({"type": "note", "message": msg})

    def start(self, steps: List[Tuple[str, str]]) -> None:
        self.emit({"type": "start", "steps": [{"id": a, "label": b} for a, b in steps], "ai": self.live, "team": self.team.public(),
                   "warning": "" if self.live else (self.error or "Sem IA: usei as regras automáticas do Scriber.")})

    def policy(self) -> str:
        return (POLICY_SFW if self.content == "sfw" else POLICY_FREE) + POLICY_FIXED

    # ---------------------------------------------------------------- uma chamada de agente
    def _ask(self, role: str, instruction: str, payload: Dict[str, Any], tokens: int, images: Optional[List[dict]] = None) -> Optional[Dict[str, Any]]:
        system = f"ROLE: {role.title()}\n\n" + prompt("core") + "\n\n" + prompt(role) + "\n\n" + self.policy()
        obj, _ = call_json(self.provider, system, instruction + "\nOutput JSON: see the format in your role description.", payload, images=images, max_tokens=int(tokens * self.team.tokens_mult), temperature=0.7 if role in ("writer", "editor") else 0.4,
                           attempts=2, cancelled=lambda: bool(self.job is not None and self.job.cancelled))
        return obj

    def step(self, sid: str, role: str, label: str, payload: Dict[str, Any], validate: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]], fallback: Callable[[], Dict[str, Any]], *,
             creative: bool = True, critique: bool = False, tokens: int = 3000, images: Optional[List[dict]] = None, quiet: bool = False) -> Dict[str, Any]:
        """Roda um agente (ou a mesa de N agentes) e devolve o resultado **validado**; se a IA falha ou devolve lixo, vale o `fallback`."""
        self.check()
        started = time.time()
        note = ""
        out: Optional[Dict[str, Any]] = None
        if not quiet:
            self.emit({"type": "step", "id": sid, "label": label, "status": "running"})
        if self.live:
            instruction = f"Do your role for this input ({label})."
            ask = lambda ins, pl: self._ask(role, ins, pl, tokens, images)   # noqa: E731
            try:
                raw = teamlib.ensemble_json(ask, self.team, instruction, payload, cancelled=lambda: bool(self.job is not None and self.job.cancelled), fatal=(Cancelled,)) if creative and self.team.multi else ask(instruction, payload)
                if raw and critique and self.team.critique:
                    raw = teamlib.critique_json(ask, instruction, payload, raw)
                out = validate(raw) if isinstance(raw, dict) else None
                if out is None:
                    note = "resposta inválida da IA"
            except Cancelled:
                raise
            except ProviderError as exc:
                if str(exc) == "cancelado":
                    raise Cancelled() from None
                note = str(exc)[:160]
            except ValueError as exc:
                note = str(exc)[:160]
        else:
            note = self.error or "sem IA"
        status = "ok"
        if out is None:
            out = fallback()
            status = "fallback"
        self.log.append({"agent": role, "label": label, "status": status, "note": note, "ms": int((time.time() - started) * 1000)})
        if not quiet or status != "ok":
            self.emit({"type": "step", "id": sid, "label": label, "status": "done" if status == "ok" else "warn", "note": note})
        return out

    def report(self) -> Dict[str, Any]:
        return {"ai": self.live and any(s["status"] == "ok" for s in self.log), "agents": self.log[-300:], "team": self.team.public(), "warnings": self.warnings[:20],
                "warning": "" if self.live else (self.error or "Sem IA: usei as regras automáticas do Scriber.")}

    def done(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(result)
        result["report"] = self.report()
        self.emit({"type": "result", "data": result})
        return result

    # ---------------------------------------------------------------- contexto: anexos, web, lorebook
    def context(self, prompt_text: str) -> Dict[str, Any]:
        from .. import attachments as att, voice

        ids = self.opts.get("attachment_ids") or []
        digest, images = "", []
        if ids:
            self.emit({"type": "step", "id": "attachments", "label": "Anexos", "status": "running"})
            analyzed = []
            transcribe = voice.transcriber(self.settings)
            for meta in self.store.get_uploads(ids):
                self.check()
                try:
                    analyzed.append(att.analyze(Path(meta["path"]), meta["name"], meta.get("mime", ""), transcribe=transcribe))
                except Exception as exc:  # noqa: BLE001  (um anexo ilegível não derruba a geração)
                    self.warnings.append(f"anexo «{meta.get('name', '?')}»: {str(exc)[:100]}")
            digest = att.build_digest(analyzed, max_total=40000)
            images = att.collect_images(analyzed)
            self.emit({"type": "step", "id": "attachments", "label": "Anexos", "status": "done", "note": f"{len(analyzed)} arquivo(s)"})
        web = text(self.opts.get("sources_text"), "", 12000)   # fontes que a pessoa fixou no painel de pesquisa
        if self.opts.get("web") and prompt_text:
            self.emit({"type": "step", "id": "web", "label": "Busca na web", "status": "running"})
            try:
                from .. import websearch

                found = websearch.gather(websearch.heuristic_query(prompt_text) or prompt_text[:200], self.settings, ui_lang=(self.settings.get("language") or "auto"))
                web = (web + "\n\n" + found.get("text", ""))[:14000].strip()
                self.sources = websearch.public_sources(found.get("sources", []))
                self.emit({"type": "sources", "sources": self.sources})
                self.emit({"type": "step", "id": "web", "label": "Busca na web", "status": "done", "note": f"{len(found.get('sources', []))} fonte(s)"})
            except Exception as exc:  # noqa: BLE001
                self.warnings.append("busca na web: " + str(exc)[:120])
                self.emit({"type": "step", "id": "web", "label": "Busca na web", "status": "warn", "note": str(exc)[:120]})
        return {"digest": digest, "images": images, "web": web}

    def lore(self, pid: str, context_text: str) -> Dict[str, Any]:
        if self.opts.get("lore") is False:
            return {"text": "", "used": []}
        only = self.opts.get("lore_books") if isinstance(self.opts.get("lore_books"), list) else None
        try:
            return L.lore_for(self.mgr.get_books(pid), context_text, True, only)
        except ScriberError:
            return {"text": "", "used": []}

    # ================================================================ GERAÇÃO AUTOMÁTICA
    def generate(self, pid: str) -> Dict[str, Any]:
        mgr = self.mgr
        meta = mgr.meta(pid)
        o = self.opts
        prompt_text = text(o.get("prompt"), "", 20000)
        type_id = o.get("type") if o.get("type") in S.WRITING_TYPES else meta["type"]
        T = S.WRITING_TYPES[type_id]
        lang = S.norm_lang(o.get("language") or meta["language"])
        size = S.norm_size(o.get("pages"), o.get("words_per_page"), type_id)
        target = size["target_words"]
        style = text(o.get("style"), "", 600)
        n_chap = int(clamp(float(o.get("chapters") or 0), 0, 60)) if isinstance(o.get("chapters"), (int, float)) and not isinstance(o.get("chapters"), bool) else 0
        outline = parse_outline(prompt_text)
        mode = "append" if o.get("mode") == "append" else "replace"
        steps = [("plan", "Planejador"), ("write", "Redator"), ("review", "Revisor"), ("package", "Empacotador")]
        self.start(steps)
        ctx = self.context(prompt_text)
        lore_all = self.lore(pid, prompt_text + " " + style)
        fmt_in = o.get("format") if isinstance(o.get("format"), dict) else {}
        fmt = S.norm_format(fmt_in, T["preset"])
        # ---------- 1. Planejador
        payload = {"request": prompt_text[:8000], "outline_given": outline or None, "type": {"id": type_id, "label": T["label"], "guide": T["guide"], "unit": T["unit"]}, "language": S.lang_name(lang),
                   "target": {"pages": size["pages"], "words_per_page": size["words_per_page"], "words": target}, "chapters_hint": n_chap, "attachments_digest": ctx["digest"][:14000], "web_notes": ctx["web"][:6000],
                   "lorebook": lore_all["text"][:5000], "style_notes": style, "content": "sfw" if self.content == "sfw" else "adult themes allowed when requested"}
        fb = lambda: self._plan_rules(prompt_text, type_id, lang, target, outline, n_chap, meta["name"])   # noqa: E731
        plan = self.step("plan", "planner", "Planejador", payload, lambda raw: self._valid_plan(raw, prompt_text, type_id, lang, target, outline, n_chap, meta["name"]), fb, critique=True, tokens=3600 + 40 * min(60, n_chap or len(outline) or 12), images=ctx["images"] or None)
        self.emit({"type": "plan", "plan": {"title": plan["title"], "sections": [{"title": s["title"], "words": s["words"]} for s in plan["sections"]], "target_words": target, "pages": size["pages"]}})
        # ---------- 2. Redator: seção por seção, parte por parte, sempre continuando da anterior
        secs = plan["sections"]
        total_parts = sum(max(1, -(-s["words"] // PART_WORDS)) for s in secs)
        if total_parts > MAX_PARTS:
            raise ValueError(f"Esse tamanho pede {total_parts} chamadas de escrita (o limite é {MAX_PARTS}). Reduza as páginas ou as palavras por página.")
        story: str = ""
        tail: str = ""
        blocks: List[Dict[str, Any]] = []
        written: List[Dict[str, Any]] = []
        done_parts = 0
        words_total = 0
        use_heads = len(secs) > 1 or T["unit"] == "chapter"
        fiction = T["group"] == "fiction"
        for si, sec in enumerate(secs):
            self.check()
            sec_text: List[str] = []
            n_parts = max(1, -(-sec["words"] // PART_WORDS))
            per_part = max(60, sec["words"] // n_parts)
            sec_lore = self.lore(pid, f"{sec['title']} {sec['summary']} {tail[-400:]}")
            for pi in range(n_parts):
                last = pi == n_parts - 1
                sid = f"write:{si + 1}" + (f".{pi + 1}" if n_parts > 1 else "")
                label = f"Redator — {si + 1}/{len(secs)} «{sec['title'][:40]}»" + (f" ({pi + 1}/{n_parts})" if n_parts > 1 else "")
                wp = {"task": "write", "type": type_id, "language": S.lang_name(lang), "doc": {"title": plan["title"], "synopsis": plan["synopsis"], "style_guide": plan["style_guide"], "characters": plan.get("characters", [])},
                      "section": {"index": si + 1, "total": len(secs), "title": sec["title"], "summary": sec["summary"], "words": sec["words"]}, "part": {"index": pi + 1, "total": n_parts, "words": per_part, "is_last": last},
                      "story_so_far": story[-2400:], "previous_tail": (sec_text[-1] if sec_text else tail)[-900:], "next_section": ({"title": secs[si + 1]["title"], "summary": secs[si + 1]["summary"]} if si + 1 < len(secs) else None),
                      "lorebook": sec_lore["text"], "user_request": prompt_text[:3000], "attachments_digest": ctx["digest"][:6000], "web_notes": ctx["web"][:5000]}
                tok = int(clamp(per_part * 2.4 + 500, 900, 12000))
                res = self.step(sid, "writer", label, wp, lambda raw: self._valid_text(raw), lambda: self._write_rules(sec, per_part, lang, pi == 0, outline), tokens=tok, quiet=False)
                body = res["text"]
                body = self._fit_length(body, per_part, wp, tok, label)
                sec_text.append(body)
                story = (story + " " + (res.get("summary") or "")).strip()
                done_parts += 1
                words_total += S.count_words(body)
                self.emit({"type": "progress", "done": done_parts, "total": total_parts, "words": words_total, "target": target})
            joined = "\n\n".join(sec_text)
            tail = joined[-900:]
            sec_blocks = D.markdown_to_blocks(joined, lists=not fiction, shift=0)
            if use_heads and sec["title"]:
                blocks.append(D.block("h1", [D.run(sec["title"])]))
            blocks.extend(sec_blocks)
            written.append({"title": sec["title"], "words": S.count_words(joined), "target": sec["words"], "summary": sec["summary"]})
        # ---------- 3. Revisor (checagens do programa + resumo)
        blocks, problems = self._clean_blocks(blocks, written)
        stats = D.stats(blocks)
        rv = self.step("review", "reviewer", "Revisor", {"request": prompt_text[:1500], "type": type_id, "language": S.lang_name(lang), "title": plan["title"], "sections": written[:80],
                                                           "stats": {"words": stats["words"], "target_words": target, "pages": S.pages_for(stats["words"], size["words_per_page"])}, "problems": problems[:20]},
                       self._valid_review, lambda: {"approved": not problems, "summary": self._fallback_summary(plan["title"], stats, target, size["words_per_page"], problems, lang), "issues": []}, creative=False, tokens=900)
        problems += [x for x in rv.get("issues", []) if x not in problems][:6]
        # ---------- 4. Empacotador: salva (com instantâneo para desfazer), grava o .docx
        self.check()
        self.emit({"type": "step", "id": "package", "label": "Empacotador", "status": "running"})
        cur = mgr.get_doc(pid)["blocks"]
        final = (cur + [D.block("pb")] + blocks) if (mode == "append" and cur) else blocks
        if mode == "append" and cur and not fmt.get("chapter_break"):
            final = cur + blocks
        gen = {"prompt": prompt_text, "pages": size["pages"], "words_per_page": size["words_per_page"], "style": style, "chapters": n_chap}
        patch: Dict[str, Any] = {"type": type_id, "language": lang, "format": {**fmt, "subtitle": plan.get("subtitle", "") or fmt["subtitle"]}, "gen": gen}
        if o.get("content") in ("sfw", "free"):
            patch["content"] = o["content"]
        if mode == "replace" or not meta["name"] or meta["name"] in ("Novo texto", "New text"):
            patch["name"] = plan["title"]
        mgr.save_doc(pid, blocks=final, label="antes de gerar: " + prompt_text[:50])
        mgr.update_meta(pid, patch)
        exp = mgr.export(pid, "docx")
        self.emit({"type": "step", "id": "package", "label": "Empacotador", "status": "done"})
        st = D.stats(final)
        return self.done({"project": mgr.meta(pid), "summary": rv.get("summary") or self._fallback_summary(plan["title"], st, target, size["words_per_page"], problems, lang), "plan": {"title": plan["title"], "subtitle": plan.get("subtitle", ""), "sections": written},
                          "problems": problems[:12], "stats": st, "target_words": target, "pages": S.pages_for(st["words"], size["words_per_page"]), "docx": exp, "sources": self.sources, "mode": mode})

    # ---- planejamento
    def _plan_rules(self, prompt_text: str, type_id: str, lang: str, target: int, outline: List[Dict[str, Any]], n_chap: int, current_name: str) -> Dict[str, Any]:
        if outline:
            secs = [dict(s) for s in outline]
        elif n_chap:
            secs = [{"title": self._chap_name(type_id, lang, i + 1), "summary": "", "words": 0} for i in range(n_chap)]
        else:
            secs = S.auto_sections(type_id, target, lang)
        secs = _alloc(secs[:120], target)
        name = current_name if current_name and current_name not in ("Novo texto", "New text", "Sem título") else _title_guess(prompt_text, type_id, lang)
        return {"title": name, "subtitle": "", "synopsis": prompt_text.strip()[:300], "style_guide": "", "characters": [], "sections": secs}

    @staticmethod
    def _chap_name(type_id: str, lang: str, n: int) -> str:
        base = S.lang_base(lang)
        tpl = S.WRITING_TYPES[type_id]["sections"].get(base) or S.WRITING_TYPES[type_id]["sections"]["en"]
        return tpl[0].replace("{n}", str(n)) if "{n}" in tpl[0] else {"pt": f"Parte {n}", "es": f"Parte {n}", "fr": f"Partie {n}", "de": f"Teil {n}", "it": f"Parte {n}"}.get(base, f"Part {n}")

    def _valid_plan(self, raw: Dict[str, Any], prompt_text: str, type_id: str, lang: str, target: int, outline: List[Dict[str, Any]], n_chap: int, current_name: str) -> Optional[Dict[str, Any]]:
        base = self._plan_rules(prompt_text, type_id, lang, target, outline, n_chap, current_name)
        secs_raw = raw.get("sections") if isinstance(raw.get("sections"), list) else []
        secs: List[Dict[str, Any]] = []
        for s in secs_raw[:120]:
            if isinstance(s, dict) and text(s.get("title"), ""):
                try:
                    w = int(float(s.get("words") or 0))
                except (TypeError, ValueError):
                    w = 0
                secs.append({"title": text(s.get("title"), "", 120), "summary": text(s.get("summary"), "", 700), "words": w})
        if not secs:
            return None
        if outline:   # o esboço do autor manda: mesmos títulos, na mesma ordem
            fixed = []
            for i, o in enumerate(outline):
                ai = secs[i] if i < len(secs) else {}
                fixed.append({"title": o["title"], "summary": ai.get("summary") or o["summary"], "words": ai.get("words", 0)})
            secs = fixed
        elif n_chap and len(secs) != n_chap:
            secs = (secs + [{"title": self._chap_name(type_id, lang, i + 1), "summary": "", "words": 0} for i in range(len(secs), n_chap)])[:n_chap]
        chars = []
        for c in raw.get("characters") if isinstance(raw.get("characters"), list) else []:
            if isinstance(c, dict) and text(c.get("name"), ""):
                chars.append({"name": text(c.get("name"), "", 60), "note": text(c.get("note"), "", 200)})
        return {"title": text(raw.get("title"), base["title"], 120), "subtitle": text(raw.get("subtitle"), "", 160), "synopsis": text(raw.get("synopsis"), base["synopsis"], 800), "style_guide": text(raw.get("style_guide"), "", 900),
                "characters": chars[:12], "sections": _alloc(secs, target)}

    # ---- escrita
    @staticmethod
    def _valid_text(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        t = raw.get("text")
        if isinstance(t, list):
            t = "\n\n".join(str(x) for x in t)
        if not isinstance(t, str) or not t.strip():
            return None
        t = re.sub(r"^```\w*\n|\n```$", "", t.strip())
        return {"text": D.clean(t)[:200000], "summary": text(raw.get("summary"), "", 500)}

    def _fit_length(self, body: str, want: int, payload: Dict[str, Any], tokens: int, label: str) -> str:
        """Se a parte ficou bem abaixo (ou acima) do tamanho pedido, pede ao Redator estender/condensar — até 1–3 vezes conforme o esforço. Nunca inventa enchimento por conta própria."""
        if not self.live:
            return body
        passes = max(1, self.team.revisions(1))
        for _ in range(passes):
            n = S.count_words(body)
            if want * 0.8 <= n <= want * 1.35:
                break
            self.check()
            if n < want * 0.8:
                pl = dict(payload, task="extend", draft=body[-12000:] if len(body) > 12000 else body, missing_words=want - n)
                pl["part"] = dict(payload["part"], words=want)
                action = "extend"
            else:
                pl = dict(payload, task="condense", draft=body, part=dict(payload["part"], words=want))
                action = "condense"
            try:
                raw = self._ask("writer", f"Action: {action}. Return the COMPLETE improved text for this part.", pl, int(tokens * 1.15))
                new = self._valid_text(raw) if isinstance(raw, dict) else None
            except Cancelled:
                raise
            except (ProviderError, ValueError):
                new = None
            if not new:
                break
            nn = S.count_words(new["text"])
            if (action == "extend" and nn > n) or (action == "condense" and nn < n):
                body = new["text"]
            else:
                break
        return body

    def _write_rules(self, sec: Dict[str, Any], words: int, lang: str, first: bool, outline: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Sem IA: o texto do próprio autor (resumo/pontos do esboço) + um marcador claro do que falta escrever. Nada de enchimento."""
        L_ = lambda pt, en: pt if S.lang_base(lang) == "pt" else en   # noqa: E731
        parts: List[str] = []
        if sec.get("summary"):
            parts.append(sec["summary"])
        parts.append(L_(f"[Escreva aqui: «{sec['title']}» — cerca de {words} palavras. Sem IA configurada, o Scriber montou só a estrutura e o que você descreveu.]",
                        f"[Write here: “{sec['title']}” — about {words} words. No AI is configured, so Scriber only built the structure and what you described.]"))
        return {"text": "\n\n".join(parts), "summary": sec.get("summary", "")}

    # ---- revisão
    def _clean_blocks(self, blocks: List[Dict[str, Any]], written: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        problems: List[str] = []
        out: List[Dict[str, Any]] = []
        prev = ""
        dup = 0
        for b in blocks:
            t = D.text_of(b).strip() if b.get("t") in D.TEXT_TYPES else ""
            if t and t == prev and b.get("t") in ("p", "quote"):
                dup += 1
                continue
            prev = t or prev
            out.append(b)
        if dup:
            problems.append(f"Removi {dup} parágrafo(s) repetido(s) em sequência.")
        for w in written:
            if w["words"] < max(40, w["target"] * 0.5):
                problems.append(f"«{w['title'][:50]}» ficou com {w['words']} palavras (meta {w['target']}).")
        ph = sum(1 for b in out if b.get("t") in D.TEXT_TYPES and re.search(r"\[(?:Escreva aqui|Write here|citação necessária|verificar|apurar|dados do autor|definir)", D.text_of(b), re.I))
        if ph:
            problems.append(f"{ph} marcador(es) entre colchetes para você preencher ou conferir.")
        return out, problems

    @staticmethod
    def _valid_review(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        s = text(raw.get("summary"), "", 900)
        if not s:
            return None
        return {"approved": raw.get("approved") is not False, "summary": s, "issues": [text(x, "", 200) for x in (raw.get("issues") if isinstance(raw.get("issues"), list) else [])][:8]}

    @staticmethod
    def _fallback_summary(title: str, stats: Dict[str, Any], target: int, wpp: int, problems: List[str], lang: str) -> str:
        pt = S.lang_base(lang) == "pt"
        pages = S.pages_for(stats["words"], wpp)
        s = (f"«{title}»: {stats['words']} palavras (~{pages} páginas), meta de {target}." if pt else f"“{title}”: {stats['words']} words (~{pages} pages), target {target}.")
        if problems:
            s += " " + " ".join(problems[:2])
        return s

    # ================================================================ EDIÇÃO: trecho selecionado
    def edit_text(self, pid: str) -> Dict[str, Any]:
        meta = self.mgr.meta(pid)
        b = self.opts.get("body") or {}
        action = b.get("action") if isinstance(b.get("action"), str) and b.get("action") in S.ACTION_IDS else ("improve" if b.get("selection") else "continue")
        selection = text(b.get("selection"), "", 24000).replace("\xa0", " ")
        instruction = text(self.opts.get("prompt"), "", 3000)
        before, after = text(b.get("context_before"), "", 2500), text(b.get("context_after"), "", 1500)
        kind = b.get("kind") if b.get("kind") in S.SELECTION_KINDS else "paragraph"
        sel_words = S.count_words(selection)
        ex = S.norm_expand(b.get("expand"))
        lang = S.norm_lang(b.get("language") or meta["language"])
        if action in ("expand", "describe"):
            want = ex["words"] if ex["mode"] == "total" else sel_words + ex["words"]
        elif action == "continue":
            want = ex["words"]
        elif action == "shorten":
            want = ex["words"] if ex["mode"] == "total" and ex["words"] < sel_words else max(10, int(sel_words * 0.55))
        else:
            want = sel_words
        want = int(clamp(want, 5, 6000))
        self.start([("lore", "Lorebook"), ("write", "Editor")])
        ctx_text = f"{before[-800:]} {selection} {after[:400]} {instruction}"
        ctx = self.context(instruction or selection[:300]) if (self.opts.get("web") or self.opts.get("sources_text")) else {"web": "", "digest": "", "images": []}
        lore = self.lore(pid, ctx_text)
        self.emit({"type": "step", "id": "lore", "label": "Lorebook", "status": "done", "note": f"{len(lore['used'])} entrada(s)"})
        payload = {"action": action, "selection": selection, "selection_kind": kind, "instruction": instruction, "context_before": before, "context_after": after,
                   "size": {"target_words": want, "min_words": int(want * 0.85), "max_words": int(want * 1.25) + 5, "current_words": sel_words}, "language": S.lang_name(lang), "type": meta["type"],
                   "doc_title": meta["name"], "style_guide": meta["gen"].get("style", ""), "lorebook": lore["text"], "web_notes": ctx["web"][:6000]}
        tokens = int(clamp(want * 2.4 + 400, 700, 12000))
        out = self.step("write", "editor", "Editor", payload, lambda raw: self._valid_edit(raw), lambda: self._edit_rules(action, selection, want, lang, meta), tokens=tokens, creative=action not in ("fix",), critique=False)
        res_text = out["text"]
        changed = out.get("changed", True)
        if self.live and changed and action in ("expand", "describe", "continue", "shorten") and (selection or action == "continue"):
            res_text = self._fit_edit(res_text, want, action, payload, tokens)
        norm = res_text.strip()
        return self.done({"text": norm, "paragraphs": [x for x in norm.split("\n") if x.strip()], "notes": out.get("notes", []), "action": action, "changed": bool(changed and norm != selection.strip()), "ai": self.live,
                          "words": S.count_words(norm), "from_words": sel_words, "target_words": want, "lore": lore["used"], "sources": self.sources})

    @staticmethod
    def _valid_edit(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        t = raw.get("text")
        if isinstance(t, list):
            t = "\n".join(str(x) for x in t)
        if not isinstance(t, str) or not t.strip():
            return None
        t = re.sub(r"^```\w*\n|\n```$", "", D.clean(t).strip())
        t = re.sub(r"\n{2,}", "\n", t)
        return {"text": t[:80000], "notes": [text(x, "", 200) for x in (raw.get("notes") if isinstance(raw.get("notes"), list) else [])][:3], "changed": True}

    def _fit_edit(self, body: str, want: int, action: str, payload: Dict[str, Any], tokens: int) -> str:
        """Expandir/encurtar com tamanho escolhido: se o resultado ficou longe da meta, uma nova rodada pede o ajuste (1–3 conforme o esforço)."""
        for _ in range(max(1, self.team.revisions(1))):
            n = S.count_words(body)
            if want * 0.8 <= n <= want * 1.3:
                break
            self.check()
            pl = dict(payload, action=action, draft_result=body, note=f"Your previous result has {n} words; the target is {want} words (between {int(want * 0.85)} and {int(want * 1.25)}). Return the COMPLETE corrected passage.")
            try:
                raw = self._ask("editor", "Adjust the length of your previous result to the target.", pl, int(tokens * 1.15))
                new = self._valid_edit(raw) if isinstance(raw, dict) else None
            except Cancelled:
                raise
            except (ProviderError, ValueError):
                new = None
            if not new:
                break
            nn = S.count_words(new["text"])
            if abs(nn - want) < abs(n - want):
                body = new["text"]
            else:
                break
        return body

    def _edit_rules(self, action: str, selection: str, want: int, lang: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        """Sem IA: só o que dá para fazer com regras. O que exige criatividade devolve o texto igual e diz isso."""
        pt = S.lang_base(lang) == "pt"
        L_ = lambda a, c: a if pt else c   # noqa: E731
        if action in ("fix", "improve") and selection.strip():
            ps = selection.split("\n")
            fixed = ps
            for _ in range(3):   # achados vizinhos se sobrepõem: refaz até não sobrar nada para corrigir
                res = spell.proofread(fixed, lang, meta.get("ignore", []), use_dict=False)
                nxt = spell.apply_issues(fixed, res["issues"])
                if nxt == fixed:
                    break
                fixed = nxt
            new = "\n".join(spell.normalize_spacing(x, lang) for x in fixed)
            return {"text": new, "notes": [L_("Sem IA: só espaços, pontuação e maiúsculas foram corrigidos.", "No AI: only spacing, punctuation and capitals were fixed.")], "changed": new != selection}
        if action == "shorten" and selection.strip():
            outp, n = [], 0
            for para in selection.split("\n"):
                kept = []
                for sent in re.split(r"(?<=[.!?…])\s+", para.strip()):
                    if n >= want and (kept or outp):
                        break
                    kept.append(sent)
                    n += S.count_words(sent)
                if kept:
                    outp.append(" ".join(kept))
                if n >= want:
                    break
            return {"text": "\n".join(outp), "notes": [L_("Sem IA: mantive as primeiras frases até o tamanho pedido.", "No AI: kept the first sentences up to the requested size.")], "changed": True}
        return {"text": selection, "notes": [L_("Sem IA configurada não dá para fazer isso: o texto ficou como estava. Configure um provedor em Configuração → Provedores.", "This needs an AI provider: the text was left as it was. Set one up in Settings → Providers.")], "changed": False}

    # ================================================================ EDIÇÃO: ortografia e gramática com IA
    def proofread_ai(self, pid: str) -> Dict[str, Any]:
        meta = self.mgr.meta(pid)
        b = self.opts.get("body") or {}
        lang = S.norm_lang(b.get("language") or meta["language"])
        paras = [str(x) for x in b.get("paragraphs")] if isinstance(b.get("paragraphs"), list) else D.plain_paragraphs(self.mgr.get_doc(pid)["blocks"])
        paras = paras[: spell.MAX_PARAS]
        base = spell.proofread(paras, lang, meta.get("ignore", []), use_dict=b.get("dictionary") is not False)
        chunks: List[List[int]] = []
        cur, size = [], 0
        for i, s in enumerate(paras):
            if not s.strip():
                continue
            if cur and size + len(s) > 3200:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(i)
            size += len(s)
        if cur:
            chunks.append(cur)
        self.start([("rules", "Regras e dicionário"), ("ai", "Revisor ortográfico")])
        self.emit({"type": "step", "id": "rules", "label": "Regras e dicionário", "status": "done", "note": f"{len(base['issues'])} achado(s)" + ("" if base["dictionary"] else " · sem dicionário do sistema")})
        ai_issues: List[Dict[str, Any]] = []
        if self.live:
            for ci, idxs in enumerate(chunks[:200]):
                self.check()
                self.emit({"type": "progress", "done": ci, "total": min(len(chunks), 200), "words": 0, "target": 0})
                pl = {"language": S.lang_name(lang), "paragraphs": [{"i": i, "text": paras[i]} for i in idxs]}
                out = self.step(f"ai:{ci + 1}", "proofreader", f"Revisor ortográfico {ci + 1}/{min(len(chunks), 200)}", pl, lambda raw, idxs=idxs: self._valid_fixes(raw, paras, idxs), lambda: {"fixes": []}, creative=False, tokens=1800, quiet=True)
                ai_issues += out["fixes"]
        else:
            self.warnings.append(self.error or "Sem IA: só as regras e o dicionário do sistema.")
        issues = spell.merge_issues(ai_issues, base["issues"])
        return self.done({"issues": issues[:2000], "dictionary": base["dictionary"], "language": lang, "ai": self.live and bool(chunks), "paragraphs": len(paras), "counts": _count_kinds(issues)})

    @staticmethod
    def _valid_fixes(raw: Dict[str, Any], paras: List[str], idxs: List[int]) -> Optional[Dict[str, Any]]:
        fixes = raw.get("fixes")
        if not isinstance(fixes, list):
            return None
        out: List[Dict[str, Any]] = []
        for f in fixes[:200]:
            if not isinstance(f, dict):
                continue
            try:
                i = int(f.get("i"))
            except (TypeError, ValueError):
                continue
            find, rep = f.get("find"), f.get("replace")
            if i not in idxs or not isinstance(find, str) or not isinstance(rep, str) or not find or find == rep or len(find) > 300 or len(rep) > 400:
                continue
            st = paras[i].find(find)
            if st < 0:
                continue
            kind = f.get("kind") if f.get("kind") in ("spelling", "grammar", "punctuation", "repetition") else "grammar"
            out.append({"p": i, "start": st, "end": st + len(find), "found": find, "fix": rep, "kind": kind, "msg": text(f.get("reason"), "", 120) or kind, "source": "ai"})
        return {"fixes": out}


def _count_kinds(issues: List[Dict[str, Any]]) -> Dict[str, int]:
    c: Dict[str, int] = {}
    for i in issues:
        c[i["kind"]] = c.get(i["kind"], 0) + 1
    return c
