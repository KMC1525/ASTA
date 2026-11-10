// Game Engine → Sound: inspirada no Audacity. Faixas com forma de onda, seleção, cortar/copiar/colar, efeitos, redução de ruído de fundo, gravação do microfone e geração por IA (efeitos, música, voz).
// Conexões opcionais: enviar os sons para o Studio e para o Canvas. O áudio é editado no navegador (Web Audio) e gravado em WAV em game/assets/sound/ ao «Aplicar ao jogo».
import { api } from '../api.js';
import { t } from '../i18n.js';
import { b64ToBlob, btn, flatFiles, ibtn, numInput, promptPanel, propRow, stem } from '../engine_ui.js';
import { confirmDialog, debounce, h, icon, modal, select, toast } from '../ui.js';

let uid = 0; const nid = () => 't' + Date.now().toString(36) + (++uid);
const COLORS = ['#7cb7ff', '#7ee2a8', '#f2c46d', '#c3a6ff', '#ff8fab', '#7cd4f2'];
const EVENTS = [['', '—'], ['music', 'Música de fundo'], ['coin', 'Moeda'], ['jump', 'Pulo'], ['hit', 'Dano'], ['win', 'Vitória'], ['lose', 'Derrota'], ['powerup', 'Item/cura'], ['shoot', 'Tiro'], ['select', 'Falar/selecionar'], ['door', 'Porta'], ['place', 'Colocar (AR)']];

// ============================================================================ DSP (puro: testável)
export const DSP = {
  fft(re, im, inverse) {
    const n = re.length;
    for (let i = 1, j = 0; i < n; i++) { let bit = n >> 1; for (; j & bit; bit >>= 1) j ^= bit; j ^= bit; if (i < j) { let t1 = re[i]; re[i] = re[j]; re[j] = t1; t1 = im[i]; im[i] = im[j]; im[j] = t1; } }
    for (let len = 2; len <= n; len <<= 1) {
      const ang = 2 * Math.PI / len * (inverse ? -1 : 1), wr = Math.cos(ang), wi = Math.sin(ang);
      for (let i = 0; i < n; i += len) { let cr = 1, ci = 0; for (let k = 0; k < len / 2; k++) { const ur = re[i + k], ui = im[i + k], vr = re[i + k + len / 2] * cr - im[i + k + len / 2] * ci, vi = re[i + k + len / 2] * ci + im[i + k + len / 2] * cr; re[i + k] = ur + vr; im[i + k] = ui + vi; re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi; const nr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = nr; } }
    }
    if (inverse) for (let i = 0; i < n; i++) { re[i] /= n; im[i] /= n; }
  },
  // perfil de ruído: espectro médio de magnitude de um trecho (só ruído)
  noiseProfile(data, size = 2048) {
    const hop = size / 4, win = DSP.hann(size), prof = new Float32Array(size / 2 + 1); let frames = 0;
    for (let s = 0; s + size <= data.length; s += hop) { const re = new Float32Array(size), im = new Float32Array(size); for (let i = 0; i < size; i++) re[i] = data[s + i] * win[i]; DSP.fft(re, im); for (let k = 0; k <= size / 2; k++) prof[k] += Math.hypot(re[k], im[k]); frames++; }
    if (frames) for (let k = 0; k < prof.length; k++) prof[k] /= frames; return prof;
  },
  hann(n) { const w = new Float32Array(n); for (let i = 0; i < n; i++) w[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / n); return w; },
  // subtração espectral com piso: reduz o que se parece com o perfil e preserva o resto
  denoise(data, prof, strength = 1.2, floor = 0.08, size = 2048) {
    const hop = size / 4, win = DSP.hann(size), out = new Float32Array(data.length), norm = new Float32Array(data.length);
    for (let s = -size + hop; s < data.length; s += hop) {   // começa antes do 1º amostra: as bordas também ficam cobertas por quadros inteiros
      const re = new Float32Array(size), im = new Float32Array(size); for (let i = 0; i < size; i++) re[i] = (data[s + i] || 0) * win[i];
      DSP.fft(re, im);
      for (let k = 0; k <= size / 2; k++) { const m = Math.hypot(re[k], im[k]) + 1e-9, g = Math.max(floor, 1 - strength * prof[k] / m); re[k] *= g; im[k] *= g; if (k > 0 && k < size / 2) { re[size - k] = re[k]; im[size - k] = -im[k]; } }
      DSP.fft(re, im, true);
      for (let i = 0; i < size; i++) { const j = s + i; if (j >= 0 && j < data.length) { out[j] += re[i] * win[i]; norm[j] += win[i] * win[i]; } }
    }
    for (let i = 0; i < out.length; i++) out[i] = norm[i] > 1e-3 ? out[i] / norm[i] : data[i] * floor; return out;
  },
  gate(data, rate, thresholdDb = -45, attack = 0.005, release = 0.12) {
    const out = new Float32Array(data.length), th = Math.pow(10, thresholdDb / 20), a = Math.exp(-1 / (attack * rate)), r = Math.exp(-1 / (release * rate)); let env = 0, g = 0;
    for (let i = 0; i < data.length; i++) { const x = Math.abs(data[i]); env = x > env ? a * env + (1 - a) * x : r * env + (1 - r) * x; const target = env > th ? 1 : 0; g += (target - g) * (target > g ? 0.01 : 0.002); out[i] = data[i] * g; }
    return out;
  },
  biquad(data, rate, type, freq, q = 0.707) {
    const w0 = 2 * Math.PI * freq / rate, al = Math.sin(w0) / (2 * q), cs = Math.cos(w0); let b0, b1, b2; const a0 = 1 + al, a1 = -2 * cs, a2 = 1 - al;
    if (type === 'lowpass') { b0 = (1 - cs) / 2; b1 = 1 - cs; b2 = (1 - cs) / 2; } else { b0 = (1 + cs) / 2; b1 = -(1 + cs); b2 = (1 + cs) / 2; }
    const out = new Float32Array(data.length); let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (let i = 0; i < data.length; i++) { const x = data[i], y = (b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2) / a0; out[i] = y; x2 = x1; x1 = x; y2 = y1; y1 = y; }
    return out;
  },
  resample(data, ratio) { const n = Math.max(1, Math.floor(data.length / ratio)), out = new Float32Array(n); for (let i = 0; i < n; i++) { const p = i * ratio, i0 = Math.floor(p), f = p - i0; out[i] = (data[i0] || 0) * (1 - f) + (data[i0 + 1] || 0) * f; } return out; },
  peak(data) { let m = 0; for (let i = 0; i < data.length; i++) { const v = Math.abs(data[i]); if (v > m) m = v; } return m; },
  encodeWav(channels, rate) {
    const n = channels[0].length, nc = channels.length, buf = new ArrayBuffer(44 + n * nc * 2), v = new DataView(buf), w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    w(0, 'RIFF'); v.setUint32(4, 36 + n * nc * 2, true); w(8, 'WAVE'); w(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, nc, true); v.setUint32(24, rate, true); v.setUint32(28, rate * nc * 2, true); v.setUint16(32, nc * 2, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, n * nc * 2, true);
    let o = 44; for (let i = 0; i < n; i++) for (let c = 0; c < nc; c++) { const s = Math.max(-1, Math.min(1, channels[c][i])); v.setInt16(o, s < 0 ? s * 32768 : s * 32767, true); o += 2; }
    return new Blob([buf], { type: 'audio/wav' });
  },
};
window.ASTA_DSP = DSP;   // usado pelos testes de navegador

