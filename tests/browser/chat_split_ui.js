// v0.6.2: abas do Chat — a barra desliza para os lados (roda, arrastar) e o botão direito divide a tela em duas abas lado a lado (estilo Firefox).
const { run } = require('./_common.js');
run('chat_split', async ({ open, api, check }) => {
  const url = process.env.ASTA_FAKE_LM;
  await api('/api/settings', { method: 'PUT', body: { providers: { lmstudio: { base_url: url + '/v1', model: 'gemma-3-12b' } }, active: { generation: 'lmstudio', characters: 'auto' }, chat: { thinking: 'off', max_tokens: 2000, context_tokens: 16000, web: { default: false } } } });
  const page = await open({ width: 900, height: 800 });
  await page.evaluate(() => { try { ['asta.web', 'asta.chat', 'asta.sources', 'asta.tabs'].forEach((k) => localStorage.removeItem(k)); } catch (e) { /* ok */ } });
  await page.reload(); await page.waitForSelector('.chx', { timeout: 10000 });
  const ta = page.locator('.composer textarea');
  const idle = () => page.waitForFunction(() => /^Run$/.test((document.querySelector('.composer .send') || { innerText: '' }).innerText.trim()), null, { timeout: 30000 });
  const say = async (txt) => { await ta.fill(txt); await ta.press('Enter'); await page.waitForTimeout(400); await page.waitForSelector('.cmsg.ai .md', { timeout: 15000 }); await idle(); await page.waitForTimeout(200); };
  const tabs = () => page.locator('.chx-tab');

  // 6 abas com conversa: a barra passa da largura e desliza
  await say('conversa numero um com um titulo bem comprido para ocupar espaco');
  for (const n of ['dois', 'tres', 'quatro', 'cinco', 'seis']) { await page.keyboard.press('Alt+n'); await page.waitForTimeout(300); await say('conversa numero ' + n + ' com um titulo bem comprido para ocupar espaco'); }
  check('abas:seis-abertas', (await tabs().count()) === 6);
  const dims = () => page.evaluate(() => { const s = document.querySelector('.chx-tabs'); return { sw: s.scrollWidth, cw: s.clientWidth, left: s.scrollLeft }; });
  const d0 = await dims();
  check('barra:passa-da-largura-e-fica-rolavel', d0.sw > d0.cw);
  check('barra:aba-da-frente-visivel', await page.evaluate(() => { const s = document.querySelector('.chx-tabs'), o = document.querySelector('.chx-tab.on'), a = s.getBoundingClientRect(), b = o.getBoundingClientRect(); return b.left >= a.left - 2 && b.right <= a.right + 2; }));
  await page.evaluate(() => { document.querySelector('.chx-tabs').scrollLeft = 0; });
  const box = await page.locator('.chx-tabs').boundingBox();
  await page.mouse.move(box.x + 300, box.y + 20); await page.mouse.wheel(0, 250); await page.waitForTimeout(500);
  check('barra:roda-do-mouse-desliza-para-os-lados', (await dims()).left > 50);
  await page.evaluate(() => { document.querySelector('.chx-tabs').scrollLeft = 300; }); await page.waitForTimeout(500);
  const before = (await dims()).left;
  await page.mouse.move(box.x + 400, box.y + 22); await page.mouse.down(); await page.mouse.move(box.x + 250, box.y + 22, { steps: 8 }); await page.mouse.up(); await page.waitForTimeout(500);
  check('barra:arrastar-desliza-sem-trocar-de-aba', (await dims()).left > before + 50);

  // botão direito → dividir a tela com outra aba
  await page.evaluate(() => { document.querySelector('.chx-tabs').scrollLeft = 0; }); await page.waitForTimeout(400);
  await tabs().nth(0).click({ button: 'right' }); await page.waitForSelector('.tabmenu', { timeout: 3000 });
  const menuTxt = await page.locator('.tabmenu').innerText();
  check('menu:tem-dividir-nova-aba-e-lista-de-abas', /split the view with a new tab/i.test(menuTxt) && /split the view with…/i.test(menuTxt) && /close tab/i.test(menuTxt));
  await page.locator('.tabmenu .opt', { hasText: 'conversa numero dois' }).click(); await page.waitForTimeout(600);
  check('divisao:duas-conversas-lado-a-lado', (await page.locator('.chx-panes.split .chx-pane').count()) === 2 && (await page.locator('.chx-pane .cmsg').count()) >= 4);
  check('divisao:as-duas-abas-formam-grupo-na-barra', (await page.locator('.chx-tab.grp').count()) === 2 && (await page.locator('.chx-tab.grp.g1').count()) === 1);
  const sideBySide = await page.evaluate(() => { const [a, b] = [...document.querySelectorAll('.chx-pane')].map((x) => x.getBoundingClientRect()); return a.right <= b.left + 2 && Math.abs(a.top - b.top) < 3; });
  check('divisao:paineis-lado-a-lado', sideBySide);
  const focusIdx = () => page.evaluate(() => [...document.querySelectorAll('.chx-pane')].findIndex((x) => x.classList.contains('focus')));
  check('divisao:foco-na-aba-escolhida-e-sem-tela-inicial', (await focusIdx()) === 1 && (await page.locator('.chx.empty').count()) === 0);
  // a caixa de texto vale para o painel com foco
  const cnt = (i) => page.locator('.chx-pane').nth(i).locator('.cmsg.user').count();
  const c0 = await cnt(0), c1 = await cnt(1);
  await say('pergunta no painel da direita');
  check('divisao:envia-no-painel-com-foco', (await cnt(1)) === c1 + 1 && (await cnt(0)) === c0);
  await page.locator('.chx-pane').nth(0).locator('.cmsg').first().click(); await page.waitForTimeout(400);
  check('divisao:clicar-no-painel-muda-o-foco', (await focusIdx()) === 0);
  await say('pergunta no painel da esquerda');
  check('divisao:envia-no-outro-painel', (await cnt(0)) === c0 + 1 && (await cnt(1)) === c1 + 1);
  // abrir uma aba fora do par mostra só ela; o grupo continua na barra
  await tabs().last().click(); await page.waitForTimeout(400);
  check('divisao:aba-fora-do-par-abre-sozinha', (await page.locator('.chx-panes.split').count()) === 0 && (await page.locator('.chx-tab.grp').count()) === 2);
  await page.locator('.chx-tab.grp').first().click(); await page.waitForTimeout(400);
  check('divisao:clicar-no-grupo-volta-para-a-tela-dividida', (await page.locator('.chx-panes.split .chx-pane').count()) === 2);
  // recarregar mantém a divisão
  await page.reload(); await page.waitForSelector('.chx-pane', { timeout: 10000 }); await page.waitForTimeout(500);
  check('divisao:volta-depois-de-recarregar', (await page.locator('.chx-panes.split .chx-pane').count()) === 2);
  // desfazer
  await page.locator('.chx-tab.grp').first().click({ button: 'right' }); await page.waitForSelector('.tabmenu');
  await page.locator('.tabmenu .opt', { hasText: 'Undo split view' }).click(); await page.waitForTimeout(400);
  check('divisao:desfazer-volta-a-uma-aba', (await page.locator('.chx-panes.split').count()) === 0 && (await page.locator('.chx-tab.grp').count()) === 0);
  // dividir com uma aba nova (vazia): sem tela inicial, o painel vazio aceita texto
  await tabs().nth(0).click({ button: 'right' }); await page.waitForSelector('.tabmenu');
  await page.locator('.tabmenu .opt', { hasText: 'Split the view with a new tab' }).click(); await page.waitForTimeout(500);
  check('divisao:com-aba-nova-tem-painel-vazio-focado', (await page.locator('.chx-pane').count()) === 2 && (await focusIdx()) === 1 && (await page.locator('.chx.empty').count()) === 0);
  await say('primeira mensagem do painel novo');
  check('divisao:painel-novo-recebeu-a-mensagem', (await cnt(1)) === 1);
  // fechar uma das duas desfaz a divisão
  await page.locator('.chx-tab.grp .x').first().click(); await page.waitForTimeout(500);
  check('divisao:fechar-uma-desfaz', (await page.locator('.chx-panes.split').count()) === 0 && (await page.locator('.chx-tab.grp').count()) === 0);
});
