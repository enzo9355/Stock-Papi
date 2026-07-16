"""Audit PIT inputs and build an immutable price-history research dataset."""

from __future__ import annotations

import datetime
import gzip
import hashlib
import io
import json
import math
import os
import re
import statistics
from pathlib import Path


PIT_REQUIREMENTS = (
    "historical_industry_membership",
    "shares_outstanding",
    "market_cap",
    "tradable_universe",
    "listing_delisting",
    "suspension",
    "corporate_actions",
    "source_timestamp_revision",
    "manifest_path_sha256",
    "adjusted_price_history",
)

_OPTIONAL_REQUIREMENTS = PIT_REQUIREMENTS[:7]
_MANIFEST_PATTERN = re.compile(
    r"manifests/(?P<market>TW|US)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}\.json"
)
_OBJECT_PATTERN = re.compile(r"objects/[0-9a-f]{64}\.json\.gz")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_MAX_MANIFEST_BYTES = 5_000_000
_MAX_OBJECT_BYTES = 10_000_000
_MAX_UNCOMPRESSED_BYTES = 20_000_000


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
        raise ValueError("research artifact is not finite JSON") from exc


def _timestamp(value=None):
    timestamp = value or datetime.datetime.now(datetime.timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return (
        timestamp.astimezone(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _safe_child(root, relative, label):
    root = Path(root).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escaped allowlisted root") from exc
    return candidate


def _read_limited(path, maximum, label):
    try:
        content = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if not 0 < len(content) <= maximum:
        raise ValueError(f"{label} size is invalid")
    return content


def _load_object(content, label):
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} JSON is invalid") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    return document


def _write_immutable(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise ValueError("immutable research artifact is unreadable") from exc
        if existing != content:
            raise ValueError("immutable research artifact conflict")
        return
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _validated_source(root, market):
    if market not in {"TW", "US"}:
        raise ValueError("market is not supported")
    quant_root = Path(root) / "publish" / "quant" / "v1"
    latest_path = quant_root / f"latest-{market}.json"
    latest_bytes = _read_limited(latest_path, 1_000_000, "quant latest pointer")
    latest = _load_object(latest_bytes, "quant latest pointer")
    manifest_relative = latest.get("manifest")
    manifest_sha = str(latest.get("manifest_sha256") or "")
    if (
        latest.get("schema_version") != 2
        or latest.get("market") != market
        or not isinstance(manifest_relative, str)
        or _MANIFEST_PATTERN.fullmatch(manifest_relative) is None
        or _MANIFEST_PATTERN.fullmatch(manifest_relative).group("market") != market
        or _SHA256_PATTERN.fullmatch(manifest_sha) is None
    ):
        raise ValueError("quant latest pointer identity is invalid")
    manifest_path = _safe_child(
        quant_root, manifest_relative, "quant source manifest"
    )
    manifest_bytes = _read_limited(
        manifest_path, _MAX_MANIFEST_BYTES, "quant source manifest"
    )
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_sha:
        raise ValueError("quant source manifest SHA-256 mismatch")
    manifest = _load_object(manifest_bytes, "quant source manifest")
    symbols = manifest.get("symbols")
    if (
        manifest.get("schema_version") != 2
        or manifest.get("market") != market
        or not isinstance(manifest.get("generated_at"), str)
        or not isinstance(manifest.get("market_as_of"), str)
        or not isinstance(symbols, dict)
        or type(manifest.get("universe_count")) is not int
        or type(manifest.get("symbol_count")) is not int
        or manifest["symbol_count"] != len(symbols)
        or manifest["universe_count"] < manifest["symbol_count"]
    ):
        raise ValueError("quant source manifest schema is invalid")
    try:
        datetime.datetime.fromisoformat(
            manifest["generated_at"].replace("Z", "+00:00")
        )
        datetime.date.fromisoformat(manifest["market_as_of"])
    except ValueError as exc:
        raise ValueError("quant source manifest timestamp is invalid") from exc
    valid_metadata = 0
    for symbol, metadata in symbols.items():
        if (
            not isinstance(symbol, str)
            or not isinstance(metadata, dict)
            or _OBJECT_PATTERN.fullmatch(str(metadata.get("path") or "")) is None
            or metadata.get("path")
            != f"objects/{str(metadata.get('sha256') or '')}.json.gz"
            or _SHA256_PATTERN.fullmatch(str(metadata.get("sha256") or ""))
            is None
            or type(metadata.get("size")) is not int
            or not 0 < metadata["size"] <= _MAX_OBJECT_BYTES
            or type(metadata.get("uncompressed_size")) is not int
            or not 0 < metadata["uncompressed_size"] <= _MAX_UNCOMPRESSED_BYTES
            or metadata.get("as_of") != manifest["market_as_of"]
        ):
            raise ValueError(f"quant source object metadata is invalid: {symbol}")
        valid_metadata += 1
    return {
        "quant_root": quant_root,
        "latest_path": latest_path,
        "latest": latest,
        "manifest_path": manifest_path,
        "manifest_relative": manifest_relative,
        "manifest_sha256": manifest_sha,
        "manifest": manifest,
        "valid_object_metadata": valid_metadata,
    }


def _optional_source_evidence(root, market, requirement):
    relative = (
        Path("research")
        / "pit_sources"
        / "v1"
        / f"{requirement}-{market}.json"
    )
    path = Path(root) / relative
    if not path.is_file():
        return {
            "status": "unavailable",
            "evidence": {
                "searched_path": relative.as_posix(),
                "reason": (
                    "no validated immutable PIT source artifact was found; "
                    "absence is not inferred from price history"
                ),
            },
        }
    content = _read_limited(path, _MAX_MANIFEST_BYTES, f"{requirement} source")
    document = _load_object(content, f"{requirement} source")
    if (
        document.get("schema_version") != 1
        or document.get("kind") != "absorb-pit-source"
        or document.get("requirement") != requirement
        or document.get("market") != market
        or not isinstance(document.get("generated_at"), str)
        or not isinstance(document.get("source_revision"), str)
        or not document["source_revision"].strip()
        or not isinstance(document.get("records"), list)
        or not document["records"]
    ):
        return {
            "status": "unavailable",
            "evidence": {
                "path": relative.as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "reason": "candidate PIT source artifact failed schema validation",
            },
        }
    return {
        "status": "available",
        "evidence": {
            "path": relative.as_posix(),
            "sha256": hashlib.sha256(content).hexdigest(),
            "generated_at": document["generated_at"],
            "source_revision": document["source_revision"],
            "record_count": len(document["records"]),
        },
    }


def audit_pit_availability(root, *, market="TW", now=None, code_sha):
    """Return an evidence-backed availability audit without inventing data."""

    if _GIT_SHA_PATTERN.fullmatch(str(code_sha)) is None:
        raise ValueError("code_sha is invalid")
    root = Path(root)
    source = _validated_source(root, market)
    manifest = source["manifest"]
    requirements = {
        requirement: _optional_source_evidence(root, market, requirement)
        for requirement in _OPTIONAL_REQUIREMENTS
    }
    requirements["source_timestamp_revision"] = {
        "status": "available",
        "evidence": {
            "generated_at": manifest["generated_at"],
            "market_as_of": manifest["market_as_of"],
            "latest_generated_at": source["latest"].get("generated_at"),
            "revision": source["manifest_sha256"],
        },
    }
    requirements["manifest_path_sha256"] = {
        "status": "available",
        "evidence": {
            "path": f"quant/v1/{source['manifest_relative']}",
            "sha256": source["manifest_sha256"],
            "size": source["manifest_path"].stat().st_size,
        },
    }
    requirements["adjusted_price_history"] = {
        "status": "available",
        "evidence": {
            "declared_object_count": source["valid_object_metadata"],
            "object_contract": (
                "content-addressed gzip JSON with SHA-256, compressed size, "
                "uncompressed size and market as-of identity"
            ),
            "price_field_policy": (
                "YF_CLOSE when finite and positive, otherwise Close; "
                "corporate-action completeness remains a separate Gate"
            ),
        },
    }
    blockers = [
        requirement
        for requirement in PIT_REQUIREMENTS
        if requirements[requirement]["status"] != "available"
    ]
    return {
        "schema_version": 1,
        "kind": "absorb-pit-availability-audit",
        "market": market,
        "generated_at": _timestamp(now),
        "code_sha": code_sha,
        "source_manifest": {
            "path": f"quant/v1/{source['manifest_relative']}",
            "sha256": source["manifest_sha256"],
            "generated_at": manifest["generated_at"],
            "market_as_of": manifest["market_as_of"],
            "symbol_count": manifest["symbol_count"],
            "universe_count": manifest["universe_count"],
        },
        "requirements": requirements,
        "formal_pit_status": "PASS" if not blockers else "BLOCKED",
        "formal_pit_blockers": blockers,
    }


def write_pit_audit(root, audit):
    if (
        not isinstance(audit, dict)
        or audit.get("schema_version") != 1
        or audit.get("kind") != "absorb-pit-availability-audit"
        or set(audit.get("requirements") or {}) != set(PIT_REQUIREMENTS)
    ):
        raise ValueError("PIT availability audit is invalid")
    content = _canonical(audit)
    digest = hashlib.sha256(content).hexdigest()
    path = (
        Path(root)
        / "publish"
        / "research"
        / "v1"
        / "pit"
        / "audits"
        / f"{digest}.json"
    )
    _write_immutable(path, content)
    return {"path": str(path), "sha256": digest}


def _finite_number(value):
    return (
        type(value) in (int, float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _history_rows(source, symbol, metadata):
    path = _safe_child(source["quant_root"], metadata["path"], "quant source object")
    compressed = _read_limited(path, _MAX_OBJECT_BYTES, "quant source object")
    if (
        len(compressed) != metadata["size"]
        or hashlib.sha256(compressed).hexdigest() != metadata["sha256"]
    ):
        raise ValueError(f"quant source object hash or size mismatch: {symbol}")
    try:
        raw = gzip.decompress(compressed)
    except (OSError, EOFError) as exc:
        raise ValueError(f"quant source object gzip is invalid: {symbol}") from exc
    if len(raw) != metadata["uncompressed_size"]:
        raise ValueError(f"quant source object uncompressed size mismatch: {symbol}")
    document = _load_object(raw, f"quant source object {symbol}")
    if (
        document.get("symbol") != symbol
        or document.get("market") != source["manifest"]["market"]
        or document.get("as_of") != metadata["as_of"]
        or not isinstance(document.get("daily"), list)
    ):
        raise ValueError(f"quant source object identity is invalid: {symbol}")
    rows = []
    seen_dates = set()
    for value in document["daily"]:
        if not isinstance(value, dict):
            continue
        date_value = str(value.get("Date") or "").split("T", 1)[0]
        try:
            date = datetime.date.fromisoformat(date_value)
        except ValueError:
            continue
        if date > datetime.date.fromisoformat(metadata["as_of"]):
            raise ValueError(f"future source row exceeds manifest as-of: {symbol}")
        close = value.get("YF_CLOSE")
        if not _finite_number(close) or close <= 0:
            close = value.get("Close")
        volume = value.get("Volume")
        if (
            date_value in seen_dates
            or not _finite_number(close)
            or close <= 0
            or not _finite_number(volume)
            or volume < 0
        ):
            continue
        seen_dates.add(date_value)
        rows.append((date_value, float(close), float(volume)))
    rows.sort(key=lambda item: item[0])
    if len(rows) < 30:
        raise ValueError(f"insufficient verified price history: {symbol}")
    return rows


def _research_rows(symbol, history):
    close = [value[1] for value in history]
    volume = [value[2] for value in history]
    rows = []
    for index in range(20, len(history) - 5):
        returns = [
            close[position] / close[position - 1] - 1.0
            for position in range(index - 19, index + 1)
        ]
        mean_volume = statistics.fmean(volume[index - 19 : index + 1])
        if mean_volume <= 0:
            continue
        future_return = close[index + 5] / close[index] - 1.0
        document = {
            "symbol": symbol,
            "source_market_date": history[index][0],
            "close": close[index],
            "volume": volume[index],
            "return_1": returns[-1],
            "momentum_5": close[index] / close[index - 5] - 1.0,
            "momentum_20": close[index] / close[index - 20] - 1.0,
            "volatility_20": statistics.pstdev(returns),
            "volume_ratio_20": volume[index] / mean_volume,
            "future_return_5": future_return,
            "direction_5": int(future_return > 0),
        }
        if not all(
            _finite_number(value)
            for key, value in document.items()
            if key not in {"symbol", "source_market_date", "direction_5"}
        ):
            continue
        rows.append(document)
    return rows


def _gzip(content):
    target = io.BytesIO()
    with gzip.GzipFile(fileobj=target, mode="wb", mtime=0) as stream:
        stream.write(content)
    return target.getvalue()


def build_price_research_dataset(
    root,
    audit,
    *,
    git_sha,
    now=None,
    require_formal=False,
    max_symbols=None,
):
    """Build an exploratory immutable dataset; formal PIT remains fail-closed."""

    if _GIT_SHA_PATTERN.fullmatch(str(git_sha)) is None:
        raise ValueError("git_sha is invalid")
    if (
        not isinstance(audit, dict)
        or audit.get("schema_version") != 1
        or audit.get("kind") != "absorb-pit-availability-audit"
        or set(audit.get("requirements") or {}) != set(PIT_REQUIREMENTS)
    ):
        raise ValueError("PIT availability audit is invalid")
    if require_formal and audit.get("formal_pit_status") != "PASS":
        raise ValueError("formal PIT dataset is blocked by unavailable dependencies")
    if max_symbols is not None and (
        type(max_symbols) is not int or max_symbols < 1
    ):
        raise ValueError("max_symbols must be positive")

    root = Path(root)
    source = _validated_source(root, audit.get("market"))
    expected_source = audit.get("source_manifest") or {}
    if (
        expected_source.get("path")
        != f"quant/v1/{source['manifest_relative']}"
        or expected_source.get("sha256") != source["manifest_sha256"]
    ):
        raise ValueError("PIT audit source manifest no longer matches")
    audit_result = write_pit_audit(root, audit)

    symbols = sorted(source["manifest"]["symbols"])
    if max_symbols is not None:
        symbols = symbols[:max_symbols]
    rows = []
    verified_symbols = 0
    for symbol in symbols:
        history = _history_rows(
            source, symbol, source["manifest"]["symbols"][symbol]
        )
        symbol_rows = _research_rows(symbol, history)
        if not symbol_rows:
            continue
        rows.extend(symbol_rows)
        verified_symbols += 1
    if verified_symbols < 1 or len(rows) < 30:
        raise ValueError("verified price research dataset is too small")
    rows.sort(key=lambda item: (item["source_market_date"], item["symbol"]))
    uncompressed = b"".join(_canonical(row) + b"\n" for row in rows)
    compressed = _gzip(uncompressed)
    dataset_sha = hashlib.sha256(compressed).hexdigest()
    uncompressed_sha = hashlib.sha256(uncompressed).hexdigest()
    publish = Path(root) / "publish" / "research" / "v1" / "pit"
    dataset_relative = f"datasets/{dataset_sha}.jsonl.gz"
    dataset_path = publish / dataset_relative
    _write_immutable(dataset_path, compressed)

    blockers = list(audit.get("formal_pit_blockers") or [])
    manifest = {
        "schema_version": 1,
        "kind": "absorb-pit-price-dataset",
        "market": audit["market"],
        "generated_at": _timestamp(now),
        "dataset_path": dataset_relative,
        "dataset_sha256": dataset_sha,
        "dataset_size": len(compressed),
        "dataset_uncompressed_sha256": uncompressed_sha,
        "dataset_uncompressed_size": len(uncompressed),
        "row_count": len(rows),
        "symbol_count": verified_symbols,
        "data_start": rows[0]["source_market_date"],
        "data_end": rows[-1]["source_market_date"],
        "universe_selection": {
            "policy": "lexicographically sorted symbols from the cutoff manifest",
            "source_symbol_count": source["manifest"]["symbol_count"],
            "requested_max_symbols": max_symbols,
            "verified_symbol_count": verified_symbols,
            "historical_membership_available": (
                audit["requirements"]["tradable_universe"]["status"]
                == "available"
            ),
        },
        "source_manifests": [
            {
                "path": f"quant/v1/{source['manifest_relative']}",
                "sha256": source["manifest_sha256"],
                "generated_at": source["manifest"]["generated_at"],
                "market_as_of": source["manifest"]["market_as_of"],
            }
        ],
        "availability_audit": {
            "path": str(
                Path(audit_result["path"]).relative_to(
                    Path(root) / "publish"
                )
            ).replace("\\", "/"),
            "sha256": audit_result["sha256"],
        },
        "code_sha": audit["code_sha"],
        "git_sha": git_sha,
        "feature_schema_version": 1,
        "features": [
            "return_1",
            "momentum_5",
            "momentum_20",
            "volatility_20",
            "volume_ratio_20",
        ],
        "target_definition": {
            "name": "five_session_adjusted_close_return",
            "horizon_sessions": 5,
            "return_field": "future_return_5",
            "classification_field": "direction_5",
            "positive_rule": "future_return_5 > 0",
        },
        "pit_policy": {
            "feature_window": "current and prior rows only",
            "target_window": "next five observed rows only",
            "existing_model_scores_used": False,
            "static_cutoff_universe": True,
            "survivorship_bias_risk": True,
            "corporate_action_contract": (
                "provider-adjusted close is used when available, but explicit "
                "corporate-action history is unavailable"
            ),
            "formal_pit_status": audit["formal_pit_status"],
            "formal_pit_blockers": blockers,
            "promotion_eligible": not blockers,
        },
        "split_policy": {
            "method": "expanding_walk_forward",
            "purge_sessions": 5,
            "embargo_sessions": 5,
            "untouched_final_holdout_fraction": 0.20,
            "selection_uses_final_holdout": False,
        },
    }
    manifest_content = _canonical(manifest)
    manifest_sha = hashlib.sha256(manifest_content).hexdigest()
    manifest_path = publish / "manifests" / f"{manifest_sha}.json"
    _write_immutable(manifest_path, manifest_content)
    return {
        "dataset_path": str(dataset_path),
        "dataset_sha256": dataset_sha,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "formal_pit_status": audit["formal_pit_status"],
    }
