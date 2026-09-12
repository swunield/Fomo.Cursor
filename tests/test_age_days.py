# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timezone
import unittest

from update_token_marketcap import CSV_COLUMNS, fmt_token_age_days, normalize_row_display


class TokenAgeDaysTests(unittest.TestCase):
    def test_days_column_follows_volume(self):
        cols = list(CSV_COLUMNS)
        self.assertIn("天数", cols)
        self.assertEqual(cols[cols.index("成交量") + 1], "天数")

    def test_utc_iso_one_decimal(self):
        now = datetime(2026, 9, 12, 8, 15, 50, tzinfo=timezone.utc)
        self.assertEqual(
            fmt_token_age_days("2026-09-01T16:15:50+00:00", now=now),
            "10.7",
        )

    def test_shanghai_display_matches_utc(self):
        now = datetime(2026, 9, 12, 8, 15, 50, tzinfo=timezone.utc)
        self.assertEqual(
            fmt_token_age_days("2026-09-02 00:15:50", now=now),
            "10.7",
        )

    def test_empty(self):
        self.assertEqual(fmt_token_age_days(""), "")
        self.assertEqual(fmt_token_age_days(None), "")

    def test_normalize_row_fills_days(self):
        now = datetime(2026, 9, 12, 8, 15, 50, tzinfo=timezone.utc)
        row = {"创建时间": "2026-09-01T16:15:50+00:00"}
        normalize_row_display(row, now=now)
        self.assertEqual(row["天数"], "10.7")


if __name__ == "__main__":
    unittest.main()
