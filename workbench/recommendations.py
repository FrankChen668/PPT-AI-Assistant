from __future__ import annotations

from typing import Any


def user_facing_error_text(raw: object) -> str:
    message = str(raw or "").strip()
    if not message:
        return ""
    folded = message.lower()
    if "http 401" in folded or "api key is invalid" in folded or "invalid api key" in folded or "unauthorized" in folded:
        return "模型 API Key 无效，请在模型配置里更新密钥后重试。"
    if "http 429" in folded or "resource_exhausted" in folded or "quota" in folded or "rate-limit" in folded:
        return "模型额度或频率已达上限，请稍后重试或切换模型。"
    if "contrast" in folded and ("required>=" in folded or "text/background" in folded or "design_spec.md" in folded):
        return "页面颜色对比度偏低，可能影响阅读。请重新生成本页，或要求文字更深、背景更浅。"
    if "missing svg" in folded:
        return "还有页面没有生成画面，暂时不能生成 PPT 文件。"
    if "qa failed" in folded or "visual quality blocked" in folded:
        return "页面检查未通过，请先修复对应页面后再继续。"
    if "export failed" in folded or "finalize failed" in folded or "deck-finalize-failed" in folded:
        return "PPT 生成失败，请先执行导出排障任务后重试。"
    line = next((item.strip() for item in message.splitlines() if item.strip()), "")
    return line or "生成失败，请重试。"


def _preflight_phrase(message: object) -> str:
    text = str(message or "")
    if "'" in text:
        parts = text.split("'")
        if len(parts) >= 3 and parts[1].strip():
            return parts[1].strip()
    return ""


def summarize_preflight_blockers(findings: object) -> str:
    if not isinstance(findings, list) or not findings:
        return ""
    grouped: dict[int, list[str]] = {}
    unknown_phrases: list[str] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        phrase = _preflight_phrase(item.get("message")) or str(item.get("code") or "").strip()
        if not phrase:
            continue
        try:
            slide_id = int(item.get("slide_id") or 0)
        except (TypeError, ValueError):
            slide_id = 0
        if slide_id > 0:
            grouped.setdefault(slide_id, [])
            if phrase not in grouped[slide_id]:
                grouped[slide_id].append(phrase)
        elif phrase not in unknown_phrases:
            unknown_phrases.append(phrase)

    parts: list[str] = []
    for slide_id in sorted(grouped):
        parts.append(f"第 {slide_id} 页存在未允许的英文短语：{'、'.join(grouped[slide_id])}")
    if unknown_phrases:
        parts.append(f"页面中存在未允许的英文短语：{'、'.join(unknown_phrases)}")
    if not parts:
        return ""
    return "生成失败。" + "；".join(parts) + "。请重新生成这些页面，或把这些英文改成中文后再导出。"


def build_action(
    key: str,
    label: str,
    detail: str,
    *,
    slide_id: int | None = None,
    disabled: bool = False,
    severity: str = "primary",
    reason_code: str = "",
    user_message: str = "",
    technical_message: str = "",
) -> dict:
    payload: dict[str, Any] = {
        "key": key,
        "label": label,
        "detail": detail,
        "severity": severity,
    }
    if slide_id is not None:
        payload["slide_id"] = int(slide_id)
    if disabled:
        payload["disabled"] = True
    if reason_code:
        payload["reason_code"] = reason_code
    if user_message:
        payload["user_message"] = user_message
    if technical_message:
        payload["technical_message"] = technical_message
    return payload


def _format_slide_ids(slide_ids: object) -> str:
    ids: list[int] = []
    for item in slide_ids if isinstance(slide_ids, list) else []:
        try:
            slide_id = int(item)
        except (TypeError, ValueError):
            continue
        if slide_id > 0 and slide_id not in ids:
            ids.append(slide_id)
    if not ids:
        return "页面"
    return "第 " + "、".join(str(item) for item in ids) + " 页"


def _missing_slides_user_message(slide_ids: object) -> str:
    ids: list[int] = []
    for item in slide_ids if isinstance(slide_ids, list) else []:
        try:
            slide_id = int(item)
        except (TypeError, ValueError):
            continue
        if slide_id > 0 and slide_id not in ids:
            ids.append(slide_id)
    if not ids:
        return "还有页面未生成，暂时无法生成 PPT。"
    if len(ids) == 1:
        return f"第 {ids[0]} 页还未生成，暂时无法生成 PPT。"
    if len(ids) <= 5:
        return f"第 {'、'.join(str(item) for item in ids)} 页还未生成，暂时无法生成 PPT。"
    return f"还有 {len(ids)} 页未生成，暂时无法生成 PPT。请先补齐缺失页面。"


