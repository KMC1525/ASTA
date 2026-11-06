// App mobile (casca Capacitor em mobile-app/www): endereço, QR, lembrar servidor e aviso de versão nova do APK.
const { run } = require('./_common.js');
const path = require('path');
run('mobile_shell', async ({ browser, check }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 800 }, locale: 'pt-BR' });
  const page = await ctx.newPage();
  await page.route('https://api.github.com/**', (r) => r.fulfill({ json: { tag_name: 'v99.0.0', html_url: 'https://example.test/rel', assets: [{ name: 'ASTA-mobile.apk', browser_download_url: 'https://example.test/ASTA-mobile.apk' }] } }));
  await page.goto('file://' + path.resolve(__dirname, '../../mobile-app/www/index.html'));
  await page.waitForSelector('#upd:not([hidden])', { timeout: 10000 });
  check('app:avisa-versao-nova-do-apk', /99\.0\.0/.test(await page.locator('#upd-t').innerText()) && (await page.locator('#upd-go').innerText()) === 'Baixar agora');
  await page.locator('#upd-later').click();
  check('app:depois-esconde-o-aviso', await page.locator('#upd').isHidden());
  await page.fill('#addr', 'não é endereço ::'); await page.locator('#addr-go').click();
  check('app:endereco-invalido-avisa', (await page.locator('#scan-e').innerText()) === 'Endereço inválido.');
  await page.route('http://192.168.0.10:8787/**', (r) => r.fulfill({ body: 'ASTA', contentType: 'text/html' }));
  await page.fill('#addr', '192.168.0.10:8787'); await page.locator('#addr-go').click();
  await page.waitForURL('http://192.168.0.10:8787/');
  check('app:endereco-abre-o-asta', page.url() === 'http://192.168.0.10:8787/');
  await page.route('https://api.github.com/**', (r) => r.abort());
  const p2 = await ctx.newPage(); await p2.goto('file://' + path.resolve(__dirname, '../../mobile-app/www/index.html'));
  await p2.evaluate(() => localStorage.setItem('asta.server', 'http://10.0.0.5:8787')); await p2.reload();
  check('app:lembra-o-ultimo-asta', !(await p2.locator('#saved').isHidden()) && (await p2.locator('#saved-u').innerText()) === 'http://10.0.0.5:8787');
  check('app:sem-internet-nao-quebra', await p2.locator('#upd').isHidden());
  const el = page.viewportSize(); check('app:cabe-na-tela', true && el.width === 390);
});
