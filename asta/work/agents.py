"""A IA do Work: equipes pequenas de agentes (planejar → escrever → conferir), cada uma com **fallback determinístico** — o Work entrega mesmo sem IA ou com resposta inválida.

  • `draft_request`  — Planejador → Redator → Revisor: do rascunho solto + anexos a um pedido claro, com checklist e destinatários sugeridos.
  • `draft_flow`     — Analista → Desenhista → Revisor: da descrição da empresa a um fluxograma (cargos, setores, ligações) validado, que o usuário confere antes de aplicar.
  • `digest`         — números exatos calculados pelo programa + Redator: resumo do dia/semana de uma pessoa, de um setor ou da organização.
  • `suggest`        — Roteador: quem deve receber um pedido, pelo cargo, função e carga de trabalho, junto do caminho no fluxograma.

A IA escreve **dados** (JSON validado), nunca código. Quantos agentes (1·4·8·12·16·20·24·28·32) e o esforço (Low…Omni) vêm de `asta/team.py`, como em todas as seções.
"""
from __future__ import annotations

import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import team as teamlib
from ..agents.llm import call_json
from ..agents.prompts import POLICY_FREE, POLICY_SFW
from ..providers import ProviderError
from ..util import text
from . import board, schema as S

PROMPTS = Path(__file__).parent / "prompts"
STEP_TOKENS = 1600


@lru_cache(maxsize=32)
def prompt(name: str) -> str:
    try:
        return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def prompt_names() -> List[str]:
    return sorted(p.stem for p in PROMPTS.glob("*.md"))


class Cancelled(Exception):
    pass


class WorkAI:
    """Uma execução da IA do Work: guarda o provedor, a equipe e o registro (log) de cada agente."""

    def __init__(self, mgr: Any, req: Optional[Dict[str, Any]] = None):
        self.mgr = mgr
        settings = mgr.store.get_settings()
        cfg = mgr.config()
        self.team = teamlib.from_config(cfg, req)
        self.content = (settings.get("generation") or {}).get("content", "free")
        self.provider: Any = None
        self.error = ""
        try:
            provider, info = _unpack(mgr.resolve_provider(settings))
            if info.get("demo") or getattr(provider, "id", "") == "demo":
                self.error = info.get("reason") or "Nenhuma IA configurada: usei as regras automáticas do Work."
            else:
                self.provider = provider
                teamlib.apply_thinking(provider, self.team, info.get("id", ""), info.get("model", ""))
        except (ProviderError, Exception) as exc:  # noqa: BLE001
            self.error = str(exc)[:200]
        self.log: List[Dict[str, Any]] = []

    @property
    def live(self) -> bool:
        return self.provider is not None

    # ---------------------------------------------------------------- uma chamada de agente
    def _ask(self, agent: str, instruction: str, payload: Dict[str, Any], tokens: int = STEP_TOKENS) -> Optional[Dict[str, Any]]:
        system = prompt("core") + "\n\n" + prompt(agent) + "\n\n" + (POLICY_SFW if self.content == "sfw" else POLICY_FREE)
        obj, _ = call_json(self.provider, system, instruction + "\nOutput JSON: see the format in your role description.", payload,
                           max_tokens=int(tokens * self.team.tokens_mult), temperature=0.4, attempts=2)
        return obj

    def step(self, agent: str, label: str, payload: Dict[str, Any], validate: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
             fallback: Callable[[], Dict[str, Any]], *, creative: bool = True, critique: bool = False) -> Dict[str, Any]:
        """Roda um agente (ou a mesa de N agentes) e devolve o resultado **validado**; se a IA falha ou devolve lixo, vale o `fallback`."""
        started = time.time()
        note = ""
        out: Optional[Dict[str, Any]] = None
        if self.live:
            instruction = f"Do your role for this input ({label})."
            ask = lambda ins, pl: self._ask(agent, ins, pl)   # noqa: E731
            try:
                raw = teamlib.ensemble_json(ask, self.team, instruction, payload) if creative and self.team.multi else ask(instruction, payload)
                if raw and critique and self.team.critique:
                    raw = teamlib.critique_json(ask, instruction, payload, raw)
                out = validate(raw) if isinstance(raw, dict) else None
                if out is None:
                    note = "resposta inválida da IA"
            except (ProviderError, ValueError) as exc:
                note = str(exc)[:160]
        else:
            note = self.error or "sem IA"
        if out is None:
            out = fallback()
            self.log.append({"agent": agent, "label": label, "status": "fallback", "note": note, "ms": int((time.time() - started) * 1000)})
        else:
            self.log.append({"agent": agent, "label": label, "status": "ok", "note": "", "ms": int((time.time() - started) * 1000)})
        return out

    def report(self) -> Dict[str, Any]:
        return {"ai": self.live and any(s["status"] == "ok" for s in self.log), "agents": self.log, "team": self.team.public(), "warning": "" if self.live else (self.error or "Sem IA: usei as regras automáticas do Work.")}


