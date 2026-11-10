// Equipe de agentes em TODAS as seções: o seletor de esforço (Low … Omni) e de agentes (1/4/8/12/16) no Chat, nas ferramentas de criação (mundo, avatar, jogo), no Studio e no Canvas,
// e os cartões «Equipe de agentes» das abas de Configuração (salvar de verdade nas configurações).
const { run, useTool } = require('./_common.js');
run('team', async ({ open, api, check, base }) => {
  await api('/api/settings', { method: 'PUT', body: { language: 'pt-BR', generation: { agents: 1, effort: 'high' }, avatars: { agents: 1, effort: 'high' }, games: { agents: 1, effort: 'high' }, chat: { team_agents: 1, effort: 'low' } } });
  const page = await open({ width: 1400, height: 950 });
  const opts = (sel) => page.locator(`${sel} option`).evaluateAll((os) => os.map((o) => o.value));
  const EFFORTS = 'low,medium,high,extra,mega,max,ultra,omni', AGENTS = '1,4,8,12,16';

  // ---- Chat: seletor ao lado do modelo, valores salvos em Configuração → Chat
  await page.waitForSelector('#chat-team-effort', { timeout: 20000 });
  check('chat:oito-niveis', (await opts('#chat-team-effort')).join(',') === EFFORTS);
  check('chat:agentes-1-4-8-12-16', (await opts('#chat-team-agents')).join(',') === AGENTS);
  check('chat:padrao-low-e-um-agente', (await page.locator('#chat-team-effort').inputValue()) === 'low' && (await page.locator('#chat-team-agents').inputValue()) === '1');
  await page.locator('#chat-team-effort').selectOption('mega'); await page.locator('#chat-team-agents').selectOption('8'); await page.waitForTimeout(700);
  const chat = (await api('/api/settings')).chat;
  check('chat:esforco-e-agentes-salvos', chat.effort === 'mega' && chat.team_agents === 8);

  // ---- ferramentas de criação do Chat: vêm marcadas como em Configuração e seguem no pedido
  for (const [tool, id, key] of [['world', 'world-team', 'generation'], ['avatar', 'avatar-team', 'avatars'], ['game', 'game-team', 'games']]) {
    await page.goto(base + '/#/main'); await page.waitForSelector('.composer');
    await useTool(page, tool);
    await page.waitForSelector(`#${id}-effort`, { timeout: 15000 });
    check(`${tool}:oito-niveis-e-cinco-contagens`, (await opts(`#${id}-effort`)).join(',') === EFFORTS && (await opts(`#${id}-agents`)).join(',') === AGENTS);
    check(`${tool}:vem-marcado-como-na-configuracao`, (await page.locator(`#${id}-effort`).inputValue()) === 'high' && (await page.locator(`#${id}-agents`).inputValue()) === '1');
  }

  // ---- Studio: novo projeto
  await page.goto(base + '/#/studio'); await page.waitForSelector('#st-new-team-effort', { timeout: 15000 });
  check('studio:seletor-no-novo-projeto', (await opts('#st-new-team-effort')).join(',') === EFFORTS && (await opts('#st-new-team-agents')).join(',') === AGENTS);

  // ---- Configuração: um cartão de equipe em cada seção; salvar grava de verdade
  await page.goto(base + '/#/config'); await page.waitForSelector('.cfgtabs');
  const tab = async (id) => { await page.locator(`.cfgtabs button[data-tab="${id}"]`).click(); await page.waitForTimeout(450); };
  const openAcc = async (title) => { await page.locator('.acc .hd', { hasText: new RegExp(title) }).click(); await page.waitForTimeout(250); };
  for (const [id, prefix] of [['chat', 'ch'], ['engine', 'ge'], ['engine', 'gen'], ['avatars', 'av'], ['engine', 'gm'], ['canvas', 'cv'], ['studio', 'st'], ['computer', 'cu'], ['rebuild', 'rb']]) {
    await tab(id);
    if (prefix === 'gen') await openAcc('Mundos 3D|3D worlds');
    if (prefix === 'gm') await openAcc('Jogos 2D|2D games');
    check(`config:${id}-tem-equipe`, (await opts(`#${prefix}-cfg-effort`)).join(',') === EFFORTS && (await opts(`#${prefix}-cfg-agents`)).join(',') === AGENTS);
  }
  await tab('avatars');
  check('config:avatars-equipe-da-conversa', (await opts('#avc-cfg-effort')).join(',') === EFFORTS && (await page.locator('#avc-cfg-effort').inputValue()) === 'low');
  await tab('code');
  check('config:code-agentes-1-4-8-12-16', (await opts('#cd-agents-cfg')).join(',') === AGENTS);

  await tab('engine'); await openAcc('Mundos 3D|3D worlds');
  await page.locator('#gen-cfg-effort').selectOption('omni'); await page.locator('#gen-cfg-agents').selectOption('12');
  check('config:dica-do-custo', /13 chamadas/.test(await page.locator('#gen-fields').innerText()));
  await page.locator('.page.cfg button.btn.primary', { hasText: 'Salvar' }).last().click(); await page.waitForTimeout(900);
  const gen = (await api('/api/settings')).generation;
  check('config:mundos-salvo', gen.effort === 'omni' && gen.agents === 12);
  await page.goto(base + '/#/main'); await page.waitForSelector('.composer'); await useTool(page, 'world'); await page.waitForSelector('#world-team-effort');
  check('world:criacao-usa-o-novo-padrao', (await page.locator('#world-team-effort').inputValue()) === 'omni' && (await page.locator('#world-team-agents').inputValue()) === '12');

  // ---- inglês: os textos novos estão traduzidos
  await api('/api/settings', { method: 'PUT', body: { language: 'en' } });
  await page.goto(base + '/#/config'); await page.reload(); await page.waitForSelector('.cfgtabs'); await tab('engine'); await openAcc('Jogos 2D|2D games');
  const txt = await page.locator('#gm-card').innerText();
  check('ingles:cartao-traduzido', /agent team/i.test(txt) && /Agents in parallel/.test(txt) && !/Equipe de agentes|paralelo|Padrão|lê o código/.test(txt));
  await api('/api/settings', { method: 'PUT', body: { language: 'pt-BR' } });

  // ---- celular: os seletores cabem na tela
  const phone = await open({ width: 390, height: 800 });
  await phone.waitForSelector('#chat-team-effort', { timeout: 20000 });
  check('celular:chat-sem-rolagem-horizontal', await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
});
