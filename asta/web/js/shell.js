// Casca do app: paleta de comandos, atalhos de teclado e boas-vindas. Recebe do main.js o que precisa (evita dependência circular).
import { api } from './api.js';
import { accentSwatches, themeCards } from './appearance.js';
import { t } from './i18n.js';
import { openPalette } from './palette.js';
import { CONFIG_TABS, ui } from './prefs.js';
import { download, h, icon, modal, toast } from './ui.js';

export function installShell(app) {
  const { state, NAV, go, saveSettings, renderSide } = app;
  const visibleNav = () => NAV.filter(([id]) => !(ui().sidebar_hidden || []).includes(id));
  const typing = (e) => { const el = e.target; return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)); };

  function toggleSidebar() { localStorage.setItem('asta.side', localStorage.getItem('asta.side') === '1' ? '0' : '1'); renderSide(); }
  async function toggleTheme() {
    const cur = document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
    await saveSettings({ ui: { theme: cur === 'light' ? 'dark' : 'light' } });
  }
  async function exportSettings() {
    const r = await fetch('/api/settings/export');
    download('asta-configuracoes.json', await r.text());
    toast(t('Configurações exportadas (sem chaves de API).'), 'ok');
  }

  function shortcutsHelp() {
    const rows = [['Ctrl/⌘ + K', t('Abrir a paleta de comandos')], ['Alt + 1 … 7', t('Ir para cada tela da barra lateral')], ['Alt + B', t('Recolher/expandir a barra lateral')], ['Alt + T', t('Alternar tema claro/escuro')],
      ['?', t('Mostrar esta ajuda')], [t('Enter / Ctrl+Enter'), t('Enviar mensagem (você escolhe em Configuração → Aparência)')], ['Shift + Enter', t('Quebrar a linha ao escrever')], ['Esc', t('Fechar janelas e a paleta')]];
    return modal(t('Atalhos de teclado'), h('dl', { class: 'shortcuts' }, rows.flatMap(([k, d]) => [h('dt', null, h('span', { class: 'kbd' }, k)), h('dd', null, d)])), [{ label: t('Fechar'), value: null, cls: 'primary' }]);
  }

  const host = {
    items() {
      const nav = NAV.map(([id, label, ic], i) => ({ group: t('Ir para'), label: t(label), icon: ic, keys: 'Alt+' + (i + 1), rank: 1, run: () => { state.ctx = {}; location.hash = '#/' + id; } }));
      const tabs = CONFIG_TABS.map(([id, label]) => ({ group: t('Configuração'), label: t('Configuração') + ' → ' + t(label), icon: 'config', run: () => go('config', { tab: id }) }));
      const actions = [
        { group: t('Ações'), label: t('Novo avatar'), icon: 'plus', run: () => { location.hash = '#/avatars/edit/new'; } },
        { group: t('Ações'), label: t('Novo chat'), icon: 'plus', run: () => go('main', { fresh: true }) },
        { group: t('Ações'), label: t('Nova criação (tela Chat)'), icon: 'sparkle', run: () => go('main', { fresh: true }) },
        { group: t('Ações'), label: t('Alternar tema claro/escuro'), icon: 'panel', keys: 'Alt+T', run: toggleTheme },
        { group: t('Ações'), label: t('Recolher/expandir a barra lateral'), icon: 'panel', keys: 'Alt+B', run: toggleSidebar },
        { group: t('Ações'), label: t('Ver atalhos de teclado'), icon: 'chev', keys: '?', run: shortcutsHelp },
        { group: t('Ações'), label: t('Exportar configurações (sem chaves de API)'), icon: 'download', run: exportSettings },
        { group: t('Ações'), label: t('Recarregar a página'), icon: 'refresh', run: () => location.reload() },
      ];
      return nav.concat(tabs, actions);
    },
    dataItems(avatars, projects, canvases) {
      const out = [];
      (avatars || []).forEach((a) => {
        out.push({ group: t('Avatares'), label: t('Conversar com {n}', { n: a.name }), hint: a.personality || '', icon: 'send', run: async () => { const c = await api('/api/avatar-chats', { method: 'POST', body: { avatar_ids: [a.id], reuse: true } }); location.hash = '#/avatars/chat/' + c.id; } });
        out.push({ group: t('Avatares'), label: t('Editar {n}', { n: a.name }), icon: 'edit', run: () => { location.hash = '#/avatars/edit/' + a.id; } });
      });
      (projects || []).forEach((p) => out.push({ group: t('Biblioteca'), label: p.name, hint: p.kind === 'game2d' ? t('Jogo 2D') : t('Mundo 3D'), icon: p.kind === 'game2d' ? 'games' : 'worlds', run: () => go('library', { highlight: p.id }) }));
      (canvases || []).forEach((c) => out.push({ group: t('Biblioteca'), label: c.name, hint: 'Canvas', icon: 'canvas', run: () => { location.hash = '#/canvas/edit/' + c.id; } }));
      return out;
    },
  };
  const open = () => openPalette(host);

  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k') { e.preventDefault(); open(); return; }  // a paleta sempre abre
    if (ui().shortcuts === false || document.querySelector('.modal-bg,.palette-bg')) return;
    if (e.altKey && !e.ctrlKey && !e.metaKey) {
      const m = /^Digit([1-9])$/.exec(e.code);
      if (m && NAV[Number(m[1]) - 1]) { e.preventDefault(); state.ctx = {}; location.hash = '#/' + NAV[Number(m[1]) - 1][0]; }
      else if (e.code === 'KeyB') { e.preventDefault(); toggleSidebar(); }
      else if (e.code === 'KeyT') { e.preventDefault(); toggleTheme(); }
      return;
    }
    if (e.key === '?' && !typing(e) && !e.ctrlKey && !e.metaKey) { e.preventDefault(); shortcutsHelp(); }
  });
  return { openPalette: open, shortcutsHelp, toggleSidebar, toggleTheme, exportSettings, visibleNav };
}

