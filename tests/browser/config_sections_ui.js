// v0.9: Configuração reorganizada — abas em grupos, padrões por seção (Studio/Rebuild/Canvas/Avatars/Jogos), atalhos, dados e restaurar.
const { run } = require('./_common.js');
run('config_sections', async ({ open, api, check }) => {
  await api('/api/settings/reset', { method: 'POST', body: { section: 'studio' } });
  const page = await open({ width: 1400, height: 950 });
  const go = async (tab) => { await page.locator(`.cfgtabs button[data-tab="${tab}"]`).click(); await page.waitForTimeout(500); };
  await page.evaluate(() => { location.hash = '#/config'; }); await page.waitForSelector('.cfgtabs', { timeout: 15000 });
  check('abas:quatro-grupos', (await page.locator('.cfgtabs .tg').count()) === 4 && (await page.locator('.cfgtabs button').count()) === 19);
  for (const id of ['appearance', 'sections', 'providers', 'media', 'voice', 'local', 'chat', 'generation', 'avatars', 'games', 'canvas', 'studio', 'rebuild', 'performance', 'data', 'mobile', 'system']) {
    await page.locator(`.cfgtabs button[data-tab="${id}"]`).click(); await page.waitForTimeout(450);
    const txt = await page.locator('.page.cfg').innerText();
    check(`aba:${id}-abre-sem-erro`, txt.length > 80 && (await page.locator('.cfgtabs button.on').getAttribute('data-tab')) === id && !/undefined|\[object/.test(txt));
  }
  // Studio: salvar padrões e ver o formulário de criação usá-los
  await page.locator('.cfgtabs button[data-tab="studio"]').click(); await page.waitForSelector('#cs-min');
  await page.fill('#cs-min', '3'); await page.fill('#cs-sec', '0');
  await page.locator('#cfg-save').click(); await page.waitForTimeout(800);
  const saved = (await api('/api/settings')).studio;
  check('studio:padroes-salvos', saved.target_seconds === 180);
  await page.evaluate(() => { location.hash = '#/studio'; }); await page.waitForSelector('#st-new', { timeout: 15000 });
  await page.waitForTimeout(400);
  check('studio:criacao-usa-os-padroes', /3\s*min|180/.test(await page.locator('#creator, .page').first().innerText()) || (await page.locator('input[type=number]').evaluateAll((els) => els.some((e) => e.value === '3' || e.value === '180'))));
  // Rebuild: desmarcar a revisão por padrão
  await page.evaluate(() => { location.hash = '#/config'; }); await page.waitForSelector('.cfgtabs'); await go('rebuild'); await page.locator('.page.cfg input[type=checkbox]').first().evaluate((e) => e.click()); await page.locator('#cfg-save').click(); await page.waitForTimeout(700);
  check('rebuild:padrao-sem-revisao', (await api('/api/settings')).rebuild.refine === false);
  // Restaurar padrões desta seção
  await go('rebuild'); await page.locator('#cfg-reset').click(); await page.waitForSelector('.modal'); await page.locator('.modal .btn.danger').click(); await page.waitForTimeout(1200);
  check('rebuild:restaurar-padroes-da-secao', (await api('/api/settings')).rebuild.refine === true);
  // Seções e atalhos: botões de salto levam à aba da seção
  await go('sections'); await page.locator('.cfg-jump[data-go="studio"]').click(); await page.waitForTimeout(600);
  check('secoes:atalho-leva-a-aba', (await page.locator('.cfgtabs button.on').getAttribute('data-tab')) === 'studio');
  // Dados: restaurar tudo
  await go('data'); check('dados:tem-pasta-e-backup', (await page.locator('#cfg-reset-all').count()) === 1);
});
