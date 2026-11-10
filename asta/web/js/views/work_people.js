// Work → Pessoas: perfis (nome de usuário, cargo, bio, função), enviar pedido, senhas (guardadas aqui, noutra máquina ou em todas) e os cargos/funções com permissões customizadas.
import { api, AUTH_MODE, avatarEl, chip, dialog, fmtAgo, h, icon, roleOf, t, toast } from '../work_ui.js';
import { confirmDialog, field, fill, select } from '../ui.js';
import { openComposer } from './work_compose.js';

const COLORS = ['#3e9bff', '#f5a524', '#30a46c', '#e5484d', '#a78bfa', '#06b6d4', '#ec4899', '#84cc16', '#8b8b94'];

export default async function render(box, W) {
  const grid = h('div', { class: 'wk-grid', id: 'wk-people' });
  const rolesBox = h('div', { id: 'wk-roles' });
  const search = h('input', { type: 'search', id: 'wk-people-q', placeholder: t('Buscar pessoas…') });
  let q = '';
  search.addEventListener('input', () => { q = search.value.trim().toLowerCase(); paint(); });
  box.replaceChildren(h('div', { class: 'row', style: { justifyContent: 'space-between', marginBottom: '12px', gap: '10px', flexWrap: 'wrap' } }, search,
    W.can('users.manage') ? h('button', { class: 'btn primary', type: 'button', id: 'wk-new-person', onclick: () => editPerson(null) }, icon('plus', 14), t('Nova pessoa')) : null), grid, rolesBox);

  function card(u) {
    const r = roleOf(W.dir, u), fns = (u.function_ids || []).map((id) => (W.dir.functions.find((f) => f.id === id) || {}).name).filter(Boolean);
    return h('button', { class: 'wk-pcard' + (u.disabled ? ' off' : ''), type: 'button', dataset: { user: u.username, id: u.id }, onclick: () => profile(u.id) },
      avatarEl(u, 48), h('div', { class: 'grow' }, h('b', null, u.display_name || u.username), h('div', { class: 'small dim' }, '@' + u.username), h('div', { class: 'row', style: { gap: '6px', flexWrap: 'wrap', marginTop: '6px' } },
        r.name ? h('span', { class: 'chip', style: { borderColor: r.color, color: r.color } }, r.name) : null, u.title ? h('span', { class: 'chip' }, u.title) : null, ...fns.map((f) => h('span', { class: 'chip solid' }, f)), u.disabled ? chip(t('Desativada'), 'err') : null),
        u.bio ? h('div', { class: 'small muted wk-bio' }, u.bio) : null),
      h('span', { class: 'small dim wk-pstat' }, u.online ? h('span', { class: 'wk-on' }, t('online')) : u.last_seen ? fmtAgo(u.last_seen) : '', u.busy ? h('span', null, t('{n} em andamento', { n: u.busy })) : null));
  }
  function paint() {
    const list = W.dir.users.filter((u) => !q || (u.display_name + ' ' + u.username + ' ' + (u.title || '') + ' ' + (u.bio || '')).toLowerCase().includes(q));
    fill(grid, ...list.map(card), !list.length ? h('div', { class: 'dim small' }, t('Ninguém encontrado.')) : null);
  }

  // ------------------------------------------------------------------ perfil
  async function profile(uid) {
    const u = W.dir.users.find((x) => x.id === uid);
    if (!u) return;
    history.replaceState(null, '', '#/work/people/' + uid);
    const mine = u.id === W.me.user.id, manage = W.can('users.manage');
    let acts = [];
    try { acts = (await api('/api/work/activities?user=' + uid + '&auto=0&limit=8')).activities; } catch (e) { /* sem permissão para ver as atividades de outros */ }
    const r = roleOf(W.dir, u);
    const d = dialog(t('Perfil'), h('div', { id: 'wk-profile' },
      h('div', { class: 'row', style: { gap: '14px', alignItems: 'center', marginBottom: '12px' } }, avatarEl(u, 64), h('div', null, h('h3', { style: { margin: 0 } }, u.display_name || u.username), h('div', { class: 'small dim' }, '@' + u.username + (u.email ? ' · ' + u.email : '')),
        h('div', { class: 'small', style: { marginTop: '4px' } }, u.online ? h('span', { class: 'wk-on' }, t('online agora')) : u.last_seen ? t('visto {t}', { t: fmtAgo(u.last_seen) }) : t('nunca entrou')))),
      h('dl', { class: 'wk-dl' }, h('dt', null, t('Cargo')), h('dd', null, r.name + (u.title ? ' · ' + u.title : '')),
        h('dt', null, t('Função')), h('dd', null, (u.function_ids || []).map((id) => (W.dir.functions.find((f) => f.id === id) || {}).name).filter(Boolean).join(', ') || '—'),
        h('dt', null, t('Bio')), h('dd', null, u.bio || '—'),
        (mine || manage) ? [h('dt', null, t('Senha')), h('dd', null, AUTH_MODE()[(u.auth || {}).mode || 'none'])] : null),
      acts.length ? h('div', null, h('h4', null, t('Atividades recentes')), h('ul', { class: 'small' }, acts.map((a) => h('li', null, a.title + ' — ' + t({ started: 'Começou', continuing: 'Continuando', paused: 'Pausada', finished: 'Finalizada', cancelled: 'Cancelada' }[a.state] || a.state))))) : null,
      h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap', marginTop: '14px' } },
        W.can('requests.send') && !mine && !u.disabled ? h('button', { class: 'btn primary', type: 'button', id: 'wk-send-request', onclick: async () => { d.close(); const r_ = await openComposer(W, { to: [u.id] }); if (r_) W.go('requests', r_.id); } }, icon('send', 14), t('Enviar pedido')) : null,
        mine || manage ? h('button', { class: 'btn', type: 'button', id: 'wk-edit-person', onclick: () => { d.close(); editPerson(u); } }, icon('edit', 14), t('Editar perfil')) : null,
        mine || manage ? h('button', { class: 'btn', type: 'button', id: 'wk-password', onclick: () => { d.close(); passwordDialog(u); } }, icon('lock', 14), t('Senha…')) : null,
        manage && !mine ? h('button', { class: 'btn', type: 'button', onclick: async () => { await api('/api/work/users/' + u.id, { method: 'PUT', body: { disabled: !u.disabled } }).catch((e) => toast(e.message, 'err')); d.close(); await W.reloadBase(); paint(); } }, u.disabled ? t('Reativar') : t('Desativar')) : null,
        manage && !mine ? h('button', { class: 'btn danger', type: 'button', onclick: async () => { if (await confirmDialog(t('Remover {n} da organização? As atividades e pedidos dela continuam registrados.', { n: u.display_name || u.username }))) { await api('/api/work/users/' + u.id, { method: 'DELETE' }).catch((e) => toast(e.message, 'err')); d.close(); await W.reloadBase(); paint(); } } }, icon('trash', 14), t('Remover')) : null,
        h('button', { class: 'btn ghost', type: 'button', onclick: () => d.close() }, t('Fechar')))));
    await d.done;
    history.replaceState(null, '', '#/work/people');
  }

  // ------------------------------------------------------------------ criar/editar pessoa
  function permSelect(cur, deny, onChange) {
    const sel = select([['', t('Herdar do cargo')], ['grant', t('Conceder')], ['deny', t('Negar')]], cur, onChange);
    return sel;
  }
  async function editPerson(u) {
    const cat = await api('/api/work/catalog');
    const manage = W.can('users.manage'), isNew = !u;
    const f = u ? JSON.parse(JSON.stringify(u)) : { username: '', display_name: '', role_id: 'worker', title: '', bio: '', email: '', function_ids: [], avatar_color: COLORS[W.dir.users.length % COLORS.length], grant: [], deny: [] };
    const inp = (k, id, ph, type = 'text') => { const el = h('input', { value: f[k] || '', id, placeholder: ph || '', type }); el.addEventListener('input', () => { f[k] = el.value; }); return el; };
    const bio = h('textarea', { rows: 3, id: 'wk-p-bio' }, f.bio || ''); bio.addEventListener('input', () => { f.bio = bio.value; });
    const assignable = W.dir.roles.filter((r) => W.me.perms.includes('*') || r.level < W.me.level);
    const roleSel = select(assignable.map((r) => [r.id, r.name]), f.role_id, (v) => { f.role_id = v; }, { id: 'wk-p-role' });
    const fnBox = h('div', { class: 'wk-checks' }, W.dir.functions.map((fn) => { const c = h('input', { type: 'checkbox', checked: (f.function_ids || []).includes(fn.id) }); c.addEventListener('change', () => { f.function_ids = c.checked ? [...f.function_ids, fn.id] : f.function_ids.filter((x) => x !== fn.id); }); return h('label', { class: 'check' }, c, h('span', null, fn.name)); }));
    const pw = h('input', { type: 'password', id: 'wk-p-pw', placeholder: t('Opcional'), autocomplete: 'new-password' });
    const mode = select([['synced', t('Em todas as máquinas da rede')], ['local', t('Só nesta máquina')]], 'synced', () => {}, { id: 'wk-p-mode' });
    const colors = h('div', { class: 'wk-colors' });
    const paintColors = () => fill(colors, ...COLORS.map((c) => h('button', { type: 'button', class: 'wk-sw' + (c === f.avatar_color ? ' on' : ''), style: { background: c }, 'aria-label': c, onclick: () => { f.avatar_color = c; paintColors(); } })));
    paintColors();
    const extra = manage ? h('details', null, h('summary', null, t('Permissões extras só desta pessoa')), h('div', { class: 'wk-permgrid' }, cat.perms.map((p) => h('div', { class: 'wk-permrow' }, h('span', { class: 'small' }, t(p.label)),
      permSelect((f.grant || []).includes(p.id) ? 'grant' : (f.deny || []).includes(p.id) ? 'deny' : '', false, (v) => { f.grant = (f.grant || []).filter((x) => x !== p.id); f.deny = (f.deny || []).filter((x) => x !== p.id); if (v === 'grant') f.grant.push(p.id); if (v === 'deny') f.deny.push(p.id); }))))) : null;
    const err = h('div', { class: 'errbox hidden', style: { whiteSpace: 'normal' } });
    const save = h('button', { class: 'btn primary', type: 'button', id: 'wk-p-save', onclick: async () => {
      err.classList.add('hidden');
      try {
        const body = { display_name: f.display_name, title: f.title, bio: f.bio, email: f.email, avatar_color: f.avatar_color };
        if (manage) Object.assign(body, { role_id: f.role_id, function_ids: f.function_ids, grant: f.grant, deny: f.deny });
        if (isNew) await api('/api/work/users', { method: 'POST', body: { ...body, username: f.username, password: pw.value, auth_mode: mode.value } });
        else await api('/api/work/users/' + u.id, { method: 'PUT', body });
        d.close(true); toast(isNew ? t('Pessoa criada.') : t('Perfil salvo.'), 'ok');
      } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); }
    } }, icon('check', 14), t('Salvar'));
    const d = dialog(isNew ? t('Nova pessoa') : t('Editar perfil'), h('div', { class: 'wk-form' },
      h('div', { class: 'grid2' }, field(t('Nome'), inp('display_name', 'wk-p-name', t('Ex.: João Lima'))), field(t('Nome de usuário'), isNew ? inp('username', 'wk-p-user', 'joao') : h('input', { value: '@' + f.username, disabled: true }))),
      h('div', { class: 'grid2' }, manage ? field(t('Cargo (define as permissões)'), roleSel) : null, field(t('Título do cargo'), inp('title', 'wk-p-title', t('Ex.: Designer pleno')))),
      manage && W.dir.functions.length ? field(t('Função'), fnBox) : null, field(t('Bio'), bio), h('div', { class: 'grid2' }, field(t('E-mail'), inp('email', 'wk-p-email', '', 'email')), field(t('Cor'), colors)),
      isNew ? h('div', { class: 'grid2' }, field(t('Senha inicial (opcional)'), pw), field(t('Onde guardar a senha'), mode)) : null, extra, err,
      h('div', { class: 'row', style: { justifyContent: 'flex-end', gap: '8px', marginTop: '14px' } }, h('button', { class: 'btn', type: 'button', onclick: () => d.close(null) }, t('Cancelar')), save)));
    if (await d.done) { await W.reloadBase(); paint(); }
  }

  async function passwordDialog(u) {
    const mine = u.id === W.me.user.id, has = !!(u.auth || {}).set;
    let machines = [];
    try { machines = (await api('/api/work/network')).machines.filter((m) => !m.revoked); } catch (e) { /* sem rede */ }
    const f = { mode: (u.auth || {}).mode && u.auth.mode !== 'none' ? u.auth.mode : 'synced', holder: (u.auth || {}).holder || (machines[0] || {}).id || '' };
    const cur = h('input', { type: 'password', id: 'wk-pw-cur', autocomplete: 'current-password' }), nw = h('input', { type: 'password', id: 'wk-pw-new', autocomplete: 'new-password' });
    const holder = select(machines.map((m) => [m.id, m.name + (m.self ? ' ' + t('(esta)') : '')]), f.holder, (v) => { f.holder = v; }, { id: 'wk-pw-holder' });
    const modeSel = select(Object.entries(AUTH_MODE()).filter(([k]) => k !== 'none'), f.mode, (v) => { f.mode = v; holderField.classList.toggle('hidden', v !== 'machine'); }, { id: 'wk-pw-mode' });
    const holderField = field(t('Máquina que guarda a senha'), holder, t('Quem entrar por outra máquina terá a senha conferida por essa. Se ela estiver desligada, não dá para entrar.')); holderField.classList.toggle('hidden', f.mode !== 'machine');
    const err = h('div', { class: 'errbox hidden', style: { whiteSpace: 'normal' } });
    const call = async (body) => { err.classList.add('hidden'); try { await api(`/api/work/users/${u.id}/password`, { method: 'POST', body }); toast(t('Senha atualizada.'), 'ok'); d.close(true); } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); } };
    const d = dialog(t('Senha de {n}', { n: u.display_name || u.username }), h('div', { class: 'wk-form', id: 'wk-pwd' },
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('A senha é opcional. Ela só guarda um resumo (hash) — nunca o texto — e você escolhe onde: nesta máquina, noutra máquina da rede, ou em todas.')),
      mine && has ? field(t('Senha atual'), cur) : null, field(t('Nova senha'), nw, t('Pelo menos 6 caracteres.')), field(t('Onde guardar'), modeSel), holderField, err,
      h('div', { class: 'row', style: { justifyContent: 'space-between', marginTop: '14px' } }, has ? h('button', { class: 'btn danger', type: 'button', id: 'wk-pw-remove', onclick: () => call({ password: '', mode: 'none', current: cur.value }) }, t('Remover a senha')) : h('span'),
        h('div', { class: 'row' }, h('button', { class: 'btn', type: 'button', onclick: () => d.close(null) }, t('Cancelar')), h('button', { class: 'btn primary', type: 'button', id: 'wk-pw-save', onclick: () => call({ password: nw.value, mode: f.mode, holder: f.holder, current: cur.value }) }, t('Salvar senha'))))));
    if (await d.done) { await W.reloadBase(); paint(); }
  }

  // ------------------------------------------------------------------ cargos e funções
  async function paintRoles() {
    if (!W.can('roles.manage')) return fill(rolesBox);
    fill(rolesBox, h('div', { class: 'card', id: 'wk-roles-card' }, h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('h3', { style: { margin: 0 } }, t('Cargos e permissões')),
      h('div', { class: 'row' }, h('button', { class: 'btn sm', type: 'button', id: 'wk-new-role', onclick: () => editRole(null) }, icon('plus', 13), t('Novo cargo')), h('button', { class: 'btn sm', type: 'button', id: 'wk-new-fn', onclick: () => editFn(null) }, icon('plus', 13), t('Nova função')))),
      h('p', { class: 'muted small' }, t('O cargo (administrador, gerente, trabalhador… ou os seus) define o que a pessoa pode fazer. A função (Financeiro, Design…) acrescenta ou tira permissões de quem a exerce. Dá para ajustar uma pessoa só, no perfil dela.')),
      h('div', { class: 'wk-grid' }, W.dir.roles.map((r) => h('button', { class: 'wk-pcard', type: 'button', dataset: { role: r.id }, onclick: () => editRole(r) }, h('span', { class: 'wk-dot', style: { background: r.color } }), h('div', { class: 'grow' }, h('b', null, r.name), h('div', { class: 'small dim' }, t('Nível {n}', { n: r.level }) + ' · ' + (r.perms.includes('*') ? t('todas as permissões') : t('{n} permissões', { n: r.perms.length }))), h('div', { class: 'small muted' }, r.description || ''))))),
      W.dir.functions.length ? h('div', null, h('h4', null, t('Funções')), h('div', { class: 'wk-grid' }, W.dir.functions.map((fn) => h('button', { class: 'wk-pcard', type: 'button', dataset: { fn: fn.id }, onclick: () => editFn(fn) }, h('span', { class: 'wk-dot', style: { background: fn.color } }), h('div', { class: 'grow' }, h('b', null, fn.name), h('div', { class: 'small dim' }, t('+{a} / −{b} permissões', { a: fn.grant.length, b: fn.deny.length }))))))) : null));
  }
  async function editRole(r) {
    const cat = await api('/api/work/catalog');
    const isAdmin = r && r.id === 'admin';
    const f = r ? JSON.parse(JSON.stringify(r)) : { name: '', description: '', level: 20, color: '#8b8b94', perms: [] };
    const name = h('input', { value: f.name, id: 'wk-r-name', disabled: false }); name.addEventListener('input', () => { f.name = name.value; });
    const desc = h('input', { value: f.description || '', id: 'wk-r-desc' }); desc.addEventListener('input', () => { f.description = desc.value; });
    const lvl = h('input', { type: 'number', min: 0, max: isAdmin ? 100 : 99, value: f.level, id: 'wk-r-level', disabled: isAdmin }); lvl.addEventListener('input', () => { f.level = parseInt(lvl.value, 10) || 0; });
    const groups = {};
    cat.perms.forEach((p) => { (groups[p.group] = groups[p.group] || []).push(p); });
    const matrix = h('div', null, Object.entries(groups).map(([g, ps]) => h('div', { class: 'wk-permgroup' }, h('b', { class: 'small' }, t(g)), ps.map((p) => {
      const c = h('input', { type: 'checkbox', checked: isAdmin || f.perms.includes(p.id), disabled: isAdmin || !(W.me.perms.includes('*') || W.me.perms.includes(p.id)), dataset: { perm: p.id } });
      c.addEventListener('change', () => { f.perms = c.checked ? [...f.perms, p.id] : f.perms.filter((x) => x !== p.id); });
      return h('label', { class: 'check' }, c, h('span', null, t(p.label)));
    }))));
    const err = h('div', { class: 'errbox hidden', style: { whiteSpace: 'normal' } });
    const d = dialog(r ? t('Cargo: {n}', { n: r.name }) : t('Novo cargo'), h('div', { class: 'wk-form', id: 'wk-role-form' }, h('div', { class: 'grid2' }, field(t('Nome do cargo'), name), field(t('Nível (quanto maior, mais alto na hierarquia)'), lvl)), field(t('Descrição'), desc),
      h('h4', null, t('Permissões')), isAdmin ? h('p', { class: 'small muted' }, t('O Administrador sempre tem todas as permissões.')) : null, matrix, err,
      h('div', { class: 'row', style: { justifyContent: 'space-between', marginTop: '14px' } }, r && !r.builtin ? h('button', { class: 'btn danger', type: 'button', id: 'wk-r-del', onclick: async () => { try { await api('/api/work/roles/' + r.id, { method: 'DELETE' }); d.close(true); } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); } } }, t('Apagar cargo')) : h('span'),
        h('div', { class: 'row' }, h('button', { class: 'btn', type: 'button', onclick: () => d.close(null) }, t('Cancelar')), h('button', { class: 'btn primary', type: 'button', id: 'wk-r-save', onclick: async () => {
          try { await api(r ? '/api/work/roles/' + r.id : '/api/work/roles', { method: r ? 'PUT' : 'POST', body: { name: f.name, description: f.description, level: f.level, perms: f.perms, color: f.color } }); d.close(true); } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); }
        } }, t('Salvar'))))), true);
    if (await d.done) { await W.reloadBase(); paint(); paintRoles(); }
  }
  async function editFn(fn) {
    const cat = await api('/api/work/catalog');
    const f = fn ? JSON.parse(JSON.stringify(fn)) : { name: '', description: '', grant: [], deny: [], color: '#a78bfa' };
    const name = h('input', { value: f.name, id: 'wk-fn-name' }); name.addEventListener('input', () => { f.name = name.value; });
    const rows = cat.perms.map((p) => h('div', { class: 'wk-permrow' }, h('span', { class: 'small' }, t(p.label)), select([['', t('Herdar do cargo')], ['grant', t('Conceder')], ['deny', t('Negar')]], f.grant.includes(p.id) ? 'grant' : f.deny.includes(p.id) ? 'deny' : '', (v) => { f.grant = f.grant.filter((x) => x !== p.id); f.deny = f.deny.filter((x) => x !== p.id); if (v === 'grant') f.grant.push(p.id); if (v === 'deny') f.deny.push(p.id); })));
    const err = h('div', { class: 'errbox hidden' });
    const d = dialog(fn ? t('Função: {n}', { n: fn.name }) : t('Nova função'), h('div', { class: 'wk-form', id: 'wk-fn-form' }, field(t('Nome da função'), name), h('div', { class: 'wk-permgrid' }, rows), err,
      h('div', { class: 'row', style: { justifyContent: 'space-between', marginTop: '14px' } }, fn ? h('button', { class: 'btn danger', type: 'button', onclick: async () => { await api('/api/work/functions/' + fn.id, { method: 'DELETE' }).catch((e) => toast(e.message, 'err')); d.close(true); } }, t('Apagar função')) : h('span'),
        h('div', { class: 'row' }, h('button', { class: 'btn', type: 'button', onclick: () => d.close(null) }, t('Cancelar')), h('button', { class: 'btn primary', type: 'button', id: 'wk-fn-save', onclick: async () => {
          try { await api(fn ? '/api/work/functions/' + fn.id : '/api/work/functions', { method: fn ? 'PUT' : 'POST', body: { name: f.name, grant: f.grant, deny: f.deny, color: f.color } }); d.close(true); } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); }
        } }, t('Salvar'))))), true);
    if (await d.done) { await W.reloadBase(); paint(); paintRoles(); }
  }

  paint(); paintRoles();
  W.live(['users', 'roles', 'functions'], () => { paint(); paintRoles(); });
  if (W.arg && W.dir.users.some((u) => u.id === W.arg)) profile(W.arg);
}