// Boas-vindas: só para quem abre o ASTA pela primeira vez (instalação nova, sem nada criado). Quem já usa o ASTA nunca vê.
export async function maybeWelcome(app, force = false) {
  const { state, saveSettings, go, refreshState, renderSide } = app;
  if (!force) {
    if (ui().welcome_done) return;
    const [projects, avatars, canvases] = await Promise.all([api('/api/projects').catch(() => []), api('/api/avatars').catch(() => []), api('/api/canvases').catch(() => [])]);
    if (projects.length || avatars.length || canvases.length) { await saveSettings({ ui: { welcome_done: true } }); return; }
  }
  let engine = null;
  try { engine = await api('/api/avatars/engine'); } catch (e) { /* sem informação de IA: segue */ }
  const save = (patch) => saveSettings({ ui: patch });
  const ai = engine && !engine.demo
    ? h('p', { class: 'muted small', style: { margin: 0 } }, '✦ ' + t('IA pronta: {n}', { n: t(engine.label) + (engine.model ? ' · ' + engine.model : '') }))
    : h('div', { class: 'errbox', style: { margin: 0, whiteSpace: 'normal' } }, t('Nenhuma IA configurada: o ASTA funciona em modo Demo (respostas prontas, sem inteligência). Configure um provedor — nuvem, LM Studio ou modelo local — para criar e conversar com IA de verdade.'));
  const langSel = h('select', null, [['auto', t('Automático (navegador)')], ['pt-BR', 'Português (Brasil)'], ['en', 'English']].map(([v, l]) => h('option', { value: v, selected: v === state.settings.language }, l)));
  langSel.addEventListener('change', async () => { await saveSettings({ language: langSel.value }); location.reload(); });
  const body = h('div', null,
    h('p', { class: 'muted', style: { marginTop: 0 } }, t('Escolha como quer ver o ASTA. Dá para mudar tudo depois em Configuração → Aparência.')),
    h('label', { class: 'f' }, t('Tema')), themeCards(ui().theme, (v) => save({ theme: v })),
    h('label', { class: 'f', style: { marginTop: '14px' } }, t('Cor de destaque')), accentSwatches(ui().accent, (v) => save({ accent: v })),
    h('label', { class: 'f', style: { marginTop: '14px' } }, t('Idioma')), langSel,
    h('div', { style: { marginTop: '16px' } }, ai),
    h('p', { class: 'dim small', style: { marginBottom: 0 } }, t('Dica: aperte Ctrl+K a qualquer momento para buscar telas, avatares e ações.')));
  const choice = await modal(t('Bem-vindo ao ASTA'), body, [{ label: engine && !engine.demo ? t('Começar') : t('Explorar no Demo'), value: 'go' }, ...(engine && !engine.demo ? [] : [{ label: t('Configurar IA'), value: 'ai', cls: 'primary' }])]);
  await saveSettings({ ui: { welcome_done: true } });
  renderSide();
  if (choice === 'ai') go('config', { tab: 'providers' });
}
