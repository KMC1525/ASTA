"""Equipe de agentes de TODAS as seções: quantos agentes (1 · 4 · 8 · 12 · 16) e qual esforço de raciocínio (Low · Medium · High · Extra · Mega · Max · Ultra · Omni).

Os oito níveis são os do modo Code (`code/efforts.py`) e valem **igualmente** em Mundos 3D, Avatars, Jogos 2D, Studio, Rebuild, Canvas, Computer Use, Code e Chat:

  • **Esforço** → o «tempo de pensamento» pedido ao modelo onde o provedor tem suporte (`providers/thinking.py`); o tamanho da resposta de cada agente; as rodadas de revisão/correção
    (`Team.revisions`) e, de Max para cima, uma crítica do plano antes de seguir. Onde o modelo não «pensa» (a maioria dos locais), o que cresce é o orçamento do próprio motor.
  • **Agentes** → com 1, cada etapa roda como sempre (um agente por etapa). Com 4, 8, 12 ou 16, cada etapa criativa vira uma **mesa de N agentes em paralelo**: cada um escreve o seu
    rascunho com uma lente diferente (fidelidade ao pedido, originalidade, coerência, risco…), e um agente **Sintetizador** junta o melhor de todos num resultado só, no mesmo formato
    JSON. Se um agente falha, a mesa segue com os demais; se a síntese falha, vale o primeiro rascunho válido; se nenhum vale, o método automático (determinístico) entrega — como antes.
    Nas conversas (Chat, Avatars) os agentes escrevem **notas privadas** que o redator final usa; no Code o número é de trabalhadores em paralelo.

Custo honesto: N agentes = N chamadas à IA por etapa + 1 de síntese (em paralelo, até 8 ao mesmo tempo). Modelos locais atendem uma por vez, então ficam mais lentos.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import efforts
from .providers import thinking as think

COUNTS: Tuple[int, ...] = (1, 4, 8, 12, 16)
DEFAULT_AGENTS = 1            # 1 = o comportamento de sempre (nada muda para quem não escolher)
MAX_AGENTS = COUNTS[-1]
LEVELS = efforts.LEVELS       # low … omni
DEFAULT_EFFORT = efforts.DEFAULT   # high
MAX_PARALLEL = 8              # chamadas simultâneas à IA dentro de uma mesa
DRAFT_BUDGET_CHARS = 60000    # tamanho máximo dos rascunhos entregues ao Sintetizador
NOTE_BUDGET_CHARS = 9000      # idem, para as notas das conversas
SECTIONS = ("generation", "avatars", "games", "studio", "rebuild", "canvas", "computer", "code", "chat")

#: multiplicador do tamanho da resposta por nível (nunca abaixo do configurado: um JSON cortado vale menos do que um pouco mais de tokens)
TOKENS_MULT = {"low": 1.0, "medium": 1.0, "high": 1.0, "extra": 1.15, "mega": 1.3, "max": 1.5, "ultra": 1.75, "omni": 2.0}

#: as lentes dos agentes (16 = o máximo): cada agente da mesa olha o mesmo pedido por um ângulo
LENSES: Tuple[Tuple[str, str], ...] = (
    ("fidelity", "Stay faithful to the request and to every attachment and constraint, to the letter. Add nothing the user did not ask for."),
    ("originality", "Aim for the most original, memorable and surprising result that still fits the request."),
    ("coherence", "Make everything coherent: names, ids, references, tone, timeline and rules must agree with each other."),
    ("richness", "Aim for richness of detail: concrete, specific, vivid content instead of generic filler."),
    ("simplicity", "Prefer the simplest design that fully works; remove anything that adds complexity without adding value."),
    ("robustness", "Think like a skeptic: find what could be invalid, empty, contradictory or break, and make the result safe against it."),
    ("structure", "Focus on structure and pacing: order, progression, balance and a satisfying beginning, middle and end."),
    ("experience", "Think of the person who will use the result: make it clear, enjoyable and easy to follow."),
    ("lightness", "Respect budgets and limits: keep the result light, compact and within the requested sizes."),
    ("tone", "Focus on tone, style and emotion: the voice must be consistent and fit the request."),
    ("edge-cases", "Cover edge cases and unusual interpretations of the request without drifting from its core."),
    ("completeness", "Check completeness: every requested element must be present and filled in, nothing left as a placeholder."),
    ("clarity", "Focus on clarity: unambiguous wording, short sentences, no jargon the user did not use."),
    ("variety", "Focus on variety: avoid repetition between elements; make each one distinct."),
    ("polish", "Focus on polish: fix awkward wording, small inconsistencies and rough edges."),
    ("integration", "Focus on how the parts fit together as a whole, and on the hand-off to the next step of the pipeline."),
)

#: etapas de planejamento/análise: de Max para cima passam por uma crítica antes de seguir
PLAN_AGENTS = ("analyst", "planner", "analyze", "profiler")


def normalize_agents(value: Any, default: int = DEFAULT_AGENTS) -> int:
    """O valor aceito mais próximo de 1 · 4 · 8 · 12 · 16 (empate → o maior)."""
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return default if default in COUNTS else DEFAULT_AGENTS
    best = COUNTS[0]
    for c in COUNTS:
        if abs(c - n) < abs(best - n) or (abs(c - n) == abs(best - n) and c > best):
            best = c
    return best


def normalize_effort(value: Any, default: str = DEFAULT_EFFORT) -> str:
    s = str(value or "").strip().lower()
    return s if s in LEVELS else (default if default in LEVELS else DEFAULT_EFFORT)


@dataclass(frozen=True)
class Team:
    agents: int = DEFAULT_AGENTS
    effort: str = DEFAULT_EFFORT

    @property
    def prof(self) -> Dict[str, Any]:
        return efforts.PROFILES[self.effort]

    @property
    def multi(self) -> bool:
        return self.agents > 1

    @property
    def thinking(self) -> str:
        """Nível de `providers/thinking.py` que corresponde ao esforço."""
        return efforts.thinking_level(self.effort)

    @property
    def tokens_mult(self) -> float:
        return TOKENS_MULT.get(self.effort, 1.0)

    @property
    def critique(self) -> bool:
        return bool(self.prof["critique_plan"])

    @property
    def workers(self) -> int:
        return max(1, min(self.agents, MAX_PARALLEL))

    def revisions(self, legacy: Optional[int] = None, cap: int = 3) -> int:
        """Rodadas de revisão/correção. `legacy` é o ajuste antigo da seção: o nível High é o ponto neutro (vale o ajuste); abaixo dele só pode diminuir; acima só pode aumentar."""
        want = int(self.prof["revisions"])
        if legacy is None:
            return max(0, min(want, cap))
        legacy = max(0, int(legacy))
        base = efforts.PROFILES["high"]["revisions"]
        if want == base:
            return max(0, min(legacy, cap))
        return max(0, min(max(legacy, want) if want > base else min(legacy, want), cap))

    def public(self) -> Dict[str, Any]:
        return {"agents": self.agents, "effort": self.effort, "thinking": self.thinking, "calls_per_step": self.agents + 1 if self.multi else 1}


def make(agents: Any = None, effort: Any = None, *, default_agents: int = DEFAULT_AGENTS, default_effort: str = DEFAULT_EFFORT) -> Team:
    return Team(normalize_agents(agents if agents is not None else default_agents, default_agents), normalize_effort(effort, default_effort))


def from_config(cfg: Any, req: Any = None, *, agents_key: str = "agents", effort_key: str = "effort", default_effort: str = DEFAULT_EFFORT) -> Team:
    """A equipe de uma seção: o ajuste dela (`cfg`) e, por cima, o escolhido naquele pedido (`req`: `{"team": {"agents", "effort"}}` ou `agents`/`effort` soltos)."""
    c = cfg if isinstance(cfg, dict) else {}
    r = req if isinstance(req, dict) else {}
    rt = r.get("team") if isinstance(r.get("team"), dict) else {}
    agents = rt.get("agents", r.get("agents", c.get(agents_key)))
    effort = rt.get("effort", r.get("effort", c.get(effort_key)))
    if isinstance(agents, str) and not agents.strip().lstrip("-").isdigit():   # ex.: o «agents» antigo do Chat («off»/«plan»/«review») não é um número
        agents = None
    return make(agents, effort, default_effort=default_effort)


def request_team(body: Any) -> Dict[str, Any]:
    """O que o corpo de um pedido HTTP escolheu para a equipe (`team: {agents, effort}` ou `agents`/`effort` soltos), já validado; vazio se não escolheu nada."""
    b = body if isinstance(body, dict) else {}
    t = b.get("team") if isinstance(b.get("team"), dict) else {}
    out: Dict[str, Any] = {}
    a = t.get("agents", b.get("agents"))
    if a is not None and not isinstance(a, bool) and str(a).strip().lstrip("-").isdigit():
        out["agents"] = normalize_agents(a)
    e = t.get("effort", b.get("effort"))
    if isinstance(e, str) and e.strip().lower() in LEVELS:
        out["effort"] = e.strip().lower()
    return out


def options() -> Dict[str, Any]:
    """O que a tela oferece: as contagens, os oito níveis (com a descrição do Code) e o custo de cada contagem."""
    return {"agents": list(COUNTS), "efforts": efforts.listing(), "default_agents": DEFAULT_AGENTS, "default_effort": DEFAULT_EFFORT,
            "lenses": [k for k, _ in LENSES], "calls_per_step": {str(n): (n + 1 if n > 1 else 1) for n in COUNTS}, "max_parallel": MAX_PARALLEL}


def apply_thinking(provider: Any, team: Team, provider_id: str = "", model: str = "") -> str:
    """Pede ao provedor o tempo de pensamento do esforço, onde ele existe (senão `off`). Devolve o nível aplicado."""
    cfg = getattr(provider, "cfg", None)
    pid = provider_id or str((cfg.get("id") if isinstance(cfg, dict) else "") or getattr(provider, "id", "") or "")
    sup = think.support(pid, model or str(getattr(provider, "model", "") or ""))
    level = team.thinking if sup.get("supported") else "off"
    try:
        provider.thinking = level
    except AttributeError:
        pass
    return level


# ----------------------------------------------------------------------------- mesa de agentes (JSON)

DRAFT_HEAD = ("TEAM MODE — you are agent {i} of {n} on a team that works on the same task in parallel. Your lens: {name}. {lens}\n"
              "Do the complete task as usual and answer in exactly the output format required below; a Synthesizer will merge the team's drafts, so make your draft the best it can be through your lens.\n\n")
MERGE_HEAD = ("TEAM MODE — you are the Synthesizer. {n} agents drafted the same task in parallel (see \"drafts\" in the input, each with the lens it used). Merge them into ONE final result: keep what is "
              "common to the best drafts, take the strongest ideas from each, drop contradictions and anything invalid, and keep every name, id and reference consistent. "
              "Answer in exactly the output format required below, as one complete JSON object (not a list of drafts). The original task input is under \"task_input\".\n\n")
CRITIQUE_HEAD = ("CRITIQUE ROUND — below you receive your own previous result under \"draft\" for the same task (the original input is under \"task_input\"). Act as a demanding reviewer: find what is missing, "
                 "inconsistent, vague or wrong, then return the IMPROVED, complete result in exactly the output format required below. If it is already good, return it with only small improvements.\n\n")


def lens_for(i: int) -> Tuple[str, str]:
    return LENSES[i % len(LENSES)]


def _draft_len(d: Any) -> int:
    try:
        return len(json.dumps(d, ensure_ascii=False))
    except (TypeError, ValueError):
        return len(str(d))


def ensemble_json(ask: Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]], team: Team, instruction: str, payload: Dict[str, Any], *,
                  cancelled: Callable[[], bool] = lambda: False, fatal: Tuple[type, ...] = (), note: Optional[Callable[[str], None]] = None,
                  on_draft: Optional[Callable[[int, str, Optional[Dict[str, Any]]], None]] = None, merge: bool = True) -> Optional[Dict[str, Any]]:
    """Roda a mesa de agentes: `ask(instrução, payload) -> objeto | None` é a chamada de UM agente (já com reparo e novas tentativas). Com `team.agents == 1` é só uma chamada.

    Cada agente recebe uma lente; os rascunhos válidos vão ao Sintetizador. Falha de um agente não derruba a mesa (a de todos, sim: o primeiro erro sobe). `fatal` lista exceções
    que sempre sobem (cancelamento). Devolve o objeto final, ou None se nenhum agente devolveu algo utilizável (o chamador usa o método automático)."""
    n = team.agents
    if n <= 1:
        return ask(instruction, payload)
    if note:
        note(f"Equipe de {n} agentes trabalhando em paralelo…")
    results: List[Tuple[int, str, Optional[Dict[str, Any]], Optional[BaseException]]] = []
    lock = threading.Lock()
    stop = threading.Event()

    def one(i: int) -> None:
        name, lens = lens_for(i)
        if stop.is_set() or cancelled():
            return
        try:
            obj = ask(DRAFT_HEAD.format(i=i + 1, n=n, name=name, lens=lens) + instruction, payload)
            err: Optional[BaseException] = None
        except BaseException as exc:  # noqa: BLE001  (um agente que cai não derruba a mesa; o erro decide depois)
            obj, err = None, exc
            if fatal and isinstance(exc, fatal):
                stop.set()
        with lock:
            results.append((i, name, obj, err))
        if on_draft:
            try:
                on_draft(i, name, obj)
            except Exception:  # noqa: BLE001
                pass

    with ThreadPoolExecutor(max_workers=team.workers, thread_name_prefix="asta-team") as pool:
        list(pool.map(one, range(n)))
    results.sort(key=lambda r: r[0])
    for _, _, _, err in results:
        if err is not None and fatal and isinstance(err, fatal):
            raise err
    drafts = [(i, nm, o) for i, nm, o, _ in results if isinstance(o, dict) and o]
    if not drafts:
        errs = [e for *_, e in results if e is not None]
        if errs and len(errs) == len(results):   # todos falharam por erro (rede/credencial): sobe o primeiro; JSON inválido do modelo vira None → método automático
            raise errs[0]
        return None
    if len(drafts) == 1 or not merge:
        return drafts[0][2]
    keep, used = [], 0
    for i, nm, o in drafts:
        size = _draft_len(o)
        if keep and used + size > DRAFT_BUDGET_CHARS:
            continue
        keep.append({"agent": i + 1, "lens": nm, "draft": o})
        used += size
    if note:
        note(f"Sintetizador: juntando os {len(keep)} rascunhos da equipe…")
    try:
        final = ask(MERGE_HEAD.format(n=len(keep)) + instruction, {"task_input": payload, "drafts": keep})
    except BaseException as exc:  # noqa: BLE001
        if fatal and isinstance(exc, fatal):
            raise
        final = None
    return final if isinstance(final, dict) and final else drafts[0][2]


def critique_json(ask: Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]], instruction: str, payload: Dict[str, Any], draft: Dict[str, Any]) -> Dict[str, Any]:
    """Uma rodada de crítica sobre `draft` (de Max para cima, nas etapas de plano). Se a crítica falha, vale o original."""
    try:
        better = ask(CRITIQUE_HEAD + instruction, {"task_input": payload, "draft": draft})
    except Exception:  # noqa: BLE001  (cancelamento e erros reais são tratados pelo chamador na próxima etapa)
        return draft
    return better if isinstance(better, dict) and better else draft


# ----------------------------------------------------------------------------- notas privadas (conversas e nós de texto)

NOTE_SYSTEM = ("You are one specialist of a team that helps write the best possible answer. Your lens: {name}. {lens}\n"
               "You do NOT write the final answer. Reply with 3 to 6 short bullet points (max 180 words in total) of concrete advice for the writer — facts to include, pitfalls to avoid, structure, "
               "tone — based on the conversation. No greetings, no preamble, in the language of the user's last message.")


def team_notes(provider: Any, messages: List[Dict[str, Any]], team: Team, *, max_tokens: int = 420, cancelled: Callable[[], bool] = lambda: False,
               note: Optional[Callable[[str], None]] = None) -> str:
    """As notas privadas de N agentes (em paralelo) para o redator final de uma conversa. Vazio com 1 agente ou se tudo falhar: a resposta segue normal."""
    if team.agents <= 1 or not messages:
        return ""
    if note:
        note(f"Equipe de {team.agents} agentes preparando notas para a resposta…")
    out: List[Tuple[int, str, str]] = []
    lock = threading.Lock()

    def one(i: int) -> None:
        if cancelled():
            return
        name, lens = lens_for(i)
        try:
            res = provider.chat(messages, system=NOTE_SYSTEM.format(name=name, lens=lens), temperature=0.6, max_tokens=max_tokens, stream=False)
            raw = res if isinstance(res, str) else "".join(str(x) for x in (res or []))
        except Exception:  # noqa: BLE001  (sem a nota desse agente a mesa segue)
            return
        body = _clean_reasoning(raw).strip()
        if body:
            with lock:
                out.append((i, name, body[:1400]))

    with ThreadPoolExecutor(max_workers=team.workers, thread_name_prefix="asta-notes") as pool:
        list(pool.map(one, range(team.agents)))
    out.sort(key=lambda r: r[0])
    parts, used = [], 0
    for i, name, body in out:
        if parts and used + len(body) > NOTE_BUDGET_CHARS:
            break
        parts.append(f"[{name}]\n{body}")
        used += len(body)
    return "\n\n".join(parts)


def notes_block(notes: str) -> str:
    """O trecho do prompt de sistema que entrega as notas da equipe ao redator final."""
    if not notes:
        return ""
    return ("\n[TEAM NOTES — private advice from a team of specialist agents; use what helps, ignore what does not, never mention the team or these notes]\n" + notes + "\n[END OF TEAM NOTES]\n")


def _clean_reasoning(raw: str) -> str:
    try:
        from . import avatars as av

        return av.strip_reasoning(str(raw or ""))
    except Exception:  # noqa: BLE001
        return str(raw or "")
