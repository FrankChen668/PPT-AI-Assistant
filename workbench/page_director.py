from __future__ import annotations

import re
from typing import Any


DEFAULT_RULE: dict[str, Any] = {
    "page_type": "default_consulting",
    "keywords": (),
    "pattern_id": "default_consulting_board",
    "archetype": "conclusion-first evidence board",
    "composition": "用结论先行的标题、3-4 个证据模块和底部 takeaway 保持清晰表达。",
    "must_answer_question": "这页希望决策者在 10 秒内记住什么判断？",
    "proof_objects": ["核心判断", "证据块", "结论收束"],
    "avoid_repetition_with": [],
}

PAGE_RULES: list[dict[str, Any]] = [
    {
        "page_type": "capability_core_map",
        "keywords": (
            "价值链合规",
            "能力核心",
            "核心能力",
            "能力图",
            "转向",
            "不是系统",
            "一套能力",
            "可运行",
            "合规追溯能力",
            "能力体系",
        ),
        "pattern_id": "capability_core_map",
        "archetype": "capability core map with supporting domains",
        "composition": "用中心能力核 + 周边能力域表达能力建设目标，说明系统、数据、供应商协同和运营机制如何共同形成可运行能力。",
        "must_answer_question": "为什么本页强调建设一套可运行能力，而不是采购或交付单一系统？",
        "proof_objects": ["中心能力核", "能力域", "运行机制"],
        "avoid_repetition_with": ["pressure_to_upgrade", "proof_chain_map"],
    },
    {
        "page_type": "pressure_to_upgrade",
        "keywords": ("外部规则", "市场压力", "内部响应", "能力升级", "外部压力", "内部能力升级"),
        "pattern_id": "pressure_to_upgrade",
        "archetype": "left-pressure right-upgrade transformation map",
        "composition": "左侧外部压力，右侧能力升级，用一方向转化路径表达业务响应。",
        "must_answer_question": "外部压力如何具体转化为内部能力建设动作？",
        "proof_objects": ["外部压力源", "内部升级动作", "转化路径"],
        "avoid_repetition_with": ["capability_core_map", "governance_columns"],
    },
    {
        "page_type": "proof_chain_map",
        "keywords": ("UFLPA", "证明链", "上游材料", "成品", "可审计", "强迫劳动"),
        "pattern_id": "proof_chain_map",
        "archetype": "proof-chain penetration map",
        "composition": "从成品到上游材料展开证明链对象，强调证据可验证和可审计。",
        "must_answer_question": "如何证明从成品到上游材料的合规链条真实存在？",
        "proof_objects": ["链路对象", "证据对象", "校验关系"],
        "avoid_repetition_with": ["lifecycle_extension_flow", "comparison_decision_matrix"],
    },
    {
        "page_type": "lifecycle_extension_flow",
        "keywords": ("关键原材料", "碳足迹", "延伸", "欧洲方向", "强迫劳动"),
        "pattern_id": "lifecycle_extension_flow",
        "archetype": "lifecycle extension flow",
        "composition": "按能力边界扩展顺序，表达从当前追溯范围向更高监管要求的延展路径。",
        "must_answer_question": "追溯能力应按什么顺序扩展，才能满足欧洲方向要求？",
        "proof_objects": ["当前能力边界", "扩展目标", "阶段路径"],
        "avoid_repetition_with": ["proof_chain_map", "governance_columns"],
    },
    {
        "page_type": "governance_columns",
        "keywords": ("SEIA 101", "ISO 22095", "可验证", "可审计", "可管理", "标准"),
        "pattern_id": "governance_columns",
        "archetype": "governance columns board",
        "composition": "多列治理结构承载标准条款、组织动作与审计输出。",
        "must_answer_question": "标准要求如何落到可执行、可审计的治理动作？",
        "proof_objects": ["标准要求", "治理动作", "审计输出"],
        "avoid_repetition_with": ["pressure_to_upgrade", "responsibility_swimlane"],
    },
    {
        "page_type": "dual_business_traceability_map",
        "keywords": ("双业务", "储能", "动力", "单一产品链路", "不能采用单一", "多业务"),
        "pattern_id": "dual_business_traceability_map",
        "archetype": "dual-business traceability map",
        "composition": "并列表达动力与储能业务差异，强调统一底座与差异化链路并存。",
        "must_answer_question": "为什么双业务场景不能使用单一产品链路模型？",
        "proof_objects": ["业务差异", "共性底座", "差异化链路"],
        "avoid_repetition_with": ["comparison_decision_matrix", "governance_columns"],
    },
    {
        "page_type": "data_integration_evidence",
        "keywords": ("三流", "物料流", "合同流", "资金流", "证据", "证据文件", "勾稽", "证明链"),
        "pattern_id": "three_flow_evidence_chain",
        "archetype": "three-flow evidence cross-check map",
        "composition": "用物料流、合同流、资金流与证据文件构成交叉校验关系，底部收束为勾稽证明链。",
        "must_answer_question": "三流与证据如何互相勾稽并形成可解释证明链？",
        "proof_objects": ["物料流", "合同流", "资金流", "证据链"],
        "avoid_repetition_with": ["proof_chain_map", "supplier_penetration_chain"],
    },
    {
        "page_type": "supplier_penetration",
        "keywords": ("T1", "T2", "TN", "供应商", "供应链", "穿透", "填报", "整改", "评分", "采购推动"),
        "pattern_id": "supplier_penetration_chain",
        "archetype": "supplier hierarchy with source-backed cross-layer actions",
        "composition": "只按原文明示的供应商层级端点和跨层动作组织页面。",
        "must_answer_question": "原文明示的供应商层级端点之间发生了哪些跨层动作？",
        "proof_objects": ["原文明示的层级端点", "原文明示的跨层动作"],
        "avoid_repetition_with": ["responsibility_swimlane", "three_flow_evidence_chain"],
    },
    {
        "page_type": "organization_responsibility",
        "keywords": ("组织", "职责", "责任", "谁发起", "谁提供", "谁审核", "谁授权", "协同机制", "部门"),
        "pattern_id": "responsibility_swimlane",
        "archetype": "swimlane responsibility map",
        "composition": "用责任泳道或责任矩阵说明谁发起、谁补资料、谁审核、谁推动供应商、谁授权发布。",
        "must_answer_question": "多组织协同下如何明确责任边界与交接关系？",
        "proof_objects": ["角色泳道", "职责动作", "协同接口"],
        "avoid_repetition_with": ["governance_columns", "comparison_decision_matrix"],
    },
    {
        "page_type": "business_process",
        "keywords": ("流程", "链路", "端到端", "触发", "处理", "输出", "闭环"),
        "pattern_id": "business_process_flow",
        "archetype": "horizontal process with optional swimlanes",
        "composition": "用横向主流程承载关键动作，必要时叠加角色泳道，底部明确输出和闭环。",
        "must_answer_question": "这条流程的关键触发、处理和输出是什么？",
        "proof_objects": ["触发条件", "处理动作", "输出结果"],
        "avoid_repetition_with": ["roadmap_lane_milestones"],
    },
    {
        "page_type": "comparison_decision",
        "keywords": ("对比", "不同", "区别", "不等于", "A/B/C", "评价维度", "质量追溯", "合规追溯"),
        "pattern_id": "comparison_decision_matrix",
        "archetype": "comparison matrix with emphasized recommendation column",
        "composition": "用对比矩阵区分对象、目标、使用方、输入和输出，并突出推荐或目标态列。",
        "must_answer_question": "多种方案/路径的核心差异和推荐结论是什么？",
        "proof_objects": ["对比维度", "差异项", "推荐结论"],
        "avoid_repetition_with": ["capability_core_map", "dual_business_traceability_map"],
    },
    {
        "page_type": "capability_loop_summary",
        "keywords": ("可审查", "可协同", "可扩展", "可运营", "总结", "承接下章", "长期运行"),
        "pattern_id": "capability_loop_summary",
        "archetype": "four-capability loop with bottom transition bar",
        "composition": "用四能力闭环围绕中心能力，底部用承接条连接下一章方案。",
        "must_answer_question": "闭环能力如何支撑长期运行和后续章节承接？",
        "proof_objects": ["中心能力", "四能力环", "承接条"],
        "avoid_repetition_with": ["capability_core_map"],
    },
    {
        "page_type": "architecture_layered",
        "keywords": ("架构", "平台", "系统", "数据底座", "接口", "治理"),
        "pattern_id": "layered_architecture",
        "archetype": "layered architecture map",
        "composition": "用分层架构表达用户、能力、数据、系统和治理边界。",
        "must_answer_question": "平台架构分层如何支撑业务目标与治理边界？",
        "proof_objects": ["分层对象", "边界关系", "能力承载"],
        "avoid_repetition_with": ["business_process_flow"],
    },
    {
        "page_type": "roadmap_execution",
        "keywords": ("路线图", "阶段", "里程碑", "计划", "交付"),
        "pattern_id": "roadmap_lane_milestones",
        "archetype": "lane roadmap with milestones",
        "composition": "用阶段泳道和里程碑说明目标、任务、交付物和风险控制。",
        "must_answer_question": "分阶段里程碑如何保证交付与风险受控？",
        "proof_objects": ["阶段目标", "里程碑", "风险控制"],
        "avoid_repetition_with": ["business_process_flow"],
    },
    {
        "page_type": "risk_governance",
        "keywords": ("风险", "应对", "治理", "责任机制", "升级"),
        "pattern_id": "risk_control_owner_matrix",
        "archetype": "risk-control-owner matrix",
        "composition": "用风险、控制动作、责任方和升级机制形成可追踪治理表。",
        "must_answer_question": "关键风险如何被控制并分配到明确 owner？",
        "proof_objects": ["风险项", "控制动作", "责任 owner"],
        "avoid_repetition_with": ["governance_columns"],
    },
]

