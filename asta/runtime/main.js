/* ASTA runtime — orquestração: renderer, loop, HUD, interação, salvamento e controles. */
(function () {
  'use strict';
  const RT = window.RT, T = window.THREE, S = RT.S, esc = RT.esc;
  const W = window.ASTA_WORLD, META = window.ASTA_META || {}, CHARS = window.ASTA_CHARS || [];
  const SOUND = window.ASTA_SOUND || W.audio, UX = window.ASTA_UX || W.ux, CFG = window.ASTA_CONFIG || { mode: 'standalone' };
  const $ = (s) => document.querySelector(s);
  const canvas = $('#view'), hud = $('#hud'), startEl = $('#start'), playBtn = $('#s-play'), statusEl = $('#s-status');
  const GKEY = 'asta.game.' + (CFG.project || 'local'), SKEY = 'asta.save.' + (CFG.project || 'local');
  const debug = /[?&]debug/.test(location.search);

  function gs() { try { return Object.assign({ quality: 'auto', master: 0.8, music: 1, ambience: 1, muted: false }, JSON.parse(localStorage.getItem(GKEY) || '{}')); } catch (e) { return { quality: 'auto', master: 0.8, music: 1, ambience: 1, muted: false }; } }
  function gsSave(o) { try { localStorage.setItem(GKEY, JSON.stringify(o)); } catch (e) { /* ignorado */ } }
  const G = gs();

  // ---------------------------------------------------------------- tela inicial
  $('#s-title').textContent = W.title;
  $('#s-desc').textContent = W.description || '';
  $('#s-intro').textContent = UX.intro && UX.intro !== W.title ? UX.intro : '';
  $('#s-help').innerHTML = S.help.join(' &nbsp;·&nbsp; ');
  playBtn.textContent = S.loading;
  document.title = W.title;

  let renderer, world, player, npcs = [], agent, audio, quality, camera, running = false, started = false;
  const clock = { last: performance.now(), t: 0 };

  function fail(msg) { statusEl.textContent = '⚠ ' + msg; playBtn.textContent = '✕'; }

  function boot() {
    let hw; try { hw = RT.detectTier(); } catch (e) { hw = { tier: 'low', gpu: '' }; }
    const target = G.quality !== 'auto' ? G.quality : (W.quality.target !== 'auto' ? W.quality.target : hw.tier);
    const budget = Object.assign({}, W.quality.tiers[target] || W.quality.tiers.medium);
    try {
      renderer = new T.WebGLRenderer({ canvas, antialias: target !== 'low', powerPreference: 'high-performance' });
    } catch (e) { return fail('WebGL indisponível neste navegador/dispositivo.'); }
    renderer.shadowMap.enabled = budget.shadow > 0;
    renderer.shadowMap.type = target === 'high' ? T.PCFSoftShadowMap : T.PCFShadowMap;
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.setClearColor(0x000000);
    camera = new T.PerspectiveCamera(70, innerWidth / innerHeight, 0.1, 1500);

    world = new RT.World(W, budget, { maxAniso: Math.min(4, renderer.capabilities.getMaxAnisotropy()) });
    world.setDistance(1);
    quality = new RT.Quality(renderer, budget, world.scene, {
      shadows: (on) => world.setShadows(on), distance: (k) => world.setDistance(k), resize: onResize,
    });
    const byId = {}; CHARS.forEach((c) => (byId[c.id] = c));
    const pcard = byId[(W.player || {}).char] || null;
    player = new RT.Player(world, W, pcard, camera, canvas);
    (W.npcs || []).forEach((n) => { const card = byId[n.char]; if (card) npcs.push(new RT.NPC(world, n, card)); });
    // se o jogador nasceu dentro de um colisor, empurra para fora
    const c0 = world.collide(player.x, player.z, 0.4); player.teleport(c0.x, c0.z);

    agent = new RT.Agent({
      cfg: CFG, meta: META, world: W, chars: CHARS,
      getContext: ctxFor,
      onAction: (npc, a) => { npc.act(a); },
      onChange: () => scheduleSave(),
      onOpen: () => { player.enabled = false; player.releaseLock(); setHudDim(true); },
      onClose: () => { player.enabled = true; setHudDim(false); toast(S.clickToPlay); },
    });

    buildHud();
    bindInput();
    onResize();
    addEventListener('resize', onResize);
    world.onThunder = () => { if (audio) audio.thunder(); };
    player.onPerspective = (p) => { updateViewBtn(); scheduleSave(); };
    player.onLockChange = (l) => { if (!l && running && !agent.isOpen() && !settingsOpen) toast(S.clickToPlay); };
    loadSave().then((s) => {
      applySave(s);
      statusEl.textContent = S.quality_note + ': ' + S[target] + (hw.forced ? '' : '') + ' · ' + npcs.length + ' NPCs';
      playBtn.disabled = false; playBtn.textContent = S.play;
      if (debug) window.__asta = { world, player, npcs, agent, renderer, quality, camera, THREE: T, openChat: (id) => agent.open(npcs.find((n) => n.id === id)), RT };
    });
    requestAnimationFrame(frame);
  }

  // ---------------------------------------------------------------- HUD
  const SVG = {
    view: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>',
    snd: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4V5Z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/></svg>',
    mute: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4V5Z"/><path d="m22 9-6 6m0-6 6 6"/></svg>',
    cfg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/></svg>',
  };
  let el = {}, settingsOpen = false;
  function buildHud() {
    const h = UX.hud || {};
    hud.innerHTML =
      '<div class="hud-tl">' + esc(W.title) + '</div>' +
      (h.compass !== false ? '<div id="compass">N</div>' : '') +
      (h.minimap !== false ? '<canvas id="minimap" width="264" height="264"></canvas>' : '') +
      (h.clock !== false ? '<div id="clock"></div>' : '') +
      '<div id="place"></div>' + (h.crosshair !== false ? '<div id="crosshair"></div>' : '') +
      '<div id="prompt"></div><div id="toast"></div><div id="bubbles"></div>' +
      (debug ? '<div id="fps"></div>' : '') +
      '<div id="toolbar"><button class="btn icon" data-a="view" title="V">' + SVG.view + '</button><button class="btn icon" data-a="snd">' + SVG.snd + '</button><button class="btn icon" data-a="cfg" title="' + esc(S.settings) + '">' + SVG.cfg + '</button></div>' +
      '<div id="touch"><div id="joy"><i></i></div><div id="tbtns"><button class="btn" data-a="jump">⤒</button><button class="btn" data-a="talk">' + esc(S.mobileTalk) + '</button></div></div>';
    ['compass', 'minimap', 'clock', 'place', 'prompt', 'toast', 'bubbles', 'crosshair', 'fps', 'toolbar', 'joy'].forEach((id) => (el[id] = document.getElementById(id)));
    el.snd = hud.querySelector('[data-a=snd]'); el.view = hud.querySelector('[data-a=view]');
    el.snd.innerHTML = G.muted ? SVG.mute : SVG.snd;
    hud.querySelector('#toolbar').addEventListener('click', (e) => {
      const a = e.target.closest('[data-a]'); if (!a) return;
      if (a.dataset.a === 'view') player.togglePerspective();
      else if (a.dataset.a === 'snd') { G.muted = !G.muted; gsSave(G); el.snd.innerHTML = G.muted ? SVG.mute : SVG.snd; if (audio) audio.setMuted(G.muted); }
      else if (a.dataset.a === 'cfg') openSettings();
      a.blur();
    });
    el.prompt.addEventListener('click', () => { if (target) interact(target); });
    updateViewBtn();
  }
  function updateViewBtn() { if (el.view) el.view.classList.toggle('on', player.perspective === 'first'); }
  function setHudDim(dim) { ['crosshair', 'prompt'].forEach((i) => el[i] && (el[i].style.opacity = dim ? 0 : '')); }
  let toastT = 0;
  function toast(msg) { if (!el.toast) return; el.toast.textContent = msg; el.toast.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => el.toast.classList.remove('show'), 2600); }

  function ctxFor(npc) {
    const h = Math.floor(world.time), m = Math.floor((world.time % 1) * 60);
    const near = world.nearestLabel(npc.x, npc.z, 16);
    return {
      time: String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0'), night: world.night > 0.5, weather: world.weather,
      place: near ? near.text : '', playerName: player.name,
      nearby: npcs.filter((o) => o !== npc && Math.hypot(o.x - npc.x, o.z - npc.z) < 16).map((o) => o.name),
    };
  }

  // ---------------------------------------------------------------- interação
  let target = null;
  function findTarget() {
    const maxD = ((W.gameplay && W.gameplay.interaction_distance) || 3.8) + (player.perspective === 'third' ? 1.3 : 0);
    const fx = Math.sin(player.camYaw), fz = Math.cos(player.camYaw);
    let best = null, bs = 1e9;
    for (let i = 0; i < npcs.length; i++) {
      const n = npcs[i], dx = n.x - player.x, dz = n.z - player.z, d = Math.hypot(dx, dz);
      if (d > maxD) continue;
      const c = (dx * fx + dz * fz) / (d || 1);
      if (d > 1.7 && c < 0.45) continue;
      const sc = d * (2 - c);
      if (sc < bs) { bs = sc; best = n; }
    }
    return best;
  }
  function interact(n) {
    if (!n || agent.isOpen()) return;
    n.model.play('nod'); agent.open(n);
  }
  const ray = new T.Raycaster(), ndc = new T.Vector2();
  function clickPick(e) {
    const r = canvas.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hits = ray.intersectObjects(npcs.map((n) => n.hit), false);
    if (hits.length && hits[0].distance < 14) {
      const n = hits[0].object.userData.npc;
      if (Math.hypot(n.x - player.x, n.z - player.z) < 7) interact(n); else toast(RT.S.talk + ' ' + n.name + ' — ↑');
      return true;
    }
    return false;
  }

  function bindInput() {
    let drag = null, moved = 0;
    canvas.addEventListener('pointerdown', (e) => { if (!running || agent.isOpen()) return; drag = { x: e.clientX, y: e.clientY, id: e.pointerId, touch: e.pointerType === 'touch' }; moved = 0; });
    addEventListener('pointermove', (e) => {
      if (!drag || e.pointerId !== drag.id || player.locked) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY; moved += Math.abs(dx) + Math.abs(dy);
      if (moved > 3) player.look(dx * (drag.touch ? 1.4 : 1), dy * (drag.touch ? 1.4 : 1));
    });
    addEventListener('pointerup', (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      const wasClick = moved < 6; drag = null;
      if (!running || agent.isOpen() || !wasClick) return;
      if (e.target !== canvas) return;
      if (player.locked) { if (target) interact(target); return; }
      if (!clickPick(e)) player.requestLock();
    });
    addEventListener('keydown', (e) => {
      if (!running || e.target.matches('input,textarea,select')) return;
      if (e.code === 'KeyE' && !agent.isOpen()) { if (target) interact(target); }
      else if (e.code === 'KeyM' && el.minimap) el.minimap.style.display = el.minimap.style.display === 'none' ? '' : 'none';
      else if (e.code === 'Escape' && agent.isOpen()) agent.close();
    });
    // toque
    const isTouch = matchMedia('(pointer:coarse)').matches || 'ontouchstart' in window;
    if (isTouch) {
      document.body.classList.add('touch');
      const joy = el.joy, knob = joy.firstElementChild; let jid = null;
      const set = (e) => {
        const r = joy.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        let dx = (e.clientX - cx) / (r.width / 2), dy = (e.clientY - cy) / (r.height / 2); const l = Math.hypot(dx, dy); if (l > 1) { dx /= l; dy /= l; }
        player.touch.x = dx; player.touch.y = dy; knob.style.transform = 'translate(' + dx * 38 + 'px,' + dy * 38 + 'px)';
      };
      joy.addEventListener('pointerdown', (e) => { jid = e.pointerId; joy.setPointerCapture(jid); set(e); });
      joy.addEventListener('pointermove', (e) => { if (e.pointerId === jid) set(e); });
      const end = (e) => { if (e.pointerId === jid) { jid = null; player.touch.x = player.touch.y = 0; knob.style.transform = ''; } };
      joy.addEventListener('pointerup', end); joy.addEventListener('pointercancel', end);
      hud.querySelector('#tbtns').addEventListener('click', (e) => {
        const a = e.target.closest('[data-a]'); if (!a) return;
        if (a.dataset.a === 'jump') player.jump(); else if (target) interact(target);
      });
    }
    addEventListener('pagehide', () => saveNow(true));
    document.addEventListener('visibilitychange', () => { if (document.hidden) saveNow(true); });
  }

  // ---------------------------------------------------------------- minimapa / bússola
  const COL = { house: '#d8c9a8', cabin: '#b08a5a', tower: '#e0e0e0', ruin: '#8a8a82', tent: '#c9a24a', stall: '#c9a24a', well: '#6aa0c8', campfire: '#ff9a3a', statue: '#cfcfcf', barn: '#c0503a', pillar: '#cfcfcf', stone_circle: '#9a9a94', lamp: '#ffd27a', sign: '#d8c9a8', bench: '#8a6a3f', crates: '#8a6a3f', fence: '#6b4a2b' };
  function drawMap() {
    if (!el.minimap || el.minimap.style.display === 'none') return;
    const c = el.minimap.getContext('2d'), s = el.minimap.width, R = 80, k = s / 2 / R;
    c.clearRect(0, 0, s, s); c.save(); c.beginPath(); c.arc(s / 2, s / 2, s / 2 - 2, 0, 7); c.clip();
    c.fillStyle = 'rgba(0,0,0,.55)'; c.fillRect(0, 0, s, s);
    c.strokeStyle = 'rgba(255,255,255,.08)'; c.lineWidth = 1; c.beginPath(); c.arc(s / 2, s / 2, s / 4, 0, 7); c.stroke();
    // borda do mundo
    c.strokeStyle = 'rgba(255,255,255,.25)'; c.strokeRect(s / 2 + (-world.half - player.x) * k, s / 2 + (-world.half - player.z) * k, world.size * k, world.size * k);
    (W.structures || []).forEach((st) => {
      const x = s / 2 + (st.x - player.x) * k, y = s / 2 + (st.z - player.z) * k; if (Math.abs(x - s / 2) > s / 2 + 8 || Math.abs(y - s / 2) > s / 2 + 8) return;
      c.fillStyle = COL[st.type] || '#aaa'; const r = st.type === 'lamp' || st.type === 'sign' ? 3 : st.type === 'tower' || st.type === 'house' || st.type === 'barn' ? 7 : 5; c.fillRect(x - r / 2, y - r / 2, r, r);
    });
    npcs.forEach((n) => { const x = s / 2 + (n.x - player.x) * k, y = s / 2 + (n.z - player.z) * k; c.fillStyle = '#6cb6ff'; c.beginPath(); c.arc(x, y, 5, 0, 7); c.fill(); });
    c.translate(s / 2, s / 2); c.rotate(Math.PI - player.camYaw);
    c.fillStyle = '#fff'; c.beginPath(); c.moveTo(0, -11); c.lineTo(7, 8); c.lineTo(0, 4); c.lineTo(-7, 8); c.closePath(); c.fill();
    c.restore();
  }
  const DIRS = RT.lang.indexOf('pt') === 0 ? ['N', 'NE', 'L', 'SE', 'S', 'SO', 'O', 'NO'] : ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  let lastPlace = '', placeT = 0, hudT = 0;
  function updateHud(dt) {
    hudT -= dt; if (hudT > 0) return; hudT = 0.12;
    if (el.compass) {
      const b = (Math.atan2(Math.sin(player.camYaw), -Math.cos(player.camYaw)) * 180 / Math.PI + 360) % 360;
      el.compass.textContent = DIRS[Math.round(b / 45) % 8] + '  ' + Math.round(b) + '°';
    }
    if (el.clock) { const h = Math.floor(world.time), m = Math.floor((world.time % 1) * 60); el.clock.textContent = (world.night > 0.5 ? '☾ ' : '☀ ') + String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0'); }
    const near = world.nearestLabel(player.x, player.z, 14);
    const txt = near ? near.text : '';
    if (txt !== lastPlace) { lastPlace = txt; if (txt) { el.place.textContent = txt; el.place.classList.add('show'); clearTimeout(placeT); placeT = setTimeout(() => el.place.classList.remove('show'), 3200); } }
    target = agent.isOpen() ? null : findTarget();
    if (target) { el.prompt.innerHTML = '<span class="kbd">E</span> &nbsp;' + esc(S.talk) + ' <b>' + esc(target.name) + '</b>'; el.prompt.classList.add('show'); } else el.prompt.classList.remove('show');
    drawMap();
    if (el.fps) el.fps.textContent = Math.round(quality.fps) + ' fps · q' + quality.level + ' · pr' + quality.pr.toFixed(2) + ' · ' + renderer.info.render.calls + ' calls';
  }
  const bubbleEls = new Map(), tmpV = new T.Vector3();
  function updateBubbles() {
    const now = performance.now();
    npcs.forEach((n) => {
      let b = bubbleEls.get(n);
      if (n.bubble && n.bubble.until > now) {
        if (!b) { b = document.createElement('div'); b.className = 'bubble'; el.bubbles.appendChild(b); bubbleEls.set(n, b); }
        if (b.dataset.t !== n.bubble.text) { b.dataset.t = n.bubble.text; b.innerHTML = '<b>' + esc(n.name) + '</b>' + esc(n.bubble.text); }
        n.headPos(tmpV).project(camera);
        const vis = tmpV.z < 1 && tmpV.z > -1;
        b.style.display = vis ? '' : 'none'; b.style.left = (tmpV.x * 0.5 + 0.5) * innerWidth + 'px'; b.style.top = (-tmpV.y * 0.5 + 0.5) * innerHeight + 'px';
      } else if (b) { b.remove(); bubbleEls.delete(n); n.bubble = null; }
    });
  }

  // ---------------------------------------------------------------- salvamento
  let saveTimer = 0, dirty = false;
  function collect() {
    return { v: 1, saved: new Date().toISOString(), time: world.time, player: { x: +player.x.toFixed(2), z: +player.z.toFixed(2), yaw: +player.camYaw.toFixed(3), perspective: player.perspective },
      npcs: Object.fromEntries(npcs.map((n) => [n.id, n.snapshot()])), agent: agent.exportState() };
  }
  async function loadSave() {
    try {
      if (CFG.mode === 'hosted') { const r = await fetch(CFG.api + '/save'); return await r.json(); }
      return JSON.parse(localStorage.getItem(SKEY) || '{}');
    } catch (e) { return {}; }
  }
  function applySave(s) {
    if (!s || !s.v) return;
    if (typeof s.time === 'number') world.setTime(s.time);
    if (s.player) { player.teleport(s.player.x, s.player.z); player.camYaw = s.player.yaw || 0; player.yaw = player.camYaw; if (s.player.perspective) player.perspective = s.player.perspective; const c = world.collide(player.x, player.z, 0.4); player.teleport(c.x, c.z); }
    npcs.forEach((n) => n.restore((s.npcs || {})[n.id]));
    agent.importState(s.agent);
    updateViewBtn();
  }
  function saveNow(beacon) {
    if (!started) return;
    dirty = false;
    const data = JSON.stringify(collect());
    try {
      if (CFG.mode === 'hosted') {
        if (beacon && navigator.sendBeacon) navigator.sendBeacon(CFG.api + '/save', new Blob([data], { type: 'application/json' }));
        else fetch(CFG.api + '/save', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: data, keepalive: data.length < 60000 }).catch(() => {});
      } else localStorage.setItem(SKEY, data);
    } catch (e) { /* cota/privado: ignora */ }
  }
  function scheduleSave() { dirty = true; clearTimeout(saveTimer); saveTimer = setTimeout(() => saveNow(), 2500); }

  // ---------------------------------------------------------------- configurações
  function openSettings() {
    settingsOpen = true; player.releaseLock();
    let box = document.getElementById('settings');
    if (!box) { box = document.createElement('div'); box.id = 'settings'; document.getElementById('app').appendChild(box); }
    const sel = (v, opts) => opts.map((o) => '<option value="' + o[0] + '"' + (v === o[0] ? ' selected' : '') + '>' + esc(o[1]) + '</option>').join('');
    box.innerHTML = '<div class="panel"><h2>' + esc(S.settings) + '</h2>' +
      '<h3>' + esc(S.quality) + '</h3><div class="row"><div><label>' + esc(S.quality) + '</label><select data-g="quality">' + sel(G.quality, [['auto', S.auto], ['low', S.low], ['medium', S.medium], ['high', S.high]]) + '</select></div>' +
      '<div><label>' + esc(S.perspective) + '</label><select data-p="persp">' + sel(player.perspective, [['third', S.third], ['first', S.first]]) + '</select></div></div>' +
      '<h3>Audio</h3><label>' + esc(S.volume) + '</label><input type="range" min="0" max="1" step="0.05" data-g="master" value="' + G.master + '">' +
      '<label>' + esc(S.music) + '</label><input type="range" min="0" max="1" step="0.05" data-g="music" value="' + G.music + '">' +
      '<label>' + esc(S.ambience) + '</label><input type="range" min="0" max="1" step="0.05" data-g="ambience" value="' + G.ambience + '">' +
      '<h3>' + esc(S.ai) + '</h3><div id="ai-box">' + agent.settingsHTML() + '</div>' +
      '<label class="check"><input type="checkbox" data-a2="voice"' + (agent.settings.voiceReply ? ' checked' : '') + '>' + esc(S.voiceReply) + '</label>' +
      '<label>' + esc(S.autonomy) + '</label><select data-a2="auto">' + sel(agent.settings.autonomy, [['off', S.off], ['low', S.lowA], ['high', S.highA]]) + '</select>' +
      '<label>' + esc(S.sttLang) + '</label><input data-a2="stt" placeholder="auto  ·  pt-BR  ·  en-US  ·  ja-JP" value="' + esc(agent.settings.sttLang) + '">' +
      '<div class="foot"><button class="btn" data-x="reset">' + esc(S.resetSave) + '</button><button class="btn" data-x="reload">' + esc(S.reload) + '</button><button class="btn primary" data-x="close" style="padding:8px 20px;font-size:14px">' + esc(S.cancel) + '</button></div></div>';
    box.classList.add('open');
    agent.bindSettings(box.querySelector('#ai-box'));
    box.onclick = (e) => { if (e.target === box) closeSettings(); const x = e.target.closest('[data-x]'); if (!x) return;
      if (x.dataset.x === 'close') closeSettings();
      else if (x.dataset.x === 'reload') { saveNow(); location.reload(); }
      else if (x.dataset.x === 'reset') { try { localStorage.removeItem(SKEY); } catch (er) { /* ok */ } if (CFG.mode === 'hosted') fetch(CFG.api + '/save', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: '{}' }); location.reload(); } };
    box.oninput = box.onchange = (e) => {
      const t = e.target;
      if (t.dataset.g) { G[t.dataset.g] = t.type === 'range' ? parseFloat(t.value) : t.value; gsSave(G); if (audio) { audio.setMasterVolume(G.master); audio.setMusicVolume(G.music); audio.setAmbienceVolume(G.ambience); } }
      else if (t.dataset.p) { player.perspective = t.value; player._camInit = false; updateViewBtn(); scheduleSave(); }
      else if (t.dataset.a2) { const k = t.dataset.a2; if (k === 'voice') agent.settings.voiceReply = t.checked; else if (k === 'auto') agent.settings.autonomy = t.value; else if (k === 'stt') agent.settings.sttLang = t.value.trim() || 'auto'; agent.saveSettings(); }
    };
  }
  function closeSettings() { settingsOpen = false; const b = document.getElementById('settings'); if (b) b.classList.remove('open'); }

  // ---------------------------------------------------------------- loop
  function onResize() {
    if (!renderer) return;
    renderer.setSize(innerWidth, innerHeight, false);
    camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  }
  let orbit = 0, acc = 0;
  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(0.05, (now - clock.last) / 1000); clock.last = now; clock.t += dt;
    if (!world || document.hidden) return;
    if (running) {
      player.update(dt, npcs);
      for (let i = 0; i < npcs.length; i++) npcs[i].update(dt, player, clock.t, npcs);
      updateHud(dt); updateBubbles();
      agent.tickAutonomy(dt, npcs, player, settingsOpen);
      acc += dt; if (acc > 20) { acc = 0; saveNow(); }
    } else {
      // pano de fundo da tela inicial: câmera orbitando o ponto de partida
      orbit += dt * 0.08;
      const cx = player.x, cz = player.z, y = player.y + 5.5;
      camera.position.set(cx + Math.sin(orbit) * 16, y, cz + Math.cos(orbit) * 16);
      camera.lookAt(cx, player.y + 2, cz); camera.fov = 60; camera.updateProjectionMatrix();
      player.model.root.position.set(player.x, player.y, player.z); player.model.root.visible = true; player.model.update(dt, 0, false);
      for (let i = 0; i < npcs.length; i++) npcs[i].update(dt, { x: player.x, z: player.z }, clock.t, npcs);
    }
    world.update(dt, camera.position, { x: player.x, y: player.y, z: player.z }, clock.t);
    renderer.toneMappingExposure = (world.baseExposure || 1) * (world.weather === 'storm' && world.flash ? 1 + world.flash : 1);
    if (audio) audio.update(world.night);
    quality.tick(dt);
    renderer.render(world.scene, camera);
  }

  playBtn.addEventListener('click', () => {
    if (!world) return;
    startEl.classList.add('hidden'); running = true; started = true;
    audio = new RT.Audio(SOUND, UX);
    audio.setMuted(G.muted); audio.vol.master = G.master; audio.vol.music = G.music; audio.vol.ambience = G.ambience;
    audio.start({ biome: world.env.biome, weather: world.weather });
    audio.setMasterVolume(G.master); audio.setMusicVolume(G.music); audio.setAmbienceVolume(G.ambience);
    player.onStep = (run) => audio.footstep(run, world.env.biome);
    if (player.perspective === 'third' || true) player._camInit = false;
    player.requestLock();
    toast(RT.S.help.slice(0, 3).join('  ').replace(/<[^>]+>/g, ''));
    window.focus();
  });

  setTimeout(boot, 30);
})();
