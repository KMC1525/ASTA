// Scriber → Edição, painel da direita: tamanho da expansão (parágrafos e diálogos), ações da IA sobre o trecho selecionado, revisão ortográfica e pesquisa na web nativa.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { btn, cancelJob, runJob } from '../scriber_ui.js';
import { expandRequest } from '../scriber_text.js';
import { teamPicker } from '../team_ui.js';
import { h, icon, toast } from '../ui.js';

const ACTIONS = [['improve', 'Melhorar', 'sparkle'], ['expand', 'Expandir', 'plus'], ['rewrite', 'Reescrever', 'refresh'], ['shorten', 'Encurtar', 'minus'], ['fix', 'Corrigir', 'check'], ['continue', 'Continuar', 'arrow'],
  ['dialogue', 'Virar diálogo', 'chat'], ['describe', 'Descrever mais', 'image'], ['tone', 'Mudar o tom', 'palette'], ['translate', 'Traduzir', 'globe'], ['custom', 'Pedir…', 'edit']];
const NEEDS_TEXT = { tone: 'Escreva o tom desejado (ex.: mais sombrio, mais leve, mais formal, mais sensual).', translate: 'Escreva o idioma de destino (ex.: inglês, espanhol).', custom: 'Escreva o que a IA deve fazer com o trecho.' };
const CHIPS = [25, 50, 100, 200, 400, 800];
const KEY = 'asta.scriber.expand';
const KIND_LABEL = { spelling: 'Ortografia', grammar: 'Gramática', punctuation: 'Pontuação', spacing: 'Espaços', repeat: 'Repetição', capital: 'Maiúscula', typography: 'Tipografia' };

