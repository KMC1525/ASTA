import { t } from '../i18n.js';
import { renderLibrary } from './library.js';

// Seção "Rebuild": os jogos reconstruídos (Ren'Py e RPG Maker 2000–MZ) e o botão para reconstruir outro.
export default (root, ctx) => renderLibrary(root, ctx, {
  kinds: ['game2d'], filter: (p) => !!p.rebuild, title: t('Rebuild'),
  subtitle: t("Reconstrua jogos Ren'Py e RPG Maker (2000 a MZ) em HTML/CSS/JS puro, com a mesma estrutura do original. Só para uso pessoal."),
  createMode: 'rebuild', section: 'rebuild', noUpdate: true, createLabel: t('Reconstruir um jogo'), emptyTitle: t('Reconstrua seu primeiro jogo'),
  emptyText: t("Anexe um jogo Ren'Py ou RPG Maker (um ZIP ou os arquivos) e o ASTA reconstrói a estrutura dele. Não publique o resultado na Steam nem em outras plataformas."),
});
