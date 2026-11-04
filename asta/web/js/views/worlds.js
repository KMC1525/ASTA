import { api } from '../api.js';
import { t } from '../i18n.js';
import { go, state } from '../main.js';
import { accordion, checkbox, field, fmtDate, gradient, h, icon, range, select, seg, toast } from '../ui.js';
import { figureSVG } from './characters.js';

const BIOMES = [['temperate', 'Temperado'], ['forest', 'Floresta'], ['desert', 'Deserto'], ['snow', 'Neve'], ['tropical', 'Tropical'], ['island', 'Ilha'], ['urban', 'Urbano'], ['wasteland', 'Pós-apocalipse'], ['swamp', 'Pântano'], ['mountain', 'Montanha']];
const WEATHER = [['clear', 'Limpo'], ['cloudy', 'Nublado'], ['fog', 'Névoa'], ['rain', 'Chuva'], ['snow', 'Neve'], ['storm', 'Tempestade']];
const AMBIENCE = [['wind', 'Vento'], ['forest', 'Floresta'], ['rain', 'Chuva'], ['ocean', 'Oceano'], ['city', 'Cidade'], ['cave', 'Caverna'], ['desert', 'Deserto'], ['night', 'Noite'], ['none', 'Nenhum']];
const MOODS = [['calm', 'Calmo'], ['tense', 'Tenso'], ['mysterious', 'Misterioso'], ['epic', 'Épico'], ['melancholic', 'Melancólico'], ['joyful', 'Alegre']];
const SCALES = [['major', 'Maior'], ['minor', 'Menor'], ['dorian', 'Dórica'], ['phrygian', 'Frígia'], ['pentatonic', 'Pentatônica'], ['lydian', 'Lídia']];
const BEHAV = [['wander', 'Vagar'], ['idle', 'Parado'], ['patrol', 'Patrulhar'], ['stand', 'Em pé']];
const tr = (arr) => arr.map(([v, l]) => [v, t(l)]);

