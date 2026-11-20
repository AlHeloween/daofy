"""
Coding rules tool

Provides Delphi source code coding rules lookup, supporting section-by-section retrieval,
reducing token consumption and improving the AI Agent's rule compliance rate.
"""

import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from mcp.types import CallToolResult, TextContent

from src.mcp_resources import PUBLIC_RESOURCE_SPECS, resolve_resource_path

from ..utils.logger import get_logger

logger = get_logger(__name__)

# ── Section name mapping: short key → Markdown heading (## or ###) ──

SECTION_KEYS: Dict[str, str] = {
    "planning": "P0 前置计划与审查",
    "workflow": "工作流总览",
    "directory": "📁 目录约束",
    "env": "① 环境检查",
    "kb_search": "② KB 搜索（编码前必做）",
    "writing": "③ 写 Delphi 代码",
    "format": "④ 格式化",
    "compile": "⑤ 编译",
    "review_guide": "⑦ 代码审核",
    "cleanup": "⑥ 清理 & 验证",
    "review_detail": "审核",
    "kb_build": "知识库重建",
    "agent_rules": "Agent 操作硬规则",
    "human_collab": "人机协同 — 异常诊断与人工介入",
    "experience": "⑪ 经验保存 — 将知识沉淀到经验库",
    "maintenance": "⑫ 规则维护",
    "automation": "⚙ 自动化测试架构 — 感知·规划·执行·反馈循环",
    "ui-testing": "⑧ 自动化 UI 交互测试",
    "ui_layout": "UI 布局规范与审计",
    "console-testing": "⑨ 控制台程序交互验证",
    # shared cross-language sections
    "debugging": "异常诊断与调试（8.1–8.14 合集）",
    "multi_change": "多修改优先级排序",
    # Sub-sections within "③ Write Delphi code"
    "delphi_file_write_rule": "delphi_file 写入规则",
    "delphi_file_dirty_flag": "脏标记保护（v2026.06.12+）",
    "delphi_file_output_format": "紧凑输出格式（v2026.06.12+）",
    "delphi_file_usage_tips": "推荐做法",
    # Review sub-sections (### level)
    "consistency": "一致性",
    "completeness": "完整性",
    "resource_leak": "资源泄露",
    "delphi_specific": "Delphi 特有陷阱",
    "common_errors": "常见错误模式",
    "code_quality": "代码质量",
    "data_conversion": "数据转换",
    "safety": "安全",
    "performance": "性能",
}

LAZARUS_SECTION_KEYS: Dict[str, str] = {
    "planning": "P0 前置计划与审查",
    "workflow": "Lazarus/FPC 工作流总览",
    "env": "① 环境检查",
    "kb_search": "② 查 API（FPC 文档）",
    "writing": "③ 编码",
    "compile": "④ 编译",
    "review_guide": "⑤ 审核",
    "cleanup": "⑥ 清理",
    # Shared keys same as SECTION_KEYS
    "kb_build": "知识库重建",
    "agent_rules": "Agent 操作硬规则",
    "human_collab": "人机协同 — 异常诊断与人工介入",
    "experience": "⑪ 经验保存 — 将知识沉淀到经验库",
    "maintenance": "⑫ 规则维护",
    "automation": "⚙ 自动化测试架构 — 感知·规划·执行·反馈循环",
    "ui-testing": "⑧ 自动化 UI 交互测试",
    "console-testing": "⑨ 控制台程序交互验证",
    # shared cross-language sections
    "debugging": "异常诊断与调试（8.1–8.14 合集）",
    "multi_change": "多修改优先级排序",
    # Review sub-sections (### level, shared with Delphi)
    "consistency": "一致性",
    "completeness": "完整性",
    "resource_leak": "资源泄露",
    "common_errors": "常见错误模式",
    "code_quality": "代码质量",
    "safety": "安全",
    "performance": "性能",
}


def _get_section_keys(language: str) -> Dict[str, str]:
    """Return section key → heading mapping for the given language."""
    lang = (language or "delphi").lower().strip()
    if lang == "lazarus":
        return LAZARUS_SECTION_KEYS
    return SECTION_KEYS

