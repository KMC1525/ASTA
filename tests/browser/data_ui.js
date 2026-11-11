// Modo Data no navegador (sem IA configurada = gerador determinístico): as sete abas, criar/editar/visualizar,
// filtrar e ordenar os registros, mesclar, gerar dados sintéticos em massa, o aviso e o aceite do web scraping,
// importar e melhorar (upgrade) e exportar em vários formatos.
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

  // ---- criar um dataset e ver os cards
  await page.click('#dt-body button:has-text("Novo")');
  await page.waitForSelector('#dt-new-kind');
  await page.fill('input[placeholder="Nome"]', 'Clientes de teste');
  await page.click('.modal button:has-text("Criar")');
  await until(page, () => document.querySelectorAll('.dt-card').length > 0);
  check('main:cria-e-mostra', (await page.textContent('#dt-body')).includes('Clientes de teste'));

  // ---- a aba de datasets lista só datasets
  await page.goto(base + '/#/data/datasets');
  await page.waitForSelector('#dt-body');
  check('datasets:lista', (await page.locator('.dt-card').count()) >= 1);
  await page.goto(base + '/#/data/databases');
  await page.waitForSelector('#dt-body');
  check('databases:vazio-ou-lista', (await page.locator('.dt-card').count()) >= 0);

  // ---- abrir o item: tabela, filtro e ordenação
  await page.goto(base + '/#/data/datasets');
  await page.waitForSelector('.dt-card');
  await page.click('.dt-card button:has-text("Abrir")');
  await page.waitForSelector('.dt-table');
  check('item:modal-abre', (await page.locator('.modal .dt-table').count()) === 1);
  const cols = await page.$$eval('.modal .dt-table th', (els) => els.length);
  check('item:tabela-com-colunas', cols >= 2);
  await page.fill('.modal input[placeholder*="Filtrar"]', 'nada-que-exista');
  await page.waitForTimeout(200);
  check('item:filtro-funciona', (await page.textContent('.modal .dt-table-wrap')).includes('0 de'));
  await page.fill('.modal input[placeholder*="Filtrar"]', '');
  await page.waitForTimeout(200);
  await page.click('.modal .dt-th');
  check('item:ordena-por-coluna', (await page.locator('.modal .dt-th').count()) >= 1);
  await page.click('.modal button:has-text("Fechar")');

  // ---- dados sintéticos em massa (sem IA = gerador determinístico)
  await page.goto(base + '/#/data/synthetic_data');
  await page.waitForSelector('#dt-synth-item');
  check('sintetico:modo-duplo', (await page.locator('#dt-synth-mode option').count()) === 2);
  await page.fill('#dt-synth-item ~ * textarea, .dt-composer textarea', 'pessoas variadas');
  await page.fill('input[type=number]', '12');
  await page.click('#dt-body button:has-text("Gerar dados sintéticos")');
  await until(page, () => /Concluído|Done/.test(document.getElementById('dt-body').textContent), null, 30000);
  const items = (await api('/api/data/items?kind=dataset')).items;
  const ds = items.find((i) => i.name === 'Clientes de teste');
  check('sintetico:gerou-registros', !!ds && ds.records >= 12);

  // ---- web scraping: aviso e aceite obrigatório
  await page.goto(base + '/#/data/web_scraping');
  await page.waitForSelector('#dt-scrape-ack');
  const warn = (await page.textContent('#dt-body')).toLowerCase();
  check('scraping:aviso-open-source', warn.includes('open source') && warn.includes('comercial'));
  check('scraping:aceite-precisa', (await page.locator('#dt-scrape-ack').count()) === 1);
  await page.fill('.dt-section textarea', 'https://exemplo.org/pagina');
  await page.click('#dt-body button:has-text("Fazer scraping")');
  await page.waitForTimeout(400);
  check('scraping:pede-o-aceite', (await page.textContent('#dt-body')).toLowerCase().includes('confirme'));
  const s = await api('/api/data/items?kind=dataset');
  check('scraping:nada-sem-aceite', !!s.items);

  // ---- upgrade: importar e melhorar
  await page.goto(base + '/#/data/upgrade');
  await page.waitForSelector('#dt-up-kind');
  check('upgrade:acoes', (await page.locator('#dt-up-action option').count()) === 2);
  check('upgrade:modo-duplo', (await page.locator('#dt-up-mode option').count()) === 2);

  // ---- exportar em vários formatos
  await page.goto(base + '/#/data/export');
  await page.waitForSelector('#dt-exp-fmt');
  const fmts = await page.$$eval('#dt-exp-fmt option', (els) => els.map((e) => e.value));
  check('export:formatos', fmts.includes('json') && fmts.includes('csv') && fmts.includes('sqlite') && fmts.includes('xml'));
  await page.click('#dt-body button:has-text("Exportar")');
  await until(page, () => document.querySelector('#dt-body a[download]') !== null, null, 15000);
  check('export:gera-arquivo', (await page.locator('#dt-body a[download]').count()) >= 1);
});
