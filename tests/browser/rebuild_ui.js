// v0.5 Rebuild: ferramenta «Rebuild» no Chat — anexa o ZIP de um jogo (sintético), reconstrói, mostra o AVISO LEGAL no fim e o jogo reconstruído abre e roda (RPG e visual novel).
const fs = require('fs');
const { run, useTool } = require('./_common.js');
run('rebuild', async ({ open, api, check, base, browser }) => {
  const page = await open({ width: 1360, height: 900 });
  await page.waitForSelector('.chx', { timeout: 10000 });
  for (const [label, file, genreLabel] of [['rpg', process.env.ASTA_REBUILD_MV, 'RPG'], ['vn', process.env.ASTA_REBUILD_RPY, 'Visual Novel']]) {
    if (label === 'rpg') { await page.locator('#chat-new').click(); await page.waitForTimeout(300); } else { await page.locator('.result .btn', { hasText: 'Rebuild another game' }).click(); await page.waitForSelector('.chx', { timeout: 8000 }); await page.waitForTimeout(400); }
    await useTool(page, 'rebuild');
    if (label === 'rpg') {
      check('rebuild:titulo-e-dica', (await page.locator('.chx-hero h1').innerText()).includes('rebuild') && (await page.locator('.chx-below').innerText()).toLowerCase().includes('personal use'));
      check('rebuild:run-desligado-sem-arquivo', await page.locator('.composer .send').isDisabled());
    }
    await page.locator('.composer input[type=file]').setInputFiles(file); await page.waitForTimeout(900);
    await page.locator('.composer .send').click();
    await page.waitForSelector('.result', { timeout: 60000 });
    const txt = await page.locator('.result').innerText();
    check(`rebuild:${label}:resultado`, txt.includes(genreLabel) && (await page.locator('.result a[href*="/play/"]').count()) === 1);
    const legal = await page.locator('.result .legal').innerText();
    check(`rebuild:${label}:aviso-legal-com-os-4-pontos`, /Steam/.test(legal) && /Personal use only/.test(legal) && /ASTA's creator nor its contributors/.test(legal) && /be aware of your actions/.test(legal));
    check(`rebuild:${label}:aviso-esta-abaixo-dos-avisos-e-antes-dos-botoes`, await page.evaluate(() => { const l = document.querySelector('.result .legal').getBoundingClientRect(), b = document.querySelector('.result a[href*="/play/"]').getBoundingClientRect(); return l.bottom <= b.top + 1; }));
    const href = await page.locator('.result a[href*="/play/"]').getAttribute('href');
    const pp = await browser.newPage(); const errs = [];
    pp.on('pageerror', (e) => errs.push(e.message)); pp.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
    await pp.goto(base + href); await pp.waitForTimeout(2500);
    for (const k of ['Enter', 'Space', 'ArrowRight', 'ArrowDown', 'Enter', 'Space']) { await pp.keyboard.press(k); await pp.waitForTimeout(250); }
    check(`rebuild:${label}:jogo-abre-e-roda-sem-erros`, (await pp.locator('canvas').count()) >= 1 && errs.length === 0);
    if (errs.length) check(`rebuild:${label}:erros:${errs[0].slice(0, 80)}`, false);
    await pp.close();
  }
  // erro claro com arquivo que não é jogo
  await page.locator('.result .btn', { hasText: 'Rebuild another game' }).click(); await page.waitForSelector('.chx', { timeout: 8000 }); await page.waitForTimeout(400); await useTool(page, 'rebuild');
  await page.locator('.composer input[type=file]').setInputFiles(process.env.ASTA_REBUILD_BAD); await page.waitForTimeout(900);
  await page.locator('.composer .send').click(); await page.waitForSelector('.errbox', { timeout: 30000 });
  check('rebuild:arquivo-invalido-explica', (await page.locator('.errbox').innerText()).includes('ZIP'));
});
