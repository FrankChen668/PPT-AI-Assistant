# Workbench

Workbench is the local browser control panel for page-by-page AI PPT production.

## Positioning

- Local AI-PPT companion for individuals and small teams.
- Not SaaS in the current stage.
- Controlled sharing for 3-4 trusted users on an office private LAN is supported.
- Public-network, authenticated multi-tenant, and untrusted multi-user deployment remain out of scope.

## Start

```powershell
python -m workbench.healthcheck
python start_workbench.py
```

Open:

```text
http://localhost:8765
http://<private-lan-ip>:8765
```

- `python -m workbench.healthcheck` validates local readiness and reports missing env-ref values.
- `python start_workbench.py` loads the repository-root `.env`, runs the readiness check, and starts the server.
- The server defaults to `WORKBENCH_HOST=0.0.0.0` and `WORKBENCH_PORT=8765`. Static files and APIs share one origin, so no CORS configuration or separate frontend process is required.
- Projects are created under `my-ppt-skill/projects/<project_name>/`.

## Generation Path

1. Create a task in the browser.
2. Workbench writes structured project files (`design_spec.md`, `outline.md`, `blueprint.json`, per-slide tasks).
3. Workbench uses `api_auto`: it calls locally configured model APIs to generate missing `svg_output/slide_XX.svg` pages.
4. Workbench refreshes preview, runs QA, and only exposes the PPT download when the recommended next action is `download_pptx`.

If real generation is unavailable (for example the API key is missing), Workbench returns an explicit error and guidance instead of a placeholder result.

Provider fallback is local and quota-only. The runtime order is Google/Gemini -> Xiaomi -> SiliconFlow -> DeepSeek. Only clear quota/rate-limit responses trigger cross-provider fallback; invalid SVG, prompt errors, and code errors do not. Runtime quota state stores only provider and key index; API key values are never logged or persisted.

## Export Rule (Mandatory)

Use only this finalize path for delivery export:

```powershell
cd my-ppt-skill
python scripts/build_project.py projects/<project> --phase finalize --skip-render --enable-layout-lint --enable-visual-qa --strict --safe-area-profile presentation --snapshots
```

## Product Boundary

- Model/API settings persist provider/model/base_url only. API keys are runtime secrets and are not written as plaintext into local settings files.
- Store only env-var references such as `siliconflow_api_key_env=WORKBENCH_SILICONFLOW_API_KEY`; real keys go into repository-root `.env` or your shell environment.
- Placeholder SVG generation is dry-run only (healthcheck / explicit placeholder action) and is blocked from real delivery acceptance.
- Final generated results still require human review before delivery.

## More

- Installation and troubleshooting: [docs/first-run-checklist.md](../docs/first-run-checklist.md)
- Local security boundary: [docs/security-local-boundary.md](../docs/security-local-boundary.md)
