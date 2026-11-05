// Boas-vindas: aparecem só numa instalação nova (nada criado ainda), deixam escolher tema/cor/idioma e nunca mais voltam; quem já usa o ASTA não vê.
const { chromium } = require('playwright');
const base = `http://127.0.0.1:${process.env.ASTA_PORT}`;
(async () => {
  const browser = await chromium.launch();
  const result = { checks: {}, errors: [] };
  const check = (k, v) => { result.checks[k] = !!v; };
  const api = async (path, opts = {}) => (await fetch(base + path, { ...opts, headers: { 'Content-Type': 'application/json' }, body: opts.body && JSON.stringify(opts.body) })).json();
  try {
    const page = await browser.newPage({ viewport: { width: 1200, height: 860 } });
    page.on('pageerror', (e) => result.errors.push('pageerror: ' + e.message));
    await page.goto(base + '/'); await page.waitForSelector('.modal', { timeout: 10000 });
    const txt = await page.locator('.modal').innerText();
    check('wel:modal-de-boas-vindas', txt.includes('Welcome to ASTA'));
    check('wel:avisa-que-esta-no-demo', txt.includes('No AI configured'));
    check('wel:tem-botao-configurar-ia', (await page.locator('.modal .btn', { hasText: 'Set up AI' }).count()) === 1);
    await page.locator('.modal .themecard[data-theme="light"]').click(); await page.waitForTimeout(400);
    check('wel:tema-muda-ao-vivo', (await page.evaluate(() => document.documentElement.dataset.theme)) === 'light');
    await page.locator('.modal .swatch[data-accent="#22c55e"]').click(); await page.waitForTimeout(300);
    check('wel:cor-muda-ao-vivo', (await page.evaluate(() => document.documentElement.style.getPropertyValue('--accent-custom'))) === '#22c55e');
    await page.locator('.modal .btn', { hasText: 'Explore in Demo' }).click(); await page.waitForTimeout(600);
    check('wel:fecha', (await page.locator('.modal').count()) === 0);
    const s = await api('/api/settings');
    check('wel:guardou-as-escolhas', s.ui.theme === 'light' && s.ui.accent === '#22c55e' && s.ui.welcome_done === true);
    await page.reload(); await page.waitForTimeout(1200);
    check('wel:nao-volta', (await page.locator('.modal').count()) === 0);
    // quem já usa o ASTA (tem algo criado) nunca vê as boas-vindas, mesmo sem a marca
    await api('/api/settings', { method: 'PUT', body: { ui: { welcome_done: false } } });
    await api('/api/avatars', { method: 'POST', body: { name: 'Aya', age: 26 } });
    await page.reload(); await page.waitForTimeout(1500);
    check('wel:usuario-antigo-nao-ve', (await page.locator('.modal').count()) === 0 && (await api('/api/settings')).ui.welcome_done === true);
    // "Rever as boas-vindas" na Configuração
    await page.evaluate(() => { location.hash = '#/config'; }); await page.waitForTimeout(500);
    await page.locator('.tabs button', { hasText: 'Appearance' }).click(); await page.waitForTimeout(400);
    await page.locator('.btn', { hasText: 'See the welcome again' }).click(); await page.waitForSelector('.modal', { timeout: 5000 });
    check('wel:rever-abre-de-novo', (await page.locator('.modal').innerText()).includes('Welcome to ASTA'));
    await page.keyboard.press('Escape');
  } catch (e) { result.errors.push('falhou: ' + e.message); }
  await browser.close();
  console.log(JSON.stringify(result));
})();
