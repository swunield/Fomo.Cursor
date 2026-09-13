# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DUST_AMOUNT = 1e-9

_REPO_ROOT = Path(__file__).resolve().parent
TRADES_DIR = _REPO_ROOT / "fomo_token_trades"


def normalize_token_addr(addr: str) -> str:
    raw = str(addr or "").strip()
    if ".." in raw or "/" in raw or "\\" in raw:
        raise ValueError("非法合约地址")
    return raw.lower()


def circulating_supply(market_cap: float, price_usd: float) -> float:
    if price_usd > 0:
        return market_cap / price_usd
    return 0.0


def _event_price(qty: float, usd: float) -> float:
    if not qty or not usd:
        return 0.0
    return usd / abs(qty)


def iter_trade_events(
    token_address: str,
    user_id: str,
    user_address: str,
    trade_obj: dict,
) -> list[dict]:
    token = normalize_token_addr(token_address)
    events: list[dict] = []

    for swap in trade_obj.get("swaps") or []:
        created_at = swap.get("createdAt")
        if not created_at:
            continue

        out_addr = normalize_token_addr(swap.get("outTokenAddress") or "")
        in_addr = normalize_token_addr(swap.get("inTokenAddress") or "")

        if out_addr == token:
            qty = float(swap.get("outHumanAmount") or 0)
            usd = float(
                swap.get("humanUsdAmountIn") or swap.get("humanUsdAmountOut") or 0
            )
        elif in_addr == token:
            qty = -float(swap.get("inHumanAmount") or 0)
            usd = float(
                swap.get("humanUsdAmountOut") or swap.get("humanUsdAmountIn") or 0
            )
        else:
            continue

        events.append(
            {
                "t": created_at,
                "userId": user_id,
                "qty": qty,
                "usd": usd,
                "price": _event_price(qty, usd),
            }
        )

    for transfer in trade_obj.get("transfers") or []:
        created_at = transfer.get("createdAt")
        if not created_at:
            continue

        if normalize_token_addr(transfer.get("tokenAddress") or "") != token:
            continue

        amount = float(transfer.get("humanAmount") or 0)
        usd = float(transfer.get("usdAmount") or 0)
        to_addr = transfer.get("toAddress") or ""
        from_addr = transfer.get("fromAddress") or ""

        if to_addr == user_address:
            qty = amount
        elif from_addr == user_address:
            qty = -amount
        else:
            continue

        events.append(
            {
                "t": created_at,
                "userId": user_id,
                "qty": qty,
                "usd": usd,
                "price": _event_price(qty, usd),
            }
        )

    return events


def _snapshot(
    t: str,
    positions: dict[str, dict[str, float]],
    last_price: float,
    circulating: float,
) -> dict:
    total_amount = 0.0
    holders = 0
    pnl = 0.0

    for pos in positions.values():
        amount = pos["amount"]
        total_amount += amount
        if amount > DUST_AMOUNT:
            holders += 1
        pnl += amount * last_price - pos["cost"] + pos["realized"]

    return {
        "t": t,
        "mcap": last_price * circulating,
        "holders": holders,
        "amount": total_amount,
        "holdMcap": total_amount * last_price,
        "pnl": pnl,
    }


def build_series(
    token_address: str,
    circulating_supply: float,
    traders: dict,
) -> list[dict]:
    events: list[dict] = []

    for trader in traders.values():
        user_id = trader.get("userId") or ""
        default_address = trader.get("userAddress") or ""
        for trade_obj in (trader.get("trades") or {}).values():
            user_address = trade_obj.get("userAddress") or default_address
            events.extend(
                iter_trade_events(token_address, user_id, user_address, trade_obj)
            )

    events.sort(key=lambda e: e["t"])

    positions: dict[str, dict[str, float]] = {}
    last_price = 0.0
    series: list[dict] = []

    for event in events:
        user_id = event["userId"]
        qty = event["qty"]
        usd = event["usd"]
        price = event["price"]

        pos = positions.setdefault(
            user_id, {"amount": 0.0, "cost": 0.0, "realized": 0.0}
        )

        if qty > 0:
            pos["amount"] += qty
            pos["cost"] += usd
        elif qty < 0:
            sold = min(pos["amount"], -qty)
            frac = sold / pos["amount"] if pos["amount"] else 0.0
            proceeds = usd * (sold / (-qty)) if qty < 0 and -qty else usd
            cost_cut = pos["cost"] * frac
            pos["realized"] += proceeds - cost_cut
            pos["cost"] -= cost_cut
            pos["amount"] -= sold

        if price > 0:
            last_price = price

        point = _snapshot(event["t"], positions, last_price, circulating_supply)
        if series and series[-1]["t"] == point["t"]:
            series[-1] = point
        else:
            series.append(point)

    return series


def empty_cache(addr: str) -> dict:
    return {
        "tokenAddress": normalize_token_addr(addr),
        "traders": {},
        "series": [],
        "lastFetchedAt": None,
        "circulatingSupply": 0,
    }


def _trades_path(addr: str, *, root: Path | None = None) -> Path:
    key = normalize_token_addr(addr)
    base = (root / "fomo_token_trades").resolve() if root is not None else TRADES_DIR.resolve()
    path = (base / f"{key}.json").resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError("非法合约地址") from exc
    return path


def load_token_trades(addr: str, *, root: Path | None = None) -> dict:
    path = _trades_path(addr, root=root)
    if not path.is_file():
        return empty_cache(addr)
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return empty_cache(addr)
    if not isinstance(data, dict):
        return empty_cache(addr)
    return data


