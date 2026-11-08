"""Drivers do sistema operacional para o Computer Use: abrir arquivos/endereços, achar e abrir programas e jogos, capturar a tela e controlar teclado e mouse.

Um driver por sistema (Linux, macOS, Windows e Android), **só com a biblioteca padrão**: onde o sistema não traz a ferramenta (ex.: `xdotool` no Linux) o driver diz
**o que falta instalar** em `capabilities()` em vez de falhar no meio da tarefa. Nada aqui executa texto escrito pela IA: sempre listas de argumentos (nunca `shell=True`).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import guard


class DriverError(Exception):
    pass


def _run(cmd: List[str], timeout: float = 20, env: Optional[dict] = None, input_: Optional[bytes] = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout, env=env, input=input_, stdin=subprocess.DEVNULL if input_ is None else None, **_NOWIN)
    except FileNotFoundError:
        raise DriverError(f"Programa não encontrado: {cmd[0]}") from None
    except subprocess.TimeoutExpired:
        raise DriverError(f"{cmd[0]} demorou mais de {int(timeout)}s.") from None
    except OSError as exc:
        raise DriverError(f"{cmd[0]}: {exc}") from None


_NOWIN: Dict[str, Any] = {"creationflags": 0x08000000} if os.name == "nt" else {}   # CREATE_NO_WINDOW: sem janela de console piscando


def _detached(cmd: List[str], cwd: Optional[str] = None) -> int:
    """Abre um programa e segue em frente (sem esperar ele fechar)."""
    kw: Dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "cwd": cwd or None}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    try:
        return subprocess.Popen(cmd, **kw).pid
    except FileNotFoundError:
        raise DriverError(f"Programa não encontrado: {cmd[0]}") from None
    except OSError as exc:
        raise DriverError(f"Não consegui abrir {cmd[0]}: {exc}") from None


def _norm(s: str) -> str:
    import unicodedata

    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()).strip()


def _score(query: str, name: str, extra: str = "") -> int:
    q, n, e = _norm(query), _norm(name), _norm(extra)
    if not q:
        return 0
    if q == n:
        return 100
    if n.startswith(q):
        return 80
    if re.search(r"\b" + re.escape(q) + r"\b", n):
        return 70
    if q in n:
        return 55
    toks = q.split()
    if toks and all(t in n or t in e for t in toks):
        return 45
    if e and (q == e or q in e):
        return 35
    return 0


# --------------------------------------------------------------------------- teclas (nomes comuns → cada sistema)

_MODS = {"ctrl": "ctrl", "control": "ctrl", "alt": "alt", "option": "alt", "opt": "alt", "shift": "shift", "super": "super", "win": "super", "windows": "super", "cmd": "super", "command": "super", "meta": "super"}
_SPECIAL = {"enter": "Return", "return": "Return", "esc": "Escape", "escape": "Escape", "tab": "Tab", "space": "space", "backspace": "BackSpace", "delete": "Delete", "del": "Delete", "insert": "Insert",
            "up": "Up", "down": "Down", "left": "Left", "right": "Right", "home": "Home", "end": "End", "pageup": "Prior", "pgup": "Prior", "pagedown": "Next", "pgdn": "Next", "capslock": "Caps_Lock", "printscreen": "Print"}


def parse_combo(combo: str) -> Dict[str, Any]:
    """«Ctrl+Shift+S» → {"mods": ["ctrl","shift"], "key": "s"}. Uma tecla só, mais modificadores. Levanta DriverError se não entender."""
    parts = [p.strip() for p in re.split(r"\s*\+\s*", str(combo or "").strip()) if p.strip()]
    if not parts or len(parts) > 5:
        raise DriverError("Combinação de teclas inválida. Exemplos: «ctrl+s», «Return», «alt+F4», «ctrl+shift+t».")
    mods, key = [], ""
    for i, p in enumerate(parts):
        low = p.lower()
        if low in _MODS and i < len(parts) - 1:
            m = _MODS[low]
            if m not in mods:
                mods.append(m)
        elif key:
            raise DriverError("Use só uma tecla por vez (mais modificadores).")
        else:
            key = p
    if not key:
        raise DriverError("Faltou a tecla principal.")
    low = key.lower()
    if low in _SPECIAL:
        key = _SPECIAL[low]
    elif re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", low):
        key = "F" + low[1:]
    elif len(key) == 1:
        key = key.lower() if key.isalpha() else key
    else:
        raise DriverError(f"Tecla desconhecida: {key}")
    return {"mods": mods, "key": key}


# --------------------------------------------------------------------------- base


class Driver:
    name = "base"
    label = "Sistema"

    def __init__(self) -> None:
        self._apps: Optional[List[dict]] = None
        self._apps_t = 0.0
        self._lock = threading.Lock()

    # ----- capacidades (o que funciona agora e o que falta instalar)
    def capabilities(self) -> Dict[str, Any]:
        return {"files": {"ok": True}, "open": self._cap_open(), "apps": self._cap_apps(), "games": {"ok": True},
                "screenshot": self._cap_shot(), "keyboard": self._cap_keys(), "mouse": self._cap_mouse()}

    def _cap_open(self) -> Dict[str, Any]:
        return {"ok": False, "hint": ""}

    def _cap_apps(self) -> Dict[str, Any]:
        return {"ok": True}

    def _cap_shot(self) -> Dict[str, Any]:
        return {"ok": False, "hint": ""}

    def _cap_keys(self) -> Dict[str, Any]:
        return {"ok": False, "hint": ""}

    def _cap_mouse(self) -> Dict[str, Any]:
        return {"ok": False, "hint": ""}

    def gui_ok(self) -> bool:
        c = self.capabilities()
        return bool(c["screenshot"]["ok"] and (c["keyboard"]["ok"] or c["mouse"]["ok"]))

    # ----- abrir
    def open_target(self, target: str) -> None:  # pragma: no cover - por sistema
        raise DriverError("Abrir arquivos e endereços não está disponível neste sistema.")

    # ----- programas
    def _scan_apps(self) -> List[dict]:
        return []

    def apps(self, refresh: bool = False) -> List[dict]:
        with self._lock:
            if self._apps is None or refresh or time.time() - self._apps_t > 120:
                try:
                    self._apps = self._scan_apps()
                except Exception:  # noqa: BLE001 - listar programas nunca derruba a tarefa
                    self._apps = self._apps or []
                self._apps_t = time.time()
            return list(self._apps)

    def find_apps(self, query: str, limit: int = 8) -> List[dict]:
        scored = [(_score(query, a["name"], a.get("exec_name", "") + " " + a.get("id", "")), a) for a in self.apps()]
        scored = [x for x in scored if x[0] > 0]
        scored.sort(key=lambda x: (-x[0], len(x[1]["name"])))
        return [a for _, a in scored[:limit]]

    def launch_app(self, app: dict, files: List[str]) -> None:  # pragma: no cover
        raise DriverError("Abrir programas não está disponível neste sistema.")

    # ----- tela, teclado, mouse
    def screenshot(self, dest: Path) -> None:
        raise DriverError("Captura de tela indisponível neste sistema." + (" " + self._cap_shot().get("hint", "")).rstrip())

    def screen_size(self) -> Optional[tuple]:
        return None

    def type_text(self, text: str) -> None:
        raise DriverError("Digitar não está disponível. " + self._cap_keys().get("hint", ""))

    def press_keys(self, combo: str) -> None:
        raise DriverError("Teclas não estão disponíveis. " + self._cap_keys().get("hint", ""))

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        raise DriverError("Mouse não está disponível. " + self._cap_mouse().get("hint", ""))

    def scroll(self, dy: int) -> None:
        raise DriverError("Rolagem não está disponível. " + self._cap_mouse().get("hint", ""))

    # ----- jogos
    def steam_roots(self) -> List[Path]:
        return []

    def games(self, extra_dirs: Optional[List[str]] = None) -> List[dict]:
        out: List[dict] = []
        out += _steam_games(self.steam_roots())
        out += _lutris_games()
        out += _folder_games(self._game_dirs(extra_dirs or []))
        seen, uniq = set(), []
        for g in out:
            if g["id"] not in seen:
                seen.add(g["id"])
                uniq.append(g)
        return uniq

    def _game_dirs(self, extra: List[str]) -> List[Path]:
        h = guard.home()
        cands = [h / "Games", h / "Jogos", h / "games", h / "Desktop" / "Games", h / "Documents" / "Games", h / "Downloads"]
        dirs = []
        for d in [*cands, *[Path(x).expanduser() for x in extra if x]]:
            try:
                if d.is_dir():
                    dirs.append(d.resolve())
            except OSError:
                pass
        return dirs

    def launch_game(self, game: dict) -> str:
        src, gid = game.get("source"), str(game.get("raw_id", ""))
        if src == "steam" and gid.isdigit():
            try:
                self.open_target(f"steam://rungameid/{gid}")
            except DriverError:
                steam = shutil.which("steam")
                if not steam:
                    raise
                _detached([steam, "-applaunch", gid])
            return "Pedi à Steam para abrir o jogo."
        if src == "lutris" and re.fullmatch(r"[\w.-]+", gid):
            lutris = shutil.which("lutris")
            if not lutris:
                raise DriverError("O Lutris não está instalado.")
            _detached([lutris, f"lutris:rungameid/{gid}" if gid.isdigit() else f"lutris:{gid}"])
            return "Pedi ao Lutris para abrir o jogo."
        path = Path(game.get("path") or "")
        if src == "folder" and path.exists():
            return self.launch_path(path)
        raise DriverError("Não sei abrir este jogo.")

    def launch_path(self, path: Path) -> str:
        """Abre um jogo/programa que está numa pasta (executável, AppImage, .app ou página HTML)."""
        if not path.exists():
            raise DriverError("Arquivo não encontrado.")
        ext = path.suffix.lower()
        if ext in (".html", ".htm"):
            self.open_target(str(path))
            return "Abri o jogo no navegador."
        if ext in (".bat", ".cmd", ".ps1", ".vbs", ".sh", ".command", ".msi", ".jar"):
            raise DriverError("Scripts e instaladores não são executados pelo Computer Use.")
        return self._launch_binary(path)

    def _launch_binary(self, path: Path) -> str:  # pragma: no cover
        raise DriverError("Não sei abrir este tipo de arquivo neste sistema.")


# --------------------------------------------------------------------------- Linux


class LinuxDriver(Driver):
    name, label = "linux", "Linux"

    def _session(self) -> str:
        if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
            return "wayland"
        if os.environ.get("DISPLAY"):
            return "x11"
        if os.environ.get("WAYLAND_DISPLAY"):
            return "wayland"
        return "none"

    def _cap_open(self) -> Dict[str, Any]:
        ok = bool(shutil.which("xdg-open") or shutil.which("gio") or shutil.which("gnome-open") or shutil.which("kde-open"))
        return {"ok": ok, "hint": "" if ok else "Instale o xdg-utils (xdg-open)."}

    def _shot_tool(self) -> List[str]:
        s = self._session()
        order = [["grim", "{out}"], ["gnome-screenshot", "-f", "{out}"], ["spectacle", "-b", "-n", "-o", "{out}"], ["maim", "{out}"], ["scrot", "-o", "{out}"], ["import", "-window", "root", "{out}"]] if s == "wayland" else \
                [["maim", "{out}"], ["scrot", "-o", "{out}"], ["import", "-window", "root", "{out}"], ["gnome-screenshot", "-f", "{out}"], ["spectacle", "-b", "-n", "-o", "{out}"], ["grim", "{out}"]]
        for cmd in order:
            if shutil.which(cmd[0]):
                return cmd
        return []

    def _cap_shot(self) -> Dict[str, Any]:
        if self._session() == "none":
            return {"ok": False, "hint": "Sem ambiente gráfico (DISPLAY/WAYLAND_DISPLAY) nesta sessão."}
        if self._shot_tool():
            return {"ok": True, "how": self._shot_tool()[0]}
        return {"ok": False, "hint": "Instale uma ferramenta de captura: scrot, maim, gnome-screenshot ou grim (Wayland)."}

    def _keys_tool(self) -> str:
        s = self._session()
        if s == "none":
            return ""
        if shutil.which("xdotool") and os.environ.get("DISPLAY"):
            return "xdotool"
        if shutil.which("ydotool"):
            return "ydotool"
        if shutil.which("wtype") and s == "wayland":
            return "wtype"
        return ""

    def _cap_keys(self) -> Dict[str, Any]:
        t = self._keys_tool()
        if t:
            return {"ok": True, "how": t}
        if self._session() == "none":
            return {"ok": False, "hint": "Sem ambiente gráfico nesta sessão."}
        return {"ok": False, "hint": "Instale o xdotool (X11) ou o ydotool/wtype (Wayland) para o ASTA digitar e apertar teclas."}

    def _cap_mouse(self) -> Dict[str, Any]:
        t = self._keys_tool()
        if t in ("xdotool", "ydotool"):
            return {"ok": True, "how": t}
        return {"ok": False, "hint": "Instale o xdotool (X11) ou o ydotool (Wayland) para o ASTA mexer o mouse." if self._session() != "none" else "Sem ambiente gráfico nesta sessão."}

    def open_target(self, target: str) -> None:
        for cmd in (["xdg-open"], ["gio", "open"], ["kde-open"], ["gnome-open"]):
            if shutil.which(cmd[0]):
                _detached(cmd + [target])
                return
        raise DriverError("Não encontrei o xdg-open (pacote xdg-utils).")

    # ----- programas: arquivos .desktop
    def _desktop_dirs(self) -> List[Path]:
        dirs = [Path(p) / "applications" for p in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if p]
        dirs += [Path.home() / ".local/share/applications", Path("/var/lib/flatpak/exports/share/applications"), Path.home() / ".local/share/flatpak/exports/share/applications",
                 Path("/var/lib/snapd/desktop/applications")]
        return dirs

    def _scan_apps(self) -> List[dict]:
        out: Dict[str, dict] = {}
        for d in self._desktop_dirs():
            if not d.is_dir():
                continue
            for f in sorted(d.rglob("*.desktop")):
                try:
                    raw = f.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                sec = re.search(r"\[Desktop Entry\](.*?)(?:\n\[|\Z)", raw, re.S)
                if not sec:
                    continue
                kv: Dict[str, str] = {}
                for line in sec.group(1).splitlines():
                    if "=" in line and not line.lstrip().startswith("#"):
                        k, v = line.split("=", 1)
                        kv.setdefault(k.strip(), v.strip())
                if kv.get("Type", "Application") != "Application" or kv.get("NoDisplay", "").lower() == "true" or kv.get("Hidden", "").lower() == "true":
                    continue
                name, ex = kv.get("Name", ""), kv.get("Exec", "")
                if not name or not ex:
                    continue
                aid = f.stem
                try:
                    exec_name = Path(shlex.split(ex)[0]).name
                except (ValueError, IndexError):
                    exec_name = ""
                out.setdefault(aid, {"id": aid, "name": name, "exec": ex, "exec_name": exec_name, "desktop": str(f), "comment": kv.get("Comment", "")[:120],
                                     "categories": [c for c in kv.get("Categories", "").split(";") if c][:6], "source": "desktop"})
        return sorted(out.values(), key=lambda a: a["name"].lower())

    def launch_app(self, app: dict, files: List[str]) -> None:
        ex = app.get("exec") or ""
        try:
            argv = shlex.split(re.sub(r"%[fFuUdDnNickvm]", "", ex).replace("%%", "%"))
        except ValueError:
            argv = []
        if not argv:
            raise DriverError("Não entendi como abrir este programa.")
        if app.get("source") == "path":
            argv = [app["exec"]]
        if files:
            argv += files
        _detached(argv)

    # ----- tela / teclado / mouse
    def screenshot(self, dest: Path) -> None:
        cmd = self._shot_tool()
        if not cmd or self._session() == "none":
            raise DriverError("Captura de tela indisponível. " + self._cap_shot().get("hint", ""))
        r = _run([c.replace("{out}", str(dest)) for c in cmd], 20)
        if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 100:
            raise DriverError("A captura de tela falhou: " + (r.stderr.decode("utf-8", "ignore").strip()[:200] or cmd[0]))

    def screen_size(self) -> Optional[tuple]:
        if shutil.which("xdotool") and os.environ.get("DISPLAY"):
            try:
                m = re.search(r"WIDTH=(\d+)\s+HEIGHT=(\d+)", _run(["xdotool", "getdisplaygeometry", "--shell"], 5).stdout.decode())
                if m:
                    return int(m.group(1)), int(m.group(2))
            except DriverError:
                pass
        return None

    def type_text(self, text: str) -> None:
        t = self._keys_tool()
        if t == "xdotool":
            r = _run(["xdotool", "type", "--clearmodifiers", "--delay", "12", "--", text], 30 + len(text) * 0.05)
        elif t == "wtype":
            r = _run(["wtype", "--", text], 30 + len(text) * 0.05)
        elif t == "ydotool":
            r = _run(["ydotool", "type", "--", text], 30 + len(text) * 0.05)
        else:
            return super().type_text(text)
        if r.returncode != 0:
            raise DriverError("Não consegui digitar: " + r.stderr.decode("utf-8", "ignore").strip()[:200])

    def press_keys(self, combo: str) -> None:
        k = parse_combo(combo)
        t = self._keys_tool()
        chord = "+".join(k["mods"] + [k["key"]])
        if t == "xdotool":
            r = _run(["xdotool", "key", "--clearmodifiers", chord], 10)
        elif t == "wtype":
            argv = ["wtype"]
            for m in k["mods"]:
                argv += ["-M", {"ctrl": "ctrl", "alt": "alt", "shift": "shift", "super": "logo"}[m]]
            argv += ["-k", k["key"]] if len(k["key"]) > 1 else [k["key"]]
            for m in reversed(k["mods"]):
                argv += ["-m", {"ctrl": "ctrl", "alt": "alt", "shift": "shift", "super": "logo"}[m]]
            r = _run(argv, 10)
        elif t == "ydotool":
            return super().press_keys(combo)
        else:
            return super().press_keys(combo)
        if r.returncode != 0:
            raise DriverError("Não consegui apertar as teclas: " + r.stderr.decode("utf-8", "ignore").strip()[:200])

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        b = {"left": "1", "middle": "2", "right": "3"}.get(button, "1")
        t = self._keys_tool()
        if t == "xdotool":
            r = _run(["xdotool", "mousemove", str(int(x)), str(int(y)), "click", "--repeat", "2" if double else "1", b], 10)
        elif t == "ydotool":
            code = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}.get(button, "0xC0")
            _run(["ydotool", "mousemove", "--absolute", "-x", str(int(x)), "-y", str(int(y))], 10)
            r = _run(["ydotool", "click"] + ([code, code] if double else [code]), 10)
        else:
            return super().click(x, y, button, double)
        if r.returncode != 0:
            raise DriverError("Não consegui clicar: " + r.stderr.decode("utf-8", "ignore").strip()[:200])

    def scroll(self, dy: int) -> None:
        if self._keys_tool() == "xdotool":
            n = max(1, min(30, abs(int(dy))))
            _run(["xdotool", "click", "--repeat", str(n), "5" if dy > 0 else "4"], 10)
            return
        return super().scroll(dy)

    def steam_roots(self) -> List[Path]:
        h = Path.home()
        return [p for p in (h / ".steam/steam", h / ".local/share/Steam", h / ".var/app/com.valvesoftware.Steam/.local/share/Steam", h / "snap/steam/common/.local/share/Steam") if p.is_dir()]

    def _launch_binary(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext == ".exe":
            for runner in (["wine"], ["wine64"], ["proton"]):
                if shutil.which(runner[0]):
                    _detached(runner + [str(path)], cwd=str(path.parent))
                    return "Abri com o Wine."
            raise DriverError("É um jogo de Windows: instale o Wine (ou use o Lutris/Steam com Proton).")
        if ext == ".appimage" or os.access(path, os.X_OK):
            if not os.access(path, os.X_OK):
                raise DriverError("O arquivo não é executável (permissão).")
            _detached([str(path)], cwd=str(path.parent))
            return "Programa aberto."
        self.open_target(str(path))
        return "Aberto com o programa padrão."


# --------------------------------------------------------------------------- macOS


_MAC_KEYS = {"Return": 36, "Tab": 48, "space": 49, "BackSpace": 51, "Escape": 53, "Delete": 117, "Left": 123, "Right": 124, "Down": 125, "Up": 126, "Home": 115, "End": 119, "Prior": 116, "Next": 121,
             "F1": 122, "F2": 120, "F3": 99, "F4": 118, "F5": 96, "F6": 97, "F7": 98, "F8": 100, "F9": 101, "F10": 109, "F11": 103, "F12": 111}


class MacDriver(Driver):
    name, label = "macos", "macOS"

    def _cap_open(self) -> Dict[str, Any]:
        return {"ok": bool(shutil.which("open"))}

    def _cap_shot(self) -> Dict[str, Any]:
        ok = bool(shutil.which("screencapture"))
        return {"ok": ok, "how": "screencapture", "hint": "" if ok else "screencapture não encontrado.", "note": "Dê permissão de «Gravação de tela» ao ASTA em Ajustes do Sistema → Privacidade."}

    def _cap_keys(self) -> Dict[str, Any]:
        ok = bool(shutil.which("osascript"))
        return {"ok": ok, "how": "osascript", "hint": "" if ok else "osascript não encontrado.", "note": "Dê permissão de «Acessibilidade» ao ASTA em Ajustes do Sistema → Privacidade."}

    def _cap_mouse(self) -> Dict[str, Any]:
        ok = bool(shutil.which("cliclick") or shutil.which("osascript"))
        return {"ok": ok, "how": "cliclick" if shutil.which("cliclick") else "osascript", "hint": "" if ok else "osascript não encontrado.",
                "note": "Para cliques mais confiáveis instale o cliclick (brew install cliclick)."}

    def open_target(self, target: str) -> None:
        _detached(["open", target])

    def _scan_apps(self) -> List[dict]:
        out = []
        for base in (Path("/Applications"), Path("/Applications/Utilities"), Path("/System/Applications"), Path("/System/Applications/Utilities"), Path.home() / "Applications"):
            if not base.is_dir():
                continue
            try:
                for f in sorted(base.iterdir()):
                    if f.suffix == ".app":
                        out.append({"id": f.stem, "name": f.stem, "path": str(f), "exec_name": f.stem, "source": "app"})
            except OSError:
                continue
        return out

    def launch_app(self, app: dict, files: List[str]) -> None:
        if app.get("source") == "path":
            _detached([app["exec"]] + files)
            return
        _detached(["open", "-a", app["path"]] + (files if files else []))

    def _osa(self, script: str, timeout: float = 15) -> None:
        r = _run(["osascript", "-e", script], timeout)
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "ignore").strip()
            hint = " Libere a «Acessibilidade» para o ASTA em Ajustes do Sistema → Privacidade e segurança." if ("1002" in err or "not allowed" in err.lower() or "assistive" in err.lower()) else ""
            raise DriverError("O macOS recusou: " + err[:200] + hint)

    def screenshot(self, dest: Path) -> None:
        r = _run(["screencapture", "-x", "-t", "png", str(dest)], 20)
        if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 100:
            raise DriverError("A captura de tela falhou. Libere a «Gravação de tela» para o ASTA em Ajustes do Sistema → Privacidade e segurança.")

    def type_text(self, text: str) -> None:
        # o texto vai por uma variável do AppleScript lida do ambiente (nunca concatenado no script): sem injeção
        env = dict(os.environ, ASTA_TYPE=text)
        r = _run(["osascript", "-e", 'tell application "System Events" to keystroke (system attribute "ASTA_TYPE")'], 30 + len(text) * 0.05, env=env)
        if r.returncode != 0:
            raise DriverError("O macOS recusou digitar: " + r.stderr.decode("utf-8", "ignore").strip()[:200] + " (libere a Acessibilidade para o ASTA).")

    def press_keys(self, combo: str) -> None:
        k = parse_combo(combo)
        using = ", ".join({"ctrl": "control down", "alt": "option down", "shift": "shift down", "super": "command down"}[m] for m in k["mods"])
        suffix = f" using {{{using}}}" if using else ""
        if k["key"] in _MAC_KEYS:
            self._osa(f'tell application "System Events" to key code {_MAC_KEYS[k["key"]]}{suffix}')
        elif len(k["key"]) == 1:
            env = dict(os.environ, ASTA_KEY=k["key"])
            r = _run(["osascript", "-e", f'tell application "System Events" to keystroke (system attribute "ASTA_KEY"){suffix}'], 10, env=env)
            if r.returncode != 0:
                raise DriverError("O macOS recusou a tecla: " + r.stderr.decode("utf-8", "ignore").strip()[:200])
        else:
            raise DriverError(f"Tecla sem suporte no macOS: {k['key']}")

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        x, y = int(x), int(y)
        cc = shutil.which("cliclick")
        if cc:
            op = {"left": "dc" if double else "c", "right": "rc"}.get(button, "c")
            r = _run([cc, f"{op}:{x},{y}"], 10)
            if r.returncode != 0:
                raise DriverError("O cliclick falhou: " + r.stderr.decode("utf-8", "ignore").strip()[:200])
            return
        if button != "left":
            raise DriverError("Clique com o botão direito no macOS precisa do cliclick (brew install cliclick).")
        self._osa(f'tell application "System Events" to click at {{{x}, {y}}}')
        if double:
            self._osa(f'tell application "System Events" to click at {{{x}, {y}}}')

    def scroll(self, dy: int) -> None:
        for _ in range(max(1, min(10, abs(int(dy)) // 3 + 1))):
            self.press_keys("Next" if dy > 0 else "Prior")

    def steam_roots(self) -> List[Path]:
        p = Path.home() / "Library/Application Support/Steam"
        return [p] if p.is_dir() else []

    def _launch_binary(self, path: Path) -> str:
        if path.suffix.lower() == ".app" or os.access(path, os.X_OK) or path.suffix.lower() in (".dmg", ".pkg"):
            if path.suffix.lower() in (".dmg", ".pkg"):
                raise DriverError("Instaladores não são executados pelo Computer Use.")
            _detached(["open", str(path)])
            return "Aberto."
        _detached(["open", str(path)])
        return "Aberto com o programa padrão."


# --------------------------------------------------------------------------- Windows


class WinDriver(Driver):
    name, label = "windows", "Windows"

    def _cap_open(self) -> Dict[str, Any]:
        return {"ok": True}

    def _ps(self) -> str:
        return shutil.which("powershell") or shutil.which("pwsh") or ""

    def _cap_shot(self) -> Dict[str, Any]:
        ok = bool(self._ps())
        return {"ok": ok, "how": "powershell", "hint": "" if ok else "PowerShell não encontrado."}

    def _cap_keys(self) -> Dict[str, Any]:
        return {"ok": True, "how": "SendInput", "note": "Janelas de administrador não recebem teclas de um programa comum."}

    def _cap_mouse(self) -> Dict[str, Any]:
        return {"ok": True, "how": "SendInput"}

    def open_target(self, target: str) -> None:
        try:
            os.startfile(target)  # type: ignore[attr-defined]
        except OSError as exc:
            raise DriverError(f"Não consegui abrir: {exc}") from None

    def _scan_apps(self) -> List[dict]:
        out: Dict[str, dict] = {}
        ps = self._ps()
        if ps:
            try:
                r = _run([ps, "-NoProfile", "-NonInteractive", "-Command", "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"], 25)
                data = json.loads(r.stdout.decode("utf-8", "ignore") or "[]")
                for it in data if isinstance(data, list) else [data]:
                    if isinstance(it, dict) and it.get("Name") and it.get("AppID"):
                        out[it["AppID"]] = {"id": it["AppID"], "name": it["Name"], "appid": it["AppID"], "exec_name": it["Name"], "source": "startapps"}
            except (DriverError, ValueError):
                pass
        if not out:
            for base in (os.environ.get("ProgramData", ""), os.environ.get("APPDATA", "")):
                root = Path(base) / "Microsoft/Windows/Start Menu/Programs" if base else None
                if root and root.is_dir():
                    for f in root.rglob("*.lnk"):
                        out[str(f)] = {"id": f.stem, "name": f.stem, "lnk": str(f), "exec_name": f.stem, "source": "lnk"}
        return sorted(out.values(), key=lambda a: a["name"].lower())

    def launch_app(self, app: dict, files: List[str]) -> None:
        if app.get("source") == "path":
            _detached([app["exec"]] + files)
            return
        if files and app.get("lnk"):
            ps = self._ps()
            if ps:
                r = _run([ps, "-NoProfile", "-NonInteractive", "-Command", "(New-Object -ComObject WScript.Shell).CreateShortcut($env:ASTA_LNK).TargetPath"], 15, env=dict(os.environ, ASTA_LNK=app["lnk"]))
                target = r.stdout.decode("utf-8", "ignore").strip()
                if target and Path(target).exists():
                    _detached([target] + files)
                    return
        if app.get("appid"):
            _detached(["explorer.exe", "shell:AppsFolder\\" + app["appid"]])
        elif app.get("lnk"):
            os.startfile(app["lnk"])  # type: ignore[attr-defined]
        else:
            raise DriverError("Não entendi como abrir este programa.")

    def _dpi(self) -> None:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    def screenshot(self, dest: Path) -> None:
        ps = self._ps()
        if not ps:
            raise DriverError("PowerShell não encontrado.")
        script = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing; $b=[System.Windows.Forms.SystemInformation]::VirtualScreen; "
                  "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height; $g=[System.Drawing.Graphics]::FromImage($bmp); "
                  "$g.CopyFromScreen($b.Left,$b.Top,0,0,$bmp.Size); $bmp.Save($env:ASTA_SHOT,[System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()")
        r = _run([ps, "-NoProfile", "-NonInteractive", "-Command", script], 30, env=dict(os.environ, ASTA_SHOT=str(dest)))
        if r.returncode != 0 or not dest.exists():
            raise DriverError("A captura de tela falhou: " + r.stderr.decode("utf-8", "ignore").strip()[:200])

    def screen_size(self) -> Optional[tuple]:
        try:
            import ctypes

            self._dpi()
            u = ctypes.windll.user32  # type: ignore[attr-defined]
            return int(u.GetSystemMetrics(0)), int(u.GetSystemMetrics(1))
        except Exception:  # noqa: BLE001
            return None

    _VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "super": 0x5B, "Return": 0x0D, "Escape": 0x1B, "Tab": 0x09, "space": 0x20, "BackSpace": 0x08, "Delete": 0x2E, "Insert": 0x2D, "Up": 0x26, "Down": 0x28,
           "Left": 0x25, "Right": 0x27, "Home": 0x24, "End": 0x23, "Prior": 0x21, "Next": 0x22, "Caps_Lock": 0x14, "Print": 0x2C}

    def _vk(self, key: str) -> int:
        if key in self._VK:
            return self._VK[key]
        m = re.fullmatch(r"F(\d+)", key)
        if m:
            return 0x6F + int(m.group(1))
        if len(key) == 1:
            import ctypes

            r = ctypes.windll.user32.VkKeyScanW(ord(key))  # type: ignore[attr-defined]
            if r != -1:
                return r & 0xFF
        raise DriverError(f"Tecla sem suporte no Windows: {key}")

    def press_keys(self, combo: str) -> None:
        import ctypes

        k = parse_combo(combo)
        u = ctypes.windll.user32  # type: ignore[attr-defined]
        seq = [self._VK[m] for m in k["mods"]] + [self._vk(k["key"])]
        for vk in seq:
            u.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
        for vk in reversed(seq):
            u.keybd_event(vk, 0, 2, 0)

    def type_text(self, text: str) -> None:
        import ctypes
        from ctypes import wintypes

        class KI(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class MI(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class IU(ctypes.Union):
            _fields_ = [("ki", KI), ("mi", MI)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", IU)]

        send = ctypes.windll.user32.SendInput  # type: ignore[attr-defined]
        data = text.replace("\r\n", "\n").encode("utf-16-le")
        units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
        for i in range(0, len(units), 40):
            batch = []
            for cu in units[i:i + 40]:
                if cu == 10:   # quebra de linha = Enter
                    for flag in (0, 2):
                        batch.append(INPUT(1, IU(ki=KI(0x0D, 0, flag, 0, 0))))
                    continue
                for flag in (0x0004, 0x0004 | 0x0002):   # KEYEVENTF_UNICODE, depois KEYUP
                    batch.append(INPUT(1, IU(ki=KI(0, cu, flag, 0, 0))))
            arr = (INPUT * len(batch))(*batch)
            send(len(batch), arr, ctypes.sizeof(INPUT))
            time.sleep(0.01)

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        import ctypes

        self._dpi()
        u = ctypes.windll.user32  # type: ignore[attr-defined]
        u.SetCursorPos(int(x), int(y))
        down, up = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}.get(button, (0x0002, 0x0004))
        for _ in range(2 if double else 1):
            u.mouse_event(down, 0, 0, 0, 0)
            u.mouse_event(up, 0, 0, 0, 0)
            time.sleep(0.05)

    def scroll(self, dy: int) -> None:
        import ctypes

        ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(-dy) * 40 & 0xFFFFFFFF, 0)  # type: ignore[attr-defined]

    def steam_roots(self) -> List[Path]:
        roots: List[Path] = []
        try:
            import winreg  # type: ignore

            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"), (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        v = winreg.QueryValueEx(k, "SteamPath" if hive == winreg.HKEY_CURRENT_USER else "InstallPath")[0]
                        roots.append(Path(v))
                except OSError:
                    continue
        except ImportError:
            pass
        for p in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
            roots.append(Path(p))
        return [p for p in dict.fromkeys(roots) if p.is_dir()]

    def _launch_binary(self, path: Path) -> str:
        if path.suffix.lower() in (".msi", ".bat", ".cmd", ".ps1", ".vbs", ".jar"):
            raise DriverError("Instaladores e scripts não são executados pelo Computer Use.")
        if path.suffix.lower() == ".exe":
            _detached([str(path)], cwd=str(path.parent))
        else:
            self.open_target(str(path))
        return "Aberto."


# --------------------------------------------------------------------------- Android (o motor roda dentro do aparelho)


class AndroidDriver(Driver):
    name, label = "android", "Android"

    def _cap_open(self) -> Dict[str, Any]:
        ok = bool(shutil.which("am"))
        return {"ok": ok, "hint": "" if ok else "O Android deste aparelho não deixa o ASTA abrir outros apps. Conecte o app a um ASTA de computador para usar o Computer Use lá."}

    def _cap_apps(self) -> Dict[str, Any]:
        return {"ok": False, "hint": "O Android não deixa um app listar ou controlar os outros. Para controlar um computador, conecte o app ao ASTA dele (Configuração → Celular e tablet)."}

    def open_target(self, target: str) -> None:
        if not shutil.which("am"):
            raise DriverError(self._cap_open()["hint"])
        r = _run(["am", "start", "-a", "android.intent.action.VIEW", "-d", target], 15)
        if r.returncode != 0:
            raise DriverError("O Android recusou abrir: " + r.stderr.decode("utf-8", "ignore").strip()[:160])


class NullDriver(Driver):
    name, label = "other", "Sistema"


_driver: Optional[Driver] = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        if os.environ.get("ASTA_ANDROID") == "1":
            _driver = AndroidDriver()
        elif sys.platform == "win32":
            _driver = WinDriver()
        elif sys.platform == "darwin":
            _driver = MacDriver()
        elif sys.platform.startswith("linux") or sys.platform.startswith("freebsd"):
            _driver = LinuxDriver()
        else:
            _driver = NullDriver()
    return _driver


def set_driver(d: Optional[Driver]) -> None:
    """Para testes: troca o driver."""
    global _driver
    _driver = d


# --------------------------------------------------------------------------- jogos (Steam, Lutris, pastas)


def _vdf_pairs(raw: str) -> Dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in re.finditer(r'"([^"]+)"\s+"([^"]*)"', raw)}


def _steam_games(roots: List[Path]) -> List[dict]:
    libs: List[Path] = []
    for r in roots:
        libs.append(r / "steamapps")
        vdf = r / "steamapps" / "libraryfolders.vdf"
        try:
            raw = vdf.read_text(encoding="utf-8", errors="ignore") if vdf.is_file() else ""
        except OSError:
            raw = ""
        for m in re.finditer(r'"path"\s+"([^"]+)"', raw):
            libs.append(Path(m.group(1).replace("\\\\", "\\")) / "steamapps")
    games, seen = [], set()
    for lib in dict.fromkeys(libs):
        try:
            files = sorted(lib.glob("appmanifest_*.acf")) if lib.is_dir() else []
        except OSError:
            files = []
        for f in files:
            try:
                kv = _vdf_pairs(f.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            appid, name = kv.get("appid", ""), kv.get("name", "")
            if not appid.isdigit() or not name or appid in seen:
                continue
            if re.search(r"steamworks common|proton|steam linux runtime|steamvr", name, re.I):
                continue
            seen.add(appid)
            games.append({"id": f"steam:{appid}", "raw_id": appid, "name": name, "source": "steam", "installed": True})
    return games


def _lutris_games() -> List[dict]:
    lutris = shutil.which("lutris")
    out: List[dict] = []
    if lutris:
        try:
            r = _run([lutris, "--list-games", "--json"], 20)
            data = json.loads(r.stdout.decode("utf-8", "ignore") or "[]")
            for g in data if isinstance(data, list) else []:
                if isinstance(g, dict) and g.get("name") and g.get("id") is not None:
                    out.append({"id": f"lutris:{g['id']}", "raw_id": str(g["id"]), "name": str(g["name"]), "source": "lutris", "installed": True, "runner": str(g.get("runner") or "")})
        except (DriverError, ValueError):
            pass
    if not out:
        d = Path.home() / ".config/lutris/games"
        if d.is_dir():
            for f in sorted(d.glob("*.yml")):
                slug = re.sub(r"-\d{9,}$", "", f.stem)
                out.append({"id": f"lutris:{f.stem}", "raw_id": f.stem, "name": slug.replace("-", " ").title(), "source": "lutris", "installed": True})
    return out


_GAME_EXT = (".exe", ".appimage", ".x86_64", ".app", ".html", ".htm", ".sh")
_SKIP_EXE = re.compile(r"unins|setup|install|redist|vcredist|dxsetup|crashhandler|crashreport|updater|launcher_helper|helper|dotnet|vc_redist|notification", re.I)


def _folder_games(dirs: List[Path], depth: int = 3, limit: int = 120) -> List[dict]:
    out: List[dict] = []
    for base in dirs:
        base_depth = len(base.parts)
        try:
            for root, dnames, fnames in os.walk(base):
                rp = Path(root)
                if len(rp.parts) - base_depth >= depth:
                    dnames[:] = []
                dnames[:] = [d for d in dnames if not d.startswith(".") and d.lower() not in ("node_modules", "__pycache__", "saves", "save", "data", "assets", "resources", "redist")]
                for n in list(fnames) + [d for d in dnames if d.lower().endswith(".app")]:
                    low = n.lower()
                    if not low.endswith(_GAME_EXT) or _SKIP_EXE.search(low):
                        continue
                    if low.endswith((".html", ".htm")) and low not in ("index.html", "game.html", "play.html"):
                        continue
                    if low.endswith(".sh") and rp == base:
                        continue
                    p = rp / n
                    name = rp.name if (low in ("index.html", "game.html", "play.html") or rp != base) and rp != base else p.stem
                    out.append({"id": "folder:" + str(p), "raw_id": str(p), "name": name.replace("_", " "), "source": "folder", "path": str(p), "installed": True})
                    if len(out) >= limit:
                        return out
        except OSError:
            continue
    return out


def find_games(games: List[dict], query: str, limit: int = 8) -> List[dict]:
    q = str(query or "").strip()
    if not q:
        return games[:limit]
    by_id = [g for g in games if g["id"].lower() == q.lower() or str(g.get("raw_id", "")).lower() == q.lower()]
    if by_id:
        return by_id[:1]
    scored = [(_score(q, g["name"]), g) for g in games]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (-x[0], len(x[1]["name"])))
    return [g for _, g in scored[:limit]]


def tempdir() -> Path:
    return Path(tempfile.gettempdir())
