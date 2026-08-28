#!/usr/bin/env python3
"""Generate reproducible environment-baseline verification evidence."""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import doctor_export

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


def _dependency_checks() -> list[CheckResult]:
    required = [
        ("python-pptx", "pptx"),
        ("cairosvg", "cairosvg"),
        ("Pillow", "PIL"),
        ("lxml", "lxml"),
        ("defusedxml", "defusedxml"),
    ]
    out: list[CheckResult] = []
    for display, module in required:
        ok = importlib.util.find_spec(module) is not None
        out.append(
            CheckResult(
                name=f"dependency:{display}",
                status="pass" if ok else "fail",
                detail=f"import {module}: {'ok' if ok else 'missing'}",
            )
        )
    return out


def _browser_checks() -> list[CheckResult]:
    candidates = [
        ("Edge", [shutil.which("msedge"), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]),
        ("Chrome", [shutil.which("chrome"), r"C:\Program Files\Google\Chrome\Application\chrome.exe"]),
    ]
    checks: list[CheckResult] = []
    for browser, paths in candidates:
        found = False
        detected = ""
        for path in paths:
            if not path:
                continue
            p = Path(path)
            if p.exists():
                found = True
                detected = str(p)
                break
        checks.append(
            CheckResult(
                name=f"browser:{browser}",
                status="pass" if found else "warning",
                detail=detected if found else "not detected",
            )
        )
    return checks


def run_environment_verification(project_dir: Path) -> dict[str, Any]:
    checks: list[CheckResult] = []
    py_ok = sys.version_info.major == 3 and sys.version_info.minor == 12
    checks.append(
        CheckResult(
            name="python-version",
            status="pass" if py_ok else "warning",
            detail=f"{platform.python_version()} (recommended: 3.12.x)",
        )
    )
    checks.extend(_dependency_checks())
    checks.extend(_browser_checks())

    doctor_report = doctor_export.run_export_doctor(
        project_dir.resolve(),
        expected_cwd=ROOT,
        check_output_lock=True,
    )
    checks.append(
        CheckResult(
            name="doctor-export",
            status="pass" if doctor_report.ok else "fail",
            detail=(
                f"errors={doctor_report.errors}, warnings={doctor_report.warnings}, "
                f"report={doctor_report.report_md}"
            ),
        )
    )

    failed = [item for item in checks if item.status == "fail"]
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_dir": str(project_dir.resolve()),
        "ok": len(failed) == 0,
        "checks": [asdict(item) for item in checks],
        "summary": {
            "total": len(checks),
            "pass": sum(1 for item in checks if item.status == "pass"),
            "warning": sum(1 for item in checks if item.status == "warning"),
            "fail": len(failed),
        },
    }
    return payload


def write_environment_report(payload: dict[str, Any]) -> tuple[Path, Path]:
    reports_dir = REPO_ROOT / "docs" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    md_path = reports_dir / f"environment-baseline-verification-{stamp}.md"
    json_path = reports_dir / f"environment-baseline-verification-{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Environment Baseline Verification",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- project_dir: `{payload['project_dir']}`",
        f"- status: `{'pass' if payload['ok'] else 'fail'}`",
        "",
        "| check | status | detail |",
        "|---|---|---|",
    ]
    for item in payload["checks"]:
        lines.append(f"| `{item['name']}` | `{item['status']}` | `{item['detail']}` |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify environment baseline and emit auditable report.")
    parser.add_argument(
        "project_dir",
        type=Path,
        nargs="?",
        default=ROOT / "projects" / "ai-trends-demo",
        help="Sample project used for doctor verification (default: projects/ai-trends-demo).",
    )
    args = parser.parse_args(argv)

    payload = run_environment_verification(args.project_dir)
    md_path, json_path = write_environment_report(payload)
    print(md_path)
    print(json_path)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
