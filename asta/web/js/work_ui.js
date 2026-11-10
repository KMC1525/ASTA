// Peças compartilhadas do Work: vocabulário (estados, prioridades), pessoas (avatar, presença), formatos, permissões e a assinatura dos eventos ao vivo (SSE, uma só conexão).
import { api } from './api.js';
import { t } from './i18n.js';
import { h, icon, toast } from './ui.js';

// ------------------------------------------------------------------ vocabulário (funções: o idioma pode mudar depois do carregamento)
export const PRIORITY = () => ({ low: t('Baixa'), normal: t('Normal'), high: t('Alta'), urgent: t('Urgente') });
export const REQ_STATUS = () => ({ sent: t('Enviado'), seen: t('Visto'), accepted: t('Aceito'), in_progress: t('Em andamento'), done: t('Concluído'), rejected: t('Recusado'), cancelled: t('Cancelado') });
export const ACT_STATE = () => ({ started: t('Começou'), continuing: t('Continuando'), paused: t('Pausada'), finished: t('Finalizada'), cancelled: t('Cancelada') });
export const NODE_KIND = () => ({ person: t('Pessoa'), role: t('Cargo'), sector: t('Setor'), note: t('Nota'), ai: t('Agente de IA') });
export const EDGE_KIND = () => ({ reports: t('Reporta a'), handoff: t('Repassa para'), approval: t('Aprova') });
export const AUTH_MODE = () => ({ none: t('Sem senha'), local: t('Só nesta máquina'), machine: t('Guardada em outra máquina'), synced: t('Em todas as máquinas da rede') });
export const statusTone = (s) => ({ done: 'ok', finished: 'ok', rejected: 'err', cancelled: 'dim', in_progress: 'info', continuing: 'info', started: 'info', accepted: 'info', paused: 'warn', seen: 'dim', sent: 'warn' }[s] || 'dim');
export const prioTone = (p) => ({ urgent: 'err', high: 'warn', low: 'dim' }[p] || 'dim');
export const chip = (label, tone = 'dim', title) => h('span', { class: 'cu-st wk-chip ' + tone, title: title || null }, label);

// ------------------------------------------------------------------ formatos
export const fmtAgo = (ts) => {
  const s = Math.max(0, Date.now() / 1000 - (ts || 0));
  if (!ts) return '';
  if (s < 60) return t('agora');
  if (s < 3600) return t('há {n} min', { n: Math.floor(s / 60) });
  if (s < 86400) return t('há {n} h', { n: Math.floor(s / 3600) });
  return t('há {n} d', { n: Math.floor(s / 86400) });
};
export const fmtWhen = (ts) => { try { return new Date(ts * 1000).toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; } };
export function fmtElapsed(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = sec % 60;
  return (hh ? hh + ':' + String(mm).padStart(2, '0') : String(mm)) + ':' + String(ss).padStart(2, '0');
}
export const fmtSize = (n) => { n = n || 0; if (n < 1024) return n + ' B'; const u = ['KB', 'MB', 'GB', 'TB']; let i = -1; do { n /= 1024; i++; } while (n >= 1024 && i < 3); return n.toFixed(n < 10 ? 1 : 0) + ' ' + u[i]; };

// ------------------------------------------------------------------ pessoas
export function avatarEl(u, size = 36) {
  const el = h('span', { class: 'wk-av' + (u && u.online ? ' online' : ''), style: { width: size + 'px', height: size + 'px', fontSize: Math.round(size * 0.42) + 'px', background: (u && u.avatar_color) || '#3e9bff' }, title: u ? (u.display_name || u.username) : '' },
    String((u && (u.display_name || u.username)) || '?').trim().charAt(0).toUpperCase());
  return el;
}
export const userName = (dir, id) => { const u = (dir.users || []).find((x) => x.id === id); return u ? (u.display_name || u.username) : t('(removido)'); };
export const roleOf = (dir, u) => (dir.roles || []).find((r) => r.id === u.role_id) || { name: '' };
export const can = (me, perm) => !!me && (me.perms.includes('*') || me.perms.includes(perm));

