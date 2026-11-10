// Scriber — funções puras de texto (sem DOM, testáveis no Node): contar palavras, achar falas (diálogos) e trechos entre aspas, classificar uma seleção e calcular o tamanho pedido da expansão.

export const countWords = (s) => ((String(s || '').match(/[\p{L}\p{N}][\p{L}\p{N}'’-]*/gu)) || []).length;

// Uma linha é uma fala quando começa com travessão/hífen de diálogo ou com aspas de abertura (ou é inteira entre aspas).
const DASH = /^\s*[—–-]\s*\S/;
const OPEN = /^\s*["“«„‘']\s*\S/;
export const isDialogueLine = (s) => DASH.test(String(s || '')) || OPEN.test(String(s || ''));

// trechos entre aspas dentro de uma linha: [{start, end}] (end exclusivo). Pares: “…” "…" «…» „…“ — um par aberto e não fechado vai até o fim da linha.
export function quotedSpans(s) {
  s = String(s || '');
  const out = [];
  const pairs = { '“': '”', '"': '"', '«': '»', '„': '“', '‘': '’' };
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (!(c in pairs)) continue;
    if (c === '‘' && /\w/.test(s[i - 1] || '')) continue;
    const close = pairs[c];
    let j = s.indexOf(close, i + 1);
    if (j < 0) j = s.length - 1;
    if (j > i + 1) out.push({ start: i, end: j + 1 });
    i = j;
  }
  return out;
}

// A fala sob um deslocamento (caret) numa linha: a linha inteira (se começa com travessão), o trecho entre aspas que contém o caret ou null.
export function dialogueAt(s, offset) {
  s = String(s || '');
  if (DASH.test(s)) return { start: 0, end: s.length, kind: 'dash' };
  const spans = quotedSpans(s);
  const hit = spans.find((p) => offset >= p.start && offset <= p.end) || (spans.length === 1 ? spans[0] : null);
  if (hit) return { start: hit.start, end: hit.end, kind: 'quote' };
  if (OPEN.test(s)) return { start: 0, end: s.length, kind: 'quote' };
  return null;
}

// 'dialogue' | 'paragraph' | 'mixed' para as linhas de uma seleção
export function selectionKind(lines) {
  const ls = (lines || []).map((x) => String(x || '').trim()).filter(Boolean);
  if (!ls.length) return 'paragraph';
  const d = ls.filter(isDialogueLine).length;
  return d === ls.length ? 'dialogue' : d === 0 ? 'paragraph' : 'mixed';
}

// Quantas palavras pedir: modo «add» soma ao que já existe, «total» é o tamanho final. O de diálogo vale quando a seleção é só fala.
export function expandRequest(kind, cfg) {
  const words = kind === 'dialogue' ? cfg.dialogue_words : cfg.expand_words;
  return { mode: cfg.mode === 'total' ? 'total' : 'add', words: Math.max(10, Math.min(3000, Math.round(Number(words) || 120))) };
}

// Posição (parágrafo, início, fim) de um achado de ortografia → útil para conferir se o texto ainda bate
export const sliceOf = (para, start, end) => String(para || '').slice(start, end);

// Aspas «inteligentes» simples para a interface (a rotina completa é a do servidor, `spell.typography`)
export const plainLines = (text) => String(text || '').split(/\r?\n/).filter((x) => x.trim().length);

// Proporção de páginas (palavras ÷ palavras por página)
export const pagesFor = (words, wpp) => Math.round((words / Math.max(1, wpp)) * 10) / 10;
