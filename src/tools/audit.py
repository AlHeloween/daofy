"""
Code audit / AST syntax parsing MCP tool

Integrates with daudit.exe, supporting two modes:
  --mode audit — run static analysis on Delphi source code, output violation report
  --mode ast   — AST syntax parsing, output entity structure information

Falls back to a guidance prompt when daudit.exe is absent, without affecting other features.

Output format:
  {"mode":"audit|ast","status":"ok|error","data":{...},"summary":{...}}

Copyright (C) Jilin Left-Right Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
"""

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.types import CallToolResult, TextContent

from ..constants import TIMEOUT_AUDIT
from .layout_audit import run_layout_audit

logger = logging.getLogger(__name__)

# daudit.exe path cache
_DAUDIT_PATH: Optional[str] = None


def _find_daudit() -> Optional[str]:
    """Locate the daudit.exe path"""
    global _DAUDIT_PATH
    if _DAUDIT_PATH:
        return _DAUDIT_PATH

    candidates = [
        Path(__file__).parent.parent.parent / "tools" / "daudit" / "daudit.exe",
        Path.cwd() / "tools" / "daudit" / "daudit.exe",
    ]
    for p in candidates:
        if p.exists():
            _DAUDIT_PATH = str(p.resolve())
            return _DAUDIT_PATH
    return None


