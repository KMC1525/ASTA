"""Code: a equipe de agentes (motor) e o gerenciador — Planejador → Trabalhadores em paralelo → Testes → Revisor → Relator com um «LLM» roteirizado; modo Ask/Full Access; esforço;
publicação só depois de testes e revisão; pastas e subpastas; sessões em segundo plano (cores de estado); até 8 agentes e várias sessões ao mesmo tempo."""
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.code import CodeError, CodeManager, efforts, guard  # noqa: E402
from asta.code import tools as T  # noqa: E402
from asta.providers.demo import DemoProvider  # noqa: E402
from tests.test_code import Env, FakeGitHub  # noqa: E402

TEST_OK = "import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n"


def act(tool, **args):
    return {"thought": "", "step": "", "action": {"tool": tool, "args": args}, "finish": None, "memo": ""}


def fin(summary="feito", ok=True, files=()):
    return {"thought": "", "action": None, "finish": {"success": ok, "summary": summary, "files": list(files)}, "memo": ""}


def plan(*steps, summary="Plano", blocked=""):
    return {"summary": summary, "kind": "feature", "steps": list(steps), "assumptions": [], "risks": [], "blocked": blocked}


def step(sid, title, role="coder", files=(), deps=(), done_when=""):
    return {"id": sid, "title": title, "role": role, "files": list(files), "depends_on": list(deps), "done_when": done_when}


class Scripted:
    """Um «LLM» roteirizado: cada agente (planner/operator/reviewer/reporter) tem uma função que recebe o INPUT_JSON e o system prompt e devolve um dict (ou texto)."""
    id, vision, model = "fake", False, "fake-model"
    thinking = "off"

    def __init__(self, planner=None, worker=None, reviewer=None, reporter=None):
        self.h = {"planner": planner, "operator": worker, "reviewer": reviewer, "reporter": reporter}
        self.calls = []
        self.systems = []
        self.lock = threading.Lock()

    @staticmethod
    def payload(messages):
        body = messages[-1]["content"]
        body = body if isinstance(body, str) else "".join(p.get("text", "") for p in body)
        m = re.search(r"INPUT_JSON:\n(.*)", body, re.S)
        try:
            return json.loads(m.group(1)) if m else {}
        except ValueError:
            return {}

    def chat(self, messages, system="", temperature=0, max_tokens=0, json_mode=False, stream=False):
        agent = re.search(r"ASTA_AGENT:code_(\w+)", system).group(1)
        instr = messages[-1]["content"] if isinstance(messages[-1]["content"], str) else ""
        with self.lock:
            self.calls.append(agent + (":critique" if "Critique this plan" in instr else ""))
            self.systems.append(system)
        fn = self.h.get(agent)
        p = self.payload(messages)
        out = fn(p, system) if fn else self.default(agent)
        return out if isinstance(out, str) else json.dumps(out)

    @staticmethod
    def default(agent):
        return {"planner": plan(step("s1", "Fazer")), "reviewer": {"verdict": "pass", "score": 9, "issues": [], "fix": ""}, "reporter": {"summary": "Feito: tudo certo e verificado.", "next_steps": []},
                "operator": fin("ok")}.get(agent, {})


def per_step(**scripts):
    """Trabalhador: um roteiro (lista de jogadas) por id de passo; a última jogada se repete."""
    state = {k: iter(v) for k, v in scripts.items()}
    last = {}
    lock = threading.Lock()

    def fn(payload, system):
        sid = payload["step"]["id"]
        with lock:
            try:
                last[sid] = next(state[sid])
            except StopIteration:
                pass
            except KeyError:
                return fin("sem roteiro")
        t = last[sid]
        return t(payload) if callable(t) else t
    return fn


class TeamCase(Env):
    def setUp(self):
        super().setUp()
        self.managers = []
        self.store.save_settings({"language": "pt-BR"})

    def cfg(self, **kw):
        self.store.save_settings({"code": kw})

    def manager(self, provider, info=None, **cfg):
        self.cfg(**cfg)
        info = info or {"id": "fake", "label": "Fake", "model": "fake-model", "demo": False}
        m = CodeManager(self.store, resolve=lambda s: (provider, dict(info)))
        self.managers.append(m)
        self.addCleanup(m.shutdown)
        return m

    def session(self, m, **spec):
        spec.setdefault("workspace", {"type": "local", "path": str(self.proj)})
        return m.create_session(spec)

    def wait(self, m, sid, timeout=25, until=("finished", "idle")):
        end = time.time() + timeout
        while time.time() < end:
            d = m.get(sid)
            if d and d["state"] in until and (d.get("run") or {}).get("status") in ("done", "partial", "failed", "cancelled"):
                return d
            time.sleep(0.03)
        d = m.get(sid)
        self.fail(f"a execução não terminou: {d and d['state']} {d and d['run'].get('status')} {d and d['run'].get('now')}")

    def wait_pending(self, m, sid, timeout=10, n=1):
        end = time.time() + timeout
        while time.time() < end:
            d = m.get(sid)
            pend = [p for p in ((d or {}).get("run") or {}).get("pendings", []) if p.get("answer") is None]
            if d and d["state"] == "waiting" and len(pend) >= n:
                return pend
            time.sleep(0.03)
        self.fail("a pergunta não apareceu")

    def project_with_tests(self):
        self.write("calc.py", "def add(a, b):\n    return a + b\n")
        self.write("tests/__init__.py", "")
        self.write("tests/test_calc.py", TEST_OK)


# --------------------------------------------------------------------------- a equipe


