/* ASTA runtime — cena: terreno, céu, clima, vegetação, estruturas e colisão (three.js). */
(function () {
  'use strict';
  const RT = window.RT;
  const T = window.THREE;
  const { clamp, lerp, smoothstep } = RT;

  // ------------------------------------------------------------------ biomas
  const BIOME = {
    temperate: { grass: [0x4f7f35, 0x6f9a45], dirt: 0x7b6244, rock: 0x77756e, sand: 0xcdbf8c, sandAmt: 1, snow: null, water: 0x2f6f8f, trees: [['oak', 0.7], ['pine', 0.3]], leaf: [0x3f7a2e, 0x5a9a38, 0x6aa842], grassBlades: true },
    forest: { grass: [0x3d6b2b, 0x557f35], dirt: 0x5e4a33, rock: 0x6e6d66, sand: 0xb9ad80, sandAmt: 0.6, snow: null, water: 0x2b5f6f, trees: [['oak', 0.45], ['pine', 0.55]], leaf: [0x2f6a2a, 0x3f7f33, 0x56913a], grassBlades: true },
    desert: { grass: [0xd6b97b, 0xc9a463], dirt: 0xa9824f, rock: 0x9b7a55, sand: 0xe0c58a, sandAmt: 0.3, snow: null, water: 0x3f8f9f, trees: [['cactus', 0.8], ['dead', 0.2]], leaf: [0x4f7d3a, 0x5d8c44, 0x6b9a4b], grassBlades: false },
    snow: { grass: [0xeaf0f6, 0xdbe4ee], dirt: 0x8d8f96, rock: 0x6f737b, sand: 0xcfd8e0, sandAmt: 0.5, snow: -1e9, water: 0x486f8f, trees: [['pine', 1]], leaf: [0x2c5a3a, 0x356a44, 0x417a50], grassBlades: false },
    tropical: { grass: [0x4c9a3b, 0x63b04a], dirt: 0x8a6b45, rock: 0x7a7a72, sand: 0xe6d6a4, sandAmt: 1, snow: null, water: 0x1f9bb0, trees: [['palm', 0.65], ['oak', 0.35]], leaf: [0x2f9a3a, 0x45b04a, 0x62c04f], grassBlades: true },
    island: { grass: [0x5f9a45, 0x74ad52], dirt: 0x9a8458, rock: 0x7c7b74, sand: 0xeadba8, sandAmt: 1.3, snow: null, water: 0x1f9bb0, trees: [['palm', 0.8], ['oak', 0.2]], leaf: [0x2f9a3a, 0x45b04a, 0x62c04f], grassBlades: true },
    urban: { grass: [0x6a6d72, 0x75787d], dirt: 0x55575b, rock: 0x8a8a8a, sand: 0x6a6d72, sandAmt: 0, snow: null, water: 0x3a5f7a, trees: [['oak', 1]], leaf: [0x3f7a2e, 0x4f8a36, 0x5a9a38], grassBlades: false },
    wasteland: { grass: [0x7a6a55, 0x6b5c49], dirt: 0x5b4d3c, rock: 0x5e554a, sand: 0x8a7a62, sandAmt: 0.3, snow: null, water: 0x4a5a4a, trees: [['dead', 1]], leaf: [0x5a5a40, 0x6a6a48, 0x707050], grassBlades: false },
    swamp: { grass: [0x4a5a34, 0x3f4d2c], dirt: 0x4a3f2e, rock: 0x57574d, sand: 0x5a5a3a, sandAmt: 0.8, snow: null, water: 0x3d4f35, trees: [['oak', 0.6], ['dead', 0.4]], leaf: [0x35502a, 0x3f5f30, 0x4a6a35], grassBlades: true },
    mountain: { grass: [0x66764f, 0x7a8760], dirt: 0x7a6a55, rock: 0x7b7b7b, sand: 0xb9ad80, sandAmt: 0.5, snow: 'high', water: 0x2f5f7f, trees: [['pine', 0.8], ['dead', 0.2]], leaf: [0x2c5a3a, 0x356a44, 0x417a50], grassBlades: true },
  };
  RT.BIOME = BIOME;

  // hora → (zênite, horizonte, sol, intensidades)
  const SKY = [
    { h: 0, z: 0x070b1c, hz: 0x18244a, sun: 0x9fb4e8, si: 0.7, hemi: 0.55, exp: 1.15 },
    { h: 4.8, z: 0x080c20, hz: 0x1a2650, sun: 0x9fb4e8, si: 0.7, hemi: 0.55, exp: 1.15 },
    { h: 5.9, z: 0x2d3f78, hz: 0xe8956a, sun: 0xff9a5a, si: 1.8, hemi: 0.8, exp: 1.15 },
    { h: 7.3, z: 0x3e78c8, hz: 0xf2c08e, sun: 0xffd2a0, si: 2.5, hemi: 0.8, exp: 1.05 },
    { h: 9.5, z: 0x2f78d8, hz: 0xa9d0f2, sun: 0xfff1dc, si: 3.0, hemi: 0.95, exp: 1.0 },
    { h: 15.5, z: 0x2f78d8, hz: 0xa9d0f2, sun: 0xfff1dc, si: 3.0, hemi: 0.95, exp: 1.0 },
    { h: 17.5, z: 0x3a6fc0, hz: 0xf5c58a, sun: 0xffc590, si: 2.5, hemi: 0.8, exp: 1.05 },
    { h: 18.8, z: 0x34437f, hz: 0xf07f4a, sun: 0xff7a3a, si: 1.8, hemi: 0.8, exp: 1.15 },
    { h: 20.0, z: 0x101a3c, hz: 0x2c3260, sun: 0x9fb4e8, si: 0.7, hemi: 0.55, exp: 1.12 },
    { h: 21.5, z: 0x070b1c, hz: 0x18244a, sun: 0x9fb4e8, si: 0.7, hemi: 0.55, exp: 1.15 },
    { h: 24, z: 0x070b1c, hz: 0x18244a, sun: 0x9fb4e8, si: 0.7, hemi: 0.55, exp: 1.15 },
  ];
  const OVERCAST = { clear: 0, cloudy: 0.4, fog: 0.55, rain: 0.65, snow: 0.5, storm: 0.85 };

  // ------------------------------------------------------------------ texturas procedurais
  const texCache = {};
  let maxAniso = 4;
  function canvasTex(key, size, draw, rx, ry) {
    if (texCache[key]) return texCache[key];
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const g = c.getContext('2d');
    draw(g, size);
    const t = new T.CanvasTexture(c);
    t.wrapS = t.wrapT = T.RepeatWrapping;
    t.colorSpace = T.SRGBColorSpace;
    t.anisotropy = maxAniso;
    if (rx) t.repeat.set(rx, ry || rx);
    texCache[key] = t;
    return t;
  }
  function speckle(g, s, n, alpha, light) {
    for (let i = 0; i < n; i++) {
      const v = light ? 255 : 0;
      g.fillStyle = `rgba(${v},${v},${v},${Math.random() * alpha})`;
      g.fillRect(Math.random() * s, Math.random() * s, 1 + Math.random() * 2, 1 + Math.random() * 2);
    }
  }
  const css = (hex) => '#' + hex.toString(16).padStart(6, '0');
  // fbm periódico (u,v em [0,1)) → texturas sem emendas
  function tfbm(u, v, seed) {
    let sum = 0, amp = 0.5, norm = 0, per = 4;
    for (let i = 0; i < 5; i++) {
      const x = u * per, y = v * per, xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi;
      const h = (a, b) => RT.hash2(((a % per) + per) % per, ((b % per) + per) % per, seed + i * 13);
      const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
      const n = lerp(lerp(h(xi, yi), h(xi + 1, yi), sx), lerp(h(xi, yi + 1), h(xi + 1, yi + 1), sx), sy);
      sum += n * amp; norm += amp; amp *= 0.5; per *= 2;
    }
    return sum / norm;
  }
  RT.tex = {
    noise() {
      return canvasTex('noise', 256, (g, s) => {
        g.fillStyle = '#bbb'; g.fillRect(0, 0, s, s);
        const img = g.getImageData(0, 0, s, s);
        for (let y = 0; y < s; y++) for (let x = 0; x < s; x++) {
          const v = 226 + (tfbm(x / s, y / s, 7) - 0.5) * 70 + (Math.random() - 0.5) * 22;
          const i = (y * s + x) * 4; img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255;
        }
        g.putImageData(img, 0, 0);
      });
    },
    planks(hex, rx, ry) {
      return canvasTex('planks' + hex + rx + ry, 128, (g, s) => {
        g.fillStyle = css(hex); g.fillRect(0, 0, s, s);
        for (let i = 0; i < 8; i++) {
          g.fillStyle = `rgba(0,0,0,${0.06 + Math.random() * 0.1})`; g.fillRect(0, i * 16, s, 16);
          g.fillStyle = 'rgba(0,0,0,0.5)'; g.fillRect(0, i * 16, s, 1.5);
        }
        speckle(g, s, 500, 0.12, false); speckle(g, s, 200, 0.1, true);
      }, rx, ry);
    },
    plaster(hex, rx, ry) {
      return canvasTex('plaster' + hex + rx + ry, 128, (g, s) => {
        g.fillStyle = css(hex); g.fillRect(0, 0, s, s);
        speckle(g, s, 900, 0.1, false); speckle(g, s, 600, 0.12, true);
      }, rx, ry);
    },
    bricks(hex, rx, ry) {
      return canvasTex('bricks' + hex + rx + ry, 128, (g, s) => {
        g.fillStyle = css(hex); g.fillRect(0, 0, s, s);
        for (let r = 0; r < 8; r++) for (let c = 0; c < 4; c++) {
          const off = r % 2 ? 16 : 0;
          g.fillStyle = `rgba(${Math.random() > 0.5 ? 255 : 0},${Math.random() > 0.5 ? 255 : 0},0,0.05)`;
          g.fillRect(c * 32 + off + 1, r * 16 + 1, 30, 14);
        }
        g.strokeStyle = 'rgba(0,0,0,0.45)'; g.lineWidth = 1.5;
        for (let r = 0; r <= 8; r++) { g.beginPath(); g.moveTo(0, r * 16); g.lineTo(s, r * 16); g.stroke(); }
        for (let r = 0; r < 8; r++) for (let c = 0; c <= 4; c++) { g.beginPath(); g.moveTo(c * 32 + (r % 2 ? 16 : 0), r * 16); g.lineTo(c * 32 + (r % 2 ? 16 : 0), r * 16 + 16); g.stroke(); }
        speckle(g, s, 500, 0.15, false);
      }, rx, ry);
    },
    stone(hex, rx, ry) {
      return canvasTex('stone' + hex + rx + ry, 128, (g, s) => {
        g.fillStyle = css(hex); g.fillRect(0, 0, s, s);
        for (let i = 0; i < 26; i++) {
          g.fillStyle = `rgba(${Math.random() > 0.5 ? 255 : 0},${Math.random() > 0.5 ? 255 : 0},${Math.random() > 0.5 ? 255 : 0},0.06)`;
          g.beginPath(); g.ellipse(Math.random() * s, Math.random() * s, 8 + Math.random() * 18, 6 + Math.random() * 12, Math.random() * 3, 0, 7); g.fill();
        }
        g.strokeStyle = 'rgba(0,0,0,0.25)'; g.lineWidth = 1;
        for (let i = 0; i < 12; i++) { g.beginPath(); g.moveTo(Math.random() * s, Math.random() * s); g.lineTo(Math.random() * s, Math.random() * s); g.stroke(); }
        speckle(g, s, 700, 0.15, false); speckle(g, s, 300, 0.1, true);
      }, rx, ry);
    },
    roof(hex, rx, ry) {
      return canvasTex('roof' + hex + rx + ry, 128, (g, s) => {
        g.fillStyle = css(hex); g.fillRect(0, 0, s, s);
        for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
          g.fillStyle = `rgba(0,0,0,${0.04 + Math.random() * 0.12})`; g.fillRect(c * 16 + (r % 2 ? 8 : 0), r * 16, 15, 15);
          g.fillStyle = 'rgba(0,0,0,0.35)'; g.fillRect(0, r * 16 + 14, s, 2);
        }
        speckle(g, s, 400, 0.12, false);
      }, rx, ry);
    },
    blade() {
      return canvasTex('blade', 64, (g, s) => {
        g.clearRect(0, 0, s, s);
        for (let i = 0; i < 9; i++) {
          const x = 6 + (i / 9) * (s - 12), h = s * (0.45 + Math.random() * 0.55), lean = (Math.random() - 0.5) * 16;
          const l = 205 + Math.random() * 50; g.strokeStyle = `rgb(${l * 0.9},${l},${l * 0.78})`;
          g.lineWidth = 3 + Math.random() * 2; g.lineCap = 'round';
          g.beginPath(); g.moveTo(x, s); g.quadraticCurveTo(x + lean * 0.3, s - h * 0.6, x + lean, s - h); g.stroke();
        }
      });
    },
    cloud() {
      return canvasTex('cloud', 128, (g, s) => {
        g.clearRect(0, 0, s, s);
        for (let i = 0; i < 16; i++) {
          const x = s * (0.2 + Math.random() * 0.6), y = s * (0.35 + Math.random() * 0.3), r = s * (0.12 + Math.random() * 0.16);
          const gr = g.createRadialGradient(x, y, 0, x, y, r);
          gr.addColorStop(0, 'rgba(255,255,255,0.55)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
          g.fillStyle = gr; g.fillRect(0, 0, s, s);
        }
      });
    },
    dot() {
      return canvasTex('dot', 32, (g, s) => {
        const gr = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
        gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
        g.fillStyle = gr; g.fillRect(0, 0, s, s);
      });
    },
    water() {
      return canvasTex('water', 128, (g, s) => {
        g.fillStyle = '#fff'; g.fillRect(0, 0, s, s);
        const img = g.getImageData(0, 0, s, s);
        for (let y = 0; y < s; y++) for (let x = 0; x < s; x++) {
          const a = tfbm(x / s, y / s, 5), b = tfbm((x / s) * 2 % 1, (y / s) * 2 % 1, 9);
          const v = 200 + a * 40 + b * 15; const i = (y * s + x) * 4;
          img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255;
        }
        g.putImageData(img, 0, 0);
      }, 120, 120);
    },
  };
  RT.labelSprite = function (text, opts) {
    opts = opts || {};
    const c = document.createElement('canvas'); c.width = 256; c.height = 64;
    const g = c.getContext('2d');
    g.font = '600 26px system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    const w = Math.min(244, g.measureText(text).width + 24);
    g.fillStyle = 'rgba(0,0,0,0.55)';
    g.beginPath(); g.roundRect ? g.roundRect(128 - w / 2, 12, w, 40, 14) : g.rect(128 - w / 2, 12, w, 40); g.fill();
    g.fillStyle = opts.color || '#fff'; g.fillText(text, 128, 33, 232);
    const t = new T.CanvasTexture(c); t.colorSpace = T.SRGBColorSpace;
    const s = new T.Sprite(new T.SpriteMaterial({ map: t, transparent: true, depthWrite: false, fog: false }));
    s.scale.set(2.4, 0.6, 1);
    return s;
  };

  // ------------------------------------------------------------------ geometria
  function mergeGeos(parts, withUV) {
    const pos = [], nor = [], col = [], uvs = [];
    const c = new T.Color();
    parts.forEach((p) => {
      let g = p.geo.index ? p.geo.toNonIndexed() : p.geo.clone();
      if (p.mat) g.applyMatrix4(p.mat);
      const pa = g.attributes.position.array, na = g.attributes.normal.array;
      if (withUV) { const ua = g.attributes.uv.array; for (let i = 0; i < ua.length; i++) uvs.push(ua[i]); }
      c.setHex(p.color);
      for (let i = 0; i < pa.length; i += 3) { pos.push(pa[i], pa[i + 1], pa[i + 2]); nor.push(na[i], na[i + 1], na[i + 2]); col.push(c.r, c.g, c.b); }
      g.dispose();
    });
    const out = new T.BufferGeometry();
    out.setAttribute('position', new T.Float32BufferAttribute(pos, 3));
    out.setAttribute('normal', new T.Float32BufferAttribute(nor, 3));
    out.setAttribute('color', new T.Float32BufferAttribute(col, 3));
    if (withUV) out.setAttribute('uv', new T.Float32BufferAttribute(uvs, 2));
    return out;
  }
  const M4 = (x, y, z, rx, ry, rz, sx, sy, sz) => {
    const m = new T.Matrix4();
    m.compose(new T.Vector3(x, y, z), new T.Quaternion().setFromEuler(new T.Euler(rx || 0, ry || 0, rz || 0)), new T.Vector3(sx || 1, sy || 1, sz || 1));
    return m;
  };
  function gableRoof(w, d, h, o) {
    const W = w / 2 + o, D = d / 2 + o;
    const v = [
      -W, 0, D, W, 0, D, W, h, 0, -W, 0, D, W, h, 0, -W, h, 0,
      W, 0, -D, -W, 0, -D, -W, h, 0, W, 0, -D, -W, h, 0, W, h, 0,
      -W, 0, -D, -W, 0, D, -W, h, 0, W, 0, D, W, 0, -D, W, h, 0,
    ];
    const uv = [0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 0, 0.5, 1, 0, 0, 1, 0, 0.5, 1];
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.Float32BufferAttribute(v, 3));
    g.setAttribute('uv', new T.Float32BufferAttribute(uv, 2));
    g.computeVertexNormals();
    return g;
  }

  // ------------------------------------------------------------------ mundo
  RT.World = function (spec, budget, opts) {
    opts = opts || {};
    const self = this;
    this.spec = spec;
    this.env = spec.environment;
    this.biome = BIOME[this.env.biome] || BIOME.temperate;
    this.budget = budget;
    this.scene = new T.Scene();
    this.size = this.env.size;
    this.half = this.size / 2;
    this.seed = spec.seed | 0;
    this.rand = RT.rng(this.seed);
    this.time = this.env.time_of_day;
    this.weather = this.env.weather;
    this.overcast = OVERCAST[this.weather] || 0;
    this.colliders = [];
    this.grid = new Map();
    this.emitters = [];
    this.glow = [];
    this.anims = [];
    this.zones = [];
    this.labels = [];
    this.clouds = [];
    this.gust = 0;
    maxAniso = opts.maxAniso || 4;
    this.realistic = spec.realism >= 0.5;

    this._buildHeight();
    this._buildTerrain();
    this._buildSky();
    this._buildWater();
    this._buildStructures();
    this._buildVegetation();
    this._buildWeather();
    this._buildLightPool();
    this.setTime(this.time);
  };
  const W = RT.World.prototype;

  // ----- altura do terreno
  W._buildHeight = function () {
    const env = this.env, seed = this.seed, half = this.half, biome = env.biome;
    const amp = 3 + env.relief * 34;
    this.amp = amp;
    const f0 = 1 / Math.max(90, env.size * 0.28);
    const baseFn = (x, z) => {
      const n = RT.fbm(x * f0, z * f0, seed, 5);
      let h;
      if (biome === 'desert') {
        const r = 1 - Math.abs(2 * RT.fbm(x * f0 * 1.4, z * f0 * 1.4, seed + 7, 4) - 1);
        h = (r * r - 0.35) * amp * 1.1 + (n - 0.5) * amp * 0.4;
      } else if (biome === 'mountain') {
        const r = 1 - Math.abs(2 * RT.fbm(x * f0 * 1.1, z * f0 * 1.1, seed + 9, 5) - 1);
        h = (r * r * 1.3 + n * 0.6 - 0.5) * amp;
      } else if (biome === 'urban') h = (n - 0.5) * amp * 0.25;
      else h = (n - 0.45) * amp * 1.6;
      h += (RT.noise2(x * 0.09, z * 0.09, seed + 3) - 0.5) * amp * 0.06;
      if (biome === 'island') h -= smoothstep(0.35, 0.95, Math.hypot(x, z) / half) * (amp * 2 + 8);
      return h;
    };
    // nível da água por percentil das alturas
    let waterY = -1e9;
    if (env.water) {
      const s = [];
      for (let i = 0; i < 40; i++) for (let j = 0; j < 40; j++) s.push(baseFn((i / 39 - 0.5) * half * 1.6, (j / 39 - 0.5) * half * 1.6));
      s.sort((a, b) => a - b);
      const pct = biome === 'island' ? 0.38 : biome === 'swamp' ? 0.4 : 0.2;
      waterY = s[Math.floor(pct * (s.length - 1))];
    }
    this.waterY = waterY;
    this.baseH = env.water ? waterY + (biome === 'island' ? -2.5 : 2.0) : 0;
    const baseH = this.baseH;
    this._noZone = (x, z) => {
      const e = Math.max(Math.abs(x), Math.abs(z)) / half;
      const f = smoothstep(0.8, 1.0, e);
      return baseFn(x, z) * (1 - f) + baseH * f;
    };
    // zonas planas (estruturas, spawn, NPCs)
    const addZone = (x, z, r0, r1, solid) => {
      const raw = this._noZone(x, z);
      this.zones.push({ x, z, r0, r1, h: Math.max(raw, waterY + 0.9), solid: !!solid });
    };
    const p = this.spec.player || {};
    addZone(p.x || 0, p.z || 0, 6, 18);
    (this.spec.structures || []).forEach((s) => {
      const big = { house: 5, cabin: 4, tower: 4, ruin: 6, barn: 7, tent: 3, stall: 3, well: 2.5, campfire: 3, stone_circle: 6 }[s.type] || 2;
      addZone(s.x, s.z, big * (s.scale || 1) + 1.5, big * (s.scale || 1) + 9, true);
    });
    (this.spec.npcs || []).forEach((n) => addZone(n.x, n.z, 2.5, 7));
    this.heightAt = (x, z) => {
      let h = this._noZone(x, z);
      const zs = this.zones;
      for (let i = 0; i < zs.length; i++) {
        const z0 = zs[i], dx = x - z0.x, dz = z - z0.z;
        const d2 = dx * dx + dz * dz;
        if (d2 < z0.r1 * z0.r1) {
          const d = Math.sqrt(d2);
          const t = d <= z0.r0 ? 1 : 1 - smoothstep(z0.r0, z0.r1, d);
          h += (z0.h - h) * t;
        }
      }
      return h;
    };
    this.groundAt = (x, z) => this.heightAt(x, z);
    this.slopeAt = (x, z) => {
      const e = 1.5;
      return Math.hypot(this.heightAt(x + e, z) - this.heightAt(x - e, z), this.heightAt(x, z + e) - this.heightAt(x, z - e)) / (2 * e);
    };
  };

  // ----- terreno
  W._buildTerrain = function () {
    const B = this.biome, biome = this.env.biome, self = this;
    const seg = this.budget.terrain_segments, size = this.size;
    const g = new T.PlaneGeometry(size, size, seg, seg);
    g.rotateX(-Math.PI / 2);
    const pos = g.attributes.position;
    for (let i = 0; i < pos.count; i++) pos.setY(i, this.heightAt(pos.getX(i), pos.getZ(i)));
    g.computeVertexNormals();
    const nor = g.attributes.normal;
    const col = new Float32Array(pos.count * 3);
    const c = new T.Color(), c2 = new T.Color(), tmp = new T.Color();
    const snowC = new T.Color(0xf4f8fb);
    const snowLine = B.snow === 'high' ? this.amp * 0.55 : B.snow;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i), ny = nor.getY(i);
      const t = RT.noise2(x * 0.05, z * 0.05, this.seed + 31), t2 = RT.noise2(x * 0.4, z * 0.4, this.seed + 37);
      c.setHex(B.grass[0]).lerp(c2.setHex(B.grass[1]), t).multiplyScalar(0.88 + t2 * 0.24);
      c.lerp(tmp.setHex(B.dirt), smoothstep(0.58, 0.74, RT.noise2(x * 0.03 + 50, z * 0.03, this.seed + 41)) * 0.7);
      if (this.waterY > -1e8) c.lerp(tmp.setHex(B.sand), (1 - smoothstep(this.waterY + 0.1, this.waterY + 1.8, y)) * Math.min(1, B.sandAmt));
      const rm = smoothstep(0.1, 0.28, 1 - ny);
      c.lerp(tmp.setHex(B.rock).multiplyScalar(0.85 + t2 * 0.3), rm);
      if (snowLine !== null) c.lerp(snowC, smoothstep(snowLine - 3, snowLine + 3, y + (t - 0.5) * 6) * (1 - rm * 0.5));
      col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
    }
    g.setAttribute('color', new T.BufferAttribute(col, 3));
    const detail = RT.tex.noise();
    detail.repeat.set(size / 7, size / 7);
    const mat = new T.MeshStandardMaterial({ vertexColors: true, map: detail, roughness: 0.96, metalness: 0, flatShading: !this.realistic && this.spec.realism < 0.25 });
    this.terrain = new T.Mesh(g, mat);
    this.terrain.receiveShadow = true;
    this.scene.add(this.terrain);
    // planície externa (continua a borda do terreno até o horizonte)
    const outer = new T.Mesh(new T.PlaneGeometry(size * 9, size * 9), new T.MeshLambertMaterial({ color: B.grass[0] }));
    outer.rotation.x = -Math.PI / 2;
    outer.position.y = this.baseH - 0.05;
    this.scene.add(outer);
    this.outer = outer;
  };

  // ----- céu
  W._buildSky = function () {
    const scene = this.scene;
    this.skyU = {
      zenith: { value: new T.Color() }, horizon: { value: new T.Color() },
      sunDir: { value: new T.Vector3(0, 1, 0) }, sunColor: { value: new T.Color() }, glow: { value: 1 },
    };
    const mat = new T.ShaderMaterial({
      uniforms: this.skyU, side: T.BackSide, depthWrite: false, fog: false,
      vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: `uniform vec3 zenith; uniform vec3 horizon; uniform vec3 sunDir; uniform vec3 sunColor; uniform float glow; varying vec3 vP;
        void main(){ vec3 d = normalize(vP); float h = d.y;
          vec3 col = mix(horizon, zenith, pow(clamp(h,0.0,1.0), 0.55));
          if (h < 0.0) col = mix(horizon, horizon*0.55, clamp(-h*4.0,0.0,1.0));
          float sd = max(dot(d, normalize(sunDir)), 0.0);
          col += sunColor * glow * (pow(sd, 900.0) * 3.0 + pow(sd, 14.0) * 0.28 + pow(sd, 3.0) * 0.06);
          gl_FragColor = vec4(col, 1.0);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
    });
    this.sky = new T.Mesh(new T.SphereGeometry(1000, 24, 16), mat);
    this.sky.frustumCulled = false; this.sky.renderOrder = -10;
    scene.add(this.sky);
    // estrelas
    const n = 700, sp = new Float32Array(n * 3), r = RT.rng(this.seed + 5);
    for (let i = 0; i < n; i++) {
      const u = r() * 2 - 1, a = r() * Math.PI * 2, s = Math.sqrt(1 - u * u);
      sp[i * 3] = Math.cos(a) * s * 950; sp[i * 3 + 1] = Math.abs(u) * 950; sp[i * 3 + 2] = Math.sin(a) * s * 950;
    }
    const sg = new T.BufferGeometry(); sg.setAttribute('position', new T.BufferAttribute(sp, 3));
    this.stars = new T.Points(sg, new T.PointsMaterial({ color: 0xffffff, size: 1.6, sizeAttenuation: false, transparent: true, opacity: 0, fog: false, depthWrite: false }));
    this.stars.frustumCulled = false; this.stars.renderOrder = -9;
    scene.add(this.stars);
    // nuvens
    const nc = this.budget.terrain_segments < 120 ? 5 : 10, cr = RT.rng(this.seed + 6);
    const ct = RT.tex.cloud();
    for (let i = 0; i < nc; i++) {
      const s = new T.Sprite(new T.SpriteMaterial({ map: ct, transparent: true, depthWrite: false, fog: false, opacity: 0.0 }));
      const sc = 140 + cr() * 160; s.scale.set(sc, sc * 0.5, 1);
      s.position.set((cr() - 0.5) * 900, 150 + cr() * 90, (cr() - 0.5) * 900);
      s.userData.speed = 1.5 + cr() * 2.5; s.userData.base = 0.35 + cr() * 0.4;
      scene.add(s); this.clouds.push(s);
    }
    // luzes
    this.hemi = new T.HemisphereLight(0xbfd8ff, 0x6a5a40, 0.9);
    this.sun = new T.DirectionalLight(0xffffff, 3);
    this.sun.castShadow = this.budget.shadow > 0;
    if (this.sun.castShadow) {
      const sh = this.sun.shadow, S = this.budget.terrain_segments > 180 ? 55 : 42;
      sh.mapSize.set(this.budget.shadow, this.budget.shadow);
      sh.camera.left = -S; sh.camera.right = S; sh.camera.top = S; sh.camera.bottom = -S; sh.camera.near = 1; sh.camera.far = 220;
      sh.bias = -0.0004; sh.normalBias = 0.05;
    }
    scene.add(this.hemi, this.sun, this.sun.target);
    this.fog = new T.Fog(0x9ab8cf, 30, 200);
    scene.fog = this.fog;
    this._tmpC = new T.Color(); this._tmpC2 = new T.Color();
  };

  W._buildWater = function () {
    if (this.waterY < -1e8) return;
    const tex = RT.tex.water();
    const mat = new T.MeshStandardMaterial({
      color: this.biome.water, roughness: 0.18, metalness: 0.12, transparent: true, opacity: 0.82, map: tex,
    });
    this.water = new T.Mesh(new T.PlaneGeometry(this.size * 9, this.size * 9), mat);
    this.water.rotation.x = -Math.PI / 2;
    this.water.position.y = this.waterY;
    this.water.receiveShadow = false;
    this.scene.add(this.water);
    this.anims.push((t) => { tex.offset.set(t * 0.004, t * 0.0025); });
  };

  // ----- colisão
  const CELL = 10;
  W.addCollider = function (c) {
    this.colliders.push(c);
    const r = c.r || Math.hypot(c.hw, c.hd);
    const x0 = Math.floor((c.x - r) / CELL), x1 = Math.floor((c.x + r) / CELL);
    const z0 = Math.floor((c.z - r) / CELL), z1 = Math.floor((c.z + r) / CELL);
    for (let i = x0; i <= x1; i++) for (let j = z0; j <= z1; j++) {
      const k = i + ',' + j;
      if (!this.grid.has(k)) this.grid.set(k, []);
      this.grid.get(k).push(c);
    }
  };
  // Empurra (x,z) para fora dos colisores; devolve {x,z,hit}
  W.collide = function (x, z, pr) {
    let hit = false;
    for (let pass = 0; pass < 2; pass++) {
      const list = this.grid.get(Math.floor(x / CELL) + ',' + Math.floor(z / CELL));
      if (!list) break;
      for (let i = 0; i < list.length; i++) {
        const c = list[i];
        if (c.r !== undefined) {
          const dx = x - c.x, dz = z - c.z, d = Math.hypot(dx, dz), m = c.r + pr;
          if (d < m) { const k = d < 1e-4 ? 1 : m / d; x = c.x + (d < 1e-4 ? m : dx * k); z = c.z + (d < 1e-4 ? 0 : dz * k); hit = true; }
        } else {
          const cs = Math.cos(c.rot), sn = Math.sin(c.rot);
          const dx = x - c.x, dz = z - c.z;
          let lx = dx * cs - dz * sn, lz = dx * sn + dz * cs;
          const ox = Math.abs(lx) - c.hw, oz = Math.abs(lz) - c.hd;
          if (ox < pr && oz < pr) {
            if (ox > 0 && oz > 0) { // canto
              const d = Math.hypot(ox, oz);
              if (d < pr) { const k = pr / (d || 1); lx = Math.sign(lx) * (c.hw + ox * k); lz = Math.sign(lz) * (c.hd + oz * k); hit = true; }
              else continue;
            } else if (ox > oz) lx = Math.sign(lx || 1) * (c.hw + pr);
            else lz = Math.sign(lz || 1) * (c.hd + pr);
            hit = true;
            x = c.x + lx * cs + lz * sn; z = c.z - lx * sn + lz * cs;
          }
        }
      }
    }
    return { x, z, hit };
  };

  // ----- estruturas
  function materialSet(world) {
    const m = {};
    const std = (o) => new T.MeshStandardMaterial(Object.assign({ roughness: 0.9, metalness: 0 }, o));
    m.std = std;
    return m;
  }
  W._buildStructures = function () {
    const self = this, ms = materialSet(this), rand = RT.rng(this.seed + 77);
    const mesh = (geo, mat, x, y, z) => { const o = new T.Mesh(geo, mat); o.position.set(x || 0, y || 0, z || 0); o.castShadow = true; o.receiveShadow = true; return o; };
    const box = (w, h, d, mat, x, y, z) => mesh(new T.BoxGeometry(w, h, d), mat, x, y, z);
    const cyl = (rt, rb, h, seg, mat, x, y, z) => mesh(new T.CylinderGeometry(rt, rb, h, seg), mat, x, y, z);
    const WALLS = [0xd9c9a8, 0xc9b79a, 0xe3d8c0, 0xb8a58a], WOOD = [0x6b4a2b, 0x7a5533, 0x5a3d24, 0x80603a], ROOF = [0x8a3b2a, 0x5a4a3a, 0x3f4a5a, 0x7a4a2a];
    const desert = this.env.biome === 'desert';
    const glowMat = () => { const mm = ms.std({ color: 0x1a1a1a, emissive: 0xffc060, emissiveIntensity: 0 }); self.glow.push(mm); return mm; };
    const fabric = [0xb04a3a, 0xc9a24a, 0x3a6a9a, 0x5a8a4a, 0xd8d0c0];

    const builders = {
      house(s, v) {
        const g = new T.Group(), w = 6.2 + (v % 2) * 1.6, d = 5.2 + (v % 3) * 0.6, h = 3.1;
        const wm = ms.std({ color: 0xffffff, map: RT.tex.plaster(WALLS[v % 4], 2, 1) });
        g.add(box(w, h, d, wm, 0, h / 2, 0));
        g.add(box(w + 0.2, 0.5, d + 0.2, ms.std({ color: 0xffffff, map: RT.tex.stone(0x777770, 3, 1) }), 0, 0.25, 0));
        const roof = mesh(gableRoof(w, d, 1.9 + (v % 2) * 0.4, 0.5), ms.std({ color: 0xffffff, map: RT.tex.roof(ROOF[v % 4], 3, 2), side: T.DoubleSide }), 0, h, 0);
        g.add(roof);
        g.add(box(0.9, 2.0, 0.12, ms.std({ color: WOOD[(v + 1) % 4] }), 0, 1.0, d / 2 + 0.03));
        const gm = glowMat();
        [-1, 1].forEach((sx) => g.add(box(0.8, 0.9, 0.1, gm, sx * (w / 2 - 1.3), 1.9, d / 2 + 0.04)));
        g.add(box(0.8, 0.9, 0.1, gm, w / 2 + 0.04, 1.9, 0).rotateY(Math.PI / 2));
        g.add(box(0.5, 1.4, 0.5, ms.std({ color: 0x6d6a66 }), w / 4, h + 1.4, -0.4));
        return { g, col: [{ hw: w / 2 + 0.1, hd: d / 2 + 0.1 }], emit: [{ x: 0, y: 1.9, z: d / 2 + 0.9, c: 0xffb060, i: 0.5, r: 9 }] };
      },
      cabin(s, v) {
        const g = new T.Group(), w = 4.6, d = 4, h = 2.6;
        g.add(box(w, h, d, ms.std({ color: 0xffffff, map: RT.tex.planks(WOOD[v % 4], 3, 2) }), 0, h / 2, 0));
        g.add(mesh(gableRoof(w, d, 1.4, 0.45), ms.std({ color: 0xffffff, map: RT.tex.planks(0x4a3526, 2, 2), side: T.DoubleSide }), 0, h, 0));
        g.add(box(0.85, 1.9, 0.1, ms.std({ color: 0x3f2c1c }), 0, 0.95, d / 2 + 0.03));
        const gm = glowMat();
        g.add(box(0.7, 0.7, 0.1, gm, 1.3, 1.6, d / 2 + 0.04));
        g.add(box(w + 0.8, 0.12, 1.2, ms.std({ color: WOOD[(v + 2) % 4] }), 0, 0.12, d / 2 + 0.6));
        return { g, col: [{ hw: w / 2 + 0.1, hd: d / 2 + 0.1 }], emit: [{ x: 0, y: 1.7, z: d / 2 + 0.9, c: 0xffb060, i: 0.4, r: 8 }] };
      },
      tower(s, v) {
        const g = new T.Group(), r = 2.3, h = 12 + (v % 3) * 2;
        g.add(cyl(r, r + 0.4, h, 14, ms.std({ color: 0xffffff, map: RT.tex.bricks(0x8a8780, 4, 4) }), 0, h / 2, 0));
        g.add(mesh(new T.ConeGeometry(r + 0.7, 4.2, 14), ms.std({ color: 0xffffff, map: RT.tex.roof(ROOF[v % 4], 3, 2) }), 0, h + 2.1, 0));
        const gm = glowMat();
        for (let i = 0; i < 3; i++) { const a = i * 2.1; g.add(box(0.5, 1.0, 0.3, gm, Math.cos(a) * r, h * 0.55 + i * 1.3, Math.sin(a) * r).rotateY(-a + Math.PI / 2)); }
        g.add(box(1, 2, 0.2, ms.std({ color: 0x3f2c1c }), 0, 1, r + 0.35));
        return { g, col: [{ r: r + 0.45 }], emit: [] };
      },
      ruin(s, v) {
        const g = new T.Group(), sm = ms.std({ color: 0xffffff, map: RT.tex.bricks(0x8d8a82, 3, 2) }), col = [];
        const r = RT.rng(this.seed || 5 + v);
        [[-3, 0, 6, 3.2, 0.6], [3, 0, 6, 2.2, 0.6], [0, -3, 0.6, 1.4, 6], [0, 3, 0.6, 2.8, 4.2]].forEach((p) => {
          g.add(box(p[2], p[3], p[4], sm, p[0], p[3] / 2, p[1]));
          col.push({ hw: p[2] / 2 + 0.1, hd: p[4] / 2 + 0.1, ox: p[0], oz: p[1] });
        });
        for (let i = 0; i < 5; i++) g.add(box(0.6 + r() * 0.6, 0.4 + r() * 0.4, 0.6 + r() * 0.6, sm, (r() - 0.5) * 8, 0.25, (r() - 0.5) * 8).rotateY(r() * 3));
        return { g, col, emit: [] };
      },
      tent(s, v) {
        const g = new T.Group(), mm = ms.std({ color: fabric[v % 5], roughness: 0.95, side: T.DoubleSide });
        const t = mesh(new T.ConeGeometry(2.4, 2.6, 4), mm, 0, 1.3, 0); t.rotation.y = Math.PI / 4; g.add(t);
        g.add(box(0.9, 1.5, 0.05, ms.std({ color: 0x1a1a1a }), 0, 0.75, 1.2));
        return { g, col: [{ r: 2.1 }], emit: [] };
      },
      stall(s, v) {
        const g = new T.Group(), wd = ms.std({ color: WOOD[v % 4] });
        [[-1.6, -1], [1.6, -1], [-1.6, 1], [1.6, 1]].forEach((p) => g.add(cyl(0.07, 0.07, 2.6, 6, wd, p[0], 1.3, p[1])));
        g.add(box(3.4, 0.9, 1.0, ms.std({ color: 0xffffff, map: RT.tex.planks(WOOD[(v + 1) % 4], 2, 1) }), 0, 0.45, 0.8));
        const cv = mesh(new T.PlaneGeometry(3.8, 2.6), ms.std({ color: fabric[v % 5], side: T.DoubleSide }), 0, 2.75, 0.1); cv.rotation.x = -Math.PI / 2 + 0.28; g.add(cv);
        for (let i = 0; i < 4; i++) g.add(box(0.4, 0.3, 0.4, ms.std({ color: [0xb04a3a, 0xc9a24a, 0x5a8a4a, 0xd8d0c0][i] }), -1.2 + i * 0.8, 1.05, 0.8));
        return { g, col: [{ hw: 1.8, hd: 1.3 }], emit: [] };
      },
      lamp(s) {
        const g = new T.Group(), gm = ms.std({ color: 0x222222, emissive: 0xffc060, emissiveIntensity: 0 });
        this.glow.push(gm);
        g.add(cyl(0.06, 0.09, 3.4, 6, ms.std({ color: 0x2a2a2e, metalness: 0.5, roughness: 0.5 }), 0, 1.7, 0));
        g.add(box(0.34, 0.42, 0.34, gm, 0, 3.5, 0));
        g.add(cyl(0.02, 0.28, 0.2, 4, ms.std({ color: 0x2a2a2e }), 0, 3.82, 0));
        return { g, col: [{ r: 0.25 }], emit: [{ x: 0, y: 3.4, z: 0, c: 0xffc477, i: 1.0, r: 13 }] };
      },
      well(s) {
        const g = new T.Group(), st = ms.std({ color: 0xffffff, map: RT.tex.stone(0x85827a, 3, 1) });
        g.add(cyl(1.15, 1.25, 1.0, 14, st, 0, 0.5, 0));
        g.add(cyl(0.9, 0.9, 0.05, 14, ms.std({ color: 0x142030, roughness: 0.2 }), 0, 0.85, 0));
        [-1, 1].forEach((sx) => g.add(box(0.12, 2.0, 0.12, ms.std({ color: 0x5a3d24 }), sx * 1.05, 1.9, 0)));
        const r = mesh(gableRoof(2.8, 2.2, 0.9, 0.2), ms.std({ color: 0xffffff, map: RT.tex.roof(0x6a3b2a, 2, 2), side: T.DoubleSide }), 0, 2.9, 0); g.add(r);
        return { g, col: [{ r: 1.35 }], emit: [] };
      },
      campfire(s) {
        const g = new T.Group();
        for (let i = 0; i < 8; i++) { const a = i * 0.785; g.add(mesh(new T.DodecahedronGeometry(0.22, 0), ms.std({ color: 0x6f6d68 }), Math.cos(a) * 0.8, 0.12, Math.sin(a) * 0.8)); }
        for (let i = 0; i < 4; i++) { const l = cyl(0.07, 0.07, 1.1, 6, ms.std({ color: 0x3f2c1c }), 0, 0.18, 0); l.rotation.set(Math.PI / 2 - 0.2, i * 0.8, 0); l.position.set(Math.cos(i * 0.8) * 0.1, 0.14, Math.sin(i * 0.8) * 0.1); g.add(l); }
        const f1 = mesh(new T.ConeGeometry(0.3, 0.9, 6), new T.MeshBasicMaterial({ color: 0xff8a2a, transparent: true, opacity: 0.92, fog: false }), 0, 0.55, 0);
        const f2 = mesh(new T.ConeGeometry(0.17, 0.6, 6), new T.MeshBasicMaterial({ color: 0xffe08a, transparent: true, opacity: 0.95, fog: false }), 0, 0.42, 0);
        f1.castShadow = f2.castShadow = false;
        g.add(f1, f2);
        const ph = Math.random() * 9;
        this.anims.push((t) => { const k = 0.85 + Math.sin(t * 13 + ph) * 0.12 + Math.sin(t * 7.3) * 0.08; f1.scale.set(1, k, 1); f2.scale.set(1, 1.05 - (k - 0.85), 1); });
        return { g, col: [{ r: 0.9 }], emit: [{ x: 0, y: 0.9, z: 0, c: 0xff9a40, i: 2.2, r: 16, always: true, flicker: true }] };
      },
      fence(s) {
        const g = new T.Group(), wd = ms.std({ color: 0x6b4a2b });
        for (let i = -3; i <= 3; i++) g.add(box(0.12, 1.1, 0.12, wd, i, 0.55, 0));
        [0.4, 0.8].forEach((y) => g.add(box(6.2, 0.09, 0.06, wd, 0, y, 0)));
        return { g, col: [{ hw: 3.1, hd: 0.15 }], emit: [] };
      },
      statue(s) {
        const g = new T.Group(), st = ms.std({ color: 0xffffff, map: RT.tex.stone(0x9a9a94, 2, 2) });
        g.add(box(1.4, 1.0, 1.4, st, 0, 0.5, 0));
        g.add(mesh(new T.CapsuleGeometry(0.28, 1.1, 4, 8), st, 0, 1.95, 0));
        g.add(mesh(new T.SphereGeometry(0.24, 12, 10), st, 0, 2.95, 0));
        g.add(mesh(new T.CapsuleGeometry(0.08, 0.9, 4, 6), st, 0.42, 2.3, 0).rotateZ(-0.5));
        return { g, col: [{ r: 0.95 }], emit: [] };
      },
      barn(s, v) {
        const g = new T.Group(), w = 9, d = 6.5, h = 4;
        g.add(box(w, h, d, ms.std({ color: 0xffffff, map: RT.tex.planks(0x8a3b2e, 4, 2) }), 0, h / 2, 0));
        g.add(mesh(gableRoof(w, d, 2.6, 0.6), ms.std({ color: 0xffffff, map: RT.tex.roof(0x4a4a4e, 4, 3), side: T.DoubleSide }), 0, h, 0));
        g.add(box(2.6, 3.0, 0.12, ms.std({ color: 0xe8e0d0 }), 0, 1.5, d / 2 + 0.04));
        return { g, col: [{ hw: w / 2 + 0.1, hd: d / 2 + 0.1 }], emit: [] };
      },
      bench(s) {
        const g = new T.Group(), wd = ms.std({ color: 0x6b4a2b });
        g.add(box(1.8, 0.1, 0.5, wd, 0, 0.5, 0)); g.add(box(1.8, 0.4, 0.08, wd, 0, 0.85, -0.22));
        [-0.8, 0.8].forEach((x) => g.add(box(0.08, 0.5, 0.45, wd, x, 0.25, 0)));
        return { g, col: [{ hw: 0.95, hd: 0.3 }], emit: [] };
      },
      sign(s) {
        const g = new T.Group();
        g.add(box(0.12, 2.0, 0.12, ms.std({ color: 0x5a3d24 }), 0, 1.0, 0));
        const label = s.label || '';
        const c = document.createElement('canvas'); c.width = 256; c.height = 96; const cx = c.getContext('2d');
        cx.fillStyle = '#7a5533'; cx.fillRect(0, 0, 256, 96); cx.strokeStyle = '#4a3220'; cx.lineWidth = 6; cx.strokeRect(3, 3, 250, 90);
        cx.fillStyle = '#f3e6c8'; cx.font = 'bold 30px serif'; cx.textAlign = 'center'; cx.textBaseline = 'middle'; cx.fillText(label.slice(0, 16), 128, 48, 230);
        const tx = new T.CanvasTexture(c); tx.colorSpace = T.SRGBColorSpace;
        g.add(box(1.4, 0.52, 0.06, ms.std({ map: tx }), 0, 1.75, 0.06));
        return { g, col: [{ r: 0.2 }], emit: [] };
      },
      crates(s, v) {
        const g = new T.Group(), wm = ms.std({ color: 0xffffff, map: RT.tex.planks(0x8a6a3f, 1, 1) });
        [[0, 0, 0, 0.9], [1.0, 0, 0.3, 0.8], [0.4, 0.9, 0.1, 0.7]].forEach((p) => g.add(box(p[3], p[3], p[3], wm, p[0], p[3] / 2 + p[1], p[2]).rotateY(p[2])));
        return { g, col: [{ hw: 1.0, hd: 0.8 }], emit: [] };
      },
      pillar(s) {
        const g = new T.Group(), st = ms.std({ color: 0xffffff, map: RT.tex.stone(0xb9b3a4, 1, 4) });
        g.add(cyl(0.5, 0.55, 5, 12, st, 0, 2.5, 0)); g.add(box(1.4, 0.35, 1.4, st, 0, 5.15, 0)); g.add(box(1.5, 0.3, 1.5, st, 0, 0.15, 0));
        return { g, col: [{ r: 0.7 }], emit: [] };
      },
      stone_circle(s) {
        const g = new T.Group(), st = ms.std({ color: 0xffffff, map: RT.tex.stone(0x8a8a84, 1, 2) }), col = [];
        for (let i = 0; i < 8; i++) { const a = i * Math.PI / 4, hh = 2.2 + (i % 3) * 0.5; const b = box(0.9, hh, 0.6, st, Math.cos(a) * 4, hh / 2, Math.sin(a) * 4); b.rotation.y = -a; b.rotation.z = (i % 2 ? 0.05 : -0.04); g.add(b); col.push({ r: 0.55, ox: Math.cos(a) * 4, oz: Math.sin(a) * 4 }); }
        return { g, col, emit: [] };
      },
    };

    (this.spec.structures || []).forEach((s, idx) => {
      const b = builders[s.type]; if (!b) return;
      const out = b.call(this, s, s.variant || 0);
      const g = out.g, sc = s.scale || 1, rot = (s.rot || 0) * Math.PI / 180;
      const y = this.heightAt(s.x, s.z);
      g.position.set(s.x, y - 0.05, s.z);
      g.rotation.y = rot; g.scale.setScalar(sc);
      g.traverse((o) => { if (o.isMesh) { o.castShadow = o.castShadow !== false; o.receiveShadow = true; } });
      this.scene.add(g);
      const cs = Math.cos(rot), sn = Math.sin(rot);
      (out.col || []).forEach((c) => {
        const ox = (c.ox || 0) * sc, oz = (c.oz || 0) * sc;
        const wx = s.x + ox * cs + oz * sn, wz = s.z - ox * sn + oz * cs;
        if (c.r !== undefined) this.addCollider({ x: wx, z: wz, r: c.r * sc });
        else this.addCollider({ x: wx, z: wz, hw: c.hw * sc, hd: c.hd * sc, rot: rot });
      });
      (out.emit || []).forEach((e) => {
        const lx = e.x * sc, lz = e.z * sc;
        this.emitters.push({ x: s.x + lx * cs + lz * sn, y: y + e.y * sc, z: s.z - lx * sn + lz * cs, c: e.c, i: e.i, r: e.r, always: !!e.always, flicker: !!e.flicker });
      });
      if (s.label) this.labels.push({ text: s.label, x: s.x, z: s.z, type: s.type });
    });
  };

  // ----- vegetação
  function treeGeometry(kind, leaf, rnd) {
    const P = [], lc = () => leaf[Math.floor(rnd() * leaf.length)];
    const cyl = (rt, rb, h, seg) => new T.CylinderGeometry(rt, rb, h, seg);
    if (kind === 'oak') {
      P.push({ geo: cyl(0.2, 0.32, 2.8, 6), mat: M4(0, 1.4, 0), color: 0x5a3d24 });
      [[0, 3.6, 0, 1.9], [0.9, 3.2, 0.3, 1.4], [-0.8, 3.3, -0.4, 1.5], [0.1, 4.5, 0.2, 1.3]].forEach((p) => P.push({ geo: new T.IcosahedronGeometry(p[3], 0), mat: M4(p[0], p[1], p[2], rnd(), rnd(), rnd()), color: lc() }));
    } else if (kind === 'pine') {
      P.push({ geo: cyl(0.14, 0.26, 2.2, 6), mat: M4(0, 1.1, 0), color: 0x4f3622 });
      [[2.0, 1.9, 2.4], [1.55, 3.4, 2.1], [1.1, 4.8, 1.8], [0.65, 6.0, 1.4]].forEach((p) => P.push({ geo: new T.ConeGeometry(p[0], p[2], 7), mat: M4(0, p[1] + p[2] / 2 - 0.2, 0), color: lc() }));
    } else if (kind === 'palm') {
      for (let i = 0; i < 5; i++) P.push({ geo: cyl(0.14 - i * 0.01, 0.18 - i * 0.01, 1.2, 6), mat: M4(i * 0.16, 0.6 + i * 1.15, 0, 0, 0, -0.14), color: 0x8a6a45 });
      for (let i = 0; i < 7; i++) { const a = i * 0.9; P.push({ geo: new T.ConeGeometry(0.35, 3.2, 4), mat: M4(0.8 + Math.cos(a) * 1.1, 6.1, Math.sin(a) * 1.1, Math.sin(a) * 1.15, 0, -Math.cos(a) * 1.15 - 0.2, 1, 1, 0.35), color: lc() }); }
    } else if (kind === 'cactus') {
      P.push({ geo: cyl(0.3, 0.32, 2.8, 8), mat: M4(0, 1.4, 0), color: 0x4f7d3a });
      P.push({ geo: cyl(0.17, 0.17, 1.1, 6), mat: M4(0.62, 1.7, 0, 0, 0, Math.PI / 2), color: 0x4f7d3a });
      P.push({ geo: cyl(0.17, 0.17, 0.9, 6), mat: M4(0.95, 2.15, 0), color: 0x4f7d3a });
      P.push({ geo: cyl(0.15, 0.15, 0.9, 6), mat: M4(-0.55, 1.4, 0, 0, 0, Math.PI / 2), color: 0x4f7d3a });
      P.push({ geo: cyl(0.15, 0.15, 0.8, 6), mat: M4(-0.85, 1.8, 0), color: 0x4f7d3a });
    } else { // árvore morta
      P.push({ geo: cyl(0.1, 0.28, 3.4, 5), mat: M4(0, 1.7, 0, 0, 0, 0.05), color: 0x4a3f36 });
      [[0.7, 2.3, 0.7], [-0.7, 2.8, -0.6], [0.5, 3.1, -0.5]].forEach((p, i) => P.push({ geo: cyl(0.04, 0.1, 1.5, 4), mat: M4(p[0], p[1], p[2], 0.5 * (i - 1), 0, i % 2 ? 0.9 : -0.9), color: 0x4a3f36 }));
    }
    return mergeGeos(P);
  }

  W._buildVegetation = function () {
    const env = this.env, B = this.biome, rnd = RT.rng(this.seed + 202), area = this.size * this.size;
    const treeCount = Math.min(this.budget.trees, Math.round(env.vegetation * (area / 10000) * 36));
    const rockCount = Math.min(this.budget.rocks, Math.round(env.rocks * (area / 10000) * 14));
    const std = new T.MeshStandardMaterial({ vertexColors: true, roughness: 0.92, flatShading: true });
    const tmpM = new T.Matrix4(), q = new T.Quaternion(), e = new T.Euler(), sv = new T.Vector3(), pv = new T.Vector3(), col = new T.Color();
    const kinds = B.trees, total = kinds.reduce((a, k) => a + k[1], 0);
    const lists = {}; kinds.forEach((k) => (lists[k[0]] = []));
    const clearOf = (x, z, extra) => {
      for (let i = 0; i < this.zones.length; i++) {
        const zn = this.zones[i]; if (Math.hypot(x - zn.x, z - zn.z) < zn.r0 + extra) return false;
      }
      return true;
    };
    let tries = 0;
    while (kinds.length && tries < treeCount * 8) {
      tries++;
      const n = Object.keys(lists).reduce((a, k) => a + lists[k].length, 0);
      if (n >= treeCount) break;
      const x = (rnd() - 0.5) * this.size * 0.94, z = (rnd() - 0.5) * this.size * 0.94;
      const y = this.heightAt(x, z);
      if (y < this.waterY + 0.7 || this.slopeAt(x, z) > 0.55) continue;
      const clump = RT.noise2(x * 0.018, z * 0.018, this.seed + 11);
      if (rnd() > Math.pow(clump, 1.4) * 1.6) continue;
      if (!clearOf(x, z, 2.5)) continue;
      let r = rnd() * total, kind = kinds[0][0];
      for (let i = 0; i < kinds.length; i++) { r -= kinds[i][1]; if (r <= 0) { kind = kinds[i][0]; break; } }
      lists[kind].push([x, y, z]);
    }
    this.treeCount = 0;
    Object.keys(lists).forEach((kind) => {
      const arr = lists[kind]; if (!arr.length) return;
      const geo = treeGeometry(kind, B.leaf, rnd);
      const im = new T.InstancedMesh(geo, std, arr.length);
      im.castShadow = true; im.receiveShadow = false;
      arr.forEach((p, i) => {
        const s = 0.75 + rnd() * 0.75;
        q.setFromEuler(e.set((rnd() - 0.5) * 0.08, rnd() * 6.28, (rnd() - 0.5) * 0.08));
        tmpM.compose(pv.set(p[0], p[1] - 0.1, p[2]), q, sv.set(s, s * (0.9 + rnd() * 0.3), s));
        im.setMatrixAt(i, tmpM);
        const v = 0.8 + rnd() * 0.4; im.setColorAt(i, col.setRGB(v, v * (0.92 + rnd() * 0.16), v));
        this.addCollider({ x: p[0], z: p[2], r: 0.42 * s });
      });
      im.instanceMatrix.needsUpdate = true; if (im.instanceColor) im.instanceColor.needsUpdate = true;
      this.scene.add(im); this.treeCount += arr.length;
    });
    // pedras
    if (rockCount > 0) {
      const rg = new T.DodecahedronGeometry(1, 0), rp = rg.attributes.position, rr = RT.rng(this.seed + 9);
      for (let i = 0; i < rp.count; i++) rp.setXYZ(i, rp.getX(i) * (0.8 + rr() * 0.4), rp.getY(i) * (0.7 + rr() * 0.4), rp.getZ(i) * (0.8 + rr() * 0.4));
      rg.computeVertexNormals();
      const rim = new T.InstancedMesh(rg, new T.MeshStandardMaterial({ color: B.rock, roughness: 0.95, flatShading: true }), rockCount);
      rim.castShadow = true; let n = 0;
      for (let t = 0; t < rockCount * 6 && n < rockCount; t++) {
        const x = (rnd() - 0.5) * this.size * 0.94, z = (rnd() - 0.5) * this.size * 0.94, y = this.heightAt(x, z);
        if (y < this.waterY + 0.3 || !clearOf(x, z, 1.5)) continue;
        const s = 0.35 + Math.pow(rnd(), 2.5) * 2.6;
        q.setFromEuler(e.set(rnd() * 3, rnd() * 6, rnd() * 3));
        tmpM.compose(pv.set(x, y + s * 0.25, z), q, sv.set(s * (0.8 + rnd() * 0.6), s * (0.6 + rnd() * 0.5), s * (0.8 + rnd() * 0.6)));
        rim.setMatrixAt(n, tmpM); const v = 0.75 + rnd() * 0.5; rim.setColorAt(n, col.setRGB(v, v, v));
        if (s > 0.9) this.addCollider({ x, z, r: s * 0.8 });
        n++;
      }
      rim.count = n; rim.instanceMatrix.needsUpdate = true; if (rim.instanceColor) rim.instanceColor.needsUpdate = true;
      this.scene.add(rim);
    }
    // capim ao redor do jogador (anel que acompanha)
    const gcount = B.grassBlades && env.vegetation > 0.15 ? Math.round(this.budget.grass * (0.5 + env.vegetation * 0.5)) : 0;
    this.grassCount = gcount;
    if (gcount > 0) {
      const gm = new T.MeshLambertMaterial({ map: RT.tex.blade(), alphaTest: 0.45, side: T.DoubleSide, transparent: false });
      const pg = new T.PlaneGeometry(0.5, 0.36); pg.translate(0, 0.18, 0);
      const pg2 = pg.clone().rotateY(Math.PI / 2);
      const merged = mergeGeos([{ geo: pg, color: 0xffffff }, { geo: pg2, color: 0xffffff }], true);
      merged.deleteAttribute('color');
      this.grass = new T.InstancedMesh(merged, gm, gcount);
      this.grass.frustumCulled = false; this.grass.receiveShadow = false;
      this.scene.add(this.grass);
      this._grassAt = { x: 1e9, z: 1e9 };
    }
  };

  W._updateGrass = function (px, pz) {
    if (!this.grass) return;
    if (Math.hypot(px - this._grassAt.x, pz - this._grassAt.z) < 7) return;
    this._grassAt = { x: px, z: pz };
    const R = 24, cell = Math.max(0.75, Math.sqrt((Math.PI * R * R) / this.grassCount) * 0.85);
    const i0 = Math.floor((px - R) / cell), i1 = Math.floor((px + R) / cell), j0 = Math.floor((pz - R) / cell), j1 = Math.floor((pz + R) / cell);
    const m = new T.Matrix4(), q = new T.Quaternion(), e = new T.Euler(), sv = new T.Vector3(), pv = new T.Vector3(), col = new T.Color();
    const g0 = new T.Color(this.biome.grass[0]), g1 = new T.Color(this.biome.grass[1]);
    let n = 0;
    for (let i = i0; i <= i1 && n < this.grassCount; i++) for (let j = j0; j <= j1 && n < this.grassCount; j++) {
      const hsh = RT.hash2(i, j, this.seed);
      if (hsh > 0.8) continue;
      const x = (i + RT.hash2(i, j, 3)) * cell, z = (j + RT.hash2(i, j, 4)) * cell;
      if (Math.hypot(x - px, z - pz) > R) continue;
      const y = this.heightAt(x, z);
      if (y < this.waterY + 0.9 || this.slopeAt(x, z) > 0.45) continue;
      let ok = true;
      for (let k = 0; k < this.zones.length; k++) { const zn = this.zones[k]; if (zn.solid && Math.hypot(x - zn.x, z - zn.z) < zn.r0 * 0.95) { ok = false; break; } }
      if (!ok) continue;
      const s = 0.7 + RT.hash2(i, j, 5) * 0.6;
      q.setFromEuler(e.set(0, RT.hash2(i, j, 6) * 6.28, 0));
      m.compose(pv.set(x, y - 0.03, z), q, sv.set(s, s * (0.8 + hsh * 0.6), s));
      this.grass.setMatrixAt(n, m);
      col.copy(g0).lerp(g1, RT.hash2(i, j, 7)).multiplyScalar(1.25);
      this.grass.setColorAt(n, col);
      n++;
    }
    this.grass.count = n;
    this.grass.instanceMatrix.needsUpdate = true;
    if (this.grass.instanceColor) this.grass.instanceColor.needsUpdate = true;
  };

  // ----- clima
  W._buildWeather = function () {
    const wx = this.weather, n = Math.min(this.budget.particles, 1800);
    this.precip = null;
    if (wx === 'rain' || wx === 'storm') {
      const p = new Float32Array(n * 6);
      for (let i = 0; i < n; i++) { const x = (Math.random() - 0.5) * 50, y = Math.random() * 25, z = (Math.random() - 0.5) * 50; p.set([x, y, z, x, y - 0.7, z], i * 6); }
      const g = new T.BufferGeometry(); g.setAttribute('position', new T.BufferAttribute(p, 3));
      this.precip = new T.LineSegments(g, new T.LineBasicMaterial({ color: 0xaac4e0, transparent: true, opacity: 0.45, fog: true, depthWrite: false }));
      this.precip.userData.kind = 'rain';
    } else if (wx === 'snow') {
      const p = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) p.set([(Math.random() - 0.5) * 50, Math.random() * 25, (Math.random() - 0.5) * 50], i * 3);
      const g = new T.BufferGeometry(); g.setAttribute('position', new T.BufferAttribute(p, 3));
      this.precip = new T.Points(g, new T.PointsMaterial({ color: 0xffffff, size: 0.22, map: RT.tex.dot(), transparent: true, depthWrite: false, opacity: 0.9 }));
      this.precip.userData.kind = 'snow';
    }
    if (this.precip) { this.precip.frustumCulled = false; this.scene.add(this.precip); }
    this.nextFlash = 4 + Math.random() * 8; this.flash = 0; this.onThunder = null;
  };
  W._updateWeather = function (dt, cam) {
    if (this.precip) {
      this.precip.position.set(cam.x, cam.y - 8, cam.z);
      const a = this.precip.geometry.attributes.position, arr = a.array;
      if (this.precip.userData.kind === 'rain') {
        const fall = 26 * dt;
        for (let i = 0; i < arr.length; i += 6) {
          arr[i + 1] -= fall; arr[i + 4] -= fall;
          if (arr[i + 1] < -2) { const y = 22 + Math.random() * 4; arr[i + 1] = y; arr[i + 4] = y - 0.7; }
        }
      } else {
        const t = performance.now() * 0.001;
        for (let i = 0; i < arr.length; i += 3) {
          arr[i + 1] -= 1.6 * dt; arr[i] += Math.sin(t + i) * 0.4 * dt;
          if (arr[i + 1] < -2) arr[i + 1] = 22 + Math.random() * 3;
        }
      }
      a.needsUpdate = true;
    }
    if (this.weather === 'storm') {
      this.nextFlash -= dt;
      if (this.nextFlash < 0) { this.flash = 1; this.nextFlash = 6 + Math.random() * 14; if (this.onThunder) setTimeout(this.onThunder, 400 + Math.random() * 1200); }
      this.flash = Math.max(0, this.flash - dt * 4);
    }
  };

  // ----- pool de luzes pontuais
  W._buildLightPool = function () {
    const n = this.budget.terrain_segments < 120 ? 2 : this.budget.terrain_segments < 200 ? 3 : 4;
    this.pool = [];
    for (let i = 0; i < n; i++) { const l = new T.PointLight(0xffb060, 0, 14, 1.6); l.castShadow = false; this.scene.add(l); this.pool.push(l); }
    this._poolT = 0;
  };
  W._updateLights = function (dt, px, pz, t) {
    this._poolT -= dt;
    if (this._poolT <= 0) {
      this._poolT = 0.5;
      const night = this.night;
      const cand = this.emitters.filter((e) => e.always || night > 0.15)
        .map((e) => ({ e, d: Math.hypot(e.x - px, e.z - pz) })).filter((o) => o.d < 55).sort((a, b) => a.d - b.d).slice(0, this.pool.length);
      this._active = cand.map((o) => o.e);
    }
    this.pool.forEach((l, i) => {
      const e = this._active && this._active[i];
      if (!e) { l.intensity = Math.max(0, l.intensity - dt * 6); return; }
      l.position.set(e.x, e.y, e.z); l.color.setHex(e.c); l.distance = e.r;
      const flick = e.flicker ? 0.85 + Math.sin(t * 11 + i) * 0.1 + Math.random() * 0.08 : 1;
      const target = e.i * 6 * flick * (e.always ? 1 : Math.min(1, this.night * 1.5));
      l.intensity += (target - l.intensity) * Math.min(1, dt * 6);
    });
  };

  // ----- hora do dia
  W.setTime = function (h) { this.time = ((h % 24) + 24) % 24; this._applySky(); };
  W._applySky = function () {
    const h = this.time;
    let a = SKY[0], b = SKY[1];
    for (let i = 0; i < SKY.length - 1; i++) if (h >= SKY[i].h && h <= SKY[i + 1].h) { a = SKY[i]; b = SKY[i + 1]; break; }
    const f = (h - a.h) / (b.h - a.h || 1);
    const oc = this.overcast, gray = this._tmpC2;
    const mix = (ca, cb, out) => out.setHex(ca).lerp(this._tmpC.setHex(cb), f);
    const zen = mix(a.z, b.z, this.skyU.zenith.value), hor = mix(a.hz, b.hz, this.skyU.horizon.value);
    const lum = (c) => c.r * 0.3 + c.g * 0.59 + c.b * 0.11;
    gray.setRGB(lum(zen) * 0.9, lum(zen) * 0.92, lum(zen) * 0.98); zen.lerp(gray, oc * 0.85);
    gray.setRGB(lum(hor) * 0.95, lum(hor) * 0.97, lum(hor) * 1.0); hor.lerp(gray, oc * 0.8);
    const sunC = this._tmpC.setHex(a.sun).lerp(gray.setHex(b.sun), f);
    const si = lerp(a.si, b.si, f) * (1 - oc * 0.75), hemi = lerp(a.hemi, b.hemi, f) * (1 - oc * 0.25);
    this.night = clamp(1 - smoothstep(5.3, 7.2, h) + smoothstep(18.6, 20.6, h), 0, 1);
    // direção do sol / lua
    const day = h >= 5.5 && h <= 18.5;
    const ang = day ? ((h - 6) / 12) * Math.PI : ((((h - 18 + 24) % 24) / 12) * Math.PI);
    const elev = Math.max(0.3, Math.sin(ang));
    this.sunDirV = new T.Vector3(Math.cos(ang) * 0.85, elev, 0.35).normalize();
    this.skyU.sunDir.value.copy(this.sunDirV);
    this.skyU.sunColor.value.copy(day ? sunC : this._tmpC.setHex(0xcfd8ff));
    this.skyU.glow.value = (day ? 1 : 0.35) * (1 - oc * 0.9);
    this.sun.color.copy(sunC);
    this.sun.intensity = si * (this.hemiBoost || 1);
    this.hemi.intensity = hemi * 1.05;
    this.hemi.color.copy(hor).lerp(this._tmpC.setHex(0xffffff), 0.35);
    this.hemi.groundColor.setHex(this.biome.grass[0]).multiplyScalar(0.5);
    this.baseExposure = lerp(a.exp, b.exp, f);
    this.fog.color.copy(hor);
    if (this.stars) this.stars.material.opacity = clamp(this.night * 1.1 - oc, 0, 1) * 0.95;
    this.glow.forEach((m) => { m.emissiveIntensity = this.night * 1.6; });
    const cc = this._tmpC.copy(hor).lerp(gray.setHex(0xffffff), 0.55);
    this.clouds.forEach((c) => { c.material.color.copy(cc).multiplyScalar(0.35 + (1 - this.night) * 0.75); c.material.opacity = c.userData.base * (0.25 + oc * 0.9) * (1 - this.night * 0.5); });
    this.sun.castShadow = this.budget.shadow > 0 && this.shadowsOn !== false && elev > 0.2;
  };
  W.setDistance = function (scale) {
    const far = this.budget.draw_distance * scale * ({ fog: 0.4, rain: 0.7, storm: 0.6, snow: 0.6, cloudy: 0.9 }[this.weather] || 1);
    this.fog.near = far * (this.weather === 'fog' ? 0.02 : 0.3); this.fog.far = far;
  };
  W.setShadows = function (on) { this.shadowsOn = on; this.sun.castShadow = on && this.budget.shadow > 0; };

  W.update = function (dt, cam, player, t) {
    if (this.env.day_cycle) { this.time = (this.time + dt * 24 / (this.env.day_length_min * 60)) % 24; this._acc = (this._acc || 0) + dt; if (this._acc > 0.25) { this._acc = 0; this._applySky(); } }
    const sd = this.sunDirV;
    this.sun.position.set(player.x + sd.x * 90, player.y + sd.y * 90, player.z + sd.z * 90);
    this.sun.target.position.set(player.x, player.y, player.z); this.sun.target.updateMatrixWorld();
    this.sky.position.copy(cam); this.stars.position.copy(cam);
    this.clouds.forEach((c) => { c.position.x += c.userData.speed * dt; if (c.position.x > 600) c.position.x = -600; });
    for (let i = 0; i < this.anims.length; i++) this.anims[i](t, dt);
    this._updateGrass(player.x, player.z);
    this._updateWeather(dt, cam);
    this._updateLights(dt, player.x, player.z, t);
    if (this.weather === 'storm' && this.flash > 0) { this.hemi.intensity += this.flash * 3; }
    if (this.water) this.water.material.color.setHex(this.biome.water).multiplyScalar(0.55 + (1 - this.night) * 0.55);
  };
  W.nearestLabel = function (x, z, maxd) {
    let best = null, bd = maxd || 18;
    for (let i = 0; i < this.labels.length; i++) { const l = this.labels[i], d = Math.hypot(l.x - x, l.z - z); if (d < bd) { bd = d; best = l; } }
    return best;
  };
})();
