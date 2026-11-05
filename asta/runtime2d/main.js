/* ASTA runtime 2D — inicialização: tela inicial, motor do gênero, ponteiro, controles de toque, mudo e tela cheia. */
(function () {
  'use strict';
  const G2 = window.G2, spec = window.ASTA_GAME, cfg = window.ASTA_CONFIG || { mode: 'standalone' };
  if (!G2 || !spec) { document.body.textContent = 'Jogo não carregado.'; return; }
  G2.setLang(spec.language); G2.sfxOn = spec.audio && spec.audio.sfx !== false;
  document.title = spec.title;
  const $ = (id) => document.getElementById(id);
  const th = G2.theme(spec.style.theme);
  document.body.style.background = th.bg;
  $('s-title').textContent = spec.title; $('s-desc').textContent = spec.description || '';
  const HELP = {
    visual_novel: G2.t('Clique ou Espaço avança · A auto · Ctrl pula · H histórico · S/L salvar/carregar', 'Click or Space advances · A auto · Ctrl skip · H log · S/L save/load'),
    rpg: G2.t('Setas/WASD movem · Espaço interage · Esc menu', 'Arrows/WASD move · Space interacts · Esc menu'),
    platformer: G2.t('Setas/A-D movem · Espaço/W pula · R reinicia a fase', 'Arrows/A-D move · Space/W jump · R restart level'),
    side_scroller: spec.data.mode === 'runner' ? G2.t('Espaço/↑ pula · ↓ desliza', 'Space/Up jumps · Down slides') : G2.t('Setas/WASD movem · Espaço atira', 'Arrows/WASD move · Space shoots'),
    point_and_click: G2.t('Clique nos objetos · clique num item do inventário e depois num objeto para usá-lo', 'Click objects · click an inventory item, then an object, to use it'),
  };
  $('s-help').textContent = HELP[spec.genre] || '';
  $('s-play').textContent = G2.t('Jogar', 'Play'); $('s-play').disabled = false;

  let game = null, stopLoop = null;
  const canvas = $('view');

  async function start() {
    G2.audio.unlock(); await G2.save.init(cfg);
    const factory = G2.engines[spec.genre];
    if (!factory) { $('s-status').textContent = 'Motor ausente: ' + spec.genre; return; }
    game = factory(spec); G2.screen.setup(canvas, game.W, game.H);
    $('start').classList.add('hidden'); $('g2-bar').classList.remove('hidden');
    const pos = (e) => G2.screen.toLogical(e.clientX, e.clientY);
    canvas.addEventListener('pointerdown', (e) => { G2.audio.unlock(); const p = pos(e); game.pointer('down', p.x, p.y, e.button); });
    canvas.addEventListener('pointermove', (e) => { const p = pos(e); game.pointer('move', p.x, p.y, e.button); });
    canvas.addEventListener('pointerup', (e) => { const p = pos(e); game.pointer('up', p.x, p.y, e.button); });
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    setupTouch();
    game.begin();
    stopLoop = G2.loop((dt) => game.update(dt), () => game.render());
    window.__game = game; // usado pelos testes automatizados
  }

  function setupTouch() {
    const touch = ('ontouchstart' in window) || navigator.maxTouchPoints > 0; if (!touch) return;
    const mode = spec.genre === 'side_scroller' ? (spec.data.mode === 'runner' ? 'runner' : 'shooter') : spec.genre;
    const layouts = {
      rpg: { dpad: true, buttons: [['action', 'A'], ['cancel', 'B']] }, platformer: { lr: true, buttons: [['jump', '⤒']] }, shooter: { dpad: true, buttons: [['fire', '●']] },
      runner: { buttons: [['jump', '⤒'], ['down', '⤓']] },
    };
    const L = layouts[mode]; if (!L) return;
    const root = $('g2-touch'); root.classList.remove('hidden'); root.replaceChildren();
    const mk = (cls, label, action) => { const b = document.createElement('button'); b.className = 'g2-tb ' + cls; b.textContent = label; const on = (v) => (e) => { e.preventDefault(); G2.input.virtual(action, v); b.classList.toggle('on', v); }; b.addEventListener('pointerdown', on(true)); ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) => b.addEventListener(ev, on(false))); return b; };
    const pad = document.createElement('div'); pad.className = 'g2-pad';
    if (L.dpad) { pad.append(mk('u', '▲', 'up'), mk('l', '◀', 'left'), mk('r', '▶', 'right'), mk('d', '▼', 'down')); } else if (L.lr) { pad.append(mk('l', '◀', 'left'), mk('r', '▶', 'right')); pad.classList.add('lr'); }
    const acts = document.createElement('div'); acts.className = 'g2-acts'; L.buttons.forEach(([a, l]) => acts.append(mk('a', l, a)));
    root.append(pad, acts);
  }

  $('s-play').addEventListener('click', start);
  addEventListener('keydown', (e) => { if (!game && (e.code === 'Enter' || e.code === 'Space') && !$('start').classList.contains('hidden')) { e.preventDefault(); start(); } });
  $('b-mute').addEventListener('click', () => { G2.audio.setMuted(!G2.audio.muted); $('b-mute').textContent = G2.audio.muted ? '🔇' : '🔊'; if (!G2.audio.muted && game && game.state) { /* a música volta no próximo evento do jogo */ } });
  $('b-full').addEventListener('click', () => { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen && document.documentElement.requestFullscreen(); });
  $('b-reset').addEventListener('click', () => { if (confirm(G2.t('Apagar o progresso salvo e recomeçar?', 'Erase saved progress and restart?'))) { G2.save.clear(); location.reload(); } });
  $('b-mute').title = G2.t('Som', 'Sound'); $('b-full').title = G2.t('Tela cheia', 'Fullscreen'); $('b-reset').title = G2.t('Apagar progresso', 'Erase progress');
  addEventListener('pagehide', () => { if (game && game.getSave && spec.genre === 'visual_novel') { try { G2.save.set('vn_auto', Object.assign({ t: Date.now() }, game.getSave())); } catch (e) { /* ok */ } } });
})();
