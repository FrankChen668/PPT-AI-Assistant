#!/usr/bin/env python3
"""Layered engineering quality gate helpers.

Use this script to separate a fast blocking core gate from full-repo advisory scans.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
CORE_RUFF_FILES = [
    "scripts/build_project.py",
    "scripts/validate_layouts_index.py",
    "scripts/ppt_master/project_manager.py",
    "tests/test_pipeline_smoke.py",
    "tests/test_project_manager.py",
]
CORE_MYPY_FILES = [
    "scripts/build_project.py",
    "scripts/validate_layouts_index.py",
    "scripts/ppt_master/project_manager.py",
]
RELEASE_CHECKS = [
    "scripts/check_template_entrypoints.py",
    "scripts/check_template_ssot_consistency.py",
    "scripts/check_docs_quality.py",
    "scripts/check_visual_baseline.py",
]
# AGENTS.md 导出禁令 1-2：禁止为导出安装/使用 pptxgenjs。仓库内出现引用它的 Node 依赖清单即阻断。
FORBIDDEN_EXPORT_DEPENDENCY = "pptxgenjs"
NODE_MANIFEST_NAMES = ("package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml")


def _run(cmd: list[str]) -> int:
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    return proc.returncode


def _git_output(args: list[str]) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _normalize_repo_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    if normalized.startswith("my-ppt-skill/"):
        return normalized[len("my-ppt-skill/") :]
    return normalized


def _active_python_files() -> list[str]:
    tracked = _git_output(["diff", "--name-only", "HEAD"])
    untracked = _git_output(["ls-files", "--others", "--exclude-standard"])
    candidates = {_normalize_repo_path(path) for path in tracked + untracked}
    allowed_prefixes = ("scripts/", "tests/")
    files = sorted(
        path
        for path in candidates
        if path.endswith(".py") and path.startswith(allowed_prefixes) and (ROOT / path).exists()
    )
    return files


def _mypy_targets_for(files: list[str]) -> list[str]:
    return [path for path in files if path.startswith("scripts/")]


def _node_manifest_paths() -> list[str]:
    tracked = _git_output(["ls-files"])
    untracked = _git_output(["ls-files", "--others", "--exclude-standard"])
    candidates = sorted({path.replace("\\", "/") for path in tracked + untracked})
    return [path for path in candidates if path.rsplit("/", 1)[-1] in NODE_MANIFEST_NAMES]


def _forbidden_export_dependency_findings(manifest_paths: list[str]) -> list[str]:
    findings: list[str] = []
    for rel_path in manifest_paths:
        manifest = REPO_ROOT / rel_path
        if not manifest.is_file():
            continue
        text = manifest.read_text(encoding="utf-8", errors="replace")
        if FORBIDDEN_EXPORT_DEPENDENCY in text:
            findings.append(rel_path)
    return findings


def _check_forbidden_export_toolchain() -> int:
    findings = _forbidden_export_dependency_findings(_node_manifest_paths())
    if not findings:
        return 0
    print(f"Forbidden export toolchain dependency `{FORBIDDEN_EXPORT_DEPENDENCY}` detected (AGENTS.md export ban 1-2):")
    for path in findings:
        print(f"- {path}")
    print(
        "Remove the Node manifest or the dependency; "
        "exports must go through build_project.py --phase finalize --skip-render."
    )
    return 1


def _run_ruff(files: list[str]) -> int:
    if not files:
        return 0
    return _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            *files,
            "--ignore",
            "E501,E402,I001",
        ]
    )


def _run_mypy(files: list[str]) -> int:
    if not files:
        return 0
    return _run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--follow-imports=skip",
            "--disable-error-code",
            "unused-ignore",
            *files,
        ]
    )


def run_core_gate() -> int:
    active_files = _active_python_files()
    if active_files:
        print("Active Python files (blocking):")
        for path in active_files:
            print(f"- {path}")
    else:
        print("Active Python files (blocking): none")

    core_ruff_files = sorted(set(CORE_RUFF_FILES + active_files))
    core_mypy_files = sorted(set(CORE_MYPY_FILES + _mypy_targets_for(active_files)))
    rc = 0
    rc |= _run_ruff(core_ruff_files)
    rc |= _run_mypy(core_mypy_files)
    rc |= _run([sys.executable, "scripts/check_mainflow_imports.py"])
    rc |= _check_forbidden_export_toolchain()
    return 1 if rc else 0


def run_release_gate() -> int:
    rc = run_core_gate()
    for check in RELEASE_CHECKS:
        rc |= _run([sys.executable, check])
    return 1 if rc else 0


def run_full_gate(strict: bool) -> int:
    results = [
        _run([sys.executable, "-m", "ruff", "check", "."]),
        _run([sys.executable, "-m", "mypy", "scripts"]),
    ]
    failed = any(code != 0 for code in results)
    if failed and not strict:
        print("Full gate has findings (advisory mode).")
        return 0
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run layered quality gates.")
    parser.add_argument(
        "gate",
        choices=("core", "release", "full"),
        help="core: blocking gate; release: delivery gate; full: advisory debt radar (non-blocking by default).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="For full gate only: fail on findings instead of advisory pass-through.",
    )
    args = parser.parse_args(argv)

    if args.gate == "core":
        return run_core_gate()
    if args.gate == "release":
        return run_release_gate()
    return run_full_gate(strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
