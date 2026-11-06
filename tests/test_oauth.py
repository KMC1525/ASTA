"""Login com a conta do provedor: OpenRouter (OAuth PKCE) de verdade; os demais abrem a página de login. Nunca com chave exposta ao navegador."""
import base64
import hashlib
import http.client
import json
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import oauth  # noqa: E402
from asta.providers import describe_presets  # noqa: E402
from asta.server import make_server  # noqa: E402
from asta.storage import Store  # noqa: E402


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="asta-oauth-"))
        self.store = Store(self.tmp)
        self.httpd, self.app = make_server("127.0.0.1", 0, self.store)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers={"Content-Type": "application/json"} if body is not None else {})
        r = c.getresponse()
        return r.status, r.read().decode()

    def test_presets_tell_which_providers_have_login(self):
        by = {p["id"]: p for p in describe_presets()}
        self.assertTrue(by["openrouter"]["oauth"])
        for pid in ("anthropic", "openai", "xai", "google", "huggingface"):
            self.assertTrue(by[pid]["login"].startswith("https://"), pid)
            self.assertFalse(by[pid]["oauth"])
        self.assertEqual(by["ollama"]["login"], "")

    def test_openrouter_pkce_flow_saves_the_key_and_state_is_single_use(self):
        st, body = self.call("POST", "/api/auth/openrouter/start", {})
        self.assertEqual(st, 200)
        url = urllib.parse.urlsplit(json.loads(body)["url"])
        q = urllib.parse.parse_qs(url.query)
        self.assertEqual((url.netloc, q["code_challenge_method"][0]), ("openrouter.ai", "S256"))
        cb = urllib.parse.urlsplit(q["callback_url"][0])
        self.assertEqual(cb.netloc, f"127.0.0.1:{self.port}")
        state = urllib.parse.parse_qs(cb.query)["state"][0]
        seen = {}

        def fake_post(u, payload):
            seen.update(url=u, **payload)
            return {"key": "sk-or-v1-CONTA-DO-USUARIO"}
        with mock.patch.object(oauth, "_post_json", fake_post):
            st, page = self.call("GET", f"/api/auth/openrouter/callback?state={state}&code=abc123")
            self.assertEqual(st, 200)
            self.assertIn("conectada", page)
            self.assertEqual(self.call("GET", f"/api/auth/openrouter/callback?state={state}&code=abc123")[0], 400)  # o state só vale uma vez
        self.assertEqual(seen["url"], oauth.OPENROUTER_EXCHANGE)
        self.assertEqual(seen["code"], "abc123")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(seen["code_verifier"].encode()).digest()).decode().rstrip("=")
        self.assertEqual(challenge, q["code_challenge"][0])  # o verifier bate com o challenge enviado no início
        cfg = self.store.get_settings()["providers"]["openrouter"]
        self.assertEqual((cfg["api_key"], cfg.get("auth")), ("sk-or-v1-CONTA-DO-USUARIO", "account"))
        pub = self.store.public_settings()["providers"]["openrouter"]
        self.assertTrue(pub["has_key"])
        self.assertNotIn("api_key", pub)
        self.assertNotIn("CONTA-DO-USUARIO", json.dumps(self.store.public_settings()))

    def test_bad_callbacks_are_explained_and_save_nothing(self):
        self.assertEqual(self.call("GET", "/api/auth/openrouter/callback?state=nada&code=x")[0], 400)
        st, body = self.call("POST", "/api/auth/openrouter/start", {})
        state = urllib.parse.parse_qs(urllib.parse.urlsplit(urllib.parse.parse_qs(urllib.parse.urlsplit(json.loads(body)["url"]).query)["callback_url"][0]).query)["state"][0]
        self.assertEqual(self.call("GET", f"/api/auth/openrouter/callback?state={state}")[0], 400)  # sem código
        self.assertFalse(self.store.get_settings()["providers"].get("openrouter", {}).get("api_key"))

    def test_login_is_only_for_the_computer_itself(self):
        class Fake:
            def is_remote(self, ip, headers):
                return True

            def allowed(self, *a):
                return True
        self.app.mobile = Fake()
        self.app.auth_routes.app = self.app
        self.assertEqual(self.call("POST", "/api/auth/openrouter/start", {})[0], 403)


if __name__ == "__main__":
    unittest.main()
