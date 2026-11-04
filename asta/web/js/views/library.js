import { api } from '../api.js';
import { t } from '../i18n.js';
import { go } from '../main.js';
import { confirmDialog, debounce, fmtDate, gradient, h, icon, modal, popover, tagsInput, toast } from '../ui.js';

const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export default async function render(root, ctx) {
  let projects = await api('/api/projects');
  let query = '', active = new Set();
  const grid = h('div', { class: 'proj-grid' }), tagbar = h('div', { class: 'taglist' });
  const input = h('input', { type: 'search', placeholder: t('Buscar por nome, descrição ou tag…'), oninput: debounce((e) => { query = e.target.value; paint(); }, 120) });

  const allTags = (p) => p.tags.auto.concat(p.tags.custom);
  const matches = (p) => {
    const hay = norm([p.name, p.description, allTags(p).join(' '), (p.last && p.last.prompt) || ''].join(' '));
    return norm(query).split(/\s+/).filter(Boolean).every((tok) => hay.includes(tok)) && [...active].every((tg) => allTags(p).includes(tg));
  };

  async function editTags(p) {
    let custom = p.tags.custom.slice(), auto = p.tags.auto.slice();
    const autoBox = h('div', { class: 'row', style: { gap: '6px' } });
    const paintAuto = () => autoBox.replaceChildren(...(auto.length ? auto.map((tg) => h('span', { class: 'chip' }, tg, h('span', { class: 'x', onclick: () => { auto = auto.filter((x) => x !== tg); paintAuto(); } }, '×'))) : [h('span', { class: 'muted small' }, t('nenhuma'))]));
    paintAuto();
    const body = h('div', null, h('label', { class: 'f' }, t('Tags automáticas (geradas pela IA)')), autoBox,
      h('label', { class: 'f', style: { marginTop: '16px' } }, t('Tags personalizadas')), tagsInput(custom, (v) => { custom = v; }));
    const ok = await modal(t('Tags de “{n}”', { n: p.name }), body, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]);
    if (ok !== 'ok') return;
    await api('/api/projects/' + p.id, { method: 'PUT', body: { tags_custom: custom, tags_auto: auto } });
    projects = await api('/api/projects'); paint();
  }

  function menu(anchor, p) {
    const item = (label, ic, fn, cls) => h('div', { class: 'opt ' + (cls || ''), onclick: () => { pop.close(); fn(); } }, icon(ic, 15), label);
    const pop = popover(anchor, h('div', null,
      item(t('Editar tags'), 'tag', () => editTags(p)),
      item(t('Renomear'), 'edit', async () => { const inp = h('input', { value: p.name }); const v = await modal(t('Renomear'), inp, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]); if (v === 'ok' && inp.value.trim()) { await api('/api/projects/' + p.id, { method: 'PUT', body: { name: inp.value } }); projects = await api('/api/projects'); paint(); } }),
      item(t('Reconstruir com o motor mais recente'), 'refresh', async () => { try { await api('/api/projects/' + p.id + '/rebuild', { method: 'POST' }); toast(t('Nova versão criada com o motor atual'), 'ok'); projects = await api('/api/projects'); paint(); } catch (e) { toast(e.message, 'err'); } }),
      item(t('Apagar'), 'trash', async () => { if (await confirmDialog(t('Apagar “{n}” e todas as suas versões? Isso não pode ser desfeito.', { n: p.name }))) { await api('/api/projects/' + p.id, { method: 'DELETE' }); projects = projects.filter((x) => x.id !== p.id); paint(); toast(t('Apagado')); } }, 'danger')));
  }

  function card(p) {
    const more = h('button', { class: 'btn ghost icon sm', title: t('Mais'), onclick: (e) => menu(e.currentTarget, p) }, icon('more', 16));
    return h('div', { class: 'proj', id: 'p-' + p.id },
      h('div', { class: 'thumb', style: { background: gradient(p.palette) } }, h('span', { class: 'badge vb' }, 'v' + p.current)),
      h('div', { class: 'bd' }, h('div', { class: 'nm', title: p.name }, p.name), h('div', { class: 'ds' }, p.description || ''),
        h('div', { class: 'row', style: { gap: '5px' } }, allTags(p).slice(0, 5).map((tg) => h('button', { class: 'chip' + (active.has(tg) ? ' on' : ''), onclick: () => { active.has(tg) ? active.delete(tg) : active.add(tg); paint(); } }, tg))),
        h('div', { class: 'dim small', style: { marginTop: 'auto' } }, fmtDate(p.updated) + (p.versions > 1 ? ' · ' + t('{n} versões', { n: p.versions }) : ''))),
      h('div', { class: 'ft' },
        h('a', { class: 'btn sm primary', href: '/play/' + p.id + '/', target: '_blank', rel: 'noopener' }, icon('play', 13), t('Jogar')),
        h('button', { class: 'btn sm', title: t('Atualizar com IA — o mesmo jogo, várias vezes'), onclick: () => go('main', { project: { id: p.id, name: p.name, current: p.current } }) }, icon('refresh', 13), t('Atualizar')),
        h('button', { class: 'btn sm ghost', title: t('Configurar mundo'), onclick: () => go('worlds', { select: p.id }) }, icon('edit', 13)),
        h('a', { class: 'btn sm ghost', title: t('Baixar ZIP'), href: '/api/projects/' + p.id + '/download' }, icon('download', 13)), h('span', { class: 'grow' }), more));
  }

  function paint() {
    const counts = {};
    projects.forEach((p) => allTags(p).forEach((tg) => (counts[tg] = (counts[tg] || 0) + 1)));
    const top = Object.keys(counts).sort((a, b) => counts[b] - counts[a]).slice(0, 18);
    active.forEach((tg) => { if (!top.includes(tg)) top.unshift(tg); });
    tagbar.replaceChildren(...top.map((tg) => h('button', { class: 'chip' + (active.has(tg) ? ' on' : ''), onclick: () => { active.has(tg) ? active.delete(tg) : active.add(tg); paint(); } }, tg, h('span', { class: 'dim' }, counts[tg] || ''))));
    const shown = projects.filter(matches);
    grid.replaceChildren(...(shown.length ? shown.map(card) : [h('div', { class: 'empty', style: { gridColumn: '1/-1' } },
      projects.length ? [h('h3', null, t('Nada encontrado')), h('p', null, t('Tente outra busca ou remova filtros de tags.'))] :
        [h('h3', null, t('Sua biblioteca está vazia')), h('p', null, t('Cada mundo gerado é salvo aqui como um projeto — dá para atualizar o mesmo jogo várias vezes.')), h('button', { class: 'btn primary', onclick: () => go('main', { fresh: true }) }, icon('sparkle', 15), t('Criar o primeiro mundo'))])]));
  }

  root.replaceChildren(h('div', { class: 'page' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, t('Biblioteca')), h('p', null, t('Todos os mundos gerados, salvos como projetos atualizáveis.')))),
    h('div', { class: 'row' }, h('div', { class: 'search' }, icon('search', 17), input), h('span', { class: 'dim small' }, t('{n} projeto(s)', { n: projects.length }))),
    tagbar, grid));
  paint();
  if (ctx.highlight) { const el = document.getElementById('p-' + ctx.highlight); if (el) { el.scrollIntoView({ block: 'center' }); el.style.borderColor = '#fff'; setTimeout(() => (el.style.borderColor = ''), 1800); } }
}
