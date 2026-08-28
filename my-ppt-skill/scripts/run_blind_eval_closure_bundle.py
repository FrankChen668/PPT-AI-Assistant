#!/usr/bin/env python3
"""Run blind-eval normal + strict sequentially and export manual-review queue."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path) -> int:
    print("+", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(cwd))
    return int(completed.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Blind-eval closure bundle runner.")
    parser.add_argument("--set", dest="set_path", required=True, help="Path to blind eval set JSON.")
    parser.add_argument(
        "--prefix",
        required=True,
        help="Output prefix without extension, e.g. docs/reports/blind-eval-round6",
    )
    parser.add_argument(
        "--primary-mode",
        choices=("release-safe", "dev-fast"),
        default="release-safe",
        help="Primary mode for blind metric computation.",
    )
    parser.add_argument("--slide", type=int, default=1, help="Dev-fast slide id if used.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    py = sys.executable

    script_baseline = repo_root / "my-ppt-skill" / "scripts" / "run_blind_eval_baseline.py"
    script_queue = repo_root / "my-ppt-skill" / "scripts" / "export_blind_manual_review_queue.py"
    set_path = (repo_root / args.set_path).resolve() if not Path(args.set_path).is_absolute() else Path(args.set_path)
    prefix = (repo_root / args.prefix).resolve() if not Path(args.prefix).is_absolute() else Path(args.prefix)

    normal_json = str(prefix) + ".results.json"
    normal_md = str(prefix) + ".summary.md"
    strict_json = str(prefix) + ".strict.results.json"
    strict_md = str(prefix) + ".strict.summary.md"
    queue_json = str(prefix) + ".manual-review-queue.json"
    queue_md = str(prefix) + ".manual-review-queue.md"

    normal_cmd = [
        py,
        str(script_baseline),
        "--set",
        str(set_path),
        "--mode",
        "release-safe",
        "--primary-mode",
        args.primary_mode,
        "--slide",
        str(max(1, int(args.slide))),
        "--output-json",
        normal_json,
        "--output-md",
        normal_md,
    ]
    strict_cmd = [
        py,
        str(script_baseline),
        "--set",
        str(set_path),
        "--mode",
        "release-safe",
        "--primary-mode",
        args.primary_mode,
        "--slide",
        str(max(1, int(args.slide))),
        "--enforce-blind-ready",
        "--enforce-p0-risk-zero",
        "--enforce-manual-review-contract",
        "--output-json",
        strict_json,
        "--output-md",
        strict_md,
    ]
    queue_cmd = [
        py,
        str(script_queue),
        "--set",
        str(set_path),
        "--results",
        strict_json,
        "--output-json",
        queue_json,
        "--output-md",
        queue_md,
    ]

    normal_rc = _run(normal_cmd, cwd=repo_root)
    strict_rc = _run(strict_cmd, cwd=repo_root)
    queue_rc = _run(queue_cmd, cwd=repo_root)

    print("bundle outputs:")
    print(f"- normal json: {normal_json}")
    print(f"- normal md: {normal_md}")
    print(f"- strict json: {strict_json}")
    print(f"- strict md: {strict_md}")
    print(f"- queue json: {queue_json}")
    print(f"- queue md: {queue_md}")

    if normal_rc != 0:
        return normal_rc
    if queue_rc != 0:
        return queue_rc
    return strict_rc


if __name__ == "__main__":
    raise SystemExit(main())
