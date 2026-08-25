#!/usr/bin/env python3
"""Template entrypoint health checks."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
AUTHORITY_INDEX = ROOT / "ppt-ai-core" / "templates" / "layouts" / "layouts_index.json"
LEGACY_MARKER = "templates/ppt-master"
POLICY_EFFECTIVE_DATE = "20260430"
CORE_TEMPLATE_ROOT = ROOT / "ppt-ai-core" / "templates"
LEGACY_TEMPLATE_ROOT = ROOT / "templates" / "ppt-master"

DOCS_TO_SCAN = [
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "AI-PPT-Architecture.md",
    ROOT / "SKILL.md",
    REPO_ROOT / "TECHNICAL_ROADMAP.md",
    ROOT / "templates" / "README.md",
    ROOT / "templates" / "ppt-master" / "README.md",
    ROOT / "templates" / "ppt-master" / "README-LEGACY.md",
]
RUNTIME_LEGACY_ALLOWLIST = {
    "scripts/check_template_entrypoints.py",
    "scripts/check_docs_quality.py",
    "scripts/import_pptmaster_assets.py",
    "scripts/ppt_master/project_manager.py",
}
LEGACY_MIRROR_ALLOWED_MISSING = {"README-LEGACY.md"}
LEGACY_MIRROR_ALLOWED_MISMATCH = {"layouts/layouts_index.json"}


@dataclass
class CheckResult:
    name: str
    status: str
    details: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check_authority_index() -> CheckResult:
    if not AUTHORITY_INDEX.is_file():
        return CheckResult(
            name="authority_index",
            status="fail",
            details=[
                f"Missing authority layouts index: {AUTHORITY_INDEX}",
                "Fix: restore my-ppt-skill/ppt-ai-core/templates/layouts/layouts_index.json",
            ],
        )
    try:
        payload = _load_json(AUTHORITY_INDEX)
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(
            name="authority_index",
            status="fail",
            details=[f"Authority index parse failed: {exc}"],
        )
    if not isinstance(payload, dict):
        return CheckResult(
            name="authority_index",
            status="fail",
            details=["Authority layouts_index.json must be a JSON object."],
        )
    layouts = payload.get("layouts")
    if not isinstance(layouts, dict):
        return CheckResult(
            name="authority_index",
            status="fail",
            details=["Authority layouts_index.json missing 'layouts' object."],
        )
    return CheckResult(
        name="authority_index",
        status="pass",
        details=[f"Authority index OK: {AUTHORITY_INDEX}"],
        data={"layout_count": len(layouts)},
    )


def check_template_governance() -> CheckResult:
    if not AUTHORITY_INDEX.is_file():
        return CheckResult(
            name="template_governance",
            status="fail",
            details=[f"Missing authority layouts index: {AUTHORITY_INDEX}"],
        )
    try:
        payload = _load_json(AUTHORITY_INDEX)
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(
            name="template_governance",
            status="fail",
            details=[f"Authority index parse failed: {exc}"],
        )

    if not isinstance(payload, dict):
        return CheckResult(
            name="template_governance",
            status="fail",
            details=["Authority layouts_index.json must be a JSON object."],
        )
    layouts = payload.get("layouts")
    if not isinstance(layouts, dict):
        return CheckResult(
            name="template_governance",
            status="fail",
            details=["Authority layouts_index.json missing 'layouts' object."],
        )

    governance = payload.get("governance")
    if not isinstance(governance, dict):
        return CheckResult(
            name="template_governance",
            status="warn",
            details=["No governance block found in layouts_index.json (legacy compatibility mode)."],
            data={"coverage_ratio": 0.0},
        )

    schema_version = governance.get("schemaVersion")
    if not isinstance(schema_version, str) or not schema_version.strip():
        return CheckResult(
            name="template_governance",
            status="fail",
            details=["governance.schemaVersion must be a non-empty string."],
        )

    templates = governance.get("templates")
    if not isinstance(templates, dict):
        return CheckResult(
            name="template_governance",
            status="fail",
            details=["governance.templates must be an object keyed by layout id."],
        )

    layout_ids = {str(key) for key in layouts}
    template_ids = {str(key) for key in templates}
    missing = sorted(layout_ids - template_ids)
    dangling = sorted(template_ids - layout_ids)
    coverage_ratio = len(template_ids & layout_ids) / max(1, len(layout_ids))
    enforce_metadata = bool(governance.get("enforceMetadata", False))

    status = "pass"
    details = [
        f"schemaVersion={schema_version}",
        f"metadata coverage={coverage_ratio:.2%} ({len(template_ids & layout_ids)}/{len(layout_ids)})",
    ]
    if missing:
        details.append(
            f"Missing governance metadata for layouts: {', '.join(missing[:5])}{' ...' if len(missing) > 5 else ''}"
        )
    if dangling:
        details.append(f"Unknown governance layout ids: {', '.join(dangling[:5])}{' ...' if len(dangling) > 5 else ''}")

    if enforce_metadata and (missing or dangling):
        status = "fail"
    elif missing or dangling:
        status = "warn"

    # Basic observability signal check
    ratios_missing = 0
    for layout_id in layout_ids:
        item = templates.get(layout_id)
        if not isinstance(item, dict):
            ratios_missing += 1
            continue
        if item.get("adoptionRate30d") is None or item.get("failureRate30d") is None:
            ratios_missing += 1
    if ratios_missing:
        details.append(f"Templates missing observability ratios: {ratios_missing}")
        if enforce_metadata:
            status = "fail"
        elif status == "pass":
            status = "warn"

    return CheckResult(
        name="template_governance",
        status=status,
        details=details,
        data={
            "schema_version": schema_version,
            "coverage_ratio": round(coverage_ratio, 4),
            "enforce_metadata": enforce_metadata,
            "missing_count": len(missing),
            "dangling_count": len(dangling),
            "missing_ratio_fields": ratios_missing,
        },
    )


def _project_date_token(project_dir: Path) -> str | None:
    match = re.search(r"(20\d{6})$", project_dir.name)
    return match.group(1) if match else None


def check_project_bindings() -> CheckResult:
    projects_dir = ROOT / "projects"
    if not projects_dir.is_dir():
        return CheckResult(
            name="project_bindings",
            status="pass",
            details=["No projects directory found; skipped binding scan."],
        )

    fail_hits: list[str] = []
    warn_hits: list[str] = []
    scanned = 0

    for binding_path in sorted(projects_dir.glob("*/template_binding.json")):
        scanned += 1
        try:
            binding = _load_json(binding_path)
        except (json.JSONDecodeError, OSError) as exc:
            warn_hits.append(f"{binding_path}: cannot parse JSON ({exc})")
            continue

        source_index = str(binding.get("source_index", ""))
        if LEGACY_MARKER not in source_index:
            continue

        project_date = _project_date_token(binding_path.parent)
        if project_date and project_date >= POLICY_EFFECTIVE_DATE:
            fail_hits.append(f"{binding_path.parent.name}: legacy source_index={source_index}")
        else:
            warn_hits.append(f"{binding_path.parent.name}: legacy source_index={source_index}")

    if fail_hits:
        return CheckResult(
            name="project_bindings",
            status="fail",
            details=["New-policy project(s) reference legacy template path:"] + [f"- {item}" for item in fail_hits],
            data={"scanned_bindings": scanned, "legacy_fail_projects": fail_hits, "legacy_warn_projects": warn_hits},
        )
    if warn_hits:
        return CheckResult(
            name="project_bindings",
            status="warn",
            details=["Historical project(s) reference legacy template path:"] + [f"- {item}" for item in warn_hits],
            data={"scanned_bindings": scanned, "legacy_warn_projects": warn_hits},
        )
    return CheckResult(
        name="project_bindings",
        status="pass",
        details=["No project binding uses legacy template source."],
        data={"scanned_bindings": scanned},
    )


def check_doc_mentions() -> CheckResult:
    warn_lines: list[str] = []
    for doc_path in DOCS_TO_SCAN:
        if not doc_path.is_file():
            continue
        lines = doc_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines, start=1):
            lower = line.lower()
            if LEGACY_MARKER not in lower:
                continue
            start = max(0, i - 3)
            end = min(len(lines), i + 1)
            context = "\n".join(lines[start:end]).lower()
            if any(token in context for token in ("legacy", "read-only", "只读", "兼容", "deprecated")):
                continue
            warn_lines.append(f"{doc_path}:{i}: {line.strip()}")

    if warn_lines:
        return CheckResult(
            name="docs_legacy_mentions",
            status="warn",
            details=["Potential ambiguous legacy-path mentions in docs:"] + [f"- {item}" for item in warn_lines],
            data={"warning_count": len(warn_lines)},
        )
    return CheckResult(
        name="docs_legacy_mentions",
        status="pass",
        details=["Legacy path mentions are explicitly marked as compatibility/read-only."],
    )


def _file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def check_legacy_mirror_drift() -> CheckResult:
    if not LEGACY_TEMPLATE_ROOT.is_dir() or not CORE_TEMPLATE_ROOT.is_dir():
        return CheckResult(
            name="legacy_mirror_drift",
            status="warn",
            details=["Legacy or core template directory is missing; mirror drift check skipped."],
        )
    missing_in_core: list[str] = []
    content_mismatch: list[str] = []
    compared = 0
    for legacy_file in sorted(path for path in LEGACY_TEMPLATE_ROOT.rglob("*") if path.is_file()):
        rel = legacy_file.relative_to(LEGACY_TEMPLATE_ROOT)
        core_file = CORE_TEMPLATE_ROOT / rel
        if not core_file.exists():
            missing_in_core.append(str(rel).replace("\\", "/"))
            continue
        compared += 1
        if _file_sha1(legacy_file) != _file_sha1(core_file):
            content_mismatch.append(str(rel).replace("\\", "/"))

    details = [f"Compared legacy mirror files: {compared}"]
    if missing_in_core:
        details.append(f"Files only in legacy mirror: {len(missing_in_core)}")
    if content_mismatch:
        details.append(f"Legacy/core content mismatch files: {len(content_mismatch)}")

    unexpected_missing = [item for item in missing_in_core if item not in LEGACY_MIRROR_ALLOWED_MISSING]
    unexpected_mismatch = [item for item in content_mismatch if item not in LEGACY_MIRROR_ALLOWED_MISMATCH]
    if unexpected_missing or unexpected_mismatch:
        details.extend([f"- {item}" for item in (missing_in_core[:5] + content_mismatch[:5])])
        return CheckResult(
            name="legacy_mirror_drift",
            status="fail",
            details=details,
            data={
                "missing_in_core": missing_in_core[:20],
                "content_mismatch": content_mismatch[:20],
                "unexpected_missing": unexpected_missing[:20],
                "unexpected_mismatch": unexpected_mismatch[:20],
            },
        )
    if missing_in_core or content_mismatch:
        details.append("Only allowlisted legacy compatibility differences were detected.")
        return CheckResult(
            name="legacy_mirror_drift",
            status="pass",
            details=details,
            data={
                "allowlisted_missing": [item for item in missing_in_core if item in LEGACY_MIRROR_ALLOWED_MISSING],
                "allowlisted_mismatch": [item for item in content_mismatch if item in LEGACY_MIRROR_ALLOWED_MISMATCH],
            },
        )
    return CheckResult(
        name="legacy_mirror_drift",
        status="pass",
        details=details + ["Legacy compatibility mirror is aligned with core templates."],
    )


def check_duplicate_asset_growth() -> CheckResult:
    if not LEGACY_TEMPLATE_ROOT.is_dir() or not CORE_TEMPLATE_ROOT.is_dir():
        return CheckResult(
            name="duplicate_asset_growth",
            status="warn",
            details=["Legacy or core template directory is missing; duplicate growth metrics skipped."],
        )

    core_files = [path for path in CORE_TEMPLATE_ROOT.rglob("*") if path.is_file()]
    legacy_files = [path for path in LEGACY_TEMPLATE_ROOT.rglob("*") if path.is_file()]
    core_count = len(core_files)
    legacy_count = len(legacy_files)
    core_bytes = sum(path.stat().st_size for path in core_files)
    legacy_bytes = sum(path.stat().st_size for path in legacy_files)
    status = "pass"
    details = [
        f"core files={core_count}, bytes={core_bytes}",
        f"legacy files={legacy_count}, bytes={legacy_bytes}",
    ]
    if legacy_count > core_count:
        status = "warn"
        details.append("Legacy compatibility mirror has more files than core authority; check growth trend.")
    if legacy_bytes > core_bytes:
        status = "warn"
        details.append("Legacy compatibility mirror uses more bytes than core authority; check growth trend.")

    return CheckResult(
        name="duplicate_asset_growth",
        status=status,
        details=details,
        data={
            "core_file_count": core_count,
            "legacy_file_count": legacy_count,
            "core_total_bytes": core_bytes,
            "legacy_total_bytes": legacy_bytes,
        },
    )


def check_no_runtime_legacy_reads() -> CheckResult:
    violations: list[str] = []
    for path in sorted((ROOT / "scripts").rglob("*.py")):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel in RUNTIME_LEGACY_ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "templates/ppt-master" in text:
            violations.append(rel)
    if violations:
        return CheckResult(
            name="no_runtime_legacy_reads",
            status="fail",
            details=[
                "Mainflow scripts must not read templates/ppt-master path directly.",
                *[f"- {item}" for item in violations[:10]],
            ],
            data={"violation_count": len(violations)},
        )
    return CheckResult(
        name="no_runtime_legacy_reads",
        status="pass",
        details=["No runtime script reads legacy template path directly."],
    )


def aggregate_status(results: list[CheckResult]) -> str:
    statuses = {r.status for r in results}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def to_exit_code(status: str) -> int:
    if status == "fail":
        return 2
    if status == "warn":
        return 1
    return 0


def main() -> int:
    checks = [
        check_authority_index(),
        check_template_governance(),
        check_project_bindings(),
        check_doc_mentions(),
        check_legacy_mirror_drift(),
        check_duplicate_asset_growth(),
        check_no_runtime_legacy_reads(),
    ]
    status = aggregate_status(checks)
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "checks": [
            {
                "name": c.name,
                "status": c.status,
                "details": c.details,
                "data": c.data,
            }
            for c in checks
        ],
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()
    print(f"[template-entrypoint-check] status={status}")
    for c in checks:
        print(f"- {c.name}: {c.status}")
        for detail in c.details:
            print(f"  {detail}")

    return to_exit_code(status)


if __name__ == "__main__":
    sys.exit(main())
