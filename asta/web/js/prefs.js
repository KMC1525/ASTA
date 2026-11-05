// Preferências de interface (settings.ui): leitura, aplicação na tela e atalhos para os outros módulos.
export const DEFAULT_UI = { theme: 'dark', accent: '', scale: 100, density: 'comfortable', motion: 'auto', font: 'system', chat_size: 'medium', send_key: 'enter', start_page: 'main', sidebar_hidden: [], shortcuts: true, welcome_done: false };

export const ui = () => Object.assign({}, DEFAULT_UI, window.ASTA_UI || {});
export function applyUi(next) { const merged = Object.assign({}, DEFAULT_UI, next || {}); if (window.ASTA_APPLY_UI) window.ASTA_APPLY_UI(merged); else window.ASTA_UI = merged; return merged; }

// Enter envia ou quebra a linha conforme a preferência. Sempre ignora Enter durante a composição de texto (IME) e Shift+Enter quebra a linha.
export function isSendKey(e) {
  if (e.key !== 'Enter' || e.isComposing) return false;
  if (ui().send_key === 'ctrl_enter') return e.ctrlKey || e.metaKey;
  return !e.shiftKey && !e.ctrlKey && !e.metaKey;
}
export const sendHint = () => (ui().send_key === 'ctrl_enter' ? 'Ctrl+Enter' : 'Enter');

// Abas da Configuração (a paleta de comandos também leva a cada uma)
export const CONFIG_TABS = [['providers', 'Provedores'], ['media', 'Mídia'], ['chat', 'Chat'], ['generation', 'Geração'], ['creative', 'Avatars e jogos'], ['voice', 'Voz'], ['local', 'Modelos locais'], ['appearance', 'Aparência'], ['system', 'Sistema']];
export const DRAFT_PREFIX = 'asta.draft.';  // rascunhos do chat dos avatares (por conversa, na sessão do navegador)
