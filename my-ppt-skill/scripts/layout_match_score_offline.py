from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LayoutProfile:
    layout_tag: str
    recipe_label: str
    page_types: set[str]
    density: set[str]
    kpi_range: tuple[int, int]
    chart_range: tuple[int, int]
    conclusion_range: tuple[int, int]
    has_comparison: bool | None
    has_timeline: bool | None
    complexity: str


PROFILES: list[LayoutProfile] = [
    LayoutProfile(
        layout_tag="Data-Three-KPIs",
        recipe_label="3 KPI + 1 chart + 3 conclusions",
        page_types={"biz_analysis", "data_conclusion"},
        density={"medium", "high"},
        kpi_range=(3, 4),
        chart_range=(0, 1),
        conclusion_range=(2, 4),
        has_comparison=False,
        has_timeline=False,
        complexity="medium",
    ),
    LayoutProfile(
        layout_tag="Chart-Bar",
        recipe_label="Chart + Conclusion",
        page_types={"data_conclusion", "biz_analysis", "comparison"},
        density={"medium", "high"},
        kpi_range=(0, 2),
        chart_range=(1, 2),
        conclusion_range=(1, 3),
        has_comparison=None,
        has_timeline=False,
        complexity="high",
    ),
    LayoutProfile(
        layout_tag="Chart-Line",
        recipe_label="Chart + Conclusion",
        page_types={"data_conclusion", "timeline", "biz_analysis"},
        density={"medium", "high"},
        kpi_range=(0, 2),
        chart_range=(1, 2),
        conclusion_range=(1, 3),
        has_comparison=None,
        has_timeline=False,
        complexity="high",
    ),
    LayoutProfile(
        layout_tag="Two-Columns-Split",
        recipe_label="Left-Right Comparison",
        page_types={"comparison", "biz_analysis"},
        density={"low", "medium"},
        kpi_range=(0, 2),
        chart_range=(0, 1),
        conclusion_range=(1, 3),
        has_comparison=True,
        has_timeline=False,
        complexity="medium",
    ),
    LayoutProfile(
        layout_tag="Timeline-Horizontal",
        recipe_label="Timeline",
        page_types={"timeline", "roadmap"},
        density={"low", "medium"},
        kpi_range=(0, 1),
        chart_range=(0, 1),
        conclusion_range=(1, 2),
        has_comparison=False,
        has_timeline=True,
        complexity="medium",
    ),
    LayoutProfile(
        layout_tag="Timeline-Vertical",
        recipe_label="Timeline",
        page_types={"timeline", "roadmap"},
        density={"medium", "high"},
        kpi_range=(0, 1),
        chart_range=(0, 1),
        conclusion_range=(1, 2),
        has_comparison=False,
        has_timeline=True,
        complexity="high",
    ),
    LayoutProfile(
        layout_tag="Grid-Three-Cards",
        recipe_label="Three Parallel Viewpoints",
        page_types={"parallel_points", "biz_analysis", "capability"},
        density={"medium", "high"},
        kpi_range=(0, 3),
        chart_range=(0, 1),
        conclusion_range=(1, 3),
        has_comparison=False,
        has_timeline=False,
        complexity="medium",
    ),
]


def _bound_score(value: int, low: int, high: int) -> float:
    if low <= value <= high:
        return 1.0
    if value < low:
        gap = low - value
    else:
        gap = value - high
    return max(0.0, 1.0 - 0.35 * gap)


def _bool_score(value: bool, expected: bool | None) -> float:
    if expected is None:
        return 0.7
    return 1.0 if value == expected else 0.0


def _density_score(value: str, expected: set[str]) -> float:
    if not value:
        return 0.5
    return 1.0 if value in expected else 0.2


def _page_type_score(value: str, expected: set[str]) -> float:
    if not value:
        return 0.5
    return 1.0 if value in expected else 0.2


def _complexity_score(value: str, expected: str) -> float:
    order = {"low": 0, "medium": 1, "high": 2}
    if value not in order:
        return 0.5
    return max(0.0, 1.0 - 0.5 * abs(order[value] - order[expected]))


def _infer_int(content: dict[str, Any], key: str, fallback_keys: tuple[str, ...]) -> int:
    direct = content.get(key)
    if isinstance(direct, int):
        return max(direct, 0)
    for name in fallback_keys:
        value = content.get(name)
        if isinstance(value, list):
            return len(value)
    return 0


def _infer_bool(content: dict[str, Any], key: str, hit_keys: tuple[str, ...]) -> bool:
    direct = content.get(key)
    if isinstance(direct, bool):
        return direct
    return any(k in content for k in hit_keys)


