// Modo Data — databases e datasets multimodais com IA.
// Abas: main, databases, datasets, synthetic (dados sintéticos), scraping (web scraping), upgrade, export.
import { api, events } from '../api.js';
import { t } from '../i18n.js';
import { go, state } from '../main.js';
import { teamPicker } from '../team_ui.js';
import { confirmDialog, h, icon, modal, select, toast } from '../ui.js';
import { createComposer } from './composer.js';
import { mergeDialog, openEditor } from './data_editor.js';

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
  ['xml', 'XML'], ['html', 'HTML'], ['md', 'Markdown'], ['sqlite', 'SQLite (.db)'], ['xlsx', 'Excel (.xlsx)'], ['sql', 'SQL (CREATE + INSERT)'], ['yaml', 'YAML'], ['zip', 'ZIP (dados + mídia + README)'],
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

// busca, ordenação e etiquetas da lista de itens (valem para Main, Databases e Datasets)
const listState = { q: '', sort: 'updated', tag: '' };
function filterItems(items) {
  const q = listState.q.trim().toLowerCase();
  let out = items.filter((it) => (!q || `${it.name} ${it.description || ''} ${(it.tags || []).join(' ')}`.toLowerCase().includes(q)) && (!listState.tag || (it.tags || []).includes(listState.tag)));
  const by = { updated: (a, b) => String(b.updated || '').localeCompare(String(a.updated || '')), name: (a, b) => String(a.name || '').localeCompare(String(b.name || ''), undefined, { numeric: true }), records: (a, b) => (b.records || 0) - (a.records || 0) };
  return out.sort(by[listState.sort] || by.updated);
}
function listControls(items, repaint) {
  const tags = Array.from(new Set(items.flatMap((it) => it.tags || []))).sort();
  const q = h('input', { id: 'dt-list-q', placeholder: t('Buscar por nome, descrição ou etiqueta…'), value: listState.q, style: { flex: '1', minWidth: '180px' } });
  q.addEventListener('input', () => { listState.q = q.value; clearTimeout(q._t); q._t = setTimeout(repaint, 200); });
  const sort = select([['updated', t('Mais recentes')], ['name', t('Nome')], ['records', t('Mais registros')]], listState.sort, (v) => { listState.sort = v; repaint(); }, { id: 'dt-list-sort' });
  return h('div', { class: 'col', style: { gap: '6px' } },
    h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap' } }, q, sort),
    tags.length ? h('div', { class: 'dt-tags' }, h('button', { class: 'chip' + (listState.tag ? '' : ' solid'), type: 'button', onclick: () => { listState.tag = ''; repaint(); } }, t('Todas')),
      ...tags.map((x) => h('button', { class: 'chip' + (listState.tag === x ? ' solid' : ''), type: 'button', onclick: () => { listState.tag = listState.tag === x ? '' : x; repaint(); } }, x))) : null);
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
    if (item && item.kind && item.id) openEditor(item.kind, item.id, onChanged);
  } catch (e) { toast(e.message, 'err'); }
}

const CHECK_LABEL = {
  requested: 'pedidos', generated: 'gerados', from_ai: 'pela IA', schema_fields: 'campos', duplicates: 'repetidos descartados', dropped: 'sem campo obrigatório', extra_fields: 'valores fora do schema',
  links: 'links', read: 'lidos', skipped_robots: 'bloqueados pelo robots.txt', failed: 'com erro', structured: 'registros prontos (JSON/CSV)', media: 'arquivos de mídia', extracted: 'extraídos pela IA', raw: 'texto cru guardado',
  total: 'registros', changed: 'alterados', unchanged: 'sem mudança', batches: 'lotes', failed_batches: 'lotes sem resposta', rows_removed: 'linhas removidas', converted: 'valores convertidos',
};

function resultSummary(ev) {
  const c = ev.checks || {};
  const bits = Object.keys(CHECK_LABEL).filter((k) => typeof c[k] === 'number' && c[k] > 0).map((k) => `${c[k]} ${t(CHECK_LABEL[k])}`);
  const warns = (ev.warnings || []).slice(0, 6);
  if (!bits.length && !warns.length) return null;
  return h('div', { class: 'col dt-result', style: { gap: '4px' } },
    bits.length ? h('div', { class: 'small' }, bits.join(' · ')) : null,
    warns.length ? h('ul', { class: 'small muted', style: { margin: 0, paddingLeft: '18px' } }, ...warns.map((w) => h('li', null, w))) : null);
}

