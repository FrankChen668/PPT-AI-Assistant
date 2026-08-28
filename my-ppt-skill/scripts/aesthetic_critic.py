#!/usr/bin/env python3
"""Contract-aware aesthetic critic for design-directed PPT pages."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ACCENT_FALLBACK_RE = re.compile(r"#(?:932141|800020|A00030|990011)", re.IGNORECASE)


def _build_accent_re(accent_colors: list[str] | None) -> re.Pattern:
    """从项目 accent 色列表构建匹配正则；None 或空时返回酒红系 fallback。"""
    hex_colors = [c for c in (accent_colors or []) if isinstance(c, str) and c.startswith("#")]
    if not hex_colors:
        return ACCENT_FALLBACK_RE
    return re.compile("|".join(re.escape(c) for c in hex_colors), re.IGNORECASE)


def _extract_accent_colors(style_route: dict[str, Any]) -> list[str]:
    """从 style_route.json 提取强调色 hex 列表：顶层 accent_colors/palette 或
    color_system 的 primary/support palette；保留顺序并去重。"""
    colors: list[str] = []
    top = style_route.get("accent_colors")
    if isinstance(top, list):
        colors.extend(str(item) for item in top if isinstance(item, str))
    palette = style_route.get("palette")
    if isinstance(palette, dict):
        colors.extend(str(item) for item in palette.values() if isinstance(item, str))
    elif isinstance(palette, list):
        colors.extend(str(item) for item in palette if isinstance(item, str))
    color_system = ((style_route.get("profile_tokens") or {}).get("hard_tokens") or {}).get("color_system") or {}
    for key in ("primary_palette", "support_palette"):
        value = color_system.get(key)
        if isinstance(value, list):
            colors.extend(str(item) for item in value if isinstance(item, str))
    return list(dict.fromkeys(c for c in colors if c.startswith("#")))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _find_by_id(items: list[Any], slide_id: int) -> dict[str, Any]:
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            sid = int(item.get("slide_id") or item.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if sid == slide_id:
            return item
    return {}


def _slide_id_from_svg(path: Path) -> int | None:
    match = re.search(r"slide_(\d+)\.svg$", path.name)
    if not match:
        return None
    return int(match.group(1))


def _svg_stats(path: Path, accent_colors: list[str] | None = None) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    accent_re = _build_accent_re(accent_colors)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {"text": "", "raw": text, "rects": [], "font_sizes": [], "accent_hits": 0, "connector_count": 0}
    all_text = "".join(
        node.text or "" for node in root.iter() if node.tag.endswith("text") or node.tag.endswith("tspan")
    )
    rects: list[tuple[float, float]] = []
    font_sizes: list[float] = []
    for node in root.iter():
        if node.tag.endswith("rect"):
            try:
                rects.append((float(node.attrib.get("width", 0)), float(node.attrib.get("height", 0))))
            except ValueError:
                pass
        if node.tag.endswith("text"):
            try:
                raw = node.attrib.get("font-size", "0")
                font_sizes.append(float(raw.removesuffix("px")))
            except ValueError:
                pass
    connector_count = sum(1 for node in root.iter() if node.tag.endswith(("line", "polyline", "path")))
    return {
        "text": all_text,
        "raw": text,
        "rects": rects,
        "font_sizes": font_sizes,
        "accent_hits": len(accent_re.findall(text)),
        "connector_count": connector_count,
    }


def _similar_card_count(rects: list[tuple[float, float]]) -> int:
    large = [(w, h) for w, h in rects if w >= 180 and h >= 80]
    best = 0
    for w, h in large:
        count = sum(1 for ow, oh in large if abs(ow - w) <= 28 and abs(oh - h) <= 28)
        best = max(best, count)
    return best


def _severity(profile: str, quality_mode: str) -> str:
    if quality_mode == "premium" or any(token in profile for token in ("proposal", "consult", "tender", "bid")):
        return "warning"
    return "advisory"


def _has_evidence_artifact(stats: dict[str, Any]) -> bool:
    raw = str(stats.get("raw") or "").lower()
    text = str(stats.get("text") or "").lower()
    markers = (
        "data-artifact",
        "prototype",
        "demo",
        "console",
        "browser",
        "window",
        "screen",
        "dashboard",
        "mockup",
        "interface",
        "原型",
        "界面",
        "控制台",
        "可运行",
        "大盘",
    )
    if any(marker in raw or marker in text for marker in markers):
        return True
    rects = list(stats.get("rects") or [])
    large = [(w, h) for w, h in rects if w >= 420 and h >= 220]
    small = [(w, h) for w, h in rects if 20 <= w <= 220 and 10 <= h <= 90]
    return bool(large and len(small) >= 4)


def run_aesthetic_critic(
    project_dir: Path,
    svg_dir: Path,
    *,
    profile: str = "presentation",
    quality_mode: str = "dev-fast",
    slide_id: int | None = None,
) -> dict[str, Any]:
    story = _read_json(project_dir / "design_story_plan.json")
    if not story:
        return {"enabled": False, "checked_slides": 0, "findings": []}
    blueprint = _read_json(project_dir / "blueprint.json")
    visual_plan = _read_json(project_dir / "slide_visual_plan.json")
    style_route = _read_json(project_dir / "style_route.json")
    accent_colors = _extract_accent_colors(style_route)
    story_slides = [item for item in story.get("slides", []) if isinstance(item, dict)]
    findings: list[dict[str, Any]] = []
    required_plan_fields = {
        "design_move",
        "visual_grammar_id",
        "rewrite_policy",
        "dominant_object",
        "accent_terms",
        "secondary_content_policy",
        "reference_case_ids",
    }
    checked = 0
    rhythm_sequence: list[tuple[int, str]] = []
    for story_slide in story_slides:
        try:
            sid = int(story_slide.get("slide_id") or 0)
        except (TypeError, ValueError):
            continue
        if slide_id is not None and sid != slide_id:
            continue
        checked += 1
        plan_slide = _find_by_id(list(visual_plan.get("slides") or []), sid)
        missing_fields = set(required_plan_fields)
        if any(
            key in story_slide
            for key in ("primary_grammar_id", "secondary_grammar_ids", "evidence_artifact_plan", "section_rhythm_role")
        ):
            missing_fields.update(
                {
                    "primary_grammar_id",
                    "secondary_grammar_ids",
                    "composite_design_move",
                    "evidence_artifact_plan",
                    "section_rhythm_role",
                }
            )
        missing = sorted(missing_fields - set(plan_slide))
        if missing:
            findings.append(
                {
                    "severity": "warning" if quality_mode in {"release-safe", "premium"} else "advisory",
                    "code": "design-contract-incomplete",
                    "slide_id": sid,
                    "path": str(project_dir / "slide_visual_plan.json"),
                    "message": f"Slide {sid} is missing design-director fields in slide_visual_plan.json: {missing}.",
                }
            )
        svg_path = svg_dir / f"slide_{sid:02d}.svg"
        if not svg_path.exists():
            continue
        stats = _svg_stats(svg_path, accent_colors=accent_colors)
        max_font = max(stats["font_sizes"] or [0])
        card_count = _similar_card_count(stats["rects"])
        severity = _severity(profile, quality_mode)
        rhythm_role = str(story_slide.get("section_rhythm_role") or plan_slide.get("section_rhythm_role") or "")
        if rhythm_role:
            rhythm_sequence.append((sid, rhythm_role))
        title = str(_find_by_id(list(blueprint.get("slides") or []), sid).get("title") or "")
        headline = str(story_slide.get("headline_rewrite") or "")
        artifact_plan = story_slide.get("evidence_artifact_plan")
        if (
            isinstance(artifact_plan, dict)
            and bool(artifact_plan.get("required"))
            and not _has_evidence_artifact(stats)
        ):
            findings.append(
                {
                    "severity": severity,
                    "code": "design-evidence-artifact-missing",
                    "slide_id": sid,
                    "path": str(svg_path),
                    "message": (
                        f"Slide {sid} requires an evidence artifact, but the SVG does not expose "
                        "a prototype, demo, screen, or engine object."
                    ),
                }
            )
        secondary_ids = [str(item) for item in story_slide.get("secondary_grammar_ids", []) if str(item).strip()]
        if (
            secondary_ids
            and card_count >= 3
            and int(stats.get("connector_count") or 0) == 0
            and not _has_evidence_artifact(stats)
        ):
            findings.append(
                {
                    "severity": severity,
                    "code": "design-composite-move-not-executed",
                    "slide_id": sid,
                    "path": str(svg_path),
                    "message": (
                        f"Slide {sid} declares composite visual grammar but still reads as "
                        "a single flat card structure."
                    ),
                }
            )
        if str(story_slide.get("dominant_object") or "").strip() and max_font < 32 and stats["accent_hits"] < 2:
            findings.append(
                {
                    "severity": severity,
                    "code": "design-no-visual-protagonist",
                    "slide_id": sid,
                    "path": str(svg_path),
                    "message": f"Slide {sid} declares a dominant object but the SVG has no strong visual protagonist.",
                }
            )
        archetype_text = " ".join(
            str(plan_slide.get(key) or "") for key in ("visual_archetype", "composition_intent", "selected_archetype")
        ).lower()
        if card_count >= 3 and ("card" in archetype_text or "matrix" in archetype_text or "grid" in archetype_text):
            findings.append(
                {
                    "severity": severity,
                    "code": "design-cardization-flat",
                    "slide_id": sid,
                    "path": str(svg_path),
                    "message": (
                        f"Slide {sid} still reads as an equal-weight card grid instead of the "
                        "selected design move."
                    ),
                }
            )
        if title and headline and headline.strip() == title.strip():
            findings.append(
                {
                    "severity": severity,
                    "code": "design-copy-not-rewritten",
                    "slide_id": sid,
                    "path": str(project_dir / "design_story_plan.json"),
                    "message": f"Slide {sid} headline_rewrite is still verbatim blueprint title.",
                }
            )
        accent_terms = [str(item) for item in story_slide.get("accent_terms", []) if str(item).strip()]
        if accent_terms and stats["accent_hits"] == 0 and not any(term in stats["text"] for term in accent_terms):
            findings.append(
                {
                    "severity": "advisory",
                    "code": "design-accent-weak",
                    "slide_id": sid,
                    "path": str(svg_path),
                    "message": (
                        f"Slide {sid} accent terms are not visually represented in the SVG text "
                        "or accent color."
                    ),
                }
            )
    for idx in range(2, len(rhythm_sequence)):
        window = rhythm_sequence[idx - 2 : idx + 1]
        roles = {role for _, role in window}
        if len(roles) == 1:
            sid = window[-1][0]
            role = window[-1][1]
            findings.append(
                {
                    "severity": _severity(profile, quality_mode),
                    "code": "design-section-rhythm-repeated",
                    "slide_id": sid,
                    "path": str(project_dir / "design_story_plan.json"),
                    "message": (
                        f"Slides {window[0][0]}-{sid} repeat section rhythm role {role!r}; "
                        "vary the chapter rhythm before Executor authoring."
                    ),
                }
            )
    return {
        "enabled": True,
        "checked_slides": checked,
        "finding_count": len(findings),
        "findings": findings,
    }
