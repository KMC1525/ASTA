import { api } from '../api.js';
import { t } from '../i18n.js';
import { go, state } from '../main.js';
import { avatarPic, MOOD_EMOJI, readSSE, REL_LABEL, richText, speakerColor } from '../avatar_ui.js';
import { confirmDialog, field, fill, h, icon, modal, popover, select, toast } from '../ui.js';
import { detectLang, Listener, listenSupported, Speaker, speechSupported } from '../voice.js';
import { openChat } from './avatars.js';

const SPEAK_KEY = 'asta.avatars.speak';

export default async function render(root, ctx, chatId) {
  let chat, chats;
  try { [chat, chats] = await Promise.all([api('/api/avatar-chats/' + chatId), api('/api/avatar-chats')]); } catch (e) { location.hash = '#/avatars'; return; }
  const cfg = state.settings.avatars || {};
  const people = {};
  const reindex = () => { Object.keys(people).forEach((k) => delete people[k]); chat.avatars.forEach((a) => (people[a.id] = a)); };
  reindex();

  const st = { busy: false, seq: 0, ctrl: null, kind: '', tick: 0, auto: !!chat.auto_talk, limit: false, voiceMode: false, bubbles: {}, mood: {}, speaking: null, dead: false };
  const multi = () => chat.mode === 'multi';
  const lastUserText = () => { const u = chat.messages.slice().reverse().find((m) => m.role === 'user'); return u ? u.text : ''; };

  const msgs = h('div', { class: 'chmsgs' });
  const head = h('div', { class: 'chhead' });
  const engineBar = h('div', { class: 'chengine' });   // qual IA responde (ou o aviso de que é só o Demo)
  const listEl = h('div', { class: 'chlist' });
  const input = h('textarea', { rows: 1, placeholder: t('Escreva uma mensagem…') });
  const sendBtn = h('button', { class: 'btn icon primary', title: t('Enviar'), onclick: () => send(input.value) }, icon('send', 17));
  const micBtn = h('button', { class: 'btn icon', title: t('Falar'), onclick: () => listener.toggle() }, icon('mic', 17));

  // ------------------------------------------------------------------ voz
  const speaker = new Speaker({ onSpeaking: (a) => { st.speaking = a ? a.id : null; paintHead(); if (!a) afterTurn(); } });
  speaker.enabled = localStorage.getItem(SPEAK_KEY) != null ? localStorage.getItem(SPEAK_KEY) === '1' : cfg.voice_reply !== false;
  const listener = new Listener({
    getLang: () => detectLang(lastUserText(), (chat.avatars[0] && chat.avatars[0].voice && chat.avatars[0].voice.lang !== 'auto' && chat.avatars[0].voice.lang) || (state.settings.language === 'en' ? 'en-US' : navigator.language)),
    onInterim: (txt) => { input.value = txt; autosize(); },
    onFinal: (txt) => { input.value = ''; send(txt); },
    onState: (on) => { micBtn.classList.toggle('on', on); if (!on && st.voiceMode && !st.busy && !speaker.speaking) setTimeout(() => { if (st.voiceMode && !st.busy && !listener.listening && !speaker.speaking && !st.dead) listener.start(); }, 700); },
    onError: (e) => toast(e.message || String(e), 'err'),
  });

  // ------------------------------------------------------------------ renderização
  const scroll = () => { msgs.scrollTop = msgs.scrollHeight; };
  const autosize = () => { input.style.height = 'auto'; input.style.height = Math.min(120, input.scrollHeight) + 'px'; };
  const userLabel = () => chat.user_name || cfg.user_name || t('Você');

  function row(m) {
    const mine = m.role === 'user', a = people[m.avatar_id];
    const text = h('div', { class: 'mtext' });
    richText(text, m.text);
    return h('div', { class: 'msg ' + (mine ? 'me' : 'av') },
      mine ? null : h('div', { class: 'mpic' }, avatarPic(a || { name: m.name, appearance: {} }, 34, m.mood || 'neutral')),
      h('div', { class: 'mbody' }, !mine && multi() ? h('div', { class: 'mname', style: { color: speakerColor(a) } }, m.name) : null, text));
  }
  const note = (txt, extra) => { const el = h('div', { class: 'sysmsg' }, txt, extra || null); msgs.appendChild(el); scroll(); return el; };

  function startBubble(id, name) {
    removeBubble(id);
    const a = people[id], text = h('div', { class: 'mtext' }, h('span', { class: 'dots' }, h('i'), h('i'), h('i')));
    const rowEl = h('div', { class: 'msg av typing' }, h('div', { class: 'mpic' }, avatarPic(a || { name }, 34, st.mood[id] || 'neutral')),
      h('div', { class: 'mbody' }, multi() ? h('div', { class: 'mname', style: { color: speakerColor(a) } }, name) : null, text));
    msgs.appendChild(rowEl); scroll();
    st.bubbles[id] = { row: rowEl, text, buf: '' };
  }
  function removeBubble(id) { const b = st.bubbles[id]; if (b) { b.row.remove(); delete st.bubbles[id]; } }

  function paintHead() {
    const a0 = chat.avatars[0], typing = Object.keys(st.bubbles)[0];
    const eff = chat.content === 'sfw' || chat.avatars.some((a) => a.content !== 'nsfw') ? 'SFW' : 'NSFW';
    const tog = (on, label, ic, fn, title) => h('button', { class: 'btn icon sm' + (on ? ' on' : ''), title, onclick: fn }, label || icon(ic, 16));
    fill(head,
      h('a', { class: 'btn ghost icon sm', href: '#/avatars', title: t('Todos os avatares') }, '←'),
      multi() ? h('div', { class: 'stack' }, chat.avatars.map((a) => h('span', { class: 'spk' + (st.speaking === a.id || st.bubbles[a.id] ? ' on' : ''), title: a.name }, avatarPic(a, 36, st.mood[a.id] || 'neutral'))))
        : h('span', { class: 'spk' + (st.speaking || typing ? ' on' : '') }, avatarPic(a0, 44, st.mood[a0.id] || 'neutral')),
      h('div', { class: 'grow', style: { minWidth: 0 } },
        h('div', { class: 't' }, chat.title || chat.avatars.map((a) => a.name).join(', ')),
        h('div', { class: 's' }, typing ? (people[typing] ? people[typing].name : '…') + ' ' + t('está digitando…')
          : multi() ? chat.avatars.map((a) => a.name).join(' · ') : t(REL_LABEL[a0.relationship] || REL_LABEL.custom) + ' ' + (MOOD_EMOJI[st.mood[a0.id]] || ''))),
      h('span', { class: 'chip ' + (eff === 'NSFW' ? 'nsfw' : 'solid'), title: t('O modo mais restritivo entre os participantes vale para a conversa.') }, eff),
      speechSupported() ? tog(speaker.enabled, '🔊', null, () => { speaker.enabled = !speaker.enabled; localStorage.setItem(SPEAK_KEY, speaker.enabled ? '1' : '0'); if (!speaker.enabled) speaker.stop(); paintHead(); }, t('Falar as respostas em voz alta')) : null,
      listenSupported() ? tog(st.voiceMode, '🎧', null, toggleVoiceMode, t('Conversa por voz (microfone sempre atento)')) : null,
      multi() ? tog(st.auto, '💬', null, toggleAuto, t('Conversa livre: os avatares conversam entre si sem você pedir')) : null,
      h('button', { class: 'btn ghost icon sm', title: t('Mais'), onclick: (e) => menu(e.currentTarget) }, icon('more', 16)));
  }

  // Mostra qual IA está respondendo. No Demo (respostas pré-programadas, sem IA) avisa o motivo e leva à configuração.
  function paintEngine(info) {
    if (!info) { engineBar.replaceChildren(); engineBar.style.display = 'none'; return; }
    engineBar.style.display = '';
    if (info.demo) {
      engineBar.className = 'chengine warn';
      engineBar.replaceChildren(h('div', { class: 'grow' }, h('b', null, t('Modo Demo: as respostas são pré-programadas, sem IA.')), ' ',
        info.reason ? h('span', null, info.reason + ' ') : null, h('span', null, t('Configure um provedor de IA — nuvem ou local — para os avatares responderem com inteligência de verdade.'))),
        h('button', { class: 'btn sm primary', onclick: () => go('config', { tab: 'providers' }) }, t('Configurar IA')));
    } else {
      engineBar.className = 'chengine ok';
      engineBar.replaceChildren(h('span', { class: 'dim small' }, '✦ ' + t('Responde com {n}', { n: t(info.label) + (info.model ? ' · ' + info.model : '') })));
    }
  }

  function paintList() {
    listEl.replaceChildren(h('div', { class: 'row', style: { padding: '2px 4px 10px' } }, h('strong', null, t('Conversas')), h('span', { class: 'grow' }),
      h('button', { class: 'btn sm', onclick: newChat }, icon('plus', 13), t('Nova'))),
      ...chats.map((c) => h('a', { class: 'li' + (c.id === chat.id ? ' active' : ''), href: '#/avatars/chat/' + c.id },
        h('div', { class: 'av' }, icon(c.mode === 'multi' ? 'characters' : 'send', 14)),
        h('div', { style: { minWidth: 0 } }, h('div', { class: 't' }, c.title || '…'), h('div', { class: 's' }, c.last ? c.last.text : '')))));
  }

  // ------------------------------------------------------------------ eventos do servidor
  function onEvent(ev) {
    if (ev.type === 'provider') paintEngine(ev);
    else if (ev.type === 'typing') { startBubble(ev.avatar_id, ev.name); paintHead(); }
    else if (ev.type === 'delta') {
      const b = st.bubbles[ev.avatar_id]; if (!b) return;
      b.buf += ev.text; b.row.classList.remove('typing'); richText(b.text, b.buf); scroll();
    } else if (ev.type === 'message') {
      const m = ev.message; removeBubble(m.avatar_id);
      chat.messages.push(m); if (m.mood) st.mood[m.avatar_id] = m.mood;
      msgs.appendChild(row(m)); scroll(); paintHead();
      speaker.say(m.text, people[m.avatar_id] || { id: m.avatar_id, name: m.name });
      if (ev.remembered && ev.remembered.length) note('🧠 ' + t('{n} guardou uma memória', { n: m.name }));
    } else if (ev.type === 'silence') { removeBubble(ev.avatar_id); paintHead(); }
    else if (ev.type === 'end') { st.reason = ev.reason; }
    else if (ev.type === 'error') { Object.keys(st.bubbles).forEach(removeBubble); note('⚠ ' + ev.message); }
  }

  async function turn(url, body, kind) {
    const my = ++st.seq;
    if (st.ctrl) { try { st.ctrl.abort(); } catch (e) { /* ok */ } }
    st.busy = true; st.kind = kind; st.reason = ''; sendBtn.disabled = kind === 'send';
    const ctrl = (st.ctrl = new AbortController());
    try {
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}), signal: ctrl.signal });
      if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || 'HTTP ' + r.status); }
      await readSSE(r, onEvent);
    } catch (e) { if (e.name !== 'AbortError') note('⚠ ' + (e.message || e)); }
    finally {
      if (my === st.seq) { st.busy = false; sendBtn.disabled = false; Object.keys(st.bubbles).forEach(removeBubble); paintHead(); afterTurn(); }
    }
  }

  async function send(text) {
    text = String(text || '').trim();
    if (!text) return;
    input.value = ''; autosize(); clearTimeout(st.tick); st.limit = false; speaker.stop(); listener.stop();
    const m = { role: 'user', name: userLabel(), text }; chat.messages.push(m); msgs.appendChild(row(m)); scroll();
    chats = chats.map((c) => (c.id === chat.id ? Object.assign({}, c, { last: { name: m.name, text: m.text.slice(0, 120), role: 'user' } }) : c)); paintList();
    await turn('/api/avatar-chats/' + chat.id + '/send', { text }, 'send');
  }

  // ------------------------------------------------------------------ conversa livre entre avatares
  function afterTurn() {
    if (st.dead || !root.isConnected) return;
    if (st.voiceMode) { speaker.whenIdle(() => { if (st.voiceMode && !st.busy && !listener.listening && !st.dead) listener.start(); }); return; }
    scheduleTick();
  }
  function scheduleTick() {
    clearTimeout(st.tick);
    if (!st.auto || !multi() || st.busy || st.limit || document.hidden || st.dead || speaker.speaking) return;
    const delay = Math.max(2, Number(cfg.auto_talk_delay) || 6) * 1000;
    st.tick = setTimeout(() => {
      if (st.dead || st.busy || (document.activeElement === input && input.value.trim())) return scheduleTick();
      speaker.whenIdle(async () => {
        if (st.dead || st.busy) return;
        await turn('/api/avatar-chats/' + chat.id + '/tick', {}, 'tick');
        if (st.reason === 'limit') { st.limit = true; note(t('Os avatares fizeram uma pausa. Escreva algo ou '), h('a', { href: '#', onclick: (e) => { e.preventDefault(); st.limit = false; turn('/api/avatar-chats/' + chat.id + '/tick', { more: true }, 'tick'); } }, t('deixe-os conversar mais'))); }
        else if (st.reason === 'disabled') st.auto = false;
        else if (st.reason === 'busy') setTimeout(scheduleTick, 1500);
      });
    }, delay);
  }
  async function toggleAuto() {
    st.auto = !st.auto; st.limit = false; paintHead();
    try { await api('/api/avatar-chats/' + chat.id, { method: 'PUT', body: { auto_talk: st.auto } }); chat.auto_talk = st.auto; } catch (e) { toast(e.message, 'err'); }
    if (st.auto) scheduleTick(); else clearTimeout(st.tick);
  }
  function toggleVoiceMode() {
    st.voiceMode = !st.voiceMode;
    if (st.voiceMode) { speaker.enabled = true; localStorage.setItem(SPEAK_KEY, '1'); clearTimeout(st.tick); if (!st.busy) listener.start(); } else listener.stop();
    paintHead();
  }

  // ------------------------------------------------------------------ menus e janelas
  async function newChat() {
    const all = await api('/api/avatars'), pick = new Set();
    if (!all.length) return toast(t('Crie um avatar primeiro.'), 'err');
    const body = h('div', { class: 'col' }, h('p', { class: 'muted small', style: { margin: 0 } }, t('Escolha um avatar (conversa single) ou vários (grupo, em que eles conversam entre si).')),
      ...all.map((a) => h('label', { class: 'check' }, h('input', { type: 'checkbox', onchange: (e) => { e.target.checked ? pick.add(a.id) : pick.delete(a.id); } }), avatarPic(a, 28), h('span', null, a.name))));
    const v = await modal(t('Nova conversa'), body, [{ label: t('Cancelar'), value: null }, { label: t('Começar'), value: 'ok', cls: 'primary' }]);
    if (v === 'ok' && pick.size) openChat([...pick]);
  }

  async function settingsDialog() {
    const d = { title: chat.title || '', user_name: chat.user_name || '', user_persona: chat.user_persona || '', content: chat.content, auto_talk: st.auto };
    const body = h('div', null,
      field(t('Título'), h('input', { value: d.title, oninput: (e) => { d.title = e.target.value; } })),
      field(t('Como os avatares chamam você'), h('input', { value: d.user_name, placeholder: cfg.user_name || t('Você'), oninput: (e) => { d.user_name = e.target.value; } })),
      field(t('Sobre você (opcional)'), h('textarea', { rows: 3, placeholder: t('Gostos, profissão, como prefere ser tratado(a)…'), oninput: (e) => { d.user_persona = e.target.value; } }, d.user_persona)),
      field(t('Conteúdo desta conversa'), select([['auto', t('Automático (segue os avatares)')], ['sfw', t('Forçar SFW')]], d.content, (v) => { d.content = v; }), t('O modo mais restritivo entre os participantes vale para a conversa.')));
    const v = await modal(t('Configurar conversa'), body, [{ label: t('Cancelar'), value: null }, { label: t('Salvar'), value: 'ok', cls: 'primary' }]);
    if (v !== 'ok') return;
    await api('/api/avatar-chats/' + chat.id, { method: 'PUT', body: d });
    Object.assign(chat, d); paintHead(); toast(t('Salvo'), 'ok');
  }

  async function memoriesDialog() {
    const box = h('div', { class: 'col' });
    const paintFor = async (av) => {
      const { memories } = await api('/api/avatars/' + av.id + '/memory');
      fill(box, ...(memories.length ? memories.map((m) => h('div', { class: 'card', style: { padding: '8px 12px' } }, m)) : [h('div', { class: 'muted small' }, t('Ainda não há memórias.'))]),
        memories.length ? h('button', { class: 'btn sm danger', onclick: async () => { await api('/api/avatars/' + av.id + '/memory', { method: 'DELETE' }); paintFor(av); } }, t('Esquecer tudo')) : null);
    };
    const holder = h('div', null, multi() ? select(chat.avatars.map((a) => [a.id, a.name]), chat.avatars[0].id, (v) => paintFor(people[v])) : null, box);
    paintFor(chat.avatars[0]);
    await modal(t('Memórias de longo prazo'), holder, [{ label: t('Fechar'), value: null }]);
  }

  function menu(anchor) {
    const item = (label, fn, cls) => h('div', { class: 'opt ' + (cls || ''), onclick: () => { pop.close(); fn(); } }, label);
    const pop = popover(anchor, h('div', null,
      item('🧠 ' + t('Memórias'), memoriesDialog),
      item('⚙ ' + t('Configurar conversa'), settingsDialog),
      item(t('Reiniciar conversa'), async () => { if (await confirmDialog(t('Apagar todas as mensagens desta conversa?'))) { await api('/api/avatar-chats/' + chat.id + '/reset', { method: 'POST' }); location.reload(); } }),
      item(t('Apagar conversa'), async () => { if (await confirmDialog(t('Apagar esta conversa?'))) { await api('/api/avatar-chats/' + chat.id, { method: 'DELETE' }); location.hash = '#/avatars'; } }, 'danger')));
  }

  // ------------------------------------------------------------------ montagem
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(input.value); } });
  input.addEventListener('input', () => { autosize(); clearTimeout(st.tick); });
  input.addEventListener('blur', () => { if (!st.busy) scheduleTick(); });
  root.replaceChildren(h('div', { class: 'chatpage' }, listEl, h('section', { class: 'chatmain' }, head, engineBar, msgs,
    h('div', { class: 'chinput' }, listenSupported() ? micBtn : null, input, sendBtn))));
  paintList(); paintHead(); paintEngine(null);
  api('/api/avatars/engine').then(paintEngine).catch(() => {});
  chat.messages.slice(-200).forEach((m) => msgs.appendChild(row(m)));
  if (!chat.messages.length) note(t('Diga olá! Quando o avatar não souber algo sobre você, ele vai perguntar — e lembrar.'));
  scroll(); input.focus();
  document.addEventListener('visibilitychange', () => { if (!document.hidden) scheduleTick(); });
  addEventListener('hashchange', () => {
    st.dead = true; clearTimeout(st.tick); speaker.stop(); listener.stop();
    if (st.ctrl) { try { st.ctrl.abort(); } catch (e) { /* ok */ } }
  }, { once: true });
  scheduleTick();
}
