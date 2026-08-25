#!/usr/bin/env python3
"""Template catalog retrieval for State 2.5 reference selection.

This module only selects reference anchors for Executor-authored SVG. It does
not render slides and must not call render_svg.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ALLOWED_TIERS = {"Gold", "Silver", "Reject"}
ALLOWED_LIFECYCLE = {"active", "candidate", "deprecated", "blocked"}
DEFAULT_MAX_TEMPLATES = 3
LOW_CONFIDENCE_THRESHOLD = 50

FREE_DESIGN_MARKERS = (
    "free",
    "free-design",
    "free design",
    "no template",
    "without template",
    "不要模板",
    "不用模板",
    "不使用模板",
    "自由创作",
    "自由设计",
    "更有创意",
)

TEMPLATE_GUIDED_MARKERS = (
    "template-guided",
    "template guided",
    "strict template",
    "strictly follow",
    "严格",
    "套",
    "套用",
    "沿用",
    "强模板",
)

NEUTRAL_TEMPLATE_MARKERS = (
    "no strict template",
    "no preference",
    "无模板偏好",
    "没有模板偏好",
    "不严格套模板",
)

STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "style",
    "report",
    "deck",
    "presentation",
    "template",
    "preference",
    "prefer",
    "like",
    "no",
    "strict",
}

ZH_CONTEXT_EXPANSIONS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("政府", "政务", "国企", "监管", "公共部门"),
        ("government", "public-sector", "formal", "state-owned enterprises"),
    ),
    (("战略", "咨询", "高管", "董事会", "经营分析"), ("strategy", "consulting", "executive", "board")),
    (("金融", "银行", "投资", "财务"), ("finance", "investment", "bank", "premium")),
    (("科技", "技术", "架构", "人工智能", "数字化"), ("technology", "ai", "architecture", "digital transformation")),
    (("医疗", "医院", "临床"), ("medical", "clinical", "health")),
    (("学术", "答辩", "论文", "科研"), ("academic", "research", "defense")),
    (("工程", "能源", "基建", "电建"), ("engineering", "energy", "infrastructure")),
    (("汽车", "认证", "测评", "检测"), ("automotive", "certification", "evaluation")),
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"Invalid JSON file: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def _parse_design_spec(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _load_clarification(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "clarification_brief.json"
    if not path.exists():
        return {}
    return _read_json(path)


def _normalize_tier(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return raw[:1].upper() + raw[1:].lower()


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_reference_field(template: dict[str, Any], key: str, fallback: list[str]) -> list[str]:
    values = _as_string_list(template.get(key))
    if values:
        return values
    return fallback


def _as_ratio(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        raw = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            raw = float(value)
        except ValueError:
            return default
    else:
        return default
    return max(0.0, min(1.0, raw))


def _as_quality_score(value: Any, default: float = 0.7) -> float:
    if isinstance(value, (int, float)):
        raw = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            raw = float(value)
        except ValueError:
            return default
    else:
        return default
    # Support legacy 0-100 scoring while storing normalized 0-1.
    if raw > 1.0:
        raw = raw / 100.0
    return max(0.0, min(1.0, raw))


def _normalize_lifecycle(value: Any) -> str:
    state = str(value or "").strip().lower()
    if state in ALLOWED_LIFECYCLE:
        return state
    return "active"


def _normalize_governance(template: dict[str, Any]) -> dict[str, Any]:
    raw = template.get("governance")
    governance = dict(raw) if isinstance(raw, dict) else {}
    density_profile = (
        str(governance.get("density_profile") or template.get("density") or "medium")
        .strip()
        .lower()
    )
    canvas_profiles = (
        _as_string_list(governance.get("canvas_profiles") or template.get("canvas_profiles"))
        or ["ppt169"]
    )
    return {
        "scenario_tags": _as_string_list(governance.get("scenario_tags") or template.get("scenario_tags")),
        "density_profile": density_profile,
        "canvas_profiles": canvas_profiles,
        "quality_score": _as_quality_score(governance.get("quality_score") or template.get("quality_score"), 0.7),
        "adoption_rate_30d": _as_ratio(governance.get("adoption_rate_30d") or template.get("adoption_rate_30d"), 0.0),
        "failure_rate_30d": _as_ratio(governance.get("failure_rate_30d") or template.get("failure_rate_30d"), 0.0),
        "lifecycle": _normalize_lifecycle(governance.get("lifecycle") or template.get("lifecycle")),
        "retire_signal": str(governance.get("retire_signal") or "").strip(),
        "last_reviewed": str(governance.get("last_reviewed") or "").strip(),
    }


def _derive_composition_patterns(template: dict[str, Any]) -> list[str]:
    style_tags = {item.lower() for item in _as_string_list(template.get("style_tags"))}
    density = str(template.get("density", "")).strip().lower()
    patterns: list[str] = []
    if {"consulting", "strategy", "executive"}.intersection(style_tags):
        patterns.append("conclusion bar + asymmetric evidence columns")
    if {"finance", "investment", "bank"}.intersection(style_tags):
        patterns.append("metric stage + risk/reward pairing")
    if {"government", "policy", "formal"}.intersection(style_tags):
        patterns.append("stable bilateral grid + policy rail")
    if {"technology", "ai", "architecture", "engineering"}.intersection(style_tags):
        patterns.append("layered architecture map + directed flow connectors")
    if "high" in density:
        patterns.append("modular zoning with bounded annotation lanes")
    if not patterns:
        patterns.append("hero headline + structured evidence blocks")
    return patterns[:3]


def _derive_avoid_copying(template: dict[str, Any]) -> list[str]:
    template_key = str(template.get("template_key") or "template").strip()
    return [
        f"Do not replicate {template_key} page geometry one-to-one; rewrite structure to fit narrative.",
        "Reuse visual grammar only (hierarchy, rhythm, emphasis), not pixel-level decoration.",
        "Replace color accents/icon motifs when they signal another brand identity.",
    ]


def _hydrate_template_reference_fields(template: dict[str, Any]) -> dict[str, Any]:
    hydrated = dict(template)
    use_cases = _as_string_list(hydrated.get("use_cases"))
    visual_strengths = _normalize_reference_field(
        hydrated,
        "visual_strengths",
        ["Clear page hierarchy and reusable structure."],
    )
    avoid_when = _normalize_reference_field(
        hydrated,
        "avoid_when",
        ["When strict brand identity or domain mismatch makes adaptation risky."],
    )
    hydrated["visual_strengths"] = visual_strengths
    hydrated["composition_patterns"] = _normalize_reference_field(
        hydrated,
        "composition_patterns",
        _derive_composition_patterns(hydrated),
    )
    hydrated["avoid_copying"] = _normalize_reference_field(
        hydrated,
        "avoid_copying",
        _derive_avoid_copying(hydrated),
    )
    hydrated["best_for"] = _normalize_reference_field(
        hydrated,
        "best_for",
        use_cases[:3] if use_cases else ["General business storytelling with structured evidence."],
    )
    hydrated["avoid_when"] = avoid_when
    hydrated["governance"] = _normalize_governance(hydrated)
    return hydrated


def _load_catalog(catalog_path: Path) -> list[dict[str, Any]]:
    payload = _read_json(catalog_path)
    templates = payload.get("templates")
    if not isinstance(templates, list):
        raise ValueError(f"template_catalog.json missing templates array: {catalog_path}")

    result: list[dict[str, Any]] = []
    for raw in templates:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item["tier"] = _normalize_tier(item.get("tier"))
        if item["tier"] not in ALLOWED_TIERS:
            raise ValueError(f"Illegal tier for template {item.get('template_key')}: {item.get('tier')}")
        if not str(item.get("template_key", "")).strip():
            raise ValueError("Template entry missing template_key")
        if item["tier"] in {"Gold", "Silver"}:
            item = _hydrate_template_reference_fields(item)
        result.append(item)
    return result


def _context_text(project_dir: Path) -> tuple[dict[str, Any], dict[str, str], str]:
    clarification = _load_clarification(project_dir)
    design_values = _parse_design_spec(project_dir / "design_spec.md")
    fields = [
        clarification.get("audience", ""),
        clarification.get("decision_goal", ""),
        clarification.get("style_goal", ""),
        clarification.get("template_preference", ""),
        " ".join(_as_string_list(clarification.get("assumptions"))),
        design_values.get("audience", ""),
        design_values.get("purpose", ""),
        design_values.get("style", ""),
        design_values.get("style_objective", ""),
        design_values.get("template_key", ""),
        design_values.get("density_profile", ""),
    ]
    context = " ".join(str(item) for item in fields if item is not None)
    return clarification, design_values, _expand_chinese_business_context(context)


def _expand_chinese_business_context(context: str) -> str:
    additions: list[str] = []
    for needles, expansions in ZH_CONTEXT_EXPANSIONS:
        if any(needle in context for needle in needles):
            additions.extend(expansions)
    if not additions:
        return context
    return f"{context} {' '.join(additions)}"


def _determine_mode(template_preference: str, requested_mode: str | None) -> tuple[str, str | None]:
    if requested_mode:
        mode = requested_mode.strip()
        if mode not in {"hybrid", "template-guided", "free-design"}:
            raise ValueError(f"Unsupported template retrieval mode: {requested_mode}")
        return mode, None

    pref = template_preference.lower()
    if any(marker in pref for marker in FREE_DESIGN_MARKERS):
        return "free-design", "user_requested_free_design"
    if any(marker in pref for marker in NEUTRAL_TEMPLATE_MARKERS):
        return "hybrid", None
    if any(marker in pref for marker in TEMPLATE_GUIDED_MARKERS):
        return "template-guided", None
    return "hybrid", None


def _tokens(value: str) -> set[str]:
    lowered = value.lower()
    normalized = "".join(ch if ch.isalnum() or "\u4e00" <= ch <= "\u9fff" else " " for ch in lowered)
    return {token for token in normalized.split() if len(token) >= 3 and token not in STOPWORDS}


def _field_matches(values: list[str], context: str) -> list[str]:
    context_lower = context.lower()
    context_tokens = _tokens(context)
    matched: list[str] = []
    for value in values:
        value_lower = value.lower()
        value_tokens = _tokens(value)
        if value_lower and value_lower in context_lower:
            matched.append(value)
            continue
        if value_tokens and context_tokens.intersection(value_tokens):
            matched.append(value)
    return matched


def _explicit_template_key(
    templates: list[dict[str, Any]],
    preference: str,
    design_values: dict[str, str],
) -> str | None:
    design_key = design_values.get("template_key", "").strip()
    if design_key:
        for item in templates:
            if item.get("template_key") == design_key:
                return design_key
    preference_lower = preference.lower()
    for item in templates:
        key = str(item.get("template_key", "")).strip()
        if key and key.lower() in preference_lower:
            return key
    return None


def _score_template(
    template: dict[str, Any],
    *,
    context: str,
    explicit_key: str | None,
) -> tuple[int, dict[str, Any], list[str], bool]:
    tier = str(template.get("tier"))
    if tier == "Reject":
        return 0, {}, ["tier is Reject"], True

    score = 25 if tier == "Gold" else 12
    reasons: list[str] = [f"tier={tier}"]
    matched_fields: dict[str, Any] = {}

    key = str(template.get("template_key", ""))
    if explicit_key and key == explicit_key:
        score += 60
        reasons.append("matches explicit template preference")

    governance = template.get("governance")
    governance_meta = governance if isinstance(governance, dict) else _normalize_governance(template)
    lifecycle = _normalize_lifecycle(governance_meta.get("lifecycle"))
    quality_score = _as_quality_score(governance_meta.get("quality_score"), 0.7)
    failure_rate = _as_ratio(governance_meta.get("failure_rate_30d"), 0.0)
    adoption_rate = _as_ratio(governance_meta.get("adoption_rate_30d"), 0.0)
    if lifecycle in {"blocked", "deprecated"} and key != explicit_key:
        reasons.append(f"lifecycle={lifecycle}")
        return 0, {}, reasons, True
    if quality_score < 0.55:
        score -= 10
        reasons.append("quality_score below 0.55")
    elif quality_score >= 0.8:
        score += 4
        reasons.append("quality_score above 0.80")
    if failure_rate >= 0.3:
        score -= 20
        reasons.append("failure_rate_30d high")
    elif failure_rate >= 0.18:
        score -= 8
        reasons.append("failure_rate_30d elevated")
    if adoption_rate >= 0.12:
        score += 4
        reasons.append("adoption_rate_30d strong")

    use_cases = _as_string_list(template.get("use_cases"))
    use_case_matches = _field_matches(use_cases, context)
    if use_case_matches:
        score += min(25, 10 + len(use_case_matches) * 5)
        matched_fields["use_cases"] = use_case_matches
        reasons.append("matches use_cases")

    audiences = _as_string_list(template.get("audiences"))
    audience_matches = _field_matches(audiences, context)
    if audience_matches:
        score += min(20, 8 + len(audience_matches) * 4)
        matched_fields["audiences"] = audience_matches
        reasons.append("matches audiences")

    style_tags = _as_string_list(template.get("style_tags"))
    style_matches = _field_matches(style_tags, context)
    if style_matches:
        score += min(20, 6 + len(style_matches) * 3)
        matched_fields["style_tags"] = style_matches
        reasons.append("matches style_tags")

    density = str(template.get("density", "")).strip()
    if density and density.lower() in context.lower():
        score += 5
        matched_fields["density"] = density
        reasons.append("matches density")

    avoid_matches = _field_matches(_as_string_list(template.get("avoid_when")), context)
    blocked = False
    if avoid_matches and key != explicit_key:
        score -= 30
        matched_fields["avoid_when"] = avoid_matches
        reasons.append("avoid_when conflict")
        if score < LOW_CONFIDENCE_THRESHOLD:
            blocked = True

    return max(0, min(100, score)), matched_fields, reasons, blocked


def _selected_entry(
    template: dict[str, Any],
    *,
    score: int,
    matched_fields: dict[str, Any],
    reasons: list[str],
) -> dict[str, Any]:
    source_path = str(template.get("source_path", "")).strip()
    reference_pages = _as_string_list(template.get("reference_pages"))
    visual_strengths = _as_string_list(template.get("visual_strengths"))
    composition_patterns = _as_string_list(template.get("composition_patterns"))
    avoid_copying = _as_string_list(template.get("avoid_copying"))
    best_for = _as_string_list(template.get("best_for"))
    avoid_when = _as_string_list(template.get("avoid_when"))
    governance = template.get("governance")
    governance_meta = governance if isinstance(governance, dict) else _normalize_governance(template)
    return {
        "template_key": template["template_key"],
        "tier": template["tier"],
        "score": score,
        "source_path": source_path,
        "matched_fields": matched_fields,
        "reference_pages": reference_pages,
        "reference_files": [f"{source_path}/{page}" for page in reference_pages if source_path],
        "use_as": ["style anchor", "composition rhythm", "visual hierarchy"],
        "visual_strengths": visual_strengths,
        "composition_patterns": composition_patterns,
        "avoid_copying": avoid_copying,
        "best_for": best_for,
        "avoid_when": avoid_when,
        "governance": governance_meta,
        "template_quality_score": _as_quality_score(governance_meta.get("quality_score"), 0.7),
        "template_failure_rate_30d": _as_ratio(governance_meta.get("failure_rate_30d"), 0.0),
        "template_adoption_rate_30d": _as_ratio(governance_meta.get("adoption_rate_30d"), 0.0),
        "template_lifecycle": _normalize_lifecycle(governance_meta.get("lifecycle")),
        "notes": str(template.get("notes", "")).strip()
        or "Reference only. Executor must create new per-slide SVG.",
        "selection_reasons": reasons,
    }


def _free_design_pack(reason: str) -> dict[str, Any]:
    requires_style_drafts = reason == "low_confidence"
    return {
        "version": "1.0",
        "mode": "free-design",
        "selection_reason": "Template retrieval skipped or confidence was too low; use art_direction only.",
        "max_templates": 0,
        "references": [],
        "selected_templates": [],
        "primary_template": None,
        "secondary_templates": [],
        "reference_files": [],
        "free_design_override_reason": (
            "No suitable template reference was selected by the formal template selector "
            f"({reason})."
        ),
        "requires_style_drafts": requires_style_drafts,
        "fallback": {
            "enabled": True,
            "fallback_mode": "free-design",
            "reason": reason,
        },
        "hard_rules": [
            "Do not pass templates to render_svg.py.",
            "Do not copy template pages literally.",
            "Executor must hand-author or iterate svg_output/slide_XX.svg.",
        ],
    }


def build_reference_pack_from_catalog(
    project_dir: Path,
    catalog_path: Path,
    *,
    requested_mode: str | None = None,
    max_templates: int = DEFAULT_MAX_TEMPLATES,
) -> dict[str, Any]:
    """Return a reference_pack payload selected from template_catalog.json."""
    project_dir = project_dir.resolve()
    catalog_path = catalog_path.resolve()
    if max_templates < 1:
        raise ValueError("max_templates must be >= 1")
    max_templates = min(DEFAULT_MAX_TEMPLATES, max_templates)

    templates = _load_catalog(catalog_path)
    clarification, design_values, context = _context_text(project_dir)
    bound_template_id = str(clarification.get("template_id") or "").strip()
    if clarification.get("template_bound") is True and bound_template_id:
        template_preference = bound_template_id
    else:
        template_preference = str(
            clarification.get("template_preference", "") or design_values.get("template_key", "")
        )
    mode, direct_fallback_reason = _determine_mode(template_preference, requested_mode)
    if mode == "free-design":
        return _free_design_pack(direct_fallback_reason or "user_requested_free_design")

    explicit_key = _explicit_template_key(templates, template_preference, design_values)
    scored: list[tuple[int, dict[str, Any], dict[str, Any], list[str]]] = []
    rejected_candidates: list[dict[str, Any]] = []
    for template in templates:
        score, matched_fields, reasons, blocked = _score_template(
            template,
            context=context,
            explicit_key=explicit_key,
        )
        if str(template.get("tier")) == "Reject" or blocked:
            rejected_candidates.append(
                {
                    "template_key": template.get("template_key"),
                    "reason": "; ".join(reasons),
                }
            )
            continue
        scored.append((score, template, matched_fields, reasons))

    scored.sort(
        key=lambda item: (
            item[0],
            1 if item[1].get("tier") == "Gold" else 0,
            str(item[1].get("template_key")),
        ),
        reverse=True,
    )
    selected = [
        _selected_entry(template, score=score, matched_fields=matched_fields, reasons=reasons)
        for score, template, matched_fields, reasons in scored[:max_templates]
        if score >= LOW_CONFIDENCE_THRESHOLD or (explicit_key and template.get("template_key") == explicit_key)
    ]

    if not selected:
        pack = _free_design_pack("low_confidence")
        pack["rejected_candidates"] = rejected_candidates
        return pack

    primary = selected[0]["template_key"]
    secondary = [item["template_key"] for item in selected[1:]]
    reference_files: list[str] = []
    quality_scores: list[float] = []
    failure_rates: list[float] = []
    for item in selected:
        reference_files.extend(item.get("reference_files", []))
        quality_scores.append(_as_quality_score(item.get("template_quality_score"), 0.7))
        failure_rates.append(_as_ratio(item.get("template_failure_rate_30d"), 0.0))

    count = max(1, len(selected))

    return {
        "version": "1.0",
        "mode": mode,
        "selection_reason": (
            "Selected by template_catalog.json using audience, decision goal, "
            "style goal, and template preference."
        ),
        "max_templates": max_templates,
        "references": selected,
        "selected_templates": selected,
        "primary_template": primary,
        "secondary_templates": secondary,
        "tone": "Professional and reference-guided",
        "themeMode": "Hybrid",
        "motifs": ["template-informed rhythm", "Executor-authored composition", "reference-only visual hierarchy"],
        "avoid": [
            "Avoid template pixel copying; adapt composition to narrative intent.",
            "Avoid using template pages as deterministic renderer input.",
        ],
        "reference_files": reference_files,
        "template_governance_summary": {
            "selected_count": len(selected),
            "avg_quality_score": round(sum(quality_scores) / count, 4),
            "avg_failure_rate_30d": round(sum(failure_rates) / count, 4),
        },
        "requires_style_drafts": False,
        "rejected_candidates": rejected_candidates,
        "fallback": {
            "enabled": True,
            "fallback_mode": "free-design",
            "reason": None,
        },
        "hard_rules": [
            "Do not pass templates to render_svg.py.",
            "Do not copy template pages literally.",
            "Executor must hand-author or iterate svg_output/slide_XX.svg.",
        ],
    }
