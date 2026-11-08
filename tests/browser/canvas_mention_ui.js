// v0.17.2 — «@» nos prompts do nó Imagem: lista as imagens do canvas, insere o apelido, mostra as fichas e salva.
const { run } = require('./_common.js');
const { execFileSync } = require('child_process');
const fs = require('fs'); const os = require('os'); const path = require('path');
run('canvas_mention', async ({ api, open, check }) => {
  const page = await open({ width: 1600, height: 1000 });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'asta-men-'));
  const base = page.url().split('#')[0];
  const cv = await api('/api/canvases', { method: 'POST', body: { name: 'Menções', template: 'blank' } });
  for (const [name, color] of [['fnaf-1-office.png', 'red'], ['Foto Perfil.png', 'blue']]) {
    const f = path.join(dir, name); execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', `color=c=${color}:s=64x64`, '-frames:v', '1', f]);
    await fetch(`${base}api/canvases/${cv.id}/assets`, { method: 'POST', headers: { 'X-Filename': encodeURIComponent(name), 'Content-Type': 'image/png' }, body: fs.readFileSync(f) });
  }
  await api(`/api/canvases/${cv.id}`, { method: 'PUT', body: { name: 'Menções', edges: [], nodes: [{ id: 'im', type: 'image', x: 20, y: 20, params: {} }, { id: 'vi', type: 'video', x: 400, y: 20, params: {} }] } });
  await page.evaluate((id) => { location.hash = '#/canvas/edit/' + id; }, cv.id); await page.waitForSelector('.cv-node', { timeout: 10000 }); await page.waitForTimeout(500);
  const ta = page.locator('.cv-node[data-id="im"] .mwrap textarea');
  check('prompt-de-imagem-e-video-aceitam-menção', (await ta.count()) === 1 && (await page.locator('.cv-node[data-id="vi"] .mwrap textarea').count()) === 1);
  await ta.click(); await ta.pressSequentially('fundo @fn');
  await page.waitForSelector('.mpop:not(.hidden) .mi[data-slug]', { timeout: 5000 });
  check('lista-filtra-pelo-apelido', (await page.locator('.mpop .mi[data-slug]').count()) === 1 && (await page.locator('.mpop .mi[data-slug="fnaf-1-office"]').count()) === 1);
  await page.keyboard.press('Enter'); await page.waitForTimeout(200);
  check('enter-insere-o-apelido', (await ta.inputValue()) === 'fundo @fnaf-1-office ');
  await ta.pressSequentially('e @'); await page.waitForSelector('.mpop:not(.hidden) .mi[data-slug]', { timeout: 5000 });
  check('arroba-sozinho-lista-todas', (await page.locator('.mpop .mi[data-slug]').count()) === 2);
  await page.keyboard.press('ArrowDown'); await page.keyboard.press('Tab'); await page.waitForTimeout(200);
  check('seta-e-tab-escolhem-outra', (await ta.inputValue()).endsWith('@foto-perfil '));
  await ta.pressSequentially('@fantasma'); await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  check('esc-fecha-a-lista', (await page.locator('.mpop:not(.hidden)').count()) === 0);
  check('fichas-das-citadas-e-aviso-da-inexistente', (await page.locator('.mchip:not(.bad)').count()) === 2 && (await page.locator('.mchip.bad').count()) === 1);
  await page.waitForTimeout(1500);
  const saved = (await api(`/api/canvases/${cv.id}`)).nodes.find((n) => n.id === 'im');
  check('prompt-salvo-com-as-menções', saved.params.prompt === 'fundo @fnaf-1-office e @foto-perfil @fantasma');
  fs.rmSync(dir, { recursive: true, force: true });
});
