// Personalização e experiência: tema (escuro/claro/auto), cor de destaque, escala, densidade, fonte, movimento, barra lateral, tela inicial,
// tecla de envio, paleta de comandos (Ctrl+K), atalhos, exportar/restaurar e acessibilidade básica.
const { run } = require('./_common.js');
run('customization', async ({ open, api, check, base, browser }) => {
  const av = await api('/api/avatars', { method: 'POST', body: { name: 'Zefira', age: 28, greeting: '' } });
  const chat = await api('/api/avatar-chats', { method: 'POST', body: { avatar_ids: [av.id] } });
  const page = await open();
  const attr = (n) => page.evaluate((k) => document.documentElement.getAttribute(k), n);
  const cssvar = (n) => page.evaluate((k) => document.documentElement.style.getPropertyValue(k).trim(), n);
  const go = async (hash) => { await page.evaluate((h) => { location.hash = h; }, hash); await page.waitForTimeout(500); };
  await go('#/config');
  await page.locator('.tabs button', { hasText: 'Appearance' }).click(); await page.waitForTimeout(500);

  // ---- tema
  check('cust:padrao-escuro', (await attr('data-theme')) === 'dark');
  await page.locator('.tabs button[data-tab="appearance"]').click(); await page.waitForTimeout(400);
  await page.locator('.themecard[data-theme="light"]').click(); await page.waitForTimeout(500);
  check('cust:tema-claro-no-html', (await attr('data-theme')) === 'light');
  check('cust:fundo-claro', (await page.evaluate(() => getComputedStyle(document.body).backgroundColor)) === 'rgb(246, 246, 244)');
  check('cust:salvo-no-servidor', (await api('/api/settings')).ui.theme === 'light');
  await page.goto(base + '/#/config', { waitUntil: 'domcontentloaded' });
  check('cust:aplica-antes-do-primeiro-quadro', (await attr('data-theme')) === 'light');  // boot.js, sem piscar de escuro
  await page.waitForTimeout(800);
  await page.locator('.tabs button', { hasText: 'Appearance' }).click(); await page.waitForTimeout(400);
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.locator('.themecard[data-theme="auto"]').click(); await page.waitForTimeout(400);
  check('cust:auto-segue-o-sistema-escuro', (await attr('data-theme')) === 'dark');
  await page.emulateMedia({ colorScheme: 'light' }); await page.waitForTimeout(300);
  check('cust:auto-muda-ao-vivo', (await attr('data-theme')) === 'light');
  await page.locator('.themecard[data-theme="dark"]').click(); await page.waitForTimeout(300);

  // ---- cor de destaque, escala, densidade, fonte, movimento
  await page.locator('.swatch[data-accent="#4f8cff"]').click(); await page.waitForTimeout(400);
  check('cust:cor-de-destaque', (await cssvar('--accent-custom')) === '#4f8cff' && (await cssvar('--on-accent-custom')) === '#fff');
  check('cust:botao-primario-usa-a-cor', (await page.evaluate(() => { const b = document.querySelector('.seg button.on'); return getComputedStyle(b).backgroundColor; })) === 'rgb(79, 140, 255)');
  await page.locator('.swatch[data-accent=""]').click(); await page.waitForTimeout(300);
  check('cust:cor-padrao-volta', (await cssvar('--accent-custom')) === '');
  await page.locator('.seg button', { hasText: '125%' }).click(); await page.waitForTimeout(300);
  check('cust:escala-125', (await cssvar('--z')) === '1.25' && (await page.evaluate(() => getComputedStyle(document.getElementById('app')).zoom)) === '1.25');
  check('cust:escala-sem-barra-de-rolagem-na-pagina', (await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight + 1)));
  await page.locator('.seg button', { hasText: '100%' }).click(); await page.waitForTimeout(300);
  await page.locator('.seg button', { hasText: 'Compact' }).click(); await page.waitForTimeout(300);
  check('cust:densidade-compacta', (await attr('data-density')) === 'compact');
  await page.locator('.seg button', { hasText: 'Comfortable' }).click(); await page.waitForTimeout(200);
  await page.locator('.seg button', { hasText: 'Serif' }).click(); await page.waitForTimeout(300);
  check('cust:fonte-serifada', (await page.evaluate(() => getComputedStyle(document.body).fontFamily)).includes('Georgia'));
  await page.locator('.seg button', { hasText: 'System' }).click(); await page.waitForTimeout(200);
  await page.locator('.seg button', { hasText: 'Large' }).click(); await page.waitForTimeout(300);
  check('cust:texto-do-chat-grande', (await attr('data-chat')) === 'large');
  await page.locator('.seg button', { hasText: 'Medium' }).click(); await page.waitForTimeout(200);
  await page.locator('select').filter({ has: page.locator('option', { hasText: 'Reduce animations' }) }).selectOption('reduce'); await page.waitForTimeout(300);
  check('cust:reduzir-animacoes', (await attr('data-motion')) === 'reduce' && (await page.evaluate(() => getComputedStyle(document.querySelector('.btn')).transitionDuration)).startsWith('1e-06'));
  await page.locator('select').filter({ has: page.locator('option', { hasText: 'Reduce animations' }) }).selectOption('auto'); await page.waitForTimeout(200);

  // ---- barra lateral e tela inicial (aba «Seções e atalhos»)
  await page.locator('.tabs button[data-tab="sections"]').click(); await page.waitForTimeout(400);
  await page.locator('label.check', { hasText: 'Game Engine' }).locator('input').uncheck(); await page.waitForTimeout(500);
  check('cust:barra-sem-jogos', (await page.locator('#side nav a[href="#/engine"]').count()) === 0 && (await page.locator('#side nav a[href="#/avatars"]').count()) === 1);
  check('cust:principal-e-config-nunca-somem', (await page.locator('#side nav a[href="#/main"]').count()) === 1 && (await page.locator('#side nav a[href="#/config"]').count()) === 1);
  await page.locator('label.check', { hasText: 'Game Engine' }).locator('input').check(); await page.waitForTimeout(400);
  check('cust:barra-volta', (await page.locator('#side nav a[href="#/engine"]').count()) === 1);
  await page.locator('select').filter({ has: page.locator('option', { hasText: 'The last screen I used' }) }).selectOption('library'); await page.waitForTimeout(400);
  const fresh = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  await fresh.goto(base + '/'); await fresh.waitForTimeout(1200);
  check('cust:tela-inicial-escolhida', (await fresh.evaluate(() => location.hash)) === '#/library');
  check('cust:titulo-da-pagina', (await fresh.title()) === 'ASTA — Library');
  await fresh.close();
  await api('/api/settings', { method: 'PUT', body: { ui: { start_page: 'main' } } });

  // ---- paleta de comandos e atalhos
  await go('#/main');
  await page.keyboard.press('Control+k'); await page.waitForSelector('.palette', { timeout: 5000 });
  check('cust:paleta-abre-com-ctrl-k', (await page.locator('.palette input').evaluate((el) => document.activeElement === el)));
  await page.locator('.palette input').fill('zefira');
  await page.waitForSelector('.palette-item:has-text("Chat with Zefira")', { timeout: 8000 }).catch(() => {});  // avatares/projetos chegam depois das telas
  check('cust:paleta-acha-avatar', (await page.locator('.palette-item', { hasText: 'Chat with Zefira' }).count()) === 1);
  await page.locator('.palette input').fill('canvas'); await page.waitForTimeout(300);
  await page.keyboard.press('Enter'); await page.waitForTimeout(500);
  check('cust:paleta-enter-navega', (await page.locator('.palette').count()) === 0 && (await page.evaluate(() => location.hash)).startsWith('#/canvas'));
  await page.keyboard.press('Control+k'); await page.waitForSelector('.palette'); await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  check('cust:esc-fecha-a-paleta', (await page.locator('.palette').count()) === 0);
  await page.keyboard.press('Control+k'); await page.locator('.palette input').fill('appearance'); await page.waitForTimeout(300);
  check('cust:paleta-acha-aba-da-config', (await page.locator('.palette-item', { hasText: 'Configuration → Appearance' }).count()) === 1);
  await page.keyboard.press('Escape');
  await go('#/main');
  await page.keyboard.press('Alt+Digit3'); await page.waitForTimeout(400);
  check('cust:atalho-alt-3', (await page.evaluate(() => location.hash)) === '#/scriber');
  await page.keyboard.press('Alt+Digit4'); await page.waitForTimeout(400);
  check('cust:atalho-alt-4', (await page.evaluate(() => location.hash)) === '#/data');   // o Data entrou na barra: Alt+4 agora é o Data
  await page.keyboard.press('Alt+Digit5'); await page.waitForTimeout(400);
  check('cust:atalho-alt-5', (await page.evaluate(() => location.hash)) === '#/avatars');
  await page.keyboard.press('Alt+KeyT'); await page.waitForTimeout(500);
  check('cust:atalho-alt-t-alterna-tema', (await attr('data-theme')) === 'light');
  await page.keyboard.press('Alt+KeyT'); await page.waitForTimeout(500);
  check('cust:atalho-alt-t-volta', (await attr('data-theme')) === 'dark');
  await page.keyboard.press('Shift+Slash'); await page.waitForSelector('.modal', { timeout: 3000 });
  check('cust:ajuda-de-atalhos', (await page.locator('.modal').innerText()).includes('Keyboard shortcuts'));
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  await api('/api/settings', { method: 'PUT', body: { ui: { shortcuts: false } } }); await page.reload(); await page.waitForTimeout(1000);
  await page.keyboard.press('Alt+Digit2'); await page.waitForTimeout(300);
  check('cust:atalhos-desligados', (await page.evaluate(() => location.hash)) !== '#/engine');
  await page.keyboard.press('Control+k'); await page.waitForTimeout(300);
  check('cust:ctrl-k-sempre-funciona', (await page.locator('.palette').count()) === 1);
  await page.keyboard.press('Escape');
  await api('/api/settings', { method: 'PUT', body: { ui: { shortcuts: true } } });

  // ---- tecla de envio no chat
  await api('/api/settings', { method: 'PUT', body: { ui: { send_key: 'ctrl_enter' } } });
  await page.evaluate((id) => { location.hash = '#/avatars/chat/' + id; }, chat.id); await page.reload(); await page.waitForTimeout(1000);
  const ta = page.locator('.chinput textarea');
  await ta.fill('primeira linha'); await ta.press('Enter'); await page.waitForTimeout(300);
  check('cust:ctrl-enter-enter-nao-envia', (await page.locator('.msg.me').count()) === 0 && (await ta.inputValue()).includes('primeira linha'));
  await ta.press('Control+Enter'); await page.waitForTimeout(1500);
  check('cust:ctrl-enter-envia', (await page.locator('.msg.me').count()) === 1);
  await api('/api/settings', { method: 'PUT', body: { ui: { send_key: 'enter' } } }); await page.reload(); await page.waitForTimeout(1000);
  await ta.fill('segunda'); await ta.press('Shift+Enter'); await page.waitForTimeout(200);
  check('cust:shift-enter-quebra-linha', (await page.locator('.msg.me').count()) === 1);
  await ta.press('Enter'); await page.waitForTimeout(1500);
  check('cust:enter-envia', (await page.locator('.msg.me').count()) === 2);

  // ---- exportar e restaurar
  await go('#/config');
  await page.locator('.tabs button[data-tab="data"]').click(); await page.waitForTimeout(400);
  const [dl] = await Promise.all([page.waitForEvent('download'), page.locator('.btn', { hasText: 'Export settings' }).click()]);
  const path = await dl.path(); const body = require('fs').readFileSync(path, 'utf8');
  check('cust:exporta-json-sem-segredos', JSON.parse(body).schema === 'asta.settings.v1' && !/"api_key"|"token"|"hf"/.test(body));
  await page.locator('.tabs button[data-tab="appearance"]').click(); await page.waitForTimeout(400);
  await page.locator('.themecard[data-theme="light"]').click(); await page.waitForTimeout(300);
  await page.locator('.btn', { hasText: 'Reset appearance defaults' }).click(); await page.waitForSelector('.modal');
  await page.locator('.modal .btn.danger').click(); await page.waitForTimeout(1500);
  check('cust:restaurar-padroes', (await attr('data-theme')) === 'dark' && (await api('/api/settings')).ui.theme === 'dark');

  // ---- acessibilidade básica
  check('cust:link-de-pular-para-o-conteudo', (await page.locator('a.skip').innerText()).length > 3);
  check('cust:botoes-de-icone-tem-nome', (await page.evaluate(() => [...document.querySelectorAll('button')].filter((b) => !b.textContent.trim() && b.title).every((b) => b.getAttribute('aria-label')))));
  await page.keyboard.press('Control+k'); await page.waitForSelector('.palette');
  check('cust:paleta-e-um-dialogo', (await page.locator('.palette[role="dialog"]').count()) === 1 && (await page.locator('.palette-list[role="listbox"] [role="option"]').count()) > 5);
  await page.keyboard.press('Escape');
});
