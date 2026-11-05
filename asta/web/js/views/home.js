import { api } from '../api.js';
import { getLang, t } from '../i18n.js';
import { go, presetOf, state } from '../main.js';
import { avatarPic, REL_LABEL } from '../avatar_ui.js';
import { gradient, h, icon, popover, select, seg, toast } from '../ui.js';
import { openChat } from './avatars.js';
import { createComposer } from './composer.js';
import { clearJob, renderRun, saveJob, savedJob } from './run.js';
import { GENRE_LABEL } from './steps.js';

const toast0 = (msg) => toast(msg, 'err');
const MODES = [['world', 'Mundo 3D', 'worlds'], ['avatar', 'Avatar', 'avatars'], ['game', 'Jogo 2D', 'games'], ['canvas', 'Canvas', 'canvas']];
const TITLES = { world: ['O que vamos criar?', 'O que vamos mudar?'], avatar: ['Quem vamos criar?', ''], game: ['Que jogo vamos criar?', 'O que vamos mudar neste jogo?'], canvas: ['O que vamos produzir?', ''] };
const HINTS = () => {
  const pt = getLang() === 'pt';
  return {
    world: pt ? ['Uma vila medieval numa floresta ao anoitecer, com chuva leve e uma taverna acolhedora', 'Um acampamento no deserto com ruínas antigas e uma arqueóloga curiosa', 'Uma cidade cyberpunk à noite, com neblina e ruas movimentadas']
      : ['A medieval village in a forest at dusk, with light rain and a cozy tavern', 'A desert camp with ancient ruins and a curious archaeologist', 'A cyberpunk city at night, with fog and busy streets'],
    avatar: pt ? ['Uma amiga divertida e carinhosa chamada Luna, que adora astronomia', 'Três amigos de faculdade: Theo, Mia e Caio', 'Um mentor sábio e paciente chamado Davi, que me ajuda com a carreira']
      : ['A funny, caring friend named Luna who loves astronomy', 'Three college friends: Theo, Mia and Caio', 'A wise, patient mentor named Davi who helps me with my career'],
    game: pt ? ['Uma visual novel romântica num café, com escolhas e três finais', 'Um RPG de aventura: uma vila, uma floresta e um dragão numa masmorra', 'Um jogo de plataforma numa floresta encantada, com moedas e inimigos', 'Um shooter espacial com chefes', 'Um escape room point & click numa casa trancada']
      : ['A romantic visual novel in a café, with choices and three endings', 'An adventure RPG: a village, a forest and a dragon in a dungeon', 'A platformer in an enchanted forest, with coins and enemies', 'A space shooter with bosses', 'A point & click escape room in a locked house'],
    canvas: [],
  };
};

export default async function render(root, ctx) {
  if (ctx.fresh) clearJob();
  const saved = savedJob();
  if (saved && !ctx.project) {
    try { const j = await api('/api/jobs/' + saved.id); if (j) return resume(root, saved); } catch (e) { clearJob(); }
  }
  return renderHub(root, ctx);
}

