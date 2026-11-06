// Timeline do Studio (estilo Kdenlive): monitor do clipe com entrada/saída e inserir, mixer de áudio com faders em dB e volume geral, zoom embaixo e trilhas recolhíveis.
const { run } = require('./_common.js');
run('studio_mixer', async ({ open, api, check }) => {
  const page = await open({ width: 1700, height: 1000 });
  const p = await api('/api/studio/projects', { method: 'POST', body: { name: 'Mixer', origin: 'manual', duration_type: 'custom', target_seconds: 30 } });
  // uma mídia de áudio e uma de vídeo no projeto (arquivos sintéticos mínimos via ffmpeg no teste Python não estão disponíveis aqui: usa um WAV gerado em JS)
  const wav = Buffer.alloc(44 + 16000 * 2 * 4); wav.write('RIFF', 0); wav.writeUInt32LE(36 + 16000 * 8, 4); wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(16000, 24); wav.writeUInt32LE(32000, 28); wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(16000 * 8, 40);
  for (let i = 0; i < 16000 * 4; i++) wav.writeInt16LE(Math.round(8000 * Math.sin(i / 20)), 44 + i * 2);
  const r = await fetch(`${page.url().split('#')[0]}api/studio/projects/${p.id}/media`, { method: 'POST', headers: { 'X-Filename': 'tom.wav', 'Content-Type': 'audio/wav' }, body: wav });
  check('midia-importada', r.status === 201);
  await page.evaluate((id) => { location.hash = '#/studio/' + id + '/timeline'; }, p.id);
  await page.waitForSelector('.stl-mixer .stl-strip', { timeout: 15000 });
  const names = await page.locator('.stl-strip .nm').allInnerTexts();
  check('mixer:tem-faixa-por-trilha-de-video-e-audio-mais-principal', names.includes('V1') && names.includes('A1') && names.some((x) => /Principal|Master|Main/.test(x)) && !names.includes('T1'));
  check('mixer:fader-comeca-em-0-dB', (await page.locator('input.db[data-db="t_a1"]').inputValue()) === '0.0' || (await page.locator('input.db[data-db="t_a1"]').inputValue()) === '+0.0');
  // fader e dB: digitar -6 dB vira ~0,5 no projeto
  await page.fill('input.db[data-db="t_a1"]', '-6'); await page.keyboard.press('Enter'); await page.waitForTimeout(1200);
  let tl = (await api(`/api/studio/projects/${p.id}`)).episodes[0].timeline;
  const a1 = tl.tracks.find((t) => t.id === 't_a1');
  check('mixer:db-digitado-salva-o-volume-da-trilha', Math.abs(a1.volume - 0.501) < 0.02);
  await page.fill('input.db[data-db="master"]', '-12'); await page.keyboard.press('Enter'); await page.waitForTimeout(1200);
  tl = (await api(`/api/studio/projects/${p.id}`)).episodes[0].timeline;
  check('mixer:volume-geral-salvo', Math.abs(tl.master - 0.251) < 0.02);
  await page.locator('input.fd[data-fader="t_a1"]').dblclick(); await page.waitForTimeout(1200);
  tl = (await api(`/api/studio/projects/${p.id}`)).episodes[0].timeline;
  check('mixer:dois-cliques-no-fader-voltam-a-0-dB', tl.tracks.find((t) => t.id === 't_a1').volume === 1);
  await page.locator('button[data-mute="t_a1"]').click(); await page.waitForTimeout(1200);
  check('mixer:mudo-da-trilha', (await api(`/api/studio/projects/${p.id}`)).episodes[0].timeline.tracks.find((t) => t.id === 't_a1').muted === true);
  // painéis liga/desliga
  await page.locator('#stl-mixer-btn, #stl-mixer').first().waitFor();
  await page.locator('.stl-bar #stl-mixer').click(); await page.waitForTimeout(300);
  check('mixer:botao-esconde-o-painel', !(await page.locator('.stl-mixer').isVisible()));
  await page.locator('.stl-bar #stl-mixer').click(); await page.waitForTimeout(300);
  // monitor do clipe: clique na mídia carrega; marcar saída e inserir
  await page.locator('.stl-asset').first().click(); await page.waitForSelector('#stl-clipmon audio, #stl-clipmon video', { state: 'attached', timeout: 8000 });
  check('monitor-do-clipe:carrega-a-midia-clicada', (await page.locator('#stl-clipmon .cm-name').innerText()).includes('tom.wav'));
  await page.locator('#cm-insert').click(); await page.waitForTimeout(1300);
  tl = (await api(`/api/studio/projects/${p.id}`)).episodes[0].timeline;
  check('monitor-do-clipe:inserir-poe-o-clipe-no-cursor', tl.clips.length === 1 && tl.clips[0].start === 0 && Math.abs(tl.clips[0].dur - 4) < 0.6);
  await page.locator('#cm-insert').click(); await page.waitForTimeout(1300);   // cursor em 0: o segundo empurra o primeiro (modo «inserir»)
  tl = (await api(`/api/studio/projects/${p.id}`)).episodes[0].timeline;
  const starts = tl.clips.map((c) => c.start).sort((a, b) => a - b);
  check('monitor-do-clipe:inserir-empurra-o-que-vem-depois', tl.clips.length === 2 && starts[0] === 0 && starts[1] >= tl.clips[0].dur - 0.7);
  // zoom embaixo
  const before = await page.locator('#stl-zoom').inputValue();
  await page.locator('#stl-zoom').fill('90'); await page.waitForTimeout(300);
  check('zoom:barra-de-baixo-muda-a-escala', (await page.locator('#stl-zoom').inputValue()) === '90' && before !== '90' && (await page.locator('#stl-pos').innerText()).includes('/'));
  // trilha recolhível
  const h0 = await page.locator('.stl-row[data-track="t_v2"]').evaluate((e) => e.getBoundingClientRect().height);
  await page.locator('.stl-row[data-track="t_v2"] .chev').click(); await page.waitForTimeout(300);
  const h1 = await page.locator('.stl-row[data-track="t_v2"]').evaluate((e) => e.getBoundingClientRect().height);
  check('trilha:recolher-diminui-a-altura', h1 < h0 * 0.6);
  await page.waitForTimeout(1200);
  check('trilha:recolhida-fica-salva', (await api(`/api/studio/projects/${p.id}`)).episodes[0].timeline.tracks.find((t) => t.id === 't_v2').collapsed === true);
});
