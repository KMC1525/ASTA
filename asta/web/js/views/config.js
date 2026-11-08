import { api, events } from '../api.js';
import { t } from '../i18n.js';
import { go, refreshState, renderSide, saveSettings, state } from '../main.js';
import { accentSwatches, themeCards } from '../appearance.js';
import { CONFIG_GROUPS, CONFIG_TABS, ui } from '../prefs.js';
import { GGUF_HINT, GGUF_KINDS, PREC_HINT, QUALITY_LABEL } from '../model_labels.js';
import { checkbox, confirmDialog, download, field, fmtBytes, h, icon, range, select, seg, toast } from '../ui.js';
import { RISK } from '../computer_ui.js';

export default async function render(root, ctx) {
  let tab = ctx.tab === 'creative' ? 'avatars' : (ctx.tab || 'providers');   // «creative» (Avatars e jogos) foi dividida em «avatars» e «games»
  const body = h('div'), tabs = h('div', { class: 'tabs cfgtabs' });
  const TABS = CONFIG_TABS;
  const paintTabs = () => tabs.replaceChildren(...CONFIG_GROUPS.flatMap(([gid, gl]) => [h('span', { class: 'tg' }, t(gl)),
    ...TABS.filter((x) => x[2] === gid).map(([id, l]) => h('button', { class: tab === id ? 'on' : '', dataset: { tab: id }, onclick: () => { tab = id; paintTabs(); paintBody(); } }, t(l)))]));
  const FNS = { providers, media, chat, generation: generation, avatars, games, canvas: canvasTab, studio: studioTab, computer: computerTab, rebuild: rebuildTab, voice, local, appearance, sections, performance, data, mobile: mobileTab, system };
  const paintBody = async () => { body.replaceChildren(h('div', { class: 'spinner' })); body.replaceChildren(await (FNS[tab] || providers)()); };
  root.replaceChildren(h('div', { class: 'page narrow cfg' }, h('div', { class: 'page-h' }, h('div', null, h('h1', null, t('Configuração')), h('p', null, t('Aparência e atalhos, IA e modelos, os padrões de cada seção e o sistema: configure uma vez e use em tudo.')))), tabs, body));
  paintTabs(); await paintBody();
}

// peças comuns das abas de seção: cartão, cabeçalho (link para a seção + restaurar padrões) e botão Salvar
const cfgCard = (title, ...kids) => h('div', { class: 'card', style: { marginBottom: '16px' } }, title ? h('h3', null, title) : null, ...kids);
const SEC_ROUTE = { chat: 'main', generation: 'worlds', avatars: 'avatars', games: 'games', canvas: 'canvas', studio: 'studio', computer: 'computer', rebuild: 'rebuild' };
const SEC_LABEL = { chat: 'Chat', generation: 'Mundos 3D', avatars: 'Avatars', games: 'Jogos 2D', canvas: 'Canvas', studio: 'Studio', computer: 'Computer Use', rebuild: 'Rebuild' };
function secHead(tab, resets) {
  const reset = resets && resets.length ? h('button', { class: 'btn sm danger', type: 'button', id: 'cfg-reset', onclick: async () => {
    if (!(await confirmDialog(t('Voltar os padrões desta seção ao original? Chaves de API, projetos e conversas não mudam.'), true, t('Restaurar')))) return;
    try { for (const sec of resets) await api('/api/settings/reset', { method: 'POST', body: { section: sec } }); await refreshState(); toast(t('Padrões restaurados'), 'ok'); go('config', { tab }); } catch (e) { toast(e.message, 'err'); }
  } }, icon('refresh', 13), t('Restaurar padrões desta seção')) : null;
  return h('div', { class: 'cfg-sechead' }, h('span', { class: 'muted small' }, t('Os padrões abaixo valem sempre que você cria algo nesta seção.')), h('span', { class: 'grow' }),
    SEC_ROUTE[tab] ? h('a', { class: 'btn sm', href: '#/' + SEC_ROUTE[tab], onclick: () => { state.ctx = {}; } }, icon('arrow', 13), t('Abrir {s}', { s: t(SEC_LABEL[tab]) })) : null, reset);
}
const saveRow = (fn) => h('div', { class: 'row', style: { justifyContent: 'flex-end' } }, h('button', { class: 'btn primary', type: 'button', id: 'cfg-save', onclick: async () => { try { await fn(); toast(t('Salvo'), 'ok'); } catch (e) { toast(e.message, 'err'); } } }, icon('check', 15), t('Salvar')));
const numInput = (obj, key, min, max, step) => h('input', { type: 'number', min, max, step: step || 1, value: obj[key], oninput: (e) => { const v = parseFloat(e.target.value); if (!Number.isNaN(v)) obj[key] = v; } });

// ---------------------------------------------------------------------------------- provedores
// Entrar com a conta: OpenRouter tem login OAuth aberto (a chave volta sozinha); Claude, ChatGPT, Grok, Gemini e Hugging Face não deixam apps de terceiros usarem o login/assinatura,
// então abrimos a página de login deles já no lugar certo para criar a chave (que se cola no campo abaixo).
function accountBox(p, cfg, repaint) {
  const msg = h('p', { class: 'muted small', style: { margin: '6px 0 0' } });
  const connected = cfg.auth === 'account' && cfg.has_key;
  if (p.oauth) {
    const go = async () => {
      msg.textContent = '';
      try {
        const r = await api('/api/auth/openrouter/start', { method: 'POST', body: {} });
        const w = window.open(r.url, 'asta-login', 'width=520,height=720');
        if (!w) { location.href = r.url; return; }
        msg.textContent = t('Faça o login na janela que abriu…');
        const done = async () => { window.removeEventListener('message', onMsg); await refreshState(); toast(t('Conta conectada'), 'ok'); renderSide(); repaint(); };
        const onMsg = (e) => { if (e.data === 'asta-auth-ok') done(); };
        window.addEventListener('message', onMsg);
        const tick = setInterval(async () => { if (w.closed) { clearInterval(tick); await refreshState(); const c = (state.settings.providers || {})[p.id] || {}; if (c.auth === 'account' && c.has_key) done(); else { window.removeEventListener('message', onMsg); msg.textContent = ''; } } }, 800);
      } catch (e) { msg.textContent = e.message; msg.className = 'err small'; }
    };
    return h('div', { class: 'field', dataset: { account: p.id } }, h('label', { class: 'f' }, t('Conta')),
      h('div', { class: 'row' }, h('button', { class: 'btn' + (connected ? '' : ' primary'), type: 'button', id: 'acct-' + p.id, onclick: go }, icon('user', 14), connected ? t('Entrar de novo com a conta') : t('Entrar com a conta do {p}', { p: 'OpenRouter' })),
        connected ? h('span', { class: 'chip on' }, t('conta conectada')) : null,
        connected ? h('button', { class: 'btn sm danger', type: 'button', onclick: async () => { await saveSettings({ providers: { [p.id]: { api_key: null, auth: '' } } }); toast(t('Conta desconectada')); await refreshState(); repaint(); } }, t('Desconectar')) : null),
      h('p', { class: 'muted small', style: { margin: '6px 0 0' } }, t('Login oficial (OAuth): você autoriza no site do OpenRouter e não precisa copiar chave. O uso é cobrado na sua conta de lá.')), msg);
  }
  return h('div', { class: 'field', dataset: { account: p.id } }, h('label', { class: 'f' }, t('Conta')),
    h('div', { class: 'row' }, h('a', { class: 'btn', href: p.login, target: '_blank', rel: 'noopener', id: 'acct-' + p.id }, icon('user', 14), t('Entrar na conta e criar a chave'))),
    h('p', { class: 'muted small', style: { margin: '6px 0 0' } }, t('Este provedor não deixa outros apps usarem o login da conta nem da assinatura (Claude Pro, ChatGPT Plus…): você entra no site dele, cria a chave em um clique e cola no campo abaixo.')));
}

