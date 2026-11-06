import { api, events } from '../api.js';
import { t } from '../i18n.js';
import { refreshState, renderSide, saveSettings, state } from '../main.js';
import { accentSwatches, themeCards } from '../appearance.js';
import { CONFIG_TABS, ui } from '../prefs.js';
import { GGUF_HINT, GGUF_KINDS, PREC_HINT, QUALITY_LABEL } from '../model_labels.js';
import { checkbox, confirmDialog, download, field, fmtBytes, h, icon, range, select, seg, toast } from '../ui.js';

export default async function render(root, ctx) {
  let tab = ctx.tab || 'providers';
  const body = h('div'), tabs = h('div', { class: 'tabs' });
  const TABS = CONFIG_TABS;
  const paintTabs = () => tabs.replaceChildren(...TABS.map(([id, l]) => h('button', { class: tab === id ? 'on' : '', onclick: () => { tab = id; paintTabs(); paintBody(); } }, t(l))));
  const paintBody = async () => { body.replaceChildren(h('div', { class: 'spinner' })); const fn = { providers, media, chat, generation, creative, voice, local, appearance, system }[tab]; body.replaceChildren(await fn()); };
  root.replaceChildren(h('div', { class: 'page narrow cfg' }, h('div', { class: 'page-h' }, h('div', null, h('h1', null, t('Configuração')), h('p', null, t('Provedores de IA, mídia, voz e modelos locais: configure uma vez e use em tudo.')))), tabs, body));
  paintTabs(); await paintBody();
}

// ---------------------------------------------------------------------------------- provedores
async function providers() {
  const presets = state.presets;
  const localModels = (await api('/api/hf/local')).models.map((m) => m.name);
  let preText = [];   // modelos de texto pré-instalados: o contexto base deles (32K) vale enquanto o usuário não escolher outro valor
  try { preText = (await api('/api/preinstalled')).models.filter((m) => m.kind === 'text' && m.n_ctx); } catch (e) { /* sem a lista, só não mostramos o valor automático */ }
  const container = h('div');
  const rolesCard = () => {
    const S = state.settings;
    const roleSel = (role, label, hint) => field(label, select((role === 'characters' ? [['auto', t('Automático (recomendado)')]] : []).concat(presets.map((p) => [p.id, t(p.label)])), role === 'characters' && S.active[role] === 'demo' ? 'auto' : S.active[role], async (v) => { await saveSettings({ active: { [role]: v } }); toast(t('Salvo'), 'ok'); paint(); }), hint);
    return h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Quem faz o quê')),
      h('div', { class: 'grid2' }, roleSel('generation', t('Geração de mundos'), t('Modelo mais capaz: roda os agentes (análise, planejamento, criação, revisão).')),
        roleSel('characters', t('Personagens (chat e voz)'), t('Responde a cada mensagem dos NPCs e dos avatares. Automático: usa o provedor de geração (nuvem ou local) ou, se não houver, o modelo local instalado — o Demo só entra quando nenhuma IA está disponível.'))));
  };
  const paint = () => container.replaceChildren(rolesCard(), h('div', null, presets.map(card)));

  function card(p) {
    const S = state.settings, cfg = (S.providers && S.providers[p.id]) || {};
    const isGen = S.active.generation === p.id, isChar = S.active.characters === p.id;
    const configured = p.id === 'demo' || cfg.has_key || cfg.model || (p.local && cfg.base_url);
    const draft = { base_url: cfg.base_url || '', model: cfg.model || '', api_key: '', vision: cfg.vision != null ? cfg.vision : p.vision, n_ctx: cfg.n_ctx > 0 ? cfg.n_ctx : 0 };
    const res = h('div', { class: 'res' });
    const dl = h('datalist', { id: 'models-' + p.id }, (p.kind === 'local_hf' ? localModels : []).map((m) => h('option', { value: m })));
    const cardEl = h('div', { class: 'prov' + (isGen || isChar ? ' open' : '') });
    const bodyEl = h('div', { class: 'bd' });

    const loadModels = async () => {
      res.className = 'res'; res.textContent = '…';
      const r = await api('/api/providers/models', { method: 'POST', body: { id: p.id, config: draft } });
      if (!r.ok) { res.className = 'res err'; res.textContent = r.error; return; }
      dl.replaceChildren(...r.models.map((m) => h('option', { value: m }))); res.className = 'res ok'; res.textContent = t('{n} modelos disponíveis — clique no campo Modelo para escolher.', { n: r.models.length });
    };
    const test = async () => {
      res.className = 'res'; res.textContent = t('Testando…');
      const r = await api('/api/providers/test', { method: 'POST', body: { id: p.id, config: draft } });
      res.className = 'res ' + (r.ok ? 'ok' : 'err');
      res.textContent = r.ok ? '✓ ' + t('Funcionou') + ' (' + (r.ms / 1000).toFixed(1) + ' s) · ' + t('resposta:') + ' ' + r.reply : '✗ ' + r.error;
    };
    const save = async () => {
      const patch = { base_url: draft.base_url, model: draft.model };
      if (p.id !== 'lmstudio') patch.vision = !!draft.vision;   // no LM Studio a visão é detectada pelo tipo do modelo (vlm)
      if (p.kind === 'local_hf') patch.n_ctx = draft.n_ctx > 0 ? draft.n_ctx : 0;   // 0 = automático
      if (draft.api_key) patch.api_key = draft.api_key;
      await saveSettings({ providers: { [p.id]: patch } }); draft.api_key = ''; toast(t('Salvo'), 'ok'); await refreshState(); renderSide(); paint();
    };
    const inputs = [];
    if (p.id === 'demo') inputs.push(h('p', { class: 'muted small', style: { margin: '10px 0 0' } }, t(p.hint)));
    else {
      if (p.id === 'lmstudio') inputs.push(lmStudioBox(p, draft, () => modelIn));
      if (p.needs_key || p.kind === 'openai' || p.id === 'anthropic') inputs.push(field(t('Chave de API') + (p.needs_key ? '' : ' (' + t('opcional') + ')'),
        h('div', { class: 'row nw' }, h('input', { type: 'password', autocomplete: 'off', placeholder: cfg.has_key ? '•••••••• (' + t('salva') + ')' : 'sk-…', oninput: (e) => { draft.api_key = e.target.value; } }),
          cfg.has_key ? h('button', { class: 'btn sm danger', onclick: async () => { await saveSettings({ providers: { [p.id]: { api_key: null } } }); toast(t('Chave removida')); await refreshState(); paint(); } }, t('Remover')) : null),
        p.docs ? h('a', { href: p.docs, target: '_blank', rel: 'noopener', class: 'muted' }, t('Obter chave →')) : null));
      if (p.kind === 'openai' || p.id === 'anthropic') inputs.push(field(t('URL base'), h('input', { value: draft.base_url || p.base_url, placeholder: p.base_url || 'https://…/v1', oninput: (e) => { draft.base_url = e.target.value.trim(); } })));
      const modelIn = h('input', { list: 'models-' + p.id, value: draft.model, placeholder: p.kind === 'local_hf' ? t('arquivo .gguf baixado') : p.id === 'lmstudio' ? t('automático: o modelo carregado no LM Studio') : t('clique em “Carregar modelos”'), oninput: (e) => { draft.model = e.target.value.trim(); } });
      inputs.push(field(t('Modelo'), h('div', { class: 'row nw' }, modelIn, dl,
        p.kind !== 'local_hf' ? h('button', { class: 'btn sm', onclick: loadModels }, icon('refresh', 13), t('Carregar modelos')) : null)));
      if (p.id === 'lmstudio') { /* visão: automática pelo tipo do modelo */ }
      else if (p.kind !== 'local_hf') inputs.push(checkbox(t('Aceita imagens (visão)'), draft.vision, (v) => { draft.vision = v; }));
      else {
        // janela de contexto: vazio = automático (32K nos modelos de texto pré-instalados; nos demais, conforme o hardware)
        const ctxHint = h('p', { class: 'muted small', style: { margin: '4px 0 0' } });
        const showCtx = () => {
          const pre = preText.find((m) => (m.parts || [m.file]).includes(draft.model) || m.file.split('/').pop() === draft.model);
          ctxHint.textContent = draft.n_ctx > 0 ? t('Usando {n} tokens de contexto.', { n: draft.n_ctx.toLocaleString() })
            : pre ? t('Automático: {n} tokens (base do modelo pré-instalado).', { n: pre.n_ctx.toLocaleString() }) : t('Automático: conforme o seu hardware (2.048 a 8.192 tokens).');
        };
        const ctxDl = h('datalist', { id: 'ctx-' + p.id }, [4096, 8192, 16384, 32768, 65536, 131072].map((n) => h('option', { value: String(n) })));
        const ctxIn = h('input', { type: 'number', list: 'ctx-' + p.id, min: 512, step: 1024, value: draft.n_ctx || '', placeholder: t('automática'), oninput: (e) => { draft.n_ctx = Math.max(0, parseInt(e.target.value || '0', 10) || 0); showCtx(); } });
        inputs.push(field(t('Janela de contexto (tokens)'), h('div', { class: 'row nw' }, ctxIn, ctxDl,
          h('button', { class: 'btn sm', onclick: () => { draft.n_ctx = 0; ctxIn.value = ''; showCtx(); } }, t('Usar o automático'))),
          t('Quanto texto o modelo lê de uma vez. Janelas maiores usam mais memória (RAM). Os modelos de texto pré-instalados começam com 32.768 (32K); você pode ajustar quando quiser.')));
        showCtx(); inputs.push(ctxHint);
      }
      if (p.hint) inputs.push(h('p', { class: 'muted small' }, t(p.hint)));
    }
    inputs.push(h('div', { class: 'row', style: { marginTop: '8px' } }, h('button', { class: 'btn sm', onclick: test }, t('Testar')), h('button', { class: 'btn sm primary', onclick: save }, t('Salvar')), p.id !== 'demo' ? h('span', { class: 'dim small' }, t('Ao testar, usamos os valores acima mesmo sem salvar.')) : null), res);
    bodyEl.replaceChildren(...inputs);
    cardEl.append(h('div', { class: 'hd', onclick: () => cardEl.classList.toggle('open') }, h('span', { class: 'dot ' + (configured ? 'ok' : ''), style: { width: '8px', height: '8px', borderRadius: '50%', background: configured ? 'var(--ok)' : 'var(--dim)' } }),
      h('span', { class: 'nm' }, t(p.label)), p.local ? h('span', { class: 'badge' }, t('local')) : null,
      h('span', { class: 'roles' }, isGen ? h('span', { class: 'chip on' }, t('geração')) : null, isChar ? h('span', { class: 'chip on' }, t('personagens')) : null)), bodyEl);
    return cardEl;
  }
  paint();
  return container;
}

