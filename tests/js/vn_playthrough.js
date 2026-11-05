// Partidas aleatórias de uma visual novel: tudo termina, os finais são alcançáveis e save/restore é consistente.
const G2 = require('./_load')(['common.js', 'vn.js']).G2;
const spec = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
let seed = 7; const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
const out = { endings: {}, bad: [] };
for (let run = 0; run < 150; run++) {
  const r = new G2.VN.Runner(spec.data); let w = r.advance(), steps = 0;
  while (w && w.type !== 'end' && steps < 4000) { w = w.type === 'menu' ? r.choose(Math.floor(rnd() * w.options.length)) : w.type === 'input' ? r.answer('Teste') : r.advance(); steps++; }
  if (!w || w.type !== 'end') out.bad.push('run ' + run + ' não terminou'); else out.endings[w.title] = (out.endings[w.title] || 0) + 1;
  const r2 = new G2.VN.Runner(spec.data); let w2 = r2.advance(), n = Math.floor(rnd() * 14);
  while (n-- > 0 && w2.type !== 'end') w2 = w2.type === 'menu' ? r2.choose(0) : w2.type === 'input' ? r2.answer('X') : r2.advance();
  const snap = JSON.parse(JSON.stringify(r2.snapshot())), before = JSON.stringify(w2), r3 = new G2.VN.Runner(spec.data); r3.restore(snap);
  if (w2.type !== 'wait' && before !== JSON.stringify(r3.advance())) out.bad.push('restore diferente: ' + before);
}
console.log(JSON.stringify(out));