def save_token_trades(addr: str, data: dict, *, root: Path | None = None) -> None:
    path = _trades_path(addr, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def should_skip_trade(
    cached_trade: dict | None, incoming_updated_at: str | None
) -> bool:
    if not cached_trade:
        return False
    closed_at = cached_trade.get("closedAt")
    if closed_at:
        return True
    cached_updated = cached_trade.get("updatedAt")
    if (
        cached_updated
        and incoming_updated_at
        and cached_updated == incoming_updated_at
    ):
        return True
    return False


def _find_cached_trade(cache: dict, trade_id: str) -> dict | None:
    for trader in (cache.get("traders") or {}).values():
        trade = (trader.get("trades") or {}).get(trade_id)
        if trade is not None:
            return trade
    return None


def plan_trade_fetches(cache: dict, holders: list[dict]) -> list[dict]:
    seen: set[str] = set()
    planned: list[dict] = []

    for holder in holders:
        trade_id = (holder.get("tradeId") or "").strip()
        if not trade_id:
            cache["_missingTradeIds"] = cache.get("_missingTradeIds", 0) + 1
            continue
        if trade_id in seen:
            continue
        seen.add(trade_id)

        cached_trade = _find_cached_trade(cache, trade_id)
        if should_skip_trade(cached_trade, holder.get("tradeUpdatedAt")):
            continue

        planned.append(
            {
                "userId": holder.get("uid") or "",
                "handle": holder.get("handle") or "",
                "displayName": holder.get("name") or "",
                "tradeId": trade_id,
            }
        )

    for trader in (cache.get("traders") or {}).values():
        for trade_id, cached_trade in (trader.get("trades") or {}).items():
            if trade_id in seen:
                continue
            seen.add(trade_id)
            if should_skip_trade(cached_trade, None):
                continue
            planned.append(
                {
                    "userId": trader.get("userId") or "",
                    "handle": trader.get("handle") or "",
                    "displayName": trader.get("displayName") or "",
                    "tradeId": trade_id,
                }
            )

    return planned


def _merge_items_by_id(existing: list[dict], incoming: list[dict]) -> list[dict]:
    by_id = {item["id"]: item for item in existing if item.get("id")}
    for item in incoming or []:
        item_id = item.get("id")
        if item_id:
            by_id[item_id] = item
    return list(by_id.values())


def merge_fetched_trade(cache: dict, holder: dict, payload: dict) -> None:
    user_id = (
        payload.get("userId") or holder.get("uid") or holder.get("userId") or ""
    )
    trade = payload.get("trade") or {}
    trade_id = trade.get("id") or holder.get("tradeId") or ""
    handle = payload.get("userHandle") or holder.get("handle") or ""
    display_name = (
        payload.get("displayName")
        or holder.get("name")
        or holder.get("displayName")
        or ""
    )

    trader = cache.setdefault("traders", {}).setdefault(
        user_id,
        {
            "userId": user_id,
            "handle": handle,
            "displayName": display_name,
            "trades": {},
        },
    )
    if payload.get("userHandle"):
        trader["handle"] = payload["userHandle"]
    if payload.get("displayName"):
        trader["displayName"] = payload["displayName"]

    existing = (trader.get("trades") or {}).get(trade_id) or {}
    merged = {
        "id": trade_id,
        "updatedAt": trade.get("updatedAt"),
        "closedAt": trade.get("closedAt"),
        "userAddress": trade.get("userAddress") or existing.get("userAddress") or "",
        "swaps": _merge_items_by_id(existing.get("swaps") or [], payload.get("swaps") or []),
        "transfers": _merge_items_by_id(
            existing.get("transfers") or [], payload.get("transfers") or []
        ),
    }
    trader.setdefault("trades", {})[trade_id] = merged


def apply_series(cache: dict, token_address: str, circulating_supply: float) -> dict:
    cache["circulatingSupply"] = circulating_supply
    cache["series"] = build_series(
        token_address, circulating_supply, cache.get("traders") or {}
    )
    return cache


def refresh_token_chart(
    addr,
    holders,
    *,
    fetch_fn,
    root=None,
    circulating=None,
    progress_fn=None,
):
    cache = load_token_trades(addr, root=root)
    planned = plan_trade_fetches(cache, holders)
    stats = {"fetched": 0, "skipped": 0, "failed": 0, "missingTradeIds": 0}
    stats["missingTradeIds"] = sum(
        1 for h in holders or [] if not str(h.get("tradeId") or "").strip()
    )
    stats["skipped"] = (
        sum(len(t.get("trades") or {}) for t in (cache.get("traders") or {}).values())
        + len(holders or [])
        - stats["missingTradeIds"]
        - len(planned)
    )
    total = len(planned)
    for i, item in enumerate(planned, start=1):
        if progress_fn:
            progress_fn(i - 1, total)
        try:
            payload = fetch_fn(item["tradeId"])
            holder = {
                "uid": item.get("uid") or item.get("userId") or "",
                "handle": item.get("handle") or "",
                "name": item.get("name") or item.get("displayName") or "",
                "tradeId": item.get("tradeId") or "",
            }
            merge_fetched_trade(cache, holder, payload)
            stats["fetched"] += 1
        except Exception:
            stats["failed"] += 1
        if progress_fn:
            progress_fn(i, total)
    supply = float(circulating or cache.get("circulatingSupply") or 0)
    cache["circulatingSupply"] = supply
    cache["series"] = build_series(addr, supply, cache.get("traders") or {})
    if not (stats["fetched"] == 0 and stats["failed"] > 0):
        cache["lastFetchedAt"] = datetime.now(timezone.utc).isoformat()
    cache["stats"] = stats
    save_token_trades(addr, cache, root=root)
    return cache
