// Work no navegador: criar a organização, perfis e pedido, quadro (arrastar, ligar, IA), arquivos de qualquer formato, entrar como outra pessoa e receber o aviso em tempo real,
// atividades (começou · continuando · finalizou), rede e backups, a aba de Configuração, o inglês e o celular. Sem IA (Demo): o Work usa as regras automáticas.
const { run, until } = require('./_common');
const fs = require('fs');
const os = require('os');
const path = require('path');
run('work', async ({ api, open, check, base, expectError }) => {
  expectError(/status of (401|409)/);   // sem sessão (401) e o convite que pede para ligar a escuta (409) são respostas esperadas
  await api('/api/settings', { method: 'PUT', body: { language: 'pt-BR', active: { generation: 'demo' } } });
  const page = await open();
  check('work:item-na-barra-lateral', (await page.locator('#side nav a[href="#/work"]').count()) === 1);
  await page.goto(base + '/#/work'); await page.waitForSelector('#wk-create');
  check('work:sem-rede-mostra-criar-e-entrar', (await page.locator('#wk-join').count()) === 1 && (await page.locator('#wk-create').count()) === 1);

  // criar a organização (primeiro usuário = administrador)
  await page.locator('#wk-new-name').fill('Estúdio Teste'); await page.locator('#wk-new-display').fill('Ana Souza'); await page.locator('#wk-new-user').fill('ana'); await page.locator('#wk-new-pw').fill('segredo1');
  await page.locator('#wk-create').click(); await page.waitForSelector('.wk-tabs');
  check('work:abas', (await page.locator('.wk-tab').count()) === 7 && (await page.locator('.wk-page h1').innerText()) === 'Estúdio Teste');
  check('work:inicio-com-4-quadros', (await page.locator('.wk-tile').count()) === 4);

  // pessoas: criar um trabalhador com senha só nesta máquina
  await page.locator('.wk-tab[data-tab="people"]').click(); await page.waitForSelector('#wk-new-person');
  await page.locator('#wk-new-person').click(); await page.waitForSelector('#wk-p-user');
  await page.locator('#wk-p-name').fill('João Lima'); await page.locator('#wk-p-user').fill('joao'); await page.locator('#wk-p-title').fill('Designer pleno');
  await page.locator('#wk-p-bio').fill('Faz identidade visual e materiais gráficos.');
  await page.locator('#wk-p-save').click(); await page.waitForSelector('.wk-pcard[data-user="joao"]');
  check('work:pessoa-criada', (await page.locator('#wk-people .wk-pcard').count()) === 2);
  await page.locator('.wk-pcard[data-user="joao"]').click(); await page.waitForSelector('#wk-send-request');
  check('work:perfil-tem-enviar-pedido-e-cargo', (await page.locator('#wk-profile').innerText()).includes('Trabalhador') && (await page.locator('#wk-profile').innerText()).includes('Designer pleno'));

  // enviar pedido pelo perfil: texto + arquivo, com rascunho automático (sem IA = regras)
  await page.locator('#wk-send-request').click(); await page.waitForSelector('#wk-composer');
  check('work:composer-ja-vem-com-o-destinatario', (await page.locator('#wk-rq-to .wk-rcpt').count()) === 1);
  await page.locator('#wk-rq-body').fill('Criar o logotipo da campanha, é urgente!\n- versão colorida\n- versão preto e branco');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'wk-')); const f1 = path.join(tmp, 'briefing.xyz'); fs.writeFileSync(f1, Buffer.from([0, 1, 2, 3, 250, 251, 252]));
  await page.locator('#wk-rq-file').setInputFiles(f1); await page.waitForSelector('#wk-rq-files .chip');
  check('work:anexo-de-formato-qualquer', (await page.locator('#wk-rq-files').innerText()).includes('briefing.xyz'));
  await page.locator('#wk-rq-ai-btn').click(); await page.waitForSelector('#wk-rq-ai .errbox, #wk-rq-ai .small');
  check('work:rascunho-sem-ia-usa-regras', (await page.locator('#wk-rq-prio').inputValue()) === 'urgent' && (await page.locator('#wk-rq-check li').count()) === 2);
  await page.locator('#wk-rq-send').click(); await page.waitForSelector('#wk-thread');
  check('work:pedido-aberto-com-conversa-e-anexo', (await page.locator('#wk-thread').innerText()).includes('briefing.xyz') && (await page.locator('#wk-rmain .cu-st').first().innerText()) === 'Enviado');

  // quadro: preencher com as pessoas, arrastar, ligar, criar setor, IA
  await page.locator('.wk-tab[data-tab="board"]').click(); await page.waitForSelector('#wk-autofill');
  await page.locator('#wk-autofill').click(); await page.waitForSelector('.wk-node');
  check('work:quadro-2-pessoas-e-1-ligacao', (await page.locator('.wk-node').count()) === 2 && (await page.locator('.wk-edge').count()) === 1);
  const n0 = page.locator('.wk-node').first(); const before = await n0.boundingBox();
  await page.mouse.move(before.x + 40, before.y + 20); await page.mouse.down(); await page.mouse.move(before.x + 140, before.y + 120, { steps: 6 }); await page.mouse.up();
  await page.waitForTimeout(500);
  const after = await n0.boundingBox();
  check('work:arrastar-move-o-cartao', Math.abs(after.x - before.x) > 40 || Math.abs(after.y - before.y) > 40);
  await n0.click(); await page.waitForSelector('#wk-n-label');
  check('work:painel-edita-o-cartao', (await page.locator('#wk-insp h3').innerText()) === 'Pessoa');
  await page.locator('#wk-add-note').click(); await page.locator('#wk-card-label').fill('Lembrar do cliente'); await page.locator('.modal .btn.primary').click(); await page.waitForSelector('.wk-node.k-note');
  check('work:nota-criada', (await page.locator('.wk-node').count()) === 3);
  // ligar pelo painel (o cartão selecionado → a nota) e adicionar/remover um cartão de pessoa
  await n0.click(); await page.waitForSelector('#wk-link-to');
  await page.locator('#wk-link-to').selectOption({ label: 'Lembrar do cliente' }); await page.locator('#wk-link-add').click(); await page.waitForFunction(() => document.querySelectorAll('.wk-edge').length === 2);
  check('work:ligar-pelo-painel', (await page.locator('.wk-edge').count()) === 2);
  await page.locator('.wk-edge').last().dispatchEvent('pointerdown'); await page.waitForSelector('#wk-e-del');
  check('work:ligacao-selecionada-mostra-o-tipo', (await page.locator('#wk-insp h3').innerText()) === 'Ligação');
  await page.locator('#wk-add-person').click(); await page.waitForSelector('.modal select'); await page.locator('.modal .btn.primary').click(); await page.waitForFunction(() => document.querySelectorAll('.wk-node').length === 4);
  await page.waitForSelector('#wk-n-del'); await page.locator('#wk-n-del').click(); await page.locator('.modal .btn.danger').click(); await page.waitForFunction(() => document.querySelectorAll('.wk-node').length === 3);
  check('work:adicionar-e-remover-cartao-de-pessoa', (await page.locator('.wk-node').count()) === 3);
  await page.locator('#wk-add-sector').click(); await page.locator('#wk-sector-name').fill('Criação'); await page.locator('.modal .btn.primary').click(); await page.waitForSelector('.wk-folder');
  check('work:setor-vira-caixa', (await page.locator('.wk-folder').count()) === 1);
  await page.locator('#wk-ai-flow').click(); await page.waitForSelector('#wk-ai-desc');
  await page.locator('#wk-ai-desc').fill('Empresa com financeiro, vendas e suporte ao cliente'); await page.locator('#wk-ai-go').click(); await page.waitForSelector('#wk-ai-apply');
  check('work:ia-propoe-sem-aplicar', (await page.locator('.wk-node').count()) === 3 && (await page.locator('#wk-ai-result').innerText()).includes('3 setor'));
  await page.locator('#wk-ai-apply').click(); await page.waitForFunction(() => document.querySelectorAll('.wk-folder').length >= 4, null, { timeout: 15000 });
  check('work:aplicou-setores-e-cartoes', (await page.locator('.wk-node').count()) > 10);
  await page.locator('#wk-fit').click(); await page.locator('#wk-layout').click(); await page.waitForTimeout(600);

  // arquivos
  await page.locator('.wk-tab[data-tab="files"]').click(); await page.waitForSelector('#wk-upload-btn');
  await page.locator('#wk-tree .cu-item', { hasText: 'Financeiro' }).first().click(); await page.waitForTimeout(400);
  const f2 = path.join(tmp, 'planilha.bin'); fs.writeFileSync(f2, Buffer.alloc(120000, 7));
  await page.locator('#wk-upload').setInputFiles(f2); await page.waitForSelector('#wk-files tr[data-name="planilha.bin"]');
  check('work:arquivo-no-setor', (await page.locator('#wk-files tr').count()) === 2);   // cabeçalho + 1
  const dl = await page.evaluate(async () => { const id = document.querySelector('#wk-files tbody tr').dataset.id; const r = await fetch(`/api/work/files/${id}/download`); const b = await r.arrayBuffer(); return [r.status, b.byteLength, r.headers.get('content-disposition')]; });
  check('work:baixa-o-mesmo-conteudo', dl[0] === 200 && dl[1] === 120000 && /attachment/.test(dl[2]));
  await page.locator('#wk-files [data-act="menu"]').click(); await page.waitForSelector('.wk-menu');
  check('work:menu-do-arquivo', (await page.locator('.wk-menu .toolopt').count()) >= 4);
  await page.keyboard.press('Escape'); await page.mouse.click(5, 5);

  // sair e entrar como o João: o aviso chega em tempo real e o pedido está na caixa de entrada
  await page.locator('#wk-logout').click(); await page.waitForSelector('.wk-person');
  check('work:login-lista-as-pessoas', (await page.locator('.wk-person').count()) === 2);
  await page.locator('.wk-person[data-user="joao"]').click(); await page.locator('#wk-enter').click(); await page.waitForSelector('.wk-tabs');
  check('work:joao-entrou-sem-senha', (await page.locator('.wk-page .page-h p').first().innerText()).includes('Trabalhador'));
  check('work:selo-na-barra-lateral', (await page.locator('#wk-badge').innerText()).trim() !== '' && (await page.locator('#wk-bell-n').count()) === 1);
  await page.locator('.wk-tab[data-tab="requests"]').click(); await page.waitForSelector('#wk-rlist .cu-item');
  await page.locator('#wk-rlist .cu-item').first().click(); await page.waitForSelector('#wk-rq-start');
  check('work:trabalhador-nao-ve-novo-pedido', (await page.locator('#wk-rq-new').count()) === 0);
  await page.locator('#wk-rq-start').click(); await page.waitForSelector('#wk-rq-done');
  await page.locator('#wk-rq-reply').fill('Já comecei!'); await page.locator('#wk-rq-reply-send').click(); await page.waitForSelector('.wk-msg.mine');
  check('work:resposta-na-conversa', (await page.locator('#wk-thread').innerText()).includes('Já comecei!'));
  check('work:caminho-no-fluxograma', (await page.locator('.wk-route').count()) === 1);
  await page.locator('.wk-tab[data-tab="activities"]').click(); await page.waitForSelector('#wk-act-title');
  await page.waitForSelector('.wk-act[data-state="started"]');
  check('work:comecar-o-pedido-abre-atividade', (await page.locator('.wk-act').count()) === 1);
  await page.locator('#wk-act-title').fill('Revisar cores'); await page.locator('#wk-act-start').click(); await page.waitForFunction(() => document.querySelectorAll('.wk-act').length === 2);
  const second = page.locator('.wk-act', { hasText: 'Revisar cores' });
  await second.locator('.wk-note-in').fill('Paleta aprovada'); await second.locator('.wk-note-in').press('Enter'); await page.waitForSelector('.wk-act[data-state="continuing"]');
  check('work:continuando-depois-do-andamento', (await page.locator('.wk-act[data-state="continuing"]').count()) === 1);
  await page.locator('.wk-act[data-state="continuing"] [data-op="finish"]').click(); await page.waitForFunction(() => document.querySelectorAll('.wk-act').length === 1);
  check('work:finalizada-sai-das-abertas', (await page.locator('#wk-act-feed details').count()) >= 2);
  await page.locator('#wk-dg-go').click(); await page.waitForSelector('#wk-dg-result');
  check('work:resumo-sem-ia-tem-numeros', (await page.locator('#wk-dg-result').innerText()).includes('atividade'));

  // rede (só leitura para o trabalhador) e a volta como administrador
  await page.locator('.wk-tab[data-tab="net"]').click(); await page.waitForSelector('#wk-machines');
  check('work:rede-trabalhador-nao-gerencia', (await page.locator('#wk-apply-net').count()) === 0 && (await page.locator('#wk-machines tbody tr').count()) === 1);
  await page.locator('#wk-logout').click(); await page.waitForSelector('.wk-person');
  await page.locator('.wk-person[data-user="ana"]').click(); await page.waitForSelector('#wk-pw'); await page.locator('#wk-pw').fill('errada'); await page.locator('#wk-enter').click(); await page.waitForSelector('.errbox:not(.hidden)');
  check('work:senha-errada-nao-entra', (await page.locator('.errbox:not(.hidden)').innerText()).includes('incorretos'));
  await page.locator('#wk-pw').fill('segredo1'); await page.locator('#wk-enter').click(); await page.waitForSelector('.wk-tabs');
  await page.locator('.wk-tab[data-tab="net"]').click(); await page.waitForSelector('#wk-apply-net');
  check('work:rede-admin-gerencia', (await page.locator('#wk-listen').inputValue()) === 'off' && (await page.locator('#wk-listen-state').innerText()).includes('Não está escutando'));
  await page.locator('#wk-invite').click(); await page.waitForSelector('#wk-invite-out .errbox');
  check('work:convite-pede-ligar-a-escuta', (await page.locator('#wk-invite-out .errbox').innerText()).includes('escuta'));
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'wk-cloud-'));
  await page.locator('#wk-link-kind2').selectOption('folder'); await page.locator('#wk-link-target').fill(folder); await page.locator('#wk-link-add2').click(); await page.waitForSelector('#wk-links ul code');
  await page.locator('#wk-sync-now').click(); await page.waitForFunction(() => document.querySelector('#wk-sync-results li'), null, { timeout: 15000 });
  check('work:pasta-de-nuvem-sincroniza-cifrado', fs.readdirSync(path.join(folder, fs.readdirSync(folder)[0])).some((n) => n.startsWith('state-')) && !fs.readFileSync(path.join(folder, fs.readdirSync(folder)[0], fs.readdirSync(path.join(folder, fs.readdirSync(folder)[0])).find((n) => n.startsWith('state-')))).includes('Estúdio'));
  await page.locator('#wk-machines [data-flag="backup"]').check(); await page.waitForSelector('#wk-bk-users input[type=checkbox]');
  check('work:maquina-de-backup-aparece', (await page.locator('#wk-backups h3').textContent()) === 'Backups' && (await page.locator('#wk-bk-users input[type=checkbox]').count()) >= 1);
  await page.locator('#wk-bk-users input[type=checkbox]').first().check(); await page.waitForTimeout(500);
  await page.locator('[data-verify]').first().click(); await page.waitForFunction(() => /arquivos presentes/.test(document.querySelector('#wk-bk-result').innerText));
  check('work:verificar-backup', true);

  // pessoas: cargos e permissões
  await page.locator('.wk-tab[data-tab="people"]').click(); await page.waitForSelector('#wk-new-role');
  await page.locator('#wk-new-role').click(); await page.waitForSelector('#wk-role-form');
  await page.locator('#wk-r-name').fill('Financeiro sênior'); await page.locator('#wk-role-form [data-perm="files.view"]').check(); await page.locator('#wk-r-save').click(); await page.waitForSelector('#wk-roles .wk-pcard[data-role]:nth-child(4)');
  check('work:cargo-customizado', (await page.locator('#wk-roles .wk-pcard[data-role]').count()) === 4);

  // configuração, inglês e celular
  await page.goto(base + '/#/config'); await page.waitForSelector('.cfgtabs');
  await page.locator('.cfgtabs button[data-tab="work"]').click(); await page.waitForSelector('#wk-card-card, #wk-card');
  check('work:aba-de-configuracao', (await page.locator('#wk-fields').count()) === 1 && (await page.locator('.cu-cfg-prompts details').count()) === 9);
  await api('/api/settings', { method: 'PUT', body: { language: 'en' } });
  await page.goto(base + '/#/work/requests'); await page.reload(); await page.waitForSelector('.wk-tabs');
  check('work:ingles', (await page.locator('.wk-tab').allInnerTexts()).map((s) => s.trim()).join('|') === 'Home|Board|People|Files|Requests|Activities|Network' || (await page.locator('.wk-tab').allInnerTexts()).map((s) => s.trim()).join('|').startsWith('Início') === false);
  await api('/api/settings', { method: 'PUT', body: { language: 'pt-BR' } });
  const mob = await open({ width: 390, height: 800 });
  await mob.goto(base + '/#/work/board'); await mob.waitForSelector('.wk-person');
  check('work:celular-login-sem-rolagem', await mob.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2));
  await mob.locator('.wk-person[data-user="ana"]').click(); await mob.locator('#wk-pw').fill('segredo1'); await mob.locator('#wk-enter').click(); await mob.waitForSelector('.wk-tabs');
  check('work:celular-sem-rolagem-horizontal', await mob.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2));
  await mob.close();
  await page.close();
});
