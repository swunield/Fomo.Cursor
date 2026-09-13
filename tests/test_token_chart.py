# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fomo_auth import parse_balance_item
from fomo_token_chart import (
    build_series,
    circulating_supply,
    empty_cache,
    iter_trade_events,
    load_token_trades,
    merge_fetched_trade,
    plan_trade_fetches,
    save_token_trades,
    should_skip_trade,
)
from update_token_marketcap import CSV_COLUMNS


TOKEN = "So1AAA"
USER = "u1"
WALLET = "Wallet1"


def _traders(swaps=None, transfers=None, user_address=WALLET):
    return {
        USER: {
            "userId": USER,
            "handle": "alice",
            "displayName": "Alice",
            "trades": {
                "t1": {
                    "id": "t1",
                    "updatedAt": "2026-09-13T00:00:00Z",
                    "closedAt": None,
                    "userAddress": user_address,
                    "swaps": swaps or [],
                    "transfers": transfers or [],
                }
            },
        }
    }


class CirculatingSupplyTests(unittest.TestCase):
    def test_divides_mcap_by_price(self):
        self.assertEqual(circulating_supply(1000.0, 0.5), 2000.0)

    def test_zero_price_is_zero(self):
        self.assertEqual(circulating_supply(1000.0, 0.0), 0.0)


class IterTradeEventsTests(unittest.TestCase):
    def test_buy_swap_positive_qty(self):
        events = iter_trade_events(
            TOKEN,
            USER,
            WALLET,
            {
                "swaps": [
                    {
                        "id": "s1",
                        "createdAt": "2026-09-11T11:00:00Z",
                        "outTokenAddress": TOKEN,
                        "outHumanAmount": 100,
                        "inTokenAddress": "USDC",
                        "inHumanAmount": 50,
                        "humanUsdAmountIn": 50,
                        "humanUsdAmountOut": 50,
                    }
                ],
                "transfers": [],
            },
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["qty"], 100)
        self.assertEqual(events[0]["usd"], 50)
        self.assertEqual(events[0]["price"], 0.5)

    def test_sell_swap_negative_qty(self):
        events = iter_trade_events(
            TOKEN,
            USER,
            WALLET,
            {
                "swaps": [
                    {
                        "id": "s2",
                        "createdAt": "2026-09-11T12:00:00Z",
                        "inTokenAddress": TOKEN,
                        "inHumanAmount": 40,
                        "outTokenAddress": "USDC",
                        "outHumanAmount": 30,
                        "humanUsdAmountIn": 30,
                        "humanUsdAmountOut": 30,
                    }
                ],
                "transfers": [],
            },
        )
        self.assertEqual(events[0]["qty"], -40)
        self.assertEqual(events[0]["usd"], 30)

    def test_transfer_direction_by_address(self):
        events = iter_trade_events(
            TOKEN,
            USER,
            WALLET,
            {
                "swaps": [],
                "transfers": [
                    {
                        "id": "tr1",
                        "createdAt": "2026-09-11T13:00:00Z",
                        "tokenAddress": TOKEN,
                        "toAddress": WALLET,
                        "fromAddress": "Other",
                        "humanAmount": 10,
                        "usdAmount": 4,
                    }
                ],
            },
        )
        self.assertEqual(events[0]["qty"], 10)
        self.assertEqual(events[0]["usd"], 4)


