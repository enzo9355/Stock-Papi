import copy
import math
import time
import uuid
from datetime import date


MAX_WATCHLIST = 12
MAX_ALERTS = 20
PENDING_SECONDS = 600


class StateError(ValueError):
    pass


def _is_valid_code(code):
    return isinstance(code, str) and bool(code) and code.isascii() and code.isalnum()


def _is_nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _is_valid_stock(code, name):
    return _is_valid_code(code) and _is_nonempty_string(name)


def _validate_stock(code, name):
    if not _is_valid_stock(code, name):
        raise StateError("股票資料格式錯誤")


def _is_finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_valid_alert_value(kind, value):
    if kind == "price":
        return _is_finite_number(value) and value > 0
    if kind == "probability":
        return _is_finite_number(value) and 1 <= value <= 99
    return kind == "trend" and value in {"多頭", "空頭"}


def _is_iso_date(value):
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _is_optional_iso_date(value):
    return value is None or _is_iso_date(value)


def empty_state():
    return {
        "watchlist": [],
        "alerts": [],
        "pending": None,
        "signals": {"as_of": None, "items": []},
    }


def normalize_state(value):
    state = empty_state()
    if not isinstance(value, dict):
        return state

    watchlist = value.get("watchlist")
    if isinstance(watchlist, list):
        seen_codes = set()
        for item in watchlist:
            if (
                not isinstance(item, dict)
                or not _is_valid_stock(item.get("code"), item.get("name"))
                or not _is_finite_number(item.get("added_at"))
            ):
                continue
            if item["code"] in seen_codes:
                continue
            seen_codes.add(item["code"])
            state["watchlist"].append(
                {
                    "code": item["code"],
                    "name": item["name"],
                    "added_at": copy.deepcopy(item.get("added_at")),
                }
            )
            if len(state["watchlist"]) == MAX_WATCHLIST:
                break

    alerts = value.get("alerts")
    if isinstance(alerts, list):
        for item in alerts:
            if (
                not isinstance(item, dict)
                or not _is_nonempty_string(item.get("id"))
                or not _is_valid_stock(item.get("code"), item.get("name"))
                or item.get("kind") not in {"price", "probability", "trend"}
                or not _is_valid_alert_value(item["kind"], item.get("value"))
                or not isinstance(item.get("enabled"), bool)
                or not _is_optional_iso_date(item.get("last_triggered_date"))
            ):
                continue
            state["alerts"].append(
                {
                    "id": item["id"],
                    "code": item["code"],
                    "name": item["name"],
                    "kind": item["kind"],
                    "value": copy.deepcopy(item["value"]),
                    "enabled": copy.deepcopy(item.get("enabled", True)),
                    "last_triggered_date": copy.deepcopy(item.get("last_triggered_date")),
                }
            )
            if len(state["alerts"]) == MAX_ALERTS:
                break

    pending = value.get("pending")
    if (
        isinstance(pending, dict)
        and _is_valid_stock(pending.get("code"), pending.get("name"))
        and pending.get("kind") in {"price", "probability"}
        and _is_finite_number(pending.get("expires_at"))
    ):
        state["pending"] = {
            "code": pending["code"],
            "name": pending["name"],
            "kind": pending["kind"],
            "expires_at": copy.deepcopy(pending["expires_at"]),
        }

    signals = value.get("signals")
    if isinstance(signals, dict):
        items = signals.get("items")
        state["signals"] = {
            "as_of": copy.deepcopy(signals.get("as_of"))
            if _is_optional_iso_date(signals.get("as_of"))
            else None,
            "items": [],
        }
        if isinstance(items, list):
            allowed_fields = ("code", "name", "price", "prob", "trend", "as_of")
            for item in items:
                if (
                    not isinstance(item, dict)
                    or not _is_valid_stock(item.get("code"), item.get("name"))
                    or not _is_finite_number(item.get("price"))
                    or item["price"] <= 0
                    or not _is_finite_number(item.get("prob"))
                    or not 0 <= item["prob"] <= 100
                    or not _is_nonempty_string(item.get("trend"))
                    or not _is_iso_date(item.get("as_of"))
                ):
                    continue
                state["signals"]["items"].append(
                    {
                        field: copy.deepcopy(item[field])
                        for field in allowed_fields
                        if field in item
                    }
                )
                if len(state["signals"]["items"]) == 5:
                    break

    return state


def add_watch(state, code, name, now=None):
    _validate_stock(code, name)
    if any(item.get("code") == code for item in state["watchlist"]):
        return state
    if len(state["watchlist"]) >= MAX_WATCHLIST:
        raise StateError("關注清單最多 12 檔")

    added_at = time.time() if now is None else now
    state["watchlist"].append({"code": code, "name": name, "added_at": added_at})
    return state


def remove_watch(state, code):
    state["watchlist"] = [item for item in state["watchlist"] if item.get("code") != code]
    state["alerts"] = [item for item in state["alerts"] if item.get("code") != code]
    return state


def start_pending(state, code, name, kind, now=None):
    _validate_stock(code, name)
    if kind not in {"price", "probability"}:
        raise StateError("不支援的提醒類型")

    started_at = time.time() if now is None else now
    state["pending"] = {
        "code": code,
        "name": name,
        "kind": kind,
        "expires_at": started_at + PENDING_SECONDS,
    }
    return state


def add_alert(state, code, name, kind, value):
    _validate_stock(code, name)
    if kind not in {"price", "probability", "trend"}:
        raise StateError("不支援的提醒類型")
    if not _is_valid_alert_value(kind, value):
        raise StateError("提醒條件格式錯誤")
    if len(state["alerts"]) >= MAX_ALERTS:
        raise StateError("提醒最多 20 條")

    alert = {
        "id": uuid.uuid4().hex,
        "code": code,
        "name": name,
        "kind": kind,
        "value": value,
        "enabled": True,
        "last_triggered_date": None,
    }
    state["alerts"].append(alert)
    return alert


def consume_pending(state, text, now=None):
    pending = state.get("pending")
    current_time = time.time() if now is None else now
    if not pending or pending.get("expires_at", 0) <= current_time:
        state["pending"] = None
        raise StateError("提醒設定已逾時")

    try:
        value = float(text)
    except (TypeError, ValueError) as error:
        raise StateError("請輸入有效數字") from error
    if not math.isfinite(value):
        raise StateError("請輸入有效數字")
    if pending["kind"] == "price" and value <= 0:
        raise StateError("價格必須大於 0")
    if pending["kind"] == "probability" and not 1 <= value <= 99:
        raise StateError("機率必須介於 1 到 99")

    alert = add_alert(
        state,
        pending["code"],
        pending["name"],
        pending["kind"],
        value,
    )
    state["pending"] = None
    return alert


def evaluate_alert(alert, quote):
    if alert["kind"] == "price":
        return quote["price"] >= float(alert["value"])
    if alert["kind"] == "probability":
        return quote["prob"] >= float(alert["value"])
    return alert["kind"] == "trend" and quote["trend"] == alert["value"]


def top_signals(quotes):
    return sorted(
        (copy.deepcopy(item) for item in quotes),
        key=lambda item: item["prob"],
        reverse=True,
    )[:5]
