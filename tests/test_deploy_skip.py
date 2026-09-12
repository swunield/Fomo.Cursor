# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_push():
    spec = importlib.util.spec_from_file_location(
        "deploy_push", ROOT / "deploy" / "push.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DeploySkipLocalDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.push = _load_push()

    def test_skips_token_and_oauth(self):
        for name in ("fomo_auth.json", "fomo_oauth_pending.json", "Server.conf"):
            self.assertTrue(self.push.should_skip(ROOT / name), name)

    def test_skips_caches_and_board_outputs(self):
        names = (
            "fomo_token_meta_cache.json",
            "fomo_mcap_ath_cache.json",
            "fomo_mcap_live_cache.json",
            "fomo_settings.json",
            "fomo_top20_last_result.json",
            "fomo_7d50_last_result.json",
            "fomo_24h_last_result.json",
            "fomo_top20_holdings_by_token.json",
            "fomo_top20_holdings_by_token.csv",
            "fomo_top20_holdings_by_token.md",
            "fomo_7d50_holdings_by_token.json",
            "fomo_24h_holdings_by_token.csv",
        )
        for name in names:
            self.assertTrue(self.push.should_skip(ROOT / name), name)

    def test_still_uploads_app_code(self):
        keep = (
            ROOT / "app.py",
            ROOT / "fomo_pipeline.py",
            ROOT / "web" / "app.js",
            ROOT / "web" / "index.html",
            ROOT / "deploy" / "nginx-fomo.conf",
        )
        for path in keep:
            self.assertFalse(self.push.should_skip(path), path.name)


if __name__ == "__main__":
    unittest.main()
