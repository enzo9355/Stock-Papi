"""Build deterministic market observations without reading model outputs."""

import datetime
import json
import math
import re
import statistics
from collections import defaultdict


MIN_SOURCE_COVERAGE = 0.95
MAX_SOURCE_AGE_DAYS = 7
FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "ai_p",
        "prob",
        "probability",
        "direction_score",
        "score",
        "recommendation",
        "top_picks",
        "model_version",
        "backtest_version",
    }
)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _mean(values):
    values = [value for value in values if value is not None]
    return statistics.fmean(values) if values else None


def _median(values):
    values = [value for value in values if value is not None]
    return statistics.median(values) if values else None


def _rounded(value, digits=2):
    return None if value is None else round(float(value), digits)


def _return_pct(stock, periods):
    if len(stock.daily) <= periods:
        return None
    current = _number(stock.daily[-1].get("Close"))
    previous = _number(stock.daily[-1 - periods].get("Close"))
    if current is None or previous is None or previous <= 0:
        return None
    return (current / previous - 1.0) * 100.0


def _finite_json(value):
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("observation source must contain finite JSON")
        return
    if isinstance(value, list):
        for item in value:
            _finite_json(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("observation source keys must be strings")
            _finite_json(item)
        return
    raise ValueError("observation source contains unsupported JSON")


def _validate_source(source, today):
    manifest = getattr(source, "manifest", None)
    stocks = getattr(source, "stocks", None)
    if (
        manifest is None
        or manifest.schema_version != 2
        or manifest.market != "TW"
        or not isinstance(stocks, list)
        or not stocks
        or manifest.symbol_count != len(stocks)
        or manifest.coverage < MIN_SOURCE_COVERAGE
        or not 0 <= manifest.failure_rate < 0.05
    ):
        raise ValueError("observation source coverage or schema is invalid")
    age = today - manifest.market_as_of
    if not 0 <= age.days <= MAX_SOURCE_AGE_DAYS:
        raise ValueError("observation source is stale or from the future")
    if (
        re.fullmatch(
            r"manifests/TW-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}\.json",
            str(manifest.manifest_path),
        )
        is None
        or re.fullmatch(r"[0-9a-f]{64}", str(manifest.manifest_sha256)) is None
    ):
        raise ValueError("observation source manifest identity is invalid")
    seen = set()
    for stock in stocks:
        if (
            stock.sample_data
            or stock.market != "TW"
            or stock.as_of != manifest.market_as_of
            or stock.symbol in seen
            or not isinstance(stock.daily, list)
            or not stock.daily
        ):
            label = "sample" if stock.sample_data else "stock"
            raise ValueError(f"observation {label} source is invalid")
        seen.add(stock.symbol)
        for row in stock.daily:
            if not isinstance(row, dict):
                raise ValueError("observation stock rows are invalid")
            _finite_json(row)
        if str(stock.daily[-1].get("Date") or "").split("T", 1)[0] != (
            manifest.market_as_of.isoformat()
        ):
            raise ValueError("observation stock date is invalid")


def _market_daily_returns(stocks):
    by_date = defaultdict(list)
    for stock in stocks:
        for previous, current in zip(stock.daily, stock.daily[1:]):
            previous_close = _number(previous.get("Close"))
            current_close = _number(current.get("Close"))
            date_text = str(current.get("Date") or "").split("T", 1)[0]
            if (
                previous_close is not None
                and previous_close > 0
                and current_close is not None
                and date_text
            ):
                by_date[date_text].append(current_close / previous_close - 1.0)
    return [
        statistics.median(by_date[date_text])
        for date_text in sorted(by_date)[-20:]
        if by_date[date_text]
    ]


def _market_observation(stocks):
    returns = {
        f"return_{periods}d_pct": _rounded(
            _median([_return_pct(stock, periods) for stock in stocks])
        )
        for periods in (1, 5, 20, 60)
    }
    advancing = declining = unchanged = 0
    above_ma20 = []
    above_ma60 = []
    new_highs = new_lows = 0
    volume_ratios = []
    institution_ratios = []
    for stock in stocks:
        one_day = _return_pct(stock, 1)
        if one_day is not None:
            if one_day > 0:
                advancing += 1
            elif one_day < 0:
                declining += 1
            else:
                unchanged += 1
        latest = stock.daily[-1]
        close = _number(latest.get("Close"))
        ma20 = _number(latest.get("MA20"))
        ma60 = _number(latest.get("MA60"))
        if close is not None and ma20 is not None:
            above_ma20.append(close >= ma20)
        if close is not None and ma60 is not None:
            above_ma60.append(close >= ma60)
        closes = [
            _number(row.get("Close"))
            for row in stock.daily[-20:]
            if _number(row.get("Close")) is not None
        ]
        if close is not None and len(closes) >= 20:
            if close >= max(closes):
                new_highs += 1
            if close <= min(closes):
                new_lows += 1
        volume = _number(latest.get("VOL_RATIO"))
        institution = _number(latest.get("INST_NET_RATIO"))
        if volume is not None:
            volume_ratios.append(volume)
        if institution is not None:
            institution_ratios.append(institution)

    daily_returns = _market_daily_returns(stocks)
    volatility = (
        statistics.pstdev(daily_returns) * math.sqrt(252) * 100
        if len(daily_returns) >= 5
        else None
    )
    if declining > advancing and (
        new_lows > new_highs or (volatility is not None and volatility >= 25)
    ):
        risk_state = "elevated"
    elif declining > advancing or (volatility is not None and volatility >= 20):
        risk_state = "cautious"
    else:
        risk_state = "normal"
    return {
        **returns,
        "advancing_count": advancing,
        "declining_count": declining,
        "unchanged_count": unchanged,
        "ma20_breadth_pct": _rounded(
            _mean([100.0 if value else 0.0 for value in above_ma20])
        ),
        "ma60_breadth_pct": _rounded(
            _mean([100.0 if value else 0.0 for value in above_ma60])
        ),
        "new_high_20d_count": new_highs,
        "new_low_20d_count": new_lows,
        "median_volume_ratio": _rounded(_median(volume_ratios)),
        "median_institution_net_ratio_pct": _rounded(
            None
            if not institution_ratios
            else statistics.median(institution_ratios) * 100
        ),
        "realized_volatility_20d_pct": _rounded(volatility),
        "risk_state": risk_state,
    }


def _phase(relative_5d, relative_20d):
    if relative_5d is None or relative_20d is None:
        return "insufficient"
    if relative_5d > 0 and relative_20d > 0:
        return "strong"
    if relative_5d > 0:
        return "strengthening"
    if relative_20d > 0:
        return "weakening"
    return "weak"


def _industry_observations(industry_map, stock_by_symbol, market):
    observations = []
    for name, raw_symbols in industry_map.items():
        if name in {"全市場", "ETF專區"}:
            continue
        symbols = sorted({str(symbol) for symbol in raw_symbols})
        stocks = [
            stock_by_symbol[symbol]
            for symbol in symbols
            if symbol in stock_by_symbol
        ]
        if not symbols:
            continue
        return_1d = _mean([_return_pct(stock, 1) for stock in stocks])
        return_5d = _mean([_return_pct(stock, 5) for stock in stocks])
        return_20d = _mean([_return_pct(stock, 20) for stock in stocks])
        relative_5d = (
            return_5d - market["return_5d_pct"]
            if return_5d is not None and market["return_5d_pct"] is not None
            else None
        )
        relative_20d = (
            return_20d - market["return_20d_pct"]
            if return_20d is not None and market["return_20d_pct"] is not None
            else None
        )
        advancing = [
            _return_pct(stock, 1) > 0
            for stock in stocks
            if _return_pct(stock, 1) is not None
        ]
        above_ma20 = []
        volume_ratios = []
        institution_ratios = []
        for stock in stocks:
            latest = stock.daily[-1]
            close = _number(latest.get("Close"))
            ma20 = _number(latest.get("MA20"))
            if close is not None and ma20 is not None:
                above_ma20.append(close >= ma20)
            volume = _number(latest.get("VOL_RATIO"))
            institution = _number(latest.get("INST_NET_RATIO"))
            if volume is not None:
                volume_ratios.append(volume)
            if institution is not None:
                institution_ratios.append(institution)
        observations.append(
            {
                "name": str(name),
                "component_count": len(symbols),
                "available_count": len(stocks),
                "coverage": _rounded(len(stocks) / len(symbols), 4),
                "return_1d_pct": _rounded(return_1d),
                "return_5d_pct": _rounded(return_5d),
                "return_20d_pct": _rounded(return_20d),
                "relative_return_5d_pct": _rounded(relative_5d),
                "relative_return_20d_pct": _rounded(relative_20d),
                "advancing_ratio_pct": _rounded(
                    _mean([100.0 if value else 0.0 for value in advancing])
                ),
                "ma20_breadth_pct": _rounded(
                    _mean([100.0 if value else 0.0 for value in above_ma20])
                ),
                "median_volume_ratio": _rounded(_median(volume_ratios)),
                "median_institution_net_ratio_pct": _rounded(
                    None
                    if not institution_ratios
                    else statistics.median(institution_ratios) * 100
                ),
                "phase": _phase(relative_5d, relative_20d),
            }
        )
    observations.sort(
        key=lambda item: (
            item["relative_return_5d_pct"] is None,
            -(
                item["relative_return_5d_pct"]
                if item["relative_return_5d_pct"] is not None
                else 0
            ),
            item["name"],
        )
    )
    for position, item in enumerate(observations, 1):
        item["display_order"] = position
    return observations


def _stock_events(stocks):
    events = []
    severity_order = {"high": 0, "medium": 1, "low": 2}

    def add(stock, event_type, severity, metric_value, unit, observation):
        events.append(
            {
                "symbol": stock.symbol,
                "name": stock.name,
                "event_type": event_type,
                "severity": severity,
                "metric_value": _rounded(metric_value),
                "unit": unit,
                "observation": observation,
                "as_of": stock.as_of.isoformat(),
            }
        )

    for stock in sorted(stocks, key=lambda item: item.symbol):
        latest = stock.daily[-1]
        one_day = _return_pct(stock, 1)
        if one_day is not None and abs(one_day) >= 5:
            add(
                stock,
                "price_move",
                "high",
                one_day,
                "pct",
                "單日漲幅異常" if one_day > 0 else "單日跌幅異常",
            )
        volume = _number(latest.get("VOL_RATIO"))
        if volume is not None and volume >= 2:
            add(stock, "volume_surge", "medium", volume, "ratio", "量能異常放大")
        elif volume is not None and volume <= 0.5:
            add(stock, "volume_dry_up", "low", volume, "ratio", "量能明顯收縮")
        rsi = _number(latest.get("RSI"))
        if rsi is not None and rsi >= 70:
            add(stock, "rsi_overbought", "medium", rsi, "index", "RSI 進入過熱區")
        elif rsi is not None and rsi <= 30:
            add(stock, "rsi_oversold", "medium", rsi, "index", "RSI 進入超賣區")
        close = _number(latest.get("Close"))
        closes = [
            _number(row.get("Close"))
            for row in stock.daily[-20:]
            if _number(row.get("Close")) is not None
        ]
        if close is not None and len(closes) >= 20:
            if close >= max(closes):
                add(stock, "new_high_20d", "medium", close, "price", "收盤創 20 日新高")
            elif close <= min(closes):
                add(stock, "new_low_20d", "medium", close, "price", "收盤創 20 日新低")
        institution = _number(latest.get("INST_NET_RATIO"))
        if institution is not None and abs(institution) >= 0.02:
            add(
                stock,
                "institution_flow",
                "medium",
                institution * 100,
                "pct",
                "機構淨流入偏高" if institution > 0 else "機構淨流出偏高",
            )
        if (_number(latest.get("DATA_PRICE_WARNING")) or 0) > 0:
            add(stock, "data_warning", "high", 1, "flag", "資料來源價差警示")
    events.sort(
        key=lambda item: (
            severity_order[item["severity"]],
            -abs(item["metric_value"] or 0),
            item["symbol"],
            item["event_type"],
        )
    )
    return events[:30]


def _etf_observations(stocks):
    observations = []
    for stock in sorted(stocks, key=lambda item: item.symbol):
        latest = stock.daily[-1]
        close = _number(latest.get("Close"))
        ma20 = _number(latest.get("MA20"))
        ma60 = _number(latest.get("MA60"))
        if close is None:
            trend = "insufficient"
        elif ma20 is not None and ma60 is not None and close >= ma20 >= ma60:
            trend = "above_ma20_ma60"
        elif ma20 is not None and close >= ma20:
            trend = "above_ma20"
        elif ma60 is not None and close < ma60:
            trend = "below_ma60"
        else:
            trend = "mixed"
        observations.append(
            {
                "symbol": stock.symbol,
                "name": stock.name,
                "price": _rounded(close),
                "return_1d_pct": _rounded(_return_pct(stock, 1)),
                "return_5d_pct": _rounded(_return_pct(stock, 5)),
                "return_20d_pct": _rounded(_return_pct(stock, 20)),
                "volume_ratio": _rounded(_number(latest.get("VOL_RATIO"))),
                "trend_observation": trend,
                "as_of": stock.as_of.isoformat(),
            }
        )
    return observations


def _heatmap(industries):
    items = []
    for industry in industries:
        value = industry["relative_return_5d_pct"]
        if value is None:
            continue
        items.append(
            {
                "name": industry["name"],
                "metric_name": "relative_return_5d_pct",
                "metric_value_pct": value,
                "available_count": industry["available_count"],
                "coverage": industry["coverage"],
                "tone": "hot" if value >= 2 else "cold" if value <= -2 else "steady",
            }
        )
    return items


def _daily_focus(market, industries, events):
    focus = [f"市場風險狀態：{market['risk_state']}"]
    if industries:
        strongest = industries[0]
        value = strongest["relative_return_5d_pct"]
        if value is not None:
            focus.append(f"{strongest['name']} 5 日相對大盤 {value:+.2f}%")
    if events:
        focus.append(
            f"{events[0]['name']}（{events[0]['symbol']}）：{events[0]['observation']}"
        )
    return focus


def _validate_output(document):
    try:
        generated = datetime.datetime.fromisoformat(
            str(document["generated_at"]).replace("Z", "+00:00")
        )
        datetime.date.fromisoformat(str(document["observation_as_of"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("observation dashboard dates are invalid") from exc
    if (
        document.get("schema_version") != 2
        or document.get("kind") != "absorb-observation-dashboard"
        or document.get("product_mode") != "observation"
        or document.get("market") != "TW"
        or generated.tzinfo is None
        or generated.utcoffset() is None
        or not isinstance(document.get("prediction_capability"), dict)
        or not isinstance(document.get("market_observation"), dict)
        or not isinstance(document.get("industry_observations"), list)
        or not isinstance(document.get("heatmap"), list)
        or not isinstance(document.get("stock_events"), list)
        or not isinstance(document.get("etf_observations"), list)
        or not isinstance(document.get("daily_focus"), list)
        or not isinstance(document.get("data_quality"), dict)
        or not isinstance(document.get("gates"), dict)
    ):
        raise ValueError("observation dashboard schema is invalid")

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in FORBIDDEN_OUTPUT_KEYS:
                    raise ValueError("observation dashboard contains prediction fields")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(document)
    try:
        json.dumps(document, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("observation dashboard must contain finite JSON") from exc
    return document


def build_observation_dashboard(
    source,
    industry_map,
    prediction_capability,
    *,
    generated_at=None,
    today=None,
):
    """Return an Observation-only dashboard bound to a verified source manifest."""
    current_date = today or datetime.date.today()
    timestamp = generated_at or datetime.datetime.now(datetime.timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    if (
        not prediction_capability.observation_enabled
        or prediction_capability.probability_allowed
        or prediction_capability.ranking_allowed
        or prediction_capability.strong_action_allowed
        or prediction_capability.performance_endorsement_allowed
    ):
        raise ValueError("observation builder requires prediction capabilities disabled")
    if not isinstance(industry_map, dict):
        raise ValueError("industry map is invalid")
    _validate_source(source, current_date)

    stock_by_symbol = {
        stock.symbol: stock for stock in sorted(source.stocks, key=lambda item: item.symbol)
    }
    etf_symbols = {
        str(symbol) for symbol in industry_map.get("ETF專區", [])
    }
    market_stocks = [
        stock
        for symbol, stock in stock_by_symbol.items()
        if symbol not in etf_symbols
    ]
    if not market_stocks:
        raise ValueError("observation market universe is empty")
    market = _market_observation(market_stocks)
    industries = _industry_observations(industry_map, stock_by_symbol, market)
    events = _stock_events(market_stocks)
    etfs = _etf_observations(
        [
            stock_by_symbol[symbol]
            for symbol in sorted(etf_symbols)
            if symbol in stock_by_symbol
        ]
    )
    manifest = source.manifest
    document = {
        "schema_version": 2,
        "kind": "absorb-observation-dashboard",
        "product_mode": "observation",
        "market": "TW",
        "observation_as_of": manifest.market_as_of.isoformat(),
        "generated_at": timestamp.astimezone(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "source_manifest": f"quant/v1/{manifest.manifest_path}",
        "source_manifest_sha256": manifest.manifest_sha256,
        "prediction_capability": prediction_capability.to_document(),
        "market_observation": market,
        "industry_observations": industries,
        "heatmap": _heatmap(industries),
        "stock_events": events,
        "etf_observations": etfs,
        "daily_focus": _daily_focus(market, industries, events),
        "data_quality": {
            "universe_count": manifest.universe_count,
            "available_count": manifest.symbol_count,
            "failure_count": manifest.failure_count,
            "coverage": _rounded(manifest.coverage, 6),
            "failure_rate": _rounded(manifest.failure_rate, 6),
            "source_age_days": (current_date - manifest.market_as_of).days,
            "failed_symbols": list(manifest.failed_symbols),
        },
        "gates": {
            "source_identity": "PASS",
            "source_schema": "PASS",
            "finite_json": "PASS",
            "sample_data": "PASS",
            "coverage": "PASS",
            "prediction_separation": "PASS",
        },
    }
    return _validate_output(document)