// LM Studio: detecta o servidor, lista os modelos (carregados primeiro), escolhe com um clique e usa nos avatares.
function lmStudioBox(p, draft, getModelInput) {
  const box = h('div', { class: 'card', style: { background: 'var(--bg2, rgba(255,255,255,.03))', margin: '4px 0 12px', padding: '12px 14px' } });
  const status = h('div', { class: 'row', style: { gap: '8px' } }), list = h('div', { class: 'row', style: { gap: '6px', flexWrap: 'wrap', marginTop: '8px' } }), note = h('p', { class: 'muted small', style: { margin: '8px 0 0' } });
  const use = async (role) => {
    await saveSettings({ providers: { lmstudio: { base_url: draft.base_url, model: draft.model } }, active: { [role]: 'lmstudio' } });
    toast(role === 'characters' ? t('Os avatares vão conversar pelo LM Studio.') : t('A geração vai usar o LM Studio.'), 'ok'); await refreshState(); renderSide();
  };
  async function detect() {
    status.replaceChildren(h('div', { class: 'spinner' })); list.replaceChildren(); note.textContent = '';
    let r;
    try { r = await api('/api/lmstudio?url=' + encodeURIComponent(draft.base_url || '')); } catch (e) { status.replaceChildren(h('span', { class: 'dim small' }, e.message)); return; }
    const dot = h('span', { style: { width: '9px', height: '9px', borderRadius: '50%', background: r.running ? 'var(--ok)' : 'var(--dim)', display: 'inline-block' } });
    status.replaceChildren(dot, h('b', null, r.running ? t('LM Studio detectado em {u}', { u: r.url }) : t('LM Studio não detectado em {u}', { u: r.url })), h('span', { class: 'grow' }),
      h('button', { class: 'btn sm', onclick: detect }, icon('refresh', 13), t('Detectar de novo')),
      r.running ? h('button', { class: 'btn sm primary', onclick: () => use('characters') }, t('Usar nos avatares')) : null,
      r.running ? h('button', { class: 'btn sm', onclick: () => use('generation') }, t('Usar na geração')) : null);
    if (!r.running) { note.textContent = t(r.hint) + (r.error ? ' (' + r.error + ')' : ''); return; }
    list.replaceChildren(...(r.models.length ? r.models.map((m) => h('button', { class: 'chip' + (draft.model === m.id || (!draft.model && r.selected === m.id) ? ' on' : ''), title: [m.loaded ? t('carregado') : t('não carregado'), m.quant, m.vision ? t('visão') : ''].filter(Boolean).join(' · '),
      onclick: () => { draft.model = m.id; const inp = getModelInput(); if (inp) inp.value = m.id; detect(); } }, (m.loaded ? '● ' : '○ ') + m.id + (m.vision ? ' 👁' : ''))) : [h('span', { class: 'dim small' }, t('Nenhum modelo instalado: baixe um na aba «Discover» do LM Studio.'))]));
    note.textContent = r.loaded.length ? t('● carregado agora · ○ instalado (o LM Studio pode carregar sob demanda). Sem escolher, o ASTA usa o modelo carregado.') : t('Nenhum modelo está carregado no LM Studio: carregue um (ou escolha um acima).');
  }
  box.append(status, list, note); detect();
  return box;
}

// ---------------------------------------------------------------------------------- geração
async function generation() {
  const g = JSON.parse(JSON.stringify(state.settings.generation)), c = JSON.parse(JSON.stringify(state.settings.characters));
  const wrap = h('div', null,
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Geração dos mundos')),
      h('div', { class: 'grid2' }, field(t('Perspectiva padrão'), seg([['first', t('1ª pessoa')], ['third', t('3ª pessoa')]], g.perspective, (v) => { g.perspective = v; })),
        field(t('Conteúdo'), seg([['free', t('Livre (SFW + NSFW)')], ['sfw', 'SFW']], g.content, (v) => { g.content = v; }), t('“Livre”: o ASTA não adiciona filtros próprios. O provedor escolhido ainda pode ter os dele. Conteúdo sexual envolvendo menores nunca é permitido.'))),
      h('div', { class: 'grid2' }, field(t('Realismo'), range(0, 1, 0.05, g.realism, (v) => { g.realism = v; }, (v) => Math.round(v * 100) + '%')),
        field(t('Tamanho do mundo'), select([['small', t('Pequeno')], ['medium', t('Médio')], ['large', t('Grande')]], g.size, (v) => { g.size = v; }), t('Sempre limitado pelo seu hardware.'))),
      h('div', { class: 'grid2' }, field(t('Qualidade alvo'), select([['auto', t('Automática (recomendado)')], ['low', t('Baixa')], ['medium', t('Média')], ['high', t('Alta')]], g.quality, (v) => { g.quality = v; })),
        field(t('Máximo de NPCs'), h('input', { type: 'number', min: 0, max: 64, value: g.max_npcs, oninput: (e) => { g.max_npcs = parseInt(e.target.value || '0', 10); } }), t('0 = automático (conforme o hardware).'))),
      h('div', { class: 'grid2' }, field(t('Rodadas de revisão'), select([['0', t('Nenhuma (mais rápido)')], ['1', '1'], ['2', '2'], ['3', '3']], String(g.revisions), (v) => { g.revisions = parseInt(v, 10); }), t('O agente Revisor pode pedir correções.')),
        field(t('Criatividade (temperatura)'), range(0, 1.5, 0.05, g.temperature, (v) => { g.temperature = v; }))),
      field(t('Máximo de tokens por agente'), h('input', { type: 'number', min: 1000, max: 32000, step: 500, value: g.max_tokens, oninput: (e) => { g.max_tokens = parseInt(e.target.value || '6000', 10); } })),
      h('div', { class: 'row' }, checkbox(t('Ciclo dia/noite'), g.day_cycle, (v) => { g.day_cycle = v; }), checkbox(t('Enviar anexos aos agentes'), g.include_attachments, (v) => { g.include_attachments = v; })),
      field(t('Autonomia dos NPCs'), select([['off', t('Desligada')], ['low', t('Baixa')], ['high', t('Alta')]], g.npc_autonomy, (v) => { g.npc_autonomy = v; }), t('NPCs decidem sozinhos o que fazer enquanto você joga (consome tokens).'))),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Geração dos personagens')),
      h('div', { class: 'grid2' }, field(t('Detalhe do system prompt'), seg([['short', t('Curto')], ['detailed', t('Detalhado')]], c.detail, (v) => { c.detail = v; })), h('div', null, checkbox(t('Criar também o personagem do jogador'), c.player_character, (v) => { c.player_character = v; }))),
      h('div', { class: 'grid2' }, field(t('Criatividade nas conversas'), range(0, 1.5, 0.05, c.temperature, (v) => { c.temperature = v; })),
        field(t('Máximo de tokens por resposta'), h('input', { type: 'number', min: 50, max: 4000, step: 50, value: c.max_tokens, oninput: (e) => { c.max_tokens = parseInt(e.target.value || '700', 10); } }))),
      h('div', { class: 'grid2' }, field(t('Memória de curto prazo (turnos)'), h('input', { type: 'number', min: 2, max: 60, value: c.history_turns, oninput: (e) => { c.history_turns = parseInt(e.target.value || '16', 10); } })),
        field(t('Memórias de longo prazo por NPC'), h('input', { type: 'number', min: 5, max: 100, value: c.memory_limit, oninput: (e) => { c.memory_limit = parseInt(e.target.value || '30', 10); } })))),
    h('div', { class: 'row', style: { justifyContent: 'flex-end' } }, h('button', { class: 'btn primary', onclick: async () => { await saveSettings({ generation: g, characters: c }); toast(t('Salvo'), 'ok'); } }, icon('check', 15), t('Salvar'))));
  return wrap;
}

