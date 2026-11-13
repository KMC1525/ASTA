// Peças compartilhadas do Code: vocabulário (estados, esforço, modos, papéis dos agentes, risco), frases das ações, aprovação Sim/Não e a assinatura dos eventos ao vivo.
import { api } from './api.js';
import { t } from './i18n.js';
import { h, icon, toast } from './ui.js';

// ------------------------------------------------------------------ vocabulário (funções: o idioma pode mudar depois do carregamento)
// o estado de cada sessão tem uma cor: cinza (parada) · cinza piscando (trabalhando) · azul-claro (terminou) · laranja (espera a sua resposta)
export const STATE = () => ({ idle: t('Parada'), working: t('Trabalhando'), waiting: t('Aguardando você'), finished: t('Terminou') });
export const STATE_DOT = { idle: 'idle', working: 'work', waiting: 'ask', finished: 'done' };
export const RUN_STATUS = () => ({ queued: t('Na fila'), running: t('Em execução'), waiting: t('Aguardando você'), done: t('Concluída'), partial: t('Parcial'), failed: t('Falhou'), cancelled: t('Cancelada') });
export const MODE = () => ({ ask: t('Ask'), full: t('Full Access') });
export const MODE_HINT = () => ({ ask: t('Pergunta Sim ou Não antes de cada ação que muda algo'), full: t('Executa tudo sem perguntar nada') });
export const RISK = () => ({ read: t('Só leitura'), write: t('Criar e editar arquivos'), delete: t('Apagar arquivos do projeto'), run: t('Rodar comandos, testes e programas'), install: t('Instalar dependências'), git: t('Mudar o repositório (git)'), publish: t('Publicar (push, pull request, release)') });
export const EFFORT_LABEL = { low: 'Low', medium: 'Medium', high: 'High', extra: 'Extra', mega: 'Mega', max: 'Max', ultra: 'Ultra', omni: 'Omni' };
export const ROLE = () => ({ architect: t('Arquiteto'), researcher: t('Pesquisador'), coder: t('Programador'), debugger: t('Depurador'), ui: t('Interface'), tester: t('Testador'), docs: t('Documentação'), prompts: t('System prompts'), reviewer: t('Revisor'), publisher: t('Publicador') });
export const PUBLISH = () => ({ none: t('Não publicar'), commit: t('Só commit local'), branch: t('Branch no GitHub'), pr: t('Branch + pull request'), main: t('Direto na branch principal') });
export const STEP_STATUS = () => ({ running: t('em andamento'), ok: t('ok'), error: t('erro'), denied: t('negada') });
export const PLAN_STATUS = () => ({ pending: t('Pendente'), running: t('Em andamento'), done: t('Feita'), failed: t('Falhou'), skipped: t('Pulada') });
export const AGENT = () => ({ planner: [t('Planejador'), t('Entende o pedido e monta o plano')], tests: [t('Testes'), t('Roda os testes e o build do projeto')], reviewer: [t('Revisor'), t('Confere o resultado com as provas')], reporter: [t('Relator'), t('Escreve o resumo final')] });
export const FILE_STATUS = () => ({ created: t('novo'), modified: t('alterado'), deleted: t('apagado') });
export const isBusy = (st) => st === 'working' || st === 'waiting';

