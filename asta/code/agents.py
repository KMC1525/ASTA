"""Os agentes do Code: chamadas à IA com saída em JSON **validada** e um fallback determinístico para cada um.

Planejador → Trabalhadores (até 8 em paralelo, um por tarefa do plano, cada um com um papel) → Revisor → Relator. A IA só devolve dados (`{"tool": …, "args": …}`); quem valida e executa é o motor
(`engine.py`). Resposta inválida depois do reparo = o agente usa o método automático e registra o aviso: a sessão não cai por culpa do modelo. Erro de rede/credencial do provedor falha a sessão
com mensagem clara. O `Brain` (chamada com reparo, repetição em erro passageiro e cancelamento) é o mesmo do Computer Use.
"""
from __future__ import annotations

import json
import re
import shlex
from typing import Any, Dict, List, Optional

from ..computer.agents import Brain, Cancelled, looks_like_json_noise, trim_obs  # noqa: F401  (reexportados para o motor)
from . import tools as T

KINDS = ("feature", "bugfix", "refactor", "tests", "docs", "ui", "research", "mixed")

TOOL_ALIASES = {"read": "read_file", "cat": "read_file", "open_file": "read_file", "view": "read_file", "ls": "list_dir", "list_directory": "list_dir", "list_files": "list_dir", "tree": "list_dir",
                "grep": "search_code", "search": "search_code", "search_files": "search_code", "rg": "search_code", "find": "find_files", "glob": "find_files", "write": "write_file", "create_file": "write_file",
                "create": "write_file", "save_file": "write_file", "edit": "edit_file", "replace": "edit_file", "str_replace": "edit_file", "str_replace_editor": "edit_file", "patch": "edit_file",
                "delete": "delete_path", "delete_file": "delete_path", "remove": "delete_path", "rm": "delete_path", "trash": "delete_path", "mkdir": "make_dir", "create_directory": "make_dir", "make_directory": "make_dir",
                "mv": "move", "rename": "move", "cp": "copy", "run": "run_command", "exec": "run_command", "execute": "run_command", "bash": "run_command", "shell": "run_command", "terminal": "run_command",
                "cmd": "run_command", "command": "run_command", "test": "run_tests", "tests": "run_tests", "run_test": "run_tests", "pytest": "run_tests", "build": "run_tests", "lint": "run_tests",
                "pip_install": "install_packages", "npm_install": "install_packages", "install": "install_packages", "web_search": "search_web", "google": "search_web", "open_url": "fetch_url",
                "browse": "fetch_url", "download": "hf_download", "commit": "commit_local", "git_commit": "commit_local", "push": "publish_changes", "publish": "publish_changes", "pr": "publish_changes",
                "pull_request": "publish_changes", "create_pull_request": "github_create_pr", "ask": "ask_user", "image": "view_image", "look": "view_image", "screenshot": "view_image", "editor": "open_in_editor",
                "vscode": "open_in_editor", "cursor": "open_in_editor", "sleep": "wait", "git_status": "git", "git_diff": "git", "git_log": "git", "prompts": "write_system_prompts"}
ARG_ALIASES = {"old": ("old_string", "old_str", "old_text", "search", "find", "target", "before", "original"), "new": ("new_string", "new_str", "new_text", "replace", "replacement", "after", "updated"),
               "pattern": ("regex", "query", "q", "search", "text", "expression"), "start": ("start_line", "from_line", "line_start", "offset", "from"), "end": ("end_line", "to_line", "line_end", "to"),
               "message": ("msg", "commit_message", "commit_msg", "title"), "args": ("arguments", "argv", "params", "options"), "program": ("command", "cmd", "executable", "exe", "binary"),
               "packages": ("package", "pkgs", "libs", "libraries", "dependencies", "deps"), "manager": ("pm", "tool", "package_manager", "installer"), "dst": ("destination", "dest", "to", "target", "output", "out"),
               "src": ("source", "from", "origin"), "brief": ("description", "prompt", "topic", "purpose", "text"), "count": ("n", "number", "num"), "path": ("file_path", "filepath", "file", "filename", "folder", "directory", "dir"),
               "content": ("contents", "text", "body", "data", "code"), "query": ("q", "search", "keywords", "search_query")}