SECTION_ALIASES: Dict[str, str] = {
    "kb-search": "kb_search",
    "kb-rebuild": "kb_build",
    "agent-rules": "agent_rules",
    "dir": "directory",
    "dirs": "directory",
    "目录": "directory",
    "human-collab": "human_collab",
    "review-guide": "review_guide",
    "review-detail": "review_detail",
    "resource-leak": "resource_leak",
    "delphi-specific": "delphi_specific",
    "common-errors": "common_errors",
    "code-quality": "code_quality",
    "data-conversion": "data_conversion",
    "delphi-file-rules": "delphi_file_write_rule",
    "delphi-file-write-rule": "delphi_file_write_rule",
    "delphi-file-dirty-flag": "delphi_file_dirty_flag",
    "delphi-file-output-format": "delphi_file_output_format",
    "delphi-file-usage-tips": "delphi_file_usage_tips",
    "delphi_file_rules": "delphi_file_write_rule",
    "ui_testing": "ui-testing",
    "ui-layout": "ui_layout",
    "layout": "ui_layout",
    "console_testing": "console-testing",
}


def _normalize_section_name(section_name: str) -> str:
    """Return the canonical section key accepted by SECTION_KEYS/META_SECTIONS."""
    return SECTION_ALIASES.get(section_name, section_name)


# Meta sections: return multiple related headings combined
META_SECTIONS: Dict[str, List[str]] = {
    "review": ["review_guide", "review_detail"],
    "coding": ["writing", "format", "compile"],
}

# Reverse mapping: heading → short key (for error hints) — built at runtime by _get_title_to_key(language)


def _get_title_to_key(language: str) -> Dict[str, str]:
    """Build reverse mapping: heading → section key for the given language."""
    keys = _get_section_keys(language)
    return {v: k for k, v in keys.items()}


CODING_RULES_DIR = Path(__file__).parent.parent / "resources" / "coding-rules"

LANGUAGE_NAMES: Dict[str, str] = {
    "delphi": "Delphi",
    "lazarus": "Lazarus/Free Pascal",
}


def _default_rules_candidates(language: str = "delphi") -> List[Path]:
    """Return built-in coding rule directories for the given language.

    Returns [shared_dir, language_dir] — shared rules first, language-specific
    rules second (language overrides shared on heading collision).
    Falls back to MCP resource path if directory structure doesn't exist.
    """
    candidates: List[Path] = []
    shared_dir = CODING_RULES_DIR / "shared"
    if shared_dir.is_dir():
        candidates.append(shared_dir)
    lang_dir = CODING_RULES_DIR / language
    if lang_dir.is_dir():
        candidates.append(lang_dir)
    if candidates:
        return candidates
    # Fallback: try the MCP resource path directly
    try:
        coding_rules = next(
            spec for spec in PUBLIC_RESOURCE_SPECS
            if spec.uri == "delphi://coding-rules"
        )
        path = resolve_resource_path(coding_rules)
        return [path] if path is not None else []
    except StopIteration:
        return []


