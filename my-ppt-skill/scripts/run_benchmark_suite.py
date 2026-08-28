#!/usr/bin/env python3
"""Run repeatable benchmark scenarios and emit KPI/debt trend reports."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

TARGET_DEBT_CODES = ("E501", "I001", "F401", "F541")


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    args: list[str]


def parse_ruff_code_counts(output: str) -> dict[str, int]:
    counts = {code: 0 for code in TARGET_DEBT_CODES}
    for line in output.splitlines():
        match = re.match(r"^([A-Z]\d{3})\b", line.strip())
        if not match:
            continue
        code = match.group(1)
        if code in counts:
            counts[code] += 1
    return counts


def evaluate_thresholds(scenario_result: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    name = str(scenario_result.get("name", ""))
    metrics = scenario_result.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    profile = thresholds.get(name, {})
    if not isinstance(profile, dict):
        profile = {}

    violations: list[str] = []
    return_code = scenario_result.get("return_code")
    if isinstance(return_code, int) and return_code != 0:
        violations.append(f"scenario_return_code={return_code}")

    mapping = [
        ("build_duration_sec", "build_duration_sec_max"),
        ("context_token_estimate", "context_token_estimate_max"),
        ("layout_quality_warning_count", "layout_quality_warning_count_max"),
        ("visual_diversity_warning_count", "visual_diversity_warning_count_max"),
    ]
    for metric_key, threshold_key in mapping:
        if threshold_key not in profile:
            continue
        if metric_key not in metrics:
            violations.append(f"missing_metric:{metric_key}")
            continue
        try:
            value = float(metrics[metric_key])
            limit = float(profile[threshold_key])
        except (TypeError, ValueError):
            violations.append(f"invalid_metric:{metric_key}")
            continue
        if value > limit:
            violations.append(f"{metric_key}={value} > {limit}")

    return {"pass": len(violations) == 0, "violations": violations}


def _run_command(command: list[str], *, cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, output


def _load_blueprint_slide_count(project_dir: Path) -> int:
    path = project_dir / "blueprint.json"
    if not path.exists():
        return 1
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return 1
    slides = payload.get("slides") if isinstance(payload, dict) else None
    if not isinstance(slides, list):
        return 1
    return max(1, len([item for item in slides if isinstance(item, dict)]))


def _resolve_changed_slides(project_dir: Path, max_count: int) -> list[int]:
    slide_count = _load_blueprint_slide_count(project_dir)
    upper = max(1, min(max_count, slide_count))
    return list(range(1, upper + 1))


def _manifest_last_record(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "exports" / "manifest.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        return {}
    tail = records[-1]
    return tail if isinstance(tail, dict) else {}


def _scenario_metrics(record: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "build_duration_sec",
        "context_token_estimate",
        "token_budget_limit",
        "token_budget_overflow",
        "page_summary_cache_hit_ratio",
        "checkpoint_count",
        "checkpoint_pages_per_chunk",
        "checkpoint_bytes",
        "template_lazy_load_hit_ratio",
        "template_reference_files_loaded",
        "template_reference_files_skipped",
        "layout_quality_warning_count",
        "visual_diversity_warning_count",
        "qa_visual_diversity_warning_count",
        "qa_errors",
        "qa_warnings",
    ]
    metrics = {key: record.get(key) for key in keys if key in record}
    if "visual_diversity_warning_count" not in metrics and "qa_visual_diversity_warning_count" in metrics:
        metrics["visual_diversity_warning_count"] = metrics["qa_visual_diversity_warning_count"]
    return metrics


def _default_thresholds() -> dict[str, Any]:
    return {
        "single_page_iter": {
            "build_duration_sec_max": 30.0,
            "context_token_estimate_max": 2500,
            "layout_quality_warning_count_max": 5,
        },
        "five_page_iter": {
            "build_duration_sec_max": 60.0,
            "context_token_estimate_max": 4500,
            "layout_quality_warning_count_max": 15,
        },
        "finalize_full": {
            "build_duration_sec_max": 180.0,
            "context_token_estimate_max": 8000,
            "visual_diversity_warning_count_max": 8,
        },
    }


def run_benchmark_suite(
    project_dir: Path,
    *,
    output_dir: Path,
    thresholds_path: Path | None = None,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    scripts_dir = Path(__file__).resolve().parent
    my_ppt_skill_dir = scripts_dir.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    thresholds = _default_thresholds()
    if thresholds_path is not None and thresholds_path.exists():
        try:
            loaded = json.loads(thresholds_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                thresholds.update(loaded)
        except Exception:
            pass

    changed_one = _resolve_changed_slides(project_dir, 1)
    changed_five = _resolve_changed_slides(project_dir, 5)
    one_flags = [flag for slide in changed_one for flag in ("--changed-slide", str(slide))]
    five_flags = [flag for slide in changed_five for flag in ("--changed-slide", str(slide))]

    scenarios = [
        Scenario(
            name="single_page_iter",
            description="Authoring incremental path with one changed slide.",
            args=[
                "python",
                "scripts/build_project.py",
                str(project_dir),
                "--phase",
                "authoring",
                "--skip-render",
                "--skip-qa",
                "--incremental",
                "--no-preflight",
                "--no-enforce-copyfit-contract",
                "--no-native-text-verify",
                *one_flags,
            ],
        ),
        Scenario(
            name="five_page_iter",
            description="Authoring incremental path with five-slide batch edit.",
            args=[
                "python",
                "scripts/build_project.py",
                str(project_dir),
                "--phase",
                "authoring",
                "--skip-render",
                "--skip-qa",
                "--incremental",
                "--no-preflight",
                "--no-enforce-copyfit-contract",
                "--no-native-text-verify",
                *five_flags,
            ],
        ),
        Scenario(
            name="finalize_full",
            description="Finalize path with QA enabled for delivery-level KPI capture.",
            args=[
                "python",
                "scripts/build_project.py",
                str(project_dir),
                "--phase",
                "finalize",
                "--skip-render",
                "--incremental",
                "--no-preflight",
                "--no-enforce-copyfit-contract",
                "--no-native-text-verify",
                "--enable-visual-qa",
            ],
        ),
    ]

    scenario_results: list[dict[str, Any]] = []
    for scenario in scenarios:
        code, output = _run_command(scenario.args, cwd=my_ppt_skill_dir)
        record = _manifest_last_record(project_dir)
        result = {
            "name": scenario.name,
            "description": scenario.description,
            "return_code": code,
            "metrics": _scenario_metrics(record),
            "build_timestamp": record.get("timestamp") if isinstance(record, dict) else None,
            "ok": code == 0,
        }
        result["threshold_eval"] = evaluate_thresholds(result, thresholds)
        if code != 0:
            result["error_excerpt"] = "\n".join(output.splitlines()[-20:])
        scenario_results.append(result)

    ruff_code, ruff_output = _run_command(["python", "-m", "ruff", "check", "."], cwd=my_ppt_skill_dir)
    debt_code_counts = parse_ruff_code_counts(ruff_output)

    mypy_code, mypy_output = _run_command(["python", "-m", "mypy", "scripts"], cwd=my_ppt_skill_dir)
    mypy_total: int | None = None
    match = re.search(r"Found\s+(\d+)\s+error", mypy_output)
    if match:
        mypy_total = int(match.group(1))
    elif "Success: no issues found" in mypy_output:
        mypy_total = 0

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_dir": str(project_dir),
        "scenarios": scenario_results,
        "thresholds": thresholds,
        "debt_trend": {
            "ruff_return_code": ruff_code,
            "ruff_target_code_counts": debt_code_counts,
            "mypy_return_code": mypy_code,
            "mypy_scripts_errors": mypy_total,
        },
    }

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"benchmark-{project_dir.name}-{stamp}.json"
    md_path = output_dir / f"benchmark-{project_dir.name}-{stamp}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# Benchmark Report - {project_dir.name}",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Project: `{project_dir}`",
        "",
        "## Scenario Results",
        "",
    ]
    for item in scenario_results:
        eval_result = item.get("threshold_eval", {})
        passed = bool(eval_result.get("pass"))
        lines.append(f"### {item['name']}")
        lines.append(f"- Return code: `{item['return_code']}`")
        lines.append(f"- Threshold pass: `{passed}`")
        metrics = item.get("metrics", {})
        if isinstance(metrics, dict):
            lines.append(f"- Metrics: `{json.dumps(metrics, ensure_ascii=False)}`")
        violations = eval_result.get("violations", [])
        if isinstance(violations, list) and violations:
            lines.append(f"- Violations: `{'; '.join(str(v) for v in violations)}`")
        lines.append("")

    lines.extend(
        [
            "## Debt Trend (Advisory)",
            "",
            f"- Ruff target codes: `{json.dumps(debt_code_counts, ensure_ascii=False)}`",
            f"- Mypy scripts errors: `{mypy_total}`",
            "",
            "## Notes",
            "",
            "- `quality_gate.py full` remains advisory in this cycle.",
            "- This report is intended for bi-weekly trend review and KPI closure.",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")

    summary["report_json"] = str(json_path)
    summary["report_md"] = str(md_path)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run benchmark scenarios and emit KPI/debt trend report.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "reports",
        help="Directory for benchmark report outputs.",
    )
    parser.add_argument("--thresholds", type=Path, help="Optional JSON file to override threshold defaults.")
    args = parser.parse_args(argv)

    result = run_benchmark_suite(
        args.project_dir,
        output_dir=args.output_dir.resolve(),
        thresholds_path=args.thresholds.resolve() if args.thresholds else None,
    )
    print(result["report_json"])
    print(result["report_md"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
