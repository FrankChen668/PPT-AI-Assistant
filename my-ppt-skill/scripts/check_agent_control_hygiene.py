#!/usr/bin/env python3
"""Ratchet agent-control document lifecycle without rewriting historical debt."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
AGENT_CONTROL_DIR = REPO_ROOT / "docs" / "agent-control"
LIFECYCLE_CUTOFF = date(2026, 8, 9)
PROCESS_PATTERNS = (
    "AI_CHANGE_SPEC-*.md",
    "STAGE_REVIEW-*.md",
    "COMPLETION-*.md",
)
ACTIVE_STATUSES = {"active", "approved", "in_progress", "ready_for_review"}


@dataclass(frozen=True)
class HygieneIssue:
    code: str
    path: str
    message: str


FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)
FIELD_RE = re.compile(r"^(?P<key>[A-Za-z0-9_-]+):\s*(?P<value>.*?)\s*$")


def read_frontmatter(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    result: dict[str, str] = {}
    for raw_line in match.group("body").splitlines():
        field = FIELD_RE.match(raw_line)
        if field:
            result[field.group("key")] = field.group("value").strip("\"'")
    return result


def parse_updated(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def iter_top_level_process_docs(agent_control_dir: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in PROCESS_PATTERNS:
        paths.update(agent_control_dir.glob(pattern))
    return sorted(path for path in paths if path.is_file())


def check_agent_control_lifecycle(
    agent_control_dir: Path = AGENT_CONTROL_DIR,
    cutoff: date = LIFECYCLE_CUTOFF,
) -> list[HygieneIssue]:
    issues: list[HygieneIssue] = []
    active_current: list[Path] = []

    for path in iter_top_level_process_docs(agent_control_dir):
        metadata = read_frontmatter(path)
        status = metadata.get("status", "").strip().lower()
        updated = parse_updated(metadata.get("updated"))

        # Ratchet only new/updated process docs. Historical debt before the cutoff
        # is intentionally not converted into a surprise all-repo migration.
        if updated is None or updated < cutoff:
            continue

        if status == "completed":
            issues.append(
                HygieneIssue(
                    "completed-process-doc-in-active-control",
                    str(path.relative_to(agent_control_dir.parent.parent)),
                    "Completed process records must move to docs/agent-control/archive/ before merge-ready.",
                )
            )

        if path.name.startswith("AI_CHANGE_SPEC-") and status in ACTIVE_STATUSES:
            active_current.append(path)

    if len(active_current) > 1:
        issues.append(
            HygieneIssue(
                "multiple-active-change-specs",
                "docs/agent-control",
                "At most one post-cutoff active AI_CHANGE_SPEC-* may live at the top level; "
                "split future work into backlog/research or archive completed records.",
            )
        )

    return issues


def main() -> int:
    issues = check_agent_control_lifecycle()
    if issues:
        print("Agent-control hygiene check failed:", file=sys.stderr)
        for issue in issues:
            print(f"- [{issue.code}] {issue.path}: {issue.message}", file=sys.stderr)
        return 1
    print("Agent-control hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
