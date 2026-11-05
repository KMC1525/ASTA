// Voz na WebUI: síntese (TTS) e reconhecimento (STT) — navegador (grátis, vários idiomas) ou
// servidor compatível com OpenAI (nuvem ou local), conforme Configuração → Voz.
import { api } from './api.js';
import { state } from './main.js';

export function detectLang(text, fallback) {
  const t = ' ' + String(text || '').toLowerCase() + ' ';
  if (/[぀-ヿ]/.test(t)) return 'ja-JP';
  if (/[가-힯]/.test(t)) return 'ko-KR';
  if (/[一-鿿]/.test(t)) return 'zh-CN';
  if (/[Ѐ-ӿ]/.test(t)) return 'ru-RU';
  const score = (words) => words.reduce((n, w) => n + (t.indexOf(' ' + w + ' ') >= 0 ? 1 : 0), 0);
  const langs = {
    'pt-BR': score(['de', 'que', 'não', 'um', 'uma', 'com', 'para', 'você', 'está', 'eu', 'muito', 'olá', 'obrigado', 'sim', 'por']) + (/[ãõç]/.test(t) ? 2 : 0),
    'es-ES': score(['el', 'los', 'las', 'una', 'con', 'para', 'qué', 'usted', 'hola', 'gracias', 'pero', 'muy', 'sí']) + (/[ñ¿¡]/.test(t) ? 2 : 0),
    'fr-FR': score(['le', 'les', 'une', 'avec', 'pour', 'vous', 'bonjour', 'merci', 'est', 'je', 'pas', 'très']) + (/[éèêàçù]/.test(t) ? 1 : 0),
    'de-DE': score(['der', 'die', 'das', 'und', 'ich', 'nicht', 'ein', 'eine', 'mit', 'hallo', 'danke', 'ist']) + (/[äöüß]/.test(t) ? 2 : 0),
    'it-IT': score(['il', 'la', 'che', 'non', 'per', 'con', 'ciao', 'grazie', 'sono', 'una', 'molto']),
    'en-US': score(['the', 'and', 'you', 'is', 'are', 'with', 'hello', 'hi', 'what', 'i', 'to', 'of', 'in', 'a']),
  };
  let best = fallback || navigator.language || 'en-US', top = 0;
  Object.keys(langs).forEach((k) => { if (langs[k] > top) { top = langs[k]; best = k; } });
  return best;
}

const cfg = (k) => ((state.settings && state.settings.voice) || {})[k] || {};
export const serverTts = () => cfg('tts').engine === 'server' && !!cfg('tts').base_url;
export const serverStt = () => cfg('stt').engine === 'server' && !!cfg('stt').base_url;
export const speechSupported = () => !!window.speechSynthesis || serverTts();
export const listenSupported = () => !!(window.SpeechRecognition || window.webkitSpeechRecognition) || (serverStt() && !!window.MediaRecorder && !!navigator.mediaDevices);

// Remove *ações* e marcadores antes de falar em voz alta.
export const speakable = (s) => String(s || '').replace(/\*[^*]*\*/g, ' ').replace(/\[\[[^\]]*\]\]/g, ' ').replace(/\s+/g, ' ').trim();

