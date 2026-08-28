#!/usr/bin/env python3
"""Validate visual baseline contact-sheet evidence coverage."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent
DOC_PATTERN = "visual-quality-contact-sheet-baseline-*.md"
REQUIRED_MIN_ROWS = 5
VALID_GRADES = {"A", "B", "C", "D"}
REQUIRED_METADATA_KEYS = ("baseline_date", "generated_at", "git_sha", "profile", "scenario_count")
REQUIRED_SCENARIOS = {"doc-import", "single-page", "multi-page", "repair-loop", "release-safe"}
MAX_BASELINE_AGE_DAYS = 14
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


@dataclass(frozen=True)
class BaselineIssue:
    code: str
    row: str
    message: str


def _latest_baseline_doc() -> Path | None:
    candidates = sorted((REPO_ROOT / "docs").glob(DOC_PATTERN))
    if not candidates:
        return None
    return candidates[-1]


def _current_git_sha() -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip().lower()


def _parse_metadata(doc_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in doc_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.lower().startswith("## baseline samples"):
            break
        match = re.match(r"^-\s*([a-zA-Z0-9_]+)\s*:\s*(.+)$", line)
        if not match:
            continue
        key = match.group(1).strip()
        value = match.group(2).strip().strip("`")
        values[key] = value
    return values


def _parse_iso_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_int(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_fallback_shas(raw: str) -> tuple[set[str], bool]:
    text = raw.strip()
    if not text:
        return set(), False
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    values: list[str]
    if isinstance(parsed, list):
        values = [str(item).strip().lower() for item in parsed]
    else:
        values = [item.strip().lower() for item in re.split(r"[,\s]+", text) if item.strip()]
    allow_head = "head" in values
    return {item for item in values if SHA_RE.fullmatch(item)}, allow_head


def _parse_table_rows(doc_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    in_table = False
    expected_parts = 5
    for raw in doc_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        lowered = line.lower()
        if lowered.startswith("| # | project | grade | scenario | contact sheet |"):
            in_table = True
            expected_parts = 6
            continue
        if lowered.startswith("| # | project | grade | contact sheet |"):
            in_table = True
            expected_parts = 5
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            if rows:
                break
            continue
        if re.fullmatch(r"\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|", line) or re.fullmatch(
            r"\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|", line
        ):
            continue
        parts = [item.strip() for item in line.strip("|").split("|")]
        if len(parts) != expected_parts:
            continue
        if expected_parts == 6:
            rows.append(
                {
                    "index": parts[0],
                    "project": parts[1].strip("`"),
                    "grade": parts[2].strip("`").upper(),
                    "scenario": parts[3].strip("`").lower(),
                    "contact_sheet": parts[4].strip("`"),
                    "notes": parts[5],
                }
            )
        else:
            rows.append(
                {
                    "index": parts[0],
                    "project": parts[1].strip("`"),
                    "grade": parts[2].strip("`").upper(),
                    "scenario": "",
                    "contact_sheet": parts[3].strip("`"),
                    "notes": parts[4],
                }
            )
    return rows


def load_baseline_grade_map(doc_path: Path | None = None) -> dict[str, str]:
    path = doc_path or _latest_baseline_doc()
    if path is None or not path.exists():
        return {}
    grade_map: dict[str, str] = {}
    for row in _parse_table_rows(path):
        project = row["project"].strip()
        grade = row["grade"].strip().upper()
        if project and grade in VALID_GRADES:
            grade_map[project] = grade
    return grade_map


def baseline_grade_for_project(project_name: str, doc_path: Path | None = None) -> str | None:
    return load_baseline_grade_map(doc_path).get(project_name.strip())


def validate_visual_baseline(doc_path: Path | None = None) -> list[BaselineIssue]:
    path = doc_path or _latest_baseline_doc()
    if path is None:
        return [BaselineIssue("missing-baseline-doc", "-", "No visual baseline document found in docs/.")]
    if not path.exists():
        return [BaselineIssue("missing-baseline-doc", "-", f"Baseline document not found: {path}")]

    metadata = _parse_metadata(path)
    rows = _parse_table_rows(path)
    issues: list[BaselineIssue] = []
    for key in REQUIRED_METADATA_KEYS:
        if not metadata.get(key, "").strip():
            issues.append(
                BaselineIssue(
                    "missing-baseline-metadata",
                    "-",
                    f"Missing required metadata field: {key}.",
                )
            )

    baseline_date = _parse_date(metadata.get("baseline_date", ""))
    if metadata.get("baseline_date", "").strip() and baseline_date is None:
        issues.append(BaselineIssue("invalid-baseline-date", "-", "baseline_date must be ISO date (YYYY-MM-DD)."))
    elif baseline_date is not None:
        age_days = (datetime.now(timezone.utc).date() - baseline_date).days
        if age_days > MAX_BASELINE_AGE_DAYS:
            issues.append(
                BaselineIssue(
                    "stale-baseline-date",
                    "-",
                    f"baseline_date is stale ({age_days} days old); max allowed is {MAX_BASELINE_AGE_DAYS}.",
                )
            )

    generated_at = metadata.get("generated_at", "")
    if generated_at.strip() and _parse_iso_datetime(generated_at) is None:
        issues.append(BaselineIssue("invalid-generated-at", "-", "generated_at must be ISO datetime."))

    scenario_count = _parse_int(metadata.get("scenario_count", ""))
    if metadata.get("scenario_count", "").strip() and (scenario_count is None or scenario_count <= 0):
        issues.append(BaselineIssue("invalid-scenario-count", "-", "scenario_count must be a positive integer."))

    git_sha = metadata.get("git_sha", "").strip().lower()
    if git_sha and not SHA_RE.fullmatch(git_sha):
        issues.append(BaselineIssue("invalid-git-sha", "-", "git_sha must be 7-40 hex characters."))

    current_sha = _current_git_sha()
    if git_sha and current_sha and current_sha != git_sha:
        fallback, allow_head = _parse_fallback_shas(metadata.get("approved_fallback_git_shas", ""))
        current_short = current_sha[:7]
        if not allow_head and current_sha not in fallback and current_short not in fallback:
            issues.append(
                BaselineIssue(
                    "baseline-sha-mismatch",
                    "-",
                    (
                        f"baseline git_sha={git_sha} does not match current HEAD={current_sha}. "
                        "Add current SHA to approved_fallback_git_shas for explicit fallback approval."
                    ),
                )
            )

    if len(rows) < REQUIRED_MIN_ROWS:
        issues.append(
            BaselineIssue(
                "insufficient-baseline-rows",
                "-",
                f"Baseline rows={len(rows)}; require >= {REQUIRED_MIN_ROWS}.",
            )
        )

    scenarios_in_rows: set[str] = set()
    for row in rows:
        project = row["project"]
        grade = row["grade"]
        scenario = row.get("scenario", "").strip().lower()
        contact_sheet = row["contact_sheet"]
        if grade not in VALID_GRADES:
            issues.append(
                BaselineIssue(
                    "invalid-grade",
                    row["index"],
                    f"{project}: invalid grade {grade!r}; expected one of {sorted(VALID_GRADES)}.",
                )
            )

        if not scenario:
            issues.append(
                BaselineIssue(
                    "missing-scenario",
                    row["index"],
                    f"{project}: scenario is required for strong baseline validation.",
                )
            )
        else:
            scenarios_in_rows.add(scenario)

        if not contact_sheet:
            issues.append(
                BaselineIssue(
                    "missing-contact-sheet",
                    row["index"],
                    f"{project}: contact sheet path is required.",
                )
            )
            continue

        declared_sheet = (REPO_ROOT / contact_sheet).resolve()
        if not declared_sheet.is_relative_to(REPO_ROOT.resolve()):
            issues.append(
                BaselineIssue(
                    "contact-sheet-outside-repo",
                    row["index"],
                    f"{project}: contact sheet must stay inside repository: {declared_sheet}",
                )
            )
            continue
        if not declared_sheet.exists():
            issues.append(
                BaselineIssue(
                    "missing-contact-sheet",
                    row["index"],
                    f"{project}: declared contact sheet missing: {declared_sheet}",
                )
            )

    missing_scenarios = sorted(REQUIRED_SCENARIOS - scenarios_in_rows)
    if missing_scenarios:
        issues.append(
            BaselineIssue(
                "insufficient-scenario-coverage",
                "-",
                f"Missing required scenarios: {', '.join(missing_scenarios)}.",
            )
        )
    if scenario_count is not None and scenario_count != len(scenarios_in_rows):
        issues.append(
            BaselineIssue(
                "scenario-count-mismatch",
                "-",
                f"scenario_count={scenario_count}, but discovered {len(scenarios_in_rows)} unique scenarios in rows.",
            )
        )

    return issues


def _to_machine_payload(issues: list[BaselineIssue]) -> dict[str, Any]:
    codes = sorted({issue.code for issue in issues})
    return {
        "status": "fail" if issues else "pass",
        "issue_codes": codes,
        "issues": [asdict(item) for item in issues],
    }


def main() -> int:
    issues = validate_visual_baseline()
    if issues:
        print("Visual baseline check failed:", file=sys.stderr)
        for issue in issues:
            print(f"- [{issue.code}] row={issue.row}: {issue.message}", file=sys.stderr)
        payload = _to_machine_payload(issues)
        print(f"VISUAL_BASELINE_CODES={','.join(payload['issue_codes'])}", file=sys.stderr)
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 1
    print("Visual baseline check passed.")
    print(json.dumps(_to_machine_payload([]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
