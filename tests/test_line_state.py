import copy
import unittest

from line_state import (
    MAX_ALERTS,
    MAX_WATCHLIST,
    PENDING_SECONDS,
    StateError,
    add_alert,
    add_watch,
    consume_pending,
    empty_state,
    evaluate_alert,
    normalize_state,
    remove_watch,
    start_pending,
    top_signals,
)


class LineStateTests(unittest.TestCase):
    def test_empty_state_and_limits_are_stable(self):
        self.assertEqual(MAX_WATCHLIST, 12)
        self.assertEqual(MAX_ALERTS, 20)
        self.assertEqual(PENDING_SECONDS, 600)
        self.assertEqual(
            empty_state(),
            {
                "watchlist": [],
                "alerts": [],
                "pending": None,
                "signals": {"as_of": None, "items": []},
            },
        )

    def test_watchlist_is_unique_and_limited_to_twelve(self):
        state = empty_state()
        for number in range(MAX_WATCHLIST):
            add_watch(state, str(1000 + number), f"股票{number}", now=1)

        add_watch(state, "1000", "股票0", now=2)

        self.assertEqual(len(state["watchlist"]), MAX_WATCHLIST)
        self.assertEqual(state["watchlist"][0]["added_at"], 1)
        with self.assertRaises(StateError):
            add_watch(state, "9999", "第十三檔", now=3)

    def test_add_watch_rejects_invalid_stock_data(self):
        for code, name in [("", "台積電"), ("23-30", "台積電"), (2330, "台積電"), ("2330", " ")]:
            with self.subTest(code=code, name=name), self.assertRaises(StateError):
                add_watch(empty_state(), code, name)

    def test_stock_codes_must_use_ascii_letters_and_digits(self):
        invalid_codes = ["台積電", "２３３０"]
        for code in invalid_codes:
            with self.subTest(operation="add_watch", code=code), self.assertRaises(StateError):
                add_watch(empty_state(), code, "台積電")

        state = normalize_state(
            {
                "watchlist": [
                    {"code": code, "name": "台積電"}
                    for code in invalid_codes
                ]
            }
        )
        self.assertEqual(state["watchlist"], [])

    def test_remove_watch_also_removes_matching_alerts(self):
        state = empty_state()
        add_watch(state, "2330", "台積電", now=1)
        add_watch(state, "2317", "鴻海", now=1)
        add_alert(state, "2330", "台積電", "price", 1000)
        other_alert = add_alert(state, "2317", "鴻海", "trend", "多頭")

        result = remove_watch(state, "2330")

        self.assertIs(result, state)
        self.assertEqual([item["code"] for item in state["watchlist"]], ["2317"])
        self.assertEqual(state["alerts"], [other_alert])

    def test_pending_success_creates_alert_and_clears_pending(self):
        state = empty_state()

        start_pending(state, "2330", "台積電", "probability", now=100)
        alert = consume_pending(state, "65", now=101)

        self.assertEqual((alert["code"], alert["kind"], alert["value"]), ("2330", "probability", 65.0))
        self.assertIsNone(state["pending"])
        self.assertEqual(state["alerts"], [alert])

    def test_pending_expires_and_rejects_invalid_values(self):
        state = empty_state()
        with self.assertRaises(StateError):
            consume_pending(state, "65", now=1)

        start_pending(state, "2330", "台積電", "price", now=100)
        with self.assertRaises(StateError):
            consume_pending(state, "900", now=701)
        self.assertIsNone(state["pending"])

        invalid_cases = [
            ("price", "not-a-number"),
            ("price", "0"),
            ("probability", "0"),
            ("probability", "100"),
        ]
        for kind, text in invalid_cases:
            with self.subTest(kind=kind, text=text):
                start_pending(state, "2330", "台積電", kind, now=100)
                with self.assertRaises(StateError):
                    consume_pending(state, text, now=101)

        with self.assertRaises(StateError):
            start_pending(state, "2330", "台積電", "trend", now=100)

    def test_start_pending_rejects_invalid_stock_data(self):
        invalid_stocks = [("", "台積電"), ("台積電", "台積電"), ("２３３０", "台積電"), ("2330", " ")]
        for code, name in invalid_stocks:
            with self.subTest(code=code, name=name), self.assertRaises(StateError):
                start_pending(empty_state(), code, name, "price", now=100)

    def test_alerts_are_limited_and_trend_values_are_validated(self):
        state = empty_state()
        for number in range(MAX_ALERTS):
            alert = add_alert(state, "2330", "台積電", "price", number + 1)
            self.assertEqual(len(alert["id"]), 32)
            self.assertTrue(alert["enabled"])
            self.assertIsNone(alert["last_triggered_date"])

        with self.assertRaises(StateError):
            add_alert(state, "2330", "台積電", "price", 21)
        with self.assertRaises(StateError):
            add_alert(empty_state(), "2330", "台積電", "trend", "盤整")
        with self.assertRaises(StateError):
            add_alert(empty_state(), "2330", "台積電", "volume", 10)

    def test_add_alert_rejects_invalid_stock_data_and_numeric_values(self):
        invalid_stocks = [("", "台積電"), ("台積電", "台積電"), ("２３３０", "台積電"), ("2330", " ")]
        for code, name in invalid_stocks:
            with self.subTest(code=code, name=name), self.assertRaises(StateError):
                add_alert(empty_state(), code, name, "price", 100)

        invalid_values = {
            "price": [True, False, 0, -1, float("nan"), float("inf"), float("-inf"), "100"],
            "probability": [True, False, 0, 100, float("nan"), float("inf"), float("-inf"), "65"],
        }
        for kind, values in invalid_values.items():
            for value in values:
                with self.subTest(kind=kind, value=value), self.assertRaises(StateError):
                    add_alert(empty_state(), "2330", "台積電", kind, value)

    def test_evaluate_alert_supports_price_probability_and_trend(self):
        quote = {"code": "2330", "price": 1000.0, "prob": 68, "trend": "多頭"}

        self.assertTrue(evaluate_alert({"kind": "price", "value": 990}, quote))
        self.assertFalse(evaluate_alert({"kind": "price", "value": 1001}, quote))
        self.assertTrue(evaluate_alert({"kind": "probability", "value": 65}, quote))
        self.assertFalse(evaluate_alert({"kind": "probability", "value": 69}, quote))
        self.assertTrue(evaluate_alert({"kind": "trend", "value": "多頭"}, quote))
        self.assertFalse(evaluate_alert({"kind": "trend", "value": "空頭"}, quote))

    def test_top_signals_sorts_copies_and_limits_results(self):
        quotes = [{"code": str(number), "prob": number, "meta": {"rank": number}} for number in range(7)]
        original = copy.deepcopy(quotes)

        signals = top_signals(quotes)
        signals[0]["meta"]["rank"] = -1

        self.assertEqual([item["prob"] for item in signals], [6, 5, 4, 3, 2])
        self.assertEqual(quotes, original)

    def test_normalize_state_drops_malformed_and_unknown_values(self):
        watchlist = [
            {"code": "2330", "name": "台積電", "added_at": 1},
            {"code": "", "name": "空代碼"},
            {"code": "23-17", "name": "非法代碼"},
            {"code": "2317", "name": " "},
            "bad",
        ] + [
            {"code": str(3000 + number), "name": f"股票{number}", "added_at": number + 2}
            for number in range(20)
        ]
        alerts = [
            {
                "id": "a1",
                "code": "2330",
                "name": "台積電",
                "kind": "price",
                "value": 1000,
                "enabled": True,
                "last_triggered_date": None,
            },
            {"id": "a2", "code": "2330", "name": "台積電", "kind": "unknown", "value": 1},
            {"id": 3, "code": "2330", "name": "台積電", "kind": "trend", "value": "多頭"},
        ] + [
            {
                "id": f"alert-{number}",
                "code": "2330",
                "name": "台積電",
                "kind": "probability",
                "value": number,
                "enabled": True,
                "last_triggered_date": None,
            }
            for number in range(1, 26)
        ]
        value = {
            "watchlist": watchlist,
            "alerts": alerts,
            "pending": {
                "code": "2330",
                "name": "台積電",
                "kind": "price",
                "expires_at": 700,
            },
            "signals": {
                "as_of": "2026-06-22",
                "items": [
                    {
                        "code": str(number),
                        "name": f"股票{number}",
                        "price": number + 1,
                        "prob": number,
                        "trend": "多頭",
                        "as_of": "2026-06-22",
                    }
                    for number in range(8)
                ],
                "extra": True,
            },
            "extra": True,
        }

        state = normalize_state(value)

        self.assertEqual(len(state["watchlist"]), MAX_WATCHLIST)
        self.assertEqual(state["watchlist"][0]["code"], "2330")
        self.assertEqual(len(state["alerts"]), MAX_ALERTS)
        self.assertEqual(state["alerts"][0]["id"], "a1")
        self.assertEqual(
            state["pending"],
            {"code": "2330", "name": "台積電", "kind": "price", "expires_at": 700},
        )
        self.assertEqual(
            state["signals"],
            {
                "as_of": "2026-06-22",
                "items": [
                    {
                        "code": str(number),
                        "name": f"股票{number}",
                        "price": number + 1,
                        "prob": number,
                        "trend": "多頭",
                        "as_of": "2026-06-22",
                    }
                    for number in range(5)
                ],
            },
        )
        self.assertNotIn("extra", state)

    def test_normalize_state_validates_values_deduplicates_and_rebuilds_schema(self):
        value = {
            "watchlist": [
                {"code": "2330", "name": "台積電", "added_at": 1, "extra": True},
                {"code": "2330", "name": "重複資料", "added_at": 2},
            ],
            "alerts": [
                {
                    "id": "a1",
                    "code": "2330",
                    "name": "台積電",
                    "kind": "price",
                    "value": 1000,
                    "enabled": False,
                    "last_triggered_date": "2026-06-22",
                    "extra": True,
                }
            ],
            "pending": {
                "code": "2330",
                "name": "台積電",
                "kind": "probability",
                "expires_at": 700,
                "extra": True,
            },
            "signals": {
                "as_of": "2026-06-22",
                "items": [
                    {
                        "code": "2330",
                        "name": "台積電",
                        "price": 1000,
                        "prob": 65,
                        "trend": "多頭",
                        "as_of": "2026-06-22",
                        "extra": True,
                    }
                ],
            },
        }

        state = normalize_state(value)

        self.assertEqual(
            state["watchlist"],
            [{"code": "2330", "name": "台積電", "added_at": 1}],
        )
        self.assertEqual(
            state["alerts"],
            [
                {
                    "id": "a1",
                    "code": "2330",
                    "name": "台積電",
                    "kind": "price",
                    "value": 1000,
                    "enabled": False,
                    "last_triggered_date": "2026-06-22",
                }
            ],
        )
        self.assertEqual(
            state["pending"],
            {"code": "2330", "name": "台積電", "kind": "probability", "expires_at": 700},
        )
        self.assertEqual(
            state["signals"],
            {
                "as_of": "2026-06-22",
                "items": [
                    {
                        "code": "2330",
                        "name": "台積電",
                        "price": 1000,
                        "prob": 65,
                        "trend": "多頭",
                        "as_of": "2026-06-22",
                    }
                ],
            },
        )

        state["watchlist"][0]["added_at"] = 2
        state["alerts"][0]["last_triggered_date"] = "2026-06-23"
        state["pending"]["name"] = "changed"
        state["signals"]["as_of"] = "2026-06-23"
        state["signals"]["items"][0]["name"] = "changed"
        state["signals"]["items"].append({"code": "2317"})
        self.assertEqual(value["watchlist"][0]["added_at"], 1)
        self.assertEqual(value["alerts"][0]["last_triggered_date"], "2026-06-22")
        self.assertEqual(value["pending"]["name"], "台積電")
        self.assertEqual(value["signals"]["as_of"], "2026-06-22")
        self.assertEqual(value["signals"]["items"][0]["name"], "台積電")
        self.assertEqual(len(value["signals"]["items"]), 1)

    def test_normalize_state_drops_invalid_alerts_pending_and_signals(self):
        invalid_alerts = [
            {"id": "", "code": "2330", "name": "台積電", "kind": "price", "value": 1},
            {"id": "a", "code": "台積電", "name": "台積電", "kind": "price", "value": 1},
            {"id": "a", "code": "2330", "name": " ", "kind": "price", "value": 1},
            {"id": "a", "code": "2330", "name": "台積電", "kind": "price", "value": True},
            {"id": "a", "code": "2330", "name": "台積電", "kind": "price", "value": 0},
            {"id": "a", "code": "2330", "name": "台積電", "kind": "price", "value": float("nan")},
            {"id": "a", "code": "2330", "name": "台積電", "kind": "price", "value": float("inf")},
            {"id": "a", "code": "2330", "name": "台積電", "kind": "probability", "value": 100},
            {"id": "a", "code": "2330", "name": "台積電", "kind": "trend", "value": "盤整"},
        ]
        invalid_signals = [
            "bad",
            {"code": "台積電", "prob": 65},
            {"code": "2330", "prob": True},
            {"code": "2330", "prob": float("nan")},
            {"code": "2330", "prob": float("inf")},
        ]

        state = normalize_state(
            {
                "alerts": invalid_alerts,
                "pending": {"code": "2330", "name": "台積電", "kind": "trend", "expires_at": 700},
                "signals": {"items": invalid_signals},
            }
        )

        self.assertEqual(state["alerts"], [])
        self.assertIsNone(state["pending"])
        self.assertEqual(state["signals"]["items"], [])

        malformed_pending = [
            {"code": "台積電", "name": "台積電", "kind": "price", "expires_at": 700},
            {"code": "2330", "name": " ", "kind": "price", "expires_at": 700},
            {"code": "2330", "name": "台積電", "kind": "price", "expires_at": True},
            {"code": "2330", "name": "台積電", "kind": "price", "expires_at": float("nan")},
            {"code": "2330", "name": "台積電", "kind": "price", "expires_at": float("inf")},
        ]
        for pending in malformed_pending:
            with self.subTest(pending=pending):
                self.assertIsNone(normalize_state({"pending": pending})["pending"])

    def test_normalize_state_requires_strict_scalar_schema(self):
        invalid_watchlist = [
            {"code": "2330", "name": "台積電"},
            {"code": "2330", "name": "台積電", "added_at": True},
            {"code": "2330", "name": "台積電", "added_at": float("nan")},
            {"code": "2330", "name": "台積電", "added_at": float("inf")},
        ]
        invalid_alerts = [
            {
                "id": "a1",
                "code": "2330",
                "name": "台積電",
                "kind": "price",
                "value": 1000,
                "enabled": 1,
                "last_triggered_date": None,
            },
            {
                "id": "a2",
                "code": "2330",
                "name": "台積電",
                "kind": "price",
                "value": 1000,
                "enabled": True,
                "last_triggered_date": "2026-02-30",
            },
            {
                "id": "a3",
                "code": "2330",
                "name": "台積電",
                "kind": "price",
                "value": 1000,
                "enabled": True,
                "last_triggered_date": "20260622",
            },
        ]
        invalid_signals = [
            {"code": "2330", "name": "", "price": 1000, "prob": 65, "trend": "多頭", "as_of": "2026-06-22"},
            {"code": "2330", "name": "台積電", "price": True, "prob": 65, "trend": "多頭", "as_of": "2026-06-22"},
            {"code": "2330", "name": "台積電", "price": 0, "prob": 65, "trend": "多頭", "as_of": "2026-06-22"},
            {"code": "2330", "name": "台積電", "price": float("inf"), "prob": 65, "trend": "多頭", "as_of": "2026-06-22"},
            {"code": "2330", "name": "台積電", "price": 1000, "prob": True, "trend": "多頭", "as_of": "2026-06-22"},
            {"code": "2330", "name": "台積電", "price": 1000, "prob": -1, "trend": "多頭", "as_of": "2026-06-22"},
            {"code": "2330", "name": "台積電", "price": 1000, "prob": 101, "trend": "多頭", "as_of": "2026-06-22"},
            {"code": "2330", "name": "台積電", "price": 1000, "prob": 65, "trend": "", "as_of": "2026-06-22"},
            {"code": "2330", "name": "台積電", "price": 1000, "prob": 65, "trend": "多頭", "as_of": "2026-02-30"},
        ]

        state = normalize_state(
            {
                "watchlist": invalid_watchlist,
                "alerts": invalid_alerts,
                "signals": {"as_of": "2026-02-30", "items": invalid_signals},
            }
        )

        self.assertEqual(state["watchlist"], [])
        self.assertEqual(state["alerts"], [])
        self.assertEqual(state["signals"], {"as_of": None, "items": []})

    def test_normalize_state_handles_non_mapping_input(self):
        for value in [None, [], "bad", 1]:
            with self.subTest(value=value):
                self.assertEqual(normalize_state(value), empty_state())


if __name__ == "__main__":
    unittest.main()
