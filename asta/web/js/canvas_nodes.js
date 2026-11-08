// Canvas: tipos de nó na interface (paleta, controles de cada nó e área de resultado) e regras de compatibilidade das portas.
import { t } from './i18n.js';
import { withMentions } from './canvas_mention.js';
import { checkbox, h, icon, seg, select } from './ui.js';

export const compatible = (out, accepts) => accepts.includes(out)
  || (out === 'media' && accepts.some((a) => ['image', 'video', 'audio', 'media'].includes(a)))
  || (['image', 'video', 'audio'].includes(out) && accepts.includes('media'));

export const GROUPS = [   // espelha schema.PALETTE
  ['Texto', ['text', 'llm', 'transcribe', 'text_template', 'text_join', 'text_edit', 'text_pick', 'text_refine']],
  ['Imagem', ['image', 'img_resize', 'img_filter', 'img_text', 'img_collage', 'img_frame']],
  ['Vídeo', ['video', 'vid_trim', 'vid_join', 'vid_speed', 'vid_look', 'vid_slideshow']],
  ['Som', ['sound', 'voice', 'aud_trim', 'aud_mix', 'aud_fx', 'aud_from_video', 'aud_loop']],
  ['Input', ['upload', 'style_prompt', 'style_folder', 'in_color', 'in_silence', 'in_url', 'in_random', 'in_vars']],
  ['Output', ['editor', 'out_export', 'out_gif', 'out_audio', 'out_image', 'out_gallery']],
];
export const TYPE_HELP = {
  text: 'Um texto que você escreve (prompt, roteiro, fala).', llm: 'Reescreve ou cria texto com o modelo de IA configurado.',
  upload: 'Seus arquivos de imagem, vídeo ou áudio.', image: 'Gera ou edita imagens.', video: 'Gera vídeos (de texto ou a partir de uma imagem).',
  sound: 'Gera efeitos sonoros ou música.', voice: 'Transforma texto em fala.', transcribe: 'Transforma áudio ou vídeo em texto.',
  style_prompt: 'Um prompt de sistema de estilo que vale para o projeto todo.', style_folder: 'Imagens, vídeos e áudios de referência de estilo para o projeto todo.',
  editor: 'Editor de vídeo: monta tudo numa linha do tempo e exporta um MP4.',
  text_template: 'Monta um texto a partir de um modelo, usando {1}, {2}… para os textos ligados.', text_join: 'Junta vários textos em um só (com separador, numeração, prefixo e sufixo).',
  text_edit: 'Maiúsculas, minúsculas, limpar espaços, ordenar, numerar linhas, trocar palavras…', text_pick: 'Escolhe uma linha, frase, parágrafo ou palavra de um texto (ou sorteia).',
  text_refine: 'Com o modelo de texto: melhora o prompt, traduz, resume, expande, corrige, divide em cenas ou em legendas.',
  img_resize: 'Muda o tamanho (encaixar, preencher, esticar), gira e espelha uma imagem — ou o quadro de um vídeo.', img_filter: 'Filtros de cor (P&B, sépia, vívido, VHS…) e ajustes de brilho, contraste e saturação.',
  img_text: 'Escreve um texto (ou o texto de outro nó) sobre a imagem.', img_collage: 'Junta várias imagens numa colagem em grade.', img_frame: 'Tira um ou mais quadros de um vídeo como imagens.',
  vid_trim: 'Corta um trecho do vídeo (início e duração).', vid_join: 'Junta vídeos e imagens em sequência, com transições suaves.', vid_speed: 'Acelera, desacelera ou toca o vídeo ao contrário.',
  vid_look: 'Dá um visual ao vídeo (cinema, VHS, P&B…) com fade de entrada e saída.', vid_slideshow: 'Transforma imagens em um vídeo com zoom suave e música.',
  aud_trim: 'Corta um trecho do áudio (ou do som de um vídeo), com fades.', aud_mix: 'Mistura vários áudios (juntos) ou toca um depois do outro.', aud_fx: 'Efeitos: volume, velocidade, reverso, eco, telefone, graves, normalizar.',
  aud_from_video: 'Extrai o áudio de um vídeo.', aud_loop: 'Repete um áudio até chegar a uma duração, com fade no final.',
  in_color: 'Gera uma imagem de cor lisa ou degradê, no tamanho que você quiser.', in_silence: 'Gera um trecho de silêncio (para espaçar áudios).', in_url: 'Baixa uma imagem, um vídeo ou um áudio de um link público.',
  in_random: 'Sorteia linhas de uma lista (variações de prompt, ideias).', in_vars: 'Texto com a data, a hora e o nome do projeto.',
  out_export: 'Monta o vídeo final: vídeo (ou imagem) + áudios + legendas, na qualidade escolhida.', out_gif: 'Transforma um vídeo em GIF animado.', out_audio: 'Junta e exporta o áudio final (MP3, WAV ou M4A), normalizado.',
  out_image: 'Exporta a imagem final (PNG, JPG ou WebP) com qualidade e largura máxima.', out_gallery: 'Reúne imagens, vídeos, áudios e textos de vários nós num lugar só para ver e baixar.',
};
export const OUT_COLOR = { text: 'var(--c-text)', image: 'var(--c-image)', video: 'var(--c-video)', audio: 'var(--c-audio)', style: 'var(--c-style)', media: 'var(--c-media)' };
export const LABEL = {
  text: 'Texto', llm: 'Texto IA', upload: 'Mídia', image: 'Imagem', video: 'Vídeo', sound: 'Som', voice: 'Voz', transcribe: 'Transcrever',
  style_prompt: 'Style Prompt', style_folder: 'Style Folder', editor: 'Editor',
  text_template: 'Modelo de texto', text_join: 'Juntar textos', text_edit: 'Editar texto', text_pick: 'Escolher trecho', text_refine: 'Refinar com IA',
  img_resize: 'Redimensionar', img_filter: 'Filtros e cor', img_text: 'Texto na imagem', img_collage: 'Colagem', img_frame: 'Quadro do vídeo',
  vid_trim: 'Cortar vídeo', vid_join: 'Juntar clipes', vid_speed: 'Velocidade', vid_look: 'Visual do vídeo', vid_slideshow: 'Imagens em vídeo',
  aud_trim: 'Cortar áudio', aud_mix: 'Misturar áudios', aud_fx: 'Efeitos de áudio', aud_from_video: 'Áudio do vídeo', aud_loop: 'Repetir áudio',
  in_color: 'Cor e degradê', in_silence: 'Silêncio', in_url: 'Link (URL)', in_random: 'Sorteio de texto', in_vars: 'Data e projeto',
  out_export: 'Vídeo final', out_gif: 'GIF animado', out_audio: 'Áudio final', out_image: 'Imagem final', out_gallery: 'Galeria',
};
const CAP = { image: 'image', video: 'video', sound: 'sound', voice: 'voice', transcribe: 'stt' };
const PORT_LABEL = { prompt: 'Prompt', refs: 'Referências', style: 'Estilo', image: 'Imagem inicial', text: 'Fala', audio: 'Áudio/vídeo', clips: 'Clipes', vars: 'Variáveis', texts: 'Textos', images: 'Imagens', video: 'Vídeo', audios: 'Áudios', items: 'Itens', captions: 'Legendas' };
const NEW_PORT = { img_resize: { image: 'Imagem' }, img_filter: { image: 'Imagem' }, img_text: { image: 'Imagem', text: 'Texto' }, text_edit: { text: 'Texto' }, text_pick: { text: 'Texto' }, text_refine: { text: 'Texto' }, vid_slideshow: { audio: 'Áudio' }, aud_trim: { audio: 'Áudio' }, aud_fx: { audio: 'Áudio' }, aud_loop: { audio: 'Áudio' }, out_export: { audio: 'Áudio', video: 'Vídeo' }, out_audio: { audio: 'Áudio' }, out_image: { image: 'Imagem' } };
export const portLabel = (nodeType, p) => (nodeType === 'llm' && p.id === 'prompt' ? t('Entrada') : t((NEW_PORT[nodeType] && NEW_PORT[nodeType][p.id]) || PORT_LABEL[p.id] || p.label));

