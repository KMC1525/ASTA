// Modo Data — databases e datasets multimodais com IA.
// Abas: main, databases, datasets, synthetic (dados sintéticos), scraping (web scraping), upgrade, export.
import { api, events } from '../api.js';
import { t } from '../i18n.js';
import { go, state } from '../main.js';
import { teamPicker } from '../team_ui.js';
import { confirmDialog, h, icon, modal, select, toast } from '../ui.js';
import { createComposer } from './composer.js';

const TABS = [
  ['main', 'Main', 'home'],
  ['databases', 'Databases', 'storage'],
  ['datasets', 'Datasets', 'folder'],
  ['synthetic_data', 'Synthetic data', 'sparkle'],
  ['web_scraping', 'Web scraping', 'globe'],
  ['upgrade', 'Upgrade', 'refresh'],
  ['export', 'Export', 'download'],
];
const TAB_IDS = TABS.map((x) => x[0]);

const EXPORT_FORMATS = [
  ['json', 'JSON'], ['jsonl', 'JSONL / NDJSON'], ['ndjson', 'NDJSON'], ['csv', 'CSV'], ['tsv', 'TSV'],
  ['xml', 'XML'], ['html', 'HTML'], ['md', 'Markdown'], ['sqlite', 'SQLite (.db)'],
];
const SYNTH_MODES = [['single', t('Um tipo de dado')], ['multi', t('Vários tipos/modalidades')]];
const MAX_SYNTH = 5000;
const MAX_URLS = 500;

