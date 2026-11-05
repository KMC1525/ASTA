// Chat 2.0: layout limpo (anexos à esquerda · modelo e Run à direita), resposta em streaming com markdown, troca de modelo, Parar/responder de novo, histórico
// e — o ponto central — as criações (mundo/avatar/jogo/canvas) só rodam quando a pessoa LIGA a ferramenta e aperta Run.
const { run, useTool } = require('./_common.js');
run('chat', async ({ open, api, check }) => {
  const url = process.env.ASTA_FAKE_LM;
  await api('/api/settings', { method: 'PUT', body: { providers: { lmstudio: { base_url: url + '/v1', model: 'gemma-3-12b' } }, active: { generation: 'lmstudio', characters: 'auto' } } });
  const page = await open({ width: 1300, height: 860 });
  await page.waitForSelector('.chx', { timeout: 10000 });
  const ta = page.locator('.composer textarea'), runBtn = page.locator('.composer .send');
  const projects = async () => (await api('/api/projects')).length;
  const p0 = await projects();

  // ---- tela limpa
  check('chat:nav-chama-Chat', (await page.locator('#side nav a').first().innerText()).trim() === 'Chat');
  check('chat:estado-vazio-sem-barra-de-modos', (await page.locator('.chx.empty').count()) === 1 && (await page.locator('.modes').count()) === 0);
  check('chat:titulo', (await page.locator('.chx-hero h1').innerText()).includes('How can I help'));
  const box = async (sel) => page.locator(sel).first().boundingBox();
  const att = await box('.composer .tools .tool:has-text("Attach")'), mdl = await box('.composer .mbtn'), rn = await box('.composer .send'), tx = await box('.composer textarea');
  check('layout:caixa-de-texto-acima', tx.y + tx.height <= att.y + 2);
  check('layout:anexos-a-esquerda', att.x < 200 + (await box('.composer')).x);
  check('layout:modelo-ao-lado-do-run-a-direita', mdl.x > att.x + att.width && rn.x > mdl.x + mdl.width - 1 && Math.abs(rn.y - mdl.y) < 30);
  check('layout:run-escrito', (await runBtn.innerText()).trim() === 'Run' && (await runBtn.isDisabled()));
  await page.screenshot({ path: process.env.ASTA_SHOT || '/dev/null' }).catch(() => {});

  // ---- conversa de uso geral (nada de pipeline)
  await ta.fill('Como faço um bolo de cenoura?'); check('chat:run-liga-com-texto', !(await runBtn.isDisabled()));
  await runBtn.click();
  await page.waitForSelector('.cmsg.ai .md strong', { timeout: 15000 });
  check('chat:resposta-em-markdown', (await page.locator('.cmsg.ai .md li').count()) === 2 && (await page.locator('.cmsg.ai .md code').count()) >= 1 && (await page.locator('.cmsg.ai .md script').count()) === 0);
  check('chat:balao-do-usuario', (await page.locator('.cmsg.user .bubble').innerText()).includes('bolo de cenoura'));
  check('chat:composer-desce-e-limpa', (await page.locator('.chx:not(.empty)').count()) === 1 && (await ta.inputValue()) === '' && (await page.locator('.chx-dock .composer').count()) === 1);
  check('chat:titulo-da-conversa', (await page.locator('.chx-title').innerText()).toLowerCase().includes('bolo'));
  check('chat:nenhum-projeto-criado', (await projects()) === p0);

  // ---- pedido de criação no chat: só SUGERE, não roda
  await ta.fill('crie um jogo 2D de plataforma com um gato'); await runBtn.click();
  await page.waitForSelector('.csuggest', { timeout: 15000 });
  await page.waitForTimeout(400);
  check('ativador:sugere-mas-nao-roda', (await projects()) === p0 && (await page.locator('.result, .runview').count()) === 0 && (await page.locator('.cmsg.ai').count()) >= 2);
  check('ativador:sugestao-oferece-ligar-jogo', (await page.locator('.csuggest .btn.primary').innerText()).includes('2D game'));
  await page.locator('.csuggest .btn.primary').click(); await page.waitForTimeout(600);
  check('ativador:ligar-so-prepara-a-ferramenta', (await page.locator('.composer .tool.on').innerText()).includes('2D game') && (await ta.inputValue()).includes('gato') && (await projects()) === p0);
  check('ativador:opcoes-da-ferramenta-aparecem', (await page.locator('.composer .tools .tool, .chx-below .tool, .chx-below .seg').count()) >= 3);
  // desligar volta ao chat simples
  await page.locator('.composer .tool.on .x').click(); await page.waitForTimeout(400);
  check('ativador:desligar-volta-a-conversar', (await page.locator('.composer .tool.on').count()) === 0 && (await runBtn.innerText()).trim() === 'Run');

  // ---- trocar de modelo
  await page.locator('.composer .mbtn').click(); await page.waitForSelector('.mpick .mp-prov', { timeout: 8000 });
  check('modelo:lista-provedores', (await page.locator('.mpick .mp-prov').count()) >= 3 && (await page.locator('.mpick .mp-prov', { hasText: 'LM Studio' }).count()) === 1);
  check('modelo:provedor-ativo-ja-vem-aberto', (await page.locator('.mpick .mp-prov.on', { hasText: 'LM Studio' }).count()) === 1);
  await page.waitForSelector('.mpick .mp-model', { timeout: 8000 });
  await page.locator('.mpick .mp-model', { hasText: 'llama-3.2-3b' }).click(); await page.waitForTimeout(800);
  const s = await api('/api/settings');
  check('modelo:troca-salva-e-mostra', s.providers.lmstudio.model === 'llama-3.2-3b' && s.active.generation === 'lmstudio' && (await page.locator('.composer .mbtn').innerText()).includes('llama-3.2-3b'));

  // ---- Parar: a resposta pela metade não fica
  const n0 = (await page.locator('.cmsg.ai').count());
  await ta.fill('[lento] me conta uma história longa'); await runBtn.click();
  await page.waitForSelector('.composer .send.stop', { timeout: 8000 });
  check('parar:run-vira-parar', (await runBtn.innerText()).trim() === 'Stop');
  await page.waitForTimeout(500); await runBtn.click(); await page.waitForTimeout(700);
  check('parar:voltou-a-run', (await runBtn.innerText()).trim() === 'Run' && (await page.locator('.cmsg.ai').count()) === n0);
  const chatId = await page.evaluate(() => localStorage.getItem('asta.chat'));
  const saved = await api('/api/chats/' + chatId);
  check('parar:nada-pela-metade-no-historico', !saved.messages.some((m) => m.role === 'assistant' && m.text.includes('parte parte')));

  // ---- responder de novo
  await page.locator('.cmsg.ai').last().hover();
  const before = (await page.locator('.cmsg.ai .md').last().innerText());
  await page.locator('.cmsg.ai .cacts button[title="Reply again"]').last().click();
  await page.waitForFunction((b) => { const e = [...document.querySelectorAll('.cmsg.ai .md')].pop(); return e && e.innerText !== b && e.innerText.length > 0; }, before, { timeout: 15000 });
  check('regenerar:troca-a-ultima-resposta', true);

  // ---- histórico: recarregar reabre a última conversa; novo chat e histórico
  await page.reload(); await page.waitForSelector('.cmsg', { timeout: 10000 }); await page.waitForTimeout(400);
  check('historico:ultima-conversa-reaberta', (await page.locator('.cmsg.user').count()) >= 2);
  await page.locator('#chat-new').click(); await page.waitForTimeout(400);
  check('historico:novo-chat-vazio', (await page.locator('.chx.empty').count()) === 1 && (await page.locator('.cmsg').count()) === 0);
  await ta.fill('Explique fotossíntese'); await runBtn.click(); await page.waitForSelector('.cmsg.ai', { timeout: 15000 }); await page.waitForTimeout(500);
  await page.locator('#chat-history').click(); await page.waitForSelector('.mp-prov.hist', { timeout: 8000 });
  check('historico:lista-as-duas-conversas', (await page.locator('.mp-prov.hist').count()) === 2);
  await page.locator('.mp-prov.hist', { hasText: 'bolo' }).first().click(); await page.waitForTimeout(600);
  check('historico:abre-a-conversa-escolhida', (await page.locator('.cmsg.user .bubble').first().innerText()).includes('bolo'));

  // ---- Run da ferramenta: aí sim cria (jogo 2D, provedor Demo para ser offline)
  await api('/api/settings', { method: 'PUT', body: { active: { generation: 'demo' } } });
  await page.locator('#chat-new').click(); await page.waitForTimeout(300);
  await useTool(page, 'game');
  check('ativador:run-sem-texto-fica-desligado', await runBtn.isDisabled());
  await ta.fill('Uma visual novel romântica num café, com escolhas e três finais'); await runBtn.click();
  await page.waitForSelector('.result', { timeout: 90000 });
  check('ativador:run-da-ferramenta-cria-o-jogo', (await projects()) === p0 + 1 && (await page.locator('.result a[href*="/play/"]').count()) === 1);
  // atualizar um projeto (vindo da Biblioteca) abre o Chat já com a ferramenta certa e o aviso "Updating"
  const list = await api('/api/projects'); const proj = await api('/api/projects/' + (list.find((x) => x.kind === 'game2d') || list[0]).id);
  await page.evaluate(async (p) => { const m = await import('/js/main.js'); m.go('main', { project: p }); }, proj);
  await page.waitForSelector('.composer .tool.on', { timeout: 8000 });
  check('atualizar:abre-com-a-ferramenta-ligada', (await page.locator('.composer .tool.on').innerText()).includes('2D game') && (await page.locator('.ctxbar').count()) === 1);
  await api('/api/settings', { method: 'PUT', body: { providers: { lmstudio: { base_url: '', model: '' } }, active: { generation: 'demo' } } });
});
