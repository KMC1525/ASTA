// Scriber → Edição: editor simples no estilo Word (negrito, itálico, títulos, listas, alinhamento, quebra de página, localizar e substituir), lorebooks à esquerda, tamanho da expansão e IA à direita.
// Selecione parágrafos e falas com o mouse (modos «Parágrafo» e «Fala») ou livremente; a IA melhora, expande ou reescreve só o trecho, com o tamanho escolhido.
// O documento é um conjunto de blocos no servidor; aqui o <div contenteditable> só recebe HTML que o servidor gerou a partir de blocos validados (nada do usuário entra sem passar por lá).
import { t } from '../i18n.js';
import { FONT_FALLBACK, btn, ibtn, propertiesDialog } from '../scriber_ui.js';
import { countWords, dialogueAt, selectionKind } from '../scriber_text.js';
import { debounce, h, icon, select, toast } from '../ui.js';
import { createLorePanel } from './scriber_lore.js';
import { createSidePanel } from './scriber_side.js';

const MODE_KEY = 'asta.scriber.pick', ZOOM_KEY = 'asta.scriber.zoom', LORE_KEY = 'asta.scriber.lore.open';
const BLOCKS = 'p,h1,h2,h3,h4,h5,h6,blockquote,li';
const CM = 37.7953;   // px por cm a 96 dpi
const store = { get: (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ok */ } } };

