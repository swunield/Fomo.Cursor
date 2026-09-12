# -*- coding: utf-8 -*-
"""Update token market cap columns in fomo_top20_holdings_by_token.csv."""
import csv
import http.client
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
CSV_PATH = OUT / "fomo_top20_holdings_by_token.csv"
JSON_PATH = OUT / "fomo_top20_holdings_by_token.json"
MD_PATH = OUT / "fomo_top20_holdings_by_token.md"
CACHE_PATH = OUT / "fomo_mcap_ath_cache.json"
LIVE_MCAP_CACHE_PATH = OUT / "fomo_mcap_live_cache.json"
# Per-token DexScreener 市值最小拉取间隔
LIVE_MCAP_MIN_INTERVAL_SEC = 10 * 60

MCAP_COLS = ("市值", "成交量", "24h涨跌", "创建时间")
# Canonical CSV / Markdown / JSON display column order (user-defined).
CSV_COLUMNS = (
    "名称",
    "市值",
    "成交量",
    "天数",
    "24h涨跌",
    "持仓市值",
    "持仓人数",
    "人均持仓市值",
    "创建时间",
    "最高持仓人",
    "最高持仓市值",
    "最低持仓人",
    "最低持仓市值",
    "所有持仓人",
    "发射平台",
    "合约地址",
)
# Old → new (read legacy files without dropping columns).
LEGACY_COL_RENAME = {
    "代币名称": "名称",
    "代币当前市值": "市值",
    "总持仓价值": "持仓市值",
    "持仓价值": "持仓市值",
    "总持仓人数": "持仓人数",
    "人均持仓价值": "人均持仓市值",
    "代币最高市值": "最高市值",
    "代币最高市值时间": "最高市值时间",
    "最高持仓价值": "最高持仓市值",
    "最低持仓价值": "最低持仓市值",
}
VALUE_COLS = (
    "人均持仓市值",
    "市值",
    "成交量",
)
HOLDING_VALUE_COLS = ("持仓市值", "最高持仓市值", "最低持仓市值")
CHANGE_COLS = ("24h涨跌",)
HOLDER_COLS = ("所有持仓人", "最高持仓人", "最低持仓人")
GECKO_NETWORKS = {
    "solana": "solana",
    "bsc": "bsc",
    "base": "base",
    "ethereum": "eth",
    "eth": "eth",
    "arbitrum": "arbitrum",
    "polygon": "polygon_pos",
    "avax": "avax",
}
GECKO_MIN_INTERVAL = 2.5
GECKO_MAX_RETRIES = 3

ctx = ssl.create_default_context()
_last_gecko_call = 0.0


def get_json(url, data=None, headers=None, timeout=40, retries=2):
    h = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except (TimeoutError, urllib.error.URLError, http.client.IncompleteRead, OSError) as exc:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise


def gecko_throttle():
    global _last_gecko_call
    wait = GECKO_MIN_INTERVAL - (time.time() - _last_gecko_call)
    if wait > 0:
        time.sleep(wait)
    _last_gecko_call = time.time()