CIRCLE_RULES: list[dict[str, Any]] = [
    {
        "circle_role": "component",
        "page_type": "dashboard_ring_component",
        "keywords": ("管理驾驶舱", "轻量驾驶舱", "数据看板", "仪表盘", "任务指标", "文件指标", "供应商指标", "风险指标", "数据指标", "完成率", "齐套率", "环形 KPI", "KPI 环", "donut"),
        "pattern_id": "dashboard_ring_component",
        "archetype": "dashboard_ring_component",
        "composition": "dashboard_ring_component",
        "intent": "Use panels or a KPI tree as the primary structure, with 1-2 local ring metrics as dashboard components.",
        "anti_patterns": ["full-page circular hero", "turning the dashboard into a mechanism loop", "decorative ring charts"],
    },
    {
        "circle_role": "loop",
        "page_type": "capability_loop_circle",
        "keywords": ("四能力闭环图", "围绕中心", "箭头形成闭环", "闭环图", "闭环", "长期能力", "长期运行", "可审查", "可协同", "可扩展", "可运营", "承接下一章"),
        "pattern_id": "capability_loop_circle",
        "archetype": "capability_loop_circle",
        "composition": "capability_loop_circle",
        "intent": "Use a center capability with an outer circular arrow path and four capability pillars to express repeatable operation.",
        "anti_patterns": ["fixed phase roadmap", "one-way process chain", "equal disconnected cards"],
    },
    {
        "circle_role": "core",
        "page_type": "capability_core_circle",
        "keywords": ("四象限能力图", "中心圆", "四周", "能力建设", "体系咨询", "平台建设", "供应链导入", "运营支持", "统一能力核心", "一套能力"),
        "pattern_id": "capability_core_circle",
        "archetype": "capability_core_circle",
        "composition": "capability_core_circle",
        "intent": "Use one filled center circle as the capability core, with four surrounding support domains and soft support connectors.",
        "anti_patterns": ["chronology", "workflow steps", "operational closure", "decorative center circle"],
    },
]

