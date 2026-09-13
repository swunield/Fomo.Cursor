# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest

from fomo_pipeline import CACHE_FRESH_SEC, is_cache_fresh, resolve_board


def _cached(*, age_sec: int, rows=None, board: str = "all") -> dict:
    ts = (datetime.now(timezone.utc) - timedelta(seconds=age_sec)).isoformat()
    return {
        "generatedAt": ts,
        "marketCapUpdatedAt": ts,
        "board": board,
        "rows": rows if rows is not None else [{"名称": "AAA"}],
    }


class CacheFreshnessTests(unittest.TestCase):
    def test_fresh_within_10_minutes(self):
        self.assertTrue(is_cache_fresh(_cached(age_sec=9 * 60)))

    def test_stale_after_10_minutes(self):
        self.assertFalse(is_cache_fresh(_cached(age_sec=CACHE_FRESH_SEC + 1)))

    def test_missing_or_empty_is_not_fresh(self):
        self.assertFalse(is_cache_fresh(None))
        self.assertFalse(is_cache_fresh(_cached(age_sec=30, rows=[])))


class RefreshSkipTests(unittest.TestCase):
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
    def test_desktop_switch_skips_pull_when_same_board_is_fresh(self):
        from fastapi.testclient import TestClient

        from app import app

        cached = _cached(age_sec=120, board="7d")
        with patch("app.load_cached_result", return_value=cached) as load_cached, patch(
            "app.threading"
        ) as threading_mod:
            res = TestClient(app).post(
                "/api/fomo-top20/refresh",
                json={"mode": "fast", "board": "7d", "limit": 50, "force": False},
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("ok"))
        self.assertFalse(body.get("started"))
        self.assertTrue(body.get("skipped"))
        self.assertEqual(body.get("reason"), "fresh")
        load_cached.assert_called()
        threading_mod.Thread.assert_not_called()

    def test_force_refresh_starts_even_when_cache_is_fresh(self):
        from fastapi.testclient import TestClient

        from app import app

        cached = _cached(age_sec=120, board="all")
        with patch("app.load_cached_result", return_value=cached), patch("app.threading") as threading_mod:
            res = TestClient(app).post(
                "/api/fomo-top20/refresh",
                json={"mode": "fast", "board": "all", "force": True},
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("started"))
        self.assertFalse(body.get("skipped"))
        threading_mod.Thread.assert_called_once()

    def test_stale_cache_starts_refresh(self):
        from fastapi.testclient import TestClient

        from app import app

        cached = _cached(age_sec=CACHE_FRESH_SEC + 30, board="24h")
        with patch("app.load_cached_result", return_value=cached), patch("app.threading") as threading_mod:
            res = TestClient(app).post(
                "/api/fomo-top20/refresh",
                json={"mode": "fast", "board": "24h", "force": False},
            )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("started"))
        threading_mod.Thread.assert_called_once()

    def test_summary_refresh_keeps_board_sum(self):
        from fastapi.testclient import TestClient

        from app import app

        cached = _cached(age_sec=120, board="all")
        with patch("app.load_cached_result", return_value=cached), patch("app.threading") as threading_mod:
            res = TestClient(app).post(
                "/api/fomo-top20/refresh",
                json={"mode": "fast", "board": "sum", "force": True},
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("started"))
        self.assertEqual(body.get("board"), "sum")
        threading_mod.Thread.assert_called_once()

    def test_summary_refresh_skips_only_when_all_three_fresh(self):
        from fastapi.testclient import TestClient

        from app import app

        def load_cached(board="all"):
            return _cached(age_sec=120, board=board)

        with patch("app.load_cached_result", side_effect=load_cached), patch(
            "app.threading"
        ) as threading_mod:
            res = TestClient(app).post(
                "/api/fomo-top20/refresh",
                json={"mode": "fast", "board": "sum", "force": False},
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("skipped"))
        self.assertEqual(body.get("board"), "sum")
        threading_mod.Thread.assert_not_called()

    def test_summary_refresh_starts_when_one_source_stale(self):
        from fastapi.testclient import TestClient

        from app import app

        def load_cached(board="all"):
            if board == "7d":
                return _cached(age_sec=CACHE_FRESH_SEC + 30, board="7d")
            return _cached(age_sec=120, board=board)

        with patch("app.load_cached_result", side_effect=load_cached), patch(
            "app.threading"
        ) as threading_mod:
            res = TestClient(app).post(
                "/api/fomo-top20/refresh",
                json={"mode": "fast", "board": "sum", "force": False},
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("started"))
        self.assertEqual(body.get("board"), "sum")
        threading_mod.Thread.assert_called_once()


class CachedPayloadTests(unittest.TestCase):
    def test_table_payload_omits_trader_dump(self):
        from app import _payload_from_cached

        body = _payload_from_cached(
            {
                "generatedAt": "2026-09-11T00:00:00+00:00",
                "board": "7d",
                "rows": [{"名称": "AAA"}],
                "traders": [{"handle": "x"}] * 50,
            }
        )
        self.assertEqual(body["rows"], [{"名称": "AAA"}])
        self.assertEqual(body.get("traders"), [])
        self.assertEqual(body.get("traderRanks"), [])

    def test_cached_payload_keeps_compact_trader_ranks(self):
        from app import _payload_from_cached

        body = _payload_from_cached(
            {
                "generatedAt": "2026-09-11T00:00:00+00:00",
                "board": "all",
                "rows": [{"名称": "AAA"}],
                "traders": [
                    {
                        "rank": 13,
                        "name": "point farm capital",
                        "handle": "pointfarmcap",
                        "uid": "secret-uid",
                        "pnl": 123,
                    }
                ],
            }
        )
        self.assertEqual(body.get("traders"), [])
        self.assertEqual(
            body.get("traderRanks"),
            [{"rank": 13, "name": "point farm capital", "handle": "pointfarmcap"}],
        )


class BoardDisplayLabelTests(unittest.TestCase):
    def test_24h_board_is_labeled_1d(self):
        cfg = resolve_board("24h", limit=50)
        self.assertEqual(cfg["shortLabel"], "1日榜")
        self.assertEqual(cfg["label"], "1日榜前50")


if __name__ == "__main__":
    unittest.main()
