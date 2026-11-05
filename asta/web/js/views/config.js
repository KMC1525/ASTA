import { api, events } from '../api.js';
import { t } from '../i18n.js';
import { refreshState, renderSide, saveSettings, state } from '../main.js';
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
  const container = h('div');
  const rolesCard = () => {
    const S = state.settings;
    const roleSel = (role, label, hint) => field(label, select(presets.map((p) => [p.id, t(p.label)]), S.active[role], async (v) => { await saveSettings({ active: { [role]: v } }); toast(t('Salvo'), 'ok'); paint(); }), hint);
    return h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Quem faz o quê')),
      h('div', { class: 'grid2' }, roleSel('generation', t('Geração de mundos'), t('Modelo mais capaz: roda os agentes (análise, planejamento, criação, revisão).')),
        roleSel('characters', t('Personagens (chat e voz)'), t('Um modelo rápido e barato basta: responde a cada mensagem dos NPCs.'))));
  };
  const paint = () => container.replaceChildren(rolesCard(), h('div', null, presets.map(card)));

  function card(p) {
    const S = state.settings, cfg = (S.providers && S.providers[p.id]) || {};
    const isGen = S.active.generation === p.id, isChar = S.active.characters === p.id;
    const configured = p.id === 'demo' || cfg.has_key || cfg.model || (p.local && cfg.base_url);
    const draft = { base_url: cfg.base_url || '', model: cfg.model || '', api_key: '', vision: cfg.vision != null ? cfg.vision : p.vision };
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
  const ram = state.hardware.ram_gb || 8;
  const results = h('div', { class: 'col' }), files = h('div', { class: 'col', style: { marginTop: '14px' } }), installed = h('div', { class: 'col' }), prog = h('div');
  const tokenIn = h('input', { type: 'password', autocomplete: 'off', placeholder: state.settings.hf.token_set ? '•••••••• (' + t('salvo') + ')' : 'hf_…' });
  const q = h('input', { type: 'search', placeholder: t('Buscar modelos GGUF (ex.: qwen, llama, gemma, mistral)…'), onkeydown: (e) => { if (e.key === 'Enter') search(); } });

  async function paintInstalled() {
    const { models } = await api('/api/hf/local');
    installed.replaceChildren(...(models.length ? models.map((m) => h('div', { class: 'row nw', style: { padding: '10px 0', borderBottom: '1px solid var(--line)' } },
      h('div', { class: 'grow' }, h('div', { class: 'mono', style: { fontSize: '13px' } }, m.name), h('div', { class: 'dim small' }, fmtBytes(m.size))),
      h('button', { class: 'btn sm', onclick: async () => { await saveSettings({ providers: { local_hf: { model: m.name } }, active: { generation: 'local_hf' } }); toast(t('Usando na geração'), 'ok'); } }, t('Usar na geração')),
      h('button', { class: 'btn sm', onclick: async () => { await saveSettings({ providers: { local_hf: { model: m.name } }, active: { characters: 'local_hf' } }); toast(t('Usando nos personagens'), 'ok'); } }, t('Usar nos personagens')),
      h('button', { class: 'btn sm ghost danger', onclick: async () => { if (await confirmDialog(t('Apagar o arquivo {n}?', { n: m.name }))) { await api('/api/hf/local/' + encodeURIComponent(m.name), { method: 'DELETE' }); paintInstalled(); } } }, icon('trash', 13)))) :
      [h('div', { class: 'muted small' }, t('Nenhum modelo baixado ainda.'))]));
  }
  async function search() {
    results.replaceChildren(h('div', { class: 'spinner' }));
    try {
      const r = await api('/api/hf/search?q=' + encodeURIComponent(q.value || 'gguf'));
      results.replaceChildren(...r.results.map((m) => h('div', { class: 'li', onclick: () => openRepo(m.id) }, h('div', { class: 'grow', style: { minWidth: 0 } }, h('div', { class: 't' }, m.id), h('div', { class: 's' }, '⬇ ' + (m.downloads || 0).toLocaleString() + ' · ♥ ' + (m.likes || 0))), icon('chev', 15))));
    } catch (e) { results.replaceChildren(h('div', { class: 'res err' }, e.message)); }
  }
  async function openRepo(repo) {
    files.replaceChildren(h('div', { class: 'spinner' }));
    try {
      const r = await api('/api/hf/files?repo=' + encodeURIComponent(repo));
      files.replaceChildren(h('div', { class: 'small muted' }, repo + ' — ' + t('sua RAM: {n} GB. Prefira arquivos até ~60% da RAM.', { n: ram })),
        ...r.files.map((f) => { const fits = f.size / 1024 ** 3 <= ram * 0.6; return h('div', { class: 'row nw', style: { padding: '8px 0', borderBottom: '1px solid var(--line)' } },
          h('div', { class: 'grow mono', style: { fontSize: '12px', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' } }, f.name), h('span', { class: 'chip ' + (fits ? 'solid' : '') }, fmtBytes(f.size) + (fits ? ' ✓' : ' ⚠')),
          h('button', { class: 'btn sm', onclick: () => dl(repo, f.name, f.size) }, icon('download', 13), t('Baixar'))); }));
    } catch (e) { files.replaceChildren(h('div', { class: 'res err' }, e.message)); }
  }
  async function dl(repo, file, size) {
    if (size / 1024 ** 3 > ram * 0.9 && !(await confirmDialog(t('Este modelo é maior que a sua RAM e provavelmente ficará muito lento. Baixar mesmo assim?'), false, t('Baixar')))) return;
    const bar = h('i'), label = h('span', { class: 'small muted' }, '0%');
    prog.replaceChildren(h('div', { class: 'card' }, h('div', { class: 'row', style: { marginBottom: '8px' } }, h('span', { class: 'mono small' }, file), h('span', { class: 'grow' }), label, h('button', { class: 'btn sm', id: 'dl-cancel' }, t('Cancelar'))), h('div', { class: 'bar' }, bar)));
    let jid;
    try { jid = (await api('/api/hf/download', { method: 'POST', body: { repo, file } })).job_id; } catch (e) { return toast(e.message, 'err'); }
    prog.querySelector('#dl-cancel').onclick = () => api('/api/jobs/' + jid + '/cancel', { method: 'POST' });
    events('/api/jobs/' + jid + '/events', (ev) => {
      if (ev.type === 'progress' && ev.total) { const p = ev.done / ev.total; bar.style.width = Math.round(p * 100) + '%'; label.textContent = Math.round(p * 100) + '% · ' + fmtBytes(ev.done) + ' / ' + fmtBytes(ev.total); }
      else if (ev.type === 'done') { toast(t('Download concluído'), 'ok'); prog.replaceChildren(); paintInstalled(); }
      else if (ev.type === 'error') { toast(ev.message, 'err'); prog.replaceChildren(); }
      else if (ev.type === 'cancelled') { toast(t('Download cancelado')); prog.replaceChildren(); }
    });
  }
  await paintInstalled();
  return h('div', null,
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Modelos locais do Hugging Face')),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Baixe modelos GGUF direto do Hugging Face e rode-os no seu computador. Requer o extra opcional:'), ' ', h('span', { class: 'kbd' }, 'pip install "asta[local]"'), ' ', t('Alternativa sem instalar nada: use Ollama ou LM Studio (aba Provedores).')),
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
    if (modelCaps.length) inputs.push(h('div', { class: 'grid2' }, modelCaps.map(([cap, label]) => {
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