class BuildSeriesTests(unittest.TestCase):
    def test_buy_then_sell_updates_holders_amount_pnl(self):
        traders = _traders(
            swaps=[
                {
                    "id": "s1",
                    "createdAt": "2026-09-11T11:00:00Z",
                    "outTokenAddress": TOKEN,
                    "outHumanAmount": 100,
                    "inTokenAddress": "USDC",
                    "humanUsdAmountIn": 50,
                    "humanUsdAmountOut": 50,
                },
                {
                    "id": "s2",
                    "createdAt": "2026-09-11T12:00:00Z",
                    "inTokenAddress": TOKEN,
                    "inHumanAmount": 100,
                    "outTokenAddress": "USDC",
                    "humanUsdAmountIn": 80,
                    "humanUsdAmountOut": 80,
                },
            ]
        )
        series = build_series(TOKEN, circulating_supply=1000.0, traders=traders)
        self.assertEqual(len(series), 2)
        first, last = series[0], series[1]
        self.assertEqual(first["holders"], 1)
        self.assertEqual(first["amount"], 100)
        self.assertEqual(first["holdMcap"], 50)  # 100 * 0.5
        self.assertEqual(first["mcap"], 500)  # 0.5 * 1000
        self.assertEqual(last["holders"], 0)
        self.assertEqual(last["amount"], 0)
        self.assertEqual(last["pnl"], 30)  # sold 80 vs cost 50

    def test_same_timestamp_keeps_last_snapshot(self):
        traders = _traders(
            swaps=[
                {
                    "id": "s1",
                    "createdAt": "2026-09-11T11:00:00.000Z",
                    "outTokenAddress": TOKEN,
                    "outHumanAmount": 10,
                    "humanUsdAmountIn": 10,
                    "humanUsdAmountOut": 10,
                },
                {
                    "id": "s2",
                    "createdAt": "2026-09-11T11:00:00.000Z",
                    "outTokenAddress": TOKEN,
                    "outHumanAmount": 5,
                    "humanUsdAmountIn": 5,
                    "humanUsdAmountOut": 5,
                },
            ]
        )
        series = build_series(TOKEN, 100.0, traders)
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0]["amount"], 15)

    def test_emptied_trader_still_affects_history(self):
        traders = _traders(
            swaps=[
                {
                    "id": "s1",
                    "createdAt": "2026-09-11T11:00:00Z",
                    "outTokenAddress": TOKEN,
                    "outHumanAmount": 10,
                    "humanUsdAmountIn": 10,
                    "humanUsdAmountOut": 10,
                },
                {
                    "id": "s2",
                    "createdAt": "2026-09-11T12:00:00Z",
                    "inTokenAddress": TOKEN,
                    "inHumanAmount": 10,
                    "humanUsdAmountIn": 10,
                    "humanUsdAmountOut": 10,
                },
            ]
        )
        series = build_series(TOKEN, 100.0, traders)
        self.assertEqual(series[0]["holders"], 1)
        self.assertEqual(series[1]["holders"], 0)


class SkipTradeTests(unittest.TestCase):
    def test_skip_when_closed(self):
        self.assertTrue(
            should_skip_trade({"closedAt": "2026-09-01T00:00:00Z", "updatedAt": "a"}, "b")
        )

    def test_skip_when_updated_at_matches(self):
        ts = "2026-09-13T00:00:00Z"
        self.assertTrue(should_skip_trade({"closedAt": None, "updatedAt": ts}, ts))

    def test_fetch_when_updated_at_changes(self):
        self.assertFalse(
            should_skip_trade(
                {"closedAt": None, "updatedAt": "2026-09-13T00:00:00Z"},
                "2026-09-13T01:00:00Z",
            )
        )

    def test_fetch_when_missing_cache(self):
        self.assertFalse(should_skip_trade(None, "2026-09-13T00:00:00Z"))


class PlanFetchesTests(unittest.TestCase):
    def test_unions_current_holders_and_cached_closed_trades(self):
        cache = empty_cache(TOKEN)
        cache["traders"][USER] = {
            "userId": USER,
            "handle": "alice",
            "displayName": "Alice",
            "trades": {
                "old": {
                    "id": "old",
                    "updatedAt": "2026-09-01T00:00:00Z",
                    "closedAt": "2026-09-02T00:00:00Z",
                    "swaps": [],
                    "transfers": [],
                }
            },
        }
        holders = [
            {
                "uid": "u2",
                "handle": "bob",
                "name": "Bob",
                "tradeId": "new",
                "tradeUpdatedAt": "2026-09-13T00:00:00Z",
            }
        ]
        planned = plan_trade_fetches(cache, holders)
        ids = {p["tradeId"] for p in planned}
        self.assertIn("new", ids)
        self.assertNotIn("old", ids)  # closedAt 已有则跳过

    def test_skips_holder_without_trade_id(self):
        cache = empty_cache(TOKEN)
        planned = plan_trade_fetches(
            cache, [{"uid": "u9", "handle": "x", "name": "X", "tradeId": ""}]
        )
        self.assertEqual(planned, [])


