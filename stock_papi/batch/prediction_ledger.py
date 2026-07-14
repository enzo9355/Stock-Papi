"""Append-only forecast records, settlements, and development projections."""

import datetime
import hashlib
import json
import math
import os
import re
from pathlib import Path


class PredictionLedgerError(ValueError):
    """Prediction ledger schema、hash 或 immutable 寫入不合法。"""


def _canonical(document):
    try:
        return json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PredictionLedgerError("ledger document is not finite JSON") from exc


def _sha256(content):
    return hashlib.sha256(content).hexdigest()


def _timestamp(value, label):
    if (
        not isinstance(value, datetime.datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise PredictionLedgerError(f"{label} must be timezone-aware")
    return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_text(value, label, maximum=100):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise PredictionLedgerError(f"invalid {label}")
    return value


def _write_exclusive(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if path.read_bytes() != content:
            raise PredictionLedgerError("immutable ledger conflict")
        return
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _write_atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class PredictionLedger:
    def __init__(self, root, market, calendars):
        if market != "TW" or calendars is None:
            raise PredictionLedgerError("unsupported prediction ledger")
        self.market = market
        self.calendars = calendars
        self.root = Path(root) / "publish" / "predictions" / "v1"
        self.records_dir = self.root / "records"
        self.settlements_dir = self.root / "settlements"
        self.index_path = self.root / f"index-{market}.json"

    def _load_index(self):
        if not self.index_path.exists():
            return {"schema_version": 1, "market": self.market, "records": []}
        try:
            document = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PredictionLedgerError("prediction index is invalid") from exc
        records = document.get("records")
        if (
            document.get("schema_version") != 1
            or document.get("market") != self.market
            or not isinstance(records, list)
        ):
            raise PredictionLedgerError("prediction index is invalid")
        return document

    def _identity(
        self,
        *,
        entity_type,
        entity_id,
        source_market_date,
        model_version,
        source_manifest_sha256,
    ):
        return {
            "market": self.market,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "source_market_date": source_market_date.isoformat(),
            "model_version": model_version,
            "source_manifest_sha256": source_manifest_sha256,
        }

    def write_forecast(
        self,
        *,
        entity_type,
        entity_id,
        source_market_date,
        probability,
        action,
        reasons,
        issued_at,
        model_version,
        source_manifest_sha256,
    ):
        if entity_type not in {"market", "industry", "stock"}:
            raise PredictionLedgerError("invalid entity type")
        entity_id = _safe_text(entity_id, "entity id")
        action = _safe_text(action, "action", maximum=30)
        model_version = _safe_text(model_version, "model version")
        if (
            type(source_market_date) is not datetime.date
            or not self.calendars.is_session(source_market_date)
            or type(probability) not in (int, float)
            or not math.isfinite(probability)
            or not 0 <= probability <= 100
            or re.fullmatch(r"[0-9a-f]{64}", str(source_manifest_sha256)) is None
            or not isinstance(reasons, (list, tuple))
        ):
            raise PredictionLedgerError("invalid forecast fields")
        normalized_reasons = tuple(
            _safe_text(reason, "reason", maximum=200) for reason in reasons
        )
        if len(normalized_reasons) > 20 or len(set(normalized_reasons)) != len(
            normalized_reasons
        ):
            raise PredictionLedgerError("invalid forecast reasons")
        issued = _timestamp(issued_at, "issued_at")
        first_session = self.calendars.next_session(source_market_date)
        sessions = [
            self.calendars.session_offset(first_session, offset).isoformat()
            for offset in range(5)
        ]
        identity = self._identity(
            entity_type=entity_type,
            entity_id=entity_id,
            source_market_date=source_market_date,
            model_version=model_version,
            source_manifest_sha256=source_manifest_sha256,
        )
        forecast_id = _sha256(_canonical(identity))
        document = {
            "schema_version": 1,
            "forecast_id": forecast_id,
            **identity,
            "forecast_sessions": sessions,
            "probability": float(probability),
            "action": action,
            "reasons": list(normalized_reasons),
            "issued_at": issued,
        }
        content = _canonical(document)
        content_sha256 = _sha256(content)
        path = self.records_dir / f"{forecast_id}.json"
        _write_exclusive(path, content)

        index = self._load_index()
        entry = {
            "forecast_id": forecast_id,
            "path": f"predictions/v1/records/{forecast_id}.json",
            "content_sha256": content_sha256,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "source_market_date": source_market_date.isoformat(),
            "issued_at": issued,
        }
        existing = [item for item in index["records"] if item.get("forecast_id") == forecast_id]
        if existing and existing != [entry]:
            raise PredictionLedgerError("prediction index conflict")
        if not existing:
            index["records"].append(entry)
            index["records"].sort(
                key=lambda item: (
                    item["source_market_date"],
                    item["issued_at"],
                    item["forecast_id"],
                )
            )
            _write_atomic(self.index_path, _canonical(index))
        return {
            **document,
            "content_sha256": content_sha256,
            "record_path": str(path),
        }

    def list_records(self):
        index = self._load_index()
        result = []
        for entry in index["records"]:
            forecast_id = str(entry.get("forecast_id") or "")
            expected_path = f"predictions/v1/records/{forecast_id}.json"
            if (
                re.fullmatch(r"[0-9a-f]{64}", forecast_id) is None
                or entry.get("path") != expected_path
            ):
                raise PredictionLedgerError("prediction index path is invalid")
            path = self.records_dir / f"{forecast_id}.json"
            try:
                content = path.read_bytes()
                document = json.loads(content)
            except (OSError, ValueError) as exc:
                raise PredictionLedgerError("prediction record is unreadable") from exc
            digest = _sha256(content)
            if (
                digest != entry.get("content_sha256")
                or document.get("forecast_id") != forecast_id
                or _canonical(document) != content
            ):
                raise PredictionLedgerError("prediction record hash mismatch")
            result.append(
                {
                    **document,
                    "content_sha256": digest,
                    "record_path": str(path),
                }
            )
        return result

    def _record(self, forecast_id):
        for record in self.list_records():
            if record["forecast_id"] == forecast_id:
                return record
        raise PredictionLedgerError("forecast does not exist")

    def settle(
        self,
        forecast_id,
        *,
        evaluated_on,
        status,
        actual_return,
        reason,
        settled_at,
    ):
        record = self._record(forecast_id)
        if (
            type(evaluated_on) is not datetime.date
            or not self.calendars.is_session(evaluated_on)
        ):
            raise PredictionLedgerError("invalid settlement date")
        maturity = datetime.date.fromisoformat(record["forecast_sessions"][-1])
        if evaluated_on < maturity:
            raise PredictionLedgerError("forecast is still active")
        if status == "matured":
            if (
                type(actual_return) not in (int, float)
                or not math.isfinite(actual_return)
                or reason is not None
            ):
                raise PredictionLedgerError("invalid matured settlement")
            direction_correct = (record["probability"] >= 50) == (actual_return > 0)
        elif status == "invalid":
            if actual_return is not None or reason not in {"suspended", "missing_price"}:
                raise PredictionLedgerError("invalid settlement reason")
            direction_correct = None
        else:
            raise PredictionLedgerError("invalid settlement status")
        document = {
            "schema_version": 1,
            "forecast_id": forecast_id,
            "status": status,
            "evaluated_on": evaluated_on.isoformat(),
            "actual_return": None if actual_return is None else float(actual_return),
            "direction_correct": direction_correct,
            "reason": reason,
            "settled_at": _timestamp(settled_at, "settled_at"),
        }
        content = _canonical(document)
        digest = _sha256(content)
        existing = list(self.settlements_dir.glob(f"{forecast_id}-*.json"))
        path = self.settlements_dir / f"{forecast_id}-{digest}.json"
        if existing and path not in existing:
            raise PredictionLedgerError("forecast settlement conflict")
        _write_exclusive(path, content)
        return {
            **document,
            "content_sha256": digest,
            "settlement_path": str(path),
        }

    def _settlements(self):
        result = {}
        if not self.settlements_dir.exists():
            return result
        for path in sorted(self.settlements_dir.glob("*.json")):
            match = re.fullmatch(r"([0-9a-f]{64})-([0-9a-f]{64})\.json", path.name)
            if match is None:
                raise PredictionLedgerError("settlement filename is invalid")
            try:
                content = path.read_bytes()
                document = json.loads(content)
            except (OSError, ValueError) as exc:
                raise PredictionLedgerError("settlement is unreadable") from exc
            if (
                _sha256(content) != match.group(2)
                or document.get("forecast_id") != match.group(1)
                or _canonical(document) != content
                or match.group(1) in result
            ):
                raise PredictionLedgerError("settlement hash or identity mismatch")
            result[match.group(1)] = document
        return result

    def accuracy_summary(self):
        settlements = self._settlements()
        matured = [item for item in settlements.values() if item.get("status") == "matured"]
        invalid = sum(item.get("status") == "invalid" for item in settlements.values())
        correct = sum(item.get("direction_correct") is True for item in matured)
        return {
            "matured": len(matured),
            "correct": correct,
            "accuracy": None if not matured else correct / len(matured),
            "invalid": invalid,
        }

    def development_projection(self, entity_type, entity_id):
        records = [
            record
            for record in self.list_records()
            if record["entity_type"] == entity_type and record["entity_id"] == entity_id
        ]
        if not records:
            raise PredictionLedgerError("entity has no forecasts")
        current = records[-1]
        previous = records[-2] if len(records) > 1 else None
        if previous is None:
            probability_change = None
            trend = "new"
            added = list(current["reasons"])
            removed = []
            version_changed = False
        else:
            probability_change = round(
                current["probability"] - previous["probability"], 10
            )
            trend = "up" if probability_change > 0 else "down" if probability_change < 0 else "flat"
            added = [reason for reason in current["reasons"] if reason not in previous["reasons"]]
            removed = [reason for reason in previous["reasons"] if reason not in current["reasons"]]
            version_changed = current["model_version"] != previous["model_version"]
        settlements = self._settlements()
        recent = []
        for record in reversed(records):
            settlement = settlements.get(record["forecast_id"])
            if settlement and settlement.get("status") == "matured":
                recent.append(
                    {
                        "source_market_date": record["source_market_date"],
                        "probability": record["probability"],
                        "actual_return": settlement["actual_return"],
                        "direction_correct": settlement["direction_correct"],
                    }
                )
            if len(recent) == 5:
                break
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "current_forecast_id": current["forecast_id"],
            "previous_forecast_id": None if previous is None else previous["forecast_id"],
            "probability_change": probability_change,
            "trend": trend,
            "reasons_added": added,
            "reasons_removed": removed,
            "model_version_changed": version_changed,
            "recent_matured": recent,
        }
