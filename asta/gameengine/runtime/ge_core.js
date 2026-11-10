/* ASTA Game Engine — núcleo do motor (JavaScript puro, sem dependências).
 * Árvore de nós como no Godot: a cena (JSON) vira nós; comportamentos (código revisado, fechado) dão vida a eles.
 * Os scripts do jogo (scripts/*.js) podem registrar comportamentos novos com GE.behavior(nome, {init, update, ...}).
 * O mesmo motor roda no navegador, no pacote exportado (web, desktop, Android, iOS) e no modo de edição do ASTA. */
(function () {
  'use strict';
  var GE = window.GE = window.GE || {};
  GE.version = '0.19.3';
  var D = function () { return window.GE_DATA || { project: {}, scenes: {}, maps: {}, assets: { images: {}, sounds: {} }, dialogues: {}, start: 'main' }; };

  // ------------------------------------------------------------------ utilidades
  GE.clamp = function (v, a, b) { return v < a ? a : v > b ? b : v; };
  GE.lerp = function (a, b, t) { return a + (b - a) * t; };
  GE.rad = function (d) { return d * Math.PI / 180; };
  GE.rng = function (seed) { var s = (seed >>> 0) || 1; return function () { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; };
  GE.num = function (v, d) { v = Number(v); return isFinite(v) ? v : d; };
  GE.hex = function (c, d) { c = String(c || ''); return /^#[0-9a-f]{3,8}$/i.test(c) ? c : (d || '#cccccc'); };
  GE.shade = function (c, amt) { // clareia/escurece "#rrggbb"
    c = GE.hex(c); if (c.length === 4) c = '#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3];
    var n = parseInt(c.slice(1, 7), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
    var f = function (x) { return GE.clamp(Math.round(x + (amt > 0 ? (255 - x) * amt : x * amt)), 0, 255); };
    return '#' + ((1 << 24) + (f(r) << 16) + (f(g) << 8) + f(b)).toString(16).slice(1);
  };
  GE.err = function (m) { try { console.error('[GE]', m); } catch (e) { /* ok */ } if (GE.onError) GE.onError(String(m)); };

  // ------------------------------------------------------------------ estado do jogo (placar, vida, itens…)
  GE.state = { score: 0, hp: 3, max_hp: 3, coins: 0, total: 0, keys: {}, time: 0, level: 1, flags: {}, over: false, won: false };
  GE.resetState = function () {
    var s = (D().project.settings || {});
    GE.state = { score: 0, hp: GE.num(s.hp, 3), max_hp: GE.num(s.hp, 3), coins: 0, total: 0, keys: {}, time: 0, level: 1, flags: {}, over: false, won: false };
  };
  GE.damage = function (n, src) {
    var st = GE.state; if (st.over || st.won || (GE.invuln && GE.invuln > 0)) return;
    st.hp -= n; GE.invuln = 0.9; GE.sfx('hit'); if (GE.onHurt) GE.onHurt(src);
    if (st.hp <= 0) { st.hp = 0; GE.lose(); }
  };
  GE.heal = function (n) { var st = GE.state; st.hp = Math.min(st.max_hp, st.hp + n); GE.sfx('powerup'); };
  GE.addScore = function (n) { GE.state.score += n; };
  GE.win = function (msg) { if (GE.state.over || GE.state.won) return; GE.state.won = true; GE.sfx('win'); GE.banner(msg || GE.tr('Você venceu!'), 'win'); };
  GE.lose = function (msg) { if (GE.state.over || GE.state.won) return; GE.state.over = true; GE.sfx('lose'); GE.banner(msg || GE.tr('Fim de jogo'), 'lose'); };
  GE.tr = function (pt) { var lang = String((D().project || {}).language || 'pt').toLowerCase(); if (lang.indexOf('pt') === 0) return pt; return (GE.EN && GE.EN[pt]) || pt; };
  GE.EN = { 'Você venceu!': 'You win!', 'Fim de jogo': 'Game over', 'Toque ou aperte uma tecla para jogar de novo': 'Tap or press a key to play again', 'Toque para começar': 'Tap to start', 'Clique para começar': 'Click to start', 'Pausado': 'Paused', 'Coletado': 'Collected', 'Pegue tudo!': 'Collect everything!', 'E: falar': 'E: talk', 'Entrar em VR': 'Enter VR', 'Entrar em AR': 'Enter AR', 'VR/AR indisponível neste navegador: prévia no computador.': 'VR/AR is not available in this browser: desktop preview.', 'Toque no chão para colocar': 'Tap the ground to place', 'Falta uma chave': 'A key is missing' };

  // ------------------------------------------------------------------ entrada (teclado, mouse, toque)
  var keys = {}, pressed = {}, released = {};
  GE.input = {
    down: function (k) { return !!keys[k]; }, hit: function (k) { return !!pressed[k]; }, up: function (k) { return !!released[k]; },
    axis: function (neg, pos) { return (GE.input.down(pos) ? 1 : 0) - (GE.input.down(neg) ? 1 : 0); },
    mouse: { x: 0, y: 0, down: false, hit: false, dx: 0, dy: 0 },
    set: function (k, v) { if (v && !keys[k]) pressed[k] = true; if (!v && keys[k]) released[k] = true; keys[k] = v; },
    any: function () { return Object.keys(pressed).length > 0 || GE.input.mouse.hit; },
    clear: function () { pressed = {}; released = {}; GE.input.mouse.hit = false; GE.input.mouse.dx = 0; GE.input.mouse.dy = 0; },
  };
  var KEYMAP = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down', KeyA: 'left', KeyD: 'right', KeyW: 'up', KeyS: 'down', Space: 'jump', Enter: 'action', KeyE: 'action', KeyF: 'fire', KeyZ: 'fire', KeyX: 'fire', ShiftLeft: 'run', ShiftRight: 'run', KeyR: 'restart', Escape: 'pause', KeyP: 'pause', KeyQ: 'drop' };
  function bindInput(target) {
    window.addEventListener('keydown', function (e) {
      if (GE.editing || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || '')) return;
      var k = KEYMAP[e.code]; if (!k) return;
      if (/^(Space|Arrow)/.test(e.code)) e.preventDefault();
      GE.input.set(k, true); if (k === 'jump') GE.input.set('up_jump', true);
    });
    window.addEventListener('keyup', function (e) { var k = KEYMAP[e.code]; if (k) { GE.input.set(k, false); if (k === 'jump') GE.input.set('up_jump', false); } });
    window.addEventListener('blur', function () { Object.keys(keys).forEach(function (k) { keys[k] = false; }); });
    var M = GE.input.mouse;
    target.addEventListener('pointerdown', function (e) { if (GE.started || GE.editing === false) { var c = ac(); if (c && c.state === 'suspended' && c.resume) c.resume(); } M.down = true; M.hit = true; M.x = e.clientX; M.y = e.clientY; if (GE.onPointer) GE.onPointer('down', e); });
    window.addEventListener('pointerup', function (e) { M.down = false; if (GE.onPointer) GE.onPointer('up', e); });
    window.addEventListener('pointermove', function (e) { M.dx += e.movementX || 0; M.dy += e.movementY || 0; M.x = e.clientX; M.y = e.clientY; if (GE.onPointer) GE.onPointer('move', e); });
  }
  // botões na tela (celular/tablet): só aparecem em aparelhos de toque
  function touchControls(dim) {
    var box = document.getElementById('ge-touch'); if (!box || box.dataset.ready) return; box.dataset.ready = '1';
    var mk = function (cls, label, key) {
      var b = document.createElement('button'); b.className = 'ge-tb ' + cls; b.textContent = label; b.setAttribute('aria-label', key);
      var on = function (v) { return function (e) { e.preventDefault(); GE.input.set(key, v); b.classList.toggle('on', v); }; };
      b.addEventListener('pointerdown', on(true)); b.addEventListener('pointerup', on(false)); b.addEventListener('pointerleave', on(false)); b.addEventListener('pointercancel', on(false));
      box.appendChild(b); return b;
    };
    mk('l', '◀', 'left'); mk('r', '▶', 'right');
    if (dim === '3d' || (D().project.genre || '').match(/topdown|iso|shooter/)) { mk('u', '▲', 'up'); mk('d', '▼', 'down'); }
    mk('a', '●', 'jump'); mk('b', '◆', 'action');
    box.classList.remove('ge-hidden');
  }

  // ------------------------------------------------------------------ som: arquivos do jogo + sintetizador de reserva
  var audioCtx = null, audioOn = true, music = null, pool = {};
  function ac() { if (!audioCtx) { try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { audioCtx = false; } } return audioCtx; }
  GE.audio = { muted: false, volume: 1 };
  GE.setMuted = function (m) { GE.audio.muted = !!m; if (music) music.muted = !!m; };
  GE.playSound = function (key, opt) {
    opt = opt || {}; var url = (D().assets.sounds || {})[key]; if (!url || GE.audio.muted || !audioOn) return null;
    try {
      var base = pool[key] || (pool[key] = new Audio(url)); base.preload = 'auto';
      var a = opt.loop ? new Audio(url) : base.cloneNode(); a.volume = GE.clamp((opt.volume == null ? 1 : opt.volume) * GE.audio.volume, 0, 1); a.loop = !!opt.loop;
      var p = a.play(); if (p && p.catch) p.catch(function () { /* o navegador só libera o som depois de um toque */ });
      if (opt.loop && opt.music) { if (music) { try { music.pause(); } catch (e) { /* ok */ } } music = a; }
      return a;
    } catch (e) { return null; }
  };
  var BEEPS = { coin: [880, 0.08, 'square', 1320], jump: [330, 0.12, 'square', 660], hit: [140, 0.18, 'sawtooth', 60], win: [523, 0.4, 'triangle', 1046], lose: [220, 0.5, 'sawtooth', 70], powerup: [440, 0.2, 'triangle', 880], shoot: [700, 0.08, 'square', 300], select: [600, 0.05, 'sine', 800], step: [100, 0.03, 'sine', 90], door: [200, 0.2, 'triangle', 140], place: [500, 0.1, 'sine', 700] };
  GE.sfx = function (name) {
    var map = ((D().project.audio || {}).events || {}), key = map[name] || name;
    if ((D().assets.sounds || {})[key]) { GE.playSound(key); return; }
    var b = BEEPS[name]; var c = ac(); if (!b || !c || GE.audio.muted) return;
    try {
      var o = c.createOscillator(), g = c.createGain(); o.type = b[2]; o.frequency.setValueAtTime(b[0], c.currentTime); o.frequency.exponentialRampToValueAtTime(Math.max(20, b[3]), c.currentTime + b[1]);
      g.gain.setValueAtTime(0.12, c.currentTime); g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + b[1] + 0.02); o.connect(g); g.connect(c.destination); o.start(); o.stop(c.currentTime + b[1] + 0.03);
    } catch (e) { /* sem áudio */ }
  };
  GE.startMusic = function () { var m = (D().project.audio || {}).music; if (m && (D().assets.sounds || {})[m]) GE.playSound(m, { loop: true, volume: 0.45, music: true }); };

  // ------------------------------------------------------------------ comportamentos
  GE.behaviors = {};
  GE.behavior = function (name, impl) { GE.behaviors[name] = impl; };
  GE.behaviorsOf = function (n) { return n.behaviors || []; };

  GE.mapData = function (path) { var d = D().maps || {}; return d[path] || d[String(path || '').replace(/^\/+/, '')] || null; };

  // ------------------------------------------------------------------ cena: JSON -> nós
  var uid = 0;
  GE.makeNode = function (spec, parent) {
    var n = {}; for (var k in spec) if (k !== 'children' && k !== 'behaviors') n[k] = spec[k];
    n.id = n.id || ('n' + (++uid)); n.name = n.name || n.type; n.parent = parent || null; n.children = []; n.alive = true; n.tags = n.tags || [];
    n.spec = spec; n.bh = [];
    (spec.behaviors || []).forEach(function (b) {
      var impl = GE.behaviors[b.type]; if (!impl) { GE.err('comportamento desconhecido: ' + b.type); return; }
      var inst = { type: b.type, p: b, impl: impl, s: {} }; n.bh.push(inst);
    });
    (spec.children || []).forEach(function (c) { n.children.push(GE.makeNode(c, n)); });
    return n;
  };
  GE.walk = function (n, fn) { if (!n) return; if (fn(n) === false) return; for (var i = 0; i < n.children.length; i++) GE.walk(n.children[i], fn); };
  GE.find = function (name) { var out = null; GE.walk(GE.root, function (n) { if (n.alive && (n.name === name || n.id === name)) { out = n; return false; } }); return out; };
  GE.findTag = function (tag) { var out = []; GE.walk(GE.root, function (n) { if (n.alive && n.tags.indexOf(tag) >= 0) out.push(n); }); return out; };
  GE.add = function (parent, spec) { var n = GE.makeNode(spec, parent); (parent || GE.root).children.push(n); initNode(n); if (GE.R && GE.R.onAdd) GE.R.onAdd(n); return n; };
  GE.remove = function (n) { n.alive = false; if (GE.R && GE.R.onRemove) GE.R.onRemove(n); };
  // buscas por tag/comportamento com cache de um quadro (zerado a cada tick e a cada cena)
  GE._cache = {};
  GE.byTag = function (tag) { var c = GE._cache['t:' + tag]; if (c) return c; c = GE._cache['t:' + tag] = []; GE.walk(GE.root, function (n) { if (n.alive && n.tags.indexOf(tag) >= 0) c.push(n); }); return c; };
  GE.byBehavior = function (type) { var c = GE._cache['b:' + type]; if (c) return c; c = GE._cache['b:' + type] = []; GE.walk(GE.root, function (n) { if (n.alive && n.bh.some(function (b) { return b.type === type; })) c.push(n); }); return c; };
  GE.dist = function (a, b) { var dx = a.x - b.x, dy = a.y - b.y; if (GE.dim === '3d') { var dz = (a.z || 0) - (b.z || 0); return Math.sqrt(dx * dx + dy * dy * 0.25 + dz * dz); } return Math.sqrt(dx * dx + dy * dy); };
  GE.collectGarbage = function () { GE.walk(GE.root, function (n) { n.children = n.children.filter(function (c) { return c.alive; }); }); };
  function initNode(n) { GE.walk(n, function (x) { x.bh.forEach(function (b) { if (b.impl.init) { try { b.impl.init(x, b.p, b.s); } catch (e) { GE.err(b.type + '.init: ' + e.message); } } }); }); }
  GE.updateNodes = function (dt) {
    GE.walk(GE.root, function (n) {
      if (!n.alive) return false;
      for (var i = 0; i < n.bh.length; i++) { var b = n.bh[i]; if (b.impl.update) { try { b.impl.update(n, dt, b.p, b.s); } catch (e) { if (!b.err) { b.err = 1; GE.err(b.type + '.update: ' + e.message); } } } }
    });
  };

  // ------------------------------------------------------------------ HUD (DOM por cima do jogo)
  var hud = null;
  function mkHud() {
    hud = document.getElementById('ge-hud'); if (!hud) return;
    hud.innerHTML = '<div id="ge-labels"></div><div id="ge-banner" class="ge-hidden"></div><div id="ge-dialog" class="ge-hidden"></div><div id="ge-toast" class="ge-hidden"></div>';
  }
  GE.hudNodes = [];
  GE.paintHud = function () {
    if (!hud) return; var st = GE.state, root = document.getElementById('ge-labels'); if (!root) return;
    var html = '';
    GE.hudNodes.forEach(function (n) {
      if (!n.alive || n.visible === false) return;
      var anchor = n.anchor || (n.type === 'UIBar' ? 'top-right' : 'top-left'), size = GE.num(n.size, 18), col = GE.hex(n.color, n.type === 'UIBar' ? '#ff4d6d' : '#ffffff');
      if (n.type === 'UILabel') {
        var txt = String(n.text || '').replace(/\{(\w+)\}/g, function (m, k) { var v = k === 'time' ? Math.floor(st.time) : k === 'total' ? st.total : st[k]; return v == null ? '' : v; });
        html += '<div class="ge-ui ' + anchor + '" style="font-size:' + size + 'px;color:' + col + '">' + esc(txt) + '</div>';
      } else if (n.type === 'UIBar') {
        var cur = GE.num(st[n.bind || 'hp'], 0), mx = Math.max(1, GE.num(st['max_' + (n.bind || 'hp')], st.max_hp));
        html += '<div class="ge-ui ' + anchor + '"><div class="ge-bar" style="width:' + GE.num(n.w, 120) + 'px"><i style="width:' + GE.clamp(cur / mx * 100, 0, 100) + '%;background:' + col + '"></i></div></div>';
      }
    });
    if (html !== GE._lastHud) { root.innerHTML = html; GE._lastHud = html; }
  };
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  GE.banner = function (msg, cls) {
    var b = document.getElementById('ge-banner'); if (!b) return;
    b.className = 'ge-' + (cls || 'info'); b.innerHTML = '<div><h2>' + esc(msg) + '</h2><p>' + esc(GE.tr('Toque ou aperte uma tecla para jogar de novo')) + '</p></div>';
    GE.bannerAt = performance.now();
  };
  GE.hideBanner = function () { var b = document.getElementById('ge-banner'); if (b) b.className = 'ge-hidden'; };
  GE.toast = function (msg, ms) { var t = document.getElementById('ge-toast'); if (!t) return; t.textContent = msg; t.className = ''; clearTimeout(GE._tt); GE._tt = setTimeout(function () { t.className = 'ge-hidden'; }, ms || 1600); };
  // diálogos: lista de {speaker, text}; avança com ação/toque
  GE.say = function (lines, done) {
    var box = document.getElementById('ge-dialog'); if (!box || !lines || !lines.length) { if (done) done(); return; }
    var i = 0; GE.talking = true;
    function show() { var l = lines[i]; box.className = ''; box.innerHTML = (l.speaker ? '<b>' + esc(l.speaker) + '</b>' : '') + '<span>' + esc(l.text) + '</span><small>▶</small>'; }
    function next() { i++; if (i >= lines.length) { box.className = 'ge-hidden'; GE.talking = false; GE.dialogNext = null; if (done) done(); } else { GE.sfx('select'); show(); } }
    GE.dialogNext = next; show();
  };

  // ------------------------------------------------------------------ ciclo de vida
  GE.sceneName = '';
  GE.loadScene = function (name, override) {
    var data = D(), sc = override || data.scenes[name] || data.scenes[data.start] || data.scenes[Object.keys(data.scenes)[0]];
    if (!sc) { GE.err('o jogo não tem cenas'); return false; }
    GE.sceneName = name || data.start; GE.scene = sc; GE.hudNodes = []; GE.talking = false; GE.dialogNext = null; GE._lastHud = null; GE.invuln = 0;
    var oldS = GE.state; GE.resetState(); if (GE.keepScore) { GE.state.score = oldS.score; GE.state.hp = oldS.hp; GE.state.max_hp = oldS.max_hp; GE.keepScore = false; }
    GE.root = GE.makeNode(sc.root || { type: 'Node2D', name: 'Main', children: [] }, null);
    GE.walk(GE.root, function (n) { if (n.type === 'UILabel' || n.type === 'UIBar') GE.hudNodes.push(n); });
    var kind = (sc.kind || data.project.kind || '2d'), dim = (kind === '2d' || kind === '2.5d') ? '2d' : '3d';
    GE.dim = dim; GE.kind = kind;
    var R = dim === '2d' ? GE.Renderer2D : GE.Renderer3D;
    if (!R) { GE.err('motor ' + dim + ' não carregado'); return false; }
    if (GE.R && GE.R.dispose) GE.R.dispose();
    GE.R = R; R.setup(sc, GE.root, document.getElementById('ge-stage'));
    initNode(GE.root);
    if (R.afterInit) R.afterInit();
    GE.hideBanner(); GE.total = 0; GE.walk(GE.root, function (n) { if (n.alive && n.bh.some(function (b) { return b.type === 'collectible'; })) GE.state.total++; });
    return true;
  };
  GE.nextScene = function (name) {
    var data = D(); if (name && data.scenes[name]) { GE.keepScore = true; GE.loadScene(name); return; }
    var names = Object.keys(data.scenes), i = names.indexOf(GE.sceneName);
    if (i >= 0 && i < names.length - 1) { GE.keepScore = true; GE.state.level++; var lv = GE.state.level; GE.loadScene(names[i + 1]); GE.state.level = lv; } else GE.win();
  };
  GE.restart = function () { GE.loadScene(GE.sceneName); GE.hideBanner(); };

  var last = 0, running = false, paused = false, rafId = 0;
  function frame(ts) {
    if (!GE.xrLoop) rafId = requestAnimationFrame(frame);
    GE._cache = {};
    var dt = Math.min(0.05, (ts - last) / 1000 || 0.016); last = ts;
    if ((GE.state.over || GE.state.won) && !GE.editing) {
      if ((GE.input.any() || false) && performance.now() - (GE.bannerAt || 0) > 600) { GE.restart(); }
      GE.input.clear(); if (GE.R) GE.R.render(0); return;
    }
    if (GE.input.hit('pause') && !GE.editing) { paused = !paused; GE.toast(paused ? GE.tr('Pausado') : '', 700); }
    if (GE.input.hit('restart') && !GE.editing) GE.restart();
    if (GE.talking) { if (GE.input.hit('action') || GE.input.hit('jump') || GE.input.mouse.hit) { if (GE.dialogNext) GE.dialogNext(); } }
    else if (!paused && !GE.editing && GE.root) {
      GE.state.time += dt; if (GE.invuln > 0) GE.invuln -= dt;
      GE.updateNodes(dt); if (GE.R && GE.R.update) GE.R.update(dt); GE.collectGarbage();
    } else if (GE.editing && GE.R && GE.R.update) GE.R.update(0);
    if (GE.R) GE.R.render(dt);
    GE.paintHud(); GE.input.clear();
  }
  GE.start = function () {
    if (running && !GE.xrLoop) return; running = true; if (!GE.xrLoop) GE.startMusic(); last = performance.now(); if (!GE.xrLoop) rafId = requestAnimationFrame(frame);
  };
  GE.tick = function (ts) { frame(ts); };
  GE.stop = function () { running = false; cancelAnimationFrame(rafId); };

  GE.boot = function (opt) {
    opt = opt || {}; var data = D(); if (window.GE_EDIT) GE.editing = true;
    mkHud(); bindInput(document.getElementById('ge-stage') || document.body);
    if (window.GE_ERRORS) window.GE_ERRORS = [];
    GE.resetState();
    var imgs = data.assets.images || {}, keys2 = Object.keys(imgs), left = keys2.length; GE.images = {};
    var go = function () {
      var ok = GE.loadScene(data.start);
      if (!ok) return;
      var dim = GE.dim; if (window.matchMedia && (matchMedia('(pointer:coarse)').matches || 'ontouchstart' in window)) touchControls(dim);
      var startEl = document.getElementById('ge-start');
      var begin = function () { if (startEl) startEl.classList.add('ge-hidden'); ac(); if (audioCtx && audioCtx.resume) audioCtx.resume(); GE.started = true; GE.startMusic(); if (GE.R && GE.R.onStart) GE.R.onStart(); };
      if (opt.autostart || GE.editing) { if (startEl) startEl.classList.add('ge-hidden'); GE.started = true; }
      else if (startEl) { var btn = document.getElementById('ge-play'); if (btn) { btn.disabled = false; btn.textContent = GE.tr(GE.kind === 'vr' ? 'Clique para começar' : 'Clique para começar'); btn.onclick = begin; } }
      else begin();
      GE.start();
      if (window.parent !== window) { try { window.parent.postMessage({ ge: 'ready', kind: GE.kind }, '*'); } catch (e) { /* ok */ } }
    };
    if (!left) return go();
    keys2.forEach(function (k) { var im = new Image(); im.onload = im.onerror = function () { if (--left === 0) go(); }; im.src = imgs[k]; GE.images[k] = im; });
  };
  window.addEventListener('error', function (e) { GE.err((e.message || 'erro') + (e.lineno ? ' (linha ' + e.lineno + ')' : '')); });
})();
