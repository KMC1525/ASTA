// Modelos pré-instalados: o cartão aparece em Configuração → Modelos locais e instala com um clique.
const { run } = require('./_common.js');
run('preinstalled', async ({ open, check }) => {
  const page = await open();
  await page.evaluate(() => { location.hash = '#/config'; }); await page.waitForTimeout(400);
  await page.locator('.tabs button[data-tab="local"]').click(); await page.waitForTimeout(700);
  const card = page.locator('.card:has(h3:has-text("Pre-installed models"))');
  check('pre:cartao-existe', (await card.count()) === 1);
  const txt = await card.innerText();
  check('pre:texto-qwen-q8', txt.includes('Qwen3.8 2B Distill') && txt.includes('Q8_0'));
  check('pre:imagem-z-image-q4', txt.includes('Z-Image') && txt.includes('Q4_K_M'));
  check('pre:ensina-que-vem-com-quantizacao-definida', txt.includes('quantization already set'));
  check('pre:dois-botoes-instalar', (await card.locator('.btn:has-text("Install")').count()) === 2);
  await card.locator('.prerow:has-text("Qwen3.8") .btn:has-text("Install")').click();
  await page.waitForSelector('.prerow:has-text("Qwen3.8") .chip:has-text("Installed")', { timeout: 20000 });
  check('pre:instalou-com-um-clique', true);
  check('pre:aparece-em-baixados', (await page.locator('.row .mono:text-is("Qwen3.8-2B-Q8_0.gguf")').count()) === 1);
  check('pre:imagem-continua-nao-instalada', (await card.locator('.prerow:has-text("Z-Image") .btn:has-text("Install")').count()) === 1);
});