NO_CIRCLE_TERMS = ("不要优先做圆", "不要做圆", "不要使用圆", "不要圆形", "不是圆形", "非圆形")
REJECTION_GROUPS: tuple[tuple[str, ...], ...] = (
    ("对比", "比较", "矩阵"),
    ("左侧", "右侧", "外部压力", "内部能力升级", "业务响应", "一方向转化"),
    ("流程链", "一方向", "阶段", "路线图"),
    ("泳道", "职责", "责任矩阵", "RACI"),
)

EXPLICIT_LAYOUTS: tuple[tuple[str, str], ...] = (
    ("四象限矩阵", "four-quadrant matrix"),
    ("四象限", "four-quadrant matrix"),
    ("对比矩阵", "comparison matrix with emphasized recommendation column"),
    ("矩阵", "matrix board"),
    ("泳道图", "swimlane responsibility map"),
    ("泳道", "swimlane responsibility map"),
    ("闭环图", "loop diagram"),
)


EXPLICIT_INTENT_RULES: tuple[dict[str, Any], ...] = (
    {
        "page_type": "cover",
        "terms": ("封面", "标题页"),
        "pattern_id": "explicit_cover_statement",
        "archetype": "report cover with dominant statement and restrained support line",
        "composition": "Create a formal report cover: one dominant statement, one restrained subtitle, and a strong but clean background structure. Do not use equal cards.",
        "must_answer_question": "这页是否一眼就是正式汇报封面，而不是内容流程页？",
        "proof_objects": ["主标题判断", "副标题说明", "背景视觉锚点"],
        "avoid_repetition_with": ["business_process_flow", "default_consulting_board", "equal_card_grid"],
    },
    {
        "page_type": "timeline_execution",
        "terms": ("时间线", "路线时间线"),
        "pattern_id": "explicit_timeline",
        "archetype": "horizontal timeline with staged milestones",
        "composition": "Use a timeline as the main structure. Show stages, order, and milestone meaning clearly. Avoid turning it into disconnected equal cards.",
        "must_answer_question": "这页是否清楚表达阶段顺序和推进节奏？",
        "proof_objects": ["阶段节点", "时间/顺序关系", "阶段结论"],
        "avoid_repetition_with": ["business_process_flow", "equal_card_grid"],
    },
    {
        "page_type": "number_focus",
        "terms": ("数字重点页", "大数字", "突出数字", "突出三个数字", "关键数字"),
        "pattern_id": "explicit_number_focus",
        "archetype": "dominant big-number evidence page",
        "composition": "Use large numbers as the main visual evidence. Give one clear hierarchy: main metric first, secondary metrics second, takeaway last. Avoid ordinary three-column card layouts.",
        "must_answer_question": "这页是否先让人记住关键数字，而不是看到普通三列卡片？",
        "proof_objects": ["主数字", "辅助数字", "结论解释"],
        "avoid_repetition_with": ["equal_card_grid", "default_consulting_board"],
    },
)

