"""Núcleo nativo (Rust) do ASTA — opcional, com equivalente em Python puro para tudo.

A biblioteca `libasta_core` (código em `asta/native/src/lib.rs`, só biblioteca padrão do Rust) acelera a síntese de áudio do Canvas Demo (música, efeitos, voz) e
a conversão para PCM, trabalhando em buffers compartilhados (`array('d')`) em vez de um objeto Python por amostra: bem mais rápido e com uma fração da RAM.
Ela é carregada com `ctypes` (nada para instalar no Python). Para compilar:  `asta native build`  (precisa do Rust — https://rustup.rs).
Sem a biblioteca (ou com `ASTA_NO_NATIVE=1`), o ASTA usa as versões em Python, que dão o mesmo resultado (exceto o ruído, que usa outro gerador de números aleatórios).
"""
from __future__ import annotations

import ctypes
import math
import os
import random
import shutil
import subprocess
import sys
import threading
from array import array
from pathlib import Path
from typing import Any, Dict, Optional

ABI = 1
SRC = Path(__file__).resolve().parent
_LIB: Any = None
_TRIED = False
_REASON = ""
_LOCK = threading.Lock()
WAVES = {"sine": 0, "square": 1, "saw": 2, "triangle": 3}


def _libname() -> str:
    return "asta_core.dll" if os.name == "nt" else ("libasta_core.dylib" if sys.platform == "darwin" else "libasta_core.so")


def native_dir() -> Path:
    return Path(os.environ.get("ASTA_HOME") or Path.home() / ".asta") / "native"


def _candidates():
    if os.environ.get("ASTA_NATIVE_LIB"):
        yield Path(os.environ["ASTA_NATIVE_LIB"])
    yield native_dir() / _libname()
    yield SRC / _libname()


def _bind(lib: Any) -> None:
    dp, cp = ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int16)
    lib.asta_abi_version.restype = ctypes.c_uint32
    lib.asta_tone.argtypes = [dp, ctypes.c_size_t, ctypes.c_double, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t]
    lib.asta_noise.argtypes = [dp, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double]
    lib.asta_mix_add.argtypes = [dp, ctypes.c_size_t, dp, ctypes.c_size_t, ctypes.c_size_t]
    lib.asta_fade_out.argtypes = [dp, ctypes.c_size_t, ctypes.c_size_t]
    lib.asta_pcm16.argtypes = [dp, ctypes.c_size_t, cp, ctypes.c_double]
    lib.asta_mul.argtypes = [dp, dp, ctypes.c_size_t, dp]


def load(force: bool = False) -> Any:
    """A biblioteca carregada, ou None (e `status()['reason']` diz por quê)."""
    global _LIB, _TRIED, _REASON
    with _LOCK:
        if _TRIED and not force:
            return _LIB
        _TRIED, _LIB = True, None
        if os.environ.get("ASTA_NO_NATIVE", "") not in ("", "0"):
            _REASON = "desligado por ASTA_NO_NATIVE"
            return None
        for path in _candidates():
            if not path.is_file():
                continue
            try:
                lib = ctypes.CDLL(str(path))
                if lib.asta_abi_version() != ABI:
                    _REASON = f"{path.name}: versão da interface diferente (recompile com `asta native setup`)"
                    continue
                _bind(lib)
                _LIB, _REASON = lib, str(path)
                return lib
            except (OSError, AttributeError) as exc:
                _REASON = f"{path.name}: {exc}"
        _REASON = _REASON or "biblioteca não compilada (opcional: `asta native setup` instala o Rust e compila)"
        return None


def available() -> bool:
    return load() is not None


def find_tool(name: str) -> Optional[str]:
    """O caminho de `cargo`/`rustup`: no PATH, ou na pasta do rustup (~/.cargo/bin; CARGO_HOME) — o rustup recém-instalado ainda não está no PATH desta sessão."""
    exe = shutil.which(name)
    if exe:
        return exe
    home = Path(os.environ.get("CARGO_HOME") or Path.home() / ".cargo")
    for cand in (home / "bin" / name, home / "bin" / (name + ".exe")):
        if cand.is_file():
            return str(cand)
    return None


def status() -> Dict[str, Any]:
    lib = load()
    return {"active": lib is not None, "reason": _REASON, "cargo": bool(find_tool("cargo")), "rustup": bool(find_tool("rustup")), "path": _REASON if lib is not None else ""}


