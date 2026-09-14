# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fomo_pipeline
from fomo_pipeline import load_settings, save_settings


class TokenFilterSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "fomo_settings.json"
        self.patcher = patch.object(fomo_pipeline, "SETTINGS_PATH", self.path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_default_filters_are_empty(self):
        s = load_settings()
        self.assertEqual(s["mcapMin"], "")
        self.assertEqual(s["daysMax"], "")

    def test_save_and_reload_filter_strings(self):
        save_settings(filters={"mcapMin": "500K", "daysMax": "30"})
        s = load_settings()
        self.assertEqual(s["mcapMin"], "500K")
        self.assertEqual(s["daysMax"], "30")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["mcapMin"], "500K")
        self.assertEqual(data["allLimit"], 20)

    def test_partial_save_keeps_other_filters(self):
        save_settings(filters={"mcapMin": "10M"})
        save_settings(filters={"holdMax": "1M"})
        s = load_settings()
        self.assertEqual(s["mcapMin"], "10M")
        self.assertEqual(s["holdMax"], "1M")

    def test_clear_filter_with_empty_string(self):
        save_settings(filters={"mcapMin": "10M"})
        save_settings(filters={"mcapMin": ""})
        self.assertEqual(load_settings()["mcapMin"], "")


class ChartHiddenSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "fomo_settings.json"
        self.patcher = patch.object(fomo_pipeline, "SETTINGS_PATH", self.path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_default_chart_hidden_is_empty(self):
        self.assertEqual(load_settings()["chartHidden"], [])

    def test_save_and_reload_chart_hidden(self):
        save_settings(chart_hidden=["holders", "pnl"])
        self.assertEqual(load_settings()["chartHidden"], ["holders", "pnl"])
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["chartHidden"], ["holders", "pnl"])

    def test_unknown_and_duplicate_chart_keys_are_dropped(self):
        save_settings(chart_hidden=["holders", "nope", "mcap", "holders"])
        self.assertEqual(load_settings()["chartHidden"], ["mcap", "holders"])

    def test_partial_filter_save_keeps_chart_hidden(self):
        save_settings(chart_hidden=["amount"])
        save_settings(filters={"mcapMin": "10M"})
        s = load_settings()
        self.assertEqual(s["chartHidden"], ["amount"])
        self.assertEqual(s["mcapMin"], "10M")

    def test_empty_list_clears_chart_hidden(self):
        save_settings(chart_hidden=["pnl"])
        save_settings(chart_hidden=[])
        self.assertEqual(load_settings()["chartHidden"], [])

    def test_omitted_chart_hidden_keeps_previous(self):
        save_settings(chart_hidden=["pnl"])
        save_settings(refresh_minutes=12)
        self.assertEqual(load_settings()["chartHidden"], ["pnl"])
        self.assertEqual(load_settings()["refreshMinutes"], 12)


class TokenFilterSettingsApiTests(unittest.TestCase):
    def test_post_filters_roundtrip(self):
        from fastapi.testclient import TestClient
        import app as appmod

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fomo_settings.json"
            with patch.object(fomo_pipeline, "SETTINGS_PATH", path), patch(
                "app.load_settings", fomo_pipeline.load_settings
            ), patch("app.save_settings", fomo_pipeline.save_settings):
                client = TestClient(appmod.app)
                res = client.post(
                    "/api/settings",
                    json={"mcapMin": "500K", "daysMax": "8.5"},
                )
                self.assertEqual(res.status_code, 200)
                body = res.json()
                self.assertTrue(body.get("ok"))
                self.assertEqual(body.get("mcapMin"), "500K")
                self.assertEqual(body.get("daysMax"), "8.5")
                got = client.get("/api/settings")
                self.assertEqual(got.json().get("mcapMin"), "500K")

    def test_post_chart_hidden_roundtrip(self):
        from fastapi.testclient import TestClient
        import app as appmod

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fomo_settings.json"
            with patch.object(fomo_pipeline, "SETTINGS_PATH", path), patch(
                "app.load_settings", fomo_pipeline.load_settings
            ), patch("app.save_settings", fomo_pipeline.save_settings):
                client = TestClient(appmod.app)
                res = client.post(
                    "/api/settings",
                    json={"chartHidden": ["holders", "bogus", "pnl"]},
                )
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json().get("chartHidden"), ["holders", "pnl"])
                got = client.get("/api/settings")
                self.assertEqual(got.json().get("chartHidden"), ["holders", "pnl"])
                client.post("/api/settings", json={"mcapMin": "2M"})
                self.assertEqual(client.get("/api/settings").json().get("chartHidden"), ["holders", "pnl"])


if __name__ == "__main__":
    unittest.main()
