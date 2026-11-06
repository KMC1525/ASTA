"""Modo de desempenho: quanto de RAM/VRAM e CPU os modelos locais podem usar.

`settings.performance.mode`:
* ``auto`` (padrão) — decide pelo hardware: PC fraco → leve; intermediário → equilibrado; potente → máximo;
* ``light`` — o mínimo de memória: janela de contexto limitada, cache de atenção quantizado (q8), modelos descarregados logo que ficam ociosos,
  modelos de imagem/áudio em fp16 com fatias de atenção e descarregando para a CPU o que não está em uso;
* ``balanced`` — meio-termo;
* ``max`` — tudo na memória, sem limites do ASTA.
Os pesos continuam sendo mapeados do disco (mmap): só as páginas usadas ocupam RAM.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional

MODES = ("auto", "light", "balanced", "max")
DEFAULTS = {"mode": "auto", "idle_unload_min": 10}


def resolve(mode: str, hw: Dict[str, Any]) -> str:
    if mode in ("light", "balanced", "max"):
        return mode
    return {"low": "light", "medium": "balanced", "high": "max"}.get(hw.get("tier", "medium"), "balanced")


def profile(perf: Optional[Dict[str, Any]], hw: Dict[str, Any]) -> Dict[str, Any]:
    """Parâmetros concretos para o modo escolhido (`perf` = settings["performance"], pode ser {})."""
    perf = perf if isinstance(perf, dict) else {}
    mode = resolve(str(perf.get("mode") or "auto"), hw)
    try:
        idle = max(0, min(int(perf.get("idle_unload_min", DEFAULTS["idle_unload_min"])), 24 * 60))
    except (TypeError, ValueError):
        idle = DEFAULTS["idle_unload_min"]
    base = {
        "light": {"ctx_cap": 4096, "n_batch": 128, "kv_q8": True, "flash": True, "idle_s": min(idle, 3) * 60 if idle else 0, "media_offload": True, "attention_slicing": True},
        "balanced": {"ctx_cap": 16384, "n_batch": 256, "kv_q8": False, "flash": True, "idle_s": idle * 60, "media_offload": False, "attention_slicing": False},
        "max": {"ctx_cap": 0, "n_batch": 512, "kv_q8": False, "flash": False, "idle_s": 0, "media_offload": False, "attention_slicing": False},
    }[mode]
    return {"mode": mode, **base}


def describe(p: Dict[str, Any]) -> str:
    return {"light": "leve (menos RAM/VRAM)", "balanced": "equilibrado", "max": "máximo"}[p["mode"]]


def cap_context(n: int, p: Dict[str, Any], explicit: bool) -> int:
    """Limita a janela de contexto no modo leve/equilibrado — mas nunca contraria um valor que o usuário definiu à mão."""
    cap = int(p.get("ctx_cap") or 0)
    return n if explicit or not cap else min(n, cap)


class IdleUnloader:
    """Descarrega um recurso pesado (modelo na RAM/VRAM) depois de `idle_s` segundos sem uso."""

    def __init__(self, unload: Callable[[], None]):
        self._unload, self._last, self._idle, self._timer = unload, time.time(), 0, None
        self._lock = threading.Lock()

    def touch(self, idle_s: int) -> None:
        with self._lock:
            self._last, self._idle = time.time(), int(idle_s)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = None
            if self._idle > 0:
                self._timer = threading.Timer(self._idle + 1, self._fire)
                self._timer.daemon = True
                self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            if self._idle <= 0 or time.time() - self._last < self._idle:
                return
        try:
            self._unload()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- memória livre agora (para o planejador do núcleo Rust)
MODE_NUM = {"light": 0, "balanced": 1, "max": 2}
_GPU_CACHE: Dict[str, Any] = {"t": 0.0, "v": (0, 0, False)}


def gpu_memory(ram_total: int = 0, ram_avail: int = 0) -> tuple:
    """(VRAM total, VRAM livre, memória unificada?) em bytes. NVIDIA: nvidia-smi. Apple Silicon: a GPU usa a RAM (≈65% dela). Sem GPU: zeros."""
    now = time.time()
    if now - _GPU_CACHE["t"] < 3.0:
        return _GPU_CACHE["v"]
    v: tuple = (0, 0, False)
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run([smi, "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout.strip().splitlines()
            if out:
                tot, free = (int(float(x)) * 1048576 for x in out[0].split(","))
                v = (tot, free, False)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    if v[0] == 0 and platform.system() == "Darwin" and "arm" in platform.machine().lower() and ram_total:
        v = (int(ram_total * 0.65), int(min(ram_avail, ram_total) * 0.65), True)
    _GPU_CACHE.update(t=now, v=v)
    return v


def memory_state() -> Dict[str, Any]:
    """RAM/VRAM livres e núcleos agora (núcleo Rust quando há; senão Python)."""
    from . import native

    si = native.sys_info()
    total, free, unified = gpu_memory(int(si.get("ram_total") or 0), int(si.get("ram_avail") or 0))
    return {"ram_total": int(si.get("ram_total") or 0), "ram_avail": int(si.get("ram_avail") or 0), "vram_total": total, "vram_free": free, "unified": unified,
            "phys": int(si.get("physical") or 1), "logical": int(si.get("logical") or 1), "features": si.get("features", [])}
