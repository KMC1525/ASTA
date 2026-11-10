// Game Engine → Assets: inspirada no Krita. Prompt à esquerda (gerar/editar arte com IA, com ou sem fundo), tela de edição no centro (pincel, borracha, balde, seleção de pontos, mover/girar/redimensionar)
// e propriedades + camadas (com pastas e subpastas) à direita. As imagens em camadas ficam em editor/assets/; «Aplicar ao jogo» grava o PNG final em game/assets/images/.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { b64ToBlob, blobToDataUrl, btn, flatFiles, ibtn, numInput, promptPanel, propRow, stem } from '../engine_ui.js';
import { confirmDialog, debounce, h, icon, modal, toast } from '../ui.js';

const BLENDS = [['source-over', 'Normal'], ['multiply', 'Multiplicar'], ['screen', 'Tela'], ['overlay', 'Sobrepor'], ['darken', 'Escurecer'], ['lighten', 'Clarear'], ['color-dodge', 'Subexpor cor'], ['difference', 'Diferença']];
const TOOLS = [['move', 'move', 'Mover / girar / redimensionar a camada (V)'], ['brush', 'brush', 'Pincel (B)'], ['eraser', 'eraser', 'Borracha (E)'], ['bucket', 'bucket', 'Balde de tinta (G)'], ['pick', 'eye', 'Conta-gotas (I)'],
  ['rect', 'select', 'Selecionar retângulo (M)'], ['lasso', 'lasso', 'Selecionar à mão livre (L)'], ['sbrush', 'wand', 'Selecionar pintando (S)'], ['pan', 'columns', 'Deslocar a tela (H / Espaço)']];
let uid = 0; const nid = () => 'l' + Date.now().toString(36) + (++uid);
const mkCanvas = (w, h2) => { const c = document.createElement('canvas'); c.width = w; c.height = h2; return c; };
const ctxOf = (c) => c.getContext('2d', { willReadFrequently: true });