def rust_version() -> str:
    cargo = find_tool("cargo")
    if not cargo:
        return ""
    try:
        return subprocess.run([cargo, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def install_rust() -> int:
    """Instala o Rust (rustup, perfil mínimo, toolchain estável) na pasta do usuário — sem sudo. Devolve 0 se o `cargo` ficou disponível."""
    import tempfile
    import urllib.request

    from ..termi18n import _

    if find_tool("cargo"):
        return 0
    print(_("Instalando o Rust (rustup, perfil mínimo) na sua pasta de usuário …"))
    try:
        if os.name == "nt":
            import platform

            arch = "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else ("i686" if platform.architecture()[0] == "32bit" else "x86_64")
            with urllib.request.urlopen(f"https://win.rustup.rs/{arch}", timeout=60) as r:
                data = r.read()
            with tempfile.NamedTemporaryFile("wb", suffix=".exe", delete=False) as fh:
                fh.write(data)
                exe = fh.name
            cmd = [exe, "-y", "--profile", "minimal", "--default-toolchain", "stable"]
        else:
            with urllib.request.urlopen("https://sh.rustup.rs", timeout=60) as r:
                data = r.read()
            with tempfile.NamedTemporaryFile("wb", suffix=".sh", delete=False) as fh:
                fh.write(data)
                exe = fh.name
            cmd = ["sh", exe, "-y", "--profile", "minimal", "--default-toolchain", "stable"]
        res = subprocess.run(cmd)
    except Exception as exc:  # noqa: BLE001  (sem internet, antivírus, sem permissão…)
        print(_("Não consegui baixar/instalar o Rust agora ({e}). Instale pelo https://rustup.rs e rode:  asta native setup", e=str(exc)[:160]))
        return 1
    finally:
        try:
            os.unlink(exe)
        except Exception:  # noqa: BLE001
            pass
    if res.returncode != 0 or not find_tool("cargo"):
        print(_("A instalação do Rust não terminou. Instale pelo https://rustup.rs e rode:  asta native setup"))
        return 1
    print(_("Rust instalado: {v}", v=rust_version()))
    return 0


def update_rust() -> int:
    """Atualiza o Rust (toolchain estável) com o rustup. Rust instalado por outro meio (gerenciador de pacotes) é atualizado por ele."""
    from ..termi18n import _

    rustup = find_tool("rustup")
    if not rustup:
        print(_("O Rust deste computador não foi instalado pelo rustup: atualize-o pelo mesmo meio em que o instalou (ex.: gerenciador de pacotes). Sigo com a versão atual: {v}", v=rust_version() or "?"))
        return 0
    print(_("Atualizando o Rust (rustup update stable) …"))
    res = subprocess.run([rustup, "update", "stable", "--no-self-update"] if os.name != "nt" else [rustup, "update", "stable"])
    if res.returncode != 0:
        print(_("Não consegui atualizar o Rust agora (sem internet?); sigo com a versão atual."))
    return 0


def build(verbose: bool = True) -> int:
    """Compila o núcleo com o `cargo` e instala em ~/.asta/native. Devolve o código de saída (0 = ok)."""
    from ..termi18n import _

    cargo = find_tool("cargo")
    if not cargo:
        print(_("O Rust (cargo) não está instalado. É opcional: o ASTA funciona igual em Python, só mais devagar na síntese de áudio.\nInstale com:  asta native install   (ou pelo https://rustup.rs)"))
        return 1
    if not (SRC / "Cargo.toml").is_file():
        print(_("Código-fonte do núcleo não encontrado nesta instalação."))
        return 1
    dest = native_dir()
    dest.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CARGO_TARGET_DIR=str(dest / "target"))
    res = subprocess.run([cargo, "build", "--release", "--manifest-path", str(SRC / "Cargo.toml")], env=env, capture_output=not verbose, text=True)
    if res.returncode != 0:
        if not verbose:
            print((res.stderr or "")[-800:])
        print(_("Não foi possível compilar o núcleo (o ASTA segue em Python)."))
        return res.returncode
    built = dest / "target" / "release" / _libname()
    if not built.is_file():
        print(_("Compilou, mas não achei a biblioteca gerada."))
        return 1
    shutil.copyfile(built, dest / _libname())
    shutil.rmtree(dest / "target", ignore_errors=True)  # só a biblioteca fica (a pasta de compilação ocupa centenas de MB)
    load(force=True)
    print(_("Núcleo em Rust ativo:"), status()["path"] if available() else status()["reason"])
    return 0 if available() else 1


def _build_hint() -> str:
    from ..termi18n import _

    if os.name == "nt":
        return _("No Windows o Rust precisa das «Ferramentas de Build do Visual Studio» (carga «Desenvolvimento para desktop com C++»): https://visualstudio.microsoft.com/visual-cpp-build-tools/ — depois rode:  asta native setup")
    if sys.platform == "darwin":
        return _("No macOS o Rust precisa das ferramentas de linha de comando da Apple. Instale com:  xcode-select --install   — depois rode:  asta native setup")
    return _("No Linux o Rust precisa de um compilador C (gcc/cc). Ex.: sudo apt install build-essential   (ou o equivalente da sua distribuição) — depois rode:  asta native setup")


def setup(mode: str = "yes", ask: Any = None) -> int:
    """Instala/atualiza o Rust e recompila o núcleo do ASTA. `mode`: "yes" (padrão: instala/atualiza e recompila sozinho), "no" (não mexe) ou "ask" (pergunta no terminal). Devolve 0 em geral (o núcleo é opcional: o ASTA funciona igual em Python)."""
    from ..termi18n import _

    mode = (mode or "yes").strip().lower()
    if mode in ("no", "none", "0", "skip", "nao", "não", "n"):
        print(_("Rust: pulado (ASTA_RUST=no)."))
        return 0
    mode = "ask" if mode == "ask" else "yes"   # padrão: automático (como as bibliotecas e os modelos); "ask" só se pedido
    have = bool(find_tool("cargo"))
    if mode == "ask":
        answer = ask(_("Atualizar o Rust e recompilar o núcleo do ASTA (mais rápido e leve)?") if have else
                     _("Instalar o Rust (perto de 300 MB, na sua pasta de usuário) para deixar o ASTA mais rápido e leve?"), default=have) if ask else None
        if answer is None:
            if not have:
                print(_("Rust: não há um terminal para perguntar, então não instalei nada. Para instalar: asta native setup --rust yes   (ou ASTA_RUST=yes no instalador)."))
                return 0
        elif not answer:
            print(_("Ok, sem Rust por agora. Quando quiser:  asta native setup"))
            return 0
    if not have and install_rust() != 0:
        return 0
    update_rust()
    if build() != 0:
        print(_build_hint())
    return 0


# --------------------------------------------------------------------------- funções (nativas, com equivalente em Python)


def _ptr(a: "array[float]"):
    addr, _ = a.buffer_info()
    return ctypes.cast(addr, ctypes.POINTER(ctypes.c_double))


def zeros(n: int) -> "array[float]":
    return array("d", bytes(8 * max(0, n)))


def tone(freq: float, dur: float, wave: str = "sine", vol: float = 0.5, sweep: Optional[float] = None, sr: int = 44100) -> "array[float]":
    n = int(dur * sr)
    na, nr = max(1, int(0.005 * sr)), max(1, int(min(0.25, dur / 2) * sr))
    out = zeros(n)
    if n <= 0:
        return out
    lib = load()
    if lib is not None:
        lib.asta_tone(_ptr(out), n, freq, WAVES.get(wave, 0), vol, sweep or 0.0, 0 if sweep is None else 1, float(sr), na, nr)
        return out
    ph, tw = 0.0, 2 * math.pi
    for i in range(n):
        f = freq if sweep is None else freq + (sweep - freq) * i / max(1, n - 1)
        ph += tw * f / sr
        s = math.sin(ph) if wave == "sine" else (1.0 if math.sin(ph) >= 0 else -1.0) if wave == "square" else (2 * (ph / tw % 1) - 1) if wave == "saw" else (2 * abs(2 * (ph / tw % 1) - 1) - 1)
        out[i] = s * vol * min(1.0, i / na) * min(1.0, (n - i) / nr)
    return out


def noise(dur: float, rnd: random.Random, vol: float = 0.4, lp: float = 0.2, decay: float = 0.0, lfo: float = 0.0, sr: int = 44100) -> "array[float]":
    n = int(dur * sr)
    out = zeros(n)
    if n <= 0:
        return out
    lib = load()
    if lib is not None:
        lib.asta_noise(_ptr(out), n, rnd.getrandbits(64), vol, lp, decay, lfo, float(sr))
        return out
    y = 0.0
    for i in range(n):
        y += lp * (rnd.uniform(-1, 1) - y)
        a = vol * (math.exp(-decay * i / sr) if decay else 1.0)
        if lfo:
            a *= 0.65 + 0.35 * math.sin(2 * math.pi * lfo * i / sr)
        out[i] = y * a
    return out


def mix_add(dst: "array[float]", src: Any, offset: int) -> None:
    """dst[offset + i] += src[i] (corta no fim de dst); altera `dst` no lugar."""
    if not isinstance(src, array):
        src = array("d", src)
    n, m = len(dst), len(src)
    if offset >= n or m == 0:
        return
    lib = load()
    if lib is not None and offset >= 0:
        lib.asta_mix_add(_ptr(dst), n, _ptr(src), m, offset)
        return
    for i in range(max(0, -offset), min(m, n - offset)):
        dst[offset + i] += src[i]


def fade_out(buf: "array[float]", fade: int) -> None:
    n = len(buf)
    fade = min(fade, n)
    if fade <= 0:
        return
    lib = load()
    if lib is not None:
        lib.asta_fade_out(_ptr(buf), n, fade)
        return
    for i in range(fade):
        buf[n - 1 - i] *= i / fade


def pcm16(samples: Any, limit: float = 0.85) -> bytes:
    """Amostras (-1..1) → bytes PCM de 16 bits, normalizando o pico quando passa de `limit`."""
    if not isinstance(samples, array):
        samples = array("d", samples)
    n = len(samples)
    if n == 0:
        return b""
    lib = load()
    if lib is not None:
        out = array("h", bytes(2 * n))
        addr, _ = out.buffer_info()
        lib.asta_pcm16(_ptr(samples), n, ctypes.cast(addr, ctypes.POINTER(ctypes.c_int16)), limit)
        return out.tobytes() if sys.byteorder == "little" else _swap(out)
    peak = max(1e-6, max(abs(s) for s in samples))
    k = limit / peak if peak > limit else 1.0
    return array("h", (int(max(-1.0, min(1.0, s * k)) * 32767) for s in samples)).tobytes()


def _swap(a: "array[int]") -> bytes:  # pragma: no cover  (máquinas big-endian)
    a.byteswap()
    return a.tobytes()