export function fmtDur(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  if (sec < 60) return sec + 's';
  const m = Math.floor(sec / 60), s = sec % 60;
  return m < 60 ? `${m}min${s ? ' ' + String(s).padStart(2, '0') + 's' : ''}` : `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}min`;
}
export const fmtWhen = (iso) => { try { return new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; } };
export const fmtClock = (ts) => { try { return new Date(ts * 1000).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }); } catch (e) { return ''; } };
const clip = (s, n = 60) => { s = String(s == null ? '' : s).replace(/\s+/g, ' '); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

// A bolinha de estado de uma sessão
export function stateDot(state, waiting) {
  const k = waiting ? 'ask' : (STATE_DOT[state] || 'idle');
  return h('span', { class: 'cd-dot ' + k, dataset: { dot: k }, title: waiting ? t('Aguardando você') : (STATE()[state] || '') });
}

// A frase de cada ação (as ferramentas do catálogo fechado de asta/code/tools.py), no idioma da interface
export function describeAction(tool, a) {
  a = a || {};
  const args = Array.isArray(a.args) ? a.args.join(' ') : '';
  switch (tool) {
    case 'list_dir': return t('Listar a pasta {p}', { p: clip(a.path || '.', 80) });
    case 'read_file': return t('Ler o arquivo {p}', { p: clip(a.path, 90) }) + (a.start ? ` (${a.start}–${a.end || '…'})` : '');
    case 'search_code': return t('Buscar «{q}» no código', { q: clip(a.pattern, 60) });
    case 'find_files': return t('Procurar arquivos «{q}»', { q: clip(a.pattern || '*', 50) });
    case 'find_todos': return t('Procurar TODO e FIXME no código');
    case 'project_info': return t('Ver a visão geral do projeto');
    case 'view_image': return t('Ver a imagem {p}', { p: clip(a.path, 80) });
    case 'search_web': return t('Pesquisar na web: «{q}»', { q: clip(a.query, 80) });
    case 'fetch_url': return t('Ler a página {u}', { u: clip(a.url, 90) });
    case 'git': return t('git {a}', { a: clip(args, 100) });
    case 'write_file': return t('Escrever o arquivo {p}', { p: clip(a.path, 90) });
    case 'edit_file': return t('Editar o arquivo {p}', { p: clip(a.path, 90) });
    case 'make_dir': return t('Criar a pasta {p}', { p: clip(a.path, 90) });
    case 'move': return t('Mover {a} para {b}', { a: clip(a.src, 60), b: clip(a.dst, 60) });
    case 'copy': return t('Copiar {a} para {b}', { a: clip(a.src, 60), b: clip(a.dst, 60) });
    case 'use_attachment': return t('Usar o anexo {n} em {p}', { n: clip(a.name, 40), p: clip(a.dst, 60) });
    case 'write_system_prompts': return t('Escrever {n} system prompt(s) em .md', { n: a.count || 1 });
    case 'hf_download': return t('Baixar {f} do Hugging Face ({r})', { f: clip(a.file, 50), r: clip(a.repo, 50) });
    case 'hf_search': return t('Pesquisar no Hugging Face: «{q}»', { q: clip(a.query, 60) });
    case 'hf_info': return t('Ver o repositório {r} no Hugging Face', { r: clip(a.repo, 60) });
    case 'delete_path': return t('Apagar {p}', { p: clip(a.path, 90) });
    case 'run_command': return t('Rodar: {c}', { c: clip((a.program || '') + ' ' + args, 110) });
    case 'run_tests': return t('Rodar {k} do projeto', { k: ({ test: t('os testes'), build: t('o build'), lint: t('o linter'), format: t('o formatador') })[a.kind || 'test'] || a.kind }) + (a.command ? ' (' + clip(a.command, 40) + ')' : '');
    case 'install_packages': return t('Instalar com {m}: {p}', { m: a.manager, p: clip((a.packages || []).join(' '), 80) });
    case 'open_in_editor': return t('Abrir {p} no editor', { p: clip(a.path || '.', 70) });
    case 'commit_local': return t('Commit local: {m}', { m: clip(a.message, 80) });
    case 'publish_changes': return (a.main ? t('Publicar direto na branch principal: {m}', { m: clip(a.message, 70) }) : t('Publicar numa branch{pr}: {m}', { pr: a.pull_request === false ? '' : t(' e abrir pull request'), m: clip(a.message, 70) }));
    case 'github_create_pr': return t('Abrir pull request: {m}', { m: clip(a.title, 80) });
    case 'github_create_repo': return t('Criar o repositório {n} no GitHub', { n: clip(a.name, 60) });
    case 'github_comment': return t('Comentar em #{n}', { n: a.number });
    case 'github_release': return t('Publicar a release {n}', { n: clip(a.tag, 40) });
    case 'github_run_workflow': return t('Rodar o workflow {w} no GitHub', { w: clip(a.workflow, 40) });
    case 'github_info': return t('Ver a conexão com o GitHub');
    case 'github_issues': return t('Listar as issues do repositório');
    case 'github_issue': return t('Ler a issue #{n}', { n: a.number });
    case 'github_ci': return t('Ver o resultado do CI');
    case 'ask_user': return t('Perguntar a você: {q}', { q: clip(a.question, 100) });
    case 'wait': return t('Esperar {s}s', { s: a.seconds || 2 });
    default: return tool;
  }
}
export const TOOL_ICON = { list_dir: 'folder', read_file: 'doc', search_code: 'search', find_files: 'search', find_todos: 'check', project_info: 'layers', view_image: 'image', search_web: 'globe', fetch_url: 'globe', git: 'branch',
  write_file: 'file', edit_file: 'edit', make_dir: 'folder', move: 'arrow', copy: 'copy', use_attachment: 'clip', write_system_prompts: 'wand', hf_download: 'download', hf_search: 'search', hf_info: 'search',
  delete_path: 'trash', run_command: 'play', run_tests: 'check', install_packages: 'download', open_in_editor: 'code', commit_local: 'branch', publish_changes: 'upload', github_create_pr: 'branch',
  github_create_repo: 'github', github_comment: 'send', github_release: 'upload', github_run_workflow: 'bolt', github_info: 'github', github_issues: 'github', github_issue: 'github', github_ci: 'github', ask_user: 'warn', wait: 'pause' };

// ------------------------------------------------------------------ eventos ao vivo (uma só conexão para a página toda)
let es = null;
const subs = new Set();
let last = { running: 0, waiting: 0, queued: 0, finished: 0 };
export const codeStatus = () => last;
function ensure() {
  if (es) return;
  es = new EventSource('/api/code/events');
  es.onmessage = (m) => {
    let ev; try { ev = JSON.parse(m.data); } catch (e) { return; }
    if (ev.status) last = ev.status;
    subs.forEach((fn) => { try { fn(ev); } catch (e) { console.error(e); } });
  };
}
export function subscribe(fn) {
  subs.add(fn); ensure();
  return () => { subs.delete(fn); if (!subs.size && es) { es.close(); es = null; } };
}

// ------------------------------------------------------------------ aprovação Sim / Não (pode haver várias perguntas ao mesmo tempo: uma por agente)
export function approvalCards(sid, run, onDone) {
  const pend = (run.pendings || []).filter((p) => p.answer == null);
  return pend.map((p) => {
    const q = p.kind === 'question';
    const send = async (approve, remember) => {
      btns.forEach((b) => { b.disabled = true; });
      try { await api('/api/code/sessions/' + sid + '/answer', { method: 'POST', body: { approve, remember, id: p.id } }); if (onDone) onDone(approve); }
      catch (e) { toast(e.message, 'err'); btns.forEach((b) => { b.disabled = false; }); }
    };
    const remember = h('input', { type: 'checkbox', id: 'cd-remember-' + p.id });
    const yes = h('button', { class: 'btn primary', type: 'button', dataset: { answer: 'yes' }, onclick: () => send(true, remember.checked) }, icon('check', 15), t('Sim'));
    const no = h('button', { class: 'btn', type: 'button', dataset: { answer: 'no' }, onclick: () => send(false, false) }, icon('x', 15), t('Não'));
    const btns = [yes, no];
    const who = p.agent && p.agent.startsWith('w') ? t('Agente {n}', { n: p.agent.slice(1) }) : ((AGENT()[p.agent] || [])[0] || '');
    return h('div', { class: 'cd-ask', role: 'alertdialog', 'aria-label': t('O Code quer a sua permissão'), dataset: { qid: p.id } },
      h('div', { class: 'cd-ask-h' }, icon(q ? 'sparkle' : 'lock', 16), h('b', null, q ? t('O Code pergunta:') : t('O Code quer fazer isto:')), who ? h('span', { class: 'chip' }, who) : null,
        q ? null : h('span', { class: 'chip cd-risk ' + p.risk }, RISK()[p.risk] || p.risk)),
      h('div', { class: 'cd-ask-b' }, q ? p.question : describeAction(p.tool, p.args)),
      q ? null : (p.tool === 'write_file' && p.args && p.args.content ? h('pre', { class: 'cd-ask-pre' }, String(p.args.content).slice(0, 700)) : p.tool === 'edit_file' ? h('pre', { class: 'cd-ask-pre' }, '- ' + String(p.args.old || '').slice(0, 300) + '\n+ ' + String(p.args.new || '').slice(0, 300)) : null),
      h('div', { class: 'row cd-ask-f' }, yes, no, q ? null : h('label', { class: 'check cd-remember' }, remember, h('span', null, t('Sim, e não perguntar «{r}» de novo nesta sessão', { r: (RISK()[p.risk] || p.risk).toLowerCase() })))));
  });
}
