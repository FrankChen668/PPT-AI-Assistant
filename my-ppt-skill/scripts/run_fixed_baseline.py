#!/usr/bin/env python3
"""Run fixed baseline projects with repeatable dev-fast/release-safe commands."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

Mode = Literal["dev-fast", "release-safe"]
RunMode = Literal["dev-fast", "release-safe", "both"]

FAILURE_CATEGORIES = (
    "preflight_missing_svg",
    "missing_state_artifact",
    "qa_blocking",
    "visual_review_required",
    "export_failure",
    "command_error",
    "unknown",
)

KEYWORD_LINES = (
    "error",
    "failed",
    "missing",
    "blocking",
    "visual",
    "export",
    "review required",
    "manual_review_required",
    "delivery_blocked",
    "traceback",
)


# Normalize suggestions to avoid mojibake in markdown reports.
SUGGESTION_BY_FAILURE = {
    "preflight_missing_svg": "Add a minimal slide SVG (single-slide first) so dev-fast preflight can pass.",
    "missing_state_artifact": (
        "Fill missing State 2.5 artifacts "
        "(style_route/art_direction/reference_pack/slide_visual_plan)."
    ),
    "qa_blocking": "Fix QA blocking findings first, then rerun the same mode.",
    "visual_review_required": "Enter deck-level visual repair loop and complete manual visual review.",
    "export_failure": "Run doctor_export first, then recover in authoring -> finalize order.",
    "command_error": "Check command args, environment dependencies, and script executability.",
    "unknown": "Keep key error snippets and refine classification rules after manual triage.",
}

SUMMARY_FIELD_DEFINITIONS = {
    "positive_delivery_pass_rate": "Pass rate for positive samples under release-safe mode (delivery capability).",
    "negative_guardrail_detection_rate": (
        "Detection rate for negative samples expected to fail (guardrail effectiveness)."
    ),
    "unexpected_pass": "Count of expected-fail runs that unexpectedly passed (missed guardrail risk).",
    "unexpected_fail": "Count of expected-pass runs that unexpectedly failed (delivery regression risk).",
}


@dataclass(slots=True)
class CompletedRun:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    command_error: str = ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixed baseline set and emit JSON/Markdown summaries.")
    parser.add_argument("--set", dest="set_path", default="", help="Path to fixed baseline set JSON.")
    parser.add_argument("--output-json", required=True, help="Result JSON output path.")
    parser.add_argument("--output-md", required=True, help="Markdown summary output path.")
    parser.add_argument("--mode", choices=("dev-fast", "release-safe", "both"), default="both")
    parser.add_argument("--slide", type=int, default=1, help="Slide id for dev-fast mode (default: 1).")
    return parser.parse_args(argv)


def _resolve_input_path(raw: str) -> Path:
    if not raw.strip():
        skill_dir = Path(__file__).resolve().parents[1]
        repo_root = skill_dir.parent
        default_path = repo_root / "docs" / "reports" / "fixed-baseline-set.json"
        return default_path
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def _resolve_output_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def load_set_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    projects = payload.get("projects")
    if not isinstance(projects, list) or not projects:
        raise ValueError("fixed baseline set must contain a non-empty 'projects' list.")
    for item in projects:
        if not isinstance(item, dict):
            raise ValueError("each project item must be an object.")
        project_name = str(item.get("project") or "").strip()
        if not project_name:
            raise ValueError("project item missing required field: project")
        role = str(item.get("baseline_role") or "").strip()
        modes = item.get("modes")
        if not isinstance(modes, list) or not modes:
            raise ValueError(f"project '{project_name}' missing required modes list.")
        normalized_modes = {str(mode).strip() for mode in modes}
        if not normalized_modes.issubset({"dev-fast", "release-safe"}):
            raise ValueError(f"project '{project_name}' has unsupported mode in modes list.")
        expected = item.get("expected")
        expected_map = expected if isinstance(expected, dict) else {}
        if role == "positive_baseline":
            release_expected = str(expected_map.get("release-safe") or "").strip().lower()
            if release_expected and release_expected != "pass":
                raise ValueError(
                    f"project '{project_name}' baseline_role=positive_baseline requires expected.release-safe=pass."
                )
            dev_expected = str(expected_map.get("dev-fast") or "").strip().lower()
            if dev_expected and dev_expected != "pass":
                raise ValueError(
                    f"project '{project_name}' baseline_role=positive_baseline requires expected.dev-fast=pass."
                )
    return payload


def classify_failure(exit_code: int, stdout: str, stderr: str, *, command_error: str = "") -> str:
    if command_error.strip():
        return "command_error"
    folded = "\n".join([stdout or "", stderr or ""]).lower()
    if (
        "missing-svg" in folded
        or ("preflight failed" in folded and "missing" in folded and "svg" in folded)
        or "preflight failed before layout/finalize" in folded
        or "preflight failed: errors=" in folded
    ):
        return "preflight_missing_svg"
    if (
        "requires required art direction artifacts" in folded
        or "missing required artifact" in folded
        or "missing: " in folded and any(
            token in folded
            for token in (
                "style_route.json",
                "art_direction.md",
                "reference_pack.json",
                "slide_visual_plan.json",
                "clarification_brief.json",
            )
        )
    ):
        return "missing_state_artifact"
    if "visual review required" in folded or "visual_delivery_ready=false" in folded:
        return "visual_review_required"
    if "qa failed" in folded or "blocking findings" in folded or "delivery_blocked" in folded:
        return "qa_blocking"
    if "export failed" in folded or "finalize failed" in folded or "doctor_export" in folded:
        return "export_failure"
    if exit_code != 0 and ("traceback" in folded or "exception" in folded):
        return "command_error"
    return "unknown"


def _pick_summary_lines(text: str, *, max_chars: int = 500) -> str:
    if not text.strip():
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    picked: list[str] = []
    for line in lines:
        lower = line.lower()
        if any(keyword in lower for keyword in KEYWORD_LINES):
            picked.append(line)
        if len(" | ".join(picked)) >= max_chars:
            break
    if not picked:
        picked = lines[-4:]
    summary = " | ".join(picked)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3] + "..."
    return summary


def _mode_sequence(mode: RunMode) -> list[Mode]:
    if mode == "both":
        return ["dev-fast", "release-safe"]
    return [mode]


def _run_command(command: list[str], *, cwd: Path) -> CompletedRun:
    started = perf_counter()
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
        elapsed = perf_counter() - started
        return CompletedRun(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_seconds=round(elapsed, 2),
        )
    except OSError as exc:
        elapsed = perf_counter() - started
        return CompletedRun(
            command=command,
            returncode=127,
            stdout="",
            stderr="",
            duration_seconds=round(elapsed, 2),
            command_error=str(exc),
        )


def build_command(py: str, *, mode: Mode, project: str, slide: int) -> list[str]:
    command = [py, "scripts/run_mode.py", mode, f"projects/{project}"]
    if mode == "dev-fast":
        command.extend(["--slide", str(slide)])
    return command


def run_fixed_baseline_set(
    config: dict[str, Any],
    *,
    mode: RunMode,
    slide: int,
    skill_dir: Path,
) -> list[dict[str, Any]]:
    py = sys.executable
    modes = _mode_sequence(mode)
    projects = config.get("projects") or []
    results: list[dict[str, Any]] = []
    for project_entry in projects:
        project_name = str(project_entry.get("project") or "").strip()
        role = str(project_entry.get("baseline_role") or "unknown").strip()
        expected = project_entry.get("expected")
        expected_map = expected if isinstance(expected, dict) else {}
        configured_modes_raw = project_entry.get("modes")
        configured_modes = {
            str(item).strip() for item in configured_modes_raw
        } if isinstance(configured_modes_raw, list) else {"dev-fast", "release-safe"}

        for run_mode in modes:
            if run_mode not in configured_modes:
                continue
            command = build_command(py, mode=run_mode, project=project_name, slide=slide)
            run = _run_command(command, cwd=skill_dir)
            status = "pass" if run.returncode == 0 else "fail"
            category = ""
            if status == "fail":
                category = classify_failure(
                    run.returncode,
                    run.stdout,
                    run.stderr,
                    command_error=run.command_error,
                )
            record = {
                "project": project_name,
                "mode": run_mode,
                "baseline_role": role,
                "expected": str(expected_map.get(run_mode) or ""),
                "status": status,
                "exit_code": run.returncode,
                "duration_seconds": run.duration_seconds,
                "command": " ".join(run.command),
                "stdout_summary": _pick_summary_lines(run.stdout),
                "stderr_summary": _pick_summary_lines(run.stderr),
                "failure_category": category,
                "command_error": run.command_error,
                "ran_at": datetime.now().isoformat(timespec="seconds"),
            }
            results.append(record)
    return results


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, dict[str, Any]] = {}
    failure_counter: Counter[str] = Counter()
    expected_summary: dict[str, Any] = {
        "known_total": 0,
        "matched": 0,
        "mismatched": 0,
        "unexpected_pass": 0,
        "unexpected_fail": 0,
    }
    by_role_mode: dict[str, dict[str, dict[str, Any]]] = {}

    for mode in ("dev-fast", "release-safe"):
        mode_rows = [item for item in results if item.get("mode") == mode]
        total = len(mode_rows)
        passed = sum(1 for row in mode_rows if row.get("status") == "pass")
        pass_rate = _safe_rate(passed, total)
        by_mode[mode] = {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate_percent": pass_rate,
        }

    for row in results:
        role = str(row.get("baseline_role") or "unknown")
        mode = str(row.get("mode") or "unknown")
        role_bucket = by_role_mode.setdefault(role, {})
        mode_bucket = role_bucket.setdefault(
            mode,
            {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "expected_known": 0,
                "expected_matched": 0,
                "expected_mismatched": 0,
                "pass_rate_percent": 0.0,
                "expected_match_rate_percent": 0.0,
            },
        )
        mode_bucket["total"] += 1
        if row.get("status") == "pass":
            mode_bucket["passed"] += 1
        else:
            mode_bucket["failed"] += 1

        expected = str(row.get("expected") or "").strip().lower()
        actual = str(row.get("status") or "").strip().lower()
        if expected in {"pass", "fail"}:
            expected_summary["known_total"] += 1
            mode_bucket["expected_known"] += 1
            if expected == actual:
                expected_summary["matched"] += 1
                mode_bucket["expected_matched"] += 1
            else:
                expected_summary["mismatched"] += 1
                mode_bucket["expected_mismatched"] += 1
                if expected == "fail" and actual == "pass":
                    expected_summary["unexpected_pass"] += 1
                elif expected == "pass" and actual == "fail":
                    expected_summary["unexpected_fail"] += 1

        if row.get("status") != "fail":
            continue
        category = str(row.get("failure_category") or "unknown")
        failure_counter[category] += 1

    for role_bucket in by_role_mode.values():
        for bucket in role_bucket.values():
            bucket["pass_rate_percent"] = _safe_rate(int(bucket["passed"]), int(bucket["total"]))
            bucket["expected_match_rate_percent"] = _safe_rate(
                int(bucket["expected_matched"]),
                int(bucket["expected_known"]),
            )

    positive_release_safe_rows = [
        row
        for row in results
        if str(row.get("baseline_role") or "") == "positive_baseline"
        and str(row.get("mode") or "") == "release-safe"
    ]
    positive_release_safe_total = len(positive_release_safe_rows)
    positive_release_safe_passed = sum(1 for row in positive_release_safe_rows if row.get("status") == "pass")

    negative_guardrail_rows = [
        row
        for row in results
        if str(row.get("baseline_role") or "") == "failure_regression"
        and str(row.get("expected") or "").strip().lower() == "fail"
    ]
    negative_guardrail_total = len(negative_guardrail_rows)
    negative_guardrail_detected = sum(1 for row in negative_guardrail_rows if row.get("status") == "fail")

    return {
        "total_runs": len(results),
        "by_mode": by_mode,
        "expected": {
            **expected_summary,
            "match_rate_percent": _safe_rate(expected_summary["matched"], expected_summary["known_total"]),
        },
        "by_role_mode": by_role_mode,
        "positive_delivery_pass_rate": {
            "scope": "positive_baseline + release-safe",
            "passed": positive_release_safe_passed,
            "total": positive_release_safe_total,
            "pass_rate_percent": _safe_rate(positive_release_safe_passed, positive_release_safe_total),
        },
        "negative_guardrail_detection_rate": {
            "scope": "failure_regression + expected=fail",
            "detected": negative_guardrail_detected,
            "total": negative_guardrail_total,
            "detection_rate_percent": _safe_rate(negative_guardrail_detected, negative_guardrail_total),
        },
        "failure_categories": dict(sorted(failure_counter.items())),
    }


def build_markdown_summary(
    *,
    set_path: Path,
    mode: RunMode,
    slide: int,
    results: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append(f"# Fixed Baseline Batch Summary ({datetime.now().strftime('%Y-%m-%d')})")
    lines.append("")
    lines.append(f"- Set: `{set_path}`")
    lines.append(f"- Mode: `{mode}`")
    lines.append(f"- Dev-fast slide: `{slide}`")
    lines.append(f"- Total runs: `{summary['total_runs']}`")
    lines.append("")
    lines.append("## Pass Rate")
    lines.append("")
    lines.append("| Mode | Passed | Failed | Total | Pass Rate |")
    lines.append("|---|---:|---:|---:|---:|")
    for item_mode in ("dev-fast", "release-safe"):
        block = summary["by_mode"].get(item_mode) or {}
        lines.append(
            f"| `{item_mode}` | {block.get('passed', 0)} | {block.get('failed', 0)} | "
            f"{block.get('total', 0)} | {block.get('pass_rate_percent', 0.0)}% |"
        )
    lines.append("")
    lines.append("## Expectation Alignment")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    expected = summary.get("expected") or {}
    lines.append(f"| expected known total | {expected.get('known_total', 0)} |")
    lines.append(f"| expected matched | {expected.get('matched', 0)} |")
    lines.append(f"| expected mismatched | {expected.get('mismatched', 0)} |")
    lines.append(f"| unexpected pass | {expected.get('unexpected_pass', 0)} |")
    lines.append(f"| unexpected fail | {expected.get('unexpected_fail', 0)} |")
    lines.append(f"| expected match rate | {expected.get('match_rate_percent', 0.0)}% |")
    lines.append("")
    lines.append("## Delivery vs Guardrail")
    lines.append("")
    lines.append("| Metric | Count | Rate | Scope |")
    lines.append("|---|---:|---:|---|")
    positive = summary.get("positive_delivery_pass_rate") or {}
    lines.append(
        f"| positive delivery pass | {positive.get('passed', 0)}/{positive.get('total', 0)} | "
        f"{positive.get('pass_rate_percent', 0.0)}% | {positive.get('scope', '')} |"
    )
    negative = summary.get("negative_guardrail_detection_rate") or {}
    lines.append(
        f"| negative guardrail detection | {negative.get('detected', 0)}/{negative.get('total', 0)} | "
        f"{negative.get('detection_rate_percent', 0.0)}% | {negative.get('scope', '')} |"
    )
    lines.append("")
    lines.append("## Metric Definitions")
    lines.append("")
    lines.append("| Field | Meaning |")
    lines.append("|---|---|")
    lines.append(
        f"| `positive_delivery_pass_rate` | {SUMMARY_FIELD_DEFINITIONS['positive_delivery_pass_rate']} |"
    )
    lines.append(
        f"| `negative_guardrail_detection_rate` | {SUMMARY_FIELD_DEFINITIONS['negative_guardrail_detection_rate']} |"
    )
    lines.append(f"| `unexpected_pass` | {SUMMARY_FIELD_DEFINITIONS['unexpected_pass']} |")
    lines.append(f"| `unexpected_fail` | {SUMMARY_FIELD_DEFINITIONS['unexpected_fail']} |")
    lines.append("")
    lines.append("## Role/Mode Breakdown")
    lines.append("")
    lines.append("| Role | Mode | Passed | Failed | Pass Rate | Expected Match |")
    lines.append("|---|---|---:|---:|---:|---:|")
    by_role_mode = summary.get("by_role_mode") or {}
    if by_role_mode:
        for role in sorted(by_role_mode):
            mode_block = by_role_mode.get(role) or {}
            for role_mode in sorted(mode_block):
                block = mode_block.get(role_mode) or {}
                lines.append(
                    f"| `{role}` | `{role_mode}` | {block.get('passed', 0)} | {block.get('failed', 0)} | "
                    f"{block.get('pass_rate_percent', 0.0)}% | {block.get('expected_match_rate_percent', 0.0)}% |"
                )
    else:
        lines.append("| `(none)` | - | 0 | 0 | 0% | 0% |")
    lines.append("")
    lines.append("## Failure Category")
    lines.append("")
    lines.append("| Category | Count | Suggested Next Step |")
    lines.append("|---|---:|---|")
    failures = summary.get("failure_categories") or {}
    if failures:
        for category, count in failures.items():
            suggestion = SUGGESTION_BY_FAILURE.get(category, SUGGESTION_BY_FAILURE["unknown"])
            lines.append(f"| `{category}` | {count} | {suggestion} |")
    else:
        lines.append("| `(none)` | 0 | N/A |")
    lines.append("")
    lines.append("## Per Project Result")
    lines.append("")
    lines.append("| Project | Role | Mode | Status | Exit | Failure Category | Error Snippet |")
    lines.append("|---|---|---|---|---:|---|---|")
    for row in results:
        snippet = row.get("stderr_summary") or row.get("stdout_summary") or row.get("command_error") or ""
        safe_snippet = str(snippet).replace("|", "\\|")
        lines.append(
            f"| `{row.get('project')}` | `{row.get('baseline_role')}` | `{row.get('mode')}` | "
            f"`{row.get('status')}` | {row.get('exit_code')} | "
            f"`{row.get('failure_category') or '-'}` | {safe_snippet} |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This summary stores only compact stdout/stderr snippets to keep reports readable.")
    lines.append("- Full command output remains in terminal execution history, not in this markdown report.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    set_path = _resolve_input_path(args.set_path)
    output_json = _resolve_output_path(args.output_json)
    output_md = _resolve_output_path(args.output_md)

    if not set_path.exists():
        print(f"error: set file not found: {set_path}")
        return 2

    config = load_set_config(set_path)
    skill_dir = Path(__file__).resolve().parents[1]
    results = run_fixed_baseline_set(
        config,
        mode=args.mode,
        slide=max(1, int(args.slide)),
        skill_dir=skill_dir,
    )
    summary = summarize_results(results)

    payload = {
        "set_name": str(config.get("set_name") or ""),
        "set_path": str(set_path),
        "mode": args.mode,
        "slide": max(1, int(args.slide)),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary_field_definitions": SUMMARY_FIELD_DEFINITIONS,
        "results": results,
        "summary": summary,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    markdown = build_markdown_summary(
        set_path=set_path,
        mode=args.mode,
        slide=max(1, int(args.slide)),
        results=results,
        summary=summary,
    )
    output_md.write_text(markdown, encoding="utf-8")

    print(f"wrote json: {output_json}")
    print(f"wrote markdown: {output_md}")
    print(
        "pass rates:",
        ", ".join(
            f"{item_mode}={summary['by_mode'][item_mode]['pass_rate_percent']}%"
            for item_mode in ("dev-fast", "release-safe")
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