// ---------------------------------------------------------------------------------- chat
async function chat() {
  const c = JSON.parse(JSON.stringify(state.settings.chat)), w = c.web, keys = { brave: '', tavily: '' };
  const num = (key, min, max, step, label, hint, target = c) => field(label, h('input', { type: 'number', min, max, step, value: target[key], id: 'cc-' + key, oninput: (e) => { const v = parseInt(e.target.value, 10); if (!Number.isNaN(v)) target[key] = Math.max(min, Math.min(max, v)); } }), hint);
  const quick = (key, values, fmt, input) => h('div', { class: 'row', style: { gap: '6px', flexWrap: 'wrap', marginTop: '6px' } }, ...values.map((v) => h('button', { class: 'chip', type: 'button', onclick: () => { c[key] = v; document.getElementById(input).value = v; } }, fmt(v))));
  const kb = (n) => (n >= 1000000 ? (n / 1000000) + 'M' : n >= 1000 ? (n / 1000) + 'K' : String(n));
  const keyField = (id, label, setFlag) => field(label, h('div', { class: 'row', style: { gap: '8px' } }, h('input', { type: 'password', autocomplete: 'off', id: 'cc-' + id, placeholder: setFlag ? '•••••••• (' + t('salva') + ')' : '', oninput: (e) => { keys[id.replace('_key', '')] = e.target.value; } }),
    setFlag ? h('button', { class: 'btn sm', type: 'button', onclick: async () => { await saveSettings({ chat: { web: { [id]: null } } }); toast(t('Chave removida'), 'ok'); await refreshState(); } }, t('Remover')) : null));
  const results = h('div', { class: 'col', style: { marginTop: '10px' } });
  const levels = [['off', t('Desligado')], ['slow', 'Slow'], ['medium', 'Medium'], ['high', 'High'], ['xhigh', 'Extra high'], ['ultra', 'Ultra']];
  const test = async () => {
    results.replaceChildren(h('div', { class: 'spinner' }));
    try {
      const patch = { chat: { web: { engine: w.engine, results: w.results, read_pages: w.read_pages, searxng_url: w.searxng_url, language: w.language } } };
      if (keys.brave) patch.chat.web.brave_key = keys.brave;
      if (keys.tavily) patch.chat.web.tavily_key = keys.tavily;
      await saveSettings(patch);   // o teste usa o que está na tela
      const r = await api('/api/web/search', { method: 'POST', body: { query: 'ASTA open source AI' } });
      results.replaceChildren(h('div', { class: 'ok small' }, '✓ ' + t('Funcionando — motor: {n}', { n: r.engine })), ...r.sources.map((x) => h('div', { class: 'small' }, h('a', { href: x.url, target: '_blank', rel: 'noopener noreferrer' }, x.title), h('span', { class: 'dim' }, ' — ' + x.host))));
    } catch (e) { results.replaceChildren(h('div', { class: 'errbox' }, e.message)); }
  };
  return h('div', null,
    h('p', { class: 'muted', style: { marginTop: 0 } }, t('Ajustes da tela Chat. O modelo e o provedor se escolhem no botão ao lado do Run; aqui ficam o tamanho das respostas, a memória da conversa, o tempo de pensamento e a busca na web.')),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Respostas')),
      h('div', { class: 'grid2' },
        h('div', null, num('max_tokens', 64, 32000, 100, t('Tamanho das respostas (tokens)'), t('Limite do texto de cada resposta. 1 token ≈ 3–4 letras; 2.000 ≈ 1.200 palavras. Com tempo de pensamento ligado, o pensamento vai além desse limite.')), quick('max_tokens', [500, 2000, 6000, 16000], (v) => t('{n} tokens', { n: kb(v) }), 'cc-max_tokens')),
        field(t('Criatividade (temperatura)'), range(0, 1.5, 0.05, c.temperature, (v) => { c.temperature = v; }), t('Baixa = mais objetivo; alta = mais criativo. Modelos com pensamento estendido ignoram este valor.'))),
      field(t('Instruções personalizadas'), h('textarea', { rows: 3, id: 'cc-instructions', maxlength: 3000, placeholder: t('Ex.: Responda sempre em português, de forma curta e com exemplos.'), oninput: (e) => { c.instructions = e.target.value; } }, c.instructions || ''), t('Entram em toda conversa do Chat, como um pedido seu ao assistente.'))),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Janela de contexto')),
      h('div', { class: 'grid2' },
        h('div', null, num('context_tokens', 1000, 2000000, 1000, t('Janela de contexto (tokens)'), t('Quanto da conversa (mais anexos e fontes da web) o ASTA envia ao modelo. Passou disso, as mensagens mais antigas saem primeiro. Nunca ponha mais do que o modelo aguenta.')), quick('context_tokens', [4000, 8000, 16000, 32000, 128000], (v) => kb(v), 'cc-context_tokens')),
        num('history_turns', 1, 100, 1, t('Máximo de turnos lembrados'), t('Pares pergunta/resposta no máximo, mesmo que caibam mais na janela.'))),
      h('p', { class: 'muted small', style: { margin: '10px 0 0' } }, t('Modelos locais têm a própria janela, definida ao carregá-los (LM Studio: Context Length; Ollama: num_ctx; GGUF embutido: n_ctx em Provedores). Este valor só limita o que o ASTA envia.'))),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Tempo de pensamento')),
      field(t('Nível padrão'), seg(levels, c.thinking, (v) => { c.thinking = v; }), t('Slow → Ultra: quanto o modelo pode «pensar» antes de responder (mais tempo e tokens, respostas melhores em problemas difíceis).')),
      h('p', { class: 'muted small', style: { margin: '6px 0 0' } }, t('O seletor aparece ao lado do nome do modelo no Chat só quando o modelo escolhido tem o recurso: Claude (pensamento estendido), modelos de raciocínio da OpenAI (o-series, GPT-5), Gemini 2.5+, gpt-oss (LM Studio/Ollama) e modelos com raciocínio no OpenRouter. Nos demais, nada é enviado. Extra high e Ultra usam o esforço mais alto do provedor com mais folga de tokens.'))),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Busca na web')),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('O botão Web do Chat pesquisa a sua pergunta (ou o prompt de uma ferramenta de criação), lê as primeiras páginas e entrega ao modelo com as fontes numeradas. Funciona com qualquer modelo, inclusive local. Sem chave, usa o DuckDuckGo e, se falhar, a Wikipédia.')),
      checkbox(t('Deixar a busca na web ligada por padrão'), c.web.default, (v) => { w.default = v; }),
      h('div', { class: 'grid2', style: { marginTop: '12px' } },
        field(t('Motor de busca'), select([['auto', t('Automático (DuckDuckGo → Wikipédia)')], ['duckduckgo', 'DuckDuckGo'], ['wikipedia', t('Wikipédia')], ['brave', 'Brave Search (' + t('chave') + ')'], ['tavily', 'Tavily (' + t('chave') + ')'], ['searxng', 'SearXNG (' + t('sua instância') + ')']], w.engine, (v) => { w.engine = v; })),
        field(t('Idioma da busca'), select([['auto', t('Automático')], ['pt', 'Português'], ['en', 'English']], w.language, (v) => { w.language = v; }))),
      h('div', { class: 'grid2' }, num('results', 1, 10, 1, t('Resultados por busca'), '', w), num('read_pages', 0, 5, 1, t('Páginas lidas por inteiro'), t('0 = só os títulos e trechos. Ler mais páginas dá respostas melhores, porém mais lentas e com mais tokens.'), w)),
      h('div', { class: 'grid2' }, keyField('brave_key', t('Chave da Brave Search'), c.web.brave_key_set), keyField('tavily_key', t('Chave da Tavily'), c.web.tavily_key_set)),
      field(t('Endereço da instância SearXNG'), h('input', { id: 'cc-searxng_url', value: w.searxng_url || '', placeholder: 'http://localhost:8080', oninput: (e) => { w.searxng_url = e.target.value.trim(); } }), t('A instância precisa permitir o formato json (search.formats em settings.yml).')),
      h('div', { class: 'row' }, h('button', { class: 'btn', id: 'cc-test', type: 'button', onclick: test }, icon('globe', 15), t('Testar busca'))), results),
    h('div', { class: 'row', style: { justifyContent: 'flex-end' } }, h('button', { class: 'btn primary', id: 'cc-save', onclick: async () => {
      const patch = JSON.parse(JSON.stringify(c)); delete patch.web.brave_key_set; delete patch.web.tavily_key_set; delete patch.web.brave_key; delete patch.web.tavily_key;
      if (keys.brave) patch.web.brave_key = keys.brave;
      if (keys.tavily) patch.web.tavily_key = keys.tavily;
      await saveSettings({ chat: patch }); await refreshState(); toast(t('Salvo'), 'ok'); } }, icon('check', 15), t('Salvar'))));
}

