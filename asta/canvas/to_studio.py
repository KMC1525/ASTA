"""Do Canvas para o Studio (v0.17): leva o fluxo (ou só alguns nós) para a timeline de um projeto do Studio, para continuar a produção criativa nela.

* Se o fluxo tem um nó **Editor** com clipes, a montagem dele vira a timeline (camadas, tempos, volumes, textos…).
* Senão, as saídas dos nós entram **na ordem do fluxo**: imagens e vídeos em sequência na V1, vozes na A1 e sons/músicas na A2, a partir do início.
* Os arquivos são **copiados** para o projeto (o Canvas não muda). Num projeto que já existe, o material entra **depois do fim** da timeline (nada é sobrescrito).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..util import text
from ..studio import schema as S

IMAGE_SECONDS = 4.0
CLIP_KEYS = ("start", "dur", "in", "speed", "mute", "volume", "fade_in", "fade_out", "opacity", "fit", "x", "y", "scale", "text", "size", "color", "bg", "pos")


def _aspect_of(assets: List[Dict[str, Any]], fallback: str = "16:9") -> str:
    for a in assets:
        w, h = int(a.get("w") or 0), int(a.get("h") or 0)
        if a["kind"] in ("image", "video") and w and h:
            r = w / h
            return "9:16" if r < 0.7 else ("1:1" if r < 0.9 else ("4:3" if r < 1.5 else "16:9"))
    return fallback


def _dur(a: Dict[str, Any]) -> float:
    return float(a.get("duration") or a.get("dur") or 0) or (IMAGE_SECONDS if a["kind"] == "image" else 3.0)


def export_to_studio(store: Any, cid: str, project_id: str = "", episode_id: str = "", name: str = "", nodes: Optional[List[str]] = None, mode: str = "auto") -> Dict[str, Any]:
    from .engine import CanvasEngine

    cs, ss = store.canvases, store.studio
    cv = cs.get(cid)
    if not cv:
        raise ValueError("Canvas não encontrado.")
    eng = CanvasEngine(store, cid)
    by_id = {n["id"]: n for n in cv["nodes"]}
    picked = [n for n in (nodes or []) if n in by_id]
    if nodes and not picked:
        raise ValueError("Esses nós não existem mais neste canvas.")
    order = [i for i in eng.topo(cv) if not picked or i in picked]
    editors = [by_id[i] for i in order if by_id[i]["type"] == "editor" and by_id[i]["params"]["timeline"]["clips"]]
    use_editor = bool(editors) and mode in ("auto", "editor")
    if mode == "editor" and not editors:
        raise ValueError("Este canvas não tem um nó Editor com clipes. Use o modo «fluxo» ou monte a timeline no Editor.")

    # ---- 1. o que entra (lista de (clipe do Studio em construção, asset do canvas))
    plan: List[Dict[str, Any]] = []     # {"asset": canvas asset | None, **clip}
    warnings: List[str] = []
    tracks_spec: List[Dict[str, Any]] = []
    if use_editor:
        ed = editors[0]
        tl = ed["params"]["timeline"]
        if len(editors) > 1:
            warnings.append(f"O canvas tem {len(editors)} Editores; levei só o primeiro («{ed.get('title') or 'Editor'}»).")
        tracks_spec = [{"id": t["id"], "kind": t["kind"], "name": t["name"], "muted": t.get("muted", False), "hidden": t.get("hidden", False)} for t in tl["tracks"]]
        for c in tl["clips"]:
            kind = next((t["kind"] for t in tl["tracks"] if t["id"] == c["track"]), "video")
            if kind == "text":
                plan.append({"asset": None, "src_track": c["track"], "kind": "text", **{k: c[k] for k in CLIP_KEYS if k in c}})
                continue
            res = eng.resolve_clip(cv, c)
            if not res:
                warnings.append("Um clipe do Editor aponta para um arquivo que não existe mais — ignorado.")
                continue
            plan.append({"asset": res["asset"], "src_track": c["track"], "kind": kind, **{k: c[k] for k in CLIP_KEYS if k in c}})
        size = (ed["params"]["width"], ed["params"]["height"])
        aspect = "9:16" if size[1] > size[0] * 1.2 else ("1:1" if abs(size[0] - size[1]) < size[0] * 0.1 else "16:9")
    else:
        vis, voices, sounds = 0.0, 0.0, 0.0
        has_out = {e["from"] for e in cv["edges"]}
        # sem seleção: as saídas finais do fluxo (nós que ninguém consome); com seleção: exatamente os escolhidos. Se o fluxo ainda não gerou nada nas pontas, vale tudo que já tem arquivo.
        finals = order if picked else [i for i in order if i not in has_out]
        if not picked and not any(eng.output(cv, by_id[i])["assets"] for i in finals):
            finals = order
        for nid in finals:
            n = by_id[nid]
            for a in eng.output(cv, n)["assets"]:
                if a["kind"] not in ("image", "video", "audio"):
                    continue
                d = _dur(a)
                if a["kind"] in ("image", "video"):
                    plan.append({"asset": a, "src_track": "v", "kind": "video", "start": round(vis, 3), "dur": round(d, 3), "fit": "contain" if a["kind"] == "image" else "cover"})
                    vis += d
                elif n["type"] == "voice":
                    plan.append({"asset": a, "src_track": "a_voice", "kind": "audio", "start": round(voices, 3), "dur": round(d, 3)})
                    voices += d
                else:
                    plan.append({"asset": a, "src_track": "a_sound", "kind": "audio", "start": round(sounds, 3), "dur": round(d, 3), "volume": 0.6 if any(p["src_track"] == "a_voice" for p in plan) else 1.0})
                    sounds += d
        aspect = _aspect_of([p["asset"] for p in plan if p["asset"]])
    if not plan:
        raise ValueError("Não há imagens, vídeos nem áudios gerados para levar ao Studio. Execute o fluxo primeiro.")

    # ---- 2. projeto de destino
    existing = ss.get(project_id) if project_id else None
    if project_id and not existing:
        raise ValueError("Projeto do Studio não encontrado.")
    if existing:
        pid = existing["id"]
    else:
        total = max([p["start"] + p["dur"] for p in plan] + [S.MIN_SECONDS])
        pid = ss.create({"name": text(name, "", 100) or cv["name"], "origin": "manual", "kind": "single", "duration_type": "custom", "target_seconds": max(S.MIN_SECONDS, min(total, S.MAX_SECONDS)),
                         "aspect": aspect, "premise": text(cv.get("description"), "", 4000)})["id"]

    # ---- 3. copia os arquivos (uma vez cada)
    mapping: Dict[str, str] = {}
    for p in plan:
        a = p["asset"]
        if a is None or a["id"] in mapping:
            continue
        path = cs.asset_path(cid, a["file"])
        rec = ss.add_asset_file(pid, path, a["file"].rsplit(".", 1)[-1] if "." in a["file"] else "bin", a["kind"], name=a.get("name") or a["file"], mime=a.get("mime", ""), source="canvas") if path else None
        if not rec:
            warnings.append(f"Não consegui copiar «{a.get('name') or a['file']}».")
            continue
        mapping[a["id"]] = rec["id"]

    # ---- 4. monta as camadas e os clipes (depois do fim da timeline que já existe)
    box: Dict[str, Any] = {}

    def fn(pr: Dict[str, Any]) -> None:
        eps = pr["episodes"]
        ep = next((e for e in eps if e["id"] == episode_id), None) if episode_id else None
        if ep is None:
            ep = eps[0] if eps else None
        if ep is None:
            ep = S.normalize_episode({"title": pr["name"], "status": "ready", "origin": "manual"}, 0)
            eps.append(ep)
        tl = ep["timeline"]
        base = tl["duration"] if existing else 0.0
        track_of: Dict[str, str] = {}
        if use_editor:
            # as trilhas de vídeo do Editor vão de baixo para cima; no Studio a primeira da lista é a de cima: V1 embaixo, V2 acima…
            for kind in ("video", "audio", "text"):
                for sp in [t for t in tracks_spec if t["kind"] == kind]:
                    reuse = next((t for t in tl["tracks"] if t["kind"] == kind and t["name"].upper() == sp["name"].upper() and not existing), None)
                    tr = reuse or S.add_track(tl, kind)
                    if tr:
                        track_of[sp["id"]] = tr["id"]
        else:
            for key, kind, nm in (("v", "video", "V1"), ("a_voice", "audio", "A1"), ("a_sound", "audio", "A2")):
                if not any(p["src_track"] == key for p in plan):
                    continue
                reuse = next((t for t in tl["tracks"] if t["kind"] == kind and t["name"] == nm and not existing), None)
                tr = reuse or S.add_track(tl, kind)
                if tr:
                    track_of[key] = tr["id"]
        added = 0
        for p in plan:
            tid = track_of.get(p["src_track"])
            if not tid:
                continue
            clip = {k: p[k] for k in CLIP_KEYS if k in p}
            clip.update(id=f"cv{len(tl['clips'])}_{added}", track=tid, start=round(float(p.get("start", 0)) + base, 3), label=(p["asset"] or {}).get("name", "")[:40] if p["asset"] else "")
            if p["asset"] is not None:
                if p["asset"]["id"] not in mapping:
                    continue
                clip["asset"] = mapping[p["asset"]["id"]]
            tl["clips"].append(clip)
            added += 1
        ep["status"] = "ready" if ep["status"] in ("draft", "planned") else ep["status"]
        box.update(eid=ep["id"], clips=added, base=base)

    ss.update(pid, fn)
    return {"project_id": pid, "episode_id": box.get("eid", ""), "clips": box.get("clips", 0), "assets": len(mapping), "from_editor": use_editor, "offset": box.get("base", 0.0), "warnings": warnings[:10]}
