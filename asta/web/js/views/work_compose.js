// Work → enviar pedido: escrito, com arquivos anexados (qualquer formato) ou os dois. A IA pode rascunhar a partir do que você escreveu e dos anexos; você revê antes de enviar.
import { api, avatarEl, dialog, h, icon, PRIORITY, roleOf, t, toast, uploadFile, fmtSize, userName } from '../work_ui.js';
import { field, fill, select } from '../ui.js';
import { teamPicker } from '../team_ui.js';
import { state } from '../main.js';

// opts: { to: [ids], text: '' } → Promise<pedido enviado | null>
export function openComposer(W, opts = {}) {
  const S = { to: [...(opts.to || [])], roles: [], functions: [], files: [], checklist: [], uploading: 0 };
  const title = h('input', { id: 'wk-rq-title', placeholder: t('Título (opcional — sai do começo do texto)') });
  const body = h('textarea', { id: 'wk-rq-body', rows: 7, placeholder: t('Escreva o pedido. Pode anexar arquivos também, ou só enviar os arquivos.') }, opts.text || '');
  const prio = select(Object.entries(PRIORITY()), 'normal', () => {}, { id: 'wk-rq-prio' });
  const due = h('input', { type: 'date', id: 'wk-rq-due' });
  const chips = h('div', { class: 'wk-chips', id: 'wk-rq-to' });
  const filesBox = h('div', { class: 'wk-attach', id: 'wk-rq-files' });
  const checkBox = h('div', { id: 'wk-rq-check' });
  const notes = h('div', { id: 'wk-rq-ai' });
  const err = h('div', { class: 'errbox hidden', style: { whiteSpace: 'normal' }, id: 'wk-rq-err' });
  const people = W.dir.users.filter((u) => !u.disabled && u.id !== W.me.user.id);
  const add = select([['', t('Para quem… (pessoa)')], ...people.map((u) => ['u:' + u.id, (u.display_name || u.username) + ' · ' + roleOf(W.dir, u).name]),
    ...W.dir.roles.map((r) => ['r:' + r.id, t('Todo o cargo: {n}', { n: r.name })]), ...W.dir.functions.map((f) => ['f:' + f.id, t('Toda a função: {n}', { n: f.name })])], '', (v) => {
    if (!v) return;
    const [k, id] = [v[0], v.slice(2)];
    const list = k === 'u' ? S.to : k === 'r' ? S.roles : S.functions;
    if (!list.includes(id)) list.push(id);
    add.value = ''; paintTo();
  }, { id: 'wk-rq-add' });
  function paintTo() {
    const mk = (label, list, id) => h('span', { class: 'chip solid wk-rcpt' }, label, h('span', { class: 'x', onclick: () => { list.splice(list.indexOf(id), 1); paintTo(); } }, '×'));
    fill(chips, ...S.to.map((id) => mk(userName(W.dir, id), S.to, id)), ...S.roles.map((id) => mk(t('Cargo: {n}', { n: (W.dir.roles.find((r) => r.id === id) || {}).name }), S.roles, id)),
      ...S.functions.map((id) => mk(t('Função: {n}', { n: (W.dir.functions.find((f) => f.id === id) || {}).name }), S.functions, id)), !S.to.length && !S.roles.length && !S.functions.length ? h('span', { class: 'dim small' }, t('Ninguém escolhido ainda.')) : null);
  }
  function paintFiles() {
    fill(filesBox, ...S.files.map((f) => h('span', { class: 'chip solid' }, icon('clip', 12), f.name, h('span', { class: 'dim small' }, fmtSize(f.size)), h('span', { class: 'x', onclick: () => { S.files = S.files.filter((x) => x !== f); paintFiles(); } }, '×'))),
      S.uploading ? h('span', { class: 'dim small' }, h('span', { class: 'spinner' }), ' ' + t('Enviando {n} arquivo(s)…', { n: S.uploading })) : null);
  }
  const picker = h('input', { type: 'file', multiple: true, class: 'hidden', id: 'wk-rq-file' });
  picker.addEventListener('change', async () => {
    for (const f of [...picker.files]) {
      S.uploading++; paintFiles();
      try { S.files.push(await uploadFile(f)); } catch (e) { toast(f.name + ': ' + e.message, 'err'); }
      S.uploading--; paintFiles();
    }
    picker.value = '';
  });
  function paintChecklist() {
    fill(checkBox, S.checklist.length ? h('div', { class: 'card', style: { padding: '10px 12px' } }, h('b', { class: 'small' }, t('Checklist do pedido')), h('ul', { class: 'small', style: { margin: '6px 0 0', paddingLeft: '18px' } }, S.checklist.map((c, i) => h('li', null, c, ' ', h('a', { href: '#', onclick: (e) => { e.preventDefault(); S.checklist.splice(i, 1); paintChecklist(); } }, '×'))))) : null);
  }
  const team = teamPicker((state.settings && state.settings.work) || {}, null, { id: 'wk-rq' });
  const aiBtn = h('button', { class: 'btn', type: 'button', id: 'wk-rq-ai-btn', onclick: async () => {
    err.classList.add('hidden'); aiBtn.disabled = true; fill(notes, h('div', { class: 'spinner' }));
    try {
      const r = await api('/api/work/ai/request', { method: 'POST', body: { brief: body.value, to: S.to, attachments: S.files.map((f) => f.id), ...team.get() } });
      title.value = r.title; body.value = r.body; prio.value = r.priority; due.value = r.due || ''; S.checklist = r.checklist || [];
      if (!S.to.length && !S.roles.length && !S.functions.length) { S.to = r.recipients || []; paintTo(); }
      paintChecklist();
      fill(notes, r.warning ? h('div', { class: 'errbox', style: { whiteSpace: 'normal' } }, r.warning) : null, (r.issues || []).length ? h('div', { class: 'small muted' }, t('O Revisor ajustou:') + ' ' + r.issues.join('; ')) : null,
        (r.route || []).length ? h('div', { class: 'small dim' }, t('Caminho no fluxograma:') + ' ' + r.route.map((x) => x.label).join(' → ')) : null,
        h('div', { class: 'small dim' }, r.agents.map((a) => `${a.agent}: ${a.status === 'ok' ? 'IA' : t('regras')}`).join(' · ')));
    } catch (e) { fill(notes, h('div', { class: 'errbox' }, e.message)); }
    aiBtn.disabled = false;
  } }, icon('wand', 14), t('Rascunhar com IA'));
  let sending = false;
  const send = h('button', { class: 'btn primary', type: 'button', id: 'wk-rq-send', onclick: async () => {
    if (sending || S.uploading) return;
    err.classList.add('hidden'); sending = true; send.disabled = true;
    try {
      const r = await api('/api/work/requests', { method: 'POST', body: { to: S.to, to_roles: S.roles, to_functions: S.functions, title: title.value, body: body.value, priority: prio.value, due: due.value, attachments: S.files.map((f) => f.id), checklist: S.checklist } });
      toast(t('Pedido enviado.'), 'ok'); d.close(r);
    } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); sending = false; send.disabled = false; }
  } }, icon('send', 14), t('Enviar pedido'));
  const d = dialog(t('Enviar pedido'), h('div', { class: 'wk-form', id: 'wk-composer' },
    field(t('Para'), h('div', null, chips, add)), field(t('Título'), title),
    field(t('Texto do pedido'), body), h('div', { class: 'row', style: { gap: '8px', margin: '4px 0 10px' } }, h('button', { class: 'btn sm', type: 'button', id: 'wk-rq-attach', onclick: () => picker.click() }, icon('clip', 14), t('Anexar arquivos')), picker, filesBox),
    h('div', { class: 'grid2' }, field(t('Prioridade'), prio), field(t('Prazo'), due)), checkBox, notes, err,
    h('div', { class: 'row', style: { justifyContent: 'space-between', marginTop: '14px', flexWrap: 'wrap', gap: '8px' } }, W.can('ai.use') ? h('div', { class: 'row' }, team.el, aiBtn) : h('span'),
      h('div', { class: 'row' }, h('button', { class: 'btn', type: 'button', onclick: () => d.close(null) }, t('Cancelar')), send))), true);
  paintTo(); paintFiles(); paintChecklist();
  return d.done;
}
export { avatarEl };