// ------------------------------------------------------------------ hub (central de criação)
async function renderHub(root, ctx) {
  const updating = ctx.project || null;
  let mode = ctx.mode || (updating ? (updating.kind === 'game2d' ? 'game' : 'world') : localStorage.getItem('asta.mode') || 'world');
  if (!MODES.some((m) => m[0] === mode)) mode = 'world';
  const body = h('div'), titleEl = h('h1'), sugEl = h('div', { class: 'suggest' }), bar = h('div', { class: 'modes' });
  const demo = state.settings.active.generation === 'demo';
  let carry = ctx.prompt || '';

  const paintBar = () => bar.replaceChildren(...MODES.map(([id, label, ic]) => h('button', { class: 'mode' + (id === mode ? ' on' : ''), type: 'button', onclick: () => { carry = body.querySelector('textarea') ? body.querySelector('textarea').value : carry; mode = id; localStorage.setItem('asta.mode', id); paint(); } }, icon(ic, 18), t(label))));
  async function paint() {
    paintBar(); titleEl.textContent = t(TITLES[mode][updating ? 1 : 0] || TITLES[mode][0]);
    const builders = { world: worldComposer, avatar: avatarComposer, game: gameComposer, canvas: canvasComposer };
    const c = await builders[mode](root, updating, carry);
    body.replaceChildren(c.el); if (c.composer) { c.composer.focus(); }
    const hints = HINTS()[mode];
    sugEl.replaceChildren(...(updating ? [] : hints.map((s) => h('button', { onclick: () => { if (c.composer) { c.composer.setText(s); c.composer.focus(); } } }, s.length > 62 ? s.slice(0, 60) + '…' : s))));
  }
  root.replaceChildren(h('div', { class: 'home' },
    updating ? h('div', { class: 'ctxbar' }, h('span', { class: 'chip' }, icon('refresh', 13), t('Atualizando:') + ' ' + updating.name + ' (v' + updating.current + ')',
      h('span', { class: 'x', title: t('Criar algo novo'), onclick: () => go('main', { fresh: true }) }, '×'))) : null,
    titleEl, updating ? null : bar, body, sugEl,
    demo ? h('div', { class: 'notice' }, t('Modo Demo (offline, sem IA): gera tudo por regras. Para usar IA de verdade, '), h('a', { href: '#/config', onclick: () => { state.ctx = { tab: 'providers' }; } }, t('configure um provedor'), '.')) : h('div', { class: 'notice' }, presetOf(state.settings.active.generation).label)));
  await paint();
}

function conflict(root, e, kind, info) {
  if (e.status === 409 && e.data && e.data.job_id) { const i = Object.assign({}, info, { id: e.data.job_id, kind }); saveJob(i); resume(root, i); return true; }
  return false;
}
async function startJob(root, url, body, kind, extra, toastFn) {
  try {
    const r = await api(url, { method: 'POST', body });
    const info = Object.assign({ id: r.job_id, kind }, extra); saveJob(info); resume(root, info);
  } catch (e) { if (!conflict(root, e, kind, extra)) toastFn(e.message); throw e; }
}

// ------------------------------------------------------------------ modo: Mundo 3D
async function worldComposer(root, project, carry) {
  const [wbs, chars] = await Promise.all([api('/api/worldbuildings'), api('/api/characters')]);
  const m = { wb: '', chars: [], persp: state.settings.generation.perspective };
  if (project && project.kind !== 'game2d') {
    try { const p = await api('/api/projects/' + project.id); m.wb = p.worldbuilding_id || ''; m.chars = p.character_ids || []; m.persp = (p.world && p.world.perspective) || m.persp; } catch (e) { project = null; }
  }
  const wbSel = select([['', t('Sem worldbuilding')]].concat(wbs.map((w) => [w.id, w.name])), m.wb, (v) => { m.wb = v; composer.refresh(); });
  const charBtn = h('button', { class: 'tool', type: 'button' });
  const perspSeg = h('div', { class: 'seg', style: { transform: 'scale(.92)', transformOrigin: 'left center' } });
  const paintChars = () => { charBtn.replaceChildren(icon('characters', 15), m.chars.length ? t('{n} personagem(ns)', { n: m.chars.length }) : t('Personagens')); charBtn.classList.toggle('on', m.chars.length > 0); };
  const paintPersp = () => perspSeg.replaceChildren(...[['first', t('1ª pessoa')], ['third', t('3ª pessoa')]].map(([v, l]) => h('button', { type: 'button', class: m.persp === v ? 'on' : '', onclick: () => { m.persp = v; paintPersp(); } }, l)));
  charBtn.addEventListener('click', () => {
    const body = h('div', null, chars.length ? chars.map((c) => {
      const cb = h('input', { type: 'checkbox', checked: m.chars.includes(c.id) });
      cb.addEventListener('change', () => { m.chars = cb.checked ? m.chars.concat(c.id) : m.chars.filter((x) => x !== c.id); paintChars(); composer.refresh(); });
      return h('label', { class: 'opt' }, cb, h('div', null, h('div', null, c.name), h('div', { class: 'small dim' }, (c.role === 'player' ? t('jogador') : 'NPC') + (c.tags.length ? ' · ' + c.tags.slice(0, 3).join(', ') : ''))));
    }) : h('div', { class: 'col', style: { padding: '10px' } }, h('span', { class: 'muted small' }, t('Você ainda não criou personagens.')), h('a', { href: '#/characters', class: 'small' }, t('Criar personagem'))));
    popover(charBtn, body);
  });
  const composer = createComposer({
    placeholder: project ? t('Descreva o que mudar neste mundo…') : t('Descreva o mundo que você quer criar…'), value: carry,
    extraReady: () => !!(m.wb || m.chars.length), tools: [h('span', { class: 'tool' }, icon('worldbuilding', 15), wbSel), charBtn, perspSeg],
    onSend: async ({ text, ids }) => {
      composer.setSending(true);
      try { await startJob(root, '/api/generate', { prompt: text, attachment_ids: ids, worldbuilding_id: m.wb, character_ids: m.chars, settings: { perspective: m.persp }, project_id: project ? project.id : '' }, 'world', { prompt: text, project }, (msg) => toast0(msg)); } catch (e) { composer.refresh(); }
    },
  });
  paintChars(); paintPersp();
  return { el: composer.el, composer };
}