// ---------------------------------------------------------------------------------- voz
async function voice() {
  const v = JSON.parse(JSON.stringify(state.settings.voice));
  const block = (key, title, extra) => {
    const x = v[key];
    return h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, title),
      field(t('Motor'), seg([['browser', t('Navegador (grátis)')], ['server', t('Servidor compatível com OpenAI')]], x.engine, (val) => { x.engine = val; })),
      h('div', { class: 'grid2' }, field(t('URL base'), h('input', { value: x.base_url, placeholder: 'https://api.openai.com/v1  ·  http://localhost:8000/v1', oninput: (e) => { x.base_url = e.target.value.trim(); } })),
        field(t('Chave de API'), h('input', { type: 'password', autocomplete: 'off', placeholder: state.settings.voice[key].api_key_set ? '•••••••• (' + t('salva') + ')' : '', oninput: (e) => { x.api_key = e.target.value; } }))),
      h('div', { class: 'grid2' }, field(t('Modelo'), h('input', { value: x.model, oninput: (e) => { x.model = e.target.value.trim(); } })), extra(x)));
  };
  return h('div', null,
    h('p', { class: 'muted', style: { marginTop: 0 } }, t('Por padrão a voz usa o navegador (reconhecimento e síntese), sem custo e em vários idiomas. Para vozes de modelos — nuvem ou 100% locais (Whisper, Kokoro, Piper… atrás de uma API compatível com OpenAI) — configure um servidor abaixo.')),
    block('stt', t('Reconhecimento de fala (STT)'), (x) => field(t('Idioma (vazio/auto = detectar)'), h('input', { value: x.lang, oninput: (e) => { x.lang = e.target.value.trim() || 'auto'; } }))),
    block('tts', t('Síntese de voz (TTS)'), (x) => field(t('Voz padrão'), h('input', { value: x.voice, placeholder: 'alloy', oninput: (e) => { x.voice = e.target.value; } }))),
    h('div', { class: 'row', style: { justifyContent: 'flex-end' } }, h('button', { class: 'btn primary', onclick: async () => {
      const clean = (x) => { const o = Object.assign({}, x); delete o.api_key_set; if (!o.api_key) delete o.api_key; return o; };
      await saveSettings({ voice: { stt: clean(v.stt), tts: clean(v.tts) } }); await refreshState(); toast(t('Salvo'), 'ok'); } }, icon('check', 15), t('Salvar'))));
}

