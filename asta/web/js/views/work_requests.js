// Work → Pedidos: caixa de entrada e de saída. Cada pedido tem conversa, anexos, checklist, o caminho no fluxograma e a ponte para as outras seções do ASTA.
import { api, avatarEl, chip, fmtAgo, fmtSize, fmtWhen, h, icon, PRIORITY, prioTone, REQ_STATUS, statusTone, t, toast, uploadFile, userName } from '../work_ui.js';
import { confirmDialog, fill, popover } from '../ui.js';
import { renderMarkdown } from '../markdown.js';
import { openComposer } from './work_compose.js';
import { go as appGo } from '../main.js';

// para onde levar o pedido: cada destino abre a seção do ASTA com o texto do pedido já preenchido
const HANDOFF = [['main', 'Chat', 'main', {}], ['engine', 'Game Engine', 'engine', {}], ['world', 'Mundo 3D', 'worlds', { mode: 'world' }], ['game', 'Jogo 2D', 'games', { mode: 'game' }], ['avatar', 'Avatar', 'avatars', { mode: 'avatar' }], ['canvas', 'Canvas', 'canvas', { mode: 'canvas' }],
  ['studio', 'Studio', 'studio', {}], ['code', 'Code', 'code', {}], ['computer', 'Computer Use', 'computer', {}]];

