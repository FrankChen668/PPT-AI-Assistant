from __future__ import annotations

import json
import re
from typing import Any, Callable

from workbench.generation import call_model_generate_with_fallback, sanitize_generation_error_message
from workbench.generation_settings import GenerationConfig, load_generation_config
from workbench.project_writer import split_explicit_pages

GenerateText = Callable[[str, GenerationConfig], str]
LoadConfig = Callable[[], GenerationConfig]

_ROOT_KEYS = {"deck_thesis", "slides"}
# 单一权威（AB-01）：claim/evidence 类规划字段（claims / acceptance_criteria /
# source_refs / claim_boundary）以本模块 schema 为唯一权威；tender 实验轨字段已隔离。
CLAIM_BOUNDARY_VALUES = ("confirmed", "assumption", "inference", "open")
_SLIDE_KEYS = {
    "id",
    "title",
    "narrative_intent",
    "claims",
    "claim_boundary",
    "acceptance_criteria",
    "visual_intent",
    "content",
    "source_refs",
}
_CONTENT_KEYS = {"headline", "body", "statement", "support"}
_SPECIFIC_LAYOUT_RE = re.compile(
    r"<svg|viewbox|\b[xywh]\s*=|\b\d+\s*px\b|坐标|两列|三列|多列|卡片布局|具体版式|模板布局",
    re.I,
)
_EXPANSIVE_ASSERTION_PATTERNS = (
    (
        "certainty",
        re.compile(
            r"(?:确保|保证)"
            r"(?P<target>[^，。；！？\n]{0,20}(?:成功|结果|成效))"
        ),
    ),
    (
        "risk_reduction",
        re.compile(
            r"(?:降低|减少|规避|消除|避免)"
            r"(?P<target>[^，。；！？\n]{0,16}(?:风险|隐患|不确定性|损失|成本))"
        ),
    ),
    (
        "scaled_or_successful_outcome",
        re.compile(
            r"(?:实现|达成|形成)"
            r"(?P<target>[^，。；！？\n]{0,16}"
            r"(?:规模化(?:运营|应用|推广)?|全面覆盖|全量覆盖|推广成功|业务成效|"
            r"确定性(?:的)?(?:结果|成效)))"
        ),
    ),
)
_NON_ASSERTIVE_PREFIX_RE = re.compile(
    r"(?:如何|能否|是否|目标(?:是|为)?|计划|拟|建议|探索|评估|研究|待验证|"
    r"希望|力争|尝试|如果|若|假如|条件下|前提下)"
)
_NON_ASSERTIVE_SUFFIX_RE = re.compile(
    r"^(?:的)?(?:路径|方法|策略|方案|可行性|条件|前提|问题|目标|建议|评估|假设)"
)
_NEGATED_ASSERTION_RE = re.compile(r"(?:不|并不|不能|无法|未能|不承诺)$")
_ASSERTION_TEXT_RE = re.compile(r"[\W_]+", re.UNICODE)
_ASSERTION_CLAUSE_RE = re.compile(r"[。；！？\n]+")


def should_plan_rough_deck(payload: dict[str, Any]) -> bool:
    if str(payload.get("deck_type") or "single").strip() != "multi":
        return False
    try:
        page_count = int(payload.get("page_count") or 1)
    except (TypeError, ValueError):
        return False
    if page_count <= 1:
        return False
    if payload.get("source_inputs") and not str(payload.get("source_grounded_context") or "").strip():
        return False
    if payload.get("slides"):
        return False
    if payload.get("existing_blueprint") is True:
        return False
    prompt = str(payload.get("raw_prompt") or payload.get("prompt") or "").strip()
    if not prompt or split_explicit_pages(prompt):
        return False
    return True


