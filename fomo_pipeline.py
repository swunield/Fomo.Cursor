# -*- coding: utf-8 -*-
"""FOMO Top20 holdings pipeline (fast path: current mcap + ATH cache)."""
from __future__ import annotations

import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from update_token_marketcap import (
    CACHE_PATH,
    CSV_COLUMNS,
    CSV_PATH,
    JSON_PATH,
    MD_PATH,
    fmt_holder_detail_line,
    fmt_holding_with_mcap_pct,
    fmt_km,
    load_cache,
    merge_ath,
    normalize_addr,
    normalize_row_display,
    ordered_fieldnames,
    save_cache,
    sum_holder_pnl_usd,
    write_csv_rows,
    write_markdown,
)

ROOT = Path(__file__).resolve().parent
LAST_RESULT_PATH = ROOT / "fomo_top20_last_result.json"
LAST_RESULT_7D_PATH = ROOT / "fomo_7d50_last_result.json"
JSON_7D_PATH = ROOT / "fomo_7d50_holdings_by_token.json"
CSV_7D_PATH = ROOT / "fomo_7d50_holdings_by_token.csv"
MD_7D_PATH = ROOT / "fomo_7d50_holdings_by_token.md"
LAST_RESULT_24H_PATH = ROOT / "fomo_24h_last_result.json"
JSON_24H_PATH = ROOT / "fomo_24h_holdings_by_token.json"
CSV_24H_PATH = ROOT / "fomo_24h_holdings_by_token.csv"
MD_24H_PATH = ROOT / "fomo_24h_holdings_by_token.md"
SETTINGS_PATH = ROOT / "fomo_settings.json"

DEFAULT_SETTINGS = {
    "allLimit": 20,
    "dayLimit": 50,
    "h24Limit": 50,
    "refreshMinutes": 10,
}
LIMIT_MIN = 1
LIMIT_MAX = 200
REFRESH_MINUTES_MIN = 1
REFRESH_MINUTES_MAX = 180

BOARD_CONFIG = {
    "all": {
        "boardKey": "all",
        "limit": 20,
        "label": "总榜",
        "lastResult": LAST_RESULT_PATH,
        "jsonPath": JSON_PATH,
        "csvPath": CSV_PATH,
        "mdPath": MD_PATH,
    },
    "7d": {
        "boardKey": "7d",
        "limit": 50,
        "label": "7日榜",
        "lastResult": LAST_RESULT_7D_PATH,
        "jsonPath": JSON_7D_PATH,
        "csvPath": CSV_7D_PATH,
        "mdPath": MD_7D_PATH,
    },
    "24h": {
        "boardKey": "24h",
        "limit": 50,
        "label": "24小时榜",
        "lastResult": LAST_RESULT_24H_PATH,
        "jsonPath": JSON_24H_PATH,
        "csvPath": CSV_24H_PATH,
        "mdPath": MD_24H_PATH,
    },
}

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

DEBOT_CHAIN_BY_NETWORK = {
    1: "eth",
    56: "bsc",
    8453: "base",
    42161: "arbitrum",
    137: "polygon",
    4663: "robinhood",
    1399811149: "solana",
    101: "solana",
}


