from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pipeline.narrative_composition import analyze_slide_narrative


@dataclass(frozen=True)
class SceneRoute:
    scene_type: str
    generation_strategy: str
    deterministic_weight: str
    executor_freedom: str
    reason: str


@dataclass(frozen=True)
class ExecutionPolicy:
    scene_type: str
    generation_strategy: str
    risk_level: str
    required_loop: str
    qa_strictness: str
    expected_first_pass_rules: list[str]


def _risk_level(scene_type: str, *, deck_profile: str) -> str:
    profile = deck_profile.strip().lower()
    high_risk_scenes = {
        "core_orbit_relationship",
        "proposal_proof",
        "data_insight",
        "architecture_flow",
        "pain_point",
        "risk_shift_control",
        "ops_closure_dashboard",
    }
    if scene_type in high_risk_scenes:
        return "high"
    if scene_type == "roadmap":
        return "high" if any(token in profile for token in ("proposal", "consult", "tender", "bid")) else "medium"
    if scene_type in {"executive_summary", "comparison"}:
        return "medium"
    return "low"


def _first_pass_rules(scene_type: str, strategy: str) -> list[str]:
    common = [
        "dominant focal point must be visible before any detail block",
        "body text must stay at or above 16px",
        "key conclusion must not be copyfit-shrunk",
    ]
    by_scene = {
        "proposal_proof": ["no same-weight card grid", "proof object must dominate supporting evidence"],
        "data_insight": ["chart must have an explicit insight headline", "avoid legend hunting"],
        "roadmap": ["timeline spine must be readable in one pass", "highlight one current or decisive phase"],
        "architecture_flow": ["flow direction must be visually explicit", "node labels must stay inside safe regions"],
        "comparison": ["decision axis must be clear", "preferred option must have visible emphasis"],
        "pain_point": [
            "left pain must be specific",
            "right impact must be 2-3 concise outcomes",
            "takeaway bar must be clearly separated",
        ],
        "risk_shift_control": [
            "before-after gate movement must dominate",
            "risk evidence matrix must support rather than flatten the story",
        ],
        "ops_closure_dashboard": [
            "closure matrix must read as the decision area",
            "monitoring cards must support rather than compete with closure",
        ],
        "cover_brand": ["hero title must be the first read", "avoid dashboard-style opener"],
    }
    rules = common + by_scene.get(scene_type, ["avoid same-weight modules"])
    if strategy == "deterministic_safe":
        rules.append("respect scaffold before adding visual polish")
    return rules


def build_execution_policy(route: SceneRoute, *, deck_profile: str = "presentation") -> ExecutionPolicy:
    profile = deck_profile.strip().lower()
    risk = _risk_level(route.scene_type, deck_profile=profile)
    proposal_profile = any(token in profile for token in ("proposal", "consult", "tender", "bid"))
    qa_strictness = "blocking" if proposal_profile and risk == "high" else "warning"
    return ExecutionPolicy(
        scene_type=route.scene_type,
        generation_strategy=route.generation_strategy,
        risk_level=risk,
        required_loop="single_slide",
        qa_strictness=qa_strictness,
        expected_first_pass_rules=_first_pass_rules(route.scene_type, route.generation_strategy),
    )


def _flatten_text(value: Any, bucket: list[str]) -> None:
    if isinstance(value, str):
        text = value.strip()
        if text:
            bucket.append(text)
        return
    if isinstance(value, dict):
        for item in value.values():
            _flatten_text(item, bucket)
        return
    if isinstance(value, list):
        for item in value:
            _flatten_text(item, bucket)


def _slide_text(slide: dict[str, Any]) -> str:
    pieces: list[str] = []
    for key in ("title", "layout_tag", "narrative_intent", "page_type", "layout_hint", "prompt"):
        _flatten_text(slide.get(key), pieces)
    _flatten_text(slide.get("content"), pieces)
    return " ".join(pieces).lower()


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _forbids_timeline(text: str) -> bool:
    return _has_any(
        text,
        (
            "不要完整时间轴",
            "不要做成完整时间轴",
            "不要时间轴",
            "不做时间轴",
            "不要完整时间线",
            "不要做成完整时间线",
            "no timeline",
        ),
    )


def _forbids_architecture_flow(text: str) -> bool:
    return _has_any(
        text,
        (
            "不要架构图",
            "不要做成架构图",
            "不要流程图",
            "不要画复杂流程图",
            "不要做成复杂流程图",
            "no architecture",
            "no flow diagram",
        ),
    )


def _forbids_closure(text: str) -> bool:
    return _has_any(text, ("不要闭环", "不要做成闭环", "不要闭环图", "no loop", "no closure"))


