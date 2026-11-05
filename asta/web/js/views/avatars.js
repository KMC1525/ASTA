import { api } from '../api.js';
import { t } from '../i18n.js';
import { go } from '../main.js';
import { confirmDialog, download, fill, h, icon, popover, toast } from '../ui.js';
import { avatarPic, MOOD_EMOJI, REL_LABEL } from '../avatar_ui.js';

// Sub-rotas: #/avatars (lista) · #/avatars/chat/<id> · #/avatars/edit/<id|new>
export function subRoute() {
  const m = location.hash.match(/^#\/avatars\/(chat|edit)\/([\w-]+)/);
  return m ? { mode: m[1], id: m[2] } : { mode: 'list', id: '' };
}
export const openChat = async (ids) => {
  const c = await api('/api/avatar-chats', { method: 'POST', body: { avatar_ids: ids, reuse: ids.length === 1 } });
  location.hash = '#/avatars/chat/' + c.id;
};

export default async function render(root, ctx) {
  const sub = subRoute();
  if (sub.mode === 'chat') return (await import('./avatar_chat.js')).default(root, ctx, sub.id);
  if (sub.mode === 'edit') return (await import('./avatar_edit.js')).default(root, ctx, sub.id);
  return renderList(root, ctx);
}

async function renderList(root, ctx) {
  let [list, chats] = await Promise.all([api('/api/avatars'), api('/api/avatar-chats')]);
  const sel = new Set();
  const grid = h('div', { class: 'av-grid' }), bar = h('div', { class: 'selbar hidden' }), chatBox = h('div', { class: 'col' });
  const byId = () => Object.fromEntries(list.map((a) => [a.id, a]));

  const importInput = h('input', { type: 'file', accept: '.json,.png,application/json,image/png', class: 'hidden', onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { const c = await api('/api/avatars/import', { method: 'POST', body: f, raw: true, headers: { 'Content-Type': f.type || 'application/octet-stream' } }); toast(t('Importado'), 'ok'); location.hash = '#/avatars/edit/' + c.id; }
    catch (er) { toast(er.message, 'err'); }
    e.target.value = '';
  } });

  const paintBar = () => {
    bar.classList.toggle('hidden', !sel.size);
    fill(bar, h('span', null, t('{n} selecionado(s)', { n: sel.size })), h('span', { class: 'grow' }),
      sel.size === 1 ? h('button', { class: 'btn primary', onclick: () => openChat([...sel]) }, icon('send', 14), t('Conversar')) : null,
      sel.size > 1 ? h('button', { class: 'btn primary', title: t('Os avatares conversam entre si de forma natural'), onclick: () => openChat([...sel]) }, icon('characters', 14), t('Conversa em grupo')) : null,
      h('button', { class: 'btn ghost', onclick: () => { sel.clear(); paint(); } }, t('Limpar')));
  };

  function menu(anchor, a) {
    const item = (label, ic, fn, cls) => h('div', { class: 'opt ' + (cls || ''), onclick: () => { pop.close(); fn(); } }, icon(ic, 15), label);
    const pop = popover(anchor, h('div', null,
      item(t('Exportar (ASTA)'), 'download', () => download((a.name || 'avatar').replace(/\W+/g, '-') + '.json', JSON.stringify(a, null, 2))),
      item(t('Exportar (Character Card V2)'), 'download', async () => { const v2 = await api('/api/avatars/' + a.id + '/export?format=card_v2'); download((a.name || 'avatar').replace(/\W+/g, '-') + '.card.json', JSON.stringify(v2, null, 2)); }),
      item(t('Duplicar'), 'copy', async () => { const c = await api('/api/avatars', { method: 'POST', body: Object.assign({}, a, { id: undefined, portrait: '', name: a.name + ' (2)' }) }); toast(t('Duplicado')); list = await api('/api/avatars'); paint(); location.hash = '#/avatars/edit/' + c.id; }),
      item(t('Apagar'), 'trash', async () => {
        if (!(await confirmDialog(t('Apagar o avatar “{n}”? Memórias e retrato também serão apagados.', { n: a.name })))) return;
        await api('/api/avatars/' + a.id, { method: 'DELETE' }); sel.delete(a.id); list = await api('/api/avatars'); chats = await api('/api/avatar-chats'); paint(); toast(t('Apagado'));
      }, 'danger')));
  }

  function card(a) {
    const on = sel.has(a.id);
    return h('div', { class: 'av-card' + (on ? ' on' : '') },
      h('label', { class: 'av-sel', title: t('Selecionar para conversa em grupo') }, h('input', { type: 'checkbox', checked: on, onchange: (e) => { if (e.target.checked && sel.size >= 8) { e.target.checked = false; return toast(t('No máximo 8 avatares por conversa.'), 'err'); } e.target.checked ? sel.add(a.id) : sel.delete(a.id); paint(); } })),
      h('div', { class: 'av-pic', onclick: () => openChat([a.id]) }, avatarPic(a, 88)),
      h('div', { class: 'av-info' },
        h('div', { class: 'av-name', title: a.name }, a.name),
        h('div', { class: 'row', style: { gap: '5px', justifyContent: 'center' } },
          h('span', { class: 'chip' }, t(REL_LABEL[a.relationship] || REL_LABEL.custom)),
          h('span', { class: 'chip ' + (a.content === 'nsfw' ? 'nsfw' : 'solid') }, a.content === 'nsfw' ? 'NSFW' : 'SFW')),
        h('div', { class: 'av-desc' }, a.personality || a.description || '')),
      h('div', { class: 'row nw', style: { gap: '6px', justifyContent: 'center', marginTop: 'auto' } },
        h('button', { class: 'btn sm primary', onclick: () => openChat([a.id]) }, icon('send', 13), t('Conversar')),
        h('button', { class: 'btn sm', onclick: () => { location.hash = '#/avatars/edit/' + a.id; } }, icon('edit', 13), t('Editar')),
        h('button', { class: 'btn sm ghost icon', title: t('Mais'), onclick: (e) => menu(e.currentTarget, a) }, icon('more', 15))));
  }

  function chatRow(c) {
    const people = byId();
    const names = c.avatar_ids.map((i) => (people[i] || {}).name).filter(Boolean);
    return h('div', { class: 'li', onclick: () => { location.hash = '#/avatars/chat/' + c.id; } },
      h('div', { class: 'av' }, icon(c.mode === 'multi' ? 'characters' : 'send', 15)),
      h('div', { style: { minWidth: 0 }, class: 'grow' }, h('div', { class: 't' }, c.title || names.join(', ')),
        h('div', { class: 's' }, c.last ? c.last.name + ': ' + c.last.text : t('Sem mensagens'))),
      h('span', { class: 'badge' }, c.mode === 'multi' ? t('grupo') : t('single')),
      h('button', { class: 'btn ghost icon sm danger', title: t('Apagar'), onclick: async (e) => { e.stopPropagation(); if (await confirmDialog(t('Apagar esta conversa?'))) { await api('/api/avatar-chats/' + c.id, { method: 'DELETE' }); chats = await api('/api/avatar-chats'); paint(); } } }, icon('trash', 14)));
  }

  function paint() {
    paintBar();
    grid.replaceChildren(...(list.length ? list.map(card) : [h('div', { class: 'empty', style: { gridColumn: '1/-1' } },
      h('h3', null, t('Crie seu primeiro avatar')),
      h('p', null, t('Amigos, namorados(as), companheiros e mentores com quem conversar por texto e voz. Crie com IA a partir de texto, imagens ou qualquer arquivo — um de cada vez ou vários juntos.')),
      h('div', { class: 'row', style: { justifyContent: 'center' } }, h('button', { class: 'btn primary', onclick: () => go('main', { mode: 'avatar' }) }, icon('sparkle', 15), t('Criar com IA')),
        h('button', { class: 'btn', onclick: () => { location.hash = '#/avatars/edit/new'; } }, icon('plus', 15), t('Novo avatar'))))]));
    chatBox.replaceChildren(...(chats.length ? chats.map(chatRow) : [h('div', { class: 'muted small' }, t('Nenhuma conversa ainda. Escolha um avatar e clique em Conversar.'))]));
  }

  root.replaceChildren(h('div', { class: 'page' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'Avatars'), h('p', null, t('Companheiros de conversa por texto e voz: um avatar ou vários conversando entre si.'))),
      h('div', { class: 'row' }, h('button', { class: 'btn', onclick: () => go('main', { mode: 'avatar' }) }, icon('sparkle', 15), t('Criar com IA')),
        h('button', { class: 'btn', onclick: () => importInput.click() }, icon('upload', 15), t('Importar')), importInput,
        h('button', { class: 'btn primary', onclick: () => { location.hash = '#/avatars/edit/new'; } }, icon('plus', 15), t('Novo')))),
    bar, grid,
    h('div', { class: 'card', style: { marginTop: '26px' } }, h('h3', null, t('Conversas')), chatBox)));
  paint();
}
