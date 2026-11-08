// App mobile (PWA): instalar na tela inicial, avisar de versão nova (perguntando «atualizar agora?») e adaptar-se ao aparelho. Vale para Wi-Fi e dados móveis:
// a checagem é só uma chamada pequena (GET /api/version) ao ASTA do computador, feita ao abrir, ao voltar ao app, ao recuperar a conexão e a cada 5 minutos.
import { t } from './i18n.js';
import { h, modal, toast } from './ui.js';

const dev = () => window.ASTA_DEVICE || { device: 'desktop' };
export const inApp = () => /ASTA-Android/.test(navigator.userAgent || '');   // o app Android (APK): o ASTA roda dentro do aparelho ou numa conexão com um computador
const REPO = 'KMC1525/ASTA';
export const isMobile = () => dev().device !== 'desktop';
let reg = null, asking = false;
const declined = new Set();

async function applyUpdate() {
  try {
    if (reg && reg.waiting) {
      reg.waiting.postMessage({ type: 'SKIP_WAITING' });
      await new Promise((ok) => { navigator.serviceWorker.addEventListener('controllerchange', ok, { once: true }); setTimeout(ok, 2500); });
    }
    if (window.caches) for (const k of await caches.keys()) if (k.startsWith('asta-shell-')) await caches.delete(k);
  } catch (e) { /* recarregar resolve */ }
  location.reload();
}

// Pergunta uma vez por versão e por sessão; «Depois» volta a perguntar na próxima vez que o app abrir.
export async function offerUpdate(version) {
  if (asking || declined.has(version || '?')) return;
  asking = true;
  try {
    const yes = await modal(t('Atualização do ASTA'),
      h('p', { class: 'muted', style: { margin: 0 } }, version ? t('Há uma versão nova do ASTA ({v}). Quer atualizar agora?', { v: version }) : t('Há uma versão nova do ASTA. Quer atualizar agora?')),
      [{ label: t('Depois'), value: false }, { label: t('Atualizar agora'), value: true, cls: 'primary' }]);
    if (yes === true) await applyUpdate(); else declined.add(version || '?');
  } finally { asking = false; }
}

// App Android: o ASTA do aparelho é o do próprio APK, então a atualização é um APK novo nas Releases do repositório (pergunta «Baixar agora» ou «Depois»)
async function checkApk() {
  try {
    const mine = (await (await fetch('/api/version', { cache: 'no-store' })).json()).version;
    const r = await fetch('https://api.github.com/repos/' + REPO + '/releases/latest', { headers: { Accept: 'application/vnd.github+json' } });
    if (!r.ok) return;
    const rel = await r.json(), v = String(rel.tag_name || '').replace(/^v/, ''), n = (s) => String(s).split('.').map((x) => parseInt(x, 10) || 0);
    const a = n(v), b = n(mine);
    let newer = false;
    for (let i = 0; i < 3; i++) if ((a[i] || 0) !== (b[i] || 0)) { newer = (a[i] || 0) > (b[i] || 0); break; }
    if (!newer || declined.has('apk-' + v)) return;
    const apk = (rel.assets || []).find((x) => /\.apk$/i.test(x.name));
    const yes = await modal(t('Atualização do app ASTA'), h('p', { class: 'muted', style: { margin: 0 } }, t('Há uma versão nova do app ASTA ({v}). Quer baixar agora?', { v })),
      [{ label: t('Depois'), value: false }, { label: t('Baixar agora'), value: true, cls: 'primary' }]);
    if (yes === true) location.href = apk ? apk.browser_download_url : rel.html_url; else declined.add('apk-' + v);
  } catch (e) { /* sem internet: tudo bem */ }
}

async function checkVersion(loaded) {
  try {
    const r = await fetch('/api/version', { cache: 'no-store' });
    if (!r.ok) return;
    const v = (await r.json()).version;
    if (v && loaded && v !== loaded) offerUpdate(v);
    else if (reg) reg.update().catch(() => {});
  } catch (e) { /* sem conexão com o computador agora: tenta de novo depois */ }
}

// Instalar o app: Android/Chrome oferece o diálogo nativo; no iPhone/iPad é «Compartilhar → Adicionar à Tela de Início»; em outros casos, o menu do navegador.
function installBar() {
  const d = dev();
  let skipped = false;
  try { skipped = localStorage.getItem('asta.install.skip') === '1'; } catch (e) { /* tudo bem */ }
  if (d.device === 'desktop' || d.standalone || skipped) return;
  let prompt = null;
  const bar = h('div', { class: 'install-bar', role: 'region', 'aria-label': t('Instalar o app') });
  const close = () => { bar.remove(); try { localStorage.setItem('asta.install.skip', '1'); } catch (e) { /* tudo bem */ } };
  const paint = () => {
    const how = prompt ? t('Instale o ASTA como app na tela inicial.')
      : d.platform === 'ios' ? t('Para instalar: toque em Compartilhar e depois em «Adicionar à Tela de Início».')
        : t('Para instalar: abra o menu do navegador e toque em «Instalar app» ou «Adicionar à tela inicial».');
    bar.replaceChildren(h('span', { class: 'grow' }, how),
      prompt ? h('button', { class: 'btn sm primary', type: 'button', onclick: async () => { prompt.prompt(); try { await prompt.userChoice; } catch (e) { /* ok */ } prompt = null; close(); } }, t('Instalar')) : null,
      h('button', { class: 'btn sm ghost', type: 'button', 'aria-label': t('Fechar'), onclick: close }, '✕'));
  };
  window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); prompt = e; paint(); });
  window.addEventListener('appinstalled', () => bar.remove());
  paint();
  document.body.appendChild(bar);
}

export function initMobile(loadedVersion) {
  const secure = location.protocol === 'https:' || ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  if ('serviceWorker' in navigator && secure) {   // o navegador só permite service worker em HTTPS/localhost; sem ele o resto (aviso de versão por consulta) continua valendo
    navigator.serviceWorker.register('/sw.js').then((r) => {
      reg = r;
      const watch = (w) => w && w.addEventListener('statechange', () => { if (w.state === 'installed' && navigator.serviceWorker.controller) checkVersion(loadedVersion).then(() => offerUpdate('')); });
      if (r.waiting && navigator.serviceWorker.controller) offerUpdate('');
      r.addEventListener('updatefound', () => watch(r.installing));
    }).catch(() => { /* sem service worker: tudo bem */ });
  }
  if (!isMobile()) return;
  if (inApp()) { setTimeout(checkApk, 6000); document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') setTimeout(checkApk, 1500); }); }
  else installBar();   // dentro do APK não faz sentido «instalar o app»
  const tick = () => checkVersion(loadedVersion);
  setInterval(tick, 5 * 60 * 1000);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') tick(); });
  window.addEventListener('online', tick);
  setTimeout(tick, 4000);
}
export { toast };
