# Security Local Boundary

Updated: 2026-08-27
Status: active

## Purpose

Define what is safe and supported for local use today, what data leaves the machine during model calls, and what is explicitly out of scope until stronger auth and deployment controls exist.

## Current Security Boundary

Supported boundary:

1. Workbench usage on the host computer by default (`127.0.0.1`).
2. Explicit opt-in sharing with 3-4 trusted colleagues on the same office private LAN.
3. Secrets injected through environment variables or env-ref fields in the local `settings.local.json` file under the Workbench directory.
4. Local repo execution by a trusted operator who can read project files and reports.

Not supported as a secure deployment model:

1. Exposing Workbench on a public network, guest Wi-Fi, port-forwarded router, or other untrusted network.
2. Treating office sharing as a secure multi-user system; there is no authentication, authorization, or data isolation.
3. Persisting plaintext provider secrets in repo-tracked files or local settings files.
4. Treating local browser access as a substitute for session auth, tenant isolation, or audit logging.

## Network Defaults and LAN Opt-in

1. Normal Workbench package/launcher runtime defaults to `WORKBENCH_HOST=127.0.0.1` and is reachable only from the host computer.
2. Bind to `0.0.0.0` only when a trusted office private LAN needs shared access, by explicitly setting `WORKBENCH_HOST=0.0.0.0`.
3. For LAN sharing, allow the Workbench TCP port only on the Windows `Private` firewall profile.
4. Never expose the current Workbench directly to the public internet.

## Provider Data Boundary

Local-first does **not** mean model generation is offline.

- Project files, task state, generated SVG/PPTX and local configuration are stored on the host by default.
- When a third-party model Provider is used, prompts and the source/material content needed for generation are transmitted to that configured Provider.
- This project does not control or guarantee Provider-side storage, logging, training, retention, residency, or deletion behavior. Those rules are governed by the Provider and the user's account/contract with it.
- Do not send material to a Provider unless its data-handling terms are acceptable for that material.

## Secret Persistence Policy

Allowed:

1. Shell/session environment variables.
2. Env-ref field names inside local settings files.
3. External key gateways such as LiteLLM Proxy.

Disallowed:

1. Plaintext keys inside the local `settings.local.json` file under the Workbench directory.
2. Plaintext keys inside repo docs, examples, tests, or fixtures unless explicitly marked as scanner allowlisted fixture data.
3. Copying provider keys into project artifacts under `my-ppt-skill/projects/`.

## Mandatory Local Rules

1. Keep the default localhost listener unless LAN sharing is explicitly needed.
2. Keep API keys in environment variables.
3. Store only env-var references in the local `settings.local.json` file under the Workbench directory, for example:
   - `siliconflow_api_key_env=WORKBENCH_SILICONFLOW_API_KEY`
4. Use external gateway-based key management when key rotation, history, or quota visibility matters.
5. From the repository root, run `python my-ppt-skill/scripts/scan_secrets.py --repo-root .` before claiming release-facing readiness. From `my-ppt-skill/`, use `python scripts/scan_secrets.py --repo-root ..`.

## What Must Exist Before Public Or Security-Sensitive Deployment

The following controls are still absent and are required before public, untrusted, or data-isolated deployment:

1. Authentication for every browser session.
2. Authorization and role separation for project actions and downloads.
3. Secret storage outside the local repo and shell profile.
4. Request logging and audit visibility.
5. TLS, session expiry, rate limiting, and deployment hardening.

## Verification

- Settings/public smoke: `python -m pytest tests/public_smoke -q`
- Workbench secure-default regression: `python -m pytest workbench/tests/test_secure_default_host.py -q`
- Secret scan from repository root: `python my-ppt-skill/scripts/scan_secrets.py --repo-root .`
- Healthcheck: `python -m workbench.healthcheck`

## Evidence

- `workbench/README.md`
- `docs/first-run-checklist.md`
