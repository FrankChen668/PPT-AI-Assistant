from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JsonLoadResult:
    status: str
    payload: Any | None
    code: str
    message: str


def load_json(path: Path, *, encoding: str = "utf-8") -> JsonLoadResult:
    if not path.exists():
        return JsonLoadResult("missing", None, "missing-file", f"File not found: {path.name}")
    try:
        payload = json.loads(path.read_text(encoding=encoding))
    except json.JSONDecodeError as exc:
        return JsonLoadResult("invalid", None, "invalid-json", f"Could not parse JSON: {exc}")
    except OSError as exc:
        return JsonLoadResult("invalid", None, "read-failed", f"Could not read JSON file: {exc}")
    return JsonLoadResult("ok", payload, "", "")


def load_json_object(path: Path, *, encoding: str = "utf-8") -> JsonLoadResult:
    result = load_json(path, encoding=encoding)
    if result.status != "ok":
        return result
    if not isinstance(result.payload, dict):
        return JsonLoadResult(
            "schema_mismatch",
            None,
            "schema-mismatch",
            "Expected JSON object at root.",
        )
    return result
