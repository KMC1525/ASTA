/* ASTA runtime — core: RNG, ruído, utilidades, hardware e qualidade adaptativa. */
(function () {
  'use strict';
  const RT = (window.RT = window.RT || {});

  // ---------------------------------------------------------------- matemática
  RT.clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  RT.lerp = (a, b, t) => a + (b - a) * t;
  RT.smoothstep = (a, b, x) => {
    const t = RT.clamp((x - a) / (b - a || 1e-6), 0, 1);
    return t * t * (3 - 2 * t);
  };
  RT.angleDiff = (a, b) => {
    let d = (b - a) % (Math.PI * 2);
    if (d > Math.PI) d -= Math.PI * 2;
    if (d < -Math.PI) d += Math.PI * 2;
    return d;
  };

  // PRNG determinístico (mulberry32)
  RT.rng = function (seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };

  function hash2(x, y, seed) {
    let h = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(seed | 0, 1274126177);
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }
  RT.hash2 = hash2;

  // ruído de valor 2D suave
  RT.noise2 = function (x, y, seed) {
    const xi = Math.floor(x), yi = Math.floor(y);
    const fx = x - xi, fy = y - yi;
    const u = fx * fx * fx * (fx * (fx * 6 - 15) + 10);
    const v = fy * fy * fy * (fy * (fy * 6 - 15) + 10);
    const a = hash2(xi, yi, seed), b = hash2(xi + 1, yi, seed);
    const c = hash2(xi, yi + 1, seed), d = hash2(xi + 1, yi + 1, seed);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  };
  RT.fbm = function (x, y, seed, oct, lac, gain) {
    oct = oct || 5; lac = lac || 2; gain = gain || 0.5;
    let amp = 0.5, f = 1, sum = 0, norm = 0;
    for (let i = 0; i < oct; i++) {
      sum += amp * RT.noise2(x * f, y * f, seed + i * 101);
      norm += amp; amp *= gain; f *= lac;
    }
    return sum / norm;
  };

  // ---------------------------------------------------------------- idioma
  RT.detectLang = function (text, fallback) {
    const t = ' ' + String(text || '').toLowerCase() + ' ';
    if (/[぀-ヿ]/.test(t)) return 'ja-JP';
    if (/[가-힯]/.test(t)) return 'ko-KR';
    if (/[一-鿿]/.test(t)) return 'zh-CN';
    if (/[Ѐ-ӿ]/.test(t)) return 'ru-RU';
    if (/[؀-ۿ]/.test(t)) return 'ar-SA';
    if (/[֐-׿]/.test(t)) return 'he-IL';
    if (/[ऀ-ॿ]/.test(t)) return 'hi-IN';
    if (/[฀-๿]/.test(t)) return 'th-TH';
    if (/[Ͱ-Ͽ]/.test(t)) return 'el-GR';
    const score = (words) => words.reduce((n, w) => n + (t.indexOf(' ' + w + ' ') >= 0 ? 1 : 0), 0);
    const langs = {
      'pt-BR': score(['de', 'que', 'não', 'um', 'uma', 'com', 'para', 'você', 'está', 'eu', 'muito', 'olá', 'obrigado', 'sim', 'por']) + (/[ãõç]/.test(t) ? 2 : 0),
      'es-ES': score(['el', 'los', 'las', 'una', 'con', 'para', 'qué', 'usted', 'hola', 'gracias', 'pero', 'muy', 'sí']) + (/[ñ¿¡]/.test(t) ? 2 : 0),
      'fr-FR': score(['le', 'les', 'une', 'avec', 'pour', 'vous', 'bonjour', 'merci', 'est', 'je', 'pas', 'très']) + (/[éèêàçù]/.test(t) ? 1 : 0),
      'de-DE': score(['der', 'die', 'das', 'und', 'ich', 'nicht', 'ein', 'eine', 'mit', 'hallo', 'danke', 'ist']) + (/[äöüß]/.test(t) ? 2 : 0),
      'it-IT': score(['il', 'la', 'che', 'non', 'per', 'con', 'ciao', 'grazie', 'sono', 'una', 'molto']),
      'en-US': score(['the', 'and', 'you', 'is', 'are', 'with', 'hello', 'hi', 'what', 'i', 'to', 'of', 'in', 'a']),
    };
    let best = fallback || (navigator.language || 'en-US'), top = 0;
    Object.keys(langs).forEach((k) => { if (langs[k] > top) { top = langs[k]; best = k; } });
    return best;
  };

  // ---------------------------------------------------------------- cor
  RT.hex = (h) => parseInt(String(h).replace('#', ''), 16);

  // ---------------------------------------------------------------- hardware / qualidade
  RT.detectTier = function () {
    const q = new URLSearchParams(location.search).get('q');
    if (q === 'low' || q === 'medium' || q === 'high') return { tier: q, gpu: 'override', forced: true };
    const cores = navigator.hardwareConcurrency || 4;
    const mem = navigator.deviceMemory || 4;
    const mobile = /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent) || (navigator.maxTouchPoints > 1 && /Mac/.test(navigator.platform));
    let gpu = '';
    try {
      const c = document.createElement('canvas');
      const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
      const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
      gpu = ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : '';
      const lose = gl && gl.getExtension('WEBGL_lose_context');
      if (lose) lose.loseContext();
    } catch (e) { /* sem WebGL */ }
    let score = (cores >= 8 ? 2 : cores >= 4 ? 1 : 0) + (mem >= 8 ? 2 : mem >= 4 ? 1 : 0) - (mobile ? 1 : 0);
    if (/SwiftShader|llvmpipe|softpipe|Software|Basic Render/i.test(gpu)) score = -5;
    else if (/RTX|GTX 1[0-9]|GTX 9|RX [5-9]\d\d|Radeon Pro|Apple M|Apple GPU|Iris Xe|Arc /i.test(gpu)) score += 2;
    else if (/Intel.*(HD|UHD)|Mali|Adreno|PowerVR|Vega 3|Vega 8/i.test(gpu)) score -= 1;
    return { tier: score >= 4 ? 'high' : score >= 2 ? 'medium' : 'low', gpu: gpu, forced: false };
  };

  // Ajusta a qualidade em tempo real para manter ~30-60 FPS em qualquer máquina.
  RT.Quality = function (renderer, budget, scene, hooks) {
    this.renderer = renderer;
    this.budget = budget;
    this.maxPR = Math.min(window.devicePixelRatio || 1, budget.pixel_ratio);
    this.pr = this.maxPR;
    this.shadows = budget.shadow > 0;
    this.level = 0; // 0 = máx.; cada nível reduz custo
    this.acc = 0; this.frames = 0; this.low = 0; this.high = 0;
    this.hooks = hooks || {};
    this.fps = 60;
    this.apply();
  };
  RT.Quality.prototype.apply = function () {
    const lvl = this.level;
    this.pr = Math.max(0.5, this.maxPR * (lvl >= 1 ? Math.pow(0.85, Math.min(lvl, 4)) : 1));
    this.renderer.setPixelRatio(this.pr);
    const shadowsOn = this.budget.shadow > 0 && lvl < 3;
    if (shadowsOn !== this.shadows) {
      this.shadows = shadowsOn;
      if (this.hooks.shadows) this.hooks.shadows(shadowsOn);
    }
    this.distScale = lvl >= 5 ? 0.7 : lvl >= 4 ? 0.85 : 1;
    if (this.hooks.distance) this.hooks.distance(this.distScale);
    if (this.hooks.resize) this.hooks.resize();
  };
  RT.Quality.prototype.tick = function (dt) {
    this.acc += dt; this.frames++;
    if (this.acc < 2) return;
    this.fps = this.frames / this.acc;
    this.acc = 0; this.frames = 0;
    if (this.fps < 28) { this.low++; this.high = 0; } else if (this.fps > 56) { this.high++; this.low = 0; } else { this.low = 0; this.high = 0; }
    if (this.low >= 2 && this.level < 5) { this.level++; this.low = 0; this.apply(); }
    else if (this.high >= 6 && this.level > 0) { this.level--; this.high = 0; this.apply(); }
  };
})();
