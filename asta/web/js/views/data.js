// Modo Data — databases e datasets multimodais com IA.
// Abas: main, databases, datasets, synthetic (dados sintéticos), scraping (web scraping), upgrade, export.
import { api, events } from '../api.js';
import { t } from '../i18n.js';
import { go, state } from '../main.js';
import { teamPicker } from '../team_ui.js';
import { confirmDialog, fmtBytes, h, icon, modal, select, toast } from '../ui.js';

const TABS = [
  ['main', 'Main', 'home'],
  ['databases', 'Databases', 'storage'],
  ['datasets', 'Datasets', 'folder'],
  ['synthetic', 'Synthetic data', 'sparkle'],
  ['scraping', 'Web scraping', 'globe'],
  ['upgrade', 'Upgrade', 'refresh'],
  ['export', 'Export', 'download'],
];
const TAB_IDS = TABS.map((x) => x[0]);

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

function recordsTable(records, schema) {
  const recs = Array.isArray(records) ? records.slice(0, 200) : [];
  const cols = [];
  const seen = new Set();
  const sfields = (schema && schema.fields) || [];
  for (const f of sfields) { if (f && f.name && !seen.has(f.name)) { seen.add(f.name); cols.push(f.name); } }
  for (const r of recs.slice(0, 50)) {
    if (r && typeof r === 'object' && !Array.isArray(r)) for (const k of Object.keys(r)) { if (!seen.has(k)) { seen.add(k); cols.push(k); } }
  }
  if (!cols.length) cols.push('value');
  const head = h('tr', null, ...cols.map((c) => h('th', null, c)));
  const body = recs.map((r) => h('tr', null, ...cols.map((c) => {
    let v = r && typeof r === 'object' && !Array.isArray(r) ? r[c] : (c === 'value' ? r : '');
    if (v && typeof v === 'object') try { v = JSON.stringify(v); } catch (e) { v = String(v); }
    return h('td', null, h('div', { class: 'dt-rec' }, v == null ? '' : String(v)));
  })));
  return h('div', { class: 'dt-table-wrap' }, h('table', { class: 'dt-table' }, h('thead', null, head), h('tbody', null, ...body)));
}

