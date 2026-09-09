# -*- coding: utf-8 -*-
"""Update token market cap columns in fomo_top20_holdings_by_token.csv."""
import csv
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
CSV_PATH = OUT / "fomo_top20_holdings_by_token.csv"
JSON_PATH = OUT / "fomo_top20_holdings_by_token.json"
MD_PATH = OUT / "fomo_top20_holdings_by_token.md"
CACHE_PATH = OUT / "fomo_mcap_ath_cache.json"

MCAP_COLS = ("代币当前市值", "代币最高市值", "代币最高市值时间")
# Canonical CSV / Markdown / JSON display column order (user-defined).
CSV_COLUMNS = (
    "代币名称",
    "代币当前市值",
    "总持仓价值",
    "总持仓人数",
    "人均持仓价值",
    "代币最高市值",
    "代币最高市值时间",
    "最高持仓人",
    "最高持仓价值",
    "最低持仓人",
    "最低持仓价值",
    "所有持仓人",
    "发射平台",
    "合约地址",
)
VALUE_COLS = (
    "总持仓价值",
    "人均持仓价值",
    "代币当前市值",
    "代币最高市值",
)
HOLDING_VALUE_COLS = ("最高持仓价值", "最低持仓价值")
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
    # Meme/FOMO desks usually quote FDV as 市值 (e.g. BUN: mcap~5M vs fdv~18M).
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


def fetch_dexscreener(addresses):
    result = {}
    unique = []
    seen = set()
    for addr in addresses:
        key = normalize_addr(addr)
        if key and key not in seen:
            seen.add(key)
            unique.append(addr.strip())

    for i in range(0, len(unique), 30):
        batch = unique[i : i + 30]
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

    missing = [addr for addr in unique if normalize_addr(addr) not in result]
    for addr in missing:
        try:
            data = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{addr}")
            for pair in data.get("pairs") or []:
                store_dex_pair(result, pair, wanted=addr)
        except Exception as exc:
            print(f"DexScreener fallback failed for {addr[:12]}...: {exc}")
        time.sleep(0.2)
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
    # strip trailing "(x%)" if present: 12.1M(2.4%) -> 12.1M
    text = re.sub(r"\([^)]*%\)$", "", text)
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


def normalize_row_display(row):
    holders = parse_holders(row.get("所有持仓人", ""))
    if holders:
        row["所有持仓人"] = " ".join(f"{rank}.{name}" for rank, name in holders)
        row["最高持仓人"] = holder_label(row.get("最高持仓人"), holders)
        row["最低持仓人"] = holder_label(row.get("最低持仓人"), holders)
    for col in VALUE_COLS:
        if col in row:
            row[col] = fmt_km(row.get(col))
    mcap = row.get("代币当前市值")
    for col in HOLDING_VALUE_COLS:
        if col in row:
            row[col] = fmt_holding_with_mcap_pct(row.get(col), mcap)
    return row


def read_csv_rows():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


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

        row["代币当前市值"] = fmt_km(current_mcap) if current_mcap else ""
        row["代币最高市值"] = fmt_km(ath_mcap) if ath_mcap else ""
        row["代币最高市值时间"] = ath_time or ""
        normalize_row_display(row)

        name = row.get("代币名称", addr[:10])
        print(
            f"  [{idx:02d}] {name[:24]:<24} "
            f"当前 {row.get('代币当前市值') or '-':>10} "
            f"最高 {row.get('代币最高市值') or '-':>10}"
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
