# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from update_token_marketcap import (
    CSV_COLUMNS,
    fmt_holding_pnl,
    normalize_row_display,
    sum_holder_pnl_usd,
    sum_pnl_from_holder_text,
)


class HoldingPnlColumnTests(unittest.TestCase):
    def test_column_follows_holding_mcap(self):
        cols = list(CSV_COLUMNS)
        self.assertIn("持仓盈亏", cols)
        self.assertEqual(cols[cols.index("持仓人数") + 1], "持仓市值")
        self.assertEqual(cols[cols.index("持仓市值") + 1], "持仓盈亏")

    def test_sum_holder_pnl_usd(self):
        holders = [
            {"pnlUsd": 1_200_000},
            {"pnlUsd": -500_000},
            {"pnlUsd": None},
        ]
        self.assertEqual(sum_holder_pnl_usd(holders), 700_000)

    def test_sum_empty_is_none(self):
        self.assertIsNone(sum_holder_pnl_usd([]))
        self.assertIsNone(sum_holder_pnl_usd([{"pnlUsd": None}]))

    def test_fmt_holding_pnl_signed_km(self):
        self.assertEqual(fmt_holding_pnl(700_000), "+700K")
        self.assertEqual(fmt_holding_pnl(-1_200_000), "-1.2M")
        self.assertEqual(fmt_holding_pnl("+700K"), "+700K")
        self.assertEqual(fmt_holding_pnl(""), "")

    def test_sum_from_holder_detail_lines(self):
        text = "\n".join(
            [
                "1.alice 12.1M(2.44%) +1.2M(+23.45%) [00:01:00]",
                "2.bob 6.3M(1.27%) -500K(-12.30%) [00:02:00]",
            ]
        )
        self.assertEqual(sum_pnl_from_holder_text(text), 700_000)

    def test_normalize_row_formats_holding_pnl(self):
        row = {"持仓盈亏": 700_000, "市值": 10_000_000, "持仓市值": 1_000_000}
        normalize_row_display(row)
        self.assertEqual(row["持仓盈亏"], "+700K")
        normalize_row_display(row)
        self.assertEqual(row["持仓盈亏"], "+700K")

    def test_normalize_row_fills_pnl_from_holder_lines(self):
        row = {
            "市值": "10.0M",
            "持仓市值": "1.0M",
            "所有持仓人": "1.alice 12.1M(2.44%) +1.2M(+10.00%)\n2.bob 6.3M(1.27%) -500K(-5.00%)",
        }
        normalize_row_display(row)
        self.assertEqual(row["持仓盈亏"], "+700K")


if __name__ == "__main__":
    unittest.main()
