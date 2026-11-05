import { api } from './api.js';
import { setLang, t } from './i18n.js';
import { h, icon, toast } from './ui.js';

// Estado global compartilhado entre as telas
export const state = { settings: null, presets: [], hardware: {}, version: '', home: '', ctx: {} };

export const NAV = [
  ['main', 'Principal', 'main'], ['worlds', 'Mundos', 'worlds'], ['avatars', 'Avatars', 'avatars'], ['games', 'Jogos 2D', 'games'], ['canvas', 'Canvas', 'canvas'],
  ['library', 'Biblioteca', 'library'], ['config', 'Configuração', 'config'],
];
const VIEWS = {
  main: () => import('./views/home.js'), worlds: () => import('./views/worlds.js'),
  library: () => import('./views/library.js'), config: () => import('./views/config.js'),
  avatars: () => import('./views/avatars.js'), games: () => import('./views/games.js'), canvas: () => import('./views/canvas.js'),
};

export function go(route, ctx) {
  state.ctx = ctx || {};
  if (location.hash === '#/' + route) render(); else location.hash = '#/' + route;
}
export const presetOf = (id) => { const p = state.presets.find((x) => x.id === id) || { label: id }; return Object.assign({}, p, { label: t(p.label) }); };
export async function refreshState() {
  const s = await api('/api/state');
  Object.assign(state, { settings: s.settings, presets: s.presets, hardware: s.hardware, version: s.version, home: s.home });
  setLang(state.settings.language);
  return s;
}
export async function saveSettings(patch) {
  state.settings = await api('/api/settings', { method: 'PUT', body: patch });
  setLang(state.settings.language);
  renderSide();
  return state.settings;
}

function route() {
  const old = location.hash.match(/^#\/(characters|worldbuilding)\b/);  // links antigos: agora vivem dentro de Mundos
  if (old) history.replaceState(null, '', '#/worlds/' + old[1]);
  const m = location.hash.match(/^#\/(\w+)/); return m && VIEWS[m[1]] ? m[1] : 'main'; }

export function renderSide() {
  const side = document.getElementById('side');
  const cur = route();
  const collapsed = localStorage.getItem('asta.side') === '1';
  side.classList.toggle('collapsed', collapsed);
  const gen = state.settings ? state.settings.active.generation : 'demo';
  const demo = gen === 'demo';
  side.replaceChildren(
    h('div', { class: 'brand', title: 'ASTA', onclick: () => go('main', {}) }, h('span', { class: 'logo' }, 'A'), h('span', { class: 'word' }, 'ASTA')),
    h('nav', null, NAV.map(([id, label, ic]) => h('a', { class: 'item' + (cur === id ? ' active' : ''), href: '#/' + id, title: t(label), onclick: () => { state.ctx = {}; } }, icon(ic, 19), h('span', { class: 'lbl' }, t(label))))),
    h('div', { class: 'foot' },
      h('div', { class: 'chipstat', title: t('Provedor de geração'), onclick: () => go('config', { tab: 'providers' }) }, h('span', { class: 'dot ' + (demo ? 'warn' : 'ok') }), h('span', { class: 't' }, presetOf(gen).label)),
      h('div', { class: 'row', style: { justifyContent: 'space-between', padding: '0 4px' } },
        h('span', { class: 'dim small t' }, 'v' + state.version),
        h('button', { class: 'btn ghost icon sm', title: t('Recolher menu'), onclick: () => { localStorage.setItem('asta.side', collapsed ? '0' : '1'); renderSide(); } }, icon('panel', 16)))));
}

let renderToken = 0;
async function render() {
  const token = ++renderToken, r = route(), main = document.getElementById('main');
  renderSide();
  main.replaceChildren(h('div', { class: 'page' }, h('div', { class: 'spinner' })));
  try {
    const mod = await VIEWS[r]();
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

addEventListener('hashchange', () => { render(); });
(async () => {
  try { await refreshState(); } catch (e) { document.getElementById('main').replaceChildren(h('div', { class: 'page narrow' }, h('div', { class: 'errbox' }, e.message))); return; }
  render();
})();