def _time_anchors(text: str) -> list[str]:
    dates = re.findall(
        r"(?:\d{4}[年/-])?\d{1,2}(?:月|/|-)\d{1,2}(?:日)?",
        text,
    )
    stages = re.findall(
        r"(?:第[一二三四五六七八九十\d]+阶段|阶段[一二三四五六七八九十\d]+|过去|现在|未来)",
        text,
    )
    return list(dict.fromkeys([*dates, *stages]))


def _timeline_evidence(text: str) -> tuple[bool, list[str]]:
    anchors = _time_anchors(text)
    relations = [
        term
        for term in ("先", "再", "随后", "然后", "之后", "通过后", "完成后", "依赖", "→", "->")
        if term in text
    ]
    return len(anchors) >= 2 and bool(relations), [*anchors, *relations]


def _from_to_direction_evidence(text: str) -> list[str]:
    node_terms = (
        "节点",
        "模块",
        "层级",
        "边界",
        "入口",
        "出口",
        "上游",
        "下游",
        "数据层",
        "应用层",
        "系统",
        "平台",
    )
    direction_actions = ("流向", "调用", "连接", "传递", "输入", "输出", "发送", "回传", "下发")
    for start, end in re.findall(r"从([^。；;，,\n]{1,48})到([^。；;，,\n]{1,48})", text):
        if (
            any(term in start for term in node_terms)
            and any(term in end for term in node_terms)
            and any(term in f"{start} {end}" for term in direction_actions)
        ):
            return ["从…到节点方向", *[term for term in direction_actions if term in f"{start} {end}"]]
    return []


def _architecture_evidence(text: str, layout_tag: str) -> tuple[bool, list[str]]:
    explicit_terms = [
        term
        for term in ("architecture", "架构", "拓扑", "分层架构", "系统架构", "平台架构")
        if term in text
    ]
    if "architecture" in layout_tag:
        explicit_terms.append(f"layout_tag={layout_tag}")
    if explicit_terms:
        return True, explicit_terms

    core_support_terms = [term for term in ("中心圆", "四周", "支持域") if term in text]
    if len(core_support_terms) == 3:
        return True, [*core_support_terms, "explicit_core_support_structure"]

    supplier_tiers = sorted(
        {
            item.upper()
            for item in re.findall(r"(?<![A-Za-z0-9])T(?:\d+|N)(?![A-Za-z0-9])", text, flags=re.I)
        }
    )
    node_terms = [
        term
        for term in (
            "节点",
            "模块",
            "层级",
            "边界",
            "入口",
            "出口",
            "上游",
            "下游",
            "数据层",
            "应用层",
            "中心圆",
            "四周",
            "支持域",
        )
        if term in text
    ]
    node_terms.extend(supplier_tiers)
    direction_terms = [
        term
        for term in ("流向", "调用", "连接", "传递", "输入", "输出", "发送", "回传", "下发", "→", "->")
        if term in text
    ]
    direction_terms.extend(_from_to_direction_evidence(text))
    return len(set(node_terms)) >= 2 and bool(direction_terms), [*node_terms, *direction_terms]


