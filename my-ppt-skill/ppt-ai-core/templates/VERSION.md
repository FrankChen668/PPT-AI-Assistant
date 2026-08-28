# ppt-ai-core templates baseline

- Source: `<ppt-master-repo>/skills/ppt-master/templates`
- Imported into this repo as: `my-ppt-skill/ppt-ai-core/templates`
- Import date: 2026-04-20
- Governance: this directory is the default template SSOT for layouts/charts/icons.

When updating templates, keep this file in sync and re-run regression:

```bash
python scripts/build_project.py projects/ai-trends-demo --skip-render --snapshots
python scripts/regress_layouts.py
```