function parse() {
  const m = location.hash.match(/^#\/data(?:\/([\w-]+))?/);
  const tab = m && TAB_IDS.includes(m[1]) ? m[1] : 'main';
  return { tab };
}

async function loadItems(kind) {
  const q = kind ? '?kind=' + encodeURIComponent(kind) : '';
  const r = await api('/api/data/items' + q);
  return r.items || [];
}

function itemLabel(it) {
  return `${it.name || it.id} (${it.kind === 'database' ? t('Database') : t('Dataset')}, ${it.records || 0} ${t('registros')})`;
}

function renderItemCard(it, onChanged) {
  const open = () => go('data', { open: { kind: it.kind, id: it.id } });
  return h('div', { class: 'dt-card' },
    h('div', { class: 'nm' }, it.name || it.id),
    h('div', { class: 'dt-meta' }, (it.kind === 'database' ? t('Database') : t('Dataset')) + ' · ' + (it.records || 0) + ' ' + t('registros') + ' · ' + (it.fields || 0) + ' ' + t('campos')),
    it.description ? h('div', { class: 'small muted' }, it.description) : null,
    (it.tags && it.tags.length) ? h('div', { class: 'dt-tags' }, ...it.tags.map((x) => h('span', { class: 'chip' }, x))) : null,
    h('div', { class: 'dt-actions' },
      h('button', { class: 'btn sm', type: 'button', onclick: open }, icon('edit', 13), t('Abrir')),
      h('button', { class: 'btn sm ghost', type: 'button', onclick: async () => {
        try { await api(`/api/data/items/${it.kind}/${it.id}/duplicate`, { method: 'POST', body: {} }); toast(t('Duplicado'), 'ok'); onChanged && onChanged(); } catch (e) { toast(e.message, 'err'); }
      } }, icon('copy', 13), t('Duplicar')),
      h('button', { class: 'btn sm ghost danger', type: 'button', onclick: async () => {
        if (!(await confirmDialog(t('Apagar «{n}»? Isso não pode ser desfeito.', { n: it.name || it.id }), true, t('Apagar')))) return;
        try { await api(`/api/data/items/${it.kind}/${it.id}`, { method: 'DELETE' }); toast(t('Apagado'), 'ok'); onChanged && onChanged(); } catch (e) { toast(e.message, 'err'); }
      } }, icon('trash', 13), t('Apagar'))));
}

// ------------------------------------------------------------------ tabela de registros (visualizar/organizar)
function recordsTable(records, schema, opt = {}) {
  const recs = Array.isArray(records) ? records : [];
  const cols = [];
  const seen = new Set();
  const sfields = (schema && schema.fields) || [];
  for (const f of sfields) { if (f && f.name && !seen.has(f.name)) { seen.add(f.name); cols.push(f.name); } }
  for (const r of recs.slice(0, 50)) {
    if (r && typeof r === 'object' && !Array.isArray(r)) for (const k of Object.keys(r)) { if (!seen.has(k)) { seen.add(k); cols.push(k); } }
  }
  if (!cols.length) cols.push('value');
  const sortKey = opt.sortKey || '';
  const dir = opt.sortDir === 'desc' ? -1 : 1;
  const cell = (r, c) => {
    let v = r && typeof r === 'object' && !Array.isArray(r) ? r[c] : (c === 'value' ? r : '');
    if (v && typeof v === 'object') { try { v = JSON.stringify(v); } catch (e) { v = String(v); } }
    return v == null ? '' : String(v);
  };
  const shown = [...recs].sort((a, b) => {
    if (!sortKey) return 0;
    const x = cell(a, sortKey), y = cell(b, sortKey);
    const nx = Number(x), ny = Number(y);
    if (x !== '' && y !== '' && !isNaN(nx) && !isNaN(ny)) return (nx - ny) * dir;
    return x.localeCompare(y, undefined, { numeric: true }) * dir;
  }).slice(0, opt.limit || 200);
  const head = h('tr', null, ...cols.map((c) => h('th', null,
    h('button', { class: 'dt-th', type: 'button', title: t('Ordenar por {c}', { c }), onclick: () => opt.onSort && opt.onSort(c) },
      c, sortKey === c ? h('span', { class: 'muted' }, dir === 1 ? ' ▲' : ' ▼') : null))));
  const body = shown.map((r) => h('tr', null, ...cols.map((c) => h('td', null, h('div', { class: 'dt-rec' }, cell(r, c))))));
  return h('div', { class: 'dt-table-wrap' }, h('table', { class: 'dt-table' }, h('thead', null, head), h('tbody', null, ...body)));
}

// ------------------------------------------------------------------ qualidade: perfil e duplicados (v0.23)
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
  try { p = await api(`/api/data/items/${kind}/${id}/profile`); } catch (e) { toast(e.message, 'err'); return; }
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

// devolve true se algo foi removido (o chamador recarrega)
async function dedupeDialog(kind, id) {
  let prev;
  try { prev = await api(`/api/data/items/${kind}/${id}/dedupe`, { method: 'POST', body: { apply: false } }); } catch (e) { toast(e.message, 'err'); return false; }
  if (!prev.removed) { toast(t('Nenhum registro repetido.'), 'ok'); return false; }
  const body = h('div', { class: 'col', style: { gap: '8px' } },
    h('div', null, t('{n} de {m} registro(s) são repetidos e serão removidos; o primeiro de cada grupo fica.', { n: prev.removed, m: prev.total })),
    h('div', { class: 'muted small' }, t('Campos comparados: {x}', { x: (prev.keys || []).join(', ') })),
    h('div', { class: 'muted small' }, t('O estado atual fica no histórico: dá para restaurar.')));
  const v = await modal(t('Remover duplicados'), body, [{ label: t('Cancelar'), value: false }, { label: t('Remover duplicados'), value: true, cls: 'primary' }]);
  if (v !== true) return false;
  try {
    const done = await api(`/api/data/items/${kind}/${id}/dedupe`, { method: 'POST', body: { apply: true } });
    toast(t('{n} registro(s) removido(s)', { n: done.removed }), 'ok');
    return !!done.applied;
  } catch (e) { toast(e.message, 'err'); return false; }
}

// ------------------------------------------------------------------ diálogo do item (ver/editar/organizar)
async function openItemDialog(kind, id, onChanged) {
  let data;
  try { data = await api(`/api/data/items/${kind}/${id}`); } catch (e) { toast(e.message, 'err'); return; }
  const filter = h('input', { placeholder: t('Filtrar registros…'), style: { flex: '1', minWidth: '160px' } });
  let sortKey = '';
  let sortDir = 'asc';
  const tableBox = h('div');
  const info = h('div', { class: 'dt-kv' },
    h('div', { class: 'muted' }, t('Tipo')), h('div', null, kind === 'database' ? t('Database') : t('Dataset')),
    h('div', { class: 'muted' }, t('Registros')), h('div', null, String((data.records || []).length)),
    h('div', { class: 'muted' }, t('Campos')), h('div', null, String(((data.schema || {}).fields || []).length)));
  const recs = h('textarea', { style: { width: '100%', minHeight: '220px', fontFamily: 'monospace', fontSize: '12px' } }, JSON.stringify(data.records || [], null, 2));
  const schemaBox = h('textarea', { style: { width: '100%', minHeight: '120px', fontFamily: 'monospace', fontSize: '12px' } }, JSON.stringify(data.schema || { fields: [] }, null, 2));

  const paint = () => {
    const all = data.records || [];
    const q = (filter.value || '').trim().toLowerCase();
    const rows = q ? all.filter((r) => JSON.stringify(r).toLowerCase().includes(q)) : all;
    tableBox.replaceChildren(
      h('div', { class: 'row', style: { gap: '8px', alignItems: 'center', marginBottom: '6px', flexWrap: 'wrap' } },
        filter,
        h('span', { class: 'muted small' }, t('{n} de {m} registro(s)', { n: rows.length, m: all.length }))),
      recordsTable(rows, data.schema || {}, {
        sortKey, sortDir,
        onSort: (c) => { if (sortKey === c) sortDir = sortDir === 'asc' ? 'desc' : 'asc'; else { sortKey = c; sortDir = 'asc'; } paint(); },
      }));
  };
  filter.addEventListener('input', paint);
  paint();

  const body = h('div', { class: 'col', style: { gap: '10px', minWidth: 'min(900px,90vw)' } },
    h('h3', { style: { margin: 0 } }, (data.meta && data.meta.name) || id), info,
    h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap' } },
      h('button', { class: 'btn', onclick: () => profileDialog(kind, id) }, t('Perfil dos dados')),
      h('button', { class: 'btn', onclick: async () => {
        if (!(await dedupeDialog(kind, id))) return;
        try {
          data = await api(`/api/data/items/${kind}/${id}`);
          recs.value = JSON.stringify(data.records || [], null, 2);
          info.children[3].textContent = String((data.records || []).length);
          paint(); onChanged && onChanged();
        } catch (e) { toast(e.message, 'err'); }
      } }, t('Remover duplicados'))),
    h('b', null, t('Visualização (amostra)')), tableBox,
    h('b', null, t('Registros (JSON)')), recs,
    h('b', null, t('Schema (JSON)')), schemaBox);
  const res = await modal(t('Database/Dataset'), body, [
    { label: t('Fechar'), value: 'close' },
    { label: t('Salvar alterações'), value: 'save', cls: 'primary' },
  ]);
  if (res !== 'save') return;
  try {
    const newRecs = JSON.parse(recs.value || '[]');
    const newSchema = JSON.parse(schemaBox.value || '{"fields":[]}');
    await api(`/api/data/items/${kind}/${id}/records`, { method: 'POST', body: { records: Array.isArray(newRecs) ? newRecs : [], schema: newSchema, mode: 'replace', label: 'manual' } });
    toast(t('Salvo'), 'ok'); onChanged && onChanged();
  } catch (e) { toast(e.message || t('JSON inválido'), 'err'); }
}

