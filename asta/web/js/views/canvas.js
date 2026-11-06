import { api } from '../api.js';
import { t } from '../i18n.js';
import { go, state } from '../main.js';
import { confirmDialog, fill, fmtDate, h, icon, modal, popover, toast } from '../ui.js';

// Sub-rotas: #/canvas (lista de canvases) · #/canvas/edit/<id> (editor)
export const subRoute = () => { const m = location.hash.match(/^#\/canvas\/edit\/([\w-]+)/); return m ? { mode: 'edit', id: m[1] } : { mode: 'list', id: '' }; };
export const openCanvas = (id) => { location.hash = '#/canvas/edit/' + id; };

export default async function render(root, ctx) {
  const sub = subRoute();
  if (sub.mode === 'edit') return (await import('./canvas_edit.js')).default(root, ctx, sub.id);
  return renderList(root, ctx);
}

const TPL_LABEL = {
  blank: ['Em branco', 'Um canvas vazio: adicione os nós que quiser.'], text_image: ['Texto → Imagem', 'Um prompt de texto que vira uma imagem.'],
  image_video: ['Texto → Imagem → Vídeo', 'Gera uma imagem e anima em um vídeo curto.'], styled: ['Com estilo do projeto', 'Style Prompt + prompt + imagem: o estilo vale para todo o canvas.'],
  scene: ['Cena completa (imagem, voz e Editor)', 'Roteiro → imagem → vídeo + narração + som, tudo montado no Editor.'],
};

async function renderList(root) {
  let list = await api('/api/canvases');
  const grid = h('div', { class: 'cv-grid' });

  async function create(preset) {
    const meta = await api('/api/canvas-templates');
    let tpl = preset || (state.settings.canvas && state.settings.canvas.template) || 'text_image';
    const name = h('input', { placeholder: t('Nome do canvas') });
    const prompt = h('textarea', { placeholder: t('Ideia inicial (opcional): ela vira o primeiro prompt do modelo.'), rows: 2, style: { minHeight: '60px' } });
    const tpls = h('div', { class: 'cv-tpls' });
    const paint = () => fill(tpls, meta.templates.map((x) => h('button', { type: 'button', class: 'cv-tpl' + (x.id === tpl ? ' on' : ''), onclick: () => { tpl = x.id; paint(); } },
      h('b', null, t((TPL_LABEL[x.id] || [x.label])[0])), h('span', null, t((TPL_LABEL[x.id] || [0, x.hint])[1])))));
    paint();
    const ok = await modal(t('Novo canvas'), h('div', null, h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Um canvas é um fluxo de nós para gerar e editar imagens, vídeos, sons e vozes. Crie um por projeto.')), name, tpls, prompt),
      [{ label: t('Cancelar'), value: false }, { label: t('Criar'), value: true, cls: 'primary' }]);
    if (!ok) return;
    try { const c = await api('/api/canvases', { method: 'POST', body: { name: name.value.trim(), template: tpl, prompt: prompt.value.trim() } }); openCanvas(c.id); }
    catch (e) { toast(e.message, 'err'); }
  }

  async function refresh() { list = await api('/api/canvases'); paint(); }
  function menu(anchor, c) {
    const item = (label, ic, fn, cls) => h('div', { class: 'opt ' + (cls || ''), onclick: () => { pop.close(); fn(); } }, icon(ic, 15), label);
    const pop = popover(anchor, h('div', null,
      item(t('Abrir'), 'canvas', () => openCanvas(c.id)),
      item(t('Renomear'), 'edit', async () => {
        const inp = h('input', { value: c.name });
        const ok = await modal(t('Renomear canvas'), inp, [{ label: t('Cancelar'), value: false }, { label: t('Salvar'), value: true, cls: 'primary' }]);
        if (ok && inp.value.trim()) { await api(`/api/canvases/${c.id}/meta`, { method: 'POST', body: { name: inp.value } }); refresh(); }
      }),
      item(t('Duplicar'), 'copy', async () => { await api(`/api/canvases/${c.id}/duplicate`, { method: 'POST' }); toast(t('Duplicado')); refresh(); }),
      h('a', { class: 'opt', href: `/api/canvases/${c.id}/download` }, icon('download', 15), t('Baixar (.zip)')),
      item(t('Apagar'), 'trash', async () => {
        if (!(await confirmDialog(t('Apagar o canvas “{n}” e todos os arquivos dele?', { n: c.name })))) return;
        try { await api('/api/canvases/' + c.id, { method: 'DELETE' }); toast(t('Apagado')); refresh(); } catch (e) { toast(e.message, 'err'); }
      }, 'danger')));
  }

  function paint() {
    fill(grid, list.map((c) => h('div', { class: 'cv-card', onclick: () => openCanvas(c.id) },
      h('div', { class: 'th', style: c.thumb ? { backgroundImage: `url("${c.thumb}")` } : {} }, c.thumb ? null : icon('canvas', 34)),
      h('button', { class: 'btn icon sm mn', title: t('Mais'), onclick: (e) => { e.stopPropagation(); menu(e.currentTarget, c); } }, icon('more', 15)),
      h('div', { class: 'inf' }, h('div', { class: 'nm', title: c.name }, c.name === 'Novo canvas' ? t('Novo canvas') : c.name),
        h('div', { class: 'mt' }, t('{n} nós · {m} arquivos', { n: c.nodes, m: c.assets }) + ' · ' + fmtDate(c.updated))))));
    body.classList.toggle('hidden', !list.length);
    empty.classList.toggle('hidden', !!list.length);
  }
  const body = h('div', null, grid);
  const empty = h('div', { class: 'empty' }, h('h3', null, t('Crie seu primeiro canvas')),
    h('p', null, t('Ligue nós de texto, imagem, vídeo, som e voz — e monte tudo no Editor de vídeo. Estilos valem para o projeto inteiro.')),
    h('button', { class: 'btn primary', onclick: () => create() }, icon('plus', 14), t('Novo canvas')));

  fill(root, h('div', { class: 'page cv-pg' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, t('Canvas')), h('p', null, t('Gere e edite imagens, vídeos, sons e vozes com fluxos simples de nós. Modelos de empresas (API) ou locais.'))),
      h('div', { class: 'row' }, h('a', { class: 'btn', href: '#/config', onclick: () => { go('config', { tab: 'media' }); } }, icon('config', 14), t('Provedores de mídia')),
        h('button', { class: 'btn primary', onclick: () => create() }, icon('plus', 14), t('Novo canvas')))),
    body, empty));
  paint();
}
