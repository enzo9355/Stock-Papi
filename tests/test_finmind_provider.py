import unittest
from unittest.mock import Mock

import pandas as pd
import requests

from stock_papi.integrations.market_data import provider


class FakeResponse:
    def __init__(self, status_code=200, payload=None, *, headers=None, json_error=None):
        self.status_code = status_code
        self.payload = {"data": []} if payload is None else payload
        self.headers = headers or {}
        self.json_error = json_error

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FinMindProviderTests(unittest.TestCase):
    def fetch(
        self,
        response=None,
        *,
        blocked_until=0,
        now=1000,
        get_error=None,
        get_side_effect=None,
        retry_attempts=2,
    ):
        get = Mock(return_value=response)
        if get_side_effect is not None:
            get.side_effect = get_side_effect
        elif get_error is not None:
            get.side_effect = get_error
        logger = Mock()
        login = Mock()
        sleep = Mock()
        self.last_logger = logger
        self.last_get = get
        self.last_sleep = sleep
        result = provider.fetch_finmind_dataset(
            "TaiwanStockPrice",
            "2330",
            "2026-07-01",
            "2026-07-23",
            blocked_until=blocked_until,
            now=lambda: now,
            login=login,
            token=lambda: "live-token-must-not-leak",
            requests_module=Mock(
                get=get,
                RequestException=requests.RequestException,
                Timeout=requests.Timeout,
                ConnectionError=requests.ConnectionError,
            ),
            pd=pd,
            logger=logger,
            sleep_fn=sleep,
            retry_attempts=retry_attempts,
        )
        return result, get, logger, login

    def assert_fetch_error(self, response=None, **kwargs):
        error_type = getattr(provider, "FinMindFetchError", RuntimeError)
        with self.assertRaises(error_type) as caught:
            self.fetch(response, **kwargs)
        return caught.exception

    def login(self, *, current_token=None, user="", password="", response=None, error=None):
        post = Mock(return_value=response)
        if error is not None:
            post.side_effect = error
        logger = Mock()
        requests_module = Mock(
            post=post,
            RequestException=requests.RequestException,
            Timeout=requests.Timeout,
            ConnectionError=requests.ConnectionError,
        )
        self.last_login_logger = logger
        result = provider.finmind_login(
            current_token,
            user,
            password,
            requests_module,
            logger=logger,
        )
        return result, post, logger

    def assert_login_error(self, **kwargs):
        with self.assertRaises(provider.FinMindFetchError) as caught:
            self.login(**kwargs)
        return caught.exception

    def test_login_allows_anonymous_mode_without_credentials(self):
        token, post, logger = self.login()

        self.assertIsNone(token)
        post.assert_not_called()
        logger.warning.assert_not_called()

    def test_login_reuses_existing_token_without_request(self):
        token, post, logger = self.login(
            current_token="existing-token-must-not-leak",
            user="configured-user",
            **{"pass" + "word": "configured-" + "value"},
        )

        self.assertEqual(token, "existing-token-must-not-leak")
        post.assert_not_called()
        logger.warning.assert_not_called()

    def test_login_accepts_only_valid_success_payload(self):
        token, post, logger = self.login(
            user="configured-user",
            response=FakeResponse(
                payload={"msg": "success", "token": "new-token-must-not-leak"}
            ),
            **{"pass" + "word": "configured-" + "value"},
        )

        self.assertEqual(token, "new-token-must-not-leak")
        self.assertEqual(post.call_count, 1)
        logger.warning.assert_not_called()
        self.assertNotIn("new-token-must-not-leak", str(logger.mock_calls))

    def test_login_failures_have_safe_structured_categories(self):
        unsafe = "credential-must-not-leak"
        cases = (
            (
                "login_timeout",
                {"error": requests.Timeout(unsafe)},
            ),
            (
                "login_network_error",
                {"error": requests.ConnectionError(unsafe)},
            ),
            (
                "login_network_error",
                {
                    "response": FakeResponse(
                        status_code=503,
                        payload={"msg": unsafe},
                    )
                },
            ),
            (
                "login_invalid_json",
                {"response": FakeResponse(json_error=ValueError(unsafe))},
            ),
            (
                "login_invalid_payload",
                {"response": FakeResponse(payload=["not", "a", "dict"])},
            ),
            (
                "login_authentication",
                {
                    "response": FakeResponse(
                        status_code=401,
                        payload={"msg": unsafe, "token": unsafe},
                    )
                },
            ),
            (
                "login_authentication",
                {"response": FakeResponse(payload={"msg": unsafe})},
            ),
            (
                "login_invalid_payload",
                {
                    "response": FakeResponse(
                        payload={"msg": "success", "token": ""}
                    )
                },
            ),
        )
        for category, behavior in cases:
            with self.subTest(category=category, behavior=tuple(behavior)):
                error = self.assert_login_error(
                    user="configured-user",
                    **{"pass" + "word": unsafe},
                    **behavior,
                )
                logger = self.last_login_logger
                self.assertEqual(error.category, category)
                self.assertTrue(error.provider_wide)
                serialized = str(error.to_dict()) + str(logger.mock_calls)
                self.assertNotIn(unsafe, serialized)
                self.assertNotIn("configured-user", serialized)
                self.assertEqual(logger.warning.call_count, 1)

    def test_valid_data_returns_dataframe(self):
        (frame, blocked_until), get, logger, login = self.fetch(
            FakeResponse(payload={"data": [{"date": "2026-07-23", "close": 100}]})
        )

        self.assertEqual(frame.to_dict("records"), [{"date": "2026-07-23", "close": 100}])
        self.assertEqual(blocked_until, 0)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(login.call_count, 1)
        logger.warning.assert_not_called()

    def test_empty_dataset_has_its_own_category(self):
        error = self.assert_fetch_error(FakeResponse(payload={"data": []}))

        self.assertEqual(error.category, "empty_dataset")
        self.assertIsNone(error.http_status)
        self.assertFalse(error.provider_wide)

    def test_402_and_403_block_the_provider_with_safe_categories(self):
        expectations = {
            402: ("quota_or_rate_limit", 3600),
            403: ("authentication_or_permission", 1800),
        }
        for status, (category, retry_after) in expectations.items():
            with self.subTest(status=status):
                error = self.assert_fetch_error(
                    FakeResponse(
                        status_code=status,
                        payload={
                            "msg": "token=live-token-must-not-leak\n"
                            + "pass"
                            + "word=must-not-leak"
                        },
                    )
                )

                self.assertEqual(error.category, category)
                self.assertEqual(error.http_status, status)
                self.assertEqual(error.retry_after_seconds, retry_after)
                self.assertEqual(error.blocked_until, 1000 + retry_after)
                self.assertTrue(error.provider_wide)
                serialized = str(error.to_dict())
                self.assertNotIn("live-token-must-not-leak", serialized)
                self.assertNotIn("must-not-leak", serialized)
                self.assertNotIn("\n", error.safe_message)
                self.assertEqual(self.last_logger.warning.call_count, 1)
                logged = str(self.last_logger.warning.call_args)
                self.assertNotIn("live-token-must-not-leak", logged)
                self.assertNotIn("must-not-leak", logged)
                self.assertRegex(
                    error.safe_message,
                    r"blocked_until=\d{4}-\d{2}-\d{2}T",
                )
                self.assertEqual(self.last_get.call_count, 1)
                self.last_sleep.assert_not_called()

    def test_429_uses_retry_after_and_blocks_provider(self):
        error = self.assert_fetch_error(
            FakeResponse(
                status_code=429,
                payload={"msg": "too many requests"},
                headers={"Retry-After": "17"},
            )
        )

        self.assertEqual(error.category, "quota_or_rate_limit")
        self.assertEqual(error.retry_after_seconds, 17)
        self.assertEqual(error.blocked_until, 1017)
        self.assertTrue(error.provider_wide)
        self.assertEqual(self.last_get.call_count, 1)
        self.last_sleep.assert_not_called()

    def test_timeout_and_connection_errors_keep_safe_categories(self):
        for exception, category in (
            (requests.Timeout("token=live-token-must-not-leak"), "timeout"),
            (
                requests.ConnectionError("pass" + "word=must-not-leak"),
                "network_error",
            ),
        ):
            with self.subTest(category=category):
                error = self.assert_fetch_error(get_error=exception)
                self.assertEqual(error.category, category)
                self.assertEqual(error.exception_type, type(exception).__name__)
                self.assertTrue(error.provider_wide)
                self.assertNotIn("must-not-leak", error.safe_message)
                self.assertEqual(self.last_get.call_count, 3)
                self.assertEqual(
                    [call.args[0] for call in self.last_sleep.call_args_list],
                    [1, 2],
                )
                self.assertEqual(self.last_logger.warning.call_count, 1)

    def test_transient_network_failure_retries_then_succeeds(self):
        (frame, _), get, logger, _ = self.fetch(
            get_side_effect=[
                requests.Timeout("unsafe first failure"),
                requests.ConnectionError("unsafe second failure"),
                FakeResponse(payload={"data": [{"value": 1}]}),
            ],
        )

        self.assertEqual(frame.to_dict("records"), [{"value": 1}])
        self.assertEqual(get.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in self.last_sleep.call_args_list],
            [1, 2],
        )
        logger.warning.assert_not_called()

    def test_retry_attempts_are_hard_capped_and_can_be_disabled(self):
        error = self.assert_fetch_error(
            get_side_effect=[
                requests.Timeout("unsafe"),
                requests.Timeout("unsafe"),
                requests.Timeout("unsafe"),
                FakeResponse(payload={"data": [{"value": 1}]}),
            ],
            retry_attempts=99,
        )
        self.assertEqual(error.category, "timeout")
        self.assertEqual(self.last_get.call_count, 3)

        error = self.assert_fetch_error(
            get_error=requests.Timeout("unsafe"),
            retry_attempts=0,
        )
        self.assertEqual(error.category, "timeout")
        self.assertEqual(self.last_get.call_count, 1)
        self.last_sleep.assert_not_called()

    def test_transient_5xx_retries_once_and_logs_only_final_failure(self):
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                (frame, _), get, logger, _ = self.fetch(
                    get_side_effect=[
                        FakeResponse(status_code=status, payload={"msg": "unsafe"}),
                        FakeResponse(payload={"data": [{"value": 1}]}),
                    ],
                )
                self.assertEqual(frame.to_dict("records"), [{"value": 1}])
                self.assertEqual(get.call_count, 2)
                self.assertEqual(
                    [call.args[0] for call in self.last_sleep.call_args_list],
                    [1],
                )
                logger.warning.assert_not_called()

        error = self.assert_fetch_error(
            get_side_effect=[
                FakeResponse(status_code=503, payload={"msg": "unsafe"}),
                FakeResponse(status_code=503, payload={"msg": "unsafe"}),
            ],
        )
        self.assertEqual(error.category, "http_error")
        self.assertEqual(self.last_get.call_count, 2)
        self.assertEqual(self.last_logger.warning.call_count, 1)

    def test_invalid_json_has_decode_category(self):
        error = self.assert_fetch_error(
            FakeResponse(json_error=ValueError("token=live-token-must-not-leak"))
        )

        self.assertEqual(error.category, "invalid_json")
        self.assertEqual(error.exception_type, "ValueError")
        self.assertTrue(error.provider_wide)
        self.assertNotIn("live-token-must-not-leak", error.safe_message)
        self.assertEqual(self.last_get.call_count, 1)
        self.last_sleep.assert_not_called()

    def test_invalid_payload_has_payload_category(self):
        error = self.assert_fetch_error(FakeResponse(payload={"data": "not-a-list"}))

        self.assertEqual(error.category, "invalid_payload")
        self.assertTrue(error.provider_wide)
        self.assertEqual(self.last_get.call_count, 1)
        self.last_sleep.assert_not_called()

    def test_5xx_keeps_http_status(self):
        error = self.assert_fetch_error(
            FakeResponse(status_code=503, payload={"msg": "backend unavailable"})
        )

        self.assertEqual(error.category, "http_error")
        self.assertEqual(error.http_status, 503)
        self.assertTrue(error.provider_wide)

    def test_active_block_fails_without_an_http_request(self):
        error_type = getattr(provider, "FinMindFetchError", RuntimeError)
        get = Mock()
        logger = Mock()
        login = Mock()
        sleep = Mock()

        with self.assertRaises(error_type) as caught:
            provider.fetch_finmind_dataset(
                "TaiwanStockPrice",
                "2330",
                "2026-07-01",
                "2026-07-23",
                blocked_until=2000,
                now=lambda: 1000,
                login=login,
                token=lambda: "live-token-must-not-leak",
                requests_module=Mock(
                    get=get,
                    RequestException=requests.RequestException,
                    Timeout=requests.Timeout,
                    ConnectionError=requests.ConnectionError,
                ),
                pd=pd,
                logger=logger,
                sleep_fn=sleep,
                retry_attempts=2,
            )

        self.assertEqual(caught.exception.category, "blocked")
        self.assertEqual(caught.exception.blocked_until, 2000)
        self.assertTrue(caught.exception.provider_wide)
        get.assert_not_called()
        login.assert_not_called()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