async function createDialog(defaultKind, onChanged) {
  const cfg = (state.settings && state.settings.data) || {};
  const name = h('input', { placeholder: t('Nome'), maxlength: 100 });
  const desc = h('input', { placeholder: t('Descrição (opcional)'), maxlength: 400 });
  const kindSel = select([['dataset', t('Dataset')], ['database', t('Database')]], defaultKind || cfg.default_kind || 'dataset', () => {}, { id: 'dt-new-kind' });
  const body = h('div', { class: 'col', style: { gap: '8px', minWidth: '420px' } },
    h('div', { class: 'field' }, h('label', { class: 'f' }, t('Tipo')), kindSel),
    h('div', { class: 'field' }, h('label', { class: 'f' }, t('Nome')), name),
    h('div', { class: 'field' }, h('label', { class: 'f' }, t('Descrição')), desc));
  const res = await modal(t('Novo database/dataset'), body, [{ label: t('Cancelar'), value: null }, { label: t('Criar'), value: 'ok', cls: 'primary' }]);
  if (res !== 'ok') return;
  try {
    const item = await api('/api/data/items', { method: 'POST', body: { kind: kindSel.value, name: name.value.trim(), description: desc.value.trim() } });
    toast(t('Criado'), 'ok'); onChanged && onChanged(item);
    if (item && item.kind && item.id) openItemDialog(item.kind, item.id, onChanged);
  } catch (e) { toast(e.message, 'err'); }
}

