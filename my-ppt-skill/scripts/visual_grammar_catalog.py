#!/usr/bin/env python3
"""Resolve reusable visual grammar patterns for design-directed PPT pages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_CATALOG = SKILL_DIR / "references" / "visual-grammar-catalog.json"


def load_visual_grammar_catalog(path: Path | None = None) -> dict[str, Any]:
    catalog_path = (path or DEFAULT_CATALOG).resolve()
    payload = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Visual grammar catalog root must be an object: {catalog_path}")
    grammars = payload.get("grammars")
    if not isinstance(grammars, list) or not grammars:
        raise ValueError(f"Visual grammar catalog must contain a non-empty grammars list: {catalog_path}")
    required = {
        "grammar_id",
        "name",
        "applies_to_tags",
        "keywords",
        "skeleton",
        "dominant_object",
        "accent_strategy",
        "secondary_content_policy",
        "failure_modes",
        "reference_case_ids",
    }
    for item in grammars:
        if not isinstance(item, dict):
            raise ValueError("Every visual grammar entry must be an object.")
        missing = sorted(required - set(item))
        if missing:
            raise ValueError(f"Visual grammar {item.get('grammar_id')!r} missing keys: {missing}")
    return payload


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(v) for v in value)
    return "" if value is None else str(value)


def _score_grammar(grammar: dict[str, Any], *, layout_tag: str, text: str) -> int:
    score = 0
    applies = grammar.get("applies_to_tags")
    if isinstance(applies, list) and layout_tag in {str(item) for item in applies}:
        score += 6
    lowered = text.lower()
    for keyword in grammar.get("keywords", []):
        key = str(keyword).strip()
        if key and key.lower() in lowered:
            score += 4
    return score


RELATIONAL_GRAMMAR_IDS = {
    "phase-transition",
    "human-ai-division",
    "input-process-output",
    "workflow-chain",
    "responsibility-loop",
    "demo-transition",
    "composite-flow-responsibility",
    "case-diagnosis",
    "engineering-gap-bridge",
}
ACTION_TERMS = (
    "触发",
    "上传",
    "提交",
    "审核",
    "退回",
    "整改",
    "复核",
    "关闭",
    "输入",
    "处理",
    "输出",
    "input",
    "process",
    "output",
    "review",
    "return",
    "close",
    "generate",
    "finalize",
)
SEQUENCE_TERMS = (
    "先",
    "再",
    "随后",
    "然后",
    "之后",
    "触发后",
    "通过后",
    "不通过",
    "退回",
    "→",
    "->",
    "workflow",
    "chain",
    "end-to-end",
    "from",
    " to ",
    "then",
    "after",
)


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def _has_actor_action_endpoint(value: str) -> bool:
    return bool(
        re.search(
            r"(?:项目组|供应商|销售|供应链|质量|IT|财务|关务|业务|部门|T(?:\d+|N)|human|ai)"
            r"[^。；;，,\n]{0,12}"
            r"(?:触发|上传|提交|审核|退回|整改|复核|关闭|输入|处理|输出|"
            r"input|process|output|review|return|close|generate|finalize)",
            value,
            flags=re.I,
        )
    )


def _has_from_to_action_endpoints(text: str) -> bool:
    for start, end in re.findall(r"从([^。；;，,\n]{1,48})到([^。；;，,\n]{1,48})", text):
        if _has_actor_action_endpoint(start) and _has_actor_action_endpoint(end):
            return True
    return False


def _process_evidence(text: str) -> bool:
    actions = set(_matched_terms(text, ACTION_TERMS))
    relations = _matched_terms(text, SEQUENCE_TERMS)
    if _has_from_to_action_endpoints(text):
        relations.append("from_to_action_endpoints")
    return len(actions) >= 2 and bool(relations)


def _responsibility_evidence(text: str) -> bool:
    lowered = text.lower()
    if any(
        term in lowered
        for term in ("human responsibility", "human owns", "ai participates", "人负责", "ai参与", "明确分工")
    ):
        return True
    bindings = re.findall(
        r"(?:项目组|供应商|销售|供应链|质量|IT|财务|关务|业务|部门)"
        r"[^。；;，,\n]{0,12}(?:发起|上传|提供|提交|审核|授权|推动|负责|关闭)",
        text,
        flags=re.I,
    )
    return len(bindings) >= 2


def _phase_evidence(text: str) -> bool:
    dates = re.findall(r"\d{1,2}月\d{1,2}日", text)
    stages = re.findall(
        r"(?:第[一二三四五六七八九十\d]+阶段|阶段[一二三四五六七八九十\d]+|过去|现在|未来)",
        text,
    )
    anchors = set([*dates, *stages])
    relations = _matched_terms(text, SEQUENCE_TERMS + ("转为", "转入", "跃迁", "transition"))
    return len(anchors) >= 2 and bool(relations)


def _demo_transition_evidence(text: str) -> bool:
    demo_terms = _matched_terms(text, ("演示", "demo", "现场", "初稿", "prototype"))
    transition_terms = _matched_terms(text, ("前后", "转为", "迭代", "初稿", "定稿", "before", "after"))
    has_from_to = _has_from_to_action_endpoints(text)
    return bool(demo_terms and (transition_terms or has_from_to))


def _cognitive_reframe_evidence(text: str) -> bool:
    lowered = text.lower()
    strong_terms = (
        "重新认识",
        "认知重构",
        "认知转变",
        "范式转变",
        "reframe",
        "paradigm shift",
    )
    if any(term in lowered for term in strong_terms):
        return True
    past_terms = ("过去", "原来", "此前", "旧认知", "传统认知")
    present_terms = ("现在", "当前", "如今", "新判断", "新认知")
    return any(term in text for term in past_terms) and any(term in text for term in present_terms)


def _engineering_gap_evidence(text: str) -> bool:
    lowered = text.lower()
    demo_terms = ("demo", "演示", "原型", "prototype")
    production_terms = ("生产", "production", "可交付", "production-ready")
    gap_terms = ("鸿沟", "隔着", "之间", "壁垒", "障碍", "bridge", "gap", "barrier")
    engineering_terms = (
        "架构",
        "规范",
        "测试",
        "权限",
        "监控",
        "发布",
        "维护",
        "多人协作",
        "software engineering",
        "architecture",
        "testing",
        "permission",
        "monitoring",
        "release",
        "maintenance",
    )
    matched_engineering = {term for term in engineering_terms if term in lowered}
    return (
        any(term in lowered for term in demo_terms)
        and any(term in lowered for term in production_terms)
        and any(term in lowered for term in gap_terms)
        and len(matched_engineering) >= 2
    )


def _case_diagnosis_evidence(text: str) -> bool:
    lowered = text.lower()
    case_terms = ("复盘", "教训", "案例", "vibe coding", "case review", "retrospective")
    surface_terms = ("表面成果", "表面繁荣", "demo跑通", "主流程", "能演示", "surface result", "apparent success")
    issue_terms = (
        "暴露的问题",
        "生产问题",
        "根本原因",
        "问题本质",
        "真问题",
        "生产级问题",
        "根因",
        "root cause",
        "exposed issue",
    )
    return (
        any(term in lowered for term in case_terms)
        and any(term in lowered for term in surface_terms)
        and any(term in lowered for term in issue_terms)
    )


def _grammar_has_relationship_evidence(grammar_id: str, text: str) -> bool:
    if grammar_id == "cognitive-reframe":
        return _cognitive_reframe_evidence(text)
    if grammar_id == "case-diagnosis":
        return _case_diagnosis_evidence(text)
    if grammar_id == "engineering-gap-bridge":
        return _engineering_gap_evidence(text)
    if grammar_id not in RELATIONAL_GRAMMAR_IDS:
        return True
    if grammar_id in {"workflow-chain", "input-process-output"}:
        return _process_evidence(text)
    if grammar_id == "phase-transition":
        return _phase_evidence(text)
    if grammar_id == "demo-transition":
        return _demo_transition_evidence(text)
    if grammar_id in {"responsibility-loop", "human-ai-division"}:
        return _responsibility_evidence(text)
    if grammar_id == "composite-flow-responsibility":
        return _process_evidence(text) and _responsibility_evidence(text)
    return False


def _rule_override(layout_tag: str, text: str) -> str | None:
    lowered = text.lower()
    flow_terms = ("链路", "流程", "workflow", "chain")
    responsibility_terms = ("人负责", "责任", "判断", "质量把控", "human responsibility", "final responsibility")
    supplier_tiers = {
        item.upper()
        for item in re.findall(r"(?<![A-Za-z0-9])T(?:\d+|N)(?![A-Za-z0-9])", text, flags=re.I)
    }
    if _case_diagnosis_evidence(text):
        return "case-diagnosis"
    if _engineering_gap_evidence(text):
        return "engineering-gap-bridge"
    if len(supplier_tiers) >= 2 and _process_evidence(text):
        return "workflow-chain"
    if any(term in lowered for term in flow_terms) and any(term in lowered for term in responsibility_terms):
        return "composite-flow-responsibility"
    if (
        "skill =" in lowered
        or "能力引擎" in text
        or ("skill" in lowered and any(term in text for term in ("角色", "模板", "规则", "检查清单", "质量标准")))
    ):
        return "capability-equation-engine"
    if (
        any(term in text for term in ("三层", "成熟度", "标准化", "个人经验", "方法沉淀", "标准复用"))
        or "maturity" in lowered
    ):
        return "maturity-ladder"
    if (
        any(term in text for term in ("原型", "画出来", "可运行"))
        or any(term in lowered for term in ("prototype", "wireframe", "interface", "screenshot"))
        or ("demo" in lowered and any(term in lowered for term in ("proof", "console", "screen", "artifact")))
    ):
        return "artifact-centered-proof"
    if layout_tag == "Grid-Four-Cards" or "四类" in text or "四象限" in text:
        return "quadrant-case-map"
    if "不要神化" in text or "误区" in text or "真实方式" in text or "myth" in lowered:
        return "myth-vs-reality"
    if "demo" in lowered or "演示" in text or "现场" in text:
        return "demo-transition"
    if "焦虑" in text or "行动" in text:
        return "anxiety-to-action"
    if "人负责" in text or "AI参与" in text or "分工" in text:
        return "human-ai-division"
    if "输入" in text and "输出" in text:
        return "input-process-output"
    if "工作流" in text or "链路" in text or "任务执行" in text:
        return "workflow-chain"
    if "能力" in text and ("放大" in text or "人才" in text):
        return "capability-amplifier"
    if "阶段" in text or "从问答工具到工作伙伴" in text:
        return "phase-transition"
    if "闭环" in text or "责任" in text:
        return "responsibility-loop"
    return None


def select_visual_grammar(
    *,
    layout_tag: str,
    narrative_intent: str,
    title: str,
    content: Any,
    catalog_path: Path | None = None,
) -> dict[str, Any]:
    catalog = load_visual_grammar_catalog(catalog_path)
    grammars = [item for item in catalog["grammars"] if isinstance(item, dict)]
    text = re.sub(r"\s+", " ", f"{layout_tag} {title} {narrative_intent} {_flatten_text(content)}")
    override = _rule_override(layout_tag, text)
    if override and _grammar_has_relationship_evidence(override, text):
        for grammar in grammars:
            if grammar.get("grammar_id") == override:
                return dict(grammar)
    eligible = [
        grammar
        for grammar in grammars
        if _grammar_has_relationship_evidence(str(grammar.get("grammar_id") or ""), text)
    ]
    scored = sorted(
        eligible,
        key=lambda item: (_score_grammar(item, layout_tag=layout_tag, text=text), str(item.get("grammar_id"))),
        reverse=True,
    )
    if scored and _score_grammar(scored[0], layout_tag=layout_tag, text=text) > 0:
        return dict(scored[0])
    neutral = _grammar_by_id(grammars, "problem-labels")
    return neutral or dict(grammars[0])


def _grammar_by_id(grammars: list[dict[str, Any]], grammar_id: str) -> dict[str, Any] | None:
    for grammar in grammars:
        if grammar.get("grammar_id") == grammar_id:
            return dict(grammar)
    return None


def select_visual_grammars(
    *,
    layout_tag: str,
    narrative_intent: str,
    title: str,
    content: Any,
    catalog_path: Path | None = None,
) -> dict[str, Any]:
    """Return a primary grammar plus secondary grammars for compound page briefs."""
    catalog = load_visual_grammar_catalog(catalog_path)
    grammars = [item for item in catalog["grammars"] if isinstance(item, dict)]
    primary = select_visual_grammar(
        layout_tag=layout_tag,
        narrative_intent=narrative_intent,
        title=title,
        content=content,
        catalog_path=catalog_path,
    )
    text = re.sub(r"\s+", " ", f"{layout_tag} {title} {narrative_intent} {_flatten_text(content)}")
    preferred = {
        "composite-flow-responsibility": ["workflow-chain", "human-ai-division"],
        "artifact-centered-proof": ["problem-labels", "input-process-output", "demo-transition"],
        "maturity-ladder": ["phase-transition", "capability-amplifier"],
        "capability-equation-engine": ["capability-amplifier", "responsibility-loop"],
        "case-diagnosis": ["problem-labels", "demo-transition"],
        "engineering-gap-bridge": ["problem-labels", "phase-transition"],
    }
    secondary: list[dict[str, Any]] = []
    seen = {str(primary.get("grammar_id"))}
    for grammar_id in preferred.get(str(primary.get("grammar_id")), []):
        grammar = _grammar_by_id(grammars, grammar_id)
        if grammar and grammar_id not in seen and _grammar_has_relationship_evidence(grammar_id, text):
            secondary.append(grammar)
            seen.add(grammar_id)
    scored = sorted(
        grammars,
        key=lambda item: (_score_grammar(item, layout_tag=layout_tag, text=text), str(item.get("grammar_id"))),
        reverse=True,
    )
    for grammar in scored:
        grammar_id = str(grammar.get("grammar_id"))
        if (
            grammar_id not in seen
            and _grammar_has_relationship_evidence(grammar_id, text)
            and _score_grammar(grammar, layout_tag=layout_tag, text=text) > 0
        ):
            secondary.append(dict(grammar))
            seen.add(grammar_id)
        if len(secondary) >= 3:
            break
    return {"primary": primary, "secondary": secondary[:3]}


def main() -> int:
    catalog = load_visual_grammar_catalog()
    print(json.dumps({"version": catalog["version"], "grammar_count": len(catalog["grammars"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
