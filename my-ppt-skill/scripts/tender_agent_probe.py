"""Real-model probe for tender PLAN / CRITIQUE / optional EXECUTE gates.

EXPERIMENTAL TRACK - ISOLATED. The tender slide contract exercised here
(claim / evidence / must_keep / page_type) is experiment-only; the single
authority for claim/evidence-class planning fields is
``workbench/content_planning.py``. Mainline modules must not import
``tender_agent_*`` (guarded by
``my-ppt-skill/tests/test_tender_agent_isolation.py``).

This is a small validation tool, not a Workbench generation path. It reuses the
configured text model helper and writes a JSON report so we can inspect whether
real model outputs respect the hard-gated tender orchestration contract.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from generate_executor_packet import build_executor_packet, find_slide_id_by_source_page
from tender_agent_orchestrator import (
    TENDER_CRITIC_RUBRIC,
    PipelineHalt,
    validate_critique_result,
    validate_plan_artifact,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workbench.generation import call_model_generate, last_generation_trace, load_generation_config  # noqa: E402
from workbench.generation_settings import GenerationConfig  # noqa: E402

JsonModelCall = Callable[[str], str]


@dataclass(frozen=True)
class ProbeResult:
    mode: str
    source_page: str
    manifest: dict[str, Any]
    critique: dict[str, Any]
    executor_context: dict[str, Any]
    executor_called: bool
    executor_result: Any
    plan_attempts: int
    provider: str
    model: str
    trace: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "source_page": self.source_page,
            "manifest": self.manifest,
            "critique": self.critique,
            "executor_context": self.executor_context,
            "executor_called": self.executor_called,
            "executor_result": self.executor_result,
            "plan_attempts": self.plan_attempts,
            "provider": self.provider,
            "model": self.model,
            "trace": self.trace,
        }


def extract_json_object(text: str) -> dict[str, Any]:
    content = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(?P<body>.*?)```", content, flags=re.I | re.S)
    if fenced:
        content = fenced.group("body").strip()
    decoder = json.JSONDecoder()
    for match in re.finditer(r"{", content):
        try:
            payload, _ = decoder.raw_decode(content[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("Model response did not contain a JSON object.")


def read_selected_page_prompt(project_path: Path, source_page: str) -> str:
    source_path = project_path / "sources" / "selected_7p_prompts.md"
    text = source_path.read_text(encoding="utf-8")
    page = source_page.upper().strip()
    pattern = re.compile(rf"(^##\s+{re.escape(page)}\b.*?)(?=^##\s+P\d+\b|\Z)", re.M | re.S)
    match = pattern.search(text)
    if not match:
        raise FileNotFoundError(f"{page} not found in {source_path}.")
    return match.group(1).strip()


def load_existing_executor_context(project_path: Path, source_page: str) -> dict[str, Any]:
    """Reuse the existing Executor packet as the visual/design handoff."""

    slide_id = find_slide_id_by_source_page(project_path, source_page)
    if slide_id is None:
        return {}
    return build_executor_packet(project_path, slide_id=slide_id)


def build_plan_prompt(input_payload: Mapping[str, Any]) -> str:
    brief = input_payload.get("brief", {})
    feedback = input_payload.get("critic_feedback", {})
    return f"""你是[CLIENT_NAME] PPT 的 PLAN 阶段，只负责输出结构化 slide_manifest，不生成 SVG，不做自我审批。

只输出 JSON，不要 Markdown，不要解释。

必须符合这个 schema：
{{
  "deck_brief": {{
    "audience": "[CLIENT_NAME]供应链合规评审委员会",
    "bid_scenario": "正式[CLIENT_NAME]技术方案评审",
    "winning_strategy": "突出低风险交付和可复核合规闭环，而不是炫技",
    "evaluation_criteria": ["可信度", "风险可控", "交付能力"],
    "tone": "正式、稳健、可信、克制",
    "visual_direction": "深红识别色、冷灰底色、咨询式信息结构"
  }},
  "slide_contracts": [
    {{
      "slide": 1,
      "source_page": "P3",
      "page_type": "problem / solution / proof / comparison / roadmap / team / cost / risk 中的一种",
      "claim": "本页 5 秒内可读的一句话甲方价值结论，不能只复述标题",
      "evidence": ["数据 / 机制 / 流程 / 案例 / 文件证据 / 规则映射 中的具体证据"],
      "layout_intent": "closed_loop / matrix / layered_blueprint / process / comparison / capability_map 中的一种",
      "must_keep": ["必须保留的信息"],
      "must_avoid": ["必须避免的问题"],
      "success_check": "评委看完后应形成的判断"
    }}
  ]
}}

