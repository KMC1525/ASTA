// Canvas: tipos de nó na interface (paleta, controles de cada nó e área de resultado) e regras de compatibilidade das portas.
import { t } from './i18n.js';
import { accordion, checkbox, fmtBytes, h, icon, seg, select } from './ui.js';

export const compatible = (out, accepts) => accepts.includes(out)
  || (out === 'media' && accepts.some((a) => ['image', 'video', 'audio', 'media'].includes(a)))
  || (['image', 'video', 'audio'].includes(out) && accepts.includes('media'));

export const GROUPS = [
  ['Entrada', ['text', 'upload']],
  ['IA', ['llm', 'image', 'video', 'sound', 'voice', 'transcribe']],
  ['Estilo do projeto', ['style_prompt', 'style_folder']],
  ['Saída', ['editor']],
];
export const TYPE_HELP = {
  text: 'Um texto que você escreve (prompt, roteiro, fala).', llm: 'Reescreve ou cria texto com o modelo de IA configurado.',
  upload: 'Seus arquivos de imagem, vídeo ou áudio.', image: 'Gera ou edita imagens.', video: 'Gera vídeos (de texto ou a partir de uma imagem).',
  sound: 'Gera efeitos sonoros ou música.', voice: 'Transforma texto em fala.', transcribe: 'Transforma áudio ou vídeo em texto.',
  style_prompt: 'Um prompt de sistema de estilo que vale para o projeto todo.', style_folder: 'Imagens, vídeos e áudios de referência de estilo para o projeto todo.',
  editor: 'Editor de vídeo: monta tudo numa linha do tempo e exporta um MP4.',
};
export const OUT_COLOR = { text: 'var(--c-text)', image: 'var(--c-image)', video: 'var(--c-video)', audio: 'var(--c-audio)', style: 'var(--c-style)', media: 'var(--c-media)' };
export const LABEL = {
  text: 'Texto', llm: 'Texto IA', upload: 'Mídia', image: 'Imagem', video: 'Vídeo', sound: 'Som', voice: 'Voz', transcribe: 'Transcrever',
  style_prompt: 'Style Prompt', style_folder: 'Style Folder', editor: 'Editor',
};
const CAP = { image: 'image', video: 'video', sound: 'sound', voice: 'voice', transcribe: 'stt' };
const PORT_LABEL = { prompt: 'Prompt', refs: 'Referências', style: 'Estilo', image: 'Imagem inicial', text: 'Fala', audio: 'Áudio/vídeo', clips: 'Clipes' };
export const portLabel = (nodeType, p) => (nodeType === 'llm' && p.id === 'prompt' ? t('Entrada') : t(PORT_LABEL[p.id] || p.label));

// ---------------------------------------------------------------------------------------------------- controles
const cut = (e) => e.stopPropagation();
function ta(c, n, key, ph, rows) {
  const el = h('textarea', { placeholder: ph, rows: rows || 3, class: 'nodrag' });
  el.value = n.params[key] || '';
  el.addEventListener('input', () => c.change(n, key, el.value));
  el.addEventListener('keydown', cut);
  return el;
}
function txt(c, n, key, ph, type) {
  const el = h('input', { type: type || 'text', placeholder: ph || '', class: 'nodrag' });
  el.value = n.params[key] ?? '';
  el.addEventListener('input', () => c.change(n, key, type === 'number' ? Number(el.value) : el.value));
  el.addEventListener('keydown', cut);
  return el;
}
const lab = (text, ctl) => h('div', null, h('label', { class: 'f' }, text), ctl);

function providerBlock(c, n, cap, extraFields) {
  const provs = c.prov.providers.filter((p) => p.caps.includes(cap));
  const defId = c.prov.active[cap] || 'demo';
  const def = c.prov.providers.find((p) => p.id === defId);
  const eff = c.prov.providers.find((p) => p.id === (n.params.provider || defId)) || def;
  const sel = select([['', t('Padrão') + (def ? ' · ' + t(def.label) : '')], ...provs.map((p) => [p.id, t(p.label)])], n.params.provider || '', (v) => c.change(n, 'provider', v, true));
  sel.classList.add('nodrag');
  const listId = 'dl_' + n.id + cap;
  const model = txt(c, n, 'model', (eff && eff.models && eff.models[cap]) || t('modelo padrão'));
  model.setAttribute('list', listId);
  const dl = h('datalist', { id: listId }, ((eff && eff.suggest && eff.suggest[cap]) || []).map((m) => h('option', { value: m })));
  const warn = eff && eff.needs_key && !eff.has_key
    ? h('div', { class: 'warnk' }, icon('warn', 13), t('Sem chave de API:'), h('a', { href: '#/config', onclick: () => c.openConfig() }, t('configurar')))
    : (eff && eff.id === 'demo' ? h('div', { class: 'dim small' }, t('Demo: resultado simples, sem IA real.')) : null);
  let extra = {};
  const jsonEl = h('textarea', { class: 'nodrag mono', rows: 2, placeholder: '{"quality": "high"}' });
  jsonEl.value = Object.keys(n.params.extra || {}).length ? JSON.stringify(n.params.extra) : '';
  jsonEl.addEventListener('keydown', cut);
  jsonEl.addEventListener('input', () => { try { extra = jsonEl.value.trim() ? JSON.parse(jsonEl.value) : {}; jsonEl.style.borderColor = ''; c.change(n, 'extra', extra && typeof extra === 'object' && !Array.isArray(extra) ? extra : {}); } catch (e) { jsonEl.style.borderColor = 'var(--err)'; } });
  const adv = accordion(t('Avançado'), h('div', { class: 'col', style: { gap: '8px', display: 'flex', flexDirection: 'column' } },
    lab(t('Modelo'), model), dl,
    ...(extraFields || []),
    n.params.extra !== undefined ? lab(t('Parâmetros extras (JSON)'), jsonEl) : null,
    n.params.ignore_global_styles !== undefined ? checkbox(t('Ignorar estilos globais'), n.params.ignore_global_styles, (v) => c.change(n, 'ignore_global_styles', v, true)) : null));
  return [lab(t('Provedor'), sel), warn, adv];
}

