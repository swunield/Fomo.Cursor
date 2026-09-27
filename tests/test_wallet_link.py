# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fomo_wallet_link import (
    amount_close,
    load_traders,
    match_balance,
    match_pool_trades,
    pick_fingerprints,
    resolve_all,
    resolve_holdings,
    resolve_holdings_all,
    resolve_trader,
    save_wallet_links,
    swap_fingerprint,
    token_owner_from_tx,
    wallet_public_view,
)

TOKEN = "J1yxV53EmVRmt9RUj6PPufMfdAYUbtgwXCuNYTBTsYzJ"
TOKEN2 = "DAemPFNc3RtibBDKkUA4eL2Ns11q9VRdbpptmqm8DGqN"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
POOL = "AQB9ihwudzy364jisT8jcCURSE8wCSYg7wu7gLZ6nGQn"
WALLET = "Beqv6dzTcjV2eodo8RRXCiCcnSYrS1vkQKhfqwHXqeit"
NOW = 1790476688.0  # just after 2026-09-27T02:36Z


def _swap(when: str, usd: float, out_human: float, token: str = TOKEN) -> dict:
    return {
        "createdAt": when,
        "networkId": 1399811149,
        "inTokenAddress": USDC,
        "outTokenAddress": token,
        "inHumanAmount": usd,
        "outHumanAmount": out_human,
        "humanUsdAmountIn": usd,
        "provider": "DFLOW",
    }


class FingerprintTests(unittest.TestCase):
    def test_buy_uses_non_quote_leg(self):
        finger = swap_fingerprint(_swap("2026-09-27T02:28:08.743Z", 4725.43, 9430091.56))
        self.assertEqual(finger["side"], "buy")
        self.assertEqual(finger["token"], TOKEN)
        self.assertEqual(finger["amount"], 9430091.56)
        self.assertEqual(finger["network"], "solana")

    def test_quote_to_quote_is_ignored(self):
        self.assertIsNone(
            swap_fingerprint(
                {
                    "createdAt": "2026-09-27T02:28:08Z",
                    "networkId": 1399811149,
                    "inTokenAddress": USDC,
                    "outTokenAddress": "So11111111111111111111111111111111111111112",
                    "inHumanAmount": 1,
                    "outHumanAmount": 0.1,
                    "humanUsdAmountIn": 1,
                }
            )
        )

    def test_pick_prefers_larger_recent_swap(self):
        swaps = [
            swap_fingerprint(_swap("2026-09-27T02:36:08.720Z", 14.85, 16689.76)),
            swap_fingerprint(_swap("2026-09-27T02:28:08.743Z", 4725.43, 9430091.56)),
        ]
        chosen = pick_fingerprints(swaps, NOW, limit=1)
        self.assertEqual(chosen[0]["amount"], 9430091.56)


class MatchTests(unittest.TestCase):
    def test_amount_tolerance_accepts_rounded_human_amount(self):
        self.assertTrue(amount_close(9430091.56, 9430091.557727))

    def test_match_pool_trade_by_time_and_token_amount(self):
        when = 1790476088.743
        rows = [
            {
                "attributes": {
                    "block_timestamp": "2026-09-27T02:28:02Z",
                    "kind": "buy",
                    "from_token_amount": "38.49812193",
                    "to_token_amount": "9430091.557727",
                    "tx_hash": "tx1",
                    "tx_from_address": WALLET,
                }
            },
            {
                "attributes": {
                    "block_timestamp": "2026-09-27T02:28:04Z",
                    "kind": "buy",
                    "from_token_amount": "36.94",
                    "to_token_amount": "6990685.11",
                    "tx_hash": "tx-other",
                    "tx_from_address": "OtherWallet",
                }
            },
        ]
        hit = match_pool_trades(rows, when=when, amount=9430091.56, side="buy", base_is_token=True)
        self.assertEqual(hit["tx"], "tx1")
        self.assertEqual(hit["txFrom"], WALLET)

    def test_owner_is_token_recipient_not_pool(self):
        tx = {
            "meta": {
                "preTokenBalances": [
                    {"accountIndex": 1, "mint": TOKEN, "owner": WALLET, "uiTokenAmount": {"uiAmount": 0}},
                    {"accountIndex": 2, "mint": TOKEN, "owner": POOL, "uiTokenAmount": {"uiAmount": 20000000}},
                ],
                "postTokenBalances": [
                    {"accountIndex": 1, "mint": TOKEN, "owner": WALLET, "uiTokenAmount": {"uiAmount": 9430091.557727}},
                    {"accountIndex": 2, "mint": TOKEN, "owner": POOL, "uiTokenAmount": {"uiAmount": 10569908.442273}},
                ],
            }
        }
        owner = token_owner_from_tx(tx, TOKEN, 9430091.56, "buy", POOL)
        self.assertEqual(owner, WALLET)


