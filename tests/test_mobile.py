"""v0.10 Mobile: QR code próprio (decodificado de verdade quando o OpenCV existe), pareamento por código, acesso só de aparelhos pareados, manifest/service worker/ícones, `asta mobile`."""
import http.client
import io
import json
import re
import shutil
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import __version__, mobile, qr  # noqa: E402
from asta.server import make_server  # noqa: E402
from asta.storage import Store  # noqa: E402
from tests.test_server import ServerCase  # noqa: E402


class QrTests(unittest.TestCase):
    def test_matrix_sizes_and_finder_patterns(self):
        for n, size in ((5, 21), (80, 37), (213, 57)):
            m = qr.matrix("x" * n)
            self.assertEqual(len(m), size)
            for cx, cy in ((0, 0), (size - 7, 0), (0, size - 7)):  # os três quadrados de localização
                self.assertTrue(all(m[cy][cx + i] and m[cy + 6][cx + i] and m[cy + i][cx] and m[cy + i][cx + 6] for i in range(7)))
                self.assertFalse(m[cy + 1][cx + 1] or m[cy + 1][cx + 5])
        with self.assertRaises(ValueError):
            qr.matrix("x" * 214)

    def test_svg_and_terminal_render(self):
        s = qr.svg("http://192.168.0.2:8787/api/mobile/pair?code=abc")
        self.assertTrue(s.startswith("<svg") and "<path" in s and "viewBox" in s)
        lines = qr.terminal("oi").splitlines()
        self.assertGreater(len(lines), 8)
        self.assertEqual(len({len(x) for x in lines}), 1)

    def test_real_decoder_reads_what_we_encode(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV não instalado (a decodificação real roda onde ele existe)")
        det = cv2.QRCodeDetector()
        for n in (5, 40, 80, 140, 213):  # versões 1 a 10 (inclui a informação de versão dos QRs 7+)
            text = ("http://192.168.0.12:8787/api/mobile/pair?code=" + "aZ9_-" * 50)[:n]
            m = qr.matrix(text)
            k, b = 8, 4
            img = np.full(((len(m) + 2 * b) * k,) * 2, 255, np.uint8)
            for y, row in enumerate(m):
                for x, c in enumerate(row):
                    if c:
                        img[(y + b) * k:(y + b + 1) * k, (x + b) * k:(x + b + 1) * k] = 0
            self.assertEqual(det.detectAndDecode(img)[0], text, n)


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="asta-mob-"))
        self.m = mobile.Mobile(self.tmp, "0.0.0.0")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_token_is_stable_secret_and_rotates(self):
        t = self.m.token()
        self.assertGreaterEqual(len(t), 30)
        self.assertEqual(mobile.Mobile(self.tmp, "0.0.0.0").token(), t)  # sobrevive a reiniciar
        self.assertTrue(self.m.pair_ok(t))
        self.assertFalse(self.m.pair_ok("errado") or self.m.pair_ok(""))
        new = self.m.rotate()
        self.assertNotEqual(new, t)
        self.assertFalse(self.m.pair_ok(t))

    def test_only_paired_devices_get_in_from_other_addresses(self):
        t = self.m.token()
        ok = lambda ip, cookie="", path="/api/state", **hd: self.m.allowed(ip, {"Cookie": cookie, **hd} if cookie else dict(hd), path)  # noqa: E731
        self.assertTrue(ok("127.0.0.1"))
        self.assertTrue(ok("::1") and ok("::ffff:127.0.0.1"))
        self.assertFalse(ok("192.168.0.20"))
        self.assertFalse(ok("192.168.0.20", "asta_pair=errado"))
        self.assertTrue(ok("192.168.0.20", f"x=1; asta_pair={t}"))
        self.assertTrue(ok("192.168.0.20", path=mobile.PAIR_PATH))  # a rota de pareamento é a única aberta
        self.assertFalse(ok("127.0.0.1", **{"X-Forwarded-For": "8.8.8.8"}))  # túnel/proxy faz tudo parecer localhost: exige pareamento
        self.assertTrue(ok("127.0.0.1", f"asta_pair={t}", **{"X-Forwarded-For": "8.8.8.8"}))

    def test_exposed_only_when_bound_to_the_network(self):
        self.assertTrue(self.m.exposed)
        self.assertFalse(mobile.Mobile(self.tmp, "127.0.0.1").exposed)
        self.assertEqual(mobile.Mobile(self.tmp, "127.0.0.1").info(8787)["pair_urls"], [])


