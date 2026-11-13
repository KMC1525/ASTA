// Modo Data → editor do item (v0.24): grade editável com paginação no servidor, mídia, colunas, limpeza, duplicados, histórico e mesclagem.
// Os dados ficam no servidor (a tela pede uma página por vez); cada edição vira uma chamada pequena e deixa um snapshot no histórico.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { confirmDialog, h, icon, modal, select, tagsInput, toast } from '../ui.js';

export const FIELD_TYPES = ['text', 'number', 'integer', 'boolean', 'date', 'url', 'category', 'json', 'image', 'audio', 'video', 'file'];
const PAGE_SIZES = [25, 50, 100, 200];
const IMG = /\.(png|jpe?g|gif|webp|bmp|avif)(\?|#|$)/i;
const AUD = /\.(mp3|wav|ogg|m4a|flac|opus)(\?|#|$)/i;
const VID = /\.(mp4|webm|mov|m4v)(\?|#|$)/i;

const kindName = (k) => (k === 'database' ? t('Database') : t('Dataset'));
export const itemUrl = (kind, id) => `/api/data/items/${kind}/${id}`;

// ------------------------------------------------------------------ valores e células
export function mediaSrc(kind, id, v) {
  if (typeof v !== 'string') return '';
  if (v.startsWith('attachments/')) return `${itemUrl(kind, id)}/media/${encodeURIComponent(v.slice('attachments/'.length))}`;
  return /^https?:\/\//i.test(v) ? v : '';
}

function mediaKind(v, ftype) {
  if (typeof v !== 'string') return '';
  if (ftype === 'image' || IMG.test(v)) return 'image';
  if (ftype === 'audio' || AUD.test(v)) return 'audio';
  if (ftype === 'video' || VID.test(v)) return 'video';
  return '';
}

function plain(v) {
  if (v === null || v === undefined) return '';
  if (typeof v === 'object') { try { return JSON.stringify(v); } catch (e) { return String(v); } }
  return String(v);
}

export function renderCell(v, ftype, kind, id) {
  if (v === null || v === undefined || v === '') return h('span', { class: 'muted' }, '');
  const mk = mediaKind(v, ftype);
  const src = mk ? mediaSrc(kind, id, v) : '';
  if (mk && src) {
    if (mk === 'image') return h('img', { class: 'dt-thumb', src, loading: 'lazy', alt: String(v), referrerpolicy: 'no-referrer' });
    if (mk === 'audio') return h('audio', { class: 'dt-aud', src, controls: true, preload: 'none' });
    return h('video', { class: 'dt-vid', src, controls: true, preload: 'none' });
  }
  if (typeof v === 'boolean') return h('span', null, v ? '✓' : '✗');
  if (typeof v === 'string' && /^https?:\/\/\S+$/i.test(v)) return h('a', { href: v, target: '_blank', rel: 'noopener noreferrer', title: v }, v.length > 60 ? v.slice(0, 57) + '…' : v);
  if (typeof v === 'string' && v.startsWith('attachments/')) {
    const href = mediaSrc(kind, id, v);
    return href ? h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, v.slice('attachments/'.length)) : h('span', null, v);
  }
  const s = plain(v);
  return h('div', { class: 'dt-rec', title: s.length > 120 ? s.slice(0, 600) : '' }, s.length > 300 ? s.slice(0, 297) + '…' : s);
}

// o que o usuário digitou → o valor do tipo da coluna (o servidor valida de novo ao guardar)
export function parseInput(text, ftype) {
  const s = String(text);
  if (s.trim() === '') return '';
  if (ftype === 'integer' || ftype === 'number') {
    const n = Number(s.trim().replace(',', '.'));
    return Number.isFinite(n) && (ftype === 'number' || Number.isInteger(n)) ? n : s;
  }
  if (ftype === 'boolean') {
    const l = s.trim().toLowerCase();
    if (['true', 'sim', 'yes', '1'].includes(l)) return true;
    if (['false', 'nao', 'não', 'no', '0'].includes(l)) return false;
    return s;
  }
  if (ftype === 'json') { try { return JSON.parse(s); } catch (e) { return s; } }
  return s;
}

async function uploadMedia(kind, id, file) {
  const r = await fetch(`${itemUrl(kind, id)}/media?name=${encodeURIComponent(file.name)}`, { method: 'POST', headers: { 'X-Filename': encodeURIComponent(file.name) }, body: await file.arrayBuffer() });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || t('Falha no upload.'));
  return j;
}

// ------------------------------------------------------------------ qualidade: perfil, duplicados e limpeza
const ISSUE_TEXT = {
  empty_column: (i) => t('A coluna «{f}» está vazia em todos os registros.', { f: i.field }),
  constant_column: (i) => t('A coluna «{f}» tem o mesmo valor em todos os registros.', { f: i.field }),
  sparse_column: (i) => t('A coluna «{f}» está preenchida em apenas {n} de {m} registros.', { f: i.field, n: i.filled, m: i.total }),
  mixed_types: (i) => t('A coluna «{f}» mistura tipos de valor: {x}.', { f: i.field, x: (i.types || []).join(', ') }),
  type_mismatch: (i) => t('A coluna «{f}» foi declarada como «{d}», mas tem valores de outro tipo.', { f: i.field, d: i.declared }),
  duplicates: (i) => t('{n} registro(s) repetido(s) — use «Remover duplicados».', { n: i.count }),
  no_records: () => t('Ainda não há registros.'),
};

async function profileDialog(kind, id) {
  let p;
  try { p = await api(`${itemUrl(kind, id)}/profile`); } catch (e) { toast(e.message, 'err'); return; }
  const num = (v) => (v === undefined || v === null ? '' : String(Math.round(v * 1000) / 1000));
  const head = h('tr', null, ...[t('Campo'), t('Preenchidos'), t('Faltando'), t('Distintos'), t('Tipos'), t('Mín–Máx'), t('Mais comuns')].map((x) => h('th', null, x)));
  const rows = (p.columns || []).map((c) => h('tr', null,
    h('td', null, c.name), h('td', null, String(c.filled)), h('td', null, String(c.missing)), h('td', null, String(c.distinct) + (c.distinct_exact ? '' : '+')),
    h('td', null, Object.keys(c.types || {}).join(', ')),
    h('td', null, c.min !== undefined ? `${num(c.min)} – ${num(c.max)}` : (c.len_min !== undefined ? t('{a}–{b} caracteres', { a: c.len_min, b: c.len_max }) : '')),
    h('td', null, (c.top || []).map((x) => `${String(x.value).slice(0, 24)} (${x.count})`).join('; '))));
  const issues = (p.issues || []).map((i) => (ISSUE_TEXT[i.code] ? ISSUE_TEXT[i.code](i) : i.code));
  const body = h('div', { class: 'col', style: { gap: '10px', minWidth: 'min(900px,90vw)' } },
    h('div', { class: 'muted small' }, t('{n} registro(s) · {m} campo(s)', { n: p.records, m: (p.columns || []).length })),
    issues.length ? h('ul', { style: { margin: 0, paddingLeft: '18px' } }, ...issues.map((x) => h('li', null, x))) : h('div', { class: 'muted' }, t('Nenhum problema encontrado.')),
    h('div', { class: 'dt-table-wrap' }, h('table', { class: 'dt-table' }, h('thead', null, head), h('tbody', null, ...rows))));
  await modal(t('Perfil dos dados'), body, [{ label: t('Fechar'), value: 'close', cls: 'primary' }]);
}

async function dedupeDialog(kind, id) {
  let prev;
  try { prev = await api(`${itemUrl(kind, id)}/dedupe`, { method: 'POST', body: { apply: false } }); } catch (e) { toast(e.message, 'err'); return false; }
  if (!prev.removed) { toast(t('Nenhum registro repetido.'), 'ok'); return false; }
  const body = h('div', { class: 'col', style: { gap: '8px' } },
    h('div', null, t('{n} de {m} registro(s) são repetidos e serão removidos; o primeiro de cada grupo fica.', { n: prev.removed, m: prev.total })),
    h('div', { class: 'muted small' }, t('Campos comparados: {x}', { x: (prev.keys || []).join(', ') })),
    h('div', { class: 'muted small' }, t('O estado atual fica no histórico: dá para restaurar.')));
  const v = await modal(t('Remover duplicados'), body, [{ label: t('Cancelar'), value: false }, { label: t('Remover duplicados'), value: true, cls: 'primary' }]);
  if (v !== true) return false;
  try {
    const done = await api(`${itemUrl(kind, id)}/dedupe`, { method: 'POST', body: { apply: true } });
    toast(t('{n} registro(s) removido(s)', { n: done.removed }), 'ok');
    return !!done.applied;
  } catch (e) { toast(e.message, 'err'); return false; }
}

async function cleanDialog(kind, id) {
  const chk = (label, on, idx) => { const i = h('input', { type: 'checkbox', checked: on, id: 'dt-clean-' + idx }); return [i, h('label', { class: 'row small', style: { gap: '6px', cursor: 'pointer' } }, i, h('span', null, label))]; };
  const [trim, trimL] = chk(t('Tirar espaços sobrando'), true, 'trim');
  const [coerce, coerceL] = chk(t('Converter os valores ao tipo de cada campo'), true, 'coerce');
  const [rows, rowsL] = chk(t('Remover linhas totalmente vazias'), true, 'rows');
  const [cols, colsL] = chk(t('Remover colunas sem nenhum valor'), false, 'cols');
  const [fill, fillL] = chk(t('Preencher vazios com a mediana / valor mais comum da coluna'), false, 'fill');
  const out = h('div', { class: 'small', id: 'dt-clean-out', style: { minHeight: '40px' } });
  const opts = () => ({ trim: trim.checked, coerce: coerce.checked, drop_empty_rows: rows.checked, drop_empty_columns: cols.checked, fill_missing: fill.checked });
  let applied = false;
  const show = (r) => {
    const parts = [t('{a} → {b} registro(s)', { a: r.before, b: r.after }), t('{n} valor(es) com espaços arrumados', { n: r.trimmed }), t('{n} valor(es) convertidos', { n: r.converted }),
      t('{n} valor(es) não converteram (mantidos)', { n: r.failed }), t('{n} coluna(s) removida(s)', { n: r.columns_removed })];
    if (r.fill) parts.push(t('{n} vazio(s) preenchidos', { n: r.fill.total }));
    out.replaceChildren(h('ul', { style: { margin: 0, paddingLeft: '18px' } }, ...parts.map((x) => h('li', null, x))), r.applied ? h('b', null, t('Aplicado. O estado anterior está no histórico.')) : h('span', { class: 'muted' }, r.changed ? t('Prévia: nada foi alterado ainda.') : t('Nada a limpar.')));
  };
  const call = async (apply) => {
    try { const r = await api(`${itemUrl(kind, id)}/clean`, { method: 'POST', body: { options: opts(), apply } }); show(r); if (apply && r.applied) applied = true; } catch (e) { toast(e.message, 'err'); }
  };
  const body = h('div', { class: 'col', style: { gap: '8px', minWidth: 'min(520px,90vw)' } }, trimL, coerceL, rowsL, colsL, fillL,
    h('div', { class: 'dt-actions' }, h('button', { class: 'btn', id: 'dt-clean-preview', type: 'button', onclick: () => call(false) }, t('Ver prévia')), h('button', { class: 'btn primary', id: 'dt-clean-apply', type: 'button', onclick: () => call(true) }, t('Aplicar'))), out);
  await modal(t('Limpar os dados'), body, [{ label: t('Fechar'), value: 'close' }]);
  return applied;
}

// ------------------------------------------------------------------ histórico, schema e mídia
async function historyDialog(kind, id) {
  let items = [];
  try { items = (await api(`${itemUrl(kind, id)}/history`)).items || []; } catch (e) { toast(e.message, 'err'); return false; }
  let restored = false;
  const list = h('div', { class: 'col', style: { gap: '4px', minWidth: 'min(560px,90vw)', maxHeight: '50vh', overflow: 'auto' } });
  const label = (hid) => { const m = String(hid).match(/^(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})[^_]*_(.*)$/); return m ? `${m[1]} ${m[2]}:${m[3]}:${m[4]} · ${m[5]}` : hid; };
  list.replaceChildren(...(items.length ? items.map((it) => h('div', { class: 'row dt-history-item', style: { gap: '8px', alignItems: 'center' } },
    h('span', { class: 'small grow' }, label(it.id)),
    h('button', { class: 'btn sm', type: 'button', onclick: async () => {
      if (!(await confirmDialog(t('Restaurar esta versão? O estado atual continua no histórico.'), false, t('Restaurar')))) return;
      try { await api(`${itemUrl(kind, id)}/history/restore`, { method: 'POST', body: { id: it.id } }); toast(t('Versão restaurada'), 'ok'); restored = true; } catch (e) { toast(e.message, 'err'); }
    } }, t('Restaurar')))) : [h('div', { class: 'muted' }, t('Sem versões no histórico.'))]));
  await modal(t('Histórico (últimas 30 versões)'), list, [{ label: t('Fechar'), value: 'close' }]);
  return restored;
}

