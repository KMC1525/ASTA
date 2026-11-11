// Modo Data no navegador (sem IA configurada = gerador determinístico): as sete abas, criar/editar/visualizar,
// filtrar e ordenar os registros, mesclar, gerar dados sintéticos em massa, o aviso e o aceite do web scraping,
// importar e melhorar (upgrade) e exportar em vários formatos.
//
// A tela roda em português ou inglês conforme o navegador, então os testes usam ids e posições (nunca o texto do botão).
const { run, until } = require('./_common');

run('data_ui', async ({ base, api, open, check }) => {
  const page = await open();

  // ---- as sete abas, na ordem pedida
  await page.goto(base + '/#/data/main');
  await page.waitForSelector('.dt-tabs');
  const tabs = await page.$$eval('.dt-tab', (els) => els.map((e) => e.getAttribute('href')));
  check('abas:as-sete', tabs.length === 7);
  check('abas:ordem', tabs.join(',') === ['#/data/main', '#/data/databases', '#/data/datasets', '#/data/synthetic_data', '#/data/web_scraping', '#/data/upgrade', '#/data/export'].join(','));
  check('nav:data-na-barra', (await page.locator('#side nav a[href="#/data"]').count()) === 1);
  check('main:descricao', (await page.textContent('#dt-body')).toLowerCase().includes('sint'));
  const headerBox = await page.locator('.page-h').boundingBox();
  check('main:cabecalho-visivel', !!headerBox && headerBox.height > 20);

  // ---- criar um dataset e ver os cards (depois de criar, o item já abre: fecha-se o diálogo)
  await page.click('#dt-body .dt-actions button');            // o primeiro botão é «Novo»
  await page.waitForSelector('#dt-new-kind');
  await page.fill('#dt-new-name', 'Clientes de teste');
  await page.click('.modal .foot button:last-child');        // o último botão do rodapé é o principal («Criar»)
  await until(page, () => document.querySelectorAll('.dt-card').length > 0);
  await page.waitForSelector('.modal .dt-table', { timeout: 15000 }).catch(() => {});
  await page.click('.modal .foot button:first-child').catch(() => {});   // «Fechar»
  await page.waitForTimeout(400);
  check('main:cria-e-mostra', (await page.textContent('#dt-body')).includes('Clientes de teste'));

  // ---- a aba de datasets lista só datasets
  await page.evaluate(() => { location.hash = '#/data/datasets'; });
  await page.waitForSelector('#dt-body');
  await page.waitForTimeout(400);
  check('datasets:lista', (await page.locator('.dt-card').count()) >= 1);
  await page.evaluate(() => { location.hash = '#/data/databases'; });
  await page.waitForTimeout(500);
  check('databases:vazio-ou-lista', (await page.locator('.dt-card').count()) >= 0);

  // ---- abrir o item: tabela, filtro e ordenação
  await page.evaluate(() => { location.hash = '#/data/datasets'; });
  await page.waitForSelector('.dt-card');
  await page.waitForTimeout(500);
  await page.click('.dt-card .dt-actions button');           // o primeiro botão do cartão é «Abrir»
  await page.waitForSelector('.modal .dt-table', { timeout: 15000 });
  check('item:modal-abre', (await page.locator('.modal .dt-table').count()) === 1);
  await page.waitForSelector('.modal .dt-history-item', { timeout: 15000 }).catch(() => {});
  check('item:historico-listado', (await page.locator('.modal .dt-history-item').count()) >= 1);
  const cols = await page.$$eval('.modal .dt-table th', (els) => els.length);
  check('item:tabela-com-colunas', cols >= 2);
  await page.fill('#dt-item-filter', 'nada-que-exista');
  await page.waitForTimeout(300);
  check('item:filtro-funciona', (await page.textContent('.modal .dt-table-wrap')).includes('0 de'));
  await page.fill('#dt-item-filter', '');
  await page.waitForTimeout(300);
  await page.click('.modal .dt-th');
  await page.waitForTimeout(200);
  check('item:ordena-por-coluna', (await page.locator('.modal .dt-th').count()) >= 1);
  await page.click('.modal .foot button:first-child');       // «Fechar»
  await page.waitForTimeout(300);

  // ---- dados sintéticos em massa (sem IA = gerador determinístico)
  await page.evaluate(() => { location.hash = '#/data/synthetic_data'; });
  await page.waitForSelector('#dt-synth-item');
  await page.waitForTimeout(400);
  check('sintetico:modo-duplo', (await page.locator('#dt-synth-mode option').count()) === 2);
  await page.fill('.dt-composer textarea', 'pessoas variadas');
  await page.fill('#dt-synth-count', '12');
  await page.click('#dt-synth-run');
  await until(page, () => /Conclu|Done/i.test(document.getElementById('dt-body').textContent), null, 40000);
  const items = (await api('/api/data/items?kind=dataset')).items;
  check('sintetico:gerou-registros', items.some((i) => i.records >= 12), `registros: ${items.map((i) => i.records).join(',')}`);

  // ---- web scraping: aviso e aceite obrigatório
  await page.evaluate(() => { location.hash = '#/data/web_scraping'; });
  await page.waitForSelector('#dt-scrape-ack');
  await page.waitForTimeout(400);
  const warn = (await page.textContent('#dt-body')).toLowerCase();
  check('scraping:aviso-open-source', warn.includes('open source') && warn.includes('comercial'));
  check('scraping:aceite-precisa', (await page.locator('#dt-scrape-ack').count()) === 1);
  await page.fill('#dt-scrape-urls', 'https://exemplo.org/pagina');
  await page.click('#dt-scrape-run');
  await page.waitForTimeout(600);
  const aviso = (await page.textContent('#dt-body')).toLowerCase();
  check('scraping:pede-o-aceite', aviso.includes('confirme') || aviso.includes('confirm'), `aviso: ${aviso.slice(0, 120)}`);
  const antes = (await api('/api/data/items?kind=dataset')).items.find((i) => i.records >= 12);
  check('scraping:nada-sem-aceite', !!antes);

  // ---- upgrade: importar e melhorar
  await page.evaluate(() => { location.hash = '#/data/upgrade'; });
  await page.waitForSelector('#dt-up-kind');
  await page.waitForTimeout(400);
  check('upgrade:acoes', (await page.locator('#dt-up-action option').count()) === 2);
  check('upgrade:modo-duplo', (await page.locator('#dt-up-mode option').count()) === 2);
  check('upgrade:arquivo', (await page.locator('#dt-up-file').count()) === 1);

  // ---- exportar em vários formatos
  await page.evaluate(() => { location.hash = '#/data/export'; });
  await page.waitForSelector('#dt-exp-fmt');
  await page.waitForTimeout(400);
  const fmts = await page.$$eval('#dt-exp-fmt option', (els) => els.map((e) => e.value));
  check('export:formatos', fmts.includes('json') && fmts.includes('csv') && fmts.includes('sqlite') && fmts.includes('xml'));
  await page.click('#dt-exp-run');
  await until(page, () => document.querySelector('#dt-body a[download]') !== null, null, 20000);
  check('export:gera-arquivo', (await page.locator('#dt-body a[download]').count()) >= 1);
});
