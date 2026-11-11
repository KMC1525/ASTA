// Preferências de interface (settings.ui): leitura, aplicação na tela e atalhos para os outros módulos.
export const DEFAULT_UI = { theme: 'dark', accent: '', scale: 100, density: 'comfortable', motion: 'auto', font: 'system', chat_size: 'medium', send_key: 'enter', start_page: 'main', sidebar_hidden: [], shortcuts: true, welcome_done: false };

export const ui = () => Object.assign({}, DEFAULT_UI, window.ASTA_UI || {});
export function applyUi(next) { const merged = Object.assign({}, DEFAULT_UI, next || {}); if (window.ASTA_APPLY_UI) window.ASTA_APPLY_UI(merged); else window.ASTA_UI = merged; return merged; }

// Enter envia ou quebra a linha conforme a preferência. Sempre ignora Enter durante a composição de texto (IME) e Shift+Enter quebra a linha.
export function isSendKey(e) {
  if (e.key !== 'Enter' || e.isComposing || e.keyCode === 229) return false;   // Enter que confirma uma palavra no teclado japonês/chinês/coreano (IME) não envia
  if (ui().send_key === 'ctrl_enter') return e.ctrlKey || e.metaKey;
  return !e.shiftKey && !e.ctrlKey && !e.metaKey;
}
export const sendHint = () => (ui().send_key === 'ctrl_enter' ? 'Ctrl+Enter' : 'Enter');

// Abas da Configuração (a paleta de comandos também leva a cada uma)
export const CONFIG_GROUPS = [['general', 'Geral'], ['ai', 'IA e modelos'], ['sections', 'Seções'], ['system', 'Sistema']];
export const CONFIG_TABS = [['appearance', 'Aparência', 'general'], ['profile', 'Perfil', 'general'], ['memory', 'Memória', 'general'], ['sections', 'Seções e atalhos', 'general'],
  ['providers', 'Provedores', 'ai'], ['media', 'Mídia', 'ai'], ['voice', 'Voz', 'ai'], ['local', 'Modelos locais', 'ai'],
  ['chat', 'Chat', 'sections'], ['engine', 'Game Engine', 'sections'], ['scriber', 'Scriber', 'sections'], ['avatars', 'Avatars', 'sections'], ['canvas', 'Canvas', 'sections'], ['studio', 'Studio', 'sections'], ['computer', 'Computer Use', 'sections'], ['code', 'Code', 'sections'], ['work', 'Work', 'sections'], ['rebuild', 'Rebuild', 'sections'],
  ['performance', 'Desempenho', 'system'], ['data', 'Dados e backup', 'system'], ['mobile', 'Celular e tablet', 'system'], ['system', 'Sistema', 'system']];
export const DRAFT_PREFIX = 'asta.draft.';  // rascunhos do chat dos avatares (por conversa, na sessão do navegador)
