// Game Engine → Map: gerar e editar o mapa do jogo (2D de blocos, isométrico com alturas e 3D com relevo). Prompt à esquerda, visualizador no centro, propriedades à direita.
// Dá para selecionar pontos/regiões do mapa e editar (pincel, blocos, objetos) ou gerar de novo só aquela parte; o mapa inteiro também sai de um prompt.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { OPT_LABEL } from '../engine_labels.js';
import { BIOME_LABEL, GENRE_LABEL, SIZE_LABEL, THEME_LABEL, btn, clone, ibtn, numInput, promptPanel, propRow, runJob } from '../engine_ui.js';
import { confirmDialog, debounce, h, icon, modal, toast } from '../ui.js';

const OBJ_EMOJI = { player: '🧍', goal: '🏁', coin: '🪙', gem: '💎', enemy: '👾', flyer: '🦇', chaser: '😈', spike: '🔺', spring: '⤴️', heart: '❤️', key: '🔑', door: '🚪', npc: '🧙', crate: '📦', tree: '🌲', rock: '🪨', house: '🏠', ball: '🟠', pillar: '🏛️', portal: '🌀' };
const OBJ2D = ['player', 'goal', 'coin', 'gem', 'heart', 'enemy', 'flyer', 'chaser', 'spike', 'spring', 'key', 'door', 'npc', 'crate', 'tree'];
const OBJ3D = ['player', 'goal', 'tree', 'rock', 'house', 'npc', 'coin', 'gem', 'enemy', 'chaser', 'crate', 'ball', 'pillar', 'portal'];

