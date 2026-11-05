// Hub: gerar um jogo 2D e um avatar pelo compositor (provedor Demo), ver na biblioteca e criar um canvas pelo modo Canvas.
const { run } = require('./_common.js');
run('hub', async ({ open, check }) => {
  const page = await open();
  await page.evaluate(() => { location.hash = '#/main'; }); await page.waitForTimeout(500);
  await page.locator('.modes .mode').nth(2).click(); await page.waitForTimeout(300);
  await page.fill('.composer textarea', 'Uma visual novel romântica num café, com escolhas e três finais');
  await page.locator('.composer .send').click(); await page.waitForSelector('.result', { timeout: 90000 });
  check('jogo:resultado-com-jogar-e-zip', (await page.locator('.result a[href*="/play/"]').count()) === 1 && (await page.locator('.result a[href*="download"]').count()) >= 1);
  await page.locator('.result .btn').last().click(); await page.waitForTimeout(500);
  await page.locator('.modes .mode').nth(1).click(); await page.waitForTimeout(300);
  await page.fill('.composer textarea', 'Uma amiga divertida e carinhosa chamada Luna, que adora astronomia');
  await page.locator('.composer .send').click(); await page.waitForSelector('.result', { timeout: 90000 });
  check('avatar:resultado-com-nome', (await page.locator('.result').innerText()).includes('Luna'));
  await page.evaluate(() => { location.hash = '#/library'; }); await page.waitForTimeout(800);
  check('biblioteca:mostra-jogo-e-avatar', (await page.locator('.proj').count()) >= 2);
  await page.evaluate(() => { location.hash = '#/main'; }); await page.waitForTimeout(500);
  await page.locator('.modes .mode').nth(3).click(); await page.waitForTimeout(300);
  await page.selectOption('.composer select', 'image_video'); await page.fill('.composer textarea', 'Um robô pintando um mural');
  await page.locator('.composer .send').click(); await page.waitForSelector('.cv-node', { timeout: 10000 });
  check('canvas-pelo-hub:3-nos', (await page.locator('.cv-node').count()) === 3);
});
