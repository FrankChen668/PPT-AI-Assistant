"""Exporter package for SVG -> PPTX conversion.

This directory intentionally mirrors the package layout used by `ppt-master`:
- keep a thin CLI facade (`svg_to_pptx.py`)
- keep conversion logic in importable modules

Authority contract:
- `scripts/svg_to_pptx.py` is the supported low-level adapter for troubleshooting.
- `ppt-ai-core/scripts/svg_to_pptx.py` remains the authoritative exporter core.
- Production delivery should use `scripts/build_project.py --phase finalize --skip-render`.
"""