async function mergeDialog(onChanged) {
  const items = await loadItems();
  if (items.length < 2) return toast(t('Crie ao menos dois itens para mesclar.'), 'err');
  const opts = items.map((it) => [it.kind + ':' + it.id, itemLabel(it)]);
  const targetSel = select(opts, opts[0][0], () => {});
  const sourceSel = select(opts, opts[1][0], () => {});
  const body = h('div', { class: 'col', style: { gap: '8px', minWidth: '480px' } },
    h('p', { class: 'muted small', style: { margin: 0 } }, t('Mescla os registros e campos do item de origem no item de destino (o destino é preservado e recebe os dados).')),
    h('div', { class: 'field' }, h('label', { class: 'f' }, t('Destino')), targetSel),
    h('div', { class: 'field' }, h('label', { class: 'f' }, t('Origem')), sourceSel));
  if (await modal(t('Mesclar databases/datasets'), body, [{ label: t('Cancelar'), value: null }, { label: t('Mesclar'), value: 'ok', cls: 'primary' }]) !== 'ok') return;
  const [tk, tid] = targetSel.value.split(':');
  const [sk, sid] = sourceSel.value.split(':');
  if (tk === sk && tid === sid) return toast(t('Escolha itens diferentes.'), 'err');
  try {
    await api(`/api/data/items/${tk}/${tid}/merge`, { method: 'POST', body: { source_kind: sk, source_id: sid } });
    toast(t('Mesclado'), 'ok'); onChanged && onChanged();
  } catch (e) { toast(e.message, 'err'); }
}

function jobWatcher(jobId, onDone) {
  const box = h('div', { class: 'muted small' }, t('Executando...'));
  const bar = h('div', { class: 'dt-bar' }, h('i'));
  const wrap = h('div', { class: 'col', style: { gap: '6px' } }, box, bar);
  // o EventSource entrega TODOS os eventos ao mesmo callback; o tipo vem em `ev.type`
  events(`/api/jobs/${jobId}/events`, (ev) => {
    if (ev.type === 'stage') { box.textContent = ev.message || ev.stage || t('Executando...'); }
    else if (ev.type === 'progress') {
      if (ev.message) box.textContent = ev.message;
      if (ev.total) bar.firstChild.style.width = Math.round((ev.done / ev.total) * 100) + '%';
    }
    else if (ev.type === 'done') { box.textContent = t('Concluído.'); bar.firstChild.style.width = '100%'; toast(t('Concluído'), 'ok'); onDone && onDone(ev); }
    else if (ev.type === 'error') { box.textContent = ev.error || t('Erro'); toast(ev.error || t('Erro'), 'err'); onDone && onDone(ev); }
  });
  return wrap;
}

// ------------------------------------------------------------------ composição do prompt (multimodal: anexos)
function promptComposer(placeholder, rows = 5) {
  const cmp = createComposer({
    placeholder,
    sendLabel: t('Enviar'),
    sendTitle: t('Enviar'),
    allowEmpty: false,
    onSend: () => {},
  });
  cmp.ta.rows = rows;   // o compositor fixa 2 linhas; aqui o prompt merece mais espaço
  cmp.el.classList.add('dt-composer');
  return cmp;
}