export default async function render(body, S) {
  const cat = S.cat, cfg = S.cfg();
  let proj = S.proj, fmt = proj.format, lang = proj.language;
  const first = await S.api.doc();
  const st = { dirty: false, saving: false, pick: store.get(MODE_KEY, 'free'), zoomMode: store.get(ZOOM_KEY, 'fit'), zoom: 100, find: false };

  // ---------------------------------------------------------------- o papel (página) e o editor
  const ed = h('div', { class: 'sc-doc', id: 'sc-doc', contenteditable: 'true', role: 'textbox', 'aria-multiline': 'true', 'aria-label': t('Texto do documento'), spellcheck: cfg.spellcheck ? 'true' : 'false', lang });
  ed.innerHTML = first.html || '<p><br></p>';   // HTML gerado pelo servidor a partir de blocos validados (docmodel.blocks_to_html escapa tudo)
  if (!ed.firstChild) ed.innerHTML = '<p><br></p>';
  try { document.execCommand('defaultParagraphSeparator', false, 'p'); } catch (e) { /* ok */ }   // Enter cria <p> (e não <div>) também depois de um título
  const page = h('div', { class: 'sc-page', id: 'sc-page' }, ed);
  const titleIn = h('input', { class: 'sc-title', id: 'sc-title', value: proj.name, maxlength: 100, 'aria-label': t('Título do texto'), placeholder: t('Título') });
  const saveTitle = debounce(async () => { const v = titleIn.value.trim(); if (!v || v === S.proj.name) return; S.proj = proj = await S.api.put('', { name: v }); const b = document.querySelector('#sc-pname b'); if (b) b.textContent = v; document.title = 'ASTA — ' + v; }, 700);
  titleIn.addEventListener('input', saveTitle);
  S.onRename = (n) => { titleIn.value = n; };
  const pageBox = h('div', { class: 'sc-pagebox', id: 'sc-pagebox' }, titleIn, page);
  const pageWrap = h('div', { class: 'sc-pagewrap', id: 'sc-pagewrap' }, pageBox);

  function applyFormat() {
    const [w] = cat.pages[fmt.page] || [21], f = fmt, px = (v) => (v * CM).toFixed(1) + 'px';
    const s = page.style;
    s.setProperty('--pw', px(w)); s.setProperty('--pt', px(f.margins[0])); s.setProperty('--pb', px(f.margins[1])); s.setProperty('--pl', px(f.margins[2])); s.setProperty('--pr', px(f.margins[3]));
    s.setProperty('--pf', FONT_FALLBACK[f.font] || f.font); s.setProperty('--ps', (f.size * 4 / 3).toFixed(2) + 'px'); s.setProperty('--plh', String(f.line)); s.setProperty('--pi', px(f.indent));
    s.setProperty('--pal', f.align); s.setProperty('--pa', (f.space_after * 4 / 3).toFixed(1) + 'px');
    if (st.zoomMode === 'fit') { const avail = pageWrap.clientWidth - 44; st.zoom = avail > 0 ? Math.max(40, Math.min(100, Math.floor((avail / (w * CM + f.margins[2] * CM + f.margins[3] * CM)) * 100))) : 100; } else st.zoom = parseInt(st.zoomMode, 10) || 100;
    pageBox.style.zoom = String(st.zoom / 100);
    ed.setAttribute('lang', lang); ed.spellcheck = !!spellOn;
  }
  let spellOn = cfg.spellcheck;
  const saveFmt = debounce(async () => { try { S.proj = proj = await S.api.put('', { format: fmt, language: lang }); } catch (e) { toast(e.message, 'err'); } }, 600);

  // ---------------------------------------------------------------- salvar
  const state = h('span', { class: 'sc-save', id: 'sc-save' }, t('salvo'));
  const stats = h('span', { class: 'sc-stats', id: 'sc-stats' }), selInfo = h('span', { class: 'sc-selinfo', id: 'sc-selinfo' });
  const paintSave = () => { state.textContent = st.saving ? t('salvando…') : st.dirty ? t('não salvo') : t('salvo'); state.classList.toggle('dirty', st.dirty); };
  async function save(label) {
    if (st.saving) return; st.saving = true; paintSave();
    const html = ed.innerHTML;
    try { await S.api.saveDoc(html, label); if (ed.innerHTML === html) st.dirty = false; } catch (e) { toast(e.message, 'err'); } finally { st.saving = false; paintSave(); if (st.dirty && cfg.autosave) autosave(); }
  }
  const autosave = debounce(() => { if (st.dirty) save(); }, 1500);
  const paintStats = debounce(() => {
    const txt = ed.innerText || '', w = countWords(txt), wpp = (S.proj.gen && S.proj.gen.words_per_page) || 300;
    stats.textContent = t('{w} palavras · {c} caracteres · ≈ {p} páginas', { w, c: txt.replace(/\s/g, '').length, p: Math.max(w ? 1 : 0, Math.round((w / wpp) * 10) / 10) });
  }, 250);
  const changed = () => { st.dirty = true; paintSave(); paintStats(); if (cfg.autosave) autosave(); };
  ed.addEventListener('input', () => { fixStructure(); changed(); });
  // sempre há pelo menos um bloco, e texto solto vira parágrafo
  function fixStructure() {
    if (!ed.firstChild) { ed.innerHTML = '<p><br></p>'; return; }
    [...ed.childNodes].forEach((n) => { if (n.nodeType === 3 && n.textContent.trim()) { const p = document.createElement('p'); n.replaceWith(p); p.appendChild(n); const r = document.createRange(); r.setStart(n, n.textContent.length); r.collapse(true); const s = getSelection(); s.removeAllRanges(); s.addRange(r); } else if (n.nodeType === 3) n.remove(); });
  }
  const sanitize = (src) => {   // colar: só marcas permitidas (a lista de permissões do servidor decide de novo ao salvar)
    const doc = new DOMParser().parseFromString(src, 'text/html'), out = document.createElement('div');
    const ok = new Set(['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'UL', 'OL', 'LI', 'B', 'STRONG', 'I', 'EM', 'U', 'S', 'STRIKE', 'DEL', 'BR']);
    const walk = (n, into) => { n.childNodes.forEach((c) => { if (c.nodeType === 3) into.appendChild(document.createTextNode(c.textContent)); else if (c.nodeType === 1) { const tag = c.tagName; if (['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'SVG', 'IMG', 'HEAD'].includes(tag)) return; if (ok.has(tag)) { const e = document.createElement(tag.toLowerCase().replace('h4', 'h3').replace('h5', 'h3').replace('h6', 'h3')); into.appendChild(e); walk(c, e); } else if (['DIV', 'TR', 'SECTION', 'ARTICLE', 'PRE'].includes(tag)) { const e = document.createElement('p'); into.appendChild(e); walk(c, e); } else walk(c, into); } }); };
    walk(doc.body, out); return out.innerHTML;
  };
  ed.addEventListener('paste', (e) => {
    const dt = e.clipboardData; if (!dt) return; e.preventDefault();
    const htmlSrc = dt.getData('text/html'), plain = dt.getData('text/plain');
    if (htmlSrc) document.execCommand('insertHTML', false, sanitize(htmlSrc));
    else plain.split(/\r?\n/).forEach((ln, i) => { if (i) document.execCommand('insertParagraph'); if (ln) document.execCommand('insertText', false, ln); });
  });

  // ---------------------------------------------------------------- comandos da barra
  const cmd = (name, val) => { ed.focus(); document.execCommand(name, false, val); changed(); syncTools(); };
  const blockSel = select([['p', t('Parágrafo')], ['h1', t('Título 1')], ['h2', t('Título 2')], ['h3', t('Título 3')], ['blockquote', t('Citação')]], 'p', (v) => cmd('formatBlock', '<' + v + '>'), { id: 'sc-block', 'aria-label': t('Estilo do bloco'), title: t('Estilo do bloco') });
  const tb = (title, ic, fn, id, label) => h('button', { class: 'sc-tb', type: 'button', title, 'aria-label': title, id, onmousedown: (e) => e.preventDefault(), onclick: fn }, label ? h('b', null, label) : icon(ic, 15));
  const tbB = tb(t('Negrito (Ctrl+B)'), '', () => cmd('bold'), 'sc-b', 'B'), tbI = tb(t('Itálico (Ctrl+I)'), '', () => cmd('italic'), 'sc-i', 'I'), tbU = tb(t('Sublinhado (Ctrl+U)'), '', () => cmd('underline'), 'sc-u', 'U'), tbS = tb(t('Riscado'), '', () => cmd('strikeThrough'), 'sc-s', 'S');
  tbI.firstChild.style.fontStyle = 'italic'; tbU.firstChild.style.textDecoration = 'underline'; tbS.firstChild.style.textDecoration = 'line-through';
  function syncTools() {
    try { [[tbB, 'bold'], [tbI, 'italic'], [tbU, 'underline'], [tbS, 'strikeThrough']].forEach(([b, c]) => b.classList.toggle('on', document.queryCommandState(c))); } catch (e) { /* ok */ }
    const n = blockOf(getSelection().anchorNode); if (n) blockSel.value = ['h1', 'h2', 'h3', 'blockquote'].includes(n.tagName.toLowerCase()) ? n.tagName.toLowerCase() : 'p';
  }
  // quebra de página e linha horizontal entram DEPOIS do bloco onde está o cursor (inserir por cima de uma seleção apagaria o texto selecionado)
  function caretAfterBlock() {
    ed.focus(); const s = getSelection(); if (!s.rangeCount) return;
    const b = blockOf(s.getRangeAt(0).endContainer) || ed.lastElementChild, r = document.createRange();
    if (b) { r.selectNodeContents(b); r.collapse(false); s.removeAllRanges(); s.addRange(r); document.execCommand('insertParagraph'); }
  }
  const insertPB = () => { caretAfterBlock(); document.execCommand('insertHTML', false, '<div class="pb" contenteditable="false"></div><p><br></p>'); changed(); };
  const insertHR = () => { caretAfterBlock(); document.execCommand('insertHorizontalRule'); changed(); };
  const fontSel = select(cat.fonts.map((f) => [f, f]), fmt.font, (v) => { fmt.font = v; applyFormat(); saveFmt(); }, { id: 'sc-font', 'aria-label': t('Fonte'), title: t('Fonte do documento') });
  const sizeIn = h('input', { type: 'number', class: 'sc-fsize', id: 'sc-fsize', min: 8, max: 24, step: 0.5, value: fmt.size, 'aria-label': t('Tamanho da fonte'), title: t('Tamanho da fonte (pt)') });
  sizeIn.addEventListener('input', () => { const v = parseFloat(sizeIn.value); if (v >= 8 && v <= 24) { fmt.size = v; applyFormat(); saveFmt(); } });
  const langSel = select(Object.entries(cat.languages).map(([k, v]) => [k, t(v)]), lang, (v) => { lang = v; applyFormat(); saveFmt(); X.langChanged && X.langChanged(); }, { id: 'sc-lang', 'aria-label': t('Idioma do texto'), title: t('Idioma do texto: o corretor e a IA usam este') });
  const spellBtn = tb(t('Corretor ortográfico do navegador'), 'check', () => { spellOn = !spellOn; spellBtn.classList.toggle('on', spellOn); ed.spellcheck = spellOn; ed.blur(); ed.focus(); }, 'sc-spell'); spellBtn.classList.toggle('on', spellOn);
  const zoomSel = select([['fit', t('Ajustar')], ['70', '70%'], ['85', '85%'], ['100', '100%'], ['120', '120%'], ['150', '150%']], st.zoomMode, (v) => { st.zoomMode = v; store.set(ZOOM_KEY, v); applyFormat(); }, { id: 'sc-zoom', 'aria-label': 'Zoom', title: 'Zoom' });
  const pickSeg = h('div', { class: 'seg sc-pickseg', id: 'sc-pick', role: 'radiogroup', 'aria-label': t('Modo de seleção com o mouse') });
  const PICKS = [['free', t('Livre'), t('Selecione e digite normalmente')], ['par', t('Parágrafo'), t('Clique num parágrafo para selecioná-lo (Shift+clique estende)')], ['dlg', t('Fala'), t('Clique numa fala (travessão ou aspas) para selecioná-la')]];
  function paintPick() {
    pickSeg.replaceChildren(...PICKS.map(([id, label, title]) => h('button', { type: 'button', role: 'radio', 'aria-checked': String(st.pick === id), class: st.pick === id ? 'on' : '', title, dataset: { pick: id }, onclick: () => setPick(id) }, label)));
    ed.classList.toggle('pick', st.pick !== 'free'); pageWrap.dataset.pick = st.pick;
  }
  function setPick(id) { st.pick = id; store.set(MODE_KEY, id); paintPick(); clearHover(); if (id !== 'free') toast(id === 'par' ? t('Clique num parágrafo para selecioná-lo. Volte para «Livre» para digitar.') : t('Clique numa fala para selecioná-la. Volte para «Livre» para digitar.')); }

  const row1 = h('div', { class: 'sc-trow' },
    tb(t('Desfazer (Ctrl+Z)'), 'undo', () => cmd('undo'), 'sc-undo'), tb(t('Refazer (Ctrl+Y)'), 'redo', () => cmd('redo'), 'sc-redo'), h('span', { class: 'sc-sep' }),
    blockSel, h('span', { class: 'sc-sep' }), tbB, tbI, tbU, tbS, h('span', { class: 'sc-sep' }),
    tb(t('Alinhar à esquerda'), 'alignl', () => cmd('justifyLeft'), 'sc-al'), tb(t('Centralizar'), 'alignc', () => cmd('justifyCenter'), 'sc-ac'), tb(t('Alinhar à direita'), 'alignr', () => cmd('justifyRight'), 'sc-ar'), tb(t('Justificar'), 'alignj', () => cmd('justifyFull'), 'sc-aj'), h('span', { class: 'sc-sep' }),
    tb(t('Lista com marcadores'), 'listul', () => cmd('insertUnorderedList'), 'sc-ul'), tb(t('Lista numerada'), 'listol', () => cmd('insertOrderedList'), 'sc-ol'), tb(t('Aumentar recuo'), 'indent', () => cmd('indent'), 'sc-in'), tb(t('Diminuir recuo'), 'outdent', () => cmd('outdent'), 'sc-out'), h('span', { class: 'sc-sep' }),
    tb(t('Linha horizontal'), 'minus', insertHR, 'sc-hr'), tb(t('Quebra de página'), 'pagebreak', insertPB, 'sc-pb'), tb(t('Localizar e substituir (Ctrl+H)'), 'search', () => toggleFind(), 'sc-findbtn'));
  const row2 = h('div', { class: 'sc-trow' }, toggleLoreBtn(), pickSeg, h('span', { class: 'sc-sep' }), fontSel, sizeIn, langSel, spellBtn, h('span', { class: 'grow' }), zoomSel,
    ibtn(t('Propriedades do documento'), 'config', () => propertiesDialog(S, async (p) => { proj = S.proj = p; fmt = p.format; lang = p.language; fontSel.value = fmt.font; sizeIn.value = fmt.size; langSel.value = lang; applyFormat(); }), '', { id: 'sc-props' }));

  function toggleLoreBtn() { return h('button', { class: 'sc-loretoggle', id: 'sc-lore-toggle', type: 'button', title: t('Mostrar ou esconder os lorebooks'), onclick: () => { document.getElementById('sc-grid').classList.toggle('nolore'); store.set(LORE_KEY, document.getElementById('sc-grid').classList.contains('nolore') ? '0' : '1'); setTimeout(applyFormat, 0); } }, icon('book', 14), t('Lorebooks')); }
  const toolbar = h('div', { class: 'sc-toolbar', id: 'sc-toolbar', role: 'toolbar', 'aria-label': t('Formatação') }, row1, row2);

  // ---------------------------------------------------------------- localizar e substituir
  const findIn = h('input', { id: 'sc-find', placeholder: t('Localizar'), 'aria-label': t('Localizar') }), repIn = h('input', { id: 'sc-replace', placeholder: t('Substituir por'), 'aria-label': t('Substituir por') });
  const caseChk = h('input', { type: 'checkbox', id: 'sc-case' });
  const findInfo = h('span', { class: 'dim small', id: 'sc-find-info' });
  const findBar = h('div', { class: 'sc-findbar hidden', id: 'sc-findbar' }, findIn, repIn, h('label', { class: 'check' }, caseChk, h('span', null, t('Maiúsc./minúsc.'))),
    btn(t('Anterior'), '', () => findNext(true), '', { id: 'sc-fprev' }), btn(t('Próximo'), '', () => findNext(false), '', { id: 'sc-fnext' }), btn(t('Substituir'), '', replaceOne, '', { id: 'sc-frep' }), btn(t('Substituir tudo'), '', replaceAll, '', { id: 'sc-frepall' }), findInfo, ibtn(t('Fechar'), 'x', () => toggleFind(false)));
  function toggleFind(on) { st.find = on == null ? !st.find : on; findBar.classList.toggle('hidden', !st.find); if (st.find) { const s = getSelection().toString(); if (s && s.length < 80 && !s.includes('\n')) findIn.value = s; findIn.focus(); findIn.select(); } }
  function findNext(back) {
    if (!findIn.value) return; ed.focus();
    const ok = window.find(findIn.value, caseChk.checked, !!back, true, false, false, false);
    findInfo.textContent = ok ? '' : t('Não encontrado'); return ok;
  }
  function replaceOne() { const s = getSelection(); if (s.toString() && (caseChk.checked ? s.toString() === findIn.value : s.toString().toLowerCase() === findIn.value.toLowerCase())) { ed.focus(); document.execCommand('insertText', false, repIn.value); changed(); } findNext(false); }
  function replaceAll() {
    if (!findIn.value) return; ed.focus();
    const r = document.createRange(); r.setStart(ed, 0); r.collapse(true); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    let n = 0; while (n < 5000 && window.find(findIn.value, caseChk.checked, false, false, false, false, false)) { if (!ed.contains(getSelection().anchorNode)) break; document.execCommand('insertText', false, repIn.value); n++; }
    findInfo.textContent = t('{n} substituição(ões)', { n }); if (n) changed();
  }

  // ---------------------------------------------------------------- seleção: blocos, falas, offsets
  const blockOf = (node) => { let n = node && node.nodeType === 3 ? node.parentNode : node; while (n && n !== ed) { if (n.matches && n.matches(BLOCKS)) return n; n = n.parentNode; } return null; };
  const allBlocks = () => [...ed.querySelectorAll(BLOCKS)];
  function textNodes(el) { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), out = []; let n; while ((n = w.nextNode())) out.push(n); return out; }
  function rangeFromOffsets(el, start, end) {
    const r = document.createRange(); let pos = 0, a = false;
    for (const n of textNodes(el)) { const len = n.textContent.length; if (!a && start <= pos + len) { r.setStart(n, start - pos); a = true; } if (a && end <= pos + len) { r.setEnd(n, end - pos); return r; } pos += len; }
    if (!a) return null; const last = textNodes(el).pop(); r.setEnd(last, last.textContent.length); return r;
  }
  const offsetIn = (el, node, off) => { const r = document.createRange(); r.setStart(el, 0); r.setEnd(node, off); return r.toString().length; };
  function caretAt(x, y) {
    if (document.caretPositionFromPoint) { const p = document.caretPositionFromPoint(x, y); return p ? { node: p.offsetNode, offset: p.offset } : null; }
    if (document.caretRangeFromPoint) { const r = document.caretRangeFromPoint(x, y); return r ? { node: r.startContainer, offset: r.startOffset } : null; }
    return null;
  }
  // Um triplo clique (ou arrastar até o começo da linha de baixo) deixa o fim da seleção no início do bloco seguinte: aqui o fim volta para o fim do bloco anterior,
  // senão trocar o trecho juntaria dois parágrafos.
  function trimRange(range) {
    const eb = blockOf(range.endContainer), sb = blockOf(range.startContainer);
    if (!eb || eb === sb || range.collapsed || offsetIn(eb, range.endContainer, range.endOffset) !== 0) return range;
    const bs = allBlocks(), prev = bs[bs.indexOf(eb) - 1]; if (!prev) return range;
    const tn = textNodes(prev), last = tn[tn.length - 1]; if (!last) return range;
    const r = range.cloneRange(); r.setEnd(last, last.textContent.length); return r;
  }
  function getSel() {
    const s = getSelection(); if (!s.rangeCount || !ed.contains(s.anchorNode) || !ed.contains(s.focusNode)) return { empty: true, text: '', lines: [], kind: 'paragraph', range: null };
    const range = trimRange(s.getRangeAt(0)), raw = range.toString().replace(/\u00a0/g, ' '), lines = raw.split(/\n+/).map((x) => x.trim()).filter(Boolean);
    return { empty: !raw.trim(), text: raw, lines, kind: selectionKind(lines), range, words: countWords(raw), collapsed: range.collapsed };
  }
  function selectRange(r) { const s = getSelection(); s.removeAllRanges(); s.addRange(r); onSelection(); }
  let hoverEl = null, anchorBlock = null;
  const clearHover = () => { if (hoverEl) { hoverEl.classList.remove('sc-hover'); hoverEl = null; } };
  ed.addEventListener('mousemove', (e) => {
    if (st.pick === 'free') return; const b = e.target.closest && e.target.closest(BLOCKS); if (b === hoverEl || !b || !ed.contains(b)) return;
    clearHover(); if (st.pick === 'dlg') { const txt = b.textContent; if (!dialogueAt(txt, 0) && !/["“«„]/.test(txt)) return; } hoverEl = b; b.classList.add('sc-hover');
  });
  ed.addEventListener('mouseleave', clearHover);
  ed.addEventListener('mousedown', (e) => {
    if (st.pick === 'free' || e.button !== 0) return;
    const b = e.target.closest && e.target.closest(BLOCKS); if (!b || !ed.contains(b)) return;
    e.preventDefault(); ed.focus();
    let r = document.createRange();
    if (st.pick === 'par') {
      if (e.shiftKey && anchorBlock && ed.contains(anchorBlock)) { const bs = [anchorBlock, b].sort((x, y) => (x.compareDocumentPosition(y) & 4 ? -1 : 1)); r.setStart(bs[0], 0); r.setEnd(bs[1], bs[1].childNodes.length); } else { r.selectNodeContents(b); anchorBlock = b; }
    } else {
      const c = caretAt(e.clientX, e.clientY), txt = b.textContent, off = c && b.contains(c.node) ? offsetIn(b, c.node, c.offset) : 0, d = dialogueAt(txt, off);
      if (!d) { toast(t('Não achei uma fala aí. Fala = linha com travessão ou trecho entre aspas.')); return; }
      const rr = rangeFromOffsets(b, d.start, d.end) || (r.selectNodeContents(b), r);
      if (e.shiftKey && anchorBlock && ed.contains(anchorBlock)) { const bs = [anchorBlock, b].sort((x, y) => (x.compareDocumentPosition(y) & 4 ? -1 : 1)); r = document.createRange(); r.setStart(bs[0], 0); r.setEnd(bs[1], bs[1].childNodes.length); } else { r = rr; anchorBlock = b; }
    }
    selectRange(r);
  });

  // ---------------------------------------------------------------- barra flutuante sobre a seleção
  let floatEl = null;
  const hideFloat = () => { if (floatEl) { floatEl.remove(); floatEl = null; } };
  function onSelection() {
    const s = getSel(); X.selChanged && X.selChanged(s);
    selInfo.textContent = s.empty ? '' : t('Seleção: {w} palavras', { w: s.words }) + ' · ' + (s.kind === 'dialogue' ? t('fala') : s.kind === 'mixed' ? t('misto') : t('parágrafo'));
    hideFloat(); if (s.empty || s.text.trim().length < 4 || !X.floatActions) return;
    const rect = s.range.getBoundingClientRect(); if (!rect || (!rect.width && !rect.height)) return;
    floatEl = h('div', { class: 'sc-float', id: 'sc-float', onmousedown: (e) => e.preventDefault(), style: { left: Math.max(8, Math.min(innerWidth - 330, rect.left + rect.width / 2 - 150)) + 'px', top: Math.max(8, rect.top - 44) + 'px' } },
      X.floatActions().map(([id, label]) => h('button', { type: 'button', dataset: { float: id }, onclick: () => { hideFloat(); X.run(id); } }, label)));
    document.body.appendChild(floatEl);
  }
  const selSoon = debounce(onSelection, 120);
  ed.addEventListener('mouseup', () => setTimeout(onSelection, 0));
  ed.addEventListener('keyup', (e) => { if (e.shiftKey || e.key.startsWith('Arrow') || e.key === 'Shift') selSoon(); syncTools(); });
  document.addEventListener('selectionchange', () => { if (!ed.contains(getSelection().anchorNode)) return; syncTools(); });
  const offFloat = (e) => { if (floatEl && !floatEl.contains(e.target) && !ed.contains(e.target)) hideFloat(); };
  document.addEventListener('mousedown', offFloat);
  pageWrap.addEventListener('scroll', hideFloat);
  ed.addEventListener('keydown', (e) => {
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === 's') { e.preventDefault(); save(); toast(t('Salvo'), 'ok'); }
    else if ((e.ctrlKey || e.metaKey) && k === 'h') { e.preventDefault(); toggleFind(true); }
    else if (e.altKey && (k === 'p' || e.code === 'KeyP')) { e.preventDefault(); const b = blockOf(getSelection().anchorNode); if (b) { const r = document.createRange(); r.selectNodeContents(b); selectRange(r); } }
    else if (e.altKey && (k === 'd' || e.code === 'KeyD')) { e.preventDefault(); const s = getSelection(), b = blockOf(s.anchorNode); if (b) { const d = dialogueAt(b.textContent, offsetIn(b, s.anchorNode, s.anchorOffset)); if (d) selectRange(rangeFromOffsets(b, d.start, d.end)); else toast(t('Não achei uma fala aí. Fala = linha com travessão ou trecho entre aspas.')); } }
    else if (e.key === 'Escape' && st.pick !== 'free') setPick('free');
  });
  findIn.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); findNext(e.shiftKey); } if (e.key === 'Escape') toggleFind(false); });

  // ---------------------------------------------------------------- aplicar texto da IA no documento (com desfazer nativo: Ctrl+Z)
  function applyText(range, lines, how) {
    ed.focus(); const s = getSelection(); s.removeAllRanges();
    let r = range.cloneRange();
    if (how === 'after') { const b = blockOf(r.endContainer) || ed.lastElementChild; if (b) { r.selectNodeContents(b); r.collapse(false); } else r.collapse(false); s.addRange(r); document.execCommand('insertParagraph'); }
    else { s.addRange(r); if (!r.collapsed) document.execCommand('delete'); }
    lines.forEach((ln, i) => { if (i) document.execCommand('insertParagraph'); if (ln) document.execCommand('insertText', false, ln); });
    changed(); onSelection();
  }

  // ---------------------------------------------------------------- a API que o painel da direita usa
  const X = { ed, S, getSel, selectRange, applyText, changed, blocks: allBlocks, textNodes, rangeFromOffsets, blockOf, lang: () => lang, setLang: (v) => { lang = v; langSel.value = v; applyFormat(); saveFmt(); }, save, hideFloat,
    contextAround(range) { const b = document.createRange(), a = document.createRange(); b.setStart(ed, 0); b.setEnd(range.startContainer, range.startOffset); a.setStart(range.endContainer, range.endOffset); a.setEnd(ed, ed.childNodes.length); return { before: b.toString().slice(-2500), after: a.toString().slice(0, 1500) }; },
    insertAtCaret(text) { ed.focus(); document.execCommand('insertText', false, text); changed(); } };
  const lore = await createLorePanel(S, { onToggle: (on) => { X.loreToggled && X.loreToggled(on); } });
  X.lore = lore;
  const side = createSidePanel(S, X);

  // ---------------------------------------------------------------- montagem
  const left = lore.el;
  const loreOpen = store.get(LORE_KEY, '1') === '1';
  const center = h('section', { class: 'sc-center', id: 'sc-center' }, toolbar, findBar, pageWrap, h('div', { class: 'sc-status' }, stats, selInfo, h('span', { class: 'grow' }), state));
  const grid = h('div', { class: 'sc-grid' + (loreOpen ? '' : ' nolore'), id: 'sc-grid' }, left, center, side.el);
  body.replaceChildren(grid);
  applyFormat(); paintPick(); paintSave(); paintStats(); syncTools();
  if (typeof ResizeObserver !== 'undefined') { const ro = new ResizeObserver(() => { if (st.zoomMode === 'fit') applyFormat(); }); ro.observe(pageWrap); S.onCleanup(() => ro.disconnect()); }
  window.addEventListener('beforeunload', flush);
  function flush() { if (st.dirty) save(); }
  S.onCleanup(() => { flush(); hideFloat(); document.removeEventListener('mousedown', offFloat); window.removeEventListener('beforeunload', flush); X.dispose && X.dispose(); });
  if (S.ctx && S.ctx.focus !== false) setTimeout(() => { try { ed.focus(); } catch (e) { /* ok */ } }, 50);
}
