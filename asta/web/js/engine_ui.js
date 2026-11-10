// Game Engine — peças compartilhadas pelas 7 abas: estado do projeto (E), API do projeto, painel de prompt com IA (anexos, web, equipe, progresso ao vivo) e utilidades.
import { api, events } from './api.js';
import { t } from './i18n.js';
import { state } from './main.js';
import { renderMarkdown } from './markdown.js';
import { teamPicker } from './team_ui.js';
import { createComposer } from './views/composer.js';
import { h, icon, toast } from './ui.js';

export const TABS = [['main', 'Main', 'engine'], ['code', 'Code', 'code'], ['assets', 'Assets', 'palette'], ['sound', 'Sound', 'wave'], ['scripts', 'Scripts', 'script'], ['map', 'Map', 'mountain'], ['publish', 'Publish', 'rocket']];
export const KINDS = [['2d', '2D'], ['2.5d', '2.5D'], ['3d', '3D'], ['vr', 'VR'], ['ar', 'AR']];
export const THEME_LABEL = { forest: 'Floresta', desert: 'Deserto', snow: 'Neve', night: 'Noite', cave: 'Caverna', city: 'Cidade', space: 'Espaço', sea: 'Mar', candy: 'Doces', lava: 'Lava', retro: 'Retrô', sunset: 'Entardecer' };
export const BIOME_LABEL = { temperate: 'Temperado', forest: 'Floresta', desert: 'Deserto', snow: 'Neve', tropical: 'Tropical', island: 'Ilha', mountain: 'Montanha', swamp: 'Pântano', wasteland: 'Pós-apocalipse', volcanic: 'Vulcânico' };
export const GENRE_LABEL = { platformer: 'Plataforma', topdown: 'Aventura (vista de cima)', shooter: 'Nave (side scroller)', iso: 'Isométrico', explore: 'Exploração 3D', fps: 'Primeira pessoa', vr_explore: 'VR: exploração', vr_room: 'VR: sala', ar_place: 'AR: colocar objetos', ar_hunt: 'AR: caça aos itens' };
export const SIZE_LABEL = { short: 'Curto', medium: 'Médio', long: 'Longo' };

let catCache = null;
export async function catalog() { if (!catCache) catCache = await api('/api/engine/catalog'); return catCache; }

// ---- API do projeto
export function projectApi(pid) {
  const base = `/api/engine/projects/${pid}`;
  const q = (o) => Object.entries(o).filter(([, v]) => v != null && v !== '').map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
  const A = {
    base, play: (rest = 'index.html') => `/api/engine/play/${pid}/${rest}`,
    get: (p, opt) => api(base + p, opt), post: (p, body) => api(base + p, { method: 'POST', body: body || {} }), put: (p, body) => api(base + p, { method: 'PUT', body }), del: (p) => api(base + p, { method: 'DELETE' }),
    tree: (area = 'game') => api(`${base}/tree?area=${area}`),
    read: (path, area = 'game') => api(`${base}/file?${q({ area, path })}`),
    write: (path, content, area = 'game') => api(`${base}/file?${q({ area, path })}`, { method: 'PUT', body: { content } }),
    remove: (path, area = 'game') => api(`${base}/file?${q({ area, path })}`, { method: 'DELETE' }),
    mkdir: (path, area = 'game') => api(`${base}/mkdir`, { method: 'POST', body: { area, path } }),
    rename: (path, to, area = 'game') => api(`${base}/rename`, { method: 'POST', body: { area, path, to } }),
    raw: (path, area = 'game') => `${base}/raw?${q({ area, path })}&t=${Date.now() % 100000}`,
    upload: (path, blob, area = 'game') => api(`${base}/upload?${q({ area, path })}`, { method: 'POST', body: blob, raw: true, headers: { 'Content-Type': 'application/octet-stream' } }),
    scene: (name) => api(`${base}/scenes/${encodeURIComponent(name)}`), saveScene: (name, sc) => api(`${base}/scenes/${encodeURIComponent(name)}`, { method: 'PUT', body: sc }),
    maps: () => api(`${base}/maps`), map: (path) => api(`${base}/map?path=${encodeURIComponent(path)}`), saveMap: (path, m) => api(`${base}/map?path=${encodeURIComponent(path)}`, { method: 'PUT', body: m }),
  };
  return A;
}
export const flatFiles = (nodes, out = []) => { (nodes || []).forEach((n) => { if (n.type === 'file') out.push(n); else flatFiles(n.children, out); }); return out; };
export const stem = (p) => String(p).split('/').pop().replace(/\.[^.]+$/, '');
export const fmtSize = (n) => (n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : n > 1024 ? Math.round(n / 1024) + ' KB' : n + ' B');
export const deep = (o) => JSON.parse(JSON.stringify(o));
export const dataUrlToBlob = (u) => { const [head, b64] = u.split(','); const mime = /data:([^;]+)/.exec(head)[1]; const bin = atob(b64); const a = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i); return new Blob([a], { type: mime }); };
export const blobToDataUrl = (b) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(b); });
export const b64ToBlob = (b64, mime) => { const bin = atob(b64); const a = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i); return new Blob([a], { type: mime }); };

