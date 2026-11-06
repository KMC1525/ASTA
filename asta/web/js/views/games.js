import { t } from '../i18n.js';
import { renderLibrary } from './library.js';

// Seção "Jogos 2D": a biblioteca filtrada em jogos (visual novel, RPG, plataforma, side scroller, point & click).
export default (root, ctx) => renderLibrary(root, ctx, {
  kinds: ['game2d'], title: t('Jogos 2D'), subtitle: t('Visual novels, RPGs, plataformas, side scrollers e point & clicks gerados pela IA — jogue no navegador ou baixe o ZIP.'),
  createMode: 'game', section: 'games', createLabel: t('Novo jogo'), emptyTitle: t('Crie seu primeiro jogo 2D'),
  emptyText: t('Descreva o jogo (ou anexe roteiros, imagens, documentos) e uma equipe de agentes escreve o jogo completo, jogável e sem dependências.'),
});