class MergeAndDiskTests(unittest.TestCase):
    def test_keeps_emptied_trader_and_merges_swaps_by_id(self):
        cache = empty_cache(TOKEN)
        holder = {"uid": USER, "handle": "alice", "name": "Alice", "tradeId": "t1"}
        merge_fetched_trade(
            cache,
            holder,
            {
                "userId": USER,
                "userHandle": "alice",
                "displayName": "Alice",
                "trade": {
                    "id": "t1",
                    "updatedAt": "2026-09-13T01:00:00Z",
                    "closedAt": "2026-09-13T02:00:00Z",
                    "userAddress": WALLET,
                },
                "swaps": [{"id": "s1", "createdAt": "2026-09-11T11:00:00Z"}],
                "transfers": [],
            },
        )
        merge_fetched_trade(
            cache,
            holder,
            {
                "userId": USER,
                "trade": {
                    "id": "t1",
                    "updatedAt": "2026-09-13T03:00:00Z",
                    "closedAt": "2026-09-13T02:00:00Z",
                    "userAddress": WALLET,
                },
                "swaps": [
                    {"id": "s1", "createdAt": "2026-09-11T11:00:00Z"},
                    {"id": "s2", "createdAt": "2026-09-11T12:00:00Z"},
                ],
                "transfers": [],
            },
        )
        swaps = cache["traders"][USER]["trades"]["t1"]["swaps"]
        self.assertEqual({s["id"] for s in swaps}, {"s1", "s2"})
        self.assertIsNotNone(cache["traders"][USER]["trades"]["t1"]["closedAt"])

    def test_roundtrip_missing_file_is_empty_series(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            loaded = load_token_trades(TOKEN, root=root)
            self.assertEqual(loaded["series"], [])
            self.assertIsNone(loaded["lastFetchedAt"])
            loaded["series"] = [
                {"t": "x", "mcap": 1, "holders": 1, "amount": 1, "holdMcap": 1, "pnl": 0}
            ]
            save_token_trades(TOKEN, loaded, root=root)
            again = load_token_trades(TOKEN, root=root)
            self.assertEqual(len(again["series"]), 1)


class ParseBalanceTradeIdTests(unittest.TestCase):
    def test_open_position_keeps_trade_id(self):
        item = {
            "balance": {"tokenAddress": "So1AAA", "shiftedBalance": 10},
            "tokenFilterResult": {"priceUSD": "2", "marketCap": "100", "token": {"symbol": "AAA", "address": "So1AAA"}},
            "userToken": {"averageEntryPriceUsd": 1, "currentCostBasisUsd": 10},
            "activeTrade": {"id": "trade-1", "closedAt": None},
        }
        parsed = parse_balance_item(item)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["tradeId"], "trade-1")

    def test_closed_position_still_none(self):
        item = {
            "balance": {"tokenAddress": "So1AAA", "shiftedBalance": 10},
            "tokenFilterResult": {"priceUSD": "2", "marketCap": "100", "token": {"symbol": "AAA"}},
            "activeTrade": {"id": "trade-1", "closedAt": "2026-09-01T00:00:00Z"},
        }
        self.assertIsNone(parse_balance_item(item))