def _run_daudit(cmd: List[str]) -> Optional[Dict]:
    """Run daudit.exe and parse the unified envelope JSON

    The new daudit outputs pure JSON in a unified format:
    {"mode":"...","status":"ok|error","data":{...},"summary":{...}}

    Args:
        cmd: List of daudit command-line arguments

    Returns:
        The parsed full payload dict, or None
    """
    daudit = _find_daudit()
    if not daudit:
        return None

    full_cmd = [daudit, "--format", "json"] + cmd

    try:
        result = subprocess.run(
            full_cmd, capture_output=True, text=True, timeout=TIMEOUT_AUDIT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode in (0, 1) and result.stdout.strip():
            return json.loads(result.stdout)
        logger.warning("daudit error (exit=%d): %s", result.returncode, result.stderr[:200])
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.error("daudit invocation failed: %s", e)

    return None


def _run_audit(paths: List[str], recursive: bool = False) -> Optional[Dict]:
    """Run daudit --mode audit

    CLI: daudit --mode audit --format json [--recursive] <path(s)>

    Returns:
        The data section dict ({findings, totalFindings}), or None
    """
    cmd = ["--mode", "audit"]
    if recursive:
        cmd.append("--recursive")
    cmd.extend(paths)

    payload = _run_daudit(cmd)
    if payload and payload.get("status") == "ok":
        return payload.get("data")
    return None


def _run_skeleton(base_dir: str, file_path: Optional[str] = None,
                   detail: str = "compact") -> Optional[List[Dict]]:
    """Run daudit --mode skeleton to extract a code skeleton summary

    CLI: daudit --mode skeleton --skeleton-detail compact --format json <file(s)>

    The skeleton mode is designed for AI Agents and outputs a preformatted text summary:
      unit name, uses, classes/records/interfaces, functions/procedures, constants/variables
    --skeleton-detail compact: no call chain information, most token-efficient

    Args:
        base_dir: Audit base directory (used to locate .pas files)
        file_path: Single file path (takes priority over base_dir)
        detail: skeleton detail level: compact (recommended) / normal / full

    Returns:
        list of {"file": path, "data": text}, or None
    """
    daudit = _find_daudit()
    if not daudit:
        return None

    pas_files: List[str] = []
    if file_path:
        pas_files.append(file_path)
    elif base_dir:
        src = Path(base_dir)
        if src.is_file():
            pas_files.append(str(src.resolve()))
        elif src.is_dir():
            pas_files.extend(str(p.resolve()) for p in src.rglob("*.pas"))

    if not pas_files:
        return None

    cmd = [daudit, "--mode", "skeleton", "--skeleton-detail", detail,
           "--format", "json"]
    cmd.extend(pas_files)

    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            tmp_path = tmp.name

        with open(tmp_path, 'wb') as f:
            result = subprocess.run(
                cmd, stdout=f, stderr=subprocess.PIPE,
                timeout=TIMEOUT_AUDIT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )

        if result.returncode == 0 and os.path.getsize(tmp_path) > 0:
            with open(tmp_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                files_data = payload.get("data", payload)
                if isinstance(files_data, dict):
                    files_list = files_data.get("files", [])
                elif isinstance(files_data, list):
                    files_list = files_data
                else:
                    files_list = []
                logger.info("Skeleton parsing complete: %d files", len(files_list))
                return files_list

        stderr = result.stderr.strip()[:200] if result.stderr else ""
        logger.warning("Skeleton parsing error (exit=%d): %s", result.returncode, stderr)

    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.error("Skeleton parsing invocation failed: %s", e)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return None


def _extract_json(text: str) -> Optional[str]:
    """Extract the first complete JSON object from mixed daudit output (handles leading banner + trailing summary)"""
    start = text.find('{')
    if start < 0:
        return None
    # Find the matching closing } character by character
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


# ── Severity ordering (maps daudit's actual severity → display level) ──
_DAUDIT_SEVERITY_MAP = {
    "error": "critical",
    "warning": "warning",
    "hint": "suggestion",
}
_SEVERITY_ORDER = {"critical": 0, "warning": 1, "suggestion": 2}
_SEVERITY_LABEL = {"critical": "🔴 Critical", "warning": "🟡 Warning", "suggestion": "🔵 Suggestion"}


def _format_report(data: Dict, min_severity: str = "suggestion") -> str:
    """Format the audit data section into a Markdown report

    data format:
    {
        "findings": [
            {"rule_id":"...", "file":"...", "line":N, "column":N,
             "severity":"hint|warning|error",
             "category":"...", "message":"...",
             "code_snippet":"..."}
        ],
        "totalFindings": N
    }
    """
    findings: List[Dict] = data.get("findings", [])
    total = data.get("totalFindings", len(findings))

    min_level = _SEVERITY_ORDER.get(min_severity, 2)

    lines: List[str] = []
    lines.append("# Code Audit Report")
    lines.append("")
    lines.append(f"**Total violations**: {total}")
    lines.append("")

    # Group by severity level
    groups: Dict[str, List[Dict]] = {"critical": [], "warning": [], "suggestion": []}
    for f in findings:
        raw_sev = f.get("severity", "hint")
        mapped_sev = _DAUDIT_SEVERITY_MAP.get(raw_sev, "suggestion")
        lv = _SEVERITY_ORDER.get(mapped_sev, 2)
        if lv <= min_level:
            groups[mapped_sev].append(f)

    # Category statistics
    cat_count: Dict[str, int] = {}
    for f in findings:
        cat = f.get("category", "Other")
        cat_count[cat] = cat_count.get(cat, 0) + 1
    if cat_count:
        lines.append("### Distribution by category")
        for cat in sorted(cat_count):
            lines.append(f"- **{cat}**: {cat_count[cat]}")
        lines.append("")

    for display_sev in ["critical", "warning", "suggestion"]:
        items = groups[display_sev]
        if not items:
            continue
        lines.append(f"## {_SEVERITY_LABEL[display_sev]} ({len(items)} items)")
        lines.append("")

        for f in items:
            rule_id = f.get("rule_id", "")
            file_path = f.get("file", "?")
            line_num = f.get("line", "?")
            column = f.get("column", "")
            category = f.get("category", "")
            message = f.get("message", "")
            snippet = f.get("code_snippet", "")

            loc = f"`{file_path}:{line_num}"
            if column:
                loc += f":{column}"
            loc += "`"

            header = f"- **[{rule_id}]** {category} — {loc}" if rule_id else f"- **{category}** — {loc}"
            lines.append(header)
            lines.append(f"  {message}")
            if snippet:
                lines.append("  ```pascal")
                lines.append(f"  {snippet}")
                lines.append("  ```")
            lines.append("")

    return "\n".join(lines)



def _build_guide(mode: str = "audit") -> str:
    """Guidance prompt shown when daudit.exe is absent

    Returns the AI manual audit guidance for the requested mode, so the AI can
    review the code directly according to the rules rather than waiting for
    daudit to be installed.
    """
    if mode == "ast":
        return (
            "# daudit unavailable — please use delphi_file to analyze the code structure manually\n\n"
            "The AST analysis engine (daudit.exe) is not installed, so the code skeleton cannot be extracted automatically.\n\n"
            "## Please analyze manually by following the steps below\n\n"
            "1. **Get the list of files to audit**\n"
            "   - `delphi_file(action=\"read\", file_path=\"...\", search_type=\"path\")` lists the .pas files in a directory\n\n"
            "2. **Read each file and extract its structure**\n"
            "   - `delphi_file(action=\"read\", file_path=\"...\", search_type=\"class\")` — extract class/interface definitions\n"
            "   - `delphi_file(action=\"read\", file_path=\"...\", search_type=\"function\")` — extract function/procedure signatures\n"
            "   - `delphi_file(action=\"read\", file_path=\"...\", search_type=\"record\")` — extract record types\n\n"
            "3. **Key points to focus on**\n"
            "   - uses dependencies (interface + implementation)\n"
            "   - Class inheritance chains and interface implementations\n"
            "   - Public method signatures and visibility\n"
            "   - Constant/type definitions\n\n"
            "> 💡 Once daudit is installed, `delphi_project(action=\"ast\", ...)` can provide a preformatted skeleton summary."
        )

    # Default audit mode
    return (
        "# daudit unavailable — please perform a manual code audit according to the review rules\n\n"
        "The static analysis engine (daudit.exe) is not installed, so the 50+ audit rules cannot be run automatically.\n"
        "**Please perform a manual audit by following the process below:**\n\n"
        "## Audit process\n\n"
        "### ① Get the review rules\n\n"
        "```\nget_coding_rules(section=\"review\")\n```\n\n"
        "Returns 66 check items across 9 dimensions (consistency/integrity/resource leaks/Delphi-specific pitfalls/\n"
        "common error patterns/code quality/data conversion/security/performance).\n\n"
        "### ② Read the source code to audit\n\n"
        "```\ndelphi_file(action=\"read\", file_path=\"Unit1.pas\")\n```\n\n"
        "### ③ Check item by item across each dimension\n\n"
        "Review each check item in `get_coding_rules(section=\"review\")` one by one, focusing on:\n\n"
        "| Priority | Dimension | Key checks |\n"
        "|--------|------|----------|\n"
        "| 🔴 P0 | Resource leaks | Create/Free pairing, try/finally resource release |\n"
        "| 🔴 P0 | Security | SQL injection, hard-coded credentials, buffer overflow |\n"
        "| 🔴 P0 | Delphi-specific | Interface circular references, double Free of TComponent, Record value semantics |\n"
        "| 🟡 P1 | Integrity | Branch coverage, boundary conditions, input validation |\n"
        "| 🟡 P1 | Common errors | Empty except, with statements, accessing VCL from threads |\n"
        "| 🟢 P2 | Code quality | Method size, cyclomatic complexity, magic numbers |\n"
        "| 🟢 P2 | Performance | Allocations inside loops, unnecessary type casts |\n\n"
        "### ④ Output the audit report\n\n"
        "Output the issues found in the following format:\n\n"
        "```\n"
        "## Audit report\n\n"
        "### 🔴 Critical issues\n"
        "- [file:line] Issue description → Fix suggestion\n\n"
        "### 🟡 Warning issues\n"
        "- [file:line] Issue description → Fix suggestion\n\n"
        "### 🔵 Suggestions\n"
        "- [file:line] Optimization suggestion\n```\n\n"
        "> 💡 Once daudit is installed, `delphi_project(action=\"audit\", ...)` can run the rule checks automatically."
    )


# ═══════════════════════════════════════════════════════════
# Runtime registration check (mode "runtime")
# ═══════════════════════════════════════════════════════════

_RULES_PATH = Path(__file__).parent.parent / "rules" / "runtime_registry.json"


def _load_runtime_rules() -> List[Dict]:
    """Load runtime registration check rules"""
    if not _RULES_PATH.exists():
        return []
    try:
        with open(_RULES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("rules", [])
    except Exception as e:
        logger.warning("Failed to load runtime rules: %s", e)
        return []


def _find_pas_dfm_files(base_dir: str) -> tuple:
    """Scan the directory for .pas and .dfm files"""
    src = Path(base_dir)
    pas_files = list(src.rglob("*.pas"))
    dfm_files = list(src.rglob("*.dfm"))
    return pas_files, dfm_files


def _extract_classes_from_dfm(filepath: Path) -> set:
    """Extract component class names from a DFM file (object Xxx: TYyy)"""
    classes = set()
    try:
        text = filepath.read_text(encoding="utf-8-sig")
        for m in re.finditer(r'object\s+\w+\s*:\s*(T\w+)', text):
            classes.add(m.group(1))
    except Exception as e:
        logger.debug("Failed to extract DFM class names %s: %s", filepath, e)
    return classes


def _extract_uses_set(filepath: Path) -> set:
    """Extract all unit names from the uses clauses of a PAS file"""
    units = set()
    try:
        text = filepath.read_text(encoding="utf-8-sig")
        # Remove strings and comments
        text = re.sub(r"'(?:[^']*)'", '', text)
        text = re.sub(r'\{[^}]*\}', '', text)
        text = re.sub(r'//[^\n]*', '', text)
        # Match uses ... ; sections
        for m in re.finditer(
            r'\buses\b\s*(.*?)\s*;',
            text, re.DOTALL
        ):
            section = m.group(1)
            for part in section.split(','):
                part = part.strip()
                if part and not part[0].isupper():
                    continue
                units.add(part)
    except Exception as e:
        logger.debug("Failed to extract uses list %s: %s", filepath, e)
    return units


def _check_runtime_rules(base_dir: str) -> List[Dict]:
    """Execute the runtime registration rule checks"""
    rules = _load_runtime_rules()
    if not rules:
        return [{
            "id": "N/A",
            "severity": "warning",
            "message": "Runtime rules file not found or rules are empty",
        }]

    pas_files, dfm_files = _find_pas_dfm_files(base_dir)
    if not pas_files and not dfm_files:
        return [{
            "id": "N/A",
            "severity": "info",
            "message": f"No .pas or .dfm files found in {base_dir}",
        }]

    # Collect all class names in the project (most reliable from DFM)
    project_classes: set = set()
    all_uses: set = set()

    for f in dfm_files:
        project_classes |= _extract_classes_from_dfm(f)
    for f in pas_files:
        all_uses |= _extract_uses_set(f)

    findings: List[Dict] = []
    for rule in rules:
        triggers = rule.get("triggers", [])
        dependencies = rule.get("dependencies", [])
        require_unit = rule.get("require_unit", "")

        # Check whether any trigger class is present
        has_trigger = any(t in project_classes for t in triggers)
        if not has_trigger:
            continue

        # If dependency classes are defined, check whether any match
        if dependencies:
            has_dep = any(d in project_classes for d in dependencies)
            if not has_dep:
                continue

        # Check whether require_unit is in the uses clauses
        unit_found = False
        for u in all_uses:
            if u == require_unit or u.endswith('.' + require_unit):
                unit_found = True
                break

        if not unit_found:
            findings.append({
                "id": rule["id"],
                "severity": rule.get("severity", "warning"),
                "trigger_classes": [t for t in triggers if t in project_classes],
                "dependencies": [d for d in dependencies if d in project_classes],
                "require_unit": require_unit,
                "message": rule.get("message", ""),
            })

    return findings


def _format_runtime_report(findings: List[Dict]) -> str:
    """Format the runtime registration check report"""
    if not findings:
        return "## ✅ Runtime registration check passed\n\nNo missing runtime registration units found.\n"

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    lines = ["## 🔍 Runtime registration check results\n"]
    lines.append(f"| Level | Rule | Count |")
    lines.append(f"|------|------|------|")
    lines.append(f"| 🔴 Errors | {len(errors)} |" if errors else "| 🔴 Errors | 0 |")
    lines.append(f"| 🟡 Warnings | {len(warnings)} |" if warnings else "| 🟡 Warnings | 0 |")
    lines.append("")

    if not errors and not warnings:
        lines.append("Check passed, no issues found.\n")
        return "\n".join(lines)

    for f in findings:
        icon = "🔴" if f["severity"] == "error" else "🟡"
        lines.append(f"### {icon} [{f['id']}] {f['severity'].upper()}")
        lines.append("")
        msg = f["message"]
        if f.get("trigger_classes"):
            msg = msg.replace("{triggers}", ", ".join(f["trigger_classes"]))
        if f.get("dependencies"):
            msg = msg.replace("{dependencies}", ", ".join(f["dependencies"]))
        lines.append(f"**{msg}**")
        lines.append("")
        lines.append(f"- Trigger classes: `{'`, `'.join(f.get('trigger_classes', []))}`")
        if f.get("dependencies"):
            lines.append(f"- Dependency classes: `{'`, `'.join(f['dependencies'])}`")
        lines.append(f"- Suggested addition: `{f.get('require_unit', '')}` to the uses clause")
        lines.append("")

    return "\n".join(lines)


async def run_audit(arguments: Dict[str, Any]) -> CallToolResult:
    """Execute Delphi code audit / AST syntax parsing / Runtime registration check / UI layout audit

    Args:
        base_dir:   Audit base directory — the root path used to locate the project and source code during audit/AST parsing/runtime checks
        file_path:    Single file path (optional for ast mode, takes priority over base_dir)
        mode:         Run mode, defaults to "audit". Options: "ast" (AST syntax parsing),
                      "runtime" (runtime registration check), "layout" (UI layout audit)
        severity:     Minimum severity level, defaults to "suggestion" (audit mode only)
        output_format: Output format, defaults to "report". Option: "json"

    Returns:
        Structured CallToolResult
    """
    base_dir = str(arguments.get("base_dir", "") or "").strip()
    file_path = str(arguments.get("file_path", "") or "").strip() or None
    mode = arguments.get("mode") or arguments.get("action") or "audit"
    severity = arguments.get("severity", "suggestion")
    output_format = arguments.get("output_format", "report")

    # Validate parameters
    if not base_dir and not file_path:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text="# Parameter error\n\nPlease provide the `base_dir` (audit base directory) or `file_path` (file) parameter.\n\n"
                     'Example: `run_audit(base_dir="C:\\\\Project\\\\src")`\n'
                     '      `run_audit(mode="ast", file_path="Unit1.pas")`'
            )],
            isError=True,
        )

    if base_dir:
        src_path = Path(base_dir)
        if not src_path.exists():
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"# Path does not exist\n\n`{base_dir}` does not exist, please check the path."
                )],
                isError=True,
            )

    if file_path:
        fp_path = Path(file_path)
        if not fp_path.exists():
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"# File does not exist\n\n`{file_path}` does not exist, please check the path."
                )],
                isError=True,
            )

    # ── UI layout audit mode (does not require daudit) ──
    if mode == "layout":
        return await run_layout_audit(arguments)

    # ── Runtime registration check mode (does not require daudit) ──
    if mode == "runtime":
        if not base_dir:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text="# Parameter error\n\nruntime mode requires the `base_dir` parameter.\n\n"
                         'Example: `run_audit(mode="runtime", base_dir="C:\\\\Project\\\\src")`'
                )],
                isError=True,
            )
        findings = _check_runtime_rules(base_dir)
        text = _format_runtime_report(findings)
        return CallToolResult(content=[TextContent(type="text", text=text)])

    # Check whether daudit is available
    if not _find_daudit():
        guide = _build_guide(mode)
        guide += (
            f"\n---\n**Request parameters**: mode=`{mode}`, base_dir=`{base_dir}`, "
            f"file_path=`{file_path or ''}`\n\n"
            f"Once daudit.exe is ready, simply call again."
        )
        return CallToolResult(content=[TextContent(type="text", text=guide)])

    # ── AST syntax parsing mode (actually invokes daudit --mode skeleton) ──
    if mode == "ast":
        detail = "compact"  # compact / normal / full
        files_list = _run_skeleton(base_dir, file_path, detail=detail)
        if not files_list:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text="# AST parsing failed\n\n"
                         "daudit.exe was found but parsing failed. Please check:\n"
                         "1. Whether daudit.exe is executable\n"
                         "2. Whether the directory/file contains .pas files\n"
                         "3. Whether there is enough memory/disk space\n\n"
                         f"**Directory**: {base_dir}\n"
                         f"**File**: {file_path or '(all)'}"
                )],
                isError=True,
            )

        if output_format == "json":
            text = json.dumps(files_list, indent=2, ensure_ascii=False)
        else:
            # The data returned by skeleton mode is already preformatted text; concatenate and output directly
            parts = []
            for fi in files_list:
                fname = fi.get("file", "?")
                fdata = fi.get("data", "")
                header = f"## {fname}\n"
                parts.append(header + fdata)
            text = "# Code structure summary (Skeleton)\n\n" + "\n---\n\n".join(parts)

            # Hint to the AI Agent: what normal/full additionally provide
            text += (
                "\n\n---\n"
                "> 💡 Current skeleton-detail=compact (most token-efficient). If you need more context, "
                "specify `skeleton_detail=\"normal\"` or `skeleton_detail=\"full\"` and call run_audit again:\n"
                "> - **normal** — same as compact, no extra information (compact/normal produce the same output volume)\n"
                "> - **full** — appends `// calls=[list of called functions] | reads=[list of global variables read]` after each function/procedure,\n"
                ">   used to analyze call chains and variable dependencies, roughly doubling the token count\n"
            )

        return CallToolResult(content=[TextContent(type="text", text=text)])

    # ── Code audit mode (default) ──
    # audit mode requires base_dir
    if not base_dir:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text="# Parameter error\n\nAudit mode requires the `base_dir` parameter.\n\n"
                     'Example: `run_audit(base_dir="C:\\\\Project\\\\src")`'
            )],
            isError=True,
        )

    data = _run_audit([base_dir], recursive=True)
    if not data:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text="# Audit execution failed\n\n"
                     "daudit.exe was found but execution failed. Please check:\n"
                     "1. Whether daudit.exe is executable\n"
                     "2. Whether the source directory contains .pas files\n"
                     "3. Whether there is enough memory/disk space\n\n"
                     f"**Directory**: {base_dir}"
            )],
            isError=True,
        )

    # Format the output
    if output_format == "json":
        text = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        text = _format_report(data, severity)

    return CallToolResult(content=[TextContent(type="text", text=text)])

