import { api } from './api.js';
import { setLang, t } from './i18n.js';
import { applyUi, ui } from './prefs.js';
import { installShell, maybeWelcome } from './shell.js';
import { h, icon, toast } from './ui.js';
import { initMobile, isMobile, offerUpdate } from './mobile.js';
import { computerStatus, subscribe as subscribeComputer } from './computer_ui.js';
import { codeStatus, subscribe as subscribeCode } from './code_ui.js';

// Estado global compartilhado entre as telas
export const state = { settings: null, presets: [], hardware: {}, version: '', home: '', ctx: {} };

export const NAV = [
  ['main', 'Chat', 'main'], ['worlds', 'Mundos', 'worlds'], ['avatars', 'Avatars', 'avatars'], ['games', 'Jogos 2D', 'games'], ['canvas', 'Canvas', 'canvas'], ['studio', 'Studio', 'film'], ['computer', 'Computer Use', 'computer'], ['code', 'Code', 'code'], ['rebuild', 'Rebuild', 'refresh'],
  ['library', 'Biblioteca', 'library'], ['config', 'Configuração', 'config'],
];
const VIEWS = {
  main: () => import('./views/chat.js'), worlds: () => import('./views/worlds.js'),
  library: () => import('./views/library.js'), config: () => import('./views/config.js'),
  avatars: () => import('./views/avatars.js'), games: () => import('./views/games.js'), rebuild: () => import('./views/rebuild.js'), studio: () => import('./views/studio.js'), canvas: () => import('./views/canvas.js'), computer: () => import('./views/computer.js'), code: () => import('./views/code.js'),
};

// Recarrega a página (uma vez por falha: sem laço se o problema continuar). Devolve true se recarregou.
function reloadPage(force) {
  try {
    const last = Number(sessionStorage.getItem('asta.reload') || 0);
    if (!force && Date.now() - last < 30000) return false;
    sessionStorage.setItem('asta.reload', String(Date.now()));
  } catch (e) { if (!force) return false; }
  location.reload();
  return true;
}

export function go(route, ctx) {
  state.ctx = ctx || {};
  if (location.hash === '#/' + route) render(); else location.hash = '#/' + route;
}
export const presetOf = (id) => { const p = state.presets.find((x) => x.id === id) || { label: id }; return Object.assign({}, p, { label: t(p.label) }); };
export async function refreshState() {
  const s = await api('/api/state');
  // o servidor foi reiniciado numa versão nova com esta página aberta: os módulos da página (já carregados) não combinam mais com os do servidor
  if (state.version && s.version && s.version !== state.version) { if (isMobile()) { offerUpdate(s.version); } else { reloadPage(); return s; } }   // no celular pergunta antes de atualizar
  Object.assign(state, { settings: s.settings, presets: s.presets, hardware: s.hardware, native: s.native || {}, version: s.version, diskVersion: s.disk_version || '', home: s.home });
  setLang(state.settings.language);
  applyUi(state.settings.ui);  // aparência (tema, cor, escala…) vinda do servidor; o cache local já pintou a tela no primeiro quadro
  return s;
}
export async function saveSettings(patch) {
  state.settings = await api('/api/settings', { method: 'PUT', body: patch });
  if ((state.settings.computer || {}).enabled) watchComputer();
  setLang(state.settings.language);
  applyUi(state.settings.ui);
  renderSide();
  return state.settings;
}

