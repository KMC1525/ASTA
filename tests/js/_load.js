// Carrega o runtime 2D (sem DOM) num contexto vm para testar a lógica pura dos motores.
const fs = require('fs'), vm = require('vm'), path = require('path');
module.exports = function load(files) {
  const ctx = vm.createContext({ navigator: { language: 'pt-BR' }, console, document: {}, location: { search: '' } });
  ctx.window = ctx; ctx.globalThis = ctx;
  const dir = path.join(__dirname, '..', '..', 'asta', 'runtime2d');
  (files || ['common.js']).forEach((f) => vm.runInContext(fs.readFileSync(path.join(dir, f), 'utf8'), ctx, { filename: f }));
  return ctx;
};
