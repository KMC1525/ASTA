"""Computer Use sem IA: o **fallback determinístico** (princípio 7 — a entrega nunca depende só do modelo).

Quando o provedor é o Demo (ou a IA não devolve um JSON utilizável), este módulo entende, por regras, os pedidos mais simples em português e inglês e monta direto uma lista de ações do
catálogo de ferramentas: criar pastas e arquivos, organizar uma pasta, abrir um programa, jogo ou site e pesquisar na web. O resto precisa de um modelo de IA, e a tarefa diz isso com clareza.
"""
from __future__ import annotations

import os
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

_THEN = re.compile(r"\s*(?:;|\s+e\s+(?:depois|então|entao)\s+|\s+(?:depois|então|entao)\s+|\s+and\s+then\s+|\s+then\s+|\.\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ]))\s*", re.I)
_Q = r"[“\"'«]?"
_QE = r"[”\"'»]?"


def _plain(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _fold(s: str) -> str:
    """Minúsculas sem acento, **preservando o tamanho** (para achar com regex no texto sem acento e recortar no original)."""
    out = []
    for c in s:
        d = unicodedata.normalize("NFKD", c)
        out.append(d[0] if d and d[0].isascii() else c)
    return "".join(out).lower()


def lang_of(text: str, pref: str = "auto") -> str:
    """«pt» ou «en»: o idioma da configuração, ou — em automático — o do pedido."""
    p = str(pref or "auto").lower()
    if p.startswith("pt"):
        return "pt"
    if p.startswith("en"):
        return "en"
    low = " " + _plain(text) + " "
    pt = sum(1 for w in (" o ", " a ", " os ", " as ", " de ", " do ", " da ", " para ", " com ", " um ", " uma ", " que ", " em ", " na ", " no ", " por ", " pasta", " abra", " crie", " organize", " arquivo", "ção", "cao ") if w in low)
    en = sum(1 for w in (" the ", " and ", " to ", " of ", " with ", " a ", " an ", " in ", " on ", " for ", " folder", " open", " create", " organize", " file") if w in low)
    return "pt" if pt >= en else "en"


def known_folders() -> Dict[str, Path]:
    """Pastas comuns do usuário que existem (Desktop, Documentos, Downloads, Imagens, Músicas, Vídeos)."""
    home = Path.home()
    out: Dict[str, Path] = {"home": home}
    cands = {"desktop": ("Desktop", "Área de Trabalho", "Área de trabalho"), "documents": ("Documents", "Documentos"), "downloads": ("Downloads", "Transferências"),
             "pictures": ("Pictures", "Imagens", "Fotos"), "music": ("Music", "Músicas", "Música"), "videos": ("Videos", "Vídeos", "Movies", "Filmes")}
    xdg = {"desktop": "DESKTOP", "documents": "DOCUMENTS", "downloads": "DOWNLOAD", "pictures": "PICTURES", "music": "MUSIC", "videos": "VIDEOS"}
    for key, names in cands.items():
        p = None
        if os.name == "posix" and not os.environ.get("ASTA_ANDROID"):
            try:
                r = subprocess.run(["xdg-user-dir", xdg[key]], capture_output=True, timeout=2, stdin=subprocess.DEVNULL)
                cand = Path(r.stdout.decode().strip()) if r.returncode == 0 and r.stdout.strip() else None
                if cand and cand.is_dir() and cand != home:
                    p = cand
            except (OSError, subprocess.SubprocessError):
                p = None
        if p is None:
            p = next((home / n for n in names if (home / n).is_dir()), None)
        if p is not None:
            out[key] = p
    return out


_WHERE = {
    "desktop": ("desktop", "area de trabalho", "ambiente de trabalho"), "documents": ("documents", "documentos", "meus documentos"), "downloads": ("downloads", "download", "transferencias"),
    "pictures": ("pictures", "imagens", "fotos", "pictures folder"), "music": ("music", "musicas", "musica"), "videos": ("videos", "filmes", "movies"),
    "home": ("home", "pasta pessoal", "pasta do usuario", "pasta inicial", "minha pasta"),
}


def resolve_where(where: str, folders: Dict[str, Path]) -> Optional[Path]:
    w = _plain(where).strip(" .,:;\"'«»“”")
    w = re.sub(r"^(?:a |o |as |os |the |minha |meu |my |na |no |em |in |on |dentro d[aoe] |inside )+", "", w)
    w = re.sub(r"^(?:pasta |folder |diretorio )+", "", w) if not re.match(r"^(pasta pessoal|pasta do|pasta inicial)", w) else w
    for key, names in _WHERE.items():
        if w in names:
            return folders.get(key) or folders["home"]
    raw = where.strip().strip("\"'“”«»").rstrip(".")
    if raw.startswith("~") or re.match(r"^([a-zA-Z]:[\\/]|/)", raw):
        return Path(raw).expanduser()
    # "pasta Fotos em documentos" → subpasta dentro de uma conhecida
    m = re.match(r"^(.+?)\s+(?:em|na|no|in|on|inside|dentro d[aoe])\s+(.+)$", raw, re.I)
    if m:
        base = resolve_where(m.group(2), folders)
        if base:
            return base / m.group(1).strip("\"'“”«» ")
    return None


def _clean_name(n: str) -> str:
    n = n.strip().strip("\"'“”«»").strip(" .,:;")
    return re.sub(r'[<>:"|?*\x00-\x1f]', "-", n).replace("/", "-").replace("\\", "-")[:120]


def _split_names(raw: str) -> List[str]:
    parts = re.split(r"\s*(?:,|\s+e\s+|\s+and\s+|\s*&\s*)\s*", raw.strip())
    return [_clean_name(p) for p in parts if _clean_name(p)]


def _act(step: str, tool: str, **args: Any) -> Dict[str, Any]:
    return {"step": step, "tool": tool, "args": args}


def _clause(text: str, folders: Dict[str, Path], idx: int) -> Optional[Dict[str, Any]]:
    """Uma frase do pedido → {"title": str, "actions": [...]} ou None se não entendi."""
    s = text.strip()
    low = _fold(s)
    sid = f"s{idx}"
    # --- criar pasta(s)
    m = re.search(r"\b(?:cri(?:e|ar|a)|faca|fazer|make|create|new|nova)\b\s+(?:uma?\s+|as\s+|os\s+|a\s+|the\s+|an?\s+)?(?:novas?\s+|new\s+)?(?:pastas?|folders?|diretorios?|directories)\b\s*(?:chamad[ao]s?|com o nome|nomead[ao]s?|named|called)?\s*(.*)$", low)
    if m:
        tail = s[m.start(1):] if m.group(1) else ""
        where_part = None
        wm = re.search(r"\s+(?:em|na|no|dentro d[aoe]|in|inside|on)\s+(.+)$", tail, re.I)
        names_raw = tail
        if wm:
            where_part, names_raw = wm.group(1), tail[:wm.start()]
        names = _split_names(names_raw)
        base = resolve_where(where_part, folders) if where_part else None
        if where_part and base is None:
            return None
        base = base or folders.get("desktop") or folders["home"]
        if not names:
            return None
        return {"title": ("Criar a pasta " if len(names) == 1 else "Criar as pastas ") + ", ".join(names), "actions": [_act(sid, "make_dir", path=str(base / n)) for n in names[:20]]}
    # --- criar arquivo com conteúdo
    m = re.search(r"\b(?:cri(?:e|ar|a)|crie|make|create|salve|save)\b\s+(?:um\s+|a\s+|an?\s+)?(?:novo\s+|new\s+)?(?:arquivo|file)(?:\s+de\s+texto|\s+text)?\s+(?:chamado\s+|named\s+|called\s+)?(\S+)\s+(?:com|contendo|with|containing)\s+(.+)$", s, re.I | re.S)
    if m:
        name, content = _clean_name(m.group(1)), m.group(2).strip().strip("\"'“”«»")
        if not name:
            return None
        where = None
        wm = re.search(r"\s+(?:em|na|no|in|inside|on)\s+(desktop|documentos|documents|downloads|area de trabalho|área de trabalho)\s*$", content, re.I)
        if wm:
            where, content = wm.group(1), content[:wm.start()].strip()
        base = (resolve_where(where, folders) if where else None) or folders.get("desktop") or folders["home"]
        if "." not in name:
            name += ".txt"
        return {"title": f"Criar o arquivo {name}", "actions": [_act(sid, "create_file", path=str(base / name), content=content)]}
    # --- organizar
    m = re.search(r"\b(?:organiz(?:e|ar|a)|arrum(?:e|ar|a)|organize|sort|tidy(?: up)?|clean up)\b\s+(?:a\s+|o\s+|os\s+arquivos\s+d[aoe]\s+|as\s+|the\s+|my\s+|minha\s+|meu\s+)*(?:pasta\s+|folder\s+|diretorio\s+)?(.*)$", low)
    if m and m.group(1):
        tail = s[m.start(1):]
        by = "type"
        bm = re.search(r"\s+(?:por|by|pela|pelo)\s+(tipo|type|extens[aã]o|extension|data|date|nome|name)\s*$", tail, re.I)
        if bm:
            word = _plain(bm.group(1))
            by = "extension" if word.startswith("exten") else "date" if word in ("data", "date") else "name" if word in ("nome", "name") else "type"
            tail = tail[:bm.start()]
        tail = re.sub(r"\s+(?:folder|pasta|directory|diretorio)\s*$", "", tail, flags=re.I)
        base = resolve_where(tail, folders)
        if base is None:
            return None
        return {"title": f"Organizar a pasta {base.name or base}", "actions": [_act(sid, "organize_folder", path=str(base), by=by)]}
    # --- abrir site
    m = re.search(r"(https?://[^\s]+)", s)
    if m and re.search(r"\b(?:abr(?:a|ir|e)|acess(?:e|ar)|visit(?:e|ar)|open|go to|visit|navegu?e)\b", low):
        return {"title": "Abrir o site " + m.group(1), "actions": [_act(sid, "open_url", url=m.group(1).rstrip(".,)"))]}
    # --- pesquisar
    m = re.search(r"\b(?:pesquis(?:e|ar|a)|search(?: for| the web for)?|procure|busque|buscar|look up|google)\b\s+(?:por\s+|sobre\s+|na web\s+|na internet\s+|online\s+|for\s+)?(.+)$", s, re.I)
    if m and len(m.group(1).strip()) > 1:
        q = m.group(1).strip().strip("\"'“”«»")
        return {"title": f"Pesquisar «{q}»", "actions": [_act(sid, "search_web", query=q)]}
    # --- abrir jogo
    m = re.search(r"\b(?:abr(?:a|ir|e)|inicie|iniciar|jog(?:ar|ue)|play|launch|start|open|run)\b\s+(?:o\s+|a\s+|the\s+)?(?:jogo|game)\s+(.+)$", s, re.I)
    if m:
        name = m.group(1).strip().strip("\"'“”«»")
        return {"title": f"Abrir o jogo {name}", "actions": [_act(sid, "launch_game", game=name)]}
    m = re.search(r"\b(?:jog(?:ar|ue)|play)\b\s+(?:o\s+|a\s+)?(.+)$", s, re.I)
    if m and len(m.group(1).split()) <= 5:
        return {"title": f"Abrir o jogo {m.group(1).strip()}", "actions": [_act(sid, "launch_game", game=m.group(1).strip().strip("\"'“”«»"))]}
    # --- abrir programa
    m = re.search(r"\b(?:abr(?:a|ir|e)|inicie|iniciar|execute|executar|rode|launch|start|open|run)\b\s+(?:o\s+|a\s+|the\s+|o programa\s+|the app\s+|app\s+|programa\s+)*(.+)$", s, re.I)
    if m:
        name = m.group(1).strip().strip("\"'“”«»").rstrip(".")
        if name and len(name.split()) <= 4:
            return {"title": f"Abrir {name}", "actions": [_act(sid, "open_app", name=name)]}
    return None


def build_script(goal: str, folders: Optional[Dict[str, Path]] = None) -> Optional[Dict[str, Any]]:
    """Pedido → {"summary", "kind", "steps": [{"id","title"}], "actions": [{"step","tool","args"}]} — ou None quando as regras não entendem (aí só a IA resolve)."""
    folders = folders or known_folders()
    clauses = [c for c in _THEN.split(str(goal or "").strip()) if c and c.strip()]
    if not clauses or len(clauses) > 8:
        return None
    steps, actions, kinds = [], [], set()
    for i, c in enumerate(clauses, 1):
        got = _clause(c, folders, i)
        if not got:
            return None
        steps.append({"id": f"s{i}", "title": got["title"], "tools": sorted({a["tool"] for a in got["actions"]}), "done_when": ""})
        actions += got["actions"]
        for a in got["actions"]:
            kinds.add({"launch_game": "games", "open_app": "apps", "search_web": "research", "open_url": "apps"}.get(a["tool"], "files"))
    kind = kinds.pop() if len(kinds) == 1 else "mixed"
    return {"summary": str(goal).strip()[:200], "kind": kind, "steps": steps, "actions": actions, "needs_gui": False}


NEEDS_AI_PT = ("Sem um modelo de IA eu só entendo pedidos simples (criar pasta ou arquivo, organizar uma pasta, abrir um programa, jogo ou site, pesquisar na web). "
               "Escolha um modelo no seletor do Chat (ou em Configuração → Provedores) e tente de novo.")
NEEDS_AI_EN = ("Without an AI model I only understand simple requests (create a folder or file, organize a folder, open a program, game or site, search the web). "
               "Pick a model in the Chat model selector (or Configuration → Providers) and try again.")
