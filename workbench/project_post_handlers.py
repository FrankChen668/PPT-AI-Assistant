from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from workbench.formal_planning import ensure_formal_planning
from workbench.quality_issue_log import (
    append_quality_issue_record,
    build_deck_finalize_issue_record,
    build_slide_qa_issue_record,
)
from workbench.quality_policy import TEXT_LAYOUT_FINDING_CODES, finding_requires_regeneration
from workbench.recommendations import summarize_preflight_blockers


def _reason_code_from_text(raw: object, *, fallback: str = "unknown") -> str:
    text = str(raw or "").lower()
    if not text:
        return fallback
    if "api key" in text and ("missing" in text or "not configured" in text):
        return "api_key_missing"
    if "http 403" in text or "permission_denied" in text or "denied access" in text or "forbidden" in text:
        return "provider_permission_denied"
    if "模型配置不一致" in text or "configmismatch" in text or "config mismatch" in text:
        return "config_mismatch"
    if "quota" in text or "resource_exhausted" in text:
        return "provider_quota"
    if "rate limit" in text or "http 429" in text:
        return "provider_rate_limit"
    if (
        "模型服务临时繁忙" in text
        or "http 500" in text
        or "http 502" in text
        or "http 503" in text
        or "http 504" in text
        or "unavailable" in text
        or "high demand" in text
        or "urlopen error" in text
        or "ssl:" in text
        or "timed out" in text
        or "connection reset" in text
        or "connection aborted" in text
    ):
        return "provider_busy"
    if "foreignobject" in text:
        return "foreign_object"
    if "invalid svg" in text or "did not contain a complete svg" in text:
        return "invalid_svg"
    if "not valid xml" in text or "parse" in text:
        return "svg_parse_error"
    if "mojibake" in text:
        return "mojibake"
    if "overflow" in text:
        return "text_overflow"
    if "safe area" in text:
        return "safe_area_violation"
    if "visual quality blocked" in text:
        return "visual_quality_blocked"
    if "qa failed" in text:
        return "qa_failed"
    if "slide count mismatch" in text:
        return "slide_count_mismatch"
    if "timeout" in text and "queue" in text:
        return "queue_timeout"
    if "export" in text:
        return "export_failed"
    return fallback


def _safe_error_text(srv: Any, raw: object) -> str:
    return srv.sanitize_generation_error_message(raw)


def _slide_generation_failure_status(reason_code: str) -> int:
    if reason_code == "config_mismatch":
        return 409
    if reason_code == "provider_busy":
        return 503
    if reason_code in {"provider_permission_denied", "quota_or_rate_limit", "provider_quota", "provider_rate_limit"}:
        return 502
    return 500


def _find_slide_state(status: dict[str, Any], slide_id: int) -> dict[str, Any] | None:
    slides = status.get("slides") if isinstance(status.get("slides"), list) else []
    for slide in slides:
        if isinstance(slide, dict) and int(slide.get("slide_id") or 0) == int(slide_id):
            return slide
    return None


def _slide_generation_already_active(slide: dict[str, Any] | None) -> bool:
    if not isinstance(slide, dict):
        return False
    status = str(slide.get("status") or "")
    phase = str(slide.get("generation_phase") or "")
    return status in {"queued", "running", "generating"} or phase in {"queued", "starting", "running", "retrying"}


def _export_placeholder_slide_ids(readiness: dict[str, Any]) -> list[int]:
    raw = readiness.get("placeholder_slides") or readiness.get("missing_slides") or []
    if not isinstance(raw, list):
        return []
    slide_ids: list[int] = []
    seen: set[int] = set()
    for item in raw:
        try:
            slide_id = int(item)
        except (TypeError, ValueError):
            continue
        if slide_id <= 0 or slide_id in seen:
            continue
        slide_ids.append(slide_id)
        seen.add(slide_id)
    return slide_ids


def _temporary_export_placeholder_svg(slide_id: int) -> str:
    title = f"第 {slide_id} 页未生成"
    body = "请在工作台处理后重新导出。"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-workbench-export-placeholder="true">
  <metadata>workbench-export-placeholder slide_{slide_id:02d}</metadata>
  <rect width="1280" height="720" fill="#F8FAFC"/>
  <rect x="84" y="84" width="1112" height="552" rx="24" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="2" stroke-dasharray="16 12"/>
  <text x="640" y="330" text-anchor="middle" font-family="Microsoft YaHei, Arial, sans-serif" font-size="42" font-weight="700" fill="#334155">{title}</text>
  <text x="640" y="390" text-anchor="middle" font-family="Microsoft YaHei, Arial, sans-serif" font-size="24" fill="#64748B">{body}</text>