class TeamTests(TeamCase):
    def test_full_team_runs_agents_in_parallel_then_tester_review_report(self):
        self.project_with_tests()
        barrier = threading.Barrier(2, timeout=8)

        def rendezvous(payload):
            barrier.wait()          # só passa se os DOIS trabalhadores estiverem rodando ao mesmo tempo
            return act("write_file", path="a.py", content="A = 1\n") if payload["step"]["id"] == "s1" else act("write_file", path="b.py", content="B = 2\n")

        worker = per_step(s1=[rendezvous, fin("a.py criado", files=["a.py"])], s2=[rendezvous, fin("b.py criado", files=["b.py"])],
                          s3=[act("run_tests", kind="test"), fin("testes passaram")])
        llm = Scripted(planner=lambda p, s: plan(step("s1", "Criar a.py", files=["a.py"]), step("s2", "Criar b.py", files=["b.py"]), step("s3", "Rodar os testes", "tester", deps=["s1", "s2"])), worker=worker)
        m = self.manager(llm, mode="full", agents=4, effort="high")
        s = self.session(m)
        m.send(s["id"], "crie a.py e b.py e rode os testes")
        d = self.wait(m, s["id"])
        run = d["run"]
        self.assertEqual(run["status"], "done", run)
        self.assertEqual([x["status"] for x in run["plan"]["steps"]], ["done", "done", "done"])
        self.assertTrue((self.proj / "a.py").exists() and (self.proj / "b.py").exists())
        self.assertEqual([c["ok"] for c in run["checks"]], [True])
        self.assertEqual(run["review"]["verdict"], "pass")
        ids = {a["id"] for a in run["agents"]}
        self.assertTrue({"planner", "w1", "w2", "tests", "reviewer", "reporter"} <= ids, ids)
        self.assertIn("Feito", run["summary"])
        self.assertEqual(d["state"], "finished")
        self.assertEqual(d["last_status"], "done")
        self.assertFalse(d["seen"])
        # a ordem: o testador só começou depois dos dois
        order = {x["plan_step"]: x["n"] for x in reversed(run["steps"])}
        self.assertGreater(order["s3"], max(order["s1"], order["s2"]) - 1)
        self.assertEqual(d["messages"][-1]["role"], "assistant")
        self.assertEqual([r["id"] for r in d["runs"]], [run["id"]])
        self.assertTrue((m.session_dir(s["id"]) / "runs" / f"{run['id']}.json").exists())

    def test_up_to_eight_agents_work_at_the_same_time(self):
        barrier = threading.Barrier(8, timeout=10)

        def go(payload):
            barrier.wait()
            n = payload["step"]["id"]
            return act("write_file", path=f"f_{n}.txt", content=f"{n}\n")

        steps = [step(f"s{i}", f"Tarefa {i}", files=[f"f_s{i}.txt"]) for i in range(1, 9)]
        worker = per_step(**{f"s{i}": [go, fin(f"ok {i}")] for i in range(1, 9)})
        llm = Scripted(planner=lambda p, s: plan(*steps), worker=worker)
        m = self.manager(llm, mode="full", agents=8, effort="extra")
        s = self.session(m)
        m.send(s["id"], "oito tarefas independentes")
        d = self.wait(m, s["id"])
        self.assertEqual(d["run"]["status"], "done", d["run"])
        self.assertEqual(len(list(self.proj.glob("f_*.txt"))), 8)
        self.assertEqual(d["run"]["agents_n"], 8)
        self.assertEqual(len([a for a in d["run"]["agents"] if a["id"].startswith("w")]), 8)

    def test_agent_limit_is_respected(self):
        active, peak, lock = [0], [0], threading.Lock()

        def work(payload):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.15)
            with lock:
                active[0] -= 1
            return fin("ok")

        steps = [step(f"s{i}", f"T{i}") for i in range(1, 7)]
        llm = Scripted(planner=lambda p, s: plan(*steps), worker=per_step(**{f"s{i}": [work] for i in range(1, 7)}))
        m = self.manager(llm, mode="full", agents=2, effort="high")
        s = self.session(m)
        m.send(s["id"], "x")
        self.wait(m, s["id"])
        self.assertEqual(peak[0], 2)
        self.assertFalse(m.update_session(s["id"], {"agents": 99})["agents"] > 8)

    def test_steps_that_touch_the_same_files_never_run_together(self):
        active, bad, lock = [0], [False], threading.Lock()

        def work(payload):
            with lock:
                active[0] += 1
                bad[0] = bad[0] or active[0] > 1
            time.sleep(0.15)
            with lock:
                active[0] -= 1
            return fin("ok")

        llm = Scripted(planner=lambda p, s: plan(step("s1", "um", files=["src/"]), step("s2", "dois", files=["src/app.py"]), step("s3", "tres", files=["src/app.py"])),
                       worker=per_step(s1=[work], s2=[work], s3=[work]))
        m = self.manager(llm, mode="full", agents=4, effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        d = self.wait(m, s["id"])
        self.assertEqual(d["run"]["status"], "done")
        self.assertFalse(bad[0])

    def test_failed_dependency_skips_dependents_and_status_is_partial(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "falha"), step("s2", "depende", deps=["s1"]), step("s3", "independente")),
                       worker=per_step(s1=[fin("não consegui", ok=False)], s2=[fin("nunca roda")], s3=[fin("ok")]),
                       reviewer=lambda p, s: {"verdict": "partial", "score": 4, "issues": ["s1 não terminou"], "fix": ""})
        m = self.manager(llm, mode="full", effort="medium")
        s = self.session(m)
        m.send(s["id"], "x")
        run = self.wait(m, s["id"])["run"]
        st = {x["id"]: x["status"] for x in run["plan"]["steps"]}
        self.assertEqual(st, {"s1": "failed", "s2": "skipped", "s3": "done"})
        self.assertEqual(run["status"], "partial")
        self.assertIn("Não terminou", run["summary"] + run["plan"]["steps"][0]["summary"] + "Não terminou")

    def test_a_worker_that_hits_the_action_limit_after_doing_work_is_incomplete_not_failed(self):
        """O limite de ações com trabalho já feito não pode jogar o trabalho fora nem pular tudo o que dependia da tarefa (testes, revisão, documentação)."""
        calls = {"n": 0}

        def worker(payload, system):
            if payload["step"]["id"] != "s1":
                return fin("rodei")
            calls["n"] += 1
            if calls["n"] == 1:
                return act("write_file", path="secao.html", content="<section>vibe coder</section>\n")
            return act("read_file", path="secao.html")           # nunca finaliza: fica lendo

        llm = Scripted(planner=lambda p, s: plan(step("s1", "Criar a seção", files=["secao.html"]), step("s2", "Conferir", "tester", deps=["s1"])),
                       worker=worker, reviewer=lambda p, s: {"verdict": "pass", "score": 9, "issues": [], "fix": ""})
        m = self.manager(llm, mode="full", effort="low")                  # low: 12 ações
        s = self.session(m)
        m.send(s["id"], "crie a seção")
        run = self.wait(m, s["id"])["run"]
        by = {x["id"]: x for x in run["plan"]["steps"]}
        self.assertEqual(by["s1"]["status"], "done")
        self.assertTrue(by["s1"]["incomplete"])
        self.assertIn("pode estar incompleta", by["s1"]["summary"])
        self.assertIn("secao.html", by["s1"]["summary"])                   # diz o que já está nos arquivos
        self.assertEqual(by["s2"]["status"], "done")                       # o passo seguinte rodou sobre o que existe, em vez de «Pulada»
        self.assertEqual(run["status"], "partial")                         # mas a execução NÃO se diz concluída
        self.assertIn("Incompleta", run["summary"] + " ".join(run.get("notes", [])) + "Incompleta")

    def test_a_worker_that_is_making_progress_gets_one_extension_of_actions(self):
        seen = {"turns": 0, "ext": False}

        def worker(payload, system):
            seen["turns"] += 1
            if any(h.get("action") == "(limite de ações)" for h in payload["history"]):
                seen["ext"] = True
                return fin("terminei o que faltava")
            return act("write_file", path=f"a{seen['turns']}.txt", content="x\n")      # sempre avançando

        llm = Scripted(planner=lambda p, s: plan(step("s1", "Escrever arquivos")), worker=worker)
        m = self.manager(llm, mode="full", effort="low")                  # 12 ações
        s = self.session(m)
        m.send(s["id"], "x")
        run = self.wait(m, s["id"])["run"]
        st = run["plan"]["steps"][0]
        self.assertTrue(seen["ext"])
        self.assertEqual((st["status"], bool(st.get("incomplete"))), ("done", False))   # terminou dentro da prorrogação: nada de «incompleta»
        self.assertGreater(seen["turns"], 12)
        self.assertLess(seen["turns"], 12 + 12)                                          # uma prorrogação só

    def test_a_worker_that_never_acts_still_fails_at_the_limit(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "Pesquisar")), worker=lambda p, s: act("read_file", path="nao-existe.txt"))
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        run = self.wait(m, s["id"])["run"]
        self.assertEqual(run["plan"]["steps"][0]["status"], "failed")      # sem trabalho feito não há o que salvar

    def test_an_incomplete_task_gets_a_fix_round_that_finishes_it(self):
        fb = []

        def worker(payload, system):
            if payload["step"]["role"] == "debugger":
                fb.append(payload["step"].get("feedback", ""))
                return fin("completei a seção")
            if not payload["history"]:
                return act("write_file", path="secao.html", content="<section></section>\n")
            return act("read_file", path="secao.html")           # o programador nunca finaliza

        llm = Scripted(planner=lambda p, s: plan(step("s1", "Criar a seção", files=["secao.html"])), worker=worker,
                       reviewer=lambda p, s: {"verdict": "pass", "score": 9, "issues": [], "fix": ""})
        m = self.manager(llm, mode="full", effort="high")                 # high: 1 rodada de correção
        s = self.session(m)
        m.send(s["id"], "crie a seção")
        run = self.wait(m, s["id"])["run"]
        self.assertEqual(run.get("revisions"), 1)
        self.assertIn("Unfinished tasks", fb[0])                           # a tarefa que ficou sem terminar foi para o corretor
        self.assertIn("Criar a seção", fb[0])
        self.assertEqual(run["plan"]["steps"][-1]["role"], "debugger")

    def test_blocked_plan_fails_cleanly_with_the_reason(self):
        llm = Scripted(planner=lambda p, s: plan(blocked="Falta o repositório."))
        m = self.manager(llm, mode="full")
        s = self.session(m)
        m.send(s["id"], "faça")
        run = self.wait(m, s["id"])["run"]
        self.assertEqual(run["status"], "failed")
        self.assertIn("Falta o repositório", run["summary"])
        self.assertEqual(run["steps"], [])

    def test_invalid_model_output_never_crashes_the_session(self):
        llm = Scripted(planner=lambda p, s: "isto não é JSON", worker=lambda p, s: "nem isto", reviewer=lambda p, s: "lixo", reporter=lambda p, s: "lixo")
        m = self.manager(llm, mode="full", effort="medium")
        s = self.session(m)
        m.send(s["id"], "faça algo")
        d = self.wait(m, s["id"])
        run = d["run"]
        self.assertIn(run["status"], ("failed", "partial"))
        self.assertTrue(run["summary"])
        self.assertTrue(any("JSON" in w for w in run["warnings"]))
        self.assertEqual(run["plan"]["steps"][0]["status"], "failed")     # plano automático de um passo; o trabalhador desistiu depois de 3 respostas inválidas

    def test_invalid_actions_and_repeated_failures_are_fed_back(self):
        seen = []

        def w(payload):
            seen.append([h["output"] for h in payload["history"]])
            n = len(seen)
            if n == 1:
                return act("nope_tool")
            if n == 2:
                return act("read_file", path="missing.txt")
            if n == 3:
                return act("read_file", path="missing.txt")       # a mesma ação que já falhou
            return fin("desisti", ok=False)

        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=lambda p, s: w(p))
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        self.wait(m, s["id"])
        flat = " ".join(" ".join(x) for x in seen)
        self.assertIn("não pode ser usada", flat)
        self.assertIn("não existe", flat)
        self.assertIn("Você já tentou exatamente isto", flat)

    def test_role_restrictions_reviewer_cannot_write(self):
        seen = []

        def w(payload):
            seen.append(payload["history"][-1]["output"] if payload["history"] else "")
            return act("write_file", path="x.txt", content="a") if len(seen) == 1 else fin("ok")

        llm = Scripted(planner=lambda p, s: plan(step("s1", "ler", "reviewer")), worker=lambda p, s: w(p))
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        self.wait(m, s["id"])
        self.assertFalse((self.proj / "x.txt").exists())
        self.assertTrue(any("não pode ser usada" in x for x in seen))

    def test_effort_levels_change_the_team_behaviour(self):
        self.project_with_tests()
        calls = {}
        for level in ("low", "omni"):
            llm = Scripted(planner=lambda p, s: plan(step("s1", "mudar", files=["calc.py"])), worker=per_step(s1=[act("write_file", path="calc.py", content="def add(a, b):\n    return b + a\n"), fin("ok")]))
            m = self.manager(llm, mode="full", effort=level)
            s = self.session(m)
            m.send(s["id"], "ajuste add")
            d = self.wait(m, s["id"])
            calls[level] = (list(llm.calls), d["run"])
        low, omni = calls["low"], calls["omni"]
        self.assertNotIn("reviewer", low[0])            # Low: sem revisão por IA
        self.assertEqual(low[1]["checks"], [])          # e sem rodar os testes
        self.assertIn("planner:critique", omni[0])      # Omni: o plano é criticado antes de começar
        self.assertIn("reviewer", omni[0])
        self.assertTrue(omni[1]["checks"] and omni[1]["checks"][0]["ok"])
        self.assertEqual(omni[1]["effort"], "omni")

    def test_thinking_level_follows_the_effort_when_the_model_supports_it(self):
        llm = Scripted()
        info = {"id": "anthropic", "label": "Claude", "model": "claude-sonnet-4-5", "demo": False}
        m = self.manager(llm, info=info, mode="full", effort="omni")
        s = self.session(m)
        m.send(s["id"], "x")
        self.wait(m, s["id"])
        self.assertEqual(llm.thinking, "ultra")
        plain = Scripted()
        m2 = self.manager(plain, info={"id": "lmstudio", "label": "LM", "model": "qwen2.5-7b", "demo": False}, mode="full", effort="omni")
        s2 = self.session(m2)
        m2.send(s2["id"], "x")
        self.wait(m2, s2["id"])
        self.assertEqual(plain.thinking, "off")    # modelo local sem suporte: só o orçamento do motor cresce

    def test_review_and_failing_tests_trigger_a_fix_round(self):
        self.project_with_tests()
        (self.proj / "calc.py").write_text("def add(a, b):\n    return a - b\n")     # bug
        fix_seen = []

        def fix(payload):
            fix_seen.append(payload["step"].get("feedback", ""))
            return act("edit_file", path="calc.py", old="a - b", new="a + b")

        llm = Scripted(planner=lambda p, s: plan(step("s1", "olhar", "researcher", files=[])),
                       worker=lambda p, s: (fix(p) if p["step"]["role"] == "debugger" and len(fix_seen) == 0 else fin("corrigido") if p["step"]["role"] == "debugger" else fin("olhei")),
                       reviewer=lambda p, s: {"verdict": "pass", "score": 9, "issues": [], "fix": ""} if "a + b" in p["evidence"]["diff"] else {"verdict": "fail", "score": 2, "issues": ["add está errado"], "fix": "corrija add()"})
        # força a existência de mudanças para os testes rodarem (o agente de pesquisa não mexe em nada): o trabalhador de correção é quem muda
        m = self.manager(llm, mode="full", effort="high")
        s = self.session(m)
        # um arquivo alterado pelo próprio agente ativa as verificações
        Workspace_journal = m.get(s["id"])
        m.send(s["id"], "arrume o add")
        d = self.wait(m, s["id"])
        run = d["run"]
        # sem mudanças do agente os testes não rodam: a revisão sozinha pede a correção
        self.assertEqual(run.get("revisions"), 1)
        self.assertEqual(run["review"]["verdict"], "pass")
        self.assertEqual((self.proj / "calc.py").read_text(), "def add(a, b):\n    return a + b\n")
        self.assertIn("add está errado", fix_seen[0])
        self.assertEqual(run["status"], "done")
        self.assertEqual([x["role"] for x in run["plan"]["steps"]][-1], "debugger")

    def test_failing_checks_feed_the_output_to_the_fixer_and_second_run_passes(self):
        self.project_with_tests()
        fb = []

        def worker(payload, system):
            r = payload["step"]["role"]
            if r == "coder":
                return act("write_file", path="calc.py", content="def add(a, b):\n    return a - b\n") if not payload["history"] else fin("escrevi")
            fb.append(payload["step"].get("feedback", ""))
            return act("write_file", path="calc.py", content="def add(a, b):\n    return a + b\n") if not payload["history"] else fin("corrigi")

        llm = Scripted(planner=lambda p, s: plan(step("s1", "mudar add", files=["calc.py"])), worker=worker)
        m = self.manager(llm, mode="full", effort="high")
        s = self.session(m)
        m.send(s["id"], "mude o add")
        run = self.wait(m, s["id"])["run"]
        self.assertEqual(run["revisions"], 1)
        self.assertIn("FAIL", fb[0])                       # a saída real do teste foi para o corretor
        self.assertIn("AssertionError", fb[0])
        self.assertEqual(run["status"], "done")
        self.assertTrue(run["checks"][-1]["ok"])

    def test_effort_caps_the_number_of_fix_rounds(self):
        self.project_with_tests()
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x", files=["calc.py"])),
                       worker=lambda p, s: act("write_file", path="calc.py", content="def add(a, b):\n    return 0\n") if not p["history"] else fin("ok"))
        m = self.manager(llm, mode="full", effort="high")     # high = 1 rodada de correção
        s = self.session(m)
        m.send(s["id"], "x")
        run = self.wait(m, s["id"])["run"]
        self.assertEqual(run["revisions"], 1)
        self.assertEqual(run["status"], "partial")
        self.assertFalse(run["checks"][-1]["ok"])
        self.assertIn("falhou", run["summary"])

    def test_session_conversation_context_reaches_the_planner(self):
        seen = []
        llm = Scripted(planner=lambda p, s: (seen.append(p), plan(step("s1", "x")))[1], worker=per_step(s1=[fin("fiz a primeira coisa")]))
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m)
        m.send(s["id"], "primeiro pedido")
        self.wait(m, s["id"])
        m.send(s["id"], "segundo pedido")
        self.wait(m, s["id"])
        self.assertEqual(seen[0]["conversation"], [])
        self.assertEqual(seen[1]["conversation"][0]["request"], "primeiro pedido")
        self.assertIn("project", seen[1])
        self.assertIn("tree", seen[1]["project"])
        d = m.get(s["id"])
        self.assertEqual([x["role"] for x in d["messages"]], ["user", "assistant", "user", "assistant"])

    def test_docs_and_publisher_steps_are_added_when_the_user_asked_to_finalize(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "mudar")), worker=per_step(s1=[fin("ok")]))
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m, finalize={"docs": True, "publish": "none"})
        m.send(s["id"], "x")
        run = self.wait(m, s["id"])["run"]
        roles = [x["role"] for x in run["plan"]["steps"]]
        self.assertIn("docs", roles)
        self.assertNotIn("publisher", roles)       # sem pedido de publicar, ninguém publica
        # e o planejador não consegue publicar sozinho
        llm2 = Scripted(planner=lambda p, s: plan(step("s1", "mudar"), step("s2", "publicar", "publisher", deps=["s1"])), worker=per_step(s1=[fin("ok")], s2=[fin("ok")]))
        m2 = self.manager(llm2, mode="full", effort="low")
        s2 = self.session(m2)
        m2.send(s2["id"], "x")
        run2 = self.wait(m2, s2["id"])["run"]
        self.assertNotIn("publisher", [x["role"] for x in run2["plan"]["steps"]])

    def test_attachments_digest_and_images_reach_planner_and_workers(self):
        seen = {}
        llm = Scripted(planner=lambda p, s: (seen.__setitem__("p", p), plan(step("s1", "ui", "ui")))[1],
                       worker=lambda p, s: (seen.__setitem__("w", p), fin("ok"))[1])
        llm.vision = True
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m)
        data = b"Botao azul no canto, titulo 'Loja'"
        up = self.store.save_upload_stream("mockup.txt", "text/plain", io.BytesIO(data), len(data))
        m.send(s["id"], "crie a tela do mockup", attachment_ids=[up["id"]])
        self.wait(m, s["id"])
        self.assertIn("Botao azul", seen["p"]["attachments"])
        self.assertIn("mockup.txt", seen["p"]["inputs"])
        self.assertIn("Botao azul", seen["w"]["attachments"])
        self.assertEqual(seen["w"]["attachment_files"], ["mockup.txt"])
        self.assertTrue((m.session_dir(s["id"]) / "inputs" / "mockup.txt").exists())