async function schemaDialog(kind, id, schema) {
  const box = h('textarea', { id: 'dt-schema-json', style: { width: '100%', minHeight: '280px', fontFamily: 'monospace', fontSize: '12px' } }, JSON.stringify(schema || { fields: [] }, null, 2));
  const body = h('div', { class: 'col', style: { gap: '8px', minWidth: 'min(640px,90vw)' } },
    h('p', { class: 'muted small', style: { margin: 0 } }, t('Cada campo tem name, type (text, number, integer, boolean, date, url, category, json, image, audio, video, file), description e required.')),
    box,
    h('div', { class: 'dt-actions' }, h('button', { class: 'btn', id: 'dt-schema-infer', type: 'button', onclick: async () => {
      try { const r = await api(`${itemUrl(kind, id)}/schema/infer`, { method: 'POST', body: {} }); box.value = JSON.stringify(r.schema, null, 2); toast(t('{n} campo(s) deduzido(s) dos dados', { n: r.added }), 'ok'); } catch (e) { toast(e.message, 'err'); }
    } }, icon('sparkle', 14), t('Deduzir dos dados'))));
  const v = await modal(t('Schema'), body, [{ label: t('Cancelar'), value: null }, { label: t('Salvar schema'), value: 'ok', cls: 'primary' }]);
  if (v !== 'ok') return false;
  try {
    await api(`${itemUrl(kind, id)}/edit`, { method: 'POST', body: { edits: [], schema: JSON.parse(box.value) } });
    toast(t('Salvo'), 'ok');
    return true;
  } catch (e) { toast(e.message || t('JSON inválido'), 'err'); return false; }
}