def debot_chain(
    addr: str = "",
    platform: str = "",
    network_id: Any = None,
    chain_hint: str = "",
) -> str:
    """Debot URL chain slug for a token."""
    try:
        nid = int(network_id)
    except (TypeError, ValueError):
        nid = 0
    if nid in DEBOT_CHAIN_BY_NETWORK:
        return DEBOT_CHAIN_BY_NETWORK[nid]

    hint = (chain_hint or "").strip().lower()
    hint_map = {
        "ethereum": "eth",
        "eth": "eth",
        "bsc": "bsc",
        "base": "base",
        "solana": "solana",
        "robinhood": "robinhood",
        "arbitrum": "arbitrum",
        "polygon": "polygon",
        "xlayer": "xlayer",
    }
    if hint in hint_map:
        return hint_map[hint]

    p = (platform or "").lower()
    a = (addr or "").strip()
    if "robinhood" in p or "pons" in p:
        return "robinhood"
    if a.lower().startswith("0x") and len(a) == 42 and a.lower().endswith("ffff"):
        return "robinhood"
    if "pump.fun" in p or "letsbonk" in p or "solana" in p:
        return "solana"
    if "bsc" in p or "pancake" in p:
        return "bsc"
    if "base" in p:
        return "base"
    if "ethereum" in p:
        return "eth"
    if "arbitrum" in p:
        return "arbitrum"
    if "polygon" in p:
        return "polygon"
    if a.startswith("0x"):
        return ""
    if a:
        return "solana"
    return ""


def debot_token_url(
    addr: str,
    platform: str = "",
    network_id: Any = None,
    chain_hint: str = "",
) -> str:
    token = (addr or "").strip()
    if not token:
        return ""
    chain = debot_chain(token, platform, network_id=network_id, chain_hint=chain_hint)
    if not chain:
        return ""
    return f"https://debot.ai/token/{chain}/{token}"


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


