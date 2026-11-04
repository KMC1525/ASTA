/* ASTA runtime — atores: humanoides procedurais, jogador e NPCs. */
(function () {
  'use strict';
  const RT = window.RT;
  const T = window.THREE;
  const { clamp, lerp, angleDiff } = RT;

  const matCache = {};
  function mat(hex, opts) {
    const k = hex + JSON.stringify(opts || {});
    if (!matCache[k]) matCache[k] = new T.MeshStandardMaterial(Object.assign({ color: RT.hex(hex), roughness: 0.85, metalness: 0 }, opts || {}));
    return matCache[k];
  }
  const defaults = { skin: '#c68a63', hair: '#2b1b12', hair_style: 'short', top: '#3b5b7a', bottom: '#2a2a30', height: 1.72, build: 1, accessory: 'none' };

  // ---------------------------------------------------------------- humanoide
  RT.makeHumanoid = function (appearance, opts) {
    const ap = Object.assign({}, defaults, appearance || {});
    opts = opts || {};
    const s = ap.height / 1.72, b = ap.build;
    const root = new T.Group(), body = new T.Group();
    root.add(body);
    const part = (geo, m, x, y, z) => { const o = new T.Mesh(geo, m); o.position.set(x, y, z); o.castShadow = true; o.receiveShadow = true; return o; };
    const pivot = (x, y) => { const g = new T.Group(); g.position.set(x, y, 0); return g; };
    const skin = mat(ap.skin), topM = mat(ap.top), botM = mat(ap.bottom), hairM = mat(ap.hair, { roughness: 0.7 });

    const legL = pivot(-0.085 * b * s, 0.9 * s), legR = pivot(0.085 * b * s, 0.9 * s);
    [legL, legR].forEach((l) => {
      l.add(part(new T.CapsuleGeometry(0.075 * b * s, 0.75 * s, 3, 8), botM, 0, -0.45 * s, 0));
      l.add(part(new T.BoxGeometry(0.13 * b * s, 0.07 * s, 0.24 * s), mat('#1c1a1a'), 0, -0.88 * s, 0.04 * s));
      body.add(l);
    });
    body.add(part(new T.BoxGeometry(0.31 * b * s, 0.16 * s, 0.2 * s), botM, 0, 0.93 * s, 0));
    const torso = part(new T.CapsuleGeometry(0.15 * b * s, 0.36 * s, 4, 10), topM, 0, 1.2 * s, 0);
    torso.scale.z = 0.7; body.add(torso);
    const head = new T.Group(); head.position.set(0, 1.62 * s, 0); body.add(head);
    head.add(part(new T.SphereGeometry(0.11 * s, 16, 12), skin, 0, 0, 0));
    head.add(part(new T.CylinderGeometry(0.045 * s, 0.05 * s, 0.1 * s, 8), skin, 0, -0.1 * s, 0));
    const eyeM = mat('#15110f');
    [-1, 1].forEach((sx) => head.add(part(new T.SphereGeometry(0.014 * s, 6, 6), eyeM, sx * 0.037 * s, 0.01 * s, 0.1 * s)));
    head.add(part(new T.BoxGeometry(0.03 * s, 0.04 * s, 0.03 * s), skin, 0, -0.015 * s, 0.108 * s));
    if (ap.hair_style !== 'bald') {
      const cap = part(new T.SphereGeometry(0.118 * s, 14, 10, 0, Math.PI * 2, 0, 1.75), hairM, 0, 0.012 * s, -0.008 * s);
      head.add(cap);
      if (ap.hair_style === 'long') head.add(part(new T.BoxGeometry(0.21 * s, 0.36 * s, 0.07 * s), hairM, 0, -0.14 * s, -0.085 * s));
      if (ap.hair_style === 'bun') head.add(part(new T.SphereGeometry(0.055 * s, 8, 8), hairM, 0, 0.13 * s, -0.07 * s));
    }
    if (ap.accessory === 'hat') {
      head.add(part(new T.CylinderGeometry(0.19 * s, 0.19 * s, 0.015 * s, 14), mat(ap.bottom), 0, 0.085 * s, 0));
      head.add(part(new T.CylinderGeometry(0.1 * s, 0.12 * s, 0.12 * s, 12), mat(ap.bottom), 0, 0.15 * s, 0));
    }
    if (ap.accessory === 'backpack') body.add(part(new T.BoxGeometry(0.26 * s, 0.34 * s, 0.14 * s), mat('#6b4a2b'), 0, 1.22 * s, -0.17 * s));
    let cape = null;
    if (ap.accessory === 'cape') {
      cape = new T.Group(); cape.position.set(0, 1.46 * s, -0.12 * s);
      const c = part(new T.PlaneGeometry(0.4 * b * s, 0.85 * s), mat(ap.bottom, { side: T.DoubleSide }), 0, -0.42 * s, 0); cape.add(c); body.add(cape);
    }
    const mkArm = (sx) => {
      const a = pivot(sx * (0.15 * b + 0.07) * s, 1.45 * s);
      a.add(part(new T.CapsuleGeometry(0.05 * b * s, 0.42 * s, 3, 8), topM, 0, -0.26 * s, 0));
      a.add(part(new T.SphereGeometry(0.052 * s, 8, 8), skin, 0, -0.56 * s, 0));
      body.add(a); return a;
    };
    const armL = mkArm(-1), armR = mkArm(1);
    if (opts.blob) {
      const blob = new T.Mesh(new T.CircleGeometry(0.42 * s, 14), new T.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.28, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 }));
      blob.rotation.x = -Math.PI / 2; blob.position.y = 0.03; root.add(blob); root.userData.blob = blob;
    }
    const h = { root, body, head, torso, legL, legR, armL, armR, cape, height: ap.height, s: s, emote: null, emoteT: 0, phase: 0, t: Math.random() * 10 };
    h.play = function (name) {
      const dur = { wave: 2.4, nod: 1.3, dance: 6, point: 2 }[name];
      if (dur) { h.emote = name; h.emoteT = 0; h.emoteDur = dur; }
    };
    h.update = function (dt, speed, airborne) {
      h.t += dt;
      const moving = speed > 0.1;
      if (moving) h.phase += dt * (3.4 + speed * 1.5);
      const amp = Math.min(1, speed / 3.2) * 0.85, sw = Math.sin(h.phase) * amp;
      legL.rotation.x = airborne ? 0.5 : sw; legR.rotation.x = airborne ? -0.3 : -sw;
      armL.rotation.x = -sw * 0.9; armR.rotation.x = sw * 0.9;
      armL.rotation.z = armR.rotation.z = 0; head.rotation.set(0, 0, 0); body.rotation.y = 0;
      body.position.y = moving ? Math.abs(Math.sin(h.phase)) * 0.045 * Math.min(1, speed / 3) * s : 0;
      torso.scale.y = 1 + (moving ? 0 : Math.sin(h.t * 1.9) * 0.012);
      if (cape) cape.rotation.x = 0.1 + Math.min(1, speed / 4) * 0.5 + Math.sin(h.t * 3) * 0.04;
      if (h.emote) {
        h.emoteT += dt;
        const e = h.emoteT;
        if (h.emote === 'wave') { armR.rotation.x = 0; armR.rotation.z = 2.5 + Math.sin(e * 10) * 0.28; head.rotation.z = 0.05; }
        else if (h.emote === 'nod') head.rotation.x = Math.sin(e * 7) * 0.28;
        else if (h.emote === 'point') { armR.rotation.x = -1.5; armR.rotation.z = 0; }
        else if (h.emote === 'dance') {
          body.position.y = Math.abs(Math.sin(e * 6)) * 0.09 * s; body.rotation.y = Math.sin(e * 3) * 0.5;
          armL.rotation.x = 0; armR.rotation.x = 0; armL.rotation.z = -2.2 + Math.sin(e * 6) * 0.5; armR.rotation.z = 2.2 + Math.cos(e * 6) * 0.5;
          legL.rotation.x = Math.sin(e * 6) * 0.4; legR.rotation.x = -Math.sin(e * 6) * 0.4;
        }
        if (e > h.emoteDur) h.emote = null;
      }
    };
    return h;
  };

  // ---------------------------------------------------------------- jogador
  RT.Player = function (world, spec, card, camera, canvas) {
    const self = this;
    this.world = world;
    this.camera = camera;
    this.canvas = canvas;
    const ps = spec.player || {};
    const ap = (card && card.appearance) || ps.appearance || {};
    this.card = card;
    this.name = (card && card.name) || 'Você';
    this.model = RT.makeHumanoid(ap, { blob: world.budget.shadow === 0 });
    world.scene.add(this.model.root);
    this.x = ps.x || 0; this.z = ps.z || 0;
    this.y = world.heightAt(this.x, this.z);
    this.vy = 0; this.onGround = true;
    this.yaw = ((ps.yaw || 0) * Math.PI) / 180; // direção do corpo
    this.camYaw = this.yaw; this.camPitch = -0.12;
    this.camDist = 4.4;
    this.perspective = spec.perspective || 'third';
    this.speed = 0;
    this.keys = {};
    this.touch = { x: 0, y: 0 };
    this.enabled = true;
    this.locked = false;
    this.sens = 0.0022;
    this.eye = 1.62 * (ap.height || 1.72) / 1.72;
    this.camPos = new T.Vector3();
    this._camInit = false;
    this.stepAcc = 0;
    this.onStep = null; this.onJump = null;

    const kd = (e) => {
      if (!self.enabled || e.target.matches && e.target.matches('input,textarea,select')) return;
      const k = e.code;
      self.keys[k] = true;
      if (k === 'Space' || k.startsWith('Arrow')) e.preventDefault();
      if (k === 'Space') self.jump();
      if (k === 'KeyV') self.togglePerspective();
    };
    const ku = (e) => { self.keys[e.code] = false; };
    window.addEventListener('keydown', kd);
    window.addEventListener('keyup', ku);
    window.addEventListener('blur', () => { self.keys = {}; });
    document.addEventListener('mousemove', (e) => {
      if (!self.locked || !self.enabled) return;
      if (self.skipMoves > 0) { self.skipMoves--; return; } // 1º evento após o lock traz um salto enorme
      const dx = e.movementX || 0, dy = e.movementY || 0;
      if (Math.abs(dx) > 220 || Math.abs(dy) > 220) return;
      self.look(dx, dy);
    });
    document.addEventListener('pointerlockchange', () => { self.locked = document.pointerLockElement === canvas; self.skipMoves = 3; if (self.onLockChange) self.onLockChange(self.locked); });
    canvas.addEventListener('wheel', (e) => { if (self.perspective === 'third') { self.camDist = clamp(self.camDist + e.deltaY * 0.004, 2, 9); } }, { passive: true });
  };
  const P = RT.Player.prototype;
  P.look = function (dx, dy) {
    this.camYaw -= dx * this.sens;
    this.camPitch = clamp(this.camPitch - dy * this.sens, -1.25, 1.2);
  };
  P.togglePerspective = function () { this.perspective = this.perspective === 'first' ? 'third' : 'first'; this._camInit = false; if (this.onPerspective) this.onPerspective(this.perspective); };
  P.jump = function () { if (this.onGround && this.enabled) { this.vy = 5.4; this.onGround = false; if (this.onJump) this.onJump(); } };
  P.requestLock = function () { if (this.canvas.requestPointerLock) { try { const r = this.canvas.requestPointerLock(); if (r && r.catch) r.catch(() => {}); } catch (e) { /* ignorado */ } } };
  P.releaseLock = function () { if (document.pointerLockElement) document.exitPointerLock(); };

  P.update = function (dt, npcs) {
    const k = this.keys, w = this.world;
    let fx = (k.KeyW || k.ArrowUp ? 1 : 0) - (k.KeyS || k.ArrowDown ? 1 : 0) + (-this.touch.y);
    let fs = (k.KeyD || k.ArrowRight ? 1 : 0) - (k.KeyA || k.ArrowLeft ? 1 : 0) + this.touch.x;
    if (!this.enabled) { fx = fs = 0; }
    const len = Math.hypot(fx, fs);
    if (len > 1) { fx /= len; fs /= len; }
    const run = !!(k.ShiftLeft || k.ShiftRight) || Math.hypot(this.touch.x, this.touch.y) > 0.9;
    const base = this.perspective === 'first' ? this.camYaw : this.camYaw;
    const sinY = Math.sin(base), cosY = Math.cos(base);
    const dirx = sinY * fx - cosY * fs, dirz = cosY * fx + sinY * fs; // frente=(sin,cos); direita=(-cos,sin)
    let sp = (run ? 6.2 : 3.1) * (fx < 0 ? 0.7 : 1);
    const depth = w.waterY - this.y;
    if (depth > 0.25) sp *= 0.6;
    const mag = Math.min(1, len);
    let nx = this.x + dirx * sp * dt * mag, nz = this.z + dirz * sp * dt * mag;
    const lim = w.half - 5;
    nx = clamp(nx, -lim, lim); nz = clamp(nz, -lim, lim);
    // terreno: bloqueia degraus íngremes e água funda
    const tryMove = (tx, tz) => {
      const g = w.heightAt(tx, tz);
      if (g - this.y > 0.75 && this.onGround) return false;
      if (g < w.waterY - 1.25) return false;
      return true;
    };
    if (mag > 0) {
      if (!tryMove(nx, nz)) {
        if (tryMove(nx, this.z)) nz = this.z; else if (tryMove(this.x, nz)) nx = this.x; else { nx = this.x; nz = this.z; }
      }
      const c = w.collide(nx, nz, 0.36);
      nx = c.x; nz = c.z;
      if (npcs) for (let i = 0; i < npcs.length; i++) {
        const n = npcs[i], dx = nx - n.x, dz = nz - n.z, d = Math.hypot(dx, dz);
        if (d < 0.7 && d > 1e-4) { nx = n.x + (dx / d) * 0.7; nz = n.z + (dz / d) * 0.7; }
      }
    }
    const moved = Math.hypot(nx - this.x, nz - this.z);
    this.speed = dt > 0 ? moved / dt : 0;
    this.x = nx; this.z = nz;
    // vertical
    const ground = w.heightAt(this.x, this.z);
    this.vy -= 16 * dt;
    this.y += this.vy * dt;
    if (this.y <= ground) {
      if (!this.onGround && this.vy < -3 && this.onLand) this.onLand();
      this.y = ground; this.vy = 0; this.onGround = true;
    } else if (this.y > ground + 0.08) this.onGround = false;
    // direção do corpo
    if (this.perspective === 'first') this.yaw = this.camYaw;
    else if (mag > 0.05) {
      const want = Math.atan2(dirx, dirz);
      this.yaw += angleDiff(this.yaw, want) * Math.min(1, dt * 10);
    }
    // passos
    if (this.onGround && this.speed > 0.5) {
      this.stepAcc += this.speed * dt;
      if (this.stepAcc > (run ? 1.7 : 1.25)) { this.stepAcc = 0; if (this.onStep) this.onStep(run); }
    }
    // modelo
    const m = this.model;
    m.root.position.set(this.x, this.y, this.z);
    m.root.rotation.y = this.yaw;
    m.root.visible = this.perspective === 'third';
    m.update(dt, this.speed, !this.onGround);
    this._camera(dt);
  };

  P._camera = function (dt) {
    const cam = this.camera, w = this.world;
    if (this.perspective === 'first') {
      cam.position.set(this.x, this.y + this.eye, this.z);
      cam.rotation.set(this.camPitch, this.camYaw + Math.PI, 0, 'YXZ');
      cam.fov = 72;
    } else {
      const piv = new T.Vector3(this.x, this.y + this.eye * 0.95, this.z);
      const cp = Math.cos(this.camPitch), f = new T.Vector3(Math.sin(this.camYaw) * cp, Math.sin(this.camPitch), Math.cos(this.camYaw) * cp);
      // aproxima a câmera se houver obstáculo (colisores) entre jogador e câmera
      let dist = this.camDist;
      for (let d = 0.8; d <= this.camDist; d += 0.5) {
        const px = piv.x - f.x * d, pz = piv.z - f.z * d, py = piv.y - f.y * d;
        const c = w.collide(px, pz, 0.15);
        if (c.hit && py < this.y + 6) { dist = Math.max(0.8, d - 0.5); break; }
      }
      const want = new T.Vector3(piv.x - f.x * dist, piv.y - f.y * dist + 0.25, piv.z - f.z * dist);
      const g = w.heightAt(want.x, want.z) + 0.35;
      if (want.y < g) want.y = g;
      if (!this._camInit) { this.camPos.copy(want); this._camInit = true; }
      this.camPos.lerp(want, Math.min(1, dt * 14));
      cam.position.copy(this.camPos);
      cam.lookAt(piv.x, piv.y + 0.05, piv.z);
      cam.fov = 64;
    }
    cam.updateProjectionMatrix();
  };

  P.teleport = function (x, z) { this.x = x; this.z = z; this.y = this.world.heightAt(x, z); this.vy = 0; this._camInit = false; };

  // ---------------------------------------------------------------- NPCs
  RT.NPC = function (world, spec, card) {
    this.world = world;
    this.id = spec.id;
    this.card = card;
    this.name = card.name;
    this.x = spec.x; this.z = spec.z; this.home = { x: spec.x, z: spec.z };
    this.y = world.heightAt(this.x, this.z);
    this.defaultMode = spec.behavior || 'wander';
    this.radius = spec.radius || 8;
    this.patrol = spec.patrol || [];
    this.patrolIdx = 0;
    this.mode = this.defaultMode;     // modo atual (pode ser sobrescrito por ações)
    this.timer = 1 + Math.random() * 4;
    this.target = null;
    this.yaw = Math.random() * Math.PI * 2;
    this.speed = 0;
    this.talking = false;
    this.rand = RT.rng(world.seed ^ (this.id.length * 7919) ^ (card.name.length * 31));
    this.model = RT.makeHumanoid(Object.assign({}, card.appearance, spec.appearance || {}), { blob: world.budget.shadow === 0 });
    world.scene.add(this.model.root);
    this.label = RT.labelSprite(this.name);
    this.label.position.set(0, this.model.height + 0.45, 0);
    this.model.root.add(this.label);
    const hit = new T.Mesh(new T.CapsuleGeometry(0.4, this.model.height - 0.8, 2, 6), new T.MeshBasicMaterial({ visible: false }));
    hit.position.y = this.model.height / 2; hit.userData.npc = this;
    this.model.root.add(hit);
    this.hit = hit;
    this.model.root.position.set(this.x, this.y, this.z);
  };
  const N = RT.NPC.prototype;

  N.headPos = function (out) { return out.set(this.x, this.y + this.model.height + 0.3, this.z); };
  N.say = function (s) { this.bubble = { text: s, until: performance.now() + 6500 }; };

  // Ações vindas do agente de IA: follow | stay | wander | wave | nod | dance | flee | goto:<rótulo>
  N.act = function (action) {
    const a = String(action || '').trim();
    const lower = a.toLowerCase();
    if (lower === 'follow') { this.mode = 'follow'; }
    else if (lower === 'stay' || lower === 'wait') { this.mode = 'stay'; }
    else if (lower === 'wander' || lower === 'resume') { this.mode = this.defaultMode === 'stay' ? 'idle' : this.defaultMode; this.target = null; }
    else if (lower === 'flee') { this.mode = 'flee'; this.fleeT = 6; }
    else if (['wave', 'nod', 'dance', 'point'].indexOf(lower) >= 0) { this.model.play(lower); }
    else if (lower.indexOf('goto') === 0) {
      const label = a.slice(a.indexOf(':') + 1).trim().toLowerCase();
      const hit = this.world.labels.find((l) => l.text.toLowerCase() === label) || this.world.labels.find((l) => l.text.toLowerCase().indexOf(label) >= 0);
      if (hit) { this.mode = 'goto'; this.target = { x: hit.x + 2.5, z: hit.z + 2.5 }; }
    }
    return lower;
  };

  N._walkTo = function (tx, tz, speed, dt) {
    const w = this.world, dx = tx - this.x, dz = tz - this.z, d = Math.hypot(dx, dz);
    if (d < 0.25) { this.speed = 0; return true; }
    const want = Math.atan2(dx, dz);
    this.yaw += angleDiff(this.yaw, want) * Math.min(1, dt * 8);
    const step = Math.min(d, speed * dt);
    let nx = this.x + Math.sin(this.yaw) * step, nz = this.z + Math.cos(this.yaw) * step;
    const g = w.heightAt(nx, nz);
    if (g < w.waterY - 0.15 || Math.abs(g - this.y) > 0.9) { this.speed = 0; this.blocked = true; return true; }
    const c = w.collide(nx, nz, 0.4);
    const moved = Math.hypot(c.x - this.x, c.z - this.z);
    this.speed = moved / dt;
    if (c.hit && moved < step * 0.3) this.blocked = true;
    this.x = c.x; this.z = c.z;
    return false;
  };
  N._face = function (px, pz, dt, rate) {
    const want = Math.atan2(px - this.x, pz - this.z);
    this.yaw += angleDiff(this.yaw, want) * Math.min(1, dt * (rate || 5));
  };
  N._pickWander = function () {
    for (let i = 0; i < 6; i++) {
      const a = this.rand() * Math.PI * 2, r = 1.5 + this.rand() * this.radius;
      const x = this.home.x + Math.cos(a) * r, z = this.home.z + Math.sin(a) * r;
      if (this.world.heightAt(x, z) > this.world.waterY + 0.2 && Math.abs(x) < this.world.half - 6 && Math.abs(z) < this.world.half - 6) return { x, z };
    }
    return null;
  };

  N.update = function (dt, player, t, others) {
    const px = player.x, pz = player.z, dp = Math.hypot(px - this.x, pz - this.z);
    this.speed = 0;
    this.blocked = false;
    if (this.talking) { this._face(px, pz, dt, 6); }
    else switch (this.mode) {
      case 'follow': {
        if (dp > 2.6) this._walkTo(px, pz, dp > 9 ? 5.4 : dp > 5 ? 3.6 : 2.5, dt); else this._face(px, pz, dt, 4);
        break;
      }
      case 'stay': if (dp < 7) this._face(px, pz, dt, 3); break;
      case 'flee': {
        this.fleeT -= dt;
        const ax = this.x - px, az = this.z - pz;
        this._walkTo(this.x + ax, this.z + az, 4.6, dt);
        if (this.fleeT <= 0) { this.mode = this.defaultMode; this.home = { x: this.x, z: this.z }; }
        break;
      }
      case 'goto': {
        if (!this.target || this._walkTo(this.target.x, this.target.z, 2.2, dt)) { this.mode = this.defaultMode; if (this.target) this.home = { x: this.x, z: this.z }; this.target = null; }
        break;
      }
      case 'patrol': {
        if (this.patrol.length < 2) { this.mode = 'wander'; break; }
        const p = this.patrol[this.patrolIdx % this.patrol.length];
        if (this._walkTo(p[0], p[1], 1.3, dt) || this.blocked) this.patrolIdx++;
        break;
      }
      case 'wander': {
        if (!this.target) {
          this.timer -= dt;
          if (this.timer <= 0) { this.target = this._pickWander(); this.timer = 3 + this.rand() * 6; }
          else if (dp < 6) this._face(px, pz, dt, 1.5);
        } else if (this._walkTo(this.target.x, this.target.z, 1.1, dt) || this.blocked) this.target = null;
        break;
      }
      default: if (dp < 6) this._face(px, pz, dt, 1.5); // idle / stand
    }
    // separação simples entre NPCs
    if (others) for (let i = 0; i < others.length; i++) {
      const o = others[i]; if (o === this) continue;
      const dx = this.x - o.x, dz = this.z - o.z, d = Math.hypot(dx, dz);
      if (d < 0.8 && d > 1e-4) { this.x += (dx / d) * (0.8 - d) * 0.5; this.z += (dz / d) * (0.8 - d) * 0.5; }
    }
    this.y = this.world.heightAt(this.x, this.z);
    const r = this.model.root;
    r.position.set(this.x, this.y, this.z);
    r.rotation.y = this.yaw;
    this.model.update(dt, this.speed, false);
    const op = clamp(1 - (dp - 9) / 6, 0, 1);
    this.label.material.opacity = op; this.label.visible = op > 0.02;
  };

  N.snapshot = function () {
    return { x: +this.x.toFixed(2), z: +this.z.toFixed(2), mode: this.mode === 'goto' || this.mode === 'flee' ? this.defaultMode : this.mode, home: this.home };
  };
  N.restore = function (s) {
    if (!s) return;
    if (typeof s.x === 'number') { this.x = s.x; this.z = s.z; }
    if (s.home) this.home = s.home;
    if (s.mode) this.mode = s.mode;
  };
})();
