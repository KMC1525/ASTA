// Peças compartilhadas do Computer Use: vocabulário (status, risco, modos, agentes), frases das ações, aprovação Sim/Não, assinatura dos eventos ao vivo e o cartão que aparece no Chat.
import { api } from './api.js';
import { t } from './i18n.js';
import { renderMarkdown } from './markdown.js';
import { h, icon, toast } from './ui.js';

// ------------------------------------------------------------------ vocabulário (funções: o idioma pode mudar depois do carregamento)
export const STATUS = () => ({ queued: t('Na fila'), running: t('Em execução'), waiting: t('Aguardando você'), done: t('Concluída'), partial: t('Parcial'), failed: t('Falhou'), cancelled: t('Cancelada') });
export const RISK = () => ({ read: t('Só leitura'), write: t('Criar ou alterar arquivos'), delete: t('Apagar (vai para a lixeira do ASTA)'), run: t('Abrir programa, jogo ou site'), input: t('Digitar, clicar e apertar teclas'), screen: t('Ver a tela') });
export const MODE = () => ({ ask: t('Ask'), full: t('Full Access') });
export const MODE_HINT = () => ({ ask: t('Pergunta Sim ou Não antes de cada ação que muda algo'), full: t('Executa tudo sem perguntar nada') });
export const AGENT = () => ({
  planner: [t('Planejador'), t('Entende o pedido e monta o roteiro')], operator: [t('Operador'), t('Executa uma ação por vez no computador')],
  verifier: [t('Revisor'), t('Confere se o resultado é o que você pediu')], reporter: [t('Relator'), t('Escreve o resumo final')],
});
export const STEP_STATUS = () => ({ running: t('em andamento'), ok: t('ok'), error: t('erro'), denied: t('negada') });
const ACTIVE = new Set(['queued', 'running', 'waiting']);
export const isActive = (s) => ACTIVE.has(s);
export const statusClass = (s) => ({ done: 'ok', partial: 'warn', failed: 'err', cancelled: 'dim', waiting: 'warn', running: 'info', queued: 'dim' }[s] || 'dim');
export const statusChip = (s) => h('span', { class: 'cu-st ' + statusClass(s), dataset: { status: s } }, s === 'running' ? h('span', { class: 'spinner' }) : null, STATUS()[s] || s);
export const modeChip = (m) => h('span', { class: 'chip cu-mode ' + (m === 'full' ? 'full' : 'ask'), title: MODE_HINT()[m === 'full' ? 'full' : 'ask'] }, icon(m === 'full' ? 'warn' : 'lock', 12), MODE()[m === 'full' ? 'full' : 'ask']);

