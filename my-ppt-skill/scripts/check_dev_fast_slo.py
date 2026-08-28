#!/usr/bin/env python3
"""Check dev-fast runtime SLO from the latest run artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def check_dev_fast_slo(project_dir: Path, threshold: float = 5.0) -> tuple[bool, str]:
    report = project_dir / "qa" / "dev-fast-last-run.json"
    if not report.exists():
        return False, f"Missing dev-fast report: {report}"
    try:
        payload = json.loads(report.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return False, f"Invalid dev-fast report JSON: {exc}"
    elapsed = float(payload.get("elapsed_sec", 0.0))
    if elapsed > threshold:
        return False, f"dev-fast SLO exceeded: elapsed={elapsed:.2f}s threshold={threshold:.2f}s"
    return True, f"dev-fast SLO ok: elapsed={elapsed:.2f}s threshold={threshold:.2f}s"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate dev-fast SLO based on last run report.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--threshold", type=float, default=5.0, help="Max allowed elapsed seconds.")
    args = parser.parse_args(argv)

    ok, message = check_dev_fast_slo(args.project_dir.resolve(), threshold=max(0.0, float(args.threshold)))
    stream = sys.stdout if ok else sys.stderr
    print(message, file=stream)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
