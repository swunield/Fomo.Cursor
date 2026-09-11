# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from fomo_pipeline import debot_token_url


class DebotTokenUrlTests(unittest.TestCase):
    def test_4stock_uses_robinhood_even_if_platform_says_bsc(self):
        self.assertEqual(
            debot_token_url(
                "0xd270d4e1ec6e6e0d28c0ecb8be966ec75997ffff",
                "BSC (pancakeswap)",
            ),
            "https://debot.ai/token/robinhood/0xd270d4e1ec6e6e0d28c0ecb8be966ec75997ffff",
        )

    def test_pons_launchpad_is_robinhood(self):
        self.assertEqual(
            debot_token_url("0x39dbed3a2bd333467115de45665cc57f813c4571", "Pons Launchpad"),
            "https://debot.ai/token/robinhood/0x39dbed3a2bd333467115de45665cc57f813c4571",
        )

    def test_solana_pump(self):
        self.assertEqual(
            debot_token_url("9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump", "pump.fun"),
            "https://debot.ai/token/solana/9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump",
        )

    def test_base_uniswap(self):
        self.assertEqual(
            debot_token_url(
                "0x5ab000ff9b9ffe0349ce5ffa5fd86f217c3680f5",
                "Base (uniswap)",
            ),
            "https://debot.ai/token/base/0x5ab000ff9b9ffe0349ce5ffa5fd86f217c3680f5",
        )

    def test_network_id_wins(self):
        self.assertEqual(
            debot_token_url("0xabc", "BSC (pancakeswap)", network_id=8453),
            "https://debot.ai/token/base/0xabc",
        )

    def test_plain_bsc_stays_bsc(self):
        self.assertEqual(
            debot_token_url(
                "0xfa6d9b504848606eb9aec04ccc161d169b3f2159",
                "BSC (pancakeswap)",
            ),
            "https://debot.ai/token/bsc/0xfa6d9b504848606eb9aec04ccc161d169b3f2159",
        )
        self.assertEqual(debot_token_url("", "Solana (raydium)"), "")


if __name__ == "__main__":
    unittest.main()
