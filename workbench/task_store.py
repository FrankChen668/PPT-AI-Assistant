from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from workbench.db import initialize_schema, open_connection


SESSION_KEYS = {"current_view", "current_task_id", "selected_workflow_mode"}
VALID_VIEWS = {"mode_select", "task_center", "new_task", "task_detail"}
VALID_WORKFLOW_MODES = {"prompt_deck", "single_page", "document_deck", "optimize_existing", "repair_existing"}
DEDUPED_EVENT_TYPES: set[str] = set()
EVENT_DEDUPE_WINDOW = timedelta(seconds=2)
SLIDE_REVIEW_TAGS = {
    "visual_quality",
    "structure_mismatch",
    "text_overflow",
    "not_consulting_grade",
    "editable_issue",
    "information_density",
    "other",
}
MAX_REVIEW_NOTES = 1200


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _timestamp(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    item = dict(row) if row is not None else {}
    if not item:
        return {}
    item.pop("benchmark_mode", None)
    item.pop("benchmark_set", None)
    item.pop("benchmark_pages_json", None)
    return item


def task_status_from_project(payload: dict[str, Any]) -> str:
    project_status = str(payload.get("project_status") or "")
    raw_export = payload.get("export")
    export: dict[str, Any] = raw_export if isinstance(raw_export, dict) else {}
    export_status = str(export.get("status") or "")
    action_key = recommended_action_key(payload)
    if action_key == "download_pptx":
        return "completed"
    if project_status in {"qa_failed", "export_failed", "export_review_required"} or export_status in {
        "failed",
        "review_required",
    }:
        return "blocked"
    if project_status in {"export_ready", "qa_passed"}:
        return "ready"
    if project_status in {"waiting_codex", "project_created", "svg_partial"}:
        return "active"
    return "active"


def recommended_action_key(payload: dict[str, Any]) -> str:
    action = payload.get("recommended_next_action")
    if isinstance(action, dict):
        return str(action.get("key") or "")
    return ""


def _normalize_issue_tags(values: list[str] | None) -> list[str]:
    if not isinstance(values, list):
        return []
    tags: list[str] = []
    for value in values:
        key = str(value or "").strip()
        if not key or key not in SLIDE_REVIEW_TAGS:
            continue
        if key not in tags:
            tags.append(key)
    return tags[:8]


def _normalize_review_notes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) > MAX_REVIEW_NOTES:
        return text[:MAX_REVIEW_NOTES].rstrip()
    return text


