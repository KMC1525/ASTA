import { api } from '../api.js';
import { getLang, t } from '../i18n.js';
import { go, presetOf, state } from '../main.js';
import { avatarPic, REL_LABEL } from '../avatar_ui.js';
import { gradient, h, icon, popover, select, seg, toast } from '../ui.js';
import { openChat } from './avatars.js';
import { createComposer } from './composer.js';
import { clearJob, renderRun, saveJob, savedJob } from './run.js';
import { teamPicker } from '../team_ui.js';
import { GENRE_LABEL } from './steps.js';

const toast0 = (msg) => toast(msg, 'err');
// avisos vindos do servidor (em português): «modo Demo (sem IA): <motivo>» etc.
const trWarn = (w) => { const m = /^(modo Demo \(sem IA\): )(.*)$/.exec(String(w)); return m ? t(m[1]) + t(m[2]) : t(String(w)); };
export const MODES = [['world', 'Mundo 3D', 'worlds'], ['avatar', 'Avatar', 'avatars'], ['game', 'Jogo 2D', 'games'], ['canvas', 'Canvas', 'canvas']];
export const TITLES = { world: ['O que vamos criar?', 'O que vamos mudar?'], avatar: ['Quem vamos criar?', ''], game: ['Que jogo vamos criar?', 'O que vamos mudar neste jogo?'], canvas: ['O que vamos produzir?', ''], rebuild: ['Qual jogo vamos reconstruir?', ''] };
export const HINTS = () => {
  const pt = getLang() === 'pt';
  return {
    world: pt ? ['Uma vila medieval numa floresta ao anoitecer, com chuva leve e uma taverna acolhedora', 'Um acampamento no deserto com ruínas antigas e uma arqueóloga curiosa', 'Uma cidade cyberpunk à noite, com neblina e ruas movimentadas']
      : ['A medieval village in a forest at dusk, with light rain and a cozy tavern', 'A desert camp with ancient ruins and a curious archaeologist', 'A cyberpunk city at night, with fog and busy streets'],
    avatar: pt ? ['Uma amiga divertida e carinhosa chamada Luna, que adora astronomia', 'Três amigos de faculdade: Theo, Mia e Caio', 'Um mentor sábio e paciente chamado Davi, que me ajuda com a carreira']
      : ['A funny, caring friend named Luna who loves astronomy', 'Three college friends: Theo, Mia and Caio', 'A wise, patient mentor named Davi who helps me with my career'],
    game: pt ? ['Uma visual novel romântica num café, com escolhas e três finais', 'Um RPG de aventura: uma vila, uma floresta e um dragão numa masmorra', 'Um jogo de plataforma numa floresta encantada, com moedas e inimigos', 'Um shooter espacial com chefes', 'Um escape room point & click numa casa trancada']
      : ['A romantic visual novel in a café, with choices and three endings', 'An adventure RPG: a village, a forest and a dragon in a dungeon', 'A platformer in an enchanted forest, with coins and enemies', 'A space shooter with bosses', 'A point & click escape room in a locked house'],
    canvas: [],
    rebuild: [],
  };
};

// Retoma a execução de uma criação em andamento (a tela de acompanhamento) quando o usuário volta ao Chat. Devolve true se retomou.
export async function resumeIfRunning(root, ctx, section) {
  if (ctx.fresh) clearJob();
  const saved = savedJob();
  if (section && saved && (saved.from || '') !== section) return false;   // numa seção, só retoma o que foi iniciado nela
  if (saved && (!ctx.project || section)) {
    try { const j = await api('/api/jobs/' + saved.id); if (j) { resume(root, saved); return true; } } catch (e) { clearJob(); }
  }
  return false;
}

function conflict(root, e, kind, info) {
  if (e.status === 409 && e.data && e.data.job_id) { const i = Object.assign({}, info, { id: e.data.job_id, kind }); saveJob(i); resume(root, i); return true; }
  return false;
}
// Seção de onde a criação foi iniciada ('' = tela Chat). O compositor embutido das seções (mountCreator) liga isto durante o clique em Run.
let ORIGIN = '';
let FROM = '';   // seção da criação que está sendo acompanhada: os botões «Novo…»/«Tentar de novo» voltam para ela em vez de ir ao Chat
const again = (section, mode, ctx) => (FROM ? go(FROM, {}) : go('main', Object.assign({ fresh: true, mode }, ctx || {})));
async function startJob(root, url, body, kind, extra, toastFn) {
  const from = ORIGIN;
  try {
    const r = await api(url, { method: 'POST', body });
    const info = Object.assign({ id: r.job_id, kind, from }, extra); saveJob(info); resume(root, info);
  } catch (e) { if (!conflict(root, e, kind, Object.assign({ from }, extra))) toastFn(e.message); throw e; }
}

