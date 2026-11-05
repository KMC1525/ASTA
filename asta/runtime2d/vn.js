/* ASTA runtime 2D — Visual Novel (estilo Ren'Py): roteiro como dados, escolhas, variáveis, histórico, salvar/carregar, auto e skip.
   `G2.VN.Runner` é o interpretador (sem DOM, testável); a interface fica em G2.engines.visual_novel. */
(function (root) {
  'use strict';
  const G2 = root.G2;

  // ---- compilação: o roteiro (rótulos com `if` aninhados) vira um programa linear com saltos
  function compile(labels) {
    const prog = [], idx = {};
    const emit = (stmts) => {
      (stmts || []).forEach((s) => {
        if (s.c === 'if') {
          const j = { c: 'jif', cond: s.cond, to: -1 }; prog.push(j); emit(s.then);
          const m = { c: 'jmp', to: -1 }; prog.push(m); j.to = prog.length; emit(s.else); m.to = prog.length;
        } else prog.push(s);
      });
    };
    Object.keys(labels).forEach((name) => { idx[name] = prog.length; emit(labels[name]); });
    return { prog, idx };
  }

  function Runner(data) {
    const c = compile(data.labels);
    this.prog = c.prog; this.idx = c.idx; this.data = data;
    this.chars = {}; (data.characters || []).forEach((ch) => (this.chars[ch.id] = ch));
    this.reset();
  }
  const R = Runner.prototype;
  R.reset = function () {
    this.vars = JSON.parse(JSON.stringify(this.data.variables || {})); this.pc = this.idx[this.data.start] || 0; this.bg = ''; this.sprites = {}; this.music = ''; this.history = [];
    this.events = []; this.waiting = null; this.seen = this.seen || {};
  };
  R.visibleChoices = function (s) { return s.choices.map((ch, i) => ({ ch, i })).filter((x) => !x.ch.if || G2.cond(x.ch.if, this.vars)); };
  // executa até um ponto que exige o jogador; devolve o estado de espera
  R.advance = function () {
    this.waiting = null;
    for (let guard = 0; guard < 8000; guard++) {
      const s = this.prog[this.pc];
      if (!s) return (this.waiting = { type: 'end', title: '' });
      switch (s.c) {
        case 'scene': this.bg = s.bg; this.sprites = {}; this.events.push({ t: 'scene', bg: s.bg }); this.pc++; break;
        case 'show': this.sprites[s.char] = { expr: s.expr, at: s.at, since: this.events.length }; this.pc++; break;
        case 'hide': delete this.sprites[s.char]; this.pc++; break;
        case 'say': {
          const who = s.who ? (this.chars[s.who] || { name: s.who }) : null, line = { who: s.who, name: who ? who.name : '', color: who ? who.color : '', text: G2.fmt(s.text, this.vars), pc: this.pc };
          this.history.push(line); if (this.history.length > 300) this.history.shift();
          this.seen[this.pc] = true; this.pc++; return (this.waiting = { type: 'say', line });
        }
        case 'menu': {
          const vis = this.visibleChoices(s);
          if (!vis.length) { this.pc++; break; }
          return (this.waiting = { type: 'menu', prompt: G2.fmt(s.prompt || '', this.vars), options: vis.map((x) => ({ label: G2.fmt(x.ch.text, this.vars), i: x.i })), at: this.pc });
        }
        case 'jump': this.pc = this.idx[s.label] != null ? this.idx[s.label] : this.prog.length; break;
        case 'set': G2.applySet(this.vars, s); this.pc++; break;
        case 'jif': this.pc = G2.cond(s.cond, this.vars) ? this.pc + 1 : s.to; break;
        case 'jmp': this.pc = s.to; break;
        case 'input': this.pc++; return (this.waiting = { type: 'input', var: s.var, prompt: G2.fmt(s.prompt || '', this.vars), def: s.default || '' });
        case 'music': this.music = s.mood; this.events.push({ t: 'music', mood: s.mood }); this.pc++; break;
        case 'sfx': this.events.push({ t: 'sfx', name: s.name }); this.pc++; break;
        case 'wait': this.pc++; return (this.waiting = { type: 'wait', seconds: s.seconds });
        case 'end': return (this.waiting = { type: 'end', title: G2.fmt(s.title || '', this.vars) });
        default: this.pc++;
      }
    }
    return (this.waiting = { type: 'end', title: '' });
  };
  R.choose = function (i) {
    const w = this.waiting, s = this.prog[w.at], ch = s.choices[w.options[i].i];
    (ch.set || []).forEach((a) => G2.applySet(this.vars, a));
    this.history.push({ who: '', name: '', color: '', text: '➤ ' + G2.fmt(ch.text, this.vars), choice: true });
    this.pc = ch.jump && this.idx[ch.jump] != null ? this.idx[ch.jump] : w.at + 1;
    return this.advance();
  };
  R.answer = function (txt) { const w = this.waiting; this.vars[w.var] = String(txt || w.def || '').slice(0, 30) || w.def || '…'; return this.advance(); };
  // `say`/`input`/`wait` já avançaram o pc ao esperar; `menu`/`end` não — ao restaurar reexecutamos a linha onde o jogador estava
  R.snapshot = function () { return { pc: this.pc, w: this.waiting ? this.waiting.type : '', vars: this.vars, bg: this.bg, sprites: this.sprites, music: this.music, history: this.history.slice(-120), seen: this.seen }; };
  R.restore = function (s) {
    this.pc = s.w === 'say' || s.w === 'input' || s.w === 'wait' ? Math.max(0, s.pc - 1) : s.pc;
    this.vars = JSON.parse(JSON.stringify(s.vars)); this.bg = s.bg; this.sprites = JSON.parse(JSON.stringify(s.sprites || {})); this.music = s.music || ''; this.history = (s.history || []).slice(); this.seen = s.seen || this.seen; this.events = []; this.waiting = null;
  };
  G2.VN = { compile, Runner };

  // ------------------------------------------------------------------ interface
  G2.engines.visual_novel = function (spec) {
    const W = 960, H = 540, data = spec.data, runner = new Runner(data), th = G2.theme(spec.style.theme);
    const dlg = new G2.Dialog({ x: 30, w: W - 60, h: 158, font: 25, speed: 52, accent: spec.style.accent || th.accent, fill: 'rgba(10,12,28,0.84)' });
    const T = G2.t, st = { t: 0, fade: 0, fadeDir: 0, state: null, auto: false, skipRead: false, overlay: '', histScroll: 0, wait: 0, autoT: 0, bgPrev: '', input: null, msg: '', msgT: 0, slotMode: '' };
    G2.screen.letterbox = '#000';
    const SLOTS = ['vn_slot1', 'vn_slot2', 'vn_slot3'];
    const buttons = () => [['auto', T('Auto', 'Auto'), st.auto], ['skip', T('Pular', 'Skip'), st.skipRead], ['hist', T('Histórico', 'Log'), false], ['save', T('Salvar', 'Save'), false], ['load', T('Carregar', 'Load'), false]];
    const btnRects = () => { let x = W - 14; return buttons().reverse().map((b) => { const w = Math.max(54, b[1].length * 10 + 24); x -= w + 8; return { id: b[0], label: b[1], on: b[2], x: x + 8, y: 10, w, h: 30 }; }); };

    function say(text, ms) { st.msg = text; st.msgT = ms || 1.8; }
    function process() {
      const w = st.state = runner.waiting;
      runner.events.splice(0).forEach((ev) => {
        if (ev.t === 'scene') { st.bgPrev = st.bgNow; st.bgNow = ev.bg; st.fade = 1; st.fadeDir = -1; }
        else if (ev.t === 'music') G2.audio.music(ev.mood, spec.audio.music.scale, spec.audio.music.tempo);
        else if (ev.t === 'sfx') G2.audio.sfx(ev.name);
      });
      if (!w) return;
      if (w.type === 'say') { dlg.show(w.line.name, w.line.text, next); dlg.skip = false; st.autoT = 0; }
      else if (w.type === 'menu') dlg.choose(w.prompt, w.options.map((o) => ({ label: o.label })), (i) => { st.state = runner.choose(i); autosave(); process(); });
      else if (w.type === 'wait') st.wait = w.seconds;
      else if (w.type === 'input') openInput(w);
      else if (w.type === 'end') { st.overlay = 'end'; G2.audio.sfx('chime'); }
    }
    function next() { runner.advance(); process(); }
    function autosave() { G2.save.set('vn_auto', Object.assign({ t: Date.now() }, runner.snapshot())); }
    function begin(saved) {
      if (saved) { runner.restore(saved); st.bgNow = runner.bg; if (runner.music) G2.audio.music(runner.music, spec.audio.music.scale, spec.audio.music.tempo); }
      next();
      if (!saved && spec.audio.music.enabled) G2.audio.music(spec.audio.music.mood, spec.audio.music.scale, spec.audio.music.tempo);
    }
    function openInput(w) {
      const box = document.createElement('div'); box.id = 'g2-input';
      box.innerHTML = '<div class="g2-card"><label></label><input maxlength="30" autocomplete="off"><button class="g2-btn"></button></div>';
      box.querySelector('label').textContent = w.prompt || T('Seu nome', 'Your name'); const inp = box.querySelector('input'); inp.value = w.def || ''; box.querySelector('button').textContent = 'OK';
      const done = () => { const v = inp.value.trim(); box.remove(); st.input = null; runner.answer(v || w.def); process(); };
      box.querySelector('button').onclick = done; inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') done(); });
      document.body.appendChild(box); st.input = box; setTimeout(() => inp.focus(), 30);
    }
    function saveTo(slot) { G2.save.set(slot, Object.assign({ t: Date.now(), line: (runner.history.filter((h) => !h.choice).slice(-1)[0] || {}).text || '' }, runner.snapshot())); say(T('Jogo salvo', 'Game saved')); G2.audio.sfx('chime'); }
    function loadFrom(slot) { const s = G2.save.get(slot); if (!s) return say(T('Slot vazio', 'Empty slot')); st.overlay = ''; runner.restore(s); st.bgNow = runner.bg; dlg.close(); next(); }
    function restart() { st.overlay = ''; runner.reset(); st.bgNow = ''; dlg.close(); next(); }

    function update(dt) {
      st.t += dt; if (st.msgT > 0) st.msgT -= dt;
      if (st.fade > 0) { st.fade = Math.max(0, st.fade - dt * 2.4); }
      const I = G2.input;
      if (st.overlay === 'end') { if (I.pressed('action') && st.t > 0.6) restart(); return; }
      if (st.overlay === 'hist') { if (I.pressed('cancel') || I.pressed('history')) st.overlay = ''; if (I.pressed('up')) st.histScroll++; if (I.pressed('down')) st.histScroll = Math.max(0, st.histScroll - 1); return; }
      if (st.overlay === 'slots') { if (I.pressed('cancel')) st.overlay = ''; return; }
      if (I.pressed('history')) st.overlay = 'hist';
      if (I.pressed('save') && !st.input) { st.overlay = 'slots'; st.slotMode = 'save'; }
      if (I.pressed('load') && !st.input) { st.overlay = 'slots'; st.slotMode = 'load'; }
      if (I.pressed('auto')) st.auto = !st.auto;
      if (st.input) return;
      dlg.skip = I.down('skip') || (st.skipRead && st.state && st.state.type === 'say' && runner.seen[st.state.line.pc]);
      dlg.update(dt);
      if (st.state && st.state.type === 'wait') { st.wait -= dt; if (st.wait <= 0) { st.state = null; next(); } }
      if (dlg.active && !dlg.choices && dlg.done && (st.auto || dlg.skip)) { st.autoT += dt; if (st.autoT > (dlg.skip ? 0.06 : 1 + dlg.text.length * 0.035)) { st.autoT = 0; dlg.confirm(); } }
    }

    const XS = { left: 0.2, center: 0.5, right: 0.8 };
    function render() {
      const c = G2.screen.begin(), t = st.t;
      G2.art.scene(c, (data.backgrounds[st.bgNow || runner.bg] || {}).scene || 'room', W, H, t, null, (data.backgrounds[st.bgNow || runner.bg] || {}).tint);
      const speaker = st.state && st.state.type === 'say' ? st.state.line.who : null;
      Object.keys(runner.sprites).forEach((id) => {
        const sp = runner.sprites[id], ch = runner.chars[id]; if (!ch) return;
        const x = W * (XS[sp.at] || 0.5), dim = speaker && speaker !== id;  // quem não fala fica um pouco apagado e recuado
        c.save(); c.globalAlpha = dim ? 0.72 : 1; G2.art.figure(c, ch.appearance, x, H + 10 + (dim ? 6 : 0), H * 0.78 * (dim ? 0.97 : 1), sp.expr, t + G2.hash(id) % 7); c.restore();
      });
      dlg.draw(c, W, H);
      // botões
      c.save(); c.textBaseline = 'middle'; c.textAlign = 'center'; c.font = G2.font(14);
      btnRects().forEach((b) => { G2.panel(c, b.x, b.y, b.w, b.h, { fill: b.on ? 'rgba(255,255,255,0.9)' : 'rgba(8,10,22,0.6)', stroke: 'rgba(255,255,255,0.35)', r: 15 }); c.fillStyle = b.on ? '#10131f' : '#fff'; c.fillText(b.label, b.x + b.w / 2, b.y + b.h / 2 + 1); });
      c.restore();
      if (st.fade > 0) { c.fillStyle = 'rgba(0,0,0,' + (st.fade * 0.85).toFixed(3) + ')'; c.fillRect(0, 0, W, H); }
      if (st.msgT > 0) { c.save(); c.font = G2.font(16); c.textAlign = 'center'; const w = c.measureText(st.msg).width + 36; G2.panel(c, W / 2 - w / 2, 56, w, 34, { r: 17 }); c.fillStyle = '#fff'; c.textBaseline = 'middle'; c.fillText(st.msg, W / 2, 74); c.restore(); }
      if (st.overlay) overlay(c);
      G2.screen.end();
    }
    function overlay(c) {
      c.save(); c.fillStyle = 'rgba(4,6,16,0.9)'; c.fillRect(0, 0, W, H); c.textBaseline = 'top';
      if (st.overlay === 'end') {
        const title = (st.state && st.state.title) || T('Fim', 'The End'); c.textAlign = 'center'; c.font = G2.font(54, true); c.fillStyle = '#fff'; c.fillText(T('FIM', 'THE END'), W / 2, H * 0.3);
        c.font = G2.font(26); c.fillStyle = dlg.o.accent; c.fillText(title, W / 2, H * 0.3 + 78); c.font = G2.font(18); c.fillStyle = 'rgba(255,255,255,0.7)'; c.fillText(T('Clique ou pressione Espaço para jogar de novo', 'Click or press Space to play again'), W / 2, H * 0.3 + 140);
      } else if (st.overlay === 'hist') {
        c.textAlign = 'left'; c.font = G2.font(22, true); c.fillStyle = '#fff'; c.fillText(T('Histórico', 'History'), 40, 24); c.font = G2.font(17);
        const lines = []; runner.history.slice(-60).forEach((h) => { G2.wrap(c, (h.name ? h.name + ': ' : '') + h.text, W - 100).forEach((l, i) => lines.push({ l, c: h.choice ? dlg.o.accent : (i ? '#ddd' : '#fff') })); });
        const rows = Math.floor((H - 100) / 24), end = Math.max(rows, lines.length - st.histScroll), view = lines.slice(Math.max(0, end - rows), end);
        view.forEach((r, i) => { c.fillStyle = r.c; c.fillText(r.l, 50, 70 + i * 24); });
        c.fillStyle = 'rgba(255,255,255,0.5)'; c.font = G2.font(14); c.fillText(T('↑/↓ rola · Esc fecha', '↑/↓ scroll · Esc closes'), 40, H - 30);
      } else if (st.overlay === 'slots') {
        c.textAlign = 'left'; c.font = G2.font(22, true); c.fillStyle = '#fff'; c.fillText(st.slotMode === 'save' ? T('Salvar jogo', 'Save game') : T('Carregar jogo', 'Load game'), 40, 24);
        st.slotRects = [];
        SLOTS.concat(st.slotMode === 'load' ? ['vn_auto'] : []).forEach((k, i) => {
          const s = G2.save.get(k), y = 80 + i * 92, r = { x: 40, y, w: W - 80, h: 78, k }; st.slotRects.push(r);
          G2.panel(c, r.x, r.y, r.w, r.h, { fill: 'rgba(20,24,48,0.9)', stroke: 'rgba(255,255,255,0.4)' });
          c.font = G2.font(18, true); c.fillStyle = '#fff'; c.fillText(k === 'vn_auto' ? T('Auto-salvamento', 'Autosave') : T('Slot ', 'Slot ') + (i + 1), r.x + 18, y + 12);
          c.font = G2.font(15); c.fillStyle = 'rgba(255,255,255,0.65)'; c.fillText(s ? new Date(s.t).toLocaleString() + ' — ' + String(s.line || '').slice(0, 80) : T('(vazio)', '(empty)'), r.x + 18, y + 42);
        });
        c.font = G2.font(14); c.fillStyle = 'rgba(255,255,255,0.5)'; c.fillText(T('Esc fecha', 'Esc closes'), 40, H - 30);
      }
      c.restore();
    }
    function pointer(type, x, y) {
      if (st.input) return;
      if (st.overlay === 'end') { if (type === 'down' && st.t > 0.6) restart(); return; }
      if (st.overlay === 'hist') { if (type === 'down') st.overlay = ''; return; }
      if (st.overlay === 'slots') {
        if (type === 'down') { const r = (st.slotRects || []).find((q) => x >= q.x && x <= q.x + q.w && y >= q.y && y <= q.y + q.h); if (r) { if (st.slotMode === 'save') { saveTo(r.k); st.overlay = ''; } else loadFrom(r.k); } else st.overlay = ''; }
        return;
      }
      if (type === 'down') {
        const b = btnRects().find((q) => x >= q.x && x <= q.x + q.w && y >= q.y && y <= q.y + q.h);
        if (b) { G2.audio.sfx('select'); if (b.id === 'auto') st.auto = !st.auto; else if (b.id === 'skip') st.skipRead = !st.skipRead; else if (b.id === 'hist') { st.overlay = 'hist'; st.histScroll = 0; } else { st.overlay = 'slots'; st.slotMode = b.id; } return; }
      }
      dlg.pointer(type, x, y);
    }
    return { update, render, pointer, begin, getSave: () => runner.snapshot(), runner, state: st, W, H };
  };
})(typeof window !== 'undefined' ? window : globalThis);
