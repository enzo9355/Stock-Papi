"""雙每日報告與 daily run 的輕量資料契約。"""

import datetime
import re
from dataclasses import dataclass


class ContractError(ValueError):
    """批次資料契約不合法。"""


def _aware(value, label):
    if not isinstance(value, datetime.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ContractError(f"{label} 必須是 timezone-aware datetime")
    return value


def _parse_date(value, label):
    try:
        parsed = datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{label} 日期不合法") from exc
    if parsed.isoformat() != value:
        raise ContractError(f"{label} 日期不合法")
    return parsed


def _parse_datetime(value, label):
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{label} 時間不合法") from exc
    return _aware(parsed, label)


def _timestamp(value):
    return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _symbols(values, label):
    if not isinstance(values, (list, tuple)):
        raise ContractError(f"{label} 必須是清單")
    result = tuple(str(value) for value in values)
    if len(result) != len(set(result)) or not all(
        re.fullmatch(r"[A-Z0-9.-]{1,12}", value) for value in result
    ):
        raise ContractError(f"{label} 不合法")
    return result


@dataclass(frozen=True)
class ReportTiming:
    source_market_date: datetime.date
    applicable_trading_date: datetime.date
    published_at: datetime.datetime
    forecast_start_date: datetime.date
    forecast_end_date: datetime.date
    backtest_as_of: datetime.date

    def __post_init__(self):
        _aware(self.published_at, "published_at")
        if (
            self.source_market_date >= self.applicable_trading_date
            or self.forecast_start_date != self.applicable_trading_date
            or self.forecast_end_date < self.forecast_start_date
            or self.backtest_as_of > self.source_market_date
        ):
            raise ContractError("報告時間語意不一致")


def build_post_close_timing(
    *, source_market_date, published_at, backtest_as_of, calendars
):
    _aware(published_at, "published_at")
    try:
        is_session = calendars.is_session(source_market_date)
    except ValueError as exc:
        raise ContractError(str(exc)) from exc
    if not is_session:
        raise ContractError("source_market_date 不是已驗證交易日")
    try:
        applicable = calendars.next_session(source_market_date)
        forecast_end = calendars.session_offset(applicable, 4)
    except ValueError as exc:
        raise ContractError(str(exc)) from exc
    return ReportTiming(
        source_market_date=source_market_date,
        applicable_trading_date=applicable,
        published_at=published_at,
        forecast_start_date=applicable,
        forecast_end_date=forecast_end,
        backtest_as_of=backtest_as_of,
    )


@dataclass(frozen=True)
class DailyRunCheckpoint:
    run_id: str
    target_market_date: datetime.date
    source_manifest: str
    source_manifest_sha256: str
    model_version: str
    next_index: int
    completed_symbols: tuple[str, ...]
    failed_symbols: tuple[str, ...]
    started_at: datetime.datetime
    updated_at: datetime.datetime
    status: str

    def __post_init__(self):
        if (
            type(self.target_market_date) is not datetime.date
            or re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}", self.run_id) is None
            or re.fullmatch(
                r"quant/v1/manifests/TW-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}\.json",
                self.source_manifest,
            )
            is None
            or re.fullmatch(r"[0-9a-f]{64}", self.source_manifest_sha256) is None
            or not isinstance(self.model_version, str)
            or not 1 <= len(self.model_version) <= 100
            or type(self.next_index) is not int
            or self.next_index < 0
            or self.status not in {"pending", "running", "completed", "failed"}
        ):
            raise ContractError("daily checkpoint schema 不合法")
        completed = _symbols(self.completed_symbols, "completed_symbols")
        failed = _symbols(self.failed_symbols, "failed_symbols")
        if completed != self.completed_symbols or failed != self.failed_symbols:
            raise ContractError("daily checkpoint symbols 必須是 tuple")
        if set(completed) & set(failed):
            raise ContractError("completed 與 failed symbols 不可重疊")
        _aware(self.started_at, "started_at")
        _aware(self.updated_at, "updated_at")
        if self.updated_at < self.started_at:
            raise ContractError("updated_at 不得早於 started_at")

    def to_dict(self):
        return {
            "schema_version": 1,
            "job_type": "daily_prediction",
            "run_id": self.run_id,
            "target_market_date": self.target_market_date.isoformat(),
            "source_manifest": self.source_manifest,
            "source_manifest_sha256": self.source_manifest_sha256,
            "model_version": self.model_version,
            "next_index": self.next_index,
            "completed_symbols": list(self.completed_symbols),
            "failed_symbols": list(self.failed_symbols),
            "started_at": _timestamp(self.started_at),
            "updated_at": _timestamp(self.updated_at),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, document):
        if not isinstance(document, dict) or document.get("schema_version") != 1 or document.get("job_type") != "daily_prediction":
            raise ContractError("daily checkpoint schema 不合法")
        try:
            return cls(
                run_id=str(document["run_id"]),
                target_market_date=_parse_date(
                    document["target_market_date"], "target_market_date"
                ),
                source_manifest=str(document["source_manifest"]),
                source_manifest_sha256=str(document["source_manifest_sha256"]),
                model_version=str(document["model_version"]),
                next_index=document["next_index"],
                completed_symbols=_symbols(
                    document["completed_symbols"], "completed_symbols"
                ),
                failed_symbols=_symbols(document["failed_symbols"], "failed_symbols"),
                started_at=_parse_datetime(document["started_at"], "started_at"),
                updated_at=_parse_datetime(document["updated_at"], "updated_at"),
                status=str(document["status"]),
            )
        except KeyError as exc:
            raise ContractError("daily checkpoint 欄位缺失") from exc

    def assert_resume_compatible(
        self, *, target_market_date, source_manifest_sha256, model_version
    ):
        if (
            self.target_market_date != target_market_date
            or self.source_manifest_sha256 != source_manifest_sha256
            or self.model_version != model_version
        ):
            raise ContractError("daily checkpoint 與本次目標不相容")
