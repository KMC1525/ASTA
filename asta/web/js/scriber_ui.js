// Scriber — peças compartilhadas pelas duas abas (Geração automática e Edição): estado do projeto (S), API do projeto, execução de jobs de IA, caixas de diálogo (formatação, histórico) e exportar.
import { api, events } from './api.js';
import { t } from './i18n.js';
import { state } from './main.js';
import { confirmDialog, h, icon, modal, select, toast } from './ui.js';

export const TABS = [['generate', 'Geração automática', 'sparkle'], ['edit', 'Edição', 'edit']];
export const LAST = 'asta.scriber.pid';
export const FONT_FALLBACK = { 'Times New Roman': '"Times New Roman", Times, serif', Georgia: 'Georgia, serif', Garamond: 'Garamond, "EB Garamond", serif', Cambria: 'Cambria, Georgia, serif', 'Palatino Linotype': '"Palatino Linotype", Palatino, serif',
  'Book Antiqua': '"Book Antiqua", Palatino, serif', Calibri: 'Calibri, Carlito, "Segoe UI", sans-serif', Arial: 'Arial, Helvetica, sans-serif', Verdana: 'Verdana, sans-serif', Helvetica: 'Helvetica, Arial, sans-serif', 'Courier New': '"Courier New", monospace',
  'Trebuchet MS': '"Trebuchet MS", sans-serif', Tahoma: 'Tahoma, sans-serif', 'Segoe UI': '"Segoe UI", sans-serif' };
export const PRESET_LABEL = { book: 'Livro', manuscript: 'Manuscrito', article: 'Artigo', report: 'Relatório', academic: 'Acadêmico (ABNT/APA)', copy: 'Copy' };
export const GROUP_LABEL = { fiction: 'Ficção', professional: 'Profissional', academic: 'Acadêmico e científico' };
export const ALIGN_LABEL = { left: 'Esquerda', justify: 'Justificado', center: 'Centralizado', right: 'Direita' };

let catCache = null;
export async function catalog() { if (!catCache) catCache = await api('/api/scriber/catalog'); return catCache; }

// ---- API do projeto
export function projectApi(pid) {
  const base = `/api/scriber/projects/${pid}`;
  return {
    base, get: (p, opt) => api(base + p, opt), post: (p, body) => api(base + p, { method: 'POST', body: body || {} }), put: (p, body) => api(base + p, { method: 'PUT', body }), del: (p) => api(base + p, { method: 'DELETE' }),
    doc: () => api(base + '/document'), saveDoc: (html, label) => api(base + '/document', { method: 'PUT', body: { html, label: label || '' } }),
    download: (name) => `${base}/exports/${encodeURIComponent(name)}`,
  };
}

// ---- o estado do projeto aberto (uma instância por projeto; as abas leem e escrevem aqui)
export async function openProject(pid) {
  const [proj, cat, status] = await Promise.all([api('/api/scriber/projects/' + pid), catalog(), api('/api/scriber/status').catch(() => ({ text: {}, dictionaries: {} }))]);
  const S = { pid, proj, cat, status, api: projectApi(pid), tabCleanup: [] };
  S.refresh = async () => { S.proj = await api('/api/scriber/projects/' + pid); return S.proj; };
  S.go = (tab) => { state.ctx = {}; location.hash = `#/scriber/${pid}/${tab}`; };
  S.onCleanup = (fn) => S.tabCleanup.push(fn);
  S.cleanup = () => { S.tabCleanup.splice(0).forEach((fn) => { try { fn(); } catch (e) { /* ok */ } }); };
  S.cfg = () => Object.assign({ expand_words: 150, dialogue_words: 60, spellcheck: true, autosave: true }, (state.settings || {}).scriber || {});
  return S;
}

// ---- roda um job de IA e devolve o resultado; `onEvent` recebe todos os eventos (etapas, progresso, notas…). `S.cancelJob()` cancela o último.
export function runJob(S, endpoint, body, onEvent) {
  return new Promise(async (resolve, reject) => {
    let jid = '';
    try { jid = (await api(`${S.api.base}/${endpoint}`, { method: 'POST', body })).job_id; }
    catch (e) { if (e.status === 409 && e.data && e.data.job_id) jid = e.data.job_id; else return reject(e); }
    S.jobId = jid;
    let result = null, failed = '';
    const stop = events(`/api/jobs/${jid}/events`, (ev) => {
      if (onEvent) onEvent(ev);
      if (ev.type === 'result') result = ev.data; else if (ev.type === 'error') failed = ev.message || t('Erro'); else if (ev.type === 'cancelled') failed = t('Cancelado.');
    }, () => { S.jobId = ''; failed ? reject(new Error(failed)) : resolve(result); });
    S.onCleanup(stop);
  });
}
export const cancelJob = (S) => { if (S.jobId) api('/api/jobs/' + S.jobId + '/cancel', { method: 'POST', body: {} }).catch(() => {}); };