// ---- o estado do editor (uma instância por projeto aberto; as abas leem e escrevem aqui)
export async function openProject(pid) {
  const [proj, cat, status] = await Promise.all([api('/api/engine/projects/' + pid), catalog(), api('/api/engine/status').catch(() => ({ text: {}, media: {}, tools: {} }))]);
  const E = { pid, proj, cat, status, logs: {}, api: projectApi(pid), tabCleanup: [] };
  E.refresh = async () => { E.proj = await api('/api/engine/projects/' + pid); return E.proj; };
  E.go = (tab) => { state.ctx = {}; location.hash = `#/engine/${pid}/${tab}`; };
  E.listeners = new Set();
  E.emit = (ev, data) => E.listeners.forEach((fn) => { try { fn(ev, data); } catch (e) { console.error(e); } });
  E.onCleanup = (fn) => E.tabCleanup.push(fn);
  E.cleanup = () => { E.tabCleanup.splice(0).forEach((fn) => { try { fn(); } catch (e) { /* ok */ } }); };
  return E;
}

// ---- painel de prompt com IA (todas as abas têm um): conversa, anexos de qualquer tipo (ZIP, vídeo…), busca na web, equipe de agentes e progresso ao vivo
// o: { tab, endpoint, placeholder, body(): campos extras, onResult(data), onEvent(ev), title, hints: [texto], tools: [Node], intro: texto }
export function promptPanel(E, o) {
  const log = E.logs[o.tab] = E.logs[o.tab] || [];
  const list = h('div', { class: 'ge-log', 'aria-live': 'polite' });
  let web = !!((state.settings || {}).engine || {}).web, jobId = '', stop = null, cur = null;
  const webBtn = h('button', { class: 'tool' + (web ? ' on' : ''), type: 'button', id: 'ge-web-' + o.tab, title: t('Busca na web nativa: o resultado entra no contexto da IA'), 'aria-pressed': String(web), onclick: () => { web = !web; webBtn.classList.toggle('on', web); webBtn.setAttribute('aria-pressed', String(web)); } }, icon('globe', 15), t('Web'));
  const team = teamPicker((state.settings || {}).engine || {}, null, { id: 'ge-team-' + o.tab });
  const ai = E.status.text && E.status.text.ai;
  const badge = h('div', { class: 'ge-aibadge ' + (ai ? 'ok' : 'warn'), title: ai ? t('IA configurada') : t('Sem IA configurada: o Game Engine usa regras automáticas. Configure em Configuração → Provedores.') },
    h('span', { class: 'dot' }), ai ? (E.status.text.label || 'IA') + (E.status.text.model ? ' · ' + E.status.text.model : '') : t('Modo regras (sem IA)'));
  const composer = createComposer({
    placeholder: o.placeholder || t('Descreva o que você quer…'), tools: [webBtn, ...(o.tools || [])], rightTools: [team.el], sendLabel: o.sendLabel || '', sendTitle: o.sendTitle || t('Enviar'),
    onSend: ({ text, ids }) => run(text, ids),
  });
  composer.el.id = 'ge-composer-' + o.tab;

  function addMsg(role, content, extra) { const m = Object.assign({ role, content }, extra || {}); log.push(m); if (log.length > 60) log.shift(); const n = renderMsg(m); list.appendChild(n); list.scrollTop = list.scrollHeight; return n; }
  function renderMsg(m) {
    if (m.role === 'user') return h('div', { class: 'ge-msg user' }, h('div', { class: 'b' }, m.content));
    if (m.role === 'err') return h('div', { class: 'ge-msg err' }, h('div', { class: 'b' }, icon('warn', 14), ' ', m.content));
    const body = h('div', { class: 'b' }); if (m.html) renderMarkdown(body, m.content); else body.textContent = m.content;
    return h('div', { class: 'ge-msg ai' }, body, m.notes && m.notes.length ? h('ul', { class: 'ge-notes' }, m.notes.map((x) => h('li', null, x))) : null);
  }
  log.forEach((m) => list.appendChild(renderMsg(m)));
  if (!log.length && o.intro) list.appendChild(h('div', { class: 'ge-msg hint' }, h('div', { class: 'b' }, o.intro)));
  if (!log.length && (o.hints || []).length) list.appendChild(h('div', { class: 'ge-hints' }, o.hints.map((x) => h('button', { type: 'button', class: 'chip', onclick: () => { composer.setText(x); composer.focus(); } }, x))));
  list.scrollTop = list.scrollHeight;

  function progress() { // cartão de progresso da execução atual
    const card = h('div', { class: 'ge-prog' }), steps = h('div', { class: 'ge-steps' }), notes = h('div', { class: 'ge-pnotes' });
    card.append(steps, notes); list.appendChild(card); list.scrollTop = list.scrollHeight;
    const chips = {};
    return {
      card, start(ev) { steps.replaceChildren(...(ev.steps || []).map((s) => { const c = h('span', { class: 'ge-step', dataset: { id: s.id } }, h('i'), s.label); chips[s.id] = c; return c; })); if (ev.warning) notes.appendChild(h('div', { class: 'ge-pnote warn' }, ev.warning)); },
      step(ev) { let c = chips[ev.id]; if (!c) { c = chips[ev.id] = h('span', { class: 'ge-step', dataset: { id: ev.id } }, h('i'), ev.label); steps.appendChild(c); } c.className = 'ge-step ' + ev.status; if (ev.note) c.title = ev.note; },
      note(msg, cls) { notes.appendChild(h('div', { class: 'ge-pnote ' + (cls || '') }, msg)); list.scrollTop = list.scrollHeight; },
      done() { card.classList.add('done'); },
    };
  }
  async function run(text, ids) {
    if (!text.trim() && !(ids || []).length) return;
    addMsg('user', text.trim() || t('(anexos)') + ' ' + (ids || []).length);
    composer.setText('');
    if (o.intercept) { let handled = false; try { handled = await o.intercept(text, ids || [], { addMsg }); } catch (e) { addMsg('err', e.message); handled = true; } if (handled) { composer.clearFiles(); return; } }
    composer.setBusy(true, cancel);
    const body = Object.assign({ prompt: text, attachment_ids: ids || [], web, team: team.get() }, o.body ? o.body() : {});
    cur = progress();
    if (o.onStart) o.onStart();
    try { jobId = (await api(`${E.api.base}/${o.endpoint}`, { method: 'POST', body })).job_id; }
    catch (e) { if (e.status === 409 && e.data && e.data.job_id) jobId = e.data.job_id; else { finish(e.message); return; } }
    let result = null, failed = '';
    stop = events(`/api/jobs/${jobId}/events`, (ev) => {
      if (o.onEvent) o.onEvent(ev);
      if (ev.type === 'start') cur.start(ev);
      else if (ev.type === 'step') cur.step(ev);
      else if (ev.type === 'note') cur.note(ev.message);
      else if (ev.type === 'plan') cur.note('✦ ' + [ev.plan.title, ev.plan.kind && ev.plan.kind.toUpperCase(), ev.plan.genre && t(GENRE_LABEL[ev.plan.genre] || ev.plan.genre), ev.plan.theme && t(THEME_LABEL[ev.plan.theme] || ev.plan.theme)].filter(Boolean).join(' · '));
      else if (ev.type === 'sources') cur.note(t('Fontes da web: {n}', { n: ev.sources.length }) + ' — ' + ev.sources.slice(0, 3).map((s) => s.host).join(', '));
      else if (ev.type === 'result') result = ev.data;
      else if (ev.type === 'error') failed = ev.message || t('Erro');
      else if (ev.type === 'cancelled') failed = t('Cancelado.');
    }, () => finish(failed, result));
  }
  function finish(err, result) {
    stop = null; jobId = ''; composer.setBusy(false); composer.clearFiles();
    if (cur) cur.done(); cur = null;
    if (err) addMsg('err', err);
    if (result) {
      const rep = result.report || {};
      const notes = [].concat(rep.warning ? [rep.warning] : [], (rep.warnings || []).slice(0, 3), (result.problems || []).slice(0, 3));
      addMsg('ai', result.summary || t('Pronto.'), { html: true, notes });
      if (o.onResult) o.onResult(result);
    }
  }
  function cancel() { if (jobId) api('/api/jobs/' + jobId + '/cancel', { method: 'POST', body: {} }).catch(() => {}); }
  E.onCleanup(() => { if (stop) stop(); });

  const el = h('section', { class: 'ge-prompt', 'aria-label': o.title || t('Prompt') },
    h('div', { class: 'ge-ph' }, h('b', null, o.title || t('Prompt')), badge), list, composer.el);
  return { el, composer, addMsg, run, setPlaceholder: (p) => composer.configure({ placeholder: p }), team };
}

