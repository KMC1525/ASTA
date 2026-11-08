// Todas as telas abrem sem erro no desktop e no celular, sem rolagem horizontal; abas da configuração; modos do hub.
const { run, useTool } = require('./_common.js');
run('smoke', async ({ open, check }) => {
  for (const [label, vp] of [['desktop', { width: 1300, height: 860 }], ['mobile', { width: 390, height: 844 }]]) {
    const page = await open(vp);
    for (const r of ['main', 'worlds', 'worlds/characters', 'worlds/worldbuilding', 'avatars', 'avatars/edit/new', 'games', 'canvas', 'studio', 'rebuild', 'library', 'config']) {
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
    check(`${label}:abas-de-config`, tabs === 17);
    await page.close();
  }
  const nav = await open();
  check('nav:sem-personagens-e-worldbuilding-soltos', (await nav.locator('#side nav a').count()) === 10);
  for (const [legacy, tab] of [['characters', 1], ['worldbuilding', 2]]) {
    await nav.evaluate((h) => { location.hash = '#/' + h; }, legacy); await nav.waitForTimeout(600);
    check(`legado:#/${legacy}-abre-a-aba-dentro-de-Mundos`, nav.url().endsWith('#/worlds/' + legacy) && (await nav.locator('.wtabs .tabs button.on').count()) === 1 && (await nav.locator('.wtabs .tabs button').nth(tab).getAttribute('class')) === 'on');
  }
  await nav.locator('.wtabs .tabs button').first().click(); await nav.waitForTimeout(500);
  check('abas-de-mundos:3', (await nav.locator('.wtabs .tabs button').count()) === 3 && nav.url().endsWith('#/worlds'));
  await nav.close();
  const page = await open();
  await page.evaluate(() => { location.hash = '#/main'; }); await page.waitForTimeout(500);
  check('chat:tela-principal-limpa', (await page.locator('.chx.empty').count()) === 1 && (await page.locator('.modes').count()) === 0 && (await page.locator('.composer').count()) === 1);
  for (const [i, id] of ['world', 'avatar', 'game', 'canvas'].entries()) { await useTool(page, id); check(`chat:ferramenta-${id}-tem-compositor`, (await page.locator('.composer').count()) === 1); }
  await page.close();
});