// ------------------------------------------------------------------ síntese
export class Speaker {
  constructor(opts) {
    this.opts = opts || {};
    this.queue = []; this.busy = false; this.idleCbs = []; this.enabled = true;
    this.voices = []; this.assigned = {}; this.counter = {};
    if (window.speechSynthesis) {
      const load = () => { this.voices = speechSynthesis.getVoices() || []; };
      load();
      if (speechSynthesis.addEventListener) speechSynthesis.addEventListener('voiceschanged', load);
    }
  }
  get speaking() { return this.busy || this.queue.length > 0; }
  say(text, avatar) {
    const clean = speakable(text);
    if (!this.enabled || !clean || !speechSupported()) return;
    this.queue.push({ text: clean, avatar });
    this._next();
  }
  stop() {
    this.queue = []; this.busy = false;
    if (window.speechSynthesis) speechSynthesis.cancel();
    if (this.audio) { try { this.audio.pause(); } catch (e) { /* ok */ } this.audio = null; }
    this._notify(null);
    this._flush();
  }
  whenIdle(cb) { if (!this.speaking) cb(); else this.idleCbs.push(cb); }
  _flush() { if (this.speaking) return; const cbs = this.idleCbs; this.idleCbs = []; cbs.forEach((c) => c()); }
  _notify(avatar) { if (this.opts.onSpeaking) this.opts.onSpeaking(avatar); }
  _done() { this.busy = false; if (this.queue.length) return this._next(); this._notify(null); this._flush(); }
  _pick(lang, avatar) {
    const prim = lang.toLowerCase().split('-')[0];
    const pool = this.voices.filter((v) => v.lang.toLowerCase().split('-')[0] === prim);
    if (!pool.length) return null;
    const v = avatar.voice || {};
    if (v.name) { const byName = pool.find((x) => x.name === v.name); if (byName) return byName; }
    // vozes distintas para avatares distintos (atribuição sequencial por idioma)
    const key = avatar.id + '|' + prim;
    if (!(key in this.assigned)) { this.counter[prim] = (this.counter[prim] || 0); this.assigned[key] = this.counter[prim]++; }
    return pool[this.assigned[key] % pool.length];
  }
  async _next() {
    if (this.busy || !this.queue.length) return;
    this.busy = true;
    const item = this.queue.shift(), v = item.avatar.voice || {};
    this._notify(item.avatar);
    const useServer = serverTts() && (v.engine === 'server' || v.engine === 'auto' || !v.engine || !window.speechSynthesis) && v.engine !== 'browser';
    if (useServer) {
      try {
        const r = await fetch('/api/voice/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: item.text, voice: v.server_voice || '' }) });
        if (!r.ok) throw new Error('tts');
        const url = URL.createObjectURL(await r.blob());
        const au = (this.audio = new Audio(url));
        au.playbackRate = Math.min(1.5, Math.max(0.7, v.rate || 1));
        au.onended = au.onerror = () => { URL.revokeObjectURL(url); this._done(); };
        await au.play();
        return;
      } catch (e) { /* cai no navegador */ }
    }
    if (!window.speechSynthesis) return this._done();
    const u = new SpeechSynthesisUtterance(item.text);
    const lang = v.lang && v.lang !== 'auto' ? v.lang : detectLang(item.text, item.avatar.language && item.avatar.language !== 'auto' ? item.avatar.language : (state.settings.language === 'en' ? 'en-US' : navigator.language));
    u.lang = lang;
    const voice = this._pick(lang, item.avatar);
    if (voice) u.voice = voice;
    u.pitch = v.pitch || 1; u.rate = v.rate || 1;
    u.onend = u.onerror = () => this._done();
    speechSynthesis.speak(u);
  }
}

// ------------------------------------------------------------------ reconhecimento
export class Listener {
  constructor(opts) { this.opts = opts; this.listening = false; this.rec = null; }
  _state(on) { this.listening = on; if (this.opts.onState) this.opts.onState(on); }
  async start() {
    if (this.listening) return;
    const lang = (this.opts.getLang && this.opts.getLang()) || navigator.language || 'en-US';
    if (serverStt() && window.MediaRecorder && navigator.mediaDevices) return this._startServer(lang);
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    const rec = (this.rec = new SR());
    rec.lang = lang; rec.interimResults = true; rec.continuous = false;
    let final = '', last = '';
    rec.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) { const t = e.results[i][0].transcript; if (e.results[i].isFinal) final += t; else interim += t; }
      last = (final + interim).trim();
      if (this.opts.onInterim) this.opts.onInterim(last);
    };
    rec.onerror = () => this._state(false);
    rec.onend = () => { this._state(false); if (last && this.opts.onFinal) this.opts.onFinal(last); };
    try { rec.start(); this._state(true); } catch (e) { this._state(false); }
  }
  async _startServer(lang) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = (this.rec = new MediaRecorder(stream)), chunks = [];
      this._state(true);
      rec.ondataavailable = (e) => chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        this._state(false);
        const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
        if (blob.size < 1200) return;
        try {
          const r = await fetch('/api/voice/stt', { method: 'POST', headers: { 'Content-Type': blob.type, 'X-Lang': cfg('stt').lang && cfg('stt').lang !== 'auto' ? cfg('stt').lang : lang.split('-')[0] }, body: blob });
          const j = await r.json();
          if (j.text && this.opts.onFinal) this.opts.onFinal(j.text);
        } catch (e) { if (this.opts.onError) this.opts.onError(e); }
      };
      rec.start();
      // para sozinho após um silêncio (detector simples por volume)
      const ac = new (window.AudioContext || window.webkitAudioContext)(), src = ac.createMediaStreamSource(stream), an = ac.createAnalyser();
      an.fftSize = 512; src.connect(an);
      const buf = new Uint8Array(an.frequencyBinCount); let quiet = 0, talked = false; const t0 = performance.now();
      const poll = () => {
        if (!this.listening || rec.state === 'inactive') { ac.close(); return; }
        an.getByteTimeDomainData(buf);
        let max = 0; for (let i = 0; i < buf.length; i++) max = Math.max(max, Math.abs(buf[i] - 128));
        if (max > 14) { talked = true; quiet = 0; } else quiet++;
        if ((talked && quiet > 28) || performance.now() - t0 > 20000) { rec.stop(); ac.close(); return; }
        setTimeout(poll, 50);
      };
      poll();
    } catch (e) { this._state(false); if (this.opts.onError) this.opts.onError(e); }
  }
  stop() {
    if (this.rec) { try { this.rec.stop(); } catch (e) { /* ok */ } }
    this._state(false);
  }
  toggle() { return this.listening ? this.stop() : this.start(); }
}

export { api };
