// Lista as frases em português da interface que não têm tradução em en.js:
//  - literais t('...') em qualquer arquivo de web/js;
//  - textos de mapas usados com t(variável) (etapas dos pipelines, gêneros, relações, nós do Canvas…).
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'asta', 'web', 'js');
const EN = (await import(pathToFileURL(join(root, 'en.js')).href)).default;
const files = [];
(function walk(d) { for (const f of readdirSync(d)) { const p = join(d, f); if (statSync(p).isDirectory()) walk(p); else if (f.endsWith('.js') && f !== 'en.js') files.push(p); } })(root);

const missing = new Set();
const lit = /(?<![\w.$])t\(\s*(?:'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)")/g;
for (const f of files) {
  const src = readFileSync(f, 'utf8');
  for (const m of src.matchAll(lit)) {
    const s = (m[1] ?? m[2]).replace(/\\'/g, "'").replace(/\\"/g, '"').replace(/\\n/g, '\n');
    if (!(s in EN)) missing.add(s);
  }
}
const bag = new Set();
const walkv = (v) => { if (typeof v === 'string') bag.add(v); else if (Array.isArray(v)) v.forEach(walkv); else if (v && typeof v === 'object') Object.values(v).forEach(walkv); };
const steps = await import(pathToFileURL(join(root, 'views', 'steps.js')).href);
const av = await import(pathToFileURL(join(root, 'avatar_ui.js')).href);
const cn = await import(pathToFileURL(join(root, 'canvas_nodes.js')).href);
['WORLD', 'AVATAR', 'GAME', 'GENRE_LABEL', 'MOOD', 'AMB'].forEach((n) => walkv(steps[n]));
walkv(av.REL_LABEL); { const q = await import(pathToFileURL(join(root, 'model_labels.js')).href); walkv(q.QUALITY_LABEL); walkv(q.PREC_HINT); walkv(q.GGUF_KINDS.map(([, l]) => l)); walkv(q.GGUF_HINT); } walkv(cn.LABEL); walkv(cn.TYPE_HELP); cn.GROUPS.forEach(([g]) => bag.add(g));
for (const s of bag) if (!(s in EN)) missing.add(s);
const empty = Object.entries(EN).filter(([, v]) => !String(v).trim()).map(([k]) => k);
console.log(JSON.stringify({ missing: [...missing], empty, keys: Object.keys(EN).length }));