def clamp_limit(value: Any, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = int(default)
    return max(LIMIT_MIN, min(LIMIT_MAX, n))


def clamp_refresh_minutes(value: Any, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = int(default)
    return max(REFRESH_MINUTES_MIN, min(REFRESH_MINUTES_MAX, n))


def load_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
        except Exception:
            pass
    return {
        "allLimit": clamp_limit(data.get("allLimit"), DEFAULT_SETTINGS["allLimit"]),
        "dayLimit": clamp_limit(data.get("dayLimit"), DEFAULT_SETTINGS["dayLimit"]),
        "h24Limit": clamp_limit(
            data.get("h24Limit", data.get("hourLimit")),
            DEFAULT_SETTINGS["h24Limit"],
        ),
        "refreshMinutes": clamp_refresh_minutes(
            data.get("refreshMinutes"),
            DEFAULT_SETTINGS["refreshMinutes"],
        ),
    }


def save_settings(
    all_limit: Any = None,
    day_limit: Any = None,
    h24_limit: Any = None,
    refresh_minutes: Any = None,
) -> dict:
    cur = load_settings()
    if all_limit is not None:
        cur["allLimit"] = clamp_limit(all_limit, cur["allLimit"])
    if day_limit is not None:
        cur["dayLimit"] = clamp_limit(day_limit, cur["dayLimit"])
    if h24_limit is not None:
        cur["h24Limit"] = clamp_limit(h24_limit, cur["h24Limit"])
    if refresh_minutes is not None:
        cur["refreshMinutes"] = clamp_refresh_minutes(
            refresh_minutes, DEFAULT_SETTINGS["refreshMinutes"]
        )
    SETTINGS_PATH.write_text(
        json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return cur


def resolve_board(board: str, limit: int | None = None) -> dict:
    b = (board or "all").strip().lower()
    if b in ("7d", "7day", "week"):
        key = "7d"
    elif b in ("24h", "24", "day", "1d", "h24"):
        key = "24h"
    else:
        key = "all"
    base = BOARD_CONFIG[key]
    settings = load_settings()
    if key == "7d":
        default_limit = settings["dayLimit"]
        short = "7日榜"
    elif key == "24h":
        default_limit = settings["h24Limit"]
        short = "24小时榜"
    else:
        default_limit = settings["allLimit"]
        short = "总榜"
    n = clamp_limit(limit if limit is not None else default_limit, default_limit)
    return {
        **base,
        "limit": n,
        "label": f"{short}前{n}",
        "shortLabel": short,
    }


def _traders_from_fomo_api(period: str, limit: int) -> list[dict]:
    """Official FOMO leaderboard.

    - all  → GET /v2/leaderboard  (totalPnL)
    - 7d   → GET /v2/leaderboard/7d
    - 24h  → GET /v2/leaderboard/24h
    """
    from fomo_auth import fomo_get, get_access_token

    if not get_access_token():
        raise RuntimeError("未配置 Privy Token，无法调用官方榜单")
    path = "/v2/leaderboard" if period == "all" else f"/v2/leaderboard/{period}"
    data = fomo_get(path, timeout=60)
    status = data.get("statusCode")
    if data.get("error") or status in (401, 403, 430, 431) or data.get("success") is False:
        err = data.get("error") or data.get("message") or f"HTTP {status}"
        raise RuntimeError(f"official leaderboard {period} failed: {err}")
    obj = data.get("responseObject", data)
    rows = []
    if isinstance(obj, dict):
        rows = obj.get("leaderboard") or obj.get("users") or obj.get("items") or []
    elif isinstance(obj, list):
        rows = obj
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"official leaderboard {period}: empty response")

    traders = []
    for i, r in enumerate(rows[:limit]):
        if not isinstance(r, dict):
            continue
        handle = (r.get("userHandle") or r.get("handle") or "").strip()
        name = (r.get("displayName") or r.get("name") or handle).strip()
        uid = (r.get("id") or r.get("userId") or r.get("uid") or "").strip()
        pnl = None
        if period == "7d":
            pnl = r.get("pnl7d")
        elif period == "24h":
            pnl = r.get("pnl24h")
        elif period == "all":
            pnl = r.get("totalPnL") or r.get("totalPnl") or r.get("pnlAllTime")
        else:
            pnl = r.get("pnl")
        if pnl is None:
            pnl = r.get("pnlAllTime") or r.get("totalPnL") or r.get("totalPnl") or r.get("pnl") or 0
        traders.append(
            {
                "rank": int(r.get("rank") or i + 1),
                "handle": handle,
                "name": name,
                "uid": uid,
                "pnl": float(pnl or 0),
                "followers": int(r.get("followers") or 0),
                "numTrades": int(r.get("numTrades") or r.get("swapCount") or 0),
                "source": "fomo-api",
            }
        )
    if not traders:
        raise RuntimeError(f"official leaderboard {period}: no parseable users")
    return traders


def fetch_traders(
    progress: Callable[[str], None] | None = None,
    board: str = "all",
    limit: int | None = None,
) -> list[dict]:
    cfg = resolve_board(board, limit=limit)
    board_key = cfg["boardKey"]
    limit = cfg["limit"]
    if progress:
        progress(f"正在拉取 FOMO {cfg['label']}…")
    traders = _traders_from_fomo_api(board_key, limit)
    if progress:
        progress(f"官方{cfg['shortLabel']}已拉取 {len(traders)} 人")
    return traders


def fetch_top20_traders(progress: Callable[[str], None] | None = None) -> list[dict]:
    return fetch_traders(progress=progress, board="all")


def collect_open_holdings(
    traders: list[dict],
    progress: Callable[[str], None] | None = None,
    mode: str = "fast",
) -> tuple[dict[str, list[dict]], dict[str, dict], dict, dict]:
    """Return token_map, profiles, stats, token_meta_cache.

    Holdings always come from FOMO /v2/users/{userId}/balances.
    """
    from fomo_auth import (
        balances_to_holdings,
        fetch_user_balances,
        get_access_token,
        load_token_meta_cache,
        resolve_user_id,
        save_token_meta_cache,
        upsert_token_meta,
    )

    token_map: dict[str, list[dict]] = defaultdict(list)
    profiles: dict[str, dict] = {}
    token_meta_cache = load_token_meta_cache()
    if not get_access_token():
        raise RuntimeError("需要先登录 FOMO（配置 Token），才能拉取持仓")
    stats = {
        "mode": mode,
        "holdingsSource": "balances",
        "tradersOk": 0,
        "tradersFail": 0,
        "holdingRows": 0,
        "errors": [],
        "tokenMetaUpdated": 0,
    }

    def one(trader: dict):
        return trader, {}

    done = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, t) for t in traders]
        for fut in as_completed(futures):
            trader, profile = fut.result()
            done += 1
            handle = trader["handle"]
            profiles[handle] = profile
            name = trader.get("name") or handle
            if progress:
                progress(f"拉取持仓 {done}/{len(traders)}：{name} (balances)")

            holdings = []
            try:
                user_id = resolve_user_id(
                    handle, known_uid=trader.get("uid") or ""
                )
                if not user_id:
                    raise RuntimeError(f"missing userId for {handle}")
                trader["uid"] = user_id
                bal_rows = fetch_user_balances(user_id)
                holdings = balances_to_holdings(bal_rows)
                for h in holdings:
                    upsert_token_meta(token_meta_cache, h)
                    stats["tokenMetaUpdated"] += 1
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
                        "marketCap": float(h.get("marketCap") or 0),
                        "volume24": float(h.get("volume24") or 0),
                        "change24": h.get("change24"),
                        "priceUsd": float(h.get("priceUsd") or 0),
                        "createdAt": h.get("createdAt") or "",
                        "holdingSince": h.get("holdingSince") or "",
                        "positionUpdatedAt": h.get("positionUpdatedAt") or "",
                        "pnlUsd": h.get("pnlUsd"),
                        "pnlPct": h.get("pnlPct"),
                    }
                )
                stats["holdingRows"] += 1

    save_token_meta_cache(token_meta_cache)
    return token_map, profiles, stats, token_meta_cache


