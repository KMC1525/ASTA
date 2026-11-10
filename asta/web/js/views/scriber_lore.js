// Scriber → Edição: painel de lorebooks (canto esquerdo). Livros de contexto no estilo dos system prompts: entradas de regras de estilo («system»), personagens, lugares, mundo… que entram nas chamadas da IA —
// sempre (entrada «sempre ativa» e as de tipo system) ou quando uma palavra-chave aparece no trecho. Importa e exporta JSON (ASTA e SillyTavern) e Markdown.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { btn, ibtn, labeled } from '../scriber_ui.js';
import { confirmDialog, debounce, h, icon, modal, select, toast } from '../ui.js';

const KIND_LABEL = { system: 'Regra de estilo (system)', character: 'Personagem', place: 'Lugar', world: 'Mundo', rule: 'Regra', plot: 'Enredo', note: 'Nota' };
const KIND_SHORT = { system: 'system', character: 'pers.', place: 'lugar', world: 'mundo', rule: 'regra', plot: 'trama', note: 'nota' };

// devolve { el, books(), enabled(), setUsed(ids), refresh() }
export async function createLorePanel(S, o = {}) {
  const url = S.api.base + '/lorebooks';
  const st = { books: [], kinds: Object.keys(KIND_LABEL), open: new Set(), editing: '', used: new Set(), on: o.enabled !== false };
  const load = async () => { const r = await api(url); st.books = r.books; st.kinds = r.kinds; };
  const save = debounce(async () => { try { const r = await api(url, { method: 'PUT', body: { books: st.books } }); st.books = r.books; } catch (e) { toast(e.message, 'err'); } }, 500);
  await load();
  const list = h('div', { class: 'sc-lore-list', id: 'sc-lore-list' });
  const newId = () => 'b_' + Math.random().toString(16).slice(2, 12);

  function paint() {
    list.replaceChildren(...(st.books.length ? st.books.map(bookEl) : [h('div', { class: 'muted small sc-lore-empty', id: 'sc-lore-empty' }, t('Nenhum lorebook ainda. Crie um para guardar personagens, lugares, regras de estilo e o que a IA deve lembrar.'))]));
    badge.textContent = String(st.books.reduce((n, b) => n + b.entries.length, 0));
  }
  function bookEl(b) {
    const open = st.open.has(b.id);
    const on = h('input', { type: 'checkbox', checked: b.enabled !== false, title: t('Usar este livro na IA'), 'aria-label': t('Usar este livro na IA') }); on.addEventListener('change', () => { b.enabled = on.checked; save(); });
    const head = h('div', { class: 'sc-book-h' }, h('span', { class: 'sc-chev', onclick: () => { open ? st.open.delete(b.id) : st.open.add(b.id); paint(); } }, icon(open ? 'chevd' : 'chevr', 13)), on,
      h('b', { class: 'sc-book-n', title: b.name, onclick: () => { open ? st.open.delete(b.id) : st.open.add(b.id); paint(); } }, b.name), h('span', { class: 'dim small' }, String(b.entries.length)), h('span', { class: 'grow' }),
      ibtn(t('Nova entrada'), 'plus', () => { addEntry(b); }, '', { dataset: { act: 'add-entry' } }), ibtn(t('Mais'), 'more', (e) => bookMenu(b, e.currentTarget)));
    return h('div', { class: 'sc-book' + (b.enabled === false ? ' off' : ''), dataset: { book: b.id } }, head, open ? h('div', { class: 'sc-entries' }, b.entries.length ? b.entries.map((e) => entryEl(b, e)) : h('div', { class: 'muted small', style: { padding: '6px 8px' } }, t('Livro vazio. Use + para adicionar uma entrada.'))) : null);
  }
  function bookMenu(b, anchor) {
    const items = [[t('Renomear'), async () => { const i = h('input', { value: b.name, maxlength: 80 }); if (await modal(t('Renomear o lorebook'), i, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]) === 'ok' && i.value.trim()) { b.name = i.value.trim(); save(); paint(); } }],
      [t('Exportar (JSON)'), () => download(b, 'json')], [t('Exportar (Markdown)'), () => download(b, 'md')],
      [t('Apagar o livro'), async () => { if (await confirmDialog(t('Apagar o lorebook «{n}» e as {c} entradas dele?', { n: b.name, c: b.entries.length }))) { st.books = st.books.filter((x) => x !== b); save(); paint(); } }, 'danger']];
    const pop = h('div', { class: 'pop sc-pop' }, items.map(([l, fn, cls]) => h('div', { class: 'opt ' + (cls || ''), onclick: () => { pop.remove(); fn(); } }, l)));
    document.body.appendChild(pop); const r = anchor.getBoundingClientRect(); pop.style.left = Math.min(innerWidth - 220, r.left) + 'px'; pop.style.top = r.bottom + 4 + 'px';
    setTimeout(() => document.addEventListener('mousedown', function off(e) { if (!pop.contains(e.target)) { pop.remove(); document.removeEventListener('mousedown', off); } }), 0);
  }
  async function download(b, fmt) { await api(url, { method: 'PUT', body: { books: st.books } }).catch(() => {}); const a = h('a', { href: `${url}/${b.id}/export?format=${fmt}`, download: b.name + (fmt === 'md' ? '.md' : '.json'), class: 'hidden' }); document.body.appendChild(a); a.click(); a.remove(); }
  function addEntry(b) {
    const e = { id: 'e_' + Math.random().toString(16).slice(2, 12), name: t('Nova entrada'), kind: 'character', keys: [], content: '', enabled: true, always: false, priority: 50 };
    b.entries.push(e); st.open.add(b.id); st.editing = e.id; paint(); save();
    setTimeout(() => { const el = list.querySelector('.sc-entry.edit input'); if (el) el.select(); }, 0);
  }
  function entryEl(b, e) {
    const editing = st.editing === e.id;
    if (!editing) {
      const used = st.used.has(e.id);
      return h('div', { class: 'sc-entry' + (e.enabled === false ? ' off' : '') + (used ? ' used' : ''), dataset: { entry: e.id }, title: e.content.slice(0, 300), onclick: () => { st.editing = e.id; paint(); } },
        h('span', { class: 'sc-kind k-' + e.kind }, t(KIND_SHORT[e.kind] || e.kind)), h('span', { class: 'sc-entry-n' }, e.name), e.always || e.kind === 'system' ? h('span', { class: 'sc-pin', title: t('Sempre ativa') }, '●') : null,
        used ? h('span', { class: 'sc-usedmark', title: t('Usada na última chamada da IA') }, '✦') : null);
    }
    const name = h('input', { value: e.name, maxlength: 80, 'aria-label': t('Nome da entrada') }); name.addEventListener('input', () => { e.name = name.value; save(); });
    const kind = select(st.kinds.map((k) => [k, t(KIND_LABEL[k] || k)]), e.kind, (v) => { e.kind = v; save(); paint(); }, { 'aria-label': t('Tipo da entrada') });
    const keys = h('input', { value: e.keys.join(', '), placeholder: t('palavras-chave, separadas por vírgula'), 'aria-label': t('Palavras-chave') }); keys.addEventListener('input', () => { e.keys = keys.value.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean); save(); });
    const content = h('textarea', { rows: 6, placeholder: e.kind === 'system' ? t('Ex.: Escreva em terceira pessoa, no passado. Frases curtas. Nada de advérbios em -mente.') : t('O que a IA precisa saber: aparência, personalidade, história, regras do lugar…'), 'aria-label': t('Conteúdo') }); content.value = e.content;
    content.addEventListener('input', () => { e.content = content.value; save(); });
    const always = h('input', { type: 'checkbox', checked: !!e.always }); always.addEventListener('change', () => { e.always = always.checked; save(); });
    const enabled = h('input', { type: 'checkbox', checked: e.enabled !== false }); enabled.addEventListener('change', () => { e.enabled = enabled.checked; save(); });
    return h('div', { class: 'sc-entry edit', dataset: { entry: e.id } }, name, kind, e.kind === 'system' ? h('div', { class: 'hint' }, t('Regras de estilo valem em todas as chamadas, como um system prompt.')) : keys, content,
      h('div', { class: 'row' }, h('label', { class: 'check' }, always, h('span', null, t('Sempre ativa'))), h('label', { class: 'check' }, enabled, h('span', null, t('Ligada')))),
      h('div', { class: 'row' }, btn(t('Pronto'), 'check', () => { st.editing = ''; paint(); }, 'primary'), h('span', { class: 'grow' }), btn(t('Apagar'), 'trash', () => { b.entries = b.entries.filter((x) => x !== e); st.editing = ''; save(); paint(); }, 'ghost')));
  }

  async function newBook() {
    const i = h('input', { id: 'sc-lore-newname', placeholder: t('ex.: Personagens, Mundo, Estilo da autora'), maxlength: 80 });
    if (await modal(t('Novo lorebook'), i, [{ label: t('Cancelar'), value: null }, { label: t('Criar'), value: 'ok', cls: 'primary' }]) !== 'ok') return;
    const b = { id: newId(), name: i.value.trim() || 'Lorebook', enabled: true, entries: [] };
    st.books.push(b); st.open.add(b.id); paint(); await api(url, { method: 'PUT', body: { books: st.books } }).then((r) => { st.books = r.books; paint(); });
  }
  function importBook() {
    const inp = h('input', { type: 'file', accept: '.json,.md,.markdown,.txt', class: 'hidden', id: 'sc-lore-import' });
    inp.addEventListener('change', async () => {
      const f = inp.files[0]; inp.remove(); if (!f) return;
      try { const text = await f.text(); const b = await api(url + '/import', { method: 'POST', body: { text, name: f.name.replace(/\.[^.]+$/, '') } }); await load(); st.open.add(b.id); paint(); toast(t('Lorebook importado: {n}', { n: b.name }), 'ok'); } catch (e) { toast(e.message, 'err'); }
    });
    document.body.appendChild(inp); inp.click();
  }

  const badge = h('span', { class: 'chip dim', id: 'sc-lore-count' }, '0');
  const master = h('input', { type: 'checkbox', checked: st.on, id: 'sc-lore-on', title: t('Enviar o lorebook para a IA') }); master.addEventListener('change', () => { st.on = master.checked; if (o.onToggle) o.onToggle(st.on); });
  const el = h('aside', { class: 'sc-left', id: 'sc-lore', 'aria-label': t('Lorebooks') },
    h('div', { class: 'sc-ph' }, h('b', null, t('Lorebooks')), badge, h('span', { class: 'grow' }), h('label', { class: 'check sc-master', title: t('Enviar o lorebook para a IA') }, master, h('span', null, t('Na IA')))),
    h('div', { class: 'sc-ftool' }, btn(t('Novo livro'), 'plus', newBook, '', { id: 'sc-lore-new' }), btn(t('Importar'), 'download', importBook, '', { id: 'sc-lore-imp', title: t('JSON do ASTA ou do SillyTavern (World Info), ou Markdown') })),
    list, h('div', { class: 'sc-lore-foot hint' }, t('Entradas de tipo «regra de estilo» e as «sempre ativas» vão em toda chamada; as outras entram quando uma palavra-chave aparece no trecho.')));
  paint();
  return { el, enabled: () => st.on, books: () => st.books, setUsed(ids) { st.used = new Set(ids || []); paint(); }, refresh: async () => { await load(); paint(); } };
}
