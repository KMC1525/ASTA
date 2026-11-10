// Scriber — escrita criativa e profissional com IA. Rotas: #/scriber (textos) · #/scriber/<texto>/<aba> — abas: generate (Geração automática) · edit (Edição).
// #/scriber/generate e #/scriber/edit abrem a aba direto no último texto (ou criam um vazio).
import { api } from '../api.js';
import { t } from '../i18n.js';
import { go, state } from '../main.js';
import { GROUP_LABEL, LAST, TABS, catalog, exportAs, historyDialog, importDialog, labeled, openProject, propertiesDialog } from '../scriber_ui.js';
import { confirmDialog, fmtDate, h, icon, modal, popover, select, toast } from '../ui.js';

const TAB_IDS = TABS.map((x) => x[0]);
const TAB_MODULES = { generate: () => import('./scriber_generate.js'), edit: () => import('./scriber_edit.js') };
const TAB_HINT = { generate: 'Gerar o texto inteiro a partir de um prompt ou esboço, em .docx', edit: 'Editar, expandir e revisar o texto como no Word' };
let current = null;   // o texto aberto (estado S): as abas se limpam ao sair

function parse() {
  const m = location.hash.match(/^#\/scriber(?:\/([\w-]+))?(?:\/([\w]+))?/);
  let pid = m && m[1] || '', tab = m && m[2] || '', direct = false;
  if (pid && TAB_IDS.includes(pid) && !tab) { tab = pid; pid = ''; direct = true; try { pid = localStorage.getItem(LAST) || ''; } catch (e) { /* ok */ } }
  return { pid, tab: TAB_IDS.includes(tab) ? tab : 'generate', direct };
}

async function openTabDirect(tab) {
  try {
    const { projects } = await api('/api/scriber/projects');
    let pid = '';
    try { pid = localStorage.getItem(LAST) || ''; } catch (e) { /* ok */ }
    if (!projects.some((p) => p.id === pid)) pid = projects[0] ? projects[0].id : '';
    if (!pid) pid = (await api('/api/scriber/projects', { method: 'POST', body: { name: t('Novo texto'), type: ((state.settings || {}).scriber || {}).type || 'romance', language: ((state.settings || {}).scriber || {}).language || '' } })).id;
    location.hash = `#/scriber/${pid}/${tab}`;
  } catch (e) { toast(e.message, 'err'); location.hash = '#/scriber'; }
}

export default async function render(root, ctx) {
  if (current) { current.cleanup(); current = null; }
  const { pid, tab, direct } = parse();
  if (!pid && direct) return openTabDirect(tab);
  if (!pid) return renderProjects(root);
  let S;
  try { S = await openProject(pid); }
  catch (e) { try { localStorage.removeItem(LAST); } catch (x) { /* ok */ } toast(e.message, 'err'); location.hash = '#/scriber'; return; }
  try { localStorage.setItem(LAST, pid); } catch (e) { /* ok */ }
  current = S; S.tab = tab; S.ctx = ctx || {};
  const body = h('div', { class: 'sc-body', id: 'sc-body' });
  const nameEl = h('button', { class: 'sc-pname', type: 'button', title: t('Renomear o texto'), id: 'sc-pname', onclick: rename }, h('b', null, S.proj.name), icon('edit', 12));
  async function rename() {
    const inp = h('input', { value: S.proj.name, maxlength: 100, id: 'sc-rename' });
    if (await modal(t('Renomear o texto'), inp, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]) !== 'ok' || !inp.value.trim()) return;
    S.proj = await S.api.put('', { name: inp.value.trim() }); nameEl.firstChild.textContent = S.proj.name; document.title = 'ASTA — ' + S.proj.name; S.onRename && S.onRename(S.proj.name);
  }
  const refresh = () => go('scriber/' + pid + '/' + tab);
  const menu = (anchor) => {
    const item = (label, ic, fn, cls) => h('div', { class: 'opt ' + (cls || ''), onclick: () => { pop.close(); fn(); } }, icon(ic, 15), label);
    const pop = popover(anchor, h('div', null,
      item(t('Propriedades (tipo, idioma, formatação)'), 'config', () => propertiesDialog(S, refresh)),
      item(t('Exportar como .docx (Word)'), 'download', () => exportAs(S, 'docx')),
      item(t('Exportar como Markdown (.md)'), 'download', () => exportAs(S, 'md')),
      item(t('Exportar como texto (.txt)'), 'download', () => exportAs(S, 'txt')),
      item(t('Exportar como página (.html)'), 'download', () => exportAs(S, 'html')),
      item(t('Importar arquivo (.docx, .md, .txt, .html)'), 'plus', () => importDialog(S, refresh)),
      item(t('Histórico (voltar a uma versão)'), 'undo', () => historyDialog(S, refresh)),
      item(t('Duplicar o texto'), 'copy', async () => { const n = await S.api.post('/duplicate', {}); toast(t('Texto duplicado'), 'ok'); location.hash = '#/scriber/' + n.id + '/edit'; }),
      item(t('Todos os textos'), 'folder', () => { location.hash = '#/scriber'; }),
      item(t('Apagar o texto'), 'trash', async () => { if (await confirmDialog(t('Apagar «{n}» e todos os arquivos dele? Isso não pode ser desfeito.', { n: S.proj.name }))) { await api('/api/scriber/projects/' + pid, { method: 'DELETE' }); try { localStorage.removeItem(LAST); } catch (e) { /* ok */ } location.hash = '#/scriber'; } }, 'danger')));
  };
  const bar = h('header', { class: 'sc-bar' },
    h('a', { class: 'btn ghost icon sm', href: '#/scriber', title: t('Todos os textos'), 'aria-label': t('Todos os textos') }, icon('arrow', 15)),
    nameEl, h('span', { class: 'chip sc-type', id: 'sc-type' }, t(S.cat.types[S.proj.type].label)), h('span', { class: 'chip dim sc-lang' }, S.proj.language),
    h('nav', { class: 'sc-tabs', role: 'tablist', 'aria-label': t('Abas do Scriber') }, TABS.map(([id, label, ic]) => h('a', { class: 'sc-tab' + (tab === id ? ' on' : ''), href: `#/scriber/${pid}/${id}`, role: 'tab', 'aria-selected': String(tab === id), dataset: { tab: id }, onclick: () => { state.ctx = {}; } }, icon(ic, 15), h('span', null, t(label))))),
    h('span', { class: 'grow' }),
    h('button', { class: 'btn sm', type: 'button', id: 'sc-export', title: t('Baixar o texto como documento do Word'), onclick: () => exportAs(S, 'docx') }, icon('download', 13), t('Baixar .docx')),
    h('button', { class: 'btn ghost icon sm', id: 'sc-menu', title: t('Mais'), type: 'button', onclick: (e) => menu(e.currentTarget) }, icon('more', 16)));
  root.replaceChildren(h('div', { class: 'sc-app', id: 'sc-app' }, bar, body));
  document.title = 'ASTA — ' + S.proj.name;
  try {
    const mod = await TAB_MODULES[tab]();
    await mod.default(body, S);
  } catch (e) { console.error(e); body.replaceChildren(h('div', { class: 'page narrow' }, h('div', { class: 'errbox' }, t('Algo deu errado:') + ' ' + (e.message || e)))); }
}

