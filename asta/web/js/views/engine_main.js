// Game Engine → Main: criar o jogo (prompt + anexos + web) e vê-lo sendo criado. Inspirado no Godot: árvore da cena, viewport com o jogo (editar/jogar) e Inspetor de propriedades.
import { t } from '../i18n.js';
import { state } from '../main.js';
import { OPT_LABEL, PROP_LABEL } from '../engine_labels.js';
import { BIOME_LABEL, GENRE_LABEL, KINDS, SIZE_LABEL, THEME_LABEL, btn, clone, flatFiles, ibtn, numInput, promptPanel, propRow, stem } from '../engine_ui.js';
import { confirmDialog, debounce, h, icon, modal, popover, toast } from '../ui.js';

const LIVE3D = new Set(['x', 'y', 'z', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'visible', 'scale']);
const RELOAD = new Set(['map', 'objects', 'kind', 'top', 'bottom', 'stars', 'fog']);
const EVENTS = [['coin', 'Moeda'], ['jump', 'Pulo'], ['hit', 'Dano'], ['win', 'Vitória'], ['lose', 'Derrota'], ['powerup', 'Item/cura'], ['shoot', 'Tiro'], ['select', 'Falar/selecionar'], ['door', 'Porta'], ['place', 'Colocar (AR)']];