// ---- pequenos componentes
export function btn(label, ic, fn, cls, attrs) { return h('button', Object.assign({ type: 'button', class: 'btn sm ' + (cls || ''), onclick: fn }, attrs || {}), ic ? icon(ic, 14) : null, label ? h('span', null, label) : null); }
export function ibtn(title, ic, fn, cls, attrs) { return h('button', Object.assign({ type: 'button', class: 'btn ghost icon sm ' + (cls || ''), title, onclick: fn }, attrs || {}), icon(ic, 15)); }
export function numField(value, onInput, o = {}) {
  const i = h('input', { type: 'number', value: value == null ? '' : value, step: o.step || 'any', min: o.min, max: o.max, id: o.id });
  i.addEventListener('input', () => { const v = parseFloat(i.value); if (!isNaN(v)) onInput(v); });
  return i;
}
export const labeled = (label, control, hint) => h('label', { class: 'sc-f' }, h('span', { class: 'l' }, label), control, hint ? h('span', { class: 'hint' }, hint) : null);
export const fmtDateTime = (iso) => String(iso || '').replace('T', ' ').replace(/\..*|\+.*|Z$/, '').slice(0, 16);

// ---- exportar (.docx, .md, .txt, .html): grava no projeto e baixa
export async function exportAs(S, fmt) {
  try {
    const e = await S.api.post('/export', { format: fmt });
    const a = h('a', { href: S.api.download(e.name), download: e.name, class: 'hidden' }); document.body.appendChild(a); a.click(); a.remove();
    toast(t('Exportado: {n}', { n: e.name }), 'ok');
    return e;
  } catch (e) { toast(e.message, 'err'); return null; }
}

// ---- importar um arquivo para o projeto (substitui ou acrescenta)
export function importDialog(S, onDone) {
  const inp = h('input', { type: 'file', accept: '.docx,.md,.markdown,.txt,.html,.htm', class: 'hidden', id: 'sc-import-file' });
  inp.addEventListener('change', async () => {
    const f = inp.files[0]; inp.remove(); if (!f) return;
    const cur = (await S.api.doc().catch(() => ({ stats: { words: 0 } }))).stats.words;
    let mode = 'replace';
    if (cur > 0) {
      const c = await modal(t('Importar «{n}»', { n: f.name }), h('p', { class: 'muted', style: { margin: 0 } }, t('O documento tem {w} palavras. O que fazer com o arquivo?', { w: cur })),
        [{ label: t('Cancelar'), value: null }, { label: t('Acrescentar no fim'), value: 'append' }, { label: t('Substituir (o atual vai para o histórico)'), value: 'replace', cls: 'primary' }]);
      if (!c) return; mode = c;
    }
    try {
      const r = await api(`${S.api.base}/import?mode=${mode}`, { method: 'POST', body: f, raw: true, headers: { 'X-Filename': encodeURIComponent(f.name), 'Content-Type': 'application/octet-stream' } });
      S.proj = r.project; toast(t('Importado: {w} palavras', { w: r.stats.words }), 'ok'); if (onDone) onDone(r);
    } catch (e) { toast(e.message, 'err'); }
  });
  document.body.appendChild(inp); inp.click();
}

// ---- histórico (pontos de retorno)
export async function historyDialog(S, onRestore) {
  const { items } = await S.api.get('/history');
  const list = h('div', { class: 'sc-hist' }, items.length ? items.map((it) => h('div', { class: 'sc-hrow' }, h('div', null, h('div', null, it.label || '—'), h('div', { class: 'small dim' }, fmtDateTime(it.t) + ' · ' + t('{w} palavras', { w: it.words }))),
    h('button', { class: 'btn sm', type: 'button', onclick: async () => { if (!(await confirmDialog(t('Voltar o texto a este ponto? O estado atual também fica no histórico.'), false, t('Voltar')))) return; await S.api.post('/history/restore', { id: it.id }); toast(t('Texto restaurado'), 'ok'); document.querySelector('.modal-bg') && document.querySelector('.modal-bg').remove(); if (onRestore) onRestore(); } }, t('Restaurar')))) : h('p', { class: 'muted' }, t('Nenhum ponto de retorno ainda. A IA e as importações guardam um antes de mudar o texto.')));
  await modal(t('Histórico'), list, [{ label: t('Salvar um ponto agora'), value: 'snap' }, { label: t('Fechar'), value: null }]).then(async (v) => { if (v === 'snap') { await S.api.post('/snapshot', { label: t('ponto de retorno manual') }); toast(t('Ponto de retorno salvo'), 'ok'); } });
}

