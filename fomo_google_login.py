# -*- coding: utf-8 -*-
"""Open a real Chrome window so the user can Google-login on fomo.family, then capture Privy tokens."""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from fomo_auth import AUTH_PATH, extract_privy_session, save_auth, test_auth

FOMO_URL = "https://fomo.family/"
USER_DATA_DIR = AUTH_PATH.parent / ".playwright-fomo-chrome"
LOGIN_TIMEOUT_SEC = 300
STORE_URL_RE = re.compile(
    r"play\.google\.com|apps\.apple\.com|itunes\.apple\.com|google\.com/store",
    re.I,
)
BAD_STORE_TEXT_RE = re.compile(
    r"google play|play store|app store|get it on|download (the )?app",
    re.I,
)
GOOD_GOOGLE_LOGIN_RE = re.compile(
    r"^(continue with google|sign in with google|sign up with google|"
    r"使用 google|用 google(登录|登入|登陸)?|google)$",
    re.I,
)

DUMP_STORAGE_JS = """
() => {
  const out = {};
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k) out[k] = localStorage.getItem(k);
    }
  } catch (e) {}
  return out;
}
"""

CLICK_LOGIN_JS = """
() => {
  const needles = ["log in", "login", "sign in", "signin", "登录", "登陸"];
  const storeHref = /play\\.google|apps\\.apple|itunes\\.apple|google\\.com\\/store/i;
  const nodes = Array.from(document.querySelectorAll('button, a, [role="button"]'));
  for (const el of nodes) {
    const href = (el.href || (el.closest && el.closest('a') && el.closest('a').href) || '');
    if (storeHref.test(href)) continue;
    const t = (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim().toLowerCase();
    if (!t || t.length > 40) continue;
    if (/google play|play store|app store|download/.test(t)) continue;
    if (needles.some((n) => t === n || t.startsWith(n + " "))) {
      el.click();
      return t;
    }
  }
  return "";
}
"""

CLICK_GOOGLE_JS = """
() => {
  const storeHref = /play\\.google|apps\\.apple|itunes\\.apple|google\\.com\\/store/i;
  const badText = /google play|play store|app store|get it on|download (the )?app/i;
  const goodText = /^(continue with google|sign in with google|sign up with google|使用 google|用 google(登录|登入|登陸)?|google)$/i;
  const nodes = Array.from(document.querySelectorAll('button, [role="button"]'));
  for (const el of nodes) {
    if (el.tagName && el.tagName.toLowerCase() === 'a') continue;
    const anchor = el.closest ? el.closest('a') : null;
    const href = (anchor && anchor.href) || el.href || '';
    if (storeHref.test(href)) continue;
    const t = (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
    const aria = (el.getAttribute("aria-label") || "").replace(/\\s+/g, " ").trim();
    if (badText.test(t) || badText.test(aria)) continue;
    if (goodText.test(t) || goodText.test(aria)) {
      el.click();
      return t || aria;
    }
  }
  return "";
}
"""


def is_store_url(url: str) -> bool:
    return bool(STORE_URL_RE.search(url or ""))


def is_google_login_target(
    *,
    tag: str,
    text: str,
    aria: str = "",
    href: str = "",
) -> bool:
    """True only for Privy/Google OAuth buttons, never Play/App Store badges."""
    if (tag or "").lower() == "a":
        return False
    if is_store_url(href):
        return False
    blob = f"{text or ''} {aria or ''}"
    if BAD_STORE_TEXT_RE.search(blob):
        return False
    norm_text = re.sub(r"\s+", " ", (text or "").strip())
    norm_aria = re.sub(r"\s+", " ", (aria or "").strip())
    return bool(GOOD_GOOGLE_LOGIN_RE.match(norm_text) or GOOD_GOOGLE_LOGIN_RE.match(norm_aria))

_lock = threading.Lock()
_job: dict[str, Any] = {
    "status": "idle",
    "progress": "",
    "error": None,
    "tokenPreview": "",
    "hasRefresh": False,
    "testOk": None,
    "testError": "",
}
_cancel = threading.Event()


def login_status() -> dict:
    with _lock:
        return {
            "ok": True,
            **_job,
        }


def request_cancel() -> dict:
    _cancel.set()
    with _lock:
        if _job["status"] == "running":
            _job["progress"] = "正在取消…"
    return login_status()