export default async function render(body, E) {
  const cat = E.cat, kind = E.proj.kind, dim = cat.kinds[kind].dim;
  const S = { scenes: [], name: E.proj.start || 'main', scene: null, sel: null, mode: 'edit', ready: false, imgs: [], sounds: [], maps: [], errors: [], grid: true, snap: 0, collapsed: new Set(), saved: true, runOpts: { mode: '' } };
  let frame = null;

  async function loadLists() {
    const tr = await E.api.tree('game'), files = flatFiles(tr.children);
    S.imgs = files.filter((f) => f.path.startsWith('assets/images/') && /\.(png|jpe?g|webp|gif|svg)$/i.test(f.path)).map((f) => stem(f.path));
    S.sounds = files.filter((f) => f.path.startsWith('assets/sound/') && /\.(wav|mp3|ogg|m4a|flac)$/i.test(f.path)).map((f) => stem(f.path));
    S.maps = (await E.api.maps()).maps;
    S.scenes = (await E.api.get('/scenes')).scenes;
  }
  async function loadScene(name) {
    if (!S.scenes.length) { S.scene = null; return; }
    S.name = S.scenes.includes(name) ? name : S.scenes[0];
    S.scene = await E.api.scene(S.name);
    S.sel = null;
  }
  const nodes = () => { const out = new Map(); const walk = (n, parent) => { out.set(n.id, { n, parent }); (n.children || []).forEach((c) => walk(c, n)); }; if (S.scene) walk(S.scene.root, null); return out; };
  const find = (id) => (nodes().get(id) || {}).n;

  // ---------------------------------------------------------------- viewport (iframe do jogo)
  const status = h('span', { class: 'ge-status small dim', id: 'ge-status' });
  const errBox = h('div', { class: 'ge-errs hidden', id: 'ge-errs' });
  function send(cmd) { if (frame && frame.contentWindow) frame.contentWindow.postMessage(cmd, '*'); }
  function sendScene(reframe) { if (!S.ready || !S.scene) return; send({ geCmd: 'scene', name: S.name, scene: S.scene, mode: S.mode, select: S.sel, reframe: !!reframe }); }
  function reloadFrame() { S.ready = false; frame.src = E.api.play('edit.html') + '?t=' + Date.now(); }
  const onMsg = (ev) => {
    if (!frame || ev.source !== frame.contentWindow) return; const m = ev.data || {};
    if (m.ge === 'ready') { S.ready = true; sendScene(true); }
    else if (m.ge === 'select') { S.sel = m.id; paintTree(); paintInspector(); }
    else if (m.ge === 'moved') { const n = find(m.id); if (n) { Object.assign(n, m.props); S.sel = m.id; markDirty(); paintInspector(); } }
    else if (m.ge === 'delete') deleteNode(m.id);
    else if (m.ge === 'duplicate') duplicateNode(m.id);
    else if (m.ge === 'error') { S.errors = S.errors.concat(m.message).slice(-4); paintErrors(); }
    else if (m.ge === 'loaded') { S.errors = []; paintErrors(); }
  };
  window.addEventListener('message', onMsg); E.onCleanup(() => window.removeEventListener('message', onMsg));
  function paintErrors() { errBox.classList.toggle('hidden', !S.errors.length); errBox.replaceChildren(...S.errors.map((x) => h('div', { class: 'e' }, icon('warn', 13), ' ', x))); }

  // ---------------------------------------------------------------- salvar
  const save = async () => { try { S.saved = false; await E.api.saveScene(S.name, S.scene); S.saved = true; paintStatus(); } catch (e) { toast(e.message, 'err'); } };
  const saveSoon = debounce(save, 700);
  function markDirty() { S.saved = false; paintStatus(); saveSoon(); }
  function paintStatus() { const n = S.scene ? nodes().size : 0; status.textContent = `${S.name} · ${t('{n} nós', { n })} · ${S.saved ? t('salvo') : t('salvando…')}`; }
  // aplica uma mudança: ao vivo no iframe quando o motor lê a propriedade a cada quadro; senão recarrega a cena
  function applyProp(n, key, value) {
    if (value === '' || value == null) delete n[key]; else n[key] = value;
    const live = dim === '2d' ? !RELOAD.has(key) : LIVE3D.has(key);
    if (live) send({ geCmd: 'patch', id: n.id, props: { [key]: value === '' ? undefined : value } }); else sendScene();
    markDirty();
  }

  // ---------------------------------------------------------------- árvore da cena
  const treeEl = h('div', { class: 'ge-tree', id: 'ge-tree', role: 'tree', 'aria-label': t('Árvore da cena') });
  function paintTree() {
    if (!S.scene) { treeEl.replaceChildren(h('div', { class: 'muted small', style: { padding: '8px' } }, t('Ainda não há cena. Descreva o jogo no prompt abaixo.'))); return; }
    const rows = [];
    const walk = (n, depth, parent) => {
      const spec = cat.node_types[n.type] || {}, kids = n.children || [], open = !S.collapsed.has(n.id);
      const row = h('div', { class: 'ge-trow' + (S.sel === n.id ? ' on' : '') + (n.visible === false ? ' hid' : ''), role: 'treeitem', 'aria-selected': String(S.sel === n.id), dataset: { id: n.id, type: n.type }, style: { paddingLeft: 6 + depth * 14 + 'px' }, draggable: parent ? 'true' : 'false',
        onclick: () => select(n.id), ondblclick: () => rename(n) },
        kids.length ? h('span', { class: 'tg', onclick: (e) => { e.stopPropagation(); open ? S.collapsed.add(n.id) : S.collapsed.delete(n.id); paintTree(); } }, icon(open ? 'chevd' : 'chevr', 12)) : h('span', { class: 'tg' }),
        h('span', { class: 'ti' }, icon(spec.icon || 'node', 14)), h('span', { class: 'tn', title: n.type }, n.name || n.type),
        (n.behaviors || []).length ? h('span', { class: 'tb', title: n.behaviors.map((b) => b.type).join(', ') }, icon('bolt', 11)) : null,
        parent ? h('button', { class: 'tv', type: 'button', title: t('Mostrar/ocultar'), onclick: (e) => { e.stopPropagation(); applyProp(n, 'visible', n.visible === false ? true : false); paintTree(); } }, icon(n.visible === false ? 'eyeoff' : 'eye', 13)) : null);
      if (parent) {
        row.addEventListener('dragstart', (e) => { e.dataTransfer.setData('text/plain', n.id); e.dataTransfer.effectAllowed = 'move'; });
      }
      row.addEventListener('dragover', (e) => { e.preventDefault(); const r = row.getBoundingClientRect(), y = (e.clientY - r.top) / r.height; row.dataset.drop = !parent ? 'in' : y < 0.28 ? 'before' : y > 0.72 ? 'after' : 'in'; });
      row.addEventListener('dragleave', () => { delete row.dataset.drop; });
      row.addEventListener('drop', (e) => { e.preventDefault(); const id = e.dataTransfer.getData('text/plain'), where = row.dataset.drop || 'in'; delete row.dataset.drop; moveNode(id, n.id, where); });
      rows.push(row);
      if (open) kids.forEach((c) => walk(c, depth + 1, n));
    };
    walk(S.scene.root, 0, null);
    treeEl.replaceChildren(...rows);
  }
  function select(id, fromFrame) { S.sel = id; paintTree(); paintInspector(); send({ geCmd: 'select', id }); }
  async function rename(n) {
    const inp = h('input', { value: n.name || '', maxlength: 60 });
    if (await modal(t('Renomear'), inp, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]) !== 'ok' || !inp.value.trim()) return;
    n.name = inp.value.trim(); markDirty(); paintTree(); paintInspector(); sendScene();
  }
  function moveNode(id, targetId, where) {
    const idx = nodes(), a = idx.get(id), b = idx.get(targetId);
    if (!a || !b || !a.parent || id === targetId) return;
    let p = b; while (p) { if (p.n.id === id) return; p = p.parent ? idx.get(p.parent.id) : null; }   // não dá para mover um nó para dentro de si mesmo
    a.parent.children = a.parent.children.filter((c) => c.id !== id); if (!a.parent.children.length) delete a.parent.children;
    if (where === 'in' || !b.parent) { (b.n.children = b.n.children || []).push(a.n); }
    else { const sib = b.parent.children, i = sib.findIndex((c) => c.id === targetId); sib.splice(where === 'before' ? i : i + 1, 0, a.n); }
    markDirty(); paintTree(); sendScene();
  }
  function deleteNode(id) {
    const info = nodes().get(id); if (!info || !info.parent) return;
    info.parent.children = info.parent.children.filter((c) => c.id !== id); if (!info.parent.children.length) delete info.parent.children;
    if (S.sel === id) S.sel = null; markDirty(); paintTree(); paintInspector(); sendScene();
  }
  const newId = () => { const all = nodes(); let i = all.size + 1; while (all.has('n' + i)) i++; return 'n' + i; };
  function reId(n) { const all = nodes(); const seen = new Set(all.keys()); const walk = (x) => { let i = seen.size + 1; let nid = 'n' + i; while (seen.has(nid)) nid = 'n' + (++i); x.id = nid; seen.add(nid); (x.children || []).forEach(walk); }; walk(n); return n; }
  function duplicateNode(id) {
    const info = nodes().get(id); if (!info || !info.parent) return;
    const copy = reId(clone(info.n)); copy.name = (copy.name || copy.type) + ' 2'; if (copy.x != null) copy.x += dim === '2d' ? 24 : 1; if (dim === '3d' && copy.z != null) copy.z += 1;
    const sib = info.parent.children; sib.splice(sib.findIndex((c) => c.id === id) + 1, 0, copy); markDirty(); select(copy.id); sendScene();
  }
  async function addNode() {
    const q = h('input', { placeholder: t('Buscar tipo de nó…'), 'aria-label': t('Buscar'), id: 'ge-addnode-q' }), list = h('div', { class: 'ge-addlist' });
    const types = Object.entries(cat.node_types).filter(([, v]) => v.dim === dim || v.dim === 'any');
    let pick = null;
    const paint = () => { const f = q.value.toLowerCase(); list.replaceChildren(...types.filter(([k, v]) => !f || (k + ' ' + t(v.label)).toLowerCase().includes(f)).map(([k, v]) => h('button', { type: 'button', class: 'ge-addopt', dataset: { type: k }, onclick: () => { pick = k; document.querySelector('.modal-bg').remove(); finish(); } }, icon(v.icon || 'node', 16), h('span', null, t(v.label)), h('small', null, k)))); };
    q.addEventListener('input', paint); paint();
    let finish = () => {};
    const done = new Promise((res) => { finish = () => res(pick); });
    modal(t('Adicionar nó'), h('div', null, q, list), [{ label: t('Cancelar'), value: null }]).then(() => finish());
    const type = await done; if (!type) return;
    const spec = cat.node_types[type], parentInfo = S.sel ? nodes().get(S.sel) : null;
    const parent = parentInfo && (cat.node_types[parentInfo.n.type].container || parentInfo.n.children) ? parentInfo.n : S.scene.root;
    const node = { id: newId(), type, name: t(spec.label) };
    spec.props.forEach((p) => { if (p.d !== '' && p.d != null && !['x', 'y', 'z', 'visible'].includes(p.k)) node[p.k] = p.d; });
    if (type === 'Sprite2D') Object.assign(node, { x: 120, y: 120, w: 40, h: 40, color: '#4cc9f0' });
    if (type === 'Label2D' || type === 'Label3D') node.text = t('Texto');
    if (type === 'Mesh3D') Object.assign(node, { y: 1, color: '#ff9f1c' });
    (parent.children = parent.children || []).push(node); markDirty(); select(node.id); sendScene();
  }

  // ---------------------------------------------------------------- inspetor
  const insp = h('div', { class: 'ge-insp', id: 'ge-insp' });
  function control(p, n, apply) {
    const v = n[p.k] != null ? n[p.k] : p.d;
    const sel = (opts, withNone) => { const s = h('select', null, (withNone ? [h('option', { value: '' }, '—')] : []).concat(opts.map(([val, lab]) => h('option', { value: val, selected: val === v }, lab)))); s.value = v == null ? '' : v; s.addEventListener('change', () => apply(s.value)); return s; };
    switch (p.t) {
      case 'num': case 'int': return numInput(v, (x) => apply(p.t === 'int' ? Math.round(x) : x), { step: p.step || (p.t === 'int' ? 1 : 'any'), min: p.min, max: p.max });
      case 'bool': { const i = h('input', { type: 'checkbox', checked: v !== false && !!v }); i.addEventListener('change', () => apply(i.checked)); return i; }
      case 'color': { const c = h('input', { type: 'color', value: /^#[0-9a-f]{6}$/i.test(v || '') ? v : '#888888' }); c.addEventListener('input', () => apply(c.value)); return h('span', { class: 'ge-colorrow' }, c, p.d === '' && v ? h('button', { class: 'btn ghost icon sm', type: 'button', title: t('Limpar'), onclick: () => { apply(''); paintInspector(); } }, icon('x', 12)) : null); }
      case 'select': return sel((p.options || []).map((o) => [o, t(OPT_LABEL[o] || o)]), false);
      case 'image': return sel(S.imgs.map((x) => [x, x]), true);
      case 'sound': return sel(S.sounds.map((x) => [x, x]), true);
      case 'map': return sel(S.maps.map((m) => [m.path, m.name + ' (' + m.path.replace('maps/', '') + ')']), true);
      case 'scene': return sel(S.scenes.map((x) => [x, x]), true);
      case 'node': return sel([...nodes().values()].map(({ n: x }) => [x.name, x.name]), true);
      case 'longtext': { const a = h('textarea', { rows: 3 }); a.value = v || ''; a.addEventListener('input', () => apply(a.value)); return a; }
      default: { const i = h('input', { value: v == null ? '' : v, maxlength: 400 }); i.addEventListener('input', () => apply(i.value)); return i; }
    }
  }
  function paintInspector() {
    if (!S.scene) { insp.replaceChildren(h('div', { class: 'muted small', style: { padding: '12px' } }, t('Sem cena.'))); return; }
    const n = S.sel && find(S.sel);
    if (!n) { insp.replaceChildren(sceneInspector()); return; }
    const spec = cat.node_types[n.type] || { props: [], label: n.type }, isRoot = n === S.scene.root;
    const nameInp = h('input', { value: n.name || '', maxlength: 60, id: 'ge-i-name', 'aria-label': t('Nome') }); nameInp.addEventListener('change', () => { n.name = nameInp.value.trim() || n.type; markDirty(); paintTree(); sendScene(); });
    const groups = { transform: [], props: [] };
    spec.props.forEach((p) => { (['x', 'y', 'z', 'rotation', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz'].includes(p.k) ? groups.transform : groups.props).push(p); });
    const row = (p) => propRow(t(PROP_LABEL[p.k] || p.k), control(p, n, (val) => applyProp(n, p.k, val)), p.hint ? t(p.hint) : '');
    const nudgePad = () => {   // mover com botões: um passo por clique (também funciona com as setas do teclado no viewport; PageUp/PageDown sobem e descem em 3D)
      const has = (k) => spec.props.some((p) => p.k === k); if (!has('x')) return null;
      const steps = dim === '3d' ? [0.25, 1, 5] : (kind === '2.5d' ? [0.25, 1, 2] : [1, 8, 32]);
      const step = steps.includes(S.nudge) ? S.nudge : steps[1], r2 = (v) => Math.round(v * 100) / 100, cur = (k) => Number(n[k]) || 0;
      const go = (dx, dv, dy) => { const step = steps.includes(S.nudge) ? S.nudge : steps[1]; if (dx) applyProp(n, 'x', r2(cur('x') + dx * step)); if (dv) applyProp(n, dim === '3d' ? 'z' : 'y', r2(cur(dim === '3d' ? 'z' : 'y') + dv * step)); if (dy) applyProp(n, 'y', r2(cur('y') + dy * step)); paintInspector(); };
      const b = (label, text, fn, id) => h('button', { type: 'button', class: 'btn sm ge-nudge-b', title: label, 'aria-label': label, id, onclick: fn }, text);
      const stepSel = h('select', { id: 'ge-nudge-step', 'aria-label': t('Passo') }, steps.map((v) => h('option', { value: v, selected: v === step }, String(v))));
      stepSel.addEventListener('change', () => { S.nudge = parseFloat(stepSel.value); });
      return h('div', { class: 'ge-igrp ge-nudge', id: 'ge-nudge' }, h('h4', null, t('Mover')),
        h('div', { class: 'ge-nudge-pad' }, b(t('Mover para a esquerda'), '←', () => go(-1, 0, 0), 'ge-nudge-l'), b(t('Mover para cima'), '↑', () => go(0, -1, 0), 'ge-nudge-u'), b(t('Mover para baixo'), '↓', () => go(0, 1, 0), 'ge-nudge-d'), b(t('Mover para a direita'), '→', () => go(1, 0, 0), 'ge-nudge-r'),
          dim === '3d' && has('y') ? [b(t('Subir'), '⤒', () => go(0, 0, 1), 'ge-nudge-up'), b(t('Descer'), '⤓', () => go(0, 0, -1), 'ge-nudge-down')] : null),
        h('label', { class: 'ge-prop' }, h('span', { class: 'l' }, t('Passo')), stepSel));
    };
    const tagsInp = h('input', { value: (n.tags || []).join(', '), placeholder: t('ex.: player, enemy'), id: 'ge-i-tags' });
    tagsInp.addEventListener('change', () => { const v = tagsInp.value.split(',').map((x) => x.trim()).filter(Boolean).slice(0, 8); if (v.length) n.tags = v; else delete n.tags; markDirty(); sendScene(); });
    const beh = h('div', { class: 'ge-behs' }, (n.behaviors || []).map((b, i) => {
      const bs = cat.behaviors[b.type] || { label: b.type, params: [] };
      return h('div', { class: 'ge-beh' }, h('div', { class: 'bh' }, icon('bolt', 13), h('b', null, t(bs.label)), h('button', { class: 'btn ghost icon sm', type: 'button', title: t('Remover'), onclick: () => { n.behaviors.splice(i, 1); if (!n.behaviors.length) delete n.behaviors; markDirty(); paintInspector(); paintTree(); sendScene(); } }, icon('x', 12))),
        bs.params.map((p) => propRow(t(PROP_LABEL[p.k] || p.k), control(p, b, (val) => { if (val === '' || val == null) delete b[p.k]; else b[p.k] = val; markDirty(); sendScene(); }))));
    }));
    const addBeh = h('select', { id: 'ge-add-beh', 'aria-label': t('Adicionar comportamento') }, h('option', { value: '' }, '＋ ' + t('Adicionar comportamento')), Object.entries(cat.behaviors).filter(([, v]) => v.dims.includes(dim)).map(([k, v]) => h('option', { value: k }, t(v.label))));
    addBeh.addEventListener('change', () => { if (!addBeh.value) return; const b = { type: addBeh.value }; cat.behaviors[b.type].params.forEach((p) => { if (p.d !== '' && p.d != null) b[p.k] = p.d; }); (n.behaviors = n.behaviors || []).push(b); markDirty(); paintInspector(); paintTree(); sendScene(); });
    insp.replaceChildren(
      h('div', { class: 'ge-ih' }, h('span', { class: 'ti' }, icon(spec.icon || 'node', 16)), nameInp, h('span', { class: 'chip dim' }, t(spec.label))),
      h('div', { class: 'ge-iact' }, btn(t('Duplicar'), 'copy', () => duplicateNode(n.id), '', { disabled: isRoot }), btn(t('Apagar'), 'trash', async () => { if (await confirmDialog(t('Apagar «{n}» e o que está dentro dele?', { n: n.name }))) deleteNode(n.id); }, 'danger', { disabled: isRoot, id: 'ge-i-del' }), btn(t('Enquadrar'), 'fit', () => send({ geCmd: 'focus', id: n.id }))),
      groups.transform.length ? h('div', { class: 'ge-igrp' }, h('h4', null, t('Transformação')), groups.transform.map(row)) : null,
      nudgePad(),
      groups.props.length ? h('div', { class: 'ge-igrp' }, h('h4', null, t('Propriedades')), groups.props.map(row)) : null,
      h('div', { class: 'ge-igrp' }, h('h4', null, t('Comportamentos')), beh, addBeh), h('div', { class: 'ge-igrp' }, h('h4', null, t('Etiquetas')), tagsInp),
      (n.type === 'TileMap' || n.type === 'Terrain3D') ? h('div', { class: 'ge-igrp' }, h('p', { class: 'muted small' }, t('Os objetos do mapa (moedas, inimigos, jogador…) são editados na aba Map.')), btn(t('Abrir o mapa'), 'mountain', () => E.go('map'))) : null);
  }
  function sceneInspector() {
    const sc = S.scene, setg = sc.settings = sc.settings || {};
    const field = (label, ctl, hint) => propRow(label, ctl, hint);
    const colorIn = (key) => { const c = h('input', { type: 'color', value: /^#[0-9a-f]{6}$/i.test(setg[key] || '') ? setg[key] : '#101820' }); c.addEventListener('input', () => { setg[key] = c.value; markDirty(); sendScene(); }); return c; };
    const numIn = (key, d, o) => numInput(setg[key] != null ? setg[key] : d, (v) => { setg[key] = v; markDirty(); sendScene(); }, o);
    const chk = (key, d) => { const i = h('input', { type: 'checkbox', checked: setg[key] != null ? !!setg[key] : d }); i.addEventListener('change', () => { setg[key] = i.checked; markDirty(); sendScene(); }); return i; };
    const winSel = h('select', { id: 'ge-i-win' }, cat.rule_wins.map((w) => h('option', { value: w, selected: (sc.rules || {}).win === w }, t({ none: 'Sem fim', reach_goal: 'Chegar ao objetivo', collect_all: 'Coletar tudo e chegar ao objetivo' }[w])))); winSel.addEventListener('change', () => { sc.rules = { win: winSel.value }; markDirty(); sendScene(); });
    const st = E.proj.settings || {}, au = st.audio || {};
    const musicSel = h('select', { id: 'ge-i-music' }, [h('option', { value: '' }, '—')].concat(S.sounds.map((s) => h('option', { value: s, selected: au.music === s }, s)))); musicSel.addEventListener('change', async () => { E.proj = await E.api.put('', { settings: { audio: Object.assign({}, au, { music: musicSel.value }) } }); });
    const evSel = (ev) => { const s = h('select', null, [h('option', { value: '' }, t('(som padrão)'))].concat(S.sounds.map((x) => h('option', { value: x, selected: (au.events || {})[ev] === x }, x)))); s.addEventListener('change', async () => { const events = Object.assign({}, au.events || {}); if (s.value) events[ev] = s.value; else delete events[ev]; E.proj = await E.api.put('', { settings: { audio: Object.assign({}, au, { events }) } }); }); return s; };
    const startSel = h('select', null, S.scenes.map((x) => h('option', { value: x, selected: E.proj.start === x }, x))); startSel.addEventListener('change', async () => { E.proj = await E.api.put('', { start: startSel.value }); });
    const hp = numInput(st.hp || 3, async (v) => { E.proj = await E.api.put('', { settings: { hp: Math.round(v) } }); }, { min: 1, max: 99 });
    const desc = h('textarea', { rows: 3, maxlength: 400, id: 'ge-i-desc' }); desc.value = E.proj.description || ''; desc.addEventListener('change', async () => { E.proj = await E.api.put('', { description: desc.value }); });
    const themeSel = h('select', { id: 'ge-i-theme' }, cat.themes.map((x) => h('option', { value: x, selected: E.proj.theme === x }, t(THEME_LABEL[x] || x)))); themeSel.addEventListener('change', async () => { E.proj = await E.api.put('', { theme: themeSel.value }); });
    const langSel = h('select', null, [['pt', 'Português'], ['en', 'English']].map(([v, l]) => h('option', { value: v, selected: E.proj.language === v }, l))); langSel.addEventListener('change', async () => { E.proj = await E.api.put('', { language: langSel.value }); });
    return h('div', null,
      h('div', { class: 'ge-ih' }, h('span', { class: 'ti' }, icon('engine', 16)), h('b', null, t('Cena e projeto'))),
      h('div', { class: 'ge-igrp' }, h('h4', null, t('Cena «{n}»', { n: S.name })),
        field(t('Fim de jogo'), winSel), dim === '2d' ? [field(t('Céu (topo)'), colorIn('sky_top')), field(t('Céu (base)'), colorIn('sky_bottom')), field(t('Altura da visão'), numIn('view_h', 540, { min: 120, max: 4000 })), field(t('Gravidade'), numIn('gravity', 0, { min: 0, max: 5000 }), t('0 = sem gravidade (vista de cima)')),
          field(t('Ordenar por profundidade'), chk('ysort', false)), field(t('Vinheta'), chk('vignette', true))] : [field(t('Câmera inicial'), (() => { const s = h('select', null, ['third', 'first'].map((v) => h('option', { value: v, selected: (setg.camera || 'third') === v }, t(v === 'third' ? '3ª pessoa' : '1ª pessoa')))); s.addEventListener('change', () => { setg.camera = s.value; markDirty(); sendScene(); }); return s; })()), field(t('Sombras'), chk('shadows', true))]),
      h('div', { class: 'ge-igrp' }, h('h4', null, t('Projeto')), field(t('Descrição'), desc), field(t('Tema'), themeSel), field(t('Idioma do jogo'), langSel), field(t('Vida inicial'), hp), field(t('Cena inicial'), startSel)),
      h('div', { class: 'ge-igrp' }, h('h4', null, t('Sons do jogo')), field(t('Música'), musicSel), EVENTS.map(([ev, lab]) => field(t(lab), evSel(ev))), h('p', { class: 'muted small' }, t('Crie e edite os sons na aba Sound.'))));
  }

  // ---------------------------------------------------------------- barra do viewport
  const sceneSel = h('select', { id: 'ge-scene-sel', class: 'ge-ssel', title: t('Cena'), 'aria-label': t('Cena') });
  const paintScenes = () => { sceneSel.replaceChildren(...S.scenes.map((s) => h('option', { value: s, selected: s === S.name }, s))); sceneSel.value = S.name; };
  sceneSel.addEventListener('change', async () => { await save(); await loadScene(sceneSel.value); paintAll(); sendScene(true); });
  const playBtn = h('button', { class: 'btn sm primary', id: 'ge-play', type: 'button', onclick: togglePlay }, icon('play', 13), h('span', null, t('Jogar')));
  function togglePlay() {
    S.mode = S.mode === 'edit' ? 'play' : 'edit'; playBtn.replaceChildren(icon(S.mode === 'edit' ? 'play' : 'stop', 13), h('span', null, S.mode === 'edit' ? t('Jogar') : t('Parar')));
    playBtn.classList.toggle('danger', S.mode === 'play'); playBtn.classList.toggle('primary', S.mode === 'edit'); stage.classList.toggle('playing', S.mode === 'play'); sendScene(S.mode === 'edit');
    if (S.mode === 'play') setTimeout(() => { try { frame.focus(); } catch (e) { /* ok */ } }, 80);
  }
  const snapSel = h('select', { id: 'ge-snap', title: t('Alinhar à grade'), 'aria-label': t('Alinhar à grade') }, [[0, t('Sem grade')], [8, '8'], [16, '16'], [32, '32']].map(([v, l]) => h('option', { value: v }, dim === '2d' ? l : (v ? v / 8 + ' m' : l))));
  snapSel.addEventListener('change', () => { S.snap = parseFloat(snapSel.value) / (dim === '2d' ? 1 : 8); send({ geCmd: 'snap', size: S.snap }); });
  const gridBtn = h('button', { class: 'btn ghost icon sm on', id: 'ge-grid', type: 'button', title: t('Mostrar a grade'), onclick: () => { S.grid = !S.grid; gridBtn.classList.toggle('on', S.grid); send({ geCmd: 'grid', on: S.grid }); } }, icon('grid', 15));
  let muted = false;
  const muteBtn = h('button', { class: 'btn ghost icon sm', id: 'ge-mute', type: 'button', title: t('Silenciar'), onclick: () => { muted = !muted; muteBtn.classList.toggle('on', muted); send({ geCmd: 'mute', on: muted }); } }, icon('audio', 15));
  const toolbar = h('div', { class: 'ge-vtool' }, playBtn, sceneSel, ibtn(t('Nova cena'), 'plus', newScene, '', { id: 'ge-new-scene' }), h('span', { class: 'sep' }), gridBtn, snapSel, ibtn(t('Enquadrar tudo'), 'fit', () => send({ geCmd: 'frame' }), '', { id: 'ge-frame' }), muteBtn,
    ibtn(t('Recarregar o jogo'), 'refresh', async () => { await save(); reloadFrame(); }, '', { id: 'ge-reload' }), ibtn(t('Tela cheia'), 'zoomin', () => { const el = stage; (el.requestFullscreen || el.webkitRequestFullscreen || (() => {})).call(el); }), h('span', { class: 'grow' }), status);
  async function newScene() {
    const inp = h('input', { placeholder: 'fase2', maxlength: 30, id: 'ge-ns-name' }), dup = h('input', { type: 'checkbox', checked: true });
    if (await modal(t('Nova cena'), h('div', null, inp, h('label', { class: 'check', style: { marginTop: '10px' } }, dup, h('span', null, t('Começar como cópia da cena atual')))), [{ label: t('Cancelar'), value: null }, { label: t('Criar'), value: 'ok', cls: 'primary' }]) !== 'ok') return;
    const name = inp.value.trim().replace(/[^\w-]+/g, '-').toLowerCase(); if (!name) return;
    if (S.scenes.includes(name)) { toast(t('Já existe uma cena com esse nome.'), 'err'); return; }
    const sc = dup.checked ? Object.assign(clone(S.scene), { name }) : blankScene(name);
    await E.api.saveScene(name, sc); await loadLists(); await loadScene(name); paintAll(); sendScene(true); toast(t('Cena criada'), 'ok');
  }
  function blankScene(name) {
    const root = dim === '2d' ? { id: 'n1', type: 'Node2D', name, children: [{ id: 'n2', type: 'Camera2D', name: 'Câmera' }, { id: 'n3', type: 'UILabel', name: 'Placar', text: 'Pontos: {score}', anchor: 'top-left' }] }
      : { id: 'n1', type: 'Node3D', name, children: [{ id: 'n2', type: 'Sky3D', name: 'Céu' }, { id: 'n3', type: 'Light3D', name: 'Sol', kind: 'directional' }, { id: 'n4', type: 'Camera3D', name: 'Câmera', mode: 'third' }] };
    return { name, kind, settings: {}, rules: { win: 'none' }, root };
  }

  // ---------------------------------------------------------------- montagem
  frame = h('iframe', { class: 'ge-frame', id: 'ge-frame', title: t('Jogo'), sandbox: 'allow-scripts allow-pointer-lock allow-modals allow-popups allow-forms', allow: 'autoplay; fullscreen; gamepad; xr-spatial-tracking', allowfullscreen: true });
  const stage = h('div', { class: 'ge-stage' }, frame);
  const optsBtn = h('button', { class: 'tool', id: 'ge-opts', type: 'button', title: t('Opções do jogo (tipo, gênero, tema, duração)') }, icon('config', 15), t('Opções'));
  const modeSel = h('select', { class: 'team-sel', id: 'ge-mode', title: t('O que o prompt faz'), 'aria-label': t('O que o prompt faz') }, [['', t('Editar este jogo')], ['new', t('Criar do zero')]].map(([v, l]) => h('option', { value: v }, l)));
  modeSel.addEventListener('change', () => { S.runOpts.mode = modeSel.value; });
  const choices = { kind: kind, genre: '', theme: '', length: 'medium' };
  optsBtn.addEventListener('click', () => {
    const mk = (opts, key, onch) => { const s = h('select', { id: 'ge-o-' + key }, opts.map(([v, l]) => h('option', { value: v, selected: choices[key] === v }, l))); s.addEventListener('change', () => { choices[key] = s.value; if (onch) onch(); }); return s; };
    const content = h('div', { class: 'ge-optpop' }); const paint = () => content.replaceChildren(
      propRow(t('Tipo'), mk(KINDS.map(([v, l]) => [v, l]), 'kind', () => { choices.genre = ''; paint(); })),
      propRow(t('Gênero do jogo'), mk([['', t('automático')]].concat(Object.entries(cat.genres).filter(([, g]) => g.kinds.includes(choices.kind)).map(([id]) => [id, t(GENRE_LABEL[id] || id)])), 'genre')),
      propRow(t('Tema'), mk([['', t('automático')]].concat(cat.themes.map((x) => [x, t(THEME_LABEL[x] || x)])), 'theme')), propRow(t('Duração'), mk(Object.keys(SIZE_LABEL).map((k) => [k, t(SIZE_LABEL[k])]), 'length')),
      h('p', { class: 'muted small' }, t('Valem para «Criar do zero». Ao editar, o tipo do jogo não muda.')));
    paint(); popover(optsBtn, content);
  });
  const pp = promptPanel(E, {
    tab: 'main', endpoint: 'generate', title: t('Prompt do jogo'), placeholder: t('Descreva o jogo ou o que mudar: “adicione um chefe no fim”, “deixe de noite”, “mais moedas”…'), tools: [optsBtn, h('span', { class: 'tool' }, modeSel)],
    intro: t('Descreva o jogo e a IA monta tudo: cena, mapa, personagens, sons e diálogos. Anexe roteiros, imagens, vídeos ou ZIPs de referência; ligue «Web» para pesquisar na internet.'),
    hints: [t('Um jogo de plataforma de floresta com moedas e um chefe'), t('Aventura 3D num vulcão, de terceira pessoa'), t('Sala de realidade virtual com objetos para arremessar'), t('Jogo isométrico numa ilha tropical')],
    body: () => Object.assign({ kind: choices.kind, genre: choices.genre, theme: choices.theme, length: choices.length, mode: S.runOpts.mode || '', language: E.proj.language }, S.runOpts.mode === 'new' ? {} : { kind: '' }),
    onStart: () => { if (S.mode === 'play') togglePlay(); },
    onResult: async (res) => { await E.refresh(); await loadLists(); await loadScene(res.project && res.project.start); document.getElementById('ge-kind').textContent = E.proj.kind.toUpperCase(); paintAll(); reloadFrame(); toast(t('Jogo atualizado'), 'ok'); },
  });
  const treeBox = h('section', { class: 'ge-panel ge-treebox' }, h('div', { class: 'ge-ph' }, h('b', null, t('Cena')), h('span', { class: 'grow' }), ibtn(t('Adicionar nó'), 'plus', addNode, '', { id: 'ge-add-node' })), treeEl);
  const left = h('div', { class: 'ge-left' }, treeBox, pp.el);
  const center = h('section', { class: 'ge-center' }, toolbar, stage, errBox);
  const right = h('aside', { class: 'ge-right', 'aria-label': t('Propriedades') }, h('div', { class: 'ge-ph' }, h('b', null, t('Propriedades'))), insp);
  body.replaceChildren(h('div', { class: 'ge-grid ge-main' }, left, center, right));
  function paintAll() { paintScenes(); paintTree(); paintInspector(); paintStatus(); }

  await loadLists(); await loadScene(E.proj.start); paintAll(); if (S.scenes.length) reloadFrame();   // sem cena ainda (projeto novo): o jogo carrega quando a IA terminar
  E.onCleanup(() => { if (!S.saved) save(); });
  const auto = (E.ctx || {}).autorun;   // veio do «Criar jogo» da lista de projetos: roda o prompt agora
  if (auto) {
    Object.assign(choices, { kind: auto.kind || kind, genre: auto.genre || '', theme: auto.theme || '', length: auto.length || 'medium' }); S.runOpts.mode = 'new'; modeSel.value = 'new';
    setTimeout(() => pp.run(auto.prompt, auto.ids || []), 150);
  }
}
