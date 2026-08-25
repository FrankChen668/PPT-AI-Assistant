# Security Local Boundary

Updated: 2026-08-07
Status: active

## Purpose

Define what is safe and supported for local use today, and what is explicitly out of scope until stronger auth and deployment controls exist.

## Current Security Boundary

Supported boundary:

1. Workbench usage on the host computer or by 3-4 trusted colleagues on the same office private LAN.
2. Secrets injected through environment variables or env-ref fields in `workbench/settings.local.json`.
3. Local repo execution by a trusted operator who can read project files and reports.

Not supported as a secure deployment model:

1. Exposing Workbench on a public network, guest Wi-Fi, port-forwarded router, or other untrusted network.
2. Treating office sharing as a secure multi-user system; there is no authentication, authorization, or data isolation.
3. Persisting plaintext provider secrets in repo-tracked files or local settings files.
4. Treating local browser access as a substitute for session auth, tenant isolation, or audit logging.

## Mandatory Local Rules

1. Bind to `0.0.0.0` only for a trusted office private LAN; use `WORKBENCH_HOST=127.0.0.1` when LAN sharing is not needed.
2. Allow the Workbench TCP port only on the Windows `Private` firewall profile.
3. Keep API keys in environment variables.
4. Store only env-var references in `workbench/settings.local.json`, for example:
   - `siliconflow_api_key_env=WORKBENCH_SILICONFLOW_API_KEY`
5. Use external gateway-based key management when key rotation, history, or quota visibility matters.
6. From the repository root, run `python my-ppt-skill/scripts/scan_secrets.py --repo-root .` before claiming release-facing readiness. From `my-ppt-skill/`, use `python scripts/scan_secrets.py --repo-root ..`.

## Secret Persistence Policy

Allowed:

1. Shell/session environment variables.
2. Env-ref field names inside local settings files.
3. External key gateways such as LiteLLM Proxy.

Disallowed:

1. Plaintext keys inside `workbench/settings.local.json`.
2. Plaintext keys inside repo docs, examples, tests, or fixtures unless explicitly marked as scanner allowlisted fixture data.
3. Copying provider keys into project artifacts under `my-ppt-skill/projects/`.

## What Must Exist Before Public Or Security-Sensitive Deployment

The following controls are still absent and are required before public, untrusted, or data-isolated deployment:

1. Authentication for every browser session.
2. Authorization and role separation for project actions and downloads.
3. Secret storage outside the local repo and shell profile.
4. Request logging and audit visibility.
5. TLS, session expiry, rate limiting, and deployment hardening.

## Verification

- Settings format check: `python -m pytest tests/public_smoke -q`
- Secret scan from repository root: `python my-ppt-skill/scripts/scan_secrets.py --repo-root .`
- Healthcheck: `python -m workbench.healthcheck`

## Evidence

- `workbench/README.md`
- `docs/first-run-checklist.md`
