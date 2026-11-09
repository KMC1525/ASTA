import { api } from '../api.js';
import { t } from '../i18n.js';
import { go } from '../main.js';
import { avatarPic, REL_LABEL } from '../avatar_ui.js';
import { confirmDialog, debounce, fmtBytes, fmtDate, gradient, h, icon, modal, popover, tagsInput, toast } from '../ui.js';
import { GGUF_KINDS } from '../model_labels.js';
import { openChat } from './avatars.js';
import { mountCreator, resumeIfRunning } from './home.js';
import { GENRE_LABEL } from './steps.js';

const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const KIND_LABEL = { world: 'Mundos 3D', game2d: 'Jogos 2D', avatar: 'Avatars', canvas: 'Canvas', model: 'Modelos de IA locais' };
const MODEL_ICON = { text: 'type', image: 'image', video: 'video', sound: 'audio', voice: 'mic', other: 'file' };
const modelKindLabel = (k) => t((GGUF_KINDS.find(([x]) => x === k) || [0, k])[1]);
const hashGradient = (id) => { let n = 0; for (const c of String(id)) n = (n * 31 + c.charCodeAt(0)) >>> 0; return `linear-gradient(135deg, hsl(${n % 360},40%,22%), hsl(${(n + 60) % 360},45%,10%))`; };

export default (root, ctx) => renderLibrary(root, ctx, {});

