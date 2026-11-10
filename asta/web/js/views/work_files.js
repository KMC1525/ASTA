// Work → Arquivos: os setores (pastas) da empresa e os arquivos deles, de qualquer formato. Enviar é sincronizar: cada arquivo vai sozinho para as máquinas que precisam dele.
import { api, dialog, fmtSize, fmtWhen, h, icon, t, toast, uploadFile, userName } from '../work_ui.js';
import { confirmDialog, field, fill, popover, select } from '../ui.js';

const INLINE = /\.(png|jpe?g|gif|webp|mp3|wav|ogg|m4a|mp4|webm|pdf|txt)$/i;
const ICON = (name) => (/\.(png|jpe?g|gif|webp|bmp|svg|psd)$/i.test(name) ? 'image' : /\.(mp4|mov|mkv|webm|avi)$/i.test(name) ? 'video' : /\.(mp3|wav|ogg|m4a|flac)$/i.test(name) ? 'audio' : /\.(zip|rar|7z|tar|gz)$/i.test(name) ? 'archive'
  : /\.(xlsx?|csv|ods)$/i.test(name) ? 'sheet' : /\.(pptx?|odp|key)$/i.test(name) ? 'slides' : /\.(docx?|pdf|odt|rtf|txt|md)$/i.test(name) ? 'doc' : 'file');