// ---------------------------------------------------------------------------------- modelos locais (Hugging Face)
async function local() {
  let kind = 'text';
  const ram = state.hardware.ram_gb || 8;
  const kindHint = h('p', { class: 'muted small', style: { margin: '10px 0 0' } }), results = h('div', { class: 'col' }), files = h('div', { class: 'col', style: { marginTop: '14px' } }), installed = h('div', { class: 'col' }), prog = h('div');
  const tokenIn = h('input', { type: 'password', autocomplete: 'off', placeholder: state.settings.hf.token_set ? '•••••••• (' + t('salvo') + ')' : 'hf_…' });
  const q = h('input', { type: 'search', placeholder: t('Buscar modelos GGUF (ex.: qwen, llama, gemma, mistral)…'), onkeydown: (e) => { if (e.key === 'Enter') search(); } });

  async function paintInstalled() {
    const { models } = await api('/api/hf/local?kind=' + kind);
    installed.replaceChildren(...(models.length ? models.map((m) => h('div', { class: 'row nw', style: { padding: '10px 0', borderBottom: '1px solid var(--line)' } },
      h('div', { class: 'grow' }, h('div', { class: 'mono', style: { fontSize: '13px' } }, m.name), h('div', { class: 'dim small' }, fmtBytes(m.size) + (m.parts > 1 ? ' · ' + t('{n} partes', { n: m.parts }) : ''))),
      m.quant ? h('span', { class: 'chip solid', title: t(QUALITY_LABEL[m.quality] || '') }, m.quant) : null,
      ...(kind === 'text' ? [
        h('button', { class: 'btn sm', onclick: async () => { await saveSettings({ providers: { local_hf: { model: m.name } }, active: { generation: 'local_hf' } }); toast(t('Usando na geração'), 'ok'); } }, t('Usar na geração')),
        h('button', { class: 'btn sm', onclick: async () => { await saveSettings({ providers: { local_hf: { model: m.name } }, active: { characters: 'local_hf' } }); toast(t('Usando nos personagens'), 'ok'); } }, t('Usar nos personagens'))]
        : (kind === 'image' || kind === 'video') ? [h('button', { class: 'btn sm', onclick: async () => { await saveSettings({ media: { models: { gguf_local: { [kind]: m.name } }, active: { [kind]: 'gguf_local' } } }); toast(t('Usando no Canvas'), 'ok'); } }, kind === 'image' ? t('Usar no Canvas (imagem)') : t('Usar no Canvas (vídeo)'))]
        : []),
      h('button', { class: 'btn sm ghost danger', onclick: async () => { if (await confirmDialog(t('Apagar o arquivo {n}?', { n: m.name }))) { await api('/api/hf/local/' + encodeURIComponent(m.name) + '?kind=' + kind, { method: 'DELETE' }); paintInstalled(); } } }, icon('trash', 13)))) :
      [h('div', { class: 'muted small' }, t('Nenhum modelo baixado ainda.'))]));
  }
  async function search() {
    results.replaceChildren(h('div', { class: 'spinner' }));
    try {
      const r = await api('/api/hf/search?q=' + encodeURIComponent(q.value || 'gguf') + '&kind=' + kind);
      results.replaceChildren(...r.results.map((m) => h('div', { class: 'li', onclick: () => openRepo(m.id) }, h('div', { class: 'grow', style: { minWidth: 0 } }, h('div', { class: 't' }, m.id), h('div', { class: 's' }, '⬇ ' + (m.downloads || 0).toLocaleString() + ' · ♥ ' + (m.likes || 0))), icon('chev', 15))));
    } catch (e) { results.replaceChildren(h('div', { class: 'res err' }, e.message)); }
  }
  async function openRepo(repo) {
    files.replaceChildren(h('div', { class: 'spinner' }));
    try {
      const [r, loc] = await Promise.all([api('/api/hf/files?repo=' + encodeURIComponent(repo)), api('/api/hf/local?kind=' + kind)]);
      const have = new Set(loc.models.map((m) => m.name));
      if (!r.files.length) return files.replaceChildren(h('div', { class: 'res err' }, t('Nenhum arquivo GGUF utilizável neste repositório.')));
      let pick = null;  // nada vem escolhido: o usuário decide a quantização antes de qualquer download
      const list = h('div', { class: 'col', style: { gap: '6px' } }), btn = h('button', { class: 'btn primary' });
      const paint = () => {
        list.replaceChildren(...r.files.map((f) => h('label', { class: 'quant' + (f === pick ? ' on' : ''), onclick: () => { pick = f; paint(); } },
          h('input', { type: 'radio', name: 'quant', checked: f === pick }),
          h('div', { class: 'grow', style: { minWidth: 0 } },
            h('div', { class: 'row', style: { gap: '8px' } }, h('b', null, f.quant || t('sem rótulo')), f.quality ? h('span', { class: 'dim small' }, t(QUALITY_LABEL[f.quality])) : null,
              f.recommended ? h('span', { class: 'chip on' }, t('Recomendada')) : null, have.has(f.name) ? h('span', { class: 'chip' }, t('Já baixado')) : null, f.parts > 1 ? h('span', { class: 'chip' }, t('{n} partes', { n: f.parts })) : null),
            h('div', { class: 'mono dim', style: { fontSize: '11px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, f.name)),
          h('span', { class: 'chip ' + (f.fits ? 'solid' : '') }, fmtBytes(f.size) + (f.fits ? ' ✓' : ' ⚠')))));
        btn.disabled = !pick;
        btn.replaceChildren(icon('download', 14), pick ? t('Baixar {q} ({s})', { q: pick.quant || pick.name, s: fmtBytes(pick.size) }) : t('Escolha uma quantização para baixar'));
      };
      btn.onclick = () => pick && dl(repo, pick);
      paint();
      files.replaceChildren(h('div', { class: 'small muted' }, repo + ' — ' + t('Escolha a quantização: menos bits = arquivo menor e mais rápido, mas com menos qualidade. Sua RAM: {n} GB; ✓ = cabe (até ~60% da RAM).', { n: ram })), list, h('div', { style: { marginTop: '10px' } }, btn));
    } catch (e) { files.replaceChildren(h('div', { class: 'res err' }, e.message)); }
  }
  async function dl(repo, f) {
    const file = f.name, size = f.size;
    const fitNote = f.fits ? t('Cabe na sua RAM.') : t('Pode não caber na sua RAM ({n} GB).', { n: ram });
    if (!(await confirmDialog(t('Baixar {q} de {r}? Tamanho: {s}. {f}', { q: f.quant || f.name, r: repo, s: fmtBytes(size), f: fitNote }), false, t('Baixar')))) return;
    if (size / 1024 ** 3 > ram * 0.9 && !(await confirmDialog(t('Este modelo é maior que a sua RAM e provavelmente ficará muito lento. Baixar mesmo assim?'), false, t('Baixar')))) return;
    const bar = h('i'), label = h('span', { class: 'small muted' }, '0%');
    prog.replaceChildren(h('div', { class: 'card' }, h('div', { class: 'row', style: { marginBottom: '8px' } }, h('span', { class: 'mono small' }, file), h('span', { class: 'grow' }), label, h('button', { class: 'btn sm', id: 'dl-cancel' }, t('Cancelar'))), h('div', { class: 'bar' }, bar)));
    let jid;
    try { jid = (await api('/api/hf/download', { method: 'POST', body: { repo, files: f.files, sizes: f.sizes, quant: f.quant || 'sem-rotulo', kind } })).job_id; } catch (e) { return toast(e.message, 'err'); }
    prog.querySelector('#dl-cancel').onclick = () => api('/api/jobs/' + jid + '/cancel', { method: 'POST' });
    events('/api/jobs/' + jid + '/events', (ev) => {
      if (ev.type === 'progress' && ev.total) { const p = ev.done / ev.total; bar.style.width = Math.round(p * 100) + '%'; label.textContent = Math.round(p * 100) + '% · ' + fmtBytes(ev.done) + ' / ' + fmtBytes(ev.total); }
      else if (ev.type === 'done') { toast(t('Download concluído'), 'ok'); prog.replaceChildren(); paintInstalled(); }
      else if (ev.type === 'error') { toast(ev.message, 'err'); prog.replaceChildren(); }
      else if (ev.type === 'cancelled') { toast(t('Download cancelado')); prog.replaceChildren(); }
    });
  }
  // modelos pré-instalados: um de texto e um de imagem, com a quantização já definida
  const preBox = h('div', { class: 'col', style: { gap: '10px' } });
  async function paintPre() {
    let list = [];
    try { list = (await api('/api/preinstalled')).models; } catch (e) { return; }
    preBox.replaceChildren(...list.map((m) => {
      const area = h('div');
      const act = m.installed ? h('span', { class: 'chip on' }, '✓ ' + t('Instalado')) : h('button', { class: 'btn sm primary', onclick: async () => {
        const bar = h('i'), label = h('span', { class: 'small muted' }, '0%'), cancelBtn = h('button', { class: 'btn sm' }, t('Cancelar'));
        area.replaceChildren(h('div', { class: 'card', style: { marginTop: '8px' } }, h('div', { class: 'row', style: { marginBottom: '8px' } }, h('span', { class: 'grow small' }, t('Baixando {n}…', { n: m.label })), label, cancelBtn), h('div', { class: 'bar' }, bar)));
        let jid;
        try { jid = (await api('/api/preinstalled/install', { method: 'POST', body: { id: m.id } })).job_id; } catch (e) { area.replaceChildren(); return toast(e.message, 'err'); }
        cancelBtn.onclick = () => api('/api/jobs/' + jid + '/cancel', { method: 'POST' });
        events('/api/jobs/' + jid + '/events', (ev) => {
          if (ev.type === 'progress' && ev.total) { const pc = Math.min(1, ev.done / ev.total); bar.style.width = Math.round(pc * 100) + '%'; label.textContent = Math.round(pc * 100) + '% · ' + fmtBytes(ev.done) + ' / ' + fmtBytes(ev.total); }
          else if (ev.type === 'done') { toast(t('{n} pronto para usar.', { n: m.label }), 'ok'); refreshState().then(() => { renderSide(); paintPre(); paintInstalled(); }); }
          else if (ev.type === 'error') { toast(ev.message, 'err'); area.replaceChildren(); }
          else if (ev.type === 'cancelled') { toast(t('Download cancelado')); area.replaceChildren(); }
        });
      } }, icon('download', 13), t('Instalar'));
      return h('div', { class: 'prerow' },
        h('div', { class: 'row nw' }, h('div', { class: 'grow', style: { minWidth: 0 } },
          h('div', { class: 'row', style: { gap: '8px' } }, h('b', null, m.label), h('span', { class: 'chip' }, t(GGUF_KINDS.find(([k]) => k === m.kind)[1])), h('span', { class: 'chip solid' }, m.quant), m.n_ctx ? h('span', { class: 'chip', title: t('Janela de contexto base; ajustável em Provedores → Hugging Face GGUF') }, t('Contexto {n}', { n: Math.round(m.n_ctx / 1024) + 'K' })) : null, h('span', { class: 'dim small' }, fmtBytes(m.size))),
          h('div', { class: 'dim small' }, t(m.hint)), h('div', { class: 'mono dim', style: { fontSize: '11px' } }, m.source + ' · ' + m.repo + ' · ' + m.license)), act), area);
    }));
  }
  const kindSeg = h('div', { class: 'seg', style: { marginBottom: '14px', flexWrap: 'wrap' } });
  const paintKind = () => {
    kindSeg.replaceChildren(...GGUF_KINDS.map(([k, l]) => h('button', { type: 'button', class: kind === k ? 'on' : '', onclick: () => { kind = k; results.replaceChildren(); files.replaceChildren(); paintKind(); paintInstalled(); } }, t(l))));
    kindHint.textContent = t(GGUF_HINT[kind]);
    q.placeholder = kind === 'text' ? t('Buscar modelos GGUF (ex.: qwen, llama, gemma, mistral)…') : t('Buscar modelos GGUF de {k} (ex.: flux, wan, outetts, qwen-vl)…', { k: t(GGUF_KINDS.find(([x]) => x === kind)[1]).toLowerCase() });
  };
  paintKind();
  await paintInstalled();
  await paintPre();
  return h('div', null,
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Modelos pré-instalados')),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Vêm com o ASTA (baixados pelo instalador) e já com a quantização definida: um modelo de texto e um de imagem. Para outras quantizações ou outros modelos, use a busca abaixo.')), preBox),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Modelos locais do Hugging Face')), kindSeg,
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Baixe modelos GGUF direto do Hugging Face e rode-os no seu computador. Requer o extra opcional:'), ' ', h('span', { class: 'kbd' }, 'pip install "asta[local]"'), ' ', t('Alternativa sem instalar nada: use Ollama ou LM Studio (aba Provedores).')), kindHint,
      h('div', { class: 'row nw' }, h('div', { class: 'search', style: { maxWidth: 'none' } }, icon('search', 17), q), h('button', { class: 'btn', onclick: search }, t('Buscar'))),
      h('div', { style: { marginTop: '12px' } }, results), files),
    prog,
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Baixados')), installed),
    h('div', { class: 'card' }, h('h3', null, t('Token do Hugging Face (opcional)')), h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Necessário apenas para modelos restritos (gated).')),
      h('div', { class: 'row nw' }, tokenIn, h('button', { class: 'btn', onclick: async () => { if (tokenIn.value) { await saveSettings({ hf: { token: tokenIn.value } }); await refreshState(); toast(t('Salvo'), 'ok'); } } }, t('Salvar')))));
}

