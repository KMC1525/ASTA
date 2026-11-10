// Scriber → Geração automática: do prompt, esboço ou anexos a um documento inteiro (e um .docx pronto), com tipo de escrita, idioma, páginas × palavras por página e formatação.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { state } from '../main.js';
import { GROUP_LABEL, cancelJob, formatFields, labeled, numField, runJob } from '../scriber_ui.js';
import { teamPicker } from '../team_ui.js';
import { debounce, h, icon, select, toast } from '../ui.js';
import { createComposer } from './composer.js';

export default async function render(body, S) {
  const cat = S.cat, proj = S.proj, cfg = Object.assign({ web: false }, (state.settings || {}).scriber || {});
  const G = { type: proj.type, language: proj.language, pages: proj.gen.pages, wpp: proj.gen.words_per_page, chapters: proj.gen.chapters || 0, style: proj.gen.style || '', content: proj.content || cfg.content || '',
    mode: 'replace', web: !!cfg.web, format: JSON.parse(JSON.stringify(proj.format)), formatDirty: false };
  const T = () => cat.types[G.type];
  const hasText = async () => (await S.api.doc().catch(() => ({ stats: { words: 0 } }))).stats.words > 0;

  // ---------------------------------------------------------------- tipo de escrita
  const typeBox = h('div', { class: 'sc-types', id: 'sc-types', role: 'radiogroup', 'aria-label': t('Tipo de escrita') });
  const typeHint = h('div', { class: 'muted small', id: 'sc-type-hint' });
  const contentField = h('div', { class: 'sc-content-field' });
  function paintTypes() {
    typeBox.replaceChildren(...['fiction', 'professional', 'academic'].map((g) => h('div', { class: 'sc-tgroup' }, h('div', { class: 'sc-tg-l' }, t(GROUP_LABEL[g])),
      h('div', { class: 'sc-tg-b' }, Object.entries(cat.types).filter(([, v]) => v.group === g).map(([k, v]) => h('button', { type: 'button', role: 'radio', 'aria-checked': String(G.type === k), class: 'sc-typebtn' + (G.type === k ? ' on' : ''), dataset: { type: k }, title: t(v.hint),
        onclick: () => pick(k) }, t(v.label)))))));
    typeHint.textContent = t(T().hint);
    contentField.replaceChildren(T().mature ? labeled(t('Conteúdo'), select([['', t('Seguir a configuração do Scriber')], ['free', t('Livre (SFW e NSFW, para adultos)')], ['sfw', t('Só SFW')]], G.content, (v) => { G.content = v; }, { id: 'sc-gen-content' }),
      t('Os limites fixos não mudam: nada sexual com menores nem com pessoas reais.')) : null);
  }
  function pick(k) {
    G.type = k;
    const d = cat.types[k];
    if (!G.formatDirty) { G.format = Object.assign(JSON.parse(JSON.stringify(cat.presets[d.preset])), { preset: d.preset, header: G.format.header, author: G.format.author, subtitle: G.format.subtitle }); paintFormat(); }
    G.wpp = d.wpp; G.pages = d.pages; pagesIn.value = G.pages; wppIn.value = G.wpp;
    paintTypes(); estimate();
  }

  // ---------------------------------------------------------------- tamanho
  const pagesIn = numField(G.pages, (v) => { G.pages = Math.max(1, Math.round(v)); estimate(); }, { min: 1, max: cat.limits.max_pages, step: 1, id: 'sc-gen-pages' });
  const wppIn = numField(G.wpp, (v) => { G.wpp = Math.max(50, Math.round(v)); estimate(); }, { min: 50, max: cat.limits.max_words_per_page, step: 10, id: 'sc-gen-wpp' });
  const chapIn = numField(G.chapters, (v) => { G.chapters = Math.max(0, Math.round(v)); estimate(); }, { min: 0, max: 60, step: 1, id: 'sc-gen-chapters' });
  const sizeInfo = h('div', { class: 'sc-sizeinfo', id: 'sc-gen-size' });
  let team = null, promptText = proj.gen.prompt || '';
  const estimate = debounce(async () => {
    const words = G.pages * G.wpp;
    sizeInfo.textContent = t('Meta: {w} palavras ({p} páginas × {c})', { w: Math.min(words, cat.limits.max_target_words), p: G.pages, c: G.wpp });
    try {
      const e = await api('/api/scriber/estimate', { method: 'POST', body: { prompt: promptText, type: G.type, language: G.language, pages: G.pages, words_per_page: G.wpp, chapters: G.chapters, team: team ? team.get() : {} } });
      sizeInfo.textContent = t('Meta: {w} palavras ({p} páginas × {c}) · {s} seção(ões) · cerca de {n} chamada(s) à IA', { w: e.target_words, p: e.pages, c: e.words_per_page, s: e.sections, n: e.calls }) + (e.from_outline ? ' · ' + t('usando o seu esboço') : '');
    } catch (err) { /* sem estimativa: segue */ }
  }, 300);

  // ---------------------------------------------------------------- idioma, estilo, modo
  const langSel = select(Object.entries(cat.languages).map(([k, v]) => [k, t(v)]), G.language, (v) => { G.language = v; estimate(); }, { id: 'sc-gen-lang' });
  const styleIn = h('input', { id: 'sc-gen-style', value: G.style, maxlength: 600, placeholder: t('ex.: primeira pessoa, humor seco, frases curtas, tom sensual…') });
  styleIn.addEventListener('input', () => { G.style = styleIn.value; });
  const modeSel = select([['replace', t('Substituir o texto (o atual vai para o histórico)')], ['append', t('Acrescentar no fim do texto atual')]], G.mode, (v) => { G.mode = v; }, { id: 'sc-gen-mode' });
  const fmtBox = h('div', { id: 'sc-gen-format' });
  function paintFormat() { fmtBox.replaceChildren(formatFields(S, G.format, (f, preset) => { G.formatDirty = true; if (preset) paintFormat(); })); }
  paintFormat(); paintTypes();

  // ---------------------------------------------------------------- prompt (composer: anexos, web, equipe)
  const ai = S.status.text && S.status.text.ai;
  let web = G.web;
  const webBtn = h('button', { class: 'tool' + (web ? ' on' : ''), type: 'button', id: 'sc-gen-web', title: t('Busca na web nativa: o resultado entra no contexto da IA'), 'aria-pressed': String(web), onclick: () => { web = !web; webBtn.classList.toggle('on', web); webBtn.setAttribute('aria-pressed', String(web)); } }, icon('globe', 15), t('Web'));
  team = teamPicker(cfg, () => estimate(), { id: 'sc-gen-team' });
  const composer = createComposer({ placeholder: t('Descreva o texto, cole um esboço (títulos com #, «Capítulo 1: …», tópicos) ou anexe material — roteiros, pesquisas, PDFs, ZIPs…'), value: promptText, tools: [webBtn], rightTools: [team.el], sendLabel: t('Gerar texto'), sendTitle: t('Gerar o texto inteiro'), onSend: ({ text, ids }) => run(text, ids) });
  composer.el.id = 'sc-gen-composer';
  const ta = composer.el.querySelector('textarea'); if (ta) ta.addEventListener('input', () => { promptText = ta.value; estimate(); });

  // ---------------------------------------------------------------- progresso e resultado
  const out = h('div', { class: 'sc-out', id: 'sc-gen-out' });
  const aiBadge = h('div', { class: 'sc-aibadge ' + (ai ? 'ok' : 'warn'), id: 'sc-gen-ai', title: ai ? t('IA configurada') : t('Sem IA configurada: o Scriber monta a estrutura do texto. Configure em Configuração → Provedores.') },
    h('span', { class: 'dot' }), ai ? (S.status.text.label || 'IA') + (S.status.text.model ? ' · ' + S.status.text.model : '') : t('Modo regras (sem IA)'));

  async function run(text, ids) {
    if (!text.trim() && !(ids || []).length) { toast(t('Descreva o texto, cole um esboço ou anexe algo.')); return; }
    promptText = text;
    composer.setBusy(true, () => cancelJob(S));
    out.replaceChildren();
    const steps = h('div', { class: 'sc-steps' }), bar = h('div', { class: 'sc-bar-prog' }, h('i', { id: 'sc-gen-bar' })), line = h('div', { class: 'sc-progline', id: 'sc-gen-line' }), notes = h('div', { class: 'sc-pnotes' }), log = h('div', { class: 'sc-plog', id: 'sc-gen-log' });
    const card = h('div', { class: 'sc-card sc-prog', id: 'sc-gen-prog' }, h('h3', null, t('Gerando…')), steps, bar, line, notes, log);
    out.appendChild(card);
    const chips = {};
    const chip = (id, label) => { let c = chips[id]; if (!c) { c = chips[id] = h('span', { class: 'sc-step', dataset: { id } }, h('i'), label); steps.appendChild(c); } return c; };
    try {
      await S.api.put('', { type: G.type, language: G.language, content: G.content, format: G.format, gen: { prompt: text, pages: G.pages, words_per_page: G.wpp, style: G.style, chapters: G.chapters } });
      const res = await runJob(S, 'generate', { prompt: text, attachment_ids: ids || [], web, team: team.get(), type: G.type, language: G.language, pages: G.pages, words_per_page: G.wpp, chapters: G.chapters, style: G.style, content: G.content, mode: G.mode, format: G.format }, (ev) => {
        if (ev.type === 'start') { (ev.steps || []).forEach((s) => chip(s.id, s.label)); if (ev.warning) notes.appendChild(h('div', { class: 'sc-pnote warn' }, ev.warning)); }
        else if (ev.type === 'step') { const c = chip(ev.id, ev.label); c.className = 'sc-step ' + ev.status; if (ev.note) c.title = ev.note; if (ev.id.startsWith('write:') && ev.status !== 'running') log.appendChild(h('div', { class: 'sc-logrow ' + ev.status }, ev.label + (ev.note ? ' — ' + ev.note : ''))); }
        else if (ev.type === 'plan') { line.textContent = '✦ ' + ev.plan.title + ' · ' + t('{n} seção(ões)', { n: ev.plan.sections.length }) + ' · ' + t('{w} palavras', { w: ev.plan.target_words }); }
        else if (ev.type === 'progress') { const bi = document.getElementById('sc-gen-bar'); if (bi && ev.total) bi.style.width = Math.round((ev.done / ev.total) * 100) + '%'; line.textContent = t('{d} de {n} partes escritas · {w} de {m} palavras', { d: ev.done, n: ev.total, w: ev.words, m: ev.target }); }
        else if (ev.type === 'note') notes.appendChild(h('div', { class: 'sc-pnote' }, ev.message));
        else if (ev.type === 'sources') notes.appendChild(h('div', { class: 'sc-pnote' }, t('Fontes da web: {n}', { n: ev.sources.length }) + ' — ' + ev.sources.slice(0, 3).map((s) => s.host).join(', ')));
      });
      card.classList.add('done'); card.querySelector('h3').textContent = t('Pronto');
      showResult(res);
      S.proj = await S.refresh();
    } catch (e) { card.classList.add('err'); card.querySelector('h3').textContent = t('Não foi possível gerar'); notes.appendChild(h('div', { class: 'sc-pnote err' }, e.message)); toast(e.message, 'err'); }
    finally { composer.setBusy(false); composer.clearFiles(); }
  }

  function showResult(res) {
    const rep = res.report || {};
    const lines = [].concat(rep.warning ? [rep.warning] : [], (res.problems || []).slice(0, 6), (rep.warnings || []).slice(0, 3));
    out.appendChild(h('div', { class: 'sc-card sc-result', id: 'sc-gen-result' },
      h('h3', null, res.plan.title), res.plan.subtitle ? h('div', { class: 'muted' }, res.plan.subtitle) : null,
      h('p', { class: 'sc-summary' }, res.summary),
      h('div', { class: 'row sc-stats' }, h('span', { class: 'chip' }, t('{w} palavras', { w: res.stats.words })), h('span', { class: 'chip' }, t('≈ {p} páginas', { p: res.pages })), h('span', { class: 'chip dim' }, t('meta {w}', { w: res.target_words })),
        h('span', { class: 'chip dim' }, t('{n} seção(ões)', { n: res.plan.sections.length }))),
      lines.length ? h('ul', { class: 'sc-notes' }, lines.map((x) => h('li', null, x))) : null,
      res.sources && res.sources.length ? h('div', { class: 'small muted' }, t('Fontes da web usadas:') + ' ' + res.sources.slice(0, 5).map((s) => s.host).join(', ')) : null,
      h('div', { class: 'row', style: { marginTop: '12px' } },
        h('a', { class: 'btn primary', id: 'sc-gen-docx', href: S.api.download(res.docx.name), download: res.docx.name }, icon('download', 15), t('Baixar .docx')),
        h('button', { class: 'btn', id: 'sc-gen-open', type: 'button', onclick: () => S.go('edit') }, icon('edit', 15), t('Abrir na Edição')),
        h('span', { class: 'dim small' }, res.docx.name + ' · ' + Math.round(res.docx.size / 1024) + ' KB'))));
    out.lastChild.scrollIntoView({ block: 'nearest' });
  }

  // ---------------------------------------------------------------- montagem
  const card = (title, ...kids) => h('section', { class: 'sc-card' }, h('h3', null, title), ...kids);
  body.replaceChildren(h('div', { class: 'sc-gen' },
    h('div', { class: 'sc-gen-main' },
      h('div', { class: 'sc-gen-head' }, h('div', null, h('h2', null, t('Geração automática')), h('p', { class: 'muted' }, t('Descreva o texto, cole um esboço ou anexe material e escolha o tamanho: o Scriber planeja, escreve parte por parte, revisa e entrega o documento em .docx.'))), aiBadge),
      h('div', { class: 'sc-gen-prompt' }, composer.el),
      out),
    h('aside', { class: 'sc-gen-side' },
      card(t('Tipo de escrita'), typeBox, typeHint, contentField),
      card(t('Tamanho'), h('div', { class: 'grid3' }, labeled(t('Páginas'), pagesIn), labeled(t('Palavras por página'), wppIn), labeled(t('Seções / capítulos'), chapIn, t('0 = automático (ou o do seu esboço)'))), sizeInfo),
      card(t('Idioma, estilo e modo'), h('div', { class: 'grid2' }, labeled(t('Idioma'), langSel), labeled(t('Modo'), modeSel)), labeled(t('Estilo, voz e tom (opcional)'), styleIn), h('div', { class: 'hint' }, t('Os lorebooks do texto (aba Edição) entram automaticamente na escrita.'))),
      card(t('Formatação do documento'), fmtBox))));
  estimate();
}
