/* ASTA runtime 2D — Side scroller: shooter (ondas, power-ups, chefes) e runner (obstáculos, pulo e deslize) com rolagem automática. */
(function (root) {
  'use strict';
  const G2 = root.G2;
  const W = 640, H = 360;

  // ------------------------------------------------------------------ arte dos inimigos/nave
  function enemyShape(c, shape, x, y, s, color, t) {
    c.save(); c.translate(x, y); const dark = G2.shade(color, -0.4), light = G2.shade(color, 0.4);
    if (shape === 'saucer') { G2.art.circ(c, 0, -s * 0.12, s * 0.28, light); c.fillStyle = color; c.beginPath(); c.ellipse(0, 0, s * 0.5, s * 0.2, 0, 0, 6.28); c.fill(); for (let i = -1; i <= 1; i++) G2.art.circ(c, i * s * 0.24, s * 0.04, s * 0.04, '#fff6a8'); }
    else if (shape === 'blob') { G2.art.monster(c, 'slime', 0, 0, s * 1.05, color, t, false); }
    else if (shape === 'fish') { c.fillStyle = color; c.beginPath(); c.ellipse(0, 0, s * 0.4, s * 0.22, 0, 0, 6.28); c.fill(); G2.art.poly(c, [[s * 0.36, 0], [s * 0.62, -s * 0.2 + Math.sin(t * 9) * 3], [s * 0.62, s * 0.2 + Math.sin(t * 9) * 3]], dark); G2.art.circ(c, -s * 0.22, -s * 0.04, s * 0.06, '#fff'); G2.art.circ(c, -s * 0.23, -s * 0.04, s * 0.03, '#111'); }
    else if (shape === 'bird') { const f = Math.sin(t * 12) * s * 0.22; G2.art.poly(c, [[0, 0], [s * 0.3, -s * 0.35 + f], [s * 0.45, 0]], dark); G2.art.poly(c, [[0, 0], [s * 0.3, s * 0.35 - f], [s * 0.45, 0]], dark); G2.art.circ(c, 0, 0, s * 0.24, color); G2.art.poly(c, [[-s * 0.2, 0], [-s * 0.42, s * 0.04], [-s * 0.2, s * 0.1]], '#ffd166'); G2.art.circ(c, -s * 0.08, -s * 0.06, s * 0.05, '#fff'); }
    else if (shape === 'ship') { G2.art.poly(c, [[-s * 0.5, 0], [s * 0.35, -s * 0.3], [s * 0.2, 0], [s * 0.35, s * 0.3]], color); G2.art.poly(c, [[-s * 0.3, 0], [s * 0.1, -s * 0.12], [s * 0.1, s * 0.12]], light); G2.art.circ(c, s * 0.28, 0, s * 0.08, '#ffb703'); }
    else { G2.art.poly(c, [[-s * 0.4, 0], [-s * 0.15, -s * 0.4], [s * 0.25, -s * 0.34], [s * 0.42, 0.05 * s], [s * 0.2, s * 0.38], [-s * 0.25, s * 0.36]], color); G2.art.circ(c, -s * 0.08, -s * 0.08, s * 0.1, dark); G2.art.circ(c, s * 0.14, s * 0.12, s * 0.07, dark); }
    c.restore();
  }
  function playerShape(c, kind, ap, x, y, t, inv) {
    if (inv && Math.floor(t * 16) % 2 === 0) return;
    if (kind === 'ship' || kind === 'bird' || kind === 'fish') {
      c.save(); c.translate(x, y); const col = (ap && ap.top) || '#6ab0ff';
      G2.art.poly(c, [[-22, 0], [-8, -4], [-14, -12], [4, -12], [26, 0], [4, 12], [-14, 12], [-8, 4]], '#cfd6e6'); G2.art.poly(c, [[-6, 0], [8, -6], [8, 6]], col); G2.art.circ(c, 6, 0, 4, '#fff6a8');
      const f = 8 + Math.sin(t * 40) * 3; G2.art.poly(c, [[-22, -4], [-22 - f, 0], [-22, 4]], '#ffb347'); c.restore();
    } else { G2.art.sprite(c, ap, x, y + 20, 38, { dir: 'right', frame: t * 8, walking: true }); c.fillStyle = 'rgba(255,180,70,0.8)'; c.beginPath(); c.ellipse(x - 14, y + 20, 4 + Math.sin(t * 40) * 2, 2, 0, 0, 6.28); c.fill(); }
  }
  G2.SS = { enemyShape, playerShape };

  // ------------------------------------------------------------------ motor
  G2.engines.side_scroller = function (spec) {
    const data = spec.data, runner = data.mode === 'runner', T = G2.t, accent = spec.style.accent || G2.theme(spec.style.theme).accent, pl = data.player;
    const S = { t: 0, mode: 'title', stage: 0, time: 0, hp: pl.hp, score: 0, menus: [], fade: 1, banner: '', bannerT: 0, overT: 0, god: false, cam: 0, shake: 0 };
    G2.screen.letterbox = '#000';
    const GROUND = H - 64;
    let P, bullets, ebullets, enemies, pickups, obstacles, boss, spawnQ, powers, stageDef, flash;

    function startStage(i, keepScore) {
      S.stage = i; S.time = 0; stageDef = data.stages[i]; S.mode = 'play'; S.fade = 1; if (!keepScore) { S.score = 0; } S.hp = pl.hp; S.cam = 0; S.stageScore = S.score;
      P = { x: runner ? 110 : 80, y: runner ? GROUND : H / 2, vy: 0, w: 30, h: 24, inv: 0, shield: 0, power: 1, fire: 0, slide: 0, ground: true, dead: false };
      bullets = []; ebullets = []; enemies = []; pickups = []; obstacles = []; boss = null; flash = 0;
      spawnQ = []; stageDef.waves.forEach((w) => { for (let k = 0; k < w.count; k++) spawnQ.push({ t: w.t + k * w.gap, w, k }); }); spawnQ.sort((a, b) => a.t - b.t);
      S.pickQ = stageDef.pickups.slice(); S.obsQ = stageDef.obstacles.slice(); S.bossQ = stageDef.boss;
      S.banner = stageDef.name; S.bannerT = 2.4; G2.audio.music(['epic', 'tense', 'joyful', 'mysterious', 'epic'][i % 5], spec.audio.music.scale, 110 + i * 6);
      G2.save.set('ss_auto', { stage: i, score: S.score });
    }
    function titleMenu() {
      const s = G2.save.get('ss_auto'); const M = G2.ListMenu;
      S.menus = [new M({ x: W / 2 - 110, y: 210, w: 220, rowH: 30, entries: [{ label: T('Continuar', 'Continue') + (s ? ' (' + (s.stage + 1) + ')' : ''), disabled: !s }, { label: T('Novo jogo', 'New game') }], onPick: (i) => { S.menus = []; if (i === 0) { S.score = s.score; startStage(s.stage, true); } else startStage(0, false); } })];
      S.menus[0].sel = s ? 0 : 1; S.mode = 'title';
    }
    const hurt = () => { if (P.inv > 0 || S.god) return; if (P.shield > 0) { P.shield = 0; P.inv = 0.8; G2.audio.sfx('hit'); return; } S.hp--; P.inv = 1.6; S.shake = 0.25; G2.audio.sfx('hit'); if (S.hp <= 0) { P.dead = true; S.mode = 'over'; S.overT = 0; G2.audio.sfx('explosion'); G2.audio.music('stop'); } };
    const rectHit = (a, b) => Math.abs(a.x - b.x) < (a.w + b.w) / 2 && Math.abs(a.y - b.y) < (a.h + b.h) / 2;
    function stageClear() { S.mode = 'clear'; S.overT = 0; S.score += 500; G2.audio.sfx('powerup'); }

    // ----- shooter
    function spawnEnemy(sq) {
      const def = data.enemies[sq.w.enemy], base = sq.w.y * H, k = sq.k, n = sq.w.count; let y = base;
      if (sq.w.pattern === 'v') y = base + (k - (n - 1) / 2) * 0 + Math.abs(k - (n - 1) / 2) * 26 - 20; else if (sq.w.pattern === 'swarm') y = G2.clamp(base + (Math.sin(k * 12.9898) * 43758.5453 % 1) * 120, 30, H - 30);
      enemies.push({ x: W + 30, y0: y, y, t: 0, def, id: sq.w.enemy, hp: def.hp, pat: sq.w.pattern, shootT: 1 + Math.random() * 1.5, w: 28, h: 22, ph: k });
    }
    function updateShooter(dt) {
      const spd = 230 * pl.speed, I = G2.input;
      P.x = G2.clamp(P.x + I.axisX() * spd * dt, 24, W * 0.62); P.y = G2.clamp(P.y + I.axisY() * spd * dt, 20, H - 20);
      P.fire -= dt; if (I.down('fire') && P.fire <= 0) { P.fire = 0.26 / pl.fire_rate; const lv = P.power; const mk = (dy) => bullets.push({ x: P.x + 22, y: P.y + dy, vx: 540, vy: dy * 6, w: 12, h: 5 }); if (lv === 1) mk(0); else if (lv === 2) { mk(-7); mk(7); } else { mk(0); mk(-12); mk(12); } G2.audio.sfx('laser'); }
      while (spawnQ.length && spawnQ[0].t <= S.time) spawnEnemy(spawnQ.shift());
      while (S.pickQ.length && S.pickQ[0].t <= S.time) { const p = S.pickQ.shift(); pickups.push({ x: W + 20, y: p.y * H, type: p.type, w: 18, h: 18 }); }
      if (S.bossQ && !boss && S.time >= S.bossQ.t) { boss = { x: W + 80, y: H / 2, hp: S.bossQ.hp, max: S.bossQ.hp, def: S.bossQ, t: 0, shootT: 1.5, w: 110, h: 90, dir: 1, in: true }; S.banner = S.bossQ.name; S.bannerT = 2.6; G2.audio.music('epic', spec.audio.music.scale, 150); }
      enemies.forEach((e) => {
        e.t += dt; e.x -= (110 + stageDef.speed * 0.2) * e.def.speed * dt;
        if (e.pat === 'sine') e.y = e.y0 + Math.sin(e.t * 3 + e.ph) * 55; else if (e.pat === 'zigzag') e.y = e.y0 + (Math.abs(((e.t * 1.2 + e.ph * 0.3) % 2) - 1) * 2 - 1) * 70;
        e.shootT -= dt; if (e.def.shoots && e.shootT <= 0 && e.x < W - 30) { e.shootT = 1.8 + Math.random(); const dx = P.x - e.x, dy = P.y - e.y, d = Math.hypot(dx, dy) || 1; ebullets.push({ x: e.x - 10, y: e.y, vx: dx / d * 190, vy: dy / d * 190, w: 8, h: 8 }); }
      });
      if (boss) {
        boss.t += dt; if (boss.in) { boss.x -= 120 * dt; if (boss.x <= W - 110) boss.in = false; }
        else { const pat = boss.def.pattern; boss.y += boss.dir * (pat === 'sweep' ? 150 : 80) * dt; if (boss.y < 60 || boss.y > H - 60) boss.dir *= -1; boss.shootT -= dt;
          if (boss.shootT <= 0) { boss.shootT = pat === 'rain' ? 0.35 : 1.1; if (pat === 'rain') ebullets.push({ x: 60 + Math.random() * (W - 120), y: -10, vx: 0, vy: 170, w: 9, h: 9 }); else { const a = Math.atan2(P.y - boss.y, P.x - boss.x); [-0.25, 0, 0.25].forEach((o) => ebullets.push({ x: boss.x - 40, y: boss.y, vx: Math.cos(a + o) * 200, vy: Math.sin(a + o) * 200, w: 9, h: 9 })); } } }
      }
      bullets.forEach((b) => { b.x += b.vx * dt; b.y += b.vy * dt; }); ebullets.forEach((b) => { b.x += b.vx * dt; b.y += b.vy * dt; }); pickups.forEach((p) => (p.x -= stageDef.speed * 0.6 * dt));
      bullets.forEach((b) => { enemies.forEach((e) => { if (b.dead || e.hp <= 0) return; if (rectHit(b, e)) { b.dead = true; e.hp--; G2.audio.sfx('hit'); if (e.hp <= 0) { S.score += e.def.score; G2.audio.sfx('explosion'); if (Math.random() < 0.12) pickups.push({ x: e.x, y: e.y, type: ['power', 'shield', 'heart', 'coin'][Math.floor(Math.random() * 4)], w: 18, h: 18 }); } } });
        if (boss && !b.dead && rectHit(b, boss)) { b.dead = true; boss.hp--; flash = 0.06; if (boss.hp <= 0) { S.score += 1000; boss = null; G2.audio.sfx('explosion'); stageClear(); } } });
      enemies.forEach((e) => { if (e.hp > 0 && rectHit(P, e)) { e.hp = 0; hurt(); } });
      ebullets.forEach((b) => { if (!b.dead && rectHit(P, { x: b.x, y: b.y, w: b.w, h: b.h })) { b.dead = true; hurt(); } });
      if (boss && !boss.in && rectHit(P, boss)) hurt();
      pickups.forEach((p) => { if (!p.dead && rectHit(P, p)) { p.dead = true; if (p.type === 'power') P.power = Math.min(3, P.power + 1); else if (p.type === 'shield') P.shield = 1; else if (p.type === 'heart') S.hp = Math.min(pl.hp, S.hp + 1); else S.score += 50; G2.audio.sfx(p.type === 'coin' ? 'coin' : 'powerup'); } });
      bullets = bullets.filter((b) => !b.dead && b.x < W + 20); ebullets = ebullets.filter((b) => !b.dead && b.x > -20 && b.y < H + 20 && b.y > -30); enemies = enemies.filter((e) => e.hp > 0 && e.x > -40); pickups = pickups.filter((p) => !p.dead && p.x > -30);
      if (!S.bossQ && S.time > stageDef.length && !enemies.length && !spawnQ.length) stageClear();
    }

    // ----- runner
    function updateRunner(dt) {
      const I = G2.input, spd = stageDef.speed * 1.6; S.cam += spd * dt;
      P.slide = Math.max(0, P.slide - dt);
      if (P.ground && I.pressed('jump') && !(I.down('down'))) { P.vy = -560 * (0.9 + pl.speed * 0.1); P.ground = false; G2.audio.sfx('jump'); }
      if (P.ground && I.pressed('down')) P.slide = 0.55;
      if (!P.ground && I.down('down')) P.vy += 1800 * dt;
      P.vy += 1500 * (!I.down('jump') && P.vy < 0 ? 2.2 : 1) * dt; P.y += P.vy * dt;
      const over = obstacles.find((o) => o.type === 'pit' && P.x > o.x - o.w / 2 + 8 && P.x < o.x + o.w / 2 - 8);
      if (P.y >= GROUND && !over) { P.y = GROUND; P.vy = 0; P.ground = true; } else P.ground = false;
      if (P.y > H + 60) { hurt(); P.y = GROUND; P.vy = 0; P.x = P.x; const pit = over; if (pit) { obstacles = obstacles.filter((o) => o !== pit); } P.ground = true; }
      while (S.obsQ.length && S.obsQ[0].t <= S.time) { const o = S.obsQ.shift(); const def = { rock: { w: 30, h: 30 }, crate: { w: 38, h: 52 }, pit: { w: 96, h: 0 }, flyer: { w: 34, h: 24 } }[o.type]; obstacles.push({ type: o.type, x: W + 40, w: def.w, h: def.h, y: o.type === 'flyer' ? GROUND - 52 : GROUND - def.h / 2, ph: Math.random() * 6 }); }
      while (S.pickQ.length && S.pickQ[0].t <= S.time) { const p = S.pickQ.shift(); for (let k = 0; k < 4; k++) pickups.push({ x: W + 20 + k * 34, y: GROUND - 36 - Math.sin(k / 3 * 3.14) * 50, type: 'coin', w: 16, h: 16 }); }
      obstacles.forEach((o) => (o.x -= spd * dt)); pickups.forEach((p) => (p.x -= spd * dt));
      const hb = { x: P.x, y: P.y - (P.slide > 0 ? 10 : 20), w: 22, h: P.slide > 0 ? 20 : 40 };
      obstacles.forEach((o) => { if (o.type === 'pit' || o.hit) return; if (rectHit(hb, { x: o.x, y: o.y, w: o.w - 4, h: o.h - 4 })) { o.hit = true; hurt(); } });
      pickups.forEach((p) => { if (!p.dead && rectHit(hb, p)) { p.dead = true; S.score += 25; G2.audio.sfx('coin'); } });
      obstacles = obstacles.filter((o) => o.x > -80); pickups = pickups.filter((p) => !p.dead && p.x > -30);
      S.score += 0; if (S.time > stageDef.length) stageClear();
    }

    function update(dt) {
      S.t += dt; if (S.bannerT > 0) S.bannerT -= dt; if (S.shake > 0) S.shake -= dt; if (flash > 0) flash -= dt; S.fade += Math.sign(0 - S.fade) * Math.min(Math.abs(S.fade), dt * 3);
      const I = G2.input;
      if (S.mode === 'title') { if (S.menus[0]) S.menus[0].update(); return; }
      if (S.mode === 'over') { S.overT += dt; if (S.overT > 0.8 && I.pressed('action')) startStage(S.stage, true); return; }
      if (S.mode === 'clear') { S.overT += dt; if (S.overT > 1.2 && I.pressed('action')) { if (S.stage + 1 < data.stages.length) startStage(S.stage + 1, true); else { S.mode = 'end'; S.overT = 0; } } return; }
      if (S.mode === 'end') { S.overT += dt; if (S.overT > 0.8 && I.pressed('action')) titleMenu(); return; }
      S.time += dt; P.inv = Math.max(0, P.inv - dt);
      if (runner) updateRunner(dt); else updateShooter(dt);
    }

    function render() {
      const c = G2.screen.begin(), t = S.t, theme = (stageDef && stageDef.theme === 'sky' ? 'sunset' : stageDef && stageDef.theme === 'cave' ? 'dungeon' : stageDef && stageDef.theme === 'sea' ? 'sea' : stageDef && stageDef.theme === 'forest' ? 'forest' : stageDef && stageDef.theme === 'city' ? 'city' : stageDef && stageDef.theme === 'desert' ? 'desert' : 'space');
      if (S.mode === 'title') { G2.art.parallax(c, 'space', t * 80, W, H, t); c.textAlign = 'center'; c.textBaseline = 'middle'; c.font = G2.font(36, true); c.fillStyle = '#fff'; c.shadowColor = '#000'; c.shadowBlur = 8; c.fillText(spec.title, W / 2, 100); c.shadowBlur = 0; c.font = G2.font(15); c.fillStyle = 'rgba(255,255,255,0.85)'; c.fillText(String(spec.description || '').slice(0, 90), W / 2, 150); playerShape(c, pl.ship, pl.appearance, 140 + Math.sin(t * 2) * 10, 190, t, false); S.menus.forEach((m) => m.draw(c)); G2.screen.end(); return; }
      c.save(); if (S.shake > 0) c.translate((Math.random() - 0.5) * 6, (Math.random() - 0.5) * 6);
      G2.art.parallax(c, theme, runner ? S.cam : S.time * stageDef.speed, W, H, t);
      if (runner) { // chão com buracos
        c.fillStyle = G2.theme(theme).ground; c.fillRect(0, GROUND + 20, W, H); c.fillStyle = G2.theme(theme).grass; c.fillRect(0, GROUND + 20, W, 8);
        obstacles.filter((o) => o.type === 'pit').forEach((o) => { c.fillStyle = '#05060c'; c.fillRect(o.x - o.w / 2, GROUND + 20, o.w, H); });
        obstacles.forEach((o) => { if (o.type === 'rock') G2.art.poly(c, [[o.x - 15, GROUND + 20], [o.x - 10, GROUND - 6], [o.x + 5, GROUND - 12], [o.x + 15, GROUND + 20]], '#7a7f8a'); else if (o.type === 'crate') { G2.art.rect(c, o.x - 19, GROUND - 32, 38, 52, '#a0703a'); c.strokeStyle = '#6a4528'; c.lineWidth = 3; c.strokeRect(o.x - 19, GROUND - 32, 38, 52); c.beginPath(); c.moveTo(o.x - 19, GROUND - 32); c.lineTo(o.x + 19, GROUND + 20); c.moveTo(o.x + 19, GROUND - 32); c.lineTo(o.x - 19, GROUND + 20); c.stroke(); } else if (o.type === 'flyer') G2.SS.enemyShape(c, 'bird', o.x, o.y + Math.sin(t * 4 + o.ph) * 4, 38, '#c0506f', t); });
        pickups.forEach((p) => { c.fillStyle = '#ffd166'; c.beginPath(); c.ellipse(p.x, p.y, 3 + 5 * Math.abs(Math.sin(t * 5 + p.x * 0.05)), 8, 0, 0, 6.28); c.fill(); });
        if (!P.dead && !(P.inv > 0 && Math.floor(t * 16) % 2 === 0)) G2.art.sprite(c, pl.appearance, P.x, P.y + 22 - (P.slide > 0 ? 4 : 0), P.slide > 0 ? 26 : 40, { dir: 'right', frame: t * 16, walking: P.ground && P.slide <= 0, hop: 0 });
      } else {
        pickups.forEach((p) => { const col = { power: '#ff9f43', shield: '#6ab0ff', heart: '#ff4d6d', coin: '#ffd166' }[p.type]; G2.art.circ(c, p.x, p.y, 10, col); c.font = G2.font(12, true); c.fillStyle = '#000'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText({ power: 'P', shield: 'S', heart: '♥', coin: '●' }[p.type], p.x, p.y + 1); });
        enemies.forEach((e) => enemyShape(c, e.def.shape, e.x, e.y, 38, e.def.color, t + e.ph));
        if (boss) { enemyShape(c, 'ship', boss.x, boss.y, 150, boss.def.color, t); c.save(); c.translate(boss.x, boss.y); c.scale(-1, 1); c.restore(); if (flash > 0) { c.fillStyle = 'rgba(255,255,255,0.35)'; c.fillRect(boss.x - 70, boss.y - 50, 120, 100); } }
        bullets.forEach((b) => G2.art.rect(c, b.x - 6, b.y - 2, 12, 4, '#fff6a8')); ebullets.forEach((b) => G2.art.circ(c, b.x, b.y, 4.5, '#ff6b6b'));
        if (!P.dead) { playerShape(c, pl.ship, pl.appearance, P.x, P.y, t, P.inv > 0); if (P.shield > 0) { c.strokeStyle = 'rgba(106,176,255,0.8)'; c.lineWidth = 2; c.beginPath(); c.arc(P.x, P.y, 26, 0, 6.28); c.stroke(); } }
      }
      c.restore();
      for (let i = 0; i < pl.hp; i++) G2.art.heart(c, 22 + i * 26, 12, 20, i < S.hp);
      c.font = G2.font(15, true); c.textBaseline = 'top'; c.textAlign = 'left'; c.fillStyle = '#fff'; c.fillText(T('Pontos ', 'Score ') + S.score, 14, 38); c.textAlign = 'right'; c.fillText(stageDef.name + (runner ? '' : '  P' + P.power), W - 14, 12);
      const prog = runner ? S.time / stageDef.length : S.bossQ ? Math.min(1, S.time / S.bossQ.t) : S.time / stageDef.length; G2.art.rect(c, W - 154, 34, 140, 5, 'rgba(255,255,255,0.2)'); G2.art.rect(c, W - 154, 34, 140 * Math.min(1, prog), 5, accent);
      if (boss) { G2.art.rect(c, W / 2 - 120, H - 22, 240, 8, 'rgba(0,0,0,0.5)'); G2.art.rect(c, W / 2 - 120, H - 22, 240 * boss.hp / boss.max, 8, '#ff4d6d'); }
      if (S.bannerT > 0) { c.save(); c.globalAlpha = Math.min(1, S.bannerT); c.font = G2.font(26, true); c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillStyle = '#fff'; c.shadowColor = '#000'; c.shadowBlur = 8; c.fillText(S.banner, W / 2, 90); c.restore(); }
      if (S.mode === 'clear' || S.mode === 'over' || S.mode === 'end') { const a = Math.min(1, S.overT * 1.5); c.fillStyle = 'rgba(2,3,10,' + 0.7 * a + ')'; c.fillRect(0, 0, W, H); c.globalAlpha = a; c.textAlign = 'center'; c.textBaseline = 'middle'; c.font = G2.font(38, true); c.fillStyle = S.mode === 'over' ? '#ff7a7a' : accent; c.fillText(S.mode === 'over' ? T('Fim de jogo', 'Game over') : S.mode === 'end' ? T('Você venceu!', 'You win!') : T('Fase concluída!', 'Stage clear!'), W / 2, H / 2 - 24); c.font = G2.font(16); c.fillStyle = '#fff';
        if (S.mode === 'end' && data.ending) G2.wrap(c, data.ending, W - 140).forEach((l, i) => c.fillText(l, W / 2, H / 2 + 14 + i * 22)); else c.fillText(T('Pontos: ', 'Score: ') + S.score, W / 2, H / 2 + 14); c.fillText(T('Pressione Espaço', 'Press Space'), W / 2, H - 50); c.globalAlpha = 1; }
      if (S.fade > 0.001) { c.fillStyle = 'rgba(0,0,0,' + S.fade + ')'; c.fillRect(0, 0, W, H); }
      G2.screen.end();
    }
    function pointer(type, x, y) {
      if (S.mode === 'title') { if (S.menus[0]) S.menus[0].pointer(type, x, y); return; }
      if (type === 'down' && S.overT > 0.8 && (S.mode === 'over' || S.mode === 'clear' || S.mode === 'end')) { G2.input.press('Space'); setTimeout(() => G2.input.release('Space'), 50); }
    }
    return { update, render, pointer, begin: titleMenu, getSave: () => ({ stage: S.stage, score: S.score }), state: S, W, H, get world() { return { P, enemies, boss, bullets, ebullets, pickups, obstacles }; } };
  };
})(typeof window !== 'undefined' ? window : globalThis);
