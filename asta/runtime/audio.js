/* ASTA runtime — áudio procedural (WebAudio): ambiente, música generativa, passos e trovões. */
(function () {
  'use strict';
  const RT = window.RT;
  const SCALES = {
    major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10], dorian: [0, 2, 3, 5, 7, 9, 10],
    phrygian: [0, 1, 3, 5, 7, 8, 10], pentatonic: [0, 2, 4, 7, 9], lydian: [0, 2, 4, 6, 7, 9, 11],
  };
  const NOTES = { C: 0, 'C#': 1, D: 2, 'D#': 3, E: 4, F: 5, 'F#': 6, G: 7, 'G#': 8, A: 9, 'A#': 10, B: 11 };
  const MOOD = {
    calm: { prog: [0, 3, 4, 0], beats: 8, p: 0.35, sub: 1 },
    tense: { prog: [0, 1, 0, 5], beats: 4, p: 0.28, sub: 1, drum: 0.3 },
    mysterious: { prog: [0, 2, 5, 3], beats: 8, p: 0.32, sub: 1 },
    epic: { prog: [0, 5, 3, 4], beats: 4, p: 0.7, sub: 2, drum: 1 },
    melancholic: { prog: [0, 5, 2, 4], beats: 8, p: 0.3, sub: 1 },
    joyful: { prog: [0, 4, 5, 3], beats: 4, p: 0.75, sub: 2 },
  };

  RT.Audio = function (spec, ux) {
    this.spec = spec || {};
    this.ctx = null;
    this.vol = { master: 0.8, music: 1, ambience: 1 };
    this.muted = false;
    this.night = 0;
    this.weather = 'clear';
    this.biome = 'temperate';
    this.running = false;
    this._timers = [];
  };
  const A = RT.Audio.prototype;

  A.start = function (opts) {
    if (this.ctx) { this.ctx.resume(); return; }
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    opts = opts || {};
    this.biome = opts.biome || 'temperate';
    this.weather = opts.weather || 'clear';
    const ctx = (this.ctx = new Ctx());
    this.master = ctx.createGain(); this.master.gain.value = this.muted ? 0 : this.vol.master;
    const comp = ctx.createDynamicsCompressor(); this.master.connect(comp); comp.connect(ctx.destination);
    this.ambBus = ctx.createGain(); this.ambBus.connect(this.master);
    this.musBus = ctx.createGain(); this.musBus.connect(this.master);
    this.sfxBus = ctx.createGain(); this.sfxBus.connect(this.master);
    // ruído (branco) em loop
    const len = ctx.sampleRate * 3, buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
    let b0 = 0, b1 = 0, b2 = 0;
    for (let i = 0; i < len; i++) { const w = Math.random() * 2 - 1; b0 = 0.99765 * b0 + w * 0.099046; b1 = 0.963 * b1 + w * 0.2965164; b2 = 0.57 * b2 + w * 1.0526913; d[i] = (b0 + b1 + b2 + w * 0.1848) * 0.2; }
    this.noiseBuf = buf;
    this._ambience();
    this._music();
    this.running = true;
    document.addEventListener('visibilitychange', () => { if (!this.ctx) return; document.hidden ? this.ctx.suspend() : this.ctx.resume(); });
  };

  A.setMasterVolume = function (v) { this.vol.master = v; if (this.master) this.master.gain.value = this.muted ? 0 : v; };
  A.setMusicVolume = function (v) { this.vol.music = v; if (this.musBus) this.musBus.gain.value = v; if (this.fileEl) this.fileEl.volume = Math.min(1, v * ((this.spec.music && this.spec.music.volume) || 0.4)); };
  A.setAmbienceVolume = function (v) { this.vol.ambience = v; if (this.ambBus) this.ambBus.gain.value = v; };
  A.setMuted = function (m) { this.muted = m; if (this.master) this.master.gain.value = m ? 0 : this.vol.master; if (this.fileEl) this.fileEl.muted = m; };

  // ----- utilidades
  A._noise = function (type, freq, q, gain, out) {
    const ctx = this.ctx, src = ctx.createBufferSource(); src.buffer = this.noiseBuf; src.loop = true;
    src.loopStart = Math.random() * 1.5;
    const f = ctx.createBiquadFilter(); f.type = type; f.frequency.value = freq; f.Q.value = q || 0.7;
    const g = ctx.createGain(); g.gain.value = gain;
    src.connect(f); f.connect(g); g.connect(out || this.ambBus); src.start();
    return { src, f, g };
  };
  A._lfo = function (rate, depth, param) {
    const o = this.ctx.createOscillator(), g = this.ctx.createGain();
    o.frequency.value = rate; g.gain.value = depth; o.connect(g); g.connect(param); o.start();
    return o;
  };
  A._every = function (minS, maxS, fn) {
    const loop = () => { fn(); this._timers.push(setTimeout(loop, (minS + Math.random() * (maxS - minS)) * 1000)); };
    this._timers.push(setTimeout(loop, minS * 1000 * Math.random()));
  };
  A._tone = function (freq, t, dur, type, gain, out, glideTo) {
    const ctx = this.ctx, o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t);
    if (glideTo) o.frequency.exponentialRampToValueAtTime(glideTo, t + dur * 0.6);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(gain, t + Math.min(0.03, dur / 3)); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(out || this.sfxBus); o.start(t); o.stop(t + dur + 0.05);
  };

  // ----- ambiente
  A._ambience = function () {
    const a = this.spec.ambience || 'wind', v = this.spec.ambience_volume != null ? this.spec.ambience_volume : 0.5, ctx = this.ctx;
    const wind = (g, f) => {
      const n = this._noise('bandpass', f || 420, 0.6, g * v);
      this._lfo(0.07, (f || 420) * 0.5, n.f.frequency); this._lfo(0.11, g * v * 0.5, n.g.gain);
      return n;
    };
    if (a === 'wind') wind(0.35);
    else if (a === 'desert') wind(0.28, 900);
    else if (a === 'forest') { wind(0.16); this._wildlife(v); }
    else if (a === 'night') { wind(0.1); this._wildlife(v, true); }
    else if (a === 'rain') this._rain(v);
    else if (a === 'ocean') {
      const n = this._noise('lowpass', 650, 0.5, 0.3 * v); this._lfo(0.09, 0.22 * v, n.g.gain);
      this._noise('highpass', 3500, 0.5, 0.025 * v);
    } else if (a === 'city') {
      this._noise('lowpass', 240, 0.5, 0.12 * v);
      const n = this._noise('bandpass', 700, 0.8, 0.035 * v); this._lfo(0.3, 0.02 * v, n.g.gain);
      const o = ctx.createOscillator(), g = ctx.createGain(); o.frequency.value = 62; g.gain.value = 0.02 * v; o.connect(g); g.connect(this.ambBus); o.start();
    } else if (a === 'cave') {
      [48, 71].forEach((f, i) => { const o = ctx.createOscillator(), g = ctx.createGain(); o.frequency.value = f; g.gain.value = (0.07 - i * 0.03) * v; o.connect(g); g.connect(this.ambBus); o.start(); });
      this._every(2.5, 7, () => this._tone(1100 + Math.random() * 500, ctx.currentTime, 0.3, 'sine', 0.05 * v, this.ambBus, 600));
    }
    if ((this.weather === 'rain' || this.weather === 'storm') && a !== 'rain') this._rain(v);
    if (this.weather === 'snow' && a !== 'wind') wind(0.18);
  };
  A._rain = function (v) {
    this._noise('highpass', 1300, 0.5, 0.2 * v); this._noise('lowpass', 7000, 0.4, 0.07 * v); this._noise('lowpass', 220, 0.5, 0.1 * v);
  };
  A._wildlife = function (v, nightOnly) {
    const ctx = this.ctx;
    this.birds = ctx.createGain(); this.birds.gain.value = nightOnly ? 0 : 1; this.birds.connect(this.ambBus);
    this._every(1.2, 4.5, () => {
      if (this.night > 0.6) return;
      const n = 1 + Math.floor(Math.random() * 3), f0 = 2300 + Math.random() * 1800;
      for (let i = 0; i < n; i++) this._tone(f0 * (1 + i * 0.07), ctx.currentTime + i * 0.13, 0.11, 'sine', 0.05 * v, this.birds, f0 * 1.35);
    });
    // grilos
    const o = ctx.createOscillator(), g = ctx.createGain(), base = ctx.createGain();
    o.frequency.value = 4300; g.gain.value = 0; base.gain.value = 0.012 * v;
    o.connect(g); g.connect(base); base.connect(this.ambBus); o.start();
    this._lfo(13, 0.5, g.gain); const dc = ctx.createConstantSource ? ctx.createConstantSource() : null;
    if (dc) { dc.offset.value = 0.5; dc.connect(g.gain); dc.start(); }
    this.crickets = base;
    if (nightOnly) base.gain.value = 0.02 * v;
  };

  // ----- música generativa
  A._music = function () {
    const m = this.spec.music || {};
    if (m.enabled === false) return;
    const ctx = this.ctx, vol = (m.volume != null ? m.volume : 0.35);
    if (m.file) {
      try {
        const el = new Audio('sound/user/' + encodeURIComponent(m.file)); el.loop = true; el.volume = Math.min(1, vol); this.fileEl = el;
        el.muted = this.muted; el.play().catch(() => {});
        return;
      } catch (e) { /* cai no procedural */ }
    }
    const scale = SCALES[m.scale] || SCALES.minor, root = 48 + (NOTES[m.root] || 0), mood = MOOD[m.mood] || MOOD.calm;
    const beat = 60 / (m.tempo || 72), self = this;
    const hz = (midi) => 440 * Math.pow(2, (midi - 69) / 12);
    const note = (deg, oct) => { const n = scale.length, o = Math.floor(deg / n), i = ((deg % n) + n) % n; return root + scale[i] + 12 * (o + oct); };
    const out = ctx.createGain(); out.gain.value = vol * 0.9; out.connect(this.musBus);
    const delay = ctx.createDelay(1.5); delay.delayTime.value = beat * 0.75; const fb = ctx.createGain(); fb.gain.value = 0.38;
    const dl = ctx.createBiquadFilter(); dl.type = 'lowpass'; dl.frequency.value = 2200;
    delay.connect(dl); dl.connect(fb); fb.connect(delay); dl.connect(out);
    const dry = ctx.createGain(); dry.gain.value = 1; dry.connect(out); dry.connect(delay);
    let chordIdx = 0, nextChord = ctx.currentTime + 0.3, nextBeat = nextChord, beatN = 0;
    const pad = (degs, t, dur) => {
      degs.forEach((d, i) => {
        [-6, 6].forEach((det) => {
          const o = ctx.createOscillator(), g = ctx.createGain(), f = ctx.createBiquadFilter();
          o.type = 'triangle'; o.frequency.value = hz(note(d, 1)); o.detune.value = det + i;
          f.type = 'lowpass'; f.frequency.value = 900;
          g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(0.05, t + Math.min(2, dur * 0.3)); g.gain.linearRampToValueAtTime(0.0001, t + dur);
          o.connect(f); f.connect(g); g.connect(out); o.start(t); o.stop(t + dur + 0.1);
        });
      });
      const b = ctx.createOscillator(), bg = ctx.createGain(); b.type = 'sine'; b.frequency.value = hz(note(degs[0], -1));
      bg.gain.setValueAtTime(0.0001, t); bg.gain.linearRampToValueAtTime(0.16, t + 0.4); bg.gain.linearRampToValueAtTime(0.0001, t + dur);
      b.connect(bg); bg.connect(out); b.start(t); b.stop(t + dur + 0.1);
    };
    const tick = () => {
      if (!self.ctx || self.ctx.state === 'closed') return;
      const now = ctx.currentTime;
      while (nextChord < now + 0.5) {
        const d = mood.prog[chordIdx % mood.prog.length]; self.chord = d;
        pad([d, d + 2, d + 4], nextChord, mood.beats * beat * 1.05);
        nextChord += mood.beats * beat; chordIdx++;
      }
      const step = beat / mood.sub;
      while (nextBeat < now + 0.5) {
        const d = self.chord || 0;
        if (Math.random() < mood.p) {
          const choices = [d, d + 2, d + 4, d + 7, d + 1, d + 3, d + 5];
          const deg = choices[Math.floor(Math.random() * choices.length)];
          self._tone(hz(note(deg, 2)), nextBeat, beat * 2.2, 'triangle', 0.075, dry);
        }
        if (mood.drum && beatN % 4 === 0 && Math.random() < mood.drum) self._tone(95, nextBeat, 0.4, 'sine', 0.2, out, 42);
        nextBeat += step; beatN++;
      }
    };
    tick(); this._musicTimer = setInterval(tick, 120);
  };

  // ----- efeitos
  A.footstep = function (run, biome) {
    if (!this.ctx) return;
    const surf = { snow: [650, 0.5, 0.1], desert: [520, 0.5, 0.1], island: [520, 0.5, 0.1], urban: [1700, 1.2, 0.14], wasteland: [700, 0.6, 0.1], swamp: [420, 0.6, 0.13] }[biome || this.biome] || [950, 0.7, 0.11];
    const ctx = this.ctx, t = ctx.currentTime, src = ctx.createBufferSource(); src.buffer = this.noiseBuf;
    const f = ctx.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = surf[0] * (0.85 + Math.random() * 0.3); f.Q.value = surf[1];
    const g = ctx.createGain(); const vol = surf[2] * (run ? 1.3 : 1);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + 0.012); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.11);
    src.connect(f); f.connect(g); g.connect(this.sfxBus); src.start(t, Math.random() * 2, 0.15);
  };
  A.thunder = function () {
    if (!this.ctx) return;
    const ctx = this.ctx, t = ctx.currentTime, src = ctx.createBufferSource(); src.buffer = this.noiseBuf;
    const f = ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = 170;
    const g = ctx.createGain(); g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.9, t + 0.08); g.gain.exponentialRampToValueAtTime(0.0001, t + 3.6);
    src.connect(f); f.connect(g); g.connect(this.sfxBus); src.start(t, Math.random(), 4);
  };
  A.update = function (night) {
    this.night = night;
    if (!this.ctx) return;
    if (this.birds) this.birds.gain.value = 1 - night;
    if (this.crickets && this.spec.ambience !== 'night') this.crickets.gain.value = night * 0.02 * ((this.spec.ambience === 'forest') ? 1 : 0.4);
  };
  A.stop = function () {
    this._timers.forEach(clearTimeout); clearInterval(this._musicTimer);
    if (this.fileEl) this.fileEl.pause();
    if (this.ctx) this.ctx.close();
    this.ctx = null;
  };
})();
