from __future__ import annotations

import dataclasses
import os
from pathlib import Path


class AbsorbConfigError(RuntimeError):
    pass


def migrated_env(name: str, legacy_name: str, *, default="", environ=None) -> str:
    environ = os.environ if environ is None else environ
    current = str(environ.get(name) or "").strip()
    legacy = str(environ.get(legacy_name) or "").strip()
    if current and legacy and current != legacy:
        raise AbsorbConfigError(f"conflicting environment variables: {name} and deprecated {legacy_name}")
    return current or legacy or default


@dataclasses.dataclass(frozen=True)
class AbsorbConfig:
    environment: str = "production"
    data_root: Path = Path(r"D:\AbsorbData")
    report_root: Path = Path(r"D:\AbsorbData\reports")

    @classmethod
    def from_env(cls, environ=None):
        environment = migrated_env("ABSORB_ENV", "STOCK_PAPI_ENV", default="production", environ=environ)
        data_root = Path(
            migrated_env(
                "ABSORB_DATA_ROOT", "STOCK_PAPI_DATA_ROOT",
                default=r"D:\AbsorbData", environ=environ,
            )
        )
        report_root = Path(
            migrated_env(
                "ABSORB_REPORT_ROOT", "STOCK_PAPI_REPORT_ROOT",
                default=str(data_root / "reports"), environ=environ,
            )
        )
        return cls(environment=environment, data_root=data_root, report_root=report_root)
