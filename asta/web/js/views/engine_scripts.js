// Game Engine → Scripts: inspirada no Notepad Next. Roteiros, GDD, diálogos, lore e missões em Markdown/texto, com várias abas (em cima ou na vertical), painéis lado a lado ou empilhados,
// pastas e subpastas, e IA para melhorar/expandir/reescrever só o parágrafo ou a fala que você selecionar. Personagens e Worldbuilding (cartões) vivem aqui também.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { createEditor, langOf } from '../editor_core.js';
import { btn, flatFiles, fmtSize, ibtn, promptPanel, runJob } from '../engine_ui.js';
import { confirmDialog, h, icon, modal, popover, seg, toast } from '../ui.js';

const DOC_KINDS = [['roteiro', 'Roteiro'], ['gdd', 'Documento de design (GDD)'], ['dialogo', 'Diálogos'], ['lore', 'História do mundo (lore)'], ['quest', 'Missões'], ['personagem', 'Ficha de personagem'], ['livre', 'Livre']];
const AI_ACTIONS = [['improve', 'Melhorar'], ['expand', 'Expandir'], ['rewrite', 'Reescrever'], ['shorten', 'Encurtar'], ['fix', 'Corrigir'], ['dialogue', 'Virar diálogo'], ['translate', 'Traduzir']];
const LAYOUT_KEY = 'asta.ge.scripts.layout';

