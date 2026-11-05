// Conversa de avatar: avisa quando só o Demo (respostas pré-programadas) está disponível e mostra qual IA responde quando há uma configurada.
const { run } = require('./_common.js');
run('avatar_engine', async ({ open, api, check }) => {
  const av = await api('/api/avatars', { method: 'POST', body: { name: 'Aya', age: 26, greeting: '' } });
  const chat = await api('/api/avatar-chats', { method: 'POST', body: { avatar_ids: [av.id] } });
  await api('/api/settings', { method: 'PUT', body: { active: { generation: 'demo', characters: 'auto' } } });
  const page = await open();
  await page.evaluate((id) => { location.hash = '#/avatars/chat/' + id; }, chat.id); await page.waitForTimeout(900);
  const warn = page.locator('.chengine.warn');
  check('eng:aviso-demo', (await warn.count()) === 1 && (await warn.innerText()).includes('Demo mode: replies are pre-programmed'));
  check('eng:botao-configurar-ia', (await warn.locator('.btn:has-text("Set up AI")').count()) === 1);
  await warn.locator('.btn').click(); await page.waitForTimeout(600);
  check('eng:leva-para-configuracao', page.url().includes('#/config'));

  // com uma IA configurada (provedor OpenAI-compatível, só a configuração: nada é chamado) o aviso some e a IA aparece
  await api('/api/settings', { method: 'PUT', body: { providers: { custom: { base_url: 'http://127.0.0.1:9/v1', model: 'meu-modelo', api_key: 'k' } }, active: { generation: 'custom' } } });
  await page.evaluate((id) => { location.hash = '#/avatars/chat/' + id; }, chat.id); await page.waitForTimeout(900);
  check('eng:sem-aviso-com-ia', (await page.locator('.chengine.warn').count()) === 0);
  const ok = page.locator('.chengine.ok');
  check('eng:mostra-qual-ia-responde', (await ok.count()) === 1 && (await ok.innerText()).includes('meu-modelo'));
  await api('/api/settings', { method: 'PUT', body: { active: { generation: 'demo' }, providers: { custom: { api_key: null } } } });
});
