// Chat — a tela principal do ASTA: conversa de uso geral com o modelo escolhido (perguntas, estudo, receitas, texto, código…).
// As criações com vários agentes (mundo 3D, avatar, jogo 2D, canvas) só rodam quando o usuário LIGA uma ferramenta (o ativador ✦): o chat nunca dispara um pipeline sozinho.
import { api, upload } from '../api.js';
import { getLang, t } from '../i18n.js';
import { go, presetOf, saveSettings, state } from '../main.js';
import { renderMarkdown } from '../markdown.js';
import { modelLabel, openModelPicker } from '../modelpicker.js';
import { readSSE } from '../avatar_ui.js';
import { confirmDialog, fill, fmtDate, h, icon, kindIcon, popover, toast } from '../ui.js';
import { createComposer, kindOf } from './composer.js';
import { HINTS, MODES, TITLES, TOOL_BUILDERS, resumeIfRunning } from './home.js';
import { clearJob } from './run.js';

const LAST_KEY = 'asta.chat';
const TOOL_LABEL = { world: 'Mundo 3D', avatar: 'Avatar', game: 'Jogo 2D', canvas: 'Canvas' };
const TOOL_ICON = { world: 'worlds', avatar: 'avatars', game: 'games', canvas: 'canvas' };

const SUGGESTIONS = () => (getLang() === 'pt'
  ? ['Como faço um bolo de cenoura fofinho?', 'Me explique a fotossíntese como se eu tivesse 12 anos', 'Monte um plano de estudos de inglês para 30 dias', 'Revise e melhore este texto: …']
  : ['How do I bake a fluffy carrot cake?', 'Explain photosynthesis like I am 12', 'Make me a 30-day English study plan', 'Proofread and improve this text: …']);