// ------------------------------------------------------------------ modo: Avatar
async function avatarComposer(root, project, carry) {
  const m = { count: 0, rel: 'auto', content: state.settings.avatars && state.settings.avatars.content === 'nsfw' ? 'nsfw' : 'sfw' };
  const countEl = h('span', { class: 'tool nopad' }), relSel = select([['auto', t('Relação: automática')], ...Object.keys(REL_LABEL).filter((k) => k !== 'custom').map((k) => [k, t(REL_LABEL[k])])], m.rel, (v) => { m.rel = v; });
  const paintCount = () => countEl.replaceChildren(icon('characters', 15), h('button', { type: 'button', class: 'step-b', title: t('Menos'), onclick: () => { m.count = Math.max(0, m.count - 1); paintCount(); } }, '−'),
    h('span', { class: 'cnt' }, m.count ? t('{n} avatar(es)', { n: m.count }) : t('Quantidade: auto')), h('button', { type: 'button', class: 'step-b', title: t('Mais'), onclick: () => { m.count = Math.min(8, m.count + 1); paintCount(); } }, '+'));
  const contentSeg = seg([['sfw', 'SFW'], ['nsfw', 'NSFW']], m.content, (v) => { m.content = v; });
  contentSeg.style.transform = 'scale(.92)'; contentSeg.style.transformOrigin = 'left center';
  const composer = createComposer({
    placeholder: t('Descreva o avatar (ou vários) — ou anexe imagens, textos, documentos…'), value: carry, tools: [countEl, h('span', { class: 'tool' }, relSel), contentSeg],
    onSend: async ({ text, ids }) => {
      composer.setSending(true);
      try { await startJob(root, '/api/avatars/generate', { prompt: text, attachment_ids: ids, count: m.count, relationship: m.rel, content: m.content }, 'avatar', { prompt: text }, (msg) => toast0(msg)); } catch (e) { composer.refresh(); }
    },
  });
  paintCount();
  return { el: composer.el, composer };
}

// ------------------------------------------------------------------ modo: Jogo 2D
async function gameComposer(root, project, carry) {
  const upd = project && project.kind === 'game2d' ? project : null;
  const m = { genre: 'auto', length: state.settings.games ? state.settings.games.length : 'medium', content: state.settings.generation.content === 'sfw' ? 'sfw' : 'free' };
  const genres = (await api('/api/games/genres'));
  const genreSel = select([['auto', t('Gênero: automático')]].concat(genres.map((g) => [g.id, GENRE_LABEL[g.id] || g.label])), m.genre, (v) => { m.genre = v; });
  const lenSel = select([['short', t('Curto')], ['medium', t('Médio')], ['long', t('Longo')]], m.length, (v) => { m.length = v; });
  const contentSel = select([['free', t('Livre (SFW + NSFW)')], ['sfw', 'SFW']], m.content, (v) => { m.content = v; });
  const composer = createComposer({
    placeholder: upd ? t('Descreva o que mudar neste jogo…') : t('Descreva o jogo que você quer criar…'), value: carry,
    tools: [...(upd ? [] : [h('span', { class: 'tool' }, icon('games', 15), genreSel)]), h('span', { class: 'tool' }, lenSel), h('span', { class: 'tool' }, contentSel)],
    onSend: async ({ text, ids }) => {
      composer.setSending(true);
      try { await startJob(root, '/api/games/generate', { prompt: text, attachment_ids: ids, genre: m.genre, length: m.length, content: m.content, project_id: upd ? upd.id : '' }, 'game', { prompt: text, project: upd }, (msg) => toast0(msg)); } catch (e) { composer.refresh(); }
    },
  });
  return { el: composer.el, composer };
}