async function mediaDialog(kind, id) {
  const list = h('div', { class: 'dt-media-list' });
  const input = h('input', { type: 'file', multiple: true, id: 'dt-media-file' });
  const paint = async () => {
    let items = [];
    try { items = (await api(`${itemUrl(kind, id)}/media`)).items || []; } catch (e) { toast(e.message, 'err'); }
    list.replaceChildren(...(items.length ? items.map((m) => h('div', { class: 'dt-media-card' },
      m.kind === 'image' && m.inline ? h('img', { class: 'dt-thumb', src: mediaSrc(kind, id, m.ref), alt: m.name, loading: 'lazy' }) : h('div', { class: 'dt-media-ic' }, icon(m.kind === 'audio' ? 'mic' : m.kind === 'video' ? 'film' : 'file', 22)),
      h('div', { class: 'small', style: { wordBreak: 'break-all' } }, m.name),
      h('div', { class: 'muted small' }, `${Math.max(1, Math.round(m.size / 1024))} KB`),
      h('div', { class: 'dt-actions' },
        h('button', { class: 'btn sm', type: 'button', title: t('Copiar a referência para usar numa célula'), onclick: async () => { try { await navigator.clipboard.writeText(m.ref); toast(t('Referência copiada: {r}', { r: m.ref }), 'ok'); } catch (e) { toast(m.ref); } } }, t('Copiar referência')),
        h('button', { class: 'btn sm ghost danger', type: 'button', onclick: async () => {
          if (!(await confirmDialog(t('Apagar «{n}»? Isso não pode ser desfeito.', { n: m.name }), true, t('Apagar')))) return;
          try { await api(`${itemUrl(kind, id)}/media/${encodeURIComponent(m.name)}`, { method: 'DELETE' }); await paint(); } catch (e) { toast(e.message, 'err'); }
        } }, icon('trash', 13))))) : [h('div', { class: 'muted' }, t('Nenhum arquivo ainda. Envie imagens, áudios, vídeos ou outros arquivos e use a referência «attachments/nome» nas células.'))]));
  };
  input.addEventListener('change', async () => {
    for (const f of Array.from(input.files || [])) { try { await uploadMedia(kind, id, f); } catch (e) { toast(f.name + ': ' + e.message, 'err'); } }
    input.value = '';
    await paint();
  });
  await paint();
  const body = h('div', { class: 'col', style: { gap: '10px', minWidth: 'min(720px,90vw)' } }, h('div', { class: 'row', style: { gap: '8px', alignItems: 'center' } }, input, h('span', { class: 'muted small' }, t('Até 25 MB por arquivo.'))), list);
  await modal(t('Mídia do item'), body, [{ label: t('Fechar'), value: 'close', cls: 'primary' }]);
}

