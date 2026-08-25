from __future__ import annotations

from typing import Any

from pipeline.narrative_composition import (
    analyze_slide_narrative,
    build_composition_candidates,
    select_composition_candidate,
)
from pipeline.scene_router import SceneRoute

REQUIRED_CONTRACT_KEYS = {
    "scene_type",
    "generation_strategy",
    "focal_point",
    "primary_read_path",
    "composition_grammar",
    "hierarchy_ladder",
    "density_budget",
    "whitespace_target",
    "template_inheritance",
    "anti_patterns",
    "critic_checks",
    "layout_intent",
    "bbox_budget",
    "text_budget",
    "deterministic_scaffold",
    "must_avoid",
    "pre_authoring_checks",
}


def _hierarchy_ladder(scene_type: str) -> dict[str, str]:
    if scene_type == "cover_brand":
        return {
            "hero": "48-56px",
            "module_title": "24-28px",
            "body": "16-18px",
            "caption": "12-13px",
        }
    return {
        "hero": "40-46px",
        "module_title": "22-26px",
        "body": "16-19px",
        "caption": "12-14px",
    }


def _density_budget(scene_type: str) -> dict[str, Any]:
    if scene_type == "core_orbit_relationship":
        return {
            "max_core_nodes": 1,
            "max_satellite_nodes": 6,
            "max_primary_claims": 1,
            "max_card_count": 7,
            "max_body_chars": 240,
            "compression_rule": "keep one core summary and shorten satellite support text before shrinking labels",
        }
    if scene_type == "data_insight":
        return {
            "max_primary_claims": 2,
            "max_card_count": 3,
            "max_body_chars": 180,
            "max_chart_count": 1,
            "compression_rule": "turn supporting prose into chart annotations before shrinking labels",
        }
    if scene_type in {"proposal_proof", "executive_summary"}:
        return {
            "max_primary_claims": 3,
            "max_card_count": 4,
            "max_body_chars": 220,
            "compression_rule": "drop tertiary detail before shrinking key text",
        }
    if scene_type == "cover_brand":
        return {
            "max_primary_claims": 1,
            "max_card_count": 1,
            "max_body_chars": 80,
            "compression_rule": "drop non-essential metadata before shrinking hero line",
        }
    if scene_type == "risk_shift_control":
        return {
            "max_primary_claims": 3,
            "max_card_count": 4,
            "max_body_chars": 260,
            "compression_rule": "compress supporting risk details before weakening the before-after gate movement",
        }
    if scene_type == "ops_closure_dashboard":
        return {
            "max_primary_claims": 3,
            "max_card_count": 4,
            "max_body_chars": 240,
            "compression_rule": "keep monitoring metrics compact and preserve closure matrix readability",
        }
    return {
        "max_primary_claims": 4,
        "max_card_count": 5,
        "max_body_chars": 260,
        "compression_rule": "split overloaded content before shrinking below body floor",
    }


def _layout_intent(scene_type: str) -> str:
    mapping = {
        "core_orbit_relationship": "core_orbit_relationship",
        "proposal_proof": "proof_map",
        "executive_summary": "dominant_takeaway",
        "data_insight": "dominant_chart",
        "pain_point": "pain_left_right",
        "roadmap": "timeline_spine",
        "architecture_flow": "node_flow_map",
        "risk_shift_control": "before_after_control_shift",
        "ops_closure_dashboard": "dashboard_to_closure_matrix",
        "cover_brand": "hero_brand_signal",
        "comparison": "decision_matrix",
        "general_explainer": "dominant_message",
    }
    return mapping.get(scene_type, "dominant_message")


def _bbox_budget(scene_type: str) -> dict[str, Any]:
    if scene_type == "cover_brand":
        return {
            "safe_area": "presentation",
            "hero_region": {"x_ratio": [0.08, 0.92], "y_ratio": [0.14, 0.52]},
            "content_region": {"x_ratio": [0.08, 0.72], "y_ratio": [0.54, 0.82]},
            "reserved_whitespace_ratio": 0.34,
        }
    return {
        "safe_area": "presentation",
        "hero_region": {"x_ratio": [0.05, 0.95], "y_ratio": [0.10, 0.28]},
        "content_region": {"x_ratio": [0.08, 0.92], "y_ratio": [0.32, 0.84]},
        "reserved_whitespace_ratio": 0.28,
    }


