# -*- coding: utf-8 -*-
"""FOMO authenticated API helpers (Privy Bearer token + optional Cookie)."""
from __future__ import annotations

import base64
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
AUTH_PATH = ROOT / "fomo_auth.json"
TOKEN_META_CACHE_PATH = ROOT / "fomo_token_meta_cache.json"
PROD_API = "https://prod-api.fomo.family"
PRIVY_AUTH = "https://auth.privy.io"
PRIVY_APP_ID = "cm6h485o300n3zj9yl6vpedq7"
PRIVY_CLIENT_ID = "client-WY5gFSayQjxnQhG4rP6SnwPAyPZWZpNRhJ6b9rzMnYwqH"
SUPPORTED_CHAINS = "1,56,143,4663,8453,1399811149"
# Cloudflare / FOMO rejects modern curl JA3; chrome110 impersonation works.
CURL_IMPERSONATE = "chrome110"


def load_auth() -> dict:
    if not AUTH_PATH.exists():
        return {}
    try:
        return json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _preview(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 16:
        return "***"
    return f"{token[:8]}…{token[-6:]}"


def parse_auth_blob(raw: str) -> dict:
    """Accept raw token, 'Bearer …', or full 'Copy as cURL' text."""
    text = (raw or "").strip()
    token = ""
    cookie = ""

    # curl -H 'authorization: Bearer xxx' (case-insensitive)
    m = re.search(r"[Aa]uthorization:\s*[Bb]earer\s+([^\s'\"]+)", text)
    if m:
        token = m.group(1).strip()
    if not token:
        m = re.search(r"[Aa]uthorization:\s*([^\s'\"]+)", text)
        if m and not m.group(1).lower().startswith("basic"):
            val = m.group(1).strip()
            token = val[7:].strip() if val.lower().startswith("bearer ") else val

    # curl -b 'a=b; c=d' or -H 'Cookie: ...'
    m = re.search(r"(?:-b|--cookie)\s+'([^']+)'", text)
    if not m:
        m = re.search(r'(?:-b|--cookie)\s+"([^"]+)"', text)
    if m:
        cookie = m.group(1).strip()
    m = re.search(r"Cookie:\s*([^\n\r]+)", text, flags=re.I)
    if m and not cookie:
        cookie = m.group(1).strip().strip("'\"")

    if not token:
        # plain token paste
        line = text.splitlines()[0].strip() if text else ""
        if line.lower().startswith("bearer "):
            token = line[7:].strip()
        elif line.startswith("eyJ"):
            token = line.strip().strip("'\"")

    return {"accessToken": token, "cookie": cookie}


def _unwrap_stored(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        try:
            decoded = json.loads(text) if text.startswith('"') else text[1:-1]
            if isinstance(decoded, str):
                text = decoded.strip()
        except Exception:
            text = text[1:-1].strip()
    return text


def _looks_jwt(value: str) -> bool:
    return value.startswith("eyJ") and value.count(".") >= 2


def extract_privy_session(
    storage: dict | None = None,
    *,
    authorization_headers: list[str] | None = None,
    authenticate_payload: dict | None = None,
) -> dict:
    """Pull access/refresh/identity tokens from browser storage or Privy payloads."""
    access = ""
    refresh = ""
    identity = ""

    for key, raw in (storage or {}).items():
        if not isinstance(key, str):
            continue
        kl = key.lower()
        val = _unwrap_stored(raw)
        if not val:
            continue
        if "refresh_token" in kl or kl.endswith("refresh-token"):
            refresh = refresh or val
        elif "id-token" in kl or "id_token" in kl or "identity" in kl:
            if _looks_jwt(val):
                identity = identity or val
        elif "privy:pat" in kl:
            continue
        elif "token" in kl and "privy" in kl and _looks_jwt(val):
            access = access or val

    if isinstance(authenticate_payload, dict):
        tok = _unwrap_stored(
            authenticate_payload.get("token")
            or authenticate_payload.get("access_token")
            or ""
        )
        if _looks_jwt(tok):
            access = tok
        rt = _unwrap_stored(authenticate_payload.get("refresh_token") or "")
        if rt:
            refresh = rt
        ident = _unwrap_stored(authenticate_payload.get("identity_token") or "")
        if _looks_jwt(ident):
            identity = ident

    if not access:
        for header in authorization_headers or []:
            text = _unwrap_stored(header)
            if text.lower().startswith("bearer "):
                text = text[7:].strip()
            if _looks_jwt(text):
                access = text
                break

    return {
        "accessToken": access,
        "refreshToken": refresh,
        "identityToken": identity,
    }


def save_auth(token_or_curl: str, note: str = "", refresh_token: str = "") -> dict:
    parsed = parse_auth_blob(token_or_curl)
    token = parsed["accessToken"]
    cookie = parsed["cookie"]
    if not token and not cookie:
        raise ValueError("未解析到 Bearer Token，请粘贴 Token 或完整 Copy as cURL")
    prev = load_auth()
    data = {
        "accessToken": token or prev.get("accessToken") or "",
        "cookie": cookie or prev.get("cookie") or "",
        "refreshToken": (refresh_token or prev.get("refreshToken") or "").strip(),
        "note": note
        or "From fomo.family DevTools (Authorization Bearer, optional Cookie)",
    }
    AUTH_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "hasToken": bool(data["accessToken"]),
        "hasCookie": bool(data["cookie"]),
        "hasRefresh": bool(data["refreshToken"]),
        "tokenPreview": _preview(data["accessToken"]),
    }


def clear_auth() -> None:
    if AUTH_PATH.exists():
        AUTH_PATH.unlink()


def get_access_token() -> str | None:
    token = (load_auth().get("accessToken") or "").strip()
    needs_refresh = (not token) or _jwt_expires_soon(token, skew_sec=60)
    if needs_refresh and get_refresh_token():
        refreshed = try_refresh_access_token()
        if refreshed:
            token = refreshed
    return token or None


def get_cookie() -> str | None:
    cookie = (load_auth().get("cookie") or "").strip()
    return cookie or None


def get_refresh_token() -> str | None:
    token = (load_auth().get("refreshToken") or "").strip()
    return token or None


def auth_status() -> dict:
    token = (load_auth().get("accessToken") or "").strip() or None
    cookie = get_cookie()
    refresh = get_refresh_token()
    return {
        "configured": bool(token or cookie),
        "hasToken": bool(token),
        "hasCookie": bool(cookie),
        "hasRefresh": bool(refresh),
        "tokenPreview": _preview(token or ""),
        "tokenExpired": bool(token and _jwt_is_expired(token)),
        "authPath": str(AUTH_PATH.name),
    }


def _b64url_json(segment: str) -> dict:
    pad = "=" * (-len(segment) % 4)
    raw = json.loads(base64.urlsafe_b64decode(segment + pad).decode("utf-8"))
    return raw if isinstance(raw, dict) else {}


def _jwt_exp(token: str) -> int | None:
    try:
        payload = _b64url_json((token or "").split(".")[1])
        exp = payload.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def _jwt_is_expired(token: str, skew_sec: int = 0) -> bool:
    exp = _jwt_exp(token)
    if not exp:
        return False
    return exp <= time.time() + skew_sec


def _jwt_expires_soon(token: str, skew_sec: int = 60) -> bool:
    return _jwt_is_expired(token, skew_sec=skew_sec)


def try_refresh_access_token() -> str | None:
    """Exchange stored Privy refresh token for a new access token. Rotates refresh."""
    refresh = get_refresh_token()
    if not refresh:
        return None
    try:
        from curl_cffi import requests as crequests
    except ImportError:
        return None
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "origin": "https://fomo.family",
        "referer": "https://fomo.family/",
        "privy-app-id": PRIVY_APP_ID,
        "privy-client-id": PRIVY_CLIENT_ID,
        "privy-client": "react-auth:3.34.0",
        "authorization": f"Bearer {refresh}",
    }
    try:
        resp = crequests.post(
            f"{PRIVY_AUTH}/api/v1/sessions",
            headers=headers,
            json={},
            impersonate=CURL_IMPERSONATE,
            timeout=30,
        )
        data = resp.json() if resp.content else {}
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    extracted = extract_privy_session(authenticate_payload=data)
    token = extracted["accessToken"]
    if not token or resp.status_code >= 400:
        return None
    save_auth(
        token,
        note="Refreshed from Privy refresh_token",
        refresh_token=extracted["refreshToken"] or refresh,
    )
    return token