def _read_first_existing_text(paths: List[Path], label: str) -> Tuple[str, Optional[Path]]:
    """Read the first existing UTF-8 text file from a candidate list.

    If the path is a directory, merge all .md files within it.
    If multiple directories are provided, merge ALL of them (not just the first).
    If a single file path is provided, read it directly.
    """
    parts: list[str] = []
    merged_path: Optional[Path] = None

    for path in paths:
        if not path.exists():
            continue
        # Directory mode: merge all .md files
        if path.is_dir():
            dir_parts: list[str] = []
            merged_paths = sorted(path.rglob("*.md"))
            for f in merged_paths:
                try:
                    dir_parts.append(f.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.error(f"Failed to read {label} sub-file: {f}: {str(e)}")
                    continue
            if dir_parts:
                merged = "\n\n".join(dir_parts)
                parts.append(merged)
                if merged_path is None:
                    merged_path = path
            continue
        # Single file mode
        try:
            text = path.read_text(encoding='utf-8')
            parts.append(text)
            if merged_path is None:
                merged_path = path
        except Exception as e:
            logger.error(f"Failed to read {label}: {path}: {str(e)}")
            continue

    if parts:
        return "\n\n".join(parts), merged_path
    return "", None


def _find_heading_ranges(lines: List[str]) -> Dict[str, Tuple[int, int]]:
    """Parse markdown line list, return mapping of {heading text: (start line, end line)}.

    The end line points to the line before the next same-level/higher-level heading; if there is no following heading, it points to the end.
    """
    # Collect all heading lines
    heading_pattern = re.compile(r'^(#{2,4})\s+(.+)$')
    headings: List[Tuple[int, str, int]] = []  # (level, title, line_index)

    for i, line in enumerate(lines):
        m = heading_pattern.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append((level, title, i))

    # Compute content range for each heading
    ranges: Dict[str, Tuple[int, int]] = {}
    for idx, (level, title, start) in enumerate(headings):
        end = len(lines)
        # Find the next same-level or higher-level heading (smaller number = higher level)
        for j in range(idx + 1, len(headings)):
            if headings[j][0] <= level:
                end = headings[j][2]
                break
        ranges[title] = (start, end)

    return ranges


def _strip_trailing_separator(text: str) -> str:
    """Remove redundant trailing --- separator lines."""
    return re.sub(r'\n---+\s*$', '', text)


def _extract_debugging_sections(content: str) -> Optional[str]:
    """Extract all ### level heading content (debugging collection).

    Files under shared/debugging/ all use ### level headings (e.g. ### 8.1 Human intervention trigger conditions),
    scattered throughout the merged rules. This function collects all 8.x numbered ### headings and their content,
    concatenated in original order and returned as a single collection.

    Only matches ### headings starting with "8." (debugging section numbers), filtering out other ### headings
    (such as ### sub-sections in writing/review/planning files).

    Args:
        content: Merged markdown content

    Returns:
        Full text of concatenated debugging sections; returns None if no matching headings
    """
    lines = content.split('\n')
    heading_pattern = re.compile(r'^###\s+(8\.(\d+))\s+(.+)$')
    # sections: (start_line, section_num_float, title, raw_heading_text)
    sections: List[Tuple[int, float, str, str]] = []

    for i, line in enumerate(lines):
        m = heading_pattern.match(line)
        if m:
            num_str = m.group(1)     # "8.1"
            num_float = float(m.group(2)) if m.group(2).isdigit() else 0.0
            # Actually let me keep the full number for proper sorting
            # 8.1 → 8.01, 8.10 → 8.10
            # Split "8.1" into (8, 1), "8.10" into (8, 10)
            parts_num = num_str.split('.')
            major = int(parts_num[0])
            minor = int(parts_num[1]) if len(parts_num) > 1 else 0
            numeric_key = major + minor / 100.0  # 8.01, 8.02, ..., 8.10, 8.11, ...
            sections.append((i, numeric_key, m.group(3).strip(), num_str))

    if not sections:
        return None

    # Sort by section number (8.1 < 8.2 < ... < 8.14)
    sections.sort(key=lambda s: s[1])

    parts: List[str] = []
    for start, num_key, title, raw_num in sections:
        # Find the next ### or higher-level (## / #) heading as end boundary
        # Note: debugging files have no ## separator between them, must use ^#{1,3} to match ### level
        end = len(lines)
        for j in range(start + 1, len(lines)):
            line = lines[j]
            # Stop at #/##/### headings (#### does not stop, preserves sub-section content)
            if re.match(r'^#{1,3}\s+', line):
                end = j
                break
        parts.append('\n'.join(lines[start:end]))

    return _strip_trailing_separator('\n\n'.join(parts))


def _extract_section(content: str, section_name: str, language: str = "delphi") -> Optional[str]:
    """Extract the specified section from markdown content.

    Returns section content (including heading line), excluding trailing separator lines.
    Returns None if the section does not exist.

    Args:
        content: markdown content
        section_name: section short key name
        language: language (affects section heading mapping)
    """
    # Special handling: debugging collection — collect all ### level headings (content of shared/debugging/)
    canonical_section = _normalize_section_name(section_name)
    if canonical_section == "debugging":
        result = _extract_debugging_sections(content)
        if result:
            return result

    lines = content.split('\n')
    ranges = _find_heading_ranges(lines)

    # Direct heading match
    if section_name in ranges:
        start, end = ranges[section_name]
        return _strip_trailing_separator('\n'.join(lines[:3] + [''] + lines[start:end]))

    # Look up via language-specific section mapping
    keys = _get_section_keys(language)
    target_title = keys.get(canonical_section)
    if target_title and target_title in ranges:
        start, end = ranges[target_title]
        return _strip_trailing_separator('\n'.join(lines[:3] + [''] + lines[start:end]))

    return None


def _extract_meta_section(content: str, meta_name: str, ranges: Dict[str, Tuple[int, int]], language: str = "delphi") -> Optional[str]:
    """Extract meta section (combination of multiple headings)."""
    keys = META_SECTIONS.get(_normalize_section_name(meta_name))
    if not keys:
        return None

    lines = content.split('\n')
    parts: List[str] = []
    section_keys = _get_section_keys(language)

    for key in keys:
        title = section_keys.get(key)
        if title and title in ranges:
            start, end = ranges[title]
            parts.append('\n'.join(lines[start:end]))

    if not parts:
        return None

    # Join parts with separator lines, prepend title block
    header = '\n'.join(lines[:3])
    body = '\n\n---\n\n'.join(parts)
    return _strip_trailing_separator(header + '\n\n' + body)


def _list_available_sections(content: str, language: str = "delphi") -> str:
    """Generate list of available sections."""
    lines = content.split('\n')
    ranges = _find_heading_ranges(lines)
    title_to_key = _get_title_to_key(language)

    available = []
    for title in sorted(ranges.keys()):
        if title in title_to_key:
            key = title_to_key[title]
            available.append(f"  `{key}` → {title}")

    lines_out = ["Available sections (pass to the section parameter):", ""]
    lines_out.append("[Top-level sections]")

    if language == "lazarus":
        lines_out.append("  Basic workflow: planning, workflow, env, kb_search, writing, compile, cleanup, review_guide")
        lines_out.append("  Review details: review(collection), consistency, completeness, resource_leak,")
        lines_out.append("           common_errors, code_quality, safety, performance")
        lines_out.append("  Others:     kb_build, agent_rules, human_collab, experience, maintenance, automation,")
        lines_out.append("           debugging(8.1–8.14 collection), multi_change")
        lines_out.append("  Combos:     review(review guide + review checklist), coding(writing+compile)")
    else:
        lines_out.append("  Basic workflow: planning, workflow, env, kb_search, writing, format, compile, cleanup, review_guide")
        lines_out.append("  Review details: review(collection), consistency, completeness, resource_leak, delphi_specific,")
        lines_out.append("           common_errors, code_quality, data_conversion, safety, performance")
        lines_out.append("  writing sub-sections: delphi_file_write_rule, delphi_file_dirty_flag, delphi_file_output_format,")
        lines_out.append("                 delphi_file_usage_tips")
        lines_out.append("  Others:     review_detail, kb_build, agent_rules, human_collab, experience, maintenance, automation,")
        lines_out.append("           debugging(8.1–8.14 collection), multi_change, ui-testing(→testing/ui), ui_layout, console-testing(→testing/console)")
        lines_out.append("  Combos:     review(review guide + review checklist), coding(write code + format + compile)")
        lines_out.append("  Compat aliases: kb-search/kb-rebuild/agent-rules/human-collab/delphi-file-rules")

    lines_out.append("")
    lines_out.append("If section is not passed, returns workflow overview + section index.")

    return '\n'.join(lines_out)


def _load_example(example_name: str, language: str = "delphi") -> Optional[str]:
    """
    Load example file by name. Recursively search matching .md files under coding-rules/{language}/examples/.

    Args:
        example_name: example name (without extension), e.g. "naming", "error-handling", "dirty-flag"
        language: programming language, defaults to "delphi"

    Returns:
        example content, returns None if not found
    """
    examples_dir = Path(__file__).parent.parent / "resources" / "coding-rules" / language / "examples"
    if not examples_dir.is_dir():
        return None

    # Exact match: examples/{name}.md or examples/**/{name}.md
    candidates = list(examples_dir.rglob(f"{example_name}.md"))
    if not candidates:
        return None

    # Prefer exact directory match (shallower first)
    candidates.sort(key=lambda p: len(p.parts))
    try:
        text = candidates[0].read_text(encoding="utf-8")
        logger.info(f"Loading example: {candidates[0].relative_to(examples_dir)}")
        return text
    except Exception as e:
        logger.error(f"Failed to read example file: {candidates[0]}: {e}")
        return None


async def get_coding_rules(
    project_path: Optional[str] = None,
    section: Optional[str] = None,
    examples: Optional[str] = None,
    language: Optional[str] = None,
) -> CallToolResult:
    """
    Get coding rules, supporting per-language (Delphi / Lazarus) and section-by-section retrieval.

    By default reads rule files from src/resources/coding-rules/{language}/ and shared/ directories.
    If CODING_RULES.mdc exists in the user project directory, merges user rules (user rules override default rules).

    Args:
        project_path: project path (optional), used to find user-defined coding rule files
        section: section name (optional), e.g. "workflow", "writing", "review", etc.
                 When not passed or None, returns workflow overview + section index, guiding on-demand retrieval.
                 Passing "list" returns the list of available sections.
        examples: example name (optional), e.g. "naming", "formatting", "error-handling".
                  When specified, loads the corresponding example file from coding-rules/{language}/examples/.
        language: programming language (optional), "delphi" (default) or "lazarus".
                  Defaults to "delphi" when not passed (backward compatible).
    """
    # Default language is delphi (backward compatible)
    lang = (language or "delphi").lower().strip()
    if lang not in LANGUAGE_NAMES:
        valid = ", ".join(LANGUAGE_NAMES.keys())
        return CallToolResult(
            content=[{"type": "text", "text": f"Unsupported language: '{language}'. Valid values: {valid}"}],
            isError=True,
        )

    logger.info(f"Coding rules request — language={lang}, project_path={project_path}, section={section}, examples={examples}")

    try:
        # Read default coding rules (shared/ + language/)
        default_rules, default_rules_path = _read_first_existing_text(
            _default_rules_candidates(lang),
            f"Default coding rule file (language={lang})",
        )
        if default_rules_path and default_rules:
            logger.info(f"Successfully read coding rule file: {default_rules_path} (language={lang})")
        elif default_rules_path:
            logger.warning(f"Default coding rule file is empty or failed to read: {default_rules_path}")
        else:
            logger.warning("Default coding rule directory does not exist: src/resources/coding-rules/")

        # If project path is provided, try to read user-defined coding rules
        user_rules = ""
        if project_path:
            project_dir = Path(project_path)
            user_rules_path = project_dir / "CODING_RULES.mdc"

            if user_rules_path.exists():
                try:
                    with open(user_rules_path, 'r', encoding='utf-8') as f:
                        user_rules = f.read()
                    logger.info(f"Successfully read user-defined coding rule file: {user_rules_path}")
                except Exception as e:
                    logger.error(f"Failed to read user-defined coding rule file: {str(e)}")
                    user_rules = ""
            else:
                logger.info(f"No custom coding rule file found in user project directory: {user_rules_path}")

        # Merge rules: default rules as base, user rules override
        merged = ""
        if default_rules:
            merged += "# ═══════════════════════════════════\n"
            merged += "# Default coding rules\n"
            merged += "# ═══════════════════════════════════\n"
            merged += default_rules
            if user_rules:
                merged += "\n\n"
                merged += "# ═══════════════════════════════════\n"
                merged += "# User-defined rules (override same-named rules above)\n"
                merged += "# ═══════════════════════════════════\n"
                merged += user_rules
        elif user_rules:
            merged = user_rules

        if not merged:
            logger.warning("No coding rule files found")
            return CallToolResult(
                content=[{"type": "text", "text": "No coding rule files found"}],
                isError=True
            )

        # Handle examples parameter: load example file by name
        if examples:
            example_text = _load_example(examples, lang)
            if example_text:
                logger.info(f"Returning example: {examples} (language={lang})")
                return CallToolResult(content=[{"type": "text", "text": example_text}])
            else:
                # List available example names for reference
                examples_dir = Path(__file__).parent.parent / "resources" / "coding-rules" / lang / "examples"
                available = []
                if examples_dir.is_dir():
                    for f in sorted(examples_dir.rglob("*.md")):
                        available.append(f.stem)
                hint = f"Available examples: {', '.join(available)}" if available else "No example files"
                return CallToolResult(
                    content=[{"type": "text", "text": f"Example not found: '{examples}'. {hint}"}],
                    isError=True
                )

        # Special section: section="automation" → read from resources/coding-rules/testing/automation/
        if section and _normalize_section_name(section) == "automation":
            automation_index = Path(__file__).parent.parent / "resources" / "coding-rules" / "testing" / "automation" / "index.md"
            if automation_index.exists():
                try:
                    text = automation_index.read_text(encoding="utf-8")
                    logger.info("Returning automation test section (from resources/coding-rules/testing/automation/index.md)")
                    return CallToolResult(content=[{"type": "text", "text": text}])
                except Exception as e:
                    logger.error(f"Failed to read automation index: {str(e)}")
                    # fall through to default handling

        # Special section: section="ui-testing" → read from resources/coding-rules/testing/ui.md
        if section and _normalize_section_name(section) == "ui-testing":
            ui_path = Path(__file__).parent.parent / "resources" / "coding-rules" / "testing" / "ui.md"
            if ui_path.exists():
                try:
                    text = ui_path.read_text(encoding="utf-8")
                    logger.info("Returning UI automation test section (from resources/coding-rules/testing/ui.md)")
                    return CallToolResult(content=[{"type": "text", "text": text}])
                except Exception as e:
                    logger.error(f"Failed to read UI test file: {str(e)}")

        # Special section: section="console-testing" → read from resources/coding-rules/testing/console.md
        if section and _normalize_section_name(section) == "console-testing":
            console_path = Path(__file__).parent.parent / "resources" / "coding-rules" / "testing" / "console.md"
            if console_path.exists():
                try:
                    text = console_path.read_text(encoding="utf-8")
                    logger.info("Returning console test section (from resources/coding-rules/testing/console.md)")
                    return CallToolResult(content=[{"type": "text", "text": text}])
                except Exception as e:
                    logger.error(f"Failed to read console test file: {str(e)}")

        # Handle section parameter
        if section == "list":
            output = _list_available_sections(merged, lang)
            return CallToolResult(content=[{"type": "text", "text": output}])

        if section:
            canonical_section = _normalize_section_name(section)
            # Check meta sections first
            lines = merged.split('\n')
            ranges = _find_heading_ranges(lines)
            meta_content = _extract_meta_section(merged, canonical_section, ranges, lang)
            if meta_content:
                logger.info(f"Returning meta section: {canonical_section} (language={lang})")
                return CallToolResult(content=[{"type": "text", "text": meta_content}])

            # Then check single sections
            section_content = _extract_section(merged, canonical_section, lang)
            if section_content:
                logger.info(f"Returning section: {canonical_section} (language={lang})")
                source = "default rules + user rules (user overrides default)" if default_rules and user_rules else \
                         "user rules" if user_rules else "default rules"
                output = f"Coding rules (source: {source}, section: {canonical_section}):\n\n"
                output += section_content
                return CallToolResult(content=[{"type": "text", "text": output}])

            # Section not found
            logger.warning(f"Unknown section: {section} (language={lang})")
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"Unknown section: '{section}' (language={lang}).\n\n{_list_available_sections(merged, lang)}"
                )],
                isError=True
            )

        # section=None: return workflow overview + section index, guiding on-demand retrieval
        logger.info(f"Returning workflow + section index (default mode, language={lang})")

        # Extract workflow overview section
        workflow_content = _extract_section(merged, "workflow", lang)
        workflow_part = workflow_content if workflow_content else ""

        # Generate section index
        if lang == "lazarus":
            index_lines = [
                "",
                "## Section index (Lazarus/FPC)",
                "",
                "Retrieve section details on demand (saves tokens, improves compliance):",
                "",
                "| Parameter | Content | When to use |",
                "|------|------|----------|",
                "| `section=\"planning\"` | P0 pre-planning and review | Required before coding new features / large-scale modifications |",
                "| `section=\"workflow\"` | Lazarus/FPC workflow overview | At task start, understand the overall flow |",
                "| `section=\"env\"` | ① Environment check | First run / when environment is abnormal |",
                "| `section=\"kb_search\"` | ② API lookup | Look up FPC definitions before coding |",
                "| `section=\"writing\"` | ③ Coding standards | Coding phase |",
                "| `section=\"compile\"` | ④ Compile | Compile verification |",
                "| `section=\"review\"` | ⑤ Code review (with complete review checklist) | Review final code quality after cleanup |",
                "| `section=\"cleanup\"` | ⑥ Cleanup | Clean up redundancy after compile passes |",
                "| `section=\"agent_rules\"` | Agent operation hard rules | When executing scripts or operating on files |",
                "| `section=\"human_collab\"` | Human-machine collaboration — abnormal diagnosis and manual intervention | During abnormal diagnosis or when manual intervention is needed |",
                "| `section=\"debugging\"` | Abnormal diagnosis and debugging (8.1–8.14 collection) | Runtime crashes / compile errors / difficult troubleshooting |",
                "| `section=\"multi_change\"` | Multi-change priority ordering | When handling multiple changes simultaneously |",
                "| `section=\"experience\"` | ⑪ Experience saving | When saving experience after problem resolution |",
                "| `section=\"kb_build\"` | Knowledge base rebuild | When KB rebuild is needed |",
                "| `section=\"automation\"` | ⚙ Automated test architecture | Before running automated UI tests |",
                "| `section=\"coding\"` | Combo: writing + compile | Complete coding workflow |",
                "",
                "Also available as finer-grained sections: planning, debugging, multi_change, consistency, completeness, resource_leak,",
                "common_errors, code_quality, safety, performance, agent_rules, human_collab, experience",
                "",
                "Usage examples:",
                "```python",
                'get_coding_rules(section="writing", language="lazarus")',
                'get_coding_rules(section="review", language="lazarus")',
                'get_coding_rules(section="list", language="lazarus")',
                "```",
            ]
        else:
            index_lines = [
            "",
            "## Section index",
            "",
            "Retrieve section details on demand (saves tokens, improves compliance):",
            "",
            "| Parameter | Content | When to use |",
            "|------|------|----------|",
             "| `section=\"planning\"` | P0 pre-planning and review | Required before coding new features / large-scale modifications |",
             "| `section=\"workflow\"` | Workflow overview | At task start, understand the overall flow |",
            "| `section=\"env\"` | ① Environment check | First run / when environment is abnormal |",
            "| `section=\"kb_search\"` | ② KB search | Look up API definitions before coding |",
             "| `section=\"writing\"` | ③ Write Delphi code (naming/format/generics/async/code organization/version compatibility/auto backup/write rules) | Coding phase |",
            "| `section=\"format\"` | ④ Format | Format code |",
            "| `section=\"compile\"` | ⑤ Compile | Compile verification |",
             "| `section=\"review\"` | ⑦ Code review (with complete review checklist) | Review final code quality after cleanup |",
             "| `section=\"cleanup\"` | ⑥ Cleanup | Clean up redundancy after compile passes |",
            "| `section=\"safety\"` | Safety rules | When security-sensitive operations are involved |",
            "| `section=\"performance\"` | Performance rules | Performance-sensitive paths |",
             "| `section=\"agent_rules\"` | Agent operation hard rules | When executing scripts or operating on files |",
             "| `section=\"human_collab\"` | Human-machine collaboration — abnormal diagnosis and manual intervention | During abnormal diagnosis or when manual intervention is needed (can be triggered at any step) |",
             "| `section=\"debugging\"` | Abnormal diagnosis and debugging (8.1–8.14 collection) | Runtime crashes / compile errors / difficult troubleshooting |",
             "| `section=\"multi_change\"` | Multi-change priority ordering | When handling multiple changes simultaneously |",
             "| `section=\"experience\"` | ⑪ Experience saving — deposit knowledge into experience library | When saving experience after problem resolution |",
            "| `section=\"kb_build\"` | Knowledge base rebuild | When KB rebuild is needed |",
             "| `section=\"automation\"` | ⚙ Automated test architecture (with prompt template F + experience optimization loop G) | Before running automated UI tests, plan test plan / recovery strategy |",
             "| `section=\"ui-testing\"` | ⑧ Automated UI interaction testing | After GUI program compiles, UI interaction verification |",
             "| `section=\"ui_layout\"` | UI layout standards and audit | Check layout quality after AI generates or modifies a Delphi form |",
             "| `section=\"console-testing\"` | ⑨ Console program interaction verification | After console program compiles, stdin/stdout verification |",
             "| `section=\"coding\"` | Combo: writing + format + compile | Complete coding workflow |",
             "| `section=\"delphi_file_write_rule\"` | delphi_file write rules (1-indexed/edits parameter) | When editing Delphi files and need to understand line number rules |",
             "",
             "Also available as finer-grained sections: planning, debugging, multi_change, consistency, completeness, resource_leak, delphi_specific, common_errors,",
             "code_quality, data_conversion, safety, performance, delphi_file_write_rule,",
             "delphi_file_dirty_flag, delphi_file_output_format, delphi_file_usage_tips, human_collab, experience, maintenance,",
             "ui-testing, ui_layout, console-testing",
            "",
            "Usage examples:",
            "```python",
            'get_coding_rules(section="writing")    # only coding rules',
            'get_coding_rules(section="review")     # only review checklist',
            'get_coding_rules(section="safety")     # only safety rules',
            'get_coding_rules(section="list")       # list all sections',
            "```",
        ]
        index_text = "\n".join(index_lines)

        output = workflow_part + "\n" + index_text
        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        error_msg = f"Exception occurred while getting coding rules: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )