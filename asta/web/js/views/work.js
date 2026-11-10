// Work — trabalho em equipe com IA: pessoas e cargos, quadro de fluxograma, setores com arquivos, pedidos, atividades, avisos em tempo real e a rede entre as máquinas.
// Esta tela cuida da entrada (criar/entrar numa rede, login) e da moldura com as abas; cada aba mora no seu arquivo (work_*.js).
import { api } from '../api.js';
import { t } from '../i18n.js';
import { state } from '../main.js';
import { avatarEl, fmtAgo, startEvents, stopEvents, subscribe, workStatus, can } from '../work_ui.js';
import { field, fill, h, icon, popover, select, toast } from '../ui.js';

const TABS = [['home', 'Início', 'work'], ['board', 'Quadro', 'network'], ['people', 'Pessoas', 'characters'], ['files', 'Arquivos', 'folder'], ['requests', 'Pedidos', 'send'], ['activities', 'Atividades', 'bolt'], ['net', 'Rede', 'globe']];
const LOADERS = { home: () => import('./work_home.js'), board: () => import('./work_board.js'), people: () => import('./work_people.js'), files: () => import('./work_files.js'), requests: () => import('./work_requests.js'), activities: () => import('./work_activities.js'), net: () => import('./work_network.js') };
const parseHash = () => { const m = location.hash.match(/^#\/work(?:\/(\w+))?(?:\/([\w-]+))?/); return { tab: m && LOADERS[m[1]] ? m[1] : 'home', arg: (m && m[2]) || '' }; };

export default async function render(root, ctx) {
  let st;
  try { st = await api('/api/work/status'); } catch (e) { root.replaceChildren(h('div', { class: 'page narrow' }, h('div', { class: 'errbox' }, e.message))); return; }
  if (!st.orgs.length) return onboarding(root, st);
  if (!st.session) return loginView(root, st);
  return shell(root, st, ctx || {});
}

const rerender = () => window.dispatchEvent(new CustomEvent('asta:go', { detail: { route: 'work' } }));

// ------------------------------------------------------------------------------------------------ criar ou entrar numa rede
function createForm(st, onDone) {
  const f = { name: '', display: '', user: '', pw: '', mode: 'synced', machine: st.machine.name };
  const inp = (k, ph, type = 'text', id) => { const el = h('input', { type, placeholder: ph || '', value: f[k], id: id || ('wk-new-' + k), autocomplete: type === 'password' ? 'new-password' : 'off' }); el.addEventListener('input', () => { f[k] = el.value; }); return el; };
  const modeSel = select([['synced', t('Em todas as máquinas da rede (recomendado)')], ['local', t('Só nesta máquina')]], f.mode, (v) => { f.mode = v; });
  const err = h('div', { class: 'errbox hidden', style: { whiteSpace: 'normal' } });
  const go = h('button', { class: 'btn primary', type: 'button', id: 'wk-create', onclick: async () => {
    err.classList.add('hidden');
    try {
      await api('/api/work/orgs', { method: 'POST', body: { name: f.name, machine_name: f.machine, admin: { username: f.user || f.display, display_name: f.display || f.user, password: f.pw, auth_mode: f.mode, title: t('Administrador') } } });
      startEvents(); toast(t('Organização criada. Você é o administrador.'), 'ok'); onDone();
    } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); }
  } }, icon('plus', 15), t('Criar organização'));
  return h('div', { class: 'wk-form' },
    field(t('Nome da organização'), inp('name', t('Ex.: Estúdio Aurora'))),
    h('div', { class: 'grid2' }, field(t('Seu nome'), inp('display', t('Ex.: Ana Souza'))), field(t('Nome de usuário'), inp('user', 'ana', 'text', 'wk-new-user'), t('2 a 32 letras minúsculas, números, ponto, hífen ou sublinhado.'))),
    h('div', { class: 'grid2' }, field(t('Senha (opcional)'), inp('pw', t('Deixe vazio para entrar sem senha'), 'password'), t('Pelo menos 6 caracteres. Você pode criar ou trocar depois.')), field(t('Onde guardar a senha'), modeSel)),
    field(t('Nome desta máquina'), inp('machine', '', 'text', 'wk-new-machine'), t('Aparece para as outras máquinas da rede.')),
    err, go);
}
function joinForm(st, onDone) {
  const f = { code: '', machine: st.machine.name };
  const code = h('textarea', { rows: 3, id: 'wk-join-code', placeholder: 'AW1.…', spellcheck: 'false' });
  code.addEventListener('input', () => { f.code = code.value.trim(); });
  const machine = h('input', { value: f.machine, id: 'wk-join-machine' });
  machine.addEventListener('input', () => { f.machine = machine.value; });
  const err = h('div', { class: 'errbox hidden', style: { whiteSpace: 'normal' } });
  return h('div', { class: 'wk-form' },
    h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Peça a quem administra a rede um código de convite (Work → Rede → Convidar máquina). Ele vale por 24 horas e só entra uma máquina por código.')),
    field(t('Código de convite'), code), field(t('Nome desta máquina'), machine), err,
    h('button', { class: 'btn primary', type: 'button', id: 'wk-join', onclick: async () => {
      err.classList.add('hidden');
      try { await api('/api/work/join', { method: 'POST', body: { code: f.code, machine_name: f.machine } }); toast(t('Esta máquina entrou na rede. Os dados estão sincronizando.'), 'ok'); onDone(); } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); }
    } }, icon('arrow', 15), t('Entrar na rede')));
}
function tailscaleLine(st) {
  const ts = st.tailscale || {};
  const txt = !ts.installed ? t('Tailscale: não instalado (opcional — o Work também sincroniza pela rede local ou por uma pasta de nuvem).')
    : ts.running ? t('Tailscale: conectado · IP {ip} · {n} máquina(s) na tailnet', { ip: ts.ip, n: (ts.peers || []).length }) : t('Tailscale: instalado, mas desconectado.');
  return h('p', { class: 'dim small', style: { margin: '14px 0 0' } }, icon('globe', 13), ' ', txt);
}

