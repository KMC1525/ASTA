"""Pipeline multi-agentes que cria avatars: Anexos → Analista → Designer → Revisor → Salvar.

Aceita texto, imagens e qualquer anexo (documentos, planilhas, áudio, vídeo…) e cria 1 ou vários
avatars de uma vez. Resposta inválida de um agente → fallback por regras (sempre entrega).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import attachments as att
from .. import voice
from ..avatars import MAX_CHAT_AVATARS, MIN_FIELD_AGE, RELATIONSHIPS, normalize_avatar
from ..providers import resolve_provider
from ..storage import Store
from ..canvas.engine import palette_of
from ..util import text
from . import prompts_avatar as P
from . import rulebased_avatars as rb
from .runner import Runner

STEPS = ["attachments", "analyst", "designer", "reviewer", "prompts", "save"]
IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}


class AvatarPipeline(Runner):
    domain = "avatar"

    def __init__(self, store: Store, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False):
        super().__init__(store, emit, cancelled)

    def run(self, req: Dict[str, Any]) -> Dict[str, Any]:
        st = self.store
        settings = st.get_settings()
        content = "nsfw" if req.get("content") == "nsfw" else "sfw"
        ctype_hint = text(req.get("character_type"), "auto", 10).lower()
        ctype_hint = ctype_hint if ctype_hint in ("real", "fictional") else "auto"
        relationship = text(req.get("relationship"), "auto", 12).lower()
        relationship = relationship if relationship in RELATIONSHIPS else "auto"
        count_hint = int(max(0, min(int(req.get("count") or 0), MAX_CHAT_AVATARS)))
        prompt = str(req.get("prompt") or "").strip()
        from_images = bool(req.get("from_images"))  # foto/arte como base: a imagem define o visual (e vira o retrato); o texto só complementa
        images_mode = "one" if req.get("images_mode") == "one" else "each"
        gen = settings["generation"]
        self.gen = {"temperature": gen.get("temperature", 0.8), "max_tokens": min(int(gen.get("max_tokens", 6000)), 6000),
                    "content": "free" if content == "nsfw" else "sfw"}
        # avatars sempre usam IA de verdade quando existe alguma (nuvem ou modelo local), mesmo com a geração ainda no Demo
        self.provider, info = resolve_provider(settings, "generation", st.models_dir)
        pid = info["id"]
        if info["demo"]:
            self.warnings.append("modo Demo (sem IA): " + info["reason"])
        self.emit({"type": "start", "steps": STEPS, "provider": pid, "model": self.provider.model, "count": count_hint, "content": content})

        # ---------- anexos
        self._step("attachments", "running")
        uploads = [m for m in (st.get_upload(u) for u in (req.get("attachment_ids") or [])[:40]) if m]
        analyzed: List[Dict[str, Any]] = []
        transcribe = voice.transcriber(settings)
        for meta in uploads:
            self._check()
            analyzed.append(att.analyze(Path(meta["path"]), meta["name"], meta.get("mime", ""), transcribe=transcribe))
        digest = att.build_digest(analyzed)
        images = att.collect_images(analyzed)
        self._step("attachments", "done" if uploads else "skipped", count=len(uploads), images=len(images))
        refs = [(m, a) for m, a in zip(uploads, analyzed) if a["kind"] == "image" and a["ext"] in IMAGE_EXTS]
        if from_images and not refs:
            raise ValueError("Anexe pelo menos uma imagem (foto ou arte) para usá-la como base do avatar.")
        ref_names = [_pretty_name(m["name"]) for m, _ in refs]
        if not prompt and not digest and not uploads:
            raise ValueError("Descreva o avatar ou anexe algo (imagem, texto, documento…) para criá-lo.")

        # ---------- 1. Analista
        brief, fb = self._agent(
            "analyst", "avatar_analyst", P.ANALYST,
            {"prompt": prompt, "attachments_digest": digest, "count_hint": count_hint, "relationship": relationship, "content": content,
             "attached_images": len(images), "language_hint": text(req.get("language"), "", 12), "character_type_hint": ctype_hint,
             "from_images": from_images, "images_mode": images_mode, "image_names": ref_names if from_images else [],
             "image_palettes": [palette_of(Path(m["path"]), 3) for m, _ in refs] if from_images else []},
            rb.analyst, images=images,
        )
        brief_avatars = [a for a in (brief.get("avatars") or []) if isinstance(a, dict) and text(a.get("name"), "")]
        if not brief_avatars:  # modelo omitiu a lista → regras
            brief = rb.analyst({"prompt": prompt, "attachments_digest": digest, "count_hint": count_hint, "relationship": relationship,
                                "from_images": from_images, "images_mode": images_mode, "image_names": ref_names if from_images else [],
                                "image_palettes": [palette_of(Path(m["path"]), 3) for m, _ in refs] if from_images else []})
            brief_avatars = brief["avatars"]
        cap = count_hint or MAX_CHAT_AVATARS
        if from_images:  # a estrutura vem das imagens, não do palpite do modelo: 1 por imagem ("each") ou 1 só ("one")
            brief_avatars = _fit_to_images(brief_avatars, ref_names, images_mode, self.warnings)
            cap = len(brief_avatars)
        brief["avatars"] = brief_avatars[:cap]
        for a in brief["avatars"]:
            a["age"] = _age(a.get("age"))
            # real (pessoa de verdade, inclusive a de uma foto) ou fictício: a escolha do usuário vence o palpite do analista
            a["character_type"] = ctype_hint if ctype_hint != "auto" else ("real" if a.get("character_type") == "real" or (from_images and a.get("source_kind") == "photo") else "fictional")
            if relationship != "auto":
                a["relationship"] = relationship
        brief["language"] = text(brief.get("language"), "pt-BR", 12)
        brief["group"] = bool(brief.get("group")) and len(brief["avatars"]) > 1
        from . import prompts

        self.language = prompts.lang_name(brief["language"])
        self._step("analyst", "warn" if fb else "done", count=len(brief["avatars"]), names=[a["name"] for a in brief["avatars"]])

        # ---------- 2. Designer
        detail = "short" if str(req.get("detail")) == "short" else "detailed"
        # foto de pessoa real (ou origem desconhecida): nunca NSFW — só arte de personagens fictícios pode ser NSFW
        eff_content = "sfw" if any(a.get("character_type") == "real" for a in brief["avatars"]) or (from_images and any(a.get("source_kind") != "art" for a in brief["avatars"])) else content
        payload = {"brief": brief, "content": eff_content, "detail": detail,
                   "user": {"name": settings["avatars"].get("user_name", ""), "persona": settings["avatars"].get("user_persona", "")}}
        mult = max(1.0, len(brief["avatars"]) * 0.7)
        cards_raw, fb = self._agent("designer", "avatar_designer", P.DESIGNER, payload, rb.designer, tokens_mult=mult)
        cards = self._finish_cards(cards_raw, brief, content, relationship, from_images)
        self._step("designer", "warn" if fb else "done", count=len(cards))

        # ---------- 3. Revisor (+ uma rodada de correção)
        review = self._review(cards, brief, prompt, content)
        if not review.get("approved", True) and review.get("issues"):
            fb_text = "\n".join(f"- [{i.get('avatar')}] {i.get('problem')} → {i.get('fix')}" for i in review["issues"] if isinstance(i, dict))[:3000]
            self.emit({"type": "revision", "round": 1, "issues": len(review["issues"])})
            redo, _ = self._agent("designer", "avatar_designer", P.DESIGNER + "\n\nFEEDBACK TO FIX:\n" + fb_text, payload, rb.designer,
                                  tokens_mult=mult, feedback=True)
            fixed = self._finish_cards(redo, brief, content, relationship, from_images)
            if fixed:
                cards = fixed
            self._step("designer", "done", count=len(cards), revision=True)
            review = self._review(cards, brief, prompt, content)
        if not review.get("approved", True):
            self.warnings.append("reviewer: not approved after revision")

        # ---------- 4. Pipeline de system prompt (Analisa → Gera → Revisa → Entrega) para cada avatar
        if req.get("prompt_pipeline", True) is False:
            self._step("prompts", "skipped")
        else:
            cards = self._prompt_stage(cards, brief, prompt, ctype_hint, detail)

        # ---------- 5. Salvar
        return self._save(cards, brief, uploads, analyzed, review)

    # ------------------------------------------------------------------ etapas
    def _finish_cards(self, raw: Dict[str, Any], brief: Dict[str, Any], content: str, relationship: str, from_images: bool = False) -> List[Dict[str, Any]]:
        items = [c for c in (raw.get("avatars") or []) if isinstance(c, dict)]
        by_name = {text(c.get("name"), "").lower(): c for c in items}
        out: List[Dict[str, Any]] = []
        names = [a["name"] for a in brief["avatars"]]
        for i, a in enumerate(brief["avatars"]):
            card = by_name.get(a["name"].lower()) or (items[i] if i < len(items) else None)
            if card is None or not text(card.get("system_prompt"), ""):  # o modelo esqueceu este avatar → regras
                card = rb.designer({"brief": {**brief, "avatars": [a]}, "content": content})["avatars"][0]
                self.warnings.append(f"designer: {a['name']} completed by fallback")
            card = dict(card)
            card.setdefault("name", a["name"])
            card["name"] = a["name"] or card["name"]
            card["age"] = _age(card.get("age") if card.get("age") not in (None, "") else a.get("age"))
            card["content"] = content
            card["character_type"] = "real" if a.get("character_type") == "real" else "fictional"
            if content == "nsfw" and card["character_type"] == "real":
                card["content"] = "sfw"
                self.warnings.append(f"{a['name']}: pessoa real → apenas SFW; o ASTA não cria conteúdo sexual sobre pessoas reais (personagens fictícios podem ser NSFW)")
            elif content == "nsfw" and from_images and a.get("source_kind") != "art":
                card["content"] = "sfw"
                self.warnings.append(f"{a['name']}: foto de pessoa real (ou origem não identificada) → apenas SFW; NSFW só vale para arte de personagens fictícios")
            if from_images and a.get("looks") and not card.get("looks"):
                card["looks"] = a["looks"]
            if relationship != "auto":
                card["relationship"] = relationship
            elif card.get("relationship") not in RELATIONSHIPS:
                card["relationship"] = a.get("relationship", "friend")
            card["source"] = "ai"
            if not card.get("looks") and a.get("looks"):
                card["looks"] = a["looks"]
            norm = normalize_avatar(card)
            if "minor_described" in norm["flags"]:
                self.warnings.append(f"{norm['name']}: descrito como menor de idade → apenas SFW e amizade")
            out.append(norm)
        return out[:MAX_CHAT_AVATARS]

    def _prompt_stage(self, cards: List[Dict[str, Any]], brief: Dict[str, Any], prompt: str, ctype_hint: str, detail: str) -> List[Dict[str, Any]]:
        """Roda o pipeline de system prompt (analisa, gera, revisa, entrega) em cada avatar; o texto do Designer vira ponto de partida.
        As regras fixas valem aqui também: pessoa real ou menor de idade viram SFW por código, qualquer que seja a resposta do modelo."""
        from .avatar_prompt import AvatarPromptPipeline

        total = len(cards)
        self._step("prompts", "running", index=0, total=total)
        sub = AvatarPromptPipeline(self.store, lambda ev: None, self.cancelled)
        sub.provider, sub.gen = self.provider, dict(self.gen)
        names = [c["name"] for c in cards]
        out: List[Dict[str, Any]] = []
        approved = revised = 0
        for i, card in enumerate(cards):
            self._check()
            self._step("prompts", "running", current=card["name"], index=i + 1, total=total)
            sub.warnings, sub.language = [], self.language
            fields = {k: (", ".join(v) if isinstance(v, list) else v) for k, v in card.items()
                      if k in ("name", "relationship", "gender", "age", "description", "personality", "scenario", "looks", "greeting", "examples", "tags", "language", "system_prompt")
                      and v not in (None, "", [])}
            if brief.get("group") and total > 1:
                fields["knows"] = ", ".join(n for n in names if n != card["name"])
            b = brief["avatars"][i] if i < len(brief["avatars"]) else {}
            hint = "real" if b.get("character_type") == "real" else ctype_hint  # o analista da criação já marcou como real: respeita (mais restritivo)
            sub.gen["content"] = "free" if card["content"] == "nsfw" else "sfw"
            res = sub.produce(fields, f"Original request: {prompt[:1200]}" if prompt else "", card["content"], hint, detail)
            new = dict(card)
            new["system_prompt"] = res["system_prompt"]
            new["character_type"] = "real" if res["analysis"]["character_type"] == "real" or card.get("character_type") == "real" else "fictional"
            new["content"] = res["content"] if new["character_type"] != "real" else "sfw"
            if card["content"] == "nsfw" and new["content"] == "sfw" and not any("SFW" in w or "sfw" in w for w in sub.warnings):
                sub.warnings.append("apenas SFW")
            self.warnings += [f"{card['name']}: {w}" for w in sub.warnings]
            approved += 1 if res["review"]["approved"] else 0
            revised += 1 if res["revised"] else 0
            out.append(normalize_avatar(new))
        self._step("prompts", "done" if approved == total else "warn", count=total, approved=approved, revised=revised)
        return out

    def _review(self, cards, brief, prompt, content):
        payload = {"request": prompt[:1500], "brief": {k: brief.get(k) for k in ("language", "group", "tone")}, "content": content,
                   "avatars": [{"name": c["name"], "age": c["age"], "relationship": c["relationship"], "content": c["content"],
                                "personality": c["personality"], "greeting": c["greeting"], "system_prompt": c["system_prompt"][:700]} for c in cards]}
        review, fb = self._agent("reviewer", "avatar_reviewer", P.REVIEWER, payload, rb.reviewer)
        review["approved"] = bool(review.get("approved", True))
        self._step("reviewer", "warn" if fb else "done", approved=review["approved"], score=review.get("score"),
                   issues=len(review.get("issues") or []))
        return review

    def _save(self, cards, brief, uploads, analyzed, review) -> Dict[str, Any]:
        self._check()
        self._step("save", "running")
        st = self.store
        saved = [st.avatars.save(c) for c in cards]
        images = [(m, a) for m, a in zip(uploads, analyzed) if a["kind"] == "image" and a["ext"] in IMAGE_EXTS]
        for i, av in enumerate(saved):
            idx = (brief["avatars"][i].get("image_index") if i < len(brief["avatars"]) else None)
            if not isinstance(idx, int) or not 0 <= idx < len(images):
                idx = i if len(images) == len(saved) else (0 if len(saved) == 1 and images else None)
            if idx is None:
                continue
            meta, item = images[idx]
            try:
                data = Path(meta["path"]).read_bytes()
                if len(data) <= 8 * 1024 * 1024:
                    st.save_portrait(av["id"], data, item["ext"])
            except OSError:
                self.warnings.append(f"{av['name']}: não foi possível guardar o retrato")
        for meta in uploads:
            st.delete_upload(meta["id"])
        self._step("save", "done", count=len(saved))
        result = {
            "type": "done", "avatar_ids": [a["id"] for a in saved],
            "avatars": [{"id": a["id"], "name": a["name"], "relationship": a["relationship"], "content": a["content"], "greeting": a["greeting"]} for a in st_refresh(st, saved)],
            "group": bool(brief.get("group")), "warnings": self.warnings, "approved": review.get("approved", True),
        }
        self.emit(result)
        return result


def _pretty_name(filename: str) -> str:
    """Nome sugerido a partir do arquivo ("luna_azul-01.png" → "Luna Azul"); vazio se não sobrar nada útil."""
    import re

    stem = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", filename)
    stem = re.sub(r"[\d_\-.()]+", " ", stem)
    stem = " ".join(w for w in stem.split() if w.lower() not in ("img", "image", "imagem", "foto", "photo", "screenshot", "captura", "dsc", "pxl", "whatsapp", "untitled"))
    words = [w for w in stem.split() if w.isalpha()][:3]
    return " ".join(w.capitalize() for w in words)


def _fit_to_images(avatars: List[Dict[str, Any]], names: List[str], mode: str, warnings: List[str]) -> List[Dict[str, Any]]:
    """Garante a estrutura pedida: "each" = um avatar por imagem (na ordem); "one" = um avatar só (com a 1ª imagem)."""
    want = min(len(names), MAX_CHAT_AVATARS) if mode == "each" else 1
    if mode == "each" and len(names) > MAX_CHAT_AVATARS:
        warnings.append(f"só os {MAX_CHAT_AVATARS} primeiros avatares serão criados (limite por conversa)")
    out = []
    for i in range(want):
        a = dict(avatars[i]) if i < len(avatars) else {"name": names[i] if mode == "each" and i < len(names) and names[i] else f"Avatar {i + 1}", "relationship": "friend",
                                                       "gender": "", "age": 24, "traits": [], "talkativeness": 0.6, "hair_color": "", "looks": "", "backstory": ""}
        a["image_index"] = i if mode == "each" else 0
        if a.get("source_kind") not in ("photo", "art"):
            a["source_kind"] = "unknown"
        out.append(a)
    return out


def _age(value: Any, default: int = 24) -> int:
    """Idade como informada: nunca "envelhecemos" um personagem descrito como menor (ele fica SFW/platônico)."""
    try:
        return max(MIN_FIELD_AGE, min(int(float(value)), 120))
    except (TypeError, ValueError):
        return default


def st_refresh(store: Store, saved: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [store.avatars.get(a["id"]) or a for a in saved]
