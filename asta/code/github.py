"""Cliente do GitHub para o Code: ler, editar e **publicar** código em repositórios — sem depender do programa `git` (por isso funciona também no celular).

Dois jeitos de trabalhar, e os dois entregam no mesmo lugar:

* **Nuvem (por API):** o repositório é baixado como ZIP (`zipball`) para uma pasta de trabalho do ASTA, o agente edita ali, e `commit_changes()` compara com a árvore do GitHub e publica **só o que
  mudou** (blobs → árvore → commit → branch) e abre o pull request. Não precisa de `git`, nem de clone, nem de computador: serve ao app Android.
* **Local (`git`):** num computador com `git`, o Code usa o `git` de verdade (clone, commit, push) — `git_auth_env()` entrega o token por variável de ambiente, nunca na linha de comando nem no
  endereço do remote.

O token (Personal Access Token ou o do `gh`) é segredo: fica só em `settings.json` (nunca vai ao navegador), nunca aparece em saídas/erros (`guard.redact`) e só é enviado ao host do GitHub configurado.
O endereço da API é configurável (`code.github.api`) para GitHub Enterprise — e para os testes, que usam um servidor GitHub de mentira.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ..providers import http
from ..providers.base import ProviderError
from . import guard

API = "https://api.github.com"
WEB = "https://github.com"
MAX_ZIP = 500 * 1024 * 1024
MAX_FILES = 40000
MAX_MEMBER = 50 * 1024 * 1024
MAX_PUBLISH_FILE = 8 * 1024 * 1024
MAX_PUBLISH_TOTAL = 60 * 1024 * 1024
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_REF = re.compile(r"^[\w][\w./+-]{0,200}$")


class GitHubError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.message, self.status = message, status


def parse_repo(spec: str) -> Tuple[str, str, str]:
    """`(dono, repositório, ref)` de «dono/repo», «dono/repo@branch», `https://github.com/dono/repo[/tree/branch]` ou `git@github.com:dono/repo.git`. `ref` vazio = branch padrão."""
    s = str(spec or "").strip()
    ref = ""
    m = re.match(r"^(?:https?://[^/]+/|git@[^:]+:|ssh://git@[^/]+/)([^/\s]+)/([^/\s#?]+?)(?:\.git)?(?:/tree/([^\s?#]+))?/?(?:[?#].*)?$", s)
    if m:
        owner, name, ref = m.group(1), m.group(2), m.group(3) or ""
    else:
        m = re.match(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:@([\w./+-]+))?$", s)
        if not m:
            raise GitHubError("Repositório inválido. Use «dono/repositório» ou o endereço https://github.com/dono/repositório.")
        owner, name, ref = m.group(1), m.group(2), m.group(3) or ""
    if not _NAME.match(owner) or not _NAME.match(name) or (ref and (not _REF.match(ref) or ".." in ref)):
        raise GitHubError("Nome de repositório ou de branch inválido.")
    return owner, name, ref


def git_blob_sha(data: bytes) -> str:
    """O SHA-1 que o Git daria a este conteúdo (para saber, sem baixar nada, se um arquivo local difere do que está no GitHub)."""
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest()


def git_auth_env(token: str, web: str = WEB) -> Dict[str, str]:
    """Variáveis de ambiente que fazem o `git` autenticar no host do GitHub (e só nele) — o token não vai para a linha de comando nem para a configuração do repositório."""
    if not token:
        return {}
    host = urllib.parse.urlsplit(web).scheme + "://" + urllib.parse.urlsplit(web).netloc
    cred = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": f"http.{host}/.extraheader", "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {cred}"}


class GitHub:
    def __init__(self, token: str = "", api: str = "", web: str = ""):
        self.token = (token or "").strip()
        self.api = (api or API).rstrip("/")
        self.web = (web or (WEB if self.api == API else re.sub(r"/api/v3$", "", self.api))).rstrip("/")
        self.login = ""

    # ----------------------------------------------------------------- HTTP
    def _headers(self, accept: str = "application/vnd.github+json") -> Dict[str, str]:
        h = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _err(self, exc: ProviderError, what: str) -> GitHubError:
        msg, st = guard.redact(str(exc), [self.token]), exc.status or 0
        if st == 401:
            return GitHubError("O GitHub recusou o token (inválido, expirado ou sem permissão). Gere outro em github.com → Settings → Developer settings → Personal access tokens e salve em Configuração → Code.", st)
        if st == 403 and re.search(r"rate limit", msg, re.I):
            return GitHubError("O GitHub limitou as chamadas (rate limit). Com um token a cota é bem maior; ou espere alguns minutos.", st)
        if st == 403:
            return GitHubError(f"Sem permissão para {what}. O token precisa do escopo «repo» (ou, no token de granularidade fina, acesso de leitura/escrita ao conteúdo e aos pull requests deste repositório). {msg[:200]}", st)
        if st == 404:
            return GitHubError(f"Não encontrei {what}. Se o repositório for privado, confira o token e o nome.", st)
        if st == 409:
            return GitHubError(f"Conflito em {what}: {msg[:240]}", st)
        if st == 422:
            return GitHubError(f"O GitHub não aceitou o pedido ({what}): {msg[:300]}", st)
        return GitHubError(f"Falha em {what}: {msg[:300]}", st)

    def call(self, method: str, path: str, payload: Optional[dict] = None, what: str = "o GitHub", timeout: float = 40) -> Any:
        url = path if path.startswith("http") else self.api + path
        try:
            with http.request(url, payload, self._headers(), method=method, timeout=timeout) as resp:
                raw = resp.read(30 * 1024 * 1024)
        except ProviderError as exc:
            raise self._err(exc, what) from None
        if not raw.strip():
            return {}
        try:
            return json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            return {}

    # ----------------------------------------------------------------- conta e repositórios
    def whoami(self) -> Dict[str, Any]:
        if not self.token:
            raise GitHubError("Sem token do GitHub. Salve um em Configuração → Code (escopo «repo»).")
        d = self.call("GET", "/user", what="a sua conta do GitHub")
        self.login = str(d.get("login") or "")
        return {"login": self.login, "name": d.get("name") or "", "avatar": d.get("avatar_url") or "", "url": d.get("html_url") or ""}

    def repos(self, query: str = "", limit: int = 40) -> List[Dict[str, Any]]:
        items = self.call("GET", f"/user/repos?per_page={min(max(limit, 1), 100)}&sort=pushed&affiliate=owner,collaborator,organization_member", what="a lista de repositórios")
        out = [self._repo_row(r) for r in items if isinstance(r, dict)]
        q = query.strip().lower()
        if q:
            out = [r for r in out if q in r["full_name"].lower() or q in (r["description"] or "").lower()]
        return out[:limit]

    @staticmethod
    def _repo_row(r: Dict[str, Any]) -> Dict[str, Any]:
        return {"full_name": r.get("full_name") or "", "description": r.get("description") or "", "private": bool(r.get("private")), "default_branch": r.get("default_branch") or "main",
                "pushed_at": r.get("pushed_at") or "", "language": r.get("language") or "", "size_kb": int(r.get("size") or 0), "html_url": r.get("html_url") or "",
                "permissions": r.get("permissions") or {}, "fork": bool(r.get("fork"))}

    def repo(self, owner: str, name: str) -> Dict[str, Any]:
        return self._repo_row(self.call("GET", f"/repos/{owner}/{name}", what=f"o repositório {owner}/{name}"))

    def create_repo(self, name: str, private: bool = True, description: str = "", auto_init: bool = True) -> Dict[str, Any]:
        if not _NAME.match(name or ""):
            raise GitHubError("Nome de repositório inválido (letras, números, ponto, hífen e sublinhado).")
        r = self.call("POST", "/user/repos", {"name": name, "private": bool(private), "description": description[:300], "auto_init": bool(auto_init)}, what="criar o repositório")
        return self._repo_row(r)

    # ----------------------------------------------------------------- checkout na nuvem (ZIP)
    def download_repo(self, owner: str, name: str, ref: str, dest: Path, cancelled: Callable[[], bool] = lambda: False) -> Dict[str, Any]:
        """Baixa o repositório (`zipball`) e extrai em `dest` com segurança (zip-slip, links, tamanho). Devolve `{files, bytes, sha}`."""
        url = f"{self.api}/repos/{owner}/{name}/zipball" + (f"/{urllib.parse.quote(ref, safe='/')}" if ref else "")
        tmp = Path(tempfile.mkdtemp(prefix="asta-gh-"))
        zpath = tmp / "repo.zip"
        try:
            try:
                with http.request(url, headers=self._headers("application/vnd.github+json"), timeout=120) as resp, open(zpath, "wb") as out:
                    total = 0
                    while True:
                        if cancelled():
                            raise GitHubError("cancelado")
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_ZIP:
                            raise GitHubError(f"O repositório passa de {MAX_ZIP // (1024 * 1024)} MB: grande demais para o checkout na nuvem. Use o Code no computador (com git).")
                        out.write(chunk)
            except ProviderError as exc:
                raise self._err(exc, f"baixar {owner}/{name}") from None
            return extract_zip(zpath, dest)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ----------------------------------------------------------------- árvore, commit e branch
    def head_sha(self, owner: str, name: str, branch: str) -> str:
        try:
            r = self.call("GET", f"/repos/{owner}/{name}/git/ref/heads/{urllib.parse.quote(branch, safe='/')}", what=f"a branch {branch}")
        except GitHubError as exc:
            if exc.status == 404:
                return ""
            raise
        return str((r.get("object") or {}).get("sha") or "")

    def tree(self, owner: str, name: str, ref: str) -> Dict[str, Any]:
        """`{entries: {caminho: {sha, mode}}, truncated}` — a árvore recursiva do commit/branch `ref`."""
        r = self.call("GET", f"/repos/{owner}/{name}/git/trees/{urllib.parse.quote(ref, safe='/')}?recursive=1", what="a árvore do repositório", timeout=60)
        ents = {e["path"]: {"sha": e.get("sha", ""), "mode": e.get("mode", "100644")} for e in (r.get("tree") or []) if isinstance(e, dict) and e.get("type") == "blob"}
        return {"entries": ents, "truncated": bool(r.get("truncated")), "sha": r.get("sha", "")}

    def diff_local(self, owner: str, name: str, base_ref: str, root: Path) -> Dict[str, List[str]]:
        """Compara a pasta local com a árvore do GitHub: `{added, modified, deleted}` (caminhos relativos). Só lê os arquivos para calcular o SHA, sem enviar nada."""
        base = self.tree(owner, name, base_ref)
        if base["truncated"]:
            raise GitHubError("O repositório é grande demais para comparar pela API (árvore truncada). Use o Code no computador, com git.")
        remote = base["entries"]
        local: Dict[str, Path] = {}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for fn in filenames:
                fp = Path(dirpath) / fn
                if fp.is_symlink():
                    continue
                local[str(fp.relative_to(root)).replace("\\", "/")] = fp
        added, modified = [], []
        for rel, fp in local.items():
            try:
                data = fp.read_bytes() if fp.stat().st_size <= MAX_PUBLISH_FILE * 2 else b""
            except OSError:
                continue
            if rel not in remote:
                added.append(rel)
            elif fp.stat().st_size <= MAX_PUBLISH_FILE * 2 and git_blob_sha(data) != remote[rel]["sha"]:
                modified.append(rel)
        deleted = [p for p in remote if p not in local]
        return {"added": sorted(added), "modified": sorted(modified), "deleted": sorted(deleted), "modes": {p: remote[p]["mode"] for p in modified}}

    def commit_changes(self, owner: str, name: str, *, branch: str, base_branch: str, message: str, root: Path, changes: Dict[str, List[str]], modes: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Cria um commit com as mudanças (via API) na `branch` — criando-a a partir de `base_branch` se não existir. Devolve `{sha, branch, url, files}`."""
        paths = list(changes.get("added", [])) + list(changes.get("modified", []))
        deleted = list(changes.get("deleted", []))
        if not paths and not deleted:
            raise GitHubError("Nada mudou: não há o que publicar.")
        if not message.strip():
            raise GitHubError("Escreva a mensagem do commit.")
        total = 0
        blobs: List[Dict[str, Any]] = []
        for rel in paths:
            fp = guard.resolve(rel, root)
            if not guard._inside(fp, root) or ".git" in Path(rel).parts:
                raise GitHubError(f"Caminho recusado: {rel}")
            data = fp.read_bytes()
            if len(data) > MAX_PUBLISH_FILE:
                raise GitHubError(f"«{rel}» tem mais de {MAX_PUBLISH_FILE // (1024 * 1024)} MB: grande demais para publicar pela API.")
            total += len(data)
            if total > MAX_PUBLISH_TOTAL:
                raise GitHubError("As mudanças passam de 60 MB: divida em commits menores.")
            blobs.append({"path": rel, "data": data})
        head = self.head_sha(owner, name, branch)
        parent = head or self.head_sha(owner, name, base_branch)
        if not parent:
            raise GitHubError(f"Não achei a branch base «{base_branch}» no GitHub.")
        commit = self.call("GET", f"/repos/{owner}/{name}/git/commits/{parent}", what="o commit base")
        base_tree = (commit.get("tree") or {}).get("sha", "")
        entries: List[Dict[str, Any]] = []
        for b in blobs:
            blob = self.call("POST", f"/repos/{owner}/{name}/git/blobs", {"content": base64.b64encode(b["data"]).decode(), "encoding": "base64"}, what=f"enviar {b['path']}", timeout=120)
            entries.append({"path": b["path"], "mode": (modes or {}).get(b["path"], "100644"), "type": "blob", "sha": blob.get("sha")})
        for rel in deleted:
            entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": None})
        tree = self.call("POST", f"/repos/{owner}/{name}/git/trees", {"base_tree": base_tree, "tree": entries}, what="montar a árvore do commit", timeout=120)
        new = self.call("POST", f"/repos/{owner}/{name}/git/commits", {"message": message[:6000], "tree": tree.get("sha"), "parents": [parent]}, what="criar o commit")
        sha = str(new.get("sha") or "")
        if head:
            self.call("PATCH", f"/repos/{owner}/{name}/git/refs/heads/{urllib.parse.quote(branch, safe='/')}", {"sha": sha, "force": False}, what=f"atualizar a branch {branch}")
        else:
            self.call("POST", f"/repos/{owner}/{name}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha}, what=f"criar a branch {branch}")
        return {"sha": sha, "branch": branch, "url": f"{self.web}/{owner}/{name}/commit/{sha}", "files": len(paths) + len(deleted), "created_branch": not head}

    # ----------------------------------------------------------------- pull requests, issues, releases, CI
    def create_pr(self, owner: str, name: str, *, head: str, base: str, title: str, body: str = "", draft: bool = True) -> Dict[str, Any]:
        r = self.call("POST", f"/repos/{owner}/{name}/pulls", {"title": title[:240] or head, "head": head, "base": base, "body": body[:60000], "draft": bool(draft)}, what="abrir o pull request")
        return {"number": r.get("number"), "url": r.get("html_url") or "", "draft": bool(r.get("draft")), "state": r.get("state") or ""}

    def find_pr(self, owner: str, name: str, head: str, base: str = "") -> Optional[Dict[str, Any]]:
        q = f"/repos/{owner}/{name}/pulls?state=open&head={urllib.parse.quote(owner + ':' + head)}" + (f"&base={urllib.parse.quote(base)}" if base else "")
        rows = self.call("GET", q, what="os pull requests")
        return {"number": rows[0].get("number"), "url": rows[0].get("html_url")} if isinstance(rows, list) and rows else None

    def issues(self, owner: str, name: str, state: str = "open", limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.call("GET", f"/repos/{owner}/{name}/issues?state={state if state in ('open', 'closed', 'all') else 'open'}&per_page={min(max(limit, 1), 50)}", what="as issues")
        return [{"number": r.get("number"), "title": r.get("title") or "", "state": r.get("state") or "", "pr": "pull_request" in r, "user": (r.get("user") or {}).get("login", ""), "labels": [x.get("name") for x in r.get("labels", []) if isinstance(x, dict)],
                 "url": r.get("html_url") or ""} for r in rows if isinstance(r, dict)]

    def issue(self, owner: str, name: str, number: int) -> Dict[str, Any]:
        r = self.call("GET", f"/repos/{owner}/{name}/issues/{int(number)}", what=f"a issue {number}")
        cm = self.call("GET", f"/repos/{owner}/{name}/issues/{int(number)}/comments?per_page=20", what="os comentários") if r.get("comments") else []
        return {"number": r.get("number"), "title": r.get("title") or "", "state": r.get("state") or "", "body": (r.get("body") or "")[:8000], "url": r.get("html_url") or "",
                "comments": [{"user": (c.get("user") or {}).get("login", ""), "body": (c.get("body") or "")[:2000]} for c in cm if isinstance(c, dict)]}

    def comment(self, owner: str, name: str, number: int, body: str) -> Dict[str, Any]:
        r = self.call("POST", f"/repos/{owner}/{name}/issues/{int(number)}/comments", {"body": body[:60000]}, what="comentar")
        return {"url": r.get("html_url") or ""}

    def create_release(self, owner: str, name: str, *, tag: str, title: str = "", body: str = "", target: str = "", draft: bool = False, prerelease: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"tag_name": tag, "name": title or tag, "body": body[:120000], "draft": bool(draft), "prerelease": bool(prerelease)}
        if target:
            payload["target_commitish"] = target
        r = self.call("POST", f"/repos/{owner}/{name}/releases", payload, what="publicar a release")
        return {"url": r.get("html_url") or "", "tag": r.get("tag_name") or tag, "draft": bool(r.get("draft"))}

    def workflow_runs(self, owner: str, name: str, branch: str = "", limit: int = 5) -> List[Dict[str, Any]]:
        q = f"/repos/{owner}/{name}/actions/runs?per_page={min(max(limit, 1), 20)}" + (f"&branch={urllib.parse.quote(branch)}" if branch else "")
        r = self.call("GET", q, what="os workflows (CI)")
        return [{"id": x.get("id"), "name": x.get("name") or "", "status": x.get("status") or "", "conclusion": x.get("conclusion") or "", "branch": x.get("head_branch") or "", "sha": (x.get("head_sha") or "")[:8],
                 "url": x.get("html_url") or ""} for x in (r.get("workflow_runs") or []) if isinstance(x, dict)]

    def dispatch_workflow(self, owner: str, name: str, workflow: str, ref: str) -> Dict[str, Any]:
        if not re.match(r"^[\w.-]+\.ya?ml$|^\d+$", workflow or ""):
            raise GitHubError("Nome do workflow inválido (use o arquivo, ex.: ci.yml).")
        self.call("POST", f"/repos/{owner}/{name}/actions/workflows/{workflow}/dispatches", {"ref": ref}, what=f"rodar o workflow {workflow}")
        return {"ok": True}


# --------------------------------------------------------------------------- extração segura do ZIP


def extract_zip(zpath: Path, dest: Path) -> Dict[str, Any]:
    """Extrai o `zipball` do GitHub em `dest`, tirando a pasta de topo `dono-repo-sha/`. Nada sai de `dest` (zip-slip), links simbólicos são ignorados e há limites de quantidade/tamanho."""
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    files = total = 0
    sha = ""
    try:
        zf = zipfile.ZipFile(zpath)
    except zipfile.BadZipFile:
        raise GitHubError("O GitHub não devolveu um ZIP válido (repositório vazio ou sem acesso).") from None
    with zf:
        infos = zf.infolist()
        top = infos[0].filename.split("/", 1)[0] if infos else ""
        m = re.search(r"-([0-9a-f]{7,40})$", top)
        sha = m.group(1) if m else ""
        for info in infos:
            name = info.filename.replace("\\", "/")
            parts = [x for x in name.split("/")[1:] if x not in ("", ".")]
            if not parts or any(x == ".." or re.match(r"^[A-Za-z]:$", x) or x.startswith("/") for x in parts):
                continue
            if info.is_dir():
                continue
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                continue
            target = (dest.joinpath(*parts)).resolve()
            if not guard._inside(target, dest):
                continue
            files += 1
            if files > MAX_FILES:
                raise GitHubError("O repositório tem arquivos demais para o checkout na nuvem. Use o Code no computador (com git).")
            if info.file_size > MAX_MEMBER:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with zf.open(info) as src, open(target, "wb") as out:
                while True:
                    chunk = src.read(1024 * 256)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_MEMBER:
                        break
                    out.write(chunk)
            total += written
            if mode & 0o111:
                try:
                    target.chmod(target.stat().st_mode | 0o111)
                except OSError:
                    pass
            if total > MAX_ZIP * 2:
                raise GitHubError("O repositório descompactado é grande demais.")
    return {"files": files, "bytes": total, "sha": sha}


def gh_cli_token() -> str:
    """O token do `gh` (GitHub CLI), se o usuário já entrou nele — assim não precisa colar nada. Vazio se não houver."""
    exe = shutil.which("gh")
    if not exe:
        return ""
    try:
        r = subprocess.run([exe, "auth", "token"], capture_output=True, text=True, timeout=8, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return ""
    tok = (r.stdout or "").strip()
    return tok if r.returncode == 0 and re.match(r"^[\w-]{20,}$", tok) else ""