function onboarding(root, st) {
  root.replaceChildren(h('div', { class: 'page wk-page' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, t('Work')),
      h('p', null, t('Trabalho em equipe com IA: pessoas, cargos, fluxograma da empresa, arquivos que sincronizam sozinhos entre as máquinas, pedidos, atividades e avisos em tempo real.')))),
    h('div', { class: 'wk-onboard' },
      h('div', { class: 'card' }, h('h3', null, t('Criar uma organização')), h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Você começa como administrador. Os dados ficam só neste computador, em arquivos comuns, até você ligar a sincronização.')), createForm(st, rerender)),
      h('div', { class: 'card' }, h('h3', null, t('Entrar numa rede que já existe')), joinForm(st, rerender))),
    tailscaleLine(st)));
}

// ------------------------------------------------------------------------------------------------ login
function loginView(root, st) {
  let org = st.orgs[0].id, people = [], pick = null;
  const list = h('div', { class: 'wk-people' });
  const pw = h('input', { type: 'password', id: 'wk-pw', placeholder: t('Senha'), autocomplete: 'current-password' });
  const pwBox = h('div', { class: 'hidden', style: { marginTop: '12px' } }, field(t('Senha'), pw));
  const err = h('div', { class: 'errbox hidden', style: { whiteSpace: 'normal', marginTop: '10px' } });
  const enter = h('button', { class: 'btn primary', type: 'button', id: 'wk-enter', disabled: true, onclick: submit }, icon('arrow', 15), t('Entrar'));
  pw.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
  async function submit() {
    if (!pick) return;
    err.classList.add('hidden');
    try { await api('/api/work/login', { method: 'POST', body: { org, username: pick.username, password: pw.value } }); startEvents(); rerender(); } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); }
  }
  async function load() {
    try { people = (await api(`/api/work/orgs/${org}/people`)).people; } catch (e) { people = []; }
    pick = null; enter.disabled = true; pwBox.classList.add('hidden'); pw.value = '';
    fill(list, ...people.map((p) => h('button', { class: 'wk-person', type: 'button', dataset: { user: p.username }, onclick: () => {
      pick = p; enter.disabled = false;
      list.querySelectorAll('.wk-person').forEach((b) => b.classList.toggle('on', b.dataset.user === p.username));
      pwBox.classList.toggle('hidden', p.auth === 'none'); if (p.auth !== 'none') pw.focus();
    } }, avatarEl({ display_name: p.display_name, username: p.username, avatar_color: p.color }, 42), h('span', { class: 'grow' }, h('b', null, p.display_name || p.username), h('span', { class: 'small dim' }, '@' + p.username + (p.role ? ' · ' + p.role : ''))),
    p.auth !== 'none' ? icon('lock', 14) : null)));
  }
  const orgSel = st.orgs.length > 1 ? field(t('Rede'), select(st.orgs.map((o) => [o.id, o.name]), org, (v) => { org = v; load(); })) : null;
  const more = h('details', { class: 'wk-more' }, h('summary', null, t('Criar outra organização ou entrar noutra rede')),
    h('div', { class: 'wk-onboard' }, h('div', { class: 'card' }, h('h3', null, t('Criar uma organização')), createForm(st, rerender)), h('div', { class: 'card' }, h('h3', null, t('Entrar numa rede que já existe')), joinForm(st, rerender))));
  root.replaceChildren(h('div', { class: 'page narrow wk-page' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, t('Work')), h('p', null, t('Escolha quem você é. A máquina «{m}» guarda a sua sessão.', { m: st.machine.name })))),
    h('div', { class: 'card' }, orgSel, list, pwBox, err, h('div', { class: 'row', style: { marginTop: '14px' } }, enter)), more, tailscaleLine(st)));
  load();
}

