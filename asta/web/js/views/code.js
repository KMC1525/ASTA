// Code — vibe coding de bases de código longas com equipes de agentes (até 32 por sessão, várias sessões em segundo plano), em pastas do computador e em repositórios do GitHub.
// Barra lateral: pastas e subpastas (nome, uma de 8 cores, recolher/expandir) com as sessões e a bolinha de estado de cada uma. Centro: a conversa e o que a equipe está fazendo. Direita: ambiente, plano, agentes e saídas.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { state } from '../main.js';
import { renderMarkdown } from '../markdown.js';
import { AGENT_COUNTS } from '../team_ui.js';
import { AGENT, EFFORT_LABEL, FILE_STATUS, MODE, MODE_HINT, PLAN_STATUS, PUBLISH, ROLE, RUN_STATUS, STATE, STEP_STATUS, TOOL_ICON, approvalCards, describeAction, fmtClock, fmtDur, fmtWhen, isBusy, stateDot, subscribe } from '../code_ui.js';
import { confirmDialog, fill, h, icon, modal, popover, seg, toast } from '../ui.js';
import { createComposer } from './composer.js';

// 1 · 2 · 4 · 8 · 12 · 16 · 20 · 24 · 28 · 32 agentes; uma sessão antiga com outro número (2, 3, 5…) continua mostrando o dela
const countsWith = (n) => [...new Set([...AGENT_COUNTS, n])].sort((a, b) => a - b);

