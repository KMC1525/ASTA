import { api, events } from '../api.js';
import { t } from '../i18n.js';
import { go, presetOf, state } from '../main.js';
import { h, icon } from '../ui.js';
import { KINDS } from './steps.js';

const JOB_KEY = 'asta.job';
export const saveJob = (info) => sessionStorage.setItem(JOB_KEY, JSON.stringify(info));
export const clearJob = () => sessionStorage.removeItem(JOB_KEY);
export const savedJob = () => JSON.parse(sessionStorage.getItem(JOB_KEY) || 'null');

// Acompanhamento ao vivo de um job multi-agentes (mundo, avatar ou jogo).
// info: { id, kind, prompt, project, ... } · hooks: { title, doneTitle, retry(), done(ev) → Node }
export function renderRun(root, jobId, info, hooks) {
  const defs = KINDS[info.kind || 'world'], STEPS = defs.steps;
  const st = {}; let order = Object.keys(STEPS); order.forEach((id) => (st[id] = { status: 'pending', detail: {}, t0: 0, t1: 0 }));
  const stepsEl = h('div', { class: 'steps' }), head = h('div'), extra = h('div');
  const actions = h('div', { class: 'row', style: { marginTop: '18px' } });
  let timer, finished = false; const revisions = [];
  const cancelBtn = h('button', { class: 'btn', onclick: async () => { await api('/api/jobs/' + jobId + '/cancel', { method: 'POST' }); cancelBtn.disabled = true; } }, t('Cancelar'));
  actions.append(cancelBtn);

  const iconFor = (s) => s === 'running' ? h('div', { class: 'spinner' }) : s === 'done' ? h('span', { class: 'ok' }, icon('check', 18)) : s === 'warn' ? h('span', { class: 'warn' }, icon('warn', 17)) : s === 'error' ? h('span', { class: 'err' }, icon('x', 18)) : s === 'skipped' ? h('span', { class: 'dim' }, '–') : h('span', { class: 'dim' }, '·');
  const secs = (x) => { const e = (x.t1 || Date.now()) - x.t0; return x.t0 ? (e / 1000).toFixed(e < 10000 ? 1 : 0) + 's' : ''; };
  const paint = () => {
    stepsEl.replaceChildren(...order.map((id) => { const s = st[id]; return h('div', { class: 'step ' + (s.status === 'pending' ? 'pending' : s.status) },
      h('div', { class: 'ic' }, iconFor(s.status)), h('div', null, h('div', { class: 'nm' }, t(STEPS[id][0])), h('div', { class: 'ds' }, s.status === 'pending' ? t(STEPS[id][1]) : defs.detail(id, s.status, s.detail))),
      h('div', { class: 'tm' }, secs(s))); }));
    extra.replaceChildren(...revisions.map((r) => h('div', { class: 'muted small', style: { marginTop: '10px' } }, t('Revisão {n}: o Revisor pediu {m} ajuste(s) — refazendo.', { n: r.round, m: r.issues }))));
  };
  head.replaceChildren(h('h2', null, hooks.title), h('div', { class: 'sub' }, t('Vários agentes de IA trabalham em etapas. Você pode sair desta tela: a geração continua.')));
  root.replaceChildren(h('div', { class: 'run' }, head, stepsEl, extra, actions));
  paint();
  timer = setInterval(() => { if (!finished) paint(); }, 500);

  const fail = (msg) => {
    finished = true; clearInterval(timer); clearJob(); cancelBtn.remove();
    actions.replaceChildren(h('button', { class: 'btn primary', onclick: hooks.retry }, t('Voltar e tentar de novo')), h('a', { class: 'btn', href: '#/config', onclick: () => { state.ctx = { tab: 'providers' }; } }, t('Ver provedores')));
    root.querySelector('.run').insertBefore(h('div', { class: 'errbox' }, msg), actions); paint();
  };

  events('/api/jobs/' + jobId + '/events', (ev) => {
    if (ev.type === 'start') {
      order = ev.steps; head.querySelector('.sub').textContent = presetOf(ev.provider).label + (ev.model && ev.model !== 'demo' ? ' · ' + ev.model : '') + (ev.tier ? ' · ' + t('hardware {t}', { t: ev.tier }) : '');
      order.forEach((id) => { if (!st[id]) st[id] = { status: 'pending', detail: {}, t0: 0, t1: 0 }; });
    } else if (ev.type === 'step') {
      const s = st[ev.id]; if (!s) return; s.status = ev.status; s.detail = ev.detail || {};
      if (ev.status === 'running') { s.t0 = s.t0 || Date.now(); s.t1 = 0; } else { s.t0 = s.t0 || Date.now(); s.t1 = Date.now(); }
    } else if (ev.type === 'revision') revisions.push(ev);
    else if (ev.type === 'error') { const bad = order.find((id) => st[id].status === 'running'); if (bad) { st[bad].status = 'error'; st[bad].t1 = Date.now(); } fail(ev.message); }
    else if (ev.type === 'cancelled') fail(t('Geração cancelada.'));
    else if (ev.type === 'done') done(ev);
    paint();
  }, () => {});

  async function done(ev) {
    finished = true; clearInterval(timer); clearJob(); cancelBtn.remove();
    const node = await hooks.done(ev);
    root.querySelector('.run').insertBefore(node, stepsEl); actions.remove(); node.scrollIntoView({ block: 'start' });
    head.querySelector('h2').textContent = hooks.doneTitle;
  }
}
