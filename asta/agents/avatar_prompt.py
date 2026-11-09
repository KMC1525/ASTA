"""Pipeline que gera o *system prompt* de um avatar: Analisa → Gera → Revisa → Entrega.

1. **Analisa** — estuda o card (e as instruções do criador) e descobre quem é o personagem: qualquer tipo (original, de uma obra, histórico, robô,
   criatura…), **real ou fictício**, idade, jeito de falar, relação com o usuário, limites e o que o modo de conteúdo (SFW/NSFW) permite.
2. **Gera** — escreve o system prompt a partir da análise.
3. **Revisa** — confere consistência, voz, idioma, tamanho e as regras fixas; se reprovar, o redator corrige uma vez e a revisão roda de novo.
4. **Entrega** — etapa determinística: limpa o texto, aplica as regras de segurança por código (nunca depende do modelo) e, se pedido, grava no avatar.

Regras fixas (valem no NSFW também): conteúdo sexual envolvendo menores não existe; **pessoa real é sempre SFW** (ela não consentiu), retratada só como
interpretação ficcional e respeitosa; personagens fictícios adultos podem ser SFW ou NSFW. Resposta inválida de um agente → fallback por regras.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional

from ..avatars import declares_minor, normalize_avatar
from ..providers import resolve_provider
from ..storage import Store
from ..util import text
from . import prompts
from . import prompts_avatar as P
from . import rulebased_avatars as rb
from .runner import Runner

STEPS = ["analyze", "generate", "review", "deliver"]
CARD_FIELDS = ("name", "relationship", "gender", "age", "description", "personality", "scenario", "looks", "greeting", "examples", "tags", "language", "system_prompt")


def clean_prompt(raw: Any, limit: int = 12000) -> str:
    """Tira cercas de markdown e rótulos que o modelo costuma colocar em volta do texto."""
    if not isinstance(raw, str):  # o modelo devolveu lista/objeto em vez de texto: não serve
        return ""
    s = raw.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*\n?|\n?```\s*$", "", s).strip()
    s = re.sub(r"^(?:system[_ ]prompt|prompt)\s*:\s*", "", s, flags=re.I).strip()
    return s[:limit].strip()


class AvatarPromptPipeline(Runner):
    domain = "avatar"

    def __init__(self, store: Store, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False):
        super().__init__(store, emit, cancelled)

    def run(self, req: Dict[str, Any]) -> Dict[str, Any]:
        st = self.store
        settings = st.get_settings()
        avatar_id = text(req.get("avatar_id"), "", 60)
        base = st.avatars.get(avatar_id) if avatar_id else None
        if avatar_id and not base:
            raise ValueError("Avatar não encontrado.")
        draft = req.get("draft") if isinstance(req.get("draft"), dict) else {}
        card = {k: (base or {}).get(k) for k in CARD_FIELDS}
        card.update({k: v for k, v in draft.items() if k in CARD_FIELDS})
        card = {k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in card.items() if v not in (None, "", [])}
        instructions = text(req.get("instructions"), "", 4000)
        if not (str(card.get("name") or "").strip() or instructions or card.get("description") or card.get("personality")):
            raise ValueError("Informe o nome do personagem ou descreva quem ele é para gerar o system prompt.")
        want = text(req.get("content") or (base or {}).get("content") or draft.get("content"), "sfw", 6).lower()
        want = "nsfw" if want == "nsfw" else "sfw"
        hint = text(req.get("character_type"), "auto", 10).lower()
        hint = hint if hint in ("auto", "fictional", "real") else "auto"
        detail = "short" if str(req.get("detail")) == "short" else "detailed"

        gen = settings["generation"]
        self.gen = {"temperature": gen.get("temperature", 0.8), "max_tokens": min(int(gen.get("max_tokens", 6000)), 4000), "content": "free" if want == "nsfw" else "sfw"}
        # avatars sempre usam IA de verdade quando existe alguma (nuvem ou modelo local), mesmo com a geração ainda no Demo
        self.provider, info = resolve_provider(settings, "generation", st.models_dir)
        pid = info["id"]
        if info["demo"]:
            self.warnings.append("modo Demo (sem IA): " + info["reason"])
        self.configure_team(settings.get("avatars"), req, pid)
        self.emit({"type": "start", "steps": STEPS, "provider": pid, "model": self.provider.model, "content": want, "avatar_id": avatar_id})

        produced = self.produce(card, instructions, want, hint, detail)
        # ---------- 4. Entrega
        return self._deliver(produced["system_prompt"], produced["analysis"], produced["review"], produced["content"], avatar_id, base, card, bool(req.get("apply")), produced["revised"])

    def produce(self, card: Dict[str, Any], instructions: str, want: str, hint: str, detail: str) -> Dict[str, Any]:
        """Etapas 1 a 3 (analisa, gera, revisa) para um card. Usada pelo editor (`run`) e pela criação de avatars (um card por vez)."""
        # ---------- 1. Analisa
        analysis, fb = self._agent("analyze", "avatar_prompt_analyst", P.PROMPT_ANALYST,
                                   {"card": card, "instructions": instructions, "content": want, "character_type_hint": hint,
                                    "relationship": card.get("relationship", "friend")}, rb.prompt_analyst)
        analysis = self._finish_analysis(analysis, card, instructions, hint)
        ctype, minor = analysis["character_type"], analysis["is_minor"]
        content = "sfw" if (ctype == "real" or minor) else want
        if want == "nsfw" and content == "sfw":
            self.warnings.append(
                "pessoa real → apenas SFW: o ASTA não cria conteúdo sexual sobre pessoas reais" if ctype == "real" and not minor
                else "personagem menor de idade → apenas SFW e platônico")
        self.gen["content"] = "free" if content == "nsfw" else "sfw"
        self.language = prompts.lang_name(analysis["language"])
        self._step("analyze", "warn" if fb else "done", character_type=ctype, is_minor=minor, language=analysis["language"], traits=analysis["traits"][:6], content=content)

        # ---------- 2. Gera
        payload = {"analysis": analysis, "card": card, "instructions": instructions, "content": content, "detail": detail}
        written, fb = self._agent("generate", "avatar_prompt_writer", P.PROMPT_WRITER, payload, rb.prompt_writer, tokens_mult=1.0)
        system_prompt = clean_prompt(written.get("system_prompt"))
        if not system_prompt:  # o modelo não entregou o texto → regras
            system_prompt = clean_prompt(rb.prompt_writer(payload)["system_prompt"])
            self.warnings.append("generate: texto vazio, completado por regras")
            fb = True
        self._step("generate", "warn" if fb else "done", words=len(system_prompt.split()))

        # ---------- 3. Revisa (+ uma rodada de correção)
        review = self._review(system_prompt, analysis, card, instructions, content, detail)
        revised = False
        if not review["approved"] and review["issues"]:
            fix = "\n".join(f"- {i.get('problem')} → {i.get('fix')}" for i in review["issues"] if isinstance(i, dict))[:3000]
            self.emit({"type": "revision", "round": 1, "issues": len(review["issues"])})
            redo, _ = self._agent("generate", "avatar_prompt_writer", P.PROMPT_WRITER + "\n\nFEEDBACK TO FIX:\n" + fix,
                                  {**payload, "previous_system_prompt": system_prompt}, rb.prompt_writer, feedback=True)
            fixed = clean_prompt(redo.get("system_prompt"))
            if fixed:
                system_prompt, revised = fixed, True
            self._step("generate", "done", words=len(system_prompt.split()), revision=True)
            review = self._review(system_prompt, analysis, card, instructions, content, detail)
        if not review["approved"]:
            self.warnings.append("reviewer: não aprovado depois da correção")
        return {"system_prompt": system_prompt, "analysis": analysis, "review": review, "content": content, "revised": revised}

    # ------------------------------------------------------------------ etapas
    def _finish_analysis(self, raw: Dict[str, Any], card: Dict[str, Any], instructions: str, hint: str) -> Dict[str, Any]:
        a = dict(raw) if isinstance(raw, dict) else {}
        ctype = a.get("character_type") if a.get("character_type") in ("real", "fictional") else "fictional"
        if hint in ("real", "fictional"):
            ctype = hint  # a escolha do usuário vale mais que o palpite do modelo
        blob = " ".join(str(card.get(k) or "") for k in ("name", "description", "personality", "scenario", "looks", "system_prompt")) + " " + instructions
        try:
            age = int(float(a.get("age"))) if a.get("age") not in (None, "") else int(float(card.get("age") or 24))
        except (TypeError, ValueError):
            age = 24
        age = max(5, min(age, 120))
        # a regra do menor é aplicada por código: vale o que o modelo disse OU o que o texto/idade do card descrevem
        minor = bool(a.get("is_minor")) or age < 18 or declares_minor(blob, age=card.get("age"))
        traits = [str(t) for t in (a.get("traits") or []) if str(t).strip()] if isinstance(a.get("traits"), list) else []
        return {**a, "character_type": ctype, "is_minor": minor, "age": age, "traits": traits,
                "language": text(a.get("language"), "pt-BR", 12), "risks": [str(r) for r in (a.get("risks") or [])][:6] if isinstance(a.get("risks"), list) else []}

    def _review(self, system_prompt: str, analysis, card, instructions, content, detail) -> Dict[str, Any]:
        review, fb = self._agent("review", "avatar_prompt_reviewer", P.PROMPT_REVIEWER,
                                 {"system_prompt": system_prompt, "analysis": analysis, "card": {k: card.get(k) for k in ("name", "age", "relationship", "personality", "description")},
                                  "instructions": instructions, "content": content, "detail": detail}, rb.prompt_reviewer)
        review = dict(review) if isinstance(review, dict) else {}
        review["approved"] = bool(review.get("approved", True))
        review["issues"] = [i for i in (review.get("issues") or []) if isinstance(i, dict)] if isinstance(review.get("issues"), list) else []
        self._step("review", "warn" if fb else "done", approved=review["approved"], score=review.get("score"), issues=len(review["issues"]))
        return review

    def _deliver(self, system_prompt, analysis, review, content, avatar_id, base, card, apply, revised) -> Dict[str, Any]:
        self._check()
        self._step("deliver", "running")
        ctype = analysis["character_type"]
        saved: Optional[Dict[str, Any]] = None
        if apply and base:
            merged = dict(base)
            merged.update({"system_prompt": system_prompt, "character_type": ctype, "content": content})
            saved = self.store.avatars.save(normalize_avatar(merged, keep_id=avatar_id))
        flags = []
        if ctype == "real":
            flags.append("real_person")
        if analysis["is_minor"]:
            flags.append("minor_described")
        result = {
            "type": "done", "system_prompt": system_prompt, "character_type": ctype, "content": content, "is_minor": analysis["is_minor"], "flags": flags,
            "language": analysis["language"], "approved": review["approved"], "score": review.get("score"), "revised": revised,
            "analysis": {k: analysis.get(k) for k in ("character_type", "kind", "source_work", "identity", "age", "traits", "relationship_dynamic", "risks", "notes")},
            "warnings": self.warnings, "applied": bool(saved), "avatar_id": (saved or {}).get("id") or avatar_id,
        }
        self._step("deliver", "done", applied=bool(saved), words=len(system_prompt.split()))
        self.emit(result)
        return result
