"""Memória unificada e perfil: os dois endpoints que devolviam erro 500 (a memória não aceitava o
carimbo de tempo e a exportação do perfil pedia cabeçalhos que o servidor não sabia mandar).

Regressões: `POST /api/memory/item` e `GET /api/profile/export` têm de responder 200/201, nunca 500.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_server import ServerCase  # noqa: E402


class MemoryItemTests(ServerCase):
    def test_add_an_item_does_not_break(self):
        s, item = self.c.json("POST", "/api/memory/item", {"section": "teste", "action": "nota", "title": "Olá", "summary": " mundo"})
        self.assertEqual(s, 200, item)
        self.assertEqual(item["title"], "Olá")
        self.assertTrue(item.get("id"))

    def test_add_an_item_with_a_timestamp(self):
        s, item = self.c.json("POST", "/api/memory/item", {"section": "teste", "action": "nota", "title": "Com data", "ts": "2026-01-02T03:04:05+00:00"})
        self.assertEqual(s, 200, item)
        self.assertTrue(str(item.get("ts", "")).startswith("2026-01-02"))

    def test_the_item_shows_up_in_the_day(self):
        s, item = self.c.json("POST", "/api/memory/item", {"section": "teste", "action": "nota", "title": "Procurada"})
        self.assertEqual(s, 200)
        s, days = self.c.json("GET", "/api/memory/days")
        self.assertEqual(s, 200)
        self.assertTrue(any(d.get("count", 0) >= 1 for d in days), f"a nota não apareceu nos dias: {days}")


class ProfileExportTests(ServerCase):
    def test_export_does_not_break(self):
        status, headers, payload = self.c.req("GET", "/api/profile/export")
        self.assertEqual(status, 200, payload)
        obj = json.loads(payload)
        self.assertIn("profile", obj)
        self.assertIn("attachment", headers.get("Content-Disposition", "").lower())

    def test_the_export_has_no_secret(self):
        """As chaves de API e os tokens nunca vão no pacote exportado."""
        s, _ = self.c.json("PUT", "/api/settings", {"providers": {"openai": {"api_key": "sk-secreto-123"}},
                                                    "code": {"github": {"token": "ghp-secreto-456"}}})
        self.assertEqual(s, 200)
        status, _h, payload = self.c.req("GET", "/api/profile/export")
        self.assertEqual(status, 200)
        blob = payload.decode("utf-8")
        self.assertNotIn("sk-secreto-123", blob)
        self.assertNotIn("ghp-secreto-456", blob)


if __name__ == "__main__":
    unittest.main()
