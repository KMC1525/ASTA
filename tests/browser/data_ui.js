// Modo Data no navegador (v0.24; sem IA configurada = métodos determinísticos): as sete abas, criar item, o editor em grade (colunas, linhas, edição de célula, filtro,
// ordenação, paginação, perfil, limpeza, mídia, histórico), busca na lista, mesclagem com prévia, dados sintéticos, aviso do scraping, upgrade (ações) e exportação.
//
// A tela roda em português ou inglês conforme o navegador, então os testes usam ids e posições (nunca o texto do botão).
const { run, until } = require('./_common');

run('data_ui', async ({ base, api, open, check }) => {
  const page = await open();
  const top = () => page.locator('.modal').last();                      // o diálogo de cima (os de dentro do editor empilham)
  const topFoot = (n) => top().locator('.foot button').nth(n);

  // ---- as sete abas, na ordem pedida
  await page.goto(base + '/#/data/main');
  await page.waitForSelector('.dt-tabs');
  const tabs = await page.$$eval('.dt-tab', (els) => els.map((e) => e.getAttribute('href')));
  check('abas:as-sete', tabs.length === 7);
  check('abas:ordem', tabs.join(',') === ['#/data/main', '#/data/databases', '#/data/datasets', '#/data/synthetic_data', '#/data/web_scraping', '#/data/upgrade', '#/data/export'].join(','));
  check('nav:data-na-barra', (await page.locator('#side nav a[href="#/data"]').count()) === 1);
  check('main:descricao', /sint|synthetic/.test((await page.textContent('#dt-body')).toLowerCase()));

  // ---- criar um dataset: o editor em grade abre sozinho
  await page.click('#dt-body .dt-actions button');            // o primeiro botão é «Novo»
  await page.waitForSelector('#dt-new-kind');
  await page.fill('.modal input:not([type=checkbox])', 'Clientes de teste');
  await page.click('.modal .foot button:last-child');
  await page.waitForSelector('#dt-item-name', { timeout: 15000 });
  check('editor:abre-apos-criar', (await page.inputValue('#dt-item-name')) === 'Clientes de teste');
  check('editor:barra-de-ferramentas', (await page.locator('#dt-add-row, #dt-add-col, #dt-btn-profile, #dt-btn-clean, #dt-btn-dedupe, #dt-btn-merge, #dt-btn-media, #dt-btn-schema, #dt-btn-history').count()) === 9);

  // ---- coluna nova (inteiro), duas linhas, edição de célula
  await page.click('#dt-add-col');
  await page.fill('#dt-newcol-name', 'idade');
  await page.selectOption('#dt-newcol-type', 'integer');
  await topFoot(1).click();
  await page.waitForSelector('th:has-text("idade")');
  check('editor:coluna-nova', (await page.locator('.dt-grid-wrap th').filter({ hasText: 'idade' }).count()) === 1);
  await page.click('#dt-add-row');
  await page.waitForSelector('.dt-grid-wrap tbody tr[data-i="0"]');
  await page.click('#dt-add-row');
  await page.waitForSelector('.dt-grid-wrap tbody tr[data-i="1"]');
  check('editor:duas-linhas', (await page.locator('.dt-grid-wrap tbody tr[data-i]').count()) === 2);
  const list = (await api('/api/data/items?kind=dataset')).items;
  const it = list.find((x) => x.name === 'Clientes de teste');
  const rows = () => api(`/api/data/items/dataset/${it.id}/rows?limit=50`);
  await page.dblclick('tr[data-i="0"] td[data-field="idade"]');
  await page.fill('.dt-edit', '42');
  await page.keyboard.press('Enter');
  await until(page, () => document.querySelector('tr[data-i="0"] td[data-field="idade"]').textContent.trim() === '42');
  await page.dblclick('tr[data-i="1"] td[data-field="content"]');
  await page.fill('.dt-edit', 'Maria Souza');
  await page.keyboard.press('Enter');
  await until(page, () => document.querySelector('tr[data-i="1"] td[data-field="content"]').textContent.includes('Maria'));
  const r1 = await rows();
  check('editor:celula-grava-no-servidor', r1.rows[0].r.idade === 42 && r1.rows[1].r.content === 'Maria Souza');
  check('editor:tipo-inteiro', typeof r1.rows[0].r.idade === 'number');

  // ---- filtro, ordenação e paginação (no servidor)
  await page.fill('#dt-item-filter', 'maria');
  await until(page, () => document.querySelectorAll('.dt-grid-wrap tbody tr[data-i]').length === 1);
  check('editor:filtro', (await page.locator('.dt-grid-wrap tbody tr[data-i]').count()) === 1);
  check('editor:filtro-mostra-total', /2/.test(await page.textContent('#dt-pager-info')));
  await page.fill('#dt-item-filter', 'nada-que-exista');
  await until(page, () => document.querySelectorAll('.dt-grid-wrap tbody tr[data-i]').length === 0);
  await page.fill('#dt-item-filter', '');
  await until(page, () => document.querySelectorAll('.dt-grid-wrap tbody tr[data-i]').length === 2);
  await page.locator('.dt-grid-wrap .dt-th').filter({ hasText: 'idade' }).click();
  await page.locator('.dt-grid-wrap .dt-th').filter({ hasText: 'idade' }).click();
  await until(page, () => document.querySelector('.dt-grid-wrap tbody tr[data-i]').dataset.i === '0');
  check('editor:ordena-por-coluna', true);
  check('editor:paginacao', (await page.locator('#dt-prev').isDisabled()) && (await page.locator('#dt-next').isDisabled()));

  // ---- apagar uma linha selecionada
  await page.check('tr[data-i="1"] .dt-sel input');
  await page.click('#dt-del-rows');
  await topFoot(1).click();                                              // confirmar
  await until(page, () => document.querySelectorAll('.dt-grid-wrap tbody tr[data-i]').length === 1);
  check('editor:apaga-linha', (await rows()).total === 1);

  // ---- perfil e limpeza (com prévia)
  await page.click('#dt-btn-profile');
  await page.waitForSelector('.modal .dt-table >> nth=1');
  check('editor:perfil', (await top().locator('.dt-table tbody tr').count()) >= 3);
  await topFoot(0).click();
  await page.click('#dt-btn-clean');
  await page.click('#dt-clean-preview');
  await until(page, () => document.getElementById('dt-clean-out').textContent.trim().length > 5);
  check('editor:limpeza-previa-nao-altera', (await rows()).total === 1);
  await topFoot(0).click();

  // ---- mídia do item: envia um PNG e usa a referência numa célula
  await page.click('#dt-btn-media');
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');
  await page.setInputFiles('#dt-media-file', { name: 'ponto.png', mimeType: 'image/png', buffer: png });
  await page.waitForSelector('.dt-media-card');
  check('midia:upload-aparece', (await page.locator('.dt-media-card').count()) === 1);
  const media = await api(`/api/data/items/dataset/${it.id}/media`);
  check('midia:referencia', media.items[0].ref === 'attachments/ponto.png');
  await topFoot(0).click();
  await page.click('#dt-add-col');
  await page.fill('#dt-newcol-name', 'foto');
  await page.selectOption('#dt-newcol-type', 'image');
  await topFoot(1).click();
  await page.waitForSelector('th:has-text("foto")');
  await page.dblclick('tr[data-i="0"] td[data-field="foto"]');
  await page.fill('.dt-edit', 'attachments/ponto.png');
  await page.keyboard.press('Enter');
  await page.waitForSelector('tr[data-i="0"] td[data-field="foto"] img.dt-thumb');
  const loaded = await page.evaluate(() => new Promise((ok) => { const im = document.querySelector('td[data-field="foto"] img'); if (im.complete) return ok(im.naturalWidth); im.onload = () => ok(im.naturalWidth); im.onerror = () => ok(-1); }));
  check('midia:miniatura-carrega', loaded === 1);

  // ---- histórico
  await page.click('#dt-btn-history');
  await page.waitForSelector('.dt-history-item');
  check('editor:historico', (await page.locator('.dt-history-item').count()) >= 3);
  await topFoot(0).click();

  // ---- fecha o editor; a lista busca e filtra
  await topFoot(0).click();
  await page.waitForTimeout(400);
  await page.evaluate(() => { location.hash = '#/data/datasets'; });
  await page.waitForSelector('.dt-card');
  check('datasets:lista', (await page.locator('.dt-card').count()) >= 1);
  await page.fill('#dt-list-q', 'zzzz-nao-existe');
  await until(page, () => document.querySelectorAll('.dt-card').length === 0);
  await page.fill('#dt-list-q', 'clientes');
  await until(page, () => document.querySelectorAll('.dt-card').length === 1);
  check('lista:busca', true);
  await page.fill('#dt-list-q', '');
  await page.evaluate(() => { location.hash = '#/data/databases'; });
  await page.waitForTimeout(500);
  check('databases:nao-lista-datasets', (await page.locator('.dt-card').count()) === 0);

  // ---- mesclar por chave, com prévia
  const b = await api('/api/data/items', { method: 'POST', body: { kind: 'dataset', name: 'Origem', records: [{ id: '1', content: 'a' }, { id: '2', content: 'b' }] } });
  await page.evaluate(() => { location.hash = '#/data/main'; });
  await page.waitForSelector('#dt-merge-open');
  await page.waitForTimeout(400);
  await page.click('#dt-merge-open');
  await page.waitForSelector('#dt-merge-strategy');
  await page.selectOption('#dt-merge-target', `dataset:${it.id}`);
  await page.selectOption('#dt-merge-source', `dataset:${b.id}`);
  await page.selectOption('#dt-merge-strategy', 'upsert');
  await page.click('#dt-merge-preview');
  await until(page, () => document.getElementById('dt-merge-out').textContent.trim().length > 5);
  check('mesclar:previa', (await rows()).total === 1);
  await topFoot(0).click();                                              // cancelar: nada muda

  // ---- dados sintéticos em massa (sem IA = gerador determinístico)
  await page.evaluate(() => { location.hash = '#/data/synthetic_data'; });
  await page.waitForSelector('#dt-synth-item');
  await page.waitForTimeout(400);
  check('sintetico:modo-duplo', (await page.locator('#dt-synth-mode option').count()) === 2);
  await page.fill('.dt-composer textarea', 'pessoas variadas');
  await page.fill('input[type=number]', '12');
  await page.click('#dt-body .dt-actions button');
  await until(page, () => /Conclu|Done/i.test(document.getElementById('dt-body').textContent), null, 40000);
  const items = (await api('/api/data/items?kind=dataset')).items;
  check('sintetico:gerou-registros', items.some((i) => i.records >= 12), `registros: ${items.map((i) => i.records).join(',')}`);
  check('sintetico:resumo-do-resultado', (await page.locator('.dt-result').count()) === 1);

  // ---- web scraping: aviso e aceite obrigatório
  await page.evaluate(() => { location.hash = '#/data/web_scraping'; });
  await page.waitForSelector('#dt-scrape-ack');
  await page.waitForTimeout(400);
  const warn = (await page.textContent('#dt-body')).toLowerCase();
  check('scraping:aviso-open-source', /open[- ]source/.test(warn) && /comercial|commercial/.test(warn));
  check('scraping:aceite-precisa', (await page.locator('#dt-scrape-ack').count()) === 1);
  check('scraping:guardar-midia', (await page.locator('#dt-scrape-media').count()) === 1);
  await page.fill('#dt-body textarea', 'https://exemplo.org/pagina');
  await page.click('#dt-body .dt-actions button');
  await page.waitForTimeout(600);
  const aviso = (await page.textContent('body')).toLowerCase();                     // a mensagem aparece num aviso (toast) fora de #dt-body
  check('scraping:pede-o-aceite', /confirme|confirm/.test(aviso));

  // ---- upgrade: importar e melhorar (as ações), e a limpeza roda sem IA
  await page.evaluate(() => { location.hash = '#/data/upgrade'; });
  await page.waitForSelector('#dt-up-kind');
  await page.waitForTimeout(400);
  const acts = await page.$$eval('#dt-up-action option', (els) => els.map((e) => e.value));
  check('upgrade:acoes', acts.join(',') === 'enrich,fill_missing,classify,translate,clean,generate');
  check('upgrade:modo-duplo', (await page.locator('#dt-up-mode option').count()) === 2);
  check('upgrade:aceita-xlsx', ((await page.getAttribute('#dt-up-file', 'accept')) || '').includes('.xlsx'));
  await page.selectOption('#dt-up-action', 'classify');
  check('upgrade:classificar-pede-campos', await page.isVisible('#dt-up-fields'));
  await page.selectOption('#dt-up-action', 'generate');
  check('upgrade:gerar-pede-quantidade', await page.isVisible('#dt-up-count'));
  await page.selectOption('#dt-up-action', 'clean');
  await page.selectOption('#dt-up-item', `dataset:${it.id}`);
  await page.click('#dt-up-run');
  await until(page, () => /Conclu|Done/i.test(document.getElementById('dt-body').textContent), null, 30000);
  check('upgrade:limpar-sem-ia', true);

  // ---- exportar em vários formatos
  await page.evaluate(() => { location.hash = '#/data/export'; });
  await page.waitForSelector('#dt-exp-fmt');
  await page.waitForTimeout(400);
  const fmts = await page.$$eval('#dt-exp-fmt option', (els) => els.map((e) => e.value));
  check('export:formatos', ['json', 'jsonl', 'csv', 'tsv', 'xml', 'html', 'md', 'sqlite', 'xlsx', 'sql', 'yaml', 'zip'].every((f) => fmts.includes(f)));
  await page.selectOption('#dt-exp-fmt', 'xlsx');
  await page.click('#dt-body .dt-actions button');
  await until(page, () => document.querySelector('#dt-body a[download]') !== null, null, 20000);
  check('export:gera-arquivo', (await page.locator('#dt-body a[download]').count()) >= 1);
});
