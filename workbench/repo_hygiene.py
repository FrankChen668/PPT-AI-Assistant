from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HygieneIssue:
    code: str
    path: str
    message: str


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _meta_index_text(root: Path) -> str:
    path = root / "docs" / "meta-model" / "meta-index.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _current_project_reports(root: Path) -> list[Path]:
    reports_dir = root / "docs" / "reports"
    if not reports_dir.exists():
        return []
    return sorted(
        path
        for path in reports_dir.glob("*.md")
        if path.is_file() and "archive" not in path.parts
    )


def find_hygiene_issues(repo_root: Path) -> list[HygieneIssue]:
    root = Path(repo_root).resolve()
    issues: list[HygieneIssue] = []
    meta_index = _meta_index_text(root)

    for report in _current_project_reports(root):
        rel = _rel(report, root)
        if rel not in meta_index:
            issues.append(
                HygieneIssue(
                    code="unlinked-report",
                    path=rel,
                    message="Current project report is not linked from docs/meta-model/meta-index.md.",
                )
            )

    pending_dir = root / "workbench" / "tasks" / "pending"
    if pending_dir.exists():
        for item in sorted(pending_dir.glob("*.json")):
            issues.append(
                HygieneIssue(
                    code="pending-task-artifact",
                    path=_rel(item, root),
                    message="Pending workbench task artifact should be cleared or archived before review.",
                )
            )

    projects_dir = root / "my-ppt-skill" / "projects"
    if projects_dir.exists():
        for item in sorted(projects_dir.glob("codex-*-ppt-*")):
            if item.is_dir():
                issues.append(
                    HygieneIssue(
                        code="generated-project-artifact",
                        path=_rel(item, root),
                        message="Generated workbench project should stay ignored, cleared, or archived before review.",
                    )
                )

    core_templates = root / "my-ppt-skill" / "ppt-ai-core" / "templates"
    legacy_templates = root / "my-ppt-skill" / "templates" / "ppt-master"
    if core_templates.exists() and legacy_templates.exists():
        core_files = [path for path in core_templates.rglob("*") if path.is_file()]
        legacy_files = [path for path in legacy_templates.rglob("*") if path.is_file()]
        if len(legacy_files) > len(core_files):
            issues.append(
                HygieneIssue(
                    code="duplicate-asset-growth-trend",
                    path=_rel(legacy_templates, root),
                    message=(
                        "Legacy mirror has more files than core template authority; "
                        "check duplicate-asset growth trend."
                    ),
                )
            )

    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check lightweight repository hygiene for workbench reviews.")
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1], type=Path)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when hygiene issues are found.")
    args = parser.parse_args(argv)
    issues = find_hygiene_issues(args.root)
    if not issues:
        print("repo hygiene: ok")
        return 0
    for issue in issues:
        print(f"{issue.code}: {issue.path} - {issue.message}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
