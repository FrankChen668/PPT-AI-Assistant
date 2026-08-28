#!/usr/bin/env python3
"""Validate fixed-baseline set and trend ledger contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _validate_source(item: dict[str, Any], repo_root: Path, errors: list[str]) -> None:
    project_name = str(item.get("project") or "").strip()
    source = item.get("source")
    if not isinstance(source, dict):
        errors.append(f"baseline source must be an object: {project_name}")
        return

    source_type = str(source.get("type") or "").strip()
    source_path_raw = str(source.get("path") or "").strip()
    _require(
        source_type in {"generator", "tracked_project"},
        f"unsupported baseline source type '{source_type}': {project_name}",
        errors,
    )
    _require(bool(source_path_raw), f"baseline source path is required: {project_name}", errors)
    if not source_path_raw:
        return

    source_path = Path(source_path_raw)
    if source_path.is_absolute() or ".." in source_path.parts:
        errors.append(f"baseline source must be a repo-relative path: {project_name}")
        return

    resolved = repo_root / source_path
    _require(resolved.exists(), f"baseline source does not exist: {source_path_raw}", errors)
    if not resolved.exists():
        return
    if source_type == "generator":
        _require(resolved.is_file(), f"baseline generator must be a file: {source_path_raw}", errors)
    if source_type == "tracked_project":
        _require(
            resolved.is_dir() and (resolved / "blueprint.json").is_file(),
            f"tracked baseline project must include blueprint.json: {source_path_raw}",
            errors,
        )


def validate_set(
    path: Path,
    errors: list[str],
    *,
    repo_root: Path | None = None,
) -> dict[str, int]:
    payload = _load_json(path)
    _require(isinstance(payload, dict), f"{path} root must be object", errors)
    projects = payload.get("projects") if isinstance(payload, dict) else None
    _require(isinstance(projects, list), f"{path} must contain projects[]", errors)
    positive = 0
    failure = 0
    if isinstance(projects, list):
        for item in projects:
            if not isinstance(item, dict):
                errors.append("projects[] contains non-object item")
                continue
            _validate_source(item, repo_root or _repo_root(), errors)
            role = str(item.get("baseline_role") or "").strip()
            expected = item.get("expected")
            expected_map = expected if isinstance(expected, dict) else {}
            release_expected = str(expected_map.get("release-safe") or "").strip().lower()
            if role == "positive_baseline":
                positive += 1
                _require(
                    release_expected == "pass",
                    f"positive_baseline must set expected.release-safe=pass: {item.get('project')}",
                    errors,
                )
            if role == "failure_regression":
                failure += 1
                _require(
                    release_expected == "fail",
                    f"failure_regression must set expected.release-safe=fail: {item.get('project')}",
                    errors,
                )
    _require(positive > 0, "fixed baseline set must include positive_baseline samples", errors)
    _require(failure > 0, "fixed baseline set must include failure_regression samples", errors)
    return {"positive": positive, "failure": failure}


def validate_trend(path: Path, errors: list[str]) -> dict[str, int]:
    payload = _load_json(path)
    _require(isinstance(payload, dict), f"{path} root must be object", errors)
    entries = payload.get("entries") if isinstance(payload, dict) else None
    _require(isinstance(entries, list), f"{path} must contain entries[]", errors)
    count = 0
    if isinstance(entries, list):
        for row in entries:
            if not isinstance(row, dict):
                errors.append("trend entries[] contains non-object item")
                continue
            count += 1
            for key in (
                "generated_at",
                "tag",
                "mode",
                "positive_delivery_pass_rate_percent",
                "negative_guardrail_detection_rate_percent",
                "unexpected_pass",
                "unexpected_fail",
                "threshold_status",
            ):
                _require(key in row, f"trend entry missing key '{key}'", errors)
    return {"entries": count}


def main() -> int:
    repo = _repo_root()
    set_path = repo / "docs" / "reports" / "fixed-baseline-set.json"
    trend_path = repo / "docs" / "reports" / "fixed-baseline-trend.json"

    errors: list[str] = []
    if not set_path.exists():
        errors.append(f"missing set file: {set_path}")
    if not trend_path.exists():
        errors.append(f"missing trend file: {trend_path}")

    set_stats = {"positive": 0, "failure": 0}
    trend_stats = {"entries": 0}
    if not errors:
        set_stats = validate_set(set_path, errors)
        trend_stats = validate_trend(trend_path, errors)

    if errors:
        for message in errors:
            print(f"ERROR: {message}")
        return 1

    print(
        "baseline_contract=pass "
        f"positive={set_stats['positive']} "
        f"failure={set_stats['failure']} "
        f"trend_entries={trend_stats['entries']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
