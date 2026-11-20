"""
Experience Tracker — tracks tool call history and automatically detects experience save opportunities.

Maintains a rolling call log inside the MCP server. When the AI calls experience(action="suggest"),
it analyzes patterns in the log and prefills an experience draft (problem/solution/tags/context)
for the AI to review before formally saving via experience(action="save").

Pattern detection:
  - fix_cycle:    compile fail → file write → compile success
  - learn_apply:  kb search → file write → compile success
  - clean_fix:    file write → compile success (no preceding failure)
"""

import json
import logging
import os
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_RECENT_CALLS = 50  # Rolling log capacity


@dataclass
class ToolCallRecord:
    """Record of a single tool call"""
    name: str
    action: str
    project_path: str = ""
    file_path: str = ""
    success: bool = False
    error_text: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class ExperienceTracker:
    """Tool call tracker — rolling log + pattern detection.

    Thread-safe. Maintains a fixed-depth ring buffer that keeps only the most recent calls.
    """

    def __init__(self):
        self._calls: deque[ToolCallRecord] = deque(maxlen=MAX_RECENT_CALLS)
        self._lock = threading.Lock()

    # ── Recording ──

    def record(self, name: str, arguments: dict, success: bool,
               result_text: str = "") -> None:
        """Record a single tool call.

        Args:
            name: Tool name (delphi_project, delphi_file, delphi_kb)
            arguments: Call arguments
            success: Whether it succeeded
            result_text: Result text fragment (e.g. error message)
        """
        action = str(arguments.get("action", ""))
        project_path = str(arguments.get("project_path", arguments.get("file_path", "")))
        file_path = str(arguments.get("file_path", arguments.get("project_path", "")))

        # Extract meaningful error text
        error_text = ""
        if not success:
            # Extract error summary from the result
            if result_text:
                # Take the first 300 characters as the error summary
                error_text = result_text.strip()[:300]

        record = ToolCallRecord(
            name=name,
            action=action,
            project_path=project_path,
            file_path=file_path,
            success=success,
            error_text=error_text,
        )
        with self._lock:
            self._calls.append(record)
        logger.debug("tracker record: %s/%s success=%s", name, action, success)

    def get_recent(self, n: int = 30) -> list[ToolCallRecord]:
        """Return the most recent N records (thread-safe snapshot)."""
        with self._lock:
            return list(self._calls)[-n:]

    def clear(self) -> None:
        """Clear the tracking log."""
        with self._lock:
            self._calls.clear()

    # ── Pattern detection ──

    def suggest(self) -> Optional[dict]:
        """Analyze recent call history and detect experience patterns worth saving.

        Returns:
            A prefilled experience draft dict (with problem, solution, tags, context),
            or None (no valuable pattern detected).
        """
        calls = self.get_recent(30)
        if len(calls) < 2:
            return None

        # ── Detect fix cycle (fix_cycle) ──
        result = self._detect_fix_cycle(calls)
        if result:
            return result

        # ── Detect learn-apply cycle (learn_apply) ──
        result = self._detect_learn_apply(calls)
        if result:
            return result

        # ── Detect clean modification (clean_fix) ──
        result = self._detect_clean_fix(calls)
        if result:
            return result

        return None

    def _detect_fix_cycle(self, calls: list[ToolCallRecord]) -> Optional[dict]:
        """Detect: compile fail → file write → compile success"""
        # Find the most recent successful compile
        success_compile_idx = None
        for i in range(len(calls) - 1, -1, -1):
            c = calls[i]
            if c.name in ("delphi_project", "compile_project") and c.action == "compile" and c.success:
                success_compile_idx = i
                break

        if success_compile_idx is None or success_compile_idx < 2:
            return None

        # Find the file write before it
        write_indices = []
        for i in range(success_compile_idx - 1, -1, -1):
            c = calls[i]
            if c.name == "delphi_file" and c.action in ("write", "replace", "insert", "delete"):
                write_indices.append(i)
                if len(write_indices) >= 3:  # Look at most 3 write operations
                    break

        if not write_indices:
            return None

        # Find a failed compile before or between the writes
        last_write_idx = write_indices[-1]
        for i in range(last_write_idx - 1, -1, -1):
            c = calls[i]
            if c.name in ("delphi_project", "compile_project") and c.action == "compile" and not c.success:
                return self._build_draft("fix_cycle", calls, i, success_compile_idx,
                                         write_indices, "fixed compile errors")

        return None

    def _detect_learn_apply(self, calls: list[ToolCallRecord]) -> Optional[dict]:
        """Detect: delphi_kb search → file write → compile success"""
        success_compile_idx = None
        for i in range(len(calls) - 1, -1, -1):
            c = calls[i]
            if c.name in ("delphi_project", "compile_project") and c.action == "compile" and c.success:
                success_compile_idx = i
                break

        if success_compile_idx is None or success_compile_idx < 2:
            return None

        # Find the write before compile
        write_indices = []
        for i in range(success_compile_idx - 1, -1, -1):
            c = calls[i]
            if c.name == "delphi_file" and c.action == "write":
                write_indices.append(i)
                if len(write_indices) >= 2:
                    break

        if not write_indices:
            return None

        # Find the kb search before the write
        last_write_idx = write_indices[-1]
        for i in range(last_write_idx - 1, -1, -1):
            c = calls[i]
            if c.name == "delphi_kb" and c.action == "search" and c.success:
                return self._build_draft("learn_apply", calls, i, success_compile_idx,
                                         write_indices, "modified code after referencing the knowledge base")

        return None

    def _detect_clean_fix(self, calls: list[ToolCallRecord]) -> Optional[dict]:
        """Detect: file write → compile success (no preceding failure, pure modification)"""
        success_compile_idx = None
        for i in range(len(calls) - 1, -1, -1):
            c = calls[i]
            if c.name in ("delphi_project", "compile_project") and c.action == "compile" and c.success:
                success_compile_idx = i
                break

        if success_compile_idx is None or success_compile_idx < 1:
            return None

        # Find the write before compile (within at most 5 calls)
        write_indices = []
        for i in range(success_compile_idx - 1, max(-1, success_compile_idx - 6), -1):
            c = calls[i]
            if c.name == "delphi_file" and c.action in ("write", "replace", "insert", "delete"):
                write_indices.append(i)
                if len(write_indices) >= 3:
                    break

        if not write_indices:
            return None

        # Confirm there is no preceding compile fail
        for i in range(min(write_indices) - 1, max(-1, min(write_indices) - 3), -1):
            c = calls[i]
            if c.name in ("delphi_project", "compile_project") and c.action == "compile" and not c.success:
                return None  # Has a failed compile → belongs to fix_cycle, not clean_fix

        return self._build_draft("clean_fix", calls, write_indices[-1],
                                 success_compile_idx, write_indices, "code modification passed compilation")

    # ── Draft construction ──

    def _build_draft(self, pattern: str, calls: list[ToolCallRecord],
                     start_idx: int, end_idx: int,
                     write_indices: list[int],
                     summary: str) -> dict:
        """Build an experience draft.

        Args:
            pattern: Detected pattern name
            calls: Full call list
            start_idx: Start index (earliest relevant call)
            end_idx: End index (latest relevant call)
            write_indices: List of write operation indices
            summary: Classification summary

        Returns:
            A prefilled experience draft
        """
        relevant = calls[start_idx:end_idx + 1]
        file_paths = sorted(set(
            c.file_path for c in relevant if c.file_path
        ))

        # Collect compile errors
        compile_errors = []
        for c in relevant:
            if c.name in ("delphi_project", "compile_project") and not c.success and c.error_text:
                compile_errors.append(c.error_text)

        # Build problem description
        if compile_errors:
            problem = f"[Auto] {summary}: compile error fixed\n\n"
            for err in compile_errors[:3]:
                problem += f"  - {err[:200]}\n"
        elif pattern == "learn_apply":
            problem = f"[Auto] {summary}: applied modification after querying the knowledge base"
        else:
            files_str = ", ".join(Path(p).name for p in file_paths[:5])
            problem = f"[Auto] {summary}: {files_str}"

        # Build solution description
        solution_parts = [f"Detected pattern: {pattern}"]
        if file_paths:
            solution_parts.append(f"\nFiles involved:\n" + "\n".join(f"  - {p}" for p in file_paths[:8]))
        if compile_errors:
            solution_parts.append(f"\nCompile errors fixed:\n" + "\n".join(f"  - {e[:150]}" for e in compile_errors[:5]))
        solution = "\n".join(solution_parts)

        # Operation sequence timeline
        timeline = []
        for c in relevant:
            action_desc = f"{c.name}/{c.action}"
            status = "✓" if c.success else "✗"
            target = c.file_path or c.project_path or ""
            timeline.append(f"  {status} {action_desc} {Path(target).name if target else ''}")
        solution += "\n\nOperation sequence:\n" + "\n".join(timeline)

        tags = ["auto-saved"]
        if pattern == "fix_cycle":
            tags.extend(["compile", "bugfix"])
        elif pattern == "learn_apply":
            tags.extend(["knowledge-base", "code"])
        elif pattern == "clean_fix":
            tags.extend(["compile", "code"])

        context = {
            "auto_saved": True,
            "pattern": pattern,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "problem": problem,
            "solution": solution,
            "tags": tags,
            "context": context,
        }


# Global singleton
_instance: Optional[ExperienceTracker] = None
_instance_lock = threading.Lock()


def get_tracker() -> ExperienceTracker:
    """Get the global ExperienceTracker instance (singleton)"""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ExperienceTracker()
    return _instance