def _unpack(res: Any) -> Any:
    if isinstance(res, tuple) and len(res) == 2:
        return res
    return res, {"demo": getattr(res, "id", "") == "demo", "id": getattr(res, "id", ""), "model": getattr(res, "model", "")}


# ============================================================================ pedidos
def _people(ctx: Any, busy: Dict[str, int]) -> List[Dict[str, Any]]:
    roles, fns = ctx.st.map("roles"), ctx.st.map("functions")
    out = []
    for u in ctx.st.all("users"):
        if u.get("disabled") or u["id"] == ctx.uid:
            continue
        out.append({"id": u["id"], "name": u.get("display_name") or u["username"], "role": (roles.get(u.get("role_id")) or {}).get("name", ""), "title": u.get("title", ""),
                    "functions": [fns[f]["name"] for f in u.get("function_ids", []) if f in fns], "bio": (u.get("bio") or "")[:200], "busy": busy.get(u["id"], 0)})
    return out


def _busy(ctx: Any) -> Dict[str, int]:
    busy: Dict[str, int] = {}
    for a in ctx.st.all("activities"):
        if a.get("state") in ("started", "continuing"):
            busy[a.get("user")] = busy.get(a.get("user"), 0) + 1
    return busy


_WORD = re.compile(r"[a-zà-ÿ0-9]{3,}", re.I)
_STOP = set("para com uma que não por mais como mas foi são tem ser está sua seu dos das nas nos the and for with this that from have não até sobre favor preciso precisamos".split())


def _stem(w: str) -> str:
    """Raiz grosseira (sem plural, 6 letras): «financeiro» e «financeiros» se encontram."""
    return (w[:-1] if len(w) > 4 and w.endswith("s") else w)[:6]


def _tokens(s: str) -> List[str]:
    return [_stem(w) for w in (m.lower() for m in _WORD.findall(s or "")) if w not in _STOP]


