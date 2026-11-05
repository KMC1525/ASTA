/* ASTA runtime 2D — núcleo comum: utilidades, temas, áudio procedural, entrada, tela, salvamento, diálogo e arte procedural.
   Toda a arte é desenhada em código (vetorial, nítida em qualquer resolução); nenhum arquivo de imagem é necessário. */
(function (root) {
  'use strict';
  const G2 = (root.G2 = root.G2 || {});
  G2.engines = {};

  // ------------------------------------------------------------------ utilidades
  G2.clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  G2.lerp = (a, b, t) => a + (b - a) * t;
  G2.hash = (s) => { let h = 2166136261; s = String(s); for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; };
  G2.rng = (seed) => { let a = (typeof seed === 'number' ? seed : G2.hash(seed)) >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; };
  G2.hex = (h) => { h = String(h || '#888888'); const m = h.match(/rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)/); if (m) return [+m[1], +m[2], +m[3]]; h = h.replace('#', ''); if (h.length === 3) h = h.replace(/(.)/g, '$1$1'); const n = parseInt(h, 16) || 0; return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
  G2.rgb = (r, g, b, a) => 'rgba(' + (r | 0) + ',' + (g | 0) + ',' + (b | 0) + ',' + (a == null ? 1 : a) + ')';
  G2.shade = (hex, amt) => { const c = G2.hex(hex); const f = amt < 0 ? (v) => v * (1 + amt) : (v) => v + (255 - v) * amt; return G2.rgb(f(c[0]), f(c[1]), f(c[2])); };
  G2.mix = (a, b, t) => { const x = G2.hex(a), y = G2.hex(b); return G2.rgb(G2.lerp(x[0], y[0], t), G2.lerp(x[1], y[1], t), G2.lerp(x[2], y[2], t)); };
  G2.t = (pt, en) => (G2.lang === 'pt' ? pt : en);
  G2.setLang = (code) => { G2.lang = String(code || 'en').toLowerCase().indexOf('pt') === 0 ? 'pt' : 'en'; };
  G2.setLang(typeof navigator !== 'undefined' ? navigator.language : 'en');

  // ------------------------------------------------------------------ condições (sem eval) e interpolação
  const TOK = /\s*(?:(\d+(?:\.\d+)?)|('[^']*'|"[^"]*")|([A-Za-z_][A-Za-z0-9_]*)|(==|!=|<=|>=|<|>|\(|\)))/y;
  const cache = {};
  function compile(src) {
    if (cache[src]) return cache[src];
    const toks = []; TOK.lastIndex = 0; let m;
    while (TOK.lastIndex < src.length && (m = TOK.exec(src))) {
      if (m[1] != null) toks.push({ k: 'n', v: parseFloat(m[1]) }); else if (m[2] != null) toks.push({ k: 's', v: m[2].slice(1, -1) });
      else if (m[3] != null) toks.push({ k: 'i', v: m[3] }); else toks.push({ k: 'o', v: m[4] });
    }
    let i = 0;
    const peek = () => toks[i], eatI = (v) => { const t = toks[i]; if (t && t.k === 'i' && t.v === v) { i++; return true; } return false; };
    function atom() {
      const t = toks[i++];
      if (!t) return () => 0;
      if (t.k === 'n' || t.k === 's') return () => t.v;
      if (t.k === 'i') { if (t.v === 'true') return () => true; if (t.v === 'false') return () => false; return (v) => (t.v in v ? v[t.v] : 0); }
      if (t.v === '(') { const e = or(); i++; return e; }
      return () => 0;
    }
    function cmp() {
      if (eatI('not')) { const e = cmp(); return (v) => !e(v); }
      const a = atom(), t = peek();
      if (t && t.k === 'o' && /^(==|!=|<=|>=|<|>)$/.test(t.v)) {
        i++; const b = atom();
        return (v) => { const x = a(v), y = b(v); switch (t.v) { case '==': return x == y; case '!=': return x != y; case '<': return x < y; case '<=': return x <= y; case '>': return x > y; default: return x >= y; } }; // eslint-disable-line eqeqeq
      }
      return a;
    }
    function and() { let l = cmp(); while (eatI('and')) { const a = l, b = cmp(); l = (v) => !!a(v) && !!b(v); } return l; }
    function or() { let l = and(); while (eatI('or')) { const a = l, b = and(); l = (v) => !!a(v) || !!b(v); } return l; }
    return (cache[src] = or());
  }
  G2.cond = (expr, vars) => { if (!expr) return true; try { return !!compile(expr)(vars || {}); } catch (e) { return false; } };
  G2.fmt = (text, vars) => String(text == null ? '' : text).replace(/\{([a-z_][a-z0-9_]*)\}/gi, (m, k) => (vars && k in vars ? vars[k] : m));
  G2.applySet = (vars, s) => {
    const cur = vars[s.var]; const v = s.value;
    if (s.op === '+=') vars[s.var] = (Number(cur) || 0) + (Number(v) || 0);
    else if (s.op === '-=') vars[s.var] = (Number(cur) || 0) - (Number(v) || 0);
    else vars[s.var] = v;
  };

  // ------------------------------------------------------------------ temas (paletas)
  const TH = (top, bot, ground, wall, grass, water, accent, bg) => ({ sky: [top, bot], ground, wall, grass, water, accent, bg: bg || top });
  G2.THEMES = {
    fantasy: TH('#3a2f6b', '#8a6fd0', '#1c1838', '#4a3f7a', '#4f8f5b', '#3b6fd0', '#ffd166', '#0b0a18'),
    forest: TH('#2c5a4a', '#8fc7a0', '#16301f', '#3b5d3a', '#3f8a4f', '#3b8fb0', '#f4d35e', '#07120c'),
    night: TH('#080d2e', '#25346e', '#0a0f26', '#1d2748', '#1f4a38', '#1c3f8a', '#cbd5ff', '#03060f'),
    desert: TH('#e8a95a', '#f6d49a', '#a8692f', '#b98a50', '#c9a45c', '#3b8fb0', '#7a3b1d', '#2b1a0c'),
    snow: TH('#8fb3d9', '#e8f1fa', '#cfdde9', '#9fb4c8', '#eef4fa', '#7fb0d6', '#2b4a6b', '#0e1a26'),
    dungeon: TH('#1d1a24', '#3a3545', '#141218', '#4a4458', '#3a4a3a', '#243a5c', '#ff9f43', '#050407'),
    city: TH('#2b3a5e', '#7b8fb8', '#1b2236', '#3b4a6b', '#3a6a4a', '#2a5a8a', '#ffd166', '#070a14'),
    space: TH('#05051a', '#1a1a4a', '#05050f', '#2a2a5a', '#2a5a4a', '#1a3a8a', '#9be7ff', '#02020a'),
    sea: TH('#1f6f9f', '#8fd6e8', '#0d3b5c', '#2a6a8a', '#d9c99a', '#1b6fb0', '#fff1a8', '#04121c'),
    retro: TH('#ff6a88', '#ffc371', '#2b1b4a', '#5a2b7a', '#3ad6a0', '#3a6aff', '#fff04d', '#14081f'),
    horror: TH('#2a0f14', '#5a2a30', '#0d0507', '#3a1a22', '#2a3a2a', '#1a2a3a', '#ff5a5a', '#050203'),
    cozy: TH('#f2b97d', '#ffe0b0', '#7a4a2b', '#c98b5a', '#6fa05a', '#5aa0c0', '#8a3b2a', '#2a1710'),
    sunset: TH('#ff8a5c', '#ffd29a', '#3b2145', '#7a4a6b', '#4a7a4f', '#3a6a9a', '#fff1c0', '#190c1f'),
  };
  G2.theme = (name) => G2.THEMES[name] || G2.THEMES.fantasy;

  // ------------------------------------------------------------------ áudio procedural
  const SCALES = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10], dorian: [0, 2, 3, 5, 7, 9, 10], phrygian: [0, 1, 3, 5, 7, 8, 10], pentatonic: [0, 2, 4, 7, 9], lydian: [0, 2, 4, 6, 7, 9, 11] };
  const MOOD = { calm: { prog: [0, 3, 4, 0], p: 0.35, step: 2 }, tense: { prog: [0, 1, 0, 5], p: 0.5, step: 1 }, mysterious: { prog: [0, 2, 5, 3], p: 0.32, step: 2 }, epic: { prog: [0, 5, 3, 4], p: 0.7, step: 1 }, melancholic: { prog: [0, 5, 2, 4], p: 0.3, step: 2 }, joyful: { prog: [0, 4, 5, 3], p: 0.75, step: 1 } };
  const SFX = {
    chime: [{ t: 'sine', f: 880, f2: 1320, d: 0.4, g: 0.16 }], door: [{ n: 1, d: 0.25, g: 0.18, fq: 500 }, { t: 'square', f: 120, f2: 80, d: 0.2, g: 0.1 }], hit: [{ t: 'square', f: 200, f2: 50, d: 0.16, g: 0.2 }, { n: 1, d: 0.1, g: 0.12, fq: 1800 }],
    jump: [{ t: 'square', f: 280, f2: 620, d: 0.14, g: 0.1 }], coin: [{ t: 'square', f: 988, d: 0.07, g: 0.09 }, { t: 'square', f: 1319, d: 0.2, g: 0.09, at: 0.07 }], select: [{ t: 'triangle', f: 660, d: 0.07, g: 0.12 }],
    step: [{ n: 1, d: 0.06, g: 0.08, fq: 700 }], wind: [{ n: 1, d: 1.2, g: 0.07, fq: 400 }], magic: [{ t: 'sine', f: 500, f2: 1700, d: 0.45, g: 0.12 }, { t: 'triangle', f: 760, f2: 2200, d: 0.4, g: 0.06, at: 0.05 }],
    powerup: [{ t: 'square', f: 392, d: 0.08, g: 0.1 }, { t: 'square', f: 523, d: 0.08, g: 0.1, at: 0.08 }, { t: 'square', f: 659, d: 0.08, g: 0.1, at: 0.16 }, { t: 'square', f: 784, d: 0.2, g: 0.1, at: 0.24 }],
    explosion: [{ n: 1, d: 0.6, g: 0.3, fq: 500 }, { t: 'sawtooth', f: 90, f2: 30, d: 0.5, g: 0.15 }], laser: [{ t: 'sawtooth', f: 1000, f2: 200, d: 0.16, g: 0.08 }], error: [{ t: 'square', f: 160, d: 0.22, g: 0.1 }],
  };
  G2.audio = (function () {
    let ctx = null, master = null, sfxBus = null, musBus = null, noise = null, timer = null, muted = false, vol = 0.8, cur = null, want = null;
    function unlock() {
      if (!ctx) {
        const C = root.AudioContext || root.webkitAudioContext; if (!C) return false;
        ctx = new C(); master = ctx.createGain(); master.gain.value = muted ? 0 : vol;
        const comp = ctx.createDynamicsCompressor(); master.connect(comp); comp.connect(ctx.destination);
        sfxBus = ctx.createGain(); sfxBus.connect(master); musBus = ctx.createGain(); musBus.gain.value = 0.55; musBus.connect(master);
        const len = ctx.sampleRate; noise = ctx.createBuffer(1, len, ctx.sampleRate); const d = noise.getChannelData(0); for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
      }
      if (ctx.state === 'suspended') ctx.resume();
      if (want) { const w = want; want = null; music(w.mood, w.scale, w.tempo); }
      return true;
    }
    function tone(f, f2, t0, d, g, type, out) {
      const o = ctx.createOscillator(), gn = ctx.createGain(); o.type = type || 'square'; o.frequency.setValueAtTime(f, t0); if (f2) o.frequency.exponentialRampToValueAtTime(Math.max(20, f2), t0 + d);
      gn.gain.setValueAtTime(0.0001, t0); gn.gain.exponentialRampToValueAtTime(g, t0 + Math.min(0.02, d / 3)); gn.gain.exponentialRampToValueAtTime(0.0001, t0 + d);
      o.connect(gn); gn.connect(out || sfxBus); o.start(t0); o.stop(t0 + d + 0.05);
    }
    function sfx(name) {
      if (!ctx || muted || !G2.sfxOn) return;
      const parts = SFX[name] || SFX.select, now = ctx.currentTime;
      parts.forEach((p) => {
        const t0 = now + (p.at || 0);
        if (p.n) {
          const src = ctx.createBufferSource(); src.buffer = noise; const f = ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = p.fq || 800; const g = ctx.createGain();
          g.gain.setValueAtTime(p.g, t0); g.gain.exponentialRampToValueAtTime(0.0001, t0 + p.d); src.connect(f); f.connect(g); g.connect(sfxBus); src.start(t0, Math.random() * 0.5, p.d + 0.05);
        } else tone(p.f, p.f2, t0, p.d, p.g, p.t);
      });
    }
    function stopMusic() { if (timer) clearInterval(timer); timer = null; cur = null; }
    function music(mood, scaleName, tempo) {
      if (mood === 'stop') { want = null; return stopMusic(); }
      if (!ctx) { want = { mood, scale: scaleName, tempo }; return; }
      if (cur && cur.mood === mood && cur.scale === scaleName) return;
      stopMusic(); cur = { mood, scale: scaleName };
      const sc = SCALES[scaleName] || SCALES.major, m = MOOD[mood] || MOOD.calm, beat = 60 / (tempo || 90), root0 = 45;
      const hz = (n) => 440 * Math.pow(2, (n - 69) / 12), note = (deg, oct) => { const L = sc.length, o = Math.floor(deg / L), i = ((deg % L) + L) % L; return root0 + sc[i] + 12 * (o + oct); };
      let next = ctx.currentTime + 0.2, step = 0, chord = 0;
      timer = setInterval(() => {
        if (!ctx || muted || ctx.state !== 'running') { next = Math.max(next, ctx ? ctx.currentTime : 0); return; }
        while (next < ctx.currentTime + 0.4) {
          const d = m.prog[Math.floor(step / 8) % m.prog.length];
          if (step % 8 === 0) { tone(hz(note(d, 0)), 0, next, beat * 4, 0.08, 'triangle', musBus); tone(hz(note(d + 2, 1)), 0, next, beat * 4, 0.035, 'sine', musBus); chord = d; }
          if (step % m.step === 0 && Math.random() < m.p) tone(hz(note(chord + [0, 2, 4, 7, 4, 2][Math.floor(Math.random() * 6)], 2)), 0, next, beat * 1.6, 0.05, 'triangle', musBus);
          next += beat / 2; step++;
        }
      }, 120);
    }
    return { unlock, sfx, music, stopMusic, setMuted(m) { muted = m; if (master) master.gain.value = m ? 0 : vol; if (m) { stopMusic(); } }, get muted() { return muted; }, setVolume(v) { vol = v; if (master) master.gain.value = muted ? 0 : v; }, get ready() { return !!ctx; } };
  })();
  G2.sfxOn = true;

  // ------------------------------------------------------------------ entrada
  const ACT = { left: ['ArrowLeft', 'KeyA'], right: ['ArrowRight', 'KeyD'], up: ['ArrowUp', 'KeyW'], down: ['ArrowDown', 'KeyS'], action: ['Space', 'Enter', 'KeyZ'], cancel: ['Escape', 'KeyX', 'Backspace'],
    jump: ['Space', 'ArrowUp', 'KeyW', 'KeyZ'], fire: ['Space', 'KeyZ', 'KeyJ'], restart: ['KeyR'], auto: ['KeyA'], history: ['KeyH'], save: ['KeyS'], load: ['KeyL'], skip: ['ControlLeft', 'ControlRight'],
    digit1: ['Digit1'], digit2: ['Digit2'], digit3: ['Digit3'], digit4: ['Digit4'], digit5: ['Digit5'], digit6: ['Digit6'], digit7: ['Digit7'], digit8: ['Digit8'] };
  G2.input = (function () {
    const down = {}, hit = {}, vdown = {}, vhit = {};
    const typing = (e) => e.target && /^(input|textarea|select)$/i.test(e.target.tagName || '');
    if (root.addEventListener) {
      root.addEventListener('keydown', (e) => {
        if (typing(e)) return;
        if (!down[e.code]) hit[e.code] = true;
        down[e.code] = true;
        if (/^(Arrow|Space)/.test(e.code)) e.preventDefault();
        if (G2.audio) G2.audio.unlock();
      });
      root.addEventListener('keyup', (e) => { down[e.code] = false; });
      root.addEventListener('blur', () => { Object.keys(down).forEach((k) => (down[k] = false)); Object.keys(vdown).forEach((k) => (vdown[k] = false)); });
    }
    const isDown = (a) => !!vdown[a] || (ACT[a] || []).some((c) => down[c]);
    const pressed = (a) => !!vhit[a] || (ACT[a] || []).some((c) => hit[c]);
    return {
      down: isDown, pressed, endFrame() { Object.keys(hit).forEach((k) => (hit[k] = false)); Object.keys(vhit).forEach((k) => (vhit[k] = false)); },
      virtual(a, on) { if (on && !vdown[a]) vhit[a] = true; vdown[a] = on; },
      axisX() { return (isDown('right') ? 1 : 0) - (isDown('left') ? 1 : 0); }, axisY() { return (isDown('down') ? 1 : 0) - (isDown('up') ? 1 : 0); },
      press(code) { down[code] = true; hit[code] = true; }, release(code) { down[code] = false; }, // usados nos testes
    };
  })();

  // ------------------------------------------------------------------ tela (lógica 16:9 → pixels reais, nítida em qualquer DPI)
  G2.screen = { canvas: null, ctx: null, W: 640, H: 360, scale: 1, ox: 0, oy: 0, dpr: 1 };
  G2.screen.setup = function (canvas, W, H) {
    const s = G2.screen; s.canvas = canvas; s.ctx = canvas.getContext('2d'); s.W = W; s.H = H;
    const resize = () => {
      s.dpr = Math.min(2, root.devicePixelRatio || 1);
      const cw = root.innerWidth, ch = root.innerHeight; s.scale = Math.min(cw / W, ch / H);
      canvas.style.width = cw + 'px'; canvas.style.height = ch + 'px'; canvas.width = Math.round(cw * s.dpr); canvas.height = Math.round(ch * s.dpr);
      s.ox = (cw - W * s.scale) / 2; s.oy = (ch - H * s.scale) / 2;
    };
    resize(); root.addEventListener('resize', resize);
  };
  G2.screen.begin = function () {
    const s = G2.screen, c = s.ctx, k = s.scale * s.dpr;
    c.setTransform(1, 0, 0, 1, 0, 0); c.fillStyle = G2.screen.letterbox || '#000'; c.fillRect(0, 0, s.canvas.width, s.canvas.height);
    c.setTransform(k, 0, 0, k, s.ox * s.dpr, s.oy * s.dpr); c.save(); c.beginPath(); c.rect(0, 0, s.W, s.H); c.clip();
    return c;
  };
  G2.screen.end = function () { G2.screen.ctx.restore(); };
  G2.screen.toLogical = function (cx, cy) { const s = G2.screen, r = s.canvas.getBoundingClientRect(); return { x: (cx - r.left - s.ox) / s.scale, y: (cy - r.top - s.oy) / s.scale }; };

  // ------------------------------------------------------------------ laço de tempo (passo fixo)
  G2.loop = function (update, render) {
    const STEP = 1 / 60; let acc = 0, last = 0, raf = 0, running = true;
    const frame = (ts) => {
      if (!running) return;
      raf = root.requestAnimationFrame(frame);
      if (!last) last = ts; acc += Math.min(0.1, (ts - last) / 1000); last = ts;
      let n = 0;
      while (acc >= STEP && n < 6) { update(STEP); G2.input.endFrame(); acc -= STEP; n++; }
      if (n === 6) acc = 0;
      render();
    };
    raf = root.requestAnimationFrame(frame);
    return () => { running = false; root.cancelAnimationFrame(raf); };
  };

  // ------------------------------------------------------------------ salvamento (localStorage ou /api/play/<id>/save)
  G2.save = (function () {
    let data = {}, key = 'asta.g2.local', hosted = false, api = '';
    return {
      async init(cfg) {
        cfg = cfg || {}; key = 'asta.g2.' + (cfg.project || 'local'); hosted = cfg.mode === 'hosted'; api = cfg.api || '';
        try {
          if (hosted) { const r = await fetch(api + '/save'); data = (await r.json()) || {}; } else data = JSON.parse(root.localStorage.getItem(key) || '{}');
        } catch (e) { data = {}; }
        return data;
      },
      get(slot) { return data[slot] || null; },
      list() { return Object.keys(data).filter((k) => k[0] !== '_'); },
      set(slot, value) {
        data[slot] = value;
        try {
          if (hosted) fetch(api + '/save', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).catch(() => {}); else root.localStorage.setItem(key, JSON.stringify(data));
        } catch (e) { /* cheio/bloqueado: ignora */ }
      },
      clear() { data = {}; try { if (hosted) fetch(api + '/save', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: '{}' }); else root.localStorage.removeItem(key); } catch (e) { /* ok */ } },
    };
  })();

  // ------------------------------------------------------------------ texto e janelas
  G2.wrap = function (ctx, text, maxW) {
    const out = []; String(text).split('\n').forEach((para) => {
      let line = ''; para.split(/\s+/).forEach((w) => { const t = line ? line + ' ' + w : w; if (ctx.measureText(t).width > maxW && line) { out.push(line); line = w; } else line = t; });
      out.push(line);
    });
    return out;
  };
  G2.rrect = function (ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); };
  G2.panel = function (ctx, x, y, w, h, opts) {
    opts = opts || {}; G2.rrect(ctx, x, y, w, h, opts.r == null ? 10 : opts.r);
    ctx.fillStyle = opts.fill || 'rgba(8,10,22,0.86)'; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = opts.stroke || 'rgba(255,255,255,0.75)'; ctx.stroke();
  };
  G2.font = (px, bold) => (bold ? '600 ' : '') + px + 'px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif';

  // Caixa de diálogo com texto "máquina de escrever", nome do falante e escolhas (usada por VN, RPG e point & click).
  G2.Dialog = function (opts) {
    this.o = Object.assign({ x: 16, y: 0, w: 0, h: 120, font: 18, speed: 48, accent: '#ffd166' }, opts || {});
    this.who = ''; this.text = ''; this.shown = 0; this.done = true; this.cb = null; this.choices = null; this.sel = 0; this.hover = -1; this.active = false; this.prompt = ''; this.skip = false; this.t = 0; this.cooldown = 0;
  };
  const D = G2.Dialog.prototype;
  D.show = function (who, text, cb) { this.who = who || ''; this.text = String(text); this.shown = 0; this.done = false; this.cb = cb || null; this.choices = null; this.active = true; this.cooldown = 0.12; };
  D.choose = function (prompt, options, cb) { this.prompt = prompt || ''; this.choices = options; this.sel = 0; this.cb = cb; this.active = true; this.done = true; this.who = ''; this.text = ''; this.cooldown = 0.15; };
  D.close = function () { this.active = false; this.choices = null; this.cb = null; };
  D.confirm = function () {
    if (!this.active || this.cooldown > 0) return;
    if (this.choices) { const i = this.sel, cb = this.cb; this.close(); G2.audio.sfx('select'); if (cb) cb(i); return; }
    if (!this.done) { this.shown = this.text.length; this.done = true; return; }
    const cb = this.cb; this.close(); if (cb) cb();
  };
  D.update = function (dt) {
    if (!this.active) return; this.t += dt; if (this.cooldown > 0) this.cooldown -= dt;
    if (!this.done) { this.shown = Math.min(this.text.length, this.shown + dt * this.o.speed * (this.skip ? 8 : 1)); if (this.shown >= this.text.length) this.done = true; }
    const I = G2.input;
    if (this.choices) {
      if (I.pressed('up')) { this.sel = (this.sel + this.choices.length - 1) % this.choices.length; G2.audio.sfx('select'); }
      if (I.pressed('down')) { this.sel = (this.sel + 1) % this.choices.length; G2.audio.sfx('select'); }
    }
    if (I.pressed('action')) this.confirm();
  };
  D.pointer = function (type, x, y) {
    if (!this.active) return false;
    if (this.choices && this.rects) { const i = this.rects.findIndex((r) => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h); if (type === 'move') { this.hover = i; if (i >= 0) this.sel = i; return true; } if (type === 'down' && i >= 0) { this.sel = i; this.confirm(); return true; } return true; }
    if (type === 'down') { this.confirm(); return true; }
    return false;
  };
  D.draw = function (ctx, W, H) {
    if (!this.active) return; const o = this.o, w = o.w || W - o.x * 2, y = o.y || H - o.h - 14;
    ctx.save(); ctx.textBaseline = 'top';
    if (this.choices) {
      const fh = o.font, rowH = fh * 1.9, n = this.choices.length, bw = Math.min(W - 60, 520), bx = (W - bw) / 2, total = n * rowH + (this.prompt ? fh * 2 : 0), by = Math.max(10, (H - o.h - total) / 2 - 10);
      this.rects = [];
      if (this.prompt) { ctx.font = G2.font(fh, true); ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.shadowColor = '#000'; ctx.shadowBlur = 6; ctx.fillText(this.prompt, W / 2, by); ctx.shadowBlur = 0; }
      this.choices.forEach((c, i) => {
        const yy = by + (this.prompt ? fh * 2 : 0) + i * rowH, on = i === this.sel; this.rects.push({ x: bx, y: yy, w: bw, h: rowH - 6 });
        G2.panel(ctx, bx, yy, bw, rowH - 6, { fill: on ? 'rgba(255,255,255,0.94)' : 'rgba(8,10,22,0.82)', stroke: on ? o.accent : 'rgba(255,255,255,0.4)', r: 9 });
        ctx.font = G2.font(fh); ctx.fillStyle = on ? '#10131f' : '#fff'; ctx.textAlign = 'center'; ctx.fillText(c.label || c, W / 2, yy + (rowH - 6 - fh) / 2 - 1);
      });
    } else {
      G2.panel(ctx, o.x, y, w, o.h, { fill: o.fill });
      ctx.font = G2.font(o.font); ctx.textAlign = 'left';
      let ty = y + 14 + (this.who ? o.font * 0.75 : 0);
      if (this.who) { ctx.font = G2.font(o.font, true); const tw = ctx.measureText(this.who).width + 26; G2.panel(ctx, o.x + 14, y - o.font * 0.9, tw, o.font * 1.8, { fill: 'rgba(8,10,22,0.95)', stroke: o.accent, r: 8 }); ctx.fillStyle = o.accent; ctx.fillText(this.who, o.x + 27, y - o.font * 0.9 + o.font * 0.4); ctx.font = G2.font(o.font); }
      ctx.fillStyle = '#f4f4f4';
      const lines = G2.wrap(ctx, this.text.slice(0, Math.floor(this.shown)), w - 36), full = G2.wrap(ctx, this.text, w - 36), lh = o.font * 1.35;
      const maxLines = Math.floor((o.h - 22 - (this.who ? o.font * 0.75 : 0)) / lh); const start = Math.max(0, full.length - maxLines);
      lines.slice(start).forEach((l, i) => ctx.fillText(l, o.x + 18, ty + i * lh));
      if (this.done) { ctx.fillStyle = o.accent; ctx.globalAlpha = 0.5 + 0.5 * Math.sin(this.t * 6); ctx.fillText('▼', o.x + w - 30, y + o.h - o.font * 1.6); ctx.globalAlpha = 1; }
    }
    ctx.restore();
  };

  // ------------------------------------------------------------------ menu de lista (teclado + mouse/toque), usado por RPG, plataforma, side scroller e point & click
  G2.ListMenu = function (o) { this.o = Object.assign({ x: 0, y: 0, w: 220, rowH: 28, font: 16, title: '', entries: [], onPick: null, onCancel: null, maxRows: 9 }, o); this.sel = 0; this.top = 0; this.rects = []; };
  const L = G2.ListMenu.prototype;
  L.update = function () {
    const I = G2.input, e = this.o.entries; if (!e.length) { if (I.pressed('cancel') && this.o.onCancel) this.o.onCancel(); return; }
    if (I.pressed('up')) { this.sel = (this.sel + e.length - 1) % e.length; G2.audio.sfx('select'); } if (I.pressed('down')) { this.sel = (this.sel + 1) % e.length; G2.audio.sfx('select'); }
    if (this.sel < this.top) this.top = this.sel; if (this.sel >= this.top + this.o.maxRows) this.top = this.sel - this.o.maxRows + 1;
    if (I.pressed('action')) this.pick(this.sel); if (I.pressed('cancel') && this.o.onCancel) this.o.onCancel();
  };
  L.pick = function (i) { const en = this.o.entries[i]; if (!en || en.disabled) { G2.audio.sfx('error'); return; } G2.audio.sfx('select'); if (this.o.onPick) this.o.onPick(i, en); };
  L.pointer = function (type, x, y) {
    const i = this.rects.findIndex((r) => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h);
    if (type === 'move' && i >= 0) this.sel = this.top + i; else if (type === 'down') { if (i >= 0) { this.sel = this.top + i; this.pick(this.sel); } else if (this.o.onCancel && !(x >= this.o.x && x <= this.o.x + this.o.w)) this.o.onCancel(); }
    return true;
  };
  L.draw = function (c) {
    const o = this.o, n = Math.min(o.entries.length, o.maxRows), h = n * o.rowH + 16 + (o.title ? o.rowH : 0); this.rects = [];
    G2.panel(c, o.x, o.y, o.w, h, { r: 8 }); c.save(); c.textBaseline = 'middle'; c.textAlign = 'left'; let y = o.y + 8;
    if (o.title) { c.font = G2.font(o.font, true); c.fillStyle = '#ffd166'; c.fillText(o.title, o.x + 14, y + o.rowH / 2); y += o.rowH; }
    c.font = G2.font(o.font);
    for (let i = 0; i < n; i++) {
      const en = o.entries[this.top + i], on = this.top + i === this.sel; this.rects.push({ x: o.x + 6, y, w: o.w - 12, h: o.rowH });
      if (on) { c.fillStyle = 'rgba(255,255,255,0.18)'; G2.rrect(c, o.x + 6, y, o.w - 12, o.rowH, 6); c.fill(); }
      c.fillStyle = en.disabled ? 'rgba(255,255,255,0.35)' : '#fff'; c.textAlign = 'left'; c.fillText(en.label, o.x + 16, y + o.rowH / 2);
      if (en.right) { c.textAlign = 'right'; c.fillStyle = en.disabled ? 'rgba(255,255,255,0.35)' : '#ffd166'; c.fillText(en.right, o.x + o.w - 16, y + o.rowH / 2); }
      y += o.rowH;
    }
    c.restore();
  };

  // ------------------------------------------------------------------ arte procedural
  const A = (G2.art = {});
  A.skinOf = (ap) => (ap && ap.skin) || '#e0ac84';
  function rect(c, x, y, w, h, f) { c.fillStyle = f; c.fillRect(x, y, w, h); }
  function circ(c, x, y, r, f) { c.fillStyle = f; c.beginPath(); c.arc(x, y, Math.max(0, r), 0, 6.2832); c.fill(); }
  function poly(c, pts, f) { c.fillStyle = f; c.beginPath(); pts.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); c.closePath(); c.fill(); }
  function grad(c, x0, y0, x1, y1, stops) { const g = c.createLinearGradient(x0, y0, x1, y1); stops.forEach((s, i) => g.addColorStop(s[0], s[1])); return g; }
  A.rect = rect; A.circ = circ; A.poly = poly; A.grad = grad;

  // rosto (olhos + boca) por expressão; (cx,cy) = centro da cabeça, r = raio
  function face(c, cx, cy, r, expr, look) {
    const ink = '#1a1412', e = r * 0.34, ey = cy + r * 0.05, lw = Math.max(1.2, r * 0.09);
    c.strokeStyle = ink; c.fillStyle = ink; c.lineWidth = lw; c.lineCap = 'round';
    const arc = (x, up) => { c.beginPath(); c.arc(x, ey + (up ? r * 0.08 : -r * 0.05), r * 0.14, up ? Math.PI * 1.05 : Math.PI * 0.05, up ? Math.PI * 1.95 : Math.PI * 0.95); c.stroke(); };
    if (look === 'up') return; // costas da cabeça
    if (look === 'left' || look === 'right') { const sx = look === 'left' ? -1 : 1; circ(c, cx + sx * r * 0.36, ey, r * 0.1, ink); c.beginPath(); c.moveTo(cx + sx * r * 0.2, cy + r * 0.45); c.lineTo(cx + sx * r * 0.45, cy + r * 0.45); c.stroke(); return; }
    if (expr === 'happy') { arc(cx - e, true); arc(cx + e, true); } else if (expr === 'sad') { circ(c, cx - e, ey, r * 0.1, ink); circ(c, cx + e, ey, r * 0.1, ink); c.beginPath(); c.moveTo(cx - e - r * 0.12, ey - r * 0.2); c.lineTo(cx - e + r * 0.1, ey - r * 0.14); c.moveTo(cx + e + r * 0.12, ey - r * 0.2); c.lineTo(cx + e - r * 0.1, ey - r * 0.14); c.stroke(); }
    else if (expr === 'angry') { circ(c, cx - e, ey, r * 0.1, ink); circ(c, cx + e, ey, r * 0.1, ink); c.beginPath(); c.moveTo(cx - e - r * 0.14, ey - r * 0.2); c.lineTo(cx - e + r * 0.12, ey - r * 0.1); c.moveTo(cx + e + r * 0.14, ey - r * 0.2); c.lineTo(cx + e - r * 0.12, ey - r * 0.1); c.stroke(); }
    else if (expr === 'surprised') { c.fillStyle = '#fff'; circ(c, cx - e, ey, r * 0.16, '#fff'); circ(c, cx + e, ey, r * 0.16, '#fff'); c.stroke(); circ(c, cx - e, ey, r * 0.07, ink); circ(c, cx + e, ey, r * 0.07, ink); }
    else if (expr === 'shy') { circ(c, cx - e, ey + r * 0.06, r * 0.09, ink); circ(c, cx + e, ey + r * 0.06, r * 0.09, ink); circ(c, cx - r * 0.55, cy + r * 0.3, r * 0.14, 'rgba(255,110,130,0.5)'); circ(c, cx + r * 0.55, cy + r * 0.3, r * 0.14, 'rgba(255,110,130,0.5)'); }
    else { circ(c, cx - e, ey, r * 0.1, ink); circ(c, cx + e, ey, r * 0.1, ink); }
    c.strokeStyle = ink; c.lineWidth = lw; c.beginPath();
    const my = cy + r * 0.45;
    if (expr === 'happy') { c.arc(cx, my - r * 0.12, r * 0.22, 0.15, Math.PI - 0.15); c.stroke(); } else if (expr === 'sad') { c.arc(cx, my + r * 0.2, r * 0.18, Math.PI + 0.3, -0.3); c.stroke(); }
    else if (expr === 'angry') { c.moveTo(cx - r * 0.18, my + r * 0.05); c.lineTo(cx + r * 0.18, my + r * 0.05); c.stroke(); } else if (expr === 'surprised') { c.ellipse(cx, my + r * 0.05, r * 0.1, r * 0.14, 0, 0, 6.28); c.fill(); }
    else if (expr === 'shy') { c.moveTo(cx - r * 0.12, my); c.quadraticCurveTo(cx, my + r * 0.1, cx + r * 0.12, my); c.stroke(); } else { c.moveTo(cx - r * 0.15, my); c.quadraticCurveTo(cx, my + r * 0.08, cx + r * 0.15, my); c.stroke(); }
  }
  A.face = face;

  // personagem de corpo inteiro (sprites da visual novel): ancorado nos pés (cx, footY)
  A.figure = function (c, ap, cx, footY, height, expr, t) {
    ap = ap || {}; const k = height / 170, bob = Math.sin((t || 0) * 2) * 1.4 * k, skin = ap.skin || '#e0ac84', hair = ap.hair || '#3a2615', top = ap.top || '#3b5b7a', bot = ap.bottom || '#2a2a30';
    c.save(); c.translate(cx, footY + bob); c.scale(k, k);
    if (ap.accessory === 'cape') rect(c, -26, -118, 52, 90, G2.shade(bot, -0.1));
    if (ap.hair_style === 'long') { c.fillStyle = hair; G2.rrect(c, -24, -150, 48, 78, 20); c.fill(); }
    rect(c, -15, -64, 12, 64, bot); rect(c, 3, -64, 12, 64, bot); rect(c, -17, -6, 15, 6, '#1a1a1f'); rect(c, 2, -6, 15, 6, '#1a1a1f');
    c.fillStyle = top; G2.rrect(c, -24, -118, 48, 62, 14); c.fill(); rect(c, -24, -70, 48, 10, G2.shade(top, -0.15));
    c.fillStyle = top; G2.rrect(c, -34, -112, 12, 52, 6); c.fill(); G2.rrect(c, 22, -112, 12, 52, 6); c.fill(); circ(c, -28, -58, 6, skin); circ(c, 28, -58, 6, skin);
    rect(c, -6, -126, 12, 14, G2.shade(skin, -0.08)); circ(c, 0, -142, 24, skin);
    if (ap.hair_style !== 'bald') { c.fillStyle = hair; c.beginPath(); c.arc(0, -146, 25, Math.PI, 0); c.lineTo(25, -142); c.quadraticCurveTo(10, -158, -25, -142); c.closePath(); c.fill(); c.beginPath(); c.moveTo(-25, -146); c.quadraticCurveTo(-12, -128, 6, -140); c.quadraticCurveTo(14, -150, 22, -146); c.fill(); }
    if (ap.hair_style === 'bun') circ(c, 0, -170, 10, hair);
    if (ap.accessory === 'hat') { rect(c, -30, -162, 60, 6, G2.shade(bot, -0.1)); rect(c, -18, -184, 36, 24, G2.shade(bot, -0.05)); }
    face(c, 0, -141, 24, expr || 'neutral');
    c.restore();
  };

  // sprite pequeno (RPG, point & click, plataforma): ancorado em (cx, footY), `size` = altura total
  A.sprite = function (c, ap, cx, footY, size, o) {
    o = o || {}; ap = ap || {}; const s = size / 30, dir = o.dir || 'down', frame = o.frame || 0, skin = ap.skin || '#e0ac84', hair = ap.hair || '#3a2615', top = ap.top || '#3b5b7a', bot = ap.bottom || '#2a2a30';
    c.save(); c.translate(cx, footY - (o.hop || 0)); c.scale(s, s);
    const step = o.walking ? Math.sin(frame * 0.9) * 3 : 0;
    c.fillStyle = 'rgba(0,0,0,0.25)'; c.beginPath(); c.ellipse(0, 0, 8, 2.6, 0, 0, 6.28); c.fill();
    rect(c, -5, -9, 4, 9 - Math.max(0, step) * 0.2, bot); rect(c, 1, -9, 4, 9 + Math.min(0, step) * 0.2, bot);
    if (ap.accessory === 'cape' && dir !== 'down') rect(c, -7, -19, 14, 12, G2.shade(bot, -0.1));
    c.fillStyle = top; G2.rrect(c, -7, -19, 14, 11, 3); c.fill();
    if (dir === 'left' || dir === 'right') rect(c, -2, -17, 4, 7, G2.shade(top, -0.2)); else { rect(c, -9, -18, 3, 8, G2.shade(top, -0.1)); rect(c, 6, -18, 3, 8, G2.shade(top, -0.1)); }
    circ(c, 0, -23, 7.5, skin);
    if (ap.hair_style !== 'bald') { c.fillStyle = hair; c.beginPath(); c.arc(0, -24, 8, Math.PI, 0); c.fill(); if (dir === 'up') circ(c, 0, -23, 7.6, hair); if (ap.hair_style === 'long') { rect(c, -8, -25, 3, 11, hair); rect(c, 5, -25, 3, 11, hair); } }
    if (ap.hair_style === 'bun') circ(c, 0, -31, 3.4, hair);
    if (ap.accessory === 'hat') { rect(c, -9, -29, 18, 2.4, bot); rect(c, -5, -35, 10, 7, bot); }
    if (ap.accessory === 'backpack' && dir === 'up') rect(c, -5, -18, 10, 9, '#6b4a2b');
    face(c, 0, -22.5, 7.5, 'neutral', dir === 'up' ? 'up' : (dir === 'left' || dir === 'right' ? dir : null));
    c.restore();
  };

  // ------------------------------------------------------------------ cenários (visual novel e point & click)
  function hills(c, W, y, amp, seed, col, n) { const r = G2.rng(seed); c.fillStyle = col; c.beginPath(); c.moveTo(0, y + amp); const pts = []; for (let i = 0; i <= n; i++) pts.push([i * W / n, y - r() * amp]); pts.forEach((p, i) => { if (i) { const q = pts[i - 1]; c.quadraticCurveTo(q[0], q[1], (p[0] + q[0]) / 2, (p[1] + q[1]) / 2); } }); c.lineTo(W, y + amp); c.lineTo(W, 9999); c.lineTo(0, 9999); c.closePath(); c.fill(); }
  function trees(c, W, base, seed, n, size, col, trunk) { const r = G2.rng(seed); for (let i = 0; i < n; i++) { const x = r() * W, s = size * (0.6 + r() * 0.7); rect(c, x - s * 0.06, base - s * 0.5, s * 0.12, s * 0.5, trunk); poly(c, [[x - s * 0.34, base - s * 0.3], [x + s * 0.34, base - s * 0.3], [x, base - s * 1.05]], col); poly(c, [[x - s * 0.28, base - s * 0.55], [x + s * 0.28, base - s * 0.55], [x, base - s * 1.2]], G2.shade(col, 0.1)); } }
  function windowsGrid(c, x, y, w, h, cols, rows, lit, seed) { const r = G2.rng(seed); const cw = w / cols, rh = h / rows; for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) { rect(c, x + i * cw + cw * 0.2, y + j * rh + rh * 0.2, cw * 0.6, rh * 0.6, r() < lit ? '#ffe9a8' : 'rgba(20,30,60,0.8)'); } }
  function stars(c, W, H, seed, n, t) { const r = G2.rng(seed); for (let i = 0; i < n; i++) { const x = r() * W, y = r() * H * 0.7, s = 0.6 + r() * 1.6; c.globalAlpha = 0.5 + 0.5 * Math.sin((t || 0) * 2 + i); circ(c, x, y, s, '#fff'); } c.globalAlpha = 1; }
  const SCENE_THEME = { forest: 'forest', room: 'cozy', city: 'city', beach: 'sea', school: 'cozy', cafe: 'cozy', night_sky: 'night', castle: 'fantasy', cave: 'dungeon', street: 'city', library: 'cozy', garden: 'forest', sunset: 'sunset', office: 'city', bedroom: 'cozy', field: 'forest', lab: 'retro', ship: 'space', kitchen: 'cozy', cellar: 'horror' };
  A.scene = function (c, kind, W, H, t, theme, tint) {
    const th = G2.theme(theme || SCENE_THEME[kind] || 'fantasy'), horizon = H * 0.62, seed = kind;
    const sky = () => { c.fillStyle = grad(c, 0, 0, 0, horizon, [[0, th.sky[0]], [1, th.sky[1]]]); c.fillRect(0, 0, W, H); };
    const floor = (col, col2) => { c.fillStyle = grad(c, 0, horizon, 0, H, [[0, col], [1, col2 || G2.shade(col, -0.35)]]); c.fillRect(0, horizon, W, H - horizon); };
    const wall = (col) => { c.fillStyle = grad(c, 0, 0, 0, horizon, [[0, G2.shade(col, 0.05)], [1, G2.shade(col, -0.2)]]); c.fillRect(0, 0, W, horizon); rect(c, 0, horizon - 6, W, 8, G2.shade(col, -0.4)); };
    if (kind === 'forest') { sky(); circ(c, W * 0.8, H * 0.2, 36, 'rgba(255,255,220,0.5)'); hills(c, W, horizon - 70, 90, seed + 1, G2.shade(th.grass, -0.35), 7); trees(c, W, horizon - 10, seed + 2, 12, H * 0.5, G2.shade(th.grass, -0.45), '#2a1c10'); floor(th.grass); trees(c, W, horizon + 60, seed + 3, 7, H * 0.8, G2.shade(th.grass, -0.25), '#3a2814'); }
    else if (kind === 'beach') { sky(); circ(c, W * 0.22, H * 0.22, 40, '#fff4c2'); c.fillStyle = grad(c, 0, horizon - 90, 0, horizon + 10, [[0, th.water], [1, G2.shade(th.water, 0.25)]]); c.fillRect(0, horizon - 90, W, 100); for (let i = 0; i < 9; i++) { c.strokeStyle = 'rgba(255,255,255,0.35)'; c.lineWidth = 2; c.beginPath(); const y = horizon - 80 + i * 10; for (let x = 0; x <= W; x += 20) c.lineTo(x, y + Math.sin(x * 0.04 + (t || 0) * 1.5 + i) * 2.5); c.stroke(); } floor('#e8d49a', '#b89c60'); }
    else if (kind === 'night_sky') { c.fillStyle = grad(c, 0, 0, 0, H, [[0, '#04061c'], [1, '#1b2656']]); c.fillRect(0, 0, W, H); stars(c, W, H, seed, 90, t); circ(c, W * 0.75, H * 0.2, 30, '#f4f1d8'); circ(c, W * 0.75 + 10, H * 0.2 - 6, 26, '#10163a'); hills(c, W, H * 0.72, 70, seed + 1, '#0a1030', 6); floor('#0c1432', '#060a1c'); }
    else if (kind === 'sunset') { c.fillStyle = grad(c, 0, 0, 0, H, [[0, '#4a2a6b'], [0.5, '#ff8a5c'], [0.8, '#ffd29a'], [1, '#ffb070']]); c.fillRect(0, 0, W, H); circ(c, W * 0.5, horizon - 10, 70, 'rgba(255,240,190,0.9)'); hills(c, W, horizon, 60, seed + 1, '#2a1838', 8); trees(c, W, horizon + 20, seed + 2, 9, H * 0.45, '#150c1c', '#150c1c'); floor('#1c1024', '#0c0612'); }
    else if (kind === 'city' || kind === 'street') { sky(); const r = G2.rng(seed); for (let i = 0; i < 12; i++) { const bw = 50 + r() * 70, bh = 90 + r() * 200, x = i * (W / 11) - 20; rect(c, x, horizon - bh, bw, bh, G2.shade(th.wall, -0.25 - r() * 0.2)); windowsGrid(c, x + 6, horizon - bh + 10, bw - 12, bh - 20, 4, Math.floor(bh / 28), 0.4, seed + i); } floor('#2a2f3e', '#14171f'); for (let x = 0; x < W; x += 90) rect(c, x, horizon + (H - horizon) * 0.55, 46, 5, 'rgba(255,255,255,0.35)'); }
    else if (kind === 'castle') { sky(); hills(c, W, horizon - 50, 60, seed, '#1f1a3a', 6); rect(c, W * 0.1, horizon - 190, W * 0.8, 190, '#4a4468'); for (let i = 0; i < 8; i++) rect(c, W * 0.1 + i * (W * 0.1), horizon - 205, W * 0.05, 18, '#4a4468'); for (let i = 0; i < 4; i++) { c.fillStyle = '#10142e'; c.beginPath(); c.arc(W * (0.22 + i * 0.19), horizon - 90, 26, Math.PI, 0); c.lineTo(W * (0.22 + i * 0.19) + 26, horizon - 20); c.lineTo(W * (0.22 + i * 0.19) - 26, horizon - 20); c.fill(); } floor('#3b3752', '#1b1830'); }
    else if (kind === 'cave') { c.fillStyle = grad(c, 0, 0, 0, H, [[0, '#0a0810'], [1, '#2a2434']]); c.fillRect(0, 0, W, H); const r = G2.rng(seed); for (let i = 0; i < 16; i++) { const x = r() * W, h2 = 40 + r() * 120; poly(c, [[x - 18, 0], [x + 18, 0], [x, h2]], '#1a1622'); } for (let i = 0; i < 9; i++) { const x = r() * W, h2 = 30 + r() * 70; poly(c, [[x - 20, H], [x + 20, H], [x, H - h2]], '#15111c'); } circ(c, W * 0.7, H * 0.5, 90, 'rgba(120,180,255,0.07)'); }
    else if (kind === 'garden' || kind === 'field') { sky(); hills(c, W, horizon - 30, 60, seed, G2.shade(th.grass, -0.3), 6); floor(th.grass); const r = G2.rng(seed + 9); for (let i = 0; i < 26; i++) { const x = r() * W, y = horizon + 14 + r() * (H - horizon - 20); circ(c, x, y, 3.2, ['#ff7aa8', '#ffe066', '#ffffff', '#b28dff'][i % 4]); } if (kind === 'garden') { for (let i = 0; i < 5; i++) { rect(c, i * W / 4.5 - 10, horizon - 20, 90, 40, G2.shade(th.grass, -0.45)); } } else for (let i = 0; i < 4; i++) { circ(c, 90 + i * 220 + Math.sin((t || 0) * 0.2 + i) * 14, 70 + (i % 2) * 40, 34, 'rgba(255,255,255,0.8)'); circ(c, 120 + i * 220 + Math.sin((t || 0) * 0.2 + i) * 14, 78 + (i % 2) * 40, 26, 'rgba(255,255,255,0.8)'); } }
    else if (kind === 'library') { wall('#5a3b25'); const r = G2.rng(seed); for (let s = 0; s < 3; s++) { const y = 40 + s * 130; rect(c, 20, y + 100, W - 40, 10, '#2a1810'); for (let x = 30; x < W - 60;) { const bw = 12 + r() * 16, bh = 60 + r() * 36; rect(c, x, y + 100 - bh, bw, bh, ['#8a2b2b', '#2b5a8a', '#2b8a5a', '#8a6a2b', '#6a2b8a'][Math.floor(r() * 5)]); x += bw + 2; } } floor('#3a2415'); }
    else if (kind === 'office') { wall('#9aa6bd'); for (let i = 0; i < 3; i++) { rect(c, 60 + i * 280, 70, 200, 150, '#cfe4ff'); rect(c, 60 + i * 280, 70, 200, 150, 'rgba(255,255,255,0.15)'); c.strokeStyle = '#6a7690'; c.lineWidth = 6; c.strokeRect(60 + i * 280, 70, 200, 150); } floor('#5a6378'); rect(c, 80, horizon + 30, 240, 14, '#6a4a30'); rect(c, 440, horizon + 40, 260, 14, '#6a4a30'); }
    else if (kind === 'bedroom' || kind === 'room') { wall(kind === 'bedroom' ? '#8a6a9a' : '#c9a37a'); c.fillStyle = 'rgba(255,255,255,0.05)'; for (let x = 20; x < W; x += 46) c.fillRect(x, 0, 14, horizon - 6); floor('#7a5535'); c.fillStyle = 'rgba(0,0,0,0.12)'; for (let x = 0; x < W; x += 80) c.fillRect(x, horizon + 6, 2, H - horizon); circ(c, W * 0.5, 0, W * 0.5, 'rgba(255,230,170,0.07)'); }
    else if (kind === 'cafe') { wall('#b0764b'); for (let i = 0; i < 5; i++) { rect(c, 90 + i * 150, 0, 3, 90 + (i % 2) * 20, '#2a1810'); circ(c, 91 + i * 150, 96 + (i % 2) * 20, 16, '#ffe9a8'); circ(c, 91 + i * 150, 96 + (i % 2) * 20, 40, 'rgba(255,230,160,0.12)'); } rect(c, 0, horizon - 70, W, 80, '#5a3520'); rect(c, 0, horizon - 74, W, 8, '#8a5a35'); floor('#4a2c18'); for (let i = 0; i < 3; i++) { circ(c, 150 + i * 230, horizon + 70, 46, '#6a4528'); rect(c, 146 + i * 230, horizon + 70, 8, 60, '#3a2414'); } }
    else if (kind === 'school') { wall('#cdd6a8'); rect(c, 60, 50, W - 120, 120, '#2a4a3a'); c.strokeStyle = '#8a6a40'; c.lineWidth = 8; c.strokeRect(60, 50, W - 120, 120); c.fillStyle = 'rgba(255,255,255,0.7)'; c.font = G2.font(24); c.fillText('2 + 2 = 4', 100, 100); floor('#a88a60'); for (let i = 0; i < 4; i++) { rect(c, 70 + i * 190, horizon + 60, 120, 14, '#7a5a30'); rect(c, 85 + i * 190, horizon + 74, 8, 40, '#5a4020'); } }
    else if (kind === 'kitchen') { wall('#e8d8b0'); for (let x = 0; x < W; x += 36) for (let y = 40; y < horizon - 70; y += 36) rect(c, x + 1, y + 1, 34, 34, (x / 36 + y / 36) % 2 ? '#f6ecd0' : '#dcc89a'); rect(c, 0, horizon - 70, W, 76, '#8a6a45'); rect(c, 0, horizon - 74, W, 8, '#cfa970'); floor('#9a7a55'); circ(c, W * 0.7, horizon - 100, 32, '#c0c0c8'); }
    else if (kind === 'lab') { wall('#2b3350'); for (let i = 0; i < 5; i++) { rect(c, 40 + i * 150, 60, 120, 90, '#10162a'); for (let j = 0; j < 5; j++) rect(c, 50 + i * 150, 70 + j * 16, 40 + (j * 17 + i * 11) % 60, 7, ['#3aff9a', '#3ab0ff', '#ffb03a'][(i + j) % 3]); } floor('#1a2038'); circ(c, W * 0.5, horizon + 40, 30, 'rgba(60,255,160,0.25)'); }
    else if (kind === 'ship') { c.fillStyle = grad(c, 0, 0, 0, H, [[0, '#06061c'], [1, '#12123a']]); c.fillRect(0, 0, W, H); stars(c, W, H, seed, 60, t); rect(c, 0, horizon - 20, W, H, '#2a3048'); for (let i = 0; i < 4; i++) { circ(c, 100 + i * 200, 120, 48, '#05051a'); c.strokeStyle = '#6a7690'; c.lineWidth = 8; c.beginPath(); c.arc(100 + i * 200, 120, 48, 0, 6.28); c.stroke(); circ(c, 90 + i * 200, 110, 2, '#fff'); } floor('#232a40'); }
    else if (kind === 'cellar') { c.fillStyle = '#120c0e'; c.fillRect(0, 0, W, H); for (let y = 0; y < horizon; y += 28) for (let x = (y / 28) % 2 ? 0 : -30; x < W; x += 60) { rect(c, x + 1, y + 1, 58, 26, G2.shade('#3a2a2e', -0.2 + ((x + y) % 7) * 0.02)); } floor('#1c1214'); circ(c, W * 0.3, horizon - 60, 14, '#ffb347'); circ(c, W * 0.3, horizon - 60, 80, 'rgba(255,170,60,0.12)'); }
    else { sky(); floor(th.ground, G2.shade(th.ground, -0.4)); }
    if (tint) { c.fillStyle = tint; c.globalAlpha = 0.18; c.fillRect(0, 0, W, H); c.globalAlpha = 1; }
  };

  // ------------------------------------------------------------------ objetos clicáveis (point & click)
  A.prop = function (c, shape, x, y, w, h, t, ap) {
    c.save(); const cx = x + w / 2;
    switch (shape) {
      case 'door': G2.rrect(c, x, y, w, h, 6); c.fillStyle = '#6a4528'; c.fill(); rect(c, x + w * 0.1, y + h * 0.07, w * 0.8, h * 0.86, '#7e5532'); circ(c, x + w * 0.78, y + h * 0.52, Math.min(w, h) * 0.05, '#ffd166'); rect(c, x + w * 0.1, y + h * 0.48, w * 0.8, 3, 'rgba(0,0,0,0.25)'); break;
      case 'gate': for (let i = 0; i < 6; i++) rect(c, x + i * (w / 6), y, w / 12, h, '#3a3f4a'); rect(c, x, y + h * 0.2, w, 8, '#4a505c'); rect(c, x, y + h * 0.7, w, 8, '#4a505c'); circ(c, cx, y + h * 0.5, Math.min(w, h) * 0.09, '#ffd166'); break;
      case 'chest': rect(c, x, y + h * 0.35, w, h * 0.65, '#7a4a25'); G2.rrect(c, x, y, w, h * 0.5, 8); c.fillStyle = '#8f5a2c'; c.fill(); rect(c, x, y + h * 0.38, w, 6, '#ffd166'); rect(c, cx - 6, y + h * 0.36, 12, 16, '#ffd166'); break;
      case 'table': rect(c, x, y + h * 0.25, w, h * 0.14, '#8a5a35'); rect(c, x + w * 0.08, y + h * 0.39, w * 0.07, h * 0.6, '#6a4528'); rect(c, x + w * 0.85, y + h * 0.39, w * 0.07, h * 0.6, '#6a4528'); circ(c, cx, y + h * 0.18, Math.min(w, h) * 0.1, '#e8e0c0'); break;
      case 'window': rect(c, x, y, w, h, '#9fd0ff'); rect(c, x, y, w, h * 0.5, '#bfe0ff'); c.strokeStyle = '#5a3b25'; c.lineWidth = 6; c.strokeRect(x, y, w, h); c.beginPath(); c.moveTo(cx, y); c.lineTo(cx, y + h); c.moveTo(x, y + h / 2); c.lineTo(x + w, y + h / 2); c.stroke(); break;
      case 'plant': rect(c, x + w * 0.3, y + h * 0.7, w * 0.4, h * 0.3, '#a0522d'); for (let i = 0; i < 5; i++) { poly(c, [[cx, y + h * 0.72], [x + w * (0.05 + i * 0.22), y + h * (0.1 + (i % 2) * 0.15)], [cx + 4, y + h * 0.72]], ['#2f8f4a', '#3fae5e'][i % 2]); } break;
      case 'tree': rect(c, cx - w * 0.08, y + h * 0.5, w * 0.16, h * 0.5, '#5a3b25'); circ(c, cx, y + h * 0.32, w * 0.46, '#2f7a45'); circ(c, cx - w * 0.22, y + h * 0.4, w * 0.3, '#3a9455'); circ(c, cx + w * 0.22, y + h * 0.4, w * 0.3, '#2a6a3c'); break;
      case 'sign': rect(c, cx - 4, y + h * 0.4, 8, h * 0.6, '#5a3b25'); G2.rrect(c, x, y, w, h * 0.5, 6); c.fillStyle = '#c9a36a'; c.fill(); c.fillStyle = '#5a3b25'; for (let i = 0; i < 3; i++) rect(c, x + w * 0.15, y + h * (0.1 + i * 0.11), w * 0.7, 3, '#5a3b25'); break;
      case 'item': circ(c, cx, y + h / 2, Math.min(w, h) / 2, '#ffd166'); circ(c, cx - 3, y + h / 2 - 3, Math.min(w, h) / 5, 'rgba(255,255,255,0.7)'); break;
      case 'key': c.fillStyle = '#ffd166'; c.beginPath(); c.arc(x + w * 0.25, y + h * 0.5, Math.min(w, h) * 0.22, 0, 6.28); c.fill(); rect(c, x + w * 0.4, y + h * 0.45, w * 0.55, h * 0.1, '#ffd166'); rect(c, x + w * 0.8, y + h * 0.5, w * 0.08, h * 0.2, '#ffd166'); c.globalAlpha = 0.5 + 0.5 * Math.sin((t || 0) * 5); circ(c, x + w * 0.7, y + h * 0.3, 3, '#fff'); c.globalAlpha = 1; break;
      case 'painting': rect(c, x, y, w, h, '#5a3b25'); rect(c, x + 5, y + 5, w - 10, h - 10, '#1b2a5a'); circ(c, x + w * 0.7, y + h * 0.3, h * 0.12, '#f4f1d8'); poly(c, [[x + 5, y + h - 5], [x + w * 0.4, y + h * 0.5], [x + w * 0.7, y + h - 5]], '#2a6a4a'); break;
      case 'lamp': rect(c, cx - 3, y + h * 0.3, 6, h * 0.7, '#3a3f4a'); poly(c, [[x, y + h * 0.35], [x + w, y + h * 0.35], [cx + w * 0.2, y], [cx - w * 0.2, y]], '#ffd166'); circ(c, cx, y + h * 0.4, w * 1.2, 'rgba(255,220,130,0.12)'); break;
      case 'box': rect(c, x, y, w, h, '#a0703a'); rect(c, x, y, w, h * 0.18, '#b8844a'); c.strokeStyle = '#6a4528'; c.lineWidth = 3; c.strokeRect(x, y, w, h); rect(c, cx - 6, y + h * 0.45, 12, 8, '#ffd166'); break;
      case 'bed': rect(c, x, y + h * 0.4, w, h * 0.6, '#3a2a50'); rect(c, x, y + h * 0.25, w, h * 0.3, '#e8e0f0'); rect(c, x, y + h * 0.1, w * 0.18, h * 0.5, '#6a4a9a'); break;
      case 'book': rect(c, x, y + h * 0.3, w, h * 0.7, '#8a2b2b'); rect(c, x + 4, y + h * 0.3, 5, h * 0.7, '#5a1818'); rect(c, x + w * 0.2, y + h * 0.5, w * 0.6, 4, '#ffd166'); break;
      case 'machine': rect(c, x, y, w, h, '#3a4258'); rect(c, x + w * 0.1, y + h * 0.1, w * 0.8, h * 0.35, '#10162a'); for (let i = 0; i < 4; i++) circ(c, x + w * (0.2 + i * 0.2), y + h * 0.7, Math.min(w, h) * 0.06, ['#ff5a5a', '#5aff8a', '#5ab0ff', '#ffd166'][i]); c.globalAlpha = 0.6 + 0.4 * Math.sin((t || 0) * 4); rect(c, x + w * 0.15, y + h * 0.2, w * 0.4, 4, '#3aff9a'); c.globalAlpha = 1; break;
      case 'rock': poly(c, [[x, y + h], [x + w * 0.15, y + h * 0.35], [x + w * 0.5, y], [x + w * 0.85, y + h * 0.3], [x + w, y + h]], '#7a7f8a'); poly(c, [[x + w * 0.5, y], [x + w * 0.85, y + h * 0.3], [x + w * 0.6, y + h * 0.5]], '#9aa0ab'); break;
      case 'shelf': rect(c, x, y, w, h, '#5a3b25'); for (let r = 0; r < 3; r++) { rect(c, x + 4, y + h * (0.31 + r * 0.33), w - 8, 4, '#3a2414'); for (let i = 0; i < 5; i++) rect(c, x + 8 + i * (w - 16) / 5, y + h * (0.05 + r * 0.33), (w - 16) / 6, h * 0.24, ['#8a2b2b', '#2b5a8a', '#2b8a5a', '#8a6a2b'][(i + r) % 4]); } break;
      case 'fireplace': rect(c, x, y, w, h, '#6a6f7a'); rect(c, x + w * 0.15, y + h * 0.3, w * 0.7, h * 0.7, '#14100c'); for (let i = 0; i < 3; i++) poly(c, [[x + w * (0.3 + i * 0.15), y + h], [x + w * (0.35 + i * 0.15), y + h * (0.55 + 0.05 * Math.sin((t || 0) * 8 + i))], [x + w * (0.4 + i * 0.15), y + h]], ['#ff6a2b', '#ffb347', '#ffd166'][i]); break;
      case 'clock': circ(c, cx, y + h * 0.4, Math.min(w, h * 0.8) / 2, '#f4f1d8'); c.strokeStyle = '#3a2a1a'; c.lineWidth = 3; c.beginPath(); c.arc(cx, y + h * 0.4, Math.min(w, h * 0.8) / 2, 0, 6.28); c.moveTo(cx, y + h * 0.4); c.lineTo(cx, y + h * 0.18); c.moveTo(cx, y + h * 0.4); c.lineTo(cx + w * 0.18, y + h * 0.45); c.stroke(); rect(c, cx - w * 0.3, y + h * 0.8, w * 0.6, h * 0.2, '#5a3b25'); break;
      case 'statue': rect(c, x + w * 0.1, y + h * 0.85, w * 0.8, h * 0.15, '#8a8f9a'); rect(c, x + w * 0.25, y + h * 0.35, w * 0.5, h * 0.5, '#b8bdc8'); circ(c, cx, y + h * 0.25, w * 0.2, '#c8cdd8'); rect(c, x + w * 0.62, y + h * 0.4, w * 0.3, 6, '#b8bdc8'); break;
      case 'npc': A.sprite(c, ap, cx, y + h, h * 0.95, { dir: 'down', frame: (t || 0) * 4 }); break;
      default: rect(c, x, y, w, h, 'rgba(255,255,255,0.2)');
    }
    c.restore();
  };

  // ------------------------------------------------------------------ monstros (batalhas do RPG) e inimigos de rolagem
  A.monster = function (c, shape, cx, cy, s, color, t, hurt) {
    c.save(); c.translate(cx, cy); const bob = Math.sin((t || 0) * 3) * s * 0.04; c.translate(0, bob); if (hurt) c.globalAlpha = 0.5 + 0.5 * Math.sin((t || 0) * 60);
    const dark = G2.shade(color, -0.4), light = G2.shade(color, 0.35), eye = (x, y, r) => { circ(c, x, y, r, '#fff'); circ(c, x + r * 0.2, y, r * 0.5, '#111'); };
    c.fillStyle = 'rgba(0,0,0,0.25)'; c.beginPath(); c.ellipse(0, s * 0.45, s * 0.42, s * 0.08, 0, 0, 6.28); c.fill();
    if (shape === 'slime') { c.fillStyle = color; c.beginPath(); c.moveTo(-s * 0.4, s * 0.45); c.quadraticCurveTo(-s * 0.45, -s * 0.2, 0, -s * 0.3); c.quadraticCurveTo(s * 0.45, -s * 0.2, s * 0.4, s * 0.45); c.closePath(); c.fill(); circ(c, -s * 0.12, -s * 0.1, s * 0.07, light); eye(-s * 0.14, s * 0.05, s * 0.07); eye(s * 0.14, s * 0.05, s * 0.07); }
    else if (shape === 'bat') { const f = Math.sin((t || 0) * 12) * s * 0.18; poly(c, [[-s * 0.1, 0], [-s * 0.5, -s * 0.2 + f], [-s * 0.4, s * 0.1], [-s * 0.25, 0.05 * s]], dark); poly(c, [[s * 0.1, 0], [s * 0.5, -s * 0.2 + f], [s * 0.4, s * 0.1], [s * 0.25, 0.05 * s]], dark); circ(c, 0, 0, s * 0.2, color); poly(c, [[-s * 0.15, -s * 0.15], [-s * 0.08, -s * 0.34], [-s * 0.02, -s * 0.15]], color); poly(c, [[s * 0.15, -s * 0.15], [s * 0.08, -s * 0.34], [s * 0.02, -s * 0.15]], color); circ(c, -s * 0.07, -s * 0.02, s * 0.04, '#ff4'); circ(c, s * 0.07, -s * 0.02, s * 0.04, '#ff4'); }
    else if (shape === 'skull') { circ(c, 0, -s * 0.08, s * 0.32, '#eee'); rect(c, -s * 0.2, s * 0.12, s * 0.4, s * 0.2, '#eee'); circ(c, -s * 0.12, -s * 0.08, s * 0.08, '#111'); circ(c, s * 0.12, -s * 0.08, s * 0.08, '#111'); for (let i = 0; i < 4; i++) rect(c, -s * 0.16 + i * s * 0.1, s * 0.2, 2, s * 0.12, '#111'); }
    else if (shape === 'goblin') { rect(c, -s * 0.22, 0, s * 0.44, s * 0.4, dark); circ(c, 0, -s * 0.12, s * 0.26, color); poly(c, [[-s * 0.22, -s * 0.15], [-s * 0.5, -s * 0.28], [-s * 0.2, -s * 0.03]], color); poly(c, [[s * 0.22, -s * 0.15], [s * 0.5, -s * 0.28], [s * 0.2, -s * 0.03]], color); eye(-s * 0.1, -s * 0.12, s * 0.06); eye(s * 0.1, -s * 0.12, s * 0.06); rect(c, s * 0.28, -s * 0.05, s * 0.07, s * 0.4, '#8a5a35'); }
    else if (shape === 'wolf') { c.fillStyle = color; c.beginPath(); c.ellipse(0, s * 0.1, s * 0.4, s * 0.22, 0, 0, 6.28); c.fill(); circ(c, -s * 0.38, -s * 0.05, s * 0.2, color); poly(c, [[-s * 0.5, -s * 0.2], [-s * 0.45, -s * 0.4], [-s * 0.35, -s * 0.2]], dark); poly(c, [[-s * 0.3, -s * 0.2], [-s * 0.25, -s * 0.4], [-s * 0.18, -s * 0.15]], dark); eye(-s * 0.42, -s * 0.07, s * 0.05); for (let i = 0; i < 4; i++) rect(c, -s * 0.3 + i * s * 0.2, s * 0.25, s * 0.07, s * 0.22, dark); poly(c, [[s * 0.38, 0], [s * 0.62, -s * 0.15], [s * 0.4, s * 0.12]], color); }
    else if (shape === 'ghost') { c.fillStyle = color; c.globalAlpha *= 0.85; c.beginPath(); c.arc(0, -s * 0.05, s * 0.34, Math.PI, 0); c.lineTo(s * 0.34, s * 0.4); for (let i = 0; i < 4; i++) c.quadraticCurveTo(s * (0.28 - i * 0.18), s * 0.2, s * (0.17 - i * 0.17), s * 0.4); c.lineTo(-s * 0.34, s * 0.4); c.closePath(); c.fill(); c.globalAlpha = 1; circ(c, -s * 0.12, -s * 0.08, s * 0.07, '#111'); circ(c, s * 0.12, -s * 0.08, s * 0.07, '#111'); }
    else if (shape === 'dragon') { const f = Math.sin((t || 0) * 4) * s * 0.06; poly(c, [[-s * 0.1, -s * 0.1], [-s * 0.7, -s * 0.5 + f], [-s * 0.45, s * 0.05]], dark); poly(c, [[s * 0.1, -s * 0.1], [s * 0.7, -s * 0.5 + f], [s * 0.45, s * 0.05]], dark); c.fillStyle = color; c.beginPath(); c.ellipse(0, s * 0.1, s * 0.34, s * 0.34, 0, 0, 6.28); c.fill(); circ(c, 0, -s * 0.28, s * 0.22, color); poly(c, [[-s * 0.16, -s * 0.4], [-s * 0.1, -s * 0.62], [-s * 0.03, -s * 0.4]], light); poly(c, [[s * 0.16, -s * 0.4], [s * 0.1, -s * 0.62], [s * 0.03, -s * 0.4]], light); circ(c, -s * 0.08, -s * 0.3, s * 0.05, '#ffd166'); circ(c, s * 0.08, -s * 0.3, s * 0.05, '#ffd166'); rect(c, -s * 0.12, -s * 0.2, s * 0.24, s * 0.06, '#111'); poly(c, [[s * 0.3, s * 0.25], [s * 0.65, s * 0.4], [s * 0.3, s * 0.4]], color); }
    else { circ(c, 0, 0, s * 0.3, color); circ(c, 0, 0, s * 0.18, light); circ(c, -s * 0.06, -s * 0.06, s * 0.06, '#fff'); for (let i = 0; i < 6; i++) { const a = (t || 0) * 2 + i * 1.047; circ(c, Math.cos(a) * s * 0.42, Math.sin(a) * s * 0.42, s * 0.05, light); } }
    c.restore();
  };

  // ------------------------------------------------------------------ fundo com paralaxe (plataforma e side scroller)
  A.parallax = function (c, theme, camX, W, H, t) {
    const th = G2.theme(theme);
    c.fillStyle = grad(c, 0, 0, 0, H, [[0, th.sky[0]], [1, th.sky[1]]]); c.fillRect(0, 0, W, H);
    const night = theme === 'night' || theme === 'space' || theme === 'horror' || theme === 'dungeon';
    if (night) stars(c, W, H, theme, 50, t); else circ(c, W * 0.82, H * 0.2, 26, 'rgba(255,255,230,0.55)');
    const layer = (f, y, amp, col, n, seed) => { const off = -((camX * f) % W); for (let k = 0; k < 2; k++) { c.save(); c.translate(off + k * W, 0); hills(c, W, y, amp, seed, col, n); c.restore(); } };
    if (theme !== 'space') { layer(0.15, H * 0.62, H * 0.2, G2.mix(th.wall, th.sky[1], 0.35), 6, theme + '1'); layer(0.3, H * 0.74, H * 0.16, G2.mix(th.wall, th.sky[1], 0.12), 7, theme + '2'); }
    if (theme === 'forest' || theme === 'fantasy' || theme === 'snow') { const off = -((camX * 0.5) % W); for (let k = 0; k < 2; k++) { c.save(); c.translate(off + k * W, 0); trees(c, W, H * 0.92, theme + 'tr', 10, H * 0.3, G2.mix(th.grass, th.sky[1], 0.25), G2.mix('#3a2814', th.sky[1], 0.4)); c.restore(); } }
    if (theme === 'city') { const off = -((camX * 0.4) % W); for (let k = 0; k < 2; k++) { c.save(); c.translate(off + k * W, 0); const r = G2.rng('city'); for (let i = 0; i < 10; i++) { const bw = 40 + r() * 50, bh = 60 + r() * 120; rect(c, i * W / 9, H * 0.85 - bh, bw, bh, G2.shade(th.wall, -0.4)); windowsGrid(c, i * W / 9 + 4, H * 0.85 - bh + 6, bw - 8, bh - 12, 3, Math.floor(bh / 24), 0.4, i); } c.restore(); } }
    if (!night) { const off = -((camX * 0.12 + (t || 0) * 6) % W); for (let k = 0; k < 2; k++) for (let i = 0; i < 4; i++) { const x = off + k * W + i * W / 3.2, y = 30 + (i % 2) * 40; circ(c, x, y, 18, 'rgba(255,255,255,0.7)'); circ(c, x + 18, y + 4, 14, 'rgba(255,255,255,0.7)'); circ(c, x - 16, y + 6, 12, 'rgba(255,255,255,0.7)'); } }
  };

  // seed de ruído usada em tiles (variação estável por posição)
  A.cellRand = (x, y) => G2.rng(x * 73856093 ^ y * 19349663)();

  // utilidades de HUD
  A.heart = function (c, x, y, s, on) { c.fillStyle = on ? '#ff4d6d' : 'rgba(255,255,255,0.18)'; c.beginPath(); c.moveTo(x, y + s * 0.3); c.bezierCurveTo(x, y - s * 0.15, x - s * 0.55, y - s * 0.1, x - s * 0.5, y + s * 0.3); c.bezierCurveTo(x - s * 0.45, y + s * 0.6, x, y + s * 0.75, x, y + s); c.bezierCurveTo(x, y + s * 0.75, x + s * 0.45, y + s * 0.6, x + s * 0.5, y + s * 0.3); c.bezierCurveTo(x + s * 0.55, y - s * 0.1, x, y - s * 0.15, x, y + s * 0.3); c.fill(); };
})(typeof window !== 'undefined' ? window : globalThis);