def build_content_planning_prompt(source_text: str, page_count: int) -> str:
    return f"""你是整套 PPT 的内容规划者。请把用户提供的一段粗糙材料规划成恰好 {page_count} 页，输出单个 JSON 对象，不要输出 Markdown。

目标：形成一句话核心观点和连续的 Takeaway Spine。每页只回答一个问题，使用判断型标题；先给一个核心结论，再给用户材料中的支撑内容和对受众的含义。允许合并、压缩、调整顺序和删除重复内容，不要机械套用“背景、现状、问题、方案、价值、计划、风险、总结”。

事实边界：只允许重组、压缩和改写用户原始输入。不允许添加用户原始输入中不存在的事实、数字、客户、法规要求或项目结果。材料不足时降低信息量或写“待补充”，不得虚构内容凑页数。

结论强度不得高于原文。只有原文明确表达了同等强度的结果时，才能保留“确保/保证某项结果”“降低某类风险或成本”“实现规模化、全面覆盖或推广成功”“形成确定性业务成效”等结论。原文如果只是目标、计划、建议、问题、评估、条件、可能性或待验证假设，输出必须保留这些限定语，或省略该结论；不得把它改写成已经发生、必然发生或具有确定因果关系的结果。不要机械屏蔽词语：原文明示的结论可以正常保留，否定句、问题句和路径描述也要按原意保留。

内容规划与视觉布局分开。visual_intent 只说明需要表达的业务关系和信息主次，不得指定模板、卡片、坐标、SVG、具体版式或画布参数。

证据边界：每页必须对 claims[0] 标注 claim_boundary，对照用户原文四选一：confirmed 指原文明确陈述的事实或已发生结果；assumption 指原文作为前提或假设提出、尚未证实的内容；inference 指由原文推导但原文未直接陈述的判断；open 指原文未覆盖或无法判断出身。不确定时选 open，不得臆造。

JSON 结构必须严格为：
{{
  "deck_thesis": "一句话核心观点",
  "slides": [
    {{
      "id": 1,
      "title": "判断型标题",
      "narrative_intent": "本页在整套论证中的作用",
      "claims": ["唯一核心结论", "可选辅助判断"],
      "claim_boundary": "confirmed | assumption | inference | open",
      "acceptance_criteria": ["读者看完应形成的判断"],
      "visual_intent": "核心判断、支撑事实、业务含义之间的关系和主次",
      "content": {{
        "headline": "适合上屏的标题",
        "body": "仅来自用户材料的支撑内容",
        "support": "对受众的含义，材料不足可写待补充"
      }},
      "source_refs": []
    }}
  ]
}}

硬约束：slides 数量必须等于 {page_count}；id 从 1 连续递增；claims[0] 是本页唯一核心结论，claims[1:] 只能是辅助判断；claim_boundary 只能取 confirmed/assumption/inference/open 四个枚举值之一，标注对象是 claims[0]；不得输出空页；不得加入其他字段。

用户原始输入：
{source_text.strip()}
"""


def _parse_json_response(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.I | re.S)
    if fenced:
        text = fenced.group(1).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("content planning response root must be an object")
    return payload


def _non_empty_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must be non-empty")
    return text


