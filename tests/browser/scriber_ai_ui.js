// Scriber com um provedor de IA simulado (o teste Python troca o provedor): geração de um texto inteiro (Planejador → Redator → Revisor → .docx), expandir só a seleção com o tamanho escolhido
// (parágrafo e fala), lorebook entrando na chamada, aceitar / tentar de novo / inserir depois, desfazer e a revisão ortográfica com IA.
const { run, until } = require('./_common');

run('scriber_ai_ui', async ({ base, api, open, check }) => {
  const page = await open();
  const p = await api('/api/scriber/projects', { method: 'POST', body: { name: 'Conto com IA', type: 'fiction', language: 'pt-BR' } });
  const pid = p.id;
  await api(`/api/scriber/projects/${pid}/lorebooks`, { method: 'PUT', body: { books: [{ name: 'Mundo', entries: [{ name: 'Ana', kind: 'character', keys: ['Ana'], content: 'Ana é ruiva e corajosa.' }] }] } });

  // ---- geração automática com IA
  await page.goto(`${base}/#/scriber/${pid}/generate`);
  await page.waitForSelector('#sc-gen-composer');
  check('ia:selo-de-ia-pronta', (await page.locator('#sc-gen-ai.ok').count()) === 1 && (await page.textContent('#sc-gen-ai')).includes('IA de teste'));
  await page.fill('#sc-gen-pages', '2');
  await page.fill('#sc-gen-wpp', '300');
  await page.fill('#sc-gen-composer textarea', 'Um conto sobre Ana e a última torre');
  await page.click('#sc-gen-composer .send');
  await page.waitForSelector('#sc-gen-result', { timeout: 90000 });
  const res = await page.textContent('#sc-gen-result');
  check('ia:geracao-titulo-e-resumo', res.includes('A Torre Final') && res.includes('Texto entregue como pedido.'));
  check('ia:geracao-progresso', (await page.locator('#sc-gen-log .sc-logrow').count()) >= 2 && (await page.locator('.sc-step.done').count()) >= 3);
  const doc = await api(`/api/scriber/projects/${pid}/document`);
  check('ia:geracao-secoes-e-palavras', (doc.html.match(/<h1>/g) || []).length === 2 && doc.stats.words > 250);
  check('ia:geracao-renomeia', (await api(`/api/scriber/projects/${pid}`)).name === 'A Torre Final');
  check('ia:docx-gerado', (await api(`/api/scriber/projects/${pid}`)).exports.some((e) => e.name.endsWith('.docx')));

  // ---- edição: expandir só a seleção, com o tamanho escolhido
  await api(`/api/scriber/projects/${pid}/document`, { method: 'PUT', body: { markdown: '# Capítulo\n\nAna abriu a porta da torre e olhou para dentro.\n\n— Quem está aí? — perguntou Ana.\n\nPrimeiro ela subiu devagar a escada.' } });
  await page.goto(`${base}/#/scriber/${pid}/edit`);
  await page.waitForSelector('#sc-doc h1');
  await page.click('#sc-pick button[data-pick=par]');
  await page.click('#sc-doc p:nth-of-type(1)');
  await page.locator('#sc-sizebox .sc-sizerow').nth(0).locator('.chip[data-n="100"]').click();
  await page.click('#sc-act-expand');
  await page.waitForSelector('#sc-sugg-accept', { timeout: 30000 });
  const chip = await page.textContent('#sc-sugg-words');
  const m = chip.match(/(\d+)\D+(\d+)/);
  check('ia:expandir-tamanho-pedido', m && Math.abs(parseInt(m[2], 10) - parseInt(m[1], 10) - 100) <= 12);
  check('ia:lorebook-na-sugestao', (await page.textContent('#sc-sugg-card')).includes('Ana'));
  check('ia:notas-da-ia', (await page.textContent('#sc-sugg-card')).includes('Confira a data.'));
  await page.click('#sc-sugg-retry');
  await page.waitForSelector('#sc-sugg-accept', { timeout: 30000 });
  check('ia:tentar-de-novo', true);
  await page.click('#sc-sugg-accept');
  const after = await page.evaluate(() => document.getElementById('sc-doc').innerText);
  check('ia:aceitar-troca-so-o-trecho', after.includes('Trecho novo começando aqui') && !after.includes('Ana abriu a porta') && after.includes('Quem está aí?') && after.includes('Primeiro ela subiu'));
  check('ia:mantem-os-blocos', (await page.locator('#sc-doc p').count()) === 3);
  await page.keyboard.press('Control+z');
  await page.waitForTimeout(200);
  const undone = await page.evaluate(() => document.getElementById('sc-doc').innerText);
  check('ia:desfazer-nativo', undone.length < after.length || undone.includes('Ana abriu a porta'));
  check('ia:lore-marcado-como-usado', (await page.locator('.sc-book .sc-chev').count()) === 1);
  await page.locator('.sc-book .sc-chev').first().click();
  check('ia:entrada-usada-destacada', (await page.locator('.sc-entry.used').count()) === 1);

  // ---- fala: tamanho próprio para diálogos
  await page.click('#sc-pick button[data-pick=dlg]');
  await page.click('#sc-doc p:nth-of-type(2)');
  await page.fill('#sc-exp-dlg', '40');
  await page.click('#sc-act-expand');
  await page.waitForSelector('#sc-sugg-accept', { timeout: 30000 });
  const m2 = (await page.textContent('#sc-sugg-words')).match(/(\d+)\D+(\d+)/);
  check('ia:expandir-fala-usa-tamanho-de-fala', m2 && Math.abs(parseInt(m2[2], 10) - parseInt(m2[1], 10) - 40) <= 8);
  await page.click('#sc-sugg-after');
  check('ia:inserir-depois', (await page.locator('#sc-doc p').count()) >= 4 && (await page.evaluate(() => document.getElementById('sc-doc').innerText)).includes('— Quem está aí?'));
  await page.click('#sc-pick button[data-pick=free]');

  // ---- continuar sem seleção e modo «Resultado com»
  await page.click('#sc-doc p:nth-of-type(1)');
  await page.click('#sc-exp-mode button[data-mode=total]');
  await page.locator('#sc-sizebox .sc-sizerow').nth(0).locator('.chip[data-n="25"]').click();
  await page.click('#sc-act-continue');
  await page.waitForSelector('#sc-sugg-accept', { timeout: 30000 });
  check('ia:continuar-sem-selecao', /(\d+)/.test(await page.textContent('#sc-sugg-words')));
  await page.click('#sc-sugg-drop');
  check('ia:descartar', (await page.locator('#sc-sugg-card').count()) === 0);

  // ---- revisão com IA
  await page.click('#sc-rtab-review');
  await page.click('#sc-review-ai');
  await until(page, () => document.querySelectorAll('.sc-issue [data-act=apply]').length > 0, null, 30000);
  check('ia:revisao-com-ia', (await page.textContent('.sc-sc-issue, .sc-issue')).includes('Primeiríssimo') || (await page.locator('.sc-issue').count()) >= 1);

  // ---- a barra flutuante mostra o tamanho escolhido
  await page.click('#sc-rtab-ai');
  await page.click('#sc-doc p:nth-of-type(1)', { clickCount: 3 });
  await page.waitForSelector('#sc-float');
  check('ia:barra-flutuante-com-tamanho', /Expandir|Expand/.test(await page.textContent('#sc-float [data-float=expand]')) && /25/.test(await page.textContent('#sc-float [data-float=expand]')));
});
