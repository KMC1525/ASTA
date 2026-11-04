"""Testes do runtime JS (funções puras) via Node — pulado se Node não existir."""
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "asta" / "runtime"

SCRIPT = r"""
const fs = require('fs'), vm = require('vm');
const ctx = vm.createContext({ navigator: { language: 'pt-BR', hardwareConcurrency: 8 }, document: {}, location: { search: '' }, console });
ctx.window = ctx; ctx.globalThis = ctx;
vm.runInContext(fs.readFileSync(process.argv[1] + '/core.js', 'utf8'), ctx);
const RT = ctx.RT; const out = {};
const a = RT.rng(42), b = RT.rng(42);
out.rngDeterministic = a() === b() && a() === b();
out.noiseRange = (() => { let ok = true; for (let i = 0; i < 2000; i++) { const v = RT.fbm(i * 0.37, i * 0.11, 7); if (!(v >= 0 && v <= 1)) ok = false; } return ok; })();
out.noiseDeterministic = RT.fbm(3.3, 4.4, 9) === RT.fbm(3.3, 4.4, 9);
out.langs = ['Olá, tudo bem com você?', 'Hello, how are you?', 'Hola, ¿qué tal?', 'こんにちは', '안녕하세요', 'Привет', 'Bonjour, je suis très content', 'Guten Tag, ich bin nicht müde'].map(s => RT.detectLang(s, 'xx'));
out.clamp = [RT.clamp(5, 0, 1), RT.clamp(-5, 0, 1)];
out.angle = Math.abs(RT.angleDiff(0.1, 2 * Math.PI - 0.1) + 0.2) < 1e-9;
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "Node.js não instalado")
class RuntimeTests(unittest.TestCase):
    def test_core_pure_functions(self):
        import json

        r = subprocess.run(["node", "-e", SCRIPT, str(RUNTIME)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertTrue(out["rngDeterministic"])
        self.assertTrue(out["noiseRange"])
        self.assertTrue(out["noiseDeterministic"])
        self.assertEqual(out["langs"], ["pt-BR", "en-US", "es-ES", "ja-JP", "ko-KR", "ru-RU", "fr-FR", "de-DE"])
        self.assertEqual(out["clamp"], [1, 0])
        self.assertTrue(out["angle"])

    def test_all_js_parse(self):
        files = list(RUNTIME.glob("*.js")) + list((ROOT / "asta" / "web" / "js").rglob("*.js"))
        self.assertGreater(len(files), 10)
        for f in files:
            is_module = "web" in f.parts
            cmd = ["node", "--input-type=module", "--check"] if is_module else ["node", "--check", str(f)]
            r = subprocess.run(cmd, input=f.read_text("utf-8") if is_module else None, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, f"{f}: {r.stderr}")

    def test_vendor_three_loads_as_classic_script(self):
        script = r"""
        const fs = require('fs'), vm = require('vm');
        const ctx = vm.createContext({}); ctx.globalThis = ctx;
        vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
        console.log(ctx.THREE.REVISION);
        """
        r = subprocess.run(["node", "-e", script, str(RUNTIME / "vendor" / "three.min.js")], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.stdout.strip(), "159", r.stderr)


if __name__ == "__main__":
    unittest.main()