// ---- formatação do documento (fonte, página, margens…) e dados do projeto
export function formatFields(S, fmt, onChange) {
  const cat = S.cat, set = (k, v) => { fmt[k] = v; if (onChange) onChange(fmt); };
  const sel = (id, opts, k, num) => select(opts, String(fmt[k]), (v) => set(k, num ? parseFloat(v) : v), { id });
  const chk = (id, label, k) => { const i = h('input', { type: 'checkbox', id, checked: !!fmt[k] }); i.addEventListener('change', () => set(k, i.checked)); return h('label', { class: 'check' }, i, h('span', null, label)); };
  const mar = (i, label) => labeled(label, numField(fmt.margins[i], (v) => { fmt.margins[i] = v; if (onChange) onChange(fmt); }, { min: 1, max: 6, step: 0.1, id: 'sc-fm-m' + i }));
  const txt = (id, k, ph) => { const i = h('input', { value: fmt[k] || '', id, placeholder: ph || '' }); i.addEventListener('input', () => set(k, i.value)); return i; };
  const preset = select(Object.keys(cat.presets).map((k) => [k, t(PRESET_LABEL[k] || k)]), fmt.preset, (v) => { Object.assign(fmt, JSON.parse(JSON.stringify(cat.presets[v])), { preset: v, header: fmt.header, author: fmt.author, subtitle: fmt.subtitle }); if (onChange) onChange(fmt, true); }, { id: 'sc-fm-preset' });
  return h('div', { class: 'sc-fmt' },
    labeled(t('Modelo de formatação'), preset, t('Muda a fonte, o espaçamento, a página e as margens de uma vez; depois ajuste o que quiser.')),
    h('div', { class: 'grid2' }, labeled(t('Fonte'), sel('sc-fm-font', cat.fonts.map((f) => [f, f]), 'font')), labeled(t('Tamanho (pt)'), numField(fmt.size, (v) => set('size', v), { min: 8, max: 24, step: 0.5, id: 'sc-fm-size' }))),
    h('div', { class: 'grid2' }, labeled(t('Entrelinha'), numField(fmt.line, (v) => set('line', v), { min: 1, max: 3, step: 0.05, id: 'sc-fm-line' })), labeled(t('Recuo da primeira linha (cm)'), numField(fmt.indent, (v) => set('indent', v), { min: 0, max: 3, step: 0.05, id: 'sc-fm-indent' }))),
    h('div', { class: 'grid2' }, labeled(t('Alinhamento'), sel('sc-fm-align', cat.aligns.map((a) => [a, t(ALIGN_LABEL[a])]), 'align')), labeled(t('Espaço depois do parágrafo (pt)'), numField(fmt.space_after, (v) => set('space_after', v), { min: 0, max: 36, step: 1, id: 'sc-fm-after' }))),
    labeled(t('Página'), sel('sc-fm-page', Object.entries(cat.pages).map(([k, [w, hh]]) => [k, `${k} (${w} × ${hh} cm)`]), 'page')),
    h('div', { class: 'sc-margins' }, mar(0, t('Margem de cima (cm)')), mar(1, t('Margem de baixo (cm)')), mar(2, t('Margem esquerda (cm)')), mar(3, t('Margem direita (cm)'))),
    h('div', { class: 'sc-checks' }, chk('sc-fm-title', t('Capa com título'), 'title_page'), chk('sc-fm-toc', t('Sumário'), 'toc'), chk('sc-fm-pn', t('Número de página'), 'page_numbers'), chk('sc-fm-cb', t('Cada capítulo (título 1) em página nova'), 'chapter_break')),
    h('div', { class: 'grid2' }, labeled(t('Cabeçalho'), txt('sc-fm-header', 'header', t('texto no alto de cada página'))), labeled(t('Autor'), txt('sc-fm-author', 'author', t('aparece na capa')))),
    labeled(t('Subtítulo'), txt('sc-fm-sub', 'subtitle', t('aparece na capa'))));
}

export async function propertiesDialog(S, onSaved) {
  const m = JSON.parse(JSON.stringify(S.proj)), cat = S.cat;
  const name = h('input', { value: m.name, maxlength: 100, id: 'sc-pp-name' });
  const type = select(Object.entries(cat.types).map(([k, v]) => [k, t(v.label)]), m.type, (v) => { m.type = v; }, { id: 'sc-pp-type' });
  const lang = select(Object.entries(cat.languages).map(([k, v]) => [k, t(v)]), m.language, (v) => { m.language = v; }, { id: 'sc-pp-lang' });
  const content = select([['', t('Seguir a configuração do Scriber')], ['free', t('Livre (SFW e NSFW)')], ['sfw', t('Só SFW')]], m.content, (v) => { m.content = v; }, { id: 'sc-pp-content' });
  const body = h('div', { class: 'sc-props' }, labeled(t('Título'), name), h('div', { class: 'grid2' }, labeled(t('Tipo de escrita'), type), labeled(t('Idioma (corretor e IA)'), lang)), labeled(t('Conteúdo'), content, t('Os limites fixos não mudam: nada sexual com menores nem com pessoas reais.')), formatFields(S, m.format));
  if (await modal(t('Propriedades do documento'), body, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]) !== 'ok') return null;
  S.proj = await S.api.put('', { name: name.value.trim() || m.name, type: m.type, language: m.language, content: m.content, format: m.format });
  if (onSaved) onSaved(S.proj);
  return S.proj;
}
