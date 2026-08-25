#!/usr/bin/env python3
"""Prevent new raw UAT evidence from accumulating under docs/uat."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import PurePosixPath

RAW_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".json",
    ".log",
    ".har",
    ".zip",
}
RAW_NAME_PREFIXES = ("source_prompt_", "raw_prompt_")
DOCS_UAT_PREFIX = "docs/uat/"
TARGET_PREFIX = "evidence/uat/"


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def is_raw_uat_evidence(path: str) -> bool:
    normalized = _normalize(path)
    if not normalized.startswith(DOCS_UAT_PREFIX):
        return False

    pure = PurePosixPath(normalized)
    name = pure.name.lower()
    if pure.suffix.lower() in RAW_EXTENSIONS:
        return True
    return name.startswith(RAW_NAME_PREFIXES)


def check_paths(paths: list[str]) -> list[str]:
    return sorted({_normalize(path) for path in paths if is_raw_uat_evidence(path)})


def changed_paths(base_ref: str | None = None) -> list[str]:
    if base_ref:
        cmd = ["git", "diff", "--name-only", "--diff-filter=AM", f"{base_ref}...HEAD"]
    elif os.environ.get("GITHUB_BASE_REF"):
        cmd = [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=AM",
            f"origin/{os.environ['GITHUB_BASE_REF']}...HEAD",
        ]
    else:
        cmd = ["git", "diff", "--name-only", "--diff-filter=AM", "HEAD^", "HEAD"]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "git diff failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", help="Git ref used as the PR/push comparison base.")
    args = parser.parse_args()

    try:
        paths = changed_paths(args.base_ref)
    except RuntimeError as exc:
        print(f"UAT evidence boundary check could not compute diff: {exc}", file=sys.stderr)
        return 2

    violations = check_paths(paths)
    if violations:
        print("UAT evidence boundary check failed:", file=sys.stderr)
        for path in violations:
            relative = path[len(DOCS_UAT_PREFIX) :]
            print(
                f"- {path}: raw UAT evidence must live under {TARGET_PREFIX}{relative}",
                file=sys.stderr,
            )
        return 1

    print("UAT evidence boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
