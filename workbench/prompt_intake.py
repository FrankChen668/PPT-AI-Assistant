from __future__ import annotations

from dataclasses import dataclass, field
import re

SUBMISSION_PROMPT_CHAR_LIMIT = 8000


RAW_INSTRUCTION_MARKERS = (
    "请只生成",
    "不要生成其他页面",
    "不要补充上下页",
    "不要输出整套 PPT",
)

NON_CONTENT_SECTION_LABELS = (
    "目标产物",
    "必须重复遵守的视觉风格",
    "视觉风格",
    "风格要求",
    "使用场景",
    "目标受众",
    "设计要求",
)


@dataclass(frozen=True)
class PromptIntake:
    title: str
    page_type_hint: str = ""
    screen_copy: list[str] = field(default_factory=list)
    conclusion: str = ""
    style_constraints: dict[str, str] = field(default_factory=dict)
    forbidden_actions: list[str] = field(default_factory=list)
    raw_prompt: str = ""


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _has_meaningful_text(text: str) -> bool:
    return bool(re.search(r"[\w\u4e00-\u9fff]", str(text or "")))


def normalize_submission_prompt(text: str, limit: int = SUBMISSION_PROMPT_CHAR_LIMIT) -> str:
    """Trim user input at submit time without destroying their formatting."""
    clean = str(text or "").strip()
    return clean[:limit].rstrip()


def _first_sentence(text: str) -> str:
    candidate = re.split(r"[。！？!?；;\n]", str(text or ""), maxsplit=1)[0]
    return candidate.strip(" ：:，,。.-_")


def make_user_task_title(prompt: str, fallback: str = "新建 PPT 任务") -> str:
    clean = normalize_submission_prompt(prompt)
    if not clean:
        return fallback

    quoted = re.search(r"[《“\"](?P<title>[^》”\"\n]{2,80})[》”\"]", clean)
    if quoted:
        return quoted.group("title").strip()[:40]

    labeled = re.search(r"(?:^|[【\s])(?:标题|主标题|上屏标题)[】:：]\s*(?P<title>[^。；;，,\n]{2,80})", clean)
    if labeled:
        return labeled.group("title").strip()[:40]

    simplified = re.sub(r"^请(?:帮我)?(?:只)?生成\s*\d*\s*页?\s*PPT[：:，,\s]*", "", clean, flags=re.I)
    simplified = re.sub(r"^生成\s*\d*\s*页?\s*PPT[：:，,\s]*", "", simplified, flags=re.I)
    simplified = re.sub(r"^PPT[：:，,\s]*", "", simplified, flags=re.I)
    simplified = re.sub(r"【[^】]{1,24}】", " ", simplified)
    title = _first_sentence(_normalize_whitespace(simplified))
    return (title[:34].rstrip(" ：:，,。.-_") or fallback)


def _extract_title(title: str, prompt: str) -> str:
    explicit = str(title or "").strip()
    match = re.search(r"[《\"](?P<title>[^》\"\n]{3,100})[》\"]", prompt)
    if match:
        quoted = _normalize_whitespace(match.group("title"))
        if quoted:
            return quoted[:100]
    labeled = _extract_labeled(prompt, ("上屏标题", "主标题", "标题"))
    if labeled:
        return labeled[:100]
    return explicit[:100]


def _extract_labeled(text: str, labels: tuple[str, ...]) -> str:
    source = str(text or "")
    for label in labels:
        pattern = rf"^[ \t\-•]*{re.escape(label)}[：:]\s*(?P<value>.+)$"
        matched = re.search(pattern, source, re.M)
        if matched:
            return _normalize_whitespace(matched.group("value"))
    return ""


def _extract_bracket_section(text: str, labels: tuple[str, ...]) -> str:
    source = str(text or "")
    for label in labels:
        block = re.search(rf"【[^】]*{re.escape(label)}[^】]*】(?P<body>.*?)(?=\n\s*【|\Z)", source, re.S)
        if block:
            value = block.group("body").strip()
            if value:
                return value
        inline = re.search(rf"【[^】]*{re.escape(label)}[^】]*】\s*(?P<body>.+)$", source, re.M)
        if inline:
            value = inline.group("body").strip()
            if value:
                return value
    return ""


