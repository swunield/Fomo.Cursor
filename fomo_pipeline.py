# -*- coding: utf-8 -*-
"""FOMO Top20 holdings pipeline (fast path: current mcap + ATH cache)."""
from __future__ import annotations

import json
import time
import urllib.error
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from update_token_marketcap import (
    CACHE_PATH,
    CSV_COLUMNS,
    CSV_PATH,
    JSON_PATH,
    MD_PATH,
    fetch_dexscreener,
    fmt_holding_with_mcap_pct,
    fmt_km,
    get_json,
    load_cache,
    merge_ath,
    normalize_addr,
    normalize_row_display,
    ordered_fieldnames,
    save_cache,
    write_csv_rows,
    write_markdown,
)

ROOT = Path(__file__).resolve().parent
LAST_RESULT_PATH = ROOT / "fomo_top20_last_result.json"

NETWORK_HINTS = {
    1: "ethereum",
    56: "bsc",
    8453: "base",
    42161: "arbitrum",
    137: "polygon",
    4663: "robinhood",
    1399811149: "solana",
    101: "solana",
}


def estimate_holding_value(item: dict) -> float:
    unreal = float(item.get("unrealizedPnlUsd") or 0)
    realized = float(item.get("realizedPnlUsd") or 0)
    profit = float(item.get("profitUsd") or (unreal + realized))
    pct = float(item.get("profitPercent") or 0)
    if pct > 0 and unreal != 0:
        cost = unreal / (pct / 100.0)
        return max(0.0, cost + unreal)
    if pct > 0 and profit != 0:
        cost = profit / (pct / 100.0)
        return max(0.0, cost + profit)
    if item.get("closedAt") is None and unreal > 0:
        return unreal
    return 0.0


def infer_platform(addr: str, network_id: Any, dex_meta: dict | None) -> str:
    addr = addr or ""
    low = addr.lower()
    meta = dex_meta or {}
    chain = meta.get("chainId") or NETWORK_HINTS.get(int(network_id or 0), "")
    dex = (meta.get("dexId") or "").lower()

    if low.endswith("pump"):
        return "pump.fun"
    if low.endswith("bonk"):
        return "LetsBonk"
    if chain == "robinhood" or int(network_id or 0) == 4663:
        if "pons" in low or low.startswith("0x39dbed"):
            return "Pons Launchpad"
        return "Robinhood Chain / Pons"
    if chain == "bsc" or int(network_id or 0) == 56:
        return f"BSC ({dex or 'pancakeswap'})"
    if chain == "base" or int(network_id or 0) == 8453:
        return f"Base ({dex or 'uniswap'})"
    if chain == "solana" or int(network_id or 0) in (1399811149, 101):
        return f"Solana ({dex or 'raydium'})"
    if chain and dex:
        return f"{chain} ({dex})"
    if chain:
        return chain
    return "unknown"


def fetch_top20_traders(progress: Callable[[str], None] | None = None) -> list[dict]:
    if progress:
        progress("正在拉取 FOMO 总榜…")
    data = get_json("https://985monitor.xyz/fomo-leaderboards.json", retries=2)
    rows = (data.get("boards") or {}).get("all") or []
    traders = []
    for r in rows[:20]:
        traders.append(
            {
                "rank": int(r.get("rank") or len(traders) + 1),
                "handle": r.get("handle") or "",
                "name": r.get("name") or r.get("handle") or "",
                "pnl": float(r.get("pnl") or 0),
                "followers": int(r.get("followers") or 0),
                "numTrades": int(r.get("numTrades") or 0),
            }
        )
    return traders


def fetch_profile(handle: str) -> dict:
    url = f"https://985monitor.xyz/api/fomo-watch/profile?handle={handle}"
    try:
        return get_json(url, retries=2)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "handle": handle}


