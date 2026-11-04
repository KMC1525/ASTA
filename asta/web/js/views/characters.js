import { api, ApiError } from '../api.js';
import { t } from '../i18n.js';
import { state } from '../main.js';
import { checkbox, confirmDialog, download, field, h, icon, initial, modal, range, select, seg, tagsInput, toast } from '../ui.js';

const NS = 'http://www.w3.org/2000/svg';
export function figureSVG(ap, size = 120) {
  ap = Object.assign({ skin: '#c68a63', hair: '#2b1b12', hair_style: 'short', top: '#3b5b7a', bottom: '#2a2a30', height: 1.72, build: 1, accessory: 'none' }, ap || {});
  const s = document.createElementNS(NS, 'svg');
  const k = ap.height / 1.72, b = ap.build;
  s.setAttribute('viewBox', '0 0 80 170'); s.setAttribute('width', size * 0.5); s.setAttribute('height', size);
  const el = (tag, attrs) => { const e = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([a, v]) => e.setAttribute(a, v)); s.appendChild(e); return e; };
  const gy = 164, top = gy - 150 * k;
  if (ap.accessory === 'cape') el('rect', { x: 40 - 17 * b, y: top + 32 * k, width: 34 * b, height: 70 * k, rx: 6, fill: ap.bottom, opacity: 0.7 });
  el('rect', { x: 40 - 14 * b, y: top + 90 * k, width: 12 * b, height: 60 * k, rx: 5, fill: ap.bottom });
  el('rect', { x: 40 + 2 * b, y: top + 90 * k, width: 12 * b, height: 60 * k, rx: 5, fill: ap.bottom });
  el('rect', { x: 40 - 16 * b, y: top + 36 * k, width: 32 * b, height: 58 * k, rx: 12, fill: ap.top });
  el('rect', { x: 40 - 24 * b, y: top + 38 * k, width: 8 * b, height: 50 * k, rx: 4, fill: ap.top });
  el('rect', { x: 40 + 16 * b, y: top + 38 * k, width: 8 * b, height: 50 * k, rx: 4, fill: ap.top });
  el('circle', { cx: 40 - 20 * b, cy: top + 92 * k, r: 4.5, fill: ap.skin }); el('circle', { cx: 40 + 20 * b, cy: top + 92 * k, r: 4.5, fill: ap.skin });
  el('circle', { cx: 40, cy: top + 20 * k, r: 14 * k, fill: ap.skin });
  if (ap.hair_style !== 'bald') el('path', { d: `M ${40 - 15 * k} ${top + 18 * k} A ${15 * k} ${15 * k} 0 0 1 ${40 + 15 * k} ${top + 18 * k} Z`, fill: ap.hair });
  if (ap.hair_style === 'long') el('rect', { x: 40 - 15 * k, y: top + 14 * k, width: 30 * k, height: 34 * k, rx: 8, fill: ap.hair, opacity: 0.9 });
  if (ap.hair_style === 'bun') el('circle', { cx: 40, cy: top + 3 * k, r: 6 * k, fill: ap.hair });
  if (ap.accessory === 'hat') { el('rect', { x: 40 - 20 * k, y: top + 5 * k, width: 40 * k, height: 3.5, rx: 2, fill: ap.bottom }); el('rect', { x: 40 - 11 * k, y: top - 7 * k, width: 22 * k, height: 14 * k, rx: 4, fill: ap.bottom }); }
  if (ap.accessory === 'backpack') el('rect', { x: 40 + 12 * b, y: top + 42 * k, width: 12, height: 30 * k, rx: 4, fill: '#6b4a2b' });
  el('circle', { cx: 35, cy: top + 20 * k, r: 1.6, fill: '#15110f' }); el('circle', { cx: 45, cy: top + 20 * k, r: 1.6, fill: '#15110f' });
  return s;
}

const blank = () => ({ name: '', role: 'npc', tags: [], system_prompt: '', greeting: '', voice: { engine: 'auto', name: '', lang: 'auto', pitch: 1, rate: 1, server_voice: '' },
  appearance: { skin: '#c68a63', hair: '#2b1b12', hair_style: 'short', top: '#3b5b7a', bottom: '#2a2a30', height: 1.72, build: 1, accessory: 'none' } });