async function openItemDialog(kind, id, onChanged) {
  let data;
  try { data = await api(`/api/data/items/${kind}/${id}`); } catch (e) { toast(e.message, 'err'); return; }
  const info = h('div', { class: 'dt-kv' },
    h('div', { class: 'muted' }, t('Tipo')), h('div', null, kind === 'database' ? t('Database') : t('Dataset')),
    h('div', { class: 'muted' }, t('Registros')), h('div', null, String((data.records || []).length)),
    h('div', { class: 'muted' }, t('Campos')), h('div', null, String(((data.schema || {}).fields || []).length)));
  const recs = h('textarea', { style: { width: '100%', minHeight: '220px', fontFamily: 'monospace', fontSize: '12px' } }, JSON.stringify(data.records || [], null, 2));
  const schemaBox = h('textarea', { style: { width: '100%', minHeight: '120px', fontFamily: 'monospace', fontSize: '12px' } }, JSON.stringify(data.schema || { fields: [] }, null, 2));
  const body = h('div', { class: 'col', style: { gap: '10px', minWidth: 'min(900px,90vw)' } },
    h('h3', { style: { margin: 0 } }, (data.meta && data.meta.name) || id), info,
    h('b', null, t('Visualização (amostra)')), recordsTable(data.records || [], data.schema || {}),
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
  events(`/api/jobs/${jobId}/events`, {
    stage: (ev) => { box.textContent = ev.message || ev.stage || t('Executando...'); },
    done: (ev) => { box.textContent = t('Concluído.'); toast(t('Concluído'), 'ok'); onDone && onDone(ev); },
    error: (ev) => { box.textContent = ev.error || t('Erro'); toast(ev.error || t('Erro'), 'err'); onDone && onDone(ev); },
    end: () => {},
  });
  return box;
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
    if (tab === 'synthetic') return paintSynthetic();
    if (tab === 'scraping') return paintScraping();
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
    const prompt = h('textarea', { placeholder: t('Descreva os dados sintéticos que deseja gerar (use prompts multimodais; você pode citar anexos e modalidades).'), rows: 6, style: { width: '100%' } });
    const count = h('input', { type: 'number', min: 1, max: 500, value: cfg.synthetic_count || 20 });
    const modeSel = select([['single', t('Um tipo de dado')], ['multi', t('Vários tipos/modalidades')]], cfg.synthetic_mode || 'single', () => {}, { id: 'dt-synth-mode' });
    const teamCfg = { agents: cfg.agents || 1, effort: cfg.effort || 'high' };
    const picker = teamPicker(teamCfg, () => {}, { id: 'dt-synth-team', defaultEffort: 'high' });
    const status = h('div');
    const run = async () => {
      if (!sel.value) return toast(t('Selecione um database/dataset.'), 'err');
      const [k, id] = sel.value.split(':');
      const tm = picker.get ? picker.get() : teamCfg;
      try {
        const r = await api(`/api/data/items/${k}/${id}/synthetic`, { method: 'POST', body: { prompt: prompt.value, count: parseInt(count.value || '20', 10), mode: modeSel.value, team: tm } });
        status.replaceChildren(jobWatcher(r.job_id, refresh));
      } catch (e) { toast(e.message, 'err'); }
    };
    body.replaceChildren(
      h('div', { class: 'dt-section col', style: { gap: '10px' } },
        h('h2', { style: { margin: 0 } }, t('Synthetic data')),
        h('p', { class: 'muted small', style: { margin: 0 } }, t('Gere dados sintéticos em massa com prompts multimodais e agentes de IA para databases e datasets (um tipo ou vários tipos/modalidades).')),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Destino (database/dataset)')), sel),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Prompt')), prompt),
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
    const prompt = h('textarea', { placeholder: t('O que extrair/estruturar a partir das páginas (prompt multimodal de extração).'), rows: 4, style: { width: '100%' } });
    const teamCfg = { agents: cfg.agents || 1, effort: cfg.effort || 'high' };
    const picker = teamPicker(teamCfg, () => {}, { id: 'dt-scrape-team', defaultEffort: 'high' });
    const status = h('div');
    const run = async () => {
      if (!sel.value) return toast(t('Selecione um database/dataset.'), 'err');
      const list = urls.value.split(/\n+/).map((s) => s.trim()).filter(Boolean);
      if (!list.length) return toast(t('Informe ao menos um link.'), 'err');
      const [k, id] = sel.value.split(':');
      const tm = picker.get ? picker.get() : teamCfg;
      try {
        const r = await api(`/api/data/items/${k}/${id}/scrape`, { method: 'POST', body: { urls: list, prompt: prompt.value, team: tm } });
        status.replaceChildren(jobWatcher(r.job_id, refresh));
      } catch (e) { toast(e.message, 'err'); }
    };
    body.replaceChildren(
      h('div', { class: 'dt-section col', style: { gap: '10px' } },
        h('h2', { style: { margin: 0 } }, t('Web scraping')),
        h('div', { class: 'dt-warn' }, h('b', null, t('Aviso: somente uso open source. Não usar para uso comercial.')), h('div', { class: 'small', style: { marginTop: '4px' } }, t('Respeite os termos de uso, robots.txt, leis aplicáveis e os direitos dos sites/fontes. Use apenas para fins open source e não comerciais.'))),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Destino (database/dataset)')), sel),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Links (um por linha)')), urls),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Prompt de extração')), prompt),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Equipe de agentes')), picker.el),
        h('div', { class: 'dt-actions' }, h('button', { class: 'btn primary', type: 'button', onclick: run }, icon('globe', 14), t('Fazer scraping e extrair'))),
        status));
  }

  function paintUpgrade() {
    const sel = itemSelect(items, 'dt-up-item');
    const fileIn = h('input', { type: 'file', accept: '.json,.jsonl,.csv,.tsv,.ndjson' });
    const kindSel = select([['dataset', t('Dataset')], ['database', t('Database')]], cfg.default_kind || 'dataset', () => {}, { id: 'dt-up-kind' });
    const prompt = h('textarea', { placeholder: t('Como melhorar/enriquecer? (opcional). Você pode pedir novos campos, limpeza, normalização ou mais dados.'), rows: 4, style: { width: '100%' } });
    const count = h('input', { type: 'number', min: 0, max: 500, value: 0 });
    const modeSel = select([['single', t('Um tipo de dado')], ['multi', t('Vários tipos/modalidades')]], cfg.synthetic_mode || 'single', () => {}, { id: 'dt-up-mode' });
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
    const run = async () => {
      if (!sel.value) return toast(t('Selecione um database/dataset para melhorar.'), 'err');
      const [k, id] = sel.value.split(':');
      const tm = picker.get ? picker.get() : teamCfg;
      try {
        const r = await api(`/api/data/items/${k}/${id}/upgrade`, { method: 'POST', body: { prompt: prompt.value, count: parseInt(count.value || '0', 10), mode: modeSel.value, action: actionSel.value, team: tm } });
        status.replaceChildren(jobWatcher(r.job_id, refresh));
      } catch (e) { toast(e.message, 'err'); }
    };
    body.replaceChildren(
      h('div', { class: 'dt-section col', style: { gap: '10px' } },
        h('h2', { style: { margin: 0 } }, t('Upgrade')),
        h('p', { class: 'muted small', style: { margin: 0 } }, t('Importe e melhore databases/datasets existentes: adicione mais dados, gere dados sintéticos e enriqueça (um tipo ou vários tipos/modalidades ao mesmo tempo).')),
        h('div', { class: 'dt-section col', style: { gap: '8px' } },
          h('b', null, t('Importar database/dataset existente')),
          h('div', { class: 'grid2' }, h('div', { class: 'field' }, h('label', { class: 'f' }, t('Tipo')), kindSel), h('div', { class: 'field' }, h('label', { class: 'f' }, t('Arquivo')), fileIn)),
          h('div', { class: 'dt-actions' }, h('button', { class: 'btn', type: 'button', onclick: importNew }, icon('upload', 14), t('Importar como novo item')))),
        h('div', { class: 'dt-section col', style: { gap: '8px' } },
          h('b', null, t('Melhorar com IA')),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Item')), sel),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Ação')), actionSel),
          h('div', { class: 'grid2' }, h('div', { class: 'field' }, h('label', { class: 'f' }, t('Quantidade (para gerar mais)')), count), h('div', { class: 'field' }, h('label', { class: 'f' }, t('Modo')), modeSel)),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Prompt/instruções')), prompt),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Equipe de agentes')), picker.el),
          h('div', { class: 'dt-actions' }, h('button', { class: 'btn primary', type: 'button', onclick: run }, icon('sparkle', 14), t('Aplicar upgrade com IA'))),
          status)));
  }

  function paintExport() {
    const sel = itemSelect(items, 'dt-exp-item');
    const fmtSel = select([['json', 'JSON'], ['jsonl', 'JSONL / NDJSON'], ['csv', 'CSV'], ['tsv', 'TSV'], ['sqlite', 'SQLite (.db)']], 'json', () => {}, { id: 'dt-exp-fmt' });
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
    body.replaceChildren(
      h('div', { class: 'dt-section col', style: { gap: '10px' } },
        h('h2', { style: { margin: 0 } }, t('Export')),
        h('p', { class: 'muted small', style: { margin: 0 } }, t('Exporte databases e datasets em vários formatos preservando a estrutura (JSON, JSONL, CSV, TSV, SQLite).')),
        h('div', { class: 'grid2' },
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Item')), sel),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Formato')), fmtSel)),
        h('div', { class: 'dt-actions' }, h('button', { class: 'btn primary', type: 'button', onclick: run }, icon('download', 14), t('Exportar'))),
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