// ---------------------------------------------------------------------------------------------------- controles
const cut = (e) => e.stopPropagation();
function ta(c, n, key, ph, rows, mention) {
  const el = h('textarea', { placeholder: ph, rows: rows || 3, class: 'nodrag' });
  el.value = n.params[key] || '';
  el.addEventListener('input', () => c.change(n, key, el.value));
  el.addEventListener('keydown', cut);
  return mention && c.mentions ? withMentions(el, c) : el;   // @ cita uma imagem do canvas (Imagem e Vídeo)
}
function txt(c, n, key, ph, type) {
  const el = h('input', { type: type || 'text', placeholder: ph || '', class: 'nodrag' });
  el.value = n.params[key] ?? '';
  el.addEventListener('input', () => c.change(n, key, type === 'number' ? Number(el.value) : el.value));
  el.addEventListener('keydown', cut);
  return el;
}
const lab = (text, ctl) => h('div', null, h('label', { class: 'f' }, text), ctl);

// Provedor + Modelo (+ Resolução, quando o tipo tem). v0.17.1: o antigo bloco «Avançado» (prompt negativo, semente, parâmetros extras em JSON, ignorar estilos) saiu da tela;
// o que já estava salvo nos canvases continua valendo no motor.
const ratio = (w, h) => { const g = (a, b) => (b ? g(b, a % b) : a), d = g(w, h); return (w / d) + ':' + (h / d); };
export const sizeLabel = (s) => { const [w, h] = s.split('x').map(Number); return `${w}×${h} (${ratio(w, h)})`; };
function providerBlock(c, n, cap, resolutionField) {
  const provs = c.prov.providers.filter((p) => p.caps.includes(cap));
  const defId = c.prov.active[cap] || 'demo';
  const def = c.prov.providers.find((p) => p.id === defId);
  const eff = c.prov.providers.find((p) => p.id === (n.params.provider || defId)) || def;
  const sel = select([['', t('Padrão') + (def ? ' · ' + t(def.label) : '')], ...provs.map((p) => [p.id, t(p.label)])], n.params.provider || '', (v) => c.change(n, 'provider', v, true));
  sel.classList.add('nodrag');
  const listId = 'dl_' + n.id + cap;
  const model = txt(c, n, 'model', (eff && eff.models && eff.models[cap]) || t('modelo padrão'));
  model.setAttribute('list', listId);
  const dl = h('datalist', { id: listId }, ((eff && eff.suggest && eff.suggest[cap]) || []).map((m) => h('option', { value: m })));
  const warn = eff && eff.needs_key && !eff.has_key
    ? h('div', { class: 'warnk' }, icon('warn', 13), t('Sem chave de API:'), h('a', { href: '#/config', onclick: () => c.openConfig() }, t('configurar')))
    : (eff && eff.id === 'demo' ? h('div', { class: 'dim small' }, t('Demo: resultado simples, sem IA real.')) : null);
  return [lab(t('Provedor'), sel), warn, lab(t('Modelo'), model), dl, resolutionField || null];
}

