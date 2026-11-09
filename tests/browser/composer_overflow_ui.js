// A barra do compositor com muitas opções (Avatares) não vaza da caixa: quebra em duas linhas, com o Run dentro dela.
const { run, useTool } = require('./_common.js');
run('composer-overflow', async ({ open, api, check }) => {
  await api('/api/settings', { method: 'PUT', body: { language: 'pt-BR' } });
  for (const width of [1400, 1100, 900]) {
    const page = await open({ width, height: 900 });
    await page.waitForSelector('.composer');
    await useTool(page, 'avatar');
    await page.waitForSelector('#avatar-team-effort', { timeout: 15000 });
    const r = await page.evaluate(() => {
      const box = document.querySelector('.composer').getBoundingClientRect();
      const out = [...document.querySelectorAll('.composer .tools > *:not(input), .composer .tools .send')].filter((e) => e.offsetParent).map((e) => e.getBoundingClientRect()).filter((b) => b.right > box.right + 1 || b.left < box.left - 1);
      return { out: out.length };
    });
    check(`avatares:${width}-tudo-dentro-da-caixa`, r.out === 0);
    await page.close();
  }
  const phone = await open({ width: 390, height: 800 });
  await phone.waitForSelector('.composer');
  check('celular:sem-rolagem-horizontal', await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
});
