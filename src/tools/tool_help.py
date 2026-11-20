"""
tool_help MCP tool — returns full help documentation by tool name

Used to replace stuffing detailed docs into tool description.
When AI Agent is unsure how to use a tool, call this tool to get full help on demand.
"""

from typing import Any
from src.utils.path_guard import TOOL_PATH_FIELDS
from ..tool_docs import TOOL_HELP_DOCS

import logging
logger = logging.getLogger(__name__)

_PATH_POLICY_TEXT = (
    "⚠️ Path parameter rule: Filesystem path parameters for this tool must be absolute paths "
    "(the MCP server cannot obtain the client's current working directory, so relative paths will be rejected). "
    "Relative paths in documentation examples are placeholders only; in actual calls, replace them with absolute paths, e.g. C:\\project\\Unit1.pas."
)


def _is_path_tool(tool_name: str) -> bool:
    return tool_name in TOOL_PATH_FIELDS


def _path_policy_text(tool_name: str) -> str:
    fields = TOOL_PATH_FIELDS.get(tool_name, ())
    if not fields:
        return _PATH_POLICY_TEXT
    return _PATH_POLICY_TEXT + " Path parameters: " + ", ".join(fields) + "."



def get_tool_help(tool_name: str, action: str = "") -> dict:
    """Get full help documentation for a single tool.

    Args:
        tool_name: Tool name, e.g. compile_project / delphi_file
        action: Optional; when an action name is specified, return only that action's detailed parameter description

    Returns:
        dict: {"tool": name, "docs": {...}} or {"error": "..."}
    """
    docs = TOOL_HELP_DOCS.get(tool_name)
    if not docs:
        available = ", ".join(sorted(TOOL_HELP_DOCS.keys()))
        return {
            "status": "failed",
            "message": f"Unknown tool: {tool_name}. Available tools: {available}",
        }

    # If an action is specified, output only the parameter section for that action
    if action:
        action_params = docs.get("action_params", {})
        act_info = action_params.get(action)
        if not act_info:
            all_actions = ", ".join(sorted(action_params.keys()))
            return {
                "status": "failed",
                "message": f"Tool {tool_name} has no action '{action}'. Available actions: {all_actions}",
            }

        desc = act_info.get("description", "")
        lines = [f"📘 {tool_name} — action: {action}", ""]
        if _is_path_tool(tool_name):
            lines.append(_path_policy_text(tool_name))
            lines.append("")
        lines.append(f"  ▶ {action}: {desc}")
        req = act_info.get("required", [])
        if req:
            lines.append(f"    Required parameters: {', '.join(req)}")
        opt = act_info.get("optional", {})
        if opt:
            lines.append("    Optional parameters:")
            for pname, pdesc in opt.items():
                lines.append(f"      {pname}: {pdesc}")
        ex = act_info.get("examples", [])
        if ex:
            lines.append("    Examples:")
            for e in ex:
                lines.append(f"      {e}")
        return {"status": "ok", "tool": tool_name, "action": action, "help": "\n".join(lines)}

    # Format as readable text
    lines = [f"📘 {tool_name} — {docs.get('description', '')}", ""]
    if _is_path_tool(tool_name):
        lines.append(_path_policy_text(tool_name))
        lines.append("")

    if docs.get("triggers"):
        triggers = "; ".join(docs["triggers"])
        lines.append(f"Trigger words: {triggers}")
        lines.append("")

    if docs.get("file_triggers"):
        ft = docs["file_triggers"]
        if isinstance(ft, list):
            for item in ft:
                lines.append(f"⚠️  {item}")
        else:
            lines.append(f"⚠️  {ft}")
        lines.append("")

    constraints = docs.get("constraints", [])
    if constraints:
        for c in constraints:
            lines.append(c)
        lines.append("")

    auto_paths = docs.get("auto_unit_paths", [])
    if auto_paths:
        lines.append("DaofyAutomation unit selection (choose one based on framework type):")
        for p in auto_paths:
            lines.append(f"  • {p}")
        lines.append("")

    if docs.get("features"):
        lines.append("Features:")
        for f in docs["features"]:
            lines.append(f"  ✅ {f}")
        lines.append("")

    if docs.get("sync_rules"):
        lines.append("Sync rules:")
        for r in docs["sync_rules"]:
            lines.append(f"  {r}")
        lines.append("")

    if docs.get("actions"):
        lines.append("Action descriptions (action):")
        acts = docs["actions"]
        if isinstance(acts, dict):
            # Display by group first
            for key, val in acts.items():
                if isinstance(val, dict):
                    lines.append(f"  ▶ {key}:")
                    for sub_k, sub_v in val.items():
                        lines.append(f"    {sub_k} — {sub_v}")
                else:
                    lines.append(f"  {key} — {val}")
        lines.append("")

    if docs.get("action_params"):
        lines.append("Parameter descriptions for each action (call tool_help first, then invoke):")
        lines.append("")
        for act_name, act_info in docs["action_params"].items():
            desc = act_info.get("description", "")
            lines.append(f"  ▶ {act_name}: {desc}")
            req = act_info.get("required", [])
            if req:
                lines.append(f"    Required parameters: {', '.join(req)}")
            opt = act_info.get("optional", {})
            if opt:
                lines.append("    Optional parameters:")
                for pname, pdesc in opt.items():
                    lines.append(f"      {pname}: {pdesc}")
            ex = act_info.get("examples", [])
            if ex:
                lines.append("    Examples:")
                for e in ex:
                    lines.append(f"      {e}")
            lines.append("")

    if docs.get("workflow_hints"):
        lines.append("Common workflows:")
        for name, flow in docs["workflow_hints"].items():
            lines.append(f"  {name}: {flow}")
        lines.append("")

    if docs.get("architecture"):
        arch = docs["architecture"]
        lines.append(f"Architecture pattern: {arch.get('pattern', '')}")
        lines.append(f"  Brain (large model): {arch.get('brain', '')}")
        lines.append(f"  Hands/feet (MCP): {arch.get('hands', '')}")
        see = arch.get('see_also')
        if see:
            lines.append(f"  See also: {see}")
        sl = arch.get('self_learning')
        if sl:
            lines.append(f"  Self-evolution: {sl}")
        lines.append("")

    if docs.get("planning_guide"):
        pg = docs["planning_guide"]
        lines.append(f"Planning guide:")
        lines.append(f"  Principle: {pg.get('principle', '')}")
        prefer = pg.get('prefer_order')
        if prefer:
            lines.append("  Fallback priority:")
            for p in prefer:
                lines.append(f"    → {p}")
        recovery = pg.get('failure_recovery')
        if recovery:
            lines.append("  Failure recovery:")
            for signal, action in recovery.items():
                lines.append(f"    {signal}: {action}")
        pt = pg.get('prompt_templates')
        if pt:
            lines.append(f"  Prompt templates: {pt}")
        eo = pg.get('experience_optimization')
        if eo:
            lines.append(f"  Experience optimization: {eo}")
        lines.append("")

    if docs.get("modes"):
        lines.append("Run modes:")
        for mode_name, mode_desc in docs["modes"].items():
            if isinstance(mode_desc, dict):
                lines.append(f"  {mode_name}: {mode_desc.get('description', '')}")
                needs = mode_desc.get('needs_auto_unit')
                if needs is not None:
                    lines.append(f"    Requires DaofyAutomation: {'Yes' if needs else 'No'}")
                # Phase-based commands
                cmds_by_phase = mode_desc.get('commands_by_phase')
                if cmds_by_phase:
                    lines.append("    Command categories (by perception-execution-verification phase):")
                    for phase_name, phase_info in cmds_by_phase.items():
                        icon = {"perception": "🔍", "execution": "⚡", "verification": "✅"}.get(phase_name, "•")
                        lines.append(f"    {icon} {phase_info.get('description', phase_name)}:")
                        for cmd_key, cmd_desc in phase_info.get('cmds', {}).items():
                            lines.append(f"        {cmd_key}: {cmd_desc}")
                # Legacy flat commands
                legacy_cmds = mode_desc.get('commands')
                if legacy_cmds and not cmds_by_phase:
                    for group, desc in legacy_cmds.items():
                        lines.append(f"    {group}: {desc}")
                # Console params
                params = mode_desc.get('params')
                if params:
                    lines.append("    Parameters:")
                    for pname, pdesc in params.items():
                        lines.append(f"      {pname}: {pdesc}")
            else:
                lines.append(f"  {mode_name}: {mode_desc}")
        lines.append("")

    if docs.get("workflow"):
        lines.append(f"Collaboration chain: {docs['workflow']}")
        lines.append("")

    if docs.get("fallback"):
        lines.append(f"Fallback strategy: {docs['fallback']}")
        lines.append("")

    if docs.get("section_guide"):
        lines.append("Section descriptions (section):")
        for sec_name, sec_desc in docs["section_guide"].items():
            lines.append(f"  {sec_name} — {sec_desc}")
        lines.append("")
    if docs.get("default_section"):
        lines.append(docs["default_section"])
        lines.append("")

    if docs.get("platforms"):
        lines.append("Supported platforms:")
        for plat_name, plat_desc in docs["platforms"].items():
            lines.append(f"  {plat_name}: {plat_desc}")
        lines.append("")

    if docs.get("china_access"):
        lines.append(f"China access: {docs['china_access']}")
        lines.append("")

    if docs.get("details"):
        lines.append(docs["details"])
        lines.append("")

    if docs.get("notes"):
        lines.append(docs["notes"])
        lines.append("")

    if docs.get("push_notification"):
        lines.append(f"Push notification: {docs['push_notification']}")
        lines.append("")

    if docs.get("usage"):
        lines.append(docs["usage"])
        lines.append("")

    if docs.get("examples"):
        lines.append("Examples:")
        for ex in docs["examples"]:
            lines.append(f"  {ex}")
        lines.append("")

    text = "\n".join(lines)
    return {"status": "ok", "tool": tool_name, "help": text}