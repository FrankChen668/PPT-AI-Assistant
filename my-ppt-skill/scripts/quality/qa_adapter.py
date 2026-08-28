#!/usr/bin/env python3
"""Workbench-facing QA adapter around scripts/qa_project.py."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from quality.report_io import load_report_markdown_excerpt

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SKILL_DIR = SCRIPTS_DIR.parent


@dataclass
class SlideQaRequest:
    project: str
    slide_id: int
    snapshots: bool = True


@dataclass
class SlideQaResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    report_path: str
    summary: str


def _first_meaningful_line(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if line:
            return line
    return ""


def _tail(text: str, limit: int = 12000) -> str:
    return text[-limit:] if len(text) > limit else text


def run_slide_qa(request: SlideQaRequest) -> SlideQaResult:
    if not request.project.strip():
        raise ValueError("project must be non-empty")
    if request.slide_id < 1:
        raise ValueError("slide_id must be >= 1")

    command = [
        sys.executable,
        "scripts/qa_project.py",
        f"projects/{request.project}",
    ]
    if request.snapshots:
        command.append("--snapshots")
    command.extend(["--slide", str(request.slide_id)])
    command.extend(["--svg-dir", "svg_output"])

    completed = subprocess.run(
        command,
        cwd=SKILL_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )

    stdout = _tail(completed.stdout)
    stderr = _tail(completed.stderr)
    project_dir = (SKILL_DIR / "projects" / request.project).resolve()
    report_path = (project_dir / "qa" / "report.md").resolve()
    report_excerpt = load_report_markdown_excerpt(project_dir, limit=2000)

    if completed.returncode == 0:
        summary = "单页 QA 通过"
    else:
        summary = _first_meaningful_line(stderr)
        if not summary:
            summary = _first_meaningful_line(report_excerpt)
        if not summary:
            summary = "单页 QA 失败"

    return SlideQaResult(
        ok=completed.returncode == 0,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        report_path=str(report_path),
        summary=summary,
    )
