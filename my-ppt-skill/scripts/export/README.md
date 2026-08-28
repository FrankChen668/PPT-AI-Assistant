# scripts/export (Internal Compatibility Layer)

This folder is **internal/compat** and is not a public delivery entrypoint.

- Authoritative exporter core: `my-ppt-skill/ppt-ai-core/scripts/svg_to_pptx.py`
- Public adapter for troubleshooting: `my-ppt-skill/scripts/svg_to_pptx.py`
- Delivery path: `python scripts/build_project.py ... --phase finalize --skip-render`

Do not use this folder as an alternate user-facing export workflow.