def _text_budget(scene_type: str) -> dict[str, Any]:
    density = _density_budget(scene_type)
    return {
        "max_primary_claims": density.get("max_primary_claims", 3),
        "max_body_chars": density.get("max_body_chars", 220),
        "min_body_font_px": 16,
        "max_text_nodes": 18 if scene_type != "cover_brand" else 8,
        "copyfit_policy": "last_resort_only",
    }


def _deterministic_scaffold(scene_type: str, strategy: str) -> dict[str, Any]:
    mapping = {
        "core_orbit_relationship": ("core_orbit", ["core_node", "satellite_nodes", "relationship_edges"]),
        "data_insight": ("chart_anchor", ["insight_title", "dominant_chart", "annotation_rail"]),
        "roadmap": ("timeline_spine", ["phase_axis", "current_phase", "dependency_lane"]),
        "architecture_flow": ("node_flow", ["core_node", "flow_edges", "boundary_labels"]),
        "comparison": ("decision_matrix", ["comparison_axis", "option_regions", "recommendation_marker"]),
        "proposal_proof": ("proof_map", ["dominant_proof", "evidence_lane", "risk_reducer"]),
        "pain_point": ("pain_left_right", ["pain_column", "impact_column", "process_strip", "takeaway_bar"]),
        "risk_shift_control": (
            "control_gate_shift",
            ["traditional_response", "process_warning", "risk_matrix", "value_strip"],
        ),
        "ops_closure_dashboard": ("closure_dashboard", ["input_foundation", "monitoring_signals", "decision_closure"]),
    }
    scaffold_type, regions = mapping.get(scene_type, ("freeform", []))
    if strategy == "executor_free_svg" and scene_type not in {"proposal_proof"}:
        scaffold_type, regions = ("freeform", [])
    return {"type": scaffold_type, "required_regions": regions}


def _focal_point(scene_type: str) -> str:
    mapping = {
        "core_orbit_relationship": "单一核心节点",
        "proposal_proof": "top action title plus central proof object",
        "executive_summary": "decision headline plus one dominant takeaway block",
        "data_insight": "insight headline anchored to a dominant chart object",
        "pain_point": "pain-to-impact bridge with a compact audit-response chain",
        "roadmap": "timeline spine with one highlighted phase pivot",
        "architecture_flow": "system map core node with directional flow emphasis",
        "risk_shift_control": (
            "visible shift from lagging response to process warning, backed by a risk evidence matrix"
        ),
        "ops_closure_dashboard": (
            "remediation closure matrix as the decision area, supported by compact monitoring signals"
        ),
        "cover_brand": "hero title and signature brand visual",
        "comparison": "decision axis with one clearly favored option",
        "general_explainer": "single dominant message block",
    }
    return mapping.get(scene_type, "single dominant message block")


def _primary_read_path(scene_type: str) -> list[str]:
    mapping = {
        "core_orbit_relationship": ["title", "core_node", "satellite_nodes", "takeaway"],
        "proposal_proof": ["action_title", "dominant_proof", "supporting_evidence"],
        "executive_summary": ["decision_title", "key_takeaway", "supporting_proof"],
        "data_insight": ["insight_title", "dominant_chart", "callout_annotations"],
        "pain_point": ["action_title", "process_strip", "pain_column", "impact_column", "takeaway_bar"],
        "roadmap": ["phase_title", "timeline_spine", "dependency_notes"],
        "architecture_flow": ["system_title", "core_node", "flow_edges"],
        "risk_shift_control": ["action_title", "process_warning", "gate_shift_arrow", "risk_matrix", "value_strip"],
        "ops_closure_dashboard": ["action_title", "indicator_foundation", "monitoring_signals", "closure_matrix"],
        "cover_brand": ["hero_title", "hero_visual", "supporting_subtitle"],
        "comparison": ["decision_title", "comparison_axis", "recommended_option"],
        "general_explainer": ["action_title", "dominant_block", "supporting_notes"],
    }
    return mapping.get(scene_type, ["action_title", "dominant_block", "supporting_notes"])


