"""Verified GCS reader for daily dashboard snapshots."""

import datetime
import hashlib
import hmac
import json
import re
import time


DASHBOARD_CACHE = {}
MAX_DASHBOARD_BYTES = 5_000_000


def load_dashboard_snapshot(today=None, *, load_object, cache=DASHBOARD_CACHE):
    now = time.time()
    cached = cache.get("latest")
    if cached and now - cached[1] < 300:
        return cached[0]
    latest_bytes = load_object("dashboard/v1/latest-TW.json", 100_000)
    if latest_bytes is None:
        return None
    try:
        latest = json.loads(latest_bytes.decode("utf-8"))
        path = str(latest["path"])
        digest = str(latest["sha256"])
        size = latest["size"]
        inference = datetime.date.fromisoformat(str(latest["inference_as_of"]))
        age = (today or datetime.date.today()) - inference
        if (
            latest.get("schema_version") != 1
            or latest.get("kind") != "absorb-daily-dashboard"
            or latest.get("market") != "TW"
            or re.fullmatch(r"objects/[0-9a-f]{64}\.json", path) is None
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or type(size) is not int
            or not 0 < size <= MAX_DASHBOARD_BYTES
            or not 0 <= age.days <= 14
        ):
            return None
        content = load_object(f"dashboard/v1/{path}", size)
        if (
            content is None
            or len(content) != size
            or not hmac.compare_digest(hashlib.sha256(content).hexdigest(), digest)
        ):
            return None
        document = json.loads(content.decode("utf-8"))
        if (
            not isinstance(document, dict)
            or document.get("schema_version") != 1
            or document.get("kind") != "absorb-daily-dashboard"
            or document.get("market") != "TW"
            or document.get("inference_as_of") != latest["inference_as_of"]
            or not isinstance(document.get("sector_snapshot"), dict)
            or not isinstance(document["sector_snapshot"].get("sectors"), dict)
            or not isinstance(document.get("heatmap"), list)
            or not isinstance(document.get("daily_focus"), list)
            or not isinstance(document.get("top_picks"), list)
        ):
            return None
    except (KeyError, TypeError, UnicodeError, ValueError):
        return None
    cache["latest"] = (document, now)
    return document