// ------------------------------------------------------------------ mesclagem (no editor e nas abas)
export async function mergeDialog(items, preset, onChanged) {
  if (items.length < 2) { toast(t('Crie ao menos dois itens para mesclar.'), 'err'); return; }
  const label = (it) => `${it.name || it.id} (${kindName(it.kind)}, ${it.records || 0} ${t('registros')})`;
  const opts = items.map((it) => [it.kind + ':' + it.id, label(it)]);
  const tgtV = preset && items.some((i) => i.kind + ':' + i.id === preset) ? preset : opts[0][0];
  const srcV = (opts.find(([v]) => v !== tgtV) || opts[1])[0];
  const targetSel = select(opts, tgtV, () => {}, { id: 'dt-merge-target' });
  const sourceSel = select(opts, srcV, () => {}, { id: 'dt-merge-source' });
  const stratSel = select([['append', t('Juntar tudo (acrescentar os registros)')], ['upsert', t('Combinar por chave (atualizar os que já existem)')]], 'append', () => draw(), { id: 'dt-merge-strategy' });
  const conflictSel = select([['keep_target', t('Manter o destino (só preencher vazios)')], ['prefer_source', t('A origem vence nos conflitos')]], 'keep_target', () => {}, { id: 'dt-merge-conflict' });
  const dedupe = h('input', { type: 'checkbox', id: 'dt-merge-dedupe' });
  const keysBox = h('div', { class: 'dt-actions', id: 'dt-merge-keys' });
  const out = h('div', { class: 'small', id: 'dt-merge-out', style: { minHeight: '32px' } });
  const keyChecks = new Map();
  const draw = async () => {
    keysBox.parentElement && (keysBox.parentElement.style.display = stratSel.value === 'upsert' ? '' : 'none');
    conflictSel.parentElement && (conflictSel.parentElement.style.display = stratSel.value === 'upsert' ? '' : 'none');
    if (stratSel.value !== 'upsert') return;
    const [tk, ti] = targetSel.value.split(':');
    try {
      const r = await api(`${itemUrl(tk, ti)}/rows?limit=1`);
      keysBox.replaceChildren(...(r.columns || []).map((c) => {
        if (!keyChecks.has(c)) keyChecks.set(c, h('input', { type: 'checkbox', checked: /^(id|_id|uuid|email|url|source_url)$/i.test(c) }));
        return h('label', { class: 'chip', style: { cursor: 'pointer' } }, keyChecks.get(c), ' ' + c);
      }));
    } catch (e) { /* sem colunas ainda */ }
  };
  targetSel.addEventListener('change', draw);
  const body = h('div', { class: 'col', style: { gap: '8px', minWidth: 'min(560px,92vw)' } },
    h('p', { class: 'muted small', style: { margin: 0 } }, t('Mescla o item de origem no de destino: o destino é preservado e recebe os dados, os campos são unidos pelo nome e a mídia da origem vai junto.')),
    h('div', { class: 'field' }, h('label', { class: 'f' }, t('Destino')), targetSel),
    h('div', { class: 'field' }, h('label', { class: 'f' }, t('Origem')), sourceSel),
    h('div', { class: 'field' }, h('label', { class: 'f' }, t('Como mesclar')), stratSel),
    h('div', { class: 'field' }, h('label', { class: 'f' }, t('Campos-chave')), keysBox),
    h('div', { class: 'field' }, h('label', { class: 'f' }, t('Conflitos')), conflictSel),
    h('label', { class: 'row small', style: { gap: '6px', cursor: 'pointer' } }, dedupe, h('span', null, t('Remover registros repetidos no final'))),
    h('div', { class: 'dt-actions' }, h('button', { class: 'btn', id: 'dt-merge-preview', type: 'button', onclick: () => run(true) }, t('Ver prévia'))), out);
  const request = (dry) => {
    const [tk, ti] = targetSel.value.split(':'); const [sk, si] = sourceSel.value.split(':');
    if (tk === sk && ti === si) { toast(t('Escolha itens diferentes.'), 'err'); return null; }
    const keys = Array.from(keyChecks.entries()).filter(([, el]) => el.checked && keysBox.contains(el)).map(([c]) => c);
    return api(`${itemUrl(tk, ti)}/merge`, { method: 'POST', body: { source_kind: sk, source_id: si, strategy: stratSel.value, keys, conflict: conflictSel.value, dedupe: dedupe.checked, dry_run: dry } });
  };
  const run = async (dry) => {
    try {
      const p = request(dry); if (!p) return false;
      const r = await p;
      const m = dry ? r : r.merge;
      out.replaceChildren(h('b', null, dry ? t('Prévia: nada foi alterado.') : t('Mesclado.')), h('div', null, t('{a} acrescentado(s) · {u} atualizado(s) · {s} sem mudança · {d} repetido(s) removido(s) · total {n}', { a: m.added, u: m.updated, s: m.skipped, d: m.duplicates_removed, n: m.total })));
      return !dry;
    } catch (e) { toast(e.message, 'err'); return false; }
  };
  await draw();
  const res = await modal(t('Mesclar databases/datasets'), body, [{ label: t('Cancelar'), value: null }, { label: t('Mesclar'), value: 'ok', cls: 'primary' }]);
  if (res !== 'ok') return;
  if (await run(false)) { toast(t('Mesclado'), 'ok'); onChanged && onChanged(); }
}