def _composition_grammar(scene_type: str) -> str:
    mapping = {
        "core_orbit_relationship": (
            "single central core node with symmetric supporting satellite nodes "
            "and explicit relationship edges"
        ),
        "proposal_proof": "dominant center proof object with two subordinate evidence lanes",
        "executive_summary": "conclusion-first title rail with one dominant claim and quiet evidence strip",
        "data_insight": "single chart anchor with concise annotation rail and no competing cards",
        "pain_point": "left pain stack + right impact stack; center/top process strip; bottom takeaway bar",
        "roadmap": "single timeline axis with asymmetric milestone emphasis",
        "architecture_flow": "layered node-edge map with clear start-to-end directionality",
        "risk_shift_control": (
            "before-after control shift with process warning visually stronger than lagging response "
            "and a supporting evidence matrix"
        ),
        "ops_closure_dashboard": (
            "operating dashboard where monitoring blocks feed a dominant remediation closure matrix"
        ),
        "cover_brand": "single concept cover composition with large negative space",
        "comparison": "two-sided comparison anchored by a decisive recommendation marker",
    }
    return mapping.get(scene_type, "one dominant message with clearly demoted support")


def _scene_anti_patterns(scene_type: str) -> list[str]:
    base = ["same-weight modules", "paragraph-heavy cards"]
    if scene_type == "core_orbit_relationship":
        base.extend(["多核心", "无连接", "环绕节点全部挤在一侧", "核心与环绕节点等权", "普通卡片网格伪装成关系图"])
    if scene_type in {"proposal_proof", "executive_summary"}:
        base.extend(["equal 6-card grid", "title plus three equal cards"])
    if scene_type == "pain_point":
        base.extend(["process diagram dominating the page", "over-detailed compliance text as focal point"])
    if scene_type == "data_insight":
        base.extend(
            [
                "default chart without insight title",
                "legend hunting before conclusion",
                "chart labels below readability floor",
            ]
        )
    if scene_type == "cover_brand":
        base.extend(["dashboard opener", "generic KPI strip", "normal content-slide shell"])
    if scene_type == "comparison":
        base.extend(["symmetrical undecidable comparison", "equal visual emphasis for all options"])
    if scene_type == "risk_shift_control":
        base.extend(
            [
                "four equal modules",
                "plain function list",
                "risk table without before-after movement",
                "traditional response card visually stronger than process warning",
            ]
        )
    if scene_type == "ops_closure_dashboard":
        base.extend(
            [
                "four equal modules",
                "plain function list",
                "closure matrix treated as a footnote",
                "monitoring cards overpower the remediation decision area",
            ]
        )
    return sorted(set(base))


def _hierarchy_rule(scene_type: str) -> str:
    mapping = {
        "risk_shift_control": (
            "Process warning and front-moved risk detection must read stronger "
            "than traditional lagging response."
        ),
        "ops_closure_dashboard": "Closure or control area must read stronger than supporting monitoring blocks.",
    }
    return mapping.get(scene_type, "The focal point must be visually stronger than supporting evidence.")


def _executor_freedom(scene_type: str) -> list[str]:
    if scene_type == "risk_shift_control":
        return [
            "May use a dark stage or light consulting board as long as the before-after movement is unmistakable.",
            "May choose table, matrix, or compact tag board for risk evidence without turning it into the focal point.",
            "May vary exact module geometry as long as process warning remains visually dominant.",
        ]
    if scene_type == "ops_closure_dashboard":
        return [
            "May use dark stage or light consulting board.",
            "May vary exact module geometry as long as read path holds.",
            "May draw monitoring signals as cards, chips, or mini-panels if the closure matrix stays dominant.",
        ]
    return [
        "May vary exact module geometry as long as the visual contract and read path hold.",
    ]


def _selected_reason(selected: dict[str, str], scene_type: str) -> str:
    if not selected:
        return ""
    if scene_type == "risk_shift_control":
        return "Best fit for a bid consulting page where the evaluator must see risk identification move forward."
    if scene_type == "ops_closure_dashboard":
        return "Best fit for bid consulting onepager with metrics plus remediation closure."
    return f"Selected for strongest match to {scene_type} narrative."


def _must_avoid(scene_type: str) -> list[str]:
    items = ["equal-weight card grid", "title-only hierarchy", "shrinking conclusion text to pass lint"]
    items.extend(_scene_anti_patterns(scene_type))
    return sorted(set(items))


def _core_orbit_primary_message(slide: dict[str, Any]) -> str:
    content = slide.get("content")
    if not isinstance(content, dict):
        return ""
    return str(content.get("summary") or "").strip()