def collect_open_holdings(
    traders: list[dict],
    progress: Callable[[str], None] | None = None,
    mode: str = "fast",
) -> tuple[dict[str, list[dict]], dict[str, dict], dict]:
    """Return token_map, profiles, stats.

    mode=fast: 985monitor profitSnapshot
    mode=full: FOMO /v2/users/{userId}/balances with Privy token
    """
    from fomo_auth import balances_to_holdings, fetch_user_balances, get_access_token

    token_map: dict[str, list[dict]] = defaultdict(list)
    profiles: dict[str, dict] = {}
    stats = {
        "mode": mode,
        "tradersOk": 0,
        "tradersFail": 0,
        "holdingRows": 0,
        "errors": [],
    }

    if mode == "full" and not get_access_token():
        raise RuntimeError("全量模式需要先配置 Privy Access Token")

    def one(trader: dict):
        handle = trader["handle"]
        profile = fetch_profile(handle)
        return trader, profile

    done = 0
    with ThreadPoolExecutor(max_workers=4 if mode == "full" else 6) as pool:
        futures = [pool.submit(one, t) for t in traders]
        for fut in as_completed(futures):
            trader, profile = fut.result()
            done += 1
            handle = trader["handle"]
            profiles[handle] = profile
            name = trader.get("name") or handle
            if progress:
                progress(f"拉取持仓 {done}/{len(traders)}：{name} ({mode})")

            holdings = []
            try:
                if mode == "full":
                    user_id = (profile.get("profile") or {}).get("userId") or profile.get("userId")
                    if not user_id:
                        raise RuntimeError(f"profile missing userId for {handle}")
                    bal_rows = fetch_user_balances(user_id)
                    holdings = balances_to_holdings(bal_rows)
                else:
                    snap = profile.get("profitSnapshot") or {}
                    for item in snap.get("items") or []:
                        if item.get("closedAt") is not None:
                            continue
                        addr = (item.get("tokenAddress") or "").strip()
                        if not addr:
                            continue
                        value = estimate_holding_value(item)
                        if value <= 0:
                            continue
                        holdings.append(
                            {
                                "tokenAddress": addr,
                                "symbol": (item.get("symbol") or "").strip(),
                                "name": (item.get("name") or "").strip(),
                                "networkId": item.get("networkId"),
                                "value": value,
                            }
                        )
                stats["tradersOk"] += 1
            except Exception as exc:
                stats["tradersFail"] += 1
                stats["errors"].append(f"{handle}: {exc}")
                if progress:
                    progress(f"失败 {name}: {exc}")
                continue

            for h in holdings:
                addr = (h.get("tokenAddress") or "").strip()
                if not addr:
                    continue
                value = float(h.get("value") or 0)
                if value <= 0:
                    continue
                symbol = (h.get("symbol") or "").strip()
                raw_name = (h.get("name") or "").strip()
                display = (
                    f"{symbol} ({raw_name})"
                    if raw_name and symbol and raw_name.upper() != symbol.upper()
                    else (symbol or raw_name or addr[:10])
                )
                token_map[normalize_addr(addr)].append(
                    {
                        "rank": trader["rank"],
                        "name": trader["name"] or handle,
                        "handle": handle,
                        "value": value,
                        "tokenAddress": addr,
                        "networkId": h.get("networkId"),
                        "symbol": symbol,
                        "displayName": display,
                        "rawName": raw_name,
                    }
                )
                stats["holdingRows"] += 1
    return token_map, profiles, stats


def aggregate_rows(
    token_map: dict[str, list[dict]],
    dex_data: dict[str, dict],
    ath_cache: dict,
) -> list[dict]:
    rows = []
    for key, holders in token_map.items():
        holders = sorted(holders, key=lambda h: h["rank"])
        total = sum(h["value"] for h in holders)
        count = len(holders)
        avg = total / count if count else 0
        hi = max(holders, key=lambda h: h["value"])
        lo = min(holders, key=lambda h: h["value"])
        sample = holders[0]
        addr = sample["tokenAddress"]
        meta = dex_data.get(normalize_addr(addr), {})
        current_mcap = float(meta.get("marketCap") or 0)
        ath_mcap, ath_time = merge_ath(ath_cache, addr, current_mcap, None, None)

        symbol = (meta.get("symbol") or sample.get("symbol") or "").strip()
        name = (meta.get("name") or sample.get("rawName") or "").strip()
        if symbol and name and name.upper() != symbol.upper():
            display = f"{symbol} ({name})"
        else:
            display = symbol or name or sample["displayName"]

        holder_details = [
            f"{h['rank']}.{h['name']} {fmt_holding_with_mcap_pct(h['value'], current_mcap)}"
            for h in holders
        ]
        row = {
            "名称": display,
            "市值": current_mcap if current_mcap else "",
            "持仓市值": total,
            "持仓人数": count,
            "人均持仓市值": avg,
            "最高市值": ath_mcap if ath_mcap else "",
            "最高市值时间": ath_time or "",
            "最高持仓人": f"{hi['rank']}.{hi['name']}",
            "最高持仓市值": hi["value"],
            "最低持仓人": f"{lo['rank']}.{lo['name']}",
            "最低持仓市值": lo["value"],
            "所有持仓人": "\n".join(holder_details),
            "持仓明细": holder_details,
            "发射平台": infer_platform(addr, sample.get("networkId"), meta),
            "合约地址": addr,
        }
        normalize_row_display(row)
        rows.append(row)

    def sort_key(r):
        from update_token_marketcap import parse_number

        return parse_number(r.get("持仓市值")) or 0

    rows.sort(key=sort_key, reverse=True)
    return rows