export default async function render(body, E) {
  const cat = E.cat, dim = cat.kinds[E.proj.kind].dim;
  const S = { maps: [], path: '', map: null, tool: dim === '3d' ? 'region' : 'paint', tile: '1', obj: 'coin', radius: 14, strength: 0.5, region: null, undo: [], ready: false, saved: true };
  let frame = null, view = null, vctx = null, V = { zoom: 1, ox: 20, oy: 20 }, drag = null, raf = 0, spaceDown = false, brushBusy = false, pendingBrush = null, needFit = true;
  const status = h('span', { class: 'small dim', id: 'ge-mstatus' });

  async function loadList() { S.maps = (await E.api.maps()).maps.filter((m) => (dim === '3d') === (m.kind === '3d')); }
  async function openMap(path) {
    S.path = path; S.map = path ? await E.api.map(path) : null; S.region = null; S.undo = []; S.saved = true; paintAll();
    if (dim === '3d') { if (S.ready) sendMapScene(); } else { needFit = true; if (view && view.width > 60) { fit(); needFit = false; } draw(); }
  }
  let ver = 0;   // cada edição sobe a versão: a resposta do servidor só substitui o mapa se nada mudou enquanto salvava (senão a edição em andamento se perdia)
  const saveSoon = debounce(async () => {
    const v = ver, sent = S.map;
    try {
      const res = await E.api.saveMap(S.path, sent);
      if (v !== ver || drag || S.map !== sent) return;   // houve edição no meio: o próximo salvamento já está agendado
      const idx = S.selObj && sent.objects ? sent.objects.indexOf(S.selObj) : -1;
      S.map = res; S.selObj = idx >= 0 && res.objects ? res.objects[idx] || null : null; S.saved = true; paintStatus(); if (dim === '2d') draw();
    } catch (e) { toast(e.message, 'err'); }
  }, 600);
  function markDirty() { ver++; S.saved = false; paintStatus(); saveSoon(); }
  function paintStatus() { status.textContent = S.map ? `${S.map.name} · ${dim === '3d' ? S.map.res + '×' + S.map.res + ' · ' + S.map.size + ' m' : S.map.w + '×' + S.map.h} · ${t('{n} objetos', { n: (S.map.objects || []).length })} · ${S.saved ? t('salvo') : t('salvando…')}` : ''; }
  const pushUndo = () => { S.undo.push(clone(S.map)); if (S.undo.length > 20) S.undo.shift(); };
  async function undo() { const m = S.undo.pop(); if (!m) return; S.map = m; markDirty(); if (dim === '3d') sendMap(); else draw(); paintAll(false); }

  // ================================================================= 2D: editor de blocos
  function setup2D(wrap) {
    view = h('canvas', { id: 'ge-mcanvas', tabindex: 0, 'aria-label': t('Mapa') }); vctx = view.getContext('2d'); wrap.replaceChildren(view);
    const ro = new ResizeObserver(() => { const r = wrap.getBoundingClientRect(); view.width = Math.max(10, r.width); view.height = Math.max(10, r.height); if (needFit && S.map && view.width > 60) { fit(); needFit = false; } draw(); }); ro.observe(wrap); E.onCleanup(() => ro.disconnect());
    view.addEventListener('contextmenu', (e) => e.preventDefault());
    view.addEventListener('wheel', (e) => { e.preventDefault(); const r = view.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, f = e.deltaY < 0 ? 1.15 : 1 / 1.15, nz = Math.max(0.1, Math.min(8, V.zoom * f)); V.ox = mx - (mx - V.ox) * nz / V.zoom; V.oy = my - (my - V.oy) * nz / V.zoom; V.zoom = nz; draw(); }, { passive: false });
    view.addEventListener('pointerdown', (e) => { view.focus(); view.setPointerCapture(e.pointerId); const c = cell(e); if (e.button === 1 || e.button === 2 || spaceDown || S.tool === 'pan') { drag = { kind: 'pan', x: e.clientX, y: e.clientY, ox: V.ox, oy: V.oy }; return; } if (!S.map) return;
      if (S.tool === 'region') { drag = { kind: 'region', a: c, b: c }; S.region = { x0: c.x, y0: c.y, x1: c.x, y1: c.y }; draw(); return; }
      if (S.tool === 'move') { const k = objAt(c); if (k >= 0) { pushUndo(); S.selObj = S.map.objects[k]; drag = { kind: 'move', o: S.selObj }; draw(); } else { S.selObj = null; draw(); } return; }
      pushUndo(); drag = { kind: 'edit', erase: e.altKey || e.button === 2 }; apply(c, e); draw(); });
    view.addEventListener('pointermove', (e) => { if (!drag) return; if (drag.kind === 'pan') { V.ox = drag.ox + e.clientX - drag.x; V.oy = drag.oy + e.clientY - drag.y; draw(); return; } const c = cell(e); if (drag.kind === 'move') { const m = S.map; drag.o.x = Math.max(0, Math.min(m.w - 1, c.x)); drag.o.y = Math.max(0, Math.min(m.h - 1, c.y)); drag.moved = true; draw(); return; } if (drag.kind === 'region') { drag.b = c; S.region = { x0: Math.min(drag.a.x, c.x), y0: Math.min(drag.a.y, c.y), x1: Math.max(drag.a.x, c.x), y1: Math.max(drag.a.y, c.y) }; draw(); paintRegion(); return; } if (drag.kind === 'edit' && (S.tool === 'paint' || S.tool === 'erase' || S.tool === 'height')) { apply(c, e); draw(); } });
    const up = () => { if (!drag) return; const d = drag; drag = null; if (d.kind === 'edit' || (d.kind === 'move' && d.moved)) { markDirty(); paintStatus(); } if (d.kind === 'region') paintRegion(); };
    view.addEventListener('pointerup', up); view.addEventListener('pointercancel', up);
    const key = (e) => { if (!document.body.contains(view) || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || '')) return; if (e.code === 'Space') { spaceDown = e.type === 'keydown'; if (spaceDown) e.preventDefault(); } if (e.type === 'keydown' && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); undo(); }
      const arrow = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.code];
      if (e.type === 'keydown' && arrow && S.tool === 'move' && S.selObj && S.map) { e.preventDefault(); pushUndo(); const o = S.selObj; o.x = Math.max(0, Math.min(S.map.w - 1, o.x + arrow[0])); o.y = Math.max(0, Math.min(S.map.h - 1, o.y + arrow[1])); markDirty(); draw(); } };
    window.addEventListener('keydown', key); window.addEventListener('keyup', key); E.onCleanup(() => { window.removeEventListener('keydown', key); window.removeEventListener('keyup', key); });
  }
  const objAt = (c) => { const os = (S.map && S.map.objects) || []; for (let i = os.length - 1; i >= 0; i--) if (Math.floor(os[i].x) === c.x && Math.floor(os[i].y) === c.y) return i; return -1; };
  const tilePx = () => (S.map ? S.map.tile : 32);
  function cell(e) { const r = view.getBoundingClientRect(), t0 = tilePx(), px = (e.clientX - r.left - V.ox) / V.zoom / t0, py = (e.clientY - r.top - V.oy) / V.zoom / t0; return { x: Math.floor(px), y: Math.floor(py), fx: px, fy: py }; }
  function fit() { if (!view || !S.map) return; V.zoom = Math.max(0.1, Math.min(4, Math.min((view.width - 30) / (S.map.w * S.map.tile), (view.height - 30) / (S.map.h * S.map.tile)))); V.ox = (view.width - S.map.w * S.map.tile * V.zoom) / 2; V.oy = (view.height - S.map.h * S.map.tile * V.zoom) / 2; }
  function apply(c, e) {
    const m = S.map, grid = m.layers[0].data; if (c.x < 0 || c.y < 0 || c.x >= m.w || c.y >= m.h) return;
    if (S.tool === 'paint') grid[c.y][c.x] = parseInt(S.tile, 10); else if (S.tool === 'erase') grid[c.y][c.x] = 0;
    else if (S.tool === 'height') { m.heights = m.heights || grid.map((r) => r.map(() => 1)); m.heights[c.y][c.x] = Math.max(0, Math.min(16, m.heights[c.y][c.x] + (e.altKey || e.shiftKey ? -1 : 1))); }
    else if (S.tool === 'object' && drag && !drag.placed) { drag.placed = true; (m.objects = m.objects || []).push({ type: S.obj, x: c.x, y: c.y }); if (S.obj === 'player') { m.objects = m.objects.filter((o, i, a) => o.type !== 'player' || a.lastIndexOf(o) === i); } paintStatus(); }
    else if (S.tool === 'delobj' && drag && !drag.placed) { drag.placed = true; const k = m.objects.findIndex((o) => o.x === c.x && o.y === c.y && o.type !== 'player'); if (k >= 0) m.objects.splice(k, 1); paintStatus(); }
  }
  function draw() {
    if (!vctx || raf) return; raf = requestAnimationFrame(() => {
      raf = 0; const m = S.map; vctx.clearRect(0, 0, view.width, view.height); vctx.fillStyle = '#0a0a0a'; vctx.fillRect(0, 0, view.width, view.height); if (!m) return;
      view.dataset.vz = String(V.zoom); view.dataset.vox = String(V.ox); view.dataset.voy = String(V.oy);   // enquadramento atual (os testes convertem célula em pixel com isso)
      const T = m.tile; vctx.save(); vctx.translate(V.ox, V.oy); vctx.scale(V.zoom, V.zoom);
      const th = (cat.theme_colors[m.theme] || cat.theme_colors.forest); vctx.fillStyle = th.bottom; vctx.fillRect(0, 0, m.w * T, m.h * T);
      const grid = m.layers[0].data;
      for (let y = 0; y < m.h; y++) for (let x = 0; x < m.w; x++) { const id = grid[y][x]; if (!id) continue; const p = m.palette[String(id)] || { color: '#777' }; vctx.fillStyle = p.color; vctx.fillRect(x * T, y * T, T + 0.5, T + 0.5); if (m.heights && m.heights[y]) { const hv = m.heights[y][x]; vctx.fillStyle = `rgba(0,0,0,${Math.max(0, (3 - hv) * 0.07)})`; vctx.fillRect(x * T, y * T, T, T); if (V.zoom > 0.5 && hv > 1) { vctx.fillStyle = 'rgba(255,255,255,.8)'; vctx.font = T * 0.4 + 'px sans-serif'; vctx.fillText(hv, x * T + 3, y * T + T * 0.45); } } }
      if (V.zoom > 0.4) { vctx.strokeStyle = 'rgba(255,255,255,.07)'; vctx.lineWidth = 1 / V.zoom; vctx.beginPath(); for (let x = 0; x <= m.w; x++) { vctx.moveTo(x * T, 0); vctx.lineTo(x * T, m.h * T); } for (let y = 0; y <= m.h; y++) { vctx.moveTo(0, y * T); vctx.lineTo(m.w * T, y * T); } vctx.stroke(); }
      vctx.font = Math.round(T * 0.78) + 'px system-ui,"Apple Color Emoji","Segoe UI Emoji"'; vctx.textAlign = 'center'; vctx.textBaseline = 'middle';
      (m.objects || []).forEach((o) => { vctx.fillText(OBJ_EMOJI[o.type] || '❓', (o.x + 0.5) * T, (o.y + 0.55) * T); });
      if (S.selObj && S.tool === 'move' && (m.objects || []).includes(S.selObj)) { vctx.strokeStyle = '#ffd166'; vctx.lineWidth = 2 / V.zoom; vctx.strokeRect(S.selObj.x * T + 1, S.selObj.y * T + 1, T - 2, T - 2); }
      if (S.region) { const r = S.region; vctx.strokeStyle = '#7cb7ff'; vctx.fillStyle = 'rgba(124,183,255,.2)'; vctx.lineWidth = 2 / V.zoom; vctx.fillRect(r.x0 * T, r.y0 * T, (r.x1 - r.x0 + 1) * T, (r.y1 - r.y0 + 1) * T); vctx.strokeRect(r.x0 * T, r.y0 * T, (r.x1 - r.x0 + 1) * T, (r.y1 - r.y0 + 1) * T); }
      vctx.restore();
    });
  }

  // ================================================================= 3D: viewer no iframe do motor
  function setup3D(wrap) {
    frame = h('iframe', { class: 'ge-frame', id: 'ge-mframe', title: t('Mapa 3D'), sandbox: 'allow-scripts allow-pointer-lock allow-modals', allow: 'autoplay; fullscreen', style: { position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0 } }); wrap.replaceChildren(frame);
    const onMsg = (ev) => { if (!frame || ev.source !== frame.contentWindow) return; const m = ev.data || {};
      if (m.ge === 'ready') { S.ready = true; sendMapScene(true); }
      else if (m.ge === 'brush') onBrush(m); };
    window.addEventListener('message', onMsg); E.onCleanup(() => window.removeEventListener('message', onMsg));
    frame.src = E.api.play('edit.html') + '?t=' + Date.now();
  }
  const send = (cmd) => { if (frame && frame.contentWindow) frame.contentWindow.postMessage(cmd, '*'); };
  function mapScene() {
    const th = cat.theme_colors[(S.map && S.map.theme) || 'forest'] || cat.theme_colors.forest;
    return { name: 'mapview', kind: '3d', settings: { shadows: true, camera: 'third' }, rules: { win: 'none' }, root: { id: 'r', type: 'Node3D', name: 'Mapa', children: [{ id: 's', type: 'Sky3D', top: th.top, bottom: th.bottom, fog: 0.15 }, { id: 'l1', type: 'Light3D', kind: 'directional', intensity: 1.1, x: 40, y: 70, z: 30, extent: 120 }, { id: 'l2', type: 'Light3D', kind: 'hemisphere', intensity: 0.8 }, { id: 't', type: 'Terrain3D', map: S.path, objects: true }] } };
  }
  function sendMapScene(reframe) { if (!S.ready || !S.map) return; (frame.contentWindow || {}).postMessage && send({ geCmd: 'map', path: S.path, data: S.map }); send({ geCmd: 'scene', name: 'mapview', scene: mapScene(), mode: 'edit', reframe: !!reframe }); sendTool(); }
  function sendMap() { send({ geCmd: 'map', path: S.path, data: S.map, region: S.region && S.tool === 'region' ? S.region : null }); sendTool(); }
  function sendTool() { send({ geCmd: 'tool', name: S.tool === 'region' || S.tool === 'place' || S.tool === 'move' || S.tool === 'delobj' || S.tool === 'raise' || S.tool === 'lower' || S.tool === 'smooth' || S.tool === 'flatten' || S.tool === 'noise' ? 'brush' : 'select', radius: S.radius }); if (S.region) send({ geCmd: 'marker', kind: 'region', x: S.region.x, z: S.region.z, radius: S.region.radius }); }
  const BRUSH_OPS = ['raise', 'lower', 'smooth', 'flatten', 'noise'];
  async function onBrush(m) {
    if (!S.map) return;
    if (S.tool === 'region') { if (m.phase === 'down') { S.region = { x: m.x, z: m.z, radius: S.radius }; send({ geCmd: 'marker', kind: 'region', x: m.x, z: m.z, radius: S.radius }); paintRegion(); } return; }
    if (S.tool === 'place' && m.phase === 'down') { pushUndo(); S.map.objects.push({ type: S.obj, x: m.x, z: m.z, ry: Math.floor(Math.random() * 360) }); markDirty(); sendMap(); return; }
    if (S.tool === 'move') {
      const os = S.map.objects || [];
      if (m.phase === 'down') { let best = -1, bd = Math.max(4, S.radius / 2); os.forEach((o, i) => { const d = Math.hypot(o.x - m.x, o.z - m.z); if (d < bd) { bd = d; best = i; } }); S.moveIdx = best; if (best >= 0) { pushUndo(); S.selObj = os[best]; } return; }
      const o = S.moveIdx >= 0 ? os[S.moveIdx] : null;
      if (o && m.phase === 'move') { o.x = m.x; o.z = m.z; sendMap(); } else if (o && m.phase === 'up') { markDirty(); S.moveIdx = -1; sendMap(); }
      return;
    }
    if (S.tool === 'delobj' && m.phase === 'down') { pushUndo(); const k = S.map.objects.findIndex((o) => o.type !== 'player' && Math.hypot(o.x - m.x, o.z - m.z) < Math.max(3, S.radius / 2)); if (k >= 0) { S.map.objects.splice(k, 1); markDirty(); sendMap(); } return; }
    if (BRUSH_OPS.includes(S.tool)) {
      if (m.phase === 'down') pushUndo(); if (m.phase === 'up') { markDirty(); return; }
      pendingBrush = { x: m.x, z: m.z }; if (brushBusy) return; brushBusy = true;
      while (pendingBrush) { const p = pendingBrush; pendingBrush = null; try { S.map = await api(E.api.base + '/map-brush', { method: 'POST', body: { path: S.path, op: S.tool, x: p.x, z: p.z, radius: S.radius, strength: S.strength, seed: Math.floor(Math.random() * 1e6), save: false } }); sendMap(); } catch (e) { toast(e.message, 'err'); break; } }
      brushBusy = false;
    }
  }

  // ================================================================= painéis
  const wrapEl = h('div', { class: 'ge-mapview', id: 'ge-mview' });
  const mapSel = h('select', { id: 'ge-msel', 'aria-label': t('Mapa') });
  mapSel.addEventListener('change', () => openMap(mapSel.value));
  async function newMap() {
    const inp = h('input', { value: dim === '3d' ? 'mundo2' : 'fase2', id: 'ge-mnew-name' });
    if (await modal(t('Novo mapa'), h('div', null, propRow(t('Nome'), inp), h('p', { class: 'muted small' }, t('Cria um mapa novo com o gerador (tema e tipo do jogo). Para algo específico, use o prompt.'))), [{ label: t('Cancelar'), value: null }, { label: t('Criar'), value: 'ok', cls: 'primary' }]) !== 'ok') return;
    try { const res = await runJob(E, 'map-ai', { action: 'generate', prompt: '', path: 'maps/' + inp.value.trim().replace(/[^\w-]+/g, '-').toLowerCase() + '.map.json', theme: E.proj.theme, genre: E.proj.genre, mode: 'new' }); await loadList(); await openMap(res.path); toast(t('Mapa criado'), 'ok'); } catch (e) { toast(e.message, 'err'); }
  }
  async function delMap() { if (!S.path || !(await confirmDialog(t('Apagar o mapa «{n}»? Cenas que usam esse mapa ficam sem ele.', { n: S.map.name })))) return; await E.api.del('/map?path=' + encodeURIComponent(S.path)); await loadList(); await openMap((S.maps[0] || {}).path || ''); }
  async function useInScene() {
    const name = E.proj.start || 'main'; try { const sc = await E.api.scene(name); let done = false; const walk = (n) => { if (!done && (n.type === 'TileMap' || n.type === 'Terrain3D')) { n.map = S.path; done = true; } (n.children || []).forEach(walk); }; walk(sc.root); if (!done) { toast(t('A cena inicial não tem um nó de mapa.'), 'err'); return; } await E.api.saveScene(name, sc); toast(t('A cena «{n}» agora usa este mapa.', { n: name }), 'ok'); } catch (e) { toast(e.message, 'err'); }
  }
  const mtool = h('div', { class: 'ge-mtool', id: 'ge-mtool' });
  const props = h('div', { class: 'ge-insp', id: 'ge-mprops' });
  const regionEl = h('div', { class: 'ge-igrp', id: 'ge-mregion' });
  function paintRegion() {
    const r = S.region;
    regionEl.replaceChildren(h('h4', null, t('Região selecionada')), r ? h('div', null, h('p', { class: 'small', id: 'ge-mregion-info' }, dim === '3d' ? t('Centro ({x}, {z}) · raio {r} m', { x: r.x, z: r.z, r: r.radius }) : t('Blocos {x0},{y0} → {x1},{y1}', r)),
      h('div', { class: 'ge-iact' }, btn(t('Gerar de novo aqui'), 'refresh', () => regenRegion(false), 'primary', { id: 'ge-mregen' }), btn(t('Descartar'), 'x', () => { S.region = null; if (dim === '3d') send({ geCmd: 'marker', kind: 'region', x: null }); paintRegion(); draw(); }))) : h('p', { class: 'muted small' }, dim === '3d' ? t('Use a ferramenta «Região» e clique no relevo; ajuste o raio.') : t('Use a ferramenta «Região» e arraste sobre os blocos.')),
      h('p', { class: 'muted small' }, t('O prompt à esquerda vale para a região: “adicione 3 casas aqui”, “um lago”, “mais inimigos”…')));
  }
  async function regenRegion(withPrompt) {
    if (!S.region) { toast(t('Selecione uma região primeiro.')); return; } const prompt = (document.querySelector('#ge-composer-map textarea') || {}).value || '';
    try { toast(t('Gerando a região de novo…')); const res = await runJob(E, 'map-ai', { action: 'regen_region', path: S.path, region: S.region, prompt, theme: S.map.theme, save: true, team: pp.team.get() }); S.map = res.map; paintStatus(); if (dim === '3d') sendMap(); else draw(); toast(t('Região atualizada'), 'ok'); } catch (e) { toast(e.message, 'err'); }
  }
  function paintTools() {
    const T2 = [['region', 'select', 'Região (selecionar pontos)'], ['paint', 'brush', 'Pintar bloco'], ['erase', 'eraser', 'Apagar bloco'], ['object', 'plus', 'Colocar objeto'], ['move', 'move', 'Mover objeto (arraste; setas movem o escolhido)'], ['delobj', 'trash', 'Remover objeto'], ['pan', 'columns', 'Deslocar']];
    if (S.map && S.map.heights) T2.splice(3, 0, ['height', 'mountain', 'Altura (Shift/Alt = baixar)']);
    const T3 = [['region', 'select', 'Região (selecionar um ponto)'], ['raise', 'mountain', 'Subir o relevo'], ['lower', 'drop', 'Descer o relevo'], ['smooth', 'wand', 'Suavizar'], ['flatten', 'grid', 'Aplainar'], ['noise', 'bolt', 'Ruído'], ['place', 'plus', 'Colocar objeto'], ['move', 'move', 'Mover objeto (arraste)'], ['delobj', 'trash', 'Remover objeto']];
    mtool.replaceChildren(...(dim === '3d' ? T3 : T2).map(([id, ic, label]) => h('button', { type: 'button', class: 'btn sm' + (S.tool === id ? ' on' : ''), dataset: { tool: id }, title: t(label), 'aria-label': t(label), 'aria-pressed': String(S.tool === id), onclick: () => { S.tool = id; paintTools(); paintProps(); if (dim === '3d') sendTool(); } }, icon(ic, 14))),
      h('span', { class: 'grow' }), ibtn(t('Desfazer'), 'undo', undo, '', { id: 'ge-mundo' }), dim === '2d' ? ibtn(t('Enquadrar'), 'fit', () => { fit(); draw(); }) : ibtn(t('Enquadrar'), 'fit', () => send({ geCmd: 'frame' })), status);
  }
  function paintProps() {
    const m = S.map; if (!m) { props.replaceChildren(h('p', { class: 'muted small' }, t('Sem mapa. Gere um com o prompt ou crie um novo.'))); return; }
    const nameIn = h('input', { value: m.name, id: 'ge-mname' }); nameIn.addEventListener('change', () => { m.name = nameIn.value.trim() || m.name; markDirty(); });
    const themeSel = h('select', { id: 'ge-mtheme' }, cat.themes.map((x) => h('option', { value: x, selected: m.theme === x }, t(THEME_LABEL[x] || x)))); themeSel.addEventListener('change', () => { m.theme = themeSel.value; markDirty(); draw(); });
    const parts = [h('div', { class: 'ge-igrp' }, h('h4', null, t('Mapa')), propRow(t('Nome'), nameIn), propRow(t('Tema'), themeSel), h('div', { class: 'ge-iact' }, btn(t('Usar na cena inicial'), 'check', useInScene, '', { id: 'ge-muse' }), btn(t('Apagar'), 'trash', delMap, 'danger')))];
    if (dim === '3d') {
      const biome = h('select', { id: 'ge-mbiome' }, cat.biomes.map((x) => h('option', { value: x, selected: m.biome === x }, t(BIOME_LABEL[x] || x)))); biome.addEventListener('change', () => { m.biome = biome.value; markDirty(); });
      const wl = h('input', { type: 'range', min: 0, max: 60, value: Math.round((m.water_level || 0) * 100) }); wl.addEventListener('input', () => { m.water_level = wl.value / 100; markDirty(); sendMap(); });
      parts.push(h('div', { class: 'ge-igrp' }, h('h4', null, t('Relevo')), propRow(t('Bioma'), biome), propRow(t('Nível da água'), wl), propRow(t('Altura máx. (m)'), numInput(m.height, (v) => { m.height = v; markDirty(); sendMap(); }, { min: 1, max: 300 })), propRow(t('Tamanho (m)'), numInput(m.size, (v) => { m.size = v; markDirty(); sendMap(); }, { min: 20, max: 2000 }))));
      const rad = h('input', { type: 'range', min: 3, max: 60, value: S.radius, id: 'ge-mradius' }), str = h('input', { type: 'range', min: 5, max: 100, value: Math.round(S.strength * 100) });
      rad.addEventListener('input', () => { S.radius = +rad.value; if (S.region) S.region.radius = S.radius; sendTool(); paintRegion(); }); str.addEventListener('input', () => { S.strength = str.value / 100; });
      parts.push(h('div', { class: 'ge-igrp' }, h('h4', null, t('Pincel')), propRow(t('Raio (m)'), rad), propRow(t('Força'), str)));
      parts.push(h('div', { class: 'ge-igrp' }, h('h4', null, t('Objeto a colocar')), h('div', { class: 'ge-pal', id: 'ge-mobjs' }, OBJ3D.map((o) => h('button', { type: 'button', class: S.obj === o ? 'on' : '', dataset: { obj: o }, onclick: () => { S.obj = o; S.tool = 'place'; paintTools(); paintProps(); sendTool(); } }, OBJ_EMOJI[o], t(OPT_LABEL[o] || o))))));
    } else {
      parts.push(h('div', { class: 'ge-igrp' }, h('h4', null, t('Blocos')), h('div', { class: 'ge-pal', id: 'ge-mpal' }, Object.entries(m.palette).map(([id, p]) => h('button', { type: 'button', class: S.tile === id && S.tool === 'paint' ? 'on' : '', dataset: { tile: id }, title: t(p.name), onclick: () => { S.tile = id; S.tool = 'paint'; paintTools(); paintProps(); } }, h('i', { style: { background: p.color } }), t(p.name))))));
      parts.push(h('div', { class: 'ge-igrp' }, h('h4', null, t('Objeto a colocar')), h('div', { class: 'ge-pal', id: 'ge-mobjs' }, OBJ2D.map((o) => h('button', { type: 'button', class: S.obj === o && S.tool === 'object' ? 'on' : '', dataset: { obj: o }, onclick: () => { S.obj = o; S.tool = 'object'; paintTools(); paintProps(); } }, OBJ_EMOJI[o], t(OPT_LABEL[o] || o))))));
    }
    props.replaceChildren(...parts, regionEl);
  }
  function paintAll(full = true) { mapSel.replaceChildren(...S.maps.map((m) => h('option', { value: m.path, selected: m.path === S.path }, m.name + ' · ' + m.path.replace('maps/', '')))); mapSel.value = S.path; paintTools(); paintProps(); paintRegion(); paintStatus(); }

  // ================================================================= IA (mapa inteiro, ajustes e região)
  const gen = { theme: '', size: 'medium', genre: '', overwrite: false };
  const themeSel = h('select', { class: 'team-sel', id: 'ge-mp-theme', title: t('Tema'), 'aria-label': t('Tema') }, [['', t('Tema: automático')], ...cat.themes.map((x) => [x, t(THEME_LABEL[x] || x)])].map(([v, l]) => h('option', { value: v }, l))); themeSel.addEventListener('change', () => { gen.theme = themeSel.value; });
  const sizeSel = h('select', { class: 'team-sel', id: 'ge-mp-size', title: t('Tamanho'), 'aria-label': t('Tamanho') }, Object.keys(SIZE_LABEL).map((k) => h('option', { value: k, selected: k === 'medium' }, t(SIZE_LABEL[k])))); sizeSel.addEventListener('change', () => { gen.size = sizeSel.value; });
  const genreSel = dim === '3d' ? null : h('select', { class: 'team-sel', id: 'ge-mp-genre', title: t('Gênero do jogo'), 'aria-label': t('Gênero do jogo') }, [['', t('Gênero: o do jogo')], ...Object.entries(cat.genres).filter(([id, g]) => g.kinds.some((k) => cat.kinds[k].dim === '2d') && ['platformer', 'topdown', 'shooter', 'iso'].includes(id)).map(([id]) => [id, t(GENRE_LABEL[id])])].map(([v, l]) => h('option', { value: v }, l)));
  if (genreSel) genreSel.addEventListener('change', () => { gen.genre = genreSel.value; });
  const modeSel = h('select', { class: 'team-sel', id: 'ge-mp-mode', title: t('O que o prompt faz'), 'aria-label': t('O que o prompt faz') }, [['generate', t('Mapa novo')], ['edit', t('Ajustar este mapa')]].map(([v, l]) => h('option', { value: v }, l)));
  let mode = 'generate'; modeSel.addEventListener('change', () => { mode = modeSel.value; });
  const pp = promptPanel(E, {
    tab: 'map', endpoint: 'map-ai', title: t('Prompt de mapa'), placeholder: dim === '3d' ? t('Descreva o mundo: “ilha vulcânica com 2 vilas, muitas árvores e um lago”…') : t('Descreva a fase: “plataforma de caverna longa com muitos espinhos e moedas”…'),
    intro: t('Gere o mapa inteiro de um prompt, ou ajuste o atual. Selecione uma região no mapa para gerar de novo só aquele pedaço ou colocar coisas ali.'),
    hints: dim === '3d' ? [t('Ilha tropical com uma vila e muitas palmeiras'), t('Montanhas nevadas com 3 casas e um lago'), t('Deserto com pedras e poucos inimigos')] : [t('Fase de floresta longa com muitas moedas'), t('Labirinto de caverna com chaves e inimigos'), t('Fase curta e fácil de plataforma')],
    tools: [h('span', { class: 'tool' }, modeSel), h('span', { class: 'tool' }, themeSel), h('span', { class: 'tool' }, sizeSel), genreSel ? h('span', { class: 'tool' }, genreSel) : null].filter(Boolean),
    body: () => ({ action: S.region && mode === 'edit' ? 'regen_region' : mode === 'edit' ? 'edit' : 'generate', path: mode === 'edit' || S.region ? S.path : '', theme: gen.theme || (mode === 'edit' && S.map ? S.map.theme : ''), length: gen.size, genre: gen.genre, region: S.region && mode === 'edit' ? S.region : undefined, save: true, overwrite: false }),
    onResult: async (res) => { await loadList(); await openMap(res.path); toast(t('Mapa pronto'), 'ok'); },
  });

  // ================================================================= montagem
  const toolbar = h('div', { class: 'ge-vtool' }, mapSel, ibtn(t('Novo mapa'), 'plus', newMap, '', { id: 'ge-mnew' }), h('span', { class: 'grow' }));
  const center = h('section', { class: 'ge-center' }, toolbar, mtool, wrapEl);
  const right = h('aside', { class: 'ge-right' }, h('div', { class: 'ge-ph' }, h('b', null, t('Propriedades'))), props);
  body.replaceChildren(h('div', { class: 'ge-grid ge-map' }, h('div', { class: 'ge-left' }, pp.el), center, right));
  if (dim === '3d') setup3D(wrapEl); else setup2D(wrapEl);
  await loadList(); paintAll();
  const initial = (S.maps.find((m) => m.path === ((E.ctx || {}).map)) || S.maps[0] || {}).path;
  if (initial) await openMap(initial); else { paintAll(); }
  E.onCleanup(() => { if (!S.saved && S.map && S.path) E.api.saveMap(S.path, S.map).catch(() => {}); });
}
