from __future__ import annotations

import json
from pathlib import Path


def project_sort_key(info: dict) -> tuple[str, float]:
    return (str(info.get("updated_at") or ""), float(info.get("mtime") or 0.0))


def collect_workbench_projects(projects_root: Path) -> dict:
    projects: list[str] = []
    project_infos: list[dict] = []
    if not projects_root.exists():
        return {
            "projects": projects,
            "project_infos": project_infos,
            "resumable_projects": [],
            "resumable_count": 0,
            "resume_mode": "none",
            "latest_project": "",
        }

    for path in sorted(projects_root.iterdir(), key=lambda item: item.name):
        if not path.is_dir():
            continue
        projects.append(path.name)
        status_path = path / "workbench_status.json"
        if not status_path.exists():
            continue
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {}
        try:
            mtime = status_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        slides = status.get("slides") if isinstance(status.get("slides"), list) else []
        export_state = status.get("export") if isinstance(status.get("export"), dict) else {}
        project_status_value = str(status.get("project_status") or "")
        export_status = str(export_state.get("status") or "")
        has_pptx = bool(export_state.get("pptx_path")) or (path / "exports" / "output-native.pptx").exists()
        has_svg_count = sum(
            1
            for slide in slides
            if slide.get("has_svg") or (path / "svg_output" / f"slide_{int(slide.get('slide_id') or 0):02d}.svg").exists()
        )
        qa_passed_count = sum(1 for slide in slides if str(slide.get("qa_status") or "") == "passed")
        is_finished = project_status_value == "exported" or export_status == "exported" or has_pptx
        info = {
            "project": str(status.get("project") or path.name),
            "project_status": project_status_value or ("exported" if is_finished else "project_created"),
            "workflow_mode": str(status.get("workflow_mode") or ""),
            "workflow_label": str(status.get("workflow_label") or ""),
            "route_label": str(status.get("route_label") or ""),
            "slide_count": int(status.get("slide_count") or len(slides)),
            "has_svg_count": has_svg_count,
            "qa_passed_count": qa_passed_count,
            "export_status": export_status,
            "has_pptx": has_pptx,
            "updated_at": str(status.get("updated_at") or ""),
            "created_at": str(status.get("created_at") or ""),
            "last_error": str(export_state.get("last_error") or ""),
            "is_resumable": not is_finished,
            "mtime": mtime,
        }
        project_infos.append(info)

    project_infos.sort(key=project_sort_key, reverse=True)
    resumable_projects = [info for info in project_infos if info.get("is_resumable")]
    if len(resumable_projects) == 1:
        resume_mode = "auto"
        latest_project = str(resumable_projects[0]["project"])
    elif len(resumable_projects) > 1:
        resume_mode = "choose"
        latest_project = ""
    else:
        resume_mode = "none"
        latest_project = ""
    return {
        "projects": projects,
        "project_infos": project_infos,
        "resumable_projects": resumable_projects,
        "resumable_count": len(resumable_projects),
        "resume_mode": resume_mode,
        "latest_project": latest_project,
    }