def _apply_meta_to_token_map(token_map: dict[str, list[dict]], holding: dict) -> None:
    key = normalize_addr(holding.get("tokenAddress") or "")
    if not key or key not in token_map:
        return
    for entry in token_map[key]:
        if holding.get("marketCap"):
            entry["marketCap"] = float(holding["marketCap"])
        if holding.get("volume24"):
            entry["volume24"] = float(holding["volume24"])
        if holding.get("change24") not in (None, ""):
            entry["change24"] = holding["change24"]
        if holding.get("priceUsd"):
            entry["priceUsd"] = float(holding["priceUsd"])
        if holding.get("symbol") and not entry.get("symbol"):
            entry["symbol"] = holding["symbol"]
        if holding.get("name") and not entry.get("rawName"):
            entry["rawName"] = holding["name"]
        if holding.get("createdAt") and not entry.get("createdAt"):
            entry["createdAt"] = holding["createdAt"]
        if holding.get("holdingSince") and not entry.get("holdingSince"):
            entry["holdingSince"] = holding["holdingSince"]
        if holding.get("positionUpdatedAt") and not entry.get("positionUpdatedAt"):
            entry["positionUpdatedAt"] = holding["positionUpdatedAt"]
        if holding.get("pnlUsd") is not None and entry.get("pnlUsd") is None:
            entry["pnlUsd"] = holding.get("pnlUsd")
            entry["pnlPct"] = holding.get("pnlPct")


