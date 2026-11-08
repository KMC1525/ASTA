import { api, events } from '../api.js';
import { getLang, t } from '../i18n.js';
import { go, state } from '../main.js';
import { confirmDialog, fill, fmtDate, h, icon, modal, select, seg, toast } from '../ui.js';
import { createComposer } from './composer.js';
import { fmtDur, mountTimeline } from './studio_timeline.js';

// Seção Studio: gera, edita e revisa vídeos com IA. Lista de projetos (único/série), criação com duração/estilo, edição automática e a página do projeto (cenas, timeline, exportar).
export const subRoute = () => { const m = location.hash.match(/^#\/studio\/([\w-]+)(?:\/(scenes|timeline|export))?/); return m ? { id: m[1], tab: m[2] || '' } : { id: '', tab: '' }; };
const STAGE_PT = { receive: 'Recebe', analyze: 'Analisa', generate: 'Gera', review: 'Revisa', deliver: 'Entrega' };
const DUR_PRESETS = [[30, '30s'], [60, '1 min'], [120, '2 min'], [300, '5 min'], [600, '10 min'], [1800, '30 min'], [3600, '1 h'], [5400, '1 h 30']];
const KIND_LABEL = { single: 'Único', series: 'Série' };
const EXPORT_LABEL = { full: ['Completo', 'Vídeo e áudio num MP4'], video: ['Somente vídeo', 'MP4 sem áudio'], audio: ['Somente áudio', 'Só a trilha de som (M4A, MP3 ou WAV)'] };
const mmss = (s) => { s = Math.round(s); const m = Math.floor(s / 60); return m ? `${m}min${s % 60 ? ' ' + String(s % 60).padStart(2, '0') + 's' : ''}` : `${s}s`; };
const typeOf = (secs, pref, durations) => {   // espelha schema.duration_type_for
  const d = Object.fromEntries(durations.map((x) => [x.id, x]));
  if (d[pref] && pref !== 'custom' && secs <= d[pref].max) return pref;
  for (const k of ['shorts', 'short', 'long']) if (secs <= d[k].max) return k;
  return 'custom';
};

export default async function render(root, ctx) {
  const meta = await api('/api/studio/meta');
  const sub = subRoute();
  if (sub.id) return renderProject(root, ctx, meta, sub);
  return renderList(root, ctx, meta);
}

// ------------------------------------------------------------------------------------------ peças reutilizáveis
function chips(options, value, onPick, cls) {
  const box = h('div', { class: 'st-chips ' + (cls || '') });
  const paint = (v) => fill(box, options.map(([id, label, hint]) => h('button', { type: 'button', class: 'st-chip' + (id === v ? ' on' : ''), dataset: { v: id }, onclick: () => { paint(id); onPick(id); } }, h('b', null, label), hint ? h('span', null, hint) : null)));
  paint(value);
  box.set = paint;
  return box;
}

// Controles de duração (tipo + minutos/segundos + controle deslizante + atalhos) e estilo. `m` é o objeto editado: { dtype, target, aspect, style, style_custom }.
function durationControls(m, meta, onChange) {
  const durs = meta.durations;
  const dmax = () => (m.dtype === 'custom' ? meta.limits.max_seconds : (durs.find((d) => d.id === m.dtype) || durs[3]).max);
  const typeBox = chips(durs.map((d) => [d.id, t(d.label), t(d.hint)]), m.dtype, (id) => {
    m.dtype = id; const d = durs.find((x) => x.id === id);
    if (id !== 'custom') { m.target = d.default; if (!m.aspectTouched) m.aspect = d.aspect; }   // cada tipo começa na sua duração padrão; depois é só ajustar
    paintTime(); onChange && onChange();
  }, 'types');
  const mi = h('input', { type: 'number', min: 0, max: 360, id: 'st-min', 'aria-label': t('minutos') }), si = h('input', { type: 'number', min: 0, max: 59, id: 'st-sec', 'aria-label': t('segundos') });
  const sl = h('input', { type: 'range', min: 5, step: 5, id: 'st-slider' }), sum = h('span', { class: 'st-sum' });
  const presets = h('div', { class: 'st-presets' }, DUR_PRESETS.map(([s, l]) => h('button', { type: 'button', class: 'st-pre', onclick: () => setTarget(s) }, l)));
  function setTarget(sec, typed) {
    sec = Math.max(meta.limits.min_seconds, Math.min(meta.limits.max_seconds, Math.round(sec)));
    const nt = typeOf(sec, m.dtype, durs);
    if (nt !== m.dtype) { m.dtype = nt; typeBox.set(nt); toast(t('A duração passou do limite do tipo escolhido: o tipo agora é «{x}».', { x: t(durs.find((d) => d.id === nt).label) })); if (!m.aspectTouched && nt !== 'custom') m.aspect = durs.find((d) => d.id === nt).aspect; }
    m.target = sec; paintTime(typed); onChange && onChange();
  }
  function paintTime(keepInputs) {
    const put = (el, v) => { if (document.activeElement !== el) el.value = v; };   // não reescreve o campo em que a pessoa está digitando
    if (!keepInputs) { put(mi, Math.floor(m.target / 60)); put(si, Math.round(m.target % 60)); }   // digitando: os campos ficam como a pessoa deixou
    const mx = dmax(); sl.max = Math.min(mx, m.dtype === 'custom' ? 10800 : mx); sl.value = Math.min(m.target, sl.max);
    sum.textContent = '= ' + fmtDur(m.target) + ' · ' + t('limite do tipo: {x}', { x: fmtDur(mx) });
    typeBox.set(m.dtype);
  }
  const apply = () => setTarget((parseInt(mi.value || '0', 10) || 0) * 60 + (parseInt(si.value || '0', 10) || 0), true);
  mi.addEventListener('change', apply); si.addEventListener('change', apply);
  sl.addEventListener('input', () => { m.target = parseInt(sl.value, 10); mi.value = Math.floor(m.target / 60); si.value = m.target % 60; sum.textContent = '= ' + fmtDur(m.target); });
  sl.addEventListener('change', () => setTarget(parseInt(sl.value, 10)));
  paintTime();
  return h('div', { class: 'st-dur' }, h('label', { class: 'f' }, t('Tipo de duração')), typeBox, h('label', { class: 'f' }, t('Duração do vídeo')),
    h('div', { class: 'st-time' }, mi, h('span', null, 'min'), si, h('span', null, 's'), sl, sum), presets);
}

function styleControls(m, meta, onChange) {
  const custom = h('textarea', { rows: 2, id: 'st-style-custom', placeholder: t('Descreva o visual: ex. aquarela suave, cores pastel, traço de lápis…'), value: m.style_custom || '', oninput: (e) => { m.style_custom = e.target.value; } });
  custom.value = m.style_custom || '';
  const box = chips(meta.styles.map((s) => [s.id, t(s.label)]), m.style, (id) => { m.style = id; custom.classList.toggle('hidden', id !== 'custom'); onChange && onChange(); }, 'styles');
  custom.classList.toggle('hidden', m.style !== 'custom');
  return h('div', null, h('label', { class: 'f' }, t('Estilo visual')), box, custom);
}

function optionControls(m, meta) {
  const lang = select([['pt-BR', 'Português (BR)'], ['en', 'English']], m.language || 'pt-BR', (v) => { m.language = v; });
  const asp = select(meta.aspects.map((a) => [a, a === '9:16' ? '9:16 · ' + t('vertical') : a === '16:9' ? '16:9 · ' + t('horizontal') : a]), m.aspect, (v) => { m.aspect = v; m.aspectTouched = true; });
  const mot = select([['auto', t('Leve: imagem com zoom e pan (Ken Burns)')], ['video', t('Modelo de vídeo em cada plano (mais lento e caro)')]], m.motion || 'auto', (v) => { m.motion = v; });
  const rev = select([[0, t('Sem revisão')], [1, t('1 rodada de correção')], [2, t('2 rodadas de correção')]], m.revisions ?? 1, (v) => { m.revisions = parseInt(v, 10); });
  const cb = (label, key) => { const i = h('input', { type: 'checkbox', checked: m[key] !== false, onchange: (e) => { m[key] = e.target.checked; } }); return h('label', { class: 'ck' }, i, h('span', null, label)); };
  const voice = h('input', { value: m.voice || '', placeholder: t('automático'), oninput: (e) => { m.voice = e.target.value.trim(); } });
  return h('details', { class: 'st-adv' }, h('summary', null, t('Opções avançadas')), h('div', { class: 'st-grid' },
    h('div', null, h('label', { class: 'f' }, t('Formato')), asp), h('div', null, h('label', { class: 'f' }, t('Idioma')), lang), h('div', null, h('label', { class: 'f' }, t('Movimento dos planos')), mot),
    h('div', null, h('label', { class: 'f' }, t('Revisão de cada cena')), rev), h('div', null, h('label', { class: 'f' }, t('Voz da narração (id/nome do provedor)')), voice), h('div', { class: 'st-cks' }, cb(t('Legendas'), 'captions'), cb(t('Música de fundo'), 'music'))));
}

// Acompanhamento simples de um job (edição automática / exportação)
function follow(host, jobId, o) {
  const list = h('div', { class: 'st-steps' }), note = h('div', { class: 'muted small st-note' });
  const stop = h('button', { class: 'btn sm', type: 'button', onclick: async () => { await api('/api/jobs/' + jobId + '/cancel', { method: 'POST' }).catch(() => {}); stop.disabled = true; } }, t('Cancelar'));
  const st = {}; let order = o.steps || [];
  const paint = () => fill(list, order.map((id) => h('div', { class: 'st-step ' + (st[id] || 'pending') }, h('span', { class: 'ic' }, st[id] === 'running' ? h('span', { class: 'spinner' }) : st[id] === 'done' ? icon('check', 14) : st[id] === 'warn' ? icon('warn', 14) : st[id] === 'error' ? icon('x', 14) : '·'), h('span', null, t(o.labels[id] || id)))));
  fill(host, h('div', { class: 'st-follow' }, list, note, h('div', { class: 'row' }, stop)));
  paint();
  const close = events('/api/jobs/' + jobId + '/events', (ev) => {
    if (ev.type === 'start' && ev.steps) { order = ev.steps; paint(); }
    else if (ev.type === 'step') { st[ev.id] = ev.status; if (!order.includes(ev.id)) order.push(ev.id); paint(); }
    else if (ev.type === 'note') note.textContent = ev.message;
    else if (ev.type === 'error') { stop.remove(); fill(host, h('div', { class: 'errbox' }, ev.message), h('div', { class: 'row', style: { marginTop: '8px' } }, h('button', { class: 'btn sm', onclick: () => o.onRetry && o.onRetry() }, t('Voltar')))); close(); }
    else if (ev.type === 'cancelled') { fill(host, h('div', { class: 'muted' }, t('Cancelado.')), h('div', { class: 'row', style: { marginTop: '8px' } }, h('button', { class: 'btn sm', onclick: () => o.onRetry && o.onRetry() }, t('Voltar')))); close(); }
    else if (ev.type === 'done') { close(); o.onDone(ev); }
  }, () => {});
  return close;
}

// ------------------------------------------------------------------------------------------ lista + criação
async function renderList(root, ctx, meta) {
  const projects = await api('/api/studio/projects');
  const D = (state.settings && state.settings.studio) || {};   /* padrões de Configuração → Studio */
  const dflt = meta.durations.find((d) => d.id === D.duration_type) || meta.durations[0];
  const m = { kind: D.kind === 'series' ? 'series' : 'single', dtype: dflt.id, target: D.target_seconds || dflt.default, aspect: D.aspect && D.aspect !== 'auto' ? D.aspect : dflt.aspect, aspectTouched: !!(D.aspect && D.aspect !== 'auto'), style: D.style || 'realistic', style_custom: D.style_custom || '',
    language: D.language && D.language !== 'auto' ? D.language : (getLang() === 'pt' ? 'pt-BR' : 'en'), motion: D.motion || 'auto', captions: D.captions !== false, music: D.music !== false, revisions: Number.isInteger(D.revisions) ? D.revisions : 1, voice: D.voice || '', name: '' };
  const mode = { v: ['autoedit', 'manual'].includes(ctx.mode) ? ctx.mode : 'new' };

  // ---- novo projeto
  const kindSeg = chips([['single', t('Único'), t('começa e termina num vídeo')], ['series', t('Série'), t('vários episódios que continuam a história')]], m.kind, (v) => { m.kind = v; }, 'kinds');
  const nameIn = h('input', { id: 'st-name', placeholder: t('Nome do projeto (opcional)'), oninput: (e) => { m.name = e.target.value; } });
  const composer = createComposer({ placeholder: t('Descreva o vídeo: tema, história, personagens, tom… (ou anexe roteiros, imagens e documentos)'), sendLabel: t('Gerar'), sendTitle: t('Planeja e gera o vídeo cena a cena'), tools: [
    h('button', { class: 'tool', type: 'button', id: 'st-only', title: t('Cria o projeto sem gerar nada ainda'), onclick: () => start(false) }, icon('plus', 15), t('Só criar o projeto'))],
  onSend: () => start(true) });
  async function start(generate) {
    const text = composer.text(), attachIds = composer.fileIds();
    if (generate && !text.trim() && !attachIds.length) { toast(t('Descreva o vídeo que você quer criar (ou anexe algo).'), 'err'); return; }
    if (composer.hasUploading()) { toast(t('Aguarde o envio dos anexos terminar.'), 'err'); return; }
    composer.setSending(true);
    try {
      const p = await api('/api/studio/projects', { method: 'POST', body: { name: m.name.trim() || text.trim().slice(0, 50) || t('Novo projeto'), kind: m.kind, duration_type: m.dtype, target_seconds: m.target, style: m.style, style_custom: m.style_custom, aspect: m.aspect,
        language: m.language, motion: m.motion, captions: m.captions, music: m.music, revisions: m.revisions, voice: m.voice, prompt: text, premise: text } });
      let job = null;
      if (generate) job = (await api(`/api/studio/projects/${p.id}/episodes/${p.episodes[0].id}/generate`, { method: 'POST', body: { prompt: text, attachment_ids: attachIds } })).job_id;
      state.ctx = job ? { job } : {};
      location.hash = '#/studio/' + p.id + (job ? '/scenes' : '');
    } catch (e) { toast(e.message, 'err'); composer.setSending(false); composer.refresh(); }
  }
  const newCard = h('div', { class: 'card st-card', id: 'st-new' }, h('h3', null, t('Novo projeto de vídeo')), h('label', { class: 'f' }, t('Tipo de projeto')), kindSeg, durationControls(m, meta), styleControls(m, meta), optionControls(m, meta),
    h('div', { class: 'st-name' }, nameIn), composer.el);

  // ---- edição automática
  const ae = { style: D.autoedit_style || 'gameplay', target: D.autoedit_target || 0, aspect: '16:9', bpm: 0, name: '' };
  const aeHost = h('div'), aeBpm = h('input', { type: 'number', min: 60, max: 240, placeholder: 'BPM', id: 'ae-bpm', oninput: (e) => { ae.bpm = parseInt(e.target.value || '0', 10) || 0; } });
  const aeTarget = h('input', { type: 'number', min: 0, max: 21600, placeholder: t('auto'), id: 'ae-target', oninput: (e) => { ae.target = parseInt(e.target.value || '0', 10) || 0; } });
  const aeComposer = createComposer({ placeholder: t('Anexe os vídeos, imagens e áudios (vários) e diga o que quer: momentos, ritmo, tom, o que destacar…'), sendLabel: t('Editar'), sendTitle: t('Monta a edição automaticamente'), tools: [], onSend: () => runAuto() });
  const craftNote = h('p', { class: 'muted small', id: 'ae-craft', style: { margin: '6px 0 0' } });
  const showCraft = (id) => { const x = meta.edit_styles.find((y) => y.id === id); craftNote.textContent = x && x.craft ? t('Técnica: ') + t(x.craft) : ''; };
  setTimeout(() => showCraft(ae.style), 0);
  const styleList = chips(meta.edit_styles.map((s) => [s.id, t(s.label), t(s.hint)]), ae.style, (v) => { ae.style = v; showCraft(v); const s = meta.edit_styles.find((x) => x.id === v); aeBpm.parentElement.classList.toggle('hidden', !s.bpm); if (s.bpm) aeBpm.placeholder = 'BPM (' + s.bpm + ')'; }, 'estyles');
  async function runAuto() {
    if (!aeComposer.fileIds().length) { toast(t('Anexe pelo menos um vídeo, imagem ou áudio.'), 'err'); return; }
    aeComposer.setSending(true);
    try {
      const ids = aeComposer.fileIds();
      const r = await api('/api/studio/autoedit', { method: 'POST', body: { attachment_ids: ids, prompt: aeComposer.text(), style: ae.style, target_seconds: ae.target, aspect: ae.aspect, bpm: ae.bpm, name: ae.name, language: m.language } });
      follow(aeHost, r.job_id, { steps: ['attachments', 'analyst', 'director', 'reviewer', 'assemble'], labels: { attachments: 'Anexos', analyst: 'Analista', director: 'Diretor', reviewer: 'Revisor', assemble: 'Montagem' },
        onDone: (ev) => { toast(t('Edição pronta: {n} cortes, {d}.', { n: ev.cuts, d: fmtDur(ev.duration) }), 'ok'); location.hash = '#/studio/' + ev.project_id + '/timeline'; }, onRetry: () => go('studio', { mode: 'autoedit' }) });
    } catch (e) { toast(e.message, 'err'); aeComposer.setSending(false); aeComposer.refresh(); }
  }
  const aeCard = h('div', { class: 'card st-card', id: 'st-auto' }, h('h3', null, t('Edição automática')), h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Anexe vários arquivos e escreva o que quer: o Analista, o Diretor e o Revisor montam os cortes no estilo escolhido, e você refina na timeline.')),
    h('label', { class: 'f' }, t('Estilo de edição')), styleList, craftNote,
    h('div', { class: 'st-grid' }, h('div', null, h('label', { class: 'f' }, t('Duração alvo (segundos; vazio = automática)')), aeTarget), h('div', null, h('label', { class: 'f' }, t('Formato')), select(meta.aspects.map((a) => [a, a]), ae.aspect, (v) => { ae.aspect = v; })),
      h('div', { class: 'hidden' }, h('label', { class: 'f' }, t('Batida (BPM)')), aeBpm)), aeComposer.el, aeHost);
  aeBpm.parentElement.classList.add('hidden');

  // ---- editar na mão: abre a timeline vazia, sem gerar nada nem usar a edição automática
  const mm = { name: '', aspect: '16:9', seconds: 60 };
  async function startManual() {
    try {
      const p = await api('/api/studio/projects', { method: 'POST', body: { name: mm.name.trim() || t('Edição manual'), kind: 'single', duration_type: 'custom', target_seconds: Math.max(5, mm.seconds || 60), aspect: mm.aspect, origin: 'manual', captions: false, music: false } });
      state.ctx = { manual: true };
      location.hash = '#/studio/' + p.id + '/timeline';
    } catch (e) { toast(e.message, 'err'); }
  }
  const manualCard = h('div', { class: 'card st-card', id: 'st-manual-card' }, h('h3', null, t('Editar na timeline')),
    h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Abre uma timeline vazia para você montar o vídeo do seu jeito: importe vídeos, imagens e áudios, corte, junte, ajuste volume, adicione legendas e exporte. Nada é gerado nem automatizado — a IA só entra se você pedir.')),
    h('div', { class: 'st-grid' }, h('div', null, h('label', { class: 'f' }, t('Nome do projeto')), h('input', { id: 'st-manual-name', placeholder: t('Edição manual'), oninput: (e) => { mm.name = e.target.value; } })),
      h('div', null, h('label', { class: 'f' }, t('Formato')), select(meta.aspects.map((a) => [a, a === '9:16' ? '9:16 · ' + t('vertical') : a === '16:9' ? '16:9 · ' + t('horizontal') : a]), mm.aspect, (v) => { mm.aspect = v; })),
      h('div', null, h('label', { class: 'f' }, t('Duração estimada (segundos)')), h('input', { type: 'number', min: 5, value: mm.seconds, id: 'st-manual-secs', oninput: (e) => { mm.seconds = parseInt(e.target.value || '60', 10) || 60; } }))),
    h('div', { class: 'row', style: { marginTop: '12px' } }, h('button', { class: 'btn primary', id: 'st-manual-go', type: 'button', onclick: startManual }, icon('film', 14), t('Abrir a timeline'))));

  const tabs = h('div', { class: 'tabs st-modes' }, h('button', { class: mode.v === 'new' ? 'on' : '', id: 'st-tab-new', onclick: () => { mode.v = 'new'; paintMode(); } }, icon('film', 14), t('Gerar com IA')),
    h('button', { class: mode.v === 'autoedit' ? 'on' : '', id: 'st-tab-auto', onclick: () => { mode.v = 'autoedit'; paintMode(); } }, icon('scissors', 14), t('Edição automática')),
    h('button', { class: mode.v === 'manual' ? 'on' : '', id: 'st-tab-manual', onclick: () => { mode.v = 'manual'; paintMode(); } }, icon('film', 14), t('Editar na timeline')));
  const creator = h('div');
  const paintMode = () => { tabs.children[0].classList.toggle('on', mode.v === 'new'); tabs.children[1].classList.toggle('on', mode.v === 'autoedit'); tabs.children[2].classList.toggle('on', mode.v === 'manual'); fill(creator, mode.v === 'new' ? newCard : mode.v === 'manual' ? manualCard : aeCard); };
  paintMode();

  // ---- projetos
  const grid = h('div', { class: 'st-grid-p' });
  const paint = () => fill(grid, projects.map((p) => h('div', { class: 'st-proj', dataset: { id: p.id }, onclick: () => { location.hash = '#/studio/' + p.id; } },
    h('div', { class: 'th', style: p.thumb ? { backgroundImage: `url("${p.thumb}")` } : {} }, p.thumb ? null : icon('film', 30), h('span', { class: 'badge vb' }, p.origin === 'autoedit' ? t('Edição automática') : t(KIND_LABEL[p.kind]))),
    h('div', { class: 'inf' }, h('div', { class: 'nm', title: p.name }, p.name), h('div', { class: 'mt' }, [p.duration ? fmtDur(p.duration) : t('alvo {x}', { x: fmtDur(p.target_seconds) }), p.episodes > 1 ? t('{n} episódios', { n: p.episodes }) : '', p.scenes ? t('{n} cenas', { n: p.scenes }) : '', fmtDate(p.updated)].filter(Boolean).join(' · ')),
      h('div', { class: 'row', style: { gap: '6px', marginTop: '8px' } }, h('span', { class: 'chip' }, (meta.durations.find((d) => d.id === p.duration_type) || {}).label ? t(meta.durations.find((d) => d.id === p.duration_type).label) : p.duration_type),
        h('span', { class: 'chip' }, t((meta.styles.find((s) => s.id === p.style) || { label: p.style }).label)), h('span', { class: 'chip' }, p.aspect), h('span', { class: 'grow' }),
        h('button', { class: 'btn ghost icon sm danger', title: t('Excluir'), onclick: async (e) => { e.stopPropagation(); if (await confirmDialog(t('Excluir «{n}» e todas as suas mídias?', { n: p.name }), true, t('Excluir'))) { await api('/api/studio/projects/' + p.id, { method: 'DELETE' }).catch((er) => toast(er.message, 'err')); projects.splice(projects.indexOf(p), 1); paint(); } } }, icon('trash', 14)))))));
  paint();
  fill(root, h('div', { class: 'page st-pg' }, h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'Studio'), h('p', null, t('Gere, edite e revise vídeos com IA: roteiro e produção cena a cena, edição automática e uma timeline completa para refinar e exportar.'))),
    h('div', { class: 'row' }, h('a', { class: 'btn', href: '#/config', onclick: () => { go('config', { tab: 'media' }); } }, icon('config', 14), t('Provedores de mídia')))), tabs, creator,
  projects.length ? h('h3', { class: 'st-h3' }, t('Seus projetos')) : h('div', { class: 'empty' }, h('h3', null, t('Nenhum projeto ainda')), h('p', null, t('Descreva um vídeo acima, ou anexe seus próprios arquivos para a edição automática.'))), grid));
}

