import { upload, api } from '../api.js';
import { t } from '../i18n.js';
import { fmtBytes, h, icon, kindIcon, toast } from '../ui.js';
import { isSendKey } from '../prefs.js';

// Tipo (ícone) de um arquivo pelo nome
export const kindOf = (n) => {
  const e = String(n).split('.').pop().toLowerCase();
  return { png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', bmp: 'image', mp3: 'audio', wav: 'audio', ogg: 'audio', m4a: 'audio', flac: 'audio', mp4: 'video', mov: 'video', webm: 'video', mkv: 'video',
    pdf: 'document', docx: 'document', doc: 'document', odt: 'document', xlsx: 'spreadsheet', csv: 'spreadsheet', ods: 'spreadsheet', pptx: 'presentation', odp: 'presentation' }[e] || 'text';
};

// Compositor: caixa de texto + anexos de qualquer tipo (clique, arrastar-e-soltar, colar) + botão de enviar.
// opts: { placeholder, value, tools: [Node], rightTools: [Node] (ficam ao lado do botão, à direita), extraReady(): bool, allowEmpty: bool, sendLabel, sendTitle, onSend({text, ids}) }
// `configure()` troca placeholder/ferramentas/ação sem perder o texto nem os anexos (o Chat usa isso ao ligar uma ferramenta de criação).
export function createComposer(opts) {
  const m = { files: [] };
  let o = Object.assign({}, opts);
  const ta = h('textarea', { rows: 2, placeholder: o.placeholder || '' });
  ta.value = o.value || '';
  const attachRow = h('div', { class: 'attach-row hidden' });
  const fileInput = h('input', { type: 'file', multiple: true, class: 'hidden' });
  const sendBtn = h('button', { class: 'send', type: 'button', disabled: true });
  const toolsBox = h('div', { class: 'tools' });
  let busy = null;  // { stop } enquanto uma resposta está em andamento: o botão vira «Parar»
  const uploading = () => m.files.some((f) => f.status === 'up');
  const ready = () => !!(ta.value.trim() || m.files.length || (o.extraReady && o.extraReady()) || o.allowEmpty);
  const paintSend = () => {
    sendBtn.classList.toggle('pill', !!o.sendLabel); sendBtn.classList.toggle('stop', !!busy);
    sendBtn.replaceChildren(icon(busy ? 'stop' : (o.sendLabel ? 'play' : 'send'), o.sendLabel ? 15 : 18), o.sendLabel ? h('span', null, busy ? t('Parar') : o.sendLabel) : null);
    sendBtn.title = busy ? t('Parar') : (o.sendTitle || o.sendLabel || t('Gerar')); sendBtn.setAttribute('aria-label', sendBtn.title);
  };
  const refresh = () => { sendBtn.disabled = busy ? false : (uploading() || !ready()); };
  const paintTools = () => toolsBox.replaceChildren(h('button', { class: 'tool', type: 'button', title: t('Anexar arquivos'), onclick: () => fileInput.click() }, icon('clip', 15), t('Anexar')),
    ...(o.tools || []), h('div', { class: 'rt' }, ...(o.rightTools || []), sendBtn), fileInput);

  const paintFiles = () => {
    attachRow.classList.toggle('hidden', !m.files.length);
    attachRow.replaceChildren(...m.files.map((f) => h('div', { class: 'att', title: f.error || f.name },
      f.status === 'up' ? h('div', { class: 'spinner' }) : kindIcon(f.kind || 'file'),
      h('span', { class: 'n' }, f.name), h('span', { class: 's' }, f.error ? '⚠' : fmtBytes(f.size)),
      f.status === 'up' ? h('div', { class: 'bar' }, h('i', { style: { width: Math.round(f.progress * 100) + '%' } })) : null,
      h('span', { class: 'x', onclick: () => { if (f.id) api('/api/uploads/' + f.id, { method: 'DELETE' }).catch(() => {}); m.files = m.files.filter((x) => x !== f); paintFiles(); } }, '×'))));
    refresh();
  };
  const addFiles = (list) => {
    [...list].forEach((file) => {
      const f = { name: file.name, size: file.size, kind: kindOf(file.name), progress: 0, status: 'up' };
      m.files.push(f); paintFiles();
      upload(file, (p) => { f.progress = p; paintFiles(); }).then((meta) => { f.id = meta.id; f.status = 'ok'; paintFiles(); })
        .catch((e) => { f.status = 'err'; f.error = e.message; toast(e.message, 'err'); m.files = m.files.filter((x) => x !== f); paintFiles(); });
    });
  };
  const send = () => {
    if (busy) return busy.stop();
    if (!sendBtn.disabled && o.onSend) o.onSend({ text: ta.value, ids: m.files.map((f) => f.id).filter(Boolean) });
  };

  fileInput.addEventListener('change', () => { addFiles(fileInput.files); fileInput.value = ''; });
  ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(240, ta.scrollHeight) + 'px'; refresh(); });
  ta.addEventListener('keydown', (e) => { if (isSendKey(e) && !busy) { e.preventDefault(); send(); } });
  ta.addEventListener('paste', (e) => { const fs = [...(e.clipboardData ? e.clipboardData.files : [])]; if (fs.length) { e.preventDefault(); addFiles(fs); } });
  sendBtn.addEventListener('click', send);

  const el = h('div', { class: 'composer' }, attachRow, ta, toolsBox);
  ['dragenter', 'dragover'].forEach((ev) => el.addEventListener(ev, (e) => { e.preventDefault(); el.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach((ev) => el.addEventListener(ev, (e) => { e.preventDefault(); el.classList.remove('drag'); }));
  el.addEventListener('drop', (e) => { if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files); });
  paintTools(); paintSend();
  setTimeout(() => { ta.dispatchEvent(new Event('input')); }, 0);
  return {
    el, ta, refresh, focus: () => ta.focus(), text: () => ta.value,
    setSending: (v) => { sendBtn.disabled = v || uploading() || !ready(); },
    setText: (v) => { ta.value = v; ta.dispatchEvent(new Event('input')); },
    configure: (next) => { o = Object.assign({}, o, next); ta.placeholder = o.placeholder || ''; paintTools(); paintSend(); refresh(); },
    setBusy: (on, stop) => { busy = on ? { stop: stop || (() => {}) } : null; paintSend(); refresh(); },
    clearFiles: (ids) => { m.files = Array.isArray(ids) ? m.files.filter((f) => !ids.includes(f.id)) : []; paintFiles(); },   // sem argumento: todos; com ids: só os enviados
    hasUploading: uploading, fileIds: () => m.files.map((f) => f.id).filter(Boolean),
  };
}