def persist_outputs(traders: list[dict], rows: list[dict], meta: dict) -> None:
    fieldnames = list(CSV_COLUMNS)
    errors = []
    try:
        write_csv_rows(fieldnames, rows)
    except OSError as exc:
        errors.append(f"csv: {exc}")
        alt = CSV_PATH.with_suffix(".live.csv")
        try:
            with open(alt, "w", encoding="utf-8-sig", newline="") as f:
                import csv

                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        except OSError as exc2:
            errors.append(f"csv-alt: {exc2}")
    try:
        write_markdown(rows)
    except OSError as exc:
        errors.append(f"md: {exc}")

    payload = {
        "generatedAt": meta.get("updatedAt"),
        "marketCapUpdatedAt": meta.get("updatedAt"),
        "source": meta.get("source")
        or "985monitor FOMO spotlight + DexScreener (fast path ATH cache)",
        "limitation": meta.get("limitation")
        or (
            "FOMO 官方 API 需登录。本表以 spotlight 未平仓盈利仓估算持仓市值；"
            "每人通常仅覆盖头部仓位。最高市值优先本地缓存，无历史源时初值=当前市值。"
        ),
        "mode": meta.get("mode") or "fast",
        "stats": meta.get("stats") or {},
        "traders": traders,
        "tokenCount": len(rows),
        "columns": list(CSV_COLUMNS),
        "rows": rows,
        "tokens": rows,
    }
    for path in (JSON_PATH, LAST_RESULT_PATH):
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            errors.append(f"{path.name}: {exc}")
    if errors:
        meta["persistWarnings"] = errors


def load_cached_result() -> dict | None:
    path = LAST_RESULT_PATH if LAST_RESULT_PATH.exists() else JSON_PATH
    if not path.exists():
        return None
    try:
        from update_token_marketcap import CSV_COLUMNS, rename_legacy_row

        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("rows", "tokens"):
            if key in data and isinstance(data[key], list):
                data[key] = [rename_legacy_row(r) for r in data[key]]
        data["columns"] = list(CSV_COLUMNS)
        return data
    except Exception:
        return None


def run_pipeline(progress: Callable[[str], None] | None = None, mode: str = "fast") -> dict:
    started = time.time()
    mode = "full" if mode == "full" else "fast"
    traders = fetch_top20_traders(progress)
    token_map, _profiles, stats = collect_open_holdings(traders, progress, mode=mode)

    addresses = []
    for holders in token_map.values():
        if holders:
            addresses.append(holders[0]["tokenAddress"])

    if progress:
        progress(f"正在拉取/命中缓存市值（{len(addresses)} 个，单币间隔≥10分钟）…")
    dex_data = fetch_dexscreener(addresses)

    if progress:
        progress("合并最高市值缓存…")
    ath_cache = load_cache()
    rows = aggregate_rows(token_map, dex_data, ath_cache)
    save_cache(ath_cache)

    updated_at = datetime.now(timezone.utc).isoformat()
    if mode == "full":
        source = "FOMO /v2/users/{id}/balances (Privy) + DexScreener"
        limitation = (
            "全量模式：使用你的 Privy Token 调用官方 balances。"
            "若某账号失败会记入 stats.errors；最高市值仍优先本地缓存。"
        )
        note = "全量模式：持仓来自 FOMO balances；市值 DexScreener（本地缓存，单币≥10分钟）；最高市值缓存。"
    else:
        source = "985monitor FOMO spotlight + DexScreener (fast path ATH cache)"
        limitation = (
            "快速模式：spotlight 未平仓盈利仓估算，通常仅头部仓位。"
            "最高市值优先本地缓存，无历史源时初值=当前市值。"
        )
        note = "快速模式：市值 DexScreener（本地缓存，单币≥10分钟）；最高市值本地缓存。"

    result = {
        "updatedAt": updated_at,
        "elapsedSec": round(time.time() - started, 1),
        "mode": mode,
        "source": source,
        "limitation": limitation,
        "stats": stats,
        "traders": traders,
        "tokenCount": len(rows),
        "columns": list(CSV_COLUMNS),
        "rows": rows,
        "note": note,
    }
    if progress:
        progress("写入 CSV / JSON / Markdown…")
    persist_outputs(traders, rows, result)
    if progress:
        progress(f"完成，共 {len(rows)} 个代币，用时 {result['elapsedSec']}s")
    return result


def run_fast_pipeline(progress: Callable[[str], None] | None = None) -> dict:
    return run_pipeline(progress=progress, mode="fast")


def run_full_pipeline(progress: Callable[[str], None] | None = None) -> dict:
    return run_pipeline(progress=progress, mode="full")