// ---------------------------------------------------------------------------------- sistema
// ---------------------------------------------------------------------------------- aparência e preferências
async function appearance() {
  const save = async (patch, quiet) => { await saveSettings({ ui: patch }); if (!quiet) toast(t('Salvo'), 'ok'); };
  const U = () => ui();
  const card = (title, ...kids) => h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, title), ...kids);
  const HIDEABLE = [['worlds', 'Mundos'], ['avatars', 'Avatars'], ['games', 'Jogos 2D'], ['canvas', 'Canvas'], ['studio', 'Studio'], ['rebuild', 'Rebuild'], ['library', 'Biblioteca']];
  const hidden = new Set(U().sidebar_hidden);
  const importInput = h('input', { type: 'file', accept: '.json,application/json', class: 'hidden', onchange: async (e) => {
    const f = e.target.files[0]; e.target.value = ''; if (!f) return;
    try {
      const r = await api('/api/settings/import', { method: 'POST', body: JSON.parse(await f.text()) });
      toast(t('Configurações importadas: {n}.', { n: r.imported.join(', ') }), 'ok'); await refreshState(); location.reload();
    } catch (er) { toast(er instanceof SyntaxError ? t('Este arquivo não é um JSON válido.') : er.message, 'err'); }
  } });
  return h('div', null,
    card(t('Tema'), themeCards(U().theme, (v) => save({ theme: v })),
      h('div', { class: 'field', style: { marginTop: '16px', marginBottom: 0 } }, h('label', { class: 'f' }, t('Cor de destaque')), accentSwatches(U().accent, (v) => save({ accent: v }, true)),
        h('div', { class: 'hint' }, t('Usada em botões, seleções e na sua mensagem no chat.')))),
    card(t('Leitura e conforto'),
      h('div', { class: 'grid2' },
        field(t('Tamanho da interface'), seg([[90, '90%'], [100, '100%'], [110, '110%'], [125, '125%'], [150, '150%']], U().scale, (v) => save({ scale: v })), t('Aumenta ou diminui tudo; útil em telas grandes ou pequenas.')),
        field(t('Densidade'), seg([['comfortable', t('Confortável')], ['compact', t('Compacta')]], U().density, (v) => save({ density: v })), t('Compacta mostra mais conteúdo na tela.'))),
      h('div', { class: 'grid2' },
        field(t('Fonte'), seg([['system', t('Sistema')], ['serif', t('Serifada')], ['mono', t('Monoespaçada')]], U().font, (v) => save({ font: v }))),
        field(t('Texto do chat dos avatares'), seg([['small', t('Pequeno')], ['medium', t('Médio')], ['large', t('Grande')]], U().chat_size, (v) => save({ chat_size: v })))),
      field(t('Animações'), select([['auto', t('Automático (segue o sistema)')], ['reduce', t('Reduzir animações')], ['full', t('Sempre animar')]], U().motion, (v) => save({ motion: v })), t('“Reduzir” desliga transições e animações — bom para sensibilidade a movimento.'))),
    card(t('Uso'),
      h('div', { class: 'grid2' },
        field(t('Idioma da interface'), select([['auto', t('Automático (navegador)')], ['pt-BR', 'Português (Brasil)'], ['en', 'English']], state.settings.language, async (v) => { await saveSettings({ language: v }); location.reload(); })),
        field(t('Enviar mensagens com'), seg([['enter', 'Enter'], ['ctrl_enter', 'Ctrl+Enter']], U().send_key, (v) => save({ send_key: v })),
          t('Com Enter, use Shift+Enter para quebrar a linha; com Ctrl+Enter, o Enter quebra a linha. Vale para o chat e para a caixa de criação.'))),
      field(t('Tela inicial'), select([['main', 'Chat'], ['last', t('A última tela que eu usei')], ['avatars', 'Avatars'], ['worlds', t('Mundos')], ['games', t('Jogos 2D')], ['canvas', 'Canvas'], ['library', t('Biblioteca')]], U().start_page, (v) => save({ start_page: v })),
        t('Qual tela abre quando você entra no ASTA.')),
      checkbox(t('Atalhos de teclado (Alt+1…7, Alt+B, Alt+T, ?) — Ctrl+K (busca) sempre funciona'), U().shortcuts, (v) => save({ shortcuts: v }, true)),
      h('div', { class: 'row', style: { marginTop: '8px' } }, h('button', { class: 'btn sm', onclick: () => window.dispatchEvent(new KeyboardEvent('keydown', { key: '?', bubbles: true })) }, t('Ver atalhos')),
        h('button', { class: 'btn sm', onclick: () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true })) }, icon('search', 13), t('Abrir a busca (Ctrl+K)')))),
    card(t('Barra lateral'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Esconda as telas que você não usa. “Chat” e “Configuração” ficam sempre; o que está escondido continua acessível pela busca (Ctrl+K).')),
      h('div', { class: 'row', style: { gap: '18px' } }, HIDEABLE.map(([id, label]) => checkbox(t(label), !hidden.has(id), async (on) => { on ? hidden.delete(id) : hidden.add(id); await save({ sidebar_hidden: [...hidden] }, true); })))),
    card(t('Backup e padrões'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Leve suas preferências para outro computador. A exportação nunca inclui chaves de API nem tokens.')),
      h('div', { class: 'row' },
        h('button', { class: 'btn sm', onclick: async () => { const r = await fetch('/api/settings/export'); download('asta-configuracoes.json', await r.text()); toast(t('Configurações exportadas (sem chaves de API).'), 'ok'); } }, icon('download', 13), t('Exportar configurações')),
        h('button', { class: 'btn sm', onclick: () => importInput.click() }, icon('upload', 13), t('Importar configurações')), importInput,
        h('button', { class: 'btn sm', onclick: () => window.ASTA_WELCOME && window.ASTA_WELCOME() }, t('Rever as boas-vindas')),
        h('span', { class: 'grow' }),
        h('button', { class: 'btn sm danger', onclick: async () => { if (await confirmDialog(t('Voltar a aparência e as preferências de uso ao padrão? Suas chaves, avatares e projetos não mudam.'), true, t('Restaurar'))) { await api('/api/settings/reset', { method: 'POST', body: { section: 'ui' } }); await refreshState(); location.reload(); } } }, t('Restaurar padrões da aparência')))));
}

async function system() {
  const hw = state.hardware;
  const cmd = (label, text) => h('div', { class: 'field' }, h('label', { class: 'f' }, label), h('div', { class: 'codebox' }, h('span', null, text), h('button', { class: 'btn sm ghost', onclick: () => { navigator.clipboard.writeText(text).then(() => toast(t('Copiado'))); } }, icon('copy', 13))));
  const pf = Object.assign({ mode: 'auto', idle_unload_min: 10 }, state.settings.performance || {});
  const nat = state.native || {};
  const perfCard = h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Desempenho')),
    h('div', { class: 'grid2' },
      field(t('Modo'), select([['auto', t('Automático (conforme o hardware)')], ['light', t('Leve — menos RAM/VRAM')], ['balanced', t('Equilibrado')], ['max', t('Máximo')]], pf.mode, async (v) => { pf.mode = v; await saveSettings({ performance: pf }); toast(t('Salvo'), 'ok'); }),
        t('Leve: limita a janela de contexto, comprime o cache de atenção, descarrega modelos ociosos e usa menos memória de vídeo nos modelos de imagem/vídeo.')),
      field(t('Descarregar modelos ociosos após (min)'), h('input', { type: 'number', min: 0, max: 1440, value: pf.idle_unload_min, onchange: async (e) => { pf.idle_unload_min = Math.max(0, parseInt(e.target.value || '0', 10)); await saveSettings({ performance: pf }); toast(t('Salvo'), 'ok'); } }), t('0 = nunca. No modo leve o limite é de até 3 min.'))),
    h('dl', { class: 'kv', style: { margin: 0 } }, h('dt', null, t('Núcleo Rust')), h('dd', null, nat.active ? h('span', { class: 'chip on' }, t('ativo')) : h('span', { class: 'muted' }, t('inativo — usando Python puro'))),
      h('dt', null, 'cargo'), h('dd', null, nat.cargo ? t('encontrado') : t('não encontrado (opcional)'))),
    h('p', { class: 'muted small', style: { marginBottom: 0 } }, t('O núcleo Rust acelera a síntese de áudio do Canvas e usa bem menos memória. Para ativar: rode “asta native setup” no terminal (instala/atualiza o Rust com a sua permissão e compila o núcleo). Sem ele, tudo funciona igual em Python.')));
  return h('div', null, perfCard,
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Seu hardware')),
      h('dl', { class: 'kv', style: { margin: 0 } }, h('dt', null, t('Sistema')), h('dd', null, hw.os + ' · ' + hw.arch), h('dt', null, 'CPU'), h('dd', null, t('{n} núcleos', { n: hw.cpus })),
        h('dt', null, 'RAM'), h('dd', null, hw.ram_gb ? hw.ram_gb + ' GB' : '—'), h('dt', null, 'GPU'), h('dd', null, hw.gpu || t('não detectada (NVIDIA)')),
        h('dt', null, 'ffmpeg'), h('dd', null, hw.ffmpeg ? t('instalado — análise de vídeo/áudio ativa') : t('não encontrado (opcional)')), h('dt', null, t('Nível')), h('dd', null, h('span', { class: 'chip on' }, hw.tier))),
      h('p', { class: 'muted small', style: { marginBottom: 0 } }, t('Os mundos se adaptam a este nível ao serem gerados e, ao jogar, ajustam resolução/sombras/distância em tempo real conforme o hardware de quem joga.'))),
    h('div', { class: 'card' }, h('h3', null, 'ASTA v' + state.version),
      h('dl', { class: 'kv', style: { marginTop: 0 } }, h('dt', null, t('Pasta de dados')), h('dd', { class: 'mono small' }, state.home), h('dt', null, t('Licença')), h('dd', null, 'MIT')),
      cmd(t('Atualizar (Linux/macOS)'), 'curl -fsSL https://raw.githubusercontent.com/KMC1525/ASTA/main/install.sh | sh'),
      cmd(t('Atualizar (Windows PowerShell)'), 'irm https://raw.githubusercontent.com/KMC1525/ASTA/main/install.ps1 | iex'),
      cmd(t('Ou, no terminal'), 'asta update'),
      h('p', { class: 'muted small', style: { marginBottom: 0 } }, t('O mesmo comando instala e atualiza. Depois de atualizar, use “Reconstruir com o motor mais recente” na Biblioteca para levar melhorias aos mundos antigos.'))));
}

