/* ASTA Game Engine — motor 2D e 2.5D (canvas). Planos de fundo com paralaxe, mapas de blocos, física simples, projeção isométrica (2.5D). */
(function () {
  'use strict';
  var GE = window.GE, TW = 64, TH = 32, ZH = 26;
  var R = GE.Renderer2D = {};
  var C = GE.clamp, N = GE.num;

  // ------------------------------------------------------------------ preparação
  R.setup = function (scene, root, stage) {
    R.scene = scene; R.root = root; R.settings = scene.settings || {}; R.iso = (R.settings.projection === 'iso');
    R.stage = stage; R.maps = []; R.pops = []; R.cache = {}; R.frame = 0;
    if (!R.canvas) { R.canvas = document.createElement('canvas'); R.canvas.id = 'ge-canvas'; R.canvas.tabIndex = 0; stage.appendChild(R.canvas); window.addEventListener('resize', R.resize); }
    else if (!R.canvas.parentNode) stage.appendChild(R.canvas);
    R.ctx = R.canvas.getContext('2d'); R.resize();
    R.cam = { x: 0, y: 0, zoom: 1, tx: 0, ty: 0, shake: 0 };
    GE.walk(root, function (n) {
      if (n.type === 'TileMap') { loadMap(n); }
      if (n.type === 'Camera2D') R.camNode = n;
    });
    // objetos do mapa viram nós (moedas, inimigos, objetivo…)
    R.maps.forEach(function (m) { if (m.node.objects !== false) spawnObjects(m); });
    var p = R.player(); if (p) { R.cam.x = R.cam.tx = p.x; R.cam.y = R.cam.ty = p.y; }
    else if (R.maps[0]) { var mp = R.maps[0]; R.cam.x = mp.w * mp.tile / 2; R.cam.y = mp.h * mp.tile / 2; }
    if (R.iso && p) { var s = R.isoXY(p.x, p.y, 0); R.cam.x = R.cam.tx = s.x; R.cam.y = R.cam.ty = s.y; }
  };
  R.dispose = function () { R.pops = []; };
  R.resize = function () {
    if (!R.canvas || !R.stage) return; var dpr = Math.min(2, window.devicePixelRatio || 1), w = R.stage.clientWidth || window.innerWidth, h = R.stage.clientHeight || window.innerHeight;
    R.canvas.width = Math.max(2, Math.round(w * dpr)); R.canvas.height = Math.max(2, Math.round(h * dpr)); R.canvas.style.width = w + 'px'; R.canvas.style.height = h + 'px'; R.dpr = dpr; R.w = w; R.h = h;
  };
  R.player = function () { return GE.byTag('player')[0] || null; };

  // ------------------------------------------------------------------ mapas de blocos
  function loadMap(n) {
    var data = GE.mapData(n.map); if (!data) return;
    var layer = (data.layers && data.layers[0]) || { data: [] };
    var m = { node: n, data: data, tile: N(data.tile, 32), w: N(data.w, 0), h: N(data.h, 0), pal: data.palette || {}, grid: layer.data || [], heights: data.heights || null };
    n.mapRef = m; R.maps.push(m);
  }
  function tileId(m, cx, cy) { if (cx < 0 || cy < 0 || cx >= m.w || cy >= m.h) return 0; var row = m.grid[cy]; return row ? (row[cx] | 0) : 0; }
  function isSolid(m, id) { var p = m.pal[String(id)]; return !!(p && p.solid); }
  R.tileSolid = function (cx, cy) { for (var i = 0; i < R.maps.length; i++) { var m = R.maps[i]; if (isSolid(m, tileId(m, cx, cy))) return true; } return false; };
  var OBJ = {
    coin: function (o, m) { return { type: 'Sprite2D', name: 'Moeda', shape: 'circle', image: 'coin', w: 18, h: 18, color: '#ffd23f', tags: ['item'], behaviors: [{ type: 'collectible', value: 10 }, { type: 'float', amp: 3, speed: 4 }] }; },
    gem: function () { return { type: 'Sprite2D', name: 'Gema', shape: 'diamond', image: 'gem', w: 20, h: 20, color: '#4cc9f0', tags: ['item'], behaviors: [{ type: 'collectible', value: 25 }, { type: 'float', amp: 3, speed: 3 }] }; },
    enemy: function (o) { return { type: 'Sprite2D', name: 'Inimigo', shape: 'circle', image: 'enemy', w: 30, h: 28, color: '#ef476f', tags: ['enemy'], behaviors: [{ type: 'enemy', hp: 1, damage: 1, score: 20 }, { type: 'patrol', range: N(o.range, 90), speed: N(o.speed, 55) }] }; },
    flyer: function (o) { return { type: 'Sprite2D', name: 'Voador', shape: 'tri', image: 'flyer', w: 28, h: 24, color: '#9d4edd', tags: ['enemy'], behaviors: [{ type: 'enemy', hp: 1, damage: 1, score: 30 }, { type: 'patrol', range: N(o.range, 120), speed: 70, axis: 'y' }] }; },
    chaser: function () { return { type: 'Sprite2D', name: 'Perseguidor', shape: 'circle', image: 'enemy', w: 28, h: 28, color: '#d62828', tags: ['enemy'], behaviors: [{ type: 'enemy', hp: 2, damage: 1, score: 40 }, { type: 'chase', speed: 70, range: 220 }] }; },
    spike: function () { return { type: 'Area2D', name: 'Espinho', w: 28, h: 14, color: '#adb5bd', shape: 'tri', tags: ['hazard'], behaviors: [{ type: 'hazard', damage: 1 }] }; },
    goal: function () { return { type: 'Area2D', name: 'Objetivo', w: 36, h: 52, color: '#80ed99', shape: 'flag', image: 'goal', tags: ['goal'], behaviors: [{ type: 'goal' }] }; },
    heart: function () { return { type: 'Sprite2D', name: 'Coração', shape: 'circle', image: 'heart', w: 20, h: 20, color: '#ff4d6d', tags: ['item'], behaviors: [{ type: 'health_pickup', amount: 1 }, { type: 'float', amp: 3, speed: 3 }] }; },
    spring: function () { return { type: 'Area2D', name: 'Mola', w: 30, h: 14, color: '#f9c74f', shape: 'rect', tags: [], behaviors: [{ type: 'spring', power: 780 }] }; },
    key: function () { return { type: 'Sprite2D', name: 'Chave', shape: 'diamond', image: 'key', w: 20, h: 20, color: '#ffbe0b', tags: ['item'], behaviors: [{ type: 'key', id: 'a' }, { type: 'float', amp: 3, speed: 3 }] }; },
    door: function () { return { type: 'Sprite2D', name: 'Porta', shape: 'rect', image: 'door', w: 32, h: 64, color: '#8d5524', solid: true, tags: [], behaviors: [{ type: 'door', key: 'a' }] }; },
    npc: function (o) { return { type: 'Sprite2D', name: o.name || 'NPC', shape: 'circle', image: 'npc', w: 28, h: 40, color: '#90e0ef', tags: ['npc'], behaviors: [{ type: 'dialogue', id: o.dialogue || 'npc1', range: 60 }] }; },
    tree: function () { return { type: 'Sprite2D', name: 'Árvore', shape: 'circle', image: 'tree', w: 56, h: 72, color: '#2d6a4f', z: -1, tags: [], behaviors: [] }; },
    crate: function () { return { type: 'Sprite2D', name: 'Caixa', shape: 'rect', image: 'crate', w: 32, h: 32, color: '#b08968', solid: true, tags: [], behaviors: [] }; },
  };
  GE.OBJ2D = OBJ;
  function spawnObjects(m) {
    var t = m.tile, out = [];
    (m.data.objects || []).forEach(function (o) {
      if (o.type === 'player') { out.push({ type: 'Sprite2D', name: 'Jogador', shape: 'rect', image: 'player', w: m.data.genre === 'iso' ? 28 : 24, h: 34, color: '#ffd166', tags: ['player'], x: N(o.x, 0) * t + t / 2, y: N(o.y, 0) * t + t / 2, behaviors: [{ type: GE.playerBehavior(m.data, R.settings) }] }); return; }
      var f = OBJ[o.type]; if (!f) return; var s = f(o, m); s.x = (N(o.x, 0) + 0.5) * t; s.y = (N(o.y, 0) + 0.5) * t; if (R.iso) { s.x = N(o.x, 0) + 0.5; s.y = N(o.y, 0) + 0.5; }
      if (o.props) for (var k in o.props) s[k] = o.props[k];
      out.push(s);
    });
    out.forEach(function (s) { m.node.children.push(GE.makeNode(s, m.node)); });
    // o jogador nasce em cima do bloco (coordenadas de mapa → mundo) — para mapas isométricos usa unidades de bloco
    if (R.iso) GE.walk(m.node, function (x) { if (x.tags.indexOf('player') >= 0) { x.x = N(x.x, 0) / t; x.y = N(x.y, 0) / t; } });
  }
  GE.playerBehavior = function (mapData, settings) {
    if (settings.projection === 'iso') return 'player_iso';
    var g = String(mapData.genre || settings.genre || 'platformer');
    return g === 'topdown' ? 'player_topdown' : g === 'shooter' ? 'player_ship' : 'player_platformer';
  };

  // ------------------------------------------------------------------ física
  GE.box = function (n) { var w = N(n.w, 32) * N(n.sx, 1), h = N(n.h, 32) * N(n.sy, 1); return { x: n.x - w / 2, y: n.y - h / 2, w: w, h: h }; };
  GE.overlap = function (a, b) { var A = GE.box(a), B = GE.box(b); return A.x < B.x + B.w && A.x + A.w > B.x && A.y < B.y + B.h && A.y + A.h > B.y; };
  function solidNodes() { var c = R.cache.solids; if (c) return c; c = R.cache.solids = []; GE.walk(GE.root, function (n) { if (n.alive && n.solid && (n.type === 'Sprite2D' || n.type === 'Area2D')) c.push(n); }); return c; }
  function blockedBox(self, bx, by, bw, bh) {
    for (var i = 0; i < R.maps.length; i++) {
      var m = R.maps[i], t = m.tile, x0 = Math.floor(bx / t), x1 = Math.floor((bx + bw - 0.01) / t), y0 = Math.floor(by / t), y1 = Math.floor((by + bh - 0.01) / t);
      for (var cy = y0; cy <= y1; cy++) for (var cx = x0; cx <= x1; cx++) { if (cx < 0 || cx >= m.w) { if (m.data.walls !== false) return true; } else if (cy >= m.h) { /* buraco embaixo: cai */ } else if (cy >= 0 && isSolid(m, tileId(m, cx, cy))) return true; }
    }
    var ns = solidNodes();
    for (var j = 0; j < ns.length; j++) { var o = ns[j]; if (o === self || !o.alive) continue; var B = GE.box(o); if (bx < B.x + B.w && bx + bw > B.x && by < B.y + B.h && by + bh > B.y) return true; }
    return false;
  }
  GE.moveBody = function (n, dx, dy) {
    var hit = { l: false, r: false, u: false, d: false }, w = N(n.cw, N(n.w, 24)) * 0.8, h = N(n.ch, N(n.h, 32)) * 0.96, steps, s;
    steps = Math.max(1, Math.ceil(Math.abs(dx) / 3)); s = dx / steps;
    for (var i = 0; i < steps; i++) { if (blockedBox(n, n.x + s - w / 2, n.y - h / 2, w, h)) { if (s > 0) hit.r = true; else hit.l = true; break; } n.x += s; }
    steps = Math.max(1, Math.ceil(Math.abs(dy) / 3)); s = dy / steps;
    for (var k = 0; k < steps; k++) { if (blockedBox(n, n.x - w / 2, n.y + s - h / 2, w, h)) { if (s > 0) hit.d = true; else hit.u = true; break; } n.y += s; }
    return hit;
  };

  // ------------------------------------------------------------------ projeção isométrica (2.5D)
  R.isoXY = function (x, y, z) { return { x: (x - y) * TW / 2, y: (x + y) * TH / 2 - N(z, 0) * ZH }; };
  R.heightAt = function (x, y) { // altura (em blocos) do terreno em (x, y): -9 = não dá para pisar (fora do mapa, vazio ou bloco sólido/água)
    var best = null;
    R.maps.forEach(function (m) {
      var cx = Math.floor(x), cy = Math.floor(y), h = -9;
      if (cx >= 0 && cy >= 0 && cx < m.w && cy < m.h) { var id = tileId(m, cx, cy); if (id && !isSolid(m, id)) h = m.heights ? N((m.heights[cy] || [])[cx], 1) : 1; }
      best = best == null ? h : Math.max(best, h);
    });
    return best == null ? -9 : best;
  };

  // ------------------------------------------------------------------ atualização
  R.update = function (dt) {
    R.cache = {}; R.frame++;
    var p = R.player(), cam = R.cam, s = R.settings;
    if (!GE.editing) {
      var f = R.camNode ? GE.find(R.camNode.follow) : null; f = f || p;
      if (f) {
        var tx = f.x, ty = f.y; if (R.iso) { var sp = R.isoXY(f.x, f.y, N(f.z, 0)); tx = sp.x; ty = sp.y; }
        cam.tx = tx; cam.ty = ty; var k = 1 - Math.pow(0.0005, dt); if (R.camNode && R.camNode.smooth != null) k = 1 - Math.pow(0.0005, dt * N(R.camNode.smooth, 1)); cam.x += (cam.tx - cam.x) * k; cam.y += (cam.ty - cam.y) * k;
      }
      if (R.camNode) cam.zoom = N(R.camNode.zoom, 1);
      var m0 = R.maps[0]; if (m0 && !R.iso && s.cam_bounds !== false) { // a câmera não mostra além do mapa
        var vw = R.viewW() / cam.zoom, vh = R.viewH() / cam.zoom, mw = m0.w * m0.tile, mh = m0.h * m0.tile;
        cam.x = mw <= vw ? mw / 2 : C(cam.x, vw / 2, mw - vw / 2); cam.y = mh <= vh ? mh / 2 : C(cam.y, vh / 2, mh - vh / 2);
      }
      for (var i = R.pops.length - 1; i >= 0; i--) { var o = R.pops[i]; o.t -= dt; o.y -= 30 * dt; if (o.t <= 0) R.pops.splice(i, 1); }
      if (cam.shake > 0) cam.shake = Math.max(0, cam.shake - dt * 2);
    }
  };
  R.pop = function (x, y, text, color) { R.pops.push({ x: x, y: y, text: String(text), color: color || '#fff', t: 0.9 }); };
  R.viewH = function () { return N(R.settings.view_h, R.iso ? 460 : 540); };
  R.viewW = function () { return R.viewH() * (R.w / R.h); };
  R.scaleNow = function () { return (R.h / R.viewH()) * R.cam.zoom; };
  R.toWorld = function (sx, sy) { var s = R.scaleNow(); return { x: (sx - R.w / 2) / s + R.cam.x, y: (sy - R.h / 2) / s + R.cam.y }; };
  R.toScreen = function (wx, wy) { var s = R.scaleNow(); return { x: (wx - R.cam.x) * s + R.w / 2, y: (wy - R.cam.y) * s + R.h / 2 }; };

  // ------------------------------------------------------------------ desenho
  function bgFill(ctx) {
    var s = R.settings, top = GE.hex(s.sky_top || s.bg, '#101820'), bot = GE.hex(s.sky_bottom || s.bg, top);
    var g = ctx.createLinearGradient(0, 0, 0, R.h); g.addColorStop(0, top); g.addColorStop(1, bot); ctx.fillStyle = g; ctx.fillRect(0, 0, R.w, R.h);
  }
  function parallax(ctx, n) {
    var f = N(n.factor, 0.3), col = GE.hex(n.color, '#2b3a55'), col2 = GE.hex(n.color2, GE.shade(col, 0.2)), style = n.style || 'hills', base = R.h * C(N(n.y, 0.75), 0, 1.2), hgt = R.h * N(n.h, 0.3);
    var off = -(R.cam.x * f * R.scaleNow()), period = 900 * (R.h / 540), rnd;
    if (style === 'solid') { ctx.fillStyle = col; ctx.globalAlpha = N(n.opacity, 1); ctx.fillRect(0, base, R.w, R.h - base); ctx.globalAlpha = 1; return; }
    ctx.save(); ctx.globalAlpha = N(n.opacity, 1);
    var x0 = Math.floor(-off / period) - 1, x1 = x0 + Math.ceil(R.w / period) + 2;
    for (var p = x0; p <= x1; p++) {
      rnd = GE.rng(p * 7919 + (n.seed | 0) + 13); var px = off + p * period;
      if (style === 'hills' || style === 'mountains') {
        ctx.fillStyle = col; ctx.beginPath(); ctx.moveTo(px, R.h);
        var pts = 7; for (var i = 0; i <= pts; i++) { var xx = px + period * i / pts, hh = hgt * (0.35 + rnd() * 0.65); ctx.lineTo(xx, style === 'mountains' ? base - hh : base - hh * 0.5 - Math.sin(i + p) * hgt * 0.15); }
        ctx.lineTo(px + period, R.h); ctx.closePath(); ctx.fill();
      } else if (style === 'clouds') {
        ctx.fillStyle = col; for (var c = 0; c < 4; c++) { var cx = px + rnd() * period, cy = base - rnd() * hgt, r = 18 + rnd() * 26; ctx.beginPath(); ctx.arc(cx, cy, r, 0, 7); ctx.arc(cx + r * 0.9, cy + 4, r * 0.75, 0, 7); ctx.arc(cx - r * 0.9, cy + 6, r * 0.65, 0, 7); ctx.fill(); }
      } else if (style === 'stars') {
        ctx.fillStyle = col; for (var q = 0; q < 26; q++) { var sx = px + rnd() * period, sy = rnd() * R.h * 0.8, r2 = 0.6 + rnd() * 1.4; ctx.globalAlpha = N(n.opacity, 1) * (0.4 + rnd() * 0.6); ctx.fillRect(sx, sy, r2, r2); }
      } else if (style === 'city') {
        for (var b = 0; b < 9; b++) { var bw = 30 + rnd() * 50, bh = hgt * (0.3 + rnd() * 0.9), bx = px + b * period / 9; ctx.fillStyle = col; ctx.fillRect(bx, base - bh, bw, bh + R.h); ctx.fillStyle = col2; for (var w = 0; w < bh / 18; w++) if (rnd() > 0.55) ctx.fillRect(bx + 6 + (w % 3) * 12, base - bh + 8 + Math.floor(w / 3) * 18, 5, 8); }
      } else if (style === 'trees') {
        for (var tr = 0; tr < 10; tr++) { var tx = px + tr * period / 10 + rnd() * 30, th = hgt * (0.5 + rnd() * 0.7); ctx.fillStyle = col2; ctx.fillRect(tx - 3, base - th * 0.3, 6, th * 0.3 + R.h); ctx.fillStyle = col; ctx.beginPath(); ctx.moveTo(tx - th * 0.28, base - th * 0.3); ctx.lineTo(tx, base - th); ctx.lineTo(tx + th * 0.28, base - th * 0.3); ctx.closePath(); ctx.fill(); }
      }
    }
    ctx.restore();
  }
  function tilePattern(ctx, id, p, x, y, t, cx, cy) {
    var col = GE.hex(p.color, '#7f7f7f'); ctx.fillStyle = col; ctx.fillRect(x, y, t + 0.6, t + 0.6);
    var h = ((cx * 73856093) ^ (cy * 19349663)) >>> 0;
    if (p.solid && p.top !== false) { ctx.fillStyle = GE.shade(col, 0.18); ctx.fillRect(x, y, t + 0.6, Math.max(2, t * 0.14)); }
    ctx.fillStyle = GE.shade(col, -0.16); for (var i = 0; i < 3; i++) { var hh = (h >> (i * 5)) & 31; ctx.fillRect(x + (hh % 8) * t / 8, y + t * 0.3 + ((hh >> 2) % 5) * t / 7, Math.max(1.5, t * 0.07), Math.max(1.5, t * 0.07)); }
    if (p.kind === 'water') { ctx.fillStyle = 'rgba(255,255,255,.12)'; ctx.fillRect(x, y + t * 0.35 + Math.sin((cx + R.frame / 20) * 1.3) * 2, t, 2); }
  }
  function drawMap2D(ctx, m) {
    var t = m.tile, vw = R.viewW() / R.cam.zoom, vh = R.viewH() / R.cam.zoom;
    var x0 = Math.max(0, Math.floor((R.cam.x - vw / 2) / t) - 1), x1 = Math.min(m.w - 1, Math.ceil((R.cam.x + vw / 2) / t) + 1), y0 = Math.max(0, Math.floor((R.cam.y - vh / 2) / t) - 1), y1 = Math.min(m.h - 1, Math.ceil((R.cam.y + vh / 2) / t) + 1);
    for (var cy = y0; cy <= y1; cy++) for (var cx = x0; cx <= x1; cx++) {
      var id = tileId(m, cx, cy); if (!id) continue; var p = m.pal[String(id)] || { color: '#777', solid: true };
      var img = p.image && GE.images && GE.images[p.image]; if (img && img.complete && img.naturalWidth) ctx.drawImage(img, cx * t, cy * t, t + 0.6, t + 0.6); else tilePattern(ctx, id, p, cx * t, cy * t, t, cx, cy);
    }
  }
  function drawShape(ctx, n, w, h) {
    var col = GE.hex(n.color, '#cccccc'), shape = n.shape || 'rect', img = n.image && GE.images && GE.images[n.image];
    if (img && img.complete && img.naturalWidth && shape !== 'none') { ctx.drawImage(img, -w / 2, -h / 2, w, h); return; }
    if (shape === 'emoji') { ctx.font = Math.round(h * 0.85) + 'px system-ui, "Apple Color Emoji", "Segoe UI Emoji"'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(n.emoji || '⭐', 0, 0); return; }
    ctx.fillStyle = col;
    if (shape === 'circle') { ctx.beginPath(); ctx.ellipse(0, 0, w / 2, h / 2, 0, 0, 7); ctx.fill(); ctx.fillStyle = 'rgba(255,255,255,.28)'; ctx.beginPath(); ctx.ellipse(-w * 0.14, -h * 0.18, w * 0.16, h * 0.12, 0, 0, 7); ctx.fill(); drawEyes(ctx, n, w, h); }
    else if (shape === 'tri') { ctx.beginPath(); ctx.moveTo(-w / 2, h / 2); ctx.lineTo(0, -h / 2); ctx.lineTo(w / 2, h / 2); ctx.closePath(); ctx.fill(); }
    else if (shape === 'diamond') { ctx.beginPath(); ctx.moveTo(0, -h / 2); ctx.lineTo(w / 2, 0); ctx.lineTo(0, h / 2); ctx.lineTo(-w / 2, 0); ctx.closePath(); ctx.fill(); ctx.fillStyle = 'rgba(255,255,255,.3)'; ctx.beginPath(); ctx.moveTo(0, -h / 2); ctx.lineTo(w / 4, -h / 8); ctx.lineTo(0, 0); ctx.lineTo(-w / 4, -h / 8); ctx.closePath(); ctx.fill(); }
    else if (shape === 'flag') { ctx.fillStyle = '#6c757d'; ctx.fillRect(-2, -h / 2, 4, h); ctx.fillStyle = col; ctx.beginPath(); ctx.moveTo(2, -h / 2); ctx.lineTo(w / 2, -h / 2 + h * 0.2); ctx.lineTo(2, -h / 2 + h * 0.4); ctx.closePath(); ctx.fill(); }
    else { ctx.fillRect(-w / 2, -h / 2, w, h); ctx.fillStyle = GE.shade(col, 0.22); ctx.fillRect(-w / 2, -h / 2, w, Math.max(2, h * 0.14)); ctx.fillStyle = GE.shade(col, -0.22); ctx.fillRect(-w / 2, h / 2 - Math.max(2, h * 0.1), w, Math.max(2, h * 0.1)); if (n.tags && n.tags.indexOf('player') >= 0) drawEyes(ctx, n, w, h); }
  }
  function drawEyes(ctx, n, w, h) {
    if (!(n.tags && (n.tags.indexOf('player') >= 0 || n.tags.indexOf('enemy') >= 0 || n.tags.indexOf('npc') >= 0))) return;
    var d = n.flip ? -1 : 1; ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(d * w * 0.16, -h * 0.12, Math.max(2, w * 0.13), 0, 7); ctx.arc(d * w * 0.38 - d * w * 0.05, -h * 0.12, Math.max(2, w * 0.13), 0, 7); ctx.fill();
    ctx.fillStyle = '#111'; ctx.beginPath(); ctx.arc(d * w * 0.2, -h * 0.12, Math.max(1, w * 0.06), 0, 7); ctx.arc(d * w * 0.35, -h * 0.12, Math.max(1, w * 0.06), 0, 7); ctx.fill();
  }
  function drawNode2D(ctx, n) {
    var w = N(n.w, 32), h = N(n.h, 32); ctx.save(); ctx.translate(n.x, n.y); if (n.rotation) ctx.rotate(GE.rad(n.rotation)); ctx.scale(N(n.sx, 1) * (n.flip ? -1 : 1), N(n.sy, 1));
    ctx.globalAlpha = n.opacity == null ? 1 : C(n.opacity, 0, 1);
    if (n.type === 'Label2D') { ctx.fillStyle = GE.hex(n.color, '#fff'); ctx.font = '600 ' + N(n.size, 18) + 'px system-ui,sans-serif'; ctx.textAlign = n.align || 'center'; ctx.textBaseline = 'middle'; ctx.scale(n.flip ? -1 : 1, 1); ctx.fillText(String(n.text || '').replace(/\{(\w+)\}/g, function (m, k) { return GE.state[k] == null ? '' : GE.state[k]; }), 0, 0); }
    else if (n.type === 'Area2D') { if (n.shape && n.shape !== 'none') drawShape(ctx, n, w, h); else if (GE.editing) { ctx.strokeStyle = 'rgba(120,200,255,.8)'; ctx.setLineDash([4, 3]); ctx.strokeRect(-w / 2, -h / 2, w, h); } }
    else if (n.type === 'Sprite2D') { if (n.shadow) { ctx.fillStyle = 'rgba(0,0,0,.25)'; ctx.beginPath(); ctx.ellipse(0, h / 2, w * 0.45, h * 0.12, 0, 0, 7); ctx.fill(); } if (GE.invuln > 0 && n.tags.indexOf('player') >= 0 && Math.floor(GE.invuln * 12) % 2) ctx.globalAlpha = 0.35; drawShape(ctx, n, w, h); }
    ctx.restore();
  }
  function drawIso(ctx) {
    var items = [], s = R.scaleNow();
    R.maps.forEach(function (m) {
      for (var cy = 0; cy < m.h; cy++) for (var cx = 0; cx < m.w; cx++) {
        var id = tileId(m, cx, cy); if (!id) continue; var hh = m.heights ? N((m.heights[cy] || [])[cx], 1) : 1;
        var sp = R.isoXY(cx, cy, 0); if (Math.abs(sp.x - R.cam.x) > R.viewW() / R.cam.zoom / 2 + TW * 2 || Math.abs(sp.y - R.cam.y) > R.viewH() / R.cam.zoom / 2 + TH * 3 + hh * ZH) continue;
        items.push({ d: cx + cy + 1 + hh * 0.001, tile: [m, cx, cy, id, hh] });
      }
    });
    GE.walk(GE.root, function (n) { if (n.alive && n.visible !== false && (n.type === 'Sprite2D' || n.type === 'Label2D' || n.type === 'Area2D') && n.shape !== 'none') items.push({ d: N(n.x, 0) + N(n.y, 0) + 0.5 + N(n.z, 0) * 0.01 + N(n.layer, 0) * 0.001, node: n }); });
    items.sort(function (a, b) { return a.d - b.d; });
    items.forEach(function (it) {
      if (it.tile) { var m = it.tile[0], cx = it.tile[1], cy = it.tile[2], id = it.tile[3], hh = it.tile[4], p = m.pal[String(id)] || { color: '#777' }, col = GE.hex(p.color, '#777'), sp = R.isoXY(cx, cy, hh), bot = R.isoXY(cx, cy, 0);
        var x = sp.x, y = sp.y, hw = TW / 2, hh2 = TH / 2, drop = bot.y - sp.y;
        if (drop > 0) { ctx.fillStyle = GE.shade(col, -0.32); ctx.beginPath(); ctx.moveTo(x - hw, y + hh2); ctx.lineTo(x, y + TH); ctx.lineTo(x, y + TH + drop); ctx.lineTo(x - hw, y + hh2 + drop); ctx.closePath(); ctx.fill(); ctx.fillStyle = GE.shade(col, -0.5); ctx.beginPath(); ctx.moveTo(x + hw, y + hh2); ctx.lineTo(x, y + TH); ctx.lineTo(x, y + TH + drop); ctx.lineTo(x + hw, y + hh2 + drop); ctx.closePath(); ctx.fill(); }
        ctx.fillStyle = col; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + hw, y + hh2); ctx.lineTo(x, y + TH); ctx.lineTo(x - hw, y + hh2); ctx.closePath(); ctx.fill();
        ctx.strokeStyle = 'rgba(0,0,0,.18)'; ctx.lineWidth = 1; ctx.stroke(); if (p.kind === 'water') { ctx.fillStyle = 'rgba(255,255,255,.16)'; ctx.fillRect(x - 8, y + hh2 - 1 + Math.sin((cx + cy + R.frame / 14)) * 1.5, 16, 2); } return; }
      var n = it.node, sp2 = R.isoXY(n.x, n.y, N(n.z, 0)); ctx.save(); ctx.translate(sp2.x, sp2.y + 2);
      var sh = R.isoXY(n.x, n.y, 0); ctx.fillStyle = 'rgba(0,0,0,.28)'; ctx.beginPath(); ctx.ellipse(0, sh.y - sp2.y, 13, 6, 0, 0, 7); ctx.fill();
      if (n.type === 'Label2D') { ctx.fillStyle = GE.hex(n.color, '#fff'); ctx.font = '600 ' + N(n.size, 16) + 'px system-ui'; ctx.textAlign = 'center'; ctx.fillText(String(n.text || ''), 0, -30); }
      else { var w = N(n.w, 28), h = N(n.h, 36); ctx.translate(0, -h / 2); ctx.scale(n.flip ? -1 : 1, 1); ctx.globalAlpha = n.opacity == null ? 1 : n.opacity; if (GE.invuln > 0 && n.tags.indexOf('player') >= 0 && Math.floor(GE.invuln * 12) % 2) ctx.globalAlpha = 0.35; drawShape(ctx, n, w, h); }
      ctx.restore();
    });
  }
  R.render = function () {
    var ctx = R.ctx; if (!ctx) return; ctx.setTransform(R.dpr, 0, 0, R.dpr, 0, 0); bgFill(ctx);
    var layers = []; GE.walk(GE.root, function (n) { if (n.alive && n.type === 'Parallax2D' && n.visible !== false) layers.push(n); });
    layers.forEach(function (n) { parallax(ctx, n); });
    var s = R.scaleNow(), sh = R.cam.shake > 0 ? (Math.random() - 0.5) * 10 * R.cam.shake : 0;
    ctx.save(); ctx.translate(R.w / 2 + sh, R.h / 2 + sh); ctx.scale(s, s); ctx.translate(-R.cam.x, -R.cam.y);
    if (R.iso) drawIso(ctx);
    else {
      R.maps.forEach(function (m) { drawMap2D(ctx, m); });
      var list = []; GE.walk(GE.root, function (n) { if (n.alive && n.visible !== false && (n.type === 'Sprite2D' || n.type === 'Label2D' || n.type === 'Area2D')) list.push(n); });
      var ys = R.settings.ysort; list.sort(function (a, b) { return (N(a.z, 0) - N(b.z, 0)) || (ys ? a.y - b.y : 0); });
      list.forEach(function (n) { drawNode2D(ctx, n); });
    }
    R.pops.forEach(function (o) { ctx.globalAlpha = C(o.t * 2, 0, 1); ctx.fillStyle = o.color; ctx.font = '700 16px system-ui'; ctx.textAlign = 'center'; var p = R.iso ? R.isoXY(o.x, o.y, 1.4) : { x: o.x, y: o.y }; ctx.fillText(o.text, p.x, p.y); ctx.globalAlpha = 1; });
    if (GE.editing && GE.edit && GE.edit.draw2D) GE.edit.draw2D(ctx, R);
    ctx.restore();
    if (R.settings.vignette !== false) { var g = ctx.createRadialGradient(R.w / 2, R.h / 2, R.h * 0.45, R.w / 2, R.h / 2, R.h * 0.95); g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,.28)'); ctx.fillStyle = g; ctx.fillRect(0, 0, R.w, R.h); }
  };
  // caixa na tela de um nó (modo de edição)
  R.bounds = function (n) {
    var w = N(n.w, 32) * N(n.sx, 1), h = N(n.h, 32) * N(n.sy, 1);
    if (n.type === 'Label2D') { w = 8 * String(n.text || '').length * N(n.size, 18) / 14; h = N(n.size, 18); }
    if (R.iso) { var sp = R.isoXY(n.x, n.y, N(n.z, 0)); return { x: sp.x - w / 2, y: sp.y - h, w: w, h: h }; }
    return { x: n.x - w / 2, y: n.y - h / 2, w: w, h: h };
  };

  // ------------------------------------------------------------------ comportamentos 2D
  var B = GE.behavior;
  function hurtPlayer(p, src) { GE.damage(1, src); R.cam.shake = 0.6; if (src && p) { p.vx = (p.x < src.x ? -1 : 1) * 160; p.vy = -240; } }
  B('player_platformer', {
    init: function (n, p, s) { n.vx = 0; n.vy = 0; s.coyote = 0; s.buf = 0; s.spawn = { x: n.x, y: n.y }; n.cw = 20; n.ch = 32; n.tags = n.tags.indexOf('player') < 0 ? n.tags.concat('player') : n.tags; },
    update: function (n, dt, p, s) {
      var speed = N(p.speed, 190), jump = N(p.jump, 540), g = N(R.settings.gravity, 1500), ax = GE.input.axis('left', 'right');
      n.vx += (ax * speed * (GE.input.down('run') ? 1.35 : 1) - n.vx) * Math.min(1, (ax ? 14 : 10) * dt); if (ax) n.flip = ax < 0;
      n.vy = Math.min(900, n.vy + g * dt); s.coyote -= dt; s.buf -= dt;
      if (GE.input.hit('jump') || GE.input.hit('up')) s.buf = 0.12;
      if (s.buf > 0 && (s.coyote > 0 || (p.double_jump && !s.dj))) { if (s.coyote <= 0) s.dj = true; n.vy = -jump; s.buf = 0; s.coyote = 0; GE.sfx('jump'); }
      if ((GE.input.up('jump') || GE.input.up('up')) && n.vy < -jump * 0.4) n.vy = -jump * 0.4;
      var hit = GE.moveBody(n, n.vx * dt, n.vy * dt);
      if (hit.d) { n.vy = 0; s.coyote = 0.1; s.dj = false; } if (hit.u) n.vy = 0.5 * Math.abs(n.vy); if (hit.l || hit.r) n.vx = 0;
      var m = R.maps[0]; if (n.y > (m ? m.h * m.tile + 160 : 2000)) { GE.damage(1, null); n.x = s.spawn.x; n.y = s.spawn.y; n.vy = 0; }
    },
  });
  B('player_topdown', {
    init: function (n) { n.cw = 20; n.ch = 22; n.vx = 0; n.vy = 0; n.tags = n.tags.indexOf('player') < 0 ? n.tags.concat('player') : n.tags; },
    update: function (n, dt, p) {
      var ax = GE.input.axis('left', 'right'), ay = GE.input.axis('up', 'down'), l = Math.sqrt(ax * ax + ay * ay) || 1, sp = N(p.speed, 170) * (GE.input.down('run') ? 1.4 : 1);
      if (ax) n.flip = ax < 0; GE.moveBody(n, ax / l * sp * dt, 0); GE.moveBody(n, 0, ay / l * sp * dt);
    },
  });
  B('player_ship', {
    init: function (n, p, s) { n.cw = 22; n.ch = 22; s.cool = 0; n.tags = n.tags.indexOf('player') < 0 ? n.tags.concat('player') : n.tags; },
    update: function (n, dt, p, s) {
      var ax = GE.input.axis('left', 'right'), ay = GE.input.axis('up', 'down'), sp = N(p.speed, 260); n.x += ax * sp * dt; n.y += ay * sp * dt;
      var m = R.maps[0]; if (m) { n.x = C(n.x, 12, m.w * m.tile - 12); n.y = C(n.y, 12, m.h * m.tile - 12); }
      s.cool -= dt; if ((GE.input.down('fire') || GE.input.down('jump')) && s.cool <= 0) { s.cool = N(p.fire_rate, 0.22); GE.sfx('shoot'); GE.add(GE.root, { type: 'Sprite2D', name: 'Tiro', shape: 'rect', w: 14, h: 5, color: '#fff3b0', x: n.x + 18, y: n.y, behaviors: [{ type: 'projectile', vx: 520, vy: 0, from: 'player', damage: 1, life: 1.6 }] }); }
      if (R.settings.autoscroll) { var sc = N(R.settings.autoscroll, 60); n.x += sc * dt; }
    },
  });
  B('player_iso', {
    init: function (n, p, s) { n.cw = 0.5; n.ch = 0.5; n.z = R.heightAt(n.x, n.y); n.tags = n.tags.indexOf('player') < 0 ? n.tags.concat('player') : n.tags; s.vz = 0; },
    update: function (n, dt, p, s) {
      var ax = GE.input.axis('left', 'right'), ay = GE.input.axis('up', 'down'), dx = ax + ay, dy = ay - ax, l = Math.sqrt(dx * dx + dy * dy) || 1, sp = N(p.speed, 3.2) * (GE.input.down('run') ? 1.5 : 1);
      if (ax) n.flip = ax < 0;
      var tryMove = function (mx, my) { var nx = n.x + mx, ny = n.y + my, h = R.heightAt(nx, ny); if (h > -9 && h - n.z <= 1.01 && !blockedIsoNode(n, nx, ny)) { n.x = nx; n.y = ny; } };
      if (ax || ay) { tryMove(dx / l * sp * dt, 0); tryMove(0, dy / l * sp * dt); }
      var gh = R.heightAt(n.x, n.y); if (gh < -8) gh = 0; if (GE.input.hit('jump') && n.z <= gh + 0.02) s.vz = 7; s.vz -= 20 * dt; n.z += s.vz * dt; if (n.z <= gh) { n.z = gh; s.vz = 0; }
    },
  });
  function blockedIsoNode(self, x, y) { var ns = solidNodes(); for (var i = 0; i < ns.length; i++) { var o = ns[i]; if (o !== self && Math.abs(o.x - x) < 0.45 && Math.abs(o.y - y) < 0.45) return true; } return false; }
  B('wander', { init: function (n, p, s) { s.ox = n.x; s.oy = n.y; s.t = 0; s.dx = 0; s.dy = 0; }, update: function (n, dt, p, s) { s.t -= dt; var r = N(p.radius, R.iso ? 2 : 80); if (s.t <= 0) { s.t = 1 + Math.random() * 2; var a = Math.random() * 6.28; s.dx = Math.cos(a); s.dy = Math.sin(a); if (Math.random() < 0.3) { s.dx = s.dy = 0; } } var sp = N(p.speed, R.iso ? 0.8 : 40) * dt; var nx = n.x + s.dx * sp, ny = n.y + s.dy * sp; if (Math.abs(nx - s.ox) > r) s.dx = -s.dx; else if (Math.abs(ny - s.oy) > r) s.dy = -s.dy; else if (R.iso) { if (R.heightAt(nx, ny) > -9) { n.x = nx; n.y = ny; n.z = R.heightAt(nx, ny); } } else { GE.moveBody(n, s.dx * sp, 0); GE.moveBody(n, 0, s.dy * sp); } if (s.dx) n.flip = s.dx < 0; } });
  B('patrol', {
    init: function (n, p, s) { s.o = p.axis === 'y' ? n.y : n.x; s.d = 1; n.cw = N(n.w, 28) * 0.8; n.ch = N(n.h, 28) * 0.8; n.vy = 0; },
    update: function (n, dt, p, s) {
      var r = N(p.range, R.iso ? 2 : 90), sp = N(p.speed, R.iso ? 0.9 : 55), g = R.settings.gravity;
      if (R.iso) { var nx = n.x + s.d * sp * dt; if (R.heightAt(nx, n.y) <= -9 || Math.abs(nx - s.o) > r) s.d = -s.d; else n.x = nx; n.z = Math.max(0, R.heightAt(n.x, n.y)); n.flip = s.d < 0; return; }
      if (p.axis === 'y') { n.y += s.d * sp * dt; if (Math.abs(n.y - s.o) > r) s.d = -s.d; return; }
      if (g) { n.vy = Math.min(900, (n.vy || 0) + N(g, 1500) * dt); var hh = GE.moveBody(n, 0, n.vy * dt); if (hh.d || hh.u) n.vy = 0; }
      var h = GE.moveBody(n, s.d * sp * dt, 0);
      if (h.l || h.r || Math.abs(n.x - s.o) > r) s.d = -s.d;
      else if (g) { var ax = n.x + s.d * (N(n.w, 28) / 2 + 2), ay = n.y + N(n.h, 28) / 2 + 4; if (!blockedBox(n, ax - 1, ay - 1, 2, 3)) s.d = -s.d; }
      n.flip = s.d < 0;
    },
  });
  B('chase', { update: function (n, dt, p) { var pl = R.player(); if (!pl) return; var d = GE.dist(n, pl), rg = N(p.range, R.iso ? 5 : 220); if (d > rg || d < 4) return; var sp = N(p.speed, 70) * dt, dx = (pl.x - n.x) / d, dy = (pl.y - n.y) / d; if (R.iso) { n.x += dx * sp / 60; n.y += dy * sp / 60; n.z = Math.max(0, R.heightAt(n.x, n.y)); } else if (R.settings.gravity) { GE.moveBody(n, dx * sp, 0); } else { GE.moveBody(n, dx * sp, 0); GE.moveBody(n, 0, dy * sp); } n.flip = dx < 0; } });
  B('drift', { update: function (n, dt, p) { n.x += N(p.vx, -90) * dt; n.y += Math.sin(GE.state.time * 3 + n.id.length) * 40 * dt; if (n.x < (R.cam.x - R.viewW() / 2 - 80)) GE.remove(n); } });
  B('spin', { update: function (n, dt, p) { n.rotation = (N(n.rotation, 0) + N(p.speed, 90) * dt) % 360; } });
  B('float', { init: function (n, p, s) { s.y0 = n.y; s.z0 = n.z; }, update: function (n, dt, p, s) { var w = Math.sin(GE.state.time * N(p.speed, 3) + (n.x || 0)) * N(p.amp, 4); if (R.iso) n.z = N(s.z0, 0) + w / 30; else n.y = s.y0 + w; } });
  B('collectible', { update: function (n, dt, p) { var pl = R.player(); if (!pl || !n.alive) return; var hit = R.iso ? (Math.abs(pl.x - n.x) < 0.6 && Math.abs(pl.y - n.y) < 0.6 && Math.abs(N(pl.z, 0) - N(n.z, 0)) < 1.6) : GE.overlap(pl, n); if (!hit) return; GE.remove(n); GE.state.coins++; GE.addScore(N(p.value, 10)); GE.sfx('coin'); R.pop(n.x, n.y - 10, '+' + N(p.value, 10), '#ffd23f'); if (GE.state.total && GE.state.coins >= GE.state.total && (R.scene.rules || {}).win === 'collect_all') GE.win(); } });
  B('health_pickup', { update: function (n, dt, p) { var pl = R.player(); if (pl && n.alive && (R.iso ? (Math.abs(pl.x - n.x) < 0.6 && Math.abs(pl.y - n.y) < 0.6) : GE.overlap(pl, n))) { GE.remove(n); GE.heal(N(p.amount, 1)); R.pop(n.x, n.y, '+♥', '#ff4d6d'); } } });
  B('hazard', { update: function (n, dt, p) { var pl = R.player(); if (pl && (R.iso ? (Math.abs(pl.x - n.x) < 0.5 && Math.abs(pl.y - n.y) < 0.5 && Math.abs(N(pl.z, 0) - N(n.z, 0)) < 1) : GE.overlap(pl, n))) GE.damage(N(p.damage, 1), n); } });
  B('goal', { update: function (n, dt, p) { var pl = R.player(); if (!pl) return; var hit = R.iso ? (Math.abs(pl.x - n.x) < 0.7 && Math.abs(pl.y - n.y) < 0.7) : GE.overlap(pl, n); if (!hit) return; var rules = R.scene.rules || {}; if (rules.win === 'collect_all' && GE.state.coins < GE.state.total) { if (!n._warned || GE.state.time - n._warned > 2) { n._warned = GE.state.time; GE.toast(GE.tr('Pegue tudo!')); } return; } GE.sfx('win'); if (p.next) GE.nextScene(p.next); else GE.nextScene(); } });
  B('spring', { update: function (n, dt, p) { var pl = R.player(); if (pl && pl.vy > 0 && GE.overlap(pl, n)) { pl.vy = -N(p.power, 780); GE.sfx('jump'); } } });
  B('key', { update: function (n, dt, p) { var pl = R.player(); if (pl && n.alive && GE.overlap(pl, n)) { GE.remove(n); GE.state.keys[p.id || 'a'] = true; GE.sfx('powerup'); GE.toast(GE.tr('Coletado')); } } });
  B('door', { update: function (n, dt, p) { var pl = R.player(); if (!pl || !n.alive) return; if (GE.dist(pl, n) < 54) { if (GE.state.keys[p.key || 'a']) { GE.remove(n); GE.sfx('door'); } else if (!n._w || GE.state.time - n._w > 2) { n._w = GE.state.time; GE.toast(GE.tr('Falta uma chave')); } } } });
  B('enemy', {
    init: function (n, p, s) { s.hp = N(p.hp, 1); n.tags = n.tags.indexOf('enemy') < 0 ? n.tags.concat('enemy') : n.tags; },
    update: function (n, dt, p, s) {
      var pl = R.player(); if (!pl || !n.alive) return;
      var near = R.iso ? (Math.abs(pl.x - n.x) < 0.55 && Math.abs(pl.y - n.y) < 0.55 && Math.abs(N(pl.z, 0) - N(n.z, 0)) < 1) : GE.overlap(pl, n);
      if (!near) return;
      if (!R.iso && R.settings.gravity && pl.vy > 80 && pl.y < n.y - 4) { s.hp--; pl.vy = -380; GE.sfx('hit'); if (s.hp <= 0) { GE.remove(n); GE.addScore(N(p.score, 20)); R.pop(n.x, n.y - 10, '+' + N(p.score, 20), '#fff'); } return; }
      if (R.iso && N(pl.z, 0) > N(n.z, 0) + 0.45) { GE.remove(n); GE.addScore(N(p.score, 20)); GE.sfx('hit'); return; }
      hurtPlayer(pl, n);
    },
  });
  B('shoot_at', { init: function (n, p, s) { s.t = N(p.interval, 2); }, update: function (n, dt, p, s) { s.t -= dt; var pl = R.player(); if (s.t > 0 || !pl || GE.dist(n, pl) > 380) return; s.t = N(p.interval, 2); var d = GE.dist(n, pl) || 1; GE.add(GE.root, { type: 'Sprite2D', name: 'Bala', shape: 'circle', w: 9, h: 9, color: '#ff6b6b', x: n.x, y: n.y, behaviors: [{ type: 'projectile', vx: (pl.x - n.x) / d * N(p.speed, 180), vy: (pl.y - n.y) / d * N(p.speed, 180), from: 'enemy', damage: N(p.damage, 1), life: 4 }] }); } });
  B('projectile', { update: function (n, dt, p, s) {
    s.life = (s.life == null ? N(p.life, 2) : s.life) - dt; n.x += N(p.vx, 0) * dt; n.y += N(p.vy, 0) * dt; if (s.life <= 0) { GE.remove(n); return; }
    if (p.from === 'player') { var es = GE.byTag('enemy'); for (var i = 0; i < es.length; i++) { var e = es[i]; if (e.alive && GE.overlap(n, e)) { var eb = e.bh.filter(function (b) { return b.type === 'enemy'; })[0]; GE.remove(n); if (eb) { eb.s.hp -= N(p.damage, 1); if (eb.s.hp <= 0) { GE.remove(e); GE.addScore(N(eb.p.score, 20)); GE.sfx('hit'); R.pop(e.x, e.y, '+' + N(eb.p.score, 20), '#fff'); } } return; } } }
    else { var pl = R.player(); if (pl && GE.overlap(n, pl)) { GE.remove(n); GE.damage(N(p.damage, 1), n); } }
    if (blockedBox(n, n.x - 3, n.y - 3, 6, 6)) GE.remove(n);
  } });
  B('spawner', { init: function (n, p, s) { s.t = 0; s.n = 0; }, update: function (n, dt, p, s) {
    s.t -= dt; if (s.t > 0) return; s.t = N(p.interval, 1.4); var tpl = p.template ? GE.find(p.template) : null; var count = 0; GE.walk(GE.root, function (x) { if (x.alive && x.spawned === n.id) count++; }); if (count >= N(p.max, 12)) return;
    var spec = tpl ? JSON.parse(JSON.stringify(tpl.spec)) : { type: 'Sprite2D', name: 'Inimigo', shape: 'circle', w: 28, h: 28, color: '#ef476f', tags: ['enemy'], behaviors: [{ type: 'enemy', hp: 1, score: 25 }, { type: 'drift', vx: -90 }] };
    spec.x = R.cam.x + R.viewW() / 2 + 40; spec.y = R.cam.y + (Math.random() - 0.5) * R.viewH() * 0.8; var nn = GE.add(GE.root, spec); nn.spawned = n.id;
  } });
  B('dialogue', { init: function (n, p, s) { s.talked = 0; }, update: function (n, dt, p, s) {
    var pl = R.player(); if (!pl || GE.talking) return; var near = R.iso ? (Math.abs(pl.x - n.x) < 1.4 && Math.abs(pl.y - n.y) < 1.4) : GE.dist(pl, n) < N(p.range, 60);
    if (near && !n._hint) { n._hint = true; GE.toast(GE.tr('E: falar'), 900); } if (!near) n._hint = false;
    if (near && GE.input.hit('action')) { var lines = ((window.GE_DATA || {}).dialogues || {})[p.id || n.name] || [{ speaker: n.name, text: '...' }]; GE.say(lines); s.talked++; }
  } });
  B('follow', { update: function (n, dt, p) { var t = GE.find(p.target || 'Jogador'); if (!t) return; var d = GE.dist(n, t); if (d > N(p.gap, 40)) { var sp = N(p.speed, 120) * dt; n.x += (t.x - n.x) / d * sp; n.y += (t.y - n.y) / d * sp; } } });
  B('bounce', { init: function (n, p, s) { s.vx = N(p.vx, 120); s.vy = N(p.vy, 90); }, update: function (n, dt, p, s) { var m = R.maps[0]; var hx = GE.moveBody(n, s.vx * dt, 0); if (hx.l || hx.r) s.vx = -s.vx; var hy = GE.moveBody(n, 0, s.vy * dt); if (hy.u || hy.d) s.vy = -s.vy; } });

  // som de fundo/objetos de áudio e luz de cena
  GE.behavior('audio_loop', { init: function (n, p) { if (p.sound) setTimeout(function () { GE.playSound(p.sound, { loop: true, volume: N(p.volume, 0.6) }); }, 50); } });
})();
