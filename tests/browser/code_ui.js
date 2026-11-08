// Code no navegador: a seção na barra lateral, pastas e subpastas (nome, 8 cores, recolher/expandir, persistência), nova sessão, as bolinhas de estado (cinza, piscando, azul-claro, laranja),
// a pergunta Sim/Não do modo Ask, os controles (modo, esforço 1–8 agentes, modelo, ao terminar), a aba de Configuração (token do GitHub como segredo), inglês e celular.
// Sem IA (Demo): as regras entendem «rode os testes» e «leia arquivo».
const fs = require('fs');
const os = require('os');
const path = require('path');
const { run, until } = require('./_common');
run('code', async ({ api, open, check, base }) => {
  const proj = fs.mkdtempSync(path.join(os.tmpdir(), 'asta-code-ui-'));
  fs.mkdirSync(path.join(proj, 'tests'));
  fs.writeFileSync(path.join(proj, 'tests', '__init__.py'), '');
  fs.writeFileSync(path.join(proj, 'calc.py'), 'def add(a, b):\n    return a + b\n');
  fs.writeFileSync(path.join(proj, 'tests', 'test_calc.py'), 'import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n');
  const proj2 = fs.mkdtempSync(path.join(os.tmpdir(), 'asta-code-ui2-'));
  fs.writeFileSync(path.join(proj2, 'notes.txt'), 'olá\n');
  try {
    await api('/api/settings', { method: 'PUT', body: { language: 'pt-BR', active: { generation: 'demo' }, code: { mode: 'ask', effort: 'high', agents: 4, max_sessions: 4 } } });
    const page = await open();
    check('code:item-na-barra-lateral', (await page.locator('#side nav a[href="#/code"]').count()) === 1);
    await page.goto(base + '/#/code'); await page.waitForSelector('#cd-new');
    check('code:boas-vindas-sem-sessoes', (await page.locator('.cd-welcome').count()) === 1 && (await page.locator('.cd-item').count()) === 0);

    // ---- pastas: criar com cor, subpasta, editar nome/cor, recolher/expandir e persistir
    await page.locator('#cd-new-folder').click(); await page.waitForSelector('#cd-folder-name');
    check('code:oito-cores-vivas-diferentes', (await page.locator('.modal .cd-sw').count()) === 8 && new Set(await page.locator('.modal .cd-sw').evaluateAll((els) => els.map((e) => e.style.background))).size === 8);
    await page.locator('#cd-folder-name').fill('Trabalho');
    await page.locator('.cd-sw[data-color="orange"]').click();
    await page.locator('.modal .foot .primary').click();
    await page.waitForSelector('.cd-folder[data-color="orange"]');
    check('code:pasta-criada-com-cor', (await page.locator('.cd-folder .cd-fn').first().innerText()) === 'Trabalho');
    await page.locator('.cd-folder .cd-more').first().click();
    await page.locator('.cd-mi', { hasText: 'Nova subpasta' }).click(); await page.waitForSelector('#cd-folder-name');
    await page.locator('#cd-folder-name').fill('Cliente X'); await page.locator('.cd-sw[data-color="green"]').click(); await page.locator('.modal .foot .primary').click();
    await page.waitForSelector('.cd-folder[data-color="green"]');
    const folders = (await api('/api/code/folders')).folders;
    const sub = folders.find((f) => f.name === 'Cliente X'), top = folders.find((f) => f.name === 'Trabalho');
    check('code:subpasta-dentro-da-pasta-principal', sub && top && sub.parent === top.id);
    check('code:subpasta-indentada', (await page.locator('.cd-folder[data-color="green"]').evaluate((e) => parseInt(e.style.paddingLeft, 10))) > (await page.locator('.cd-folder[data-color="orange"]').evaluate((e) => parseInt(e.style.paddingLeft, 10))));
    // editar nome e cor
    await page.locator('.cd-folder[data-color="orange"] .cd-more').click();
    await page.locator('.cd-mi', { hasText: 'Editar nome e cor' }).click(); await page.waitForSelector('#cd-folder-name');
    await page.locator('#cd-folder-name').fill('Trabalho 2026'); await page.locator('.cd-sw[data-color="purple"]').click(); await page.locator('.modal .foot .primary').click();
    await page.waitForSelector('.cd-folder[data-color="purple"]');
    check('code:renomear-e-trocar-cor', (await api('/api/code/folders')).folders.some((f) => f.name === 'Trabalho 2026' && f.color === 'purple'));
    // recolher / expandir
    await page.locator('.cd-folder[data-color="purple"] .cd-caret').click();
    await page.waitForSelector('.cd-folder[data-color="purple"][data-collapsed="1"]');
    check('code:recolhida-esconde-a-subpasta', (await page.locator('.cd-folder[data-color="green"]').count()) === 0);
    await until(page, () => true);
    await page.waitForTimeout(300);
    check('code:recolher-persiste-no-servidor', (await api('/api/code/folders')).folders.find((f) => f.name === 'Trabalho 2026').collapsed === true);
    await page.reload(); await page.waitForSelector('.cd-folder');
    check('code:recolhida-continua-apos-recarregar', (await page.locator('.cd-folder[data-collapsed="1"]').count()) === 1);
    await page.locator('#cd-expand-all').click(); await page.waitForSelector('.cd-folder[data-color="green"]');
    check('code:expandir-tudo', (await page.locator('.cd-folder[data-collapsed="1"]').count()) === 0);

    // ---- nova sessão (pasta do computador, dentro da subpasta), estado inicial cinza
    await page.locator('#cd-new').click(); await page.waitForSelector('#cd-path');
    check('code:tres-origens-de-projeto', (await page.locator('.modal .seg button').count()) >= 3);
    check('code:oito-niveis-de-esforco', (await page.locator('#cd-effort option').allInnerTexts()).join(',') === 'Low,Medium,High,Extra,Mega,Max,Ultra,Omni');
    check('code:agentes-de-1-a-8', (await page.locator('#cd-agents').getAttribute('max')) === '8' && (await page.locator('#cd-agents').getAttribute('min')) === '1');
    check('code:finalizar-opcoes', (await page.locator('#cd-publish option').count()) === 5);
    await page.locator('#cd-path').fill(proj);
    await page.locator('#cd-new-title').fill('Sessão A');
    await page.locator('#cd-folder').selectOption({ label: '  Cliente X' });
    await page.locator('.modal .foot .primary').click();
    await page.waitForSelector('#cd-title');
    check('code:sessao-criada-e-aberta', (await page.locator('h2#cd-title').innerText()) === 'Sessão A' && /#\/code\/cs_/.test(page.url()));
    check('code:sessao-na-subpasta', (await api('/api/code/sessions')).sessions.find((s) => s.title === 'Sessão A').folder_id === sub.id);
    check('code:estado-inicial-cinza', (await page.locator('.cd-item.on .cd-dot').getAttribute('data-dot')) === 'idle');
    check('code:painel-ambiente', (await page.locator('.cd-panel').innerText()).includes(path.basename(proj)));

    // ---- controles da sessão
    check('code:controles-modo-esforco-agentes-modelo', (await page.locator('#cd-mode').count()) === 1 && (await page.locator('#cd-effort-sel option').count()) === 8 && (await page.locator('#cd-agents-sel option').count()) === 8 && (await page.locator('#cd-model-btn').count()) === 1 && (await page.locator('#cd-finalize').count()) === 1);
    await page.locator('#cd-effort-sel').selectOption('omni'); await page.waitForTimeout(400);
    await page.locator('#cd-agents-sel').selectOption('8'); await page.waitForTimeout(400);
    const sess = (await api('/api/code/sessions')).sessions.find((s) => s.title === 'Sessão A');
    check('code:esforco-e-agentes-salvos', sess.effort === 'omni' && sess.agents === 8);
    await page.locator('#cd-model-btn').click(); await page.waitForSelector('.mpick .mp-prov');
    check('code:seletor-de-modelo-da-sessao', (await page.locator('.mpick .mp-title').innerText()).toLowerCase().includes('modelo desta sessão') && (await page.locator('.mpick .mp-prov').count()) >= 1);
    await page.mouse.click(5, 5); await page.waitForTimeout(200);
    await page.locator('#cd-effort-sel').selectOption('low'); await page.waitForTimeout(300);
    await page.locator('#cd-finalize').click(); await page.waitForSelector('#cd-fin-pub');
    check('code:menu-ao-terminar', (await page.locator('#cd-fin-docs').count()) === 1 && (await page.locator('#cd-fin-pub option').count()) === 5);
    await page.locator('#cd-fin-ok').click(); await page.waitForTimeout(300);

    // ---- modo Ask: pergunta Sim/Não, estado laranja, selo na barra lateral
    await page.locator('.composer textarea').fill('rode os testes');
    await page.locator('.composer .send').click();
    await page.waitForSelector('.cd-ask');
    check('code:pergunta-sim-nao', (await page.locator('.cd-ask [data-answer="yes"]').count()) === 1 && (await page.locator('.cd-ask [data-answer="no"]').count()) === 1);
    check('code:bolinha-laranja-esperando-voce', (await page.locator('.cd-item.on .cd-dot').getAttribute('data-dot')) === 'ask');
    check('code:selo-da-barra-lateral-1-esperando', (await page.locator('#cd-badge.ask').innerText()) === '1');
    check('code:equipe-e-plano-aparecem', (await page.locator('.cd-ag').count()) >= 2 && (await page.locator('#cd-plan li').count()) >= 1);
    await page.locator('.cd-ask [data-answer="yes"]').click();
    await until(page, () => (document.querySelector('.cd-msg.ai') || {}).className?.includes('done'));
    check('code:resumo-do-code-na-conversa', (await page.locator('.cd-msg.ai .md').innerText()).length > 5 && (await page.locator('.cd-msg.user').count()) === 1);
    check('code:sessao-aberta-volta-a-cinza', (await page.locator('.cd-item.on .cd-dot').getAttribute('data-dot')) === 'idle');

    // ---- segunda sessão em segundo plano (Full Access): termina enquanto a primeira está aberta → bolinha azul-clara
    await page.locator('#cd-new').click(); await page.waitForSelector('#cd-path');
    await page.locator('#cd-path').fill(proj2); await page.locator('#cd-new-title').fill('Sessão B');
    await page.locator('.modal .seg button', { hasText: 'Full Access' }).click();
    await page.locator('.modal .foot .primary').click();
    await until(page, () => (document.querySelector('h2#cd-title') || {}).textContent === 'Sessão B');
    await page.locator('.composer textarea').fill('leia notes.txt');
    await page.locator('.composer .send').click();
    await page.waitForSelector('.cd-msg.ai');
    const idB = (await api('/api/code/sessions')).sessions.find((s) => s.title === 'Sessão B').id;
    await page.locator('.cd-item', { hasText: 'Sessão A' }).first().click();
    await until(page, () => (document.querySelector('h2#cd-title') || {}).textContent === 'Sessão A');
    await page.waitForSelector(`.cd-item[data-id="${idB}"]`);
    // B já terminou: ao abrir A o azul já está lá (ou aparece em instantes)
    await until(page, (id) => ['done', 'idle'].includes(document.querySelector(`.cd-item[data-id="${id}"] .cd-dot`).dataset.dot), idB);
    const bState = (await api('/api/code/sessions')).sessions.find((s) => s.id === idB);
    check('code:segunda-sessao-terminou-em-segundo-plano', bState.last_status === 'done' || bState.run_status === 'done');

    // ---- mover entre pastas pelo menu e por arrastar
    await page.locator(`.cd-item[data-id="${idB}"] .cd-more`).click();
    await page.locator('.cd-mi', { hasText: 'Mover para uma pasta' }).click(); await page.waitForSelector('#cd-move-to');
    await page.locator('#cd-move-to').selectOption({ label: 'Trabalho 2026' }); await page.locator('.modal .foot .primary').click();
    await page.waitForTimeout(500);
    check('code:mover-sessao-pelo-menu', (await api('/api/code/sessions')).sessions.find((s) => s.id === idB).folder_id === top.id);
    await page.locator(`.cd-item[data-id="${idB}"]`).dragTo(page.locator('.cd-loose'));
    await page.waitForTimeout(600);
    check('code:arrastar-para-sem-pasta', (await api('/api/code/sessions')).sessions.find((s) => s.id === idB).folder_id === null);

    // ---- configuração: aba Code, token como segredo
    await page.goto(base + '/#/config'); await page.waitForSelector('.cfgtabs');
    await page.locator('.cfgtabs button[data-tab="code"]').click(); await page.waitForSelector('#cd-gh-token');
    check('config:oito-niveis-listados', (await page.locator('#cd-effort-list li').count()) === 8);
    check('config:linguagens-pedidas', (await page.locator('#cd-langs details').evaluateAll((els) => els.map((e) => e.dataset.lang))).join(',').includes('python') && (await page.locator('#cd-langs details[data-lang="cpp"]').count()) === 1 && (await page.locator('#cd-langs details[data-lang="csharp"]').count()) === 1);
    await page.locator('#cd-gh-token').fill('ghp_ui_secret_token_1234567890abcdefghijklmn');
    await page.locator('#cd-gh-save').click(); await page.waitForTimeout(800);
    await page.locator('.cfgtabs button[data-tab="code"]').click().catch(() => {});
    await page.waitForSelector('#cd-gh-token');
    const html = await page.content();
    check('config:token-salvo-e-nunca-aparece-na-pagina', !html.includes('ghp_ui_secret') && (await page.locator('#cd-gh-token').getAttribute('placeholder')).includes('salvo') && (await api('/api/state')).settings.code.github.token_set === true);
    await page.locator('#cd-gh-remove').click(); await page.waitForTimeout(700);
    check('config:token-removido', (await api('/api/state')).settings.code.github.token_set === false);

    // ---- celular: lista e sessão se alternam
    const phone = await open({ width: 390, height: 800 });
    await phone.goto(base + '/#/code'); await phone.waitForSelector('.cd-item');
    check('code:celular-mostra-a-lista', (await phone.locator('.cd-main').isVisible()) === true && (await phone.locator('.cd-side').isVisible()) === true);
    await phone.locator('.cd-item').first().click(); await phone.waitForSelector('#cd-back');
    check('code:celular-sessao-esconde-a-lista-e-tem-voltar', (await phone.locator('.cd-side').isVisible()) === false && (await phone.locator('#cd-back').isVisible()) === true);
    check('code:celular-sem-rolagem-horizontal', (await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)));
    await phone.locator('#cd-back').click(); await phone.waitForSelector('.cd-side');

    // ---- inglês
    await api('/api/settings', { method: 'PUT', body: { language: 'en' } });
    await page.goto(base + '/#/code'); await page.reload(); await page.waitForSelector('#cd-new');
    check('code:ingles', (await page.locator('#cd-new').innerText()).includes('New session') && (await page.locator('#side nav a[href="#/code"] .lbl').innerText()) === 'Code');
    await api('/api/settings', { method: 'PUT', body: { language: 'pt-BR' } });
  } finally {
    fs.rmSync(proj, { recursive: true, force: true }); fs.rmSync(proj2, { recursive: true, force: true });
  }
});
