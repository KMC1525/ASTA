/* ASTA Game Engine — motor 3D / VR / AR (three.js). Terreno por mapa de alturas, céu, luzes, personagens simples, câmera em 1ª/3ª pessoa,
 * WebXR (VR com teletransporte e pegar objetos; AR com marcador de chão e colocar objetos). Sem WebXR no navegador, roda em prévia no computador. */
(function () {
  'use strict';
  var GE = window.GE, T = window.THREE, N = GE.num, C = GE.clamp;
  var R = GE.Renderer3D = {};

  // ------------------------------------------------------------------ preparação
  R.setup = function (scene, root, stage) {
    R.scene3 = scene; R.settings = scene.settings || {}; R.stage = stage; R.kind = scene.kind || GE.kind; R.pops = [];
    R.xr = { active: false, mode: '', supported: false }; R.solids = []; R.terrains = []; R.camNode = null; R.player = null;
    if (!T) { stage.innerHTML = '<p style="color:#fff;padding:20px">three.js não carregou.</p>'; return; }
    if (!R.renderer) {
      R.renderer = new T.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
      R.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1)); R.renderer.shadowMap.enabled = R.settings.shadows !== false; R.renderer.shadowMap.type = T.PCFSoftShadowMap;
      R.renderer.toneMapping = T.ACESFilmicToneMapping; R.renderer.toneMappingExposure = 1.05;
      R.canvas = R.renderer.domElement; R.canvas.id = 'ge-canvas'; R.canvas.tabIndex = 0; stage.appendChild(R.canvas); window.addEventListener('resize', R.resize);
    } else if (!R.canvas.parentNode) stage.appendChild(R.canvas);
    R.renderer.xr.enabled = (R.kind === 'vr' || R.kind === 'ar');
    R.three = new T.Scene(); R.three.background = new T.Color(GE.hex(R.settings.sky_bottom || R.settings.bg, '#87b8e8'));
    R.camera = new T.PerspectiveCamera(70, 1, 0.05, 1200); R.rig = new T.Group(); R.rig.add(R.camera); R.three.add(R.rig);
    R.world = new T.Group(); R.three.add(R.world);
    R.yaw = 0; R.pitch = 0; R.orbit = { yaw: 0.8, pitch: 0.5, dist: 14, tx: 0, ty: 0, tz: 0 };
    R.resize();
    build(root, R.world);
    R.terrains.forEach(function (t) { if (t.node.objects !== false) spawnObjects(t); });
    // luz padrão se a cena não tiver nenhuma
    var hasLight = false; GE.walk(root, function (n) { if (n.type === 'Light3D') hasLight = true; });
    if (!hasLight) { var h = new T.HemisphereLight(0xcfe8ff, 0x6b5a45, 0.9 * Math.PI); R.three.add(h); var d = new T.DirectionalLight(0xffffff, 1.1 * Math.PI); d.position.set(30, 50, 20); d.castShadow = R.settings.shadows !== false; setShadow(d, 60); R.three.add(d); }
    R.pointerSetup();
  };
  R.dispose = function () {
    if (R.renderer && R.renderer.xr.isPresenting) { var s = R.renderer.xr.getSession(); if (s) s.end(); }
    if (R.three) R.three.traverse(function (o) { if (o.geometry) o.geometry.dispose(); if (o.material) { (Array.isArray(o.material) ? o.material : [o.material]).forEach(function (m) { if (m.map) m.map.dispose(); m.dispose(); }); } });
    if (R.renderer) R.renderer.setAnimationLoop(null);
  };
  R.resize = function () {
    if (!R.renderer || !R.stage) return; var w = R.stage.clientWidth || window.innerWidth, h = R.stage.clientHeight || window.innerHeight; R.w = w; R.h = h;
    if (!R.renderer.xr.isPresenting) R.renderer.setSize(w, h); R.camera.aspect = w / h; R.camera.updateProjectionMatrix();
  };
  function setShadow(l, ext) { l.shadow.mapSize.set(2048, 2048); var c = l.shadow.camera; c.left = -ext; c.right = ext; c.top = ext; c.bottom = -ext; c.near = 1; c.far = ext * 4; l.shadow.bias = -0.0004; }

  // ------------------------------------------------------------------ construção dos nós
  function mat(n, extra) {
    var o = { color: new T.Color(GE.hex(n.color, '#9aa7b5')), roughness: n.rough == null ? 0.78 : C(N(n.rough, 0.78), 0, 1), metalness: C(N(n.metal, 0), 0, 1) };
    if (n.emissive) { o.emissive = new T.Color(GE.hex(n.emissive, '#000')); o.emissiveIntensity = N(n.glow, 0.9); }
    if (n.opacity != null && n.opacity < 1) { o.transparent = true; o.opacity = n.opacity; }
    if (n.flat) o.flatShading = true; if (extra) for (var k in extra) o[k] = extra[k];
    var m = new T.MeshStandardMaterial(o);
    if (n.image && GE.images && GE.images[n.image] && GE.images[n.image].complete) { var tx = new T.Texture(GE.images[n.image]); tx.needsUpdate = true; tx.colorSpace = T.SRGBColorSpace; tx.wrapS = tx.wrapT = T.RepeatWrapping; tx.repeat.set(N(n.rep, 1), N(n.rep, 1)); m.map = tx; }
    return m;
  }
  function geom(n) {
    var w = N(n.w, 1), h = N(n.h, 1), d = N(n.d, 1), s = n.shape || 'box';
    if (s === 'sphere') return new T.SphereGeometry(w / 2, 24, 16);
    if (s === 'cylinder') return new T.CylinderGeometry(w / 2, w / 2, h, 20);
    if (s === 'cone') return new T.ConeGeometry(w / 2, h, 20);
    if (s === 'plane') return new T.PlaneGeometry(w, d);
    if (s === 'torus') return new T.TorusGeometry(w / 2, Math.max(0.03, Math.min(w, h) / 10), 12, 28);
    if (s === 'capsule') return new T.CapsuleGeometry(w / 2, Math.max(0.01, h - w), 6, 14);
    if (s === 'octa') return new T.OctahedronGeometry(w / 2);
    if (s === 'icosa') return new T.IcosahedronGeometry(w / 2, 0);
    return new T.BoxGeometry(w, h, d);
  }
  function humanoid(n) {
    var g = new T.Group(), col = GE.hex(n.color, '#4cc9f0'), skin = GE.hex(n.skin, '#f1c27d'), sc = N(n.scale, 1);
    var body = new T.Mesh(new T.CapsuleGeometry(0.28, 0.55, 5, 12), new T.MeshStandardMaterial({ color: col, roughness: 0.7 })); body.position.y = 0.9; body.castShadow = true; g.add(body);
    var head = new T.Mesh(new T.SphereGeometry(0.2, 16, 12), new T.MeshStandardMaterial({ color: skin, roughness: 0.8 })); head.position.y = 1.5; head.castShadow = true; g.add(head);
    var eyeM = new T.MeshBasicMaterial({ color: 0x111111 }); [-0.07, 0.07].forEach(function (x) { var e = new T.Mesh(new T.SphereGeometry(0.03, 8, 6), eyeM); e.position.set(x, 1.53, 0.17); g.add(e); });
    var legM = new T.MeshStandardMaterial({ color: GE.shade(col, -0.45), roughness: 0.8 }); g.legs = [];
    [-0.12, 0.12].forEach(function (x) { var p = new T.Group(); p.position.set(x, 0.62, 0); var l = new T.Mesh(new T.BoxGeometry(0.13, 0.6, 0.15), legM); l.position.y = -0.3; l.castShadow = true; p.add(l); g.add(p); g.legs.push(p); });
    g.arms = []; [-0.36, 0.36].forEach(function (x) { var p = new T.Group(); p.position.set(x, 1.2, 0); var a = new T.Mesh(new T.BoxGeometry(0.1, 0.5, 0.1), new T.MeshStandardMaterial({ color: col, roughness: 0.7 })); a.position.y = -0.22; a.castShadow = true; p.add(a); g.add(p); g.arms.push(p); });
    g.scale.setScalar(sc); return g;
  }
  function labelSprite(n) {
    var c = document.createElement('canvas'); c.width = 512; c.height = 128; var x = c.getContext('2d'); x.font = '600 56px system-ui,sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
    x.fillStyle = 'rgba(0,0,0,.45)'; x.fillRect(0, 24, 512, 80); x.fillStyle = GE.hex(n.color, '#ffffff'); x.fillText(String(n.text || ''), 256, 64);
    var tex = new T.CanvasTexture(c); tex.colorSpace = T.SRGBColorSpace; var sp = new T.Sprite(new T.SpriteMaterial({ map: tex, transparent: true, depthWrite: false })); var s = N(n.size, 1.2); sp.scale.set(4 * s, s, 1); return sp;
  }
  function skyDome(top, bottom, stars) {
    var g = new T.SphereGeometry(500, 24, 16), cols = [], pos = g.attributes.position, ct = new T.Color(top), cb = new T.Color(bottom);
    for (var i = 0; i < pos.count; i++) { var t = C((pos.getY(i) + 80) / 420, 0, 1); var c = cb.clone().lerp(ct, Math.pow(t, 0.7)); cols.push(c.r, c.g, c.b); }
    g.setAttribute('color', new T.Float32BufferAttribute(cols, 3)); var m = new T.Mesh(g, new T.MeshBasicMaterial({ vertexColors: true, side: T.BackSide, fog: false, depthWrite: false })); m.renderOrder = -10;
    var grp = new T.Group(); grp.add(m);
    if (stars) { var rnd = GE.rng(11), p = []; for (var k = 0; k < 600; k++) { var a = rnd() * 6.283, b = Math.acos(rnd() * 0.95 + 0.04); p.push(Math.cos(a) * Math.sin(b) * 480, Math.cos(b) * 480, Math.sin(a) * Math.sin(b) * 480); } var sg = new T.BufferGeometry(); sg.setAttribute('position', new T.Float32BufferAttribute(p, 3)); grp.add(new T.Points(sg, new T.PointsMaterial({ color: 0xffffff, size: 1.6, sizeAttenuation: false, fog: false }))); }
    return grp;
  }
  function build(n, parent) {
    var o = null, s = R.settings;
    switch (n.type) {
      case 'Mesh3D': { o = new T.Mesh(geom(n), mat(n)); o.castShadow = n.shadow !== false && n.shape !== 'plane'; o.receiveShadow = true; if (n.shape === 'plane') o.rotation.x = -Math.PI / 2; break; }
      case 'Light3D': {
        var col = new T.Color(GE.hex(n.color, '#ffffff')), k = n.kind || 'directional', it = N(n.intensity, 1) * Math.PI;   // física: π equivale à iluminação clássica
        if (k === 'ambient') o = new T.AmbientLight(col, it); else if (k === 'hemisphere') o = new T.HemisphereLight(col, new T.Color(GE.hex(n.color2, '#554433')), it);
        else if (k === 'point') { o = new T.PointLight(col, it * 1.6, N(n.range, 30), 1.6); o.castShadow = !!n.shadow; }
        else if (k === 'spot') { o = new T.SpotLight(col, it * 2, N(n.range, 40), 0.6, 0.4, 1.2); o.castShadow = !!n.shadow; }
        else { o = new T.DirectionalLight(col, it); o.castShadow = n.shadow !== false && s.shadows !== false; setShadow(o, N(n.extent, 60)); o.position.set(N(n.x, 30), N(n.y, 50), N(n.z, 20)); n._dirpos = true; }
        break; }
      case 'Camera3D': R.camNode = n; o = new T.Group(); break;
      case 'Sky3D': { var tp = GE.hex(n.top, '#4a90d9'), bt = GE.hex(n.bottom, '#cfe8ff'); R.three.add(skyDome(tp, bt, n.stars)); R.three.background = new T.Color(bt); if (N(n.fog, 0.35) > 0) R.three.fog = new T.Fog(new T.Color(bt), 20, 20 + 280 * (1 - C(N(n.fog, 0.35), 0, 1)) + 40); o = new T.Group(); break; }
      case 'Water3D': { var sz = N(n.size, 400); o = new T.Mesh(new T.PlaneGeometry(sz, sz), new T.MeshStandardMaterial({ color: GE.hex(n.color, '#2f7fbf'), transparent: true, opacity: N(n.opacity, 0.78), roughness: 0.25, metalness: 0.1 })); o.rotation.x = -Math.PI / 2; o.position.y = N(n.level, 0); n._fixedY = true; o.receiveShadow = true; break; }
      case 'Humanoid3D': o = humanoid(n); break;
      case 'Label3D': o = labelSprite(n); break;
      case 'Terrain3D': { o = buildTerrain(n); break; }
      case 'XRRig': o = new T.Group(); R.rigNode = n; break;
      case 'AudioPlayer': case 'UILabel': case 'UIBar': case 'Node3D': default: o = new T.Group();
    }
    n.obj = o; if (o) { o.userData.nodeId = n.id; parent.add(o); applyTransform(n); }
    n.children.forEach(function (c) { build(c, o || parent); });
    return o;
  }
  function applyTransform(n) {
    var o = n.obj; if (!o) return;
    if (!n._dirpos && !n._fixedY && n.type !== 'Terrain3D' && n.type !== 'Sky3D') o.position.set(N(n.x, 0), N(n.y, 0), N(n.z, 0));
    else if (n._dirpos) o.position.set(N(n.x, 30), N(n.y, 50), N(n.z, 20));
    else if (n._fixedY) o.position.set(N(n.x, 0), N(n.level, 0), N(n.z, 0));
    if (n.type === 'Mesh3D' && n.shape === 'plane') { o.rotation.set(-Math.PI / 2 + GE.rad(N(n.rx, 0)), GE.rad(N(n.ry, 0)), GE.rad(N(n.rz, 0))); }
    else if (n.type !== 'Light3D') o.rotation.set(GE.rad(N(n.rx, 0)), GE.rad(N(n.ry, 0)), GE.rad(N(n.rz, 0)), 'YXZ');
    if (n.type !== 'Label3D' && n.type !== 'Terrain3D') o.scale.set(N(n.sx, 1) * (n.type === 'Humanoid3D' ? N(n.scale, 1) : 1), N(n.sy, 1) * (n.type === 'Humanoid3D' ? N(n.scale, 1) : 1), N(n.sz, 1) * (n.type === 'Humanoid3D' ? N(n.scale, 1) : 1));
    o.visible = n.visible !== false;
  }
  R.onAdd = function (n) { var parent = (n.parent && n.parent.obj) || R.world; build(n, parent); n.obj && n.obj.updateMatrixWorld(true); GE.walk(n, function (x) { if (x.solid && x.obj) R.solids.push(x); }); };
  R.onRemove = function (n) { GE.walk(n, function (x) { x.alive = false; if (x.obj && x.obj.parent) x.obj.parent.remove(x.obj); }); R.solids = R.solids.filter(function (s) { return s.alive; }); };

  // ------------------------------------------------------------------ terreno
  function buildTerrain(n) {
    var data = GE.mapData(n.map); if (!data) { return new T.Group(); }
    var res = N(data.res, 65), size = N(data.size, 200), hs = N(data.height, 24), hm = data.heights || [];
    var geo = new T.PlaneGeometry(size, size, res - 1, res - 1); geo.rotateX(-Math.PI / 2);
    var pos = geo.attributes.position, cols = new Float32Array(pos.count * 3), pal = data.colors || {};
    var cLow = new T.Color(GE.hex(n.color_low || pal.low, '#d8c690')), cMid = new T.Color(GE.hex(n.color_mid || pal.mid, '#5e9c4a')), cHigh = new T.Color(GE.hex(n.color_high || pal.high, '#8a7b6a')), cPeak = new T.Color(GE.hex(pal.peak, '#f2f2f2')), cWater = new T.Color(GE.hex(pal.shore, '#cdb87a'));
    var wl = N(data.water_level, 0.18), rnd = GE.rng(N(data.seed, 7)), tmp = new T.Color();
    for (var i = 0; i < pos.count; i++) {
      var h = (hm[i] || 0) / 255; pos.setY(i, h * hs); var t = h;
      if (t < wl + 0.03) tmp.copy(cWater).lerp(cLow, 0.4); else if (t < 0.45) tmp.copy(cLow).lerp(cMid, C((t - wl) / (0.45 - wl) * 1.3, 0, 1)); else if (t < 0.75) tmp.copy(cMid).lerp(cHigh, (t - 0.45) / 0.3); else tmp.copy(cHigh).lerp(cPeak, C((t - 0.75) / 0.2, 0, 1));
      var j = 0.93 + rnd() * 0.14; cols[i * 3] = tmp.r * j; cols[i * 3 + 1] = tmp.g * j; cols[i * 3 + 2] = tmp.b * j;
    }
    geo.setAttribute('color', new T.BufferAttribute(cols, 3)); geo.computeVertexNormals();
    var m = new T.Mesh(geo, new T.MeshStandardMaterial({ vertexColors: true, roughness: 1, metalness: 0, flatShading: data.flat === true })); m.receiveShadow = true; m.castShadow = false;
    var grp = new T.Group(); grp.add(m);
    if (wl > 0) { var w = new T.Mesh(new T.PlaneGeometry(size, size), new T.MeshStandardMaterial({ color: GE.hex(pal.water, '#2f7fbf'), transparent: true, opacity: 0.72, roughness: 0.2, metalness: 0.1 })); w.rotation.x = -Math.PI / 2; w.position.y = wl * hs + 0.02; grp.add(w); }
    R.terrains.push({ node: n, data: data, size: size, res: res, hs: hs, hm: hm, wl: wl });
    return grp;
  }
  R.terrainHeight = function (x, z) {
    var best = null; for (var i = 0; i < R.terrains.length; i++) {
      var t = R.terrains[i], u = (x / t.size + 0.5) * (t.res - 1), v = (z / t.size + 0.5) * (t.res - 1);
      if (u < 0 || v < 0 || u > t.res - 1 || v > t.res - 1) continue; var x0 = Math.floor(u), z0 = Math.floor(v), x1 = Math.min(t.res - 1, x0 + 1), z1 = Math.min(t.res - 1, z0 + 1), fx = u - x0, fz = v - z0;
      var g = function (a, b) { return (t.hm[b * t.res + a] || 0) / 255 * t.hs; };
      var h = (g(x0, z0) * (1 - fx) + g(x1, z0) * fx) * (1 - fz) + (g(x0, z1) * (1 - fx) + g(x1, z1) * fx) * fz; best = best == null ? h : Math.max(best, h);
    }
    return best;
  };
  R.groundAt = function (x, z, fromY) { // altura do chão: terreno ou topo de uma caixa sólida sob o ponto
    var h = R.terrainHeight(x, z); if (h == null) h = 0; var wl = R.terrains[0]; if (wl && R.settings.walk_on_water !== true) h = Math.max(h, wl.wl * wl.hs);
    for (var i = 0; i < R.solids.length; i++) { var b = R.solids[i].box; if (b && x > b.min.x && x < b.max.x && z > b.min.z && z < b.max.z && b.max.y <= fromY + 0.7) h = Math.max(h, b.max.y); }
    return h;
  };
  R.blockedXZ = function (x, z, y, r) {
    for (var i = 0; i < R.solids.length; i++) { var s = R.solids[i], b = s.box; if (!b || !s.alive) continue; if (y + 1.6 < b.min.y || y + 0.6 > b.max.y) continue; if (x + r > b.min.x && x - r < b.max.x && z + r > b.min.z && z - r < b.max.z) return true; }
    var t = R.terrains[0]; if (t) { var lim = t.size / 2 - 1; if (Math.abs(x) > lim || Math.abs(z) > lim) return true; }
    return false;
  };
  function refreshSolids() { R.solids = []; R.world.updateMatrixWorld(true); GE.walk(GE.root, function (n) { if (n.alive && n.solid && n.obj) { n.box = new T.Box3().setFromObject(n.obj); R.solids.push(n); } }); }

  // ------------------------------------------------------------------ objetos do mapa 3D
  var OBJ = {
    tree: function (o) { var s = N(o.s, 1) * (0.8 + (N(o.x, 0) * 13 % 7) / 14); return { type: 'Node3D', name: 'Árvore', sx: s, sy: s, sz: s, solid: true, children: [{ type: 'Mesh3D', shape: 'cylinder', w: 0.5, h: 2, y: 1, color: '#6b4a2b' }, { type: 'Mesh3D', shape: 'cone', w: 2.6, h: 3.2, y: 3.4, color: GE.shade(o.color || '#2f7a3a', (N(o.x, 0) % 5) / 25) }, { type: 'Mesh3D', shape: 'cone', w: 2, h: 2.4, y: 4.7, color: GE.shade(o.color || '#2f7a3a', 0.1) }] }; },
    rock: function (o) { var s = N(o.s, 1); return { type: 'Mesh3D', name: 'Pedra', shape: 'icosa', w: 1.8 * s, h: 1.8 * s, d: 1.8 * s, sy: 0.7, y: 0.6 * s, color: '#8a8d93', flat: true, solid: true }; },
    house: function (o) { var s = N(o.s, 1); return { type: 'Node3D', name: 'Casa', sx: s, sy: s, sz: s, solid: true, children: [{ type: 'Mesh3D', shape: 'box', w: 5, h: 3, d: 4, y: 1.5, color: '#d9c7a1' }, { type: 'Mesh3D', shape: 'cone', w: 6.6, h: 2.4, y: 4.2, ry: 45, color: '#a14b3a', sz: 0.8 }, { type: 'Mesh3D', shape: 'box', w: 0.9, h: 1.6, d: 0.1, y: 0.8, z: 2.02, color: '#5b3a22', solid: false }] }; },
    npc: function (o) { return { type: 'Humanoid3D', name: o.name || 'NPC', color: '#f4a261', tags: ['npc'], behaviors: [{ type: 'dialogue', id: o.dialogue || 'npc1', range: 3.2 }, { type: 'wander', radius: 2, speed: 0.6 }] }; },
    coin: function () { return { type: 'Mesh3D', name: 'Moeda', shape: 'torus', w: 0.7, h: 0.7, color: '#ffd23f', emissive: '#aa7a00', glow: 0.7, rx: 90, shadow: false, tags: ['item'], behaviors: [{ type: 'collectible', value: 10 }, { type: 'spin', speed: 140, axis: 'y' }, { type: 'float', amp: 0.18, speed: 3 }] }; },
    gem: function () { return { type: 'Mesh3D', name: 'Gema', shape: 'octa', w: 0.8, h: 0.8, color: '#4cc9f0', emissive: '#0a6a8a', glow: 0.9, shadow: false, tags: ['item'], behaviors: [{ type: 'collectible', value: 25 }, { type: 'spin', speed: 100, axis: 'y' }, { type: 'float', amp: 0.2, speed: 2.5 }] }; },
    enemy: function (o) { return { type: 'Mesh3D', name: 'Inimigo', shape: 'sphere', w: 1.1, h: 1.1, color: '#ef476f', tags: ['enemy'], behaviors: [{ type: 'enemy', hp: 1, damage: 1, score: 25 }, { type: 'patrol', range: N(o.range, 5), speed: 1.6 }] }; },
    chaser: function () { return { type: 'Mesh3D', name: 'Perseguidor', shape: 'icosa', w: 1.2, h: 1.2, color: '#d62828', emissive: '#550000', tags: ['enemy'], behaviors: [{ type: 'enemy', hp: 1, damage: 1, score: 40 }, { type: 'chase', speed: 2.6, range: 14 }] }; },
    goal: function () { return { type: 'Mesh3D', name: 'Objetivo', shape: 'torus', w: 3, h: 3, color: '#80ed99', emissive: '#1e8a3c', glow: 1, shadow: false, tags: ['goal'], behaviors: [{ type: 'goal' }, { type: 'float', amp: 0.2, speed: 2 }, { type: 'spin', speed: 40, axis: 'y' }], y: 1.6 }; },
    crate: function () { return { type: 'Mesh3D', name: 'Caixa', shape: 'box', w: 0.5, h: 0.5, d: 0.5, color: '#b08968', solid: false, tags: ['grab'], behaviors: [{ type: 'grab' }] }; },
    ball: function () { return { type: 'Mesh3D', name: 'Bola', shape: 'sphere', w: 0.3, h: 0.3, color: '#f77f00', tags: ['grab'], behaviors: [{ type: 'grab' }] }; },
    pillar: function () { return { type: 'Mesh3D', name: 'Pilar', shape: 'cylinder', w: 1, h: 5, y: 2.5, color: '#c9ced6', solid: true }; },
    portal: function () { return { type: 'Mesh3D', name: 'Portal', shape: 'torus', w: 2.6, h: 2.6, color: '#b388ff', emissive: '#5a2da8', glow: 1.2, shadow: false, tags: ['goal'], behaviors: [{ type: 'goal' }, { type: 'spin', speed: 60, axis: 'z' }], y: 1.8 }; },
  };
  GE.OBJ3D = OBJ;
  function spawnObjects(t) {
    var out = [];
    (t.data.objects || []).forEach(function (o) {
      var h = R.terrainHeight(N(o.x, 0), N(o.z, 0)); if (h == null) h = 0;
      if (o.type === 'player') { out.push({ type: 'Humanoid3D', name: 'Jogador', color: '#ffd166', tags: ['player'], x: N(o.x, 0), y: h + 0.05, z: N(o.z, 0), ry: N(o.ry, 0), behaviors: [{ type: R.kind === 'vr' ? 'player_vr' : (R.settings.camera === 'first' ? 'player_fps' : 'player_third') }] }); return; }
      var f = OBJ[o.type]; if (!f) return; var s = f(o); var off = N(s.y, 0); s.x = N(o.x, 0); s.z = N(o.z, 0); s.y = h + off + (o.type === 'coin' || o.type === 'gem' ? 0.9 : 0) + (o.type === 'rock' ? 0 : 0); s.ry = N(o.ry, N(s.ry, 0));
      if (o.type === 'goal') s.y = h + 1.6; if (o.props) for (var k in o.props) s[k] = o.props[k];
      s._baseY = s.y; out.push(s);
    });
    out.forEach(function (s) { t.node.children.push(GE.makeNode(s, t.node)); });
    // as crianças novas ainda não têm objetos three: constrói agora
    t.node.children.forEach(function (c) { if (!c.obj) build(c, t.node.obj || R.world); });
  }

  R.afterInit = function () {
    R.rig.position.set(0, 0, 0); var p = GE.byTag3('player')[0]; R.player = p || null;
    R.world.updateMatrixWorld(true); refreshSolids();
    if (p) { var gh = R.groundAt(p.x, p.z, p.y + 2); if (gh > p.y - 0.01) p.y = gh; R.yaw = GE.rad(N(p.ry, 0)); }
    if (R.kind === 'vr' || R.kind === 'ar') xrSetup();
    var cm = R.camNode; if (cm) { R.camMode = cm.mode || (R.settings.camera === 'first' ? 'first' : 'third'); R.camera.fov = N(cm.fov, 70); R.camera.updateProjectionMatrix(); } else R.camMode = R.settings.camera === 'first' ? 'first' : 'third';
    if (R.kind === 'vr' || R.kind === 'ar') R.camMode = 'first';
  };
  GE.byTag3 = GE.byTag;
  // ------------------------------------------------------------------ entrada de ponteiro / câmera
  R.pointerSetup = function () {
    if (R._ptr) return; R._ptr = true;
    GE.onPointer = function (kind, e) {
      if (GE.editing) return;
      if (kind === 'down' && GE.started && R.camMode && !R.xr.active && R.settings.pointer_lock !== false && !('ontouchstart' in window) && R.canvas.requestPointerLock && document.pointerLockElement !== R.canvas) { try { R.canvas.requestPointerLock(); } catch (x) { /* ok */ } }
      if (kind === 'move' && !R.xr.active && !GE.talking) {
        var locked = document.pointerLockElement === R.canvas, drag = GE.input.mouse.down && (e.pointerType === 'touch' || e.buttons);
        if (locked || drag) { var sens = locked ? 0.0024 : 0.005; R.yaw -= (e.movementX || 0) * sens; R.pitch = C(R.pitch - (e.movementY || 0) * sens, -1.35, 1.35); }
      }
    };
  };

  // ------------------------------------------------------------------ atualização / desenho
  R.update = function (dt) {
    if (!R.three) return;
    GE.walk(GE.root, function (n) { if (n.alive && n.obj) applyTransform(n); });
    var p = R.player;
    if (GE.editing) { R.editCamera(); return; }
    if (p && p.alive) {
      var cm = R.camMode, tx = p.x, ty = p.y, tz = p.z;
      if (R.xr.active) { R.rig.position.set(p.x, p.y, p.z); R.rig.rotation.y = R.yaw; }
      else if (cm === 'first') { R.camera.position.set(p.x, p.y + 1.62, p.z); R.camera.rotation.set(R.pitch, R.yaw, 0, 'YXZ'); R.rig.position.set(0, 0, 0); R.rig.rotation.set(0, 0, 0); if (p.obj) p.obj.visible = false; }
      else {
        var dist = N(R.camNode && R.camNode.distance, 6.5), hgt = N(R.camNode && R.camNode.height, 2), ox = Math.sin(R.yaw) * Math.cos(R.pitch * 0.6) * dist, oz = Math.cos(R.yaw) * Math.cos(R.pitch * 0.6) * dist, oy = hgt + Math.sin(R.pitch) * dist * 0.6 + 0.3;
        var cx = tx + ox, cz = tz + oz, cy = ty + oy, g = R.groundAt(cx, cz, cy + 5); if (cy < g + 0.5) cy = g + 0.5;
        R.rig.position.set(0, 0, 0); R.rig.rotation.set(0, 0, 0); var k = 1 - Math.pow(0.001, dt || 0.016); if (!R._cp) R._cp = new T.Vector3(cx, cy, cz); R._cp.x += (cx - R._cp.x) * k; R._cp.y += (cy - R._cp.y) * k; R._cp.z += (cz - R._cp.z) * k;
        R.camera.position.copy(R._cp); R.camera.lookAt(tx, ty + 1.4, tz); if (p.obj) p.obj.visible = true;
      }
    } else if (R.camNode && R.camNode.mode !== 'orbit') {
      var c = R.camNode; R.camera.position.set(N(c.x, 0), N(c.y, 5), N(c.z, 10)); if (c.target) { var tn = GE.find(c.target); if (tn) R.camera.lookAt(tn.x, tn.y, tn.z); else R.camera.lookAt(0, 0, 0); } else R.camera.rotation.set(GE.rad(N(c.rx, -15)), GE.rad(N(c.ry, 0)), 0, 'YXZ');
    } else if (!p) { R.orbit.yaw += dt * 0.15; R.orbitApply(); }
    if (R.settings.day_cycle) { /* reservado: ciclo de dia */ }
  };
  R.orbitApply = function () { var o = R.orbit, cp = Math.cos(o.pitch), x = o.tx + Math.sin(o.yaw) * cp * o.dist, z = o.tz + Math.cos(o.yaw) * cp * o.dist, y = o.ty + Math.sin(o.pitch) * o.dist; R.camera.position.set(x, y, z); R.camera.lookAt(o.tx, o.ty, o.tz); };
  R.render = function (dt) { if (R.renderer && R.three && !R.renderer.xr.isPresenting) { R.renderer.render(R.three, R.camera); } };
  R.editCamera = function () { R.orbitApply(); };

  // ------------------------------------------------------------------ WebXR (VR / AR)
  function xrSetup() {
    var mode = R.kind === 'ar' ? 'immersive-ar' : 'immersive-vr', btn = document.getElementById('ge-xr');
    var ok = !!(navigator.xr && navigator.xr.isSessionSupported);
    var mark = function (sup) {
      R.xr.supported = sup; if (!btn) return; btn.classList.remove('ge-hidden'); btn.textContent = GE.tr(R.kind === 'ar' ? 'Entrar em AR' : 'Entrar em VR');
      btn.disabled = !sup; btn.title = sup ? '' : GE.tr('VR/AR indisponível neste navegador: prévia no computador.'); btn.onclick = function () { xrStart(mode); };
    };
    if (ok) navigator.xr.isSessionSupported(mode).then(mark).catch(function () { mark(false); }); else mark(false);
    // controles (ponteiros) para pegar/teleportar
    R.ctrl = [0, 1].map(function (i) {
      var c = R.renderer.xr.getController(i); var ray = new T.Mesh(new T.CylinderGeometry(0.004, 0.004, 3, 6), new T.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.5 })); ray.rotation.x = Math.PI / 2; ray.position.z = -1.5; c.add(ray);
      var tip = new T.Mesh(new T.SphereGeometry(0.02, 8, 6), new T.MeshBasicMaterial({ color: 0xffffff })); c.add(tip); R.rig.add(c);
      c.addEventListener('selectstart', function () { xrSelect(c); }); c.addEventListener('squeezestart', function () { xrGrab(c, true); }); c.addEventListener('squeezeend', function () { xrGrab(c, false); }); c.userData.i = i; return c;
    });
    R.reticle = new T.Mesh(new T.RingGeometry(0.12, 0.16, 32).rotateX(-Math.PI / 2), new T.MeshBasicMaterial({ color: 0xffffff })); R.reticle.matrixAutoUpdate = false; R.reticle.visible = false; R.three.add(R.reticle);
    if (R.kind === 'ar' || R.kind === 'vr') { var floor = new T.GridHelper(40, 40, 0x88aaff, 0x335577); floor.material.transparent = true; floor.material.opacity = R.kind === 'ar' ? 0.35 : 0.2; floor.position.y = 0.01; R.three.add(floor); }
    if (R.kind === 'ar') R.three.background = null;
  }
  function xrStart(mode) {
    if (!navigator.xr) return;
    var opts = mode === 'immersive-ar' ? { requiredFeatures: ['hit-test'], optionalFeatures: ['local-floor', 'dom-overlay'], domOverlay: { root: document.getElementById('ge-hud') || document.body } } : { optionalFeatures: ['local-floor', 'bounded-floor', 'hand-tracking'] };
    navigator.xr.requestSession(mode, opts).then(function (session) {
      R.xr.active = true; R.xr.mode = mode; R.renderer.xr.setReferenceSpaceType('local-floor'); R.renderer.xr.setSession(session);
      if (mode === 'immersive-ar') { R.three.background = null; R.renderer.setClearAlpha(0); session.requestReferenceSpace('viewer').then(function (vs) { session.requestHitTestSource({ space: vs }).then(function (src) { R.hitSource = src; }); }); }
      GE.xrLoop = true; GE.stop(); R.renderer.setAnimationLoop(function (ts) { GE.tick(ts); xrFrame(); R.renderer.render(R.three, R.camera); });
      session.addEventListener('end', function () { R.xr.active = false; R.hitSource = null; R.renderer.setAnimationLoop(null); GE.xrLoop = false; GE.start(); R.resize(); if (R.reticle) R.reticle.visible = false; });
    }).catch(function (e) { GE.toast(String(e && e.message || e)); });
  }
  function xrFrame() {
    var fr = R.renderer.xr.getFrame && R.renderer.xr.getFrame();
    if (R.hitSource && fr) { var hits = fr.getHitTestResults(R.hitSource), ref = R.renderer.xr.getReferenceSpace(); if (hits.length && ref) { var pose = hits[0].getPose(ref); if (pose) { R.reticle.visible = true; R.reticle.matrix.fromArray(pose.transform.matrix); } } else R.reticle.visible = false; }
    // locomoção suave pelo analógico (VR)
    var s = R.renderer.xr.getSession(); if (s && R.kind === 'vr' && R.player) {
      s.inputSources.forEach(function (src) { var gp = src.gamepad; if (!gp || !gp.axes || gp.axes.length < 4) return; var ax = gp.axes[2], ay = gp.axes[3]; if (Math.abs(ax) + Math.abs(ay) < 0.2) return;
        var yaw = R.rig.rotation.y + (R.camera.rotation.y || 0), sp = 2.6 * (1 / 60); R.player.x += (Math.sin(yaw) * ay + Math.cos(yaw) * ax) * sp; R.player.z += (Math.cos(yaw) * ay - Math.sin(yaw) * ax) * sp; });
    }
  }
  var ray = null;
  function ctrlRay(c) { if (!ray) ray = new T.Raycaster(); var m = new T.Matrix4().extractRotation(c.matrixWorld); ray.ray.origin.setFromMatrixPosition(c.matrixWorld); ray.ray.direction.set(0, 0, -1).applyMatrix4(m); return ray; }
  function xrSelect(c) {
    if (R.kind === 'ar') { if (R.reticle.visible) { var pos = new T.Vector3().setFromMatrixPosition(R.reticle.matrix); R.placeAt(pos.x, pos.y, pos.z); } return; }
    var r = ctrlRay(c), t = r.ray.origin.y > 0 && r.ray.direction.y < -0.05 ? -r.ray.origin.y / r.ray.direction.y : -1;   // teletransporte: onde o raio encontra o chão
    if (t > 0 && t < 30 && R.player) { R.player.x += r.ray.origin.x + r.ray.direction.x * t - (R.rig.position.x + R.camera.position.x); R.player.z += r.ray.origin.z + r.ray.direction.z * t - (R.rig.position.z + R.camera.position.z); GE.sfx('select'); }
  }
  function xrGrab(c, on) {
    if (on) { var best = null, bd = 0.5, p = new T.Vector3().setFromMatrixPosition(c.matrixWorld); GE.byTag3('grab').forEach(function (n) { if (!n.obj) return; var q = new T.Vector3().setFromMatrixPosition(n.obj.matrixWorld), d = p.distanceTo(q); if (d < bd) { bd = d; best = n; } }); if (best) { c.attach(best.obj); c.userData.held = best; GE.sfx('select'); } }
    else if (c.userData.held) { var h = c.userData.held; R.world.attach(h.obj); h.x = h.obj.position.x; h.y = h.obj.position.y; h.z = h.obj.position.z; h.vy = 0; h.thrown = true; c.userData.held = null; GE.sfx('place'); }
  }
  // AR: coloca uma cópia do primeiro nó com o comportamento place_on_tap
  R.placeAt = function (x, y, z) {
    var tpl = GE.byBehavior('place_on_tap')[0]; if (!tpl) { return; }
    var spec = JSON.parse(JSON.stringify(tpl.spec)); spec.x = x; spec.y = y; spec.z = z; spec.visible = true; spec.behaviors = (spec.behaviors || []).filter(function (b) { return b.type !== 'place_on_tap'; });
    var n = GE.add(GE.root, spec); n.placed = true; GE.sfx('place'); GE.state.score += 5;
  };
  // pega objetos com o mouse na prévia (clique segura o objeto na frente da câmera)
  R.pickCenter = function () { var rc = new T.Raycaster(); rc.setFromCamera(new T.Vector2(0, 0), R.camera); var objs = []; GE.byTag3('grab').forEach(function (n) { if (n.obj) objs.push(n.obj); }); var h = rc.intersectObjects(objs, true); if (!h.length || h[0].distance > 4) return null; var o = h[0].object; while (o && !o.userData.nodeId) o = o.parent; return o ? GE.byTag3('grab').filter(function (n) { return n.obj === o; })[0] : null; };

  // ------------------------------------------------------------------ edição (clicar/arrastar)
  R.pick = function (sx, sy) {
    var rc = new T.Raycaster(), v = new T.Vector2((sx / R.w) * 2 - 1, -(sy / R.h) * 2 + 1); rc.setFromCamera(v, R.camera);
    var h = rc.intersectObjects(R.world.children, true); for (var i = 0; i < h.length; i++) { var o = h[i].object; if (o.geometry && o.geometry.type === 'PlaneGeometry' && o.parent && o.parent.userData.nodeId) { /* chão/água: só seleciona se for o único */ } while (o && !o.userData.nodeId) o = o.parent; if (!o) continue; var id = o.userData.nodeId, nn = null; GE.walk(GE.root, function (x) { if (x.id === id) nn = x; }); if (nn && nn.type !== 'Terrain3D' && nn.type !== 'Water3D') return nn; }
    return null;
  };
  R.groundPoint = function (sx, sy) {
    var rc = new T.Raycaster(), v = new T.Vector2((sx / R.w) * 2 - 1, -(sy / R.h) * 2 + 1); rc.setFromCamera(v, R.camera);
    var meshes = []; R.terrains.forEach(function (t) { if (t.node.obj) meshes.push(t.node.obj); }); var h = meshes.length ? rc.intersectObjects(meshes, true) : [];
    if (h.length) return h[0].point; var pl = new T.Plane(new T.Vector3(0, 1, 0), 0), out = new T.Vector3(); return rc.ray.intersectPlane(pl, out) ? out : null;
  };

  // ------------------------------------------------------------------ comportamentos 3D
  var B = GE.behavior, ctrlDown = false;
  function moveXZ(n, dx, dz, r) {
    var nx = n.x + dx, nz = n.z + dz;
    if (!R.blockedXZ(nx, n.z, n.y, r)) n.x = nx; if (!R.blockedXZ(n.x, nz, n.y, r)) n.z = nz;
  }
  function walkAnim(n, moving, dt) {
    if (!n.obj || !n.obj.legs) return; n._ph = (n._ph || 0) + (moving ? dt * 9 : 0); var a = moving ? Math.sin(n._ph) * 0.7 : 0;
    n.obj.legs[0].rotation.x = a; n.obj.legs[1].rotation.x = -a; if (n.obj.arms) { n.obj.arms[0].rotation.x = -a * 0.8; n.obj.arms[1].rotation.x = a * 0.8; }
  }
  function playerCommon(n, dt, p, s, third) {
    var sp = N(p.speed, 5) * (GE.input.down('run') ? 1.7 : 1), ax = GE.input.axis('left', 'right'), az = GE.input.axis('up', 'down'), l = Math.sqrt(ax * ax + az * az) || 1;
    var yaw = R.yaw, fx = -Math.sin(yaw), fz = -Math.cos(yaw), rx = Math.cos(yaw), rz = -Math.sin(yaw);
    var dx = (rx * ax - fx * az) / l * sp * dt, dz = (rz * ax - fz * az) / l * sp * dt;
    if (ax || az) { moveXZ(n, dx, dz, 0.4); if (third) { var want = Math.atan2(dx, dz), cur = n.ry ? GE.rad(n.ry) : 0, diff = Math.atan2(Math.sin(want - cur), Math.cos(want - cur)); n.ry = (cur + diff * Math.min(1, dt * 12)) * 180 / Math.PI; } }
    if (!third) n.ry = yaw * 180 / Math.PI;
    var gh = R.groundAt(n.x, n.z, n.y); s.vy = (s.vy || 0) - 24 * dt; n.y += s.vy * dt;
    if (n.y <= gh) { n.y = gh; s.vy = 0; s.ground = true; } else if (n.y - gh > 0.1) s.ground = false;
    if (GE.input.hit('jump') && s.ground) { s.vy = N(p.jump, 8); s.ground = false; GE.sfx('jump'); }
    walkAnim(n, !!(ax || az) && s.ground, dt);
    if (n.y < -30) { n.y = gh + 2; }
  }
  B('player_third', { init: function (n) { n.tags = n.tags.indexOf('player') < 0 ? n.tags.concat('player') : n.tags; }, update: function (n, dt, p, s) { playerCommon(n, dt, p, s, true); } });
  B('player_fps', { init: function (n) { n.tags = n.tags.indexOf('player') < 0 ? n.tags.concat('player') : n.tags; }, update: function (n, dt, p, s) {
    playerCommon(n, dt, p, s, false);
    if (GE.input.hit('action') || GE.input.mouse.hit) { if (s.held) { s.held.thrown = true; s.held = null; } else { var g = R.pickCenter(); if (g) s.held = g; } }
    if (s.held && s.held.alive) { var f = new T.Vector3(); R.camera.getWorldDirection(f); s.held.x = n.x + f.x * 1.4; s.held.y = n.y + 1.3 + f.y * 1.4; s.held.z = n.z + f.z * 1.4; s.held.vy = 0; }
  } });
  B('player_vr', { init: function (n) { n.tags = n.tags.indexOf('player') < 0 ? n.tags.concat('player') : n.tags; }, update: function (n, dt, p, s) {
    if (R.xr.active) { var gh = R.groundAt(n.x, n.z, n.y); n.y = gh; return; }   // em VR o chão é fixo e o analógico move o jogador (xrFrame)
    playerCommon(n, dt, p, s, false);
    if (GE.input.hit('action') || GE.input.mouse.hit) { if (s.held) { s.held.thrown = true; s.held = null; } else { var g = R.pickCenter(); if (g) { s.held = g; GE.sfx('select'); } } }
    if (s.held && s.held.alive) { var f = new T.Vector3(); R.camera.getWorldDirection(f); s.held.x = n.x + f.x * 1.1; s.held.y = n.y + 1.3 + f.y * 1.1; s.held.z = n.z + f.z * 1.1; s.held.vy = 0; }
  } });
  B('grab', { init: function (n, p, s) { n.vy = 0; s.home = { x: n.x, y: n.y, z: n.z }; }, update: function (n, dt) {
    if (!n.thrown) return; n.vy -= 9.8 * dt; n.y += n.vy * dt; var gh = R.groundAt(n.x, n.z, n.y + 0.5) + N(n.h, 0.5) / 2; if (n.y <= gh) { n.y = gh; n.vy = Math.abs(n.vy) > 1.5 ? -n.vy * 0.35 : 0; if (n.vy === 0) n.thrown = false; }
  } });
  B('place_on_tap', { init: function (n) { n.visible = false; } });
  B('wander', { init: function (n, p, s) { s.ox = n.x; s.oz = n.z; s.t = 0; s.dx = 0; s.dz = 0; }, update: function (n, dt, p, s) {
    s.t -= dt; var r = N(p.radius, 4); if (s.t <= 0) { s.t = 1.2 + Math.random() * 2.5; var a = Math.random() * 6.28; s.dx = Math.cos(a); s.dz = Math.sin(a); if (Math.random() < 0.35) s.dx = s.dz = 0; }
    var sp = N(p.speed, 1) * dt; if (Math.abs(n.x + s.dx * sp - s.ox) > r || Math.abs(n.z + s.dz * sp - s.oz) > r) { s.dx = -s.dx; s.dz = -s.dz; } moveXZ(n, s.dx * sp, s.dz * sp, 0.35);
    n.y = R.groundAt(n.x, n.z, n.y + 1) + (n._off || 0); if (s.dx || s.dz) n.ry = Math.atan2(s.dx, s.dz) * 180 / Math.PI; walkAnim(n, !!(s.dx || s.dz), dt);
  } });
  B('patrol', { init: function (n, p, s) { s.ox = n.x; s.oz = n.z; s.d = 1; s.off = n.y - (R.terrainHeight(n.x, n.z) || 0); }, update: function (n, dt, p, s) {
    var r = N(p.range, 5), sp = N(p.speed, 1.5) * dt; if (p.axis === 'z') { n.z += s.d * sp; if (Math.abs(n.z - s.oz) > r) s.d = -s.d; } else { n.x += s.d * sp; if (Math.abs(n.x - s.ox) > r) s.d = -s.d; }
    n.y = R.groundAt(n.x, n.z, n.y + 1) + s.off; n.ry = s.d > 0 ? 90 : -90;
  } });
  B('chase', { init: function (n, p, s) { s.off = n.y - (R.terrainHeight(n.x, n.z) || 0); }, update: function (n, dt, p, s) {
    var pl = R.player; if (!pl) return; var dx = pl.x - n.x, dz = pl.z - n.z, d = Math.sqrt(dx * dx + dz * dz); if (d > N(p.range, 14) || d < 0.8) return; var sp = N(p.speed, 2.6) * dt; moveXZ(n, dx / d * sp, dz / d * sp, 0.4); n.y = R.groundAt(n.x, n.z, n.y + 1) + s.off; n.ry = Math.atan2(dx, dz) * 180 / Math.PI;
  } });
  B('spin', { update: function (n, dt, p) { var k = (p.axis === 'x' ? 'rx' : p.axis === 'z' ? 'rz' : 'ry'); n[k] = (N(n[k], 0) + N(p.speed, 90) * dt) % 360; } });
  B('float', { init: function (n, p, s) { s.y0 = n.y; }, update: function (n, dt, p, s) { n.y = s.y0 + Math.sin(GE.state.time * N(p.speed, 2) + (n.x || 0)) * N(p.amp, 0.2); } });
  B('collectible', { update: function (n, dt, p) { var pl = R.player; if (!pl || !n.alive) return; var near = R.xr.active ? R.camera.getWorldPosition(new T.Vector3()).distanceTo(new T.Vector3(n.x, n.y, n.z)) < 1.1 : GE.dist(pl, { x: n.x, y: n.y - 1, z: n.z }) < 1.5; if (!near) return; GE.remove(n); GE.state.coins++; GE.addScore(N(p.value, 10)); GE.sfx('coin'); if (GE.state.total && GE.state.coins >= GE.state.total && (R.scene3.rules || {}).win === 'collect_all') GE.win(); } });
  B('health_pickup', { update: function (n, dt, p) { var pl = R.player; if (pl && n.alive && GE.dist(pl, n) < 1.4) { GE.remove(n); GE.heal(N(p.amount, 1)); } } });
  B('hazard', { update: function (n, dt, p) { var pl = R.player; if (pl && GE.dist(pl, n) < 1.3) GE.damage(N(p.damage, 1), n); } });
  B('enemy', { init: function (n, p, s) { s.hp = N(p.hp, 1); n.tags = n.tags.indexOf('enemy') < 0 ? n.tags.concat('enemy') : n.tags; }, update: function (n, dt, p, s) {
    var pl = R.player; if (!pl || !n.alive) return; if (GE.dist(pl, n) > 1.2) return;
    if (pl.y > n.y + 0.55 && (pl.vy || 0) < 0) { GE.remove(n); GE.addScore(N(p.score, 25)); GE.sfx('hit'); return; }
    GE.damage(N(p.damage, 1), n);
  } });
  B('goal', { update: function (n, dt, p) { var pl = R.player; if (!pl) return; if (GE.dist(pl, n) > 2) return; var rules = R.scene3.rules || {}; if (rules.win === 'collect_all' && GE.state.coins < GE.state.total) { if (!n._w || GE.state.time - n._w > 2) { n._w = GE.state.time; GE.toast(GE.tr('Pegue tudo!')); } return; } GE.sfx('win'); if (p.next) GE.nextScene(p.next); else GE.nextScene(); } });
  B('dialogue', { update: function (n, dt, p, s) {
    var pl = R.player; if (!pl || GE.talking) return; var near = GE.dist(pl, n) < N(p.range, 3);
    if (near && !n._hint) { n._hint = true; GE.toast(GE.tr('E: falar'), 900); } if (!near) n._hint = false;
    if (near && GE.input.hit('action')) { var lines = ((window.GE_DATA || {}).dialogues || {})[p.id || n.name] || [{ speaker: n.name, text: '...' }]; GE.say(lines); if (document.pointerLockElement) document.exitPointerLock(); }
  } });
  B('teleport_pad', { update: function (n, dt, p) { var pl = R.player; if (pl && GE.dist(pl, n) < 1.2) { pl.x = N(p.to_x, 0); pl.z = N(p.to_z, 0); pl.y = R.groundAt(pl.x, pl.z, 99); GE.sfx('door'); } } });
  B('audio_loop', { init: function (n, p) { if (p.sound) setTimeout(function () { GE.playSound(p.sound, { loop: true, volume: N(p.volume, 0.6) }); }, 50); } });
  B('follow', { update: function (n, dt, p) { var t = GE.find(p.target || 'Jogador'); if (!t) return; var dx = t.x - n.x, dz = t.z - n.z, d = Math.sqrt(dx * dx + dz * dz); if (d > N(p.gap, 2)) { var sp = N(p.speed, 2) * dt; moveXZ(n, dx / d * sp, dz / d * sp, 0.3); n.y = R.groundAt(n.x, n.z, n.y + 1); } } });
})();
