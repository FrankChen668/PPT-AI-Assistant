#!/usr/bin/env python3
"""Evaluate guardrail execution behavior across key agent scenarios."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import doctor_export
import run_mode

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent


@dataclass
class EvalCase:
    scenario: str
    passed: bool
    evidence: str


def _base_project(project_dir: Path) -> None:
    (project_dir / "art_direction.md").write_text("# Art Direction\n", encoding="utf-8")
    (project_dir / "reference_pack.json").write_text("{}\n", encoding="utf-8")
    (project_dir / "slide_visual_plan.json").write_text("{\"slides\":[]}\n", encoding="utf-8")
    (project_dir / "style_route.json").write_text("{\"requires_style_drafts\": false}\n", encoding="utf-8")
    (project_dir / "svg_output").mkdir(parents=True, exist_ok=True)
    (project_dir / "svg_output" / "slide_01.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><text x="80" y="120">ok</text></svg>',
        encoding="utf-8",
    )
    (project_dir / "blueprint.json").write_text(
        json.dumps({"slides": [{"id": 1, "title": "A", "layout_tag": "Cover-Center", "content": {"headline": "x"}}]}),
        encoding="utf-8",
    )
    (project_dir / "design_spec.md").write_text("# Design Spec\n", encoding="utf-8")


def run_eval() -> list[EvalCase]:
    results: list[EvalCase] = []

    # Scenario 1: Existing SVG should keep default finalize --skip-render contract in docs.
    runbook = (REPO_ROOT / "docs" / "export-runbook.md").read_text(encoding="utf-8")
    pass_1 = "--phase finalize --skip-render" in runbook
    results.append(EvalCase("existing-svg-default-export-path", pass_1, "docs/export-runbook.md"))

    # Scenario 2: Forbidden node should be detected by doctor.
    with tempfile.TemporaryDirectory(prefix="eval_forbidden_node_") as tmp:
        project = Path(tmp)
        _base_project(project)
        (project / "svg_output" / "slide_01.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject x="0" y="0" width="100" height="50"/></svg>',
            encoding="utf-8",
        )
        report = doctor_export.run_export_doctor(project, expected_cwd=Path.cwd(), check_output_lock=False)
        pass_2 = any(item.code == "forbidden-svg-node" for item in report.findings)
        results.append(EvalCase("forbidden-node-detected", pass_2, str(report.report_md)))

    # Scenario 3: Locked PPTX should fail doctor with lock guidance.
    with tempfile.TemporaryDirectory(prefix="eval_locked_pptx_") as tmp:
        project = Path(tmp)
        _base_project(project)
        (project / "exports").mkdir(parents=True, exist_ok=True)
        (project / "exports" / "output-native.pptx").write_bytes(b"dummy")
        with patch.object(doctor_export, "_is_output_locked", return_value=True):
            report = doctor_export.run_export_doctor(project, expected_cwd=Path.cwd(), check_output_lock=True)
        pass_3 = any(item.code == "locked-output-pptx" for item in report.findings)
        results.append(EvalCase("locked-pptx-detected", pass_3, str(report.report_md)))

    # Scenario 4: release-safe must fail fast without Art Direction artifacts.
    with tempfile.TemporaryDirectory(prefix="eval_release_safe_gate_") as tmp:
        project = Path(tmp)
        code = run_mode.main(["release-safe", str(project)])
        pass_4 = code == 1
        results.append(EvalCase("release-safe-art-direction-gate", pass_4, f"exit_code={code}"))

    # Scenario 5: dev-fast route should remain authoring-only (no finalize export command).
    with tempfile.TemporaryDirectory(prefix="eval_dev_fast_") as tmp:
        project = Path(tmp)
        _base_project(project)
        commands: list[list[str]] = []

        def fake_run(cmd: list[str]) -> int:
            commands.append(cmd)
            return 0

        with patch.object(run_mode, "_run", side_effect=fake_run):
            code = run_mode.main(["dev-fast", str(project), "--slide", "1"])
        cmd_text = "\n".join(" ".join(item) for item in commands)
        pass_5 = code == 0 and "--phase authoring" in cmd_text and "--phase finalize" not in cmd_text
        results.append(EvalCase("dev-fast-no-export", pass_5, cmd_text))

    return results


def write_report(results: list[EvalCase]) -> tuple[Path, Path]:
    reports_dir = REPO_ROOT / "docs" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    md_path = reports_dir / f"agent-execution-eval-{stamp}.md"
    json_path = reports_dir / f"agent-execution-eval-{stamp}.json"

    passed_count = sum(1 for item in results if item.passed)
    total_count = len(results)
    failed_count = total_count - passed_count

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "results": [asdict(item) for item in results],
        "summary": {
            "total": total_count,
            "passed": passed_count,
            "failed": failed_count,
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Agent Execution Evaluation",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- pass_rate: `{passed_count}/{total_count}`",
        "",
        "| scenario | passed | evidence |",
        "|---|---:|---|",
    ]
    for item in results:
        lines.append(f"| `{item.scenario}` | `{item.passed}` | `{item.evidence}` |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main() -> int:
    results = run_eval()
    md_path, json_path = write_report(results)
    print(md_path)
    print(json_path)
    failed = [item for item in results if not item.passed]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
