import datetime
from pathlib import Path


TAIPEI = datetime.timezone(datetime.timedelta(hours=8), "Asia/Taipei")
RUN_START = datetime.time(5, 30)
DRAIN_START = datetime.time(9, 20)
CHECKPOINT_START = datetime.time(9, 25)
RUN_END = datetime.time(9, 30)


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