// Biblioteca de tudo que você criou, mais os modelos de IA locais instalados. opts: { kinds: [...], title, subtitle, create: [label, fn], emptyTitle, emptyText }
export async function renderLibrary(root, ctx, opts) {
  if (opts.section && await resumeIfRunning(root, ctx, opts.section)) return;   // uma criação iniciada nesta seção: mostra o acompanhamento
  const creator = opts.createMode ? await mountCreator(root, { mode: opts.createMode, section: opts.section || '' }) : null;   // o mesmo compositor do Chat, aqui dentro
  const kinds = opts.kinds || ['world', 'game2d', 'avatar', 'canvas', 'model'];
  const fetchAll = () => Promise.all([
    kinds.some((k) => k === 'world' || k === 'game2d') ? api('/api/projects') : [], kinds.includes('avatar') ? api('/api/avatars') : [], kinds.includes('canvas') ? api('/api/canvases') : [],
    kinds.includes('model') ? api('/api/library/models').then((r) => r.models).catch(() => []) : []]);
  let items = [];
  const rebuild = ([pr, av, cv, md]) => {
    items = pr.filter((p) => kinds.includes(p.kind) && (!opts.filter || opts.filter(p))).map((p) => Object.assign({ itemKind: p.kind, tags: p.tags }, p))
      .concat(av.map((a) => ({ itemKind: 'avatar', id: a.id, name: a.name, description: a.personality || a.description || '', tags: { auto: a.tags, custom: [] }, updated: a.updated, raw: a })))
      .concat(cv.map((c) => ({ itemKind: 'canvas', id: c.id, name: c.name === 'Novo canvas' ? t('Novo canvas') : c.name, description: c.description || '', tags: { auto: [], custom: [] }, updated: c.updated, raw: c })));
    items.sort((a, b) => String(b.updated).localeCompare(String(a.updated)));
    // modelos locais ficam depois do que você criou, em ordem alfabética
    items = items.concat(md.slice().sort((a, b) => (a.label || a.name).localeCompare(b.label || b.name)).map((m) => ({ itemKind: 'model', id: m.id, name: m.label || m.name, description: m.label ? m.name : '', updated: '', raw: m,
      tags: { auto: [modelKindLabel(m.kind), m.quant].filter(Boolean).concat(m.preinstalled ? [t('pré-instalado')] : []), custom: [] } })));
  };
  rebuild(await fetchAll());
  const reload = async () => { rebuild(await fetchAll()); const ids = new Set(items.map((x) => selKey(x))); selected.forEach((k) => { if (!ids.has(k)) selected.delete(k); }); };
  let query = '', active = new Set(), typeFilter = 'all';
  const selected = new Set(); let selecting = false;   // seleção para apagar vários de uma vez
  const selKey = (p) => p.itemKind + ':' + p.id;
  const grid = h('div', { class: 'proj-grid' }), tagbar = h('div', { class: 'taglist' }), typebar = h('div', { class: 'taglist', style: { marginTop: '14px' } });
  const input = h('input', { type: 'search', placeholder: t('Buscar por nome, descrição ou tag…'), oninput: debounce((e) => { query = e.target.value; paint(); }, 120) });
  const allTags = (p) => p.tags.auto.concat(p.tags.custom);
  const matches = (p) => {
    if (typeFilter !== 'all' && p.itemKind !== typeFilter) return false;
    const hay = norm([p.name, p.description, allTags(p).join(' '), (p.last && p.last.prompt) || ''].join(' '));
    return norm(query).split(/\s+/).filter(Boolean).every((tok) => hay.includes(tok)) && [...active].every((tg) => allTags(p).includes(tg));
  };
  const endpoint = (p) => (p.itemKind === 'avatar' ? '/api/avatars/' : p.itemKind === 'canvas' ? '/api/canvases/' : '/api/projects/') + p.id;

  async function editTags(p) {
    let custom = p.tags.custom.slice(), auto = p.tags.auto.slice();
    const autoBox = h('div', { class: 'row', style: { gap: '6px' } });
    const paintAuto = () => autoBox.replaceChildren(...(auto.length ? auto.map((tg) => h('span', { class: 'chip' }, tg, h('span', { class: 'x', onclick: () => { auto = auto.filter((x) => x !== tg); paintAuto(); } }, '×'))) : [h('span', { class: 'muted small' }, t('nenhuma'))]));
    paintAuto();
    const body = h('div', null, h('label', { class: 'f' }, t('Tags automáticas (geradas pela IA)')), autoBox, h('label', { class: 'f', style: { marginTop: '16px' } }, t('Tags personalizadas')), tagsInput(custom, (v) => { custom = v; }));
    const ok = await modal(t('Tags de “{n}”', { n: p.name }), body, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]);
    if (ok !== 'ok') return;
    await api('/api/projects/' + p.id, { method: 'PUT', body: { tags_custom: custom, tags_auto: auto } }); await reload(); paint();
  }
  async function rename(p) {
    const inp = h('input', { value: p.name }); const v = await modal(t('Renomear'), inp, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]);
    if (v !== 'ok' || !inp.value.trim()) return;
    if (p.itemKind === 'avatar') await api('/api/avatars/' + p.id, { method: 'PUT', body: Object.assign({}, p.raw, { name: inp.value }) }); else await api(endpoint(p), { method: 'PUT', body: { name: inp.value } });
    await reload(); paint();
  }
  // apaga um ou vários itens (projetos, avatars, canvases e modelos locais); mostra o resultado e recarrega
  async function removeItems(list) {
    let ok = 0, failed = 0, freed = 0;
    const models = list.filter((p) => p.itemKind === 'model');
    if (models.length) {
      try { const r = await api('/api/library/models/delete', { method: 'POST', body: { items: models.map((m) => ({ kind: m.raw.kind, name: m.raw.name })) } }); ok += r.deleted.length; failed += r.missing.length; freed = r.freed; }
      catch (e) { failed += models.length; toast(e.message, 'err'); }
    }
    for (const p of list.filter((x) => x.itemKind !== 'model')) {
      try { await api(endpoint(p), { method: 'DELETE' }); ok++; } catch (e) { failed++; }
    }
    await reload();
    if (!selected.size) selecting = false;   // terminou de apagar a seleção: sai do modo de seleção
    paint();
    toast(t('{n} apagado(s)', { n: ok }) + (freed ? ' · ' + t('{n} liberados', { n: fmtBytes(freed) }) : '') + (failed ? ' · ' + t('{n} com erro', { n: failed }) : ''), failed ? 'err' : 'ok');
  }
  async function confirmRemove(list) {
    const models = list.filter((p) => p.itemKind === 'model'), pre = models.filter((m) => m.raw.preinstalled);
    const total = models.reduce((a, m) => a + (m.raw.size || 0), 0);
    let msg = list.length === 1 ? (models.length ? t('Apagar o modelo “{n}” do computador? Ele pode ser baixado de novo depois.', { n: list[0].name }) : t('Apagar “{n}” e todo o seu conteúdo? Isso não pode ser desfeito.', { n: list[0].name }))
      : t('Apagar {n} itens? Isso não pode ser desfeito.', { n: list.length });
    if (models.length && list.length > 1) msg += ' ' + t('{n} modelos de IA ({s}) serão removidos do computador.', { n: models.length, s: fmtBytes(total) });
    if (pre.length) msg += ' ' + t('Os arquivos de apoio dos modelos pré-instalados (VAE, codificador de texto) também são apagados.');
    if (await confirmDialog(msg)) await removeItems(list);
  }
  function menu(anchor, p) {
    const item = (label, ic, fn, cls) => h('div', { class: 'opt ' + (cls || ''), onclick: () => { pop.close(); fn(); } }, icon(ic, 15), label);
    const list = [];
    if (p.itemKind === 'model') list.push(item(t('Selecionar vários'), 'check', () => { selecting = true; selected.add(selKey(p)); paint(); }), item(t('Apagar modelo'), 'trash', () => confirmRemove([p]), 'danger'));
    else {
      list.push(item(t('Selecionar vários'), 'check', () => { selecting = true; selected.add(selKey(p)); paint(); }));
      if (p.itemKind === 'world' || p.itemKind === 'game2d') list.push(item(t('Editar tags'), 'tag', () => editTags(p)));
      list.push(item(t('Renomear'), 'edit', () => rename(p)));
      if (p.itemKind === 'world' || p.itemKind === 'game2d') list.push(item(t('Reconstruir com o motor mais recente'), 'refresh', async () => { try { await api('/api/projects/' + p.id + '/rebuild', { method: 'POST' }); toast(t('Nova versão criada com o motor atual'), 'ok'); await reload(); paint(); } catch (e) { toast(e.message, 'err'); } }));
      if (p.itemKind === 'canvas') list.push(item(t('Duplicar'), 'copy', async () => { await api('/api/canvases/' + p.id + '/duplicate', { method: 'POST' }); toast(t('Duplicado')); await reload(); paint(); }));
      list.push(item(t('Apagar'), 'trash', () => confirmRemove([p]), 'danger'));
    }
    const pop = popover(anchor, h('div', null, list));
  }

  function modelCard(p) {
    const m = p.raw, pick = selecting ? selectBox(p) : null;
    return h('div', { class: 'proj model' + (selected.has(selKey(p)) ? ' picked' : ''), id: 'p-' + p.id, onclick: selecting ? () => toggle(p) : null },
      h('div', { class: 'thumb', style: { background: hashGradient(p.id), display: 'grid', placeItems: 'center' } }, icon(MODEL_ICON[m.kind] || 'file', 34), pick, h('span', { class: 'badge vb' }, t(KIND_LABEL.model) + ' · ' + modelKindLabel(m.kind))),
      h('div', { class: 'bd' }, h('div', { class: 'nm', title: p.name }, p.name), h('div', { class: 'ds mono', style: { fontSize: '12px' } }, p.description || ''),
        h('div', { class: 'row', style: { gap: '5px' } }, allTags(p).map((tg) => h('span', { class: 'chip' }, tg))),
        h('div', { class: 'dim small', style: { marginTop: 'auto' } }, fmtBytes(m.size) + (m.parts > 1 ? ' · ' + t('{n} partes', { n: m.parts }) : '') + (m.extra_files && m.extra_files.length ? ' · ' + t('+ {n} arquivos de apoio', { n: m.extra_files.length }) : ''))),
      h('div', { class: 'ft' }, h('span', { class: 'grow' }), selecting ? null : h('button', { class: 'btn sm ghost danger', title: t('Apagar modelo'), onclick: (e) => { e.stopPropagation(); confirmRemove([p]); } }, icon('trash', 13), t('Apagar')), selecting ? null : h('button', { class: 'btn ghost icon sm', title: t('Mais'), onclick: (e) => menu(e.currentTarget, p) }, icon('more', 16))));
  }
  const toggle = (p) => { const k = selKey(p); selected.has(k) ? selected.delete(k) : selected.add(k); paint(); };
  const selectBox = (p) => h('input', { type: 'checkbox', class: 'pick', checked: selected.has(selKey(p)), title: t('Selecionar'), onclick: (e) => e.stopPropagation(), onchange: () => toggle(p) });

  function card(p) {
    if (p.itemKind === 'model') return modelCard(p);
    const more = h('button', { class: 'btn ghost icon sm', title: t('Mais'), onclick: (e) => menu(e.currentTarget, p) }, icon('more', 16));
    const k = p.itemKind;
    const thumb = k === 'avatar' ? h('div', { class: 'thumb', style: { background: hashGradient(p.id), display: 'grid', placeItems: 'center' } }, avatarPic(p.raw, 78), h('span', { class: 'badge vb' }, t(KIND_LABEL[k])))
      : k === 'canvas' ? h('div', { class: 'thumb', style: { backgroundImage: p.raw.thumb ? 'url(' + p.raw.thumb + ')' : hashGradient(p.id), backgroundSize: 'cover', backgroundPosition: 'center' } }, h('span', { class: 'badge vb' }, t(KIND_LABEL[k]) + ' · ' + p.raw.nodes + ' ' + t('nós')))
        : h('div', { class: 'thumb', style: { background: gradient(p.palette) } }, h('span', { class: 'badge vb' }, (k === 'game2d' ? (GENRE_LABEL[p.genre] || t(KIND_LABEL[k])) + ' · ' : '') + 'v' + p.current));
    const foot = k === 'avatar' ? [h('button', { class: 'btn sm primary', onclick: () => openChat([p.id]) }, icon('send', 13), t('Conversar')), h('a', { class: 'btn sm', href: '#/avatars/edit/' + p.id }, icon('edit', 13), t('Editar'))]
      : k === 'canvas' ? [h('a', { class: 'btn sm primary', href: '#/canvas/edit/' + p.id }, icon('canvas', 13), t('Abrir'))]
        : [h('a', { class: 'btn sm primary', href: '/play/' + p.id + '/', target: '_blank', rel: 'noopener' }, icon('play', 13), t('Jogar')),
          h('button', { class: 'btn sm', title: t('Atualizar com IA — o mesmo jogo, várias vezes'), onclick: () => (creator && !opts.noUpdate ? creator.setProject({ id: p.id, name: p.name, current: p.current, kind: k }) : go('main', { project: { id: p.id, name: p.name, current: p.current, kind: k } })) }, icon('refresh', 13), t('Atualizar com IA')),
          k === 'world' ? h('button', { class: 'btn sm ghost', title: t('Configurar mundo'), onclick: () => go('worlds', { select: p.id }) }, icon('edit', 13)) : null,
          h('a', { class: 'btn sm ghost', title: t('Baixar ZIP'), href: '/api/projects/' + p.id + '/download' }, icon('download', 13))];
    if (selecting) thumb.append(selectBox(p));
    return h('div', { class: 'proj' + (selected.has(selKey(p)) ? ' picked' : ''), id: 'p-' + p.id, onclick: selecting ? () => toggle(p) : null },
      thumb,
      h('div', { class: 'bd' }, h('div', { class: 'nm', title: p.name }, p.name), h('div', { class: 'ds' }, p.description || ''),
        h('div', { class: 'row', style: { gap: '5px' } }, allTags(p).slice(0, 5).map((tg) => h('button', { class: 'chip' + (active.has(tg) ? ' on' : ''), onclick: () => { active.has(tg) ? active.delete(tg) : active.add(tg); paint(); } }, tg))),
        h('div', { class: 'dim small', style: { marginTop: 'auto' } }, fmtDate(p.updated) + (p.versions > 1 ? ' · ' + t('{n} versões', { n: p.versions }) : ''))),
      h('div', { class: 'ft', style: selecting ? { pointerEvents: 'none', opacity: .5 } : null }, ...foot, h('span', { class: 'grow' }), more));
  }

  const bar = h('div', { class: 'selbar' });
  function paintBar(shown) {
    if (!selecting) { bar.replaceChildren(); bar.style.display = 'none'; return; }
    bar.style.display = '';
    const n = selected.size, visible = shown.map(selKey), allOn = visible.length && visible.every((k) => selected.has(k));
    bar.replaceChildren(h('b', null, n ? t('{n} selecionado(s)', { n }) : t('Escolha os itens que quer apagar')),
      h('button', { class: 'btn sm', onclick: () => { visible.forEach((k) => (allOn ? selected.delete(k) : selected.add(k))); paint(); } }, allOn ? t('Desmarcar os exibidos') : t('Selecionar os exibidos')),
      h('span', { class: 'grow' }),
      h('button', { class: 'btn sm danger', disabled: !n, onclick: () => confirmRemove(items.filter((p) => selected.has(selKey(p)))) }, icon('trash', 13), t('Apagar selecionados')),
      h('button', { class: 'btn sm ghost', onclick: () => { selecting = false; selected.clear(); paint(); } }, t('Cancelar')));
  }
  const selectBtn = h('button', { class: 'btn sm', onclick: () => { selecting = !selecting; if (!selecting) selected.clear(); paint(); } }, icon('check', 13), t('Selecionar'));

  function paint() {
    const counts = {};
    items.forEach((p) => allTags(p).forEach((tg) => (counts[tg] = (counts[tg] || 0) + 1)));
    const top = Object.keys(counts).sort((a, b) => counts[b] - counts[a]).slice(0, 18);
    active.forEach((tg) => { if (!top.includes(tg)) top.unshift(tg); });
    tagbar.replaceChildren(...top.map((tg) => h('button', { class: 'chip' + (active.has(tg) ? ' on' : ''), onclick: () => { active.has(tg) ? active.delete(tg) : active.add(tg); paint(); } }, tg, h('span', { class: 'dim' }, counts[tg] || ''))));
    if (kinds.length > 1) typebar.replaceChildren(...[['all', t('Tudo')]].concat(kinds.map((k) => [k, t(KIND_LABEL[k])])).map(([k, l]) => h('button', { class: 'chip' + (typeFilter === k ? ' on' : ''), onclick: () => { typeFilter = k; paint(); } }, l, h('span', { class: 'dim' }, k === 'all' ? items.length : items.filter((x) => x.itemKind === k).length))));
    const shown = items.filter(matches);
    selectBtn.classList.toggle('primary', selecting); selectBtn.style.display = items.length ? '' : 'none';
    paintBar(shown);
    grid.replaceChildren(...(shown.length ? shown.map(card) : [h('div', { class: 'empty', style: { gridColumn: '1/-1' } },
      items.length ? [h('h3', null, t('Nada encontrado')), h('p', null, t('Tente outra busca ou remova filtros de tags.'))] :
        [h('h3', null, opts.emptyTitle || t('Sua biblioteca está vazia')), h('p', null, opts.emptyText || t('Tudo que você cria no ASTA — mundos 3D, avatars, jogos 2D e canvases — fica salvo aqui e dá para atualizar quantas vezes quiser.')),
          h('button', { class: 'btn primary', onclick: () => (creator ? creator.focus() : go('main', { fresh: true, mode: opts.createMode })) }, icon('sparkle', 15), opts.createLabel || t('Criar o primeiro'))])]));
  }

  root.replaceChildren(h('div', { class: 'page' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, opts.title || t('Biblioteca')), h('p', null, opts.subtitle || t('Tudo que você criou e os modelos de IA locais instalados.'))),
      opts.createMode ? h('button', { class: 'btn primary', onclick: () => (creator ? creator.setProject(null) : go('main', { fresh: true, mode: opts.createMode })) }, icon('plus', 15), opts.createLabel || t('Novo')) : null),
    creator ? creator.el : null,
    h('div', { class: 'row' }, h('div', { class: 'search' }, icon('search', 17), input), selectBtn, h('span', { class: 'dim small' }, t('{n} item(ns)', { n: items.length }))),
    bar,
    typebar, tagbar, grid));
  paint();
  if (ctx.highlight) { const el = document.getElementById('p-' + ctx.highlight); if (el) { el.scrollIntoView({ block: 'center' }); el.style.borderColor = '#fff'; setTimeout(() => (el.style.borderColor = ''), 1800); } }
}
