// Modelos locais: buscar, escolher a quantização, baixar (inclusive um modelo dividido em partes) e apagar.
const { run, until } = require('./_common.js');
run('models', async ({ open, check }) => {
  const page = await open();
  await page.evaluate(() => { location.hash = '#/config'; }); await page.waitForTimeout(400);
  await page.locator('.tabs button').nth(5).click(); await page.waitForTimeout(400);
  await page.locator('input[type=search]').fill('tiny'); await page.keyboard.press('Enter');
  await page.waitForSelector('.li', { timeout: 10000 });
  await page.locator('.li').first().click(); await page.waitForSelector('.quant', { timeout: 10000 });
  check('quants:lista-varias-opcoes', (await page.locator('.quant').count()) >= 6);
  check('quants:tem-rotulo-de-quantizacao', (await page.locator('.quant b').allInnerTexts()).includes('Q4_K_M'));
  check('quants:uma-recomendada', (await page.locator('.quant .chip.on').count()) === 1);
  check('quants:mmproj-fora-da-lista', !(await page.locator('.quant').allInnerTexts()).join('\n').includes('mmproj'));
  // nada vem escolhido: sem escolher a quantização não dá para baixar
  const dlBtn = page.locator('.btn.primary:has-text("quantiza"), .btn.primary:has-text("quantization")');
  check('quants:nada-pre-selecionado', (await page.locator('.quant.on').count()) === 0 && (await dlBtn.count()) === 1 && (await dlBtn.isDisabled()));
  // escolher outra quantização muda o botão de baixar
  if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT });
  await page.locator('.quant:has(b:text-is("Q8_0"))').click();
  check('quants:botao-segue-a-escolha', (await page.locator('.card .btn.primary, .col .btn.primary').last().innerText()).includes('Q8_0'));
  await page.locator('.quant:has(b:text-is("Q5_K_M"))').click();
  await page.locator('.btn.primary:has-text("Q5_K_M")').click();
  await page.waitForSelector('.modal');
  check('confirmacao:mostra-a-quantizacao-e-o-tamanho', (await page.locator('.modal').innerText()).includes('Q5_K_M'));
  await page.locator('.modal .foot .btn.primary').click();
  await page.waitForSelector('.mono:text-is("tiny-Q5_K_M.gguf")', { timeout: 15000 });
  await until(page, () => [...document.querySelectorAll('.row .mono')].some((e) => e.textContent === 'tiny-Q5_K_M.gguf' && e.closest('.row').querySelector('.chip')));
  check('baixados:mostra-a-quantizacao', (await page.locator('.row:has(.mono:text-is("tiny-Q5_K_M.gguf")) .chip').first().innerText()) === 'Q5_K_M');
  // modelo dividido em partes: baixa tudo e aparece uma vez
  await page.locator('.li').first().click(); await page.waitForSelector('.quant:has-text("3")', { timeout: 5000 });
  await page.locator('.quant:has(.chip:has-text("3"))').click();
  await page.locator('.btn.primary:has-text("Q4_K_M")').click();
  await page.waitForSelector('.modal'); await page.locator('.modal .foot .btn.primary').click();
  await until(page, () => [...document.querySelectorAll('.row .mono')].some((e) => e.textContent.startsWith('huge-Q4_K_M-00001')));
  check('baixados:modelo-dividido-uma-linha', (await page.locator('.row .mono:has-text("huge-Q4_K_M")').count()) === 1);
  check('baixados:marca-3-partes', (await page.locator('.row:has(.mono:has-text("huge")) .dim').first().innerText()).includes('3'));
  // GGUF de imagem: aba própria, pasta própria e "usar no Canvas"
  await page.locator('.seg button:text-is("Image")').click(); await page.waitForTimeout(300);
  check('tipos:aba-imagem-comeca-vazia', (await page.locator('.card:has(h3:text-is("Downloaded")) .row:has(.mono)').count()) === 0);
  await page.locator('input[type=search]').fill('flux'); await page.keyboard.press('Enter');
  await page.waitForSelector('.li'); await page.locator('.li').first().click(); await page.waitForSelector('.quant');
  await page.locator('.quant:has(b:text-is("Q4_K_M")):not(:has(.chip:has-text("parts")))').first().click();
  await page.locator('.btn.primary:has-text("Q4_K_M")').click();
  await page.waitForSelector('.modal'); await page.locator('.modal .foot .btn.primary').click();
  const useBtn = page.locator('.row:has(.mono:text-is("tiny-Q4_K_M.gguf")) .btn:has-text("Use in the Canvas (image)")');
  await useBtn.waitFor({ timeout: 15000 });
  check('tipos:imagem-oferece-usar-no-canvas', true);
  await useBtn.click(); await page.waitForTimeout(600);
  const st = await page.evaluate(() => fetch('/api/settings').then((r) => r.json()));
  check('tipos:canvas-passa-a-usar-o-gguf', st.media.active.image === 'gguf_local' && st.media.models.gguf_local.image === 'tiny-Q4_K_M.gguf');
  await page.locator('.seg button:text-is("Text")').click(); await page.waitForTimeout(400);
  check('tipos:texto-nao-mistura-com-imagem', (await page.locator('.row .mono:text-is("tiny-Q4_K_M.gguf")').count()) === 0);
  await page.locator('.seg button:text-is("Voice")').click(); await page.waitForTimeout(300);
  check('tipos:voz-so-baixa-e-organiza', (await page.locator('.muted.small:has-text("only downloads and organizes")').count()) === 1);
  await page.evaluate(() => fetch('/api/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ media: { active: { image: 'demo' } } }) }));  // não deixa o estado para outros testes
});