def _extract_screen_copy(text: str) -> list[str]:
    explicit = _extract_bracket_section(text, ("上屏内容", "页面文案", "必须使用的页面文案"))
    scoped = explicit or _strip_raw_instructions(text)
    lines: list[str] = []
    for raw_line in scoped.splitlines():
        line = raw_line.strip()
        if not line or (line.startswith("【") and line.endswith("】")):
            continue
        if any(marker in line for marker in RAW_INSTRUCTION_MARKERS):
            continue
        line = re.sub(r"^[\-•]\s*", "", line)
        line = line.replace("主标题：", "上屏标题：")
        line = _normalize_whitespace(line)
        if not line:
            continue
        lines.append(line)
    if lines:
        return lines
    stripped = _strip_raw_instructions(scoped)
    return [stripped] if stripped else []


def _extract_style_constraints(text: str) -> dict[str, str]:
    source = str(text or "")
    mapping: dict[str, str] = {}
    for label in ("主色调", "辅助色", "背景色", "页面类型", "页类型"):
        value = _extract_labeled(source, (label,))
        if value:
            mapping[label] = value
    return mapping


def _strip_raw_instructions(text: str) -> str:
    source = str(text or "")
    source = _remove_non_content_sections(source)
    source = re.sub(r"^\s*\d+\s*页\s*PPT[：:]\s*P?\d*\s*[《\"][^》\"\n]{2,120}[》\"]\s*[。，,.、]*", "", source)
    source = re.sub(r"^\s*PPT[：:]\s*P?\d*\s*[《\"][^》\"\n]{2,120}[》\"]\s*[。，,.、]*", "", source, flags=re.I)
    cleaned_lines: list[str] = []
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(marker in line for marker in RAW_INSTRUCTION_MARKERS):
            continue
        if re.match(r"^[\-•]?\s*页面类型[：:]", line):
            continue
        if re.match(r"^[\-•]?\s*(主色调|辅助色|背景色)[：:]", line):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines).strip()
    if not cleaned:
        cleaned = source.strip()
    for marker in RAW_INSTRUCTION_MARKERS:
        cleaned = cleaned.replace(marker, "")
    cleaned = re.sub(r"^\s*\d+\s*页\s*PPT[：:]\s*P?\d*\s*[《\"][^》\"\n]{2,120}[》\"]\s*[。，,.、]*", "", cleaned)
    cleaned = re.sub(r"^\s*PPT[：:]\s*P?\d*\s*[《\"][^》\"\n]{2,120}[》\"]\s*[。，,.、]*", "", cleaned, flags=re.I)
    cleaned = _normalize_whitespace(cleaned)
    return cleaned if _has_meaningful_text(cleaned) else ""


def _remove_non_content_sections(text: str) -> str:
    cleaned = str(text or "")
    for label in NON_CONTENT_SECTION_LABELS:
        cleaned = re.sub(rf"【[^】]*{re.escape(label)}[^】]*】.*?(?=\s*【|\Z)", " ", cleaned, flags=re.S)
        cleaned = re.sub(rf"[\-•]?\s*{re.escape(label)}[：:].*?(?=\s+[\-•]\s*[\u4e00-\u9fff]{{2,12}}[：:]|\s*【|\Z)", " ", cleaned)
    return cleaned


def normalize_prompt_intake(title: str, prompt: str) -> PromptIntake:
    raw = str(prompt or "").strip()
    clean_title = _extract_title(title, raw)
    page_type_hint = _extract_labeled(raw, ("页面类型", "页类型"))
    conclusion = _extract_bracket_section(raw, ("底部结论", "核心结论", "核心判断"))
    screen_copy = _extract_screen_copy(raw)
    style_constraints = _extract_style_constraints(raw)
    forbidden = [marker for marker in RAW_INSTRUCTION_MARKERS if marker in raw]
    return PromptIntake(
        title=clean_title,
        page_type_hint=page_type_hint,
        screen_copy=screen_copy,
        conclusion=conclusion,
        style_constraints=style_constraints,
        forbidden_actions=forbidden,
        raw_prompt=raw,
    )


def compact_for_blueprint(intake: PromptIntake, *, body_limit: int, support_limit: int) -> dict[str, str]:
    body_source = "\n".join(item for item in intake.screen_copy if item).strip()
    if not body_source:
        body_source = _strip_raw_instructions(intake.raw_prompt)
    if not _has_meaningful_text(body_source):
        body_source = intake.title
    support = intake.conclusion.strip() or body_source
    return {
        "headline": intake.title[:100],
        "body": body_source[:body_limit].rstrip(),
        "statement": intake.title[:100],
        "support": support[:support_limit].rstrip(),
    }