class AggregateRowsHoldersTests(unittest.TestCase):
    def test_row_holders_keep_trade_id_and_csv_columns_unchanged(self):
        from fomo_pipeline import aggregate_rows

        token_map = {
            "So1AAA": [
                {
                    "rank": 9,
                    "name": "ogle",
                    "handle": "ogle",
                    "uid": "u1",
                    "tradeId": "trade-1",
                    "amount": 10.0,
                    "value": 20.0,
                    "tokenAddress": "So1AAA",
                    "symbol": "AAA",
                    "rawName": "AAA Token",
                    "marketCap": 100.0,
                    "volume24": 0,
                    "change24": None,
                    "positionUpdatedAt": "2026-09-13T00:00:00Z",
                    "pnlUsd": 10.0,
                }
            ]
        }
        rows = aggregate_rows(token_map, {}, {})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["合约地址"], "So1AAA")
        self.assertEqual(rows[0]["holders"][0]["tradeId"], "trade-1")
        self.assertEqual(rows[0]["holders"][0]["uid"], "u1")
        self.assertEqual(rows[0]["holders"][0]["amount"], 10.0)
        self.assertEqual(rows[0]["holders"][0]["tradeUpdatedAt"], "2026-09-13T00:00:00Z")
        self.assertNotIn("holders", CSV_COLUMNS)
        self.assertIn("合约地址", CSV_COLUMNS)


class FetchTradeTests(unittest.TestCase):
    def test_empty_id_raises(self):
        from fomo_auth import fetch_trade

        with self.assertRaises(RuntimeError):
            fetch_trade("")

    def test_returns_response_object(self):
        from unittest.mock import patch

        from fomo_auth import fetch_trade

        payload = {
            "success": True,
            "responseObject": {
                "trade": {"id": "trade-1"},
                "swaps": [],
                "transfers": [],
            },
        }
        with patch("fomo_auth.fomo_get", return_value=payload) as mock_get:
            obj = fetch_trade("trade-1")
        mock_get.assert_called_once_with("/trades/trade-1", token=None)
        self.assertEqual(obj["trade"]["id"], "trade-1")

    def test_error_status_raises(self):
        from unittest.mock import patch

        from fomo_auth import fetch_trade

        with patch(
            "fomo_auth.fomo_get",
            return_value={"error": "denied", "statusCode": 401},
        ):
            with self.assertRaises(RuntimeError):
                fetch_trade("trade-1")


