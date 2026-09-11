# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class No985MonitorSourcesTests(unittest.TestCase):
    def test_runtime_sources_do_not_mention_985monitor(self):
        files = [
            ROOT / "fomo_pipeline.py",
            ROOT / "app.py",
            ROOT / "web" / "app.js",
            ROOT / "web" / "index.html",
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("985monitor", text, msg=str(path))
            self.assertNotIn("fomo-watch/profile", text, msg=str(path))


class FetchTradersFomoOnlyTests(unittest.TestCase):
    def test_uses_official_fomo_api(self):
        from fomo_pipeline import fetch_traders

        traders = [{"handle": "alice", "rank": 1, "source": "fomo-api"}]
        with patch("fomo_pipeline._traders_from_fomo_api", return_value=traders) as api:
            out = fetch_traders(board="all", limit=20)
        api.assert_called_once_with("all", 20)
        self.assertEqual(out, traders)

    def test_does_not_fallback_when_fomo_api_fails(self):
        import fomo_pipeline
        from fomo_pipeline import fetch_traders

        self.assertFalse(hasattr(fomo_pipeline, "_traders_from_985"))
        with patch(
            "fomo_pipeline._traders_from_fomo_api",
            side_effect=RuntimeError("未配置 Privy Token，无法调用官方榜单"),
        ):
            with self.assertRaises(RuntimeError):
                fetch_traders(board="7d", limit=50)


class CollectHoldingsFomoOnlyTests(unittest.TestCase):
    def test_requires_fomo_token(self):
        from fomo_pipeline import collect_open_holdings

        with patch("fomo_auth.get_access_token", return_value=""):
            with self.assertRaises(RuntimeError) as ctx:
                collect_open_holdings(
                    [{"handle": "alice", "rank": 1, "name": "Alice", "uid": ""}]
                )
        msg = str(ctx.exception)
        self.assertTrue("Token" in msg or "登录" in msg)


if __name__ == "__main__":
    unittest.main()