def _content_roles(scene_type: str, narrative_roles: Any) -> dict[str, Any]:
    if scene_type == "core_orbit_relationship":
        return {
            "core": "core_node",
            "satellites": "satellite_nodes",
            "relationships": "relationship_edges",
        }
    return dict(narrative_roles or {})


def build_visual_contract(
    *,
    slide: dict[str, Any],
    route: SceneRoute,
    template_principles: list[str] | None = None,
) -> dict[str, Any]:
    inheritance = [str(item).strip() for item in (template_principles or []) if str(item).strip()][:5]
    narrative = analyze_slide_narrative(slide, deck_profile=route.scene_type)
    candidates = build_composition_candidates(narrative, route)
    selected = select_composition_candidate(candidates)
    anti_patterns = sorted(
        set(
            _scene_anti_patterns(route.scene_type)
            + [str(item) for item in narrative.get("anti_patterns", []) if str(item).strip()]
        )
    )
    return {
        "scene_type": route.scene_type,
        "generation_strategy": route.generation_strategy,
        "deterministic_weight": route.deterministic_weight,
        "executor_freedom": route.executor_freedom,
        "route_reason": route.reason,
        "focal_point": _focal_point(route.scene_type),
        "primary_read_path": _primary_read_path(route.scene_type),
        "composition_grammar": _composition_grammar(route.scene_type),
        "hierarchy_ladder": _hierarchy_ladder(route.scene_type),
        "density_budget": _density_budget(route.scene_type),
        "layout_intent": _layout_intent(route.scene_type),
        "bbox_budget": _bbox_budget(route.scene_type),
        "text_budget": _text_budget(route.scene_type),
        "deterministic_scaffold": _deterministic_scaffold(route.scene_type, route.generation_strategy),
        "whitespace_target": ">= 28% perceived open space",
        "template_inheritance": inheritance,
        "anti_patterns": anti_patterns,
        "must_avoid": _must_avoid(route.scene_type),
        "pre_authoring_checks": [
            "choose focal point before writing SVG",
            "compress content before copyfit",
            "reserve whitespace before adding decoration",
        ],
        "critic_checks": [
            "dominant focal point exists",
            "primary read path is visible in 3 seconds",
            "density budget is respected before copyfit",
            "anti-patterns are not visible in final SVG",
        ],
        "relationship_model": (
            "satellites_support_core"
            if route.scene_type == "core_orbit_relationship"
            else str(narrative.get("relationship_model") or "supporting_evidence")
        ),
        "primary_message": (
            _core_orbit_primary_message(slide)
            if route.scene_type == "core_orbit_relationship"
            else str(narrative.get("primary_message") or "")
        ),
        "content_roles": _content_roles(route.scene_type, narrative.get("content_roles")),
        "composition_candidates": candidates,
        "selected_composition": str(selected.get("id") or ""),
        "selected_composition_reason": _selected_reason(selected, route.scene_type),
        "hierarchy_rule": _hierarchy_rule(route.scene_type),
    }


def validate_visual_contract_shape(contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    missing = sorted(REQUIRED_CONTRACT_KEYS - set(contract.keys()))
    if missing:
        issues.append(f"missing keys: {missing}")
    if not isinstance(contract.get("primary_read_path"), list) or not contract.get("primary_read_path"):
        issues.append("primary_read_path must be a non-empty list")
    if not isinstance(contract.get("density_budget"), dict):
        issues.append("density_budget must be an object")
    if not isinstance(contract.get("bbox_budget"), dict):
        issues.append("bbox_budget must be an object")
    if not isinstance(contract.get("text_budget"), dict):
        issues.append("text_budget must be an object")
    if not isinstance(contract.get("deterministic_scaffold"), dict):
        issues.append("deterministic_scaffold must be an object")
    if not isinstance(contract.get("anti_patterns"), list):
        issues.append("anti_patterns must be a list")
    if not isinstance(contract.get("must_avoid"), list):
        issues.append("must_avoid must be a list")
    if not isinstance(contract.get("pre_authoring_checks"), list) or not contract.get("pre_authoring_checks"):
        issues.append("pre_authoring_checks must be a non-empty list")
    if not isinstance(contract.get("critic_checks"), list) or not contract.get("critic_checks"):
        issues.append("critic_checks must be a non-empty list")
    return issues