NO_BROWSER_MSG = "未找到可用浏览器。请安装 Google Chrome，或运行: python -m playwright install chromium"


def playwright_unavailable_reason() -> str | None:
    """Why headed Playwright login cannot run on this machine, or None if it can."""
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return NO_BROWSER_MSG
    if _system_chrome_exists():
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "缺少 playwright。请运行: pip install playwright && python -m playwright install chrome"
    try:
        with sync_playwright() as p:
            exe = getattr(p.chromium, "executable_path", "") or ""
            if exe and Path(exe).is_file():
                return None
    except Exception:
        pass
    return NO_BROWSER_MSG


def _system_chrome_exists() -> bool:
    if sys.platform == "win32":
        roots = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        for root in roots:
            if not root:
                continue
            candidate = Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if candidate.is_file():
                return True
        return False
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if shutil.which(name):
            return True
    return False


def start_google_login() -> dict:
    reason = playwright_unavailable_reason()
    if reason:
        raise RuntimeError(reason)
    with _lock:
        if _job["status"] == "running":
            return {
                "ok": True,
                "started": False,
                "message": "已有登录窗口在等待",
                **{k: _job[k] for k in ("status", "progress")},
            }
        _job.update(
            {
                "status": "running",
                "progress": "正在打开 Chrome…",
                "error": None,
                "tokenPreview": "",
                "hasRefresh": False,
                "testOk": None,
                "testError": "",
            }
        )
    _cancel.clear()
    threading.Thread(target=_run_login, name="fomo-google-login", daemon=True).start()
    return {"ok": True, "started": True, "status": "running", "progress": "正在打开 Chrome…"}


def _set_progress(msg: str) -> None:
    with _lock:
        if _job["status"] == "running":
            _job["progress"] = msg


def _run_login() -> None:
    try:
        session = capture_google_login(
            progress=_set_progress,
            should_cancel=_cancel.is_set,
        )
        saved = save_auth(
            session["accessToken"],
            note="Captured from fomo.family Google login (Playwright)",
            refresh_token=session.get("refreshToken") or "",
        )
        checked = test_auth()
        with _lock:
            _job["status"] = "done"
            _job["progress"] = "已保存 Token"
            _job["error"] = None
            _job["tokenPreview"] = saved.get("tokenPreview") or ""
            _job["hasRefresh"] = bool(saved.get("hasRefresh"))
            _job["testOk"] = bool(checked.get("ok"))
            _job["testError"] = checked.get("error") or ""
    except Exception as exc:
        if _cancel.is_set() and "取消" in str(exc):
            with _lock:
                _job["status"] = "error"
                _job["error"] = "已取消"
                _job["progress"] = "已取消"
            return
        with _lock:
            _job["status"] = "error"
            _job["error"] = str(exc)
            _job["progress"] = "登录失败"


