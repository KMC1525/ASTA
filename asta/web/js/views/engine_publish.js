// Game Engine → Publish: exportar para Web (HTML5 + PWA), Windows, macOS, Linux, Android e iOS. Cada pacote leva o jogo jogável e um projeto nativo pronto para compilar
// (Electron no desktop, Capacitor no celular) com fluxo do GitHub Actions. O prompt escreve textos de loja, notas de versão e ajustes. Veja os limites honestos em cada cartão.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { btn, flatFiles, fmtSize, ibtn, promptPanel, propRow, stem } from '../engine_ui.js';
import { confirmDialog, h, icon, toast } from '../ui.js';

const PLATS = [
  ['web', 'Web (HTML5 + PWA)', 'globe', 'Abre em qualquer navegador moderno, sem servidor. Inclui manifesto e service worker (instala como app). Para itch.io, GitHub Pages ou o seu site.'],
  ['win', 'Windows', 'computer', 'Jogar.bat (janela de app) + projeto Electron para gerar o .exe (instalador/portátil) com Node.js — ou pelo GitHub Actions.'],
  ['macos', 'macOS', 'computer', 'Jogar.command + projeto Electron para o .dmg (em um Mac). Distribuir fora da App Store exige assinatura e notarização da Apple.'],
  ['linux', 'Linux', 'computer', 'jogar.sh + .desktop + projeto Electron para AppImage/.deb (Node.js ou GitHub Actions).'],
  ['android', 'Android', 'rocket', 'Projeto Capacitor para o APK (Node.js, JDK 17 e Android SDK — ou GitHub Actions). Play Store exige keystore e conta de desenvolvedor.'],
  ['ios', 'iOS', 'rocket', 'Projeto Capacitor para o Xcode (só em um Mac). Aparelho e App Store exigem conta Apple Developer; o GitHub Actions gera um build de simulador sem assinatura.'],
];

