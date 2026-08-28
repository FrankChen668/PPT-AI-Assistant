#!/usr/bin/env python3
"""Generate art direction artifacts between Designer and Executor.

Outputs in projects/<project_name>/:
- art_direction.md
- reference_pack.json
- slide_visual_plan.json
- style_drafts.json (single-route record or multi-draft options for low-confidence routing)
- layout_memory.json (lightweight last-selected archetype memory)
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from generate_design_story_plan import build_design_story_plan
from generate_slide_plan import build_semantic_plan_row
from pipeline.scene_router import build_execution_policy, classify_slide_scene
from pipeline.visual_contracts import build_visual_contract
from prompt_pattern_catalog import resolve_prompt_pattern
from template_catalog import build_reference_pack_from_catalog

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_LAYOUTS_INDEX = SKILL_DIR / "ppt-ai-core" / "templates" / "layouts" / "layouts_index.json"
DEFAULT_TEMPLATE_CATALOG = SKILL_DIR / "templates" / "template_catalog.json"
TEMPLATE_LOOKUP_MODE = "index_then_lazy_load"
TEMPLATE_REFERENCE_MAX_PER_SLIDE = 2

RECOMMENDATION_RULES: list[tuple[str, tuple[str, ...], list[str]]] = [
    (
        "certification",
        ("certification", "test", "qa", "认证", "检测"),
        ["中汽研_常规", "中汽研_商务", "中汽研_现代"],
    ),
    (
        "energy",
        ("energy", "construction", "工程", "电建"),
        ["中国电建_常规", "中国电建_现代"],
    ),
    (
        "government",
        ("government", "state-owned", "政务", "国企"),
        ["government_blue", "government_red", "ai_ops"],
    ),
    (
        "finance",
        ("finance", "investment", "银行", "投资"),
        ["招商银行", "exhibit", "mckinsey"],
    ),
    (
        "technology",
        ("technology", "ai", "architecture", "system", "技术", "架构"),
        ["anthropic", "google_style", "ai_ops"],
    ),
    (
        "strategy",
        ("strategy", "executive", "consulting", "board", "战略"),
        ["exhibit", "mckinsey", "consulting_classic"],
    ),
    (
        "creative",
        ("creative", "campaign", "brand", "活动", "品牌"),
        ["smart_red", "pixel_retro"],
    ),
]
DEFAULT_TEMPLATES = ["mckinsey", "exhibit", "anthropic"]

CATEGORY_MOTIFS: dict[str, list[str]] = {
    "strategy": ["exhibit takeaway bar", "asymmetric callout", "executive signal strip"],
    "technology": ["modular system panel", "connection lines", "dark-light contrast anchors"],
    "government": ["stable crest line", "formal section rail", "balanced bilateral composition"],
    "finance": ["premium accent line", "key metric highlight", "evidence-first table blocks"],
    "certification": ["compliance badge", "evidence checklist", "audit trail blocks"],
    "energy": ["infrastructure flow", "layered process arrows", "engineering milestone bands"],
    "creative": ["bold color punctuation", "dynamic overlap", "hero visual foreground"],
    "default": ["single accent focal point", "rhythm by whitespace", "one-idea-per-slide emphasis"],
}

BUSINESS_SEMANTIC_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("growth_strategy", ("growth", "strategy", "roadmap", "market", "growth plan")),
    ("finance_risk", ("finance", "investment", "bank", "risk", "valuation", "profit")),
    ("policy_compliance", ("government", "policy", "compliance", "governance", "regulation")),
    ("technology_system", ("technology", "architecture", "system", "ai", "platform")),
    ("operations_execution", ("delivery", "execution", "ops", "efficiency", "rollout")),
]

EMOTION_SEMANTIC_BY_PROFILE: dict[str, str] = {
    "executive_exhibit": "decisive_confident",
    "consulting_classic": "decisive_confident",
    "luxury_finance": "premium_trustworthy",
    "engineering_blueprint": "rational_precise",
    "ai_product_keynote": "innovative_optimistic",
    "policy_institutional": "authoritative_stable",
    "editorial_report": "balanced_calm",
    "strategy_consulting": "decisive_confident",
}

DENSITY_HINTS: dict[str, str] = {
    "low": "prefer one dominant visual + sparse support icons",
    "medium": "mix icon clusters and one supporting chart/diagram",
    "high": "prioritize structured icon sets and explanatory diagrams over decorative images",
}
CORE_CONCLUSION_LAYOUTS = {
    "Strategy-Map",
    "Capability-Mapping",
    "Roadmap-MultiPhase",
    "Data-Single-KPI",
    "Data-Three-KPIs",
    "Chart-Bar",
    "Chart-Line",
}


@dataclass(frozen=True)
class ArtDirectionArtifacts:
    art_direction_md: Path
    reference_pack_json: Path
    slide_visual_plan_json: Path
    design_story_plan_json: Path
    style_drafts_json: Path
    layout_memory_json: Path


DEFAULT_LAYOUT_EXPLORATION: dict[str, Any] = {
    "enabled": True,
    "candidate_count": 2,
    "anti_repeat_window": 1,
    "enforce_in_modes": ["release-safe", "premium"],
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"Invalid JSON file: {path} ({exc})") from exc


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_design_spec(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _required_file(project_dir: Path, name: str) -> Path:
    path = project_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return path


def _normalize_template_key(layouts: dict[str, Any], key: str) -> str:
    if key in layouts:
        return key
    lower_map = {layout_id.lower(): layout_id for layout_id in layouts}
    found = lower_map.get(key.lower())
    if not found:
        raise ValueError(f"Unknown template id: {key}")
    return found


def _dedupe_templates(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _normalize_text(value: str) -> str:
    return value.strip().lower()


def _context_tokens(value: str) -> set[str]:
    lowered = value.lower()
    normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", lowered)
    return {token for token in normalized.split() if token}


def _infer_business_semantic(context: str, category: str) -> str:
    tokens = _context_tokens(context)
    for semantic, keywords in BUSINESS_SEMANTIC_KEYWORDS:
        if any(keyword in context.lower() for keyword in keywords) or any(keyword in tokens for keyword in keywords):
            return semantic
    fallback_by_category = {
        "strategy": "growth_strategy",
        "technology": "technology_system",
        "government": "policy_compliance",
        "finance": "finance_risk",
        "energy": "operations_execution",
        "certification": "policy_compliance",
        "creative": "growth_strategy",
    }
    return fallback_by_category.get(category, "operations_execution")


def _infer_emotion_semantic(
    style_profile: str,
    tone: str,
    style_objective: str,
) -> str:
    profile_key = style_profile.strip().lower()
    if profile_key in EMOTION_SEMANTIC_BY_PROFILE:
        return EMOTION_SEMANTIC_BY_PROFILE[profile_key]
    tone_text = f"{tone} {style_objective}".lower()
    if any(token in tone_text for token in ("official", "formal", "authoritative", "鏀垮姟", "姝ｅ紡")):
        return "authoritative_stable"
    if any(token in tone_text for token in ("finance", "premium", "invest", "financial", "鎶曡祫")):
        return "premium_trustworthy"
    if any(token in tone_text for token in ("tech", "system", "architecture", "engineering")):
        return "rational_precise"
    if any(token in tone_text for token in ("creative", "brand", "campaign", "鍒涙剰")):
        return "expressive_dynamic"
    return "balanced_calm"


def _estimate_information_density(blueprint: dict[str, Any]) -> str:
    slides = blueprint.get("slides")
    if not isinstance(slides, list) or not slides:
        return "medium"

    complexity_scores: list[float] = []
    data_like = 0
    for raw_slide in slides:
        if not isinstance(raw_slide, dict):
            continue
        layout_tag = str(raw_slide.get("layout_tag", ""))
        if layout_tag.startswith("Data-") or layout_tag.startswith("Chart-"):
            data_like += 1
        content = raw_slide.get("content")
        if not isinstance(content, dict):
            complexity_scores.append(1.0)
            continue
        score = float(len(content))
        for value in content.values():
            if isinstance(value, list):
                score += min(6.0, float(len(value)) * 0.8)
            elif isinstance(value, dict):
                score += min(4.0, float(len(value)) * 0.6)
            elif isinstance(value, str) and len(value) > 60:
                score += 0.6
        complexity_scores.append(score)

    if not complexity_scores:
        return "medium"
    avg_score = sum(complexity_scores) / len(complexity_scores)
    data_ratio = data_like / max(1, len(complexity_scores))
    if avg_score >= 7.0 or data_ratio >= 0.35:
        return "high"
    if avg_score >= 4.0:
        return "medium"
    return "low"


def _asset_type_for_layout(layout_tag: str, density: str) -> str:
    if layout_tag.startswith("Image-"):
        return "hero_image"
    if layout_tag.startswith("Data-") or layout_tag.startswith("Chart-"):
        return "data_iconography"
    if layout_tag in {
        "Strategy-Map",
        "Capability-Mapping",
        "Roadmap-MultiPhase",
        "Timeline-Horizontal",
        "Timeline-Vertical",
    }:
        return "diagrammatic_icons"
    if layout_tag in {"Cover-Center", "Statement-Bold"}:
        return "hero_symbol"
    return "supporting_icons" if density != "low" else "minimal_icons"


def _build_asset_component_binding(slides: list[dict[str, Any]], density: str) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    for slide in slides:
        layout_tag = str(slide.get("layout_tag", "")).strip()
        if not layout_tag:
            continue
        preferred = _asset_type_for_layout(layout_tag, density)
        bindings.append(
            {
                "slide_id": slide.get("id"),
                "layout_tag": layout_tag,
                "preferred_asset_type": preferred,
                "mapping_rule": (
                    "match business concept first, then emotion tone, then density constraint; "
                    "avoid decorative assets without decision support value"
                ),
            }
        )
    return bindings


def _build_asset_semantic_mapping(
    *,
    context: str,
    category: str,
    blueprint: dict[str, Any],
    style_profile: str,
    tone: str,
    style_objective: str,
) -> dict[str, Any]:
    business_semantic = _infer_business_semantic(context, category)
    emotion_semantic = _infer_emotion_semantic(style_profile, tone, style_objective)
    density = _estimate_information_density(blueprint)
    slides = [item for item in blueprint.get("slides", []) if isinstance(item, dict)]
    return {
        "business_semantic": business_semantic,
        "emotion_semantic": emotion_semantic,
        "information_density": density,
        "selection_policy": [
            "business semantic must be satisfied before style embellishment",
            "emotion semantic controls palette intensity and icon sharpness",
            "information density controls asset count ceiling per slide",
        ],
        "icon_style_tokens": [
            business_semantic,
            emotion_semantic,
            f"density_{density}",
        ],
        "image_style_tokens": [
            f"{business_semantic}_scene",
            f"{emotion_semantic}_mood",
            DENSITY_HINTS.get(density, DENSITY_HINTS["medium"]),
        ],
        "component_binding": _build_asset_component_binding(slides, density),
    }


def _match_template_category(context: str) -> tuple[str, list[str]]:
    lowered = _normalize_text(context)
    for category, keywords, templates in RECOMMENDATION_RULES:
        if any(keyword in lowered for keyword in keywords):
            return category, templates
    return "default", DEFAULT_TEMPLATES


def recommend_templates(audience: str, purpose: str, style_objective: str, keywords_text: str) -> list[str]:
    """Return up to 3 template ids from lightweight rule matching."""
    context = " ".join([audience, purpose, style_objective, keywords_text])
    _, templates = _match_template_category(context)
    return templates[:3]


def _load_template_binding(project_dir: Path) -> dict[str, Any] | None:
    binding_path = project_dir / "template_binding.json"
    if not binding_path.exists():
        return None
    return _read_json(binding_path)


def _candidate_binding_template(binding: dict[str, Any] | None) -> str | None:
    if not binding:
        return None
    for key in ("template_key", "layout_id", "template_id"):
        value = binding.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _template_reference_root(
    template_id: str,
    project_dir: Path,
    binding: dict[str, Any] | None,
) -> tuple[Path | None, str]:
    local_dir = project_dir / "templates" / "layout_ref" / template_id
    if local_dir.is_dir():
        return local_dir, "project_layout_ref"

    if binding:
        rel = binding.get("relative_path")
        if isinstance(rel, str) and rel.strip():
            candidate = (project_dir / rel).resolve()
            if candidate.is_dir():
                return candidate, "template_binding_relative_path"

        src = binding.get("source_template")
        if isinstance(src, str) and src.strip():
            candidate = Path(src)
            if not candidate.is_absolute():
                candidate = (SKILL_DIR / src).resolve()
            if candidate.is_dir():
                return candidate, "template_binding_source_template"

    index_dir = SKILL_DIR / "ppt-ai-core" / "templates" / "layouts" / template_id
    if index_dir.is_dir():
        return index_dir, "global_layouts_index"
    return None, "missing"


def _reference_files_for_template(template_id: str, project_dir: Path, binding: dict[str, Any] | None) -> list[str]:
    base, _ = _template_reference_root(template_id, project_dir, binding)
    if base is None:
        return []
    wanted = ["design_spec.md", "01_cover.svg", "02_toc.svg", "02_chapter.svg", "03_content.svg", "04_ending.svg"]
    output: list[str] = []
    for name in wanted:
        path = base / name
        if not path.exists():
            continue
        try:
            rel_project = path.resolve().relative_to(project_dir.resolve())
            output.append(rel_project.as_posix())
            continue
        except ValueError:
            pass
        try:
            rel_skill = path.resolve().relative_to(SKILL_DIR.resolve())
            output.append(rel_skill.as_posix())
        except ValueError:
            output.append(path.resolve().as_posix())
    return output


def _collect_reference_files(
    primary: str,
    secondaries: list[str],
    project_dir: Path,
    binding: dict[str, Any] | None,
) -> list[str]:
    selected = _dedupe_templates([primary] + secondaries)
    refs: list[str] = []
    for template_id in selected:
        refs.extend(_reference_files_for_template(template_id, project_dir, binding))
    return _dedupe_templates(refs)


def _collect_reference_inventory(
    primary: str,
    secondaries: list[str],
    project_dir: Path,
    binding: dict[str, Any] | None,
) -> dict[str, list[str]]:
    selected = _dedupe_templates([primary] + secondaries)
    inventory: dict[str, list[str]] = {}
    for template_id in selected:
        inventory[template_id] = _reference_files_for_template(template_id, project_dir, binding)
    return inventory


def _reference_needles_for_layout(layout_tag: str) -> tuple[str, ...]:
    if layout_tag in {"Cover-Center"}:
        return ("01_cover.svg",)
    if layout_tag in {"Section-Divider"}:
        return ("02_chapter.svg", "02_toc.svg")
    if layout_tag in {"End-Page"}:
        return ("04_ending.svg",)
    return ("03_content.svg", "02_toc.svg")


def _slide_reference_files(reference_files: list[str], layout_tag: str) -> list[str]:
    if not reference_files:
        return []
    needles = _reference_needles_for_layout(layout_tag)
    filtered = [item for item in reference_files if any(item.endswith(needle) for needle in needles)]
    return filtered[:TEMPLATE_REFERENCE_MAX_PER_SLIDE]


def _lazy_load_reference_files(
    blueprint: dict[str, Any],
    reference_inventory: dict[str, list[str]],
) -> tuple[list[str], dict[str, Any]]:
    slides = blueprint.get("slides") if isinstance(blueprint, dict) else None
    selected_templates = [key for key in reference_inventory.keys()]
    all_candidates: list[str] = []
    for key in selected_templates:
        all_candidates.extend(reference_inventory.get(key, []))
    deduped_all = _dedupe_templates(all_candidates)

    if not isinstance(slides, list):
        return deduped_all, {
            "template_lookup_mode": TEMPLATE_LOOKUP_MODE,
            "template_reference_files_loaded": len(deduped_all),
            "template_reference_files_skipped": 0,
            "template_lazy_load_hit_ratio": 1.0 if deduped_all else 0.0,
            "template_lazy_load_warning": False,
            "template_lazy_load_warning_reason": None,
        }

    needed_names: set[str] = set()
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        layout_tag = str(slide.get("layout_tag", "")).strip()
        for needle in _reference_needles_for_layout(layout_tag):
            needed_names.add(needle)

    loaded = [item for item in deduped_all if any(item.endswith(needle) for needle in needed_names)]
    loaded = _dedupe_templates(loaded)
    skipped = max(0, len(deduped_all) - len(loaded))
    ratio = round((len(loaded) / len(deduped_all)), 4) if deduped_all else 0.0

    # Warn when any page tries to pull too many references; keep non-blocking.
    per_slide_over_limit = False
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        layout_tag = str(slide.get("layout_tag", "")).strip()
        if len(_slide_reference_files(loaded, layout_tag)) > TEMPLATE_REFERENCE_MAX_PER_SLIDE:
            per_slide_over_limit = True
            break

    return loaded, {
        "template_lookup_mode": TEMPLATE_LOOKUP_MODE,
        "template_reference_files_loaded": len(loaded),
        "template_reference_files_skipped": skipped,
        "template_lazy_load_hit_ratio": ratio,
        "template_lazy_load_warning": per_slide_over_limit,
        "template_lazy_load_warning_reason": (
            f"reference files per slide exceeded {TEMPLATE_REFERENCE_MAX_PER_SLIDE}"
            if per_slide_over_limit
            else None
        ),
    }


def _archetype_for_layout(layout_tag: str) -> str:
    mapping = {
        "Cover-Center": "hero opener with strong focal headline",
        "Statement-Bold": "single-claim manifesto with emphatic anchor bar",
        "Section-Divider": "chapter transition with controlled drama",
        "End-Page": "calm close with contact certainty",
        "Strategy-Map": "executive exhibit with asymmetric callout",
        "Capability-Mapping": "three-lane capability map with dominant system-support lane",
        "Roadmap-MultiPhase": "multi-band roadmap with phase momentum",
        "Timeline-Horizontal": "progressive timeline with forward motion",
        "Timeline-Vertical": "stacked milestone narrative with alternating anchors",
        "Flow-Steps": "process runway with directional pacing",
    }
    if layout_tag in mapping:
        return mapping[layout_tag]
    if layout_tag.startswith("Grid-"):
        return "modular insight grid with one highlighted module"
    if layout_tag.startswith("Data-") or layout_tag.startswith("Chart-"):
        return "evidence-first data stage with clear hero metric"
    if layout_tag.startswith("Image-"):
        return "image-led storytelling with anchored copy block"
    if layout_tag in {"Two-Columns-Split", "Before-After", "Pros-Cons"}:
        return "deliberate comparison board with controlled contrast"
    return "structured editorial canvas with controlled asymmetry"


def _composition_intent_for_layout(layout_tag: str) -> str:
    if layout_tag in {"Cover-Center", "Statement-Bold"}:
        return "Create one dominant visual center, then support with minimal secondary anchors."
    if layout_tag in {"Capability-Mapping", "Roadmap-MultiPhase", "Strategy-Map"}:
        return "Use directional lanes to move the eye from context to decision implication."
    if layout_tag.startswith("Grid-"):
        return "Break uniformity with one offset or weighted card to avoid matrix monotony."
    if layout_tag.startswith("Data-") or layout_tag.startswith("Chart-"):
        return "Prioritize the conclusion zone before showing supporting evidence marks."
    return "Balance whitespace and content density to maintain narrative momentum."


def _hierarchy_strategy_for_layout(layout_tag: str) -> str:
    if layout_tag in {"Capability-Mapping", "Roadmap-MultiPhase"}:
        return "Primary: section headline; Secondary: lane headers; Tertiary: evidence details."
    if layout_tag.startswith("Chart-") or layout_tag.startswith("Data-"):
        return "Primary: key metric takeaway; Secondary: data marks; Tertiary: annotation footnotes."
    return "Primary: headline; Secondary: structural grouping; Tertiary: explanatory copy."


def _rhythm_role(slide_index: int, total: int, layout_tag: str) -> str:
    if slide_index == 1:
        return "set-tone"
    if slide_index == total:
        return "resolve"
    if layout_tag in {"Section-Divider", "Statement-Bold"}:
        return "accent-break"
    if layout_tag.startswith("Data-") or layout_tag.startswith("Chart-"):
        return "evidence-peak"
    if layout_tag in {"Capability-Mapping", "Roadmap-MultiPhase", "Strategy-Map"}:
        return "narrative-core"
    return "supporting-flow"


def _variation_rule(layout_tag: str) -> str:
    if layout_tag.startswith("Grid-"):
        return "Avoid equal-width card matrix repetition; keep at least one card with asymmetric weight."
    if layout_tag in {"Two-Columns-Split", "Before-After", "Pros-Cons"}:
        return "Avoid mirrored bilateral split on consecutive pages; vary the dominant side."
    if layout_tag in {"Cover-Center", "Section-Divider"}:
        return "Avoid centered title lockup repetition on adjacent slides."
    return "Avoid generic left-right split and avoid card stacks with identical rhythm."


def _candidate_count(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 2
    return 2 if parsed != 2 else parsed


def _resolve_layout_exploration(
    style_route: dict[str, Any] | None,
    *,
    layout_exploration_mode: str = "auto",
    candidate_count: int = 2,
) -> dict[str, Any]:
    route_block = style_route.get("layout_exploration") if isinstance(style_route, dict) else None
    payload = dict(DEFAULT_LAYOUT_EXPLORATION)
    if isinstance(route_block, dict):
        payload["enabled"] = bool(route_block.get("enabled", payload["enabled"]))
        payload["candidate_count"] = _candidate_count(route_block.get("candidate_count", payload["candidate_count"]))
        payload["anti_repeat_window"] = int(route_block.get("anti_repeat_window", payload["anti_repeat_window"]) or 1)
        modes = route_block.get("enforce_in_modes")
        if isinstance(modes, list):
            payload["enforce_in_modes"] = [str(item).strip() for item in modes if str(item).strip()]
    if layout_exploration_mode == "on":
        payload["enabled"] = True
    elif layout_exploration_mode == "off":
        payload["enabled"] = False
    payload["candidate_count"] = _candidate_count(candidate_count)
    payload["anti_repeat_window"] = max(1, int(payload.get("anti_repeat_window", 1)))
    return payload


def _archetype_family(archetype: str, layout_tag: str) -> str:
    arche = archetype.lower()
    layout = layout_tag.lower()
    text = arche
    if any(token in text for token in ("card", "grid", "matrix", "list", "module")):
        return "modular-grid"
    if any(token in text for token in ("timeline", "roadmap", "milestone", "phase")):
        return "timeline-roadmap"
    if any(token in text for token in ("flow", "process", "swimlane", "runway", "lane")):
        return "process-flow"
    if any(token in text for token in ("data", "chart", "kpi", "metric", "evidence")):
        return "evidence-data"
    if any(token in text for token in ("hero", "manifesto", "statement", "headline")):
        return "hero-claim"
    if any(token in text for token in ("comparison", "contrast", "versus", "before-after")):
        return "comparison"
    # fallback to layout signal when archetype wording is generic
    if any(token in layout for token in ("grid", "matrix", "list")):
        return "modular-grid"
    if any(token in layout for token in ("timeline", "roadmap")):
        return "timeline-roadmap"
    if any(token in layout for token in ("flow", "process")):
        return "process-flow"
    if any(token in layout for token in ("data-", "chart-")):
        return "evidence-data"
    return "editorial"


def _alternative_archetype(layout_tag: str) -> tuple[str, str, str]:
    if layout_tag.startswith("Grid-"):
        return (
            "alternating evidence strips with one dominant claim anchor",
            "Break cards into staggered horizontal evidence strips with one dominant summary zone.",
            "Avoid equal-size card blocks; enforce asymmetry between odd/even rows.",
        )
    if layout_tag in {"Strategy-Map", "Capability-Mapping"}:
        return (
            "swimlane decision flow with milestone anchors",
            "Use top-down swimlanes to show dependencies before detailing supporting evidence.",
            "Avoid turning lanes into equal cards; keep one dominant decision lane.",
        )
    if layout_tag in {"Roadmap-MultiPhase", "Timeline-Horizontal", "Timeline-Vertical"}:
        return (
            "phase-gated staircase with checkpoint gates",
            "Use staircase progression to emphasize gating decisions between phases.",
            "Avoid uniform timeline nodes; vary phase width by importance.",
        )
    if layout_tag.startswith("Data-") or layout_tag.startswith("Chart-"):
        return (
            "insight ladder with ranked evidence checkpoints",
            "Lead with takeaway, then descend through ranked evidence checkpoints.",
            "Avoid chart-only delivery; each evidence block must map to one decision implication.",
        )
    if layout_tag in {"Two-Columns-Split", "Before-After", "Pros-Cons"}:
        return (
            "weighted verdict board with asymmetric comparison",
            "Keep comparison but enforce one dominant side and one rebuttal side.",
            "Avoid mirror-symmetric bilateral panels.",
        )
    if layout_tag in {"Cover-Center", "Statement-Bold", "Section-Divider"}:
        return (
            "left-anchored hero headline with right evidence cue",
            "Shift from center lockup to left-anchored headline and one right-side cue.",
            "Avoid repeated centered hero lockups.",
        )
    return (
        "editorial split-stage with dominant takeaway lane",
        "Use editorial split-stage to separate judgment and support evidence.",
        "Avoid default equal split and repetitive card stack rhythm.",
    )


def _score_candidate_for_slide(layout_tag: str, narrative_intent: str, archetype: str) -> float:
    score = 1.0
    arche = archetype.lower()
    intent = narrative_intent.lower()
    if any(token in intent for token in ("timeline", "phase", "milestone", "推进", "阶段")) and any(
        token in arche for token in ("timeline", "roadmap", "phase", "staircase")
    ):
        score += 0.6
    if any(token in intent for token in ("process", "flow", "链路", "流程", "end-to-end")) and any(
        token in arche for token in ("flow", "lane", "runway", "swimlane")
    ):
        score += 0.6
    if any(token in intent for token in ("data", "evidence", "kpi", "指标")) and any(
        token in arche for token in ("data", "evidence", "insight", "metric")
    ):
        score += 0.5
    if layout_tag.startswith("Grid-") and "grid" in arche:
        score += 0.3
    if layout_tag.startswith("Data-") or layout_tag.startswith("Chart-"):
        if any(token in arche for token in ("data", "evidence", "insight")):
            score += 0.3
    return score


def _load_layout_memory(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "selected_sequence": [], "last_selection_by_slide": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"version": 1, "selected_sequence": [], "last_selection_by_slide": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "selected_sequence": [], "last_selection_by_slide": {}}
    seq = payload.get("selected_sequence")
    by_slide = payload.get("last_selection_by_slide")
    payload["selected_sequence"] = seq if isinstance(seq, list) else []
    payload["last_selection_by_slide"] = by_slide if isinstance(by_slide, dict) else {}
    payload["version"] = 1
    return payload

def _avoid_list(layout_tag: str) -> list[str]:
    common = [
        "Do not reduce this page to default equal cards.",
        "Do not use decorative gradients that obscure copy readability.",
    ]
    if layout_tag.startswith("Chart-") or layout_tag.startswith("Data-"):
        return common + ["Do not let labels overpower the key takeaway statement."]
    if layout_tag in {"Capability-Mapping", "Strategy-Map", "Roadmap-MultiPhase"}:
        return common + ["Do not flatten hierarchy into uniform bullet lists."]
    return common


def _breakthrough_and_clarity_slides(slides: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    breakthrough_tags = {
        "Cover-Center",
        "Statement-Bold",
        "Section-Divider",
        "Strategy-Map",
        "Capability-Mapping",
        "Roadmap-MultiPhase",
    }
    clarity_tags = {
        "Chart-Bar",
        "Chart-Line",
        "Data-Single-KPI",
        "Data-Three-KPIs",
        "Content-List-Left",
        "Content-List-Right",
    }
    breakthrough: list[int] = []
    clarity: list[int] = []
    for slide in slides:
        sid = slide.get("id")
        tag = str(slide.get("layout_tag", ""))
        if not isinstance(sid, int):
            continue
        if tag in breakthrough_tags:
            breakthrough.append(sid)
        if tag in clarity_tags:
            clarity.append(sid)
    return breakthrough, clarity


def _target_paths(project_dir: Path) -> ArtDirectionArtifacts:
    return ArtDirectionArtifacts(
        art_direction_md=project_dir / "art_direction.md",
        reference_pack_json=project_dir / "reference_pack.json",
        slide_visual_plan_json=project_dir / "slide_visual_plan.json",
        design_story_plan_json=project_dir / "design_story_plan.json",
        style_drafts_json=project_dir / "style_drafts.json",
        layout_memory_json=project_dir / "layout_memory.json",
    )


def _assert_overwrite_policy(paths: ArtDirectionArtifacts, overwrite: bool) -> None:
    existing = [
        p
        for p in [
            paths.art_direction_md,
            paths.reference_pack_json,
            paths.slide_visual_plan_json,
            paths.design_story_plan_json,
            paths.style_drafts_json,
            paths.layout_memory_json,
        ]
        if p.exists()
    ]
    if existing and not overwrite:
        joined = ", ".join(str(item) for item in existing)
        raise FileExistsError(
            "Art direction artifacts already exist and overwrite is disabled. "
            f"Use --overwrite to replace files: {joined}"
        )


def _load_style_route(project_dir: Path) -> dict[str, Any] | None:
    path = project_dir / "style_route.json"
    if not path.exists():
        return None
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return None
    return payload


def _load_existing_reference_pack(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return None
    usable_keys = {"mode", "references", "selected_templates", "primary_template", "reference_files"}
    if not usable_keys.intersection(payload.keys()):
        return None
    return payload


def _reference_pack_templates(reference_pack: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("references", "selected_templates"):
        value = reference_pack.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)][:3]
    return []


def _reference_pack_template_ids(reference_pack: dict[str, Any]) -> list[str]:
    items = _reference_pack_templates(reference_pack)
    ids = [str(item.get("template_key", "")).strip() for item in items if str(item.get("template_key", "")).strip()]
    if ids:
        return ids[:3]

    primary = reference_pack.get("primary_template")
    secondaries = reference_pack.get("secondary_templates")
    result: list[str] = []
    if isinstance(primary, str) and primary.strip():
        result.append(primary.strip())
    if isinstance(secondaries, list):
        result.extend(str(item).strip() for item in secondaries if str(item).strip())
    return _dedupe_templates(result)[:3]


def _reference_pack_files(reference_pack: dict[str, Any]) -> list[str]:
    files = reference_pack.get("reference_files")
    if isinstance(files, list):
        return [str(item) for item in files if str(item).strip()]
    refs: list[str] = []
    for item in _reference_pack_templates(reference_pack):
        raw = item.get("reference_files")
        if isinstance(raw, list):
            refs.extend(str(value) for value in raw if str(value).strip())
    return _dedupe_templates(refs)


def _template_reference_principles(reference_pack: dict[str, Any]) -> list[str]:
    if reference_pack.get("mode") == "free-design":
        return []
    principles: list[str] = []
    for item in _reference_pack_templates(reference_pack):
        template_key = str(item.get("template_key", "")).strip()
        if not template_key:
            continue
        use_as = item.get("use_as")
        strengths = item.get("visual_strengths")
        fragments: list[str] = []
        if isinstance(use_as, list) and use_as:
            fragments.append("use for " + ", ".join(str(value) for value in use_as[:3]))
        if isinstance(strengths, list) and strengths:
            fragments.append("borrow " + ", ".join(str(value) for value in strengths[:3]))
        if not fragments:
            fragments.append("use for rhythm, hierarchy, and tone")
        principles.append(f"{template_key}: {'; '.join(fragments)}")
    return principles[:3]


def _context_keywords(outline: str, design_values: dict[str, str], blueprint: dict[str, Any]) -> str:
    fields = [
        design_values.get("audience", ""),
        design_values.get("purpose", ""),
        design_values.get("style_objective", ""),
        design_values.get("keywords", ""),
        outline,
    ]
    slides = blueprint.get("slides")
    if isinstance(slides, list):
        for slide in slides:
            if not isinstance(slide, dict):
                continue
            fields.append(str(slide.get("title", "")))
            fields.append(str(slide.get("layout_tag", "")))
            fields.append(str(slide.get("narrative_intent", "")))
    return " ".join(fields)


def _resolve_templates(
    layouts: dict[str, Any],
    design_values: dict[str, str],
    context_keywords: str,
    cli_template: str | None,
    cli_secondary: list[str] | None,
    binding: dict[str, Any] | None,
    style_route: dict[str, Any] | None = None,
) -> tuple[str, list[str], str]:
    binding_template = _candidate_binding_template(binding)
    category, recommended = _match_template_category(
        " ".join(
            [
                design_values.get("audience", ""),
                design_values.get("purpose", ""),
                design_values.get("style_objective", ""),
                context_keywords,
            ]
        )
    )
    route_candidates: list[str] = []
    if isinstance(style_route, dict):
        raw_candidates = style_route.get("template_candidates")
        if isinstance(raw_candidates, list):
            for item in raw_candidates:
                if isinstance(item, dict):
                    route_value = item.get("template_id") or item.get("template")
                else:
                    route_value = item
                if isinstance(route_value, str) and route_value.strip():
                    route_candidates.append(route_value.strip())

    if cli_template:
        primary = _normalize_template_key(layouts, cli_template)
    elif route_candidates:
        primary = _normalize_template_key(layouts, route_candidates[0])
    elif binding_template:
        primary = _normalize_template_key(layouts, binding_template)
    else:
        primary = _normalize_template_key(layouts, recommended[0])

    if cli_secondary:
        secondary = [_normalize_template_key(layouts, item) for item in cli_secondary]
    elif route_candidates:
        secondary = [_normalize_template_key(layouts, item) for item in route_candidates[1:]]
    else:
        pool = [item for item in recommended if item != primary]
        if len(pool) < 2:
            pool.extend(item for item in DEFAULT_TEMPLATES if item != primary and item not in pool)
        secondary = pool[:2]

    combined = _dedupe_templates([primary] + secondary)[:3]
    primary = combined[0]
    secondary = combined[1:]
    return primary, secondary, category


def _build_reference_pack(
    primary: str,
    secondary: list[str],
    category: str,
    layouts_meta: dict[str, Any],
    reference_files: list[str],
    style_route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    primary_meta = layouts_meta.get(primary, {}) if isinstance(layouts_meta, dict) else {}
    tone = primary_meta.get("tone") if isinstance(primary_meta, dict) else None
    theme_mode = primary_meta.get("themeMode") if isinstance(primary_meta, dict) else None
    requires_style_drafts = (
        bool(style_route.get("requires_style_drafts", False))
        if isinstance(style_route, dict)
        else False
    )
    avoid = [
        "Avoid applying identical card-grid structure on all slides.",
        "Avoid fixed center-title treatment on consecutive pages.",
        "Avoid template pixel copying; adapt composition to narrative intent.",
    ]
    return {
        "primary_template": primary,
        "secondary_templates": secondary,
        "tone": tone or "Professional and narrative-driven",
        "themeMode": theme_mode or "Hybrid",
        "motifs": CATEGORY_MOTIFS.get(category, CATEGORY_MOTIFS["default"]),
        "avoid": avoid,
        "reference_files": reference_files,
        "style_profile": (style_route or {}).get("style_profile", category),
        "style_confidence": (style_route or {}).get("confidence"),
        "risk_flags": (style_route or {}).get("risk_flags", []),
        "requires_style_drafts": requires_style_drafts,
    }


def _attach_asset_semantic_mapping(
    reference_pack: dict[str, Any],
    *,
    context: str,
    category: str,
    blueprint: dict[str, Any],
    design_values: dict[str, str],
    style_route: dict[str, Any] | None,
) -> dict[str, Any]:
    style_profile = str(reference_pack.get("style_profile") or "")
    if not style_profile and isinstance(style_route, dict):
        style_profile = str(style_route.get("style_profile") or "")
    tone = str(reference_pack.get("tone") or "")
    style_objective = str(design_values.get("style_objective") or design_values.get("style") or "")
    mapping = _build_asset_semantic_mapping(
        context=context,
        category=category,
        blueprint=blueprint,
        style_profile=style_profile,
        tone=tone,
        style_objective=style_objective,
    )
    result = dict(reference_pack)
    result["asset_semantic_mapping"] = mapping
    return result


def _execution_tokens_from_style_route(style_route: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(style_route, dict):
        return {}
    profile_tokens = style_route.get("profile_tokens")
    if not isinstance(profile_tokens, dict):
        return {}
    hard_tokens = profile_tokens.get("hard_tokens")
    if isinstance(hard_tokens, dict):
        return dict(hard_tokens)
    return {}


def _merge_execution_tokens(
    defaults: dict[str, Any],
    explicit: dict[str, Any] | None,
) -> dict[str, Any]:
    result = dict(defaults)
    if not isinstance(explicit, dict):
        return result
    for key, value in explicit.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_execution_tokens(result[key], value)
        else:
            result[key] = value
    return result


def _build_enforcement_hints(
    *,
    layout_tag: str,
    execution_tokens: dict[str, Any] | None,
    anti_repeat_window: int,
) -> dict[str, Any]:
    hard = execution_tokens if isinstance(execution_tokens, dict) else {}
    raw_color_system = hard.get("color_system")
    raw_typography_system = hard.get("typography_system")
    raw_spacing_system = hard.get("spacing_system")
    raw_rhythm_rules = hard.get("rhythm_rules")
    color_system = raw_color_system if isinstance(raw_color_system, dict) else {}
    typography_system = raw_typography_system if isinstance(raw_typography_system, dict) else {}
    spacing_system = raw_spacing_system if isinstance(raw_spacing_system, dict) else {}
    rhythm_rules = raw_rhythm_rules if isinstance(raw_rhythm_rules, dict) else {}
    raw_title_zone = spacing_system.get("title_zone")
    title_zone = raw_title_zone if isinstance(raw_title_zone, dict) else {}
    raw_exclude = color_system.get("exclude_from_primary_count", ["#FFFFFF", "gray_scale"])
    exclude_values = raw_exclude if isinstance(raw_exclude, list) else ["#FFFFFF", "gray_scale"]
    return {
        "enabled": bool(hard),
        "max_primary_colors_per_slide": int(color_system.get("max_primary_colors_per_slide", 3)),
        "exclude_from_primary_count": [str(item) for item in exclude_values],
        "title_zone": {
            "y_min": int(title_zone.get("y_min", 60)),
            "y_max": int(title_zone.get("y_max", 140)),
            "max_lines": int(typography_system.get("title_max_lines", 2)),
        },
        "anti_repetition": {
            "window": int(max(1, anti_repeat_window)),
            "avoid_identical_layout_consecutive": bool(rhythm_rules.get("avoid_identical_layout_consecutive", True)),
            "avoid_equal_card_grid_as_default": bool(rhythm_rules.get("avoid_equal_card_grid_as_default", True)),
        },
        "core_conclusion_required": layout_tag in CORE_CONCLUSION_LAYOUTS,
    }


def _build_slide_visual_plan(
    blueprint: dict[str, Any],
    reference_files: list[str],
    *,
    reference_pack: dict[str, Any] | None = None,
    design_story_plan: dict[str, Any] | None = None,
    style_route: dict[str, Any] | None = None,
    execution_tokens: dict[str, Any] | None = None,
    prompt_catalog_path: Path | None = None,
    layout_exploration: dict[str, Any] | None = None,
    layout_memory_path: Path | None = None,
) -> dict[str, Any]:
    slides = blueprint.get("slides")
    if not isinstance(slides, list):
        raise ValueError("blueprint.json must contain slides array.")
    plan_slides: list[dict[str, Any]] = []
    total = len([s for s in slides if isinstance(s, dict)])
    visible_index = 0
    requires_style_drafts = (
        bool(style_route.get("requires_style_drafts", False))
        if isinstance(style_route, dict)
        else False
    )
    draft_candidates = []
    if isinstance(style_route, dict):
        raw = style_route.get("template_candidates")
        if isinstance(raw, list):
            for item in raw[:3]:
                if isinstance(item, dict):
                    tid = item.get("template_id") or item.get("template")
                else:
                    tid = item
                if isinstance(tid, str) and tid.strip():
                    draft_candidates.append(tid.strip())
    template_principles = _template_reference_principles(reference_pack or {})
    semantic_mapping = reference_pack.get("asset_semantic_mapping", {}) if isinstance(reference_pack, dict) else {}
    deck_profile = ""
    if isinstance(style_route, dict):
        deck_profile = str(style_route.get("style_profile") or "")
    if not deck_profile and isinstance(reference_pack, dict):
        deck_profile = str(reference_pack.get("style_profile") or "")
    if not deck_profile:
        deck_profile = "presentation"
    density_value = "medium"
    if isinstance(semantic_mapping, dict):
        density_value = str(semantic_mapping.get("information_density") or "medium")

    exploration = dict(DEFAULT_LAYOUT_EXPLORATION)
    if isinstance(layout_exploration, dict):
        exploration.update(layout_exploration)
    exploration_enabled = bool(exploration.get("enabled", True))
    anti_repeat_window = max(1, int(exploration.get("anti_repeat_window", 1) or 1))
    memory_path = layout_memory_path or Path(".") / "layout_memory.json"
    layout_memory = _load_layout_memory(memory_path)
    sequence = [str(item).strip() for item in layout_memory.get("selected_sequence", []) if str(item).strip()]
    selected_by_slide: dict[str, Any] = {}
    last_by_slide = layout_memory.get("last_selection_by_slide")
    if isinstance(last_by_slide, dict):
        selected_by_slide = dict(last_by_slide)
    slide_selection_records: list[dict[str, Any]] = []
    story_by_id: dict[int, dict[str, Any]] = {}
    if isinstance(design_story_plan, dict):
        for item in design_story_plan.get("slides", []):
            if not isinstance(item, dict):
                continue
            try:
                story_by_id[int(item.get("slide_id") or 0)] = item
            except (TypeError, ValueError):
                continue

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        visible_index += 1
        sid = slide.get("id")
        if not isinstance(sid, int):
            raise ValueError("blueprint.json contains slide without integer id.")
        layout_tag = str(slide.get("layout_tag", ""))
        semantic_plan = build_semantic_plan_row(slide)
        prompt_pattern = resolve_prompt_pattern(layout_tag, prompt_catalog_path)
        base_archetype = _archetype_for_layout(layout_tag)
        base_composition = _composition_intent_for_layout(layout_tag)
        base_variation = _variation_rule(layout_tag)
        alt_archetype, alt_composition, alt_variation = _alternative_archetype(layout_tag)
        if alt_archetype == base_archetype:
            alt_archetype = "offset editorial structure with dominant evidence lane"

        candidate_archetypes = [
            {
                "candidate_id": "A",
                "archetype": base_archetype,
                "composition_intent": base_composition,
                "variation_rule": base_variation,
                "family": _archetype_family(base_archetype, layout_tag),
            },
            {
                "candidate_id": "B",
                "archetype": alt_archetype,
                "composition_intent": alt_composition,
                "variation_rule": alt_variation,
                "family": _archetype_family(alt_archetype, layout_tag),
            },
        ]
        previous_window = sequence[-anti_repeat_window:] if anti_repeat_window > 0 else []
        previous_family = _archetype_family(previous_window[-1], layout_tag) if previous_window else ""
        semantic_intent = " ".join(
            (
                str(slide.get("narrative_intent", "")),
                str(semantic_plan.get("page_intent", "")),
                str(semantic_plan.get("page_type", "")),
                str(semantic_plan.get("narrative_role", "")),
            )
        )
        score_a = _score_candidate_for_slide(layout_tag, semantic_intent, base_archetype)
        score_b = _score_candidate_for_slide(layout_tag, semantic_intent, alt_archetype)
        selected_idx = 0
        selection_reason = "Primary candidate selected by content fit."
        rejected_reason = "Secondary candidate kept as fallback for variation."
        if exploration_enabled:
            if (
                previous_family
                and candidate_archetypes[0]["family"] == previous_family
                and candidate_archetypes[1]["family"] != previous_family
            ):
                selected_idx = 1
                selection_reason = (
                    f"Switched to candidate B to avoid repeating previous archetype family '{previous_family}'."
                )
                rejected_reason = "Candidate A rejected due to adjacent-page family repetition."
            elif score_b > score_a:
                selected_idx = 1
                selection_reason = "Candidate B selected by higher narrative fit score on this page."
                rejected_reason = "Candidate A retained but had lower content-fit score."
            else:
                rejected_reason = "Candidate B rejected because candidate A had higher or equal fit."
        selected = candidate_archetypes[selected_idx]
        rejected = candidate_archetypes[1 - selected_idx]
        scene_route = classify_slide_scene(slide, deck_profile=deck_profile)
        execution_policy = build_execution_policy(scene_route, deck_profile=deck_profile)
        visual_contract = build_visual_contract(
            slide=slide,
            route=scene_route,
            template_principles=template_principles,
        )
        acceptance_criteria = list(semantic_plan.get("acceptance_criteria") or [])
        if semantic_plan.get("visual_intent"):
            visual_contract["visual_intent"] = semantic_plan["visual_intent"]
        if semantic_plan.get("source_refs"):
            visual_contract["source_refs"] = list(semantic_plan["source_refs"])

        plan_item = {
            "slide_id": sid,
            "layout_tag": layout_tag,
            "page_type": semantic_plan["page_type"],
            "narrative_role": semantic_plan["narrative_role"],
            "page_intent": semantic_plan["page_intent"],
            "core_conclusion": semantic_plan["conclusion"],
            "conclusion_source": semantic_plan["conclusion_source"],
            "conclusion_confidence": semantic_plan["conclusion_confidence"],
            "supporting_claims": semantic_plan["supporting_claims"],
            "evidence": semantic_plan["evidence"],
            "source_refs": semantic_plan["source_refs"],
            "visual_intent": semantic_plan["visual_intent"],
            "acceptance_criteria": acceptance_criteria,
            "content_blocks": semantic_plan["content_blocks"],
            "business_visual_archetype": semantic_plan["visual_archetype"],
            "density_level": semantic_plan["density_level"],
            "editable_priority": semantic_plan["editable_priority"],
            "narrative_intent": str(slide.get("narrative_intent", "")).strip() or "support deck storyline",
            "visual_archetype": selected["archetype"],
            "composition_intent": selected["composition_intent"],
            "hierarchy_strategy": _hierarchy_strategy_for_layout(layout_tag),
            "rhythm_role": _rhythm_role(visible_index, total, layout_tag),
            "reference_slides": _slide_reference_files(reference_files, layout_tag),
            "template_reference_principles": template_principles,
            "variation_rule": selected["variation_rule"],
            "avoid": _avoid_list(layout_tag),
            "candidate_archetypes": candidate_archetypes,
            "selected_archetype": selected["archetype"],
            "selected_candidate_id": selected["candidate_id"],
            "selection_reason": selection_reason,
            "rejected_candidate_id": rejected["candidate_id"],
            "rejected_reason": rejected_reason,
            "asset_semantic_hint": {
                "preferred_asset_type": _asset_type_for_layout(layout_tag, density_value),
                "business_semantic": str(semantic_mapping.get("business_semantic", "")),
                "emotion_semantic": str(semantic_mapping.get("emotion_semantic", "")),
                "information_density": density_value,
            },
            "page_prompt_pattern": {
                "pattern_id": prompt_pattern.get("pattern_id"),
                "conclusion_formula": prompt_pattern.get("conclusion_formula"),
                "block_structure": prompt_pattern.get("block_structure"),
                "composition_cues": prompt_pattern.get("composition_cues"),
                "anti_patterns": prompt_pattern.get("anti_patterns", []),
            },
            "scene_route": {
                "scene_type": scene_route.scene_type,
                "generation_strategy": scene_route.generation_strategy,
                "deterministic_weight": scene_route.deterministic_weight,
                "executor_freedom": scene_route.executor_freedom,
                "reason": scene_route.reason,
            },
            "execution_policy": {
                "scene_type": execution_policy.scene_type,
                "generation_strategy": execution_policy.generation_strategy,
                "risk_level": execution_policy.risk_level,
                "required_loop": execution_policy.required_loop,
                "qa_strictness": execution_policy.qa_strictness,
                "expected_first_pass_rules": execution_policy.expected_first_pass_rules,
            },
            "visual_contract": visual_contract,
            "enforcement_hints": _build_enforcement_hints(
                layout_tag=layout_tag,
                execution_tokens=execution_tokens,
                anti_repeat_window=anti_repeat_window,
            ),
        }
        if requires_style_drafts and draft_candidates:
            plan_item["draft_routes"] = draft_candidates[:3]
        story = story_by_id.get(sid)
        if story:
            for key in (
                "design_move",
                "visual_grammar_id",
                "primary_grammar_id",
                "secondary_grammar_ids",
                "composite_design_move",
                "evidence_artifact_plan",
                "section_rhythm_role",
                "rewrite_policy",
                "dominant_object",
                "accent_terms",
                "secondary_content_policy",
                "reference_case_ids",
            ):
                if key in story:
                    plan_item[key] = story[key]
            plan_item["design_story"] = {
                key: story.get(key)
                for key in (
                    "memory_sentence",
                    "headline_rewrite",
                    "label_set",
                    "takeaway_line",
                    "compressed_blocks",
                    "content_selection",
                    "primary_grammar_id",
                    "secondary_grammar_ids",
                    "composite_design_move",
                    "evidence_artifact_plan",
                    "section_rhythm_role",
                    "avoid",
                    "variation_note",
                )
                if key in story
            }
        plan_slides.append(plan_item)
        sequence.append(selected["archetype"])
        selected_by_slide[str(sid)] = {
            "selected_archetype": selected["archetype"],
            "selected_candidate_id": selected["candidate_id"],
            "selection_reason": selection_reason,
            "rejected_candidate_id": rejected["candidate_id"],
            "rejected_reason": rejected_reason,
        }
        slide_selection_records.append(
            {
                "slide_id": sid,
                "selected_archetype": selected["archetype"],
                "selected_candidate_id": selected["candidate_id"],
                "selection_reason": selection_reason,
            }
        )
    layout_memory_payload = {
        "version": 1,
        "selected_sequence": sequence[-50:],
        "last_selection_by_slide": selected_by_slide,
        "last_updated_by": "generate_art_direction",
        "selection_records": slide_selection_records,
        "layout_exploration": {
            "enabled": exploration_enabled,
            "candidate_count": _candidate_count(exploration.get("candidate_count")),
            "anti_repeat_window": anti_repeat_window,
        },
    }
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(json.dumps(layout_memory_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "version": 1,
        "mode": "style_drafts" if requires_style_drafts else "single_route",
        "layout_exploration": {
            "enabled": exploration_enabled,
            "candidate_count": _candidate_count(exploration.get("candidate_count")),
            "anti_repeat_window": anti_repeat_window,
        },
        "slides": plan_slides,
    }


def _build_art_direction_markdown(
    primary: str,
    secondary: list[str],
    reference_pack: dict[str, Any],
    blueprint: dict[str, Any],
    *,
    style_route: dict[str, Any] | None = None,
) -> str:
    slides = [s for s in blueprint.get("slides", []) if isinstance(s, dict)]
    breakthrough, clarity = _breakthrough_and_clarity_slides(slides)
    motifs = reference_pack.get("motifs", [])
    motif_text = ", ".join(str(item) for item in motifs) if isinstance(motifs, list) else str(motifs)
    semantic_mapping = reference_pack.get("asset_semantic_mapping", {})
    business_semantic = (
        str(semantic_mapping.get("business_semantic", "n/a"))
        if isinstance(semantic_mapping, dict)
        else "n/a"
    )
    emotion_semantic = (
        str(semantic_mapping.get("emotion_semantic", "n/a"))
        if isinstance(semantic_mapping, dict)
        else "n/a"
    )
    density_semantic = (
        str(semantic_mapping.get("information_density", "n/a"))
        if isinstance(semantic_mapping, dict)
        else "n/a"
    )
    template_ids = _reference_pack_template_ids(reference_pack)
    is_free_design = reference_pack.get("mode") == "free-design"
    if is_free_design or not template_ids:
        template_line = "none (free-design)"
    else:
        template_line = ", ".join(template_ids)
    ref_files = reference_pack.get("reference_files", [])
    ref_lines = "\n".join(f"- {item}" for item in ref_files[:12]) if isinstance(ref_files, list) else "- (none)"
    if not ref_lines:
        ref_lines = "- (none)"
    principles = _template_reference_principles(reference_pack)
    principle_lines = (
        "\n".join(f"- {item}" for item in principles)
        if principles
        else "- (none; free-design uses art_direction only)"
    )
    breakthrough_text = ", ".join(str(x) for x in breakthrough) if breakthrough else "none"
    clarity_text = ", ".join(str(x) for x in clarity) if clarity else "none"
    route_conf = (style_route or {}).get("confidence")
    route_profile = (style_route or {}).get("style_profile")
    risk_flags = (style_route or {}).get("risk_flags", [])
    risk_text = ", ".join(str(item) for item in risk_flags) if isinstance(risk_flags, list) and risk_flags else "none"
    requires_drafts = bool((style_route or {}).get("requires_style_drafts", False))
    route_mode = "style_drafts" if requires_drafts else "single_route"
    return "\n".join(
        [
            "# Art Direction",
            "",
            "## Routing Snapshot",
            f"- style_profile: {route_profile or 'n/a'}",
            f"- confidence: {route_conf if route_conf is not None else 'n/a'}",
            f"- route_mode: {route_mode}",
            f"- risk_flags: {risk_text}",
            "- When route_mode is style_drafts, review style_drafts.json before full-deck execution.",
            "",
            "## Visual Metaphor",
            f"- Core metaphor: narrative evidence board with {motif_text}.",
            f"- Tone and mode: {reference_pack.get('tone')} | {reference_pack.get('themeMode')}.",
            "",
            "## Asset Semantic Mapping",
            f"- Business semantic: {business_semantic}",
            f"- Emotion semantic: {emotion_semantic}",
            f"- Information density: {density_semantic}",
            "- Asset selection order: business semantic -> emotion semantic -> density constraint.",
            "",
            "## Rhythm Strategy",
            "- Open with a decisive visual signal, escalate through contrast pages, then resolve with clean summary.",
            "- Keep deck-level pacing varied: hero pages, dense evidence pages, and reset pages must alternate.",
            "",
            "## Composition Principles",
            "- layout_tag is schema only; composition follows visual archetype and narrative intent.",
            "- Keep one dominant visual actor per key slide, then subordinate support details.",
            "- Preserve safe-area discipline while avoiding repetitive equal-width card grids.",
            "- Execution-grade hard tokens are stored in reference_pack.json.execution_tokens (if routed).",
            (
                "- Each slide must follow its page_prompt_pattern "
                "(conclusion formula + block structure + anti-pattern guardrails)."
            ),
            "",
            "## Taboos",
            "- Do not repeat identical left-right split across consecutive slides.",
            "- Do not use center-aligned title lockup as the default for all pages.",
            "- Do not copy template pixels; borrow rhythm, hierarchy, and tone.",
            "",
            "## Template References",
            f"- Selected templates: {template_line}",
            "- Borrow template principles, not slide layouts.",
            "- Principle anchors:",
            principle_lines,
            "- Reference files:",
            ref_lines,
            "",
            "## Page Strategy",
            f"- Visual breakthrough slides: {breakthrough_text}",
            f"- Clarity-priority slides: {clarity_text}",
            (
                "- Breakthrough pages may take asymmetry and stronger contrast; "
                "clarity pages prioritize readability and hierarchy."
            ),
            "",
        ]
    ) + "\n"


def _build_style_drafts_payload(
    *,
    style_route: dict[str, Any] | None,
    primary: str,
    secondaries: list[str],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    if isinstance(style_route, dict):
        raw = style_route.get("template_candidates")
        if isinstance(raw, list):
            for item in raw[:3]:
                if isinstance(item, dict):
                    template_id = item.get("template_id") or item.get("template")
                    score = item.get("score")
                    reason = item.get("reason")
                else:
                    template_id = item
                    score = None
                    reason = None
                if isinstance(template_id, str) and template_id.strip():
                    candidates.append(
                        {
                            "template_id": template_id.strip(),
                            "score": score,
                            "reason": reason or "style-route candidate",
                        }
                    )
    if not candidates:
        candidates = [
            {"template_id": item, "score": None, "reason": "fallback candidate"}
            for item in [primary] + secondaries
        ]
    candidates = candidates[:3]
    requires_style_drafts = bool((style_route or {}).get("requires_style_drafts", False))
    if not requires_style_drafts:
        selected = candidates[0]["template_id"] if candidates else primary
        return {
            "mode": "single_route",
            "selected_template": selected,
            "selected_draft_id": "draft-1",
            "drafts": [
                {
                    "draft_id": "draft-1",
                    "template_id": selected,
                    "thesis": "Proceed with the selected route.",
                }
            ],
        }

    drafts: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        template_id = str(candidate.get("template_id"))
        drafts.append(
            {
                "draft_id": f"draft-{index}",
                "template_id": template_id,
                "score": candidate.get("score"),
                "thesis": f"Explore a {template_id} execution route before committing deck-wide style.",
                "risk_mitigation": "Validate one representative core slide before full-deck generation.",
            }
        )
    return {
        "mode": "style_drafts",
        "selected_template": None,
        "selected_draft_id": None,
        "drafts": drafts,
    }


def generate_art_direction(
    project_dir: Path,
    *,
    overwrite: bool = False,
    template: str | None = None,
    secondary_templates: list[str] | None = None,
    layouts_index_path: Path | None = None,
    template_catalog_path: Path | None = None,
    prompt_catalog_path: Path | None = None,
    mode: str | None = None,
    layout_exploration_mode: str = "auto",
    candidate_count: int = 2,
) -> ArtDirectionArtifacts:
    project_dir = project_dir.resolve()
    if not project_dir.exists():
        raise FileNotFoundError(f"Project path not found: {project_dir}")

    outline_path = _required_file(project_dir, "outline.md")
    design_spec_path = _required_file(project_dir, "design_spec.md")
    blueprint_path = _required_file(project_dir, "blueprint.json")

    index_path = layouts_index_path.resolve() if layouts_index_path else DEFAULT_LAYOUTS_INDEX.resolve()
    if not index_path.exists():
        raise FileNotFoundError(f"Missing layouts index: {index_path}")

    artifacts = _target_paths(project_dir)
    _assert_overwrite_policy(artifacts, overwrite=overwrite)

    outline_text = outline_path.read_text(encoding="utf-8")
    design_values = _parse_design_spec(design_spec_path)
    blueprint = _read_json(blueprint_path)
    style_route = _load_style_route(project_dir)
    layout_exploration = _resolve_layout_exploration(
        style_route,
        layout_exploration_mode=layout_exploration_mode,
        candidate_count=candidate_count,
    )
    index_data = _read_json(index_path)
    layouts = index_data.get("layouts")
    if not isinstance(layouts, dict):
        raise ValueError(f"Invalid layouts index (missing layouts object): {index_path}")

    binding = _load_template_binding(project_dir)
    context = _context_keywords(outline_text, design_values, blueprint)
    existing_reference_pack = _load_existing_reference_pack(artifacts.reference_pack_json)
    primary, secondaries, category = _resolve_templates(
        layouts,
        design_values,
        context,
        cli_template=template,
        cli_secondary=secondary_templates,
        binding=binding,
        style_route=style_route,
    )

    reference_inventory = _collect_reference_inventory(primary, secondaries, project_dir, binding)
    reference_files, lazy_load_metrics = _lazy_load_reference_files(blueprint, reference_inventory)
    catalog_path = template_catalog_path.resolve() if template_catalog_path else DEFAULT_TEMPLATE_CATALOG.resolve()
    use_template_catalog = catalog_path.exists() and (
        template_catalog_path is not None
        or (project_dir / "clarification_brief.json").exists()
    )
    if existing_reference_pack is not None:
        reference_pack = existing_reference_pack
        template_ids = _reference_pack_template_ids(reference_pack)
        if template_ids:
            primary = template_ids[0]
            secondaries = template_ids[1:]
        elif reference_pack.get("mode") == "free-design":
            primary = "free-design"
            secondaries = []
        reference_files = _reference_pack_files(reference_pack)
        # Existing pack may come from old flow; backfill metrics from current lazy-load selection.
        loaded = len(reference_files)
        lazy_load_metrics = {
            "template_lookup_mode": str(reference_pack.get("template_lookup_mode") or TEMPLATE_LOOKUP_MODE),
            "template_reference_files_loaded": _to_int(
                reference_pack.get("template_reference_files_loaded", loaded),
                loaded,
            ),
            "template_reference_files_skipped": _to_int(reference_pack.get("template_reference_files_skipped", 0), 0),
            "template_lazy_load_hit_ratio": _to_float(
                reference_pack.get("template_lazy_load_hit_ratio", 1.0 if loaded else 0.0),
                1.0 if loaded else 0.0,
            ),
            "template_lazy_load_warning": bool(reference_pack.get("template_lazy_load_warning", False)),
            "template_lazy_load_warning_reason": reference_pack.get("template_lazy_load_warning_reason"),
        }
    elif use_template_catalog:
        reference_pack = build_reference_pack_from_catalog(
            project_dir,
            catalog_path,
            requested_mode=mode,
        )
        if isinstance(style_route, dict):
            reference_pack["style_profile"] = style_route.get("style_profile")
            reference_pack["style_confidence"] = style_route.get("confidence")
            reference_pack["risk_flags"] = style_route.get("risk_flags", [])
            reference_pack["requires_style_drafts"] = bool(style_route.get("requires_style_drafts", False))
        primary = reference_pack.get("primary_template") or "free-design"
        if not isinstance(primary, str):
            primary = "free-design"
        raw_secondaries = reference_pack.get("secondary_templates", [])
        secondaries = [str(item) for item in raw_secondaries] if isinstance(raw_secondaries, list) else []
        raw_reference_files = reference_pack.get("reference_files", [])
        reference_files = [str(item) for item in raw_reference_files] if isinstance(raw_reference_files, list) else []
        loaded = len(reference_files)
        lazy_load_metrics = {
            "template_lookup_mode": str(reference_pack.get("template_lookup_mode") or TEMPLATE_LOOKUP_MODE),
            "template_reference_files_loaded": _to_int(
                reference_pack.get("template_reference_files_loaded", loaded),
                loaded,
            ),
            "template_reference_files_skipped": _to_int(reference_pack.get("template_reference_files_skipped", 0), 0),
            "template_lazy_load_hit_ratio": _to_float(
                reference_pack.get("template_lazy_load_hit_ratio", 1.0 if loaded else 0.0),
                1.0 if loaded else 0.0,
            ),
            "template_lazy_load_warning": bool(reference_pack.get("template_lazy_load_warning", False)),
            "template_lazy_load_warning_reason": reference_pack.get("template_lazy_load_warning_reason"),
        }
    else:
        reference_pack = _build_reference_pack(
            primary,
            secondaries,
            category,
            layouts,
            reference_files,
            style_route=style_route,
        )
    reference_pack.update(lazy_load_metrics)
    reference_pack["layout_exploration"] = layout_exploration
    execution_tokens = _merge_execution_tokens(
        _execution_tokens_from_style_route(style_route),
        reference_pack.get("execution_tokens") if isinstance(reference_pack, dict) else None,
    )
    reference_pack["execution_tokens_version"] = 1
    reference_pack["execution_tokens"] = execution_tokens
    reference_pack = _attach_asset_semantic_mapping(
        reference_pack,
        context=context,
        category=category,
        blueprint=blueprint,
        design_values=design_values,
        style_route=style_route,
    )
    design_story_plan = build_design_story_plan(
        blueprint,
        reference_pack=reference_pack,
    )
    slide_visual_plan = _build_slide_visual_plan(
        blueprint,
        reference_files,
        reference_pack=reference_pack,
        design_story_plan=design_story_plan,
        style_route=style_route,
        execution_tokens=execution_tokens,
        prompt_catalog_path=prompt_catalog_path,
        layout_exploration=layout_exploration,
        layout_memory_path=artifacts.layout_memory_json,
    )
    art_direction_md = _build_art_direction_markdown(
        primary,
        secondaries,
        reference_pack,
        blueprint,
        style_route=style_route,
    )
    style_drafts = _build_style_drafts_payload(
        style_route=style_route,
        primary=primary,
        secondaries=secondaries,
    )

    artifacts.art_direction_md.write_text(art_direction_md, encoding="utf-8")
    artifacts.reference_pack_json.write_text(
        json.dumps(reference_pack, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts.slide_visual_plan_json.write_text(
        json.dumps(slide_visual_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts.design_story_plan_json.write_text(
        json.dumps(design_story_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts.style_drafts_json.write_text(
        json.dumps(style_drafts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifacts


def _parse_secondary_arg(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [item.strip() for item in value.split(",")]
    result = [item for item in parts if item]
    return result or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate art direction artifacts for a project.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output artifacts.")
    parser.add_argument("--template", help="Set primary template id explicitly.")
    parser.add_argument("--secondary", help="Comma-separated secondary template ids.")
    parser.add_argument("--template-catalog", type=Path, help="Path to template_catalog.json.")
    parser.add_argument("--prompt-catalog", type=Path, help="Path to prompt-pattern-catalog.json.")
    parser.add_argument(
        "--layout-exploration",
        choices=["on", "off", "auto"],
        default="auto",
        help="Control dual-candidate anti-homogenization policy in slide_visual_plan generation.",
    )
    parser.add_argument(
        "--candidate-count",
        type=int,
        default=2,
        help="Candidate archetype count per slide. Current implementation supports only 2.",
    )
    parser.add_argument(
        "--mode",
        choices=["hybrid", "template-guided", "free-design"],
        help=(
            "Template retrieval mode for reference_pack.json. "
            "Defaults to hybrid unless project context says otherwise."
        ),
    )
    args = parser.parse_args(argv)

    try:
        artifacts = generate_art_direction(
            args.project_dir,
            overwrite=args.overwrite,
            template=args.template,
            secondary_templates=_parse_secondary_arg(args.secondary),
            template_catalog_path=args.template_catalog,
            prompt_catalog_path=args.prompt_catalog,
            mode=args.mode,
            layout_exploration_mode=args.layout_exploration,
            candidate_count=args.candidate_count,
        )
    except Exception as exc:
        print(f"error: {exc}")
        return 1

    print("Art direction generated:")
    print(artifacts.art_direction_md)
    print(artifacts.reference_pack_json)
    print(artifacts.slide_visual_plan_json)
    print(artifacts.style_drafts_json)
    print(artifacts.layout_memory_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
