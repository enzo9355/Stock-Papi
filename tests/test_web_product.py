import os
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test")
os.environ.setdefault("LINE_CHANNEL_SECRET", "test")

import app as stock_app


def analysis_data():
    return {
        "name": "台積電", "code": "2330", "price": 100.0, "prob": 63,
        "as_of": "2026-07-03", "quant_source": "本地回測快照",
        "trend": "多頭", "rsi": 58.0, "ma20": 98.0, "macd_osc": 0.3,
        "k": 62.0, "d": 54.0, "s_score": 55.0, "s_status": "中性",
        "candles": "[]", "ma20_line": "[]", "prob_h": "[]", "pred": "[]",
        "news": [],
        "projection": {
            "ok": True, "amount": 100000, "shares": 1000,
            "deployed_amount": 100000, "strategy_profit": 8000,
            "buy_hold_profit": 5000, "strategy_annualized": 8.0,
            "buy_hold_annualized": 5.0,
        },
        "foreign_flow": {
            "available": True, "net_5": 1500, "net_20": 3200,
            "status": "外資偏多", "source": "外資",
        },
        "bt": {
            "days": 100, "accuracy": 54.0, "brier": 0.23,
            "strat_cum": 8.0, "bh_cum": 5.0, "win_rate": 57.0,
            "trades": 7, "mdd": -6.0, "sharpe": 1.1,
            "conclusion": "風險調整後表現尚可", "top_features": ["成交量", "RSI", "法人"],
        },
        "recommendation": {
            "action": "分批布局", "level": "cautious_bullish",
            "headline": "模型與趨勢偏多，但短線不宜追高",
            "confidence": "可信度有限",
            "supporting_reasons": ["五日上漲機率 63%", "站上 MA20"],
            "risk_reasons": ["相似歷史訊號少於 12 次"],
            "suggested_action": "等待拉回後分二至三次建立部位。",
            "invalidation_conditions": ["股價跌破 MA20"],
            "unheld_guidance": "等待拉回後分批建立部位",
            "held_guidance": "可續抱但不宜明顯加碼",
            "data_as_of": "2026-07-03",
            "source_metrics": {"sample_count": 7},
        },
        "backtest_interpretation": {
            "advantage": "過去相同規則的結果優於單純買進持有，但不代表未來仍會維持。",
            "cumulative_return": "投入 10 萬元，歷史結果約變成 10.8 萬元。",
            "maximum_drawdown": "最差階段，10 萬元可能一度剩下約 9.4 萬元。",
            "win_rate": "每 100 次進場約有 57 次獲利；勝率不代表每次盈虧相同。",
            "cash_ratio": "資料不足：目前無法判斷空手比例。",
            "sharpe": "報酬效率（Sharpe Ratio）為 1.10，用來比較承擔波動後的歷史報酬。",
            "brier": "機率可信度（Brier Score）為 0.230；它檢查模型說 60% 時，歷史實際上漲率是否接近 60%。",
        },
    }


