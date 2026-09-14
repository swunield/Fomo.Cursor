# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class FavoriteStoreTests(unittest.TestCase):
    def test_toggle_adds_then_removes_normalized_addr(self):
        from fomo_favorites import toggle_favorite

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "fomo_favorites.json"
            with patch("fomo_favorites.FAVORITES_PATH", path):
                addr, on, addrs = toggle_favorite("SoABC")
                self.assertEqual(addr, "soabc")
                self.assertTrue(on)
                self.assertEqual(addrs, ["soabc"])
                addr, on, addrs = toggle_favorite("SOABC")
                self.assertEqual(addr, "soabc")
                self.assertFalse(on)
                self.assertEqual(addrs, [])

    def test_empty_addr_raises_chinese(self):
        from fomo_favorites import normalize_favorite_addr

        with self.assertRaises(ValueError) as ctx:
            normalize_favorite_addr("")
        self.assertIn("缺少", str(ctx.exception))

    def test_traversal_addr_raises_chinese(self):
        from fomo_favorites import normalize_favorite_addr

        with self.assertRaises(ValueError) as ctx:
            normalize_favorite_addr("../secret")
        self.assertIn("非法", str(ctx.exception))


class FavoriteApiTests(unittest.TestCase):
    def test_get_empty_and_toggle_roundtrip(self):
        from fastapi.testclient import TestClient
        import app as appmod

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "fomo_favorites.json"
            with patch("fomo_favorites.FAVORITES_PATH", path):
                client = TestClient(appmod.app)
                empty = client.get("/api/favorites")
                self.assertEqual(empty.status_code, 200)
                self.assertEqual(empty.json().get("addrs"), [])
                added = client.post("/api/favorites/toggle", json={"addr": "SoFav"})
                self.assertEqual(added.status_code, 200)
                body = added.json()
                self.assertTrue(body.get("favorited"))
                self.assertEqual(body.get("addrs"), ["sofav"])
                listed = client.get("/api/favorites")
                self.assertEqual(listed.json().get("addrs"), ["sofav"])

    def test_empty_toggle_returns_400_chinese(self):
        from fastapi.testclient import TestClient
        import app as appmod

        client = TestClient(appmod.app)
        res = client.post("/api/favorites/toggle", json={"addr": ""})
        self.assertEqual(res.status_code, 400)
        self.assertIn("缺少", res.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main()
