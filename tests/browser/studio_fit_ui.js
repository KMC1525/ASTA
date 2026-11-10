// v0.19.6 — timeline do Studio em qualquer tamanho de janela e com layouts extremos: nada fica cortado ou fora de alcance.
// Regra: toda janela visível cabe dentro do editor; a timeline e o monitor mantêm um tamanho mínimo; o que não cabe (faixas do mixer, abas, editor inteiro em janela estreita) rola.
const { run } = require('./_common.js');
run('studio_fit', async ({ open, api, check }) => {
  const p = await api('/api/studio/projects', { method: 'POST', body: { name: 'Fit', origin: 'manual', duration_type: 'custom', target_seconds: 30 } });
  const page = await open({ width: 1920, height: 1080 });
  const states = {
    padrao: {},
    extremo: { mixw: 900, bin: 1200, insp: 1200, top: 1400, inset: { l: 400, r: 400, t: 400, b: 400 } },
    trocado: { order: ['right', 'center', 'left'], flip: true, mixLeft: true, mixw: 700 },
  };
  const probe = () => page.evaluate(() => {
    const root = document.querySelector('.stl'), host = document.querySelector('.st-tlhost'), r = root.getBoundingClientRect(), bad = [];
    const vis = (e) => e && !e.classList.contains('hidden') && getComputedStyle(e).display !== 'none' && e.offsetParent !== null;
    const inside = (name, e) => { if (!vis(e)) return; const b = e.getBoundingClientRect(); if (b.width < 1 || b.height < 1) { bad.push(name + ' sem tamanho'); return; } if (b.left < r.left - 1.5 || b.right > r.right + 1.5 || b.top < r.top - 1.5 || b.bottom > r.bottom + 1.5) bad.push(`${name} fora do editor [${Math.round(b.left - r.left)},${Math.round(r.right - b.right)},${Math.round(b.top - r.top)},${Math.round(r.bottom - b.bottom)}]`); };
    ['#stl-dock-left', '#stl-dock-right', '.stl-mons', '.stl-scroll', '.stl-mixer', '.stl-bar', '.stl-zbar'].forEach((sel) => inside(sel, document.querySelector(sel)));
    document.querySelectorAll('.stl-bar .stl-btn').forEach((b, i) => inside('botao-da-barra ' + i, b));
    const mons = document.querySelector('.stl-mons'); if (vis(mons)) { const m = mons.getBoundingClientRect(); document.querySelectorAll('.stl-trans .stl-btn').forEach((e, i) => { const b = e.getBoundingClientRect(); if (b.left < m.left - 1 || b.right > m.right + 1 || b.top < m.top - 1 || b.bottom > m.bottom + 1) bad.push('controle de reproducao ' + i + ' cortado'); }); }
    const w = (sel) => { const e = document.querySelector(sel); return vis(e) ? e.getBoundingClientRect().width : 999; };
    if (w('.stl-scroll') < 190) bad.push('timeline estreita demais: ' + Math.round(w('.stl-scroll')));
    if (w('.stl-mons') < 150) bad.push('monitor estreito demais: ' + Math.round(w('.stl-mons')));
    const strips = document.querySelector('.stl-strips'), mixer = document.querySelector('.stl-mixer');
    if (vis(mixer) && strips) { const cs = getComputedStyle(strips); if ((strips.scrollWidth > strips.clientWidth + 1 && !/auto|scroll/.test(cs.overflowX)) || (strips.scrollHeight > strips.clientHeight + 1 && !/auto|scroll/.test(cs.overflowY))) bad.push('faixas do mixer cortadas sem rolagem'); }
    const hs = getComputedStyle(host); if (r.width > host.clientWidth + 1 && !/auto|scroll/.test(hs.overflowX)) bad.push('editor mais largo que a janela e sem rolagem lateral');
    return { bad, rootW: Math.round(r.width), hostW: host.clientWidth };
  });
  const sizes = [[1920, 1080], [1366, 768], [1024, 700], [800, 600], [390, 844]];
  for (const [name, st] of Object.entries(states)) {
    for (const [W, H] of sizes) {
      await page.setViewportSize({ width: W, height: H });
      await page.evaluate(({ id, st }) => { localStorage.setItem('asta.stl.layout', JSON.stringify(st)); location.hash = '#/studio/' + id + '/timeline'; location.reload(); }, { id: p.id, st });
      await page.waitForSelector('.stl .stl-top', { timeout: 15000 }); await page.waitForTimeout(900);
      const r = await probe();
      check(`fit:${name}:${W}x${H}${r.bad.length ? ' ' + r.bad.join('; ') : ''}`, r.bad.length === 0);
    }
  }
  // redimensionar a janela com o editor aberto reajusta as janelas (sem recarregar)
  await page.setViewportSize({ width: 1600, height: 900 }); await page.evaluate(({ id }) => { localStorage.setItem('asta.stl.layout', JSON.stringify({ bin: 600, insp: 600 })); location.hash = '#/studio/' + id + '/timeline'; location.reload(); }, { id: p.id });
  await page.waitForSelector('.stl .stl-top'); await page.waitForTimeout(800);
  await page.setViewportSize({ width: 1000, height: 800 }); await page.waitForTimeout(700);
  const r2 = await probe(); check('fit:redimensionar-a-janela-reajusta' + (r2.bad.length ? ' ' + r2.bad.join('; ') : ''), r2.bad.length === 0);
});