_SHELL_OPS = re.compile(r"(\|\||&&|[|;<>`]|\$\(|\n)")


def _s(v: Any, n: int = 400) -> str:
    return str(v if v is not None else "").strip()[:n]


def _list(v: Any, n: int = 12, m: int = 300) -> List[str]:
    return [_s(x, m) for x in v if _s(x, m)][:n] if isinstance(v, list) else []


def normalize_plan(obj: Optional[Dict[str, Any]], goal: str, max_steps: int = 7) -> Dict[str, Any]:
    obj = obj if isinstance(obj, dict) else {}
    steps: List[Dict[str, Any]] = []
    ids: Dict[str, str] = {}
    raw = obj.get("steps") if isinstance(obj.get("steps"), list) else []
    for st in raw:
        if isinstance(st, str):
            st = {"title": st}
        if not isinstance(st, dict) or not _s(st.get("title"), 200):
            continue
        sid = f"s{len(steps) + 1}"
        if _s(st.get("id"), 20):
            ids[_s(st.get("id"), 20)] = sid
        role = _s(st.get("role"), 20).lower()
        steps.append({"id": sid, "title": _s(st.get("title"), 200), "role": role if role in T.ROLES else "coder", "files": _list(st.get("files"), 12, 200), "depends_on": [], "done_when": _s(st.get("done_when"), 300),
                      "status": "pending", "_deps": st.get("depends_on")})
        if len(steps) >= max(1, max_steps):
            break
    for i, st in enumerate(steps):   # dependências só para passos anteriores: sem ciclos
        deps = st.pop("_deps", None)
        for d in deps if isinstance(deps, list) else []:
            k = ids.get(_s(d, 20), _s(d, 20))
            if k in [x["id"] for x in steps[:i]] and k not in st["depends_on"]:
                st["depends_on"].append(k)
    kind = _s(obj.get("kind"), 20).lower()
    return {"summary": _s(obj.get("summary"), 300) or _s(goal, 300), "kind": kind if kind in KINDS else "mixed", "steps": steps, "assumptions": _list(obj.get("assumptions"), 6),
            "risks": _list(obj.get("risks"), 6), "blocked": _s(obj.get("blocked"), 400)}


def fallback_plan(goal: str) -> Dict[str, Any]:
    return {"summary": _s(goal, 300), "kind": "mixed", "assumptions": [], "risks": [], "blocked": "",
            "steps": [{"id": "s1", "title": _s(goal, 200) or "Executar o pedido", "role": "coder", "files": [], "depends_on": [], "done_when": "", "status": "pending"}]}