class FakeClient:
    def __init__(self) -> None:
        self.trade_calls = 0

    def pools(self, token: str, network: str) -> list[dict]:
        return [{"pool": POOL, "base": token, "quote": USDC, "volume": 1}]

    def trades(self, network: str, pool: str, threshold: float) -> list[dict]:
        self.trade_calls += 1
        return [
            {
                "attributes": {
                    "block_timestamp": "2026-09-27T02:28:02Z",
                    "kind": "buy",
                    "from_token_amount": "38.5",
                    "to_token_amount": "9430091.557727",
                    "tx_hash": "tx1",
                    "tx_from_address": "FeePayer",
                }
            }
        ]

    def transaction(self, signature: str) -> dict:
        return {
            "meta": {
                "preTokenBalances": [
                    {"accountIndex": 1, "mint": TOKEN, "owner": WALLET, "uiTokenAmount": {"uiAmount": 0}},
                ],
                "postTokenBalances": [
                    {"accountIndex": 1, "mint": TOKEN, "owner": WALLET, "uiTokenAmount": {"uiAmount": 9430091.557727}},
                ],
            }
        }


class ResolveTests(unittest.TestCase):
    def _write_trade(self, root: Path) -> None:
        trades = root / "fomo_token_trades"
        trades.mkdir()
        payload = {
            "traders": {
                "u1": {
                    "userId": "u1",
                    "handle": "pointfarmcap",
                    "displayName": "point farm capital",
                    "trades": {
                        "t1": {
                            "userAddress": "FgactYhd2nkUxWfBgY435reoWq2HYsw3AqyRnfaRDfbF",
                            "swaps": [
                                _swap("2026-09-27T02:36:08.720Z", 14.85, 16689.76),
                                _swap("2026-09-27T02:28:08.743Z", 4725.43, 9430091.56),
                            ],
                        }
                    },
                }
            }
        }
        (trades / "token.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_resolve_uses_token_owner(self):
        trader = load_traders_from_swaps()
        row = resolve_trader(trader, FakeClient(), now=NOW)
        self.assertEqual(row["status"], "matched")
        self.assertEqual(row["wallets"][0]["address"], WALLET)
        self.assertEqual(row["wallets"][0]["tx"], "tx1")
        self.assertIn("FgactYhd2nkUxWfBgY435reoWq2HYsw3AqyRnfaRDfbF", row["ledgerAddresses"])

    def test_resolve_all_skips_already_matched(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_trade(root)
            cache_path = root / "fomo_wallet_links.json"
            client = FakeClient()
            resolve_all(root=root, path=cache_path, client=client, now=NOW)
            calls = client.trade_calls
            resolve_all(root=root, path=cache_path, client=client, now=NOW)
            self.assertEqual(client.trade_calls, calls)
            saved = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["traders"]["u1"]["wallets"][0]["address"], WALLET)

    def test_public_view_counts(self):
        body = wallet_public_view(
            {
                "updatedAt": "t",
                "finishedAt": "t",
                "traders": {"u": {"userId": "u", "handle": "h", "status": "matched", "wallets": [{"address": "A"}]}},
            }
        )
        self.assertEqual(body["stats"]["matched"], 1)
        self.assertEqual(body["traders"][0]["wallets"][0]["address"], "A")


def load_traders_from_swaps() -> dict:
    swaps = [
        swap_fingerprint(_swap("2026-09-27T02:36:08.720Z", 14.85, 16689.76)),
        swap_fingerprint(_swap("2026-09-27T02:28:08.743Z", 4725.43, 9430091.56)),
    ]
    return {
        "userId": "u1",
        "handle": "pointfarmcap",
        "displayName": "point farm capital",
        "ledgerAddresses": {"FgactYhd2nkUxWfBgY435reoWq2HYsw3AqyRnfaRDfbF"},
        "swaps": swaps,
    }


def _pos(token: str, amount: float, swap_amount: float | None = None) -> dict:
    return {
        "token": token,
        "networkId": 1399811149,
        "network": "solana",
        "amount": amount,
        "swapAmount": amount if swap_amount is None else swap_amount,
    }


class HoldingClient:
    def __init__(self, books: dict[str, list[dict]]) -> None:
        self.books = books
        self.calls: list[str] = []

    def largest_holders(self, mint: str) -> list[dict]:
        self.calls.append(mint)
        return self.books.get(mint, [])


class HoldingTests(unittest.TestCase):
    def test_unique_balance_picks_owner(self):
        hit, reason = match_balance(
            [
                {"owner": "PoolVault", "amount": 50000000},
                {"owner": WALLET, "amount": 9549554.1},
                {"owner": "Other", "amount": 1000000},
            ],
            9549554.09,
        )
        self.assertEqual(reason, "")
        self.assertEqual(hit["owner"], WALLET)

    def test_near_tie_is_ambiguous(self):
        hit, reason = match_balance(
            [{"owner": "A", "amount": 1000}, {"owner": "B", "amount": 1004}],
            1002,
        )
        self.assertIsNone(hit)
        self.assertEqual(reason, "ambiguous_balance")

    def test_loose_single_token_is_not_enough(self):
        client = HoldingClient({TOKEN: [{"owner": WALLET, "amount": 10150}, {"owner": "Other", "amount": 500}]})
        wallet, reason = resolve_holdings(
            {"positions": [_pos(TOKEN, 10000)]},
            client,
        )
        self.assertIsNone(wallet)
        self.assertEqual(reason, "no_balance_match")

    def test_same_owner_on_two_tokens_accepts_loose_band(self):
        client = HoldingClient(
            {
                TOKEN: [{"owner": WALLET, "amount": 10150}, {"owner": "Other", "amount": 400}],
                TOKEN2: [{"owner": WALLET, "amount": 20300}, {"owner": "Other", "amount": 800}],
            }
        )
        wallet, reason = resolve_holdings(
            {"positions": [_pos(TOKEN, 10000), _pos(TOKEN2, 20000)]},
            client,
        )
        self.assertEqual(reason, "")
        self.assertEqual(wallet["address"], WALLET)
        self.assertEqual(wallet["method"], "holding")
        self.assertEqual(wallet["matchedTokens"], 2)

    def test_two_tokens_two_owners_conflict(self):
        client = HoldingClient(
            {
                TOKEN: [{"owner": WALLET, "amount": 10000}],
                TOKEN2: [{"owner": "OtherWallet", "amount": 20000}],
            }
        )
        wallet, reason = resolve_holdings(
            {"positions": [_pos(TOKEN, 10000), _pos(TOKEN2, 20000)]},
            client,
        )
        self.assertIsNone(wallet)
        self.assertEqual(reason, "ambiguous_balance")

    def test_swap_net_used_when_ledger_balance_differs(self):
        client = HoldingClient(
            {
                TOKEN: [{"owner": WALLET, "amount": 8000}, {"owner": "Other", "amount": 100}],
                TOKEN2: [{"owner": WALLET, "amount": 4000}, {"owner": "Other", "amount": 50}],
            }
        )
        wallet, reason = resolve_holdings(
            {
                "positions": [
                    _pos(TOKEN, 15000, 8000),
                    _pos(TOKEN2, 9000, 4000),
                ]
            },
            client,
        )
        self.assertEqual(reason, "")
        self.assertEqual(wallet["address"], WALLET)
        self.assertEqual(wallet["matchedTokens"], 2)

    def test_resolve_trader_uses_holding_without_swaps(self):
        client = HoldingClient({TOKEN: [{"owner": WALLET, "amount": 9549554.1}, {"owner": "Other", "amount": 10}]})
        row = resolve_trader(
            {
                "userId": "u2",
                "handle": "holder",
                "displayName": "Holder",
                "ledgerAddresses": [],
                "swaps": [],
                "positions": [_pos(TOKEN, 9549554.09)],
            },
            client,
            now=NOW,
        )
        self.assertEqual(row["status"], "matched")
        self.assertEqual(row["wallets"][0]["method"], "holding")
        self.assertEqual(row["wallets"][0]["address"], WALLET)

    def test_load_traders_keeps_open_amount_and_token_case(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            trades = root / "fomo_token_trades"
            trades.mkdir()
            payload = {
                "traders": {
                    "u1": {
                        "userId": "u1",
                        "handle": "h",
                        "displayName": "n",
                        "trades": {
                            "t1": {
                                "userAddress": "Ledger",
                                "swaps": [
                                    _swap("2026-09-27T02:28:08.743Z", 100, 100),
                                    {
                                        "createdAt": "2026-09-27T02:30:08.743Z",
                                        "networkId": 1399811149,
                                        "inTokenAddress": TOKEN,
                                        "outTokenAddress": USDC,
                                        "inHumanAmount": 40,
                                        "outHumanAmount": 40,
                                        "humanUsdAmountIn": 40,
                                    },
                                ],
                                "transfers": [
                                    {
                                        "tokenAddress": TOKEN.lower(),
                                        "humanAmount": 10,
                                        "toAddress": "Ledger",
                                        "fromAddress": "Someone",
                                        "networkId": 1399811149,
                                    }
                                ],
                            }
                        },
                    }
                }
            }
            (trades / "token.json").write_text(json.dumps(payload), encoding="utf-8")
            rec = load_traders(root)["u1"]
            self.assertEqual(len(rec["positions"]), 1)
            self.assertEqual(rec["positions"][0]["token"], TOKEN)
            self.assertAlmostEqual(rec["positions"][0]["amount"], 70)
            self.assertAlmostEqual(rec["positions"][0]["swapAmount"], 60)

    def test_holdings_pass_skips_existing_solana_match(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            trades = root / "fomo_token_trades"
            trades.mkdir()
            payload = {
                "traders": {
                    "u1": {
                        "userId": "u1",
                        "handle": "pointfarmcap",
                        "displayName": "point farm capital",
                        "trades": {"t1": {"userAddress": "Ledger", "swaps": [_swap("2026-09-27T02:28:08.743Z", 10, 100)]}},
                    },
                    "u2": {
                        "userId": "u2",
                        "handle": "other",
                        "displayName": "Other",
                        "trades": {"t1": {"userAddress": "Ledger2", "swaps": [_swap("2026-09-27T02:28:08.743Z", 10, 100, TOKEN2)]}},
                    },
                }
            }
            (trades / "token.json").write_text(json.dumps(payload), encoding="utf-8")
            cache_path = root / "fomo_wallet_links.json"
            save_wallet_links(
                {
                    "traders": {
                        "u1": {
                            "userId": "u1",
                            "handle": "pointfarmcap",
                            "status": "matched",
                            "wallets": [{"address": WALLET, "network": "solana", "method": "swap"}],
                        }
                    }
                },
                cache_path,
            )
            client = HoldingClient({TOKEN2: [{"owner": "FoundWallet", "amount": 100}, {"owner": "X", "amount": 1}]})
            resolve_holdings_all(root=root, path=cache_path, client=client)
            self.assertNotIn(TOKEN, client.calls)
            saved = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["traders"]["u1"]["wallets"][0]["address"], WALLET)
            self.assertEqual(saved["traders"]["u2"]["wallets"][0]["address"], "FoundWallet")
            self.assertEqual(saved["traders"]["u2"]["wallets"][0]["method"], "holding")


class WalletApiTests(unittest.TestCase):
    def test_get_reads_cache(self):
        import app as appmod
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "fomo_wallet_links.json"
            save_wallet_links(
                {
                    "updatedAt": "2026-09-27T00:00:00+00:00",
                    "finishedAt": "2026-09-27T00:00:00+00:00",
                    "traders": {
                        "u1": {
                            "userId": "u1",
                            "handle": "pointfarmcap",
                            "displayName": "point farm capital",
                            "status": "matched",
                            "wallets": [{"address": WALLET, "network": "solana"}],
                        }
                    },
                },
                path,
            )
            with patch("app.load_wallet_links", return_value=__import__("fomo_wallet_link").load_wallet_links(path)):
                client = TestClient(appmod.app)
                res = client.get("/api/fomo-top20/wallets")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["stats"]["matched"], 1)
        self.assertEqual(body["traders"][0]["wallets"][0]["address"], WALLET)

    def test_refresh_requires_login(self):
        import app as appmod
        from fastapi.testclient import TestClient

        client = TestClient(appmod.app)
        with patch("app.get_access_token", return_value=None):
            res = client.post("/api/fomo-top20/wallets/refresh", json={})
        self.assertEqual(res.status_code, 401)

    def test_second_refresh_while_running(self):
        import app as appmod
        from fastapi.testclient import TestClient

        entered = threading.Event()
        hold = threading.Event()

        def fake_resolve(*args, **kwargs):
            entered.set()
            hold.wait(timeout=5)
            return {"traders": {}}

        client = TestClient(appmod.app)
        with patch("app.get_access_token", return_value="tok"), patch("app.resolve_all", side_effect=fake_resolve):
            appmod._wallet_job.update(status="idle", done=0, total=0, error=None)
            first = client.post("/api/fomo-top20/wallets/refresh", json={"force": False})
            self.assertTrue(entered.wait(timeout=2))
            second = client.post("/api/fomo-top20/wallets/refresh", json={"force": False})
            hold.set()
        self.assertTrue(first.json()["started"])
        self.assertTrue(second.json()["running"])
        self.assertFalse(second.json()["ok"])


if __name__ == "__main__":
    unittest.main()
