"""Repair suggestion and deterministic replacement helpers."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


def collect_repair_slide_ids(report: Any | None) -> list[int]:
    if report is None or not getattr(report, "repair_recommendation", None):
        return []
    ids: set[int] = set()
    for item in report.repair_recommendation:
        value = item.get("slide")
        if isinstance(value, int):
            ids.add(value)
    return sorted(ids)


def write_repair_round_note(
    project_dir: Path,
    round_index: int,
    report: Any,
    *,
    mode: str,
    replacement_source: str | None = None,
    replaced_slide_ids: list[int] | None = None,
) -> Path:
    qa_dir = project_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    path = qa_dir / f"repair_round_{round_index:02d}.md"
    lines = [
        f"# Repair Round {round_index}",
        "",
        f"Mode: {mode}",
        "",
    ]
    if replacement_source:
        lines.append(f"Replacement source: `{replacement_source}`")
        lines.append("")
    if replaced_slide_ids:
        lines.append(f"Replaced slides: {', '.join(str(item) for item in replaced_slide_ids)}")
        lines.append("")
    for item in report.repair_recommendation or []:
        slide = item.get("slide")
        lines.append(f"## Slide {slide}")
        for action in item.get("actions") or []:
            lines.append(f"- {action}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def apply_deterministic_repair(
    project_dir: Path,
    slide_ids: list[int],
    render_project: Callable[..., Any],
    *,
    source_dir_name: str = "__repair_tmp_svg_output",
) -> list[int]:
    if not slide_ids:
        return []
    render_project(project_dir, output_dir=source_dir_name, clean=True)
    tmp_dir = project_dir / source_dir_name
    svg_output = project_dir / "svg_output"
    svg_output.mkdir(parents=True, exist_ok=True)
    repaired: list[int] = []
    for slide_id in slide_ids:
        filename = f"slide_{slide_id:02d}.svg"
        source = tmp_dir / filename
        target = svg_output / filename
        if not source.exists():
            continue
        shutil.copy2(source, target)
        repaired.append(slide_id)
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return repaired


def append_repair_audit(
    project_dir: Path,
    *,
    round_index: int,
    requested_slide_ids: list[int],
    repaired_slide_ids: list[int],
    replacement_source: str,
) -> Path:
    qa_dir = project_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    audit_path = qa_dir / "repair_replacements.jsonl"
    payload = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "round_index": round_index,
        "requested_slide_ids": requested_slide_ids,
        "repaired_slide_ids": repaired_slide_ids,
        "replacement_source": replacement_source,
    }
    with audit_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return audit_path
