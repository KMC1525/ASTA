// Layout da timeline do Studio: validação, presets em JSON (salvar no navegador, exportar e importar) e a ordem das janelas.
// Tudo aqui é dado puro (sem DOM), para o arquivo da timeline só aplicar o resultado. Um arquivo importado é entrada não confiável: cada campo é conferido e limitado.

export const PRESET_KIND = 'asta-studio-timeline-preset';
export const PRESET_VERSION = 1;
export const DEF_ORDER = ['left', 'center', 'right'];
const STORE = 'asta.stl.presets';
const MAX_PRESETS = 30, MAX_BYTES = 200 * 1024;

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

/** Só os campos válidos de um layout (números limitados, ordem como permutação, nomes de janelas conhecidos). */
export function sanitizeLayout(raw, toolIds) {
  const o = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {}, out = {};
  if (isNum(o.bin)) out.bin = clamp(Math.round(o.bin), 100, 1200);
  if (isNum(o.insp)) out.insp = clamp(Math.round(o.insp), 100, 1200);
  if (isNum(o.top)) out.top = clamp(Math.round(o.top), 100, 1400);
  if (isNum(o.rs)) out.rs = clamp(Math.round(o.rs * 100) / 100, 0.6, 2.4);
  if (isNum(o.mixw)) out.mixw = o.mixw <= 0 ? 0 : clamp(Math.round(o.mixw), 120, 900);
  if (Array.isArray(o.order) && o.order.length === 3 && DEF_ORDER.every((k) => o.order.includes(k))) out.order = o.order.slice();
  if (typeof o.flip === 'boolean') out.flip = o.flip;
  if (typeof o.mixLeft === 'boolean') out.mixLeft = o.mixLeft;
  if (o.inset && typeof o.inset === 'object') { out.inset = {}; ['l', 'r', 't', 'b'].forEach((k) => { out.inset[k] = isNum(o.inset[k]) ? clamp(Math.round(o.inset[k]), 0, 400) : 0; }); }
  if (o.tools && typeof o.tools === 'object') { out.tools = {}; toolIds.forEach((id) => { if (typeof o.tools[id] === 'boolean') out.tools[id] = o.tools[id]; }); }
  if (o.tab && typeof o.tab === 'object') { out.tab = {}; ['left', 'right'].forEach((s) => { if (typeof o.tab[s] === 'string' && toolIds.includes(o.tab[s])) out.tab[s] = o.tab[s]; }); }
  return out;
}

const LAYOUT_KEYS = ['bin', 'insp', 'top', 'rs', 'mixw', 'order', 'flip', 'mixLeft', 'inset', 'tools', 'tab'];

/** O objeto que vai para o arquivo .json: tipo, versão, nome, layout e ajustes da timeline. */
export function makePreset(name, lay, timeline) {
  const layout = {}; LAYOUT_KEYS.forEach((k) => { if (lay[k] !== undefined) layout[k] = JSON.parse(JSON.stringify(lay[k])); });
  return { kind: PRESET_KIND, version: PRESET_VERSION, name: String(name || '').trim().slice(0, 60) || 'Meu layout', saved: new Date().toISOString(), layout, timeline: { snap: !!(timeline || {}).snap, ripple: !!(timeline || {}).ripple } };
}

/** Lê um preset (texto JSON ou objeto). Devolve { name, layout, timeline } limpo ou lança Error com a razão (em português, já pronta para o aviso). */
export function parsePreset(src, toolIds) {
  let p = src;
  if (typeof src === 'string') {
    if (src.length > MAX_BYTES) throw new Error('Arquivo grande demais para ser um preset de timeline.');
    try { p = JSON.parse(src); } catch (e) { throw new Error('O arquivo não é um JSON válido.'); }
  }
  if (!p || typeof p !== 'object' || p.kind !== PRESET_KIND) throw new Error('Este JSON não é um preset de timeline do ASTA.');
  if (!isNum(p.version) || p.version > PRESET_VERSION) throw new Error('Preset de uma versão mais nova do ASTA: atualize o ASTA para usá-lo.');
  const layout = sanitizeLayout(p.layout, toolIds);
  if (!Object.keys(layout).length) throw new Error('O preset não tem nenhum ajuste de layout.');
  const tl = p.timeline && typeof p.timeline === 'object' ? p.timeline : {};
  return { name: String(p.name || '').trim().slice(0, 60) || 'Meu layout', layout, timeline: { snap: typeof tl.snap === 'boolean' ? tl.snap : undefined, ripple: typeof tl.ripple === 'boolean' ? tl.ripple : undefined } };
}

/** Presets guardados neste navegador: [{ id, name, saved, preset }]. */
export function loadPresets() {
  try { const a = JSON.parse(localStorage.getItem(STORE) || '[]'); return Array.isArray(a) ? a.filter((x) => x && typeof x.id === 'string' && x.preset && typeof x.preset === 'object').slice(0, MAX_PRESETS) : []; } catch (e) { return []; }
}
export function savePresets(list) { try { localStorage.setItem(STORE, JSON.stringify(list.slice(0, MAX_PRESETS))); return true; } catch (e) { return false; } }

/** Guarda (ou troca, se já existe o nome) um preset; devolve a lista nova. */
export function addPreset(list, preset) {
  const id = 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), same = list.findIndex((x) => x.name.toLowerCase() === preset.name.toLowerCase());
  const rec = { id: same >= 0 ? list[same].id : id, name: preset.name, saved: preset.saved, preset };
  const out = list.slice(); if (same >= 0) out[same] = rec; else out.unshift(rec);
  return out.slice(0, MAX_PRESETS);
}

export const fileName = (name) => (String(name || 'layout').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'layout');

/** Troca duas janelas de lugar na ordem do alto (left, center, right). */
export function swapOrder(order, a, b) {
  const o = order.slice(), i = o.indexOf(a), j = o.indexOf(b);
  if (i < 0 || j < 0 || i === j) return o;
  o[i] = b; o[j] = a; return o;
}