def _int_feature(features: dict[str, Any], key: str) -> int:
    try:
        return int(features.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _bool_feature(features: dict[str, Any], key: str) -> bool:
    return bool(features.get(key))


def _route_for_scene(scene_type: str, *, reason: str, deck_profile: str) -> SceneRoute:
    batch_mode = any(token in deck_profile for token in ("batch", "low_cost", "low-cost", "commodity"))
    if batch_mode and scene_type in {"data_insight", "comparison", "roadmap"}:
        return SceneRoute(scene_type, "deterministic_safe", "high", "low-medium", reason)

    policy = {
        "core_orbit_relationship": ("skeleton_then_polish", "medium-high", "medium"),
        "proposal_proof": ("executor_free_svg", "medium", "high"),
        "executive_summary": ("executor_free_svg", "medium", "high"),
        "data_insight": ("skeleton_then_polish", "high", "medium"),
        "pain_point": ("skeleton_then_polish", "medium-high", "medium"),
        "roadmap": ("skeleton_then_polish", "medium-high", "medium-high"),
        "architecture_flow": ("skeleton_then_polish", "medium-high", "medium-high"),
        "risk_shift_control": ("skeleton_then_polish", "medium-high", "medium"),
        "ops_closure_dashboard": ("skeleton_then_polish", "medium-high", "medium"),
        "cover_brand": ("executor_free_svg", "low-medium", "high"),
        "comparison": ("skeleton_then_polish", "medium-high", "medium"),
        "general_explainer": ("executor_free_svg", "medium", "medium-high"),
    }
    strategy, deterministic_weight, executor_freedom = policy.get(
        scene_type,
        ("executor_free_svg", "medium", "medium-high"),
    )
    return SceneRoute(scene_type, strategy, deterministic_weight, executor_freedom, reason)


def classify_slide_scene(slide: dict[str, Any], *, deck_profile: str = "presentation") -> SceneRoute:
    text = _slide_text(slide)
    layout_tag = str(slide.get("layout_tag") or "").lower()
    profile = deck_profile.strip().lower()
    features = slide.get("features")
    feature_map = features if isinstance(features, dict) else {}

    explicit_scene = str(slide.get("scene_type") or "").strip()
    if explicit_scene == "core_orbit_relationship":
        return _route_for_scene(explicit_scene, reason="explicit scene_type", deck_profile=profile)

    chart_count = _int_feature(feature_map, "chart_count")
    kpi_count = _int_feature(feature_map, "kpi_count")
    has_timeline = _bool_feature(feature_map, "has_timeline")
    has_comparison = _bool_feature(feature_map, "has_comparison")

    if "cover" in layout_tag or any(
        token in text for token in ("\u5c01\u9762", "title page", "opening statement", "opening slide")
    ):
        return _route_for_scene("cover_brand", reason="cover/title signal", deck_profile=profile)

    narrative = analyze_slide_narrative(slide, deck_profile=profile)
    narrative_scene = str(narrative.get("scene_type") or "")
    if narrative_scene in {"risk_shift_control", "ops_closure_dashboard"}:
        if not (narrative_scene == "ops_closure_dashboard" and _forbids_closure(text)):
            return _route_for_scene(
                narrative_scene,
                reason=f"narrative composition signal: {narrative.get('relationship_model')}",
                deck_profile=profile,
            )

    if (
        chart_count > 0
        or kpi_count >= 2
        or "chart" in layout_tag
        or any(
            token in text
            for token in ("kpi", "trend", "\u540c\u6bd4", "\u73af\u6bd4", "\u6307\u6807", "insight", "conversion")
        )
    ):
        return _route_for_scene("data_insight", reason="chart/kpi insight signal", deck_profile=profile)

    if any(token in text for token in ("\u75db\u70b9", "\u74f6\u9888", "\u6323\u624e", "\u6311\u6218")):
        return _route_for_scene("pain_point", reason="pain point signal", deck_profile=profile)

    timeline_supported, timeline_evidence = _timeline_evidence(text)
    explicit_timeline_layout = any(token in layout_tag for token in ("timeline", "roadmap"))
    if not _forbids_timeline(text) and (timeline_supported or has_timeline or explicit_timeline_layout):
        reason = "timeline evidence: " + ", ".join(timeline_evidence or [layout_tag or "has_timeline"])
        return _route_for_scene("roadmap", reason=reason, deck_profile=profile)

    architecture_supported, architecture_evidence = _architecture_evidence(text, layout_tag)
    if not _forbids_architecture_flow(text) and architecture_supported:
        return _route_for_scene(
            "architecture_flow",
            reason="architecture evidence: " + ", ".join(architecture_evidence),
            deck_profile=profile,
        )

    if (
        has_comparison
        or any(token in layout_tag for token in ("comparison", "matrix"))
        or any(token in text for token in ("compare", "versus", "vs", "tradeoff", "\u5bf9\u6bd4", "\u4f18\u52a3"))
    ):
        return _route_for_scene("comparison", reason="comparison signal", deck_profile=profile)

    proposal_profile = any(token in profile for token in ("proposal", "consult", "tender", "bid"))
    proposal_proof_tokens = (
        "proof",
        "evidence",
        "risk",
        "deliver",
        "case",
        "capability",
        "\u8ba4\u8bc1",
        "\u6848\u4f8b",
        "\u98ce\u63a7",
        "\u4ea4\u4ed8",
    )
    if proposal_profile and any(token in text for token in proposal_proof_tokens):
        return _route_for_scene("proposal_proof", reason="proposal proof/risk signal", deck_profile=profile)

    if proposal_profile or any(
        token in text
        for token in (
            "summary",
            "decision",
            "recommendation",
            "takeaway",
            "\u7ed3\u8bba",
            "\u5efa\u8bae",
            "\u51b3\u7b56",
        )
    ):
        return _route_for_scene("executive_summary", reason="executive summary signal", deck_profile=profile)

    return _route_for_scene("general_explainer", reason="default route", deck_profile=profile)
