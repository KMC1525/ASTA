/* ASTA Game Engine — modo de edição do editor (como o viewport do Godot): clicar seleciona, arrastar move, rodinha dá zoom, botão do meio/direito desloca.
 * Só roda dentro do ASTA (iframe do editor). Conversa com a página pelo postMessage: {geCmd: …} entra, {ge: …} sai. */
(function () {
  'use strict';
  var GE = window.GE, N = GE.num, E = GE.edit = { sel: null, grid: true, snap: 0, hover: null };
  var drag = null, pan = null, spaceDown = false, brush = null;
  function post(m) { try { m.ge = m.ge || 'msg'; window.parent.postMessage(m, '*'); } catch (e) { /* ok */ } }
  function byId(id) { var f = null; GE.walk(GE.root, function (n) { if (n.id === id) { f = n; return false; } }); return f; }
  function offset(n) { var x = 0, y = 0, z = 0, p = n.parent; while (p) { x += N(p.x, 0); y += N(p.y, 0); z += N(p.z, 0); p = p.parent; } return { x: x, y: y, z: z }; }
  function snap(v) { return E.snap > 0 ? Math.round(v / E.snap) * E.snap : v; }
  function selectable(n) { return n && n.alive && !n._virtual && n.parent && n.type !== 'UILabel' && n.type !== 'UIBar' && n.type !== 'Sky3D' && n.type !== 'Light3D' ? true : (n && n.type === 'Light3D' && !n._virtual); }
  E.select = function (id, quiet) { E.sel = id; if (!quiet) post({ ge: 'select', id: id }); if (GE.R && GE.R.onSelect) GE.R.onSelect(id ? byId(id) : null); };

  // ------------------------------------------------------------------ 2D
  function pick2D(sx, sy) {
    var R = GE.R, w = R.toWorld(sx, sy), list = [];
    GE.walk(GE.root, function (n) { if (n.alive && n.visible !== false && !n._virtual && (n.type === 'Sprite2D' || n.type === 'Label2D' || n.type === 'Area2D' || n.type === 'Camera2D')) list.push(n); });
    list.sort(function (a, b) { return (N(b.z, 0) - N(a.z, 0)) || (b.y - a.y); });
    for (var i = 0; i < list.length; i++) { var n = list[i], b = R.bounds(n); if (n.type === 'Camera2D') continue; var pad = 4 / R.scaleNow(); if (w.x >= b.x - pad && w.x <= b.x + b.w + pad && w.y >= b.y - pad && w.y <= b.y + b.h + pad) return n; }
    var tm = null; GE.walk(GE.root, function (n) { if (n.type === 'TileMap' && n.mapRef) { var m = n.mapRef; if (!R.iso && w.x >= 0 && w.y >= 0 && w.x <= m.w * m.tile && w.y <= m.h * m.tile) tm = n; } });
    return tm;
  }
  E.draw2D = function (ctx, R) {
    var s = R.scaleNow(), step = 32, vw = R.viewW() / R.cam.zoom, vh = R.viewH() / R.cam.zoom;
    if (E.grid && !R.iso) {
      ctx.lineWidth = 1 / s; ctx.strokeStyle = 'rgba(255,255,255,.07)'; ctx.beginPath();
      var x0 = Math.floor((R.cam.x - vw / 2) / step) * step, y0 = Math.floor((R.cam.y - vh / 2) / step) * step;
      for (var x = x0; x < R.cam.x + vw / 2; x += step) { ctx.moveTo(x, R.cam.y - vh / 2); ctx.lineTo(x, R.cam.y + vh / 2); }
      for (var y = y0; y < R.cam.y + vh / 2; y += step) { ctx.moveTo(R.cam.x - vw / 2, y); ctx.lineTo(R.cam.x + vw / 2, y); }
      ctx.stroke(); ctx.strokeStyle = 'rgba(255,90,90,.5)'; ctx.beginPath(); ctx.moveTo(-9999, 0); ctx.lineTo(9999, 0); ctx.stroke(); ctx.strokeStyle = 'rgba(90,255,120,.5)'; ctx.beginPath(); ctx.moveTo(0, -9999); ctx.lineTo(0, 9999); ctx.stroke();
    }
    var m0 = R.maps[0]; if (m0 && !R.iso) { ctx.strokeStyle = 'rgba(120,200,255,.6)'; ctx.setLineDash([6 / s, 4 / s]); ctx.strokeRect(0, 0, m0.w * m0.tile, m0.h * m0.tile); ctx.setLineDash([]); }
    if (R.camNode && !R.iso) { var cw = R.viewW() / N(R.camNode.zoom, 1), ch = R.viewH() / N(R.camNode.zoom, 1); ctx.strokeStyle = 'rgba(255,210,90,.55)'; ctx.strokeRect(R.cam.x - cw / 2, R.cam.y - ch / 2, cw, ch); }
    var h = E.hover && byId(E.hover); if (h && h.id !== E.sel) { var hb = R.bounds(h); ctx.strokeStyle = 'rgba(255,255,255,.5)'; ctx.lineWidth = 1.5 / s; ctx.strokeRect(hb.x, hb.y, hb.w, hb.h); label(ctx, h.name, hb.x, hb.y - 4 / s, s); }
    var n = E.sel && byId(E.sel);
    if (n && n.alive) {
      var b = R.bounds(n); if (n.type === 'TileMap' && n.mapRef) b = { x: 0, y: 0, w: n.mapRef.w * n.mapRef.tile, h: n.mapRef.h * n.mapRef.tile };
      ctx.strokeStyle = '#ffd166'; ctx.lineWidth = 2 / s; ctx.strokeRect(b.x, b.y, b.w, b.h); ctx.fillStyle = '#ffd166'; var hs = 5 / s; [[b.x, b.y], [b.x + b.w, b.y], [b.x, b.y + b.h], [b.x + b.w, b.y + b.h]].forEach(function (p) { ctx.fillRect(p[0] - hs / 2, p[1] - hs / 2, hs, hs); });
      label(ctx, n.name + ' (' + n.type + ')', b.x, b.y - 6 / s, s);
    }
  };
  function label(ctx, text, x, y, s) { ctx.font = '600 ' + (11 / s) + 'px system-ui'; ctx.fillStyle = 'rgba(0,0,0,.65)'; var w = ctx.measureText(text).width; ctx.fillRect(x - 2 / s, y - 12 / s, w + 4 / s, 14 / s); ctx.fillStyle = '#fff'; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'; ctx.fillText(text, x, y - 1 / s); }
  function isoInv(R, wx, wy) { // posição na tela do mundo -> coordenadas de bloco
    var a = wx / 32, b = wy / 16; return { x: (a + b) / 2, y: (b - a) / 2 };
  }

  // ------------------------------------------------------------------ 3D
  E.frame3D = function (R) {
    var T = window.THREE; if (!T) return; var n = E.sel && byId(E.sel);
    if (!E.helper) { E.helper = new T.BoxHelper(new T.Object3D(), 0xffd166); E.helper.visible = false; R.three.add(E.helper); }
    if (E.helper.parent !== R.three) R.three.add(E.helper);
    if (n && n.obj && n.alive && n.type !== 'Terrain3D') { E.helper.setFromObject(n.obj); E.helper.visible = true; } else E.helper.visible = false;
  };
  E.reset3D = function (R) { E.helper = null; };
  // anel sobre o terreno: mostra onde o pincel/região atua (um «LineLoop» que acompanha o relevo)
  function ring(R, x, z, r, color) {
    var T = window.THREE; if (!T || !R.three) return null; var pts = [], n = 72;
    for (var i = 0; i < n; i++) { var a = i / n * 6.2832, px = x + Math.cos(a) * r, pz = z + Math.sin(a) * r, y = R.terrainHeight(px, pz); pts.push(new T.Vector3(px, (y == null ? 0 : y) + 0.4, pz)); }
    var g = new T.BufferGeometry().setFromPoints(pts), m = new T.LineLoop(g, new T.LineBasicMaterial({ color: color || 0xffd166, depthTest: false, transparent: true })); m.renderOrder = 20; return m;
  }
  E.setMarker = function (kind, x, z, r) {
    var R = GE.R; if (!R || !R.three) return; var key = '_m_' + kind; if (E[key]) { R.three.remove(E[key]); E[key] = null; }
    if (x == null) return; E[key] = ring(R, x, z, r, kind === 'region' ? 0x7cb7ff : 0xffd166); if (E[key]) R.three.add(E[key]);
  };

  // ------------------------------------------------------------------ entrada do mouse
  function bind() {
    var el = document.getElementById('ge-stage'); if (!el || el._geEdit) return; el._geEdit = true;
    el.addEventListener('contextmenu', function (e) { e.preventDefault(); });
    el.addEventListener('wheel', function (e) {
      if (!GE.editing) return; e.preventDefault(); var R = GE.R, f = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      if (GE.dim === '2d') { var before = R.toWorld(e.offsetX, e.offsetY); R.cam.zoom = GE.clamp(R.cam.zoom * f, 0.15, 6); var after = R.toWorld(e.offsetX, e.offsetY); R.cam.x += before.x - after.x; R.cam.y += before.y - after.y; R.camNode && (R.camNode.zoom = R.cam.zoom); }
      else R.orbit.dist = GE.clamp(R.orbit.dist / f, 1.5, 600);
    }, { passive: false });
    el.addEventListener('pointerdown', function (e) {
      if (!GE.editing) return; var R = GE.R; el.setPointerCapture && el.setPointerCapture(e.pointerId);
      var panBtn = e.button === 1 || e.button === 2 || (e.button === 0 && spaceDown);
      if (GE.dim === '2d') {
        if (panBtn) { pan = { x: e.clientX, y: e.clientY, cx: R.cam.x, cy: R.cam.y }; return; }
        var n = pick2D(e.offsetX, e.offsetY); E.select(n ? n.id : null);
        if (n && n.type !== 'TileMap') { var w = R.toWorld(e.offsetX, e.offsetY); drag = { id: n.id, wx: w.x, wy: w.y, nx: n.x, ny: n.y, moved: false }; }
      } else {
        if (panBtn || e.button === 0 && e.shiftKey) { pan = { x: e.clientX, y: e.clientY, tx: R.orbit.tx, tz: R.orbit.tz, ty: R.orbit.ty }; return; }
        if (E.tool === 'brush') { var bp = R.groundPoint(e.offsetX, e.offsetY); if (bp) { brush = { down: true }; post({ ge: 'brush', phase: 'down', x: +bp.x.toFixed(2), z: +bp.z.toFixed(2) }); } return; }
        var n3 = R.pick(e.offsetX, e.offsetY); E.select(n3 ? n3.id : null);
        if (n3) { var gp = R.groundPoint(e.offsetX, e.offsetY); drag = { id: n3.id, gx: gp ? gp.x : 0, gz: gp ? gp.z : 0, nx: n3.x, nz: n3.z, moved: false }; }
        else pan = { x: e.clientX, y: e.clientY, yaw: R.orbit.yaw, pitch: R.orbit.pitch, orbit: true };
      }
    });
    el.addEventListener('pointermove', function (e) {
      if (!GE.editing) return; var R = GE.R;
      if (pan) {
        var dx = e.clientX - pan.x, dy = e.clientY - pan.y;
        if (GE.dim === '2d') { var s = R.scaleNow(); R.cam.x = pan.cx - dx / s; R.cam.y = pan.cy - dy / s; }
        else if (pan.orbit) { R.orbit.yaw = pan.yaw - dx * 0.006; R.orbit.pitch = GE.clamp(pan.pitch + dy * 0.006, 0.05, 1.5); }
        else { var o = R.orbit, k = o.dist * 0.0016; o.tx = pan.tx - (Math.cos(o.yaw) * dx + Math.sin(o.yaw) * dy * 0.0) * k; o.tz = pan.tz + (Math.sin(o.yaw) * dx - Math.cos(o.yaw) * dy) * k * 0; o.tx = pan.tx - Math.cos(o.yaw) * dx * k - Math.sin(o.yaw) * dy * k; o.tz = pan.tz + Math.sin(o.yaw) * dx * k - Math.cos(o.yaw) * dy * k; }
        return;
      }
      if (drag) {
        var n = byId(drag.id); if (!n) { drag = null; return; }
        if (GE.dim === '2d') {
          var w = R.toWorld(e.offsetX, e.offsetY), mx = w.x - drag.wx, my = w.y - drag.wy;
          if (R.iso) { var a = isoInv(R, w.x, w.y), b = isoInv(R, drag.wx, drag.wy); mx = a.x - b.x; my = a.y - b.y; n.x = Math.round((drag.nx + mx) * 4) / 4; n.y = Math.round((drag.ny + my) * 4) / 4; }
          else { n.x = snap(drag.nx + mx); n.y = snap(drag.ny + my); }
        } else {
          var gp = R.groundPoint(e.offsetX, e.offsetY); if (gp) { var oldH = R.terrainHeight(n.x, n.z); n.x = snap(+(drag.nx + gp.x - drag.gx).toFixed(2)); n.z = snap(+(drag.nz + gp.z - drag.gz).toFixed(2)); var newH = R.terrainHeight(n.x, n.z); if (oldH != null && newH != null) n.y = +(n.y + newH - oldH).toFixed(2); drag.dy = true; }
        }
        drag.moved = true; return;
      }
      if (E.tool === 'brush' && GE.dim === '3d') { var hp = R.groundPoint(e.offsetX, e.offsetY); if (hp) { E.setMarker('brush', hp.x, hp.z, E.radius || 10); if (brush && brush.down) { var now = performance.now(); if (!brush.t || now - brush.t > 110) { brush.t = now; post({ ge: 'brush', phase: 'move', x: +hp.x.toFixed(2), z: +hp.z.toFixed(2) }); } } } return; }
      var hv = GE.dim === '2d' ? pick2D(e.offsetX, e.offsetY) : GE.R.pick(e.offsetX, e.offsetY); E.hover = hv ? hv.id : null;
    });
    var up = function () {
      if (brush && brush.down) { brush = null; post({ ge: 'brush', phase: 'up' }); }
      if (drag && drag.moved) { var n = byId(drag.id); if (n) { var off = offset(n), props = GE.dim === '2d' ? { x: +(n.x - 0).toFixed(2), y: +(n.y - 0).toFixed(2) } : { x: +n.x.toFixed(2), y: +n.y.toFixed(2), z: +n.z.toFixed(2) }; post({ ge: 'moved', id: n.id, props: props }); } }
      drag = null; pan = null;
    };
    el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
    window.addEventListener('keydown', function (e) {
      if (!GE.editing || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || '')) return;
      if (e.code === 'Space') { spaceDown = true; e.preventDefault(); }
      var n = E.sel && byId(E.sel); if (!n) return;
      var d = e.shiftKey ? 10 : 1, mv = null;
      if (e.code === 'ArrowLeft') mv = [-d, 0]; else if (e.code === 'ArrowRight') mv = [d, 0]; else if (e.code === 'ArrowUp') mv = [0, -d]; else if (e.code === 'ArrowDown') mv = [0, d];
      if (mv) { e.preventDefault(); if (GE.dim === '2d') { var u = GE.R.iso ? 0.25 * d : d; n.x += mv[0] ? Math.sign(mv[0]) * u : 0; n.y += mv[1] ? Math.sign(mv[1]) * u : 0; post({ ge: 'moved', id: n.id, props: { x: +n.x.toFixed(2), y: +n.y.toFixed(2) } }); } else { n.x += mv[0] * 0.25; n.z += mv[1] * 0.25; post({ ge: 'moved', id: n.id, props: { x: +n.x.toFixed(2), y: +n.y.toFixed(2), z: +n.z.toFixed(2) } }); } }
      if (e.code === 'Delete' || e.code === 'Backspace') { e.preventDefault(); post({ ge: 'delete', id: n.id }); }
      if (e.code === 'KeyD' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); post({ ge: 'duplicate', id: n.id }); }
    });
    window.addEventListener('keyup', function (e) { if (e.code === 'Space') spaceDown = false; });
  }

  // ------------------------------------------------------------------ comandos da página do ASTA
  var saved = null;
  function keepCamera() { var R = GE.R; if (!R) return null; return GE.dim === '2d' ? { cam: { x: R.cam.x, y: R.cam.y, zoom: R.cam.zoom } } : { orbit: JSON.parse(JSON.stringify(R.orbit)) }; }
  function restoreCamera(s) { var R = GE.R; if (!s || !R) return; if (s.cam && GE.dim === '2d') { R.cam.x = s.cam.x; R.cam.y = s.cam.y; R.cam.zoom = s.cam.zoom; } if (s.orbit && GE.dim === '3d') R.orbit = s.orbit; }
  function frameScene() {
    var R = GE.R; if (!R) return;
    if (GE.dim === '2d') { var m = R.maps[0]; if (m && !R.iso) { R.cam.x = m.w * m.tile / 2; R.cam.y = m.h * m.tile / 2; R.cam.zoom = GE.clamp(Math.min(R.viewW() / (m.w * m.tile), R.viewH() / (m.h * m.tile)) * 0.95, 0.15, 3); } else if (m && R.iso) { var c = R.isoXY(m.w / 2, m.h / 2, 0); R.cam.x = c.x; R.cam.y = c.y; R.cam.zoom = 0.9; } else { var p = R.player(); if (p) { R.cam.x = p.x; R.cam.y = p.y; } } }
    else { var t = R.terrains[0]; R.orbit.tx = 0; R.orbit.tz = 0; R.orbit.ty = 2; R.orbit.dist = t ? t.size * 0.55 : 22; R.orbit.pitch = 0.55; var pl = GE.byTag('player')[0]; if (pl && !t) { R.orbit.tx = pl.x; R.orbit.tz = pl.z; } }
  }
  function load(cmd) {
    var keep = keepCamera(); GE.editing = (cmd.mode !== 'play'); if (E.helper) E.helper = null;
    GE.resetState(); var ok = GE.loadScene(cmd.name || cmd.scene.name || GE.sceneName, cmd.scene); if (!ok) return;
    if (GE.editing) { if (keep && !cmd.reframe) restoreCamera(keep); else frameScene(); bind(); document.getElementById('ge-start').classList.add('ge-hidden'); document.getElementById('ge-xr').classList.add('ge-hidden'); }
    else { GE.started = true; document.getElementById('ge-start').classList.add('ge-hidden'); var px = document.getElementById('ge-xr'); if (px && (GE.kind === 'vr' || GE.kind === 'ar')) px.classList.remove('ge-hidden'); GE.startMusic(); try { document.getElementById('ge-stage').focus(); } catch (e) { /* ok */ } }
    if (cmd.select) E.select(cmd.select, true);
  }
  window.addEventListener('message', function (ev) {
    var c = ev.data; if (!c || typeof c !== 'object' || !c.geCmd) return;
    try {
      if (c.geCmd === 'scene') { load(c); post({ ge: 'loaded', kind: GE.kind, name: GE.sceneName }); }
      else if (c.geCmd === 'select') E.select(c.id, true);
      else if (c.geCmd === 'patch') { var n = byId(c.id); if (n && c.props) for (var k in c.props) n[k] = c.props[k]; }
      else if (c.geCmd === 'grid') E.grid = !!c.on;
      else if (c.geCmd === 'snap') E.snap = N(c.size, 0);
      else if (c.geCmd === 'frame') frameScene();
      else if (c.geCmd === 'tool') { E.tool = c.name || 'select'; E.radius = N(c.radius, 10); if (E.tool !== 'brush') E.setMarker('brush', null); }
      else if (c.geCmd === 'marker') E.setMarker(c.kind || 'region', c.x, c.z, N(c.radius, 10));
      else if (c.geCmd === 'map') { (window.GE_DATA.maps = window.GE_DATA.maps || {})[c.path] = c.data; var sc = GE.scene, nm = GE.sceneName; E._m_region = null; E._m_brush = null; load({ name: nm, scene: sc, mode: 'edit', reframe: false }); if (c.region) E.setMarker('region', c.region.x, c.region.z, c.region.radius); }
      else if (c.geCmd === 'mute') GE.setMuted(!!c.on);
      else if (c.geCmd === 'focus') { var f = byId(c.id); if (f && GE.dim === '2d') { var b = GE.R.bounds(f); GE.R.cam.x = b.x + b.w / 2; GE.R.cam.y = b.y + b.h / 2; } else if (f && GE.dim === '3d') { GE.R.orbit.tx = f.x; GE.R.orbit.tz = f.z; GE.R.orbit.ty = f.y; } }
    } catch (e) { post({ ge: 'error', message: String(e && e.message || e) }); }
  });
  GE.onError = function (m) { if (window.parent !== window) post({ ge: 'error', message: m }); };
  E.active = function () { return !!GE.editing; };
})();