function fileThumbs(c, n) {
  const files = (n.params.files || []).map((id) => c.asset(id)).filter(Boolean);
  const box = h('div', { class: 'thumbs' }, files.map((a) => {
    const pv = a.kind === 'image' ? h('img', { src: c.url(a), loading: 'lazy', draggable: 'false' })
      : a.kind === 'video' ? h('video', { src: c.url(a) + '#t=0.1', preload: 'metadata', muted: true })
        : h('div', null, icon('audio', 20));
    return h('div', { class: 'thumb nodrag', title: a.name, onclick: () => c.preview(a) }, pv, h('div', { class: 'nm' }, a.name),
      h('span', { class: 'x', onclick: (e) => { e.stopPropagation(); c.change(n, 'files', n.params.files.filter((f) => f !== a.id), true); } }, '×'));
  }));
  const input = h('input', { type: 'file', multiple: true, accept: 'image/*,video/*,audio/*', class: 'hidden', onchange: (e) => { c.uploadTo(n, [...e.target.files]); e.target.value = ''; } });
  return [files.length ? box : h('div', { class: 'dim small' }, t('Arraste arquivos aqui ou use o botão.')),
    h('button', { class: 'btn sm nodrag', onclick: () => input.click() }, icon('upload', 13), t('Adicionar arquivos')), input];
}

