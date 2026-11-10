// Editor de texto/código leve (sem dependências): números de linha, realce de sintaxe (JS, JSON, CSS, HTML, Markdown), recuo automático, Tab, Ctrl+S e busca.
// Técnica: um <textarea> transparente por cima de um <pre> com o texto colorido (os dois com a mesma fonte e rolagem sincronizada). Nunca usa innerHTML com texto do usuário sem escapar.
import { t } from './i18n.js';
import { h } from './ui.js';

const esc = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const KW = 'var|let|const|function|return|if|else|for|while|do|break|continue|switch|case|default|new|this|typeof|instanceof|in|of|try|catch|finally|throw|class|extends|null|undefined|true|false|async|await|yield|delete|void';
const RULES = {
  js: [['c', '\\/\\/[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/'], ['s', '\'(?:\\\\.|[^\'\\\\\\n])*\'|"(?:\\\\.|[^"\\\\\\n])*"|`(?:\\\\.|[^`\\\\])*`'], ['n', '\\b\\d+(?:\\.\\d+)?\\b'], ['g', '\\bGE(?:\\.[A-Za-z_]+)*'], ['k', '\\b(?:' + KW + ')\\b'], ['f', '\\b[A-Za-z_$][\\w$]*(?=\\s*\\()']],
  json: [['k', '"(?:\\\\.|[^"\\\\\\n])*"(?=\\s*:)'], ['s', '"(?:\\\\.|[^"\\\\\\n])*"'], ['n', '-?\\b\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?\\b'], ['g', '\\b(?:true|false|null)\\b']],
  css: [['c', '\\/\\*[\\s\\S]*?\\*\\/'], ['s', '\'[^\'\\n]*\'|"[^"\\n]*"'], ['n', '#[0-9a-fA-F]{3,8}\\b|-?\\b\\d+(?:\\.\\d+)?(?:px|em|rem|%|vh|vw|s|ms)?\\b'], ['k', '[A-Za-z-]+(?=\\s*:)'], ['f', '[.#][\\w-]+']],
  html: [['c', '<!--[\\s\\S]*?-->'], ['k', '<\\/?[A-Za-z][\\w-]*'], ['s', '"[^"\\n]*"|\'[^\'\\n]*\''], ['g', '\\s[\\w-]+(?==)']],
  md: [['k', '^#{1,6}[^\\n]*'], ['s', '`[^`\\n]+`'], ['g', '\\*\\*[^*\\n]+\\*\\*|__[^_\\n]+__'], ['f', '^\\s*(?:[-*+]|\\d+\\.)\\s'], ['c', '^>[^\\n]*|<!--[\\s\\S]*?-->'], ['n', '^[A-ZÀ-Ý][\\wÀ-ÿ ]{0,28}:(?=\\s)']],
};
const COMPILED = {};
function compile(lang) {
  if (COMPILED[lang] !== undefined) return COMPILED[lang];
  const r = RULES[lang]; if (!r) return (COMPILED[lang] = null);
  const src = r.map((x) => '(' + x[1] + ')').join('|');
  return (COMPILED[lang] = { re: new RegExp(src, lang === 'md' ? 'gm' : 'g'), cls: r.map((x) => x[0]) });
}
export function langOf(path) {
  const e = String(path || '').split('.').pop().toLowerCase();
  return { js: 'js', mjs: 'js', json: 'json', css: 'css', html: 'html', svg: 'html', xml: 'html', md: 'md', markdown: 'md', txt: 'md', dialogue: 'md', gdd: 'md' }[e] || 'text';
}
export function highlight(code, lang) {
  const c = compile(lang);
  if (!c || code.length > 250000) return esc(code) + '\n';
  let out = '', last = 0, m;
  c.re.lastIndex = 0;
  while ((m = c.re.exec(code))) {
    if (m[0] === '') { c.re.lastIndex++; continue; }
    let i = 1; while (i < m.length && m[i] === undefined) i++;
    out += esc(code.slice(last, m.index)) + '<span class="tk-' + c.cls[i - 1] + '">' + esc(m[0]) + '</span>';
    last = m.index + m[0].length;
  }
  return out + esc(code.slice(last)) + '\n';
}

