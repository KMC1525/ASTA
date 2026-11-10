// Game Engine → Code: inspirada no VS Code. Esquerda: prompt (IA edita o código; opcional: modo Code do ASTA). Meio: pastas e arquivos do jogo (criar, renomear, mover, enviar, apagar). Direita: editor com abas.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { createEditor, langOf } from '../editor_core.js';
import { btn, fileInputButton, flatFiles, fmtSize, ibtn, promptPanel } from '../engine_ui.js';
import { confirmDialog, h, icon, modal, toast } from '../ui.js';

const ICON = { js: 'code', json: 'file', css: 'file', html: 'code', md: 'doc', txt: 'doc', svg: 'image', png: 'image', jpg: 'image', jpeg: 'image', webp: 'image', gif: 'image', wav: 'audio', mp3: 'audio', ogg: 'audio', m4a: 'audio', flac: 'audio' };
const SKELETON = {
  js: (n) => `// Comportamento «${n}». Use na cena: "behaviors": [{ "type": "${n}" }]\nGE.behavior('${n}', {\n  init: function (n, p, s) {\n    // roda uma vez quando o nó nasce\n  },\n  update: function (n, dt, p, s) {\n    // roda a cada quadro (dt = segundos)\n  },\n});\n`,
  json: () => '{\n  \n}\n', md: (n) => `# ${n}\n\n`, txt: () => '', css: () => '', html: () => '',
};