export default async function render(body, E) {
  const D = { name: 'sem-nome', w: 512, h: 512, layers: [], sel: '', mask: null, hasMask: false, dirty: false, saved: '' };
  const V = { zoom: 1, ox: 20, oy: 20, tool: 'brush', color: '#e63946', size: 18, opacity: 1, hardness: 0.8, tol: 40 };
  const reg = new Map();   // id -> canvas (as camadas apagadas continuam aqui para o desfazer)
  let undo = [], redo = [], drag = null, raf = 0, spaceDown = false, lastPos = null;
  const view = h('canvas', { id: 'ge-acanvas', tabindex: 0, 'aria-label': t('Tela de edição') });
  const wrap = h('div', { class: 'ge-canvaswrap', id: 'ge-awrap' }, view);
  const vctx = view.getContext('2d');

  // ---------------------------------------------------------------- modelo
  const walk = (nodes, fn, parent) => nodes.forEach((n) => { fn(n, parent); if (n.type === 'group') walk(n.children, fn, n); });
  const findNode = (id) => { let out = null; walk(D.layers, (n, p) => { if (n.id === id) out = { n, parent: p }; }); return out; };
  const listOf = (info) => (info && info.parent ? info.parent.children : D.layers);
  const selNode = () => (D.sel ? (findNode(D.sel) || {}).n : null);
  const activeLayer = () => { const n = selNode(); if (n && n.type === 'layer') return n; let out = null; walk(D.layers, (x) => { if (x.type === 'layer' && !out) out = x; }); return out; };
  function newLayer(name, cv) { const c = cv || mkCanvas(D.w, D.h); const l = { id: nid(), type: 'layer', name: name || t('Camada'), visible: true, locked: false, opacity: 1, blend: 'source-over', x: D.w / 2, y: D.h / 2, rot: 0, sx: 1, sy: 1, canvas: c, fresh: true }; reg.set(l.id, c); return l; }
  function newGroup(name) { return { id: nid(), type: 'group', name: name || t('Pasta'), visible: true, locked: false, opacity: 1, blend: 'source-over', open: true, children: [] }; }
  const structure = (nodes) => nodes.map((n) => { const c = Object.assign({}, n); if (n.type === 'group') c.children = structure(n.children); else { c.cid = n.id; delete c.canvas; } return c; });
  const inflate = (nodes) => nodes.map((n) => { const c = Object.assign({}, n); if (n.type === 'group') c.children = inflate(n.children); else { c.canvas = reg.get(n.cid); delete c.cid; } return c; });
  function snap(layerIds) {
    const px = []; (layerIds || []).forEach((id) => { const cv = reg.get(id); if (cv) px.push([id, ctxOf(cv).getImageData(0, 0, cv.width, cv.height)]); });
    return { tree: structure(D.layers), px, sel: D.sel };
  }
  function pushUndo(layerIds) { undo.push(snap(layerIds)); if (undo.length > 18) undo.shift(); redo = []; markDirty(); }
  function restore(entry) {
    const cur = { tree: structure(D.layers), px: entry.px.map(([id]) => { const cv = reg.get(id); return [id, ctxOf(cv).getImageData(0, 0, cv.width, cv.height)]; }), sel: D.sel };
    D.layers = inflate(entry.tree); D.sel = entry.sel; entry.px.forEach(([id, data]) => { ctxOf(reg.get(id)).putImageData(data, 0, 0); });
    paintLayers(); paintProps(); draw(); markDirty(); return cur;
  }
  const doUndo = () => { const e = undo.pop(); if (e) redo.push(restore(e)); }, doRedo = () => { const e = redo.pop(); if (e) undo.push(restore(e)); };

  // ---------------------------------------------------------------- desenho (composição)
  function drawNode(ctx, n) {
    if (!n.visible) return;
    ctx.save(); ctx.globalAlpha *= n.opacity; ctx.globalCompositeOperation = n.blend || 'source-over';
    if (n.type === 'group') {
      if (n.opacity < 1 || (n.blend && n.blend !== 'source-over')) { const t2 = mkCanvas(D.w, D.h), c2 = t2.getContext('2d'); n.children.slice().reverse().forEach((c) => drawNode(c2, c)); ctx.drawImage(t2, 0, 0); }
      else { ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = n.opacity; n.children.slice().reverse().forEach((c) => drawNode(ctx, c)); }
    } else { ctx.translate(n.x, n.y); ctx.rotate(n.rot * Math.PI / 180); ctx.scale(n.sx, n.sy); ctx.drawImage(n.canvas, -n.canvas.width / 2, -n.canvas.height / 2); }
    ctx.restore();
  }
  function composite() { const c = mkCanvas(D.w, D.h), x = c.getContext('2d'); D.layers.slice().reverse().forEach((n) => drawNode(x, n)); return c; }
  const toDoc = (e) => { const r = view.getBoundingClientRect(); return { x: (e.clientX - r.left - V.ox) / V.zoom, y: (e.clientY - r.top - V.oy) / V.zoom }; };
  function toLocal(l, p) { const dx = p.x - l.x, dy = p.y - l.y, a = -l.rot * Math.PI / 180, c = Math.cos(a), s = Math.sin(a); return { x: (dx * c - dy * s) / l.sx + l.canvas.width / 2, y: (dx * s + dy * c) / l.sy + l.canvas.height / 2 }; }
  function resizeView() { const r = wrap.getBoundingClientRect(); view.width = Math.max(10, Math.round(r.width)); view.height = Math.max(10, Math.round(r.height)); draw(); }
  function draw() {
    if (raf) return; raf = requestAnimationFrame(() => {
      raf = 0; vctx.clearRect(0, 0, view.width, view.height); vctx.save(); vctx.translate(V.ox, V.oy); vctx.scale(V.zoom, V.zoom);
      vctx.imageSmoothingEnabled = V.zoom < 2; vctx.fillStyle = 'rgba(255,255,255,0.0)';
      vctx.save(); vctx.shadowColor = 'rgba(0,0,0,.5)'; vctx.shadowBlur = 20; vctx.fillStyle = '#111'; vctx.fillRect(0, 0, D.w, D.h); vctx.restore();
      const chk = 16 / V.zoom; vctx.fillStyle = '#2c2c2c'; vctx.fillRect(0, 0, D.w, D.h); vctx.fillStyle = '#3a3a3a'; for (let y = 0; y < D.h; y += chk * 2) for (let x = 0; x < D.w; x += chk * 2) { vctx.fillRect(x, y, chk, chk); vctx.fillRect(x + chk, y + chk, chk, chk); }
      vctx.drawImage(composite(), 0, 0);
      if (D.hasMask) { vctx.save(); const ov = mkCanvas(D.w, D.h), oc = ov.getContext('2d'); oc.drawImage(D.mask, 0, 0); oc.globalCompositeOperation = 'source-in'; oc.fillStyle = 'rgba(80,160,255,.38)'; oc.fillRect(0, 0, D.w, D.h); vctx.drawImage(ov, 0, 0); vctx.restore(); }
      const l = selNode(); if (l && V.tool === 'move' && l.type === 'layer') overlay(l);
      if (drag && drag.kind === 'rect') { vctx.strokeStyle = '#7cb7ff'; vctx.setLineDash([6 / V.zoom, 4 / V.zoom]); vctx.lineWidth = 1.5 / V.zoom; vctx.strokeRect(drag.a.x, drag.a.y, drag.b.x - drag.a.x, drag.b.y - drag.a.y); }
      if (drag && drag.kind === 'lasso') { vctx.strokeStyle = '#7cb7ff'; vctx.setLineDash([6 / V.zoom, 4 / V.zoom]); vctx.lineWidth = 1.5 / V.zoom; vctx.beginPath(); drag.pts.forEach((p, i) => (i ? vctx.lineTo(p.x, p.y) : vctx.moveTo(p.x, p.y))); vctx.stroke(); }
      vctx.restore();
      if ((V.tool === 'brush' || V.tool === 'eraser' || V.tool === 'sbrush') && lastPos) { vctx.strokeStyle = '#fff'; vctx.lineWidth = 1; vctx.beginPath(); vctx.arc(lastPos.sx, lastPos.sy, Math.max(2, V.size * V.zoom / 2), 0, 7); vctx.stroke(); }
    });
  }
  function corners(l) { const hw = l.canvas.width * l.sx / 2, hh = l.canvas.height * l.sy / 2, a = l.rot * Math.PI / 180, c = Math.cos(a), s = Math.sin(a); return [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]].map(([x, y]) => ({ x: l.x + x * c - y * s, y: l.y + x * s + y * c })); }
  function overlay(l) {
    const cs = corners(l); vctx.strokeStyle = '#ffd166'; vctx.lineWidth = 1.5 / V.zoom; vctx.setLineDash([]); vctx.beginPath(); cs.forEach((p, i) => (i ? vctx.lineTo(p.x, p.y) : vctx.moveTo(p.x, p.y))); vctx.closePath(); vctx.stroke();
    vctx.fillStyle = '#ffd166'; cs.forEach((p) => vctx.fillRect(p.x - 4 / V.zoom, p.y - 4 / V.zoom, 8 / V.zoom, 8 / V.zoom));
    const top = rotHandle(l); vctx.beginPath(); vctx.moveTo((cs[0].x + cs[1].x) / 2, (cs[0].y + cs[1].y) / 2); vctx.lineTo(top.x, top.y); vctx.stroke(); vctx.beginPath(); vctx.arc(top.x, top.y, 5 / V.zoom, 0, 7); vctx.fill();
  }
  function rotHandle(l) { const a = l.rot * Math.PI / 180, hh = l.canvas.height * l.sy / 2 + 28 / V.zoom; return { x: l.x + Math.sin(a) * hh, y: l.y - Math.cos(a) * hh }; }
  function fit() { const r = wrap.getBoundingClientRect(); V.zoom = Math.max(0.05, Math.min(8, Math.min((r.width - 40) / D.w, (r.height - 40) / D.h))); V.ox = (r.width - D.w * V.zoom) / 2; V.oy = (r.height - D.h * V.zoom) / 2; draw(); paintOpts(); }

  // ---------------------------------------------------------------- ferramentas de pintura
  function stroke(l, from, to, erase) {
    const ctx = ctxOf(l.canvas); const a = toLocal(l, from), b = toLocal(l, to), sc = (l.sx + l.sy) / 2;
    ctx.save(); ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.lineWidth = V.size / sc; ctx.globalAlpha = V.opacity; ctx.globalCompositeOperation = erase ? 'destination-out' : 'source-over'; ctx.strokeStyle = V.color; ctx.fillStyle = V.color;
    if (V.hardness < 0.95) { ctx.shadowColor = erase ? '#000' : V.color; ctx.shadowBlur = (1 - V.hardness) * V.size / sc * 0.9; ctx.shadowOffsetX = 0; ctx.shadowOffsetY = 0; }
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x + 0.01, b.y); ctx.stroke(); ctx.restore();
  }
  function maskStroke(from, to, erase) { const c = D.mask.getContext('2d'); c.save(); c.lineCap = 'round'; c.lineWidth = V.size; c.strokeStyle = '#fff'; c.globalCompositeOperation = erase ? 'destination-out' : 'source-over'; c.beginPath(); c.moveTo(from.x, from.y); c.lineTo(to.x + 0.01, to.y); c.stroke(); c.restore(); D.hasMask = true; }
  function ensureMask() { if (!D.mask) D.mask = mkCanvas(D.w, D.h); }
  function clearMask() { if (D.mask) D.mask.getContext('2d').clearRect(0, 0, D.w, D.h); D.hasMask = false; draw(); paintOpts(); }
  function maskHasPixels() { if (!D.mask) return false; const d = ctxOf(D.mask).getImageData(0, 0, D.w, D.h).data; for (let i = 3; i < d.length; i += 4) if (d[i] > 8) return true; return false; }
  function bucket(l, p) {
    const lp = toLocal(l, p), x = Math.round(lp.x), y = Math.round(lp.y), cv = l.canvas, w = cv.width, hh = cv.height; if (x < 0 || y < 0 || x >= w || y >= hh) return;
    const ctx = ctxOf(cv), img = ctx.getImageData(0, 0, w, hh), d = img.data, i0 = (y * w + x) * 4, t0 = [d[i0], d[i0 + 1], d[i0 + 2], d[i0 + 3]];
    const col = hexRgb(V.color), tol = V.tol * 4.4, ok = (i) => Math.abs(d[i] - t0[0]) + Math.abs(d[i + 1] - t0[1]) + Math.abs(d[i + 2] - t0[2]) + Math.abs(d[i + 3] - t0[3]) <= tol;
    const mk = D.hasMask ? ctxOf(D.mask).getImageData(0, 0, D.w, D.h).data : null, inMask = (px, py) => { if (!mk) return true; const dd = toDoc2(l, px, py); const mx = Math.round(dd.x), my = Math.round(dd.y); return mx >= 0 && my >= 0 && mx < D.w && my < D.h && mk[(my * D.w + mx) * 4 + 3] > 128; };
    const seen = new Uint8Array(w * hh), st = [[x, y]]; let n = 0;
    while (st.length && n < 4e6) { const [cx, cy] = st.pop(); if (cx < 0 || cy < 0 || cx >= w || cy >= hh) continue; const k = cy * w + cx; if (seen[k]) continue; seen[k] = 1; if (!ok(k * 4)) continue; n++;
      if (inMask(cx, cy)) { d[k * 4] = col[0]; d[k * 4 + 1] = col[1]; d[k * 4 + 2] = col[2]; d[k * 4 + 3] = Math.round(255 * V.opacity); } st.push([cx + 1, cy], [cx - 1, cy], [cx, cy + 1], [cx, cy - 1]); }
    ctx.putImageData(img, 0, 0);
  }
  const toDoc2 = (l, lx, ly) => { const dx = (lx - l.canvas.width / 2) * l.sx, dy = (ly - l.canvas.height / 2) * l.sy, a = l.rot * Math.PI / 180, c = Math.cos(a), s = Math.sin(a); return { x: l.x + dx * c - dy * s, y: l.y + dx * s + dy * c }; };
  const hexRgb = (hx) => { const n = parseInt(hx.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; };
  function pickColor(p) { const c = composite(), x = Math.round(p.x), y = Math.round(p.y); if (x < 0 || y < 0 || x >= D.w || y >= D.h) return; const d = ctxOf(c).getImageData(x, y, 1, 1).data; if (d[3] > 0) { V.color = '#' + [d[0], d[1], d[2]].map((v) => v.toString(16).padStart(2, '0')).join(''); paintOpts(); } }
  // remove o fundo: o que se parece com a cor das bordas (a partir das bordas, sem comer o miolo) vira transparente
  function removeBackground(cv, tol) {
    const ctx = ctxOf(cv), w = cv.width, hh = cv.height, img = ctx.getImageData(0, 0, w, hh), d = img.data; tol = (tol == null ? 38 : tol) * 4.4;
    const samples = []; for (let x = 0; x < w; x += Math.max(1, w >> 5)) { samples.push((x) * 4, ((hh - 1) * w + x) * 4); } for (let y = 0; y < hh; y += Math.max(1, hh >> 5)) { samples.push((y * w) * 4, (y * w + w - 1) * 4); }
    const bg = [0, 0, 0]; samples.forEach((i) => { bg[0] += d[i]; bg[1] += d[i + 1]; bg[2] += d[i + 2]; }); bg[0] /= samples.length; bg[1] /= samples.length; bg[2] /= samples.length;
    const near = (i) => d[i + 3] < 8 || Math.abs(d[i] - bg[0]) + Math.abs(d[i + 1] - bg[1]) + Math.abs(d[i + 2] - bg[2]) <= tol;
    const seen = new Uint8Array(w * hh), st = [];
    for (let x = 0; x < w; x++) { st.push([x, 0], [x, hh - 1]); } for (let y = 0; y < hh; y++) { st.push([0, y], [w - 1, y]); }
    while (st.length) { const [cx, cy] = st.pop(); if (cx < 0 || cy < 0 || cx >= w || cy >= hh) continue; const k = cy * w + cx; if (seen[k]) continue; seen[k] = 1; if (!near(k * 4)) continue; d[k * 4 + 3] = 0; st.push([cx + 1, cy], [cx - 1, cy], [cx, cy + 1], [cx, cy - 1]); }
    for (let k = 0; k < w * hh; k++) { if (d[k * 4 + 3] === 0) continue; const x = k % w, y = (k / w) | 0; let tr = 0; if (x > 0 && d[(k - 1) * 4 + 3] === 0) tr++; if (x < w - 1 && d[(k + 1) * 4 + 3] === 0) tr++; if (y > 0 && d[(k - w) * 4 + 3] === 0) tr++; if (y < hh - 1 && d[(k + w) * 4 + 3] === 0) tr++; if (tr) d[k * 4 + 3] = Math.round(d[k * 4 + 3] * (1 - 0.35 * tr)); }
    ctx.putImageData(img, 0, 0);
  }
  function trim(l) {
    const cv = l.canvas, ctx = ctxOf(cv), d = ctx.getImageData(0, 0, cv.width, cv.height).data; let x0 = cv.width, y0 = cv.height, x1 = -1, y1 = -1;
    for (let y = 0; y < cv.height; y++) for (let x = 0; x < cv.width; x++) if (d[(y * cv.width + x) * 4 + 3] > 8) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    if (x1 < 0) return; const nc = mkCanvas(x1 - x0 + 1, y1 - y0 + 1); nc.getContext('2d').drawImage(cv, -x0, -y0);
    const cx = (x0 + x1) / 2 - cv.width / 2, cy = (y0 + y1) / 2 - cv.height / 2, a = l.rot * Math.PI / 180;
    l.x += (cx * l.sx) * Math.cos(a) - (cy * l.sy) * Math.sin(a); l.y += (cx * l.sx) * Math.sin(a) + (cy * l.sy) * Math.cos(a); l.canvas = nc; reg.set(l.id, nc);
  }

  // ---------------------------------------------------------------- mouse
  function onDown(e) {
    view.focus(); const p = toDoc(e), sp = { sx: e.clientX - view.getBoundingClientRect().left, sy: e.clientY - view.getBoundingClientRect().top };
    if (e.button === 1 || e.button === 2 || V.tool === 'pan' || spaceDown) { drag = { kind: 'pan', x: e.clientX, y: e.clientY, ox: V.ox, oy: V.oy }; wrap.classList.add('pan'); view.setPointerCapture(e.pointerId); return; }
    const l = activeLayer(); view.setPointerCapture(e.pointerId); lastPos = Object.assign({}, sp, p);
    if (V.tool === 'pick') { pickColor(p); return; }
    if (V.tool === 'rect') { drag = { kind: 'rect', a: p, b: p, add: e.shiftKey }; return; }
    if (V.tool === 'lasso') { drag = { kind: 'lasso', pts: [p], add: e.shiftKey }; return; }
    if (V.tool === 'sbrush') { ensureMask(); drag = { kind: 'sbrush', last: p, erase: e.altKey }; maskStroke(p, p, e.altKey); draw(); return; }
    if (!l || l.locked || !l.visible) { if (l && l.locked) toast(t('A camada está travada.')); return; }
    if (V.tool === 'bucket') { pushUndo([l.id]); bucket(l, p); markDirty(); draw(); paintLayers(); return; }
    if (V.tool === 'move') {
      const cs = corners(l), hit = (q) => Math.hypot(q.x - p.x, q.y - p.y) < 10 / V.zoom, rh = rotHandle(l);
      if (hit(rh)) { pushUndo([]); drag = { kind: 'rot', l, a0: Math.atan2(p.y - l.y, p.x - l.x), r0: l.rot }; return; }
      if (cs.some(hit)) { pushUndo([]); drag = { kind: 'scale', l, d0: Math.hypot(p.x - l.x, p.y - l.y), s0: [l.sx, l.sy] }; return; }
      pushUndo([]); drag = { kind: 'move', l, p0: p, x0: l.x, y0: l.y }; return;
    }
    // pincel/borracha
    pushUndo([l.id]); drag = { kind: 'paint', l, last: p, erase: V.tool === 'eraser', before: D.hasMask ? ctxOf(l.canvas).getImageData(0, 0, l.canvas.width, l.canvas.height) : null };
    stroke(l, p, p, drag.erase); clipToMask(); draw();
  }
  function clipToMask() { // com uma seleção ativa, a pintura só vale dentro dela
    if (!drag || drag.kind !== 'paint' || !drag.before) return; const l = drag.l, ctx = ctxOf(l.canvas), cur = ctx.getImageData(0, 0, l.canvas.width, l.canvas.height), b = drag.before, mk = ctxOf(D.mask).getImageData(0, 0, D.w, D.h).data;
    for (let y = 0; y < l.canvas.height; y++) for (let x = 0; x < l.canvas.width; x++) { const k = (y * l.canvas.width + x) * 4, dd = toDoc2(l, x, y), mx = Math.round(dd.x), my = Math.round(dd.y); const inside = mx >= 0 && my >= 0 && mx < D.w && my < D.h && mk[(my * D.w + mx) * 4 + 3] > 128; if (!inside) { cur.data[k] = b.data[k]; cur.data[k + 1] = b.data[k + 1]; cur.data[k + 2] = b.data[k + 2]; cur.data[k + 3] = b.data[k + 3]; } }
    ctx.putImageData(cur, 0, 0);
  }
  function onMove(e) {
    const r = view.getBoundingClientRect(), p = toDoc(e); lastPos = { sx: e.clientX - r.left, sy: e.clientY - r.top, x: p.x, y: p.y };
    if (!drag) { if (V.tool === 'brush' || V.tool === 'eraser' || V.tool === 'sbrush') draw(); return; }
    if (drag.kind === 'pan') { V.ox = drag.ox + (e.clientX - drag.x); V.oy = drag.oy + (e.clientY - drag.y); draw(); return; }
    if (drag.kind === 'rect') { drag.b = p; draw(); return; }
    if (drag.kind === 'lasso') { drag.pts.push(p); draw(); return; }
    if (drag.kind === 'sbrush') { maskStroke(drag.last, p, drag.erase); drag.last = p; draw(); return; }
    if (drag.kind === 'move') { drag.l.x = drag.x0 + (p.x - drag.p0.x); drag.l.y = drag.y0 + (p.y - drag.p0.y); draw(); paintPropsSoon(); return; }
    if (drag.kind === 'rot') { drag.l.rot = Math.round((drag.r0 + (Math.atan2(p.y - drag.l.y, p.x - drag.l.x) - drag.a0) * 180 / Math.PI) * 10) / 10; draw(); paintPropsSoon(); return; }
    if (drag.kind === 'scale') { const k = Math.max(0.02, Math.hypot(p.x - drag.l.x, p.y - drag.l.y) / Math.max(1, drag.d0)); drag.l.sx = drag.s0[0] * k; drag.l.sy = drag.s0[1] * k; draw(); paintPropsSoon(); return; }
    if (drag.kind === 'paint') { stroke(drag.l, drag.last, p, drag.erase); clipToMask(); drag.last = p; draw(); }
  }
  function onUp() {
    if (!drag) return; const d = drag; drag = null; wrap.classList.remove('pan');
    if (d.kind === 'rect' || d.kind === 'lasso') {
      ensureMask(); const c = D.mask.getContext('2d'); if (!d.add) c.clearRect(0, 0, D.w, D.h); c.fillStyle = '#fff'; c.beginPath();
      if (d.kind === 'rect') c.rect(Math.min(d.a.x, d.b.x), Math.min(d.a.y, d.b.y), Math.abs(d.b.x - d.a.x), Math.abs(d.b.y - d.a.y)); else d.pts.forEach((q, i) => (i ? c.lineTo(q.x, q.y) : c.moveTo(q.x, q.y)));
      c.fill(); D.hasMask = maskHasPixels(); draw(); paintOpts(); return;
    }
    if (d.kind === 'sbrush') { D.hasMask = maskHasPixels(); paintOpts(); }
    if (d.kind === 'paint') paintLayers(); if (d.kind === 'move' || d.kind === 'rot' || d.kind === 'scale') paintProps(); markDirty();
  }
  view.addEventListener('pointerdown', onDown); view.addEventListener('pointermove', onMove); view.addEventListener('pointerup', onUp); view.addEventListener('pointercancel', onUp); view.addEventListener('contextmenu', (e) => e.preventDefault());
  view.addEventListener('pointerleave', () => { lastPos = null; draw(); });
  view.addEventListener('wheel', (e) => { e.preventDefault(); const r = view.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, f = e.deltaY < 0 ? 1.15 : 1 / 1.15, nz = Math.max(0.05, Math.min(16, V.zoom * f)); V.ox = mx - (mx - V.ox) * nz / V.zoom; V.oy = my - (my - V.oy) * nz / V.zoom; V.zoom = nz; draw(); paintOpts(); }, { passive: false });
  const onKey = (e) => {
    if (!document.body.contains(view) || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || '')) return;
    if (e.code === 'Space') { spaceDown = e.type === 'keydown'; wrap.classList.toggle('pan', spaceDown); if (e.type === 'keydown') e.preventDefault(); return; }
    if (e.type !== 'keydown') return;
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === 'z') { e.preventDefault(); e.shiftKey ? doRedo() : doUndo(); return; } if ((e.ctrlKey || e.metaKey) && k === 'y') { e.preventDefault(); doRedo(); return; }
    if ((e.ctrlKey || e.metaKey) && k === 's') { e.preventDefault(); saveDoc(); return; } if ((e.ctrlKey || e.metaKey) && k === 'd') { e.preventDefault(); selectAllOff(); return; }
    const map = { v: 'move', b: 'brush', e: 'eraser', g: 'bucket', i: 'pick', m: 'rect', l: 'lasso', s: 'sbrush', h: 'pan' }; if (map[k] && !e.ctrlKey && !e.metaKey) { V.tool = map[k]; paintOpts(); draw(); }
    if (k === '[') { V.size = Math.max(1, V.size - 4); paintOpts(); } if (k === ']') { V.size = Math.min(400, V.size + 4); paintOpts(); }
  };
  const selectAllOff = () => clearMask();
  window.addEventListener('keydown', onKey); window.addEventListener('keyup', onKey); E.onCleanup(() => { window.removeEventListener('keydown', onKey); window.removeEventListener('keyup', onKey); });

  // ---------------------------------------------------------------- camadas (painel)
  const layersEl = h('div', { class: 'ge-layers', id: 'ge-layers', role: 'tree', 'aria-label': t('Camadas') });
  function paintLayers() {
    const rows = [];
    const rec = (nodes, depth, parent) => nodes.forEach((n) => {
      const th = n.type === 'layer' ? mkCanvas(26, 26) : null; if (th) { const tc = th.getContext('2d'); const k = Math.min(26 / n.canvas.width, 26 / n.canvas.height); tc.drawImage(n.canvas, (26 - n.canvas.width * k) / 2, (26 - n.canvas.height * k) / 2, n.canvas.width * k, n.canvas.height * k); th.className = 'th'; }
      const row = h('div', { class: 'ge-lrow' + (D.sel === n.id ? ' on' : ''), dataset: { id: n.id, type: n.type }, style: { paddingLeft: 6 + depth * 14 + 'px' }, draggable: 'true', onclick: () => { D.sel = n.id; paintLayers(); paintProps(); draw(); }, ondblclick: () => renameNode(n) },
        n.type === 'group' ? h('button', { type: 'button', title: t('Abrir/fechar'), onclick: (e) => { e.stopPropagation(); n.open = !n.open; paintLayers(); } }, icon(n.open ? 'chevd' : 'chevr', 12)) : h('span', { style: { width: '14px' } }),
        n.type === 'group' ? h('span', { style: { display: 'grid', color: 'var(--muted)' } }, icon('folder', 15)) : th, h('span', { class: 'ln', title: n.name }, n.name),
        h('button', { type: 'button', class: n.visible ? 'on' : '', title: t('Mostrar/ocultar'), onclick: (e) => { e.stopPropagation(); pushUndo([]); n.visible = !n.visible; paintLayers(); draw(); } }, icon(n.visible ? 'eye' : 'eyeoff', 13)),
        h('button', { type: 'button', class: n.locked ? 'on' : '', title: t('Travar'), onclick: (e) => { e.stopPropagation(); n.locked = !n.locked; paintLayers(); } }, icon('lock', 13)));
      row.addEventListener('dragstart', (e) => { e.dataTransfer.setData('text/plain', n.id); });
      row.addEventListener('dragover', (e) => { e.preventDefault(); const r = row.getBoundingClientRect(), y = (e.clientY - r.top) / r.height; row.dataset.drop = n.type === 'group' && y > 0.3 && y < 0.7 ? 'in' : y < 0.5 ? 'before' : 'after'; });
      row.addEventListener('dragleave', () => { delete row.dataset.drop; });
      row.addEventListener('drop', (e) => { e.preventDefault(); const where = row.dataset.drop; delete row.dataset.drop; moveNode(e.dataTransfer.getData('text/plain'), n.id, where); });
      rows.push(row); if (n.type === 'group' && n.open) rec(n.children, depth + 1, n);
    });
    rec(D.layers, 0, null);
    layersEl.replaceChildren(...(rows.length ? rows : [h('div', { class: 'muted small', style: { padding: '10px' } }, t('Sem camadas. Gere uma imagem ou crie uma camada.'))]));
  }
  function moveNode(id, targetId, where) {
    const a = findNode(id), b = findNode(targetId); if (!a || !b || id === targetId) return;
    let p = b.parent; while (p) { if (p.id === id) return; p = (findNode(p.id) || {}).parent; } if (a.n.type === 'group' && b.n.id === a.n.id) return;
    pushUndo([]); listOf(a).splice(listOf(a).indexOf(a.n), 1);
    if (where === 'in' && b.n.type === 'group') { b.n.children.unshift(a.n); b.n.open = true; } else { const list = listOf(b), i = list.indexOf(b.n); list.splice(where === 'before' ? i : i + 1, 0, a.n); }
    paintLayers(); draw();
  }
  async function renameNode(n) { const inp = h('input', { value: n.name }); if (await modal(t('Renomear'), inp, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]) === 'ok' && inp.value.trim()) { n.name = inp.value.trim(); markDirty(); paintLayers(); paintProps(); } }
  function addLayer(name, cv) { const l = newLayer(name, cv), info = D.sel ? findNode(D.sel) : null; pushUndo([]); if (info && info.n.type === 'group') info.n.children.unshift(l); else if (info) listOf(info).splice(listOf(info).indexOf(info.n), 0, l); else D.layers.unshift(l); D.sel = l.id; paintLayers(); paintProps(); draw(); return l; }
  function addGroup() { const g = newGroup(), info = D.sel ? findNode(D.sel) : null; pushUndo([]); if (info) listOf(info).splice(listOf(info).indexOf(info.n), 0, g); else D.layers.unshift(g); D.sel = g.id; paintLayers(); paintProps(); draw(); }
  function dupNode() {
    const info = D.sel && findNode(D.sel); if (!info) return; const copy = (n) => { if (n.type === 'group') return Object.assign({}, n, { id: nid(), name: n.name + ' 2', children: n.children.map(copy) }); const c = mkCanvas(n.canvas.width, n.canvas.height); c.getContext('2d').drawImage(n.canvas, 0, 0); const o = Object.assign({}, n, { id: nid(), name: n.name + ' 2', canvas: c }); reg.set(o.id, c); return o; };
    pushUndo([]); const c = copy(info.n); listOf(info).splice(listOf(info).indexOf(info.n), 0, c); D.sel = c.id; paintLayers(); paintProps(); draw();
  }
  async function delNode() { const info = D.sel && findNode(D.sel); if (!info) return; if (info.n.type === 'group' && info.n.children.length && !(await confirmDialog(t('Apagar a pasta «{n}» e as camadas dentro dela?', { n: info.n.name })))) return; pushUndo([]); listOf(info).splice(listOf(info).indexOf(info.n), 1); D.sel = ''; paintLayers(); paintProps(); draw(); }
  function mergeDown() {
    const info = D.sel && findNode(D.sel); if (!info || info.n.type !== 'layer') return; const list = listOf(info), i = list.indexOf(info.n), below = list[i + 1]; if (!below || below.type !== 'layer') { toast(t('Não há uma camada logo abaixo para mesclar.')); return; }
    pushUndo([below.id]); const tc = ctxOf(below.canvas); tc.save(); tc.translate(below.canvas.width / 2, below.canvas.height / 2); tc.scale(1 / below.sx, 1 / below.sy); tc.rotate(-below.rot * Math.PI / 180); tc.translate(-below.x, -below.y); tc.globalAlpha = info.n.opacity; tc.globalCompositeOperation = info.n.blend; tc.translate(info.n.x, info.n.y); tc.rotate(info.n.rot * Math.PI / 180); tc.scale(info.n.sx, info.n.sy); tc.drawImage(info.n.canvas, -info.n.canvas.width / 2, -info.n.canvas.height / 2); tc.restore();
    list.splice(i, 1); D.sel = below.id; paintLayers(); paintProps(); draw();
  }
  function flattenAll() { pushUndo([]); const c = composite(), l = newLayer(t('Imagem final'), c); D.layers = [l]; D.sel = l.id; paintLayers(); paintProps(); draw(); }

  // ---------------------------------------------------------------- propriedades e opções
  const propsEl = h('div', { class: 'ge-insp', id: 'ge-aprops' });
  const paintPropsSoon = debounce(() => paintProps(), 120);
  function paintProps() {
    const n = selNode();
    const doc = h('div', { class: 'ge-igrp' }, h('h4', null, t('Documento')), propRow(t('Nome'), (() => { const i = h('input', { value: D.name, id: 'ge-aname' }); i.addEventListener('change', () => { D.name = i.value.trim().replace(/[^\w-]+/g, '-').toLowerCase() || 'sem-nome'; i.value = D.name; markDirty(); }); return i; })()),
      propRow(t('Tamanho'), h('span', { class: 'small muted' }, D.w + ' × ' + D.h + ' px')));
    if (!n) { propsEl.replaceChildren(doc, h('p', { class: 'muted small' }, t('Selecione uma camada para ver as propriedades.'))); return; }
    const set = (k, v) => { n[k] = v; markDirty(); draw(); };
    const op = h('input', { type: 'range', min: 0, max: 100, value: Math.round(n.opacity * 100) }); op.addEventListener('input', () => set('opacity', op.value / 100));
    const bl = h('select', null, BLENDS.map(([v, l]) => h('option', { value: v, selected: n.blend === v }, t(l)))); bl.addEventListener('change', () => set('blend', bl.value));
    const grp = [h('div', { class: 'ge-igrp' }, h('h4', null, n.type === 'group' ? t('Pasta') : t('Camada')), propRow(t('Nome'), (() => { const i = h('input', { value: n.name, id: 'ge-lname' }); i.addEventListener('change', () => { n.name = i.value || n.name; paintLayers(); markDirty(); }); return i; })()), propRow(t('Opacidade'), op), propRow(t('Mistura'), bl))];
    if (n.type === 'layer') {
      grp.push(h('div', { class: 'ge-igrp' }, h('h4', null, t('Transformação')), propRow('X', numInput(Math.round(n.x * 10) / 10, (v) => set('x', v))), propRow('Y', numInput(Math.round(n.y * 10) / 10, (v) => set('y', v))), propRow(t('Girar (°)'), numInput(n.rot, (v) => set('rot', v))),
        propRow(t('Escala (%)'), numInput(Math.round(n.sx * 1000) / 10, (v) => { const k = v / 100; n.sx = k; n.sy = Math.sign(n.sy || 1) * k; markDirty(); draw(); })),
        h('div', { class: 'ge-iact' }, btn(t('Espelhar H'), 'columns', () => { pushUndo([]); n.sx = -n.sx; paintProps(); draw(); }), btn(t('Espelhar V'), 'columns', () => { pushUndo([]); n.sy = -n.sy; paintProps(); draw(); }), btn(t('Resetar'), 'refresh', () => { pushUndo([]); Object.assign(n, { x: D.w / 2, y: D.h / 2, rot: 0, sx: 1, sy: 1 }); paintProps(); draw(); }))));
      grp.push(h('div', { class: 'ge-igrp' }, h('h4', null, t('Ferramentas da camada')), h('div', { class: 'ge-iact' }, btn(t('Remover fundo'), 'wand', () => { pushUndo([n.id]); removeBackground(n.canvas, V.tol); paintLayers(); draw(); }, '', { id: 'ge-rmbg' }), btn(t('Cortar ao conteúdo'), 'scissors', () => { pushUndo([n.id]); trim(n); paintLayers(); paintProps(); draw(); }),
        btn(t('Limpar'), 'eraser', () => { pushUndo([n.id]); ctxOf(n.canvas).clearRect(0, 0, n.canvas.width, n.canvas.height); paintLayers(); draw(); })), propRow(t('Tolerância'), (() => { const r = h('input', { type: 'range', min: 5, max: 120, value: V.tol }); r.addEventListener('input', () => { V.tol = +r.value; }); return r; })()),
        h('div', { class: 'ge-iact' }, filterBtn(n, 'Brilho +', 'brightness(1.2)'), filterBtn(n, 'Brilho −', 'brightness(0.8)'), filterBtn(n, 'Contraste', 'contrast(1.25)'), filterBtn(n, 'Matiz', 'hue-rotate(40deg)'), filterBtn(n, 'P&B', 'grayscale(1)'), filterBtn(n, 'Inverter', 'invert(1)'))));
    }
    propsEl.replaceChildren(doc, ...grp);
  }
  function filterBtn(n, label, f) { return btn(t(label), '', () => { pushUndo([n.id]); const c = mkCanvas(n.canvas.width, n.canvas.height), x = c.getContext('2d'); x.filter = f; x.drawImage(n.canvas, 0, 0); const dx = ctxOf(n.canvas); dx.clearRect(0, 0, c.width, c.height); dx.drawImage(c, 0, 0); paintLayers(); draw(); }); }
  const optsEl = h('div', { class: 'ge-aopts', id: 'ge-aopts' });
  function paintOpts() {
    const rng = (min, max, key, scale = 1, w) => { const r = h('input', { type: 'range', min, max, value: V[key] * scale, style: w ? { width: w } : null }); r.addEventListener('input', () => { V[key] = +r.value / scale; paintOptsLabel(); }); return r; };
    const color = h('input', { type: 'color', value: V.color, id: 'ge-acolor', title: t('Cor') }); color.addEventListener('input', () => { V.color = color.value; });
    optsEl.replaceChildren(h('span', null, t('Cor')), color, h('span', null, t('Tamanho') + ' ' + V.size), rng(1, 300, 'size'), h('span', null, t('Opacidade')), rng(5, 100, 'opacity', 100, '80px'), h('span', null, t('Dureza')), rng(0, 100, 'hardness', 100, '80px'),
      h('span', { class: 'grow' }), h('span', { class: 'small' }, Math.round(V.zoom * 100) + '%'), ibtn(t('Enquadrar'), 'fit', fit), ibtn(t('Zoom 100%'), 'zoomin', () => { V.zoom = 1; draw(); paintOpts(); }));
    paintTools(); paintSelBar();
  }
  const paintOptsLabel = () => { const sp = optsEl.children[2]; if (sp) sp.textContent = t('Tamanho') + ' ' + V.size; };
  const toolsEl = h('div', { class: 'ge-atools', id: 'ge-atools', role: 'toolbar', 'aria-label': t('Ferramentas') });
  const paintTools = () => toolsEl.replaceChildren(...TOOLS.map(([id, ic, label]) => h('button', { type: 'button', class: 'ge-atool' + (V.tool === id ? ' on' : ''), dataset: { tool: id }, title: t(label), 'aria-label': t(label), 'aria-pressed': String(V.tool === id), onclick: () => { V.tool = id; paintTools(); draw(); } }, icon(ic, 17))));
  const selBar = h('div', { class: 'ge-selhint hidden', id: 'ge-selbar' });
  function paintSelBar() { selBar.classList.toggle('hidden', !D.hasMask); selBar.replaceChildren(h('span', null, icon('select', 13), ' ', t('Há uma seleção ativa: pintar e editar com IA só afetam a área selecionada.')), btn(t('Inverter'), 'refresh', invertMask), btn(t('Limpar seleção'), 'x', clearMask, '', { id: 'ge-clearsel' })); }
  function invertMask() { ensureMask(); const c = D.mask.getContext('2d'), tmp = mkCanvas(D.w, D.h), tx = tmp.getContext('2d'); tx.fillStyle = '#fff'; tx.fillRect(0, 0, D.w, D.h); tx.globalCompositeOperation = 'destination-out'; tx.drawImage(D.mask, 0, 0); c.clearRect(0, 0, D.w, D.h); c.drawImage(tmp, 0, 0); D.hasMask = maskHasPixels(); draw(); paintOpts(); }

  // ---------------------------------------------------------------- salvar / abrir
  const status = h('span', { class: 'small dim', id: 'ge-astatus' });
  const markDirty = () => { D.dirty = true; status.textContent = t('não salvo'); autosave(); };
  const autosave = debounce(() => { if (D.layers.length) saveDoc(true); }, 4000);
  const layerPath = (l) => `assets/${D.name}/${l.id}.png`;
  async function saveDoc(quiet) {
    if (!D.layers.length) return; const files = [];
    walk(D.layers, (n) => { if (n.type === 'layer') files.push(n); });
    try {
      for (const l of files) { if (l.fresh || l.dirtyPx !== false) { const blob = await new Promise((r) => l.canvas.toBlob(r, 'image/png')); await E.api.upload(layerPath(l), blob, 'editor'); l.fresh = false; } }
      const ser = (nodes) => nodes.map((n) => (n.type === 'group' ? { id: n.id, type: 'group', name: n.name, visible: n.visible, locked: n.locked, opacity: n.opacity, blend: n.blend, open: n.open, children: ser(n.children) } : { id: n.id, type: 'layer', name: n.name, visible: n.visible, locked: n.locked, opacity: n.opacity, blend: n.blend, x: n.x, y: n.y, rot: n.rot, sx: n.sx, sy: n.sy, w: n.canvas.width, h: n.canvas.height }));
      await E.api.write(`assets/${D.name}.asset.json`, JSON.stringify({ schema: 'asta.ge.asset.v1', name: D.name, w: D.w, h: D.h, layers: ser(D.layers) }), 'editor');
      D.dirty = false; status.textContent = t('salvo'); if (!quiet) toast(t('Documento salvo'), 'ok'); loadList();
    } catch (e) { toast(e.message, 'err'); }
  }
  const loadImage = (src) => new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = () => rej(new Error(t('Não consegui abrir a imagem.'))); im.src = src; });
  async function openDoc(name) {
    try {
      const doc = JSON.parse((await E.api.read(`assets/${name}.asset.json`, 'editor')).content);
      D.name = doc.name; D.w = doc.w; D.h = doc.h; D.mask = null; D.hasMask = false; undo = []; redo = [];
      const build = async (nodes) => { const out = []; for (const n of nodes) { if (n.type === 'group') { out.push(Object.assign(newGroup(n.name), n, { children: await build(n.children) })); } else { const im = await loadImage(E.api.raw(`assets/${doc.name}/${n.id}.png`, 'editor')); const c = mkCanvas(n.w, n.h); c.getContext('2d').drawImage(im, 0, 0); const l = Object.assign({}, n, { canvas: c }); reg.set(l.id, c); out.push(l); } } return out; };
      D.layers = await build(doc.layers); D.sel = ''; walk(D.layers, (n) => { if (n.type === 'layer' && !D.sel) D.sel = n.id; }); D.dirty = false; status.textContent = t('salvo');
      paintLayers(); paintProps(); fit(); toast(t('Aberto: {n}', { n: name }));
    } catch (e) { toast(e.message, 'err'); }
  }
  async function importImage(src, name) {
    const im = await loadImage(src); const w = Math.max(16, Math.min(2048, im.naturalWidth || 512)), hh = Math.max(16, Math.min(2048, im.naturalHeight || 512));
    D.name = (name || 'imagem').replace(/[^\w-]+/g, '-').toLowerCase().slice(0, 30) || 'imagem'; D.w = w; D.h = hh; D.mask = null; D.hasMask = false; undo = []; redo = [];
    const c = mkCanvas(w, hh); c.getContext('2d').drawImage(im, 0, 0, w, hh); const l = newLayer(name || t('Imagem'), c); D.layers = [l]; D.sel = l.id; paintLayers(); paintProps(); fit(); markDirty();
  }
  async function newDoc() {
    const nameIn = h('input', { value: 'sprite', id: 'ge-nd-name' }), preset = h('select', { id: 'ge-nd-size' }, [[512, 512], [256, 256], [1024, 1024], [128, 128], [64, 64], [1024, 512], [512, 1024], [1920, 1080]].map(([w, hh]) => h('option', { value: w + 'x' + hh }, w + ' × ' + hh)));
    if (await modal(t('Novo documento'), h('div', null, propRow(t('Nome'), nameIn), propRow(t('Tamanho'), preset)), [{ label: t('Cancelar'), value: null }, { label: t('Criar'), value: 'ok', cls: 'primary' }]) !== 'ok') return;
    const [w, hh] = preset.value.split('x').map(Number); D.name = nameIn.value.trim().replace(/[^\w-]+/g, '-').toLowerCase() || 'sprite'; D.w = w; D.h = hh; D.mask = null; D.hasMask = false; undo = []; redo = []; const l = newLayer(t('Camada 1')); D.layers = [l]; D.sel = l.id; paintLayers(); paintProps(); fit(); markDirty();
  }
  async function applyToGame() {
    if (!D.layers.length) return; const c = composite(); let out = c;
    if (await confirmDialog(t('Recortar as bordas transparentes antes de aplicar?'), false, t('Recortar')).catch(() => false)) { const l = newLayer('tmp', c); trim(l); out = mkCanvas(l.canvas.width, l.canvas.height); out.getContext('2d').drawImage(l.canvas, 0, 0); }
    const blob = await new Promise((r) => out.toBlob(r, 'image/png'));
    try { await E.api.upload(`assets/images/${D.name}.png`, blob, 'game'); await saveDoc(true); toast(t('Imagem «{n}» aplicada ao jogo (assets/images/{n}.png). Use-a em um nó com a propriedade «image».', { n: D.name }), 'ok'); loadList(); } catch (e) { toast(e.message, 'err'); }
  }
  function downloadPng() { composite().toBlob((b) => { const a = h('a', { href: URL.createObjectURL(b), download: D.name + '.png' }); document.body.appendChild(a); a.click(); a.remove(); }); }
  const listEl = h('div', { class: 'ge-alist', id: 'ge-alist' });
  async function loadList() {
    const [ed, gm] = await Promise.all([E.api.tree('editor'), E.api.tree('game')]);
    const docs = flatFiles(ed.children).filter((f) => f.path.endsWith('.asset.json') && f.path.startsWith('assets/')).map((f) => f.path.replace(/^assets\//, '').replace(/\.asset\.json$/, ''));
    const imgs = flatFiles(gm.children).filter((f) => f.path.startsWith('assets/images/') && /\.(png|jpe?g|webp|gif|svg)$/i.test(f.path));
    listEl.replaceChildren(...docs.map((d) => h('button', { type: 'button', class: 'ge-athumb', title: t('Abrir documento em camadas'), dataset: { doc: d }, onclick: () => openDoc(d) }, icon('layers', 22), h('div', null, d))),
      ...imgs.map((f) => h('button', { type: 'button', class: 'ge-athumb', title: t('Abrir esta imagem do jogo'), dataset: { img: stem(f.path) }, onclick: () => importImage(E.api.raw(f.path), stem(f.path)) }, h('img', { src: E.api.raw(f.path), alt: stem(f.path) }), h('div', null, stem(f.path)))));
    if (!listEl.children.length) listEl.replaceChildren(h('div', { class: 'muted small', style: { gridColumn: '1/-1' } }, t('Nenhuma imagem ainda. Gere uma com o prompt.')));
  }

  // ---------------------------------------------------------------- IA
  const ai = { transparent: true, target: 'new', size: '' };
  const transBtn = h('button', { class: 'tool on', type: 'button', id: 'ge-trans', title: t('Gera a imagem sem fundo (transparente)'), onclick: () => { ai.transparent = !ai.transparent; transBtn.classList.toggle('on', ai.transparent); transBtn.textContent = ai.transparent ? t('Sem fundo') : t('Com fundo'); } }, t('Sem fundo'));
  const targetSel = h('select', { class: 'team-sel', id: 'ge-atarget', title: t('Onde colocar o resultado'), 'aria-label': t('Onde colocar o resultado') }, [['new', t('Nova camada')], ['doc', t('Novo documento')]].map(([v, l]) => h('option', { value: v }, l))); targetSel.addEventListener('change', () => { ai.target = targetSel.value; });
  const pp = promptPanel(E, {
    tab: 'assets', endpoint: 'asset', title: t('Prompt de arte'), placeholder: t('Descreva a arte: “espada de fogo pixel art”, “ícone de coração”, “fundo de floresta”… Com uma seleção ativa, descreva a mudança só naquela área.'),
    intro: t('Gere sprites, ícones, UI e fundos. Selecione uma área (retângulo, mão livre ou pintando) para editar só aquele ponto com IA. Sem modelo de imagem, o ASTA desenha em vetor.'),
    hints: [t('herói de aventura em pixel art'), t('moeda dourada brilhante'), t('árvore cartoon'), t('botão de menu futurista')], tools: [transBtn, h('span', { class: 'tool' }, targetSel)],
    body: () => {
      const editing = D.hasMask && D.layers.length, b = { transparent: ai.transparent, size: '' };
      if (editing) { b.action = 'edit'; b.image = composite().toDataURL('image/png'); b.transparent = false; }
      else if (D.layers.length && ai.target === 'new' && false) b.image = composite().toDataURL('image/png');
      return b;
    },
    onResult: async (res) => {
      const img = res.image; if (!img) return;
      const src = img.mime === 'image/svg+xml' ? 'data:image/svg+xml;base64,' + img.data : 'data:' + img.mime + ';base64,' + img.data;
      const im = await loadImage(src);
      if (D.hasMask && D.layers.length) {   // edição de uma região: o resultado só entra dentro da seleção (camada nova, não destrutivo)
        const c = mkCanvas(D.w, D.h), x = c.getContext('2d'); x.drawImage(im, 0, 0, D.w, D.h); x.globalCompositeOperation = 'destination-in'; x.filter = 'blur(1.5px)'; x.drawImage(D.mask, 0, 0); x.filter = 'none';
        addLayer(t('Edição IA'), c); toast(t('Edição aplicada só na área selecionada (nova camada)'), 'ok'); return;
      }
      const prompt = (document.querySelector('#ge-composer-assets textarea') || {}).value; const nm = img.name || 'imagem';
      if (ai.target === 'doc' || !D.layers.length) { await importImage(src, nm); if (img.needs_cutout) { const l = activeLayer(); if (l) removeBackground(l.canvas, 38); draw(); paintLayers(); } return; }
      const c = mkCanvas(D.w, D.h), x = c.getContext('2d'), k = Math.min(D.w / im.naturalWidth, D.h / im.naturalHeight, 4) * 0.92; x.drawImage(im, (D.w - im.naturalWidth * k) / 2, (D.h - im.naturalHeight * k) / 2, im.naturalWidth * k, im.naturalHeight * k);
      if (img.needs_cutout) removeBackground(c, 38);
      addLayer(nm, c); toast(img.source === 'ai' ? t('Imagem gerada') : t('Desenho vetorial criado (sem modelo de imagem configurado)'), 'ok');
    },
  });

  // ---------------------------------------------------------------- montagem
  const topbar = h('div', { class: 'ge-vtool' }, btn(t('Novo'), 'plus', newDoc, '', { id: 'ge-anew' }), btn(t('Salvar'), 'check', () => saveDoc(), 'primary', { id: 'ge-asave' }), btn(t('Aplicar ao jogo'), 'rocket', applyToGame, '', { id: 'ge-aapply', title: t('Grava o PNG final em assets/images/') }), btn('PNG', 'download', downloadPng),
    h('span', { class: 'sep' }), ibtn(t('Desfazer (Ctrl+Z)'), 'undo', doUndo, '', { id: 'ge-aundo' }), ibtn(t('Refazer (Ctrl+Shift+Z)'), 'skipback', doRedo, '', { style: { transform: 'scaleX(-1)' } }), h('span', { class: 'grow' }), status);
  const layerBtns = h('div', { class: 'ge-ftool' }, ibtn(t('Nova camada'), 'plus', () => addLayer(), '', { id: 'ge-add-layer' }), ibtn(t('Nova pasta'), 'folder', addGroup, '', { id: 'ge-add-group' }), ibtn(t('Duplicar'), 'copy', dupNode), ibtn(t('Mesclar com a de baixo'), 'join', mergeDown), ibtn(t('Achatar tudo'), 'layers', flattenAll), ibtn(t('Apagar'), 'trash', delNode, '', { id: 'ge-del-layer' }));
  const left = h('div', { class: 'ge-left' }, pp.el);
  const center = h('section', { class: 'ge-center' }, topbar, optsEl, selBar, h('div', { class: 'ge-awork' }, toolsEl, wrap));
  const right = h('aside', { class: 'ge-right' }, h('div', { class: 'ge-ph' }, h('b', null, t('Camadas'))), layerBtns, layersEl, propsEl, h('div', { class: 'ge-ph' }, h('b', null, t('Imagens do projeto'))), listEl);
  body.replaceChildren(h('div', { class: 'ge-grid ge-assets' }, left, center, right));
  paintOpts(); paintLayers(); paintProps(); loadList();
  const ro = new ResizeObserver(resizeView); ro.observe(wrap); E.onCleanup(() => { ro.disconnect(); if (D.dirty && D.layers.length) saveDoc(true); });
  resizeView();
  if (!D.layers.length) { D.w = 512; D.h = 512; fit(); }
}
