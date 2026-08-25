from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from workbench.generation_settings import load_generation_config

MIN_PYTHON = (3, 11)
PROVIDER_PLAINTEXT_FIELDS = (
    "google_api_key",
    "google_api_keys",
    "xiaomi_api_key",
    "xiaomi_api_keys",
    "siliconflow_api_key",
    "siliconflow_api_keys",
    "deepseek_api_key",
    "deepseek_api_keys",
)
PROVIDER_ENV_FIELDS = (
    "google_api_key_env",
    "google_api_keys_env",
    "xiaomi_api_key_env",
    "xiaomi_api_keys_env",
    "siliconflow_api_key_env",
    "siliconflow_api_keys_env",
    "deepseek_api_key_env",
    "deepseek_api_keys_env",
)


def detect_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _check_python() -> dict[str, Any]:
    current = sys.version_info[:3]
    status = "pass" if current >= MIN_PYTHON else "fail"
    return {
        "status": status,
        "detail": f"python={current[0]}.{current[1]}.{current[2]} minimum={MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
    }


def _check_required_paths(repo_root: Path) -> dict[str, Any]:
    required = [
        repo_root / "workbench" / "__init__.py",
        repo_root / "workbench" / "server.py",
        repo_root / "my-ppt-skill" / "scripts" / "build_project.py",
        repo_root / "my-ppt-skill" / "scripts" / "run_fixed_baseline.py",
    ]
    missing = [str(path.relative_to(repo_root)) for path in required if not path.exists()]
    if missing:
        return {"status": "fail", "detail": f"missing required paths: {', '.join(missing)}"}
    return {"status": "pass", "detail": "required repo paths present"}


def _read_settings(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        return {}
    return json.loads(settings_path.read_text(encoding="utf-8-sig"))


def _has_plaintext_secret(value: object) -> bool:
    if isinstance(value, list):
        return any(str(item or "").strip() for item in value)
    return bool(str(value or "").strip())


def _check_settings(repo_root: Path) -> dict[str, Any]:
    settings_path = repo_root / "workbench" / "settings.local.json"
    if not settings_path.exists():
        return {
            "status": "pass",
            "detail": "settings.local.json not found; dry-run remains supported without local secrets",
        }
    payload = _read_settings(settings_path)
    plaintext_fields = [field for field in PROVIDER_PLAINTEXT_FIELDS if _has_plaintext_secret(payload.get(field))]
    if plaintext_fields:
        return {
            "status": "fail",
            "detail": f"plaintext secret fields detected: {', '.join(plaintext_fields)}",
        }
    try:
        load_generation_config(settings_path)
    except ValueError as exc:
        return {
            "status": "fail",
            "detail": str(exc),
        }
    provider = str(payload.get("generation_provider") or payload.get("provider") or "google").strip().lower()
    if provider == "gemini":
        provider = "google"
    env_fields = [
        field
        for field in PROVIDER_ENV_FIELDS
        if field.startswith(f"{provider}_") and str(payload.get(field) or "").strip()
    ]
    if env_fields:
        missing_env_fields = [
            f"{field}={str(payload.get(field)).strip()}"
            for field in env_fields
            if not os.environ.get(str(payload.get(field)).strip(), "").strip()
        ]
        if missing_env_fields:
            return {
                "status": "fail",
                "detail": f"configured env refs missing values: {', '.join(missing_env_fields)}",
            }
        return {"status": "pass", "detail": f"env-ref secret fields configured: {', '.join(env_fields)}"}
    return {
        "status": "pass",
        "detail": "no plaintext secrets found; local settings can remain unset for dry-run",
    }


def run_healthcheck(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root.resolve() if repo_root else detect_repo_root()
    checks = {
        "python": _check_python(),
        "paths": _check_required_paths(root),
        "settings": _check_settings(root),
    }
    failed = sum(1 for item in checks.values() if item["status"] == "fail")
    passed = sum(1 for item in checks.values() if item["status"] == "pass")
    status = "fail" if failed else "pass"
    return {
        "status": status,
        "repo_root": str(root),
        "checks": checks,
        "summary": {
            "passed": passed,
            "failed": failed,
            "total": len(checks),
        },
    }


def main() -> int:
    result = run_healthcheck()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
