import { api, events } from '../api.js';
import { t } from '../i18n.js';
import { fill, h, icon, toast } from '../ui.js';

// «Tools» da timeline do Studio: as janelas do editor (mídias, monitor, propriedades, mixer) e as ferramentas extras (efeitos, SFX, captura de tela, legendas, transcrição, navegador de mídia).
// Cada uma pode ser ligada/desligada em «Tools»; as ligadas ficam nos painéis laterais (abas), no centro (monitor) ou embaixo (mixer).
export const TOOLS = [
  { id: 'media', label: 'Mídias', hint: 'Os arquivos do projeto', icon: 'folder', dock: 'left' },
  { id: 'monitor', label: 'Monitor', hint: 'A prévia do vídeo', icon: 'video', dock: 'center' },
  { id: 'props', label: 'Propriedades', hint: 'Ajustes do clipe selecionado', icon: 'panel', dock: 'right' },
  { id: 'mixer', label: 'Mixer de áudio', hint: 'Volume de cada trilha e principal', icon: 'audio', dock: 'bottom' },
  { id: 'effects', label: 'Efeitos', hint: 'Filtros, fades, zoom e camadas de efeito', icon: 'wand', dock: 'right' },
  { id: 'sfx', label: 'Efeitos sonoros', hint: 'Whoosh, impacto, riser… gerados no ASTA', icon: 'bolt', dock: 'left' },
  { id: 'capture', label: 'Captura de tela', hint: 'Grava a tela e põe na timeline', icon: 'computer', dock: 'left' },
  { id: 'captions', label: 'Legendas', hint: 'Criar, importar e exportar SRT/VTT', icon: 'type', dock: 'right' },
  { id: 'transcribe', label: 'Transcrição', hint: 'Áudio/vídeo → texto → legendas', icon: 'doc', dock: 'right' },
  { id: 'browser', label: 'Navegador de mídia', hint: 'Arquivos dos Canvas e de outros projetos', icon: 'search', dock: 'left' },
];
export const DEFAULT_ON = ['media', 'monitor', 'props', 'mixer'];
export const FILTERS = [['none', 'Sem filtro'], ['bw', 'Preto e branco'], ['warm', 'Quente'], ['cool', 'Frio'], ['vivid', 'Vivo'], ['vhs', 'VHS'], ['cinematic', 'Cinema'], ['phonk', 'Phonk'],
  ['sepia', 'Sépia'], ['negative', 'Negativo'], ['blur', 'Desfoque'], ['sharpen', 'Nitidez'], ['glow', 'Brilho suave'], ['grain', 'Granulado'], ['vignette', 'Vinheta'], ['mirror', 'Espelhar'], ['noir', 'Noir'], ['teal_orange', 'Azul e laranja']];
export const FILTER_CSS = { none: '', bw: 'grayscale(1)', warm: 'sepia(.35) saturate(1.2)', cool: 'hue-rotate(15deg) saturate(1.1)', vivid: 'saturate(1.5) contrast(1.1)', vhs: 'saturate(1.3) contrast(.95) blur(.4px)',
  cinematic: 'contrast(1.12) saturate(.9)', phonk: 'grayscale(.5) contrast(1.3) brightness(.95)', sepia: 'sepia(.9)', negative: 'invert(1)', blur: 'blur(3px)', sharpen: 'contrast(1.25) saturate(1.1)',
  glow: 'brightness(1.08) saturate(1.2) blur(.6px)', grain: 'contrast(1.1)', vignette: 'brightness(.92) contrast(1.08)', mirror: '', noir: 'grayscale(1) contrast(1.4) brightness(.95)', teal_orange: 'hue-rotate(-12deg) saturate(1.35) contrast(1.08)' };

