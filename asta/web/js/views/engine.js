// Game Engine — a seção que substitui «Mundos» e «Jogos 2D»: crie jogos 2D, 2.5D, 3D, VR e AR com IA. Inspirada no Godot.
// Rotas: #/engine (projetos) · #/engine/<projeto>/<aba> — abas: main · code · assets · sound · scripts · map · publish. #/engine/<aba> abre a aba no último projeto.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { go, state } from '../main.js';
import { BIOME_LABEL, GENRE_LABEL, KINDS, SIZE_LABEL, TABS, THEME_LABEL, catalog, openProject } from '../engine_ui.js';
import { teamPicker } from '../team_ui.js';
import { confirmDialog, fmtDate, h, icon, modal, popover, toast } from '../ui.js';
import { createComposer } from './composer.js';

const LAST = 'asta.engine.pid';
const TAB_IDS = TABS.map((x) => x[0]);
const TAB_MODULES = {
  main: () => import('./engine_main.js'), code: () => import('./engine_code.js'), assets: () => import('./engine_assets.js'), sound: () => import('./engine_sound.js'),
  scripts: () => import('./engine_scripts.js'), map: () => import('./engine_map.js'), publish: () => import('./engine_publish.js'),
};
let current = null;   // o editor aberto (estado E): as abas se limpam ao sair

function parse() {
  const m = location.hash.match(/^#\/engine(?:\/([\w-]+))?(?:\/([\w]+))?/);
  let pid = m && m[1] || '', tab = m && m[2] || '';
  if (pid && TAB_IDS.includes(pid) && !tab) { tab = pid; pid = ''; try { pid = localStorage.getItem(LAST) || ''; } catch (e) { /* ok */ } }
  return { pid, tab: TAB_IDS.includes(tab) ? tab : 'main' };
}

export default async function render(root, ctx) {
  if (current) { current.cleanup(); current = null; }
  const { pid, tab } = parse();
  if (!pid) return renderProjects(root, ctx);
  let E;
  try { E = await openProject(pid); }
  catch (e) { try { localStorage.removeItem(LAST); } catch (x) { /* ok */ } toast(e.message, 'err'); location.hash = '#/engine'; return; }
  try { localStorage.setItem(LAST, pid); } catch (e) { /* ok */ }
  current = E; E.tab = tab; E.ctx = ctx || {};
  const body = h('div', { class: 'ge-body', id: 'ge-body' });
  const nameEl = h('button', { class: 'ge-pname', type: 'button', title: t('Renomear o projeto'), onclick: rename }, h('b', null, E.proj.name), icon('edit', 12));
  async function rename() {
    const inp = h('input', { value: E.proj.name, maxlength: 60 });
    if (await modal(t('Renomear o projeto'), inp, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]) !== 'ok' || !inp.value.trim()) return;
    E.proj = await E.api.put('', { name: inp.value.trim() }); nameEl.firstChild.textContent = E.proj.name;
  }
  const menu = (anchor) => {
    const item = (label, ic, fn, cls) => h('div', { class: 'opt ' + (cls || ''), onclick: () => { pop.close(); fn(); } }, icon(ic, 15), label);
    const pop = popover(anchor, h('div', null,
      item(t('Salvar um ponto de retorno'), 'check', async () => { await E.api.post('/snapshot', { label: t('ponto de retorno manual') }); toast(t('Ponto de retorno salvo'), 'ok'); }),
      item(t('Histórico (desfazer mudanças da IA)'), 'undo', () => historyDialog(E)),
      item(t('Duplicar o projeto'), 'copy', async () => { const n = await E.api.post('/duplicate', {}); toast(t('Projeto duplicado'), 'ok'); location.hash = '#/engine/' + n.id + '/main'; }),
      item(t('Todos os projetos'), 'folder', () => { location.hash = '#/engine'; }),
      item(t('Apagar o projeto'), 'trash', async () => { if (await confirmDialog(t('Apagar «{n}» e todos os arquivos dele? Isso não pode ser desfeito.', { n: E.proj.name }))) { await api('/api/engine/projects/' + pid, { method: 'DELETE' }); try { localStorage.removeItem(LAST); } catch (e) { /* ok */ } location.hash = '#/engine'; } }, 'danger')));
  };
  const bar = h('header', { class: 'ge-bar' },
    h('a', { class: 'btn ghost icon sm', href: '#/engine', title: t('Todos os projetos'), 'aria-label': t('Todos os projetos') }, icon('arrow', 15)),
    nameEl, h('span', { class: 'chip ge-kind', id: 'ge-kind' }, E.proj.kind.toUpperCase()), h('span', { class: 'chip dim ge-genre' }, t(GENRE_LABEL[E.proj.genre] || E.proj.genre)),
    h('nav', { class: 'ge-tabs', role: 'tablist', 'aria-label': t('Abas do Game Engine') }, TABS.map(([id, label, ic]) => h('a', { class: 'ge-tab' + (tab === id ? ' on' : ''), href: `#/engine/${pid}/${id}`, role: 'tab', 'aria-selected': String(tab === id), dataset: { tab: id }, onclick: () => { state.ctx = {}; } }, icon(ic, 15), h('span', null, label)))),
    h('span', { class: 'grow' }),
    h('a', { class: 'btn sm', href: E.api.play('index.html'), target: '_blank', rel: 'noopener', id: 'ge-play-tab', title: t('Jogar em uma aba nova') }, icon('play', 13), t('Jogar')),
    h('button', { class: 'btn ghost icon sm', id: 'ge-menu', title: t('Mais'), type: 'button', onclick: (e) => menu(e.currentTarget) }, icon('more', 16)));
  root.replaceChildren(h('div', { class: 'ge-app', id: 'ge-app' }, bar, body));
  document.title = 'ASTA — ' + E.proj.name;
  try {
    const mod = await TAB_MODULES[tab]();
    await mod.default(body, E);
  } catch (e) { console.error(e); body.replaceChildren(h('div', { class: 'page narrow' }, h('div', { class: 'errbox' }, t('Algo deu errado:') + ' ' + (e.message || e)))); }
}

