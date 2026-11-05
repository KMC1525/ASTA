/* ASTA runtime 2D — Plataforma: física de passo fixo (coyote time, pulo variável, plataformas, molas), inimigos, checkpoints e fases em ASCII.
   `G2.Plat.World` é a simulação (sem DOM, testável); a interface fica em G2.engines.platformer. */
(function (root) {
  'use strict';
  const G2 = root.G2;
  const TS = 32, W = 640, H = 360;
  const MAXV = 220, JUMP = 580, GRAV = 1500, PW = 20, PH = 28;

  // ------------------------------------------------------------------ simulação
  function World(level, cfg) {
    this.rows = level.tiles; this.h = this.rows.length; this.w = this.rows[0].length; this.cfg = cfg; this.ents = []; this.events = []; this.score = 0; this.coins = 0; this.done = false; this.t = 0;
    this.grid = this.rows.map((r) => r.split(''));
    let start = { x: 1, y: 1 };
    for (let y = 0; y < this.h; y++) for (let x = 0; x < this.w; x++) {
      const ch = this.grid[y][x], px = x * TS, py = y * TS;
      if (ch === 'P') { start = { x, y }; this.grid[y][x] = '.'; }
      else if (ch === 'C') { this.ents.push({ type: 'coin', x: px + 8, y: py + 8, w: 16, h: 16 }); this.grid[y][x] = '.'; }
      else if (ch === 'H') { this.ents.push({ type: 'heart', x: px + 6, y: py + 6, w: 20, h: 20 }); this.grid[y][x] = '.'; }
      else if (ch === 'K') { let gyy = y; while (gyy < this.h && '#S='.indexOf(this.grid[gyy][x]) < 0) gyy++; if (gyy < this.h && gyy > 0) this.ents.push({ type: 'check', x: px + 8, y: (gyy - 1) * TS, w: 16, h: 32, on: false }); this.grid[y][x] = '.'; }  /* checkpoint sempre sobre chão */
      else if (ch === 'F') { this.ents.push({ type: 'flag', x: px + 4, y: py - 128, w: 24, h: 160 });  /* mastro alto: dá para pegá-lo no ar */ this.grid[y][x] = '.'; }
      else if (ch === 'E') { this.ents.push({ type: 'enemy', kind: 'walker', x: px + 4, y: py + 12, w: 24, h: 20, vx: -40, vy: 0, alive: true, hp: 1 }); this.grid[y][x] = '.'; }
      else if (ch === 'B') { this.ents.push({ type: 'enemy', kind: 'bat', x: px + 4, y: py + 4, w: 24, h: 18, ox: px, oy: py, ph: x, alive: true, hp: 1 }); this.grid[y][x] = '.'; }
      else if (ch === 'J') { this.ents.push({ type: 'enemy', kind: 'jumper', x: px + 4, y: py + 8, w: 24, h: 24, vx: 0, vy: 0, wait: 1 + (x % 5) * 0.2, alive: true, hp: 1 }); this.grid[y][x] = '.'; }
    }
    this.start = { x: start.x * TS + (TS - PW) / 2, y: start.y * TS + TS - PH };
    this.check = null;
    this.p = { x: this.start.x, y: this.start.y, w: PW, h: PH, vx: 0, vy: 0, ground: false, coyote: 0, buffer: 0, face: 1, hp: cfg.hp, invuln: 0, dead: false, deadT: 0, jumps: 0, air: 0 };
  }
  const WP = World.prototype;
  WP.tile = function (tx, ty) { if (tx < 0 || tx >= this.w) return '#'; if (ty < 0) return '.'; if (ty >= this.h) return '.'; return this.grid[ty][tx]; };
  WP.solidTile = (ch) => ch === '#' || ch === 'S';
  WP.respawn = function () {
    const p = this.p, s = this.check || this.start; p.x = s.x; p.y = s.y; p.vx = p.vy = 0; p.dead = false; p.deadT = 0; p.hp = this.cfg.hp; p.invuln = 1.5; p.ground = false;
  };
  WP.hurt = function (dir, src) {
    const p = this.p; if (p.invuln > 0 || p.dead) return; this.cause = src || 'hit'; p.hp--; p.invuln = 1.3; p.vy = -260; p.vx = dir * 110; this.events.push('hit');
    if (p.hp <= 0) { p.dead = true; p.deadT = 0; this.events.push('die'); }
  };
  WP.overlap = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  WP.step = function (dt, inp) {
    const p = this.p, cfg = this.cfg; this.t += dt;
    if (p.dead) { p.deadT += dt; p.vy += GRAV * dt; p.y += p.vy * dt; return; }
    if (p.invuln > 0) p.invuln -= dt;
    const dir = (inp.right ? 1 : 0) - (inp.left ? 1 : 0), maxv = MAXV * cfg.speed;
    if (dir) { p.face = dir; const a = (p.ground ? 1700 : 1100) * dt; p.vx = p.vx < dir * maxv ? Math.min(dir * maxv, p.vx + a) : Math.max(dir * maxv, p.vx - a); }
    else { const f = (p.ground ? 1900 : 350) * dt; p.vx = p.vx > 0 ? Math.max(0, p.vx - f) : Math.min(0, p.vx + f); }
    p.buffer = inp.jumpPressed ? 0.12 : p.buffer - dt; p.coyote = p.ground ? 0.1 : p.coyote - dt;
    if (p.buffer > 0 && (p.coyote > 0 || (cfg.double_jump && p.jumps < 2 && !p.ground))) {
      p.vy = -JUMP * cfg.jump; p.buffer = 0; p.coyote = 0; p.jumps = p.ground || p.jumps === 0 ? 1 : p.jumps + 1; p.ground = false; this.events.push('jump');
    }
    p.vy += GRAV * dt * (!inp.jumpHeld && p.vy < 0 ? 2.1 : 1); if (p.vy > 820) p.vy = 820;
    this.moveX(p.vx * dt); this.moveY(p.vy * dt);
    if (p.ground) { p.jumps = 0; p.air = 0; } else p.air += dt;
    if (p.y > this.h * TS + 120) { this.cause = 'fall'; p.hp = 0; p.dead = true; p.deadT = 0; this.events.push('die'); return; }
    // hazards (espinhos: metade inferior do tile)
    const x0 = Math.floor(p.x / TS), x1 = Math.floor((p.x + p.w - 1) / TS), y0 = Math.floor((p.y + 8) / TS), y1 = Math.floor((p.y + p.h - 1) / TS);
    for (let ty = y0; ty <= y1; ty++) for (let tx = x0; tx <= x1; tx++) if (this.tile(tx, ty) === '^') { const sp = { x: tx * TS + 4, y: ty * TS + 14, w: 24, h: 18 }; if (this.overlap(p, sp)) this.hurt(-p.face, 'spike'); }
    this.entities(dt);
  };
  WP.moveX = function (dx) {
    const p = this.p; p.x += dx; if (p.x < 0) { p.x = 0; p.vx = 0; }
    const dirR = dx > 0, x = dirR ? p.x + p.w : p.x, tx = Math.floor(x / TS), y0 = Math.floor(p.y / TS), y1 = Math.floor((p.y + p.h - 0.01) / TS);
    for (let ty = y0; ty <= y1; ty++) if (this.solidTile(this.tile(tx, ty))) { p.x = dirR ? tx * TS - p.w - 0.01 : (tx + 1) * TS + 0.01; p.vx = 0; break; }
  };
  WP.moveY = function (dy) {
    const p = this.p, prevBottom = p.y + p.h; p.y += dy; p.ground = false;
    const x0 = Math.floor((p.x + 1) / TS), x1 = Math.floor((p.x + p.w - 1) / TS);
    if (dy >= 0) {
      const ty = Math.floor((p.y + p.h) / TS);
      for (let tx = x0; tx <= x1; tx++) {
        const ch = this.tile(tx, ty), top = ty * TS;
        if (this.solidTile(ch) || (ch === '=' && prevBottom <= top + 1)) { p.y = top - p.h; p.vy = ch === 'S' ? -820 : 0; p.ground = ch !== 'S'; if (ch === 'S') this.events.push('spring'); break; }
      }
    } else {
      const ty = Math.floor(p.y / TS);
      for (let tx = x0; tx <= x1; tx++) if (this.solidTile(this.tile(tx, ty))) { p.y = (ty + 1) * TS; p.vy = 0; break; }
    }
  };
  WP.entities = function (dt) {
    const p = this.p;
    this.ents.forEach((e) => {
      if (e.type === 'enemy') {
        if (!e.alive) return;
        if (e.kind === 'walker') {
          e.vy = Math.min(600, e.vy + GRAV * dt); e.x += e.vx * dt;
          const fx = e.vx > 0 ? e.x + e.w + 1 : e.x - 1, wall = this.solidTile(this.tile(Math.floor(fx / TS), Math.floor((e.y + e.h - 4) / TS))), ledge = !(this.solidTile(this.tile(Math.floor(fx / TS), Math.floor((e.y + e.h + 4) / TS))) || this.tile(Math.floor(fx / TS), Math.floor((e.y + e.h + 4) / TS)) === '=');
          if (wall || ledge) { e.vx = -e.vx; e.x += e.vx * dt * 2; }
          e.y += e.vy * dt; const ty = Math.floor((e.y + e.h) / TS), tx = Math.floor((e.x + e.w / 2) / TS); if (this.solidTile(this.tile(tx, ty)) || this.tile(tx, ty) === '=') { e.y = ty * TS - e.h; e.vy = 0; }
          if (e.y > this.h * TS + 200) e.alive = false;
        } else if (e.kind === 'bat') { e.x = e.ox + 4 + Math.sin(this.t * 1.6 + e.ph) * 64; e.y = e.oy + 4 + Math.sin(this.t * 3.2 + e.ph) * 14; }
        else if (e.kind === 'jumper') {
          e.vy = Math.min(600, e.vy + GRAV * dt); e.y += e.vy * dt; e.x += e.vx * dt; const ty = Math.floor((e.y + e.h) / TS), tx = Math.floor((e.x + e.w / 2) / TS);
          if (e.vy >= 0 && (this.solidTile(this.tile(tx, ty)) || this.tile(tx, ty) === '=')) { e.y = ty * TS - e.h; e.vy = 0; e.vx = 0; e.wait -= dt; if (e.wait <= 0) { e.wait = 1.1; e.vy = -430; e.vx = Math.abs(p.x - e.x) < 220 ? (p.x < e.x ? -70 : 70) : 0; } }
          if (this.solidTile(this.tile(Math.floor((e.x + (e.vx > 0 ? e.w : 0)) / TS), Math.floor((e.y + e.h / 2) / TS)))) e.vx = 0;
        }
        if (!p.dead && this.overlap(p, e)) {
          if (p.vy > 60 && p.y + p.h - e.y < 18) { e.alive = false; p.vy = -380; this.score += 100; this.events.push('stomp'); } else this.hurt(p.x < e.x ? -1 : 1, e.kind);
        }
      } else if (e.type === 'coin' && !e.got && this.overlap(p, e)) { e.got = true; this.coins++; this.score += 10; this.events.push('coin'); }
      else if (e.type === 'heart' && !e.got && p.hp < this.cfg.hp && this.overlap(p, e)) { e.got = true; p.hp++; this.events.push('powerup'); }
      else if (e.type === 'check' && !e.on && this.overlap(p, e)) { e.on = true; this.check = { x: e.x - 2, y: Math.floor(e.y / TS) * TS + TS - PH }; this.events.push('chime'); }
      else if (e.type === 'flag' && !this.done && this.overlap(p, e)) { this.done = true; this.score += 250; this.events.push('powerup'); }
    });
  };
  G2.Plat = { World, TS, MAXV, JUMP, GRAV };

  // ------------------------------------------------------------------ interface
  G2.engines.platformer = function (spec) {
    const data = spec.data, T = G2.t, th0 = G2.theme(spec.style.theme), accent = spec.style.accent || th0.accent, cfg = Object.assign({ hp: 3, speed: 1, jump: 1, double_jump: false }, data.player);
    const S = { t: 0, mode: 'title', level: 0, world: null, lives: cfg.lives, score: 0, cam: 0, camY: 0, fade: 1, fadeTo: 0, menus: [], banner: '', bannerT: 0, overT: 0, total: 0, clearT: 0 };
    G2.screen.letterbox = '#000';
    const lv = () => data.levels[S.level];
    function startLevel(i, keep) {
      S.level = i; S.world = new World(lv(), cfg); S.cam = 0; S.camY = 0; S.mode = 'play'; S.banner = lv().name + (lv().intro ? ' — ' + lv().intro : ''); S.bannerT = 3; S.fade = 1; S.fadeTo = 0;
      if (!keep) { S.lives = cfg.lives; S.score = 0; }
      S.baseScore = S.score; G2.audio.music(['calm', 'joyful', 'mysterious', 'epic', 'tense'][i % 5], spec.audio.music.scale, spec.audio.music.tempo + i * 6);
      G2.save.set('plat_auto', { level: i, lives: S.lives, score: S.score });
    }
    function titleMenu() {
      const s = G2.save.get('plat_auto'); const M = G2.ListMenu;
      S.menus = [new M({ x: W / 2 - 110, y: 210, w: 220, rowH: 30, entries: [{ label: T('Continuar', 'Continue') + (s ? ' (' + (s.level + 1) + ')' : ''), disabled: !s }, { label: T('Novo jogo', 'New game') }],
        onPick: (i) => { S.menus = []; if (i === 0) { S.lives = s.lives; S.score = s.score; startLevel(s.level, true); } else startLevel(0, false); } })];
      S.menus[0].sel = s ? 0 : 1; S.mode = 'title';
    }
    function update(dt) {
      S.t += dt; if (S.bannerT > 0) S.bannerT -= dt; S.fade += Math.sign(S.fadeTo - S.fade) * Math.min(Math.abs(S.fadeTo - S.fade), dt * 3);
      const I = G2.input;
      if (S.mode === 'title') { if (S.menus[0]) S.menus[0].update(); return; }
      if (S.mode === 'over' || S.mode === 'end') { S.overT += dt; if (S.overT > 0.7 && I.pressed('action')) { if (S.mode === 'end') titleMenu(); else startLevel(S.level, false); } return; }
      const w = S.world;
      if (S.mode === 'clear') { S.clearT += dt; if (S.clearT > 1.4 && (I.pressed('action') || S.clearT > 3.5)) { if (S.level + 1 < data.levels.length) startLevel(S.level + 1, true); else { S.mode = 'end'; S.overT = 0; G2.audio.sfx('powerup'); } } return; }
      if (I.pressed('restart')) { S.score = S.baseScore; startLevel(S.level, true); return; }
      const inp = { left: I.down('left'), right: I.down('right'), jumpPressed: I.pressed('jump'), jumpHeld: I.down('jump') };
      w.step(dt, inp); w.events.splice(0).forEach((e) => G2.audio.sfx(e === 'stomp' ? 'hit' : e === 'spring' ? 'jump' : e === 'die' ? 'explosion' : e));
      if (w.p.dead && w.p.deadT > 1.1) { S.lives--; if (S.lives <= 0) { S.mode = 'over'; S.overT = 0; G2.audio.music('stop'); } else { w.respawn(); } }
      if (w.done && S.mode === 'play') { S.mode = 'clear'; S.clearT = 0; S.score += w.score; G2.audio.sfx('powerup'); }
      const p = w.p, tx = G2.clamp(p.x + p.w / 2 - W / 2 + p.face * 40, 0, Math.max(0, w.w * TS - W)), ty = G2.clamp(p.y - H * 0.55, 0, Math.max(0, w.h * TS - H));
      S.cam += (tx - S.cam) * Math.min(1, dt * 7); S.camY += (ty - S.camY) * Math.min(1, dt * 5);
    }
    function tileColors(theme) { const t = G2.theme(theme); return { top: theme === 'snow' ? '#f4f8fc' : theme === 'desert' ? '#e8d6a0' : t.grass, body: theme === 'snow' ? '#9fb4c8' : G2.shade(t.ground === '#0a0f26' ? '#3a2a1a' : t.ground, 0.2), dark: G2.shade(t.ground, -0.1) }; }
    function render() {
      const c = G2.screen.begin(), t = S.t;
      if (S.mode === 'title') { c.fillStyle = G2.art.grad(c, 0, 0, 0, H, [[0, th0.sky[0]], [1, th0.sky[1]]]); c.fillRect(0, 0, W, H); G2.art.parallax(c, spec.style.theme, t * 30, W, H, t); c.textAlign = 'center'; c.textBaseline = 'middle'; c.font = G2.font(36, true); c.fillStyle = '#fff'; c.shadowColor = '#000'; c.shadowBlur = 8; c.fillText(spec.title, W / 2, 100); c.shadowBlur = 0; c.font = G2.font(15); c.fillStyle = 'rgba(255,255,255,0.85)'; c.fillText(String(spec.description || '').slice(0, 90), W / 2, 150); S.menus.forEach((m) => m.draw(c)); G2.screen.end(); return; }
      const w = S.world, L = lv(), tc = tileColors(L.theme);
      G2.art.parallax(c, L.theme, S.cam, W, H, t);
      c.save(); c.translate(-Math.round(S.cam), -Math.round(S.camY));
      const x0 = Math.floor(S.cam / TS), x1 = Math.min(w.w - 1, x0 + 21), y0 = Math.floor(S.camY / TS), y1 = Math.min(w.h - 1, y0 + 12);
      for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
        const ch = w.grid[y][x], px = x * TS, py = y * TS;
        if (ch === '#') { c.fillStyle = tc.body; c.fillRect(px, py, TS, TS); c.fillStyle = tc.dark; c.fillRect(px + 4, py + 10, 6, 3); c.fillRect(px + 18, py + 20, 8, 3); if (y === 0 || w.grid[y - 1][x] !== '#') { c.fillStyle = tc.top; c.fillRect(px, py, TS, 8); c.fillStyle = G2.shade(tc.top, -0.2); for (let i = 0; i < 4; i++) c.fillRect(px + 2 + i * 8, py + 8, 4, 3); } }
        else if (ch === '=') { c.fillStyle = '#8a5a35'; c.fillRect(px, py, TS, 8); c.fillStyle = '#b8844a'; c.fillRect(px, py, TS, 3); }
        else if (ch === '^') { c.fillStyle = '#c8ccd6'; for (let i = 0; i < 3; i++) { c.beginPath(); c.moveTo(px + i * 10 + 1, py + TS); c.lineTo(px + i * 10 + 6, py + 14); c.lineTo(px + i * 10 + 11, py + TS); c.fill(); } }
        else if (ch === 'S') { c.fillStyle = '#5a6070'; c.fillRect(px + 4, py + 22, 24, 10); c.fillStyle = '#ff6b6b'; c.fillRect(px + 2, py + 14, 28, 8); c.fillStyle = '#ffd166'; c.fillRect(px + 6, py + 16, 20, 3); }
      }
      w.ents.forEach((e) => {
        if (e.type === 'coin' && !e.got) { const sq = Math.abs(Math.sin(t * 5 + e.x)); c.fillStyle = '#ffd166'; c.beginPath(); c.ellipse(e.x + 8, e.y + 8, 3 + 5 * sq, 8, 0, 0, 6.28); c.fill(); c.fillStyle = 'rgba(255,255,255,0.6)'; c.fillRect(e.x + 7, e.y + 3, 2, 6); }
        else if (e.type === 'heart' && !e.got) G2.art.heart(c, e.x + 10, e.y + 2 + Math.sin(t * 4) * 2, 18, true);
        else if (e.type === 'check') { c.fillStyle = '#6a6f7a'; c.fillRect(e.x + 6, e.y, 3, 32); c.fillStyle = e.on ? '#5fd68a' : '#ff6b6b'; c.beginPath(); c.moveTo(e.x + 9, e.y + 2); c.lineTo(e.x + 9 + 14, e.y + 8 + (e.on ? Math.sin(t * 6) * 1.5 : 0)); c.lineTo(e.x + 9, e.y + 14); c.fill(); }
        else if (e.type === 'flag') { c.fillStyle = '#e8e8f0'; c.fillRect(e.x + 10, e.y + 20, 4, 140); c.fillStyle = '#ffd166'; c.beginPath(); c.arc(e.x + 12, e.y + 18, 6, 0, 6.28); c.fill(); c.fillStyle = accent; c.beginPath(); c.moveTo(e.x + 14, e.y + 26); c.lineTo(e.x + 14 + 30, e.y + 38 + Math.sin(t * 5) * 2); c.lineTo(e.x + 14, e.y + 50); c.fill(); }
        else if (e.type === 'enemy' && e.alive) { const kind = e.kind === 'walker' ? 'slime' : e.kind === 'bat' ? 'bat' : 'goblin'; G2.art.monster(c, kind, e.x + e.w / 2, e.y + e.h / 2 - (e.kind === 'bat' ? 0 : 4), e.kind === 'bat' ? 36 : 42, e.kind === 'walker' ? '#c0506f' : e.kind === 'bat' ? '#9b72d0' : '#6bd16b', t + e.x, false); }
      });
      const p = w.p; if (!(p.invuln > 0 && Math.floor(t * 16) % 2 === 0)) G2.art.sprite(c, data.player.appearance, p.x + p.w / 2, p.y + p.h + 1, 30, { dir: p.dead ? 'down' : (p.face > 0 ? 'right' : 'left'), frame: t * 14, walking: p.ground && Math.abs(p.vx) > 20, hop: 0 });
      c.restore();
      // HUD
      for (let i = 0; i < cfg.hp; i++) G2.art.heart(c, 22 + i * 26, 14, 20, i < p.hp);
      c.font = G2.font(15, true); c.textBaseline = 'top'; c.textAlign = 'left'; c.fillStyle = '#fff'; c.fillText('♥×' + Math.max(0, S.lives) + '   ● ' + w.coins + '   ' + (S.score + w.score), 14, 40);
      c.textAlign = 'right'; c.fillText(L.name, W - 14, 14);
      if (S.bannerT > 0) { c.save(); c.globalAlpha = Math.min(1, S.bannerT); c.font = G2.font(18, true); c.textAlign = 'center'; const tw = Math.min(W - 40, c.measureText(S.banner).width + 40); G2.panel(c, W / 2 - tw / 2, 60, tw, 34, { r: 17 }); c.fillStyle = '#fff'; c.textBaseline = 'middle'; c.fillText(S.banner, W / 2, 78); c.restore(); }
      if (S.mode === 'clear') { c.fillStyle = 'rgba(0,0,10,0.55)'; c.fillRect(0, 0, W, H); c.textAlign = 'center'; c.textBaseline = 'middle'; c.font = G2.font(38, true); c.fillStyle = accent; c.fillText(T('Fase concluída!', 'Level complete!'), W / 2, H / 2 - 20); c.font = G2.font(17); c.fillStyle = '#fff'; c.fillText(T('Pontos: ', 'Score: ') + (S.score + w.score) + '   ●' + w.coins, W / 2, H / 2 + 24); }
      if (S.mode === 'over' || S.mode === 'end') { const a = Math.min(1, S.overT * 1.5); c.fillStyle = 'rgba(2,3,10,' + 0.85 * a + ')'; c.fillRect(0, 0, W, H); c.globalAlpha = a; c.textAlign = 'center'; c.textBaseline = 'middle'; c.font = G2.font(40, true); c.fillStyle = S.mode === 'end' ? accent : '#ff7a7a'; c.fillText(S.mode === 'end' ? T('Você venceu!', 'You win!') : T('Fim de jogo', 'Game over'), W / 2, H / 2 - 30); c.font = G2.font(16); c.fillStyle = '#fff'; if (S.mode === 'end' && data.ending) G2.wrap(c, data.ending, W - 120).forEach((l, i) => c.fillText(l, W / 2, H / 2 + 16 + i * 22)); c.fillText(T('Pressione Espaço', 'Press Space'), W / 2, H - 50); c.globalAlpha = 1; }
      if (S.fade > 0.001) { c.fillStyle = 'rgba(0,0,0,' + S.fade + ')'; c.fillRect(0, 0, W, H); }
      G2.screen.end();
    }
    function pointer(type, x, y) {
      if (S.mode === 'title') { if (S.menus[0]) S.menus[0].pointer(type, x, y); return; }
      if (type === 'down' && (S.mode === 'over' || S.mode === 'end') && S.overT > 0.7) { if (S.mode === 'end') titleMenu(); else startLevel(S.level, false); }
      if (type === 'down' && S.mode === 'clear' && S.clearT > 1.4) S.clearT = 99;
    }
    return { update, render, pointer, begin: titleMenu, getSave: () => ({ level: S.level, lives: S.lives, score: S.score }), state: S, W, H };
  };
})(typeof window !== 'undefined' ? window : globalThis);