export function fmtDur(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  if (sec < 60) return sec + 's';
  const m = Math.floor(sec / 60), s = sec % 60;
  return m < 60 ? `${m}min${s ? ' ' + String(s).padStart(2, '0') + 's' : ''}` : `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}min`;
}
export const fmtClock = (ts) => { try { return new Date(ts * 1000).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }); } catch (e) { return ''; } };
export const fmtWhen = (iso) => { try { return new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; } };
const base = (p) => String(p || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop() || String(p || '');
const clip = (s, n = 60) => { s = String(s == null ? '' : s).replace(/\s+/g, ' '); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

// A frase de cada ação (as ferramentas do catálogo fechado de asta/computer/tools.py), no idioma da interface
export function describeAction(tool, a) {
  a = a || {};
  switch (tool) {
    case 'list_dir': return t('Listar a pasta {p}', { p: clip(a.path, 90) });
    case 'read_file': return t('Ler o arquivo {p}', { p: clip(a.path, 90) });
    case 'find_files': return t('Procurar «{q}» em {p}', { q: clip(a.pattern || a.kind || '*', 40), p: clip(a.root, 70) });
    case 'make_dir': return t('Criar a pasta {p}', { p: clip(a.path, 90) });
    case 'create_file': return t('Criar o arquivo {p}', { p: clip(a.path, 90) });
    case 'copy': return t('Copiar {a} para {b}', { a: clip(a.src, 60), b: clip(a.dst, 60) });
    case 'move': return t('Mover {a} para {b}', { a: clip(a.src, 60), b: clip(a.dst, 60) });
    case 'organize_folder': return a.dry_run ? t('Prever a organização da pasta {p}', { p: clip(a.path, 80) }) : t('Organizar a pasta {p} (por {by})', { p: clip(a.path, 80), by: ({ type: t('tipo'), extension: t('extensão'), date: t('data'), name: t('nome') })[a.by || 'type'] || a.by });
    case 'zip_files': return t('Compactar em {p}', { p: clip(a.dst, 90) });
    case 'trash': return t('Mandar para a lixeira do ASTA: {p}', { p: clip(a.path, 90) });
    case 'search_web': return t('Pesquisar na web: «{q}»', { q: clip(a.query, 80) });
    case 'open_url': return t('Abrir o endereço {u}', { u: clip(a.url, 90) });
    case 'open_path': return t('Abrir {p} com o programa padrão', { p: clip(a.path, 90) });
    case 'list_apps': return a.query ? t('Procurar o programa «{n}»', { n: clip(a.query, 40) }) : t('Ver os programas instalados');
    case 'open_app': return t('Abrir o programa «{n}»', { n: clip(a.name, 50) }) + ((a.files || []).length ? ' · ' + t('{n} arquivo(s)', { n: a.files.length }) : '');
    case 'run_program': return t('Rodar o programa {p} {a}', { p: clip(a.program, 40), a: clip((a.args || []).join(' '), 80) });
    case 'list_games': return t('Ver os jogos instalados');
    case 'launch_game': return t('Abrir o jogo «{n}»', { n: clip(a.game || base(a.path), 60) });
    case 'screenshot': return t('Capturar a tela');
    case 'type_text': return t('Digitar: «{x}»', { x: clip(a.text, 90) });
    case 'press_keys': return t('Apertar {k}', { k: clip(a.keys, 40) });
    case 'click': return t('Clicar em ({x}, {y})', { x: a.x, y: a.y });
    case 'scroll': return t('Rolar a tela');
    case 'wait': return t('Esperar {s}s', { s: a.seconds || 2 });
    case 'ask_user': return t('Perguntar a você: {q}', { q: clip(a.question, 100) });
    default: return tool;
  }
}
export const TOOL_ICON = { list_dir: 'folder', read_file: 'doc', find_files: 'search', make_dir: 'folder', create_file: 'file', copy: 'copy', move: 'arrow', organize_folder: 'library', zip_files: 'archive', trash: 'trash',
  search_web: 'globe', open_url: 'globe', open_path: 'file', list_apps: 'search', open_app: 'play', run_program: 'play', list_games: 'games', launch_game: 'games', screenshot: 'image', type_text: 'type', press_keys: 'type',
  click: 'cursor', scroll: 'cursor', wait: 'pause', ask_user: 'warn' };

// ------------------------------------------------------------------ eventos ao vivo (uma só conexão para a página toda)
let es = null;
const subs = new Set();
let last = { running: 0, waiting: 0, queued: 0, enabled: false };
export const computerStatus = () => last;
function ensure() {
  if (es) return;
  es = new EventSource('/api/computer/events');
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

// ------------------------------------------------------------------ aprovação Sim / Não
export function approvalCard(task, onDone) {
  const p = task.pending;
  if (!p || p.answer != null) return null;
  const q = p.kind === 'question';
  const send = async (approve, remember) => {
    btns.forEach((b) => { b.disabled = true; });
    try { await api('/api/computer/tasks/' + task.id + '/answer', { method: 'POST', body: { approve, remember } }); if (onDone) onDone(approve); }
    catch (e) { toast(e.message, 'err'); btns.forEach((b) => { b.disabled = false; }); }
  };
  const remember = h('input', { type: 'checkbox', id: 'cu-remember-' + task.id });
  const yes = h('button', { class: 'btn primary', type: 'button', dataset: { answer: 'yes' }, onclick: () => send(true, remember.checked) }, icon('check', 15), t('Sim'));
  const no = h('button', { class: 'btn', type: 'button', dataset: { answer: 'no' }, onclick: () => send(false, false) }, icon('x', 15), t('Não'));
  const btns = [yes, no];
  return h('div', { class: 'cu-ask', role: 'alertdialog', 'aria-label': t('O Computer Use quer a sua permissão') },
    h('div', { class: 'cu-ask-h' }, icon(q ? 'sparkle' : 'lock', 16), h('b', null, q ? t('O Computer Use pergunta:') : t('O Computer Use quer fazer isto:')), q ? null : h('span', { class: 'chip cu-risk ' + p.risk }, RISK()[p.risk] || p.risk)),
    h('div', { class: 'cu-ask-b' }, q ? p.question : describeAction(p.tool, p.args)),
    h('div', { class: 'row cu-ask-f' }, yes, no,
      q ? null : h('label', { class: 'check cu-remember' }, remember, h('span', null, t('Sim, e não perguntar «{r}» de novo nesta tarefa', { r: (RISK()[p.risk] || p.risk).toLowerCase() })))));
}

// ------------------------------------------------------------------ cartão ao vivo no Chat
export function liveCard(ref, fallbackText, opts = {}) {
  const tid = ref.task_id;
  const el = h('div', { class: 'cu-card', dataset: { task: tid } });
  let task = null, off = null, busy = false, timer = 0;
  const open = () => { if (opts.open) opts.open(tid); else location.hash = '#/computer'; };
  const paint = () => {
    const status = task ? task.status : (ref.status || 'queued');
    const act = isActive(status);
    const head = h('div', { class: 'cu-card-h' }, icon('computer', 16), h('b', null, t('Computer Use')), modeChip(task ? task.mode : ref.mode), statusChip(status), h('span', { class: 'grow' }),
      h('button', { class: 'btn sm', type: 'button', dataset: { open: tid }, onclick: open }, icon('arrow', 13), t('Abrir em Computer Use')));
    const kids = [head];
    if (task && act) {
      const cur = task.now ? describeAction(task.now, (task.steps[task.steps.length - 1] || {}).args) : '';
      const done = (task.plan.steps || []).filter((p) => p.status === 'done').length, total = (task.plan.steps || []).length;
      kids.push(h('div', { class: 'cu-card-s' }, task.note ? task.note : (status === 'queued' ? t('Esperando uma vaga (no máximo 8 tarefas ao mesmo tempo).') : (cur || t('Pensando no que fazer…'))),
        total ? h('span', { class: 'dim' }, ' · ' + t('etapa {a} de {b}', { a: Math.min(total, done + 1), b: total })) : null));
      const ask = approvalCard(task, () => refresh());
      if (ask) kids.push(ask);
      kids.push(h('div', { class: 'row' }, h('button', { class: 'btn sm danger', type: 'button', onclick: async () => { try { await api('/api/computer/tasks/' + tid + '/cancel', { method: 'POST', body: {} }); } catch (e) { toast(e.message, 'err'); } } }, icon('stop', 13), t('Cancelar'))));
    } else {
      const body = h('div', { class: 'md' });
      renderMarkdown(body, (task && task.summary) || fallbackText || '');
      kids.push(body);
      if (task && task.undo) kids.push(h('div', { class: 'dim small' }, t('Mudanças em arquivos podem ser desfeitas na seção Computer Use.')));
    }
    el.replaceChildren(...kids);
  };
  async function refresh() {
    if (busy) return; busy = true;
    try { task = await api('/api/computer/tasks/' + tid); } catch (e) { task = null; }
    busy = false;
    if (!el.isConnected && off) { off(); off = null; return; }
    paint();
    if (task && !isActive(task.status) && off) { off(); off = null; }
  }
  const soon = () => { clearTimeout(timer); timer = setTimeout(refresh, 150); };
  paint();
  refresh().then(() => {
    if (task && isActive(task.status)) off = subscribe((ev) => { if (!el.isConnected) { if (off) { off(); off = null; } return; } if (ev.type === 'hello' || (ev.type === 'task' && ev.task.id === tid)) soon(); });
  });
  return el;
}
