// v0.6.1: cada seção (Mundos, Avatars, Jogos 2D, Rebuild) cria DENTRO da própria página — sem ir ao Chat. O hash nunca vira #/main; o acompanhamento e o resultado aparecem na seção.
const { run } = require('./_common.js');
run('sections_inline', async ({ open, check }) => {
  const page = await open();
  const hash = () => page.evaluate(() => location.hash);
  const go = async (r) => { await page.evaluate((x) => { location.hash = x; }, r); await page.waitForSelector('#creator .composer textarea', { timeout: 15000 }); await page.waitForTimeout(300); };
  for (const [route, text, expect] of [['#/games', 'Uma visual novel romântica num café, com escolhas e três finais', 'a[href*="/play/"]'], ['#/avatars', 'Uma amiga divertida chamada Luna, que adora astronomia', null], ['#/worlds', 'Uma vila medieval numa floresta ao anoitecer', 'a[href*="/play/"]']]) {
    await go(route);
    check(`${route}:compositor-na-secao`, (await page.locator('#creator .composer .send').count()) === 1 && (await page.locator('.chx').count()) === 0);
    await page.fill('#creator .composer textarea', text);
    await page.locator('#creator .composer .send').click();
    await page.waitForSelector('.result', { timeout: 90000 });
    check(`${route}:resultado-na-propria-secao`, (await hash()) === route && (!expect || (await page.locator('.result ' + expect).count()) >= 1));
    await page.locator('.result .btn').last().click(); await page.waitForTimeout(600);   // «Novo…/Criar mais»: volta à seção, não ao Chat
    check(`${route}:botao-novo-volta-para-a-secao`, (await hash()) === route || (await hash()).startsWith(route));
  }
  // Jogos 2D: «Atualizar» num jogo existente usa o compositor da seção (modo atualização)
  await go('#/games');
  await page.locator('.proj .btn:has-text("Update")').first().click(); await page.waitForTimeout(800);
  check('jogos:atualizar-abre-o-compositor-da-secao', (await page.locator('#creator').innerText()).includes('—') && (await hash()) === '#/games');
  await page.locator('#creator .btn:has-text("Create a new one")').click(); await page.waitForTimeout(500);
  check('jogos:criar-um-novo-sai-do-modo-atualizacao', !(await page.locator('#creator').innerText()).includes('—'));
  await go('#/rebuild');
  check('rebuild:compositor-na-secao', (await page.locator('#creator .composer input[type=file]').count()) === 1);
  await page.locator('#creator .composer input[type=file]').setInputFiles(process.env.ASTA_REBUILD_MV); await page.waitForTimeout(900);
  await page.locator('#creator .composer .send').click();
  await page.waitForSelector('.result', { timeout: 60000 });
  check('rebuild:resultado-na-propria-secao-com-aviso-legal', (await hash()) === '#/rebuild' && (await page.locator('.result .legal').count()) === 1);
  // voltar à seção com uma criação em andamento retoma o acompanhamento só nela
  check('chat:continua-funcionando', await page.evaluate(() => { location.hash = '#/main'; return true; }));
  await page.waitForSelector('.chx', { timeout: 10000 });
});
