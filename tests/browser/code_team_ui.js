// Code com a equipe de agentes de verdade (LLM roteirizado pelo teste Python): grade de agentes, plano, ações, arquivos mudados, diff, navegador de arquivos e Desfazer.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { run, until } = require('./_common');
run('code_team', async ({ api, open, check, base }) => {
  const proj = fs.mkdtempSync(path.join(os.tmpdir(), 'asta-code-team-'));
  fs.writeFileSync(path.join(proj, 'keep.txt'), 'antes\n');
  try {
    await api('/api/settings', { method: 'PUT', body: { language: 'pt-BR', code: { mode: 'full', effort: 'high', agents: 4 } } });
    const s = await api('/api/code/sessions', { method: 'POST', body: { title: 'Equipe', mode: 'full', effort: 'extra', agents: 3, workspace: { type: 'local', path: proj } } });
    const page = await open();
    await page.goto(base + '/#/code/' + s.id); await page.waitForSelector('.composer textarea');
    await page.locator('.composer textarea').fill('crie a.py e b.py e ajuste keep.txt');
    await page.locator('.composer .send').click();
    await page.waitForSelector('#cd-run');
    await until(page, () => !!document.querySelector('.cd-msg.ai'));
    check('team:agentes-aparecem-na-grade', (await page.locator('.cd-ag[data-agent="planner"]').count()) === 1 && (await page.locator('.cd-ag[data-agent="w1"]').count()) === 1 && (await page.locator('.cd-ag[data-agent="w2"]').count()) === 1);
    check('team:equipe-completa-ate-o-relator', (await page.locator('.cd-ag[data-agent="reviewer"]').count()) === 1 && (await page.locator('.cd-ag[data-agent="reporter"]').count()) === 1);
    check('team:plano-com-tres-tarefas-feitas', (await page.locator('#cd-plan li').count()) === 3 && (await page.locator('#cd-plan li[data-status="done"]').count()) === 3);
    check('team:acoes-listadas-com-ferramenta', (await page.locator('.cd-step[data-tool="write_file"]').count()) >= 2 && (await page.locator('.cd-step[data-tool="edit_file"]').count()) === 1);
    await page.locator('#cd-acts summary').click();
    await page.locator('.cd-step[data-tool="edit_file"] .cd-sh').click();
    check('team:acao-expande-com-o-resultado', (await page.locator('.cd-step.open .cd-sd pre').innerText()).includes('Editei'));
    check('team:resumo-na-conversa', (await page.locator('.cd-msg.ai .md').innerText()).includes('Feito'));
    check('team:arquivos-mudados-no-painel', (await page.locator('#cd-changed li').count()) === 3 && (await page.locator('#cd-changed li[data-path="a.py"][data-status="created"]').count()) === 1 && (await page.locator('#cd-changed li[data-path="keep.txt"][data-status="modified"]').count()) === 1);
    check('team:estado-azul-ao-terminar-aberta-vira-cinza', ['idle', 'done'].includes(await page.locator('.cd-item.on .cd-dot').getAttribute('data-dot')));
    // diff
    await page.locator('#cd-changed li[data-path="keep.txt"] .cd-fl').click(); await page.waitForSelector('.cd-diff');
    check('team:diff-colorido', (await page.locator('.cd-diff .add').count()) >= 1 && (await page.locator('.cd-diff .del').count()) >= 1 && (await page.locator('.cd-diff').innerText()).includes('depois'));
    await page.locator('.modal .foot .primary').click();
    // navegador de arquivos
    await page.locator('#cd-files').click(); await page.waitForSelector('.cd-fi2');
    check('team:navegador-lista-os-arquivos', (await page.locator('.cd-fi2[data-path="a.py"]').count()) === 1);
    await page.locator('.cd-fi2[data-path="a.py"]').click();
    await until(page, () => document.querySelector('.cd-fview').textContent.includes('A = 1'));
    check('team:navegador-mostra-o-conteudo', true);
    await page.locator('.modal .foot .primary').click();
    // desfazer
    await page.locator('#cd-undo').click(); await page.locator('.modal .btn.danger').click();
    await until(page, () => !document.querySelector('#cd-undo'));
    check('team:desfazer-restaura-os-arquivos', fs.readFileSync(path.join(proj, 'keep.txt'), 'utf8') === 'antes\n' && !fs.existsSync(path.join(proj, 'a.py')) && !fs.existsSync(path.join(proj, 'b.py')));
    check('team:lista-de-saidas-esvazia', (await page.locator('#cd-changed li').count()) === 0);
    // celular: sem rolagem horizontal com a equipe na tela
    const phone = await open({ width: 390, height: 800 });
    await phone.goto(base + '/#/code/' + s.id); await phone.waitForSelector('#cd-run');
    check('team:celular-sem-rolagem-horizontal', await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  } finally {
    fs.rmSync(proj, { recursive: true, force: true });
  }
});