export default async function render(root, ctx) {
  if (await resumeIfRunning(root, ctx)) return;   // uma criação em andamento: mostra o acompanhamento (como sempre foi)
  const toolFromCtx = ctx.mode ? ({ game: 'game', world: 'world', avatar: 'avatar', canvas: 'canvas' })[ctx.mode] : (ctx.project ? (ctx.project.kind === 'game2d' ? 'game' : 'world') : '');
  const updating = ctx.project || null;
  const st = { chat: null, tool: toolFromCtx || '', busy: false, ctrl: null, stick: true, current: null, bubble: null, chats: [] };

  // ------------------------------------------------------------------ peças
  const hero = h('div', { class: 'chx-hero' });                   // estado vazio: título + caixa no centro
  const list = h('div', { class: 'chx-list' });                   // mensagens
  const scrollBox = h('div', { class: 'chx-scroll' }, h('div', { class: 'chx-col' }, list));
  const dock = h('div', { class: 'chx-dock' });                   // caixa de texto embaixo (quando já há conversa)
  const topTitle = h('div', { class: 'chx-title' });
  const banner = h('div', { class: 'chx-banner' });               // sugestão de ferramenta / avisos
  const below = h('div', { class: 'chx-below' });
  const newPill = h('button', { class: 'newmsgs hidden', type: 'button', onclick: () => scroll(true) }, '↓ ' + t('Novas mensagens'));
  const wrap = h('div', { class: 'chx' });

  const modelBtn = h('button', { class: 'tool mbtn', type: 'button', title: t('Trocar de modelo ou provedor'), onclick: (e) => openModelPicker(e.currentTarget, { saveSettings, go, onChange: (cur) => { st.current = cur; paintModel(); } }) });
  const paintModel = () => { modelBtn.replaceChildren(icon('sparkle', 14), h('span', { class: 'mlabel' }, modelLabel(st.current)), icon('chev', 12)); modelBtn.classList.toggle('warn', !!(st.current && st.current.demo)); };
  const toolBtn = h('button', { class: 'tool', type: 'button', title: t('Ligar uma ferramenta de criação (mundo 3D, avatar, jogo 2D, canvas)'), 'aria-haspopup': 'true', onclick: (e) => openToolMenu(e.currentTarget) });
  const paintToolBtn = () => {
    toolBtn.classList.toggle('on', !!st.tool);
    toolBtn.replaceChildren(icon('sparkle', 15), st.tool ? t(TOOL_LABEL[st.tool]) : t('Criar'),
      st.tool ? h('span', { class: 'x', title: t('Voltar a só conversar'), onclick: (e) => { e.stopPropagation(); setTool(''); } }, '×') : icon('chev', 12));
  };

  const composer = createComposer({ placeholder: t('Pergunte qualquer coisa…'), sendLabel: t('Run'), sendTitle: t('Executar'), tools: [toolBtn], rightTools: [modelBtn], onSend: (x) => (st.tool ? toolRun(x) : sendChat(x)) });

  // ------------------------------------------------------------------ ferramentas de criação (ativadores)
  let toolCfg = null;
  async function setTool(id, text) {
    st.tool = id; paintToolBtn(); banner.replaceChildren(); below.replaceChildren();
    if (text != null) composer.setText(text);
    if (!id) { toolCfg = null; composer.configure({ placeholder: t('Pergunte qualquer coisa…'), tools: [toolBtn], extraReady: null, allowEmpty: false, onSend: (x) => sendChat(x) }); paintHero(); return; }
    try { toolCfg = await TOOL_BUILDERS[id](root, updating, composer.text(), composer); }
    catch (e) { toast(e.message, 'err'); st.tool = ''; paintToolBtn(); return; }
    composer.configure({ placeholder: toolCfg.placeholder, tools: [toolBtn, ...(toolCfg.tools || [])], extraReady: toolCfg.extraReady || null, allowEmpty: !!toolCfg.allowEmpty, onSend: toolCfg.onSend });
    if (toolCfg.below) below.replaceChildren(toolCfg.below);
    paintHero(); composer.focus();
  }
  const toolRun = (x) => toolCfg.onSend(x);   // o Run da ferramenta (a mesma ação de sempre: inicia o pipeline e abre o acompanhamento)

  function openToolMenu(anchor) {
    const item = (id, label, ic, hint) => h('div', { class: 'opt toolopt' + (st.tool === id ? ' on' : ''), dataset: { tool: id }, role: 'menuitem', onclick: () => { pop.close(); setTool(id); } },
      icon(ic, 16), h('div', null, h('div', null, label), h('div', { class: 'dim small' }, hint)));
    const pop = popover(anchor, h('div', { class: 'toolmenu', role: 'menu' },
      h('div', { class: 'mp-title' }, t('Ferramentas de criação')),
      h('div', { class: 'dim small', style: { padding: '0 10px 8px' } }, t('Só rodam quando você liga uma e aperta Run.')),
      item('world', t('Mundo 3D'), 'worlds', t('Um mundo jogável com NPCs')), item('avatar', t('Avatar'), 'avatars', t('Personagens para conversar')),
      item('game', t('Jogo 2D'), 'games', t('Um jogo completo e jogável')), item('canvas', t('Canvas'), 'canvas', t('Imagem, vídeo, som e voz em nós')),
      st.tool ? h('div', { class: 'opt', onclick: () => { pop.close(); setTool(''); } }, icon('x', 16), t('Só conversar')) : null));
  }

  // ------------------------------------------------------------------ conversa
  const nearBottom = () => scrollBox.scrollHeight - scrollBox.scrollTop - scrollBox.clientHeight < 140;
  const scroll = (force) => { if (force || st.stick) { scrollBox.scrollTop = scrollBox.scrollHeight; st.stick = true; newPill.classList.add('hidden'); } else newPill.classList.remove('hidden'); };

  function msgEl(m) {
    const body = h('div', { class: 'md' });
    if (m.role === 'user') {
      body.textContent = m.text;
      const chips = (m.attachments || []).map((a) => h('span', { class: 'chip' }, kindIcon(kindOf(a.name)), a.name));
      return h('div', { class: 'cmsg user', dataset: { id: m.id || '' } }, h('div', { class: 'bubble' }, chips.length ? h('div', { class: 'row', style: { gap: '6px', marginBottom: '6px' } }, chips) : null, body));
    }
    renderMarkdown(body, m.text);
    const el = h('div', { class: 'cmsg ai', dataset: { id: m.id || '' } }, h('div', { class: 'who' }, icon('sparkle', 14), h('span', null, m.model || t('Assistente'))), body, h('div', { class: 'cacts' }));
    el._m = m; el._body = body;
    return el;
  }
  function paintActs() {
    const rows = [...list.querySelectorAll('.cmsg.ai')], last = rows[rows.length - 1];
    rows.forEach((el) => {
      const acts = el.querySelector('.cacts'); if (!acts || !el._m) return;
      const b = (ic, title, fn) => h('button', { class: 'btn ghost icon sm', type: 'button', title, onclick: fn }, icon(ic, 14));
      fill(acts, b('copy', t('Copiar'), async () => { try { await navigator.clipboard.writeText(el._m.text); toast(t('Copiado'), 'ok'); } catch (e) { toast(t('Não foi possível copiar.'), 'err'); } }),
        el === last && !st.busy ? b('refresh', t('Responder de novo'), () => regenerate()) : null);
    });
  }
  function paintHero() {
    const empty = !st.chat || !st.chat.messages.length;
    wrap.classList.toggle('empty', empty);
    topTitle.textContent = (st.chat && st.chat.title) || t('Novo chat');
    if (empty) {
      const hints = st.tool ? HINTS()[st.tool] : SUGGESTIONS();
      fill(hero, h('h1', null, st.tool ? t(TITLES[st.tool][updating ? 1 : 0] || TITLES[st.tool][0]) : t('Como posso ajudar?')),
        updating && st.tool ? h('div', { class: 'ctxbar' }, h('span', { class: 'chip' }, icon('refresh', 13), t('Atualizando:') + ' ' + updating.name + ' (v' + updating.current + ')', h('span', { class: 'x', title: t('Criar algo novo'), onclick: () => go('main', { fresh: true }) }, '×'))) : null,
        composer.el, below, banner,
        h('div', { class: 'suggest' }, (st.tool && updating ? [] : hints).map((s) => h('button', { type: 'button', onclick: () => { composer.setText(s); composer.focus(); } }, s.length > 62 ? s.slice(0, 60) + '…' : s))),
        engineNote());
      dock.replaceChildren(); scrollBox.classList.add('hidden'); hero.classList.remove('hidden');
    } else {
      dock.replaceChildren(h('div', { class: 'chx-col' }, banner, composer.el, below, engineNote(true)));
      hero.replaceChildren(); hero.classList.add('hidden'); scrollBox.classList.remove('hidden');
    }
  }
  const engineNote = (compact) => {
    const demo = st.current && st.current.demo;
    return demo ? h('div', { class: 'notice' }, t('Modo Demo (sem IA): o Chat não consegue responder perguntas de verdade. '), h('a', { href: '#/config', onclick: (e) => { e.preventDefault(); go('config', { tab: 'providers' }); } }, t('Configure um provedor')), t(' ou escolha um modelo no botão ao lado do Run.'))
      : (compact ? null : h('div', { class: 'notice' }, st.current ? t(st.current.label || '') : presetOf(state.settings.active.generation).label));
  };

  async function openChat(id) {
    try { st.chat = await api('/api/chats/' + id); } catch (e) { st.chat = null; try { localStorage.removeItem(LAST_KEY); } catch (er) { /* ok */ } return; }
    try { localStorage.setItem(LAST_KEY, id); } catch (e) { /* ok */ }
    list.replaceChildren(...st.chat.messages.map(msgEl)); paintActs(); paintHero(); scroll(true);
  }
  function newChat() {
    st.chat = null; list.replaceChildren(); try { localStorage.removeItem(LAST_KEY); } catch (e) { /* ok */ }
    banner.replaceChildren(); if (st.tool) setTool(''); paintHero(); composer.focus();
  }
  async function ensureChat() {
    if (!st.chat) { st.chat = await api('/api/chats', { method: 'POST', body: {} }); try { localStorage.setItem(LAST_KEY, st.chat.id); } catch (e) { /* ok */ } }
    return st.chat;
  }

  function onEvent(ev, ctl) {
    if (ev.type === 'user') {
      st.chat.messages.push(ev.message);
      if (ctl.pending) { ctl.pending.dataset.id = ev.message.id; ctl.pending = null; }
    } else if (ev.type === 'title') { st.chat.title = ev.title; topTitle.textContent = ev.title; }
    else if (ev.type === 'provider') { st.current = Object.assign({}, st.current, ev); paintModel(); }
    else if (ev.type === 'notice') banner.replaceChildren(h('div', { class: 'chx-note' }, ev.message));
    else if (ev.type === 'typing') {
      ctl.buf = '';
      ctl.body = h('div', { class: 'md' }, h('span', { class: 'dots' }, h('i'), h('i'), h('i')));
      ctl.el = h('div', { class: 'cmsg ai typing' }, h('div', { class: 'who' }, icon('sparkle', 14), h('span', null, modelLabel(st.current))), ctl.body, h('div', { class: 'cacts' }));
      list.appendChild(ctl.el); scroll();
    } else if (ev.type === 'delta' && ctl.body) { ctl.buf += ev.text; ctl.el.classList.remove('typing'); renderMarkdown(ctl.body, ctl.buf); scroll(); }
    else if (ev.type === 'removed') {
      const ids = new Set(ev.ids || []);
      st.chat.messages = st.chat.messages.filter((x) => !ids.has(x.id));
      list.querySelectorAll('.cmsg').forEach((el) => { if (ids.has(el.dataset.id)) el.remove(); });
    } else if (ev.type === 'message') {
      st.chat.messages.push(ev.message);
      if (ctl.el) ctl.el.remove();
      const el = msgEl(ev.message); list.appendChild(el); ctl.el = null; paintActs(); scroll();
    } else if (ev.type === 'suggest') {
      banner.replaceChildren(h('div', { class: 'csuggest' }, icon('sparkle', 15), h('span', { class: 'grow' }, t('Parece que você quer criar: {n}. Quer ligar essa ferramenta?', { n: t(TOOL_LABEL[ev.tool]) })),
        h('button', { class: 'btn sm primary', type: 'button', onclick: () => { setTool(ev.tool, ev.prompt); } }, icon(TOOL_ICON[ev.tool], 13), t('Ligar {n}', { n: t(TOOL_LABEL[ev.tool]) })),
        h('button', { class: 'btn sm ghost', type: 'button', onclick: () => banner.replaceChildren() }, t('Agora não'))));
    } else if (ev.type === 'error') { if (ctl.el) { ctl.el.remove(); ctl.el = null; } banner.replaceChildren(h('div', { class: 'chx-note err' }, '⚠ ' + ev.message)); }
  }

  async function run(url, body, pending) {
    st.busy = true; st.ctrl = new AbortController(); composer.setBusy(true, stop); paintActs();
    const ctl = { pending: pending || null };   // `pending` liga o balão local da pergunta ao id vindo do servidor
    try {
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: st.ctrl.signal });
      if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || 'HTTP ' + r.status); }
      await readSSE(r, (ev) => onEvent(ev, ctl));
    } catch (e) { if (e.name !== 'AbortError') banner.replaceChildren(h('div', { class: 'chx-note err' }, '⚠ ' + (e.message || e))); }
    finally {
      st.busy = false; st.ctrl = null; composer.setBusy(false);
      if (ctl.el) ctl.el.remove();   // resposta cortada pelo botão Parar: nada pela metade
      paintActs(); paintHero(); refreshChats();
    }
  }
  function stop() { if (st.ctrl) { try { st.ctrl.abort(); } catch (e) { /* ok */ } } }

  async function sendChat({ text, ids }) {
    const msg = String(text || '').trim();
    if (!msg && !(ids && ids.length)) return;
    try { await ensureChat(); } catch (e) { return toast(e.message, 'err'); }
    banner.replaceChildren();
    const local = { id: '', role: 'user', text: msg || t('(anexo)'), attachments: [...composer.el.querySelectorAll('.att .n')].map((n) => ({ name: n.textContent })) };
    if (!st.chat.messages.length) list.replaceChildren();
    const el = msgEl(local); list.appendChild(el);
    composer.setText(''); composer.clearFiles(); paintHero(); scroll(true);
    await run('/api/chats/' + st.chat.id + '/send', { text: msg, attachment_ids: ids || [] }, el);
  }
  async function regenerate() { if (!st.chat || st.busy) return; banner.replaceChildren(); await run('/api/chats/' + st.chat.id + '/regenerate', {}); }

  // ------------------------------------------------------------------ histórico
  async function refreshChats() { try { st.chats = await api('/api/chats'); } catch (e) { /* ok */ } }
  async function openHistory(anchor) {
    await refreshChats();
    const body = h('div', { class: 'mpick' }, h('div', { class: 'mp-title' }, t('Conversas')));
    const pop = popover(anchor, body);
    const paint = () => body.replaceChildren(h('div', { class: 'mp-title' }, t('Conversas')), ...(st.chats.length ? st.chats.map((c) => h('div', { class: 'mp-prov hist' + (st.chat && st.chat.id === c.id ? ' on' : ''), role: 'button', tabindex: '0', onclick: () => { pop.close(); openChat(c.id); } },
      h('div', { class: 'grow', style: { minWidth: 0 } }, h('div', { class: 'hn' }, c.title), h('div', { class: 'dim small hn' }, fmtDate(c.updated) + ' · ' + c.last)),
      h('button', { class: 'btn ghost icon sm', type: 'button', title: t('Apagar conversa'), onclick: async (e) => {
        e.stopPropagation();
        if (!(await confirmDialog(t('Apagar esta conversa?')))) return;
        await api('/api/chats/' + c.id, { method: 'DELETE' });
        if (st.chat && st.chat.id === c.id) newChat();
        await refreshChats(); paint();
      } }, icon('trash', 13)))) : [h('div', { class: 'dim small', style: { padding: '8px 10px' } }, t('Nenhuma conversa ainda.'))]));
    paint();
  }

  // ------------------------------------------------------------------ montagem
  scrollBox.addEventListener('scroll', () => { st.stick = nearBottom(); if (st.stick) newPill.classList.add('hidden'); });
  const top = h('div', { class: 'chx-top' }, topTitle, h('span', { class: 'grow' }),
    h('button', { class: 'btn ghost sm', type: 'button', id: 'chat-history', title: t('Conversas anteriores'), onclick: (e) => openHistory(e.currentTarget) }, icon('library', 15), t('Histórico')),
    h('button', { class: 'btn ghost sm', type: 'button', id: 'chat-new', title: t('Novo chat'), onclick: newChat }, icon('plus', 15), t('Novo chat')));
  wrap.append(top, hero, scrollBox, newPill, dock);
  root.replaceChildren(wrap);
  paintToolBtn(); paintModel();
  api('/api/chat/providers').then((r) => { st.current = r.current; paintModel(); paintHero(); }).catch(() => {});
  if (ctx.fresh) clearJob();
  // abre a última conversa (a menos que a pessoa tenha vindo para criar algo ou pedido um chat novo)
  let last = ''; try { last = localStorage.getItem(LAST_KEY) || ''; } catch (e) { /* ok */ }
  if (last && !ctx.fresh && !toolFromCtx && !ctx.prompt) await openChat(last);
  paintHero();
  if (toolFromCtx) await setTool(toolFromCtx, ctx.prompt || '');
  else if (ctx.prompt) composer.setText(ctx.prompt);
  composer.focus();
}
