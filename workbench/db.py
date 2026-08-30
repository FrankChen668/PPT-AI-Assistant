from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_VERSION = 5


def open_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workbench_tasks (
          id TEXT PRIMARY KEY,
          project_name TEXT UNIQUE,
          workflow_mode TEXT NOT NULL,
          title TEXT NOT NULL,
          user_prompt TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          project_status TEXT NOT NULL DEFAULT '',
          recommended_action TEXT NOT NULL DEFAULT '',
          export_status TEXT NOT NULL DEFAULT '',
          slide_count INTEGER NOT NULL DEFAULT 0,
          next_slide_id INTEGER,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          completed_at TEXT NOT NULL DEFAULT '',
          archived_at TEXT NOT NULL DEFAULT '',
          last_error TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS workbench_session (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS workbench_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          payload_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES workbench_tasks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS workbench_page_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id TEXT NOT NULL,
          project_name TEXT NOT NULL,
          slide_id INTEGER NOT NULL,
          slide_no_at_event INTEGER,
          event_type TEXT NOT NULL,
          phase TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT '',
          started_at TEXT NOT NULL DEFAULT '',
          ended_at TEXT NOT NULL DEFAULT '',
          duration_ms INTEGER,
          payload_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES workbench_tasks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS workbench_slide_reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id TEXT NOT NULL,
          project_name TEXT NOT NULL,
          slide_id INTEGER NOT NULL,
          score INTEGER,
          usable_for_next_edit INTEGER,
          pptx_editable INTEGER,
          issue_tags_json TEXT NOT NULL DEFAULT '[]',
          notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES workbench_tasks(id) ON DELETE CASCADE,
          UNIQUE(task_id, slide_id)
        );

        CREATE INDEX IF NOT EXISTS idx_workbench_tasks_updated_at
          ON workbench_tasks(updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_workbench_tasks_status
          ON workbench_tasks(status);

        CREATE INDEX IF NOT EXISTS idx_workbench_page_events_task_slide
          ON workbench_page_events(task_id, slide_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_workbench_page_events_project_slide
          ON workbench_page_events(project_name, slide_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_workbench_slide_reviews_task_slide
          ON workbench_slide_reviews(task_id, slide_id, updated_at);

        CREATE INDEX IF NOT EXISTS idx_workbench_slide_reviews_project_slide
          ON workbench_slide_reviews(project_name, slide_id, updated_at);
        """
    )
    task_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(workbench_tasks)")}
    if "next_slide_id" not in task_columns:
        conn.execute("ALTER TABLE workbench_tasks ADD COLUMN next_slide_id INTEGER")
    event_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(workbench_page_events)")}
    if "slide_no_at_event" not in event_columns:
        conn.execute("ALTER TABLE workbench_page_events ADD COLUMN slide_no_at_event INTEGER")
        # Legacy v4 used slide_id as both identity and page number. This is only a
        # best-effort compatibility snapshot; it cannot reconstruct old reorders.
        conn.execute(
            "UPDATE workbench_page_events SET slide_no_at_event = slide_id WHERE slide_no_at_event IS NULL"
        )
    conn.execute(
        "INSERT OR IGNORE INTO workbench_session(key, value) VALUES('current_view', 'mode_select')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO workbench_session(key, value) VALUES('current_task_id', '')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO workbench_session(key, value) VALUES('selected_workflow_mode', 'prompt_deck')"
    )
    conn.execute(
        """
        UPDATE workbench_session
        SET value = 'mode_select'
        WHERE key = 'current_view'
          AND value = 'task_center'
          AND COALESCE((SELECT value FROM workbench_session WHERE key = 'current_task_id'), '') = ''
        """
    )
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
