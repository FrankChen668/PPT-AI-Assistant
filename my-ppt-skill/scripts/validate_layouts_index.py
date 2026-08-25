#!/usr/bin/env python3
"""Validate template layout index metadata and references."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_INDEX_PATH = (
    Path(__file__).resolve().parent.parent
    / "ppt-ai-core"
    / "templates"
    / "layouts"
    / "layouts_index.json"
)
DEFAULT_LAYOUTS_DIR = DEFAULT_INDEX_PATH.parent
DEFAULT_CANDIDATE_LAYOUTS_DIR = DEFAULT_LAYOUTS_DIR.parent / "layouts_candidate"
IGNORED_LAYOUT_DIRS = {"__pycache__"}
DEFAULT_DENSITY_PROFILES = {"low", "medium", "high"}
DEFAULT_LIFECYCLE_STATES = {"active", "candidate", "deprecated"}


@dataclass(frozen=True)
class LayoutIndexIssue:
    code: str
    path: str
    message: str


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _layout_dirs(layouts_dir: Path) -> set[str]:
    if not layouts_dir.exists():
        return set()
    return {
        item.name
        for item in layouts_dir.iterdir()
        if item.is_dir() and item.name not in IGNORED_LAYOUT_DIRS
    }


def _layout_candidate_dirs(layouts_candidate_dir: Path | None) -> set[str]:
    if layouts_candidate_dir is None or not layouts_candidate_dir.exists():
        return set()
    return _layout_dirs(layouts_candidate_dir)


def _float_range(value: Any, default: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        return default
    lower = value[0]
    upper = value[1]
    if not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
        return default
    lo = float(lower)
    hi = float(upper)
    if lo > hi:
        return default
    return lo, hi


def validate_layouts_index(
    index_path: Path,
    layouts_dir: Path,
    layouts_candidate_dir: Path | None = DEFAULT_CANDIDATE_LAYOUTS_DIR,
) -> list[LayoutIndexIssue]:
    issues: list[LayoutIndexIssue] = []
    if not index_path.exists():
        return [LayoutIndexIssue("missing-layout-index", str(index_path), "Layout index file is missing.")]
    if not layouts_dir.exists():
        return [LayoutIndexIssue("missing-layout-directory", str(layouts_dir), "Layouts directory is missing.")]

    try:
        payload = _load_json(index_path)
    except Exception as exc:
        return [LayoutIndexIssue("invalid-layout-index-json", str(index_path), f"Could not parse JSON: {exc}")]

    if not isinstance(payload, dict):
        return [LayoutIndexIssue("invalid-layout-index-root", str(index_path), "Layout index root must be an object.")]

    layouts = payload.get("layouts")
    if not isinstance(layouts, dict):
        return [
            LayoutIndexIssue(
                "missing-layouts-object",
                str(index_path),
                "Layout index must contain a layouts object.",
            )
        ]

    layout_ids = {str(key) for key in layouts}
    layout_dirs = _layout_dirs(layouts_dir)
    meta = payload.get("meta")
    meta_total = meta.get("total") if isinstance(meta, dict) else None
    if not isinstance(meta_total, int):
        issues.append(
            LayoutIndexIssue(
                "layout-index-missing-meta-total",
                str(index_path),
                "meta.total must be an integer.",
            )
        )
    elif meta_total != len(layout_ids) or meta_total != len(layout_dirs):
        issues.append(
            LayoutIndexIssue(
                "layout-index-total-mismatch",
                str(index_path),
                f"meta.total={meta_total}, layouts={len(layout_ids)}, directories={len(layout_dirs)}.",
            )
        )

    for layout_id in sorted(layout_ids - layout_dirs):
        issues.append(
            LayoutIndexIssue(
                "layout-index-missing-directory",
                str(index_path),
                f"Layout {layout_id!r} exists in layouts_index.json but has no matching directory.",
            )
        )
    for directory in sorted(layout_dirs - layout_ids):
        issues.append(
            LayoutIndexIssue(
                "layout-directory-missing-index",
                str(layouts_dir / directory),
                f"Layout directory {directory!r} is missing from layouts_index.json.",
            )
        )

    candidate_dirs = _layout_candidate_dirs(layouts_candidate_dir)
    for layout_id in sorted(layout_ids & candidate_dirs):
        issues.append(
            LayoutIndexIssue(
                "layout-candidate-index-leak",
                str(index_path),
                f"Layout {layout_id!r} appears in layouts_index.json but also exists in candidate directory.",
            )
        )

    category_refs: set[str] = set()
    categories = payload.get("categories")
    if isinstance(categories, dict):
        for category_name, category in categories.items():
            if not isinstance(category, dict):
                issues.append(
                    LayoutIndexIssue(
                        "layout-index-invalid-category",
                        str(index_path),
                        f"Category {category_name!r} must be an object.",
                    )
                )
                continue
            refs = category.get("layouts")
            if not isinstance(refs, list):
                issues.append(
                    LayoutIndexIssue(
                        "layout-index-invalid-category-layouts",
                        str(index_path),
                        f"Category {category_name!r} must define a layouts array.",
                    )
                )
                continue
            seen_category_refs: set[str] = set()
            for ref in refs:
                if not isinstance(ref, str):
                    issues.append(
                        LayoutIndexIssue(
                            "layout-index-category-nonstring",
                            str(index_path),
                            f"Category {category_name!r} contains a non-string layout reference.",
                        )
                    )
                    continue
                if ref in seen_category_refs:
                    issues.append(
                        LayoutIndexIssue(
                            "layout-index-category-duplicate",
                            str(index_path),
                            f"Category {category_name!r} references layout {ref!r} more than once.",
                        )
                    )
                seen_category_refs.add(ref)
                category_refs.add(ref)
                if ref not in layout_ids:
                    issues.append(
                        LayoutIndexIssue(
                            "layout-index-category-missing-layout",
                            str(index_path),
                            f"Category {category_name!r} references unknown layout {ref!r}.",
                        )
                    )

    for layout_id in sorted(layout_ids - category_refs):
        issues.append(
            LayoutIndexIssue(
                "layout-index-layout-missing-category",
                str(index_path),
                f"Layout {layout_id!r} does not belong to any category.",
            )
        )

    quick_lookup = payload.get("quickLookup")
    if isinstance(quick_lookup, dict):
        for lookup_name, refs in quick_lookup.items():
            if not isinstance(refs, list):
                issues.append(
                    LayoutIndexIssue(
                        "layout-index-invalid-quicklookup",
                        str(index_path),
                        f"quickLookup {lookup_name!r} must be an array.",
                    )
                )
                continue
            seen_lookup_refs: set[str] = set()
            for ref in refs:
                if not isinstance(ref, str):
                    issues.append(
                        LayoutIndexIssue(
                            "layout-index-quicklookup-nonstring",
                            str(index_path),
                            f"quickLookup {lookup_name!r} contains a non-string layout reference.",
                        )
                    )
                    continue
                if ref in seen_lookup_refs:
                    issues.append(
                        LayoutIndexIssue(
                            "layout-index-quicklookup-duplicate",
                            str(index_path),
                            f"quickLookup {lookup_name!r} references layout {ref!r} more than once.",
                        )
                    )
                seen_lookup_refs.add(ref)
                if ref not in layout_ids:
                    issues.append(
                        LayoutIndexIssue(
                            "layout-index-quicklookup-missing-layout",
                            str(index_path),
                            f"quickLookup {lookup_name!r} references unknown layout {ref!r}.",
                        )
                    )

    governance = payload.get("governance")
    if governance is not None and not isinstance(governance, dict):
        issues.append(
            LayoutIndexIssue(
                "layout-index-invalid-governance",
                str(index_path),
                "governance must be an object when provided.",
            )
        )
        return issues

    governance_obj = governance if isinstance(governance, dict) else {}
    schema_version = governance_obj.get("schemaVersion")
    if governance and not isinstance(schema_version, str):
        issues.append(
            LayoutIndexIssue(
                "layout-index-invalid-governance-schema-version",
                str(index_path),
                "governance.schemaVersion must be a string.",
            )
        )
    enforce_metadata = bool(governance_obj.get("enforceMetadata", False))
    allowed_density_raw = governance_obj.get("allowedDensityProfiles")
    allowed_density = (
        {str(item).strip().lower() for item in allowed_density_raw if str(item).strip()}
        if isinstance(allowed_density_raw, list)
        else set(DEFAULT_DENSITY_PROFILES)
    )
    if not allowed_density:
        allowed_density = set(DEFAULT_DENSITY_PROFILES)
    allowed_lifecycle_raw = governance_obj.get("allowedLifecycleStates")
    allowed_lifecycle = (
        {str(item).strip().lower() for item in allowed_lifecycle_raw if str(item).strip()}
        if isinstance(allowed_lifecycle_raw, list)
        else set(DEFAULT_LIFECYCLE_STATES)
    )
    if not allowed_lifecycle:
        allowed_lifecycle = set(DEFAULT_LIFECYCLE_STATES)
    quality_range = _float_range(governance_obj.get("qualityScoreRange"), (0.0, 1.0))
    ratio_range = _float_range(governance_obj.get("ratioRange"), (0.0, 1.0))

    template_meta = governance_obj.get("templates")
    if template_meta is not None and not isinstance(template_meta, dict):
        issues.append(
            LayoutIndexIssue(
                "layout-index-invalid-governance-templates",
                str(index_path),
                "governance.templates must be an object keyed by layout id.",
            )
        )
        template_meta = {}
    template_meta_obj = template_meta if isinstance(template_meta, dict) else {}

    if enforce_metadata:
        for layout_id in sorted(layout_ids - set(template_meta_obj)):
            issues.append(
                LayoutIndexIssue(
                    "layout-index-missing-governance-template",
                    str(index_path),
                    f"Layout {layout_id!r} is missing governance.templates metadata.",
                )
            )
        for layout_id in sorted(set(template_meta_obj) - layout_ids):
            issues.append(
                LayoutIndexIssue(
                    "layout-index-governance-unknown-template",
                    str(index_path),
                    f"governance.templates contains unknown layout {layout_id!r}.",
                )
            )

    for layout_id in sorted(layout_ids):
        meta = template_meta_obj.get(layout_id)
        if meta is None:
            continue
        if not isinstance(meta, dict):
            issues.append(
                LayoutIndexIssue(
                    "layout-index-governance-template-invalid",
                    str(index_path),
                    f"governance.templates[{layout_id!r}] must be an object.",
                )
            )
            continue

        scenario_tags = meta.get("scenarioTags")
        if enforce_metadata and (not isinstance(scenario_tags, list) or not scenario_tags):
            issues.append(
                LayoutIndexIssue(
                    "layout-index-governance-missing-scenario-tags",
                    str(index_path),
                    f"governance.templates[{layout_id!r}].scenarioTags must be a non-empty array.",
                )
            )

        density = str(meta.get("densityProfile", "")).strip().lower()
        if enforce_metadata and density not in allowed_density:
            issues.append(
                LayoutIndexIssue(
                    "layout-index-governance-invalid-density",
                    str(index_path),
                    f"governance.templates[{layout_id!r}].densityProfile={density!r} is not allowed.",
                )
            )

        canvas_profiles = meta.get("canvasProfiles")
        if enforce_metadata and (not isinstance(canvas_profiles, list) or not canvas_profiles):
            issues.append(
                LayoutIndexIssue(
                    "layout-index-governance-missing-canvas-profiles",
                    str(index_path),
                    f"governance.templates[{layout_id!r}].canvasProfiles must be a non-empty array.",
                )
            )

        quality_score = meta.get("qualityScore")
        if enforce_metadata:
            if not isinstance(quality_score, (int, float)):
                issues.append(
                    LayoutIndexIssue(
                        "layout-index-governance-invalid-quality-score",
                        str(index_path),
                        f"governance.templates[{layout_id!r}].qualityScore must be numeric.",
                    )
                )
            else:
                quality_value = float(quality_score)
                if quality_value < quality_range[0] or quality_value > quality_range[1]:
                    issues.append(
                        LayoutIndexIssue(
                            "layout-index-governance-quality-score-out-of-range",
                            str(index_path),
                            (
                                f"governance.templates[{layout_id!r}].qualityScore={quality_value} is outside "
                                f"{quality_range[0]}..{quality_range[1]}."
                            ),
                        )
                    )

        lifecycle = str(meta.get("lifecycle", "")).strip().lower()
        if enforce_metadata and lifecycle not in allowed_lifecycle:
            issues.append(
                LayoutIndexIssue(
                    "layout-index-governance-invalid-lifecycle",
                    str(index_path),
                    f"governance.templates[{layout_id!r}].lifecycle={lifecycle!r} is not allowed.",
                )
            )

        for field_name in ("adoptionRate30d", "failureRate30d"):
            value = meta.get(field_name)
            if value is None:
                if enforce_metadata:
                    issues.append(
                        LayoutIndexIssue(
                            "layout-index-governance-missing-ratio",
                            str(index_path),
                            f"governance.templates[{layout_id!r}] is missing {field_name}.",
                        )
                    )
                continue
            if not isinstance(value, (int, float)):
                issues.append(
                    LayoutIndexIssue(
                        "layout-index-governance-invalid-ratio",
                        str(index_path),
                        f"governance.templates[{layout_id!r}].{field_name} must be numeric.",
                    )
                )
                continue
            numeric = float(value)
            if numeric < ratio_range[0] or numeric > ratio_range[1]:
                issues.append(
                    LayoutIndexIssue(
                        "layout-index-governance-ratio-out-of-range",
                        str(index_path),
                        (
                            f"governance.templates[{layout_id!r}].{field_name}={numeric} is outside "
                            f"{ratio_range[0]}..{ratio_range[1]}."
                        ),
                    )
                )

    return issues


def _format_issues(issues: list[LayoutIndexIssue]) -> str:
    lines = ["Template layout index validation failed:"]
    for issue in issues:
        lines.append(f"- [{issue.code}] {issue.path}: {issue.message}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate template layouts_index.json against layout directories and references."
    )
    parser.add_argument("--index-path", type=Path, default=DEFAULT_INDEX_PATH, help="Path to layouts_index.json.")
    parser.add_argument(
        "--layouts-dir",
        type=Path,
        default=DEFAULT_LAYOUTS_DIR,
        help="Path to layout template directories.",
    )
    parser.add_argument(
        "--candidate-layouts-dir",
        type=Path,
        default=DEFAULT_CANDIDATE_LAYOUTS_DIR,
        help="Optional path to candidate template directories that must stay outside layouts_index.json.",
    )
    args = parser.parse_args(argv)

    issues = validate_layouts_index(args.index_path, args.layouts_dir, args.candidate_layouts_dir)
    if issues:
        print(_format_issues(issues), file=sys.stderr)
        return 1

    print("Template layout index validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