FORBIDDEN_THREE_COLUMN_TERMS = (
    "不要三列卡片",
    "不要普通三列卡片",
    "不要三列",
    "不要三栏卡片",
    "不要卡片",
)


def _norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _find_explicit_layout(text: str) -> tuple[str, str]:
    for label, archetype in EXPLICIT_LAYOUTS:
        if label in text:
            return label, archetype
    return "", ""


def _find_explicit_intent(text: str) -> dict[str, Any] | None:
    for rule in EXPLICIT_INTENT_RULES:
        hits = [term for term in rule["terms"] if term in text]
        if hits:
            item = dict(rule)
            item["hits"] = hits
            return item
    return None


def _detect_forbidden_layout_terms(text: str) -> list[str]:
    if any(term in text for term in FORBIDDEN_THREE_COLUMN_TERMS):
        return ["three-column cards"]
    return []


def _score_rule(rule: dict[str, Any], text: str) -> tuple[int, list[str]]:
    hits = [str(term) for term in rule["keywords"] if str(term) in text]
    return len(hits), hits


ACTION_TERMS = (
    "登录",
    "访问",
    "上传",
    "填报",
    "提交",
    "下发",
    "回传",
    "汇总",
    "审核",
    "整改",
    "退回",
    "复核",
    "关闭",
    "触发",
    "处理",
    "输出",
    "授权",
    "发布",
)
SEQUENCE_TERMS = (
    "先",
    "再",
    "随后",
    "然后",
    "之后",
    "通过后",
    "不通过",
    "触发后",
    "下发",
    "回传",
    "退回",
    "→",
    "->",
)
CAPABILITY_MODEL_TERMS = (
    "能力核心",
    "核心能力",
    "能力图",
    "不是系统",
    "一套能力",
    "合规追溯能力",
    "能力体系",
)
ARCHITECTURE_EVIDENCE_TERMS = ("架构", "分层", "数据底座", "接口", "系统边界", "层级", "节点")


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _hierarchy_endpoints(text: str) -> list[str]:
    endpoints = {
        item.upper()
        for item in re.findall(r"(?<![A-Za-z0-9])T(?:\d+|N)(?![A-Za-z0-9])", text, flags=re.I)
    }
    for term in ("源头", "上游", "下游"):
        if term in text:
            endpoints.add(term)
    return sorted(endpoints)