function fileThumbs(c, n) {
  const files = (n.params.files || []).map((id) => c.asset(id)).filter(Boolean);
  const box = h('div', { class: 'thumbs' }, files.map((a) => {
    const pv = a.kind === 'image' ? h('img', { src: c.url(a), loading: 'lazy', draggable: 'false' })
      : a.kind === 'video' ? h('video', { src: c.url(a) + '#t=0.1', preload: 'metadata', muted: true })
        : h('div', null, icon('audio', 20));
    return h('div', { class: 'thumb nodrag', title: a.name, onclick: () => c.preview(a) }, pv, h('div', { class: 'nm' }, a.name),
      h('span', { class: 'x', onclick: (e) => { e.stopPropagation(); c.change(n, 'files', n.params.files.filter((f) => f !== a.id), true); } }, '×'));
  }));
  const input = h('input', { type: 'file', multiple: true, accept: 'image/*,video/*,audio/*', class: 'hidden', onchange: (e) => { c.uploadTo(n, [...e.target.files]); e.target.value = ''; } });
  return [files.length ? box : h('div', { class: 'dim small' }, t('Arraste arquivos aqui ou use o botão.')),
    h('button', { class: 'btn sm nodrag', onclick: () => input.click() }, icon('upload', 13), t('Adicionar arquivos')), input];
}

