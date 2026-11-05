// Se um arquivo da tela não carrega (ex.: ASTA atualizado com a página aberta), a página se recupera sozinha ou explica o que fazer.
const { run } = require('./_common.js');
run('resilience', async ({ base, api, check, browser }) => {
  const mk = async () => { const ctx = await browser.newContext({ viewport: { width: 1300, height: 800 } }); return { ctx, page: await ctx.newPage() }; };

  // 1) o arquivo falha sempre: recarrega uma vez e então mostra a mensagem amigável com o botão de recarregar (sem laço de recarga)
  { const { ctx, page } = await mk(); let hits = 0;
    await page.route('**/js/model_labels.js', (route) => { hits++; route.abort(); });
    await page.goto(base + '/#/config'); await page.waitForSelector('.errbox', { timeout: 15000 }); await page.waitForTimeout(500);
    const txt = await page.locator('.errbox').innerText();
    check('res:mensagem-amigavel', txt.includes('could not be loaded') && txt.includes('Ctrl+F5'));
    check('res:botao-recarregar', (await page.locator('.errbox .btn:has-text("Reload the page")').count()) === 1);
    check('res:recarregou-uma-vez-so', hits >= 2 && hits <= 3);
    check('res:detalhe-tecnico-aparece', (await page.locator('.errbox .mono').innerText()).length > 5);
    await ctx.close(); }

  // 2) falha só na primeira vez: a recarga automática resolve e a Configuração abre normalmente
  { const { ctx, page } = await mk(); let n = 0;
    await page.route('**/js/model_labels.js', (route) => { n++; n === 1 ? route.abort() : route.continue(); });
    await page.goto(base + '/#/config'); await page.waitForSelector('.tabs', { timeout: 15000 });
    check('res:configuracao-abre-apos-recarga-automatica', (await page.locator('.tabs button').count()) >= 6 && (await page.locator('.errbox').count()) === 0);
    await ctx.close(); }

  // 3) o servidor avisa quando há uma versão mais nova em disco do que a que está rodando
  const st = await api('/api/state');
  check('res:estado-informa-versao-em-disco', typeof st.disk_version === 'string' && st.disk_version === st.version);
});