const BODY = {
  text: (c, n) => [ta(c, n, 'text', t('Escreva o texto…'), 4)],
  llm: (c, n) => [ta(c, n, 'instruction', t('O que fazer com o texto de entrada? Ex.: “Descreva a cena com detalhes visuais”.'), 3),
    h('div', { class: 'dim small' }, t('Usa o modelo de texto ativo em Configuração → Provedores.')),
    checkbox(t('Ignorar estilos globais'), n.params.ignore_global_styles, (v) => c.change(n, 'ignore_global_styles', v, true))],
  upload: (c, n) => fileThumbs(c, n),
  image: (c, n) => [
    seg([['generate', t('Gerar')], ['edit', t('Editar')]], n.params.mode, (v) => c.change(n, 'mode', v, true)),
    ta(c, n, 'prompt', n.params.mode === 'edit' ? t('O que mudar na imagem ligada em “Referências”?') : t('Descreva a imagem (ou ligue um nó de texto)…'), 3),
    h('div', { class: 'r2' }, lab(t('Tamanho'), select(c.meta.sizes.map((s) => [s, s.replace('x', '×')]), n.params.size, (v) => c.change(n, 'size', v))),
      lab(t('Quantidade'), select([1, 2, 3, 4].map((i) => [String(i), String(i)]), String(n.params.count), (v) => c.change(n, 'count', Number(v))))),
    ...providerBlock(c, n, 'image', [lab(t('Prompt negativo'), txt(c, n, 'negative', t('o que evitar'))), lab(t('Semente (0 = aleatória)'), txt(c, n, 'seed', '0', 'number'))])],
  video: (c, n) => [
    ta(c, n, 'prompt', t('Descreva o vídeo (ou ligue um texto e/ou uma imagem inicial)…'), 3),
    h('div', { class: 'r2' }, lab(t('Duração (s)'), txt(c, n, 'duration', '5', 'number')), lab(t('Proporção'), select(c.meta.aspects.map((a) => [a, a]), n.params.aspect, (v) => c.change(n, 'aspect', v)))),
    ...providerBlock(c, n, 'video')],
  sound: (c, n) => [
    seg([['sfx', t('Efeito')], ['music', t('Música')]], n.params.kind, (v) => c.change(n, 'kind', v, true)),
    ta(c, n, 'prompt', n.params.kind === 'music' ? t('Estilo da música: calma, piano, noturna…') : t('Ex.: chuva forte com trovões'), 2),
    lab(t('Duração (s)'), txt(c, n, 'duration', '5', 'number')),
    ...providerBlock(c, n, 'sound')],
  voice: (c, n) => [
    ta(c, n, 'text', t('O que a voz vai dizer (ou ligue um nó de texto)…'), 3),
    h('div', { class: 'r2' }, lab(t('Voz'), txt(c, n, 'voice', t('padrão'))), lab(t('Velocidade'), txt(c, n, 'speed', '1', 'number'))),
    ...providerBlock(c, n, 'voice')],
  transcribe: (c, n) => [h('div', { class: 'dim small' }, t('Ligue um áudio ou vídeo na entrada.')), lab(t('Idioma (opcional)'), txt(c, n, 'language', 'pt, en…')), ...providerBlock(c, n, 'stt')],
  style_prompt: (c, n) => [ta(c, n, 'text', t('Ex.: ilustração em aquarela, cores suaves, traço delicado.'), 4), globalCheck(c, n)],
  style_folder: (c, n) => [...fileThumbs(c, n), globalCheck(c, n),
    n.result.digest ? h('div', { class: 'digest nodrag' }, n.result.digest) : null,
    (n.params.files || []).length ? h('button', { class: 'btn sm nodrag', onclick: () => c.run([n.id], true) }, icon('refresh', 13), t('Analisar estilo')) : null],
  editor: (c, n) => {
    const tl = n.params.timeline;
    return [h('div', { class: 'small muted' }, t('{n} clipe(s) · {s}s', { n: tl.clips.length, s: (tl.duration || 0).toFixed(1) }) + ' · ' + n.params.width + '×' + n.params.height),
      h('button', { class: 'btn sm primary nodrag', onclick: () => c.openTimeline(n) }, icon('film', 13), t('Abrir editor')),
      h('div', { class: 'dim small' }, t('Ligue nós em “Clipes” para usar as saídas deles na linha do tempo.'))];
  },
};
function globalCheck(c, n) {
  return h('div', null, checkbox(t('Vale para o projeto todo'), n.params.global, (v) => c.change(n, 'global', v, true)),
    h('div', { class: 'dim small' }, n.params.global ? t('Aplicado automaticamente a todos os nós de geração.') : t('Aplicado só aos nós ligados em “Estilo”.')));
}

export const nodeBody = (c, n) => h('div', { class: 'bd' }, BODY[n.type] ? BODY[n.type](c, n) : null);
export const capOf = (type) => CAP[type] || '';

// ---------------------------------------------------------------------------------------------------- resultado
export function nodeResult(c, n) {
  const st = c.state(n.id), r = n.result;
  const box = h('div', { class: 'res' });
  const items = (r.assets || []).map((id) => c.asset(id)).filter(Boolean);
  if (st.state === 'running') box.append(h('div', { class: 'run' }, h('div', { class: 'spinner' }), st.note || t('Gerando…')));
  else if (st.state === 'queued') box.append(h('div', { class: 'run' }, t('Na fila…')));
  else if (st.state === 'skipped') box.append(h('div', { class: 'dim small' }, t('Pulado: um nó de entrada falhou.')));
  const error = st.state === 'error' ? st.message : (r.state === 'error' ? r.error : '');
  if (error) box.append(h('div', { class: 'err' }, error));
  if (st.state === 'running' || st.state === 'queued') return box;
  const imgs = items.filter((a) => a.kind === 'image');
  if (imgs.length) box.append(h('div', { class: 'rimgs nodrag' + (imgs.length === 1 ? ' one' : '') }, imgs.map((a) => h('img', { src: c.url(a), loading: 'lazy', title: a.prompt || a.name, draggable: 'false', onclick: () => c.preview(a, imgs) }))));
  items.filter((a) => a.kind === 'video').forEach((a) => box.append(h('video', { src: c.url(a), controls: true, preload: 'metadata', class: 'nodrag' })));
  items.filter((a) => a.kind === 'audio').forEach((a) => box.append(h('audio', { src: c.url(a), controls: true, preload: 'metadata', class: 'nodrag' })));
  if ((n.type === 'llm' || n.type === 'transcribe') && r.text) box.append(h('div', { class: 'rtxt nodrag' }, r.text));
  (st.warnings || []).forEach((w) => box.append(h('div', { class: 'wr' }, w)));
  if (items.length) box.append(h('div', { class: 'dim small', style: { marginTop: '6px' } }, items.map((a) => (a.provider ? t(c.providerLabel(a.provider)) : '') + (a.model ? ' · ' + a.model : '')).filter(Boolean)[0] || ''));
  return box.childNodes.length ? box : null;
}
export { fmtBytes };
