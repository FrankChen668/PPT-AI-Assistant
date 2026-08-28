#!/usr/bin/env python3
"""Export-naming utilities extracted from build_project.py.

Provides stable and semantic PPTX output file naming, plus output-plan
construction for multi-target (native+raster) exports.

Extraction ref: build_project.py candidate #1 — shallow monolith deepening.
"""

from __future__ import annotations

import re
from pathlib import Path


def sanitize_project_name(name: str) -> str:
    """Sanitize a project name for use in filenames.

    Replaces filesystem-unsafe characters with hyphens and whitespace with
    underscores.
    """
    value = re.sub(r"[\\/:*?\"<>|]+", "-", name.strip())
    value = re.sub(r"\s+", "_", value)
    return value or "project"


def stable_output_name(export_mode: str) -> str:
    """Return the stable (non-versioned) output filename for a given mode."""
    return "output-native.pptx" if export_mode == "native" else "output.pptx"


def semantic_output_name(project_name: str, export_mode: str, version: int, timestamp: str) -> str:
    """Return a human-readable, versioned output filename."""
    safe_name = sanitize_project_name(project_name)
    return f"{safe_name}--{export_mode}--v{version}--{timestamp}.pptx"


def next_semantic_version(exports_dir: Path, project_name: str, export_mode: str) -> int:
    """Scan exports/ and return the next semantic version number."""
    safe_name = sanitize_project_name(project_name)
    patt = re.compile(
        rf"^{re.escape(safe_name)}--{re.escape(export_mode)}--v(\d+)--\d{{8}}-\d{{4}}\.pptx$"
    )
    versions: list[int] = []
    for candidate in exports_dir.glob("*.pptx"):
        match = patt.match(candidate.name)
        if match:
            versions.append(int(match.group(1)))
    return (max(versions) + 1) if versions else 1


def build_output_plan(
    project_dir: Path,
    mode: str,
    artifact_name: str,
    timestamp: str,
) -> dict[str, list[Path]]:
    """Build a plan of output file paths for each export mode.

    Args:
        project_dir: Path to the project directory (used for exports/ subdir).
        mode: One of 'native', 'raster', or 'both'.
        artifact_name: One of 'stable', 'semantic', or 'both'.
        timestamp: Timestamp string for semantic naming.

    Returns:
        Mapping of export_mode -> list of target Paths.
    """
    exports_dir = project_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    export_modes: list[str] = []
    if mode in {"native", "both"}:
        export_modes.append("native")
    if mode in {"raster", "both"}:
        export_modes.append("raster")

    output_plan: dict[str, list[Path]] = {}
    for export_mode in export_modes:
        targets: list[Path] = []
        if artifact_name in {"stable", "both"}:
            targets.append(exports_dir / stable_output_name(export_mode))
        if artifact_name in {"semantic", "both"}:
            version = next_semantic_version(exports_dir, project_dir.name, export_mode)
            semantic_name = semantic_output_name(project_dir.name, export_mode, version, timestamp)
            targets.append(exports_dir / semantic_name)
        output_plan[export_mode] = targets
    return output_plan


def is_stable_target(target: Path, export_mode: str) -> bool:
    """Check whether *target* is the stable (non-versioned) name for *export_mode*."""
    return target.name == stable_output_name(export_mode)


def planned_semantic_target(targets: list[Path], export_mode: str) -> Path | None:
    """Return the first non-stable target from a list (i.e. the semantic one)."""
    stable_name = stable_output_name(export_mode)
    for candidate in targets:
        if candidate.name != stable_name:
            return candidate
    return None


def next_semantic_target(project_dir: Path, export_mode: str, timestamp: str, reserved: set[Path]) -> Path:
    """Find the next available semantic path, avoiding *reserved* paths and existing files."""
    exports_dir = project_dir / "exports"
    version = next_semantic_version(exports_dir, project_dir.name, export_mode)
    while True:
        candidate = exports_dir / semantic_output_name(project_dir.name, export_mode, version, timestamp)
        resolved = candidate.resolve()
        if resolved not in reserved and not candidate.exists():
            return candidate
        version += 1