export default async function render(box, W) {
  const S = { folder: W.arg || '', files: [] };
  const tree = h('aside', { class: 'cu-list wk-tree', id: 'wk-tree' });
  const main = h('section', { class: 'cu-main', id: 'wk-fmain' });
  box.replaceChildren(h('div', { class: 'cu-split' }, tree, main));
  const folderName = (id) => (id ? (W.dir.folders.find((f) => f.id === id) || {}).name || '?' : t('Meus arquivos'));

  function paintTree() {
    const kids = (p) => W.dir.folders.filter((f) => (f.parent || '') === p);
    const item = (f, depth) => [h('button', { class: 'cu-item' + (S.folder === f.id ? ' on' : ''), type: 'button', dataset: { folder: f.id }, style: { paddingLeft: 12 + depth * 16 + 'px' }, onclick: () => open(f.id) },
      h('span', { class: 'wk-dot', style: { background: f.color } }), h('span', { class: 'grow' }, h('span', { class: 'cu-t' }, f.name)), (f.access || {}).mode === 'restricted' ? icon('lock', 12) : null), ...kids(f.id).flatMap((k) => item(k, depth + 1))];
    fill(tree, W.can('folders.manage') ? h('button', { class: 'btn cu-new', type: 'button', id: 'wk-new-folder', onclick: newFolder }, icon('plus', 15), t('Novo setor')) : null,
      h('button', { class: 'cu-item' + (!S.folder ? ' on' : ''), type: 'button', dataset: { folder: '' }, onclick: () => open('') }, icon('user', 14), h('span', { class: 'grow' }, h('span', { class: 'cu-t' }, t('Meus arquivos')), h('span', { class: 'cu-s' }, t('Só você enxerga')))),
      h('div', { class: 'cu-grp' }, t('Setores')), ...kids('').filter((f) => !f.parent).flatMap((f) => item(f, 0)), !W.dir.folders.length ? h('div', { class: 'dim small cu-none' }, t('Nenhum setor ainda. Crie um aqui ou desenhe no Quadro.')) : null);
  }
  async function newFolder() {
    const name = h('input', { id: 'wk-nf-name', placeholder: t('Ex.: Financeiro') });
    const parent = select([['', t('(nenhuma — setor principal)')], ...W.dir.folders.map((f) => [f.id, f.name])], '', () => {}, { id: 'wk-nf-parent' });
    const d = dialog(t('Novo setor'), h('div', { class: 'wk-form' }, field(t('Nome'), name), field(t('Dentro de'), parent), h('p', { class: 'dim small' }, t('Depois dá para escolher quem enxerga (no Quadro, clicando na caixa do setor).')),
      h('div', { class: 'row', style: { justifyContent: 'flex-end', gap: '8px' } }, h('button', { class: 'btn', type: 'button', onclick: () => d.close(null) }, t('Cancelar')), h('button', { class: 'btn primary', type: 'button', id: 'wk-nf-ok', onclick: async () => {
        try { const f = await api('/api/work/folders', { method: 'POST', body: { name: name.value, parent: parent.value, x: 40 + W.dir.folders.length * 30, y: 40 + W.dir.folders.length * 30 } }); d.close(f); } catch (e) { toast(e.message, 'err'); }
      } }, t('Criar')))));
    const f = await d.done;
    if (f) { await W.reloadBase(); open(f.id); }
  }
  async function open(id) { S.folder = id; history.replaceState(null, '', '#/work/files' + (id ? '/' + id : '')); await load(); }
  async function load() {
    try { S.files = (await api('/api/work/files?folder=' + encodeURIComponent(S.folder))).files; } catch (e) { S.files = []; toast(e.message, 'err'); }
    paintTree(); paintMain();
  }

  function paintMain() {
    const canUp = W.can('files.upload');
    const picker = h('input', { type: 'file', multiple: true, class: 'hidden', id: 'wk-upload' });
    const status = h('div', { class: 'small dim', id: 'wk-upload-status' });
    async function send(list) {
      let n = 0;
      for (const f of [...list]) {
        status.textContent = t('Enviando {n}… ', { n: f.name });
        try { await uploadFile(f, { folder: S.folder }, (p) => { status.textContent = t('Enviando {n}… ', { n: f.name }) + Math.round(p * 100) + '%'; }); n++; } catch (e) { toast(f.name + ': ' + e.message, 'err'); }
      }
      status.textContent = n ? t('{n} arquivo(s) enviado(s). Eles já estão sincronizando com as outras máquinas.', { n }) : '';
      await load();
    }
    picker.addEventListener('change', () => { send(picker.files); picker.value = ''; });
    const zone = h('div', { class: 'wk-drop', id: 'wk-drop' }, icon('upload', 20), h('span', null, t('Solte arquivos aqui — qualquer formato')));
    ['dragenter', 'dragover'].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add('on'); }));
    ['dragleave', 'drop'].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove('on'); }));
    zone.addEventListener('drop', (e) => { if (canUp && e.dataTransfer.files.length) send(e.dataTransfer.files); });
    const fobj = W.dir.folders.find((f) => f.id === S.folder);
    fill(main, h('div', { class: 'cu-head' }, h('h2', null, folderName(S.folder)), h('div', { class: 'row cu-meta' }, fobj ? h('span', { class: 'small muted' }, fobj.description || ((fobj.access || {}).mode === 'restricted' ? t('Acesso restrito') : t('Todos com permissão de ver arquivos'))) : h('span', { class: 'small muted' }, t('Arquivos pessoais: só você enxerga. Mova para um setor para compartilhar.')))),
      canUp ? h('div', { class: 'row', style: { gap: '8px', marginBottom: '10px', flexWrap: 'wrap' } }, h('button', { class: 'btn primary', type: 'button', id: 'wk-upload-btn', onclick: () => picker.click() }, icon('upload', 14), t('Enviar arquivos')), picker,
        h('button', { class: 'btn', type: 'button', id: 'wk-import-lib', onclick: importProject }, icon('library', 14), t('Da Biblioteca do ASTA')), zone) : null, status,
      S.files.length ? h('div', { class: 'card wk-table-card' }, h('table', { class: 'wk-table', id: 'wk-files' }, h('thead', null, h('tr', null, ['Nome', 'Tamanho', 'Versões', 'Dono', 'Atualizado', ''].map((c) => h('th', null, t(c))))),
        h('tbody', null, S.files.map(row)))) : h('div', { class: 'dim small', style: { padding: '24px 4px' }, id: 'wk-nofiles' }, t('Nenhum arquivo aqui ainda.')));
  }
  function row(f) {
    const dl = (v) => `/api/work/files/${f.id}/download${v ? '?v=' + v : ''}`;
    return h('tr', { dataset: { name: f.name, id: f.id } }, h('td', null, h('a', { class: 'wk-fname', href: dl(0), download: f.name }, icon(ICON(f.name), 15), f.name), !f.local ? h('span', { class: 'small dim', title: t('O conteúdo está em outra máquina e será buscado ao abrir.') }, ' ☁') : null),
      h('td', { class: 'small' }, fmtSize(f.size)), h('td', { class: 'small' }, 'v' + f.versions.length), h('td', { class: 'small' }, userName(W.dir, f.owner)), h('td', { class: 'small' }, fmtWhen(f.updated)),
      h('td', null, h('button', { class: 'btn ghost icon sm', type: 'button', title: t('Ações'), dataset: { act: 'menu' }, onclick: (e) => menu(e.currentTarget, f) }, icon('more', 16))));
  }
  function menu(anchor, f) {
    const items = [];
    const add = (label, ic, fn, cls = '') => items.push(h('button', { class: 'toolopt ' + cls, type: 'button', onclick: async () => { pop.close(); await fn(); } }, icon(ic, 14), label));
    if (INLINE.test(f.name)) add(t('Abrir sem baixar'), 'eye', () => { window.open(`/api/work/files/${f.id}/download?inline=1`, '_blank', 'noopener'); });
    add(t('Baixar'), 'download', () => { location.href = `/api/work/files/${f.id}/download`; });
    if (f.versions.length > 1) f.versions.slice().reverse().forEach((v) => add(t('Baixar a versão {n} ({s})', { n: v.n, s: fmtWhen(v.ts) }), 'download', () => { location.href = `/api/work/files/${f.id}/download?v=${v.n}`; }));
    add(t('Usar no ASTA (anexo)'), 'copy', async () => { try { const m = await api(`/api/work/files/${f.id}/to-upload`, { method: 'POST', body: {} }); toast(t('«{n}» virou um anexo do ASTA: dá para usar no Chat, Canvas, Studio, Code…', { n: m.name }), 'ok'); } catch (e) { toast(e.message, 'err'); } });
    if (f.owner === W.me.user.id || W.can('files.delete')) {
      add(t('Mover para…'), 'arrow', () => move(f));
      add(t('Apagar'), 'trash', async () => { if (await confirmDialog(t('Apagar «{n}» para todos?', { n: f.name }))) { try { await api('/api/work/files/' + f.id, { method: 'DELETE' }); await load(); } catch (e) { toast(e.message, 'err'); } } }, 'danger');
    }
    const pop = popover(anchor, h('div', { class: 'wk-menu' }, ...items));
  }
  async function move(f) {
    const sel = select([['', t('Meus arquivos')], ...W.dir.folders.map((x) => [x.id, x.name])], f.folder_id || '', () => {}, { id: 'wk-move-to' });
    const d = dialog(t('Mover «{n}»', { n: f.name }), h('div', { class: 'wk-form' }, field(t('Para'), sel), h('div', { class: 'row', style: { justifyContent: 'flex-end', gap: '8px' } }, h('button', { class: 'btn', type: 'button', onclick: () => d.close(null) }, t('Cancelar')), h('button', { class: 'btn primary', type: 'button', id: 'wk-move-ok', onclick: () => d.close(sel.value) }, t('Mover')))));
    const to = await d.done;
    if (to === null) return;
    try { await api('/api/work/files/' + f.id, { method: 'PUT', body: { folder_id: to } }); await load(); } catch (e) { toast(e.message, 'err'); }
  }
  async function importProject() {
    let projects = [];
    try { projects = await api('/api/projects'); } catch (e) { toast(e.message, 'err'); return; }
    if (!projects.length) return toast(t('A Biblioteca do ASTA ainda não tem projetos.'), '');
    const sel = select(projects.map((p) => [p.id, p.name + ' · ' + (p.kind === 'game2d' ? t('Jogo 2D') : t('Mundo 3D'))]), projects[0].id, () => {}, { id: 'wk-lib-pick' });
    const d = dialog(t('Trazer da Biblioteca'), h('div', { class: 'wk-form' }, field(t('Projeto (vira um .zip neste setor)'), sel), h('div', { class: 'row', style: { justifyContent: 'flex-end', gap: '8px' } }, h('button', { class: 'btn', type: 'button', onclick: () => d.close(null) }, t('Cancelar')),
      h('button', { class: 'btn primary', type: 'button', id: 'wk-lib-ok', onclick: () => d.close(sel.value) }, t('Trazer')))));
    const id = await d.done;
    if (!id) return;
    try { await api('/api/work/files/from-project', { method: 'POST', body: { project_id: id, folder_id: S.folder } }); toast(t('Projeto enviado ao setor.'), 'ok'); await load(); } catch (e) { toast(e.message, 'err'); }
  }

  await load();
  W.live(['files', 'folders'], load);
}