def backfill_missing_token_meta(
    token_map: dict[str, list[dict]],
    token_meta_cache: dict,
    traders: list[dict],
    progress: Callable[[str], None] | None = None,
) -> dict:
    """When auth is available, fetch balances for holders of tokens missing mcap."""
    from fomo_auth import (
        balances_to_holdings,
        fetch_user_balances,
        get_access_token,
        meta_from_cache_or_holding,
        resolve_user_id,
        save_token_meta_cache,
        upsert_token_meta,
    )

    if not get_access_token() or not token_map:
        return token_meta_cache

    missing = []
    for addr, holders in token_map.items():
        meta = meta_from_cache_or_holding(token_meta_cache, addr, holders)
        if float(meta.get("marketCap") or 0) <= 0:
            missing.append(addr)
    if not missing:
        return token_meta_cache

    uid_by_handle = {
        (t.get("handle") or ""): (t.get("uid") or "")
        for t in traders
        if t.get("handle")
    }
    uncovered = set(missing)
    fetch_plan: list[tuple[str, str, list[str]]] = []  # handle, uid, covers

    # Greedy set cover: pick holders that cover most missing tokens
    while uncovered:
        best = None  # (cover_n, has_uid, handle, uid, covers)
        handles = {
            (h.get("handle") or "")
            for addr in uncovered
            for h in (token_map.get(addr) or [])
            if h.get("handle")
        }
        for handle in handles:
            covers = [
                a
                for a in uncovered
                if any((x.get("handle") or "") == handle for x in (token_map.get(a) or []))
            ]
            if not covers:
                continue
            uid = uid_by_handle.get(handle) or ""
            cand = (len(covers), 1 if uid else 0, handle, uid, covers)
            if best is None or cand[:2] > best[:2]:
                best = cand
        if not best:
            break
        _n, _has_uid, handle, uid, covers = best
        if not uid:
            try:
                uid = resolve_user_id(handle)
                if uid:
                    uid_by_handle[handle] = uid
            except Exception:
                uid = ""
        if not uid:
            for a in covers:
                uncovered.discard(a)
            continue
        fetch_plan.append((handle, uid, covers))
        for a in covers:
            uncovered.discard(a)
    if progress and fetch_plan:
        progress(f"补全缺失行情：{len(missing)} 个代币，约 {len(fetch_plan)} 次 balances…")

    for i, (handle, uid, covers) in enumerate(fetch_plan, 1):
        if progress:
            progress(f"补全行情 {i}/{len(fetch_plan)}：{handle}（覆盖 {len(covers)}）")
        try:
            holds = balances_to_holdings(fetch_user_balances(uid))
            for h in holds:
                upsert_token_meta(token_meta_cache, h)
                _apply_meta_to_token_map(token_map, h)
        except Exception as exc:
            if progress:
                progress(f"补全行情失败 {handle}: {exc}")

    save_token_meta_cache(token_meta_cache)
    return token_meta_cache


def aggregate_rows(
    token_map: dict[str, list[dict]],
    token_meta_cache: dict,
    ath_cache: dict,
) -> list[dict]:
    from fomo_auth import meta_from_cache_or_holding

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
        meta = meta_from_cache_or_holding(token_meta_cache, addr, holders)
        current_mcap = float(meta.get("marketCap") or 0)
        volume24 = float(meta.get("volume24") or 0)
        change24 = meta.get("change24")
        created_at = (meta.get("createdAt") or sample.get("createdAt") or "").strip()
        # Keep ATH cache warm (columns removed from table output).
        merge_ath(ath_cache, addr, current_mcap, None, None)

        symbol = (meta.get("symbol") or sample.get("symbol") or "").strip()
        name = (meta.get("name") or sample.get("rawName") or "").strip()
        # Never treat trader nicknames as token names.
        trader_labels = {
            (h.get("name") or "").strip().lower()
            for h in holders
            if h.get("name")
        } | {
            (h.get("handle") or "").strip().lower()
            for h in holders
            if h.get("handle")
        }
        if name.lower() in trader_labels:
            name = ""
        if symbol and name and name.upper() != symbol.upper():
            display = f"{symbol} ({name})"
        else:
            display = symbol or name or (sample.get("symbol") or addr[:10])

        holder_details = [
            fmt_holder_detail_line(
                h["rank"],
                h["name"],
                h["value"],
                current_mcap,
                holding_since=h.get("holdingSince") or "",
                position_updated_at=h.get("positionUpdatedAt") or "",
                pnl_usd=h.get("pnlUsd"),
                pnl_pct=h.get("pnlPct"),
            )
            for h in sorted(holders, key=lambda x: float(x.get("value") or 0), reverse=True)
        ]
        network_id = meta.get("networkId") if meta.get("networkId") is not None else sample.get("networkId")
        platform = infer_platform(addr, network_id, meta)
        row = {
            "名称": display,
            "市值": current_mcap if current_mcap else "",
            "成交量": volume24 if volume24 else "",
            "24h涨跌": change24 if change24 not in (None, "") else "",
            "持仓人数": count,
            "持仓市值": total,
            "持仓盈亏": sum_holder_pnl_usd(holders),
            "人均持仓市值": avg,
            "创建时间": created_at or "",
            "最高持仓人": f"{hi['rank']}.{hi['name']}",
            "最高持仓市值": hi["value"],
            "最低持仓人": f"{lo['rank']}.{lo['name']}",
            "最低持仓市值": lo["value"],
            "所有持仓人": "\n".join(holder_details),
            "持仓明细": holder_details,
            "发射平台": platform,
            "合约地址": addr,
            "debotChain": debot_chain(addr, platform, network_id=network_id),
        }
        normalize_row_display(row)
        rows.append(row)

    def sort_key(r):
        from update_token_marketcap import parse_number

        return parse_number(r.get("持仓市值")) or 0

    rows.sort(key=sort_key, reverse=True)
    return rows


