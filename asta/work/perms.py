"""Permissões do Work: cargos (papéis) customizados, ajustes por função e por pessoa.

Permissão efetiva = permissões do cargo ∪ concessões da(s) função(ões) − negações da(s) função(ões) ∪ concessões da pessoa − negações da pessoa.
O cargo `admin` tem tudo (`*`) e não pode ser enfraquecido; sempre existe pelo menos uma pessoa administradora ativa.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set

#: catálogo fechado: chave → (grupo, descrição em português — a tela traduz)
CATALOG: Dict[str, tuple] = {
    "org.manage": ("Organização", "Editar a organização, o quadro de máquinas e as redes"),
    "network.manage": ("Organização", "Gerenciar máquinas, redes, convites e sincronização"),
    "backup.manage": ("Organização", "Escolher as máquinas de backup e restaurar dados"),
    "users.manage": ("Pessoas", "Criar, editar e desativar pessoas e redefinir senhas"),
    "roles.manage": ("Pessoas", "Criar e editar cargos, funções e permissões"),
    "flow.view": ("Fluxograma", "Ver o quadro com cargos e setores"),
    "flow.edit": ("Fluxograma", "Editar o quadro (cargos, setores, ligações)"),
    "folders.manage": ("Arquivos", "Criar setores/pastas e definir quem acessa"),
    "files.view": ("Arquivos", "Ver e baixar arquivos dos setores a que tem acesso"),
    "files.upload": ("Arquivos", "Enviar arquivos de qualquer formato"),
    "files.delete": ("Arquivos", "Apagar arquivos de outras pessoas"),
    "requests.send": ("Pedidos", "Enviar pedidos (texto, arquivos ou os dois) a outras pessoas"),
    "requests.view_all": ("Pedidos", "Ver todos os pedidos da organização"),
    "requests.reply": ("Pedidos", "Responder aos pedidos que recebe"),
    "activities.view_all": ("Atividades", "Ver as atividades de todas as pessoas"),
    "notifications.broadcast": ("Notificações", "Enviar avisos a pessoas, cargos ou a todos"),
    "ai.use": ("IA", "Usar a IA do Work (rascunho de pedidos, fluxograma, resumos)"),
}
ALL = tuple(CATALOG)

BUILTIN_ROLES: List[Dict[str, Any]] = [
    {"id": "admin", "name": "Administrador", "level": 100, "color": "#e5484d", "perms": ["*"], "builtin": True,
     "description": "Controla tudo: pessoas, cargos, redes, máquinas e backups."},
    {"id": "manager", "name": "Gerente", "level": 50, "color": "#f5a524", "builtin": True,
     "perms": ["flow.view", "flow.edit", "folders.manage", "files.view", "files.upload", "files.delete", "requests.send", "requests.view_all", "requests.reply",
               "activities.view_all", "notifications.broadcast", "ai.use"],
     "description": "Coordena setores: envia pedidos, vê as atividades da equipe e organiza os arquivos."},
    {"id": "worker", "name": "Trabalhador", "level": 10, "color": "#3e9bff", "builtin": True,
     "perms": ["flow.view", "files.view", "files.upload", "requests.reply", "ai.use"],
     "description": "Recebe pedidos, registra atividades e compartilha arquivos."},
]


def valid_perm(p: Any) -> bool:
    return isinstance(p, str) and (p == "*" or p in CATALOG)


def clean_perms(items: Any) -> List[str]:
    out: List[str] = []
    for p in items if isinstance(items, (list, tuple, set)) else []:
        if valid_perm(p) and p not in out:
            out.append(p)
    return out


def effective(user: Dict[str, Any], roles: Dict[str, Dict[str, Any]], functions: Dict[str, Dict[str, Any]]) -> Set[str]:
    """O conjunto de permissões da pessoa. Pessoa desativada não tem nenhuma."""
    if not user or user.get("disabled"):
        return set()
    role = roles.get(user.get("role_id") or "") or {}
    perms: Set[str] = set(role.get("perms") or [])
    if "*" in perms:
        return set(ALL) | {"*"}
    fns = [functions[f] for f in user.get("function_ids") or [] if f in functions]
    for f in fns:
        perms |= set(f.get("grant") or [])
    for f in fns:
        perms -= set(f.get("deny") or [])
    perms |= set(user.get("grant") or [])
    perms -= set(user.get("deny") or [])
    return {p for p in perms if p in CATALOG}


def can(perms: Iterable[str], perm: str) -> bool:
    ps = perms if isinstance(perms, (set, frozenset)) else set(perms)
    return "*" in ps or perm in ps


def level_of(user: Dict[str, Any], roles: Dict[str, Dict[str, Any]]) -> int:
    return int((roles.get(user.get("role_id") or "") or {}).get("level") or 0)


def folder_visible(folder: Dict[str, Any], user: Dict[str, Any], perms: Set[str]) -> bool:
    """Quem enxerga um setor/pasta: admin sempre; `all` = todos com `files.view`; `restricted` = só as pessoas, cargos e funções listados."""
    if "*" in perms:
        return True
    if not can(perms, "files.view"):
        return False
    acc = folder.get("access") or {}
    if acc.get("mode") != "restricted":
        return True
    if user.get("id") in (acc.get("users") or []) or user.get("role_id") in (acc.get("roles") or []):
        return True
    return bool(set(user.get("function_ids") or []) & set(acc.get("functions") or []))