def _string_list(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of strings")
    items = [item.strip() for item in value if item.strip()]
    if not allow_empty and not items:
        raise ValueError(f"{field} must not be empty")
    return items


def _normalize_claim_boundary(value: object) -> tuple[str, bool]:
    """Return (boundary, defaulted): 非法或缺失归一为 open 并计入 defaulted 计数（AB-03）。"""
    text = str(value or "").strip().lower()
    if text in CLAIM_BOUNDARY_VALUES:
        return text, False
    return "open", True


def _is_non_assertive_context(clause: str, start: int, end: int) -> bool:
    prefix = re.split(r"[，,:：；;]", clause[:start])[-1]
    suffix = clause[end:]
    return bool(
        _NON_ASSERTIVE_PREFIX_RE.search(prefix)
        or _NON_ASSERTIVE_SUFFIX_RE.search(suffix)
        or _NEGATED_ASSERTION_RE.search(prefix[-4:])
    )


def _normalize_assertion_target(value: str) -> str:
    return _ASSERTION_TEXT_RE.sub("", str(value or "").lower())


def _same_assertion_target(left: str, right: str) -> bool:
    left_text = _normalize_assertion_target(left)
    right_text = _normalize_assertion_target(right)
    if not left_text or not right_text:
        return False
    return left_text in right_text


def _expansive_assertions(text: str) -> list[tuple[str, str]]:
    assertions: list[tuple[str, str]] = []
    for clause in _ASSERTION_CLAUSE_RE.split(text):
        for kind, pattern in _EXPANSIVE_ASSERTION_PATTERNS:
            for match in pattern.finditer(clause):
                if not _is_non_assertive_context(clause, match.start(), match.end()):
                    assertions.append((kind, match.group("target")))
    return assertions


def _validate_source_grounded_conclusions(
    source_text: str,
    conclusion_fields: list[tuple[str, str]],
) -> None:
    supported = _expansive_assertions(source_text)
    for field, text in conclusion_fields:
        for kind, target in _expansive_assertions(text):
            if any(
                source_kind == kind
                and _same_assertion_target(target, source_target)
                for source_kind, source_target in supported
            ):
                continue
            raise ValueError(f"{field} contains unsupported expansive conclusion: {kind}")


def _validate_planning_payload(
    payload: dict[str, Any],
    page_count: int,
    source_text: str,
) -> dict[str, Any]:
    extra_root_keys = set(payload) - _ROOT_KEYS
    if extra_root_keys:
        raise ValueError(f"unexpected content planning root keys: {sorted(extra_root_keys)}")
    deck_thesis = _non_empty_text(payload.get("deck_thesis"), "deck_thesis")
    raw_slides = payload.get("slides")
    if not isinstance(raw_slides, list) or len(raw_slides) != page_count:
        raise ValueError("content planning slide count does not match the requested page count")

    conclusion_fields = [("deck_thesis", deck_thesis)]
    slides: list[dict[str, Any]] = []
    claim_boundary_defaulted_count = 0
    for expected_id, raw_slide in enumerate(raw_slides, start=1):
        if not isinstance(raw_slide, dict):
            raise ValueError(f"slide {expected_id} must be an object")
        extra_slide_keys = set(raw_slide) - _SLIDE_KEYS
        if extra_slide_keys:
            raise ValueError(f"slide {expected_id} has unexpected keys: {sorted(extra_slide_keys)}")
        if raw_slide.get("id") != expected_id:
            raise ValueError("content planning slide ids must be continuous and start at 1")

        title = _non_empty_text(raw_slide.get("title"), f"slides[{expected_id}].title")
        narrative_intent = _non_empty_text(
            raw_slide.get("narrative_intent"),
            f"slides[{expected_id}].narrative_intent",
        )
        claims = _string_list(raw_slide.get("claims"), f"slides[{expected_id}].claims")
        claim_boundary, boundary_defaulted = _normalize_claim_boundary(raw_slide.get("claim_boundary"))
        if boundary_defaulted:
            claim_boundary_defaulted_count += 1
        acceptance_criteria = _string_list(
            raw_slide.get("acceptance_criteria"),
            f"slides[{expected_id}].acceptance_criteria",
        )
        visual_intent = _non_empty_text(
            raw_slide.get("visual_intent"),
            f"slides[{expected_id}].visual_intent",
        )
        if _SPECIFIC_LAYOUT_RE.search(visual_intent):
            raise ValueError(f"slides[{expected_id}].visual_intent contains specific layout instructions")
        _string_list(
            raw_slide.get("source_refs"),
            f"slides[{expected_id}].source_refs",
            allow_empty=True,
        )
        source_refs: list[str] = []
        content = raw_slide.get("content")
        if not isinstance(content, dict):
            raise ValueError(f"slides[{expected_id}].content must be an object")
        extra_content_keys = set(content) - _CONTENT_KEYS
        if extra_content_keys:
            raise ValueError(
                f"slides[{expected_id}].content has unexpected keys: {sorted(extra_content_keys)}"
            )
        if not all(isinstance(value, str) for value in content.values()):
            raise ValueError(f"slides[{expected_id}].content values must be strings")
        normalized_content = {
            key: str(content.get(key) or "").strip()
            for key in ("headline", "body", "statement", "support")
            if str(content.get(key) or "").strip()
        }
        conclusion_fields.append((f"slides[{expected_id}].claims[0]", claims[0]))
        body = normalized_content.get("body") or normalized_content.get("support") or claims[0]
        if not body:
            raise ValueError(f"slides[{expected_id}] must not be empty")
        slides.append(
            {
                "id": expected_id,
                "title": title,
                "body": body,
                "prompt": body,
                "narrative_intent": narrative_intent,
                "claims": claims,
                "claim_boundary": claim_boundary,
                "acceptance_criteria": acceptance_criteria,
                "visual_intent": visual_intent,
                "content": normalized_content,
                "source_refs": source_refs,
            }
        )
    _validate_source_grounded_conclusions(source_text, conclusion_fields)
    return {
        "status": "used",
        "deck_thesis": deck_thesis,
        "slides": slides,
        "reason": "",
        "claim_boundary_defaulted_count": claim_boundary_defaulted_count,
    }


def plan_rough_deck_content(
    payload: dict[str, Any],
    *,
    config: GenerationConfig | None = None,
    config_loader: LoadConfig | None = None,
    generate: GenerateText | None = None,
) -> dict[str, Any]:
    if not should_plan_rough_deck(payload):
        return {"status": "bypass", "deck_thesis": "", "slides": [], "reason": "not_eligible"}

    try:
        page_count = int(payload.get("page_count") or 1)
        effective_config = config or (config_loader() if config_loader else load_generation_config())
        if not effective_config.configured():
            raise ValueError("generation provider is not configured")
        generator = generate or call_model_generate_with_fallback
        source_text = str(
            payload.get("source_grounded_context")
            or payload.get("raw_prompt")
            or payload.get("prompt")
            or ""
        )
        raw_result = generator(
            build_content_planning_prompt(
                source_text,
                page_count,
            ),
            effective_config,
        )
        return _validate_planning_payload(
            _parse_json_response(raw_result),
            page_count,
            source_text,
        )
    except Exception as exc:
        return {
            "status": "fallback",
            "deck_thesis": "",
            "slides": [],
            "reason": sanitize_generation_error_message(exc),
        }
