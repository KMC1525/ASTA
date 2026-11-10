// v0.19.5 — timeline do Studio: bordas arrastáveis nos quatro lados das janelas, troca de lugar das janelas e presets de layout em JSON (guardar, exportar, importar).
const { run } = require('./_common.js');
const fs = require('fs'); const os = require('os'); const path = require('path');
run('studio_layout', async ({ open, api, check }) => {
  const page = await open({ width: 1700, height: 1000 });
  const p = await api('/api/studio/projects', { method: 'POST', body: { name: 'Layout', origin: 'manual', duration_type: 'custom', target_seconds: 30 } });
  await page.evaluate((id) => { location.hash = '#/studio/' + id + '/timeline'; }, p.id);
  await page.waitForSelector('.stl .stl-top', { timeout: 15000 }); await page.waitForTimeout(800);
  const lay = async () => page.evaluate(() => JSON.parse(localStorage.getItem('asta.stl.layout') || '{}'));
  const box = async (sel) => page.locator(sel).first().boundingBox();
  const dragBy = async (sel, dx, dy) => { await page.locator(sel).first().evaluate((e) => e.scrollIntoView({ block: 'center' })); const b = await box(sel); const x = b.x + b.width / 2, y = b.y + b.height / 2; await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x + dx / 2, y + dy / 2, { steps: 4 }); await page.mouse.move(x + dx, y + dy, { steps: 4 }); await page.mouse.up(); await page.waitForTimeout(250); };

  // ---- redimensionar: as divisórias e as quatro bordas de fora
  const mix0 = (await box('.stl-mixer')).width;
  await dragBy('#stl-gut-mixer', -90, 0);
  check('layout:mixer-ganha-largura-pela-divisoria', (await box('.stl-mixer')).width > mix0 + 60 && (await lay()).mixw > mix0);
  await dragBy('.stl-top .stl-edge.l', 60, 0); await dragBy('.stl-top .stl-edge.r', -40, 0); await dragBy('.stl-top .stl-edge.t', 0, 30); await dragBy('.stl-tlwrap .stl-edge.b', 0, -20);
  const L = await lay();
  check('layout:quatro-bordas-recuam-o-editor ' + JSON.stringify(L.inset), L.inset && L.inset.l >= 40 && L.inset.r >= 25 && L.inset.t >= 20 && L.inset.b >= 12);
  check('layout:recuo-aparece-nas-janelas', (await page.locator('.stl-top').evaluate((e) => parseFloat(getComputedStyle(e).paddingLeft))) >= 40);
  await page.locator('.stl-top .stl-edge.l').dblclick(); await page.locator('.stl-top .stl-edge.r').dblclick(); await page.locator('.stl-top .stl-edge.t').dblclick(); await page.locator('.stl-tlwrap .stl-edge.b').dblclick(); await page.waitForTimeout(250);
  const I0 = (await lay()).inset; check('layout:dois-cliques-zeram-os-recuos', I0.l === 0 && I0.r === 0 && I0.t === 0 && I0.b === 0);

  // ---- trocar de lugar
  const openMenu = async () => { if (!(await page.locator('#stl-lay-menu').count())) { await page.locator('#stl-layout').click(); await page.waitForSelector('#stl-lay-menu'); } };
  await openMenu();
  const lx = async () => (await box('#stl-dock-left')).x, rx = async () => (await box('#stl-dock-right')).x;
  check('layout:ordem-padrao-esquerda-antes-da-direita', (await lx()) < (await rx()));
  await page.locator('[data-swap="left-right"]').click(); await page.waitForTimeout(400);
  check('layout:troca-esquerda-direita', (await lx()) > (await rx()) && JSON.stringify((await lay()).order) === JSON.stringify(['right', 'center', 'left']));
  await page.locator('[data-swap="left-center"]').click(); await page.waitForTimeout(400);
  check('layout:troca-esquerda-centro', (await box('.stl-mons')).x > (await lx()) && (await box('.stl-mons')).x > (await rx()) && JSON.stringify((await lay()).order) === JSON.stringify(['right', 'left', 'center']));
  const gb = await box('#stl-gut-bin'); check('layout:divisoria-continua-visivel-depois-da-troca', gb && gb.width > 0);
  await page.locator('[data-swap="flip"]').click(); await page.waitForTimeout(400);
  check('layout:timeline-vai-para-cima', (await box('.stl-tlwrap')).y < (await box('.stl-top')).y && (await lay()).flip === true);
  await page.locator('[data-swap="mixer"]').click(); await page.waitForTimeout(400);
  check('layout:mixer-troca-de-lado', (await box('.stl-mixer')).x < (await box('.stl-scroll')).x && (await lay()).mixLeft === true);
  const hBefore = (await box('.stl-top')).height; await dragBy('#stl-gut-top', 0, 60);
  check('layout:divisoria-horizontal-funciona-com-a-timeline-em-cima', (await box('.stl-top')).height < hBefore - 30);
  const isoWidth = (await box('.stl-mixer')).width; await dragBy('#stl-gut-mixer', 50, 0);
  check('layout:divisoria-do-mixer-com-o-mixer-na-esquerda', (await box('.stl-mixer')).width > isoWidth + 30);

  // ---- presets em JSON: guardar no navegador, exportar, apagar layout, aplicar e importar
  await openMenu();
  await page.locator('#stl-preset-name').fill('Meu estúdio'); await page.locator('#stl-preset-save').click(); await page.waitForTimeout(300);
  check('preset:guardado-no-navegador', (await page.locator('.stl-preset').count()) === 1 && (await page.evaluate(() => JSON.parse(localStorage.getItem('asta.stl.presets')).length)) === 1);
  const [dl] = await Promise.all([page.waitForEvent('download'), page.locator('.stl-preset [data-act="export"]').click()]);
  const exported = JSON.parse(fs.readFileSync(await dl.path(), 'utf8'));
  check('preset:exporta-json-com-tipo-versao-e-layout', exported.kind === 'asta-studio-timeline-preset' && exported.version === 1 && exported.name === 'Meu estúdio' && exported.layout.flip === true && exported.layout.mixLeft === true && Array.isArray(exported.layout.order));
  check('preset:nome-do-arquivo', /timeline-meu-estudio\.json$/.test(dl.suggestedFilename()));
  await page.locator('#stl-lay-reset').click(); await page.waitForTimeout(400);
  const R = await lay(); check('preset:voltar-ao-padrao', R.flip === false && R.mixLeft === false && JSON.stringify(R.order) === JSON.stringify(['left', 'center', 'right']) && (await lx()) < (await rx()));
  await page.locator('.stl-preset [data-act="apply"]').click(); await page.waitForTimeout(500);
  const A = await lay(); check('preset:aplicar-restaura-o-layout', A.flip === true && A.mixLeft === true && JSON.stringify(A.order) === JSON.stringify(exported.layout.order) && exported.layout.order[0] === 'right');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'asta-preset-')), good = path.join(dir, 'ok.json'), bad = path.join(dir, 'bad.json'), evil = path.join(dir, 'evil.json');
  fs.writeFileSync(good, JSON.stringify({ kind: 'asta-studio-timeline-preset', version: 1, name: 'Importado', layout: { bin: 333, order: ['center', 'left', 'right'], flip: false, mixLeft: false, inset: { l: 20, r: 0, t: 0, b: 0 }, tools: { effects: true, sfx: false } }, timeline: { snap: false } }));
  fs.writeFileSync(bad, '{ isto não é json');
  fs.writeFileSync(evil, JSON.stringify({ kind: 'asta-studio-timeline-preset', version: 1, name: '<img src=x onerror=alert(1)>', layout: { bin: 'x', top: 1e12, order: ['left', 'left', 'left'], inset: { l: -50, r: 1e9 }, tools: { __proto__: { x: 1 }, nope: true }, tab: { left: '../x' } } }));
  await openMenu(); await page.locator('#stl-preset-file').setInputFiles(bad); await page.waitForTimeout(500);
  check('preset:json-invalido-e-recusado-sem-mudar-nada', (await lay()).bin !== 333 && /válido|valid/i.test(await page.locator('.toast').last().innerText()));
  await openMenu(); await page.locator('#stl-preset-file').setInputFiles(good); await page.waitForTimeout(600);
  const G = await lay(); check('preset:importar-aplica-e-limpa', G.bin === 333 && JSON.stringify(G.order) === JSON.stringify(['center', 'left', 'right']) && G.inset.l === 20 && G.tools.effects === true);
  await openMenu(); await page.locator('#stl-preset-file').setInputFiles(evil); await page.waitForTimeout(600);
  const V = await lay();
  check('preset:valores-absurdos-sao-limitados', V.top <= 1400 && V.inset.l === 0 && V.inset.r <= 400 && JSON.stringify(V.order.slice().sort()) === JSON.stringify(['center', 'left', 'right']) && !Object.keys(V.tools).includes('nope') && V.tab.left !== '../x');
  check('preset:nome-nao-vira-html', (await page.locator('img[src="x"]').count()) === 0);
  await openMenu(); await page.locator('.stl-preset [data-act="delete"]').first().click(); await page.waitForTimeout(300);
  check('preset:apagar', (await page.locator('.stl-preset').count()) === 0);
  await page.reload(); await page.waitForSelector('.stl .stl-top', { timeout: 15000 }); await page.waitForTimeout(600);
  check('layout:persiste-ao-recarregar', JSON.stringify((await lay()).order.slice().sort()) === JSON.stringify(['center', 'left', 'right']) && (await page.locator('.stl-top').count()) === 1);
});
