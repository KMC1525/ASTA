// v0.7 Studio: criar (duração/estilo/tipo), gerar cena a cena ao vivo, timeline estilo Kdenlive (cortar, juntar, silenciar, excluir, desfazer, lâmina, play), exportar e edição automática.
const { run } = require('./_common.js');
run('studio', async ({ open, api, check, base }) => {
  await api('/api/settings', { method: 'PUT', body: { active: { generation: 'demo' } } });
  const page = await open({ width: 1500, height: 950 });
  await page.evaluate(() => { location.hash = '#/studio'; });
  await page.waitForSelector('#st-new', { timeout: 15000 });
  const navTxt = await page.locator('#side nav').innerText();
  check('nav:studio-abaixo-do-canvas', /Canvas\s*\n?\s*Studio/.test(navTxt.replace(/\n+/g, '\n')));

  // ---- criação: tipos, estilos, duração customizável
  check('criar:quatro-tipos-de-duracao', (await page.locator('.st-chips.types .st-chip').count()) === 4);
  check('criar:tres-estilos-mais-custom', (await page.locator('.st-chips.styles .st-chip').count()) === 4 && /Realistic|Realista/.test(await page.locator('.st-chips.styles').innerText()));
  check('criar:unico-e-serie', (await page.locator('.st-chips.kinds .st-chip').count()) === 2);
  const typeText = await page.locator('.st-chips.types').innerText();
  check('criar:limites-2-30-90-min', /2 minutes|Até 2 minutos|Up to 2/i.test(typeText) || (/2/.test(typeText) && /30/.test(typeText) && /90/.test(typeText)));
  await page.locator('.st-chips.types .st-chip[data-v="short"]').click();
  check('duracao:curta-comeca-em-10-min', (await page.inputValue('#st-min')) === '10');
  await page.fill('#st-min', '45'); await page.locator('#st-min').dispatchEvent('change'); await page.waitForTimeout(300);
  check('duracao:passou-de-30-min-vira-longa', (await page.locator('.st-chips.types .st-chip.on').getAttribute('data-v')) === 'long');
  await page.fill('#st-min', '200'); await page.locator('#st-min').dispatchEvent('change'); await page.waitForTimeout(300);
  check('duracao:acima-de-90-min-vira-personalizada', (await page.locator('.st-chips.types .st-chip.on').getAttribute('data-v')) === 'custom');
  await page.locator('.st-presets .st-pre', { hasText: '1 min' }).click(); await page.waitForTimeout(200);
  check('duracao:atalho-1-min', (await page.inputValue('#st-min')) === '1' && (await page.inputValue('#st-sec')) === '0');
  await page.locator('.st-chips.types .st-chip[data-v="shorts"]').click();
  await page.fill('#st-min', '0'); await page.fill('#st-sec', '16'); await page.locator('#st-sec').dispatchEvent('change'); await page.waitForTimeout(200);
  check('duracao:digitar-minutos-e-segundos-nao-embaralha', (await page.inputValue('#st-min')) === '0' && (await page.inputValue('#st-sec')) === '16' && /0:16|16s|16 s/.test(await page.locator('.st-sum').innerText()));
  check('duracao:segundos-livres-e-tipo-shorts', (await page.locator('.st-chips.types .st-chip.on').getAttribute('data-v')) === 'shorts' && (await page.inputValue('#st-sec')) === '16');
  await page.locator('.st-chips.styles .st-chip[data-v="custom"]').click();
  check('estilo:custom-mostra-campo-de-texto', await page.locator('#st-style-custom').isVisible());
  await page.locator('.st-chips.styles .st-chip[data-v="anime"]').click();
  check('estilo:custom-esconde-o-campo', !(await page.locator('#st-style-custom').isVisible()));

  // ---- gerar (provedor Demo): cena a cena ao vivo
  await page.fill('#st-new .composer textarea', 'Uma raposa viaja pela floresta. Ela encontra um rio e chega em casa.');
  await page.locator('#st-new .composer .send').click();
  await page.waitForSelector('#st-board .st-scene', { timeout: 30000 });
  check('projeto:abre-na-aba-de-cenas', /\/scenes$/.test(await page.evaluate(() => location.hash)));
  await page.waitForFunction(() => document.querySelectorAll('#st-board .st-scene.delivered').length >= 2, null, { timeout: 120000 });
  const stages = await page.evaluate(() => [...document.querySelectorAll('#st-board .st-scene')].map((s) => [...s.querySelectorAll('.stg')].map((x) => x.className.includes('s-done') || x.className.includes('s-warn'))));
  check('cenas:duas-cenas-com-os-cinco-passos-concluidos', stages.length === 2 && stages.every((r) => r.length === 5 && r.every(Boolean)));
  const stNames = await page.locator('#st-board .st-scene').first().locator('.stg').allInnerTexts();
  check('cenas:passos-recebe-analisa-gera-revisa-entrega', stNames.map((x) => x.trim()).join(',') === 'Receive,Analyze,Generate,Review,Deliver');
  check('cenas:progresso-2-de-2', /2 of 2|2 de 2/.test(await page.locator('.st-progress').innerText()));
  const pid = (await page.evaluate(() => location.hash)).match(/studio\/([\w-]+)/)[1];
  const proj = await api('/api/studio/projects/' + pid);
  const eid = proj.episodes[0].id;
  check('cenas:projeto-guardou-estilo-e-duracao', proj.style === 'anime' && proj.target_seconds === 16 && proj.duration_type === 'shorts' && proj.aspect === '9:16');

  // ---- timeline estilo Kdenlive
  await page.locator('#st-tab-timeline').click();
  await page.waitForSelector('.stl .stl-clip', { timeout: 15000 });
  check('timeline:seis-trilhas', (await page.locator('.stl-row').count()) === 6);
  check('timeline:barra-de-ferramentas', (await page.locator('.stl-bar .stl-btn').count()) >= 18 && (await page.locator('#stl-split, #stl-join, #stl-mute, #stl-del').count()) === 4);
  check('timeline:bin-inspetor-e-monitor', (await page.locator('.stl-asset').count()) > 3 && (await page.locator('.stl-mon').count()) === 1 && (await page.locator('.stl-insp').count()) === 1);
  const count = () => page.locator('.stl-clip').count();
  const vClips = () => page.locator('.stl-row.k-video .stl-clip');
  const n0 = await count();
  await vClips().first().click();
  check('timeline:selecionar-mostra-propriedades', (await page.locator('.stl-clip.sel').count()) === 1 && (await page.locator('.stl-insp input[data-k="dur"]').count()) === 1);
  // cortar no cursor (S): playhead no meio do clipe selecionado
  const first = await page.evaluate(() => { const c = document.querySelector('.stl-row.k-video .stl-clip'); return { w: c.getBoundingClientRect().width }; });
  const ruler = page.locator('.stl-ruler');
  const rb = await ruler.boundingBox();
  await page.mouse.click(rb.x + 118 + 20, rb.y + 10);
  await page.waitForTimeout(150);
  await vClips().first().click();
  await page.keyboard.press('s'); await page.waitForTimeout(200);
  check('cortar:S-divide-o-clipe-em-dois', (await count()) === n0 + 1);
  // juntar (J): as duas partes do mesmo arquivo voltam a ser um clipe
  await vClips().first().click({ modifiers: ['Shift'] });   // a parte nova já está selecionada: soma a primeira
  await page.keyboard.press('j'); await page.waitForTimeout(200);
  check('juntar:J-une-as-partes-do-mesmo-arquivo', (await count()) === n0);
  // cortar de novo e desfazer
  await vClips().first().click(); await page.keyboard.press('s'); await page.waitForTimeout(150);
  check('cortar:de-novo', (await count()) === n0 + 1);
  await page.keyboard.press('Control+z'); await page.waitForTimeout(200);
  check('desfazer:Ctrl+Z-volta', (await count()) === n0);
  await page.keyboard.press('Control+Shift+z'); await page.waitForTimeout(200);
  check('refazer:Ctrl+Shift+Z', (await count()) === n0 + 1);
  // silenciar (M)
  await vClips().first().click(); await page.keyboard.press('m'); await page.waitForTimeout(150);
  check('silenciar:M-marca-o-clipe-como-mudo', (await page.locator('.stl-clip.muted').count()) >= 1);
  await page.keyboard.press('m'); await page.waitForTimeout(150);
  // lâmina (C) + clique
  await page.keyboard.press('c'); await page.waitForTimeout(100);
  check('lamina:C-liga-a-ferramenta', (await page.locator('.stl-content.razor').count()) === 1);
  const cb = await vClips().nth(1).boundingBox();
  const nBefore = await count();
  await page.mouse.click(cb.x + cb.width / 2, cb.y + cb.height / 2); await page.waitForTimeout(200);
  check('lamina:clique-no-clipe-corta', (await count()) === nBefore + 1);
  await page.keyboard.press('v');
  // excluir (Del)
  await vClips().last().click(); await page.keyboard.press('Delete'); await page.waitForTimeout(150);
  check('excluir:Del-remove-o-clipe', (await count()) === nBefore);
  // inspetor: velocidade e filtro
  await vClips().first().click();
  await page.selectOption('.stl-insp select[data-k="speed"]', '2'); await page.waitForTimeout(150);
  await page.selectOption('.stl-insp select[data-k="filter"]', 'bw'); await page.waitForTimeout(150);
  check('inspetor:velocidade-e-filtro-aparecem-no-clipe', /2×/.test(await vClips().first().innerText()) && /Black and white|Preto e branco/.test(await vClips().first().innerText()));
  // texto
  await page.keyboard.press('t'); await page.waitForTimeout(200);
  check('texto:T-adiciona-legenda-na-trilha-T1', (await page.locator('.stl-row.k-text .stl-clip').count()) >= 3);
  // reproduzir / régua
  const tc0 = await page.locator('.stl-tc').innerText();
  await page.keyboard.press(' '); await page.waitForTimeout(900); await page.keyboard.press(' ');
  const tc1 = await page.locator('.stl-tc').innerText();
  check('play:Space-avanca-o-cursor', tc0.split(' / ')[0] !== tc1.split(' / ')[0]);
  await page.mouse.click(rb.x + 118 + 200, rb.y + 10); await page.waitForTimeout(150);
  check('regua:clique-move-o-cursor', !/^00:00:00 /.test(await page.locator('.stl-tc').innerText()));
  check('monitor:mostra-uma-camada-de-video', (await page.locator('.stl-layers .lyr').count()) >= 1);
  // trilhas: silenciar/ocultar/travar
  await page.locator('.stl-row.k-audio').first().locator('button[data-act="lock"]').click(); await page.waitForTimeout(100);
  check('trilha:travar', (await page.locator('.stl-clip.locked').count()) >= 1);
  await page.locator('.stl-row.k-audio').first().locator('button[data-act="lock"]').click();
  // salvamento automático
  await page.waitForFunction(() => /Saved|Salvo/.test(document.querySelector('.stl-status').textContent), null, { timeout: 8000 });
  const saved = await api(`/api/studio/projects/${pid}`);
  const tl = saved.episodes[0].timeline;
  check('salvar:timeline-gravada-no-servidor', tl.clips.some((c) => c.speed === 2 && c.filter === 'bw') && tl.clips.some((c) => c.text === 'Text' || c.text === 'Texto'));
  // recarregar mantém a edição
  await page.reload(); await page.waitForSelector('.stl .stl-clip', { timeout: 15000 });
  check('salvar:recarregar-mantem-a-edicao', (await page.locator('.stl-clip').count()) === tl.clips.length);

  // ---- exportar
  await page.locator('#st-tab-export').click(); await page.waitForSelector('.st-chips.modes', { timeout: 5000 });
  check('exportar:tres-modos', (await page.locator('.st-chips.modes .st-chip').count()) === 3);
  await page.locator('.st-chips.modes .st-chip[data-v="audio"]').click();
  await page.locator('#st-export').click();
  await page.waitForSelector('.ok-note', { timeout: 120000 });
  check('exportar:audio-gerado-e-listado', (await page.locator('.st-exp').count()) === 1 && /Audio only|Somente áudio/.test(await page.locator('.st-exp').innerText()));
  await page.locator('.st-chips.modes .st-chip[data-v="video"]').click();
  await page.locator('#st-export').click();
  await page.waitForFunction(() => document.querySelectorAll('.st-exp').length === 2, null, { timeout: 120000 });
  const ex = (await api(`/api/studio/projects/${pid}`)).episodes[0].exports;
  check('exportar:modos-no-servidor', ex.map((e) => e.mode).join(',') === 'audio,video' && ex[0].file.endsWith('.m4a') && ex[1].file.endsWith('.mp4'));

  // ---- série: novo episódio
  const ser = await api('/api/studio/projects', { method: 'POST', body: { name: 'Série UI', kind: 'series', duration_type: 'short', target_seconds: 600, style: 'cartoon', prompt: 'x' } });
  await page.evaluate((id) => { location.hash = '#/studio/' + id; }, ser.id);
  await page.waitForSelector('#st-new-ep', { timeout: 10000 });
  await page.locator('#st-new-ep').click(); await page.waitForTimeout(600);
  check('serie:novo-episodio', (await page.locator('.st-ep:not(.new)').count()) === 2 && (await api('/api/studio/projects/' + ser.id)).episodes.length === 2);
  // configurações do projeto: tipo e estilo
  await page.locator('#st-settings').click(); await page.waitForSelector('.modal #st-min', { timeout: 5000 });
  await page.locator('.modal .st-chips.types .st-chip[data-v="long"]').click();
  await page.locator('.modal .btn.primary').click(); await page.waitForTimeout(600);
  const ser2 = await api('/api/studio/projects/' + ser.id);
  check('configuracoes:tipo-longa-salvo', ser2.duration_type === 'long' && ser2.target_seconds === 3600);

  // ---- edição automática (anexos reais)
  await page.evaluate(() => { location.hash = '#/studio'; }); await page.waitForSelector('#st-tab-auto', { timeout: 10000 });
  await page.locator('#st-tab-auto').click(); await page.waitForSelector('#st-auto');
  check('auto:estilos-gameplay-documentario-phonk', /Gameplay/.test(await page.locator('.st-chips.estyles').innerText()) && /Documentary|Documentário/.test(await page.locator('.st-chips.estyles').innerText()) && /Phonk/.test(await page.locator('.st-chips.estyles').innerText()));
  await page.locator('#st-auto .composer input[type=file]').setInputFiles([process.env.ASTA_AE_VIDEO, process.env.ASTA_AE_MUSIC]); await page.waitForTimeout(1500);
  await page.locator('.st-chips.estyles .st-chip[data-v="phonk"]').click();
  check('auto:phonk-mostra-bpm', await page.locator('#ae-bpm').isVisible());
  await page.fill('#ae-target', '12');
  await page.fill('#st-auto .composer textarea', 'melhores momentos em edit phonk');
  await page.locator('#st-auto .composer .send').click();
  await page.waitForSelector('.stl .stl-clip', { timeout: 120000 });
  check('auto:abre-na-timeline-com-cortes-e-musica', (await page.locator('.stl-row.k-video .stl-clip').count()) >= 5 && (await page.locator('.stl-row.k-audio .stl-clip').count()) >= 1);
  check('auto:aspecto-vertical-do-phonk', await page.locator('.stl-mon.ar-16-9').count() === 1 || await page.locator('.stl-mon.ar-9-16').count() === 1);
  const list = await api('/api/studio/projects');
  check('lista:projetos-e-origem-edicao-automatica', list.some((p) => p.origin === 'autoedit') && list.length >= 3);

  // ---- v0.7.1: teclado e janelas redimensionáveis
  await page.evaluate((id) => { location.hash = '#/studio/' + id + '/timeline'; }, pid);
  await page.waitForSelector('.stl .stl-clip', { timeout: 15000 });
  // foco preso num campo do inspetor não pode matar os atalhos
  await page.locator('.stl-row.k-video .stl-clip').first().click();
  await page.selectOption('.stl-insp select[data-k="speed"]', '1.5'); await page.waitForTimeout(250);
  check('teclado:depois-de-mexer-no-inspetor-o-foco-sai-do-campo', await page.evaluate(() => !/^(SELECT|INPUT|TEXTAREA)$/.test(document.activeElement.tagName)));
  const nBef2 = await page.locator('.stl-clip').count();
  await page.keyboard.press('Control+c'); await page.keyboard.press('Control+v'); await page.waitForTimeout(250);
  check('teclado:Ctrl+C-Ctrl+V-cola-no-cursor', (await page.locator('.stl-clip').count()) === nBef2 + 1);
  await page.keyboard.press('Control+z'); await page.waitForTimeout(150);
  // segurar a tecla não corta em rajada
  await page.locator('.stl-row.k-video .stl-clip').first().click();
  const nB = await page.locator('.stl-clip').count();
  await page.keyboard.down('Delete'); await page.keyboard.down('Delete'); await page.keyboard.down('Delete'); await page.keyboard.up('Delete'); await page.waitForTimeout(200);
  check('teclado:tecla-segurada-nao-repete-a-acao', (await page.locator('.stl-clip').count()) === nB - 1);
  await page.keyboard.press('Control+z'); await page.waitForTimeout(150);
  // botão da barra não rouba o foco: Space continua reproduzindo
  await page.locator('#stl-marker').click(); await page.keyboard.press('Escape');
  const t0 = await page.locator('.stl-tc').innerText(); await page.keyboard.press(' '); await page.waitForTimeout(700); await page.keyboard.press(' ');
  check('teclado:Space-depois-de-clicar-num-botao-da-barra', (await page.locator('.stl-tc').innerText()).split(' / ')[0] !== t0.split(' / ')[0]);
  // cursor pode passar do fim da timeline
  const rb2 = await page.locator('.stl-ruler').boundingBox();
  await page.keyboard.press('End'); await page.keyboard.press('Shift+ArrowRight'); await page.waitForTimeout(100);
  const tcEnd = await page.locator('.stl-tc').innerText();
  check('teclado:cursor-vai-alem-do-fim', tcEnd.split(' / ')[0] > tcEnd.split(' / ')[1]);
  // seleção que não passa pelo cursor: S corta o que estiver sob ele
  await page.keyboard.press('Home'); await page.keyboard.press('Shift+ArrowRight'); await page.keyboard.press('Shift+ArrowRight');
  await page.locator('.stl-row.k-video .stl-clip').last().click();
  const nS = await page.locator('.stl-clip').count();
  await page.keyboard.press('s'); await page.waitForTimeout(200);
  check('teclado:S-corta-sob-o-cursor-mesmo-sem-a-selecao-passar-por-ele', (await page.locator('.stl-clip').count()) > nS);
  await page.keyboard.press('Control+z'); await page.waitForTimeout(150);

  // janelas redimensionáveis
  const w = () => page.evaluate(() => ({ bin: document.querySelector('.stl-bin').getBoundingClientRect().width, insp: document.querySelector('.stl-insp').getBoundingClientRect().width, top: document.querySelector('.stl-top').getBoundingClientRect().height, row: document.querySelector('.stl-row.k-video').getBoundingClientRect().height }));
  const w0 = await w();
  const dragBy = async (sel, dx, dy) => { const b = await page.locator(sel).boundingBox(); await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await page.mouse.down(); await page.mouse.move(b.x + b.width / 2 + dx, b.y + b.height / 2 + dy, { steps: 6 }); await page.mouse.up(); await page.waitForTimeout(150); };
  await dragBy('#stl-gut-bin', 90, 0);
  await dragBy('#stl-gut-insp', -70, 0);
  await dragBy('#stl-gut-top', 0, -80);
  const w1 = await w();
  check('janelas:arrastar-aumenta-a-largura-das-midias', w1.bin > w0.bin + 60);
  check('janelas:arrastar-aumenta-a-largura-das-propriedades', w1.insp > w0.insp + 40);
  check('janelas:arrastar-diminui-o-monitor-e-aumenta-a-timeline', w1.top < w0.top - 50);
  await page.locator('#stl-rowup').click(); await page.locator('#stl-rowup').click(); await page.waitForTimeout(150);
  check('janelas:trilhas-mais-altas', (await w()).row > w1.row + 10);
  await page.reload(); await page.waitForSelector('.stl .stl-clip', { timeout: 15000 });
  const w2 = await w();
  check('janelas:tamanhos-lembrados-ao-recarregar', Math.abs(w2.bin - w1.bin) < 3 && Math.abs(w2.insp - w1.insp) < 3 && Math.abs(w2.top - w1.top) < 3 && w2.row > w1.row + 10);
  await page.locator('#stl-gut-bin').dblclick(); await page.waitForTimeout(150);
  check('janelas:dois-cliques-voltam-ao-padrao', Math.abs((await w()).bin - w0.bin) < 3);
  await page.keyboard.press('f'); await page.waitForTimeout(200);
  check('janelas:F-liga-a-tela-cheia-do-editor', await page.evaluate(() => { const r = document.querySelector('.stl').getBoundingClientRect(); return document.querySelector('.stl.full') && r.width >= innerWidth - 2 && r.height >= innerHeight - 2; }));
  await page.keyboard.press('Escape'); await page.waitForTimeout(150);
  check('janelas:Esc-sai-da-tela-cheia', (await page.locator('.stl.full').count()) === 0);

  // ---- edição manual do zero: importar mídia e não perder o bin ao trocar de aba
  const man = await api('/api/studio/projects', { method: 'POST', body: { name: 'Manual', kind: 'single', duration_type: 'shorts', target_seconds: 30 } });
  await page.evaluate((id) => { location.hash = '#/studio/' + id + '/timeline'; }, man.id);
  await page.waitForSelector('#st-manual', { timeout: 10000 }); await page.locator('#st-manual').click();
  await page.waitForSelector('.stl #stl-import', { timeout: 10000 });
  await page.locator('.stl-bin input[type=file]').setInputFiles(process.env.ASTA_AE_VIDEO); await page.waitForSelector('.stl-asset', { timeout: 15000 });
  await page.locator('.stl-asset').first().dblclick(); await page.waitForSelector('.stl-clip', { timeout: 5000 });
  await page.waitForFunction(() => /Saved|Salvo/.test(document.querySelector('.stl-status').textContent), null, { timeout: 8000 });
  await page.locator('#st-tab-export').click(); await page.waitForTimeout(300); await page.locator('#st-tab-timeline').click();
  await page.waitForSelector('.stl-clip', { timeout: 8000 });
  check('manual:bin-e-clipe-continuam-ao-trocar-de-aba', (await page.locator('.stl-asset').count()) === 1 && (await page.locator('.stl-clip').count()) === 1);
});
