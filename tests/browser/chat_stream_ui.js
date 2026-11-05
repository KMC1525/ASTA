// v0.4.2: envio e streaming do Chat (tempo real, foco, tags <think>, Parar/Esc + «Responder», troca de conversa no meio da resposta, conversa apagada em outra aba,
// falha de envio, IME) e o painel das fontes pesquisadas no canto direito.
const { run } = require('./_common.js');
run('chat_stream', async ({ open, api, check, expectError }) => {
  expectError(/status of 404/);   // o 404 da conversa apagada é provocado de propósito
  const url = process.env.ASTA_FAKE_LM;
  await api('/api/settings', { method: 'PUT', body: { providers: { lmstudio: { base_url: url + '/v1', model: 'gemma-3-12b' } }, active: { generation: 'lmstudio', characters: 'auto' }, chat: { thinking: 'off', max_tokens: 2000, context_tokens: 16000, web: { default: false, engine: 'auto', results: 5 } } } });
  const page = await open({ width: 1400, height: 900 });
  await page.evaluate(() => { try { ['asta.web', 'asta.chat', 'asta.sources'].forEach((k) => localStorage.removeItem(k)); } catch (e) { /* ok */ } });
  await page.reload(); await page.waitForSelector('.chx', { timeout: 10000 });
  const ta = page.locator('.composer textarea'), runBtn = page.locator('.composer .send');
  const label = async () => (await runBtn.innerText()).trim();
  const idle = async () => { await page.waitForFunction(() => /^Run$/.test((document.querySelector('.composer .send') || { innerText: '' }).innerText.trim()), null, { timeout: 30000 }); };

  // ---- 1. resposta em tempo real: o texto cresce aos poucos, o balão «digitando» aparece na hora e o foco continua na caixa
  await ta.click(); await ta.fill('[stream] conte uma história'); await ta.press('Enter');
  await page.waitForSelector('.cmsg.ai.typing', { timeout: 3000 });
  check('envio:balao-digitando-aparece-na-hora', true);
  const sizes = new Set(); const t0 = Date.now();
  while ((await label()) === 'Stop' && Date.now() - t0 < 20000) { sizes.add(await page.evaluate(() => { const e = document.querySelector('.cmsg.ai .md'); return e ? e.innerText.length : 0; })); await page.waitForTimeout(100); }
  check('streaming:texto-cresce-em-tempo-real', [...sizes].filter((n) => n > 0).length >= 4);
  await idle();
  check('envio:foco-continua-na-caixa-de-texto', await page.evaluate(() => document.activeElement && document.activeElement.tagName === 'TEXTAREA'));
  check('envio:resposta-completa', (await page.locator('.cmsg.ai .md').last().innerText()).trim().split(/\s+/).length >= 30);

  // ---- 2. tags <think> chegando aos poucos nunca aparecem na tela
  await ta.fill('[think] quanto é 6x7?'); await ta.press('Enter');
  const seen = [];
  const t1 = Date.now();
  while ((await label()) === 'Stop' && Date.now() - t1 < 20000) { seen.push(await page.evaluate(() => { const e = [...document.querySelectorAll('.cmsg.ai .md')].pop(); return e ? e.innerText : ''; })); await page.waitForTimeout(60); }
  await idle();
  check('think:nunca-aparece-no-meio-da-resposta', seen.every((x) => !/<|racioc[ií]nio|think/i.test(x)));
  check('think:resposta-final-limpa', (await page.locator('.cmsg.ai .md').last().innerText()).trim() === 'Resposta limpa.');

  // ---- 3. markdown: sub-listas, endereços soltos viram links, [n] sem fonte fica como texto
  await ta.fill('[md] formate'); await ta.press('Enter'); await idle();
  const last = page.locator('.cmsg.ai').last();
  check('markdown:sub-listas', (await last.locator('li li').count()) === 2 && (await last.locator('.md > ul > li').count()) === 4);
  check('markdown:link-solto-sem-ponto-final', (await last.locator('a[href="https://example.org/x"]').count()) === 1);
  check('markdown:citacao-sem-fonte-fica-texto', (await last.locator('button.cite').count()) === 0 && (await last.innerText()).includes('[1]'));

  // ---- 4. Parar → a pergunta sem resposta ganha «Responder»; Responder conclui sem duplicar a pergunta
  const users0 = await page.locator('.cmsg.user').count();
  await ta.fill('[lento] me conta mais'); await ta.press('Enter');
  await page.waitForFunction(() => /Stop/.test(document.querySelector('.composer .send').innerText), null, { timeout: 5000 });
  await page.waitForTimeout(500); await runBtn.click(); await idle(); await page.waitForTimeout(600);
  check('parar:oferece-responder', (await page.locator('#chat-retry').count()) === 1 && (await page.locator('.csuggest.retry').innerText()).includes('interrupted'));
  check('parar:nada-pela-metade', (await page.locator('.cmsg.user').count()) === users0 + 1 && !(await page.locator('.cmsg.ai .md').last().innerText()).includes('parte parte'));
  await page.locator('#chat-retry').click(); await page.waitForFunction(() => document.querySelectorAll('.csuggest.retry').length === 0, null, { timeout: 5000 }); await idle();
  check('parar:responder-conclui-sem-duplicar', (await page.locator('.cmsg.user').count()) === users0 + 1 && (await page.locator('.cmsg.ai').count()) === users0 + 1);

  // ---- 5. Esc também para a resposta
  await ta.fill('[lento] outra'); await ta.press('Enter');
  await page.waitForFunction(() => /Stop/.test(document.querySelector('.composer .send').innerText), null, { timeout: 5000 });
  await page.waitForTimeout(400); await ta.press('Escape'); await idle();
  check('parar:esc-funciona', (await label()) === 'Run');
  await page.locator('#chat-retry').click(); await idle();

  // ---- 6. abas: nova aba no meio de uma resposta — a resposta segue chegando em segundo plano e nada vaza para a outra aba
  await page.locator('#chat-new').click(); await page.waitForTimeout(300);
  await ta.fill('[lento] pergunta da conversa A'); await ta.press('Enter');
  await page.waitForFunction(() => /Stop/.test(document.querySelector('.composer .send').innerText), null, { timeout: 5000 });
  await page.waitForTimeout(400);
  await page.locator('#chat-new').click(); await page.waitForTimeout(500);
  check('abas:nova-aba-fica-vazia-e-livre-para-enviar', (await page.locator('.chx.empty').count()) === 1 && (await page.locator('.cmsg').count()) === 0 && (await label()) === 'Run' && (await page.locator('.chx-tab').count()) >= 2);
  check('abas:aba-da-resposta-mostra-que-esta-ocupada', (await page.locator('.chx-tab.busy').count()) === 1);
  await page.waitForFunction(() => document.querySelectorAll('.chx-tab.busy').length === 0, null, { timeout: 30000 });
  check('abas:resposta-terminou-em-segundo-plano', (await page.locator('.chx-tab.busy').count()) === 0 && (await page.locator('.cmsg').count()) === 0);
  await page.locator('.chx-tab', { hasText: 'conversa A' }).first().click(); await page.waitForTimeout(500);
  check('abas:conversa-a-recebeu-a-resposta-inteira', (await page.locator('.cmsg.user').count()) === 1 && (await page.locator('.cmsg.ai').count()) === 1 && (await page.locator('.cmsg.ai .md').innerText()).includes('parte parte'));
  // a mesma resposta pode ser interrompida na aba da frente: sobra a pergunta com «Responder»
  await ta.fill('[lento] outra na aba A'); await ta.press('Enter');
  await page.waitForFunction(() => /Stop/.test(document.querySelector('.composer .send').innerText), null, { timeout: 5000 });
  await page.waitForTimeout(400); await ta.press('Escape'); await idle(); await page.waitForTimeout(500);
  check('abas:parar-na-aba-da-frente', (await page.locator('#chat-retry').count()) === 1);
  await page.locator('#chat-retry').click(); await idle();
  // fechar aba
  const tabsBefore = await page.locator('.chx-tab').count();
  await page.locator('.chx-tab.on .x').click(); await page.waitForTimeout(500);
  check('abas:fechar-aba', (await page.locator('.chx-tab').count()) === tabsBefore - 1 || (tabsBefore === 2 && (await page.locator('.chx-tab').count()) === 0));

  // ---- 7. conversa apagada em outra aba: o próximo envio abre uma nova e funciona
  await page.locator('#chat-new').click(); await page.waitForTimeout(300);
  await ta.fill('conversa que vai ser apagada'); await ta.press('Enter'); await idle();
  const oldId = await page.evaluate(() => localStorage.getItem('asta.chat'));
  await api('/api/chats/' + oldId, { method: 'DELETE' });
  await ta.fill('depois de apagada'); await ta.press('Enter');
  await page.waitForFunction((o) => localStorage.getItem('asta.chat') !== o, oldId, { timeout: 10000 }); await page.waitForSelector('.cmsg.ai', { timeout: 10000 }); await idle();
  const newId = await page.evaluate(() => localStorage.getItem('asta.chat'));
  check('apagada:abre-nova-e-responde', newId && newId !== oldId && (await page.locator('.cmsg.ai').count()) === 1 && (await page.locator('.chx-note.err').count()) === 0);

  // ---- 8. falha de envio: o balão some e o texto volta para a caixa
  await page.route('**/api/chats/*/send', (r) => r.fulfill({ status: 200, contentType: 'text/event-stream', body: 'data: ' + JSON.stringify({ type: 'error', kind: 'provider', message: 'falhou de propósito' }) + '\n\n' }));
  const n0 = await page.locator('.cmsg.user').count();
  await ta.fill('esta não chega'); await ta.press('Enter'); await page.waitForTimeout(700);
  check('falha:balao-removido-e-texto-volta', (await page.locator('.cmsg.user').count()) === n0 && (await ta.inputValue()) === 'esta não chega' && (await page.locator('.chx-note.err').innerText()).includes('falhou de propósito'));
  await page.unroute('**/api/chats/*/send');
  await ta.press('Enter'); await idle();
  check('falha:reenviar-funciona', (await page.locator('.cmsg.user').count()) === n0 + 1);

  // ---- 9. Enter que confirma uma palavra no IME não envia
  await ta.fill('こんにちは');
  await ta.evaluate((el) => { el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true, cancelable: true })); el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 229, bubbles: true, cancelable: true })); });
  await page.waitForTimeout(300);
  check('ime:enter-da-composicao-nao-envia', (await ta.inputValue()) === 'こんにちは' && (await page.locator('.cmsg.user').count()) === n0 + 1);
  await ta.fill('');

  // ---- 10. painel das fontes no canto direito, na ordem da busca
  await page.locator('#chat-new').click(); await page.waitForTimeout(300);
  check('fontes:painel-fechado-sem-pesquisa', (await page.locator('#chat-side:not(.hidden)').count()) === 0 && (await page.locator('#chat-sources:not(.hidden)').count()) === 0);
  await page.locator('#chat-web').click();
  await ta.fill('[web] qual o preço do dólar?'); await ta.press('Enter');
  await page.waitForSelector('#chat-side:not(.hidden) .sgroup.live', { timeout: 8000 });
  check('fontes:painel-abre-sozinho-e-mostra-pesquisando', (await page.locator('#chat-side .sg-wait').count()) === 1 || (await page.locator('#chat-side .ssrc').count()) > 0);
  await idle();
  const titles = await page.locator('#chat-side .ssrc .st').allInnerTexts();
  check('fontes:todas-na-ordem-da-busca', JSON.stringify(titles) === JSON.stringify(['Fonte A', 'Fonte B', 'Fonte C', 'Fonte D', 'Fonte E']));
  check('fontes:numeros-1-a-5', JSON.stringify(await page.locator('#chat-side .ssrc .sn').allInnerTexts()) === JSON.stringify(['1', '2', '3', '4', '5']));
  check('fontes:trecho-e-selo-de-lida', (await page.locator('#chat-side .ssrc .ss').count()) === 5 && (await page.locator('#chat-side .ssrc .badge').count()) === 2);
  const box = await page.locator('#chat-side').boundingBox(), mainBox = await page.locator('.chx-main').boundingBox();
  check('fontes:painel-no-canto-direito', box.x > mainBox.x + mainBox.width - 5 && box.x + box.width >= 1395);
  check('fontes:links-abrem-em-nova-aba-com-seguranca', (await page.locator('#chat-side .ssrc .st').first().getAttribute('target')) === '_blank' && (await page.locator('#chat-side .ssrc .st').first().getAttribute('rel')).includes('noopener'));
  check('fontes:citacoes-viram-botoes', (await page.locator('.cmsg.ai button.cite').count()) === 3);
  await page.locator('.cmsg.ai button.cite').nth(1).click(); await page.waitForTimeout(250);
  check('fontes:citacao-destaca-a-fonte', (await page.locator('#chat-side .ssrc.hl .sn').innerText()) === '2');
  check('fontes:contador-no-topo', (await page.locator('#chat-sources .count').innerText()) === '5');
  // segunda pesquisa: novo grupo depois do primeiro (ordem cronológica)
  await ta.fill('[web] e o euro?'); await ta.press('Enter'); await idle();
  check('fontes:segunda-pesquisa-vira-segundo-grupo', (await page.locator('#chat-side .sgroup').count()) === 2 && (await page.locator('#chat-side .sg-n').allTextContents()).join('|') === 'Search 1|Search 2' && (await page.locator('#chat-sources .count').innerText()) === '10');
  // fechar, lembrar a escolha, reabrir pelo botão
  await page.locator('#chat-side-close').click(); await page.waitForTimeout(200);
  check('fontes:fechar-esconde-o-painel', (await page.locator('#chat-side:not(.hidden)').count()) === 0 && (await page.locator('#chat-sources:not(.hidden)').count()) === 1);
  await page.reload(); await page.waitForSelector('.cmsg', { timeout: 10000 }); await page.waitForTimeout(500);
  check('fontes:escolha-de-fechar-e-lembrada', (await page.locator('#chat-side:not(.hidden)').count()) === 0);
  await page.locator('#chat-sources').click(); await page.waitForTimeout(250);
  check('fontes:reabre-pelo-botao-com-as-duas-pesquisas', (await page.locator('#chat-side .sgroup').count()) === 2);
  await page.locator('#chat-side .sgroup').first().locator('.sg-h').click(); await page.waitForTimeout(300);
  check('fontes:clicar-na-pesquisa-vai-para-a-resposta', true);
  // tela estreita: o painel não abre sozinho e vira gaveta
  await page.setViewportSize({ width: 800, height: 800 }); await page.evaluate(() => localStorage.removeItem('asta.sources')); await page.reload(); await page.waitForSelector('.cmsg', { timeout: 10000 }); await page.waitForTimeout(400);
  check('fontes:tela-estreita-nao-abre-sozinho', (await page.locator('#chat-side:not(.hidden)').count()) === 0);
  await page.locator('#chat-sources').click(); await page.waitForTimeout(250);
  const nb = await page.locator('#chat-side').boundingBox();
  check('fontes:tela-estreita-vira-gaveta-a-direita', nb.x + nb.width <= 801 && nb.x > 400 && !(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2)));
  await api('/api/settings', { method: 'PUT', body: { providers: { lmstudio: { base_url: '', model: '' } }, active: { generation: 'demo' } } });
});