def fix_args(tool: str, args: Any) -> Dict[str, Any]:
    """Aceita os nomes de argumento que modelos pequenos costumam usar («file_path», «old_string»…) e converte `command` em programa + argumentos (sem operadores de shell)."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {"command": args} if tool == "run_command" else {}
    out = dict(args) if isinstance(args, dict) else {}
    t = T.TOOLS.get(tool)
    if not t:
        return out
    for name in t.args:
        if out.get(name) in (None, ""):
            for alt in ARG_ALIASES.get(name, ()):
                if alt not in t.args and out.get(alt) not in (None, ""):
                    out[name] = out[alt]
                    break
    if tool == "run_command":
        prog = out.get("program")
        if isinstance(prog, str) and (" " in prog.strip()) and not out.get("args"):
            if _SHELL_OPS.search(prog):
                out["program"] = prog.strip()   # o guard recusa com a explicação
            else:
                try:
                    parts = shlex.split(prog, posix=True)
                except ValueError:
                    parts = prog.split()
                if parts:
                    out["program"], out["args"] = parts[0], parts[1:]
        if isinstance(out.get("args"), str):
            try:
                out["args"] = shlex.split(out["args"])
            except ValueError:
                out["args"] = out["args"].split()
    if tool == "git" and isinstance(out.get("args"), str):
        out["args"] = out["args"].split()
    return out


def normalize_turn(obj: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Saída do Trabalhador → {"kind": "action"|"finish"|"bad", …}. Aceita os formatos que modelos pequenos costumam devolver."""
    if not isinstance(obj, dict):
        return {"kind": "bad", "why": "resposta vazia"}
    thought, step, memo = _s(obj.get("thought"), 500), _s(obj.get("step"), 12), _s(obj.get("memo"), 400)
    fin = obj.get("finish")

    def finish(d: Dict[str, Any]) -> Dict[str, Any]:
        return {"kind": "finish", "success": d.get("success") is not False, "summary": _s(d.get("summary"), 2000), "files": _list(d.get("files"), 20, 200), "thought": thought, "step": step, "memo": memo}

    if isinstance(fin, dict):
        return finish(fin)
    if obj.get("done") is True and not obj.get("action"):
        return finish({"success": obj.get("success", True), "summary": obj.get("summary", "")})
    act = obj.get("action")
    if isinstance(act, str):
        act = {"tool": act, "args": obj.get("args") or {}}
    if not isinstance(act, dict) and (obj.get("tool") or obj.get("name")):
        act = {"tool": obj.get("tool") or obj.get("name"), "args": obj.get("args") or obj.get("arguments") or {}}
    if isinstance(act, dict):
        tool = _s(act.get("tool") or act.get("name"), 40)
        tool = TOOL_ALIASES.get(tool.lower(), tool)
        args = act.get("args") if act.get("args") not in (None, "") else act.get("arguments")
        if tool == "finish":
            return finish(args if isinstance(args, dict) else {})
        if tool:
            return {"kind": "action", "tool": tool, "args": fix_args(tool, args), "thought": thought, "step": step, "memo": memo}
    return {"kind": "bad", "why": "nem «action» nem «finish» na resposta"}