// ------------------------------------------------------------------ modo: Mundo 3D
async function worldTool(root, project, carry, composer) {
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
    }) : h('div', { class: 'col', style: { padding: '10px' } }, h('span', { class: 'muted small' }, t('Você ainda não criou personagens.')), h('a', { href: '#/worlds/characters', class: 'small' }, t('Criar personagem'))));
    popover(charBtn, body);
  });
  const team = teamPicker(state.settings.generation, null, { id: 'world-team' });   // esforço (Low … Omni) e 1/4/8/12/16 agentes: vêm marcados como em Configuração
  const cfg = {
    placeholder: project ? t('Descreva o que mudar neste mundo…') : t('Descreva o mundo que você quer criar…'),
    extraReady: () => !!(m.wb || m.chars.length), tools: [h('span', { class: 'tool' }, icon('worldbuilding', 15), wbSel), charBtn, perspSeg, team.el],
    onSend: async ({ text, ids }) => {
      composer.setSending(true);
      try { await startJob(root, '/api/generate', { prompt: text, attachment_ids: ids, worldbuilding_id: m.wb, character_ids: m.chars, settings: { perspective: m.persp }, team: team.get(), project_id: project ? project.id : '' }, 'world', { prompt: text, project }, (msg) => toast0(msg)); } catch (e) { composer.refresh(); }
    },
  };
  paintChars(); paintPersp();
  return cfg;
}

// ------------------------------------------------------------------ modo: Avatar
async function avatarTool(root, project, carry, composer) {
  const m = { count: 0, rel: 'auto', ctype: 'auto', base: false, imgMode: 'each', content: state.settings.avatars && state.settings.avatars.content === 'nsfw' ? 'nsfw' : 'sfw' };
  const countEl = h('span', { class: 'tool nopad' }), relSel = select([['auto', t('Relação: automática')], ...Object.keys(REL_LABEL).filter((k) => k !== 'custom').map((k) => [k, t(REL_LABEL[k])])], m.rel, (v) => { m.rel = v; });
  const paintCount = () => countEl.replaceChildren(icon('characters', 15), h('button', { type: 'button', class: 'step-b', title: t('Menos'), onclick: () => { m.count = Math.max(0, m.count - 1); paintCount(); } }, '−'),
    h('span', { class: 'cnt' }, m.count ? t('{n} avatar(es)', { n: m.count }) : t('Quantidade: auto')), h('button', { type: 'button', class: 'step-b', title: t('Mais'), onclick: () => { m.count = Math.min(8, m.count + 1); paintCount(); } }, '+'));
  const contentSeg = seg([['sfw', 'SFW'], ['nsfw', 'NSFW']], m.content, (v) => { m.content = v; paintBase(); });
  contentSeg.style.transform = 'scale(.92)'; contentSeg.style.transformOrigin = 'left center';
  // tipo de personagem: fictício (SFW ou NSFW) ou pessoa real (sempre SFW); automático = o analista decide
  const typeSel = select([['auto', t('Tipo: automático')], ['fictional', t('Personagem fictício')], ['real', t('Pessoa real (sempre SFW)')]], m.ctype, (v) => { m.ctype = v; paintBase(); });
  // foto/arte como base: a imagem anexada define o visual do avatar (e vira o retrato); o texto e os outros anexos só complementam
  const baseBtn = h('button', { class: 'tool', type: 'button', title: t('Usa as imagens anexadas (foto ou arte) como base visual do avatar. Dá para enviar só a imagem ou somar texto e outros anexos.'), onclick: () => { m.base = !m.base; paintBase(); } });
  const modeSeg = h('div', { class: 'seg', style: { transform: 'scale(.92)', transformOrigin: 'left center' } });
  const baseNote = h('div', { class: 'muted small', style: { textAlign: 'center', marginTop: '10px' } });
  const paintBase = () => {
    baseBtn.replaceChildren(icon('image', 15), t('Foto/arte como base')); baseBtn.classList.toggle('on', m.base);
    modeSeg.classList.toggle('hidden', !m.base);
    modeSeg.replaceChildren(...[['each', t('Um avatar por imagem')], ['one', t('Uma pessoa com todas as imagens')]].map(([v, l]) => h('button', { type: 'button', class: m.imgMode === v ? 'on' : '', onclick: () => { m.imgMode = v; paintBase(); } }, l)));
    baseNote.textContent = (m.base ? t('Anexe a foto ou arte (clipe ou arrastar). O texto é opcional: nome, personalidade, história… Fotos de pessoas reais ficam sempre em SFW; NSFW só vale para arte de personagens fictícios.') + ' ' : '')
      + (m.ctype === 'real' && m.content === 'nsfw' ? t('Pessoas reais ficam sempre em SFW: o ASTA não cria conteúdo sexual sobre pessoas reais. Personagens fictícios adultos podem ser NSFW.') : '');
    composer.configure({ placeholder: m.base ? t('Opcional: nome, personalidade, história… (a imagem anexada é a base do visual)') : t('Descreva o avatar (ou vários) — ou anexe imagens, textos, documentos…') });
  };
  const team = teamPicker(state.settings.avatars, null, { id: 'avatar-team' });
  const cfg = {
    placeholder: t('Descreva o avatar (ou vários) — ou anexe imagens, textos, documentos…'), tools: [baseBtn, modeSeg, countEl, h('span', { class: 'tool' }, relSel), h('span', { class: 'tool' }, typeSel), contentSeg, team.el],
    onSend: async ({ text, ids }) => {
      composer.setSending(true);
      try { await startJob(root, '/api/avatars/generate', { prompt: text, attachment_ids: ids, count: m.count, relationship: m.rel, character_type: m.ctype, content: m.content, from_images: m.base, images_mode: m.imgMode, team: team.get() }, 'avatar', { prompt: text }, (msg) => toast0(msg)); } catch (e) { composer.refresh(); }
    },
  };
  paintCount(); paintBase();
  return Object.assign(cfg, { below: baseNote });
}

