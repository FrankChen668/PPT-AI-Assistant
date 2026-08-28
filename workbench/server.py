#!/usr/bin/env python3
from __future__ import annotations

import base64
import binascii
import importlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime
from html import escape as html_escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlparse

from workbench.state import (
    add_event,
    backup_slide_revision as backup_slide_revision,
    compute_export_readiness,
    compute_project_status,
    list_slide_revisions,
    load_status,
    restore_slide_revision as restore_slide_revision,
    save_status,
    update_export_status as update_export_status,
)
from workbench.routes import resolve_route
from workbench.task_store import initialize_task_store
from workbench.page_authoring import (
    PAGE_TYPES,
    append_slide_to_project,
    build_initial_status_from_blueprint,
    delete_slide_from_project,
    insert_slide_after_project,
    is_true_single_page_workflow,
    normalize_content_handling,
    normalize_page_style,
    repair_budget_overload as repair_budget_overload,
    update_page_authoring_evidence,
)
from workbench.generation import (
    DEFAULT_SETTINGS_PATH,
    auto_generate_project,
    auto_generate_slide as auto_generate_slide,
    load_generation_config,
    public_generation_settings,
    sanitize_generation_error_message,
    update_generation_settings,
    user_facing_generation_error as user_facing_generation_error,
)
from workbench.finalize_evidence import (
    compute_finalize_evidence as _compute_finalize_evidence,
    export_relpath,
    resolve_latest_exported_pptx,
)
from workbench.single_page_export import (
    export_single_slide_pptx as export_single_slide_pptx,
    promote_single_slide_work_output,
)
from workbench.quality_policy import evaluate_user_quality as evaluate_user_quality
from workbench.server_io import (
    read_latest_manifest_record as io_read_latest_manifest_record,
    read_qa_report_summary as io_read_qa_report_summary,
    read_json_object as io_read_json_object,
)
from workbench.recommendations import (
    compute_recommended_next_action,
    visual_delivery_ready,
)
from workbench.project_listing import collect_workbench_projects
from workbench.status_service import (
    apply_delivery_contract_state,
    apply_export_readiness_state,
    apply_finalize_evidence_to_export_state,
    build_missing_project_status,
    generation_metadata_for_status,
    normalize_workflow_mode as normalize_workflow_mode,
    resolve_workflow_fields,
    workflow_label as workflow_label,
)
from workbench.real_generation_guards import (
    MOJIBAKE_TOKENS as MOJIBAKE_TOKENS,
    PLACEHOLDER_SVG_MARKERS as PLACEHOLDER_SVG_MARKERS,
    apply_real_generation_guards,
    collect_real_generation_risks as collect_real_generation_risks,
)
from workbench.project_post_handlers import (
    handle_project_finalize,
    handle_slide_auto_generate,
    handle_slide_export_pptx,
    handle_slide_qa,
)
from workbench.project_post_extra_handlers import (
    handle_project_budget_repair,
    handle_project_placeholder_svg,
    handle_slide_budget_repair,
    handle_slide_executor_packet,
    handle_slide_placeholder_svg,
    handle_slide_restore_revision,
)
from workbench.prompt_intake import make_user_task_title, normalize_submission_prompt
from workbench.content_planning import plan_rough_deck_content
from workbench.connections import (
    DEFAULT_CONNECTIONS_PATH,
    create_connection,
    delete_connection,
    list_connection_models,
    list_connections,
    seed_connection_from_settings,
    test_connection,
    update_connection,
)
from workbench.role_routing import (
    DEFAULT_ROLE_ROUTING_PATH,
    load_role_routing,
    resolve_role_config,
    update_role_routing,
)
from workbench.generation import call_model_generate
from workbench.generation_settings import GenerationConfig
from workbench.project_writer import (
    set_context as set_project_writer_context,
    create_design_spec as _pw_create_design_spec,
    create_outline as _pw_create_outline,
    create_clarification_brief as _pw_create_clarification_brief,
    create_blueprint as _pw_create_blueprint,
    create_art_direction as _pw_create_art_direction,
    create_reference_pack as _pw_create_reference_pack,
    create_slide_visual_plan as _pw_create_slide_visual_plan,
    write_project_files as _pw_write_project_files,
    split_prompt as _pw_split_prompt,
)
from workbench.task_writer import (
    set_context as set_task_writer_context,
    route_policy_text as _tw_route_policy_text,
    create_agent_task as _tw_create_agent_task,
    create_slide_task as _tw_create_slide_task,
    create_slide_regenerate_task as _tw_create_slide_regenerate_task,
    create_slide_repair_task as _tw_create_slide_repair_task,
    create_budget_repair_task as _tw_create_budget_repair_task,
    create_export_diagnostic_task as _tw_create_export_diagnostic_task,
    create_workbench_task as _tw_create_workbench_task,
    parse_source_inputs as _tw_parse_source_inputs,
    prepare_document_sources as _tw_prepare_document_sources,
)
from workbench.integrations import (
    set_context as set_integrations_context,
    run_skill_command as _int_run_skill_command,
    template_binding_status as _int_template_binding_status,
    bind_template_to_project as _int_bind_template_to_project,
    resolve_template_instruction as _int_resolve_template_instruction,
    compute_export_readiness_full as _int_compute_export_readiness_full,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "my-ppt-skill"
SKILL_SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS_DIR))
PROJECTS_DIR = SKILL_DIR / "projects"
OUTLINE_TEMP_PROJECT_PREFIX = "workbench-outline-"
# C13-B：模板画廊唯一数据源（运行时模板索引权威路径）。
LAYOUTS_INDEX_PATH = SKILL_DIR / "ppt-ai-core" / "templates" / "layouts" / "layouts_index.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"
WORKBENCH_DB_PATH = Path(__file__).resolve().parent / "workbench.db"
GENERATION_SETTINGS_PATH = DEFAULT_SETTINGS_PATH
CONNECTIONS_PATH = DEFAULT_CONNECTIONS_PATH
ROLE_ROUTING_PATH = DEFAULT_ROLE_ROUTING_PATH
WORKBENCH_UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"
DEFAULT_WORKBENCH_HOST = "0.0.0.0"
DEFAULT_WORKBENCH_PORT = 8765
MAX_DOCUMENT_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_DOCUMENT_UPLOAD_SUFFIXES = {".pdf", ".doc", ".docx", ".txt", ".md", ".markdown", ".rtf"}
CONTENT_PLANNING_TIMEOUT_SECONDS = 360
CONTENT_PLANNING_MAX_TOTAL_ATTEMPTS = 1

def normalize_workbench_page_type(value: object) -> str:
    page_type = str(value or "").strip()
    return page_type if page_type in PAGE_TYPES else "content"

def _load_symbol(module_name: str, symbol_name: str) -> Any:
    module = importlib.import_module(module_name)
    return getattr(module, symbol_name)

SlideQaRequest = _load_symbol("quality.qa_adapter", "SlideQaRequest")
run_slide_qa = _load_symbol("quality.qa_adapter", "run_slide_qa")
FinalizeRequest = _load_symbol("export.export_adapter", "FinalizeRequest")
run_finalize = _load_symbol("export.export_adapter", "run_finalize")
generate_executor_packet = _load_symbol("generate_executor_packet", "generate_executor_packet")
evaluate_budget_policy = _load_symbol("generate_slide_plan", "evaluate_budget_policy")

PROJECT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SCENES = {"report", "proposal", "product"}
STYLE_PROFILES = {"consulting_blue", "tech_dark", "minimal_white", "consulting_classic"}
GENERATION_MODES = {"api_auto"}
DECK_TYPES = {"single", "multi"}
PAGE_COUNTS = {1, 3, 4, 5, 8, 10}
SLIDE_GENERATION_CONCURRENCY_LIMIT = 3
SLIDE_GENERATION_QUEUE_TIMEOUT_SEC = 90.0
DELETE_STALE_LOCK_TIMEOUT_SEC = 120.0
_GENERATION_SEMAPHORE_LOCK = threading.Lock()
_GENERATION_SEMAPHORES: dict[str, threading.BoundedSemaphore] = {}
_TASK_STORE_MIGRATION_LOCK = threading.Lock()
_TASK_STORE_MIGRATED = False
_TASK_STORE_MIGRATED_KEYS: set[tuple[str, str]] = set()
_PREVIEW_EVENT_LOCK = threading.Lock()
_PREVIEW_EVENT_CACHE: dict[tuple[str, int, str, str], float] = {}
_PREVIEW_EVENT_DEDUP_SECONDS = 10.0

SCENE_MAP = {
    "report": {
        "audience": "management reviewers",
        "decision_goal": "understand progress, risks, and next actions",
        "purpose": "项目汇报",
        "quality_profile": "presentation",
    },
    "proposal": {
        "audience": "executive decision makers and proposal reviewers",
        "decision_goal": "evaluate solution value and approve next-stage action",
        "purpose": "投标方案 / 售前汇报",
        "quality_profile": "premium",
    },
    "product": {
        "audience": "customers and internal product stakeholders",
        "decision_goal": "understand product value, core capability, and adoption path",
        "purpose": "产品介绍",
        "quality_profile": "presentation",
    },
}

_STYLE_FONT_TITLE = '"PingFang SC", "Microsoft YaHei", "Arial", sans-serif'
_STYLE_FONT_BODY = '"PingFang SC", "Microsoft YaHei", "Arial", sans-serif'
_STYLE_FONT_LADDER = "H1 46/1.15/700, Body 24/1.45/400, Caption 16/1.4/400"

STYLE_MAP = {
    "consulting_blue": {
        "label": "咨询蓝",
        "style": "minimalist",
        "primary_color": "#123B7A",
        "accent_color": "#FF7A1A",
        "background_color": "#F7FAFF",
        "card_bg": "#FFFFFF",
        "text_color": "#172033",
        "muted_color": "#667085",
        "line_color": "#D8E2F2",
        "font_title": _STYLE_FONT_TITLE,
        "font_body": _STYLE_FONT_BODY,
        "font_ladder": _STYLE_FONT_LADDER,
        "style_goal": "consulting-grade blue business page with clear hierarchy and restrained orange emphasis",
        "template_preference": "free design; no fixed template selected in POC",
    },
    "tech_dark": {
        "label": "科技深色",
        "style": "tech",
        "primary_color": "#0B1220",
        "accent_color": "#38BDF8",
        "background_color": "#08111F",
        "card_bg": "#FFFFFF",
        "text_color": "#E5EDF7",
        "muted_color": "#94A3B8",
        "line_color": "#D8E2F2",
        "font_title": _STYLE_FONT_TITLE,
        "font_body": _STYLE_FONT_BODY,
        "font_ladder": _STYLE_FONT_LADDER,
        "style_goal": "dark technology page with high contrast and structured evidence blocks",
        "template_preference": "free design; no fixed template selected in POC",
    },
    "minimal_white": {
        "label": "极简白底",
        "style": "minimalist",
        "primary_color": "#111827",
        "accent_color": "#2563EB",
        "background_color": "#FFFFFF",
        "card_bg": "#FFFFFF",
        "text_color": "#111827",
        "muted_color": "#6B7280",
        "line_color": "#D8E2F2",
        "font_title": _STYLE_FONT_TITLE,
        "font_body": _STYLE_FONT_BODY,
        "font_ladder": _STYLE_FONT_LADDER,
        "style_goal": "minimal white business page with quiet typography and strong readability",
        "template_preference": "free design; no fixed template selected in POC",
    },
    "consulting_classic": {
        "label": "咨询风格",
        "style": "consulting_classic",
        "primary_color": "#AD053D",
        "accent_color": "#932341",
        "background_color": "#F2F6F6",
        "card_bg": "#FFFFFF",
        "text_color": "#4A5558",
        "muted_color": "#6B7E85",
        "line_color": "#7C969D",
        "font_title": '"Microsoft YaHei", "PingFang SC", "Arial", sans-serif',
        "font_body": '"Microsoft YaHei", "PingFang SC", "Arial", sans-serif',
        "font_ladder": _STYLE_FONT_LADDER,
        "style_goal": "table-first consulting style with restrained wine-red accents, blue-gray structure lines, and generous whitespace",
        "template_preference": "consulting_classic; table-first consulting template with hybrid dark cover and light content pages",
    },
}

TEMPLATE_MODES = {
    "free": {
        "label": "自由设计",
        "instruction": "No fixed template is selected. Codex may choose layout freely while obeying design_spec.md and blueprint.json.",
    },
    "reference": {
        "label": "参考模板",
        "instruction": "Use available project template references if template_binding.json or templates/layout_ref exists. If none exists, state that no concrete template is bound and proceed with a compatible layout.",
    },
    "reuse": {
        "label": "沿用上次风格",
        "instruction": "Reuse the current project's design_spec.md style tokens and previous generated SVG visual language when regenerating slides.",
    },
    "strict_template": {
        "label": "严格模板",
        "instruction": "Follow the bound template structure strictly, including section order, grid relationship, and visual hierarchy.",
    },
}


