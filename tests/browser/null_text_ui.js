// v0.17.44: nenhuma tela escreve o texto «null»/«undefined»/«NaN» (era `replaceChildren(…, null)` do DOM nativo nas telas de criação e no botão Fontes).
const { run } = require('./_common.js');
run('null_text', async ({ open, api, check }) => {
  await api('/api/settings', { method: 'PUT', body: { language: 'pt-BR' } });
  const page = await open({ width: 1300, height: 900 });
  await page.waitForSelector('.composer .send');
  check('botao-enviar-sem-texto-solto', !(await page.locator('.composer .send').first().innerText()).includes('null'));
  for (const r of ['main', 'worlds', 'avatars', 'games', 'canvas', 'studio', 'code', 'rebuild', 'library', 'config']) {
    await page.evaluate((x) => { location.hash = '#/' + x; }, r); await page.waitForTimeout(700);
    const txt = await page.locator('body').innerText();
    check(`${r}:sem-null-undefined-nan`, !/\bnull\b|\bundefined\b|\bNaN\b|\[object Object\]/.test(txt));
  }
});
