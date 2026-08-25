#!/usr/bin/env python3
"""Run the local/CI quality gate for the AI-PPT skill."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from create_ai_trends_demo import create_project as create_ai_trends_demo_project

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent
DEMO_PROJECT = ROOT / "projects" / "ai-trends-demo"


def run_step(label: str, args: list[str]) -> None:
    print(f"\n==> {label}", flush=True)
    print(" ".join(args), flush=True)
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Missing expected JSON report: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid JSON report root: {path}")
    return data


def require_clean_report(path: Path, label: str) -> None:
    report = load_json(path)
    errors = int(report.get("errors", 0))
    warnings = int(report.get("warnings", 0))
    if report.get("ok") is not True or errors != 0 or warnings != 0:
        raise RuntimeError(f"{label} is not clean: ok={report.get('ok')} errors={errors} warnings={warnings}")


def require_visual_metrics(path: Path, label: str) -> None:
    report = load_json(path)
    visual_score = report.get("visual_score")
    if not isinstance(visual_score, (int, float)):
        raise RuntimeError(f"{label} visual_score missing or invalid: {visual_score!r}")
    metrics = report.get("metrics", {})
    if not isinstance(metrics, dict):
        raise RuntimeError(f"{label} metrics payload is invalid")
    recommendation_count = metrics.get("repair_recommendation_count")
    if not isinstance(recommendation_count, int):
        raise RuntimeError(f"{label} repair_recommendation_count missing or invalid: {recommendation_count!r}")


def require_manifest_stage_metrics(path: Path, label: str) -> None:
    payload = load_json(path)
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise RuntimeError(f"{label} manifest records missing or invalid: {path}")
    record = records[-1]
    if not isinstance(record, dict):
        raise RuntimeError(f"{label} manifest last record is invalid: {path}")
    required_float_keys = (
        "stage_parse_sec",
        "stage_render_sec",
        "stage_finalize_sec",
        "stage_export_sec",
        "stage_qa_sec",
        "stage_total_sec",
    )
    for key in required_float_keys:
        value = record.get(key)
        if not isinstance(value, (int, float)):
            raise RuntimeError(f"{label} missing or invalid {key}: {value!r}")
    for key in ("stage_failure_code", "stage_failure_source"):
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"{label} missing or invalid {key}: {value!r}")


def repo_status() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git status failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout


def ensure_demo_svg_output(project_dir: Path = DEMO_PROJECT) -> None:
    if not project_dir.exists():
        create_ai_trends_demo_project(project_dir, render=True)
        return
    if (project_dir / "svg_output" / "slide_04.svg").exists():
        return
    run_step(
        "Generate ai-trends-demo SVG fixture",
        [sys.executable, "scripts/render_svg.py", str(project_dir), "--clean"],
    )


def prepare_demo_project(project_dir: Path) -> None:
    create_ai_trends_demo_project(project_dir, render=True)


def verify_artifacts(
    demo_project: Path,
    regression_project: Path,
    dashboard_html: Path,
    dashboard_json: Path,
    wrap_report_json: Path,
    wrap_report_md: Path,
) -> None:
    expected = [
        demo_project / "exports" / "output-native.pptx",
        demo_project / "qa" / "report.md",
        regression_project / "exports" / "layout-regression-native.pptx",
        regression_project / "qa" / "report.md",
        dashboard_html,
        dashboard_json,
        wrap_report_json,
        wrap_report_md,
    ]
    for path in expected:
        if not path.exists():
            raise RuntimeError(f"Missing expected quality gate artifact: {path}")

    require_clean_report(demo_project / "qa" / "report.json", "ai-trends-demo QA")
    require_clean_report(regression_project / "qa" / "report.json", "layout regression QA")
    require_manifest_stage_metrics(demo_project / "exports" / "manifest.json", "ai-trends-demo build")
    require_manifest_stage_metrics(regression_project / "exports" / "manifest.json", "layout regression build")


def main() -> int:
    try:
        before_status = repo_status()
        run_step("Unit and smoke tests", [sys.executable, "-m", "pytest", "-q"])
        run_step("Documentation quality checks", [sys.executable, "scripts/check_docs_quality.py"])
        run_step("Template layout index checks", [sys.executable, "scripts/validate_layouts_index.py"])
        with tempfile.TemporaryDirectory(prefix="quality_gate_") as tmp:
            sandbox = Path(tmp)
            demo_project = sandbox / "ai-trends-demo"
            prepare_demo_project(demo_project)
            regression_project = sandbox / "_layout_regression"
            dashboard_html = sandbox / "docs" / "visual-quality-trend-dashboard.html"
            dashboard_json = sandbox / "docs" / "visual-quality-trend-data.json"
            wrap_out_dir = sandbox / "qa"
            wrap_report_json = wrap_out_dir / "text-wrap-snapshot-report.json"
            wrap_report_md = wrap_out_dir / "text-wrap-snapshot-report.md"

            ensure_demo_svg_output(demo_project)
            run_step(
                "Generate visual trend dashboard",
                [
                    sys.executable,
                    "scripts/build_visual_trend_dashboard.py",
                    "--output-html",
                    str(dashboard_html),
                    "--output-json",
                    str(dashboard_json),
                ],
            )
            run_step(
                "SVG/PPTX wrap snapshot compare",
                [
                    sys.executable,
                    "scripts/compare_text_wrap_snapshots.py",
                    "--min-samples",
                    "10",
                    "--out-dir",
                    str(wrap_out_dir),
                ],
            )
            run_step(
                "UTF-8 check ai-trends-demo SVG",
                [sys.executable, "scripts/check_svg_encoding.py", str(demo_project)],
            )
            run_step(
                "Build ai-trends-demo from Executor SVG",
                [
                    sys.executable,
                    "scripts/build_project.py",
                    str(demo_project),
                    "--skip-render",
                    "--snapshots",
                ],
            )
            run_step("QA ai-trends-demo", [sys.executable, "scripts/qa_project.py", str(demo_project), "--snapshots"])
            require_clean_report(demo_project / "qa" / "report.json", "ai-trends-demo full QA")
            run_step(
                "QA ai-trends-demo slide 4",
                [sys.executable, "scripts/qa_project.py", str(demo_project), "--snapshots", "--slide", "4"],
            )
            require_clean_report(demo_project / "qa" / "report.json", "ai-trends-demo slide 4 QA")
            run_step(
                "QA ai-trends-demo visual baseline",
                [sys.executable, "scripts/qa_project.py", str(demo_project), "--enable-visual-qa"],
            )
            require_clean_report(demo_project / "qa" / "report.json", "ai-trends-demo visual QA")
            require_visual_metrics(demo_project / "qa" / "report.json", "ai-trends-demo visual QA")
            run_step(
                "Layout DSL regression",
                [sys.executable, "scripts/regress_layouts.py", "--project-dir", str(regression_project)],
            )
            require_clean_report(regression_project / "qa" / "report.json", "layout regression QA")
            verify_artifacts(
                demo_project,
                regression_project,
                dashboard_html,
                dashboard_json,
                wrap_report_json,
                wrap_report_md,
            )
        after_status = repo_status()
        if after_status != before_status:
            raise RuntimeError(
                "quality gate introduced repo-tracked changes; default verification must stay artifact-clean"
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr, flush=True)
        return 1

    print("\nQuality gate passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
