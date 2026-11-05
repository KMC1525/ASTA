import { upload, api } from '../api.js';
import { t } from '../i18n.js';
import { fmtBytes, h, icon, kindIcon, toast } from '../ui.js';

// Tipo (ícone) de um arquivo pelo nome
export const kindOf = (n) => {
  const e = String(n).split('.').pop().toLowerCase();
  return { png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', bmp: 'image', mp3: 'audio', wav: 'audio', ogg: 'audio', m4a: 'audio', flac: 'audio', mp4: 'video', mov: 'video', webm: 'video', mkv: 'video',
    pdf: 'document', docx: 'document', doc: 'document', odt: 'document', xlsx: 'spreadsheet', csv: 'spreadsheet', ods: 'spreadsheet', pptx: 'presentation', odp: 'presentation' }[e] || 'text';
};

// Compositor: caixa de texto + anexos de qualquer tipo (clique, arrastar-e-soltar, colar) + botão de enviar.
// opts: { placeholder, value, tools: [Node], extraReady(): bool, allowEmpty: bool, onSend({text, ids}) }
export function createComposer(opts) {
  const m = { files: [] };
  const ta = h('textarea', { rows: 2, placeholder: opts.placeholder || '' });
  ta.value = opts.value || '';
  const attachRow = h('div', { class: 'attach-row hidden' });
  const fileInput = h('input', { type: 'file', multiple: true, class: 'hidden' });
  const sendBtn = h('button', { class: 'send', title: t('Gerar'), disabled: true }, icon('send', 18));
  const uploading = () => m.files.some((f) => f.status === 'up');
  const ready = () => !!(ta.value.trim() || m.files.length || (opts.extraReady && opts.extraReady()) || opts.allowEmpty);
  const refresh = () => { sendBtn.disabled = uploading() || !ready(); };

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
  const send = () => { if (!sendBtn.disabled && opts.onSend) opts.onSend({ text: ta.value, ids: m.files.map((f) => f.id).filter(Boolean) }); };

  fileInput.addEventListener('change', () => { addFiles(fileInput.files); fileInput.value = ''; });
  ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(240, ta.scrollHeight) + 'px'; refresh(); });
  ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
  ta.addEventListener('paste', (e) => { const fs = [...(e.clipboardData ? e.clipboardData.files : [])]; if (fs.length) { e.preventDefault(); addFiles(fs); } });
  sendBtn.addEventListener('click', send);

  const el = h('div', { class: 'composer' }, attachRow, ta,
    h('div', { class: 'tools' }, h('button', { class: 'tool', type: 'button', title: t('Anexar arquivos'), onclick: () => fileInput.click() }, icon('clip', 15), t('Anexar')), ...(opts.tools || []), sendBtn, fileInput));
  ['dragenter', 'dragover'].forEach((ev) => el.addEventListener(ev, (e) => { e.preventDefault(); el.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach((ev) => el.addEventListener(ev, (e) => { e.preventDefault(); el.classList.remove('drag'); }));
  el.addEventListener('drop', (e) => { if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files); });
  setTimeout(() => { ta.dispatchEvent(new Event('input')); }, 0);
  return { el, ta, refresh, focus: () => ta.focus(), setSending: (v) => { sendBtn.disabled = v || uploading() || !ready(); }, text: () => ta.value, setText: (v) => { ta.value = v; ta.dispatchEvent(new Event('input')); } };
}
