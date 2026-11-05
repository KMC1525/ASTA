// Aplica a aparência escolhida ANTES da primeira pintura (script clássico no <head>): sem piscar de escuro para claro ao abrir.
// O valor vem do cache local da última sessão; depois o servidor (settings.ui) confirma e corrige (ver prefs.js).
(function () {
  var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
  function lum(hex) {
    var n = parseInt(hex.slice(1), 16), c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  window.ASTA_APPLY_UI = function (ui) {
    ui = ui || {};
    var r = document.documentElement, theme = ui.theme === 'light' || ui.theme === 'auto' ? ui.theme : 'dark';
    var resolved = theme === 'auto' ? (mq && mq.matches ? 'light' : 'dark') : theme;
    r.dataset.theme = resolved;
    r.dataset.density = ui.density === 'compact' ? 'compact' : 'comfortable';
    r.dataset.motion = ui.motion === 'reduce' || ui.motion === 'full' ? ui.motion : 'auto';
    r.dataset.font = ui.font === 'serif' || ui.font === 'mono' ? ui.font : 'system';
    r.dataset.chat = ui.chat_size === 'small' || ui.chat_size === 'large' ? ui.chat_size : 'medium';
    var scale = [90, 100, 110, 125, 150].indexOf(Number(ui.scale)) >= 0 ? Number(ui.scale) : 100;
    var zoomOk = !window.CSS || !CSS.supports || CSS.supports('zoom', '1.1');
    r.style.setProperty('--z', zoomOk ? String(scale / 100) : '1');
    var accent = /^#[0-9a-f]{6}$/i.test(ui.accent || '') ? ui.accent.toLowerCase() : '';
    if (accent) { r.style.setProperty('--accent-custom', accent); r.style.setProperty('--on-accent-custom', lum(accent) > 0.4 ? '#000' : '#fff'); }
    else { r.style.removeProperty('--accent-custom'); r.style.removeProperty('--on-accent-custom'); }
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', resolved === 'light' ? '#f6f6f4' : '#000000');
    var cs = document.querySelector('meta[name="color-scheme"]');
    if (cs) cs.setAttribute('content', resolved);
    try { localStorage.setItem('asta.ui', JSON.stringify(ui)); } catch (e) { /* navegação privada: tudo bem, o servidor confirma */ }
    window.ASTA_UI = ui;
  };
  var cached = null;
  try { cached = JSON.parse(localStorage.getItem('asta.ui') || 'null'); } catch (e) { /* ignora */ }
  window.ASTA_APPLY_UI(cached || {});
  if (mq && mq.addEventListener) mq.addEventListener('change', function () { if ((window.ASTA_UI || {}).theme === 'auto') window.ASTA_APPLY_UI(window.ASTA_UI); });
})();
