# -*- coding: utf-8 -*-
"""Link FOMO holders to on-chain wallets by swap time, token amount, and current balance."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fomo_token_chart import TRADES_DIR

ROOT = Path(__file__).resolve().parent
WALLET_CACHE_PATH = ROOT / "fomo_wallet_links.json"

RECENT_SEC = 26 * 3600
TIME_WINDOW_SEC = 40
AMOUNT_REL = 0.002
HOLD_REL = 0.005
HOLD_AGREE_REL = 0.02
MIN_HOLD_AMOUNT = 1.0
MAX_HOLD_QUERIES = 3
GECKO_MIN_INTERVAL = 2.6

# Quote assets. The fingerprint is the other leg of the swap.
QUOTES = {
    "so11111111111111111111111111111111111111112",
    "epjfwdd5aufqssqem2qn1xzybapc8g4weggkzwytdt1v",
    "es9vmfrzacermjfrf4h2fyd4kconky11mcce8benwnyb",
    "0x0000000000000000000000000000000000000000",
    "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "0xdac17f958d2ee523a2206206994597c13d831ec7",
    "0x55d398326f99059ff775485246999027b3197955",
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
    "0x4200000000000000000000000000000000000006",
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
}

GECKO_NETWORK = {
    1: "eth",
    56: "bsc",
    137: "polygon",
    8453: "base",
    42161: "arbitrum",
    101: "solana",
    1399811149: "solana",
}

DEX_CHAIN = {
    "eth": "ethereum",
    "bsc": "bsc",
    "polygon": "polygon",
    "base": "base",
    "arbitrum": "arbitrum",
    "solana": "solana",
}

RPCS = (
    "https://api.mainnet-beta.solana.com",
    "https://solana-rpc.publicnode.com",
)
# getTokenLargestAccounts is blocked on the public cluster. These still serve it.
HOLD_RPCS = (
    "https://public.rpc.solanavibestation.com",
    "https://solana-mainnet.gateway.tatum.io",
)


def parse_time(value: str | None) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return 0.0


def same_addr(left: str, right: str) -> bool:
    a = str(left or "").strip()
    b = str(right or "").strip()
    if a.lower().startswith("0x") or b.lower().startswith("0x"):
        return a.lower() == b.lower()
    return a == b


def is_quote(addr: str) -> bool:
    raw = str(addr or "").strip()
    key = raw.lower() if raw.lower().startswith("0x") else raw
    if key.startswith("0x"):
        key = key.lower()
    return key in QUOTES or raw.lower() in QUOTES


def amount_close(left: float, right: float) -> bool:
    if left <= 0 or right <= 0:
        return False
    diff = abs(left - right)
    if diff <= 0.05:
        return True
    return diff / max(left, right) <= AMOUNT_REL


def swap_fingerprint(swap: dict) -> dict | None:
    if not isinstance(swap, dict):
        return None
    inn = str(swap.get("inTokenAddress") or "").strip()
    out = str(swap.get("outTokenAddress") or "").strip()
    try:
        in_human = float(swap.get("inHumanAmount") or 0)
        out_human = float(swap.get("outHumanAmount") or 0)
        usd = float(swap.get("humanUsdAmountIn") or swap.get("humanUsdAmountOut") or 0)
    except (TypeError, ValueError):
        return None
    created = str(swap.get("createdAt") or "").strip()
    if not created or parse_time(created) <= 0:
        return None
    try:
        network_id = int(swap.get("networkId") or swap.get("outNetworkId") or swap.get("inNetworkId") or 0)
    except (TypeError, ValueError):
        network_id = 0
    in_quote = is_quote(inn)
    out_quote = is_quote(out)
    if in_quote and not out_quote:
        token, human, side = out, out_human, "buy"
    elif out_quote and not in_quote:
        token, human, side = inn, in_human, "sell"
    elif not in_quote and not out_quote:
        token, human, side = out, out_human, "buy"
    else:
        return None
    if not token or human <= 0:
        return None
    return {
        "t": created,
        "when": parse_time(created),
        "networkId": network_id,
        "network": GECKO_NETWORK.get(network_id, ""),
        "token": token,
        "amount": human,
        "side": side,
        "usd": usd,
    }


def pick_fingerprints(swaps: list[dict], now: float, *, limit: int = 2) -> list[dict]:
    grouped: dict[int, list[dict]] = {}
    for swap in swaps:
        grouped.setdefault(int(swap.get("networkId") or 0), []).append(swap)
    chosen: list[dict] = []
    for group in grouped.values():
        group.sort(key=lambda item: ((item["when"] >= now - RECENT_SEC), item["usd"]), reverse=True)
        seen: set[tuple[str, str]] = set()
        kept = 0
        for item in group:
            bucket = (item["token"], item["t"][:16])
            if bucket in seen:
                continue
            seen.add(bucket)
            chosen.append(item)
            kept += 1
            if kept >= limit:
                break
    return chosen


def match_pool_trades(
    rows: list[dict],
    *,
    when: float,
    amount: float,
    side: str,
    base_is_token: bool,
) -> dict | None:
    best: tuple[float, float, dict] | None = None
    for row in rows:
        attrs = row.get("attributes") if isinstance(row, dict) and "attributes" in row else row
        if not isinstance(attrs, dict):
            continue
        block_time = parse_time(str(attrs.get("block_timestamp") or ""))
        if not block_time or abs(block_time - when) > TIME_WINDOW_SEC:
            continue
        kind = str(attrs.get("kind") or "")
        try:
            from_amt = float(attrs.get("from_token_amount") or 0)
            to_amt = float(attrs.get("to_token_amount") or 0)
        except (TypeError, ValueError):
            continue
        if base_is_token:
            got = to_amt if side == "buy" else from_amt
            if kind and kind != side:
                continue
        else:
            got = from_amt if side == "buy" else to_amt
            if kind and kind == side:
                continue
        if not amount_close(got, amount):
            continue
        rank = (abs(block_time - when), abs(got - amount))
        if best is None or rank < (best[0], best[1]):
            best = (rank[0], rank[1], attrs)
    if best is None:
        return None
    attrs = best[2]
    return {
        "tx": str(attrs.get("tx_hash") or ""),
        "txFrom": str(attrs.get("tx_from_address") or ""),
        "blockTime": parse_time(str(attrs.get("block_timestamp") or "")),
    }


def _ui_amount(token_amount: dict) -> float:
    if not isinstance(token_amount, dict):
        return 0.0
    if token_amount.get("uiAmount") not in (None, ""):
        return float(token_amount["uiAmount"])
    return float(token_amount.get("uiAmountString") or 0)


def token_owner_from_tx(tx: dict, mint: str, amount: float, side: str, pool: str = "") -> str:
    meta = (tx or {}).get("meta") or {}
    pre = {
        row.get("accountIndex"): row
        for row in (meta.get("preTokenBalances") or [])
        if isinstance(row, dict)
    }
    sign = 1 if side == "buy" else -1
    for row in meta.get("postTokenBalances") or []:
        if not isinstance(row, dict) or not same_addr(str(row.get("mint") or ""), mint):
            continue
        owner = str(row.get("owner") or "")
        if not owner or same_addr(owner, pool):
            continue
        prev_ui = (pre.get(row.get("accountIndex")) or {}).get("uiTokenAmount") or {}
        post_ui = row.get("uiTokenAmount") or {}
        try:
            prev = _ui_amount(prev_ui)
            post = _ui_amount(post_ui)
        except (TypeError, ValueError):
            continue
        delta = post - prev
        if delta == 0 or (delta > 0) != (sign > 0):
            continue
        if amount_close(abs(delta), amount):
            return owner
    return ""


def _canon_addr(token: str, case_map: dict[str, str]) -> str:
    raw = str(token or "").strip()
    if not raw:
        return ""
    key = raw.lower()
    prev = case_map.get(key, "")
    if not prev or (prev == prev.lower() and raw != raw.lower()):
        case_map[key] = raw
        prev = raw
    return prev


def _touch_position(
    rec: dict,
    case_map: dict[str, str],
    network_id: int,
    token: str,
    delta: float,
    *,
    from_swap: bool,
) -> None:
    if not token or not delta or is_quote(token):
        return
    try:
        network_id = int(network_id or 0)
    except (TypeError, ValueError):
        network_id = 0
    canonical = _canon_addr(token, case_map)
    if not canonical:
        return
    slot_key = f"{network_id}:{canonical.lower()}"
    slot = rec["_positions"].setdefault(
        slot_key,
        {
            "token": canonical,
            "networkId": network_id,
            "network": GECKO_NETWORK.get(network_id, ""),
            "amount": 0.0,
            "swapAmount": 0.0,
        },
    )
    slot["token"] = canonical
    slot["amount"] += float(delta)
    if from_swap:
        slot["swapAmount"] += float(delta)


def _swap_network(swap: dict) -> int:
    try:
        return int(swap.get("networkId") or swap.get("outNetworkId") or swap.get("inNetworkId") or 0)
    except (TypeError, ValueError):
        return 0


def _human(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def load_traders(root: Path | None = None) -> dict[str, dict]:
    base = (root / "fomo_token_trades") if root is not None else TRADES_DIR
    traders: dict[str, dict] = {}
    case_map: dict[str, str] = {}
    if not base.is_dir():
        return traders
    for path in sorted(base.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for uid, trader in (data.get("traders") or {}).items():
            if not isinstance(trader, dict):
                continue
            rec = traders.setdefault(
                str(uid),
                {
                    "userId": str(trader.get("userId") or uid),
                    "handle": trader.get("handle") or "",
                    "displayName": trader.get("displayName") or "",
                    "ledgerAddresses": set(),
                    "swaps": [],
                    "_positions": {},
                },
            )
            if trader.get("handle"):
                rec["handle"] = trader["handle"]
            if trader.get("displayName"):
                rec["displayName"] = trader["displayName"]
            for trade in (trader.get("trades") or {}).values():
                if not isinstance(trade, dict):
                    continue
                ledger = str(trade.get("userAddress") or "").strip()
                if ledger:
                    rec["ledgerAddresses"].add(ledger)
                trade_network = 0
                for swap in trade.get("swaps") or []:
                    if not isinstance(swap, dict):
                        continue
                    finger = swap_fingerprint(swap)
                    if finger:
                        rec["swaps"].append(finger)
                    network_id = _swap_network(swap)
                    trade_network = network_id or trade_network
                    _touch_position(
                        rec, case_map, network_id, str(swap.get("outTokenAddress") or ""),
                        _human(swap.get("outHumanAmount")), from_swap=True,
                    )
                    _touch_position(
                        rec, case_map, network_id, str(swap.get("inTokenAddress") or ""),
                        -_human(swap.get("inHumanAmount")), from_swap=True,
                    )
                for transfer in trade.get("transfers") or []:
                    if not isinstance(transfer, dict):
                        continue
                    try:
                        network_id = int(transfer.get("networkId") or trade_network or 0)
                    except (TypeError, ValueError):
                        network_id = trade_network
                    amount = _human(transfer.get("humanAmount"))
                    token = str(transfer.get("tokenAddress") or "")
                    to_addr = str(transfer.get("toAddress") or "")
                    from_addr = str(transfer.get("fromAddress") or "")
                    if ledger and to_addr == ledger:
                        _touch_position(rec, case_map, network_id, token, amount, from_swap=False)
                    elif ledger and from_addr == ledger:
                        _touch_position(rec, case_map, network_id, token, -amount, from_swap=False)
    for rec in traders.values():
        rows = []
        for slot in rec.pop("_positions", {}).values():
            if max(slot["amount"], slot["swapAmount"]) >= MIN_HOLD_AMOUNT:
                rows.append(slot)
        rows.sort(key=lambda slot: max(slot["amount"], slot["swapAmount"]), reverse=True)
        rec["positions"] = rows
    return traders


def empty_wallet_cache() -> dict:
    return {"updatedAt": None, "finishedAt": None, "traders": {}}


def load_wallet_links(path: Path | None = None) -> dict:
    target = path or WALLET_CACHE_PATH
    if not target.is_file():
        return empty_wallet_cache()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_wallet_cache()
    if not isinstance(data, dict):
        return empty_wallet_cache()
    data.setdefault("traders", {})
    return data


def save_wallet_links(cache: dict, path: Path | None = None) -> None:
    target = path or WALLET_CACHE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def _id_addr(ref: dict) -> str:
    raw = str((ref or {}).get("id") or "")
    if "_" not in raw:
        return raw
    return raw.split("_", 1)[1]


def _http_json(url: str, *, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "FomoDesk/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _rpc(method: str, params: list, *, retries: int = 1, urls: tuple[str, ...] | None = None) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last: Exception | dict | None = None
    endpoints = urls or RPCS
    for attempt in range(max(retries, 1)):
        for url in endpoints:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=40) as resp:
                    data = json.loads(resp.read().decode())
                if data.get("error"):
                    last = data["error"]
                    continue
                return data.get("result")
            except urllib.error.HTTPError as exc:
                last = exc
                time.sleep(3 + attempt * 4 if exc.code == 429 else 0.3)
            except Exception as exc:
                last = exc
                time.sleep(0.3)
    raise RuntimeError(str(last or "rpc failed"))


class ChainClient:
    def __init__(self, sleep_sec: float = GECKO_MIN_INTERVAL) -> None:
        self.sleep_sec = sleep_sec
        self._gecko_at = 0.0
        self._gecko_cache: dict[tuple, list] = {}
        self._dex_cache: dict[str, list] = {}
        self._holders: dict[str, list] = {}

    def _gecko_wait(self) -> None:
        gap = self.sleep_sec - (time.time() - self._gecko_at)
        if gap > 0:
            time.sleep(gap)
        self._gecko_at = time.time()

    def pools(self, token: str, network: str) -> list[dict]:
        key = f"{network}:{token if not token.lower().startswith('0x') else token.lower()}"
        if key not in self._dex_cache:
            found = self._dex_pools(token, network) or self._gecko_pools(token, network)
            self._dex_cache[key] = found[:3]
        return self._dex_cache[key]

    def _dex_pools(self, token: str, network: str) -> list[dict]:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token}"
        data = None
        for attempt in range(2):
            try:
                data = _http_json(url)
                break
            except Exception:
                time.sleep(0.8 + attempt)
        if not isinstance(data, dict):
            return []
        chain = DEX_CHAIN.get(network, network)
        pairs = []
        for pair in data.get("pairs") or []:
            if not isinstance(pair, dict) or str(pair.get("chainId") or "") != chain:
                continue
            base = (pair.get("baseToken") or {}).get("address") or ""
            quote = (pair.get("quoteToken") or {}).get("address") or ""
            if not same_addr(base, token) and not same_addr(quote, token):
                continue
            vol = float(((pair.get("volume") or {}).get("h24")) or 0)
            pairs.append({"pool": pair.get("pairAddress") or "", "base": base, "quote": quote, "volume": vol})
        pairs.sort(key=lambda item: item["volume"], reverse=True)
        return [item for item in pairs if item["pool"]]

    def _gecko_pools(self, token: str, network: str) -> list[dict]:
        url = f"https://api.geckoterminal.com/api/v2/networks/{network}/tokens/{token}/pools?page=1"
        try:
            self._gecko_wait()
            data = _http_json(url)
        except Exception:
            return []
        pairs = []
        for item in (data or {}).get("data") or []:
            if not isinstance(item, dict):
                continue
            attrs = item.get("attributes") or {}
            rel = item.get("relationships") or {}
            base = _id_addr((rel.get("base_token") or {}).get("data") or {})
            quote = _id_addr((rel.get("quote_token") or {}).get("data") or {})
            if not same_addr(base, token) and not same_addr(quote, token):
                continue
            vol = float(((attrs.get("volume_usd") or {}).get("h24")) or 0)
            pairs.append({"pool": attrs.get("address") or "", "base": base, "quote": quote, "volume": vol})
        pairs.sort(key=lambda item: item["volume"], reverse=True)
        return [item for item in pairs if item["pool"]]

    def trades(self, network: str, pool: str, threshold: float) -> list[dict]:
        bucket = int(threshold)
        key = (network, pool, bucket)
        if key in self._gecko_cache:
            return self._gecko_cache[key]
        url = (
            "https://api.geckoterminal.com/api/v2/networks/"
            f"{network}/pools/{pool}/trades?trade_volume_in_usd_greater_than={bucket}"
        )
        rows: list[dict] = []
        for attempt in range(4):
            self._gecko_wait()
            try:
                data = _http_json(url)
                rows = list((data or {}).get("data") or [])
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    time.sleep(20 + attempt * 10)
                    continue
                rows = []
                break
            except Exception:
                rows = []
                break
        self._gecko_cache[key] = rows
        return rows

    def transaction(self, signature: str) -> dict:
        if not signature:
            return {}
        try:
            tx = _rpc(
                "getTransaction",
                [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
            )
        except Exception:
            return {}
        return tx or {}

    def largest_holders(self, mint: str) -> list[dict]:
        key = str(mint or "").strip()
        if not key:
            return []
        if key in self._holders:
            return self._holders[key]
        time.sleep(1.2)
        result = _rpc("getTokenLargestAccounts", [key], retries=4, urls=HOLD_RPCS) or {}
        accounts = result.get("value") or []
        addrs = [str(item.get("address") or "") for item in accounts if item.get("address")]
        infos: list = []
        if addrs:
            time.sleep(1.2)
            fetched = _rpc("getMultipleAccounts", [addrs, {"encoding": "jsonParsed"}], retries=4, urls=HOLD_RPCS) or {}
            infos = fetched.get("value") or []
        rows: list[dict] = []
        for acc, info in zip(accounts, infos):
            parsed = (((info or {}).get("data") or {}).get("parsed") or {}).get("info") or {}
            owner = str(parsed.get("owner") or "")
            amount = _largest_ui(acc)
            if owner and amount > 0:
                rows.append({"owner": owner, "amount": amount, "account": acc.get("address") or ""})
        self._holders[key] = rows
        return rows


def _largest_ui(account: dict) -> float:
    if not isinstance(account, dict):
        return 0.0
    if account.get("uiAmount") not in (None, ""):
        try:
            return float(account["uiAmount"])
        except (TypeError, ValueError):
            return 0.0
    if account.get("uiAmountString") not in (None, ""):
        try:
            return float(account["uiAmountString"])
        except (TypeError, ValueError):
            return 0.0
    try:
        raw = float(account.get("amount") or 0)
        decimals = int(account.get("decimals") or 0)
    except (TypeError, ValueError):
        return 0.0
    return raw / (10 ** decimals) if decimals else raw


def hold_close(left: float, right: float, rel: float = HOLD_REL) -> bool:
    if left <= 0 or right <= 0:
        return False
    diff = abs(left - right)
    if diff <= 0.5:
        return True
    return diff / max(left, right) <= rel


def match_balance(holders: list[dict], target: float, limit: float = HOLD_REL) -> tuple[dict | None, str]:
    ranked: list[tuple[float, str, float]] = []
    totals: dict[str, float] = {}
    for row in holders:
        if not isinstance(row, dict):
            continue
        owner = str(row.get("owner") or "")
        try:
            amount = float(row.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if not owner or amount <= 0 or target <= 0:
            continue
        totals[owner] = totals.get(owner, 0.0) + amount
    for owner, amount in totals.items():
        ranked.append((abs(amount - target) / max(target, amount), owner, amount))
    ranked.sort()
    if not ranked:
        return None, "no_holders"
    score, owner, amount = ranked[0]
    if not hold_close(amount, target, limit):
        return None, "no_balance_match"
    if len(ranked) > 1 and hold_close(ranked[1][2], target, limit):
        return None, "ambiguous_balance"
    return {"owner": owner, "amount": amount, "rel": score}, ""


def _solana_positions(trader: dict) -> list[dict]:
    rows = []
    for slot in trader.get("positions") or []:
        if not isinstance(slot, dict) or slot.get("network") != "solana":
            continue
        amount = _human(slot.get("amount"))
        swap_amount = _human(slot.get("swapAmount"))
        if max(amount, swap_amount) < MIN_HOLD_AMOUNT:
            continue
        rows.append(slot)
    rows.sort(key=lambda slot: max(_human(slot.get("amount")), _human(slot.get("swapAmount"))), reverse=True)
    return rows[:MAX_HOLD_QUERIES]


def resolve_holdings(trader: dict, client: ChainClient) -> tuple[dict | None, str]:
    positions = _solana_positions(trader)
    if not positions:
        return None, ""
    votes: dict[str, list[tuple[dict, dict, str]]] = {}
    last_reason = "no_balance_match"
    for pos in positions:
        try:
            holders = client.largest_holders(pos["token"])
        except Exception:
            last_reason = "rpc_failed"
            continue
        amount = _human(pos.get("amount"))
        swap_amount = _human(pos.get("swapAmount"))
        hit, reason = (None, "no_balance_match")
        source = "holding"
        if amount >= MIN_HOLD_AMOUNT:
            hit, reason = match_balance(holders, amount, HOLD_REL)
        if not hit and amount >= MIN_HOLD_AMOUNT:
            loose, loose_reason = match_balance(holders, amount, HOLD_AGREE_REL)
            if loose:
                hit, reason, source = loose, "", "loose"
            else:
                reason = loose_reason or reason
        if (
            not hit
            and swap_amount >= MIN_HOLD_AMOUNT
            and not hold_close(swap_amount, amount)
        ):
            loose, loose_reason = match_balance(holders, swap_amount, HOLD_AGREE_REL)
            if loose:
                hit, reason, source = loose, "", "loose"
            else:
                reason = loose_reason or reason
        if not hit:
            last_reason = reason or last_reason
            continue
        votes.setdefault(hit["owner"], []).append((pos, hit, source))
    if not votes:
        return None, last_reason
    agreed = {owner: items for owner, items in votes.items() if len(items) >= 2}
    singles = {
        owner: items
        for owner, items in votes.items()
        if len(items) == 1 and items[0][2] == "holding"
    }
    if len(agreed) == 1:
        owner = next(iter(agreed))
    elif len(agreed) > 1:
        return None, "ambiguous_balance"
    elif len(singles) == 1:
        owner = next(iter(singles))
    elif len(singles) > 1:
        return None, "ambiguous_balance"
    else:
        return None, "ambiguous_balance" if len(votes) > 1 else last_reason
    pos, hit, source = votes[owner][0]
    return (
        {
            "address": owner,
            "network": "solana",
            "networkId": int(pos.get("networkId") or 1399811149),
            "tx": "",
            "token": pos.get("token") or "",
            "amount": _human(pos.get("amount")) if source == "holding" else _human(pos.get("swapAmount")),
            "chainAmount": hit["amount"],
            "side": "hold",
            "method": "holding",
            "matchedTokens": len(votes[owner]),
        },
        "",
    )


def _quiet_enough(signatures: list[dict], when: float) -> bool:
    if not signatures:
        return False
    times = [int(item.get("blockTime") or 0) for item in signatures if item.get("blockTime")]
    if not times:
        return False
    newest, oldest = max(times), min(times)
    span = max(newest - oldest, 1)
    pages = (newest - when) / span
    return pages <= 6


def resolve_fingerprint(finger: dict, client: ChainClient) -> tuple[dict | None, str]:
    network = finger.get("network") or ""
    if not network:
        return None, "unsupported_network"
    pools = client.pools(finger["token"], network)
    if not pools:
        return None, "no_pool"
    threshold = finger["usd"] * 0.8 if finger["usd"] >= 50 else max(finger["usd"] * 0.5, 0)
    recent = finger["when"] >= time.time() - RECENT_SEC
    for pool in pools[:2] if recent else []:
        base_is_token = same_addr(pool["base"], finger["token"])
        rows = client.trades(network, pool["pool"], threshold)
        hit = match_pool_trades(
            rows,
            when=finger["when"],
            amount=finger["amount"],
            side=finger["side"],
            base_is_token=base_is_token,
        )
        if not hit:
            continue
        owner = ""
        if network == "solana" and hit.get("tx"):
            tx = client.transaction(hit["tx"])
            owner = token_owner_from_tx(tx, finger["token"], finger["amount"], finger["side"], pool["pool"])
        address = owner or hit.get("txFrom") or ""
        if not address or same_addr(address, pool["pool"]):
            continue
        return (
            {
                "address": address,
                "network": network,
                "networkId": finger["networkId"],
                "tx": hit.get("tx") or "",
                "token": finger["token"],
                "amount": finger["amount"],
                "side": finger["side"],
                "swapAt": finger["t"],
                "blockTime": int(hit.get("blockTime") or 0),
                "method": "swap",
            },
            "",
        )
    if network == "solana":
        owner, sig, reason = _resolve_solana_rpc(finger, pools[0], client)
        if owner:
            return (
                {
                    "address": owner,
                    "network": "solana",
                    "networkId": finger["networkId"],
                    "tx": sig,
                    "token": finger["token"],
                    "amount": finger["amount"],
                    "side": finger["side"],
                    "swapAt": finger["t"],
                    "blockTime": int(finger["when"]),
                    "method": "swap",
                },
                "",
            )
        return None, reason or "no_match"
    return None, "no_match" if recent else "no_recent_swap"


def _resolve_solana_rpc(finger: dict, pool: dict, client: ChainClient) -> tuple[str, str, str]:
    try:
        first = _rpc("getSignaturesForAddress", [pool["pool"], {"limit": 1000}]) or []
    except Exception:
        return "", "", "rpc_failed"
    if not first:
        return "", "", "no_match"
    if not _quiet_enough(first, finger["when"]):
        return "", "", "pool_too_active"
    before = None
    pages = [first]
    for _ in range(5):
        times = [int(item.get("blockTime") or 0) for item in pages[-1] if item.get("blockTime")]
        if not times:
            break
        oldest = min(times)
        if oldest <= finger["when"] + TIME_WINDOW_SEC:
            break
        before = pages[-1][-1]["signature"]
        try:
            nxt = _rpc("getSignaturesForAddress", [pool["pool"], {"limit": 1000, "before": before}]) or []
        except Exception:
            break
        if not nxt:
            break
        pages.append(nxt)
    for batch in pages:
        for item in batch:
            bt = int(item.get("blockTime") or 0)
            if item.get("err") or abs(bt - finger["when"]) > TIME_WINDOW_SEC:
                continue
            tx = client.transaction(item["signature"])
            owner = token_owner_from_tx(tx, finger["token"], finger["amount"], finger["side"], pool["pool"])
            if owner:
                return owner, item["signature"], ""
    return "", "", "no_match"


def resolve_trader(trader: dict, client: ChainClient, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    fingers = pick_fingerprints(trader.get("swaps") or [], now)
    grouped: dict[str, list[dict]] = {}
    for finger in fingers:
        net = finger.get("network") or str(finger.get("networkId"))
        grouped.setdefault(net, []).append(finger)
    wallets: list[dict] = []
    reasons: list[str] = []
    for group in grouped.values():
        wallet = None
        reason = "no_match"
        for finger in group:
            wallet, reason = resolve_fingerprint(finger, client)
            if wallet:
                break
        if wallet:
            wallets.append(wallet)
        elif reason:
            reasons.append(reason)
    if not any(item.get("network") == "solana" for item in wallets):
        holding, hold_reason = resolve_holdings(trader, client)
        if holding:
            wallets.append(holding)
        elif hold_reason:
            reasons.append(hold_reason)
    if not fingers and not wallets and not reasons:
        reasons.append("no_swaps")
    return {
        "userId": trader.get("userId") or "",
        "handle": trader.get("handle") or "",
        "displayName": trader.get("displayName") or "",
        "ledgerAddresses": sorted(trader.get("ledgerAddresses") or []),
        "wallets": wallets,
        "status": "matched" if wallets else "unresolved",
        "reason": "" if wallets else (reasons[0] if reasons else "no_match"),
    }


def resolve_all(
    *,
    root: Path | None = None,
    path: Path | None = None,
    client: ChainClient | None = None,
    force: bool = False,
    progress_fn: Callable[[int, int], None] | None = None,
    now: float | None = None,
) -> dict:
    traders = load_traders(root)
    cache = load_wallet_links(path)
    stored = cache.setdefault("traders", {})
    client = client or ChainClient()
    now = time.time() if now is None else now
    items = list(traders.items())
    total = len(items)
    done = 0
    for uid, trader in items:
        done += 1
        prev = stored.get(uid) or {}
        if not force and prev.get("status") == "matched" and prev.get("wallets"):
            if progress_fn:
                progress_fn(done, total)
            continue
        try:
            row = resolve_trader(trader, client, now=now)
        except Exception as exc:
            row = {
                "userId": trader.get("userId") or uid,
                "handle": trader.get("handle") or "",
                "displayName": trader.get("displayName") or "",
                "ledgerAddresses": sorted(trader.get("ledgerAddresses") or []),
                "wallets": [],
                "status": "unresolved",
                "reason": "error",
            }
            row["error"] = str(exc)[:200]
        stored[uid] = row
        cache["updatedAt"] = datetime.now(timezone.utc).isoformat()
        save_wallet_links(cache, path)
        if progress_fn:
            progress_fn(done, total)
    cache["finishedAt"] = datetime.now(timezone.utc).isoformat()
    cache["updatedAt"] = cache["finishedAt"]
    save_wallet_links(cache, path)
    return cache


def resolve_holdings_all(
    *,
    root: Path | None = None,
    path: Path | None = None,
    client: ChainClient | None = None,
    force: bool = False,
    progress_fn: Callable[[int, int], None] | None = None,
) -> dict:
    """Fill wallets from current Solana balances. Leaves an existing match in place."""
    traders = load_traders(root)
    cache = load_wallet_links(path)
    stored = cache.setdefault("traders", {})
    client = client or ChainClient()
    items = list(traders.items())
    total = len(items)
    done = 0
    for uid, trader in items:
        done += 1
        prev = stored.get(uid)
        if not isinstance(prev, dict):
            prev = {
                "userId": trader.get("userId") or uid,
                "handle": trader.get("handle") or "",
                "displayName": trader.get("displayName") or "",
                "ledgerAddresses": sorted(trader.get("ledgerAddresses") or []),
                "wallets": [],
                "status": "unresolved",
                "reason": "",
            }
        if trader.get("handle"):
            prev["handle"] = trader["handle"]
        if trader.get("displayName"):
            prev["displayName"] = trader["displayName"]
        already = [
            item for item in (prev.get("wallets") or [])
            if isinstance(item, dict) and item.get("network") == "solana" and item.get("address")
        ]
        if not force and prev.get("status") == "matched" and already:
            stored[uid] = prev
            if progress_fn:
                progress_fn(done, total)
            continue
        try:
            holding, reason = resolve_holdings(trader, client)
        except Exception as exc:
            holding, reason = None, "error"
            prev["error"] = str(exc)[:200]
        if holding:
            others = [
                item for item in (prev.get("wallets") or [])
                if isinstance(item, dict) and item.get("network") != "solana"
            ]
            prev["wallets"] = others + [holding]
            prev["status"] = "matched"
            prev["reason"] = ""
            prev.pop("holdingReason", None)
        elif reason:
            prev["holdingReason"] = reason
        stored[uid] = prev
        cache["updatedAt"] = datetime.now(timezone.utc).isoformat()
        save_wallet_links(cache, path)
        if progress_fn:
            progress_fn(done, total)
    cache["finishedAt"] = datetime.now(timezone.utc).isoformat()
    cache["updatedAt"] = cache["finishedAt"]
    save_wallet_links(cache, path)
    return cache


def wallet_public_view(cache: dict, job: dict | None = None) -> dict:
    job = job or {}
    rows = []
    matched = unresolved = 0
    for uid, trader in (cache.get("traders") or {}).items():
        if not isinstance(trader, dict):
            continue
        status = trader.get("status") or "unresolved"
        if status == "matched":
            matched += 1
        else:
            unresolved += 1
        rows.append(
            {
                "userId": trader.get("userId") or uid,
                "handle": trader.get("handle") or "",
                "displayName": trader.get("displayName") or "",
                "status": status,
                "reason": trader.get("reason") or "",
                "wallets": trader.get("wallets") or [],
            }
        )
    rows.sort(key=lambda item: (item["status"] != "matched", item["handle"]))
    return {
        "ok": True,
        "updatedAt": cache.get("updatedAt"),
        "finishedAt": cache.get("finishedAt"),
        "running": job.get("status") == "running",
        "progress": {"done": int(job.get("done") or 0), "total": int(job.get("total") or 0)},
        "stats": {"matched": matched, "unresolved": unresolved, "traders": len(rows)},
        "traders": rows,
    }


def main() -> None:
    def progress(done: int, total: int) -> None:
        print(f"{done}/{total}", flush=True)

    cache = resolve_all(progress_fn=progress)
    stats = wallet_public_view(cache)["stats"]
    print("matched", stats["matched"], "unresolved", stats["unresolved"], flush=True)


if __name__ == "__main__":
    main()