class RefreshOrchestrationTests(unittest.TestCase):
    def test_fetch_fn_called_only_for_open_changed_trades(self):
        from fomo_token_chart import empty_cache, merge_fetched_trade, refresh_token_chart

        addr = TOKEN
        cache = empty_cache(addr)
        merge_fetched_trade(
            cache,
            {"uid": USER, "handle": "alice", "name": "Alice", "tradeId": "old"},
            {
                "userId": USER,
                "trade": {
                    "id": "old",
                    "updatedAt": "2026-09-01T00:00:00Z",
                    "closedAt": "2026-09-02T00:00:00Z",
                    "userAddress": WALLET,
                },
                "swaps": [],
                "transfers": [],
            },
        )
        calls = []

        def fetch_fn(trade_id):
            calls.append(trade_id)
            return {
                "userId": "u2",
                "userHandle": "bob",
                "displayName": "Bob",
                "trade": {
                    "id": trade_id,
                    "updatedAt": "2026-09-13T00:00:00Z",
                    "closedAt": None,
                    "userAddress": "Wallet2",
                },
                "swaps": [
                    {
                        "id": "s1",
                        "createdAt": "2026-09-11T11:00:00Z",
                        "outTokenAddress": addr,
                        "outHumanAmount": 10,
                        "humanUsdAmountIn": 10,
                        "humanUsdAmountOut": 10,
                    }
                ],
                "transfers": [],
            }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_token_trades(addr, cache, root=root)
            out = refresh_token_chart(
                addr,
                [
                    {
                        "uid": "u2",
                        "handle": "bob",
                        "name": "Bob",
                        "tradeId": "new",
                        "tradeUpdatedAt": "2026-09-13T00:00:00Z",
                    }
                ],
                fetch_fn=fetch_fn,
                root=root,
                circulating=100.0,
            )
        self.assertEqual(calls, ["new"])
        self.assertTrue(out["traders"][USER]["trades"]["old"]["closedAt"])
        self.assertIn("new", out["traders"]["u2"]["trades"])
        self.assertGreaterEqual(len(out["series"]), 1)
        self.assertEqual(out["stats"]["fetched"], 1)

    def test_refresh_keys_trader_from_planned_user_id_when_payload_lacks_user_id(self):
        from fomo_token_chart import refresh_token_chart

        def fetch_fn(trade_id):
            return {
                "trade": {
                    "id": trade_id,
                    "updatedAt": "2026-09-13T00:00:00Z",
                    "closedAt": None,
                    "userAddress": WALLET,
                },
                "swaps": [],
                "transfers": [],
            }

        with TemporaryDirectory() as tmp:
            out = refresh_token_chart(
                TOKEN,
                [
                    {
                        "uid": USER,
                        "handle": "alice",
                        "name": "Alice",
                        "tradeId": "t-open",
                        "tradeUpdatedAt": "2026-09-13T00:00:00Z",
                    }
                ],
                fetch_fn=fetch_fn,
                root=Path(tmp),
                circulating=100.0,
            )
        self.assertIn(USER, out["traders"])
        self.assertNotIn("", out["traders"])
        self.assertIn("t-open", out["traders"][USER]["trades"])
        self.assertEqual(out["traders"][USER]["handle"], "alice")
        self.assertEqual(out["traders"][USER]["displayName"], "Alice")

    def test_matching_trade_updated_at_skips_fetch(self):
        from fomo_token_chart import refresh_token_chart

        ts = "2026-09-13T00:00:00Z"
        cache = empty_cache(TOKEN)
        merge_fetched_trade(
            cache,
            {"uid": USER, "handle": "alice", "name": "Alice", "tradeId": "t1"},
            {
                "userId": USER,
                "trade": {
                    "id": "t1",
                    "updatedAt": ts,
                    "closedAt": None,
                    "userAddress": WALLET,
                },
                "swaps": [],
                "transfers": [],
            },
        )
        calls = []

        def fetch_fn(trade_id):
            calls.append(trade_id)
            raise AssertionError("fetch_fn should not be called")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_token_trades(TOKEN, cache, root=root)
            refresh_token_chart(
                TOKEN,
                [
                    {
                        "uid": USER,
                        "handle": "alice",
                        "name": "Alice",
                        "tradeId": "t1",
                        "tradeUpdatedAt": ts,
                    }
                ],
                fetch_fn=fetch_fn,
                root=root,
                circulating=100.0,
            )
        self.assertEqual(calls, [])

    def test_all_fetches_fail_does_not_set_last_fetched_at(self):
        from fomo_token_chart import refresh_token_chart

        def fetch_fn(trade_id):
            raise RuntimeError("boom")

        with TemporaryDirectory() as tmp:
            out = refresh_token_chart(
                TOKEN,
                [
                    {
                        "uid": USER,
                        "handle": "alice",
                        "name": "Alice",
                        "tradeId": "t-fail",
                    }
                ],
                fetch_fn=fetch_fn,
                root=Path(tmp),
                circulating=100.0,
            )
        self.assertIsNone(out["lastFetchedAt"])
        self.assertEqual(out["stats"]["fetched"], 0)
        self.assertGreater(out["stats"]["failed"], 0)


