# -*- coding: utf-8 -*-
"""Presentation layer, disclosure, and HTML template boundary tests."""

import unittest
from reporting.professional_schema import (
    ProfessionalPostCloseReport,
    compute_content_sha256,
)
from reporting.professional_html import build_professional_report_view


class TestRegressionPresentation(unittest.TestCase):

    def test_production_view_model_keeps_quantitative_research_unavailable(self):
        from tests.test_professional_report_schema import ProfessionalReportSchemaTests
        doc = ProfessionalReportSchemaTests()._document()
        doc["identity"]["content_sha256"] = compute_content_sha256(doc)
        report = ProfessionalPostCloseReport.from_document(doc)
        view = build_professional_report_view(report)
        self.assertEqual(view["quantitative_research"]["status"], "unavailable")

    def test_disclosure_text_matches_mandatory_specification(self):
        from reporting.regression_schema import FORBIDDEN_WORDS
        mandatory_disclosure = "\u6a21\u578b\u5c1a\u672a\u901a\u904e Ranking\u3001Calibration\u3001Quality \u8207 Transaction Value\uff0c\u56e0\u6b64\u4e0d\u63d0\u4f9b\u6b63\u5f0f\u9810\u6e2c\u6a5f\u7387\u3002"
        ai_label = "AI \u6a21\u578b\u53c3\u8003\u5efa\u8b70"
        uncalibrated_output_name = "\u6a21\u578b\u65b9\u5411\u53c3\u8003"

        self.assertIn("\u4e0d\u63d0\u4f9b\u6b63\u5f0f\u9810\u6e2c\u6a5f\u7387", mandatory_disclosure)
        self.assertEqual(ai_label, "AI \u6a21\u578b\u53c3\u8003\u5efa\u8b70")
        self.assertEqual(uncalibrated_output_name, "\u6a21\u578b\u65b9\u5411\u53c3\u8003")

        forbidden = ["Probability", "\u52dd\u7387", "\u4e0a\u6f35\u6a5f\u7387", "\u4e0b\u8dcc\u6a5f\u7387", "\u6b63\u5f0f\u9810\u6e2c", "\u8cb7\u9032\u8a0a\u865f", "\u8ce3\u51fa\u8a0a\u865f"]
        for word in forbidden:
            self.assertIn(word, FORBIDDEN_WORDS)


if __name__ == "__main__":
    unittest.main()
