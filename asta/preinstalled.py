"""Modelos locais pré-instalados: o ASTA já nasce com um modelo de texto e um de imagem prontos para rodar no seu computador.

São baixados pelo instalador (e pelo `asta update`) — ou com `asta models install` / pelo botão em Configuração → Modelos locais — e ficam
nas mesmas pastas dos demais modelos locais. A quantização deles já vem definida pelo catálogo (e você pode baixar outras na mesma aba).

Catálogo inicial (só estes dois):

* texto  — `empero-ai/Qwen3.8-2B-Distill` em Q8_0 (GGUF oficial do autor: `empero-ai/Qwen3.8-2B-Distill-GGUF`);
* imagem — `Tongyi-MAI/Z-Image` em Q4_K_M (GGUF `unsloth/Z-Image-GGUF`), com o VAE e o codificador de texto (Qwen3-4B) que ele precisa.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import hf
from .providers.base import ProviderError

CATALOG: List[Dict[str, Any]] = [
    {
        "id": "text-qwen3.8-2b-distill", "kind": "text", "label": "Qwen3.8 2B Distill", "source": "empero-ai/Qwen3.8-2B-Distill", "license": "apache-2.0",
        "repo": "empero-ai/Qwen3.8-2B-Distill-GGUF", "file": "Qwen3.8-2B-Q8_0.gguf", "quant": "Q8_0", "size": 2076674432,
        "hint": "Modelo de texto pequeno e rápido (2B, destilado para raciocínio): roda mundos, avatars, jogos e o nó Texto IA no seu computador.",
        "companions": [],
    },
    {
        "id": "image-z-image", "kind": "image", "label": "Z-Image", "source": "Tongyi-MAI/Z-Image", "license": "apache-2.0",
        "repo": "unsloth/Z-Image-GGUF", "file": "z-image-Q4_K_M.gguf", "quant": "Q4_K_M", "size": 3850115136,
        "hint": "Modelo de imagem da Tongyi-MAI (Alibaba). Vem com o VAE e o codificador de texto (Qwen3-4B) de que precisa; roda pelo provedor GGUF local do Canvas.",
        "companions": [
            {"repo": "Comfy-Org/z_image_turbo", "file": "split_files/vae/ae.safetensors", "size": 335304388, "label": "VAE (ae.safetensors)"},
            {"repo": "unsloth/Qwen3-4B-Instruct-2507-GGUF", "file": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "size": 2497281120, "label": "Codificador de texto (Qwen3-4B Q4_K_M)"},
        ],
        # como o Canvas carrega e usa este modelo (o campo "extra" do nó pode sobrescrever): "@model" = o arquivo principal; nomes de arquivo = pasta de imagens
        "load": {"diffusion_model_path": "@model", "vae_path": "ae.safetensors", "llm_path": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"},
        "run": {"cfg_scale": 4.0, "sample_steps": 30},
    },
]


def entry(entry_id: str) -> Dict[str, Any]:
    e = next((x for x in CATALOG if x["id"] == entry_id), None)
    if not e:
        raise ProviderError("Modelo pré-instalado desconhecido.")
    return e


def _files(e: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = [{"repo": e["repo"], "file": e["file"], "size": e["size"], "main": True}]
    out += [{"repo": c["repo"], "file": c["file"], "size": c["size"], "main": False} for c in e.get("companions", [])]
    return out


def installed(models_dir: Path, e: Dict[str, Any]) -> bool:
    folder = hf.kind_dir(models_dir, e["kind"])
    return all((folder / Path(f["file"]).name).is_file() for f in _files(e))


def status(models_dir: Path) -> List[Dict[str, Any]]:
    return [{"id": e["id"], "kind": e["kind"], "label": e["label"], "source": e["source"], "license": e["license"], "repo": e["repo"], "file": e["file"], "quant": e["quant"],
             "size": sum(f["size"] for f in _files(e)), "hint": e["hint"], "parts": [Path(f["file"]).name for f in _files(e)], "installed": installed(models_dir, e)} for e in CATALOG]


def defaults_for(kind: str, filename: str) -> Dict[str, Any]:
    """Como carregar/usar um modelo do catálogo no Canvas ({"load": {...}, "run": {...}}); vazio para os demais."""
    for e in CATALOG:
        if e["kind"] == kind and Path(e["file"]).name == Path(filename).name and e.get("load"):
            return {"load": dict(e["load"]), "run": dict(e.get("run") or {})}
    return {}


def _lib(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def apply(store: Any, e: Dict[str, Any]) -> List[str]:
    """Deixa o modelo pronto para usar. Só troca o provedor padrão se ele ainda é o Demo e a biblioteca que roda o modelo está instalada."""
    name, notes = Path(e["file"]).name, []
    s = store.get_settings()
    if e["kind"] == "text":
        patch: Dict[str, Any] = {"providers": {"local_hf": {"model": name}}}
        if _lib("llama_cpp"):
            act = {r: "local_hf" for r in ("generation", "characters") if s["active"].get(r, "demo") == "demo"}
            if act:
                patch["active"] = act
                notes.append("ativado como modelo de texto padrão")
        elif s["active"].get("generation", "demo") == "demo":
            notes.append('para usá-lo instale a biblioteca: asta libs --extras local')
        store.save_settings(patch)
    elif e["kind"] == "image":
        patch = {"media": {"models": {"gguf_local": {"image": name}}}}
        if _lib("stable_diffusion_cpp"):
            if (s.get("media") or {}).get("active", {}).get("image", "demo") == "demo":
                patch["media"]["active"] = {"image": "gguf_local"}
                notes.append("ativado como provedor de imagem padrão do Canvas")
        else:
            notes.append('para usá-lo instale a biblioteca: asta libs --extras local')
        store.save_settings(patch)
    return notes


def install(store: Any, entry_id: str, token: str = "", progress: Optional[Callable[[int, int], None]] = None, cancelled: Callable[[], bool] = lambda: False,
            log: Callable[[str], None] = lambda m: None) -> Dict[str, Any]:
    """Baixa o modelo e os arquivos de que ele precisa (pula o que já está na pasta) e o deixa pronto para usar."""
    e = entry(entry_id)
    folder = hf.kind_dir(store.models_dir, e["kind"], create=True)
    todo = [f for f in _files(e) if not (folder / Path(f["file"]).name).is_file()]
    done_bytes = 0
    total = sum(f["size"] for f in todo)
    for f in todo:
        log(f"Baixando {Path(f['file']).name} ({f['size'] / 1024 ** 3:.1f} GB) de {f['repo']} …")

        def prog(d: int, t: int, base: int = done_bytes) -> None:
            if progress:
                progress(base + d, total or (base + t))

        hf.download_many(f["repo"], [f["file"]], folder, token, {f["file"]: f["size"]}, prog, cancelled, any_file=True)
        done_bytes += f["size"]
    notes = apply(store, e)
    return {"id": e["id"], "downloaded": [Path(f["file"]).name for f in todo], "notes": notes}


def install_selected(store: Any, which: str = "all", token: str = "", log: Callable[[str], None] = print) -> int:
    """`asta models install`: `which` = all | none | text | image | lista. Devolve 0 se tudo certo, 1 se algum falhou."""
    which = (which or "all").strip().lower()
    if which in ("none", "no", "0"):
        log("Modelos pré-instalados: nada a baixar (ASTA_MODELS=none).")
        return 0
    names = [x.strip() for x in which.replace(";", ",").split(",") if x.strip()]
    chosen = [e for e in CATALOG if "all" in names or e["kind"] in names or e["id"] in names]
    if not chosen:
        log("Modelos desconhecidos: use all, none, text, image ou os ids do catálogo.")
        return 2
    failed = 0
    for e in chosen:
        try:
            if installed(store.models_dir, e):
                log(f"{e['label']} ({e['quant']}): já instalado.")
                apply(store, e)
                continue
            r = install(store, e["id"], token, log=log)
            log(f"{e['label']} ({e['quant']}): pronto" + (f" — {'; '.join(r['notes'])}" if r["notes"] else "") + ".")
        except ProviderError as exc:
            failed += 1
            log(f"⚠  {e['label']}: não foi possível instalar ({exc}). Tente de novo com:  asta models install")
    return 1 if failed else 0
