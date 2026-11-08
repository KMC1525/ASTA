// v0.14 — edição manual na timeline do Studio: trilha de destino das mídias, velocidade que ajusta a duração, lâmina só no clipe clicado, salvar ao trocar de aba.
const { run } = require('./_common.js');
const { execFileSync } = require('child_process');
const fs = require('fs'); const os = require('os'); const path = require('path');
run('studio_edit', async ({ open, api, check }) => {
  const page = await open({ width: 1700, height: 1000 });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'asta-edit-'));
  const mp4 = path.join(dir, 'v.mp4'), wav = path.join(dir, 't.wav');
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc=d=4:s=160x90:r=24', '-pix_fmt', 'yuv420p', mp4]);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=f=300:d=5', wav]);
  const p = await api('/api/studio/projects', { method: 'POST', body: { name: 'Edição', origin: 'manual', duration_type: 'custom', target_seconds: 30 } });
  const up = async (file, name, type) => (await fetch(`${page.url().split('#')[0]}api/studio/projects/${p.id}/media`, { method: 'POST', headers: { 'X-Filename': name, 'Content-Type': type }, body: fs.readFileSync(file) })).status;
  check('midias-importadas', (await up(mp4, 'v.mp4', 'video/mp4')) === 201 && (await up(mp4, 'w.mp4', 'video/mp4')) === 201 && (await up(wav, 't.wav', 'audio/wav')) === 201);
  await page.evaluate((id) => { location.hash = '#/studio/' + id + '/timeline'; }, p.id);
  await page.waitForSelector('.stl-asset', { timeout: 15000 });
  const tl = async () => (await api(`/api/studio/projects/${p.id}`)).episodes[0].timeline;
  const wait = (ms = 1200) => page.waitForTimeout(ms);
  await page.locator('.stl-asset', { hasText: 't.wav' }).dblclick(); await wait(400);
  await page.locator('.stl-asset', { hasText: 'v.mp4' }).dblclick(); await wait(400);
  await page.locator('.stl-asset', { hasText: 'w.mp4' }).dblclick(); await wait();
  let t = await tl();
  const tr = (a) => t.clips.find((c) => c.label.startsWith(a)).track;
  check('trilha:audio-vai-para-a-A1', tr('t.wav') === 't_a1');
  check('trilha:video-vai-para-a-V1', tr('v.mp4') === 't_v1');
  check('trilha:segundo-video-no-mesmo-instante-sobe-para-a-V2', tr('w.mp4') === 't_v2');
  // velocidade: 2× usa o mesmo trecho em metade do tempo
  await page.locator('.stl-row[data-track="t_v1"] .stl-clip').first().click();
  await page.locator('select[data-k="speed"]').selectOption('2'); await wait();
  t = await tl(); const v1 = t.clips.find((c) => c.track === 't_v1');
  check('velocidade:2x-reduz-a-duracao-pela-metade', v1.speed === 2 && Math.abs(v1.dur - 2) < 0.15);
  await page.locator('select[data-k="speed"]').selectOption('1'); await wait();
  t = await tl(); check('velocidade:voltar-a-1x-restaura-a-duracao', Math.abs(t.clips.find((c) => c.track === 't_v1').dur - 4) < 0.15);
  // a mídia deixou de ter o monitor do clipe
  check('sem-monitor-do-clipe', (await page.locator('.stl-clipmon, #cm-insert').count()) === 0);
  // trocar de aba logo depois de editar não perde a edição
  await page.keyboard.press('Control+a'); await page.keyboard.press('m');
  await page.locator('#st-tab-export').click(); await wait(1500);
  t = await tl(); check('salvar:trocar-de-aba-nao-perde-a-ultima-edicao', t.clips.filter((c) => c.mute).length >= 2);
  fs.rmSync(dir, { recursive: true, force: true });
});