硬约束：
- 不得生成页面设计稿或 SVG。
- 不得把能力展示写成甲方价值。
- 不得新增源文档没有提供的事实、数字、案例或承诺。
- claim 必须表达“这页对甲方有什么价值”，不能只重复页面标题或能力名词。
- claim 必须采用“咨询风格通过/以 [机制、流程或能力]，帮助瑞浦 [甲方价值]”的表达方向。
- claim 不得写成“本页让评委形成判断/本页让评委确信/本页回答……”这类页面意图说明。
- claim 尽量控制在 45 个汉字左右，确保 5 秒内可读。
- evidence 至少 1 条，必须来自源页可支持的机制、流程、文件证据、规则映射或案例类型。
- 如果源文档未提供数字，不得编造任何比例、周期、通过率、成本降低等量化指标。
- 不得使用“自动判定合规、保证通过、全部覆盖、替代人工判断”等绝对化承诺。
- source_page 必须使用输入页码。
- 如果收到 critic_feedback，必须修正被打回的问题。

输入 brief：
{json.dumps(brief, ensure_ascii=False, indent=2)}

critic_feedback：
{json.dumps(feedback, ensure_ascii=False, indent=2)}
"""


def build_critique_prompt(input_payload: Mapping[str, Any]) -> str:
    deck_brief = input_payload.get("deck_brief", {})
    contracts = input_payload.get("slide_contracts", input_payload.get("slide_manifest", {}))
    rubric = input_payload.get("rubric", TENDER_CRITIC_RUBRIC)
    return f"""你是[CLIENT_NAME] PPT 的 CRITIQUE 阶段，只负责按 rubric 审查 deck_brief + slide_contracts。

只输出 JSON，不要 Markdown，不要解释。不得生成 SVG。不得替 PLAN 重写页面契约。

输出必须符合：
{{
  "pass": false,
  "slide_scores": [
    {{
      "slide": 1,
      "score": 0,
      "claim_score": 0,
      "evidence_score": 0,
      "bid_relevance_score": 0,
      "differentiation_score": 0,
      "clarity_score": 0,
      "necessity_score": 0,
      "decision": "blocked",
      "failed_criteria": ["buyer_value_over_capability"]
    }}
  ],
  "required_changes": [
    {{
      "slide": 1,
      "reason": "具体打回原因",
      "required_change": "必须怎么改"
    }}
  ]
}}

判定规则：
- 如果页面只是能力展示，缺少甲方价值，必须 pass=false。
- 如果核心结论空泛，不能在 5 秒内读懂，必须 pass=false。
- 如果 evidence_type 为空、none、无、泛泛背书，必须 pass=false。
- 如果 audience_pain 不具体，必须 pass=false。
- pass=false 时 required_changes 必须非空。
- pass=true 时 required_changes 必须为空。
- score 是 0-100 分；pass=true 时每页 score 必须 >=80。
- claim_score / evidence_score / bid_relevance_score / differentiation_score / \
clarity_score / necessity_score 均为 0-3 分。
- pass=true 时所有维度分必须 >=2，decision 必须是 approved。
- score <80 时必须 pass=false，并给出 required_changes。
- 不得要求新增源文档没有提供的客户案例、收益数字、审计通过率、周期缩短数值或绝对承诺。
- 如果源文档未提供数字，required_change 只能要求补强机制、流程、规则映射、证据类型或甲方价值表达，不能要求编造量化指标。
- 对[CLIENT_NAME]页而言，“规则映射、流程机制、文件证据、运营指标口径”都可以作为证据类型，不应只把数字当作证据。
- required_change 中不得出现“X天、Y小时、XX%、100%、自动合规审查、保证通过、全部覆盖、替代人工判断、\
通过率提升”等未提供或绝对化表达。
- 修改建议只能使用克制表达，例如“降低资料组织风险、提升审查响应一致性、形成可复核运行机制”，不能要求承诺结果。

rubric：
{json.dumps(rubric, ensure_ascii=False, indent=2)}

deck_brief：
{json.dumps(deck_brief, ensure_ascii=False, indent=2)}