// ------------------------------------------------------------------ modo: Jogo 2D
async function gameTool(root, project, carry, composer) {
  const upd = project && project.kind === 'game2d' ? project : null;
  const m = { genre: 'auto', length: state.settings.games ? state.settings.games.length : 'medium', content: state.settings.generation.content === 'sfw' ? 'sfw' : 'free' };
  const genres = (await api('/api/games/genres'));
  const genreSel = select([['auto', t('Gênero: automático')]].concat(genres.map((g) => [g.id, GENRE_LABEL[g.id] || g.label])), m.genre, (v) => { m.genre = v; });
  const lenSel = select([['short', t('Curto')], ['medium', t('Médio')], ['long', t('Longo')]], m.length, (v) => { m.length = v; });
  const contentSel = select([['free', t('Livre (SFW + NSFW)')], ['sfw', 'SFW']], m.content, (v) => { m.content = v; });
  const team = teamPicker(state.settings.games, null, { id: 'game-team' });
  const cfg = {
    placeholder: upd ? t('Descreva o que mudar neste jogo…') : t('Descreva o jogo que você quer criar…'),
    tools: [...(upd ? [] : [h('span', { class: 'tool' }, icon('games', 15), genreSel)]), h('span', { class: 'tool' }, lenSel), h('span', { class: 'tool' }, contentSel), team.el],
    onSend: async ({ text, ids }) => {
      composer.setSending(true);
      try { await startJob(root, '/api/games/generate', { prompt: text, attachment_ids: ids, genre: m.genre, length: m.length, content: m.content, team: team.get(), project_id: upd ? upd.id : '' }, 'game', { prompt: text, project: upd }, (msg) => toast0(msg)); } catch (e) { composer.refresh(); }
    },
  };
  return cfg;
}