def preflight_blocked_action(readiness: dict) -> dict | None:
    if readiness.get("ready"):
        return None
    findings = readiness.get("preflight_blocking_findings")
    if not isinstance(findings, list) or not findings:
        return None
    first = findings[0] if isinstance(findings[0], dict) else {}
    try:
        slide_id = int(first.get("slide_id") or 0)
    except (TypeError, ValueError):
        slide_id = 0
    phrase = _preflight_phrase(first.get("message"))
    slide_label = f"第 {slide_id} 页" if slide_id > 0 else "当前页面"
    if phrase:
        detail = f"{slide_label}导出前检查未通过：页面中出现英文短语 {phrase}。请重新生成或调整该页后再生成 PPT。"
    else:
        detail = f"{slide_label}导出前检查未通过。请重新生成或调整该页后再生成 PPT。"
    return build_action(
        "repair_slide",
        f"处理{slide_label}",
        detail,
        slide_id=slide_id if slide_id > 0 else None,
        severity="danger",
        reason_code="preflight_blocked",
        user_message=detail,
        technical_message=str(first.get("message") or first.get("code") or "preflight_blocked"),
    )


def visual_delivery_ready(evidence: dict) -> bool | str:
    if evidence.get("export_is_current") is False:
        return False
    raw_user_quality = evidence.get("user_quality")
    user_quality: dict[str, Any] = raw_user_quality if isinstance(raw_user_quality, dict) else {}
    if user_quality.get("can_download") is True and user_quality.get("user_quality_status") == "approved":
        return True
    if evidence.get("last_finalize_fresh_qa") is not True:
        return False
    if evidence.get("delivery_blocked") is True:
        return False
    if evidence.get("manual_review_required") is True:
        return False
    if evidence.get("manual_review_required") is False and evidence.get("delivery_blocked") is False:
        return True
    return "unknown"


def deck_level_repair_items(evidence: dict) -> list[dict[str, Any]]:
    raw_items = evidence.get("deck_level_repair_items")
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                "issue_code": str(raw.get("issue_code") or "deck-level-repair").strip() or "deck-level-repair",
                "message": str(raw.get("message") or "").strip(),
                "recommended_action": str(raw.get("recommended_action") or "").strip(),
                "repair_scope": str(raw.get("repair_scope") or "deck_level").strip() or "deck_level",
            }
        )
    return items


def actionable_deck_level_repair_items(evidence: dict) -> list[dict[str, Any]]:
    actionable: list[dict[str, Any]] = []
    for item in deck_level_repair_items(evidence):
        issue_code = str(item.get("issue_code") or "").strip().lower()
        if issue_code == "visual-delivery-review-required":
            continue
        actionable.append(item)
    return actionable