def fomo_get(path: str, token: str | None = None, timeout: int = 40, _retried: bool = False) -> dict:
    token = token if token is not None else get_access_token()
    cookie = get_cookie()
    if not token and not cookie:
        raise RuntimeError("未配置 FOMO 登录态：请点「用 Google 登录」，或粘贴 Privy Access Token / Copy as cURL")
    if not path.startswith("/"):
        path = "/" + path
    url = PROD_API + path
    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9",
        "app-language": "zh",
        "content-type": "application/json",
        "origin": "https://fomo.family",
        "referer": "https://fomo.family/",
        "x-supported-chains": SUPPORTED_CHAINS,
    }
    if token:
        headers["authorization"] = f"Bearer {token}"
    if cookie:
        headers["cookie"] = cookie

    try:
        from curl_cffi import requests as crequests
    except ImportError as exc:
        raise RuntimeError("缺少 curl_cffi，请运行: pip install curl_cffi") from exc

    try:
        resp = crequests.get(
            url,
            headers=headers,
            impersonate=CURL_IMPERSONATE,
            timeout=timeout,
        )
        try:
            body = resp.json()
        except Exception:
            body = {"error": resp.text[:500], "statusCode": resp.status_code}
        if not isinstance(body, dict):
            body = {"responseObject": body, "statusCode": resp.status_code}
        body.setdefault("statusCode", resp.status_code)
        if resp.status_code >= 400 and "error" not in body and "success" not in body:
            body["error"] = body.get("message") or f"HTTP {resp.status_code}"
        if (
            not _retried
            and resp.status_code in (401, 403)
            and get_refresh_token()
        ):
            new_token = try_refresh_access_token()
            if new_token:
                return fomo_get(path, token=new_token, timeout=timeout, _retried=True)
        return body
    except Exception as exc:
        return {"error": str(exc), "statusCode": 0}


