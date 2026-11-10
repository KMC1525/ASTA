// Work → Rede: as máquinas e as redes (Tailscale, rede local ou pasta de nuvem), os convites, o estado da sincronização e as máquinas de backup que cada pessoa escolhe.
import { api, askDesktop, fmtAgo, fmtSize, fmtWhen, h, icon, t, toast } from '../work_ui.js';
import { confirmDialog, field, fill, select } from '../ui.js';

export default async function render(box, W) {
  const root = h('div', { class: 'wk-net', id: 'wk-net' });
  box.replaceChildren(root);
  let N = null, B = null;
  const can = () => !!(N && N.can_manage);

  async function load() {
    try { N = await api('/api/work/network'); } catch (e) { return fill(root, h('div', { class: 'errbox' }, e.message)); }
    try { B = await api('/api/work/backup'); } catch (e) { B = null; }
    paint();
  }

  // ------------------------------------------------------------------ esta máquina e a escuta
  function thisMachine() {
    const ts = N.tailscale, me = N.machine, L = N.listen;
    const name = h('input', { value: me.name, id: 'wk-m-name' });
    const mode = select([['off', t('Desligada (padrão) — só esta máquina enxerga os dados')], ['auto', t('Tailscale — escuta só no IP da tailnet')], ['lan', t('Rede local — escuta em todas as interfaces')]], ['off', 'auto', 'lan'].includes(L.listen) ? L.listen : 'off', () => {}, { id: 'wk-listen', disabled: !can() });
    const port = h('input', { type: 'number', value: L.port, min: 1024, max: 65535, id: 'wk-port', disabled: !can() });
    const auto = h('input', { type: 'checkbox', checked: N.auto_sync, id: 'wk-autosync', disabled: !can() });
    const every = h('input', { type: 'number', value: N.interval, min: 5, max: 600, id: 'wk-interval', disabled: !can() });
    const tsInfo = !ts.installed ? t('Tailscale: não instalado (opcional — o Work também sincroniza pela rede local ou por uma pasta de nuvem).')
      : ts.running ? t('Tailscale: conectado · IP {ip} · {n} máquina(s) na tailnet', { ip: ts.ip, n: ts.peers.length }) : t('Tailscale: instalado, mas desconectado.');
    return h('div', { class: 'card', id: 'wk-this' }, h('h3', null, t('Esta máquina')),
      h('div', { class: 'row', style: { gap: '8px' } }, name, h('button', { class: 'btn sm', type: 'button', id: 'wk-m-rename', onclick: async () => { try { await api('/api/work/machines/' + me.id, { method: 'PUT', body: { name: name.value } }); toast(t('Nome salvo.'), 'ok'); load(); } catch (e) { toast(e.message, 'err'); } } }, t('Renomear'))),
      h('p', { class: 'small', style: { margin: '10px 0 2px' } }, icon('globe', 13), ' ', tsInfo), ts.peers && ts.peers.length ? h('p', { class: 'small dim', style: { margin: 0 } }, ts.peers.slice(0, 8).map((p) => `${p.name} (${p.ips[0] || '?'})${p.online ? '' : ' ✕'}`).join(' · ')) : null,
      h('div', { class: 'grid2', style: { marginTop: '12px' } }, field(t('Sincronizar com outras máquinas'), mode), field(t('Porta'), port)),
      h('div', { class: 'row', style: { gap: '14px', flexWrap: 'wrap', margin: '6px 0' } }, h('label', { class: 'check' }, auto, h('span', null, t('Sincronizar sozinho a cada'))), every, h('span', { class: 'small' }, t('segundos'))),
      h('p', { class: 'small', id: 'wk-listen-state', style: { margin: '6px 0' } }, N.listening ? h('span', { class: 'wk-on' }, t('Escutando em {a}', { a: L.addrs.join(', ') })) : t('Não está escutando. Outras máquinas só sincronizam se você ligar isto (ou se esta máquina procurar as delas).')),
      can() ? h('button', { class: 'btn primary', type: 'button', id: 'wk-apply-net', onclick: async () => {
        try { const r = await api('/api/work/network', { method: 'PUT', body: { peer: { listen: mode.value, port: parseInt(port.value, 10) || 8790 }, auto_sync: auto.checked, interval: parseInt(every.value, 10) || 15 } }); if (r.error) toast(r.error, 'err'); else toast(t('Rede atualizada.'), 'ok'); load(); } catch (e) { toast(e.message, 'err'); }
      } }, icon('check', 14), t('Aplicar')) : null,
      h('p', { class: 'dim small', style: { marginBottom: 0 } }, t('A WebUI continua só neste computador. O Work abre uma porta separada que só responde ao protocolo de sincronização, com mensagens assinadas e cifradas pela chave da rede.')));
  }

  // ------------------------------------------------------------------ convite e entrar
  function invite() {
    const out = h('div', { id: 'wk-invite-out' });
    const code = h('textarea', { rows: 3, id: 'wk-join-code2', placeholder: 'AW1.…', spellcheck: 'false' });
    return h('div', { class: 'card' }, h('h3', null, t('Convidar uma máquina')),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Gera um código de uso único (vale 24 horas) que a outra máquina cola em «Entrar numa rede». Ele leva a chave da rede: trate como senha.')),
      can() ? h('button', { class: 'btn', type: 'button', id: 'wk-invite', onclick: async () => {
        try { const r = await api('/api/work/network/invite', { method: 'POST', body: {} }); fill(out, h('textarea', { readonly: true, rows: 3, id: 'wk-invite-code', onclick: (e) => e.target.select() }, r.code), h('div', { class: 'row', style: { gap: '8px', marginTop: '6px' } }, h('button', { class: 'btn sm', type: 'button', onclick: () => { navigator.clipboard && navigator.clipboard.writeText(r.code); toast(t('Código copiado.'), 'ok'); } }, icon('copy', 13), t('Copiar')), h('span', { class: 'small dim' }, t('Vale até {d}', { d: fmtWhen(r.expires) }))));
        } catch (e) { fill(out, h('div', { class: 'errbox', style: { whiteSpace: 'normal' } }, e.message)); }
      } }, icon('plus', 14), t('Gerar código de convite')) : h('p', { class: 'dim small' }, t('Só quem gerencia a rede convida máquinas.')), out,
      h('details', { style: { marginTop: '14px' } }, h('summary', null, t('Entrar noutra rede com um código')), field(t('Código de convite'), code),
        h('button', { class: 'btn', type: 'button', id: 'wk-join2', onclick: async () => { try { await api('/api/work/join', { method: 'POST', body: { code: code.value.trim(), machine_name: N.machine.name } }); toast(t('Esta máquina entrou na rede. Os dados estão sincronizando.'), 'ok'); location.reload(); } catch (e) { toast(e.message, 'err'); } } }, t('Entrar'))));
  }

  // ------------------------------------------------------------------ máquinas
  function machines() {
    const row = (m) => h('tr', { dataset: { id: m.id, name: m.name } }, h('td', null, h('span', { class: 'wk-dot ' + (m.online ? 'on' : ''), title: m.online ? t('online') : t('sem contato recente') }), ' ', h('b', null, m.name), m.self ? h('span', { class: 'chip', style: { marginLeft: '6px' } }, t('esta')) : null, m.revoked ? h('span', { class: 'chip', style: { marginLeft: '6px', color: 'var(--err)' } }, t('revogada')) : null,
      h('div', { class: 'small dim' }, (m.os || '') + (m.addrs && m.addrs.length ? ' · ' + m.addrs.join(', ') : ''))),
      h('td', { class: 'small' }, (m.users || []).join(', ') || '—'), h('td', { class: 'small' }, m.self ? t('agora') : m.last_contact ? fmtAgo(m.last_contact) : '—'),
      h('td', null, (() => { const c = h('input', { type: 'checkbox', checked: !!m.backup, disabled: !can() || m.revoked, dataset: { flag: 'backup' } }); c.addEventListener('change', () => patch(m.id, { backup: c.checked })); return h('label', { class: 'check' }, c, h('span', null, t('Backup'))); })()),
      h('td', null, select([['needed', t('Só o necessário')], ['all', t('Guarda tudo')]], m.hold, (v) => patch(m.id, { hold: v }), { disabled: !can() || m.revoked, 'data-flag': 'hold' })),
      h('td', null, can() && !m.self ? h('button', { class: 'btn sm ' + (m.revoked ? '' : 'danger'), type: 'button', dataset: { act: 'revoke' }, onclick: async () => { if (m.revoked || await confirmDialog(t('Revogar «{n}»? Ela deixa de sincronizar com esta rede.', { n: m.name }), true, t('Revogar'))) patch(m.id, { revoked: !m.revoked }); } }, m.revoked ? t('Reativar') : t('Revogar')) : null));
    return h('div', { class: 'card' }, h('h3', null, t('Máquinas da rede')), h('div', { class: 'wk-table-card' }, h('table', { class: 'wk-table', id: 'wk-machines' }, h('thead', null, h('tr', null, ['Máquina', 'Quem usa', 'Último contato', 'Backup', 'Arquivos', ''].map((c) => h('th', null, t(c))))), h('tbody', null, N.machines.map(row)))),
      h('p', { class: 'dim small', style: { marginBottom: 0 } }, t('«Só o necessário» guarda os arquivos de quem usa a máquina, dos setores que essa pessoa enxerga e dos pedidos dela; o resto é buscado sob demanda. «Guarda tudo» (um servidor ou um backup) recebe todos os arquivos. Revogar não troca a chave da rede: para excluir de vez uma máquina que já a conhecia, crie a rede de novo.')));
  }
  async function patch(id, body) { try { await api('/api/work/machines/' + id, { method: 'PUT', body }); await load(); } catch (e) { toast(e.message, 'err'); load(); } }

  // ------------------------------------------------------------------ pontes e estado da sincronização
  function links() {
    const kind = select([['peer', t('Endereço de outra máquina (ip:porta)')], ['folder', t('Pasta de nuvem (Drive, Dropbox, NAS…)')]], 'peer', () => {}, { id: 'wk-link-kind2' });
    const target = h('input', { id: 'wk-link-target', placeholder: '100.64.0.7:8790  ·  ~/Dropbox/asta-work' });
    const r = N.sync || {};
    return h('div', { class: 'card', id: 'wk-links' }, h('h3', null, t('Sincronização')),
      h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap', alignItems: 'center' } }, can() ? h('button', { class: 'btn primary', type: 'button', id: 'wk-sync-now', onclick: async (e) => { e.currentTarget.disabled = true; try { const s = await api('/api/work/network/sync', { method: 'POST', body: {} }); toast((s.results || []).length ? t('Sincronização concluída.') : t('Nenhuma máquina para sincronizar ainda.'), (s.results || []).some((x) => x.ok) ? 'ok' : ''); } catch (er) { toast(er.message, 'err'); } load(); } }, icon('refresh', 14), t('Sincronizar agora')) : null,
        h('span', { class: 'small muted', id: 'wk-last-sync' }, N.last_sync ? t('Última sincronização {t}', { t: fmtAgo(N.last_sync) }) : t('Ainda não sincronizou.'))),
      (r.results || []).length ? h('ul', { class: 'small', id: 'wk-sync-results' }, r.results.map((x) => h('li', null, h('b', null, x.target), x.ok ? ` — ✓ ${x.docs_in} ↓ ${x.docs_out} ↑ · ${t('arquivos')}: ${x.blobs_in} ↓ ${x.blobs_out} ↑` : ' — ✕ ' + x.error))) : null,
      (N.links || []).length ? h('ul', { class: 'small' }, N.links.map((l) => h('li', null, (l.kind === 'folder' ? t('Pasta') : t('Endereço')) + ': ', h('code', null, l.addr || l.path), ' ', can() ? h('a', { href: '#', onclick: async (e) => { e.preventDefault(); await api('/api/work/network/links?target=' + encodeURIComponent(l.addr || l.path), { method: 'DELETE' }); load(); } }, t('remover')) : null))) : null,
      can() ? h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap', marginTop: '8px' } }, kind, target, h('button', { class: 'btn', type: 'button', id: 'wk-link-add2', onclick: async () => { try { await api('/api/work/network/links', { method: 'POST', body: { kind: kind.value, target: target.value } }); target.value = ''; load(); } catch (e) { toast(e.message, 'err'); } } }, icon('plus', 14), t('Adicionar'))) : null,
      h('p', { class: 'dim small', style: { marginBottom: 0 } }, t('A pasta de nuvem guarda tudo cifrado com a chave da rede; quem sincroniza a pasta (Drive, Dropbox…) não consegue ler. Os dados nunca passam por um servidor do ASTA.')));
  }

  // ------------------------------------------------------------------ backups
  function backups() {
    if (!B) return null;
    const result = h('div', { id: 'wk-bk-result', class: 'small' });
    const userRow = (u) => {
      const chosen = new Set(u.backup_machines);
      return h('tr', { dataset: { id: u.id } }, h('td', null, h('b', null, u.name)), h('td', { class: 'small' }, `${u.files} · ${fmtSize(u.bytes)}`),
        h('td', null, B.targets.length ? B.targets.map((m) => { const c = h('input', { type: 'checkbox', checked: chosen.has(m.id), dataset: { machine: m.id } }); c.addEventListener('change', async () => { c.checked ? chosen.add(m.id) : chosen.delete(m.id); try { await api('/api/work/users/' + u.id, { method: 'PUT', body: { backup_machines: [...chosen] } }); toast(t('Backup atualizado.'), 'ok'); } catch (e) { toast(e.message, 'err'); load(); } }); return h('label', { class: 'check' }, c, h('span', null, m.name)); }) : h('span', { class: 'dim small' }, t('Nenhuma máquina de backup ainda.'))));
    };
    return h('div', { class: 'card', id: 'wk-backups' }, h('h3', null, t('Backups')),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Marque na tabela de máquinas quais servem de backup. Cada pessoa escolhe, aqui, em quais delas quer guardar os próprios arquivos — uma ou mais. A máquina de backup também guarda cópias diárias dos documentos da rede.')),
      B.targets.length ? h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap', marginBottom: '8px' } }, B.targets.map((m) => h('div', { class: 'row', style: { gap: '6px' } }, h('span', { class: 'wk-dot ' + (m.online ? 'on' : '') }), h('b', { class: 'small' }, m.name),
        can() ? h('button', { class: 'btn sm', type: 'button', dataset: { verify: m.id }, onclick: async () => { try { const v = await api('/api/work/backup/verify', { method: 'POST', body: { machine: m.id } }); fill(result, v.missing.length ? t('{p} de {e} arquivos presentes em {n}. Faltam: {f}', { p: v.present, e: v.expected, n: m.name, f: v.missing.slice(0, 5).map((x) => x.name).join(', ') }) : t('Tudo certo em {n}: {p} de {e} arquivos presentes.', { n: m.name, p: v.present, e: v.expected })); } catch (e) { fill(result, h('span', { class: 'err' }, e.message)); } } }, t('Verificar')) : null,
        can() && !m.self ? h('button', { class: 'btn sm', type: 'button', dataset: { restore: m.id }, onclick: async () => { if (await confirmDialog(t('Trazer de «{n}» os arquivos que faltam aqui?', { n: m.name }), false, t('Restaurar'))) { try { const r = await api('/api/work/backup/restore', { method: 'POST', body: { machine: m.id } }); toast(t('{n} arquivo(s) restaurado(s).', { n: r.restored }), 'ok'); load(); } catch (e) { toast(e.message, 'err'); } } } }, t('Restaurar daqui')) : null))) : null, result,
      B.users.length ? h('div', { class: 'wk-table-card' }, h('table', { class: 'wk-table', id: 'wk-bk-users' }, h('thead', null, h('tr', null, [t('Pessoa'), t('Arquivos'), t('Guardar também em')].map((c) => h('th', null, c)))), h('tbody', null, B.users.map(userRow)))) : null,
      B.this_is_backup ? h('div', { class: 'small', style: { marginTop: '10px' } }, h('b', null, t('Cópias dos documentos nesta máquina')), h('ul', null, B.snapshots.slice(0, 5).map((s) => h('li', null, s.name + ' · ' + fmtSize(s.size)))), W.can('backup.manage') ? h('button', { class: 'btn sm', type: 'button', id: 'wk-snap', onclick: async () => { try { await api('/api/work/backup/snapshot', { method: 'POST', body: {} }); toast(t('Cópia criada.'), 'ok'); load(); } catch (e) { toast(e.message, 'err'); } } }, t('Criar cópia agora')) : null) : null);
  }

  function data() {
    let desk = false; try { desk = localStorage.getItem('asta.work.desktop') === '1'; } catch (e) { /* ok */ }
    const c = h('input', { type: 'checkbox', checked: desk, id: 'wk-desktop-notes' });
    c.addEventListener('change', async () => { if (c.checked) { if (!(await askDesktop())) c.checked = false; } else { try { localStorage.setItem('asta.work.desktop', '0'); } catch (e) { /* ok */ } } });
    return h('div', { class: 'card' }, h('h3', null, t('Seus dados')),
      h('label', { class: 'check' }, c, h('span', null, t('Avisar também pelas notificações do sistema (quando esta aba estiver em segundo plano)'))),
      W.can('org.manage') ? h('div', { class: 'row', style: { gap: '8px', marginTop: '10px', flexWrap: 'wrap' } }, h('a', { class: 'btn sm', href: '/api/work/export', id: 'wk-export' }, icon('download', 13), t('Exportar documentos (ZIP)')), h('a', { class: 'btn sm', href: '/api/work/export?files=1' }, icon('download', 13), t('Exportar com os arquivos'))) : null,
      h('p', { class: 'dim small', style: { marginBottom: 0 } }, t('Tudo fica em arquivos comuns na pasta do ASTA (work/). A entrada do Work protege o acesso pelo aplicativo e pela rede; não cifra os arquivos no disco desta máquina — para isso use a cifra de disco do sistema.')));
  }

  function paint() {
    fill(root, thisMachine(), h('div', { class: 'wk-two' }, h('div', { class: 'wk-col' }, invite(), links()), h('div', { class: 'wk-col' }, backups(), data())), machines());
  }

  await load();
  W.live(['machines', 'users'], load);
}
