import json
import sys
import types
import unittest

try:
    import linebot.models  # noqa: F401
except ModuleNotFoundError:
    linebot = types.ModuleType("linebot")
    models = types.ModuleType("linebot.models")
    for name in ("MessageAction", "QuickReply", "QuickReplyButton"):
        setattr(models, name, type(name, (), {}))
    linebot.models = models
    sys.modules["linebot"] = linebot
    sys.modules["linebot.models"] = models

from stock_papi.integrations.line.flex import (
    build_line_navigation_flex,
    build_tutorial_flex,
    build_welcome_flex,
)
from stock_papi.integrations.line.presentation import (
    build_industry_carousel,
    build_sector_signal_carousel,
)


class AbsorbLinePresentationTests(unittest.TestCase):
    def test_core_flex_fixtures_are_absorb_json(self):
        for fixture in (
            build_welcome_flex(),
            build_tutorial_flex(),
            build_line_navigation_flex("https://example.com"),
            build_industry_carousel("半導體", ["2330"], lambda _code: "台積電"),
            build_sector_signal_carousel("半導體", [{
                "code": "2330", "name": "台積電", "prob": 63,
                "trend": "多頭", "foreign_net_5": 1000,
                "score": 70.0, "as_of": "2026-07-15",
            }], 5),
        ):
            payload = json.dumps(fixture, ensure_ascii=False)
            with self.subTest(kind=fixture["type"]):
                self.assertIn("ABSORB", payload)
                self.assertNotRegex(payload, r"(?i)Stock[ -]?Papi|Papillon|AI QUANT|蝴蝶|老爸")
                self.assertNotIn("#39c6a3", payload.lower())
                self.assertIn("#122643", payload.lower())


if __name__ == "__main__":
    unittest.main()