async function providers() {
  const presets = state.presets;
  const localInfo = (await api('/api/hf/local')).models, localModels = localInfo.map((m) => m.name);
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
      if (p.oauth || p.login) inputs.push(accountBox(p, cfg, () => { paint(); }));
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
          const loc = localInfo.find((m) => m.name === draft.model);
          let txt = draft.n_ctx > 0 ? t('Usando {n} tokens de contexto.', { n: draft.n_ctx.toLocaleString() })
            : pre ? t('Automático: {n} tokens (base do modelo pré-instalado).', { n: pre.n_ctx.toLocaleString() }) : t('Automático: conforme o seu hardware (2.048 a 8.192 tokens).');
          if (loc && loc.ctx_train) {   // até onde o modelo foi treinado e quanto o cache de atenção custa na memória (lido do arquivo, sem carregar o modelo)
            const gb = (n) => (n / 1073741824).toFixed(n >= 1073741824 * 10 ? 0 : 1) + ' GB', want = draft.n_ctx > 0 ? draft.n_ctx : loc.ctx_train;
            txt += ' ' + t('Este modelo foi treinado com até {n} tokens.', { n: loc.ctx_train.toLocaleString() });
            if (loc.kv_bytes_per_token) txt += ' ' + t('O cache de atenção de {c} tokens ocupa ≈ {a} (≈ {b} com cache de 4 bits).', { c: want.toLocaleString(), a: gb(loc.kv_bytes_per_token * want), b: gb(loc.kv_bytes_per_token * want * 0.28) });
            if (draft.n_ctx > loc.ctx_train) txt += ' ⚠ ' + t('O valor escolhido passa do que o modelo suporta: a qualidade pode cair.');
          }
          ctxHint.textContent = txt;
        };
        const ctxDl = h('datalist', { id: 'ctx-' + p.id }, [4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576].map((n) => h('option', { value: String(n), label: n >= 1048576 ? '1M' : Math.round(n / 1024) + 'K' })));
        const ctxIn = h('input', { type: 'number', list: 'ctx-' + p.id, min: 512, step: 1024, value: draft.n_ctx || '', placeholder: t('automática'), oninput: (e) => { draft.n_ctx = Math.max(0, parseInt(e.target.value || '0', 10) || 0); showCtx(); } });
        inputs.push(field(t('Janela de contexto (tokens)'), h('div', { class: 'row nw' }, ctxIn, ctxDl,
          h('button', { class: 'btn sm', onclick: () => { draft.n_ctx = 0; ctxIn.value = ''; showCtx(); } }, t('Usar o automático'))),
          t('Quanto texto o modelo lê de uma vez. Janelas maiores usam mais memória (RAM/VRAM): 256K (262144), 512K (524288) e 1M (1048576) só valem em modelos treinados para isso — o ASTA lê o limite do modelo no arquivo e avisa se você passar dele, e comprime o cache de atenção sozinho para caber. Os modelos de texto pré-instalados começam com 32.768 (32K).')));
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

// Por que o LM Studio não respondeu: separa «está no próprio aparelho» de «está em outro computador da rede» (cada um tem uma causa típica diferente)
function lmWhy(r) {
  let host = ''; try { host = new URL(r.url).hostname; } catch (e) { /* ok */ }
  const own = /^(127\.|localhost$|\[?::1)/.test(host);
  if (own) return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '') ? t('O LM Studio não roda neste aparelho. Para usar o do seu computador, use «LM Studio no computador» abaixo (IP do computador, não 127.0.0.1).') : t(r.hint);
  if (r.kind === 'refused') return t('O computador respondeu que a porta está fechada: no LM Studio (Developer) ligue «Serve on Local Network» — sem isso ele só aceita conexões do próprio computador — e reinicie o servidor.');
  if (r.kind === 'timeout') return t('O computador não respondeu a tempo: libere a porta 1234 no firewall (no Windows: «Permitir um aplicativo» para o LM Studio, rede privada), e confira se o celular está no mesmo Wi-Fi (redes de visitantes isolam os aparelhos).');
  if (r.kind === 'dns') return t('Não achei esse endereço. Digite o IP do computador (ex.: 192.168.0.10), que aparece no LM Studio em Developer, ao lado de «Serve on Local Network».');
  if (r.kind === 'unreachable') return t('Sem caminho até esse endereço: confira se o celular está no mesmo Wi-Fi do computador e o IP digitado.');
  return t(r.hint);
}

// LM Studio do COMPUTADOR, usado pelo celular/tablet: acha o servidor na rede (ou usa o IP digitado) e aponta o endereço do provedor para ele.
// No computador o LM Studio precisa estar com «Serve on Local Network» ligado (Developer → Server Settings) e na mesma rede Wi-Fi.
function pcBox(draft, detect) {
  if (!/Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '')) return null;
  const out = h('div', { class: 'muted small', style: { marginTop: '6px' } });
  const addr = h('input', { id: 'lms-pc-addr', inputmode: 'url', autocapitalize: 'off', placeholder: '192.168.0.10  ·  192.168.0.10:1234', 'aria-label': t('Endereço do computador') });
  const point = async (url) => {
    draft.base_url = url; await saveSettings({ providers: { lmstudio: { base_url: url } } });
    let ok = false; try { ok = (await api('/api/lmstudio?url=' + encodeURIComponent(url))).running; } catch (e) { /* o detect mostra o motivo */ }
    if (ok) { await saveSettings({ active: { generation: 'lmstudio', characters: 'lmstudio' } }); toast(t('Conectado ao LM Studio do computador.'), 'ok'); await refreshState(); renderSide(); }   // quem conectou quer usar: o Chat e os avatares passam a usar os modelos dele
    detect();
  };
  const scan = async () => {
    out.replaceChildren(h('div', { class: 'spinner' }), ' ', t('Procurando o LM Studio na rede…'));
    let r;
    try { r = await api('/api/lmstudio/scan', { method: 'POST', body: {} }); } catch (e) { out.textContent = e.message; return; }
    if (!r.servers.length) { out.textContent = t('Não achei. No computador: LM Studio → Developer → ligue «Serve on Local Network» e «Start Server»; o celular precisa estar no mesmo Wi-Fi. Ou digite o IP do computador.'); return; }
    out.replaceChildren(...r.servers.map((sv) => h('button', { class: 'btn sm', type: 'button', onclick: () => point(sv.url) }, sv.url + ' · ' + t('{n} modelo(s)', { n: sv.models }))));
  };
  const manual = () => {
    let v = addr.value.trim();
    if (!v) { out.textContent = t('Digite o IP do computador (ex.: 192.168.0.10).'); return; }
    const scheme = (v.match(/^(https?):\/\//i) || [, ''])[1].toLowerCase();   // https:// (túnel) é mantido; sem esquema vale http + porta 1234
    v = v.replace(/^https?:\/\//i, '');
    const path = /^[^/]+\/lm\/[\w-]+/.test(v) ? v.slice(v.indexOf('/')).replace(/\/(v1|api\/v0)(\/.*)?$/, '').replace(/\/$/, '') : '';   // link «…/lm/<código>» do acesso de fora de casa
    v = v.replace(/\/.*$/, '');
    if (!scheme && !/:\d+$/.test(v)) v += ':1234';
    point((scheme || 'http') + '://' + v + path);
  };
  return h('div', { class: 'lms-pc', id: 'lms-pc', style: { marginTop: '12px', paddingTop: '10px', borderTop: '1px solid var(--line, rgba(255,255,255,.1))' } },
    h('b', null, t('LM Studio no computador')),
    h('p', { class: 'muted small', style: { margin: '4px 0 8px' } }, t('Use os modelos do LM Studio do seu computador por este aparelho, na mesma rede Wi-Fi.')),
    h('p', { class: 'muted small', style: { margin: '0 0 8px' } }, t('Fora de casa, sem VPN: no computador, abra Configuração → Celular e tablet → «LM Studio fora de casa», ligue e copie o link; cole-o aqui. (Ou use o Tailscale: digite o IP 100.x.x.x ou o nome ….ts.net do computador.)')),
    h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap' } }, h('button', { class: 'btn sm primary', type: 'button', id: 'lms-pc-scan', onclick: scan }, icon('refresh', 13), t('Procurar na rede')), addr,
      h('button', { class: 'btn sm', type: 'button', id: 'lms-pc-go', onclick: manual }, t('Conectar'))), out);
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
    if (!r.running) { note.textContent = lmWhy(r) + (r.error ? ' (' + r.error + ')' : ''); return; }
    list.replaceChildren(...(r.models.length ? r.models.map((m) => h('button', { class: 'chip' + (draft.model === m.id || (!draft.model && r.selected === m.id) ? ' on' : ''), title: [m.loaded ? t('carregado') : t('não carregado'), m.quant, m.vision ? t('visão') : ''].filter(Boolean).join(' · '),
      onclick: () => { draft.model = m.id; const inp = getModelInput(); if (inp) inp.value = m.id; detect(); } }, (m.loaded ? '● ' : '○ ') + m.id + (m.vision ? ' 👁' : ''))) : [h('span', { class: 'dim small' }, t('Nenhum modelo instalado: baixe um na aba «Discover» do LM Studio.'))]));
    note.textContent = r.loaded.length ? t('● carregado agora · ○ instalado (o LM Studio pode carregar sob demanda). Sem escolher, o ASTA usa o modelo carregado.') : t('Nenhum modelo está carregado no LM Studio: carregue um (ou escolha um acima).');
  }
  box.append(status, list, note, pcBox(draft, detect)); detect();
  return box;
}