def _has_actor_action_endpoint(value: str) -> bool:
    return bool(
        re.search(
            r"(?:项目组|供应商|销售|供应链|质量|IT|财务|关务|业务|部门|T(?:\d+|N))"
            r"[^。；;，,\n]{0,12}"
            r"(?:登录|访问|上传|填报|提交|下发|回传|汇总|审核|整改|退回|复核|关闭|触发|处理|输出|授权|发布)",
            value,
            flags=re.I,
        )
    )


def _has_from_to_action_endpoints(text: str) -> bool:
    for start, end in re.findall(r"从([^。；;，,\n]{1,48})到([^。；;，,\n]{1,48})", text):
        if _has_actor_action_endpoint(start) and _has_actor_action_endpoint(end):
            return True
    return False


def _supplier_contract(text: str) -> tuple[str, list[str], str]:
    endpoints = _hierarchy_endpoints(text)
    action_labels: list[str] = []
    for action in ("下发", "汇总", "回传", "上传", "提交", "审核", "退回", "整改", "流转", "传递"):
        if action not in text:
            continue
        label = "任务下发" if action == "下发" and "任务" in text else action
        if label not in action_labels:
            action_labels.append(label)
    endpoint_text = "、".join(endpoints)
    action_text = "、".join(action_labels)
    composition = f"按原文明示的层级端点（{endpoint_text}）组织结构，只呈现原文明示的跨层动作：{action_text}。"
    proof_objects = [f"层级端点：{endpoint_text}", f"跨层动作：{action_text}"]
    must_answer = f"{endpoint_text} 之间明示的 {action_text} 关系如何发生？"
    return composition, proof_objects, must_answer


def _supports_supplier_penetration(text: str) -> tuple[bool, list[str]]:
    endpoints = _hierarchy_endpoints(text)
    actions = _matched_terms(text, ACTION_TERMS)
    cross_layer_actions = [
        term
        for term in ("下发", "回传", "汇总", "上传", "提交", "审核", "退回", "流转", "传递")
        if term in text
    ]
    supported = len(endpoints) >= 2 and bool(cross_layer_actions)
    return supported, [*endpoints, *cross_layer_actions, *actions]


def _supports_process(text: str) -> tuple[bool, list[str]]:
    actions = _matched_terms(text, ACTION_TERMS)
    relations = _matched_terms(text, SEQUENCE_TERMS)
    if _has_from_to_action_endpoints(text):
        relations.append("从…到动作端点")
    return len(set(actions)) >= 2 and bool(relations), [*actions, *relations]


def _supports_responsibility(text: str) -> tuple[bool, list[str]]:
    bindings = re.findall(r"谁(?:发起|提供|提交|审核|授权|推动|负责|关闭)", text)
    explicit_bindings = re.findall(
        r"(?:项目组|供应商|销售|供应链|质量|IT|财务|关务|业务|部门)"
        r"[^。；;，,\n]{0,12}(?:发起|提供|提交|审核|授权|推动|负责|关闭)",
        text,
        flags=re.I,
    )
    evidence = [*bindings, *explicit_bindings]
    return bool(evidence), evidence


def _time_anchors(text: str) -> list[str]:
    dates = re.findall(r"\d{1,2}月\d{1,2}日", text)
    stages = re.findall(r"(?:第[一二三四五六七八九十\d]+阶段|阶段[一二三四五六七八九十\d]+)", text)
    return list(dict.fromkeys([*dates, *stages]))


def _supports_roadmap(text: str) -> tuple[bool, list[str]]:
    anchors = _time_anchors(text)
    relations = _matched_terms(text, SEQUENCE_TERMS)
    explicit_request = "路线图" in text and (
        "三阶段" in text
        or "按阶段" in text
        or bool(re.search(r"[二三四五六七八九十\d]+个?阶段", text))
    )
    evidence = [*anchors, *relations]
    if explicit_request:
        evidence.append("explicit_multi_stage_roadmap")
    return explicit_request or (len(anchors) >= 2 and bool(relations)), evidence