const BODY = {
  text: (c, n) => [ta(c, n, 'text', t('Escreva o texto…'), 4)],
  llm: (c, n) => [ta(c, n, 'instruction', t('O que fazer com o texto de entrada? Ex.: “Descreva a cena com detalhes visuais”.'), 3),
    h('div', { class: 'dim small' }, t('Usa o modelo de texto ativo em Configuração → Provedores.')),
    checkbox(t('Ignorar estilos globais'), n.params.ignore_global_styles, (v) => c.change(n, 'ignore_global_styles', v, true))],
  upload: (c, n) => fileThumbs(c, n),
  image: (c, n) => [
    seg([['generate', t('Gerar')], ['edit', t('Editar')]], n.params.mode, (v) => c.change(n, 'mode', v, true)),
    ta(c, n, 'prompt', n.params.mode === 'edit' ? t('O que mudar na imagem ligada em “Referências” (ou citada com @)?') : t('Descreva a imagem (ou ligue um nó de texto). Digite @ para citar uma imagem do canvas.'), 3, true),
    lab(t('Quantidade'), select([1, 2, 3, 4].map((i) => [String(i), String(i)]), String(n.params.count), (v) => c.change(n, 'count', Number(v)))),
    ...providerBlock(c, n, 'image', lab(t('Resolução'), select(c.meta.sizes.map((s) => [s, sizeLabel(s)]), n.params.size, (v) => c.change(n, 'size', v))))],
  video: (c, n) => [
    ta(c, n, 'prompt', t('Descreva o vídeo (ou ligue um texto e/ou uma imagem inicial). Digite @ para citar a imagem inicial.'), 3, true),
    h('div', { class: 'r2' }, lab(t('Duração (s)'), txt(c, n, 'duration', '5', 'number')), lab(t('Proporção'), select(c.meta.aspects.map((a) => [a, a]), n.params.aspect, (v) => c.change(n, 'aspect', v)))),
    ...providerBlock(c, n, 'video', lab(t('Resolução'), select((c.meta.resolutions || [0]).map((r) => [String(r), r ? r + 'p' : t('Automática')]), String(n.params.resolution || 0), (v) => c.change(n, 'resolution', Number(v)))))],
  sound: (c, n) => [
    seg([['sfx', t('Efeito')], ['music', t('Música')]], n.params.kind, (v) => c.change(n, 'kind', v, true)),
    ta(c, n, 'prompt', n.params.kind === 'music' ? t('Estilo da música: calma, piano, noturna…') : t('Ex.: chuva forte com trovões'), 2),
    lab(t('Duração (s)'), txt(c, n, 'duration', '5', 'number')),
    ...providerBlock(c, n, 'sound')],
  voice: (c, n) => [
    ta(c, n, 'text', t('O que a voz vai dizer (ou ligue um nó de texto)…'), 3),
    h('div', { class: 'r2' }, lab(t('Voz'), txt(c, n, 'voice', t('padrão'))), lab(t('Velocidade'), txt(c, n, 'speed', '1', 'number'))),
    ...providerBlock(c, n, 'voice')],
  transcribe: (c, n) => [h('div', { class: 'dim small' }, t('Ligue um áudio ou vídeo na entrada.')), lab(t('Idioma (opcional)'), txt(c, n, 'language', 'pt, en…')), ...providerBlock(c, n, 'stt')],
  style_prompt: (c, n) => [ta(c, n, 'text', t('Ex.: ilustração em aquarela, cores suaves, traço delicado.'), 4), globalCheck(c, n)],
  style_folder: (c, n) => [...fileThumbs(c, n), globalCheck(c, n),
    n.result.digest ? h('div', { class: 'digest nodrag' }, n.result.digest) : null,
    (n.params.files || []).length ? h('button', { class: 'btn sm nodrag', onclick: () => c.run([n.id], true) }, icon('refresh', 13), t('Analisar estilo')) : null],
  editor: (c, n) => {
    const tl = n.params.timeline;
    return [h('div', { class: 'small muted' }, t('{n} clipe(s) · {s}s', { n: tl.clips.length, s: (tl.duration || 0).toFixed(1) }) + ' · ' + n.params.width + '×' + n.params.height),
      h('button', { class: 'btn sm primary nodrag', onclick: () => c.openTimeline(n) }, icon('film', 13), t('Abrir editor')),
      h('div', { class: 'dim small' }, t('Ligue nós em “Clipes” para usar as saídas deles na linha do tempo.'))];
  },
};
function globalCheck(c, n) {
  return h('div', null, checkbox(t('Vale para o projeto todo'), n.params.global, (v) => c.change(n, 'global', v, true)),
    h('div', { class: 'dim small' }, n.params.global ? t('Aplicado automaticamente a todos os nós de geração.') : t('Aplicado só aos nós ligados em “Estilo”.')));
}