def export_recommended_next_action(status: dict, evidence: dict) -> dict | None:
    export_state = status.get("export", {}) if isinstance(status.get("export"), dict) else {}
    export_status = str(export_state.get("status") or "")
    has_export = bool(export_state.get("pptx_path"))
    if evidence.get("export_is_current") is False:
        has_export = False

    raw_user_quality = evidence.get("user_quality")
    user_quality: dict[str, Any] = raw_user_quality if isinstance(raw_user_quality, dict) else {}
    user_can_download = bool(user_quality.get("can_download"))
    raw_delivery_contract = evidence.get("delivery_contract")
    delivery_contract: dict[str, Any] = raw_delivery_contract if isinstance(raw_delivery_contract, dict) else {}
    if delivery_contract.get("delivery_status") == "not_downloadable":
        has_export = False

    if export_status == "failed" and not has_export:
        technical_message = str(export_state.get("last_error") or "")
        context = export_state.get("last_error_context") if isinstance(export_state.get("last_error_context"), dict) else {}
        context_message = str(context.get("user_facing_error") or "").strip()
        detail = context_message or "PPT 生成失败，请先执行导出排障任务，再重新生成。"
        return build_action(
            "repair_export_failure",
            "处理导出问题",
            detail,
            severity="danger",
            reason_code="export_failed",
            user_message=context_message or user_facing_error_text(technical_message) or detail,
            technical_message=technical_message,
        )

    if delivery_contract.get("delivery_approved") is False:
        return None

    if has_export and export_status in {"exported", "review_required"}:
        context = export_state.get("last_error_context") if isinstance(export_state.get("last_error_context"), dict) else {}
        note = str(context.get("user_facing_error") or export_state.get("last_error") or "").strip()
        ready = visual_delivery_ready(evidence) is True and export_status == "exported"
        detail = "PPT 已生成，可下载。"
        reason_code = "export_ready_downloadable"
        if not ready:
            detail = note or "PPT 已生成，可下载；检查提示仅作为重新生成参考。"
            reason_code = "export_ready_with_notes"
        return build_action(
            "download_pptx",
            "下载",
            detail,
            severity="primary",
            reason_code=reason_code,
            user_message=detail,
            technical_message=str(export_state.get("last_error") or ""),
        )

    if has_export and user_can_download and visual_delivery_ready(evidence) is True:
        return build_action(
            "download_pptx",
            "下载",
            "PPT 已生成，可下载交付。",
            severity="primary",
            reason_code="export_ready_downloadable",
            user_message="PPT 已生成，可下载交付。",
        )

    if has_export and evidence.get("manual_review_required") is True:
        detail = "PPT 已生成，可下载；检查提示仅作为重新生成参考。"
        return build_action(
            "download_pptx",
            "下载",
            detail,
            severity="primary",
            reason_code="visual_review_required",
            user_message=detail,
            technical_message=str(export_state.get("last_error") or "visual_review_required"),
        )

    context = export_state.get("last_error_context") if isinstance(export_state.get("last_error_context"), dict) else {}
    if (
        export_status == "review_required"
        and has_export
        and str(export_state.get("last_error_code") or "") == "deck-finalize-warning-gate"
        and context.get("fallback_used") is True
    ):
        detail = "PPT 已生成，可下载；检查提示仅作为重新生成参考。"
        return build_action(
            "download_pptx",
            "下载",
            detail,
            severity="primary",
            reason_code="visual_review_required",
            user_message=detail,
            technical_message=str(context.get("strict_warning") or export_state.get("last_error") or ""),
        )

    if export_status == "review_required" or (has_export and evidence.get("delivery_blocked") is True):
        detail = "PPT 已生成，可下载；检查提示仅作为重新生成参考。"
        return build_action(
            "download_pptx",
            "下载",
            detail,
            severity="primary",
            reason_code="delivery_blocked",
            user_message=detail,
            technical_message=str(export_state.get("last_error") or "delivery_blocked"),
        )

    if has_export and export_status == "exported" and visual_delivery_ready(evidence) is True:
        return build_action(
            "download_pptx",
            "下载",
            "PPT 已生成，可下载交付。",
            severity="primary",
            reason_code="export_ready_downloadable",
            user_message="PPT 已生成，可下载交付。",
        )
    return None


