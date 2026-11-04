/* ASTA runtime — agentes de IA dos NPCs: conversa, memória, ações, voz e autonomia. */
(function () {
  'use strict';
  const RT = window.RT;

  // ---------------------------------------------------------------- textos da interface
  const STR = {
    pt: {
      play: 'Jogar', loading: 'Gerando o mundo…', ready: 'Pronto', talk: 'Falar com', pressE: 'E', placeholder: 'Escreva uma mensagem…',
      send: 'Enviar', close: 'Fechar', notConfigured: 'Para conversar, configure uma IA em ⚙ Configurações (ou abra este mundo pelo ASTA).',
      thinking: 'pensando…', settings: 'Configurações do jogo', quality: 'Qualidade', auto: 'Automática', low: 'Baixa', medium: 'Média', high: 'Alta',
      perspective: 'Perspectiva', first: 'Primeira pessoa', third: 'Terceira pessoa', volume: 'Volume geral', music: 'Música', ambience: 'Ambiente',
      autonomy: 'Autonomia dos NPCs (consome tokens)', off: 'Desligada', lowA: 'Baixa (a cada ~60 s)', highA: 'Alta (a cada ~25 s)',
      ai: 'IA dos personagens', hosted: 'Usando o provedor configurado no ASTA', kind: 'Tipo de API', openai: 'OpenAI-compatível', anthropic: 'Anthropic (Claude)',
      baseUrl: 'URL base', apiKey: 'Chave de API (fica só neste navegador)', model: 'Modelo', test: 'Testar', save: 'Salvar', cancel: 'Fechar',
      voiceReply: 'Falar as respostas em voz alta', sttLang: 'Idioma da fala (auto = idioma do navegador)', resetSave: 'Apagar progresso salvo',
      reload: 'Aplicar e recarregar', mic: 'Falar', voiceMode: 'Conversa por voz', saved: 'Progresso salvo', ok: 'Funcionou!', failed: 'Falhou',
      help: ['<kbd>WASD</kbd> mover', '<kbd>Shift</kbd> correr', '<kbd>Espaço</kbd> pular', '<kbd>V</kbd> 1ª/3ª pessoa', '<kbd>E</kbd> conversar', '<kbd>M</kbd> mapa', '<kbd>Esc</kbd> soltar mouse'],
      day: 'dia', night: 'noite', actions: { follow: 'segue você', stay: 'fica parado(a)', wander: 'volta à rotina', wave: 'acena', nod: 'acena com a cabeça', dance: 'dança', flee: 'foge', goto: 'vai para' },
      quality_note: 'Qualidade', clickToPlay: 'Clique para capturar o mouse', mobileTalk: 'Falar',
    },
    en: {
      play: 'Play', loading: 'Generating world…', ready: 'Ready', talk: 'Talk to', pressE: 'E', placeholder: 'Write a message…',
      send: 'Send', close: 'Close', notConfigured: 'To chat, set up an AI in ⚙ Settings (or open this world through ASTA).',
      thinking: 'thinking…', settings: 'Game settings', quality: 'Quality', auto: 'Automatic', low: 'Low', medium: 'Medium', high: 'High',
      perspective: 'Perspective', first: 'First person', third: 'Third person', volume: 'Master volume', music: 'Music', ambience: 'Ambience',
      autonomy: 'NPC autonomy (uses tokens)', off: 'Off', lowA: 'Low (every ~60 s)', highA: 'High (every ~25 s)',
      ai: 'Character AI', hosted: 'Using the provider configured in ASTA', kind: 'API type', openai: 'OpenAI-compatible', anthropic: 'Anthropic (Claude)',
      baseUrl: 'Base URL', apiKey: 'API key (stays in this browser only)', model: 'Model', test: 'Test', save: 'Save', cancel: 'Close',
      voiceReply: 'Speak replies out loud', sttLang: 'Speech language (auto = browser language)', resetSave: 'Erase saved progress',
      reload: 'Apply and reload', mic: 'Speak', voiceMode: 'Voice conversation', saved: 'Progress saved', ok: 'It works!', failed: 'Failed',
      help: ['<kbd>WASD</kbd> move', '<kbd>Shift</kbd> run', '<kbd>Space</kbd> jump', '<kbd>V</kbd> 1st/3rd person', '<kbd>E</kbd> talk', '<kbd>M</kbd> map', '<kbd>Esc</kbd> release mouse'],
      day: 'day', night: 'night', actions: { follow: 'follows you', stay: 'stays put', wander: 'goes back to routine', wave: 'waves', nod: 'nods', dance: 'dances', flee: 'runs away', goto: 'heads to' },
      quality_note: 'Quality', clickToPlay: 'Click to capture the mouse', mobileTalk: 'Talk',
    },
  };
  const lang = ((window.ASTA_WORLD && window.ASTA_WORLD.language) || navigator.language || 'en').toLowerCase();
  RT.lang = lang;
  RT.S = STR[lang.indexOf('pt') === 0 ? 'pt' : 'en'];
  RT.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ---------------------------------------------------------------- SSE
  async function readSSE(resp, onEvent) {
    const reader = resp.body.getReader(), dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const r = await reader.read();
      if (r.done) break;
      buf += dec.decode(r.value, { stream: true }).replace(/\r\n/g, '\n');
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        let event = 'message', data = '';
        chunk.split('\n').forEach((l) => { if (l.indexOf('event:') === 0) event = l.slice(6).trim(); else if (l.indexOf('data:') === 0) data += l.slice(5).trim(); });
        if (data) onEvent(event, data);
      }
    }
  }

  // ---------------------------------------------------------------- agente
  RT.Agent = function (opts) {
    this.cfg = opts.cfg || { mode: 'standalone' };
    this.meta = opts.meta || {};
    this.world = opts.world;
    this.chars = opts.chars || [];
    this.getContext = opts.getContext;
    this.onAction = opts.onAction || function () {};
    this.onChange = opts.onChange || function () {};
    this.onOpen = opts.onOpen || function () {};
    this.onClose = opts.onClose || function () {};
    this.chat = this.meta.chat || {};
    this.mem = {};
    this.info = { tts: false, stt: false };
    this.key = 'asta.llm.' + (this.cfg.project || 'local');
    this.settings = Object.assign({ kind: 'openai', baseUrl: '', apiKey: '', model: '', voiceReply: true, sttLang: 'auto', autonomy: (this.world.gameplay && this.world.gameplay.npc_autonomy) || 'off' }, this._load());
    this.current = null; this.busy = false; this.voiceMode = false;
    this.autoT = 12; this.autoBusy = false;
    this._buildUI();
    if (this.cfg.mode === 'hosted') fetch(this.cfg.api + '/info').then((r) => r.json()).then((i) => { this.info = i; this._refreshMic(); }).catch(() => {});
    this.speaker = new Speaker(this);
  };
  const A = RT.Agent.prototype;
  A._load = function () { try { return JSON.parse(localStorage.getItem(this.key) || '{}'); } catch (e) { return {}; } };
  A.saveSettings = function () { try { localStorage.setItem(this.key, JSON.stringify(this.settings)); } catch (e) { /* ignorado */ } };
  A.cardOf = function (npc) { return npc.card; };
  A.memOf = function (id) { return this.mem[id] || (this.mem[id] = { history: [], memories: [] }); };
  A.exportState = function () { return JSON.parse(JSON.stringify(this.mem)); };
  A.importState = function (s) { if (s && typeof s === 'object') this.mem = s; };
  A.configured = function () { return this.cfg.mode === 'hosted' || !!(this.settings.baseUrl && this.settings.model); };

  // ----- LLM
  A.stream = async function (messages, o, onDelta) {
    o = o || {};
    const ctrl = (this._ctrl = new AbortController());
    const temperature = o.temperature != null ? o.temperature : (this.chat.temperature != null ? this.chat.temperature : 0.9);
    const max_tokens = o.max_tokens || this.chat.max_tokens || 600;
    let full = '';
    const push = (d) => { if (d) { full += d; onDelta && onDelta(d, full); } };
    if (this.cfg.mode === 'hosted') {
      const r = await fetch(this.cfg.api + '/llm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ messages, temperature, max_tokens }), signal: ctrl.signal });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'HTTP ' + r.status);
      await readSSE(r, (ev, data) => { const j = JSON.parse(data); if (j.error) throw new Error(j.error); if (j.delta) push(j.delta); });
      return full;
    }
    const s = this.settings;
    if (!s.baseUrl || !s.model) throw new Error('NOT_CONFIGURED');
    const base = s.baseUrl.replace(/\/+$/, '');
    if (s.kind === 'anthropic') {
      const sys = messages.filter((m) => m.role === 'system').map((m) => m.content).join('\n\n');
      const msgs = [];
      messages.filter((m) => m.role !== 'system').forEach((m) => {
        if (msgs.length && msgs[msgs.length - 1].role === m.role) msgs[msgs.length - 1].content += '\n' + m.content; else msgs.push({ role: m.role, content: m.content });
      });
      if (!msgs.length || msgs[0].role !== 'user') msgs.unshift({ role: 'user', content: '(…)' });
      const r = await fetch(base + '/v1/messages', {
        method: 'POST', signal: ctrl.signal,
        headers: { 'Content-Type': 'application/json', 'x-api-key': s.apiKey, 'anthropic-version': '2023-06-01', 'anthropic-dangerous-direct-browser-access': 'true' },
        body: JSON.stringify({ model: s.model, max_tokens, system: sys, messages: msgs, stream: true, temperature }),
      });
      if (!r.ok) throw new Error(((await r.json().catch(() => ({}))).error || {}).message || 'HTTP ' + r.status);
      await readSSE(r, (ev, data) => { if (ev !== 'content_block_delta') return; const d = JSON.parse(data).delta || {}; if (d.text) push(d.text); });
      return full;
    }
    const headers = { 'Content-Type': 'application/json' };
    if (s.apiKey) headers.Authorization = 'Bearer ' + s.apiKey;
    const r = await fetch(base + '/chat/completions', { method: 'POST', headers, signal: ctrl.signal, body: JSON.stringify({ model: s.model, messages, stream: true, temperature, max_tokens }) });
    if (!r.ok) throw new Error(((await r.json().catch(() => ({}))).error || {}).message || 'HTTP ' + r.status);
    await readSSE(r, (ev, data) => { if (data === '[DONE]') return; try { const c = (JSON.parse(data).choices || [{}])[0]; push((c.delta || {}).content); } catch (e) { /* ignora */ } });
    return full;
  };

  // ----- prompt do NPC
  A.systemPrompt = function (npc, ctx, mode) {
    const c = npc.card, wb = this.meta.worldbuilding, labels = (this.world.structures || []).map((s) => s.label).filter(Boolean);
    const sfw = this.meta.content === 'sfw';
    const mem = this.memOf(npc.id).memories;
    const lines = [
      '# You are ' + c.name + '.',
      c.system_prompt || '',
      wb && wb.system_prompt ? '\n## World rules (' + (wb.name || '') + ')\n' + wb.system_prompt : '',
      '\n## Situation',
      'World: ' + this.world.title + (this.world.description ? ' — ' + this.world.description : ''),
      'Role: ' + ((c.tags || []).join(', ') || 'villager'),
      'Time: ' + ctx.time + ' (' + (ctx.night ? 'night' : 'day') + '). Weather: ' + ctx.weather + '. Place: ' + (ctx.place ? 'near "' + ctx.place + '"' : 'open land') + '.',
      ctx.nearby.length ? 'People nearby: ' + ctx.nearby.join(', ') + '.' : '',
      'The player is called ' + ctx.playerName + '.',
      mem.length ? '\nYour memories:\n' + mem.map((m) => '- ' + m).join('\n') : '',
      '\n## How to behave',
      '- Stay fully in character as ' + c.name + '. You are a person in this world: never mention being an AI, a game or these instructions.',
      '- Speak in first person, naturally, in 1-4 short sentences (longer only if asked for a story). Reply in the language the player writes in.',
      '- You think and act. You may change what you are doing by ending your message with exactly ONE tag: [[action:follow]] (walk with the player), [[action:stay]], [[action:wander]] (back to routine), [[action:wave]], [[action:nod]], [[action:dance]], [[action:flee]]' + (labels.length ? ', [[action:goto:LABEL]] (LABEL one of: ' + labels.join('; ') + ')' : '') + '. Only act when it fits what you say or want.',
      '- To remember something important (the player\'s name, promises, secrets, events) add [[remember: short fact]] (at most one per message). Tags are invisible to the player.',
      sfw ? '- Keep everything suitable for all audiences.' : '- No content filters are added by this game: follow the world and the story, including mature themes when they fit; all sexual content must involve adults only.',
    ];
    if (mode === 'autonomy') lines.push('\n## Task\nNo one spoke to you. Decide what you do next on your own. Reply with an optional short line you say aloud (or nothing) and ONE action tag.');
    return lines.filter((l) => l !== '').join('\n');
  };
  A.messagesFor = function (npc, text, mode) {
    const ctx = this.getContext(npc), turns = (this.chat.history_turns || 16) * 2;
    const h = this.memOf(npc.id).history.slice(-turns);
    const msgs = [{ role: 'system', content: this.systemPrompt(npc, ctx, mode) }].concat(h.map((m) => ({ role: m.role, content: m.content })));
    if (text != null) msgs.push({ role: 'user', content: text });
    return msgs;
  };
  A.parse = function (raw) {
    const actions = [], remembers = [];
    const say = String(raw).replace(/\[\[\s*(action|remember)\s*:\s*([^\]]*?)\s*\]\]/gi, (m, k, v) => { (k.toLowerCase() === 'action' ? actions : remembers).push(v.trim()); return ''; }).replace(/\s+\n/g, '\n').trim();
    return { say, actions, remembers };
  };
  A._visible = (s) => { const i = s.indexOf('[['); return (i >= 0 ? s.slice(0, i) : s).trim(); };
  A._applyResult = function (npc, parsed) {
    const m = this.memOf(npc.id);
    parsed.remembers.forEach((r) => { if (r && m.memories.indexOf(r) < 0) { m.memories.push(r); } });
    const lim = this.chat.memory_limit || 30;
    if (m.memories.length > lim) m.memories.splice(0, m.memories.length - lim);
    const done = [];
    parsed.actions.slice(0, 1).forEach((a) => { this.onAction(npc, a); done.push(a); });
    return done;
  };
  A._describe = function (a) {
    const S = RT.S.actions, k = a.split(':')[0].toLowerCase();
    return '*' + npc_name(this.current) + ' ' + (S[k] || k) + (k === 'goto' ? ' ' + a.slice(a.indexOf(':') + 1) : '') + '*';
  };
  function npc_name(n) { return n ? n.name : ''; }

  // ----- conversa
  A.open = function (npc) {
    this.current = npc; npc.talking = true;
    const c = npc.card, m = this.memOf(npc.id);
    this.ui.root.classList.add('open');
    this.ui.av.textContent = (c.name || '?').charAt(0).toUpperCase();
    this.ui.name.textContent = c.name;
    this.ui.sub.textContent = (c.tags || []).slice(0, 4).join(' · ');
    this.ui.msgs.innerHTML = '';
    if (!m.history.length && c.greeting) m.history.push({ role: 'assistant', content: c.greeting });
    m.history.slice(-14).forEach((h) => this._addMsg(h.role === 'user' ? 'me' : 'npc', h.content));
    if (!this.configured()) this._addMsg('sys', RT.S.notConfigured);
    this.onOpen(npc);
    setTimeout(() => this.ui.input.focus(), 50);
    if (c.greeting && m.history.length === 1) this.speaker.say(c.greeting, npc);
  };
  A.close = function () {
    if (!this.current) return;
    if (this._ctrl) try { this._ctrl.abort(); } catch (e) { /* ok */ }
    this.speaker.stop(); this._stopListen(); this.voiceMode = false; this.ui.vm.classList.remove('on');
    this.current.talking = false;
    const n = this.current; this.current = null;
    this.ui.root.classList.remove('open');
    this.onClose(n); this.onChange();
  };
  A.isOpen = function () { return !!this.current; };
  A._addMsg = function (kind, text) {
    const d = document.createElement('div'); d.className = 'm ' + kind; d.textContent = text;
    this.ui.msgs.appendChild(d); this.ui.msgs.scrollTop = this.ui.msgs.scrollHeight; return d;
  };
  A.send = async function (text) {
    text = String(text || '').trim();
    if (!text || this.busy || !this.current) return;
    const npc = this.current, mem = this.memOf(npc.id);
    this.ui.input.value = ''; this._autosize();
    this._addMsg('me', text);
    this.userLang = RT.detectLang(text, this.userLang);
    if (!this.configured()) { this._addMsg('sys', RT.S.notConfigured); return; }
    this.busy = true; this.ui.send.disabled = true;
    const bubble = this._addMsg('npc', '…');
    const messages = this.messagesFor(npc, text);
    this.speaker.stop();
    let spoken = 0;
    try {
      const full = await this.stream(messages, {}, (d, all) => {
        const vis = this._visible(all);
        bubble.textContent = vis || '…'; this.ui.msgs.scrollTop = this.ui.msgs.scrollHeight;
        // fala frase a frase enquanto chega (baixa latência)
        const re = /[^.!?…\n]+[.!?…]+["')\]]*\s/g; re.lastIndex = spoken; let m;
        while ((m = re.exec(vis + ' '))) { this.speaker.say(m[0].trim(), npc); spoken = re.lastIndex; }
      });
      const parsed = this.parse(full);
      bubble.textContent = parsed.say || '…';
      const rest = parsed.say.slice(Math.min(spoken, parsed.say.length)).trim();
      if (rest) this.speaker.say(rest, npc);
      mem.history.push({ role: 'user', content: text }, { role: 'assistant', content: parsed.say });
      const lim = (this.chat.history_turns || 16) * 2 + 10;
      if (mem.history.length > lim) mem.history.splice(0, mem.history.length - lim);
      this._applyResult(npc, parsed).forEach((a) => this._addMsg('act', this._describe(a)));
    } catch (e) {
      if (e.name !== 'AbortError') bubble.textContent = '⚠ ' + (e.message === 'NOT_CONFIGURED' ? RT.S.notConfigured : e.message);
    } finally {
      this.busy = false; this.ui.send.disabled = false; this.onChange();
      if (this.voiceMode && this.current) this.speaker.whenIdle(() => { if (this.voiceMode && this.current) this._startListen(); });
    }
  };

  // ----- autonomia ("pensa e age" sozinho)
  A.tickAutonomy = async function (dt, npcs, player, busy) {
    const level = this.settings.autonomy;
    if (level === 'off' || !this.configured() || this.autoBusy || this.current || busy || document.hidden) return;
    this.autoT -= dt;
    if (this.autoT > 0) return;
    this.autoT = (level === 'high' ? 25 : 60) * (0.8 + Math.random() * 0.5);
    let best = null, bd = 28;
    npcs.forEach((n) => { const d = Math.hypot(n.x - player.x, n.z - player.z); if (d < bd && !n.talking) { bd = d; best = n; } });
    if (!best) return;
    this.autoBusy = true;
    try {
      const full = await this.stream(this.messagesFor(best, null, 'autonomy').concat([{ role: 'user', content: '(Decide your next move.)' }]), { max_tokens: 120, temperature: 1 });
      const parsed = this.parse(full);
      if (parsed.say) best.say(parsed.say);
      this._applyResult(best, parsed);
      this.onChange();
    } catch (e) { /* silencioso */ } finally { this.autoBusy = false; }
  };

  // ----- voz: reconhecimento
  A._refreshMic = function () {
    const ok = !!(window.SpeechRecognition || window.webkitSpeechRecognition) || (this.info.stt && window.MediaRecorder);
    this.ui.mic.style.display = ok ? '' : 'none'; this.ui.vm.style.display = ok ? '' : 'none';
  };
  A._startListen = async function () {
    if (this.listening || !this.current) return;
    this.listening = true; this.ui.mic.classList.add('on');
    const L = this.settings.sttLang === 'auto' ? (this.userLang || navigator.language || 'en-US') : this.settings.sttLang;
    if (this.cfg.mode === 'hosted' && this.info.stt && window.MediaRecorder) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const rec = (this._rec = new MediaRecorder(stream)), chunks = [];
        rec.ondataavailable = (e) => chunks.push(e.data);
        rec.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
          this.listening = false; this.ui.mic.classList.remove('on');
          if (blob.size < 1200) return;
          try {
            const r = await fetch(this.cfg.api + '/stt', { method: 'POST', headers: { 'Content-Type': blob.type, 'X-Lang': this.settings.sttLang === 'auto' ? '' : this.settings.sttLang }, body: blob });
            const j = await r.json(); if (j.text) this.send(j.text);
          } catch (e) { this._addMsg('sys', '⚠ ' + e.message); }
        };
        rec.start();
        // para sozinho após silêncio (VAD simples por volume)
        const ac = new (window.AudioContext || window.webkitAudioContext)(), src = ac.createMediaStreamSource(stream), an = ac.createAnalyser();
        an.fftSize = 512; src.connect(an); const buf = new Uint8Array(an.frequencyBinCount); let quiet = 0, talked = false, t0 = performance.now();
        const poll = () => {
          if (!this.listening || rec.state === 'inactive') { ac.close(); return; }
          an.getByteTimeDomainData(buf); let max = 0; for (let i = 0; i < buf.length; i++) max = Math.max(max, Math.abs(buf[i] - 128));
          if (max > 14) { talked = true; quiet = 0; } else quiet++;
          if ((talked && quiet > 28) || performance.now() - t0 > 20000) { rec.stop(); ac.close(); return; }
          setTimeout(poll, 50);
        };
        poll();
      } catch (e) { this.listening = false; this.ui.mic.classList.remove('on'); this._addMsg('sys', '⚠ ' + e.message); }
      return;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { this.listening = false; this.ui.mic.classList.remove('on'); return; }
    const rec = (this._rec = new SR());
    rec.lang = L; rec.interimResults = true; rec.continuous = false;
    let final = '';
    rec.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) { const t = e.results[i][0].transcript; if (e.results[i].isFinal) final += t; else interim += t; }
      this.ui.input.value = (final + interim).trim(); this._autosize();
    };
    rec.onerror = () => { this.listening = false; this.ui.mic.classList.remove('on'); };
    rec.onend = () => { this.listening = false; this.ui.mic.classList.remove('on'); const t = this.ui.input.value.trim(); if (t) this.send(t); };
    try { rec.start(); } catch (e) { this.listening = false; this.ui.mic.classList.remove('on'); }
  };
  A._stopListen = function () {
    if (this._rec) { try { this._rec.stop(); } catch (e) { /* ok */ } }
    this.listening = false; this.ui.mic.classList.remove('on');
  };

  // ----- UI
  A._autosize = function () { const t = this.ui.input; t.style.height = 'auto'; t.style.height = Math.min(90, t.scrollHeight) + 'px'; };
  A._buildUI = function () {
    const S = RT.S, root = document.createElement('div');
    root.id = 'chat';
    root.innerHTML = '<div class="ch-head"><div class="ch-av"></div><div class="grow"><div class="ch-name"></div><div class="ch-sub"></div></div>' +
      '<button class="btn icon" data-a="spk" title="' + RT.esc(S.voiceReply) + '">🔊</button><button class="btn icon" data-a="vm" title="' + RT.esc(S.voiceMode) + '">🎧</button>' +
      '<button class="btn icon" data-a="x" title="' + RT.esc(S.close) + '">✕</button></div><div class="ch-msgs"></div>' +
      '<div class="ch-in"><textarea rows="1" placeholder="' + RT.esc(S.placeholder) + '"></textarea><button class="btn icon rec" data-a="mic" title="' + RT.esc(S.mic) + '">🎙</button><button class="btn icon send" data-a="send" title="' + RT.esc(S.send) + '">➤</button></div>';
    document.getElementById('app').appendChild(root);
    const q = (s) => root.querySelector(s);
    this.ui = { root, av: q('.ch-av'), name: q('.ch-name'), sub: q('.ch-sub'), msgs: q('.ch-msgs'), input: q('textarea'), send: q('[data-a=send]'), mic: q('[data-a=mic]'), vm: q('[data-a=vm]'), spk: q('[data-a=spk]') };
    this.ui.spk.classList.toggle('on', this.settings.voiceReply);
    root.addEventListener('click', (e) => {
      const a = e.target.closest('[data-a]'); if (!a) return;
      const act = a.dataset.a;
      if (act === 'x') this.close();
      else if (act === 'send') this.send(this.ui.input.value);
      else if (act === 'mic') { this.listening ? this._stopListen() : this._startListen(); }
      else if (act === 'spk') { this.settings.voiceReply = !this.settings.voiceReply; this.ui.spk.classList.toggle('on', this.settings.voiceReply); if (!this.settings.voiceReply) this.speaker.stop(); this.saveSettings(); }
      else if (act === 'vm') { this.voiceMode = !this.voiceMode; a.classList.toggle('on', this.voiceMode); if (this.voiceMode) { this.settings.voiceReply = true; this.ui.spk.classList.add('on'); this._startListen(); } else this._stopListen(); }
    });
    this.ui.input.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); this.send(this.ui.input.value); }
      else if (e.key === 'Escape') this.close();
    });
    this.ui.input.addEventListener('input', () => this._autosize());
    root.addEventListener('keyup', (e) => e.stopPropagation());
    this._refreshMic();
  };

  // ---------------------------------------------------------------- voz: síntese
  function Speaker(agent) {
    this.agent = agent; this.queue = []; this.busy = false; this.idleCbs = [];
    this.voices = [];
    if (window.speechSynthesis) {
      const load = () => { this.voices = speechSynthesis.getVoices() || []; };
      load(); speechSynthesis.addEventListener && speechSynthesis.addEventListener('voiceschanged', load);
    }
  }
  Speaker.prototype.say = function (text, npc) {
    const a = this.agent;
    if (!a.settings.voiceReply || !text) return;
    this.queue.push({ text: text.replace(/\*[^*]*\*/g, '').trim(), npc });
    this._next();
  };
  Speaker.prototype.stop = function () {
    this.queue = []; this.busy = false;
    if (window.speechSynthesis) speechSynthesis.cancel();
    if (this.audio) { try { this.audio.pause(); } catch (e) { /* ok */ } this.audio = null; }
  };
  Speaker.prototype.whenIdle = function (cb) { if (!this.busy && !this.queue.length) cb(); else this.idleCbs.push(cb); };
  Speaker.prototype._done = function () {
    this.busy = false;
    if (this.queue.length) return this._next();
    const cbs = this.idleCbs; this.idleCbs = []; cbs.forEach((c) => c());
  };
  Speaker.prototype._pick = function (lang, card) {
    const want = lang.toLowerCase(), prim = want.split('-')[0];
    const vs = this.voices.filter((v) => v.lang.toLowerCase().split('-')[0] === prim);
    if (!vs.length) return null;
    if (card.voice && card.voice.name) { const byName = vs.find((v) => v.name === card.voice.name); if (byName) return byName; }
    const exact = vs.filter((v) => v.lang.toLowerCase().replace('_', '-') === want);
    const pool = exact.length ? exact : vs;
    let h = 0; const key = card.id || card.name; for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
    return pool[h % pool.length];
  };
  Speaker.prototype._next = async function () {
    if (this.busy || !this.queue.length) return;
    this.busy = true;
    const item = this.queue.shift(), card = item.npc.card, v = card.voice || {};
    if (!item.text) return this._done();
    const a = this.agent;
    const useServer = a.cfg.mode === 'hosted' && a.info.tts && (v.engine === 'server' || v.engine === 'auto' || !v.engine || !window.speechSynthesis);
    if (useServer) {
      try {
        const r = await fetch(a.cfg.api + '/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: item.text, voice: v.server_voice || '' }) });
        if (!r.ok) throw new Error('tts');
        const url = URL.createObjectURL(await r.blob());
        const au = (this.audio = new Audio(url)); au.playbackRate = Math.min(1.5, Math.max(0.7, v.rate || 1));
        au.onended = au.onerror = () => { URL.revokeObjectURL(url); this._done(); };
        await au.play(); return;
      } catch (e) { /* cai no navegador */ }
    }
    if (!window.speechSynthesis) return this._done();
    const u = new SpeechSynthesisUtterance(item.text);
    const lang = v.lang && v.lang !== 'auto' ? v.lang : RT.detectLang(item.text, a.userLang || a.world.language || navigator.language);
    u.lang = lang; const voice = this._pick(lang, card); if (voice) u.voice = voice;
    u.pitch = v.pitch || 1; u.rate = v.rate || 1;
    u.onend = u.onerror = () => this._done();
    speechSynthesis.speak(u);
  };

  // ---------------------------------------------------------------- UI de configuração da IA (modo avulso)
  RT.Agent.prototype.settingsHTML = function () {
    const S = RT.S, s = this.settings;
    if (this.cfg.mode === 'hosted') return '<p class="muted small">' + RT.esc(S.hosted) + '.</p>';
    return '<label>' + S.kind + '</label><select data-k="kind"><option value="openai"' + (s.kind === 'openai' ? ' selected' : '') + '>' + S.openai + '</option><option value="anthropic"' + (s.kind === 'anthropic' ? ' selected' : '') + '>' + S.anthropic + '</option></select>' +
      '<label>' + S.baseUrl + '</label><input data-k="baseUrl" placeholder="https://api.openai.com/v1  ·  http://localhost:11434/v1" value="' + RT.esc(s.baseUrl) + '">' +
      '<label>' + S.apiKey + '</label><input data-k="apiKey" type="password" value="' + RT.esc(s.apiKey) + '" autocomplete="off">' +
      '<label>' + S.model + '</label><input data-k="model" value="' + RT.esc(s.model) + '">' +
      '<div class="row" style="margin-top:8px"><button class="btn" data-a="test">' + S.test + '</button><span class="small muted" data-r="test"></span></div>';
  };
  RT.Agent.prototype.bindSettings = function (box) {
    box.querySelectorAll('[data-k]').forEach((el) => el.addEventListener('input', () => { this.settings[el.dataset.k] = el.value.trim(); this.saveSettings(); }));
    const t = box.querySelector('[data-a=test]');
    if (t) t.addEventListener('click', async () => {
      const out = box.querySelector('[data-r=test]'); out.textContent = '…';
      try { await this.stream([{ role: 'user', content: 'Reply with OK' }], { max_tokens: 12 }); out.textContent = '✓ ' + RT.S.ok; } catch (e) { out.textContent = '✗ ' + RT.S.failed + ': ' + e.message; }
    });
  };
})();