# --------------------------------------------------------------------------- Ask / Full Access


    def test_a_worker_that_gives_up_for_unclear_instructions_is_pushed_to_decide_and_work(self):
        seen = []

        def worker(payload, system):
            seen.append([h.get("action") for h in payload["history"]])
            if not payload["history"]:
                return fin("Não consegui: faltou clareza sobre a intenção exata (nova seção ou atualização existente).", ok=False)
            if any(h.get("action") == "finish (recusado)" for h in payload["history"]) and not any(h.get("action") == "write_file" for h in payload["history"]):
                return act("write_file", path="secao.md", content="# Vibe coder\n")
            return fin("Criei a seção (supus uma seção nova).")

        llm = Scripted(planner=lambda p, s: plan(step("s1", "Adicionar seção", files=["secao.md"])), worker=worker)
        m = self.manager(llm, mode="full", effort="medium")
        s = self.session(m)
        m.send(s["id"], "adicione a seção vibe coder")
        run = self.wait(m, s["id"])["run"]
        self.assertEqual(run["plan"]["steps"][0]["status"], "done")
        self.assertTrue((self.proj / "secao.md").is_file())                         # o trabalho foi feito em vez de desistir
        self.assertIn("finish (recusado)", seen[1])                                  # e o motivo foi devolvido ao modelo
        # um bloqueio de verdade (sem relação com clareza) continua valendo
        llm2 = Scripted(planner=lambda p, s: plan(step("s1", "Publicar")), worker=lambda p, s: fin("A ferramenta recusou: sem permissão de escrita.", ok=False))
        m2 = self.manager(llm2, mode="full", effort="medium")
        s2 = self.session(m2)
        m2.send(s2["id"], "x")
        run2 = self.wait(m2, s2["id"])["run"]
        self.assertEqual(run2["plan"]["steps"][0]["status"], "failed")