def compute_recommended_next_action(status: dict, readiness: dict, evidence: dict) -> dict:
    slides = status.get("slides", [])
    raw_user_quality = evidence.get("user_quality")
    user_quality: dict[str, Any] = raw_user_quality if isinstance(raw_user_quality, dict) else {}
    should_auto_repair = user_quality.get("should_auto_repair")
    deck_level_blockers = actionable_deck_level_repair_items(evidence)
    export_state = status.get("export", {}) if isinstance(status.get("export"), dict) else {}
    has_current_export = (
        bool(export_state.get("pptx_path"))
        and str(export_state.get("status") or "") in {"exported", "review_required"}
        and evidence.get("export_is_current") is not False
    )

    if not slides:
        return build_action("create_task", "开始生成", "未生成。", reason_code="no_slides", user_message="未生成。")

    export_ready = bool(readiness.get("ready"))

    if evidence.get("qa_scope") == "slide":
        try:
            checked_slide = int(evidence.get("checked_slide") or 0)
        except (TypeError, ValueError):
            checked_slide = 0
        checked_state = next(
            (slide for slide in slides if int(slide.get("slide_id") or 0) == checked_slide),
            None,
        )
        if isinstance(checked_state, dict) and (
            str(checked_state.get("qa_status") or "") in {"failed", "qa_failed"}
            or str(checked_state.get("status") or "") in {"qa_failed", "needs_regeneration"}
        ):
            detail = f"第 {checked_slide} 页检查未通过，请先处理这一页。"
            return build_action(
                "repair_slide",
                f"处理第 {checked_slide} 页",
                detail,
                slide_id=checked_slide,
                severity="warning",
                reason_code="qa_failed_slide",
                user_message=detail,
                technical_message=str(checked_state.get("last_error") or "qa_failed_slide"),
            )

    if deck_level_blockers and not has_current_export:
        first = deck_level_blockers[0]
        detail = "当前没有可下载的 PPT，请重新生成或补齐页面。"
        return build_action(
            "repair_delivery_blocker",
            "重新生成",
            detail,
            severity="danger",
            reason_code="delivery_blocked",
            user_message=detail,
            technical_message=str(first.get("issue_code") or "deck-level-repair"),
        )

    regeneration_needed = [
        slide
        for slide in slides
        if str(slide.get("last_error_code") or "") == "layout_regeneration_needed"
        or str(slide.get("status") or "") == "needs_regeneration"
        or (
            str(slide.get("recommended_action") or "") == "auto_generate"
            and str(slide.get("qa_status") or "") in {"failed", "qa_failed"}
        )
    ]
    if regeneration_needed and not has_current_export:
        first = int(regeneration_needed[0].get("slide_id") or 1)
        detail = f"第 {first} 页需要重新生成。"
        return build_action(
            "auto_generate",
            f"重新生成第 {first} 页",
            detail,
            slide_id=first,
            severity="warning",
            reason_code="layout_regeneration_needed",
            user_message=detail,
            technical_message=str(regeneration_needed[0].get("last_error_context") or regeneration_needed[0].get("last_error_code") or ""),
        )

    failed = [slide for slide in slides if str(slide.get("qa_status") or "") in {"failed", "qa_failed"}]
    if failed and not export_ready and should_auto_repair is not False and not has_current_export:
        first = int(failed[0].get("slide_id") or 1)
        raw_error = str(failed[0].get("last_error") or "")
        translated = user_facing_error_text(raw_error)
        detail = f"第 {first} 页检查未通过，请先处理这一页。"
        if translated:
            detail = f"第 {first} 页检查未通过：{translated}"
        return build_action(
            "repair_slide",
            f"处理第 {first} 页",
            detail,
            slide_id=first,
            severity="danger",
            reason_code="qa_failed_slide",
            user_message=detail,
            technical_message=raw_error,
        )

    missing_svg = readiness.get("missing_slides") or []
    missing_ids = {int(item) for item in missing_svg}
    retryable_generation_failures = [
        slide
        for slide in slides
        if int(slide.get("slide_id") or 0) in missing_ids
        and str(slide.get("status") or "") == "failed"
        and str(slide.get("recommended_action") or "") == "auto_generate"
        and str(slide.get("last_error_code") or "") in {"provider_busy", "svg_parse_error"}
    ]
    if retryable_generation_failures and not export_ready:
        first_slide = retryable_generation_failures[0]
        first = int(first_slide.get("slide_id") or 1)
        reason_code = str(first_slide.get("last_error_code") or "generation_failed")
        detail = str(first_slide.get("last_error") or "").strip() or f"第 {first} 页生成失败，请重试本页。"
        return build_action(
            "auto_generate",
            f"重试第 {first} 页",
            detail,
            slide_id=first,
            severity="warning",
            reason_code=reason_code,
            user_message=detail,
            technical_message=str(first_slide.get("last_error_context") or first_slide.get("last_error") or ""),
        )

    if missing_svg and not export_ready:
        promptless_missing = [
            slide
            for slide in slides
            if int(slide.get("slide_id") or 0) in missing_ids
            and ((("prompt" in slide) and not str(slide.get("prompt") or "").strip()) or str(slide.get("status") or "") == "waiting_prompt")
        ]
        if promptless_missing:
            first = int(promptless_missing[0].get("slide_id") or missing_svg[0])
            return build_action(
                "edit_page_prompt",
                f"补充第 {first} 页内容",
                f"第 {first} 页还没有提示词，请先补充内容。",
                slide_id=first,
                severity="warning",
                reason_code="missing_slide_prompt",
                user_message=f"第 {first} 页还没有提示词，请先补充内容。",
            )

        raw_generation = status.get("generation")
        generation: dict[str, Any] = raw_generation if isinstance(raw_generation, dict) else {}
        first = int(missing_svg[0])
        missing_label = _format_slide_ids(missing_svg)
        missing_message = _missing_slides_user_message(missing_svg)
        if generation.get("api_key_configured") is False:
            detail = f"{missing_label}还没有生成：模型 API Key 尚未配置，PPTX 暂时不能生成。请先在模型配置中更新后再生成。"
            return build_action(
                "auto_generate",
                f"生成第 {first} 页",
                detail,
                slide_id=first,
                disabled=True,
                severity="danger",
                reason_code="api_key_missing",
                user_message=detail,
            )
        return build_action(
            "auto_generate",
            f"生成第 {first} 页",
            missing_message,
            slide_id=first,
            reason_code="missing_slide_svg",
            user_message=missing_message,
            technical_message=f"missing svg_output/slide_{first:02d}.svg",
        )

    budget_overloaded = readiness.get("budget_overloaded_slides") or []
    if budget_overloaded:
        first = int(budget_overloaded[0])
        return build_action(
            "repair_budget",
            f"优化第 {first} 页",
            f"第 {first} 页页面还需要优化，请先精简后再继续。",
            slide_id=first,
            severity="warning",
            reason_code="budget_overload",
            user_message=f"第 {first} 页页面还需要优化，请先精简后再继续。",
        )

    preflight_action = preflight_blocked_action(readiness)
    if preflight_action:
        return preflight_action

    export_action = export_recommended_next_action(status, evidence)
    if export_action:
        return export_action

    if deck_level_blockers:
        first = deck_level_blockers[0]
        detail = "当前没有可下载的 PPT，请重新生成或补齐页面。"
        return build_action(
            "repair_delivery_blocker",
            "重新生成",
            detail,
            severity="danger",
            reason_code="delivery_blocked",
            user_message=detail,
            technical_message=str(first.get("issue_code") or "deck-level-repair"),
        )

    if evidence.get("delivery_blocked") is True and should_auto_repair is not False:
        detail = "当前没有可下载的 PPT，请重新生成或补齐页面。"
        return build_action(
            "repair_delivery_blocker",
            "重新生成",
            detail,
            severity="warning",
            reason_code="delivery_blocked",
            user_message=detail,
        )

    if failed and not export_ready and should_auto_repair is False and all(slide.get("has_svg") for slide in slides):
        detail = "有页面未通过检查，请重新生成该页。"
        return build_action(
            "repair_delivery_blocker",
            "重新生成页面",
            detail,
            severity="warning",
            reason_code="delivery_blocked",
            user_message=detail,
            technical_message=str(failed[0].get("last_error") or "qa_failed_slide"),
        )

    unqa = [slide for slide in slides if str(slide.get("qa_status") or "not_run") not in {"passed"}]
    if unqa and not export_ready:
        first = int(unqa[0].get("slide_id") or 1)
        if str(status.get("generation_mode") or "api_auto") == "api_auto":
            return build_action(
                "auto_check",
                "待检查",
                f"第 {first} 页已生成，待自动检查。",
                slide_id=first,
                reason_code="slide_pending_qa",
                user_message=f"第 {first} 页已生成，待自动检查。",
            )
        return build_action(
            "qa_slide",
            "待检查",
            f"第 {first} 页已生成，待检查。",
            slide_id=first,
            reason_code="slide_pending_qa",
            user_message=f"第 {first} 页已生成，待检查。",
        )

    if readiness.get("ready") and evidence.get("last_finalize_fresh_qa") is not True:
        return build_action("fresh_release_safe", "生成", "可生成。", reason_code="fresh_finalize_required", user_message="可生成。")

    if readiness.get("ready") and evidence.get("export_is_current") is False:
        return build_action("fresh_release_safe", "生成", "可生成。", reason_code="stale_export", user_message="可生成。")

    if evidence.get("manual_review_required") is True:
        review_message = "已生成，可下载。"
        return build_action(
            "manual_review",
            "下载",
            review_message,
            severity="info",
            reason_code="manual_review_available",
            user_message=review_message,
        )

    return build_action("export_pptx", "生成", "可生成。", reason_code="ready_to_export", user_message="可生成。")