export function createSidePanel(S, X) {
  const cfg = Object.assign({ expand_words: 150, dialogue_words: 60, web: false }, S.cfg());
  let ex = { mode: 'add', par: cfg.expand_words, dlg: cfg.dialogue_words };
  try { ex = Object.assign(ex, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (e) { /* ok */ }
  const saveEx = () => { try { localStorage.setItem(KEY, JSON.stringify(ex)); } catch (e) { /* ok */ } };
  const st = { tab: 'ai', busy: false, sel: null, sug: null, web: !!cfg.web, useSources: true, sources: [], issues: [], ignore: (S.proj.ignore || []).slice() };
  const team = teamPicker(cfg, null, { id: 'sc-ed-team' });
  const ai = S.status.text && S.status.text.ai;

  // ================================================================ aba IA
  const selBox = h('div', { class: 'sc-selbox', id: 'sc-selbox' });
  const sizeBox = h('div', { class: 'sc-sizebox', id: 'sc-sizebox' });
  const actBox = h('div', { class: 'sc-actions', id: 'sc-actions' });
  const instr = h('textarea', { rows: 2, id: 'sc-instr', placeholder: t('Instrução opcional: “mais tenso”, “sem advérbios”, “em primeira pessoa”, “inglês”…'), 'aria-label': t('Instrução para a IA') });
  const sugBox = h('div', { class: 'sc-sugg-box', id: 'sc-sugg' });
  const statusBox = h('div', { class: 'sc-busy hidden', id: 'sc-busy' });
  const webChk = h('input', { type: 'checkbox', id: 'sc-ai-web', checked: st.web }); webChk.addEventListener('change', () => { st.web = webChk.checked; });
  const loreChk = h('input', { type: 'checkbox', id: 'sc-ai-lore', checked: X.lore.enabled() }); loreChk.addEventListener('change', () => { document.getElementById('sc-lore-on').checked = loreChk.checked; document.getElementById('sc-lore-on').dispatchEvent(new Event('change')); });
  X.loreToggled = (on) => { loreChk.checked = on; };
  const srcChk = h('input', { type: 'checkbox', id: 'sc-ai-src', checked: true }); srcChk.addEventListener('change', () => { st.useSources = srcChk.checked; });
  const srcLabel = h('label', { class: 'check hidden', id: 'sc-ai-src-l' }, srcChk, h('span', null, t('Usar as fontes fixadas')));

  function paintSel(s) {
    st.sel = s;
    selBox.replaceChildren(s && !s.empty
      ? h('div', null, h('b', null, t('{w} palavras', { w: s.words })), ' · ', t(s.kind === 'dialogue' ? 'fala' : s.kind === 'mixed' ? 'misto' : 'parágrafo'), ' · ', t('{n} linha(s)', { n: s.lines.length }), h('div', { class: 'small dim sc-selprev' }, s.text.trim().slice(0, 140) + (s.text.length > 140 ? '…' : '')))
      : h('div', { class: 'muted small' }, t('Selecione um trecho no texto — ou ative «Parágrafo»/«Fala» na barra e clique com o mouse — para melhorar, expandir ou reescrever só aquela parte.')));
    paintSize();
  }
  X.selChanged = paintSel;

  function paintSize() {
    const kind = st.sel && !st.sel.empty ? st.sel.kind : 'paragraph';
    const row = (label, key, id) => {
      const num = h('input', { type: 'number', min: 10, max: 3000, step: 10, value: ex[key], id, 'aria-label': label }); num.addEventListener('input', () => { const v = parseInt(num.value, 10); if (v >= 10) { ex[key] = Math.min(3000, v); rng.value = Math.min(1000, ex[key]); saveEx(); paintChips(); } });
      const rng = h('input', { type: 'range', min: 10, max: 1000, step: 10, value: Math.min(1000, ex[key]), id: id + '-r', 'aria-label': label + ' (' + t('controle deslizante') + ')' }); rng.addEventListener('input', () => { ex[key] = parseInt(rng.value, 10); num.value = ex[key]; saveEx(); paintChips(); });
      const chips = h('div', { class: 'sc-chips' });
      const paintChips = () => chips.replaceChildren(...CHIPS.map((n) => h('button', { type: 'button', class: 'chip' + (ex[key] === n ? ' on' : ''), dataset: { n }, onclick: () => { ex[key] = n; num.value = n; rng.value = Math.min(1000, n); saveEx(); paintChips(); } }, (ex.mode === 'total' ? '' : '+') + n)));
      paintChips();
      return h('div', { class: 'sc-sizerow' + ((key === 'dlg') === (kind === 'dialogue') ? ' active' : '') }, h('div', { class: 'row' }, h('b', null, label), h('span', { class: 'grow' }), num, h('span', { class: 'dim small' }, t('palavras'))), rng, chips);
    };
    const seg = h('div', { class: 'seg', id: 'sc-exp-mode' }, [['add', t('Acrescentar')], ['total', t('Resultado com')]].map(([id, l]) => h('button', { type: 'button', class: ex.mode === id ? 'on' : '', dataset: { mode: id }, onclick: () => { ex.mode = id; saveEx(); paintSize(); } }, l)));
    sizeBox.replaceChildren(seg, row(t('Parágrafos'), 'par', 'sc-exp-par'), row(t('Diálogos / falas'), 'dlg', 'sc-exp-dlg'),
      h('div', { class: 'hint' }, ex.mode === 'add' ? t('Expandir e Descrever acrescentam este tanto de palavras ao trecho selecionado; Continuar escreve este tanto.') : t('Expandir e Descrever deixam o trecho com este tamanho; Encurtar também o usa.')));
  }

  const eff = () => expandRequest(st.sel && !st.sel.empty ? st.sel.kind : 'paragraph', { mode: ex.mode, expand_words: ex.par, dialogue_words: ex.dlg });
  X.floatActions = () => [['improve', t('Melhorar')], ['expand', t('Expandir') + ' ' + (ex.mode === 'add' ? '+' : '') + eff().words], ['rewrite', t('Reescrever')], ['shorten', t('Encurtar')]];

  async function run(action, again) {
    if (st.busy) { toast(t('A IA ainda está trabalhando.')); return; }
    const s = st.sel && !st.sel.empty ? st.sel : (again && st.sug ? { range: st.sug.range, text: st.sug.original, lines: st.sug.original.split('\n'), kind: st.sug.kind, words: 0, empty: false } : null);
    const cur = X.getSel();
    const sel = cur.empty ? s : cur;
    if (action !== 'continue' && (!sel || sel.empty)) { toast(t('Selecione um trecho do texto (ou use «Continuar»).')); return; }
    const instruction = instr.value.trim();
    if (NEEDS_TEXT[action] && !instruction) { instr.focus(); toast(t(NEEDS_TEXT[action])); return; }
    const range = (sel && sel.range) ? sel.range.cloneRange() : null;
    let range0 = range;
    if (!range0) { const g = getSelection(); range0 = g.rangeCount ? g.getRangeAt(0).cloneRange() : null; if (!range0) { range0 = document.createRange(); range0.selectNodeContents(X.ed.lastElementChild || X.ed); range0.collapse(false); } }
    const kind = sel ? sel.kind : 'paragraph', ctx = X.contextAround(range0);
    X.hideFloat();
    const body = { action, selection: sel ? sel.lines.join('\n') : '', kind, prompt: instruction, expand: expandRequest(kind, { mode: ex.mode, expand_words: ex.par, dialogue_words: ex.dlg }), context_before: ctx.before, context_after: ctx.after,
      web: st.web, lore: X.lore.enabled(), team: team.get(), language: X.lang(), sources_text: st.useSources ? pinned() : '' };
    setBusy(true, ACTIONS.find((a) => a[0] === action)[1]);
    try {
      const res = await runJob(S, 'edit', body, (ev) => { if (ev.type === 'step') statusBox.dataset.step = ev.label; });
      X.lore.setUsed((res.lore || []).map((x) => x.id));
      showSuggestion({ res, range: range0, original: body.selection, kind, action, instruction });
    } catch (e) { toast(e.message, 'err'); }
    finally { setBusy(false); }
  }
  X.run = run;
  function setBusy(on, label) {
    st.busy = on; statusBox.classList.toggle('hidden', !on);
    statusBox.replaceChildren(...(on ? [h('div', { class: 'spinner' }), h('span', null, t('A IA está trabalhando: {a}…', { a: t(label) })), btn(t('Parar'), 'stop', () => cancelJob(S), '', { id: 'sc-ai-stop' })] : []));
    actBox.querySelectorAll('button').forEach((b) => { b.disabled = on; });
  }

  function showSuggestion(sg) {
    st.sug = sg; const r = sg.res;
    if (!r.changed) { sugBox.replaceChildren(h('div', { class: 'sc-sugg warn', id: 'sc-sugg-card' }, h('b', null, t('Nada a mudar')), (r.notes || []).map((n) => h('div', { class: 'small' }, n)))); return; }
    const lines = r.paragraphs && r.paragraphs.length ? r.paragraphs : [r.text];
    const after = sg.action === 'continue';
    sugBox.replaceChildren(h('div', { class: 'sc-sugg', id: 'sc-sugg-card' },
      h('div', { class: 'row' }, h('b', null, t(ACTIONS.find((a) => a[0] === sg.action)[1])), h('span', { class: 'grow' }), h('span', { class: 'chip dim', id: 'sc-sugg-words' }, after ? t('{n} palavras novas', { n: r.words }) : t('{a} → {b} palavras', { a: r.from_words, b: r.words }))),
      h('div', { class: 'sc-sugg-text', id: 'sc-sugg-text' }, lines.map((l) => h('p', null, l))),
      (r.notes || []).length ? h('ul', { class: 'sc-notes' }, r.notes.map((n) => h('li', null, n))) : null,
      r.lore && r.lore.length ? h('div', { class: 'small dim' }, '✦ ' + t('Lorebook usado:') + ' ' + r.lore.map((x) => x.name).join(', ')) : null,
      h('div', { class: 'row', style: { marginTop: '8px' } },
        h('button', { class: 'btn sm primary', id: 'sc-sugg-accept', type: 'button', onclick: () => accept(lines, after ? 'after' : 'replace') }, icon('check', 14), after ? t('Inserir') : t('Aceitar')),
        after ? null : h('button', { class: 'btn sm', id: 'sc-sugg-after', type: 'button', onclick: () => accept(lines, 'after') }, t('Inserir depois')),
        h('button', { class: 'btn sm', id: 'sc-sugg-retry', type: 'button', onclick: () => run(sg.action, true) }, icon('refresh', 14), t('Tentar de novo')),
        h('button', { class: 'btn ghost sm', id: 'sc-sugg-drop', type: 'button', onclick: () => { st.sug = null; sugBox.replaceChildren(); } }, t('Descartar')))));
    sugBox.scrollIntoView && sugBox.scrollIntoView({ block: 'nearest' });
  }
  function accept(lines, how) {
    const sg = st.sug; if (!sg) return;
    X.applyText(sg.range, lines, how); st.sug = null; sugBox.replaceChildren(); toast(t('Trecho atualizado (Ctrl+Z desfaz).'), 'ok');
  }

  const pinned = () => st.sources.filter((s) => s.pinned && s.text).map((s, i) => `[${i + 1}] ${s.title}\n${s.url}\n${s.text}`).join('\n\n').slice(0, 11000);

  ACTIONS.forEach(([id, label, ic]) => actBox.appendChild(h('button', { type: 'button', class: 'btn sm sc-act', dataset: { act: id }, id: 'sc-act-' + id, onclick: () => run(id) }, icon(ic, 14), t(label))));
  const aiBadge = h('div', { class: 'sc-aibadge ' + (ai ? 'ok' : 'warn'), id: 'sc-ed-ai', title: ai ? t('IA configurada') : t('Sem IA configurada: Corrigir e Encurtar funcionam com regras; o resto precisa de um provedor em Configuração → Provedores.') },
    h('span', { class: 'dot' }), ai ? (S.status.text.label || 'IA') + (S.status.text.model ? ' · ' + S.status.text.model : '') : t('Modo regras (sem IA)'));
  const aiTab = h('div', { class: 'sc-tabpane', id: 'sc-pane-ai' }, aiBadge,
    h('section', { class: 'sc-sec' }, h('h4', null, t('Trecho selecionado')), selBox),
    h('section', { class: 'sc-sec' }, h('h4', null, t('Tamanho da expansão')), sizeBox),
    h('section', { class: 'sc-sec' }, h('h4', null, t('Ações')), actBox, instr,
      h('div', { class: 'sc-opts' }, h('label', { class: 'check' }, loreChk, h('span', null, t('Usar o lorebook'))), h('label', { class: 'check' }, webChk, h('span', null, t('Pesquisar na web'))), srcLabel), h('div', { class: 'row' }, team.el)),
    statusBox, sugBox);

  // ================================================================ aba Revisão (ortografia)
  const dictInfo = h('div', { class: 'small', id: 'sc-dict' });
  const issuesBox = h('div', { class: 'sc-issues', id: 'sc-issues' });
  const reviewInfo = h('div', { class: 'small muted', id: 'sc-review-info' });
  const paraTexts = () => X.blocks().map((b) => b.textContent.replace(/\u00a0/g, ' '));   // mesmo tamanho: as posições dos achados continuam valendo
  function paintDict(has) {
    const l = X.lang();
    dictInfo.replaceChildren(h('span', { class: 'dot ' + (has ? 'ok' : 'warn') }), ' ', has ? t('Dicionário do sistema ativo para {l}', { l }) : t('Sem dicionário do sistema para {l} (instale hunspell ou aspell): o corretor do navegador e as regras continuam funcionando.', { l }));
  }
  X.langChanged = () => { paintDict(!!(S.status.dictionaries || {})[X.lang()]); };
  async function review(useAi) {
    const paras = paraTexts();
    reviewInfo.textContent = t('Revisando…');
    try {
      let res;
      if (useAi) { setBusy(true, t('Revisão ortográfica')); try { res = await runJob(S, 'proofread-ai', { paragraphs: paras, language: X.lang(), team: team.get() }); } finally { setBusy(false); } }
      else res = await api('/api/scriber/proofread', { method: 'POST', body: { paragraphs: paras, language: X.lang(), ignore: st.ignore } });
      st.issues = (res.issues || []).filter((i) => !st.ignore.includes(i.found));
      paintDict(res.dictionary); paintIssues(res);
    } catch (e) { reviewInfo.textContent = ''; toast(e.message, 'err'); }
  }
  function paintIssues(res) {
    const n = st.issues.length;
    reviewInfo.textContent = n ? t('{n} ponto(s) para revisar em {p} parágrafo(s).', { n, p: res ? res.paragraphs : paraTexts().length }) : t('Nenhum problema encontrado. O corretor do navegador também sublinha erros enquanto você digita.');
    issuesBox.replaceChildren(...st.issues.slice(0, 300).map((i, idx) => h('div', { class: 'sc-issue', dataset: { idx, kind: i.kind }, onclick: () => show(i) },
      h('span', { class: 'sc-kind k-' + i.kind }, t(KIND_LABEL[i.kind] || i.kind)), h('div', { class: 'sc-issue-t' }, h('s', null, i.found.length > 40 ? i.found.slice(0, 40) + '…' : i.found), i.fix !== '' && i.fix != null ? [' → ', h('b', null, i.fix.length > 40 ? i.fix.slice(0, 40) + '…' : i.fix)] : null, h('div', { class: 'small dim' }, i.msg)),
      i.fix != null && i.fix !== '' ? h('button', { class: 'btn sm', type: 'button', dataset: { act: 'apply' }, onclick: (e) => { e.stopPropagation(); applyIssue(i); } }, t('Aplicar')) : null,
      h('button', { class: 'btn ghost sm', type: 'button', title: t('Ignorar e não avisar de novo neste texto'), dataset: { act: 'ignore' }, onclick: (e) => { e.stopPropagation(); ignoreWord(i); } }, '×'))));
  }
  function locate(i) { const b = X.blocks()[i.p]; if (!b || b.textContent.replace(/\u00a0/g, ' ').slice(i.start, i.end) !== i.found) return null; return { b, r: X.rangeFromOffsets(b, i.start, i.end) }; }
  function show(i) { const loc = locate(i); if (!loc || !loc.r) { toast(t('O texto mudou; revise de novo.')); return; } X.ed.focus(); X.selectRange(loc.r); loc.b.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
  function applyIssue(i) { const loc = locate(i); if (!loc || !loc.r) { toast(t('O texto mudou; revise de novo.')); return false; } X.ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(loc.r); document.execCommand('insertText', false, i.fix); X.changed(); st.issues = st.issues.filter((x) => x !== i); fixShift(i, i.fix.length - (i.end - i.start)); paintIssues(); return true; }
  function fixShift(done, delta) { st.issues.forEach((x) => { if (x.p === done.p && x.start >= done.end) { x.start += delta; x.end += delta; } }); }
  async function ignoreWord(i) { if (!st.ignore.includes(i.found)) st.ignore.push(i.found); st.issues = st.issues.filter((x) => x.found !== i.found); paintIssues(); try { S.proj = await S.api.put('', { ignore: st.ignore }); } catch (e) { /* ok */ } }
  function applyAll() {
    const list = st.issues.filter((i) => i.fix != null && i.fix !== '').sort((a, b) => (a.p - b.p) || (b.start - a.start)); let n = 0;
    list.forEach((i) => { const loc = locate(i); if (!loc || !loc.r) return; X.ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(loc.r); document.execCommand('insertText', false, i.fix); n++; });
    X.changed(); toast(t('{n} correção(ões) aplicada(s).', { n }), 'ok'); review(false);
  }
  async function typography() {
    const blocks = X.blocks(), paras = blocks.map((b) => b.textContent.replace(/\u00a0/g, ' '));
    try {
      const r = await api('/api/scriber/typography', { method: 'POST', body: { paragraphs: paras, language: X.lang() } });
      let n = 0, skipped = 0;
      r.paragraphs.forEach((np, i) => {
        const b = blocks[i]; if (!b || np === paras[i]) return;
        if (b.querySelector('b,strong,i,em,u,s,strike')) { skipped++; return; }   // com formatação dentro: não mexe (trocar o texto apagaria o negrito/itálico)
        const rg = document.createRange(); rg.selectNodeContents(b); X.ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(rg); document.execCommand('insertText', false, np); n++;
      });
      X.changed(); toast(t('{n} parágrafo(s) padronizado(s).', { n }) + (skipped ? ' ' + t('{s} com formatação foram mantidos.', { s: skipped }) : ''), 'ok');
    } catch (e) { toast(e.message, 'err'); }
  }
  const reviewTab = h('div', { class: 'sc-tabpane hidden', id: 'sc-pane-review' },
    h('section', { class: 'sc-sec' }, h('h4', null, t('Ortografia e gramática')), dictInfo,
      h('div', { class: 'row' }, h('button', { class: 'btn sm primary', id: 'sc-review', type: 'button', onclick: () => review(false) }, icon('check', 14), t('Revisar agora')), h('button', { class: 'btn sm', id: 'sc-review-ai', type: 'button', onclick: () => review(true), title: t('Gramática, concordância e pontuação com motivo (usa a IA)') }, icon('sparkle', 14), t('Revisar com IA'))),
      h('div', { class: 'row' }, h('button', { class: 'btn sm', id: 'sc-review-all', type: 'button', onclick: applyAll }, t('Aplicar todas')), h('button', { class: 'btn sm', id: 'sc-typo', type: 'button', onclick: typography, title: t('Aspas curvas, travessão de fala e reticências do idioma') }, t('Padronizar aspas e travessões'))),
      reviewInfo, issuesBox),
    h('section', { class: 'sc-sec' }, h('p', { class: 'hint' }, t('Enquanto você digita, o corretor do navegador sublinha erros no idioma do texto (mude o idioma na barra). «Revisar agora» usa regras e o dicionário do sistema, sem IA; «Revisar com IA» acrescenta gramática e concordância.'))));
  paintDict(!!(S.status.dictionaries || {})[X.lang()]);

  // ================================================================ aba Web (pesquisa nativa)
  const qIn = h('input', { id: 'sc-q', placeholder: t('Pesquisar na web…'), 'aria-label': t('Pesquisar na web') });
  const results = h('div', { class: 'sc-results', id: 'sc-results' }), pins = h('div', { class: 'sc-pins', id: 'sc-pins' });
  const saveSources = async () => { try { await S.api.put('/sources', { sources: st.sources }); } catch (e) { /* ok */ } };
  function paintPins() {
    srcLabel.classList.toggle('hidden', !st.sources.some((s) => s.pinned));
    pins.replaceChildren(...(st.sources.length ? st.sources.map((s) => h('div', { class: 'sc-pin-row' + (s.pinned ? ' on' : ''), dataset: { url: s.url } },
      h('div', { class: 'grow' }, h('a', { href: s.url, target: '_blank', rel: 'noopener noreferrer', title: s.url }, s.title || s.url), h('div', { class: 'small dim' }, s.pinned ? t('Fixada: entra no contexto da IA') : t('Guardada'))),
      h('button', { class: 'btn ghost sm', type: 'button', title: t('Inserir a referência no texto'), onclick: () => X.insertAtCaret(`(${s.title || s.url}. ${s.url})`) }, t('Inserir')),
      h('button', { class: 'btn ghost sm', type: 'button', title: t('Tirar da lista'), onclick: () => { st.sources = st.sources.filter((x) => x !== s); saveSources(); paintPins(); } }, '×'))) : [h('div', { class: 'muted small' }, t('Nenhuma fonte fixada. Pesquise, leia uma página e fixe-a: o texto dela entra no contexto das ações da IA.'))]));
  }
  async function search() {
    const q = qIn.value.trim(); if (!q) return;
    results.replaceChildren(h('div', { class: 'muted small' }, t('Pesquisando…')));
    try {
      const r = await api('/api/scriber/search', { method: 'POST', body: { query: q } });
      results.replaceChildren(...r.results.map((x) => h('div', { class: 'sc-result', dataset: { url: x.url } }, h('a', { href: x.url, target: '_blank', rel: 'noopener noreferrer' }, x.title), h('div', { class: 'small dim' }, x.host), h('div', { class: 'small' }, x.snippet),
        h('div', { class: 'row' }, h('button', { class: 'btn sm', type: 'button', dataset: { act: 'pin' }, onclick: async (e) => { const b = e.currentTarget; b.disabled = true; b.textContent = t('Lendo…'); try { const pg = await api('/api/scriber/search/read', { method: 'POST', body: { url: x.url } }); st.sources = st.sources.filter((s) => s.url !== x.url).concat([{ title: pg.title || x.title, url: x.url, note: '', text: pg.text, pinned: true }]); saveSources(); paintPins(); toast(t('Fonte fixada'), 'ok'); } catch (err) { toast(err.message, 'err'); } b.disabled = false; b.textContent = t('Ler e fixar'); } }, t('Ler e fixar')),
          h('button', { class: 'btn ghost sm', type: 'button', onclick: () => X.insertAtCaret(`(${x.title}. ${x.url})`) }, t('Inserir referência'))))));
      if (!r.results.length) results.replaceChildren(h('div', { class: 'muted small' }, t('Nada encontrado.')));
    } catch (e) { results.replaceChildren(h('div', { class: 'sc-pnote err' }, e.message)); }
  }
  qIn.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); search(); } });
  S.api.get('/sources').then((r) => { st.sources = r.sources || []; paintPins(); }).catch(() => paintPins());
  const webTab = h('div', { class: 'sc-tabpane hidden', id: 'sc-pane-web' },
    h('section', { class: 'sc-sec' }, h('h4', null, t('Pesquisa na web')), h('div', { class: 'row nw' }, qIn, h('button', { class: 'btn sm primary', id: 'sc-search', type: 'button', onclick: search }, icon('search', 14))), results),
    h('section', { class: 'sc-sec' }, h('h4', null, t('Fontes deste texto')), pins));

  // ================================================================ abas
  const TABS = [['ai', t('IA'), aiTab], ['review', t('Revisão'), reviewTab], ['web', t('Web'), webTab]];
  const tabBar = h('div', { class: 'sc-rtabs', role: 'tablist', id: 'sc-rtabs' });
  function setTab(id) { st.tab = id; TABS.forEach(([k, , el]) => el.classList.toggle('hidden', k !== id)); tabBar.querySelectorAll('button').forEach((b) => { b.classList.toggle('on', b.dataset.tab === id); b.setAttribute('aria-selected', String(b.dataset.tab === id)); }); }
  tabBar.append(...TABS.map(([id, label]) => h('button', { type: 'button', role: 'tab', dataset: { tab: id }, id: 'sc-rtab-' + id, onclick: () => setTab(id) }, label)));
  const el = h('aside', { class: 'sc-right', id: 'sc-right', 'aria-label': t('Expansão e IA') }, tabBar, h('div', { class: 'sc-rbody' }, ...TABS.map((x) => x[2])));
  paintSel(null); setTab('ai'); paintPins();
  return { el, setTab, run };
}