def _relationship_evidence(
    page_type: str,
    text: str,
    keyword_hits: list[str],
) -> tuple[bool, list[str]]:
    if page_type == "capability_core_map":
        evidence = _matched_terms(text, CAPABILITY_MODEL_TERMS)
        return bool(evidence), evidence
    if page_type == "supplier_penetration":
        return _supports_supplier_penetration(text)
    if page_type == "organization_responsibility":
        return _supports_responsibility(text)
    if page_type == "business_process":
        return _supports_process(text)
    if page_type == "roadmap_execution":
        return _supports_roadmap(text)
    if page_type == "architecture_layered":
        evidence = _matched_terms(text, ARCHITECTURE_EVIDENCE_TERMS)
        return bool(evidence), evidence
    if page_type == "risk_governance":
        actions = _matched_terms(text, ("应对", "控制", "处置", "升级"))
        owners = _matched_terms(text, ("责任", "负责人", "owner", "Owner"))
        return bool(actions and owners), [*actions, *owners]
    return True, keyword_hits


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _circle_rejection_hits(text: str) -> list[str]:
    if _has_any(text, NO_CIRCLE_TERMS):
        return ["explicit_no_circle"]
    hits: list[str] = []
    for group in REJECTION_GROUPS:
        group_hits = [term for term in group if term in text]
        if len(group_hits) >= 2:
            hits.extend(group_hits)
    return hits


def _circle_decision(text: str) -> dict[str, Any]:
    rejection_hits = _circle_rejection_hits(text)
    if rejection_hits:
        return {"circle_role": "none", "rule": None, "hits": [], "rejection_hits": rejection_hits}
    scored: list[tuple[int, int, dict[str, Any], list[str]]] = []
    for index, rule in enumerate(CIRCLE_RULES):
        score, hits = _score_rule(rule, text)
        scored.append((score, -index, rule, hits))
    scored.sort(reverse=True)
    score, _index, rule, hits = scored[0]
    if score < 2:
        return {"circle_role": "none", "rule": None, "hits": [], "rejection_hits": []}
    return {"circle_role": str(rule["circle_role"]), "rule": rule, "hits": hits, "rejection_hits": []}


def _best_rule(text: str) -> tuple[dict[str, Any], list[str], float]:
    scored: list[tuple[int, int, dict[str, Any], list[str]]] = []
    for index, rule in enumerate(PAGE_RULES):
        score, keyword_hits = _score_rule(rule, text)
        supported, evidence = _relationship_evidence(str(rule["page_type"]), text, keyword_hits)
        if not supported:
            score = 0
            evidence = []
        scored.append((score, -index, rule, evidence))
    scored.sort(reverse=True)
    score, _index, rule, hits = scored[0]
    if score == 0:
        return DEFAULT_RULE, [], 0.2
    return rule, hits, min(0.95, 0.45 + score * 0.12)


def _user_constraints(text: str, explicit_layout: str) -> dict[str, Any]:
    return {
        "explicit_layout": explicit_layout,
        "must_preserve_screen_copy": "必须使用" in text or "上屏内容" in text or "页面文案" in text,
        "free_design_requested": "自由设计" in text or "不要套模板" in text,
        "forbidden_layout_terms": [
            label
            for label, _archetype in EXPLICIT_LAYOUTS
            if label in text and (f"不要做成{label}" in text or f"不要用{label}" in text)
        ],
    }