export default async function render(body, E) {
  let lay = { split: 'none', tabs: 'top' }; try { lay = Object.assign(lay, JSON.parse(localStorage.getItem(LAYOUT_KEY) || '{}')); } catch (e) { /* ok */ }
  const S = { tree: [], panes: [{ tabs: [], active: '' }], act: 0, folded: new Set(), sel: '', view: 'docs' };
  const saveLay = () => { try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(lay)); } catch (e) { /* ok */ } };
  const ext = (p) => String(p).split('.').pop().toLowerCase();
  const editors = new Map();   // paneIndex -> editor
  const dirOf = (p) => (p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '');
  const allTabs = () => S.panes.flatMap((p) => p.tabs);
  const findTab = (path) => allTabs().find((x) => x.path === path);

  // ---------------------------------------------------------------- árvore de pastas
  const explorer = h('div', { class: 'ge-files', id: 'ge-sfiles', role: 'tree', 'aria-label': t('Roteiros') });
  async function loadTree() { S.tree = (await E.api.tree('docs')).children; paintTree(); }
  function paintTree() {
    const rows = [];
    const walk = (nodes, depth) => nodes.forEach((n) => {
      const isDir = n.type === 'dir', open = !S.folded.has(n.path);
      const row = h('div', { class: 'ge-frow' + (S.sel === n.path ? ' on' : ''), dataset: { path: n.path, type: n.type }, draggable: 'true', style: { paddingLeft: 6 + depth * 13 + 'px' },
        onclick: () => { S.sel = n.path; if (isDir) { open ? S.folded.add(n.path) : S.folded.delete(n.path); paintTree(); } else { openDoc(n.path); paintTree(); } } },
        h('span', { class: 'fi' }, isDir ? icon(open ? 'chevd' : 'chevr', 12) : null), h('span', { class: 'fi' }, icon(isDir ? 'folder' : 'doc', 14)), h('span', { class: 'fn', title: n.path }, n.name), isDir ? null : h('span', { class: 'fs' }, fmtSize(n.size)));
      row.addEventListener('dragstart', (e) => e.dataTransfer.setData('text/plain', n.path));
      row.addEventListener('dragover', (e) => { e.preventDefault(); row.dataset.drop = 'in'; }); row.addEventListener('dragleave', () => { delete row.dataset.drop; });
      row.addEventListener('drop', async (e) => { e.preventDefault(); e.stopPropagation(); delete row.dataset.drop; const target = isDir ? n.path : dirOf(n.path), src = e.dataTransfer.getData('text/plain'); if (!src || dirOf(src) === target || src === target) return; try { const to = (target ? target + '/' : '') + src.split('/').pop(); await E.api.rename(src, to, 'docs'); allTabs().forEach((x) => { if (x.path === src) x.path = to; }); S.panes.forEach((p) => { if (p.active === src) p.active = to; }); await loadTree(); paintPanes(); } catch (err) { toast(err.message, 'err'); } });
      rows.push(row); if (isDir && open) walk(n.children || [], depth + 1);
    });
    walk(S.tree, 0);
    explorer.replaceChildren(...(rows.length ? rows : [h('div', { class: 'muted small', style: { padding: '10px' } }, t('Nenhum roteiro ainda. Crie um arquivo ou peça à IA.'))]));
  }
  const curDir = () => { const f = flatFiles(S.tree).find((x) => x.path === S.sel); return f ? dirOf(f.path) : S.sel || ''; };
  async function newDoc(preset) {
    const inp = h('input', { value: (curDir() ? curDir() + '/' : '') + (preset || 'novo') + '.md', id: 'ge-sn-name', 'aria-label': t('Caminho do arquivo') });
    if (await modal(t('Novo roteiro'), h('div', null, inp, h('p', { class: 'muted small' }, t('Formato padrão: .md (Markdown) ou .txt. Use «/» para subpastas.'))), [{ label: t('Cancelar'), value: null }, { label: t('Criar'), value: 'ok', cls: 'primary' }]) !== 'ok' || !inp.value.trim()) return;
    let path = inp.value.trim().replace(/^\/+/, ''); if (!/\.(md|txt|markdown)$/i.test(path)) path += '.md';
    try { await E.api.write(path, '# ' + path.split('/').pop().replace(/\.[^.]+$/, '') + '\n\n', 'docs'); await loadTree(); S.sel = path; await openDoc(path); } catch (e) { toast(e.message, 'err'); }
  }
  async function newFolder() { const inp = h('input', { value: (curDir() ? curDir() + '/' : '') + 'nova-pasta', id: 'ge-sd-name' }); if (await modal(t('Nova pasta'), inp, [{ label: t('Cancelar'), value: null }, { label: t('Criar'), value: 'ok', cls: 'primary' }]) !== 'ok' || !inp.value.trim()) return; try { await E.api.mkdir(inp.value.trim().replace(/^\/+/, ''), 'docs'); await loadTree(); } catch (e) { toast(e.message, 'err'); } }
  async function renameSel() { if (!S.sel) return; const inp = h('input', { value: S.sel }); if (await modal(t('Renomear / mover'), inp, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]) !== 'ok' || inp.value.trim() === S.sel) return; try { const to = inp.value.trim().replace(/^\/+/, ''); await E.api.rename(S.sel, to, 'docs'); allTabs().forEach((x) => { if (x.path === S.sel) x.path = to; }); S.panes.forEach((p) => { if (p.active === S.sel) p.active = to; }); S.sel = to; await loadTree(); paintPanes(); } catch (e) { toast(e.message, 'err'); } }
  async function deleteSel() { if (!S.sel) return; if (!(await confirmDialog(t('Apagar «{n}»? Se for uma pasta, tudo dentro dela também.', { n: S.sel })))) return; try { await E.api.remove(S.sel, 'docs'); S.panes.forEach((p) => { p.tabs = p.tabs.filter((x) => x.path !== S.sel && !x.path.startsWith(S.sel + '/')); if (!p.tabs.find((x) => x.path === p.active)) p.active = (p.tabs[0] || {}).path || ''; }); S.sel = ''; await loadTree(); paintPanes(); } catch (e) { toast(e.message, 'err'); } }

  // ---------------------------------------------------------------- abas e painéis
  async function openDoc(path, paneIdx) {
    const pi = paneIdx == null ? S.act : paneIdx; let tab = findTab(path);
    if (!tab) { try { const r = await E.api.read(path, 'docs'); if (r.type !== 'text') { toast(t('Este arquivo não é texto.'), 'err'); return; } tab = { path, content: r.content, orig: r.content, dirty: false }; } catch (e) { toast(e.message, 'err'); return; } }
    const pane = S.panes[pi]; if (!pane.tabs.includes(tab)) { S.panes.forEach((p) => { p.tabs = p.tabs.filter((x) => x !== tab); }); pane.tabs.push(tab); }
    pane.active = path; S.act = pi; paintPanes();
  }
  async function saveTab(tab, ed) { if (!tab) return; if (ed) tab.content = ed.get(); try { await E.api.write(tab.path, tab.content, 'docs'); tab.orig = tab.content; tab.dirty = false; paintPanes(); loadTree(); toast(t('Salvo: {p}', { p: tab.path }), 'ok'); } catch (e) { toast(e.message, 'err'); } }
  const panesEl = h('div', { class: 'ge-panes', id: 'ge-panes' });
  function paintPanes() {
    panesEl.className = 'ge-panes' + (lay.split === 'v' ? ' v' : ''); editors.clear();
    const count = lay.split === 'none' ? 1 : 2; while (S.panes.length < count) S.panes.push({ tabs: [], active: '' });
    if (S.panes.length > count) { S.panes[0].tabs.push(...S.panes[1].tabs.filter((x) => !S.panes[0].tabs.includes(x))); S.panes.length = count; if (S.act >= count) S.act = 0; }
    panesEl.replaceChildren(...S.panes.map((p, i) => paneEl(p, i)));
  }
  function paneEl(pane, idx) {
    const tabEls = pane.tabs.map((tb) => h('div', { class: 'ge-etab' + (tb.path === pane.active ? ' on' : ''), role: 'tab', dataset: { path: tb.path }, title: tb.path, onclick: () => { pane.active = tb.path; S.act = idx; paintPanes(); } },
      icon('doc', 13), h('span', null, tb.path.split('/').pop()), tb.dirty ? h('span', { class: 'dirty' }, '●') : null,
      S.panes.length > 1 ? h('span', { class: 'x', title: t('Mover para o outro painel'), onclick: (e) => { e.stopPropagation(); const other = S.panes[(idx + 1) % S.panes.length]; pane.tabs = pane.tabs.filter((x) => x !== tb); other.tabs.push(tb); other.active = tb.path; if (pane.active === tb.path) pane.active = (pane.tabs[0] || {}).path || ''; S.act = (idx + 1) % S.panes.length; paintPanes(); } }, '⇄') : null,
      h('span', { class: 'x', title: t('Fechar'), onclick: async (e) => { e.stopPropagation(); if (tb.dirty && !(await confirmDialog(t('«{n}» tem mudanças não salvas. Fechar mesmo assim?', { n: tb.path }), true, t('Fechar')))) return; pane.tabs = pane.tabs.filter((x) => x !== tb); if (pane.active === tb.path) pane.active = (pane.tabs[pane.tabs.length - 1] || {}).path || ''; paintPanes(); } }, '×')));
    const tabBar = h('div', { class: lay.tabs === 'left' ? 'ge-vtabs' : 'ge-etabs', id: 'ge-stabs-' + idx, role: 'tablist' }, tabEls);
    const tab = pane.tabs.find((x) => x.path === pane.active);
    const col = h('div', { class: 'pcol' });
    const stat = h('div', { class: 'ge-estatus' });
    if (tab) {
      const ed = createEditor({ value: tab.content, lang: langOf(tab.path), wrap: true, lineNumbers: false, spellcheck: true, label: tab.path, onChange: (v) => { tab.content = v; const d = v !== tab.orig; if (d !== tab.dirty) { tab.dirty = d; const dot = tabBar.querySelector('.ge-etab.on'); if (dot) { dot.querySelector('.dirty') ? dot.querySelector('.dirty').remove() : dot.insertBefore(h('span', { class: 'dirty' }, '●'), dot.children[2]); } } wordStat(); }, onSave: () => saveTab(tab, ed), onCursor: (c) => { const sp = stat.querySelector('.cur'); if (sp) sp.textContent = t('Linha {l}, col. {c}', { l: c.line, c: c.col }); } });
      editors.set(idx, ed);
      ed.ta.addEventListener('focus', () => { if (S.act !== idx) { S.act = idx; document.querySelectorAll('.ge-pane').forEach((el, k) => el.classList.toggle('act', k === idx)); } });
      ed.ta.addEventListener('mouseup', (e) => floatBar(ed, e)); ed.ta.addEventListener('keyup', (e) => { if (e.shiftKey || e.key === 'Shift') floatBar(ed, null); });
      const wordStat = () => { const v = ed.get(), words = (v.match(/[\p{L}\p{N}'’-]+/gu) || []).length; stat.querySelector('.wc').textContent = t('{w} palavras · {c} caracteres · {l} linhas', { w: words, c: v.length, l: v.split('\n').length }); };
      stat.append(h('span', { class: 'wc' }), h('span', { class: 'cur' }), h('span', { class: 'grow' }), h('span', null, tab.dirty ? t('não salvo') : t('salvo'))); setTimeout(wordStat, 0);
      col.append(aiBar(ed, tab), ed.el, stat);
    } else col.append(h('div', { class: 'empty', style: { margin: 'auto' } }, h('h3', null, t('Nenhum arquivo aberto')), h('p', null, t('Abra um roteiro na árvore, crie um novo ou gere um com o prompt.'))));
    const el = h('div', { class: 'ge-pane' + (lay.tabs === 'left' ? ' vt' : '') + (idx === S.act ? ' act' : ''), dataset: { pane: idx }, onmousedown: () => { S.act = idx; } });
    if (lay.tabs === 'left') el.append(tabBar, h('div', { class: 'pcol' }, ...col.childNodes)); else { const c2 = h('div', { class: 'pcol' }, tabBar, ...col.childNodes); el.append(c2); }
    return el;
  }

  // ---------------------------------------------------------------- IA sobre o trecho selecionado
  function paragraphRange(v, pos) { let s = v.lastIndexOf('\n\n', pos - 1); s = s < 0 ? 0 : s + 2; let e = v.indexOf('\n\n', pos); if (e < 0) e = v.length; return [s, e]; }
  function lineRange(v, pos) { const s = v.lastIndexOf('\n', pos - 1) + 1; let e = v.indexOf('\n', pos); if (e < 0) e = v.length; return [s, e]; }
  async function aiOn(ed, tab, action, instruction) {
    const sel = ed.selection(); if (!sel.text.trim()) { toast(t('Selecione um trecho (ou use «¶ Parágrafo» / «💬 Fala»).')); return; }
    const v = ed.get(), start = sel.start, end = sel.end; toast(t('A IA está trabalhando no trecho…'));
    try {
      const res = await runJob(E, 'script', { action, selection: sel.text, context: v.slice(Math.max(0, start - 700), Math.min(v.length, end + 700)), prompt: instruction || '', doc: tab.path, team: promptTeam() });
      if (!res || !res.text) { toast(t('A IA não devolveu texto.'), 'err'); return; }
      ed.replaceRange(start, end, res.text); (res.notes || []).slice(0, 2).forEach((n) => toast(n)); toast(t('Trecho atualizado (Ctrl+Z desfaz).'), 'ok');
    } catch (e) { toast(e.message, 'err'); }
  }
  const promptTeam = () => (pp && pp.team ? pp.team.get() : {});
  function aiBar(ed, tab) {
    const bar = h('div', { class: 'ge-aibar', dataset: { aibar: '1' } }, h('span', { class: 'lbl' }, 'IA'),
      btn(t('¶ Parágrafo'), '', () => { const [a, b] = paragraphRange(ed.get(), ed.selection().start); ed.select(a, b); }, '', { title: t('Seleciona o parágrafo onde está o cursor'), id: 'ge-sel-par' }), btn(t('💬 Fala'), '', () => { const [a, b] = lineRange(ed.get(), ed.selection().start); ed.select(a, b); }, '', { title: t('Seleciona a linha (fala/diálogo) do cursor'), id: 'ge-sel-line' }),
      ...AI_ACTIONS.map(([id, label]) => btn(t(label), '', () => aiOn(ed, tab, id), '', { dataset: { act: id } })), btn(t('Pedir…'), 'sparkle', async () => { const i = h('input', { placeholder: t('ex.: deixe mais sombrio, com humor, em primeira pessoa…'), id: 'ge-sai-ask' }); if (await modal(t('O que a IA deve fazer com o trecho?'), i, [{ label: t('Cancelar'), value: null }, { label: t('Aplicar'), value: 'ok', cls: 'primary' }]) === 'ok' && i.value.trim()) aiOn(ed, tab, 'rewrite', i.value.trim()); }),
      h('span', { class: 'grow' }), btn(t('Salvar'), 'check', () => saveTab(tab, ed), 'primary', { id: 'ge-ssave-doc' }), btn(t('Enviar diálogos ao jogo'), 'play', () => sendDialogues(ed.get()), '', { title: t('Lê «## id» e «Nome: fala» e grava em data/dialogues.json'), id: 'ge-sdlg' }));
    return bar;
  }
  let floatEl = null;
  function floatBar(ed, ev) {
    if (floatEl) { floatEl.remove(); floatEl = null; } const sel = ed.selection(); if (sel.text.trim().length < 4) return;
    const r = ed.ta.getBoundingClientRect(), x = ev ? ev.clientX : r.left + 40, y = ev ? ev.clientY : r.top + 40, tab = allTabs().find((z) => z.path === (S.panes[S.act] || {}).active);
    floatEl = h('div', { class: 'ge-float', style: { left: Math.min(innerWidth - 320, Math.max(8, x - 20)) + 'px', top: Math.max(8, y - 46) + 'px' }, onmousedown: (e) => e.preventDefault() }, ...[['improve', 'Melhorar'], ['expand', 'Expandir'], ['rewrite', 'Reescrever'], ['shorten', 'Encurtar']].map(([id, l]) => h('button', { type: 'button', dataset: { float: id }, onclick: () => { floatEl.remove(); floatEl = null; if (tab) aiOn(ed, tab, id); } }, t(l))));
    document.body.appendChild(floatEl); setTimeout(() => { const off = (e) => { if (floatEl && !floatEl.contains(e.target)) { floatEl.remove(); floatEl = null; document.removeEventListener('mousedown', off); } }; document.addEventListener('mousedown', off); }, 0);
  }
  E.onCleanup(() => { if (floatEl) floatEl.remove(); });
  async function sendDialogues(text) {
    const map = {}; let cur = '', n = 0;
    text.split('\n').forEach((line) => { const hd = /^#{1,6}\s+(.+?)\s*$/.exec(line); if (hd) { cur = hd[1].toLowerCase().replace(/[^\w-]+/g, '-').replace(/^-|-$/g, ''); return; } const m = /^\s*(?:[-*]\s*)?([^:#\n]{1,40}):\s+(.+)$/.exec(line); if (m && cur) { (map[cur] = map[cur] || []).push({ speaker: m[1].trim(), text: m[2].trim() }); n++; } });
    if (!n) { toast(t('Não achei diálogos. Use «## id» e, embaixo, linhas «Nome: fala».'), 'err'); return; }
    let cur2 = {}; try { cur2 = JSON.parse((await E.api.read('data/dialogues.json')).content); } catch (e) { /* novo */ }
    try { await E.api.write('data/dialogues.json', JSON.stringify(Object.assign(cur2, map), null, 2)); toast(t('{n} fala(s) em {k} diálogo(s) enviadas ao jogo (data/dialogues.json).', { n, k: Object.keys(map).length }), 'ok'); } catch (e) { toast(e.message, 'err'); }
  }

  // ---------------------------------------------------------------- prompt (gerar documentos)
  const gen = { doc: 'roteiro', dest: 'new' };
  const docSel = h('select', { class: 'team-sel', id: 'ge-sdoc', title: t('Tipo de documento'), 'aria-label': t('Tipo de documento') }, DOC_KINDS.map(([v, l]) => h('option', { value: v }, t(l)))); docSel.addEventListener('change', () => { gen.doc = docSel.value; });
  const destSel = h('select', { class: 'team-sel', id: 'ge-sdest', title: t('Onde colocar'), 'aria-label': t('Onde colocar') }, [['new', t('Novo arquivo')], ['cursor', t('No cursor do arquivo aberto')]].map(([v, l]) => h('option', { value: v }, l))); destSel.addEventListener('change', () => { gen.dest = destSel.value; });
  let pp = promptPanel(E, {
    tab: 'scripts', endpoint: 'script', title: t('Prompt de roteiro'), placeholder: t('Peça: “GDD do jogo”, “diálogos do mago com o herói”, “3 missões secundárias”, “a história do vilão”…'),
    intro: t('Escreva roteiros, GDD, diálogos, lore e missões com a IA — ou à mão. Selecione um trecho no editor para melhorar ou expandir só ele.'),
    hints: [t('Documento de design (GDD) deste jogo'), t('Diálogos do guia com o jogador'), t('Três missões secundárias curtas'), t('A história do vilão em um parágrafo')], tools: [h('span', { class: 'tool' }, docSel), h('span', { class: 'tool' }, destSel)],
    body: () => ({ action: 'generate', doc: gen.doc }),
    onResult: async (res) => {
      if (!res.text) return;
      const ed = editors.get(S.act), tab = findTab((S.panes[S.act] || {}).active);
      if (gen.dest === 'cursor' && ed && tab) { ed.insert('\n' + res.text + '\n'); toast(t('Texto inserido no cursor'), 'ok'); return; }
      let base = (res.title || gen.doc).replace(/[^\w-]+/g, '-').toLowerCase().slice(0, 30) || 'roteiro', path = (curDir() ? curDir() + '/' : '') + base + '.md', n = 2;
      const files = flatFiles(S.tree).map((f) => f.path); while (files.includes(path)) path = (curDir() ? curDir() + '/' : '') + base + '-' + (n++) + '.md';
      await E.api.write(path, res.text, 'docs'); await loadTree(); S.sel = path; await openDoc(path); toast(t('Criado: {p}', { p: path }), 'ok');
    },
  });

  // ---------------------------------------------------------------- montagem
  const viewSeg = seg([['docs', t('Roteiros')], ['characters', t('Personagens')], ['worldbuilding', t('Worldbuilding')]], S.view, (v) => { S.view = v; paintView(); });
  viewSeg.id = 'ge-sview';
  const mid = h('aside', { class: 'ge-mid', 'aria-label': t('Arquivos de roteiro') },
    h('div', { class: 'ge-ph' }, h('b', null, t('Roteiros'))),
    h('div', { class: 'ge-ftool' }, ibtn(t('Novo roteiro'), 'plus', () => newDoc(), '', { id: 'ge-snew' }), ibtn(t('Nova pasta'), 'folder', newFolder, '', { id: 'ge-sfolder' }), ibtn(t('Renomear / mover'), 'edit', renameSel), ibtn(t('Apagar'), 'trash', deleteSel, '', { id: 'ge-sdelete' }), ibtn(t('Atualizar'), 'refresh', () => loadTree())), explorer);
  const layoutBar = h('div', { class: 'ge-vtool' }, viewSeg, h('span', { class: 'grow' }),
    ibtn(t('Painel único'), 'panel', () => { lay.split = 'none'; saveLay(); paintPanes(); paintLayoutBtns(); }, '', { id: 'ge-lay-one' }), ibtn(t('Dividir lado a lado'), 'split', () => { lay.split = 'h'; saveLay(); paintPanes(); paintLayoutBtns(); }, '', { id: 'ge-lay-h' }), ibtn(t('Dividir um sobre o outro'), 'splitv', () => { lay.split = 'v'; saveLay(); paintPanes(); paintLayoutBtns(); }, '', { id: 'ge-lay-v' }),
    h('span', { class: 'sep', style: { width: '1px', height: '20px', background: 'var(--line2)' } }), ibtn(t('Abas em cima'), 'rowsmall', () => { lay.tabs = 'top'; saveLay(); paintPanes(); paintLayoutBtns(); }, '', { id: 'ge-tabs-top' }), ibtn(t('Abas na vertical'), 'columns', () => { lay.tabs = 'left'; saveLay(); paintPanes(); paintLayoutBtns(); }, '', { id: 'ge-tabs-left' }));
  const paintLayoutBtns = () => { [['ge-lay-one', lay.split === 'none'], ['ge-lay-h', lay.split === 'h'], ['ge-lay-v', lay.split === 'v'], ['ge-tabs-top', lay.tabs === 'top'], ['ge-tabs-left', lay.tabs === 'left']].forEach(([id, on]) => { const b = document.getElementById(id); if (b) b.classList.toggle('on', on); }); };
  const cards = h('div', { class: 'ge-cards', id: 'ge-cards' });
  const right = h('section', { class: 'ge-center', id: 'ge-sright' });
  const grid = h('div', { class: 'ge-grid ge-scripts' }, h('div', { class: 'ge-left' }, pp.el), mid, right);
  async function paintView() {
    const docs = S.view === 'docs'; mid.classList.toggle('hidden', !docs); grid.style.gridTemplateColumns = docs ? '' : '330px minmax(0,1fr)';
    if (docs) { right.replaceChildren(layoutBar, panesEl); paintPanes(); paintLayoutBtns(); return; }
    right.replaceChildren(layoutBar, cards); cards.replaceChildren(h('div', { class: 'spinner' }));
    try { const mod = await (S.view === 'characters' ? import('./characters.js') : import('./worldbuilding.js')); const holder = h('div'); cards.replaceChildren(holder); await mod.default(holder, {}); }
    catch (e) { cards.replaceChildren(h('div', { class: 'errbox' }, e.message)); }
  }
  body.replaceChildren(grid);
  E.onCleanup(() => { allTabs().filter((x) => x.dirty).forEach((x) => { const ed = [...editors.values()].find((z) => z && z.get && x.content === z.get()); E.api.write(x.path, ed ? ed.get() : x.content, 'docs').catch(() => {}); }); });
  await loadTree(); await paintView();
  const first = flatFiles(S.tree).find((f) => /gdd|roteiro/i.test(f.path)) || flatFiles(S.tree)[0]; if (first) openDoc(first.path);
}
