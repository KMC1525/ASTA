// Relações dos avatars: namorada, namorado, esposa e marido aparecem na criação e no editor, e o seletor não corta o texto.
const { run, useTool } = require('./_common.js');
run('relationships', async ({ open, api, check }) => {
  const page = await open({ width: 1300, height: 900 });
  await page.evaluate(() => { location.hash = '#/main'; }); await page.waitForTimeout(500);
  await useTool(page, 'avatar');
  const sel = page.locator('.composer select').filter({ has: page.locator('option', { hasText: 'Relationship: automatic' }) });
  const opts = await sel.locator('option').allInnerTexts();
  check('rel:opcoes-na-criacao', ['Girlfriend', 'Boyfriend', 'Wife', 'Husband'].every((x) => opts.includes(x)) && opts.includes('Friend') && opts.includes('Partner'));
  const fits = async (s) => s.evaluate((el) => {
    const txt = el.options[el.selectedIndex].text, span = document.createElement('span'), cs = getComputedStyle(el);
    span.style.cssText = `position:absolute;visibility:hidden;white-space:nowrap;font:${cs.font}`; span.textContent = txt; document.body.appendChild(span);
    const w = span.getBoundingClientRect().width; span.remove();
    return w <= el.getBoundingClientRect().width - parseFloat(cs.paddingRight) - parseFloat(cs.paddingLeft) + 1;
  });
  check('rel:texto-nao-e-cortado-automatica', await fits(sel));
  await sel.selectOption({ label: 'Girlfriend' }); await page.waitForTimeout(200);
  check('rel:texto-nao-e-cortado-namorada', await fits(sel));
  await sel.selectOption({ label: 'Husband' }); await page.waitForTimeout(200);
  check('rel:texto-nao-e-cortado-marido', await fits(sel));

  // editor do avatar: as quatro opções, e salvar mantém
  await page.evaluate(() => { location.hash = '#/avatars/edit/new'; }); await page.waitForTimeout(700);
  const ed = page.locator('select').filter({ has: page.locator('option', { hasText: 'Wife' }) }).first();
  const eopts = await ed.locator('option').allInnerTexts();
  check('rel:opcoes-no-editor', ['Girlfriend', 'Boyfriend', 'Wife', 'Husband'].every((x) => eopts.includes(x)));
  await page.locator('input[placeholder^="E.g"]').first().fill('Marta');
  await ed.selectOption({ label: 'Wife' });
  await page.locator('.seg button:text-is("NSFW")').click(); await page.waitForTimeout(200);
  await page.locator('.btn', { hasText: 'Save' }).first().click(); await page.waitForTimeout(900);
  const saved = (await api('/api/avatars')).find((a) => a.name === 'Marta');
  check('rel:salvou-esposa-nsfw', saved && saved.relationship === 'wife' && saved.content === 'nsfw' && saved.gender === 'female');
  // a lista mostra o rótulo certo
  await page.evaluate(() => { location.hash = '#/avatars'; }); await page.waitForTimeout(700);
  check('rel:lista-mostra-esposa', (await page.locator('.av-card', { hasText: 'Marta' }).locator('.chip', { hasText: 'Wife' }).count()) === 1);
});
