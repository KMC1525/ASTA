"""Modelos locais do Canvas (diffusers/transformers): o usuário escolhe a precisão (quantização) ANTES de qualquer download.

Nada é baixado em silêncio: o provedor "Hugging Face local" só carrega modelos que o usuário baixou aqui, escolhendo a precisão:

* **fp32** — original, maior arquivo e mais memória; é o que funciona em CPU;
* **fp16** — metade do tamanho e da memória, mais rápido em placa de vídeo (GPU); em CPU pode ser lento ou não funcionar;
* **bf16** — como o fp16, mas com a faixa de valores do fp32; exige GPU/CPU recentes.

Só os arquivos da precisão escolhida são baixados (variantes `.fp16.safetensors` quando o repositório as tem). A escolha fica em
`settings.media.precision[modelo]`.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..providers.base import ProviderError

PRECISIONS = ("fp32", "fp16", "bf16")
LABELS = {"fp32": "fp32 · original", "fp16": "fp16 · metade do tamanho", "bf16": "bf16 · metade do tamanho"}
HINTS = {"fp32": "Maior e mais lento, mas funciona em qualquer computador (inclusive só com CPU).",
         "fp16": "Metade do tamanho e da memória; ideal com placa de vídeo (GPU). Em CPU pode ser lento ou falhar.",
         "bf16": "Como o fp16, com a faixa de valores do fp32; pede um processador/GPU recente."}
WEIGHT_EXT = (".safetensors", ".bin", ".pt", ".pth", ".ckpt", ".msgpack", ".h5", ".onnx", ".onnx_data", ".tflite", ".mlmodel", ".gguf")
SKIP_EXT = (".md", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".wav", ".mp3", ".flac")
MARKER = "asta_precision.txt"


def _hub() -> Any:
    try:
        import huggingface_hub  # type: ignore

        return huggingface_hub
    except ImportError:
        raise ProviderError('Modelos locais precisam das bibliotecas opcionais (huggingface_hub). Instale com:  pip install "asta[media]"  (ou rode: asta libs)') from None


def select_files(files: List[Dict[str, Any]], precision: str) -> List[Dict[str, Any]]:
    """Quais arquivos do repositório baixar para a precisão escolhida (pesos duplicados em outros formatos/variantes ficam de fora)."""
    names = [f["name"] for f in files]
    has_st = any(n.endswith(".safetensors") for n in names)
    diffusers_layout = "model_index.json" in names
    low = precision in ("fp16", "bf16")

    def is_variant(n: str) -> bool:
        return ".fp16." in n or ".bf16." in n

    def twin(n: str) -> str:  # nome da variante fp16 de um peso
        stem, dot, ext = n.rpartition(".")
        return f"{stem}.fp16.{ext}" if dot else n

    out = []
    for f in files:
        n = f["name"]
        low_n = n.lower()
        if n.startswith(".") or low_n.endswith(SKIP_EXT):
            continue
        if not low_n.endswith(WEIGHT_EXT):
            out.append(f)
            continue
        if has_st and not low_n.endswith((".safetensors", ".onnx_data")) and not low_n.endswith(".gguf"):
            continue  # só safetensors quando existe
        if low_n.endswith((".onnx", ".onnx_data", ".tflite", ".mlmodel")):
            continue
        if diffusers_layout and "/" not in n:
            continue  # checkpoint único na raiz repete os pesos das pastas (unet/, vae/…)
        if is_variant(n):
            if low:
                out.append(f)  # fp16 e bf16 usam a variante fp16 (bf16 só muda o tipo ao carregar)
            continue
        if low and twin(n) in names:
            continue  # existe a variante fp16 deste peso: baixa só ela
        out.append(f)
    return out


def _siblings(model: str, token: str) -> List[Dict[str, Any]]:
    info = _hub().HfApi().model_info(model, files_metadata=True, token=token or None)
    return [{"name": s.rfilename, "size": int(getattr(s, "size", 0) or 0)} for s in (info.siblings or [])]


def options(model: str, token: str = "", gpu: bool = False) -> Dict[str, Any]:
    """As precisões possíveis para um modelo, com o tamanho do download de cada uma e a recomendada para este computador."""
    files = _siblings(model, token)
    out = []
    for p in PRECISIONS:
        chosen = select_files(files, p)
        out.append({"id": p, "label": LABELS[p], "hint": HINTS[p], "size": sum(f["size"] for f in chosen), "files": len(chosen)})
    rec = "fp16" if gpu else "fp32"
    for o in out:
        o["recommended"] = o["id"] == rec
    return {"model": model, "options": out, "recommended": rec}


def _snapshot(model: str) -> Optional[Path]:
    try:
        return Path(_hub().snapshot_download(model, local_files_only=True))
    except Exception:  # noqa: BLE001 — não está no cache
        return None


def downloaded_precision(model: str) -> str:
    """Precisão com que o modelo foi baixado ("" se não foi baixado pelo ASTA)."""
    try:
        snap = _snapshot(model)
    except ProviderError:
        return ""
    marker = snap / MARKER if snap else None
    if marker and marker.is_file():
        p = marker.read_text(encoding="utf-8").strip()
        return p if p in PRECISIONS else ""
    return ""


def has_fp16_variant(model: str) -> bool:
    snap = _snapshot(model)
    return bool(snap and any(".fp16." in p.name for p in snap.rglob("*") if p.is_file() or p.is_symlink()))


def _incomplete_bytes(model: str) -> int:
    try:
        cache = Path(_hub().constants.HF_HUB_CACHE) / ("models--" + model.replace("/", "--")) / "blobs"
        return sum(p.stat().st_size for p in cache.glob("*.incomplete"))
    except Exception:  # noqa: BLE001
        return 0


def download(model: str, precision: str, token: str = "", progress: Optional[Callable[[int, int], None]] = None, cancelled: Callable[[], bool] = lambda: False) -> Path:
    """Baixa os arquivos da precisão escolhida, um a um (dá para cancelar entre arquivos), e registra a escolha."""
    if precision not in PRECISIONS:
        raise ProviderError("Escolha a precisão (quantização) do modelo antes de baixar.")
    hub = _hub()
    files = select_files(_siblings(model, token), precision)
    if not files:
        raise ProviderError("Nenhum arquivo utilizável neste repositório.")
    total = sum(f["size"] for f in files)
    done, snap = 0, None
    for f in files:
        if cancelled():
            raise ProviderError("cancelado")
        stop = threading.Event()

        def poll(base: int = done) -> None:
            while not stop.wait(0.5):
                if progress:
                    progress(base + _incomplete_bytes(model), total)

        t = threading.Thread(target=poll, daemon=True)
        t.start()
        try:
            snap = Path(hub.hf_hub_download(model, f["name"], token=token or None)).parents[len(Path(f["name"]).parts) - 1]
        finally:
            stop.set()
            t.join(1)
        done += f["size"]
        if progress:
            progress(done, total)
    if snap is None:
        raise ProviderError("O download não gerou arquivos.")
    (snap / MARKER).write_text(precision, encoding="utf-8")
    return snap


def torch_dtype(precision: str) -> Any:
    import torch  # type: ignore

    return {"fp32": torch.float32, "fp16": torch.float16, "bf16": torch.bfloat16}[precision]