// ------------------------------------------------------------------ o editor
export async function openEditor(kind, id, onChanged, allItems = []) {
  const S = { q: '', sort: '', dir: 'asc', offset: 0, limit: 50, data: null, selected: new Set(), changed: false };
  const title = h('input', { id: 'dt-item-name', class: 'dt-title', 'aria-label': t('Nome') });
  const desc = h('input', { id: 'dt-item-desc', placeholder: t('Descrição'), style: { flex: '1', minWidth: '200px' } });
  const tagBox = h('div', { class: 'grow' });
  const meta = h('div', { class: 'muted small', id: 'dt-item-meta' });
  const filter = h('input', { id: 'dt-item-filter', placeholder: t('Filtrar registros…'), style: { flex: '1', minWidth: '160px' } });
  const sizeSel = select(PAGE_SIZES.map((n) => [String(n), t('{n} por página', { n })]), String(S.limit), (v) => { S.limit = parseInt(v, 10); S.offset = 0; load(); }, { id: 'dt-page-size' });
  const info = h('span', { class: 'muted small', id: 'dt-pager-info' });
  const prev = h('button', { class: 'btn sm', id: 'dt-prev', type: 'button', onclick: () => { S.offset = Math.max(0, S.offset - S.limit); load(); } }, '‹');
  const next = h('button', { class: 'btn sm', id: 'dt-next', type: 'button', onclick: () => { S.offset += S.limit; load(); } }, '›');
  const tableBox = h('div', { class: 'dt-table-wrap dt-grid-wrap' });
  const delBtn = h('button', { class: 'btn sm danger', id: 'dt-del-rows', type: 'button', style: { display: 'none' } });

  const typeOf = (c) => ((S.data.schema.fields || []).find((f) => f.name === c) || {}).type || 'text';
  async function load(keepScroll) {
    const sc = tableBox.scrollTop;
    const qs = new URLSearchParams({ q: S.q, sort: S.sort, dir: S.dir, offset: S.offset, limit: S.limit });
    try { S.data = await api(`${itemUrl(kind, id)}/rows?${qs}`); } catch (e) { toast(e.message, 'err'); return; }
    if (S.offset >= S.data.matched && S.offset > 0) { S.offset = Math.max(0, Math.floor((S.data.matched - 1) / S.limit) * S.limit); return load(); }
    S.selected.clear();
    paint();
    if (keepScroll) tableBox.scrollTop = sc;
  }
  function paintHead() {
    const m = S.data.meta || {};
    if (document.activeElement !== title) title.value = m.name || id;
    if (document.activeElement !== desc) desc.value = m.description || '';
    meta.textContent = `${kindName(kind)} · ${S.data.total} ${t('registros')} · ${(S.data.schema.fields || []).length} ${t('campos')}`;
  }
  function paint() {
    paintHead();
    const cols = S.data.columns && S.data.columns.length ? S.data.columns : ['value'];
    const from = S.data.matched ? S.offset + 1 : 0;
    info.textContent = t('{a}–{b} de {c}', { a: from, b: Math.min(S.offset + S.limit, S.data.matched), c: S.data.matched }) + (S.data.matched !== S.data.total ? ' ' + t('(filtrado de {n})', { n: S.data.total }) : '');
    prev.disabled = S.offset <= 0;
    next.disabled = S.offset + S.limit >= S.data.matched;
    const head = h('tr', null, h('th', { class: 'dt-sel' }, h('input', { type: 'checkbox', id: 'dt-sel-all', 'aria-label': t('Selecionar todas'), onchange: (e) => { S.data.rows.forEach((r) => (e.target.checked ? S.selected.add(r.i) : S.selected.delete(r.i))); paintSel(); } })),
      ...cols.map((c) => h('th', null, h('div', { class: 'row', style: { gap: '4px', alignItems: 'center' } },
        h('button', { class: 'dt-th', type: 'button', title: t('Ordenar por {c}', { c }), onclick: () => { if (S.sort === c) S.dir = S.dir === 'asc' ? 'desc' : 'asc'; else { S.sort = c; S.dir = 'asc'; } S.offset = 0; load(); } },
          c, S.sort === c ? h('span', { class: 'muted' }, S.dir === 'asc' ? ' ▲' : ' ▼') : null),
        h('span', { class: 'chip dim' }, typeOf(c)),
        h('button', { class: 'btn ghost sm dt-colmenu', type: 'button', title: t('Opções da coluna'), onclick: () => columnDialog(c) }, '⋯')))));
    const body = S.data.rows.map((row) => {
      const tr = h('tr', { dataset: { i: row.i } }, h('td', { class: 'dt-sel' }, h('input', { type: 'checkbox', checked: S.selected.has(row.i), onchange: (e) => { if (e.target.checked) S.selected.add(row.i); else S.selected.delete(row.i); paintSel(); } })));
      cols.forEach((c) => {
        const ft = typeOf(c);
        const td = h('td', { class: 'dt-cell', dataset: { field: c }, title: t('Duplo clique para editar') }, renderCell(row.r && typeof row.r === 'object' ? row.r[c] : (c === 'value' ? row.r : ''), ft, kind, id));
        td.addEventListener('dblclick', () => editCell(td, row, c, ft));
        tr.appendChild(td);
      });
      return tr;
    });
    if (!body.length) body.push(h('tr', null, h('td', { colspan: cols.length + 1, class: 'muted', style: { padding: '14px' } }, S.data.total ? t('Nenhum registro corresponde ao filtro.') : t('Ainda não há registros. Use «+ Linha», importe um arquivo (aba Upgrade) ou gere dados sintéticos.'))));
    tableBox.replaceChildren(h('table', { class: 'dt-table' }, h('thead', null, head), h('tbody', null, ...body)));
    paintSel();
  }
  function paintSel() {
    const n = S.selected.size;
    delBtn.style.display = n ? '' : 'none';
    delBtn.replaceChildren(icon('trash', 13), t('Apagar {n} selecionada(s)', { n }));
  }
  function editCell(td, row, field, ftype) {
    if (td.querySelector('.dt-edit')) return;
    const cur = row.r && typeof row.r === 'object' ? row.r[field] : (field === 'value' ? row.r : '');
    const raw = cur === null || cur === undefined ? '' : (typeof cur === 'object' ? JSON.stringify(cur, null, 2) : String(cur));
    const multi = ftype === 'json' || raw.length > 60 || raw.includes('\n');
    const el = multi ? h('textarea', { class: 'dt-edit', rows: Math.min(8, raw.split('\n').length + 1) }, raw) : h('input', { class: 'dt-edit', value: raw });
    let done = false;
    const finish = async (commit) => {
      if (done) return; done = true;
      if (!commit || el.value === raw) { td.replaceChildren(renderCell(cur, ftype, kind, id)); return; }
      const value = parseInput(el.value, ftype);
      try {
        await api(`${itemUrl(kind, id)}/edit`, { method: 'POST', body: { edits: [{ op: 'set', i: row.i, field, value }] } });
        if (row.r && typeof row.r === 'object') row.r[field] = value;
        S.changed = true;
        td.replaceChildren(renderCell(value, ftype, kind, id));
      } catch (e) { toast(e.message, 'err'); td.replaceChildren(renderCell(cur, ftype, kind, id)); }
    };
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); finish(false); }
      else if (e.key === 'Enter' && (!multi || e.ctrlKey || e.metaKey)) { e.preventDefault(); finish(true); }
    });
    el.addEventListener('blur', () => setTimeout(() => finish(true), 120));
    const kids = [el];
    if (['image', 'audio', 'video', 'file'].includes(ftype)) {
      const up = h('input', { type: 'file', style: { display: 'none' } });
      up.addEventListener('change', async () => { const f = up.files && up.files[0]; if (!f) return; try { const r = await uploadMedia(kind, id, f); el.value = r.ref; el.focus(); } catch (e) { toast(e.message, 'err'); } });
      kids.push(up, h('button', { class: 'btn sm', type: 'button', onmousedown: (e) => e.preventDefault(), onclick: () => up.click() }, icon('upload', 12), t('Enviar arquivo')));
    }
    td.replaceChildren(...kids);
    el.focus();
  }
  async function columnDialog(c) {
    const ft = typeOf(c);
    const nameIn = h('input', { id: 'dt-col-name', value: c });
    const typeSel = select(FIELD_TYPES.map((x) => [x, x]), ft, () => {}, { id: 'dt-col-type' });
    const body = h('div', { class: 'col', style: { gap: '8px', minWidth: 'min(420px,90vw)' } },
      h('div', { class: 'field' }, h('label', { class: 'f' }, t('Nome da coluna')), nameIn),
      h('div', { class: 'field' }, h('label', { class: 'f' }, t('Tipo')), typeSel),
      h('div', { class: 'muted small' }, t('Mudar o tipo converte os valores que dá; o que não converte fica como estava.')),
      h('div', { class: 'dt-actions' }, h('button', { class: 'btn danger', id: 'dt-col-remove', type: 'button', onclick: async () => {
        if (!(await confirmDialog(t('Remover a coluna «{c}» de todos os registros? O estado atual fica no histórico.', { c }), true, t('Remover')))) return;
        try { await api(`${itemUrl(kind, id)}/columns`, { method: 'POST', body: { op: 'remove', name: c } }); S.changed = true; document.querySelectorAll('.modal-bg').forEach((m, i, a) => { if (i === a.length - 1) m.remove(); }); await load(true); } catch (e) { toast(e.message, 'err'); }
      } }, icon('trash', 13), t('Remover coluna'))));
    const v = await modal(t('Coluna «{c}»', { c }), body, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]);
    if (v !== 'ok') return;
    try {
      let name = c;
      if (nameIn.value.trim() && nameIn.value.trim() !== c) { await api(`${itemUrl(kind, id)}/columns`, { method: 'POST', body: { op: 'rename', name: c, new_name: nameIn.value.trim() } }); name = nameIn.value.trim().replace(/ /g, '_'); }
      if (typeSel.value !== ft) { const r = await api(`${itemUrl(kind, id)}/columns`, { method: 'POST', body: { op: 'retype', name, type: typeSel.value } }); if (r.failed) toast(t('{n} valor(es) não converteram e foram mantidos.', { n: r.failed })); }
      S.changed = true; await load(true);
    } catch (e) { toast(e.message, 'err'); }
  }
  async function addColumn() {
    const nameIn = h('input', { id: 'dt-newcol-name', placeholder: t('nome_da_coluna') });
    const typeSel = select(FIELD_TYPES.map((x) => [x, x]), 'text', () => {}, { id: 'dt-newcol-type' });
    const def = h('input', { id: 'dt-newcol-default', placeholder: t('Valor inicial (opcional)') });
    const body = h('div', { class: 'col', style: { gap: '8px', minWidth: 'min(420px,90vw)' } }, h('div', { class: 'field' }, h('label', { class: 'f' }, t('Nome da coluna')), nameIn), h('div', { class: 'field' }, h('label', { class: 'f' }, t('Tipo')), typeSel), h('div', { class: 'field' }, h('label', { class: 'f' }, t('Valor inicial')), def));
    const v = await modal(t('Nova coluna'), body, [{ label: t('Cancelar'), value: null }, { label: t('Adicionar'), value: 'ok', cls: 'primary' }]);
    if (v !== 'ok') return;
    try { await api(`${itemUrl(kind, id)}/columns`, { method: 'POST', body: { op: 'add', name: nameIn.value, type: typeSel.value, default: def.value === '' ? null : parseInput(def.value, typeSel.value) } }); S.changed = true; await load(true); } catch (e) { toast(e.message, 'err'); }
  }
  async function meta_save() {
    try {
      await api(itemUrl(kind, id), { method: 'PUT', body: { name: title.value, description: desc.value, tags: tags.get() } });
      S.changed = true;
    } catch (e) { toast(e.message, 'err'); }
  }

  filter.addEventListener('input', () => { clearTimeout(filter._t); filter._t = setTimeout(() => { S.q = filter.value.trim(); S.offset = 0; load(); }, 250); });
  title.addEventListener('change', meta_save);
  desc.addEventListener('change', meta_save);
  await load();
  if (!S.data) return;
  const tags = tagsInput((S.data.meta || {}).tags || [], () => meta_save(), t('adicionar tag…'));
  tagBox.appendChild(tags);
  const reloadAfter = async (p) => { if (await p) { S.changed = true; S.offset = 0; await load(); } };
  const btn = (id_, ic, label, fn) => h('button', { class: 'btn sm', id: id_, type: 'button', onclick: fn }, icon(ic, 13), label);
  const bar = h('div', { class: 'dt-actions dt-editor-bar' },
    btn('dt-add-row', 'plus', t('Linha'), async () => { try { await api(`${itemUrl(kind, id)}/edit`, { method: 'POST', body: { edits: [{ op: 'insert', record: {} }] } }); S.changed = true; S.q = ''; filter.value = ''; S.sort = ''; await load(); S.offset = Math.max(0, Math.floor((S.data.matched - 1) / S.limit) * S.limit); await load(); } catch (e) { toast(e.message, 'err'); } }),
    btn('dt-add-col', 'plus', t('Coluna'), addColumn),
    btn('dt-btn-profile', 'layers', t('Perfil dos dados'), () => profileDialog(kind, id)),
    btn('dt-btn-clean', 'sparkle', t('Limpar'), () => reloadAfter(cleanDialog(kind, id))),
    btn('dt-btn-dedupe', 'copy', t('Remover duplicados'), () => reloadAfter(dedupeDialog(kind, id))),
    btn('dt-btn-merge', 'layers', t('Mesclar'), async () => { await mergeDialog(allItems.length ? allItems : (await api('/api/data/items')).items || [], kind + ':' + id, async () => { S.changed = true; await load(); }); }),
    btn('dt-btn-media', 'image', t('Mídia'), () => mediaDialog(kind, id)),
    btn('dt-btn-schema', 'edit', t('Schema'), () => reloadAfter(schemaDialog(kind, id, S.data.schema))),
    btn('dt-btn-history', 'refresh', t('Histórico'), () => reloadAfter(historyDialog(kind, id))),
    delBtn);
  delBtn.addEventListener('click', async () => {
    const idx = Array.from(S.selected);
    if (!(await confirmDialog(t('Apagar {n} registro(s)? O estado atual fica no histórico.', { n: idx.length }), true, t('Apagar')))) return;
    try { await api(`${itemUrl(kind, id)}/edit`, { method: 'POST', body: { edits: [{ op: 'delete', i: idx }] } }); S.changed = true; await load(true); } catch (e) { toast(e.message, 'err'); }
  });
  const body = h('div', { class: 'col dt-editor', style: { gap: '10px', width: 'min(1180px,94vw)' } },
    h('div', { class: 'row', style: { gap: '8px', alignItems: 'center', flexWrap: 'wrap' } }, title, meta),
    h('div', { class: 'row', style: { gap: '8px', alignItems: 'center', flexWrap: 'wrap' } }, desc, tagBox),
    bar,
    h('div', { class: 'row', style: { gap: '8px', alignItems: 'center', flexWrap: 'wrap' } }, filter, sizeSel, prev, info, next),
    tableBox);
  await modal(kindName(kind), body, [{ label: t('Fechar'), value: 'close', cls: 'primary' }]);
  if (S.changed && onChanged) onChanged();
}
