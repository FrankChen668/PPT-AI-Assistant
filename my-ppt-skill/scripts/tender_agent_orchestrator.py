"""Hard-gated PLAN -> CRITIQUE -> EXECUTE orchestration for tender slides.

EXPERIMENTAL TRACK - ISOLATED. This module's slide contract fields
(claim / evidence / must_keep / page_type) are experiment-only. The single
authority for claim/evidence-class planning fields is the mainline content
planning schema in ``workbench/content_planning.py`` (claims /
acceptance_criteria / source_refs / claim_boundary). Mainline modules
(``workbench/*``, ``my-ppt-skill/scripts/build_project.py``) must not import
``tender_agent_*``; a guard test enforces this isolation
(``my-ppt-skill/tests/test_tender_agent_isolation.py``).

The module deliberately does not call a model provider. Callers inject three
independent functions so tests and future integrations can prove that gates are
enforced by Python control flow, not by prompt instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Any, Callable, Mapping

TENDER_CRITIC_RUBRIC: tuple[dict[str, str], ...] = (
    {
        "id": "five_second_message",
        "check": "核心结论是否在前 5 秒可读，不依赖图表解释。",
    },
    {
        "id": "buyer_pain_mapping",
        "check": "页面是否明确回应甲方的成本、风险、合规或交付痛点。",
    },
    {
        "id": "buyer_value_over_capability",
        "check": "是否把我方能力转译成甲方价值，而不是只做能力展示。",
    },
    {
        "id": "evidence_backing",
        "check": "主张是否有数据、机制、案例、流程或证据类型支撑。",
    },
    {
        "id": "visual_reduces_cognitive_load",
        "check": "图示是否降低理解成本，而不是装饰性堆叠。",
    },
    {
        "id": "non_ai_tender_tone",
        "check": "页面是否像正式售前/投标稿，避免空泛 AI 味表达。",
    },
)

REQUIRED_DECK_BRIEF_FIELDS = (
    "audience",
    "bid_scenario",
    "winning_strategy",
    "evaluation_criteria",
    "tone",
    "visual_direction",
)

REQUIRED_SLIDE_CONTRACT_FIELDS = (
    "slide",
    "source_page",
    "page_type",
    "claim",
    "evidence",
    "layout_intent",
    "must_keep",
    "must_avoid",
    "success_check",
)

REQUIRED_CRITIQUE_FIELDS = ("pass", "slide_scores", "required_changes")
REQUIRED_SCORE_FIELDS = (
    "claim_score",
    "evidence_score",
    "bid_relevance_score",
    "differentiation_score",
    "clarity_score",
    "necessity_score",
)
MIN_APPROVED_TOTAL_SCORE = 80
MIN_APPROVED_DIMENSION_SCORE = 2
GLOBAL_CONTRACT_BANNED_PHRASES = (
    "100%",
    "guaranteed pass",
    "guarantee pass",
    "保证通过",
    "自动合规审查",
    "替代人工判断",
    "全部覆盖",
)


class SchemaError(ValueError):
    """Raised when a stage output fails the required schema."""


class PipelineHalt(RuntimeError):
    """Raised when a hard gate blocks the next stage."""

    def __init__(self, stage: str, message: str, payload: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.stage = stage
        self.payload = dict(payload or {})


@dataclass(frozen=True)
class OrchestrationResult:
    manifest: dict[str, Any]
    critique: dict[str, Any]
    contract_qa: dict[str, Any]
    workflow_state: dict[str, Any]
    executor_result: Any
    plan_attempts: int


PlanCall = Callable[[Mapping[str, Any]], Mapping[str, Any]]
CriticCall = Callable[[Mapping[str, Any]], Mapping[str, Any]]
ExecutorCall = Callable[[Mapping[str, Any]], Any]


def _validate_non_empty_string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{label} must be a non-empty string.")


def _validate_non_empty_string_list(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value:
        raise SchemaError(f"{label} must be a non-empty list.")
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise SchemaError(f"{label}[{index}] must be a non-empty string.")


def validate_plan_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Validate PLAN output as a deck brief plus per-slide persuasion contracts."""

    if not isinstance(artifact, Mapping):
        raise SchemaError("plan artifact must be an object.")

    deck_brief = artifact.get("deck_brief")
    if not isinstance(deck_brief, Mapping):
        raise SchemaError("plan artifact.deck_brief must be an object.")
    missing_brief = [field for field in REQUIRED_DECK_BRIEF_FIELDS if field not in deck_brief]
    if missing_brief:
        raise SchemaError(f"deck_brief missing required fields: {', '.join(missing_brief)}.")
    for field in REQUIRED_DECK_BRIEF_FIELDS:
        value = deck_brief.get(field)
        if field == "evaluation_criteria":
            _validate_non_empty_string_list(value, f"deck_brief.{field}")
        else:
            _validate_non_empty_string(value, f"deck_brief.{field}")

    contracts = artifact.get("slide_contracts")
    if not isinstance(contracts, list) or not contracts:
        raise SchemaError("plan artifact.slide_contracts must be a non-empty list.")

    seen_ids: set[int] = set()
    for index, contract in enumerate(contracts, start=1):
        if not isinstance(contract, Mapping):
            raise SchemaError(f"slide_contracts[{index}] must be an object.")
        missing = [field for field in REQUIRED_SLIDE_CONTRACT_FIELDS if field not in contract]
        if missing:
            raise SchemaError(f"slide_contracts[{index}] missing required fields: {', '.join(missing)}.")
        slide_value = contract.get("slide")
        if not isinstance(slide_value, int) or slide_value < 1:
            raise SchemaError(f"slide_contracts[{index}].slide must be a positive integer.")
        slide_id = slide_value
        if slide_id in seen_ids:
            raise SchemaError(f"duplicate slide contract: {slide_id}.")
        seen_ids.add(slide_id)

        for field in REQUIRED_SLIDE_CONTRACT_FIELDS:
            if field == "slide":
                continue
            value = contract.get(field)
            if field in {"evidence", "must_keep", "must_avoid"}:
                _validate_non_empty_string_list(value, f"slide_contracts[{slide_id}].{field}")
            else:
                _validate_non_empty_string(value, f"slide_contracts[{slide_id}].{field}")
    return {
        "deck_brief": dict(deck_brief),
        "slide_contracts": [dict(contract) for contract in contracts],
    }


