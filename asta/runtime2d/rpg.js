/* ASTA runtime 2D — RPG (estilo RPG Maker): mapas em tiles, eventos com páginas/condições, comandos, batalhas por turnos, loja, menu e save.
   `G2.RPG` traz a matemática pura (testável sem DOM); a interface fica em G2.engines.rpg. */
(function (root) {
  'use strict';
  const G2 = root.G2;
  const SOLID = '#H~T^', TS = 32, W = 672, H = 384, COLS = 21, ROWS = 12;

  // ------------------------------------------------------------------ regras (puras)
  const GROWTH = { warrior: [8, 1, 2, 1.2, 0.5, 0.5], mage: [4, 4, 0.5, 0.5, 2.5, 0.7], rogue: [5, 2, 1.7, 0.7, 0.7, 1.2], cleric: [6, 3, 1, 1, 2, 0.6] }; // hp mp atk def mag spd
  const xpToNext = (lv) => Math.round(12 * Math.pow(lv, 1.55));
  function member(p) {
    return { id: p.id, name: p.name, cls: p.cls, level: p.level, xp: 0, maxhp: p.hp, hp: p.hp, maxmp: p.mp, mp: p.mp, atk: p.atk, def: p.def, mag: p.mag, spd: p.spd, skills: (p.skills || []).slice(), appearance: p.appearance };
  }
  function levelUp(m) {
    const g = GROWTH[m.cls] || GROWTH.warrior; m.level++;
    m.maxhp += Math.round(g[0]); m.maxmp += Math.round(g[1]); m.atk += Math.round(g[2]); m.def += Math.round(g[3]); m.mag += Math.round(g[4]); m.spd += Math.round(g[5]);
    m.hp = Math.min(m.maxhp, m.hp + Math.round(g[0])); m.mp = Math.min(m.maxmp, m.mp + Math.round(g[1]));
  }
  function gainXp(m, xp) { const out = []; m.xp += xp; while (m.xp >= xpToNext(m.level) && m.level < 50) { m.xp -= xpToNext(m.level); levelUp(m); out.push(m.level); } return out; }
  const jitter = (rnd, lo, hi) => lo + (hi - lo) * rnd();
  function physDamage(atk, def, rnd, defending, crit) { let d = atk * jitter(rnd, 0.9, 1.1) - def * 0.5; if (crit) d *= 1.6; if (defending) d *= 0.5; return Math.max(1, Math.round(d)); }
  function skillAmount(skill, user, target, rnd, defending) {
    const stat = skill.stat === 'atk' ? user.atk : user.mag;
    if (skill.kind === 'heal') return Math.round(skill.power * stat * jitter(rnd, 0.9, 1.1)) + 5;
    let d = skill.power * stat * jitter(rnd, 0.9, 1.1) - target.def * 0.4; if (defending) d *= 0.5; return Math.max(1, Math.round(d));
  }
  function enemyInstance(id, def) { return { id, name: def.name, hp: def.hp, maxhp: def.hp, atk: def.atk, def: def.def, spd: def.spd, xp: def.xp, gold: def.gold, color: def.color, shape: def.shape, boss: !!def.boss, alive: true }; }
  const fleeChance = (party, foes, boss) => (boss ? 0 : G2.clamp(0.5 + (avg(party, 'spd') - avg(foes, 'spd')) * 0.04, 0.25, 0.9));
  function avg(list, k) { return list.length ? list.reduce((a, b) => a + b[k], 0) / list.length : 0; }
  G2.RPG = { GROWTH, xpToNext, member, levelUp, gainXp, physDamage, skillAmount, enemyInstance, fleeChance, SOLID };

  // ------------------------------------------------------------------ arte dos tiles
  const BASE = { g1: '#5aa05a', g2: '#4f9150', dirt: '#b08a5a', floor: '#8f6c46', stone: '#7d8290', wall: '#4d5262', tree: '#2f7a45', trunk: '#5a3b25', water: '#3b78d0', sand: '#dfc98a', roof: '#a8453a', hwall: '#dccaa4' };
  const THEME_PAL = {
    grass: {}, forest: { g1: '#3f8a4f', g2: '#367a45', tree: '#256a3a' }, snow: { g1: '#eef4fa', g2: '#dce8f2', tree: '#3f7a5a', dirt: '#b8b0a4', water: '#6fa8d8' }, desert: { g1: '#dfc98a', g2: '#d3b877', tree: '#6a8a3a', dirt: '#c49a62', sand: '#e8d6a0' },
    dungeon: { g1: '#3a4a3a', g2: '#324232', stone: '#5a5666', wall: '#2a2833', floor: '#4a4455' }, cave: { g1: '#4a4a52', g2: '#40404a', stone: '#5e5a66', wall: '#26242c', floor: '#4e4a58', dirt: '#6a5a4a' },
    town: { g1: '#68ad62', g2: '#5c9d58' }, castle: { g1: '#6a8a6a', g2: '#5e7e5e', stone: '#9a9fb0', wall: '#6a6f82', floor: '#8a7a68' },
  };
  const palCache = {};
  const palOf = (theme) => palCache[theme] || (palCache[theme] = Object.assign({}, BASE, THEME_PAL[theme] || {}));
  function drawTile(c, ch, x, y, tx, ty, P, rows, t) {
    const s = TS, r = G2.art.cellRand(tx, ty), A = G2.art;
    const fill = (col) => { c.fillStyle = col; c.fillRect(x, y, s, s); };
    const grass = () => { fill((tx + ty) % 2 ? P.g1 : P.g2); c.strokeStyle = G2.shade(P.g1, -0.2); c.lineWidth = 1.4; for (let i = 0; i < 3; i++) { const bx = x + 4 + ((r * 97 * (i + 1)) % 24), by = y + 6 + ((r * 53 * (i + 2)) % 20); c.beginPath(); c.moveTo(bx, by); c.lineTo(bx - 1.5, by - 4); c.moveTo(bx, by); c.lineTo(bx + 1.5, by - 4); c.stroke(); } };
    switch (ch) {
      case ',': fill(P.dirt); c.fillStyle = G2.shade(P.dirt, -0.18); for (let i = 0; i < 4; i++) c.fillRect(x + ((r * 211 * (i + 1)) % 28), y + ((r * 131 * (i + 2)) % 28), 3, 2); break;
      case '=': fill(P.floor); c.fillStyle = G2.shade(P.floor, -0.25); for (let i = 1; i < 4; i++) c.fillRect(x, y + i * 8 - 1, s, 1.5); c.fillRect(x + ((tx * 13) % 24) + 2, y, 1.5, 8); break;
      case '_': fill(P.stone); c.strokeStyle = G2.shade(P.stone, -0.3); c.lineWidth = 1; c.strokeRect(x + 0.5, y + 0.5, s - 1, s - 1); c.fillStyle = G2.shade(P.stone, 0.12); c.fillRect(x + 4 + (r * 40) % 18, y + 5 + (r * 90) % 18, 3, 2); break;
      case '#': fill(P.wall); c.fillStyle = G2.shade(P.wall, 0.15); c.fillRect(x, y, s, 3); c.strokeStyle = G2.shade(P.wall, -0.35); c.lineWidth = 1; for (let i = 0; i < 3; i++) { const yy = y + 4 + i * 9; c.beginPath(); c.moveTo(x, yy); c.lineTo(x + s, yy); c.stroke(); const o = i % 2 ? 8 : 16; c.beginPath(); c.moveTo(x + o, yy); c.lineTo(x + o, yy + 9); c.moveTo(x + o + 16, yy); c.lineTo(x + o + 16, yy + 9); c.stroke(); } break;
      case 'H': {
        const above = ty > 0 ? rows[ty - 1][tx] : '.', left = tx > 0 ? rows[ty][tx - 1] : '.', right = tx + 1 < rows[ty].length ? rows[ty][tx + 1] : '.';
        if (above !== 'H' && above !== 'D') { fill(P.roof); c.fillStyle = G2.shade(P.roof, -0.25); for (let i = 0; i < 4; i++) c.fillRect(x, y + 6 + i * 8, s, 1.6); if (left !== 'H') c.fillRect(x, y, 3, s); if (right !== 'H') c.fillRect(x + s - 3, y, 3, s); } else { fill(P.hwall); c.fillStyle = G2.shade(P.hwall, -0.12); c.fillRect(x, y + s - 4, s, 4); if ((tx + ty) % 2 === 0) { c.fillStyle = '#9fd0ff'; c.fillRect(x + 8, y + 7, 16, 14); c.strokeStyle = '#5a3b25'; c.lineWidth = 2; c.strokeRect(x + 8, y + 7, 16, 14); c.beginPath(); c.moveTo(x + 16, y + 7); c.lineTo(x + 16, y + 21); c.stroke(); } }
        break;
      }
      case 'D': fill(P.hwall); c.fillStyle = '#6a4528'; G2.rrect(c, x + 6, y + 3, s - 12, s - 3, 3); c.fill(); c.fillStyle = '#7e5532'; c.fillRect(x + 9, y + 6, s - 18, s - 6); c.fillStyle = '#ffd166'; c.beginPath(); c.arc(x + s - 12, y + 18, 2, 0, 6.28); c.fill(); break;
      case '~': { fill(P.water); c.strokeStyle = 'rgba(255,255,255,0.35)'; c.lineWidth = 1.5; for (let i = 0; i < 2; i++) { c.beginPath(); const yy = y + 9 + i * 14; for (let k = 0; k <= s; k += 4) c.lineTo(x + k, yy + Math.sin(k * 0.3 + t * 2 + tx + i * 2) * 1.6); c.stroke(); } break; }
      case 'T': grass(); c.fillStyle = 'rgba(0,0,0,0.2)'; c.beginPath(); c.ellipse(x + 16, y + 28, 11, 4, 0, 0, 6.28); c.fill(); c.fillStyle = P.trunk; c.fillRect(x + 13, y + 18, 6, 11); c.fillStyle = P.tree; c.beginPath(); c.arc(x + 16, y + 12, 12, 0, 6.28); c.fill(); c.fillStyle = G2.shade(P.tree, 0.18); c.beginPath(); c.arc(x + 12, y + 9, 6, 0, 6.28); c.fill(); break;
      case '^': grass(); c.fillStyle = '#7a7f8a'; c.beginPath(); c.moveTo(x, y + s); c.lineTo(x + 16, y + 2); c.lineTo(x + s, y + s); c.fill(); c.fillStyle = '#9aa0ab'; c.beginPath(); c.moveTo(x + 16, y + 2); c.lineTo(x + s, y + s); c.lineTo(x + 20, y + s); c.fill(); c.fillStyle = '#fff'; c.beginPath(); c.moveTo(x + 11, y + 11); c.lineTo(x + 16, y + 2); c.lineTo(x + 21, y + 11); c.fill(); break;
      case 'S': fill(P.sand); c.fillStyle = G2.shade(P.sand, -0.12); for (let i = 0; i < 4; i++) c.fillRect(x + ((r * 173 * (i + 1)) % 28), y + ((r * 79 * (i + 2)) % 28), 2, 2); break;
      case 'B': fill(P.water); c.fillStyle = '#8a5a35'; c.fillRect(x, y + 2, s, s - 4); c.fillStyle = '#6a4528'; for (let i = 0; i < 4; i++) c.fillRect(x, y + 3 + i * 7, s, 1.6); c.fillRect(x, y + 2, s, 2); c.fillRect(x, y + s - 4, s, 2); break;
      case 'F': grass(); for (let i = 0; i < 3; i++) { c.fillStyle = ['#ff7aa8', '#ffe066', '#ffffff', '#b28dff'][Math.floor(r * 10 + i) % 4]; c.beginPath(); c.arc(x + 7 + ((r * 191 * (i + 1)) % 20), y + 8 + ((r * 83 * (i + 2)) % 18), 2.4, 0, 6.28); c.fill(); } break;
      default: grass();
    }
    void A;
  }

  const ListMenu = G2.ListMenu;

  // ------------------------------------------------------------------ motor
  G2.engines.rpg = function (spec) {
    const data = spec.data, T = G2.t, th = G2.theme(spec.style.theme), accent = spec.style.accent || th.accent;
    const dlg = new G2.Dialog({ x: 12, w: W - 24, h: 96, font: 17, speed: 56, accent });
    const S = { t: 0, mode: 'title', map: '', px: 0, py: 0, dir: 'down', mv: null, party: [], inv: {}, gold: 0, vars: JSON.parse(JSON.stringify(data.variables || {})), removed: {}, steps: 0, safe: 0, fade: 0, fadeTarget: 0, menus: [], toast: '', toastT: 0, banner: '', bannerT: 0, timers: [], busy: false, battle: null, autoRan: {}, end: null, walk: 0, evTurn: {} };
    G2.screen.letterbox = '#000';
    const mapOf = (id) => data.maps[id];
    const say = (who, text) => new Promise((res) => dlg.show(who, G2.fmt(text, S.vars), res));
    const choose = (opts) => new Promise((res) => dlg.choose('', opts.map((o) => ({ label: G2.fmt(o, S.vars) })), res));
    const wait = (sec) => new Promise((res) => S.timers.push({ t: sec, res }));
    const toast = (msg) => { S.toast = msg; S.toastT = 2.2; };
    const fade = async (to, sec) => { S.fadeTarget = to; S.fadeSpeed = 1 / (sec || 0.25); await wait((sec || 0.25) + 0.02); };

    // ----- estado do mundo
    function newGame() {
      S.party = data.start_party.map((id) => member(data.party.find((p) => p.id === id))); S.inv = {}; S.gold = 0; S.vars = JSON.parse(JSON.stringify(data.variables || {})); S.removed = {}; S.steps = 0; S.autoRan = {}; S.end = null;
      S.map = data.start.map; S.px = data.start.x; S.py = data.start.y; S.dir = 'down'; S.mv = null; S.mode = 'map'; S.banner = mapOf(S.map).name; S.bannerT = 2.5;
      G2.audio.music(mapOf(S.map).music, spec.audio.music.scale, spec.audio.music.tempo); autoEvents();
    }
    function snapshot() { return { map: S.map, px: S.px, py: S.py, dir: S.dir, party: JSON.parse(JSON.stringify(S.party)), inv: S.inv, gold: S.gold, vars: S.vars, removed: S.removed, steps: S.steps, t: Date.now(), place: mapOf(S.map).name }; }
    function load(s) {
      S.party = JSON.parse(JSON.stringify(s.party)); S.inv = Object.assign({}, s.inv); S.gold = s.gold; S.vars = Object.assign({}, s.vars); S.removed = Object.assign({}, s.removed); S.steps = s.steps || 0;
      S.map = s.map; S.px = s.px; S.py = s.py; S.dir = s.dir || 'down'; S.mv = null; S.mode = 'map'; S.menus = []; S.battle = null; S.end = null; S.autoRan = {}; dlg.close(); S.banner = mapOf(S.map).name; S.bannerT = 2;
      G2.audio.music(mapOf(S.map).music, spec.audio.music.scale, spec.audio.music.tempo);
    }
    const slots = ['rpg_slot1', 'rpg_slot2', 'rpg_slot3'];
    const autosave = () => G2.save.set('rpg_auto', snapshot());
    const addItem = (id, n) => { S.inv[id] = Math.max(0, (S.inv[id] || 0) + n); if (!S.inv[id]) delete S.inv[id]; };

    // ----- eventos
    const evKey = (e) => S.map + ':' + e.id;
    const liveEvents = () => mapOf(S.map).events.filter((e) => !S.removed[evKey(e)]);
    const pageOf = (e) => e.pages.find((p) => G2.cond(p.if, S.vars));
    const eventAt = (x, y) => liveEvents().find((e) => e.x === x && e.y === y && (e.solid || e.trigger === 'touch'));
    const blocked = (x, y) => { const m = mapOf(S.map), rows = m.tiles; if (y < 0 || x < 0 || y >= rows.length || x >= rows[0].length) return true; if (SOLID.indexOf(rows[y][x]) >= 0) return true; const e = liveEvents().find((q) => q.x === x && q.y === y && q.solid); return !!e; };
    async function runEvent(e) {
      if (S.busy) return; S.busy = true; S.mode = 'event';
      try {
        const pg = pageOf(e); const cmds = pg ? pg.commands : [];
        if (e.kind === 'heal' && !cmds.length) { healAll(); G2.audio.sfx('magic'); await say('', T('Seus HP e MP foram restaurados!', 'Your HP and MP were restored!')); }
        else await runCommands(cmds, e);
      } finally { S.busy = false; if (S.mode === 'event') S.mode = 'map'; autosaveSoon(); }
    }
    let saveT = 0; const autosaveSoon = () => { saveT = 1; };
    function autoEvents() { const k = S.map; if (S.autoRan[k]) return; S.autoRan[k] = true; const e = liveEvents().find((q) => q.trigger === 'auto' && pageOf(q) && pageOf(q).commands.length); if (e) setTimeout(() => runEvent(e), 300); }
    function healAll() { S.party.forEach((m) => { m.hp = m.maxhp; m.mp = m.maxmp; }); }
    function removeEvent(e) { if (e) S.removed[evKey(e)] = true; }
    async function warp(map, x, y) {
      await fade(1, 0.22); S.map = map; S.px = x; S.py = y; S.mv = null; S.safe = 4; S.banner = mapOf(map).name; S.bannerT = 2.4; G2.audio.music(mapOf(map).music, spec.audio.music.scale, spec.audio.music.tempo); autosave();
      await fade(0, 0.22); autoEvents();
    }
    async function runCommands(cmds, ev) { for (let i = 0; i < cmds.length; i++) { const r = await exec(cmds[i], ev); if (r === 'stop') return 'stop'; } return ''; }
    async function exec(c, ev) {
      switch (c.c) {
        case 'say': await say(c.who, c.text); break;
        case 'choice': { const i = await choose(c.options.map((o) => o.text)); return runCommands(c.options[i].do, ev); }
        case 'set': G2.applySet(S.vars, c); break;
        case 'item': addItem(c.id, c.n); toast((c.n > 0 ? T('Obteve ', 'Got ') : T('Perdeu ', 'Lost ')) + Math.abs(c.n) + '× ' + data.items[c.id].name); if (c.n > 0) G2.audio.sfx('coin'); break;
        case 'gold': S.gold = Math.max(0, S.gold + c.n); if (c.n > 0) toast('+' + c.n + ' ' + T('moedas', 'gold')); break;
        case 'heal': healAll(); G2.audio.sfx('magic'); break;
        case 'warp': await warp(c.map, c.x, c.y); break;
        case 'recruit': { if (!S.party.find((m) => m.id === c.id) && S.party.length < 4) { const p = data.party.find((q) => q.id === c.id); const lead = S.party[0]; const m = member(p); while (m.level < lead.level) levelUp(m); S.party.push(m); G2.audio.sfx('powerup'); toast(m.name + T(' entrou no grupo!', ' joined the party!')); } break; }
        case 'remove': removeEvent(ev); break;
        case 'if': return runCommands(G2.cond(c.cond, S.vars) ? c.then : c.else, ev);
        case 'sfx': G2.audio.sfx(c.name); break;
        case 'shop': await shop(c.items); break;
        case 'battle': {
          const res = await battle(c.enemies, c.boss);
          if (res === 'win') { if (ev && ev.kind === 'enemy') removeEvent(ev); autosave(); return runCommands(c.win, ev); }
          if (res === 'lose') { if (c.lose === 'continue') { S.party.forEach((m) => { m.hp = Math.max(1, Math.round(m.maxhp / 2)); }); return 'stop'; } await gameOver(); return 'stop'; }
          break;
        }
        case 'end': await victory(c.title); return 'stop';
        default: break;
      }
      return '';
    }
    function victory(title) { S.mode = 'end'; S.end = { title: title || T('Você venceu!', 'You win!'), t: 0 }; G2.audio.sfx('powerup'); return new Promise(() => {}); }
    function gameOver() { S.mode = 'over'; S.end = { t: 0 }; G2.audio.music('stop'); return new Promise(() => {}); }

    // ----- loja
    function shop(ids) {
      return new Promise((res) => {
        const mk = () => ({ x: 14, y: 14, w: 330, maxRows: 8, title: T('Loja', 'Shop') + ' — ' + S.gold + ' ' + T('moedas', 'gold'), entries: ids.map((id) => ({ label: data.items[id].name, right: data.items[id].price + '', disabled: S.gold < data.items[id].price })).concat([{ label: T('Sair', 'Leave') }]),
          onPick: (i) => { if (i === ids.length) { S.menus.pop(); res(); return; } const it = data.items[ids[i]]; S.gold -= it.price; addItem(ids[i], 1); G2.audio.sfx('coin'); toast(T('Comprou ', 'Bought ') + it.name); const m = new ListMenu(mk()); m.sel = i; S.menus[S.menus.length - 1] = m; }, onCancel: () => { S.menus.pop(); res(); } });
        S.menus.push(new ListMenu(mk()));
      });
    }

    // ----- batalha
    const rnd = Math.random;
    function battle(ids, boss) {
      return new Promise(async (resolve) => {
        await fade(1, 0.18); G2.audio.sfx('hit');
        const foes = ids.map((id) => enemyInstance(id, data.enemies[id])), isBoss = !!boss || foes.some((f) => f.boss);
        const B = (S.battle = { foes, boss: isBoss, phase: 'input', actor: 0, actions: [], queue: [], msg: '', msgT: 0, menu: null, fx: [], over: '', t: 0, resolve });
        S.mode = 'battle'; G2.audio.music(isBoss ? 'epic' : 'tense', spec.audio.music.scale, 120); await fade(0, 0.2);
        B.msg = foes.length > 1 ? T('Inimigos apareceram!', 'Enemies appeared!') : foes[0].name + T(' apareceu!', ' appeared!'); B.msgT = 1.2;
        nextActor();
      });
    }
    const aliveParty = () => S.party.filter((m) => m.hp > 0);
    const aliveFoes = () => S.battle.foes.filter((f) => f.alive);
    function nextActor() {
      const B = S.battle; while (B.actor < S.party.length && S.party[B.actor].hp <= 0) B.actor++;
      if (B.actor >= S.party.length) return runRound();
      commandMenu(S.party[B.actor]);
    }
    function pickTarget(kind, cb) { // kind: enemy | ally
      const B = S.battle; const list = kind === 'enemy' ? aliveFoes().map((f) => ({ label: f.name + ' (' + f.hp + ')', ref: f })) : S.party.map((m) => ({ label: m.name + ' (' + m.hp + '/' + m.maxhp + ')', ref: m, disabled: false }));
      B.menu = new ListMenu({ x: 12, y: 190, w: 250, title: T('Alvo', 'Target'), entries: list, onPick: (i) => { B.menu = null; cb(list[i].ref); }, onCancel: () => { B.menu = null; commandMenu(S.party[B.actor]); } });
    }
    function commandMenu(m) {
      const B = S.battle; const entries = [{ label: T('Atacar', 'Attack') }, { label: T('Habilidades', 'Skills'), disabled: !m.skills.length }, { label: T('Itens', 'Items'), disabled: !Object.keys(S.inv).some((id) => data.items[id].kind !== 'key') }, { label: T('Defender', 'Defend') }, { label: T('Fugir', 'Run'), disabled: B.boss }];
      B.menu = new ListMenu({ x: 12, y: 232, w: 170, title: m.name, entries, onPick: (i) => {
        if (i === 0) { B.menu = null; pickTarget('enemy', (t) => queue({ kind: 'attack', actor: m, target: t })); }
        else if (i === 1) skillMenu(m); else if (i === 2) itemMenu(m);
        else if (i === 3) { B.menu = null; queue({ kind: 'defend', actor: m }); } else { B.menu = null; queue({ kind: 'flee', actor: m }); } } });
    }
    function skillMenu(m) {
      const B = S.battle, list = m.skills.map((id) => ({ id, s: data.skills[id] })).filter((x) => x.s);
      B.menu = new ListMenu({ x: 12, y: 160, w: 260, title: T('Habilidades', 'Skills'), entries: list.map((x) => ({ label: x.s.name, right: x.s.mp + ' MP', disabled: m.mp < x.s.mp })),
        onPick: (i) => { const sk = list[i].s, go = (t) => { B.menu = null; queue({ kind: 'skill', actor: m, skill: sk, target: t }); };
          if (sk.target === 'all_enemies' || sk.target === 'all_allies') go(null); else pickTarget(sk.target === 'ally' ? 'ally' : 'enemy', go); }, onCancel: () => commandMenu(m) });
    }
    function itemMenu(m) {
      const B = S.battle, list = Object.keys(S.inv).filter((id) => data.items[id].kind !== 'key');
      B.menu = new ListMenu({ x: 12, y: 160, w: 270, title: T('Itens', 'Items'), entries: list.map((id) => ({ label: data.items[id].name, right: '×' + S.inv[id] })),
        onPick: (i) => { const id = list[i]; pickTarget('ally', (t) => { B.menu = null; queue({ kind: 'item', actor: m, item: id, target: t }); }); }, onCancel: () => commandMenu(m) });
    }
    function queue(a) { const B = S.battle; B.menu = null; B.actions.push(a); B.actor++; nextActor(); }
    function runRound() {
      const B = S.battle, defend = {}; B.actions.forEach((a) => { if (a.kind === 'defend') defend[a.actor.id] = true; }); B.defend = defend;
      aliveFoes().forEach((f) => B.actions.push({ kind: 'foe', actor: f }));
      B.actions.sort((a, b) => (b.actor.spd + (b.kind === 'defend' ? 99 : 0) + rnd() * 3) - (a.actor.spd + (a.kind === 'defend' ? 99 : 0) + rnd() * 3));
      B.queue = B.actions; B.actions = []; B.phase = 'run'; B.step = 0.4;
    }
    function fx(kind, who, val) { S.battle.fx.push({ kind, who, val, t: 0 }); }
    function say2(text, ms) { const B = S.battle; B.msg = text; B.msgT = ms || 0.9; B.step = (ms || 0.9) + 0.15; }
    function exeAction(a) {
      const B = S.battle, I = a.actor;
      if (I.hp !== undefined && I.hp <= 0) return false; if (I.alive === false) return false;
      if (a.kind === 'defend') { say2(I.name + T(' se defende.', ' defends.'), 0.6); return true; }
      if (a.kind === 'flee') {
        if (rnd() < fleeChance(aliveParty(), aliveFoes(), B.boss)) { say2(T('Vocês fugiram!', 'You got away!'), 0.9); B.over = 'fled'; } else say2(T('Não conseguiu fugir!', "Couldn't escape!"), 0.8); return true;
      }
      if (a.kind === 'item') { const it = data.items[a.item]; if (!S.inv[a.item]) return false; addItem(a.item, -1); const t = a.target; if (it.kind === 'heal_hp') { t.hp = Math.min(t.maxhp, t.hp + it.amount); fx('heal', t, it.amount); } else if (it.kind === 'heal_mp') t.mp = Math.min(t.maxmp, t.mp + it.amount); G2.audio.sfx('magic'); say2(I.name + T(' usou ', ' used ') + it.name + '.', 0.8); return true; }
      if (a.kind === 'attack') {
        let t = a.target; if (!t.alive) t = aliveFoes()[0]; if (!t) return false; const crit = rnd() < 0.08, d = physDamage(I.atk, t.def, rnd, false, crit);
        t.hp -= d; fx('dmg', t, d); G2.audio.sfx('hit'); if (t.hp <= 0) { t.hp = 0; t.alive = false; fx('die', t); }
        say2(I.name + T(' ataca! ', ' attacks! ') + (crit ? T('Crítico! ', 'Critical! ') : '') + t.name + ' −' + d, 0.85); return true;
      }
      if (a.kind === 'skill') {
        const sk = a.skill; if (I.mp < sk.mp) { say2(T('MP insuficiente!', 'Not enough MP!'), 0.7); return true; } I.mp -= sk.mp; G2.audio.sfx('magic');
        const targets = sk.target === 'all_enemies' ? aliveFoes() : sk.target === 'all_allies' ? aliveParty() : [a.target && (a.target.alive === false ? aliveFoes()[0] : a.target)].filter(Boolean);
        targets.forEach((t) => { const v = skillAmount(sk, I, t, rnd, B.defend[t.id]); if (sk.kind === 'heal') { t.hp = Math.min(t.maxhp, t.hp + v); fx('heal', t, v); } else { t.hp -= v; fx('dmg', t, v); if (t.hp <= 0) { t.hp = 0; t.alive = false; fx('die', t); } } });
        say2(I.name + ' → ' + sk.name + '!', 0.9); return true;
      }
      if (a.kind === 'foe') {
        const tg = aliveParty(); if (!tg.length) return false; const t = tg[Math.floor(rnd() * tg.length)], d = physDamage(I.atk, t.def, rnd, !!B.defend[t.id], rnd() < 0.05);
        t.hp = Math.max(0, t.hp - d); fx('dmg', t, d); B.shake = 0.25; G2.audio.sfx('hit'); say2(I.name + T(' ataca ', ' attacks ') + t.name + '! −' + d, 0.85); if (t.hp <= 0) fx('die', t); return true;
      }
      return false;
    }
    function endBattle(result) {
      const B = S.battle;
      const finish = async () => { S.battle = null; S.mode = 'event'; await fade(1, 0.15); S.mode = 'map'; G2.audio.music(mapOf(S.map).music, spec.audio.music.scale, spec.audio.music.tempo); await fade(0, 0.2); S.safe = 5; B.resolve(result); };
      if (result === 'win') {
        const xp = B.foes.reduce((a, f) => a + f.xp, 0), gold = B.foes.reduce((a, f) => a + f.gold, 0), alive = aliveParty(), share = Math.max(1, Math.ceil(xp / Math.max(1, alive.length)));
        S.gold += gold; const lines = [T('Vitória!', 'Victory!') + ' +' + xp + ' XP, +' + gold + ' ' + T('moedas', 'gold')]; G2.audio.sfx('powerup');
        alive.forEach((m) => { gainXp(m, share).forEach((lv) => lines.push(m.name + T(' subiu para o nível ', ' reached level ') + lv + '!')); });
        B.phase = 'result'; B.lines = lines; B.msg = lines.shift(); B.msgT = 99; B.after = () => { if (B.lines.length) { B.msg = B.lines.shift(); G2.audio.sfx('chime'); } else finish(); };
      } else if (result === 'fled') finish(); else finish();
    }
    function battleUpdate(dt) {
      const B = S.battle; B.t += dt; if (B.msgT > 0) B.msgT -= dt; if (B.shake > 0) B.shake -= dt; B.fx.forEach((f) => (f.t += dt)); B.fx = B.fx.filter((f) => f.t < 1.2 || f.kind === 'die');
      if (B.menu) { B.menu.update(); return; }
      if (B.phase === 'run') {
        B.step -= dt; if (B.step > 0) return;
        if (B.over) return endBattle(B.over);
        if (!aliveFoes().length) return endBattle('win'); if (!aliveParty().length) { return (async () => { S.battle = null; await fade(1, 0.2); B.resolve('lose'); })(); }
        const a = B.queue.shift(); if (!a) { B.phase = 'input'; B.actor = 0; B.defend = {}; return nextActor(); }
        if (!exeAction(a)) B.step = 0.02; return;
      }
      if (B.phase === 'result' && (G2.input.pressed('action') || G2.input.pressed('cancel') || B.clicked)) { B.clicked = false; G2.audio.sfx('select'); B.after(); }
    }
    function battleDraw(c) {
      const B = S.battle, t = B.t, theme = mapOf(S.map).theme; const P = palOf(theme === 'town' ? 'grass' : theme);
      c.save(); if (B.shake > 0) c.translate((rnd() - 0.5) * 8, (rnd() - 0.5) * 6);
      c.fillStyle = G2.art.grad(c, 0, 0, 0, H, [[0, G2.shade(P.g1, -0.55)], [0.55, G2.shade(P.g2, -0.2)], [1, G2.shade(P.g1, -0.5)]]); c.fillRect(0, 0, W, H);
      const n = B.foes.length; B.foes.forEach((f, i) => {
        const x = W / 2 + (i - (n - 1) / 2) * 120, y = 105, dead = !f.alive, fxd = B.fx.find((q) => q.kind === 'die' && q.who === f);
        if (dead) { const k = fxd ? Math.max(0, 1 - fxd.t * 2.2) : 0; if (k <= 0) return; c.globalAlpha = k; }
        G2.art.monster(c, f.shape, x, y, f.boss ? 150 : 96, f.color, t + i, B.fx.some((q) => q.kind === 'dmg' && q.who === f && q.t < 0.25)); c.globalAlpha = 1;
        if (!dead) { G2.art.rect(c, x - 34, y + (f.boss ? 82 : 56), 68, 6, 'rgba(0,0,0,0.5)'); G2.art.rect(c, x - 34, y + (f.boss ? 82 : 56), 68 * f.hp / f.maxhp, 6, f.hp / f.maxhp > 0.35 ? '#5fd68a' : '#ff5a5a'); c.font = G2.font(12); c.fillStyle = '#fff'; c.textAlign = 'center'; c.fillText(f.name, x, y + (f.boss ? 100 : 74)); }
      });
      // grupo
      const px = W - 262; G2.panel(c, px, 232, 250, 142, { r: 8 }); c.textAlign = 'left'; c.textBaseline = 'top';
      S.party.forEach((m, i) => { const y = 242 + i * 32, cur = B.phase === 'input' && S.party[B.actor] === m; c.font = G2.font(14, true); c.fillStyle = m.hp <= 0 ? '#ff7a7a' : cur ? accent : '#fff'; c.fillText(m.name + '  Lv' + m.level, px + 12, y);
        G2.art.rect(c, px + 130, y + 2, 100, 7, 'rgba(255,255,255,0.15)'); G2.art.rect(c, px + 130, y + 2, 100 * m.hp / m.maxhp, 7, '#5fd68a'); G2.art.rect(c, px + 130, y + 11, 100, 5, 'rgba(255,255,255,0.15)'); G2.art.rect(c, px + 130, y + 11, 100 * m.mp / Math.max(1, m.maxmp), 5, '#6ab0ff'); c.font = G2.font(11); c.fillStyle = '#ddd'; c.fillText(m.hp + '/' + m.maxhp + ' HP', px + 12, y + 17); });
      // efeitos
      B.fx.forEach((f) => { if (f.kind === 'die') return; let x, y; if (f.who.alive !== undefined) { const i = B.foes.indexOf(f.who); x = W / 2 + (i - (n - 1) / 2) * 120; y = 70; } else { const i = S.party.indexOf(f.who); x = px + 190; y = 240 + i * 32; } c.font = G2.font(20, true); c.textAlign = 'center'; c.fillStyle = f.kind === 'heal' ? '#7dffa8' : '#fff'; c.strokeStyle = '#000'; c.lineWidth = 3; const yy = y - f.t * 30; c.strokeText(String(f.val), x, yy); c.fillText(String(f.val), x, yy); });
      c.restore();
      if (B.menu) B.menu.draw(c);
      if (B.msgT > 0 || B.phase === 'result') { G2.panel(c, 12, 12, W - 24, 36, { r: 8 }); c.font = G2.font(16); c.fillStyle = '#fff'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(B.msg, W / 2, 31); if (B.phase === 'result') { c.fillStyle = accent; c.fillText('▼', W - 34, 31); } }
    }

    // ----- mapa
    function tryMove(dx, dy, dir) {
      S.dir = dir; const nx = S.px + dx, ny = S.py + dy;
      const e = liveEvents().find((q) => q.x === nx && q.y === ny);
      if (e && e.trigger === 'touch' && e.solid) { runEvent(e); return; }
      if (blocked(nx, ny)) return;
      S.mv = { fx: S.px, fy: S.py, tx: nx, ty: ny, t: 0 }; S.px = nx; S.py = ny; S.walk++;
      if (S.walk % 2 === 0) G2.audio.sfx('step');
    }
    function arrive() {
      const e = liveEvents().find((q) => q.x === S.px && q.y === S.py && q.trigger === 'touch' && !q.solid);
      if (e && pageOf(e) && pageOf(e).commands.length) { runEvent(e); return; }
      S.steps++; const enc = mapOf(S.map).encounters;
      if (S.safe > 0) { S.safe--; return; }
      if (enc && enc.rate > 0 && enc.groups.length && rnd() < enc.rate) { S.busy = true; S.mode = 'event'; battle(enc.groups[Math.floor(rnd() * enc.groups.length)], false).then((r) => { S.busy = false; if (r === 'lose') gameOver(); else if (S.mode === 'event') S.mode = 'map'; autosaveSoon(); }); }
    }
    function interact() {
      const d = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] }[S.dir], x = S.px + d[0], y = S.py + d[1];
      const e = liveEvents().find((q) => q.x === x && q.y === y && q.trigger === 'action');
      if (e) { if (e.kind === 'npc') S.evTurn[evKey(e)] = { up: 'down', down: 'up', left: 'right', right: 'left' }[S.dir]; runEvent(e); }
    }
    function openMenu() {
      const root = () => ({ x: 14, y: 14, w: 190, title: T('Menu', 'Menu'), entries: [{ label: T('Itens', 'Items') }, { label: T('Equipe', 'Party') }, { label: T('Salvar', 'Save') }, { label: T('Carregar', 'Load') }, { label: T('Voltar', 'Close') }],
        onPick: (i) => { if (i === 0) itemsMenu(); else if (i === 1) statusMenu(); else if (i === 2) slotMenu('save'); else if (i === 3) slotMenu('load'); else closeMenus(); }, onCancel: closeMenus });
      S.menus = [new ListMenu(root())]; S.mode = 'menu';
    }
    function closeMenus() { S.menus = []; S.status = null; if (S.mode === 'menu') S.mode = 'map'; G2.audio.sfx('select'); }
    function itemsMenu() {
      const ids = Object.keys(S.inv), mk = () => new ListMenu({ x: 214, y: 14, w: 300, title: T('Itens', 'Items'), entries: ids.filter((id) => S.inv[id]).map((id) => ({ label: data.items[id].name, right: '×' + S.inv[id], disabled: data.items[id].kind === 'key' })),
        onPick: (i) => { const id = ids.filter((q) => S.inv[q])[i], it = data.items[id]; S.menus.push(new ListMenu({ x: 214, y: 90, w: 260, title: T('Usar em', 'Use on'), entries: S.party.map((m) => ({ label: m.name, right: m.hp + '/' + m.maxhp })), onCancel: () => S.menus.pop(),
          onPick: (j) => { const m = S.party[j]; if (it.kind === 'heal_hp' && m.hp < m.maxhp) { m.hp = Math.min(m.maxhp, m.hp + it.amount); } else if (it.kind === 'heal_mp' && m.mp < m.maxmp) { m.mp = Math.min(m.maxmp, m.mp + it.amount); } else { G2.audio.sfx('error'); return; } addItem(id, -1); G2.audio.sfx('magic'); S.menus.pop(); S.menus[S.menus.length - 1] = mk(); } })); }, onCancel: () => S.menus.pop() });
      S.menus.push(mk());
    }
    function statusMenu() { S.status = 0; S.menus.push(new ListMenu({ x: 214, y: 14, w: 160, title: T('Equipe', 'Party'), entries: S.party.map((m) => ({ label: m.name })), onPick: (i) => { S.status = i; }, onCancel: () => { S.status = null; S.menus.pop(); } })); }
    function slotMenu(mode) {
      const keys = mode === 'load' ? slots.concat(['rpg_auto']) : slots;
      S.menus.push(new ListMenu({ x: 214, y: 14, w: 330, title: mode === 'save' ? T('Salvar', 'Save') : T('Carregar', 'Load'), entries: keys.map((k, i) => { const s = G2.save.get(k); return { label: (k === 'rpg_auto' ? T('Auto', 'Auto') : T('Slot ', 'Slot ') + (i + 1)), right: s ? s.place + ' · Lv' + s.party[0].level : T('vazio', 'empty'), disabled: mode === 'load' && !s }; }),
        onPick: (i) => { const k = keys[i]; if (mode === 'save') { G2.save.set(k, snapshot()); toast(T('Jogo salvo', 'Game saved')); G2.audio.sfx('chime'); S.menus.pop(); } else { load(G2.save.get(k)); } }, onCancel: () => S.menus.pop() }));
    }

    // ----- laço
    function update(dt) {
      S.t += dt; if (S.toastT > 0) S.toastT -= dt; if (S.bannerT > 0) S.bannerT -= dt; if (saveT > 0) { saveT -= dt; if (saveT <= 0 && S.mode === 'map') autosave(); }
      S.fade += Math.sign(S.fadeTarget - S.fade) * Math.min(Math.abs(S.fadeTarget - S.fade), dt * (S.fadeSpeed || 4));
      S.timers.forEach((q) => (q.t -= dt)); const due = S.timers.filter((q) => q.t <= 0); S.timers = S.timers.filter((q) => q.t > 0); due.forEach((q) => q.res());
      const I = G2.input;
      if (S.mode === 'title') { const m = S.menus[0]; if (m) m.update(); return; }
      if (S.mode === 'end' || S.mode === 'over') { S.end.t += dt; if (S.end.t > 0.7 && I.pressed('action')) endChoice(); return; }
      if (S.mode === 'battle' && S.battle) { dlg.update(dt); battleUpdate(dt); return; }
      dlg.update(dt);
      if (dlg.active) return;
      if (S.mode === 'menu') { const m = S.menus[S.menus.length - 1]; if (m) m.update(); else S.mode = 'map'; return; }
      if (S.mode !== 'map') return;
      if (S.mv) {
        S.mv.t += dt / 0.15; if (S.mv.t >= 1) { S.mv = null; arrive(); }
      }
      if (!S.mv && S.mode === 'map') {
        if (I.pressed('action')) return interact();
        if (I.pressed('cancel')) return openMenu();
        const ax = I.axisX(), ay = I.axisY();
        if (ay && !ax) tryMove(0, ay, ay < 0 ? 'up' : 'down'); else if (ax) tryMove(ax, 0, ax < 0 ? 'left' : 'right');
      }
    }
    function endChoice() { if (S.mode === 'over') { const s = G2.save.get('rpg_auto'); if (s) load(s); else newGame(); } else { newGame(); } S.end = null; }
    function titleMenu() {
      const s = G2.save.get('rpg_auto');
      S.menus = [new ListMenu({ x: W / 2 - 110, y: 230, w: 220, entries: [{ label: T('Continuar', 'Continue'), disabled: !s }, { label: T('Novo jogo', 'New game') }], onPick: (i) => { S.menus = []; if (i === 0) load(s); else newGame(); } })];
      if (s) S.menus[0].sel = 0; else S.menus[0].sel = 1; S.mode = 'title';
    }

    // ----- desenho
    function render() {
      const c = G2.screen.begin(), t = S.t;
      if (S.mode === 'title') { c.fillStyle = G2.art.grad(c, 0, 0, 0, H, [[0, th.sky[0]], [1, th.ground]]); c.fillRect(0, 0, W, H); c.textAlign = 'center'; c.textBaseline = 'middle'; c.font = G2.font(40, true); c.fillStyle = '#fff'; c.fillText(spec.title, W / 2, 110); c.font = G2.font(16); c.fillStyle = 'rgba(255,255,255,0.75)'; c.fillText(String(spec.description || '').slice(0, 80), W / 2, 160); S.menus.forEach((m) => m.draw(c)); G2.screen.end(); return; }
      if (S.mode === 'battle' && S.battle) { battleDraw(c); dlg.draw(c, W, H); if (S.fade > 0.001) { c.fillStyle = 'rgba(0,0,0,' + S.fade + ')'; c.fillRect(0, 0, W, H); } G2.screen.end(); return; }
      const m = mapOf(S.map), rows = m.tiles, P = palOf(m.theme), mw = rows[0].length, mh = rows.length;
      let fx = S.px, fy = S.py; if (S.mv) { fx = G2.lerp(S.mv.fx, S.mv.tx, Math.min(1, S.mv.t)); fy = G2.lerp(S.mv.fy, S.mv.ty, Math.min(1, S.mv.t)); }
      const camX = G2.clamp(fx * TS + TS / 2 - W / 2, 0, Math.max(0, mw * TS - W)), camY = G2.clamp(fy * TS + TS / 2 - H / 2, 0, Math.max(0, mh * TS - H));
      c.fillStyle = '#05060c'; c.fillRect(0, 0, W, H); c.save(); c.translate(-Math.round(camX) + (mw * TS < W ? (W - mw * TS) / 2 : 0), -Math.round(camY) + (mh * TS < H ? (H - mh * TS) / 2 : 0));
      const x0 = Math.floor(camX / TS), y0 = Math.floor(camY / TS);
      for (let ty = y0; ty <= Math.min(mh - 1, y0 + ROWS + 1); ty++) for (let tx = x0; tx <= Math.min(mw - 1, x0 + COLS + 1); tx++) drawTile(c, rows[ty][tx], tx * TS, ty * TS, tx, ty, P, rows, t);
      // objetos e personagens ordenados por y
      const drawables = liveEvents().filter((e) => e.kind !== 'warp' && e.kind !== 'trigger').map((e) => ({ y: e.y, e })); drawables.push({ y: fy, player: true }); drawables.sort((a, b) => a.y - b.y);
      drawables.forEach((d) => {
        if (d.player) { const lead = S.party[0]; G2.art.sprite(c, lead.appearance, fx * TS + TS / 2, fy * TS + TS - 2, 30, { dir: S.dir, frame: S.walk + t * 8, walking: !!S.mv }); return; }
        const e = d.e, ex = e.x * TS, ey = e.y * TS;
        if (e.kind === 'npc') G2.art.sprite(c, e.appearance, ex + TS / 2, ey + TS - 2, 30, { dir: S.evTurn[evKey(e)] || 'down', frame: t * 2, hop: Math.max(0, Math.sin(t * 2 + e.x) * 0.5) });
        else if (e.kind === 'chest') { const open = S.vars[e.id + '_open']; G2.art.prop(c, 'chest', ex + 4, ey + 8 + (open ? 3 : 0), 24, 20, t); if (open) { c.fillStyle = 'rgba(0,0,0,0.5)'; c.fillRect(ex + 6, ey + 12, 20, 4); } }
        else if (e.kind === 'sign') G2.art.prop(c, 'sign', ex + 6, ey + 4, 20, 26, t);
        else if (e.kind === 'heal') { c.fillStyle = '#6ab0ff'; c.beginPath(); c.arc(ex + 16, ey + 18, 11, 0, 6.28); c.fill(); c.fillStyle = '#bfe0ff'; c.beginPath(); c.arc(ex + 16, ey + 16, 6, 0, 6.28); c.fill(); c.globalAlpha = 0.5 + 0.5 * Math.sin(t * 4); G2.art.circ(c, ex + 16, ey + 8, 2, '#fff'); c.globalAlpha = 1; }
        else if (e.kind === 'enemy') G2.art.monster(c, 'ghost', ex + 16, ey + 14, 40, '#9b72d0', t, false);
        if (e.icon && e.kind !== 'heal' && e.kind !== 'chest' && e.kind !== 'sign') { c.font = G2.font(18); c.textAlign = 'center'; c.fillText(e.icon, ex + 16, ey + 14); }
      });
      c.restore();
      // sombras de caverna
      if (m.theme === 'cave' || m.theme === 'dungeon') { const g = c.createRadialGradient(W / 2, H / 2, 70, W / 2, H / 2, 280); g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,0.7)'); c.fillStyle = g; c.fillRect(0, 0, W, H); }
      if (S.bannerT > 0) { c.save(); c.globalAlpha = Math.min(1, S.bannerT); c.font = G2.font(18, true); const w = c.measureText(S.banner).width + 40; G2.panel(c, W / 2 - w / 2, 12, w, 34, { r: 17 }); c.fillStyle = '#fff'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(S.banner, W / 2, 30); c.restore(); }
      if (S.toastT > 0) { c.save(); c.font = G2.font(15); const w = c.measureText(S.toast).width + 34; G2.panel(c, W / 2 - w / 2, 56, w, 30, { r: 15 }); c.fillStyle = '#fff'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(S.toast, W / 2, 71); c.restore(); }
      dlg.draw(c, W, H);
      S.menus.forEach((mm) => mm.draw(c));
      if (S.mode === 'menu' && S.status != null) { const p = S.party[S.status] || S.party[0]; G2.panel(c, 388, 14, 270, 230, { r: 8 }); c.save(); c.textAlign = 'left'; c.textBaseline = 'top'; G2.art.sprite(c, p.appearance, 424, 90, 56, { dir: 'down' }); c.font = G2.font(17, true); c.fillStyle = accent; c.fillText(p.name, 462, 30); c.font = G2.font(13); c.fillStyle = '#fff';
        [['Lv', p.level + ' (' + p.xp + '/' + xpToNext(p.level) + ' XP)'], ['HP', p.hp + '/' + p.maxhp], ['MP', p.mp + '/' + p.maxmp], ['ATK', p.atk], ['DEF', p.def], ['MAG', p.mag], ['SPD', p.spd]].forEach((r, i) => { c.fillStyle = 'rgba(255,255,255,0.65)'; c.fillText(r[0], 400, 104 + i * 18); c.fillStyle = '#fff'; c.fillText(String(r[1]), 450, 104 + i * 18); });
        c.fillStyle = 'rgba(255,255,255,0.65)'; c.fillText(T('Moedas', 'Gold') + ': ' + S.gold, 400, 232); c.restore(); }
      if (S.mode === 'end' || S.mode === 'over') { const a = Math.min(1, S.end.t * 1.2); c.fillStyle = 'rgba(2,3,10,' + 0.88 * a + ')'; c.fillRect(0, 0, W, H); c.globalAlpha = a; c.textAlign = 'center'; c.textBaseline = 'middle'; c.font = G2.font(46, true); c.fillStyle = S.mode === 'end' ? accent : '#ff7a7a'; c.fillText(S.mode === 'end' ? S.end.title : T('Fim de jogo', 'Game over'), W / 2, H / 2 - 20); c.font = G2.font(16); c.fillStyle = 'rgba(255,255,255,0.75)'; c.fillText(S.mode === 'end' ? T('Pressione Espaço para jogar de novo', 'Press Space to play again') : T('Pressione Espaço para continuar do último salvamento', 'Press Space to continue from the last save'), W / 2, H / 2 + 36); c.globalAlpha = 1; }
      if (S.fade > 0.001) { c.fillStyle = 'rgba(0,0,0,' + S.fade + ')'; c.fillRect(0, 0, W, H); }
      G2.screen.end();
    }
    function pointer(type, x, y) {
      if (S.mode === 'title' || S.mode === 'menu' || (S.mode === 'battle' && S.battle && S.battle.menu)) { const m = S.mode === 'battle' ? S.battle.menu : S.menus[S.menus.length - 1]; if (m && !dlg.active) m.pointer(type, x, y); return; }
      if (dlg.active) { dlg.pointer(type, x, y); return; }
      if (S.mode === 'end' || S.mode === 'over') { if (type === 'down' && S.end.t > 0.7) endChoice(); return; }
      if (S.mode === 'battle' && S.battle && S.battle.phase === 'result' && type === 'down') { S.battle.clicked = true; return; }
      if (S.mode === 'map' && type === 'down') { // toque: caminhar na direção do toque; toque curto no personagem = interagir/menu
        const cx = W / 2, cy = H / 2, dx = x - cx, dy = y - cy;
        if (Math.abs(dx) < 36 && Math.abs(dy) < 36) { interact(); return; }
        if (!S.mv && !S.busy) { if (Math.abs(dx) > Math.abs(dy)) tryMove(dx < 0 ? -1 : 1, 0, dx < 0 ? 'left' : 'right'); else tryMove(0, dy < 0 ? -1 : 1, dy < 0 ? 'up' : 'down'); }
      }
    }
    function begin() { titleMenu(); }
    return { update, render, pointer, begin, getSave: snapshot, state: S, W, H, _api: { runCommands, newGame } };
  };
})(typeof window !== 'undefined' ? window : globalThis);
