import { api } from '../api.js';
import { t } from '../i18n.js';
import { fill, h, icon, popover, toast } from '../ui.js';
import { DEFAULT_ON, FILTERS as FX_FILTERS, FILTER_CSS as FX_CSS, TOOLS, buildTools } from './studio_tools.js';
import { DEF_ORDER, addPreset, fileName, loadPresets, makePreset, parsePreset, sanitizeLayout, savePresets, swapOrder } from './studio_layout.js';

// Timeline de edição do Studio, inspirada no Kdenlive: bin de mídias, monitor do projeto, inspetor de propriedades, mixer de áudio e trilhas com cortar, juntar, silenciar, mover, aparar…
const FPS = 24;
const FILTERS = FX_FILTERS, FILTER_CSS = FX_CSS;   // a lista de filtros é a mesma da ferramenta «Efeitos»
const SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4];
const HEAD_W = 118;
const uid = () => 'c_' + Math.random().toString(36).slice(2, 10);
const clone = (x) => JSON.parse(JSON.stringify(x));
const r3 = (x) => Math.round(x * 1000) / 1000;
export const timecode = (s) => { s = Math.max(0, s); const m = Math.floor(s / 60), sec = Math.floor(s % 60), f = Math.floor((s % 1) * FPS); return String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0') + ':' + String(f).padStart(2, '0'); };
export const fmtDur = (s) => { s = Math.round(s); const hh = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60; return hh ? `${hh}h ${String(m).padStart(2, '0')}min` : m ? `${m}min ${String(sec).padStart(2, '0')}s` : `${sec}s`; };

export function mountTimeline(host, o) {
  const pid = o.pid, eid = o.eid;
  const S = { tl: clone(o.timeline), assets: {}, pps: 36, t: 0, sel: new Set(), tool: 'select', snap: true, ripple: false, playing: false, undo: [], redo: [], saveTimer: 0, saved: true, w0: 0, t0: 0, raf: 0, aspect: o.aspect || '16:9' };
  const setAssets = (list) => { S.assets = {}; (list || []).forEach((a) => { S.assets[a.id] = a; }); };
  setAssets(o.assets);
  const media = (a) => `/api/studio/projects/${pid}/media/${a.file}`;
  const thumb = (a) => (a.kind === 'image' ? media(a) : `/api/studio/projects/${pid}/thumb/${a.id}`);
  const trackOf = (id) => S.tl.tracks.find((x) => x.id === id);
  const clipById = (id) => S.tl.clips.find((c) => c.id === id);
  const assetOf = (c) => S.assets[c.asset];
  const end = (c) => c.start + c.dur;
  const total = () => Math.max(0, ...S.tl.clips.map(end));
  const selClips = () => S.tl.clips.filter((c) => S.sel.has(c.id));
  const locked = (c) => { const tr = trackOf(c.track); return !tr || tr.locked; };
  const isMedia = (c) => { const a = assetOf(c); return !!a && a.kind !== 'image'; };
  const maxDur = (c) => { const a = assetOf(c); return a && a.kind !== 'image' && a.dur ? Math.max(0.1, (a.dur - c.in) / (c.speed || 1)) : 1e9; };

  // ---------------------------------------------------------------- persistência e histórico
  const status = h('span', { class: 'stl-status' });
  const paintStatus = () => { status.textContent = S.saved ? t('Salvo') : S.failed ? t('Sem salvar — tentando de novo') : t('Salvando…'); status.className = 'stl-status' + (S.saved ? '' : ' busy'); };
  async function save() {
    clearTimeout(S.saveTimer); S.saveTimer = 0;
    const sent = snap();
    try {
      await api(`/api/studio/projects/${pid}/episodes/${eid}/timeline`, { method: 'PUT', body: { timeline: S.tl } });
      S.failed = false; if (snap() === sent) S.saved = true; if (o.onSaved) o.onSaved(S.tl);   // mudou enquanto salvava? continua «Salvando…» e salva de novo
      if (!S.saved && !S.saveTimer) S.saveTimer = setTimeout(save, 300);
    } catch (e) {
      if (!S.failed) toast(t('Não consegui salvar a timeline: {e}. Tento de novo em instantes.', { e: e.message }), 'err');
      S.failed = true; if (!S.saveTimer && root.isConnected) S.saveTimer = setTimeout(save, 5000);
    }
    paintStatus();
  }
  const scheduleSave = () => { S.saved = false; paintStatus(); clearTimeout(S.saveTimer); S.saveTimer = setTimeout(save, 700); };
  const snap = () => JSON.stringify({ tracks: S.tl.tracks, clips: S.tl.clips, markers: S.tl.markers, master: S.tl.master });
  const pushUndo = () => { S.undo.push(snap()); if (S.undo.length > 120) S.undo.shift(); S.redo = []; };
  function restore(json) { const d = JSON.parse(json); S.tl.tracks = d.tracks; S.tl.clips = d.clips; S.tl.markers = d.markers; S.tl.master = d.master ?? 1; S.sel = new Set([...S.sel].filter((id) => clipById(id))); renderAll(); scheduleSave(); }
  const undo = () => { if (!S.undo.length) return; S.redo.push(snap()); restore(S.undo.pop()); };
  const redo = () => { if (!S.redo.length) return; S.undo.push(snap()); restore(S.redo.pop()); };
  function change(fn, keepSel) { pushUndo(); fn(); S.tl.clips.forEach((c) => { c.start = r3(Math.max(0, c.start)); c.dur = r3(Math.max(0.1, c.dur)); c.in = r3(Math.max(0, c.in)); }); if (!keepSel) S.sel = new Set([...S.sel].filter((id) => clipById(id))); renderAll(); scheduleSave(); }

  // ---------------------------------------------------------------- edições
  function splitAt(time, ids, strict) {
    const hit = (c) => !locked(c) && c.start + 0.04 < time && time < end(c) - 0.04;
    let targets = (ids && ids.length ? S.tl.clips.filter((c) => ids.includes(c.id)) : S.tl.clips).filter(hit);
    if (!targets.length && ids && ids.length && !strict) targets = S.tl.clips.filter(hit);   // a seleção não passa pelo cursor: corta o que estiver sob ele (a lâmina é estrita: só o clipe clicado)
    if (!targets.length) { toast(t('Não há clipe sob o cursor para cortar.')); return; }
    change(() => {
      const added = [];
      targets.forEach((c) => {
        const left = c.dur, cut = r3(time - c.start);
        const b = Object.assign(clone(c), { id: uid(), start: r3(time), dur: r3(left - cut), fade_in: 0 });
        if (isMedia(c)) b.in = r3(c.in + cut * (c.speed || 1));
        c.dur = cut; c.fade_out = 0;
        S.tl.clips.push(b); added.push(b.id);
      });
      S.sel = new Set(added);
    }, true);
  }
  function joinSel() {
    const cs = selClips().filter((c) => !locked(c));
    if (cs.length < 2) { toast(t('Selecione dois ou mais clipes para juntar.')); return; }
    let merged = 0, closed = 0;
    change(() => {
      const byTrack = {};
      cs.forEach((c) => { (byTrack[c.track] = byTrack[c.track] || []).push(c); });
      Object.values(byTrack).forEach((list) => {
        list.sort((a, b) => a.start - b.start);
        let cur = list[0];
        for (let i = 1; i < list.length; i++) {
          const n = list[i], same = cur.asset && cur.asset === n.asset && Math.abs((cur.speed || 1) - (n.speed || 1)) < 1e-6 && Math.abs(n.start - end(cur)) < 0.06
            && (!isMedia(cur) || Math.abs(n.in - (cur.in + cur.dur * (cur.speed || 1))) < 0.06) && !!cur.mute === !!n.mute && cur.filter === n.filter
            && Math.abs((cur.volume ?? 1) - (n.volume ?? 1)) < 0.001 && Math.abs((cur.opacity ?? 1) - (n.opacity ?? 1)) < 0.001 && Math.abs((cur.scale || 1) - (n.scale || 1)) < 0.001
            && Math.abs((cur.x || 0) - (n.x || 0)) < 0.001 && Math.abs((cur.y || 0) - (n.y || 0)) < 0.001 && cur.fit === n.fit && !(n.fade_in > 0);
          if (same) { cur.dur = r3(cur.dur + n.dur); cur.fade_out = n.fade_out; S.tl.clips.splice(S.tl.clips.indexOf(n), 1); S.sel.delete(n.id); merged++; }
          else { const gap = n.start - end(cur); if (Math.abs(gap) > 0.01) { n.start = r3(end(cur)); closed++; } cur = n; }
        }
      });
    }, true);
    toast(merged ? t('{n} parte(s) juntada(s)', { n: merged }) + (closed ? ' · ' + t('{n} espaço(s) fechado(s)', { n: closed }) : '') : closed ? t('{n} espaço(s) fechado(s)', { n: closed }) : t('Já estão juntos.'));
  }
  function toggleMute() {
    const cs = selClips().filter((c) => !locked(c));
    if (!cs.length) { toast(t('Selecione clipes para silenciar.')); return; }
    const all = cs.every((c) => c.mute);
    change(() => cs.forEach((c) => { c.mute = !all; }), true);
  }
  function del(ripple) {
    const cs = selClips().filter((c) => !locked(c));
    if (!cs.length) return;
    change(() => {
      const ids = new Set(cs.map((c) => c.id));
      if (ripple) {
        const ranges = cs.map((c) => [c.start, end(c)]).sort((a, b) => a[0] - b[0]);
        S.tl.clips = S.tl.clips.filter((c) => !ids.has(c.id));
        const merged = [];
        ranges.forEach((r) => { const l = merged[merged.length - 1]; if (l && r[0] <= l[1] + 1e-6) l[1] = Math.max(l[1], r[1]); else merged.push([...r]); });
        S.tl.clips.forEach((c) => { let sh = 0; merged.forEach((r) => { if (c.start >= r[1] - 1e-6) sh += r[1] - r[0]; }); if (sh && !locked(c)) c.start = r3(c.start - sh); });
      } else S.tl.clips = S.tl.clips.filter((c) => !ids.has(c.id));
      S.sel.clear();
    }, true);
  }
  function duplicate() {
    const cs = selClips().filter((c) => !locked(c));
    if (!cs.length) return;
    change(() => { const add = cs.map((c) => Object.assign(clone(c), { id: uid(), start: r3(end(c)) })); S.tl.clips.push(...add); S.sel = new Set(add.map((c) => c.id)); }, true);
  }
  function trimTo(side) {   // [ e ]: apara o começo/fim dos clipes selecionados no cursor
    const cs = selClips().filter((c) => !locked(c) && c.start < S.t && S.t < end(c));
    if (!cs.length) return;
    change(() => cs.forEach((c) => {
      if (side === 'start') { const d = S.t - c.start; if (isMedia(c)) c.in = r3(c.in + d * (c.speed || 1)); c.start = r3(S.t); c.dur = r3(c.dur - d); } else c.dur = r3(S.t - c.start);
    }), true);
  }
  let clip = [];
  function copySel(cut) {
    const cs = selClips().filter((c) => !locked(c) || !cut);
    if (!cs.length) return;
    clip = clone(cs); toast(t('{n} clipe(s) copiado(s)', { n: cs.length }));
    if (cut) del(false);
  }
  function paste() {
    if (!clip.length) { toast(t('Nada copiado.')); return; }
    const base = Math.min(...clip.map((c) => c.start));
    change(() => { const add = clip.filter((c) => trackOf(c.track) && !trackOf(c.track).locked).map((c) => Object.assign(clone(c), { id: uid(), start: r3(S.t + (c.start - base)) })); S.tl.clips.push(...add); S.sel = new Set(add.map((c) => c.id)); }, true);
  }
  function addMarker() { change(() => { S.tl.markers.push({ t: r3(S.t), label: '' }); S.tl.markers.sort((a, b) => a.t - b.t); }, true); }
  function addText() {
    const c = { id: uid(), track: '', asset: '', scene: '', label: '', start: r3(S.t), dur: 3, in: 0, speed: 1, mute: false, volume: 1, fade_in: 0, fade_out: 0, opacity: 1, fit: 'cover', x: 0, y: 0, scale: 1, filter: 'none',
      text: t('Texto'), size: S.aspect === '9:16' ? 50 : 42, color: '#ffffff', bg: '#000000', pos: 'bottom' };
    change(() => {
      const tr = S.tl.tracks.find((x) => x.kind === 'text' && !x.locked) || addLayer('text', true);   // sem camada de texto livre: cria uma
      if (!tr) { toast(t('Limite de 16 camadas.'), 'err'); return; }
      c.track = tr.id; S.tl.clips.push(c); S.sel = new Set([c.id]);
    }, true);
  }
  // Camadas livres: cada tipo tem as suas (vídeo só recebe vídeo, imagem só imagem, áudio só áudio, texto só texto, efeitos só efeitos). Mídia solta vai para a primeira camada do tipo
  // onde o trecho está livre; se não houver (ou todas estiverem ocupadas), uma camada nova é criada — sem empilhar clipes de tipos diferentes na mesma trilha.
  const kindOfAsset = (a) => (a.kind === 'audio' ? 'audio' : a.kind === 'image' ? 'image' : 'video');
  const accepts = (tr, a) => !tr.locked && tr.kind === kindOfAsset(a);
  const PREFIX = { video: 'V', audio: 'A', text: 'T', image: 'I', fx: 'FX' };
  const KIND_LABEL = { video: 'Vídeo', audio: 'Áudio', text: 'Texto', image: 'Imagem', fx: 'Efeitos' };
  function addLayer(kind, quiet) {   // espelha schema.add_track: a nova camada fica no topo do seu grupo (texto, efeitos, vídeo/imagem, áudio)
    if (S.tl.tracks.length >= 16) { toast(t('Limite de 16 camadas.'), 'err'); return null; }
    const pre = PREFIX[kind], nums = S.tl.tracks.filter((x) => x.kind === kind && x.name.toUpperCase().startsWith(pre) && /^\d+$/.test(x.name.slice(pre.length))).map((x) => parseInt(x.name.slice(pre.length), 10));
    let n = Math.max(0, ...nums) + 1; const ids = new Set(S.tl.tracks.map((x) => x.id)); while (ids.has('t_' + pre.toLowerCase() + n)) n++;
    const tr = { id: 't_' + pre.toLowerCase() + n, kind, name: pre + n, muted: false, hidden: false, locked: false, volume: 1, collapsed: false };
    const nText = S.tl.tracks.filter((x) => x.kind === 'text').length, nFx = S.tl.tracks.filter((x) => x.kind === 'fx').length;
    const at = { text: 0, fx: nText, video: nText + nFx, image: nText + nFx, audio: S.tl.tracks.length }[kind];
    if (quiet) { S.tl.tracks.splice(at, 0, tr); return tr; }
    change(() => { S.tl.tracks.splice(at, 0, tr); }, true);
    toast(t('Camada {n} criada.', { n: tr.name }), 'ok');
    return tr;
  }
  function pickTrack(kind, at, dur, ignoreBusy) {   // ignoreBusy: «Inserir» (empurra o resto da MESMA trilha) usa a camada padrão mesmo ocupada
    const list = S.tl.tracks.filter((x) => x.kind === kind && !x.locked);
    if (kind === 'video' || kind === 'image') list.reverse();   // a de baixo da lista de camadas é a «principal» (V1)
    const free = (tr) => !S.tl.clips.some((c) => c.track === tr.id && c.start < at + dur - 1e-6 && end(c) > at + 1e-6);
    const hit = ignoreBusy ? list[0] : list.find(free);
    if (hit) return hit;
    return addLayer(kind, true) || list[0];   // nenhuma livre: camada nova (a criação entra no mesmo passo do histórico de quem chamou)
  }
  function addAsset(a, at, trackId, opt) {
    opt = opt || {};
    const kind = kindOfAsset(a);
    const dur = opt.dur || (a.kind === 'image' ? 4 : Math.max(0.5, a.dur || 4));
    const start = at == null ? S.t : at;
    const given = trackId && trackOf(trackId);
    let tr = given && accepts(given, a) ? given : null;
    const c = { id: uid(), track: '', asset: a.id, scene: '', label: a.name.slice(0, 40), start: r3(start), dur, in: opt.in || 0, speed: 1, mute: false, volume: 1, fade_in: 0, fade_out: 0, opacity: 1, fit: 'cover', x: 0, y: 0, scale: 1, filter: 'none',
      text: '', size: 44, color: '#ffffff', bg: '', pos: 'bottom' };
    change(() => {
      if (!tr) tr = pickTrack(kind, start, dur, !!opt.ripple);
      if (!tr) { toast(t('Não há camada livre para esse tipo de mídia.')); return; }
      c.track = tr.id;
      if (opt.ripple) S.tl.clips.filter((x) => x.track === tr.id && x.start >= c.start - 1e-6).forEach((x) => { x.start = r3(x.start + dur); });   // «Inserir»: empurra o resto da trilha; «Sobrescrever» não mexe nos outros
      S.tl.clips.push(c); S.sel = new Set([c.id]);
    }, true);
    return c;
  }
  function addFx(filter, dur) {   // camada de efeitos: o filtro vale para tudo abaixo dela, enquanto o clipe dura
    const start = S.t;
    const c = { id: uid(), track: '', asset: '', scene: '', label: '', start: r3(start), dur: r3(dur), in: 0, speed: 1, mute: false, volume: 1, fade_in: 0, fade_out: 0, opacity: 1, fit: 'cover', x: 0, y: 0, scale: 1, filter, text: '', size: 44, color: '#ffffff', bg: '', pos: 'bottom' };
    change(() => {
      const list = S.tl.tracks.filter((x) => x.kind === 'fx' && !x.locked);
      const free = (tr) => !S.tl.clips.some((k) => k.track === tr.id && k.start < start + dur - 1e-6 && end(k) > start + 1e-6);
      const tr = list.find(free) || addLayer('fx', true);
      if (!tr) { toast(t('Limite de 16 camadas.'), 'err'); return; }
      c.track = tr.id; S.tl.clips.push(c); S.sel = new Set([c.id]);
    }, true);
  }
  function addCaptions(cues, st) {   // legendas viram clipes de texto numa camada de texto (a primeira destravada; senão, uma nova)
    if (!cues || !cues.length) return;
    st = st || {};
    change(() => {
      const tr = S.tl.tracks.find((x) => x.kind === 'text' && !x.locked) || addLayer('text', true);
      if (!tr) { toast(t('Limite de 16 camadas.'), 'err'); return; }
      const add = cues.map((q) => ({ id: uid(), track: tr.id, asset: '', scene: '', label: '', start: r3(Math.max(0, q.start)), dur: r3(Math.max(0.3, q.end - q.start)), in: 0, speed: 1, mute: false, volume: 1, fade_in: 0, fade_out: 0, opacity: 1, fit: 'cover', x: 0, y: 0, scale: 1,
        filter: 'none', text: q.text, size: st.size || 44, color: st.color || '#ffffff', bg: st.bg || '', pos: st.pos || 'bottom' }));
      S.tl.clips.push(...add); S.sel = new Set(add.map((x) => x.id));
    }, true);
  }
  function selectAll() {   // Shift+A: tudo que está na timeline (mover com o mouse ou , e . ; apagar com Del). Trilhas travadas ficam selecionadas, mas nada nelas é movido nem apagado.
    S.sel = new Set(S.tl.clips.map((c) => c.id)); renderAll();
    const n = S.sel.size, lk = S.tl.clips.filter((c) => locked(c)).length;
    toast(n ? t('{n} clipe(s) selecionado(s): arraste, use , e . para deslocar ou Del para apagar.', { n }) + (lk ? ' ' + t('{n} em trilhas travadas não serão alterados.', { n: lk }) : '') : t('A timeline está vazia.'));
  }
  function nudge(dt) {   // desloca os clipes selecionados (esquerda/direita), sem passar do começo e sem tocar nas trilhas travadas
    const cs = selClips().filter((c) => !locked(c));
    if (!cs.length) return;
    const d = Math.max(dt, -Math.min(...cs.map((c) => c.start)));
    if (Math.abs(d) < 1e-9) return;
    change(() => cs.forEach((c) => { c.start = r3(c.start + d); }), true);
  }
  function renameTrack(tr) { const v = prompt(t('Nome da camada'), tr.name); if (v && v.trim()) { pushUndo(); tr.name = v.trim().slice(0, 12); renderAll(); scheduleSave(); } }
  function moveTrack(tr, dir) {   // sobe/desce dentro do mesmo grupo (a ordem entre grupos é fixa: texto, efeitos, vídeo/imagem, áudio)
    const grp = (k) => (k === 'image' ? 'video' : k), i = S.tl.tracks.indexOf(tr), j = i + dir, o = S.tl.tracks[j];
    if (!o || grp(o.kind) !== grp(tr.kind)) return;
    pushUndo(); S.tl.tracks[i] = o; S.tl.tracks[j] = tr; renderAll(); scheduleSave();
  }
  function deleteTrack(tr) {
    const n = S.tl.clips.filter((c) => c.track === tr.id).length;
    if (S.tl.tracks.filter((x) => x.kind === tr.kind).length < 2 && ['video', 'audio'].includes(tr.kind) && S.tl.tracks.length < 3) { toast(t('Deixe ao menos uma camada de vídeo e uma de áudio.'), 'err'); return; }
    if (n && !confirm(t('Apagar a camada {n} e os {m} clipe(s) dela?', { n: tr.name, m: n }))) return;
    change(() => { S.tl.clips = S.tl.clips.filter((c) => c.track !== tr.id); S.tl.tracks = S.tl.tracks.filter((x) => x.id !== tr.id); });
  }
  function trackMenu(e, tr) {
    e.preventDefault(); e.stopPropagation();
    const at = h('div', { style: { position: 'fixed', left: e.clientX + 'px', top: e.clientY + 'px', width: '1px', height: '1px' } }); document.body.appendChild(at);
    const item = (ic, label, fn, dis) => h('div', { class: 'opt' + (dis ? ' disabled' : ''), role: 'menuitem', onclick: () => { if (dis) return; pop.close(); fn(); } }, icon(ic, 15), h('div', null, label));
    const grp = (k) => (k === 'image' ? 'video' : k), i = S.tl.tracks.indexOf(tr);
    const pop = popover(at, h('div', { class: 'toolmenu stl-menu', role: 'menu' }, item('edit', t('Renomear a camada'), () => renameTrack(tr)),
      item('chev', t('Subir a camada'), () => moveTrack(tr, -1), !(S.tl.tracks[i - 1] && grp(S.tl.tracks[i - 1].kind) === grp(tr.kind))), item('chevd', t('Descer a camada'), () => moveTrack(tr, 1), !(S.tl.tracks[i + 1] && grp(S.tl.tracks[i + 1].kind) === grp(tr.kind))),
      item('trash', t('Apagar a camada'), () => deleteTrack(tr))), () => at.remove());
  }
  function layerMenu(anchor) {
    const item = (k, ic) => h('div', { class: 'opt', role: 'menuitem', dataset: { layer: k }, onclick: () => { pop.close(); addLayer(k); } }, icon(ic, 15), h('div', null, t(KIND_LABEL[k])));
    const pop = popover(anchor, h('div', { class: 'toolmenu stl-menu', role: 'menu', id: 'stl-layer-menu' }, item('video', 'video'), item('image', 'image'), item('audio', 'audio'), item('text', 'type'), item('fx', 'wand')));
  }
  function toolsMenu(anchor) {
    const row = (x) => h('label', { class: 'opt tl-opt', role: 'menuitemcheckbox', title: t(x.hint) }, h('input', { type: 'checkbox', checked: !!LAY.tools[x.id], dataset: { tool: x.id }, onchange: (ev) => { setTool(x.id, ev.target.checked); } }), icon(x.icon, 15), h('div', null, h('b', null, t(x.label)), h('div', { class: 'muted small' }, t(x.hint))));
    popover(anchor, h('div', { class: 'toolmenu stl-menu', role: 'menu', id: 'stl-tools-menu' }, TOOLS.map(row), h('div', { class: 'opt', role: 'menuitem', onclick: () => { LAY.tools = Object.fromEntries(TOOLS.map((x) => [x.id, DEFAULT_ON.includes(x.id)])); applyTools(); saveLay(); } }, icon('refresh', 15), h('div', null, t('Voltar ao padrão')))));
  }

  // ---------------------------------------------------------------- layout: trocar janelas de lugar e presets em JSON
  const TOOL_IDS = TOOLS.map((x) => x.id);
  const commitLay = () => { applyLay(); saveLay(); renderAll(); if (isOn('monitor')) updatePreview(true); };
  const dlJson = (obj, name) => { const a = h('a', { href: URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' })), download: name }); document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); };
  const currentPreset = (name) => makePreset(name, LAY, { snap: S.snap, ripple: S.ripple });
  function applyPreset(p) {
    const lay = sanitizeLayout(p.layout, TOOL_IDS);
    Object.keys(lay).forEach((k) => { if (k === 'tools') Object.assign(LAY.tools, lay.tools); else if (k === 'tab') Object.assign(LAY.tab, lay.tab); else if (k === 'inset') LAY.inset = Object.assign({ l: 0, r: 0, t: 0, b: 0 }, lay.inset); else LAY[k] = lay[k]; });
    if (typeof p.timeline.snap === 'boolean') S.snap = p.timeline.snap;
    if (typeof p.timeline.ripple === 'boolean') S.ripple = p.timeline.ripple;
    LAY.mix = LAY.tools.mixer !== false; applyTools(); saveLay(); updatePreview(true);
  }
  function layoutMenu(anchor) {
    const body = h('div', { class: 'stl-lay', id: 'stl-lay-menu', role: 'menu' });
    const sw = (id, label, fn) => h('button', { class: 'btn sm', type: 'button', dataset: { swap: id }, onclick: () => { fn(); commitLay(); paint(); } }, icon('swap', 14), label);
    const swapSlot = (a, b) => () => { LAY.order = swapOrder(LAY.order, a, b); };
    const paint = () => {
      const list = loadPresets(), nameInp = h('input', { type: 'text', id: 'stl-preset-name', maxlength: 60, placeholder: t('Nome do preset'), 'aria-label': t('Nome do preset') });
      const save = () => {
        const p = currentPreset(nameInp.value || t('Meu layout')), next = addPreset(loadPresets(), p);
        if (!savePresets(next)) { toast(t('Não deu para guardar neste navegador.'), 'err'); return; }
        toast(t('Preset «{n}» guardado neste navegador.', { n: p.name }), 'ok'); paint();
      };
      nameInp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); save(); } });
      const fileIn = h('input', { type: 'file', accept: 'application/json,.json', class: 'hidden', id: 'stl-preset-file' });
      fileIn.addEventListener('change', async () => {
        const f = fileIn.files && fileIn.files[0]; fileIn.value = ''; if (!f) return;
        try { const p = parsePreset(await f.text(), TOOL_IDS); applyPreset(p); toast(t('Preset «{n}» aplicado.', { n: p.name }), 'ok'); paint(); } catch (e) { toast(t(e.message), 'err'); }
      });
      const rows = list.map((r) => h('div', { class: 'stl-preset', dataset: { id: r.id } }, h('span', { class: 'nm', title: r.name }, r.name),
        h('button', { class: 'btn sm primary', type: 'button', dataset: { act: 'apply' }, onclick: () => { try { const p = parsePreset(r.preset, TOOL_IDS); applyPreset(p); toast(t('Preset «{n}» aplicado.', { n: p.name }), 'ok'); } catch (e) { toast(t(e.message), 'err'); } } }, t('Aplicar')),
        h('button', { class: 'btn sm ghost icon', type: 'button', dataset: { act: 'export' }, title: t('Exportar este preset (.json)'), 'aria-label': t('Exportar este preset (.json)'), onclick: () => dlJson(r.preset, 'timeline-' + fileName(r.name) + '.json') }, icon('download', 14)),
        h('button', { class: 'btn sm ghost icon', type: 'button', dataset: { act: 'delete' }, title: t('Apagar este preset'), 'aria-label': t('Apagar este preset'), onclick: () => { savePresets(loadPresets().filter((x) => x.id !== r.id)); paint(); } }, icon('trash', 14))));
      fill(body,
        h('h5', null, t('Trocar de lugar')),
        h('div', { class: 'row' }, sw('left-center', t('Esquerda ⇄ centro'), swapSlot('left', 'center')), sw('center-right', t('Centro ⇄ direita'), swapSlot('center', 'right')), sw('left-right', t('Esquerda ⇄ direita'), swapSlot('left', 'right')),
          sw('flip', t('Timeline ⇄ janelas de cima'), () => { LAY.flip = !LAY.flip; }), sw('mixer', t('Mixer para o outro lado'), () => { LAY.mixLeft = !LAY.mixLeft; })),
        h('h5', null, t('Tamanho')),
        h('p', { class: 'muted small', style: { margin: '0 6px 6px' } }, t('Arraste as bordas das janelas: as divisórias mudam o tamanho de duas janelas e as bordas de fora recuam o editor naquele lado. Dois cliques voltam ao padrão.')),
        h('div', { class: 'row' }, h('button', { class: 'btn sm', type: 'button', id: 'stl-lay-reset', onclick: () => { Object.assign(LAY, clone(DEF), { tools: LAY.tools, tab: LAY.tab }); LAY.order = DEF_ORDER.slice(); applyTools(); saveLay(); paint(); } }, icon('refresh', 14), t('Voltar ao layout padrão'))),
        h('h5', null, t('Presets de layout')),
        h('div', { class: 'row' }, nameInp, h('button', { class: 'btn sm primary', type: 'button', id: 'stl-preset-save', onclick: save }, icon('check', 14), t('Guardar aqui'))),
        h('div', { id: 'stl-preset-list' }, rows.length ? rows : h('p', { class: 'muted small', style: { margin: '8px 6px' } }, t('Nenhum preset guardado ainda.'))),
        h('div', { class: 'row', style: { marginTop: '8px' } },
          h('button', { class: 'btn sm', type: 'button', id: 'stl-preset-export', onclick: () => dlJson(currentPreset(nameInp.value || t('Meu layout')), 'timeline-' + fileName(nameInp.value || 'layout') + '.json') }, icon('download', 14), t('Exportar o layout atual (.json)')),
          h('button', { class: 'btn sm', type: 'button', id: 'stl-preset-import', onclick: () => fileIn.click() }, icon('upload', 14), t('Importar .json')), fileIn));
    };
    paint(); popover(anchor, body);
  }

  // velocidade: o clipe usa o MESMO trecho da mídia, então a duração na timeline muda (2× = metade do tempo; 0,5× = o dobro), sem passar do fim da mídia
  function setSpeed(v) {
    if (!(v > 0)) return;
    const a = document.activeElement;
    change(() => selClips().filter((c) => !locked(c)).forEach((c) => { const old = c.speed || 1; c.speed = v; if (isMedia(c)) c.dur = r3(Math.max(0.1, Math.min(c.dur * old / v, maxDur(c)))); }), true);
    if (a && a.blur && a.tagName === 'SELECT') setTimeout(() => { try { a.blur(); } catch (e) { /* ok */ } }, 0);
  }
  const setProp = (k, v) => { const a = document.activeElement; change(() => selClips().filter((c) => !locked(c)).forEach((c) => { c[k] = v; }), true); if (a && a.blur && /^(SELECT|INPUT)$/.test(a.tagName) && a.type !== 'text') setTimeout(() => { if (document.activeElement === a || !root.contains(document.activeElement)) { try { a.blur(); } catch (e) { /* ok */ } } }, 0); };   // sem foco preso no campo, os atalhos voltam a funcionar

  // ---------------------------------------------------------------- DOM
  const toolBtn = (id, ic, label, key, fn, extra) => h('button', { class: 'stl-btn', type: 'button', id: 'stl-' + id, tabindex: '-1', onmousedown: (e) => e.preventDefault(), title: label + (key ? ` (${key})` : ''), onclick: fn }, icon(ic, 15), extra || null);
  const bar = h('div', { class: 'stl-bar' });
  const bin = h('div', { class: 'stl-bin stl-panel', id: 'stl-tool-media', dataset: { tool: 'media' } }), inspector = h('div', { class: 'stl-insp stl-panel', id: 'stl-tool-props', dataset: { tool: 'props' } });
  const monitor = h('div', { class: 'stl-mon ar-' + S.aspect.replace(':', '-') });
  const layers = h('div', { class: 'stl-layers' }), capEl = h('div', { class: 'stl-cap' });
  monitor.append(layers, capEl);
  const tcEl = h('span', { class: 'stl-tc' }), playBtn = h('button', { class: 'stl-btn', type: 'button', id: 'stl-play', title: t('Reproduzir/pausar') + ' (Space)', onclick: () => togglePlay() });
  const ruler = h('div', { class: 'stl-ruler' }), rows = h('div', { class: 'stl-rows' }), ph = h('div', { class: 'stl-ph' }), content = h('div', { class: 'stl-content' }, ruler, rows, ph);
  const scroller = h('div', { class: 'stl-scroll' }, content);
  const marquee = h('div', { class: 'stl-marquee hidden' });
  content.append(marquee);
  const gut = (id, dir, title) => h('div', { class: 'stl-gut ' + dir, id: 'stl-gut-' + id, role: 'separator', 'aria-orientation': dir === 'v' ? 'vertical' : 'horizontal', tabindex: '-1', title });
  const g1 = gut('bin', 'v', t('Arraste para mudar a largura do painel da esquerda (dois cliques: padrão)')), g2 = gut('insp', 'v', t('Arraste para mudar a largura do painel da direita (dois cliques: padrão)')), g3 = gut('top', 'h', t('Arraste para mudar a altura do monitor e da timeline (dois cliques: padrão)'));
  const leftDock = h('div', { class: 'stl-dock', id: 'stl-dock-left', dataset: { dock: 'left' } }), rightDock = h('div', { class: 'stl-dock', id: 'stl-dock-right', dataset: { dock: 'right' } });
  const center = h('div', { class: 'stl-mons', id: 'stl-tool-monitor' }, h('div', { class: 'stl-mon-wrap' }, monitor, h('div', { class: 'stl-trans' },
    h('button', { class: 'stl-btn', type: 'button', title: t('Início') + ' (Home)', onclick: () => seek(0) }, icon('skipback', 15)),
    h('button', { class: 'stl-btn', type: 'button', title: t('Quadro anterior') + ' (←)', onclick: () => seek(S.t - 1 / FPS) }, icon('stepback', 15)), playBtn,
    h('button', { class: 'stl-btn', type: 'button', title: t('Próximo quadro') + ' (→)', onclick: () => seek(S.t + 1 / FPS) }, icon('stepfwd', 15)),
    h('button', { class: 'stl-btn', type: 'button', title: t('Fim') + ' (End)', onclick: () => seek(total()) }, icon('skipfwd', 15)), tcEl)));
  const top = h('div', { class: 'stl-top' }, leftDock, g1, center, g2, rightDock);
  const mixer = h('div', { class: 'stl-mixer', id: 'stl-mixer' });
  const zoomRange = h('input', { type: 'range', class: 'stl-zoom nodrag', id: 'stl-zoom', min: 0, max: 100, step: 1, title: t('Zoom da timeline') });
  const posEl = h('span', { class: 'stl-pos', id: 'stl-pos' });
  const zbar = h('div', { class: 'stl-zbar' }, posEl, h('span', { class: 'grow' }), h('button', { class: 'stl-btn', type: 'button', title: t('Menos zoom') + ' (-)', onclick: () => zoom(1 / 1.35) }, icon('zoomout', 15)), zoomRange,
    h('button', { class: 'stl-btn', type: 'button', title: t('Mais zoom') + ' (+)', onclick: () => zoom(1.35) }, icon('zoomin', 15)), h('button', { class: 'stl-btn', type: 'button', title: t('Ajustar à tela'), onclick: () => fit() }, icon('fit', 15)));
  const gm = gut('mixer', 'v', t('Arraste para mudar a largura do mixer (dois cliques: automático)'));
  const tlwrap = h('div', { class: 'stl-tlwrap' }, scroller, gm, mixer);
  const root = h('div', { class: 'stl' }, bar, top, g3, tlwrap, zbar);
  fill(host, root);
  // tamanhos e janelas (Tools) ligadas — guardados no navegador
  const DEF = { bin: 230, insp: 290, top: 250, rs: 1.15, mix: true, mixw: 0, order: DEF_ORDER.slice(), flip: false, mixLeft: false, inset: { l: 0, r: 0, t: 0, b: 0 } };
  let LAY = Object.assign({}, DEF);
  try { Object.assign(LAY, sanitizeLayout(JSON.parse(localStorage.getItem('asta.stl.layout') || '{}'), TOOLS.map((x) => x.id)), { mix: undefined }); } catch (e) { /* ok */ }
  if (LAY.mix === undefined) LAY.mix = true;
  LAY.order = LAY.order.slice(); LAY.inset = Object.assign({ l: 0, r: 0, t: 0, b: 0 }, LAY.inset);
  if (!LAY.tools || typeof LAY.tools !== 'object') LAY.tools = Object.fromEntries(TOOLS.map((x) => [x.id, x.id === 'mixer' ? LAY.mix !== false : DEFAULT_ON.includes(x.id)]));   // layouts antigos só conheciam o mixer
  TOOLS.forEach((x) => { if (LAY.tools[x.id] === undefined) LAY.tools[x.id] = DEFAULT_ON.includes(x.id); });
  LAY.tab = LAY.tab && typeof LAY.tab === 'object' ? LAY.tab : {};
  LAY.mix = LAY.tools.mixer !== false;
  const isOn = (id) => !!LAY.tools[id];
  const dockIds = (side) => TOOLS.filter((x) => x.dock === side && isOn(x.id)).map((x) => x.id);
  const isVisible = (id) => { const d = TOOLS.find((x) => x.id === id); return !!d && isOn(id) && (d.dock === 'left' || d.dock === 'right' ? LAY.tab[d.dock] === id : true); };
  const clampLay = () => { const H = root.clientHeight || 700, W = root.clientWidth || 1200; LAY.bin = Math.max(140, Math.min(LAY.bin, W * 0.45)); LAY.insp = Math.max(190, Math.min(LAY.insp, W * 0.45)); LAY.top = Math.max(140, Math.min(LAY.top, H - 150)); LAY.rs = Math.max(0.6, Math.min(2.4, LAY.rs)); LAY.mix = LAY.tools.mixer !== false; LAY.mixw = LAY.mixw > 0 ? Math.max(140, Math.min(LAY.mixw, W * 0.6)) : 0;
    ['l', 'r'].forEach((k) => { LAY.inset[k] = Math.max(0, Math.min(LAY.inset[k] || 0, W * 0.3)); }); ['t', 'b'].forEach((k) => { LAY.inset[k] = Math.max(0, Math.min(LAY.inset[k] || 0, H * 0.2)); }); };
  const SLOT = { left: leftDock, center, right: rightDock };
  let topSig = '';
  const applyLay = () => {
    clampLay(); root.style.setProperty('--bin', LAY.bin + 'px'); root.style.setProperty('--insp', LAY.insp + 'px'); root.style.setProperty('--toph', LAY.top + 'px'); root.style.setProperty('--rs', String(LAY.rs)); root.classList.toggle('no-mixer', !LAY.mix);
    // janelas do alto: a ordem (esquerda, centro, direita) pode ser trocada; no celular vale sempre a ordem padrão
    const narrow = !!(window.matchMedia && window.matchMedia('(max-width:980px)').matches), order = narrow ? DEF_ORDER : LAY.order;
    const vis = { left: dockIds('left').length > 0, center: isOn('monitor'), right: dockIds('right').length > 0 };
    Object.keys(SLOT).forEach((k) => SLOT[k].classList.toggle('hidden', !vis[k]));
    const seq = order.filter((k) => vis[k]), gs = [g1, g2], sizes = [];
    gs.forEach((g) => { g.classList.add('hidden'); g._ks = null; });
    const kids = [];
    seq.forEach((k, i) => {
      kids.push(SLOT[k]);
      sizes.push(k === 'center' ? 'minmax(0,1fr)' : (seq.length === 1 || (!vis.center && i === seq.length - 1)) ? 'minmax(0,1fr)' : (k === 'left' ? LAY.bin : LAY.insp) + 'px');
      if (i < seq.length - 1) {
        const g = gs[i], a2 = k, b2 = seq[i + 1]; g.classList.remove('hidden');
        g._ks = a2 !== 'center' ? { key: a2 === 'left' ? 'bin' : 'insp', sign: 1 } : { key: b2 === 'left' ? 'bin' : 'insp', sign: -1 };   // a janela de painel é a que cresce; a do centro (monitor) absorve o resto
        kids.push(g); sizes.push('6px');
      }
    });
    Object.keys(SLOT).forEach((k) => { if (!seq.includes(k)) kids.push(SLOT[k]); }); gs.forEach((g) => { if (!kids.includes(g)) kids.push(g); });
    edges.filter((e) => e._host === top).forEach((e) => kids.push(e));
    const sig = kids.map((el) => el.id || el.dataset.dock || el.dataset.side || 'c').join('|'); if (sig !== topSig) { topSig = sig; top.replaceChildren(...kids); }
    top.style.gridTemplateColumns = sizes.join(' ');
    const none = !seq.length; root.classList.toggle('no-top', none); g3.classList.toggle('hidden', none);   // sem janelas no alto, a timeline ocupa tudo
    // timeline em cima ou embaixo das janelas
    root.classList.toggle('flip', !!LAY.flip); const O = LAY.flip ? { top: 4, g3: 3, tl: 1, zb: 2 } : { top: 1, g3: 2, tl: 3, zb: 4 };
    bar.style.order = '0'; top.style.order = String(O.top); g3.style.order = String(O.g3); tlwrap.style.order = String(O.tl); zbar.style.order = String(O.zb);
    // mixer: de que lado da timeline e qual a largura
    gm.classList.toggle('hidden', !LAY.mix); mixer.style.order = LAY.mixLeft ? '0' : '2'; gm.style.order = '1'; scroller.style.order = LAY.mixLeft ? '2' : '0';
    mixer.classList.toggle('left', !!LAY.mixLeft); mixer.style.width = LAY.mixw > 0 ? LAY.mixw + 'px' : ''; mixer.style.maxWidth = LAY.mixw > 0 ? 'none' : '';
    // recuos nas quatro bordas do editor (cada janela encolhe a partir da borda)
    const I = LAY.inset, topEl = LAY.flip ? tlwrap : top, botEl = LAY.flip ? top : tlwrap;
    [top, tlwrap].forEach((el) => { el.style.paddingLeft = I.l ? I.l + 'px' : ''; el.style.paddingRight = I.r ? I.r + 'px' : ''; el.style.paddingTop = ''; el.style.paddingBottom = ''; });
    topEl.style.paddingTop = I.t ? I.t + 'px' : ''; botEl.style.paddingBottom = I.b ? I.b + 'px' : '';
    edges.forEach((e) => { const side = e.dataset.side; e.style[side === 'l' ? 'left' : side === 'r' ? 'right' : side === 't' ? 'top' : 'bottom'] = (I[side] || 0) + 'px'; e.classList.toggle('active', (I[side] || 0) > 0); });
    edges.forEach((e) => { const hostEl = e.parentNode; if (e.dataset.side === 't') e.classList.toggle('hidden', hostEl !== topEl); if (e.dataset.side === 'b') e.classList.toggle('hidden', hostEl !== botEl); });
    g1.title = g2.title = t('Arraste para mudar a largura da janela ao lado (dois cliques: padrão)');
    g3.title = t('Arraste para mudar a altura das janelas de cima e da timeline (dois cliques: padrão)');
  };
  const saveLay = () => { try { localStorage.setItem('asta.stl.layout', JSON.stringify(LAY)); } catch (e) { /* ok */ } };
  const dragGut = (g, ks) => {
    g.addEventListener('dblclick', () => { const { key } = ks(); LAY[key] = DEF[key]; applyLay(); saveLay(); renderAll(); });
    g.addEventListener('pointerdown', (e) => {
      e.preventDefault(); const { key, sign } = ks(), horiz = g.classList.contains('h'), p0 = horiz ? e.clientY : e.clientX, v0 = LAY[key] || (key === 'mixw' ? mixer.offsetWidth : 0); g.setPointerCapture(e.pointerId); g.classList.add('on');
      const mv = (ev) => { LAY[key] = v0 + sign * ((horiz ? ev.clientY : ev.clientX) - p0); applyLay(); if (key !== 'top') { paintRuler(); } };
      const up = () => { g.removeEventListener('pointermove', mv); g.removeEventListener('pointerup', up); g.classList.remove('on'); saveLay(); renderAll(); };
      g.addEventListener('pointermove', mv); g.addEventListener('pointerup', up);
    });
  };
  dragGut(g1, () => g1._ks || { key: 'bin', sign: 1 }); dragGut(g2, () => g2._ks || { key: 'insp', sign: -1 });
  dragGut(g3, () => ({ key: 'top', sign: LAY.flip ? -1 : 1 }));
  dragGut(gm, () => ({ key: 'mixw', sign: LAY.mixLeft ? 1 : -1 }));
  // bordas externas: arrastar para dentro recua a janela daquele lado (cada janela encolhe a partir da borda; dois cliques voltam)
  const edges = [];
  [['l', top], ['r', top], ['t', top], ['b', top], ['l', tlwrap], ['r', tlwrap], ['t', tlwrap], ['b', tlwrap]].forEach(([side, hostEl]) => {
    const e = h('div', { class: 'stl-edge ' + side, dataset: { side }, role: 'separator', tabindex: '-1', title: t('Arraste para recuar esta borda do editor (dois cliques: voltar)') }); e._host = hostEl; hostEl.append(e); edges.push(e);
    const horiz = side === 't' || side === 'b', sign = side === 'l' || side === 't' ? 1 : -1;
    e.addEventListener('dblclick', () => { LAY.inset[side] = 0; applyLay(); saveLay(); renderAll(); });
    e.addEventListener('pointerdown', (ev) => {
      ev.preventDefault(); const p0 = horiz ? ev.clientY : ev.clientX, v0 = LAY.inset[side] || 0; e.setPointerCapture(ev.pointerId); e.classList.add('on');
      const mv = (m) => { LAY.inset[side] = v0 + sign * ((horiz ? m.clientY : m.clientX) - p0); applyLay(); paintRuler(); };
      const up = () => { e.removeEventListener('pointermove', mv); e.removeEventListener('pointerup', up); e.classList.remove('on'); saveLay(); renderAll(); };
      e.addEventListener('pointermove', mv); e.addEventListener('pointerup', up);
    });
  });

  // ---------------------------------------------------------------- Tools: as janelas do editor e as ferramentas extras
  const setProps = (obj) => { change(() => selClips().filter((c) => !locked(c)).forEach((c) => Object.assign(c, obj)), true); };
  const T = buildTools({ pid, S, mediaUrl: (a) => media(a), selClips, setProp: (k, v) => setProp(k, v), setProps, trackOf, select: (ids) => { S.sel = new Set(ids); renderAll(); }, seek: (x) => seek(x),
    addAsset: (a, at) => addAsset(a, at), addFx: (f, d) => addFx(f, d), addCaptions: (q, st) => addCaptions(q, st), addAssetRec: (a) => { S.assets[a.id] = a; if (o.onAsset) o.onAsset(a); paintBin(); }, isOn, isVisible });
  const panelEl = (id) => (id === 'media' ? bin : id === 'props' ? inspector : T.panels[id]);
  function paintDocks() {
    ['left', 'right'].forEach((side) => {
      const ids = dockIds(side), dock = side === 'left' ? leftDock : rightDock;
      if (!ids.length) { dock.replaceChildren(); return; }
      if (!ids.includes(LAY.tab[side])) LAY.tab[side] = ids[0];
      const tabs = ids.length > 1 ? h('div', { class: 'stl-tabs2', role: 'tablist' }, ids.map((id) => { const d = TOOLS.find((x) => x.id === id); return h('button', { type: 'button', role: 'tab', class: 'tb' + (LAY.tab[side] === id ? ' on' : ''), dataset: { tab: id }, title: t(d.hint),
        onclick: () => { LAY.tab[side] = id; saveLay(); paintDocks(); T.refresh(id); } }, icon(d.icon, 13), h('span', null, t(d.label))); })) : null;
      fill(dock, tabs, panelEl(LAY.tab[side]));
    });
  }
  function applyTools() { paintDocks(); applyLay(); if (isOn('monitor')) updatePreview(true); renderAll(); buildBar(); }
  function setTool(id, on) {
    LAY.tools[id] = !!on; if (id === 'mixer') LAY.mix = !!on;
    if (!on && id === 'capture') { const p = T.panels.capture; if (p && p._stop) p._stop(); }
    applyTools(); saveLay();
  }
  paintDocks(); applyLay();

  function buildBar() {
    const sep = () => h('span', { class: 'stl-sep' });
    const toggle = (id, ic, label, key, get, set) => { const b = toolBtn(id, ic, label, key, () => { set(!get()); paintBar(); }); b.classList.toggle('on', get()); return b; };
    const paintBar = () => {
      fill(bar,
        toolBtn('t-select', 'cursor', t('Selecionar'), 'V', () => { S.tool = 'select'; paintBar(); }), toolBtn('t-razor', 'razor', t('Lâmina: clique no clipe para cortar'), 'C', () => { S.tool = S.tool === 'razor' ? 'select' : 'razor'; paintBar(); }),
        sep(), toolBtn('split', 'scissors', t('Cortar no cursor'), 'S', () => splitAt(S.t, [...S.sel])), toolBtn('join', 'join', t('Juntar clipes selecionados'), 'J', joinSel), toolBtn('mute', 'mute', t('Silenciar / reativar o som'), 'M', toggleMute),
        toolBtn('del', 'trash', t('Excluir'), 'Del', () => del(false)), toolBtn('rdel', 'ripple', t('Excluir e fechar o espaço'), 'Shift+Del', () => del(true)), toolBtn('dup', 'copy', t('Duplicar'), 'Ctrl+D', duplicate),
        sep(), toolBtn('trim-s', 'trimstart', t('Aparar o começo no cursor'), '[', () => trimTo('start')), toolBtn('trim-e', 'trimend', t('Aparar o fim no cursor'), ']', () => trimTo('end')),
        toolBtn('text', 'type', t('Adicionar texto'), 'T', addText), toolBtn('marker', 'flag', t('Marcador no cursor'), 'K', addMarker),
        sep(), toolBtn('undo', 'undo', t('Desfazer'), 'Ctrl+Z', undo), toolBtn('redo', 'redo', t('Refazer'), 'Ctrl+Shift+Z', redo),
        sep(), toggle('snap', 'magnet', t('Ímã: gruda nas bordas dos clipes'), '', () => S.snap, (v) => { S.snap = v; }), toggle('ripple', 'ripple', t('Mover em cadeia (ripple)'), '', () => S.ripple, (v) => { S.ripple = v; }),
        sep(), toolBtn('layer', 'layers', t('Nova camada: vídeo, imagem, áudio, texto ou efeitos'), '', (e) => layerMenu(e.currentTarget), h('span', { class: 'lbl' }, t('Camada'))),
        toolBtn('tools', 'columns', t('Tools: ligar e desligar as janelas do editor'), '', (e) => toolsMenu(e.currentTarget), h('span', { class: 'lbl' }, t('Tools'))),
        toolBtn('layout', 'grid', t('Layout: trocar as janelas de lugar, tamanhos e presets em JSON'), '', (e) => layoutMenu(e.currentTarget), h('span', { class: 'lbl' }, t('Layout'))),
        h('span', { class: 'grow' }), toolBtn('rowdn', 'rowsmall', t('Trilhas mais baixas'), '', () => { LAY.rs -= 0.2; applyLay(); saveLay(); renderAll(); }), toolBtn('rowup', 'rowbig', t('Trilhas mais altas'), '', () => { LAY.rs += 0.2; applyLay(); saveLay(); renderAll(); }),
        toolBtn('mixer', 'audio', t('Mixer de áudio'), '', () => { setTool('mixer', !LAY.mix); }),
        toolBtn('full', 'expand', t('Tela cheia do editor') + ' (F)', 'F', () => toggleFull()), sep(), h('button', { class: 'stl-btn', type: 'button', tabindex: '-1', onmousedown: (e) => e.preventDefault(), title: t('Menos zoom') + ' (-)', onclick: () => zoom(1 / 1.35) }, icon('zoomout', 15)),
        h('button', { class: 'stl-btn', type: 'button', title: t('Mais zoom') + ' (+)', onclick: () => zoom(1.35) }, icon('zoomin', 15)), h('button', { class: 'stl-btn', type: 'button', title: t('Ajustar à tela'), onclick: fit }, icon('fit', 15)),
        status);
      const tool = (id) => bar.querySelector('#stl-t-' + id); if (tool(S.tool)) tool(S.tool).classList.add('on');
      content.classList.toggle('razor', S.tool === 'razor');
      const on = (id, v) => { const b = bar.querySelector('#stl-' + id); if (b) b.classList.toggle('on', !!v); }; on('mixer', LAY.mix);
      ['layer', 'tools', 'layout'].forEach((id) => { const b = bar.querySelector('#stl-' + id); if (b) b.classList.add('wide'); });
    };
    paintBar();
  }

  // ---------------------------------------------------------------- bin (mídias do projeto)
  function paintBin() {
    const list = Object.values(S.assets).sort((a, b) => (a.created < b.created ? 1 : -1));
    const fileIn = h('input', { type: 'file', multiple: true, accept: 'image/*,video/*,audio/*,.zip,.rar,.7z,.tar,.tgz,.cbz,.cbr', class: 'hidden' });
    fileIn.addEventListener('change', async () => {
      for (const f of fileIn.files) {
        try { const r = await fetch(`/api/studio/projects/${pid}/media`, { method: 'POST', headers: { 'X-Filename': encodeURIComponent(f.name), 'Content-Type': f.type || 'application/octet-stream' }, body: f }); const j = await r.json(); if (!r.ok) throw new Error(j.error || 'erro'); for (const a of [j, ...(j.also || [])]) { S.assets[a.id] = a; if (o.onAsset) o.onAsset(a); } }
        catch (e) { toast(f.name + ': ' + e.message, 'err'); }
      }
      fileIn.value = ''; paintBin();
    });
    fill(bin, h('div', { class: 'stl-bin-h' }, h('b', null, t('Mídias')), h('span', { class: 'grow' }), h('button', { class: 'stl-btn', type: 'button', id: 'stl-import', title: t('Importar mídias'), onclick: () => fileIn.click() }, icon('upload', 15)), fileIn),
      h('div', { class: 'stl-bin-l' }, list.length ? list.map((a) => h('div', { class: 'stl-asset', draggable: 'true', title: a.name + ' — ' + t('arraste para a timeline ou dê dois cliques'), dataset: { id: a.id },
        ondragstart: (e) => { e.dataTransfer.setData('text/asta-asset', a.id); }, onclick: () => markAsset(a), ondblclick: () => addAsset(a), oncontextmenu: (e) => assetMenu(e, a) },
      a.kind === 'audio' ? h('div', { class: 'th ico' }, icon('music', 18)) : h('div', { class: 'th', style: { backgroundImage: `url("${thumb(a)}")` } }), h('div', { class: 'nm' }, a.name), h('div', { class: 'du' }, a.kind === 'image' ? t('imagem') : fmtDur(a.dur || 0)))) : h('div', { class: 'muted small', style: { padding: '12px' } }, t('Sem mídias. Importe arquivos ou gere o episódio.'))));
  }

  function markAsset(a) {   // um clique só destaca a mídia (arrastar ou dois cliques coloca na timeline)
    bin.querySelectorAll('.stl-asset.cur').forEach((x) => x.classList.remove('cur'));
    const row = bin.querySelector(`.stl-asset[data-id="${a.id}"]`); if (row) row.classList.add('cur');
  }
  function assetMenu(e, a) {   // botão direito numa mídia: colocar no cursor (empurrando ou por cima) ou tirar do projeto
    e.preventDefault(); markAsset(a);
    const at = h('div', { style: { position: 'fixed', left: e.clientX + 'px', top: e.clientY + 'px', width: '1px', height: '1px' } }); document.body.appendChild(at);
    const item = (ic, label, fn) => h('div', { class: 'opt', role: 'menuitem', onclick: () => { pop.close(); fn(); } }, icon(ic, 15), h('div', null, label));
    const pop = popover(at, h('div', { class: 'toolmenu stl-menu', role: 'menu' },
      item('join', t('Inserir no cursor (empurra o que vem depois)'), () => addAsset(a, S.t, null, { ripple: true })),
      item('copy', t('Colocar no cursor (sem mexer nos outros clipes)'), () => addAsset(a, S.t)),
      item('trash', t('Tirar do projeto'), () => removeAsset(a))), () => at.remove());
  }
  async function removeAsset(a) {
    if (S.tl.clips.some((c) => c.asset === a.id)) return toast(t('Esta mídia está em uso na timeline. Apague os clipes dela antes.'), 'err');
    try { await api(`/api/studio/projects/${pid}/media/${a.id}`, { method: 'DELETE' }); delete S.assets[a.id]; if (o.onAssetRemoved) o.onAssetRemoved(a); paintBin(); toast(t('Mídia removida do projeto.'), 'ok'); } catch (err) { toast(err.message, 'err'); }
  }

  // ---------------------------------------------------------------- régua e trilhas
  const width = () => Math.max(scroller.clientWidth - HEAD_W, (total() + 12) * S.pps);
  function paintRuler() {
    const w = width();
    const steps = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600];
    const step = steps.find((s) => s * S.pps >= 70) || 3600;
    const kids = [];
    for (let x = 0; x <= w / S.pps; x += step) kids.push(h('div', { class: 'tick', style: { left: x * S.pps + 'px' } }, h('span', null, timecode(x).slice(0, step < 1 ? 8 : 5))));
    S.tl.markers.forEach((m, i) => kids.push(h('div', { class: 'mk', style: { left: m.t * S.pps + 'px' }, title: (m.label || t('Marcador')) + ' · ' + timecode(m.t), onpointerdown: (e) => { e.stopPropagation(); seek(m.t); }, ondblclick: (e) => { e.stopPropagation(); change(() => S.tl.markers.splice(i, 1), true); } }, icon('flag', 11))));
    fill(ruler, kids); ruler.style.width = w + 'px'; ruler.style.marginLeft = HEAD_W + 'px';
  }
  // forma de onda dos clipes de áudio (picos 0–1 por bloco, guardados em cache no servidor); cada clipe desenha só o trecho que usa
  const WAVE = {};
  function waveSvg(c, a, peaks) {
    const n = peaks.length, dur = a.dur || 1, i0 = Math.max(0, Math.floor((c.in || 0) / dur * n)), i1 = Math.min(n, Math.max(i0 + 1, Math.ceil(((c.in || 0) + c.dur * (c.speed || 1)) / dur * n)));
    const want = Math.max(8, Math.min(i1 - i0, Math.floor(c.dur * S.pps / 2))), step = (i1 - i0) / want, NS = 'http://www.w3.org/2000/svg';
    let top = '', bot = '';
    for (let i = 0; i < want; i++) { let m = 0; for (let j = Math.floor(i0 + i * step); j < Math.max(Math.floor(i0 + i * step) + 1, Math.floor(i0 + (i + 1) * step)) && j < n; j++) m = Math.max(m, peaks[j]); const y = Math.max(1, m * 46); top += `${i},${50 - y} `; bot = `${i},${50 + y} ` + bot; }
    const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('class', 'wf'); svg.setAttribute('viewBox', `0 0 ${want} 100`); svg.setAttribute('preserveAspectRatio', 'none');
    const poly = document.createElementNS(NS, 'polygon'); poly.setAttribute('points', top + bot); svg.appendChild(poly); return svg;
  }
  let waveBusy = false;
  async function loadWaves() {
    if (waveBusy) return;
    const need = [...new Set(S.tl.clips.filter((c) => { const tr = trackOf(c.track), a = assetOf(c); return tr && tr.kind === 'audio' && a && WAVE[a.id] === undefined && !(c.start > winR1 || end(c) < winR0); }).map((c) => c.asset))].slice(0, 4);
    if (!need.length) return;
    waveBusy = true; need.forEach((id) => { WAVE[id] = null; });
    try {
      await Promise.all(need.map(async (id) => { try { const r = await api(`/api/studio/projects/${pid}/wave/${id}?n=1200`); WAVE[id] = r.peaks && r.peaks.length ? r.peaks : false; } catch (e) { WAVE[id] = false; } }));
    } finally { waveBusy = false; }
    if (root.isConnected) { paintRows(); }
  }
  function clipEl(c, tr) {
    const a = assetOf(c), k = tr.kind;
    const style = { left: c.start * S.pps + 'px', width: Math.max(3, c.dur * S.pps) + 'px' };
    if (a && a.kind !== 'audio' && c.dur * S.pps > 24) { style.backgroundImage = `url("${thumb(a)}")`; }
    const pk = k === 'audio' && a && Array.isArray(WAVE[a.id]) ? waveSvg(c, a, WAVE[a.id]) : null;
    const el = h('div', { class: 'stl-clip k-' + k + (S.sel.has(c.id) ? ' sel' : '') + (c.mute ? ' muted' : '') + (tr.locked ? ' locked' : '') + (c.scene ? ' sc' : ''), dataset: { id: c.id }, style, title: (c.label || (a ? a.name : c.text)) + ' · ' + timecode(c.start) },
      pk, h('span', { class: 'hl', dataset: { h: 'l' } }), h('span', { class: 'hr', dataset: { h: 'r' } }),
      h('div', { class: 'lb' }, c.mute ? icon('mute', 11) : null, k === 'text' ? (c.text || t('Texto')) : k === 'fx' ? t((FILTERS.find((f) => f[0] === c.filter) || FILTERS[0])[1]) : (c.label || (a ? a.name : '')),
        (c.speed || 1) !== 1 ? h('span', { class: 'bd' }, (c.speed).toFixed(2).replace(/\.?0+$/, '') + '×') : null, c.filter && c.filter !== 'none' ? h('span', { class: 'bd' }, t(FILTERS.find((f) => f[0] === c.filter)[1])) : null));
    return el;
  }
  // Só os clipes perto da janela visível viram elementos (timelines com milhares de clipes ficavam pesadas); ao rolar além da margem, a lista é refeita.
  let winR0 = 0, winR1 = 0;
  const visRange = () => { const w = Math.max(scroller.clientWidth, 400) / S.pps, x0 = Math.max(0, scroller.scrollLeft / S.pps); return [Math.max(0, x0 - w), x0 + w * 2]; };
  function paintRows() {
    const [r0, r1] = visRange(); winR0 = r0; winR1 = r1;
    const near = (c) => S.sel.has(c.id) ? false : (c.start > r1 || end(c) < r0);
    fill(rows, S.tl.tracks.map((tr, idx) => h('div', { class: 'stl-row k-' + tr.kind + (tr.collapsed ? ' collapsed' : ''), dataset: { track: tr.id } },
      h('div', { class: 'stl-head', oncontextmenu: (e) => trackMenu(e, tr), title: t(KIND_LABEL[tr.kind]) + ' — ' + t('botão direito: renomear, subir, descer, apagar') }, h('button', { type: 'button', class: 'chev' + (tr.collapsed ? ' c' : ''), title: tr.collapsed ? t('Expandir a trilha') : t('Recolher a trilha'), dataset: { act: 'collapse' }, onclick: () => { tr.collapsed = !tr.collapsed; renderAll(); scheduleSave(); } }, icon('chev', 11)), h('span', { class: 'nm', ondblclick: () => renameTrack(tr) }, tr.name), h('span', { class: 'bt' },
        tr.kind === 'video' || tr.kind === 'audio' ? h('button', { type: 'button', class: tr.muted ? 'on' : '', title: tr.kind === 'audio' ? t('Silenciar a trilha') : t('Silenciar o áudio dos vídeos desta trilha'), dataset: { act: 'mute' }, onclick: () => { pushUndo(); tr.muted = !tr.muted; renderAll(); scheduleSave(); } }, icon('mute', 12)) : null,
        tr.kind !== 'audio' ? h('button', { type: 'button', class: tr.hidden ? 'on' : '', title: t('Ocultar a trilha'), dataset: { act: 'hide' }, onclick: () => { pushUndo(); tr.hidden = !tr.hidden; renderAll(); scheduleSave(); } }, icon('eye', 12)) : null,
        h('button', { type: 'button', class: tr.locked ? 'on' : '', title: t('Travar a trilha'), dataset: { act: 'lock' }, onclick: () => { pushUndo(); tr.locked = !tr.locked; renderAll(); scheduleSave(); } }, icon('lock', 12)))),
      h('div', { class: 'stl-lane' + (tr.hidden ? ' hid' : ''), style: { width: width() + 'px' } }, S.tl.clips.filter((c) => c.track === tr.id && !near(c)).map((c) => clipEl(c, tr))))));
    loadWaves();
  }
  let scrollRaf = 0;
  scroller.addEventListener('scroll', () => {   // rolou além do que está desenhado? refaz só as trilhas (no máximo uma vez por quadro)
    if (scrollRaf || drag) return;
    const w = Math.max(scroller.clientWidth, 400) / S.pps, x0 = scroller.scrollLeft / S.pps;
    if ((winR0 > 0 && x0 - winR0 < w * 0.25) || (winR1 < total() + 12 && winR1 - (x0 + w) < w * 0.25)) {   // a borda visível chegou perto do que está desenhado
      scrollRaf = requestAnimationFrame(() => { scrollRaf = 0; paintRows(); });
    }
  }, { passive: true });
  function paintPh() { ph.style.left = HEAD_W + S.t * S.pps + 'px'; ph.style.height = content.scrollHeight + 'px'; }
  function renderAll() { paintRuler(); paintRows(); paintPh(); paintInspector(); paintTime(); paintMixer(); syncZoom(); updatePreview(true); content.style.width = HEAD_W + width() + 'px'; T.refreshLive(); }
  // durante o arrasto só o que muda (régua, trilhas, cursor, tempo e monitor), no máximo uma vez por quadro: refazer o mixer e o inspetor a cada movimento do mouse deixava a edição pesada
  let renderRaf = 0;
  function renderDrag() {
    if (renderRaf) return;
    renderRaf = requestAnimationFrame(() => { renderRaf = 0; paintRuler(); paintRows(); paintPh(); paintTime(); updatePreview(true); content.style.width = HEAD_W + width() + 'px'; });
  }

  // ---------------------------------------------------------------- inspetor
  function paintInspector() {
    const cs = selClips();
    if (!cs.length) { fill(inspector, h('div', { class: 'stl-bin-h' }, h('b', null, t('Propriedades'))), h('div', { class: 'muted small', style: { padding: '12px' } }, t('Selecione um clipe na timeline. Atalhos: S corta, J junta, M silencia, Del exclui, C lâmina, Space reproduz.'))); return; }
    const c = cs[0], one = cs.length === 1, k = trackOf(c.track).kind, lk = cs.every((x) => !locked(x));
    const num = (label, key, step, min, max, conv) => h('label', { class: 'pf' }, h('span', null, label), h('input', { type: 'number', step, min, max, value: conv ? conv.to(c[key]) : c[key], disabled: !lk, dataset: { k: key },
      onchange: (e) => { let v = parseFloat(e.target.value); if (isNaN(v)) return; if (conv) v = conv.from(v); v = Math.min(max == null ? 1e9 : (conv ? conv.from(max) : max), Math.max(min == null ? -1e9 : (conv ? conv.from(min) : min), v)); setProp(key, r3(v)); } }));
    const f = [];
    f.push(h('div', { class: 'stl-bin-h' }, h('b', null, one ? (c.label || (assetOf(c) || {}).name || (k === 'text' ? t('Texto') : t('Clipe'))).slice(0, 26) : t('{n} clipes', { n: cs.length }))));
    if (one) f.push(h('div', { class: 'pg' }, num(t('Início (s)'), 'start', 0.1, 0), num(t('Duração (s)'), 'dur', 0.1, 0.1), k !== 'text' && isMedia(c) ? num(t('Ponto de corte (s)'), 'in', 0.1, 0) : null));
    if (cs.length > 1) f.push(h('div', { class: 'pg' }, h('div', { class: 'pf wide', style: { color: 'var(--text)' } }, t('{n} clipes, {d} no total', { n: cs.length, d: fmtDur(Math.max(...cs.map((x) => end(x))) - Math.min(...cs.map((x) => x.start))) })),
      h('label', { class: 'pf wide' }, h('span', null, t('Deslocar todos (s) — negativo = para a esquerda')), h('div', { class: 'row2' }, h('input', { type: 'number', step: 0.1, value: 1, id: 'stl-shift', style: { flex: '1' } }),
        h('button', { class: 'stl-btn', type: 'button', id: 'stl-shift-l', title: t('Deslocar para a esquerda') + ' (,)', onclick: () => nudge(-Math.abs(parseFloat(document.getElementById('stl-shift').value) || 0)) }, icon('stepback', 14)),
        h('button', { class: 'stl-btn', type: 'button', id: 'stl-shift-r', title: t('Deslocar para a direita') + ' (.)', onclick: () => nudge(Math.abs(parseFloat(document.getElementById('stl-shift').value) || 0)) }, icon('stepfwd', 14))))));
    if (k === 'video' || k === 'audio') f.push(h('div', { class: 'pg' },
      h('label', { class: 'pf' }, h('span', null, t('Velocidade')), h('select', { disabled: !lk, dataset: { k: 'speed' }, onchange: (e) => setSpeed(parseFloat(e.target.value)) }, SPEEDS.map((s) => h('option', { value: s, selected: Math.abs(s - (c.speed || 1)) < 0.001 }, s + '×')))),
      num(t('Volume (%)'), 'volume', 5, 0, 200, { to: (v) => Math.round(v * 100), from: (v) => v / 100 }),
      h('label', { class: 'pf ck' }, h('input', { type: 'checkbox', checked: !!c.mute, disabled: !lk, dataset: { k: 'mute' }, onchange: (e) => setProp('mute', e.target.checked) }), h('span', null, t('Silenciar este clipe')))));
    if (k !== 'text' && k !== 'fx') f.push(h('div', { class: 'pg' }, num(t('Fade de entrada (s)'), 'fade_in', 0.1, 0, 30), num(t('Fade de saída (s)'), 'fade_out', 0.1, 0, 30)));
    if (k === 'fx') f.push(h('div', { class: 'pg' },
      h('label', { class: 'pf wide' }, h('span', null, t('Efeito')), h('select', { disabled: !lk, dataset: { k: 'filter' }, onchange: (e) => setProp('filter', e.target.value) }, FILTERS.map(([v, l]) => h('option', { value: v, selected: v === (c.filter || 'none') }, t(l))))),
      num(t('Intensidade (%)'), 'opacity', 5, 0, 100, { to: (v) => Math.round(v * 100), from: (v) => v / 100 })));
    if (k === 'video' || k === 'image') f.push(h('div', { class: 'pg' },
      h('label', { class: 'pf' }, h('span', null, t('Filtro')), h('select', { disabled: !lk, dataset: { k: 'filter' }, onchange: (e) => setProp('filter', e.target.value) }, FILTERS.map(([v, l]) => h('option', { value: v, selected: v === (c.filter || 'none') }, t(l))))),
      h('label', { class: 'pf' }, h('span', null, t('Ajuste')), h('select', { disabled: !lk, dataset: { k: 'fit' }, onchange: (e) => setProp('fit', e.target.value) }, [['cover', t('Preencher')], ['contain', t('Caber')], ['stretch', t('Esticar')]].map(([v, l]) => h('option', { value: v, selected: v === c.fit }, l)))),
      num(t('Opacidade (%)'), 'opacity', 5, 0, 100, { to: (v) => Math.round(v * 100), from: (v) => v / 100 }), num(t('Escala (%)'), 'scale', 5, 10, 400, { to: (v) => Math.round(v * 100), from: (v) => v / 100 }),
      num(t('Posição X'), 'x', 0.05, -1, 1), num(t('Posição Y'), 'y', 0.05, -1, 1)));
    if (k === 'text') f.push(h('div', { class: 'pg' }, h('label', { class: 'pf wide' }, h('span', null, t('Texto')), h('textarea', { rows: 3, disabled: !lk, dataset: { k: 'text' }, onchange: (e) => setProp('text', e.target.value) }, c.text)),
      num(t('Tamanho'), 'size', 2, 8, 300), h('label', { class: 'pf' }, h('span', null, t('Posição')), h('select', { disabled: !lk, dataset: { k: 'pos' }, onchange: (e) => setProp('pos', e.target.value) }, [['top', t('Topo')], ['center', t('Centro')], ['bottom', t('Base')]].map(([v, l]) => h('option', { value: v, selected: v === c.pos }, l)))),
      h('label', { class: 'pf' }, h('span', null, t('Cor')), h('input', { type: 'color', value: c.color || '#ffffff', disabled: !lk, onchange: (e) => setProp('color', e.target.value) })),
      h('label', { class: 'pf' }, h('span', null, t('Fundo')), h('input', { type: 'color', value: c.bg || '#000000', disabled: !lk, onchange: (e) => setProp('bg', e.target.value) }))));
    fill(inspector, f);
  }

  // ---------------------------------------------------------------- preview (monitor)
  const pool = new Map();   // id do clipe → elemento de mídia
  const lastUse = new Map();
  const fade = (c, tt) => { if (!S.playing) return 1; let f = 1;   // parado: mostra o quadro inteiro (os fades só valem tocando e na exportação)
   if (c.fade_in > 0) f = Math.min(f, (tt - c.start) / c.fade_in); if (c.fade_out > 0) f = Math.min(f, (end(c) - tt) / c.fade_out); return Math.max(0, Math.min(1, f)); };
  function elFor(c, a) {
    let el = pool.get(c.id);
    if (!el || el.dataset.asset !== c.asset) {
      el = a.kind === 'image' ? h('img', { src: media(a), draggable: 'false' }) : h(a.kind === 'video' ? 'video' : 'audio', Object.assign({ src: media(a), preload: 'auto', playsinline: true }, a.kind === 'video' ? { poster: thumb(a) } : {}));
      el.dataset.asset = c.asset; pool.set(c.id, el);
      if (pool.size > 24) { const old = [...lastUse.entries()].sort((x, y) => x[1] - y[1]).find(([id]) => pool.has(id) && !activeIds.has(id)); if (old) { const e = pool.get(old[0]); if (e.pause) e.pause(); e.remove(); pool.delete(old[0]); lastUse.delete(old[0]); } }
    }
    lastUse.set(c.id, performance.now());
    return el;
  }
  let activeIds = new Set();
  function updatePreview(seeked) {
    const tt = S.t, act = new Set();
    const tracks = S.tl.tracks;
    const vtracks = tracks.map((tr, i) => [tr, i]).filter(([tr]) => (tr.kind === 'video' || tr.kind === 'image') && !tr.hidden);
    const shown = [];
    vtracks.forEach(([tr, i]) => {
      const cs = S.tl.clips.filter((c) => c.track === tr.id && c.start <= tt + 1e-6 && tt < end(c)).sort((a, b) => b.start - a.start);
      const c = cs[0], a = c && assetOf(c);
      if (c && a && a.kind !== 'audio') {
        act.add(c.id);
        const el = elFor(c, a);
        el.style.zIndex = String(100 - i); el.style.opacity = String((c.opacity ?? 1) * fade(c, tt));
        el.style.objectFit = c.fit === 'stretch' ? 'fill' : c.fit || 'cover';
        el.style.transform = `translate(${(c.x || 0) * 50}%, ${(c.y || 0) * 50}%) scale(${c.scale || 1})` + (c.filter === 'mirror' ? ' scaleX(-1)' : ''); el.style.filter = FILTER_CSS[c.filter || 'none'] || '';
        el.className = 'lyr';
        shown.push(el);
        if (el.tagName === 'VIDEO') { el.muted = !!(c.mute || tr.muted); el.volume = Math.max(0, Math.min(1, (c.volume ?? 1) * fade(c, tt) * plainGain(tr))); route(el, tr.id); sync(el, c, tt, seeked); }
      }
    });
    S.tl.clips.forEach((c) => {
      const tr = trackOf(c.track);
      if (!tr || tr.kind !== 'audio' || tr.muted || c.mute || c.start > tt + 1e-6 || tt >= end(c)) return;
      const a = assetOf(c); if (!a) return;
      act.add(c.id);
      const el = elFor(c, a); el.volume = Math.max(0, Math.min(1, (c.volume ?? 1) * fade(c, tt) * plainGain(tr))); route(el, tr.id); sync(el, c, tt, seeked);
    });
    // camadas de efeitos: o filtro vale para tudo que está na prévia enquanto o clipe de efeito está sob o cursor
    const fxs = S.tl.clips.filter((c) => { const tr = trackOf(c.track); return tr && tr.kind === 'fx' && !tr.hidden && c.filter && c.filter !== 'none' && c.start <= tt + 1e-6 && tt < end(c); }).map((c) => FILTER_CSS[c.filter] || '').filter(Boolean);
    const mirror = S.tl.clips.some((c) => { const tr = trackOf(c.track); return tr && tr.kind === 'fx' && !tr.hidden && c.filter === 'mirror' && c.start <= tt + 1e-6 && tt < end(c); });
    layers.style.filter = fxs.join(' '); layers.style.transform = mirror ? 'scaleX(-1)' : '';
    // texto
    const caps = S.tl.clips.filter((c) => { const tr = trackOf(c.track); return tr && tr.kind === 'text' && !tr.hidden && c.start <= tt + 1e-6 && tt < end(c); });
    fill(capEl, caps.map((c) => h('div', { class: 'cp pos-' + c.pos, style: { color: c.color, background: c.bg ? c.bg + 'a6' : 'transparent', fontSize: Math.max(10, c.size * (monitor.clientWidth || 640) / (S.aspect === '9:16' ? 720 : 1280)) + 'px' } }, c.text)));
    // elementos que saíram de cena
    pool.forEach((el, id) => { if (!act.has(id)) { if (el.pause && !el.paused) el.pause(); if (el.parentNode === layers) el.remove(); } });
    shown.forEach((el) => { if (el.parentNode !== layers) layers.appendChild(el); });
    activeIds = act;
  }
  function sync(el, c, tt, seeked) {
    if (!el.pause) return;
    const target = (c.in || 0) + (tt - c.start) * (c.speed || 1);
    el.playbackRate = Math.max(0.25, Math.min(4, c.speed || 1));
    if (seeked || Math.abs(el.currentTime - target) > 0.35) { try { el.currentTime = target; } catch (e) { /* ainda sem metadados */ } }
    if (S.playing) { if (el.paused) el.play().catch(() => {}); } else if (!el.paused) el.pause();
  }

  // ---------------------------------------------------------------- áudio: mixer (fader em dB, medidor, mudo por trilha e volume geral), como no Kdenlive
  const AUD = { ctx: null, tr: new Map(), master: null, mAn: null, src: new WeakMap() };
  const dbOf = (v) => (v > 0.0005 ? 20 * Math.log10(v) : -Infinity);
  const volOf = (db) => Math.min(2, Math.pow(10, db / 20));
  const posOfVol = (v) => (v <= 0.0005 ? 0 : Math.max(0, Math.min(1, (dbOf(v) + 60) / 66)));      // fader: -60 dB … +6 dB
  const volOfPos = (p) => (p <= 0.004 ? 0 : volOf(-60 + p * 66));
  const fmtDb = (v) => (v <= 0.0005 ? '−∞' : (dbOf(v) >= 0 ? '+' : '') + dbOf(v).toFixed(1).replace('-', '−'));
  const masterVol = () => (S.tl.master == null ? 1 : S.tl.master);
  const plainGain = (tr) => (AUD.ctx ? 1 : (tr.volume == null ? 1 : tr.volume) * masterVol());   // com WebAudio, o ganho vai pelos nós; sem ele, multiplica no próprio elemento
  function ensureAudio() {
    if (AUD.ctx) { if (AUD.ctx.state === 'suspended') AUD.ctx.resume().catch(() => {}); return; }
    const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    try {
      AUD.ctx = new AC(); AUD.master = AUD.ctx.createGain(); AUD.mAn = AUD.ctx.createAnalyser(); AUD.mAn.fftSize = 512;
      AUD.master.connect(AUD.mAn); AUD.mAn.connect(AUD.ctx.destination); applyGains();
    } catch (e) { AUD.ctx = null; }
  }
  function trackNode(id) {
    let n = AUD.tr.get(id); if (n) return n;
    const g = AUD.ctx.createGain(), an = AUD.ctx.createAnalyser(); an.fftSize = 512; g.connect(an); an.connect(AUD.master);
    n = { g, an }; AUD.tr.set(id, n); const tr = trackOf(id); g.gain.value = tr && tr.volume != null ? tr.volume : 1; return n;
  }
  function route(el, trackId) {
    if (!AUD.ctx || !el.pause) return;
    let r = AUD.src.get(el);
    try {
      if (!r) { r = { node: AUD.ctx.createMediaElementSource(el), track: '' }; AUD.src.set(el, r); }
      if (r.track !== trackId) { r.node.disconnect(); r.node.connect(trackNode(trackId).g); r.track = trackId; }
    } catch (e) { /* já roteado por outro contexto: toca direto */ }
  }
  function applyGains() { if (!AUD.ctx) return; AUD.master.gain.value = masterVol(); S.tl.tracks.forEach((tr) => { if (AUD.tr.has(tr.id)) AUD.tr.get(tr.id).g.gain.value = tr.volume == null ? 1 : tr.volume; }); }
  const peakOf = (an) => { const b = new Float32Array(an.fftSize); an.getFloatTimeDomainData(b); let m = 0; for (let i = 0; i < b.length; i++) m = Math.max(m, Math.abs(b[i])); return m; };
  let meterRaf = 0;
  const meters = new Map();   // id da trilha (ou 'master') → { el, level }
  function meterLoop() {
    meterRaf = 0;
    if (!root.isConnected || !LAY.mix) return;
    meters.forEach((m, id) => {
      const an = id === 'master' ? AUD.mAn : (AUD.tr.get(id) || {}).an;
      const pk = an && S.playing ? peakOf(an) : 0;
      m.level = Math.max(pk > 0 ? Math.max(0, (dbOf(pk) + 60) / 66) : 0, m.level - 0.025);   // sobe na hora, cai devagar
      m.el.style.height = Math.round(m.level * 100) + '%'; m.el.parentNode.classList.toggle('hot', m.level > 0.93);
    });
    if (S.playing || [...meters.values()].some((m) => m.level > 0.001)) meterRaf = requestAnimationFrame(meterLoop);
  }
  const kickMeters = () => { if (!meterRaf && LAY.mix) meterRaf = requestAnimationFrame(meterLoop); };
  function strip(id, label, get, set, mutedGet, onMute, kind) {
    const slider = h('input', { type: 'range', class: 'fd nodrag', min: 0, max: 1000, step: 1, value: Math.round(posOfVol(get()) * 1000), orient: 'vertical', 'aria-label': t('Volume') + ' ' + label, dataset: { fader: id } });
    const db = h('input', { type: 'text', class: 'db nodrag', value: fmtDb(get()), inputmode: 'decimal', 'aria-label': 'dB ' + label, dataset: { db: id } });
    const bar = h('i'), box = h('div', { class: 'mt' }, bar);
    meters.set(id, { el: bar, level: 0 });
    slider.addEventListener('pointerdown', () => pushUndo());
    slider.addEventListener('input', () => { set(volOfPos(slider.value / 1000)); db.value = fmtDb(get()); applyGains(); S.saved = false; paintStatus(); });
    slider.addEventListener('change', () => scheduleSave());
    slider.addEventListener('dblclick', () => { pushUndo(); set(1); slider.value = Math.round(posOfVol(1) * 1000); db.value = fmtDb(1); applyGains(); scheduleSave(); });   // dois cliques: 0 dB
    db.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Enter') db.blur(); });
    db.addEventListener('change', () => { const x = parseFloat(String(db.value).replace('−', '-').replace(',', '.')); pushUndo(); set(Number.isNaN(x) ? get() : (/^[-−]\s*(inf|∞)/i.test(db.value) ? 0 : volOf(Math.max(-60, Math.min(6, x))))); slider.value = Math.round(posOfVol(get()) * 1000); db.value = fmtDb(get()); applyGains(); scheduleSave(); });
    const mute = onMute ? h('button', { type: 'button', class: 'mu' + (mutedGet() ? ' on' : ''), title: t('Silenciar a trilha'), dataset: { mute: id }, onclick: (e) => { onMute(); e.currentTarget.classList.toggle('on', mutedGet()); } }, icon('mute', 12)) : h('span');
    const scale = h('div', { class: 'sc' }, ['+6', '0', '−12', '−24', '−36', '−60'].map((x) => h('span', null, x)));
    return h('div', { class: 'stl-strip k-' + (kind || 'master') + (id === 'master' ? ' master' : ''), dataset: { strip: id } }, h('div', { class: 'nm' }, label), h('div', { class: 'bt' }, mute),
      h('div', { class: 'fw' }, scale, box, slider), db, h('div', { class: 'dbl' }, 'dB'));
  }
  function paintMixer() {
    meters.clear();
    const tracks = S.tl.tracks.filter((x) => x.kind !== 'text');
    fill(mixer, h('div', { class: 'stl-mix-h' }, h('b', null, t('Mixer de áudio'))),
      h('div', { class: 'stl-strips' }, tracks.map((tr) => strip(tr.id, tr.name, () => (tr.volume == null ? 1 : tr.volume), (v) => { tr.volume = v; }, () => tr.muted, () => { pushUndo(); tr.muted = !tr.muted; renderAllKeepMixer(); scheduleSave(); }, tr.kind)),
        strip('master', t('Principal'), masterVol, (v) => { S.tl.master = v; }, null, null)));
    kickMeters();
  }
  const renderAllKeepMixer = () => { paintRows(); updatePreview(true); };

  // ---------------------------------------------------------------- zoom (barra de baixo)
  const ppsToPos = (p) => Math.round((Math.log(p / 2) / Math.log(200)) * 100);
  const posToPps = (v) => 2 * Math.pow(200, v / 100);
  function syncZoom() { if (document.activeElement !== zoomRange) zoomRange.value = String(ppsToPos(S.pps)); }
  zoomRange.addEventListener('input', () => zoom(posToPps(Number(zoomRange.value)) / S.pps));

  function paintTime() { posEl.textContent = timecode(S.t) + ' / ' + timecode(total()); tcEl.textContent = timecode(S.t) + ' / ' + timecode(total()); playBtn.replaceChildren(icon(S.playing ? 'pause' : 'play', 15)); }
  function seek(tt) { S.t = Math.max(0, Math.min(tt, 6 * 3600)); /* o cursor pode ir além do fim (para posicionar um clipe novo) */ if (S.playing) { S.w0 = performance.now(); S.t0 = S.t; } paintPh(); paintTime(); updatePreview(true); }
  function togglePlay() {
    if (S.playing) { S.playing = false; cancelAnimationFrame(S.raf); paintTime(); updatePreview(false); return; }
    if (S.t >= total() - 0.05) S.t = 0;
    ensureAudio();
    S.playing = true; S.w0 = performance.now(); S.t0 = S.t; paintTime(); updatePreview(true);
    const tick = () => {
      if (!S.playing) return;
      S.t = S.t0 + (performance.now() - S.w0) / 1000;
      if (S.t >= total()) { S.t = total(); S.playing = false; paintPh(); paintTime(); updatePreview(false); return; }
      paintPh(); tcEl.textContent = posEl.textContent = timecode(S.t) + ' / ' + timecode(total()); updatePreview(false);
      const x = HEAD_W + S.t * S.pps; if (x > scroller.scrollLeft + scroller.clientWidth - 40 || x < scroller.scrollLeft + HEAD_W) scroller.scrollLeft = Math.max(0, x - HEAD_W - 60);
      S.raf = requestAnimationFrame(tick);
    };
    S.raf = requestAnimationFrame(tick);
  }
  function zoom(f) { const mid = (scroller.scrollLeft + scroller.clientWidth / 2 - HEAD_W) / S.pps; S.pps = Math.max(2, Math.min(400, S.pps * f)); renderAll(); scroller.scrollLeft = Math.max(0, mid * S.pps - scroller.clientWidth / 2 + HEAD_W); }
  function toggleFull() { const on = root.classList.toggle('full'); host.classList.toggle('st-tlfull', on); document.body.classList.toggle('stl-noscroll', on); applyLay(); renderAll(); }
  function fit() { S.pps = Math.max(2, Math.min(400, (scroller.clientWidth - HEAD_W - 40) / Math.max(5, total()))); renderAll(); scroller.scrollLeft = 0; }

  // ---------------------------------------------------------------- mouse: selecionar, mover, aparar, lâmina, régua, soltar mídia
  const timeAt = (clientX) => (clientX - content.getBoundingClientRect().left - HEAD_W) / S.pps;
  function snapTime(val, ignore, edgeLen) {
    if (!S.snap) return val;
    const pts = [0, S.t, ...S.tl.markers.map((m) => m.t)];
    S.tl.clips.forEach((c) => { if (!ignore.has(c.id)) { pts.push(c.start, end(c)); } });
    const th = 8 / S.pps; let best = null;
    for (const p of pts) {
      for (const [v, off] of edgeLen == null ? [[val, 0]] : [[val, 0], [val + edgeLen, edgeLen]]) { const d = Math.abs(v - p); if (d <= th && (!best || d < best.d)) best = { d, adj: p - off }; }
    }
    return best ? best.adj : val;
  }
  let drag = null;
  content.addEventListener('pointerdown', (e) => {
    const ae = document.activeElement; if (ae && ae !== document.body && /^(INPUT|SELECT|TEXTAREA)$/.test(ae.tagName) && root.contains(ae)) ae.blur();   // o foco sai do campo: os atalhos voltam
    if (e.button !== 0 && e.button !== 2) return;
    const rl = e.target.closest('.stl-ruler');
    if (rl) { drag = { type: 'scrub' }; seek(timeAt(e.clientX)); content.setPointerCapture(e.pointerId); return; }
    const hd = e.target.closest('.stl-head'); if (hd) return;
    const ce = e.target.closest('.stl-clip');
    if (!ce) {
      if (e.target.closest('.stl-lane')) { if (!e.shiftKey) { S.sel.clear(); renderAll(); } const r = content.getBoundingClientRect(); drag = { type: 'marquee', x0: e.clientX - r.left, y0: e.clientY - r.top, base: new Set(S.sel) }; content.setPointerCapture(e.pointerId); }
      return;
    }
    const c = clipById(ce.dataset.id); if (!c) return;
    if (e.button === 2) { if (!S.sel.has(c.id)) { S.sel = new Set([c.id]); renderAll(); } return; }
    if (S.tool === 'razor') { splitAt(timeAt(e.clientX), [c.id], true); return; }
    if (e.shiftKey) { if (S.sel.has(c.id)) S.sel.delete(c.id); else S.sel.add(c.id); renderAll(); return; }
    if (!S.sel.has(c.id)) { S.sel = new Set([c.id]); renderAll(); }
    if (locked(c)) return;
    const handle = e.target.dataset && e.target.dataset.h;
    const ids = new Set(S.sel);
    drag = { type: handle ? 'trim-' + handle : 'move', id: c.id, x0: e.clientX, y0: e.clientY, ids, orig: selClips().filter((x) => !locked(x)).map((x) => ({ id: x.id, start: x.start, dur: x.dur, in: x.in, track: x.track })), pushed: false,   // clipes de trilhas travadas não acompanham o arrasto
      after: S.ripple ? S.tl.clips.filter((x) => !ids.has(x.id) && x.start >= end(c) - 1e-6 && !locked(x)).map((x) => ({ id: x.id, start: x.start })) : [] };
    content.setPointerCapture(e.pointerId);
  });
  content.addEventListener('pointermove', (e) => {
    if (!drag) return;
    if (drag.type === 'scrub') { seek(timeAt(e.clientX)); return; }
    if (drag.type === 'marquee') {
      const r = content.getBoundingClientRect(), x1 = e.clientX - r.left, y1 = e.clientY - r.top;
      const l = Math.min(drag.x0, x1), tp = Math.min(drag.y0, y1), w = Math.abs(x1 - drag.x0), hh = Math.abs(y1 - drag.y0);
      Object.assign(marquee.style, { left: l + 'px', top: tp + 'px', width: w + 'px', height: hh + 'px' }); marquee.classList.remove('hidden');
      const sel = new Set(drag.base);
      content.querySelectorAll('.stl-clip').forEach((el) => { const b = el.getBoundingClientRect(); const cl = b.left - r.left, ct = b.top - r.top; if (cl < l + w && cl + b.width > l && ct < tp + hh && ct + b.height > tp) sel.add(el.dataset.id); });
      S.sel = sel; content.querySelectorAll('.stl-clip').forEach((el) => el.classList.toggle('sel', S.sel.has(el.dataset.id))); return;
    }
    const dt = (e.clientX - drag.x0) / S.pps;
    if (!drag.pushed && Math.abs(e.clientX - drag.x0) + Math.abs(e.clientY - drag.y0) < 3) return;
    if (!drag.pushed) { pushUndo(); drag.pushed = true; }
    const prim = drag.orig.find((x) => x.id === drag.id), c = clipById(drag.id);
    if (drag.type === 'move') {
      let d = dt;
      const ns = snapTime(Math.max(0, prim.start + d), drag.ids, prim.dur);
      d = ns - prim.start;
      const minStart = Math.min(...drag.orig.map((x) => x.start));
      if (minStart + d < 0) d = -minStart;
      drag.orig.forEach((x) => { const cc = clipById(x.id); cc.start = r3(x.start + d); });
      if (drag.orig.length === 1) {   // trocar de trilha do mesmo tipo
        const rowsEl = [...rows.children]; const y = e.clientY;
        const hit = rowsEl.find((r) => { const b = r.getBoundingClientRect(); return y >= b.top && y < b.bottom; });
        if (hit) { const tr = trackOf(hit.dataset.track); if (tr && !tr.locked && tr.kind === trackOf(prim.track).kind) c.track = tr.id; }
      }
    } else if (drag.type === 'trim-l') {
      let ns = snapTime(Math.max(0, prim.start + dt), drag.ids);
      let d = ns - prim.start;
      const spd = c.speed || 1;
      if (isMedia(c)) d = Math.max(d, -prim.in / spd);
      d = Math.min(d, prim.dur - 0.1); if (prim.start + d < 0) d = -prim.start;
      c.start = r3(prim.start + d); c.dur = r3(prim.dur - d); if (isMedia(c)) c.in = r3(prim.in + d * spd);
    } else if (drag.type === 'trim-r') {
      const ne = snapTime(prim.start + prim.dur + dt, drag.ids);
      c.dur = r3(Math.min(Math.max(0.1, ne - prim.start), maxDur(Object.assign({}, c, { in: prim.in }))));
      drag.after.forEach((x) => { clipById(x.id).start = r3(x.start + (c.dur - prim.dur)); });   // ripple: o que vem depois acompanha
    }
    renderDrag();
  });
  const endDrag = () => {
    if (!drag) return;
    const d = drag; drag = null; marquee.classList.add('hidden');
    if (renderRaf) { cancelAnimationFrame(renderRaf); renderRaf = 0; }
    if (d.pushed) {
      S.tl.clips.forEach((c) => { c.start = r3(Math.max(0, c.start)); c.dur = r3(Math.max(0.1, c.dur)); c.in = r3(Math.max(0, c.in)); });   // mesma limpeza das outras edições
      scheduleSave(); renderAll();
    } else if (d.type === 'marquee') renderAll();
  };
  content.addEventListener('pointerup', endDrag); content.addEventListener('pointercancel', endDrag);
  content.addEventListener('contextmenu', (e) => {
    const ce = e.target.closest('.stl-clip'); if (!ce) return; e.preventDefault();
    const c = clipById(ce.dataset.id); if (!S.sel.has(c.id)) { S.sel = new Set([c.id]); renderAll(); }
    const at = h('div', { style: { position: 'fixed', left: e.clientX + 'px', top: e.clientY + 'px', width: '1px', height: '1px' } }); document.body.appendChild(at);
    const item = (ic, label, fn) => h('div', { class: 'opt', role: 'menuitem', onclick: () => { pop.close(); fn(); } }, icon(ic, 15), h('div', null, label));
    const tt = timeAt(e.clientX);
    const pop = popover(at, h('div', { class: 'toolmenu stl-menu', role: 'menu' }, item('scissors', t('Cortar aqui'), () => splitAt(tt, [c.id], true)), item('join', t('Juntar selecionados'), joinSel), item('mute', t('Silenciar / reativar o som'), toggleMute),
      item('copy', t('Duplicar'), duplicate), item('ripple', t('Excluir e fechar o espaço'), () => del(true)), item('trash', t('Excluir'), () => del(false))), () => at.remove());
  });
  scroller.addEventListener('wheel', (e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15); } }, { passive: false });
  // soltar mídia do bin numa trilha
  content.addEventListener('dragover', (e) => { if (e.dataTransfer.types.includes('text/asta-asset')) e.preventDefault(); });
  content.addEventListener('drop', (e) => {
    const id = e.dataTransfer.getData('text/asta-asset'); if (!id || !S.assets[id]) return; e.preventDefault();
    const lane = e.target.closest('.stl-row'); const a = S.assets[id];
    let trackId = lane && lane.dataset.track; const tr = trackId && trackOf(trackId);
    if (tr && !accepts(tr, a)) trackId = '';   // só cai na camada do mesmo tipo (e destravada); senão vai para uma camada livre ou nova do tipo certo
    addAsset(a, Math.max(0, snapTime(timeAt(e.clientX), new Set())), trackId);
  });

  // ---------------------------------------------------------------- teclado
  const onKey = (e) => {
    if (!root.isConnected) { document.removeEventListener('keydown', onKey); return; }
    const tg = e.target; if (tg && (tg.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(tg.tagName))) return;
    if (e.altKey) return;
    const k = e.key, ctrl = e.ctrlKey || e.metaKey;
    const done = () => { e.preventDefault(); e.stopPropagation(); };
    if (e.repeat && !/^Arrow/.test(k) && !',.<>+-='.includes(k)) { if (!ctrl && k !== 'Escape') e.preventDefault(); return; }   // segurar a tecla não corta/exclui em rajada
    if (ctrl && k.toLowerCase() === 'z') { done(); if (e.shiftKey) redo(); else undo(); }
    else if (ctrl && k.toLowerCase() === 'y') { done(); redo(); }
    else if (ctrl && k.toLowerCase() === 'd') { done(); duplicate(); }
    else if (ctrl && k.toLowerCase() === 'c') { done(); copySel(false); }
    else if (ctrl && k.toLowerCase() === 'x') { done(); copySel(true); }
    else if (ctrl && k.toLowerCase() === 'v') { done(); paste(); }
    else if (ctrl && k.toLowerCase() === 'a') { done(); selectAll(); }
    else if (ctrl) return;
    else if (e.shiftKey && (k === 'A' || k === 'a')) { done(); selectAll(); }   // Shift+A: seleciona a timeline inteira
    else if (k === ',' || k === '<') { done(); nudge(-(e.shiftKey ? 1 : 1 / FPS)); }   // desloca a seleção (Shift: 1 s)
    else if (k === '.' || k === '>') { done(); nudge(e.shiftKey ? 1 : 1 / FPS); }
    else if (k === ' ') { done(); togglePlay(); }
    else if (k === 'ArrowLeft') { done(); seek(S.t - (e.shiftKey ? 1 : 1 / FPS)); }
    else if (k === 'ArrowRight') { done(); seek(S.t + (e.shiftKey ? 1 : 1 / FPS)); }
    else if (k === 'Home') { done(); seek(0); } else if (k === 'End') { done(); seek(total()); }
    else if (k === 'Delete' || k === 'Backspace') { done(); del(e.shiftKey); }
    else if (k === 's' || k === 'S') { done(); splitAt(S.t, [...S.sel]); }
    else if (k === 'j' || k === 'J') { done(); joinSel(); }
    else if (k === 'm' || k === 'M') { done(); toggleMute(); }
    else if (k === 'c' || k === 'C') { done(); S.tool = S.tool === 'razor' ? 'select' : 'razor'; buildBar(); }
    else if (k === 'v' || k === 'V') { done(); S.tool = 'select'; buildBar(); }
    else if (k === 't' || k === 'T') { done(); addText(); }
    else if (k === 'k' || k === 'K') { done(); addMarker(); }
    else if (k === '[') { done(); trimTo('start'); } else if (k === ']') { done(); trimTo('end'); }
    else if (k === '+' || k === '=') { done(); zoom(1.35); } else if (k === '-') { done(); zoom(1 / 1.35); }
    else if (k === 'f' || k === 'F') { done(); toggleFull(); }
    else if (k === 'Escape') { if (root.classList.contains('full')) toggleFull(); else { S.tool = 'select'; S.sel.clear(); buildBar(); renderAll(); } }
  };
  document.addEventListener('keydown', onKey);
  const onUnload = () => {   // fechar a página no meio de um salvamento: o pedido sai com keepalive e o navegador o termina
    if (S.saved) return;
    try { fetch(`/api/studio/projects/${pid}/episodes/${eid}/timeline`, { method: 'PUT', keepalive: true, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ timeline: S.tl }) }); } catch (e) { /* ok */ }
  };
  window.addEventListener('beforeunload', onUnload); window.addEventListener('pagehide', onUnload);

  buildBar(); paintBin(); renderAll(); paintStatus();
  new ResizeObserver(() => { if (root.isConnected) { paintRuler(); paintRows(); paintPh(); } }).observe(scroller);
  return {
    save, S, destroy() { T.destroy(); if (!S.saved) save(); window.removeEventListener('beforeunload', onUnload); window.removeEventListener('pagehide', onUnload); document.body.classList.remove('stl-noscroll'); S.playing = false; cancelAnimationFrame(S.raf); cancelAnimationFrame(meterRaf); cancelAnimationFrame(renderRaf); if (AUD.ctx) { try { AUD.ctx.close(); } catch (e) { /* ok */ } } document.removeEventListener('keydown', onKey); pool.forEach((el) => { if (el.pause) el.pause(); }); },
    refreshAssets(list) { setAssets(list); paintBin(); renderAll(); },
    api: { copySel, paste, toggleFull, splitAt, joinSel, toggleMute, del, duplicate, addText, addMarker, undo, redo, seek, togglePlay, zoom, fit, total, selectAll, nudge, addLayer, addFx, addCaptions, setTool },
  };
}
