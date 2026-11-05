// Configuração → Provedores → LM Studio: detecta o servidor, lista os modelos (carregados primeiro), escolhe com um clique e usa nos avatares.
const { run } = require('./_common.js');
run('lmstudio', async ({ open, api, check }) => {
  const url = process.env.ASTA_FAKE_LM;
  await api('/api/settings', { method: 'PUT', body: { providers: { lmstudio: { base_url: url + '/v1', model: '' } }, active: { generation: 'demo', characters: 'auto' } } });
  const page = await open();
  await page.evaluate(() => { location.hash = '#/config'; }); await page.waitForTimeout(700);
  const card = page.locator('.prov', { hasText: 'LM Studio' }).first();
  await card.locator('.hd').click();
  await page.waitForSelector('.prov.open:has-text("LM Studio detected at")', { timeout: 15000 });
  check('lm:detectou-o-servidor', true);
  const body = card.locator('.bd');
  check('lm:modelos-de-chat-listados', (await body.locator('.chip', { hasText: 'gemma-3-12b' }).count()) === 1 && (await body.locator('.chip', { hasText: 'qwen3-8b' }).count()) === 1);
  check('lm:embeddings-escondidos', (await body.locator('.chip', { hasText: 'embedding' }).count()) === 0);
  check('lm:carregado-marcado', (await body.locator('.chip', { hasText: '● gemma-3-12b' }).count()) === 1 && (await body.locator('.chip', { hasText: '○ qwen3-8b' }).count()) === 1);
  check('lm:visao-sinalizada', (await body.locator('.chip', { hasText: 'gemma-3-12b' }).innerText()).includes('👁'));
  check('lm:sem-caixa-de-visao-manual', (await body.locator('text=Accepts images').count()) === 0);
  await body.locator('.chip', { hasText: 'llama-3.2-3b' }).click(); await page.waitForTimeout(800);
  check('lm:clique-escolhe-o-modelo', (await body.locator('input[list="models-lmstudio"]').inputValue()) === 'llama-3.2-3b');
  await body.locator('.btn:has-text("Use for avatars")').click(); await page.waitForTimeout(700);
  const s = await api('/api/settings');
  check('lm:usa-nos-avatares', s.active.characters === 'lmstudio' && s.providers.lmstudio.model === 'llama-3.2-3b');
  const eng = await api('/api/avatars/engine');
  check('lm:motor-do-chat-e-o-lm-studio', eng.id === 'lmstudio' && eng.model === 'llama-3.2-3b' && !eng.demo);
  await api('/api/settings', { method: 'PUT', body: { providers: { lmstudio: { base_url: '', model: '' } }, active: { characters: 'auto' } } });
});