// ---------------------------------------------------------------------------------------------------- nós novos (v0.11): formulários por tabela
const sel = (c, n, key, options) => { const el = select(options.map(([v, l]) => [String(v), l]), String(n.params[key]), (v) => c.change(n, key, typeof options[0][0] === 'number' ? Number(v) : v, true)); el.classList.add('nodrag'); return el; };
const colorIn = (c, n, key) => { const el = h('input', { type: 'color', class: 'nodrag', value: n.params[key] || '#000000' }); el.addEventListener('input', () => c.change(n, key, el.value)); return el; };
const FILTERS = [['none', 'Nenhum'], ['bw', 'Preto e branco'], ['sepia', 'Sépia'], ['vivid', 'Vívido'], ['warm', 'Quente'], ['cool', 'Frio'], ['cinematic', 'Cinema'], ['vhs', 'VHS'], ['phonk', 'Phonk'], ['blur', 'Desfoque'], ['sharpen', 'Nitidez'], ['vignette', 'Vinheta'], ['invert', 'Inverter']];
const SIZE_NUM = (k, ph) => ['num', k, ph];
// cada campo: [tipo, chave, rótulo, opções|placeholder]; tipos: ta, txt, num, sel, chk, color
const FORMS = {
  text_template: [['ta', 'template', 'Modelo', 'Ex.: Cena: {1}. Estilo: {2}. Tudo: {todos}', 4], ['hint', 'Use {1}, {2}… para os textos ligados em «Variáveis», {todos} para todos juntos.']],
  text_join: [['sel', 'sep', 'Separador', [['paragraph', 'Parágrafo'], ['line', 'Linha'], ['space', 'Espaço'], ['comma', 'Vírgula'], ['dash', 'Traço'], ['custom', 'Personalizado']]], ['txt', 'custom', 'Separador personalizado', ' | '], ['chk', 'numbering', 'Numerar os textos'], ['txt', 'prefix', 'Antes', ''], ['txt', 'suffix', 'Depois', '']],
  text_edit: [['sel', 'op', 'O que fazer', [['trim', 'Limpar espaços'], ['upper', 'MAIÚSCULAS'], ['lower', 'minúsculas'], ['title', 'Cada Palavra Maiúscula'], ['dedupe', 'Tirar linhas repetidas'], ['sort', 'Ordenar linhas'], ['reverse', 'Inverter linhas'], ['number', 'Numerar linhas'], ['no_empty', 'Tirar linhas vazias'], ['replace', 'Trocar palavra']]], ['txt', 'find', 'Procurar', ''], ['txt', 'replace', 'Trocar por', '']],
  text_pick: [['sel', 'mode', 'Pegar', [['lines', 'Linhas'], ['sentences', 'Frases'], ['paragraphs', 'Parágrafos'], ['words', 'Palavras']]], ['num', 'index', 'A partir do nº (0 = tudo)'], ['num', 'count', 'Quantos'], ['chk', 'random', 'Sortear'], ['num', 'seed', 'Semente (0 = aleatória)']],
  text_refine: [['sel', 'mode', 'Modo', [['improve', 'Melhorar prompt'], ['translate', 'Traduzir'], ['summarize', 'Resumir'], ['expand', 'Expandir'], ['fix', 'Corrigir'], ['scenes', 'Dividir em cenas'], ['captions', 'Fazer legendas']]], ['txt', 'language', 'Idioma (para traduzir)', 'inglês'], ['ta', 'instruction', 'Instrução extra (opcional)', '', 2], ['hint', 'Usa o modelo de texto ativo em Configuração → Provedores; sem IA, faz uma versão simples.']],
  img_resize: [['num', 'width', 'Largura (0 = automática)'], ['num', 'height', 'Altura (0 = automática)'], ['sel', 'mode', 'Encaixe', [['fit', 'Encaixar'], ['cover', 'Preencher e cortar'], ['stretch', 'Esticar'], ['pad', 'Encaixar com borda']]], ['sel', 'rotate', 'Girar', [[0, 'Não girar'], [90, '90°'], [180, '180°'], [270, '270°']]], ['sel', 'flip', 'Espelhar', [['none', 'Não'], ['h', 'Horizontal'], ['v', 'Vertical'], ['both', 'Os dois']]], ['color', 'bg', 'Cor da borda'], ['sel', 'format', 'Formato', [['png', 'PNG'], ['jpg', 'JPG']]]],
  img_filter: [['sel', 'preset', 'Filtro', FILTERS], ['range', 'brightness', 'Brilho', -1, 1, 0.05], ['range', 'contrast', 'Contraste', 0, 3, 0.05], ['range', 'saturation', 'Saturação', 0, 3, 0.05]],
  img_text: [['ta', 'text', 'Texto (ou ligue um nó de texto)', 'Escreva o texto…', 2], ['sel', 'pos', 'Posição', [['top', 'Em cima'], ['center', 'No meio'], ['bottom', 'Embaixo']]], ['range', 'size', 'Tamanho (% da altura)', 1, 30, 1], ['color', 'color', 'Cor do texto'], ['chk', 'box', 'Faixa escura atrás']],
  img_collage: [['num', 'cols', 'Colunas'], ['num', 'cell', 'Tamanho de cada imagem (px)'], ['num', 'gap', 'Espaço (px)'], ['color', 'bg', 'Cor do fundo']],
  img_frame: [['sel', 'at', 'Quadro', [['first', 'O primeiro'], ['middle', 'O do meio'], ['last', 'O último'], ['seconds', 'Em um segundo exato']]], ['num', 'seconds', 'Segundo'], ['num', 'count', 'Quantos quadros (1 a 4, espaçados)']],
  vid_trim: [['num', 'start', 'Início (s)'], ['num', 'duration', 'Duração (s, 0 = até o fim)']],
  vid_join: [['num', 'width', 'Largura'], ['num', 'height', 'Altura'], ['num', 'fps', 'Quadros por segundo'], ['num', 'image_seconds', 'Segundos por imagem'], ['range', 'fade', 'Transição (s)', 0, 2, 0.05], ['color', 'bg', 'Cor do fundo']],
  vid_speed: [['range', 'factor', 'Velocidade (×)', 0.25, 4, 0.05], ['chk', 'reverse', 'Tocar ao contrário']],
  vid_look: [['sel', 'preset', 'Visual', FILTERS], ['num', 'fade_in', 'Fade de entrada (s)'], ['num', 'fade_out', 'Fade de saída (s)']],
  vid_slideshow: [['num', 'seconds', 'Segundos por imagem'], ['num', 'width', 'Largura'], ['num', 'height', 'Altura'], ['chk', 'zoom', 'Zoom suave'], ['range', 'fade', 'Transição (s)', 0, 2, 0.05], ['range', 'music_volume', 'Volume da música', 0, 2, 0.05]],
  aud_trim: [['num', 'start', 'Início (s)'], ['num', 'duration', 'Duração (s, 0 = até o fim)'], ['num', 'fade_in', 'Fade de entrada (s)'], ['num', 'fade_out', 'Fade de saída (s)']],
  aud_mix: [['sel', 'mode', 'Como juntar', [['mix', 'Ao mesmo tempo'], ['sequence', 'Um depois do outro']]], ['range', 'volume', 'Volume', 0, 2, 0.05]],
  aud_fx: [['sel', 'fx', 'Efeito', [['normalize', 'Normalizar volume'], ['louder', 'Mais alto'], ['quieter', 'Mais baixo'], ['faster', 'Mais rápido'], ['slower', 'Mais lento'], ['reverse', 'Ao contrário'], ['echo', 'Eco'], ['telephone', 'Telefone'], ['bass', 'Mais graves'], ['none', 'Nenhum']]], ['range', 'amount', 'Intensidade', 0.1, 4, 0.1]],
  aud_from_video: [['sel', 'format', 'Formato', [['mp3', 'MP3'], ['wav', 'WAV'], ['m4a', 'M4A']]]],
  aud_loop: [['num', 'duration', 'Duração final (s)'], ['num', 'fade_out', 'Fade no final (s)']],
  in_color: [['color', 'color', 'Cor'], ['sel', 'gradient', 'Degradê', [['none', 'Cor lisa'], ['vertical', 'Vertical'], ['horizontal', 'Horizontal'], ['diagonal', 'Diagonal']]], ['color', 'color2', 'Segunda cor'], ['num', 'width', 'Largura'], ['num', 'height', 'Altura']],
  in_silence: [['num', 'seconds', 'Duração (s)']],
  in_url: [['txt', 'url', 'Endereço (https://…)', 'https://exemplo.com/foto.jpg'], ['hint', 'Só links públicos de imagem, vídeo ou áudio (até 60 MB).']],
  in_random: [['ta', 'lines', 'Uma ideia por linha', '', 5], ['num', 'count', 'Quantas sortear'], ['sel', 'joiner', 'Juntar com', [['line', 'Linhas'], ['comma', 'Vírgulas'], ['space', 'Espaços']]], ['num', 'seed', 'Semente (0 = aleatória)']],
  in_vars: [['ta', 'template', 'Texto', '{data} {hora} · {projeto}', 2], ['hint', 'Variáveis: {data}, {hora}, {ano}, {projeto}, {nos}, {arquivos}, {aleatorio}.']],
  out_export: [['sel', 'quality', 'Qualidade', [['480p', '480p'], ['720p', '720p'], ['1080p', '1080p']]], ['chk', 'burn', 'Gravar as legendas no vídeo'], ['range', 'music_volume', 'Volume dos áudios sobre o som do vídeo', 0, 2, 0.05], ['num', 'image_seconds', 'Segundos (se a entrada for uma imagem)'], ['num', 'fps', 'Quadros por segundo']],
  out_gif: [['num', 'width', 'Largura (px)'], ['num', 'fps', 'Quadros por segundo'], ['num', 'max_seconds', 'Duração máxima (s)']],
  out_audio: [['sel', 'format', 'Formato', [['mp3', 'MP3'], ['wav', 'WAV'], ['m4a', 'M4A']]], ['sel', 'mode', 'Como juntar', [['sequence', 'Um depois do outro'], ['mix', 'Ao mesmo tempo']]], ['chk', 'normalize', 'Normalizar o volume']],
  out_image: [['sel', 'format', 'Formato', [['png', 'PNG'], ['jpg', 'JPG'], ['webp', 'WebP']]], ['range', 'quality', 'Qualidade', 10, 100, 1], ['num', 'max_width', 'Largura máxima (px, 0 = original)']],
  out_gallery: [['hint', 'Ligue em «Itens» imagens, vídeos, áudios e textos de qualquer nó: eles aparecem aqui para ver e baixar.']],
};
function formBody(c, n) {
  return (FORMS[n.type] || []).map(([kind, key, label, a, b, step]) => {
    if (kind === 'hint') return h('div', { class: 'dim small' }, t(key));
    if (kind === 'ta') return lab(t(label), ta(c, n, key, t(a), b));
    if (kind === 'txt') return lab(t(label), txt(c, n, key, a));
    if (kind === 'num') return lab(t(label), txt(c, n, key, '', 'number'));
    if (kind === 'sel') return lab(t(label), sel(c, n, key, a.map(([v, l]) => [v, t(l)])));
    if (kind === 'chk') return checkbox(t(label), !!n.params[key], (v) => c.change(n, key, v, true));
    if (kind === 'color') return lab(t(label), colorIn(c, n, key));
    if (kind === 'range') { const el = h('input', { type: 'range', class: 'nodrag', min: a, max: b, step, value: n.params[key] }); const out = h('span', { class: 'dim small' }, String(n.params[key])); el.addEventListener('input', () => { out.textContent = el.value; c.change(n, key, Number(el.value)); }); return lab(t(label), h('div', { class: 'row nw' }, el, out)); }
    return null;
  });
}