class WebProductTests(unittest.TestCase):
    def test_dashboard_starts_with_today_trading_preparation_cards(self):
        response = stock_app.app.test_client().get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("今日交易準備", html)
        self.assertIn("盤後分析", html)
        self.assertIn("盤前更新", html)

    def test_market_insights_fallback_uses_themes_with_five_companies(self):
        market_map = {
            "全市場": ["9999"], "ETF專區": ["0050"],
            "半導體": ["1001", "1002", "1003", "1004", "1005"],
            "AI伺服器": ["2001", "2002", "2003", "2004", "2005"],
        }
        cards = [{
            "name": "ETF專區",
            "leader": {"code": "0050", "name": "ETF", "prob": 80, "trend": "多頭", "as_of": ""},
        }]
        with (
            patch.object(stock_app, "fetch_market_insights", return_value=None),
            patch.object(stock_app, "industry_map", market_map),
            patch.object(stock_app, "dashboard_sector_cards", return_value=cards),
            patch.object(stock_app, "get_stock_name", side_effect=lambda code: f"公司{code}"),
        ):
            payload = stock_app.market_insights_payload()

        self.assertEqual([item["name"] for item in payload["industries"]], ["半導體", "AI伺服器"])
        self.assertTrue(all(len(item["leaders"]) == 5 for item in payload["industries"]))
        self.assertTrue(all(item["coverage"] == 0 for item in payload["industries"]))
        with patch.object(stock_app, "fetch_market_insights", return_value=payload):
            html = stock_app.app.test_client().get("/market-map").get_data(as_text=True)
        self.assertNotIn("None%", html)
        self.assertNotIn("+0.0%", html)

    def test_every_papi_theme_has_at_least_five_companies(self):
        self.assertTrue(all(len(names) >= 5 for names in stock_app.PAPI_THEME_SECTORS.values()))

    @patch.object(stock_app, "fetch_market_insights")
    def test_market_map_renders_industries_mops_etfs_and_supply_chains(self, fetch):
        fetch.return_value = {
            "schema_version": 1, "as_of": "2026-07-06",
            "industries": [{
                "name": "半導體", "average_prob": 62.0, "average_return": 1.8,
                "bullish_ratio": 75.0, "coverage": 4, "heat_tone": "rise",
                "heat_size": "md", "chips": [
                    {"label": "法人", "score": 7},
                    {"label": "融資", "score": 5},
                    {"label": "量能", "score": 8},
                ],
                "leaders": [{
                    "symbol": "2330", "name": "台積電", "prob": 68,
                    "trend": "多頭", "close": 1000, "return_1d": 1.8,
                    "signals": ["AI偏多", "法人偏多"],
                }, {
                    "symbol": "2454", "name": "聯發科", "prob": 61,
                    "trend": "多頭", "close": None, "return_1d": None,
                    "signals": [],
                }],
            }],
            "mops": [{"code": "2330", "name": "台積電", "title": "重大投資", "published_at": "2026-07-06T09:00:00+08:00", "source": "TWSE"}],
            "etfs": [{"ticker": "0050.TW", "name": "元大台灣50", "market": "TW", "holdings": []}],
            "supply_chains": [{"id": "semiconductor", "name": "半導體供應鏈", "stages": [{
                "name": "晶圓製造", "nodes": [{
                    "symbol": "2330", "name": "台積電", "market": "TW",
                    "prob": 68, "trend": "多頭", "return_1d": 1.8,
                    "signals": ["AI偏多"],
                }],
            }]}],
            "sources": ["TWSE"],
        }

        response = stock_app.app.test_client().get("/market-map")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for label in (
            "產業地圖", "產業關鍵指標", "產業漲跌熱力圖", "籌碼訊號",
            "產業角色分群", "+1.8%", "重大資訊 MOPS", "ETF 持倉",
            "台美日供應鏈", "重大投資",
        ):
            self.assertIn(label, html)

    def test_build_market_heatmap_orders_strongest_first(self):
        cards = [
            {"name": "弱勢", "count": 1, "score": 42, "leader": {"code": "1101", "prob": 42}},
            {"name": "強勢", "count": 2, "score": 68, "leader": {"code": "2330", "prob": 68}},
        ]

        result = stock_app.build_market_heatmap(cards)

        self.assertEqual([item["name"] for item in result], ["強勢", "弱勢"])
        self.assertEqual(result[0]["tone"], "hot")
        self.assertEqual(result[1]["tone"], "cold")

    def test_find_industry_peers_excludes_current_stock(self):
        market_map = {
            "全市場": ["2330", "2454", "2303"],
            "半導體": ["2330", "2454", "2303"],
        }

        peers = stock_app.find_industry_peers("2330", market_map, limit=2)

        self.assertEqual(peers, {"category": "半導體", "codes": ["2454", "2303"]})

    def test_root_renders_dashboard_and_search_redirects_known_stock(self):
        client = stock_app.app.test_client()

        root = client.get("/")
        with patch.object(
            stock_app,
            "search_stock_code",
            side_effect=[("2330", "台積電"), (None, None)],
        ):
            found = client.get("/search?q=台積電")
            missing = client.get("/search?q=不存在股票", follow_redirects=True)

        self.assertEqual(root.status_code, 200)
        self.assertIn("ABSORB", root.get_data(as_text=True))
        self.assertEqual(found.status_code, 302)
        self.assertTrue(found.headers["Location"].endswith("/stock/2330"))
        self.assertIn("找不到", missing.get_data(as_text=True))

    def test_empty_search_stays_on_dashboard_with_clear_error(self):
        response = stock_app.app.test_client().get("/search?q=", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("找不到", response.get_data(as_text=True))

    def test_base_shell_uses_absorb_brand_and_light_theme(self):
        response = stock_app.app.test_client().get("/dashboard")
        html = response.get_data(as_text=True)
        css = Path(stock_app.app.static_folder, "app.css").read_text(encoding="utf-8")

        self.assertIn("ABSORB", html)
        self.assertIn('alt="ABSORB logo"', html)
        self.assertIn("今天市場", html)
        self.assertIn("使用 LINE 登入", html)
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertIn("--absorb-navy:#122643", css)
        self.assertIn("--absorb-canvas:#f7f9fc", css)
        self.assertIn(".glass-panel", css)
        self.assertNotIn("量化觀測站", html)

    def test_web_security_headers_and_pinned_chart_supply_chain(self):
        response = stock_app.app.test_client().get("/dashboard")
        csp = response.headers["Content-Security-Policy"]

        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("form-action 'self'", csp)
        self.assertNotIn("'unsafe-inline'", csp)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        with patch.object(stock_app, "analyze", return_value=analysis_data()):
            stock_html = stock_app.app.test_client().get("/stock/2330").get_data(as_text=True)
        self.assertIn("lightweight-charts@4.2.2", stock_html)
        self.assertIn("integrity=\"sha384-", stock_html)
        self.assertNotIn("style=", stock_html)

    def test_dashboard_page_is_the_absorb_research_dashboard(self):
        with patch.object(stock_app, "analyze") as analyze:
            response = stock_app.app.test_client().get("/dashboard")

        self.assertEqual(response.status_code, 200)
        analyze.assert_not_called()
        html = response.get_data(as_text=True)
        for label in ["市場摘要", "今日焦點", "市場熱力圖", "產業預測", "精選標的", "新手投資小辭典", "LINE 管理關注"]:
            self.assertIn(label, html)
        self.assertNotIn("強勢訊號", html)
        for web_only_removed in ["我的關注", "最近提醒", "data-alert-preview", "/watchlist"]:
            self.assertNotIn(web_only_removed, html)
        self.assertIn('data-dashboard-endpoint="/api/dashboard"', html)
        self.assertIn('data-top-picks', html)
        self.assertIn('data-watchlist-strip', html)

    def test_dashboard_has_real_search_and_section_navigation(self):
        html = stock_app.app.test_client().get("/dashboard").get_data(as_text=True)

        for marker in (
            'action="/search"',
            'name="q"',
            'id="market-pulse"',
            'id="industry-forecast"',
            'id="top-picks"',
            'id="learn"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    @patch.object(stock_app, "analyze")
    @patch.object(stock_app, "_published_dashboard_snapshot")
    def test_dashboard_api_returns_verified_observation_without_runtime_analysis(
        self, load_snapshot, analyze
    ):
        load_snapshot.return_value = {
            "schema_version": 2,
            "kind": "absorb-observation-dashboard",
            "product_mode": "observation",
            "market": "TW",
            "observation_as_of": "2026-07-15",
            "generated_at": "2026-07-16T06:35:08Z",
            "source_manifest": "quant/v1/manifests/TW-20260716T063508Z-aaaaaaaaaaaa.json",
            "source_manifest_sha256": "a" * 64,
            "prediction_capability": {
                "mode": "research",
                "observation_enabled": True,
                "probability_allowed": False,
                "ranking_allowed": False,
                "strong_action_allowed": False,
                "performance_endorsement_allowed": False,
            },
            "market_observation": {
                "return_1d_pct": 0.8,
                "advancing_count": 1200,
                "declining_count": 700,
                "risk_state": "normal",
            },
            "industry_observations": [
                {
                    "name": "半導體",
                    "relative_return_5d_pct": 1.2,
                    "display_order": 1,
                }
            ],
            "heatmap": [
                {
                    "name": "半導體",
                    "metric_name": "relative_return_5d_pct",
                    "metric_value_pct": 1.2,
                    "tone": "steady",
                }
            ],
            "daily_focus": ["市場風險狀態：normal"],
            "stock_events": [],
            "etf_observations": [],
            "data_quality": {"coverage": 0.997},
            "gates": {"prediction_separation": "PASS"},
        }

        response = stock_app.app.test_client().get("/api/dashboard")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        analyze.assert_not_called()
        self.assertEqual(payload["product_mode"], "observation")
        self.assertEqual(payload["observation_as_of"], "2026-07-15")
        self.assertEqual(payload["market_observation"]["advancing_count"], 1200)
        self.assertEqual(payload["industry_observations"][0]["name"], "半導體")
        self.assertEqual(payload["heatmap"][0]["name"], "半導體")
        self.assertEqual(payload["prediction_status"], "AI 預測研究中")
        self.assertNotIn("top_picks", payload)
        self.assertNotIn("opportunities", payload)

    @patch.object(stock_app, "analyze")
    @patch.object(stock_app, "_published_dashboard_snapshot", return_value=None)
    def test_dashboard_api_fails_closed_without_snapshot(
        self, _load_snapshot, analyze
    ):
        response = stock_app.app.test_client().get("/api/dashboard")

        self.assertEqual(response.status_code, 503)
        analyze.assert_not_called()
        self.assertEqual(
            response.get_json()["status"], "observation_unavailable"
        )

    def test_preview_report_is_not_public_without_preview_prefix(self):
        response = stock_app.app.test_client().get("/preview/report")

        self.assertEqual(response.status_code, 404)

    @patch.object(stock_app, "analyze")
    @patch.object(stock_app, "_published_dashboard_snapshot")
    def test_preview_dashboard_uses_candidate_products(self, load_snapshot, analyze):
        analyze.return_value = {
            "price": 23150.0,
            "prob": 58,
            "trend": "多頭",
            "as_of": "2026-07-15",
            "recommendation": {},
        }
        load_snapshot.return_value = {
            "baseline_status": "initial_backtest_bootstrap",
            "inference_as_of": "2026-07-15",
            "backtest_as_of": None,
            "model_version": "lgbm-5d-v1",
            "backtest_version": None,
            "feature_schema_version": 1,
            "recommendation_policy_version": "recommendation-v1",
            "presentation": {
                "model_output_label": "模型方向分數",
                "calibration_notice": "尚未完成機率校準驗證",
                "confidence_cap": "low",
                "strong_action_allowed": False,
                "performance_endorsement_allowed": False,
                "top_picks_label": "量化觀察名單",
            },
            "sector_snapshot": {
                "sectors": {
                    "網通設備": [{
                        "code": "4906",
                        "name": "正文",
                        "prob": 73.7,
                        "direction_score": 73.7,
                        "score": 73.7,
                        "trend": "跌破 MA20",
                        "as_of": "2026-07-15",
                        "data_quality_warning": True,
                    }]
                }
            },
            "heatmap": [{
                "code": "4906",
                "count": 6,
                "direction_score": 59.9,
                "name": "網通設備",
                "tone": "steady",
            }],
            "daily_focus": ["candidate focus"],
            "top_picks": [{
                "code": "4906",
                "name": "正文",
                "direction_score": 73.7,
                "strong_action_allowed": False,
            }],
        }
        with patch.object(
            stock_app, "PREVIEW_CANDIDATE_PREFIX", "previews/demo"
        ), patch.object(stock_app, "cached_opportunities", return_value=[]):
            response = stock_app.app.test_client().get("/api/dashboard")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["inference_as_of"], "2026-07-15")
        self.assertEqual(payload["model_version"], "lgbm-5d-v1")
        self.assertEqual(payload["sector_cards"][0]["leader"]["code"], "4906")
        self.assertEqual(payload["heatmap"][0]["name"], "網通設備")
        self.assertEqual(payload["daily_focus"], ["candidate focus"])
        self.assertEqual(payload["top_picks"][0]["code"], "4906")
        self.assertFalse(payload["top_picks"][0]["strong_action_allowed"])

    @patch.object(stock_app, "find_industry_peers", return_value={"category": "半導體", "codes": ["2454"]})
    @patch.object(stock_app, "get_stock_name", return_value="聯發科")
    @patch.object(stock_app, "analyze", return_value=analysis_data())
    def test_stock_page_is_the_core_analysis_workspace(self, _analyze, _name, _peers):
        response = stock_app.app.test_client().get("/stock/2330")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        for label in ["五日上漲機率", "技術指標", "新手解讀", "風險提醒"]:
            self.assertIn(label, html)
        for label in ["投資金額試算", "外資買賣超", "約可買股數", "外資偏多"]:
            self.assertIn(label, html)
        for web_only_removed in ["設定提醒", "data-watchlist-add", "data-alert-open"]:
            self.assertNotIn(web_only_removed, html)
        self.assertIn("data-watchlist-toggle", html)
        self.assertIn("登入後加入關注", html)
        self.assertIn("data-chart-range", html)
        self.assertIn("<details", html)
        self.assertIn("/static/app.css", html)
        self.assertIn("產業同儕", html)
        self.assertIn("聯發科", html)
        self.assertIn('aria-label="個股分析導覽"', html)
        self.assertIn("分批布局", html)
        self.assertIn("支持這項建議", html)
        self.assertIn("反對這項建議", html)
        self.assertIn("未持有", html)
        self.assertIn("已持有", html)
        self.assertIn("投入 10 萬元，歷史結果約變成 10.8 萬元", html)
        self.assertIn("查看模型與回測詳細數據", html)

    def test_dashboard_script_does_not_insert_api_text_with_inner_html(self):
        script = Path(stock_app.app.static_folder, "app.js").read_text(encoding="utf-8")

        self.assertNotIn(".innerHTML", script)

    def test_stock_page_does_not_render_unsafe_news_links(self):
        data = analysis_data()
        data["news"] = [{
            "title": "不安全來源仍保留文字",
            "normalized_title": "不安全來源仍保留文字",
            "link": "javascript:alert(1)",
            "source": "未知來源",
            "published_at": "2026-07-11T09:00:00+08:00",
            "direction": "neutral",
        }]

        with patch.object(stock_app, "analyze", return_value=data):
            html = stock_app.app.test_client().get("/stock/2330").get_data(as_text=True)

        self.assertIn("不安全來源仍保留文字", html)
        self.assertNotIn('href="javascript:', html)

    @patch.object(stock_app, "analyze", return_value=analysis_data())
    def test_stock_page_accepts_standard_us_ticker(self, analyze):
        response = stock_app.app.test_client().get("/stock/AAPL")

        self.assertEqual(response.status_code, 200)
        analyze.assert_called_once_with("AAPL")

    @patch.object(stock_app, "analyze", return_value=analysis_data())
    def test_stock_page_uses_summary_chart_news_first_flow(self, _analyze):
        response = stock_app.app.test_client().get("/stock/2330")
        html = response.get_data(as_text=True)

        for label in ["預測摘要", "價格與預測軌跡", "近期新聞", "新手解讀"]:
            self.assertIn(label, html)
        self.assertIn("glass-segmented", html)
        self.assertIn("chart-shell", html)

    @patch.object(stock_app, "analyze", return_value=analysis_data())
    def test_stock_page_has_guided_analysis_controls(self, _analyze):
        html = stock_app.app.test_client().get("/stock/2330").get_data(as_text=True)

        for marker in (
            'class="page-jump-nav',
            'data-amount-preset="10000"',
            'data-amount-preset="50000"',
            'data-amount-preset="100000"',
            'id="backtest"',
            'id="sentiment"',
            'data-news-filter="positive"',
            "ABSORB 判讀",
            "情緒動能",
            "最大回撤",
            "資料日 2026-07-03",
            "本地回測快照",
            "資料完整度</span><strong>資料不足",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_web_is_analysis_only_and_old_watchlist_redirects(self):
        client = stock_app.app.test_client()
        response = client.get("/watchlist")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/dashboard"))

    @patch.object(stock_app, "analyze")
    def test_stock_summary_api_removed_with_browser_watchlist(self, analyze):
        response = stock_app.app.test_client().get("/api/stock/2330/summary")

        self.assertEqual(response.status_code, 404)
        analyze.assert_not_called()

    def test_line_navigation_maps_six_entries_to_web_routes_and_line_actions(self):
        navigation = stock_app.build_line_navigation_flex("https://example.com/")

        self.assertEqual(navigation["type"], "carousel")
        self.assertEqual(len(navigation["contents"]), 6)
        expected_uri = {
            "看大盤": "https://example.com/market",
            "深度分析": "https://example.com/dashboard",
        }
        actual_uri = {}
        actual_message = {}
        for card in navigation["contents"]:
            self.assertEqual(len(card["footer"]["contents"]), 1)
            action = card["footer"]["contents"][0]["action"]
            title = card["body"]["contents"][0]["text"]
            if action["type"] == "uri":
                actual_uri[title] = action["uri"]
            else:
                actual_message[title] = action["text"]
        self.assertEqual(actual_uri, expected_uri)
        self.assertEqual(actual_message, {
            "查自選": "我的關注",
            "找機會": "預測",
            "設提醒": "提醒管理",
            "算報酬": "投資試算",
        })
        self.assertNotIn("強勢訊號", actual_message)

    def test_rich_menu_source_is_plain_text_and_large(self):
        svg = Path("assets/rich-menu.svg").read_text(encoding="utf-8")

        for label in ["看大盤", "找機會", "查自選", "設提醒", "算報酬", "深度分析"]:
            self.assertIn(label, svg)
        for old_label in ["今日盤勢", "我的關注", "產業預測", "提醒管理", "投資試算", "完整分析"]:
            self.assertNotIn(old_label, svg)
        for emoji in ["📈", "⭐", "🏭", "🔔", "🧮", "📊"]:
            self.assertNotIn(emoji, svg)
        for marker in ["ABSORB", "#122643", "#ffffff", "#eaf0f7"]:
            self.assertIn(marker, svg)
        self.assertIn('font:800 132px', svg)
        self.assertIn('font:700 48px', svg)

    def test_line_summary_card_has_one_clear_cta(self):
        card = stock_app.build_line_summary_card(
            "強勢訊號", ["2330 台積電", "五日上漲機率 68%"],
            "查看完整分析", "https://example.com/stock/2330",
        )

        self.assertEqual(len(card["footer"]["contents"]), 1)
        self.assertEqual(
            card["footer"]["contents"][0]["action"]["uri"],
            "https://example.com/stock/2330",
        )

    def test_web_shell_supports_keyboard_and_mobile_interactions(self):
        response = stock_app.app.test_client().get("/dashboard")
        html = response.get_data(as_text=True)
        css = Path(stock_app.app.static_folder, "app.css").read_text(encoding="utf-8")

        for marker in ['class="skip-link"', 'id="main-content"', 'aria-live="polite"']:
            self.assertIn(marker, html)
        for rule in [":focus-visible", "prefers-reduced-motion", "min-height:44px"]:
            self.assertIn(rule, css)
        self.assertIn("grid-template-columns:repeat(4,1fr)", css)
        self.assertIn('href="/reports">每日報告</a>', html)

    def test_browser_bundle_has_no_local_watchlist_storage(self):
        source = Path(stock_app.app.static_folder, "app.js").read_text(encoding="utf-8")

        for removed in ["localStorage", "quant-watchlist", "data-alert-open", "data-alert-form"]:
            self.assertNotIn(removed, source)
        self.assertIn("initReturnCalculator", source)
        self.assertIn("if (!entries.length) return", source)

    def test_health_check_is_separate_from_dashboard(self):
        client = stock_app.app.test_client()

        for path in ("/health", "/healthz"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_data(as_text=True), "ok")

    def test_stock_chart_is_clipped_and_resizes_with_its_panel(self):
        css = Path(stock_app.app.static_folder, "app.css").read_text(encoding="utf-8")
        js = Path(stock_app.app.static_folder, "app.js").read_text(encoding="utf-8")

        self.assertIn(".chart-shell{overflow:hidden", css)
        self.assertIn(".stock-chart{", css)
        self.assertIn("min-height:320px", css)
        self.assertIn("function measureChartHeight", js)
        self.assertIn("Math.min(460", js)
        self.assertIn("ResizeObserver", js)


if __name__ == "__main__":
    unittest.main()
