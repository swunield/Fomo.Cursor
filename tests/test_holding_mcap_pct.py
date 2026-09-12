# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from update_token_marketcap import fmt_holding_with_mcap_pct, normalize_row_display


class HoldingMcapPctTests(unittest.TestCase):
    def test_normalize_row_adds_holding_mcap_percent(self):
        row = {
            "市值": 100_000_000,
            "持仓市值": 12_100_000,
            "人均持仓市值": 1_000_000,
        }
        normalize_row_display(row)
        self.assertEqual(row["持仓市值"], "12.1M(12.1%)")
        self.assertEqual(row["人均持仓市值"], "1.0M")

    def test_normalize_row_holding_mcap_percent_is_idempotent(self):
        row = {"市值": "100.0M", "持仓市值": "12.1M(12.1%)"}
        normalize_row_display(row)
        self.assertEqual(row["持仓市值"], "12.1M(12.1%)")
        normalize_row_display(row)
        self.assertEqual(row["持仓市值"], "12.1M(12.1%)")

    def test_fmt_holding_plain_km_gains_percent(self):
        self.assertEqual(
            fmt_holding_with_mcap_pct("68.8M", "308.3M"),
            "68.8M(22.3%)",
        )

    def test_cached_payload_formats_holding_mcap_percent(self):
        from app import _format_display_rows

        rows = _format_display_rows(
            [{"名称": "UBIK", "市值": "37.6M", "持仓市值": "12.1M"}]
        )
        self.assertEqual(rows[0]["持仓市值"], "12.1M(32.2%)")
    def test_normalize_row_adds_holding_mcap_percent(self):
        row = {
            "市值": 100_000_000,
            "持仓市值": 12_100_000,
            "人均持仓市值": 1_000_000,
        }
        normalize_row_display(row)
        self.assertEqual(row["持仓市值"], "12.1M(12.1%)")
        self.assertEqual(row["人均持仓市值"], "1.0M")

    def test_normalize_row_holding_mcap_percent_is_idempotent(self):
        row = {"市值": "100.0M", "持仓市值": "12.1M(12.1%)"}
        normalize_row_display(row)
        self.assertEqual(row["持仓市值"], "12.1M(12.1%)")
        normalize_row_display(row)
        self.assertEqual(row["持仓市值"], "12.1M(12.1%)")

    def test_fmt_holding_plain_km_gains_percent(self):
        self.assertEqual(
            fmt_holding_with_mcap_pct("68.8M", "308.3M"),
            "68.8M(22.3%)",
        )


if __name__ == "__main__":
    unittest.main()
