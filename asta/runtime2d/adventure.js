/* ASTA runtime 2D — Point & click: cenas com objetos clicáveis, verbos (olhar, pegar, usar, falar), inventário e itens usados em objetos. */
(function (root) {
  'use strict';
  const G2 = root.G2;
  const W = 800, H = 450, SH = 360; // cena (SH) + barra inferior

  G2.engines.point_and_click = function (spec) {
    const data = spec.data, T = G2.t, accent = spec.style.accent || G2.theme(spec.style.theme).accent;
    const dlg = new G2.Dialog({ x: 20, w: W - 40, h: 92, y: SH - 106, font: 19, speed: 56, accent });
    const S = { t: 0, mode: 'title', scene: '', vars: JSON.parse(JSON.stringify(data.variables || {})), inv: [], sel: '', hover: null, popup: null, fade: 1, fadeTarget: 0, timers: [], menus: [], busy: false, msg: '', msgT: 0, end: null, mouse: { x: 0, y: 0 }, hint: '', seen: {} };
    G2.screen.letterbox = '#000';
    const sceneOf = (id) => data.scenes[id];
    const hidKey = (h) => '__hid_' + S.scene + '_' + h.id;
    const visible = (h) => !S.vars[hidKey(h)] && G2.cond(h.if, S.vars);
    const say = (who, text) => new Promise((res) => dlg.show(who, G2.fmt(text, S.vars), res));
    const choose = (opts) => new Promise((res) => dlg.choose('', opts.map((o) => ({ label: G2.fmt(o, S.vars) })), res));
    const wait = (sec) => new Promise((res) => S.timers.push({ t: sec, res }));
    const toast = (m) => { S.msg = m; S.msgT = 2; };
    const fade = async (to, sec) => { S.fadeTarget = to; S.fadeSpeed = 1 / (sec || 0.25); await wait((sec || 0.25) + 0.02); };

    function newGame() { S.vars = JSON.parse(JSON.stringify(data.variables || {})); S.inv = []; S.sel = ''; S.seen = {}; S.end = null; S.mode = 'play'; enter(data.start, true); }
    function snapshot() { return { scene: S.scene, vars: S.vars, inv: S.inv, seen: S.seen, t: Date.now() }; }
    function load(s) { S.vars = Object.assign({}, s.vars); S.inv = s.inv.slice(); S.seen = Object.assign({}, s.seen); S.end = null; S.mode = 'play'; S.sel = ''; enter(s.scene, false); }
    async function enter(id, first) {
      S.busy = true; if (!first) await fade(1, 0.2); S.scene = id; S.popup = null; S.hover = null; const sc = sceneOf(id);
      G2.audio.music(['calm', 'mysterious', 'tense', 'calm'][Object.keys(data.scenes).indexOf(id) % 4], spec.audio.music.scale, spec.audio.music.tempo);
      await fade(0, 0.25); G2.save.set('pc_auto', snapshot());
      if (!S.seen[id] && sc.intro) { S.seen[id] = true; await say('', sc.intro); }
      S.seen[id] = true; S.busy = false;
    }
    async function runCommands(cmds, h) { for (let i = 0; i < cmds.length; i++) { const r = await exec(cmds[i], h); if (r === 'stop') return 'stop'; } return ''; }
    async function exec(c, h) {
      switch (c.c) {
        case 'say': await say(c.who, c.text); break;
        case 'choice': { const i = await choose(c.options.map((o) => o.text)); return runCommands(c.options[i].do, h); }
        case 'set': G2.applySet(S.vars, c); break;
        case 'item': if (c.n > 0) { if (S.inv.indexOf(c.id) < 0) S.inv.push(c.id); toast(T('Pegou: ', 'Got: ') + data.items[c.id].name); } else { S.inv = S.inv.filter((x) => x !== c.id); if (S.sel === c.id) S.sel = ''; } break;
        case 'goto': await enter(c.scene, false); return 'stop';
        case 'hide': if (h) S.vars[hidKey(h)] = true; break;
        case 'if': return runCommands(G2.cond(c.cond, S.vars) ? c.then : c.else, h);
        case 'sfx': G2.audio.sfx(c.name); break;
        case 'end': S.mode = 'end'; S.end = { title: c.title || T('Fim', 'The End'), t: 0 }; G2.audio.sfx('powerup'); return 'stop';
        default: break;
      }
      return '';
    }
    async function act(h, verb) {
      if (S.busy) return; S.busy = true; S.popup = null;
      try {
        if (verb === 'look') await say('', h.look || T('Nada de especial.', 'Nothing special.'));
        else await runCommands(h[verb] || [], h);
      } finally { S.busy = false; G2.save.set('pc_auto', snapshot()); }
    }
    async function useItemOn(h, item) {
      if (S.busy) return; S.busy = true; S.popup = null;
      try {
        const cmds = h.use_item && h.use_item[item];
        if (cmds && cmds.length) { S.sel = ''; await runCommands(cmds, h); } else { G2.audio.sfx('error'); await say('', h.fail || T('Isso não funciona aqui.', "That doesn't work here.")); }
      } finally { S.busy = false; G2.save.set('pc_auto', snapshot()); }
    }

    // ----- geometria
    const rectOf = (h) => ({ x: h.x * W, y: h.y * SH, w: h.w * W, h: h.h * SH });
    const hit = (h, x, y) => { const r = rectOf(h); return x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h; };
    const hotspotAt = (x, y) => { const list = sceneOf(S.scene).hotspots.filter(visible); for (let i = list.length - 1; i >= 0; i--) if (hit(list[i], x, y)) return list[i]; return null; };
    const slotRect = (i) => ({ x: W - 8 - (8 - i) * 54, y: SH + 22, w: 48, h: 48 });
    const VERBS = () => [['look', T('Olhar', 'Look')], ['take', T('Pegar', 'Take')], ['use', T('Usar', 'Use')], ['talk', T('Falar', 'Talk')]];
    function popupFor(h) { const verbs = VERBS().filter(([k]) => k === 'look' || (h[k] && h[k].length)); const r = rectOf(h); const bw = 84, bh = 30; const x = G2.clamp(r.x + r.w / 2 - bw / 2, 6, W - bw - 6); return { h, items: verbs.map(([k, l], i) => ({ k, l, x, y: Math.max(6, r.y - 8 - (verbs.length - i) * (bh + 4)), w: bw, h: bh })) }; }

    // ----- laço
    function update(dt) {
      S.t += dt; if (S.msgT > 0) S.msgT -= dt; S.fade += Math.sign(S.fadeTarget - S.fade) * Math.min(Math.abs(S.fadeTarget - S.fade), dt * (S.fadeSpeed || 4));
      S.timers.forEach((q) => (q.t -= dt)); const due = S.timers.filter((q) => q.t <= 0); S.timers = S.timers.filter((q) => q.t > 0); due.forEach((q) => q.res());
      const I = G2.input;
      if (S.mode === 'title') { if (S.menus[0]) S.menus[0].update(); return; }
      if (S.mode === 'end') { S.end.t += dt; if (S.end.t > 0.8 && I.pressed('action')) titleMenu(); return; }
      dlg.update(dt);
      if (!dlg.active && !S.busy) { if (I.pressed('cancel')) { S.popup = null; S.sel = ''; } for (let k = 1; k <= 8; k++) if (G2.input.pressed('digit' + k) && S.inv[k - 1]) S.sel = S.sel === S.inv[k - 1] ? '' : S.inv[k - 1]; }
    }
    function titleMenu() {
      const s = G2.save.get('pc_auto'); const M = G2.ListMenu;
      S.menus = [new M({ x: W / 2 - 110, y: 250, w: 220, rowH: 32, entries: [{ label: T('Continuar', 'Continue'), disabled: !s }, { label: T('Novo jogo', 'New game') }], onPick: (i) => { S.menus = []; if (i === 0) load(s); else newGame(); } })];
      S.menus[0].sel = s ? 0 : 1; S.mode = 'title';
    }

    function render() {
      const c = G2.screen.begin(), t = S.t;
      if (S.mode === 'title') { const th = G2.theme(spec.style.theme); c.fillStyle = G2.art.grad(c, 0, 0, 0, H, [[0, th.sky[0]], [1, th.ground]]); c.fillRect(0, 0, W, H); c.textAlign = 'center'; c.textBaseline = 'middle'; c.font = G2.font(42, true); c.fillStyle = '#fff'; c.fillText(spec.title, W / 2, 130); c.font = G2.font(17); c.fillStyle = 'rgba(255,255,255,0.8)'; c.fillText(String(spec.description || '').slice(0, 90), W / 2, 190); S.menus.forEach((m) => m.draw(c)); G2.screen.end(); return; }
      const sc = sceneOf(S.scene);
      c.save(); c.beginPath(); c.rect(0, 0, W, SH); c.clip(); G2.art.scene(c, sc.theme, W, SH, t, sc.tone);
      sc.hotspots.filter(visible).forEach((h) => { const r = rectOf(h); G2.art.prop(c, h.shape, r.x, r.y, r.w, r.h, t, h.appearance); });
      const hov = !dlg.active && !S.busy && !S.popup ? hotspotAt(S.mouse.x, S.mouse.y) : null; S.hover = hov;
      if (hov) { const r = rectOf(hov); c.strokeStyle = 'rgba(255,255,255,' + (0.55 + 0.35 * Math.sin(t * 6)) + ')'; c.lineWidth = 2; c.setLineDash([6, 4]); c.strokeRect(r.x - 4, r.y - 4, r.w + 8, r.h + 8); c.setLineDash([]); }
      c.restore();
      // barra inferior
      c.fillStyle = '#0a0c18'; c.fillRect(0, SH, W, H - SH); c.fillStyle = 'rgba(255,255,255,0.18)'; c.fillRect(0, SH, W, 2);
      c.textAlign = 'left'; c.textBaseline = 'middle'; c.font = G2.font(17, true); c.fillStyle = '#fff';
      const line = S.sel ? T('Usar ', 'Use ') + data.items[S.sel].name + (hov ? T(' com ', ' on ') + (hov.name || hov.id) : T(' com…', ' on…')) : hov ? (hov.name || hov.id) : sc.name; c.fillText(line, 16, SH + 26);
      c.font = G2.font(13); c.fillStyle = 'rgba(255,255,255,0.55)'; c.fillText(S.sel ? T('Clique em um objeto · clique no item de novo para guardar', 'Click an object · click the item again to put it away') : T('Clique em um objeto para interagir', 'Click an object to interact'), 16, SH + 52);
      for (let i = 0; i < 8; i++) { const r = slotRect(i), id = S.inv[i], on = id && id === S.sel; G2.panel(c, r.x, r.y, r.w, r.h, { fill: on ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.06)', stroke: on ? accent : 'rgba(255,255,255,0.3)', r: 8 }); if (id) { c.font = G2.font(26); c.textAlign = 'center'; c.fillStyle = '#fff'; c.fillText(data.items[id].emoji || '📦', r.x + r.w / 2, r.y + r.h / 2 + 2); } }
      if (S.msgT > 0) { c.save(); c.font = G2.font(15); const w = c.measureText(S.msg).width + 34; G2.panel(c, W / 2 - w / 2, 14, w, 32, { r: 16 }); c.fillStyle = '#fff'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(S.msg, W / 2, 30); c.restore(); }
      if (S.popup) { c.font = G2.font(15); c.textBaseline = 'middle'; c.textAlign = 'center'; S.popup.items.forEach((b) => { const on = S.mouse.x >= b.x && S.mouse.x <= b.x + b.w && S.mouse.y >= b.y && S.mouse.y <= b.y + b.h; G2.panel(c, b.x, b.y, b.w, b.h, { fill: on ? 'rgba(255,255,255,0.95)' : 'rgba(8,10,22,0.92)', r: 8 }); c.fillStyle = on ? '#10131f' : '#fff'; c.fillText(b.l, b.x + b.w / 2, b.y + b.h / 2 + 1); }); }
      dlg.draw(c, W, SH + 90);
      if (S.mode === 'end') { const a = Math.min(1, S.end.t * 1.3); c.fillStyle = 'rgba(2,3,10,' + 0.88 * a + ')'; c.fillRect(0, 0, W, H); c.globalAlpha = a; c.textAlign = 'center'; c.textBaseline = 'middle'; c.font = G2.font(50, true); c.fillStyle = accent; c.fillText(S.end.title, W / 2, H / 2 - 20); c.font = G2.font(17); c.fillStyle = '#fff'; c.fillText(T('Pressione Espaço para jogar de novo', 'Press Space to play again'), W / 2, H / 2 + 40); c.globalAlpha = 1; }
      if (S.fade > 0.001) { c.fillStyle = 'rgba(0,0,0,' + S.fade + ')'; c.fillRect(0, 0, W, H); }
      G2.screen.end();
    }
    function pointer(type, x, y, btn) {
      S.mouse.x = x; S.mouse.y = y;
      if (S.mode === 'title') { if (S.menus[0]) S.menus[0].pointer(type, x, y); return; }
      if (S.mode === 'end') { if (type === 'down' && S.end.t > 0.8) titleMenu(); return; }
      if (dlg.active) { dlg.pointer(type, x, y); return; }
      if (type !== 'down' || S.busy) return;
      if (S.popup) { const b = S.popup.items.find((q) => x >= q.x && x <= q.x + q.w && y >= q.y && y <= q.y + q.h); const h = S.popup.h; S.popup = null; if (b) act(h, b.k); return; }
      for (let i = 0; i < 8; i++) { const r = slotRect(i); if (S.inv[i] && x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) { if (btn === 2) { say('', data.items[S.inv[i]].desc || data.items[S.inv[i]].name); return; } S.sel = S.sel === S.inv[i] ? '' : S.inv[i]; G2.audio.sfx('select'); return; } }
      if (y > SH) return;
      const h = hotspotAt(x, y);
      if (!h) { S.sel = ''; return; }
      if (btn === 2) { act(h, 'look'); return; }
      if (S.sel) { useItemOn(h, S.sel); return; }
      const verbs = VERBS().filter(([k]) => h[k] && h[k].length);
      if (!verbs.length) { act(h, 'look'); return; }
      if (verbs.length === 1 && !h.look) { act(h, verbs[0][0]); return; }
      S.popup = popupFor(h); G2.audio.sfx('select');
    }
    return { update, render, pointer, begin: titleMenu, getSave: snapshot, state: S, W, H, hotspots: () => sceneOf(S.scene).hotspots.filter(visible), _api: { act, useItemOn } };
  };
})(typeof window !== 'undefined' ? window : globalThis);
