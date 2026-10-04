# -*- coding: utf-8 -*-
"""Resolve unmatched FOMO holders via board holding amounts + on-chain balances."""
from __future__ import annotations

import json
from pathlib import Path

from deploy.push import connect, run
from fomo_wallet_link import (
    load_wallet_links,
    resolve_holdings_all,
    wallet_public_view,
)

WORK = Path(r"C:\Users\swuni\AppData\Local\Temp\fomo_wallet_work")
CACHE = WORK / "fomo_wallet_links.json"
REMOTE_CACHE = "/opt/Fomo/fomo_wallet_links.json"


def main() -> None:
    before = load_wallet_links(CACHE)
    before_matched = {
        uid
        for uid, row in (before.get("traders") or {}).items()
        if row.get("status") == "matched" and row.get("wallets")
    }
    print("before_matched", len(before_matched), flush=True)

    def progress(done: int, total: int) -> None:
        if done == total or done % 10 == 0:
            print(f"{done}/{total}", flush=True)

    cache = resolve_holdings_all(
        root=WORK,
        board_root=WORK,
        path=CACHE,
        progress_fn=progress,
    )
    view = wallet_public_view(cache)
    print("stats", view["stats"], flush=True)

    new_rows = []
    for uid, row in (cache.get("traders") or {}).items():
        if uid in before_matched:
            continue
        if row.get("status") != "matched" or not row.get("wallets"):
            continue
        wallets = [
            w
            for w in row.get("wallets") or []
            if isinstance(w, dict) and w.get("method") == "holding"
        ]
        if not wallets:
            wallets = [w for w in row.get("wallets") or [] if isinstance(w, dict)]
        w0 = wallets[0]
        new_rows.append(
            (
                row.get("handle") or "",
                w0.get("network"),
                w0.get("address"),
                w0.get("amount"),
                w0.get("token"),
            )
        )
    new_rows.sort(key=lambda item: (-(item[3] or 0), item[0]))
    print("newly_matched", len(new_rows), flush=True)
    for handle, net, addr, amount, token in new_rows[:40]:
        print(f"NEW {handle} {net} amt={amount} {addr} token={str(token)[:20]}", flush=True)

    _, client = connect()
    sftp = client.open_sftp()
    sftp.put(str(CACHE), REMOTE_CACHE)
    sftp.close()
    run(client, "systemctl restart fomo")
    client.close()
    print("uploaded", CACHE.stat().st_size, flush=True)


if __name__ == "__main__":
    main()
