#!/usr/bin/env python3
"""Route style profile before art direction / executor stages."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_LAYOUTS_INDEX = SKILL_DIR / "ppt-ai-core" / "templates" / "layouts" / "layouts_index.json"

REQUIRED_CLARITY_FIELDS = ("audience", "decision_goal", "style_goal", "template_preference")
UNCLEAR_MARKERS = {
    "",
    "unknown",
    "tbd",
    "n/a",
    "na",
    "none",
    "unsure",
    "unclear",
    "to be decided",
    "pending",
}
DEFAULT_LAYOUT_EXPLORATION = {
    "enabled": True,
    "candidate_count": 2,
    "anti_repeat_window": 1,
    "enforce_in_modes": ["release-safe", "premium"],
}


@dataclass(frozen=True)
class StyleProfileSpec:
    name: str
    rationale: str
    composition_grammar: str
    rhythm_grammar: str
    typography_ladder: str
    taboo_patterns: tuple[str, ...]
    keywords: tuple[str, ...]
    template_affinity: tuple[str, ...]
    hard_tokens: dict[str, Any] = field(default_factory=dict)


STYLE_PROFILES: tuple[StyleProfileSpec, ...] = (
    StyleProfileSpec(
        name="proposal_consulting_wine_v2",
        rationale=(
            "Proposal-grade consulting narrative with disciplined wine accent, "
            "action-title hierarchy, and anti-homogenized rhythm."
        ),
        composition_grammar=(
            "Conclusion-first action title + structured evidence blocks; prefer "
            "asymmetric 60/40 or layer-split composition over equal card grids."
        ),
        rhythm_grammar=(
            "Dark/light reset cadence with no three consecutive identical page "
            "types; dense evidence pages must be followed by readability reset pages."
        ),
        typography_ladder="Cover 48-60/700, H1 26-30/700, H2 16-20/600, Body 13-15/400, Caption 10-12/400",
        taboo_patterns=(
            "dashed_frame_as_primary_structure",
            "equal_card_grid_default",
            "centered_body_copy",
            "decorative_icon_without_semantic_role",
            "overuse_fullpage_burgundy_background",
        ),
        keywords=(
            "proposal",
            "bid",
            "presale",
            "solution",
            "consulting",
            "tender",
            "project progress",
            "售前",
            "[CLIENT_NAME]",
            "解决方案",
            "项目进展",
            "汇报",
        ),
        template_affinity=("exhibit", "mckinsey", "consulting_classic"),
        hard_tokens={
            "token_set": "proposal_consulting_wine_v2",
            "scope": "consulting_profiles_only",
            "color_system": {
                "max_primary_colors_per_slide": 3,
                "exclude_from_primary_count": ["#FFFFFF", "gray_scale"],
                "primary_palette": ["#8B1A35", "#6B1228", "#1E3A5F"],
                "support_palette": ["#6B7280", "#4A6FA5", "#E8C4CC", "#F5F6F7"],
                "no_fullpage_primary_background": True,
            },
            "typography_system": {
                "body_min_font_px": 12,
                "title_max_lines": 2,
                "max_font_weights_per_slide": 2,
                "h1_range_px": [26, 30],
                "h2_range_px": [16, 20],
                "caption_range_px": [10, 12],
                "line_height": {"title": 1.2, "body": 1.5, "list": 1.6},
            },
            "spacing_system": {
                "safe_area": {"x": 56, "y": 44, "w": 1168, "h": 632},
                "title_zone": {"y_min": 44, "y_max": 112},
                "min_adjacent_spacing_px": 16,
                "module_spacing_px": [32, 48],
            },
            "rhythm_rules": {
                "max_consecutive_same_page_type": 2,
                "visual_reset_every_pages": [4, 6],
                "avoid_identical_layout_consecutive": True,
                "avoid_equal_card_grid_as_default": True,
            },
            "taboo_patterns": [
                "dashed_frame_as_primary_structure",
                "equal_card_grid_default",
                "centered_body_copy",
                "decorative_icon_without_semantic_role",
                "overuse_fullpage_burgundy_background",
            ],
            "qa_checks": [
                "max-primary-colors",
                "action-title-format",
                "no-dashed-frame-primary",
                "consecutive-homogeneous-rhythm",
            ],
        },
    ),
    StyleProfileSpec(
        name="executive_exhibit",
        rationale="Conclusion-first executive narrative with assertive evidence framing.",
        composition_grammar="Hero headline + takeaway bar + 2-3 evidence modules; asymmetry preferred.",
        rhythm_grammar="Open strong, alternate evidence peak and reset pages, close with decisive summary.",
        typography_ladder="H1 46/700, H2 30/600, Body 20/400, Meta 14/400",
        taboo_patterns=(
            "repetitive_equal_cards",
            "centered_title_every_page",
            "data_without_conclusion_label",
        ),
        keywords=("executive", "board", "strategy", "consulting", "decision", "exhibit"),
        template_affinity=("exhibit", "mckinsey", "consulting_classic"),
        hard_tokens={
            "token_set": "consulting_proposal_v1",
            "scope": "consulting_profiles_only",
            "color_system": {
                "max_primary_colors_per_slide": 3,
                "exclude_from_primary_count": ["#FFFFFF", "gray_scale"],
                "primary_palette": ["#003366", "#0066CC", "#E8500A"],
            },
            "typography_system": {
                "body_min_font_px": 16,
                "title_max_lines": 2,
                "max_font_weights_per_slide": 2,
            },
            "spacing_system": {
                "safe_area": {"x": 60, "y": 60, "w": 1160, "h": 600},
                "title_zone": {"y_min": 60, "y_max": 140},
                "min_adjacent_spacing_px": 16,
            },
            "rhythm_rules": {
                "max_consecutive_same_rhythm_role": 2,
                "avoid_identical_layout_consecutive": True,
                "avoid_equal_card_grid_as_default": True,
            },
            "taboo_patterns": [
                "repetitive_equal_cards",
                "centered_title_every_page",
                "data_without_conclusion_label",
            ],
            "qa_checks": [
                "max-primary-colors",
                "consecutive-homogeneous-rhythm",
                "core-conclusion-hierarchy",
            ],
        },
    ),
    StyleProfileSpec(
        name="luxury_finance",
        rationale="Premium finance narrative that emphasizes confidence, control, and downside clarity.",
        composition_grammar="Signal strip + high-contrast KPI stage + risk/reward paired evidence.",
        rhythm_grammar="Claim -> valuation evidence -> risk control -> confidence close.",
        typography_ladder="H1 44/700, H2 30/600, Body 19/400, Meta 13/400",
        taboo_patterns=(
            "rainbow_palette",
            "playful_iconography",
            "crowded_table_without_highlight",
        ),
        keywords=("finance", "investment", "valuation", "bank", "investor", "capital", "fund"),
        template_affinity=("cmb", "bank", "finance", "exhibit", "mckinsey"),
    ),
    StyleProfileSpec(
        name="engineering_blueprint",
        rationale="System-first engineering storytelling with modular logic and interface clarity.",
        composition_grammar="Layered system map + directional connectors + constrained annotation zones.",
        rhythm_grammar="Context map -> module deep-dive -> integration evidence -> rollout checkpoints.",
        typography_ladder="H1 40/700, H2 28/600, Body 18/400, Meta 13/400",
        taboo_patterns=(
            "floating_decorative_shapes",
            "ambiguous_connection_direction",
            "low_contrast_code_labels",
        ),
        keywords=("engineering", "system", "architecture", "infrastructure", "ops", "platform", "blueprint"),
        template_affinity=("ai_ops", "google_style", "anthropic"),
    ),
    StyleProfileSpec(
        name="ai_product_keynote",
        rationale="Product keynote narrative with memorable hero moments and clear proof blocks.",
        composition_grammar="Hero visual anchor + product promise + proof cards with one dominant metric.",
        rhythm_grammar="Problem framing -> feature reveal -> proof demo -> momentum close.",
        typography_ladder="H1 48/700, H2 30/600, Body 20/400, Meta 14/400",
        taboo_patterns=(
            "feature_wall_without_priority",
            "uniform_slide_density",
            "generic_stock_illustration_overuse",
        ),
        keywords=("ai", "product", "launch", "keynote", "feature", "roadmap", "demo"),
        template_affinity=("anthropic", "google_style", "ai_ops"),
    ),
    StyleProfileSpec(
        name="policy_institutional",
        rationale="Institutional policy communication with formality, traceability, and governance tone.",
        composition_grammar="Stable bilateral grid + policy rail + compliance evidence blocks.",
        rhythm_grammar="Mandate framing -> policy mechanism -> implementation controls -> governance outcome.",
        typography_ladder="H1 42/700, H2 29/600, Body 19/400, Meta 13/400",
        taboo_patterns=(
            "casual_tone_copy",
            "aggressive_color_contrast",
            "layout_jumps_without_section_rails",
        ),
        keywords=("policy", "institutional", "government", "regulation", "public", "state-owned", "compliance"),
        template_affinity=("government_blue", "government_red", "ai_ops"),
    ),
    StyleProfileSpec(
        name="editorial_report",
        rationale="Balanced editorial business report with high readability and moderate visual emphasis.",
        composition_grammar="Headline deck + sectional evidence blocks + disciplined whitespace cadence.",
        rhythm_grammar="Context -> analysis -> implication -> recommendation.",
        typography_ladder="H1 40/700, H2 28/600, Body 18/400, Meta 13/400",
        taboo_patterns=(
            "ornamental_background_noise",
            "overly_nested_bullets",
            "identical_split_layout_repetition",
        ),
        keywords=("report", "analysis", "business", "briefing", "summary", "review"),
        template_affinity=("mckinsey", "exhibit", "anthropic"),
    ),
    StyleProfileSpec(
        name="consulting_classic",
        rationale=(
            "SIE consulting narrative with decisive action titles, structured evidence, "
            "and readable light-content pages."
        ),
        composition_grammar=(
            "Conclusion-first action title + evidence modules; prefer asymmetric splits, "
            "table-first data pages, and clear chapter resets."
        ),
        rhythm_grammar=(
            "Alternate dark/light chapter resets, evidence peaks, and readability pages; "
            "avoid repeated equal-card grids."
        ),
        typography_ladder="Cover 48-60/700, H1 28-32/700, H2 18-22/600, Body 14-16/400, Caption 11-12/400",
        taboo_patterns=(
            "dashed_frame_as_primary_structure",
            "equal_card_grid_default",
            "centered_body_copy",
            "decorative_icon_without_semantic_role",
        ),
        keywords=(
            "咨询风格",
            "consulting classic",
            "consulting",
            "strategy",
            "recommendation",
            "proposal",
            "solution",
        ),
        template_affinity=("consulting_classic", "exhibit", "mckinsey"),
        hard_tokens={
            "token_set": "consulting_classic",
            "scope": "consulting_profiles_only",
            "style_token_source": "design_spec.consulting_classic",
            "structure_system": {
                "prefer_asymmetric_split": True,
                "table_first_data_pages": True,
                "chapter_reset_required": True,
            },
            "typography_system": {
                "body_min_font_px": 14,
                "title_max_lines": 2,
                "max_font_weights_per_slide": 2,
            },
            "rhythm_rules": {
                "max_consecutive_same_rhythm_role": 2,
                "avoid_identical_layout_consecutive": True,
                "avoid_equal_card_grid_as_default": True,
            },
            "taboo_patterns": [
                "dashed_frame_as_primary_structure",
                "equal_card_grid_default",
                "centered_body_copy",
                "decorative_icon_without_semantic_role",
            ],
            "qa_checks": [
                "action-title-format",
                "table-context-labels",
                "consecutive-homogeneous-rhythm",
                "no-dashed-frame-primary",
            ],
        },
    ),
)

DEFAULT_PROFILE = next(item for item in STYLE_PROFILES if item.name == "editorial_report")
PROFILE_BY_NAME = {item.name: item for item in STYLE_PROFILES}


def _required_file(project_dir: Path, name: str) -> Path:
    path = project_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"Invalid JSON file: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def _parse_design_spec(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _normalized(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _is_unclear(value: Any) -> bool:
    token = _normalized(value)
    return token in UNCLEAR_MARKERS or token.startswith("unknown")


def _parse_assumptions(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _validate_clarification_gate(clarification: dict[str, Any]) -> tuple[list[str], bool]:
    autonomous_mode = bool(clarification.get("autonomous_mode", False))
    assumptions = _parse_assumptions(clarification.get("assumptions"))
    unclear_fields = [field for field in REQUIRED_CLARITY_FIELDS if _is_unclear(clarification.get(field))]
    if not unclear_fields:
        return [], autonomous_mode
    if autonomous_mode and assumptions:
        return unclear_fields, autonomous_mode
    if autonomous_mode and not assumptions:
        raise ValueError(
            "State 1 clarification gate failed: autonomous_mode=true requires non-empty assumptions "
            f"when fields are unclear ({', '.join(unclear_fields)})."
        )
    raise ValueError(
        "State 1 clarification gate failed: unresolved fields block State 2 "
        f"({', '.join(unclear_fields)})."
    )


def _resolve_style_profile(context: str) -> StyleProfileSpec:
    lowered = context.lower()
    best: StyleProfileSpec | None = None
    best_hits = 0
    for profile in STYLE_PROFILES:
        hits = sum(1 for keyword in profile.keywords if keyword in lowered)
        if hits > best_hits:
            best = profile
            best_hits = hits
    return best if best is not None else DEFAULT_PROFILE


def _score_template(
    template_id: str,
    *,
    context: str,
    profile: StyleProfileSpec,
    template_preference: str,
) -> tuple[float, list[str]]:
    score = 0.35
    reasons: list[str] = []
    tid = template_id.lower()
    ctx = context.lower()
    pref = template_preference.lower()

    if pref and (tid in pref or pref in tid):
        score += 0.36
        reasons.append("matches template preference")

    affinity_hits = [token for token in profile.template_affinity if token in tid]
    if affinity_hits:
        score += min(0.26, 0.12 + 0.05 * len(affinity_hits))
        reasons.append("fits profile affinity")

    if profile.name == "executive_exhibit" and any(token in ctx for token in ("conclusion", "decision", "board")):
        score += 0.08
        reasons.append("context supports executive exhibit narrative")
    if profile.name == "proposal_consulting_wine_v2" and any(
        token in ctx for token in ("proposal", "bid", "presale", "solution", "tender")
    ):
        score += 0.08
        reasons.append("context supports proposal consulting narrative")
    if profile.name == "engineering_blueprint" and any(token in ctx for token in ("architecture", "system", "ops")):
        score += 0.08
        reasons.append("context supports engineering blueprint narrative")
    if profile.name == "luxury_finance" and any(token in ctx for token in ("finance", "investment", "valuation")):
        score += 0.08
        reasons.append("context supports finance narrative")

    if not reasons:
        reasons.append("fallback candidate")
    return score, reasons


def _build_template_candidates(
    layouts: dict[str, Any],
    *,
    context: str,
    profile: StyleProfileSpec,
    template_preference: str,
    seed_text: str = "",
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    seed = (seed_text or "").strip().lower()
    for template_id in sorted(layouts):
        score, reasons = _score_template(
            template_id,
            context=context,
            profile=profile,
            template_preference=template_preference,
        )
        tie_hash = hashlib.sha1(f"{seed}|{template_id}".encode("utf-8")).hexdigest()[:8]
        tie_priority = int(tie_hash, 16) / 0xFFFFFFFF
        scored.append(
            {
                "template_id": template_id,
                "score": round(min(0.99, score), 3),
                "reason": "; ".join(reasons),
                "_tie_priority": tie_priority,
            }
        )
    scored.sort(key=lambda item: (float(item["score"]), float(item["_tie_priority"])), reverse=True)
    for item in scored:
        item.pop("_tie_priority", None)
    top = scored[:3]
    if len(top) < 3 and scored:
        for item in scored:
            if item in top:
                continue
            top.append(item)
            if len(top) == 3:
                break
    return top


def _route_confidence(
    clarification: dict[str, Any],
    unclear_fields: list[str],
    template_candidates: list[dict[str, Any]],
    *,
    slide_count: int = 0,
) -> float:
    base = 0.58
    if not unclear_fields:
        base += 0.18
    else:
        base -= 0.12 * min(2, len(unclear_fields))
    top_score = float(template_candidates[0]["score"]) if template_candidates else 0.0
    spread = 0.0
    if len(template_candidates) >= 2:
        spread = top_score - float(template_candidates[1]["score"])
    if spread >= 0.18:
        base += 0.1
    elif spread <= 0.05:
        base -= 0.04 if 0 < slide_count <= 3 else 0.08
    if bool(clarification.get("autonomous_mode", False)):
        base -= 0.03 if 0 < slide_count <= 3 else 0.08
    if 0 < slide_count <= 3:
        base += 0.04
    assumptions = _parse_assumptions(clarification.get("assumptions"))
    if assumptions:
        base += 0.04
    return max(0.3, min(0.95, round(base, 2)))


def _profile_tokens(profile: StyleProfileSpec) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "composition_grammar": profile.composition_grammar,
        "rhythm_grammar": profile.rhythm_grammar,
        "typography_ladder": profile.typography_ladder,
        "taboo_patterns": list(profile.taboo_patterns),
    }
    if isinstance(profile.hard_tokens, dict) and profile.hard_tokens:
        payload["hard_tokens"] = profile.hard_tokens
    return payload


def generate_style_route(
    project_dir: Path,
    *,
    layouts_index_path: Path | None = None,
    overwrite: bool = False,
    confidence_draft_threshold: float = 0.7,
) -> Path:
    project_dir = project_dir.resolve()
    if not project_dir.exists():
        raise FileNotFoundError(f"Project path not found: {project_dir}")

    design_spec = _required_file(project_dir, "design_spec.md")
    outline = _required_file(project_dir, "outline.md")
    clarification_path = _required_file(project_dir, "clarification_brief.json")
    clarification = _read_json(clarification_path)

    unclear_fields, autonomous_mode = _validate_clarification_gate(clarification)
    design_values = _parse_design_spec(design_spec)
    outline_text = outline.read_text(encoding="utf-8")
    blueprint = project_dir / "blueprint.json"
    slide_count = 0
    if blueprint.exists():
        blueprint_payload = _read_json(blueprint)
        slides = blueprint_payload.get("slides")
        slide_count = len(slides) if isinstance(slides, list) else 0

    index_path = layouts_index_path.resolve() if layouts_index_path else DEFAULT_LAYOUTS_INDEX.resolve()
    index_payload = _read_json(index_path)
    layouts = index_payload.get("layouts")
    if not isinstance(layouts, dict) or not layouts:
        raise ValueError(f"Invalid layouts index (missing layouts object): {index_path}")

    context = " ".join(
        [
            str(clarification.get("audience", "")),
            str(clarification.get("decision_goal", "")),
            str(clarification.get("style_goal", "")),
            str(clarification.get("template_preference", "")),
            design_values.get("purpose", ""),
            outline_text,
        ]
    )
    explicit_style_profile = _normalized(design_values.get("style_profile"))
    profile = PROFILE_BY_NAME.get(explicit_style_profile, _resolve_style_profile(context))

    template_candidates = _build_template_candidates(
        layouts,
        context=context,
        profile=profile,
        template_preference=str(clarification.get("template_preference", "")),
        seed_text=project_dir.name,
    )
    confidence = _route_confidence(
        clarification,
        unclear_fields,
        template_candidates,
        slide_count=slide_count,
    )
    requires_style_drafts = confidence < confidence_draft_threshold

    risk_flags: list[str] = []
    if unclear_fields:
        risk_flags.extend(f"assumption-required:{field}" for field in unclear_fields)
    if autonomous_mode:
        risk_flags.append("autonomous-mode")
    if requires_style_drafts:
        risk_flags.append("route-low-confidence")
    if (
        len(template_candidates) >= 2
        and abs(
            float(template_candidates[0]["score"])
            - float(template_candidates[1]["score"])
        )
        <= 0.05
    ):
        risk_flags.append("template-ranking-ambiguous")
    if slide_count >= 12:
        risk_flags.append("long-deck-rhythm-risk")

    payload = {
        "style_profile": profile.name,
        "profile_rationale": profile.rationale,
        "profile_tokens": _profile_tokens(profile),
        "confidence": confidence,
        "template_candidates": template_candidates[:3],
        "risk_flags": risk_flags,
        "requires_style_drafts": requires_style_drafts,
        "layout_exploration": dict(DEFAULT_LAYOUT_EXPLORATION),
        "clarification_gate": {
            "status": "pass",
            "autonomous_mode": autonomous_mode,
            "unclear_fields": unclear_fields,
            "assumptions_count": len(_parse_assumptions(clarification.get("assumptions"))),
        },
        "state": {
            "blueprint_slide_count": slide_count,
            "source_files": {
                "clarification_brief": str(clarification_path),
                "design_spec": str(design_spec),
                "outline": str(outline),
                "blueprint": str(blueprint) if blueprint.exists() else None,
            },
        },
    }

    out_path = project_dir / "style_route.json"
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"{out_path} already exists; use --overwrite to replace it.")
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate style route and confidence profile for a project.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing style_route.json.")
    parser.add_argument(
        "--confidence-draft-threshold",
        type=float,
        default=0.7,
        help="If confidence is lower than this threshold, requires_style_drafts is enabled.",
    )
    args = parser.parse_args(argv)
    try:
        route_path = generate_style_route(
            args.project_dir,
            overwrite=args.overwrite,
            confidence_draft_threshold=args.confidence_draft_threshold,
        )
    except Exception as exc:
        print(f"error: {exc}")
        return 1
    print(route_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
