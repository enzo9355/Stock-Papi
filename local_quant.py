import datetime
import json
import os
import secrets
import shutil
from pathlib import Path


TAIPEI = datetime.timezone(datetime.timedelta(hours=8), "Asia/Taipei")
RUN_START = datetime.time(5, 30)
DRAIN_START = datetime.time(9, 20)
CHECKPOINT_START = datetime.time(9, 25)
RUN_END = datetime.time(9, 30)
LAYOUT_DIRS = (
    "raw", "cache", "checkpoints", "artifacts", "publish", "logs", "secrets",
)


def validate_data_root(path):
    path = Path(path).expanduser()
    if (
        path.drive.upper() != "D:"
        or path.parent != Path("D:/")
        or path.name.lower() != "stockpapidata"
    ):
        raise ValueError(r"data root must be D:\StockPapiData")
    return path


def window_phase(now=None):
    current = (now or datetime.datetime.now(TAIPEI)).astimezone(TAIPEI).time()
    if RUN_START <= current < DRAIN_START:
        return "run"
    if DRAIN_START <= current < CHECKPOINT_START:
        return "drain"
    if CHECKPOINT_START <= current < RUN_END:
        return "checkpoint"
    return "closed"


def ensure_layout(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name in LAYOUT_DIRS:
        (root / name).mkdir(exist_ok=True)
    return root


def check_free_space(root, min_free_gb=100.0, free_bytes=None):
    free_bytes = shutil.disk_usage(Path(root)).free if free_bytes is None else free_bytes
    if free_bytes < min_free_gb * 1024**3:
        raise RuntimeError(f"D drive requires at least {min_free_gb:g} GB free")
    return free_bytes


class RunnerLock:
    def __init__(self, path, token):
        self.path = Path(path)
        self.token = token

    def release(self):
        if not self.path.exists():
            return
        try:
            current = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("runner lock is unreadable") from exc
        if current.get("token") != self.token:
            raise RuntimeError("runner lock ownership changed")
        self.path.unlink()

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        self.release()


def acquire_lock(root, now=None, stale_after=datetime.timedelta(hours=6)):
    now = now or datetime.datetime.now(TAIPEI)
    lock_path = Path(root) / "checkpoints" / "runner.lock"
    if lock_path.exists():
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
            started_at = datetime.datetime.fromisoformat(existing["started_at"])
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("existing runner lock is invalid") from exc
        if now - started_at <= stale_after:
            raise RuntimeError("local quant runner is already active")
        archive = lock_path.with_name(
            f"runner.lock.stale.{now.strftime('%Y%m%dT%H%M%S')}"
        )
        os.replace(lock_path, archive)

    token = secrets.token_hex(16)
    payload = json.dumps(
        {"pid": os.getpid(), "token": token, "started_at": now.isoformat()},
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        descriptor = os.open(
            lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as exc:
        raise RuntimeError("local quant runner is already active") from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return RunnerLock(lock_path, token)


def save_checkpoint(root, state):
    if not isinstance(state, dict):
        raise TypeError("checkpoint must be a dictionary")
    checkpoint = Path(root) / "checkpoints" / "progress.json"
    temporary = checkpoint.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, checkpoint)


def load_checkpoint(root):
    checkpoint = Path(root) / "checkpoints" / "progress.json"
    if not checkpoint.exists():
        return {}
    try:
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("checkpoint is invalid") from exc
    if not isinstance(state, dict):
        raise RuntimeError("checkpoint must contain an object")
    return state
