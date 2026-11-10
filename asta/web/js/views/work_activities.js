// Work → Atividades: o registro constante do que começou, está continuando e terminou — o seu e o da equipe — e o resumo do dia/semana feito pela IA.
import { ACT_STATE, api, avatarEl, chip, fmtAgo, fmtElapsed, fmtWhen, h, icon, statusTone, t, toast, userName } from '../work_ui.js';
import { fill, select } from '../ui.js';
import { teamPicker } from '../team_ui.js';
import { state } from '../main.js';

export default async function render(box, W) {
  const S = { who: W.me.user.id, st: '', auto: true, acts: [] };
  const quick = h('input', { id: 'wk-act-title', placeholder: t('O que você vai fazer agora?'), maxlength: 160 });
  const startBtn = h('button', { class: 'btn primary', type: 'button', id: 'wk-act-start', onclick: start }, icon('play', 14), t('Começar'));
  quick.addEventListener('keydown', (e) => { if (e.key === 'Enter') start(); });
  const mine = h('div', { id: 'wk-act-mine' }), feed = h('div', { id: 'wk-act-feed' }), digestBox = h('div', { id: 'wk-digest' });
  const filters = h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap', margin: '0 0 10px' } });
  box.replaceChildren(h('div', { class: 'wk-two' }, h('div', { class: 'wk-col' },
    h('div', { class: 'card' }, h('h3', null, t('Registrar atividade')), h('div', { class: 'row' }, quick, startBtn), h('p', { class: 'dim small', style: { marginBottom: 0 } }, t('Comece uma atividade, registre o andamento e conclua. Enquanto esta aba estiver aberta, o ASTA avisa a equipe que você continua nela.')), h('div', { style: { marginTop: '10px' } }, mine)),
    h('div', { class: 'card' }, h('h3', null, t('Linha do tempo')), filters, feed)), h('div', { class: 'wk-col' }, digestPanel(), digestBox)));

  async function start() {
    if (!quick.value.trim()) return;
    try { await api('/api/work/activities', { method: 'POST', body: { title: quick.value } }); quick.value = ''; await load(); } catch (e) { toast(e.message, 'err'); }
  }
  async function op(a, kind, note) { try { await api(`/api/work/activities/${a.id}/${kind}`, { method: 'POST', body: { note: note || '' } }); await load(); } catch (e) { toast(e.message, 'err'); } }

  function activeCard(a) {
    const note = h('input', { placeholder: t('Registrar o andamento…'), class: 'wk-note-in', dataset: { id: a.id } });
    note.addEventListener('keydown', (e) => { if (e.key === 'Enter' && note.value.trim()) op(a, 'progress', note.value); });
    const last = (a.log || []).filter((l) => l.text).slice(-1)[0];
    return h('div', { class: 'wk-act', dataset: { id: a.id, state: a.state } }, h('div', { class: 'row', style: { justifyContent: 'space-between', gap: '8px' } }, h('b', null, a.title), chip(ACT_STATE()[a.state], statusTone(a.state))),
      h('div', { class: 'small dim' }, h('span', { class: 'wk-timer', dataset: { start: a.started, paused: a.state === 'paused' ? '1' : '' } }, fmtElapsed(a.elapsed)), last ? ' · ' + last.text : ''),
      h('div', { class: 'row', style: { gap: '6px', marginTop: '6px' } }, note,
        a.state === 'paused' ? h('button', { class: 'btn sm', type: 'button', dataset: { op: 'resume' }, onclick: () => op(a, 'progress') }, icon('play', 12), t('Retomar')) : h('button', { class: 'btn sm', type: 'button', dataset: { op: 'pause' }, onclick: () => op(a, 'pause') }, icon('pause', 12), t('Pausar')),
        h('button', { class: 'btn sm primary', type: 'button', dataset: { op: 'finish' }, onclick: () => op(a, 'finish', note.value) }, icon('check', 12), t('Concluir')),
        h('button', { class: 'btn sm ghost', type: 'button', title: t('Cancelar a atividade'), dataset: { op: 'cancel' }, onclick: () => op(a, 'cancel') }, icon('x', 12))));
  }
  function paintMine() {
    const open = S.acts.filter((a) => a.user === W.me.user.id && ['started', 'continuing', 'paused'].includes(a.state));
    fill(mine, ...(open.length ? open.map(activeCard) : [h('div', { class: 'dim small' }, t('Nenhuma atividade em andamento.'))]));
  }
  function paintFilters() {
    const people = [[W.me.user.id, t('Eu')], ...(W.can('activities.view_all') ? [['', t('Todas as pessoas')], ...W.dir.users.filter((u) => u.id !== W.me.user.id).map((u) => [u.id, u.display_name || u.username])] : [])];
    const auto = h('input', { type: 'checkbox', checked: S.auto, id: 'wk-act-auto' }); auto.addEventListener('change', () => { S.auto = auto.checked; load(); });
    fill(filters, select(people, S.who, (v) => { S.who = v; load(); }, { id: 'wk-act-who' }), select([['', t('Todos os estados')], ...Object.entries(ACT_STATE())], S.st, (v) => { S.st = v; load(); }, { id: 'wk-act-state' }), h('label', { class: 'check' }, auto, h('span', null, t('Mostrar registros automáticos'))));
  }
  function paintFeed() {
    const rows = S.acts;
    fill(feed, ...(rows.length ? rows.map((a) => h('details', { class: 'wk-feed' + (a.auto ? ' auto' : ''), dataset: { id: a.id } }, h('summary', null, avatarEl(W.dir.users.find((u) => u.id === a.user), 24), h('span', { class: 'grow' }, h('b', null, userName(W.dir, a.user)), ' ', a.title),
      a.stale ? chip(t('sem sinal'), 'warn', t('Sem sinal há mais de 5 minutos')) : null, a.auto ? null : chip(ACT_STATE()[a.state], statusTone(a.state)), h('span', { class: 'small dim' }, fmtAgo(a.finished || a.beat || a.started))),
      h('ul', { class: 'small wk-log' }, (a.log || []).map((l) => h('li', null, fmtWhen(l.ts) + ' — ' + ({ start: t('começou'), progress: t('andamento'), continue: t('continuando'), pause: t('pausou'), finish: t('finalizou'), cancel: t('cancelou'), auto: t('registro') }[l.kind] || l.kind) + (l.text ? ': ' + l.text : '')))))) : [h('div', { class: 'dim small' }, t('Nada registrado ainda.'))]));
  }
  async function load() {
    try { S.acts = (await api(`/api/work/activities?user=${S.who}&state=${S.st}&auto=${S.auto ? 1 : 0}&limit=120`)).activities; } catch (e) { S.acts = []; toast(e.message, 'err'); }
    paintFilters(); paintMine(); paintFeed();
  }

  // ------------------------------------------------------------------ resumo com IA
  function digestPanel() {
    const scope = select([['me', t('Meu resumo')], ...(W.can('activities.view_all') ? [['org', t('Resumo da organização')]] : [])], 'me', () => {}, { id: 'wk-dg-scope' });
    const period = select([['day', t('Hoje')], ['week', t('Esta semana')], ['month', t('Este mês')]], 'day', () => {}, { id: 'wk-dg-period' });
    const team = teamPicker((state.settings && state.settings.work) || {}, null, { id: 'wk-dg' });
    const go = h('button', { class: 'btn primary', type: 'button', id: 'wk-dg-go', disabled: !W.can('ai.use'), onclick: async () => {
      go.disabled = true; fill(digestBox, h('div', { class: 'card' }, h('div', { class: 'spinner' })));
      try {
        const r = await api('/api/work/ai/digest', { method: 'POST', body: { scope: scope.value, period: period.value, ...team.get() } });
        const s = r.stats, list = (title, items) => items.length ? h('div', null, h('h4', null, title), h('ul', { class: 'small' }, items.map((x) => h('li', null, x)))) : null;
        fill(digestBox, h('div', { class: 'card', id: 'wk-dg-result' }, r.warning ? h('div', { class: 'small dim' }, r.warning) : null, h('p', null, r.summary),
          h('div', { class: 'wk-tiles small' }, [[s.activities, t('atividades')], [(s.by_state.finished || 0), t('concluídas')], [s.requests, t('pedidos')], [s.work_minutes, t('min. trabalhados')]].map(([n, l]) => h('div', { class: 'wk-tile static' }, h('b', null, String(n)), h('span', null, l)))),
          list(t('Destaques'), r.highlights), list(t('Atenção'), r.risks), list(t('Próximos passos'), r.next_steps)));
      } catch (e) { fill(digestBox, h('div', { class: 'errbox' }, e.message)); }
      go.disabled = !W.can('ai.use');
    } }, icon('wand', 14), t('Gerar resumo'));
    return h('div', { class: 'card' }, h('h3', null, t('Resumo com IA')), h('p', { class: 'muted small', style: { marginTop: 0 } }, t('Os números vêm dos registros, calculados pelo ASTA; a IA só escreve o texto. Sem IA configurada, o resumo sai por regras.')),
      h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap' } }, scope, period, team.el, go));
  }

  // relógio das atividades abertas + sinal de vida (a cada minuto avisa que você continua nelas)
  const tick = setInterval(() => {
    if (!document.body.contains(box)) { clearInterval(tick); clearInterval(beat); return; }
    box.querySelectorAll('.wk-timer').forEach((el) => { if (el.dataset.paused) return; el.textContent = fmtElapsed(Date.now() / 1000 - parseFloat(el.dataset.start)); });
  }, 1000);
  const beat = setInterval(async () => {
    if (!document.body.contains(box)) return;
    for (const a of S.acts.filter((x) => x.user === W.me.user.id && ['started', 'continuing'].includes(x.state))) { try { await api(`/api/work/activities/${a.id}/progress`, { method: 'POST', body: { note: '' } }); } catch (e) { /* encerrada em outra máquina */ } }
  }, 60000);

  await load();
  W.live(['activities'], load);
}