def rank_people(brief: str, people: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    """Fallback do Roteador: quem tem mais palavras em comum com o pedido (função, cargo, bio), desempatando por menos atividades em andamento."""
    want = set(_tokens(brief))
    scored = []
    for p in people:
        have = set(_tokens(" ".join([p.get("role", ""), p.get("title", ""), " ".join(p.get("functions", [])), p.get("bio", "")])))
        score = len(want & have)
        if score:
            scored.append((-score, p.get("busy", 0), p["name"].lower(), p))
    scored.sort(key=lambda t: t[:3])
    return [{"user": t[3]["id"], "why": "Combina com: " + ", ".join(sorted(want & set(_tokens(" ".join([t[3].get('role', ''), t[3].get('title', ''), " ".join(t[3].get('functions', [])), t[3].get('bio', '')]))))[:5])}
            for t in scored[:limit]]


def _fallback_priority(brief: str) -> str:
    low = brief.lower()
    if re.search(r"\b(urgente|urgent|asap|agora mesmo|hoje|imediat\w*)\b", low):
        return "urgent"
    if re.search(r"\b(importante|prioridade|priority|important|crítico|critico)\b", low):
        return "high"
    return "normal"


def _fallback_due(brief: str) -> str:
    m = re.search(r"\b(20\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b", brief)
    return m.group(0) if m else ""


def _clean_list(v: Any, n: int, width: int = 200) -> List[str]:
    return [text(x, "", width) for x in v if isinstance(x, (str, int, float)) and text(x, "", width)][:n] if isinstance(v, list) else []


def draft_request(ctx: Any, brief: str, attachments_text: str = "", to: Optional[List[str]] = None, req: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Do rascunho solto a um pedido pronto para enviar (o usuário confere e edita antes)."""
    ai = WorkAI(ctx.mgr, req)
    brief = text(brief, "", 12000)
    if not brief and not attachments_text:
        raise ValueError("Escreva o rascunho do pedido ou anexe algo.")
    busy = _busy(ctx)
    people = _people(ctx, busy)
    ids = {p["id"] for p in people}
    base = {"brief": brief, "attachments_text": attachments_text[:12000], "people": people, "preferred_recipients": to or [], "today": time.strftime("%Y-%m-%d")}

    def plan_ok(o: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        goal = text(o.get("goal"), "", 400)
        if not goal:
            return None
        return {"goal": goal, "deliverables": _clean_list(o.get("deliverables"), 8), "priority": S.pick(o.get("priority"), S.PRIORITIES, "normal"),
                "due": _fallback_due(str(o.get("due") or "")), "recipients": [r for r in S.id_list(o.get("recipients"), 3) if r in ids]}

    def plan_fb() -> Dict[str, Any]:
        first = re.split(r"(?<=[.!?])\s|\n", (brief or attachments_text).strip(), maxsplit=1)[0]
        return {"goal": text(first, "", 300), "deliverables": [], "priority": _fallback_priority(brief), "due": _fallback_due(brief), "recipients": [r["user"] for r in rank_people(brief, people)]}

    plan = ai.step("planner", "request-plan", base, plan_ok, plan_fb, critique=True)

    def write_ok(o: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title, body = text(o.get("title"), "", 120), text(o.get("body"), "", 20000)
        return {"title": title, "body": body, "checklist": _clean_list(o.get("checklist"), 8)} if title and body else None

    def bullets() -> List[str]:
        return [text(re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", ln), "", 200) for ln in brief.splitlines() if re.match(r"^\s*(?:[-*•]|\d+[.)])\s+\S", ln)][:8]

    def write_fb() -> Dict[str, Any]:
        return {"title": text(re.sub(r"\s+", " ", plan["goal"]), "", 90) or "Pedido", "body": brief or attachments_text[:4000], "checklist": plan["deliverables"] or bullets()}

    draft = ai.step("writer", "request-draft", {**base, "plan": plan}, write_ok, write_fb)

    def review_ok(o: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        d = write_ok(o)
        if not d:
            return None
        return {**d, "priority": S.pick(o.get("priority"), S.PRIORITIES, plan["priority"]), "due": _fallback_due(str(o.get("due") or "")) or plan["due"], "issues": _clean_list(o.get("issues"), 6)}

    final = ai.step("reviewer", "request-review", {**base, "plan": plan, "draft": draft}, review_ok,
                    lambda: {**draft, "priority": plan["priority"], "due": plan["due"], "issues": []}, creative=False)
    recipients = [r for r in (to or []) if r in ids] or plan["recipients"]
    return {**final, "recipients": recipients, "route": ctx.mgr.route_between(ctx.st, ctx.uid, recipients[0]) if recipients else [], **ai.report()}


def suggest(ctx: Any, rid: str = "", brief: str = "", req: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Quem deve receber (ou assumir) um pedido: Roteador com fallback por afinidade de palavras + o caminho no fluxograma."""
    ai = WorkAI(ctx.mgr, req)
    if rid:
        r = ctx.st.get("requests", rid)
        if not r or not ctx.mgr.can_see_request(ctx, r):
            raise ValueError("Pedido não encontrado.")
        brief = (r.get("title", "") + "\n" + r.get("body", "")).strip()
    brief = text(brief, "", 8000)
    if not brief:
        raise ValueError("Informe o pedido.")
    people = _people(ctx, _busy(ctx))
    ids = {p["id"] for p in people}
    route = ctx.mgr.route_between(ctx.st, ctx.uid, people[0]["id"]) if people else []

    def ok(o: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rec = [{"user": x.get("user"), "why": text(x.get("why"), "", 200)} for x in o.get("recipients", []) if isinstance(x, dict) and x.get("user") in ids][:3] if isinstance(o.get("recipients"), list) else []
        return {"recipients": rec, "route_note": text(o.get("route_note"), "", 300)} if rec else None

    out = ai.step("router", "route", {"request": brief, "people": people, "route": route}, ok, lambda: {"recipients": rank_people(brief, people), "route_note": ""}, creative=False)
    for x in out["recipients"]:
        x["route"] = ctx.mgr.route_between(ctx.st, ctx.uid, x["user"])
    return {**out, **ai.report()}


# ============================================================================ fluxograma
SECTOR_WORDS = [(r"financ|contab|tesour", "Financeiro"), (r"\brh\b|recursos humanos|pessoas|people", "RH"), (r"comercial|vendas|sales", "Comercial"), (r"market", "Marketing"),
                (r"\bti\b|tecnolog|desenvolv|software|dev\b|engenharia", "Tecnologia"), (r"opera[cç]", "Operações"), (r"jur[ií]d|legal", "Jurídico"),
                (r"suporte|atendimento|support|sac\b", "Atendimento"), (r"log[ií]st|estoque|expedi", "Logística"), (r"produ[cç][aã]o|f[aá]brica|manufat", "Produção"),
                (r"design|cria[cç][aã]o|criativ", "Design"), (r"compras|suprimentos|procurement", "Compras"), (r"qualidade|quality", "Qualidade"), (r"admin", "Administrativo")]
COLORS = ["#3e9bff", "#f5a524", "#30a46c", "#e5484d", "#a78bfa", "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#14b8a6", "#8b5cf6", "#eab308"]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:24] or "x"


def fallback_flow(description: str) -> Dict[str, Any]:
    """Fluxograma padrão por palavras-chave: administração no topo → um gerente por setor → a equipe do setor."""
    low = description.lower()
    names = [name for rx, name in SECTOR_WORDS if re.search(rx, low)] or ["Operações", "Administrativo", "Atendimento"]
    sectors, nodes, edges = [], [{"key": "top", "kind": "role", "label": "Diretoria", "text": "", "sector": "", "ref": "admin"}], []
    for i, name in enumerate(names[:12]):
        k = _slug(name)
        sectors.append({"key": k, "name": name, "color": COLORS[i % len(COLORS)], "description": ""})
        nodes += [{"key": f"s-{k}", "kind": "sector", "label": name, "text": "", "sector": k, "ref": ""},
                  {"key": f"m-{k}", "kind": "role", "label": f"Gerente de {name}", "text": "", "sector": k, "ref": "manager"},
                  {"key": f"w-{k}", "kind": "role", "label": f"Equipe de {name}", "text": "", "sector": k, "ref": "worker"}]
        edges += [{"from": "top", "to": f"m-{k}", "kind": "reports", "label": ""}, {"from": f"m-{k}", "to": f"w-{k}", "kind": "reports", "label": ""},
                  {"from": f"s-{k}", "to": f"m-{k}", "kind": "handoff", "label": ""}]
    return {"sectors": sectors, "nodes": nodes, "edges": edges}


def normalize_flow(raw: Any, role_ids: List[str], user_ids: List[str]) -> Optional[Dict[str, Any]]:
    """Valida um fluxograma vindo da IA (ou de fora): tipos, chaves únicas, ligações para cartões que existem, referências a cargos/pessoas reais, limites."""
    if not isinstance(raw, dict):
        return None
    sectors, keys = [], set()
    for s in raw.get("sectors", [])[:20] if isinstance(raw.get("sectors"), list) else []:
        if isinstance(s, dict) and text(s.get("name"), "", 60):
            k = _slug(str(s.get("key") or s.get("name")))
            if k not in keys:
                keys.add(k)
                sectors.append({"key": k, "name": text(s.get("name"), "", 60), "color": S.color(s.get("color"), COLORS[len(sectors) % len(COLORS)]), "description": text(s.get("description"), "", 300)})
    nodes, nkeys = [], set()
    for n in raw.get("nodes", [])[:60] if isinstance(raw.get("nodes"), list) else []:
        if not isinstance(n, dict) or not text(n.get("label"), "", 80):
            continue
        key = _slug(str(n.get("key") or n.get("label")))
        if key in nkeys:
            continue
        kind = S.pick(n.get("kind"), S.NODE_KINDS, "note")
        sector = _slug(str(n.get("sector"))) if n.get("sector") else ""
        ref = n.get("ref") if isinstance(n.get("ref"), str) else ""
        if kind == "role" and ref not in role_ids:
            kind, ref = "note", ""
        if kind == "person" and ref not in user_ids:
            kind, ref = "note", ""
        if kind == "sector" and sector not in keys:
            kind = "note"
        nkeys.add(key)
        nodes.append({"key": key, "kind": kind, "label": text(n.get("label"), "", 80), "text": text(n.get("text"), "", 300), "sector": sector if sector in keys else "", "ref": ref})
    edges, seen = [], set()
    for e in raw.get("edges", [])[:120] if isinstance(raw.get("edges"), list) else []:
        if isinstance(e, dict):
            a, b = _slug(str(e.get("from"))), _slug(str(e.get("to")))
            if a in nkeys and b in nkeys and a != b and (a, b) not in seen:
                seen.add((a, b))
                edges.append({"from": a, "to": b, "kind": S.pick(e.get("kind"), S.EDGE_KINDS, "reports"), "label": text(e.get("label"), "", 60)})
    return {"sectors": sectors, "nodes": nodes, "edges": edges} if len(nodes) >= 2 else None


def draft_flow(ctx: Any, description: str, req: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Da descrição da empresa a um fluxograma proposto. Nada é aplicado: o usuário revê e usa «Aplicar ao quadro»."""
    ai = WorkAI(ctx.mgr, req)
    description = text(description, "", 8000)
    if not description:
        raise ValueError("Descreva a empresa (setores, cargos, como o trabalho passa de um para outro).")
    roles = [{"id": r["id"], "name": r["name"], "level": r.get("level")} for r in ctx.st.all("roles")]
    people = [{"id": u["id"], "name": u.get("display_name"), "role": u.get("role_id")} for u in ctx.st.all("users") if not u.get("disabled")]
    role_ids, user_ids = [r["id"] for r in roles], [p["id"] for p in people]
    base = {"description": description, "roles": roles, "people": people}

    def an_ok(o: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        secs = [{"key": _slug(str(s.get("key") or s.get("name"))), "name": text(s.get("name"), "", 60), "description": text(s.get("description"), "", 300), "positions": _clean_list(s.get("positions"), 6, 80)}
                for s in o.get("sectors", [])[:12] if isinstance(s, dict) and text(s.get("name"), "", 60)] if isinstance(o.get("sectors"), list) else []
        return {"sectors": secs, "top": _clean_list(o.get("top"), 6, 80)} if secs else None

    analysis = ai.step("flow_analyst", "flow-analysis", base, an_ok, lambda: {"sectors": [{"key": s["key"], "name": s["name"], "description": "", "positions": []} for s in fallback_flow(description)["sectors"]], "top": ["Diretoria"]})
    designed = ai.step("flow_designer", "flow-design", {**base, "analysis": analysis}, lambda o: normalize_flow(o, role_ids, user_ids), lambda: fallback_flow(description), critique=True)
    final = ai.step("flow_reviewer", "flow-review", {**base, "chart": designed}, lambda o: normalize_flow(o, role_ids, user_ids), lambda: designed, creative=False)
    # posições prévias para a tela desenhar a proposta antes de aplicar
    nodes = [{**n, "id": n["key"]} for n in final["nodes"]]
    pos = board.auto_layout(nodes, [{"from": e["from"], "to": e["to"]} for e in final["edges"]])
    for n in final["nodes"]:
        n["x"], n["y"] = pos[n["key"]]
    return {"draft": final, **ai.report()}


# ============================================================================ resumo de produtividade
def stats_for(ctx: Any, scope: str, period: str, user: str = "") -> Dict[str, Any]:
    """Números exatos (sem IA) do período: atividades por estado, pedidos por estado, atrasos, paradas e quem mais entregou."""
    now = time.time()
    span = {"day": 86400, "week": 7 * 86400, "month": 30 * 86400}.get(period, 86400)
    since = now - span
    users = ctx.st.map("users")
    who = {user} if scope == "me" and user else set(users)
    acts = [a for a in ctx.st.all("activities") if a.get("user") in who and not a.get("auto") and max(a.get("started") or 0, a.get("finished") or 0) >= since]
    reqs = [r for r in ctx.st.all("requests") if (set(r.get("to") or []) | {r.get("from")}) & who and r["_m"]["ts"] >= since - span]
    by_state: Dict[str, int] = {}
    for a in acts:
        by_state[a["state"]] = by_state.get(a["state"], 0) + 1
    req_state: Dict[str, int] = {}
    for r in reqs:
        req_state[r["status"]] = req_state.get(r["status"], 0) + 1
    today = time.strftime("%Y-%m-%d")
    overdue = [r for r in reqs if r.get("due") and r["due"] < today and r["status"] in S.REQ_OPEN]
    stale = [a for a in acts if a["state"] in ("started", "continuing") and now - float(a.get("beat") or 0) > S.BEAT_STALE]
    done: Dict[str, int] = {}
    for a in acts:
        if a["state"] == "finished":
            done[a["user"]] = done.get(a["user"], 0) + 1
    top = sorted(done.items(), key=lambda kv: -kv[1])[:5]
    secs = sum(int((a.get("finished") or now) - (a.get("started") or now)) for a in acts if a["state"] == "finished")
    return {"period": period, "scope": scope, "activities": len(acts), "by_state": by_state, "requests": len(reqs), "request_status": req_state,
            "overdue": [{"id": r["id"], "title": r.get("title"), "due": r.get("due")} for r in overdue[:10]],
            "stalled": [{"id": a["id"], "title": a.get("title"), "user": (users.get(a["user"]) or {}).get("display_name", "")} for a in stale[:10]],
            "top_finishers": [{"user": (users.get(u) or {}).get("display_name", u), "finished": n} for u, n in top], "work_minutes": round(secs / 60)}


def _fallback_digest(st: Dict[str, Any]) -> Dict[str, Any]:
    bs, rs = st["by_state"], st["request_status"]
    label = {"day": "hoje", "week": "nesta semana", "month": "neste mês"}.get(st["period"], "no período")
    parts = [f"{label.capitalize()}: {st['activities']} atividade(s) ({bs.get('finished', 0)} concluída(s), {bs.get('continuing', 0) + bs.get('started', 0)} em andamento, {bs.get('paused', 0)} pausada(s)) e {st['requests']} pedido(s)"
             f" ({rs.get('done', 0)} concluído(s), {rs.get('in_progress', 0)} em andamento, {rs.get('sent', 0) + rs.get('seen', 0)} sem resposta)."]
    if st["work_minutes"]:
        parts.append(f"Tempo em atividades concluídas: {st['work_minutes']} min.")
    risks = [f"Pedido atrasado: {o['title']} (prazo {o['due']})" for o in st["overdue"]] + [f"Atividade parada: {s['title']} ({s['user']})" for s in st["stalled"]]
    nxt = (["Cobrar os pedidos atrasados."] if st["overdue"] else []) + (["Conferir as atividades paradas e retomar ou encerrar."] if st["stalled"] else [])
    return {"summary": " ".join(parts), "highlights": [f"{t['user']}: {t['finished']} concluída(s)" for t in st["top_finishers"]], "risks": risks[:10], "next_steps": nxt}


def digest(ctx: Any, scope: str = "me", period: str = "day", req: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if scope != "me":
        ctx.need("activities.view_all")
    if period not in ("day", "week", "month"):
        period = "day"
    ai = WorkAI(ctx.mgr, req)
    st = stats_for(ctx, scope, period, ctx.uid)
    items = [{"user": (ctx.st.get("users", a["user"]) or {}).get("display_name", ""), "title": a.get("title"), "state": a.get("state")} for a in ctx.mgr.list_activities(ctx, "" if scope != "me" else ctx.uid, "", False, 40)]

    def ok(o: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        s = text(o.get("summary"), "", 2000)
        return {"summary": s, "highlights": _clean_list(o.get("highlights"), 8, 240), "risks": _clean_list(o.get("risks"), 8, 240), "next_steps": _clean_list(o.get("next_steps"), 5, 240)} if s else None

    out = ai.step("digest", "digest", {"scope": scope, "period": period, "stats": st, "items": items}, ok, lambda: _fallback_digest(st), creative=False)
    return {**out, "stats": st, **ai.report()}
