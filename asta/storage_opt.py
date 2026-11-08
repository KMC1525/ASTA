"""Armazenamento do ASTA (HDD/SSD): quanto cada parte ocupa, o que dá para liberar sem perder nada e arquivos duplicados.

Tudo fica em ASTA_HOME (padrão ~/.asta). Três coisas, todas **seguras e com prévia**:

  • `report` — tamanho de cada parte (modelos, projetos, canvases, Studio, avatars, conversas, anexos pendentes…), os maiores arquivos e quanto dá para liberar;
  • `clean` — sobras que nunca são dados do usuário: downloads interrompidos antigos (`.part`), anexos que ninguém usou há mais de um dia, pastas vazias de anexos;
  • `dedupe` — arquivos **idênticos** (conferidos byte a byte pelo núcleo Rust) viram um só no disco, trocando as cópias por *links físicos* (hard links): ninguém perde arquivo
    nenhum, os dois caminhos continuam funcionando e o espaço de uma das cópias volta. Só em arquivos que o ASTA nunca altera no lugar (modelos, imagens, vídeos, áudios, pacotes).

Nada é apagado ou trocado sem `apply=True`; o padrão é só mostrar o que seria feito.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List

from . import native

#: pastas de ASTA_HOME e o nome mostrado ao usuário
AREAS = [("models", "Modelos"), ("projects", "Projetos (mundos e jogos)"), ("canvases", "Canvas"), ("studio", "Studio"), ("avatars", "Avatars"), ("avatar_chats", "Conversas dos avatars"),
         ("chats", "Conversas do Chat"), ("characters", "Personagens"), ("avatar_memory", "Memórias"), ("uploads", "Anexos pendentes"), ("native", "Núcleo Rust"), ("worldbuildings", "Mundos-base")]
#: tipos de arquivo que o ASTA grava uma vez e nunca altera no lugar: seguros para virar link físico
IMMUTABLE_EXT = ("gguf", "safetensors", "ckpt", "pt", "pth", "bin", "onnx", "png", "jpg", "jpeg", "webp", "gif", "mp4", "webm", "mov", "mkv", "wav", "mp3", "m4a", "ogg", "flac", "zip")
STALE_UPLOAD_SECONDS = 24 * 3600
STALE_PART_SECONDS = 24 * 3600


def human(n: int) -> str:
    f = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or u == "TB":
            return f"{f:.0f} {u}" if u == "B" else f"{f:.1f} {u}"
        f /= 1024
    return f"{n} B"


def _orphans(home: Path) -> List[Dict[str, Any]]:
    """Sobras que podem sair sem perder nada: downloads de modelo parados (.part), anexos esquecidos e pastas de anexos vazias."""
    now = time.time()
    out: List[Dict[str, Any]] = []
    models = home / "models"
    if models.is_dir():
        for p in models.rglob("*.part"):
            try:
                st = p.stat()
            except OSError:
                continue
            if now - st.st_mtime > STALE_PART_SECONDS:
                out.append({"path": str(p), "bytes": st.st_size, "why": "download de modelo interrompido há mais de um dia"})
    up = home / "uploads"
    if up.is_dir():
        for d in up.iterdir():
            if not d.is_dir():
                continue
            try:
                age = now - d.stat().st_mtime
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            except OSError:
                continue
            if age > STALE_UPLOAD_SECONDS or size == 0:
                out.append({"path": str(d), "bytes": size, "why": "anexo que ninguém usou" if size else "pasta de anexo vazia"})
    return out


def report(home: Any) -> Dict[str, Any]:
    """Uso do disco por área, os maiores arquivos, o que é sobra e quanto os duplicados ocupam (sem mexer em nada)."""
    home = Path(home)
    areas: List[Dict[str, Any]] = []
    total = 0
    largest: List[Dict[str, Any]] = []
    for folder, label in AREAS:
        r = native.scan_dir(home / folder)
        if not r:
            continue
        areas.append({"id": folder, "label": label, "bytes": r["bytes"], "files": r["files"]})
        total += r["bytes"]
        largest += r["largest"]
    areas.sort(key=lambda a: -a["bytes"])
    largest.sort(key=lambda x: -x["bytes"])
    orph = _orphans(home)
    dups = duplicates(home)
    try:
        du = shutil.disk_usage(home)
        disk = {"total": du.total, "free": du.free}
    except OSError:
        disk = {"total": 0, "free": 0}
    return {"home": str(home), "total": total, "areas": areas, "largest": largest[:10], "orphans": {"files": len(orph), "bytes": sum(o["bytes"] for o in orph), "items": orph[:20]},
            "duplicates": {"groups": len(dups["groups"]), "bytes": dups["reclaimable"], "items": dups["groups"][:10]}, "disk": disk, "native": native.status()["ops"]}


#: só nestas pastas as cópias podem virar link físico: o ASTA ali sempre grava um arquivo novo e nunca reescreve o existente (retratos e anexos, por exemplo, ficam de fora)
LINKABLE_ROOTS = ("models", "canvases", "studio", "projects")


def _linkable(home: Path, path: str) -> bool:
    try:
        parts = Path(path).resolve().relative_to(home.resolve()).parts
    except ValueError:
        return False
    return bool(parts) and parts[0] in LINKABLE_ROOTS and not path.endswith(".asta-link")


def duplicates(home: Any, min_size: int = 1 << 20) -> Dict[str, Any]:
    """Grupos de arquivos idênticos (≥ 1 MB) e quanto espaço voltaria. Os que já são o mesmo arquivo no disco (link físico) não contam."""
    home = Path(home)
    groups = []
    reclaimable = 0
    for g in native.dup_groups(home, min_size=min_size, exts=IMMUTABLE_EXT):
        paths = [p for p in g["paths"] if os.path.isfile(p) and _linkable(home, p)]
        if len(paths) < 2:
            continue
        inodes = {}
        for p in paths:
            try:
                st = os.stat(p)
            except OSError:
                continue
            inodes.setdefault((st.st_dev, st.st_ino), []).append(p)
        if len(inodes) < 2:
            continue   # todos já apontam para o mesmo arquivo no disco
        extra = (len(inodes) - 1) * g["size"]
        reclaimable += extra
        groups.append({"size": g["size"], "paths": paths, "copies": len(inodes), "reclaimable": extra})
    groups.sort(key=lambda x: -x["reclaimable"])
    return {"groups": groups, "reclaimable": reclaimable}


def _link_over(keep: str, dup: str) -> bool:
    """Troca `dup` por um link físico para `keep` sem deixar um instante sem o arquivo: cria o link ao lado e substitui."""
    tmp = dup + ".asta-link"
    try:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        os.link(keep, tmp)
        os.replace(tmp, dup)
        return True
    except OSError:
        try:
            if os.path.lexists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        return False


def optimize(home: Any, *, dedupe: bool = True, clean: bool = True, apply: bool = False) -> Dict[str, Any]:
    """Libera espaço. Sem `apply` só diz o que faria (prévia). Devolve o que foi (ou seria) feito e os bytes liberados."""
    home = Path(home)
    result: Dict[str, Any] = {"applied": bool(apply), "cleaned": [], "linked": [], "freed": 0, "failed": []}
    if clean:
        for o in _orphans(home):
            if apply:
                try:
                    shutil.rmtree(o["path"]) if os.path.isdir(o["path"]) else os.unlink(o["path"])
                except OSError:
                    result["failed"].append(o["path"])
                    continue
            result["cleaned"].append(o)
            result["freed"] += o["bytes"]
    if dedupe:
        for g in duplicates(home)["groups"]:
            keep = g["paths"][0]
            try:
                keep_st = os.stat(keep)
            except OSError:
                continue
            for dup in g["paths"][1:]:
                try:
                    st = os.stat(dup)
                except OSError:
                    continue
                if (st.st_dev, st.st_ino) == (keep_st.st_dev, keep_st.st_ino):
                    continue   # já são o mesmo arquivo
                if st.st_dev != keep_st.st_dev:
                    result["failed"].append(dup + " (outro disco)")
                    continue
                if apply and not _link_over(keep, dup):
                    result["failed"].append(dup)
                    continue
                result["linked"].append({"kept": keep, "replaced": dup, "bytes": g["size"]})
                result["freed"] += g["size"]
    return result
