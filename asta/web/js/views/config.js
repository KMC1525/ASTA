import { api, events } from '../api.js';
import { t } from '../i18n.js';
import { refreshState, renderSide, saveSettings, state } from '../main.js';
import { GGUF_HINT, GGUF_KINDS, PREC_HINT, QUALITY_LABEL } from '../model_labels.js';
import { checkbox, confirmDialog, field, fmtBytes, h, icon, range, select, seg, toast } from '../ui.js';

export default async function render(root, ctx) {
  let tab = ctx.tab || 'providers';
  const body = h('div'), tabs = h('div', { class: 'tabs' });
  const TABS = [['providers', 'Provedores'], ['media', 'Mídia'], ['generation', 'Geração'], ['creative', 'Avatars e jogos'], ['voice', 'Voz'], ['local', 'Modelos locais'], ['system', 'Sistema']];
  const paintTabs = () => tabs.replaceChildren(...TABS.map(([id, l]) => h('button', { class: tab === id ? 'on' : '', onclick: () => { tab = id; paintTabs(); paintBody(); } }, t(l))));
  const paintBody = async () => { body.replaceChildren(h('div', { class: 'spinner' })); const fn = { providers, media, generation, creative, voice, local, system }[tab]; body.replaceChildren(await fn()); };
  root.replaceChildren(h('div', { class: 'page narrow' }, h('div', { class: 'page-h' }, h('div', null, h('h1', null, t('Configuração')), h('p', null, t('Provedores de IA, mídia, voz e modelos locais: configure uma vez e use em tudo.')))), tabs, body));
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
      const patch = { base_url: draft.base_url, model: draft.model, vision: !!draft.vision };
      if (p.kind === 'local_hf') patch.n_ctx = draft.n_ctx > 0 ? draft.n_ctx : 0;   // 0 = automático
      if (draft.api_key) patch.api_key = draft.api_key;
      await saveSettings({ providers: { [p.id]: patch } }); draft.api_key = ''; toast(t('Salvo'), 'ok'); await refreshState(); renderSide(); paint();
    };
    const inputs = [];
    if (p.id === 'demo') inputs.push(h('p', { class: 'muted small', style: { margin: '10px 0 0' } }, t(p.hint)));
    else {
      if (p.needs_key || p.kind === 'openai' || p.id === 'anthropic') inputs.push(field(t('Chave de API') + (p.needs_key ? '' : ' (' + t('opcional') + ')'),
        h('div', { class: 'row nw' }, h('input', { type: 'password', autocomplete: 'off', placeholder: cfg.has_key ? '•••••••• (' + t('salva') + ')' : 'sk-…', oninput: (e) => { draft.api_key = e.target.value; } }),
          cfg.has_key ? h('button', { class: 'btn sm danger', onclick: async () => { await saveSettings({ providers: { [p.id]: { api_key: null } } }); toast(t('Chave removida')); await refreshState(); paint(); } }, t('Remover')) : null),
        p.docs ? h('a', { href: p.docs, target: '_blank', rel: 'noopener', class: 'muted' }, t('Obter chave →')) : null));
      if (p.kind === 'openai' || p.id === 'anthropic') inputs.push(field(t('URL base'), h('input', { value: draft.base_url || p.base_url, placeholder: p.base_url || 'https://…/v1', oninput: (e) => { draft.base_url = e.target.value.trim(); } })));
      inputs.push(field(t('Modelo'), h('div', { class: 'row nw' }, h('input', { list: 'models-' + p.id, value: draft.model, placeholder: p.kind === 'local_hf' ? t('arquivo .gguf baixado') : t('clique em “Carregar modelos”'), oninput: (e) => { draft.model = e.target.value.trim(); } }), dl,
        p.kind !== 'local_hf' ? h('button', { class: 'btn sm', onclick: loadModels }, icon('refresh', 13), t('Carregar modelos')) : null)));
      if (p.kind !== 'local_hf') inputs.push(checkbox(t('Aceita imagens (visão)'), draft.vision, (v) => { draft.vision = v; }));
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
async function system() {
  const hw = state.hardware;
  const cmd = (label, text) => h('div', { class: 'field' }, h('label', { class: 'f' }, label), h('div', { class: 'codebox' }, h('span', null, text), h('button', { class: 'btn sm ghost', onclick: () => { navigator.clipboard.writeText(text).then(() => toast(t('Copiado'))); } }, icon('copy', 13))));
  return h('div', null,
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Idioma da interface')),
      select([['auto', t('Automático (navegador)')], ['pt-BR', 'Português (Brasil)'], ['en', 'English']], state.settings.language, async (v) => { await saveSettings({ language: v }); location.reload(); })),
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
