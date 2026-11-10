// Work → Quadro: o quadro branco da empresa. Cargos, pessoas, notas e agentes de IA viram cartões; setores viram caixas (com os arquivos dentro); ligações mostram quem reporta
// a quem e por onde o trabalho passa. Arrastar move, a roda do mouse dá zoom, arrastar o fundo desloca, e a bolinha de baixo de cada cartão puxa uma ligação.
import { api, avatarEl, EDGE_KIND, h, icon, NODE_KIND, roleOf, t, toast } from '../work_ui.js';
import { confirmDialog, field, fill, modal, select } from '../ui.js';
import { teamPicker } from '../team_ui.js';
import { state } from '../main.js';

const NW = 190, NH = 70;   // o mesmo tamanho de asta/work/board.py
const COLORS = ['#3e9bff', '#f5a524', '#30a46c', '#e5484d', '#a78bfa', '#06b6d4', '#ec4899', '#84cc16', '#8b8b94'];
const SVGNS = 'http://www.w3.org/2000/svg';
const sv = (tag, attrs) => { const el = document.createElementNS(SVGNS, tag); Object.entries(attrs || {}).forEach(([k, v]) => el.setAttribute(k, v)); return el; };

export default async function render(box, W) {
  const S = { nodes: [], edges: [], folders: [], sel: null, zoom: 1, pan: { x: 80, y: 60 }, canEdit: false, fitted: false };
  const stage = h('div', { class: 'wk-stage', id: 'wk-stage', tabindex: '0' });
  const world = h('div', { class: 'wk-world' });
  const svg = sv('svg', { class: 'wk-edges', width: '1', height: '1' });
  svg.innerHTML = '<defs><marker id="wk-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" fill="currentColor"/></marker></defs>';
  const edgeLayer = sv('g', {}); svg.appendChild(edgeLayer);
  const folderLayer = h('div', { class: 'wk-layer' }), nodeLayer = h('div', { class: 'wk-layer' });
  world.append(folderLayer, svg, nodeLayer);
  const empty = h('div', { class: 'wk-empty hidden' }, h('b', null, t('O quadro está vazio')), h('span', null, t('Use «Preencher com as pessoas» para começar com a sua equipe, «Criar com IA» para desenhar a empresa a partir de uma descrição, ou adicione cartões pela barra de cima.')));
  stage.append(world, empty);
  const inspector = h('aside', { class: 'wk-insp', id: 'wk-insp' });
  const tool = (label, ic, fn, id, cls = '') => h('button', { class: 'btn sm ' + cls, type: 'button', id, onclick: fn, title: label }, icon(ic, 14), h('span', { class: 'lbl' }, label));
  const bar = h('div', { class: 'wk-toolbar' });
  box.replaceChildren(bar, h('div', { class: 'wk-board' }, stage, inspector));

  // ------------------------------------------------------------------ dados
  async function load(keepSel = true) {
    const r = await api('/api/work/board');
    S.nodes = r.nodes; S.edges = r.edges; S.folders = r.folders; S.canEdit = r.can_edit;
    if (!keepSel || (S.sel && !find(S.sel))) S.sel = null;
    paintBar(); paint();
    if (!S.fitted && (S.nodes.length || S.folders.length)) { S.fitted = true; fit(); }
  }
  const find = (sel) => sel.kind === 'node' ? S.nodes.find((n) => n.id === sel.id) : sel.kind === 'edge' ? S.edges.find((e) => e.id === sel.id) : S.folders.find((f) => f.id === sel.id);
  const nodeById = (id) => S.nodes.find((n) => n.id === id);
  const put = async (kind, id, body) => api(`/api/work/${kind}/${id}`, { method: 'PUT', body });
  const guard = async (fn) => { try { return await fn(); } catch (e) { toast(e.message, 'err'); await load(); return null; } };

  // ------------------------------------------------------------------ desenho
  const applyView = () => { world.style.transform = `translate(${S.pan.x}px,${S.pan.y}px) scale(${S.zoom})`; stage.style.backgroundSize = `${28 * S.zoom}px ${28 * S.zoom}px`; stage.style.backgroundPosition = `${S.pan.x}px ${S.pan.y}px`; };
  function nodeEl(n) {
    const u = n.kind === 'person' ? W.dir.users.find((x) => x.id === n.ref) : null;
    const role = n.kind === 'role' ? W.dir.roles.find((r) => r.id === n.ref) : null;
    const el = h('div', { class: 'wk-node k-' + n.kind + (S.sel && S.sel.kind === 'node' && S.sel.id === n.id ? ' sel' : ''), dataset: { id: n.id, kind: n.kind }, style: { left: n.x + 'px', top: n.y + 'px', width: NW + 'px', height: NH + 'px', '--c': n.color } },
      u ? avatarEl(u, 34) : h('span', { class: 'wk-ni' }, icon({ role: 'lock', sector: 'folder', note: 'doc', ai: 'sparkle', person: 'user' }[n.kind] || 'doc', 18)),
      h('span', { class: 'grow wk-nt' }, h('b', null, n.label || (u && u.display_name) || (role && role.name) || t('Cartão')), h('span', { class: 'small dim' }, n.kind === 'person' && u ? roleOf(W.dir, u).name : n.text || NODE_KIND()[n.kind])),
      S.canEdit ? h('span', { class: 'wk-handle', title: t('Arraste até outro cartão para ligar') }) : null);
    el.addEventListener('pointerdown', (e) => onNodeDown(e, n, el));
    el.addEventListener('dblclick', () => { if (n.kind === 'person' && n.ref) W.go('people', n.ref); else if (n.kind === 'sector' && n.ref) W.go('files', n.ref); });
    return el;
  }
  function folderEl(f) {
    const el = h('div', { class: 'wk-folder' + (S.sel && S.sel.kind === 'folder' && S.sel.id === f.id ? ' sel' : ''), dataset: { id: f.id }, style: { left: f.x + 'px', top: f.y + 'px', width: f.w + 'px', height: f.h + 'px', '--c': f.color } },
      h('div', { class: 'wk-fh' }, icon('folder', 15), h('b', null, f.name), (f.access || {}).mode === 'restricted' ? icon('lock', 12) : null),
      S.canEdit && W.can('folders.manage') ? h('span', { class: 'wk-resize', title: t('Redimensionar') }) : null);
    el.addEventListener('pointerdown', (e) => onFolderDown(e, f, el));
    el.addEventListener('dblclick', () => W.go('files', f.id));
    return el;
  }
  function edgeEls(e) {
    const a = nodeById(e.from), b = nodeById(e.to);
    if (!a || !b) return [];
    const ca = { x: a.x + NW / 2, y: a.y + NH / 2 }, cb = { x: b.x + NW / 2, y: b.y + NH / 2 };
    const clip = (c, other) => {   // ponto em que a linha sai da borda do cartão
      const dx = other.x - c.x, dy = other.y - c.y;
      if (!dx && !dy) return c;
      const k = Math.min(dx ? (NW / 2) / Math.abs(dx) : 1e9, dy ? (NH / 2) / Math.abs(dy) : 1e9);
      return { x: c.x + dx * k, y: c.y + dy * k };
    };
    const p1 = clip(ca, cb), p2 = clip(cb, ca);
    const sel = S.sel && S.sel.kind === 'edge' && S.sel.id === e.id;
    const g = sv('g', { class: 'wk-edge e-' + e.kind + (sel ? ' sel' : ''), 'data-id': e.id });
    g.append(sv('line', { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, class: 'wk-hit' }), sv('line', { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, class: 'wk-line', 'marker-end': 'url(#wk-arrow)' }));
    if (e.label) { const tx = sv('text', { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 - 6, 'text-anchor': 'middle', class: 'wk-elabel' }); tx.textContent = e.label; g.append(tx); }
    g.addEventListener('pointerdown', (ev) => { ev.stopPropagation(); choose({ kind: 'edge', id: e.id }); });
    return [g];
  }
  function paint() {
    fill(folderLayer, ...S.folders.map(folderEl));
    fill(nodeLayer, ...S.nodes.map(nodeEl));
    edgeLayer.replaceChildren(...S.edges.flatMap(edgeEls));
    empty.classList.toggle('hidden', !!(S.nodes.length || S.folders.length));
    paintInspector(); applyView();
  }
  function paintBar() {
    const edit = S.canEdit;
    fill(bar,
      edit ? [tool(t('Pessoa'), 'user', () => addCard('person'), 'wk-add-person'), tool(t('Cargo'), 'lock', () => addCard('role'), 'wk-add-role'), W.can('folders.manage') ? tool(t('Setor'), 'folder', addSector, 'wk-add-sector') : null,
        tool(t('Nota'), 'doc', () => addCard('note'), 'wk-add-note'), tool(t('Agente de IA'), 'sparkle', () => addCard('ai'), 'wk-add-ai'), h('span', { class: 'wk-sep' }),
        tool(t('Organizar'), 'columns', () => guard(async () => { const r = await api('/api/work/board/layout', { method: 'POST', body: {} }); Object.assign(S, { nodes: r.nodes, edges: r.edges }); paint(); fit(); }), 'wk-layout'),
        tool(t('Preencher com as pessoas'), 'characters', () => guard(async () => { const r = await api('/api/work/board/autofill', { method: 'POST', body: {} }); Object.assign(S, { nodes: r.nodes, edges: r.edges, folders: r.folders }); paint(); fit(); }), 'wk-autofill'),
        W.can('ai.use') ? tool(t('Criar com IA'), 'wand', aiDialog, 'wk-ai-flow', 'primary') : null, h('span', { class: 'wk-sep' })] : h('span', { class: 'chip', id: 'wk-readonly' }, icon('eye', 12), t('Somente leitura')),
      tool(t('Menos zoom'), 'zoomout', () => zoomBy(1 / 1.2), 'wk-zoom-out'), tool(t('Mais zoom'), 'zoomin', () => zoomBy(1.2), 'wk-zoom-in'), tool(t('Ajustar à tela'), 'fit', fit, 'wk-fit'));
  }

  // ------------------------------------------------------------------ pan, zoom
  const toWorld = (cx, cy) => { const r = stage.getBoundingClientRect(); return { x: (cx - r.left - S.pan.x) / S.zoom, y: (cy - r.top - S.pan.y) / S.zoom }; };
  function zoomBy(k, cx, cy) {
    const r = stage.getBoundingClientRect(); cx = cx ?? r.left + r.width / 2; cy = cy ?? r.top + r.height / 2;
    const w = toWorld(cx, cy), z = Math.max(0.2, Math.min(2.5, S.zoom * k));
    S.pan.x = cx - r.left - w.x * z; S.pan.y = cy - r.top - w.y * z; S.zoom = z; applyView();
  }
  function fit() {
    const items = [...S.nodes.map((n) => ({ x: n.x, y: n.y, w: NW, h: NH })), ...S.folders.map((f) => ({ x: f.x, y: f.y, w: f.w, h: f.h }))];
    if (!items.length) { S.pan = { x: 80, y: 60 }; S.zoom = 1; applyView(); return; }
    const x0 = Math.min(...items.map((i) => i.x)), y0 = Math.min(...items.map((i) => i.y)), x1 = Math.max(...items.map((i) => i.x + i.w)), y1 = Math.max(...items.map((i) => i.y + i.h));
    const r = stage.getBoundingClientRect(), z = Math.max(0.3, Math.min(1.2, Math.min((r.width - 80) / (x1 - x0), (r.height - 80) / (y1 - y0))));
    S.zoom = z; S.pan = { x: (r.width - (x1 - x0) * z) / 2 - x0 * z, y: (r.height - (y1 - y0) * z) / 2 - y0 * z }; applyView();
  }
  stage.addEventListener('wheel', (e) => { e.preventDefault(); zoomBy(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX, e.clientY); }, { passive: false });
  stage.addEventListener('pointerdown', (e) => {
    if (e.target !== stage && e.target !== world && e.target !== nodeLayer && e.target !== folderLayer && e.target !== svg) return;
    choose(null);
    const start = { x: e.clientX, y: e.clientY, px: S.pan.x, py: S.pan.y };
    stage.setPointerCapture(e.pointerId); stage.classList.add('panning');
    const move = (ev) => { S.pan.x = start.px + ev.clientX - start.x; S.pan.y = start.py + ev.clientY - start.y; applyView(); };
    const up = () => { stage.classList.remove('panning'); stage.removeEventListener('pointermove', move); stage.removeEventListener('pointerup', up); };
    stage.addEventListener('pointermove', move); stage.addEventListener('pointerup', up);
  });

  // ------------------------------------------------------------------ arrastar cartões, caixas e ligações
  function choose(sel) { S.sel = sel; nodeLayer.querySelectorAll('.wk-node').forEach((el) => el.classList.toggle('sel', !!sel && sel.kind === 'node' && el.dataset.id === sel.id)); folderLayer.querySelectorAll('.wk-folder').forEach((el) => el.classList.toggle('sel', !!sel && sel.kind === 'folder' && el.dataset.id === sel.id)); edgeLayer.querySelectorAll('.wk-edge').forEach((el) => el.classList.toggle('sel', !!sel && sel.kind === 'edge' && el.dataset.id === sel.id)); paintInspector(); }
  const drag = (e, onMove, onEnd) => {
    const move = (ev) => onMove(ev); const up = (ev) => { document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', up); onEnd(ev); };
    document.addEventListener('pointermove', move); document.addEventListener('pointerup', up);
  };
  const inFolder = (n) => S.folders.find((f) => n.x + NW / 2 >= f.x && n.x + NW / 2 <= f.x + f.w && n.y + NH / 2 >= f.y && n.y + NH / 2 <= f.y + f.h);
  function onNodeDown(e, n, el) {
    e.stopPropagation();
    choose({ kind: 'node', id: n.id });
    if (!S.canEdit) return;
    if (e.target.classList.contains('wk-handle')) return startLink(e, n);
    const start = toWorld(e.clientX, e.clientY), o = { x: n.x, y: n.y }; let moved = false;
    drag(e, (ev) => {
      const w = toWorld(ev.clientX, ev.clientY);
      if (!moved && Math.hypot(w.x - start.x, w.y - start.y) < 3) return;
      moved = true; n.x = Math.round(o.x + w.x - start.x); n.y = Math.round(o.y + w.y - start.y);
      el.style.left = n.x + 'px'; el.style.top = n.y + 'px'; edgeLayer.replaceChildren(...S.edges.flatMap(edgeEls));
    }, async () => {
      if (!moved) return;
      const f = inFolder(n); n.parent = f ? f.id : '';
      await guard(() => put('nodes', n.id, { x: n.x, y: n.y, parent: n.parent }));
    });
  }
  function onFolderDown(e, f, el) {
    e.stopPropagation();
    choose({ kind: 'folder', id: f.id });
    if (!S.canEdit || !W.can('folders.manage')) return;
    const resizing = e.target.classList.contains('wk-resize');
    const start = toWorld(e.clientX, e.clientY), o = { x: f.x, y: f.y, w: f.w, h: f.h };
    const kids = S.nodes.filter((n) => n.parent === f.id).map((n) => ({ n, x: n.x, y: n.y }));
    let moved = false;
    drag(e, (ev) => {
      const w = toWorld(ev.clientX, ev.clientY), dx = w.x - start.x, dy = w.y - start.y;
      if (!moved && Math.hypot(dx, dy) < 3) return; moved = true;
      if (resizing) { f.w = Math.max(120, Math.round(o.w + dx)); f.h = Math.max(90, Math.round(o.h + dy)); el.style.width = f.w + 'px'; el.style.height = f.h + 'px'; }
      else { f.x = Math.round(o.x + dx); f.y = Math.round(o.y + dy); el.style.left = f.x + 'px'; el.style.top = f.y + 'px'; kids.forEach((k) => { k.n.x = Math.round(k.x + dx); k.n.y = Math.round(k.y + dy); }); nodeLayer.querySelectorAll('.wk-node').forEach((ne) => { const nn = nodeById(ne.dataset.id); ne.style.left = nn.x + 'px'; ne.style.top = nn.y + 'px'; }); edgeLayer.replaceChildren(...S.edges.flatMap(edgeEls)); }
    }, async () => {
      if (!moved) return;
      await guard(async () => { await put('folders', f.id, { x: f.x, y: f.y, w: f.w, h: f.h }); if (!resizing) for (const k of kids) await put('nodes', k.n.id, { x: k.n.x, y: k.n.y }); });
    });
  }
  function startLink(e, from) {
    const line = sv('line', { class: 'wk-line wk-temp' }); edgeLayer.appendChild(line);
    const a = { x: from.x + NW / 2, y: from.y + NH };
    drag(e, (ev) => { const w = toWorld(ev.clientX, ev.clientY); line.setAttribute('x1', a.x); line.setAttribute('y1', a.y); line.setAttribute('x2', w.x); line.setAttribute('y2', w.y); }, async (ev) => {
      line.remove();
      const hit = document.elementFromPoint(ev.clientX, ev.clientY), tgt = hit && hit.closest ? hit.closest('.wk-node') : null;
      if (tgt && tgt.dataset.id !== from.id) await guard(async () => { await api('/api/work/edges', { method: 'POST', body: { from: from.id, to: tgt.dataset.id, kind: 'reports' } }); await load(); });
    });
  }

  // ------------------------------------------------------------------ adicionar
  const center = () => { const r = stage.getBoundingClientRect(); const w = toWorld(r.left + r.width / 2, r.top + r.height / 2); return { x: Math.round(w.x - NW / 2), y: Math.round(w.y - NH / 2) }; };
  async function addCard(kind) {
    const pos = center(); let spec = { kind, ...pos };
    if (kind === 'person' || kind === 'role') {
      const used = new Set(S.nodes.filter((n) => n.kind === kind).map((n) => n.ref));
      const opts = kind === 'person' ? W.dir.users.filter((u) => !u.disabled).map((u) => [u.id, (u.display_name || u.username) + ' · ' + roleOf(W.dir, u).name]) : W.dir.roles.map((r) => [r.id, r.name]);
      const sel = select(opts.map(([v, l]) => [v, (used.has(v) ? '✓ ' : '') + l]), opts[0] && opts[0][0], () => {});
      const ok = await modal(kind === 'person' ? t('Adicionar uma pessoa ao quadro') : t('Adicionar um cargo ao quadro'), field(kind === 'person' ? t('Pessoa') : t('Cargo'), sel), [{ label: t('Cancelar'), value: false }, { label: t('Adicionar'), value: true, cls: 'primary' }]);
      if (ok !== true) return; spec.ref = sel.value;
    } else {
      const inp = h('input', { id: 'wk-card-label', placeholder: kind === 'ai' ? t('Ex.: Assistente de triagem') : t('Texto da nota') });
      const ok = await modal(kind === 'ai' ? t('Novo agente de IA') : t('Nova nota'), field(t('Título'), inp), [{ label: t('Cancelar'), value: false }, { label: t('Adicionar'), value: true, cls: 'primary' }]);
      if (ok !== true) return; spec.label = inp.value || (kind === 'ai' ? t('Agente de IA') : t('Nota'));
      spec.color = kind === 'ai' ? '#a78bfa' : '#8b8b94';
    }
    await guard(async () => { const n = await api('/api/work/nodes', { method: 'POST', body: spec }); S.sel = { kind: 'node', id: n.id }; await load(); });
  }
  async function addSector() {
    const inp = h('input', { id: 'wk-sector-name', placeholder: t('Ex.: Financeiro') });
    const ok = await modal(t('Novo setor'), h('div', null, field(t('Nome do setor'), inp), h('p', { class: 'dim small' }, t('O setor vira uma caixa no quadro e uma pasta de arquivos compartilhados. Arraste cartões para dentro dela.'))), [{ label: t('Cancelar'), value: false }, { label: t('Criar setor'), value: true, cls: 'primary' }]);
    if (ok !== true || !inp.value.trim()) return;
    const pos = center();
    await guard(async () => { const f = await api('/api/work/folders', { method: 'POST', body: { name: inp.value, x: pos.x - 80, y: pos.y - 60, w: 420, h: 260, color: COLORS[S.folders.length % COLORS.length] } }); await W.reloadBase(); S.sel = { kind: 'folder', id: f.id }; await load(); });
  }

  // ------------------------------------------------------------------ painel de edição
  function colorRow(cur, on) { return h('div', { class: 'wk-colors' }, COLORS.map((c) => h('button', { type: 'button', class: 'wk-sw' + (c === cur ? ' on' : ''), style: { background: c }, 'aria-label': c, onclick: () => on(c) }))); }
  const debounced = (fn, ms = 400) => { let tm; return (...a) => { clearTimeout(tm); tm = setTimeout(() => fn(...a), ms); }; };
  function paintInspector() {
    const sel = S.sel && find(S.sel);
    if (!sel) return fill(inspector, h('h3', null, t('Quadro')), h('p', { class: 'muted small' }, t('Clique num cartão, numa ligação ou numa caixa de setor para editar. Dê dois cliques num cartão de pessoa para abrir o perfil, ou numa caixa para abrir os arquivos do setor.')),
      h('div', { class: 'wk-legend' }, Object.entries(EDGE_KIND()).map(([k, l]) => h('div', { class: 'small' }, h('span', { class: 'wk-lg e-' + k }), l))), h('p', { class: 'dim small' }, t('{n} cartões · {m} ligações · {s} setores', { n: S.nodes.length, m: S.edges.length, s: S.folders.length })));
    const ro = !S.canEdit;
    if (S.sel.kind === 'node') {
      const n = sel, save = debounced((patch) => guard(async () => { Object.assign(n, await put('nodes', n.id, patch)); paint(); }));
      const label = h('input', { value: n.label, disabled: ro, id: 'wk-n-label' }); label.addEventListener('input', () => save({ label: label.value }));
      const text = h('textarea', { rows: 3, disabled: ro, id: 'wk-n-text' }, n.text); text.addEventListener('input', () => save({ text: text.value }));
      const out = S.edges.filter((e) => e.from === n.id), inn = S.edges.filter((e) => e.to === n.id);
      const targetSel = select([['', t('Ligar a…')], ...S.nodes.filter((x) => x.id !== n.id).map((x) => [x.id, x.label || x.kind])], '', () => {}, { id: 'wk-link-to' });
      const kindSel = select(Object.entries(EDGE_KIND()), 'reports', () => {}, { id: 'wk-link-kind' });
      return fill(inspector, h('h3', null, NODE_KIND()[n.kind]), field(t('Título'), label), field(t('Descrição'), text), ro ? null : field(t('Cor'), colorRow(n.color, (c) => { n.color = c; guard(() => put('nodes', n.id, { color: c })); paint(); })),
        h('h4', null, t('Ligações')), ...out.map((e) => linkRow(e, t('para'), e.to)), ...inn.map((e) => linkRow(e, t('de'), e.from)),
        ro ? null : h('div', { class: 'grid2', style: { gap: '6px' } }, targetSel, kindSel), ro ? null : h('button', { class: 'btn sm', type: 'button', id: 'wk-link-add', onclick: () => targetSel.value && guard(async () => { await api('/api/work/edges', { method: 'POST', body: { from: n.id, to: targetSel.value, kind: kindSel.value } }); await load(); }) }, icon('plus', 13), t('Ligar')),
        ro ? null : h('button', { class: 'btn sm danger', type: 'button', id: 'wk-n-del', style: { marginTop: '12px' }, onclick: async () => { if (await confirmDialog(t('Remover este cartão e as ligações dele?'))) await guard(async () => { await api('/api/work/nodes/' + n.id, { method: 'DELETE' }); S.sel = null; await load(); }); } }, icon('trash', 13), t('Remover cartão')));
    }
    if (S.sel.kind === 'edge') {
      const e = sel, a = nodeById(e.from), b = nodeById(e.to);
      const lab = h('input', { value: e.label, disabled: ro, id: 'wk-e-label' }); lab.addEventListener('input', debounced(() => guard(async () => { Object.assign(e, await put('edges', e.id, { label: lab.value })); paint(); })));
      return fill(inspector, h('h3', null, t('Ligação')), h('p', { class: 'small muted' }, (a ? a.label : '?') + ' → ' + (b ? b.label : '?')),
        field(t('Tipo'), select(Object.entries(EDGE_KIND()), e.kind, (v) => guard(async () => { Object.assign(e, await put('edges', e.id, { kind: v })); paint(); }), { disabled: ro })), field(t('Texto sobre a linha'), lab),
        ro ? null : h('button', { class: 'btn sm danger', type: 'button', id: 'wk-e-del', onclick: () => guard(async () => { await api('/api/work/edges/' + e.id, { method: 'DELETE' }); S.sel = null; await load(); }) }, icon('trash', 13), t('Remover ligação')));
    }
    const f = sel, canF = S.canEdit && W.can('folders.manage');
    const name = h('input', { value: f.name, disabled: !canF, id: 'wk-f-name' }); name.addEventListener('input', debounced(() => guard(async () => { Object.assign(f, await put('folders', f.id, { name: name.value })); await W.reloadBase(); paint(); })));
    const acc = f.access || { mode: 'all', users: [], roles: [], functions: [] };
    const saveAcc = (patch) => guard(async () => { Object.assign(f, await put('folders', f.id, { access: { ...acc, ...patch } })); paint(); });
    const chk = (list, key, idf, labf) => h('div', { class: 'wk-checks' }, list.map((x) => { const i = h('input', { type: 'checkbox', checked: (acc[key] || []).includes(idf(x)), disabled: !canF }); i.addEventListener('change', () => saveAcc({ [key]: i.checked ? [...(acc[key] || []), idf(x)] : (acc[key] || []).filter((v) => v !== idf(x)) })); return h('label', { class: 'check' }, i, h('span', null, labf(x))); }));
    return fill(inspector, h('h3', null, t('Setor')), field(t('Nome'), name), canF ? field(t('Cor'), colorRow(f.color, (c) => guard(async () => { Object.assign(f, await put('folders', f.id, { color: c })); paint(); }))) : null,
      field(t('Quem enxerga os arquivos'), select([['all', t('Todos que podem ver arquivos')], ['restricted', t('Só quem eu escolher')]], acc.mode, (v) => saveAcc({ mode: v }), { disabled: !canF, id: 'wk-f-mode' })),
      acc.mode === 'restricted' ? h('div', null, h('h4', null, t('Cargos')), chk(W.dir.roles, 'roles', (r) => r.id, (r) => r.name), h('h4', null, t('Funções')), chk(W.dir.functions, 'functions', (x) => x.id, (x) => x.name), h('h4', null, t('Pessoas')), chk(W.dir.users.filter((u) => !u.disabled), 'users', (u) => u.id, (u) => u.display_name || u.username)) : null,
      h('div', { class: 'row', style: { marginTop: '12px', gap: '8px' } }, h('button', { class: 'btn sm', type: 'button', id: 'wk-f-open', onclick: () => W.go('files', f.id) }, icon('folder', 13), t('Abrir arquivos')),
        canF ? h('button', { class: 'btn sm danger', type: 'button', id: 'wk-f-del', onclick: async () => { if (await confirmDialog(t('Apagar este setor? Ele precisa estar sem arquivos.'))) await guard(async () => { await api('/api/work/folders/' + f.id, { method: 'DELETE' }); await W.reloadBase(); S.sel = null; await load(); }); } }, icon('trash', 13), t('Apagar')) : null));
  }
  function linkRow(e, dir, other) {
    const o = nodeById(other);
    return h('div', { class: 'wk-linkrow' }, h('span', { class: 'small' }, EDGE_KIND()[e.kind] + ' ' + dir + ' '), h('b', { class: 'small' }, o ? o.label : '?'), h('button', { class: 'btn ghost icon sm', type: 'button', title: t('Remover ligação'), onclick: () => choose({ kind: 'edge', id: e.id }) }, icon('edit', 12)));
  }

  // ------------------------------------------------------------------ criar com IA
  async function aiDialog() {
    const desc = h('textarea', { rows: 5, id: 'wk-ai-desc', placeholder: t('Ex.: Somos uma agência com direção, financeiro, comercial, criação (designers e redatores) e atendimento. O atendimento repassa briefings para a criação, e tudo que passa de R$ 5 mil é aprovado pelo financeiro.') });
    const team = teamPicker((state.settings && state.settings.work) || {}, null, { id: 'wk-ai' });
    const result = h('div', { id: 'wk-ai-result' });
    let draft = null; const replace = h('input', { type: 'checkbox', id: 'wk-ai-replace' });
    const go = h('button', { class: 'btn primary', type: 'button', id: 'wk-ai-go', onclick: async () => {
      go.disabled = true; fill(result, h('div', { class: 'spinner' }));
      try {
        const r = await api('/api/work/ai/flow', { method: 'POST', body: { description: desc.value, ...team.get() } });
        draft = r.draft;
        fill(result, r.warning ? h('div', { class: 'errbox', style: { whiteSpace: 'normal' } }, r.warning) : null,
          h('p', null, t('Proposta: {s} setor(es), {n} cartões e {e} ligações.', { s: draft.sectors.length, n: draft.nodes.length, e: draft.edges.length })),
          h('ul', { class: 'small' }, draft.sectors.map((s) => h('li', null, s.name))),
          h('div', { class: 'small dim' }, r.agents.map((a) => `${a.agent}: ${a.status === 'ok' ? 'IA' : t('regras')}`).join(' · ')),
          h('label', { class: 'check' }, replace, h('span', null, t('Substituir o quadro atual'))),
          h('button', { class: 'btn primary', type: 'button', id: 'wk-ai-apply', onclick: async () => {
            try { const b = await api('/api/work/board/apply', { method: 'POST', body: { draft, replace: replace.checked } }); Object.assign(S, { nodes: b.nodes, edges: b.edges, folders: b.folders }); await W.reloadBase(); paint(); fit(); document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); toast(t('Fluxograma aplicado ao quadro.'), 'ok'); } catch (e) { toast(e.message, 'err'); }
          } }, icon('check', 14), t('Aplicar ao quadro')));
      } catch (e) { fill(result, h('div', { class: 'errbox' }, e.message)); }
      go.disabled = false;
    } }, icon('wand', 14), t('Gerar proposta'));
    await modal(t('Criar o fluxograma com IA'), h('div', { class: 'wk-form' }, h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Descreva a empresa. A equipe de agentes (Analista → Desenhista → Revisor) propõe setores, cargos e ligações; nada muda no quadro até você aplicar. Sem IA configurada, o ASTA usa um modelo padrão por palavras-chave.')), desc, h('div', { class: 'row', style: { margin: '10px 0' } }, team.el, go), result), [{ label: t('Fechar'), value: null }]);
  }

  await load(false);
  W.live(['nodes', 'edges', 'folders'], () => load());
}