def _to_int_bool(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _decode_slide_review(item: dict[str, Any]) -> dict[str, Any]:
    if not item:
        return {}
    raw_tags = item.get("issue_tags_json")
    tags: list[str] = []
    if isinstance(raw_tags, str) and raw_tags.strip():
        try:
            decoded = json.loads(raw_tags)
        except json.JSONDecodeError:
            decoded = []
        if isinstance(decoded, list):
            tags = [str(value).strip() for value in decoded if str(value).strip()]
    item["issue_tags"] = tags
    item["usable_for_next_edit"] = None if item.get("usable_for_next_edit") is None else bool(int(item["usable_for_next_edit"]))
    item["pptx_editable"] = None if item.get("pptx_editable") is None else bool(int(item["pptx_editable"]))
    return item


class TaskStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        with self.connect() as conn:
            initialize_schema(conn)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = open_connection(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def get_session(self) -> dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value FROM workbench_session").fetchall()
        session = {str(row["key"]): str(row["value"]) for row in rows}
        session.setdefault("current_view", "mode_select")
        session.setdefault("current_task_id", "")
        session.setdefault("selected_workflow_mode", "prompt_deck")
        return session

    def update_session(
        self,
        *,
        current_view: str | None = None,
        current_task_id: str | None = None,
        selected_workflow_mode: str | None = None,
    ) -> dict[str, str]:
        with self.connect() as conn:
            if current_view is not None:
                if current_view not in VALID_VIEWS:
                    raise ValueError("current_view must be mode_select, task_center, new_task, or task_detail.")
                conn.execute(
                    "INSERT INTO workbench_session(key, value) VALUES('current_view', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (current_view,),
                )
            if current_task_id is not None:
                conn.execute(
                    "INSERT INTO workbench_session(key, value) VALUES('current_task_id', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (current_task_id,),
                )
            if selected_workflow_mode is not None:
                if selected_workflow_mode not in VALID_WORKFLOW_MODES:
                    raise ValueError("selected_workflow_mode is not supported.")
                conn.execute(
                    "INSERT INTO workbench_session(key, value) VALUES('selected_workflow_mode', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (selected_workflow_mode,),
                )
            conn.commit()
        return self.get_session()

    def activate_task(self, task_id: str) -> dict[str, str]:
        task = self.get_task(task_id)
        if not task:
            raise ValueError("task does not exist.")
        return self.update_session(current_view="task_detail", current_task_id=task_id)

    def create_task(
        self,
        *,
        workflow_mode: str,
        title: str,
        user_prompt: str,
        project_name: str = "",
        slide_count: int = 0,
        status: str = "active",
        project_status: str = "",
        recommended_action: str = "",
        export_status: str = "",
        last_error: str = "",
        created_at: str | None = None,
        updated_at: str | None = None,
        task_id: str | None = None,
    ) -> dict:
        now = utc_now()
        created = created_at or now
        updated = updated_at or created
        identifier = task_id or f"task_{uuid.uuid4().hex}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO workbench_tasks(
                  id, project_name, workflow_mode, title, user_prompt, status,
                  project_status, recommended_action, export_status, slide_count,
                  created_at, updated_at, completed_at, archived_at, last_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    project_name or None,
                    workflow_mode,
                    title,
                    user_prompt,
                    status,
                    project_status,
                    recommended_action,
                    export_status,
                    int(slide_count or 0),
                    created,
                    updated,
                    created if status == "completed" else "",
                    created if status == "archived" else "",
                    last_error,
                ),
            )
            conn.commit()
        return self.get_task(identifier)

    def get_task(self, task_id: str) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM workbench_tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row)

    def get_task_by_project(self, project_name: str) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM workbench_tasks WHERE project_name = ?", (project_name,)).fetchone()
        return row_to_dict(row)

    def list_tasks(self, *, status: str | None = None, include_archived: bool = False) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if not include_archived:
            clauses.append("status != 'archived'")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM workbench_tasks {where} ORDER BY rowid DESC",
                params,
            ).fetchall()
        tasks = [row_to_dict(row) for row in rows]
        tasks.sort(
            key=lambda item: (
                _timestamp(item.get("updated_at")),
                _timestamp(item.get("created_at")),
            ),
            reverse=True,
        )
        return tasks

    def sync_task_from_project(self, task_id: str, project_status_payload: dict[str, Any]) -> dict[str, Any]:
        raw_export = project_status_payload.get("export")
        export: dict[str, Any] = raw_export if isinstance(raw_export, dict) else {}
        raw_slides = project_status_payload.get("slides")
        slides: list[Any] = raw_slides if isinstance(raw_slides, list) else []
        next_status = task_status_from_project(project_status_payload)
        next_project_status = str(project_status_payload.get("project_status") or "")
        next_recommended_action = recommended_action_key(project_status_payload)
        next_export_status = str(export.get("status") or "")
        next_slide_count = int(project_status_payload.get("slide_count") or len(slides))
        next_last_error = str(export.get("last_error") or "")
        project_updated_at = str(project_status_payload.get("updated_at") or "").strip()
        now = utc_now()
        with self.connect() as conn:
            existing = row_to_dict(
                conn.execute("SELECT * FROM workbench_tasks WHERE id = ?", (task_id,)).fetchone()
            )
            changed = any(
                [
                    str(existing.get("status") or "") != next_status,
                    str(existing.get("project_status") or "") != next_project_status,
                    str(existing.get("recommended_action") or "") != next_recommended_action,
                    str(existing.get("export_status") or "") != next_export_status,
                    int(existing.get("slide_count") or 0) != next_slide_count,
                    str(existing.get("last_error") or "") != next_last_error,
                ]
            )
            next_updated_at = (project_updated_at or now) if changed else str(existing.get("updated_at") or now)
            completed_at = now if next_status == "completed" and not str(existing.get("completed_at") or "") else ""
            conn.execute(
                """
                UPDATE workbench_tasks
                SET status = ?,
                    project_status = ?,
                    recommended_action = ?,
                    export_status = ?,
                    slide_count = ?,
                    updated_at = ?,
                    completed_at = CASE WHEN completed_at = '' THEN ? ELSE completed_at END,
                    last_error = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    next_project_status,
                    next_recommended_action,
                    next_export_status,
                    next_slide_count,
                    next_updated_at,
                    completed_at,
                    next_last_error,
                    task_id,
                ),
            )
            conn.commit()
        return self.get_task(task_id)

    def mark_missing_project(self, task_id: str) -> dict:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE workbench_tasks
                SET status = 'missing_project',
                    updated_at = ?,
                    last_error = 'Project directory is missing.'
                WHERE id = ?
                """,
                (now, task_id),
            )
            conn.commit()
        return self.get_task(task_id)

    def append_event(self, task_id: str, event_type: str, payload: dict | None = None) -> dict:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat(timespec="microseconds")
        text = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
        with self.connect() as conn:
            if event_type in DEDUPED_EVENT_TYPES:
                existing = conn.execute(
                    """
                    SELECT *
                    FROM workbench_events
                    WHERE task_id = ? AND event_type = ? AND payload_json = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (task_id, event_type, text),
                ).fetchone()
                if existing is not None:
                    try:
                        existing_at = datetime.fromisoformat(str(existing["created_at"]))
                    except ValueError:
                        existing_at = None
                    if existing_at is not None and now_dt - existing_at <= EVENT_DEDUPE_WINDOW:
                        return row_to_dict(existing)
            cursor = conn.execute(
                "INSERT INTO workbench_events(task_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (task_id, event_type, text, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM workbench_events WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row)

    def list_events(self, task_id: str, *, limit: int = 50) -> list[dict]:
        safe_limit = max(1, min(int(limit or 50), 200))
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM workbench_events
                WHERE task_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (task_id, safe_limit),
            ).fetchall()
        events: list[dict] = []
        for row in rows:
            item = row_to_dict(row)
            try:
                payload = json.loads(str(item.get("payload_json") or "{}"))
            except json.JSONDecodeError:
                payload = {}
            item["payload"] = payload if isinstance(payload, dict) else {}
            events.append(item)
        return events

    def append_page_event(
        self,
        task_id: str,
        *,
        project_name: str,
        slide_id: int,
        event_type: str,
        phase: str = "",
        status: str = "",
        started_at: str = "",
        ended_at: str = "",
        duration_ms: int | None = None,
        payload: dict | None = None,
    ) -> dict:
        now = utc_now()
        clean_event_type = str(event_type or "").strip()
        if not clean_event_type:
            raise ValueError("event_type is required.")
        if int(slide_id or 0) < 0:
            raise ValueError("slide_id must be >= 0.")
        text = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO workbench_page_events(
                  task_id, project_name, slide_id, event_type, phase, status,
                  started_at, ended_at, duration_ms, payload_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    str(project_name or ""),
                    int(slide_id),
                    clean_event_type,
                    str(phase or ""),
                    str(status or ""),
                    str(started_at or ""),
                    str(ended_at or ""),
                    int(duration_ms) if duration_ms is not None else None,
                    text,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM workbench_page_events WHERE id = ?", (cursor.lastrowid,)).fetchone()
        item = row_to_dict(row)
        try:
            decoded = json.loads(str(item.get("payload_json") or "{}"))
        except json.JSONDecodeError:
            decoded = {}
        item["payload"] = decoded if isinstance(decoded, dict) else {}
        return item

    def upsert_slide_review(
        self,
        task_id: str,
        *,
        project_name: str,
        slide_id: int,
        score: int | None = None,
        usable_for_next_edit: bool | None = None,
        pptx_editable: bool | None = None,
        issue_tags: list[str] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        if int(slide_id or 0) < 1:
            raise ValueError("slide_id must be positive.")
        if score is not None and int(score) not in {1, 2, 3, 4, 5}:
            raise ValueError("score must be 1-5.")
        normalized_notes = _normalize_review_notes(notes)
        normalized_tags = _normalize_issue_tags(issue_tags)
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO workbench_slide_reviews(
                  task_id, project_name, slide_id, score,
                  usable_for_next_edit, pptx_editable, issue_tags_json,
                  notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, slide_id) DO UPDATE SET
                  project_name=excluded.project_name,
                  score=excluded.score,
                  usable_for_next_edit=excluded.usable_for_next_edit,
                  pptx_editable=excluded.pptx_editable,
                  issue_tags_json=excluded.issue_tags_json,
                  notes=excluded.notes,
                  updated_at=excluded.updated_at
                """,
                (
                    str(task_id or "").strip(),
                    str(project_name or "").strip(),
                    int(slide_id),
                    int(score) if score is not None else None,
                    _to_int_bool(usable_for_next_edit),
                    _to_int_bool(pptx_editable),
                    json.dumps(normalized_tags, ensure_ascii=False),
                    normalized_notes,
                    now,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT *
                FROM workbench_slide_reviews
                WHERE task_id = ? AND slide_id = ?
                """,
                (str(task_id or "").strip(), int(slide_id)),
            ).fetchone()
        return _decode_slide_review(row_to_dict(row))

    def get_slide_review(self, task_id: str, slide_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM workbench_slide_reviews
                WHERE task_id = ? AND slide_id = ?
                """,
                (str(task_id or "").strip(), int(slide_id)),
            ).fetchone()
        return _decode_slide_review(row_to_dict(row))

    def list_slide_reviews(self, task_id: str, *, slide_id: int | None = None) -> list[dict[str, Any]]:
        clauses = ["task_id = ?"]
        params: list[Any] = [str(task_id or "").strip()]
        if slide_id is not None:
            clauses.append("slide_id = ?")
            params.append(int(slide_id))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM workbench_slide_reviews
                WHERE {' AND '.join(clauses)}
                ORDER BY slide_id ASC, updated_at DESC
                """,
                params,
            ).fetchall()
        return [_decode_slide_review(row_to_dict(row)) for row in rows]

    def list_page_events(self, task_id: str, *, slide_id: int | None = None, limit: int = 200) -> list[dict]:
        safe_limit = max(1, min(int(limit or 200), 1000))
        params: list[Any] = [task_id]
        clauses = ["task_id = ?"]
        if slide_id is not None:
            clauses.append("slide_id = ?")
            params.append(int(slide_id))
        params.append(safe_limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM workbench_page_events
                WHERE {' AND '.join(clauses)}
                ORDER BY id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        events: list[dict] = []
        for row in rows:
            item = row_to_dict(row)
            try:
                payload = json.loads(str(item.get("payload_json") or "{}"))
            except json.JSONDecodeError:
                payload = {}
            item["payload"] = payload if isinstance(payload, dict) else {}
            events.append(item)
        return events

    def migrate_projects(self, projects_root: Path) -> dict[str, int]:
        created = 0
        skipped = 0
        if not projects_root.exists():
            return {"created": 0, "skipped": 0}
        for path in sorted(projects_root.iterdir(), key=lambda item: item.name):
            if not path.is_dir():
                continue
            status_path = path / "workbench_status.json"
            if not status_path.exists():
                continue
            if self.get_task_by_project(path.name):
                skipped += 1
                continue
            try:
                payload = json.loads(status_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            slides = payload.get("slides") if isinstance(payload.get("slides"), list) else []
            export = payload.get("export") if isinstance(payload.get("export"), dict) else {}
            project_status = str(payload.get("project_status") or "")
            title = self.title_from_project_payload(path.name, payload)
            task_status = task_status_from_project(payload)
            self.create_task(
                workflow_mode=str(payload.get("workflow_mode") or "single_page"),
                title=title,
                user_prompt=str(payload.get("prompt") or payload.get("user_prompt") or title),
                project_name=path.name,
                slide_count=int(payload.get("slide_count") or len(slides)),
                status=task_status,
                project_status=project_status,
                recommended_action=recommended_action_key(payload),
                export_status=str(export.get("status") or ""),
                last_error=str(export.get("last_error") or ""),
                created_at=str(payload.get("created_at") or utc_now()),
                updated_at=str(payload.get("updated_at") or payload.get("created_at") or utc_now()),
            )
            created += 1
        return {"created": created, "skipped": skipped}

    @staticmethod
    def title_from_project_payload(project_name: str, payload: dict) -> str:
        title = str(payload.get("title") or "").strip()
        if title:
            return title
        slides = payload.get("slides") if isinstance(payload.get("slides"), list) else []
        if slides:
            first = slides[0] if isinstance(slides[0], dict) else {}
            slide_title = str(first.get("title") or "").strip()
            if slide_title:
                return slide_title[:80]
        return project_name


def initialize_task_store(db_path: Path) -> TaskStore:
    return TaskStore(db_path)