class TokenChartApiTests(unittest.TestCase):
    def setUp(self):
        import app as appmod

        lock = getattr(appmod, "_chart_lock", None)
        jobs = getattr(appmod, "_chart_jobs", None)
        if lock is not None and jobs is not None:
            with lock:
                jobs.clear()

    def test_get_missing_returns_empty_series(self):
        from fastapi.testclient import TestClient
        import app as appmod

        with TemporaryDirectory() as tmp:
            with patch("fomo_token_chart.TRADES_DIR", Path(tmp) / "fomo_token_trades"):
                client = TestClient(appmod.app)
                res = client.get("/api/fomo-top20/token-chart", params={"addr": "SoNoSuch"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["series"], [])
        self.assertIsNone(body["lastFetchedAt"])
        self.assertFalse(body["running"])

    def test_unauthenticated_post_returns_401(self):
        import app as appmod
        from fastapi.testclient import TestClient

        client = TestClient(appmod.app)
        with patch("app.get_access_token", return_value=None):
            res = client.post(
                "/api/fomo-top20/token-chart/refresh",
                json={"addr": "SoLock", "holders": [{"uid": "u", "tradeId": "t"}]},
            )
        self.assertEqual(res.status_code, 401)

    def test_empty_addr_returns_400_chinese(self):
        import app as appmod
        from fastapi.testclient import TestClient

        client = TestClient(appmod.app)
        with patch("app.get_access_token", return_value="tok"):
            res = client.post(
                "/api/fomo-top20/token-chart/refresh",
                json={"addr": "", "holders": []},
            )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "缺少合约地址")

    def test_second_post_while_running_returns_running(self):
        import app as appmod
        from fastapi.testclient import TestClient

        client = TestClient(appmod.app)
        entered = threading.Event()
        hold = threading.Event()

        def fake_refresh(*args, **kwargs):
            entered.set()
            hold.wait(timeout=5)
            return empty_cache("x")

        with patch("app.get_access_token", return_value="tok"), patch(
            "app.refresh_token_chart", side_effect=fake_refresh
        ):
            r1 = client.post(
                "/api/fomo-top20/token-chart/refresh",
                json={"addr": "SoLock", "holders": [{"uid": "u", "tradeId": "t"}]},
            )
            self.assertTrue(entered.wait(timeout=2), "refresh thread did not start")
            r2 = client.post(
                "/api/fomo-top20/token-chart/refresh",
                json={"addr": "SoLock", "holders": [{"uid": "u", "tradeId": "t"}]},
            )
            hold.set()
        self.assertTrue(r1.json().get("started") or r1.json().get("running"))
        self.assertTrue(r2.json().get("running"))
        self.assertFalse(r2.json().get("ok", True) and r2.json().get("started"))

    def test_failed_refresh_get_surfaces_error_without_last_fetched(self):
        from fastapi.testclient import TestClient
        from fomo_token_chart import refresh_token_chart
        import app as appmod

        def fetch_fn(trade_id):
            raise RuntimeError("boom")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            trades_dir = root / "fomo_token_trades"
            refresh_token_chart(
                TOKEN,
                [{"uid": USER, "handle": "alice", "name": "Alice", "tradeId": "t-fail"}],
                fetch_fn=fetch_fn,
                root=root,
                circulating=100.0,
            )
            with patch("fomo_token_chart.TRADES_DIR", trades_dir):
                client = TestClient(appmod.app)
                res = client.get(
                    "/api/fomo-top20/token-chart", params={"addr": TOKEN}
                )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsNone(body["lastFetchedAt"])
        self.assertIn("笔交易拉取失败", body.get("error") or "")

    def test_get_traversal_addr_returns_400_chinese(self):
        from fastapi.testclient import TestClient
        import app as appmod

        client = TestClient(appmod.app)
        res = client.get(
            "/api/fomo-top20/token-chart", params={"addr": "../secret"}
        )
        self.assertEqual(res.status_code, 400)
        detail = res.json().get("detail") or ""
        self.assertTrue(any("\u4e00" <= ch <= "\u9fff" for ch in detail), detail)

    def test_post_traversal_addr_returns_400_chinese(self):
        from fastapi.testclient import TestClient
        import app as appmod

        client = TestClient(appmod.app)
        with patch("app.get_access_token", return_value="tok"):
            res = client.post(
                "/api/fomo-top20/token-chart/refresh",
                json={"addr": "../secret", "holders": []},
            )
        self.assertEqual(res.status_code, 400)
        detail = res.json().get("detail") or ""
        self.assertTrue(any("\u4e00" <= ch <= "\u9fff" for ch in detail), detail)


class TradesPathSafetyTests(unittest.TestCase):
    def test_dotdot_addr_does_not_write_outside_temp_root(self):
        from fomo_token_chart import save_token_trades

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                save_token_trades("../secret", {"series": []}, root=root)
            self.assertFalse((root / "secret.json").exists())
            self.assertFalse(any(root.rglob("secret.json")))
            self.assertFalse((root.parent / "secret.json").exists())


if __name__ == "__main__":
    unittest.main()
