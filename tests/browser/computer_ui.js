// Computer Use no navegador: a seção na barra lateral, ligar o recurso, criar uma tarefa no modo Ask (Sim/Não), o passo a passo e o histórico, desfazer,
// o botão do Chat (cartão ao vivo com a pergunta), a aba de Configuração e o celular. Sem IA (Demo): as regras entendem «crie a pasta …».
const { run, until } = require('./_common');
run('computer', async ({ api, open, check, base }) => {
  const home = process.env.ASTA_TEST_HOME;
  await api('/api/settings', { method: 'PUT', body: { computer: { enabled: false, mode: 'ask' } } });
  const page = await open();
  check('cu:item-na-barra-lateral', (await page.locator('#side nav a[href="#/computer"]').count()) === 1);
  await page.goto(base + '/#/computer'); await page.waitForSelector('#cu-enable');
  check('cu:desligado-por-padrao-pede-para-ligar', (await page.locator('.cu-onboard').count()) === 1 && (await page.locator('#cu-mode').count()) === 0);
  await page.locator('#cu-enable').click(); await page.waitForSelector('#cu-mode');
  check('cu:ligou-e-mostra-os-modos', (await page.locator('#cu-mode button').allInnerTexts()).join('|') === 'Ask|Full Access' && (await api('/api/settings')).computer.enabled === true);
  check('cu:mostra-capacidades-do-computador', (await page.locator('.cu-caps li').count()) === 6);

  // tarefa no modo Ask: a pergunta aparece, o selo da barra lateral acende e «Não» nega a ação
  await page.locator('.composer textarea').fill(`crie a pasta UiNegada em ${home}/Documents`);
  await page.locator('.composer .send').click();
  await page.waitForSelector('.cu-ask');
  check('cu:pergunta-sim-nao', (await page.locator('.cu-ask [data-answer="yes"]').count()) === 1 && (await page.locator('.cu-ask [data-answer="no"]').count()) === 1);
  check('cu:selo-da-barra-mostra-1-esperando', (await page.locator('#cu-badge.ask').innerText()) === '1');
  check('cu:time-de-agentes-e-roteiro', (await page.locator('.cu-ag').count()) === 4 && (await page.locator('.cu-plan li').count()) >= 1);
  await page.locator('.cu-ask [data-answer="no"]').click();
  await until(page, () => ['partial', 'failed', 'done'].includes((document.querySelector('.cu-meta .cu-st') || {}).dataset?.status));
  const denied = await page.locator('.cu-step[data-status="denied"]').count();
  check('cu:acao-negada-aparece-no-passo-a-passo', denied === 1);
  check('cu:pasta-nao-foi-criada', !(await api('/api/computer/tasks')).tasks.some((t) => t.ok > 0 && t.goal.includes('UiNegada')));

  // nova tarefa: «sim, e não perguntar de novo» → conclui; passo a passo com detalhes; desfazer
  await page.locator('#cu-new').click(); await page.waitForSelector('.composer textarea');
  await page.locator('.composer textarea').fill(`crie a pasta UiAprovada em ${home}/Documents`);
  await page.locator('.composer .send').click();
  await page.waitForSelector('.cu-ask');
  await page.locator('.cu-ask .cu-remember input').check();
  await page.locator('.cu-ask [data-answer="yes"]').click();
  await until(page, () => (document.querySelector('.cu-meta .cu-st') || {}).dataset?.status === 'done');
  check('cu:concluida-com-resumo', (await page.locator('.cu-sum').count()) === 1 && (await page.locator('#cu-goal').innerText()).includes('UiAprovada'));
  await page.locator('.cu-step').first().locator('.cu-sh').click();
  check('cu:passo-expande-com-ferramenta-e-resultado', (await page.locator('.cu-step.open .cu-pre').count()) >= 1 && (await page.locator('.cu-step.open .cu-kv').innerText()).includes('make_dir'));
  check('cu:historico-lista-as-duas', (await page.locator('.cu-item').count()) === 2);
  await page.locator('#cu-undo').click(); await page.locator('.modal .btn.primary').click();
  await until(page, () => !document.querySelector('#cu-undo'));
  const tasks = (await api('/api/computer/tasks')).tasks;
  check('cu:desfazer-limpou-o-botao', tasks.every((t) => !t.undo));
  await page.reload(); await page.waitForSelector('.cu-item');
  check('cu:historico-sobrevive-ao-recarregar', (await page.locator('.cu-item').count()) === 2);
  await page.locator('.cu-item').nth(0).click(); await page.waitForSelector('#cu-goal');
  check('cu:abre-tarefa-antiga-por-endereco', /#\/computer\/cu_/.test(page.url()));

  // Chat: botão Computer Use → cartão ao vivo com a pergunta e o resumo
  await page.goto(base + '/#/main'); await page.waitForSelector('#chat-cu');
  await page.locator('#chat-cu').click();
  check('cu:menu-do-chat-tem-ask-e-full', (await page.locator('.cuopt').count()) === 2);
  await page.locator('.cuopt[data-mode="ask"]').click();
  check('cu:botao-fica-ligado-com-o-modo', (await page.locator('#chat-cu').innerText()).includes('Ask'));
  await page.locator('.composer textarea').fill(`crie a pasta UiChat em ${home}/Documents`);
  await page.locator('.composer .send').click();
  await page.waitForSelector('.cu-card .cu-ask');
  check('cu:cartao-no-chat-pergunta-sim-nao', (await page.locator('.cu-card [data-answer="yes"]').count()) === 1);
  await page.locator('.cu-card [data-answer="yes"]').click();
  await until(page, () => /Done|Concluída/.test((document.querySelector('.cu-card .cu-st') || {}).textContent || ''));
  check('cu:cartao-mostra-resumo-e-link', (await page.locator('.cu-card .md').count()) === 1 && (await page.locator('.cu-card [data-open]').count()) === 1);
  check('cu:sem-responder-de-novo-em-tarefa', (await page.locator('.cmsg.cu .cacts button').count()) === 0);
  await page.reload(); await page.waitForSelector('.cu-card');
  check('cu:cartao-volta-no-historico-do-chat', (await page.locator('.cmsg.user .cu-chip-user').count()) >= 1 && (await page.locator('.cu-card').count()) >= 1);
  await page.locator('.cu-card [data-open]').first().click(); await page.waitForSelector('#cu-goal');
  check('cu:abrir-leva-a-secao', page.url().includes('#/computer'));

  // Configuração
  await page.goto(base + '/#/config'); await page.waitForSelector('.cfgtabs');
  await page.locator('.cfgtabs button[data-tab="computer"]').click(); await page.waitForSelector('#cu-gamedirs');
  check('cu:aba-de-configuracao', (await page.locator('.cu-cfg-prompts details').count()) >= 15 && (await page.locator('.cu-asks input').count()) === 5);
  await page.locator('.cu-cfg-prompts details summary', { hasText: 'operator.md' }).click();
  await until(page, () => /Operator/.test(document.querySelector('.cu-cfg-prompts details[open] pre')?.textContent || ''));
  check('cu:le-os-prompts-internos', true);

  // esconder da barra lateral e celular
  await api('/api/settings', { method: 'PUT', body: { ui: { sidebar_hidden: ['computer'] } } });
  await page.reload(); await page.waitForSelector('#side nav');
  check('cu:da-para-esconder-da-barra', (await page.locator('#side nav a[href="#/computer"]').count()) === 0);
  await api('/api/settings', { method: 'PUT', body: { ui: { sidebar_hidden: [] } } });
  const phone = await open({ width: 390, height: 800 });
  await phone.goto(base + '/#/computer'); await phone.waitForSelector('.cu-item');
  check('cu:celular-lista-e-nova-tarefa-empilhadas', (await phone.locator('.cu-list').isVisible()) && (await phone.locator('.cu-main .cu-new-card').isVisible()));
  await phone.locator('.cu-item').first().click(); await phone.waitForSelector('.cu-back');
  check('cu:celular-detalhe-com-voltar', (await phone.locator('.cu-back').isVisible()) && !(await phone.locator('.cu-list').isVisible()));
  const overflow = await phone.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
  check('cu:celular-sem-rolagem-horizontal', !overflow);
  await api('/api/computer/history/clear', { method: 'POST', body: { purge: true } });
  await api('/api/settings', { method: 'PUT', body: { computer: { enabled: false } } });
});
