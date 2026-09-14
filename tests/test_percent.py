# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from update_token_marketcap import (
    fmt_change24,
    fmt_holding_with_mcap_pct,
    fmt_percent,
    fmt_pnl_with_pct,
    rewrite_percents_in_text,
)


class PercentFormatTests(unittest.TestCase):
    def test_lt_10_two_decimals(self):
        self.assertEqual(fmt_percent(2.44), "2.44%")
        self.assertEqual(fmt_percent(9.99), "9.99%")
        self.assertEqual(fmt_percent(0.5), "0.50%")

    def test_lt_100_one_decimal(self):
        self.assertEqual(fmt_percent(10), "10.0%")
        self.assertEqual(fmt_percent(22.3), "22.3%")
        self.assertEqual(fmt_percent(99.9), "99.9%")

    def test_gte_100_no_decimal(self):
        self.assertEqual(fmt_percent(100), "100%")
        self.assertEqual(fmt_percent(150.4), "150%")

    def test_signed(self):
        self.assertEqual(fmt_percent(-5.2, signed=True), "-5.20%")
        self.assertEqual(fmt_percent(21.18, signed=True), "+21.2%")
        self.assertEqual(fmt_percent(-150.7, signed=True), "-151%")

    def test_change24_ratio_and_percent_string(self):
        self.assertEqual(fmt_change24(-0.2118), "-21.2%")
        self.assertEqual(fmt_change24(0.052), "+5.20%")
        self.assertEqual(fmt_change24("+5.20%"), "+5.20%")
        self.assertEqual(fmt_change24("-21.18%"), "-21.2%")
        self.assertEqual(fmt_change24(1.5), "+150%")

    def test_holding_mcap_uses_percent_rules(self):
        self.assertEqual(fmt_holding_with_mcap_pct("2.44M", "100M"), "2.4M(2.44%)")
        self.assertEqual(fmt_holding_with_mcap_pct("12.1M", "100M"), "12.1M(12.1%)")
        self.assertEqual(fmt_holding_with_mcap_pct("150M", "100M"), "150.0M(150%)")

    def test_pnl_pct_uses_percent_rules(self):
        self.assertEqual(fmt_pnl_with_pct(1_200_000, 23.45), "+1.2M(+23.5%)")
        self.assertEqual(fmt_pnl_with_pct(-500_000, -5.2), "-500K(-5.20%)")
        self.assertEqual(fmt_pnl_with_pct(100, 120), "+100(+120%)")

    def test_rewrite_percents_in_holder_line(self):
        self.assertEqual(
            rewrite_percents_in_text("1.alice 12.1M(2.440%) +1.2M(+23.45%)"),
            "1.alice 12.1M(2.44%) +1.2M(+23.5%)",
        )


if __name__ == "__main__":
    unittest.main()
