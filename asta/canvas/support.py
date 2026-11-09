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
    # ---- Unsloth (v0.17.30): Qwen-Image 2.1 e Turbo, Z-Image e Turbo (imagem) e Wan2.2 TI2V 5B (vídeo). As receitas vêm dos cartões dos repositórios unsloth/*-GGUF (VAE, codificador de texto, passos e CFG).
    {"id": "qwen-image-2.1", "name": r"qwen[-_ ]?image[-_ ]?2[._]?1", "label": "Qwen-Image 2.1", "cap": "image",
     "load": {"vae_path": r"qwen[-_]?image[-_]?2[._]?1[-_]?vae.*\.safetensors$", "llm_path": r"^qwen[-_]?3[-_]?vl[-_]?8b[-_]?instruct(?!.*mmproj)[^/]*\.gguf$"},
     "run": {"cfg_scale": 6.0, "sample_steps": 20, "sample_method": "euler"}, "variants": [{"match": r"turbo", "run": {"cfg_scale": 1.0, "sample_steps": 8, "sample_method": "euler"}}],   # Turbo: 8 passos, CFG 1
     "options": {"offload_params_to_cpu": True, "diffusion_flash_attn": True},
     "need": "o VAE do Qwen-Image 2.1 (qwen_image_2.1_vae_bf16.safetensors, em unsloth/Qwen-Image-2.1-FP8) e o codificador de texto Qwen3-VL-8B-Instruct (um .gguf, ex.: unsloth/Qwen3-VL-8B-Instruct-GGUF)",
     "downloads": {"vae_path": {"repo": "unsloth/Qwen-Image-2.1-FP8", "file": "vae/qwen_image_2.1_vae_bf16.safetensors", "label": "VAE do Qwen-Image 2.1", "approx": 0.68},
                   "llm_path": {"repo": "unsloth/Qwen3-VL-8B-Instruct-GGUF", "file": "Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf", "label": "Codificador de texto Qwen3-VL-8B-Instruct (UD-Q4_K_XL)", "approx": 5.1}}},
    {"id": "z-image", "name": r"z[-_ ]?image", "label": "Z-Image", "cap": "image",
     "load": {"vae_path": r"^ae\.safetensors$", "llm_path": r"^qwen[-_]?3[-_]?4b[-_]?instruct[-_]?2507(?!.*mmproj)[^/]*\.gguf$"},
     "run": {"cfg_scale": 4.0, "sample_steps": 30}, "variants": [{"match": r"turbo", "run": {"cfg_scale": 1.0, "sample_steps": 8}}],   # Turbo: 8 passos, sem CFG; o Z-Image «base» usa 30 passos e CFG 4
     "options": {"offload_params_to_cpu": True, "diffusion_flash_attn": True},
     "need": "o VAE (ae.safetensors) e o codificador de texto Qwen3-4B-Instruct-2507 (um .gguf, ex.: unsloth/Qwen3-4B-Instruct-2507-GGUF)",
     "downloads": {"vae_path": {"repo": "Comfy-Org/z_image_turbo", "file": "split_files/vae/ae.safetensors", "label": "VAE (ae.safetensors)", "approx": 0.34},
                   "llm_path": {"repo": "unsloth/Qwen3-4B-Instruct-2507-GGUF", "file": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "label": "Codificador de texto Qwen3-4B-Instruct-2507 (Q4_K_M)", "approx": 2.5}}},
    {"id": "wan22-ti2v-5b", "name": r"wan[-_. ]?2[._]?2.*ti2v", "label": "Wan2.2 TI2V 5B", "cap": "video",
     "load": {"vae_path": r"wan[-_]?2[._]?2[-_]?vae.*\.safetensors$", "t5xxl_path": r"umt5[-_]?xxl.*\.(safetensors|gguf)$"},
     "run": {"cfg_scale": 5.0, "sample_steps": 30, "flow_shift": 5.0, "sample_method": "euler"},
     "video": {"fps": 24, "sizes": {"landscape": [1280, 704], "portrait": [704, 1280]}, "max_frames": 121},   # 720p apenas (1280×704 ou 704×1280); quadros = 4k+1 (o VAE comprime 4× no tempo)
     "options": {"offload_params_to_cpu": True, "diffusion_flash_attn": True},
     "need": "o VAE do Wan2.2 (Wan2.2_VAE.safetensors, em unsloth/Wan2.2-TI2V-5B-GGUF) e o codificador de texto UMT5-XXL (um .gguf, ex.: city96/umt5-xxl-encoder-gguf)",
     "downloads": {"vae_path": {"repo": "unsloth/Wan2.2-TI2V-5B-GGUF", "file": "VAE/Wan2.2_VAE.safetensors", "label": "VAE do Wan2.2", "approx": 1.4},
                   "t5xxl_path": {"repo": "city96/umt5-xxl-encoder-gguf", "file": "umt5-xxl-encoder-Q4_K_M.gguf", "label": "Codificador de texto UMT5-XXL (Q4_K_M)", "approx": 3.7}}},
    {"id": "qwen-image", "name": r"qwen[-_ ]?image", "label": "Qwen-Image",
     "load": {"vae_path": r"qwen.*image.*vae", "llm_path": r"qwen2[._]?5.*vl.*\.gguf$"}, "marker": "transformer_blocks.0.img_mod.1.weight", "run": {"cfg_scale": 2.5, "flow_shift": 3.0, "sample_method": "euler"}, "options": {"offload_params_to_cpu": True, "diffusion_flash_attn": True},
     "need": "o VAE (qwen_image_vae.safetensors, em Comfy-Org/Qwen-Image_ComfyUI) e o codificador de texto Qwen2.5-VL (um .gguf, ex.: unsloth/Qwen2.5-VL-7B-Instruct-GGUF)",
     "downloads": {"vae_path": {"repo": "Comfy-Org/Qwen-Image_ComfyUI", "file": "split_files/vae/qwen_image_vae.safetensors", "label": "VAE do Qwen-Image", "approx": 0.25},
                   "llm_path": {"repo": "unsloth/Qwen2.5-VL-7B-Instruct-GGUF", "file": "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf", "label": "Codificador de texto Qwen2.5-VL (Q4_K_M)", "approx": 4.7}}},
    {"id": "flux2-klein-9b", "name": r"flux[-_. ]?2.*9b", "label": "FLUX.2 klein (9B)",
     "load": {"vae_path": r"flux2[-_]?(ae|vae)", "llm_path": r"^qwen[-_]?3[-_]8b(?![-_]?(instruct|vl|thinking|embedding|2507))[^/]*\.gguf$"}, "marker": "double_blocks.",
     "run": {"cfg_scale": 1.0, "sample_steps": 4, "sample_method": "euler"}, "run_base": {"cfg_scale": 4.0, "sample_steps": 50, "sample_method": "euler"},   # klein é destilado (4 passos, sem CFG); o «base» usa 50 passos e CFG 4
     "options": {"offload_params_to_cpu": True, "diffusion_flash_attn": True},
     "need": "o VAE do FLUX.2 (flux2-vae.safetensors, em Comfy-Org/flux2-dev) e o codificador de texto Qwen3-8B (um .gguf, ex.: unsloth/Qwen3-8B-GGUF)",
     "downloads": {"vae_path": {"repo": "Comfy-Org/flux2-dev", "file": "split_files/vae/flux2-vae.safetensors", "label": "VAE do FLUX.2", "approx": 0.34},
                   "llm_path": {"repo": "unsloth/Qwen3-8B-GGUF", "file": "Qwen3-8B-Q4_K_M.gguf", "label": "Codificador de texto Qwen3-8B (Q4_K_M)", "approx": 5.0}}},
    {"id": "flux2-klein-4b", "name": r"flux[-_. ]?2.*4b", "label": "FLUX.2 klein (4B)",
     "load": {"vae_path": r"flux2[-_]?(ae|vae)", "llm_path": r"^qwen[-_]?3[-_]4b(?![-_]?(instruct|vl|thinking|embedding|2507))[^/]*\.gguf$"}, "marker": "double_blocks.",
     "run": {"cfg_scale": 1.0, "sample_steps": 4, "sample_method": "euler"}, "run_base": {"cfg_scale": 4.0, "sample_steps": 50, "sample_method": "euler"},   # klein é destilado (4 passos, sem CFG); o «base» usa 50 passos e CFG 4
     "options": {"offload_params_to_cpu": True, "diffusion_flash_attn": True},
     "need": "o VAE do FLUX.2 (flux2-vae.safetensors, em Comfy-Org/flux2-dev) e o codificador de texto Qwen3-4B (um .gguf, ex.: unsloth/Qwen3-4B-GGUF)",
     "downloads": {"vae_path": {"repo": "Comfy-Org/flux2-dev", "file": "split_files/vae/flux2-vae.safetensors", "label": "VAE do FLUX.2", "approx": 0.34},
                   "llm_path": {"repo": "unsloth/Qwen3-4B-GGUF", "file": "Qwen3-4B-Q4_K_M.gguf", "label": "Codificador de texto Qwen3-4B (Q4_K_M)", "approx": 2.5}}},
    {"id": "flux3-klein", "name": r"flux[-_. ]?3(?!.*pup)", "label": "FLUX.3 Image Klein",   # «pup» = o expansor de prompt (um modelo de texto), não é de imagem
     "load": {"vae_path": r"flux2[-_]?(ae|vae)", "llm_path": r"^qwen[-_]?3[-_]?vl[-_]?4b[-_]?instruct(?!.*mmproj)[^/]*\.gguf$"},
     "run": {"cfg_scale": 1.0, "sample_steps": 16}, "run_base": {"cfg_scale": 3.5, "sample_steps": 50},   # destilado: 16 passos, sem guidance; «base»: 50 passos, guidance 3,5 (cartão do modelo)
     "options": {"offload_params_to_cpu": True, "diffusion_flash_attn": True},
     "need": "o VAE do FLUX.2/3 (flux2-vae.safetensors, em Comfy-Org/flux2-dev) e o codificador de texto Qwen3-VL-4B-Instruct (um .gguf, ex.: unsloth/Qwen3-VL-4B-Instruct-GGUF)",
     "downloads": {"vae_path": {"repo": "Comfy-Org/flux2-dev", "file": "split_files/vae/flux2-vae.safetensors", "label": "VAE do FLUX.2/3", "approx": 0.34},
                   "llm_path": {"repo": "unsloth/Qwen3-VL-4B-Instruct-GGUF", "file": "Qwen3-VL-4B-Instruct-Q4_K_M.gguf", "label": "Codificador de texto Qwen3-VL-4B-Instruct (Q4_K_M)", "approx": 2.5}}},
    {"id": "flux", "name": r"flux(?![-_. ]?[23])", "label": "FLUX",
     "load": {"vae_path": r"^ae\.safetensors$", "clip_l_path": r"clip[_-]?l.*\.safetensors$", "t5xxl_path": r"t5xxl.*\.(safetensors|gguf)$"}, "marker": "double_blocks.", "run": {}, "options": {"offload_params_to_cpu": True, "diffusion_flash_attn": True},
     "need": "o VAE (ae.safetensors), o clip_l.safetensors e o t5xxl (safetensors ou .gguf)",
     "downloads": {"vae_path": {"repo": "Comfy-Org/z_image_turbo", "file": "split_files/vae/ae.safetensors", "label": "VAE (ae.safetensors)", "approx": 0.33},
                   "clip_l_path": {"repo": "comfyanonymous/flux_text_encoders", "file": "clip_l.safetensors", "label": "clip_l", "approx": 0.25},
                   "t5xxl_path": {"repo": "comfyanonymous/flux_text_encoders", "file": "t5xxl_fp8_e4m3fn.safetensors", "label": "t5xxl (fp8)", "approx": 4.9}}},
]


def run_for(fam: Dict[str, Any], filename: str) -> Dict[str, Any]:
    """Os parâmetros de geração da família; a variante «base» (sem destilação) usa os de `run_base`, se a família tem, e `variants` (ex.: «turbo») trocam os parâmetros pelo nome do arquivo."""
    name = Path(filename).name
    for v in fam.get("variants") or []:
        if re.search(v["match"], name, re.I):
            return dict(v["run"])
    if fam.get("run_base") and re.search(r"base", name, re.I):
        return dict(fam["run_base"])
    return dict(fam.get("run") or {})


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