def fetch_user_by_handle(handle: str, token: str | None = None) -> dict:
    """Resolve FOMO user via GET /v2/users/userHandle/{handle}.

    Note: ``userHandle`` is a literal path segment (lookup-by-handle), not a placeholder.
    """
    handle = (handle or "").strip()
    if not handle:
        raise RuntimeError("empty user handle")
    from urllib.parse import quote

    data = fomo_get(f"/v2/users/userHandle/{quote(handle, safe='')}", token=token)
    status = data.get("statusCode")
    if data.get("error") or status in (401, 403, 404, 430, 431) or data.get("success") is False:
        code = status or "?"
        err = data.get("error") or data.get("message") or "not found"
        raise RuntimeError(f"userHandle lookup failed for {handle}: HTTP {code} {err}")
    obj = data.get("responseObject")
    if not isinstance(obj, dict) or not obj.get("id"):
        raise RuntimeError(f"unexpected userHandle shape for {handle}")
    return obj


def resolve_user_id(
    handle: str,
    *,
    known_uid: str | None = None,
    token: str | None = None,
) -> str:
    """Prefer known uid, else FOMO /v2/users/userHandle/{handle}."""
    uid = (known_uid or "").strip()
    if uid:
        return uid
    user = fetch_user_by_handle(handle, token=token)
    return str(user.get("id") or "").strip()


def fetch_user_balances(user_id: str, token: str | None = None) -> list[dict]:
    data = fomo_get(f"/v2/users/{user_id}/balances", token=token)
    status = data.get("statusCode")
    if data.get("error") or status in (401, 403, 430, 431):
        code = status or "?"
        err = data.get("error") or data.get("message") or "unauthorized"
        hint = ""
        if code in (430, 431) or err == "unauthorized":
            hint = (
                " 常见原因：Token 过期，或 TLS 指纹被拦（本项目需 curl_cffi chrome110）。"
                " 请点侧边栏「用 Google 登录」，或对成功的 prod-api 请求 Copy as cURL 再粘贴。"
            )
        raise RuntimeError(f"balances failed for {user_id}: HTTP {code} {err}.{hint}")

    obj = data.get("responseObject", data)
    if isinstance(obj, dict) and "balances" in obj:
        rows = obj.get("balances") or []
    elif isinstance(obj, list):
        rows = obj
    else:
        rows = data.get("balances") or []
    if not isinstance(rows, list):
        raise RuntimeError(f"unexpected balances shape for {user_id}: {type(obj)}")
    return rows