slide_contracts：
{json.dumps(contracts, ensure_ascii=False, indent=2)}
"""


def build_execute_prompt(input_payload: Mapping[str, Any]) -> str:
    deck_brief = input_payload.get("approved_deck_brief", {})
    contracts = input_payload.get("approved_slide_contracts", input_payload.get("approved_slide_manifest", {}))
    executor_context = input_payload.get("approved_executor_context", {})
    style_system = input_payload.get("style_system", {})
    source_excerpt = input_payload.get("approved_source_excerpt", "")
    return f"""你是[CLIENT_NAME] PPT 的 EXECUTE 阶段，只能根据 approved deck_brief + slide_contracts 生成单页 SVG。

只输出 SVG，不要解释。不得重写页面目标、核心结论或证据类型。
硬约束：
- 页面文案只能来自 approved_deck_brief、approved_slide_contracts 和 approved_source_excerpt。
- 页面结构必须优先遵守 approved_executor_context 中来自项目现有 generate_executor_packet 的 visual_contract、\
narrative_composition 和 design_story。
- approved_slide_contracts 控制事实和说服力，approved_executor_context 控制视觉表达；不得绕开现有 \
Executor packet 重新自由设计。
- 不得新增 approved_source_excerpt 中没有出现的技术词、能力点、服务项、指标或承诺。
- 不得新增“区块链存证、端到端审计追踪、持续合规监控、法规更新跟踪”等源页未给出的具体能力表达。
- 如果需要细化模块，只能改写源页已提供的现状调研、组织职责、管理流程、证据链、供应商评估、文件审核、\
报告输出、运营支持等内容。

approved_deck_brief：
{json.dumps(deck_brief, ensure_ascii=False, indent=2)}

approved_slide_contracts：
{json.dumps(contracts, ensure_ascii=False, indent=2)}

approved_source_excerpt：
{str(source_excerpt)[:7000]}

approved_executor_context：
{json.dumps(executor_context, ensure_ascii=False, indent=2)}