export default async function render(body, E) {
  const AC = window.AudioContext || window.webkitAudioContext; const ac = new AC(); E.onCleanup(() => { try { stopPlay(); ac.close(); } catch (e) { /* ok */ } });
  const P = { name: 'meu-som', tracks: [], sel: { track: '', a: 0, b: 0 }, head: 0, clip: null, noise: null, dirty: false };
  const V = { pps: 120, scroll: 0, rec: null, playing: null, loop: false };
  let undo = [], redo = [];
  const trackById = (id) => P.tracks.find((x) => x.id === id);
  const selTrack = () => trackById(P.sel.track) || P.tracks[0];
  const duration = () => Math.max(2, ...P.tracks.map((x) => x.start + x.buf.duration));
  const rate = () => (P.tracks[0] ? P.tracks[0].buf.sampleRate : ac.sampleRate);

  function mkBuf(channels, sr) { const b = ac.createBuffer(channels.length, channels[0].length, sr); channels.forEach((d, i) => b.copyToChannel(d, i)); return b; }
  const chans = (buf) => Array.from({ length: buf.numberOfChannels }, (_, i) => buf.getChannelData(i));
  const pushUndo = () => { undo.push({ tracks: P.tracks.map((x) => Object.assign({}, x)), sel: Object.assign({}, P.sel) }); if (undo.length > 25) undo.shift(); redo = []; markDirty(); };
  const restore = (e) => { const cur = { tracks: P.tracks.map((x) => Object.assign({}, x)), sel: Object.assign({}, P.sel) }; P.tracks = e.tracks.map((x) => Object.assign({}, x)); P.sel = e.sel; paintAll(); markDirty(); return cur; };
  const doUndo = () => { const e = undo.pop(); if (e) redo.push(restore(e)); }, doRedo = () => { const e = redo.pop(); if (e) undo.push(restore(e)); };
  const markDirty = () => { P.dirty = true; status.textContent = t('não salvo'); };

  // ---------------------------------------------------------------- faixas
  function addTrack(buf, name) { pushUndo(); const tr = { id: nid(), name: name || t('Faixa {n}', { n: P.tracks.length + 1 }), buf, start: 0, vol: 1, pan: 0, mute: false, solo: false, color: COLORS[P.tracks.length % COLORS.length] }; P.tracks.push(tr); P.sel = { track: tr.id, a: 0, b: 0 }; paintAll(); return tr; }
  async function decode(arrayBuffer) { return ac.decodeAudioData(arrayBuffer.slice(0)); }
  async function addFile(file) { try { addTrack(await decode(await file.arrayBuffer()), file.name.replace(/\.[^.]+$/, '')); } catch (e) { toast(t('Não consegui abrir «{n}» como áudio.', { n: file.name }), 'err'); } }
  const range = () => { const tr = selTrack(); if (!tr) return null; const a = P.sel.b > P.sel.a ? P.sel.a - tr.start : 0, b = P.sel.b > P.sel.a ? P.sel.b - tr.start : tr.buf.duration; return { tr, a: Math.max(0, a), b: Math.min(tr.buf.duration, b), whole: !(P.sel.b > P.sel.a) }; };
  function edit(fn, label) {
    const r = range(); if (!r) { toast(t('Não há faixa para editar.')); return; } const sr = r.tr.buf.sampleRate, i0 = Math.floor(r.a * sr), i1 = Math.floor(r.b * sr); if (i1 <= i0) { toast(t('Selecione um trecho.')); return; }
    pushUndo(); const src = chans(r.tr.buf), out = src.map((d) => { const seg = d.slice(i0, i1), res = fn(seg, sr, d); return [d.slice(0, i0), res, d.slice(i1)]; });
    const len = out[0][0].length + out[0][1].length + out[0][2].length, merged = out.map(([a, b, c]) => { const m = new Float32Array(len); m.set(a, 0); m.set(b, a.length); m.set(c, a.length + b.length); return m; });
    r.tr.buf = mkBuf(merged, sr); const newEnd = r.a + out[0][1].length / sr; P.sel = { track: r.tr.id, a: r.tr.start + r.a, b: r.tr.start + newEnd }; paintAll(); if (label) toast(label, 'ok');
  }
  const fx = {
    gain: (db) => edit((d) => d.map((v) => v * Math.pow(10, db / 20)), ''), fadeIn: () => edit((d) => { const o = new Float32Array(d.length); for (let i = 0; i < d.length; i++) o[i] = d[i] * (i / d.length); return o; }), fadeOut: () => edit((d) => { const o = new Float32Array(d.length); for (let i = 0; i < d.length; i++) o[i] = d[i] * (1 - i / d.length); return o; }),
    normalize: () => { const r = range(); if (!r) return; const peak = Math.max(...chans(r.tr.buf).map((d) => DSP.peak(d.slice(Math.floor(r.a * r.tr.buf.sampleRate), Math.floor(r.b * r.tr.buf.sampleRate))))); if (!peak) return; edit((d) => d.map((v) => v * 0.97 / peak)); },
    reverse: () => edit((d) => d.slice().reverse()), silence: () => edit((d) => new Float32Array(d.length)), invert: () => edit((d) => d.map((v) => -v)),
    speed: (ratio) => edit((d) => DSP.resample(d, ratio)), echo: (delay, decay) => edit((d, sr) => { const n = Math.floor(delay * sr), o = new Float32Array(d.length + n * 4); o.set(d); for (let k = 1; k <= 4; k++) for (let i = 0; i < d.length; i++) o[i + n * k] += d[i] * Math.pow(decay, k); return o; }),
    lowpass: (f) => edit((d, sr) => DSP.biquad(d, sr, 'lowpass', f)), highpass: (f) => edit((d, sr) => DSP.biquad(d, sr, 'highpass', f)), gate: (db) => edit((d, sr) => DSP.gate(d, sr, db)),
    denoise: (strength) => { const r = range(); if (!r) return; const prof = P.noise || (() => { const d = r.tr.buf.getChannelData(0); const q = quietest(d, r.tr.buf.sampleRate); return DSP.noiseProfile(q); })(); edit((d) => DSP.denoise(d, prof, strength), t('Ruído de fundo reduzido')); },
  };
  function quietest(d, sr) { const w = Math.floor(sr * 0.25); let best = 1e9, at = 0; for (let s = 0; s + w < d.length; s += Math.floor(w / 2)) { let e = 0; for (let i = s; i < s + w; i += 8) e += d[i] * d[i]; if (e < best) { best = e; at = s; } } return d.slice(at, at + Math.max(w, 4096)); }
  function captureNoise() { const r = range(); if (!r || r.whole) { toast(t('Selecione um trecho que tenha só o ruído de fundo.')); return; } const sr = r.tr.buf.sampleRate; P.noise = DSP.noiseProfile(r.tr.buf.getChannelData(0).slice(Math.floor(r.a * sr), Math.floor(r.b * sr))); toast(t('Perfil de ruído capturado. Agora use «Reduzir ruído».'), 'ok'); }
  function cutCopy(cut) { const r = range(); if (!r || r.whole) { toast(t('Selecione um trecho.')); return; } const sr = r.tr.buf.sampleRate, i0 = Math.floor(r.a * sr), i1 = Math.floor(r.b * sr); P.clip = chans(r.tr.buf).map((d) => d.slice(i0, i1)); P.clipRate = sr; if (cut) del(); else toast(t('Copiado'), 'ok'); }
  function del() { const r = range(); if (!r || r.whole) { toast(t('Selecione um trecho.')); return; } const sr = r.tr.buf.sampleRate, i0 = Math.floor(r.a * sr), i1 = Math.floor(r.b * sr); pushUndo(); r.tr.buf = mkBuf(chans(r.tr.buf).map((d) => { const o = new Float32Array(d.length - (i1 - i0)); o.set(d.slice(0, i0)); o.set(d.slice(i1), i0); return o; }), sr); P.sel = { track: r.tr.id, a: r.tr.start + r.a, b: r.tr.start + r.a }; P.head = r.tr.start + r.a; paintAll(); }
  function paste() {
    const tr = selTrack(); if (!P.clip || !tr) { toast(t('Nada copiado.')); return; } const sr = tr.buf.sampleRate, at = Math.max(0, Math.min(tr.buf.duration, P.head - tr.start)), i = Math.floor(at * sr); pushUndo();
    const clip = P.clip.length === tr.buf.numberOfChannels ? P.clip : tr.buf.numberOfChannels === 1 ? [P.clip[0]] : P.clip.concat(P.clip).slice(0, tr.buf.numberOfChannels); const cr = P.clipRate === sr ? clip : clip.map((d) => DSP.resample(d, P.clipRate / sr));
    tr.buf = mkBuf(chans(tr.buf).map((d, c) => { const o = new Float32Array(d.length + cr[c].length); o.set(d.slice(0, i)); o.set(cr[c], i); o.set(d.slice(i), i + cr[c].length); return o; }), sr); paintAll();
  }
  function trimToSel() { const r = range(); if (!r || r.whole) { toast(t('Selecione um trecho.')); return; } const sr = r.tr.buf.sampleRate, i0 = Math.floor(r.a * sr), i1 = Math.floor(r.b * sr); pushUndo(); r.tr.buf = mkBuf(chans(r.tr.buf).map((d) => d.slice(i0, i1)), sr); r.tr.start += r.a; P.sel = { track: r.tr.id, a: 0, b: 0 }; paintAll(); }
  function splitAtHead() { const tr = selTrack(); if (!tr) return; const at = P.head - tr.start; if (at <= 0.01 || at >= tr.buf.duration - 0.01) { toast(t('Coloque o cursor no meio da faixa.')); return; } const sr = tr.buf.sampleRate, i = Math.floor(at * sr); pushUndo(); const A = chans(tr.buf).map((d) => d.slice(0, i)), B = chans(tr.buf).map((d) => d.slice(i)); tr.buf = mkBuf(A, sr); const nt = { id: nid(), name: tr.name + ' ②', buf: mkBuf(B, sr), start: tr.start + at, vol: tr.vol, pan: tr.pan, mute: false, solo: false, color: tr.color }; P.tracks.splice(P.tracks.indexOf(tr) + 1, 0, nt); paintAll(); }
  function dupTrack() { const tr = selTrack(); if (!tr) return; pushUndo(); P.tracks.splice(P.tracks.indexOf(tr) + 1, 0, Object.assign({}, tr, { id: nid(), name: tr.name + ' 2' })); paintAll(); }
  async function delTrack() { const tr = selTrack(); if (!tr) return; if (!(await confirmDialog(t('Apagar a faixa «{n}»?', { n: tr.name })))) return; pushUndo(); P.tracks = P.tracks.filter((x) => x !== tr); P.sel = { track: '', a: 0, b: 0 }; paintAll(); }

  // ---------------------------------------------------------------- reprodução (mixagem ao vivo)
  function stopPlay() { if (V.playing) { V.playing.nodes.forEach((n) => { try { n.stop(); } catch (e) { /* ok */ } }); cancelAnimationFrame(V.playing.raf); const at = V.playing.from + (ac.currentTime - V.playing.t0); V.playing = null; if (!V.loop) P.head = Math.min(at, duration()); paintPlayBtn(); drawAll(); } }
  async function play(fromSel) {
    if (V.playing) { stopPlay(); return; } await ac.resume(); if (!P.tracks.length) return;
    const hasSolo = P.tracks.some((x) => x.solo), from = fromSel && P.sel.b > P.sel.a ? P.sel.a : P.head, to = fromSel && P.sel.b > P.sel.a ? P.sel.b : duration(), t0 = ac.currentTime + 0.05, nodes = [];
    P.tracks.forEach((tr) => {
      if (tr.mute || (hasSolo && !tr.solo)) return; const end = tr.start + tr.buf.duration; if (end <= from || tr.start >= to) return;
      const src = ac.createBufferSource(), g = ac.createGain(), pn = ac.createStereoPanner ? ac.createStereoPanner() : null; src.buffer = tr.buf; g.gain.value = tr.vol; if (pn) pn.pan.value = tr.pan; src.connect(g); (pn ? (g.connect(pn), pn) : g).connect(ac.destination);
      const off = Math.max(0, from - tr.start), when = t0 + Math.max(0, tr.start - from); src.start(when, off, Math.min(tr.buf.duration - off, to - Math.max(from, tr.start))); nodes.push(src);
    });
    const info = { nodes, t0, from, to, raf: 0 }; V.playing = info; paintPlayBtn();
    const tick = () => { if (!V.playing) return; const pos = from + Math.max(0, ac.currentTime - t0); P.head = pos; drawAll(); if (pos >= to + 0.05) { if (V.loop) { stopPlay(); play(fromSel); return; } P.head = fromSel ? P.sel.a : 0; stopPlay(); return; } info.raf = requestAnimationFrame(tick); }; info.raf = requestAnimationFrame(tick);
  }
  async function mixdown(onlyTrack) {
    const sr = rate(), dur = onlyTrack ? onlyTrack.start + onlyTrack.buf.duration : duration(), oc = new OfflineAudioContext(2, Math.ceil(dur * sr) + 1, sr), hasSolo = P.tracks.some((x) => x.solo);
    (onlyTrack ? [onlyTrack] : P.tracks).forEach((tr) => { if (!onlyTrack && (tr.mute || (hasSolo && !tr.solo))) return; const s = oc.createBufferSource(), g = oc.createGain(), pn = oc.createStereoPanner(); s.buffer = tr.buf; g.gain.value = onlyTrack ? 1 : tr.vol; pn.pan.value = onlyTrack ? 0 : tr.pan; s.connect(g); g.connect(pn); pn.connect(oc.destination); s.start(onlyTrack ? 0 : tr.start); });
    const out = await oc.startRendering(); let peak = Math.max(DSP.peak(out.getChannelData(0)), DSP.peak(out.getChannelData(1))); const k = peak > 1 ? 0.98 / peak : 1; const chs = [out.getChannelData(0), out.getChannelData(1)].map((d) => (k < 1 ? d.map((v) => v * k) : d));
    return DSP.encodeWav(onlyTrack ? [chs[0]] : chs, sr);
  }

  // ---------------------------------------------------------------- gravação
  async function toggleRecord() {
    if (V.rec) { V.rec.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } }), mr = new MediaRecorder(stream), chunks = []; V.rec = mr; paintRec();
      mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      mr.onstop = async () => { stream.getTracks().forEach((x) => x.stop()); V.rec = null; paintRec(); try { addTrack(await decode(await new Blob(chunks).arrayBuffer()), t('Gravação')); toast(t('Gravação adicionada'), 'ok'); } catch (e) { toast(t('A gravação não pôde ser lida: {e}', { e: e.message }), 'err'); } };
      mr.start(); toast(t('Gravando… clique de novo para parar.'));
    } catch (e) { V.rec = null; paintRec(); toast(t('Não consegui usar o microfone: {e}', { e: e.message }), 'err'); }
  }
  const recBtn = h('button', { class: 'btn sm', id: 'ge-srec', type: 'button', onclick: toggleRecord }, icon('record', 13), h('span', null, t('Gravar')));
  const paintRec = () => { recBtn.classList.toggle('danger', !!V.rec); recBtn.querySelector('span').textContent = V.rec ? t('Parar gravação') : t('Gravar'); };

  // ---------------------------------------------------------------- desenho
  const tracksEl = h('div', { class: 'ge-tracks', id: 'ge-tracks' });
  const ruler = h('canvas', { id: 'ge-ruler', title: t('Clique para mover o cursor') });
  const rulerRow = h('div', { class: 'ge-ruler' }, h('div', { class: 'sp' }), ruler);
  const peaksCache = new WeakMap();
  function peaks(buf, spp) { let m = peaksCache.get(buf); if (!m) { m = new Map(); peaksCache.set(buf, m); } const key = Math.max(1, Math.round(spp)); if (m.has(key)) return m.get(key); const d = buf.getChannelData(0), n = Math.ceil(d.length / key), mn = new Float32Array(n), mx = new Float32Array(n); for (let i = 0; i < n; i++) { let lo = 1, hi = -1; const s = i * key, e = Math.min(d.length, s + key); const step = Math.max(1, Math.floor((e - s) / 24)); for (let j = s; j < e; j += step) { const v = d[j]; if (v < lo) lo = v; if (v > hi) hi = v; } mn[i] = lo; mx[i] = hi; } const out = { mn, mx, key }; m.set(key, out); if (m.size > 6) m.delete(m.keys().next().value); return out; }
  const w2x = (sec) => (sec - V.scroll) * V.pps, x2w = (x) => x / V.pps + V.scroll;
  function drawTrack(tr, cv) {
    const w = cv.clientWidth || 600, hh = 96; if (cv.width !== w) cv.width = w; cv.height = hh; const c = cv.getContext('2d'); c.clearRect(0, 0, w, hh);
    c.fillStyle = tr.mute ? 'rgba(120,120,120,.05)' : 'rgba(255,255,255,.02)'; c.fillRect(0, 0, w, hh); c.strokeStyle = 'rgba(255,255,255,.08)'; c.beginPath(); c.moveTo(0, hh / 2); c.lineTo(w, hh / 2); c.stroke();
    const sr = tr.buf.sampleRate, spp = sr / V.pps, pk = peaks(tr.buf, spp); c.fillStyle = tr.mute ? '#666' : tr.color;
    for (let x = 0; x < w; x++) { const s = (x2w(x) - tr.start) * sr / pk.key, i = Math.floor(s); if (i < 0 || i >= pk.mn.length) continue; const y0 = hh / 2 - pk.mx[i] * (hh / 2 - 4) * tr.vol, y1 = hh / 2 - pk.mn[i] * (hh / 2 - 4) * tr.vol; c.fillRect(x, y0, 1, Math.max(1, y1 - y0)); }
    if (P.sel.track === tr.id && P.sel.b > P.sel.a) { c.fillStyle = 'rgba(124,183,255,.22)'; c.fillRect(w2x(P.sel.a), 0, w2x(P.sel.b) - w2x(P.sel.a), hh); c.strokeStyle = '#7cb7ff'; c.strokeRect(w2x(P.sel.a) + .5, .5, w2x(P.sel.b) - w2x(P.sel.a), hh - 1); }
    const hx = w2x(P.head); if (hx >= 0 && hx <= w) { c.strokeStyle = '#ffd166'; c.beginPath(); c.moveTo(hx + .5, 0); c.lineTo(hx + .5, hh); c.stroke(); }
  }
  function drawRuler() {
    const w = ruler.clientWidth || 600; if (ruler.width !== w) ruler.width = w; ruler.height = 24; const c = ruler.getContext('2d'); c.clearRect(0, 0, w, 24); c.fillStyle = '#8b8b8b'; c.font = '10px sans-serif'; c.strokeStyle = '#444';
    const step = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60].find((s) => s * V.pps >= 60) || 60; for (let s = Math.ceil(V.scroll / step) * step; w2x(s) < w; s += step) { const x = Math.round(w2x(s)) + .5; c.beginPath(); c.moveTo(x, 14); c.lineTo(x, 24); c.stroke(); c.fillText(step < 1 ? s.toFixed(2) + 's' : (s >= 60 ? Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0') : s + 's'), x + 3, 11); }
    const hx = w2x(P.head); c.fillStyle = '#ffd166'; c.beginPath(); c.moveTo(hx - 5, 0); c.lineTo(hx + 5, 0); c.lineTo(hx, 9); c.fill();
  }
  let rafD = 0; function drawAll() { if (rafD) return; rafD = requestAnimationFrame(() => { rafD = 0; drawRuler(); tracksEl.querySelectorAll('.ge-trk').forEach((row) => { const tr = trackById(row.dataset.id); if (tr) drawTrack(tr, row.querySelector('canvas')); }); paintInfo(); }); }
  function paintTracks() {
    tracksEl.replaceChildren(...P.tracks.map((tr) => {
      const cv = h('canvas'), row = h('div', { class: 'ge-trk' + (P.sel.track === tr.id ? ' on' : ''), dataset: { id: tr.id } },
        h('div', { class: 'ge-trkhead', onclick: () => { P.sel.track = tr.id; paintTracks(); drawAll(); } }, h('div', { class: 'nm', title: tr.name, ondblclick: async () => { const i = h('input', { value: tr.name }); if (await modal(t('Renomear'), i, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]) === 'ok' && i.value.trim()) { tr.name = i.value.trim(); markDirty(); paintTracks(); drawAll(); } } }, tr.name),
          h('div', { class: 'row' }, h('button', { class: 'btn sm ghost' + (tr.mute ? ' on' : ''), type: 'button', title: t('Silenciar'), onclick: (e) => { e.stopPropagation(); tr.mute = !tr.mute; paintTracks(); drawAll(); } }, 'M'), h('button', { class: 'btn sm ghost' + (tr.solo ? ' on' : ''), type: 'button', title: t('Solo'), onclick: (e) => { e.stopPropagation(); tr.solo = !tr.solo; paintTracks(); drawAll(); } }, 'S'), h('span', { class: 'small dim' }, tr.buf.duration.toFixed(2) + 's')),
          (() => { const r = h('input', { type: 'range', min: 0, max: 150, value: Math.round(tr.vol * 100), title: t('Volume') }); r.addEventListener('input', () => { tr.vol = r.value / 100; markDirty(); drawAll(); }); r.addEventListener('click', (e) => e.stopPropagation()); return r; })(),
          (() => { const r = h('input', { type: 'range', min: -100, max: 100, value: Math.round(tr.pan * 100), title: t('Balanço (esq./dir.)') }); r.addEventListener('input', () => { tr.pan = r.value / 100; markDirty(); }); r.addEventListener('click', (e) => e.stopPropagation()); return r; })()),
        h('div', { class: 'ge-trkview' }, cv));
      let selDrag = null;
      cv.addEventListener('pointerdown', (e) => { cv.setPointerCapture(e.pointerId); P.sel.track = tr.id; const x = e.offsetX, w = Math.max(0, x2w(x)); selDrag = { w0: w }; if (e.shiftKey && P.sel.b > P.sel.a) { selDrag.w0 = P.sel.a; P.sel.b = w; } else { P.sel = { track: tr.id, a: w, b: w }; P.head = w; } tracksEl.querySelectorAll('.ge-trk').forEach((r) => r.classList.toggle('on', r.dataset.id === tr.id)); drawAll(); });
      cv.addEventListener('pointermove', (e) => { if (!selDrag) return; const w = Math.max(0, x2w(e.offsetX)); P.sel.a = Math.min(selDrag.w0, w); P.sel.b = Math.max(selDrag.w0, w); P.head = P.sel.a; drawAll(); });
      cv.addEventListener('pointerup', () => { selDrag = null; if (P.sel.b - P.sel.a < 0.005) { P.sel.b = P.sel.a; } drawAll(); });
      return row;
    }));
    if (!P.tracks.length) tracksEl.replaceChildren(h('div', { class: 'empty', style: { margin: '30px auto', maxWidth: '420px' } }, h('h3', null, t('Nenhuma faixa ainda')), h('p', null, t('Gere um som com o prompt, grave com o microfone ou arraste um arquivo de áudio para cá.'))));
    drawAll();
  }
  ruler.addEventListener('pointerdown', (e) => { P.head = Math.max(0, x2w(e.offsetX)); drawAll(); });
  tracksEl.addEventListener('wheel', (e) => { e.preventDefault(); if (e.shiftKey) { V.scroll = Math.max(0, V.scroll + e.deltaY / V.pps); } else { const x = e.offsetX - 150, before = x2w(x); V.pps = Math.max(8, Math.min(4000, V.pps * (e.deltaY < 0 ? 1.2 : 1 / 1.2))); V.scroll = Math.max(0, before - x / V.pps); } drawAll(); }, { passive: false });
  tracksEl.addEventListener('dragover', (e) => e.preventDefault()); tracksEl.addEventListener('drop', async (e) => { e.preventDefault(); for (const f of [...(e.dataTransfer.files || [])]) await addFile(f); });
  const info = h('span', { class: 'small dim', id: 'ge-sinfo' }); const status = h('span', { class: 'small dim', id: 'ge-sstatus' });
  function paintInfo() { const s = P.sel; info.textContent = (s.b > s.a ? t('Seleção: {a}s → {b}s ({d}s)', { a: s.a.toFixed(2), b: s.b.toFixed(2), d: (s.b - s.a).toFixed(2) }) : t('Cursor: {a}s', { a: P.head.toFixed(2) })) + ' · ' + t('Duração: {d}s', { d: duration().toFixed(2) }); }
  const playBtn = h('button', { class: 'btn sm primary', id: 'ge-splay', type: 'button', onclick: () => play(false) }, icon('play', 13), h('span', null, t('Tocar')));
  const paintPlayBtn = () => { playBtn.replaceChildren(icon(V.playing ? 'stop' : 'play', 13), h('span', null, V.playing ? t('Parar') : t('Tocar'))); playBtn.classList.toggle('danger', !!V.playing); playBtn.classList.toggle('primary', !V.playing); };

  // ---------------------------------------------------------------- efeitos (diálogos de parâmetros)
  async function ask(title, fields, ok) { const inputs = fields.map((f) => { const i = f.type === 'select' ? h('select', null, f.options.map(([v, l]) => h('option', { value: v, selected: v === f.value }, l))) : h('input', { type: 'number', value: f.value, step: f.step || 'any', min: f.min, max: f.max }); i.id = 'ge-fx-' + f.k; return [f, i]; }); if (await modal(title, h('div', null, inputs.map(([f, i]) => propRow(f.label, i))), [{ label: t('Cancelar'), value: null }, { label: t('Aplicar'), value: 'ok', cls: 'primary' }]) !== 'ok') return; ok(Object.fromEntries(inputs.map(([f, i]) => [f.k, f.type === 'select' ? i.value : parseFloat(i.value)]))); }
  const FX = [
    ['gain', 'Ganho (dB)', () => ask(t('Ganho'), [{ k: 'db', label: 'dB', value: 6, step: 1 }], (v) => fx.gain(v.db))], ['fadein', 'Fade in', () => fx.fadeIn()], ['fadeout', 'Fade out', () => fx.fadeOut()], ['normalize', 'Normalizar', () => fx.normalize()], ['reverse', 'Inverter (reverso)', () => fx.reverse()], ['silence', 'Silenciar trecho', () => fx.silence()],
    ['speed', 'Velocidade / tom', () => ask(t('Velocidade e tom'), [{ k: 'r', label: t('Fator (1 = igual; 2 = dobro e mais agudo)'), value: 1.25, step: 0.05, min: 0.25, max: 4 }], (v) => fx.speed(v.r))], ['echo', 'Eco', () => ask(t('Eco'), [{ k: 'd', label: t('Atraso (s)'), value: 0.25, step: 0.05, min: 0.02, max: 1 }, { k: 'k', label: t('Intensidade (0–0,9)'), value: 0.5, step: 0.05, min: 0, max: 0.9 }], (v) => fx.echo(v.d, v.k))],
    ['lowpass', 'Passa-baixas', () => ask(t('Passa-baixas'), [{ k: 'f', label: 'Hz', value: 3000, min: 100, max: 18000 }], (v) => fx.lowpass(v.f))], ['highpass', 'Passa-altas', () => ask(t('Passa-altas'), [{ k: 'f', label: 'Hz', value: 120, min: 20, max: 8000 }], (v) => fx.highpass(v.f))],
    ['gate', 'Silenciar ruído (gate)', () => ask(t('Silenciar ruído de fundo'), [{ k: 'db', label: t('Limite (dB; o que estiver abaixo some)'), value: -45, min: -80, max: -10 }], (v) => fx.gate(v.db))],
    ['noise', 'Capturar perfil de ruído', captureNoise], ['denoise', 'Reduzir ruído', () => ask(t('Reduzir ruído de fundo'), [{ k: 's', label: t('Força (0,5 suave · 2 forte)'), value: 1.3, step: 0.1, min: 0.3, max: 3 }], (v) => fx.denoise(v.s))],
  ];

  // ---------------------------------------------------------------- salvar / aplicar ao jogo
  async function saveProject(quiet) {
    if (!P.tracks.length) return;
    try {
      for (const tr of P.tracks) await E.api.upload(`sound/${P.name}/${tr.id}.wav`, await mixdown(Object.assign({}, tr, { start: 0 })), 'editor');
      await E.api.write(`sound/${P.name}.sound.json`, JSON.stringify({ schema: 'asta.ge.sound.v1', name: P.name, tracks: P.tracks.map((x) => ({ id: x.id, name: x.name, start: x.start, vol: x.vol, pan: x.pan, mute: x.mute, solo: x.solo, color: x.color })) }), 'editor');
      P.dirty = false; status.textContent = t('salvo'); if (!quiet) toast(t('Projeto de áudio salvo'), 'ok'); loadLib();
    } catch (e) { toast(e.message, 'err'); }
  }
  async function openProject(name) {
    try {
      const doc = JSON.parse((await E.api.read(`sound/${name}.sound.json`, 'editor')).content); P.name = doc.name; P.tracks = []; undo = []; redo = [];
      for (const tr of doc.tracks) { const buf = await decode(await (await fetch(E.api.raw(`sound/${doc.name}/${tr.id}.wav`, 'editor'))).arrayBuffer()); P.tracks.push(Object.assign({}, tr, { buf })); }
      P.sel = { track: '', a: 0, b: 0 }; P.head = 0; P.dirty = false; paintAll(); toast(t('Aberto: {n}', { n: name }));
    } catch (e) { toast(e.message, 'err'); }
  }
  async function applyToGame() {
    if (!P.tracks.length) return; const nm = h('input', { value: P.name, id: 'ge-sname' }), use = h('select', { id: 'ge-suse' }, EVENTS.map(([v, l]) => h('option', { value: v }, t(l))));
    if (await modal(t('Aplicar ao jogo'), h('div', null, propRow(t('Nome do arquivo'), nm), propRow(t('Usar como'), use), h('p', { class: 'muted small' }, t('Mistura todas as faixas (menos as silenciadas) e grava em assets/sound/ como WAV.'))), [{ label: t('Cancelar'), value: null }, { label: t('Gravar'), value: 'ok', cls: 'primary' }]) !== 'ok') return;
    const name = nm.value.trim().replace(/[^\w-]+/g, '-').toLowerCase() || 'som';
    try {
      await E.api.upload(`assets/sound/${name}.wav`, await mixdown(null), 'game'); await saveProject(true);
      if (use.value) { const st = (E.proj.settings || {}).audio || {}; const next = use.value === 'music' ? Object.assign({}, st, { music: name }) : Object.assign({}, st, { events: Object.assign({}, st.events || {}, { [use.value]: name }) }); E.proj = await E.api.put('', { settings: { audio: next } }); }
      toast(t('Som «{n}» aplicado ao jogo', { n: name }), 'ok'); loadLib();
    } catch (e) { toast(e.message, 'err'); }
  }

  // ---------------------------------------------------------------- biblioteca + conexões opcionais (Studio, Canvas)
  const libEl = h('div', { class: 'ge-sfxlist', id: 'ge-slib' });
  async function loadLib() {
    const [ed, gm] = await Promise.all([E.api.tree('editor'), E.api.tree('game')]);
    const docs = flatFiles(ed.children).filter((f) => f.path.startsWith('sound/') && f.path.endsWith('.sound.json')).map((f) => f.path.replace(/^sound\//, '').replace(/\.sound\.json$/, ''));
    const snds = flatFiles(gm.children).filter((f) => f.path.startsWith('assets/sound/') && /\.(wav|mp3|ogg|m4a|flac)$/i.test(f.path));
    const sel = new Set();
    const row = (f) => { const au = new Audio(E.api.raw(f.path, 'game')); const cb = h('input', { type: 'checkbox', title: t('Selecionar para enviar') }); cb.addEventListener('change', () => (cb.checked ? sel.add(f.path) : sel.delete(f.path)));
      return h('div', { class: 'ge-sfx', dataset: { snd: stem(f.path) } }, cb, h('span', { class: 'nm', title: f.path }, stem(f.path)), ibtn(t('Ouvir'), 'play', () => { au.currentTime = 0; au.play().catch(() => {}); }), ibtn(t('Abrir no editor'), 'edit', async () => { try { addTrack(await decode(await (await fetch(E.api.raw(f.path, 'game'))).arrayBuffer()), stem(f.path)); } catch (e) { toast(e.message, 'err'); } }),
        ibtn(t('Apagar'), 'trash', async () => { if (await confirmDialog(t('Apagar «{n}» do jogo?', { n: f.path }))) { await E.api.remove(f.path); loadLib(); } })); };
    const link = h('div', { class: 'ge-linkbox', id: 'ge-slinks' }, h('b', null, t('Conexões opcionais')), h('div', { class: 'ge-iact', style: { marginTop: '6px' } },
      btn(t('Enviar ao Studio'), 'film', async () => { if (!sel.size) { toast(t('Marque os sons que quer enviar.')); return; } try { const r = await E.api.post('/studio-link', { paths: [...sel] }); toast(t('{n} som(ns) enviados ao Studio', { n: r.added }), 'ok'); } catch (e) { toast(e.message, 'err'); } }, '', { id: 'ge-to-studio' }),
      btn(t('Enviar ao Canvas'), 'canvas', async () => { if (!sel.size) { toast(t('Marque os sons que quer enviar.')); return; } try { const r = await E.api.post('/canvas-link', { paths: [...sel] }); toast(t('{n} arquivo(s) enviados ao Canvas', { n: r.added }), 'ok'); } catch (e) { toast(e.message, 'err'); } }, '', { id: 'ge-to-canvas' })));
    libEl.replaceChildren(h('div', { class: 'small dim' }, t('Projetos de áudio')), ...(docs.length ? docs.map((d) => h('div', { class: 'ge-sfx', dataset: { doc: d } }, icon('layers', 14), h('span', { class: 'nm' }, d), btn(t('Abrir'), 'edit', () => openProject(d)))) : [h('div', { class: 'muted small' }, '—')]),
      h('div', { class: 'small dim', style: { marginTop: '8px' } }, t('Sons do jogo')), ...(snds.length ? snds.map(row) : [h('div', { class: 'muted small' }, t('Nenhum som ainda.'))]), link);
  }

  // ---------------------------------------------------------------- IA
  const gen = { kind: '', duration: '', text: '' };
  const kindSel = h('select', { class: 'team-sel', id: 'ge-skind', title: t('Tipo de som'), 'aria-label': t('Tipo de som') }, [['', t('Auto')], ['sfx', t('Efeito')], ['music', t('Música')], ['voice', t('Voz')]].map(([v, l]) => h('option', { value: v }, l))); kindSel.addEventListener('change', () => { gen.kind = kindSel.value; });
  const durIn = h('input', { type: 'number', class: 'team-sel', id: 'ge-sdur', min: 0.2, max: 60, step: 0.5, placeholder: 's', title: t('Duração (s)'), style: { width: '64px' } }); durIn.addEventListener('input', () => { gen.duration = durIn.value; });
  const pp = promptPanel(E, {
    tab: 'sound', endpoint: 'sound', title: t('Prompt de som'), placeholder: t('Descreva o som: “moeda 8-bit”, “música calma de floresta”, “voz de um velho mago dizendo olá”…'),
    intro: t('Gere efeitos, músicas e vozes. Sem modelo de áudio, o ASTA sintetiza efeitos e trilhas de verdade. Depois edite: cortar, fades, remover ruído de fundo, gravar sua própria voz.'),
    hints: [t('efeito de moeda'), t('música épica de batalha'), t('voz de narrador: Bem-vindo, herói'), t('som de porta pesada')], tools: [h('span', { class: 'tool' }, kindSel), h('span', { class: 'tool' }, durIn)],
    body: () => ({ kind: gen.kind, duration: gen.duration ? parseFloat(gen.duration) : undefined }),
    onResult: async (res) => { const s = res.sound; if (!s) return; try { const buf = await decode(await b64ToBlob(s.data, s.mime).arrayBuffer()); addTrack(buf, s.name); toast(s.source === 'ai' ? t('Som gerado') : t('Som sintetizado pelo ASTA (sem modelo de áudio)'), 'ok'); } catch (e) { toast(t('Não consegui abrir o áudio gerado: {e}', { e: e.message }), 'err'); } },
  });

  // ---------------------------------------------------------------- montagem
  const fileIn = h('input', { type: 'file', accept: 'audio/*,.wav,.mp3,.ogg,.m4a,.flac,.webm', multiple: true, class: 'hidden' }); fileIn.addEventListener('change', async () => { for (const f of [...fileIn.files]) await addFile(f); fileIn.value = ''; });
  const loopBtn = ibtn(t('Repetir'), 'loop', () => { V.loop = !V.loop; loopBtn.classList.toggle('on', V.loop); }, '', { id: 'ge-sloop' });
  const transport = h('div', { class: 'ge-stool' }, playBtn, btn(t('Tocar seleção'), 'play', () => play(true), '', { id: 'ge-splaysel' }), loopBtn, recBtn, h('span', { class: 'sep' }), btn(t('Importar'), 'upload', () => fileIn.click(), '', { id: 'ge-simport' }), btn(t('Salvar'), 'check', () => saveProject(), '', { id: 'ge-ssave' }), btn(t('Aplicar ao jogo'), 'rocket', applyToGame, 'primary', { id: 'ge-sapply' }), fileIn, h('span', { class: 'grow' }), status);
  const editBar = h('div', { class: 'ge-stool' }, ibtn(t('Desfazer'), 'undo', doUndo, '', { id: 'ge-sundo' }), ibtn(t('Refazer'), 'skipback', doRedo, '', { style: { transform: 'scaleX(-1)' } }), h('span', { class: 'sep' }), btn(t('Cortar'), 'scissors', () => cutCopy(true), '', { id: 'ge-scut' }), btn(t('Copiar'), 'copy', () => cutCopy(false)), btn(t('Colar'), 'file', paste), btn(t('Excluir'), 'trash', del, '', { id: 'ge-sdel' }), btn(t('Cortar ao trecho'), 'trimstart', trimToSel), btn(t('Dividir'), 'split', splitAtHead), btn(t('Duplicar faixa'), 'copy', dupTrack), btn(t('Apagar faixa'), 'trash', delTrack, 'danger'),
    h('span', { class: 'sep' }), btn(t('Selecionar tudo'), 'select', () => { const tr = selTrack(); if (tr) { P.sel = { track: tr.id, a: tr.start, b: tr.start + tr.buf.duration }; drawAll(); } }), btn('−', '', () => { V.pps = Math.max(8, V.pps / 1.5); drawAll(); }, '', { title: t('Reduzir zoom') }), btn('+', '', () => { V.pps = Math.min(4000, V.pps * 1.5); drawAll(); }, '', { title: t('Aumentar zoom') }), h('span', { class: 'grow' }), info);
  const fxEl = h('div', { class: 'ge-igrp' }, h('h4', null, t('Efeitos (no trecho selecionado ou na faixa inteira)')), h('div', { class: 'ge-fxgrid', id: 'ge-fx' }, FX.map(([id, label, fn]) => btn(t(label), '', fn, '', { dataset: { fx: id } }))));
  const noiseNote = h('p', { class: 'muted small' }, t('Para tirar o ruído de fundo: selecione um trecho que tenha só o ruído, use «Capturar perfil de ruído» e depois «Reduzir ruído». Sem perfil, o ASTA usa o trecho mais silencioso da faixa.'));
  const center = h('section', { class: 'ge-center' }, transport, editBar, rulerRow, tracksEl);
  const right = h('aside', { class: 'ge-right' }, h('div', { class: 'ge-ph' }, h('b', null, t('Efeitos e biblioteca'))), h('div', { class: 'ge-insp' }, fxEl, noiseNote, libEl));
  body.replaceChildren(h('div', { class: 'ge-grid ge-sound' }, h('div', { class: 'ge-left' }, pp.el), center, right));
  const paintAll = () => { paintTracks(); drawAll(); };
  const ro = new ResizeObserver(() => drawAll()); ro.observe(tracksEl); E.onCleanup(() => { ro.disconnect(); if (P.dirty && P.tracks.length) saveProject(true); });
  const keys = (e) => { if (!document.body.contains(tracksEl) || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || '')) return; if (e.code === 'Space') { e.preventDefault(); play(false); } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? doRedo() : doUndo(); } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'x') { e.preventDefault(); cutCopy(true); } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') { e.preventDefault(); cutCopy(false); } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') { e.preventDefault(); paste(); } else if (e.key === 'Delete') { e.preventDefault(); del(); } };
  window.addEventListener('keydown', keys); E.onCleanup(() => window.removeEventListener('keydown', keys));
  E.sound = { P, addTrack, fx, range, mixdown, mkBuf, play, DSP };   // usado pelos testes
  window.ASTA_SOUND = E.sound;
  paintAll(); loadLib();
}