def validate_slide_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Backward-compatible alias for callers migrating to plan artifacts."""

    return validate_plan_artifact(manifest)


def validate_critique_result(result: Mapping[str, Any], plan_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Validate CRITIQUE output before EXECUTE can run."""

    artifact = validate_plan_artifact(plan_artifact)
    if not isinstance(result, Mapping):
        raise SchemaError("critic_result must be an object.")
    missing = [field for field in REQUIRED_CRITIQUE_FIELDS if field not in result]
    if missing:
        raise SchemaError(f"critic_result missing required fields: {', '.join(missing)}.")
    passed = result.get("pass")
    if not isinstance(passed, bool):
        raise SchemaError("critic_result.pass must be a boolean.")

    scores = result.get("slide_scores")
    if not isinstance(scores, list) or not scores:
        raise SchemaError("critic_result.slide_scores must be a non-empty list.")
    changes = result.get("required_changes")
    if not isinstance(changes, list):
        raise SchemaError("critic_result.required_changes must be a list.")
    if not passed and not changes:
        raise SchemaError("critic_result.required_changes must explain why pass=false.")
    if passed and changes:
        raise SchemaError("critic_result.required_changes must be empty when pass=true.")

    slide_ids: set[int] = {int(contract["slide"]) for contract in artifact["slide_contracts"]}
    scored_ids: set[int] = set()
    for index, score in enumerate(scores, start=1):
        if not isinstance(score, Mapping):
            raise SchemaError(f"slide_scores[{index}] must be an object.")
        slide_id_value = score.get("slide", score.get("slide_id"))
        if not isinstance(slide_id_value, int) or slide_id_value not in slide_ids:
            raise SchemaError(f"slide_scores[{index}].slide does not match plan artifact.")
        slide_id = slide_id_value
        scored_ids.add(slide_id)
        numeric_score = score.get("score")
        if not isinstance(numeric_score, (int, float)) or not 0 <= numeric_score <= 100:
            raise SchemaError(f"slide_scores[{index}].score must be 0-100.")
        if passed and numeric_score < MIN_APPROVED_TOTAL_SCORE:
            raise SchemaError(
                f"slide_scores[{index}].score must be >={MIN_APPROVED_TOTAL_SCORE} when pass=true."
            )
        for field in REQUIRED_SCORE_FIELDS:
            value = score.get(field)
            if not isinstance(value, (int, float)) or not 0 <= value <= 3:
                raise SchemaError(f"slide_scores[{index}].{field} must be 0-3.")
            if passed and value < MIN_APPROVED_DIMENSION_SCORE:
                raise SchemaError(
                    f"slide_scores[{index}].{field} must be >={MIN_APPROVED_DIMENSION_SCORE} when pass=true."
                )
        decision = score.get("decision")
        if decision not in {"approved", "blocked"}:
            raise SchemaError(f"slide_scores[{index}].decision must be approved or blocked.")
        if passed and decision != "approved":
            raise SchemaError(f"slide_scores[{index}].decision must be approved when pass=true.")
        failed = score.get("failed_criteria", [])
        if not isinstance(failed, list):
            raise SchemaError(f"slide_scores[{index}].failed_criteria must be a list.")
    if scored_ids != slide_ids:
        raise SchemaError("critic_result.slide_scores must cover every slide contract.")
    return dict(result)