// ------------------------------------------------------------------ modo: Canvas
async function canvasComposer(root, project, carry) {
  const templates = await api('/api/canvas-templates');
  const m = { template: 'text_image' };
  const tplSel = select(templates.map((x) => [x.id, t(x.label)]), m.template, (v) => { m.template = v; hint.textContent = t((templates.find((x) => x.id === v) || {}).hint || ''); });
  const hint = h('div', { class: 'muted small', style: { textAlign: 'center', marginTop: '12px' } }, t((templates[0] || {}).hint || ''));
  const composer = createComposer({
    placeholder: t('Descreva o que você quer produzir (opcional) — vira o primeiro prompt do fluxo…'), value: carry, allowEmpty: true, tools: [h('span', { class: 'tool' }, icon('canvas', 15), tplSel)],
    onSend: async ({ text, ids }) => {
      composer.setSending(true);
      try { const c = await api('/api/canvases', { method: 'POST', body: { template: m.template, prompt: text, attachment_ids: ids } }); location.hash = '#/canvas/' + c.id; } catch (e) { toast0(e.message); composer.refresh(); }
    },
  });
  return { el: h('div', null, composer.el, hint), composer };
}

// ------------------------------------------------------------------ execução + resultado
function resume(root, info) {
  const retry = () => go('main', { fresh: true, mode: info.kind === 'game' ? 'game' : info.kind, project: info.project, prompt: info.prompt });
  if (info.kind === 'avatar') return renderRun(root, info.id, info, { title: t('Criando seus avatares…'), doneTitle: t('Avatares prontos!'), retry, done: avatarDone });
  if (info.kind === 'game') return renderRun(root, info.id, info, { title: info.project ? t('Atualizando o jogo…') : t('Criando o seu jogo…'), doneTitle: t('Jogo pronto!'), retry, done: gameDone });
  return renderRun(root, info.id, info, { title: info.project ? t('Atualizando o mundo…') : t('Criando o seu mundo…'), doneTitle: t('Mundo pronto!'), retry, done: worldDone });
}

async function worldDone(ev) {
  let palette = {};
  try { palette = (await api('/api/projects/' + ev.project_id)).palette || {}; } catch (e) { /* ok */ }
  return h('div', { class: 'result' }, h('div', { class: 'hero', style: { background: gradient(palette) } }),
    h('div', { class: 'body' }, h('h3', null, ev.title), h('p', { class: 'muted', style: { margin: '0 0 12px' } }, ev.description || ''),
      h('div', { class: 'row', style: { gap: '6px', marginBottom: '16px' } }, ev.tags.map((tg) => h('span', { class: 'chip' }, tg)), h('span', { class: 'badge' }, 'v' + ev.version)),
      ev.warnings && ev.warnings.length ? h('div', { class: 'muted small', style: { marginBottom: '12px' } }, '⚠ ' + t('Alguns agentes usaram o gerador de regras (resposta inválida do modelo). Veja prompts/agents/ no ZIP.')) : null,
      h('div', { class: 'row' },
        h('a', { class: 'btn primary', href: '/play/' + ev.project_id + '/', target: '_blank', rel: 'noopener' }, icon('play', 15), t('Jogar')),
        h('a', { class: 'btn', href: '/api/projects/' + ev.project_id + '/download' }, icon('download', 15), t('Baixar ZIP')),
        h('button', { class: 'btn', onclick: () => go('main', { project: { id: ev.project_id, name: ev.title, current: ev.version, kind: 'world' } }) }, icon('refresh', 15), t('Atualizar este mundo')),
        h('button', { class: 'btn ghost', onclick: () => go('library', { highlight: ev.project_id }) }, t('Ver na biblioteca')),
        h('button', { class: 'btn ghost', onclick: () => go('main', { fresh: true, mode: 'world' }) }, t('Novo mundo')))));
}

