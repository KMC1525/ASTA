// Todas as telas abrem sem erro no desktop e no celular, sem rolagem horizontal; abas da configuração; modos do hub.
const { run } = require('./_common.js');
run('smoke', async ({ open, check }) => {
  for (const [label, vp] of [['desktop', { width: 1300, height: 860 }], ['mobile', { width: 390, height: 844 }]]) {
    const page = await open(vp);
    for (const r of ['main', 'worlds', 'avatars', 'avatars/edit/new', 'games', 'canvas', 'characters', 'worldbuilding', 'library', 'config']) {
      await page.evaluate((h) => { location.hash = '#/' + h; }, r); await page.waitForTimeout(450);
      check(`${label}:${r}:sem-erro`, (await page.locator('.errbox').count()) === 0);
      check(`${label}:${r}:sem-rolagem-horizontal`, !(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2)));
    }
    const tabs = await page.locator('.tabs button').count();
    for (let i = 0; i < tabs; i++) {
      await page.evaluate(() => { location.hash = '#/config'; }); await page.waitForTimeout(250);
      await page.locator('.tabs button').nth(i).click(); await page.waitForTimeout(350);
      check(`${label}:config-aba-${i}`, (await page.locator('.errbox').count()) === 0);
    }
    check(`${label}:abas-de-config`, tabs === 7);
    await page.close();
  }
  const page = await open();
  await page.evaluate(() => { location.hash = '#/main'; }); await page.waitForTimeout(500);
  check('hub:4-modos', (await page.locator('.modes .mode').count()) === 4);
  for (let i = 0; i < 4; i++) { await page.locator('.modes .mode').nth(i).click(); await page.waitForTimeout(350); check(`hub:modo-${i}-tem-compositor`, (await page.locator('.composer').count()) === 1); }
  await page.close();
});