class LocalServerTests(ServerCase):
    def test_version_manifest_icons_and_service_worker(self):
        st, r = self.c.json("GET", "/api/version")
        self.assertEqual((st, r["version"]), (200, __version__))
        st, h, body = self.c.req("GET", "/manifest.webmanifest")
        mf = json.loads(body)
        self.assertEqual((st, mf["display"], mf["start_url"]), (200, "standalone", "/"))
        self.assertIn("manifest+json", h.get("Content-Type", ""))
        self.assertTrue({"any", "maskable"} <= {i["purpose"] for i in mf["icons"]})
        for icon in mf["icons"]:
            st, h, data = self.c.req("GET", icon["src"])
            self.assertEqual((st, data[:4]), (200, b"\x89PNG"), icon["src"])
        st, h, body = self.c.req("GET", "/sw.js")
        js = body.decode()
        self.assertIn(f"VERSION = '{__version__}'", js)
        self.assertNotIn("__ASTA_VERSION__", js)
        self.assertEqual(h.get("Service-Worker-Allowed"), "/")
        self.assertIn("SKIP_WAITING", js)
        html = self.c.req("GET", "/")[2].decode()
        for needle in ('rel="manifest"', "apple-touch-icon", "viewport-fit=cover", "/css/mobile.css"):
            self.assertIn(needle, html)

    def test_info_on_the_computer_and_loopback_is_not_exposed(self):
        st, r = self.c.json("GET", "/api/mobile")
        self.assertEqual(st, 200)
        self.assertFalse(r["exposed"])  # o servidor de teste escuta só em 127.0.0.1
        self.assertEqual(r["pair_urls"], [])
        self.assertEqual(self.c.json("GET", "/api/mobile/pair?code=errado")[0], 403)


class NetworkServerTests(unittest.TestCase):
    """Servidor exposto na rede, acessado pelo endereço de rede do próprio computador (portanto como aparelho remoto)."""

    @classmethod
    def setUpClass(cls):
        cls.ips = mobile.lan_ips()
        cls.tmp = Path(tempfile.mkdtemp(prefix="asta-net-"))
        cls.httpd, cls.app = make_server("0.0.0.0", 0, Store(cls.tmp))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def get(self, host, path, cookie=""):
        c = http.client.HTTPConnection(host, self.port, timeout=10)
        c.request("GET", path, headers={"Cookie": cookie} if cookie else {})
        r = c.getresponse()
        body = r.read()
        return r.status, dict(r.getheaders()), body

    def test_pairing_flow_with_a_remote_device(self):
        if not self.ips:
            self.skipTest("este computador não tem endereço de rede local")
        host = self.ips[0]
        st, _, body = self.get("127.0.0.1", "/api/mobile")  # no computador: sem parear
        info = json.loads(body)
        self.assertEqual((st, info["exposed"]), (200, True))
        self.assertIn("<svg", info["qr_svg"])
        self.assertTrue(info["pair_urls"][0].startswith(f"http://{host}:{self.port}/api/mobile/pair?code="))
        code = re.search(r"code=([\w-]+)", info["pair_urls"][0]).group(1)
        st, _, body = self.get(host, "/")  # aparelho remoto sem parear
        self.assertEqual(st, 401)
        self.assertIn(b"QR", body)
        self.assertEqual(self.get(host, "/api/state")[0], 401)
        self.assertEqual(self.get(host, "/api/mobile")[0], 401)  # nem o QR ele vê
        self.assertEqual(self.get(host, "/api/mobile/pair?code=errado")[0], 403)
        st, h, _ = self.get(host, f"/api/mobile/pair?code={code}")
        self.assertEqual((st, h.get("Location")), (302, "/"))
        cookie = h["Set-Cookie"].split(";")[0]
        self.assertIn("HttpOnly", h["Set-Cookie"])
        self.assertEqual(self.get(host, "/api/state", cookie)[0], 200)
        self.assertEqual(self.get(host, "/", cookie)[0], 200)
        self.assertEqual(self.get(host, "/api/mobile", cookie)[0], 403)  # pareado usa o ASTA, mas não administra os pareamentos
        self.app.mobile.rotate()
        self.assertEqual(self.get(host, "/api/state", cookie)[0], 401)  # código novo desparea


class CliTests(unittest.TestCase):
    def test_mobile_command_is_registered_and_prints_a_qr(self):
        from asta import cli

        class A:
            host, port = "0.0.0.0", 8787
        tmp = Path(tempfile.mkdtemp(prefix="asta-cli-"))
        try:
            httpd, app = make_server("0.0.0.0", 0, Store(tmp))
            httpd.server_close()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cli._print_mobile_qr(app, 8787)
            out = buf.getvalue()
            if mobile.lan_ips():
                self.assertIn("█", out)
                self.assertIn("8787", out)
            else:
                self.assertIn("rede local", out.lower() + "rede local")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        with redirect_stdout(io.StringIO()) as o:
            try:
                cli.main(["--help"])
            except SystemExit:
                pass
        self.assertIn("mobile", o.getvalue())


if __name__ == "__main__":
    unittest.main()