def _extract_features(slide: dict[str, Any]) -> dict[str, Any]:
    raw_content = slide.get("content")
    raw_features = slide.get("features")
    content: dict[str, Any] = raw_content if isinstance(raw_content, dict) else {}
    features: dict[str, Any] = raw_features if isinstance(raw_features, dict) else {}

    kpi_count = int(features.get("kpi_count", _infer_int(content, "kpi_count", ("kpis",))))
    chart_count = int(
        features.get(
            "chart_count",
            _infer_int(content, "chart_count", ("bars", "points", "chart_series")),
        )
    )
    conclusion_count = int(
        features.get(
            "conclusion_count",
            _infer_int(content, "conclusion_count", ("conclusions", "takeaways")),
        )
    )
    has_comparison = bool(
        features.get(
            "has_comparison",
            _infer_bool(content, "has_comparison", ("before", "after", "left", "right", "pros", "cons")),
        )
    )
    has_timeline = bool(
        features.get(
            "has_timeline",
            _infer_bool(content, "has_timeline", ("events", "phases", "milestones")),
        )
    )

    page_type = str(slide.get("page_type") or "").strip().lower()
    density = str(slide.get("content_density") or "").strip().lower()

    if not page_type:
        if has_timeline:
            page_type = "timeline"
        elif has_comparison:
            page_type = "comparison"
        elif chart_count > 0:
            page_type = "data_conclusion"
        elif kpi_count >= 3 and conclusion_count >= 2:
            page_type = "biz_analysis"
        else:
            page_type = "generic"

    if not density:
        signal = conclusion_count + chart_count + (kpi_count // 2)
        if signal >= 5:
            density = "high"
        elif signal >= 3:
            density = "medium"
        else:
            density = "low"

    if chart_count >= 1 and density == "high":
        complexity = "high"
    elif has_timeline or has_comparison or chart_count >= 1:
        complexity = "medium"
    else:
        complexity = "low"

    return {
        "page_type": page_type,
        "content_density": density,
        "kpi_count": kpi_count,
        "chart_count": chart_count,
        "conclusion_count": conclusion_count,
        "has_comparison": has_comparison,
        "has_timeline": has_timeline,
        "visual_complexity": complexity,
        "layout_hint": str(slide.get("layout_hint") or "").strip(),
    }


def _score_candidate(
    profile: LayoutProfile,
    extracted: dict[str, Any],
    usage_frequency: float,
) -> dict[str, Any]:
    structure_score = (
        _bound_score(extracted["kpi_count"], *profile.kpi_range)
        + _bound_score(extracted["chart_count"], *profile.chart_range)
        + _bound_score(extracted["conclusion_count"], *profile.conclusion_range)
        + _bool_score(extracted["has_comparison"], profile.has_comparison)
        + _bool_score(extracted["has_timeline"], profile.has_timeline)
    ) / 5.0

    density_score = _density_score(extracted["content_density"], profile.density)
    page_type_score = _page_type_score(extracted["page_type"], profile.page_types)
    complexity_score = _complexity_score(extracted["visual_complexity"], profile.complexity)

    total = (
        0.35 * structure_score
        + 0.20 * density_score
        + 0.20 * page_type_score
        + 0.15 * complexity_score
        + 0.10 * usage_frequency
    )

    return {
        "layout_tag": profile.layout_tag,
        "recipe_label": profile.recipe_label,
        "score": round(total, 4),
        "score_breakdown": {
            "structure": round(structure_score, 4),
            "density": round(density_score, 4),
            "page_type": round(page_type_score, 4),
            "visual_complexity": round(complexity_score, 4),
            "usage_frequency": round(usage_frequency, 4),
        },
    }


def recommend_layouts(blueprint: dict[str, Any], topk: int, threshold: float) -> dict[str, Any]:
    slides = blueprint.get("slides")
    if not isinstance(slides, list):
        raise ValueError("blueprint.json must contain a top-level slides array")

    layout_counter = Counter(
        str(slide.get("layout_tag", ""))
        for slide in slides
        if isinstance(slide, dict) and str(slide.get("layout_tag", "")).strip()
    )
    max_count = max(layout_counter.values(), default=1)

    output_slides: list[dict[str, Any]] = []

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        extracted = _extract_features(slide)

        candidates: list[dict[str, Any]] = []
        for profile in PROFILES:
            freq = layout_counter.get(profile.layout_tag, 0) / max_count
            candidates.append(_score_candidate(profile, extracted, usage_frequency=freq))

        candidates.sort(key=lambda item: item["score"], reverse=True)
        selected = candidates[:max(1, topk)]
        top_score = selected[0]["score"] if selected else 0.0

        decision = "recommendation"
        note = "offline recommendation only"
        if top_score < threshold:
            decision = "executor_free_svg"
            note = "No strong match. Prefer Executor free-form SVG composition."

        output_slides.append(
            {
                "slide_id": slide.get("id"),
                "current_layout_tag": slide.get("layout_tag"),
                "features_used": extracted,
                "decision": decision,
                "note": note,
                "candidates": selected,
            }
        )

    return {
        "mode": "offline_layout_match_score_prototype",
        "not_integrated_into_mainline": True,
        "weights": {
            "structure": 0.35,
            "density": 0.20,
            "page_type": 0.20,
            "visual_complexity": 0.15,
            "usage_frequency": 0.10,
        },
        "guardrails": [
            "Do not select layouts by usage frequency alone.",
            "Do not remove user content to force template matching.",
            "Do not force complex pages into a single template when confidence is low.",
            "Do not override explicit user style or page-type instructions.",
            "When no suitable match exists, recommend Executor free-form SVG composition.",
        ],
        "slides": output_slides,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline prototype for layout match scoring. Does not modify project files or pipeline behavior."
    )
    parser.add_argument("blueprint", type=Path, help="Path to blueprint.json")
    parser.add_argument("--topk", type=int, default=3, help="Top K candidates per slide")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.58,
        help="Minimum top score to return recommendation instead of executor_free_svg",
    )
    parser.add_argument("--output", type=Path, help="Optional output JSON path")
    args = parser.parse_args()

    data = json.loads(args.blueprint.read_text(encoding="utf-8-sig"))
    report = recommend_layouts(data, topk=max(1, args.topk), threshold=args.threshold)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