// ------------------------------------------------------------------------------------------------ moldura com as abas
async function shell(root, st, ctx) {
  startEvents();
  let me, dir;
  const reloadBase = async () => { me = await api('/api/work/me'); dir = await api('/api/work/directory'); };
  try { await reloadBase(); } catch (e) { stopEvents(); return rerender(); }
  const cur = parseHash();
  if (ctx.tab) cur.tab = ctx.tab;
  if (ctx.arg) cur.arg = ctx.arg;
  const body = h('div', { class: 'wk-body' });
  const bell = h('button', { class: 'btn ghost icon wk-bell', type: 'button', id: 'wk-bell', title: t('Avisos'), onclick: () => openBell(bell) }, icon('bell', 18), h('span', { class: 'wk-bell-n hidden', id: 'wk-bell-n' }));
  const paintBell = () => { const n = workStatus().unread; const b = bell.querySelector('.wk-bell-n'); b.textContent = n > 99 ? '99+' : String(n); b.classList.toggle('hidden', !n); };
  const tabs = h('nav', { class: 'wk-tabs', 'aria-label': t('Work') }, TABS.map(([id, label, ic]) => h('a', { class: 'wk-tab' + (cur.tab === id ? ' on' : ''), href: '#/work/' + id, dataset: { tab: id }, onclick: () => { state.ctx = {}; } }, icon(ic, 15), t(label))));
  const role = (dir.roles.find((r) => r.id === me.user.role_id) || {}).name || '';
  root.replaceChildren(h('div', { class: 'page wk-page' },
    h('div', { class: 'page-h' },
      h('div', { class: 'row', style: { gap: '14px', alignItems: 'center' } }, avatarEl({ ...me.user, online: true }, 44), h('div', null, h('h1', { style: { fontSize: '22px' } }, me.org.name), h('p', { style: { margin: 0 } }, (me.user.display_name || me.user.username) + ' · ' + role + ' · ' + me.machine.name))),
      h('div', { class: 'row' }, bell, h('button', { class: 'btn sm', type: 'button', id: 'wk-logout', onclick: async () => { await api('/api/work/logout', { method: 'POST', body: {} }); stopEvents(); rerender(); } }, icon('x', 13), t('Sair')))),
    tabs, body));
  paintBell();

  // contexto entregue às abas
  const liveHandlers = new Set();
  const W = {
    get me() { return me; }, get dir() { return dir; }, arg: cur.arg, tab: cur.tab,
    reloadBase: async () => { await reloadBase(); }, can: (p) => can(me, p),
    go: (tab, arg) => { location.hash = '#/work/' + tab + (arg ? '/' + arg : ''); },
    live: (kinds, fn) => { const h_ = { kinds, fn }; liveHandlers.add(h_); return () => liveHandlers.delete(h_); },
    refreshBell: paintBell,
  };
  let timer = null; const pending = new Set();
  const off = subscribe((ev) => {
    if (!document.body.contains(body)) { off(); return; }
    if (ev.type === 'stopped' || ev.type === 'logout') { off(); rerender(); return; }
    if (ev.type === 'unread') paintBell();
    if (ev.type === 'change') {
      pending.add(ev.kind);
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const kinds = new Set(pending); pending.clear();
        if (['users', 'roles', 'functions', 'folders', 'machines'].some((k) => kinds.has(k))) { try { await reloadBase(); } catch (e) { /* sessão encerrada */ } }
        liveHandlers.forEach((hd) => { if (hd.kinds.some((k) => kinds.has(k))) { try { hd.fn(kinds); } catch (e) { console.error(e); } } });
      }, 250);
    }
  });
  const mod = await LOADERS[cur.tab]();
  await mod.default(body, W);

  async function openBell(anchor) {
    const list = h('div', { class: 'wk-bell-list' }, h('div', { class: 'spinner' }));
    const pop = popover(anchor, h('div', { class: 'wk-bell-pop' }, h('div', { class: 'row', style: { justifyContent: 'space-between', marginBottom: '8px' } }, h('b', null, t('Avisos')),
      h('button', { class: 'btn sm ghost', type: 'button', id: 'wk-readall', onclick: async () => { await api('/api/work/notifications/read', { method: 'POST', body: { all: true } }); pop.close(); } }, t('Marcar tudo como lido'))), list));
    try {
      const r = await api('/api/work/notifications');
      fill(list, ...(r.items.length ? r.items.slice(0, 25).map((n) => h('button', { class: 'wk-note' + (n.read ? '' : ' unread'), type: 'button', onclick: async () => {
        pop.close(); await api('/api/work/notifications/read', { method: 'POST', body: { ids: [n.id] } });
        const ref = n.ref || {};
        if (ref.type === 'request') W.go('requests', ref.id); else if (ref.type === 'file') W.go('files'); else if (ref.type === 'user') W.go('people', ref.id);
      } }, h('b', null, n.title), n.body ? h('span', { class: 'small muted' }, n.body) : null, h('span', { class: 'small dim' }, fmtAgo(n.ts)))) : [h('div', { class: 'dim small', style: { padding: '12px' } }, t('Nenhum aviso ainda.'))]));
    } catch (e) { fill(list, h('div', { class: 'errbox' }, e.message)); }
  }
}