export default async function render(root, ctx) {
  const projects = await api('/api/projects');
  const libChars = await api('/api/characters');
  let sel = ctx.select || (projects[0] && projects[0].id) || null, proj = null, w = null, swaps = {};
  const listEl = h('div', { class: 'list' }), editor = h('div');

  async function load(id) {
    sel = id; swaps = {};
    proj = id ? await api('/api/projects/' + id) : null;
    w = proj && proj.world ? JSON.parse(JSON.stringify(proj.world)) : null;
    paintList(); paintEditor();
  }
  function paintList() {
    listEl.replaceChildren(...(projects.length ? projects.map((p) => h('div', { class: 'li' + (p.id === sel ? ' active' : ''), onclick: () => load(p.id) },
      h('div', { class: 'av', style: { background: gradient(p.palette), color: 'transparent' } }, '·'), h('div', { style: { minWidth: 0 } }, h('div', { class: 't' }, p.name), h('div', { class: 's' }, 'v' + p.current + ' · ' + fmtDate(p.updated))))) :
      [h('div', { class: 'muted small', style: { padding: '8px 12px' } }, t('Nenhum mundo gerado ainda.'))]));
  }

  async function save() {
    const patch = {
      title: w.title, description: w.description, perspective: w.perspective, realism: w.realism,
      environment: w.environment, audio: w.audio, ux: w.ux, gameplay: w.gameplay, quality: { target: w.quality.target },
      npcs: w.npcs.map((n) => ({ id: n.id, behavior: n.behavior, radius: n.radius })), characters: swaps,
      _summary: t('Ajustes manuais nas configurações do mundo.'),
    };
    try {
      await api('/api/projects/' + proj.id + '/edit', { method: 'POST', body: patch });
      toast(t('Nova versão salva'), 'ok');
      const list = await api('/api/projects'); projects.splice(0, projects.length, ...list);
      await load(proj.id);
    } catch (e) { toast(e.message, 'err'); }
  }

  function paintEditor() {
    if (!proj || !w) { editor.replaceChildren(h('div', { class: 'empty' }, h('h3', null, t('Nenhum mundo para configurar')), h('p', null, t('Gere um mundo na tela principal; depois você ajusta clima, hora, NPCs, áudio e qualidade aqui.')), h('button', { class: 'btn primary', onclick: () => go('main', { fresh: true }) }, icon('sparkle', 15), t('Criar um mundo')))); return; }
    const env = w.environment, au = w.audio, mu = au.music, ux = w.ux, hud = ux.hud;
    const tier = w.quality.target === 'auto' ? (state.hardware.tier || 'medium') : w.quality.target;
    const maxSize = (w.quality.tiers[tier] || {}).max_size || 800;
    const charName = (id) => (proj.characters.find((c) => c.id === id) || {}).name || id;
    const charOf = (id) => proj.characters.find((c) => c.id === id);

    const general = h('div', null,
      h('div', { class: 'grid2' }, field(t('Título'), h('input', { value: w.title, oninput: (e) => { w.title = e.target.value; } })), field(t('Perspectiva inicial'), seg([['first', t('1ª pessoa')], ['third', t('3ª pessoa')]], w.perspective, (v) => { w.perspective = v; }))),
      field(t('Descrição'), h('textarea', { rows: 3, oninput: (e) => { w.description = e.target.value; } }, w.description)),
      field(t('Realismo'), range(0, 1, 0.05, w.realism, (v) => { w.realism = v; }, (v) => Math.round(v * 100) + '%'), t('Mais realista = sombras/estilo suave; menos = visual estilizado. O jogo sempre respeita o hardware.')));
    const environment = h('div', null,
      h('div', { class: 'grid2' }, field(t('Bioma'), select(tr(BIOMES), env.biome, (v) => { env.biome = v; })), field(t('Clima'), select(tr(WEATHER), env.weather, (v) => { env.weather = v; }))),
      h('div', { class: 'grid2' }, field(t('Tamanho do mundo'), range(120, maxSize, 10, Math.min(env.size, maxSize), (v) => { env.size = v; }, (v) => v + ' m'), t('Limite para o seu hardware ({t}): {m} m', { t: tier, m: maxSize })),
        field(t('Relevo'), range(0, 1, 0.05, env.relief, (v) => { env.relief = v; }, (v) => Math.round(v * 100) + '%'))),
      h('div', { class: 'grid2' }, field(t('Hora inicial'), range(0, 24, 0.25, env.time_of_day, (v) => { env.time_of_day = v; }, (v) => String(Math.floor(v)).padStart(2, '0') + ':' + String(Math.round((v % 1) * 60)).padStart(2, '0'))),
        field(t('Duração do dia'), range(2, 60, 1, env.day_length_min, (v) => { env.day_length_min = v; }, (v) => v + ' min'))),
      h('div', { class: 'grid2' }, field(t('Vegetação'), range(0, 1, 0.05, env.vegetation, (v) => { env.vegetation = v; }, (v) => Math.round(v * 100) + '%')), field(t('Pedras'), range(0, 1, 0.05, env.rocks, (v) => { env.rocks = v; }, (v) => Math.round(v * 100) + '%'))),
      h('div', { class: 'row' }, checkbox(t('Ciclo dia/noite'), env.day_cycle, (v) => { env.day_cycle = v; }), checkbox(t('Água (lagos/mar)'), env.water, (v) => { env.water = v; })));
    const structs = w.structures.filter((s) => s.label);
    const worldAcc = h('div', null, h('div', { class: 'muted small', style: { marginBottom: '8px' } }, t('{a} estruturas · {b} NPCs', { a: w.structures.length, b: w.npcs.length }) + ' — ' + t('para mudar o layout, use “Atualizar com IA”.')),
      h('div', { class: 'row', style: { gap: '6px' } }, structs.length ? structs.map((s) => h('span', { class: 'chip' }, s.label)) : h('span', { class: 'dim small' }, t('sem pontos de interesse nomeados'))));
    const npcs = h('div', null, w.npcs.length ? w.npcs.map((n) => {
      const c = charOf(n.char);
      return h('div', { class: 'row nw', style: { padding: '10px 0', borderBottom: '1px solid var(--line)', alignItems: 'center' } },
        h('div', { style: { width: '34px', flex: 'none' } }, c ? figureSVG(c.appearance, 46) : null),
        h('div', { class: 'grow', style: { minWidth: 0 } }, h('div', null, charName(n.char)), h('div', { class: 'dim small' }, (c && c.tags.slice(0, 3).join(', ')) || '')),
        h('div', { style: { width: '130px' } }, select(tr(BEHAV), n.behavior, (v) => { n.behavior = v; })),
        h('div', { style: { width: '84px' } }, h('input', { type: 'number', min: 2, max: 60, value: n.radius, title: t('Raio de movimento (m)'), oninput: (e) => { n.radius = parseFloat(e.target.value) || 8; } })),
        h('div', { style: { width: '170px' } }, select([['', t('Card do jogo')]].concat(libChars.filter((x) => x.role === 'npc').map((x) => [x.id, '↻ ' + x.name])), '', (v) => { if (v) { swaps[n.char] = v; toast(t('Será trocado ao salvar')); } })));
    }) : h('div', { class: 'muted small' }, t('Este mundo não tem NPCs.')));
    const audio = h('div', null,
      h('div', { class: 'grid2' }, field(t('Ambiente sonoro'), select(tr(AMBIENCE), au.ambience, (v) => { au.ambience = v; })), field(t('Volume do ambiente'), range(0, 1, 0.05, au.ambience_volume, (v) => { au.ambience_volume = v; }, (v) => Math.round(v * 100) + '%'))),
      h('div', { class: 'row' }, checkbox(t('Música gerada'), mu.enabled, (v) => { mu.enabled = v; }), checkbox(t('Passos'), au.footsteps, (v) => { au.footsteps = v; })),
      h('div', { class: 'grid3' }, field(t('Humor'), select(tr(MOODS), mu.mood, (v) => { mu.mood = v; })), field(t('Escala'), select(tr(SCALES), mu.scale, (v) => { mu.scale = v; })), field(t('Andamento'), range(40, 160, 2, mu.tempo, (v) => { mu.tempo = v; }, (v) => v + ' bpm'))),
      field(t('Volume da música'), range(0, 1, 0.05, mu.volume, (v) => { mu.volume = v; }, (v) => Math.round(v * 100) + '%')));
    const iface = h('div', null,
      field(t('Texto de abertura'), h('input', { value: ux.intro, oninput: (e) => { ux.intro = e.target.value; } })),
      h('div', { class: 'row' }, [['crosshair', 'Mira'], ['minimap', 'Minimapa'], ['compass', 'Bússola'], ['clock', 'Relógio'], ['hints', 'Dicas']].map(([k, l]) => checkbox(t(l), hud[k], (v) => { hud[k] = v; }))),
      h('div', { class: 'row', style: { marginTop: '10px' } }, h('div', null, h('label', { class: 'f' }, t('Destaque')), h('input', { type: 'color', value: ux.theme.accent, oninput: (e) => { ux.theme.accent = e.target.value; } }))),
      field(t('Autonomia dos NPCs'), select([['off', t('Desligada')], ['low', t('Baixa')], ['high', t('Alta')]], w.gameplay.npc_autonomy, (v) => { w.gameplay.npc_autonomy = v; }), t('NPCs decidem sozinhos o que fazer; consome tokens do provedor.')));
    const quality = h('div', null, field(t('Qualidade alvo'), seg([['auto', t('Auto')], ['low', t('Baixa')], ['medium', t('Média')], ['high', t('Alta')]], w.quality.target, (v) => { w.quality.target = v; paintEditor(); }),
      t('Auto: o jogo mede o hardware de quem joga e ajusta resolução, sombras e distância em tempo real. Seu hardware: {t}.', { t: state.hardware.tier })));
    const versions = h('div', null, [...proj.versions_list].reverse().map((v) => h('div', { class: 'row nw', style: { padding: '10px 0', borderBottom: '1px solid var(--line)' } },
      h('span', { class: 'badge' }, 'v' + v.n), h('div', { class: 'grow' }, h('div', { style: { fontSize: '13px' } }, (v.prompt ? v.prompt.slice(0, 110) : v.summary) || '—'), h('div', { class: 'dim small' }, fmtDate(v.created) + ' · ' + (v.n === 1 ? t('criação') : v.source === 'ai' ? t('atualização por IA') : t('edição manual')))),
      h('a', { class: 'btn sm ghost', href: '/play/' + proj.id + '/v' + v.n + '/', target: '_blank', rel: 'noopener', title: t('Jogar esta versão') }, icon('play', 13)),
      h('a', { class: 'btn sm ghost', href: '/api/projects/' + proj.id + '/download?v=' + v.n, title: t('Baixar') }, icon('download', 13)))));

    editor.replaceChildren(
      h('div', { class: 'row', style: { marginBottom: '16px' } }, h('h2', { style: { margin: 0, fontSize: '20px', fontWeight: 600 } }, proj.name, ' ', h('span', { class: 'badge' }, 'v' + proj.current)), h('span', { class: 'grow' }),
        h('a', { class: 'btn sm', href: '/play/' + proj.id + '/', target: '_blank', rel: 'noopener' }, icon('play', 13), t('Jogar')),
        h('a', { class: 'btn sm', href: '/api/projects/' + proj.id + '/download' }, icon('download', 13), 'ZIP'),
        h('button', { class: 'btn sm', onclick: () => go('main', { project: { id: proj.id, name: proj.name, current: proj.current } }) }, icon('refresh', 13), t('Atualizar com IA'))),
      accordion(t('Geral'), general, true), accordion(t('Ambiente'), environment, true), accordion(t('Estruturas'), worldAcc, false),
      accordion(t('Personagens e NPCs'), npcs, false, h('span', { class: 'badge', style: { marginLeft: '8px' } }, w.npcs.length)),
      accordion(t('Áudio'), audio, false), accordion(t('Interface e jogo'), iface, false), accordion(t('Qualidade e hardware'), quality, false),
      accordion(t('Versões'), versions, false, h('span', { class: 'badge', style: { marginLeft: '8px' } }, proj.versions_list.length)),
      h('div', { class: 'stickybar' }, h('span', { class: 'dim small' }, t('Cada salvamento cria uma nova versão — sem gastar IA.')), h('button', { class: 'btn primary', onclick: save }, icon('check', 15), t('Salvar nova versão'))));
  }

  root.replaceChildren(h('div', { class: 'page' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, t('Mundos')), h('p', null, t('Configure e personalize os mundos gerados: ambiente, NPCs, áudio, interface e qualidade.')))),
    h('div', { class: 'split' }, listEl, editor)));
  await load(sel);
}
