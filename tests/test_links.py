"""Links colados no Chat: texto da página, imagens e vídeos dentro dela (v0.14.1)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta import websearch as ws  # noqa: E402

PAGE = ('<html><head><title>Receita</title><meta property="og:image" content="/capa.jpg"><meta name="description" content="Um bolo simples."></head><body>'
        '<p>Misture todos os ingredientes com calma e leve ao forno por quarenta minutos.</p>'
        '<img src="/passo1.png" alt="Passo 1"><img src="tracking.gif" width="1" height="1"><img src="/icon.png">'
        '<video poster="/poster.jpg"><source src="/video.mp4"></video>'
        '<iframe src="https://www.youtube.com/embed/abc" title="Tutorial"></iframe></body></html>')


class Links(unittest.TestCase):
    def test_extract_urls(self):
        t = "veja https://a.com/x, e (https://b.org/y.png). de novo https://a.com/x"
        self.assertEqual(ws.extract_urls(t), ["https://a.com/x", "https://b.org/y.png"])
        self.assertEqual(ws.extract_urls("sem link"), [])

    def test_page_media(self):
        m = ws.page_media(PAGE, "https://site.com/receita")
        urls = [i["url"] for i in m["images"]]
        self.assertEqual(urls[0], "https://site.com/capa.jpg")
        self.assertIn("https://site.com/passo1.png", urls)
        self.assertIn("https://site.com/poster.jpg", urls)
        self.assertFalse(any("tracking" in u or "icon" in u for u in urls))
        vids = [v["url"] for v in m["videos"]]
        self.assertIn("https://site.com/video.mp4", vids)
        self.assertIn("https://www.youtube.com/embed/abc", vids)

    def test_links_context(self):
        class Resp:
            def __init__(self, body, ctype):
                self.body, self.headers = body, {"Content-Type": ctype}
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1): return self.body[:n] if n > 0 else self.body
            def geturl(self): return "https://site.com/receita"

        def fake(req, timeout=0):
            u = req.full_url
            if u.endswith(".jpg") or u.endswith(".png"):
                return Resp(b"\x89PNGdata", "image/png")
            return Resp(PAGE.encode(), "text/html; charset=utf-8")
        with mock.patch.object(ws, "safe_url", return_value=True), mock.patch.object(ws._OPENER, "open", side_effect=fake):
            got = ws.links_context(["https://site.com/receita"])
        self.assertIn("Misture todos", got["text"])
        self.assertIn("Vídeos da página", got["text"])
        self.assertIn("https://site.com/passo1.png", got["text"])
        self.assertTrue(got["images"])
        self.assertEqual(got["items"][0]["videos"], 2)

    def test_private_link_refused(self):
        r = ws.read_link("http://127.0.0.1:8080/x")
        self.assertTrue(r["error"])


if __name__ == "__main__":
    unittest.main()
