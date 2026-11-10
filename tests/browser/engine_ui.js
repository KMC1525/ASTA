// Game Engine no navegador: criar um jogo por prompt (sem IA = regras), Main (árvore, inspetor, jogar), Code (arquivos e editor), Assets (camadas, pincel, seleção),
// Sound (faixas, edição, redução de ruído), Scripts (abas, painéis, IA no trecho), Map (blocos e região), Publish (exportar), o jogo isolado e o inglês.
const { run } = require('./_common');
run('engine', async ({ api, open, check, base, browser }) => {
  await api('/api/settings', { method: 'PUT', body: { language: 'pt-BR', active: { generation: 'demo' } } });
  const page = await open({ width: 1500, height: 900 });
  check('engine:item-no-menu-e-sem-mundos-nem-jogos2d', (await page.locator('#side nav a[href="#/engine"]').count()) === 1 && (await page.locator('#side nav a[href="#/worlds"], #side nav a[href="#/games"]').count()) === 0);

  // ---- atalho: ir direto para uma aba (sem nenhum projeto, cria um vazio e abre a aba)
  await page.goto(base + '/#/engine'); await page.waitForSelector('#ge-new-composer');
  check('engine:atalhos-das-7-abas', (await page.locator('#ge-direct .ge-direct-b').count()) === 7);
  await page.locator('#ge-direct .ge-direct-b[data-tab="sound"]').click(); await page.waitForSelector('.ge-app', { timeout: 15000 }); await page.waitForTimeout(800);
  check('engine:atalho-abre-a-aba-em-projeto-novo', /#\/engine\/[\w-]+\/sound$/.test(await page.evaluate(() => location.hash)) && (await page.locator('.ge-tab.on').innerText()).includes('Sound') && (await api('/api/engine/projects')).projects.length === 1);
  await page.evaluate(() => { location.hash = '#/engine/map'; }); await page.waitForTimeout(1200);
  check('engine:atalho-usa-o-ultimo-projeto', (await page.locator('.ge-tab.on').innerText()).includes('Map') && (await api('/api/engine/projects')).projects.length === 1);
  for (const p of (await api('/api/engine/projects')).projects) await api('/api/engine/projects/' + p.id, { method: 'DELETE' });

  // ---- criar um jogo 3D com um prompt (sem IA: o gerador de regras)
  await page.goto(base + '/#/engine'); await page.waitForSelector('#ge-new-composer');
  await page.locator('.ge-kindbtn[data-kind="3d"]').click();
  await page.locator('#ge-new-composer textarea').fill('Aventura 3D "Ilha Gelada" na neve com gemas');
  await page.locator('#ge-new-composer .send').click();
  await page.waitForSelector('#ge-frame', { timeout: 20000 });
  await page.waitForFunction(() => document.querySelectorAll('.ge-step.done, .ge-step.warn').length >= 4, null, { timeout: 60000 });
  await page.waitForFunction(() => document.querySelectorAll('.ge-trow').length > 5, null, { timeout: 30000 });
  const pid = page.url().match(/#\/engine\/([\w-]+)\//)[1];
  check('engine:projeto-3d-criado-com-arvore-da-cena', (await page.locator('.ge-trow').count()) >= 8 && (await page.locator('#ge-kind').innerText()) === '3D');

  // ---- Main: inspetor, editar propriedade e salvar; adicionar nó; jogar
  await page.locator('.ge-trow[data-type="Sky3D"]').click();
  await page.waitForSelector('#ge-i-name');
  check('engine:inspetor-mostra-propriedades-do-no', (await page.locator('.ge-igrp h4').first().innerText()).length > 0 && (await page.locator('.ge-prop').count()) >= 3);
  await page.locator('#ge-i-name').fill('Céu do Norte'); await page.locator('#ge-i-name').dispatchEvent('change');
  await page.waitForTimeout(1400);
  let sc = await api(`/api/engine/projects/${pid}/scenes/main`);
  check('engine:renomear-no-salva-a-cena', JSON.stringify(sc).includes('Céu do Norte'));
  await page.locator('#ge-add-node').click(); await page.waitForSelector('#ge-addnode-q');
  await page.locator('.ge-addopt[data-type="Mesh3D"]').click();
  await page.waitForTimeout(1200);
  sc = await api(`/api/engine/projects/${pid}/scenes/main`);
  check('engine:adicionar-no-mesh3d', JSON.stringify(sc).includes('"Mesh3D"'));
  await page.locator('#ge-i-del').click(); await page.locator('.modal .btn.danger').click(); await page.waitForTimeout(1200);
  sc = await api(`/api/engine/projects/${pid}/scenes/main`);
  check('engine:apagar-no', !JSON.stringify(sc).includes('Malha 3D'));
  await page.locator('#ge-play').click(); await page.waitForTimeout(1500);
  check('engine:jogar-alterna-para-parar', (await page.locator('#ge-play').innerText()).includes('Parar'));
  await page.locator('#ge-play').click();

  // ---- o jogo roda isolado: sem acesso à API do ASTA
  const gp = await browser.newPage(); const gerrs = [];
  gp.on('pageerror', (e) => gerrs.push(e.message));
  await gp.goto(`${base}/api/engine/play/${pid}/index.html`);
  await gp.waitForFunction(() => { const b = document.getElementById('ge-play'); return b && !b.disabled; }, null, { timeout: 20000 });
  const origin = await gp.evaluate(async () => ({ o: window.origin, secure: typeof window.GE, cookie: (() => { try { return document.cookie; } catch (e) { return 'bloqueado'; } })(), api: await fetch('/api/state').then((r) => r.status).catch(() => 'bloqueado') }));
  check('engine:jogo-isolado-sem-origem-do-asta', origin.o === 'null' && origin.api === 'bloqueado');
  await gp.click('#ge-play'); await gp.waitForTimeout(1500);
  check('engine:jogo-3d-roda-sem-erros', gerrs.length === 0 && (await gp.evaluate(() => GE.dim)) === '3d');
  await gp.close();

  // ---- Code
  await page.goto(base + `/#/engine/${pid}/code`); await page.waitForSelector('#ge-files .ge-frow');
  check('engine:code-arvore-de-pastas', (await page.locator('.ge-frow[data-type="dir"]').count()) >= 3);
  await page.locator('#ge-new-file').click(); await page.locator('#ge-nf-name').fill('scripts/sub/meu.js'); await page.locator('.modal .btn.primary').click();
  await page.waitForSelector('.ge-ed-ta'); await page.waitForFunction(() => document.querySelector('.ge-ed-ta').value.includes("GE.behavior('meu'"));
  check('engine:code-novo-arquivo-com-subpasta', (await page.locator('.ge-etab.on').innerText()).includes('meu.js') && (await page.locator('.ge-ed-ta').inputValue()).includes("GE.behavior('meu'"));
  await page.locator('.ge-ed-ta').click(); await page.keyboard.press('Control+End'); await page.keyboard.type('\n// linha nova');
  check('engine:code-realce-e-aba-suja', (await page.locator('.ge-ed-hl .tk-k').count()) > 0 && (await page.locator('.ge-etab.on .dirty').count()) === 1);
  await page.keyboard.press('Control+s'); await page.waitForTimeout(700);
  const saved = await api(`/api/engine/projects/${pid}/file?area=game&path=scripts/sub/meu.js`);
  check('engine:code-ctrl-s-salva', saved.content.includes('// linha nova'));
  // IA do código sem modelo: esqueleto de comportamento
  await page.locator('#ge-composer-code textarea').fill('faça o inimigo pulsar'); await page.locator('#ge-composer-code .send').click();
  await page.waitForFunction(async (u) => (await (await fetch(u)).json()).content.includes("GE.behavior('pulsar'"), `/api/engine/projects/${pid}/file?area=game&path=scripts/sub/meu.js`, { timeout: 40000 });   // a IA acrescenta ao arquivo aberto
  check('engine:code-ia-sem-modelo-escreve-comportamento-no-arquivo-aberto', true);
  // renomear/apagar
  await page.locator('.ge-frow[data-path="scripts/sub/meu.js"]').click();
  await page.locator('#ge-delete').click(); await page.locator('.modal .btn.danger').click(); await page.waitForTimeout(600);
  check('engine:code-apagar-arquivo', JSON.stringify(await api(`/api/engine/projects/${pid}/tree?area=game`)).indexOf('meu.js') < 0);
  check('engine:code-link-opcional-com-o-modo-code', (await page.locator('#ge-usecode').count()) === 1);

  // ---- Assets
  await page.goto(base + `/#/engine/${pid}/assets`); await page.waitForSelector('#ge-acanvas');
  await page.locator('#ge-composer-assets textarea').fill('moeda dourada'); await page.locator('#ge-composer-assets .send').click();
  await page.waitForFunction(() => document.querySelectorAll('.ge-lrow[data-type="layer"]').length >= 1, null, { timeout: 40000 });
  check('engine:assets-gera-imagem-em-camada', (await page.locator('.ge-lrow[data-type="layer"]').count()) >= 1);
  await page.locator('#ge-add-group').click(); await page.locator('#ge-add-layer').click();
  check('engine:assets-pastas-e-camadas', (await page.locator('.ge-lrow[data-type="group"]').count()) === 1 && (await page.locator('.ge-lrow').count()) >= 3);
  const cv = await page.locator('#ge-acanvas').boundingBox();
  await page.locator('.ge-atool[data-tool="brush"]').click();
  await page.mouse.move(cv.x + 300, cv.y + 200); await page.mouse.down(); await page.mouse.move(cv.x + 420, cv.y + 260, { steps: 6 }); await page.mouse.up();
  await page.locator('.ge-atool[data-tool="rect"]').click();
  await page.mouse.move(cv.x + 250, cv.y + 150); await page.mouse.down(); await page.mouse.move(cv.x + 450, cv.y + 300, { steps: 4 }); await page.mouse.up();
  await page.waitForSelector('#ge-clearsel');
  check('engine:assets-selecao-ativa-barra', (await page.locator('#ge-selbar').count()) === 1);
  await page.locator('#ge-clearsel').click();
  await page.locator('#ge-aname').fill('moeda-ui'); await page.locator('#ge-aname').dispatchEvent('change');
  await page.locator('#ge-asave').click(); await page.waitForTimeout(1200);
  await page.locator('#ge-aapply').click(); await page.locator('.modal .btn').first().click(); await page.waitForTimeout(1500);
  const tree = JSON.stringify(await api(`/api/engine/projects/${pid}/tree?area=game`));
  const edt = JSON.stringify(await api(`/api/engine/projects/${pid}/tree?area=editor`));
  check('engine:assets-aplicar-ao-jogo-grava-png-e-doc-em-camadas', tree.includes('moeda-ui.png') && edt.includes('moeda-ui.asset.json'));

  // ---- Sound
  await page.goto(base + `/#/engine/${pid}/sound`); await page.waitForSelector('#ge-tracks');
  await page.locator('#ge-composer-sound textarea').fill('efeito de moeda'); await page.locator('#ge-composer-sound .send').click();
  await page.waitForSelector('.ge-trk', { timeout: 40000 });
  check('engine:sound-gera-faixa', (await page.locator('.ge-trk').count()) === 1);
  const dsp = await page.evaluate(() => {
    const S = window.ASTA_SOUND, D = S.DSP, sr = 8000, n = sr * 2, sig = new Float32Array(n), noise = new Float32Array(n);
    let seed = 1; const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296 - 0.5; };
    for (let i = 0; i < n; i++) { noise[i] = rnd() * 0.2; sig[i] = (i > sr * 0.5 && i < sr * 1.5 ? Math.sin(2 * Math.PI * 440 * i / sr) * 0.5 : 0) + noise[i]; }
    const prof = D.noiseProfile(noise.slice(0, 4096)), den = D.denoise(sig, prof, 1.3);
    const rms = (a, s, e) => { let t = 0; for (let i = s; i < e; i++) t += a[i] * a[i]; return Math.sqrt(t / (e - s)); };
    const wav = D.encodeWav([sig.slice(0, 100)], sr);
    return { before: rms(sig, 0, sr * 0.4), after: rms(den, 0, sr * 0.4), tone: rms(den, sr * 0.6, sr * 1.4), gate: rms(D.gate(sig, sr, -20), 0, sr * 0.4), wavSize: wav.size };
  });
  check('engine:sound-reducao-de-ruido-tira-o-ruido-e-mantem-o-tom', dsp.after < dsp.before * 0.5 && dsp.tone > 0.25 && dsp.gate < dsp.before * 0.5 && dsp.wavSize === 44 + 200);
  const dur0 = await page.evaluate(() => window.ASTA_SOUND.P.tracks[0].buf.duration);
  await page.evaluate(() => { const S = window.ASTA_SOUND; S.P.sel = { track: S.P.tracks[0].id, a: 0.05, b: 0.15 }; });
  await page.locator('#ge-sdel').click();
  const dur1 = await page.evaluate(() => window.ASTA_SOUND.P.tracks[0].buf.duration);
  check('engine:sound-excluir-trecho-encurta-a-faixa', dur1 < dur0 - 0.05);
  await page.locator('#ge-sundo').click();
  check('engine:sound-desfazer', Math.abs((await page.evaluate(() => window.ASTA_SOUND.P.tracks[0].buf.duration)) - dur0) < 0.001);
  await page.locator('[data-fx="fadeout"]').click(); await page.locator('[data-fx="normalize"]').click();
  await page.locator('#ge-ssave').click(); await page.waitForTimeout(1500);
  await page.locator('#ge-sapply').click(); await page.locator('#ge-sname').fill('efeito-teste'); await page.locator('#ge-suse').selectOption('coin'); await page.locator('.modal .btn.primary').click(); await page.waitForTimeout(2000);
  check('engine:sound-aplicar-ao-jogo-e-mapeia-evento', JSON.stringify(await api(`/api/engine/projects/${pid}/tree?area=game`)).includes('efeito-teste.wav') && ((await api(`/api/engine/projects/${pid}`)).settings.audio.events.coin === 'efeito-teste'));
  await page.locator('#ge-srec').click(); await page.waitForTimeout(1500); await page.locator('#ge-srec').click();
  await page.waitForFunction(() => window.ASTA_SOUND.P.tracks.length >= 2, null, { timeout: 15000 }).catch(() => {});
  check('engine:sound-gravacao-do-microfone', (await page.evaluate(() => window.ASTA_SOUND.P.tracks.length)) >= 2);
  check('engine:sound-conexoes-opcionais-studio-e-canvas', (await page.locator('#ge-to-studio').count()) === 1 && (await page.locator('#ge-to-canvas').count()) === 1);

  // ---- Scripts
  await page.goto(base + `/#/engine/${pid}/scripts`); await page.waitForSelector('#ge-snew');
  await page.locator('#ge-composer-scripts textarea').fill('GDD do jogo'); await page.locator('#ge-composer-scripts .send').click();
  await page.waitForSelector('.ge-pane .ge-ed-ta', { timeout: 40000 });
  check('engine:scripts-gera-documento-em-markdown', (await page.locator('.ge-ed-ta').inputValue()).includes('#'));
  await page.locator('#ge-snew').click(); await page.locator('#ge-sn-name').fill('historias/cena1'); await page.locator('.modal .btn.primary').click();
  await page.waitForSelector('.ge-etab[data-path="historias/cena1.md"]');
  await page.locator('.ge-ed-ta').click(); await page.keyboard.press('Control+a'); await page.keyboard.type('## guia\nGuia: Olá, viajante.\nHeroi: Oi!\n\nTexto  solto ,com erro . aqui');
  await page.locator('#ge-sdlg').click(); await page.waitForTimeout(800);
  check('engine:scripts-enviar-dialogos-ao-jogo', Array.isArray((JSON.parse((await api(`/api/engine/projects/${pid}/file?area=game&path=data/dialogues.json`)).content).guia)));
  await page.locator('#ge-sel-par').click();
  const sel = await page.evaluate(() => { const t = document.querySelector('.ge-ed-ta'); return t.value.slice(t.selectionStart, t.selectionEnd); });
  check('engine:scripts-seleciona-paragrafo', sel.startsWith('Texto  solto'));
  await page.locator('[data-act="fix"]').click(); await page.waitForFunction(() => document.querySelector('.ge-ed-ta').value.includes('Texto solto,com erro. Aqui'), null, { timeout: 30000 });
  check('engine:scripts-ia-corrige-so-o-trecho-selecionado', (await page.locator('.ge-ed-ta').inputValue()).includes('Guia: Olá, viajante.'));
  await page.locator('#ge-lay-h').click(); await page.waitForSelector('.ge-pane[data-pane="1"]');
  await page.locator('#ge-tabs-left').click(); await page.waitForSelector('.ge-vtabs');
  check('engine:scripts-painel-dividido-e-abas-verticais', (await page.locator('.ge-pane').count()) === 2 && (await page.locator('.ge-vtabs').count()) >= 1);
  await page.locator('#ge-lay-v').click(); await page.locator('#ge-tabs-top').click();
  check('engine:scripts-empilhado-e-abas-em-cima', (await page.locator('.ge-panes.v').count()) === 1 && (await page.locator('.ge-etabs').count()) >= 1);
  await page.locator('.seg button', { hasText: 'Personagens' }).click(); await page.waitForTimeout(800);
  check('engine:scripts-cartoes-de-personagens-e-worldbuilding', (await page.locator('#ge-cards').count()) === 1);
  await page.locator('#ge-lay-one').click().catch(() => {});

  // ---- Map (2D)
  const p2 = await api('/api/engine/projects', { method: 'POST', body: { name: 'Mapa2D', kind: '2d', genre: 'platformer' } });
  await page.goto(base + `/#/engine/${p2.id}/map`); await page.waitForSelector('#ge-mcanvas');
  await page.waitForFunction(() => /objetos/.test(document.getElementById('ge-mstatus').textContent), null, { timeout: 15000 });
  const mp0 = (await api(`/api/engine/projects/${p2.id}/maps`)).maps[0].path;
  const mv = await page.locator('#ge-mcanvas').boundingBox();
  await page.locator('.ge-pal [data-tile="3"]').click();
  await page.mouse.move(mv.x + mv.width / 2, mv.y + mv.height / 2); await page.mouse.down(); await page.mouse.move(mv.x + mv.width / 2 + 60, mv.y + mv.height / 2, { steps: 5 }); await page.mouse.up();
  await page.waitForTimeout(1200);
  const before = await api(`/api/engine/projects/${p2.id}/map?path=${encodeURIComponent(mp0)}`);
  check('engine:map-pintar-bloco-salva-o-mapa', JSON.stringify(before.layers[0].data).includes('3'));
  await page.locator('[data-tool="region"]').click();
  await page.mouse.move(mv.x + 100, mv.y + mv.height / 2 - 20); await page.mouse.down(); await page.mouse.move(mv.x + 260, mv.y + mv.height / 2 + 40, { steps: 4 }); await page.mouse.up();
  await page.waitForSelector('#ge-mregen');
  await page.locator('#ge-mregen').click(); await page.waitForFunction(() => document.querySelector('.toast') && /Região atualizada|Gerando/.test(document.body.innerText), null, { timeout: 40000 });
  check('engine:map-regiao-selecionada-e-gerada-de-novo', (await page.locator('#ge-mregion-info').count()) === 1);
  await page.locator('#ge-composer-map textarea').fill('fase de caverna com muitas moedas'); await page.locator('#ge-composer-map .send').click();
  await page.waitForFunction(() => document.querySelectorAll('#ge-msel option').length >= 2, null, { timeout: 40000 });
  check('engine:map-prompt-gera-mapa-inteiro', (await api(`/api/engine/projects/${p2.id}/maps`)).maps.length >= 2);

  // ---- Publish
  await page.goto(base + `/#/engine/${p2.id}/publish`); await page.waitForSelector('#ge-export-web');
  check('engine:publish-seis-plataformas', (await page.locator('.ge-plat').count()) === 6);
  await page.locator('#ge-p-version').fill('1.2.3'); await page.locator('#ge-p-version').dispatchEvent('change'); await page.waitForTimeout(500);
  await page.locator('#ge-export-android').click(); await page.waitForSelector('.ge-exp[data-file*="android"]', { timeout: 30000 });
  await page.locator('#ge-export-ios').click(); await page.waitForSelector('.ge-exp[data-file*="ios"]', { timeout: 30000 });
  const exps = (await api(`/api/engine/projects/${p2.id}/exports`)).items;
  check('engine:publish-exporta-android-e-ios-com-versao', exps.some((x) => x.platform === 'android' && x.file.includes('1.2.3')) && exps.some((x) => x.platform === 'ios'));
  check('engine:publish-verificacoes', (await page.locator('.ge-check').count()) >= 6);

  // ---- Configuração, inglês, celular
  await page.goto(base + '/#/config'); await page.waitForSelector('.cfgtabs');
  await page.locator('.cfgtabs button[data-tab="engine"]').click(); await page.waitForSelector('#cfg-engine-status');
  check('engine:config-aba-game-engine-com-geradores-do-chat', (await page.locator('.acc').count()) >= 2 && (await page.locator('.cfgtabs button[data-tab="games"], .cfgtabs button[data-tab="generation"]').count()) === 0);
  await api('/api/settings', { method: 'PUT', body: { language: 'en' } });
  await page.goto(base + `/#/engine/${pid}/main`); await page.reload(); await page.waitForSelector('.ge-tab.on');
  const en = await page.locator('#ge-app').innerText();
  check('engine:ingles', /Scene tree|Game prompt|Properties/.test(en) && !/Propriedades|Prompt do jogo/.test(en));
  await api('/api/settings', { method: 'PUT', body: { language: 'pt-BR' } });
  await page.close();
  const m = await browser.newPage({ viewport: { width: 390, height: 800 }, isMobile: true, hasTouch: true });
  await m.goto(base + `/#/engine/${pid}/main`); await m.waitForSelector('.ge-tab.on');
  check('engine:celular-sem-rolagem-horizontal-da-pagina', (await m.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)));
  await m.close();
});
