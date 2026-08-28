#!/usr/bin/env python3
"""Evaluate complex-page capability pack coverage and rubric score."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class CapabilityRule:
    name: str
    required_tags: list[str]
    required_weight: int
    readiness_weight: int
    mandatory: bool = True


@dataclass
class CapabilityResult:
    name: str
    mandatory: bool
    covered: bool
    coverage_score: int
    readiness_score: int
    matching_slide_ids: list[int]


RULES: list[CapabilityRule] = [
    CapabilityRule(
        name="dense_onepager",
        required_tags=["Grid-Four-Cards", "Two-Columns-Split", "Content-List-Left", "Content-List-Right"],
        required_weight=15,
        readiness_weight=10,
        mandatory=True,
    ),
    CapabilityRule(
        name="strategy_map",
        required_tags=["Strategy-Map"],
        required_weight=15,
        readiness_weight=10,
        mandatory=True,
    ),
    CapabilityRule(
        name="capability_mapping",
        required_tags=["Capability-Mapping"],
        required_weight=15,
        readiness_weight=10,
        mandatory=True,
    ),
    CapabilityRule(
        name="kpi_data_page",
        required_tags=["Chart-Bar", "Chart-Line", "Data-Three-KPIs", "Data-Single-KPI"],
        required_weight=5,
        readiness_weight=5,
        mandatory=False,
    ),
]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _slide_is_ready(slide: dict[str, Any]) -> bool:
    title = str(slide.get("title") or "").strip()
    content = slide.get("content")
    if not title or not isinstance(content, dict):
        return False
    non_empty_items = 0
    for value in content.values():
        if isinstance(value, str) and value.strip():
            non_empty_items += 1
        elif isinstance(value, list) and value:
            non_empty_items += 1
        elif isinstance(value, dict) and value:
            non_empty_items += 1
    return non_empty_items >= 2


def evaluate_project(project_dir: Path) -> dict[str, Any]:
    blueprint = project_dir / "blueprint.json"
    if not blueprint.exists():
        raise RuntimeError(f"Missing blueprint: {blueprint}")
    payload = _read_json(blueprint)
    slides = payload.get("slides")
    if not isinstance(slides, list):
        raise RuntimeError("Invalid blueprint slides payload.")

    results: list[CapabilityResult] = []
    for rule in RULES:
        required_tags = set(rule.required_tags)
        matched = [
            slide
            for slide in slides
            if isinstance(slide, dict) and str(slide.get("layout_tag") or "") in required_tags
        ]
        covered = bool(matched)
        ready = any(_slide_is_ready(slide) for slide in matched)
        matching_ids: list[int] = []
        for slide in matched:
            if not isinstance(slide, dict):
                continue
            slide_id = slide.get("id")
            if isinstance(slide_id, int):
                matching_ids.append(slide_id)
        results.append(
            CapabilityResult(
                name=rule.name,
                mandatory=rule.mandatory,
                covered=covered,
                coverage_score=rule.required_weight if covered else 0,
                readiness_score=rule.readiness_weight if ready else 0,
                matching_slide_ids=matching_ids,
            )
        )

    required_results = [item for item in results if item.mandatory]
    optional_results = [item for item in results if not item.mandatory]
    coverage_total = sum(item.coverage_score for item in required_results)
    readiness_total = sum(item.readiness_score for item in required_results)
    bonus_total = sum(item.coverage_score + item.readiness_score for item in optional_results)

    qa_report = project_dir / "qa" / "report.json"
    qa_score = 0
    qa_metrics: dict[str, Any] = {}
    if qa_report.exists():
        try:
            qa_payload = _read_json(qa_report)
            qa_errors = int(qa_payload.get("errors", 0))
            qa_warnings = int(qa_payload.get("warnings", 0))
            qa_score = 35 if qa_errors == 0 and qa_warnings == 0 else (20 if qa_errors == 0 else 0)
            layered_verdict = qa_payload.get("layered_verdict") if isinstance(qa_payload, dict) else None
            qa_metrics = {
                "errors": qa_errors,
                "warnings": qa_warnings,
                "advisories": int(qa_payload.get("advisories", 0)),
                "visual_score": qa_payload.get("visual_score"),
                "layered_verdict_present": isinstance(layered_verdict, dict),
                "delivery_blocked": (
                    bool((layered_verdict or {}).get("delivery_blocked"))
                    if isinstance(layered_verdict, dict)
                    else None
                ),
                "blocking_finding_count": (
                    int((layered_verdict or {}).get("blocking_finding_count", 0))
                    if isinstance(layered_verdict, dict)
                    else 0
                ),
            }
        except Exception:
            qa_metrics = {}

    repair_plan = project_dir / "qa" / "repair_plan.json"
    repair_plan_summary = {
        "present": False,
        "item_count": 0,
        "blocking_item_count": 0,
    }
    if repair_plan.exists():
        try:
            repair_payload = _read_json(repair_plan)
            items = repair_payload.get("items") if isinstance(repair_payload, dict) else []
            if isinstance(items, list):
                repair_plan_summary = {
                    "present": True,
                    "item_count": len(items),
                    "blocking_item_count": sum(
                        1
                        for item in items
                        if isinstance(item, dict) and bool(item.get("is_blocking"))
                    ),
                }
        except Exception:
            pass

    total = coverage_total + readiness_total + qa_score + bonus_total
    return {
        "project": str(project_dir),
        "rubric_total": total,
        "rubric_breakdown": {
            "coverage_total": coverage_total,
            "readiness_total": readiness_total,
            "qa_total": qa_score,
            "bonus_total": bonus_total,
            "required_covered_count": sum(1 for item in required_results if item.covered),
            "required_total": len(required_results),
        },
        "capabilities": [asdict(item) for item in results],
        "qa_metrics": qa_metrics,
        "repair_plan_summary": repair_plan_summary,
        "pass": total >= 70 and all(item.covered for item in required_results),
    }


def write_report(result: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Complex Page Capability Pack Report",
        "",
        f"- project: `{result['project']}`",
        f"- rubric_total: `{result['rubric_total']}`",
        f"- pass: `{result['pass']}`",
        "",
        "## Breakdown",
        "",
        f"- coverage_total: `{result['rubric_breakdown']['coverage_total']}`",
        f"- readiness_total: `{result['rubric_breakdown']['readiness_total']}`",
        f"- qa_total: `{result['rubric_breakdown']['qa_total']}`",
        f"- bonus_total: `{result['rubric_breakdown']['bonus_total']}`",
        (
            f"- required_covered: `{result['rubric_breakdown']['required_covered_count']}/"
            f"{result['rubric_breakdown']['required_total']}`"
        ),
        "",
        "## Capability Coverage",
        "",
    ]
    for item in result["capabilities"]:
        lines.append(
            (
                f"- {item['name']} (mandatory=`{item['mandatory']}`): "
                f"covered=`{item['covered']}` "
                f"coverage_score=`{item['coverage_score']}` "
                f"readiness_score=`{item['readiness_score']}` "
                f"slides=`{item['matching_slide_ids']}`"
            )
        )

    lines.extend(
        [
            "",
            "## QA Signals",
            "",
            f"- qa_metrics: `{result.get('qa_metrics', {})}`",
            f"- repair_plan_summary: `{result.get('repair_plan_summary', {})}`",
        ]
    )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(project_dir: Path) -> int:
    result = evaluate_project(project_dir)
    qa_dir = project_dir / "qa"
    out_json = qa_dir / "complex-page-pack-report.json"
    out_md = qa_dir / "complex-page-pack-report.md"
    write_report(result, out_json, out_md)
    print(f"Wrote {out_json}")
    print(f"Wrote {out_md}")
    if not result["pass"]:
        print("error: complex page capability pack rubric not met.", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate complex-page capability pack rubric.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    args = parser.parse_args(argv)
    return run(args.project_dir.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