async function gameDone(ev) {
  let palette = {};
  try { palette = (await api('/api/projects/' + ev.project_id)).palette || {}; } catch (e) { /* ok */ }
  return h('div', { class: 'result' }, h('div', { class: 'hero', style: { background: gradient(palette) } }),
    h('div', { class: 'body' }, h('h3', null, ev.title), h('p', { class: 'muted', style: { margin: '0 0 12px' } }, ev.description || ''),
      h('div', { class: 'row', style: { gap: '6px', marginBottom: '16px' } }, h('span', { class: 'chip on' }, GENRE_LABEL[ev.genre] || ev.genre), ev.tags.map((tg) => h('span', { class: 'chip' }, tg)), h('span', { class: 'badge' }, 'v' + ev.version)),
      ev.warnings && ev.warnings.length ? h('div', { class: 'muted small', style: { marginBottom: '12px' } }, '⚠ ' + t('Alguns agentes usaram o gerador de regras (resposta inválida do modelo). Veja prompts/agents/ no ZIP.')) : null,
      h('div', { class: 'row' },
        h('a', { class: 'btn primary', href: '/play/' + ev.project_id + '/', target: '_blank', rel: 'noopener' }, icon('play', 15), t('Jogar')),
        h('a', { class: 'btn', href: '/api/projects/' + ev.project_id + '/download' }, icon('download', 15), t('Baixar ZIP')),
        h('button', { class: 'btn', onclick: () => go('main', { project: { id: ev.project_id, name: ev.title, current: ev.version, kind: 'game2d' } }) }, icon('refresh', 15), t('Atualizar este jogo')),
        h('button', { class: 'btn ghost', onclick: () => go('games', { highlight: ev.project_id }) }, t('Ver na biblioteca')),
        h('button', { class: 'btn ghost', onclick: () => go('main', { fresh: true, mode: 'game' }) }, t('Novo jogo')))));
}

async function avatarDone(ev) {
  const cards = await Promise.all(ev.avatar_ids.map((id) => api('/api/avatars/' + id).catch(() => null)));
  const list = cards.filter(Boolean);
  return h('div', { class: 'result' }, h('div', { class: 'body' }, h('h3', null, list.length > 1 ? t('{n} avatares criados', { n: list.length }) : t('Avatar criado')),
    ev.warnings && ev.warnings.length ? h('div', { class: 'muted small', style: { marginBottom: '12px' } }, '⚠ ' + ev.warnings.slice(0, 3).join(' · ')) : null,
    h('div', { class: 'av-grid', style: { gridTemplateColumns: 'repeat(auto-fill,minmax(190px,1fr))', marginBottom: '16px' } }, list.map((a) => h('div', { class: 'av-card' },
      h('div', { class: 'av-pic', onclick: () => openChat([a.id]) }, avatarPic(a, 72)),
      h('div', { class: 'av-info' }, h('div', { class: 'av-name' }, a.name), h('div', { class: 'row', style: { gap: '5px', justifyContent: 'center' } }, h('span', { class: 'chip' }, t(REL_LABEL[a.relationship] || REL_LABEL.custom)), h('span', { class: 'chip ' + (a.content === 'nsfw' ? 'nsfw' : 'solid') }, a.content === 'nsfw' ? 'NSFW' : 'SFW')),
        h('div', { class: 'av-desc' }, a.greeting || a.personality || '')),
      h('div', { class: 'row nw', style: { gap: '6px', justifyContent: 'center', marginTop: 'auto' } }, h('button', { class: 'btn sm primary', onclick: () => openChat([a.id]) }, icon('send', 13), t('Conversar')), h('a', { class: 'btn sm', href: '#/avatars/edit/' + a.id }, icon('edit', 13), t('Editar')))))),
    h('div', { class: 'row' },
      list.length > 1 ? h('button', { class: 'btn primary', onclick: () => openChat(list.map((a) => a.id)) }, icon('characters', 15), t('Conversa em grupo')) : null,
      h('a', { class: 'btn', href: '#/avatars' }, t('Ver todos os avatares')), h('button', { class: 'btn ghost', onclick: () => go('main', { fresh: true, mode: 'avatar' }) }, t('Criar mais')))));
}