// ---------------------------------------------------------------------------------- geração
async function generation() {
  const g = JSON.parse(JSON.stringify(state.settings.generation)), c = JSON.parse(JSON.stringify(state.settings.characters));
  const wrap = h('div', null, secHead('generation', ['generation', 'characters']),
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
  const quick = (key, values, fmt, input) => h('div', { class: 'row', style: { gap: '6px', flexWrap: 'wrap', marginTop: '6px', marginBottom: '14px' } }, ...values.map((v) => h('button', { class: 'chip', type: 'button', onclick: () => { c[key] = v; document.getElementById(input).value = v; } }, fmt(v))));
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
  return h('div', null, secHead('chat', null),
    h('p', { class: 'muted', style: { marginTop: 0 } }, t('Ajustes da tela Chat. O modelo e o provedor se escolhem no botão ao lado do Run; aqui ficam o tamanho das respostas, a memória da conversa, o tempo de pensamento e a busca na web.')),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Respostas')),
      h('div', { class: 'grid2' },
        h('div', null, num('max_tokens', 2000, 128000, 100, t('Tamanho das respostas (tokens)'), t('Limite do texto de cada resposta (mínimo 2.000, máximo 128.000). 1 token ≈ 3–4 letras; 2.000 ≈ 1.200 palavras. Se o modelo aceitar menos que isso, o ASTA descobre o limite dele e ajusta sozinho. Com tempo de pensamento ligado, o pensamento vai além desse limite.')), quick('max_tokens', [2000, 4000, 8000, 16000, 32000, 64000], (v) => t('{n} tokens', { n: kb(v) }), 'cc-max_tokens')),
        field(t('Criatividade (temperatura)'), range(0, 1.5, 0.05, c.temperature, (v) => { c.temperature = v; }), t('Baixa = mais objetivo; alta = mais criativo. Modelos com pensamento estendido ignoram este valor.'))),
      field(t('Estilo das respostas'), seg([['balanced', t('Equilibrado')], ['detailed', t('Detalhado')], ['epic', t('Longo e profundo')]], c.reply_style || 'detailed', (v) => { c.reply_style = v; }),
        t('Equilibrado: o tamanho acompanha a pergunta. Detalhado (padrão): respostas completas, com raciocínio, exemplos e passos. Longo e profundo: usa todo o espaço disponível, em seções. Em todos, o tamanho vem de conteúdo, nunca de enrolação.')),
      field(t('Equipe de agentes'), seg([['off', t('Desligada')], ['plan', t('Planejar e escrever')], ['review', t('Planejar, escrever e revisar')]], c.agents || 'off', (v) => { c.agents = v; }),
        t('Desligada: um modelo só, resposta direta. Planejar e escrever: um Planejador monta o roteiro e o Redator o segue. Planejar, escrever e revisar: um Revisor confere o rascunho e o Redator o melhora uma vez. Mais completo, porém mais lento e com mais tokens; se algum agente falhar, a resposta segue sem ele.')),
      h('div', { class: 'row', style: { gap: '16px', flexWrap: 'wrap', alignItems: 'center' } },
        checkbox(t('Continuar sozinho quando a resposta for cortada pelo limite'), c.auto_continue !== false, (v) => { c.auto_continue = v; }),
        num('continue_rounds', 0, 8, 1, t('Continuações no máximo'), t('Quantas vezes o ASTA pede para o modelo seguir de onde parou. 0 = nunca.'))),
      field(t('Instruções personalizadas'), h('textarea', { rows: 3, id: 'cc-instructions', maxlength: 3000, placeholder: t('Ex.: Responda sempre em português, de forma curta e com exemplos.'), oninput: (e) => { c.instructions = e.target.value; } }, c.instructions || ''), t('Entram em toda conversa do Chat, como um pedido seu ao assistente.'))),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, 'Computer Use'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Recurso opcional do Chat: o botão Computer Use ao lado do Run manda a IA fazer tarefas no seu computador (arquivos, programas, jogos, pesquisa e escrita), no modo Ask (pergunta antes) ou Full Access (sem perguntar). Fica desligado até você ligar.')),
      h('div', { class: 'row' }, h('span', { class: 'chip ' + ((state.settings.computer || {}).enabled ? 'on' : '') }, (state.settings.computer || {}).enabled ? t('Ligado') : t('Desligado')),
        h('button', { class: 'btn sm', type: 'button', id: 'cfg-open-cu', onclick: () => go('config', { tab: 'computer' }) }, icon('config', 13), t('Ajustes do Computer Use')))),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Janela de contexto')),
      h('div', { class: 'grid2' },
        h('div', null, num('context_tokens', 1000, 2000000, 1000, t('Janela de contexto (tokens)'), t('Quanto da conversa (mais anexos e fontes da web) o ASTA envia ao modelo. Passou disso, as mensagens mais antigas saem primeiro. Nunca ponha mais do que o modelo aguenta: 256K, 512K e 1M só em modelos que suportam (Gemini, GPT-4.1, Claude com 1M, Llama 4, Qwen-Plus… e locais com contexto longo).')), quick('context_tokens', [4000, 8000, 16000, 32000, 128000, 256000, 512000, 1000000], (v) => kb(v), 'cc-context_tokens')),
        num('history_turns', 1, 1000, 1, t('Máximo de turnos lembrados'), t('Pares pergunta/resposta no máximo, mesmo que caibam mais na janela.'))),
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
  const card = cfgCard;
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
      field(t('Animações'), select([['auto', t('Automático (segue o sistema)')], ['reduce', t('Reduzir animações')], ['full', t('Sempre animar')]], U().motion, (v) => save({ motion: v })), t('“Reduzir” desliga transições e animações — bom para quem sente enjoo com movimento ou usa um computador mais fraco.'))),
    card(t('Idioma'),
      field(t('Idioma da interface'), select([['auto', t('Automático (navegador)')], ['pt-BR', 'Português (Brasil)'], ['en', 'English']], state.settings.language, async (v) => { await saveSettings({ language: v }); location.reload(); }),
        t('Os textos do terminal (asta, asta update, instaladores) seguem o idioma do computador; para forçar um, use ASTA_LANG=pt ou ASTA_LANG=en.'))),
    card(t('Padrões da aparência'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Volta o tema, as cores e o conforto de leitura ao original. Suas chaves, avatares e projetos não mudam.')),
      h('div', { class: 'row' }, h('button', { class: 'btn sm', onclick: () => window.ASTA_WELCOME && window.ASTA_WELCOME() }, t('Rever as boas-vindas')), h('span', { class: 'grow' }),
        h('button', { class: 'btn sm danger', onclick: async () => { if (await confirmDialog(t('Voltar a aparência e as preferências de uso ao padrão? Suas chaves, avatares e projetos não mudam.'), true, t('Restaurar'))) { await api('/api/settings/reset', { method: 'POST', body: { section: 'ui' } }); await refreshState(); location.reload(); } } }, t('Restaurar padrões da aparência')))));
}

// ---------------------------------------------------------------------------------- seções e atalhos
async function sections() {
  const save = async (patch, quiet) => { await saveSettings({ ui: patch }); if (!quiet) toast(t('Salvo'), 'ok'); };
  const U = () => ui();
  const HIDEABLE = [['worlds', 'Mundos'], ['avatars', 'Avatars'], ['games', 'Jogos 2D'], ['canvas', 'Canvas'], ['studio', 'Studio'], ['computer', 'Computer Use'], ['rebuild', 'Rebuild'], ['library', 'Biblioteca']];
  const hidden = new Set(U().sidebar_hidden);
  const jump = (tab, label, desc) => h('button', { class: 'cfg-jump', type: 'button', dataset: { go: tab }, onclick: () => go('config', { tab }) }, h('b', null, t(label)), h('span', null, t(desc)));
  return h('div', null,
    cfgCard(t('Barra lateral'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Esconda as telas que você não usa. “Chat” e “Configuração” ficam sempre; o que está escondido continua acessível pela busca (Ctrl+K).')),
      h('div', { class: 'row', style: { gap: '18px', flexWrap: 'wrap' } }, HIDEABLE.map(([id, label]) => checkbox(t(label), !hidden.has(id), async (on) => { on ? hidden.delete(id) : hidden.add(id); await save({ sidebar_hidden: [...hidden] }, true); })))),
    cfgCard(t('Tela inicial'),
      field(t('Qual tela abre quando você entra no ASTA'), select([['main', 'Chat'], ['last', t('A última tela que eu usei')], ['avatars', 'Avatars'], ['worlds', t('Mundos')], ['games', t('Jogos 2D')], ['canvas', 'Canvas'], ['studio', 'Studio'], ['computer', 'Computer Use'], ['rebuild', 'Rebuild'], ['library', t('Biblioteca')]], U().start_page, (v) => save({ start_page: v })))),
    cfgCard(t('Teclado'),
      checkbox(t('Atalhos de teclado (Alt+1…9 e 0, Alt+B, Alt+T, ?) — Ctrl+K (busca) sempre funciona'), U().shortcuts, (v) => save({ shortcuts: v }, true)),
      field(t('Enviar mensagens com'), seg([['enter', 'Enter'], ['ctrl_enter', 'Ctrl+Enter']], U().send_key, (v) => save({ send_key: v })),
        t('Com Enter, use Shift+Enter para quebrar a linha; com Ctrl+Enter, o Enter quebra a linha. Vale para o chat e para a caixa de criação.')),
      h('div', { class: 'row', style: { marginTop: '8px' } }, h('button', { class: 'btn sm', onclick: () => window.dispatchEvent(new KeyboardEvent('keydown', { key: '?', bubbles: true })) }, t('Ver atalhos')),
        h('button', { class: 'btn sm', onclick: () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true })) }, icon('search', 13), t('Abrir a busca (Ctrl+K)')))),
    cfgCard(t('Configurações de cada seção'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Cada seção tem os próprios padrões, usados sempre que você cria algo nela.')),
      h('div', { class: 'cfg-jumps' }, jump('chat', 'Chat', 'tamanho da resposta, contexto, pensamento, busca na web'), jump('generation', 'Mundos 3D', 'perspectiva, conteúdo, realismo, NPCs'), jump('avatars', 'Avatars', 'persona, memória, conversa em grupo'),
        jump('games', 'Jogos 2D', 'tamanho, revisão, criatividade'), jump('canvas', 'Canvas', 'modelo inicial de novos canvases'), jump('studio', 'Studio', 'duração, estilo, formato, exportação, edição automática'),
        jump('computer', 'Computer Use', 'ligar, modo Ask ou Full Access, limites e prompts'), jump('rebuild', 'Rebuild', 'revisão do texto por IA e limite de chamadas'), jump('performance', 'Desempenho', 'modo leve, modelos ociosos, Rust'))));
}

