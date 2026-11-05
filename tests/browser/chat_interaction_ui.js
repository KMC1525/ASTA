// Conversa usuário × avatar: parar, responder de novo, editar, apagar, copiar, rascunho, rolagem inteligente, memórias e nome do avatar renomeado.
const { run } = require('./_common.js');
run('chat_interaction', async ({ open, api, check, base }) => {
  const url = process.env.ASTA_FAKE_LM;
  await api('/api/settings', { method: 'PUT', body: { providers: { lmstudio: { base_url: url + '/v1', model: 'llama-3.2-3b' } }, active: { generation: 'lmstudio', characters: 'auto' } } });
  const av = await api('/api/avatars', { method: 'POST', body: { name: 'Nara', age: 27, greeting: '' } });
  const chat = await api('/api/avatar-chats', { method: 'POST', body: { avatar_ids: [av.id] } });
  const sendApi = async (text) => { const r = await fetch(`${base}/api/avatar-chats/${chat.id}/send`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) }); await r.text(); };
  const page = await open({ width: 1300, height: 800 });
  const go = async () => { await page.evaluate((id) => { location.hash = '#/avatars/chat/' + id; }, chat.id); await page.reload(); await page.waitForSelector('.chinput textarea', { timeout: 10000 }); await page.waitForTimeout(500); };
  await go();
  const ta = page.locator('.chinput textarea'), sendBtn = page.locator('.chinput .btn.icon').last();
  const msgText = async (sel) => (await page.locator(sel).allInnerTexts());

  // ---- enviar e receber
  await ta.fill('oi Nara'); await ta.press('Enter');
  await page.waitForSelector('.msg.av .mtext:has-text("Resposta 1")', { timeout: 10000 });
  check('chat:responde', (await page.locator('.msg.me').count()) === 1 && (await page.locator('.msg.av').count()) === 1);
  check('chat:botao-volta-a-enviar', (await sendBtn.getAttribute('aria-label')) === 'Send' && !(await sendBtn.isDisabled()));

  // ---- ações da mensagem aparecem ao passar o mouse
  await page.locator('.msg.av').hover(); await page.waitForTimeout(300);
  check('chat:acoes-visiveis-no-hover', (await page.locator('.msg.av .macts').evaluate((el) => getComputedStyle(el).opacity)) === '1');
  check('chat:resposta-tem-responder-de-novo', (await page.locator('.msg.av .macts button[title="Reply again"]').count()) === 1 && (await page.locator('.msg.me .macts button[title="Reply again"]').count()) === 0);

  // ---- editar a própria mensagem (persiste)
  await page.locator('.msg.me').hover(); await page.locator('.msg.me .macts button[title="Edit"]').click();
  await page.locator('.msg.me textarea.medit').fill('oi Nara, tudo bem?'); await page.locator('.msg.me .btn', { hasText: 'Save' }).click(); await page.waitForTimeout(500);
  check('chat:editou', (await page.locator('.msg.me .mtext').innerText()).includes('tudo bem?'));
  await go();
  check('chat:edicao-persiste', (await msgText('.msg.me .mtext')).join('').includes('tudo bem?'));

  // ---- responder de novo troca a resposta (continua uma só)
  await page.locator('.msg.av').hover(); await page.locator('.msg.av .macts button[title="Reply again"]').click();
  await page.waitForSelector('.msg.av .mtext:has-text("Resposta 2")', { timeout: 10000 });
  check('chat:responder-de-novo', (await page.locator('.msg.av').count()) === 1 && !(await msgText('.msg.av .mtext')).join('').includes('Resposta 1'));
  const saved = await api('/api/avatar-chats/' + chat.id);
  check('chat:historico-sem-a-resposta-antiga', saved.messages.filter((m) => m.role === 'avatar').length === 1 && saved.messages.filter((m) => m.role === 'avatar')[0].text === 'Resposta 2');

  // ---- apagar a resposta
  await page.locator('.msg.av').hover(); await page.locator('.msg.av .macts button[title="Delete message"]').click();
  await page.waitForSelector('.modal'); await page.locator('.modal .btn.danger').click(); await page.waitForTimeout(500);
  check('chat:apagou', (await page.locator('.msg.av').count()) === 0);
  await go();
  check('chat:apagar-persiste', (await page.locator('.msg.av').count()) === 0 && (await page.locator('.msg.me').count()) === 1);

  // ---- parar no meio da resposta (o botão vira «Parar»; nada fica salvo pela metade)
  await ta.fill('[lento] conta uma história'); await ta.press('Enter');
  await page.waitForSelector('.msg.typing, .msg.av .mtext', { timeout: 5000 });
  await page.waitForTimeout(500);
  check('chat:botao-vira-parar', (await sendBtn.getAttribute('aria-label')) === 'Stop');
  await sendBtn.click(); await page.waitForTimeout(700);
  check('chat:parou-sem-balao-preso', (await page.locator('.msg.typing').count()) === 0 && (await sendBtn.getAttribute('aria-label')) === 'Send');
  await page.waitForTimeout(2500);
  const after = await api('/api/avatar-chats/' + chat.id);
  check('chat:resposta-cortada-nao-e-salva', after.messages.filter((m) => m.role === 'avatar').length === 0 && after.messages.filter((m) => m.role === 'user').length === 2);
  // ...e dá para pedir a resposta de novo
  await go(); await page.locator('.msg.me').last().hover();
  await ta.fill('oi?'); await ta.press('Enter'); await page.waitForSelector('.msg.av .mtext', { timeout: 10000 });

  // ---- rascunho: o que foi digitado e não enviado volta quando você reabre a conversa
  await ta.fill('texto que ainda não enviei'); await page.waitForTimeout(200);
  await page.evaluate(() => { location.hash = '#/avatars'; }); await page.waitForTimeout(500);
  await go();
  check('chat:rascunho-volta', (await ta.inputValue()) === 'texto que ainda não enviei');
  await ta.fill(''); await page.waitForTimeout(100);
  check('chat:limite-de-6000-no-campo', (await ta.getAttribute('maxlength')) === '6000');

  // ---- rolagem inteligente: quem subiu para ler o histórico não é puxado para baixo
  for (let i = 0; i < 12; i++) await sendApi('mensagem de enchimento número ' + i);
  await go();
  await ta.fill('[lento] outra história'); await ta.press('Enter'); await page.waitForTimeout(300);
  await page.locator('.chmsgs').evaluate((el) => { el.scrollTop = 0; el.dispatchEvent(new Event('scroll')); });
  await page.waitForTimeout(3500);
  check('chat:nao-puxa-a-tela-para-baixo', (await page.locator('.chmsgs').evaluate((el) => el.scrollTop)) < 80);
  check('chat:mostra-novas-mensagens', (await page.locator('.newmsgs:not(.hidden)').count()) === 1);
  await page.locator('.newmsgs').click(); await page.waitForTimeout(300);
  check('chat:novas-mensagens-leva-ao-fim', (await page.locator('.chmsgs').evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight < 8)));

  // ---- memórias: ensinar e esquecer uma só
  await page.locator('.chhead .btn[title="More"]').click(); await page.locator('.pop .opt', { hasText: 'Memories' }).click(); await page.waitForSelector('.modal input');
  await page.locator('.modal input').fill('meu aniversário é em março'); await page.locator('.modal input').press('Enter'); await page.waitForTimeout(600);
  await page.locator('.modal input').fill('gosto de café'); await page.locator('.modal input').press('Enter'); await page.waitForTimeout(600);
  check('chat:ensinou-memorias', (await page.locator('.modal .card', { hasText: 'março' }).count()) === 1 && (await page.locator('.modal .card', { hasText: 'café' }).count()) === 1);
  await page.locator('.modal .card', { hasText: 'março' }).locator('button[title="Forget this one"]').click(); await page.waitForTimeout(500);
  check('chat:esqueceu-so-uma', (await page.locator('.modal .card', { hasText: 'março' }).count()) === 0 && (await page.locator('.modal .card', { hasText: 'café' }).count()) === 1);
  await page.keyboard.press('Escape');

  // ---- renomear o avatar atualiza a conversa (o título não fica preso ao nome antigo)
  await api('/api/avatars/' + av.id, { method: 'PUT', body: { ...(await api('/api/avatars/' + av.id)), name: 'Nara Lima' } });
  await go();
  check('chat:titulo-segue-o-nome-novo', (await page.locator('.chhead .t').innerText()) === 'Nara Lima' && (await page.locator('.chlist .li.active .t').innerText()) === 'Nara Lima');
  await api('/api/settings', { method: 'PUT', body: { active: { generation: 'demo' }, providers: { lmstudio: { base_url: '', model: '' } } } });  // não deixa o servidor falso configurado para os outros testes
});