def normalize_created_at(value) -> str:
    """Normalize FOMO createdAt (unix sec/ms or ISO) to UTC ISO string."""
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if "T" in text or (text.count("-") >= 2 and not text.replace(".", "").isdigit()):
            return text
        try:
            value = float(text)
        except ValueError:
            return text
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    if ts > 1e12:  # milliseconds
        ts /= 1000.0
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def parse_balance_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    trade = item.get("activeTrade") or {}
    # Only currently open positions
    if trade and trade.get("closedAt") is not None:
        return None

    bal = item.get("balance") or {}
    tfr = item.get("tokenFilterResult") or {}
    token_meta = tfr.get("token") or item.get("token") or {}
    user_token = item.get("userToken") or {}

    addr = (
        bal.get("tokenAddress")
        or token_meta.get("address")
        or user_token.get("tokenAddress")
        or item.get("tokenAddress")
        or ""
    ).strip()
    if not addr:
        return None

    symbol = (
        token_meta.get("symbol")
        or (token_meta.get("info") or {}).get("symbol")
        or tfr.get("symbol")
        or item.get("symbol")
        or ""
    ).strip()
    name = (
        token_meta.get("name")
        or (token_meta.get("info") or {}).get("name")
        or item.get("name")
        or ""
    ).strip()
    network_id = (
        token_meta.get("networkId")
        or user_token.get("networkId")
        or trade.get("networkId")
        or item.get("networkId")
    )

    try:
        price = float(tfr.get("priceUSD") or 0)
    except (TypeError, ValueError):
        price = 0.0

    amount = bal.get("shiftedBalance")
    if amount is None:
        amount = trade.get("humanTokenAmount")
    if amount is None:
        amount = user_token.get("humanAmountRemaining")
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0.0

    value = amount * price if price > 0 and amount > 0 else 0.0
    # Drop dust / rounding-to-$0 bags (fmt_km rounds <0.5 to "0")
    if value < 1.0:
        return None

    def _f(v):
        if v in (None, ""):
            return 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    market_cap = _f(tfr.get("marketCap"))
    volume24 = _f(tfr.get("volume24"))
    change24 = _f(tfr.get("change24"))
    launchpad = (token_meta.get("launchpad") or {}) if isinstance(token_meta, dict) else {}
    created_at = normalize_created_at(
        tfr.get("createdAt")
        or token_meta.get("createdAt")
        or (token_meta.get("info") or {}).get("createdAt")
    )
    holding_since = (
        user_token.get("holdingSince")
        or trade.get("createdAt")
        or ""
    )
    position_updated_at = (
        trade.get("updatedAt")
        or user_token.get("updatedAt")
        or ""
    )

    valuation = item.get("valuation") if isinstance(item.get("valuation"), dict) else {}
    entry = _f(
        user_token.get("averageEntryPriceUsd")
        or trade.get("avgEntryPrice")
        or valuation.get("avgEntryPriceUsd")
        or valuation.get("entryPriceUsd")
    )
    cost = _f(
        user_token.get("currentCostBasisUsd")
        or user_token.get("totalCostBasisUsd")
        or valuation.get("currentCostBasisUsd")
    )
    if cost <= 0 and entry > 0 and amount > 0:
        cost = amount * entry

    pnl_usd = None
    for key in (
        "unrealizedPnlUsd",
        "unrealizedPnl",
        "pnlUsd",
        "profitUsd",
    ):
        if valuation.get(key) not in (None, ""):
            pnl_usd = _f(valuation.get(key))
            break
        if key.startswith("unrealized") and trade.get(key) not in (None, ""):
            pnl_usd = _f(trade.get(key))
            break
    pnl_pct = None
    if cost > 0:
        if pnl_usd is None:
            pnl_usd = value - cost
        pnl_pct = pnl_usd / cost * 100.0
    elif pnl_usd is not None and value > 0:
        inferred_cost = value - pnl_usd
        if inferred_cost > 0:
            pnl_pct = pnl_usd / inferred_cost * 100.0

    return {
        "tokenAddress": addr,
        "symbol": symbol,
        "name": name,
        "networkId": network_id,
        "amount": amount,
        "priceUsd": price,
        "value": value,
        "marketCap": market_cap,
        "volume24": volume24,
        "change24": change24,
        "createdAt": created_at,
        "holdingSince": str(holding_since or "").strip(),
        "positionUpdatedAt": str(position_updated_at or "").strip(),
        "entryPriceUsd": entry,
        "pnlUsd": pnl_usd,
        "pnlPct": pnl_pct,
        "launchpadIconUrl": launchpad.get("launchpadIconUrl") or "",
    }


