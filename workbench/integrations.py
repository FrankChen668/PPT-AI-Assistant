from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

_CTX: dict = {}

SKILL_DIR: Path = Path(__file__).resolve().parents[1] / "my-ppt-skill"
TEMPLATE_MODES: dict[str, dict[str, str]] = {
    "free": {"instruction": "No fixed template is selected."},
    "strict_template": {"instruction": "Follow the bound template strictly."},
}


def _default_compute_export_readiness(target: Path, status: dict) -> dict[str, Any]:
    del target, status
    return {
        "ready": False,
        "status": "not_ready",
        "reasons": ["compute_export_readiness is not configured."],
        "missing_slides": [],
        "qa_failed_slides": [],
    }


compute_export_readiness: Callable[[Path, dict], dict[str, Any]] = _default_compute_export_readiness

def set_context(**kwargs) -> None:
    _CTX.update(kwargs)
    globals().update(kwargs)

def run_skill_command(args: list[str]) -> dict:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=SKILL_DIR,
        text=True,
        capture_output=True,
        timeout=120,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-8000:],
        "stderr": completed.stderr[-8000:],
    }

def template_binding_status(target: Path) -> dict:
    binding_path = target / "template_binding.json"
    layout_ref_dir = target / "templates" / "layout_ref"
    binding_exists = binding_path.exists()
    layout_ref_exists = layout_ref_dir.exists() and any(path.is_dir() for path in layout_ref_dir.iterdir())
    template_id = ""
    if binding_exists:
        try:
            payload = json.loads(binding_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                template_id = str(payload.get("template_id") or payload.get("layout_id") or "").strip()
        except Exception:
            template_id = ""
    bound = binding_exists and layout_ref_exists
    if bound:
        note = (
            f"Template is bound ({template_id})."
            if template_id
            else "Template is bound (template_binding.json + templates/layout_ref)."
        )
    else:
        note = "No concrete template is bound yet."
    return {
        "bound": bound,
        "binding_exists": binding_exists,
        "layout_ref_exists": layout_ref_exists,
        "template_id": template_id,
        "note": note,
    }

def resolve_template_instruction(template_mode: str, binding: dict) -> str:
    if template_mode == "reference":
        if binding.get("bound"):
            template_id = binding.get("template_id")
            if template_id:
                return f"Use template reference strictly from template_binding.json ({template_id}) and templates/layout_ref/{template_id}/."
            return "Use template reference strictly from template_binding.json and templates/layout_ref/."
        return "No concrete template is bound now. Explicitly state this and use a compatible free layout."
    if template_mode == "reuse":
        return (
            "Reuse the existing project's visual language from design_spec.md and existing svg_output pages. "
            "Keep typography scale, spacing rhythm, and color tokens consistent."
        )
    if template_mode == "strict_template":
        return TEMPLATE_MODES["strict_template"]["instruction"]
    return TEMPLATE_MODES["free"]["instruction"]

def bind_template_to_project(target: Path, template_id: str, *, layouts_dir: Path) -> bool:
    """把画廊选中的模板绑定到新项目（写 template_binding.json + 复制 layout_ref）。

    template_id 必须是 layouts_dir 下的合法目录名；非法或不存在时抛 ValueError，
    不静默跳过（前端画廊只展示合法模板，非法值说明契约被破坏）。
    """
    clean_id = str(template_id or "").strip()
    if not clean_id or clean_id in {".", ".."} or "/" in clean_id or "\\" in clean_id:
        raise ValueError(f"invalid template_id: {template_id}")
    source_dir = (layouts_dir / clean_id).resolve()
    if layouts_dir.resolve() not in source_dir.parents:
        raise ValueError(f"invalid template_id: {template_id}")
    if not source_dir.is_dir():
        raise ValueError(f"selected_template_id does not exist: {clean_id}")
    target.mkdir(parents=True, exist_ok=True)
    (target / "template_binding.json").write_text(
        json.dumps({"template_id": clean_id, "source": "gallery"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    layout_ref_dir = target / "templates" / "layout_ref"
    layout_ref_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, layout_ref_dir / clean_id, dirs_exist_ok=True)
    return True


def _overloaded_slide_ids(target: Path) -> list[int]:
    report_path = target / "qa" / "overload-report.json"
    if not report_path.exists():
        return []
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw = payload.get("overloaded_slides") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return []
    slide_ids: list[int] = []
    for item in raw:
        try:
            slide_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return slide_ids

def _slide_id_from_path(path_value: object) -> int | None:
    match = re.search(r"slide_(\d+)\.svg", str(path_value or ""), re.I)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None

def _preflight_blocking_findings(target: Path) -> list[dict[str, Any]]:
    report_path = target / "qa" / "preflight-report.json"
    if not report_path.exists():
        return []
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict) or payload.get("ok") is not False:
        return []
    raw_findings = payload.get("findings")
    if not isinstance(raw_findings, list):
        return []
    findings: list[dict[str, Any]] = []
    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "").strip().lower()
        if severity != "error":
            continue
        message = str(item.get("message") or "").strip()
        path = str(item.get("path") or "").strip()
        findings.append(
            {
                "severity": severity,
                "code": str(item.get("code") or "preflight-error").strip() or "preflight-error",
                "message": message,
                "path": path,
                "slide_id": _slide_id_from_path(path),
            }
        )
    return findings

def compute_export_readiness_full(name: str, target: Path, status: dict) -> dict:
    reasons: list[str] = []
    if not target.exists():
        reasons.append("项目不存在。")
    if not (target / "blueprint.json").exists():
        reasons.append("缺少 blueprint.json。")

    base = compute_export_readiness(target, status)
    reasons.extend(base.get("reasons", []))
    overloaded_slides = _overloaded_slide_ids(target)
    if overloaded_slides:
        reasons.append(
            "Budget policy blocks export for overloaded slides: "
            + ", ".join(str(item) for item in overloaded_slides)
            + ". Compress or split the slide content before finalizing."
        )
    preflight_findings = _preflight_blocking_findings(target)
    if preflight_findings:
        first = preflight_findings[0]
        slide_id = first.get("slide_id")
        prefix = f"第 {slide_id} 页" if slide_id else "页面"
        reasons.append(f"{prefix}导出前检查未通过：{first.get('message') or first.get('code')}")

    merged = []
    seen = set()
    for reason in reasons:
        if reason not in seen:
            merged.append(reason)
            seen.add(reason)
    ready = not merged
    return {
        "artifact_buildable": bool(base.get("artifact_buildable", base.get("ready")))
        and target.exists()
        and (target / "blueprint.json").exists()
        and not preflight_findings,
        "ready": ready,
        "status": "ready" if ready else "not_ready",
        "reasons": merged,
        "reason_codes": ["preflight_blocked"] if preflight_findings else [],
        "missing_slides": base.get("missing_slides", []),
        "placeholder_slides": base.get("placeholder_slides", []),
        "qa_failed_slides": base.get("qa_failed_slides", []),
        "warnings": base.get("warnings", []),
        "budget_overloaded_slides": overloaded_slides,
        "preflight_blocking_findings": preflight_findings,
        "preflight_findings": preflight_findings,
    }