// ------------------------------------------------------------------ modo: Canvas
const TPL_TEXT = {
  blank: ['Em branco', 'Um canvas vazio: adicione os nós que quiser.'], text_image: ['Texto → Imagem', 'Um prompt de texto que vira uma imagem.'],
  image_video: ['Texto → Imagem → Vídeo', 'Gera uma imagem e anima em um vídeo curto.'], styled: ['Com estilo do projeto', 'Style Prompt + prompt + imagem: o estilo vale para todo o canvas.'],
  scene: ['Cena completa (imagem, voz e Editor)', 'Roteiro → imagem → vídeo + narração + som, tudo montado no Editor.'],
};
const TPL_LABEL = (x) => t((TPL_TEXT[x.id] || [x.label])[0]);
const TPL_HINT = (x) => (x ? t((TPL_TEXT[x.id] || [0, x.hint])[1]) : '');
async function canvasTool(root, project, carry, composer) {
  const templates = (await api('/api/canvas-templates')).templates;
  const m = { template: 'text_image' };
  const tplSel = select(templates.map((x) => [x.id, TPL_LABEL(x)]), m.template, (v) => { m.template = v; hint.textContent = TPL_HINT(templates.find((x) => x.id === v)); });
  const hint = h('div', { class: 'muted small', style: { textAlign: 'center', marginTop: '12px' } }, TPL_HINT(templates.find((x) => x.id === m.template)));
  const cfg = {
    placeholder: t('Descreva o que você quer produzir (opcional) — vira o primeiro prompt do fluxo…'), allowEmpty: true, tools: [h('span', { class: 'tool' }, icon('canvas', 15), tplSel)],
    onSend: async ({ text, ids }) => {
      composer.setSending(true);
      try { const c = await api('/api/canvases', { method: 'POST', body: { template: m.template, prompt: text, attachment_ids: ids } }); location.hash = '#/canvas/edit/' + c.id; } catch (e) { toast0(e.message); composer.refresh(); }
    },
  };
  return Object.assign(cfg, { below: hint });
}

// ------------------------------------------------------------------ execução + resultado
function resume(root, info) {
  FROM = info.from || '';
  const retry = () => (FROM ? go(FROM, {}) : go('main', { fresh: true, mode: info.kind === 'game' ? 'game' : info.kind, project: info.project, prompt: info.prompt }));
  if (info.kind === 'avatar') return renderRun(root, info.id, info, { title: t('Criando seus avatares…'), doneTitle: t('Avatares prontos!'), retry, done: avatarDone });
  if (info.kind === 'rebuild') return renderRun(root, info.id, info, { title: t('Reconstruindo o jogo…'), doneTitle: t('Jogo reconstruído!'), retry: () => again('rebuild', 'rebuild'), done: rebuildDone });
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
        h('button', { class: 'btn', onclick: () => again('', 'world', { project: { id: ev.project_id, name: ev.title, current: ev.version, kind: 'world' } }) }, icon('refresh', 15), t('Atualizar este mundo')),
        h('button', { class: 'btn ghost', onclick: () => go('library', { highlight: ev.project_id }) }, t('Ver na biblioteca')),
        h('button', { class: 'btn ghost', onclick: () => again('', 'world') }, t('Novo mundo')))));
}

// aviso legal do Rebuild (vem do servidor, nos dois idiomas)
const legalBox = (n) => { const x = n && (n[getLang() === 'pt' ? 'pt' : 'en'] || n.pt); return !x ? null : h('div', { class: 'legal', role: 'note' }, h('div', { class: 'lg-t' }, icon('warn', 16), x.title), h('p', null, x.intro), h('ul', null, x.points.map((p) => h('li', null, p))), h('p', { class: 'small dim' }, x.scope)); };

function refineSummary(r) {
  if (!r || (!r.calls && !r.cleaned)) return null;
  const parts = [];
  if (r.cleaned) parts.push(t('{n} texto(s) limpo(s)', { n: r.cleaned }));
  if (r.calls) parts.push(t('{n} fala(s) revisada(s)', { n: r.polished || 0 }), t('{n} nome(s) legível(is)', { n: r.named || 0 }), t('{n} chamada(s) à IA', { n: r.calls }));
  return h('p', { class: 'muted small', style: { margin: '0 0 12px' } }, '✦ ' + t('Revisão de texto:') + ' ' + parts.join(' · ') + (r.reverted ? ' · ' + t('revertida (a estrutura mudou)') : ''));
}