// ---------------------------------------------------------------------------------- mídia (Canvas)
const CAPS = [['image', 'Imagem'], ['video', 'Vídeo'], ['sound', 'Som e música'], ['voice', 'Voz (texto → fala)'], ['stt', 'Transcrição (fala → texto)']];
async function media() {
  let data = await api('/api/media/providers');
  const container = h('div');
  const paint = () => container.replaceChildren(defaults(), h('div', null, data.providers.filter((p) => p.id !== 'demo').map(card)), demoCard());

  const reload = async () => { data = await api('/api/media/providers'); await refreshState(); paint(); };
  function defaults() {
    return h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Modelo padrão de cada tipo de mídia')),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Cada nó do Canvas pode escolher outro provedor. Aqui fica o padrão do projeto. “Demo” funciona offline, sem IA, para testar os fluxos.')),
      h('div', { class: 'grid2' }, CAPS.map(([cap, label]) => field(t(label), select(data.providers.filter((p) => p.caps.includes(cap)).map((p) => [p.id, t(p.label) + (p.needs_key && !p.has_key ? ' · ' + t('sem chave') : '')]), data.active[cap] || 'demo',
        async (v) => { await saveSettings({ media: { active: { [cap]: v } } }); data.active[cap] = v; toast(t('Salvo'), 'ok'); })))));
  }
  function demoCard() {
    const d = data.providers.find((p) => p.id === 'demo');
    return h('div', { class: 'card', style: { marginTop: '16px' } }, h('h3', null, t(d.label)), h('p', { class: 'muted small', style: { margin: 0 } }, t(d.hint)));
  }
  function card(p) {
    const draft = { key: '', url: p.base_url === p.default_url ? '' : p.base_url, models: Object.assign({}, p.models) };
    const configured = (!p.needs_key || p.has_key) && (p.id !== 'custom' || p.base_url);
    const res = h('div', { class: 'res' });
    const inUse = CAPS.filter(([cap]) => data.active[cap] === p.id).map(([, l]) => t(l));
    const body = h('div', { class: 'bd' });
    const inputs = [];
    if (p.needs_key) inputs.push(field(t('Chave de API'), h('div', { class: 'row nw' },
      h('input', { type: 'password', autocomplete: 'off', placeholder: p.has_key ? '•••••••• (' + t('salva') + ')' : 'sk-…', oninput: (e) => { draft.key = e.target.value; } }),
      p.has_key ? h('button', { class: 'btn sm danger', onclick: async () => { await saveSettings({ providers: { [p.id]: { api_key: null } } }); toast(t('Chave removida')); reload(); } }, t('Remover')) : null),
      p.docs ? h('a', { href: p.docs, target: '_blank', rel: 'noopener', class: 'muted' }, t('Obter chave →')) : null));
    if (p.local || p.id === 'custom' || p.default_url) {
      if (p.id !== 'local_hf' && p.id !== 'voice_settings') inputs.push(field(t('Endereço do servidor'), h('input', { value: draft.url, placeholder: p.default_url || 'http://127.0.0.1:8000/v1', oninput: (e) => { draft.url = e.target.value.trim(); } })));
    }
    const listId = 'mm-' + p.id;
    inputs.push(h('datalist', { id: listId }));
    const modelCaps = CAPS.filter(([cap]) => p.caps.includes(cap) && p.id !== 'voice_settings' && p.id !== 'a1111');
    if (p.id === 'local_hf') inputs.push(localModels(p, draft));
    else if (modelCaps.length) inputs.push(h('div', { class: 'grid2' }, modelCaps.map(([cap, label]) => {
      const dl = h('datalist', { id: listId + cap }, ((p.suggest || {})[cap] || []).map((m) => h('option', { value: m })));
      return field(t('Modelo') + ' · ' + t(label), h('div', null, h('input', { list: listId + cap, value: draft.models[cap] || '', placeholder: t('padrão do provedor'), oninput: (e) => { draft.models[cap] = e.target.value.trim(); } }), dl));
    })));
    if (p.hint) inputs.push(h('p', { class: 'muted small' }, t(p.hint)));
    const test = async () => {
      res.className = 'res'; res.textContent = t('Testando…');
      try { const r = await api('/api/media/test', { method: 'POST', body: { provider: p.id } }); res.className = 'res ok'; res.textContent = '✓ ' + r.message; }
      catch (e) { res.className = 'res err'; res.textContent = '✗ ' + e.message; }
    };
    const save = async () => {
      const patch = { media: { models: { [p.id]: draft.models }, urls: { [p.id]: draft.url } } };
      if (draft.key) patch.providers = { [p.id]: { api_key: draft.key } };
      await saveSettings(patch); toast(t('Salvo'), 'ok'); reload();
    };
    inputs.push(h('div', { class: 'row', style: { marginTop: '8px' } }, h('button', { class: 'btn sm primary', onclick: save }, t('Salvar')), h('button', { class: 'btn sm', onclick: async () => { await save(); test(); } }, t('Salvar e testar')),
      h('span', { class: 'dim small' }, t('Use “Salvar e testar” para conferir a conexão.'))), res);
    body.replaceChildren(...inputs);
    const cardEl = h('div', { class: 'prov' + (inUse.length ? ' open' : '') });
    cardEl.append(h('div', { class: 'hd', onclick: () => cardEl.classList.toggle('open') },
      h('span', { class: 'dot', style: { width: '8px', height: '8px', borderRadius: '50%', background: configured ? 'var(--ok)' : 'var(--dim)' } }),
      h('span', { class: 'nm' }, t(p.label)), p.local ? h('span', { class: 'badge' }, t('local')) : null,
      h('span', { class: 'dim small', style: { marginLeft: '8px' } }, p.caps.map((c) => t((CAPS.find((x) => x[0] === c) || [0, c])[1])).join(' · ')),
      h('span', { class: 'roles' }, inUse.map((l) => h('span', { class: 'chip on' }, l)))), body);
    return cardEl;
  }
  paint();
  return container;
}

