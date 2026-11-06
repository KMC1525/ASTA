// Studio: editar direto na timeline, sem gerar nem usar a edição automática.
const { run } = require('./_common.js');
run('studio_manual', async ({ open, api, check }) => {
  const page = await open({ width: 1500, height: 950 });
  await page.evaluate(() => { location.hash = '#/studio'; }); await page.waitForSelector('#st-tab-manual', { timeout: 15000 });
  check('modo:tres-formas-de-criar', (await page.locator('.st-modes button').count()) === 3);
  await page.locator('#st-tab-manual').click(); await page.waitForSelector('#st-manual-go');
  await page.fill('#st-manual-name', 'Meu corte'); await page.fill('#st-manual-secs', '45');
  await page.locator('#st-manual-go').click();
  await page.waitForSelector('.st-tlhost .stl-row', { timeout: 15000 }); await page.waitForTimeout(800);
  check('abre-direto-na-timeline-vazia', /#\/studio\/[\w-]+\/timeline/.test(page.url()) && (await page.locator('.st-tlhost').count()) === 1 && (await page.locator('.empty', { hasText: /empty|vazia/i }).count()) === 0);
  check('timeline-tem-trilhas-e-biblioteca-de-midias', (await page.locator('.stl-row').count()) >= 3 && (await page.locator('.stl-bin').count()) === 1);
  const list = await api('/api/studio/projects');
  const p = await api('/api/studio/projects/' + list.find((x) => x.name === 'Meu corte').id);
  check('projeto-manual-sem-geracao', p.origin === 'manual' && p.episodes.length === 1 && p.episodes[0].scenes.length === 0 && p.episodes[0].timeline.clips.length === 0 && p.target_seconds === 45);
  check('nenhum-job-de-ia-foi-iniciado', !(await api(`/api/studio/projects/${p.id}/job`)).job_id);
  await page.locator('.st-tabs button', { hasText: /Roteiro|Script/ }).first().click(); await page.waitForTimeout(400);
  await page.locator('.st-tabs button', { hasText: /Timeline/ }).first().click(); await page.waitForTimeout(600);
  check('volta-pra-timeline-sem-tela-vazia', (await page.locator('.st-tlhost').count()) === 1);
});