export default async function render(root, ctx) {
  let list = await api('/api/characters');
  let sel = ctx.select || (list[0] && list[0].id) || null, draft = null;
  const listEl = h('div', { class: 'list' }), editor = h('div');

  const load = (id) => { sel = id; const c = list.find((x) => x.id === id); draft = c ? JSON.parse(JSON.stringify(c)) : null; paintList(); paintEditor(); };
  const newDraft = (base) => { sel = null; draft = Object.assign(blank(), base || {}); paintList(); paintEditor(); };
  const reload = async (id) => { list = await api('/api/characters'); load(id !== undefined ? id : sel); };

  function paintList() {
    listEl.replaceChildren(...(list.length ? list.map((c) => h('div', { class: 'li' + (c.id === sel ? ' active' : ''), onclick: () => load(c.id) },
      h('div', { class: 'av', style: { background: c.appearance.top } }, initial(c.name)), h('div', { style: { minWidth: 0 } }, h('div', { class: 't' }, c.name), h('div', { class: 's' }, (c.role === 'player' ? t('jogador') : 'NPC') + (c.tags.length ? ' · ' + c.tags.slice(0, 2).join(', ') : ''))))) :
      [h('div', { class: 'muted small', style: { padding: '8px 12px' } }, t('Nenhum personagem ainda.'))]));
  }

  function voiceTest() {
    if (!window.speechSynthesis) return toast(t('Este navegador não tem síntese de voz.'), 'err');
    const v = draft.voice, u = new SpeechSynthesisUtterance(draft.greeting || t('Olá, viajante! Que bom ver você.'));
    const lang = v.lang && v.lang !== 'auto' ? v.lang : (state.settings.language === 'en' ? 'en-US' : navigator.language);
    u.lang = lang; u.pitch = v.pitch; u.rate = v.rate;
    const voices = speechSynthesis.getVoices(); const pick = (v.name && voices.find((x) => x.name === v.name)) || voices.find((x) => x.lang.toLowerCase().startsWith(lang.toLowerCase().split('-')[0]));
    if (pick) u.voice = pick;
    speechSynthesis.cancel(); speechSynthesis.speak(u);
  }

  function paintEditor() {
    if (!draft) { editor.replaceChildren(h('div', { class: 'empty' }, h('h3', null, t('Crie seu primeiro personagem')), h('p', null, t('Cada personagem é um agente de IA com nome, tags, system prompt e voz.')),
      h('div', { class: 'row', style: { justifyContent: 'center' } }, h('button', { class: 'btn primary', onclick: () => newDraft() }, icon('plus', 15), t('Novo personagem')), h('button', { class: 'btn', onclick: aiCreate }, icon('sparkle', 15), t('Criar com IA'))))); return; }
    const d = draft, ap = d.appearance, fig = h('div', { class: 'fig' }, figureSVG(ap, 168));
    const refig = () => fig.replaceChildren(figureSVG(ap, 168));
    const color = (key, label) => h('div', { style: { textAlign: 'center' } }, h('input', { type: 'color', value: ap[key], oninput: (e) => { ap[key] = e.target.value; refig(); } }), h('div', { class: 'small dim' }, label));
    const voices = window.speechSynthesis ? speechSynthesis.getVoices() : [];
    const dl = h('datalist', { id: 'voices' }, voices.map((v) => h('option', { value: v.name }, v.lang)));
    editor.replaceChildren(
      h('div', { class: 'row', style: { marginBottom: '16px' } },
        h('h2', { style: { margin: 0, fontSize: '20px', fontWeight: 600 } }, d.id ? d.name || t('Sem nome') : t('Novo personagem')), h('span', { class: 'grow' }),
        d.id ? h('button', { class: 'btn sm', onclick: () => download((d.name || 'personagem').replace(/\W+/g, '-') + '.json', JSON.stringify(d, null, 2)) }, icon('download', 14), t('Exportar')) : null,
        d.id ? h('button', { class: 'btn sm', onclick: async () => { const c = await api('/api/characters', { method: 'POST', body: Object.assign({}, d, { id: undefined, name: d.name + ' (2)' }) }); toast(t('Duplicado')); reload(c.id); } }, icon('copy', 14), t('Duplicar')) : null,
        d.id ? h('button', { class: 'btn sm danger', onclick: async () => { if (await confirmDialog(t('Apagar o personagem “{n}”? Mundos já gerados não são afetados.', { n: d.name }))) { await api('/api/characters/' + d.id, { method: 'DELETE' }); toast(t('Apagado')); const rest = list.filter((x) => x.id !== d.id); list = rest; load(rest[0] ? rest[0].id : null); } } }, icon('trash', 14)) : null),
      h('div', { class: 'card sect' }, h('h3', null, t('Identidade')),
        h('div', { class: 'grid2' }, field(t('Nome'), h('input', { value: d.name, placeholder: t('Ex.: Mira, a herbalista'), oninput: (e) => { d.name = e.target.value; } })),
          field(t('Tipo'), seg([['npc', 'NPC'], ['player', t('Jogador')]], d.role, (v) => { d.role = v; }))),
        field(t('Tags'), tagsInput(d.tags, (v) => { d.tags = v; })),
        field(t('System prompt'), h('textarea', { rows: 9, placeholder: t('Quem é, como fala, o que sabe, o que quer, segredos… Escreva como “Você é …”.'), oninput: (e) => { d.system_prompt = e.target.value; } }, d.system_prompt),
          t('É assim que o personagem pensa e age. Ele conversa por texto (chat) ou por voz.')),
        field(t('Primeira fala (opcional)'), h('input', { value: d.greeting, oninput: (e) => { d.greeting = e.target.value; } }))),
      h('div', { class: 'card sect' }, h('h3', null, t('Voz')), dl,
        h('div', { class: 'grid2' },
          field(t('Motor'), select([['auto', t('Automático (servidor se configurado, senão navegador)')], ['browser', t('Navegador (grátis, offline)')], ['server', t('Servidor TTS (Configuração → Voz)')]], d.voice.engine, (v) => { d.voice.engine = v; })),
          field(t('Idioma da voz'), h('input', { value: d.voice.lang, placeholder: 'auto · pt-BR · en-US · ja-JP', oninput: (e) => { d.voice.lang = e.target.value.trim() || 'auto'; } }), t('“auto” detecta o idioma de cada frase — qualquer idioma.'))),
        h('div', { class: 'grid2' },
          field(t('Voz do navegador'), h('input', { value: d.voice.name, setAttribute: null, list: 'voices', placeholder: t('(escolha automática)'), oninput: (e) => { d.voice.name = e.target.value; } })),
          field(t('Voz do servidor'), h('input', { value: d.voice.server_voice, placeholder: 'alloy', oninput: (e) => { d.voice.server_voice = e.target.value; } }))),
        h('div', { class: 'grid2' }, field(t('Tom'), range(0.5, 2, 0.05, d.voice.pitch, (v) => { d.voice.pitch = v; })), field(t('Velocidade'), range(0.5, 2, 0.05, d.voice.rate, (v) => { d.voice.rate = v; }))),
        h('button', { class: 'btn sm', onclick: voiceTest }, icon('audio', 14), t('Testar voz'))),
      h('div', { class: 'card sect' }, h('h3', null, t('Aparência')),
        h('div', { class: 'row nw', style: { alignItems: 'flex-start', gap: '22px' } }, fig,
          h('div', { class: 'grow' },
            h('div', { class: 'row', style: { gap: '14px', marginBottom: '14px' } }, color('skin', t('pele')), color('hair', t('cabelo')), color('top', t('roupa')), color('bottom', t('calça'))),
            h('div', { class: 'grid2' }, field(t('Cabelo'), select([['short', t('curto')], ['long', t('longo')], ['bun', t('coque')], ['bald', t('careca')]], ap.hair_style, (v) => { ap.hair_style = v; refig(); })),
              field(t('Acessório'), select([['none', t('nenhum')], ['hat', t('chapéu')], ['cape', t('capa')], ['backpack', t('mochila')]], ap.accessory, (v) => { ap.accessory = v; refig(); }))),
            h('div', { class: 'grid2' }, field(t('Altura'), range(1.4, 2.1, 0.01, ap.height, (v) => { ap.height = v; refig(); }, (v) => v.toFixed(2) + ' m')), field(t('Porte'), range(0.8, 1.3, 0.01, ap.build, (v) => { ap.build = v; refig(); }, (v) => v.toFixed(2)))))) ),
      h('div', { class: 'stickybar' },
        h('button', { class: 'btn primary', onclick: save }, icon('check', 15), t('Salvar'))));
  }

  async function save() {
    if (!draft.name.trim()) return toast(t('Dê um nome ao personagem.'), 'err');
    try {
      const c = draft.id ? await api('/api/characters/' + draft.id, { method: 'PUT', body: draft }) : await api('/api/characters', { method: 'POST', body: draft });
      toast(t('Personagem salvo'), 'ok'); await reload(c.id);
    } catch (e) { toast(e.message, 'err'); }
  }

  async function aiCreate() {
    const ta = h('textarea', { rows: 5, placeholder: t('Descreva: quem é, personalidade, papel no mundo, jeito de falar…') });
    const v = await modal(t('Criar personagem com IA'), h('div', null, h('p', { class: 'muted small', style: { marginTop: 0 } }, t('A IA escreve o card; você revisa e salva.')), ta),
      [{ label: t('Cancelar'), value: null }, { label: t('Criar'), value: 'ok', cls: 'primary' }]);
    if (v !== 'ok' || !ta.value.trim()) return;
    toast(t('Criando…'));
    try { const card = await api('/api/ai/character', { method: 'POST', body: { description: ta.value } }); newDraft(card); toast(t('Rascunho pronto — revise e salve.'), 'ok'); } catch (e) { toast(e.message, 'err'); }
  }

  const importInput = h('input', { type: 'file', accept: '.json,.png,application/json,image/png', class: 'hidden', onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { const c = await api('/api/characters/import', { method: 'POST', body: f, raw: true, headers: { 'Content-Type': f.type || 'application/octet-stream' } }); toast(t('Importado'), 'ok'); await reload(c.id); } catch (er) { toast(er.message, 'err'); }
    e.target.value = '';
  } });

  root.replaceChildren(h('div', { class: 'page' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, t('Personagens')), h('p', null, t('Agentes de IA que pensam e agem nos mundos. Cada um é salvo como um card.'))),
      h('div', { class: 'row' }, h('button', { class: 'btn', onclick: aiCreate }, icon('sparkle', 15), t('Criar com IA')), h('button', { class: 'btn', onclick: () => importInput.click() }, icon('upload', 15), t('Importar')), importInput,
        h('button', { class: 'btn primary', onclick: () => newDraft() }, icon('plus', 15), t('Novo')))),
    h('div', { class: 'split' }, listEl, editor)));
  if (sel) load(sel); else { paintList(); paintEditor(); }
  if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => { if (draft && root.isConnected) paintEditor(); };
}