// ---------------------------------------------------------------------------------- canvas
async function canvasTab() {
  let tpls = [];
  try { tpls = (await api('/api/canvas-templates')).templates || []; } catch (e) { /* sem a lista, só o padrão */ }
  const cv = JSON.parse(JSON.stringify(state.settings.canvas || { template: 'text_image' }));
  const opts = (tpls.length ? tpls : [{ id: 'text_image', label: 'Texto → Imagem' }]).map((x) => [x.id, t(x.label)]);
  return h('div', null, secHead('canvas', ['canvas']),
    cfgCard(t('Novos canvases'), field(t('Modelo inicial'), select(opts, cv.template, (v) => { cv.template = v; }), t('O modelo que vem marcado ao criar um canvas novo. Os provedores de imagem, vídeo, som e voz ficam em Mídia.')),
      h('div', { class: 'row' }, h('button', { class: 'btn sm', type: 'button', onclick: () => go('config', { tab: 'media' }) }, icon('config', 13), t('Provedores de mídia')))),
    saveRow(() => saveSettings({ canvas: cv })));
}

// ---------------------------------------------------------------------------------- studio
async function studioTab() {
  const meta = await api('/api/studio/meta');
  const st = JSON.parse(JSON.stringify(state.settings.studio));
  const dt = () => meta.durations.find((d) => d.id === st.duration_type) || meta.durations[0];
  const mi = h('input', { type: 'number', min: 0, max: 360, id: 'cs-min', value: Math.floor(st.target_seconds / 60) }), si = h('input', { type: 'number', min: 0, max: 59, id: 'cs-sec', value: Math.round(st.target_seconds % 60) });
  const setT = () => { st.target_seconds = Math.max(meta.limits.min_seconds, Math.min(meta.limits.max_seconds, (parseInt(mi.value || '0', 10) || 0) * 60 + (parseInt(si.value || '0', 10) || 0))); };
  mi.addEventListener('input', setT); si.addEventListener('input', setT);
  const custom = h('textarea', { rows: 2, id: 'cs-style-custom', placeholder: t('Descreva o visual: ex. aquarela suave, cores pastel, traço de lápis…'), oninput: (e) => { st.style_custom = e.target.value; } }, st.style_custom);
  const cb = (label, key) => checkbox(label, st[key] !== false, (v) => { st[key] = v; });
  const styleSel = select(meta.styles.map((x) => [x.id, t(x.label)]), st.style, (v) => { st.style = v; custom.classList.toggle('hidden', v !== 'custom'); });
  custom.classList.toggle('hidden', st.style !== 'custom');
  return h('div', null, secHead('studio', ['studio']),
    cfgCard(t('Projeto novo'),
      h('div', { class: 'grid2' }, field(t('Tipo de projeto'), seg([['single', t('Único')], ['series', t('Série')]], st.kind, (v) => { st.kind = v; })),
        field(t('Tipo de duração'), select(meta.durations.map((d) => [d.id, t(d.label) + ' — ' + t(d.hint)]), st.duration_type, (v) => { st.duration_type = v; }))),
      field(t('Duração padrão'), h('div', { class: 'st-time' }, mi, h('span', null, 'min'), si, h('span', null, 's')), t('Cada projeto novo começa com esta duração; dá para mudar na hora de criar.')),
      h('div', { class: 'grid2' }, field(t('Estilo visual'), styleSel), field(t('Formato'), select([['auto', t('Automático (pelo tipo de duração)')]].concat(meta.aspects.map((a) => [a, a])), st.aspect, (v) => { st.aspect = v; })))
      , custom,
      field(t('Idioma dos vídeos'), select([['auto', t('Igual ao da interface')], ['pt-BR', 'Português (BR)'], ['en', 'English']], st.language, (v) => { st.language = v; }))),
    cfgCard(t('Geração'),
      h('div', { class: 'grid2' }, field(t('Movimento dos planos'), select([['auto', t('Leve: imagem com zoom e pan (Ken Burns)')], ['video', t('Modelo de vídeo em cada plano (mais lento e caro)')]], st.motion, (v) => { st.motion = v; })),
        field(t('Revisão de cada cena'), select([[0, t('Sem revisão')], [1, t('1 rodada de correção')], [2, t('2 rodadas de correção')]], st.revisions, (v) => { st.revisions = parseInt(v, 10); }))),
      field(t('Voz da narração (id/nome do provedor)'), h('input', { value: st.voice, placeholder: t('automático'), oninput: (e) => { st.voice = e.target.value.trim(); } })),
      h('div', { class: 'row', style: { gap: '18px' } }, cb(t('Legendas'), 'captions'), cb(t('Música de fundo'), 'music'))),
    cfgCard(t('Exportação'),
      h('div', { class: 'grid2' }, field(t('Qualidade do vídeo'), select(meta.quality.map((q) => [q, q]), st.export_quality, (v) => { st.export_quality = v; })),
        field(t('Formato do áudio'), select(meta.audio_formats.map((q) => [q, q.toUpperCase()]), st.audio_format, (v) => { st.audio_format = v; })))),
    cfgCard(t('Edição automática'),
      h('div', { class: 'grid2' }, field(t('Estilo padrão'), select(meta.edit_styles.map((x) => [x.id, t(x.label)]), st.autoedit_style, (v) => { st.autoedit_style = v; })),
        field(t('Duração alvo (segundos; 0 = automática)'), numInput(st, 'autoedit_target', 0, 21600, 5)))),
    saveRow(async () => { setT(); await saveSettings({ studio: st }); }));
}