def persist_outputs(
    traders: list[dict],
    rows: list[dict],
    meta: dict,
    board: str = "all",
) -> None:
    import csv as _csv

    cfg = resolve_board(board)
    fieldnames = list(CSV_COLUMNS)
    csv_path = cfg["csvPath"]
    json_path = cfg["jsonPath"]
    md_path = cfg["mdPath"]
    last_path = cfg["lastResult"]
    errors: list[str] = []

    try:
        tmp = csv_path.with_suffix(csv_path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        try:
            tmp.replace(csv_path)
        except OSError:
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
    except OSError as exc:
        errors.append(f"csv: {exc}")

    try:
        lines = [
            f"# FOMO {cfg['label']} 持仓汇总",
            "",
            f"> 市值更新时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "| " + " | ".join(fieldnames) + " |",
            "| " + " | ".join(["---"] * len(fieldnames)) + " |",
        ]
        for row in rows:
            cells = [
                str(row.get(h, "")).replace("|", "\\|").replace("\n", " ")
                for h in fieldnames
            ]
            lines.append("| " + " | ".join(cells) + " |")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        errors.append(f"md: {exc}")

    payload = {
        "generatedAt": meta.get("updatedAt"),
        "marketCapUpdatedAt": meta.get("updatedAt"),
        "board": cfg["boardKey"],
        "boardLabel": cfg["label"],
        "source": meta.get("source") or "FOMO API balances",
        "limitation": meta.get("limitation")
        or "持仓与行情均来自 FOMO balances（需登录）。",
        "mode": meta.get("mode") or "fast",
        "stats": meta.get("stats") or {},
        "traders": traders,
        "tokenCount": len(rows),
        "columns": list(CSV_COLUMNS),
        "rows": rows,
        "tokens": rows,
        "note": meta.get("note") or "",
    }
    for path in (json_path, last_path):
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            errors.append(f"{path.name}: {exc}")
    if errors:
        meta["persistWarnings"] = errors


CACHE_FRESH_SEC = DEFAULT_SETTINGS["refreshMinutes"] * 60


def cache_fresh_sec() -> int:
    return load_settings()["refreshMinutes"] * 60


def is_cache_fresh(cached: dict | None, *, now: datetime | None = None, max_age_sec: int = CACHE_FRESH_SEC) -> bool:
    """True when this board was pulled recently enough to skip another fetch."""
    if not cached:
        return False
    rows = cached.get("rows") or cached.get("tokens") or []
    if not rows:
        return False
    raw = cached.get("generatedAt") or cached.get("updatedAt") or cached.get("marketCapUpdatedAt") or ""
    if not raw:
        return False
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (current - ts) <= timedelta(seconds=max_age_sec)


_CACHE_MEM: dict[str, tuple[float, dict]] = {}


def load_cached_result(board: str = "all") -> dict | None:
    cfg = resolve_board(board)
    path = cfg["lastResult"] if cfg["lastResult"].exists() else cfg["jsonPath"]
    if not path.exists():
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    key = str(path)
    hit = _CACHE_MEM.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        from update_token_marketcap import CSV_COLUMNS, rename_legacy_row

        data = json.loads(path.read_text(encoding="utf-8"))
        for field in ("rows", "tokens"):
            if field in data and isinstance(data[field], list):
                data[field] = [rename_legacy_row(r) for r in data[field]]
        data["columns"] = list(CSV_COLUMNS)
        data.setdefault("board", cfg["boardKey"])
        data.setdefault("boardLabel", cfg["label"])
        _CACHE_MEM[key] = (mtime, data)
        return data
    except Exception:
        return None


def run_pipeline(
    progress: Callable[[str], None] | None = None,
    mode: str = "fast",
    board: str = "all",
    limit: int | None = None,
) -> dict:
    started = time.time()
    mode = "full" if mode == "full" else "fast"
    cfg = resolve_board(board, limit=limit)
    traders = fetch_traders(progress, board=cfg["boardKey"], limit=cfg["limit"])
    token_map, _profiles, stats, token_meta_cache = collect_open_holdings(
        traders, progress, mode=mode
    )

    from fomo_auth import get_access_token

    if get_access_token():
        token_meta_cache = backfill_missing_token_meta(
            token_map, token_meta_cache, traders, progress=progress
        )

    if progress:
        progress("已用 FOMO balances 更新代币市值/成交量/涨跌缓存…")

    if progress:
        progress("合并最高市值缓存…")
    ath_cache = load_cache()
    rows = aggregate_rows(token_map, token_meta_cache, ath_cache)
    save_cache(ath_cache)

    updated_at = datetime.now(timezone.utc).isoformat()
    source = f"FOMO {cfg['label']} balances (实时开仓+行情)"
    limitation = (
        f"{'全量' if mode == 'full' else '快速'}·{cfg['label']}：持仓来自 Privy balances；"
        "市值/成交量/24h涨跌来自 tokenFilterResult（已缓存）。"
    )
    note = (
        f"{'全量' if mode == 'full' else '快速'} · {cfg['label']}："
        "持仓与行情均来自 FOMO balances（实时开仓）。"
    )
    src = (traders[0].get("source") if traders else "") or ""
    if cfg["boardKey"] in ("all", "7d", "24h"):
        api_path = (
            "/v2/leaderboard"
            if cfg["boardKey"] == "all"
            else f"/v2/leaderboard/{cfg['boardKey']}"
        )
        if src == "fomo-api":
            note += f" 榜单来自官方 {api_path}（{len(traders)}人）。"
        elif len(traders) < cfg["limit"]:
            limitation += f" 数据源当前仅返回 {len(traders)} 名交易员（目标前{cfg['limit']}）。"
            note += f" 当前源提供 {len(traders)}/{cfg['limit']} 名交易员。"

    result = {
        "updatedAt": updated_at,
        "elapsedSec": round(time.time() - started, 1),
        "mode": mode,
        "board": cfg["boardKey"],
        "boardLabel": cfg["label"],
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
    persist_outputs(traders, rows, result, board=cfg["boardKey"])
    if progress:
        progress(f"完成，共 {len(rows)} 个代币，用时 {result['elapsedSec']}s")
    return result


def run_fast_pipeline(progress: Callable[[str], None] | None = None) -> dict:
    return run_pipeline(progress=progress, mode="fast", board="all")


def run_full_pipeline(progress: Callable[[str], None] | None = None) -> dict:
    return run_pipeline(progress=progress, mode="full", board="all")
