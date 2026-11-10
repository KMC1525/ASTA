// Work → Início: o que precisa da sua atenção agora (pedidos, atividades em andamento, quem está online).
import { api, avatarEl, chip, fmtAgo, h, icon, PRIORITY, prioTone, REQ_STATUS, roleOf, statusTone, t, userName } from '../work_ui.js';
import { fill } from '../ui.js';

export default async function render(box, W) {
  const tiles = h('div', { class: 'wk-tiles' });
  const left = h('div', { class: 'wk-col' });
  const right = h('div', { class: 'wk-col' });
  box.replaceChildren(tiles, h('div', { class: 'wk-two' }, left, right));

  async function paint() {
    const [reqs, acts, notes] = await Promise.all([api('/api/work/requests?box=in'), api('/api/work/activities?user=' + W.me.user.id + '&auto=0&limit=60'), api('/api/work/notifications?unread=1')]);
    const open = reqs.requests.filter((r) => ['sent', 'seen', 'accepted', 'in_progress'].includes(r.status));
    const running = acts.activities.filter((a) => ['started', 'continuing', 'paused'].includes(a.state));
    const online = W.dir.users.filter((u) => u.online && !u.disabled);
    const tile = (n, label, ic, tab) => h('a', { class: 'wk-tile', href: '#/work/' + tab }, icon(ic, 20), h('b', null, String(n)), h('span', null, label));
    fill(tiles, tile(open.length, t('Pedidos abertos para você'), 'send', 'requests'), tile(notes.unread, t('Avisos não lidos'), 'bell', 'home'), tile(running.length, t('Suas atividades em andamento'), 'bolt', 'activities'), tile(online.length, t('Pessoas online agora'), 'characters', 'people'));
    fill(left,
      h('div', { class: 'card' }, h('h3', null, t('Pedidos para você')),
        open.length ? h('div', { class: 'wk-list' }, open.slice(0, 6).map((r) => h('a', { class: 'wk-li', href: '#/work/requests/' + r.id },
          h('span', { class: 'grow' }, h('b', null, r.title), h('span', { class: 'small dim' }, t('de {n}', { n: userName(W.dir, r.from) }) + ' · ' + fmtAgo(r.updated))),
          r.priority !== 'normal' ? chip(PRIORITY()[r.priority], prioTone(r.priority)) : null, chip(REQ_STATUS()[r.status], statusTone(r.status))))) : h('p', { class: 'dim small' }, t('Nenhum pedido aberto. Quando alguém enviar, aparece aqui na hora.'))),
      h('div', { class: 'card' }, h('h3', null, t('Suas atividades')),
        running.length ? h('div', { class: 'wk-list' }, running.slice(0, 6).map((a) => h('a', { class: 'wk-li', href: '#/work/activities' }, h('span', { class: 'grow' }, h('b', null, a.title)), chip(t(a.state === 'paused' ? 'Pausada' : 'Em andamento'), a.state === 'paused' ? 'warn' : 'info')))) : h('p', { class: 'dim small' }, t('Nada em andamento. Registre o que está começando na aba Atividades.'))));
    fill(right,
      h('div', { class: 'card' }, h('h3', null, t('Quem está online')),
        online.length ? h('div', { class: 'wk-list' }, online.map((u) => h('a', { class: 'wk-li', href: '#/work/people/' + u.id }, avatarEl(u, 30), h('span', { class: 'grow' }, h('b', null, u.display_name || u.username), h('span', { class: 'small dim' }, roleOf(W.dir, u).name + (u.title ? ' · ' + u.title : ''))), u.busy ? chip(t('{n} em andamento', { n: u.busy }), 'info') : null))) : h('p', { class: 'dim small' }, t('Ninguém online.'))),
      W.can('flow.view') ? h('div', { class: 'card' }, h('h3', null, t('Atalhos')), h('div', { class: 'row', style: { flexWrap: 'wrap', gap: '8px' } },
        W.can('requests.send') ? h('a', { class: 'btn sm', href: '#/work/requests/new', id: 'wk-home-new' }, icon('plus', 13), t('Novo pedido')) : null,
        h('a', { class: 'btn sm', href: '#/work/board' }, icon('network', 13), t('Abrir o quadro')), h('a', { class: 'btn sm', href: '#/work/files' }, icon('folder', 13), t('Arquivos')))) : null);
  }
  await paint();
  W.live(['requests', 'activities', 'notifications', 'presence', 'users'], paint);
}
