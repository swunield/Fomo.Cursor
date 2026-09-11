# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fomo_auth
from fomo_auth import extract_privy_session, save_auth, load_auth
from fomo_google_login import is_google_login_target, is_store_url
from fomo_oauth import create_code_challenge, parse_privy_callback


class ExtractPrivySessionTests(unittest.TestCase):
    def test_reads_standard_localstorage_keys(self):
        got = extract_privy_session(
            {
                "privy:token": "eyJhbGciOiJaccess.aaa.bbb",
                "privy:refresh_token": "rt-local",
                "privy:id-token": "eyJhbGciOiJid.aaa.bbb",
            }
        )
        self.assertEqual(got["accessToken"], "eyJhbGciOiJaccess.aaa.bbb")
        self.assertEqual(got["refreshToken"], "rt-local")
        self.assertEqual(got["identityToken"], "eyJhbGciOiJid.aaa.bbb")

    def test_unwraps_json_quoted_values(self):
        got = extract_privy_session(
            {
                "privy:token": '"eyJhbGciOiJquoted.aaa.bbb"',
                "privy:refresh_token": '"rt-quoted"',
            }
        )
        self.assertEqual(got["accessToken"], "eyJhbGciOiJquoted.aaa.bbb")
        self.assertEqual(got["refreshToken"], "rt-quoted")

    def test_falls_back_to_authorization_header(self):
        got = extract_privy_session(
            {},
            authorization_headers=["Bearer eyJhbGciOiJhdr.aaa.bbb"],
        )
        self.assertEqual(got["accessToken"], "eyJhbGciOiJhdr.aaa.bbb")

    def test_prefers_authenticate_payload(self):
        got = extract_privy_session(
            {"privy:token": "eyJhbGciOiJold.aaa.bbb"},
            authenticate_payload={
                "token": "eyJhbGciOiJnew.aaa.bbb",
                "refresh_token": "rt-new",
                "identity_token": "eyJhbGciOiJidn.aaa.bbb",
            },
        )
        self.assertEqual(got["accessToken"], "eyJhbGciOiJnew.aaa.bbb")
        self.assertEqual(got["refreshToken"], "rt-new")
        self.assertEqual(got["identityToken"], "eyJhbGciOiJidn.aaa.bbb")

    def test_ignores_non_jwt_storage_noise(self):
        got = extract_privy_session(
            {
                "privy:ca-id": "d4869847-5de7-42c1-ac30-82a33e039734",
                "theme": "dark",
            }
        )
        self.assertEqual(got["accessToken"], "")
        self.assertEqual(got["refreshToken"], "")


class SaveAuthRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "fomo_auth.json"
        self._orig = fomo_auth.AUTH_PATH
        fomo_auth.AUTH_PATH = self.tmp

    def tearDown(self):
        fomo_auth.AUTH_PATH = self._orig
        if self.tmp.exists():
            self.tmp.unlink()
        if self.tmp.parent.exists():
            self.tmp.parent.rmdir()

    def test_save_auth_keeps_refresh_token(self):
        save_auth(
            "eyJhbGciOiJsave.aaa.bbb",
            refresh_token="rt-saved",
            note="unit-test",
        )
        data = load_auth()
        self.assertEqual(data["accessToken"], "eyJhbGciOiJsave.aaa.bbb")
        self.assertEqual(data["refreshToken"], "rt-saved")


class GoogleClickTargetTests(unittest.TestCase):
    def test_rejects_google_play_store_badge(self):
        self.assertTrue(is_store_url("https://play.google.com/store/apps/details?id=family.fomo.app"))
        self.assertFalse(
            is_google_login_target(
                tag="a",
                text="GET IT ON Google Play",
                aria="Google Play",
                href="https://play.google.com/store/apps/details?id=family.fomo.app",
            )
        )
        self.assertFalse(
            is_google_login_target(
                tag="div",
                text="Google Play",
                href="https://play.google.com/store/apps/details?id=family.fomo.app",
            )
        )

    def test_accepts_privy_google_login_button(self):
        self.assertTrue(
            is_google_login_target(tag="button", text="Continue with Google", href="")
        )
        self.assertTrue(is_google_login_target(tag="button", text="Google", href=""))
        self.assertTrue(is_google_login_target(tag="button", text="使用 Google", href=""))


