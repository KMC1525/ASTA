// Seletor de modelo do Chat: troca de provedor e de modelo em um clique (nuvem, LM Studio, Ollama, modelo local…).
import { api } from './api.js';
import { t } from './i18n.js';
import { h, icon, popover, toast } from './ui.js';

export const modelLabel = (cur) => (!cur ? t('Modelo') : cur.demo ? t('Demo (sem IA)') : (cur.model ? cur.model : t(cur.label || 'Modelo')));

// host: { saveSettings, go, onChange(current) }
export async function openModelPicker(anchor, host) {
  const box = h('div', { class: 'mpick' }, h('div', { class: 'spinner' }));
  const pop = popover(anchor, box);
  let data;
  try { data = await api('/api/chat/providers'); } catch (e) { pop.close(); return toast(e.message, 'err'); }
  const cur = data.current;
  let openId = (data.providers.find((p) => p.selected) || {}).id || '';
  const models = {};  // cache dos modelos de cada provedor nesta abertura

  async function choose(pid, model) {
    pop.close();
    try {
      await host.saveSettings({ active: { generation: pid }, providers: { [pid]: { model } } });
      const fresh = await api('/api/chat/providers');
      host.onChange(fresh.current);
      toast(t('Chat usando {n}', { n: (model || t('o modelo carregado')) + ' · ' + t((data.providers.find((p) => p.id === pid) || {}).label || pid) }), 'ok');
    } catch (e) { toast(e.message, 'err'); }
  }
  async function loadModels(p) {
    if (models[p.id]) return models[p.id];
    try { models[p.id] = (await api('/api/providers/models', { method: 'POST', body: { id: p.id, config: {} } })); } catch (e) { models[p.id] = { ok: false, error: e.message, models: [] }; }
    return models[p.id];
  }
  // barra de pesquisa: filtra os modelos de TODOS os provedores usáveis (nuvem e locais) de uma vez; Enter escolhe o primeiro resultado
  let query = '', seq = 0, first = null;
  const body = h('div', { class: 'mp-body' });   // só o corpo é redesenhado: o campo de pesquisa fica no lugar (senão perde o foco a cada letra)
  const search = h('input', { class: 'mp-search', type: 'search', placeholder: t('Pesquisar modelo ou provedor…'), 'aria-label': t('Pesquisar modelo ou provedor'), autocomplete: 'off',
    oninput: () => { query = search.value.trim().toLowerCase(); paint(); },
    onkeydown: (e) => { if (e.key === 'Enter' && first) { e.preventDefault(); first(); } } });
  async function paintSearch() {
    const my = ++seq, terms = query.split(/\s+/).filter(Boolean);
    const list = h('div', { class: 'mp-results' }, h('div', { class: 'spinner' }));
    body.replaceChildren(list);
    const usable = data.providers.filter((p) => p.usable || p.model);
    const loaded = await Promise.all(usable.map(async (p) => [p, await loadModels(p)]));
    if (my !== seq) return;   // o usuário continuou digitando
    const rows = [];
    first = null;
    const hit = (txt) => terms.every((w) => txt.toLowerCase().includes(w));
    for (const [p, r] of loaded) {
      const label = t(p.label);
      const ms = (r.models || []).filter((m) => hit(m + ' ' + label + ' ' + p.id)).slice(0, 40);
      if (!ms.length) continue;
      rows.push(h('div', { class: 'mp-group' }, label, p.local ? h('span', { class: 'badge' }, t('local')) : h('span', { class: 'badge' }, t('nuvem'))));
      ms.forEach((m) => { const go = () => choose(p.id, m); if (!first) first = go; rows.push(h('div', { class: 'mp-model' + (p.selected && p.model === m ? ' on' : ''), onclick: go }, m)); });
    }
    const notReady = data.providers.filter((p) => !(p.usable || p.model) && hit(t(p.label) + ' ' + p.id));
    notReady.forEach((p) => rows.push(h('div', { class: 'mp-prov off', role: 'button', tabindex: '0', onclick: () => { pop.close(); host.go('config', { tab: 'providers' }); } },
      h('span', { class: 'grow' }, t(p.label)), h('span', { class: 'dim small' }, p.needs_key && !p.has_key ? t('sem chave') : t('configurar')), icon('chev', 13))));
    if (!rows.length) rows.push(h('div', { class: 'dim small', style: { padding: '8px 10px' } }, t('Nenhum modelo encontrado para «{q}».', { q: query })));
    list.replaceChildren(...rows);
  }
  async function paint() {
    if (query) return paintSearch();
    first = null;
    const rows = [];
    for (const p of data.providers) {
      const open = openId === p.id, selected = p.selected;
      const head = h('div', { class: 'mp-prov' + (selected ? ' on' : '') + (!p.usable && !open ? ' off' : ''), role: 'button', tabindex: '0',
        onclick: () => { if (!p.usable && !(p.model)) { if (p.needs_key && !p.has_key) { pop.close(); return host.go('config', { tab: 'providers' }); } } openId = open ? '' : p.id; paint(); } },
      h('span', { class: 'mp-dot' }, selected ? '●' : '○'), h('span', { class: 'grow' }, t(p.label)), p.local ? h('span', { class: 'badge' }, t('local')) : h('span', { class: 'badge' }, t('nuvem')),
      !p.usable && p.needs_key && !p.has_key ? h('span', { class: 'dim small' }, t('sem chave')) : null, icon('chev', 13));
      rows.push(head);
      if (open) {
        const list = h('div', { class: 'mp-models' }, h('div', { class: 'spinner' }));
        rows.push(list);
        loadModels(p).then((r) => {
          const items = [];
          if (p.id === 'lmstudio') items.push(h('div', { class: 'mp-model' + (selected && !p.model ? ' on' : ''), onclick: () => choose(p.id, '') }, t('Automático (o modelo carregado no LM Studio)')));
          (r.models || []).forEach((m) => items.push(h('div', { class: 'mp-model' + (selected && p.model === m ? ' on' : ''), onclick: () => choose(p.id, m) }, m)));
          if (!items.length) items.push(h('div', { class: 'dim small', style: { padding: '6px 10px' } }, r.error ? r.error : t('Nenhum modelo encontrado.')));
          const manual = h('input', { placeholder: t('Outro modelo (digite o nome)…'), onkeydown: (e) => { if (e.key === 'Enter' && manual.value.trim()) choose(p.id, manual.value.trim()); } });
          list.replaceChildren(...items, h('div', { style: { padding: '6px 6px 2px' } }, manual));
        });
      }
    }
    body.replaceChildren(...rows,
      h('div', { class: 'mp-foot' }, h('a', { href: '#/config', onclick: () => { pop.close(); host.go('config', { tab: 'providers' }); return false; } }, icon('config', 13), t('Gerenciar provedores…'))));
  }
  box.replaceChildren(h('div', { class: 'mp-title' }, t('Modelo do Chat')), search, body);
  await paint();
  search.focus();
}