// ---------------------------------------------------------------------------------- computer use
async function computerTab() {
  const cu = Object.assign({ enabled: false, mode: 'ask', max_parallel: 8, max_steps: 40, team: 'full', revisions: 1, ask_for: ['write', 'delete', 'run', 'input', 'screen'], game_dirs: [], app_wait: 2 }, JSON.parse(JSON.stringify(state.settings.computer || {})));
  let status = null, inv = null, prompts = [];
  try { status = await api('/api/computer/status'); } catch (e) { /* servidor antigo: segue sem o painel */ }
  try { inv = await api('/api/computer/inventory'); } catch (e) { /* idem */ }
  try { prompts = (await api('/api/computer/prompts')).prompts; } catch (e) { /* idem */ }
  const asks = ['write', 'delete', 'run', 'input', 'screen'];
  const askSet = new Set((cu.ask_for || []).filter((x) => asks.includes(x)));
  const caps = (status && status.capabilities) || {};
  const capLabel = { files: t('Arquivos e pastas'), open: t('Abrir arquivos e sites'), apps: t('Programas instalados'), screenshot: t('Ver a tela'), keyboard: t('Digitar e apertar teclas'), mouse: t('Mouse') };
  const capList = h('ul', { class: 'cu-capul', style: { listStyle: 'none', margin: 0, padding: 0 } }, Object.keys(capLabel).map((k) => {
    const c = caps[k] || {};
    return h('li', { class: c.ok ? 'ok' : 'no', style: { display: 'flex', gap: '8px', margin: '4px 0' } }, icon(c.ok ? 'check' : 'x', 14), h('span', null, capLabel[k], c.ok ? (c.how ? ' · ' + c.how : '') : ' · ' + (c.hint ? t(c.hint) : t('indisponível')), c.note ? h('span', { class: 'dim small' }, ' — ' + t(c.note)) : null));
  }));
  const dirs = h('textarea', { rows: 3, id: 'cu-gamedirs', placeholder: '~/Games\n/mnt/jogos', oninput: (e) => { cu.game_dirs = e.target.value.split('\n').map((x) => x.trim()).filter(Boolean); } }, (cu.game_dirs || []).join('\n'));
  const promptsBox = h('div', { class: 'cu-cfg-prompts' }, prompts.map((name) => {
    const pre = h('pre', null, '…');
    let loaded = false;
    return h('details', { ontoggle: async (e) => { if (!e.target.open || loaded) return; loaded = true; try { pre.textContent = (await api('/api/computer/prompts/' + name)).text; } catch (err) { pre.textContent = err.message; } } }, h('summary', { class: 'mono small' }, name), pre);
  }));
  return h('div', null, secHead('computer', ['computer']),
    cfgCard(t('Computer Use'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Uma equipe de agentes de IA (Planejador, Operador, Revisor e Relator) faz tarefas no seu computador com o modelo que você escolheu no Chat: digitar e escrever, pesquisar, usar programas instalados (Krita, OBS Studio, Audacity…), organizar e criar arquivos e pastas e abrir jogos da Steam, do Lutris e de pastas. Até 8 tarefas ao mesmo tempo.')),
      checkbox(t('Ligar o Computer Use (recurso opcional, desligado por padrão)'), cu.enabled, (v) => { cu.enabled = v; }),
      field(t('Modo padrão'), seg([['ask', 'Ask'], ['full', 'Full Access']], cu.mode, (v) => { cu.mode = v; }),
        t('Ask: antes de cada ação que muda algo, aparece Sim ou Não. Full Access: executa tudo sem perguntar. Dá para escolher o modo em cada tarefa.'))),
    cfgCard(t('Quando perguntar (modo Ask)'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Só listar, ler e pesquisar nunca pergunta. Marque o que deve pedir um Sim ou Não:')),
      h('div', { class: 'cu-asks' }, asks.map((r) => checkbox(RISK()[r], askSet.has(r), (on) => { on ? askSet.add(r) : askSet.delete(r); cu.ask_for = asks.filter((x) => askSet.has(x)); })))),
    cfgCard(t('Equipe e limites'),
      h('div', { class: 'grid2' },
        field(t('Equipe de agentes'), seg([['full', t('Completa')], ['fast', t('Rápida')]], cu.team, (v) => { cu.team = v; }),
          t('Completa: Planejador → Operador → Revisor → Relator. Rápida: só o Operador age, com relatório automático (menos chamadas à IA; bom para modelos locais lentos).')),
        field(t('Tarefas ao mesmo tempo'), range(1, 8, 1, cu.max_parallel, (v) => { cu.max_parallel = v; }), t('No máximo 8. As que passam disso esperam na fila. Tela, teclado e mouse são um só: só uma tarefa por vez os usa; arquivos, pesquisa e programas de linha de comando seguem em paralelo.'))),
      h('div', { class: 'grid2' },
        field(t('Máximo de passos por tarefa'), numInput(cu, 'max_steps', 5, 200, 5), t('Cada passo é uma ação. Ao chegar no limite a tarefa para e conta o que conseguiu.')),
        field(t('Rodadas de correção do Revisor'), select([['0', t('Nenhuma')], ['1', '1'], ['2', '2']], String(cu.revisions), (v) => { cu.revisions = parseInt(v, 10); }), t('Se o Revisor achar que faltou algo, o Operador tenta corrigir.')))),
    cfgCard(t('Jogos'),
      field(t('Pastas de jogos'), dirs, t('Uma pasta por linha. A Steam e o Lutris são achados sozinhos; aqui entram jogos soltos em pastas (executáveis, AppImage, .app e jogos de navegador).'))),
    saveRow(async () => { cu.max_steps = Math.max(5, Math.min(200, cu.max_steps)); await saveSettings({ computer: cu }); await refreshState(); }),
    cfgCard(t('Bibliotecas e ferramentas'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('O Computer Use só precisa do Python padrão. O resto é opcional e melhora ou serve de plano B; o que falta aparece com o comando para instalar.')),
      h('ul', { id: 'cu-libs', style: { listStyle: 'none', margin: 0, padding: 0 } }, ((status && status.libs) || []).map((l) => h('li', { class: l.ok ? 'ok' : 'no', dataset: { lib: l.id }, style: { display: 'flex', gap: '8px', margin: '5px 0' } }, icon(l.ok ? 'check' : (l.required ? 'x' : 'warn'), 14),
        h('span', null, t(l.label), h('span', { class: 'dim small' }, ' — ' + t(l.for)), l.ok ? null : h('span', { class: 'small', style: { display: 'block', color: l.required ? 'var(--err)' : 'var(--warn)' } }, (l.required ? t('Falta (necessário): ') : t('Opcional: ')) + t(l.hint))))))),
    cfgCard(t('O que o ASTA enxerga neste computador'),
      status ? h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Sistema: {s}.', { s: status.platform_label })) : null, capList,
      inv ? h('p', { class: 'dim small', style: { margin: '10px 0 0' } }, t('{a} programa(s) e {g} jogo(s) encontrados.', { a: inv.apps, g: inv.game_count }) + (inv.games.length ? ' ' + inv.games.slice(0, 8).map((g) => g.name).join(', ') + (inv.game_count > 8 ? '…' : '') : '')) : null,
      h('div', { class: 'row', style: { marginTop: '10px' } }, h('button', { class: 'btn sm', type: 'button', onclick: () => go('config', { tab: 'computer' }) }, icon('refresh', 13), t('Atualizar')))),
    cfgCard(t('Segurança — o que vale em qualquer modo'),
      h('ul', { class: 'muted small', style: { margin: 0, paddingLeft: '18px' } }, [
        t('Nunca lê nem escreve senhas, chaves SSH/GPG/nuvem, perfis de navegador, arquivos .env nem a pasta de dados do ASTA (onde ficam as chaves de API e estas configurações).'),
        t('Nunca escreve em pastas do sistema, nem apaga a pasta pessoal ou um disco inteiro.'),
        t('Nunca roda shells, interpretadores (bash, PowerShell, Python…), sudo, apagadores de disco nem scripts: a IA só pede ações de um catálogo fechado, validadas pelo ASTA.'),
        t('«Apagar» manda para a lixeira do ASTA e tudo que muda arquivos pode ser desfeito na seção Computer Use.'),
        t('Ver a tela envia a imagem ao modelo de IA escolhido; com um modelo na nuvem, isso sai do seu computador. Por isso o modo Ask pergunta antes.')].map((x) => h('li', null, x)))),
    cfgCard(t('System prompts internos'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Os textos que orientam cada agente são arquivos .md abertos, no código do ASTA (asta/computer/prompts). Aqui você só os lê.')), promptsBox),
    cfgCard(t('Seus dados'),
      h('p', { class: 'muted small', style: { margin: 0 } }, t('O histórico passo a passo, as capturas de tela e a lixeira ficam em arquivos comuns na pasta do ASTA (~/.asta/computer). Apague quando quiser: na seção Computer Use, em «Limpar o histórico».'))));
}

// ---------------------------------------------------------------------------------- rebuild
async function rebuildTab() {
  const rb = JSON.parse(JSON.stringify(state.settings.rebuild));
  return h('div', null, secHead('rebuild', ['rebuild']),
    cfgCard(t('Revisão do texto por IA'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Depois de reconstruir, o Perfilador, o Polidor e o Auditor revisam só o TEXTO do jogo (erros de digitação, pontuação, nomes genéricos), sem mudar a estrutura. Sem IA configurada, só a limpeza automática roda.')),
      checkbox(t('Revisar o texto com IA (marcado por padrão no Rebuild)'), rb.refine !== false, (v) => { rb.refine = v; }),
      field(t('Limite de chamadas ao modelo por reconstrução'), numInput(rb, 'max_calls', 5, 200, 5), t('Menos chamadas = mais rápido e barato; com modelos locais pequenos, 20 a 40 costuma bastar.'))),
    cfgCard(t('O que o Rebuild lê'),
      h('p', { class: 'muted small', style: { margin: 0 } }, t("Ren'Py (scripts .rpy) e RPG Maker 2000, 2003, XP, VX, VX Ace, MV e MZ. Só a estrutura é reconstruída; a arte e o áudio originais nunca são lidos nem copiados. Só para uso pessoal: não publique o resultado na Steam nem em outras plataformas."))),
    saveRow(() => saveSettings({ rebuild: rb })));
}

// ---------------------------------------------------------------------------------- desempenho (modo leve + Rust)
async function performance() {
  const pf = Object.assign({ mode: 'auto', idle_unload_min: 10 }, state.settings.performance || {});
  const nat = state.native || {};
  const hw = state.hardware;
  const cmd = (label, text) => h('div', { class: 'field' }, h('label', { class: 'f' }, label), h('div', { class: 'codebox' }, h('span', null, text), h('button', { class: 'btn sm ghost', onclick: () => { navigator.clipboard.writeText(text).then(() => toast(t('Copiado'))); } }, icon('copy', 13))));
  return h('div', null, secHead('performance', ['performance']),
    cfgCard(t('Desempenho'),
      h('div', { class: 'grid2' },
        field(t('Modo'), select([['auto', t('Automático (conforme o hardware)')], ['light', t('Leve — menos RAM/VRAM')], ['balanced', t('Equilibrado')], ['max', t('Máximo')]], pf.mode, async (v) => { pf.mode = v; await saveSettings({ performance: pf }); toast(t('Salvo'), 'ok'); }),
          t('Leve: limita a janela de contexto, comprime o cache de atenção, descarrega modelos ociosos e usa menos memória de vídeo nos modelos de imagem/vídeo.')),
        field(t('Descarregar modelos ociosos após (min)'), h('input', { type: 'number', min: 0, max: 1440, value: pf.idle_unload_min, onchange: async (e) => { pf.idle_unload_min = Math.max(0, parseInt(e.target.value || '0', 10)); await saveSettings({ performance: pf }); toast(t('Salvo'), 'ok'); } }), t('0 = nunca. No modo leve o limite é de até 3 min.'))),
      h('p', { class: 'muted small', style: { marginBottom: 0 } }, t('Seu hardware: {t}', { t: hw.tier }) + ' · ' + hw.cpus + ' CPU · ' + (hw.ram_gb ? hw.ram_gb + ' GB RAM' : '—') + ' · ' + (hw.gpu || t('não detectada (NVIDIA)')))),
    cfgCard(t('Núcleo Rust'),
      h('dl', { class: 'kv', style: { margin: 0 } }, h('dt', null, t('Núcleo Rust')), h('dd', null, nat.active ? h('span', { class: 'chip on' }, t('ativo')) : h('span', { class: 'muted' }, t('inativo — usando Python puro'))),
        h('dt', null, 'Rust (cargo)'), h('dd', null, nat.cargo ? t('encontrado') : t('não encontrado (opcional)')),
        h('dt', null, t('Carga de modelos locais')), h('dd', { id: 'nat-models' }, nat.models ? h('span', { class: 'chip on' }, t('otimizada')) : h('span', { class: 'muted' }, t('padrão (recompile o núcleo: asta native setup)'))),
        h('dt', null, t('Agentes, armazenamento e memória')), h('dd', { id: 'nat-ops' }, nat.ops ? h('span', { class: 'chip on' }, t('otimizados')) : h('span', { class: 'muted' }, t('padrão (atualize o núcleo: asta native setup)'))),
        h('dt', null, t('Processador')), h('dd', null, (nat.cores ? t('{p} núcleos físicos · {l} threads', { p: nat.cores[0], l: nat.cores[1] }) : '—') + ((nat.features || []).length ? ' · ' + nat.features.join(' ').toUpperCase() : '')),
        nat.last && nat.last.llm ? h('dt', null, t('Último modelo de texto')) : null,
        nat.last && nat.last.llm ? h('dd', { id: 'nat-llm' }, nat.last.llm.model + ' · ' + t('contexto {c}', { c: nat.last.llm.n_ctx }) + ' · ' + (nat.last.llm.n_gpu_layers === -1 ? t('tudo na GPU') : nat.last.llm.n_gpu_layers > 0 ? t('{n} camadas na GPU', { n: nat.last.llm.n_gpu_layers }) : t('na CPU')) + ' · ' + t('{n} threads', { n: nat.last.llm.n_threads }) + (nat.last.llm.kv_q8 ? ' · ' + t('cache em 8 bits') : '')) : null,
        nat.last && nat.last.media ? h('dt', null, t('Último modelo de mídia')) : null,
        nat.last && nat.last.media ? h('dd', { id: 'nat-media' }, nat.last.media.model + ' · ' + ({ gpu: t('tudo na GPU'), model_offload: t('descarga do modelo'), sequential_offload: t('descarga sequencial (pouca VRAM)'), cpu: t('na CPU') }[nat.last.media.strategy] || '—')) : null),
      h('p', { class: 'muted small' }, t('O núcleo Rust é parte do ASTA: faz a síntese de áudio do Canvas, lê o cabeçalho dos modelos locais, escolhe contexto (até 1M de tokens), camadas na GPU e threads pela memória livre, agenda vários agentes locais, procura arquivos duplicados e devolve memória ao sistema. Os instaladores já o trazem; pelo terminal o ASTA baixa a biblioteca pronta da Release (sem compilador). Se ele estiver inativo, o ASTA funciona em Python, só mais devagar. Para ativar agora, rode no terminal:')),
      cmd(t('Ativar/atualizar o núcleo Rust (baixa a biblioteca pronta)'), 'asta native setup')),
    storageCard());
}

// Armazenamento (HDD/SSD): quanto cada parte ocupa, sobras e arquivos duplicados; «Liberar espaço» mostra a prévia e só então aplica (nada é apagado sem confirmar)
function storageCard() {
  const fmt = (n) => { let f = n, u = 0; const U = ['B', 'KB', 'MB', 'GB', 'TB']; while (f >= 1024 && u < 4) { f /= 1024; u++; } return (u ? f.toFixed(1) : Math.round(f)) + ' ' + U[u]; };
  const body = h('div', { id: 'storage-body' }, h('div', { class: 'spinner' }));
  const load = async () => {
    let r;
    try { r = await api('/api/storage'); } catch (e) { body.replaceChildren(h('div', { class: 'errbox' }, e.message)); return; }
    const free = r.orphans.bytes + r.duplicates.bytes;
    body.replaceChildren(
      h('dl', { class: 'kv', style: { margin: 0 } }, h('dt', null, t('Total do ASTA')), h('dd', { id: 'storage-total' }, fmt(r.total)),
        h('dt', null, t('Livre no disco')), h('dd', null, r.disk.total ? fmt(r.disk.free) + ' / ' + fmt(r.disk.total) : '—'),
        ...r.areas.slice(0, 8).flatMap((a) => [h('dt', null, t(a.label)), h('dd', null, fmt(a.bytes) + ' · ' + t('{n} arquivo(s)', { n: a.files }))])),
      h('p', { class: 'muted small', id: 'storage-free' }, free ? t('Dá para liberar ≈ {n}: {o} de sobras (downloads parados, anexos esquecidos) e {d} em {g} grupo(s) de arquivos idênticos (viram um só no disco, sem perder nada).', { n: fmt(free), o: fmt(r.orphans.bytes), d: fmt(r.duplicates.bytes), g: r.duplicates.groups }) : t('Nada a liberar agora: sem sobras nem arquivos duplicados.')),
      h('div', { class: 'row' }, h('button', { class: 'btn', id: 'storage-preview', type: 'button', disabled: !free, onclick: () => optimize(false) }, t('Ver o que seria feito')), h('button', { class: 'btn primary', id: 'storage-apply', type: 'button', disabled: !free, onclick: () => optimize(true) }, t('Liberar espaço')),
        h('button', { class: 'btn ghost', type: 'button', onclick: load }, icon('refresh', 14), t('Atualizar'))),
      h('div', { id: 'storage-out' }));
  };
  async function optimize(apply) {
    if (apply && !(await confirmDialog(t('Apagar as sobras e trocar os arquivos idênticos por um único arquivo no disco? Nada que você usa é perdido: os dois caminhos continuam funcionando.'), false, t('Liberar espaço')))) return;
    try {
      const r = await api('/api/storage/optimize', { method: 'POST', body: { apply } });
      const out = document.getElementById('storage-out');
      out.replaceChildren(h('p', { class: 'small', style: { margin: '10px 0 0' } }, (apply ? t('Liberado: {n}.', { n: fmt(r.freed) }) : t('Seria liberado: {n}.', { n: fmt(r.freed) })) + ' ' + t('{c} sobra(s) e {l} arquivo(s) duplicado(s).', { c: r.cleaned.length, l: r.linked.length })
        + (r.failed.length ? ' ' + t('{n} não deu para tratar.', { n: r.failed.length }) : '')));
      if (apply) { toast(t('Espaço liberado: {n}', { n: fmt(r.freed) }), 'ok'); load(); }
    } catch (e) { toast(e.message, 'err'); }
  }
  load();
  return cfgCard(t('Armazenamento'), h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Quanto o ASTA ocupa no HDD/SSD e o que dá para liberar. O núcleo Rust procura arquivos idênticos (modelos, imagens, vídeos…) e o ASTA os troca por links: o mesmo arquivo, um só no disco.')), body);
}

// ---------------------------------------------------------------------------------- dados e backup
async function data() {
  const cmd = (label, text) => h('div', { class: 'field' }, h('label', { class: 'f' }, label), h('div', { class: 'codebox' }, h('span', null, text), h('button', { class: 'btn sm ghost', onclick: () => { navigator.clipboard.writeText(text).then(() => toast(t('Copiado'))); } }, icon('copy', 13))));
  const importInput = h('input', { type: 'file', accept: '.json,application/json', class: 'hidden', onchange: async (e) => {
    const f = e.target.files[0]; e.target.value = ''; if (!f) return;
    try {
      const r = await api('/api/settings/import', { method: 'POST', body: JSON.parse(await f.text()) });
      toast(t('Configurações importadas: {n}.', { n: r.imported.join(', ') }), 'ok'); await refreshState(); location.reload();
    } catch (er) { toast(er instanceof SyntaxError ? t('Este arquivo não é um JSON válido.') : er.message, 'err'); }
  } });
  return h('div', null,
    cfgCard(t('Seus dados'),
      h('dl', { class: 'kv', style: { marginTop: 0 } }, h('dt', null, t('Pasta de dados')), h('dd', { class: 'mono small' }, state.home)),
      h('p', { class: 'muted small' }, t('Conversas, projetos, mídias, modelos e configurações ficam só no seu computador. O ASTA, ao atualizar, nunca mexe nesta pasta.')),
      cmd(t('Abrir a pasta no seu computador (terminal)'), 'asta folder')),
    cfgCard(t('Backup das configurações'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Leve suas preferências (aparência, padrões de cada seção, desempenho) para outro computador. A exportação nunca inclui chaves de API nem tokens.')),
      h('div', { class: 'row' },
        h('button', { class: 'btn sm', onclick: async () => { const r = await fetch('/api/settings/export'); download('asta-configuracoes.json', await r.text()); toast(t('Configurações exportadas (sem chaves de API).'), 'ok'); } }, icon('download', 13), t('Exportar configurações')),
        h('button', { class: 'btn sm', onclick: () => importInput.click() }, icon('upload', 13), t('Importar configurações')), importInput)),
    cfgCard(t('Restaurar tudo'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Volta aparência e os padrões de TODAS as seções ao original. Suas chaves de API, avatares, mundos, jogos, vídeos e conversas não mudam.')),
      h('button', { class: 'btn sm danger', id: 'cfg-reset-all', onclick: async () => {
        if (!(await confirmDialog(t('Restaurar a aparência e os padrões de todas as seções? Suas chaves, avatares e projetos não mudam.'), true, t('Restaurar')))) return;
        try { for (const sec of ['ui', 'generation', 'characters', 'avatars', 'games', 'canvas', 'studio', 'computer', 'rebuild', 'performance']) await api('/api/settings/reset', { method: 'POST', body: { section: sec } }); await refreshState(); location.reload(); } catch (e) { toast(e.message, 'err'); }
      } }, icon('refresh', 13), t('Restaurar tudo ao padrão'))));
}

// ---------------------------------------------------------------------------------- celular e tablet

// Computador: libera o LM Studio para o celular FORA de casa, sem VPN (túnel da Cloudflare + proxy com código secreto; ver asta/remote.py)
function remoteCard() {
  const box = h('div', { id: 'remote-lm' });
  let timer = null;
  const call = async (action, extra) => { try { return await api('/api/remote', { method: 'POST', body: Object.assign({ action }, extra || {}) }); } catch (e) { toast(e.message, 'err'); return null; } };
  async function paint(st) {
    if (!st) { try { st = await api('/api/remote'); } catch (e) { box.textContent = e.message; return; } }
    clearTimeout(timer);
    if (st.state === 'installing' || st.state === 'starting') timer = setTimeout(() => paint(), 1500);
    const msg = { off: t('Desligado'), installing: t('Baixando o cloudflared…'), starting: t('Ligando o túnel…'), on: t('Ligado'), error: t('Erro') }[st.state] || st.state;
    const link = st.link ? h('div', { class: 'codebox', id: 'remote-link' }, h('span', { class: 'mono small' }, st.link),
      h('button', { class: 'btn sm ghost', type: 'button', onclick: () => { navigator.clipboard.writeText(st.link).then(() => toast(t('Copiado'))); } }, icon('copy', 13))) : null;
    box.replaceChildren(
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Use o LM Studio deste computador pelo app do celular de qualquer lugar (4G/5G, outro Wi-Fi), sem instalar VPN no celular. O ASTA cria um endereço https temporário da Cloudflare e só deixa passar a API do LM Studio, protegida por um código secreto do link. O LM Studio precisa estar com o servidor ligado.')),
      h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap', alignItems: 'center' } }, h('b', null, msg),
        !st.installed && st.state !== 'installing' ? (st.can_download ? h('button', { class: 'btn sm primary', type: 'button', id: 'remote-install', onclick: async () => { paint(await call('install')); } }, t('Baixar o cloudflared'))
          : h('span', { class: 'muted small' }, t('Instale o cloudflared pelo gerenciador de pacotes do sistema.'))) : null,
        st.installed && st.state !== 'on' && st.state !== 'starting' ? h('button', { class: 'btn sm primary', type: 'button', id: 'remote-start', onclick: async () => { paint(await call('start')); } }, t('Ligar o acesso de fora de casa')) : null,
        st.state === 'on' || st.state === 'starting' ? h('button', { class: 'btn sm', type: 'button', id: 'remote-stop', onclick: async () => { paint(await call('stop')); } }, t('Desligar')) : null,
        st.enabled ? h('button', { class: 'btn sm danger', type: 'button', id: 'remote-rotate', onclick: async () => { if (await confirmDialog(t('Gerar um código novo? O link antigo deixa de funcionar.'), true, t('Gerar novo código'))) paint(await call('rotate')); } }, t('Gerar novo código')) : null),
      st.error ? h('p', { class: 'err small' }, st.error) : null,
      link,
      link ? h('p', { class: 'muted small' }, t('No celular: Configuração → Provedores → LM Studio → «LM Studio no computador», cole este link e toque em Conectar. O endereço muda toda vez que o acesso é ligado; quem tiver o link usa o seu LM Studio, então não o compartilhe.')) : null);
  }
  paint();
  return cfgCard(t('LM Studio fora de casa (sem VPN)'), box);
}

async function mobileTab() {
  if (/ASTA-Android/.test(navigator.userAgent || '')) {   // app Android: o ASTA roda neste aparelho; QR de pareamento e «asta mobile» são do computador
    return h('div', null, cfgCard(t('ASTA neste aparelho'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Você está no app Android: o ASTA roda dentro do aparelho, sem computador. Conversas, projetos e chaves ficam só aqui.')),
      h('p', { class: 'muted small' }, t('Para usar o ASTA de um computador (modelos locais pesados, mais memória), conecte o app a ele: o ASTA do computador continua rodando lá e este app vira a janela.')),
      h('div', { class: 'row' }, h('button', { class: 'btn', type: 'button', id: 'app-choose', onclick: () => { try { localStorage.setItem('asta.mode', 'remote'); } catch (e) { /* ok */ } location.href = 'http://localhost/?choose=1'; } }, icon('globe', 14), t('Conectar a um computador')))));
  }
  const info = await api('/api/mobile');
  if (window.ASTA_CLASSIFY) window.ASTA_CLASSIFY();
  const d = window.ASTA_DEVICE || {};
  const cmd = (text) => h('div', { class: 'codebox' }, h('span', null, text), h('button', { class: 'btn sm ghost', type: 'button', onclick: () => { navigator.clipboard.writeText(text).then(() => toast(t('Copiado'))); } }, icon('copy', 13)));
  const row = (a, b) => h('tr', null, h('th', null, a), h('td', null, b));
  let pairing;
  if (info.exposed && info.pair_urls.length) {
    const svg = new DOMParser().parseFromString(info.qr_svg, 'image/svg+xml').documentElement;   // SVG gerado pelo servidor (só números e traçados)
    pairing = cfgCard(t('Instalar no celular ou tablet'),
      h('div', { class: 'mob-qr' }, h('div', { class: 'qr', id: 'mob-qr', role: 'img', 'aria-label': t('QR code de pareamento') }, document.importNode(svg, true)),
        h('ol', null, h('li', null, t('Deixe o celular ou tablet na mesma rede Wi-Fi deste computador.')), h('li', null, t('Aponte a câmera para o QR code ao lado.')),
          h('li', null, t('Abra o link: o aparelho fica pareado e o ASTA abre.')), h('li', null, t('Instale: no Android, «Instalar»; no iPhone/iPad, Compartilhar → «Adicionar à Tela de Início».')))),
      h('p', { class: 'muted small' }, t('Endereço na rede: {u}', { u: info.urls.join(' · ') })),
      h('div', { class: 'row' }, h('button', { class: 'btn sm danger', type: 'button', id: 'mob-rotate', onclick: async () => {
        if (!(await confirmDialog(t('Gerar um código novo? Os aparelhos já pareados precisam escanear o QR code de novo.'), true, t('Gerar novo código')))) return;
        try { await api('/api/mobile/rotate', { method: 'POST', body: {} }); toast(t('Código novo gerado'), 'ok'); go('config', { tab: 'mobile' }); } catch (e) { toast(e.message, 'err'); }
      } }, icon('refresh', 13), t('Gerar novo código (desparear todos)'))));
  } else {
    pairing = cfgCard(t('Liberar o uso pelo celular'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, info.has_network
        ? t('Por segurança, o ASTA só fala com este computador. Para usar no celular ou tablet, abra o ASTA assim — só os aparelhos que você parear por QR code entram:')
        : t('Não encontrei uma rede local (Wi-Fi/Ethernet) neste computador. Conecte-se a uma rede e abra o ASTA assim:')),
      cmd('asta mobile'),
      h('p', { class: 'muted small', style: { marginBottom: 0 } }, t('O QR code de pareamento aparece aqui e no terminal.')));
  }
  const appSvg = new DOMParser().parseFromString(info.app_qr_svg, 'image/svg+xml').documentElement;
  const appCard = cfgCard(t('Baixar o app sem computador'),
    h('div', { class: 'mob-qr' }, h('div', { class: 'qr', id: 'mob-app-qr', role: 'img', 'aria-label': t('QR code do app Android') }, document.importNode(appSvg, true)),
      h('div', { style: { flex: 1, minWidth: '220px' } },
        h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Aponte a câmera do celular Android para baixar o app pelo repositório do ASTA (APK); o app avisa quando sai versão nova e pergunta se você quer baixar. No iPhone/iPad, use «Adicionar à Tela de Início» pelo endereço do ASTA. O app é a janela: o ASTA em si precisa estar rodando num computador ou servidor seu.')),
        h('a', { href: info.app_url, target: '_blank', rel: 'noopener', class: 'small mono' }, info.app_url))));
  return h('div', null, pairing, remoteCard(), appCard,
    cfgCard(t('Este aparelho'), h('table', { class: 'mob-table', id: 'mob-device' },
      row(t('Tipo'), ({ phone: t('Smartphone'), foldable: t('Smartphone dobrável'), tablet: t('Tablet'), desktop: t('Computador') })[d.device] || '—'),
      row(t('Tela'), (d.width || '?') + '×' + (d.height || '?') + ' · ' + (d.orient === 'landscape' ? t('deitado') : t('em pé')) + (d.fold ? ' · ' + t('dobrável') + ': ' + d.fold : '')),
      row(t('Plataforma'), ({ android: 'Android', ios: 'iOS / iPadOS', other: t('outra') })[d.platform] || '—'), row(t('App instalado'), d.standalone ? t('sim') : t('não')))),
    cfgCard(t('O que é compatível'), h('table', { class: 'mob-table' },
      row(t('Plataformas'), t('Android (Chrome, Edge, Samsung Internet, Firefox) e Apple (iOS e iPadOS 16.4 ou mais novo, no Safari)')),
      row(t('Arquiteturas'), t('Qualquer uma: ARM64 (Snapdragon, Apple A e M, MediaTek, Exynos, Tensor) e x86. O app roda no navegador do aparelho; o processamento pesado fica no computador.')),
      row(t('Aparelhos'), t('Smartphones, smartphones dobráveis, tablets, Chromebooks e similares. A interface se adapta sozinha ao tipo de aparelho, à orientação e ao tamanho da tela.')),
      row(t('Atualizações'), t('O app avisa quando o ASTA do computador tem versão nova e pergunta se você quer atualizar agora ou depois. Funciona em Wi-Fi e em dados móveis, desde que o aparelho alcance o computador.')))));
}

async function system() {
  const hw = state.hardware;
  const cmd = (label, text) => h('div', { class: 'field' }, h('label', { class: 'f' }, label), h('div', { class: 'codebox' }, h('span', null, text), h('button', { class: 'btn sm ghost', onclick: () => { navigator.clipboard.writeText(text).then(() => toast(t('Copiado'))); } }, icon('copy', 13))));
  return h('div', null,
    (hw.components || []).length ? h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Componentes do seu PC')),
      h('dl', { class: 'kv', id: 'hw-components', style: { margin: 0 } }, ...hw.components.flatMap((c) => [h('dt', null, t(c.type)), h('dd', null, c.name)])),
      h('p', { class: 'muted small', style: { marginBottom: 0 } }, t('Detectado no seu computador, só para mostrar aqui: nada disso é enviado para fora.'))) : null,
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
      const quants = h('div', { class: 'col', id: 'quants-' + cap, style: { gap: '6px', marginTop: '14px' } }, h('div', { class: 'small muted' }, t('Procurando versões menores (quantizadas)…')));
      area.replaceChildren(h('div', { class: 'small muted' }, t('Escolha a precisão: menos bits = download menor e mais rápido, com um pequeno custo de qualidade; o fp16 pede placa de vídeo.')), list, h('div', { style: { marginTop: '8px' } }, btn), quants);
      // versões menores (8 e 4 bits, fp8…) feitas pela comunidade: o download encolhe de verdade; usar uma delas troca o modelo escolhido por aquele repositório
      api('/api/media/local/quants?model=' + encodeURIComponent(model)).then((q) => {
        const vs = q.variants || [];
        if (!vs.length) { quants.replaceChildren(h('div', { class: 'small dim' }, t('Não há versões menores deste modelo na Hugging Face. Para modelos de texto, use as versões GGUF em Modelos locais.'))); return; }
        quants.replaceChildren(h('b', { class: 'small' }, t('Quantizações menores (da comunidade)')), h('div', { class: 'small dim' }, t('Pesos já comprimidos (8 ou 4 bits): download e memória bem menores, com algum custo de qualidade. Feitas por terceiros, não pelo ASTA.')),
          ...vs.map((v) => h('div', { class: 'quant qv', dataset: { quant: v.id } },
            h('div', { class: 'grow' }, h('div', { class: 'row', style: { gap: '8px' } }, h('b', { class: 'mono small' }, v.id), h('span', { class: 'chip' }, v.kind)), h('div', { class: 'dim small' }, t(v.note))),
            h('span', { class: 'chip solid' }, v.size ? fmtBytes(v.size) : '?'),
            v.loadable ? h('button', { class: 'btn sm', type: 'button', onclick: () => { draft.models[cap] = v.id; rows[cap].input.value = v.id; setChip(cap, ''); panel(cap); } }, icon('download', 13), t('Usar esta')) : h('span', { class: 'dim small' }, t('não suportada aqui')))));
      }).catch(() => { quants.replaceChildren(h('div', { class: 'small dim' }, t('Não consegui procurar versões menores agora (sem conexão com a Hugging Face).'))); });
    }).catch((e) => { area.replaceChildren(h('div', { class: 'res err' }, e.message)); });
  }
  for (const [cap, label] of caps) {
    const dl = h('datalist', { id: 'lm-' + cap }, ((p.suggest || {})[cap] || []).map((m) => h('option', { value: m })));
    const input = h('input', { list: 'lm-' + cap, value: draft.models[cap] || '', placeholder: p.models[cap] || '', oninput: (e) => { draft.models[cap] = e.target.value.trim(); setChip(cap, ''); } });
    chips[cap] = h('span', { class: 'chip' }, t('não baixado'));
    rows[cap] = { area: h('div'), input };
    box.append(h('div', null, h('label', { class: 'f' }, t('Modelo') + ' · ' + t(label)), h('div', { class: 'row nw' }, input, dl, chips[cap], h('button', { class: 'btn sm', onclick: () => panel(cap) }, icon('download', 13), t('Precisão e download'))), rows[cap].area));
  }
  refresh();
  return h('div', { class: 'col', style: { gap: '10px', marginBottom: '8px' } }, hint, box);
}

// ---------------------------------------------------------------------------------- avatars e jogos 2D
async function avatars() {
  const av = JSON.parse(JSON.stringify(state.settings.avatars));
  const num = numInput;
  return h('div', null, secHead('avatars', ['avatars']),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Avatars')),
      h('div', { class: 'grid2' },
        field(t('Conteúdo padrão ao criar avatars'), seg([['sfw', 'SFW'], ['nsfw', 'NSFW']], av.content, (v) => { av.content = v; }), t('Cada avatar tem a própria escolha. NSFW só vale para personagens adultos: menores de idade são sempre SFW e nunca viram par romântico.')),
        field(t('Como os avatars chamam você'), h('input', { value: av.user_name, placeholder: t('automático'), oninput: (e) => { av.user_name = e.target.value; } }))),
      field(t('Sua persona (opcional)'), h('textarea', { rows: 2, placeholder: t('Quem você é para os avatars: gostos, história, jeito de falar…'), oninput: (e) => { av.user_persona = e.target.value; } }, av.user_persona)),
      h('div', { class: 'grid2' }, field(t('Criatividade nas conversas'), range(0, 1.5, 0.05, av.temperature, (v) => { av.temperature = v; })), field(t('Máximo de tokens por resposta'), num(av, 'max_tokens', 50, 4000, 50))),
      h('div', { class: 'grid2' }, field(t('Memória de curto prazo (turnos)'), num(av, 'history_turns', 2, 80)), field(t('Memórias de longo prazo por avatar'), num(av, 'memory_limit', 5, 200))),
      h('div', { class: 'row' }, checkbox(t('Em grupo, os avatars conversam entre si sem você pedir'), av.auto_talk, (v) => { av.auto_talk = v; }), checkbox(t('Responder também por voz'), av.voice_reply, (v) => { av.voice_reply = v; })),
      h('div', { class: 'grid2' }, field(t('Máximo de falas seguidas entre avatars'), num(av, 'auto_talk_max', 1, 40), t('Depois disso eles esperam uma mensagem sua.')), field(t('Segundos entre falas autônomas'), num(av, 'auto_talk_delay', 1, 60)))),
    saveRow(() => saveSettings({ avatars: av })));
}

async function games() {
  const g = JSON.parse(JSON.stringify(state.settings.games));
  const num = numInput;
  return h('div', null, secHead('games', ['games']),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h3', null, t('Jogos 2D')),
      h('div', { class: 'grid2' }, field(t('Tamanho padrão do jogo'), seg([['short', t('Curto')], ['medium', t('Médio')], ['long', t('Longo')]], g.length, (v) => { g.length = v; })),
        field(t('Rodadas de revisão'), select([['0', t('Nenhuma (mais rápido)')], ['1', '1'], ['2', '2']], String(g.revisions), (v) => { g.revisions = parseInt(v, 10); }), t('O agente Revisor pode pedir correções.'))),
      h('div', { class: 'grid2' }, field(t('Criatividade (temperatura)'), range(0, 1.5, 0.05, g.temperature, (v) => { g.temperature = v; })), field(t('Máximo de tokens por agente'), num(g, 'max_tokens', 1000, 32000, 500)))),
    saveRow(() => saveSettings({ games: g })));
}
