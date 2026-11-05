// Componentes visuais dos avatars: retrato (ou rosto desenhado com humor), cores e texto com *ações*.
import { h } from './ui.js';

const NS = 'http://www.w3.org/2000/svg';
export const MOOD_EMOJI = { neutral: '🙂', happy: '😊', sad: '😢', angry: '😠', shy: '😳', excited: '🤩', surprised: '😮', flirty: '😉', sleepy: '😴', worried: '😟' };
export const REL_LABEL = { friend: 'Amigo(a)', partner: 'Namorado(a)', companion: 'Companheiro(a)', mentor: 'Mentor(a)', custom: 'Outro' };

export const portraitUrl = (av) => (av && av.portrait ? '/api/avatars/' + av.id + '/portrait?v=' + encodeURIComponent(av.portrait) : '');

// Rosto desenhado a partir da aparência (cores do card) e do humor atual.
export function faceSVG(ap, mood = 'neutral', size = 44) {
  ap = Object.assign({ skin: '#c68a63', hair: '#2b1b12', hair_style: 'short', top: '#3b5b7a' }, ap || {});
  const s = document.createElementNS(NS, 'svg');
  s.setAttribute('viewBox', '0 0 64 64'); s.setAttribute('width', size); s.setAttribute('height', size);
  const el = (tag, a) => { const e = document.createElementNS(NS, tag); Object.entries(a).forEach(([k, v]) => e.setAttribute(k, v)); s.appendChild(e); return e; };
  const ink = '#1a1412', line = { fill: 'none', stroke: ink, 'stroke-width': 2.2, 'stroke-linecap': 'round' };
  el('rect', { width: 64, height: 64, fill: '#161616' });
  if (ap.hair_style === 'long') el('rect', { x: 14, y: 16, width: 36, height: 40, rx: 14, fill: ap.hair });
  el('path', { d: 'M8 66c2-14 12-18 24-18s22 4 24 18z', fill: ap.top });
  el('rect', { x: 27, y: 40, width: 10, height: 10, rx: 4, fill: ap.skin });
  el('ellipse', { cx: 32, cy: 29, rx: 14, ry: 15.5, fill: ap.skin });
  if (ap.hair_style !== 'bald') el('path', { d: 'M17 28c-1-12 7-18 15-18s16 6 15 18c-3-7-8-9-15-9s-12 2-15 9z', fill: ap.hair });
  if (ap.hair_style === 'bun') el('circle', { cx: 32, cy: 8, r: 6, fill: ap.hair });
  // olhos e boca por humor
  const eyeDots = (y, r = 1.9, dx = 5.5) => { el('circle', { cx: 32 - dx, cy: y, r, fill: ink }); el('circle', { cx: 32 + dx, cy: y, r, fill: ink }); };
  const arc = (x, y, up) => el('path', Object.assign({ d: `M${x - 3} ${y}q3 ${up ? -4 : 4} 6 0` }, line));
  const mouth = { neutral: 'M27 38q5 2 10 0', happy: 'M26 37q6 6 12 0', sad: 'M27 40q5-4 10 0', angry: 'M27 40q5-3 10 0', shy: 'M28 38q4 2 8 0', excited: 'M26 36q6 8 12 0z', surprised: '', flirty: 'M27 37q5 4 10 0', sleepy: 'M29 38h6', worried: 'M27 39q2-2 5 0t5 0' };
  if (mood === 'happy' || mood === 'excited') { arc(26.5, 28, true); arc(37.5, 28, true); }
  else if (mood === 'sleepy') { el('path', Object.assign({ d: 'M22 29h8M34 29h8' }, line)); }
  else if (mood === 'flirty') { eyeDots(28.5); arc(37.5, 28, true); }
  else if (mood === 'surprised') { el('circle', { cx: 26.5, cy: 28, r: 3, fill: '#fff', stroke: ink, 'stroke-width': 1.6 }); el('circle', { cx: 37.5, cy: 28, r: 3, fill: '#fff', stroke: ink, 'stroke-width': 1.6 }); eyeDots(28, 1.3); }
  else eyeDots(mood === 'shy' ? 29.5 : 28.5);
  if (mood === 'sad' || mood === 'worried') { el('path', Object.assign({ d: 'M22 23l7 2M42 23l-7 2' }, line, { 'stroke-width': 1.8 })); }
  if (mood === 'angry') { el('path', Object.assign({ d: 'M22 25l7-3M42 25l-7-3' }, line, { 'stroke-width': 2 })); }
  if (mood === 'surprised') el('ellipse', { cx: 32, cy: 39, rx: 2.6, ry: 3.4, fill: ink }); else el('path', Object.assign({ d: mouth[mood] || mouth.neutral }, line, mood === 'excited' ? { fill: '#7a1f2b' } : {}));
  if (mood === 'shy' || mood === 'flirty' || mood === 'excited') { el('circle', { cx: 22.5, cy: 34, r: 3, fill: '#ff7a8a', opacity: 0.45 }); el('circle', { cx: 41.5, cy: 34, r: 3, fill: '#ff7a8a', opacity: 0.45 }); }
  return s;
}

// Retrato circular: a imagem do avatar (anexada/importada) ou o rosto desenhado.
export function avatarPic(av, size = 40, mood = 'neutral') {
  const box = h('span', { class: 'apic', style: { width: size + 'px', height: size + 'px' }, title: av ? av.name : '' });
  const url = portraitUrl(av);
  if (url) box.appendChild(h('img', { src: url, alt: av.name, width: size, height: size, loading: 'lazy' }));
  else box.appendChild(faceSVG(av && av.appearance, mood, size));
  return box;
}

// Cor de destaque do nome do avatar nas conversas em grupo (legível no fundo preto).
export function speakerColor(av) {
  const hex = ((av && av.appearance && (av.appearance.top || av.appearance.hair)) || '#8899aa').replace('#', '');
  let r = parseInt(hex.slice(0, 2), 16) || 136, g = parseInt(hex.slice(2, 4), 16) || 153, b = parseInt(hex.slice(4, 6), 16) || 170;
  const lift = (c) => Math.round(c + (255 - c) * 0.45);
  return `rgb(${lift(r)},${lift(g)},${lift(b)})`;
}

// Texto da conversa: *ações* viram itálico (sempre nós de texto, nunca innerHTML).
export function richText(el, text) {
  el.replaceChildren();
  String(text || '').split(/(\*[^*\n]+\*)/g).forEach((part) => {
    if (!part) return;
    if (/^\*[^*\n]+\*$/.test(part)) el.appendChild(h('em', { class: 'act' }, part.slice(1, -1)));
    else el.appendChild(document.createTextNode(part));
  });
  return el;
}

// Lê um corpo SSE de uma resposta fetch (POST): chama onEvent(obj) para cada evento.
export async function readSSE(resp, onEvent) {
  const reader = resp.body.getReader(), dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const r = await reader.read();
    if (r.done) break;
    buf += dec.decode(r.value, { stream: true }).replace(/\r\n/g, '\n');
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
      const data = chunk.split('\n').filter((l) => l.indexOf('data:') === 0).map((l) => l.slice(5).trim()).join('');
      if (data) { try { onEvent(JSON.parse(data)); } catch (e) { /* ignora */ } }
    }
  }
}