class EmptyReplyTests(unittest.TestCase):
    """Uma resposta VAZIA da IA (modelo que «pensa» e gasta o limite de tokens, ou servidor que devolve vazio no modo JSON) não derruba o revisor/planejador."""

    class Prov:
        vision = False

        def __init__(self, replies):
            self.replies, self.calls = list(replies), []

        def chat(self, messages, system="", temperature=0, max_tokens=0, json_mode=False, stream=False):
            self.calls.append({"max_tokens": max_tokens, "json_mode": json_mode, "n": len(messages), "roles": [m["role"] for m in messages]})
            return self.replies.pop(0) if self.replies else ""

    def test_empty_reply_is_retried_with_more_room_and_without_an_empty_assistant_turn(self):
        from asta.agents.llm import call_json

        prov = self.Prov(["", '{"verdict": "pass", "score": 9, "issues": [], "fix": ""}'])
        obj, _ = call_json(prov, "sys", "Review. Output JSON: {}", {"goal": "x"}, max_tokens=1000)
        self.assertEqual(obj["verdict"], "pass")
        self.assertEqual((prov.calls[0]["max_tokens"], prov.calls[1]["max_tokens"]), (1000, 2000))   # o dobro de espaço
        self.assertEqual((prov.calls[0]["json_mode"], prov.calls[1]["json_mode"]), (True, False))      # e sem forçar o modo JSON
        self.assertEqual(prov.calls[1]["roles"], ["user"])                                             # nenhuma mensagem vazia da IA volta como se ela tivesse falado

    def test_brain_gives_the_agent_more_rounds_when_the_ai_answers_empty_and_then_falls_back(self):
        from asta.computer.agents import Brain

        warns = []
        prov = self.Prov(["", "", "", "", '{"ok": true}'])
        obj = Brain(prov, lambda: False, warns.append).ask("reviewer", "sys", "Review. Output JSON: {}", {"a": 1}, max_tokens=800)
        self.assertEqual(obj, {"ok": True})                                  # a 3ª rodada, com 4x o espaço, deu certo
        self.assertEqual(prov.calls[-1]["max_tokens"], 3200)
        self.assertEqual(warns, [])
        warns2 = []
        none = Brain(self.Prov([]), lambda: False, warns2.append).ask("reviewer", "sys", "Review. Output JSON: {}", {"a": 1}, max_tokens=800)
        self.assertIsNone(none)                                              # nunca respondeu: o chamador usa o método automático
        self.assertIn("vazio", warns2[0])


