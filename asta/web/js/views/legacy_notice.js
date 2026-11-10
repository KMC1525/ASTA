// Aviso das telas antigas «Mundos» e «Jogos 2D»: foram substituídas pelo Game Engine, mas o que você criou nelas continua aqui e na Biblioteca.
import { t } from '../i18n.js';
import { go } from '../main.js';
import { h, icon } from '../ui.js';

export function legacyNotice() {
  return h('div', { class: 'card', id: 'legacy-notice', style: { margin: '14px 22px 0', display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' } },
    icon('engine', 20), h('div', { style: { flex: 1, minWidth: '220px' } }, h('b', null, t('Esta tela foi substituída pelo Game Engine.')), h('div', { class: 'muted small' }, t('Os mundos e jogos que você já criou continuam aqui e na Biblioteca. Para criar novos (2D, 2.5D, 3D, VR e AR) e editar tudo, use o Game Engine.'))),
    h('button', { class: 'btn primary', type: 'button', id: 'legacy-go', onclick: () => go('engine', {}) }, icon('arrow', 14), t('Abrir o Game Engine')));
}
