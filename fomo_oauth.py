# -*- coding: utf-8 -*-
"""In-browser Privy/Google OAuth (no Playwright)."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlparse

from fomo_auth import (
    CURL_IMPERSONATE,
    PRIVY_APP_ID,
    PRIVY_AUTH,
    PRIVY_CLIENT_ID,
    ROOT,
    extract_privy_session,
    save_auth,
    test_auth,
)

PENDING_PATH = ROOT / "fomo_oauth_pending.json"
PENDING_TTL_SEC = 15 * 60
# Privy 只允许跳回 fomo.family。根路径 `/` 在 iOS Universal Link / Android App Link
# 里会强制打开 FOMO App，一次性 code 就被 App 吃掉。/robots.txt 是静态文本、
# 不在 App 路径名单里，也不会加载 FOMO 页面上的 Privy SDK。
FOMO_REDIRECT = "https://fomo.family/robots.txt"


def b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def create_code_verifier() -> str:
    return b64url_nopad(os.urandom(36))


def create_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256((verifier or "").encode("utf-8")).digest()
    return b64url_nopad(digest)


def parse_privy_callback(text: str) -> dict:
    """Extract privy_oauth_code / privy_oauth_state from a URL or query string."""
    raw = (text or "").strip().strip("'\"")
    if not raw:
        return {"authorization_code": "", "state_code": ""}
    candidate = raw.split()[0]
    if "privy_oauth_code" not in candidate and "authorization_code" not in candidate:
        return {"authorization_code": "", "state_code": ""}
    if "://" not in candidate and not candidate.startswith("?"):
        candidate = "https://callback.local/?" + candidate.lstrip("?&")
    elif candidate.startswith("?"):
        candidate = "https://callback.local/" + candidate
    parsed = urlparse(candidate)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.fragment and "privy_oauth_code" in parsed.fragment:
        qs.update(parse_qs(parsed.fragment, keep_blank_values=True))
    code = (qs.get("privy_oauth_code") or qs.get("authorization_code") or [""])[0]
    state = (qs.get("privy_oauth_state") or qs.get("state_code") or qs.get("state") or [""])[0]
    return {
        "authorization_code": unquote(code or "").strip(),
        "state_code": unquote(state or "").strip(),
    }


def _load_pending() -> dict:
    if not PENDING_PATH.exists():
        return {}
    try:
        data = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_pending(data: dict) -> None:
    PENDING_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _prune_pending(data: dict, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    out = {}
    for key, row in (data or {}).items():
        if key in ("updatedAt",):
            continue
        if not isinstance(row, dict):
            continue
        created = float(row.get("createdAt") or 0)
        if created and now - created > PENDING_TTL_SEC:
            continue
        out[key] = row
    return out


def start_browser_google_oauth() -> dict:
    verifier = create_code_verifier()
    state = create_code_verifier()
    challenge = create_code_challenge(verifier)
    try:
        from curl_cffi import requests as crequests
    except ImportError as exc:
        raise RuntimeError("缺少 curl_cffi，请运行: pip install curl_cffi") from exc

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "origin": "https://fomo.family",
        "referer": "https://fomo.family/",
        "privy-app-id": PRIVY_APP_ID,
        "privy-client-id": PRIVY_CLIENT_ID,
        "privy-client": "react-auth:3.34.0",
    }
    resp = crequests.post(
        f"{PRIVY_AUTH}/api/v1/oauth/init",
        headers=headers,
        json={
            "provider": "google",
            "redirect_to": FOMO_REDIRECT,
            "code_challenge": challenge,
            "state_code": state,
        },
        impersonate=CURL_IMPERSONATE,
        timeout=30,
    )
    try:
        body = resp.json() if resp.content else {}
    except Exception:
        body = {}
    url = (body.get("url") or "") if isinstance(body, dict) else ""
    if resp.status_code >= 400 or not url:
        err = ""
        if isinstance(body, dict):
            err = body.get("error") or body.get("message") or ""
        raise RuntimeError(err or f"Privy OAuth 初始化失败 HTTP {resp.status_code}")

    pending = _prune_pending(_load_pending())
    pending[state] = {
        "codeVerifier": verifier,
        "codeChallenge": challenge,
        "createdAt": time.time(),
        "createdAtIso": datetime.now(timezone.utc).isoformat(),
    }
    pending["updatedAt"] = datetime.now(timezone.utc).isoformat()
    _save_pending(pending)
    return {
        "ok": True,
        "started": True,
        "mode": "browser",
        "url": url,
        "progress": "请用 Google 登录。完成后会打开一段英文文本页，请留在浏览器（不要打开 FOMO App），复制顶部完整地址贴回本页保存",
    }


def complete_browser_google_oauth(callback_text: str) -> dict:
    parsed = parse_privy_callback(callback_text)
    code = parsed["authorization_code"]
    state = parsed["state_code"]
    if not code:
        raise ValueError("未解析到 privy_oauth_code，请粘贴登录后的 fomo.family 完整链接")
    pending = _prune_pending(_load_pending())
    row = pending.get(state) if state else None
    if not isinstance(row, dict):
        # state 对不上时，尝试最近一条（部分回调会改写 state）
        newest = None
        newest_ts = -1.0
        for key, item in pending.items():
            if key == "updatedAt" or not isinstance(item, dict):
                continue
            ts = float(item.get("createdAt") or 0)
            if ts > newest_ts:
                newest_ts = ts
                newest = item
        row = newest
    if not isinstance(row, dict) or not row.get("codeVerifier"):
        raise RuntimeError("找不到这次登录的校验码，请重新点「用 Google 登录」")

    try:
        from curl_cffi import requests as crequests
    except ImportError as exc:
        raise RuntimeError("缺少 curl_cffi，请运行: pip install curl_cffi") from exc

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "origin": "https://fomo.family",
        "referer": "https://fomo.family/",
        "privy-app-id": PRIVY_APP_ID,
        "privy-client-id": PRIVY_CLIENT_ID,
        "privy-client": "react-auth:3.34.0",
    }
    resp = crequests.post(
        f"{PRIVY_AUTH}/api/v1/oauth/authenticate",
        headers=headers,
        json={
            "authorization_code": code,
            "state_code": state or "",
            "code_verifier": row["codeVerifier"],
            "mode": "login-or-sign-up",
        },
        impersonate=CURL_IMPERSONATE,
        timeout=40,
    )
    try:
        body = resp.json() if resp.content else {}
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    extracted = extract_privy_session(authenticate_payload=body)
    token = extracted["accessToken"]
    if resp.status_code >= 400 or not token:
        err = body.get("error") or body.get("message") or f"HTTP {resp.status_code}"
        raise RuntimeError(f"换票失败：{err}。请重新登录，或改为粘贴 Bearer Token。")

    saved = save_auth(
        token,
        note="Browser Google OAuth (Privy)",
        refresh_token=extracted.get("refreshToken") or "",
    )
    if state and state in pending:
        pending.pop(state, None)
        _save_pending(_prune_pending(pending))
    checked = test_auth()
    return {
        "ok": True,
        **saved,
        "test": checked,
        "testOk": bool(checked.get("ok")),
        "testError": checked.get("error") or "",
    }
