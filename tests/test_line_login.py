import datetime
import unittest
from urllib.parse import parse_qs, urlparse

from flask import Flask

from stock_papi.services.auth import (
    LineLoginConfig,
    create_pkce_pair,
    safe_return_path,
    sign_opaque_token,
    verify_line_claims,
)
from stock_papi.web.routes.auth import register_auth_routes
from stock_papi.shared.logging import redact_secrets


NOW = datetime.datetime(2026, 7, 13, 4, 0, tzinfo=datetime.timezone.utc)
USER_ID = "U" + "a" * 32


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self):
        self.calls = []
        self.nonce = None
        self.token_status = 200
        self.verify_status = 200
        self.claim_overrides = {}

    def post(self, url, *, data, timeout):
        self.calls.append((url, dict(data), timeout))
        if url.endswith("/token"):
            return FakeResponse(self.token_status, {"id_token": "verified.id.token"})
        claims = {
            "iss": "https://access.line.me",
            "aud": "1234567890",
            "exp": int(NOW.timestamp()) + 300,
            "nonce": self.nonce,
            "sub": USER_ID,
            "name": "測試使用者",
            "picture": "https://profile.line-scdn.net/avatar.png",
        }
        claims.update(self.claim_overrides)
        return FakeResponse(self.verify_status, claims)


class FakeAuthStore:
    def __init__(self):
        self.attempts = {}
        self.sessions = {}
        self.users = {}
        self.deleted_sessions = []

    def create_oauth_attempt(self, attempt_id, value):
        if attempt_id in self.attempts:
            raise RuntimeError("collision")
        self.attempts[attempt_id] = dict(value)

    def consume_oauth_attempt(self, attempt_id, now):
        value = self.attempts.pop(attempt_id, None)
        if value is None or value["expires_at"] <= now:
            return None
        return value

    def create_session(self, session_id, value):
        self.sessions[session_id] = dict(value)

    def load_session(self, session_id, now):
        value = self.sessions.get(session_id)
        return dict(value) if value and value["expires_at"] > now else None

    def delete_session(self, session_id):
        self.deleted_sessions.append(session_id)
        self.sessions.pop(session_id, None)

    def upsert_user(self, user_id, profile):
        existing = self.users.get(user_id, {"login_count": 0, "created_at": NOW})
        existing.update(profile)
        existing["login_count"] += 1
        self.users[user_id] = existing
        return dict(existing)

    def get_user(self, user_id):
        value = self.users.get(user_id)
        return dict(value) if value else None


class FakeLineStore:
    def __init__(self):
        self.users = {}
        self.updated_user_ids = []

    def load(self, user_id):
        state = self.users.setdefault(user_id, {
            "watchlist": [], "alerts": [], "pending": {},
            "signals": {"as_of": None, "items": []},
        })
        return state, None

    def update(self, user_id, mutate):
        state, _ = self.load(user_id)
        mutate(state)
        self.updated_user_ids.append(user_id)
        return state


