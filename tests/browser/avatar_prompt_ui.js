// Editor de avatar: pipeline do system prompt (Analisa → Gera → Revisa → Entrega) e tipo de personagem (real = sempre SFW).
const { run } = require('./_common.js');
run('avatar_prompt', async ({ open, api, check }) => {
  const card = await api('/api/avatars', { method: 'POST', body: { name: 'Selene', age: 28, content: 'nsfw', personality: 'misteriosa e carinhosa' } });
  const page = await open();
  await page.evaluate((id) => { location.hash = '#/avatars/edit/' + id; }, card.id); await page.waitForTimeout(900);
  check('ap:cartao-do-pipeline', (await page.locator('.card h3:has-text("Generate the system prompt with AI")').count()) === 1);
  await page.locator('textarea[placeholder^="E.g. anime character"]').fill('Gosta de astronomia e fala baixinho.');
  await page.locator('.btn:has-text("Generate system prompt")').click();
  await page.waitForFunction(() => document.querySelector('textarea[placeholder^="Who they are"]') && document.querySelector('textarea[placeholder^="Who they are"]').value.includes('Selene'), null, { timeout: 20000 });
  check('ap:system-prompt-preenchido', true);
  const stepsTxt = await page.locator('.card:has(h3:has-text("Generate the system prompt with AI"))').innerText();
  check('ap:quatro-etapas', ['Analyze', 'Generate', 'Review', 'Deliver'].every((x) => stepsTxt.includes(x)));
  check('ap:mostra-nota-e-resultado', stepsTxt.includes('Score'));
  check('ap:texto-contem-instrucao', (await page.locator('textarea[placeholder^="Who they are"]').inputValue()).includes('astronomia'));

  // pessoa real: o conteúdo vira SFW e o NSFW é recusado
  await page.locator('.seg button:has-text("Real person")').click(); await page.waitForTimeout(250);
  check('ap:real-forca-sfw', (await page.locator('.seg button.on', { hasText: 'SFW' }).count()) >= 1 && (await page.locator('.seg button.on', { hasText: 'NSFW' }).count()) === 0);
  await page.locator('.seg button:text-is("NSFW")').click(); await page.waitForTimeout(250);
  check('ap:real-recusa-nsfw', (await page.locator('.seg button.on', { hasText: 'NSFW' }).count()) === 0);
  await page.locator('.btn:has-text("Save")').first().click(); await page.waitForTimeout(600);
  const saved = await api('/api/avatars/' + card.id);
  check('ap:salvou-real-sfw', saved.character_type === 'real' && saved.content === 'sfw' && saved.system_prompt.includes('Selene'));
  await page.locator('.seg button:has-text("Fictional")').click(); await page.waitForTimeout(250);
  await page.locator('.seg button:text-is("NSFW")').click(); await page.waitForTimeout(250);
  check('ap:ficticio-aceita-nsfw', (await page.locator('.seg button.on', { hasText: 'NSFW' }).count()) === 1);

  // composer da home: seletor de tipo de personagem
  await page.evaluate(() => { location.hash = '#/main'; }); await page.waitForTimeout(500);
  const hasAvatarMode = await page.locator('button:has-text("Avatar")').count();
  if (hasAvatarMode) { await page.locator('button:has-text("Avatar")').first().click(); await page.waitForTimeout(500); }
  check('ap:home-seletor-de-tipo', (await page.locator('select option:text-is("Real person (always SFW)")').count()) >= 1);
});
