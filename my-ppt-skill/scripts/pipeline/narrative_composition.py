from __future__ import annotations

from typing import Any


def _flatten_text(value: Any, bucket: list[str]) -> None:
    if isinstance(value, str):
        text = value.strip()
        if text:
            bucket.append(text)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _flatten_text(str(key), bucket)
            _flatten_text(item, bucket)
        return
    if isinstance(value, list):
        for item in value:
            _flatten_text(item, bucket)


def _slide_text(slide: dict[str, Any]) -> str:
    pieces: list[str] = []
    for key in ("title", "layout_tag", "narrative_intent", "page_type", "layout_hint"):
        _flatten_text(slide.get(key), pieces)
    _flatten_text(slide.get("content"), pieces)
    return " ".join(pieces).lower()


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token.lower() in text for token in tokens)


def _iter_content_blocks(slide: dict[str, Any]) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    content = slide.get("content")
    if isinstance(content, dict):
        for key, value in content.items():
            pieces: list[str] = [str(key)]
            _flatten_text(value, pieces)
            blocks.append((str(key), " ".join(pieces).lower()))
    return blocks


def _risk_content_roles(slide: dict[str, Any]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for label, text in _iter_content_blocks(slide):
        if _contains_any(text, ("预警价值", "主动管控", "价值", "总结", "收束")):
            roles[label] = "argument_closure"
        elif _contains_any(text, ("传统", "事后", "海关审查", "销售出库", "末端", "被动")):
            roles[label] = "traditional_response"
        elif _contains_any(text, ("平台", "过程预警", "原材料入库", "半成品", "成品出库前", "前移")):
            roles[label] = "process_warning"
        elif _contains_any(text, ("名单", "地区", "文件", "数据", "风险维度", "管控标签")):
            roles[label] = "risk_matrix"
    return roles


def _ops_content_roles(slide: dict[str, Any]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for label, text in _iter_content_blocks(slide):
        if _contains_any(text, ("基座", "核心指标", "指标体系", "任务指标", "文件指标", "供应商指标")):
            roles[label] = "input_foundation"
        elif _contains_any(text, ("看板", "监控", "完成率", "齐套率", "响应及时率", "一次通过率", "趋势")):
            roles[label] = "monitoring_signal"
        elif _contains_any(text, ("卡点", "归因", "整改", "闭环", "责任部门", "处置动作", "状态")):
            roles[label] = "decision_closure"
    return roles


def _risk_detected(text: str) -> bool:
    return (
        _contains_any(text, ("风险识别关口前移", "过程预警", "事后响应", "末端发现"))
        and _contains_any(text, ("海关审查", "销售出库", "原材料入库", "半成品", "前移", "主动管控"))
    )


def _ops_detected(text: str) -> bool:
    return (
        _contains_any(text, ("运营指标", "运营指标体系", "卡点归因", "整改闭环"))
        and _contains_any(text, ("任务", "文件", "供应商", "责任部门", "处置动作", "状态"))
    )


def _risk_model(slide: dict[str, Any]) -> dict[str, Any]:
    return {
        "scene_type": "risk_shift_control",
        "relationship_model": "lagging_response_to_process_warning",
        "primary_message": (
            "Risk identification moves from customs or sales-out lagging discovery "
            "to process warning at intake and production checkpoints."
        ),
        "content_roles": _risk_content_roles(slide),
        "composition_candidates": [],
    }


def _ops_model(slide: dict[str, Any]) -> dict[str, Any]:
    return {
        "scene_type": "ops_closure_dashboard",
        "relationship_model": "monitoring_to_diagnosis_to_action",
        "primary_message": (
            "Operating indicators are not a display board; they drive bottleneck "
            "diagnosis and remediation closure."
        ),
        "content_roles": _ops_content_roles(slide),
        "composition_candidates": [],
    }


def analyze_slide_narrative(slide: dict[str, Any], deck_profile: str = "presentation") -> dict[str, Any]:
    del deck_profile
    text = _slide_text(slide)
    if _risk_detected(text):
        return _risk_model(slide)
    if _ops_detected(text):
        return _ops_model(slide)
    return {
        "scene_type": "general_explainer",
        "relationship_model": "supporting_evidence",
        "primary_message": "A main statement is supported by concise evidence.",
        "content_roles": {},
        "composition_candidates": [],
    }


def build_composition_candidates(model: dict[str, Any], route: Any) -> list[dict[str, str]]:
    scene_type = str(model.get("scene_type") or getattr(route, "scene_type", ""))
    if scene_type == "risk_shift_control":
        return [
            {
                "id": "before_after_shift_with_evidence_matrix",
                "best_for": "formal proposal defense where the evaluator must see the control gate move forward",
                "visual_logic": (
                    "traditional response is weakened, process warning becomes "
                    "the stronger contrast card, and the risk matrix proves coverage"
                ),
                "risk": "may become a plain function list if the before-after shift is not visually dominant",
            },
            {
                "id": "control_gate_timeline_board",
                "best_for": "explaining checkpoint movement across intake, production, and outbound stages",
                "visual_logic": "a control-gate path carries risk tags forward across business nodes",
                "risk": "may over-emphasize process flow and bury the evidence matrix",
            },
        ]
    if scene_type == "ops_closure_dashboard":
        return [
            {
                "id": "dashboard_with_closure_matrix",
                "best_for": "formal proposal defense",
                "visual_logic": "monitoring signals support a stronger closure matrix",
                "risk": "may become equal-weight cards if hierarchy is not enforced",
            },
            {
                "id": "closed_loop_flow_board",
                "best_for": "emphasizing management closure from metrics to action",
                "visual_logic": (
                    "indicator inputs feed monitoring signals, then bottleneck "
                    "diagnosis and remediation status close the loop"
                ),
                "risk": "may feel crowded when every indicator is drawn as a separate chip",
            },
        ]
    return []


def select_composition_candidate(candidates: list[dict[str, str]]) -> dict[str, str]:
    if not candidates:
        return {}
    preferred = {
        "dashboard_with_closure_matrix",
        "before_after_shift_with_evidence_matrix",
    }
    for candidate in candidates:
        if candidate.get("id") in preferred:
            return candidate
    return candidates[0]