style_system：
{json.dumps(style_system, ensure_ascii=False, indent=2)}
"""


def weak_manifest(source_page: str) -> dict[str, Any]:
    return {
        "deck_brief": {
            "audience": "[CLIENT_NAME]供应链合规评审委员会",
            "bid_scenario": "正式[CLIENT_NAME]技术方案评审",
            "winning_strategy": "突出低风险交付和可复核合规闭环，而不是炫技",
            "evaluation_criteria": ["可信度", "风险可控", "交付能力"],
            "tone": "正式、稳健、可信、克制",
            "visual_direction": "深红识别色、冷灰底色、咨询式信息结构",
        },
        "slide_contracts": [
            {
                "slide": 1,
                "source_page": source_page,
                "page_type": "solution",
                "claim": "我们能力强，平台功能完整",
                "evidence": ["none"],
                "layout_intent": "capability_map",
                "must_keep": ["能力完整"],
                "must_avoid": ["不要太复杂"],
                "success_check": "评委认为我们很强",
            }
        ]
    }


def make_model_json_call(config: GenerationConfig, timeout: int) -> Callable[[str], dict[str, Any]]:
    def call(prompt: str) -> dict[str, Any]:
        return extract_json_object(call_model_generate(prompt, config, timeout=timeout))

    return call


def run_probe(
    *,
    project_path: Path,
    source_page: str,
    mode: str,
    model_json_call: Callable[[str], dict[str, Any]],
    model_text_call: JsonModelCall | None = None,
    provider: str = "",
    model: str = "",
    allow_execute: bool = False,
    max_plan_revisions: int = 2,
) -> ProbeResult:
    page = source_page.upper().strip()
    page_prompt = ""
    executor_context: dict[str, Any] = {}
    if mode == "normal":
        page_prompt = read_selected_page_prompt(project_path, page)
        executor_context = load_existing_executor_context(project_path, page)
        brief = {
            "source_page": page,
            "project": project_path.name,
            "page_prompt": page_prompt[:7000],
        }
        feedback: Mapping[str, Any] = {}
        manifest: dict[str, Any] | None = None
        critique: dict[str, Any] | None = None
        plan_attempts = 0
        for attempt in range(1, max_plan_revisions + 2):
            plan_attempts = attempt
            manifest = validate_plan_artifact(
                model_json_call(build_plan_prompt({"brief": brief, "critic_feedback": feedback}))
            )
            critique = validate_critique_result(
                model_json_call(
                    build_critique_prompt(
                        {
                            "deck_brief": manifest["deck_brief"],
                            "slide_contracts": manifest["slide_contracts"],
                            "rubric": list(TENDER_CRITIC_RUBRIC),
                        }
                    )
                ),
                manifest,
            )
            if critique["pass"]:
                break
            feedback = {"critic_result": critique}
            if attempt > max_plan_revisions:
                raise PipelineHalt(
                    "critique",
                    "Critic rejected slide_manifest.",
                    {
                        "mode": mode,
                        "source_page": page,
                        "manifest": manifest,
                        "critique": critique,
                        "executor_called": False,
                        "plan_attempts": plan_attempts,
                    },
                )
        if manifest is None or critique is None:
            raise PipelineHalt("plan", "PLAN did not produce a slide_manifest.")
    elif mode == "weak":
        manifest = validate_plan_artifact(weak_manifest(page))
        plan_attempts = 0
        critique = validate_critique_result(
            model_json_call(
                build_critique_prompt(
                    {
                        "deck_brief": manifest["deck_brief"],
                        "slide_contracts": manifest["slide_contracts"],
                        "rubric": list(TENDER_CRITIC_RUBRIC),
                    }
                )
            ),
            manifest,
        )
    else:
        raise ValueError("mode must be normal or weak.")

    executor_called = False
    executor_result: Any = None
    if not critique["pass"]:
        raise PipelineHalt(
            "critique",
            "Critic rejected slide_manifest.",
            {
                "mode": mode,
                "source_page": page,
                "manifest": manifest,
                "critique": critique,
                "executor_called": False,
                "plan_attempts": plan_attempts,
            },
        )

    if allow_execute:
        if model_text_call is None:
            raise ValueError("model_text_call is required when allow_execute=True.")
        executor_called = True
        executor_result = model_text_call(
            build_execute_prompt(
                {
                    "approved_deck_brief": manifest["deck_brief"],
                    "approved_slide_contracts": manifest["slide_contracts"],
                    "style_system": {
                        "canvas": "1280x720",
                        "style": "formal tender consulting",
                        "primary_color": "#932141",
                    },
                    "approved_source_excerpt": page_prompt,
                    "approved_executor_context": executor_context,
                }
            )
        )

    return ProbeResult(
        mode=mode,
        source_page=page,
        manifest=manifest,
        critique=critique,
        executor_context=executor_context,
        executor_called=executor_called,
        executor_result=executor_result,
        plan_attempts=plan_attempts,
        provider=provider,
        model=model,
        trace=last_generation_trace(),
    )


def default_output_path(project_path: Path, source_page: str, mode: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return project_path / "qa" / f"tender-agent-probe-{mode}-{source_page.lower()}-{stamp}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a real-model tender agent gate probe.")
    parser.add_argument("project", help="Project path, e.g. projects/[PROJECT_EXAMPLE]")
    parser.add_argument("--source-page", default="P3")
    parser.add_argument("--mode", choices=("normal", "weak"), default="normal")
    parser.add_argument("--provider", default="")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--allow-execute", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    project_path = Path(args.project)
    if not project_path.is_absolute():
        project_path = Path.cwd() / project_path
    config = load_generation_config(provider_override=args.provider)
    if not config.configured():
        raise SystemExit(f"Provider {config.provider} is not configured.")

    json_call = make_model_json_call(config, args.timeout)

    def text_call(prompt: str) -> str:
        return call_model_generate(prompt, config, timeout=args.timeout)

    output = Path(args.output) if args.output else default_output_path(project_path, args.source_page, args.mode)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = run_probe(
            project_path=project_path,
            source_page=args.source_page,
            mode=args.mode,
            model_json_call=json_call,
            model_text_call=text_call,
            provider=config.provider,
            model=config.model,
            allow_execute=bool(args.allow_execute),
        ).to_dict()
    except PipelineHalt as exc:
        result = {
            "halted": True,
            "stage": exc.stage,
            "message": str(exc),
            "payload": exc.payload,
            "provider": config.provider,
            "model": config.model,
            "trace": last_generation_trace(),
        }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"probe_report={output}")
    if result.get("halted"):
        print(f"halted_stage={result.get('stage')}")
    else:
        print(f"critic_pass={result.get('critique', {}).get('pass')}")
        print(f"executor_called={result.get('executor_called')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