// ---- roda um job de IA e devolve o resultado (sem interface própria): usado por botões que agem sobre um trecho (Scripts, Map…)
export function runJob(E, endpoint, body, onStep) {
  return new Promise(async (resolve, reject) => {
    let jid = '';
    try { jid = (await api(`${E.api.base}/${endpoint}`, { method: 'POST', body })).job_id; }
    catch (e) { if (e.status === 409 && e.data && e.data.job_id) jid = e.data.job_id; else return reject(e); }
    let result = null, failed = '';
    const stop = events(`/api/jobs/${jid}/events`, (ev) => { if (onStep) onStep(ev); if (ev.type === 'result') result = ev.data; else if (ev.type === 'error') failed = ev.message || t('Erro'); else if (ev.type === 'cancelled') failed = t('Cancelado.'); }, () => (failed ? reject(new Error(failed)) : resolve(result)));
    E.onCleanup(stop);
  });
}

// ---- pequenos componentes
export function panel(title, body, right, cls) { return h('section', { class: 'ge-panel ' + (cls || '') }, title ? h('div', { class: 'ge-ph' }, h('b', null, title), right || null) : null, body); }
export function btn(label, ic, fn, cls, attrs) { return h('button', Object.assign({ type: 'button', class: 'btn sm ' + (cls || ''), onclick: fn }, attrs || {}), ic ? icon(ic, 14) : null, label ? h('span', null, label) : null); }
export function ibtn(title, ic, fn, cls, attrs) { return h('button', Object.assign({ type: 'button', class: 'btn ghost icon sm ' + (cls || ''), title, onclick: fn }, attrs || {}), icon(ic, 15)); }
export function propRow(label, control, hint) { return h('label', { class: 'ge-prop', title: hint || '' }, h('span', { class: 'l' }, label), control); }
export function numInput(value, onInput, o = {}) {
  const i = h('input', { type: 'number', value: value == null ? '' : value, step: o.step || 'any', min: o.min, max: o.max });
  i.addEventListener('input', () => { const v = parseFloat(i.value); if (!isNaN(v)) onInput(v); }); return i;
}
export const clone = deep;
export function fileInputButton(label, accept, onFiles, multiple = true) {
  const inp = h('input', { type: 'file', multiple, accept: accept || '', class: 'hidden' });
  inp.addEventListener('change', () => { if (inp.files.length) onFiles([...inp.files]); inp.value = ''; });
  return h('span', null, h('button', { type: 'button', class: 'btn sm', onclick: () => inp.click() }, icon('upload', 14), label), inp);
}