function jobWatcher(jobId, onDone) {
  const box = h('div', { class: 'muted small' }, t('Executando...'));
  const bar = h('div', { class: 'dt-bar' }, h('i'));
  const sum = h('div');
  const wrap = h('div', { class: 'col', style: { gap: '6px' } }, box, bar, sum);
  // o EventSource entrega TODOS os eventos ao mesmo callback; o tipo vem em `ev.type`
  events(`/api/jobs/${jobId}/events`, (ev) => {
    if (ev.type === 'stage') { box.textContent = ev.message || ev.stage || t('Executando...'); }
    else if (ev.type === 'step' && ev.label) { box.textContent = ev.label + (ev.status === 'fallback' ? ' · ' + t('método automático') : ''); }
    else if (ev.type === 'progress') {
      if (ev.message) box.textContent = ev.message;
      if (ev.total) bar.firstChild.style.width = Math.round((ev.done / ev.total) * 100) + '%';
    }
    else if (ev.type === 'done') { box.textContent = t('Concluído.'); bar.firstChild.style.width = '100%'; sum.replaceChildren(resultSummary(ev) || ''); toast(t('Concluído'), 'ok'); onDone && onDone(ev); }
    else if (ev.type === 'error') { box.textContent = ev.message || ev.error || t('Erro'); toast(ev.message || ev.error || t('Erro'), 'err'); onDone && onDone(ev); }
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
  // ao terminar uma tarefa de IA só recarrega a lista (para os contadores): repintar a aba apagaria o resumo do resultado que acabou de aparecer
  async function refreshQuiet() { items = await loadItems().catch(() => items); }
  const body = h('div', { id: 'dt-body' });

  async function paint() {
    // open requested item dialog
    if (ctx && ctx.open && ctx.open.kind && ctx.open.id) {
      const o = ctx.open; ctx.open = null;
      await openEditor(o.kind, o.id, refresh, items);
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
    const grid = h('div', { class: 'dt-grid' }, ...filterItems(items).map((it) => renderItemCard(it, refresh)));
    body.replaceChildren(
      h('div', { class: 'dt-section' },
        h('h2', { style: { marginTop: 0 } }, t('Data')),
        h('p', { class: 'muted' }, t('Crie, gere, gerencie, edite, visualize, organize e mescle databases e datasets multimodais com ajuda de agentes de IA. Gere dados sintéticos, faça web scraping open source, importe/melhore (upgrade) e exporte em vários formatos preservando a estrutura.')),
        h('div', { class: 'dt-actions', style: { marginTop: '8px' } },
          h('button', { class: 'btn primary', type: 'button', onclick: () => createDialog(cfg.default_kind, refresh) }, icon('plus', 14), t('Novo database/dataset')),
          h('button', { class: 'btn', id: 'dt-merge-open', type: 'button', onclick: () => mergeDialog(items, '', refresh) }, icon('layers', 14), t('Mesclar')),
          h('button', { class: 'btn', type: 'button', onclick: refresh }, icon('refresh', 14), t('Atualizar')))),
      h('h3', null, t('Todos os itens')),
      items.length ? listControls(items, paintMain) : null,
      items.length ? grid : h('div', { class: 'muted' }, t('Nenhum database ou dataset ainda. Crie um novo para começar.')));
  }

  function paintKind(kind) {
    const all = items.filter((it) => it.kind === kind);
    const list = filterItems(all);
    const grid = h('div', { class: 'dt-grid' }, ...list.map((it) => renderItemCard(it, refresh)));
    body.replaceChildren(
      h('div', { class: 'row', style: { justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' } },
        h('h2', { style: { margin: 0 } }, kind === 'database' ? t('Databases') : t('Datasets')),
        h('div', { class: 'dt-actions' },
          h('button', { class: 'btn primary', type: 'button', onclick: () => createDialog(kind, refresh) }, icon('plus', 14), t('Novo')),
          h('button', { class: 'btn', type: 'button', onclick: () => mergeDialog(items, '', refresh) }, icon('layers', 14), t('Mesclar')))),
      all.length ? listControls(all, () => paintKind(kind)) : null,
      list.length ? grid : all.length ? h('div', { class: 'muted' }, t('Nenhum item corresponde à busca.')) : h('div', { class: 'muted' }, kind === 'database' ? t('Nenhum database ainda.') : t('Nenhum dataset ainda.')));
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
        status.replaceChildren(jobWatcher(r.job_id, refreshQuiet));
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
    const media = h('input', { type: 'checkbox', id: 'dt-scrape-media' });
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
          body: { urls: list, prompt: cmp.text(), team: tm, ack: true, download_media: media.checked, attachment_ids: cmp.fileIds() },
        });
        status.replaceChildren(jobWatcher(r.job_id, refreshQuiet));
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
        h('p', { class: 'muted small', style: { margin: 0 } }, t('Aceita qualquer tipo de link: páginas, JSON, CSV, XML/RSS, texto, imagens, áudio, vídeo e PDFs. JSON e CSV viram registros direto; páginas passam pela IA; arquivos de mídia viram registros com o endereço, o tipo e o tamanho.')),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Links (um por linha)')), urls),
        h('label', { class: 'row small', style: { gap: '6px', cursor: 'pointer' } }, media, h('span', null, t('Guardar no item os arquivos de mídia dos links (até 20 MB cada)'))),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Prompt de extração')), cmp.el),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Equipe de agentes')), picker.el),
        h('div', { class: 'dt-actions' }, h('button', { class: 'btn primary', type: 'button', onclick: run }, icon('globe', 14), t('Fazer scraping e extrair'))),
        status));
  }

  function paintUpgrade() {
    const sel = itemSelect(items, 'dt-up-item');
    const fileIn = h('input', { type: 'file', id: 'dt-up-file', accept: '.json,.jsonl,.ndjson,.csv,.tsv,.xml,.xlsx' });
    const kindSel = select([['dataset', t('Dataset')], ['database', t('Database')]], cfg.default_kind || 'dataset', () => {}, { id: 'dt-up-kind' });
    const cmp = promptComposer(t('Como melhorar/enriquecer? (opcional). Você pode pedir novos campos, limpeza, normalização ou mais dados.'), 4);
    const count = h('input', { type: 'number', min: 0, max: MAX_SYNTH, value: 20, id: 'dt-up-count' });
    const modeSel = select(SYNTH_MODES, cfg.synthetic_mode || 'single', () => {}, { id: 'dt-up-mode' });
    const fieldsIn = h('input', { id: 'dt-up-fields', placeholder: t('campo1, campo2') });
    const langIn = h('input', { id: 'dt-up-lang', placeholder: t('Idioma de destino (ex.: inglês)') });
    const ACTIONS = [
      ['enrich', t('Melhorar/enriquecer os registros (a base inteira, em lotes)')],
      ['fill_missing', t('Preencher valores vazios')],
      ['classify', t('Classificar (criar uma coluna com um rótulo)')],
      ['translate', t('Traduzir campos de texto')],
      ['clean', t('Limpar e padronizar (sem IA)')],
      ['generate', t('Gerar e adicionar mais dados sintéticos')],
    ];
    const HINT = { enrich: '', fill_missing: t('Sem IA, preenche com a mediana (números) ou o valor mais comum de cada coluna.'), classify: t('Escreva em «Campos» o nome da nova coluna (ex.: sentimento) e, no prompt, o critério.'),
      translate: t('Escreva em «Campos» as colunas a traduzir e o idioma de destino.'), clean: t('Tira espaços, converte tipos pelo schema e remove linhas vazias. Funciona offline.'), generate: t('Acrescenta registros novos, sem repetir os que já existem.') };
    const hint = h('div', { class: 'muted small', id: 'dt-up-hint' });
    const fieldsBox = h('div', { class: 'field' }, h('label', { class: 'f' }, t('Campos')), fieldsIn);
    const langBox = h('div', { class: 'field' }, h('label', { class: 'f' }, t('Idioma')), langIn);
    const countBox = h('div', { class: 'field' }, h('label', { class: 'f' }, t('Quantidade (para gerar mais)')), count);
    const sync = () => {
      const a = actionSel.value;
      hint.textContent = HINT[a] || '';
      fieldsBox.style.display = ['fill_missing', 'classify', 'translate'].includes(a) ? '' : 'none';
      langBox.style.display = a === 'translate' ? '' : 'none';
      countBox.style.display = a === 'generate' ? '' : 'none';
    };
    const actionSel = select(ACTIONS, 'enrich', sync, { id: 'dt-up-action' });
    const teamCfg = { agents: cfg.agents || 1, effort: cfg.effort || 'high' };
    const picker = teamPicker(teamCfg, () => {}, { id: 'dt-up-team', defaultEffort: 'high' });
    const status = h('div');
    const send = async (url, f) => {
      const raw = await f.arrayBuffer();
      const r = await fetch(url, { method: 'POST', headers: { 'X-Filename': encodeURIComponent(f.name) }, body: raw });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || t('Falha ao importar'));
      return j;
    };
    const importNew = async () => {
      const f = fileIn.files && fileIn.files[0];
      if (!f) return toast(t('Selecione um arquivo para importar.'), 'err');
      try { await send(`/api/data/upgrade/import?kind=${encodeURIComponent(kindSel.value)}&item_name=${encodeURIComponent(f.name.replace(/\.[^.]+$/, ''))}&name=${encodeURIComponent(f.name)}`, f); toast(t('Importado'), 'ok'); await refresh(); } catch (e) { toast(e.message, 'err'); }
    };
    // importa dentro de um item que já existe (soma os registros e acrescenta as colunas ao schema)
    const importInto = async () => {
      const f = fileIn.files && fileIn.files[0];
      if (!f) return toast(t('Selecione um arquivo para importar.'), 'err');
      if (!sel.value) return toast(t('Selecione um database/dataset para melhorar.'), 'err');
      const [k, id] = sel.value.split(':');
      try { await send(`/api/data/items/${k}/${id}/import?mode=append&name=${encodeURIComponent(f.name)}`, f); toast(t('Importado'), 'ok'); await refresh(); } catch (e) { toast(e.message, 'err'); }
    };
    const run = async () => {
      if (!sel.value) return toast(t('Selecione um database/dataset para melhorar.'), 'err');
      const [k, id] = sel.value.split(':');
      const tm = picker.get ? picker.get() : teamCfg;
      try {
        const r = await api(`/api/data/items/${k}/${id}/upgrade`, {
          method: 'POST',
          body: { prompt: cmp.text(), count: parseInt(count.value || '0', 10), mode: modeSel.value, action: actionSel.value, fields: fieldsIn.value.split(',').map((x) => x.trim()).filter(Boolean), language: langIn.value.trim(), team: tm, attachment_ids: cmp.fileIds() },
        });
        status.replaceChildren(jobWatcher(r.job_id, refreshQuiet));
      } catch (e) { toast(e.message, 'err'); }
    };
    cmp.configure({ onSend: run });
    sync();
    body.replaceChildren(
      h('div', { class: 'dt-section col', style: { gap: '10px' } },
        h('h2', { style: { margin: 0 } }, t('Upgrade')),
        h('p', { class: 'muted small', style: { margin: 0 } }, t('Importe e melhore databases/datasets existentes: adicione mais dados, gere dados sintéticos e enriqueça (um tipo ou vários tipos/modalidades ao mesmo tempo).')),
        h('div', { class: 'field' }, h('label', { class: 'f' }, t('Destino (database/dataset)')), sel),
        h('div', { class: 'dt-section col', style: { gap: '8px' } },
          h('b', null, t('Importar database/dataset existente')),
          h('div', { class: 'muted small' }, t('Formatos: JSON, JSONL/NDJSON, CSV, TSV, XML e Excel (.xlsx).')),
          h('div', { class: 'grid2' }, h('div', { class: 'field' }, h('label', { class: 'f' }, t('Tipo')), kindSel), h('div', { class: 'field' }, h('label', { class: 'f' }, t('Arquivo')), fileIn)),
          h('div', { class: 'dt-actions' },
            h('button', { class: 'btn', id: 'dt-up-import-new', type: 'button', onclick: importNew }, icon('upload', 14), t('Importar como novo item')),
            h('button', { class: 'btn', id: 'dt-up-import-into', type: 'button', onclick: importInto }, icon('layers', 14), t('Importar dentro do item')))),
        h('div', { class: 'dt-section col', style: { gap: '8px' } },
          h('b', null, t('Melhorar')),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Ação')), actionSel), hint,
          h('div', { class: 'grid2' }, countBox, h('div', { class: 'field' }, h('label', { class: 'f' }, t('Modo')), modeSel)),
          fieldsBox, langBox,
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Prompt/instruções')), cmp.el),
          h('div', { class: 'field' }, h('label', { class: 'f' }, t('Equipe de agentes')), picker.el),
          h('div', { class: 'dt-actions' }, h('button', { class: 'btn primary', id: 'dt-up-run', type: 'button', onclick: run }, icon('sparkle', 14), t('Aplicar upgrade'))),
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
        await refreshQuiet();
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
      await refreshQuiet();
    };
    body.replaceChildren(
      h('div', { class: 'dt-section col', style: { gap: '10px' } },
        h('h2', { style: { margin: 0 } }, t('Export')),
        h('p', { class: 'muted small', style: { margin: 0 } }, t('Exporte databases e datasets em vários formatos preservando a estrutura (JSON, JSONL/NDJSON, CSV, TSV, XML, HTML, Markdown, SQLite, Excel, SQL, YAML e pacote ZIP com a mídia).')),
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
