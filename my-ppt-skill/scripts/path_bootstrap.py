from __future__ import annotations

import sys
from pathlib import Path


def ensure_scripts_path(anchor: Path) -> Path:
    scripts_dir = anchor.resolve().parent
    scripts_text = str(scripts_dir)
    if scripts_text not in sys.path:
        sys.path.insert(0, scripts_text)
    return scripts_dir
