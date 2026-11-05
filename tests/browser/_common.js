// Utilidades dos testes de navegador (Playwright + Chromium). Cada script imprime uma linha JSON: { checks: {nome: bool}, errors: [..] }.
const { chromium } = require('playwright');

exports.run = async function run(name, fn) {
  const port = process.env.ASTA_PORT;
  const base = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch();
  const result = { checks: {}, errors: [] };
  const check = (label, ok) => { result.checks[label] = !!ok; };
  const api = async (path, opts = {}) => {
    const r = await fetch(base + path, { ...opts, headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) }, body: opts.body && typeof opts.body !== 'string' && !Buffer.isBuffer(opts.body) ? JSON.stringify(opts.body) : opts.body });
    return r.json();
  };
  const open = async (viewport = { width: 1400, height: 900 }) => {
    await api('/api/settings', { method: 'PUT', body: { ui: { welcome_done: true } } });  // sem o modal de boas-vindas da instalação nova
    const page = await browser.newPage({ viewport });
    page.on('pageerror', (e) => result.errors.push(`${name} pageerror: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') result.errors.push(`${name} console: ${m.text()}`); });
    await page.goto(base + '/');
    return page;
  };
  try { await fn({ base, api, open, check, browser }); }
  catch (e) { result.errors.push(`${name} falhou: ${e.message}`); }
  await browser.close();
  console.log(JSON.stringify(result));
};
exports.until = async (page, fn, arg, timeout = 90000) => page.waitForFunction(fn, arg, { timeout });
// Liga uma ferramenta de criação (ativador) no Chat: world | avatar | game | canvas
exports.useTool = async (page, id) => {
  await page.locator('.composer .tool[aria-haspopup]').click();
  await page.locator(`.toolmenu .toolopt[data-tool="${id}"]`).click();
  await page.waitForTimeout(450);
};