const head = (title, ...extra) => h('div', { class: 'stl-bin-h' }, h('b', null, title), h('span', { class: 'grow' }), ...extra);
const label = (txt, ...kids) => h('label', { class: 'pf' }, h('span', null, txt), ...kids);
const num = (value, o = {}) => h('input', Object.assign({ type: 'number', value }, o));
const dl = (blob, name) => { const a = h('a', { href: URL.createObjectURL(blob), download: name }); document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); };
const fmt = (s) => { s = Math.max(0, s); return String(Math.floor(s / 60)).padStart(2, '0') + ':' + (s % 60).toFixed(1).padStart(4, '0'); };

// c: o contexto que a timeline entrega (estado, ações e utilidades) — veja `mountTimeline`
export function buildTools(c) {
  const panels = {}, painters = {};
  const reg = (id, title, build) => { const el = h('div', { class: 'stl-panel', id: 'stl-tool-' + id, dataset: { tool: id } }); panels[id] = el; build(el, title); painters[id] = () => { if (el._paint) el._paint(); }; };

  // ------------------------------------------------------------ efeitos
  const fx = { cur: 'vivid', dur: 3 };
  reg('effects', t('Efeitos'), (el, title) => {
    const sw = FILTERS.filter(([k]) => k !== 'none').map(([k, name]) => h('button', { type: 'button', class: 'fxsw' + (fx.cur === k ? ' on' : ''), dataset: { fx: k }, title: t(name),
      onclick: () => { fx.cur = k; paint(); } }, h('i', { style: { filter: FILTER_CSS[k] || '', transform: k === 'mirror' ? 'scaleX(-1)' : '' } }), h('span', null, t(name))));
    const paint = () => {
      const sel = c.selClips();
      fill(el, head(title),
        h('div', { class: 'pg1' }, h('div', { class: 'sub' }, t('Filtro')), h('div', { class: 'fxgrid' }, sw.map((b) => { b.classList.toggle('on', b.dataset.fx === fx.cur); return b; })),
          h('div', { class: 'row2' },
            h('button', { class: 'btn sm primary', type: 'button', id: 'fx-apply', disabled: !sel.length, title: t('Aplica o filtro aos clipes selecionados'), onclick: () => { c.setProp('filter', fx.cur); } }, icon('wand', 13), t('Aos clipes selecionados')),
            h('button', { class: 'btn sm', type: 'button', id: 'fx-clear', disabled: !sel.length, onclick: () => c.setProp('filter', 'none') }, t('Tirar filtro'))),
          h('div', { class: 'sub' }, t('Camada de efeitos')),
          h('p', { class: 'muted small', style: { margin: '0 0 6px' } }, t('Uma camada própria: o filtro vale para tudo que está abaixo dela, só enquanto o trecho dura.')),
          h('div', { class: 'row2' }, label(t('Duração (s)'), num(fx.dur, { min: 0.2, step: 0.5, id: 'fx-dur', oninput: (e) => { fx.dur = parseFloat(e.target.value) || 3; } })),
            h('button', { class: 'btn sm', type: 'button', id: 'fx-layer', onclick: () => c.addFx(fx.cur, Math.max(0.2, fx.dur)) }, icon('layers', 13), t('Pôr no cursor'))),
          h('div', { class: 'sub' }, t('Fades')),
          h('div', { class: 'row2 wrap' }, [['fade_in', 0.5, 'Entrada ½ s'], ['fade_in', 1, 'Entrada 1 s'], ['fade_out', 0.5, 'Saída ½ s'], ['fade_out', 1, 'Saída 1 s'], ['both', 1, 'Entrada e saída']].map(([k, v, nm]) =>
            h('button', { class: 'btn sm', type: 'button', disabled: !sel.length, onclick: () => { if (k === 'both') c.setProps({ fade_in: v, fade_out: v }); else c.setProp(k, v); } }, t(nm))),
          h('button', { class: 'btn sm ghost', type: 'button', disabled: !sel.length, onclick: () => c.setProps({ fade_in: 0, fade_out: 0 }) }, t('Sem fades'))),
          h('div', { class: 'sub' }, t('Zoom do clipe')),
          h('div', { class: 'row2 wrap' }, [1, 1.15, 1.3, 1.5, 2].map((v) => h('button', { class: 'btn sm', type: 'button', disabled: !sel.length, onclick: () => c.setProp('scale', v) }, Math.round(v * 100) + '%')))));
    };
    paint(); el._paint = paint;
  });

  // ------------------------------------------------------------ efeitos sonoros
  const sfx = { list: null, dur: 0, place: true, cache: new Map(), busy: '' };
  reg('sfx', t('Efeitos sonoros'), (el, title) => {
    const paint = () => {
      const body = !sfx.list ? h('div', { class: 'muted small', style: { padding: '12px' } }, t('Carregando…'))
        : h('div', { class: 'sfxl' }, sfx.list.map((e) => h('div', { class: 'sfxr' }, h('span', { class: 'nm' }, t(e.label)), h('span', { class: 'muted small' }, e.dur + ' s'),
          h('button', { class: 'stl-btn', type: 'button', title: t('Ouvir'), disabled: !!sfx.busy, dataset: { sfx: e.id, act: 'play' }, onclick: () => make(e, false) }, icon('play', 13)),
          h('button', { class: 'stl-btn', type: 'button', title: t('Adicionar à timeline'), disabled: !!sfx.busy, dataset: { sfx: e.id, act: 'add' }, onclick: () => make(e, true) }, icon('plus', 13)))));
      fill(el, head(title), h('div', { class: 'pg1' }, h('div', { class: 'row2' }, label(t('Duração (s; 0 = padrão do efeito)'), num(sfx.dur, { min: 0, max: 30, step: 0.5, id: 'sfx-dur', oninput: (e) => { sfx.dur = parseFloat(e.target.value) || 0; } })),
        h('label', { class: 'pf ck' }, h('input', { type: 'checkbox', checked: sfx.place, onchange: (e) => { sfx.place = e.target.checked; } }), h('span', null, t('Pôr no cursor ao adicionar')))),
        h('p', { class: 'muted small', style: { margin: '0 0 6px' } }, t('Gerados dentro do ASTA, sem internet. O mesmo efeito com a mesma duração reaproveita o arquivo.'))), body);
    };
    async function make(e, add) {
      const key = e.id + '|' + sfx.dur;
      sfx.busy = e.id; paint();
      try {
        let rec = sfx.cache.get(key);
        if (!rec || !c.S.assets[rec.id]) { rec = await api(`/api/studio/projects/${c.pid}/sfx`, { method: 'POST', body: { kind: e.id, duration: sfx.dur, seed: 1 } }); sfx.cache.set(key, rec); c.addAssetRec(rec); }
        if (add) { if (sfx.place) c.addAsset(rec, c.S.t); else toast(t('Efeito adicionado às mídias do projeto.'), 'ok'); }
        else { const a = new Audio(c.mediaUrl(rec)); a.volume = 0.8; a.play().catch(() => {}); }
      } catch (err) { toast(err.message, 'err'); }
      sfx.busy = ''; paint();
    }
    paint(); el._paint = paint;
    if (!sfx.list) api('/api/studio/sfx').then((r) => { sfx.list = r.effects; paint(); }).catch((err) => { sfx.list = []; toast(err.message, 'err'); paint(); });
  });

  // ------------------------------------------------------------ captura de tela
  const cap = { rec: null, chunks: [], t0: 0, timer: 0, audio: true, mic: false, streams: [], ctx: null };
  reg('capture', t('Captura de tela'), (el, title) => {
    const supported = !!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia && window.MediaRecorder);
    const status = h('div', { class: 'muted small', id: 'cap-status', style: { margin: '8px 0' } });
    const paint = () => {
      const on = !!cap.rec;
      fill(el, head(title), h('div', { class: 'pg1' },
        supported ? null : h('div', { class: 'errbox' }, t('Este navegador não deixa o ASTA gravar a tela (ou a página não é segura). Use o Chrome, Edge ou Firefox em http://localhost.')),
        h('p', { class: 'muted small', style: { margin: '0 0 8px' } }, t('Escolha a tela, janela ou aba na janela do navegador. A gravação vira um vídeo do projeto e entra na timeline.')),
        h('label', { class: 'pf ck' }, h('input', { type: 'checkbox', checked: cap.audio, disabled: on, id: 'cap-audio', onchange: (e) => { cap.audio = e.target.checked; } }), h('span', null, t('Incluir o som da aba/sistema (se o navegador oferecer)'))),
        h('label', { class: 'pf ck' }, h('input', { type: 'checkbox', checked: cap.mic, disabled: on, id: 'cap-mic', onchange: (e) => { cap.mic = e.target.checked; } }), h('span', null, t('Incluir o microfone'))),
        h('div', { class: 'row2' }, on ? h('button', { class: 'btn sm danger', type: 'button', id: 'cap-stop', onclick: stop }, icon('stop', 13), t('Parar e usar'))
          : h('button', { class: 'btn sm primary', type: 'button', id: 'cap-start', disabled: !supported, onclick: start }, icon('computer', 13), t('Gravar a tela'))), status));
    };
    const tick = () => { status.textContent = cap.rec ? '● ' + t('Gravando') + ' ' + fmt((performance.now() - cap.t0) / 1000) : ''; };
    const release = () => { cap.streams.forEach((s) => s.getTracks().forEach((x) => x.stop())); cap.streams = []; if (cap.ctx) { try { cap.ctx.close(); } catch (e) { /* ok */ } cap.ctx = null; } clearInterval(cap.timer); cap.timer = 0; };
    async function start() {
      try {
        const disp = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 30 }, audio: cap.audio });
        cap.streams = [disp];
        let stream = disp;
        if (cap.mic) {
          try {
            const mic = await navigator.mediaDevices.getUserMedia({ audio: true }); cap.streams.push(mic);
            const AC = window.AudioContext || window.webkitAudioContext; cap.ctx = new AC(); const dest = cap.ctx.createMediaStreamDestination();
            [disp, mic].forEach((s) => { if (s.getAudioTracks().length) cap.ctx.createMediaStreamSource(new MediaStream(s.getAudioTracks())).connect(dest); });
            stream = new MediaStream([...disp.getVideoTracks(), ...dest.stream.getAudioTracks()]);
          } catch (e) { toast(t('Sem acesso ao microfone — gravando só a tela.'), 'err'); }
        }
        const mime = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm'].find((m) => MediaRecorder.isTypeSupported(m)) || '';
        cap.chunks = []; cap.rec = new MediaRecorder(stream, mime ? { mimeType: mime, videoBitsPerSecond: 6000000 } : {});
        cap.rec.ondataavailable = (ev) => { if (ev.data && ev.data.size) cap.chunks.push(ev.data); };
        cap.rec.onstop = finish;
        disp.getVideoTracks()[0].addEventListener('ended', () => { if (cap.rec && cap.rec.state !== 'inactive') cap.rec.stop(); });   // o usuário parou pelo botão do navegador
        cap.rec.start(1000); cap.t0 = performance.now(); cap.timer = setInterval(tick, 250); paint(); tick();
      } catch (e) { release(); cap.rec = null; paint(); if (e && e.name !== 'NotAllowedError') toast(e.message || t('Não foi possível gravar a tela.'), 'err'); }
    }
    function stop() { if (cap.rec && cap.rec.state !== 'inactive') cap.rec.stop(); }
    async function finish() {
      const blob = new Blob(cap.chunks, { type: (cap.rec && cap.rec.mimeType) || 'video/webm' }); release(); cap.rec = null; paint();
      if (!blob.size) { toast(t('A gravação ficou vazia.'), 'err'); return; }
      status.textContent = t('Enviando a gravação…');
      try {
        const name = 'captura-' + new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-') + '.webm';
        const r = await fetch(`/api/studio/projects/${c.pid}/media`, { method: 'POST', headers: { 'X-Filename': encodeURIComponent(name), 'Content-Type': 'video/webm' }, body: blob });
        const j = await r.json(); if (!r.ok) throw new Error(j.error || 'erro');
        c.addAssetRec(j); c.addAsset(j, c.S.t); status.textContent = ''; toast(t('Captura adicionada à timeline.'), 'ok');
      } catch (e) { status.textContent = ''; toast(e.message, 'err'); }
    }
    paint(); el._paint = paint; el._stop = () => { if (cap.rec) { cap.rec.onstop = null; try { cap.rec.stop(); } catch (e) { /* ok */ } release(); cap.rec = null; } };
  });

  // ------------------------------------------------------------ legendas
  const cp = { size: 0, color: '#ffffff', bg: '#000000', pos: 'bottom', text: '', dur: 10, atCursor: true };
  const textTracks = () => c.S.tl.tracks.filter((x) => x.kind === 'text');
  const captionClips = () => c.S.tl.clips.filter((x) => { const tr = c.trackOf(x.track); return tr && tr.kind === 'text'; }).sort((a, b) => a.start - b.start);
  reg('captions', t('Legendas'), (el, title) => {
    const style = () => ({ size: cp.size || (c.S.aspect === '9:16' ? 50 : 42), color: cp.color, bg: cp.bg, pos: cp.pos });
    const paint = () => {
    const list = captionClips();
    const area = h('textarea', { rows: 4, id: 'cap-text', placeholder: t('Cole aqui o texto: ele é dividido em legendas e distribuído pelo tempo.'), oninput: (e) => { cp.text = e.target.value; } }, cp.text);
    const file = h('input', { type: 'file', accept: '.srt,.vtt,text/vtt,application/x-subrip,text/plain', class: 'hidden', id: 'cap-file' });
    file.addEventListener('change', async () => { const f = file.files[0]; file.value = ''; if (f) await importText(await f.text()); });
    async function importText(txt) {
      try { const r = await api('/api/studio/captions/parse', { method: 'POST', body: { text: txt } }); const off = cp.atCursor ? c.S.t - r.cues[0].start : 0; c.addCaptions(r.cues.map((x) => ({ start: x.start + off, end: x.end + off, text: x.text })), style()); toast(t('{n} legenda(s) importada(s).', { n: r.cues.length }), 'ok'); } catch (e) { toast(e.message, 'err'); }
    }
    async function exportAs(format) {
      const cues = captionClips().map((x) => ({ start: x.start, dur: x.dur, text: x.text }));
      if (!cues.length) return toast(t('Não há legendas na timeline para exportar.'));
      try { const r = await fetch('/api/studio/captions/srt', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cues, format }) }); if (!r.ok) throw new Error((await r.json()).error || 'erro'); dl(await r.blob(), 'legendas.' + format); } catch (e) { toast(e.message, 'err'); }
    }
    async function generate() {
      if (!cp.text.trim()) return toast(t('Escreva o texto das legendas.'), 'err');
      try { const start = c.S.t; const r = await api('/api/studio/captions/align', { method: 'POST', body: { text: cp.text, start, end: start + Math.max(1, cp.dur) } }); c.addCaptions(r.cues, style()); toast(t('{n} legenda(s) criada(s).', { n: r.cues.length }), 'ok'); } catch (e) { toast(e.message, 'err'); }
    }
    fill(el, head(title, h('span', { class: 'muted small' }, t('{n} na timeline', { n: list.length }))),
      h('div', { class: 'pg1' }, h('div', { class: 'sub' }, t('Estilo')),
        h('div', { class: 'pg', style: { padding: 0 } }, label(t('Tamanho'), num(cp.size || '', { min: 8, max: 300, placeholder: t('automático'), id: 'cap-size', onchange: (e) => { cp.size = parseInt(e.target.value, 10) || 0; } })),
          label(t('Posição'), h('select', { onchange: (e) => { cp.pos = e.target.value; } }, [['bottom', t('Base')], ['center', t('Centro')], ['top', t('Topo')]].map(([v, l]) => h('option', { value: v, selected: v === cp.pos }, l)))),
          label(t('Cor'), h('input', { type: 'color', value: cp.color, onchange: (e) => { cp.color = e.target.value; } })), label(t('Fundo'), h('input', { type: 'color', value: cp.bg, onchange: (e) => { cp.bg = e.target.value; } }))),
        h('div', { class: 'sub' }, t('Do texto')), area,
        h('div', { class: 'row2' }, label(t('Duração total (s)'), num(cp.dur, { min: 1, step: 1, id: 'cap-dur', oninput: (e) => { cp.dur = parseFloat(e.target.value) || 10; } })), h('button', { class: 'btn sm primary', type: 'button', id: 'cap-gen', onclick: generate }, icon('type', 13), t('Gerar a partir do cursor'))),
        h('div', { class: 'sub' }, t('Arquivo SRT / WebVTT')),
        h('label', { class: 'pf ck' }, h('input', { type: 'checkbox', checked: cp.atCursor, onchange: (e) => { cp.atCursor = e.target.checked; } }), h('span', null, t('Começar no cursor (senão, nos horários do arquivo)'))),
        h('div', { class: 'row2 wrap' }, h('button', { class: 'btn sm', type: 'button', id: 'cap-import', onclick: () => file.click() }, icon('upload', 13), t('Importar arquivo')), file,
          h('button', { class: 'btn sm', type: 'button', id: 'cap-srt', onclick: () => exportAs('srt') }, icon('download', 13), 'SRT'), h('button', { class: 'btn sm', type: 'button', id: 'cap-vtt', onclick: () => exportAs('vtt') }, icon('download', 13), 'VTT')),
        h('div', { class: 'sub' }, t('Na timeline')),
        h('div', { class: 'caplist' }, list.length ? list.slice(0, 200).map((x) => h('div', { class: 'capr', onclick: () => { c.seek(x.start); c.select([x.id]); } }, h('span', { class: 'muted small' }, fmt(x.start)), h('span', { class: 'nm' }, x.text.replace(/\n/g, ' ')))) : h('div', { class: 'muted small' }, t('Nenhuma legenda ainda.')))));
    };
    paint(); el._paint = paint;
  });

  // ------------------------------------------------------------ transcrição
  const tx = { asset: '', lang: '', text: '', res: null, busy: false, msg: '', close: null };
  reg('transcribe', t('Transcrição'), (el, title) => {
    let media = [];
    const prep = () => {   // as mídias e a seleção mudam: refeito a cada desenho do painel
      media = Object.values(c.S.assets).filter((a) => a.kind === 'video' ? a.audio : a.kind === 'audio').sort((a, b) => (a.created < b.created ? 1 : -1));
      const sel = c.selClips().map((x) => c.S.assets[x.asset]).find((a) => a && (a.kind === 'audio' || (a.kind === 'video' && a.audio)));
      if (!tx.asset || !c.S.assets[tx.asset]) tx.asset = (sel && sel.id) || (media[0] && media[0].id) || '';
    };
    const msg = h('div', { class: 'muted small', id: 'tx-msg', style: { margin: '8px 0' } }, tx.msg);
    async function run() {
      if (!tx.asset) return toast(t('Escolha um áudio ou vídeo do projeto.'), 'err');
      tx.busy = true; tx.res = null; tx.msg = t('Transcrevendo…'); paint();
      try {
        const clip = c.S.tl.clips.find((x) => x.asset === tx.asset);
        const r = await api(`/api/studio/projects/${c.pid}/transcribe`, { method: 'POST', body: { asset: tx.asset, language: tx.lang, text: tx.text, offset: clip ? clip.start - (clip.in || 0) : c.S.t } });
        tx.close = events('/api/jobs/' + r.job_id + '/events', (ev) => {
          if (ev.type === 'note') { tx.msg = ev.message; msg.textContent = ev.message; }
          else if (ev.type === 'error') { tx.busy = false; tx.msg = ev.message; paint(); toast(ev.message, 'err'); if (tx.close) tx.close(); }
          else if (ev.type === 'cancelled') { tx.busy = false; tx.msg = t('Cancelado.'); paint(); if (tx.close) tx.close(); }
          else if (ev.type === 'done') { tx.busy = false; tx.res = ev; tx.msg = ''; paint(); if (tx.close) tx.close(); }
        }, () => {});
      } catch (e) { tx.busy = false; tx.msg = e.status === 409 ? t('Já há uma transcrição em andamento.') : e.message; paint(); }
    }
    function paint() {
      prep();
      fill(el, head(title), h('div', { class: 'pg1' },
        media.length ? null : h('div', { class: 'muted small' }, t('Importe um áudio ou vídeo com som para transcrever.')),
        label(t('Arquivo'), h('select', { id: 'tx-asset', disabled: tx.busy, onchange: (e) => { tx.asset = e.target.value; } }, media.map((a) => h('option', { value: a.id, selected: a.id === tx.asset }, a.name.slice(0, 40))))),
        label(t('Idioma (vazio = automático)'), h('input', { value: tx.lang, placeholder: 'pt, en…', id: 'tx-lang', disabled: tx.busy, oninput: (e) => { tx.lang = e.target.value.trim(); } })),
        h('div', { class: 'sub' }, t('Já tenho o texto (opcional)')),
        h('textarea', { rows: 3, id: 'tx-text', disabled: tx.busy, placeholder: t('Cole o texto falado: o ASTA só o alinha ao áudio, sem usar o provedor de transcrição.'), oninput: (e) => { tx.text = e.target.value; } }, tx.text),
        h('div', { class: 'row2' }, h('button', { class: 'btn sm primary', type: 'button', id: 'tx-run', disabled: tx.busy || !tx.asset, onclick: run }, tx.busy ? h('span', { class: 'spinner' }) : icon('doc', 13), t('Transcrever'))), msg,
        tx.res ? h('div', { class: 'txres', id: 'tx-res' }, h('div', { class: 'row2 wrap' }, h('button', { class: 'btn sm primary', type: 'button', id: 'tx-make', onclick: () => { c.addCaptions(tx.res.cues, { size: c.S.aspect === '9:16' ? 50 : 42, color: '#ffffff', bg: '#000000', pos: 'bottom' }); toast(t('{n} legenda(s) criada(s).', { n: tx.res.cues.length }), 'ok'); } }, icon('type', 13), t('Criar {n} legendas', { n: tx.res.cues.length })),
          h('button', { class: 'btn sm', type: 'button', onclick: () => { navigator.clipboard && navigator.clipboard.writeText(tx.res.text).then(() => toast(t('Texto copiado.'), 'ok')); } }, icon('copy', 13), t('Copiar o texto'))),
          h('div', { class: 'muted small', style: { whiteSpace: 'pre-wrap', maxHeight: '160px', overflow: 'auto', marginTop: '8px' } }, tx.res.text)) : null));
    }
    paint(); el._paint = paint;
  });

  // ------------------------------------------------------------ navegador de mídia
  const br = { q: '', kind: '', source: '', items: null, sel: new Set(), busy: false, err: '' };
  reg('browser', t('Navegador de mídia'), (el, title) => {
    const SRC = { canvas: 'Canvas', studio: 'Studio', export: 'Exportação' };
    const search = h('input', { type: 'search', id: 'br-q', placeholder: t('Buscar por nome ou prompt…'), value: br.q, oninput: (e) => { br.q = e.target.value; clearTimeout(br.tm); br.tm = setTimeout(load, 300); } });
    const key = (it) => it.source + ':' + it.ref;
    async function load() {
      br.busy = true; br.err = ''; draw();
      try { const r = await api(`/api/studio/library?q=${encodeURIComponent(br.q)}&kind=${br.kind}&source=${br.source}&exclude=${c.pid}`); br.items = r.items; br.sel = new Set([...br.sel].filter((k) => r.items.some((i) => key(i) === k))); } catch (e) { br.err = e.message; br.items = []; }
      br.busy = false; draw();
    }
    async function doImport(items, place) {
      if (!items.length) return;
      try {
        const r = await api(`/api/studio/projects/${c.pid}/import`, { method: 'POST', body: { items: items.map((i) => ({ source: i.source, ref: i.ref })) } });
        r.assets.forEach((a) => c.addAssetRec(a)); br.sel.clear();
        if (place) { let at = c.S.t; r.assets.forEach((a) => { c.addAsset(a, at); at += a.kind === 'image' ? 4 : Math.max(0.5, a.dur || 4); }); }
        toast(t('{n} arquivo(s) copiado(s) para o projeto.', { n: r.assets.length }), 'ok'); draw();
      } catch (e) { toast(e.message, 'err'); }
    }
    function draw() {
      const items = br.items || [];
      const chip = (val, txt, field) => h('button', { type: 'button', class: 'chipb' + (br[field] === val ? ' on' : ''), onclick: () => { br[field] = val; load(); } }, txt);
      fill(el, head(title, h('button', { class: 'stl-btn', type: 'button', title: t('Atualizar'), onclick: load }, icon('refresh', 14))),
        h('div', { class: 'pg1' }, search, h('div', { class: 'chiprow' }, chip('', t('Tudo'), 'kind'), chip('video', t('Vídeos'), 'kind'), chip('image', t('Imagens'), 'kind'), chip('audio', t('Áudios'), 'kind')),
          h('div', { class: 'chiprow' }, chip('', t('Todas as origens'), 'source'), chip('canvas', 'Canvas', 'source'), chip('studio', 'Studio', 'source'), chip('export', t('Exportações'), 'source'))),
        br.err ? h('div', { class: 'errbox', style: { margin: '8px' } }, br.err) : null,
        h('div', { class: 'brl', id: 'br-list' }, br.busy && !items.length ? h('div', { class: 'muted small', style: { padding: '12px' } }, t('Carregando…'))
          : items.length ? items.map((it) => h('label', { class: 'brr' + (br.sel.has(key(it)) ? ' on' : ''), title: it.where, ondblclick: () => doImport([it], true) },
            h('input', { type: 'checkbox', checked: br.sel.has(key(it)), onchange: (e) => { if (e.target.checked) br.sel.add(key(it)); else br.sel.delete(key(it)); draw(); } }),
            it.kind === 'image' ? h('div', { class: 'th', style: { backgroundImage: `url("${it.url}")` } }) : it.kind === 'video' ? h('video', { class: 'th', src: it.url, preload: 'metadata', muted: true }) : h('div', { class: 'th ico' }, icon('music', 16)),
            h('div', { class: 'col' }, h('div', { class: 'nm' }, it.name), h('div', { class: 'muted small' }, (SRC[it.source] || it.source) + ' · ' + it.where.split(' · ').slice(1).join(' · ') + (it.dur ? ' · ' + Math.round(it.dur) + ' s' : ''))))) : h('div', { class: 'muted small', style: { padding: '12px' } }, t('Nada encontrado. Gere mídias num Canvas ou em outro projeto do Studio.'))),
        h('div', { class: 'row2', style: { padding: '8px 10px' } }, h('button', { class: 'btn sm primary', type: 'button', id: 'br-import', disabled: !br.sel.size, onclick: () => doImport(items.filter((i) => br.sel.has(key(i))), false) }, icon('download', 13), t('Importar ({n})', { n: br.sel.size })),
          h('button', { class: 'btn sm', type: 'button', disabled: !br.sel.size, onclick: () => doImport(items.filter((i) => br.sel.has(key(i))), true) }, t('Importar e pôr no cursor'))));
    }
    draw(); el._paint = draw; if (br.items === null) load();
  });

  return {
    panels,
    refresh(id) { if (painters[id]) painters[id](); },
    refreshLive() { ['captions', 'transcribe', 'effects'].forEach((id) => { if (c.isOn(id) && c.isVisible(id) && painters[id]) painters[id](); }); },
    destroy() { Object.values(panels).forEach((p) => { if (p._stop) p._stop(); }); if (tx.close) tx.close(); },
  };
}