def load_cache():
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    cache["updatedAt"] = datetime.now(timezone.utc).isoformat()
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def load_live_mcap_cache():
    if LIVE_MCAP_CACHE_PATH.exists():
        try:
            with open(LIVE_MCAP_CACHE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def save_live_mcap_cache(cache):
    cache["updatedAt"] = datetime.now(timezone.utc).isoformat()
    with open(LIVE_MCAP_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _live_cache_age_sec(entry) -> float | None:
    if not isinstance(entry, dict):
        return None
    fetched = entry.get("fetchedAt")
    if not fetched:
        return None
    try:
        if isinstance(fetched, (int, float)):
            return max(0.0, time.time() - float(fetched))
        ts = datetime.fromisoformat(str(fetched).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
    except Exception:
        return None


def live_mcap_from_cache_entry(entry: dict) -> dict:
    """Strip cache metadata; return DexScreener-shaped meta dict."""
    skip = {"fetchedAt", "cachedAt", "source"}
    return {k: v for k, v in entry.items() if k not in skip}


def normalize_addr(addr):
    addr = (addr or "").strip()
    if addr.startswith("0x"):
        return addr.lower()
    return addr


def store_dex_pair(result, pair, wanted=None):
    base = normalize_addr((pair.get("baseToken") or {}).get("address"))
    quote = normalize_addr((pair.get("quoteToken") or {}).get("address"))
    if wanted:
        wanted_key = normalize_addr(wanted)
        if wanted_key != base:
            return
        token = wanted_key
    else:
        token = base
    if not token:
        return
    liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
    prev = result.get(token)
    if prev and liquidity <= prev["liquidityUsd"]:
        return
    # Prefer FDV when DexScreener circulating is incomplete; pump.fun full-mint
    # FDV mistakes are corrected later via GeckoTerminal.
    circ = float(pair.get("marketCap") or 0)
    fdv = float(pair.get("fdv") or 0)
    mcap = fdv or circ
    price = float(pair.get("priceUsd") or 0)
    base_tok = pair.get("baseToken") or {}
    result[token] = {
        "marketCap": mcap,
        "circulatingMarketCap": circ,
        "fdv": fdv,
        "priceUsd": price,
        "chainId": pair.get("chainId") or "",
        "liquidityUsd": liquidity,
        "pairAddress": pair.get("pairAddress") or "",
        "url": pair.get("url") or "",
        "name": base_tok.get("name") or "",
        "symbol": base_tok.get("symbol") or "",
        "dexId": pair.get("dexId") or "",
    }


def fetch_gecko_token_mcap(network: str, address: str):
    """Return (market_cap_usd, fdv_usd, price_usd) from GeckoTerminal token endpoint."""
    if not network or not address:
        return None, None, None
    gecko_throttle()
    data = get_json(
        f"https://api.geckoterminal.com/api/v2/networks/{network}/tokens/{address}",
        retries=GECKO_MAX_RETRIES,
    )
    attrs = (data.get("data") or {}).get("attributes") or {}

    def _f(key):
        try:
            v = float(attrs.get(key) or 0)
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None

    return _f("market_cap_usd"), _f("fdv_usd"), _f("price_usd")


def needs_gecko_mcap_correction(addr: str, meta: dict | None) -> bool:
    """DexScreener often quotes pump.fun with full 1B mint; FOMO uses circulating."""
    if not meta:
        return False
    if meta.get("mcapSource") == "geckoterminal":
        return False
    addr = addr or ""
    if addr.endswith("pump"):
        return True
    try:
        price = float(meta.get("priceUsd") or 0)
        mcap = float(meta.get("marketCap") or 0)
    except (TypeError, ValueError):
        return False
    if price <= 0 or mcap <= 0:
        return False
    implied = mcap / price
    return implied >= 400_000_000 and mcap >= 1_000_000


def apply_gecko_mcap_correction(addr: str, meta: dict) -> dict:
    network = infer_gecko_network(meta.get("chainId") or "", "")
    if not network and (addr or "").endswith("pump"):
        network = "solana"
    if not network:
        return meta
    try:
        gecko_mcap, gecko_fdv, gecko_price = fetch_gecko_token_mcap(network, addr)
    except Exception as exc:
        print(f"Gecko mcap failed for {addr[:12]}...: {exc}")
        return meta
    chosen = gecko_mcap or gecko_fdv
    if not chosen:
        return meta
    out = dict(meta)
    out["dexscreenerMarketCap"] = meta.get("marketCap")
    out["marketCap"] = chosen
    if gecko_mcap:
        out["circulatingMarketCap"] = gecko_mcap
    if gecko_fdv:
        out["fdv"] = gecko_fdv
    if gecko_price:
        out["priceUsd"] = gecko_price
    out["mcapSource"] = "geckoterminal"
    return out



def fetch_dexscreener(addresses, min_interval_sec: int | None = None, use_cache: bool = True):
    """Fetch current mcap/meta from DexScreener with per-token local cache.

    Tokens fetched within ``min_interval_sec`` (default 10 minutes) are served
    from ``fomo_mcap_live_cache.json`` and not requested again.
    """
    if min_interval_sec is None:
        min_interval_sec = LIVE_MCAP_MIN_INTERVAL_SEC

    result = {}
    unique = []
    seen = set()
    for addr in addresses:
        key = normalize_addr(addr)
        if key and key not in seen:
            seen.add(key)
            unique.append(addr.strip())

    live_cache = load_live_mcap_cache() if use_cache else {}
    to_fetch = []
    cache_hits = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for addr in unique:
        key = normalize_addr(addr)
        entry = live_cache.get(key)
        age = _live_cache_age_sec(entry) if use_cache else None
        if (
            use_cache
            and isinstance(entry, dict)
            and entry.get("marketCap") is not None
            and age is not None
            and age < min_interval_sec
            and (
                entry.get("mcapSource") == "geckoterminal"
                or not needs_gecko_mcap_correction(addr, entry)
            )
        ):
            result[key] = live_mcap_from_cache_entry(entry)
            cache_hits += 1
        else:
            to_fetch.append(addr)

    if cache_hits or to_fetch:
        print(
            f"DexScreener: cache hit {cache_hits}, fetch {len(to_fetch)} "
            f"(min interval {min_interval_sec // 60}m)"
        )

    for i in range(0, len(to_fetch), 30):
        batch = to_fetch[i : i + 30]
        url = "https://api.dexscreener.com/latest/dex/tokens/" + ",".join(batch)
        try:
            data = get_json(url)
        except Exception as exc:
            print(f"DexScreener batch failed: {exc}")
            continue
        for pair in data.get("pairs") or []:
            for addr in batch:
                store_dex_pair(result, pair, wanted=addr)
        time.sleep(0.25)

    missing = [addr for addr in to_fetch if normalize_addr(addr) not in result]
    for addr in missing:
        try:
            data = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{addr}")
            for pair in data.get("pairs") or []:
                store_dex_pair(result, pair, wanted=addr)
        except Exception as exc:
            print(f"DexScreener fallback failed for {addr[:12]}...: {exc}")
        time.sleep(0.2)

    gecko_fixed = 0
    for addr in to_fetch:
        key = normalize_addr(addr)
        meta = result.get(key)
        if not meta:
            continue
        if needs_gecko_mcap_correction(addr, meta):
            fixed = apply_gecko_mcap_correction(addr, meta)
            if fixed.get("mcapSource") == "geckoterminal":
                gecko_fixed += 1
            result[key] = fixed
    if gecko_fixed:
        print(f"GeckoTerminal mcap corrections: {gecko_fixed}")

    if use_cache:
        for addr in to_fetch:
            key = normalize_addr(addr)
            meta = result.get(key)
            if not meta:
                continue
            live_cache[key] = {
                **meta,
                "fetchedAt": now_iso,
                "source": meta.get("mcapSource") or "dexscreener",
            }
        save_live_mcap_cache(live_cache)

    return result


def infer_gecko_network(chain_id, platform):
    chain_id = (chain_id or "").lower()
    if chain_id in GECKO_NETWORKS:
        return GECKO_NETWORKS[chain_id]
    platform = (platform or "").lower()
    if "solana" in platform or "pump" in platform or "bonk" in platform:
        return "solana"
    if "bsc" in platform:
        return "bsc"
    if "base" in platform:
        return "base"
    return None


def fetch_gecko_ath(network, address, current_mcap, current_price):
    if not network or not current_price or current_price <= 0:
        return None, None
    gecko_throttle()
    try:
        pools = get_json(
            f"https://api.geckoterminal.com/api/v2/networks/{network}/tokens/{address}/pools?page=1",
            retries=GECKO_MAX_RETRIES,
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, None
        raise

    pool_rows = pools.get("data") or []
    if not pool_rows:
        return None, None
    pool = pool_rows[0]["attributes"]["address"]

    gecko_throttle()
    ohlcv = get_json(
        f"https://api.geckoterminal.com/api/v2/networks/{network}/pools/{pool}/ohlcv/day?aggregate=1&limit=1000",
        retries=GECKO_MAX_RETRIES,
    )
    rows = (ohlcv.get("data") or {}).get("attributes", {}).get("ohlcv_list") or []
    if not rows:
        return None, None

    highs = [float(row[2]) for row in rows if float(row[2]) > 0]
    if not highs:
        return None, None

    highs.sort()
    median_high = highs[len(highs) // 2]
    max_allowed_high = max(median_high * 8, current_price * 5)
    valid_rows = [row for row in rows if 0 < float(row[2]) <= max_allowed_high]
    if not valid_rows:
        valid_rows = [row for row in rows if float(row[2]) > 0]

    supply_factor = current_mcap / current_price
    best_mcap = 0.0
    best_ts = None
    for ts, _open, high, _low, _close, _vol in valid_rows:
        mcap = float(high) * supply_factor
        if mcap > best_mcap:
            best_mcap = mcap
            best_ts = int(ts)
    if best_mcap <= 0:
        return None, None
    if current_mcap > 0 and best_mcap > current_mcap * 50:
        return None, None
    return best_mcap, best_ts


def merge_ath(cache, address, current_mcap, gecko_ath_mcap, gecko_ath_ts):
    key = normalize_addr(address)
    now_iso = datetime.now(timezone.utc).isoformat()
    entry = cache.get(key, {})

    candidates = []
    if current_mcap and current_mcap > 0:
        candidates.append((current_mcap, now_iso))
    if gecko_ath_mcap and gecko_ath_mcap > 0:
        ts_iso = (
            datetime.fromtimestamp(gecko_ath_ts, tz=timezone.utc).isoformat()
            if gecko_ath_ts
            else now_iso
        )
        candidates.append((gecko_ath_mcap, ts_iso))
    if entry.get("athMarketCap"):
        cached_ath = float(entry["athMarketCap"])
        cache_ok = current_mcap <= 0 or cached_ath <= current_mcap * 10
        if gecko_ath_mcap:
            cache_ok = cache_ok or cached_ath <= current_mcap * 50
        if cache_ok:
            candidates.append((cached_ath, entry.get("athMarketCapTime") or now_iso))

    if not candidates:
        return None, None

    best = max(candidates, key=lambda item: item[0])
    if current_mcap > 0 and best[0] > current_mcap * 50:
        best = (current_mcap, now_iso)
    cache[key] = {
        "athMarketCap": best[0],
        "athMarketCapTime": best[1],
        "lastCurrentMarketCap": current_mcap,
        "lastUpdated": now_iso,
        "source": entry.get("source") or "dexscreener+gecko+cache",
    }
    return best[0], best[1]


def parse_number(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("$", "").replace(",", "").replace(" ", "")
    if not text or text == "-":
        return None
    # strip trailing "(pct)" if present: 12.1M(2.4%) / 6.3M(-) -> 12.1M / 6.3M
    text = re.sub(r"\([^)]*\)$", "", text)
    multiplier = 1.0
    upper = text.upper()
    if upper.endswith("B"):
        multiplier = 1e9
        text = text[:-1]
    elif upper.endswith("M"):
        multiplier = 1e6
        text = text[:-1]
    elif upper.endswith("K"):
        multiplier = 1e3
        text = text[:-1]
    try:
        return float(text) * multiplier
    except (TypeError, ValueError):
        return None


def fmt_km(value):
    num = parse_number(value)
    if num is None:
        return "" if value in (None, "") else str(value)
    sign = "-" if num < 0 else ""
    n = abs(num)
    if n >= 1_000_000:
        return f"{sign}{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{sign}{int(round(n / 1e3))}K"
    return f"{sign}{int(round(n))}"


def fmt_change24(value):
    """Format FOMO change24 (ratio or percent) as +12.34% / -5.67%."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            return text
        try:
            num = float(text)
        except ValueError:
            return text
    else:
        try:
            num = float(value)
        except (TypeError, ValueError):
            return str(value)
    # FOMO tokenFilterResult.change24 is typically a ratio like -0.21
    if abs(num) <= 1.5:
        num *= 100.0
    return f"{num:+.2f}%"


def fmt_holding_with_mcap_pct(holding_value, market_cap):
    holding = parse_number(holding_value)
    if holding is None:
        return "" if holding_value in (None, "") else str(holding_value)
    value_text = fmt_km(holding)
    mcap = parse_number(market_cap)
    if not mcap or mcap <= 0:
        return f"{value_text}(-)"
    pct = holding / mcap * 100
    if pct >= 10:
        pct_text = f"{pct:.1f}%"
    elif pct >= 1:
        pct_text = f"{pct:.2f}%"
    else:
        pct_text = f"{pct:.3f}%"
    return f"{value_text}({pct_text})"


def fmt_signed_km(value):
    num = parse_number(value)
    if num is None:
        return ""
    text = fmt_km(num)
    if num > 0 and text and not text.startswith("+"):
        return f"+{text}"
    return text


def fmt_pnl_with_pct(pnl_usd, pnl_pct) -> str:
    """Format open PnL as '+1.2M(+23.45%)' / '-500K(-12.30%)'."""
    if pnl_usd is None or pnl_usd == "":
        return ""
    try:
        pnl_usd = float(pnl_usd)
    except (TypeError, ValueError):
        return ""
    amt = fmt_signed_km(pnl_usd)
    if not amt:
        return ""
    if pnl_pct is None or pnl_pct == "":
        return amt
    try:
        pct = float(pnl_pct)
    except (TypeError, ValueError):
        return amt
    return f"{amt}({pct:+.2f}%)"


def _parse_dt(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            ts = float(text)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def fmt_hold_duration(since_value, now=None) -> str:
    """Holding duration as '[DD:HH:MM]' (zero-padded)."""
    start = _parse_dt(since_value)
    if not start:
        return ""
    end = now or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    secs = int((end - start.astimezone(timezone.utc)).total_seconds())
    if secs < 0:
        secs = 0
    days = secs // 86400
    hours = (secs % 86400) // 3600
    mins = (secs % 3600) // 60
    return f"[{days:02d}:{hours:02d}:{mins:02d}]"


def fmt_position_updated_at(value) -> str:
    """Local time as 'YYYYMMDD HH:MM' (Asia/Shanghai)."""
    dt = _parse_dt(value)
    if not dt:
        return ""
    try:
        from zoneinfo import ZoneInfo

        local = dt.astimezone(ZoneInfo("Asia/Shanghai"))
    except Exception:
        local = dt.astimezone(timezone(timedelta(hours=8)))
    return local.strftime("%Y%m%d %H:%M")


def fmt_created_at_local(value) -> str:
    """Display createdAt as 'YYYY-MM-DD HH:mm:ss' in Asia/Shanghai."""
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if (
        len(text) >= 19
        and text[10] == " "
        and "T" not in text
        and "+" not in text
        and "Z" not in text.upper()
    ):
        return text[:19]
    dt = _parse_dt(value)
    if not dt:
        return text
    try:
        from zoneinfo import ZoneInfo

        local = dt.astimezone(ZoneInfo("Asia/Shanghai"))
    except Exception:
        local = dt.astimezone(timezone(timedelta(hours=8)))
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _created_at_dt(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if (
        len(text) >= 19
        and text[10] == " "
        and "T" not in text
        and "+" not in text
        and "Z" not in text.upper()
    ):
        naive = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        try:
            from zoneinfo import ZoneInfo

            return naive.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        except Exception:
            return naive.replace(tzinfo=timezone(timedelta(hours=8)))
    return _parse_dt(value)


def fmt_token_age_days(value, now=None) -> str:
    """Token age in days from createdAt, one decimal place."""
    dt = _created_at_dt(value)
    if not dt:
        return ""
    end = now or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    secs = (end - dt.astimezone(timezone.utc)).total_seconds()
    if secs < 0:
        secs = 0
    return f"{secs / 86400.0:.1f}"


def fmt_holder_detail_line(
    rank,
    name,
    holding_value,
    market_cap,
    holding_since="",
    position_updated_at="",
    pnl_usd=None,
    pnl_pct=None,
) -> str:
    base = f"{rank}.{name} {fmt_holding_with_mcap_pct(holding_value, market_cap)}"
    parts = [base]
    pnl = fmt_pnl_with_pct(pnl_usd, pnl_pct)
    if pnl:
        parts.append(pnl)
    dur = fmt_hold_duration(holding_since)
    if dur:
        parts.append(dur)
    upd = fmt_position_updated_at(position_updated_at)
    if upd:
        parts.append(f"[{upd}]")
    return " ".join(parts)


def parse_holders(text):
    items = []
    for rank, name in re.findall(r"(\d+)\.(.+?)(?=\s+\d+\.|$)", str(text or "").strip()):
        items.append((int(rank), name.strip()))
    return items


def holder_label(value, holders):
    text = str(value or "").strip()
    if not text:
        return ""
    if re.match(r"^\d+\.", text):
        return text
    by_name = {name: f"{rank}.{name}" for rank, name in holders}
    return by_name.get(text, text)


def parse_holder_detail_line(line: str):
    """Parse '1.Name 6.2M(1.57%) …' -> (rank, name, value_text, suffix) or None."""
    text = str(line or "").strip()
    m = re.match(r"^(\d+)\.(.+?)\s+(\S+\([^)]*\))(?:\s+(.*))?$", text)
    if not m:
        return None
    return (
        int(m.group(1)),
        m.group(2).strip(),
        m.group(3).strip(),
        (m.group(4) or "").strip(),
    )


def normalize_row_display(row, now=None):
    details = row.get("持仓明细")
    if isinstance(details, str) and details.strip():
        details = [ln.strip() for ln in details.splitlines() if ln.strip()]
        row["持仓明细"] = details

    if isinstance(details, list) and details:
        cleaned = []
        name_labels = []
        for line in details:
            parsed = parse_holder_detail_line(line)
            if parsed:
                rank, name, val, suffix = parsed
                extra = f" {suffix}" if suffix else ""
                cleaned.append(f"{rank}.{name} {val}{extra}")
                name_labels.append(f"{rank}.{name}")
            else:
                # already 'rank.name' only
                cleaned.append(str(line).strip())
                name_labels.append(str(line).strip())
        row["持仓明细"] = cleaned
        # Persist rich lines in 所有持仓人 so tips survive even if 持仓明细 is dropped
        row["所有持仓人"] = "\n".join(cleaned)
        holders = []
        for line in cleaned:
            parsed = parse_holder_detail_line(line)
            if parsed:
                holders.append((parsed[0], parsed[1]))
        if not holders:
            holders = parse_holders(" ".join(name_labels))
        if holders:
            row["最高持仓人"] = holder_label(row.get("最高持仓人"), holders)
            row["最低持仓人"] = holder_label(row.get("最低持仓人"), holders)
    else:
        raw_all = str(row.get("所有持仓人") or "")
        if "\n" in raw_all and "(" in raw_all:
            lines = [ln.strip() for ln in raw_all.splitlines() if ln.strip()]
            row["持仓明细"] = lines
            row["所有持仓人"] = "\n".join(lines)
            holders = []
            for line in lines:
                parsed = parse_holder_detail_line(line)
                if parsed:
                    holders.append((parsed[0], parsed[1]))
            if holders:
                row["最高持仓人"] = holder_label(row.get("最高持仓人"), holders)
                row["最低持仓人"] = holder_label(row.get("最低持仓人"), holders)
        else:
            holders = parse_holders(raw_all)
            if holders:
                row["所有持仓人"] = " ".join(f"{rank}.{name}" for rank, name in holders)
                row["最高持仓人"] = holder_label(row.get("最高持仓人"), holders)
                row["最低持仓人"] = holder_label(row.get("最低持仓人"), holders)

    for col in VALUE_COLS:
        if col in row:
            row[col] = fmt_km(row.get(col))
    for col in CHANGE_COLS:
        if col in row:
            row[col] = fmt_change24(row.get(col))
    mcap = row.get("市值")
    for col in HOLDING_VALUE_COLS:
        if col in row:
            row[col] = fmt_holding_with_mcap_pct(row.get(col), mcap)
    created_raw = row.get("创建时间")
    if "创建时间" in row:
        row["创建时间"] = fmt_created_at_local(created_raw)
    row["天数"] = fmt_token_age_days(created_raw, now=now)
    return row


def rename_legacy_row(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        out[LEGACY_COL_RENAME.get(k, k)] = v
    return out


def read_csv_rows():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        return [rename_legacy_row(r) for r in csv.DictReader(f)]


def ordered_fieldnames(rows):
    present = []
    seen = set()
    for col in CSV_COLUMNS:
        if any(col in row for row in rows):
            present.append(col)
            seen.add(col)
    for row in rows:
        for col in row.keys():
            if col not in seen:
                present.append(col)
                seen.add(col)
    return present


def write_csv_rows(fieldnames, rows):
    tmp = CSV_PATH.with_suffix(".csv.tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    try:
        tmp.replace(CSV_PATH)
    except OSError:
        # File may be locked by Excel/IDE; keep .tmp and also try direct write
        with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def write_markdown(rows):
    headers = ordered_fieldnames(rows) if rows else list(CSV_COLUMNS)
    lines = [
        "# FOMO Top20 持仓代币汇总",
        "",
        f"> 市值更新时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        cells = []
        for h in headers:
            val = str(row.get(h, "")).replace("|", "\\|").replace("\n", " ")
            cells.append(val)
        lines.append("| " + " | ".join(cells) + " |")
    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_json(rows):
    payload = {}
    if JSON_PATH.exists():
        with open(JSON_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    payload["marketCapUpdatedAt"] = datetime.now(timezone.utc).isoformat()
    payload["tokens"] = rows
    if "rows" in payload:
        payload["rows"] = rows
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    if not CSV_PATH.exists():
        raise SystemExit(f"CSV not found: {CSV_PATH}")

    rows = read_csv_rows()
    if not rows:
        raise SystemExit("CSV is empty")

    fieldnames = ordered_fieldnames(rows)
    for row in rows:
        for col in CSV_COLUMNS:
            row.setdefault(col, "")

    addresses = [row.get("合约地址", "") for row in rows]
    dex_data = fetch_dexscreener(addresses)
    cache = load_cache()

    print(f"Loaded {len(rows)} tokens, DexScreener matched {len(dex_data)}")
    for idx, row in enumerate(rows, 1):
        addr = row.get("合约地址", "")
        key = normalize_addr(addr)
        meta = dex_data.get(key, {})
        current_mcap = meta.get("marketCap") or 0.0
        current_price = meta.get("priceUsd") or 0.0
        chain_id = meta.get("chainId") or ""
        platform = row.get("发射平台", "")

        gecko_network = infer_gecko_network(chain_id, platform)
        gecko_ath_mcap, gecko_ath_ts = None, None
        if gecko_network:
            try:
                gecko_ath_mcap, gecko_ath_ts = fetch_gecko_ath(
                    gecko_network, addr, current_mcap, current_price
                )
            except Exception as exc:
                print(f"  [{idx}] Gecko ATH failed for {addr[:12]}...: {exc}")

        ath_mcap, ath_time = merge_ath(cache, addr, current_mcap, gecko_ath_mcap, gecko_ath_ts)

        row["市值"] = fmt_km(current_mcap) if current_mcap else ""
        row["最高市值"] = fmt_km(ath_mcap) if ath_mcap else ""
        row["最高市值时间"] = ath_time or ""
        normalize_row_display(row)

        name = row.get("名称", addr[:10])
        print(
            f"  [{idx:02d}] {name[:24]:<24} "
            f"当前 {row.get('市值') or '-':>10} "
            f"最高 {row.get('最高市值') or '-':>10}"
        )

    save_cache(cache)
    write_csv_rows(fieldnames, rows)
    write_markdown(rows)
    update_json(rows)

    print()
    print(f"Updated: {CSV_PATH.name}")
    print(f"Cache:   {CACHE_PATH.name}")
    print(f"Also refreshed: {JSON_PATH.name}, {MD_PATH.name}")


if __name__ == "__main__":
    main()
