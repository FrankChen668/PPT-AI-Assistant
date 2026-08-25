from __future__ import annotations

import json
from typing import Any


def handle_slide_budget_repair(handler: Any, name: str, slide_id: int) -> bool:
    from workbench import server as srv

    target = srv.project_dir(name)
    result = srv.repair_budget_overload(target, [slide_id])
    try:
        report = srv.evaluate_budget_policy(target, profile="proposal_consulting")
        result["budget_profile"] = report.profile
        result["overloaded_slides"] = report.overloaded_slides
    except (FileNotFoundError, ValueError, OSError) as exc:
        result["budget_refresh_error"] = {
            "code": "budget-refresh-failed",
            "message": str(exc),
            "context": {"profile": "proposal_consulting", "scope": "single-slide"},
        }
    srv.json_response(handler, srv.ok("budget repair completed", project=name, data=result))
    return True


def handle_slide_executor_packet(handler: Any, name: str, slide_id: int, payload: dict[str, Any]) -> bool:
    from workbench import server as srv

    target = srv.project_dir(name)
    markdown_raw = payload.get("markdown", True)
    write_markdown = bool(markdown_raw) if isinstance(markdown_raw, (bool, int)) else str(markdown_raw).strip().lower() != "false"
    packet_path = srv.generate_executor_packet(target, slide_id=slide_id, write_markdown=write_markdown)
    packet_data = json.loads(packet_path.read_text(encoding="utf-8"))
    packet_md = packet_path.with_suffix(".md")
    status = srv.load_status(target) or srv.build_initial_status_from_blueprint(name, target)
    slides = srv.enrich_slides_for_workbench(target, status.get("slides", []))
    status["slides"] = slides
    srv.add_event(status, "executor_packet", f"Generated executor packet for slide {slide_id}.")
    srv.save_status(target, status)
    srv.json_response(
        handler,
        srv.ok(
            "executor packet generated",
            project=name,
            data={
                "slide_id": slide_id,
                "packet_json_path": srv.to_relative_path(target, packet_path),
                "packet_markdown_path": srv.to_relative_path(target, packet_md) if packet_md.exists() else "",
                "verify_command": str(packet_data.get("verify") or ""),
            },
        ),
    )
    return True


def handle_slide_restore_revision(handler: Any, name: str, slide_id: int, payload: dict[str, Any]) -> bool:
    from workbench import server as srv

    target = srv.project_dir(name)
    revision_name = srv.require_non_empty(payload.get("revision_name"), "revision_name")
    restored_path = srv.restore_slide_revision(target, slide_id, revision_name)
    status = srv.load_status(target) or srv.build_initial_status_from_blueprint(name, target)
    for slide in status.get("slides", []):
        if int(slide.get("slide_id", 0)) == slide_id:
            slide["status"] = "restored"
            slide["qa_status"] = "not_run"
            slide["last_error"] = ""
            break
    srv.add_event(status, "revision_restored", f"Restored slide {slide_id} from {revision_name}.")
    srv.save_status(target, status)
    srv.json_response(handler, srv.ok("revision restored", name, {"slide_id": slide_id, "svg_path": restored_path}))
    return True


def handle_slide_placeholder_svg(handler: Any, name: str, slide_id: int) -> bool:
    from workbench import server as srv

    output = srv.write_placeholder_svg(name, slide_id=slide_id)
    target = srv.project_dir(name)
    status = srv.load_status(target) or srv.build_initial_status_from_blueprint(name, target)
    slides = status.get("slides") if isinstance(status.get("slides"), list) else []
    for slide in slides:
        if int(slide.get("slide_id") or 0) != int(slide_id):
            continue
        slide["status"] = "placeholder_svg"
        slide["qa_status"] = "not_run"
        slide["has_svg"] = True
        slide["svg_path"] = f"svg_output/slide_{slide_id:02d}.svg"
        slide["last_error"] = "placeholder is dry-run only"
        break
    status["placeholder_generation_used"] = True
    srv.add_event(status, "placeholder_svg", f"Placeholder SVG generated for slide {slide_id} (dry-run only).")
    srv.save_status(target, status)
    srv.json_response(
        handler,
        srv.ok(
            "placeholder svg generated (dry-run only)",
            project=name,
            data={"path": str(output), "dry_run_only": True},
        ),
    )
    return True


def handle_project_placeholder_svg(handler: Any, name: str) -> bool:
    from workbench import server as srv

    output = srv.write_placeholder_svg(name)
    target = srv.project_dir(name)
    status = srv.load_status(target) or srv.build_initial_status_from_blueprint(name, target)
    slides = status.get("slides") if isinstance(status.get("slides"), list) else []
    if slides:
        slide = slides[0] if isinstance(slides[0], dict) else {}
        slide["status"] = "placeholder_svg"
        slide["qa_status"] = "not_run"
        slide["has_svg"] = True
        slide["svg_path"] = "svg_output/slide_01.svg"
        slide["last_error"] = "placeholder is dry-run only"
    status["placeholder_generation_used"] = True
    srv.add_event(status, "placeholder_svg", "Placeholder SVG generated (dry-run only).")
    srv.save_status(target, status)
    srv.json_response(
        handler,
        srv.ok(
            "placeholder svg generated (dry-run only)",
            project=name,
            data={"path": str(output), "dry_run_only": True},
        ),
    )
    return True


def handle_project_budget_repair(handler: Any, name: str) -> bool:
    from workbench import server as srv

    target = srv.project_dir(name)
    result = srv.repair_budget_overload(target)
    try:
        report = srv.evaluate_budget_policy(target, profile="proposal_consulting")
        result["budget_profile"] = report.profile
        result["overloaded_slides"] = report.overloaded_slides
    except (FileNotFoundError, ValueError, OSError) as exc:
        result["budget_refresh_error"] = {
            "code": "budget-refresh-failed",
            "message": str(exc),
            "context": {"profile": "proposal_consulting", "scope": "project"},
        }
    srv.json_response(handler, srv.ok("budget repair completed", project=name, data=result))
    return True
