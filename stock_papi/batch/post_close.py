"""Fail-closed post-close stage machine with resumable checkpoints."""

import datetime
import hashlib
import json
import math
import os
import re
from pathlib import Path

from stock_papi.batch.runtime import acquire_job_lock, job_namespace
from stock_papi.batch.status import PipelineStatusWriter


REQUIRED_CALLBACKS = (
    "load_source",
    "infer",
    "settle",
    "aggregate",
    "render",
    "publish",
    "upload",
    "remote_verify",
    "notify",
)


class PostClosePipelineError(RuntimeError):
    """Post-close input、來源 readiness 或 checkpoint 不合法。"""


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
        raise PostClosePipelineError("pipeline stage output must be finite JSON") from exc


def _write_atomic(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(_canonical(document))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class PostClosePipeline:
    def __init__(
        self,
        root,
        *,
        target_market_date,
        source_manifest,
        source_manifest_sha256,
        model_version,
        callbacks,
        max_source_attempts=6,
        retry_seconds=300,
        failure_rate_threshold=0.05,
        source_deadline=None,
        sleep_fn=lambda _seconds: None,
    ):
        if (
            type(target_market_date) is not datetime.date
            or re.fullmatch(
                r"quant/v1/manifests/TW-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}\.json",
                str(source_manifest),
            )
            is None
            or re.fullmatch(r"[0-9a-f]{64}", str(source_manifest_sha256)) is None
            or not isinstance(model_version, str)
            or not 1 <= len(model_version) <= 100
            or type(max_source_attempts) is not int
            or max_source_attempts < 1
            or type(retry_seconds) not in (int, float)
            or retry_seconds < 0
            or type(failure_rate_threshold) not in (int, float)
            or not 0 <= failure_rate_threshold <= 1
            or not isinstance(callbacks, dict)
            or any(not callable(callbacks.get(name)) for name in REQUIRED_CALLBACKS)
            or not callable(sleep_fn)
        ):
            raise ValueError("invalid post-close pipeline configuration")
        if source_deadline is not None and (
            not isinstance(source_deadline, datetime.datetime)
            or source_deadline.tzinfo is None
            or source_deadline.utcoffset() is None
        ):
            raise ValueError("source_deadline must be timezone-aware")
        self.root = Path(root)
        self.target_market_date = target_market_date
        self.source_manifest = source_manifest
        self.source_manifest_sha256 = source_manifest_sha256
        self.model_version = model_version
        self.callbacks = callbacks
        self.max_source_attempts = max_source_attempts
        self.retry_seconds = retry_seconds
        self.failure_rate_threshold = failure_rate_threshold
        self.source_deadline = source_deadline
        self.sleep_fn = sleep_fn

    def _identity(self, dry_run):
        return {
            "target_market_date": self.target_market_date.isoformat(),
            "source_manifest": self.source_manifest,
            "source_manifest_sha256": self.source_manifest_sha256,
            "model_version": self.model_version,
            "dry_run": dry_run,
        }

    def _run_id(self, dry_run):
        digest = hashlib.sha256(_canonical(self._identity(dry_run))).hexdigest()[:8]
        return f"{self.target_market_date.strftime('%Y%m%d')}T000000Z-{digest}"

    def _checkpoint_path(self, run_id, dry_run):
        current = job_namespace(self.root, "post_close_report").checkpoint
        return current.with_name(f"dry-run-{run_id}.json") if dry_run else current

    def _load_state(self, path, run_id, dry_run, checked_at):
        identity = self._identity(dry_run)
        if path.exists():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise PostClosePipelineError("post-close checkpoint is invalid") from exc
            if (
                state.get("schema_version") != 1
                or state.get("job_type") != "post_close_report"
                or state.get("run_id") != run_id
                or any(state.get(key) != value for key, value in identity.items())
                or not isinstance(state.get("completed_stages"), list)
                or not isinstance(state.get("outputs"), dict)
            ):
                raise PostClosePipelineError("post-close checkpoint identity mismatch")
            return state
        state = {
            "schema_version": 1,
            "job_type": "post_close_report",
            "run_id": run_id,
            **identity,
            "completed_stages": [],
            "outputs": {},
            "status": "running",
            "started_at": checked_at.astimezone(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        _write_atomic(path, state)
        return state

    def _validate_source(self, source):
        failure_rate = source.get("failure_rate") if isinstance(source, dict) else None
        if not isinstance(source, dict):
            raise PostClosePipelineError("source is not ready")
        if source.get("sample_data") is True:
            raise PostClosePipelineError("sample source is forbidden")
        if (
            source.get("market") != "TW"
            or source.get("market_as_of") != self.target_market_date.isoformat()
        ):
            raise PostClosePipelineError("source target market date mismatch")
        if (
            source.get("manifest_path") != self.source_manifest
            or source.get("manifest_sha256") != self.source_manifest_sha256
            or source.get("model_version") != self.model_version
        ):
            raise PostClosePipelineError("source identity mismatch")
        if (
            type(failure_rate) not in (int, float)
            or not math.isfinite(failure_rate)
            or not 0 <= failure_rate <= self.failure_rate_threshold
        ):
            raise PostClosePipelineError("source failure rate exceeds threshold")
        _canonical(source)
        return source

    def run(self, *, now=None, dry_run=False):
        checked_at = now or datetime.datetime.now(datetime.timezone.utc)
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        run_id = self._run_id(dry_run)
        path = self._checkpoint_path(run_id, dry_run)
        writer = PipelineStatusWriter(
            self.root,
            job_type="post_close_report",
            run_id=run_id,
            target_date=self.target_market_date,
        )
        with acquire_job_lock(
            self.root,
            "post_close_report",
            self.target_market_date,
            now=checked_at,
        ):
            state = self._load_state(path, run_id, dry_run, checked_at)
            if state.get("status") == "completed":
                return dict(state)
            state["status"] = "running"

            def save():
                state["updated_at"] = checked_at.astimezone(
                    datetime.timezone.utc
                ).isoformat().replace("+00:00", "Z")
                _write_atomic(path, state)

            def stage(name, status_stage, callback, *args):
                if name in state["completed_stages"]:
                    return state["outputs"][name]
                output = callback(*args)
                _canonical(output)
                state["outputs"][name] = output
                state["completed_stages"].append(name)
                save()
                writer.record(status_stage, now=checked_at)
                return output

            try:
                if "source" in state["completed_stages"]:
                    source = state["outputs"]["source"]
                else:
                    source = None
                    for attempt in range(1, self.max_source_attempts + 1):
                        if self.source_deadline is not None and checked_at >= self.source_deadline:
                            break
                        candidate = self.callbacks["load_source"]()
                        if candidate is not None:
                            source = self._validate_source(candidate)
                            break
                        writer.record(
                            "data_wait", now=checked_at, details={"processed": attempt}
                        )
                        if attempt < self.max_source_attempts:
                            self.sleep_fn(self.retry_seconds)
                    if source is None:
                        raise PostClosePipelineError("source readiness deadline exceeded")
                    state["outputs"]["source"] = source
                    state["completed_stages"].append("source")
                    save()
                inference = stage("inference", "inference", self.callbacks["infer"], source)
                settlement = stage("settlement", "settlement", self.callbacks["settle"], source)
                report = stage(
                    "aggregation",
                    "aggregation",
                    self.callbacks["aggregate"],
                    source,
                    inference,
                    settlement,
                )
                if dry_run:
                    state["status"] = "completed"
                    state["dry_run"] = True
                    save()
                    writer.record("completed", now=checked_at)
                    return dict(state)
                rendered = stage("render", "render", self.callbacks["render"], report)
                receipt = stage(
                    "publish", "publish", self.callbacks["publish"], report, rendered
                )
                stage("upload", "upload", self.callbacks["upload"], receipt)
                stage("remote_verify", "verify", self.callbacks["remote_verify"], receipt)
                stage("notify", "notify", self.callbacks["notify"], receipt)
                state["status"] = "completed"
                save()
                writer.record("completed", now=checked_at)
                return dict(state)
            except Exception as exc:
                state["status"] = "failed"
                state["last_error_type"] = type(exc).__name__
                save()
                writer.record("failed", now=checked_at, error=exc)
                raise