async function rebuildDone(ev) {
  let palette = {};
  try { palette = (await api('/api/projects/' + ev.project_id)).palette || {}; } catch (e) { /* ok */ }
  return h('div', { class: 'result' }, h('div', { class: 'hero', style: { background: gradient(palette) } }),
    h('div', { class: 'body' }, h('h3', null, ev.title), h('p', { class: 'muted', style: { margin: '0 0 12px' } }, ev.description || ''),
      h('div', { class: 'row', style: { gap: '6px', marginBottom: '16px' } }, h('span', { class: 'chip on' }, GENRE_LABEL[ev.genre] || ev.genre), h('span', { class: 'chip' }, (ev.rebuild && ev.rebuild.engine_name) || ''), h('span', { class: 'badge' }, 'v' + ev.version)),
      ev.warnings && ev.warnings.length ? h('details', { class: 'muted small', style: { marginBottom: '12px' } }, h('summary', null, '⚠ ' + t('{n} aviso(s) da reconstrução', { n: ev.warnings.length })), h('ul', null, ev.warnings.slice(0, 12).map((w) => h('li', null, w)))) : null,
      refineSummary(ev.refine),
      legalBox(ev.notice),
      h('div', { class: 'row', style: { marginTop: '14px' } },
        h('a', { class: 'btn primary', href: '/play/' + ev.project_id + '/', target: '_blank', rel: 'noopener' }, icon('play', 15), t('Jogar')),
        h('a', { class: 'btn', href: '/api/projects/' + ev.project_id + '/download' }, icon('download', 15), t('Baixar ZIP')),
        h('button', { class: 'btn ghost', onclick: () => go('games', { highlight: ev.project_id }) }, t('Ver na biblioteca')),
        h('button', { class: 'btn ghost', onclick: () => again('', 'rebuild') }, t('Reconstruir outro jogo')))));
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
        h('button', { class: 'btn', onclick: () => again('', 'game', { project: { id: ev.project_id, name: ev.title, current: ev.version, kind: 'game2d' } }) }, icon('refresh', 15), t('Atualizar este jogo')),
        h('button', { class: 'btn ghost', onclick: () => go('games', { highlight: ev.project_id }) }, t('Ver na biblioteca')),
        h('button', { class: 'btn ghost', onclick: () => again('', 'game') }, t('Novo jogo')))));
}

async function avatarDone(ev) {
  const cards = await Promise.all(ev.avatar_ids.map((id) => api('/api/avatars/' + id).catch(() => null)));
  const list = cards.filter(Boolean);
  return h('div', { class: 'result' }, h('div', { class: 'body' }, h('h3', null, list.length > 1 ? t('{n} avatares criados', { n: list.length }) : t('Avatar criado')),
    ev.warnings && ev.warnings.length ? h('div', { class: 'muted small', style: { marginBottom: '12px' } }, '⚠ ' + ev.warnings.slice(0, 3).map(trWarn).join(' · ')) : null,
    h('div', { class: 'av-grid', style: { gridTemplateColumns: 'repeat(auto-fill,minmax(190px,1fr))', marginBottom: '16px' } }, list.map((a) => h('div', { class: 'av-card' },
      h('div', { class: 'av-pic', onclick: () => openChat([a.id]) }, avatarPic(a, 72)),
      h('div', { class: 'av-info' }, h('div', { class: 'av-name' }, a.name), h('div', { class: 'row', style: { gap: '5px', justifyContent: 'center' } }, h('span', { class: 'chip' }, t(REL_LABEL[a.relationship] || REL_LABEL.custom)), h('span', { class: 'chip ' + (a.content === 'nsfw' ? 'nsfw' : 'solid') }, a.content === 'nsfw' ? 'NSFW' : 'SFW')),
        h('div', { class: 'av-desc' }, a.greeting || a.personality || '')),
      h('div', { class: 'row nw', style: { gap: '6px', justifyContent: 'center', marginTop: 'auto' } }, h('button', { class: 'btn sm primary', onclick: () => openChat([a.id]) }, icon('send', 13), t('Conversar')), h('a', { class: 'btn sm', href: '#/avatars/edit/' + a.id }, icon('edit', 13), t('Editar')))))),
    h('div', { class: 'row' },
      list.length > 1 ? h('button', { class: 'btn primary', onclick: () => openChat(list.map((a) => a.id)) }, icon('characters', 15), t('Conversa em grupo')) : null,
      h('a', { class: 'btn', href: '#/avatars' }, t('Ver todos os avatares')), h('button', { class: 'btn ghost', onclick: () => again('', 'avatar') }, t('Criar mais')))));
}

