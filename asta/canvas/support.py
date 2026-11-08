"""Arquivos de apoio dos GGUF de difusão (v0.17.7): Qwen-Image, FLUX… trazem só o «transformador» e precisam do VAE e dos codificadores de texto **na mesma pasta**.

Aqui ficam as famílias conhecidas (como reconhecer o modelo, que arquivo de apoio cada parâmetro de carga espera e de onde baixá-lo). O download **só acontece quando a pessoa pede**
(botão «Baixar os arquivos de apoio» no nó) — o ASTA não baixa gigabytes sozinho no meio de uma geração.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import hf

FAMILIES: List[Dict[str, Any]] = [
    {"id": "qwen-image", "name": r"qwen[-_ ]?image", "label": "Qwen-Image",
     "load": {"vae_path": r"(qwen.*image.*vae|(^|[-_.])vae([-_.]|$)|^ae\.safetensors$)", "llm_path": r"qwen2[._]?5.*vl.*\.gguf$"}, "run": {"cfg_scale": 2.5}, "options": {"offload_params_to_cpu": True, "diffusion_flash_attn": True},
     "need": "o VAE (qwen_image_vae.safetensors, em Comfy-Org/Qwen-Image_ComfyUI) e o codificador de texto Qwen2.5-VL (um .gguf, ex.: unsloth/Qwen2.5-VL-7B-Instruct-GGUF)",
     "downloads": {"vae_path": {"repo": "Comfy-Org/Qwen-Image_ComfyUI", "file": "split_files/vae/qwen_image_vae.safetensors", "label": "VAE do Qwen-Image", "approx": 0.25},
                   "llm_path": {"repo": "unsloth/Qwen2.5-VL-7B-Instruct-GGUF", "file": "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf", "label": "Codificador de texto Qwen2.5-VL (Q4_K_M)", "approx": 4.7}}},
    {"id": "flux", "name": r"flux", "label": "FLUX",
     "load": {"vae_path": r"^ae\.safetensors$", "clip_l_path": r"clip[_-]?l.*\.safetensors$", "t5xxl_path": r"t5xxl.*\.(safetensors|gguf)$"}, "run": {}, "options": {"offload_params_to_cpu": True, "diffusion_flash_attn": True},
     "need": "o VAE (ae.safetensors), o clip_l.safetensors e o t5xxl (safetensors ou .gguf)",
     "downloads": {"vae_path": {"repo": "Comfy-Org/z_image_turbo", "file": "split_files/vae/ae.safetensors", "label": "VAE (ae.safetensors)", "approx": 0.33},
                   "clip_l_path": {"repo": "comfyanonymous/flux_text_encoders", "file": "clip_l.safetensors", "label": "clip_l", "approx": 0.25},
                   "t5xxl_path": {"repo": "comfyanonymous/flux_text_encoders", "file": "t5xxl_fp8_e4m3fn.safetensors", "label": "t5xxl (fp8)", "approx": 4.9}}},
]


def family_of(filename: str) -> Optional[Dict[str, Any]]:
    return next((f for f in FAMILIES if re.search(f["name"], Path(filename).name, re.I)), None)


def find_companions(folder: Path, model: Path, fam: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Para cada parâmetro de carga da família, o nome do arquivo de apoio achado em `folder` (None se falta)."""
    files = sorted(f for f in folder.iterdir() if f.is_file() and f != model and not f.name.endswith(".part")) if folder.is_dir() else []
    out: Dict[str, Optional[str]] = {}
    for key, pat in fam["load"].items():
        hit = next((f for f in files if re.search(pat, f.name, re.I)), None)
        out[key] = hit.name if hit else None
    return out


def missing(folder: Path, filename: str) -> Dict[str, Any]:
    """{family, missing: [{key, label, repo, file, approx}], approx_gb} do que falta para o modelo `filename` (vazio se não é de uma família conhecida ou se está tudo lá)."""
    fam = family_of(filename)
    if not fam:
        return {"family": "", "missing": [], "approx_gb": 0.0}
    found = find_companions(folder, folder / Path(filename).name, fam)
    todo = [{"key": k, **fam["downloads"][k]} for k, v in found.items() if v is None]
    return {"family": fam["id"], "label": fam["label"], "missing": todo, "approx_gb": round(sum(t["approx"] for t in todo), 1)}


def download_missing(folder: Path, filename: str, token: str = "", progress: Optional[Callable[[int, int], None]] = None,
                     cancelled: Callable[[], bool] = lambda: False, note: Callable[[str], None] = lambda m: None) -> List[str]:
    """Baixa para `folder` os arquivos de apoio que faltam (retoma downloads parciais). Devolve os nomes baixados."""
    info = missing(folder, filename)
    got: List[str] = []
    n = len(info["missing"])
    for i, t in enumerate(info["missing"]):
        note(f"Baixando {t['label']} ({i + 1}/{n})…")
        base = i

        def prog(done: int, total: int, base: int = base) -> None:
            if progress:   # progresso geral: cada arquivo vale uma fatia igual
                progress(int((base + (done / total if total else 0)) * 1000), n * 1000)

        folder.mkdir(parents=True, exist_ok=True)
        hf.download_many(t["repo"], [t["file"]], folder, token, None, prog, cancelled, any_file=True)
        got.append(Path(t["file"]).name)
    return got
