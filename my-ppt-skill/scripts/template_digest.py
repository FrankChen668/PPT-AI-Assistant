#!/usr/bin/env python3
"""Generate compact template digests from the authority layouts index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = ROOT / "ppt-ai-core" / "templates" / "layouts" / "layouts_index.json"
DEFAULT_OUTPUT = ROOT / "ppt-ai-core" / "templates" / "layouts" / "template_digest.json"


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _list_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _template_governance(index_payload: dict[str, Any], layout_id: str) -> dict[str, Any]:
    governance = index_payload.get("governance")
    templates = governance.get("templates") if isinstance(governance, dict) else None
    raw = templates.get(layout_id) if isinstance(templates, dict) else {}
    if not isinstance(raw, dict):
        raw = {}

    density = _text(raw.get("densityProfile")) or "medium"
    lifecycle = _text(raw.get("lifecycle")) or "active"
    return {
        "scenario_tags": _list_text(raw.get("scenarioTags")),
        "density_profile": density,
        "canvas_profiles": _list_text(raw.get("canvasProfiles")) or ["ppt169"],
        "quality_score": _number(raw.get("qualityScore"), 0.0),
        "adoption_rate_30d": _number(raw.get("adoptionRate30d"), 0.0),
        "failure_rate_30d": _number(raw.get("failureRate30d"), 0.0),
        "lifecycle": lifecycle,
        "last_reviewed": _text(raw.get("lastReviewed")),
        "retire_signal": _text(raw.get("retireSignal")),
    }


def build_digest(index_path: Path = DEFAULT_INDEX) -> dict[str, Any]:
    data = json.loads(index_path.read_text(encoding="utf-8-sig"))
    layouts = data.get("layouts")
    if not isinstance(layouts, dict):
        raise ValueError("layouts_index.json must contain a layouts object.")

    governance = data.get("governance")
    schema_version = governance.get("schemaVersion") if isinstance(governance, dict) else None
    digest: dict[str, Any] = {
        "source": str(index_path.as_posix()),
        "count": len(layouts),
        "governance_schema_version": _text(schema_version) or "legacy",
        "templates": [],
    }
    templates: list[dict[str, Any]] = []
    lifecycle_counts: dict[str, int] = {}
    quality_sum = 0.0
    failure_sum = 0.0
    coverage = 0
    for layout_id, detail in sorted(layouts.items()):
        if not isinstance(layout_id, str):
            continue
        if not isinstance(detail, dict):
            detail = {}
        keywords = _list_text(detail.get("keywords"))
        summary_parts = [
            _text(detail.get("label")),
            _text(detail.get("summary")),
            _text(detail.get("tone")),
            _text(detail.get("themeMode")),
            " ".join(keywords),
        ]
        search_blob = " ".join(part for part in summary_parts if part).lower()
        template_governance = _template_governance(data, layout_id)
        lifecycle = str(template_governance.get("lifecycle") or "active")
        lifecycle_counts[lifecycle] = lifecycle_counts.get(lifecycle, 0) + 1
        quality_sum += float(template_governance.get("quality_score") or 0.0)
        failure_sum += float(template_governance.get("failure_rate_30d") or 0.0)
        if template_governance.get("scenario_tags"):
            coverage += 1
        templates.append(
            {
                "id": layout_id,
                "label": _text(detail.get("label")) or layout_id,
                "summary": _text(detail.get("summary")),
                "tone": _text(detail.get("tone")),
                "themeMode": _text(detail.get("themeMode")),
                "keywords": keywords,
                "assets": _list_text(detail.get("assets")),
                "search": search_blob,
                "governance": template_governance,
            }
        )
    digest["templates"] = templates
    total = len(templates) or 1
    digest["governance_metrics"] = {
        "metadata_coverage_ratio": round(coverage / total, 4),
        "lifecycle_counts": lifecycle_counts,
        "avg_quality_score": round(quality_sum / total, 4),
        "avg_failure_rate_30d": round(failure_sum / total, 4),
    }
    return digest


def write_digest(output_path: Path = DEFAULT_OUTPUT, index_path: Path = DEFAULT_INDEX) -> Path:
    digest = build_digest(index_path=index_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(digest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate compact template digest JSON.")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = write_digest(output_path=args.output, index_path=args.index)
    print(output)


if __name__ == "__main__":
    main()
