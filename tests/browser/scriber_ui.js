// Scriber no navegador (sem IA configurada = regras): lista de textos, as duas abas (Geração automática e Edição), editor estilo Word, seleção por mouse (parágrafo e fala), tamanho da expansão,
// lorebooks (criar, editar, importar, exportar), revisão ortográfica, localizar/substituir, formatação, exportar .docx, importar arquivo, histórico, configuração e tela estreita.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { run, until } = require('./_common');

run('scriber_ui', async ({ base, api, open, check }) => {
  const page = await open();
  const doc = () => page.evaluate(() => document.getElementById('sc-doc').innerText);
  const html = () => page.evaluate(() => document.getElementById('sc-doc').innerHTML);

  // ---- lista de textos e atalhos para as duas abas
  await page.goto(base + '/#/scriber');
  await page.waitForSelector('#sc-new-gen');
  const hasAi = (await api('/api/scriber/status')).text.ai;   // outros testes podem ter configurado um provedor neste servidor
  check('home:ia-aviso', (await page.locator('#sc-ainote').count()) === (hasAi ? 0 : 1));
  check('home:tipos', (await page.locator('#sc-new-type option').count()) >= 12);
  check('home:abas-diretas', (await page.locator('#sc-direct a[data-tab=generate]').count()) === 1 && (await page.locator('#sc-direct a[data-tab=edit]').count()) === 1);
  check('nav:scriber-na-barra', (await page.locator('#side nav a[href="#/scriber"]').count()) === 1);
  await page.selectOption('#sc-new-type', 'journalism');
  await page.fill('#sc-new-name', 'Reportagem de teste');
  await page.click('#sc-new-edit');
  await page.waitForSelector('#sc-doc');
  const pid = (await page.evaluate(() => location.hash)).split('/')[2];
  check('home:cria-e-abre-edicao', /#\/scriber\/[\w-]+\/edit/.test(await page.evaluate(() => location.hash)) && (await page.textContent('#sc-pname')).includes('Reportagem de teste'));
  check('edicao:tipo-no-topo', (await page.textContent('#sc-type')).length > 3);

  // ---- editor: digitar, formatar, estrutura
  await page.click('#sc-doc');
  await page.keyboard.type('Titulo da materia');
  await page.selectOption('#sc-block', 'h1');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Primeiro paragrafo  com erro ,aqui.');
  await page.keyboard.press('Enter');
  await page.keyboard.type('— Olá, disse ela. Segundo parágrafo da história.');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Terceiro parágrafo com "aspas" e mais texto para contar.');
  check('editor:titulo-1', (await html()).startsWith('<h1>Titulo da materia</h1>'));
  await page.click('#sc-doc p:nth-of-type(3)', { clickCount: 3 });
  await page.click('#sc-b');
  check('editor:negrito', (await html()).includes('<b>Terceiro'));
  await page.click('#sc-b');
  await page.click('#sc-ul');
  check('editor:lista', (await html()).includes('<li>'));
  await page.click('#sc-undo');
  await page.click('#sc-pb');
  check('editor:quebra-de-pagina', (await html()).includes('class="pb"'));
  await until(page, () => /palavras|words/.test(document.getElementById('sc-stats').textContent) && !/^0 /.test(document.getElementById('sc-stats').textContent));
  check('editor:contagem', /\d+ (palavras|words)/.test(await page.textContent('#sc-stats')));
  await until(page, () => /salvo|saved/.test(document.getElementById('sc-save').textContent) && !/não|un/.test(document.getElementById('sc-save').textContent), null, 8000);
  const saved = (await api(`/api/scriber/projects/${pid}/document`));
  check('editor:salva-sozinho', saved.stats.words >= 15 && saved.html.includes('<h1>Titulo da materia</h1>'));
  check('editor:html-limpo', !/onclick|<script/.test(saved.html));

  // ---- título editável sincroniza com a barra
  await page.fill('#sc-title', 'Manchete Final');
  await until(page, () => document.querySelector('#sc-pname b').textContent === 'Manchete Final');
  check('editor:renomeia-pelo-titulo', (await api(`/api/scriber/projects/${pid}`)).name === 'Manchete Final');

  // ---- seleção por mouse: parágrafo e fala
  await page.click('#sc-pick button[data-pick=par]');
  await page.click('#sc-doc p:nth-of-type(1)');
  check('selecao:paragrafo', /Seleção|Selection/.test(await page.textContent('#sc-selinfo')) && /5 (palavras|words)/.test(await page.textContent('#sc-selinfo')));
  await page.click('#sc-doc p:nth-of-type(2)', { modifiers: ['Shift'] });
  check('selecao:shift-estende', /12 (palavras|words)/.test(await page.textContent('#sc-selinfo')) || /1\d (palavras|words)/.test(await page.textContent('#sc-selinfo')));
  await page.click('#sc-pick button[data-pick=dlg]');
  await page.click('#sc-doc p:nth-of-type(2)');
  check('selecao:fala', /(fala|dialogue)/.test(await page.textContent('#sc-selinfo')));
  await page.click('#sc-pick button[data-pick=free]');
  await page.click('#sc-doc p:nth-of-type(1)', { clickCount: 3 });
  await page.waitForSelector('#sc-float');
  check('selecao:barra-flutuante', (await page.locator('#sc-float button').count()) === 4);
  check('selecao:painel-direito', (await page.textContent('#sc-selbox')).length > 10 && !(await page.textContent('#sc-selbox')).includes('Selecione um trecho'));

  // ---- tamanho da expansão (parágrafos e diálogos)
  await page.click('#sc-exp-mode button[data-mode=total]');
  check('expansao:modo-resultado', (await page.locator('#sc-exp-mode button.on[data-mode=total]').count()) === 1);
  await page.click('#sc-exp-mode button[data-mode=add]');
  await page.locator('#sc-sizebox .sc-sizerow').nth(0).locator('.chip[data-n="400"]').click();
  check('expansao:chip-paragrafo', (await page.inputValue('#sc-exp-par')) === '400');
  await page.fill('#sc-exp-dlg', '90');
  check('expansao:numero-fala', (await page.inputValue('#sc-exp-dlg-r')) === '90');
  const ex = await page.evaluate(() => JSON.parse(localStorage.getItem('asta.scriber.expand')));
  check('expansao:guardada', ex.par === 400 && ex.dlg === 90 && ex.mode === 'add');

  // ---- ações da IA sem IA: Corrigir funciona com regras; Expandir avisa que não dá
  await page.click('#sc-doc p:nth-of-type(1)', { clickCount: 3 });
  await page.click('#sc-act-fix');
  await page.waitForSelector('#sc-sugg-accept', { timeout: 20000 });
  check('ia:corrigir-regras', (await page.textContent('#sc-sugg-text')).includes('com erro, aqui.'));
  await page.click('#sc-sugg-accept');
  check('ia:aceitar-nao-junta-paragrafos', (await page.locator('#sc-doc p').count()) >= 3 && (await doc()).includes('com erro, aqui.'));
  await page.click('#sc-doc p:nth-of-type(2)', { clickCount: 3 });
  await page.click('#sc-act-expand');
  await page.waitForSelector('#sc-sugg-card.warn', { timeout: 20000 });
  check('ia:expandir-sem-ia-e-honesto', /(Nothing|Nada)/.test(await page.textContent('#sc-sugg-card')));
  await page.click('#sc-doc p:nth-of-type(2)', { clickCount: 3 });
  await page.click('#sc-act-tone');
  check('ia:tom-pede-instrucao', (await page.locator('#sc-instr:focus').count()) === 1);

  // ---- revisão ortográfica (regras, sem IA)
  await page.click('#sc-rtab-review');
  await page.click('#sc-doc');
  await page.keyboard.press('Control+End');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Mais   uma frase  com espaços , errados e repetida repetida.');
  await page.click('#sc-review');
  await until(page, () => document.querySelectorAll('.sc-issue').length > 0);
  const n0 = await page.locator('.sc-issue').count();
  check('revisao:achados', n0 >= 3);
  await page.locator('.sc-issue [data-act=apply]').first().click();
  check('revisao:aplicar-um', (await page.locator('.sc-issue').count()) < n0);
  await page.click('#sc-review-all');
  await until(page, () => /Nenhum problema|No problems/.test(document.getElementById('sc-review-info').textContent), null, 15000);
  check('revisao:aplicar-todas', !(await doc()).includes('  ') && !(await doc()).includes(' ,'));
  await page.click('#sc-typo');
  await until(page, () => document.querySelector('#sc-doc').innerText.includes('“aspas”'), null, 8000);
  check('revisao:tipografia', (await doc()).includes('“aspas”'));
  check('revisao:aviso-dicionario', (await page.textContent('#sc-dict')).length > 20);

  // ---- localizar e substituir
  await page.click('#sc-doc');
  await page.keyboard.press('Control+h');
  await page.fill('#sc-find', 'parágrafo');
  await page.fill('#sc-replace', 'trecho');
  await page.click('#sc-frepall');
  check('localizar:substituir-tudo', !(await doc()).includes('parágrafo') && (await doc()).includes('trecho'));

  // ---- lorebooks: criar, entradas, editar, persistir, exportar, importar
  await page.click('#sc-lore-new');
  await page.fill('#sc-lore-newname', 'Mundo da história');
  await page.click('.modal .btn.primary');
  await page.waitForSelector('.sc-book');
  await page.locator('.sc-book [data-act=add-entry]').first().click();
  await page.waitForSelector('.sc-entry.edit');
  await page.locator('.sc-entry.edit input').first().fill('Ana');
  await page.locator('.sc-entry.edit input').nth(1).fill('Ana, anita');
  await page.locator('.sc-entry.edit textarea').fill('Ana é ruiva e corajosa.');
  await page.locator('.sc-entry.edit .check input').first().check();
  await page.locator('.sc-entry.edit .btn.primary').click();
  await page.locator('.sc-book [data-act=add-entry]').first().click();
  await page.locator('.sc-entry.edit select').selectOption('system');
  await page.locator('.sc-entry.edit input').first().fill('Voz');
  await page.locator('.sc-entry.edit textarea').fill('Escreva sempre no passado.');
  await page.locator('.sc-entry.edit .btn.primary').click();
  await page.waitForTimeout(900);
  const books = (await api(`/api/scriber/projects/${pid}/lorebooks`)).books;
  check('lore:salva-no-servidor', books.length === 1 && books[0].entries.length === 2 && books[0].entries[0].keys.join() === 'Ana,anita' && books[0].entries[0].always === true && books[0].entries[1].kind === 'system');
  check('lore:contador', (await page.textContent('#sc-lore-count')) === '2');
  await page.reload();
  await page.waitForSelector('#sc-lore-list .sc-book');
  check('lore:persiste-ao-recarregar', (await page.locator('.sc-entry').count()) === 0 || (await page.locator('.sc-book').count()) === 1);
  await page.locator('.sc-book .sc-chev').first().click();
  check('lore:entradas-listadas', (await page.locator('.sc-entry').count()) === 2);
  const loreFile = path.join(os.tmpdir(), 'asta-lore-' + Date.now() + '.json');
  fs.writeFileSync(loreFile, JSON.stringify({ entries: { 0: { key: ['Dragão'], content: 'Um dragão antigo.', comment: 'Dragão' } } }));
  await page.setInputFiles('#sc-lore-import', loreFile).catch(async () => { await page.click('#sc-lore-imp'); await page.setInputFiles('#sc-lore-import', loreFile); });
  await until(page, () => document.querySelectorAll('.sc-book').length === 2);
  check('lore:importa-sillytavern', (await page.locator('.sc-book').count()) === 2);
  const exp = await fetch(`${base}/api/scriber/projects/${pid}/lorebooks/${books[0].id}/export`).then((r) => r.json());
  check('lore:exporta-json', exp.type === 'asta.lorebook' && exp.entries.length === 2);
  await page.click('#sc-lore-toggle');
  check('lore:esconde-painel', await page.evaluate(() => document.getElementById('sc-grid').classList.contains('nolore')));
  await page.click('#sc-lore-toggle');

  // ---- formatação do documento
  await page.click('#sc-props');
  await page.waitForSelector('#sc-fm-font');
  await page.selectOption('#sc-fm-font', 'Arial');
  await page.selectOption('#sc-fm-page', 'Letter');
  await page.fill('#sc-fm-size', '13');
  await page.check('#sc-fm-toc');
  await page.click('.modal .btn.primary');
  await until(page, () => document.querySelector('#sc-page').style.getPropertyValue('--pf').includes('Arial'));
  const meta = await api(`/api/scriber/projects/${pid}`);
  check('formato:aplicado-e-salvo', meta.format.font === 'Arial' && meta.format.page === 'Letter' && meta.format.size === 13 && meta.format.toc === true);
  await page.selectOption('#sc-lang', 'en-US');
  await until(page, () => document.getElementById('sc-doc').getAttribute('lang') === 'en-US');
  check('idioma:vai-para-o-editor', true);
  await page.waitForTimeout(900);
  check('idioma:salvo', (await api(`/api/scriber/projects/${pid}`)).language === 'en-US');

  // ---- exportar .docx pelo botão, histórico e importar
  const [dl] = await Promise.all([page.waitForEvent('download'), page.click('#sc-export')]);
  const file = await dl.path();
  const bytes = fs.readFileSync(file);
  check('docx:baixa-zip-valido', bytes.slice(0, 2).toString() === 'PK' && bytes.includes(Buffer.from('word/document.xml')) && dl.suggestedFilename().endsWith('.docx'));
  await page.click('#sc-menu');
  await page.locator('.pop .opt', { hasText: /Histórico|History/ }).click();
  await page.waitForSelector('.modal');
  check('historico:abre', (await page.locator('.modal').count()) === 1);
  await page.keyboard.press('Escape');
  const mdFile = path.join(os.tmpdir(), 'asta-import-' + Date.now() + '.md');
  fs.writeFileSync(mdFile, '# Importado\n\nTexto que veio de um arquivo **markdown**.\n');
  await page.click('#sc-menu');
  await page.locator('.pop .opt', { hasText: /Importar arquivo|Import file/ }).click();
  await page.setInputFiles('#sc-import-file', mdFile);
  await page.waitForSelector('.modal');
  await page.locator('.modal .btn', { hasText: /Substituir|Replace/ }).click();
  await until(page, () => document.getElementById('sc-doc') && document.getElementById('sc-doc').innerText.includes('veio de um arquivo'));
  check('importar:substitui-e-guarda-historico', (await api(`/api/scriber/projects/${pid}/history`)).items.length >= 1 && (await html()).includes('<h1>Importado</h1>'));

  // ---- Geração automática
  await page.click('.sc-tab[data-tab=generate]');
  await page.waitForSelector('#sc-gen-composer');
  check('geracao:aba-abre', (await page.locator('#sc-types .sc-typebtn').count()) >= 12);
  check('geracao:selo-de-ia', (await page.locator(hasAi ? '#sc-gen-ai.ok' : '#sc-gen-ai.warn').count()) === 1);
  await page.click('#sc-types .sc-typebtn[data-type=scientific]');
  check('geracao:tipo-muda-formato', (await page.inputValue('#sc-fm-preset')) === 'academic' && (await page.inputValue('#sc-fm-font')) === 'Times New Roman');
  await page.fill('#sc-gen-pages', '3');
  await page.fill('#sc-gen-wpp', '200');
  await until(page, () => /600/.test(document.getElementById('sc-gen-size').textContent));
  check('geracao:meta-paginas-x-palavras', /600/.test(await page.textContent('#sc-gen-size')));
  await page.selectOption('#sc-gen-lang', 'en-US');
  await page.fill('#sc-gen-composer textarea', '# Introduction\n- why it matters\n# Method\n- how we did it\n# Results\n- what we found');
  await page.click('#sc-gen-composer .send');
  await page.waitForSelector('#sc-gen-result', { timeout: 60000 });
  check('geracao:resultado-e-docx', (await page.locator('#sc-gen-docx').count()) === 1 && (await page.getAttribute('#sc-gen-docx', 'href')).includes('/exports/'));
  const gres = await api(`/api/scriber/projects/${pid}/document`);
  check('geracao:esboco-vira-secoes', (gres.html.match(/<h1>/g) || []).length === 3 && gres.html.includes('Introduction'));
  const dl2 = await fetch(base + (await page.getAttribute('#sc-gen-docx', 'href')));
  const buf = Buffer.from(await dl2.arrayBuffer());
  check('geracao:docx-baixavel', buf.slice(0, 2).toString() === 'PK' && dl2.headers.get('content-type').includes('wordprocessingml'));
  await page.click('#sc-gen-open');
  await page.waitForSelector('#sc-doc');
  check('geracao:abre-na-edicao', (await html()).includes('<h1>Method</h1>'));
  check('geracao:historico-do-anterior', (await api(`/api/scriber/projects/${pid}/history`)).items.some((i) => /gerar|generat/i.test(i.label)));

  // ---- rotas diretas para as abas, configuração e barra lateral
  await page.goto(base + '/#/scriber/generate');
  await page.waitForSelector('#sc-gen-composer');
  await page.goto(base + '/#/scriber/edit');
  await page.waitForSelector('#sc-doc');
  check('rotas:abas-diretas', true);
  await page.goto(base + '/#/config');
  await page.waitForSelector('.cfgtabs');
  await page.locator('.cfgtabs [data-tab=scriber], .cfgtabs button', { hasText: /^Scriber$/ }).first().click();
  await page.waitForSelector('#sc-card, #cfg-scriber-status');
  check('config:aba-scriber', (await page.locator('#cfg-scriber-status').count()) === 1 && (await page.locator('#sc-card').count()) === 1);
  check('config:prompts-internos', (await page.locator('.cu-cfg-prompts details').count()) >= 6);

  // ---- tela estreita: as abas continuam acessíveis
  const mobile = await open({ width: 390, height: 844 });
  await mobile.goto(`${base}/#/scriber/${pid}/edit`);
  await mobile.waitForSelector('#sc-doc');
  check('mobile:editor-e-painel-na-mesma-pagina', (await mobile.locator('#sc-right').count()) === 1 && (await mobile.locator('#sc-toolbar').count()) === 1);
  await mobile.goto(`${base}/#/scriber/${pid}/generate`);
  await mobile.waitForSelector('#sc-gen-composer');
  check('mobile:geracao', (await mobile.locator('#sc-types').count()) === 1);
});