def normalize_review(obj: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return None
    verdict = _s(obj.get("verdict"), 12).lower()
    if verdict not in ("pass", "partial", "fail"):
        return None
    try:
        score = max(0, min(10, int(float(obj.get("score", 7 if verdict == "pass" else 4)))))
    except (TypeError, ValueError):
        score = 7 if verdict == "pass" else 4
    return {"verdict": verdict, "score": score, "issues": _list(obj.get("issues"), 10, 300), "fix": _s(obj.get("fix"), 800)}


# --------------------------------------------------------------------------- instruções por agente

PLAN_INSTR = ("Write the plan for the user's request in INPUT_JSON.goal. Output JSON: "
              '{"summary": str, "kind": "feature|bugfix|refactor|tests|docs|ui|research|mixed", "steps": [{"id": "s1", "title": str, "role": str, "files": [str], "depends_on": [str], "done_when": str}], '
              '"assumptions": [str], "risks": [str], "blocked": ""}')
CRITIQUE_INSTR = ("Critique this plan (INPUT_JSON.plan) for the request in INPUT_JSON.goal: missing steps, wrong order, steps that would edit the same file in parallel, unverifiable done_when, risks. "
                  "Then output the IMPROVED plan in the same format: "
                  '{"summary": str, "kind": str, "steps": [{"id": "s1", "title": str, "role": str, "files": [str], "depends_on": [str], "done_when": str}], "assumptions": [str], "risks": [str], "blocked": ""}')
TURN_INSTR = ("Decide the single next action (or finish) for the step in INPUT_JSON.step. Output JSON: "
              '{"thought": str, "step": "s1", "action": {"tool": str, "args": {}} | null, "finish": null | {"success": bool, "summary": str, "files": [str]}, "memo": ""}')
REVIEW_INSTR = ("Review whether the goal in INPUT_JSON.goal was really reached, using INPUT_JSON.evidence (diff, checks, worker reports). Output JSON: "
                '{"verdict": "pass|partial|fail", "score": 0-10, "issues": [str], "fix": str}')
REPORT_INSTR = ('Write the final message for the user from INPUT_JSON. Output JSON: {"summary": str, "next_steps": [str]}')


def evidence_lines(status: str, checks: List[dict], review: Optional[dict], lang: str, notes: Optional[List[str]] = None, denied: int = 0) -> List[str]:
    """As linhas de **evidência** que acompanham SEMPRE o resumo final (geradas pelo motor, não pela IA): o que os testes disseram, o que a revisão apontou, o que não foi publicado.
    O Relator por IA escreve o texto; isto garante que ele nunca diga «tudo certo» quando as provas dizem outra coisa."""
    pt = lang == "pt"
    lines: List[str] = []
    for c in checks:
        if c.get("skipped"):
            lines.append(f"– {c.get('label')}: " + ("você negou rodar este comando." if pt else "you denied running this command."))
        else:
            lines.append(f"{'✔' if c.get('ok') else '✘'} {c.get('label')}: " + (("passou" if pt else "passed") if c.get("ok") else (f"falhou (saída {c.get('exit')})" if pt else f"failed (exit {c.get('exit')})")))
    if not checks:
        lines.append("Nenhum teste foi executado: o resultado não foi verificado automaticamente." if pt else "No tests were run: the result was not verified automatically.")
    if review and review.get("issues") and (status != "done" or review.get("verdict") != "pass"):
        lines.append(("Pendências da revisão: " if pt else "Open review issues: ") + "; ".join(review["issues"][:3]))
    if denied:
        lines.append(f"Você negou {denied} ação(ões)." if pt else f"You denied {denied} action(s).")
    lines.extend(notes or [])
    return lines


def deterministic_report(goal: str, status: str, steps: List[dict], files: List[Dict[str, str]], review: Optional[dict], checks: List[dict], undo: bool, lang: str, notes: Optional[List[str]] = None,
                         links: Optional[List[str]] = None, denied: int = 0) -> str:
    pt = lang == "pt"
    head = {"done": ("Pronto.", "Done."), "partial": ("Fiz uma parte do pedido.", "I did part of the request."), "failed": ("Não consegui concluir o pedido.", "I could not finish the request."),
            "cancelled": ("A sessão foi cancelada.", "The session was cancelled.")}.get(status, ("Terminei.", "Finished."))[0 if pt else 1]
    lines = [head]
    ok = [s for s in steps if s.get("status") == "done"]
    bad = [s for s in steps if s.get("status") == "failed"]
    if steps:
        lines.append((f"{len(ok)} de {len(steps)} tarefa(s) do plano concluída(s)." if pt else f"{len(ok)} of {len(steps)} plan task(s) completed."))
    for s in ok[:6]:
        if s.get("summary"):
            lines.append(f"- {s['title']}: {str(s['summary'])[:240]}")
    for s in bad[:3]:
        lines.append((f"- Não terminou: {s['title']} — {str(s.get('summary', ''))[:200]}" if pt else f"- Not finished: {s['title']} — {str(s.get('summary', ''))[:200]}"))
    if files:
        lab = {"created": "novo", "modified": "alterado", "deleted": "apagado"} if pt else {"created": "new", "modified": "changed", "deleted": "deleted"}
        more = f"\n… (+{len(files) - 10})" if len(files) > 10 else ""
        lines.append(("Arquivos:" if pt else "Files:") + "\n" + "\n".join(f"- {f['path']} ({lab.get(f['status'], f['status'])})" for f in files[:10]) + more)
    lines.extend(evidence_lines(status, checks, review, lang, notes, denied))
    for u in links or []:
        lines.append(u)
    if undo:
        lines.append("Você pode desfazer as mudanças nos arquivos pelo botão «Desfazer»." if pt else "You can undo the file changes with the Undo button.")
    return "\n".join(lines)
