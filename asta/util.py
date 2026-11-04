"""Utilitários sem dependências: ids, JSON atômico, hardware, coerção numérica."""
from __future__ import annotations

import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def asta_home() -> Path:
    """Pasta de dados do usuário (ASTA_HOME ou ~/.asta)."""
    custom = os.environ.get("ASTA_HOME")
    base = Path(custom).expanduser() if custom else Path.home() / ".asta"
    base.mkdir(parents=True, exist_ok=True)
    return base


def new_id(prefix: str = "") -> str:
    return prefix + secrets.token_hex(5)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(text: str, default: str = "item", max_len: int = 48) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:max_len].strip("-")) or default


def safe_filename(name: str, default: str = "file") -> str:
    """Nome de arquivo seguro (sem diretórios, sem caracteres de controle)."""
    name = os.path.basename(str(name or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f<>:\"|?*]", "_", name).strip(". ")
    return name[:120] or default


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data: Any, private: bool = False) -> None:
    """Escrita atômica: grava em arquivo temporário e troca."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        if private:
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def num(value: Any, default: float, lo: Optional[float] = None, hi: Optional[float] = None) -> float:
    """Converte para número com limites; valores inválidos viram `default`."""
    try:
        out = float(value)
        if out != out or out in (float("inf"), float("-inf")):
            raise ValueError
    except (TypeError, ValueError):
        out = float(default)
    if lo is not None:
        out = max(lo, out)
    if hi is not None:
        out = min(hi, out)
    return out


def text(value: Any, default: str = "", max_len: int = 4000) -> str:
    if value is None:
        return default
    s = str(value).strip()
    return s[:max_len] if s else default


def deep_merge(base: dict, patch: dict) -> dict:
    """Mescla `patch` em `base` recursivamente (retorna novo dict)."""
    out = dict(base)
    for key, val in (patch or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


# --------------------------------------------------------------------------- hardware


def _ram_gb() -> Optional[float]:
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemTotal"):
                        return int(line.split()[1]) / 1024 / 1024
        elif sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3)
            return int(out.stdout.strip()) / 1024 ** 3
        elif os.name == "nt":
            import ctypes

            class MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MemStatus()
            stat.dwLength = ctypes.sizeof(MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
            return stat.ullTotalPhys / 1024 ** 3
    except Exception:
        return None
    return None


def _gpu_name() -> Optional[str]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=3,
        )
        line = out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else ""
        return line or None
    except Exception:
        return None


_HW_CACHE: Optional[dict] = None


def hardware_info(refresh: bool = False) -> dict:
    """Detecta CPU/RAM (e GPU NVIDIA, se houver) e classifica em low/medium/high."""
    global _HW_CACHE
    if _HW_CACHE is not None and not refresh:
        return _HW_CACHE
    cpus = os.cpu_count() or 2
    ram = _ram_gb()
    eff_ram = ram if ram is not None else 8.0
    if eff_ram < 6 or cpus <= 2:
        tier = "low"
    elif eff_ram >= 16 and cpus >= 8:
        tier = "high"
    else:
        tier = "medium"
    _HW_CACHE = {
        "os": platform.system() or sys.platform,
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cpus": cpus,
        "ram_gb": round(ram, 1) if ram is not None else None,
        "gpu": _gpu_name(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "tier": tier,
    }
    return _HW_CACHE