function route() {
  const old = location.hash.match(/^#\/(characters|worldbuilding)\b/);  // links antigos: agora vivem dentro de Mundos
  if (old) history.replaceState(null, '', '#/worlds/' + old[1]);
  if (/^#\/chat\b/.test(location.hash)) history.replaceState(null, '', '#/main');   // apelido: #/chat = tela Chat
  const m = location.hash.match(/^#\/(\w+)/); return m && VIEWS[m[1]] ? m[1] : 'main'; }

export function renderSide() {
  const side = document.getElementById('side');
  const cur = route();
  const collapsed = localStorage.getItem('asta.side') === '1';
  side.classList.toggle('collapsed', collapsed);
  const gen = state.settings ? state.settings.active.generation : 'demo';
  const demo = gen === 'demo';
  const stale = state.diskVersion && state.diskVersion !== state.version;   // há uma versão mais nova instalada do que a que está rodando
  side.replaceChildren(
    h('div', { class: 'brand', title: 'ASTA', onclick: () => go('main', {}) }, h('span', { class: 'logo' }, 'A'), h('span', { class: 'word' }, 'ASTA')),
    h('button', { class: 'searchbtn', type: 'button', title: t('Buscar (Ctrl+K)'), onclick: () => shell && shell.openPalette() }, icon('search', 16), h('span', null, t('Buscar…')), h('span', { class: 'kbd' }, 'Ctrl K')),
    h('nav', { 'aria-label': t('Telas') }, NAV.filter(([id]) => id === cur || !(ui().sidebar_hidden || []).includes(id)).map(([id, label, ic]) => h('a', { class: 'item' + (cur === id ? ' active' : ''), href: '#/' + id, title: t(label), 'aria-current': cur === id ? 'page' : null, onclick: () => { state.ctx = {}; } }, icon(ic, 19), h('span', { class: 'lbl' }, t(label)), id === 'computer' ? computerBadge() : id === 'code' ? codeBadge() : null))),
    h('div', { class: 'foot' },
      h('div', { class: 'chipstat', title: t('Provedor de geração'), onclick: () => go('config', { tab: 'providers' }) }, h('span', { class: 'dot ' + (demo ? 'warn' : 'ok') }), h('span', { class: 't' }, presetOf(gen).label)),
      stale ? h('div', { class: 'small t', style: { padding: '4px', color: 'var(--warn, #f5b942)' } }, t('Versão {v} instalada: feche o ASTA e abra de novo.', { v: state.diskVersion })) : null,
      h('div', { class: 'row', style: { justifyContent: 'space-between', padding: '0 4px' } },
        h('span', { class: 'dim small t' }, 'v' + state.version),
        h('button', { class: 'btn ghost icon sm', title: t('Recolher menu'), onclick: () => { localStorage.setItem('asta.side', collapsed ? '0' : '1'); renderSide(); } }, icon('panel', 16)))));
}

// Selo do Computer Use na barra lateral: quantas tarefas esperam a sua resposta (laranja) ou estão rodando (azul). Atualiza sozinho pelos eventos ao vivo.
function computerBadge() {
  const s = computerStatus(), n = (s.waiting || 0), r = (s.running || 0) + (s.queued || 0);
  const b = h('span', { class: 'cu-badge' + (n ? ' ask' : r ? ' run' : ' hidden'), id: 'cu-badge', title: n ? t('Aguardando você') : t('Em execução') }, String(n || r || ''));
  return b;
}
// Selo do Code na barra lateral: sessões esperando a sua resposta (laranja) ou trabalhando em segundo plano (azul). Atualiza sozinho pelos eventos ao vivo.
function codeBadge() {
  const s = codeStatus(), n = s.waiting || 0, r = (s.running || 0) + (s.queued || 0);
  return h('span', { class: 'cu-badge' + (n ? ' ask' : r ? ' run' : ' hidden'), id: 'cd-badge', title: n ? t('Aguardando você') : t('Em execução') }, String(n || r || ''));
}
function watchCode() {
  if (watchCode.on) return;
  watchCode.on = true;
  subscribeCode((ev) => {
    if (!ev.status && ev.type !== 'status') return;
    const s = codeStatus(), b = document.getElementById('cd-badge');
    if (!b) return;
    const n = s.waiting || 0, r = (s.running || 0) + (s.queued || 0);
    b.className = 'cu-badge' + (n ? ' ask' : r ? ' run' : ' hidden');
    b.textContent = String(n || r || '');
    b.title = n ? t('Aguardando você') : t('Em execução');
  });
}
function watchComputer() {
  if (watchComputer.on) return;
  watchComputer.on = true;
  subscribeComputer((ev) => {
    if (!ev.status && ev.type !== 'status') return;
    const s = computerStatus(), b = document.getElementById('cu-badge');
    if (!b) return;
    const n = s.waiting || 0, r = (s.running || 0) + (s.queued || 0);
    b.className = 'cu-badge' + (n ? ' ask' : r ? ' run' : ' hidden');
    b.textContent = String(n || r || '');
    b.title = n ? t('Aguardando você') : t('Em execução');
  });
}

let renderToken = 0;
async function render() {
  const token = ++renderToken, r = route(), main = document.getElementById('main');
  document.title = 'ASTA — ' + t((NAV.find(([id]) => id === r) || [0, 'Chat'])[1]);
  try { localStorage.setItem('asta.last', r); } catch (e) { /* ok */ }
  renderSide();
  main.replaceChildren(h('div', { class: 'page' }, h('div', { class: 'spinner' })));
  let mod;
  try { mod = await VIEWS[r](); }
  catch (e) {
    // Não deu para carregar os arquivos da tela (ex.: o ASTA foi atualizado com esta página aberta e ela ficou com arquivos de outra versão).
    // Recarregar resolve; se já recarregamos e continua falhando, explica o que fazer em vez de mostrar só o erro técnico.
    console.error(e);
    if (reloadPage()) return;
    if (token !== renderToken) return;
    main.replaceChildren(h('div', { class: 'page narrow' }, h('div', { class: 'errbox' },
      h('p', { style: { margin: '0 0 8px' } }, t('Não foi possível carregar esta tela. Isso costuma acontecer quando o ASTA é atualizado com a página aberta.')),
      h('p', { class: 'small', style: { margin: '0 0 12px' } }, t('Recarregue a página (Ctrl+F5). Se continuar, feche o ASTA, abra de novo com o comando asta e recarregue.')),
      h('p', { class: 'small', style: { margin: '0 0 12px' } }, t('Também pode ser uma extensão de bloqueio de anúncios ou rastreadores barrando um arquivo do ASTA: desative-a para este endereço (localhost) e recarregue.')),
      h('p', { class: 'mono small dim', style: { margin: '0 0 12px' } }, String((e && e.message) || e)),
      h('button', { class: 'btn primary', onclick: () => reloadPage(true) }, t('Recarregar a página')))));
    return;
  }
  try {
    if (token !== renderToken) return;
    const root = h('div');
    main.replaceChildren(root);
    main.scrollTop = 0;
    await mod.default(root, state.ctx || {});
  } catch (e) {
    console.error(e);
    main.replaceChildren(h('div', { class: 'page narrow' }, h('div', { class: 'errbox' }, t('Algo deu errado:') + ' ' + (e.message || e))));
  }
}

let shell = null;
addEventListener('asta:go', (e) => { if (e.detail && e.detail.route) go(e.detail.route, e.detail.ctx); });   // telas que não importam o main.js pedem navegação por evento
addEventListener('hashchange', () => { render(); });
(async () => {
  try { await refreshState(); } catch (e) { document.getElementById('main').replaceChildren(h('div', { class: 'page narrow' }, h('div', { class: 'errbox' }, e.message))); return; }
  const skip = document.querySelector('.skip');
  if (skip) { skip.textContent = t('Ir para o conteúdo'); skip.addEventListener('click', (e) => { e.preventDefault(); const m = document.getElementById('main'); if (m) m.focus(); }); }
  const app = { state, NAV, go, saveSettings, renderSide, refreshState };
  shell = installShell(app);
  // tela inicial preferida (só quando o ASTA abre sem um endereço específico)
  if (!location.hash || location.hash === '#' || location.hash === '#/') {
    const start = ui().start_page === 'last' ? (localStorage.getItem('asta.last') || 'main') : ui().start_page;
    if (start && start !== 'main' && VIEWS[start]) location.hash = '#/' + start;
  }
  render();
  watchCode();
  if ((state.settings.computer || {}).enabled) watchComputer();   // só conecta nos eventos do Computer Use se o recurso opcional estiver ligado
  maybeWelcome(app).catch((e) => console.error(e));
  initMobile(state.version);
})();
window.ASTA_WELCOME = () => maybeWelcome({ state, NAV, go, saveSettings, renderSide, refreshState }, true);
