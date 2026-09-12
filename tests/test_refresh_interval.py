# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import json
import tempfile
import unittest

import fomo_pipeline
from fomo_pipeline import is_cache_fresh, load_settings, save_settings


def _cached(*, age_sec: int, rows=None, board: str = "all") -> dict:
    ts = (datetime.now(timezone.utc) - timedelta(seconds=age_sec)).isoformat()
    return {
        "generatedAt": ts,
        "marketCapUpdatedAt": ts,
        "board": board,
        "rows": rows if rows is not None else [{"名称": "AAA"}],
    }


class RefreshMinutesSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "fomo_settings.json"
        self.patcher = patch.object(fomo_pipeline, "SETTINGS_PATH", self.path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_default_refresh_minutes_is_10(self):
        self.assertEqual(load_settings()["refreshMinutes"], 10)

    def test_save_and_reload_refresh_minutes(self):
        save_settings(refresh_minutes=15)
        self.assertEqual(load_settings()["refreshMinutes"], 15)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["refreshMinutes"], 15)

    def test_refresh_minutes_clamped(self):
        self.assertEqual(save_settings(refresh_minutes=0)["refreshMinutes"], 1)
        self.assertEqual(save_settings(refresh_minutes=999)["refreshMinutes"], 180)
        self.assertEqual(save_settings(refresh_minutes="x")["refreshMinutes"], 10)


class RefreshUsesSettingsIntervalTests(unittest.TestCase):
    def setUp(self):
        import app

        with app._lock:
            app._job.update(
                {
                    "status": "idle",
                    "progress": "",
                    "result": None,
                    "error": None,
                    "mode": None,
                    "board": "all",
                }
            )

    def test_one_minute_setting_treats_90s_cache_as_stale(self):
        from fastapi.testclient import TestClient
        from app import app

        cached = _cached(age_sec=90, board="all")
        settings = {
            "allLimit": 20,
            "dayLimit": 50,
            "h24Limit": 50,
            "refreshMinutes": 1,
        }
        with patch("app.load_cached_result", return_value=cached), patch(
            "app.load_settings", return_value=settings
        ), patch("app.threading") as threading_mod:
            res = TestClient(app).post(
                "/api/fomo-top20/refresh",
                json={"mode": "fast", "board": "all", "force": False},
            )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("started"))
        threading_mod.Thread.assert_called_once()

    def test_ten_minute_setting_keeps_90s_cache_fresh(self):
        from fastapi.testclient import TestClient
        from app import app

        cached = _cached(age_sec=90, board="all")
        settings = {
            "allLimit": 20,
            "dayLimit": 50,
            "h24Limit": 50,
            "refreshMinutes": 10,
        }
        with patch("app.load_cached_result", return_value=cached), patch(
            "app.load_settings", return_value=settings
        ), patch("app.threading") as threading_mod:
            res = TestClient(app).post(
                "/api/fomo-top20/refresh",
                json={"mode": "fast", "board": "all", "force": False},
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("skipped"))
        self.assertEqual(body.get("reason"), "fresh")
        threading_mod.Thread.assert_not_called()


class RefreshMinutesUiTests(unittest.TestCase):
    def test_settings_page_has_refresh_interval_input(self):
        html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("自动刷新", html)
        self.assertIn("set-refresh-minutes", html)


if __name__ == "__main__":
    unittest.main()