export default async function render(body, E) {
  const S = { tree: [], open: [], active: '', folded: new Set(), sel: '', useCode: false, codeSession: ((E.proj.connections || {}).code_session) || '' };
  const ext = (p) => String(p).split('.').pop().toLowerCase();
  let editor = null;

  // ---------------------------------------------------------------- explorador
  const explorer = h('div', { class: 'ge-files', id: 'ge-files', role: 'tree', 'aria-label': t('Arquivos do jogo') });
  async function loadTree(keep) { S.tree = (await E.api.tree('game')).children; paintTree(); }
  function dirOf(p) { return p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : ''; }
  function paintTree() {
    const rows = [];
    const walk = (nodes, depth) => nodes.forEach((n) => {
      const isDir = n.type === 'dir', open = !S.folded.has(n.path);
      const row = h('div', { class: 'ge-frow' + (S.sel === n.path ? ' on' : ''), role: 'treeitem', dataset: { path: n.path, type: n.type }, style: { paddingLeft: 6 + depth * 13 + 'px' }, draggable: 'true',
        onclick: () => { S.sel = n.path; if (isDir) { open ? S.folded.add(n.path) : S.folded.delete(n.path); paintTree(); } else { openFile(n.path); paintTree(); } }, ondblclick: () => { if (!isDir) openFile(n.path, true); } },
        h('span', { class: 'fi' }, isDir ? icon(open ? 'chevd' : 'chevr', 12) : null), h('span', { class: 'fi' }, icon(isDir ? 'folder' : (ICON[n.ext && n.ext.slice(1)] || 'file'), 14)), h('span', { class: 'fn', title: n.path }, n.name), isDir ? null : h('span', { class: 'fs' }, fmtSize(n.size)));
      row.addEventListener('dragstart', (e) => { e.dataTransfer.setData('text/plain', n.path); e.dataTransfer.effectAllowed = 'move'; });
      row.addEventListener('dragover', (e) => { e.preventDefault(); if (isDir || true) row.dataset.drop = 'in'; });
      row.addEventListener('dragleave', () => { delete row.dataset.drop; });
      row.addEventListener('drop', async (e) => {
        e.preventDefault(); e.stopPropagation(); delete row.dataset.drop; const target = isDir ? n.path : dirOf(n.path);
        if (e.dataTransfer.files && e.dataTransfer.files.length) { await uploadFiles([...e.dataTransfer.files], target); return; }
        const src = e.dataTransfer.getData('text/plain'); if (!src || src === target || dirOf(src) === target) return;
        try { await E.api.rename(src, (target ? target + '/' : '') + src.split('/').pop()); S.open.forEach((o) => { if (o.path === src) o.path = (target ? target + '/' : '') + src.split('/').pop(); }); if (S.active === src) S.active = (target ? target + '/' : '') + src.split('/').pop(); await loadTree(); paintTabs(); } catch (err) { toast(err.message, 'err'); }
      });
      rows.push(row);
      if (isDir && open) walk(n.children || [], depth + 1);
    });
    walk(S.tree, 0);
    explorer.replaceChildren(...(rows.length ? rows : [h('div', { class: 'muted small', style: { padding: '10px' } }, t('Pasta vazia.'))]));
  }
  explorer.addEventListener('dragover', (e) => e.preventDefault());
  explorer.addEventListener('drop', async (e) => { e.preventDefault(); if (e.dataTransfer.files && e.dataTransfer.files.length) await uploadFiles([...e.dataTransfer.files], ''); });
  async function uploadFiles(files, dir) {
    let ok = 0;
    for (const f of files) {
      try {
        if (/\.zip$/i.test(f.name)) { const r = await api(E.api.base + '/import-zip?area=game&into=' + encodeURIComponent(dir || ''), { method: 'POST', body: f, raw: true, headers: { 'Content-Type': 'application/zip' } }); ok += r.written; if (r.skipped) toast(t('{n} arquivo(s) do ZIP ignorados (tipo não permitido).', { n: r.skipped })); continue; }
        await E.api.upload((dir ? dir + '/' : '') + f.name, f); ok++;
      } catch (e) { toast(f.name + ': ' + e.message, 'err'); }
    }
    if (ok) { toast(t('{n} arquivo(s) enviados', { n: ok }), 'ok'); await loadTree(); }
  }
  const curDir = () => { const n = flatFiles(S.tree).find((f) => f.path === S.sel); if (n) return dirOf(n.path); return S.sel || 'scripts'; };
  async function newFile() {
    const dir = curDir(), inp = h('input', { value: (dir ? dir + '/' : '') + 'novo.js', id: 'ge-nf-name', 'aria-label': t('Caminho do arquivo') });
    if (await modal(t('Novo arquivo'), h('div', null, inp, h('p', { class: 'muted small' }, t('Use «/» para criar subpastas. Tipos: .js .json .css .html .md .txt .svg …'))), [{ label: t('Cancelar'), value: null }, { label: t('Criar'), value: 'ok', cls: 'primary' }]) !== 'ok' || !inp.value.trim()) return;
    const path = inp.value.trim().replace(/^\/+/, ''), e = ext(path), base = path.split('/').pop().replace(/\.[^.]+$/, '').replace(/[^\w]+/g, '_');
    try { await E.api.write(path, (SKELETON[e] || (() => ''))(base), 'game'); await loadTree(); S.sel = path; openFile(path); } catch (err) { toast(err.message, 'err'); }
  }
  async function newFolder() {
    const inp = h('input', { value: (curDir() ? curDir() + '/' : '') + 'nova-pasta', id: 'ge-nd-name' });
    if (await modal(t('Nova pasta'), inp, [{ label: t('Cancelar'), value: null }, { label: t('Criar'), value: 'ok', cls: 'primary' }]) !== 'ok' || !inp.value.trim()) return;
    try { await E.api.mkdir(inp.value.trim().replace(/^\/+/, '')); await loadTree(); } catch (err) { toast(err.message, 'err'); }
  }
  async function renameSel() {
    if (!S.sel) return; const inp = h('input', { value: S.sel, id: 'ge-rn-name' });
    if (await modal(t('Renomear / mover'), inp, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]) !== 'ok' || inp.value.trim() === S.sel) return;
    try { const to = inp.value.trim().replace(/^\/+/, ''); await E.api.rename(S.sel, to); S.open.forEach((o) => { if (o.path === S.sel) o.path = to; }); if (S.active === S.sel) S.active = to; S.sel = to; await loadTree(); paintTabs(); } catch (err) { toast(err.message, 'err'); }
  }
  async function deleteSel() {
    if (!S.sel) return; if (!(await confirmDialog(t('Apagar «{n}»? Se for uma pasta, tudo dentro dela também.', { n: S.sel })))) return;
    try { await E.api.remove(S.sel); S.open = S.open.filter((o) => o.path !== S.sel && !o.path.startsWith(S.sel + '/')); if (!S.open.find((o) => o.path === S.active)) S.active = (S.open[0] || {}).path || ''; S.sel = ''; await loadTree(); paintTabs(); showActive(); } catch (err) { toast(err.message, 'err'); }
  }

  // ---------------------------------------------------------------- editor
  const tabsEl = h('div', { class: 'ge-etabs', id: 'ge-etabs', role: 'tablist' });
  const stage = h('div', { class: 'ge-editor', id: 'ge-editor' });
  const statusEl = h('div', { class: 'ge-estatus', id: 'ge-estatus' });
  const findBar = h('div', { class: 'ge-findbar hidden', id: 'ge-findbar' });
  const findIn = h('input', { placeholder: t('Buscar no arquivo…'), id: 'ge-find', 'aria-label': t('Buscar') });
  findIn.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); if (editor) editor.find(findIn.value); } if (e.key === 'Escape') { findBar.classList.add('hidden'); if (editor) editor.focus(); } });
  findBar.append(findIn, btn(t('Próximo'), 'arrow', () => editor && editor.find(findIn.value)), ibtn(t('Fechar'), 'x', () => findBar.classList.add('hidden')));
  async function openFile(path, pin) {
    let f = S.open.find((o) => o.path === path);
    if (!f) {
      try { const r = await E.api.read(path); f = { path, type: r.type, content: r.content, orig: r.content, size: r.size, dirty: false }; } catch (e) { toast(e.message, 'err'); return; }
      S.open.push(f);
    }
    S.active = path; paintTabs(); showActive();
  }
  function paintTabs() {
    tabsEl.replaceChildren(...S.open.map((o) => h('div', { class: 'ge-etab' + (o.path === S.active ? ' on' : ''), role: 'tab', dataset: { path: o.path }, title: o.path, onclick: () => { S.active = o.path; paintTabs(); showActive(); } },
      icon(ICON[ext(o.path)] || 'file', 13), h('span', null, o.path.split('/').pop()), o.dirty ? h('span', { class: 'dirty' }, '●') : null,
      h('span', { class: 'x', title: t('Fechar'), onclick: async (e) => { e.stopPropagation(); if (o.dirty && !(await confirmDialog(t('«{n}» tem mudanças não salvas. Fechar mesmo assim?', { n: o.path }), true, t('Fechar')))) return; S.open = S.open.filter((x) => x !== o); if (S.active === o.path) S.active = (S.open[S.open.length - 1] || {}).path || ''; paintTabs(); showActive(); } }, '×'))));
  }
  function paintStatus(extra) {
    const f = S.open.find((o) => o.path === S.active);
    statusEl.replaceChildren(f ? h('span', { class: 'mono' }, f.path) : null, f && f.type === 'text' ? h('span', null, langOf(f.path).toUpperCase()) : null, extra ? h('span', null, extra) : null, h('span', { class: 'grow' }), f && f.type === 'text' ? h('span', null, f.dirty ? t('não salvo') : t('salvo')) : null);
  }
  async function saveFile(f) {
    f = f || S.open.find((o) => o.path === S.active); if (!f || f.type !== 'text') return;
    f.content = editor && S.active === f.path ? editor.get() : f.content;
    try { const r = await E.api.write(f.path, f.content); f.orig = f.content; f.dirty = false; paintTabs(); paintStatus(); (r.warnings || []).forEach((w) => toast(f.path + ': ' + w, 'err')); await loadTree(); if (!(r.warnings || []).length) toast(t('Salvo: {p}', { p: f.path }), 'ok'); } catch (e) { toast(e.message, 'err'); }
  }
  function showActive() {
    const f = S.open.find((o) => o.path === S.active); editor = null; findBar.classList.add('hidden');
    if (!f) { stage.replaceChildren(h('div', { class: 'empty', style: { margin: 'auto' } }, h('h3', null, t('Abra um arquivo')), h('p', null, t('Escolha um arquivo na árvore, crie um novo ou peça à IA no prompt à esquerda.')))); paintStatus(); return; }
    if (f.type === 'image') { stage.replaceChildren(h('div', { class: 'ge-preview' }, h('img', { src: E.api.raw(f.path), alt: f.path }))); paintStatus(fmtSize(f.size)); return; }
    if (f.type === 'audio') { stage.replaceChildren(h('div', { class: 'ge-preview' }, h('audio', { controls: true, src: E.api.raw(f.path) }))); paintStatus(fmtSize(f.size)); return; }
    if (f.type !== 'text') { stage.replaceChildren(h('div', { class: 'ge-preview' }, h('div', { class: 'empty' }, h('h3', null, t('Arquivo binário')), h('p', null, fmtSize(f.size)), h('a', { class: 'btn', href: E.api.raw(f.path), download: f.path.split('/').pop() }, icon('download', 14), t('Baixar'))))); paintStatus(); return; }
    editor = createEditor({ value: f.content, lang: langOf(f.path), label: f.path, onChange: (v) => { f.content = v; const d = v !== f.orig; if (d !== f.dirty) { f.dirty = d; paintTabs(); paintStatus(); } }, onSave: () => saveFile(f), onCursor: (c) => { const sp = statusEl.querySelector('.cur'); if (sp) sp.textContent = t('Linha {l}, col. {c}', { l: c.line, c: c.col }) + (c.sel ? ' · ' + t('{n} selecionados', { n: c.sel }) : ''); } });
    stage.replaceChildren(findBar, editor.el, statusEl); paintStatus();
    statusEl.insertBefore(h('span', { class: 'cur' }, ''), statusEl.querySelector('.grow'));
    editor.ta.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') { e.preventDefault(); findBar.classList.remove('hidden'); findIn.focus(); findIn.select(); } });
    editor.focus();
  }
  async function formatJson() { const f = S.open.find((o) => o.path === S.active); if (!f || !editor || ext(f.path) !== 'json') return; try { editor.set(JSON.stringify(JSON.parse(editor.get()), null, 2) + '\n'); f.content = editor.get(); f.dirty = f.content !== f.orig; paintTabs(); paintStatus(); } catch (e) { toast(t('JSON inválido: {e}', { e: e.message }), 'err'); } }
  const saveAll = async () => { for (const f of S.open.filter((o) => o.dirty)) await saveFile(f); };

  // ---------------------------------------------------------------- IA + conexão opcional com o modo Code
  const linkBox = h('div', { class: 'ge-linkbox', id: 'ge-linkbox' });
  const useCode = h('input', { type: 'checkbox', id: 'ge-usecode', checked: false });
  const paintLink = () => linkBox.replaceChildren(h('label', { class: 'check' }, useCode, h('span', null, t('Usar o modo Code do ASTA (equipe de agentes com testes e git)'))),
    h('div', { class: 'small', style: { marginTop: '4px' } }, useCode.checked ? t('Os prompts abaixo vão para uma sessão do modo Code apontada para a pasta do jogo. O que ele escrever aparece aqui ao recarregar.') : t('Desligado: a IA do Game Engine edita os arquivos direto (rápido, só scripts, dados e cenas).')),
    S.codeSession ? h('div', { style: { marginTop: '6px' } }, h('a', { class: 'btn sm', href: '#/code/' + S.codeSession, id: 'ge-open-code' }, icon('code', 13), t('Abrir a sessão no modo Code'))) : null);
  useCode.addEventListener('change', () => { S.useCode = useCode.checked; paintLink(); }); paintLink();
  const pp = promptPanel(E, {
    tab: 'code', endpoint: 'code', title: t('Prompt de código'), placeholder: t('Peça uma mudança: “faça o jogador dar um dash com Shift”, “crie um chefe que atira”…'), intro: t('A IA lê os arquivos abertos, planeja, escreve e confere a sintaxe. Os scripts rodam só dentro do jogo (isolados do ASTA).'),
    hints: [t('Crie um comportamento que faça o inimigo pulsar'), t('Adicione um dash quando apertar Shift'), t('Faça a câmera tremer quando o jogador levar dano')],
    body: () => ({ files: [S.active].concat(S.open.map((o) => o.path)).filter((p, i, a) => p && a.indexOf(p) === i && ext(p) !== 'png').slice(0, 6) }),
    onStart: async () => { await saveAll(); },
    intercept: async (text, ids, { addMsg }) => {
      if (!S.useCode) return false;
      const link = await api(E.api.base + '/code-link', { method: 'POST', body: {} }); S.codeSession = link.session_id;
      await api('/api/code/sessions/' + S.codeSession + '/send', { method: 'POST', body: { message: text, attachment_ids: ids } });
      addMsg('ai', t('Enviei o pedido ao modo Code. Acompanhe a sessão lá; depois use ↻ para recarregar os arquivos aqui.')); paintLink(); return true;
    },
    onResult: async (res) => {
      await loadTree();
      for (const f of S.open) { if ((res.files || []).includes(f.path)) { try { const r = await E.api.read(f.path); f.content = r.content; f.orig = r.content; f.dirty = false; } catch (e) { /* ok */ } } }
      if ((res.files || [])[0] && !S.open.find((o) => o.path === res.files[0])) await openFile(res.files[0]); else { paintTabs(); showActive(); }
    },
  });
  const left = h('div', { class: 'ge-left' }, linkBox, pp.el);

  // ---------------------------------------------------------------- montagem
  const mid = h('aside', { class: 'ge-mid', 'aria-label': t('Explorador') },
    h('div', { class: 'ge-ph' }, h('b', null, t('Arquivos'))),
    h('div', { class: 'ge-ftool' }, ibtn(t('Novo arquivo'), 'plus', newFile, '', { id: 'ge-new-file' }), ibtn(t('Nova pasta'), 'folder', newFolder, '', { id: 'ge-new-folder' }), fileInputButton('', '', (fs) => uploadFiles(fs, curDir()), true), ibtn(t('Renomear / mover'), 'edit', renameSel, '', { id: 'ge-rename' }), ibtn(t('Apagar'), 'trash', deleteSel, '', { id: 'ge-delete' }), ibtn(t('Atualizar'), 'refresh', () => loadTree(), '', { id: 'ge-refresh' })),
    explorer);
  const right = h('section', { class: 'ge-center', 'aria-label': t('Editor') },
    h('div', { class: 'ge-vtool' }, btn(t('Salvar'), 'check', () => saveFile(), 'primary', { id: 'ge-save' }), btn(t('Salvar tudo'), 'check', saveAll), btn(t('Formatar JSON'), 'wand', formatJson), h('span', { class: 'grow' }), h('a', { class: 'btn sm', href: E.api.play('index.html'), target: '_blank', rel: 'noopener' }, icon('play', 13), t('Testar o jogo'))),
    tabsEl, stage);
  body.replaceChildren(h('div', { class: 'ge-grid code ge-codegrid' }, left, mid, right));
  E.onCleanup(() => { const dirty = S.open.filter((o) => o.dirty); dirty.forEach((f) => { E.api.write(f.path, f.path === S.active && editor ? editor.get() : f.content).catch(() => {}); }); });
  await loadTree(); S.folded = new Set(); showActive();
  const first = flatFiles(S.tree).find((f) => f.path.startsWith('scripts/') && f.ext === '.js') || flatFiles(S.tree).find((f) => f.path.endsWith('.scene.json'));
  if (first) openFile(first.path);
}
