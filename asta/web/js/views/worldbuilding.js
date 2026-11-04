import { api } from '../api.js';
import { t } from '../i18n.js';
import { confirmDialog, download, field, h, icon, modal, tagsInput, toast } from '../ui.js';

const blank = () => ({ name: '', tags: [], system_prompt: '' });

export default async function render(root, ctx) {
  let list = await api('/api/worldbuildings');
  let sel = ctx.select || (list[0] && list[0].id) || null, draft = null;
  const listEl = h('div', { class: 'list' }), editor = h('div');

  const load = (id) => { sel = id; const c = list.find((x) => x.id === id); draft = c ? JSON.parse(JSON.stringify(c)) : null; paintList(); paintEditor(); };
  const newDraft = (base) => { sel = null; draft = Object.assign(blank(), base || {}); paintList(); paintEditor(); };
  const reload = async (id) => { list = await api('/api/worldbuildings'); load(id !== undefined ? id : sel); };

  function paintList() {
    listEl.replaceChildren(...(list.length ? list.map((c) => h('div', { class: 'li' + (c.id === sel ? ' active' : ''), onclick: () => load(c.id) },
      h('div', { class: 'av' }, icon('worldbuilding', 16)), h('div', { style: { minWidth: 0 } }, h('div', { class: 't' }, c.name), h('div', { class: 's' }, (c.system_prompt || '').slice(0, 60))))) :
      [h('div', { class: 'muted small', style: { padding: '8px 12px' } }, t('Nenhum worldbuilding ainda.'))]));
  }

  function paintEditor() {
    if (!draft) { editor.replaceChildren(h('div', { class: 'empty' }, h('h3', null, t('Defina as regras gerais dos seus mundos')), h('p', null, t('Um worldbuilding descreve cenário, tom, regras e convenções — e vale para todos os personagens do mundo.')),
      h('div', { class: 'row', style: { justifyContent: 'center' } }, h('button', { class: 'btn primary', onclick: () => newDraft() }, icon('plus', 15), t('Novo worldbuilding')), h('button', { class: 'btn', onclick: aiCreate }, icon('sparkle', 15), t('Criar com IA'))))); return; }
    const d = draft;
    editor.replaceChildren(
      h('div', { class: 'row', style: { marginBottom: '16px' } }, h('h2', { style: { margin: 0, fontSize: '20px', fontWeight: 600 } }, d.id ? d.name || t('Sem nome') : t('Novo worldbuilding')), h('span', { class: 'grow' }),
        d.id ? h('button', { class: 'btn sm', onclick: () => download((d.name || 'worldbuilding').replace(/\W+/g, '-') + '.json', JSON.stringify(d, null, 2)) }, icon('download', 14), t('Exportar')) : null,
        d.id ? h('button', { class: 'btn sm', onclick: async () => { const c = await api('/api/worldbuildings', { method: 'POST', body: Object.assign({}, d, { id: undefined, name: d.name + ' (2)' }) }); toast(t('Duplicado')); reload(c.id); } }, icon('copy', 14), t('Duplicar')) : null,
        d.id ? h('button', { class: 'btn sm danger', onclick: async () => { if (await confirmDialog(t('Apagar o worldbuilding “{n}”?', { n: d.name }))) { await api('/api/worldbuildings/' + d.id, { method: 'DELETE' }); toast(t('Apagado')); list = list.filter((x) => x.id !== d.id); load(list[0] ? list[0].id : null); } } }, icon('trash', 14)) : null),
      h('div', { class: 'card' },
        field(t('Nome do worldbuilding'), h('input', { value: d.name, placeholder: t('Ex.: Reino de Alder — fantasia sombria'), oninput: (e) => { d.name = e.target.value; } })),
        field(t('Tags'), tagsInput(d.tags, (v) => { d.tags = v; })),
        field(t('System prompt'), h('textarea', { rows: 16, placeholder: t('Cenário, época, tecnologia/magia, facções, tom, tabus, como os personagens falam e se comportam…'), oninput: (e) => { d.system_prompt = e.target.value; } }, d.system_prompt),
          t('Este texto é entregue a todos os agentes ao gerar o mundo e a cada NPC durante o jogo.')),
        h('div', { class: 'row', style: { justifyContent: 'flex-end' } }, h('button', { class: 'btn primary', onclick: save }, icon('check', 15), t('Salvar')))));
  }

  async function save() {
    if (!draft.name.trim()) return toast(t('Dê um nome ao worldbuilding.'), 'err');
    try {
      const c = draft.id ? await api('/api/worldbuildings/' + draft.id, { method: 'PUT', body: draft }) : await api('/api/worldbuildings', { method: 'POST', body: draft });
      toast(t('Worldbuilding salvo'), 'ok'); await reload(c.id);
    } catch (e) { toast(e.message, 'err'); }
  }
  async function aiCreate() {
    const ta = h('textarea', { rows: 5, placeholder: t('Descreva o tipo de mundo: cenário, tom, regras, época…') });
    const v = await modal(t('Criar worldbuilding com IA'), h('div', null, h('p', { class: 'muted small', style: { marginTop: 0 } }, t('A IA escreve o card; você revisa e salva.')), ta),
      [{ label: t('Cancelar'), value: null }, { label: t('Criar'), value: 'ok', cls: 'primary' }]);
    if (v !== 'ok' || !ta.value.trim()) return;
    toast(t('Criando…'));
    try { newDraft(await api('/api/ai/worldbuilding', { method: 'POST', body: { description: ta.value } })); toast(t('Rascunho pronto — revise e salve.'), 'ok'); } catch (e) { toast(e.message, 'err'); }
  }
  const importInput = h('input', { type: 'file', accept: '.json,application/json', class: 'hidden', onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { const data = JSON.parse(await f.text()); const c = await api('/api/worldbuildings', { method: 'POST', body: Object.assign({}, data, { id: undefined }) }); toast(t('Importado'), 'ok'); await reload(c.id); } catch (er) { toast(t('Arquivo inválido'), 'err'); }
    e.target.value = '';
  } });

  root.replaceChildren(h('div', { class: 'page' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'Worldbuilding'), h('p', null, t('Regras gerais que valem para os mundos gerados. Cada uma é salva como um card.'))),
      h('div', { class: 'row' }, h('button', { class: 'btn', onclick: aiCreate }, icon('sparkle', 15), t('Criar com IA')), h('button', { class: 'btn', onclick: () => importInput.click() }, icon('upload', 15), t('Importar')), importInput,
        h('button', { class: 'btn primary', onclick: () => newDraft() }, icon('plus', 15), t('Novo')))),
    h('div', { class: 'split' }, listEl, editor)));
  if (sel) load(sel); else { paintList(); paintEditor(); }
}
