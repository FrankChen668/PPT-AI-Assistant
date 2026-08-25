#!/usr/bin/env python3
"""Lightweight visual diversity checks for slide_visual_plan.json."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VisualDiversityReport:
    checked_slides: int
    warnings: list[str]
    report_path: Path
    layout_exploration_enabled: bool
    candidate_count: int
    archetype_switch_count: int
    consecutive_repeat_count: int
    diversity_gate_result: str


def _load_plan(plan_path: Path) -> dict[str, Any]:
    if not plan_path.exists():
        raise FileNotFoundError(f"Missing slide visual plan: {plan_path}")
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"Invalid JSON file: {plan_path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid slide visual plan (object expected): {plan_path}")
    return payload


def _slide_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    slides = payload.get("slides")
    if not isinstance(slides, list):
        raise ValueError("slide_visual_plan.json must contain slides array.")
    rows: list[dict[str, Any]] = []
    for item in slides:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _consecutive_archetype_warnings(slides: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    run_archetype = ""
    run_start = 0
    run_len = 0
    for idx, slide in enumerate(slides, start=1):
        archetype = _as_text(slide.get("visual_archetype")).lower()
        if archetype == run_archetype:
            run_len += 1
            continue
        if run_len >= 3 and run_archetype:
            warnings.append(
                f"Slides {run_start}-{run_start + run_len - 1} reuse visual_archetype '{run_archetype}' continuously."
            )
        run_archetype = archetype
        run_start = idx
        run_len = 1
    if run_len >= 3 and run_archetype:
        warnings.append(
            f"Slides {run_start}-{run_start + run_len - 1} reuse visual_archetype '{run_archetype}' continuously."
        )
    return warnings


def _empty_variation_warning(slides: list[dict[str, Any]]) -> str | None:
    if not slides:
        return None
    empty_count = 0
    for slide in slides:
        if not _as_text(slide.get("variation_rule")):
            empty_count += 1
    ratio = empty_count / len(slides)
    if ratio > 0.35:
        return (
            f"{empty_count}/{len(slides)} slides have empty variation_rule "
            f"({ratio:.0%}); consider adding stronger per-slide variation constraints."
        )
    return None


def _card_grid_overuse_warning(slides: list[dict[str, Any]]) -> str | None:
    if len(slides) <= 1:
        return None
    card_grid_count = 0
    for slide in slides:
        layout_tag = _as_text(slide.get("layout_tag")).lower()
        archetype = _as_text(slide.get("visual_archetype")).lower()
        comp = _as_text(slide.get("composition_intent")).lower()
        text = " ".join([layout_tag, archetype, comp])
        if any(token in text for token in ("grid", "card", "list", "matrix")):
            card_grid_count += 1
    ratio = card_grid_count / len(slides)
    if ratio > 0.6:
        return (
            f"{card_grid_count}/{len(slides)} slides are card/grid/list dominant "
            f"({ratio:.0%}); add more archetype diversity."
        )
    return None


def _adjacent_repeat_warnings(slides: list[dict[str, Any]]) -> tuple[list[str], int]:
    warnings: list[str] = []
    repeats = 0
    previous = ""
    for idx, slide in enumerate(slides, start=1):
        archetype = _as_text(slide.get("selected_archetype") or slide.get("visual_archetype")).lower()
        if idx > 1 and archetype and archetype == previous:
            repeats += 1
            warnings.append(f"Slides {idx - 1}-{idx} use the same selected archetype '{archetype}'.")
        previous = archetype
    return warnings, repeats


def _candidate_selection_inactive_warning(slides: list[dict[str, Any]]) -> str | None:
    if not slides:
        return None
    with_candidates = [
        slide
        for slide in slides
        if isinstance(slide.get("candidate_archetypes"), list) and slide.get("candidate_archetypes")
    ]
    if len(with_candidates) < 2:
        return None
    selected_b = 0
    for slide in with_candidates:
        if _as_text(slide.get("selected_candidate_id")).upper() == "B":
            selected_b += 1
    if selected_b == 0:
        return (
            "Candidate selection seems inactive: no slide selected candidate B. "
            "Verify anti-repeat strategy is taking effect."
        )
    return None


def _switch_count(slides: list[dict[str, Any]]) -> int:
    selected = [_as_text(slide.get("selected_archetype") or slide.get("visual_archetype")) for slide in slides]
    selected = [item for item in selected if item]
    if len(selected) <= 1:
        return 0
    switches = 0
    previous = selected[0]
    for current in selected[1:]:
        if current != previous:
            switches += 1
        previous = current
    return switches


def check_visual_diversity(project_dir: Path) -> VisualDiversityReport:
    project_dir = project_dir.resolve()
    plan_path = project_dir / "slide_visual_plan.json"
    payload = _load_plan(plan_path)
    slides = _slide_rows(payload)

    warnings: list[str] = []
    warnings.extend(_consecutive_archetype_warnings(slides))
    adjacent_warnings, repeat_count = _adjacent_repeat_warnings(slides)
    warnings.extend(adjacent_warnings)
    empty_warn = _empty_variation_warning(slides)
    if empty_warn:
        warnings.append(empty_warn)
    card_warn = _card_grid_overuse_warning(slides)
    if card_warn:
        warnings.append(card_warn)
    candidate_warn = _candidate_selection_inactive_warning(slides)
    if candidate_warn:
        warnings.append(candidate_warn)

    plan_level = payload.get("layout_exploration") if isinstance(payload, dict) else None
    enabled = bool(plan_level.get("enabled", False)) if isinstance(plan_level, dict) else False
    candidate_count = 2
    if isinstance(plan_level, dict):
        try:
            candidate_count = int(plan_level.get("candidate_count", 2))
        except (TypeError, ValueError):
            candidate_count = 2
    switch_count = _switch_count(slides)
    gate_result = "pass" if not warnings else "warn"

    report_dir = project_dir / "qa"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "visual-diversity-report.json"
    report_payload = {
        "checked_slides": len(slides),
        "warnings": warnings,
        "layout_exploration_enabled": enabled,
        "candidate_count": candidate_count,
        "archetype_switch_count": switch_count,
        "consecutive_repeat_count": repeat_count,
        "diversity_gate_result": gate_result,
    }
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return VisualDiversityReport(
        checked_slides=len(slides),
        warnings=warnings,
        report_path=report_path,
        layout_exploration_enabled=enabled,
        candidate_count=candidate_count,
        archetype_switch_count=switch_count,
        consecutive_repeat_count=repeat_count,
        diversity_gate_result=gate_result,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check visual diversity from slide_visual_plan.json.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    args = parser.parse_args(argv)
    try:
        report = check_visual_diversity(args.project_dir)
    except Exception as exc:
        print(f"error: {exc}")
        return 1
    print(f"Visual diversity checked: slides={report.checked_slides}, warnings={len(report.warnings)}")
    print(report.report_path)
    for item in report.warnings:
        print(f"- warning: {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