// ------------------------------------------------------------------ eventos ao vivo (uma só conexão para a página toda)
let es = null;
const subs = new Set();
let last = { unread: 0, on: false };
export const workStatus = () => last;
export function subscribe(fn) { subs.add(fn); return () => subs.delete(fn); }
export function startEvents() {
  if (es || typeof EventSource === 'undefined') return;
  es = new EventSource('/api/work/events');
  es.onmessage = (m) => {
    let ev; try { ev = JSON.parse(m.data); } catch (e) { return; }
    if (ev.type === 'hello') last = { unread: ev.unread || 0, on: true };
    if (ev.type === 'unread') {
      const more = ev.n > last.unread;
      last = { unread: ev.n, on: true };
      if (more) announce();
    }
    if (ev.type === 'logout') { stopEvents(); }
    subs.forEach((f) => { try { f(ev); } catch (e) { console.error(e); } });
  };
}
export function stopEvents() {
  if (es) { es.close(); es = null; }
  last = { unread: 0, on: false };
  subs.forEach((f) => { try { f({ type: 'stopped' }); } catch (e) { /* ok */ } });
}

// A notificação mais nova vira um aviso na tela e, se a pessoa ligou, uma notificação do sistema.
async function announce() {
  try {
    const r = await api('/api/work/notifications?unread=1');
    const n = r.items[0];
    if (!n) return;
    toast('🔔 ' + n.title + (n.body ? ' — ' + n.body : ''), 'ok');
    let on = false; try { on = localStorage.getItem('asta.work.desktop') === '1'; } catch (e) { /* ok */ }
    if (on && typeof Notification !== 'undefined' && Notification.permission === 'granted' && document.hidden) new Notification(n.title, { body: n.body || '' });
  } catch (e) { /* sem sessão: nada a anunciar */ }
}
export async function askDesktop() {
  if (typeof Notification === 'undefined') { toast(t('Este navegador não tem notificações do sistema.'), 'err'); return false; }
  const p = Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission();
  try { localStorage.setItem('asta.work.desktop', p === 'granted' ? '1' : '0'); } catch (e) { /* ok */ }
  if (p === 'granted') toast(t('Notificações do sistema ligadas.'), 'ok'); else toast(t('O navegador não permitiu as notificações.'), 'err');
  return p === 'granted';
}

// rótulo + ícone pequeno para listas
export const row = (ic, ...kids) => h('span', { class: 'row', style: { gap: '6px', alignItems: 'center' } }, icon(ic, 14), ...kids);

// Diálogo que o próprio conteúdo fecha (o `modal()` do ASTA só fecha pelos botões do rodapé): `const d = dialog(título, corpo); … d.close(valor); await d.done`.
export function dialog(title, body, wide = false) {
  let resolve;
  const done = new Promise((r) => { resolve = r; });
  const back = document.activeElement;
  const close = (v) => { bg.remove(); document.removeEventListener('keydown', onKey); if (back && back.focus && document.contains(back)) { try { back.focus(); } catch (e) { /* ok */ } } resolve(v === undefined ? null : v); };
  const onKey = (e) => { if (e.key === 'Escape') close(null); };
  const bg = h('div', { class: 'modal-bg', onmousedown: (e) => { if (e.target === bg) close(null); } },
    h('div', { class: 'modal' + (wide ? ' wk-wide' : ''), role: 'dialog', 'aria-modal': 'true', 'aria-label': String(title) }, h('h2', null, title), body));
  document.body.appendChild(bg);
  document.addEventListener('keydown', onKey);
  return { close, done, el: bg };
}

// Envia um arquivo (qualquer formato) para o Work; devolve o arquivo criado. `extra`: { folder, request } vão nos cabeçalhos.
export function uploadFile(file, extra = {}, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/work/files');
    xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
    if (extra.folder) xhr.setRequestHeader('X-Folder', encodeURIComponent(extra.folder));
    if (extra.request) xhr.setRequestHeader('X-Request', encodeURIComponent(extra.request));
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
    xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total); };
    xhr.onload = () => { let d = {}; try { d = JSON.parse(xhr.responseText); } catch (e) { /* ok */ } if (xhr.status >= 200 && xhr.status < 300) resolve(d); else reject(new Error(d.error || `Erro ${xhr.status}`)); };
    xhr.onerror = () => reject(new Error(t('Falha no envio do arquivo.')));
    xhr.send(file);
  });
}
export { api, h, icon, toast, t };