</svg>
"""


def _is_temporary_export_placeholder(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return "workbench-export-placeholder" in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _install_temporary_export_placeholders(project_path: Path, slide_ids: list[int]) -> list[Path]:
    svg_dir = project_path / "svg_output"
    final_dir = project_path / "svg_final"
    svg_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for slide_id in slide_ids:
        output_path = svg_dir / f"slide_{slide_id:02d}.svg"
        final_path = final_dir / f"slide_{slide_id:02d}.svg"
        if output_path.exists() and not _is_temporary_export_placeholder(output_path):
            continue
        if final_path.exists() and not _is_temporary_export_placeholder(final_path):
            continue
        output_path.write_text(_temporary_export_placeholder_svg(slide_id), encoding="utf-8")
        created.append(output_path)
    return created


def _cleanup_temporary_export_placeholders(paths: list[Path]) -> None:
    for path in paths:
        candidates = [path]
        if path.parent.name == "svg_output":
            candidates.append(path.parent.parent / "svg_final" / path.name)
        for candidate in candidates:
            try:
                if _is_temporary_export_placeholder(candidate):
                    candidate.unlink()
            except OSError:
                continue


def _merge_iteration_note(prompt: object, iteration_note: object) -> str:
    base = str(prompt or "").strip()
    note = str(iteration_note or "").strip()
    if not note:
        return base
    if not base:
        return f"追加修改要求：\n{note}"
    return f"{base}\n\n追加修改要求：\n{note}"


def _handle_slide_generation_failure(
    handler: Any,
    srv: Any,
    name: str,
    slide_id: int,
    exc: object,
    generation_started_at: str,
    generation_started_perf: float,
    waited_sec: float,
) -> bool:
    user_message = srv.user_facing_generation_error(exc)
    technical_error = srv.sanitize_generation_error_message(exc)
    reason_code = _reason_code_from_text(user_message, fallback=_reason_code_from_text(exc, fallback="unknown"))
    target = srv.project_dir(name)
    status = srv.load_status(target) or srv.build_initial_status_from_blueprint(name, target)
    slides = status.get("slides") if isinstance(status.get("slides"), list) else []
    slide_state = next((item for item in slides if isinstance(item, dict) and int(item.get("slide_id") or 0) == int(slide_id)), None)
    if isinstance(slide_state, dict):
        slide_no = int(slide_state.get("slide_no") or slide_id)
        svg_exists = (target / "svg_output" / f"slide_{slide_no:02d}.svg").exists() or (target / "svg_final" / f"slide_{slide_no:02d}.svg").exists()
        slide_state["status"] = "qa_failed" if svg_exists else "failed"
        slide_state["has_svg"] = bool(svg_exists)
        slide_state["qa_status"] = "failed" if svg_exists else "not_run"
        slide_state["last_error"] = user_message
        slide_state["last_error_code"] = reason_code
        slide_state["recommended_action"] = "auto_generate"
        slide_state["generation_phase"] = "failed_preserved_previous" if svg_exists else "failed"
        slide_state["generation_completed_at"] = srv.iso_now()
        slide_state["lock_updated_at"] = srv.iso_now()
        status["project_status"] = "qa_failed" if svg_exists else ("svg_partial" if any(item.get("has_svg") for item in slides if isinstance(item, dict)) else "waiting_codex")
        srv.add_event(status, "api_auto_generate_failed", f"Slide {slide_id} auto generation failed: {user_message}")
        srv.save_status(target, status)
    srv.record_page_event_for_project(
        name,
        slide_id,
        "slide_generate_failed",
        phase="generation",
        status="error",
        started_at=generation_started_at,
        ended_at=srv.iso_now(),
        duration_ms=srv.elapsed_ms(generation_started_perf),
        payload={
            "error": user_message,
            "technical_error": technical_error,
            "waited_sec": round(waited_sec, 3),
            "reason_code": reason_code,
        },
    )
    handler._json_error(
        _slide_generation_failure_status(reason_code),
        code="slide_generation_failed",
        message=user_message,
        context={"project": name, "slide_id": slide_id, "reason_code": reason_code},
        data={
            "reason_code": reason_code,
            "provider_message": user_message,
            "technical_error": technical_error,
            "recommended_action": "retry this page",
        },
    )
    return True


def _strict_warning_gate_failed(stdout: object, stderr: object, summary: object) -> bool:
    text = "\n".join(str(item or "") for item in (stdout, stderr, summary)).lower()
    return "finalize produced" in text and "warning" in text and "strict mode" in text


def _strict_quality_gate_failed(stdout: object, stderr: object, summary: object) -> bool:
    text = "\n".join(str(item or "") for item in (stdout, stderr, summary)).lower()
    if _strict_warning_gate_failed(stdout, stderr, summary):
        return True
    if "layout lint failed" in text:
        return True
    if "preflight failed" in text:
        return True
    if "visual qa" in text and "failed" in text:
        return True
    return False


def _first_warning_line(stdout: object, stderr: object) -> str:
    for line in "\n".join(str(item or "") for item in (stdout, stderr)).splitlines():
        clean = line.strip()
        if clean.lower().startswith("warning:"):
            return clean
    return ""


def _layout_lint_failure_message(stdout: object, stderr: object) -> str:
    lines = [line.strip() for line in "\n".join(str(item or "") for item in (stdout, stderr)).splitlines()]
    if not any("layout lint failed" in line.lower() for line in lines):
        return ""
    selected: list[str] = []
    for line in lines:
        folded = line.lower()
        if (
            "layout lint failed" in folded
            or "layout-lint-report" in folded
            or ("error:" in folded and "layout lint" in folded)
            or ("report:" in folded and "layout-lint" in folded)
        ):
            selected.append(line)
    return "\n".join(dict.fromkeys(selected)).strip()


def _finalize_failure_message(
    *,
    preflight_user_message: str,
    stdout: object,
    stderr: object,
    summary: object,
) -> str:
    if preflight_user_message:
        return preflight_user_message
    layout_message = _layout_lint_failure_message(stdout, stderr)
    if layout_message:
        return layout_message
    if summary:
        return str(summary)
    return str(stderr or "")[-2000:]


def _slide_id_from_path_or_message(value: object) -> int:
    match = re.search(r"slide_(\d+)\.svg", str(value or ""), re.I)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_layout_lint_markdown_findings(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    findings: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or "|" not in line:
            continue
        folded = line.lower()
        code = next((item for item in sorted(TEXT_LAYOUT_FINDING_CODES, key=len, reverse=True) if item in folded), "")
        if not code or not any(item in folded for item in ("error", "warning")):
            continue
        match = re.search(r"(?:^|[\\/])?(svg_output[\\/])?slide_(\d+)\.svg", line, re.I)
        if not match:
            continue
        finding = {
            "severity": "error" if "error" in folded else "warning",
            "code": code,
            "message": line,
            "path": f"svg_output/slide_{int(match.group(2)):02d}.svg",
            "source_report": path.name,
        }
        if finding_requires_regeneration(finding):
            findings.append(finding)
    return findings


def _slide_layout_regeneration_findings(target: Path, slide_id: int) -> list[dict[str, Any]]:
    reports = [
        target / "qa" / "layout-lint-report.json",
        target / "qa" / "report.json",
    ]
    findings: list[dict[str, Any]] = []
    for report_path in reports:
        payload = _read_json_object(report_path)
        raw_findings = payload.get("findings")
        if not isinstance(raw_findings, list):
            continue
        for item in raw_findings:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            message = str(item.get("message") or "")
            path = str(item.get("path") or "")
            finding_slide = _slide_id_from_path_or_message(path) or _slide_id_from_path_or_message(message)
            if finding_slide and finding_slide != slide_id:
                continue
            if code in TEXT_LAYOUT_FINDING_CODES and finding_requires_regeneration(item):
                findings.append({**item, "source_report": str(report_path.name)})
    for item in _read_layout_lint_markdown_findings(target / "qa" / "layout-lint-report.md"):
        finding_slide = _slide_id_from_path_or_message(item.get("path")) or _slide_id_from_path_or_message(item.get("message"))
        if finding_slide and finding_slide != slide_id:
            continue
        findings.append(item)
    return findings


def handle_slide_qa(handler: Any, name: str, slide_id: int) -> bool:
    from workbench import server as srv

    target = srv.project_dir(name)
    with srv.project_structure_lock(name):
        slide_no = srv.slide_no_for_identity(target, slide_id)
        status = srv.load_status(target) or srv.build_initial_status_from_blueprint(name, target)
        ensure_formal_planning(target, status)
        slide_state = None
        for item in status.get("slides", []):
            if int(item.get("slide_id", 0)) == slide_id:
                slide_state = item
                break
        qa_started_at = srv.iso_now()
        if slide_state is not None:
            slide_state["status"] = "qa_running"
            slide_state["qa_status"] = "running"
            slide_state["qa_started_at"] = qa_started_at
            slide_state["lock_updated_at"] = qa_started_at
            srv.save_status(target, status)
        srv.record_page_event_for_project(
            name,
            slide_id,
            "slide_qa_started",
            phase="qa",
            status="running",
            started_at=qa_started_at,
        )
    qa_started_perf = time.perf_counter()
    try:
        qa = srv.run_slide_qa(srv.SlideQaRequest(project=name, slide_id=slide_no, snapshots=True))
    except Exception as exc:
        safe_error = _safe_error_text(srv, exc)
        srv.record_page_event_for_project(
            name,
            slide_id,
            "slide_qa_failed",
            phase="qa",
            status="error",
            started_at=qa_started_at,
            ended_at=srv.iso_now(),
            duration_ms=srv.elapsed_ms(qa_started_perf),
            payload={"error": safe_error, "reason_code": _reason_code_from_text(exc, fallback="qa_failed")},
        )
        raise
    result = {
        "returncode": qa.returncode,
        "stdout": qa.stdout,
        "stderr": qa.stderr,
        "summary": qa.summary,
        "report_path": qa.report_path,
    }
    quality = srv.evaluate_user_quality(target, {"qa_scope": "slide"})
    quality_blocked = str(quality.get("user_quality_status") or "") == "blocked"
    quality_blockers = [str(code) for code in quality.get("hard_blocker_codes") or [] if str(code).strip()]
    layout_regeneration_findings = _slide_layout_regeneration_findings(target, slide_no)
    qa_effective_ok = bool(qa.ok)
    if qa_effective_ok and quality_blocked:
        qa_effective_ok = False
        result["quality_override"] = {
            "blocked": True,
            "reason": "visual_quality_blocked",
            "codes": quality_blockers,
        }
        if not result.get("summary"):
            result["summary"] = "visual quality blocked"
    if layout_regeneration_findings:
        qa_effective_ok = False
        result["ok"] = False
        result["reason_code"] = "layout_regeneration_needed"
        result["layout_blockers"] = layout_regeneration_findings[:8]
        result["summary"] = "本页需要重新生成。"
    else:
        result["ok"] = qa_effective_ok
    status = srv.load_status(target) or srv.build_initial_status_from_blueprint(name, target)
    for item in status.get("slides", []):
        if int(item.get("slide_id", 0)) == slide_id:
            if qa_effective_ok:
                item["status"] = "qa_passed"
                item["qa_status"] = "passed"
                item["last_error"] = ""
                item.pop("last_error_code", None)
                item.pop("last_error_context", None)
                item.pop("recommended_action", None)
            else:
                item["status"] = "needs_regeneration" if layout_regeneration_findings else "qa_failed"
                item["qa_status"] = "failed"
                item["last_error"] = (
                    result.get("summary")
                    or qa.summary
                    or ((qa.stderr or "")[-2000:] or (qa.stdout or "")[-2000:])
                )
                if layout_regeneration_findings:
                    item["last_error_code"] = "layout_regeneration_needed"
                    item["last_error_context"] = {"layout_blockers": layout_regeneration_findings[:8]}
                    item["recommended_action"] = "auto_generate"
            item["lock_updated_at"] = srv.iso_now()
            break
    qa_reason_code = (
        ""
        if qa_effective_ok
        else (
            "layout_regeneration_needed"
            if layout_regeneration_findings
            else ("visual_quality_blocked" if quality_blocked else "qa_failed")
        )
    )
    srv.record_page_event_for_project(
        name,
        slide_id,
        "slide_qa_completed",
        phase="qa",
        status="ok" if qa_effective_ok else "failed",
        started_at=qa_started_at,
        ended_at=srv.iso_now(),
        duration_ms=srv.elapsed_ms(qa_started_perf),
        payload={
            "returncode": qa.returncode,
            "summary": result.get("summary") or qa.summary,
            "quality_blocked": quality_blocked,
            "quality_blockers": quality_blockers[:8],
            "layout_blockers": layout_regeneration_findings[:8],
            "reason_code": qa_reason_code,
        },
    )
    try:
        append_quality_issue_record(
            target,
            build_slide_qa_issue_record(
                target,
                project_name=name,
                slide_id=slide_no,
                qa_ok=qa_effective_ok,
                reason_code=qa_reason_code,
                quality=quality,
                quality_blockers=quality_blockers[:8],
                layout_blockers=layout_regeneration_findings[:8],
            ),
        )
    except Exception:
        pass
    srv.add_event(status, "slide_qa", f"Slide {slide_id} QA {'passed' if qa_effective_ok else 'failed'}.")
    srv.save_status(target, status)
    srv.json_response(
        handler,
        srv.ok("qa completed" if qa_effective_ok else "qa failed", project=name, data=result),
    )
    return True


def handle_slide_auto_generate(handler: Any, name: str, slide_id: int, payload: dict[str, Any]) -> bool:
    from workbench import server as srv

    target = srv.project_dir(name)
    status = srv.load_status(target) or srv.build_initial_status_from_blueprint(name, target)
    active_slide = _find_slide_state(status, slide_id)
    if _slide_generation_already_active(active_slide):
        srv.record_page_event_for_project(
            name,
            slide_id,
            "slide_generate_already_active",
            phase="generation",
            status="running",
            started_at=srv.iso_now(),
            payload={
                "reason_code": "slide_generation_already_active",
                "slide_status": str(active_slide.get("status") or "") if isinstance(active_slide, dict) else "",
                "generation_phase": str(active_slide.get("generation_phase") or "") if isinstance(active_slide, dict) else "",
            },
        )
        srv.json_response(
            handler,
            srv.ok(
                "slide auto generation already active",
                project=name,
                data={
                    "slide_id": slide_id,
                    "already_active": True,
                    "status": str(active_slide.get("status") or "") if isinstance(active_slide, dict) else "",
                    "generation_phase": str(active_slide.get("generation_phase") or "") if isinstance(active_slide, dict) else "",
                },
            ),
        )
        return True
    request_started_at = srv.iso_now()
    request_started_perf = time.perf_counter()
    srv.record_page_event_for_project(
        name,
        slide_id,
        "slide_generate_requested",
        phase="generation",
        status="queued",
        started_at=request_started_at,
        payload={"concurrency_limit": srv.SLIDE_GENERATION_CONCURRENCY_LIMIT},
    )
    semaphore, acquired, waited_sec = srv.acquire_generation_slot(name)
    if not acquired:
        srv.record_page_event_for_project(
            name,
            slide_id,
            "slide_generate_queue_timeout",
            phase="generation",
            status="timeout",
            started_at=request_started_at,
            ended_at=srv.iso_now(),
            duration_ms=srv.elapsed_ms(request_started_perf),
            payload={
                "waited_sec": round(waited_sec, 3),
                "queue_timeout_sec": srv.SLIDE_GENERATION_QUEUE_TIMEOUT_SEC,
                "concurrency_limit": srv.SLIDE_GENERATION_CONCURRENCY_LIMIT,
                "reason_code": "queue_timeout",
            },
        )
        handler._json_error(
            429,
            code="slide_generation_queue_timeout",
            message="Slide generation queue timeout. Please retry shortly.",
            context={
                "project": name,
                "slide_id": slide_id,
                "waited_sec": round(waited_sec, 3),
                "queue_timeout_sec": srv.SLIDE_GENERATION_QUEUE_TIMEOUT_SEC,
                "concurrency_limit": srv.SLIDE_GENERATION_CONCURRENCY_LIMIT,
            },
            data={
                "queue_timeout_sec": srv.SLIDE_GENERATION_QUEUE_TIMEOUT_SEC,
                "waited_sec": round(waited_sec, 3),
                "concurrency_limit": srv.SLIDE_GENERATION_CONCURRENCY_LIMIT,
            },
        )
        return True
    with srv.project_structure_lock(name):
        slide_no = srv.slide_no_for_identity(target, slide_id)
        if any(key in payload for key in {"page_type", "title", "prompt", "iteration_note", "content_handling", "page_style"}):
            status, _ = srv.update_page_authoring_evidence(
                target,
                slide_id,
                page_type=str(payload.get("page_type") or "content"),
                title=str(payload.get("title") or ""),
                prompt=_merge_iteration_note(payload.get("prompt"), payload.get("iteration_note")),
                content_handling=str(payload.get("content_handling") or ""),
                page_style=str(payload.get("page_style") or ""),
            )
            srv.save_status(target, status)
        status = srv.load_status(target) or srv.build_initial_status_from_blueprint(name, target)
        status["generation_mode"] = "api_auto"
        active_slide = _find_slide_state(status, slide_id)
        if not isinstance(active_slide, dict):
            semaphore.release()
            raise ValueError(f"Slide identity {slide_id} does not exist.")
        previous_generation_phase = active_slide.get("generation_phase")
        previous_lock_updated_at = active_slide.get("lock_updated_at")
        generation_started_at = srv.iso_now()
        active_slide["generation_phase"] = "admitted"
        active_slide["lock_updated_at"] = generation_started_at
        srv.save_status(target, status)
        srv.record_page_event_for_project(
            name,
            slide_id,
            "slide_generate_started",
            phase="generation",
            status="running",
            started_at=generation_started_at,
            payload={"waited_sec": round(waited_sec, 3)},
        )
    generation_started_perf = time.perf_counter()
    result = None
    # 页面已有 SVG 时属于“页面重新生成”角色，否则属于“SVG 页面生成”角色。
    generation_role = (
        "page_regeneration"
        if (target / "svg_output" / f"slide_{slide_no:02d}.svg").exists()
        else "svg_generation"
    )
    try:
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                result = srv.auto_generate_slide(
                    name,
                    target,
                    slide_id,
                    config=srv.resolve_role_generation_config(generation_role),
                    overwrite=True,
                )
                break
            except ValueError as exc:
                message = str(exc)
                if "API key is not configured" in message:
                    detail = "Real generation unavailable. Configure API key. Placeholder is dry-run only."
                    safe_message = srv.sanitize_generation_error_message(message)
                    srv.record_page_event_for_project(
                        name,
                        slide_id,
                        "slide_generate_failed",
                        phase="generation",
                        status="error",
                        started_at=generation_started_at,
                        ended_at=srv.iso_now(),
                        duration_ms=srv.elapsed_ms(generation_started_perf),
                        payload={"error": safe_message, "waited_sec": round(waited_sec, 3), "reason_code": "api_key_missing"},
                    )
                    handler._json_error(
                        409,
                        code="real_generation_unavailable",
                        message=detail,
                        context={"project": name, "slide_id": slide_id, "reason_code": "api_key_missing"},
                        data={
                            "provider_message": safe_message,
                            "recommended_action": "configure API key",
                            "placeholder_policy": "placeholder is dry-run only",
                        },
                    )
                    return True
                reason_code = _reason_code_from_text(
                    srv.user_facing_generation_error(exc),
                    fallback=_reason_code_from_text(exc, fallback="unknown"),
                )
                if reason_code == "provider_busy" and attempt < max_attempts:
                    srv.record_page_event_for_project(
                        name,
                        slide_id,
                        "slide_generate_retry",
                        phase="generation",
                        status="retrying",
                        started_at=generation_started_at,
                        payload={"attempt": attempt, "next_attempt": attempt + 1, "reason_code": reason_code},
                    )
                    time.sleep(min(0.5, attempt * 0.2))
                    continue
                return _handle_slide_generation_failure(
                    handler,
                    srv,
                    name,
                    slide_id,
                    exc,
                    generation_started_at,
                    generation_started_perf,
                    waited_sec,
                )
            except Exception as exc:
                reason_code = _reason_code_from_text(
                    srv.user_facing_generation_error(exc),
                    fallback=_reason_code_from_text(exc, fallback="unknown"),
                )
                if reason_code == "provider_busy" and attempt < max_attempts:
                    srv.record_page_event_for_project(
                        name,
                        slide_id,
                        "slide_generate_retry",
                        phase="generation",
                        status="retrying",
                        started_at=generation_started_at,
                        payload={"attempt": attempt, "next_attempt": attempt + 1, "reason_code": reason_code},
                    )
                    time.sleep(min(0.5, attempt * 0.2))
                    continue
                return _handle_slide_generation_failure(
                    handler,
                    srv,
                    name,
                    slide_id,
                    exc,
                    generation_started_at,
                    generation_started_perf,
                    waited_sec,
                )
        srv.record_page_event_for_project(
            name,
            slide_id,
            "slide_generate_completed",
            phase="generation",
            status="ok",
            started_at=generation_started_at,
            ended_at=srv.iso_now(),
            duration_ms=srv.elapsed_ms(generation_started_perf),
            payload={**(result if isinstance(result, dict) else {}), "waited_sec": round(waited_sec, 3)},
        )
    finally:
        semaphore.release()
        with srv.project_structure_lock(name):
            current_status = srv.load_status(target)
            current_slide = _find_slide_state(current_status or {}, slide_id)
            if (
                isinstance(current_slide, dict)
                and str(current_slide.get("generation_phase") or "") == "admitted"
                and str(current_slide.get("lock_updated_at") or "") == generation_started_at
            ):
                if previous_generation_phase is None:
                    current_slide.pop("generation_phase", None)
                else:
                    current_slide["generation_phase"] = previous_generation_phase
                if previous_lock_updated_at is None:
                    current_slide.pop("lock_updated_at", None)
                else:
                    current_slide["lock_updated_at"] = previous_lock_updated_at
                srv.save_status(target, current_status)
    srv.json_response(handler, srv.ok("slide auto generation completed", project=name, data=result))
    return True


def handle_slide_export_pptx(handler: Any, name: str, slide_id: int) -> bool:
    from workbench import server as srv

    target = srv.project_dir(name)
    with srv.project_structure_lock(name):
        slide_no = srv.slide_no_for_identity(target, slide_id)
        status = srv.load_status(target) or srv.build_initial_status_from_blueprint(name, target)
        export_started_at = srv.iso_now()
        srv.record_page_event_for_project(
            name,
            slide_id,
            "slide_export_started",
            phase="export",
            status="running",
            started_at=export_started_at,
        )
    guard = srv.collect_real_generation_risks(target, status)
    export_started_perf = time.perf_counter()
    placeholder_slides = [int(item) for item in guard.get("placeholder_slides") or []]
    mojibake_risks = guard.get("mojibake_risks") or []
    if slide_no in placeholder_slides:
        srv.record_page_event_for_project(
            name,
            slide_id,
            "slide_export_failed",
            phase="export",
            status="error",
            started_at=export_started_at,
            ended_at=srv.iso_now(),
            duration_ms=srv.elapsed_ms(export_started_perf),
            payload={"reason_code": "invalid_svg", "error": "placeholder is dry-run only"},
        )
        handler._json_error(
            409,
            code="real_generation_required",
            message="Placeholder slide cannot be exported as real output. placeholder is dry-run only.",
            context={"project": name, "slide_id": slide_id},
            data={
                "placeholder_slides": placeholder_slides,
                "recommended_action": "regenerate real AI content",
                "placeholder_policy": "placeholder is dry-run only",
            },
        )
        return True
    if mojibake_risks:
        srv.record_page_event_for_project(
            name,
            slide_id,
            "slide_export_failed",
            phase="export",
            status="error",
            started_at=export_started_at,
            ended_at=srv.iso_now(),
            duration_ms=srv.elapsed_ms(export_started_perf),
            payload={"reason_code": "mojibake", "error": "text integrity blocked"},
        )
        handler._json_error(
            409,
            code="text_integrity_blocked",
            message="Text integrity check failed. Mojibake markers found; repair content before export.",
            context={"project": name, "slide_id": slide_id},
            data={"mojibake_risks": mojibake_risks[:8]},
        )
        return True

    result = srv.export_single_slide_pptx(target, slide_id, slide_no=slide_no)
    artifact_pptx_sha256 = str(result.get("artifact_pptx_sha256") or "")
    if not artifact_pptx_sha256:
        export_path = Path(str(result.get("export_path") or ""))
        if export_path.is_file():
            artifact_pptx_sha256 = hashlib.sha256(export_path.read_bytes()).hexdigest()
    returncode = int(result.get("returncode") or 0)
    work_dir = Path(str(result.get("work_dir") or "")).resolve()
    has_export = bool(result.get("export_path"))
    quality_gate_blocked = bool(result.get("quality_gate_blocked"))
    stderr_text = str(result.get("stderr") or "")
    diagnostics = {
        "stderr_tail": stderr_text[-2000:],
        "qa_findings": srv.summarize_export_gate_findings(work_dir),
    }
    if returncode != 0 and not has_export:
        gate_failure = bool(diagnostics["qa_findings"])
        error_code = "single_slide_export_gate_failed" if gate_failure else "single_slide_export_failed"
        message = (
            "Single-slide export blocked by QA gate."
            if gate_failure
            else "Single-slide export command failed."
        )
        srv.update_export_status(
            target,
            status,
            {
                "last_error_code": error_code,
                "last_error_context": {
                    "project": name,
                    "slide_id": slide_id,
                    "work_dir": str(work_dir),
                    "returncode": returncode,
                },
                "last_error": message,
            },
        )
        srv.add_event(status, "single_slide_export_failed", f"Single-slide export failed for slide {slide_id}.")
        srv.save_status(target, status)
        srv.record_page_event_for_project(
            name,
            slide_id,
            "slide_export_failed",
            phase="export",
            status="failed",
            started_at=export_started_at,
            ended_at=srv.iso_now(),
            duration_ms=srv.elapsed_ms(export_started_perf),
            payload={
                "reason_code": "export_failed" if not gate_failure else "qa_failed",
                "error": _safe_error_text(srv, message),
                "returncode": returncode,
            },
        )
        handler._json_error(
            409,
            code=error_code,
            message=message,
            context={
                "project": name,
                "slide_id": slide_id,
                "work_dir": str(work_dir),
                "returncode": returncode,
            },
            data={
                "result": result,
                "diagnostics": diagnostics,
            },
        )
        return True
    if returncode != 0 and has_export:
        gate_failure = bool(diagnostics["qa_findings"])
        error_code = "single_slide_export_gate_failed" if gate_failure else "single_slide_export_failed"
        message = (
            "Single-slide export completed with review required."
            if gate_failure
            else "Single-slide export completed with fallback checks."
        )
        srv.update_export_status(
            target,
            status,
            {
                "last_error_code": error_code,
                "last_error_context": {
                    "project": name,
                    "slide_id": slide_id,
                    "work_dir": str(work_dir),
                    "returncode": returncode,
                },
                "last_error": message,
            },
        )
        srv.add_event(
            status,
            "single_slide_export_review_required",
            f"Exported slide {slide_id} with review-required findings.",
        )
        srv.save_status(target, status)
        srv.record_page_event_for_project(
            name,
            slide_id,
            "slide_export_completed",
            phase="export",
            status="review_required",
            started_at=export_started_at,
            ended_at=srv.iso_now(),
            duration_ms=srv.elapsed_ms(export_started_perf),
            payload={
                "reason_code": "qa_failed" if gate_failure else "export_failed",
                "returncode": returncode,
                "review_required": True,
                "source_svg_sha256": str(result.get("source_svg_sha256") or ""),
                "artifact_pptx_sha256": artifact_pptx_sha256,
                "export_mode": str(result.get("export_mode") or "strict"),
            },
        )
        srv.json_response(
            handler,
            srv.ok(
                message,
                project=name,
                data={
                    **result,
                    "review_required": True,
                    "diagnostics": diagnostics,
                },
            ),
        )
        return True
    if quality_gate_blocked:
        srv.update_export_status(
            target,
            status,
            {
                "last_error_code": "single_slide_export_gate_failed",
                "last_error_context": {
                    "project": name,
                    "slide_id": slide_id,
                    "work_dir": str(work_dir),
                    "returncode": int(result.get("strict_returncode") or returncode),
                },
                "last_error": "Single-slide export used relaxed fallback; review required.",
            },
        )
        srv.add_event(
            status,
            "single_slide_export_review_required",
            f"Exported slide {slide_id} with relaxed fallback; review required.",
        )
    else:
        srv.add_event(status, "single_slide_export", f"Exported slide {slide_id} as a standalone PPTX.")
        srv.update_export_status(
            target,
            status,
            {
                "last_error_code": "",
                "last_error_context": {},
                "last_error": "",
            },
        )
    srv.save_status(target, status)
    srv.record_page_event_for_project(
        name,
        slide_id,
        "slide_export_completed",
        phase="export",
        status="ok" if not quality_gate_blocked else "review_required",
        started_at=export_started_at,
        ended_at=srv.iso_now(),
        duration_ms=srv.elapsed_ms(export_started_perf),
        payload={
            "reason_code": "" if not quality_gate_blocked else "qa_failed",
            "returncode": returncode,
            "review_required": bool(quality_gate_blocked),
            "source_svg_sha256": str(result.get("source_svg_sha256") or ""),
            "artifact_pptx_sha256": artifact_pptx_sha256,
            "export_mode": str(result.get("export_mode") or "strict"),
        },
    )
    srv.json_response(
        handler,
        srv.ok(
            "single-slide export completed",
            project=name,
            data={
                **result,
                "review_required": bool(quality_gate_blocked),
                "diagnostics": diagnostics,
            },
        ),
    )
    return True


def handle_project_finalize(handler: Any, name: str, payload: dict[str, Any]) -> bool:
    from workbench import server as srv

    target = srv.project_dir(name)
    requested_mode = str(payload.get("mode") or "").strip().lower()
    fresh_requested = bool(payload.get("fresh", False))
    with srv.project_structure_lock(name):
        finalize_started_at = srv.iso_now()
        finalize_started_perf = time.perf_counter()
        status = srv.load_status(target)
        if not status:
            status = srv.build_initial_status_from_blueprint(name, target)
        previous_export = dict(status.get("export") or {}) if isinstance(status.get("export"), dict) else {}
        srv.update_export_status(target, status, {"status": "running"})
        srv.record_page_event_for_project(
            name,
            0,
            "deck_export_started",
            phase="export",
            status="running",
            started_at=finalize_started_at,
        )
    ensure_formal_planning(target, status)
    srv.save_status(target, status)
    readiness = srv.compute_export_readiness_full(name, target, status)
    readiness = srv.apply_real_generation_guards(target, status, readiness)
    if not readiness["ready"]:
        code = "project_not_export_ready"
        message = "project is not export-ready"
        if readiness.get("real_generation_blocked"):
            code = "real_generation_required"
            message = (
                "Real generation required before export. "
                "Configure API key. Placeholder is dry-run only."
            )
        srv.record_page_event_for_project(
            name,
            0,
            "deck_export_failed",
            phase="export",
            status="error",
            started_at=finalize_started_at,
            ended_at=srv.iso_now(),
            duration_ms=srv.elapsed_ms(finalize_started_perf),
            payload={"reason_code": "export_failed", "error": _safe_error_text(srv, message)},
        )
        status["export"] = previous_export
        srv.save_status(target, status)
        handler._json_error(
            409,
            code=code,
            message=message,
            context={"project": name},
            data={"export_readiness": readiness},
        )
        return True
    srv.update_export_status(
        target,
        status,
        {
            "ready": True,
            "pptx_path": "",
            "last_returncode": None,
            "last_error": "",
            "last_error_code": "",
            "last_error_context": {},
        },
    )
    placeholder_slides = _export_placeholder_slide_ids(readiness)
    temporary_placeholders = _install_temporary_export_placeholders(target, placeholder_slides)
    used_mode = requested_mode if requested_mode in {"release-safe", "premium"} else "dev-fast"
    if fresh_requested and used_mode in {"release-safe", "premium"}:
        fresh = srv.run_finalize_fresh(name, used_mode)
        returncode = int(fresh["returncode"])
        stdout = str(fresh["stdout"])
        stderr = str(fresh["stderr"])
        summary = "fresh finalize completed" if returncode == 0 else "fresh finalize failed"
        finalize_command = str(fresh["command"])
        manifest_path = str((target / "exports" / "manifest.json"))
    elif used_mode in {"release-safe", "premium"}:
        cached = srv.run_finalize_cached_mode(name, used_mode)
        returncode = int(cached["returncode"])
        stdout = str(cached["stdout"])
        stderr = str(cached["stderr"])
        summary = f"{used_mode} finalize completed" if returncode == 0 else f"{used_mode} finalize failed"
        finalize_command = str(cached["command"])
        manifest_path = str((target / "exports" / "manifest.json"))
    else:
        finalize = srv.run_finalize(
            srv.FinalizeRequest(
                project=name,
                enable_layout_lint=True,
                enable_visual_qa=True,
                enable_preflight=False,
                strict=False,
                safe_area_profile="presentation",
                snapshots=True,
            )
        )
        returncode = finalize.returncode
        stdout = finalize.stdout
        stderr = finalize.stderr
        summary = finalize.summary
        finalize_command = (
            f"cd my-ppt-skill && python scripts/build_project.py projects/{name} --phase finalize --skip-render "
            "--enable-layout-lint --enable-visual-qa --strict --safe-area-profile presentation --snapshots"
        )
        manifest_path = finalize.manifest_path
    strict_returncode = returncode
    strict_stdout = stdout
    strict_stderr = stderr
    fallback_used = False
    warning_gate_blocked = False
    if (
        used_mode in {"release-safe", "premium"}
        and returncode != 0
        and _strict_quality_gate_failed(stdout, stderr, summary)
    ):
        strict_status = srv.load_status(target) or status
        strict_readiness = srv.compute_export_readiness_full(name, target, strict_status)
        strict_preflight_blockers = strict_readiness.get("preflight_blocking_findings")
        if not isinstance(strict_preflight_blockers, list):
            strict_preflight_blockers = []
        if not strict_preflight_blockers:
            fallback = srv.run_finalize(
                srv.FinalizeRequest(
                    project=name,
                    enable_layout_lint=True,
                    enable_visual_qa=True,
                    enable_preflight=False,
                    strict=False,
                    safe_area_profile="presentation",
                    snapshots=True,
                )
            )
            fallback_used = True
            warning_gate_blocked = True
            returncode = int(fallback.returncode)
            stdout = "\n\n".join(
                item
                for item in (
                    str(strict_stdout or ""),
                    "[relaxed fallback stdout]",
                    str(fallback.stdout or ""),
                )
                if item
            )
            stderr = "\n\n".join(
                item
                for item in (
                    str(strict_stderr or ""),
                    "[relaxed fallback stderr]",
                    str(fallback.stderr or ""),
                )
                if item
            )
            summary = fallback.summary or "relaxed finalize completed after strict warning gate"
            finalize_command = f"{finalize_command} && relaxed fallback finalize"
            manifest_path = fallback.manifest_path
    _cleanup_temporary_export_placeholders(temporary_placeholders)
    export = srv.exported_pptx_path(target, require_current=True)
    next_status = srv.load_status(target) or srv.build_initial_status_from_blueprint(name, target)
    srv.sync_status_slides_with_blueprint(target, next_status)
    expected_slides = srv.expected_project_slide_count(target, next_status)
    exported_slides = srv.count_pptx_slides(export) if export is not None else None
    slide_count_mismatch = bool(
        export is not None
        and expected_slides > 0
        and exported_slides is not None
        and exported_slides != expected_slides
    )
    if slide_count_mismatch:
        mismatch_msg = (
            f"Exported PPT slide count mismatch: expected {expected_slides}, got {exported_slides}."
        )
        summary = mismatch_msg
        if stderr:
            stderr = f"{stderr}\n{mismatch_msg}"
        else:
            stderr = mismatch_msg
        returncode = returncode if returncode != 0 else 1
    evidence = srv.compute_finalize_evidence(target)
    raw_user_quality = evidence.get("user_quality")
    user_quality: dict[str, Any] = raw_user_quality if isinstance(raw_user_quality, dict) else {}
    export_exists = export is not None
    export_artifact_ok = export_exists and exported_slides is not None and not slide_count_mismatch
    post_finalize_readiness = srv.compute_export_readiness_full(name, target, next_status)
    preflight_blockers = post_finalize_readiness.get("preflight_blocking_findings")
    if not isinstance(preflight_blockers, list):
        preflight_blockers = []
    preflight_user_message = summarize_preflight_blockers(preflight_blockers)
    finalize_failure_message = _finalize_failure_message(
        preflight_user_message=preflight_user_message,
        stdout=stdout,
        stderr=stderr,
        summary=summary,
    )
    review_required_export = bool(
        export_artifact_ok
        and (
            fallback_used
            or placeholder_slides
            or preflight_blockers
            or user_quality.get("manual_review_required")
            or evidence["manual_review_required"]
        )
    )
    export_status_value = "review_required" if review_required_export else "exported"
    export_context = {
        "project": name,
        "mode": used_mode,
        "fresh_requested": fresh_requested,
        "returncode": returncode,
        "strict_returncode": strict_returncode,
        "fallback_used": fallback_used,
        "expected_slide_count": expected_slides,
        "exported_slide_count": exported_slides,
        "placeholder_slides": placeholder_slides,
        "manual_review_required": review_required_export,
        "strict_warning": _first_warning_line(strict_stdout, strict_stderr),
    }
    if returncode == 0 and export_artifact_ok:
        pptx_relpath = srv.to_relative_path(target, export)
        srv.update_export_status(
            target,
            next_status,
            {
                "status": export_status_value,
                "ready": True,
                "pptx_path": pptx_relpath,
                "last_returncode": 0,
                "last_error": "",
                "last_error_code": "",
                "last_error_context": export_context if review_required_export else {},
            },
        )
    elif export_artifact_ok:
        pptx_relpath = srv.to_relative_path(target, export)
        srv.update_export_status(
            target,
            next_status,
            {
                "status": "review_required",
                "ready": True,
                "pptx_path": pptx_relpath,
                "last_returncode": returncode,
                "last_error": "",
                "last_error_code": "",
                "last_error_context": export_context,
            },
        )
    else:
        srv.update_export_status(
            target,
            next_status,
            {
                "status": "failed",
                "ready": True,
                "pptx_path": "",
                "last_returncode": returncode,
                "last_error": finalize_failure_message,
                "last_error_code": "deck-finalize-failed",
                "last_error_context": {
                    "project": name,
                    "mode": used_mode,
                    "fresh_requested": fresh_requested,
                    "returncode": returncode,
                    "strict_returncode": strict_returncode,
                    "fallback_used": fallback_used,
                    "expected_slide_count": expected_slides,
                    "exported_slide_count": exported_slides,
                    "preflight_blockers": preflight_blockers,
                    **({"user_facing_error": preflight_user_message} if preflight_user_message else {}),
                },
            },
        )
    finalize_status = export_status_value if export_artifact_ok else "failed"
    data = {
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "summary": summary,
        "manifest_path": manifest_path,
        "export_path": str(export) if export is not None else None,
        "finalize_command": finalize_command,
        "last_finalize_mode": evidence["last_finalize_mode"],
        "last_finalize_fresh_qa": evidence["last_finalize_fresh_qa"],
        "last_finalize_cache_hit": evidence["last_finalize_cache_hit"],
        "last_qa_report_path": evidence["last_qa_report_path"],
        "last_contact_sheet_path": evidence["last_contact_sheet_path"],
        "qa_scope": evidence["qa_scope"],
        "checked_slide": evidence["checked_slide"],
        "manual_review_required": evidence["manual_review_required"],
        "delivery_blocked": evidence["delivery_blocked"],
        "user_quality": user_quality,
        "finalize_status": finalize_status,
        "expected_slide_count": expected_slides,
        "exported_slide_count": exported_slides,
        "placeholder_slides": placeholder_slides,
        "strict_returncode": strict_returncode,
        "fallback_used": fallback_used,
        "strict_warning_gate_blocked": warning_gate_blocked,
    }
    if preflight_blockers:
        data["preflight_blockers"] = preflight_blockers
    if preflight_user_message:
        data["user_facing_error"] = preflight_user_message
    if fallback_used:
        data["strict_warning"] = _first_warning_line(strict_stdout, strict_stderr)
    if finalize_status == "failed" and returncode != 0:
        data["doctor_hint"] = f"cd my-ppt-skill && python scripts/doctor_export.py projects/{name}"
    srv.record_page_event_for_project(
        name,
        0,
        "deck_export_completed" if finalize_status in {"exported", "review_required"} else "deck_export_failed",
        phase="export",
        status="ok" if finalize_status == "exported" else ("review_required" if finalize_status == "review_required" else "failed"),
        started_at=finalize_started_at,
        ended_at=srv.iso_now(),
        duration_ms=srv.elapsed_ms(finalize_started_perf),
        payload={
            "reason_code": "" if finalize_status == "exported" else ("qa_failed" if finalize_status == "review_required" else "export_failed"),
            "returncode": returncode,
            "finalize_status": finalize_status,
            "expected_slide_count": expected_slides,
            "exported_slide_count": exported_slides,
            "placeholder_slides": placeholder_slides,
        },
    )
    try:
        append_quality_issue_record(target, build_deck_finalize_issue_record(target, project_name=name, data=data))
    except Exception:
        pass
    srv.json_response(
        handler,
        srv.ok(
            "finalize completed"
            if finalize_status == "exported"
            else "finalize review required"
            if finalize_status == "review_required"
            else "finalize failed",
            project=name,
            data=data,
        ),
    )
    return True