export const nodeBody = (c, n) => h('div', { class: 'bd' }, BODY[n.type] ? BODY[n.type](c, n) : (FORMS[n.type] ? formBody(c, n) : null));
export const capOf = (type) => CAP[type] || '';

// ---------------------------------------------------------------------------------------------------- resultado
export function nodeResult(c, n) {
  const st = c.state(n.id), r = n.result;
  const box = h('div', { class: 'res' });
  const items = (r.assets || []).map((id) => c.asset(id)).filter(Boolean);
  if (st.state === 'running') box.append(h('div', { class: 'run' }, h('div', { class: 'spinner' }), st.note || t('Gerando…')));
  else if (st.state === 'queued') box.append(h('div', { class: 'run' }, t('Na fila…')));
  else if (st.state === 'skipped') box.append(h('div', { class: 'dim small' }, t('Pulado: um nó de entrada falhou.')));
  const error = st.state === 'error' ? st.message : (r.state === 'error' ? r.error : '');
  if (error) {
    box.append(h('div', { class: 'err' }, error));
    if (/ainda não foi baixado|not been downloaded/i.test(error)) box.append(h('button', { class: 'btn sm primary nodrag', type: 'button', style: { marginTop: '6px' }, onclick: () => window.dispatchEvent(new CustomEvent('asta:go', { detail: { route: 'config', ctx: { tab: 'media' } } })) }, icon('download', 13), t('Baixar o modelo agora')));   // abre Configuração → Mídia na escolha da precisão
  }
  if (st.state === 'running' || st.state === 'queued') return box;
  const imgs = items.filter((a) => a.kind === 'image');
  if (imgs.length) box.append(h('div', { class: 'rimgs nodrag' + (imgs.length === 1 ? ' one' : '') }, imgs.map((a) => h('img', { src: c.url(a), loading: 'lazy', title: a.prompt || a.name, draggable: 'false', onclick: () => c.preview(a, imgs) }))));
  items.filter((a) => a.kind === 'video').forEach((a) => box.append(h('video', { src: c.url(a), controls: true, preload: 'metadata', class: 'nodrag' })));
  items.filter((a) => a.kind === 'audio').forEach((a) => box.append(h('audio', { src: c.url(a), controls: true, preload: 'metadata', class: 'nodrag' })));
  if (r.text && !['text', 'style_prompt'].includes(n.type) && !(st.state === 'error')) box.append(h('div', { class: 'rtxt nodrag' }, r.text));
  (st.warnings || []).forEach((w) => box.append(h('div', { class: 'wr' }, w)));
  if (items.length) box.append(h('div', { class: 'dim small', style: { marginTop: '6px' } }, items.map((a) => (a.provider ? t(c.providerLabel(a.provider)) : '') + (a.model ? ' · ' + a.model : '')).filter(Boolean)[0] || ''));
  return box.childNodes.length ? box : null;
}
