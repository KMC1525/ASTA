// Markdown seguro para as respostas do Chat: monta nós DOM (nunca innerHTML), então nada que o modelo escreva vira HTML/script.
// Cobre o que as respostas costumam usar: títulos, negrito/itálico/tachado, `código`, blocos de código com «copiar», listas, citações, tabelas, linhas e links http(s).
import { t } from './i18n.js';
import { h } from './ui.js';

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|~~[^~\n]+~~|\*[^*\s][^*\n]*\*|(?<![\w])_[^_\s][^_\n]*_(?![\w])|\[[^\]\n]+\]\([^)\s]+\))/g;

export function inline(parent, src) {
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
    } else parent.appendChild(document.createTextNode(part));
  });
}

const cells = (line) => line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());

export function renderMarkdown(el, src) {
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
    if (/^>\s?/.test(trimmed)) { flush(); const q = []; while (i < lines.length && /^>\s?/.test(lines[i].trim())) q.push(lines[i++].trim().replace(/^>\s?/, '')); const bq = h('blockquote'); renderMarkdown(bq, q.join('\n')); el.appendChild(bq); continue; }
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
    if ((m = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(line))) {
      flush();
      const ordered = /\d/.test(m[2]), list = h(ordered ? 'ol' : 'ul');
      if (ordered && parseInt(m[2], 10) > 1) list.setAttribute('start', parseInt(m[2], 10));
      while (i < lines.length && (m = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i]))) {
        const li = h('li'); inline(li, m[3]); i++;
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) { li.appendChild(document.createElement('br')); inline(li, lines[i++].trim()); }
        list.appendChild(li);
      }
      el.appendChild(list);
      continue;
    }
    para.push(line); i++;
  }
  flush();
  return el;
}