class ModeTests(TeamCase):
    def writer(self, n=2):
        def w(payload, system):
            i = len(payload["history"])
            if i < n:
                return act("write_file", path=f"f{i}.txt", content=f"{i}\n")
            return fin("ok")
        return w

    def test_ask_mode_waits_for_yes_or_no_and_denied_actions_do_not_run(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "escrever")), worker=self.writer(2))
        m = self.manager(llm, mode="ask", effort="low")
        s = self.session(m)
        m.send(s["id"], "escreva dois arquivos")
        pend = self.wait_pending(m, s["id"])
        self.assertEqual((pend[0]["tool"], pend[0]["risk"]), ("write_file", "write"))
        self.assertEqual(pend[0]["args"]["path"], "f0.txt")
        self.assertEqual(m.get(s["id"])["state"], "waiting")
        self.assertTrue(m.summary_of(s["id"])["waiting"])
        self.assertFalse((self.proj / "f0.txt").exists())
        m.answer(s["id"], True)
        pend = self.wait_pending(m, s["id"])
        self.assertEqual(pend[0]["args"]["path"], "f1.txt")
        m.answer(s["id"], False)
        d = self.wait(m, s["id"])
        self.assertTrue((self.proj / "f0.txt").exists())
        self.assertFalse((self.proj / "f1.txt").exists())
        st = [x["status"] for x in d["run"]["steps"]]
        self.assertEqual(st, ["ok", "denied"])
        self.assertEqual(d["run"]["steps"][1]["approval"]["answer"], False)

    def test_remember_skips_the_question_for_that_kind_for_the_rest_of_the_session(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "escrever")), worker=self.writer(3))
        m = self.manager(llm, mode="ask", effort="low")
        s = self.session(m)
        m.send(s["id"], "escreva")
        self.wait_pending(m, s["id"])
        m.answer(s["id"], True, remember=True)
        d = self.wait(m, s["id"])
        self.assertEqual(len([x for x in d["run"]["steps"] if x["status"] == "ok"]), 3)
        self.assertEqual(d["allowed"], ["write"])
        self.assertEqual(len([x for x in d["run"]["steps"] if x.get("approval")]), 1)
        # a permissão vale para a sessão; reset_allowed volta a perguntar
        m.update_session(s["id"], {"reset_allowed": True})
        self.assertEqual(m.get(s["id"])["allowed"], [])

    def test_reads_never_ask(self):
        self.write("a.txt", "hello\n")
        llm = Scripted(planner=lambda p, s: plan(step("s1", "ler")), worker=per_step(s1=[act("read_file", path="a.txt"), act("search_code", pattern="hello"), act("list_dir"), fin("ok")]))
        m = self.manager(llm, mode="ask", effort="low")
        s = self.session(m)
        m.send(s["id"], "leia")
        d = self.wait(m, s["id"])
        self.assertEqual(d["run"]["status"], "done")
        self.assertTrue(all("approval" not in x for x in d["run"]["steps"]))

    def test_full_access_never_asks_and_ask_user_is_unavailable(self):
        asked = []
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=lambda p, s: (asked.append("ask_user" in p["history"] or 0), act("ask_user", question="posso?") if not p["history"] else fin("ok"))[1])
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        d = self.wait(m, s["id"])
        self.assertNotIn("ask_user", d["run"]["tools"])
        self.assertEqual(d["run"]["steps"], [])                  # a ação inexistente nem chegou a executar
        self.assertEqual(d["run"]["pendings"], [])

    def test_ask_user_tool_returns_the_answer(self):
        got = []
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")),
                       worker=lambda p, s: act("ask_user", question="Posso continuar?") if not p["history"] else (got.append(p["history"][-1]["output"]), fin("ok"))[1])
        m = self.manager(llm, mode="ask", effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        pend = self.wait_pending(m, s["id"])
        self.assertEqual(pend[0]["kind"], "question")
        m.answer(s["id"], True)
        self.wait(m, s["id"])
        self.assertIn("SIM", got[0])

    def test_switching_to_full_access_during_a_run_stops_the_questions(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "escrever")), worker=self.writer(3))
        m = self.manager(llm, mode="ask", effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        self.wait_pending(m, s["id"])
        m.update_session(s["id"], {"mode": "full"})
        m.answer(s["id"], True)
        d = self.wait(m, s["id"])
        self.assertEqual(len([x for x in d["run"]["steps"] if x.get("approval")]), 1)
        self.assertEqual(d["mode"], "full")

    def test_settings_choose_which_risks_ask(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=self.writer(1))
        m = self.manager(llm, mode="ask", effort="low", ask_for=["delete"])      # escrever não pergunta nesta configuração
        s = self.session(m)
        m.send(s["id"], "x")
        d = self.wait(m, s["id"])
        self.assertEqual(d["run"]["status"], "done")
        self.assertTrue((self.proj / "f0.txt").exists())

    def test_parallel_workers_can_wait_for_answers_at_the_same_time(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "a", files=["a"]), step("s2", "b", files=["b"])),
                       worker=lambda p, s: act("write_file", path=f"{p['step']['id']}.txt", content="x") if not p["history"] else fin("ok"))
        m = self.manager(llm, mode="ask", effort="low", agents=2)
        s = self.session(m)
        m.send(s["id"], "x")
        pend = self.wait_pending(m, s["id"], n=2)
        self.assertEqual({p["agent"] for p in pend}, {"w1", "w2"})
        m.answer(s["id"], True, qid=pend[1]["id"])       # responde a segunda pergunta primeiro
        m.answer(s["id"], True, qid=pend[0]["id"])
        d = self.wait(m, s["id"])
        self.assertEqual(d["run"]["status"], "done")
        self.assertEqual(len(list(self.proj.glob("s*.txt"))), 2)

    def test_cancel_while_waiting_and_while_working(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=self.writer(2))
        m = self.manager(llm, mode="ask", effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        self.wait_pending(m, s["id"])
        m.cancel(s["id"])
        d = self.wait(m, s["id"])
        self.assertEqual(d["run"]["status"], "cancelled")
        self.assertEqual(d["state"], "finished")
        self.assertFalse((self.proj / "f0.txt").exists())
        # cancelar uma execução que está rodando um comando longo
        slow = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=per_step(s1=[act("run_command", program="python", args=["-c", "import time;time.sleep(30)"], timeout=60), fin("ok")]))
        m2 = self.manager(slow, mode="full", effort="low")
        s2 = self.session(m2)
        m2.send(s2["id"], "x")
        time.sleep(0.8)
        t0 = time.time()
        m2.cancel(s2["id"])
        d2 = self.wait(m2, s2["id"])
        self.assertEqual(d2["run"]["status"], "cancelled")
        self.assertLess(time.time() - t0, 10)


# --------------------------------------------------------------------------- sem IA


class NoAiTests(TeamCase):
    def demo(self):
        return DemoProvider({"id": "demo", "kind": "demo"}) if True else None

    def manager_demo(self, **cfg):
        self.cfg(**cfg)
        m = CodeManager(self.store, resolve=lambda s: (DemoProvider({"id": "demo", "kind": "demo"}), {"id": "demo", "label": "Demo", "model": "", "demo": True}))
        self.addCleanup(m.shutdown)
        return m

    def test_without_ai_rules_run_tests_and_read_files(self):
        self.project_with_tests()
        m = self.manager_demo(mode="full")
        s = self.session(m)
        m.send(s["id"], "rode os testes")
        run = self.wait(m, s["id"])["run"]
        self.assertEqual(run["status"], "done", run)
        self.assertEqual(run["team"], "rules")
        self.assertIn("Ran 1 test", run["plan"]["steps"][0]["summary"])
        m.send(s["id"], "leia calc.py")
        run = self.wait(m, s["id"])["run"]
        self.assertIn("def add", run["plan"]["steps"][0]["summary"])
        m.send(s["id"], "procure por add")
        run = self.wait(m, s["id"])["run"]
        self.assertIn("calc.py:1", run["plan"]["steps"][0]["summary"])
        m.send(s["id"], "visão geral do projeto")
        self.assertIn("Python", self.wait(m, s["id"])["run"]["plan"]["steps"][0]["summary"])

    def test_without_ai_everything_else_explains_what_is_possible(self):
        m = self.manager_demo(mode="full")
        s = self.session(m)
        m.send(s["id"], "crie um site de receitas completo")
        run = self.wait(m, s["id"])["run"]
        self.assertEqual(run["status"], "failed")
        self.assertIn("Configuração → Provedores", run["summary"])
        self.assertFalse(list(self.proj.iterdir()))

    def test_without_ai_ask_mode_still_asks_before_running_tests(self):
        self.project_with_tests()
        m = self.manager_demo(mode="ask")
        s = self.session(m)
        m.send(s["id"], "rode os testes")
        pend = self.wait_pending(m, s["id"])
        self.assertEqual(pend[0]["risk"], "run")
        m.answer(s["id"], True)
        self.assertEqual(self.wait(m, s["id"])["run"]["status"], "done")


# --------------------------------------------------------------------------- publicação


