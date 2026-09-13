# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from fomo_pipeline import token_map_for_traders, unique_traders


class UniqueTradersTests(unittest.TestCase):
    def test_same_uid_kept_once(self):
        all_board = [
            {"rank": 1, "handle": "alice", "name": "Alice", "uid": "u1"},
            {"rank": 2, "handle": "bob", "name": "Bob", "uid": "u2"},
        ]
        day_board = [
            {"rank": 8, "handle": "alice", "name": "Alice", "uid": "u1"},
            {"rank": 3, "handle": "cara", "name": "Cara", "uid": "u3"},
        ]
        out = unique_traders(all_board, day_board)
        self.assertEqual([t["uid"] for t in out], ["u1", "u2", "u3"])

    def test_same_handle_without_uid_kept_once(self):
        a = [{"rank": 1, "handle": "Alice", "name": "Alice", "uid": ""}]
        b = [{"rank": 9, "handle": "alice", "name": "Alice", "uid": ""}]
        out = unique_traders(a, b)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rank"], 1)


class TokenMapForTradersTests(unittest.TestCase):
    def test_keeps_board_traders_and_rewrites_rank(self):
        token_map = {
            "addr1": [
                {
                    "rank": 1,
                    "name": "Alice",
                    "handle": "alice",
                    "uid": "u1",
                    "value": 100,
                    "tokenAddress": "ADDR1",
                },
                {
                    "rank": 2,
                    "name": "Bob",
                    "handle": "bob",
                    "uid": "u2",
                    "value": 50,
                    "tokenAddress": "ADDR1",
                },
            ]
        }
        traders = [{"rank": 8, "handle": "alice", "name": "Alice", "uid": "u1"}]
        filtered = token_map_for_traders(token_map, traders)
        self.assertEqual(len(filtered["addr1"]), 1)
        self.assertEqual(filtered["addr1"][0]["rank"], 8)
        self.assertEqual(filtered["addr1"][0]["name"], "Alice")


if __name__ == "__main__":
    unittest.main()
