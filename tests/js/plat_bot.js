// Robô jogador: verifica que as fases geradas são completáveis com a física real do motor.
const G2 = require('./_load')(['common.js', 'platformer.js']).G2;
const { World, TS } = G2.Plat;
const specs = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
function bot(w, st) {
  const p = w.p, ty0 = Math.floor((p.y + p.h - 2) / TS), cx = Math.floor((p.x + p.w / 2) / TS); let jump = false;
  const groundAt = (tx) => { for (let y = ty0 + 1; y < w.h; y++) { const ch = w.tile(tx, y); if (w.solidTile(ch) || ch === '=') return true; } return false; };
  if (p.ground) {
    if (w.solidTile(w.tile(cx + 1, ty0)) || w.solidTile(w.tile(cx + 1, ty0 - 1))) jump = true;
    if (!groundAt(cx + 1)) jump = true;
    if (w.tile(cx + 1, ty0) === '^' || w.tile(cx + 2, ty0) === '^' || w.tile(cx + 3, ty0) === '^') jump = true;
    w.ents.forEach((e) => { if (e.type === 'enemy' && e.alive && e.x > p.x && e.x - p.x < 84 && Math.abs(e.y - p.y) < 60) jump = true; });
  }
  if (st.holdT > 0) st.holdT -= 1 / 60;
  const inp = { left: false, right: true, jumpPressed: jump && st.holdT <= 0, jumpHeld: jump || st.holdT > 0 };
  if (inp.jumpPressed) st.holdT = 0.5;
  return inp;
}
const out = { levels: 0, done: 0, failed: [], respawnOverVoid: 0 };
for (const spec of specs) spec.data.levels.forEach((lv, li) => {
  const w = new World(lv, Object.assign({ hp: 3, speed: 1, jump: 1, double_jump: false }, spec.data.player)), st = { holdT: 0 }; let deaths = 0;
  for (let i = 0; i < 60 * 200 && !w.done; i++) {
    w.step(1 / 60, bot(w, st)); w.events.length = 0;
    if (w.p.dead && w.p.deadT > 0.6) { deaths++; w.respawn(); const below = (() => { const tx = Math.floor((w.p.x + w.p.w / 2) / TS); for (let y = Math.floor(w.p.y / TS); y < w.h; y++) if ('#S='.includes(w.tile(tx, y))) return true; return false; })(); if (!below) out.respawnOverVoid++; }
    if (deaths > 12) break;
  }
  out.levels++; if (w.done) out.done++; else out.failed.push(spec.title + ' L' + li);
});
console.log(JSON.stringify(out));
