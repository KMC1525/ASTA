// Etapas dos pipelines multi-agentes (nomes, descrições e o texto de detalhe de cada etapa) para a tela de acompanhamento.
import { t } from '../i18n.js';

export const MOOD = { calm: 'Calmo', tense: 'Tenso', mysterious: 'Misterioso', epic: 'Épico', melancholic: 'Melancólico', joyful: 'Alegre' };
export const AMB = { wind: 'Vento', forest: 'Floresta', rain: 'Chuva', ocean: 'Oceano', city: 'Cidade', cave: 'Caverna', desert: 'Deserto', night: 'Noite', none: 'Nenhum' };
const warnText = (s) => (s === 'warn' ? ' · ' + t('usou o gerador de regras (resposta inválida do modelo)') : '');
export const GENRE_LABEL = { visual_novel: 'Visual Novel', rpg: 'RPG 2D', platformer: 'Plataforma', side_scroller: 'Side scroller', point_and_click: 'Point & click' };

export const WORLD = {
  steps: {
    attachments: ['Anexos', 'Lê textos, planilhas, imagens, áudios e vídeos'],
    analyst: ['Analista', 'Entende o pedido e extrai ideias dos anexos'],
    planner: ['Planejador', 'Desenha o mapa, os pontos de interesse e o orçamento de hardware'],
    characters: ['Personagens', 'Cria os agentes de IA (cards) que vão viver no mundo'],
    architect: ['Arquiteto do mundo', 'Monta terreno, estruturas, clima e NPCs'],
    sound_ux: ['Som e interface', 'Define trilha, ambiente sonoro e a interface do jogo'],
    reviewer: ['Revisor', 'Critica o resultado e pede correções, se preciso'],
    package: ['Empacotamento', 'Gera a pasta/ZIP do jogo e salva na biblioteca'],
  },
  detail(id, s, d) {
    d = d || {};
    if (s === 'running') return d.revision ? t('revisando…') : t('trabalhando…');
    if (s === 'error') return d.message || '';
    const warn = warnText(s);
    switch (id) {
      case 'attachments': return s === 'skipped' ? t('Sem anexos') : t('{n} arquivo(s)', { n: d.count }) + (d.images ? ' · ' + t('{n} imagem(ns) para visão', { n: d.images }) : '');
      case 'analyst': return d.title ? '“' + d.title + '”' + warn : warn.slice(3);
      case 'planner': return t('{n} pontos de interesse', { n: d.landmarks || 0 }) + warn;
      case 'characters': return s === 'skipped' ? t('Usando os personagens existentes') : t('{n} personagem(ns) criado(s)', { n: d.count }) + warn;
      case 'architect': return t('{a} estruturas · {b} NPCs', { a: d.structures, b: d.npcs }) + warn;
      case 'sound_ux': return t('música {m} · ambiente {a}', { m: t(MOOD[d.music] || d.music).toLowerCase(), a: t(AMB[d.ambience] || d.ambience).toLowerCase() }) + warn;
      case 'reviewer': return (d.approved ? t('aprovado') : t('com ressalvas')) + (d.score != null ? ' · ' + t('nota {n}/10', { n: d.score }) : '') + (d.issues ? ' · ' + t('{n} apontamentos', { n: d.issues }) : '') + warn;
      case 'package': return t('versão {n} salva', { n: d.version });
      default: return '';
    }
  },
};

export const AVATAR = {
  steps: {
    attachments: ['Anexos', 'Lê textos, planilhas, imagens, áudios e vídeos'],
    analyst: ['Analista', 'Entende quem você quer criar e extrai ideias dos anexos'],
    designer: ['Designer de avatares', 'Escreve personalidade, voz, aparência e primeira mensagem'],
    reviewer: ['Revisor', 'Confere idade adulta, conteúdo SFW/NSFW e coerência'],
    prompts: ['System prompts', 'Pipeline por avatar: analisa, gera, revisa e entrega o system prompt'],
    save: ['Salvando', 'Guarda os avatares na sua coleção'],
  },
  detail(id, s, d) {
    d = d || {};
    if (s === 'running') return d.revision ? t('revisando…') : t('trabalhando…');
    if (s === 'error') return d.message || '';
    const warn = warnText(s);
    switch (id) {
      case 'attachments': return s === 'skipped' ? t('Sem anexos') : t('{n} arquivo(s)', { n: d.count }) + (d.images ? ' · ' + t('{n} imagem(ns) para visão', { n: d.images }) : '');
      case 'analyst': return (d.names && d.names.length ? d.names.join(', ') : t('{n} avatar(es)', { n: d.count })) + warn;
      case 'designer': return t('{n} avatar(es)', { n: d.count }) + warn;
      case 'reviewer': return (d.approved ? t('aprovado') : t('com ressalvas')) + (d.score != null ? ' · ' + t('nota {n}/10', { n: d.score }) : '') + (d.issues ? ' · ' + t('{n} apontamentos', { n: d.issues }) : '') + warn;
      case 'prompts': return s === 'skipped' ? t('Desligado') : d.current ? t('{c} ({i}/{n})', { c: d.current, i: d.index, n: d.total }) : d.count != null ? t('{n} avatar(es)', { n: d.count }) + (d.revised ? ' · ' + t('{n} corrigido(s)', { n: d.revised }) : '') + warn : '';
      case 'save': return t('{n} avatar(es)', { n: d.count });
      default: return '';
    }
  },
};

export const GAME = {
  steps: {
    attachments: ['Anexos', 'Lê textos, planilhas, imagens, áudios e vídeos'],
    analyst: ['Analista de jogo', 'Escolhe o gênero e entende a ideia'],
    designer: ['Game designer', 'Escreve o jogo como dados: roteiro, mapas, fases, enigmas'],
    reviewer: ['Revisor', 'Confere se dá para jogar do início ao fim'],
    package: ['Empacotamento', 'Monta o ZIP do jogo e salva na biblioteca'],
  },
  detail(id, s, d) {
    d = d || {};
    if (s === 'running') return d.revision ? t('revisando…') : t('trabalhando…');
    if (s === 'error') return d.message || '';
    const warn = warnText(s);
    switch (id) {
      case 'attachments': return s === 'skipped' ? t('Sem anexos') : t('{n} arquivo(s)', { n: d.count }) + (d.images ? ' · ' + t('{n} imagem(ns) para visão', { n: d.images }) : '');
      case 'analyst': return (GENRE_LABEL[d.genre] || d.genre || '') + (d.title ? ' · “' + d.title + '”' : '') + warn;
      case 'designer': return (GENRE_LABEL[d.genre] || '') + warn;
      case 'reviewer': return (d.approved ? t('aprovado') : t('com ressalvas')) + (d.score != null ? ' · ' + t('nota {n}/10', { n: d.score }) : '') + (d.issues ? ' · ' + t('{n} apontamentos', { n: d.issues }) : '') + warn;
      case 'package': return t('versão {n} salva', { n: d.version });
      default: return '';
    }
  },
};

export const KINDS = { world: WORLD, avatar: AVATAR, game: GAME };
