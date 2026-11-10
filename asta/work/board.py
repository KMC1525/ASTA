"""O quadro branco do Work (fluxograma da empresa): layout automático e caminho entre duas pessoas.

O quadro é feito de documentos pequenos — `nodes` (cargos, pessoas, setores, notas, agentes de IA) e `edges` (ligações: reporta a / repassa para / aprova) — mais as `folders`
(setores), que aparecem como caixas e guardam os arquivos compartilhados. Aqui ficam as contas puras (sem rede nem disco), usadas pela tela, pela IA e pelos testes.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, Iterable, List, Optional, Tuple

NODE_W, NODE_H = 190, 70
GAP_X, GAP_Y = 40, 90


def depths(nodes: Iterable[Dict[str, Any]], edges: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """Profundidade de cada nó seguindo as ligações (`from` → `to`) a partir das raízes (nós sem ligação de entrada). Ciclos não travam."""
    ids = [n["id"] for n in nodes]
    out: Dict[str, List[str]] = {i: [] for i in ids}
    indeg: Dict[str, int] = {i: 0 for i in ids}
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a in out and b in out and a != b:
            out[a].append(b)
            indeg[b] += 1
    depth: Dict[str, int] = {}
    q = deque(i for i in ids if indeg[i] == 0)
    for i in q:
        depth[i] = 0
    while q:
        cur = q.popleft()
        for nxt in out[cur]:
            if nxt not in depth:
                depth[nxt] = depth[cur] + 1
                q.append(nxt)
    for i in ids:   # só em ciclo (ninguém é raiz): vai para o nível 0
        depth.setdefault(i, 0)
    return depth


def auto_layout(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], origin: Tuple[float, float] = (0.0, 0.0)) -> Dict[str, Tuple[float, float]]:
    """Posições (x, y) em camadas: o topo da hierarquia em cima, cada nível numa linha, cada linha centrada. Determinístico."""
    d = depths(nodes, edges)
    rows: Dict[int, List[str]] = {}
    for n in sorted(nodes, key=lambda n: (d[n["id"]], str(n.get("label", "")).lower(), n["id"])):
        rows.setdefault(d[n["id"]], []).append(n["id"])
    widest = max((len(r) for r in rows.values()), default=1)
    full = widest * (NODE_W + GAP_X)
    pos: Dict[str, Tuple[float, float]] = {}
    for level, row in rows.items():
        start = origin[0] + (full - len(row) * (NODE_W + GAP_X)) / 2
        for i, nid in enumerate(row):
            pos[nid] = (round(start + i * (NODE_W + GAP_X), 1), round(origin[1] + level * (NODE_H + GAP_Y), 1))
    return pos


def anchor_nodes(st_users: Dict[str, Dict[str, Any]], nodes: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Para cada pessoa, os nós do quadro que a representam: o nó dela e, na falta, o nó do cargo dela."""
    by_person: Dict[str, List[str]] = {}
    by_role: Dict[str, List[str]] = {}
    for n in nodes:
        if n.get("kind") == "person" and n.get("ref"):
            by_person.setdefault(n["ref"], []).append(n["id"])
        elif n.get("kind") == "role" and n.get("ref"):
            by_role.setdefault(n["ref"], []).append(n["id"])
    return {uid: by_person.get(uid) or by_role.get(u.get("role_id") or "", []) for uid, u in st_users.items()}


def find_path(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], starts: List[str], goals: List[str]) -> List[str]:
    """Menor caminho (lista de ids de nós) entre qualquer nó de `starts` e qualquer de `goals`, andando pelas ligações nos dois sentidos. Vazio se não há caminho."""
    if not starts or not goals:
        return []
    adj: Dict[str, List[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a in adj and b in adj:
            adj[a].append(b)
            adj[b].append(a)
    goal = set(goals)
    prev: Dict[str, Optional[str]] = {s: None for s in starts if s in adj}
    q = deque(prev)
    while q:
        cur = q.popleft()
        if cur in goal:
            path = [cur]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])  # type: ignore[arg-type]
            return path[::-1]
        for nxt in sorted(adj[cur]):
            if nxt not in prev:
                prev[nxt] = cur
                q.append(nxt)
    return []


def template(kind: str, roles: List[Dict[str, Any]], users: List[Dict[str, Any]], sectors: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Quadro inicial determinístico (a base quando a IA não está disponível): administradores no topo → gerentes → trabalhadores, cada pessoa ligada a um superior do nível acima.
    Devolve `{nodes: [...], edges: [...]}` com ids provisórios `t1…`; as posições vêm de `auto_layout`."""
    lvl = {r["id"]: int(r.get("level") or 0) for r in roles}
    people = sorted([u for u in users if not u.get("disabled")], key=lambda u: (-lvl.get(u.get("role_id") or "", 0), (u.get("display_name") or "").lower()))
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    tiers: Dict[int, List[str]] = {}
    for i, u in enumerate(people, 1):
        nid = f"t{i}"
        nodes.append({"id": nid, "kind": "person", "ref": u["id"], "label": u.get("display_name") or u.get("username", ""), "text": u.get("title", "")})
        tiers.setdefault(lvl.get(u.get("role_id") or "", 0), []).append(nid)
    order = sorted(tiers, reverse=True)
    for hi, lo in zip(order, order[1:]):
        for j, nid in enumerate(tiers[lo]):
            edges.append({"from": tiers[hi][j % len(tiers[hi])], "to": nid, "kind": "reports", "label": ""})
    return {"nodes": nodes, "edges": edges}