export default async function render(box, W) {
  const S = { box: 'in', list: [], sel: W.arg && W.arg !== 'new' ? W.arg : '', cur: null };
  const listEl = h('aside', { class: 'cu-list wk-rlist', id: 'wk-rlist' });
  const mainEl = h('section', { class: 'cu-main', id: 'wk-rmain', 'aria-live': 'polite' });
  box.replaceChildren(h('div', { class: 'cu-split' }, listEl, mainEl));

  async function loadList() {
    try { S.list = (await api('/api/work/requests?box=' + S.box)).requests; } catch (e) { S.list = []; toast(e.message, 'err'); }
    paintList();
  }
  function paintList() {
    const seg = [['in', t('Recebidos')], ['out', t('Enviados')], ...(W.can('requests.view_all') ? [['all', t('Todos')]] : [])];
    fill(listEl, W.can('requests.send') ? h('button', { class: 'btn primary cu-new', id: 'wk-rq-new', type: 'button', onclick: compose }, icon('plus', 15), t('Novo pedido')) : null,
      h('div', { class: 'seg', style: { margin: '6px 0' } }, seg.map(([k, l]) => h('button', { type: 'button', class: S.box === k ? 'on' : '', dataset: { box: k }, onclick: () => { S.box = k; loadList(); } }, l))),
      ...S.list.map((r) => h('button', { class: 'cu-item' + (S.sel === r.id ? ' on' : '') + (r.unread ? ' ask' : ''), type: 'button', dataset: { id: r.id, status: r.status }, onclick: () => select(r.id) },
        h('span', { class: 'cu-dot ' + ({ done: 'ok', rejected: 'err', cancelled: 'dim' }[r.status] || (r.unread ? 'warn' : 'info')) }),
        h('span', { class: 'grow' }, h('span', { class: 'cu-t' }, (r.unread ? '● ' : '') + r.title), h('span', { class: 'cu-s' }, (S.box === 'out' ? t('para {n}', { n: (r.to || []).map((id) => userName(W.dir, id)).join(', ') }) : t('de {n}', { n: userName(W.dir, r.from) })) + ' · ' + REQ_STATUS()[r.status] + ' · ' + fmtAgo(r.updated))))),
      !S.list.length ? h('div', { class: 'dim small cu-none' }, S.box === 'in' ? t('Nenhum pedido recebido ainda.') : t('Nada por aqui.')) : null);
  }
  async function compose() { const r = await openComposer(W, {}); if (r) { S.box = 'out'; S.sel = r.id; await loadList(); await select(r.id); } }
  async function select(id) {
    S.sel = id; history.replaceState(null, '', '#/work/requests' + (id ? '/' + id : ''));
    await show(); await loadList();
  }
  async function show() {
    if (!S.sel) { S.cur = null; return fill(mainEl, h('div', { class: 'card' }, h('h3', null, t('Pedidos')), h('p', { class: 'muted' }, t('Escolha um pedido à esquerda ou envie um novo. Cada pedido pode ter texto, arquivos de qualquer formato, ou os dois.')))); }
    try { S.cur = await api('/api/work/requests/' + S.sel); } catch (e) { S.cur = null; return fill(mainEl, h('div', { class: 'errbox' }, e.message)); }
    paintDetail();
  }

  function paintDetail() {
    const r = S.cur, me = W.me.user.id, isTo = (r.to || []).includes(me), isFrom = r.from === me;
    const btn = (label, ic, fn, id, cls = '') => h('button', { class: 'btn sm ' + cls, type: 'button', id, onclick: fn }, icon(ic, 13), label);
    const st = (status, note) => async () => { try { await api(`/api/work/requests/${r.id}/status`, { method: 'POST', body: { status, note: note || '' } }); await show(); await loadList(); } catch (e) { toast(e.message, 'err'); } };
    const actions = [];
    if (isTo || W.me.perms.includes('*')) {
      if (['sent', 'seen'].includes(r.status)) actions.push(btn(t('Aceitar'), 'check', st('accepted'), 'wk-rq-accept'));
      if (['sent', 'seen', 'accepted'].includes(r.status)) actions.push(btn(t('Começar'), 'play', st('in_progress'), 'wk-rq-start', 'primary'));
      if (['accepted', 'in_progress'].includes(r.status)) actions.push(btn(t('Concluir'), 'check', st('done'), 'wk-rq-done', 'primary'));
      if (['sent', 'seen', 'accepted', 'in_progress'].includes(r.status)) actions.push(btn(t('Recusar'), 'x', st('rejected'), 'wk-rq-reject'));
    }
    if ((isFrom || W.can('requests.view_all')) && ['sent', 'seen', 'accepted', 'in_progress'].includes(r.status)) actions.push(btn(t('Cancelar pedido'), 'stop', async () => { if (await confirmDialog(t('Cancelar este pedido?'), true, t('Cancelar pedido'))) st('cancelled')(); }, 'wk-rq-cancel'));
    if ((isFrom || W.can('requests.view_all')) && ['done', 'rejected', 'cancelled'].includes(r.status)) actions.push(btn(t('Reabrir'), 'refresh', st('sent'), 'wk-rq-reopen'));
    const handoff = btn(t('Levar para…'), 'arrow', (e) => openHandoff(e.currentTarget, r), 'wk-rq-handoff');
    const suggest = W.can('ai.use') ? btn(t('Quem deve fazer? (IA)'), 'wand', suggestWho, 'wk-rq-suggest') : null;
    const sugg = h('div', { id: 'wk-rq-sugg' });
    async function suggestWho() { fill(sugg, h('div', { class: 'spinner' })); try { const s = await api('/api/work/ai/suggest', { method: 'POST', body: { request_id: r.id } }); fill(sugg, h('div', { class: 'card' }, h('b', { class: 'small' }, t('Sugestão')), ...(s.recipients.length ? s.recipients.map((x) => h('div', { class: 'small' }, userName(W.dir, x.user) + ' — ' + x.why + ((x.route || []).length ? ' (' + x.route.map((n) => n.label).join(' → ') + ')' : ''))) : [h('div', { class: 'small dim' }, t('Sem sugestão.'))]), s.warning ? h('div', { class: 'small dim' }, s.warning) : null)); } catch (e) { fill(sugg, h('div', { class: 'errbox' }, e.message)); } }
    const files = (m) => (m.attachments || []).map((id) => r.files[id]).filter(Boolean).map((f) => h('a', { class: 'chip solid wk-file', href: `/api/work/files/${f.id}/download`, title: fmtSize(f.size), download: f.name }, icon('clip', 12), f.name, h('span', { class: 'dim small' }, fmtSize(f.size))));
    const msgs = (r.thread || []).map((m) => m.kind === 'status'
      ? h('div', { class: 'wk-evt' }, userName(W.dir, m.by) + ' → ' + (REQ_STATUS()[m.status] || m.status) + (m.text ? ': ' + m.text : '') + ' · ' + fmtWhen(m.ts))
      : h('div', { class: 'wk-msg' + (m.by === me ? ' mine' : '') }, avatarEl(W.dir.users.find((u) => u.id === m.by), 30), h('div', { class: 'grow' }, h('div', { class: 'small dim' }, userName(W.dir, m.by) + ' · ' + fmtWhen(m.ts)),
        m.text ? (() => { const el = h('div', { class: 'md' }); renderMarkdown(el, m.text); return el; })() : null, h('div', { class: 'row', style: { gap: '6px', flexWrap: 'wrap', marginTop: '4px' } }, files(m)))));
    const text = h('textarea', { rows: 3, id: 'wk-rq-reply', placeholder: t('Responder…') });
    const attach = []; const attBox = h('span', { class: 'row', style: { gap: '6px' } });
    const picker = h('input', { type: 'file', multiple: true, class: 'hidden', id: 'wk-rq-reply-file' });
    picker.addEventListener('change', async () => { for (const f of [...picker.files]) { try { attach.push(await uploadFile(f, { request: r.id })); } catch (e) { toast(e.message, 'err'); } } picker.value = ''; fill(attBox, ...attach.map((a) => h('span', { class: 'chip solid' }, a.name))); });
    const reply = async () => { try { await api(`/api/work/requests/${r.id}/reply`, { method: 'POST', body: { text: text.value, attachments: attach.map((a) => a.id) } }); await show(); await loadList(); } catch (e) { toast(e.message, 'err'); } };
    fill(mainEl,
      h('div', { class: 'cu-head' }, h('h2', null, r.title), h('div', { class: 'row cu-meta', style: { flexWrap: 'wrap' } }, chip(REQ_STATUS()[r.status], statusTone(r.status)), r.priority !== 'normal' ? chip(PRIORITY()[r.priority], prioTone(r.priority)) : null,
        r.due ? chip(t('Prazo {d}', { d: r.due }), r.due < new Date().toISOString().slice(0, 10) && ['sent', 'seen', 'accepted', 'in_progress'].includes(r.status) ? 'err' : 'dim') : null,
        h('span', { class: 'small muted' }, t('de {n} para {m}', { n: userName(W.dir, r.from), m: (r.to || []).map((id) => userName(W.dir, id)).join(', ') })))),
      (r.route || []).length > 1 ? h('div', { class: 'wk-route small' }, icon('network', 13), ' ', t('Caminho no fluxograma:') + ' ', r.route.map((x) => x.label).join(' → ')) : null,
      r.checklist && r.checklist.length ? h('div', { class: 'card' }, h('b', { class: 'small' }, t('Checklist')), h('ul', { class: 'wk-checklist' }, r.checklist.map((c) => h('li', null, h('label', { class: 'check' }, h('input', { type: 'checkbox' }), h('span', null, c)))))) : null,
      h('div', { class: 'row cu-actions', style: { gap: '8px', flexWrap: 'wrap' } }, ...actions, handoff, suggest), sugg,
      h('div', { class: 'wk-thread card', id: 'wk-thread' }, ...msgs), h('div', { class: 'card' }, text, h('div', { class: 'row', style: { justifyContent: 'space-between', marginTop: '8px' } }, h('div', { class: 'row' }, h('button', { class: 'btn sm', type: 'button', onclick: () => picker.click() }, icon('clip', 13), t('Anexar')), picker, attBox), h('button', { class: 'btn primary sm', type: 'button', id: 'wk-rq-reply-send', onclick: reply }, icon('send', 13), t('Responder')))));
  }

  function openHandoff(anchor, r) {
    const prompt = r.title + (r.body ? '\n\n' + r.body : '') + (r.checklist && r.checklist.length ? '\n\n' + r.checklist.map((c) => '- ' + c).join('\n') : '');
    const pop = popover(anchor, h('div', { class: 'wk-handoff' }, h('div', { class: 'small dim', style: { padding: '4px 8px' } }, t('Abre a seção com o texto do pedido pronto:')), HANDOFF.map(([id, label, route, ctx]) => h('button', { class: 'toolopt', type: 'button', dataset: { target: id }, onclick: async () => {
      pop.close();
      if (id === 'computer') { try { const res = await api(`/api/work/requests/${r.id}/computer`, { method: 'POST', body: {} }); appGo('computer', { task: res.task.id }); } catch (e) { toast(e.message, 'err'); } return; }
      appGo(route, { ...ctx, prompt });
    } }, label))));
  }

  await loadList();
  if (W.arg === 'new') { history.replaceState(null, '', '#/work/requests'); compose(); }
  await show();
  W.live(['requests'], async () => { await loadList(); if (S.sel) await show(); });
}