async function historyDialog(E) {
  const { items } = await E.api.get('/history');
  const list = h('div', { class: 'ge-hist' }, items.length ? items.map((it) => h('div', { class: 'ge-hrow' }, h('div', null, h('div', null, it.label || '—'), h('div', { class: 'small dim' }, it.t.replace('T', ' ').replace(/\+.*/, ''))),
    h('button', { class: 'btn sm', type: 'button', onclick: async () => { if (!(await confirmDialog(t('Voltar o jogo a este ponto? O estado atual também fica salvo no histórico.'), false, t('Voltar')))) return; await E.api.post('/history/restore', { id: it.id }); toast(t('Jogo restaurado'), 'ok'); document.querySelector('.modal-bg') && document.querySelector('.modal-bg').remove(); go('engine'); location.reload(); } }, icon('undo', 13), t('Voltar')))) : h('p', { class: 'muted' }, t('Ainda não há pontos de retorno. A IA salva um antes de cada mudança grande.')));
  await modal(t('Histórico'), list, [{ label: t('Fechar'), value: null }]);
}

// ============================================================================ lista de projetos + criar um jogo inteiro com um prompt
async function renderProjects(root, ctx) {
  const [{ projects }, cat, status] = await Promise.all([api('/api/engine/projects'), catalog(), api('/api/engine/status').catch(() => ({ text: {} }))]);
  const opt = { kind: '2d', genre: '', theme: '', length: 'medium', web: !!((state.settings || {}).engine || {}).web };
  const kindSeg = h('div', { class: 'ge-kinds', role: 'radiogroup', 'aria-label': t('Tipo de jogo') });
  const genreSel = h('select', { id: 'ge-new-genre', 'aria-label': t('Gênero') }), themeSel = h('select', { id: 'ge-new-theme', 'aria-label': t('Tema') }), lenSel = h('select', { id: 'ge-new-length', 'aria-label': t('Duração') }, Object.keys(SIZE_LABEL).map((k) => h('option', { value: k, selected: k === 'medium' }, t(SIZE_LABEL[k]))));
  const paintKinds = () => {
    kindSeg.replaceChildren(...KINDS.map(([id, label]) => h('button', { type: 'button', role: 'radio', 'aria-checked': String(opt.kind === id), class: 'ge-kindbtn' + (opt.kind === id ? ' on' : ''), dataset: { kind: id }, title: t(cat.kinds[id].hint), onclick: () => { opt.kind = id; opt.genre = ''; paintKinds(); } }, h('b', null, label), h('span', null, t(cat.kinds[id].hint)))));
    genreSel.replaceChildren(h('option', { value: '' }, t('Gênero: automático')), ...Object.entries(cat.genres).filter(([, g]) => g.kinds.includes(opt.kind)).map(([id]) => h('option', { value: id }, t(GENRE_LABEL[id] || id))));
    genreSel.value = opt.genre;
  };
  genreSel.addEventListener('change', () => { opt.genre = genreSel.value; });
  themeSel.append(h('option', { value: '' }, t('Tema: automático')), ...cat.themes.map((id) => h('option', { value: id }, t(THEME_LABEL[id] || id))));
  themeSel.addEventListener('change', () => { opt.theme = themeSel.value; }); lenSel.addEventListener('change', () => { opt.length = lenSel.value; });
  paintKinds();
  const team = teamPicker((state.settings || {}).engine || {}, null, { id: 'ge-new-team' });
  const webBtn = h('button', { class: 'tool' + (opt.web ? ' on' : ''), type: 'button', id: 'ge-new-web', title: t('Busca na web nativa: o resultado entra no contexto da IA'), 'aria-pressed': String(opt.web), onclick: () => { opt.web = !opt.web; webBtn.classList.toggle('on', opt.web); webBtn.setAttribute('aria-pressed', String(opt.web)); } }, icon('globe', 15), t('Web'));
  const composer = createComposer({ placeholder: t('Descreva o jogo que você quer criar — ou anexe roteiros, imagens, vídeos, ZIPs…'), tools: [webBtn, h('span', { class: 'tool' }, genreSel), h('span', { class: 'tool' }, themeSel), h('span', { class: 'tool' }, lenSel)], rightTools: [team.el], sendLabel: t('Criar jogo'), sendTitle: t('Criar o jogo inteiro'), onSend: create });
  composer.el.id = 'ge-new-composer';
  async function create({ text, ids }) {
    composer.setBusy(true, () => {});
    try {
      const name = (/["“”']([^"“”']{3,40})["“”']/.exec(text) || [])[1] || '';
      const p = await api('/api/engine/projects', { method: 'POST', body: { name: name || t('Novo jogo'), kind: opt.kind, genre: opt.genre, theme: opt.theme || 'forest', description: text.slice(0, 300), starter: false } });
      state.ctx = { autorun: { prompt: text, ids, kind: opt.kind, genre: opt.genre, theme: opt.theme, length: opt.length, web: opt.web, team: team.get() } };
      location.hash = '#/engine/' + p.id + '/main';
    } catch (e) { toast(e.message, 'err'); composer.setBusy(false); }
  }
  const aiNote = status.text && status.text.ai ? null : h('div', { class: 'errbox ge-ainote', style: { whiteSpace: 'normal' } }, t('Nenhuma IA configurada: o Game Engine cria o jogo com regras automáticas (já jogável). Configure um provedor em Configuração → Provedores para pedidos livres e detalhados.'));
  const grid = h('div', { class: 'proj-grid ge-projects', id: 'ge-projects' });
  const paint = () => grid.replaceChildren(...projects.map((p) => card(p)));
  const card = (p) => h('div', { class: 'proj ge-pcard', dataset: { pid: p.id } },
    h('a', { class: 'thumb', href: '#/engine/' + p.id + '/main', style: { background: `linear-gradient(180deg, ${p.colors[0]} 0%, ${p.colors[1]} 55%, ${p.colors[2]} 55%, ${p.colors[2]} 100%)` } }, h('span', { class: 'badge vb' }, p.kind.toUpperCase() + ' · ' + t(GENRE_LABEL[p.genre] || p.genre))),
    h('div', { class: 'bd' }, h('div', { class: 'nm', title: p.name }, p.name), h('div', { class: 'ds' }, p.description || ''), h('div', { class: 'dim small', style: { marginTop: 'auto' } }, fmtDate(p.updated) + ' · ' + t('{n} cena(s)', { n: p.scenes }))),
    h('div', { class: 'ft' }, h('a', { class: 'btn sm primary', href: '#/engine/' + p.id + '/main' }, icon('engine', 13), t('Abrir')), h('a', { class: 'btn sm', href: `/api/engine/play/${p.id}/index.html`, target: '_blank', rel: 'noopener' }, icon('play', 13), t('Jogar')), h('span', { class: 'grow' }),
      h('button', { class: 'btn ghost icon sm', type: 'button', title: t('Apagar'), onclick: async () => { if (await confirmDialog(t('Apagar «{n}» e todos os arquivos dele? Isso não pode ser desfeito.', { n: p.name }))) { await api('/api/engine/projects/' + p.id, { method: 'DELETE' }); projects.splice(projects.indexOf(p), 1); paint(); } } }, icon('trash', 14))));
  paint();
  root.replaceChildren(h('div', { class: 'page ge-home' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'Game Engine'), h('p', null, t('Crie jogos 2D, 2.5D, 3D, VR e AR com IA: descreva, ajuste a cena como no Godot, edite código, arte, som, roteiros e mapas, e exporte para Windows, macOS, Linux, Android e iOS.')))),
    h('div', { class: 'ge-newcard' }, kindSeg, composer.el), aiNote,
    projects.length ? h('h2', { class: 'ge-h2' }, t('Seus jogos')) : h('div', { class: 'empty' }, h('h3', null, t('Crie seu primeiro jogo')), h('p', null, t('Escreva o que você imagina, escolha o tipo (2D, 2.5D, 3D, VR ou AR) e o ASTA monta um jogo completo e jogável. Depois é só ajustar.'))),
    projects.length ? grid : null));
}
