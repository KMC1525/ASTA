// Modelos locais do Canvas: a precisão (quantização) é escolhida ANTES do download; nada vem pré-selecionado.
const { run } = require('./_common.js');
run('local-models', async ({ open, check }) => {
  const page = await open();
  await page.route('**/api/media/local/quants**', (r) => r.fulfill({ json: { model: 'x/y', variants: [{ id: 'comunidade/modelo-nf4', size: 6e9, downloads: 10, kind: 'int4', loadable: true, note: '4 bits · pede a biblioteca bitsandbytes (placa NVIDIA)' }, { id: 'comunidade/modelo-gguf', size: 5e9, downloads: 9, kind: 'GGUF', loadable: false, note: 'formato que o carregador embutido não lê' }] } }));
  await page.evaluate(() => { location.hash = '#/config'; }); await page.waitForTimeout(400);
  await page.locator('.tabs button[data-tab="media"]').click(); await page.waitForTimeout(600);
  const card = page.locator('.prov:has(.nm:has-text("Hugging Face local"))');
  await card.locator('.hd').click();
  check('local:aviso-de-que-nada-baixa-sozinho', (await card.innerText()).toLowerCase().includes('only downloads after your choice'));
  check('local:comeca-como-nao-baixado', (await card.locator('.chip:has-text("not downloaded")').count()) >= 1);
  await card.locator('.btn:has-text("Precision and download")').first().click();
  await page.waitForSelector('.quant', { timeout: 10000 });
  check('local:3-precisoes-com-tamanho', (await page.locator('.quant:not(.qv)').count()) === 3 && (await page.locator('.quant:not(.qv) .chip.solid').allInnerTexts()).every((x) => /\d/.test(x)));
  check('local:nada-pre-selecionado', (await page.locator('.quant.on').count()) === 0 && (await card.locator('.btn.primary:has-text("Pick a precision")').isDisabled()));
  check('local:uma-recomendada', (await page.locator('.quant:not(.qv) .chip.on').count()) === 1);
  await page.waitForSelector('.quant.qv', { timeout: 10000 });
  check('local:quantizacoes-menores-listadas', (await page.locator('.quant.qv').count()) === 2 && (await page.locator('.quant.qv button:has-text("Use this one")').count()) === 1 && (await page.locator('.quant.qv', { hasText: 'not supported here' }).count()) === 1);
  await page.locator('.quant:has(b:text-is("fp16"))').click();
  check('local:botao-segue-a-escolha', (await card.locator('.btn.primary:has-text("fp16")').count()) === 1);
  await card.locator('.btn.primary:has-text("fp16")').click();
  await page.waitForSelector('.chip:has-text("downloaded · fp16")', { timeout: 20000 });
  check('local:baixado-na-precisao-escolhida', true);
});
