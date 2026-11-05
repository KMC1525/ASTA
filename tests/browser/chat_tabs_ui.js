// v0.4.3: abas do Chat — comando «Nova aba de chat» (Alt+N, paleta, /nova), Alt+W, rascunho por aba, respostas em paralelo e em segundo plano, abas que voltam depois de recarregar.
const { run } = require('./_common.js');
run('chat_tabs', async ({ open, api, check }) => {
  const url = process.env.ASTA_FAKE_LM;
  await api('/api/settings', { method: 'PUT', body: { providers: { lmstudio: { base_url: url + '/v1', model: 'gemma-3-12b' } }, active: { generation: 'lmstudio', characters: 'auto' }, chat: { thinking: 'off', max_tokens: 2000, context_tokens: 16000, web: { default: false } } } });
  const page = await open({ width: 1400, height: 900 });
  await page.evaluate(() => { try { ['asta.web', 'asta.chat', 'asta.sources', 'asta.tabs'].forEach((k) => localStorage.removeItem(k)); } catch (e) { /* ok */ } });
  await page.reload(); await page.waitForSelector('.chx', { timeout: 10000 });
  const ta = page.locator('.composer textarea'), runBtn = page.locator('.composer .send');
  const label = async () => (await runBtn.innerText()).trim();
  const idle = () => page.waitForFunction(() => /^Run$/.test((document.querySelector('.composer .send') || { innerText: '' }).innerText.trim()), null, { timeout: 30000 });
  const tabs = () => page.locator('.chx-tab').count();

  // ---- uma aba só: a barra de abas fica escondida (tela limpa)
  check('abas:uma-so-esconde-a-barra', (await page.locator('.chx-tabs:not(.hidden)').count()) === 0 && (await tabs()) === 0 || (await page.locator('.chx-tabs.hidden').count()) === 1);
  await ta.fill('primeira conversa'); await ta.press('Enter'); await page.waitForSelector('.cmsg.ai .md', { timeout: 15000 }); await idle();

  // ---- Alt+N abre uma aba nova (e não duplica aba em branco)
  await page.keyboard.press('Alt+n'); await page.waitForTimeout(400);
  check('alt-n:abre-aba-nova-vazia', (await tabs()) === 2 && (await page.locator('.chx.empty').count()) === 1 && (await page.locator('.chx-tabs:not(.hidden)').count()) === 1);
  check('alt-n:foco-na-caixa', await page.evaluate(() => document.activeElement && document.activeElement.tagName === 'TEXTAREA'));
  await page.keyboard.press('Alt+n'); await page.waitForTimeout(300);
  check('alt-n:nao-duplica-aba-em-branco', (await tabs()) === 2);

  // ---- rascunho por aba
  await ta.fill('rascunho da aba 2');
  await page.locator('.chx-tab').first().click(); await page.waitForTimeout(400);
  check('aba:troca-mostra-a-outra-conversa', (await page.locator('.cmsg.user .bubble').first().innerText()).includes('primeira conversa') && (await ta.inputValue()) === '');
  await page.locator('.chx-tab').nth(1).click(); await page.waitForTimeout(400);
  check('aba:rascunho-volta-ao-reabrir', (await ta.inputValue()) === 'rascunho da aba 2');
  await ta.fill('');

  // ---- comando /nova na caixa: abre aba, não envia
  await page.locator('.chx-tab').first().click(); await page.waitForTimeout(300);
  const users0 = await page.locator('.cmsg.user').count(), chats0 = (await api('/api/chats')).length;
  await ta.fill('/nova'); await ta.press('Enter'); await page.waitForTimeout(500);
  check('comando-/nova:vai-para-a-aba-em-branco-sem-enviar', (await page.locator('.cmsg.user').count()) === 0 && (await page.locator('.chx.empty').count()) === 1 && (await tabs()) === 2 && (await api('/api/chats')).length === chats0);
  await page.locator('.chx-tab').first().click(); await page.waitForTimeout(300);
  check('comando-/nova:nada-foi-enviado-na-primeira', (await page.locator('.cmsg.user').count()) === users0 && (await ta.inputValue()) === '');

  // ---- paleta de comandos
  await page.keyboard.press('Control+k'); await page.waitForSelector('.palette', { timeout: 5000 });
  await page.keyboard.type('new chat tab'); await page.waitForTimeout(300);
  const items = await page.locator('.palette-item').allInnerTexts();
  check('paleta:tem-nova-aba-de-chat', items.some((x) => /New chat tab/i.test(x)));
  await page.keyboard.press('Enter'); await page.waitForTimeout(400);
  check('paleta:comando-ativa-a-aba-em-branco', (await page.locator('.chx.empty').count()) === 1 && (await tabs()) === 2);

  // ---- respostas em paralelo: a lenta segue em segundo plano enquanto outra aba responde
  await page.locator('.chx-tab').first().click(); await page.waitForTimeout(300);
  await ta.fill('[lento] resposta demorada na aba 1'); await ta.press('Enter');
  await page.waitForFunction(() => /Stop/.test(document.querySelector('.composer .send').innerText), null, { timeout: 5000 });
  await page.locator('.chx-tab').nth(1).click(); await page.waitForTimeout(300);
  check('paralelo:aba-livre-pode-enviar', (await label()) === 'Run' && (await page.locator('.chx-tab.busy').count()) === 1);
  await ta.fill('pergunta rápida na aba 2'); await ta.press('Enter');
  await page.waitForFunction(() => document.querySelector('.cmsg.ai .md') && /Resposta \d+/.test(document.querySelector('.cmsg.ai .md').innerText), null, { timeout: 15000 });
  await idle();
  check('paralelo:aba-2-respondeu-enquanto-a-1-segue', (await page.locator('.cmsg.ai .md').first().innerText()).includes('Resposta') && (await page.locator('.chx-tab.busy').count()) <= 1);
  await page.waitForFunction(() => document.querySelectorAll('.chx-tab.busy').length === 0, null, { timeout: 30000 });
  await page.locator('.chx-tab').first().click(); await page.waitForTimeout(400);
  check('paralelo:aba-1-terminou-em-segundo-plano', (await page.locator('.cmsg.ai').count()) === 2 && (await page.locator('.cmsg.ai .md').last().innerText()).includes('parte parte'));

  // ---- as abas voltam depois de recarregar (mesma ordem, mesma aba da frente)
  const titlesBefore = await page.locator('.chx-tab .tt').allInnerTexts();
  await page.reload(); await page.waitForSelector('.chx-tab', { timeout: 10000 }); await page.waitForTimeout(500);
  const titlesAfter = await page.locator('.chx-tab .tt').allInnerTexts();
  check('persistencia:abas-voltam-iguais', JSON.stringify(titlesBefore) === JSON.stringify(titlesAfter) && titlesAfter.length === 2);
  check('persistencia:aba-da-frente-lembrada', (await page.locator('.chx-tab.on .tt').innerText()) === titlesBefore[0]);

  // ---- histórico: abrir uma conversa que já tem aba só traz a aba para a frente
  await page.locator('#chat-history').click(); await page.waitForSelector('.mp-prov.hist', { timeout: 5000 });
  await page.locator('.mp-prov.hist', { hasText: 'pergunta rápida' }).first().click(); await page.waitForTimeout(500);
  check('historico:conversa-ja-aberta-nao-duplica-aba', (await tabs()) === 2 && (await page.locator('.chx-tab.on .tt').innerText()).includes('pergunta rápida'));

  // ---- de outra tela: Alt+N leva ao Chat com uma aba nova; sair e voltar mantém uma resposta em andamento
  await page.keyboard.press('Alt+n'); await page.waitForTimeout(300);   // aba em branco
  await ta.fill('[lento] sair da tela no meio'); await ta.press('Enter');
  await page.waitForFunction(() => /Stop/.test(document.querySelector('.composer .send').innerText), null, { timeout: 5000 });
  await page.evaluate(() => { location.hash = '#/library'; }); await page.waitForTimeout(700);
  await page.keyboard.press('Alt+n'); await page.waitForSelector('.chx', { timeout: 8000 }); await page.waitForTimeout(700);
  check('fora-do-chat:alt-n-leva-ao-chat-com-aba-nova', page.url().endsWith('#/main') && (await page.locator('.chx.empty').count()) === 1 && (await tabs()) === 4);
  await page.locator('.chx-tab', { hasText: 'sair da tela' }).click(); await page.waitForTimeout(500);
  check('fora-do-chat:resposta-em-segundo-plano-avisada-ou-pronta', (await page.locator('.chx-note.searching').count()) === 1 || (await page.locator('.cmsg.ai').count()) === 1);
  await page.waitForFunction(() => document.querySelectorAll('.cmsg.ai').length === 1 && !document.querySelector('#chat-retry'), null, { timeout: 30000 });
  check('fora-do-chat:resposta-chegou-sem-pedir-de-novo', (await page.locator('.cmsg.ai .md').innerText()).includes('parte parte') && (await page.locator('#chat-retry').count()) === 0);

  // ---- Alt+W fecha a aba da frente; a última aba nunca some
  const n = await tabs();
  await page.keyboard.press('Alt+w'); await page.waitForTimeout(500);
  check('alt-w:fecha-a-aba-da-frente', (await tabs()) === n - 1 || ((await tabs()) === 0 && n === 2));
  for (let i = 0; i < 6; i++) { await page.keyboard.press('Alt+w'); await page.waitForTimeout(250); }
  check('alt-w:a-ultima-aba-fica-vazia', (await page.locator('.chx.empty').count()) === 1 && (await page.locator('.composer textarea').count()) === 1);
  check('alt-w:fechar-aba-nao-apaga-a-conversa', (await api('/api/chats')).length >= chats0 + 2);
  await api('/api/settings', { method: 'PUT', body: { providers: { lmstudio: { base_url: '', model: '' } }, active: { generation: 'demo' } } });
});
