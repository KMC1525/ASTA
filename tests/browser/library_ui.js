// Biblioteca: modelos de IA locais aparecem junto do que você criou; dá para selecionar vários itens e apagar (um a um ou em lote).
const { run } = require('./_common.js');
run('library', async ({ open, api, check }) => {
  const names = ['LibA', 'LibB', 'LibC'];
  for (const name of names) await api('/api/canvases', { method: 'POST', body: { name } });
  const page = await open();
  await page.evaluate(() => { location.hash = '#/library'; }); await page.waitForTimeout(900);
  const has = async (txt) => (await page.locator('.proj', { hasText: txt }).count()) >= 1;
  check('lib:canvases-aparecem', (await has('LibA')) && (await has('LibB')) && (await has('LibC')));
  check('lib:modelo-de-texto-pre-instalado', await has('Qwen3.8 2B Distill'));
  check('lib:modelo-avulso', await has('outro-Q4_K_M.gguf'));
  check('lib:z-image-uma-vez-so', (await page.locator('.proj.model', { hasText: 'Z-Image' }).count()) === 1);
  check('lib:codificador-de-apoio-nao-vira-modelo-solto', (await page.locator('.proj.model', { hasText: 'Qwen3-4B-Instruct' }).count()) === 0);
  check('lib:badge-tipo-do-modelo', (await page.locator('.proj.model', { hasText: 'Z-Image' }).locator('.badge', { hasText: 'Image' }).count()) === 1);
  check('lib:filtro-por-tipo-modelos', (await page.locator('.taglist .chip', { hasText: 'Local AI models' }).count()) === 1);
  check('lib:aviso-pre-instalado', (await page.locator('.proj.model', { hasText: 'Qwen3.8' }).locator('.chip', { hasText: 'pre-installed' }).count()) === 1);

  // seleção em lote: 2 canvases + 1 modelo
  await page.locator('.btn:has-text("Select")').first().click(); await page.waitForTimeout(200);
  check('lib:barra-de-selecao', (await page.locator('.selbar').count()) === 1 && (await page.locator('.proj .pick').count()) >= 6);
  check('lib:apagar-desligado-sem-selecao', await page.locator('.selbar .btn:has-text("Delete selected")').isDisabled());
  for (const txt of ['LibA', 'LibB', 'outro-Q4_K_M.gguf']) await page.locator('.proj', { hasText: txt }).first().click();
  await page.waitForTimeout(200);
  check('lib:contador-3', (await page.locator('.selbar').innerText()).includes('3 selected'));
  check('lib:cartoes-marcados', (await page.locator('.proj.picked').count()) === 3);
  await page.locator('.selbar .btn:has-text("Delete selected")').click(); await page.waitForTimeout(250);
  check('lib:pede-confirmacao', (await page.locator('.modal, .dialog, [role=dialog]').count()) >= 1 || (await page.locator('text=Delete 3 items').count()) >= 1);
  await page.locator('button:has-text("Delete")').last().click(); await page.waitForTimeout(900);
  check('lib:canvases-apagados', !(await has('LibA')) && !(await has('LibB')) && (await has('LibC')));
  check('lib:modelo-apagado', !(await has('outro-Q4_K_M.gguf')));
  const canv = await api('/api/canvases');
  check('lib:servidor-confirma-canvases', canv.filter((c) => ['LibA', 'LibB'].includes(c.name)).length === 0 && canv.some((c) => c.name === 'LibC'));
  check('lib:selecao-encerrada-apos-apagar', (await page.locator('.proj .pick').count()) === 0 && (await page.locator('.selbar').count()) === 1 && !(await page.locator('.selbar').isVisible()));

  // apagar um modelo de cada vez (Z-Image leva o VAE e o codificador de texto junto)
  const z = page.locator('.proj.model', { hasText: 'Z-Image' });
  await z.locator('.btn:has-text("Delete")').click(); await page.waitForTimeout(250);
  await page.locator('button:has-text("Delete")').last().click(); await page.waitForTimeout(800);
  check('lib:z-image-apagado', (await page.locator('.proj.model', { hasText: 'Z-Image' }).count()) === 0);
  const left = (await api('/api/library/models')).models.map((m) => m.name);
  check('lib:servidor-sem-z-image-e-com-qwen', !left.includes('z-image-Q4_K_M.gguf') && !left.includes('Qwen3-4B-Instruct-2507-Q4_K_M.gguf') && left.includes('Qwen3.8-2B-Q8_0.gguf'));
});
