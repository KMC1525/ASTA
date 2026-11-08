import { t } from './i18n.js';
import { h } from './ui.js';

// Menções com «@» nos prompts dos nós Imagem e Vídeo: digite @ e escolha uma imagem do canvas; ela vira referência da geração (veja asta/canvas/mentions.py).
const TOKEN = /(?:^|[^\w@.])@([A-Za-z0-9_-]*)$/;          // «@ap» logo antes do cursor
const MENTION = /(?<![\w@.])@([A-Za-z0-9][A-Za-z0-9_-]*)/g;  // mesma regra do servidor

// ta: o <textarea> do prompt; c: { mentions(): Promise<[{slug, name, url}]> }. Devolve o elemento que substitui o textarea (caixa + lista + fichas das imagens citadas).
export function withMentions(ta, c) {
  let items = [], open = false, sel = 0, range = null, loaded = 0, seq = 0;   // seq: descarta respostas atrasadas (fechou ou digitou de novo enquanto a lista carregava)
  const pop = h('div', { class: 'mpop nodrag hidden', role: 'listbox' }), chips = h('div', { class: 'mchips' });
  const wrap = h('div', { class: 'mwrap' }, ta, pop, chips);
  const load = async (force) => {
    if (!force && Date.now() - loaded < 4000) return items;
    try { items = await c.mentions(); loaded = Date.now(); } catch (e) { items = []; }
    return items;
  };
  const close = () => { seq++; open = false; pop.classList.add('hidden'); };
  function paintChips() {
    const toks = [...new Set([...ta.value.matchAll(MENTION)].map((m) => m[1]))];
    chips.replaceChildren(...toks.map((tok) => {
      const it = items.find((x) => x.slug === tok.toLowerCase() || x.id === tok);
      return it ? h('span', { class: 'mchip', title: it.name }, h('i', { style: { backgroundImage: `url("${it.url}")` } }), '@' + it.slug)
        : h('span', { class: 'mchip bad', title: t('Não há imagem com esse apelido neste canvas') }, '@' + tok);
    }));
  }
  function paintPop(list) {
    pop.replaceChildren(...(list.length ? list.map((it, i) => h('div', { class: 'mi' + (i === sel ? ' on' : ''), role: 'option', dataset: { slug: it.slug },
      onmousedown: (e) => { e.preventDefault(); pick(it); } }, h('i', { style: { backgroundImage: `url("${it.url}")` } }), h('b', null, '@' + it.slug), h('span', { class: 'muted small' }, it.name)))
      : [h('div', { class: 'mi none' }, t('Nenhuma imagem neste canvas. Envie ou gere uma imagem e cite com @.'))]));
    pop.classList.remove('hidden'); open = true;
  }
  const filtered = () => items.filter((x) => !range || x.slug.includes(range.q.toLowerCase())).slice(0, 8);
  async function refresh() {
    const pos = ta.selectionStart, m = TOKEN.exec(ta.value.slice(0, pos));
    if (!m) { close(); return; }
    range = { start: pos - m[1].length - 1, end: pos, q: m[1] };
    const my = ++seq;
    await load(true);
    if (my !== seq) return;
    sel = 0; paintPop(filtered()); paintChips();
  }
  function pick(it) {
    if (!range) return;
    const v = ta.value, ins = '@' + it.slug + ' ';
    ta.value = v.slice(0, range.start) + ins + v.slice(range.end);
    const caret = range.start + ins.length; ta.setSelectionRange(caret, caret);
    close(); ta.dispatchEvent(new Event('input', { bubbles: true })); ta.focus();
  }
  ta.addEventListener('input', () => { refresh(); paintChips(); });
  ta.addEventListener('click', () => { if (ta.value.includes('@')) refresh(); });
  ta.addEventListener('blur', () => setTimeout(close, 120));
  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (open) e.preventDefault(); close(); return; }   // também cancela uma lista que ainda está carregando
    if (!open) return;
    const list = filtered();
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + Math.max(1, list.length)) % Math.max(1, list.length); paintPop(list); }
    else if ((e.key === 'Enter' || e.key === 'Tab') && list[sel]) { e.preventDefault(); e.stopPropagation(); pick(list[sel]); }
  }, true);
  if (ta.value.includes('@')) load(true).then(paintChips); else paintChips();
  return wrap;
}