def build_workflow_state(critique: Mapping[str, Any]) -> dict[str, Any]:
    """Derive executable state from Critic output; the model does not set this."""

    validate_basic = isinstance(critique, Mapping) and isinstance(critique.get("slide_scores"), list)
    scores = critique.get("slide_scores", []) if validate_basic else []
    approved = bool(critique.get("pass"))
    blocked_slides: list[int] = []
    for score in scores:
        if not isinstance(score, Mapping):
            continue
        slide = score.get("slide", score.get("slide_id"))
        if not isinstance(slide, int):
            continue
        low_total = isinstance(score.get("score"), (int, float)) and score["score"] < MIN_APPROVED_TOTAL_SCORE
        low_dimension = any(
            isinstance(score.get(field), (int, float)) and score[field] < MIN_APPROVED_DIMENSION_SCORE
            for field in REQUIRED_SCORE_FIELDS
        )
        if score.get("decision") == "blocked" or low_total or low_dimension:
            blocked_slides.append(slide)

    svg_allowed = approved and not blocked_slides
    return {
        "plan_review": "approved" if svg_allowed else "blocked",
        "svg_allowed": svg_allowed,
        "export_allowed": False,
        "blocked_slides": sorted(set(blocked_slides)),
        "required_fixes": list(critique.get("required_changes", [])) if isinstance(critique, Mapping) else [],
        "blocked_reason": None if svg_allowed else "Critic blocked one or more slide contracts.",
    }


def _normalize_text(value: Any) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def _contains_phrase(text: str, phrase: Any) -> bool:
    normalized_phrase = _normalize_text(phrase)
    return bool(normalized_phrase) and normalized_phrase in text


def _extract_svg_texts_by_slide(executor_result: Any) -> dict[int, str]:
    if isinstance(executor_result, Mapping):
        slides = executor_result.get("slides")
        if isinstance(slides, list):
            extracted: dict[int, str] = {}
            for index, item in enumerate(slides, start=1):
                if not isinstance(item, Mapping):
                    continue
                slide_id = item.get("slide", item.get("slide_id", index))
                if not isinstance(slide_id, int):
                    continue
                content = item.get("svg", item.get("text", item.get("content", "")))
                extracted[slide_id] = _normalize_text(content)
            return extracted
        slide_id = executor_result.get("slide", executor_result.get("slide_id", 1))
        if isinstance(slide_id, int) and "svg" in executor_result:
            return {slide_id: _normalize_text(executor_result.get("svg"))}
    if isinstance(executor_result, str):
        return {1: _normalize_text(executor_result)}
    return {}