// ------------------------------------------------------------------------------------------ página do projeto
let CUR_EP = {};
async function renderProject(root, ctx, meta, sub) {
  let p;
  try { p = await api('/api/studio/projects/' + sub.id); } catch (e) { fill(root, h('div', { class: 'page' }, h('div', { class: 'errbox' }, e.message), h('a', { class: 'btn', href: '#/studio' }, t('Voltar')))); return; }
  let epId = CUR_EP[p.id] && p.episodes.some((e) => e.id === CUR_EP[p.id]) ? CUR_EP[p.id] : (p.episodes.find((e) => e.status !== 'ready') || p.episodes[0]).id;
  let tab = sub.tab || (p.origin === 'manual' || (epOf().timeline.clips.length && epOf().status === 'ready') ? 'timeline' : 'scenes');
  let tl = null, closeJob = null, jobId = ctx.job || null, busy = false;
  const body = h('div', { class: 'st-body' }), head = h('div', { class: 'st-head' }), epBar = h('div', { class: 'st-eps' }), tabsEl = h('div', { class: 'tabs st-tabs' });
  function epOf() { return p.episodes.find((e) => e.id === epId) || p.episodes[0]; }
  const reload = async () => { p = await api('/api/studio/projects/' + p.id); };

  function paintHead() {
    const dt = meta.durations.find((d) => d.id === p.duration_type);
    fill(head, h('a', { class: 'st-back', href: '#/studio' }, '← Studio'), h('div', { class: 'row nw' }, h('h1', { class: 'st-title', id: 'st-title', contenteditable: 'plaintext-only', spellcheck: 'false', onblur: async (e) => {
      const nm = e.target.textContent.trim().slice(0, 100); if (nm && nm !== p.name) { p = await api(`/api/studio/projects/${p.id}/meta`, { method: 'POST', body: { name: nm } }); } else e.target.textContent = p.name; } , onkeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); } } }, p.name),
    h('span', { class: 'grow' }), h('button', { class: 'btn sm', id: 'st-settings', onclick: openSettings }, icon('config', 14), t('Configurações')), h('button', { class: 'btn sm', id: 'st-auto-btn', onclick: openAuto }, icon('scissors', 14), t('Edição automática'))),
    h('div', { class: 'row st-badges' }, h('span', { class: 'chip on' }, t(KIND_LABEL[p.kind])), h('span', { class: 'chip' }, dt ? t(dt.label) : p.duration_type), h('span', { class: 'chip' }, t('alvo {x}', { x: fmtDur(p.target_seconds) })),
      h('span', { class: 'chip' }, t((meta.styles.find((s) => s.id === p.style) || { label: p.style }).label)), h('span', { class: 'chip' }, p.aspect)));
    fill(epBar, p.kind === 'series' ? [...p.episodes.map((e) => h('div', { class: 'st-ep' + (e.id === epId ? ' on' : ''), dataset: { id: e.id }, onclick: () => { epId = e.id; CUR_EP[p.id] = e.id; paintAll(); } }, h('b', null, 'Ep ' + e.n), h('span', null, e.title),
      p.episodes.length > 1 ? h('button', { class: 'x', title: t('Excluir episódio'), onclick: async (ev) => { ev.stopPropagation(); if (await confirmDialog(t('Excluir o episódio «{n}»?', { n: e.title }), true, t('Excluir'))) { await api(`/api/studio/projects/${p.id}/episodes/${e.id}`, { method: 'DELETE' }).catch((er) => toast(er.message, 'err')); await reload(); epId = p.episodes[0].id; paintAll(); } } }, '×') : null)),
      h('button', { class: 'st-ep new', id: 'st-new-ep', onclick: async () => { const r = await api(`/api/studio/projects/${p.id}/episodes`, { method: 'POST', body: {} }).catch((er) => { toast(er.message, 'err'); return null; }); if (r) { p = r; epId = p.episodes[p.episodes.length - 1].id; CUR_EP[p.id] = epId; tab = 'scenes'; paintAll(); } } }, icon('plus', 14), t('Novo episódio'))] : []);
    epBar.classList.toggle('hidden', p.kind !== 'series');
  }
  function paintTabs() {
    fill(tabsEl, [['scenes', t('Roteiro e cenas'), 'list'], ['timeline', t('Timeline'), 'film'], ['export', t('Exportar'), 'download']].map(([id, label, ic]) => h('button', { class: tab === id ? 'on' : '', id: 'st-tab-' + id, onclick: () => { tab = id; history.replaceState(null, '', '#/studio/' + p.id + '/' + id); paintTabs(); paintBody(); } }, icon(ic, 14), label)));
  }
  function paintAll() { paintHead(); paintTabs(); paintBody(); }
  function paintBody() {
    tlToken++;
    if (tl) { tl.destroy(); tl = null; }
    if (tab === 'timeline') paintTimeline(); else if (tab === 'export') paintExport(); else paintScenes();
  }

  // ---------------------------------------------------------------- cenas + geração ao vivo
  function paintScenes() {
    const ep = epOf();
    const prompt = h('textarea', { id: 'st-prompt', rows: 3, placeholder: t('Descreva o vídeo (ou o que acontece neste episódio)…') }); prompt.value = ep.prompt || (ep.n === 1 ? p.premise : '');
    const bar = h('div', { class: 'st-prog hidden' }, h('i')), progTxt = h('span', { class: 'muted small' }), actions = h('div', { class: 'row' });
    const board = h('div', { class: 'st-board', id: 'st-board' }), log = h('div', { class: 'muted small st-note', id: 'st-log' });
    const delivered = () => ep.scenes.filter((s) => s.status === 'delivered').length;
    const sceneEl = (s, i) => {
      const img = s.shots.map((x) => p.assets.find((a) => a.id === x.image)).find(Boolean);
      return h('div', { class: 'st-scene ' + s.status, dataset: { id: s.id }, id: 'sc-' + s.id },
        h('div', { class: 'th', style: img ? { backgroundImage: `url("/api/studio/projects/${p.id}/media/${img.file}")` } : {} }, h('span', { class: 'n' }, i + 1)),
        h('div', { class: 'tx' }, h('div', { class: 'tt' }, s.title, h('span', { class: 'du' }, mmss(s.actual || s.secs))), h('div', { class: 'sm' }, s.summary), s.narration ? h('div', { class: 'nr' }, '“' + s.narration.slice(0, 160) + (s.narration.length > 160 ? '…' : '') + '”') : null,
          s.notes && s.notes.length ? h('div', { class: 'nt' }, '⚠ ' + s.notes.slice(0, 2).join(' · ')) : null),
        h('div', { class: 'sg' }, ['receive', 'analyze', 'generate', 'review', 'deliver'].map((k) => h('span', { class: 'stg s-' + (s.stages[k] || 'pending'), dataset: { stage: k }, title: t(STAGE_PT[k]) }, s.stages[k] === 'running' ? h('span', { class: 'spinner' }) : s.stages[k] === 'done' ? icon('check', 11) : s.stages[k] === 'warn' ? icon('warn', 11) : s.stages[k] === 'error' ? icon('x', 11) : '', t(STAGE_PT[k])))),
        h('div', { class: 'ac' }, s.score != null ? h('span', { class: 'chip' }, t('nota {n}', { n: s.score })) : null, h('button', { class: 'btn sm ghost redo', disabled: busy || s.status === 'pending' && false, title: t('Refazer só esta cena'), onclick: () => generate({ redo: [s.id] }) }, icon('refresh', 13), t('Refazer'))));
    };
    const paintBoard = () => {
      fill(board, ep.scenes.length ? ep.scenes.map(sceneEl) : [h('div', { class: 'empty' }, h('h3', null, t('Ainda não há cenas')), h('p', null, t('Descreva o vídeo e aperte «Gerar»: o Showrunner escreve o roteiro e cada cena é produzida em cinco passos — recebe, analisa, gera, revisa e entrega.')))]);
      const d = delivered(), n = ep.scenes.length;
      bar.classList.toggle('hidden', !n); bar.firstChild.style.width = n ? Math.round(100 * d / n) + '%' : '0%';
      progTxt.textContent = n ? t('{d} de {n} cenas entregues', { d, n }) + ' · ' + t('{a} de {b}', { a: fmtDur(ep.timeline.duration), b: fmtDur(ep.target || p.target_seconds) }) : '';
      paintActions();
    };
    const paintActions = () => {
      const n = ep.scenes.length, d = delivered();
      fill(actions, h('button', { class: 'btn primary', id: 'st-gen', disabled: busy, onclick: () => generate({}) }, icon('play', 14), !n ? t('Gerar') : d < n ? t('Continuar a geração') : t('Gerar de novo')),
        n ? h('button', { class: 'btn', id: 'st-replan', disabled: busy, title: t('Escreve um roteiro novo e refaz todas as cenas'), onclick: async () => { if (await confirmDialog(t('Replanejar descarta as cenas e a timeline deste episódio e gera tudo de novo. Continuar?'), true, t('Replanejar'))) generate({ replan: true }); } }, icon('refresh', 14), t('Replanejar tudo')) : null,
        busy ? h('button', { class: 'btn', id: 'st-cancel', onclick: async () => { await api('/api/jobs/' + jobId + '/cancel', { method: 'POST' }).catch(() => {}); } }, t('Cancelar')) : null,
        d ? h('button', { class: 'btn ghost', onclick: () => { tab = 'timeline'; paintTabs(); paintBody(); } }, icon('film', 14), t('Abrir na timeline')) : null);
    };
    async function generate(extra) {
      if (busy) return;
      try {
        await api(`/api/studio/projects/${p.id}/episodes/${ep.id}/meta`, { method: 'POST', body: { prompt: prompt.value } });
        const r = await api(`/api/studio/projects/${p.id}/episodes/${ep.id}/generate`, { method: 'POST', body: Object.assign({ prompt: prompt.value }, extra) });
        attach(r.job_id);
      } catch (e) { if (e.status === 409 && e.data && e.data.job_id) attach(e.data.job_id); else toast(e.message, 'err'); }
    }
    function attach(id) {
      jobId = id; busy = true; paintActions(); board.querySelectorAll('.redo').forEach((b) => { b.disabled = true; });
      if (closeJob) closeJob();
      let pending = 0;
      const refresh = async () => { if (pending) return; pending = 1; try { await reload(); const e2 = epOf(); Object.assign(ep, e2); ep.scenes = e2.scenes; ep.timeline = e2.timeline; paintBoard(); } finally { pending = 0; } };
      closeJob = events('/api/jobs/' + id + '/events', (ev) => {
        if (ev.type === 'scene') {
          const row = board.querySelector('#sc-' + ev.id);
          if (row) { const chip = row.querySelector(`.stg[data-stage="${ev.stage}"]`); if (chip && ev.status) { chip.className = 'stg s-' + ev.status; } row.className = 'st-scene ' + (ev.stage === 'error' ? 'error' : 'running'); if (ev.status === 'running') row.scrollIntoView({ block: 'nearest' }); }
          if (ev.status === 'done' || ev.status === 'warn' || ev.status === 'error') refresh();
        } else if (ev.type === 'plan' || ev.type === 'scene_done' || ev.type === 'progress') refresh();
        else if (ev.type === 'note') log.textContent = ev.message;
        else if (ev.type === 'step' && ev.id === 'planner') log.textContent = ev.status === 'running' ? t('O Showrunner está escrevendo o roteiro…') : t('Roteiro pronto.');
        else if (ev.type === 'error') { busy = false; log.replaceChildren(h('div', { class: 'errbox' }, ev.message)); refresh().then(paintBoard); }
        else if (ev.type === 'cancelled') { busy = false; log.textContent = t('Geração cancelada. O que já foi entregue está salvo: use «Continuar a geração».'); refresh(); }
        else if (ev.type === 'done') { busy = false; log.textContent = ev.warnings && ev.warnings.length ? '⚠ ' + ev.warnings.slice(0, 3).join(' · ') : t('Pronto.'); refresh().then(() => { toast(t('Episódio gerado: {d}', { d: fmtDur(ev.duration) }), 'ok'); }); }
      }, () => { busy = false; paintActions(); });
    }
    fill(body, h('div', { class: 'st-scenes' }, h('div', { class: 'card st-promptbox' }, h('label', { class: 'f' }, ep.n > 1 || p.kind === 'series' ? t('Sobre este episódio') : t('Sobre o vídeo')), prompt, actions,
      ep.recap ? h('p', { class: 'muted small', style: { marginBottom: 0 } }, h('b', null, t('Resumo:') + ' '), ep.recap) : null), h('div', { class: 'row st-progress' }, bar, progTxt), log, board));
    paintBoard();
    if (jobId && ctx.job === jobId) { ctx.job = null; attach(jobId); } else if (!busy) {
      api(`/api/studio/projects/${p.id}/job`).then((j) => { if (j.job_id && j.kind === 'generate' && tab === 'scenes') attach(j.job_id); }).catch(() => {});
    }
  }

  // ---------------------------------------------------------------- timeline
  let manual = !!ctx.manual || p.origin === 'manual';   // projeto criado para editar na mão: a timeline abre mesmo vazia
  async function paintTimeline() {
    const my = ++tlToken;
    try { await reload(); } catch (e) { /* segue com o que há */ }   // mídias e timeline sempre frescas: nada de bin vazio por dado velho
    if (my !== tlToken || tab !== 'timeline') return;
    const ep = epOf();
    if (!ep.timeline.clips.length && !p.assets.length && !manual) {
      fill(body, h('div', { class: 'empty' }, h('h3', null, t('A timeline está vazia')), h('p', null, t('Gere o episódio na aba «Roteiro e cenas», use a edição automática ou importe mídias e monte do zero.')),
        h('div', { class: 'row', style: { justifyContent: 'center' } }, h('button', { class: 'btn primary', onclick: () => { tab = 'scenes'; paintTabs(); paintBody(); } }, t('Ir para o roteiro')), h('button', { class: 'btn', id: 'st-manual', onclick: () => { manual = true; paintTimeline(); } }, t('Editar do zero')))));
      return;
    }
    const host = h('div', { class: 'st-tlhost' }); fill(body, host);
    tl = mountTimeline(host, { pid: p.id, eid: ep.id, timeline: ep.timeline, assets: p.assets, aspect: p.aspect, onSaved: (x) => { ep.timeline = x; }, onAsset: (a) => { if (!p.assets.some((y) => y.id === a.id)) p.assets.push(a); }, onAssetRemoved: (a) => { p.assets = p.assets.filter((y) => y.id !== a.id); } });
  }
  let tlToken = 0;

  // ---------------------------------------------------------------- exportar
  function paintExport() {
    const ep = epOf();
    const SD = (state.settings && state.settings.studio) || {};
    const x = { mode: 'full', quality: SD.export_quality || '720p', format: SD.audio_format || 'm4a', fps: (meta.fps || [24]).includes(SD.export_fps) ? SD.export_fps : 24 };
    const out = h('div', { class: 'st-exp-out', id: 'st-exp-out' }), listEl = h('div', { class: 'st-exports', id: 'st-exports' });
    const modeBox = chips(['full', 'video', 'audio'].map((k) => [k, t(EXPORT_LABEL[k][0]), t(EXPORT_LABEL[k][1])]), x.mode, (v) => { x.mode = v; q.classList.toggle('hidden', v === 'audio'); fp.classList.toggle('hidden', v === 'audio'); f.classList.toggle('hidden', v !== 'audio'); }, 'modes');
    const q = h('div', null, h('label', { class: 'f' }, t('Qualidade')), select(meta.quality.map((v) => [v, v]), x.quality, (v) => { x.quality = v; }));
    const fp = h('div', null, h('label', { class: 'f' }, t('Quadros por segundo (fps)')), select((meta.fps || [24]).map((v) => [v, v + ' fps']), x.fps, (v) => { x.fps = parseInt(v, 10); }));
    const f = h('div', { class: 'hidden' }, h('label', { class: 'f' }, t('Formato do áudio')), select(meta.audio_formats.map((v) => [v, v.toUpperCase()]), x.format, (v) => { x.format = v; }));
    const paintList = () => fill(listEl, ep.exports.length ? [...ep.exports].reverse().map((r) => h('div', { class: 'st-exp' }, h('span', { class: 'chip' }, t(EXPORT_LABEL[r.mode][0])), h('span', null, r.file), h('span', { class: 'muted small' }, fmtDur(r.dur) + (r.quality ? ' · ' + r.quality : '') + (r.fps ? ' · ' + r.fps + ' fps' : '') + ' · ' + (r.size / 1048576).toFixed(1) + ' MB'), h('span', { class: 'grow' }),
      h('a', { class: 'btn sm', href: `/api/studio/projects/${p.id}/exports/${r.file}`, target: '_blank', rel: 'noopener' }, icon('play', 13), t('Abrir')), h('a', { class: 'btn sm', href: `/api/studio/projects/${p.id}/exports/${r.file}?download=1` }, icon('download', 13), t('Baixar')),
      h('button', { class: 'btn ghost icon sm danger', title: t('Excluir'), onclick: async () => { await api(`/api/studio/projects/${p.id}/exports/${r.file}`, { method: 'DELETE' }); ep.exports = ep.exports.filter((e) => e.file !== r.file); paintList(); } }, icon('trash', 13)))) : [h('div', { class: 'muted small' }, t('Nenhuma exportação ainda.'))]);
    const go1 = h('button', { class: 'btn primary', id: 'st-export', onclick: async () => {
      go1.disabled = true;
      try {
        const r = await api(`/api/studio/projects/${p.id}/episodes/${ep.id}/export`, { method: 'POST', body: x });
        follow(out, r.job_id, { steps: [], labels: {}, onDone: async (ev) => { go1.disabled = false; fill(out, h('div', { class: 'ok-note' }, icon('check', 15), ' ' + t('Exportado: {f}', { f: ev.export.file }), ' ', h('a', { href: ev.url, target: '_blank', rel: 'noopener' }, t('Abrir')))); await reload(); Object.assign(ep, epOf()); ep.exports = epOf().exports; paintList(); }, onRetry: () => { go1.disabled = false; out.replaceChildren(); } });
        out.querySelector('.st-steps').replaceChildren(h('span', { class: 'spinner' }), ' ', t('Exportando…'));
      } catch (e) { go1.disabled = false; if (e.status === 409) toast(t('Já há uma geração ou exportação em andamento neste projeto.'), 'err'); else toast(e.message, 'err'); }
    } }, icon('download', 14), t('Exportar'));
    fill(body, h('div', { class: 'card st-export' }, h('h3', null, t('Exportar o episódio')), h('p', { class: 'muted small', style: { marginTop: 0 } }, ep.timeline.clips.length ? t('Duração da timeline: {d}', { d: fmtDur(ep.timeline.duration) }) : t('A timeline está vazia.')),
      h('label', { class: 'f' }, t('O que exportar')), modeBox, h('div', { class: 'st-grid' }, q, fp, f), h('p', { class: 'muted small', style: { margin: '8px 0 0' }, id: 'st-exp-hint' }, t('2K e 4K com 60 ou 120 fps pedem um computador forte e geram arquivos grandes; a exportação usa a predefinição mais leve do codificador para gastar menos CPU.')), h('div', { class: 'row', style: { marginTop: '14px' } }, go1), out), h('h3', { class: 'st-h3' }, t('Exportações')), listEl);
    paintList();
  }

  // ---------------------------------------------------------------- configurações e edição automática do projeto
  async function openSettings() {
    const m = { dtype: p.duration_type, target: p.target_seconds, aspect: p.aspect, style: p.style, style_custom: p.style_custom, language: p.language, motion: p.motion, captions: p.captions, music: p.music, revisions: p.revisions, voice: p.voice, aspectTouched: true };
    const nameIn = h('input', { value: p.name });
    const ok = await modal(t('Configurações do projeto'), h('div', { class: 'st-settings' }, h('label', { class: 'f' }, t('Nome')), nameIn, durationControls(m, meta), styleControls(m, meta), optionControls(m, meta)), [{ label: t('Cancelar'), value: false }, { label: t('Salvar'), value: true, cls: 'primary' }]);
    if (!ok) return;
    try { p = await api(`/api/studio/projects/${p.id}/meta`, { method: 'POST', body: { name: nameIn.value.trim() || p.name, duration_type: m.dtype, target_seconds: m.target, aspect: m.aspect, style: m.style, style_custom: m.style_custom, language: m.language, motion: m.motion, captions: m.captions, music: m.music, revisions: m.revisions, voice: m.voice } }); paintAll(); toast(t('Salvo'), 'ok'); }
    catch (e) { toast(e.message, 'err'); }
  }
  async function openAuto() {
    const ae = { style: 'gameplay', target: 0, bpm: 0 };
    const ep = epOf(), hasContent = ep.timeline.clips.length > 0;
    if (hasContent && p.kind === 'single' && !(await confirmDialog(t('Este projeto já tem uma timeline. A edição automática vai substituí-la. Continuar?'), true, t('Substituir')))) return;
    const host = h('div'), cmp = createComposer({ placeholder: t('Anexe os arquivos e diga o que quer…'), sendLabel: t('Editar'), tools: [], onSend: () => run() });
    const target = h('input', { type: 'number', min: 0, placeholder: t('auto'), oninput: (e) => { ae.target = parseInt(e.target.value || '0', 10) || 0; } });
    const bpm = h('input', { type: 'number', min: 60, max: 240, placeholder: 'BPM', oninput: (e) => { ae.bpm = parseInt(e.target.value || '0', 10) || 0; } });
    const list = chips(meta.edit_styles.map((s) => [s.id, t(s.label), t(s.hint)]), ae.style, (v) => { ae.style = v; }, 'estyles');
    let done;
    const closeP = modal(t('Edição automática'), h('div', { class: 'st-settings' }, p.kind === 'series' ? h('p', { class: 'muted small' }, t('O resultado entra como um novo episódio.')) : null, h('label', { class: 'f' }, t('Estilo de edição')), list,
      h('div', { class: 'st-grid' }, h('div', null, h('label', { class: 'f' }, t('Duração alvo (segundos)')), target), h('div', null, h('label', { class: 'f' }, t('Batida (BPM)')), bpm)), cmp.el, host), [{ label: t('Fechar'), value: false }]);
    async function run() {
      cmp.setSending(true);
      try {
        const r = await api('/api/studio/autoedit', { method: 'POST', body: { attachment_ids: cmp.fileIds(), prompt: cmp.text(), style: ae.style, target_seconds: ae.target, aspect: p.aspect, bpm: ae.bpm, project_id: p.id, language: p.language } });
        follow(host, r.job_id, { steps: ['attachments', 'analyst', 'director', 'reviewer', 'assemble'], labels: { attachments: 'Anexos', analyst: 'Analista', director: 'Diretor', reviewer: 'Revisor', assemble: 'Montagem' },
          onDone: async (ev) => { document.querySelector('.modal-bg')?.remove(); await reload(); epId = ev.episode_id; CUR_EP[p.id] = epId; tab = 'timeline'; paintAll(); toast(t('Edição pronta: {n} cortes, {d}.', { n: ev.cuts, d: fmtDur(ev.duration) }), 'ok'); }, onRetry: () => { cmp.setSending(false); cmp.refresh(); host.replaceChildren(); } });
      } catch (e) { toast(e.message, 'err'); cmp.setSending(false); cmp.refresh(); }
    }
    await closeP;
  }

  fill(root, h('div', { class: 'page st-pg st-project' }, head, epBar, tabsEl, body));
  paintAll();
  window.ASTA_STUDIO = { alive: () => root.isConnected, timeline: () => tl };
}
