"""Idempotent public report notification receipts."""

import datetime
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


class NotificationError(ValueError):
    pass


def _write_atomic(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with temporary.open("wb") as stream:
        stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


class NotificationManager:
    def __init__(self, root, *, send, max_attempts=3):
        if not callable(send) or type(max_attempts) is not int or not 1 <= max_attempts <= 5:
            raise ValueError("invalid notification manager")
        self.root = Path(root) / "logs" / "notifications" / "v1"
        self.send = send
        self.max_attempts = max_attempts

    def deliver(self, *, report_type, content_sha256, audience, public_url, summary, now):
        parsed = urlsplit(public_url)
        if (
            report_type not in {"post_close", "pre_market", "weekly_model"}
            or re.fullmatch(r"[0-9a-f]{64}", str(content_sha256)) is None
            or audience not in {"admin", "broadcast"}
            or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or not isinstance(summary, list) or len(summary) > 10
            or not all(isinstance(value, str) and len(value) <= 300 for value in summary)
            or not isinstance(now, datetime.datetime) or now.tzinfo is None
        ):
            raise NotificationError("invalid notification input")
        identity = f"{report_type}|{content_sha256}|{audience}".encode()
        key = hashlib.sha256(identity).hexdigest()
        path = self.root / audience / f"{key}.json"
        if path.exists():
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("status") == "sent":
                return {**document, "receipt_path": str(path)}
        else:
            document = {"schema_version": 1, "notification_key": key, "report_type": report_type, "content_sha256": content_sha256, "audience": audience, "public_url": public_url, "attempts": 0}
        labels = {"post_close": "盤後分析", "pre_market": "盤前更新", "weekly_model": "模型驗證週報"}
        message = f"Stock Papi {labels[report_type]}\n" + ("\n".join(summary) + "\n" if summary else "") + public_url
        document["status"] = "pending"; _write_atomic(path, document)
        for _ in range(self.max_attempts - document["attempts"]):
            document["attempts"] += 1; _write_atomic(path, document)
            try:
                self.send(message, audience)
            except Exception as exc:
                document["status"] = "failed"; document["last_error_type"] = type(exc).__name__; _write_atomic(path, document)
                continue
            document["status"] = "sent"
            document["sent_at"] = now.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
            document.pop("last_error_type", None); _write_atomic(path, document); break
        return {**document, "receipt_path": str(path)}