def balances_to_holdings(rows: list[dict]) -> list[dict]:
    out = []
    for item in rows:
        parsed = parse_balance_item(item)
        if parsed and parsed["value"] > 0:
            out.append(parsed)
    return out


def _norm_addr(addr: str) -> str:
    addr = (addr or "").strip()
    if addr.startswith("0x"):
        return addr.lower()
    return addr


def load_token_meta_cache() -> dict:
    if not TOKEN_META_CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(TOKEN_META_CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_token_meta_cache(cache: dict) -> None:
    cache = dict(cache or {})
    cache["updatedAt"] = datetime.now(timezone.utc).isoformat()
    TOKEN_META_CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def upsert_token_meta(cache: dict, holding: dict) -> None:
    """Merge FOMO balances token fields into local meta cache."""
    if not isinstance(holding, dict):
        return
    addr = _norm_addr(holding.get("tokenAddress") or "")
    if not addr or addr == "updatedAt":
        return
    now = datetime.now(timezone.utc).isoformat()
    prev = cache.get(addr) if isinstance(cache.get(addr), dict) else {}
    entry = {
        **prev,
        "tokenAddress": holding.get("tokenAddress") or prev.get("tokenAddress") or addr,
        "symbol": holding.get("symbol") or prev.get("symbol") or "",
        "name": holding.get("name") or prev.get("name") or "",
        "networkId": holding.get("networkId")
        if holding.get("networkId") is not None
        else prev.get("networkId"),
        "priceUsd": float(holding.get("priceUsd") or prev.get("priceUsd") or 0),
        "marketCap": float(prev.get("marketCap") or 0),
        "volume24": float(prev.get("volume24") or 0),
        "change24": prev.get("change24"),
        "createdAt": prev.get("createdAt") or "",
        "fetchedAt": now,
        "source": "fomo-balances",
    }
    if holding.get("marketCap"):
        entry["marketCap"] = float(holding["marketCap"])
    if holding.get("volume24"):
        entry["volume24"] = float(holding["volume24"])
    if holding.get("change24") not in (None, ""):
        entry["change24"] = float(holding["change24"])
    created = normalize_created_at(holding.get("createdAt") or entry.get("createdAt"))
    if created:
        entry["createdAt"] = created
    cache[addr] = entry

def meta_from_cache_or_holding(cache: dict, addr: str, holders: list[dict] | None = None) -> dict:
    key = _norm_addr(addr)
    meta = {}
    if isinstance(cache.get(key), dict):
        meta = dict(cache[key])
    if holders:
        for h in holders:
            # Holder dict uses "name" for trader nickname; token name is "rawName".
            token_name = (h.get("rawName") or "").strip()
            if float(h.get("marketCap") or 0) > 0 or h.get("change24") not in (None, ""):
                for field in (
                    "symbol",
                    "networkId",
                    "priceUsd",
                    "marketCap",
                    "volume24",
                    "change24",
                    "createdAt",
                ):
                    if h.get(field) not in (None, ""):
                        meta[field] = h.get(field)
                if token_name:
                    meta["name"] = token_name
                break
            if not meta.get("symbol") and h.get("symbol"):
                meta["symbol"] = h["symbol"]
            if not meta.get("name") and token_name:
                meta["name"] = token_name
            if not meta.get("createdAt") and h.get("createdAt"):
                meta["createdAt"] = h["createdAt"]
            if meta.get("networkId") is None and h.get("networkId") is not None:
                meta["networkId"] = h["networkId"]
    if meta.get("createdAt"):
        meta["createdAt"] = normalize_created_at(meta.get("createdAt"))
    return meta


def test_auth(token: str | None = None) -> dict:
    """Probe /config then a public top trader balances endpoint."""
    try:
        data = fomo_get("/config", token=token)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    status = data.get("statusCode")
    if data.get("error") == "unauthorized" or status in (401, 403, 430, 431):
        return {
            "ok": False,
            "error": "unauthorized",
            "statusCode": status,
            "hint": (
                "FOMO 返回 unauthorized。请点「用 Google 登录」，"
                "或对状态为 200 的 prod-api 请求 Copy as cURL 再保存。"
            ),
            "detail": {k: data.get(k) for k in ("error", "message", "statusCode") if k in data},
        }
    if data.get("success") or status in (None, 200) or "responseObject" in data:
        return {"ok": True, "endpoint": "/config", "statusCode": status or 200}
    return {"ok": False, "error": "unexpected", "detail": data}