// Modelos locais do Canvas (diffusers/transformers): a precisão (quantização) é escolhida ANTES de qualquer download; nada baixa sozinho.
function localModels(p, draft) {
  const box = h('div', { class: 'col', style: { gap: '10px' } });
  const rows = {}, chips = {};
  const caps = CAPS.filter(([cap]) => p.caps.includes(cap));
  const modelOf = (cap) => draft.models[cap] || p.models[cap] || '';
  const setChip = (cap, prec) => { chips[cap].className = 'chip ' + (prec ? 'on' : ''); chips[cap].textContent = prec ? t('baixado · {p}', { p: prec }) : t('não baixado'); };
  async function refresh() {
    try {
      const st = await api('/api/media/local/state');
      if (!st.libs) { hint.textContent = t('Instale as bibliotecas dos modelos locais para baixá-los:') + ' pip install "asta[media]"  (' + t('ou rode') + ' asta libs)'; }
      for (const [cap] of caps) setChip(cap, (st.models[cap] && st.models[cap].model === modelOf(cap) && st.models[cap].precision) || '');
    } catch (e) { /* sem estado: os chips ficam como "não baixado" */ }
  }
  const hint = h('p', { class: 'muted small', style: { margin: 0 } }, t('Escolha o modelo de cada tipo e, antes de usá-lo, a precisão (quantização) do download: o ASTA só baixa depois da sua escolha e só carrega o que você baixou.'));
  function panel(cap) {
    const model = modelOf(cap), area = rows[cap].area;
    if (!/^[\w.-]+\/[\w.-]+$/.test(model)) return toast(t('Informe o modelo no formato dono/nome (ex.: stabilityai/sd-turbo).'), 'err');
    area.replaceChildren(h('div', { class: 'spinner' }));
    api('/api/media/local/options?model=' + encodeURIComponent(model)).then((r) => {
      let pick = null;
      const list = h('div', { class: 'col', style: { gap: '6px' } }), btn = h('button', { class: 'btn primary' });
      const paint = () => {
        list.replaceChildren(...r.options.map((o) => h('label', { class: 'quant' + (o === pick ? ' on' : ''), onclick: () => { pick = o; paint(); } },
          h('input', { type: 'radio', name: 'prec-' + cap, checked: o === pick }),
          h('div', { class: 'grow' }, h('div', { class: 'row', style: { gap: '8px' } }, h('b', null, o.id), o.recommended ? h('span', { class: 'chip on' }, t('Recomendada')) : null),
            h('div', { class: 'dim small' }, t(PREC_HINT[o.id]))),
          h('span', { class: 'chip solid' }, o.size ? fmtBytes(o.size) : '?'))));
        btn.disabled = !pick;
        btn.replaceChildren(icon('download', 14), pick ? t('Baixar {q} ({s})', { q: model + ' · ' + pick.id, s: pick.size ? fmtBytes(pick.size) : '?' }) : t('Escolha uma precisão para baixar'));
      };
      btn.onclick = async () => {
        if (!pick) return;
        const bar = h('i'), label = h('span', { class: 'small muted' }, '0%');
        area.replaceChildren(h('div', { class: 'card' }, h('div', { class: 'row', style: { marginBottom: '8px' } }, h('span', { class: 'mono small' }, model + ' · ' + pick.id), h('span', { class: 'grow' }), label, h('button', { class: 'btn sm', id: 'lm-cancel-' + cap }, t('Cancelar'))), h('div', { class: 'bar' }, bar)));
        let jid;
        try { await saveSettings({ media: { models: { local_hf: { [cap]: model } } } }); jid = (await api('/api/media/local/download', { method: 'POST', body: { model, precision: pick.id } })).job_id; }
        catch (e) { area.replaceChildren(); return toast(e.message, 'err'); }
        area.querySelector('#lm-cancel-' + cap).onclick = () => api('/api/jobs/' + jid + '/cancel', { method: 'POST' });
        events('/api/jobs/' + jid + '/events', (ev) => {
          if (ev.type === 'progress' && ev.total) { const pc = Math.min(1, ev.done / ev.total); bar.style.width = Math.round(pc * 100) + '%'; label.textContent = Math.round(pc * 100) + '% · ' + fmtBytes(ev.done) + ' / ' + fmtBytes(ev.total); }
          else if (ev.type === 'done') { toast(t('Download concluído'), 'ok'); area.replaceChildren(); refresh(); }
          else if (ev.type === 'error') { toast(ev.message, 'err'); area.replaceChildren(); }
          else if (ev.type === 'cancelled') { toast(t('Download cancelado')); area.replaceChildren(); }
        });
      };
      paint();
      area.replaceChildren(h('div', { class: 'small muted' }, t('Escolha a precisão: menos bits = download menor e mais rápido, com um pequeno custo de qualidade; o fp16 pede placa de vídeo.')), list, h('div', { style: { marginTop: '8px' } }, btn));
    }).catch((e) => { area.replaceChildren(h('div', { class: 'res err' }, e.message)); });
  }
  for (const [cap, label] of caps) {
    const dl = h('datalist', { id: 'lm-' + cap }, ((p.suggest || {})[cap] || []).map((m) => h('option', { value: m })));
    const input = h('input', { list: 'lm-' + cap, value: draft.models[cap] || '', placeholder: p.models[cap] || '', oninput: (e) => { draft.models[cap] = e.target.value.trim(); setChip(cap, ''); } });
    chips[cap] = h('span', { class: 'chip' }, t('não baixado'));
    rows[cap] = { area: h('div') };
    box.append(h('div', null, h('label', { class: 'f' }, t('Modelo') + ' · ' + t(label)), h('div', { class: 'row nw' }, input, dl, chips[cap], h('button', { class: 'btn sm', onclick: () => panel(cap) }, icon('download', 13), t('Precisão e download'))), rows[cap].area));
  }
  refresh();
  return h('div', { class: 'col', style: { gap: '10px', marginBottom: '8px' } }, hint, box);
}

// ---------------------------------------------------------------------------------- avatars e jogos 2D
async function creative() {
  const av = JSON.parse(JSON.stringify(state.settings.avatars)), g = JSON.parse(JSON.stringify(state.settings.games));
  const num = (obj, key, min, max, step) => h('input', { type: 'number', min, max, step: step || 1, value: obj[key], oninput: (e) => { const v = parseFloat(e.target.value); if (!Number.isNaN(v)) obj[key] = v; } });
  return h('div', null,
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Avatars')),
      h('div', { class: 'grid2' },
        field(t('Conteúdo padrão ao criar avatars'), seg([['sfw', 'SFW'], ['nsfw', 'NSFW']], av.content, (v) => { av.content = v; }), t('Cada avatar tem a própria escolha. NSFW só vale para personagens adultos: menores de idade são sempre SFW e nunca viram par romântico.')),
        field(t('Como os avatars chamam você'), h('input', { value: av.user_name, placeholder: t('automático'), oninput: (e) => { av.user_name = e.target.value; } }))),
      field(t('Sua persona (opcional)'), h('textarea', { rows: 2, placeholder: t('Quem você é para os avatars: gostos, história, jeito de falar…'), oninput: (e) => { av.user_persona = e.target.value; } }, av.user_persona)),
      h('div', { class: 'grid2' }, field(t('Criatividade nas conversas'), range(0, 1.5, 0.05, av.temperature, (v) => { av.temperature = v; })), field(t('Máximo de tokens por resposta'), num(av, 'max_tokens', 50, 4000, 50))),
      h('div', { class: 'grid2' }, field(t('Memória de curto prazo (turnos)'), num(av, 'history_turns', 2, 80)), field(t('Memórias de longo prazo por avatar'), num(av, 'memory_limit', 5, 200))),
      h('div', { class: 'row' }, checkbox(t('Em grupo, os avatars conversam entre si sem você pedir'), av.auto_talk, (v) => { av.auto_talk = v; }), checkbox(t('Responder também por voz'), av.voice_reply, (v) => { av.voice_reply = v; })),
      h('div', { class: 'grid2' }, field(t('Máximo de falas seguidas entre avatars'), num(av, 'auto_talk_max', 1, 40), t('Depois disso eles esperam uma mensagem sua.')), field(t('Segundos entre falas autônomas'), num(av, 'auto_talk_delay', 1, 60)))),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Jogos 2D')),
      h('div', { class: 'grid2' }, field(t('Tamanho padrão do jogo'), seg([['short', t('Curto')], ['medium', t('Médio')], ['long', t('Longo')]], g.length, (v) => { g.length = v; })),
        field(t('Rodadas de revisão'), select([['0', t('Nenhuma (mais rápido)')], ['1', '1'], ['2', '2']], String(g.revisions), (v) => { g.revisions = parseInt(v, 10); }), t('O agente Revisor pode pedir correções.'))),
      h('div', { class: 'grid2' }, field(t('Criatividade (temperatura)'), range(0, 1.5, 0.05, g.temperature, (v) => { g.temperature = v; })), field(t('Máximo de tokens por agente'), num(g, 'max_tokens', 1000, 32000, 500)))),
    h('div', { class: 'row', style: { justifyContent: 'flex-end' } }, h('button', { class: 'btn primary', onclick: async () => { await saveSettings({ avatars: av, games: g }); toast(t('Salvo'), 'ok'); } }, icon('check', 15), t('Salvar'))));
}