def direct_page(*, title: str, prompt: str, mode: str) -> dict[str, Any]:
    text = _norm(f"{title}\n{prompt}")
    rule, hits, confidence = _best_rule(text)
    explicit_layout, explicit_archetype = _find_explicit_layout(_norm(prompt))
    explicit_intent = _find_explicit_intent(text)
    constraints = _user_constraints(text, explicit_layout)
    forbidden_layout_terms = _detect_forbidden_layout_terms(text)
    if forbidden_layout_terms:
        constraints["forbidden_layout_terms"] = sorted(
            set(list(constraints.get("forbidden_layout_terms") or []) + forbidden_layout_terms)
        )
    circle = _circle_decision(text)

    page_type = str(rule["page_type"])
    selected_archetype = str(rule["archetype"])
    pattern_id = str(rule["pattern_id"])
    composition_intent = str(rule["composition"])
    composition_grammar = composition_intent
    must_answer_question = str(rule.get("must_answer_question") or DEFAULT_RULE["must_answer_question"])
    proof_objects = list(rule.get("proof_objects") or DEFAULT_RULE["proof_objects"])
    avoid_repetition_with = list(rule.get("avoid_repetition_with") or [])
    conflicts: list[str] = []

    if explicit_intent:
        page_type = str(explicit_intent["page_type"])
        selected_archetype = str(explicit_intent["archetype"])
        pattern_id = str(explicit_intent["pattern_id"])
        composition_intent = str(explicit_intent["composition"])
        composition_grammar = composition_intent
        hits = list(explicit_intent["hits"])
        confidence = 0.92
        must_answer_question = str(explicit_intent["must_answer_question"])
        proof_objects = list(explicit_intent["proof_objects"])
        avoid_repetition_with = list(explicit_intent["avoid_repetition_with"])
        if str(rule["page_type"]) != page_type:
            conflicts.append(f"user_explicit_intent_overrode_{rule['page_type']}")
        if explicit_archetype and explicit_archetype != selected_archetype:
            conflicts.append(f"user_explicit_intent_overrode_explicit_layout_{explicit_layout}")
    elif explicit_archetype and explicit_archetype != selected_archetype:
        selected_archetype = explicit_archetype
        conflicts.append(f"user_explicit_layout_overrode_{page_type}")
        if circle["rule"]:
            conflicts.append(f"user_explicit_layout_blocked_circle_{explicit_layout}")
    elif circle["rule"]:
        circle_rule = circle["rule"]
        page_type = str(circle_rule["page_type"])
        selected_archetype = str(circle_rule["archetype"])
        pattern_id = str(circle_rule["pattern_id"])
        composition_intent = str(circle_rule["intent"])
        composition_grammar = str(circle_rule["composition"])
        hits = list(circle["hits"])
        confidence = min(0.95, 0.58 + len(hits) * 0.08)
        must_answer_question = "该圆形语法是否承载了明确业务判断，而非装饰？"
        proof_objects = ["中心能力", "外圈关系", "闭环/组件约束"]
        avoid_repetition_with = ["default_consulting_board", "comparison_decision_matrix"]

    if page_type == "supplier_penetration":
        composition_intent, proof_objects, must_answer_question = _supplier_contract(text)
        composition_grammar = composition_intent

    anti_patterns = ["generic business slide", "equal card grid by default", "prompt text on canvas"]
    if circle["rule"]:
        anti_patterns += list(circle["rule"]["anti_patterns"])
    if "three-column cards" in constraints.get("forbidden_layout_terms", []):
        anti_patterns += ["three-column cards", "ordinary equal card layout"]
    return {
        "circle_role": circle["circle_role"],
        "page_type_decision": {
            "page_type": page_type,
            "confidence": confidence,
            "evidence_terms": hits,
            "circle_role": circle["circle_role"],
            "circle_rejection_terms": circle["rejection_hits"],
            "mode": mode,
            "explicit_layout": explicit_layout,
            "user_constraints": constraints,
            "conflicts": conflicts,
        },
        "selected_archetype": selected_archetype,
        "visual_archetype": selected_archetype,
        "composition_intent": composition_intent,
        "hierarchy_strategy": "Primary: action-title judgment; Secondary: visual structure; Tertiary: concise evidence labels.",
        "rhythm_role": page_type,
        "variation_rule": "Avoid repeating the same archetype on adjacent pages when mode is prompt_deck or document_deck.",
        "argument_pattern": pattern_id,
        "proof_objects": proof_objects,
        "page_prompt_pattern": {
            "pattern_id": pattern_id,
            "conclusion_formula": "Use a judgment sentence that states the business implication.",
            "block_structure": ["action title", selected_archetype, "takeaway"],
            "composition_cues": [composition_intent],
            "anti_patterns": anti_patterns,
        },
        "visual_contract_patch": {
            "focal_point": selected_archetype,
            "primary_read_path": ["action title", "main visual structure", "takeaway"],
            "composition_grammar": composition_grammar,
            "template_inheritance": "free design; director provides page grammar only",
            "anti_patterns": anti_patterns,
            "critic_checks": [
                "page type is visible in the main structure",
                "user hard constraints are preserved",
                "no title clipping",
                "no visual rhythm repeat beyond two adjacent pages",
            ],
            "recommended_diagram_grammar": selected_archetype,
            "must_answer_question": must_answer_question,
            "avoid_repetition_with": avoid_repetition_with,
        },
    }
