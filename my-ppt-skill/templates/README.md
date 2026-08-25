# Templates Compatibility Notice

This directory is a compatibility layer.

## Authoritative Template Source (Must Use)

All new template development and default runtime selection must use:

- `my-ppt-skill/ppt-ai-core/templates/layouts/`
- `my-ppt-skill/ppt-ai-core/templates/layouts_candidate/` (candidate only; not indexed for mainline retrieval)
- `my-ppt-skill/ppt-ai-core/templates/charts/`
- `my-ppt-skill/ppt-ai-core/templates/icons/`

Mainline rule:

- `layouts/` contains indexed and shippable templates only.
- `layouts_candidate/` contains pre-index candidates only.
- `scripts/validate_layouts_index.py` must pass before moving a candidate into `layouts/`.

## Legacy Path (Read-Only)

- `my-ppt-skill/templates/ppt-master/` is legacy compatibility only.
- New projects are prohibited from using this legacy path as the primary template entrypoint.
- Template operations must go through `scripts/ppt_master/project_manager.py`.

## New Project Rule

For new projects, template selection must use:

```bash
python scripts/ppt_master/project_manager.py list-templates
python scripts/ppt_master/project_manager.py init <project_name> --template <layout_id>
python scripts/ppt_master/project_manager.py apply-template <project_path> <layout_id>
```

## Legacy Tree Retirement Boundary

This section records the retirement boundary of the legacy tree
`my-ppt-skill/templates/ppt-master/` (~6911 files). No file may be deleted based
on this section: it is an audit record only. Any actual pruning requires
separate owner confirmation (per repo `AGENTS.md` Owner 确认门).

### Entrypoint check result (recorded, not weakened)

`python my-ppt-skill/scripts/check_template_entrypoints.py` on 2026-07-28 returned
`status=pass` (exit 0). All seven checks passed, including the ones that guard the
legacy tree:

- `legacy_mirror_drift`: compared 6910 mirror files; only allowlisted differences
  (`README-LEGACY.md` present only in legacy, `layouts/layouts_index.json`
  content mismatch) — no unexpected drift.
- `duplicate_asset_growth`: core=6959 files / 6386043 bytes, legacy=6911 files /
  6145672 bytes (legacy stays below core; no growth warning).
- `no_runtime_legacy_reads`: no mainflow script reads `templates/ppt-master`
  outside the explicit allowlist.
- `project_bindings`: `scanned_bindings=0` — no current project binding uses the
  legacy source.

The entrypoint constraints above are **not weakened** by this document; this
change is documentation-only.

### Reference audit (who still references the legacy tree)

Audited by searching for `templates/ppt-master` across scripts, tests, and docs
(2026-07-28). References still pointing at the legacy tree:

- Runtime / compatibility (read only via explicit switch):
  - `scripts/ppt_master/project_manager.py` reads `templates/ppt-master/layouts`
    **only** through the `--allow-legacy-templates` fallback in
    `resolve_layout_template_source` and in the `list-templates` legacy display.
    The default resolution path is `ppt-ai-core/templates/layouts`.
  - `scripts/import_pptmaster_assets.py` targets `templates/ppt-master/` as the
    import destination that populates the mirror.
- Governance / gates (compare against the tree, do not select from it):
  - `scripts/check_template_entrypoints.py` (the checks listed above).
  - `scripts/check_docs_quality.py` (forbids the legacy index path inside docs).
  - `scripts/quality_gate.py` (runs the entrypoint checker in release checks).
  - `workbench/repo_hygiene.py` (`duplicate-asset-growth-trend` compares legacy
    vs. core file counts).
- Tests (assert the guards above):
  - `my-ppt-skill/tests/test_check_template_entrypoints.py`
  - `my-ppt-skill/tests/test_quality_gate.py`
  - `workbench/tests/test_repo_hygiene.py`
- Docs: this README, `templates/ppt-master/README.md`,
  `templates/ppt-master/README-LEGACY.md`, `docs/template-entrypoint-policy.md`,
  `workbench/README.md`.

### Retention scope (must keep now)

- The entire `templates/ppt-master/` tree stays retained. It is still readable
  through the explicit `--allow-legacy-templates` compatibility switch (policy
  §6 exception: blocked production recovery / historical reproducibility), and
  several governance checks and tests use it as a comparison baseline.
- `templates/ppt-master/layouts/layouts_index.json`, `README.md`, and
  `README-LEGACY.md` are load-bearing for the mirror-drift allowlist and must not
  be removed without updating the checker.

### Pruning candidates (audit-only; execution needs owner confirmation)

- The bulk mirrored legacy asset subtrees under `templates/ppt-master/`
  (`layouts/`, `charts/`, `icons/`) duplicate `ppt-ai-core/templates/*` and are
  surfaced only through the mirror-drift / duplicate-growth comparison, not
  through any default runtime read. They are candidates for eventual retirement.
- These sibling compat stubs are **not** part of the ppt-master tree and out of
  this boundary's scope: `templates/charts/kpi-card.svg`,
  `templates/icons/arrow-right.svg`, `templates/template_catalog.json` (the
  latter is actively read by `select_reference_templates.py` /
  `generate_art_direction.py`).

### Owner and trigger conditions

- Owner: product owner (per repo `AGENTS.md` Owner 确认门). Any deletion is a
  separate, owner-confirmed change; this audit does not authorize it.
- Trigger conditions for a future pruning proposal (all must hold):
  1. `check_template_entrypoints.py` still reports `scanned_bindings=0` (no
     project binds the legacy source), and no historical project needs
     `--allow-legacy-templates`.
  2. The governance checks that compare against the mirror
     (`legacy_mirror_drift`, `duplicate_asset_growth`,
     `repo_hygiene.duplicate-asset-growth-trend`) are updated first so removal
     does not break the entrypoint gate.
  3. Owner explicitly confirms scope, migration buffer, and rollback per
     `docs/template-entrypoint-policy.md` §5–§7.
