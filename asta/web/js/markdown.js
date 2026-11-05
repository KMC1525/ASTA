// Markdown seguro para as respostas do Chat: monta nós DOM (nunca innerHTML), então nada que o modelo escreva vira HTML/script.
// Cobre o que as respostas costumam usar: títulos, negrito/itálico/tachado, `código`, blocos de código com «copiar», listas, citações, tabelas, linhas e links http(s).
import { t } from './i18n.js';
import { h } from './ui.js';

// `CITE` (definido por renderMarkdown quando a tela pede): {has(n), open(n), title(n)} — os [1], [2]… das respostas com busca na web viram botões que levam à fonte
let CITE = null;
const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|~~[^~\n]+~~|\*[^*\s][^*\n]*\*|(?<![\w])_[^_\s][^_\n]*_(?![\w])|\[[^\]\n]+\]\([^)\s]+\)|\[\d{1,2}(?:\s*,\s*\d{1,2})*\](?!\()|https?:\/\/[^\s<>()\[\]`]+[^\s<>()\[\]`.,;:!?'"])/g;

export function inline(parent, src) {
  const cite = CITE;   // os botões de citação usam o objeto da hora do desenho (o CITE global volta ao valor anterior quando renderMarkdown termina)
  String(src || '').split(INLINE).forEach((part) => {
    if (!part) return;
    let m;
    if (part.length > 2 && part[0] === '`' && part.endsWith('`')) parent.appendChild(h('code', null, part.slice(1, -1)));
    else if ((m = /^\*\*([^*\n]+)\*\*$/.exec(part)) || (m = /^__([^_\n]+)__$/.exec(part))) parent.appendChild(h('strong', null, m[1]));
    else if ((m = /^~~([^~\n]+)~~$/.exec(part))) parent.appendChild(h('del', null, m[1]));
    else if ((m = /^\*([^*\s][^*\n]*)\*$/.exec(part)) || (m = /^_([^_\s][^_\n]*)_$/.exec(part))) parent.appendChild(h('em', null, m[1]));
    else if ((m = /^\[([^\]\n]+)\]\(([^)\s]+)\)$/.exec(part))) {
      if (/^(https?:\/\/|mailto:)/i.test(m[2])) parent.appendChild(h('a', { href: m[2], target: '_blank', rel: 'noopener noreferrer' }, m[1]));
      else parent.appendChild(document.createTextNode(part));  // javascript:, data: etc. nunca viram link
    } else if (/^\[\d{1,2}(?:\s*,\s*\d{1,2})*\]$/.test(part)) {   // citação [1] ou [1, 2]
      const nums = part.slice(1, -1).split(',').map((x) => parseInt(x, 10));
      if (cite && nums.every((n) => cite.has(n))) nums.forEach((n) => parent.appendChild(h('button', { class: 'cite', type: 'button', title: cite.title(n), onclick: () => cite.open(n) }, String(n))));
      else parent.appendChild(document.createTextNode(part));
    } else if (/^https?:\/\//i.test(part)) parent.appendChild(h('a', { href: part, target: '_blank', rel: 'noopener noreferrer' }, part));   // endereço solto no texto
    else parent.appendChild(document.createTextNode(part));
  });
}

const cells = (line) => line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());

export function renderMarkdown(el, src, opts) {
  const prev = CITE;
  if (opts && 'cite' in opts) CITE = opts.cite || null;
  try { return draw(el, src); } finally { CITE = prev; }
}

const LI = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const indentOf = (s) => s.replace(/\t/g, '    ').length;

// lista (com sub-listas pela indentação): devolve o elemento e a próxima linha
function listBlock(lines, i, indent) {
  const first = LI.exec(lines[i]), ordered = /\d/.test(first[2]), ul = h(ordered ? 'ol' : 'ul');
  if (ordered && parseInt(first[2], 10) > 1) ul.setAttribute('start', parseInt(first[2], 10));
  while (i < lines.length) {
    const m = LI.exec(lines[i]);
    if (!m) break;
    const ind = indentOf(m[1]);
    if (ind < indent) break;
    if (ind > indent) {   // item mais recuado: sub-lista do item anterior
      const parent = ul.lastElementChild;
      if (!parent) break;
      const r = listBlock(lines, i, ind); parent.appendChild(r.el); i = r.i; continue;
    }
    if (/\d/.test(m[2]) !== ordered) break;   // trocou de tipo no mesmo nível: começa outra lista
    const li = h('li'); inline(li, m[3]); i++;
    while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !LI.test(lines[i])) { li.appendChild(document.createElement('br')); inline(li, lines[i++].trim()); }
    ul.appendChild(li);
  }
  return { el: ul, i };
}

function draw(el, src) {
  el.replaceChildren();
  const lines = String(src || '').replace(/\r\n/g, '\n').split('\n');
  let i = 0;
  const para = [];
  const flush = () => { if (para.length) { const p = h('p'); para.forEach((l, k) => { if (k) p.appendChild(document.createElement('br')); inline(p, l); }); el.appendChild(p); para.length = 0; } };
  while (i < lines.length) {
    const line = lines[i], trimmed = line.trim();
    let m;
    if ((m = /^```\s*([\w+#.-]*)\s*$/.exec(trimmed))) {  // bloco de código (também enquanto ainda está sendo escrito: sem a cerca de fechamento)
      flush();
      const code = []; i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i].trim())) code.push(lines[i++]);
      i++;
      const text = code.join('\n'), pre = h('pre', null, h('code', null, text));
      const copy = h('button', { class: 'copycode', type: 'button', onclick: async () => { try { await navigator.clipboard.writeText(text); copy.textContent = t('Copiado'); setTimeout(() => (copy.textContent = t('Copiar')), 1200); } catch (e) { /* ok */ } } }, t('Copiar'));
      el.appendChild(h('div', { class: 'codeblock' }, m[1] ? h('span', { class: 'lang' }, m[1]) : null, copy, pre));
      continue;
    }
    if (!trimmed) { flush(); i++; continue; }
    if ((m = /^(#{1,4})\s+(.*)$/.exec(trimmed))) { flush(); const hd = h('h' + (m[1].length + 2)); inline(hd, m[2]); el.appendChild(hd); i++; continue; }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) { flush(); el.appendChild(h('hr')); i++; continue; }
    if (/^>\s?/.test(trimmed)) { flush(); const q = []; while (i < lines.length && /^>\s?/.test(lines[i].trim())) q.push(lines[i++].trim().replace(/^>\s?/, '')); const bq = h('blockquote'); draw(bq, q.join('\n')); el.appendChild(bq); continue; }
    if (/^\|.*\|\s*$/.test(trimmed) && i + 1 < lines.length && /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(lines[i + 1].trim())) {  // tabela
      flush();
      const head = cells(trimmed); i += 2;
      const rows = [];
      while (i < lines.length && /^\|.*\|\s*$/.test(lines[i].trim())) rows.push(cells(lines[i++]));
      const tb = h('table', null, h('thead', null, h('tr', null, head.map((c) => { const th = h('th'); inline(th, c); return th; }))),
        h('tbody', null, rows.map((r) => h('tr', null, head.map((_, k) => { const td = h('td'); inline(td, r[k] || ''); return td; })))));
      el.appendChild(h('div', { class: 'tablewrap' }, tb));
      continue;
    }
    if (LI.test(line)) { flush(); const r = listBlock(lines, i, indentOf(LI.exec(line)[1])); el.appendChild(r.el); i = r.i; continue; }
    para.push(line); i++;
  }
  flush();
  return el;
}
