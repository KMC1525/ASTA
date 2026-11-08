// Computer Use — a seção lateral que acompanha as tarefas que a equipe de agentes está fazendo no seu computador (até 8 ao mesmo tempo) e guarda o histórico passo a passo das anteriores.
import { api } from '../api.js';
import { t } from '../i18n.js';
import { saveSettings, state } from '../main.js';
import { renderMarkdown } from '../markdown.js';
import { AGENT, MODE, MODE_HINT, RISK, STATUS, STEP_STATUS, TOOL_ICON, approvalCard, describeAction, fmtClock, fmtDur, fmtWhen, isActive, modeChip, statusChip, subscribe } from '../computer_ui.js';
import { confirmDialog, fill, h, icon, modal, seg, toast } from '../ui.js';
import { createComposer } from './composer.js';

const FULL_OK = 'asta.cu.fullok';
const lsGet = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ok */ } };
const idFromHash = () => { const m = location.hash.match(/^#\/computer\/([\w-]+)/); return m ? m[1] : ''; };
const cfg = () => (state.settings && state.settings.computer) || {};

export default async function render(root, ctx) {
  const st = { tasks: [], status: null, sel: (ctx && ctx.task) || idFromHash(), cur: null, filter: '', open: new Set(), mode: cfg().mode === 'full' ? 'full' : 'ask', inv: null };
  const listEl = h('aside', { class: 'cu-list', 'aria-label': t('Tarefas') });
  const mainEl = h('section', { class: 'cu-main', 'aria-live': 'polite' });
  const split = h('div', { class: 'cu-split' }, listEl, mainEl);
  const capBadge = h('span', { class: 'chip cu-cap', id: 'cu-cap' });
  root.replaceChildren(h('div', { class: 'page cu-page' },
    h('div', { class: 'page-h' }, h('div', null, h('h1', null, t('Computer Use')),
      h('p', null, t('Uma equipe de agentes de IA que faz tarefas no seu computador: arquivos e pastas, programas, jogos, pesquisa e escrita. Até 8 ao mesmo tempo.'))),
      h('div', { class: 'row' }, capBadge, h('a', { class: 'btn sm', href: '#/config', onclick: () => { state.ctx = { tab: 'computer' }; } }, icon('config', 13), t('Configurar')))),
    split));

  // ------------------------------------------------------------------ dados
  async function loadList() {
    try { const r = await api('/api/computer/tasks'); st.tasks = r.tasks; st.status = r.status; } catch (e) { toast(e.message, 'err'); }
    paintCap(); paintList();
  }
  async function loadCur(quiet) {
    if (!st.sel) { st.cur = null; return; }
    try { st.cur = await api('/api/computer/tasks/' + st.sel); } catch (e) { st.cur = null; if (!quiet) { toast(t('Tarefa não encontrada'), 'err'); st.sel = ''; } }
  }
  function paintCap() {
    const s = st.status || {}, n = (s.running || 0) + (s.waiting || 0), max = s.max_parallel || 8;
    capBadge.className = 'chip cu-cap' + (n ? ' busy' : '');
    capBadge.textContent = t('{n} de {m} em execução', { n, m: max }) + (s.queued ? ' · ' + t('{n} na fila', { n: s.queued }) : '');
  }

  // ------------------------------------------------------------------ lista (esquerda)
  function item(s) {
    const act = isActive(s.status);
    return h('button', { class: 'cu-item' + (st.sel === s.id ? ' on' : '') + (s.waiting ? ' ask' : ''), type: 'button', dataset: { id: s.id, status: s.status }, onclick: () => select(s.id) },
      h('span', { class: 'cu-dot ' + (s.waiting ? 'warn' : act ? 'info' : s.status === 'done' ? 'ok' : s.status === 'failed' ? 'err' : s.status === 'partial' ? 'warn' : 'dim') }, act && !s.waiting ? h('i', { class: 'pulse' }) : null),
      h('span', { class: 'grow' }, h('span', { class: 'cu-t' }, s.goal), h('span', { class: 'cu-s' }, s.waiting ? t('Aguardando você') : (STATUS()[s.status] || s.status), ' · ', fmtWhen(s.created), ' · ', MODE()[s.mode === 'full' ? 'full' : 'ask'],
        s.steps ? ' · ' + t('{n} passo(s)', { n: s.steps }) : '')));
  }
  function paintList() {
    const q = st.filter.trim().toLowerCase();
    const all = st.tasks.filter((x) => !q || x.goal.toLowerCase().includes(q));
    const act = all.filter((x) => isActive(x.status)), old = all.filter((x) => !isActive(x.status));
    const search = h('input', { type: 'search', id: 'cu-filter', placeholder: t('Buscar nas tarefas…'), value: st.filter, 'aria-label': t('Buscar nas tarefas…') });
    search.addEventListener('input', () => { st.filter = search.value; const pos = search.selectionStart; paintList(); const again = listEl.querySelector('#cu-filter'); if (again) { again.focus(); try { again.setSelectionRange(pos, pos); } catch (e) { /* ok */ } } });
    fill(listEl,
      h('button', { class: 'btn primary cu-new', id: 'cu-new', type: 'button', onclick: () => select('') }, icon('plus', 15), t('Nova tarefa')),
      st.tasks.length > 6 || st.filter ? search : null,
      act.length ? h('div', { class: 'cu-grp' }, t('Em andamento')) : null, ...act.map(item),
      old.length ? h('div', { class: 'cu-grp' }, t('Histórico')) : null, ...old.map(item),
      !all.length ? h('div', { class: 'dim small cu-none' }, st.tasks.length ? t('Nada encontrado.') : t('Nenhuma tarefa ainda. As tarefas e o passo a passo de cada uma ficam aqui.')) : null,
      old.length && !st.filter ? h('button', { class: 'btn sm ghost danger', id: 'cu-clear', type: 'button', onclick: clearHistory }, icon('trash', 13), t('Limpar o histórico')) : null);
  }
  async function clearHistory() {
    const purge = h('input', { type: 'checkbox', id: 'cu-purge' });
    const v = await modal(t('Limpar o histórico'), h('div', null, h('p', { class: 'muted', style: { marginTop: 0 } }, t('Apaga o registro das tarefas terminadas (passo a passo e capturas de tela). O que elas fizeram nos seus arquivos continua como está; depois disto não dá mais para desfazer.')),
      h('label', { class: 'check' }, purge, h('span', null, t('Também esvaziar a lixeira do ASTA dessas tarefas (arquivos que elas "apagaram")')))), [{ label: t('Cancelar'), value: false }, { label: t('Limpar'), value: true, cls: 'danger' }]);
    if (v !== true) return;
    try { const r = await api('/api/computer/history/clear', { method: 'POST', body: { purge: purge.checked } }); toast(t('{n} tarefa(s) apagada(s)', { n: r.deleted }), 'ok'); if (st.cur && !isActive(st.cur.status)) st.sel = ''; await loadList(); await show(); } catch (e) { toast(e.message, 'err'); }
  }
  async function select(id) {
    st.sel = id;
    history.replaceState(null, '', '#/computer' + (id ? '/' + id : ''));
    await loadCur(); paintList(); await show();
    mainEl.scrollTop = 0;
  }

  // ------------------------------------------------------------------ painel principal
  async function show() {
    split.dataset.sel = st.sel ? '1' : '0';
    if (!st.sel) return paintNew();
    if (!st.cur) await loadCur();
    if (!st.cur) { st.sel = ''; return paintNew(); }
    paintTask();
  }

  // ----- nova tarefa
  async function paintNew() {
    const enabled = cfg().enabled === true;
    let inv = st.inv;
    if (!inv && enabled) { try { inv = st.inv = await api('/api/computer/inventory'); } catch (e) { inv = null; } }
    const caps = (st.status && st.status.capabilities) || {};
    const parts = [];
    if (!enabled) {
      parts.push(h('div', { class: 'card cu-onboard' }, h('h2', null, t('Ligue o Computer Use quando quiser')),
        h('p', { class: 'muted' }, t('É um recurso opcional: fica desligado até você ligar. Com ele, a IA que você escolheu no Chat faz tarefas no seu computador por você.')),
        h('ul', { class: 'cu-can' }, [t('Digitar e escrever textos, e pesquisar na web'), t('Usar programas instalados (Krita, OBS Studio, Audacity, o gerenciador de arquivos…)'), t('Organizar e criar arquivos de qualquer formato, pastas e subpastas'),
          t('Abrir e jogar jogos da Steam, do Lutris e de pastas do computador')].map((x) => h('li', null, x))),
        h('div', { class: 'cu-modes' }, h('div', null, h('b', null, 'Ask'), h('span', null, t('Pergunta Sim ou Não antes de cada ação que muda algo.'))), h('div', null, h('b', null, 'Full Access'), h('span', null, t('Executa tudo sem perguntar nada.')))),
        h('p', { class: 'dim small' }, t('Sempre valem, em qualquer modo: não toca em senhas, chaves nem nos dados do ASTA, não mexe em pastas do sistema, não roda shells nem scripts, e o que é "apagado" vai para uma lixeira do ASTA (dá para desfazer).')),
        h('div', { class: 'row' }, h('button', { class: 'btn primary', id: 'cu-enable', type: 'button', onclick: async () => { try { await saveSettings({ computer: { enabled: true } }); toast(t('Computer Use ligado'), 'ok'); paintNew(); } catch (e) { toast(e.message, 'err'); } } }, icon('check', 15), t('Ligar o Computer Use')))));
    } else {
      const modeSeg = seg([['ask', MODE().ask], ['full', MODE().full]], st.mode, async (v) => {
        if (v === 'full' && lsGet(FULL_OK) !== '1') {
          const ok = await confirmDialog(t('O modo Full Access executa tudo sem perguntar: criar, mover, mandar para a lixeira, abrir programas e jogos, digitar e clicar. Os limites de segurança do ASTA (senhas e chaves, pastas do sistema, dados do ASTA, shells e scripts) continuam valendo e as mudanças em arquivos podem ser desfeitas. Usar o Full Access?'), false, t('Usar Full Access'));
          if (!ok) { st.mode = 'ask'; paintNew(); return; }
          lsSet(FULL_OK, '1');
        }
        st.mode = v; hint.textContent = MODE_HINT()[v];
      });
      modeSeg.id = 'cu-mode';
      const hint = h('span', { class: 'dim small' }, MODE_HINT()[st.mode]);
      const composer = createComposer({ placeholder: t('Diga o que o computador deve fazer…'), sendLabel: t('Run'), sendTitle: t('Executar'),
        onSend: async ({ text, ids }) => {
          try {
            const r = await api('/api/computer/tasks', { method: 'POST', body: { goal: text, mode: st.mode, attachment_ids: ids } });
            composer.setText(''); composer.clearFiles(ids);
            toast(t('Tarefa iniciada'), 'ok');
            await loadList(); await select(r.task.id);
          } catch (e) { toast(e.message, 'err'); }
        } });
      const ex = [t('Organize minha pasta Downloads por tipo'), t('Crie as pastas Trabalho, Estudos e Lazer na Área de trabalho'), t('Pesquise as melhores configurações do OBS Studio para gravar gameplay e salve um resumo em Documentos'),
        t('Abra o Krita e crie uma tela nova de 1920x1080'), ...(inv && inv.games && inv.games.length ? [t('Abra o jogo {n}', { n: inv.games[0].name })] : [t('Abra o jogo que eu mais jogo na Steam')])];
      parts.push(h('div', { class: 'cu-new-card' }, h('h2', null, t('O que o computador deve fazer?')), composer.el,
        h('div', { class: 'row cu-modebar' }, h('span', { class: 'muted small' }, t('Modo')), modeSeg, hint),
        h('div', { class: 'suggest cu-ex' }, ex.map((x) => h('button', { type: 'button', onclick: () => { composer.setText(x); composer.focus(); } }, x.length > 70 ? x.slice(0, 68) + '…' : x)))));
    }
    if (enabled || st.status) {
      const capRow = (key, label) => { const c = caps[key] || {}; return h('li', { class: c.ok ? 'ok' : 'no' }, icon(c.ok ? 'check' : 'x', 13), h('span', null, label), c.ok ? (c.how ? h('span', { class: 'dim' }, ' · ' + c.how) : null) : h('span', { class: 'dim' }, ' · ' + (c.hint ? t(c.hint) : t('indisponível')))); };
      parts.push(h('div', { class: 'card cu-caps' }, h('h3', null, t('O que este computador permite')),
        h('ul', null, capRow('files', t('Arquivos e pastas')), capRow('open', t('Abrir arquivos e sites')), capRow('apps', t('Programas instalados')), capRow('screenshot', t('Ver a tela')), capRow('keyboard', t('Digitar e apertar teclas')), capRow('mouse', t('Mouse'))),
        inv ? h('p', { class: 'dim small', style: { margin: '8px 0 0' } }, t('{a} programa(s) e {g} jogo(s) encontrados neste computador.', { a: inv.apps, g: inv.game_count })) : null));
    }
    fill(mainEl, ...parts);
  }

  // ----- tarefa
  function agentsRow(task) {
    const by = Object.fromEntries((task.agents || []).map((a) => [a.id, a]));
    return h('div', { class: 'cu-team' }, ['planner', 'operator', 'verifier', 'reporter'].map((id, i) => {
      const a = by[id] || { status: 'pending' }, [name, desc] = AGENT()[id];
      return h('div', { class: 'cu-ag ' + a.status, dataset: { agent: id, status: a.status }, title: desc },
        h('span', { class: 'cu-ag-i' }, a.status === 'running' ? h('span', { class: 'spinner' }) : a.status === 'done' ? icon('check', 14) : a.status === 'warn' ? icon('warn', 14) : a.status === 'error' ? icon('x', 14) : h('span', { class: 'dim' }, String(i + 1))),
        h('b', null, name), h('span', { class: 'dim small' }, a.note ? a.note : (a.status === 'skipped' ? t('pulado') : desc)));
    }));
  }
  function planList(task) {
    const p = task.plan || {}, steps = p.steps || [];
    if (!steps.length && !p.summary) return null;
    return h('div', { class: 'card cu-plan' }, h('h3', null, t('Roteiro')), p.summary ? h('p', { class: 'muted', style: { margin: '0 0 10px' } }, p.summary) : null,
      h('ol', null, steps.map((s) => h('li', { class: s.status, dataset: { step: s.id } }, h('span', { class: 'cu-pi' }, s.status === 'done' ? icon('check', 13) : s.status === 'running' ? h('span', { class: 'spinner' }) : s.status === 'skipped' ? '–' : '·'), h('span', null, s.title)))),
      (p.assumptions || []).length ? h('p', { class: 'dim small', style: { margin: '10px 0 0' } }, t('Suposições:') + ' ' + p.assumptions.join(' · ')) : null,
      (p.risks || []).length ? h('p', { class: 'small', style: { margin: '4px 0 0', color: 'var(--warn)' } }, t('Atenção:') + ' ' + p.risks.join(' · ')) : null);
  }
  function stepEl(task, s) {
    const open = st.open.has(s.n);
    const dur = s.t1 && s.t0 ? fmtDur(s.t1 - s.t0) : (s.status === 'running' ? '…' : '');
    const label = s.tool === '—' ? t('Resposta da IA rejeitada') : describeAction(s.tool, s.args);
    const detail = h('div', { class: 'cu-sd' },
      s.thought ? h('p', { class: 'cu-th' }, icon('sparkle', 12), ' ', s.thought) : null,
      h('div', { class: 'cu-kv' }, h('b', null, t('Ferramenta')), h('span', { class: 'mono' }, s.tool), h('b', null, t('Risco')), h('span', null, RISK()[s.risk] || s.risk),
        s.plan_step ? h('b', null, t('Etapa')) : null, s.plan_step ? h('span', null, s.plan_step) : null, h('b', null, t('Hora')), h('span', null, fmtClock(s.t0))),
      Object.keys(s.args || {}).length ? h('pre', { class: 'cu-pre' }, JSON.stringify(s.args, null, 2)) : null,
      s.output ? h('pre', { class: 'cu-pre out ' + s.status }, s.output) : null,
      s.approval ? h('p', { class: 'dim small' }, s.approval.answer ? t('Você aprovou esta ação.') : t('Você negou esta ação.')) : null,
      s.shot ? h('img', { class: 'cu-shot', loading: 'lazy', alt: t('Captura de tela'), src: `/api/computer/tasks/${task.id}/shots/${s.shot}`, onclick: () => modal(t('Captura de tela'), h('img', { class: 'cu-shot big', src: `/api/computer/tasks/${task.id}/shots/${s.shot}`, alt: '' }), [{ label: t('Fechar'), value: null, cls: 'primary' }]) }) : null);
    return h('div', { class: 'cu-step ' + s.status + (open ? ' open' : ''), dataset: { n: String(s.n), status: s.status } },
      h('button', { class: 'cu-sh', type: 'button', 'aria-expanded': String(open), onclick: (e) => { const el = e.currentTarget.parentElement; el.classList.toggle('open'); if (el.classList.contains('open')) st.open.add(s.n); else st.open.delete(s.n); } },
        h('span', { class: 'cu-sn' }, String(s.n)), h('span', { class: 'cu-si' }, icon(TOOL_ICON[s.tool] || 'file', 15)), h('span', { class: 'grow cu-sl' }, label),
        h('span', { class: 'cu-ss ' + s.status }, s.status === 'running' ? h('span', { class: 'spinner' }) : null, STEP_STATUS()[s.status] || s.status), h('span', { class: 'dim small cu-sd-t' }, dur), icon('chev', 14)),
      detail);
  }
  function paintTask() {
    const task = st.cur;
    if (!task) return;
    const act = isActive(task.status);
    const dur = (task.started ? (task.finished || Date.now() / 1000) - task.started : 0);
    const actions = h('div', { class: 'row cu-actions' },
      act ? h('button', { class: 'btn sm danger', id: 'cu-cancel', type: 'button', onclick: async () => { try { await api('/api/computer/tasks/' + task.id + '/cancel', { method: 'POST', body: {} }); } catch (e) { toast(e.message, 'err'); } } }, icon('stop', 13), t('Cancelar')) : null,
      !act && task.undo ? h('button', { class: 'btn sm', id: 'cu-undo', type: 'button', onclick: undo }, icon('undo', 13), t('Desfazer as mudanças em arquivos')) : null,
      !act ? h('button', { class: 'btn sm', id: 'cu-retry', type: 'button', onclick: retry }, icon('refresh', 13), t('Refazer')) : null,
      !act ? h('button', { class: 'btn sm ghost danger', id: 'cu-del', type: 'button', onclick: del }, icon('trash', 13), t('Apagar')) : null);
    const ask = approvalCard(task, () => { loadCur(true).then(paintTask); });
    const sum = !act && task.summary ? h('div', { class: 'card cu-sum' }, h('h3', null, t('Resumo')), (() => { const b = h('div', { class: 'md' }); renderMarkdown(b, task.summary); return b; })()) : null;
    const rv = task.review && !act ? h('div', { class: 'card cu-rev ' + task.review.verdict }, h('h3', null, t('Revisão')),
      h('div', { class: 'row' }, h('span', { class: 'cu-st ' + ({ pass: 'ok', partial: 'warn', fail: 'err' }[task.review.verdict] || 'dim') }, { pass: t('Aprovado'), partial: t('Parcial'), fail: t('Reprovado') }[task.review.verdict] || task.review.verdict), h('span', { class: 'dim small' }, t('nota {n}/10', { n: task.review.score }))),
      (task.review.issues || []).length ? h('ul', { class: 'cu-issues' }, task.review.issues.map((x) => h('li', null, x))) : null) : null;
    const files = (task.files || []).length ? h('div', { class: 'card cu-files' }, h('h3', null, t('Arquivos e pastas tocados')), h('ul', null, task.files.slice(0, 30).map((f) => h('li', { class: 'mono small' }, f))),
      task.files.length > 30 ? h('p', { class: 'dim small', style: { margin: '6px 0 0' } }, t('… e mais {n}', { n: task.files.length - 30 })) : null) : null;
    const steps = h('div', { class: 'cu-steps', id: 'cu-steps' }, (task.steps || []).length ? task.steps.map((s) => stepEl(task, s)) : [h('div', { class: 'dim small', style: { padding: '14px' } }, act ? t('Os passos aparecem aqui assim que começam.') : t('Nenhum passo foi executado.'))]);
    fill(mainEl,
      h('button', { class: 'btn sm ghost cu-back', type: 'button', onclick: () => select('') }, icon('stepback', 14), t('Tarefas')),
      h('div', { class: 'cu-head' }, h('h2', { id: 'cu-goal' }, task.goal),
        h('div', { class: 'row cu-meta' }, statusChip(task.status), modeChip(task.mode), task.provider && task.provider.label ? h('span', { class: 'chip' }, task.provider.label + (task.provider.model ? ' · ' + task.provider.model : '')) : null,
          task.team === 'rules' ? h('span', { class: 'chip', title: t('Sem IA: só pedidos simples, entendidos por regras') }, t('sem IA')) : null,
          h('span', { class: 'dim small', 'data-live-dur': task.started && act ? String(task.started) : '' }, dur ? fmtDur(dur) : ''), h('span', { class: 'dim small' }, fmtWhen(task.created))), actions),
      ask, task.note ? h('div', { class: 'chx-note' }, task.note) : null,
      (task.warnings || []).length ? h('div', { class: 'notice cu-warn', style: { textAlign: 'left' } }, '⚠ ' + task.warnings.slice(-3).join(' · ')) : null,
      sum, agentsRow(task), planList(task), rv,
      h('div', { class: 'card cu-timeline' }, h('h3', null, t('Passo a passo') + ' · ' + (task.steps || []).length), steps),
      files);
    if (act) { const box = mainEl.querySelector('#cu-steps'); if (box && box.lastElementChild && st.follow !== false) box.lastElementChild.scrollIntoView({ block: 'nearest' }); }
  }
  async function undo() {
    if (!(await confirmDialog(t('Desfazer o que esta tarefa fez nos seus arquivos? Pastas e arquivos criados são removidos, o que foi movido volta ao lugar e o que foi para a lixeira do ASTA é restaurado.'), false, t('Desfazer')))) return;
    try { const r = await api('/api/computer/tasks/' + st.sel + '/undo', { method: 'POST', body: {} }); toast(t('Desfeito'), 'ok'); st.cur = r.task; paintTask(); loadList(); }
    catch (e) { toast(e.message, 'err'); }
  }
  async function retry() {
    try { const r = await api('/api/computer/tasks/' + st.sel + '/retry', { method: 'POST', body: {} }); await loadList(); await select(r.task.id); }
    catch (e) { toast(e.message, 'err'); }
  }
  async function del() {
    const purge = h('input', { type: 'checkbox', id: 'cu-purge' });
    const v = await modal(t('Apagar a tarefa'), h('div', null, h('p', { class: 'muted', style: { marginTop: 0 } }, t('Apaga o registro e o passo a passo desta tarefa. O que ela fez nos seus arquivos continua como está (use "Desfazer" antes, se quiser reverter).')),
      h('label', { class: 'check' }, purge, h('span', null, t('Também esvaziar a lixeira do ASTA desta tarefa')))), [{ label: t('Cancelar'), value: false }, { label: t('Apagar'), value: true, cls: 'danger' }]);
    if (v !== true) return;
    try { await api('/api/computer/tasks/' + st.sel + (purge.checked ? '?purge=1' : ''), { method: 'DELETE' }); toast(t('Apagado'), 'ok'); st.sel = ''; st.cur = null; history.replaceState(null, '', '#/computer'); await loadList(); await show(); }
    catch (e) { toast(e.message, 'err'); }
  }

  // ------------------------------------------------------------------ ao vivo
  let pend = 0;
  const unsub = subscribe((ev) => {
    if (!root.isConnected) { unsub(); return; }
    if (ev.status) { st.status = ev.status; paintCap(); }
    if (ev.type === 'hello') { loadList(); if (st.sel) loadCur(true).then(paintTask); return; }
    if (ev.type !== 'task') return;
    const s = ev.task, i = st.tasks.findIndex((x) => x.id === s.id);
    if (i >= 0) st.tasks[i] = s; else st.tasks.unshift(s);
    st.tasks.sort((a, b) => String(b.created).localeCompare(String(a.created)));
    paintList();
    if (s.id === st.sel) { clearTimeout(pend); pend = setTimeout(async () => { await loadCur(true); if (st.sel && st.cur) paintTask(); }, 120); }
  });
  const tick = setInterval(() => {
    if (!root.isConnected) { clearInterval(tick); return; }
    const d = mainEl.querySelector('[data-live-dur]');
    if (d && d.dataset.liveDur) d.textContent = fmtDur(Date.now() / 1000 - Number(d.dataset.liveDur));
  }, 1000);

  await loadList();
  if (st.sel) await loadCur(true);
  await show();
}
