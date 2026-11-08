"""Navegador de mídia do Studio (v0.17): tudo que o ASTA já tem e pode entrar na timeline — arquivos dos Canvas, de outros projetos do Studio e exportações — com busca e importação.

Nada é movido: importar **copia** o arquivo para o projeto (o original continua onde estava).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..util import text

KINDS = ("image", "video", "audio")
SOURCES = ("canvas", "studio", "export")


def _match(q: str, *fields: str) -> bool:
    q = q.lower().strip()
    return not q or any(q in (f or "").lower() for f in fields)


def browse(store: Any, query: str = "", kind: str = "", source: str = "", exclude_project: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    """Itens [{source, ref, kind, name, dur, w, h, where, url, thumb}] mais recentes primeiro. `ref` é o que `resolve` precisa para importar."""
    items: List[Dict[str, Any]] = []
    if source in ("", "canvas"):
        for c in store.canvases.list():
            cv = store.canvases.get(c["id"])
            for a in (cv or {}).get("assets", []):
                if a["kind"] in KINDS and (not kind or a["kind"] == kind) and _match(query, a.get("name", ""), a.get("prompt", ""), c["name"]):
                    items.append({"source": "canvas", "ref": f"{c['id']}/{a['id']}", "kind": a["kind"], "name": a.get("name") or a["file"], "dur": a.get("dur", 0), "w": a.get("w", 0), "h": a.get("h", 0),
                                  "where": f"Canvas · {c['name']}", "created": a.get("created", ""), "url": f"/api/canvases/{c['id']}/assets/{a['file']}"})
    if source in ("", "studio", "export"):
        for s in store.studio.list():
            if s["id"] == exclude_project:
                continue
            p = store.studio.get(s["id"])
            if not p:
                continue
            if source in ("", "studio"):
                for a in p["assets"]:
                    if a["kind"] in KINDS and (not kind or a["kind"] == kind) and _match(query, a.get("name", ""), a.get("prompt", ""), p["name"]):
                        items.append({"source": "studio", "ref": f"{p['id']}/{a['id']}", "kind": a["kind"], "name": a.get("name") or a["file"], "dur": a.get("dur", 0), "w": a.get("w", 0), "h": a.get("h", 0),
                                      "where": f"Studio · {p['name']}", "created": a.get("created", ""), "url": f"/api/studio/projects/{p['id']}/media/{a['file']}"})
            if source in ("", "export") and kind in ("", "video", "audio"):
                for e in p["episodes"]:
                    for x in e.get("exports", []):
                        k = "audio" if x.get("mode") == "audio" else "video"
                        if (not kind or k == kind) and _match(query, x.get("file", ""), p["name"]):
                            items.append({"source": "export", "ref": f"{p['id']}/{x['file']}", "kind": k, "name": x["file"], "dur": x.get("dur", 0), "w": 0, "h": 0,
                                          "where": f"Exportação · {p['name']}", "created": x.get("created", ""), "url": f"/api/studio/projects/{p['id']}/exports/{x['file']}"})
    items.sort(key=lambda i: i.get("created", ""), reverse=True)
    return items[:limit]


def resolve(store: Any, source: str, ref: str) -> Optional[Dict[str, Any]]:
    """O arquivo de um item do navegador: {path, kind, name, mime, ext}. None se não existe (ou a referência é inválida)."""
    if source not in SOURCES or "/" not in ref:
        return None
    a_id, _, b_id = ref.partition("/")
    if source == "canvas":
        cv = store.canvases.get(a_id)
        a = next((x for x in (cv or {}).get("assets", []) if x["id"] == b_id), None)
        path = store.canvases.asset_path(a_id, a["file"]) if a else None
        return {"path": path, "kind": a["kind"], "name": a["name"], "mime": a.get("mime", ""), "ext": Path(a["file"]).suffix.lstrip(".")} if a and path else None
    p = store.studio.get(a_id)
    if not p:
        return None
    if source == "studio":
        a = next((x for x in p["assets"] if x["id"] == b_id), None)
        path = store.studio.media_path(a_id, a["file"]) if a else None
        return {"path": path, "kind": a["kind"], "name": a["name"], "mime": a.get("mime", ""), "ext": Path(a["file"]).suffix.lstrip(".")} if a and path else None
    path = store.studio.export_path(a_id, text(b_id, "", 200))
    if not path:
        return None
    audio = path.suffix.lower() in (".m4a", ".mp3", ".wav")
    return {"path": path, "kind": "audio" if audio else "video", "name": path.name, "mime": "", "ext": path.suffix.lstrip(".")}


def import_item(store: Any, pid: str, source: str, ref: str) -> Optional[Dict[str, Any]]:
    """Copia o item para os ativos do projeto `pid`; devolve o registro do ativo (ou None)."""
    r = resolve(store, source, ref)
    if not r:
        return None
    return store.studio.add_asset_file(pid, r["path"], r["ext"] or "bin", r["kind"], name=r["name"], mime=r["mime"], source=source)
