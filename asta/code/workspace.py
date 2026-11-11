"""O workspace de uma sessão do Code: a pasta do projeto + as operações de arquivo que as ferramentas usam + o **diário de mudanças** que permite desfazer.

Toda operação passa por `guard.check_path` (nada fora do projeto, nada de segredos, nada de `.git/`). Antes de qualquer mudança o conteúdo anterior vai para
`<sessão>/backups/<n>`; o diário (lista de dicts, guardada no documento da sessão) registra *o que* mudou e *em qual rodada*. Desfazer repõe os backups na ordem inversa.
O diário também alimenta o diff mostrado na tela e entregue ao Revisor — vale para qualquer pasta, tenha ela Git ou não.
"""
from __future__ import annotations

import difflib
import fnmatch
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import guard
from .langs import SKIP_DIRS

MAX_WRITE = 2 * 1024 * 1024
MAX_READ_FILE = 6 * 1024 * 1024
MAX_SEARCH_FILE = 1_500_000


class WorkspaceError(Exception):
    """Erro de uso de uma operação (arquivo inexistente, texto não encontrado, binário…). A mensagem volta para a IA, que escolhe outro caminho."""


def is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def _decode(data: bytes, name: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise WorkspaceError(f"«{name}» não é texto UTF-8 (binário ou outra codificação).") from None


def _atomic_write(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".asta-tmp-{threading.get_ident()}-{p.name}")
    try:
        tmp.write_bytes(data)
        try:
            shutil.copymode(p, tmp)   # mantém o bit de executável de um script que está sendo editado
        except OSError:
            pass
        tmp.replace(p)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


class Workspace:
    def __init__(self, root: Path, session_dir: Path, journal: Optional[List[Dict[str, Any]]] = None, extra_read: Iterable[Path] = ()):
        self.root = Path(root).resolve()
        self.session_dir = Path(session_dir)
        self.backups = self.session_dir / "backups"
        self.journal: List[Dict[str, Any]] = journal if journal is not None else []
        self.extra_read = [Path(x).resolve() for x in extra_read]
        self.lock = threading.RLock()
        self.path_locks: Dict[str, threading.RLock] = {}
        self._pl = threading.Lock()
        self.run = ""

    # ----------------------------------------------------------------- caminhos
    def rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.root)).replace("\\", "/") or "."
        except ValueError:
            return str(p)

    def check(self, path: str, op: str) -> Path:
        return guard.check_path(path, op, self.root, extra_read=self.extra_read)

    def _lock_for(self, p: Path) -> threading.RLock:
        with self._pl:
            return self.path_locks.setdefault(str(p), threading.RLock())

    # ----------------------------------------------------------------- diário
    def _backup(self, p: Path) -> Tuple[bool, str]:
        """Guarda o conteúdo atual de `p` (se existir) e devolve (existia, nome do backup)."""
        if not p.exists():
            return False, ""
        self.backups.mkdir(parents=True, exist_ok=True)
        name = f"{int(time.time() * 1000)}-{len(self.journal)}-{threading.get_ident() % 1000}"
        dest = self.backups / name
        if p.is_dir():
            shutil.copytree(p, dest, symlinks=True)
        else:
            shutil.copy2(p, dest)
        return True, name

    def _mkparents(self, p: Path) -> None:
        """Cria as pastas que faltam acima de `p` e registra cada uma no diário (desfazer remove as que ficarem vazias)."""
        missing: List[Path] = []
        d = p.parent
        while not d.exists() and guard._inside(d, self.root) and d != self.root:
            missing.append(d)
            d = d.parent
        for d in reversed(missing):
            try:
                d.mkdir(exist_ok=True)
            except OSError:
                break
            self._log("mkdir", d, False, "")

    def _log(self, op: str, p: Path, existed: bool, backup: str, dst: Optional[Path] = None) -> None:
        with self.lock:
            e = {"n": len(self.journal) + 1, "run": self.run, "op": op, "path": self.rel(p), "existed": existed, "backup": backup, "undone": False, "ts": time.time()}
            if dst is not None:
                e["dst"] = self.rel(dst)
            self.journal.append(e)

    # ----------------------------------------------------------------- leitura
    def list_dir(self, path: str = ".", depth: int = 1, limit: int = 200, hidden: bool = False) -> str:
        p = self.check(path, "read")
        if not p.is_dir():
            raise WorkspaceError(f"«{path}» não é uma pasta.")
        depth, limit = max(1, min(int(depth or 1), 8)), max(10, min(int(limit or 200), 2000))
        lines: List[str] = []

        def walk(d: Path, level: int, prefix: str) -> None:
            if len(lines) >= limit:
                return
            try:
                entries = sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except OSError as exc:
                lines.append(f"{prefix}(sem acesso: {exc.strerror})")
                return
            for e in entries:
                if len(lines) >= limit:
                    lines.append(f"{prefix}… (lista cortada em {limit} itens)")
                    return
                if (e.name in SKIP_DIRS and e.is_dir()) or (not hidden and e.name.startswith(".") and e.name not in (".github", ".gitignore", ".env.example")):
                    if e.is_dir() and e.name in SKIP_DIRS:
                        lines.append(f"{prefix}{e.name}/  (ignorada)")
                    continue
                if e.is_dir():
                    lines.append(f"{prefix}{e.name}/")
                    if level < depth:
                        walk(e, level + 1, prefix + "  ")
                else:
                    try:
                        sz = e.stat().st_size
                    except OSError:
                        sz = 0
                    lines.append(f"{prefix}{e.name}  ({_human(sz)})")

        walk(p, 1, "")
        return f"{self.rel(p)}/\n" + ("\n".join(lines) if lines else "(vazia)")

    def read_file(self, path: str, start: int = 1, end: int = 0, max_chars: int = 16000) -> str:
        p = self.check(path, "read")
        if not p.is_file():
            raise WorkspaceError(f"«{path}» não existe ou não é um arquivo." + self._suggest(p))
        if p.stat().st_size > MAX_READ_FILE:
            raise WorkspaceError(f"«{path}» tem {_human(p.stat().st_size)}: grande demais para ler inteiro. Use search_code ou read_file com start/end num arquivo menor.")
        data = p.read_bytes()
        if is_binary(data):
            raise WorkspaceError(f"«{path}» é binário ({_human(len(data))}). Para imagens use view_image.")
        text = _decode(data, p.name)
        lines = text.splitlines()
        total = len(lines)
        start = max(1, int(start or 1))
        stop = total if not end or int(end) <= 0 else min(total, int(end))
        max_chars = max(500, min(int(max_chars or 16000), 60000))
        out: List[str] = []
        used = 0
        last = start - 1
        for i in range(start - 1, stop):
            row = f"{i + 1:>5}\t{lines[i]}"
            if len(row) > 600:
                row = row[:600] + " …"
            if used + len(row) > max_chars and out:
                break
            out.append(row)
            used += len(row) + 1
            last = i + 1
        head = f"{self.rel(p)} — {total} linha(s)" + (f" · mostrando {start}–{last}" if (start > 1 or last < total) else "")
        tail = f"\n… (continua: use start={last + 1})" if last < stop else ""
        if total == 0:
            return head + "\n(arquivo vazio)"
        if not out:
            return head + "\n(sem linhas nesse intervalo)"
        return head + "\n" + "\n".join(out) + tail

    def _suggest(self, p: Path) -> str:
        try:
            names = [x.name for x in p.parent.iterdir()] if p.parent.is_dir() else []
        except OSError:
            names = []
        close = difflib.get_close_matches(p.name, names, n=3, cutoff=0.6)
        return f" Parecidos: {', '.join(close)}." if close else ""

    def image_path(self, path: str) -> Path:
        p = self.check(path, "read")
        if not p.is_file() or p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
            raise WorkspaceError("Só dá para ver arquivos de imagem (png, jpg, gif, webp, bmp).")
        if p.stat().st_size > 12 * 1024 * 1024:
            raise WorkspaceError("A imagem é grande demais (mais de 12 MB).")
        return p

    def iter_files(self, base: Path, glob: str = "") -> Iterable[Path]:
        pats = [g.strip() for g in re.split(r"[,;]", glob) if g.strip()]
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and d != ".git")
            for fn in sorted(filenames):
                fp = Path(dirpath) / fn
                if pats:
                    rel = self.rel(fp)
                    if not any(fnmatch.fnmatch(fn, g) or fnmatch.fnmatch(rel, g) for g in pats):
                        continue
                yield fp

    def search(self, pattern: str, path: str = ".", glob: str = "", ignore_case: bool = False, limit: int = 100, context: int = 0) -> str:
        base = self.check(path, "read")
        try:
            rx = re.compile(pattern, re.I if ignore_case else 0)
        except re.error as exc:
            raise WorkspaceError(f"Expressão regular inválida: {exc}. Para texto literal, escape os caracteres especiais.") from None
        limit, context = max(1, min(int(limit or 100), 400)), max(0, min(int(context or 0), 3))
        hits: List[str] = []
        files = [base] if base.is_file() else self.iter_files(base, glob)
        n_files = 0
        for fp in files:
            try:
                if fp.stat().st_size > MAX_SEARCH_FILE:
                    continue
                data = fp.read_bytes()
            except OSError:
                continue
            if is_binary(data) or _hidden_secret(fp):
                continue
            n_files += 1
            lines = data.decode("utf-8", "replace").splitlines()
            for i, line in enumerate(lines):
                if rx.search(line):
                    if context:
                        lo, hi = max(0, i - context), min(len(lines), i + context + 1)
                        hits.append(f"{self.rel(fp)}:{i + 1}:\n" + "\n".join(f"  {j + 1}{'>' if j == i else ' '} {lines[j][:300]}" for j in range(lo, hi)))
                    else:
                        hits.append(f"{self.rel(fp)}:{i + 1}: {line.strip()[:300]}")
                    if len(hits) >= limit:
                        return "\n".join(hits) + f"\n… (parei em {limit} resultados; refine o padrão ou a pasta)"
        return "\n".join(hits) if hits else f"Nenhum resultado para «{pattern}» ({n_files} arquivo(s) de texto vistos)."

    def find(self, pattern: str = "*", path: str = ".", limit: int = 100) -> str:
        base = self.check(path, "read")
        limit = max(1, min(int(limit or 100), 500))
        out: List[str] = []
        pat = pattern or "*"
        for fp in self.iter_files(base):
            if fnmatch.fnmatch(fp.name, pat) or fnmatch.fnmatch(self.rel(fp), pat):
                out.append(self.rel(fp))
                if len(out) >= limit:
                    out.append(f"… (parei em {limit})")
                    break
        return "\n".join(out) if out else f"Nenhum arquivo combina com «{pat}»."

    # ----------------------------------------------------------------- escrita (com diário)
    def write(self, path: str, content: str, overwrite: bool = True) -> str:
        p = self.check(path, "write")
        if len(content.encode("utf-8")) > MAX_WRITE:
            raise WorkspaceError("Conteúdo grande demais para uma escrita só (limite 2 MB).")
        with self._lock_for(p):
            if p.is_dir():
                raise WorkspaceError(f"«{path}» é uma pasta.")
            existed = p.exists()
            if existed and not overwrite:
                raise WorkspaceError(f"«{path}» já existe. Use edit_file para alterá-lo ou overwrite=true para substituir inteiro.")
            had, bk = self._backup(p) if existed else (False, "")
            self._mkparents(p)
            _atomic_write(p, content.encode("utf-8"))
            self._log("write", p, had, bk)
        n = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"{'Substituí' if existed else 'Criei'} {self.rel(p)} ({n} linha(s), {_human(len(content.encode('utf-8')))})."

    def edit(self, path: str, old: str, new: str, replace_all: bool = False) -> str:
        p = self.check(path, "write")
        if old == new:
            raise WorkspaceError("«old» e «new» são iguais: nada a mudar.")
        if not old:
            raise WorkspaceError("«old» está vazio: para criar ou substituir um arquivo inteiro use write_file.")
        with self._lock_for(p):
            if not p.is_file():
                raise WorkspaceError(f"«{path}» não existe." + self._suggest(p))
            data = p.read_bytes()
            if is_binary(data):
                raise WorkspaceError(f"«{path}» é binário.")
            text = _decode(data, p.name)
            crlf = "\r\n" in text and text.count("\r\n") >= text.count("\n") / 2
            norm = text.replace("\r\n", "\n")
            o, nw = old.replace("\r\n", "\n"), new.replace("\r\n", "\n")
            count = norm.count(o)
            if count == 0:
                hint = self._near_miss(norm, o)
                raise WorkspaceError(f"O trecho «old» não foi encontrado em {self.rel(p)} (a busca é exata, com espaços e quebras de linha)." + hint)
            if count > 1 and not replace_all:
                raise WorkspaceError(f"O trecho «old» aparece {count} vezes em {self.rel(p)}. Inclua mais linhas em volta para ser único, ou use replace_all=true.")
            result = norm.replace(o, nw) if replace_all else norm.replace(o, nw, 1)
            if crlf:
                result = result.replace("\n", "\r\n")
            had, bk = self._backup(p)
            _atomic_write(p, result.encode("utf-8"))
            self._log("edit", p, had, bk)
        return f"Editei {self.rel(p)} ({count if replace_all else 1} trecho(s) trocado(s))."

    @staticmethod
    def _near_miss(text: str, old: str) -> str:
        first = next((ln.strip() for ln in old.splitlines() if ln.strip()), "")
        if not first:
            return ""
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if first in ln:
                return f" A primeira linha aparece na linha {i + 1}; confira a indentação e as linhas seguintes com read_file."
        close = difflib.get_close_matches(first, [ln.strip() for ln in lines], n=1, cutoff=0.75)
        return f" Linha parecida no arquivo: «{close[0][:120]}»." if close else " Releia o arquivo com read_file: ele pode ter mudado."

    def mkdir(self, path: str) -> str:
        p = self.check(path, "write")
        if p.exists():
            return f"{self.rel(p)} já existe."
        p.mkdir(parents=True, exist_ok=True)
        self._log("mkdir", p, False, "")
        return f"Criei a pasta {self.rel(p)}."

    def delete(self, path: str) -> str:
        p = self.check(path, "delete")
        with self._lock_for(p):
            if not p.exists() and not p.is_symlink():
                raise WorkspaceError(f"«{path}» não existe.")
            had, bk = self._backup(p) if not p.is_symlink() else (False, "")
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink()
            self._log("delete", p, had, bk)
        return f"Apaguei {self.rel(p)} (dá para desfazer)."

    def move(self, src: str, dst: str, overwrite: bool = False) -> str:
        s, d = self.check(src, "delete"), self.check(dst, "write")
        with self._lock_for(s):
            if not s.exists():
                raise WorkspaceError(f"«{src}» não existe.")
            if d.exists() and not overwrite:
                raise WorkspaceError(f"«{dst}» já existe (use overwrite=true para substituir).")
            if d == s or guard._inside(d, s):
                raise WorkspaceError("O destino está dentro da origem.")
            if d.exists():
                self._backup_replaced(d)
            self._mkparents(d)
            shutil.move(str(s), str(d))
            self._log("move", s, True, "", dst=d)
        return f"Movi {self.rel(s)} para {self.rel(d)}."

    def copy(self, src: str, dst: str, overwrite: bool = False) -> str:
        s, d = self.check(src, "read"), self.check(dst, "write")
        if not s.exists():
            raise WorkspaceError(f"«{src}» não existe.")
        with self._lock_for(d):
            if d.exists() and not overwrite:
                raise WorkspaceError(f"«{dst}» já existe (use overwrite=true para substituir).")
            if d.exists():
                self._backup_replaced(d)
            self._mkparents(d)
            if s.is_dir():
                shutil.copytree(s, d, dirs_exist_ok=True, symlinks=True)
            else:
                shutil.copy2(s, d)
            self._log("copy", d, False, "")
        return f"Copiei {self.rel(s)} para {self.rel(d)}."

    def import_file(self, src: Path, dst: str) -> str:
        """Copia um arquivo de fora (um anexo da sessão) para dentro do projeto."""
        d = self.check(dst, "write")
        if not src.is_file():
            raise WorkspaceError("O anexo não existe.")
        with self._lock_for(d):
            if d.exists():
                self._backup_replaced(d)
            self._mkparents(d)
            shutil.copy2(src, d)
            self._log("copy", d, False, "")
        return f"Copiei o anexo para {self.rel(d)}."

    def _backup_replaced(self, d: Path) -> None:
        had, bk = self._backup(d)
        if d.is_dir():
            shutil.rmtree(d)
        else:
            d.unlink()
        self._log("delete", d, had, bk)

    # ----------------------------------------------------------------- desfazer / diff
    def undoable(self, run: str = "") -> bool:
        return any(not e.get("undone") and (not run or e.get("run") == run) for e in self.journal)

    def undo(self, run: str = "") -> List[str]:
        """Desfaz as mudanças (de uma rodada, ou todas) na ordem inversa. Devolve o que foi feito."""
        notes: List[str] = []
        with self.lock:
            entries = [e for e in self.journal if not e.get("undone") and (not run or e.get("run") == run)]
            for e in reversed(entries):
                try:
                    notes.append(self._undo_one(e))
                    e["undone"] = True
                except (OSError, WorkspaceError, guard.Blocked) as exc:
                    notes.append(f"Não consegui desfazer {e.get('path')}: {exc}")
        return notes

    def _undo_one(self, e: Dict[str, Any]) -> str:
        p = guard.check_path(e["path"], "write", self.root)
        op = e["op"]
        if op == "mkdir":
            try:
                p.rmdir()
            except OSError:
                pass
            return f"Pasta {e['path']} removida."
        if op == "move":
            dst = guard.check_path(e["dst"], "write", self.root)
            if dst.exists() and not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(p))
            return f"{e['dst']} voltou para {e['path']}."
        if e.get("existed") and e.get("backup"):
            src = self.backups / e["backup"]
            if not src.exists():
                raise WorkspaceError("o backup não existe mais")
            if p.exists():
                shutil.rmtree(p) if p.is_dir() else p.unlink()
            p.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, p, symlinks=True)
            else:
                shutil.copy2(src, p)
            return f"{e['path']} voltou ao que era antes."
        if p.exists():   # o arquivo foi criado nesta sessão: desfazer = apagar
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        return f"{e['path']} removido (foi criado pelo agente)."

    def changed_files(self) -> List[Dict[str, str]]:
        """Arquivos mexidos (diário ainda não desfeito), com o estado atual: `created` | `modified` | `deleted`."""
        state: Dict[str, Dict[str, Any]] = {}
        with self.lock:
            for e in self.journal:
                if e.get("undone") or e["op"] == "mkdir":
                    continue
                path = e["path"]
                st = state.setdefault(path, {"first_existed": bool(e.get("existed")), "backup": e.get("backup", "")})
                if e["op"] == "move":
                    state.setdefault(e["dst"], {"first_existed": False, "backup": ""})
        out: List[Dict[str, str]] = []
        for path, st in state.items():
            p = self.root / path
            if p.exists():
                out.append({"path": path, "status": "modified" if st["first_existed"] else "created"})
            elif st["first_existed"]:
                out.append({"path": path, "status": "deleted"})
        return sorted(out, key=lambda x: x["path"])

    def original_text(self, path: str) -> Optional[str]:
        """O conteúdo do arquivo antes da primeira mudança da sessão (None se ele foi criado depois)."""
        with self.lock:
            for e in self.journal:
                if e["path"] == path and not e.get("undone") and e["op"] in ("write", "edit", "delete", "move"):
                    if not e.get("existed"):
                        return None
                    b = self.backups / e["backup"] if e.get("backup") else None
                    if b and b.is_file():
                        try:
                            return b.read_bytes().decode("utf-8", "replace")
                        except OSError:
                            return None
                    return None
        return None

    def diff(self, path: str = "", max_chars: int = 60000) -> str:
        """Diff unificado do que a sessão mudou (de um arquivo ou de todos)."""
        files = [x for x in self.changed_files() if not path or x["path"] == path]
        chunks: List[str] = []
        total = 0
        for f in files:
            cur = ""
            p = self.root / f["path"]
            if f["status"] != "deleted" and p.is_file():
                try:
                    data = p.read_bytes()
                except OSError:
                    data = b""
                if is_binary(data):
                    chunks.append(f"Binary file {f['path']} {f['status']}\n")
                    continue
                cur = data.decode("utf-8", "replace")
            old = self.original_text(f["path"]) if f["status"] != "created" else None
            a = (old or "").splitlines(keepends=True)
            b = cur.splitlines(keepends=True)
            d = "".join(difflib.unified_diff(a, b, "/dev/null" if f["status"] == "created" else "a/" + f["path"], "/dev/null" if f["status"] == "deleted" else "b/" + f["path"], n=3))
            if not d:
                continue
            if total + len(d) > max_chars:
                chunks.append(f"… (diff cortado: mais {len(files) - len(chunks)} arquivo(s))\n")
                break
            chunks.append(d if d.endswith("\n") else d + "\n")
            total += len(d)
        return "".join(chunks)


def _human(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return f"{int(f)} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024
    return f"{n} B"


def _hidden_secret(p: Path) -> bool:
    from ..computer import guard as cg

    return bool(cg._sensitive(p)) and not guard._EXAMPLE_ENV.match(p.name)