const idFromHash = () => { const m = location.hash.match(/^#\/code\/([\w-]+)/); return m ? m[1] : ''; };
const cfg = () => (state.settings && state.settings.code) || {};
const inApp = () => /ASTA-Android/.test(navigator.userAgent || '');

// App Android: o ASTA do aparelho trabalha com repositórios do GitHub pela nuvem (sem git nem comandos); para rodar código de verdade ele pode abrir o ASTA do seu computador
function pcBridge() {
  if (!inApp()) return null;
  const local = /^(127\.0\.0\.1|localhost)$/.test(location.hostname);
  return h('div', { class: 'card cd-pc', id: 'cd-pc', style: { margin: '0 0 12px' } },
    local
      ? [h('b', null, t('Executar no seu computador')),
        h('p', { class: 'muted small', style: { margin: '4px 0 8px' } }, t('Neste aparelho o Code edita e publica repositórios do GitHub pela nuvem. Para rodar testes e programas, mande a sessão para o ASTA do seu computador: você acompanha e aprova daqui.')),
        h('button', { class: 'btn primary', type: 'button', id: 'cd-pc-go', onclick: () => { location.href = 'http://localhost/?goto=code'; } }, icon('globe', 14), t('Executar no meu computador'))]
      : [h('b', null, t('Executando no seu computador')),
        h('p', { class: 'muted small', style: { margin: '4px 0 8px' } }, t('As sessões rodam no computador conectado; este aparelho é só a janela.')),
        h('button', { class: 'btn', type: 'button', id: 'cd-pc-back', onclick: () => { location.href = 'http://localhost/?local=1'; } }, t('Voltar ao ASTA deste aparelho'))]);
}

export default async function render(root, ctx) {
  const st = { sessions: [], folders: [], status: null, sel: (ctx && ctx.session) || idFromHash(), cur: null, filter: '', menu: null };
  const sideEl = h('aside', { class: 'cd-side', 'aria-label': t('Sessões') });
  const mainEl = h('section', { class: 'cd-main', 'aria-live': 'polite' });
  const panelEl = h('aside', { class: 'cd-panel', 'aria-label': t('Detalhes da sessão') });
  const split = h('div', { class: 'cd-split' }, sideEl, mainEl, panelEl);
  const capBadge = h('span', { class: 'chip cd-cap', id: 'cd-cap' });
  root.replaceChildren(h('div', { class: 'page cd-page' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, t('Code')),
      h('p', null, t('Vibe coding de projetos grandes com uma equipe de agentes de IA: ler, planejar, escrever, testar, revisar e publicar no GitHub. Até 8 agentes por sessão e várias sessões ao mesmo tempo.'))),
      h('div', { class: 'row' }, capBadge, h('a', { class: 'btn sm', href: '#/config', onclick: () => { state.ctx = { tab: 'code' }; } }, icon('config', 13), t('Configurar')))),
    pcBridge(), split));
  let composer = null, tick = 0, off = null, refreshT = 0, composerSid = '';

  // ------------------------------------------------------------------ dados
  async function loadList() {
    try { const r = await api('/api/code/sessions'); st.sessions = r.sessions; st.folders = r.folders; st.status = r.status; } catch (e) { toast(e.message, 'err'); }
    paintCap(); paintSide();
  }
  async function loadCur(quiet) {
    if (!st.sel) { st.cur = null; return; }
    try { st.cur = await api('/api/code/sessions/' + st.sel); } catch (e) { st.cur = null; if (!quiet) { toast(t('Sessão não encontrada'), 'err'); st.sel = ''; } }
  }
  function paintCap() {
    const s = st.status || {}, n = (s.running || 0) + (s.waiting || 0);
    capBadge.className = 'chip cd-cap' + (n ? ' busy' : '');
    capBadge.textContent = t('{n} em execução', { n }) + (s.waiting ? ' · ' + t('{n} esperando você', { n: s.waiting }) : '') + (s.queued ? ' · ' + t('{n} na fila', { n: s.queued }) : '');
  }
  const colorOf = (id) => ((st.status && st.status.colors) || []).find((c) => c.id === id) || { hex: '#3b82f6', label: id };
  const folderPath = (id) => { const by = Object.fromEntries(st.folders.map((f) => [f.id, f])); const out = []; let n = 0; while (id && by[id] && n++ < 10) { out.unshift(by[id].name); id = by[id].parent; } return out.join(' / '); };
  async function putFolder(id, body) { try { await api('/api/code/folders/' + id, { method: 'PUT', body }); await loadList(); } catch (e) { toast(e.message, 'err'); } }

  // ------------------------------------------------------------------ barra lateral: pastas, subpastas e sessões
  function sessionItem(s, depth) {
    const sub = s.workspace && s.workspace.status === 'preparing' ? t('Preparando o repositório…') : s.waiting ? t('Aguardando você') : isBusy(s.state) ? (s.now || STATE()[s.state]) : (s.workspace.label || '') + (s.updated ? ' · ' + fmtWhen(s.updated) : '');
    const el = h('div', { class: 'cd-item' + (st.sel === s.id ? ' on' : '') + (s.waiting ? ' ask' : ''), role: 'button', tabindex: '0', draggable: 'true', dataset: { id: s.id, state: s.state }, style: { paddingLeft: (10 + depth * 14) + 'px' },
      onclick: () => select(s.id), onkeydown: (e) => { if (e.key === 'Enter') select(s.id); },
      ondragstart: (e) => { e.dataTransfer.setData('text/asta-session', s.id); e.dataTransfer.effectAllowed = 'move'; } },
    stateDot(s.state, s.waiting), h('span', { class: 'grow' }, h('span', { class: 'cd-t' }, s.title || t('Nova sessão')), h('span', { class: 'cd-s' }, sub)),
    h('button', { class: 'btn ghost icon sm cd-more', type: 'button', title: t('Mais'), 'aria-label': t('Mais'), onclick: (e) => { e.stopPropagation(); sessionMenu(e.currentTarget, s); } }, icon('more', 15)));
    return el;
  }
  function folderBlock(f, depth) {
    const kids = st.folders.filter((x) => x.parent === f.id), sess = st.sessions.filter((s) => s.folder_id === f.id);
    const count = (id) => st.sessions.filter((s) => s.folder_id === id).length + st.folders.filter((x) => x.parent === id).reduce((n, x) => n + count(x.id), 0);
    const hex = colorOf(f.color).hex;
    const busy = [...st.sessions.filter((s) => s.folder_id === f.id)].some((s) => isBusy(s.state));
    const head = h('div', { class: 'cd-folder', dataset: { folder: f.id, color: f.color, collapsed: f.collapsed ? '1' : '0' }, style: { paddingLeft: (4 + depth * 14) + 'px' },
      ondragover: (e) => { if (e.dataTransfer.types.includes('text/asta-session')) { e.preventDefault(); head.classList.add('drop'); } }, ondragleave: () => head.classList.remove('drop'),
      ondrop: async (e) => { e.preventDefault(); head.classList.remove('drop'); const sid = e.dataTransfer.getData('text/asta-session'); if (sid) await moveSession(sid, f.id); } },
    h('button', { class: 'btn ghost icon sm cd-caret', type: 'button', title: f.collapsed ? t('Expandir') : t('Recolher'), 'aria-expanded': f.collapsed ? 'false' : 'true', 'aria-label': (f.collapsed ? t('Expandir') : t('Recolher')) + ' ' + f.name,
      onclick: () => { f.collapsed = !f.collapsed; paintSide(); putFolder(f.id, { collapsed: f.collapsed }); } }, icon(f.collapsed ? 'chevr' : 'chevd', 14)),
    h('span', { class: 'cd-fi', style: { color: hex }, title: colorOf(f.color).label }, icon('foldero', 17)),
    h('span', { class: 'cd-fn', ondblclick: () => folderDialog(f), title: f.name }, f.name), h('span', { class: 'cd-fc' }, busy ? h('i', { class: 'cd-mini work' }) : null, String(count(f.id))),
    h('button', { class: 'btn ghost icon sm cd-more', type: 'button', title: t('Mais'), 'aria-label': t('Mais'), onclick: (e) => { e.stopPropagation(); folderMenu(e.currentTarget, f); } }, icon('more', 15)));
    const body = f.collapsed ? null : h('div', { class: 'cd-fkids' }, ...kids.map((k) => folderBlock(k, depth + 1)), ...sess.map((s) => sessionItem(s, depth + 1)),
      !kids.length && !sess.length ? h('div', { class: 'dim small cd-empty', style: { paddingLeft: (22 + depth * 14) + 'px' } }, t('Vazia: arraste uma sessão para cá.')) : null);
    return h('div', { class: 'cd-fblock' }, head, body);
  }
  function paintSide() {
    const q = st.filter.trim().toLowerCase();
    const search = h('input', { type: 'search', id: 'cd-filter', placeholder: t('Buscar nas sessões…'), value: st.filter, 'aria-label': t('Buscar nas sessões…') });
    search.addEventListener('input', () => { st.filter = search.value; const pos = search.selectionStart; paintSide(); const again = sideEl.querySelector('#cd-filter'); if (again) { again.focus(); try { again.setSelectionRange(pos, pos); } catch (e) { /* ok */ } } });
    let tree;
    if (q) {
      const hit = st.sessions.filter((s) => (s.title + ' ' + s.goal + ' ' + (s.workspace.label || '') + ' ' + folderPath(s.folder_id)).toLowerCase().includes(q));
      tree = hit.length ? hit.map((s) => sessionItem(s, 0)) : [h('div', { class: 'dim small cd-none' }, t('Nada encontrado.'))];
    } else {
      const roots = st.folders.filter((f) => !f.parent), loose = st.sessions.filter((s) => !s.folder_id || !st.folders.some((f) => f.id === s.folder_id));
      const busy = loose.filter((s) => isBusy(s.state)), rest = loose.filter((s) => !isBusy(s.state));
      tree = [...roots.map((f) => folderBlock(f, 0)),
        (loose.length || roots.length || st.sessions.length) ? h('div', { class: 'cd-grp cd-loose', dataset: { loose: '1' }, ondragover: (e) => { if (e.dataTransfer.types.includes('text/asta-session')) e.preventDefault(); },
          ondrop: async (e) => { e.preventDefault(); const sid = e.dataTransfer.getData('text/asta-session'); if (sid) await moveSession(sid, null); } }, roots.length ? t('Sem pasta') : t('Sessões')) : null,
        ...busy.map((s) => sessionItem(s, 0)), ...rest.map((s) => sessionItem(s, 0)),
        !st.sessions.length ? h('div', { class: 'dim small cd-none' }, t('Nenhuma sessão ainda. Crie uma pasta para organizar e uma sessão para começar.')) : null];
    }
    fill(sideEl,
      h('div', { class: 'row cd-newrow' }, h('button', { class: 'btn primary cd-new', id: 'cd-new', type: 'button', onclick: () => newSessionDialog() }, icon('plus', 15), t('Nova sessão')),
        h('button', { class: 'btn icon', id: 'cd-new-folder', type: 'button', title: t('Nova pasta'), 'aria-label': t('Nova pasta'), onclick: () => folderDialog(null, null) }, icon('foldero', 16))),
      st.sessions.length > 5 || st.filter ? search : null,
      h('div', { class: 'cd-tree', id: 'cd-tree' }, ...tree),
      st.folders.length ? h('div', { class: 'row cd-fold-all' }, h('button', { class: 'btn sm ghost', type: 'button', id: 'cd-collapse-all', onclick: () => setAll(true) }, t('Recolher tudo')), h('button', { class: 'btn sm ghost', type: 'button', id: 'cd-expand-all', onclick: () => setAll(false) }, t('Expandir tudo'))) : null);
  }
  async function setAll(collapsed) { st.folders.forEach((f) => { f.collapsed = collapsed; }); paintSide(); await Promise.all(st.folders.map((f) => api('/api/code/folders/' + f.id, { method: 'PUT', body: { collapsed } }).catch(() => {}))); }
  async function moveSession(sid, folder) { try { await api('/api/code/sessions/' + sid, { method: 'PUT', body: { folder_id: folder } }); await loadList(); if (st.sel === sid) { await loadCur(true); paintMain(); } } catch (e) { toast(e.message, 'err'); } }

  // ------------------------------------------------------------------ pastas: criar, editar (nome e cor), subpasta, apagar
  async function folderDialog(f, parent) {
    const colors = (st.status && st.status.colors) || [];
    let color = f ? f.color : colors[(st.folders.length) % Math.max(1, colors.length)].id;
    const name = h('input', { id: 'cd-folder-name', value: f ? f.name : '', placeholder: t('Nome da pasta'), maxlength: 60, 'aria-label': t('Nome da pasta') });
    const sw = h('div', { class: 'cd-swatches', role: 'radiogroup', 'aria-label': t('Cor da pasta') });
    const paintSw = () => sw.replaceChildren(...colors.map((c) => h('button', { type: 'button', class: 'cd-sw' + (c.id === color ? ' on' : ''), role: 'radio', 'aria-checked': c.id === color ? 'true' : 'false', title: t(c.label), 'aria-label': t(c.label),
      dataset: { color: c.id }, style: { background: c.hex }, onclick: () => { color = c.id; paintSw(); } })));
    paintSw();
    name.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); document.querySelector('.modal .foot .primary').click(); } });
    const where = parent || (f && f.parent);
    const v = await modal(f ? t('Editar a pasta') : (parent ? t('Nova subpasta') : t('Nova pasta')), h('div', null,
      where ? h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Dentro de: {p}', { p: folderPath(where) })) : null,
      h('label', { class: 'f' }, t('Nome')), name, h('label', { class: 'f', style: { marginTop: '12px' } }, t('Cor')), sw),
    [{ label: t('Cancelar'), value: false }, { label: f ? t('Salvar') : t('Criar'), value: true, cls: 'primary' }]);
    if (v !== true) return;
    if (!name.value.trim()) return toast(t('Dê um nome à pasta.'), 'err');
    try {
      if (f) await api('/api/code/folders/' + f.id, { method: 'PUT', body: { name: name.value.trim(), color } });
      else await api('/api/code/folders', { method: 'POST', body: { name: name.value.trim(), color, parent: parent || null } });
      await loadList();
    } catch (e) { toast(e.message, 'err'); }
  }
  function menu(anchor, items) {
    const box = h('div', { class: 'cd-menu' }, items.filter(Boolean).map(([label, ic, fn, cls]) => h('button', { type: 'button', class: 'cd-mi ' + (cls || ''), onclick: () => { pop.close(); fn(); } }, icon(ic, 14), label)));
    const pop = popover(anchor, box);
  }
  const folderMenu = (anchor, f) => menu(anchor, [[t('Editar nome e cor'), 'edit', () => folderDialog(f)], [t('Nova subpasta'), 'plus', () => folderDialog(null, f.id)], [t('Nova sessão aqui'), 'code', () => newSessionDialog(f.id)],
    [t('Apagar a pasta'), 'trash', async () => { if (await confirmDialog(t('Apagar a pasta «{n}»? As sessões e subpastas dela sobem para a pasta de cima; nada é perdido.', { n: f.name }), true)) { try { await api('/api/code/folders/' + f.id, { method: 'DELETE' }); await loadList(); } catch (e) { toast(e.message, 'err'); } } }, 'danger']]);
  const sessionMenu = (anchor, s) => menu(anchor, [[t('Renomear'), 'edit', () => renameSession(s)], [t('Mover para uma pasta…'), 'foldero', () => moveDialog(s)],
    [t('Apagar a sessão'), 'trash', async () => { if (await confirmDialog(t('Apagar a sessão «{n}»? O histórico dela some; o projeto continua como está.', { n: s.title }), true)) { try { await api('/api/code/sessions/' + s.id, { method: 'DELETE' }); if (st.sel === s.id) { st.sel = ''; history.replaceState(null, '', '#/code'); st.cur = null; } await loadList(); paintMain(); } catch (e) { toast(e.message, 'err'); } } }, 'danger']]);
  async function renameSession(s) {
    const inp = h('input', { id: 'cd-rename', value: s.title, maxlength: 120 });
    inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); document.querySelector('.modal .foot .primary').click(); } });
    const v = await modal(t('Renomear a sessão'), inp, [{ label: t('Cancelar'), value: false }, { label: t('Salvar'), value: true, cls: 'primary' }]);
    if (v !== true || !inp.value.trim()) return;
    try { await api('/api/code/sessions/' + s.id, { method: 'PUT', body: { title: inp.value.trim() } }); await loadList(); if (st.sel === s.id) { await loadCur(true); paintMain(); } } catch (e) { toast(e.message, 'err'); }
  }
  async function moveDialog(s) {
    const opts = [['', t('Sem pasta')]];
    const walk = (parent, depth) => st.folders.filter((f) => f.parent === parent).forEach((f) => { opts.push([f.id, '\u00a0\u00a0'.repeat(depth) + f.name]); walk(f.id, depth + 1); });
    walk(null, 0);
    const sel = h('select', { id: 'cd-move-to' }, opts.map(([v, l]) => h('option', { value: v, selected: v === (s.folder_id || '') }, l)));
    const v = await modal(t('Mover para uma pasta'), sel, [{ label: t('Cancelar'), value: false }, { label: t('Mover'), value: true, cls: 'primary' }]);
    if (v === true) await moveSession(s.id, sel.value || null);
  }

  // ------------------------------------------------------------------ nova sessão
  async function newSessionDialog(folderId) {
    const stt = st.status || {}, c = cfg();
    const phone = !!stt.android;
    const f = { source: phone ? 'github' : 'local', path: '', create: true, repo: '', name: '', title: '', folder: folderId || '', mode: c.mode || 'ask', effort: c.effort || 'high', agents: c.agents || 4, provider: '', model: '', docs: !!(c.finalize || {}).docs, publish: (c.finalize || {}).publish || 'none' };
    const body = h('div', { class: 'cd-new-form' });
    let repos = null;
    const srcSeg = seg([...(phone ? [] : [['local', t('Pasta do computador')]]), ['github', t('Repositório do GitHub')], ['new', t('Projeto novo')]], f.source, (v) => { f.source = v; paintSource(); });
    const srcBox = h('div');
    const inp = (key, ph, id) => { const i = h('input', { id, value: f[key], placeholder: ph, oninput: (e) => { f[key] = e.target.value; } }); return i; };
    async function paintSource() {
      if (f.source === 'local') srcBox.replaceChildren(h('label', { class: 'f' }, t('Pasta do projeto')), inp('path', t('Ex.: /home/voce/meu-projeto ou C:/projetos/meu-app'), 'cd-path'),
        h('label', { class: 'check', style: { marginTop: '8px' } }, h('input', { type: 'checkbox', id: 'cd-create', checked: f.create, onchange: (e) => { f.create = e.target.checked; } }), h('span', null, t('Criar a pasta se ela não existir'))),
        h('div', { class: 'hint' }, t('A pasta fica como está; o Code só mexe nos arquivos dela (e tudo pode ser desfeito). Se tiver git, ele usa o git. Pasta vazia? Sem problema: o Code começa um projeto novo nela. Dá para colar o endereço «file:///…» do gerenciador de arquivos.')));
      else if (f.source === 'new') srcBox.replaceChildren(h('label', { class: 'f' }, t('Nome do projeto')), inp('name', t('Ex.: loja-de-receitas'), 'cd-name'), h('div', { class: 'hint' }, t('O Code cria uma pasta nova nos dados do ASTA para o projeto.')));
      else {
        const list = h('div', { class: 'cd-repos' });
        srcBox.replaceChildren(h('label', { class: 'f' }, t('Repositório')), inp('repo', t('dono/repositório ou https://github.com/dono/repositório[@branch]'), 'cd-repo'), list,
          h('div', { class: 'hint' }, phone || (stt && !stt.git) ? t('Modo nuvem: o ASTA baixa o repositório, o agente edita e publica pela API do GitHub, sem precisar do git. Funciona no celular.') : t('O ASTA clona o repositório com git (ou baixa pela API do GitHub se preferir o modo nuvem em Configuração → Code).')),
          stt.github && stt.github.token ? null : h('div', { class: 'warnbox small' }, t('Sem token do GitHub: dá para ler repositórios públicos, mas não para publicar. Salve um em Configuração → Code.')));
        if (stt.github && stt.github.token) {
          if (repos === null) { try { repos = (await api('/api/code/github/repos')).repos; } catch (e) { repos = []; list.textContent = e.message; } }
          list.replaceChildren(...(repos || []).slice(0, 30).map((r) => h('button', { type: 'button', class: 'cd-repo', onclick: () => { f.repo = r.full_name; srcBox.querySelector('#cd-repo').value = r.full_name; } }, icon('github', 13), h('span', null, r.full_name), r.private ? h('span', { class: 'chip' }, t('privado')) : null)));
        }
      }
    }
    const folderOpts = [['', t('Sem pasta')]];
    const walk = (parent, depth) => st.folders.filter((x) => x.parent === parent).forEach((x) => { folderOpts.push([x.id, '\u00a0\u00a0'.repeat(depth) + x.name]); walk(x.id, depth + 1); });
    walk(null, 0);
    const effortSel = h('select', { id: 'cd-effort', onchange: (e) => { f.effort = e.target.value; hint.textContent = t((stt.efforts.find((x) => x.id === f.effort) || {}).hint || ''); } }, (stt.efforts || []).map((e) => h('option', { value: e.id, selected: e.id === f.effort }, EFFORT_LABEL[e.id] || e.id)));
    const hint = h('div', { class: 'hint' }, t(((stt.efforts || []).find((x) => x.id === f.effort) || {}).hint || ''));
    const agents = h('select', { id: 'cd-agents', onchange: (e) => { f.agents = parseInt(e.target.value, 10); } }, countsWith(f.agents).map((n) => h('option', { value: n, selected: n === f.agents }, t('{n} agente(s)', { n }))));
    let provs = [];
    try { provs = (await api('/api/chat/providers')).providers.filter((p) => p.usable || p.model); } catch (e) { /* sem lista: usa o padrão */ }
    const provSel = h('select', { id: 'cd-provider', onchange: (e) => { f.provider = e.target.value; } }, [h('option', { value: '' }, t('O padrão (o provedor escolhido em Configuração)')), ...provs.map((p) => h('option', { value: p.id }, t(p.label) + (p.local ? ' · ' + t('local') : ' · ' + t('nuvem'))))]);
    const modelIn = h('input', { id: 'cd-model', placeholder: t('Modelo (opcional)'), oninput: (e) => { f.model = e.target.value; } });
    body.append(h('label', { class: 'f' }, t('Título (opcional)')), inp('title', t('Ex.: Corrigir o login'), 'cd-new-title'),
      h('label', { class: 'f', style: { marginTop: '12px' } }, t('Projeto')), srcSeg, srcBox,
      h('div', { class: 'grid2', style: { marginTop: '12px' } },
        h('div', null, h('label', { class: 'f' }, t('Pasta de organização')), h('select', { id: 'cd-folder', onchange: (e) => { f.folder = e.target.value; } }, folderOpts.map(([v, l]) => h('option', { value: v, selected: v === f.folder }, l)))),
        h('div', null, h('label', { class: 'f' }, t('Modo')), seg([['ask', MODE().ask], ['full', MODE().full]], f.mode, (v) => { f.mode = v; modeHint.textContent = MODE_HINT()[v]; }))),
      h('div', { class: 'hint', id: 'cd-mode-hint' }, ''),
      h('div', { class: 'grid2', style: { marginTop: '12px' } }, h('div', null, h('label', { class: 'f' }, t('Esforço')), effortSel, hint),
        h('div', null, h('label', { class: 'f' }, t('Agentes ao mesmo tempo')), agents, h('div', { class: 'hint' }, t('Até 32 agentes (1, 2, 4, 8, 12, 16, 20, 24, 28 ou 32) trabalhando ao mesmo tempo.')))),
      h('div', { class: 'grid2', style: { marginTop: '12px' } }, h('div', null, h('label', { class: 'f' }, t('Modelo de IA')), provSel), h('div', null, h('label', { class: 'f' }, t('Modelo (nome)')), modelIn)),
      h('label', { class: 'f', style: { marginTop: '12px' } }, t('Ao terminar')),
      h('label', { class: 'check' }, h('input', { type: 'checkbox', id: 'cd-docs', checked: f.docs, onchange: (e) => { f.docs = e.target.checked; } }), h('span', null, t('Atualizar README, changelogs e notas de versão'))),
      h('select', { id: 'cd-publish', onchange: (e) => { f.publish = e.target.value; } }, Object.entries(PUBLISH()).map(([v, l]) => h('option', { value: v, selected: v === f.publish }, l))));
    const modeHint = body.querySelector('#cd-mode-hint');
    modeHint.textContent = MODE_HINT()[f.mode];
    await paintSource();
    const v = await modal(t('Nova sessão'), body, [{ label: t('Cancelar'), value: false }, { label: t('Criar a sessão'), value: true, cls: 'primary' }]);
    if (v !== true) return;
    const spec = { title: f.title.trim(), folder_id: f.folder || null, mode: f.mode, effort: f.effort, agents: f.agents, provider: { id: f.provider, model: f.model }, finalize: { docs: f.docs, publish: f.publish },
      workspace: f.source === 'local' ? { type: 'local', path: f.path.trim(), create: !!f.create } : f.source === 'github' ? { type: 'github', repo: f.repo.trim() } : { type: 'new', name: f.name.trim() } };
    try { const s = await api('/api/code/sessions', { method: 'POST', body: spec }); await loadList(); await select(s.id); } catch (e) { toast(e.message, 'err'); }
  }

  // ------------------------------------------------------------------ seleção e painéis
  async function select(id) {
    st.sel = id;
    history.replaceState(null, '', '#/code' + (id ? '/' + id : ''));
    await loadCur(); paintSide(); paintMain();
    mainEl.scrollTop = 0;
    if (id) api('/api/code/sessions/' + id + '/seen', { method: 'POST', body: {} }).then(loadList).catch(() => {});
  }
  function paintMain() {
    split.dataset.sel = st.sel ? '1' : '0';
    clearInterval(tick);
    if (!st.sel || !st.cur) { st.cur = null; composer = null; composerSid = ''; paintPanel(); return paintWelcome(); }
    paintSession();
    paintPanel();
    tick = setInterval(() => { if (!mainEl.isConnected) return clearInterval(tick); mainEl.querySelectorAll('[data-elapsed]').forEach((el) => { el.textContent = fmtDur(Date.now() / 1000 - Number(el.dataset.elapsed)); }); }, 1000);
  }
  function paintWelcome() {
    const stt = st.status || {};
    fill(mainEl, h('div', { class: 'card cd-welcome' },
      h('h2', null, t('Comece uma sessão')),
      h('p', { class: 'muted' }, t('Cada sessão é um projeto com a sua própria equipe: o Planejador divide o pedido, até 8 agentes trabalham ao mesmo tempo, os testes rodam e o Revisor confere antes de publicar. Você pode deixar várias sessões trabalhando em segundo plano.')),
      h('div', { class: 'cd-cards' },
        h('button', { class: 'cd-card', type: 'button', id: 'cd-start-new', onclick: () => newSessionDialog() }, icon('plus', 20), h('b', null, t('Nova sessão')), h('span', { class: 'dim small' }, t('Uma pasta do computador, um repositório do GitHub ou um projeto do zero.'))),
        h('button', { class: 'cd-card', type: 'button', onclick: () => folderDialog(null, null) }, icon('foldero', 20), h('b', null, t('Nova pasta')), h('span', { class: 'dim small' }, t('Organize as sessões em pastas e subpastas, cada uma com a sua cor.')))),
      h('ul', { class: 'muted small cd-feats' }, [t('Linguagens: Python, HTML, CSS, JavaScript, TypeScript, Java, Rust, C, C++, C#, Go e outras, com as bibliotecas de cada uma.'),
        t('Anexe imagens, PDFs, áudio, vídeo, documentos e pacotes: tudo vira contexto para gerar código.'),
        t('Provedores de IA de nuvem (frontier) ou locais; os 8 níveis de esforço valem para todos.'),
        stt.android ? t('Neste aparelho o Code trabalha pelo GitHub (nuvem); para rodar testes, use o seu computador.') : t('Ferramentas: git, GitHub, Hugging Face, terminal, pip, VS Code e Cursor.')].map((x) => h('li', null, x)))));
  }

  // cabeçalho, conversa, execução ao vivo e caixa de texto
  function paintSession() {
    const d = st.cur, run = d.run || {}, busy = isBusy(d.state), ws = d.workspace || {}, repo = ws.repo || {};
    const head = h('div', { class: 'cd-head' },
      h('button', { class: 'btn sm cd-back', type: 'button', id: 'cd-back', onclick: () => select('') }, icon('arrow', 13), t('Sessões')),
      h('h2', { id: 'cd-title', title: t('Clique para renomear'), onclick: () => renameSession({ id: d.id, title: d.title }) }, d.title),
      h('div', { class: 'row cd-meta' }, h('span', { class: 'cd-st ' + (d.state || 'idle'), id: 'cd-state' }, stateDot(d.state, (run.pendings || []).some((p) => p.answer == null)), (run.pendings || []).some((p) => p.answer == null) ? t('Aguardando você') : STATE()[d.state] || ''),
        h('span', { class: 'chip', title: ws.path || '' }, icon(ws.kind === 'cloud' || repo.owner ? 'github' : 'foldero', 12), ws.label || t('sem projeto')),
        repo.branch ? h('span', { class: 'chip' }, icon('branch', 12), repo.branch) : null,
        h('span', { class: 'chip cd-mode ' + d.mode, title: MODE_HINT()[d.mode] }, icon(d.mode === 'full' ? 'warn' : 'lock', 12), MODE()[d.mode]),
        h('span', { class: 'chip' }, icon('bolt', 12), EFFORT_LABEL[d.effort] || d.effort), h('span', { class: 'chip' }, icon('layers', 12), t('{n} agente(s)', { n: d.agents })),
        run.provider && run.provider.label ? h('span', { class: 'chip' }, run.provider.demo ? t('Demo (sem IA)') : (run.provider.model || run.provider.label)) : null,
        repo.pr_url ? h('a', { class: 'chip link', href: repo.pr_url, target: '_blank', rel: 'noopener' }, icon('branch', 12), t('Pull request')) : null));
    const msgs = h('div', { class: 'cd-msgs', id: 'cd-msgs' }, ...(d.messages || []).map(messageEl));
    if (ws.status === 'preparing') msgs.append(h('div', { class: 'card cd-prep' }, h('div', { class: 'spinner' }), h('span', null, t('Preparando o repositório (baixando e abrindo o projeto)…'))));
    if (ws.status === 'error') msgs.append(h('div', { class: 'errbox', style: { whiteSpace: 'normal' } }, t('Não foi possível preparar o projeto: {e}', { e: ws.error || '' })));
    const live = runBlock(d);
    const asks = approvalCards(d.id, run, () => refreshCur());
    fill(mainEl, head, msgs, live, ...asks, composerBox(d, busy));
    if (!busy && msgs.lastChild && !msgs.querySelector('.cd-prep')) msgs.lastChild.scrollIntoView({ block: 'nearest' });
  }
  function messageEl(m) {
    if (m.role === 'user') return h('div', { class: 'cd-msg user', dataset: { msg: m.id } }, h('div', { class: 'cd-bubble' }, m.text, (m.attachments || []).length ? h('div', { class: 'cd-att' }, ...m.attachments.map((a) => h('span', { class: 'chip' }, icon('clip', 11), a.name))) : null));
    const body = h('div', { class: 'md' });
    renderMarkdown(body, m.text || '');
    return h('div', { class: 'cd-msg ai ' + (m.status || ''), dataset: { msg: m.id } }, h('div', { class: 'cd-ai-h' }, icon('code', 14), h('b', null, 'Code'), m.status ? h('span', { class: 'cd-rs ' + m.status }, RUN_STATUS()[m.status] || m.status) : null), body);
  }

  // a execução (plano, agentes, ações, testes, revisão): ao vivo enquanto trabalha; recolhida depois
  function runBlock(d) {
    const run = d.run || {};
    if (!run.id) return h('div');
    const busy = isBusy(d.state);
    const el = h('div', { class: 'cd-run card', id: 'cd-run', open: busy });
    const title = h('div', { class: 'cd-run-h' }, icon('layers', 15), h('b', null, busy ? t('A equipe está trabalhando') : t('Detalhes da última execução')), h('span', { class: 'cd-rs ' + (run.status || '') }, RUN_STATUS()[run.status] || ''),
      run.started ? h('span', { class: 'dim small' }, busy ? h('span', { 'data-elapsed': String(run.started) }, fmtDur(Date.now() / 1000 - run.started)) : fmtDur((run.finished || run.started) - run.started)) : null, h('span', { class: 'grow' }),
      run.steps && run.steps.length ? h('span', { class: 'dim small' }, t('{n} ação(ões)', { n: run.steps.length })) : null);
    const kids = [title];
    if (run.now && busy) kids.push(h('div', { class: 'cd-now' }, h('span', { class: 'spinner' }), run.now));
    if ((run.warnings || []).length) kids.push(h('div', { class: 'warnbox small' }, run.warnings.join(' · ')));
    kids.push(agentsGrid(run));
    kids.push(h('details', { class: 'cd-acts', open: busy, id: 'cd-acts' }, h('summary', null, t('Ações ({n})', { n: (run.steps || []).length })), actionList(run)));
    if ((run.checks || []).length) kids.push(h('div', { class: 'cd-checks' }, ...run.checks.map((c) => h('details', { class: 'cd-check ' + (c.ok ? 'ok' : 'bad') }, h('summary', null, icon(c.ok ? 'check' : 'x', 13), c.label + ' — ' + (c.ok ? t('passou') : t('falhou'))), h('pre', null, c.output || '')))));
    if (run.review) kids.push(h('div', { class: 'cd-review ' + run.review.verdict }, h('b', null, t('Revisão: {v} ({s}/10)', { v: ({ pass: t('aprovado'), partial: t('parcial'), fail: t('reprovado') })[run.review.verdict] || run.review.verdict, s: run.review.score })),
      (run.review.issues || []).length ? h('ul', null, ...run.review.issues.map((x) => h('li', null, x))) : null));
    fill(el, ...kids);
    return el;
  }
  function agentsGrid(run) {
    const list = (run.agents || []).filter((a) => a.status !== 'idle' || a.id.startsWith('w'));
    if (!list.length) return h('div');
    return h('div', { class: 'cd-team', id: 'cd-team' }, ...list.map((a) => {
      const meta = AGENT()[a.id] || [];
      const name = meta[0] || t('Agente {n}', { n: String(a.id).slice(1) });
      const role = a.role ? (ROLE()[a.role] || a.role) : '';
      return h('div', { class: 'cd-ag ' + a.status, dataset: { agent: a.id, status: a.status }, title: meta[1] || '' },
        h('span', { class: 'cd-ag-i' }, a.status === 'running' ? h('span', { class: 'spinner' }) : icon(a.status === 'done' ? 'check' : a.status === 'error' ? 'x' : a.status === 'warn' ? 'warn' : a.status === 'idle' ? 'pause' : 'sparkle', 15)),
        h('b', null, name), role && a.status !== 'idle' ? h('span', { class: 'chip' }, role) : null, a.note ? h('span', { class: 'small dim' }, a.note) : null);
    }));
  }
  function actionList(run) {
    const steps = (run.steps || []).slice(-80);
    if (!steps.length) return h('div', { class: 'dim small', style: { padding: '8px 4px' } }, t('Nenhuma ação ainda.'));
    return h('div', { class: 'cd-steps' }, ...steps.map((s) => {
      const open = h('div', { class: 'cd-sd' }, s.output ? h('pre', null, s.output) : h('span', { class: 'dim small' }, t('Sem resultado ainda.')), (s.sources || []).length ? h('div', { class: 'small' }, ...s.sources.map((x) => h('a', { href: x.url, target: '_blank', rel: 'noopener', style: { display: 'block' } }, x.title || x.url))) : null);
      const row = h('div', { class: 'cd-step ' + s.status, dataset: { n: s.n, tool: s.tool, status: s.status } },
        h('button', { class: 'cd-sh', type: 'button', onclick: () => row.classList.toggle('open') }, h('span', { class: 'cd-sn' }, '#' + s.n), h('span', { class: 'cd-si' }, icon(TOOL_ICON[s.tool] || 'file', 14)),
          h('span', { class: 'cd-sl' }, describeAction(s.tool, s.args)), s.agent ? h('span', { class: 'chip' }, String(s.agent).startsWith('w') ? t('Agente {n}', { n: String(s.agent).slice(1) }) : ((AGENT()[s.agent] || [])[0] || s.agent)) : null,
          h('span', { class: 'cd-ss ' + s.status }, s.status === 'running' ? h('span', { class: 'spinner' }) : null, STEP_STATUS()[s.status] || s.status), s.dur ? h('span', { class: 'cd-sd-t' }, fmtDur(s.dur)) : null, icon('chevr', 13)), open);
      return row;
    }));
  }

  // ------------------------------------------------------------------ caixa de texto (multimodal) e controles da sessão
  function composerBox(d, busy) {
    const ws = d.workspace || {};
    const notReady = ws.status !== 'ready';
    const finalize = { docs: !!(d.finalize || {}).docs, publish: (d.finalize || {}).publish || 'none' };
    const bar = [];
    const modeBtn = h('button', { class: 'tool cd-modebtn ' + d.mode, type: 'button', id: 'cd-mode', title: MODE_HINT()[d.mode], onclick: async () => { const next = d.mode === 'ask' ? 'full' : 'ask'; if (next === 'full' && !(await confirmDialog(t('No Full Access o Code executa tudo sem perguntar nada (os limites fixos de segurança continuam valendo). Ativar?'), false, t('Ativar')))) return; await patch({ mode: next }); } },
      icon(d.mode === 'full' ? 'warn' : 'lock', 14), MODE()[d.mode]);
    const effort = h('select', { class: 'cd-sel', id: 'cd-effort-sel', title: t('Nível de esforço'), 'aria-label': t('Nível de esforço'), onchange: (e) => patch({ effort: e.target.value }) }, ((st.status || {}).efforts || []).map((e) => h('option', { value: e.id, selected: e.id === d.effort }, EFFORT_LABEL[e.id])));
    const agents = h('select', { class: 'cd-sel', id: 'cd-agents-sel', title: t('Agentes ao mesmo tempo'), 'aria-label': t('Agentes ao mesmo tempo'), onchange: (e) => patch({ agents: parseInt(e.target.value, 10) }) }, countsWith(d.agents).map((n) => h('option', { value: n, selected: n === d.agents }, t('{n} agente(s)', { n }))));
    const modelBtn = h('button', { class: 'tool', type: 'button', id: 'cd-model-btn', title: t('Modelo de IA desta sessão'), onclick: (e) => modelPicker(e.currentTarget, d) }, icon('sparkle', 14), (d.provider && (d.provider.model || d.provider.id)) ? (d.provider.model || d.provider.id) : t('Modelo'));
    const fin = h('button', { class: 'tool', type: 'button', id: 'cd-finalize', title: t('O que fazer ao terminar'), onclick: (e) => finalizeMenu(e.currentTarget, d, finalize) }, icon('upload', 14), finalize.publish !== 'none' || finalize.docs ? t('Ao terminar: {x}', { x: [finalize.docs ? t('docs') : '', finalize.publish !== 'none' ? PUBLISH()[finalize.publish] : ''].filter(Boolean).join(' + ') }) : t('Ao terminar'));
    bar.push(modeBtn, effort, agents, modelBtn, fin);
    if (composerSid !== d.id || !composer) {
      composer = createComposer({ placeholder: t('Peça uma mudança, uma correção, uma revisão… (anexe imagens, PDFs, áudio, código)'), tools: bar, sendLabel: t('Enviar'), onSend: ({ text, ids }) => send(text, ids) });
      composerSid = d.id;
    } else { composer.configure({ tools: bar, placeholder: t('Peça uma mudança, uma correção, uma revisão… (anexe imagens, PDFs, áudio, código)') }); }
    composer.setBusy(busy, () => cancelRun());
    const wrap = h('div', { class: 'cd-composer' + (notReady ? ' off' : '') }, composer.el);
    if (notReady) wrap.append(h('div', { class: 'dim small' }, t('Espere o projeto ficar pronto para enviar pedidos.')));
    return wrap;
  }
  async function patch(body) { try { st.cur = Object.assign(st.cur, await api('/api/code/sessions/' + st.sel, { method: 'PUT', body })); await loadList(); paintMain(); } catch (e) { toast(e.message, 'err'); } }
  function finalizeMenu(anchor, d, fin) {
    const docs = h('input', { type: 'checkbox', id: 'cd-fin-docs', checked: fin.docs }), pub = h('select', { id: 'cd-fin-pub' }, Object.entries(PUBLISH()).map(([v, l]) => h('option', { value: v, selected: v === fin.publish }, l)));
    const box = h('div', { class: 'cd-fin' }, h('b', null, t('Ao terminar o pedido')),
      h('label', { class: 'check' }, docs, h('span', null, t('Atualizar README, changelogs e notas de versão'))),
      h('label', { class: 'f' }, t('Publicar')), pub, h('p', { class: 'dim small', style: { margin: '6px 0 0' } }, t('A publicação só acontece depois dos testes e da revisão sem problema. «Direto na branch principal» só vale quando você escolhe aqui.')),
      h('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: '8px' } }, h('button', { class: 'btn primary sm', type: 'button', id: 'cd-fin-ok', onclick: async () => { pop.close(); await patch({ finalize: { docs: docs.checked, publish: pub.value } }); } }, t('Salvar'))));
    const pop = popover(anchor, box);
  }
  async function modelPicker(anchor, d) {
    const box = h('div', { class: 'mpick' }, h('div', { class: 'spinner' }));
    const pop = popover(anchor, box);
    let data;
    try { data = await api('/api/chat/providers'); } catch (e) { pop.close(); return toast(e.message, 'err'); }
    const choose = async (pid, model) => { pop.close(); await patch({ provider: { id: pid, model } }); toast(pid ? t('Esta sessão vai usar {n}', { n: (model || pid) }) : t('Esta sessão volta a usar o provedor padrão'), 'ok'); };
    const models = {}; let openId = '';
    const body = h('div', { class: 'mp-body' });
    const paint = () => {
      const rows = [h('div', { class: 'mp-prov' + (!(d.provider && d.provider.id) ? ' on' : ''), role: 'button', tabindex: '0', onclick: () => choose('', '') }, h('span', { class: 'grow' }, t('O padrão (o provedor escolhido em Configuração)')))];
      data.providers.filter((p) => p.usable || p.model).forEach((p) => {
        const open = openId === p.id;
        rows.push(h('div', { class: 'mp-prov' + (d.provider && d.provider.id === p.id ? ' on' : ''), role: 'button', tabindex: '0', onclick: () => { openId = open ? '' : p.id; paint(); } },
          h('span', { class: 'grow' }, t(p.label)), p.local ? h('span', { class: 'badge' }, t('local')) : h('span', { class: 'badge' }, t('nuvem')), icon('chev', 13)));
        if (open) {
          const list = h('div', { class: 'mp-models' }, h('div', { class: 'spinner' }));
          rows.push(list);
          (models[p.id] ? Promise.resolve(models[p.id]) : api('/api/providers/models', { method: 'POST', body: { id: p.id, config: {} } }).catch((e) => ({ models: [], error: e.message }))).then((r) => {
            models[p.id] = r;
            const manual = h('input', { placeholder: t('Outro modelo (digite o nome)…'), onkeydown: (e) => { if (e.key === 'Enter' && manual.value.trim()) choose(p.id, manual.value.trim()); } });
            list.replaceChildren(h('div', { class: 'mp-model', onclick: () => choose(p.id, '') }, t('Automático (o modelo configurado)')), ...(r.models || []).map((m) => h('div', { class: 'mp-model' + (d.provider && d.provider.model === m ? ' on' : ''), onclick: () => choose(p.id, m) }, m)), h('div', { style: { padding: '6px 6px 2px' } }, manual));
          });
        }
      });
      body.replaceChildren(...rows, h('div', { class: 'mp-foot' }, h('a', { href: '#/config', onclick: () => { pop.close(); state.ctx = { tab: 'providers' }; return true; } }, icon('config', 13), t('Gerenciar provedores…'))));
    };
    box.replaceChildren(h('div', { class: 'mp-title' }, t('Modelo desta sessão')), body);
    paint();
  }
  async function send(text, ids) {
    const d = st.cur;
    try {
      st.cur = await api('/api/code/sessions/' + d.id + '/send', { method: 'POST', body: { text, attachment_ids: ids, options: { mode: d.mode, effort: d.effort, agents: d.agents, finalize: d.finalize } } });
      if (composer) { composer.setText(''); composer.clearFiles(ids); }
      await loadList(); paintMain();
    } catch (e) { toast(e.message, 'err'); }
  }
  async function cancelRun() { try { await api('/api/code/sessions/' + st.sel + '/cancel', { method: 'POST', body: {} }); } catch (e) { toast(e.message, 'err'); } }

  // ------------------------------------------------------------------ painel da direita: ambiente, plano, saídas
  function paintPanel() {
    const d = st.cur;
    if (!d) return fill(panelEl);
    const run = d.run || {}, ws = d.workspace || {}, repo = ws.repo || {}, plan = (run.plan || {}).steps || [], files = d.files || [], stt = st.status || {};
    const sect = (title, ...kids) => h('div', { class: 'cd-ps' }, h('div', { class: 'cd-pt' }, title), ...kids);
    const kv = (k, v) => v ? h('div', { class: 'cd-kv' }, h('span', { class: 'dim' }, k), h('span', null, v)) : null;
    const editorOk = !stt.android && (stt.editors.vscode || stt.editors.cursor);
    fill(panelEl,
      sect(t('Ambiente'), kv(t('Projeto'), ws.label), kv(t('Pasta'), ws.kind === 'cloud' ? t('Cópia na nuvem do ASTA') : ws.path), kv(t('Modo do GitHub'), ws.kind === 'cloud' ? t('nuvem (API)') : ws.kind === 'git' ? 'git' : ''), kv(t('Branch base'), repo.base_branch),
        kv(t('Branch de trabalho'), repo.branch), kv(t('Permissões lembradas'), (d.allowed || []).length ? d.allowed.join(', ') : ''),
        h('div', { class: 'row cd-pact' },
          editorOk && stt.editors.vscode ? h('button', { class: 'btn sm', type: 'button', id: 'cd-vscode', onclick: () => openEditor('vscode') }, icon('code', 13), 'VS Code') : null,
          editorOk && stt.editors.cursor ? h('button', { class: 'btn sm', type: 'button', id: 'cd-cursor', onclick: () => openEditor('cursor') }, icon('code', 13), 'Cursor') : null,
          h('button', { class: 'btn sm', type: 'button', id: 'cd-files', onclick: () => filesDialog() }, icon('foldero', 13), t('Arquivos')))),
      plan.length ? sect(t('Plano'), h('ol', { class: 'cd-plan', id: 'cd-plan' }, ...plan.map((p) => h('li', { class: p.status + (p.incomplete ? ' incomplete' : ''), dataset: { step: p.id, status: p.status, incomplete: p.incomplete ? '1' : '' }, title: p.done_when || '' },
        h('span', { class: 'cd-pi' }, p.status === 'running' ? h('span', { class: 'spinner' }) : icon(p.incomplete ? 'warn' : p.status === 'done' ? 'check' : p.status === 'failed' ? 'x' : p.status === 'skipped' ? 'pause' : 'file', 13)),
        h('span', null, h('span', null, p.title), h('span', { class: 'dim small', style: { display: 'block' } }, (ROLE()[p.role] || p.role) + ' · ' + (p.incomplete ? t('Incompleta (limite de ações)') : (PLAN_STATUS()[p.status] || p.status)) + ((p.depends_on || []).length ? ' · ' + t('depois de {d}', { d: p.depends_on.join(', ') }) : '')))))))
        : null,
      sect(t('Saídas'), files.length ? h('ul', { class: 'cd-files', id: 'cd-changed' }, ...files.slice(0, 60).map((f) => h('li', { dataset: { path: f.path, status: f.status } }, h('button', { class: 'cd-fl', type: 'button', onclick: () => diffDialog(f.path) }, h('span', { class: 'cd-fs ' + f.status }, FILE_STATUS()[f.status] || f.status), h('span', { class: 'mono' }, f.path)))))
        : h('div', { class: 'dim small' }, t('Nenhum arquivo foi mudado ainda.')),
      h('div', { class: 'row cd-pact' }, files.length ? h('button', { class: 'btn sm', type: 'button', id: 'cd-diff', onclick: () => diffDialog('') }, icon('eye', 13), t('Ver tudo (diff)')) : null,
        d.undo && !isBusy(d.state) ? h('button', { class: 'btn sm danger', type: 'button', id: 'cd-undo', onclick: undo }, icon('undo', 13), t('Desfazer')) : null)));
  }
  async function undo() {
    if (!(await confirmDialog(t('Desfazer as mudanças em arquivos desta sessão? Os arquivos voltam ao que eram antes do Code mexer.'), true, t('Desfazer')))) return;
    try { const r = await api('/api/code/sessions/' + st.sel + '/undo', { method: 'POST', body: {} }); toast(t('{n} mudança(s) desfeita(s)', { n: (r.notes || []).length }), 'ok'); await refreshCur(); } catch (e) { toast(e.message, 'err'); }
  }
  async function openEditor(which, path, line) { try { await api('/api/code/sessions/' + st.sel + '/editor', { method: 'POST', body: { editor: which, path: path || '.', line } }); toast(t('Aberto no editor'), 'ok'); } catch (e) { toast(e.message, 'err'); } }
  async function diffDialog(path) {
    let r;
    try { r = await api('/api/code/sessions/' + st.sel + '/diff?path=' + encodeURIComponent(path || '')); } catch (e) { return toast(e.message, 'err'); }
    const pre = h('pre', { class: 'cd-diff' }, ...String(r.diff || t('(sem diferenças)')).split('\n').map((ln) => h('span', { class: ln.startsWith('+') && !ln.startsWith('+++') ? 'add' : ln.startsWith('-') && !ln.startsWith('---') ? 'del' : ln.startsWith('@@') ? 'hunk' : '' }, ln + '\n')));
    await modal(path ? t('Mudanças em {p}', { p: path }) : t('Todas as mudanças'), h('div', { class: 'cd-diffbox' }, pre), [{ label: t('Fechar'), value: null, cls: 'primary' }]);
  }
  async function filesDialog() {
    let cur = '.';
    const crumbs = h('div', { class: 'cd-crumbs mono small' }), list = h('div', { class: 'cd-flist' }), view = h('div', { class: 'cd-fview-wrap' }, h('pre', { class: 'cd-fview' }, t('Escolha um arquivo.')));
    function showFile(r, path) {
      if (r.binary) { view.replaceChildren(h('pre', { class: 'cd-fview' }, t('Arquivo binário ({n} bytes).', { n: r.size }))); return; }
      const text = String(r.text || '') + (r.truncated ? '\n…' : '');
      const md = /\.(md|markdown)$/i.test(path || r.path || '');
      if (md) {
        const body = h('div', { class: 'md cd-fmd' });
        renderMarkdown(body, text);
        view.replaceChildren(body);
      } else {
        view.replaceChildren(h('pre', { class: 'cd-fview' }, text));
      }
    }
    async function go(path) {
      cur = path;
      try {
        const r = await api('/api/code/sessions/' + st.sel + '/browse?path=' + encodeURIComponent(path) + '&limit=2000');
        crumbs.textContent = '/' + (r.path === '.' ? '' : r.path);
        const nodes = [...(r.path !== '.' ? [h('button', { class: 'cd-fi2', type: 'button', onclick: () => go(r.path.split('/').slice(0, -1).join('/') || '.') }, icon('arrow', 13), '..')] : []),
          ...r.items.map((it) => h('button', { class: 'cd-fi2', type: 'button', dataset: { path: it.path }, onclick: () => (it.dir ? go(it.path) : openF(it.path)) }, icon(it.dir ? 'foldero' : 'file', 13), h('span', null, it.name)))];
        if (r.truncated) nodes.push(h('div', { class: 'dim small', style: { padding: '6px 8px' } }, t('Mostrando {n} de {t} itens (pasta muito grande).', { n: r.items.length, t: r.total || r.items.length })));
        list.replaceChildren(...nodes);
      } catch (e) { list.textContent = e.message; }
    }
    async function openF(path) {
      view.replaceChildren(h('pre', { class: 'cd-fview' }, t('Carregando…')));
      try { const r = await api('/api/code/sessions/' + st.sel + '/file?path=' + encodeURIComponent(path)); showFile(r, path); } catch (e) { view.replaceChildren(h('pre', { class: 'cd-fview' }, e.message)); }
    }
    await go('.');
    await modal(t('Arquivos do projeto'), h('div', { class: 'cd-fbrowser' }, crumbs, h('div', { class: 'cd-fcols' }, list, view)), [{ label: t('Fechar'), value: null, cls: 'primary' }]);
  }

  // ------------------------------------------------------------------ eventos ao vivo
  async function refreshCur() {
    clearTimeout(refreshT);
    if (!st.sel) return;
    const keepText = composer ? composer.text() : '';
    await loadCur(true);
    if (!mainEl.isConnected) return;
    if (st.cur) { paintSession(); paintPanel(); if (composer && keepText && !composer.text()) composer.setText(keepText); } else paintMain();
    await loadList();
  }
  off = subscribe((ev) => {
    if (!root.isConnected) { if (off) off(); clearInterval(tick); return; }
    if (ev.type === 'status' && ev.status) { st.status = ev.status; paintCap(); }
    if (ev.type === 'folders') { st.folders = ev.folders; paintSide(); }
    if (ev.type === 'session') {
      const i = st.sessions.findIndex((s) => s.id === ev.session.id);
      if (i >= 0) st.sessions[i] = ev.session; else st.sessions.unshift(ev.session);
      paintSide();
      if (ev.session.id === st.sel) { clearTimeout(refreshT); refreshT = setTimeout(refreshCur, 120); if (ev.session.state === 'finished') api('/api/code/sessions/' + st.sel + '/seen', { method: 'POST', body: {} }).catch(() => {}); }
    }
  });

  await loadList();
  if (st.sel) { await loadCur(true); if (!st.cur) st.sel = ''; }
  paintSide(); paintMain();
}
