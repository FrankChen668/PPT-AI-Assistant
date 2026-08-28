#!/usr/bin/env python3
"""Validate documentation encoding and command/path consistency."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from layout_contracts import layout_tags
from layout_renderers import LayoutRenderer
from render_theme import Theme
from validate_layouts_index import validate_layouts_index

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent
LAYOUT_DSL_PATH = ROOT / "references" / "layout-dsl.md"
LAYOUTS_INDEX_PATH = ROOT / "ppt-ai-core" / "templates" / "layouts" / "layouts_index.json"
LAYOUTS_DIR = ROOT / "ppt-ai-core" / "templates" / "layouts"

LEGACY_INDEX_PATH = "my-ppt-skill/templates/ppt-master/layouts/layouts_index.json"
RUNTIME_INDEX_PATH = "my-ppt-skill/ppt-ai-core/templates/layouts/layouts_index.json"
RUNTIME_INDEX_PATH_ALT = "ppt-ai-core/templates/layouts/layouts_index.json"
DOC_COMMAND_MIN_SUCCESS_RATE = 0.95
DOC_SMOKE_COMMANDS: list[list[str]] = [
    [sys.executable, "scripts/ppt_master/project_manager.py", "list-templates"],
    [sys.executable, "scripts/build_project.py", "--help"],
    [sys.executable, "scripts/qa_project.py", "--help"],
]


@dataclass
class DocIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class CountPattern:
    pattern: str
    label: str


LAYOUT_DSL_SECTION_RE = re.compile(r"^##\s+(?P<num>\d+)\.\s+(?P<tag>[A-Za-z0-9\-]+)\s*$", re.MULTILINE)
MOJIBAKE_TOKENS = ("闁", "锟", "鈥", "銆", "�", "???")

LAYOUT_COUNT_PATTERNS: dict[Path, list[CountPattern]] = {
    REPO_ROOT / "AI-PPT-Architecture.md": [
        CountPattern(r"layout-dsl\.md\s+#\s*(\d+)\s+种\s+layout_tag", "layout-dsl catalog count"),
        CountPattern(r"完全一致\*\*（(\d+)\s+种，见第五节）", "blueprint contract count"),
        CountPattern(r"## 五、Layout DSL 库（(\d+)\s+种）", "layout library section count"),
        CountPattern(r"☑\s+(\d+)\s+布局几何与契约", "milestone layout count"),
        CountPattern(r"；(\d+)\s+标签\s+\+\s+契约为规格/QA", "executor qa contract count"),
    ],
}


def _decode_utf8(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def check_utf8_docs(paths: list[Path]) -> list[DocIssue]:
    issues: list[DocIssue] = []
    for path in paths:
        if not path.exists():
            issues.append(DocIssue("missing-doc", str(path), "Required documentation file is missing."))
            continue
        try:
            _decode_utf8(path)
        except UnicodeDecodeError as exc:
            issues.append(
                DocIssue(
                    "invalid-utf8",
                    str(path),
                    f"File is not valid UTF-8: {exc}",
                )
            )
    return issues


def _is_likely_mojibake(text: str) -> bool:
    if not text:
        return False
    hit_count = sum(text.count(token) for token in MOJIBAKE_TOKENS)
    if hit_count == 0:
        return False
    return hit_count >= 4 and (hit_count / max(1, len(text))) >= 0.01


def check_mojibake_docs(paths: list[Path]) -> list[DocIssue]:
    issues: list[DocIssue] = []
    for path in paths:
        if not path.exists():
            issues.append(DocIssue("missing-doc", str(path), "Required documentation file is missing."))
            continue
        try:
            content = _decode_utf8(path)
        except UnicodeDecodeError:
            continue
        if _is_likely_mojibake(content):
            issues.append(
                DocIssue(
                    "likely-mojibake",
                    str(path),
                    "Document appears to contain mojibake/garbled text. Verify encoding/source text integrity.",
                )
            )
    return issues


def check_index_path_consistency(paths: list[Path]) -> list[DocIssue]:
    issues: list[DocIssue] = []
    for path in paths:
        if not path.exists():
            issues.append(DocIssue("missing-doc", str(path), "Required documentation file is missing."))
            continue
        content = _decode_utf8(path)
        if LEGACY_INDEX_PATH in content:
            issues.append(
                DocIssue(
                    "legacy-index-path",
                    str(path),
                    f"Legacy template index path found; use {RUNTIME_INDEX_PATH}.",
                )
            )
        if RUNTIME_INDEX_PATH not in content and RUNTIME_INDEX_PATH_ALT not in content:
            issues.append(
                DocIssue(
                    "missing-runtime-index-path",
                    str(path),
                    (
                        "Runtime template index path is missing: "
                        f"{RUNTIME_INDEX_PATH} (or {RUNTIME_INDEX_PATH_ALT} for skill-relative docs)"
                    ),
                )
            )
    return issues


def check_layout_dsl_contract_sync(layout_dsl_path: Path, contract_tags: list[str]) -> list[DocIssue]:
    issues: list[DocIssue] = []
    if not layout_dsl_path.exists():
        return [DocIssue("missing-doc", str(layout_dsl_path), "Required layout DSL file is missing.")]

    headings = [
        (int(match.group("num")), match.group("tag"))
        for match in LAYOUT_DSL_SECTION_RE.finditer(_decode_utf8(layout_dsl_path))
    ]
    if len(headings) != len(contract_tags):
        issues.append(
            DocIssue(
                "layout-dsl-section-count-mismatch",
                str(layout_dsl_path),
                f"layout-dsl headings={len(headings)} but runtime contracts={len(contract_tags)}.",
            )
        )

    expected_numbers = list(range(1, len(headings) + 1))
    actual_numbers = [num for num, _ in headings]
    if actual_numbers != expected_numbers:
        issues.append(
            DocIssue(
                "layout-dsl-heading-sequence",
                str(layout_dsl_path),
                f"layout-dsl heading numbers are not sequential: {actual_numbers}.",
            )
        )

    actual_tags = [tag for _, tag in headings]
    if set(actual_tags) != set(contract_tags):
        missing = sorted(set(contract_tags) - set(actual_tags))
        extra = sorted(set(actual_tags) - set(contract_tags))
        issues.append(
            DocIssue(
                "layout-dsl-tag-set-mismatch",
                str(layout_dsl_path),
                f"layout-dsl tags differ from runtime contracts. missing={missing or '-'} extra={extra or '-'}",
            )
        )
    elif actual_tags != contract_tags:
        issues.append(
            DocIssue(
                "layout-dsl-tag-order-mismatch",
                str(layout_dsl_path),
                "layout-dsl heading order does not match runtime layout contract order.",
            )
        )

    return issues


def check_renderer_contract_sync(contract_tags: set[str], renderer_tags: set[str]) -> list[DocIssue]:
    issues: list[DocIssue] = []
    for tag in sorted(contract_tags - renderer_tags):
        issues.append(
            DocIssue(
                "layout-contract-without-renderer",
                "scripts/layout_contracts.py",
                f"{tag} has a layout contract but no registered renderer.",
            )
        )
    for tag in sorted(renderer_tags - contract_tags):
        issues.append(
            DocIssue(
                "renderer-without-layout-contract",
                "scripts/layout_renderers.py",
                f"{tag} has a registered renderer but no layout contract.",
            )
        )
    return issues


def check_layout_count_mentions(
    patterns_by_path: dict[Path, list[CountPattern]], expected_count: int
) -> list[DocIssue]:
    issues: list[DocIssue] = []
    for path, patterns in patterns_by_path.items():
        if not path.exists():
            issues.append(DocIssue("missing-doc", str(path), "Required documentation file is missing."))
            continue
        content = _decode_utf8(path)
        for pattern in patterns:
            matches = list(re.finditer(pattern.pattern, content))
            if not matches:
                issues.append(
                    DocIssue(
                        "layout-count-pattern-missing",
                        str(path),
                        f"Missing expected layout count declaration for {pattern.label}.",
                    )
                )
                continue
            for match in matches:
                declared = int(match.group(1))
                if declared != expected_count:
                    issues.append(
                        DocIssue(
                            "layout-count-mismatch",
                            str(path),
                            f"{pattern.label} declares {declared}, expected {expected_count}.",
                        )
                    )
    return issues


def validate_runtime_layout_index() -> list[DocIssue]:
    return [
        DocIssue(issue.code, issue.path, issue.message)
        for issue in validate_layouts_index(LAYOUTS_INDEX_PATH, LAYOUTS_DIR)
    ]


def run_doc_command_smoke(
    commands: list[list[str]] | None = None,
    min_success_rate: float = DOC_COMMAND_MIN_SUCCESS_RATE,
) -> list[DocIssue]:
    command_list = commands or DOC_SMOKE_COMMANDS
    if not command_list:
        return []

    issues: list[DocIssue] = []
    succeeded = 0
    for cmd in command_list:
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if result.returncode == 0:
            succeeded += 1
            continue
        issues.append(
            DocIssue(
                "doc-command-failed",
                " ".join(cmd),
                f"Command failed with exit={result.returncode}: {(result.stderr or result.stdout).strip()}",
            )
        )

    success_rate = succeeded / len(command_list)
    if success_rate < min_success_rate:
        issues.append(
            DocIssue(
                "doc-command-success-rate-low",
                "docs-command-smoke",
                (
                    f"Command smoke success rate {success_rate:.2%} is below target "
                    f"{min_success_rate:.0%} ({succeeded}/{len(command_list)})."
                ),
            )
        )
    return issues


def check_export_contract_consistency(paths: list[Path]) -> list[DocIssue]:
    issues: list[DocIssue] = []
    required_phrase = "--phase finalize --skip-render"
    required_recovery = "doctor -> authoring gate -> finalize gate"
    required_forbidden = "pptxgenjs"
    for path in paths:
        if not path.exists():
            issues.append(DocIssue("missing-doc", str(path), "Required documentation file is missing."))
            continue
        content = _decode_utf8(path)
        if required_phrase not in content:
            issues.append(
                DocIssue(
                    "missing-finalize-skip-render-contract",
                    str(path),
                    "Expected finalize --skip-render default contract is missing.",
                )
            )
        if required_recovery not in content:
            issues.append(
                DocIssue(
                    "missing-recovery-sequence-contract",
                    str(path),
                    "Expected fixed recovery sequence `doctor -> authoring gate -> finalize gate` is missing.",
                )
            )
        if required_forbidden not in content:
            issues.append(
                DocIssue(
                    "missing-forbidden-toolchain-contract",
                    str(path),
                    "Expected forbidden-toolchain marker `pptxgenjs` is missing.",
                )
            )
    return issues


def check_environment_verification_contract(path: Path) -> list[DocIssue]:
    if not path.exists():
        return [DocIssue("missing-doc", str(path), "Required documentation file is missing.")]
    content = _decode_utf8(path)
    issues: list[DocIssue] = []
    if "verify_environment_baseline.py" not in content:
        issues.append(
            DocIssue(
                "missing-environment-verification-command",
                str(path),
                "Expected `verify_environment_baseline.py` command is missing.",
            )
        )
    if "environment-baseline-verification-" not in content:
        issues.append(
            DocIssue(
                "missing-environment-verification-report-contract",
                str(path),
                "Expected environment verification report path contract is missing.",
            )
        )
    return issues


def check_visual_recipe_screenshot_contract(path: Path, min_sections: int = 6) -> list[DocIssue]:
    if not path.exists():
        return [DocIssue("missing-doc", str(path), "Required documentation file is missing.")]
    content = _decode_utf8(path)
    section_count = len(re.findall(r"^##\s+\d+\)", content, flags=re.MULTILINE))
    screenshot_count = content.count("Screenshot standard:")
    issues: list[DocIssue] = []
    if section_count < min_sections:
        issues.append(
            DocIssue(
                "insufficient-visual-recipe-sections",
                str(path),
                f"Expected at least {min_sections} visual recipe sections, got {section_count}.",
            )
        )
    if screenshot_count < min_sections:
        issues.append(
            DocIssue(
                "missing-visual-recipe-screenshot-standard",
                str(path),
                (
                    "Each visual recipe section should include a screenshot standard. "
                    f"Found {screenshot_count}, expected at least {min_sections}."
                ),
            )
        )
    return issues


def _format_issues(issues: list[DocIssue]) -> str:
    lines = ["Documentation quality check failed:"]
    for issue in issues:
        lines.append(f"- [{issue.code}] {issue.path}: {issue.message}")
    return "\n".join(lines)


def main() -> int:
    utf8_targets = [
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "AI-PPT-Architecture.md",
        REPO_ROOT / "TECHNICAL_ROADMAP.md",
        REPO_ROOT / "docs" / "architecture-ssot-index.md",
        REPO_ROOT / "docs" / "export-runbook.md",
        REPO_ROOT / "docs" / "environment-baseline.md",
        REPO_ROOT / "docs" / "exporter-capability-matrix.md",
        REPO_ROOT / "docs" / "visual-quality-contact-sheet-baseline-2026-05-03.md",
        REPO_ROOT / "docs" / "complex-page-capability-pack-and-rubric.md",
        REPO_ROOT / "docs" / "quality-threshold-governance.md",
        ROOT / "SKILL.md",
        ROOT / "references" / "visual-recipes.md",
        ROOT / "references" / "design-guidelines.md",
        ROOT / "references" / "strategist-checklist.md",
    ]
    index_targets = [
        REPO_ROOT / "AGENTS.md",
        ROOT / "references" / "strategist-checklist.md",
    ]

    issues: list[DocIssue] = []
    issues.extend(check_utf8_docs(utf8_targets))
    issues.extend(check_mojibake_docs(utf8_targets))
    issues.extend(check_index_path_consistency(index_targets))
    contract_tags = layout_tags()
    renderer_tags = set(LayoutRenderer(Theme()).registry)
    issues.extend(check_layout_dsl_contract_sync(LAYOUT_DSL_PATH, contract_tags))
    issues.extend(check_renderer_contract_sync(set(contract_tags), renderer_tags))
    issues.extend(check_layout_count_mentions(LAYOUT_COUNT_PATTERNS, expected_count=len(contract_tags)))
    issues.extend(validate_runtime_layout_index())
    issues.extend(run_doc_command_smoke())
    issues.extend(check_environment_verification_contract(REPO_ROOT / "docs" / "environment-baseline.md"))
    issues.extend(check_visual_recipe_screenshot_contract(ROOT / "references" / "visual-recipes.md"))
    issues.extend(
        check_export_contract_consistency(
            [
                REPO_ROOT / "AGENTS.md",
                REPO_ROOT / "docs" / "export-runbook.md",
                ROOT / "SKILL.md",
            ]
        )
    )

    if issues:
        print(_format_issues(issues), file=sys.stderr)
        return 1

    print("Docs quality check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())