def run_contract_qa(executor_result: Any, plan_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Check rendered SVG text against approved slide contracts before export."""

    artifact = validate_plan_artifact(plan_artifact)
    svg_texts = _extract_svg_texts_by_slide(executor_result)
    issues: list[dict[str, Any]] = []
    blocked_slides: set[int] = set()

    for contract in artifact["slide_contracts"]:
        slide_id = int(contract["slide"])
        svg_text = svg_texts.get(slide_id, "")
        if not svg_text:
            blocked_slides.add(slide_id)
            issues.append({"slide": slide_id, "issue": "missing_svg", "detail": "No SVG text found for slide."})
            continue

        if not _contains_phrase(svg_text, contract["claim"]):
            blocked_slides.add(slide_id)
            issues.append({"slide": slide_id, "issue": "missing_claim", "detail": str(contract["claim"])})

        evidence_items = list(contract.get("evidence", []))
        if evidence_items and not any(_contains_phrase(svg_text, item) for item in evidence_items):
            blocked_slides.add(slide_id)
            issues.append({"slide": slide_id, "issue": "missing_evidence", "detail": evidence_items})

        missing_keep = [item for item in contract.get("must_keep", []) if not _contains_phrase(svg_text, item)]
        if missing_keep:
            blocked_slides.add(slide_id)
            issues.append({"slide": slide_id, "issue": "missing_must_keep", "detail": missing_keep})

        avoided = [item for item in contract.get("must_avoid", []) if _contains_phrase(svg_text, item)]
        avoided.extend(item for item in GLOBAL_CONTRACT_BANNED_PHRASES if _contains_phrase(svg_text, item))
        if avoided:
            blocked_slides.add(slide_id)
            issues.append({"slide": slide_id, "issue": "must_avoid_violation", "detail": sorted(set(avoided))})

    export_allowed = not blocked_slides
    return {
        "status": "approved" if export_allowed else "blocked",
        "export_allowed": export_allowed,
        "blocked_slides": sorted(blocked_slides),
        "issues": issues,
    }


def apply_contract_qa_to_workflow_state(
    workflow_state: Mapping[str, Any], contract_qa: Mapping[str, Any]
) -> dict[str, Any]:
    """Derive export permission from contract QA; the model does not set it."""

    updated = dict(workflow_state)
    export_allowed = bool(contract_qa.get("export_allowed"))
    blocked_slides = sorted(
        set(updated.get("blocked_slides", [])) | set(contract_qa.get("blocked_slides", []))
    )
    updated.update(
        {
            "contract_qa_status": "approved" if export_allowed else "blocked",
            "export_allowed": export_allowed,
            "blocked_slides": blocked_slides,
            "contract_qa_issues": list(contract_qa.get("issues", [])),
            "blocked_reason": None if export_allowed else "Contract QA blocked one or more rendered slides.",
        }
    )
    return updated


def run_hard_gated_pipeline(
    brief: Mapping[str, Any],
    plan_call: PlanCall,
    critic_call: CriticCall,
    executor_call: ExecutorCall,
    *,
    style_system: Mapping[str, Any] | None = None,
    max_plan_revisions: int = 2,
) -> OrchestrationResult:
    """Run independent PLAN, CRITIQUE, and EXECUTE calls with code gates."""

    if max_plan_revisions < 0:
        raise ValueError("max_plan_revisions must be >= 0.")

    feedback: Mapping[str, Any] | None = None
    last_manifest: dict[str, Any] | None = None
    last_critique: dict[str, Any] | None = None

    for attempt in range(1, max_plan_revisions + 2):
        plan_input = {
            "brief": dict(brief),
            "critic_feedback": dict(feedback or {}),
        }
        raw_manifest = plan_call(plan_input)
        try:
            manifest = validate_plan_artifact(raw_manifest)
        except SchemaError as exc:
            feedback = {"schema_error": str(exc)}
            if attempt > max_plan_revisions:
                raise PipelineHalt("plan", str(exc), {"attempt": attempt}) from exc
            continue

        last_manifest = manifest
        critic_input = {
            "deck_brief": manifest["deck_brief"],
            "slide_contracts": manifest["slide_contracts"],
            "rubric": list(TENDER_CRITIC_RUBRIC),
        }
        raw_critique = critic_call(critic_input)
        critique = validate_critique_result(raw_critique, manifest)
        last_critique = critique
        workflow_state = build_workflow_state(critique)
        if not workflow_state["svg_allowed"]:
            feedback = {"critic_result": critique}
            if attempt > max_plan_revisions:
                raise PipelineHalt("critique", "Critic rejected slide_manifest.", critique)
            continue

        executor_input = {
            "approved_deck_brief": manifest["deck_brief"],
            "approved_slide_contracts": manifest["slide_contracts"],
            "style_system": dict(style_system or {}),
            "workflow_state": workflow_state,
        }
        executor_result = executor_call(executor_input)
        contract_qa = run_contract_qa(executor_result, manifest)
        workflow_state = apply_contract_qa_to_workflow_state(workflow_state, contract_qa)
        return OrchestrationResult(
            manifest=manifest,
            critique=critique,
            contract_qa=contract_qa,
            workflow_state=workflow_state,
            executor_result=executor_result,
            plan_attempts=attempt,
        )

    raise PipelineHalt(
        "critique",
        "Pipeline did not reach an approved manifest.",
        {"manifest": last_manifest, "critique": last_critique},
    )