export default async function render(root, ctx) {
  const { tab } = parse();
  const cfg = Object.assign({ agents: 1, effort: 'high', default_kind: 'dataset', synthetic_count: 20, synthetic_mode: 'single' }, (state.settings || {}).data || {});
  let items = await loadItems().catch(() => []);

  async function refresh() { items = await loadItems().catch(() => []); paint(); }
  const body = h('div', { id: 'dt-body' });

  async function paint() {
    // open requested item dialog
    if (ctx && ctx.open && ctx.open.kind && ctx.open.id) {
      const o = ctx.open; ctx.open = null;
      await openItemDialog(o.kind, o.id, refresh);
    }
    if (tab === 'main') return paintMain();
    if (tab === 'databases') return paintKind('database');
    if (tab === 'datasets') return paintKind('dataset');
    if (tab === 'synthetic_data') return paintSynthetic();
    if (tab === 'web_scraping') return paintScraping();
    if (tab === 'upgrade') return paintUpgrade();
    if (tab === 'export') return paintExport();
  }

  function paintMain() {
    const grid = h('div', { class: 'dt-grid' }, ...items.map((it) => renderItemCard(it, refresh)));
    body.replaceChildren(
      h('div', { class: 'dt-section' },
        h('h2', { style: { marginTop: 0 } }, t('Data')),
        h('p', { class: 'muted' }, t('Crie, gere, gerencie, edite, visualize, organize e mescle databases e datasets multimodais com ajuda de agentes de IA. Gere dados sintéticos, faça web scraping open source, importe/melhore (upgrade) e exporte em vários formatos preservando a estrutura.')),
        h('div', { class: 'dt-actions', style: { marginTop: '8px' } },
          h('button', { class: 'btn primary', type: 'button', onclick: () => createDialog(cfg.default_kind, refresh) }, icon('plus', 14), t('Novo database/dataset')),
          h('button', { class: 'btn', type: 'button', onclick: () => mergeDialog(refresh) }, icon('layers', 14), t('Mesclar')),
          h('button', { class: 'btn', type: 'button', onclick: refresh }, icon('refresh', 14), t('Atualizar')))),
      h('h3', null, t('Todos os itens')),
      items.length ? grid : h('div', { class: 'muted' }, t('Nenhum database ou dataset ainda. Crie um novo para começar.')));
  }

  function paintKind(kind) {
    const list = items.filter((it) => it.kind === kind);
    const grid = h('div', { class: 'dt-grid' }, ...list.map((it) => renderItemCard(it, refresh)));
    body.replaceChildren(
      h('div', { class: 'row', style: { justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' } },
        h('h2', { style: { margin: 0 } }, kind === 'database' ? t('Databases') : t('Datasets')),
        h('div', { class: 'dt-actions' },
          h('button', { class: 'btn primary', type: 'button', onclick: () => createDialog(kind, refresh) }, icon('plus', 14), t('Novo')),
          h('button', { class: 'btn', type: 'button', onclick: () => mergeDialog(refresh) }, icon('layers', 14), t('Mesclar')))),
      list.length ? grid : h('div', { class: 'muted' }, kind === 'database' ? t('Nenhum database ainda.') : t('Nenhum dataset ainda.')));
  }

  function itemSelect(list, id) {
    const opts = list.length ? list.map((it) => [it.kind + ':' + it.id, itemLabel(it)]) : [['', t('Nenhum item disponível')]];
    return select(opts, opts[0][0], () => {}, { id });
  }

  function paintSynthetic() {
    const sel = itemSelect(items, 'dt-synth-item');
    const cmp = promptComposer(t('Descreva os dados sintéticos que deseja gerar (use prompts multimodais; anexe arquivos/imagens e cite modalidades).'), 6);
    const count = h('input', { type: 'number', min: 1, max: MAX_SYNTH, value: cfg.synthetic_count || 20 });
    const modeSel = select(SYNTH_MODES, cfg.synthetic_mode || 'single', () => {}, { id: 'dt-synth-mode' });
    const teamCfg = { agents: cfg.agents || 1, effort: cfg.effort || 'high' };
    const picker = teamPicker(teamCfg, () => {}, { id: 'dt-synth-team', defaultEffort: 'high' });
    const status = h('div');
    const run = async () => {
      if (!sel.value) return toast(t('Selecione um database/dataset.'), 'err');
      if (!cmp.text().trim()) return toast(t('Escreva o prompt de geração.'), 'err');
      const [k, id] = sel.value.split(':');
      const tm = picker.get ? picker.get() : teamCfg;
      const n = Math.max(1, Math.min(parseInt(count.value || '20', 10) || 20, MAX_SYNTH));
      try {
        const r = await api(`/api/data/items/${k}/${id}/synthetic`, {
          method: 'POST',
          body: { prompt: cmp.text(), count: n, mode: modeSel.value, team: tm, attachment_ids: cmp.fileIds() },
        });
        status.replaceChildren(jobWatcher(r.job_id, refresh));
      } catch (e) { toast(e.message, 'err'); }
    };
    cmp.configure({ onSend: run });
    body.replaceChildren(
      h('div', { class: 'dt-section col', style: { gap: '10px' } },
        h('h2', { style: { margin: 0 } }, t('Synthetic data')),
        h('p', { class: 'muted small', style: { margin: 0 } }, t('Gere dados sintéticos em massa com prompts multimodais e agentes de IA para databases e datasets (um tipo ou vários tipos/modalidades).')),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Destino (database/dataset)')), sel),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Prompt')), cmp.el),
        h('div', { class: 'grid2' },
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Quantidade')), count),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Modo')), modeSel)),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Equipe de agentes')), picker.el),
        h('div', { class: 'dt-actions' }, h('button', { class: 'btn primary', type: 'button', onclick: run }, icon('sparkle', 14), t('Gerar dados sintéticos'))),
        status));
  }

  function paintScraping() {
    const sel = itemSelect(items, 'dt-scrape-item');
    const urls = h('textarea', { placeholder: t('Um link por linha (sites ou qualquer tipo de link http/https).'), rows: 6, style: { width: '100%' } });
    const cmp = promptComposer(t('O que extrair/estruturar a partir das páginas (prompt multimodal de extração).'), 4);
    const teamCfg = { agents: cfg.agents || 1, effort: cfg.effort || 'high' };
    const picker = teamPicker(teamCfg, () => {}, { id: 'dt-scrape-team', defaultEffort: 'high' });
    const status = h('div');
    const ack = h('input', { type: 'checkbox', id: 'dt-scrape-ack' });
    const run = async () => {
      if (!sel.value) return toast(t('Selecione um database/dataset.'), 'err');
      if (!ack.checked) return toast(t('Confirme o aviso de uso open source para continuar.'), 'err');
      const list = urls.value.split(/\n+/).map((s) => s.trim()).filter(Boolean).slice(0, MAX_URLS);
      if (!list.length) return toast(t('Informe ao menos um link.'), 'err');
      const [k, id] = sel.value.split(':');
      const tm = picker.get ? picker.get() : teamCfg;
      try {
        const r = await api(`/api/data/items/${k}/${id}/scrape`, {
          method: 'POST',
          body: { urls: list, prompt: cmp.text(), team: tm, ack: true, attachment_ids: cmp.fileIds() },
        });
        status.replaceChildren(jobWatcher(r.job_id, refresh));
      } catch (e) { toast(e.message, 'err'); }
    };
    cmp.configure({ onSend: run });
    body.replaceChildren(
      h('div', { class: 'dt-section col', style: { gap: '10px' } },
        h('h2', { style: { margin: 0 } }, t('Web scraping')),
        h('div', { class: 'dt-warn' },
          h('b', null, t('Aviso: somente uso open source. Não usar para uso comercial.')),
          h('div', { class: 'small', style: { marginTop: '4px' } }, t('Respeite os termos de uso, robots.txt, leis aplicáveis e os direitos dos sites/fontes. Use apenas para fins open source e não comerciais.')),
          h('label', { class: 'row small', style: { marginTop: '8px', gap: '6px', cursor: 'pointer' } },
            ack, h('span', null, t('Li o aviso e vou usar apenas para fins open source e não comerciais.')))),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Destino (database/dataset)')), sel),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Links (um por linha)')), urls),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Prompt de extração')), cmp.el),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Equipe de agentes')), picker.el),
        h('div', { class: 'dt-actions' }, h('button', { class: 'btn primary', type: 'button', onclick: run }, icon('globe', 14), t('Fazer scraping e extrair'))),
        status));
  }

  function paintUpgrade() {
    const sel = itemSelect(items, 'dt-up-item');
    const fileIn = h('input', { type: 'file', accept: '.json,.jsonl,.ndjson,.csv,.tsv,.xml' });
    const kindSel = select([['dataset', t('Dataset')], ['database', t('Database')]], cfg.default_kind || 'dataset', () => {}, { id: 'dt-up-kind' });
    const cmp = promptComposer(t('Como melhorar/enriquecer? (opcional). Você pode pedir novos campos, limpeza, normalização ou mais dados.'), 4);
    const count = h('input', { type: 'number', min: 0, max: MAX_SYNTH, value: 0 });
    const modeSel = select(SYNTH_MODES, cfg.synthetic_mode || 'single', () => {}, { id: 'dt-up-mode' });
    const actionSel = select([['enrich', t('Melhorar/enriquecer registros existentes')], ['generate', t('Gerar e adicionar mais dados sintéticos')]], 'enrich', () => {}, { id: 'dt-up-action' });
    const teamCfg = { agents: cfg.agents || 1, effort: cfg.effort || 'high' };
    const picker = teamPicker(teamCfg, () => {}, { id: 'dt-up-team', defaultEffort: 'high' });
    const status = h('div');
    const importNew = async () => {
      const f = fileIn.files && fileIn.files[0];
      if (!f) return toast(t('Selecione um arquivo para importar.'), 'err');
      try {
        const raw = await f.arrayBuffer();
        const r = await fetch(`/api/data/upgrade/import?kind=${encodeURIComponent(kindSel.value)}&item_name=${encodeURIComponent(f.name.replace(/\.[^.]+$/, ''))}&name=${encodeURIComponent(f.name)}`, { method: 'POST', headers: { 'X-Filename': encodeURIComponent(f.name) }, body: raw });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || t('Falha ao importar'));
        toast(t('Importado'), 'ok'); await refresh();
      } catch (e) { toast(e.message, 'err'); }
    };
    // importa dentro de um item que já existe (soma os registros e acrescenta as colunas ao schema)
    const importInto = async () => {
      const f = fileIn.files && fileIn.files[0];
      if (!f) return toast(t('Selecione um arquivo para importar.'), 'err');
      if (!sel.value) return toast(t('Selecione um database/dataset para melhorar.'), 'err');
      const [k, id] = sel.value.split(':');
      try {
        const raw = await f.arrayBuffer();
        const r = await fetch(`/api/data/items/${k}/${id}/import?mode=append&name=${encodeURIComponent(f.name)}`, { method: 'POST', headers: { 'X-Filename': encodeURIComponent(f.name) }, body: raw });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || t('Falha ao importar'));
        toast(t('Importado'), 'ok'); await refresh();
      } catch (e) { toast(e.message, 'err'); }
    };
    const run = async () => {
      if (!sel.value) return toast(t('Selecione um database/dataset para melhorar.'), 'err');
      const [k, id] = sel.value.split(':');
      const tm = picker.get ? picker.get() : teamCfg;
      try {
        const r = await api(`/api/data/items/${k}/${id}/upgrade`, {
          method: 'POST',
          body: { prompt: cmp.text(), count: parseInt(count.value || '0', 10), mode: modeSel.value, action: actionSel.value, team: tm, attachment_ids: cmp.fileIds() },
        });
        status.replaceChildren(jobWatcher(r.job_id, refresh));
      } catch (e) { toast(e.message, 'err'); }
    };
    cmp.configure({ onSend: run });
    body.replaceChildren(
      h('div', { class: 'dt-section col', style: { gap: '10px' } },
        h('h2', { style: { margin: 0 } }, t('Upgrade')),
        h('p', { class: 'muted small', style: { margin: 0 } }, t('Importe e melhore databases/datasets existentes: adicione mais dados, gere dados sintéticos e enriqueça (um tipo ou vários tipos/modalidades ao mesmo tempo).')),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Destino (database/dataset)')), sel),
        h('div', { class: 'dt-section col', style: { gap: '8px' } },
          h('b', null, t('Importar database/dataset existente')),
          h('div', { class: 'grid2' }, h('div', { class: 'field' }, h('label', { class: 'f' }, t('Tipo')), kindSel), h('div', { class: 'field' }, h('label', { class: 'f' }, t('Arquivo')), fileIn)),
          h('div', { class: 'dt-actions' },
            h('button', { class: 'btn', type: 'button', onclick: importNew }, icon('upload', 14), t('Importar como novo item')),
            h('button', { class: 'btn', type: 'button', onclick: importInto }, icon('layers', 14), t('Importar dentro do item')))),
        h('div', { class: 'dt-section col', style: { gap: '8px' } },
          h('b', null, t('Melhorar com IA')),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Ação')), actionSel),
          h('div', { class: 'grid2' }, h('div', { class: 'field' }, h('label', { class: 'f' }, t('Quantidade (para gerar mais)')), count), h('div', { class: 'field' }, h('label', { class: 'f' }, t('Modo')), modeSel)),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Prompt/instruções')), cmp.el),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Equipe de agentes')), picker.el),
          h('div', { class: 'dt-actions' }, h('button', { class: 'btn primary', type: 'button', onclick: run }, icon('sparkle', 14), t('Aplicar upgrade com IA'))),
          status)));
  }

  function paintExport() {
    const sel = itemSelect(items, 'dt-exp-item');
    const fmtSel = select(EXPORT_FORMATS, 'json', () => {}, { id: 'dt-exp-fmt' });
    const status = h('div');
    const run = async () => {
      if (!sel.value) return toast(t('Selecione um database/dataset.'), 'err');
      const [k, id] = sel.value.split(':');
      try {
        const r = await api(`/api/data/items/${k}/${id}/export`, { method: 'POST', body: { format: fmtSel.value } });
        toast(t('Exportado: {n}', { n: r.name }), 'ok');
        status.replaceChildren(h('div', { class: 'row', style: { gap: '8px', alignItems: 'center', flexWrap: 'wrap' } },
          h('span', { class: 'small' }, t('Arquivo: {n} ({r} registros)', { n: r.name, r: r.records })),
          h('a', { class: 'btn sm primary', href: `/api/data/items/${k}/${id}/exports/${encodeURIComponent(r.name)}`, download: r.name }, icon('download', 13), t('Baixar'))));
        await refresh();
      } catch (e) { toast(e.message, 'err'); }
    };
    const runAll = async () => {
      if (!items.length) return toast(t('Nenhum item disponível'), 'err');
      const done = [];
      for (const it of items) {
        try {
          const r = await api(`/api/data/items/${it.kind}/${it.id}/export`, { method: 'POST', body: { format: fmtSel.value } });
          done.push({ kind: it.kind, id: it.id, name: r.name, records: r.records });
        } catch (e) { /* um item que falhou não para os outros */ }
      }
      toast(t('{n} arquivo(s) exportado(s)', { n: done.length }), 'ok');
      status.replaceChildren(h('div', { class: 'col', style: { gap: '4px' } }, ...done.map((d) => h('div', { class: 'row', style: { gap: '8px', alignItems: 'center' } },
        h('span', { class: 'small' }, d.name + ' (' + d.records + ')'),
        h('a', { class: 'btn sm', href: `/api/data/items/${d.kind}/${d.id}/exports/${encodeURIComponent(d.name)}`, download: d.name }, icon('download', 13), t('Baixar'))))));
      await refresh();
    };
    body.replaceChildren(
      h('div', { class: 'dt-section col', style: { gap: '10px' } },
        h('h2', { style: { margin: 0 } }, t('Export')),
        h('p', { class: 'muted small', style: { margin: 0 } }, t('Exporte databases e datasets em vários formatos preservando a estrutura (JSON, JSONL/NDJSON, CSV, TSV, XML, HTML, Markdown, SQLite).')),
        h('div', { class: 'grid2' },
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Item')), sel),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Formato')), fmtSel)),
        h('div', { class: 'dt-actions' },
          h('button', { class: 'btn primary', type: 'button', onclick: run }, icon('download', 14), t('Exportar')),
          h('button', { class: 'btn', type: 'button', onclick: runAll }, icon('layers', 14), t('Exportar todos'))),
        status));
  }

  const tabBar = h('nav', { class: 'dt-tabs', role: 'tablist', 'aria-label': t('Abas do Data') },
    TABS.map(([id, label, ic]) => h('a', { class: 'dt-tab' + (tab === id ? ' on' : ''), href: '#/data/' + id, role: 'tab', 'aria-selected': String(tab === id) }, icon(ic, 14), h('span', null, t(label)))));
  root.replaceChildren(h('div', { class: 'page dt-app' },
    h('div', { class: 'page-h dt-bar' },
      h('div', null, h('h1', { style: { margin: 0 } }, 'Data'), h('p', { class: 'muted small', style: { margin: 0 } }, t('Databases e datasets multimodais com IA'))),
      h('span', { class: 'grow' }), tabBar),
    body));
  await paint();
}
