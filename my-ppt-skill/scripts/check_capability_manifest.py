#!/usr/bin/env python3
"""Validate docs/superpowers/capabilities.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, TypeGuard

ALLOWED_STATUS = {"executable", "planned", "deprecated", "runtime_artifact"}
REQUIRED_EXECUTABLE_FIELDS = (
    "trigger",
    "inputs",
    "outputs",
    "boundary",
    "verification_command",
    "last_verified",
    "evidence",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the superpowers capability manifest.")
    parser.add_argument("--repo-root", default="", help="Repository root path (auto-detected by default).")
    parser.add_argument("--manifest", default="", help="Optional manifest path override.")
    return parser.parse_args(argv)


def detect_repo_root(raw: str) -> Path:
    if raw.strip():
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def detect_manifest_path(repo_root: Path, raw: str) -> Path:
    if raw.strip():
        path = Path(raw).expanduser()
        return path if path.is_absolute() else (repo_root / path).resolve()
    return repo_root / "docs" / "superpowers" / "capabilities.json"


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_empty_string_list(value: Any) -> TypeGuard[list[str]]:
    return isinstance(value, list) and bool(value) and all(_is_non_empty_string(item) for item in value)


def validate_manifest(payload: dict[str, Any], *, repo_root: Path) -> list[str]:
    errors: list[str] = []
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        return ["manifest must contain a non-empty 'capabilities' list."]

    seen_names: set[str] = set()
    for index, item in enumerate(capabilities, start=1):
        label = f"capabilities[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object.")
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            errors.append(f"{label} missing required field: name")
            continue
        if name in seen_names:
            errors.append(f"{label} has duplicate name: {name}")
        seen_names.add(name)

        status = str(item.get("status") or "").strip()
        if status not in ALLOWED_STATUS:
            errors.append(f"{label} has unsupported status: {status or '<missing>'}")
            continue
        if status != "executable":
            continue

        for field in REQUIRED_EXECUTABLE_FIELDS:
            value = item.get(field)
            if field in {"inputs", "outputs", "evidence"}:
                if not _is_non_empty_string_list(value):
                    errors.append(f"{label} executable field '{field}' must be a non-empty string list.")
            elif not _is_non_empty_string(value):
                errors.append(f"{label} executable field '{field}' must be a non-empty string.")

        evidence = item.get("evidence")
        if _is_non_empty_string_list(evidence):
            for evidence_path in evidence:
                resolved = (repo_root / str(evidence_path)).resolve()
                if not resolved.exists():
                    errors.append(f"{label} evidence path does not exist: {evidence_path}")

    return errors


def _print_result(manifest_path: Path, errors: list[str]) -> int:
    if errors:
        print(f"capability_manifest=fail path={manifest_path}")
        for message in errors:
            print(f"- {message}")
        return 1
    print(f"capability_manifest=pass path={manifest_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = detect_repo_root(args.repo_root)
    manifest_path = detect_manifest_path(repo_root, args.manifest)
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    errors = validate_manifest(payload, repo_root=repo_root)
    return _print_result(manifest_path, errors)


if __name__ == "__main__":
    raise SystemExit(main())
