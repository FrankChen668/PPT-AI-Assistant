from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NativeTextVerifyReport:
    ok: bool
    checked_pptx: int
    checked_lines: int
    narrow_column_lines: int
    risk_lines: int
    findings: list[dict[str, Any]]