// ============================================================================ lista de textos + criar
async function renderProjects(root) {
  const [{ projects }, cat, status] = await Promise.all([api('/api/scriber/projects'), catalog(), api('/api/scriber/status').catch(() => ({ text: {} }))]);
  const cfg = Object.assign({ type: 'romance', language: 'pt-BR' }, (state.settings || {}).scriber || {});
  const nw = { name: '', type: cfg.type, language: cfg.language };
  const typeSel = h('select', { id: 'sc-new-type', 'aria-label': t('Tipo de escrita') }, ['fiction', 'professional', 'academic'].map((g) => h('optgroup', { label: t(GROUP_LABEL[g]) }, Object.entries(cat.types).filter(([, v]) => v.group === g).map(([k, v]) => h('option', { value: k, selected: k === nw.type }, t(v.label))))));
  typeSel.value = nw.type;
  const hint = h('div', { class: 'muted small', id: 'sc-new-hint' }, t(cat.types[nw.type].hint));
  typeSel.addEventListener('change', () => { nw.type = typeSel.value; hint.textContent = t(cat.types[nw.type].hint); });
  const langSel = select(Object.entries(cat.languages).map(([k, v]) => [k, t(v)]), nw.language, (v) => { nw.language = v; }, { id: 'sc-new-lang', 'aria-label': t('Idioma') });
  const nameIn = h('input', { id: 'sc-new-name', placeholder: t('Título do texto (opcional)'), maxlength: 100, 'aria-label': t('Título do texto') });
  async function create(tab) {
    try {
      const p = await api('/api/scriber/projects', { method: 'POST', body: { name: nameIn.value.trim() || t('Novo texto'), type: nw.type, language: nw.language } });
      location.hash = `#/scriber/${p.id}/${tab}`;
    } catch (e) { toast(e.message, 'err'); }
  }
  const aiNote = status.text && status.text.ai ? null : h('div', { class: 'sc-ainote', id: 'sc-ainote' }, t('Nenhuma IA configurada: o Scriber monta a estrutura do texto, o editor, o corretor e o .docx funcionam, mas escrever e expandir com IA precisa de um provedor em Configuração → Provedores.'));
  const grid = h('div', { class: 'proj-grid sc-projects', id: 'sc-projects' });
  const paint = () => grid.replaceChildren(...projects.map((p) => h('div', { class: 'proj sc-pcard', dataset: { pid: p.id } },
    h('a', { class: 'thumb sc-thumb', href: '#/scriber/' + p.id + '/edit' }, h('span', { class: 'sc-doc-ic' }, icon('doc', 34)), h('span', { class: 'badge vb' }, t((cat.types[p.type] || { label: p.type }).label))),
    h('div', { class: 'bd' }, h('div', { class: 'nm', title: p.name }, p.name), h('div', { class: 'ds' }, p.description || ''), h('div', { class: 'dim small', style: { marginTop: 'auto' } }, fmtDate(p.updated) + ' · ' + t('{w} palavras · {p} páginas', { w: p.words, p: p.pages }))),
    h('div', { class: 'ft' }, h('a', { class: 'btn sm primary', href: '#/scriber/' + p.id + '/edit' }, icon('edit', 13), t('Editar')), h('a', { class: 'btn sm', href: '#/scriber/' + p.id + '/generate' }, icon('sparkle', 13), t('Gerar')), h('span', { class: 'grow' }),
      h('button', { class: 'btn ghost icon sm', type: 'button', title: t('Apagar'), onclick: async () => { if (await confirmDialog(t('Apagar «{n}» e todos os arquivos dele? Isso não pode ser desfeito.', { n: p.name }))) { await api('/api/scriber/projects/' + p.id, { method: 'DELETE' }); projects.splice(projects.indexOf(p), 1); paint(); } } }, icon('trash', 14))))));
  paint();
  root.replaceChildren(h('div', { class: 'page sc-home' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'Scriber'), h('p', null, t('Escreva romances (SFW ou NSFW), reportagens, análises, copy, livros acadêmicos e pesquisa científica: gere um texto inteiro em .docx ou edite como no Word, com lorebooks, IA sobre o trecho selecionado, correção ortográfica e busca na web.')))),
    h('div', { class: 'sc-newcard' }, h('div', { class: 'grid3' }, labeled(t('Tipo de escrita'), typeSel), labeled(t('Idioma'), langSel), labeled(t('Título'), nameIn)), hint,
      h('div', { class: 'row', style: { marginTop: '12px' } },
        h('button', { class: 'btn primary', id: 'sc-new-gen', type: 'button', onclick: () => create('generate') }, icon('sparkle', 15), t('Gerar automaticamente')),
        h('button', { class: 'btn', id: 'sc-new-edit', type: 'button', onclick: () => create('edit') }, icon('edit', 15), t('Escrever / editar')))), aiNote,
    h('div', { class: 'sc-direct', id: 'sc-direct' }, h('span', { class: 'sc-direct-l' }, t('Ir direto para uma aba')),
      TABS.map(([id, label, ic]) => h('a', { class: 'btn sm sc-direct-b', href: '#/scriber/' + id, dataset: { tab: id }, title: t(TAB_HINT[id]) }, icon(ic, 14), t(label)))),
    projects.length ? h('h2', { class: 'ge-h2' }, t('Seus textos')) : h('div', { class: 'empty' }, h('h3', null, t('Escreva seu primeiro texto')), h('p', null, t('Escolha o tipo de escrita e o idioma, e gere o texto inteiro ou comece a escrever. Tudo fica em arquivos comuns na sua pasta.'))),
    projects.length ? grid : null));
}
