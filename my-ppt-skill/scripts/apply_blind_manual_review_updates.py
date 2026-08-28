#!/usr/bin/env python3
"""Apply manual visual review updates to blind-eval set config."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

VALID_STATUS = {"pending", "complete", "reject"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_updates(
    *,
    set_config: dict[str, Any],
    updates_payload: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    projects = set_config.get("projects")
    if not isinstance(projects, list):
        raise ValueError("set config missing projects list")

    reviews = updates_payload.get("reviews")
    if not isinstance(reviews, list):
        raise ValueError("updates payload missing reviews list")

    blind_map: dict[str, dict[str, Any]] = {}
    for item in projects:
        if not isinstance(item, dict):
            continue
        if str(item.get("baseline_role") or "").strip() != "blind_holdout":
            continue
        name = str(item.get("project") or "").strip()
        if name:
            blind_map[name] = item

    changed: list[str] = []
    violations: list[str] = []
    for review in reviews:
        if not isinstance(review, dict):
            violations.append("review entry is not object")
            continue
        name = str(review.get("project") or "").strip()
        status = str(review.get("status") or "").strip().lower()
        reviewer = str(review.get("reviewer") or "").strip()
        score = review.get("score")
        if not name:
            violations.append("review project is empty")
            continue
        if name not in blind_map:
            violations.append(f"{name}: not a blind_holdout project in set")
            continue
        if status not in VALID_STATUS:
            violations.append(f"{name}: invalid status '{status or '(empty)'}'")
            continue
        if status in {"complete", "reject"} and not reviewer:
            violations.append(f"{name}: reviewer required when status={status}")
            continue

        target = blind_map[name]
        manual = target.get("manual_visual_review")
        manual_map = manual if isinstance(manual, dict) else {}
        manual_map["status"] = status
        manual_map["reviewer"] = reviewer
        manual_map["score"] = score
        if "notes" in review:
            manual_map["notes"] = str(review.get("notes") or "")
        target["manual_visual_review"] = manual_map
        changed.append(name)

    updated = dict(set_config)
    updated["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return updated, changed, violations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply blind manual-review updates to set JSON.")
    parser.add_argument("--set", dest="set_path", required=True, help="Path to blind eval set JSON.")
    parser.add_argument("--updates", required=True, help="Path to update payload JSON.")
    parser.add_argument("--output-set", default="", help="Output path (default: overwrite --set path).")
    parser.add_argument("--backup", action="store_true", help="Write .bak copy before overwriting output set.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    set_path = Path(args.set_path).resolve()
    updates_path = Path(args.updates).resolve()
    out_set = Path(args.output_set).resolve() if args.output_set else set_path

    if not set_path.exists():
        print(f"error: set file not found: {set_path}")
        return 2
    if not updates_path.exists():
        print(f"error: updates file not found: {updates_path}")
        return 2

    set_config = _load_json(set_path)
    updates_payload = _load_json(updates_path)
    try:
        updated, changed, violations = apply_updates(set_config=set_config, updates_payload=updates_payload)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2

    if violations:
        print("update violations:")
        for item in violations:
            print(f"- {item}")
        return 1

    out_set.parent.mkdir(parents=True, exist_ok=True)
    if args.backup and out_set.exists():
        backup_path = out_set.with_suffix(out_set.suffix + ".bak")
        backup_path.write_text(out_set.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"wrote backup: {backup_path}")

    out_set.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote updated set: {out_set}")
    print(f"updated projects: {len(changed)}")
    if changed:
        print("project list:", ", ".join(changed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