def capture_google_login(
    *,
    progress: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    timeout_sec: int = LOGIN_TIMEOUT_SEC,
) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "缺少 playwright。请运行: pip install playwright && python -m playwright install chrome"
        ) from exc

    def log(msg: str) -> None:
        if progress:
            progress(msg)

    def cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    captured: dict[str, Any] = {"authenticate": None, "headers": []}
    context = None

    with sync_playwright() as p:
        context = _launch_context(p)

        context.on("response", lambda resp: _on_response(resp, captured))
        context.on("page", lambda pg: _watch_and_close_store_page(pg))
        page = context.pages[0] if context.pages else context.new_page()
        log("正在打开 fomo.family…")
        try:
            page.goto(FOMO_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:
            _safe_close(context)
            raise RuntimeError(f"打开 fomo.family 失败：{exc}") from exc

        deadline = time.time() + timeout_sec
        last_click = 0.0
        google_clicked = False
        login_clicks = 0
        while time.time() < deadline:
            if cancelled():
                _safe_close(context)
                raise RuntimeError("已取消")

            _close_store_pages(context)
            try:
                if is_store_url(page.url or ""):
                    page.goto(FOMO_URL, wait_until="domcontentloaded", timeout=20000)
            except Exception:
                pass

            session = _collect_session(context, captured)
            if session.get("accessToken"):
                time.sleep(1.2)
                session = _collect_session(context, captured) or session
                log("已检测到登录，正在保存 Token…")
                _safe_close(context)
                return session

            now = time.time()
            if now - last_click >= 2.5 and not google_clicked:
                clicked = _try_click_login(context, allow_login=login_clicks < 4)
                last_click = now
                if clicked.get("login"):
                    login_clicks += 1
                if clicked.get("google"):
                    google_clicked = True
                    log("已点击 Google 登录，请在窗口内完成授权…")
            if not google_clicked:
                log("请在弹出的 Chrome 里打开登录，并点 Continue with Google…")
            page.wait_for_timeout(800)

        _safe_close(context)
        raise RuntimeError("等待 Google 登录超时（5 分钟）。请重试并在窗口内完成登录。")


def _launch_context(p):
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    kwargs = {
        "headless": False,
        "viewport": {"width": 1280, "height": 860},
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ],
        "ignore_default_args": ["--enable-automation"],
    }
    try:
        return p.chromium.launch_persistent_context(
            str(USER_DATA_DIR),
            channel="chrome",
            **kwargs,
        )
    except Exception as first:
        hint = str(first)
        if "ProcessSingleton" in hint or "already running" in hint.lower() or "lock" in hint.lower():
            raise RuntimeError("登录浏览器配置目录被占用，请先关掉上次弹出的 Chrome 窗口后再试。") from first
        try:
            return p.chromium.launch_persistent_context(str(USER_DATA_DIR), **kwargs)
        except Exception as exc:
            hint = str(exc)
            if "Executable doesn't exist" in hint or "chromium" in hint.lower():
                raise RuntimeError(NO_BROWSER_MSG) from exc
            if "ProcessSingleton" in hint or "already running" in hint.lower() or "lock" in hint.lower():
                raise RuntimeError("登录浏览器配置目录被占用，请先关掉上次弹出的 Chrome 窗口后再试。") from exc
            raise RuntimeError(f"无法启动 Chrome：{exc}") from exc


def _safe_close(context) -> None:
    if context is None:
        return
    try:
        context.close()
    except Exception:
        pass


def _on_response(response, captured: dict[str, Any]) -> None:
    try:
        url = response.url or ""
        if "auth.privy.io" in url and "/oauth/authenticate" in url and response.status == 200:
            payload = response.json()
            if isinstance(payload, dict) and (
                payload.get("token") or payload.get("access_token") or payload.get("refresh_token")
            ):
                captured["authenticate"] = payload
        headers = response.request.headers or {}
        auth = headers.get("authorization") or headers.get("Authorization") or ""
        if (
            auth.lower().startswith("bearer ")
            and "prod-api.fomo.family" in url
        ):
            captured["headers"].append(auth)
    except Exception:
        return


def _collect_session(context, captured: dict[str, Any]) -> dict:
    storage: dict[str, str] = {}
    for pg in list(context.pages):
        try:
            if "fomo.family" not in (pg.url or ""):
                continue
            dumped = pg.evaluate(DUMP_STORAGE_JS)
            if isinstance(dumped, dict):
                storage.update({str(k): ("" if v is None else str(v)) for k, v in dumped.items()})
        except Exception:
            continue
    return extract_privy_session(
        storage,
        authorization_headers=list(captured.get("headers") or []),
        authenticate_payload=captured.get("authenticate"),
    )


def _watch_and_close_store_page(page) -> None:
    def maybe_close() -> None:
        try:
            if is_store_url(page.url or ""):
                page.close()
        except Exception:
            return

    try:
        maybe_close()
        page.on("load", lambda: maybe_close())
        page.on("framenavigated", lambda frame: maybe_close() if frame == page.main_frame else None)
    except Exception:
        return


def _close_store_pages(context) -> None:
    for pg in list(context.pages):
        try:
            if is_store_url(pg.url or ""):
                pg.close()
        except Exception:
            continue


def _try_click_login(context, *, allow_login: bool = True) -> dict:
    clicked = {"login": "", "google": ""}
    for pg in list(context.pages):
        try:
            url = pg.url or ""
            if "fomo.family" not in url or is_store_url(url):
                continue
            if allow_login:
                clicked["login"] = pg.evaluate(CLICK_LOGIN_JS) or clicked["login"]
                pg.wait_for_timeout(400)
            clicked["google"] = pg.evaluate(CLICK_GOOGLE_JS) or clicked["google"]
        except Exception:
            continue
    return clicked
