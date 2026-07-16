"""CLI for PIT availability audit and immutable price research datasets."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .pit_dataset import (
    audit_pit_availability,
    build_price_research_dataset,
    write_pit_audit,
)


def _git_sha():
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description="ABSORB PIT research dataset")
    parser.add_argument(
        "command",
        choices=("audit", "build", "all"),
    )
    parser.add_argument("--root", type=Path, default=Path(r"D:\AbsorbData"))
    parser.add_argument("--market", choices=("TW", "US"), default="TW")
    parser.add_argument("--git-sha")
    parser.add_argument("--max-symbols", type=int)
    parser.add_argument("--require-formal", action="store_true")
    args = parser.parse_args(argv)

    git_sha = args.git_sha or _git_sha()
    audit = audit_pit_availability(
        args.root,
        market=args.market,
        code_sha=git_sha,
    )
    audit_result = write_pit_audit(args.root, audit)
    result = {"audit": audit_result, "formal_pit_status": audit["formal_pit_status"]}
    if args.command in {"build", "all"}:
        result["dataset"] = build_price_research_dataset(
            args.root,
            audit,
            git_sha=git_sha,
            require_formal=args.require_formal,
            max_symbols=args.max_symbols,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
