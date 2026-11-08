// v0.17 — timeline do Studio: Tools (janelas ligáveis), camadas livres (imagem, efeitos…), Shift+A + deslocar/apagar, efeitos, SFX, legendas, forma de onda, virtualização e exportação 2K/4K/fps.
const { run } = require('./_common.js');
const { execFileSync } = require('child_process');
const fs = require('fs'); const os = require('os'); const path = require('path');
run('studio_tools', async ({ open, api, check }) => {
  const page = await open({ width: 1700, height: 1000 });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'asta-tools-'));
  const mp4 = path.join(dir, 'v.mp4'), wav = path.join(dir, 't.wav'), png = path.join(dir, 'p.png');
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc=d=4:s=160x90:r=24', '-pix_fmt', 'yuv420p', mp4]);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=f=300:d=5', wav]);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=64x64', '-frames:v', '1', png]);
  const p = await api('/api/studio/projects', { method: 'POST', body: { name: 'Tools', origin: 'manual', duration_type: 'custom', target_seconds: 30 } });
  const up = async (file, name, type) => (await fetch(`${page.url().split('#')[0]}api/studio/projects/${p.id}/media`, { method: 'POST', headers: { 'X-Filename': name, 'Content-Type': type }, body: fs.readFileSync(file) })).status;
  check('midias-importadas', (await up(mp4, 'v.mp4', 'video/mp4')) === 201 && (await up(wav, 't.wav', 'audio/wav')) === 201 && (await up(png, 'p.png', 'image/png')) === 201);
  await page.evaluate((id) => { location.hash = '#/studio/' + id + '/timeline'; }, p.id);
  await page.waitForSelector('.stl-asset', { timeout: 15000 });
  const tl = async () => (await api(`/api/studio/projects/${p.id}`)).episodes[0].timeline;
  const wait = (ms = 1200) => page.waitForTimeout(ms);
  const toggleTool = async (id, on) => { await page.locator('#stl-tools').click(); const cb = page.locator(`#stl-tools-menu input[data-tool="${id}"]`); if ((await cb.isChecked()) !== on) await cb.click(); await page.keyboard.press('Escape'); await page.mouse.click(5, 5); await wait(250); };

  // ---- Tools: as janelas atuais + as novas
  check('tools:janelas-padrao', (await page.locator('#stl-dock-left #stl-tool-media').count()) === 1 && (await page.locator('#stl-dock-right #stl-tool-props').count()) === 1 && (await page.locator('.stl-mons:not(.hidden)').count()) === 1);
  await page.locator('#stl-tools').click();
  const ids = await page.locator('#stl-tools-menu input[data-tool]').evaluateAll((els) => els.map((e) => e.dataset.tool));
  check('tools:menu-lista-todas', ['media', 'monitor', 'props', 'mixer', 'effects', 'sfx', 'capture', 'captions', 'transcribe', 'browser'].every((x) => ids.includes(x)));
  await page.keyboard.press('Escape'); await page.mouse.click(5, 5);
  await toggleTool('effects', true); await toggleTool('sfx', true); await toggleTool('captions', true); await toggleTool('browser', true); await toggleTool('transcribe', true); await toggleTool('capture', true);
  check('tools:abas-novas-aparecem', (await page.locator('.stl-tabs2 .tb[data-tab="effects"]').count()) === 1 && (await page.locator('.stl-tabs2 .tb[data-tab="sfx"]').count()) === 1);
  await toggleTool('mixer', false);
  check('tools:mixer-desligado-some', (await page.locator('div.stl-mixer').isVisible()) === false);
  await toggleTool('mixer', true);
  check('tools:mixer-ligado-volta', await page.locator('div.stl-mixer').isVisible());
  await toggleTool('monitor', false);
  check('tools:monitor-desligado-some', (await page.locator('.stl-mons').isVisible()) === false);
  await toggleTool('monitor', true);
  const lay = await page.evaluate(() => JSON.parse(localStorage.getItem('asta.stl.layout')));
  check('tools:escolha-fica-guardada', lay.tools.effects === true && lay.tools.mixer === true);

  // ---- camadas livres, sem misturar tipos
  const mk = async (k) => { await page.locator('#stl-layer').click(); await page.locator(`#stl-layer-menu .opt[data-layer="${k}"]`).click(); await wait(300); };
  await mk('fx'); await mk('image'); await mk('video'); await mk('audio'); await mk('text'); await wait(1200);
  let t = await tl(); const name = (id) => t.tracks.find((x) => x.id === id).name;
  const kinds = Object.fromEntries(t.tracks.map((x) => [x.name, x.kind]));
  check('camadas:criadas-com-o-tipo-certo', kinds.FX1 === 'fx' && kinds.I1 === 'image' && kinds.V3 === 'video' && kinds.A4 === 'audio' && kinds.T2 === 'text');
  const order = t.tracks.map((x) => x.kind);
  check('camadas:ordem-texto-efeitos-video-audio', order.indexOf('text') === 0 && order.indexOf('fx') < order.indexOf('video') && order.lastIndexOf('video') < order.indexOf('audio'));
  await page.locator('.stl-asset', { hasText: 'p.png' }).dblclick(); await wait(500);
  await page.locator('.stl-asset', { hasText: 'v.mp4' }).dblclick(); await wait(500);
  await page.locator('.stl-asset', { hasText: 't.wav' }).dblclick(); await wait(1500);
  t = await tl();
  const clipOf = (label) => t.clips.find((c) => c.label.startsWith(label));
  check('camadas:imagem-vai-para-camada-de-imagem', name(clipOf('p.png').track) === 'I1');
  check('camadas:video-vai-para-camada-de-video-e-audio-para-audio', t.tracks.find((x) => x.id === clipOf('v.mp4').track).kind === 'video' && t.tracks.find((x) => x.id === clipOf('t.wav').track).kind === 'audio');
  // soltar uma imagem numa camada de vídeo não mistura: vai para a de imagem
  await page.locator('.stl-asset', { hasText: 'p.png' }).dblclick(); await wait(1200);
  t = await tl(); check('camadas:segunda-imagem-no-mesmo-instante-ganha-camada-nova-de-imagem', t.clips.filter((c) => c.label.startsWith('p.png')).every((c) => t.tracks.find((x) => x.id === c.track).kind === 'image') && new Set(t.clips.filter((c) => c.label.startsWith('p.png')).map((c) => c.track)).size === 2);

  // ---- forma de onda
  await page.waitForSelector('.stl-clip.k-audio .wf polygon', { timeout: 15000 }).catch(() => {});
  check('onda:clipe-de-audio-desenha-a-forma-de-onda', (await page.locator('.stl-clip.k-audio .wf polygon').count()) >= 1);

  // ---- efeitos: filtro nos selecionados e camada de efeitos
  await page.locator('.stl-row[data-track="t_v1"] .stl-clip').first().click();
  await page.locator('.stl-tabs2 .tb[data-tab="effects"]').click(); await wait(250);
  await page.locator('.fxsw[data-fx="sepia"]').click(); await page.locator('#fx-apply').click(); await wait(1300);
  t = await tl(); check('efeitos:filtro-aplicado-ao-clipe-selecionado', t.clips.find((c) => c.track === 't_v1').filter === 'sepia');
  await page.locator('.fxsw[data-fx="negative"]').click(); await page.locator('#fx-layer').click(); await wait(1300);
  t = await tl(); const fxc = t.clips.find((c) => t.tracks.find((x) => x.id === c.track).kind === 'fx');
  check('efeitos:camada-de-efeitos-no-cursor', !!fxc && fxc.filter === 'negative' && Math.abs(fxc.dur - 3) < 0.01 && fxc.asset === '');

  // ---- SFX
  await page.locator('.stl-tabs2 .tb[data-tab="sfx"]').click(); await page.waitForSelector('[data-act="add"][data-sfx="whoosh"]', { timeout: 10000 });
  await page.locator('[data-act="add"][data-sfx="whoosh"]').click(); await wait(2200);
  t = await tl(); const full = await api(`/api/studio/projects/${p.id}`);
  check('sfx:efeito-vira-ativo-e-clipe-de-audio', full.assets.some((a) => a.source === 'sfx' && a.kind === 'audio') && t.clips.some((c) => c.label.startsWith('Whoosh')));

  // ---- legendas
  await page.locator('.stl-tabs2 .tb[data-tab="captions"]').click(); await page.locator('#cap-text').fill('Primeira frase da legenda. Segunda frase da legenda.');
  await page.locator('#cap-dur').fill('8'); await page.locator('#cap-gen').click(); await wait(1500);
  t = await tl(); const caps = t.clips.filter((c) => t.tracks.find((x) => x.id === c.track).kind === 'text');
  check('legendas:texto-vira-clipes-de-texto', caps.length >= 2 && caps[0].text.includes('Primeira'));
  check('legendas:lista-na-aba', (await page.locator('.caplist .capr').count()) >= 2);

  // ---- navegador de mídia e transcrição (painéis abrem)
  await page.locator('.stl-tabs2 .tb[data-tab="browser"]').click(); await page.waitForSelector('#br-list', { timeout: 8000 });
  check('navegador:painel-abre', (await page.locator('#br-q').count()) === 1 && (await page.locator('#br-import').count()) === 1);
  await page.locator('.stl-tabs2 .tb[data-tab="transcribe"]').click(); await page.waitForSelector('#tx-run', { timeout: 8000 });
  check('transcricao:painel-abre-com-os-arquivos', (await page.locator('#tx-asset option').count()) >= 2);
  await page.locator('.stl-tabs2 .tb[data-tab="capture"]').click(); await page.waitForSelector('#cap-start', { timeout: 8000 });
  check('captura:painel-abre', (await page.locator('#cap-start').count()) === 1);

  // ---- Shift+A: seleciona tudo, desloca com . e apaga com Del
  await page.mouse.click(900, 700); await page.keyboard.press('Escape');
  const n = (await tl()).clips.length;
  await page.keyboard.press('Shift+A'); await wait(300);
  check('shift+a:seleciona-todos-os-clipes', (await page.locator('.stl-clip.sel').count()) === n);
  const before = Object.fromEntries((await tl()).clips.map((c) => [c.id, c.start]));
  await page.keyboard.press('Shift+Period'); await wait(1400);   // Shift + . = 1 s para a direita
  const after = Object.fromEntries((await tl()).clips.map((c) => [c.id, c.start]));
  check('shift+a:desloca-tudo-para-a-direita', Object.keys(before).every((id) => Math.abs(after[id] - before[id] - 1) < 0.01));
  await page.keyboard.press('Shift+Comma'); await wait(1400);
  const back = Object.fromEntries((await tl()).clips.map((c) => [c.id, c.start]));
  check('shift+a:desloca-tudo-para-a-esquerda', Object.keys(before).every((id) => Math.abs(back[id] - before[id]) < 0.01));
  await page.keyboard.press('Delete'); await wait(1500);
  check('shift+a:apaga-tudo', (await tl()).clips.length === 0);
  await page.keyboard.press('Control+z'); await wait(1400);
  check('shift+a:desfazer-traz-tudo-de-volta', (await tl()).clips.length === n);

  // ---- muitos clipes: só os próximos da janela viram elementos
  const cur = await tl(); const vt = cur.tracks.find((x) => x.kind === 'video').id; const asset = full.assets.find((a) => a.kind === 'video').id;
  const many = Array.from({ length: 1500 }, (_, i) => ({ id: 'm' + i, track: vt, asset, start: i * 2, dur: 1.9, in: 0 }));
  await api(`/api/studio/projects/${p.id}/episodes/${p.episodes[0].id}/timeline`, { method: 'PUT', body: { timeline: { tracks: cur.tracks, clips: many } } });
  await page.evaluate((id) => { location.hash = '#/studio/' + id + '/export'; }, p.id); await wait(500);
  check('exportar:fps-e-resolucoes', (await page.locator('#st-exp-hint').count()) === 1);
  const opts = await page.locator('.st-export select').evaluateAll((els) => els.map((e) => [...e.options].map((o) => o.textContent)));
  check('exportar:opcoes-24-30-60-120-fps', opts.some((o) => o.join() === '24 fps,30 fps,60 fps,120 fps'));
  check('exportar:opcoes-2K-e-4K', opts.some((o) => o.includes('2K') && o.includes('4K') && o.includes('1080p')));
  await page.evaluate((id) => { location.hash = '#/studio/' + id + '/timeline'; }, p.id); await page.waitForSelector('.stl-clip', { timeout: 15000 }); await wait(500);
  const drawn = await page.locator('.stl-clip').count();
  check('desempenho:so-os-clipes-proximos-sao-desenhados', drawn > 0 && drawn < 300);
  await page.locator('.stl-scroll').evaluate((el) => { el.scrollLeft = 60000; }); await wait(600);
  const ids2 = await page.locator('.stl-clip').evaluateAll((els) => els.map((e) => e.dataset.id));
  check('desempenho:ao-rolar-os-clipes-novos-aparecem', ids2.length > 0 && ids2.length < 300 && ids2.some((i) => parseInt(i.slice(1), 10) > 600));
  fs.rmSync(dir, { recursive: true, force: true });
});
