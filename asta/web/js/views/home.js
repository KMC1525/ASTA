import { api, events, upload } from '../api.js';
import { getLang, t } from '../i18n.js';
import { go, presetOf, state } from '../main.js';
import { fmtBytes, gradient, h, icon, kindIcon, popover, select, toast } from '../ui.js';

const STEPS = {
  attachments: ['Anexos', 'Lê textos, planilhas, imagens, áudios e vídeos'],
  analyst: ['Analista', 'Entende o pedido e extrai ideias dos anexos'],
  planner: ['Planejador', 'Desenha o mapa, os pontos de interesse e o orçamento de hardware'],
  characters: ['Personagens', 'Cria os agentes de IA (cards) que vão viver no mundo'],
  architect: ['Arquiteto do mundo', 'Monta terreno, estruturas, clima e NPCs'],
  sound_ux: ['Som e interface', 'Define trilha, ambiente sonoro e a interface do jogo'],
  reviewer: ['Revisor', 'Critica o resultado e pede correções, se preciso'],
  package: ['Empacotamento', 'Gera a pasta/ZIP do jogo e salva na biblioteca'],
};
const MOOD = { calm: 'Calmo', tense: 'Tenso', mysterious: 'Misterioso', epic: 'Épico', melancholic: 'Melancólico', joyful: 'Alegre' };
const AMB = { wind: 'Vento', forest: 'Floresta', rain: 'Chuva', ocean: 'Oceano', city: 'Cidade', cave: 'Caverna', desert: 'Deserto', night: 'Noite', none: 'Nenhum' };
const stepDetail = (id, s, d) => {
  d = d || {};
  if (s === 'running') return d.revision ? t('revisando…') : t('trabalhando…');
  if (s === 'error') return d.message || '';
  const warn = s === 'warn' ? ' · ' + t('usou o gerador de regras (resposta inválida do modelo)') : '';
  switch (id) {
    case 'attachments': return s === 'skipped' ? t('Sem anexos') : t('{n} arquivo(s)', { n: d.count }) + (d.images ? ' · ' + t('{n} imagem(ns) para visão', { n: d.images }) : '');
    case 'analyst': return d.title ? '“' + d.title + '”' + warn : warn.slice(3);
    case 'planner': return t('{n} pontos de interesse', { n: d.landmarks || 0 }) + warn;
    case 'characters': return s === 'skipped' ? t('Usando os personagens existentes') : t('{n} personagem(ns) criado(s)', { n: d.count }) + warn;
    case 'architect': return t('{a} estruturas · {b} NPCs', { a: d.structures, b: d.npcs }) + warn;
    case 'sound_ux': return t('música {m} · ambiente {a}', { m: t(MOOD[d.music] || d.music).toLowerCase(), a: t(AMB[d.ambience] || d.ambience).toLowerCase() }) + warn;
    case 'reviewer': return (d.approved ? t('aprovado') : t('com ressalvas')) + (d.score != null ? ' · ' + t('nota {n}/10', { n: d.score }) : '') + (d.issues ? ' · ' + t('{n} apontamentos', { n: d.issues }) : '') + warn;
    case 'package': return t('versão {n} salva', { n: d.version });
    default: return '';
  }
};

const SUGGEST = () => getLang() === 'pt'
  ? ['Uma vila medieval numa floresta ao anoitecer, com chuva leve e uma taverna acolhedora', 'Um acampamento no deserto com ruínas antigas e uma arqueóloga curiosa', 'Uma cidade cyberpunk à noite, com neblina e ruas movimentadas']
  : ['A medieval village in a forest at dusk, with light rain and a cozy tavern', 'A desert camp with ancient ruins and a curious archaeologist', 'A cyberpunk city at night, with fog and busy streets'];