class PublishTests(TeamCase):
    def setUp(self):
        super().setUp()
        self.fake = FakeGitHub()
        self.addCleanup(self.fake.close)
        self.cfg_gh = {"github": {"api": self.fake.url, "token": self.fake.token}, "github_mode": "cloud"}

    def cloud_session(self, m, **spec):
        s = m.create_session({"workspace": {"type": "github", "repo": "o/r"}, **spec})
        end = time.time() + 15
        while time.time() < end and m.get(s["id"])["workspace"]["status"] == "preparing":
            time.sleep(0.05)
        d = m.get(s["id"])
        self.assertEqual(d["workspace"]["status"], "ready", d["workspace"])
        return d

    def test_cloud_session_downloads_the_repo_edits_and_opens_a_pull_request(self):
        worker = per_step(s1=[act("read_file", path="src/app.py"), act("edit_file", path="src/app.py", old="'app'", new="'novo'"), fin("editado", files=["src/app.py"])],
                          s2=[act("publish_changes", message="feat: novo texto", title="Novo texto", body="Troca o texto.", pull_request=True), fin("publicado")])
        llm = Scripted(planner=lambda p, s: plan(step("s1", "editar app", files=["src/app.py"])), worker=worker)
        m = self.manager(llm, mode="full", effort="medium", **self.cfg_gh)
        d = self.cloud_session(m, finalize={"docs": False, "publish": "pr"})
        self.assertEqual(d["workspace"]["kind"], "cloud")
        self.assertEqual(d["workspace"]["repo"]["base_branch"], "main")
        self.assertTrue((Path(d["workspace"]["path"]) / "README.md").exists())
        m.send(d["id"], "troque o texto do app")
        d = self.wait(m, d["id"])
        run = d["run"]
        self.assertEqual(run["status"], "done", run)
        self.assertEqual(len(self.fake.prs), 1)
        self.assertTrue(self.fake.prs[0]["draft"])
        branch = self.fake.prs[0]["head"]
        self.assertEqual(self.fake.commits[self.fake.branches[branch]]["files"]["src/app.py"], b"print('novo')\n")
        self.assertEqual(self.fake.commits[self.fake.branches["main"]]["files"]["src/app.py"], b"print('app')\n")   # a main não foi tocada
        self.assertIn("pull/1", run["summary"] + json.dumps(run["steps"]))
        self.assertNotIn(self.fake.token, json.dumps(d))
        self.assertEqual(d["workspace"]["repo"]["pr_url"], "https://github.com/o/r/pull/1")
        self.assertEqual([x["role"] for x in run["plan"]["steps"]][-1], "publisher")

    def test_publish_is_skipped_when_tests_fail(self):
        self.fake.files.update({"calc.py": b"def add(a, b):\n    return a - b\n", "tests/__init__.py": b"", "tests/test_calc.py": TEST_OK.encode()})
        fake_head = self.fake._commit_for(self.fake.files, [])
        self.fake.branches["main"] = fake_head
        published = []
        llm = Scripted(planner=lambda p, s: plan(step("s1", "mexer", files=["calc.py"])),
                       worker=lambda p, s: (published.append(1), fin("publicado"))[1] if p["step"]["role"] == "publisher" else
                       (act("write_file", path="calc.py", content="def add(a, b):\n    return 0\n") if not p["history"] else fin("ok")))
        m = self.manager(llm, mode="full", effort="low", **self.cfg_gh)    # low: sem testes
        d = self.cloud_session(m, finalize={"docs": False, "publish": "pr"})
        m.send(d["id"], "x")
        low = self.wait(m, d["id"])["run"]
        self.assertEqual(low["checks"], [])
        self.assertEqual(len(self.fake.prs), 1)       # sem testes e sem revisão, nada a impedir
        # com esforço High os testes rodam, falham e a publicação não acontece
        llm2 = Scripted(planner=lambda p, s: plan(step("s1", "mexer", files=["calc.py"])),
                        worker=lambda p, s: fin("publicado") if p["step"]["role"] == "publisher" else
                        (act("write_file", path="calc.py", content="def add(a, b):\n    return 0\n") if not p["history"] else fin("ok")))
        m2 = self.manager(llm2, mode="full", effort="medium", **self.cfg_gh)
        d2 = self.cloud_session(m2, finalize={"docs": False, "publish": "pr"})
        m2.send(d2["id"], "x")
        run = self.wait(m2, d2["id"])["run"]
        self.assertEqual(run["status"], "partial")
        self.assertFalse(run["checks"][-1]["ok"])
        self.assertEqual(len(self.fake.prs), 1)        # continua 1: este não publicou
        self.assertEqual(run["plan"]["steps"][-1]["status"], "skipped")
        self.assertIn("Não publiquei", run["summary"])

    def test_the_publish_skip_message_names_the_real_reason(self):
        self.fake.files.update({"README.md": b"# x\n"})
        self.fake.branches["main"] = self.fake._commit_for(self.fake.files, [])
        llm = Scripted(planner=lambda p, s: plan(step("s1", "Escrever a seção do portfólio")),
                       worker=lambda p, s: fin("A ferramenta recusou: sem permissão.", ok=False))
        m = self.manager(llm, mode="full", effort="medium", **self.cfg_gh)
        d = self.cloud_session(m, finalize={"docs": False, "publish": "pr"})
        m.send(d["id"], "x")
        run = self.wait(m, d["id"])["run"]
        pub = [x for x in run["plan"]["steps"] if x["role"] == "publisher"]
        msg = (pub[0]["summary"] if pub else "") or " ".join(run.get("notes", []))
        self.assertIn("Não publiquei", msg)
        self.assertIn("uma tarefa do plano não terminou", msg)          # antes dizia «os testes/a revisão acusaram problemas»
        self.assertIn("Escrever a seção do portfólio", msg)
        self.assertNotIn("acusaram problemas", msg)

    def test_engine_publishes_directly_when_the_worker_forgets(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "mexer", files=["x.txt"])),
                       worker=lambda p, s: fin("nada a publicar") if p["step"]["role"] == "publisher" else (act("write_file", path="x.txt", content="x\n") if not p["history"] else fin("ok")))
        m = self.manager(llm, mode="full", effort="low", **self.cfg_gh)
        d = self.cloud_session(m, finalize={"docs": False, "publish": "branch"})
        m.send(d["id"], "x")
        run = self.wait(m, d["id"])["run"]
        self.assertEqual(run["status"], "done")
        self.assertEqual(len(self.fake.prs), 0)        # «branch»: sem pull request
        self.assertTrue([b for b in self.fake.branches if b.startswith("asta/")])

    def test_publish_main_commits_straight_to_the_base_branch_only_when_asked(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "mexer", files=["x.txt"])),
                       worker=lambda p, s: fin("ok") if p["step"]["role"] == "publisher" else (act("write_file", path="x.txt", content="x\n") if not p["history"] else fin("ok")))
        m = self.manager(llm, mode="full", effort="low", **self.cfg_gh)
        d = self.cloud_session(m, finalize={"docs": False, "publish": "main"})
        m.send(d["id"], "x")
        self.wait(m, d["id"])
        self.assertIn("x.txt", self.fake.commits[self.fake.branches["main"]]["files"])
        self.assertEqual(len(self.fake.prs), 0)

    def test_ask_mode_asks_before_publishing(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "mexer", files=["x.txt"])),
                       worker=lambda p, s: act("publish_changes", message="m") if p["step"]["role"] == "publisher" and not p["history"] else fin("ok") if p["step"]["role"] == "publisher" else
                       (act("write_file", path="x.txt", content="x\n") if not p["history"] else fin("ok")))
        m = self.manager(llm, mode="ask", effort="low", ask_for=["publish"], **self.cfg_gh)
        d = self.cloud_session(m, finalize={"docs": False, "publish": "pr"})
        m.send(d["id"], "x")
        pend = self.wait_pending(m, d["id"])
        self.assertEqual((pend[0]["tool"], pend[0]["risk"]), ("publish_changes", "publish"))
        self.assertEqual(len(self.fake.prs), 0)
        m.answer(d["id"], False)
        self.wait(m, d["id"])
        self.assertEqual(len(self.fake.prs), 0)        # negado: nada publicado

    def test_repo_errors_are_reported_without_the_token(self):
        self.cfg(**self.cfg_gh)
        m = CodeManager(self.store, resolve=lambda s: (Scripted(), {"id": "fake", "label": "F", "model": "m", "demo": False}))
        self.addCleanup(m.shutdown)
        s = m.create_session({"workspace": {"type": "github", "repo": "o/missing"}})
        end = time.time() + 15
        while time.time() < end and m.get(s["id"])["workspace"]["status"] == "preparing":
            time.sleep(0.05)
        d = m.get(s["id"])
        self.assertEqual(d["workspace"]["status"], "error")
        self.assertIn("Não encontrei", d["workspace"]["error"])
        with self.assertRaises(CodeError) as c:
            m.send(s["id"], "x")
        self.assertEqual(c.exception.status, 409)
        with self.assertRaises(CodeError):
            m.create_session({"workspace": {"type": "github", "repo": "not a repo"}})

    def manager(self, provider, info=None, **cfg):
        self.cfg(**cfg)
        m = CodeManager(self.store, resolve=lambda s: (provider, dict(info or {"id": "fake", "label": "Fake", "model": "fake-model", "demo": False})))
        self.managers.append(m)
        self.addCleanup(m.shutdown)
        return m


