import { api, events } from '../api.js';
import { t } from '../i18n.js';
import { state } from '../main.js';
import { confirmDialog, download, field, h, icon, range, select, seg, tagsInput, toast } from '../ui.js';
import { avatarPic, faceSVG, MOOD_EMOJI, REL_LABEL } from '../avatar_ui.js';
import { figureSVG } from './characters.js';
import { openChat } from './avatars.js';

const blank = () => ({
  name: '', relationship: 'friend', gender: '', age: 24, character_type: 'fictional', content: state.settings.avatars.content === 'nsfw' ? 'nsfw' : 'sfw', tags: [], description: '', personality: '', scenario: '',
  system_prompt: '', greeting: '', examples: '', looks: '', language: 'auto', talkativeness: 0.6, portrait: '', flags: [],
  voice: { engine: 'auto', name: '', lang: 'auto', pitch: 1, rate: 1, server_voice: '' },
  appearance: { skin: '#c68a63', hair: '#2b1b12', hair_style: 'short', top: '#3b5b7a', bottom: '#2a2a30', height: 1.72, build: 1, accessory: 'none' },
});

export default async function render(root, ctx, id) {
  let d = id === 'new' ? blank() : await api('/api/avatars/' + id).catch(() => null);
  if (!d) { location.hash = '#/avatars'; return; }
  const box = h('div');
  const isNew = !d.id;

  function voiceTest() {
    if (!window.speechSynthesis) return toast(t('Este navegador não tem síntese de voz.'), 'err');
    const v = d.voice, u = new SpeechSynthesisUtterance((d.greeting || t('Olá! Que bom ver você.')).replace(/\*[^*]*\*/g, ''));
    const lang = v.lang && v.lang !== 'auto' ? v.lang : (state.settings.language === 'en' ? 'en-US' : navigator.language);
    u.lang = lang; u.pitch = v.pitch; u.rate = v.rate;
    const voices = speechSynthesis.getVoices();
    const pick = (v.name && voices.find((x) => x.name === v.name)) || voices.find((x) => x.lang.toLowerCase().startsWith(lang.toLowerCase().split('-')[0]));
    if (pick) u.voice = pick;
    speechSynthesis.cancel(); speechSynthesis.speak(u);
  }

  async function save() {
    if (!d.name.trim()) return toast(t('Dê um nome ao avatar.'), 'err');
    try {
      const body = Object.assign({}, d); delete body.flags;
      const c = d.id ? await api('/api/avatars/' + d.id, { method: 'PUT', body }) : await api('/api/avatars', { method: 'POST', body });
      toast(t('Avatar salvo'), 'ok');
      if (c.flags && c.flags.length) toast(t('Este avatar descreve um menor de idade: ele fica SFW e apenas amigo (nunca parceiro).'), 'err');
      if (!d.id) location.hash = '#/avatars/edit/' + c.id; else { d = c; paint(); }
    } catch (e) { toast(e.message, 'err'); }
  }

  async function uploadPortrait(file) {
    try { d = await api('/api/avatars/' + d.id + '/portrait', { method: 'PUT', body: file, raw: true, headers: { 'Content-Type': file.type || 'application/octet-stream' } }); toast(t('Retrato atualizado'), 'ok'); paint(); }
    catch (e) { toast(e.message, 'err'); }
  }

  // pipeline de system prompt (Analisa → Gera → Revisa → Entrega)
  const genOpts = { instructions: '' };
  const genBox = { status: h('span', { class: 'dim small' }), steps: h('div', { class: 'col', style: { gap: '4px', marginTop: '10px' } }), out: h('div') };
  const PROMPT_STEPS = [['analyze', t('Analisa'), t('Entende quem é o personagem (real ou fictício, idade, jeito de falar)')], ['generate', t('Gera'), t('Escreve o system prompt')], ['review', t('Revisa'), t('Confere coerência, voz, idioma e regras de segurança')], ['deliver', t('Entrega'), t('Limpa, aplica as regras e entrega o texto final')]];
  const stepRows = {};
  function paintSteps() {
    genBox.steps.replaceChildren(...PROMPT_STEPS.map(([id, label, hint]) => { const r = h('div', { class: 'row', style: { gap: '8px' }, title: hint }, h('span', { class: 'chip' }, label), h('span', { class: 'dim small' }, '')); stepRows[id] = r; return r; }));
  }
  const stepText = (id, s, dt) => {
    if (s === 'running') return dt.revision ? t('revisando…') : t('trabalhando…');
    if (id === 'analyze') return (dt.character_type === 'real' ? t('pessoa real') : t('personagem fictício')) + (dt.is_minor ? ' · ' + t('menor de idade') : '') + ' · ' + (dt.content || '').toUpperCase();
    if (id === 'generate') return t('{n} palavras', { n: dt.words || 0 }) + (dt.revision ? ' · ' + t('corrigido') : '');
    if (id === 'review') return (dt.approved ? t('aprovado') : t('com ressalvas')) + (dt.score != null ? ' · ' + t('nota {n}/10', { n: dt.score }) : '');
    return s === 'done' ? t('pronto') : '';
  };
  async function generatePrompt() {
    paintSteps(); genBox.out.replaceChildren(); genBox.status.textContent = '';
    let jid;
    try { jid = (await api('/api/avatars/system-prompt', { method: 'POST', body: { avatar_id: d.id || '', draft: d, instructions: genOpts.instructions, content: d.content, character_type: d.character_type === 'real' ? 'real' : 'auto', detail: 'detailed' } })).job_id; }
    catch (e) { return toast(e.message, 'err'); }
    events('/api/jobs/' + jid + '/events', (ev) => {
      if (ev.type === 'step' && stepRows[ev.id]) { stepRows[ev.id].lastChild.textContent = stepText(ev.id, ev.status, ev.detail || {}); stepRows[ev.id].firstChild.classList.toggle('on', ev.status === 'done' || ev.status === 'warn'); }
      else if (ev.type === 'done') {
        d.system_prompt = ev.system_prompt;
        if (ev.character_type) d.character_type = ev.character_type;
        if (ev.content) d.content = ev.content;
        d.flags = ev.flags || d.flags;
        const notes = (ev.warnings || []).map((w) => h('div', { class: 'errbox', style: { marginTop: '8px' } }, w));
        toast(t('System prompt gerado: revise e salve.'), 'ok');
        paint();
        genBox.out.replaceChildren(h('div', { class: 'muted small', style: { marginTop: '10px' } }, t('Pronto — o texto foi para o campo System prompt (acima). Nota {n}/10.', { n: ev.score == null ? '—' : ev.score })), ...notes);
      }
      else if (ev.type === 'error') toast(ev.message, 'err');
      else if (ev.type === 'cancelled') toast(t('Cancelado'));
    });
  }

  function paint() {
    const ap = d.appearance, minor = (d.flags || []).includes('minor_described') || d.age < 18;
    const fig = h('div', { class: 'fig' }, figureSVG(ap, 168)), pic = h('div', { class: 'row', style: { gap: '10px' } });
    const refig = () => { fig.replaceChildren(figureSVG(ap, 168)); paintMoods(); };
    const paintMoods = () => pic.replaceChildren(...['neutral', 'happy', 'shy', 'sad', 'angry', 'flirty'].map((m) => h('div', { style: { textAlign: 'center' }, title: m }, d.portrait && m === 'neutral' ? avatarPic(d, 46) : faceSVG(ap, m, 46), h('div', { class: 'small dim' }, MOOD_EMOJI[m]))));
    const color = (key, label) => h('div', { style: { textAlign: 'center' } }, h('input', { type: 'color', value: ap[key], oninput: (e) => { ap[key] = e.target.value; refig(); } }), h('div', { class: 'small dim' }, label));
    const voices = window.speechSynthesis ? speechSynthesis.getVoices() : [];
    const portraitInput = h('input', { type: 'file', accept: 'image/png,image/jpeg,image/webp,image/gif', class: 'hidden', onchange: (e) => { if (e.target.files[0]) uploadPortrait(e.target.files[0]); e.target.value = ''; } });

    box.replaceChildren(
      h('div', { class: 'row', style: { marginBottom: '16px' } },
        h('h2', { style: { margin: 0, fontSize: '20px', fontWeight: 600 } }, d.id ? d.name || t('Sem nome') : t('Novo avatar')), h('span', { class: 'grow' }),
        d.id ? h('button', { class: 'btn sm primary', onclick: () => openChat([d.id]) }, icon('send', 14), t('Conversar')) : null,
        d.id ? h('button', { class: 'btn sm', onclick: () => download((d.name || 'avatar').replace(/\W+/g, '-') + '.json', JSON.stringify(d, null, 2)) }, icon('download', 14), t('Exportar')) : null,
        d.id ? h('button', { class: 'btn sm', onclick: async () => { const v2 = await api('/api/avatars/' + d.id + '/export?format=card_v2'); download((d.name || 'avatar').replace(/\W+/g, '-') + '.card.json', JSON.stringify(v2, null, 2)); } }, icon('download', 14), 'Card V2') : null,
        d.id ? h('button', { class: 'btn sm danger', onclick: async () => { if (await confirmDialog(t('Apagar o avatar “{n}”? Memórias e retrato também serão apagados.', { n: d.name }))) { await api('/api/avatars/' + d.id, { method: 'DELETE' }); toast(t('Apagado')); location.hash = '#/avatars'; } } }, icon('trash', 14)) : null),

      h('div', { class: 'card sect' }, h('h3', null, t('Identidade')),
        h('div', { class: 'grid2' }, field(t('Nome'), h('input', { value: d.name, placeholder: t('Ex.: Luna'), oninput: (e) => { d.name = e.target.value; } })),
          field(t('Relação com você'), select(Object.keys(REL_LABEL).map((k) => [k, t(REL_LABEL[k])]), d.relationship, (v) => { d.relationship = v; }))),
        h('div', { class: 'grid3' }, field(t('Gênero'), h('input', { value: d.gender, list: 'genders', placeholder: t('feminino, masculino, não-binário…'), oninput: (e) => { d.gender = e.target.value; } }), null),
          field(t('Idade'), h('input', { type: 'number', min: 5, max: 120, value: d.age, oninput: (e) => { d.age = parseInt(e.target.value || '24', 10); } })),
          field(t('Conteúdo'), seg([['sfw', 'SFW'], ['nsfw', 'NSFW']], d.content, (v) => { if (v === 'nsfw' && d.character_type === 'real') { toast(t('Pessoas reais ficam sempre em SFW.'), 'err'); paint(); return; } d.content = v; }))),
        field(t('Tipo de personagem'), seg([['fictional', t('Fictício (original ou de uma obra)')], ['real', t('Pessoa real')]], d.character_type || 'fictional', (v) => { d.character_type = v; if (v === 'real') d.content = 'sfw'; paint(); }),
          t('Dá para criar avatares de qualquer tipo de personagem, real ou fictício. Pessoa real fica sempre SFW (o ASTA não cria conteúdo sexual sobre pessoas reais) e é retratada só como interpretação ficcional e respeitosa. Personagens fictícios adultos podem ser SFW ou NSFW.')),
        h('datalist', { id: 'genders' }, ['feminino', 'masculino', 'não-binário', 'female', 'male', 'non-binary'].map((g) => h('option', { value: g }))),
        h('div', { class: 'hint small dim' }, t('SFW: tudo para todos os públicos. NSFW: conversa adulta sem filtros do ASTA (o provedor escolhido ainda pode ter os dele). Avatares são adultos (18+); se o card descrever um menor de idade, ele fica SFW e apenas amigo.')),
        minor ? h('div', { class: 'errbox', style: { marginTop: '10px' } }, t('Este avatar descreve um menor de idade: o modo NSFW e o papel de parceiro(a) ficam desativados.')) : null,
        field(t('Tags'), tagsInput(d.tags, (v) => { d.tags = v; }))),

      h('div', { class: 'card sect' }, h('h3', null, t('Personalidade')),
        field(t('Personalidade'), h('textarea', { rows: 3, placeholder: t('Carinhosa, curiosa, um pouco ciumenta, adora astronomia…'), oninput: (e) => { d.personality = e.target.value; } }, d.personality)),
        field(t('Aparência (texto)'), h('textarea', { rows: 2, placeholder: t('Cabelos longos e ruivos, olhos verdes, estilo casual…'), oninput: (e) => { d.looks = e.target.value; } }, d.looks), t('Também serve de descrição para geradores de imagem (Canvas).')),
        field(t('Descrição'), h('textarea', { rows: 3, oninput: (e) => { d.description = e.target.value; } }, d.description)),
        field(t('Cenário'), h('textarea', { rows: 2, placeholder: t('Onde e como vocês se conhecem…'), oninput: (e) => { d.scenario = e.target.value; } }, d.scenario)),
        field(t('System prompt'), h('textarea', { rows: 8, placeholder: t('Quem é, como fala, o que sente… Escreva como “Você é …”. Vazio = usa os campos acima.'), oninput: (e) => { d.system_prompt = e.target.value; } }, d.system_prompt)),
        field(t('Primeira mensagem'), h('textarea', { rows: 2, oninput: (e) => { d.greeting = e.target.value; } }, d.greeting)),
        field(t('Exemplos de fala'), h('textarea', { rows: 4, placeholder: t('Usuário: …\nAvatar: …'), oninput: (e) => { d.examples = e.target.value; } }, d.examples), t('Mostram o estilo do avatar ao modelo.')),
        field(t('Falante em grupo'), range(0.1, 1, 0.05, d.talkativeness, (v) => { d.talkativeness = v; }, (v) => Math.round(v * 100) + '%'), t('Quanto mais alto, mais o avatar puxa a conversa nos grupos.'))),

      h('div', { class: 'card sect' }, h('h3', null, t('Gerar o system prompt com IA')),
        h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Um pipeline em 4 etapas — analisa o personagem, gera o prompt, revisa e entrega — usando o nome, a personalidade, a aparência e as instruções abaixo. O resultado vai para o campo System prompt; revise e salve.')),
        field(t('Instruções (opcional)'), h('textarea', { rows: 3, placeholder: t('Ex.: personagem de anime, fala com gírias, é protetora e meio tsundere; ou: baseada em uma figura histórica…'), oninput: (e) => { genOpts.instructions = e.target.value; } }, genOpts.instructions)),
        h('div', { class: 'row' }, h('button', { class: 'btn primary', onclick: generatePrompt }, icon('sparkle', 14), t('Gerar system prompt')), genBox.status),
        genBox.steps, genBox.out),

      h('div', { class: 'card sect' }, h('h3', null, t('Voz')), h('datalist', { id: 'voices' }, voices.map((v) => h('option', { value: v.name }, v.lang))),
        h('div', { class: 'grid2' },
          field(t('Motor'), select([['auto', t('Automático (servidor se configurado, senão navegador)')], ['browser', t('Navegador (grátis, offline)')], ['server', t('Servidor TTS (Configuração → Voz)')]], d.voice.engine, (v) => { d.voice.engine = v; })),
          field(t('Idioma da voz'), h('input', { value: d.voice.lang, placeholder: 'auto · pt-BR · en-US · ja-JP', oninput: (e) => { d.voice.lang = e.target.value.trim() || 'auto'; } }), t('“auto” detecta o idioma de cada frase — qualquer idioma.'))),
        h('div', { class: 'grid2' }, field(t('Voz do navegador'), h('input', { value: d.voice.name, list: 'voices', placeholder: t('(escolha automática)'), oninput: (e) => { d.voice.name = e.target.value; } })),
          field(t('Voz do servidor'), h('input', { value: d.voice.server_voice, placeholder: 'alloy', oninput: (e) => { d.voice.server_voice = e.target.value; } }))),
        h('div', { class: 'grid2' }, field(t('Tom'), range(0.5, 2, 0.05, d.voice.pitch, (v) => { d.voice.pitch = v; })), field(t('Velocidade'), range(0.5, 2, 0.05, d.voice.rate, (v) => { d.voice.rate = v; }))),
        h('button', { class: 'btn sm', onclick: voiceTest }, icon('audio', 14), t('Testar voz'))),

      h('div', { class: 'card sect' }, h('h3', null, t('Aparência e retrato')),
        h('div', { class: 'row nw', style: { alignItems: 'flex-start', gap: '22px' } }, fig,
          h('div', { class: 'grow' },
            h('div', { class: 'row', style: { gap: '14px', marginBottom: '14px' } }, color('skin', t('pele')), color('hair', t('cabelo')), color('top', t('roupa')), color('bottom', t('calça'))),
            h('div', { class: 'grid2' }, field(t('Cabelo'), select([['short', t('curto')], ['long', t('longo')], ['bun', t('coque')], ['bald', t('careca')]], ap.hair_style, (v) => { ap.hair_style = v; refig(); })),
              field(t('Acessório'), select([['none', t('nenhum')], ['hat', t('chapéu')], ['cape', t('capa')], ['backpack', t('mochila')]], ap.accessory, (v) => { ap.accessory = v; refig(); }))),
            h('div', { class: 'grid2' }, field(t('Altura'), range(1.4, 2.1, 0.01, ap.height, (v) => { ap.height = v; refig(); }, (v) => v.toFixed(2) + ' m')), field(t('Porte'), range(0.8, 1.3, 0.01, ap.build, (v) => { ap.build = v; refig(); }, (v) => v.toFixed(2)))),
            h('label', { class: 'f' }, t('Expressões')), pic,
            h('div', { class: 'row', style: { marginTop: '12px' } },
              d.id ? h('button', { class: 'btn sm', onclick: () => portraitInput.click() }, icon('image', 14), d.portrait ? t('Trocar retrato') : t('Enviar retrato')) : h('span', { class: 'dim small' }, t('Salve o avatar para enviar um retrato.')), portraitInput,
              d.portrait ? h('button', { class: 'btn sm ghost danger', onclick: async () => { d = await api('/api/avatars/' + d.id + '/portrait', { method: 'DELETE' }); paint(); } }, t('Remover retrato')) : null)))),

      h('div', { class: 'stickybar' }, h('button', { class: 'btn primary', onclick: save }, icon('check', 15), t('Salvar'))));
    paintMoods();
  }

  root.replaceChildren(h('div', { class: 'page' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'Avatars'), h('p', null, t('Edite o card do avatar: personalidade, voz e aparência.'))),
      h('a', { class: 'btn', href: '#/avatars' }, t('← Todos os avatares'))), box));
  paint();
  if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => { if (root.isConnected) paint(); };
}
