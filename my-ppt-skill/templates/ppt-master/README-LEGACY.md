# LEGACY TEMPLATE PATH (READ-ONLY)

`my-ppt-skill/templates/ppt-master/*` is retained only for backward compatibility.

## Mandatory Rules

1. New projects must not select templates directly from this directory.
2. This directory is read-only for compatibility scenarios.
3. Primary source of truth is:
   - `my-ppt-skill/ppt-ai-core/templates/*`
4. Template operations must use:
   - `python scripts/ppt_master/project_manager.py ...`
5. Legacy source access is allowed only when an explicit compatibility flag is provided (for example: `--allow-legacy-templates`).

## Why It Exists

- Prevents breaking historical projects that referenced legacy assets.
- Provides migration buffer while all new workflow converges on `ppt-ai-core/templates`.
