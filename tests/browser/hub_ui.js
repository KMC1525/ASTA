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
  // avatar a partir de uma foto/arte: só a imagem, sem texto
  await page.locator('.result .btn').last().click(); await page.waitForTimeout(500);
  await page.locator('.modes .mode').nth(1).click(); await page.waitForTimeout(300);
  check('foto-base:opcao-existe', (await page.locator('.composer .tool:has-text("Photo/art as base")').count()) === 1);
  await page.locator('.composer .tool:has-text("Photo/art as base")').click(); await page.waitForTimeout(200);
  check('foto-base:escolha-um-por-imagem-ou-uma-pessoa', (await page.locator('.composer .seg button').count()) >= 2 && (await page.locator('.home').innerText()).includes('always stay SFW'));
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
  await page.locator('.composer input[type=file]').setInputFiles({ name: 'rita_vermelha.png', mimeType: 'image/png', buffer: png });
  await page.waitForTimeout(800);
  await page.locator('.composer .send').click(); await page.waitForSelector('.result', { timeout: 90000 });
  check('foto-base:avatar-criado-so-com-a-imagem', (await page.locator('.result').innerText()).includes('Rita Vermelha'));
  await page.evaluate(() => { location.hash = '#/library'; }); await page.waitForTimeout(800);
  check('biblioteca:mostra-jogo-e-avatar', (await page.locator('.proj').count()) >= 2);
  await page.evaluate(() => { location.hash = '#/main'; }); await page.waitForTimeout(500);
  await page.locator('.modes .mode').nth(3).click(); await page.waitForTimeout(300);
  await page.selectOption('.composer select', 'image_video'); await page.fill('.composer textarea', 'Um robô pintando um mural');
  await page.locator('.composer .send').click(); await page.waitForSelector('.cv-node', { timeout: 10000 });
  check('canvas-pelo-hub:3-nos', (await page.locator('.cv-node').count()) === 3);
});