export default async function render(body, E) {
  const P = Object.assign({ version: '1.0.0', package: '', author: '', short: '', description: '', tags: '', release_notes: '' }, E.proj.publish || {});
  const st = E.proj.settings || {};
  const S = { orientation: st.orientation || 'landscape', fullscreen: st.fullscreen !== false, busy: new Set(), exports: [] };
  const exportsEl = h('div', { class: 'ge-exports', id: 'ge-exports' }), platsEl = h('div', { class: 'ge-plats', id: 'ge-plats' }), checksEl = h('div', { class: 'ge-checks', id: 'ge-checks' });

  async function saveSettings() {
    try { E.proj = await E.api.put('', { publish: { version: P.version, package: P.package, author: P.author, short: P.short, description: P.description, tags: P.tags, release_notes: P.release_notes }, settings: { orientation: S.orientation, fullscreen: S.fullscreen, package: P.package } }); } catch (e) { toast(e.message, 'err'); }
  }
  async function exportOne(id) {
    if (S.busy.has(id)) return; S.busy.add(id); paintPlats();
    try { await saveSettings(); const r = await api(E.api.base + '/export', { method: 'POST', body: { platform: id, version: P.version, package: P.package, author: P.author } }); toast(t('Exportado: {f} ({s})', { f: r.file, s: fmtSize(r.size) }), 'ok'); (r.notes || []).forEach((n) => toast(t(n))); await loadExports(); }
    catch (e) { toast(e.message, 'err'); } finally { S.busy.delete(id); paintPlats(); }
  }
  async function loadExports() { S.exports = (await api(E.api.base + '/exports')).items; paintExports(); paintPlats(); }
  function paintExports() {
    exportsEl.replaceChildren(...(S.exports.length ? S.exports.map((x) => h('div', { class: 'ge-exp', dataset: { file: x.file } }, icon('archive', 15), h('span', { class: 'nm', title: x.file }, x.file), h('span', { class: 'small dim' }, fmtSize(x.size) + ' · ' + x.t),
      h('a', { class: 'btn sm', href: x.url, download: x.file }, icon('download', 13), t('Baixar')), ibtn(t('Apagar'), 'trash', async () => { if (await confirmDialog(t('Apagar «{n}»?', { n: x.file }))) { await api(E.api.base + '/exports/' + encodeURIComponent(x.file), { method: 'DELETE' }); loadExports(); } }))) : [h('div', { class: 'muted small' }, t('Nada exportado ainda.'))]));
  }
  function paintPlats() {
    platsEl.replaceChildren(...PLATS.map(([id, label, ic, hint]) => {
      const last = S.exports.find((x) => x.platform === id);
      return h('div', { class: 'ge-plat', dataset: { platform: id } }, h('h3', null, icon(ic, 18), label), h('div', { class: 'small muted' }, t(hint)),
        h('div', { class: 'row', style: { gap: '8px', marginTop: 'auto', flexWrap: 'wrap' } }, h('button', { class: 'btn primary sm', type: 'button', id: 'ge-export-' + id, disabled: S.busy.has(id), onclick: () => exportOne(id) }, icon('rocket', 13), S.busy.has(id) ? t('Gerando…') : t('Exportar')),
          last ? h('a', { class: 'btn sm', href: last.url, download: last.file }, icon('download', 13), t('Baixar o último')) : null, last ? h('span', { class: 'small dim' }, fmtSize(last.size)) : null));
    }));
  }
  async function paintChecks() {
    const tr = await E.api.tree('game'), files = flatFiles(tr.children), maps = (await E.api.maps()).maps, scenes = (await E.api.get('/scenes')).scenes;
    const list = [];
    const ok = (good, label) => list.push([good, label]);
    ok(scenes.length > 0, t('{n} cena(s)', { n: scenes.length })); ok(maps.length > 0 || E.proj.kind === 'ar' || E.proj.genre === 'vr_room', t('{n} mapa(s)', { n: maps.length }));
    let allMapsOk = true; for (const m of maps) { const full = await E.api.map(m.path); const hasP = (full.objects || []).some((o) => o.type === 'player'), hasG = (full.objects || []).some((o) => o.type === 'goal' || o.type === 'portal'); if (!hasP || !hasG) allMapsOk = false; }
    ok(allMapsOk, t('Todo mapa tem ponto de partida e objetivo'));
    const au = (E.proj.settings || {}).audio || {}, snds = files.filter((f) => f.path.startsWith('assets/sound/')), imgs = files.filter((f) => f.path.startsWith('assets/images/'));
    ok(snds.length > 0, t('{n} som(ns)', { n: snds.length })); ok(!!au.music && snds.some((f) => stem(f.path) === au.music), t('Música de fundo definida')); ok(imgs.length > 0, t('{n} imagem(ns)', { n: imgs.length })); ok(files.some((f) => f.path === 'assets/icon.png'), t('Ícone próprio (assets/icon.png) — sem ele o ASTA gera um'));
    checksEl.replaceChildren(...list.map(([good, label]) => h('div', { class: 'ge-check' }, h('span', { class: good ? 'ok' : 'no' }, icon(good ? 'check' : 'warn', 14)), label)));
  }

  // ---- formulário
  const txt = (key, o = {}) => { const i = h(o.area ? 'textarea' : 'input', Object.assign({ id: 'ge-p-' + key, value: P[key] || '', rows: o.rows }, o.attrs || {})); if (o.area) i.value = P[key] || ''; i.addEventListener('change', () => { P[key] = i.value; saveSettings(); }); return i; };
  const orient = h('select', { id: 'ge-p-orient' }, [['landscape', t('Horizontal')], ['portrait', t('Vertical')], ['any', t('Qualquer')]].map(([v, l]) => h('option', { value: v, selected: S.orientation === v }, l))); orient.addEventListener('change', () => { S.orientation = orient.value; saveSettings(); });
  const full = h('input', { type: 'checkbox', checked: S.fullscreen, id: 'ge-p-full' }); full.addEventListener('change', () => { S.fullscreen = full.checked; saveSettings(); });
  const iconBox = h('div', { class: 'ge-iact' }, h('span', { class: 'small muted' }, t('O ícone é gerado com a inicial do jogo. Para um próprio, salve um PNG como assets/icon.png (aba Assets → Aplicar ao jogo, com o nome «icon» — depois mova para assets/).')));
  const form = h('div', { class: 'ge-insp', id: 'ge-pform' },
    h('div', { class: 'ge-igrp' }, h('h4', null, t('Aplicativo')), propRow(t('Versão'), txt('version', { attrs: { placeholder: '1.0.0' } })), propRow(t('Identificador'), txt('package', { attrs: { placeholder: 'com.seunome.jogo' } }), t('com.empresa.jogo — usado no Android, iOS e desktop')), propRow(t('Autor'), txt('author')), propRow(t('Orientação'), orient), propRow(t('Tela cheia'), full), iconBox),
    h('div', { class: 'ge-igrp' }, h('h4', null, t('Página do jogo')), propRow(t('Resumo'), txt('short')), propRow(t('Descrição'), txt('description', { area: true, rows: 6 })), propRow(t('Etiquetas'), txt('tags')), propRow(t('Notas da versão'), txt('release_notes', { area: true, rows: 4 }))));

  const pp = promptPanel(E, {
    tab: 'publish', endpoint: 'publish-ai', title: t('Prompt de publicação'), placeholder: t('Peça: “texto de loja em inglês”, “notas da versão 1.1”, “deixe em modo retrato”, “resumo curto e divertido”…'),
    intro: t('A IA escreve a página do jogo (resumo, descrição, etiquetas, notas) e sugere ajustes de exportação — só afirma o que o jogo realmente tem.'),
    hints: [t('Descrição de loja curta e empolgante'), t('Notas da primeira versão'), t('Etiquetas para itch.io')],
    onResult: async (res) => { const p = res.publish || {}; Object.assign(P, { short: p.short || P.short, description: p.description || P.description, tags: (p.tags || []).join(', ') || P.tags, release_notes: p.release_notes || P.release_notes, version: p.version || P.version }); if (p.orientation) S.orientation = p.orientation; if (typeof p.fullscreen === 'boolean') S.fullscreen = p.fullscreen; await saveSettings(); render(body, E); toast(t('Textos de publicação atualizados'), 'ok'); },
  });
  const center = h('section', { class: 'ge-pub' }, h('div', { class: 'page-h' }, h('div', null, h('h1', { style: { fontSize: '22px' } }, t('Publicar')), h('p', null, t('Exporte o jogo para cada plataforma. Todos os pacotes levam o jogo jogável; o instalador nativo precisa do Node.js, Android SDK ou Xcode — ou do fluxo do GitHub Actions que vai junto.')))),
    h('div', { class: 'row', style: { gap: '8px', margin: '0 0 14px' } }, h('button', { class: 'btn primary', type: 'button', id: 'ge-export-all', onclick: async () => { for (const [id] of PLATS) await exportOne(id); } }, icon('rocket', 14), t('Exportar tudo')), h('a', { class: 'btn', href: E.api.play('index.html'), target: '_blank', rel: 'noopener', id: 'ge-pub-test' }, icon('play', 14), t('Testar no navegador'))),
    platsEl, h('h2', { class: 'ge-h2' }, t('Verificações')), checksEl, h('h2', { class: 'ge-h2' }, t('Pacotes exportados')), exportsEl,
    h('p', { class: 'muted small', style: { marginTop: '18px' } }, t('Limites honestos: o ASTA não compila nem assina binários nativos; VR/AR rodam por WebXR no navegador do aparelho e não foram testados em headset real.')));
  const right = h('aside', { class: 'ge-right' }, h('div', { class: 'ge-ph' }, h('b', null, t('Ajustes de publicação'))), form);
  body.replaceChildren(h('div', { class: 'ge-grid ge-pubgrid' }, h('div', { class: 'ge-left' }, pp.el), center, right));
  paintPlats(); await Promise.all([loadExports(), paintChecks()]);
}
