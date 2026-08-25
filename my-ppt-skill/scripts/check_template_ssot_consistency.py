#!/usr/bin/env python3
"""Validate template SSOT consistency between layouts_index and template_catalog.

Policy:
- layouts_index.json is authority for core template ids.
- template_catalog.json may include a small set of approved variant entries.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = ROOT / "ppt-ai-core" / "templates" / "layouts" / "layouts_index.json"
DEFAULT_CATALOG = ROOT / "templates" / "template_catalog.json"

ALLOWED_VARIANT_POLICIES: dict[str, dict[str, str]] = {
    # Variant source directories are advisory today; warning by default.
    "academic_defense_research_board": {"missing_source_path_severity": "warn"},
    "ai_ops_architecture_review": {"missing_source_path_severity": "warn"},
    "exhibit_investor_brief": {"missing_source_path_severity": "warn"},
    "google_product_update": {"missing_source_path_severity": "warn"},
    "government_blue_policy_brief": {"missing_source_path_severity": "warn"},
    "mckinsey_decision_memo": {"missing_source_path_severity": "warn"},
}


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def _catalog_entries(catalog_payload: dict) -> dict[str, dict]:
    raw = catalog_payload.get("templates")
    if not isinstance(raw, list):
        raise ValueError("template_catalog.json missing templates array")
    entries: dict[str, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = item.get("template_key")
        if not isinstance(key, str) or not key.strip():
            continue
        entries[key.strip()] = item
    return entries


def _catalog_duplicate_keys(catalog_payload: dict) -> list[str]:
    raw = catalog_payload.get("templates")
    if not isinstance(raw, list):
        raise ValueError("template_catalog.json missing templates array")
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = item.get("template_key")
        if not isinstance(key, str):
            continue
        normalized = key.strip()
        if not normalized:
            continue
        if normalized in seen:
            duplicates.add(normalized)
        seen.add(normalized)
    return sorted(duplicates)


def _severity_for_variant(key: str, field: str, default: str = "warn") -> str:
    policy = ALLOWED_VARIANT_POLICIES.get(key, {})
    if not isinstance(policy, dict):
        return default
    raw = policy.get(field)
    if raw in {"warn", "error", "ignore"}:
        return raw
    return default


@dataclass
class ConsistencyReport:
    core_count: int
    catalog_count: int
    missing_in_catalog: list[str] = field(default_factory=list)
    catalog_only_extras: list[str] = field(default_factory=list)
    disallowed_extras: list[str] = field(default_factory=list)
    duplicate_catalog_keys: list[str] = field(default_factory=list)
    core_source_mismatches: list[str] = field(default_factory=list)
    source_path_errors: list[str] = field(default_factory=list)
    source_path_warnings: list[str] = field(default_factory=list)
    stale_whitelist_entries: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(
            self.missing_in_catalog
            or self.disallowed_extras
            or self.duplicate_catalog_keys
            or self.core_source_mismatches
            or self.source_path_errors
        )


def build_report(index_path: Path, catalog_path: Path) -> ConsistencyReport:
    idx = _load_json(index_path)
    catalog = _load_json(catalog_path)

    duplicate_catalog_keys = _catalog_duplicate_keys(catalog)

    layouts = idx.get("layouts")
    if not isinstance(layouts, dict):
        raise ValueError("layouts_index.json missing layouts object")

    core_ids = {k for k, v in layouts.items() if isinstance(k, str) and isinstance(v, dict)}
    catalog_map = _catalog_entries(catalog)
    catalog_ids = set(catalog_map.keys())

    missing_in_catalog = sorted(core_ids - catalog_ids)
    extra_in_catalog = sorted(catalog_ids - core_ids)
    disallowed_extras = sorted(set(extra_in_catalog) - set(ALLOWED_VARIANT_POLICIES.keys()))
    stale_whitelist_entries = sorted(set(ALLOWED_VARIANT_POLICIES.keys()) - set(extra_in_catalog))

    core_source_mismatches: list[str] = []
    for key in sorted(core_ids):
        item = catalog_map.get(key)
        if not isinstance(item, dict):
            continue
        source_path = item.get("source_path")
        desired = f"ppt-ai-core/templates/layouts/{key}"
        if not isinstance(source_path, str) or source_path.strip() != desired:
            core_source_mismatches.append(f"{key}: expected source_path={desired}, got={source_path!r}")

    source_path_errors: list[str] = []
    source_path_warnings: list[str] = []
    for key, item in catalog_map.items():
        source_path = item.get("source_path")
        if not isinstance(source_path, str) or not source_path.strip():
            if key in ALLOWED_VARIANT_POLICIES:
                severity = _severity_for_variant(key, "missing_source_path_severity")
                if severity == "error":
                    source_path_errors.append(f"{key}: missing source_path (variant policy=error)")
                elif severity == "warn":
                    source_path_warnings.append(f"{key}: missing source_path (variant policy=warn)")
            else:
                source_path_errors.append(f"{key}: missing source_path")
            continue
        resolved = ROOT / source_path
        if not resolved.exists():
            if key in ALLOWED_VARIANT_POLICIES:
                severity = _severity_for_variant(key, "missing_source_path_severity")
                if severity == "error":
                    source_path_errors.append(f"{key}: variant source_path not found -> {source_path}")
                elif severity == "warn":
                    source_path_warnings.append(f"{key}: variant source_path not found -> {source_path}")
            else:
                source_path_errors.append(f"{key}: source_path not found -> {source_path}")

    return ConsistencyReport(
        core_count=len(core_ids),
        catalog_count=len(catalog_ids),
        missing_in_catalog=missing_in_catalog,
        catalog_only_extras=extra_in_catalog,
        disallowed_extras=disallowed_extras,
        duplicate_catalog_keys=duplicate_catalog_keys,
        core_source_mismatches=core_source_mismatches,
        source_path_errors=source_path_errors,
        source_path_warnings=source_path_warnings,
        stale_whitelist_entries=stale_whitelist_entries,
    )


def _emit_report(report: ConsistencyReport) -> None:
    print(f"core templates: {report.core_count}")
    print(f"catalog templates: {report.catalog_count}")
    print(f"missing in catalog: {len(report.missing_in_catalog)}")
    if report.missing_in_catalog:
        print("  - " + ", ".join(report.missing_in_catalog))
    print(f"catalog-only extras: {len(report.catalog_only_extras)}")
    if report.catalog_only_extras:
        print("  - " + ", ".join(report.catalog_only_extras))
    print(f"disallowed extras: {len(report.disallowed_extras)}")
    if report.disallowed_extras:
        print("  - " + ", ".join(report.disallowed_extras))
    print(f"duplicate catalog keys: {len(report.duplicate_catalog_keys)}")
    if report.duplicate_catalog_keys:
        print("  - " + ", ".join(report.duplicate_catalog_keys))
    print(f"core source mismatches: {len(report.core_source_mismatches)}")
    if report.core_source_mismatches:
        for issue in report.core_source_mismatches:
            print("  -", issue)
    print(f"source path issues: {len(report.source_path_errors)}")
    if report.source_path_errors:
        for issue in report.source_path_errors:
            print("  -", issue)
    print(f"source path warnings: {len(report.source_path_warnings)}")
    if report.source_path_warnings:
        for issue in report.source_path_warnings:
            print("  -", issue)
    print(f"stale whitelist entries: {len(report.stale_whitelist_entries)}")
    if report.stale_whitelist_entries:
        print("  - " + ", ".join(report.stale_whitelist_entries))


def _report_as_json(report: ConsistencyReport) -> dict[str, Any]:
    return {
        "core_templates": report.core_count,
        "catalog_templates": report.catalog_count,
        "missing_in_catalog": report.missing_in_catalog,
        "catalog_only_extras": report.catalog_only_extras,
        "disallowed_extras": report.disallowed_extras,
        "duplicate_catalog_keys": report.duplicate_catalog_keys,
        "core_source_mismatches": report.core_source_mismatches,
        "source_path_errors": report.source_path_errors,
        "source_path_warnings": report.source_path_warnings,
        "stale_whitelist_entries": report.stale_whitelist_entries,
        "status": "fail" if report.failed else "pass",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check template SSOT consistency.")
    parser.add_argument("--index-path", type=Path, default=DEFAULT_INDEX, help="Path to layouts_index.json.")
    parser.add_argument("--catalog-path", type=Path, default=DEFAULT_CATALOG, help="Path to template_catalog.json.")
    parser.add_argument(
        "--strict-variant-warnings",
        action="store_true",
        help="Fail when variant warning items are present.",
    )
    parser.add_argument("--json", action="store_true", help="Print report as JSON.")
    args = parser.parse_args(argv)

    report = build_report(args.index_path, args.catalog_path)
    if args.json:
        print(json.dumps(_report_as_json(report), ensure_ascii=False, indent=2))
    else:
        _emit_report(report)

    if report.failed:
        return 1
    if args.strict_variant_warnings and report.source_path_warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
