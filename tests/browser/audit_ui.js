// v0.4.3 (auditoria): a tela Mundos lista só mundos, textos traduzidos (biblioteca, modelo do Chat), título do Chat legível, Configuração com todas as abas visíveis e o painel de aviso do Demo.
const { run } = require('./_common.js');
run('audit', async ({ open, api, check }) => {
  await api('/api/settings', { method: 'PUT', body: { active: { generation: 'demo', characters: 'auto' }, providers: { lmstudio: { base_url: '', model: '' } } } });
  const wait = async (jobId) => { for (let i = 0; i < 150; i++) { const j = await api('/api/jobs/' + jobId); if (j.status !== 'running') return j; await new Promise((x) => setTimeout(x, 300)); } };
  const g = await api('/api/games/generate', { method: 'POST', body: { prompt: 'Um jogo curto de aventura com um gato (teste da auditoria)', genre: 'platformer', length: 'short' } }); await wait(g.job_id);
  const w = await api('/api/generate', { method: 'POST', body: { prompt: 'Uma ilha tropical com um farol e um pescador (teste da auditoria)' } }); await wait(w.job_id);
  const worlds = await api('/api/projects?kind=world');
  const page = await open({ width: 1360, height: 900 });

  // ---- Mundos: só mundos (antes listava jogos 2D como se fossem mundos)
  await page.evaluate(() => { location.hash = '#/worlds'; }); await page.waitForTimeout(900);
  const names = await page.locator('.list .li .t').allInnerTexts();
  check('mundos:lista-so-mundos', names.length === worlds.length && names.length >= 1 && !names.some((n) => /jogo curto de aventura/i.test(n)));
  check('mundos:o-primeiro-abre-no-editor', (await page.locator('.acc').count()) >= 3 && (await page.locator('.empty h3').count()) === 0);

  // ---- títulos do gerador offline não terminam numa preposição
  const gameName = (await api('/api/projects?kind=game2d')).find((p) => /auditoria|aventura/i.test(p.description || p.name)).name;
  check('titulo:jogo-sem-preposicao-no-fim', !/\b(com|de|um|uma|e|a|o)$/i.test(gameName.trim()) && gameName.split(' ').length <= 8);
  check('titulo:mundo-sem-preposicao-no-fim', !worlds.some((x) => /\b(de|um|uma|com|e|a|o)$/i.test(x.name.trim())));

  // ---- Biblioteca: rótulo do filtro traduzido
  await page.evaluate(() => { location.hash = '#/library'; }); await page.waitForTimeout(900);
  const chips = (await page.locator('.chip').allInnerTexts()).join(' | ');
  check('biblioteca:filtro-de-mundos-em-ingles', /3D worlds/.test(chips) && !/Mundos 3D/.test(chips));

  // ---- Configuração: as 17 abas (em 4 grupos) cabem (quebram de linha) em vez de ficarem escondidas
  await page.evaluate(() => { location.hash = '#/config'; }); await page.waitForTimeout(700);
  const boxes = await page.locator('.tabs button').evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right, vis: r.width > 0 }; }));
  check('config:abas-todas-visiveis', boxes.length === 17 && boxes.every((b) => b.vis && b.r <= 1360 && b.l >= 0) && !(await page.locator('.tabs').evaluate((el) => el.scrollWidth > el.clientWidth + 2)));

  // ---- Chat: título legível, aviso do Demo e rótulo do modelo traduzido na resposta
  await page.evaluate(() => { location.hash = '#/main'; }); await page.waitForSelector('.chx-hero h1', { timeout: 8000 }); await page.waitForTimeout(500);
  const colors = await page.evaluate(() => ({ h1: getComputedStyle(document.querySelector('.chx-hero h1')).color, strong: (() => { const d = document.createElement('i'); d.style.color = 'var(--strong)'; document.body.appendChild(d); const c = getComputedStyle(d).color; d.remove(); return c; })() }));
  check('chat:titulo-com-cor-forte', colors.h1 === colors.strong);
  check('chat:aviso-do-demo-visivel', (await page.locator('.notice').innerText()).includes('Demo mode'));
  await page.fill('.composer textarea', 'Qual a capital da França?'); await page.press('.composer textarea', 'Enter'); await page.waitForSelector('.cmsg.ai .md', { timeout: 15000 });
  check('chat:demo-responde-honesto', /Demo|modo Demo/i.test(await page.locator('.cmsg.ai .md').last().innerText()));
  check('chat:rotulo-do-modelo-traduzido', (await page.locator('.cmsg.ai .who').last().innerText()).includes('Demo (offline, no AI)'));
});
