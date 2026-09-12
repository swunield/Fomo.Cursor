# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from update_token_marketcap import fmt_created_at_local, normalize_row_display


class FmtCreatedAtLocalTests(unittest.TestCase):
    def test_utc_iso_to_shanghai(self):
        self.assertEqual(
            fmt_created_at_local("2026-09-01T16:15:50+00:00"),
            "2026-09-02 00:15:50",
        )

    def test_naive_iso_treated_as_utc(self):
        self.assertEqual(
            fmt_created_at_local("2026-09-01T16:15:50"),
            "2026-09-02 00:15:50",
        )

    def test_already_local_display_stays(self):
        self.assertEqual(
            fmt_created_at_local("2026-09-02 00:15:50"),
            "2026-09-02 00:15:50",
        )

    def test_empty(self):
        self.assertEqual(fmt_created_at_local(""), "")
        self.assertEqual(fmt_created_at_local(None), "")

    def test_normalize_row_converts_created_at(self):
        row = {"创建时间": "2026-09-01T16:15:50+00:00"}
        normalize_row_display(row)
        self.assertEqual(row["创建时间"], "2026-09-02 00:15:50")
        normalize_row_display(row)
        self.assertEqual(row["创建时间"], "2026-09-02 00:15:50")


if __name__ == "__main__":
    unittest.main()