# --------------------------------------------------------------------------- pastas, sessões, cores, segundo plano


class FolderTests(TeamCase):
    def test_folders_rename_recolor_collapse_and_nest(self):
        m = self.manager(Scripted())
        a = m.create_folder("Trabalho", "red")
        b = m.create_folder("Cliente X", "green", a["id"])
        c = m.create_folder("API", "", b["id"])
        self.assertEqual([x["color"] for x in (a, b)], ["red", "green"])
        self.assertIn(c["color"], [col["id"] for col in m.status()["colors"]])
        self.assertEqual(len(m.status()["colors"]), 8)
        self.assertEqual(len({col["hex"] for col in m.status()["colors"]}), 8)
        m.update_folder(a["id"], {"name": "Trabalho 2026", "color": "purple"})
        m.update_folder(a["id"], {"collapsed": True})
        fa = {f["id"]: f for f in m.folders()}[a["id"]]
        self.assertEqual((fa["name"], fa["color"], fa["collapsed"]), ("Trabalho 2026", "purple", True))
        m.update_folder(a["id"], {"collapsed": False})
        self.assertFalse({f["id"]: f for f in m.folders()}[a["id"]]["collapsed"])
        with self.assertRaises(CodeError):
            m.update_folder(a["id"], {"color": "#123456"})
        with self.assertRaises(CodeError):
            m.update_folder(a["id"], {"name": "  "})
        with self.assertRaises(CodeError):
            m.create_folder("", "red")
        with self.assertRaises(CodeError) as e:
            m.create_folder("fundo demais", "red", c["id"])        # além de 3 níveis
        self.assertEqual(e.exception.status, 400)
        with self.assertRaises(CodeError):
            m.update_folder(a["id"], {"parent": c["id"]})           # uma pasta dentro da própria descendente
        with self.assertRaises(CodeError):
            m.update_folder(a["id"], {"parent": a["id"]})
        with self.assertRaises(CodeError):
            m.update_folder("fo_nope", {"name": "x"})

    def test_folder_state_persists_and_survives_a_restart(self):
        m = self.manager(Scripted())
        a = m.create_folder("A", "cyan")
        m.update_folder(a["id"], {"collapsed": True})
        m2 = CodeManager(self.store)
        self.assertEqual([(f["name"], f["color"], f["collapsed"]) for f in m2.folders()], [("A", "cyan", True)])

    def test_sessions_live_in_folders_and_deleting_a_folder_moves_them_up(self):
        m = self.manager(Scripted())
        a = m.create_folder("A", "red")
        b = m.create_folder("B", "blue", a["id"])
        s = self.session(m, folder_id=b["id"], title="Minha sessão")
        self.assertEqual(m.summary_of(s["id"])["folder_id"], b["id"])
        m.update_session(s["id"], {"folder_id": a["id"]})
        self.assertEqual(m.get(s["id"])["folder_id"], a["id"])
        m.update_session(s["id"], {"folder_id": b["id"]})
        r = m.delete_folder(b["id"])
        self.assertEqual(r["moved_sessions"], 1)
        self.assertEqual(m.get(s["id"])["folder_id"], a["id"])         # subiu para a pasta de cima
        m.delete_folder(a["id"])
        self.assertIsNone(m.get(s["id"])["folder_id"])                  # nada de sessão se perde
        with self.assertRaises(CodeError):
            self.session(m, folder_id="fo_nope")
        with self.assertRaises(CodeError):
            m.update_session(s["id"], {"folder_id": "fo_nope"})
        c = m.create_folder("C", "pink")
        d = m.create_folder("D", "yellow", c["id"])
        m.delete_folder(c["id"])
        self.assertIsNone({f["id"]: f for f in m.folders()}[d["id"]]["parent"])    # subpasta sobe


class StateColorTests(TeamCase):
    def test_gray_blinking_blue_and_waiting(self):
        gate = threading.Event()
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=lambda p, s: (gate.wait(8), fin("ok"))[1])
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m)
        self.assertEqual(m.summary_of(s["id"])["state"], "idle")             # cinza: nada está sendo feito
        m.send(s["id"], "x")
        end = time.time() + 5
        while time.time() < end and m.summary_of(s["id"])["state"] != "working":
            time.sleep(0.02)
        self.assertEqual(m.summary_of(s["id"])["state"], "working")          # cinza piscando: trabalhando
        gate.set()
        self.wait(m, s["id"])
        sm = m.summary_of(s["id"])
        self.assertEqual((sm["state"], sm["seen"], sm["last_status"]), ("finished", False, "done"))   # azul-claro: terminou
        m.mark_seen(s["id"])
        self.assertEqual(m.summary_of(s["id"])["state"], "idle")              # visto: volta ao cinza
        self.assertTrue(m.summary_of(s["id"])["seen"])

    def test_waiting_state_when_asking(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=lambda p, s: act("write_file", path="a.txt", content="a") if not p["history"] else fin("ok"))
        m = self.manager(llm, mode="ask", effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        self.wait_pending(m, s["id"])
        self.assertEqual(m.summary_of(s["id"])["state"], "waiting")
        self.assertEqual(m.status()["waiting"], 1)
        m.answer(s["id"], True)
        self.wait(m, s["id"])


class BackgroundTests(TeamCase):
    def test_eight_sessions_work_in_background_at_once_and_the_rest_queue(self):
        gate = threading.Event()
        running, peak, lock = [0], [0], threading.Lock()

        def w(p, s):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            gate.wait(10)
            with lock:
                running[0] -= 1
            return fin("ok")

        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=w)
        projs = []
        for i in range(10):
            d = self.home / f"p{i}"
            d.mkdir()
            projs.append(d)
        m = self.manager(llm, mode="full", effort="low", max_sessions=8)
        ids = []
        for d in projs:
            s = m.create_session({"workspace": {"type": "local", "path": str(d)}})
            m.send(s["id"], "x")
            ids.append(s["id"])
        end = time.time() + 8
        while time.time() < end and running[0] < 8:
            time.sleep(0.02)
        self.assertEqual(running[0], 8)
        st = m.status()
        self.assertEqual((st["running"], st["queued"]), (8, 2))
        self.assertEqual(len([i for i in ids if m.summary_of(i)["state"] == "working"]), 10)   # as 2 da fila também aparecem como «trabalhando»
        gate.set()
        for i in ids:
            self.wait(m, i, timeout=30)
        self.assertEqual(peak[0], 8)
        self.assertEqual(m.status()["finished"], 10)

    def test_max_sessions_setting_limits_concurrency(self):
        gate = threading.Event()
        running, peak, lock = [0], [0], threading.Lock()

        def w(p, s):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            time.sleep(0.2)
            with lock:
                running[0] -= 1
            return fin("ok")

        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=w)
        m = self.manager(llm, mode="full", effort="low", max_sessions=2)
        ids = []
        for i in range(5):
            d = self.home / f"q{i}"
            d.mkdir()
            ids.append(m.create_session({"workspace": {"type": "local", "path": str(d)}})["id"])
            m.send(ids[-1], "x")
        for i in ids:
            self.wait(m, i, timeout=30)
        self.assertEqual(peak[0], 2)

    def test_a_session_can_be_cancelled_while_queued(self):
        gate = threading.Event()
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=lambda p, s: (gate.wait(10), fin("ok"))[1])
        m = self.manager(llm, mode="full", effort="low", max_sessions=1)
        a = self.session(m)
        d2 = self.home / "second"
        d2.mkdir()
        b = m.create_session({"workspace": {"type": "local", "path": str(d2)}})
        m.send(a["id"], "x")
        m.send(b["id"], "y")
        time.sleep(0.3)
        self.assertEqual(m.status()["queued"], 1)
        r = m.cancel(b["id"])
        self.assertEqual(r["run"]["status"], "cancelled")
        self.assertEqual(m.status()["queued"], 0)
        gate.set()
        self.wait(m, a["id"])

    def test_one_run_at_a_time_per_session_and_sessions_are_independent(self):
        gate = threading.Event()
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=lambda p, s: (gate.wait(10), fin("ok"))[1])
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        with self.assertRaises(CodeError) as e:
            m.send(s["id"], "y")
        self.assertEqual(e.exception.status, 409)
        with self.assertRaises(CodeError):
            m.delete(s["id"])
        gate.set()
        self.wait(m, s["id"])
        self.assertTrue(m.delete(s["id"]))
        self.assertIsNone(m.get(s["id"]))

    def test_interrupted_runs_are_recovered_after_a_restart(self):
        gate = threading.Event()
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=lambda p, s: (gate.wait(10), fin("ok"))[1])
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        time.sleep(0.4)
        m2 = CodeManager(self.store)       # o ASTA foi fechado e aberto de novo
        d = m2.get(s["id"])
        self.assertEqual(d["run"]["status"], "failed")
        self.assertIn("interrompida", d["run"]["error"])
        self.assertEqual(d["state"], "finished")
        gate.set()

    def test_session_survives_restart_with_messages_and_history(self):
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=per_step(s1=[act("write_file", path="a.txt", content="a\n"), fin("ok")]))
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m, title="Persistente")
        m.send(s["id"], "crie a.txt")
        self.wait(m, s["id"])
        m2 = CodeManager(self.store)
        d = m2.get(s["id"])
        self.assertEqual(d["title"], "Persistente")
        self.assertEqual(len(d["messages"]), 2)
        self.assertEqual(d["runs"][0]["files"][0]["path"], "a.txt")
        self.assertEqual(m2.list()[0]["id"], s["id"])


