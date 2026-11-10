"""Formato dos documentos do Work: validação de tudo que chega do navegador, de outra máquina ou da IA (entrada não confiável).

Todo documento é um JSON pequeno `{id, …campos, _m: {rev, ts, by, origin, deleted}}` numa coleção (ver store.py). Aqui ficam só os `norm_*`: recebem qualquer coisa e devolvem um dict válido.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..util import num, text
from . import perms as P

SCHEMA = "asta.work.v1"
COLLECTIONS = ("meta", "users", "roles", "functions", "folders", "nodes", "edges", "requests", "activities", "notifications", "files", "machines", "presence")

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")
ID_RE = re.compile(r"^[\w.-]{1,80}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

AUTH_MODES = ("none", "local", "machine", "synced")   # sem senha · só nesta máquina · guardada em outra máquina · replicada em todas as máquinas
PRIORITIES = ("low", "normal", "high", "urgent")
REQ_STATUS = ("sent", "seen", "accepted", "in_progress", "done", "rejected", "cancelled")
REQ_OPEN = ("sent", "seen", "accepted", "in_progress")
ACT_STATES = ("started", "continuing", "paused", "finished", "cancelled")
NODE_KINDS = ("person", "role", "sector", "note", "ai")
EDGE_KINDS = ("reports", "handoff", "approval")
HOLD = ("needed", "all")
BEAT_STALE = 300   # segundos sem sinal para uma atividade «continuando» ser marcada como parada


def valid_id(v: Any) -> bool:
    return isinstance(v, str) and bool(ID_RE.match(v))


def pick(v: Any, allowed: tuple, default: str) -> str:
    return v if isinstance(v, str) and v in allowed else default


def color(v: Any, default: str = "#3e9bff") -> str:
    return v if isinstance(v, str) and COLOR_RE.match(v) else default


def id_list(v: Any, limit: int = 200) -> List[str]:
    out: List[str] = []
    for x in v if isinstance(v, list) else []:
        if valid_id(x) and x not in out:
            out.append(x)
        if len(out) >= limit:
            break
    return out


def norm_username(v: Any) -> str:
    s = str(v or "").strip().lower().lstrip("@")
    return s if USERNAME_RE.match(s) else ""


def norm_user(raw: Any, old: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Perfil: nome de usuário, cargo (`role_id`), função(ões), bio… Campos ausentes mantêm o valor de `old`."""
    r = raw if isinstance(raw, dict) else {}
    o = old or {}

    def g(k: str, d: Any = "") -> Any:
        return r[k] if k in r else o.get(k, d)

    return {
        "username": norm_username(g("username")) or o.get("username", ""),
        "display_name": text(g("display_name"), "", 80) or text(g("username"), "", 80),
        "role_id": g("role_id") if valid_id(g("role_id")) else (o.get("role_id") or "worker"),
        "title": text(g("title"), "", 80),            # cargo escrito livremente («Designer pleno»); o `role_id` é o que dá as permissões
        "function_ids": id_list(g("function_ids", []), 12),
        "bio": text(g("bio"), "", 1200),
        "avatar_color": color(g("avatar_color"), o.get("avatar_color") or "#3e9bff"),
        "email": text(g("email"), "", 120),
        "grant": P.clean_perms(g("grant", [])), "deny": P.clean_perms(g("deny", [])),
        "disabled": bool(g("disabled", False)),
        "auth": norm_auth(g("auth", {}), o.get("auth")),
        "backup_machines": id_list(g("backup_machines", []), 16),
        "home_machines": id_list(g("home_machines", []), 64),
    }


def norm_auth(raw: Any, old: Any = None) -> Dict[str, Any]:
    r = raw if isinstance(raw, dict) else {}
    o = old if isinstance(old, dict) else {}
    mode = pick(r.get("mode", o.get("mode")), AUTH_MODES, "none")
    return {"mode": mode, "holder": r.get("holder", o.get("holder")) if mode == "machine" and valid_id(r.get("holder", o.get("holder"))) else "",
            "set": bool(r.get("set", o.get("set", False))) and mode != "none"}


