#!/usr/bin/env python3
"""Import templates/assets from a local ppt-master checkout.

We keep the imported assets under my-ppt-skill/templates/ppt-master/ so our
existing templates/ directory remains stable and hand-curated assets are not
overwritten accidentally.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

DEFAULT_SRC = Path.home() / "Documents" / "Cursor" / "ppt-master" / "skills" / "ppt-master" / "templates"


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import ppt-master templates into this repo.")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC, help="ppt-master templates directory")
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "templates" / "ppt-master",
        help="Destination directory under this repo",
    )
    args = parser.parse_args(argv)

    src = args.src.resolve()
    dest = args.dest.resolve()
    if not src.exists():
        raise SystemExit(f"Source does not exist: {src}")
    copy_tree(src, dest)
    print(f"Imported ppt-master templates to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