def json_response(handler: SimpleHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    response_payload = dict(payload) if isinstance(payload, dict) else payload
    request_id = str(getattr(handler, "_request_id", "") or "")
    if request_id and isinstance(response_payload, dict) and "request_id" not in response_payload:
        response_payload["request_id"] = request_id
    body = json.dumps(response_payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    if request_id:
        handler.send_header("X-Request-Id", request_id)
    handler.end_headers()
    handler.wfile.write(body)


def ok(message: str, project: str | None = None, data: dict | None = None) -> dict:
    return {"ok": True, "message": message, "project": project, "data": data or {}}


def fail(message: str, data: dict | None = None) -> dict:
    return {
        "ok": False,
        "message": message,
        "data": data or {},
        "error": {
            "code": "request-failed",
            "message": message,
            "context": {},
        },
    }


def fail_structured(
    code: str,
    message: str,
    *,
    data: dict | None = None,
    context: dict[str, Any] | None = None,
) -> dict:
    payload = fail(message, data=data)
    payload["error"] = {
        "code": str(code or "request-failed"),
        "message": message,
        "context": context or {},
    }
    return payload


def next_request_id() -> str:
    return f"wb-{uuid.uuid4().hex[:12]}"


def sanitize_upload_filename(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return "document.bin"
    base = Path(raw).name
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    clean = clean.strip("._-")
    return clean or "document.bin"


def stage_document_upload(filename: str, content_base64: str) -> dict[str, Any]:
    payload = str(content_base64 or "").strip()
    if not payload:
        raise ValueError("上传内容为空。")
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("上传内容不是有效的 base64。") from exc
    if not raw:
        raise ValueError("上传内容为空。")
    if len(raw) > MAX_DOCUMENT_UPLOAD_BYTES:
        raise ValueError(f"上传文件超过上限 {MAX_DOCUMENT_UPLOAD_BYTES // (1024 * 1024)} MB。")
    safe_name = sanitize_upload_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_DOCUMENT_UPLOAD_SUFFIXES:
        raise ValueError("仅支持 PDF/DOC/DOCX/TXT/MD/RTF 文件上传。")
    stamp = datetime.now().strftime("%Y%m%d")
    bucket = WORKBENCH_UPLOADS_DIR / stamp
    bucket.mkdir(parents=True, exist_ok=True)
    target = bucket / f"wbup-{uuid.uuid4().hex[:10]}-{safe_name}"
    target.write_bytes(raw)
    return {
        "filename": safe_name,
        "size_bytes": len(raw),
        "source_path": str(target.resolve()),
        "relative_path": str(target.relative_to(REPO_ROOT)).replace("\\", "/"),
    }


def delete_workbench_task_and_project(store: Any, task_id: str) -> dict[str, Any]:
    task = store.get_task(task_id)
    if not task:
        raise FileNotFoundError("Task not found")
    project_name = str(task.get("project_name") or "").strip()
    project_removed = False
    project_archived = False
    project_archive_path = ""
    if project_name:
        clean_project = validate_project_name(project_name)
        target = (PROJECTS_DIR / clean_project).resolve()
        projects_root = PROJECTS_DIR.resolve()
        if target != projects_root and projects_root in target.parents and target.exists():
            archive_root = projects_root / ".workbench_archive" / "deleted-tasks"
            archive_root.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            archive_target = archive_root / f"{stamp}_{clean_project}_{task_id}"
            target.replace(archive_target)
            project_removed = True
            project_archived = True
            project_archive_path = str(archive_target.relative_to(projects_root)).replace("\\", "/")
    with store.connect() as conn:
        conn.execute("DELETE FROM workbench_tasks WHERE id = ?", (task_id,))
        conn.commit()
    session = store.get_session()
    if session.get("current_task_id") == task_id:
        store.update_session(current_view="mode_select", current_task_id="")
    return {
        "task_id": task_id,
        "project_name": project_name,
        "project_removed": project_removed,
        "project_archived": project_archived,
        "project_archive_path": project_archive_path,
    }


def task_purge_busy_context(status: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(status, dict):
        return None
    project_status = str(status.get("project_status") or "").strip().lower()
    if project_status in {"generating", "qa_running", "export_running"}:
        return {"busy_scope": "project", "busy_status": project_status}
    export_info = status.get("export") if isinstance(status.get("export"), dict) else {}
    export_status = str(export_info.get("status") or "").strip().lower()
    if export_status == "running":
        return {"busy_scope": "export", "busy_status": export_status}
    slides = status.get("slides") if isinstance(status.get("slides"), list) else []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        if slide_is_busy_for_delete(slide) and not slide_is_stale_for_delete(slide, status):
            return {
                "busy_scope": "slide",
                "busy_status": str(slide.get("status") or ""),
                "busy_slide_id": int(slide.get("slide_id") or 0),
            }
    return None


def purge_workbench_task_and_project(store: Any, task_id: str) -> dict[str, Any]:
    task = store.get_task(task_id)
    if not task:
        return {
            "task_id": task_id,
            "project_name": "",
            "project_removed": False,
            "already_deleted": True,
        }
    project_name = str(task.get("project_name") or "").strip()
    project_removed = False
    if project_name:
        clean_project = validate_project_name(project_name)
        target = (PROJECTS_DIR / clean_project).resolve()
        projects_root = PROJECTS_DIR.resolve()
        if target != projects_root and projects_root in target.parents and target.exists():
            try:
                shutil.rmtree(target)
                project_removed = True
            except FileNotFoundError:
                # 并发重复删除时目录可能已被另一请求移除，按幂等处理。
                pass
    with store.connect() as conn:
        conn.execute("DELETE FROM workbench_tasks WHERE id = ?", (task_id,))
        conn.commit()
    session = store.get_session()
    if session.get("current_task_id") == task_id:
        store.update_session(current_view="mode_select", current_task_id="")
    return {
        "task_id": task_id,
        "project_name": project_name,
        "project_removed": project_removed,
        "already_deleted": False,
    }


def project_generation_semaphore(project_name: str) -> threading.BoundedSemaphore:
    clean = validate_project_name(project_name)
    with _GENERATION_SEMAPHORE_LOCK:
        sem = _GENERATION_SEMAPHORES.get(clean)
        if sem is None:
            sem = threading.BoundedSemaphore(SLIDE_GENERATION_CONCURRENCY_LIMIT)
            _GENERATION_SEMAPHORES[clean] = sem
        return sem


def acquire_generation_slot(project_name: str, timeout_sec: float | None = None) -> tuple[threading.BoundedSemaphore, bool, float]:
    semaphore = project_generation_semaphore(project_name)
    timeout_value = SLIDE_GENERATION_QUEUE_TIMEOUT_SEC if timeout_sec is None else float(timeout_sec)
    started = time.monotonic()
    acquired = semaphore.acquire(timeout=max(0.0, timeout_value))
    waited_sec = max(0.0, time.monotonic() - started)
    return semaphore, acquired, waited_sec


def slide_is_busy_for_delete(slide: dict[str, Any] | None) -> bool:
    if not isinstance(slide, dict):
        return False
    status = str(slide.get("status") or "").strip().lower()
    qa_status = str(slide.get("qa_status") or "").strip().lower()
    return status in {"generating", "qa_running"} or qa_status == "running"


def _parse_iso8601(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def slide_delete_lock_age_seconds(slide: dict[str, Any] | None, status: dict[str, Any] | None = None) -> float | None:
    if not isinstance(slide, dict):
        return None
    status = status if isinstance(status, dict) else {}
    candidates = [
        _parse_iso8601(slide.get("lock_updated_at")),
        _parse_iso8601(slide.get("qa_started_at")),
        _parse_iso8601(slide.get("generation_started_at")),
        _parse_iso8601(status.get("updated_at")),
    ]
    alive = [item for item in candidates if item is not None]
    if not alive:
        return None
    latest = max(alive)
    return max(0.0, (datetime.now().astimezone() - latest).total_seconds())


def slide_is_stale_for_delete(
    slide: dict[str, Any] | None,
    status: dict[str, Any] | None = None,
    *,
    timeout_sec: float = DELETE_STALE_LOCK_TIMEOUT_SEC,
) -> bool:
    if not slide_is_busy_for_delete(slide):
        return False
    age_sec = slide_delete_lock_age_seconds(slide, status)
    if age_sec is None:
        return False
    return age_sec >= max(0.0, float(timeout_sec))


def summarize_export_gate_findings(work_dir: Path) -> list[dict[str, Any]]:
    report = work_dir / "qa" / "layout-lint-report.json"
    if not report.exists():
        return []
    payload, warning = io_read_json_object(report, encoding="utf-8")
    if warning:
        return []
    findings = payload.get("findings") if isinstance(payload, dict) else None
    if not isinstance(findings, list):
        return []
    summary: list[dict[str, Any]] = []
    for item in findings[:5]:
        if not isinstance(item, dict):
            continue
        summary.append(
            {
                "severity": str(item.get("severity") or ""),
                "code": str(item.get("code") or ""),
                "message": str(item.get("message") or ""),
            }
        )
    return summary


def validate_project_name(name: str) -> str:
    clean = name.strip()
    if not PROJECT_RE.fullmatch(clean):
        raise ValueError("Project name must contain only letters, numbers, dash, and underscore.")
    return clean


def project_dir(name: str) -> Path:
    clean = validate_project_name(name)
    path = (PROJECTS_DIR / clean).resolve()
    if PROJECTS_DIR.resolve() not in path.parents:
        raise ValueError("Project path escapes projects directory.")
    return path


def read_json_body(handler: SimpleHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object.")
    return payload


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_skill_command(args: list[str]) -> dict:
    return _int_run_skill_command(args)

def run_document_intake(project_name: str, quality_threshold: int = 55) -> dict[str, Any]:
    name = validate_project_name(project_name)
    target = project_dir(name)
    try:
        module = importlib.import_module("document_intake")
        runner = getattr(module, "run_document_intake")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"文档 Intake 模块加载失败：{exc}") from exc
    try:
        result = runner(target, quality_threshold=int(quality_threshold), strict_gate=False)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"文档 Intake 执行失败：{exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("文档 Intake 返回结果无效。")
    parse_report_path = target / "parse_report.json"
    source_manifest_path = target / "source_manifest.json"
    document_ir_path = target / "document_ir.json"
    parse_payload, warning = io_read_json_object(parse_report_path, encoding="utf-8")
    if warning:
        raise ValueError(str(warning.get("message") or "无法读取 parse_report.json"))
    gate_passed = bool(parse_payload.get("gate_passed")) if isinstance(parse_payload, dict) else False
    return {
        "project": name,
        "parse_report_path": str(parse_report_path),
        "source_manifest_path": str(source_manifest_path),
        "document_ir_path": str(document_ir_path),
        "gate_passed": gate_passed,
        "parse_quality_score": int((parse_payload or {}).get("parse_quality_score") or 0),
        "fallback_triggered": bool((parse_payload or {}).get("fallback_triggered")),
        "record_count": len((parse_payload or {}).get("records") or []),
    }

def template_binding_status(target: Path) -> dict:
    return _int_template_binding_status(target)


def bind_template_to_project(target: Path, template_id: str, *, layouts_dir: Path) -> bool:
    return _int_bind_template_to_project(target, template_id, layouts_dir=layouts_dir)

def resolve_template_instruction(template_mode: str, binding: dict) -> str:
    return _int_resolve_template_instruction(template_mode, binding)

def route_policy_text(route: dict) -> str:
    return _tw_route_policy_text(route)

def compute_export_readiness_full(name: str, target: Path, status: dict) -> dict:
    return _int_compute_export_readiness_full(name, target, status)

def to_relative_path(target: Path, absolute_or_relative: Path) -> str:
    candidate = absolute_or_relative
    if candidate.is_absolute():
        try:
            return str(candidate.relative_to(target)).replace("\\", "/")
        except ValueError:
            return str(candidate).replace("\\", "/")
    return str(candidate).replace("\\", "/")


def read_latest_manifest_record(target: Path) -> tuple[dict, str, list[dict[str, Any]]]:
    return io_read_latest_manifest_record(target)


def read_qa_report_summary(target: Path) -> dict:
    return io_read_qa_report_summary(target)


def compute_finalize_evidence(target: Path) -> dict:
    return _compute_finalize_evidence(
        target,
        exported_pptx_resolver=lambda project: exported_pptx_path(project, require_current=True),
    )

def exported_pptx_path(target: Path, *, require_current: bool = False) -> Path | None:
    return resolve_latest_exported_pptx(target, require_current=require_current)


def single_slide_export_path(target: Path, slide_id: int) -> Path | None:
    single_pages_dir = target / "exports" / "single-pages"
    canonical = single_pages_dir / f"slide_{slide_id:02d}.pptx"
    pattern = f"slide_{slide_id:02d}*.pptx"
    candidates = [path for path in single_pages_dir.glob(pattern) if path.is_file()]
    if canonical.exists() and canonical not in candidates:
        candidates.append(canonical)
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def count_pptx_slides(pptx_path: Path) -> int | None:
    try:
        with zipfile.ZipFile(pptx_path, "r") as archive:
            count = 0
            for name in archive.namelist():
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                    count += 1
            return count
    except (OSError, zipfile.BadZipFile):
        return None


def expected_project_slide_count(target: Path, status: dict) -> int:
    try:
        blueprint = read_blueprint(target)
    except (FileNotFoundError, ValueError, OSError):
        blueprint = {}
    blueprint_slides = blueprint.get("slides") if isinstance(blueprint, dict) else None
    if isinstance(blueprint_slides, list) and blueprint_slides:
        return len(blueprint_slides)
    slides = status.get("slides") if isinstance(status.get("slides"), list) else []
    if slides:
        return len(slides)
    return int(status.get("slide_count") or 0)


def task_store():
    global _TASK_STORE_MIGRATED
    store = initialize_task_store(WORKBENCH_DB_PATH)
    key = (str(WORKBENCH_DB_PATH.resolve()), str(PROJECTS_DIR.resolve()))
    if not _TASK_STORE_MIGRATED:
        _TASK_STORE_MIGRATED_KEYS.clear()
    if key not in _TASK_STORE_MIGRATED_KEYS:
        with _TASK_STORE_MIGRATION_LOCK:
            if key not in _TASK_STORE_MIGRATED_KEYS:
                store.migrate_projects(PROJECTS_DIR)
                _TASK_STORE_MIGRATED_KEYS.add(key)
                _TASK_STORE_MIGRATED = True
    return store


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def elapsed_ms(started_perf: float) -> int:
    return max(0, int(round((time.perf_counter() - started_perf) * 1000)))


def record_page_event_for_project(
    project_name: str,
    slide_id: int,
    event_type: str,
    *,
    phase: str,
    status: str = "",
    started_at: str = "",
    ended_at: str = "",
    duration_ms: int | None = None,
    payload: dict | None = None,
) -> dict:
    if event_type == "slide_preview_served":
        source = str((payload or {}).get("source") or "")
        key = (project_name, int(slide_id), event_type, source)
        now_perf = time.monotonic()
        with _PREVIEW_EVENT_LOCK:
            last_perf = _PREVIEW_EVENT_CACHE.get(key)
            if last_perf is not None and now_perf - last_perf < _PREVIEW_EVENT_DEDUP_SECONDS:
                return {}
            _PREVIEW_EVENT_CACHE[key] = now_perf
    try:
        store = task_store()
        task = store.get_task_by_project(project_name)
        if not task:
            return {}
        return store.append_page_event(
            str(task["id"]),
            project_name=project_name,
            slide_id=slide_id,
            event_type=event_type,
            phase=phase,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            payload=payload,
        )
    except Exception as exc:
        sys.stderr.write(f"[workbench] failed to record page event {event_type}: {exc}\n")
        return {}


def task_session_payload(store) -> dict:
    session = store.get_session()
    current_id = session.get("current_task_id") or ""
    current_task: dict[str, Any] | None = store.get_task(current_id) if current_id else None
    if current_id and not current_task:
        session = store.update_session(current_view="mode_select", current_task_id="")
        current_task = None
    return {"session": session, "current_task": current_task}


def sync_visible_tasks_from_projects(store) -> None:
    for task in store.list_tasks()[:20]:
        task_id = str(task.get("id") or "")
        project_name = str(task.get("project_name") or "")
        if not task_id or not project_name:
            continue
        if str(task.get("status") or "") == "completed":
            continue
        target = project_dir(project_name)
        if not target.exists():
            store.mark_missing_project(task_id)
            continue
        status = load_status(target)
        if not status:
            continue
        store.sync_task_from_project(
            task_id,
            {
                "project_status": status.get("project_status", ""),
                "updated_at": status.get("updated_at", ""),
                "recommended_next_action": status.get("recommended_next_action", {}),
                "export": status.get("export", {}),
                "slide_count": status.get("slide_count", 0),
                "slides": status.get("slides", []),
            },
        )


def slide_packet_paths(target: Path, slide_id: int) -> tuple[Path, Path]:
    packet_dir = target / "executor_packets"
    return packet_dir / f"slide_{slide_id:02d}.json", packet_dir / f"slide_{slide_id:02d}.md"


def enrich_slides_for_workbench(
    target: Path,
    slides: list[dict],
    reviews_by_slide: dict[int, dict[str, Any]] | None = None,
) -> list[dict]:
    reviews = reviews_by_slide or {}
    enriched: list[dict] = []
    for item in slides:
        slide = dict(item)
        slide_id = int(slide.get("slide_id") or 0)
        if slide_id < 1:
            enriched.append(slide)
            continue
        review = reviews.get(slide_id, {})
        packet_json, packet_md = slide_packet_paths(target, slide_id)
        has_svg = bool(slide.get("has_svg"))
        qa_status = str(slide.get("qa_status") or "not_run")
        slide["packet_status"] = "packet_ready" if packet_json.exists() else "packet_missing"
        slide["packet_path"] = to_relative_path(target, packet_json) if packet_json.exists() else ""
        slide["packet_markdown_path"] = to_relative_path(target, packet_md) if packet_md.exists() else ""
        slide["svg_status"] = "svg_authored" if has_svg else "svg_missing"
        if qa_status == "passed":
            slide["qa_status_field"] = "qa_passed"
        elif qa_status in {"failed", "qa_failed"}:
            slide["qa_status_field"] = "qa_failed"
        else:
            slide["qa_status_field"] = "qa_pending"
        slide["review_score"] = review.get("score")
        slide["review_usable_for_next_edit"] = review.get("usable_for_next_edit")
        slide["review_pptx_editable"] = review.get("pptx_editable")
        slide["review_issue_tags"] = review.get("issue_tags") or []
        slide["review_notes"] = review.get("notes") or ""
        slide["review_updated_at"] = review.get("updated_at") or ""
        enriched.append(slide)
    return enriched


def sync_status_slides_with_blueprint(target: Path, status: dict) -> bool:
    try:
        blueprint = read_blueprint(target)
    except ValueError:
        return False
    raw_slides = blueprint.get("slides") if isinstance(blueprint, dict) else []
    if not isinstance(raw_slides, list):
        return False
    if str(status.get("deck_type") or "").strip() == "single":
        raw_slides = raw_slides[:1]
    status_slides = status.get("slides")
    if not isinstance(status_slides, list):
        status_slides = []
    existing_by_id: dict[int, dict[str, Any]] = {}
    for item in status_slides:
        if not isinstance(item, dict):
            continue
        slide_id = int(item.get("slide_id") or 0)
        if slide_id > 0 and slide_id not in existing_by_id:
            existing_by_id[slide_id] = item
    rebuilt: list[dict[str, Any]] = []
    changed = False
    for index, slide in enumerate(raw_slides, start=1):
        content = slide.get("content", {}) if isinstance(slide, dict) else {}
        default_title = ""
        if isinstance(slide, dict):
            default_title = str(slide.get("title") or content.get("headline") or content.get("statement") or "").strip()
        page_type = normalize_workbench_page_type(slide.get("page_type") if isinstance(slide, dict) else "content")
        content_handling = normalize_content_handling(slide.get("content_handling") if isinstance(slide, dict) else "")
        page_style = normalize_page_style(slide.get("page_style") if isinstance(slide, dict) else "")
        prompt = str(content.get("body") or content.get("support") or "") if isinstance(content, dict) else ""
        existing = existing_by_id.get(index)
        if isinstance(existing, dict):
            merged = dict(existing)
        else:
            merged = {
                "slide_id": index,
                "title": default_title or f"{index}. 未命名页面",
                "page_type": page_type,
                "content_handling": content_handling,
                "page_style": page_style,
                "prompt": prompt,
                "status": "waiting_codex",
                "svg_path": f"svg_output/slide_{index:02d}.svg",
                "has_svg": False,
                "qa_status": "not_run",
                "revision_count": 0,
                "last_error": "",
            }
            changed = True
        if int(merged.get("slide_id") or 0) != index:
            changed = True
        merged["slide_id"] = index
        if not str(merged.get("title") or "").strip():
            merged["title"] = default_title or f"{index}. 未命名页面"
            changed = True
        normalized_existing_page_type = normalize_workbench_page_type(merged.get("page_type"))
        if merged.get("page_type") != normalized_existing_page_type:
            merged["page_type"] = normalized_existing_page_type
            changed = True
        if not str(merged.get("page_type") or "").strip():
            merged["page_type"] = page_type
            changed = True
        normalized_existing_content_handling = normalize_content_handling(merged.get("content_handling"))
        if merged.get("content_handling") != normalized_existing_content_handling:
            merged["content_handling"] = normalized_existing_content_handling
            changed = True
        if not str(merged.get("content_handling") or "").strip():
            merged["content_handling"] = content_handling
            changed = True
        normalized_existing_page_style = normalize_page_style(merged.get("page_style"))
        if merged.get("page_style") != normalized_existing_page_style:
            merged["page_style"] = normalized_existing_page_style
            changed = True
        if not str(merged.get("page_style") or "").strip():
            merged["page_style"] = page_style
            changed = True
        if not str(merged.get("prompt") or "").strip() and prompt:
            merged["prompt"] = prompt
            changed = True
        rebuilt.append(merged)
    if len(rebuilt) != len(status_slides):
        changed = True
    if changed:
        status["slides"] = rebuilt
        status["slide_count"] = len(rebuilt)
    return changed


def constrain_single_page_readiness(status: dict, readiness: dict) -> dict:
    if str(status.get("deck_type") or "").strip() != "single":
        return readiness
    constrained = dict(readiness)
    for key in (
        "missing_slides",
        "qa_failed_slides",
        "qa_not_run_slides",
        "svg_missing_slides",
        "budget_overloaded_slides",
    ):
        values = constrained.get(key)
        if isinstance(values, list):
            constrained[key] = [item for item in values if int(item or 0) <= 1]
    reasons = constrained.get("reasons")
    if isinstance(reasons, list):
        filtered_reasons: list[str] = []
        replaced_missing_reason = False
        missing_slides = [
            int(item or 0)
            for item in (constrained.get("missing_slides") if isinstance(constrained.get("missing_slides"), list) else [])
            if int(item or 0) > 0
        ]
        for item in reasons:
            reason = str(item or "")
            is_missing_svg_reason = "SVG" in reason and ("页面" in reason or "slide" in reason.lower())
            if is_missing_svg_reason:
                if missing_slides and not replaced_missing_reason:
                    filtered_reasons.append("以下页面还没有 SVG：" + ", ".join(str(slide) for slide in missing_slides))
                    replaced_missing_reason = True
                continue
            filtered_reasons.append(reason)
        constrained["reasons"] = filtered_reasons
        if not filtered_reasons:
            constrained["ready"] = True
            constrained["status"] = "ready"
    return constrained


def run_finalize_fresh(project: str, quality_mode: str) -> dict:
    command = [
        sys.executable,
        "scripts/build_project.py",
        f"projects/{project}",
        "--phase",
        "finalize",
        "--skip-render",
        "--auto-slide-plan",
        "--auto-slide-plan-overwrite",
        "--enable-layout-lint",
        "--enable-visual-qa",
        "--strict",
        "--safe-area-profile",
        "presentation",
        "--snapshots",
        "--quality-mode",
        quality_mode,
        "--profile",
        "proposal_consulting",
    ]
    completed = subprocess.run(
        command,
        cwd=SKILL_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "command": "cd my-ppt-skill && " + " ".join(command[1:]),
    }


def run_finalize_cached_mode(project: str, quality_mode: str) -> dict:
    command = [
        sys.executable,
        "scripts/run_mode.py",
        quality_mode,
        f"projects/{project}",
    ]
    completed = subprocess.run(
        command,
        cwd=SKILL_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "command": "cd my-ppt-skill && " + " ".join(command[1:]),
    }


def require_non_empty(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must be non-empty.")
    return text


def require_choice(value: object, field: str, choices: set[str]) -> str:
    text = str(value or "").strip()
    if text not in choices:
        raise ValueError(f"{field} must be one of {', '.join(sorted(choices))}.")
    return text


def page_count_from_payload(payload: dict) -> int:
    deck_type = require_choice(payload.get("deck_type", "single"), "deck_type", DECK_TYPES)
    if deck_type == "single":
        return 1
    try:
        page_count = int(payload.get("page_count", 3))
    except (TypeError, ValueError) as exc:
        raise ValueError("page_count must be a number.") from exc
    if page_count < 1 or page_count > 80:
        raise ValueError("page_count must be between 1 and 80.")
    return page_count


def split_prompt(prompt: str, count: int) -> list[dict[str, str]]:
    return _pw_split_prompt(prompt, count)

def create_design_spec(
    scene: dict,
    style: dict,
    page_count: int = 1,
    template_mode: str = "free",
    template_instruction: str = "",
    route: dict | None = None,
    template_binding: dict | None = None,
) -> str:
    return _pw_create_design_spec(scene, style, page_count, template_mode, template_instruction, route, template_binding)

def create_outline(slides: list[dict[str, str]]) -> str:
    return _pw_create_outline(slides)

def create_clarification_brief(
    scene: dict,
    style: dict,
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
) -> dict:
    return _pw_create_clarification_brief(scene, style, template_mode, template_instruction, route, template_binding)

def create_blueprint(
    slides: list[dict[str, str]],
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
) -> dict:
    return _pw_create_blueprint(slides, template_mode, template_instruction, route, template_binding)

def create_agent_task(
    name: str,
    slides: list[dict[str, str]],
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
) -> str:
    return _tw_create_agent_task(name, slides, template_mode, template_instruction, route, template_binding)

def create_slide_task(
    name: str,
    slide: dict[str, str],
    slide_id: int,
    total: int,
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
) -> str:
    return _tw_create_slide_task(name, slide, slide_id, total, template_mode, template_instruction, route, template_binding)

def create_slide_regenerate_task(
    name: str,
    slide: dict[str, str],
    slide_id: int,
    total: int,
    route: dict,
    template_mode: str,
    template_instruction: str,
    template_binding: dict,
) -> str:
    return _tw_create_slide_regenerate_task(name, slide, slide_id, total, route, template_mode, template_instruction, template_binding)

def create_slide_repair_task(
    name: str,
    slide_id: int,
    total: int,
    qa_excerpt: str,
    route: dict,
    template_mode: str,
    template_instruction: str,
    template_binding: dict,
) -> str:
    return _tw_create_slide_repair_task(name, slide_id, total, qa_excerpt, route, template_mode, template_instruction, template_binding)

def create_budget_repair_task(
    name: str,
    slide_id: int,
    total: int,
    budget_excerpt: str,
    route: dict,
    template_mode: str,
    template_instruction: str,
    template_binding: dict,
) -> str:
    return _tw_create_budget_repair_task(
        name,
        slide_id,
        total,
        budget_excerpt,
        route,
        template_mode,
        template_instruction,
        template_binding,
    )

def create_export_diagnostic_task(
    name: str,
    export_excerpt: str,
    route: dict,
    template_mode: str,
    template_instruction: str,
    template_binding: dict,
) -> str:
    return _tw_create_export_diagnostic_task(
        name,
        export_excerpt,
        route,
        template_mode,
        template_instruction,
        template_binding,
    )

def repair_excerpt_from_qa(target: Path, slide_id: int, fallback: str) -> str:
    lines: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    qa_item_found = False
    repair_plan_path = target / "qa" / "repair_plan.json"
    if repair_plan_path.exists():
        payload, io_warning = io_read_json_object(repair_plan_path, encoding="utf-8")
        if io_warning:
            warning_code = str(io_warning.get("code") or "repair-plan-read-failed")
            warning_message = str(io_warning.get("message") or "Could not read repair_plan.json")
            lines.append(f"- [{warning_code}] {warning_message}")
            payload = {}
        items = payload.get("items") if isinstance(payload, dict) else []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    item_slide_id = int(item.get("slide_id") or 0)
                except (TypeError, ValueError):
                    item_slide_id = 0
                if item_slide_id != slide_id:
                    continue
                code = str(item.get("issue_code") or "qa-finding").strip()
                message = str(item.get("message") or "").strip()
                action = str(item.get("recommended_action") or "").strip()
                key = (code, message, action)
                if key in seen:
                    continue
                seen.add(key)
                qa_item_found = True
                line = f"- [{code}] {message}"
                if action:
                    line += f" Apply: {action}"
                lines.append(line)
                if len(lines) >= 8:
                    break
    if lines and not qa_item_found and fallback:
        lines.append(f"- [fallback-context] {str(fallback).strip()}")
    if lines:
        return "\n".join(lines)
    return str(fallback or "")


def read_repair_plan_items(target: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    repair_plan_path = target / "qa" / "repair_plan.json"
    if not repair_plan_path.exists():
        return [], None
    payload, io_warning = io_read_json_object(repair_plan_path, encoding="utf-8")
    if payload is None:
        payload = {}
    items_raw = payload.get("items") if isinstance(payload, dict) else []
    items: list[dict[str, Any]] = []
    if isinstance(items_raw, list):
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            try:
                slide_id = int(item.get("slide_id") or 0)
            except (TypeError, ValueError):
                slide_id = 0
            items.append(
                {
                    "slide_id": slide_id,
                    "issue_code": str(item.get("issue_code") or "").strip(),
                    "message": str(item.get("message") or "").strip(),
                    "recommended_action": str(item.get("recommended_action") or "").strip(),
                    "repair_scope": str(item.get("repair_scope") or "").strip(),
                    "severity": str(item.get("severity") or "").strip(),
                }
            )
    return items, io_warning


def deck_level_repair_blockers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for item in items:
        scope = str(item.get("repair_scope") or "").strip().lower()
        slide_id = int(item.get("slide_id") or 0)
        is_deck_level = scope == "deck_level" or (not scope and slide_id <= 0)
        if not is_deck_level:
            continue
        blockers.append(item)
    return blockers

def create_art_direction(style: dict) -> str:
    return _pw_create_art_direction(style)

def create_reference_pack(
    style: dict,
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
) -> dict:
    return _pw_create_reference_pack(style, template_mode, template_instruction, route, template_binding)

def create_slide_visual_plan(slides: list[dict[str, str]]) -> dict:
    return _pw_create_slide_visual_plan(slides)

def write_project_files(name: str, payload: dict) -> dict:
    return _pw_write_project_files(name, payload)

def resolve_role_generation_config(role: str) -> "GenerationConfig | None":
    return resolve_role_config(role, ROLE_ROUTING_PATH, CONNECTIONS_PATH, settings_path=GENERATION_SETTINGS_PATH)


def call_content_planning_model_generate(prompt: str, config: GenerationConfig) -> str:
    return call_model_generate(
        prompt,
        config,
        timeout=CONTENT_PLANNING_TIMEOUT_SECONDS,
        max_total_attempts=CONTENT_PLANNING_MAX_TOTAL_ATTEMPTS,
    )


def create_workbench_task(payload: dict) -> dict:
    planning_payload = dict(payload)
    document_context = _tw_prepare_document_sources(planning_payload)
    if document_context is not None:
        planning_payload["project_name"] = document_context["project_name"]
        source_grounded_context = str(document_context.get("source_grounded_context") or "").strip()
        if source_grounded_context:
            planning_payload["source_grounded_context"] = source_grounded_context
    requested_name = str(payload.get("project_name") or "").strip()
    if document_context is not None:
        requested_name = str(planning_payload.get("project_name") or "").strip()
    if requested_name and PROJECT_RE.fullmatch(requested_name):
        planning_payload["existing_blueprint"] = (project_dir(requested_name) / "blueprint.json").is_file()
    planning_config = resolve_role_generation_config("content_planning")
    if planning_config is not None and planning_config.model_source == "role_routing":
        # 角色路由命中时绕开全局 fallback 链，否则注入的连接配置会被重查的全局设置覆盖。
        content_plan = plan_rough_deck_content(
            planning_payload,
            config=planning_config,
            generate=call_content_planning_model_generate,
        )
    elif planning_config is not None:
        content_plan = plan_rough_deck_content(
            planning_payload,
            config=planning_config,
            generate=call_model_generate,
        )
    else:
        content_plan = plan_rough_deck_content(
            planning_payload,
            config_loader=lambda: load_generation_config(GENERATION_SETTINGS_PATH),
        )
    task_kwargs: dict[str, Any] = {"content_plan": content_plan}
    if document_context is not None:
        task_kwargs["document_context"] = document_context
    return _tw_create_workbench_task(planning_payload, **task_kwargs)


def _is_document_outline_request(payload: dict) -> bool:
    workflow_mode = normalize_workflow_mode(payload.get("workflow_mode"), str(payload.get("deck_type", "multi")))
    return workflow_mode == "document_deck" and bool(_tw_parse_source_inputs(payload.get("source_inputs")))


def _remove_temporary_outline_workspace(workspace: Path) -> None:
    """只删除本请求刚创建、且仍位于项目根目录下一层的临时目录。"""
    projects_root = PROJECTS_DIR.resolve()
    resolved_workspace = workspace.resolve()
    if (
        resolved_workspace.parent != projects_root
        or not resolved_workspace.name.startswith(OUTLINE_TEMP_PROJECT_PREFIX)
    ):
        raise ValueError("Refusing to remove an unexpected outline temporary workspace.")
    if resolved_workspace.exists():
        shutil.rmtree(resolved_workspace)


def _prepare_temporary_outline_document_context(payload: dict) -> tuple[dict, Path]:
    """为文档大纲预览复用 Intake；调用方必须在请求结束时清理返回路径。"""
    projects_root = PROJECTS_DIR.resolve()
    if not projects_root.is_dir():
        raise ValueError("Projects directory is unavailable for document outline preview.")
    workspace = Path(tempfile.mkdtemp(prefix=OUTLINE_TEMP_PROJECT_PREFIX, dir=str(projects_root))).resolve()
    if workspace.parent != projects_root or not workspace.name.startswith(OUTLINE_TEMP_PROJECT_PREFIX):
        raise ValueError("Temporary outline workspace escaped the controlled projects root.")
    planning_payload = dict(payload)
    planning_payload["project_name"] = workspace.name
    try:
        document_context = _tw_prepare_document_sources(planning_payload)
        if document_context is None:
            raise ValueError("Document outline preview requires prepared source materials.")
        if str(document_context.get("project_name") or "") != workspace.name:
            raise ValueError("Document outline preview returned an unexpected temporary project.")
        source_grounded_context = str(document_context.get("source_grounded_context") or "").strip()
        if not source_grounded_context:
            raise ValueError("Document outline preview did not produce source-grounded context.")
        planning_payload["source_grounded_context"] = source_grounded_context
        return planning_payload, workspace
    except Exception:
        _remove_temporary_outline_workspace(workspace)
        raise


def _plan_outline_content(payload: dict) -> dict:
    planning_config = resolve_role_generation_config("content_planning")
    if planning_config is not None and planning_config.model_source == "role_routing":
        return plan_rough_deck_content(
            payload,
            config=planning_config,
            generate=call_content_planning_model_generate,
        )
    if planning_config is not None:
        return plan_rough_deck_content(
            payload,
            config=planning_config,
            generate=call_model_generate,
        )
    return plan_rough_deck_content(
        payload,
        config_loader=lambda: load_generation_config(GENERATION_SETTINGS_PATH),
    )

def build_project_name(deck_type: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"codex-{deck_type}-ppt-{stamp}-{uuid.uuid4().hex[:8]}"


def resolve_server_address(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, int]:
    args = list(sys.argv if argv is None else argv)
    env = os.environ if environ is None else environ
    host = str(env.get("WORKBENCH_HOST") or DEFAULT_WORKBENCH_HOST).strip() or DEFAULT_WORKBENCH_HOST
    raw_port = args[1] if len(args) > 1 else env.get("WORKBENCH_PORT", str(DEFAULT_WORKBENCH_PORT))
    try:
        port = int(str(raw_port).strip())
    except ValueError as exc:
        raise ValueError("WORKBENCH_PORT must be an integer.") from exc
    if port < 1 or port > 65535:
        raise ValueError("WORKBENCH_PORT must be between 1 and 65535.")
    return host, port


def write_server_pid_file(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{int(pid)}\n", encoding="ascii")


def remove_server_pid_file(path: Path, pid: int) -> None:
    try:
        recorded = path.read_text(encoding="ascii").strip()
    except OSError:
        return
    if recorded != str(int(pid)):
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def slide_count_for_project(name: str) -> int:
    target = project_dir(name)
    try:
        blueprint = read_blueprint(target)
    except (ValueError, OSError, json.JSONDecodeError):
        return 0
    slides = blueprint.get("slides")
    return len(slides) if isinstance(slides, list) else 0


def slide_path(target: Path, slide_id: int, folder: str = "svg_output") -> Path:
    if slide_id < 1 or slide_id > 99:
        raise ValueError("slide id must be between 1 and 99.")
    return target / folder / f"slide_{slide_id:02d}.svg"


def project_slide_status(name: str) -> list[dict]:
    target = project_dir(name)
    count = slide_count_for_project(name)
    slides: list[dict] = []
    qa_report = target / "qa" / "report.md"
    for slide_id in range(1, count + 1):
        output = slide_path(target, slide_id, "svg_output")
        final = slide_path(target, slide_id, "svg_final")
        task = target / "agent_tasks" / f"slide_{slide_id:02d}.md"
        slides.append(
            {
                "slide_id": slide_id,
                "has_svg_output": output.exists(),
                "has_svg_final": final.exists(),
                "has_task": task.exists(),
                "task_path": str(task) if task.exists() else None,
                "qa_available": qa_report.exists(),
                "status": "generated" if output.exists() or final.exists() else "pending_generation",
            }
        )
    return slides


def read_blueprint(target: Path) -> dict:
    blueprint = target / "blueprint.json"
    if not blueprint.exists():
        raise ValueError("Missing blueprint.json.")
    try:
        payload = json.loads(blueprint.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid blueprint.json: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read blueprint.json: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("blueprint.json root must be an object.")
    return payload


def read_design_tokens(target: Path) -> dict[str, str]:
    tokens = {
        "primary_color": "#123B7A",
        "accent_color": "#FF7A1A",
        "background_color": "#F7FAFF",
        "text_color": "#172033",
        "muted_color": "#667085",
    }
    path = target / "design_spec.md"
    if not path.exists():
        return tokens
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        key = key.strip()
        if key in tokens:
            tokens[key] = value.strip()
    return tokens


def wrap_text(text: str, max_chars: int = 28, max_lines: int = 4) -> list[str]:
    clean = " ".join(text.split())
    lines: list[str] = []
    current = ""
    for char in clean:
        current += char
        if len(current) >= max_chars:
            lines.append(current)
            current = ""
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines or [clean[:max_chars]]


def write_placeholder_svg(name: str, slide_id: int = 1) -> Path:
    target = project_dir(name)
    blueprint = read_blueprint(target)
    slides = blueprint.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("blueprint.json must contain at least one slide.")
    if slide_id < 1 or slide_id > len(slides):
        raise ValueError("slide id does not exist in blueprint.")
    slide = slides[slide_id - 1]
    content = slide.get("content", {}) if isinstance(slide, dict) else {}
    title = str(content.get("headline") or content.get("statement") or slide.get("title") or "单页校验")
    body = str(content.get("body") or content.get("support") or "")
    title = re.sub(r"[A-Za-z][A-Za-z0-9\\-_/]*", "", title)
    body = re.sub(r"[A-Za-z][A-Za-z0-9\\-_/]*", "", body)
    title = " ".join(title.split()).strip(" -_") or "工作台流程校验"
    body = " ".join(body.split()).strip()
    tokens = read_design_tokens(target)
    background_color = html_escape(tokens["background_color"])
    primary_color = html_escape(tokens["primary_color"])
    accent_color = html_escape(tokens["accent_color"])
    text_color = html_escape(tokens["text_color"])
    headline = html_escape(title)
    body_lines = wrap_text(body, max_chars=30, max_lines=4)
    variant = (slide_id - 1) % 3
    if variant == 0:
        body_tspans = "\n".join(
            f'      <tspan x="104" dy="{0 if index == 0 else 38}">{html_escape(line)}</tspan>'
            for index, line in enumerate(body_lines)
        )
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <!-- slide_id={slide_id} layout_tag=Statement-Bold visual_archetype=left-accent-board template_id=workbench-poc -->
  <rect x="0" y="0" width="1280" height="720" fill="{background_color}"/>
  <rect x="64" y="56" width="1152" height="608" fill="#FFFFFF" stroke="{primary_color}" stroke-width="1.5" opacity="0.18"/>
  <rect x="64" y="56" width="14" height="608" fill="{accent_color}"/>
  <text x="104" y="104" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="17" font-weight="600" opacity="0.72">工作台流程校验页</text>
  <text x="104" y="182" fill="{primary_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="58" font-weight="700">{headline}</text>
  <text x="104" y="310" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="28" font-weight="400">
{body_tspans}
  </text>
  <line x1="104" y1="564" x2="1178" y2="564" stroke="{primary_color}" stroke-width="2" opacity="0.14"/>
  <text x="104" y="612" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="17" font-weight="400" opacity="0.68">
    占位页，仅用于流程校验。
  </text>
</svg>
'''
    elif variant == 1:
        body_tspans = "\n".join(
            f'      <tspan x="104" dy="{0 if index == 0 else 34}">{html_escape(line)}</tspan>'
            for index, line in enumerate(body_lines)
        )
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <!-- slide_id={slide_id} layout_tag=Two-Column-Insight visual_archetype=top-band-with-sidebar template_id=workbench-poc -->
  <rect x="0" y="0" width="1280" height="720" fill="#FFFFFF"/>
  <rect x="0" y="0" width="1280" height="176" fill="{primary_color}"/>
  <text x="92" y="86" fill="#FFFFFF" font-family="Microsoft YaHei, Arial, sans-serif" font-size="16" font-weight="600" opacity="0.82">工作台流程校验页</text>
  <text x="92" y="146" fill="#FFFFFF" font-family="Microsoft YaHei, Arial, sans-serif" font-size="54" font-weight="700">{headline}</text>
  <rect x="78" y="228" width="760" height="372" fill="{background_color}" stroke="{primary_color}" stroke-width="1.2" opacity="0.96"/>
  <text x="104" y="286" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="26" font-weight="400">
{body_tspans}
  </text>
  <rect x="884" y="228" width="318" height="372" fill="#F2F7FF" stroke="{primary_color}" stroke-width="1.1"/>
  <text x="912" y="286" fill="{primary_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="21" font-weight="700">执行提示</text>
  <text x="912" y="336" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="18" font-weight="400">逐页交付</text>
  <text x="912" y="372" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="18" font-weight="400">单页检查</text>
  <text x="912" y="408" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="18" font-weight="400">最终导出</text>
</svg>
'''
    else:
        body_tspans = "\n".join(
            f'      <tspan x="112" dy="{0 if index == 0 else 36}">{html_escape(line)}</tspan>'
            for index, line in enumerate(body_lines)
        )
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <!-- slide_id={slide_id} layout_tag=Focus-Card visual_archetype=hero-card-right-focus template_id=workbench-poc -->
  <rect x="0" y="0" width="1280" height="720" fill="{background_color}"/>
  <circle cx="1110" cy="96" r="168" fill="{accent_color}" opacity="0.14"/>
  <rect x="72" y="72" width="700" height="576" fill="#FFFFFF" stroke="{primary_color}" stroke-width="1.4"/>
  <text x="112" y="124" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="17" font-weight="600" opacity="0.74">工作台流程校验页</text>
  <text x="112" y="198" fill="{primary_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="56" font-weight="700">{headline}</text>
  <text x="112" y="318" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="27" font-weight="400">
{body_tspans}
  </text>
  <rect x="820" y="170" width="380" height="420" fill="#FFFFFF" stroke="{primary_color}" stroke-width="1.2"/>
  <text x="852" y="238" fill="{primary_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="24" font-weight="700">闭环检查</text>
  <line x1="852" y1="258" x2="1158" y2="258" stroke="{primary_color}" stroke-width="1.2" opacity="0.25"/>
  <text x="852" y="304" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="18" font-weight="400">1. 任务交接</text>
  <text x="852" y="344" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="18" font-weight="400">2. 页面预览</text>
  <text x="852" y="384" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="18" font-weight="400">3. 单页修复</text>
  <text x="852" y="424" fill="{text_color}" font-family="Microsoft YaHei, Arial, sans-serif" font-size="18" font-weight="400">4. 导出归档</text>
</svg>
'''
    output = slide_path(target, slide_id, "svg_output")
    write_text(output, svg)
    return output


def load_slide_reviews_for_project(project_name: str) -> tuple[dict[str, Any], dict[int, dict[str, Any]], list[dict[str, Any]]]:
    store = task_store()
    task = store.get_task_by_project(project_name)
    if not task:
        return {}, {}, []
    task_id = str(task.get("id") or "")
    if not task_id:
        return task, {}, []
    reviews = store.list_slide_reviews(task_id)
    by_slide: dict[int, dict[str, Any]] = {}
    for review in reviews:
        slide_id = int(review.get("slide_id") or 0)
        if slide_id < 1:
            continue
        by_slide[slide_id] = review
    return task, by_slide, reviews


def build_project_status_slide_context(
    name: str,
    target: Path,
    status: dict[str, Any],
) -> tuple[dict[str, Any], str, list[dict[str, Any]], list[dict[str, Any]]]:
    task_meta, reviews_by_slide, review_items = load_slide_reviews_for_project(name)
    task_title = str(task_meta.get("title") or status.get("title") or name)
    slides = enrich_slides_for_workbench(target, status.get("slides", []), reviews_by_slide=reviews_by_slide)
    status["slides"] = slides
    return task_meta, task_title, slides, review_items


def project_status(name: str) -> dict:
    target = project_dir(name)
    if not target.exists():
        return build_missing_project_status()
    status = load_status(target)
    if not status:
        status = build_initial_status_from_blueprint(name, target)
    if sync_status_slides_with_blueprint(target, status):
        save_status(target, status)
    readiness = compute_export_readiness_full(name, target, status)
    readiness = constrain_single_page_readiness(status, readiness)
    readiness = apply_real_generation_guards(target, status, readiness)
    status["project_status"] = compute_project_status(status, readiness)
    status["slide_count"] = len(status.get("slides", []))
    workflow_mode, workflow_label_value = resolve_workflow_fields(status)
    stale_export = exported_pptx_path(target)
    current_export = exported_pptx_path(target, require_current=True)
    apply_export_readiness_state(
        status,
        readiness,
        stale_export_relpath=export_relpath(target, stale_export) if stale_export is not None else "",
        current_export_relpath=export_relpath(target, current_export) if current_export is not None else "",
    )
    task_meta, task_title, slides, review_items = build_project_status_slide_context(name, target, status)
    evidence = compute_finalize_evidence(target)
    exported_slide_count = count_pptx_slides(current_export) if current_export is not None else None
    evidence["artifact_created"] = current_export is not None and exported_slide_count is not None
    evidence["pptx_openable"] = exported_slide_count is not None if current_export is not None else None
    evidence["page_count_exported"] = exported_slide_count or 0
    repair_items, repair_plan_warning = read_repair_plan_items(target)
    deck_level_blockers = deck_level_repair_blockers(repair_items)
    evidence["deck_level_repair_items"] = deck_level_blockers
    apply_finalize_evidence_to_export_state(
        status,
        readiness,
        evidence,
        current_export_relpath=export_relpath(target, current_export) if current_export is not None else "",
    )
    delivery_contract = apply_delivery_contract_state(status, readiness, evidence)
    evidence = {
        **evidence,
        "delivery_contract": delivery_contract,
        "manual_review_required": delivery_contract["manual_review_required"],
        "delivery_blocked": delivery_contract["delivery_blocked"],
    }
    generation_metadata = generation_metadata_for_status(status)
    status["generation"] = generation_metadata
    status["generation_mode"] = "api_auto"
    recommended_next_action = compute_recommended_next_action(status, readiness, evidence)
    status["workflow_mode"] = workflow_mode
    status["workflow_label"] = workflow_label_value
    status["recommended_next_action"] = recommended_next_action
    save_status(target, status, touch=False)
    return {
        "task_id": str(task_meta.get("id") or ""),
        "task_title": task_title,
        "project_status": status.get("project_status", "project_created"),
        "updated_at": status.get("updated_at", ""),
        "route_id": status.get("route_id", ""),
        "route_label": status.get("route_label", ""),
        "route_policy": status.get("route_policy", {"allowed_actions": [], "forbidden_actions": []}),
        "route_template_mode": status.get("route_template_mode", status.get("template_mode", "free")),
        "route_template_required": bool(status.get("route_template_required", False)),
        "workflow_mode": workflow_mode,
        "workflow_label": workflow_label_value,
        "deck_type": str(status.get("deck_type") or ""),
        "generation_mode": "api_auto",
        "generation": generation_metadata,
        "recommended_next_action": recommended_next_action,
        "template_mode": status.get("template_mode", "free"),
        "template_bound": bool(status.get("template_bound", False)),
        "template_binding_note": status.get("template_binding_note", ""),
        "formal_planning_status": status.get("formal_planning_status", ""),
        "fallback_used": bool(status.get("fallback_used", False)),
        "failed_stage": status.get("failed_stage", ""),
        "failure_message": status.get("failure_message", ""),
        "formal_planning": status.get("formal_planning", {}),
        "slide_count": status["slide_count"],
        "slides": slides,
        "slide_reviews": review_items,
        "export": status.get("export", {}),
        "export_readiness": readiness,
        "last_finalize_mode": evidence["last_finalize_mode"],
        "last_finalize_fresh_qa": evidence["last_finalize_fresh_qa"],
        "last_finalize_cache_hit": evidence["last_finalize_cache_hit"],
        "last_qa_report_path": evidence["last_qa_report_path"],
        "last_contact_sheet_path": evidence["last_contact_sheet_path"],
        "qa_scope": evidence["qa_scope"],
        "checked_slide": evidence["checked_slide"],
        "manual_review_required": status.get("manual_review_required", evidence["manual_review_required"]),
        "delivery_blocked": status.get("delivery_blocked", evidence["delivery_blocked"]),
        "artifact_buildable": status.get("artifact_buildable", False),
        "artifact_created": status.get("artifact_created", False),
        "hard_blockers": status.get("hard_blockers", []),
        "quality_notes": status.get("quality_notes", []),
        "delivery_status": status.get("delivery_status"),
        "delivery_approved": status.get("delivery_approved"),
        "delivery_contract": status.get("delivery_contract", {}),
        "visual_score": evidence.get("visual_score", "not_scored"),
        "visual_score_status": evidence.get("visual_score_status", "missing"),
        "visual_score_reason": evidence.get("visual_score_reason", ""),
        "visual_delivery_ready": visual_delivery_ready(evidence),
        "user_quality": evidence.get("user_quality", {}),
        "planning": (
            evidence.get("user_quality", {}).get("planning", {})
            if isinstance(evidence.get("user_quality"), dict)
            else {}
        ),
        "deck_level_repair_blockers": deck_level_blockers,
        "repair_plan_warning": repair_plan_warning or {},
    }


def project_status_lite(name: str) -> dict:
    target = project_dir(name)
    if not target.exists():
        return build_missing_project_status()
    status = load_status(target)
    if not status:
        status = build_initial_status_from_blueprint(name, target)
    if sync_status_slides_with_blueprint(target, status):
        save_status(target, status)
    readiness = compute_export_readiness(target, status)
    project_state = compute_project_status(status, readiness)
    raw_slides = status.get("slides") if isinstance(status.get("slides"), list) else []
    lite_slides: list[dict[str, Any]] = []
    for slide in raw_slides:
        if not isinstance(slide, dict):
            continue
        lite_slides.append(
            {
                "slide_id": int(slide.get("slide_id") or 0),
                "title": str(slide.get("title") or ""),
                "status": str(slide.get("status") or ""),
                "has_svg": bool(slide.get("has_svg")),
                "qa_status": str(slide.get("qa_status") or ""),
                "qa_status_field": str(slide.get("qa_status_field") or ""),
                "last_error": str(slide.get("last_error") or ""),
                "last_error_code": str(slide.get("last_error_code") or ""),
                "generation_phase": str(slide.get("generation_phase") or ""),
                "block_total": int(slide.get("block_total") or 0),
                "block_completed": int(slide.get("block_completed") or 0),
                "current_block_label": str(slide.get("current_block_label") or ""),
                "generation_started_at": str(slide.get("generation_started_at") or ""),
                "generation_completed_at": str(slide.get("generation_completed_at") or ""),
            }
        )
    export_state = status.get("export") if isinstance(status.get("export"), dict) else {}
    generation = generation_metadata_for_status(status)
    return {
        "project_status": project_state,
        "updated_at": status.get("updated_at", ""),
        "slide_count": len(lite_slides),
        "slides": lite_slides,
        "export": {
            "status": str(export_state.get("status") or ""),
            "ready": bool(export_state.get("ready") or readiness.get("ready")),
            "last_error": str(export_state.get("last_error") or ""),
        },
        "export_readiness": {
            "ready": bool(readiness.get("ready")),
            "status": str(readiness.get("status") or ""),
            "reasons": list(readiness.get("reasons") or [])[:5],
            "missing_slides": list(readiness.get("missing_slides") or [])[:20],
            "qa_failed_slides": list(readiness.get("qa_failed_slides") or [])[:20],
        },
        "generation": {
            "provider": str(generation.get("provider") or ""),
            "model": str(generation.get("model") or ""),
            "configured_provider": str(generation.get("configured_provider") or ""),
            "configured_model": str(generation.get("configured_model") or ""),
            "last_attempted_provider": str(generation.get("last_attempted_provider") or ""),
            "last_attempted_model": str(generation.get("last_attempted_model") or ""),
            "api_key_configured": bool(generation.get("api_key_configured")),
        },
        "generation_mode": "api_auto",
    }


def serve_text(handler: SimpleHTTPRequestHandler, text: str, content_type: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def serve_slide_preview_html(handler: SimpleHTTPRequestHandler, project: str, slide_id: int, svg_path: Path) -> None:
    svg = svg_path.read_text(encoding="utf-8")
    project_attr = html_escape(project, quote=True)
    slide_attr = str(int(slide_id))
    title = html_escape(f"{project} - 第 {slide_id} 页预览")
    body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    html, body {{
      width: 100%;
      height: 100%;
      margin: 0;
      background: #f8fafc;
      overflow: hidden;
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
    }}
    body {{
      display: grid;
      place-items: center;
    }}
    .slide-preview-root {{
      width: min(100vw, calc(100vh * 16 / 9));
      height: min(100vh, calc(100vw * 9 / 16));
      max-width: min(100vw, calc(100vh * 16 / 9));
      max-height: min(100vh, calc(100vw * 9 / 16));
      aspect-ratio: 16 / 9;
      display: grid;
      place-items: center;
      overflow: hidden;
    }}
    .slide-preview-root > svg {{
      display: block;
      width: 100%;
      height: 100%;
    }}
  </style>
</head>
<body data-preview-status="ready" data-project="{project_attr}" data-slide="{slide_attr}">
  <main class="slide-preview-root" aria-label="第 {slide_attr} 页预览">
{svg}
  </main>
</body>
</html>
"""
    serve_text(handler, body, "text/html; charset=utf-8")


_layouts_index_cache: dict[str, Any] | None = None


def load_layouts_index() -> dict[str, Any]:
    """读取 layouts_index.json 并缓存到内存（启动后只读一次）。"""
    global _layouts_index_cache
    if _layouts_index_cache is None:
        with open(LAYOUTS_INDEX_PATH, encoding="utf-8") as handle:
            _layouts_index_cache = json.load(handle)
    return _layouts_index_cache


def build_templates_payload() -> dict[str, Any]:
    """把 layouts_index.json 转换为画廊 API 响应（categories / templates / quick_lookup）。"""
    index = load_layouts_index()
    categories = []
    templates = []
    category_of: dict[str, str] = {}
    for category_id, category in index.get("categories", {}).items():
        layout_ids = list(category.get("layouts", []))
        categories.append(
            {
                "id": str(category_id),
                "label": str(category.get("label") or category_id),
                "template_ids": layout_ids,
            }
        )
        for layout_id in layout_ids:
            category_of.setdefault(str(layout_id), str(category_id))
    for template_id, meta in index.get("layouts", {}).items():
        templates.append(
            {
                "id": str(template_id),
                "label": str(meta.get("label") or template_id),
                "summary": str(meta.get("summary") or ""),
                "tone": str(meta.get("tone") or ""),
                "category": category_of.get(str(template_id), ""),
            }
        )
    return {
        "categories": categories,
        "templates": templates,
        "quick_lookup": index.get("quickLookup", {}),
        "meta": {"total": int(index.get("meta", {}).get("total") or len(templates))},
    }


class WorkbenchHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        request_id = str(getattr(self, "_request_id", "") or "-")
        sys.stderr.write(f"[workbench][{request_id}] " + format % args + "\n")

    def _json_error(
        self,
        status: int,
        *,
        code: str,
        message: str,
        context: dict[str, Any] | None = None,
        data: dict | None = None,
    ) -> None:
        json_response(
            self,
            fail_structured(code, message, data=data, context=context),
            status,
        )

    def _page_event(
        self,
        *,
        project_name: str,
        slide_id: int,
        event_type: str,
        phase: str = "",
        status: str = "",
        started_at: str = "",
        ended_at: str = "",
        duration_ms: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        try:
            store = task_store()
            task = store.get_task_by_project(project_name)
            if not task:
                return
            store.append_page_event(
                str(task["id"]),
                project_name=project_name,
                slide_id=slide_id,
                event_type=event_type,
                phase=phase,
                status=status,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                payload=payload or {},
            )
        except (OSError, ValueError, KeyError):
            return

    def do_GET(self) -> None:
        self._request_id = next_request_id()
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/":
                return self.serve_file(
                    STATIC_DIR / "index.html",
                    "text/html; charset=utf-8",
                    cache_control="no-store, max-age=0",
                )
            if path.startswith("/static/"):
                return self.serve_static(path)
            if path.startswith("/api/workbench/"):
                return self.handle_workbench_get(path)
            if path == "/api/templates":
                return self.handle_list_templates()
            if path == "/api/projects":
                return self.handle_list_projects()
            if path.startswith("/api/projects/"):
                return self.handle_project_get(path, parsed.query)
            self._json_error(404, code="not-found", message="Not found", context={"method": "GET", "path": path})
        except ValueError as exc:
            self._json_error(400, code="invalid-request", message=str(exc), context={"method": "GET", "path": path})
        except OSError as exc:
            self._json_error(500, code="io-error", message=str(exc), context={"method": "GET", "path": path})
        except Exception as exc:
            self._json_error(500, code="internal-error", message=str(exc), context={"method": "GET", "path": path})

    def do_POST(self) -> None:
        self._request_id = next_request_id()
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/api/outline/generate":
                return self.handle_outline_generate()
            if path == "/api/outline/confirm":
                return self.handle_outline_confirm()
            if path == "/api/workbench/tasks":
                return self.handle_create_workbench_task()
            if path.startswith("/api/workbench/"):
                return self.handle_workbench_post(path)
            if path == "/api/projects":
                return self.handle_create_project()
            if path.startswith("/api/projects/"):
                return self.handle_project_post(path)
            self._json_error(404, code="not-found", message="Not found", context={"method": "POST", "path": path})
        except ValueError as exc:
            self._json_error(400, code="invalid-request", message=str(exc), context={"method": "POST", "path": path})
        except OSError as exc:
            self._json_error(500, code="io-error", message=str(exc), context={"method": "POST", "path": path})
        except Exception as exc:
            self._json_error(500, code="internal-error", message=str(exc), context={"method": "POST", "path": path})

    def do_PATCH(self) -> None:
        self._request_id = next_request_id()
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path.startswith("/api/workbench/"):
                return self.handle_workbench_patch(path)
            if path.startswith("/api/projects/"):
                return self.handle_project_patch(path)
            self._json_error(404, code="not-found", message="Not found", context={"method": "PATCH", "path": path})
        except ValueError as exc:
            self._json_error(400, code="invalid-request", message=str(exc), context={"method": "PATCH", "path": path})
        except OSError as exc:
            self._json_error(500, code="io-error", message=str(exc), context={"method": "PATCH", "path": path})
        except Exception as exc:
            self._json_error(500, code="internal-error", message=str(exc), context={"method": "PATCH", "path": path})

    def do_DELETE(self) -> None:
        self._request_id = next_request_id()
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path.startswith("/api/workbench/"):
                return self.handle_workbench_delete(path)
            if path.startswith("/api/projects/"):
                return self.handle_project_delete(path)
            self._json_error(404, code="not-found", message="Not found", context={"method": "DELETE", "path": path})
        except ValueError as exc:
            self._json_error(400, code="invalid-request", message=str(exc), context={"method": "DELETE", "path": path})
        except OSError as exc:
            self._json_error(500, code="io-error", message=str(exc), context={"method": "DELETE", "path": path})
        except Exception as exc:
            self._json_error(500, code="internal-error", message=str(exc), context={"method": "DELETE", "path": path})

    def serve_file(
        self,
        path: Path,
        content_type: str | None = None,
        cache_control: str | None = None,
    ) -> None:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            json_response(self, fail("File not found"), 404)
            return
        body = resolved.read_bytes()
        guessed_type = content_type or mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", guessed_type)
        self.send_header("Content-Length", str(len(body)))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)

    def serve_download(self, path: Path, filename: str, content_type: str) -> None:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            json_response(self, fail("File not found"), 404)
            return
        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, path: str) -> None:
        rel = path.removeprefix("/static/").lstrip("/")
        resolved = (STATIC_DIR / rel).resolve()
        if STATIC_DIR.resolve() not in resolved.parents:
            raise ValueError("Static path escapes static directory.")
        self.serve_file(resolved, cache_control="no-store, max-age=0")

    def handle_list_projects(self) -> None:
        json_response(self, ok("projects", data=collect_workbench_projects(PROJECTS_DIR)))

    def handle_list_templates(self) -> None:
        try:
            payload = build_templates_payload()
        except (OSError, ValueError) as exc:
            json_response(self, fail(f"模板索引读取失败：{exc}"), 500)
            return
        json_response(self, ok("template gallery", data=payload))

    def handle_workbench_get(self, path: str) -> None:
        store = task_store()
        if path == "/api/workbench/session":
            json_response(self, ok("workbench session", data=task_session_payload(store)))
            return
        if path == "/api/workbench/generation-settings":
            json_response(
                self,
                ok(
                    "workbench generation settings",
                    data={"settings": public_generation_settings(GENERATION_SETTINGS_PATH)},
                ),
            )
            return
        if path == "/api/workbench/connections":
            # C08-b：首次拉取连接列表时触发旧体系 settings 的一次性幂等迁移。
            seed_connection_from_settings(CONNECTIONS_PATH, settings_path=GENERATION_SETTINGS_PATH)
            json_response(self, ok("workbench connections", data={"connections": list_connections(CONNECTIONS_PATH)}))
            return
        if path == "/api/workbench/role-routing":
            json_response(self, ok("workbench role routing", data={"roles": load_role_routing(ROLE_ROUTING_PATH)["roles"]}))
            return
        connection_route = self.parse_connection_route(path)
        if connection_route is not None:
            connection_id, action = connection_route
            if action == "models":
                try:
                    result = list_connection_models(CONNECTIONS_PATH, connection_id)
                except KeyError:
                    json_response(self, fail("Connection not found"), 404)
                    return
                json_response(self, ok("workbench connection models", data=result))
                return
            json_response(self, fail("Not found"), 404)
            return
        if path == "/api/workbench/tasks":
            sync_visible_tasks_from_projects(store)
            json_response(self, ok("workbench tasks", data={"tasks": store.list_tasks()}))
            return
        task_route = self.parse_task_route(path)
        if task_route is not None:
            task_id, action = task_route
            task = store.get_task(task_id)
            if not task:
                json_response(self, fail("Task not found"), 404)
                return
            if action == "events":
                json_response(self, ok("workbench task events", data={"events": store.list_events(task_id)}))
                return
            if action == "page-events":
                json_response(self, ok("workbench page events", data={"events": store.list_page_events(task_id)}))
                return
            if action == "slide-reviews":
                json_response(self, ok("workbench slide reviews", data={"reviews": store.list_slide_reviews(task_id)}))
                return
            if action == "":
                data = {"task": task}
                project_name = str(task.get("project_name") or "")
                if project_name:
                    target = project_dir(project_name)
                    if target.exists():
                        project_payload = project_status(project_name)
                        data["project_status"] = project_payload
                        data["task"] = store.sync_task_from_project(task_id, project_payload)
                    else:
                        data["task"] = store.mark_missing_project(task_id)
                json_response(self, ok("workbench task", data=data))
                return
        json_response(self, fail("Not found"), 404)

    def handle_workbench_post(self, path: str) -> None:
        store = task_store()
        if path == "/api/workbench/connections":
            connection = create_connection(CONNECTIONS_PATH, read_json_body(self))
            json_response(self, ok("workbench connection created", data={"connection": connection}))
            return
        connection_route = self.parse_connection_route(path)
        if connection_route is not None:
            connection_id, action = connection_route
            if action == "test":
                try:
                    result = test_connection(CONNECTIONS_PATH, connection_id)
                except KeyError:
                    json_response(self, fail("Connection not found"), 404)
                    return
                json_response(self, ok("workbench connection test finished", data={"result": result}))
                return
            json_response(self, fail("Not found"), 404)
            return
        if path == "/api/workbench/uploads":
            payload = read_json_body(self)
            filename = str(payload.get("filename") or "").strip()
            content_base64 = str(payload.get("content_base64") or "")
            if not filename:
                json_response(self, fail("filename is required"), 400)
                return
            staged = stage_document_upload(filename, content_base64)
            json_response(self, ok("workbench upload staged", data=staged))
            return
        task_route = self.parse_task_route(path)
        if task_route is not None:
            task_id, action = task_route
            if action == "events":
                task = store.get_task(task_id)
                if not task:
                    json_response(self, fail("Task not found"), 404)
                    return
                payload = read_json_body(self)
                event_type = str(payload.get("event_type") or "").strip()
                if not re.match(r"^[a-z][a-z0-9_]{1,64}$", event_type):
                    json_response(self, fail("Invalid event_type"), 400)
                    return
                event_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
                event = store.append_event(task_id, event_type, event_payload)
                json_response(self, ok("workbench task event created", data={"event": event}))
                return
            if action == "activate":
                session = store.activate_task(task_id)
                json_response(self, ok("task activated", data={"session": session, "task": store.get_task(task_id)}))
                return
            if action == "archive":
                task = store.get_task(task_id)
                if not task:
                    json_response(self, fail("Task not found"), 404)
                    return
                now = datetime.now().isoformat(timespec="seconds")
                with store.connect() as conn:
                    conn.execute(
                        "UPDATE workbench_tasks SET status='archived', archived_at=?, updated_at=? WHERE id=?",
                        (now, now, task_id),
                    )
                    conn.commit()
                json_response(self, ok("task archived", data={"task": store.get_task(task_id)}))
                return
            if action == "delete":
                try:
                    result = delete_workbench_task_and_project(store, task_id)
                except FileNotFoundError:
                    json_response(self, fail("Task not found"), 404)
                    return
                json_response(self, ok("task deleted", data=result))
                return
            if action == "sync":
                task = store.get_task(task_id)
                if not task:
                    json_response(self, fail("Task not found"), 404)
                    return
                project_name = str(task.get("project_name") or "")
                if not project_name or not project_dir(project_name).exists():
                    json_response(self, ok("task synced", data={"task": store.mark_missing_project(task_id)}))
                    return
                project_payload = project_status(project_name)
                synced = store.sync_task_from_project(task_id, project_payload)
                json_response(self, ok("task synced", data={"task": synced, "project_status": project_payload}))
                return
        json_response(self, fail("Not found"), 404)

    def handle_workbench_patch(self, path: str) -> None:
        if path == "/api/workbench/generation-settings":
            settings = update_generation_settings(read_json_body(self), GENERATION_SETTINGS_PATH)
            json_response(self, ok("workbench generation settings updated", data={"settings": settings}))
            return
        if path == "/api/workbench/role-routing":
            body = read_json_body(self)
            data = update_role_routing(ROLE_ROUTING_PATH, body.get("roles"), connections_path=CONNECTIONS_PATH)
            json_response(self, ok("workbench role routing updated", data={"roles": data["roles"]}))
            return
        connection_route = self.parse_connection_route(path)
        if connection_route is not None:
            connection_id, action = connection_route
            if action:
                json_response(self, fail("Not found"), 404)
                return
            try:
                connection = update_connection(CONNECTIONS_PATH, connection_id, read_json_body(self))
            except KeyError:
                json_response(self, fail("Connection not found"), 404)
                return
            json_response(self, ok("workbench connection updated", data={"connection": connection}))
            return
        if path != "/api/workbench/session":
            json_response(self, fail("Not found"), 404)
            return
        payload = read_json_body(self)
        store = task_store()
        session = store.update_session(
            current_view=payload.get("current_view") if "current_view" in payload else None,
            current_task_id=str(payload.get("current_task_id") or "") if "current_task_id" in payload else None,
            selected_workflow_mode=payload.get("selected_workflow_mode")
            if "selected_workflow_mode" in payload
            else None,
        )
        json_response(self, ok("workbench session updated", data={"session": session}))

    def handle_project_patch(self, path: str) -> None:
        slide_route = self.parse_slide_route(path)
        if slide_route is None:
            json_response(self, fail("Not found"), 404)
            return
        name, slide_id, action = slide_route
        if action != "draft":
            json_response(self, fail("Not found"), 404)
            return
        payload = read_json_body(self)
        target = project_dir(name)
        previous_status = load_status(target) or build_initial_status_from_blueprint(name, target)
        previous_slide = next(
            (item for item in previous_status.get("slides", []) if int(item.get("slide_id") or 0) == slide_id),
            None,
        )
        previous_slide = dict(previous_slide) if isinstance(previous_slide, dict) else {}
        page_type = str(payload.get("page_type") or previous_slide.get("page_type") or "content")
        content_handling = normalize_content_handling(
            payload.get("content_handling") if "content_handling" in payload else previous_slide.get("content_handling")
        )
        page_style = normalize_page_style(
            payload.get("page_style") if "page_style" in payload else previous_slide.get("page_style")
        )
        title = str(payload.get("title") if "title" in payload else previous_slide.get("title") or "")
        prompt = normalize_submission_prompt(
            str(payload.get("prompt") if "prompt" in payload else previous_slide.get("prompt") or "")
        )
        status, _ = update_page_authoring_evidence(
            target,
            slide_id,
            page_type=page_type,
            title=title,
            prompt=prompt,
            content_handling=content_handling,
            page_style=page_style,
        )
        status_item = next(
            (item for item in status.get("slides", []) if int(item.get("slide_id") or 0) == slide_id),
            None,
        )
        if isinstance(status_item, dict) and previous_slide:
            for key, value in previous_slide.items():
                if key in {"title", "page_type", "content_handling", "page_style", "prompt"}:
                    continue
                status_item[key] = value
        add_event(status, "slide_draft_saved", f"Draft saved for slide {slide_id}.")
        save_status(target, status)
        json_response(
            self,
            ok(
                "slide draft saved",
                project=name,
                data={
                    "slide_id": slide_id,
                    "page_type": page_type,
                    "content_handling": content_handling,
                    "page_style": page_style,
                    "title": title,
                    "prompt": prompt,
                },
            ),
        )

    def handle_outline_generate(self) -> None:
        """C13-A：只生成大纲（plan_rough_deck_content），不创建项目。"""
        payload = read_json_body(self)
        temporary_workspace: Path | None = None
        planning_payload = payload
        try:
            if _is_document_outline_request(payload):
                planning_payload, temporary_workspace = _prepare_temporary_outline_document_context(payload)
            content_plan = _plan_outline_content(planning_payload)
        finally:
            if temporary_workspace is not None:
                _remove_temporary_outline_workspace(temporary_workspace)
        if content_plan.get("status") != "used":
            json_response(
                self,
                fail(content_plan.get("reason") or "大纲生成失败"),
                422,
            )
            return
        slides = content_plan.get("slides") or []
        json_response(
            self,
            ok(
                "outline generated",
                data={
                    "deck_thesis": content_plan.get("deck_thesis") or "",
                    "slides": slides,
                    "page_count": len(slides),
                },
            ),
        )

    def handle_outline_confirm(self) -> None:
        """C13-A：接收确认/修改后的大纲，创建项目并启动生成。

        claim_boundary 为后端校验字段：沿用生成结果原值，前端不可修改。
        """
        payload = read_json_body(self)
        store = task_store()
        raw_slides = payload.get("slides")
        if not isinstance(raw_slides, list) or not raw_slides:
            raise ValueError("slides must be a non-empty list")
        normalized_slides: list[dict] = []
        for index, raw_slide in enumerate(raw_slides, start=1):
            if not isinstance(raw_slide, dict):
                raise ValueError(f"slides[{index}] must be an object")
            title = str(raw_slide.get("title") or "").strip()
            if not title:
                raise ValueError(f"slides[{index}].title must be non-empty")
            body = str(raw_slide.get("body") or "").strip()
            if not body:
                body = str(raw_slide.get("prompt") or "").strip()
            if not body:
                raise ValueError(f"slides[{index}].body must be non-empty")
            slide: dict = {
                "id": index,
                "title": title,
                "body": body,
                "prompt": str(raw_slide.get("prompt") or body),
            }
            for key in ("narrative_intent", "visual_intent"):
                value = str(raw_slide.get(key) or "").strip()
                if value:
                    slide[key] = value
            for key in ("claims", "acceptance_criteria", "source_refs"):
                value = raw_slide.get(key)
                if isinstance(value, list) and all(isinstance(item, str) for item in value):
                    slide[key] = [item for item in value if item.strip()]
            claim_boundary = str(raw_slide.get("claim_boundary") or "").strip()
            if claim_boundary:
                slide["claim_boundary"] = claim_boundary
            content = raw_slide.get("content")
            if isinstance(content, dict):
                slide["content"] = {
                    str(key): str(value or "").strip()
                    for key, value in content.items()
                    if str(value or "").strip()
                }
            normalized_slides.append(slide)
        deck_thesis = str(payload.get("deck_thesis") or "").strip()
        raw_prompt = str(payload.get("raw_prompt") or payload.get("prompt") or "")
        clean_prompt = normalize_submission_prompt(raw_prompt)
        if not clean_prompt:
            clean_prompt = str(normalized_slides[0].get("title") or "")
        payload["raw_prompt"] = raw_prompt or clean_prompt
        payload["prompt"] = clean_prompt
        payload["page_count"] = len(normalized_slides)
        document_context = None
        if _is_document_outline_request(payload):
            document_context = _tw_prepare_document_sources(payload)
            if document_context is None:
                raise ValueError("Document outline confirmation requires prepared source materials.")
            payload["project_name"] = str(document_context["project_name"])
        task_kwargs: dict[str, Any] = {
            "content_plan": {
                "status": "used",
                "deck_thesis": deck_thesis,
                "slides": normalized_slides,
                "reason": "",
            }
        }
        if document_context is not None:
            task_kwargs["document_context"] = document_context
        data = _tw_create_workbench_task(payload, **task_kwargs)
        title = make_user_task_title(clean_prompt, str(data.get("project") or "新建 PPT 任务"))
        task = store.create_task(
            workflow_mode=str(payload.get("workflow_mode") or data.get("workflow_mode") or "prompt_deck"),
            title=title,
            user_prompt=clean_prompt,
            project_name=str(data.get("project") or ""),
            slide_count=int(data.get("page_count") or len(normalized_slides) or 0),
        )
        store.activate_task(str(task["id"]))
        data["task_id"] = task["id"]
        data["task_title"] = title
        json_response(self, ok("outline confirmed, task created", project=data["project"], data=data))

    def handle_create_workbench_task(self) -> None:
        payload = read_json_body(self)
        store = task_store()
        raw_prompt = str(payload.get("prompt") or "")
        clean_prompt = normalize_submission_prompt(raw_prompt)
        payload["raw_prompt"] = raw_prompt
        payload["prompt"] = clean_prompt
        data = create_workbench_task(payload)
        title = make_user_task_title(clean_prompt, str(data.get("project") or "新建 PPT 任务"))
        task = store.create_task(
            workflow_mode=str(payload.get("workflow_mode") or data.get("workflow_mode") or "prompt_deck"),
            title=title,
            user_prompt=clean_prompt,
            project_name=str(data.get("project") or ""),
            slide_count=int(data.get("page_count") or payload.get("page_count") or 0),
        )
        store.activate_task(str(task["id"]))
        data["task_id"] = task["id"]
        data["task_title"] = title
        json_response(self, ok("codex task created", project=data["project"], data=data))

    def handle_project_get(self, path: str, query: str = "") -> None:
        slide_route = self.parse_slide_route(path)
        if slide_route is not None:
            name, slide_id, action = slide_route
            target = project_dir(name)
            if action == "svg":
                svg = slide_path(target, slide_id, "svg_output")
                if not svg.exists():
                    svg = slide_path(target, slide_id, "svg_final")
                if not svg.exists():
                    json_response(self, fail("SVG not found"), 404)
                    return
                record_page_event_for_project(
                    name,
                    slide_id,
                    "slide_preview_served",
                    phase="preview",
                    status="ok",
                    payload={"source": "slide_svg_route", "bytes": svg.stat().st_size},
                )
                self.serve_file(svg, "image/svg+xml; charset=utf-8")
                return
            if action == "preview":
                svg = slide_path(target, slide_id, "svg_output")
                if not svg.exists():
                    svg = slide_path(target, slide_id, "svg_final")
                if not svg.exists():
                    json_response(self, fail("SVG not found"), 404)
                    return
                record_page_event_for_project(
                    name,
                    slide_id,
                    "slide_preview_served",
                    phase="preview",
                    status="ok",
                    payload={"source": "slide_html_preview_route", "bytes": svg.stat().st_size},
                )
                serve_slide_preview_html(self, name, slide_id, svg)
                return
            if action == "task":
                task = target / "agent_tasks" / f"slide_{slide_id:02d}.md"
                if not task.exists():
                    json_response(self, fail("Slide task not found"), 404)
                    return
                serve_text(self, task.read_text(encoding="utf-8"), "text/markdown; charset=utf-8")
                return
            if action == "revisions":
                revisions = list_slide_revisions(target, slide_id)
                json_response(self, ok("slide revisions", name, {"slide_id": slide_id, "revisions": revisions}))
                return
            if action == "review":
                store = task_store()
                task = store.get_task_by_project(name)
                if not task:
                    json_response(
                        self,
                        ok("slide review", name, {"slide_id": slide_id, "review": {}}),
                    )
                    return
                review = store.get_slide_review(str(task.get("id") or ""), slide_id)
                json_response(self, ok("slide review", name, {"slide_id": slide_id, "review": review}))
                return
            if action == "export-pptx":
                export = single_slide_export_path(target, slide_id)
                if export is None or not export.exists():
                    promoted = promote_single_slide_work_output(target, slide_id)
                    if promoted is not None:
                        export = promoted
                if export is None or not export.exists():
                    json_response(self, fail("Single-slide PPTX not generated yet."), 404)
                    return
                self.serve_download(
                    export,
                    f"{name}-slide-{slide_id:02d}.pptx",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
                return
            json_response(self, fail("Not found"), 404)
            return

        name, action = self.parse_project_route(path)
        target = project_dir(name)
        if action == "status":
            json_response(self, ok("status", project=name, data=project_status(name)))
            return
        if action == "status-lite":
            json_response(self, ok("status lite", project=name, data=project_status_lite(name)))
            return
        if action == "export-readiness":
            status = load_status(target)
            if not status:
                status = build_initial_status_from_blueprint(name, target)
            readiness = compute_export_readiness_full(name, target, status)
            json_response(self, ok("export readiness", name, readiness))
            return
        if action == "svg":
            params = parse_qs(query)
            slide_id = int(params.get("slide", ["1"])[0])
            svg = slide_path(target, slide_id, "svg_output")
            if not svg.exists():
                svg = slide_path(target, slide_id, "svg_final")
            if not svg.exists():
                json_response(self, fail("SVG not found"), 404)
                return
            record_page_event_for_project(
                name,
                slide_id,
                "slide_preview_served",
                phase="preview",
                status="ok",
                payload={"source": "project_svg_route", "bytes": svg.stat().st_size},
            )
            self.serve_file(svg, "image/svg+xml; charset=utf-8")
            return
        if action == "agent-task":
            task = target / "agent_task.md"
            if not task.exists():
                json_response(self, fail("agent_task.md not found"), 404)
                return
            serve_text(self, task.read_text(encoding="utf-8"), "text/markdown; charset=utf-8")
            return
        if action == "qa-report":
            report = target / "qa" / "report.md"
            if not report.exists():
                json_response(
                    self,
                    ok(
                        "qa report",
                        name,
                        {
                            "exists": False,
                            "path": "qa/report.md",
                            "content": "",
                        },
                    ),
                )
                return
            content = report.read_text(encoding="utf-8")
            json_response(
                self,
                ok(
                    "qa report",
                    name,
                    {
                        "exists": True,
                        "path": "qa/report.md",
                        "content": content[-12000:],
                    },
                ),
            )
            return
        if action == "qa-contact-sheet":
            contact_sheet = target / "qa" / "contact-sheet.png"
            if not contact_sheet.exists():
                json_response(self, fail("QA contact sheet not found"), 404)
                return
            self.serve_file(contact_sheet, "image/png")
            return
        if action == "export-pptx":
            export_file = exported_pptx_path(target, require_current=True)
            if export_file is None:
                stale_export = exported_pptx_path(target)
                if stale_export:
                    json_response(self, fail("PPTX is stale. Please regenerate the PPT file before downloading."), 409)
                    return
                json_response(self, fail("PPTX not generated yet. Please generate the PPT file first."), 404)
                return
            delivery = project_status(name)
            if delivery.get("delivery_approved") is not True:
                blockers = [str(item) for item in delivery.get("hard_blockers") or []]
                if "invalid-pptx" in blockers or delivery.get("artifact_created") is not True:
                    message = "PPTX is invalid or incomplete. Please regenerate the PPT file before downloading."
                else:
                    message = "PPTX download is blocked by the current delivery checks."
                json_response(self, fail(message), 409)
                return
            self.serve_download(
                export_file,
                f"{name}.pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
            return
        json_response(self, fail("Not found"), 404)

    def handle_create_project(self) -> None:
        payload = read_json_body(self)
        name = validate_project_name(str(payload.get("project_name", "")))
        data = write_project_files(name, payload)
        message = "created"
        if data["style_route"]["returncode"] != 0:
            message = "created with style route warnings"
        json_response(self, ok(message, project=name, data=data))

    def handle_project_post(self, path: str) -> None:
        slide_route = self.parse_slide_route(path)
        if slide_route is not None:
            name, slide_id, action = slide_route
            if action == "qa":
                handle_slide_qa(self, name, slide_id)
                return
            if action == "auto-generate":
                payload = read_json_body(self)
                handle_slide_auto_generate(self, name, slide_id, payload)
                return
            if action == "export-pptx":
                handle_slide_export_pptx(self, name, slide_id)
                return
            if action == "budget-repair-task":
                handle_slide_budget_repair(self, name, slide_id)
                return
            if action == "executor-packet":
                payload = read_json_body(self)
                handle_slide_executor_packet(self, name, slide_id, payload)
                return
            if action == "insert-after":
                target = project_dir(name)
                payload = read_json_body(self)
                status = load_status(target) or build_initial_status_from_blueprint(name, target)
                if is_true_single_page_workflow(status):
                    json_response(self, fail("单页任务只能保留 1 页。需要多页 PPT 时，请新建多页任务。"), 409)
                    return
                result = insert_slide_after_project(
                    target,
                    slide_id,
                    page_type=str(payload.get("page_type") or "content"),
                    title=str(payload.get("title") or ""),
                    prompt=str(payload.get("prompt") or ""),
                    content_handling=str(payload.get("content_handling") or ""),
                    page_style=str(payload.get("page_style") or ""),
                )
                json_response(self, ok("slide inserted", project=name, data=result))
                return
            if action == "restore-revision":
                payload = read_json_body(self)
                handle_slide_restore_revision(self, name, slide_id, payload)
                return
            if action == "placeholder-svg":
                handle_slide_placeholder_svg(self, name, slide_id)
                return
            if action == "review":
                payload = read_json_body(self)
                store = task_store()
                task = store.get_task_by_project(name)
                if not task:
                    json_response(self, fail("Task not found for project review"), 404)
                    return
                review = store.upsert_slide_review(
                    str(task.get("id") or ""),
                    project_name=name,
                    slide_id=slide_id,
                    score=payload.get("score"),
                    usable_for_next_edit=payload.get("usable_for_next_edit"),
                    pptx_editable=payload.get("pptx_editable"),
                    issue_tags=payload.get("issue_tags") if isinstance(payload.get("issue_tags"), list) else [],
                    notes=str(payload.get("notes") or ""),
                )
                record_page_event_for_project(
                    name,
                    slide_id,
                    "manual_review_submitted",
                    phase="manual_review",
                    status="ok",
                    started_at=iso_now(),
                    payload={
                        "score": review.get("score"),
                        "usable_for_next_edit": review.get("usable_for_next_edit"),
                        "pptx_editable": review.get("pptx_editable"),
                        "issue_tags": review.get("issue_tags") or [],
                    },
                )
                if review.get("pptx_editable") is not None:
                    record_page_event_for_project(
                        name,
                        slide_id,
                        "pptx_editability_checked",
                        phase="manual_review",
                        status="ok",
                        started_at=iso_now(),
                        payload={"pptx_editable": bool(review.get("pptx_editable"))},
                    )
                json_response(self, ok("slide review saved", project=name, data={"slide_id": slide_id, "review": review}))
                return
            json_response(self, fail("Not found"), 404)
            return

        name, action = self.parse_project_route(path)
        if action == "slides":
            target = project_dir(name)
            payload = read_json_body(self)
            status = load_status(target) or build_initial_status_from_blueprint(name, target)
            if is_true_single_page_workflow(status):
                json_response(self, fail("单页任务只能保留 1 页。需要多页 PPT 时，请新建多页任务。"), 409)
                return
            result = append_slide_to_project(
                target,
                page_type=str(payload.get("page_type") or "content"),
                title=str(payload.get("title") or ""),
                prompt=str(payload.get("prompt") or ""),
                content_handling=str(payload.get("content_handling") or ""),
                page_style=str(payload.get("page_style") or ""),
            )
            json_response(self, ok("slide appended", project=name, data=result))
            return
        if action == "placeholder-svg":
            handle_project_placeholder_svg(self, name)
            return
        if action == "auto-generate":
            target = project_dir(name)
            status = load_status(target) or build_initial_status_from_blueprint(name, target)
            status["generation_mode"] = "api_auto"
            save_status(target, status)
            slides = status.get("slides") if isinstance(status.get("slides"), list) else []
            event_slide_ids = [
                int(slide.get("slide_id") or 0)
                for slide in slides
                if isinstance(slide, dict)
                and int(slide.get("slide_id") or 0) > 0
                and not slide.get("has_svg")
            ]
            generation_started_at = iso_now()
            generation_started_perf = time.perf_counter()
            for event_slide_id in event_slide_ids:
                record_page_event_for_project(
                    name,
                    event_slide_id,
                    "slide_generate_requested",
                    phase="generation",
                    status="queued",
                    started_at=generation_started_at,
                    payload={"source": "project_auto_generate"},
                )
                record_page_event_for_project(
                    name,
                    event_slide_id,
                    "slide_generate_started",
                    phase="generation",
                    status="running",
                    started_at=generation_started_at,
                    payload={"source": "project_auto_generate"},
                )
            try:
                result = auto_generate_project(name, project_dir(name), config=resolve_role_generation_config("svg_generation"))
            except ValueError as exc:
                message = str(exc)
                if "API key is not configured" in message:
                    safe_message = sanitize_generation_error_message(message)
                    for event_slide_id in event_slide_ids:
                        record_page_event_for_project(
                            name,
                            event_slide_id,
                            "slide_generate_failed",
                            phase="generation",
                            status="error",
                            started_at=generation_started_at,
                            ended_at=iso_now(),
                            duration_ms=elapsed_ms(generation_started_perf),
                            payload={
                                "source": "project_auto_generate",
                                "reason_code": "api_key_missing",
                                "error": safe_message,
                            },
                        )
                    self._json_error(
                        409,
                        code="real_generation_unavailable",
                        message="Real generation unavailable. Configure API key. Placeholder is dry-run only.",
                        context={"project": name, "reason_code": "api_key_missing"},
                        data={
                            "provider_message": safe_message,
                            "recommended_action": "configure API key",
                            "placeholder_policy": "placeholder is dry-run only",
                        },
                    )
                    return
                raise
            generated_slides = {int(item) for item in result.get("generated_slides", [])}
            skipped_slides = {int(item) for item in result.get("skipped_slides", [])}
            failed_slides = {int(item) for item in result.get("failed_slides", [])}
            for event_slide_id in sorted(generated_slides):
                record_page_event_for_project(
                    name,
                    event_slide_id,
                    "slide_generate_completed",
                    phase="generation",
                    status="ok",
                    started_at=generation_started_at,
                    ended_at=iso_now(),
                    duration_ms=elapsed_ms(generation_started_perf),
                    payload={"source": "project_auto_generate", "generated_count": result.get("generated_count")},
                )
            for event_slide_id in sorted(skipped_slides):
                record_page_event_for_project(
                    name,
                    event_slide_id,
                    "slide_generate_skipped",
                    phase="generation",
                    status="skipped",
                    started_at=generation_started_at,
                    ended_at=iso_now(),
                    duration_ms=elapsed_ms(generation_started_perf),
                    payload={"source": "project_auto_generate", "reason_code": "prompt_missing"},
                )
            for event_slide_id in sorted(failed_slides):
                record_page_event_for_project(
                    name,
                    event_slide_id,
                    "slide_generate_failed",
                    phase="generation",
                    status="error",
                    started_at=generation_started_at,
                    ended_at=iso_now(),
                    duration_ms=elapsed_ms(generation_started_perf),
                    payload={"source": "project_auto_generate", "reason_code": "generation_failed"},
                )
            json_response(self, ok("auto generation completed", project=name, data=result))
            return
        if action == "qa":
            qa = run_slide_qa(SlideQaRequest(project=name, slide_id=1, snapshots=True))
            result = {
                "returncode": qa.returncode,
                "stdout": qa.stdout,
                "stderr": qa.stderr,
                "summary": qa.summary,
                "report_path": qa.report_path,
            }
            json_response(self, ok("qa completed" if qa.ok else "qa failed", project=name, data=result))
            return
        if action == "finalize":
            payload = read_json_body(self)
            handle_project_finalize(self, name, payload)
            return
        if action == "budget-repair-task":
            handle_project_budget_repair(self, name)
            return
        json_response(self, fail("Not found"), 404)

    def handle_connection_delete(self, connection_id: str) -> None:
        # 物理删除前先拦住被角色路由引用的连接，避免路由指向不存在的连接后静默失败。
        role_labels = {
            "content_planning": "内容规划",
            "svg_generation": "SVG 页面生成",
            "page_regeneration": "页面重新生成",
        }
        routing = load_role_routing(ROLE_ROUTING_PATH)
        referenced = [
            role_labels.get(role, role)
            for role, entry in routing["roles"].items()
            if str(entry.get("connection_id") or "") == connection_id
        ]
        if referenced:
            self._json_error(
                409,
                code="connection_in_use",
                message=f"该连接正被角色路由使用（{'、'.join(referenced)}），请先在角色路由中改用其他连接再删除。",
                context={"connection_id": connection_id, "referenced_roles": referenced},
            )
            return
        try:
            removed = delete_connection(CONNECTIONS_PATH, connection_id)
        except KeyError:
            json_response(self, fail("Connection not found"), 404)
            return
        json_response(self, ok("workbench connection deleted", data={"connection": removed}))

    def handle_workbench_delete(self, path: str) -> None:
        connection_route = self.parse_connection_route(path)
        if connection_route is not None:
            connection_id, action = connection_route
            if action:
                json_response(self, fail("Not found"), 404)
                return
            self.handle_connection_delete(connection_id)
            return
        task_route = self.parse_task_route(path)
        if task_route is None:
            json_response(self, fail("Not found"), 404)
            return
        task_id, action = task_route
        if action:
            json_response(self, fail("Not found"), 404)
            return
        store = task_store()
        task = store.get_task(task_id)
        if task:
            project_name = str(task.get("project_name") or "").strip()
            if project_name:
                clean_project = validate_project_name(project_name)
                target = (PROJECTS_DIR / clean_project).resolve()
                if target.exists():
                    busy = task_purge_busy_context(load_status(target))
                    if busy:
                        self._json_error(
                            409,
                            code="task_purge_blocked",
                            message="Task generation, QA or export is running. Please retry purge after it completes.",
                            context={"task_id": task_id, "project": clean_project, **busy},
                            data={"task_id": task_id, **busy},
                        )
                        return
        result = purge_workbench_task_and_project(store, task_id)
        json_response(self, ok("task purged", data=result))

    def handle_project_delete(self, path: str) -> None:
        slide_route = self.parse_slide_route(path)
        if slide_route is None:
            json_response(self, fail("Not found"), 404)
            return
        name, slide_id, action = slide_route
        if action:
            json_response(self, fail("Not found"), 404)
            return
        target = project_dir(name)
        status = load_status(target) or {}
        status_slides = status.get("slides") if isinstance(status, dict) else None
        if isinstance(status_slides, list):
            target_slide = next((item for item in status_slides if int(item.get("slide_id") or 0) == int(slide_id)), None)
            if isinstance(target_slide, dict) and slide_is_busy_for_delete(target_slide):
                if slide_is_stale_for_delete(target_slide, status):
                    age_sec = slide_delete_lock_age_seconds(target_slide, status) or 0.0
                    has_svg = bool(target_slide.get("has_svg"))
                    target_slide["status"] = "svg_ready" if has_svg else "waiting_codex"
                    target_slide["qa_status"] = "not_run"
                    target_slide["last_error"] = ""
                    target_slide["lock_updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
                    add_event(
                        status,
                        "slide_delete_stale_unlock",
                        f"Slide {slide_id} stale lock auto-unlocked before delete (age={age_sec:.1f}s).",
                    )
                    save_status(target, status)
                else:
                    self._json_error(
                        409,
                        code="slide_delete_blocked",
                        message="Target slide generation or QA is running. Please retry delete after it completes.",
                        context={
                            "project": name,
                            "slide_id": slide_id,
                            "busy_slide_id": int(target_slide.get("slide_id") or 0),
                            "busy_status": str(target_slide.get("status") or ""),
                            "busy_qa_status": str(target_slide.get("qa_status") or ""),
                        },
                        data={
                            "slide_id": slide_id,
                            "busy_slide_id": int(target_slide.get("slide_id") or 0),
                            "busy_status": str(target_slide.get("status") or ""),
                            "busy_qa_status": str(target_slide.get("qa_status") or ""),
                        },
                    )
                    return
        result = delete_slide_from_project(target, slide_id)
        json_response(self, ok("slide deleted", project=name, data=result))

    def parse_project_route(self, path: str) -> tuple[str, str]:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 4 or parts[0] != "api" or parts[1] != "projects":
            raise ValueError("Invalid project endpoint.")
        return validate_project_name(parts[2]), parts[3]

    def parse_task_route(self, path: str) -> tuple[str, str] | None:
        parts = [part for part in path.split("/") if part]
        if len(parts) < 4 or parts[0] != "api" or parts[1] != "workbench" or parts[2] != "tasks":
            return None
        task_id = str(parts[3] or "").strip()
        if not re.match(r"^[A-Za-z0-9_-]{1,96}$", task_id):
            raise ValueError("Invalid task id.")
        action = str(parts[4] or "") if len(parts) > 4 else ""
        if len(parts) > 5:
            raise ValueError("Invalid task endpoint.")
        return task_id, action

    def parse_connection_route(self, path: str) -> tuple[str, str] | None:
        parts = [part for part in path.split("/") if part]
        if len(parts) < 4 or parts[0] != "api" or parts[1] != "workbench" or parts[2] != "connections":
            return None
        connection_id = str(parts[3] or "").strip()
        if not re.match(r"^[A-Za-z0-9_-]{1,96}$", connection_id):
            raise ValueError("Invalid connection id.")
        action = str(parts[4] or "") if len(parts) > 4 else ""
        if len(parts) > 5:
            raise ValueError("Invalid connection endpoint.")
        return connection_id, action

    def parse_slide_route(self, path: str) -> tuple[str, int, str] | None:
        parts = [part for part in path.split("/") if part]
        if len(parts) not in {5, 6} or parts[0] != "api" or parts[1] != "projects" or parts[3] != "slides":
            return None
        name = validate_project_name(parts[2])
        try:
            slide_id = int(parts[4])
        except ValueError as exc:
            raise ValueError("slide id must be a number.") from exc
        if slide_id < 1 or slide_id > 99:
            raise ValueError("slide id must be between 1 and 99.")
        return name, slide_id, parts[5] if len(parts) == 6 else ""

# Configure extracted modules with server context.
set_integrations_context(
    SKILL_DIR=SKILL_DIR,
    TEMPLATE_MODES=TEMPLATE_MODES,
    compute_export_readiness=compute_export_readiness,
)
set_project_writer_context(
    require_non_empty=require_non_empty,
    project_dir=project_dir,
    SCENES=SCENES,
    STYLE_PROFILES=STYLE_PROFILES,
    GENERATION_MODES=GENERATION_MODES,
    TEMPLATE_MODES=TEMPLATE_MODES,
    SCENE_MAP=SCENE_MAP,
    STYLE_MAP=STYLE_MAP,
    template_binding_status=template_binding_status,
    resolve_route=resolve_route,
    resolve_template_instruction=resolve_template_instruction,
    write_text=write_text,
    write_json=write_json,
    run_skill_command=run_skill_command,
    create_agent_task=create_agent_task,
    create_slide_task=create_slide_task,
)
set_task_writer_context(
    require_non_empty=require_non_empty,
    require_choice=require_choice,
    page_count_from_payload=page_count_from_payload,
    validate_project_name=validate_project_name,
    build_project_name=build_project_name,
    project_dir=project_dir,
    DECK_TYPES=DECK_TYPES,
    SCENES=SCENES,
    STYLE_PROFILES=STYLE_PROFILES,
    TEMPLATE_MODES=TEMPLATE_MODES,
    template_binding_status=template_binding_status,
    bind_template_to_project=bind_template_to_project,
    template_layouts_dir=SKILL_DIR / "ppt-ai-core" / "templates" / "layouts",
    resolve_route=resolve_route,
    split_prompt=split_prompt,
    write_project_files=write_project_files,
    write_json=write_json,
    run_skill_command=run_skill_command,
    run_document_intake=run_document_intake,
)

def main() -> None:
    host, port = resolve_server_address()
    server = ThreadingHTTPServer((host, port), WorkbenchHandler)
    pid_path_value = str(os.environ.get("WORKBENCH_PID_FILE") or "").strip()
    pid_path = Path(pid_path_value).resolve() if pid_path_value else None
    if pid_path is not None:
        write_server_pid_file(pid_path, os.getpid())
    print(f"Single Page PPT Workbench listening on {host}:{port}")
    print(f"Local access: http://localhost:{port}")
    if host == "0.0.0.0":
        print(f"LAN access: http://<this-computer-private-ip>:{port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if pid_path is not None:
            remove_server_pid_file(pid_path, os.getpid())


if __name__ == "__main__":
    main()