def norm_role(raw: Any, old: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    r = raw if isinstance(raw, dict) else {}
    o = old or {}
    builtin = bool(o.get("builtin"))
    perms = P.clean_perms(r.get("perms", o.get("perms", [])))
    if o.get("id") == "admin":
        perms = ["*"]
    return {"name": text(r.get("name", o.get("name")), "", 60) or o.get("name") or "Cargo", "description": text(r.get("description", o.get("description")), "", 300),
            "level": int(num(r.get("level", o.get("level")), 20, 0, 99 if o.get("id") != "admin" else 100)), "color": color(r.get("color", o.get("color")), "#8b8b94"),
            "perms": perms, "builtin": builtin}


def norm_function(raw: Any, old: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    r = raw if isinstance(raw, dict) else {}
    o = old or {}
    return {"name": text(r.get("name", o.get("name")), "", 60) or "Função", "description": text(r.get("description", o.get("description")), "", 300),
            "grant": P.clean_perms(r.get("grant", o.get("grant", []))), "deny": P.clean_perms(r.get("deny", o.get("deny", []))),
            "color": color(r.get("color", o.get("color")), "#a78bfa")}


def norm_access(raw: Any) -> Dict[str, Any]:
    r = raw if isinstance(raw, dict) else {}
    return {"mode": "restricted" if r.get("mode") == "restricted" else "all", "users": id_list(r.get("users")), "roles": id_list(r.get("roles")), "functions": id_list(r.get("functions"))}


def norm_folder(raw: Any, old: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Setor/pasta: aparece no quadro como uma caixa (x, y, w, h) e guarda os arquivos compartilhados dele."""
    r = raw if isinstance(raw, dict) else {}
    o = old or {}

    def g(k: str, d: Any = None) -> Any:
        return r[k] if k in r else o.get(k, d)

    parent = g("parent", "")
    return {"name": text(g("name"), "", 80) or "Setor", "parent": parent if valid_id(parent) else "", "color": color(g("color"), "#3e9bff"),
            "x": num(g("x"), 0, -20000, 20000), "y": num(g("y"), 0, -20000, 20000), "w": num(g("w"), 360, 120, 4000), "h": num(g("h"), 240, 90, 4000),
            "access": norm_access(g("access", {})), "description": text(g("description"), "", 400)}


def norm_node(raw: Any, old: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    r = raw if isinstance(raw, dict) else {}
    o = old or {}

    def g(k: str, d: Any = None) -> Any:
        return r[k] if k in r else o.get(k, d)

    return {"kind": pick(g("kind"), NODE_KINDS, "note"), "ref": g("ref") if valid_id(g("ref")) else "", "label": text(g("label"), "", 80), "text": text(g("text"), "", 600),
            "x": num(g("x"), 0, -20000, 20000), "y": num(g("y"), 0, -20000, 20000), "color": color(g("color"), "#3e9bff"),
            "parent": g("parent") if valid_id(g("parent")) else ""}


def norm_edge(raw: Any, old: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    r = raw if isinstance(raw, dict) else {}
    o = old or {}
    src, dst = r.get("from", o.get("from")), r.get("to", o.get("to"))
    return {"from": src if valid_id(src) else "", "to": dst if valid_id(dst) else "", "label": text(r.get("label", o.get("label")), "", 60),
            "kind": pick(r.get("kind", o.get("kind")), EDGE_KINDS, "reports")}


def norm_machine(raw: Any, old: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    r = raw if isinstance(raw, dict) else {}
    o = old or {}
    addrs = [text(a, "", 120) for a in (r.get("addrs", o.get("addrs", [])) if isinstance(r.get("addrs", o.get("addrs", [])), list) else [])]
    return {"name": text(r.get("name", o.get("name")), "", 60) or "Máquina", "os": text(r.get("os", o.get("os")), "", 40), "addrs": [a for a in addrs if a][:8],
            "backup": bool(r.get("backup", o.get("backup", False))), "hold": pick(r.get("hold", o.get("hold")), HOLD, "needed"),
            "revoked": bool(r.get("revoked", o.get("revoked", False))), "tailnet": text(r.get("tailnet", o.get("tailnet")), "", 120)}


def norm_message(raw: Any, by: str, ts: float, kind: str = "msg") -> Dict[str, Any]:
    r = raw if isinstance(raw, dict) else {}
    return {"id": "m" + format(int(ts * 1000), "x") + by[-4:], "by": by, "ts": ts, "kind": kind, "text": text(r.get("text"), "", 8000), "attachments": id_list(r.get("attachments"), 30)}


def dedupe(items: List[str]) -> List[str]:
    return list(dict.fromkeys(items))