// opts: { value, lang, readOnly, lineNumbers (true), onChange(value), onSave(), onCursor({line, col, sel}), wrap (false), placeholder, minHeight }
export function createEditor(opts = {}) {
  let lang = opts.lang || 'text', changeCb = opts.onChange, lastValue = opts.value || '';
  const ta = h('textarea', { class: 'ge-ed-ta', spellcheck: opts.spellcheck === true ? 'true' : 'false', autocapitalize: 'off', autocomplete: 'off', wrap: opts.wrap ? 'soft' : 'off', placeholder: opts.placeholder || '', 'aria-label': opts.label || t('Editor de texto') });
  ta.value = lastValue; if (opts.readOnly) ta.readOnly = true;
  const code = h('code'); const pre = h('pre', { class: 'ge-ed-hl', 'aria-hidden': 'true' }, code);
  const gut = h('div', { class: 'ge-ed-gut', 'aria-hidden': 'true' });
  const body = h('div', { class: 'ge-ed-body' }, pre, ta);
  const el = h('div', { class: 'ge-ed' + (opts.wrap ? ' wrap' : '') + (opts.lineNumbers === false ? ' nonum' : '') }, opts.lineNumbers === false ? null : gut, body);
  if (opts.minHeight) el.style.minHeight = opts.minHeight;
  let lines = 0;
  const paint = () => {
    code.innerHTML = highlight(ta.value, lang);
    const n = ta.value.split('\n').length;
    if (n !== lines && opts.lineNumbers !== false) { lines = n; gut.textContent = Array.from({ length: n }, (_, i) => i + 1).join('\n'); }
  };
  const sync = () => { pre.scrollTop = ta.scrollTop; pre.scrollLeft = ta.scrollLeft; gut.scrollTop = ta.scrollTop; };
  const cursor = () => {
    if (!opts.onCursor) return;
    const pos = ta.selectionStart, before = ta.value.slice(0, pos), line = before.split('\n').length, col = pos - before.lastIndexOf('\n');
    opts.onCursor({ line, col, sel: Math.abs(ta.selectionEnd - ta.selectionStart) });
  };
  ta.addEventListener('input', () => { paint(); sync(); lastValue = ta.value; if (changeCb) changeCb(ta.value); cursor(); });
  ta.addEventListener('scroll', sync);
  ['keyup', 'click', 'select', 'focus'].forEach((ev) => ta.addEventListener(ev, cursor));
  const indentOf = (txt, pos) => { const ls = txt.lastIndexOf('\n', pos - 1) + 1; const m = /^[ \t]*/.exec(txt.slice(ls, pos)); return m ? m[0] : ''; };
  const edit = (start, end, text, selStart, selEnd) => {   // mantém o desfazer nativo do navegador quando possível
    ta.focus(); ta.setSelectionRange(start, end);
    let ok = false; try { ok = document.execCommand('insertText', false, text); } catch (e) { ok = false; }
    if (!ok) { ta.setRangeText(text, start, end, 'end'); ta.dispatchEvent(new Event('input', { bubbles: true })); }
    if (selStart != null) ta.setSelectionRange(selStart, selEnd == null ? selStart : selEnd);
  };
  ta.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); if (opts.onSave) opts.onSave(); return; }
    if (opts.readOnly) return;
    const s = ta.selectionStart, en = ta.selectionEnd, v = ta.value;
    if (e.key === 'Tab') {
      e.preventDefault();
      if (s !== en && v.slice(s, en).includes('\n')) {   // recua/avança as linhas selecionadas
        const ls = v.lastIndexOf('\n', s - 1) + 1, block = v.slice(ls, en), out = e.shiftKey ? block.replace(/^( {1,2}|\t)/gm, '') : block.replace(/^/gm, '  ');
        edit(ls, en, out, ls, ls + out.length);
      } else if (e.shiftKey) { const ls = v.lastIndexOf('\n', s - 1) + 1; const m = /^( {1,2}|\t)/.exec(v.slice(ls)); if (m) edit(ls, ls + m[0].length, '', Math.max(ls, s - m[0].length)); }
      else edit(s, en, '  ');
    } else if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey && !e.isComposing && (lang === 'js' || lang === 'json' || lang === 'css' || lang === 'html')) {
      e.preventDefault();
      const ind = indentOf(v, s), prev = v[s - 1], next = v[s];
      if ((prev === '{' || prev === '[' || prev === '(') && (next === '}' || next === ']' || next === ')')) edit(s, en, '\n' + ind + '  \n' + ind, s + 1 + ind.length + 2);
      else edit(s, en, '\n' + ind + (prev === '{' || prev === '[' || prev === '(' ? '  ' : ''));
    }
  });
  paint();
  return {
    el, ta,
    get: () => ta.value,
    set(v, l) { if (l) lang = l; ta.value = v == null ? '' : String(v); lastValue = ta.value; lines = 0; paint(); sync(); ta.scrollTop = 0; },
    setLang(l) { lang = l; paint(); },
    focus: () => ta.focus(),
    onChange(fn) { changeCb = fn; },
    selection() { return { start: ta.selectionStart, end: ta.selectionEnd, text: ta.value.slice(ta.selectionStart, ta.selectionEnd) }; },
    replaceRange(start, end, text) { edit(start, end, text, start, start + text.length); },
    insert(text) { edit(ta.selectionStart, ta.selectionEnd, text); },
    select(start, end) { ta.focus(); ta.setSelectionRange(start, end); },
    goto(line) { const ls = ta.value.split('\n'); let pos = 0; for (let i = 0; i < Math.min(line - 1, ls.length - 1); i++) pos += ls[i].length + 1; ta.focus(); ta.setSelectionRange(pos, pos + (ls[line - 1] || '').length); const lh = parseFloat(getComputedStyle(ta).lineHeight) || 20; ta.scrollTop = Math.max(0, (line - 4) * lh); sync(); },
    find(q, from) { if (!q) return -1; const idx = ta.value.toLowerCase().indexOf(q.toLowerCase(), from == null ? ta.selectionEnd : from); const at = idx < 0 ? ta.value.toLowerCase().indexOf(q.toLowerCase(), 0) : idx; if (at >= 0) { ta.focus(); ta.setSelectionRange(at, at + q.length); const line = ta.value.slice(0, at).split('\n').length, lh = parseFloat(getComputedStyle(ta).lineHeight) || 20; ta.scrollTop = Math.max(0, (line - 4) * lh); sync(); } return at; },
    refresh: () => { paint(); sync(); },
  };
}
