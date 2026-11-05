// Paridade das condições (o Python valida o que o JS executa), temas e matemática do RPG.
const G2 = require('./_load')(['common.js', 'rpg.js']).G2;
const cases = JSON.parse(process.argv[2]);
const out = { cond: [], themes: Object.keys(G2.THEMES), fmt: G2.fmt('Oi {player}, {x}', { player: 'Ana' }) };
for (const [expr, vars] of cases) out.cond.push(G2.cond(expr, vars));
const R = G2.RPG, rnd = () => 0.5;
const m = R.member({ id: 'h', name: 'H', cls: 'warrior', level: 1, hp: 30, mp: 8, atk: 7, def: 3, mag: 4, spd: 5, skills: [], appearance: {} });
out.levels = R.gainXp(m, 200); out.stats = [m.level, m.maxhp, m.atk];
out.dmg = [R.physDamage(10, 2, rnd, false, false), R.physDamage(10, 2, rnd, true, false), R.physDamage(1, 50, rnd, false, false)];
out.flee = [R.fleeChance([{ spd: 5 }], [{ spd: 5 }], false), R.fleeChance([{ spd: 5 }], [{ spd: 5 }], true)];
console.log(JSON.stringify(out));
