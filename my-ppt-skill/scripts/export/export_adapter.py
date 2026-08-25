#!/usr/bin/env python3
"""Workbench-facing export adapter around build_project finalize entrypoint."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SKILL_DIR = SCRIPTS_DIR.parent


@dataclass
class FinalizeRequest:
    project: str
    enable_layout_lint: bool = True
    enable_visual_qa: bool = True
    enable_preflight: bool = True
    strict: bool = True
    safe_area_profile: str = "presentation"
    snapshots: bool = True


@dataclass
class FinalizeResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    pptx_path: str
    manifest_path: str
    summary: str


def _tail(text: str, limit: int = 12000) -> str:
    return text[-limit:] if len(text) > limit else text


def _first_meaningful_line(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if line:
            return line
    return ""


def _resolve_pptx_from_manifest(project_dir: Path, manifest_path: Path) -> Path | None:
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        return None

    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        output_files = record.get("output_files")
        if not isinstance(output_files, list):
            continue
        for rel in output_files:
            if not isinstance(rel, str) or not rel.lower().endswith(".pptx"):
                continue
            candidate = (project_dir / rel.replace("\\", "/")).resolve()
            if candidate.exists():
                return candidate
    return None


def run_finalize(request: FinalizeRequest) -> FinalizeResult:
    if not request.project.strip():
        raise ValueError("project must be non-empty")

    command = [
        sys.executable,
        "scripts/build_project.py",
        f"projects/{request.project}",
        "--phase",
        "finalize",
        "--skip-render",
        "--auto-slide-plan",
        "--auto-slide-plan-overwrite",
        "--safe-area-profile",
        request.safe_area_profile,
    ]
    if request.enable_layout_lint:
        command.append("--enable-layout-lint")
    if request.enable_visual_qa:
        command.append("--enable-visual-qa")
    command.append("--preflight" if request.enable_preflight else "--no-preflight")
    if request.strict:
        command.append("--strict")
    if request.snapshots:
        command.append("--snapshots")

    completed = subprocess.run(
        command,
        cwd=SKILL_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )

    stdout = _tail(completed.stdout)
    stderr = _tail(completed.stderr)
    project_dir = (SKILL_DIR / "projects" / request.project).resolve()
    manifest_path = (project_dir / "exports" / "manifest.json").resolve()

    pptx_candidate = (project_dir / "exports" / "output-native.pptx").resolve()
    if not pptx_candidate.exists():
        from_manifest = _resolve_pptx_from_manifest(project_dir, manifest_path)
        if from_manifest is not None:
            pptx_candidate = from_manifest

    if completed.returncode == 0:
        summary = "导出完成"
    else:
        summary = _first_meaningful_line(stderr) or "导出失败"

    return FinalizeResult(
        ok=completed.returncode == 0,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        pptx_path=str(pptx_candidate) if pptx_candidate.exists() else "",
        manifest_path=str(manifest_path),
        summary=summary,
    )