class PrivyCallbackParseTests(unittest.TestCase):
    def test_parses_fomo_family_callback_url(self):
        got = parse_privy_callback(
            "https://fomo.family/?privy_oauth_code=91opRup2uZjr9dpdYZ4Qe%2BW8olt%2FrDymE1loORqzZIc%3D"
            "&privy_oauth_state=342hk7plyQwqcWbJ8ImVoX6oNT4-I9dJc2SMSNfHR-NkiamZ"
            "&privy_oauth_provider=google"
        )
        self.assertEqual(got["authorization_code"], "91opRup2uZjr9dpdYZ4Qe+W8olt/rDymE1loORqzZIc=")
        self.assertEqual(got["state_code"], "342hk7plyQwqcWbJ8ImVoX6oNT4-I9dJc2SMSNfHR-NkiamZ")

    def test_parses_robots_txt_callback_url(self):
        got = parse_privy_callback(
            "https://fomo.family/robots.txt?privy_oauth_code=abc.def"
            "&privy_oauth_state=state-1&privy_oauth_provider=google"
        )
        self.assertEqual(got["authorization_code"], "abc.def")
        self.assertEqual(got["state_code"], "state-1")

    def test_parses_raw_query_string(self):
        got = parse_privy_callback(
            "privy_oauth_code=abc.def&privy_oauth_state=state-1"
        )
        self.assertEqual(got["authorization_code"], "abc.def")
        self.assertEqual(got["state_code"], "state-1")

    def test_empty_when_not_callback(self):
        got = parse_privy_callback("eyJhbGciOiJsave.aaa.bbb")
        self.assertEqual(got["authorization_code"], "")

    def test_challenge_is_s256_base64url(self):
        # SHA256("test") = n4bQgYhMfWWaL+qgxVrQFaO/TxsrC4Is0V1sFbDwCgg=
        # urlsafe no pad: n4bQgYhMfWWaL-qgxVrQFaO_TxsrC4Is0V1sFbDwCgg
        self.assertEqual(
            create_code_challenge("test"),
            "n4bQgYhMfWWaL-qgxVrQFaO_TxsrC4Is0V1sFbDwCgg",
        )


class GoogleStartRouteTests(unittest.TestCase):
    def test_desktop_start_uses_playwright(self):
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from app import app

        with patch(
            "app.start_google_login",
            return_value={"ok": True, "started": True, "status": "running", "progress": "正在打开 Chrome…"},
        ) as playwright, patch("app.start_browser_google_oauth") as browser:
            res = TestClient(app).post("/api/auth/google/start", json={"mobile": False})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["mode"], "playwright")
        self.assertFalse(res.json().get("url"))
        playwright.assert_called_once()
        browser.assert_not_called()

    def test_desktop_start_falls_back_when_no_browser(self):
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from app import app

        with patch(
            "app.start_google_login",
            side_effect=RuntimeError("未找到可用浏览器。请安装 Google Chrome，或运行: python -m playwright install chromium"),
        ) as playwright, patch(
            "app.start_browser_google_oauth",
            return_value={
                "ok": True,
                "mode": "browser",
                "url": "https://accounts.google.com/o/oauth2/auth?x=1",
                "progress": "请用 Google 登录",
            },
        ) as browser:
            res = TestClient(app).post("/api/auth/google/start", json={"mobile": False})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("url"))
        self.assertEqual(body.get("fallback"), "browser")
        playwright.assert_called_once()
        browser.assert_called_once()

    def test_mobile_start_uses_browser_oauth_url(self):
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from app import app

        with patch("app.start_google_login") as playwright, patch(
            "app.start_browser_google_oauth",
            return_value={
                "ok": True,
                "mode": "browser",
                "url": "https://accounts.google.com/o/oauth2/auth?x=1",
            },
        ) as browser:
            res = TestClient(app).post("/api/auth/google/start", json={"mobile": True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("url"))
        browser.assert_called_once()
        playwright.assert_not_called()


class PlaywrightAvailabilityTests(unittest.TestCase):
    def test_linux_without_display_is_unavailable(self):
        from unittest.mock import patch

        from fomo_google_login import NO_BROWSER_MSG, playwright_unavailable_reason

        with patch("fomo_google_login.sys.platform", "linux"), patch.dict(
            "os.environ", {"DISPLAY": "", "WAYLAND_DISPLAY": ""}, clear=False
        ):
            # Ensure empty, not missing: pop if set
            import os

            os.environ.pop("DISPLAY", None)
            os.environ.pop("WAYLAND_DISPLAY", None)
            self.assertEqual(playwright_unavailable_reason(), NO_BROWSER_MSG)


if __name__ == "__main__":
    unittest.main()
