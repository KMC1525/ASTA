// v0.4.1: aba Chat nas configurações (tamanho da resposta, janela de contexto, tempo de pensamento, busca na web), botão Web no Chat com fontes,
// seletor de tempo de pensamento ao lado do modelo (só quando o modelo tem o recurso) e busca nas ferramentas de criação.
const { run, useTool } = require('./_common.js');
run('chat_settings', async ({ open, api, check, base }) => {
  const url = process.env.ASTA_FAKE_LM;
  const S = (m) => api('/api/settings', { method: 'PUT', body: m });
  await S({ providers: { lmstudio: { base_url: url + '/v1', model: 'gemma-3-12b' } }, active: { generation: 'lmstudio', characters: 'auto' }, chat: { max_tokens: 2000, context_tokens: 16000, thinking: 'off', instructions: '', web: { default: false, engine: 'auto', results: 5, read_pages: 2 } } });
  const page = await open({ width: 1300, height: 900 });
  await page.evaluate(() => { try { localStorage.removeItem('asta.web'); localStorage.removeItem('asta.chat'); } catch (e) { /* ok */ } });

  // ---- aba Chat nas configurações
  await page.evaluate(() => { location.hash = '#/config'; }); await page.waitForTimeout(600);
  const tabNames = await page.locator('.tabs button').allInnerTexts();
  check('config:aba-Chat-existe', tabNames.includes('Chat') && tabNames.length === 23);
  await page.locator('.tabs button', { hasText: /^Chat$/ }).click(); await page.waitForSelector('#cc-max_tokens', { timeout: 8000 });
  check('config:campos-do-chat', (await page.locator('#cc-max_tokens').count()) === 1 && (await page.locator('#cc-context_tokens').count()) === 1 && (await page.locator('.seg button', { hasText: 'Ultra' }).count()) === 1 && (await page.locator('.seg button', { hasText: 'Extra high' }).count()) === 1);
  await page.locator('.card:has(#cc-max_tokens) .chip', { hasText: /^8K tokens$/ }).click();
  check('config:atalho-de-tamanho-preenche', (await page.inputValue('#cc-max_tokens')) === '8000');
  check('config:minimo-2k-no-campo', (await page.getAttribute('#cc-max_tokens', 'min')) === '2000');
  await page.fill('#cc-max_tokens', '3000');
  await page.locator('.card:has(#cc-context_tokens) .chip', { hasText: /^32K$/ }).click();
  await page.fill('#cc-instructions', 'Responda sempre em tópicos.');
  await page.locator('.seg button', { hasText: /^High$/ }).click();
  await page.locator('label:has-text("Keep web search on by default"), .checkbox:has-text("Keep web search on by default")').first().click();
  await page.selectOption('.card:has(#cc-results) select >> nth=0', 'duckduckgo');
  await page.fill('#cc-results', '4');
  await page.fill('#cc-brave_key', 'segredo-brave');
  await page.locator('#cc-save').click(); await page.waitForTimeout(700);
  let s = await api('/api/settings');
  check('config:salva-tamanho-contexto-pensamento', s.chat.max_tokens === 3000 && s.chat.context_tokens === 32000 && s.chat.thinking === 'high' && s.chat.instructions === 'Responda sempre em tópicos.');
  check('config:salva-busca-na-web', s.chat.web.default === true && s.chat.web.engine === 'duckduckgo' && s.chat.web.results === 4 && s.chat.web.brave_key_set === true && s.chat.web.brave_key === '');
  await page.locator('#cc-test').click(); await page.waitForSelector('.ok:has-text("Working")', { timeout: 10000 });
  check('config:testar-busca-lista-resultados', (await page.locator('.card a[href="https://a.com/d"]').count()) === 1);

  // ---- Chat: a busca vem ligada por padrão; fontes aparecem na resposta
  await page.evaluate(() => { location.hash = '#/main'; }); await page.reload(); await page.waitForSelector('#chat-web', { timeout: 10000 }); await page.waitForTimeout(600);
  check('chat:web-ligado-por-padrao', (await page.locator('#chat-web.on').count()) === 1);
  check('chat:sem-botao-de-pensamento-em-modelo-sem-recurso', (await page.locator('#chat-think:not(.hidden)').count()) === 0);
  await page.locator('#chat-web').click();
  check('chat:web-desliga-no-botao', (await page.locator('#chat-web.on').count()) === 0);
  await page.locator('#chat-web').click();
  await page.fill('.composer textarea', 'Qual o preço do dólar hoje?'); await page.locator('.composer .send').click();
  await page.waitForSelector('.cmsg.ai .csources a', { timeout: 15000 });
  check('chat:fontes-na-resposta', (await page.locator('.cmsg.ai .csources a').first().getAttribute('href')) === 'https://a.com/d' && (await page.locator('.cmsg.ai .csources a').first().getAttribute('rel')).includes('noopener'));
  check('chat:busca-nao-deixa-aviso-preso', (await page.locator('.chx-note.searching').count()) === 0);
  await page.reload(); await page.waitForSelector('.cmsg.ai .csources a', { timeout: 10000 });
  check('chat:fontes-persistem-no-historico', (await page.locator('.cmsg.ai .csources a').count()) === 1);
  check('chat:web-lembrado-entre-visitas', (await page.locator('#chat-web.on').count()) === 1);

  // ---- tempo de pensamento ao lado do modelo (só com modelo que tem o recurso)
  await S({ providers: { lmstudio: { model: 'openai/gpt-oss-20b' } } });
  await page.reload(); await page.waitForSelector('#chat-think:not(.hidden)', { timeout: 10000 });
  const mb = await page.locator('.composer .mbtn').boundingBox(), tb = await page.locator('#chat-think').boundingBox();
  check('pensamento:aparece-ao-lado-do-nome-do-modelo', tb.x < mb.x && Math.abs(tb.y - mb.y) < 12 && tb.x + tb.width <= mb.x + 8);
  check('pensamento:mostra-o-nivel-salvo', (await page.locator('#chat-think').innerText()).includes('High'));
  await page.locator('#chat-think').click(); await page.waitForSelector('.thinkopt', { timeout: 5000 });
  const opts = await page.locator('.thinkopt').allInnerTexts();
  check('pensamento:modos-slow-a-ultra', opts.length === 6 && ['Slow', 'Medium', 'High', 'Extra high', 'Ultra'].every((n) => opts.some((o) => o.startsWith(n))));
  await page.locator('.thinkopt[data-level="ultra"]').click(); await page.waitForTimeout(600);
  s = await api('/api/settings');
  check('pensamento:escolha-salva', s.chat.thinking === 'ultra' && (await page.locator('#chat-think').innerText()).includes('Ultra'));
  await page.locator('#chat-web').click();   // desliga: esta rodada não pesquisa
  await page.fill('.composer textarea', 'resolva um problema difícil'); await page.locator('.composer .send').click();
  await page.waitForSelector('.cmsg.ai:last-child .md', { timeout: 15000 }); await page.waitForTimeout(500);

  // ---- ferramenta de criação + Web: o prompt é pesquisado e as fontes seguem junto (provedor Demo, offline)
  await S({ active: { generation: 'demo' } });
  await page.locator('#chat-new').click(); await page.waitForTimeout(300);
  await page.locator('#chat-web:not(.on)').click();
  await useTool(page, 'game');
  check('ferramenta:web-continua-ao-lado-das-opcoes', (await page.locator('.composer #chat-web.on').count()) === 1);
  await page.fill('.composer textarea', 'Um jogo de plataforma sobre o dólar'); await page.locator('.composer .send').click();
  await page.waitForSelector('.result', { timeout: 90000 });
  check('ferramenta:cria-com-a-busca', (await page.locator('.result a[href*="/play/"]').count()) === 1);
  // v0.15.8: celular/app — «LM Studio no computador» (procura na rede ou IP digitado); no computador o cartão não aparece
  check('lmstudio:computador-nao-mostra-o-cartao-do-celular', (await (await open({ width: 1300, height: 900 })).evaluate(async () => { location.hash = '#/config'; await new Promise((r) => setTimeout(r, 1200)); return document.querySelectorAll('#lms-pc').length; })) === 0);
  await S({ providers: { lmstudio: { base_url: url + '/v1' } }, active: { generation: 'lmstudio' } });   // o cartão do provedor em uso já vem aberto
  // v0.15.11: no computador, Celular e tablet → «LM Studio fora de casa» (túnel + proxy com código)
  const pc = await open({ width: 1300, height: 900 });
  await pc.evaluate(() => { location.hash = '#/config'; }); await pc.waitForSelector('.cfgtabs');
  await pc.locator('.cfgtabs button[data-tab="mobile"]').click(); await pc.waitForSelector('#remote-lm');
  check('remoto:cartao-no-computador', (await pc.locator('#remote-lm').innerText()).includes('LM Studio') && ((await pc.locator('#remote-install').count()) + (await pc.locator('#remote-start').count())) === 1);
  const mob = await open({ width: 390, height: 800 });
  await mob.addInitScript(() => Object.defineProperty(navigator, 'userAgent', { get: () => 'Mozilla/5.0 (Linux; Android 14) ASTA-Android' }));
  await mob.goto(base + '/#/config'); await mob.reload(); await mob.waitForSelector('#lms-pc');
  await mob.fill('#lms-pc-addr', '127.0.0.1:' + new URL(url).port); await mob.locator('#lms-pc-go').click(); await mob.waitForTimeout(800);
  check('lmstudio:celular-aponta-para-o-computador', (await api('/api/settings')).providers.lmstudio.base_url === url);
  await S({ providers: { lmstudio: { base_url: '', model: '' } }, active: { generation: 'demo' }, chat: { thinking: 'off', max_tokens: 2000, context_tokens: 16000, instructions: '', web: { default: false, engine: 'auto', results: 5 } } });
  await api('/api/settings', { method: 'PUT', body: { chat: { web: { brave_key: null } } } });
});