class LineLoginTests(unittest.TestCase):
    def setUp(self):
        self.auth_store = FakeAuthStore()
        self.line_store = FakeLineStore()
        self.http = FakeHttp()
        self.config = LineLoginConfig(
            channel_id="1234567890",
            channel_secret="channel-secret",
            redirect_uri="http://localhost/auth/line/callback",
            session_secret="s" * 32,
            cookie_secure=False,
        )
        app = Flask(__name__, template_folder="../templates", static_folder="../static")
        app.config.update(TESTING=True)
        register_auth_routes(
            app,
            config=self.config,
            auth_store=lambda: self.auth_store,
            line_store=lambda: self.line_store,
            search_stock=lambda code: (code, "台積電") if code == "2330" else (None, None),
            http_post=self.http.post,
            now=lambda: NOW,
        )
        self.client = app.test_client()

    def _start_login(self, return_to="/stock/2330"):
        response = self.client.get("/auth/line/login", query_string={"return_to": return_to})
        query = parse_qs(urlparse(response.headers["Location"]).query)
        self.http.nonce = query["nonce"][0]
        return response, query

    def _login(self):
        _response, query = self._start_login()
        return self.client.get("/auth/line/callback", query_string={
            "code": "authorization-code", "state": query["state"][0],
        })

    def test_pkce_and_safe_return_path(self):
        verifier, challenge = create_pkce_pair()

        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)
        self.assertNotEqual(verifier, challenge)
        self.assertEqual(safe_return_path("/stock/2330?tab=risk"), "/stock/2330?tab=risk")
        for unsafe in ("https://evil.test", "//evil.test", "/\\evil", "/%0d%0aX", "stock/2330"):
            self.assertEqual(safe_return_path(unsafe), "/")
        self.assertFalse(LineLoginConfig(
            "1234567890", "secret", "https://app.example/callback", "s" * 32,
            cookie_secure=False,
        ).configured)
        self.assertFalse(LineLoginConfig(
            "1234567890", "secret", "http://localhost/callback", "s" * 32,
            cookie_secure=True,
        ).configured)

    def test_login_generates_state_nonce_pkce_and_server_attempt(self):
        response, query = self._start_login()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlparse(response.headers["Location"]).netloc, "access.line.me")
        self.assertEqual(query["scope"], ["openid profile"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(len(self.auth_store.attempts), 1)
        attempt = next(iter(self.auth_store.attempts.values()))
        self.assertEqual(attempt["nonce"], query["nonce"][0])
        self.assertNotEqual(attempt["code_verifier"], query["code_challenge"][0])
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_callback_success_verifies_id_token_rotates_session_and_returns(self):
        response = self._login()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/stock/2330"))
        self.assertEqual(len(self.auth_store.sessions), 1)
        session = next(iter(self.auth_store.sessions.values()))
        self.assertEqual(session["line_user_id"], USER_ID)
        self.assertNotIn("id_token", str(session))
        self.assertNotIn("access_token", str(session))
        self.assertEqual(self.auth_store.users[USER_ID]["plan"], "free")
        self.assertEqual(len(self.http.calls), 2)
        self.assertIn("code_verifier", self.http.calls[0][1])
        self.assertEqual(self.http.calls[1][1]["nonce"], self.http.nonce)

        old_session_id = next(iter(self.auth_store.sessions))
        second = self._login()
        self.assertEqual(second.status_code, 302)
        self.assertIn(old_session_id, self.auth_store.deleted_sessions)
        self.assertNotIn(old_session_id, self.auth_store.sessions)

    def test_state_mismatch_cancel_token_failure_and_replay_fail_closed(self):
        _response, query = self._start_login()
        mismatch = self.client.get("/auth/line/callback", query_string={"code": "x", "state": "wrong"})
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(self.http.calls, [])

        cancelled = self.client.get("/auth/line/callback", query_string={"error": "access_denied"})
        self.assertEqual(cancelled.status_code, 400)

        _response, query = self._start_login()
        self.http.token_status = 500
        failure = self.client.get("/auth/line/callback", query_string={"code": "x", "state": query["state"][0]})
        self.assertEqual(failure.status_code, 503)
        replay = self.client.get("/auth/line/callback", query_string={"code": "x", "state": query["state"][0]})
        self.assertEqual(replay.status_code, 400)

    def test_claim_validation_rejects_issuer_audience_expiry_nonce_and_subject(self):
        base = {
            "iss": "https://access.line.me", "aud": self.config.channel_id,
            "exp": int(NOW.timestamp()) + 60, "nonce": "nonce", "sub": USER_ID,
            "name": "使用者", "picture": "https://example.com/avatar.png",
        }
        cases = (
            {"iss": "https://evil.test"}, {"aud": "other"},
            {"exp": int(NOW.timestamp()) - 1}, {"nonce": "wrong"},
            {"sub": "attacker"}, {"picture": "javascript:alert(1)"},
        )
        for change in cases:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    verify_line_claims({**base, **change}, self.config, "nonce", NOW)

    def test_private_state_and_watchlist_are_session_isolated_and_csrf_protected(self):
        self._login()
        state = self.client.get("/api/account/state")
        payload = state.get_json()
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.headers["Cache-Control"], "private, no-store")
        self.assertEqual(payload["user"]["display_name"], "測試使用者")

        missing_csrf = self.client.post("/api/account/watchlist", json={"action": "add", "code": "2330"})
        self.assertEqual(missing_csrf.status_code, 403)
        added = self.client.post(
            "/api/account/watchlist",
            json={"action": "add", "code": "2330", "line_user_id": "U" + "b" * 32},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        self.assertEqual(added.status_code, 200)
        self.assertEqual(self.line_store.updated_user_ids, [USER_ID])
        self.assertEqual(self.line_store.users[USER_ID]["watchlist"][0]["code"], "2330")
        self.assertNotIn("U" + "b" * 32, self.line_store.users)

    def test_unauthenticated_private_routes_do_not_read_or_mutate_user_state(self):
        fresh_app = self.client.application.test_client()
        response = fresh_app.get("/api/account/state")
        mutation = fresh_app.post("/api/account/watchlist", json={"action": "add", "code": "2330"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertEqual(mutation.status_code, 401)
        self.assertEqual(self.line_store.updated_user_ids, [])

    def test_logout_requires_csrf_and_invalidates_server_session(self):
        self._login()
        payload = self.client.get("/api/account/state").get_json()
        session_id = next(iter(self.auth_store.sessions))

        self.assertEqual(self.client.post("/auth/logout").status_code, 403)
        response = self.client.post("/auth/logout", headers={"X-CSRF-Token": payload["csrf_token"]})
        self.assertEqual(response.status_code, 302)
        self.assertIn(session_id, self.auth_store.deleted_sessions)
        self.assertEqual(self.client.get("/api/account/state").status_code, 401)

    def test_missing_configuration_fails_closed_without_affecting_public_app(self):
        app = Flask("missing")
        register_auth_routes(
            app,
            config=LineLoginConfig("", "", "", "", cookie_secure=True),
            auth_store=lambda: None,
            line_store=lambda: None,
            search_stock=lambda _code: (None, None),
            http_post=self.http.post,
            now=lambda: NOW,
        )
        response = app.test_client().get("/auth/line/login")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.http.calls, [])

    def test_login_has_bounded_process_rate_limit(self):
        responses = [self.client.get("/auth/line/login") for _ in range(11)]

        self.assertTrue(all(response.status_code == 302 for response in responses[:10]))
        self.assertEqual(responses[10].status_code, 429)
        self.assertEqual(responses[10].headers["Retry-After"], "60")

    def test_line_user_id_is_redacted_from_log_text(self):
        self.assertEqual(redact_secrets(f"loaded user {USER_ID}"), "loaded user U********")


if __name__ == "__main__":
    unittest.main()