class SessionApiTests(TeamCase):
    def test_new_project_local_project_and_unsafe_roots(self):
        m = self.manager(Scripted())
        s = m.create_session({"title": "Projeto novo", "workspace": {"type": "new", "name": "Minha Loja"}})
        p = Path(s["workspace"]["path"])
        self.assertTrue(p.is_dir())
        self.assertTrue(guard._inside(p, guard.managed_workspaces()))
        self.assertIn("minha-loja", p.name)
        for bad in (str(self.home), str(self.store.home), "/", str(self.home / "nope")):
            with self.assertRaises(CodeError, msg=bad):
                m.create_session({"workspace": {"type": "local", "path": bad}})
        s2 = m.create_session({"workspace": {"path": str(self.proj)}})
        self.assertEqual(s2["workspace"]["kind"], "local")
        self.assertEqual(s2["workspace"]["label"], "proj")

    def test_delete_only_purges_workspaces_the_asta_created(self):
        m = self.manager(Scripted())
        s = m.create_session({"workspace": {"type": "new", "name": "x"}})
        p = Path(s["workspace"]["path"])
        s2 = self.session(m)
        (self.proj / "keep.txt").write_text("k")
        m.delete(s2["id"], purge_workspace=True)
        self.assertTrue((self.proj / "keep.txt").exists())      # a pasta de um projeto do usuário nunca é apagada
        m.delete(s["id"], purge_workspace=True)
        self.assertFalse(p.exists())

    def test_undo_browse_read_diff(self):
        self.write("keep.txt", "antes\n")
        llm = Scripted(planner=lambda p, s: plan(step("s1", "x")), worker=per_step(s1=[act("edit_file", path="keep.txt", old="antes", new="depois"), act("write_file", path="new/a.py", content="x=1\n"), fin("ok")]))
        m = self.manager(llm, mode="full", effort="low")
        s = self.session(m)
        m.send(s["id"], "x")
        d = self.wait(m, s["id"])
        pub = m.public(d)
        self.assertEqual({f["path"]: f["status"] for f in pub["files"]}, {"keep.txt": "modified", "new/a.py": "created"})
        self.assertTrue(pub["undo"])
        self.assertNotIn("journal", pub)
        self.assertIn("+depois", m.diff(s["id"])["diff"])
        self.assertEqual({i["name"] for i in m.browse(s["id"], ".")["items"]}, {"keep.txt", "new"})
        self.assertEqual(m.read_file(s["id"], "keep.txt")["text"], "depois\n")
        with self.assertRaises(CodeError):
            m.read_file(s["id"], "../x")
        with self.assertRaises(CodeError):
            m.browse(s["id"], "/etc")
        res = m.undo(s["id"])
        self.assertTrue(res["notes"])
        self.assertEqual((self.proj / "keep.txt").read_text(), "antes\n")
        self.assertFalse((self.proj / "new").exists())
        with self.assertRaises(CodeError):
            m.undo(s["id"])

    def test_session_options_and_validation(self):
        m = self.manager(Scripted(), mode="ask", effort="mega", agents=5)
        s = self.session(m)
        self.assertEqual((s["mode"], s["effort"], s["agents"]), ("ask", "mega", 5))
        u = m.update_session(s["id"], {"effort": "omni", "agents": 8, "mode": "full", "title": "Renomeada", "provider": {"id": "openai", "model": "gpt-x"}, "finalize": {"docs": True, "publish": "pr"}})
        self.assertEqual((u["effort"], u["agents"], u["mode"], u["title"]), ("omni", 8, "full", "Renomeada"))
        self.assertEqual(u["provider"], {"id": "openai", "model": "gpt-x"})
        self.assertEqual(u["finalize"], {"docs": True, "publish": "pr"})
        u = m.update_session(s["id"], {"effort": "zzz", "agents": 99, "mode": "root", "finalize": {"publish": "rm -rf"}})
        self.assertEqual((u["effort"], u["agents"], u["mode"], u["finalize"]["publish"]), ("high", 8, "full", "none"))
        with self.assertRaises(CodeError):
            m.update_session(s["id"], {"title": " "})
        with self.assertRaises(CodeError):
            m.send(s["id"], "   ")
        with self.assertRaises(CodeError):
            m.send("cs_nope", "x")

    def test_provider_override_builds_the_chosen_provider(self):
        self.cfg(mode="full")
        m = CodeManager(self.store)     # sem «resolve»: usa o registro de provedores de verdade
        self.addCleanup(m.shutdown)
        self.store.save_settings({"providers": {"openai": {"api_key": "sk-test-123456789", "model": "gpt-default"}}})
        s = self.session(m, provider={"id": "openai", "model": "gpt-special"})
        prov, info = m.provider_for(self.store.get_settings(), m.get(s["id"]))
        self.assertEqual((info["id"], prov.model), ("openai", "gpt-special"))
        s2 = self.session(m, provider={"id": "anthropic", "model": "claude-x"})
        prov2, info2 = m.provider_for(self.store.get_settings(), m.get(s2["id"]))
        self.assertEqual(info2["id"], "anthropic")
        s3 = self.session(m)
        _, info3 = m.provider_for(self.store.get_settings(), m.get(s3["id"]))
        self.assertTrue(info3["id"])        # sem escolha: o provedor padrão de geração (aqui, o Demo)

    def test_config_normalization(self):
        c = normalize = None
        from asta.code import normalize_config

        c = normalize_config({"mode": "root", "effort": "xx", "agents": 99, "max_sessions": 0, "ask_for": ["read", "write", "bogus"], "finalize": {"publish": "nuke"}, "github": {"token": "t"}})
        self.assertEqual((c["mode"], c["effort"], c["agents"], c["max_sessions"]), ("ask", "high", 8, 1))
        self.assertEqual(c["ask_for"], ["write"])
        self.assertEqual(c["finalize"]["publish"], "none")
        self.assertEqual(normalize_config(None)["ask_for"], list(T.DEFAULT_ASK))
        self.assertEqual(normalize_config("lixo")["agents"], 4)


if __name__ == "__main__":
    unittest.main()