// ferramentas de criação do Chat (os ativadores): cada uma devolve a configuração do compositor — placeholder, opções, o que o Run faz
// Rebuild: reconstrói um jogo Ren'Py / RPG Maker (ZIP anexado) nos motores 2D do ASTA — sem IA; o aviso legal aparece no fim.
async function rebuildTool(root, project, carry, composer) {
  const m = { refine: !(state.settings.rebuild && state.settings.rebuild.refine === false) };
  const refineBox = h('label', { class: 'tool', title: t('Uma equipe de agentes de IA (Perfilador → Polidor → Auditor) revisa só o TEXTO do jogo em etapas curtas, feita para modelos locais pequenos. A estrutura nunca muda. Sem IA configurada, só a limpeza automática roda.') },
    h('input', { type: 'checkbox', checked: m.refine, onchange: (e) => { m.refine = e.target.checked; } }), ' ', t('Revisar o texto com IA'));
  const team = teamPicker(state.settings.rebuild, null, { id: 'rebuild-team' });
  const cfg = {
    placeholder: t("Anexe o ZIP do jogo (Ren'Py ou RPG Maker) que você quer reconstruir…"), allowEmpty: false, tools: [refineBox, team.el],
    onSend: async ({ ids }) => {
      if (!ids.length) { toast0(t('Anexe o ZIP do jogo (ou os scripts/arquivos de dados) para reconstruí-lo.')); return; }
      composer.setSending(true);
      try { await startJob(root, '/api/games/rebuild', { attachment_ids: ids, refine: m.refine, team: team.get() }, 'rebuild', { prompt: '' }, (msg) => toast0(msg)); } catch (e) { composer.refresh(); }
    },
  };
  return Object.assign(cfg, { below: h('div', { class: 'muted small', style: { textAlign: 'center', marginTop: '12px', maxWidth: '560px', marginInline: 'auto' } },
    t("Aceita Ren'Py (scripts .rpy) e RPG Maker 2000 → MZ, em ZIP. Reconstrói a estrutura (mapas, eventos, diálogos, escolhas…) em HTML, CSS e JS puros; a arte e o áudio originais não são copiados. Só para uso pessoal — um aviso legal aparece ao final.")) });
}

// Compositor embutido nas seções (Mundos, Avatars, Jogos 2D, Rebuild): a mesma ferramenta de criação do Chat, sem precisar ir até lá.
// `section` = rota da seção (para voltar a ela depois); `project` = atualizar um mundo/jogo existente. Devolve { el, setProject(p), focus() }.
export async function mountCreator(root, { mode, section, project }) {
  const el = h('div', { class: 'card creator', id: 'creator' });
  const body = h('div');
  let proj = project || null, composer = null;
  const mk = async () => {
    body.replaceChildren(h('div', { class: 'muted small' }, t('Carregando…')));
    composer = createComposer({ placeholder: '', sendLabel: t('Run'), sendTitle: t('Executar'), tools: [] });
    let cfg;
    try { cfg = await TOOL_BUILDERS[mode](root, proj, '', composer); } catch (e) { body.replaceChildren(h('div', { class: 'errbox' }, e.message)); return; }
    composer.configure({ placeholder: cfg.placeholder, tools: cfg.tools || [], extraReady: cfg.extraReady || null, allowEmpty: !!cfg.allowEmpty,
      onSend: (x) => { ORIGIN = section; try { return cfg.onSend(x); } finally { ORIGIN = ''; } } });
    body.replaceChildren(composer.el, cfg.below || null);
  };
  const head = h('div', { class: 'row', style: { marginBottom: '8px' } });
  const paintHead = () => {
    const [newT, updT] = TITLES[mode] || ['', ''];
    head.replaceChildren(h('b', null, proj ? t(updT || newT) + ' — ' + proj.name : t(newT)), h('span', { class: 'grow' }),
      proj ? h('button', { class: 'btn ghost sm', type: 'button', onclick: () => api0(null) }, '× ' + t('Criar um novo')) : null);
  };
  const api0 = async (p) => { proj = p; paintHead(); await mk(); };
  el.append(head, body);
  paintHead();
  await mk();
  return { el, setProject: async (p) => { await api0(p); el.scrollIntoView({ block: 'center' }); if (composer) composer.focus(); }, focus: () => { el.scrollIntoView({ block: 'center' }); if (composer) composer.focus(); } };
}

export const TOOL_BUILDERS = { world: worldTool, avatar: avatarTool, game: gameTool, canvas: canvasTool, rebuild: rebuildTool };
