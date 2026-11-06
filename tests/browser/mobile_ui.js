// v0.10 Mobile: o app se adapta ao tipo de aparelho e à tela, oferece instalar, pergunta antes de atualizar e a aba «Celular e tablet» da Configuração funciona.
const { run } = require('./_common.js');
const { devices } = require('playwright');
run('mobile', async ({ browser, base, api, open, check }) => {
  await api('/api/settings', { method: 'PUT', body: { ui: { welcome_done: true } } });
  const ctx = async (opts) => { const c = await browser.newContext(opts); const p = await c.newPage(); await p.goto(base + '/'); await p.waitForSelector('#side nav', { timeout: 15000 }); return [c, p]; };
  const attrs = (p) => p.evaluate(() => { const d = document.documentElement.dataset; return { device: d.device, layout: d.layout, orient: d.orient, platform: d.platform, fold: d.fold }; });

  // ---- classificação do aparelho
  const [c1, phone] = await ctx({ ...devices['iPhone 13'] });
  let a = await attrs(phone);
  check('aparelho:iphone-e-celular-ios', a.device === 'phone' && a.platform === 'ios' && a.layout === 'compact' && a.orient === 'portrait');
  check('celular:barra-de-baixo', (await phone.evaluate(() => { const r = document.getElementById('side').getBoundingClientRect(); return r.top > innerHeight / 2 && r.width >= innerWidth - 2; })));
  check('celular:sem-rolagem-horizontal', !(await phone.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2)));
  check('celular:alvos-de-toque-grandes', (await phone.evaluate(() => { const b = document.querySelector('#side .item'); return b.getBoundingClientRect().height >= 44; })));
  await phone.setViewportSize({ width: 844, height: 390 }); await phone.waitForTimeout(300);
  a = await attrs(phone);
  check('celular:deitado-vira-coluna-lateral', a.orient === 'landscape' && (await phone.evaluate(() => { const r = document.getElementById('side').getBoundingClientRect(); return r.left <= 1 && r.width < 120 && r.height > 300; })));
  check('app:instalar-aparece-no-celular', (await phone.locator('.install-bar').count()) === 1 && /Compartilhar|Share/.test(await phone.locator('.install-bar').innerText()));
  await phone.locator('.install-bar button[aria-label]').click();
  await phone.reload(); await phone.waitForSelector('#side nav');
  check('app:instalar-nao-volta-depois-de-fechar', (await phone.locator('.install-bar').count()) === 0);
  await c1.close();

  const [c2, android] = await ctx({ ...devices['Pixel 7'] });
  a = await attrs(android);
  check('aparelho:pixel-e-celular-android', a.device === 'phone' && a.platform === 'android');
  await c2.close();

  const [c3, tablet] = await ctx({ ...devices['iPad (gen 7)'] });
  a = await attrs(tablet);
  check('aparelho:ipad-e-tablet', a.device === 'tablet' && a.platform === 'ios' && a.layout !== 'compact');
  check('tablet:sem-rolagem-horizontal', !(await tablet.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2)));
  await c3.close();

  const [c4, fold] = await ctx({ viewport: { width: 717, height: 840 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2.6, userAgent: 'Mozilla/5.0 (Linux; Android 14; SM-F946B) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36' });
  a = await attrs(fold);
  check('aparelho:galaxy-fold-aberto-e-dobravel', a.device === 'foldable' && a.fold === 'open' && a.layout === 'medium');
  await fold.setViewportSize({ width: 360, height: 800 }); await fold.waitForTimeout(300);
  a = await attrs(fold);
  check('dobravel:fechado-vira-layout-compacto', a.device === 'foldable' && a.fold === 'closed' && a.layout === 'compact');
  await c4.close();

  const desktop = await open({ width: 1300, height: 860 });
  await desktop.waitForSelector('#side nav');
  check('aparelho:computador-continua-igual', (await attrs(desktop)).device === 'desktop' && (await desktop.locator('.install-bar').count()) === 0);

  // ---- aviso de versão nova: pergunta antes de atualizar (celular)
  const [c5, up] = await ctx({ ...devices['Pixel 7'] });
  await up.evaluate(() => { try { localStorage.setItem('asta.install.skip', '1'); } catch (e) { /* ok */ } });
  await up.route('**/api/version', (r) => r.fulfill({ json: { version: '99.0.0' } }));
  await up.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await up.waitForSelector('.modal', { timeout: 15000 });
  const txt = await up.locator('.modal').innerText();
  check('atualizacao:pergunta-com-a-versao-nova', /99\.0\.0/.test(txt) && /Update now|Atualizar agora/.test(txt) && /Later|Depois/.test(txt));
  await up.locator('.modal .btn', { hasText: /Later|Depois/ }).click(); await up.waitForTimeout(300);
  check('atualizacao:depois-fecha-sem-recarregar', (await up.locator('.modal').count()) === 0);
  await up.evaluate(() => document.dispatchEvent(new Event('visibilitychange'))); await up.waitForTimeout(600);
  check('atualizacao:nao-pergunta-de-novo-na-mesma-sessao', (await up.locator('.modal').count()) === 0);
  await up.unroute('**/api/version');
  await c5.close();

  // ---- Configuração → Celular e tablet
  await desktop.evaluate(() => { location.hash = '#/config'; }); await desktop.waitForSelector('.cfgtabs');
  await desktop.locator('.cfgtabs button[data-tab="mobile"]').click(); await desktop.waitForSelector('.mob-table', { timeout: 10000 });
  const t = await desktop.locator('.page.cfg').innerText();
  check('config:aba-celular-explica-asta-mobile', /asta mobile/.test(t) && /ARM64/.test(t) && /Snapdragon/.test(t) && /foldable|dobr/i.test(t));
  check('config:aba-celular-mostra-este-aparelho', (await desktop.locator('#mob-device').innerText()).length > 20);
  // o servidor de teste escuta só em localhost: sem QR (o QR aparece quando se abre com `asta mobile`)
  check('config:sem-qr-quando-so-localhost', (await desktop.locator('#mob-qr').count()) === 0);
  const manifest = await desktop.evaluate(async () => { const r = await fetch(document.querySelector('link[rel=manifest]').href); return r.json(); });
  check('pwa:manifest-linkado-e-valido', manifest.display === 'standalone' && manifest.icons.length >= 3);
  const sw = await desktop.evaluate(async () => { try { const r = await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready; return !!r.scope; } catch (e) { return String(e); } });
  check('pwa:service-worker-registra-em-localhost', sw === true);
});