export default async function render(root, ctx) {
  if (ctx.fresh) sessionStorage.removeItem('asta.job');
  const saved = JSON.parse(sessionStorage.getItem('asta.job') || 'null');
  if (saved && !ctx.project) {
    try { const j = await api('/api/jobs/' + saved.id); if (j) return renderRun(root, saved.id, saved); } catch (e) { sessionStorage.removeItem('asta.job'); }
  }
  return renderComposer(root, ctx);
}

// ------------------------------------------------------------------ composer
async function renderComposer(root, ctx) {
  const [wbs, chars] = await Promise.all([api('/api/worldbuildings'), api('/api/characters')]);
  const m = { prompt: ctx.prompt || '', files: [], wb: ctx.project ? '' : '', chars: [], persp: state.settings.generation.perspective, project: ctx.project || null };
  if (m.project) {
    try { const p = await api('/api/projects/' + m.project.id); m.wb = p.worldbuilding_id || ''; m.chars = p.character_ids || []; m.persp = (p.world && p.world.perspective) || m.persp; m.project.name = p.name; m.project.current = p.current; } catch (e) { m.project = null; }
  }
  const ta = h('textarea', { rows: 2, placeholder: m.project ? t('Descreva o que mudar neste mundo…') : t('Descreva o mundo que você quer criar…') });
  ta.value = m.prompt;
  const attachRow = h('div', { class: 'attach-row hidden' });
  const fileInput = h('input', { type: 'file', multiple: true, class: 'hidden' });
  const sendBtn = h('button', { class: 'send', title: t('Gerar'), disabled: true }, icon('send', 18));
  const wbSel = select([['', t('Sem worldbuilding')]].concat(wbs.map((w) => [w.id, w.name])), m.wb, (v) => { m.wb = v; });
  const charBtn = h('button', { class: 'tool', type: 'button' });
  const perspSeg = h('div', { class: 'seg', style: { transform: 'scale(.92)', transformOrigin: 'left center' } });

  const paintChars = () => { charBtn.replaceChildren(icon('characters', 15), m.chars.length ? t('{n} personagem(ns)', { n: m.chars.length }) : t('Personagens')); charBtn.classList.toggle('on', m.chars.length > 0); };
  const paintPersp = () => perspSeg.replaceChildren(...[['first', t('1ª pessoa')], ['third', t('3ª pessoa')]].map(([v, l]) => h('button', { type: 'button', class: m.persp === v ? 'on' : '', onclick: () => { m.persp = v; paintPersp(); } }, l)));
  const uploading = () => m.files.some((f) => f.status === 'up');
  const refresh = () => { sendBtn.disabled = uploading() || (!ta.value.trim() && !m.files.length && !m.wb && !m.chars.length); };
  const paintFiles = () => {
    attachRow.classList.toggle('hidden', !m.files.length);
    attachRow.replaceChildren(...m.files.map((f) => h('div', { class: 'att', title: f.error || f.name },
      f.status === 'up' ? h('div', { class: 'spinner' }) : kindIcon(f.kind || 'file'),
      h('span', { class: 'n' }, f.name), h('span', { class: 's' }, f.error ? '⚠' : fmtBytes(f.size)),
      f.status === 'up' ? h('div', { class: 'bar' }, h('i', { style: { width: Math.round(f.progress * 100) + '%' } })) : null,
      h('span', { class: 'x', onclick: () => { if (f.id) api('/api/uploads/' + f.id, { method: 'DELETE' }).catch(() => {}); m.files = m.files.filter((x) => x !== f); paintFiles(); refresh(); } }, '×'))));
    refresh();
  };
  const kindOf = (n) => { const e = n.split('.').pop().toLowerCase(); return { png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', mp3: 'audio', wav: 'audio', ogg: 'audio', m4a: 'audio', flac: 'audio', mp4: 'video', mov: 'video', webm: 'video', mkv: 'video', pdf: 'document', docx: 'document', doc: 'document', odt: 'document', xlsx: 'spreadsheet', csv: 'spreadsheet', ods: 'spreadsheet', pptx: 'presentation', odp: 'presentation' }[e] || 'text'; };
  const addFiles = (list) => {
    [...list].forEach((file) => {
      const f = { name: file.name, size: file.size, kind: kindOf(file.name), progress: 0, status: 'up' };
      m.files.push(f); paintFiles();
      upload(file, (p) => { f.progress = p; paintFiles(); }).then((meta) => { f.id = meta.id; f.status = 'ok'; paintFiles(); })
        .catch((e) => { f.status = 'err'; f.error = e.message; toast(e.message, 'err'); m.files = m.files.filter((x) => x !== f); paintFiles(); });
    });
  };
  fileInput.addEventListener('change', () => { addFiles(fileInput.files); fileInput.value = ''; });
  ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(240, ta.scrollHeight) + 'px'; m.prompt = ta.value; refresh(); });
  ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (!sendBtn.disabled) go_(); } });
  ta.addEventListener('paste', (e) => { const fs = [...(e.clipboardData ? e.clipboardData.files : [])]; if (fs.length) { e.preventDefault(); addFiles(fs); } });
  wbSel.addEventListener('change', refresh);

  charBtn.addEventListener('click', () => {
    const body = h('div', null, chars.length ? chars.map((c) => {
      const cb = h('input', { type: 'checkbox', checked: m.chars.includes(c.id) });
      cb.addEventListener('change', () => { m.chars = cb.checked ? m.chars.concat(c.id) : m.chars.filter((x) => x !== c.id); paintChars(); refresh(); });
      return h('label', { class: 'opt' }, cb, h('div', null, h('div', null, c.name), h('div', { class: 'small dim' }, (c.role === 'player' ? t('jogador') : 'NPC') + (c.tags.length ? ' · ' + c.tags.slice(0, 3).join(', ') : ''))));
    }) : h('div', { class: 'col', style: { padding: '10px' } }, h('span', { class: 'muted small' }, t('Você ainda não criou personagens.')), h('a', { href: '#/characters', class: 'small' }, t('Criar personagem'))));
    popover(charBtn, body);
  });

  const composer = h('div', { class: 'composer' }, attachRow, ta,
    h('div', { class: 'tools' },
      h('button', { class: 'tool', type: 'button', title: t('Anexar arquivos'), onclick: () => fileInput.click() }, icon('clip', 15), t('Anexar')),
      h('span', { class: 'tool' }, icon('worldbuilding', 15), wbSel), charBtn, perspSeg, sendBtn, fileInput));
  ['dragenter', 'dragover'].forEach((ev) => composer.addEventListener(ev, (e) => { e.preventDefault(); composer.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach((ev) => composer.addEventListener(ev, (e) => { e.preventDefault(); composer.classList.remove('drag'); }));
  composer.addEventListener('drop', (e) => { if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files); });

  async function go_() {
    sendBtn.disabled = true;
    try {
      const r = await api('/api/generate', { method: 'POST', body: {
        prompt: m.prompt, attachment_ids: m.files.map((f) => f.id).filter(Boolean), worldbuilding_id: m.wb, character_ids: m.chars,
        settings: { perspective: m.persp }, project_id: m.project ? m.project.id : '' } });
      const info = { id: r.job_id, prompt: m.prompt, project: m.project };
      sessionStorage.setItem('asta.job', JSON.stringify(info));
      renderRun(root, r.job_id, info);
    } catch (e) {
      if (e.status === 409 && e.data && e.data.job_id) { toast(t('Já existe uma geração em andamento — acompanhe por aqui.')); const info = { id: e.data.job_id }; sessionStorage.setItem('asta.job', JSON.stringify(info)); return renderRun(root, e.data.job_id, info); }
      toast(e.message, 'err'); refresh();
    }
  }
  sendBtn.addEventListener('click', go_);

  const demo = state.settings.active.generation === 'demo';
  root.replaceChildren(h('div', { class: 'home' },
    m.project ? h('div', { class: 'ctxbar' }, h('span', { class: 'chip' }, icon('refresh', 13), t('Atualizando:') + ' ' + m.project.name + ' (v' + m.project.current + ')',
      h('span', { class: 'x', title: t('Criar um mundo novo'), onclick: () => go('main', { fresh: true }) }, '×'))) : null,
    h('h1', null, m.project ? t('O que vamos mudar?') : t('O que vamos criar?')),
    composer,
    m.project ? null : h('div', { class: 'suggest' }, SUGGEST().map((s) => h('button', { onclick: () => { ta.value = s; ta.dispatchEvent(new Event('input')); ta.focus(); } }, s.length > 62 ? s.slice(0, 60) + '…' : s))),
    demo ? h('div', { class: 'notice' }, t('Modo Demo (offline, sem IA): gera mundos por regras. Para usar IA de verdade, '), h('a', { href: '#/config', onclick: () => { state.ctx = { tab: 'providers' }; } }, t('configure um provedor'), '.')) : h('div', { class: 'notice' }, presetOf(state.settings.active.generation).label)));
  paintChars(); paintPersp(); paintFiles(); ta.dispatchEvent(new Event('input')); ta.focus();
}

// ------------------------------------------------------------------ execução do pipeline
function renderRun(root, jobId, info) {
  const st = {}; let order = Object.keys(STEPS); order.forEach((id) => (st[id] = { status: 'pending', detail: {}, t0: 0, t1: 0 }));
  const stepsEl = h('div', { class: 'steps' }), head = h('div'), extra = h('div');
  const actions = h('div', { class: 'row', style: { marginTop: '18px' } });
  let startAt = Date.now(), timer, closeEs = () => {}, finished = false, revisions = [];
  const cancelBtn = h('button', { class: 'btn', onclick: async () => { await api('/api/jobs/' + jobId + '/cancel', { method: 'POST' }); cancelBtn.disabled = true; } }, t('Cancelar'));
  actions.append(cancelBtn);

  const iconFor = (s) => s === 'running' ? h('div', { class: 'spinner' }) : s === 'done' ? h('span', { class: 'ok' }, icon('check', 18)) : s === 'warn' ? h('span', { class: 'warn' }, icon('warn', 17)) : s === 'error' ? h('span', { class: 'err' }, icon('x', 18)) : s === 'skipped' ? h('span', { class: 'dim' }, '–') : h('span', { class: 'dim' }, '·');
  const secs = (x) => { const e = (x.t1 || Date.now()) - x.t0; return x.t0 ? (e / 1000).toFixed(e < 10000 ? 1 : 0) + 's' : ''; };
  const paint = () => {
    stepsEl.replaceChildren(...order.map((id) => { const s = st[id]; return h('div', { class: 'step ' + (s.status === 'pending' ? 'pending' : s.status) },
      h('div', { class: 'ic' }, iconFor(s.status)), h('div', null, h('div', { class: 'nm' }, t(STEPS[id][0])), h('div', { class: 'ds' }, s.status === 'pending' ? t(STEPS[id][1]) : stepDetail(id, s.status, s.detail))),
      h('div', { class: 'tm' }, secs(s))); }));
    extra.replaceChildren(...revisions.map((r) => h('div', { class: 'muted small', style: { marginTop: '10px' } }, t('Revisão {n}: o Revisor pediu {m} ajuste(s) — refazendo.', { n: r.round, m: r.issues }))));
  };
  const title = info && info.project ? t('Atualizando o mundo…') : t('Criando o seu mundo…');
  head.replaceChildren(h('h2', null, title), h('div', { class: 'sub' }, t('Vários agentes de IA trabalham em etapas. Você pode sair desta tela: a geração continua.')));
  root.replaceChildren(h('div', { class: 'run' }, head, stepsEl, extra, actions));
  paint();
  timer = setInterval(() => { if (!finished) paint(); }, 500);

  const fail = (msg) => { finished = true; clearInterval(timer); sessionStorage.removeItem('asta.job'); cancelBtn.remove();
    actions.replaceChildren(h('button', { class: 'btn primary', onclick: () => go('main', { fresh: true, project: info && info.project, prompt: info && info.prompt }) }, t('Voltar e tentar de novo')), h('a', { class: 'btn', href: '#/config', onclick: () => { state.ctx = { tab: 'providers' }; } }, t('Ver provedores')));
    root.querySelector('.run').insertBefore(h('div', { class: 'errbox' }, msg), actions); paint(); };

  closeEs = events('/api/jobs/' + jobId + '/events', (ev) => {
    if (ev.type === 'start') { order = ev.steps; head.querySelector('.sub').textContent = presetOf(ev.provider).label + (ev.model && ev.model !== 'demo' ? ' · ' + ev.model : '') + ' · ' + t('hardware {t}', { t: ev.tier }); order.forEach((id) => { if (!st[id]) st[id] = { status: 'pending', detail: {}, t0: 0, t1: 0 }; }); }
    else if (ev.type === 'step') { const s = st[ev.id]; if (!s) return; s.status = ev.status; s.detail = ev.detail || {}; if (ev.status === 'running') { s.t0 = s.t0 || Date.now(); s.t1 = 0; } else { s.t0 = s.t0 || Date.now(); s.t1 = Date.now(); } }
    else if (ev.type === 'revision') revisions.push(ev);
    else if (ev.type === 'error') { const bad = order.find((id) => st[id].status === 'running'); if (bad) { st[bad].status = 'error'; st[bad].t1 = Date.now(); } fail(ev.message); }
    else if (ev.type === 'cancelled') fail(t('Geração cancelada.'));
    else if (ev.type === 'done') done(ev);
    paint();
  }, () => {});

  async function done(ev) {
    finished = true; clearInterval(timer); sessionStorage.removeItem('asta.job');
    let palette = {};
    try { palette = (await api('/api/projects/' + ev.project_id)).palette || {}; } catch (e) { /* ok */ }
    cancelBtn.remove();
    const res = h('div', { class: 'result' },
      h('div', { class: 'hero', style: { background: gradient(palette) } }),
      h('div', { class: 'body' }, h('h3', null, ev.title), h('p', { class: 'muted', style: { margin: '0 0 12px' } }, ev.description || ''),
        h('div', { class: 'row', style: { gap: '6px', marginBottom: '16px' } }, ev.tags.map((tg) => h('span', { class: 'chip' }, tg)), h('span', { class: 'badge' }, 'v' + ev.version)),
        ev.warnings && ev.warnings.length ? h('div', { class: 'muted small', style: { marginBottom: '12px' } }, '⚠ ' + t('Alguns agentes usaram o gerador de regras (resposta inválida do modelo). Veja prompts/agents/ no ZIP.')) : null,
        h('div', { class: 'row' },
          h('a', { class: 'btn primary', href: '/play/' + ev.project_id + '/', target: '_blank', rel: 'noopener' }, icon('play', 15), t('Jogar')),
          h('a', { class: 'btn', href: '/api/projects/' + ev.project_id + '/download' }, icon('download', 15), t('Baixar ZIP')),
          h('button', { class: 'btn', onclick: () => go('main', { project: { id: ev.project_id, name: ev.title, current: ev.version } }) }, icon('refresh', 15), t('Atualizar este mundo')),
          h('button', { class: 'btn ghost', onclick: () => go('library', { highlight: ev.project_id }) }, t('Ver na biblioteca')),
          h('button', { class: 'btn ghost', onclick: () => go('main', { fresh: true }) }, t('Novo mundo')))));
    root.querySelector('.run').insertBefore(res, stepsEl); actions.remove(); res.scrollIntoView({ block: 'start' });
    head.querySelector('h2').textContent = t('Mundo pronto!');
  }
}
