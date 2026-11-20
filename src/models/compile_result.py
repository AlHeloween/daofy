"""
Compile result model

Defines the data models related to compilation results.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum
from pathlib import Path


class CompileStatus(Enum):
    """Compile status enum"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class CompileMessage:
    """Compile message (error or warning)"""
    file_path: str
    line: int
    column: int
    message: str
    message_type: str  # "error" | "warning" | "fatal"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary"""
        return asdict(self)


@dataclass
class CompileResult:
    """Compile result"""
    status: CompileStatus
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    output_file: Optional[str] = None
    output_files: List[str] = field(default_factory=list)  # Paths of all output artifacts (exe/dll/bpl/bpi/dcp, etc.)
    warnings: List[CompileMessage] = field(default_factory=list)
    errors: List[CompileMessage] = field(default_factory=list)
    duration: int = 0  # milliseconds
    log: str = ""  # Full compile log

    def to_dict(self, strip_log: bool = True) -> Dict[str, Any]:
        """Convert to a dictionary

        Args:
            strip_log: Whether to strip the compiler copyright banner (Embarcadero / Copyright lines)
        """
        log = self._strip_compiler_header(self.log) if strip_log else self.log
        result: Dict[str, Any] = {
            "status": self.status.value,
            "duration": self.duration,
        }
        # List of output artifacts (the first item is the main target file: exe/dll/bpl)
        if self.output_files:
            result["output_files"] = self.output_files
        if self.status != CompileStatus.SUCCESS:
            if self.error_code:
                result["error_code"] = self.error_code
            if self.error_message:
                result["error_message"] = self.error_message
        if self.errors:
            result["errors"] = [e.to_dict() for e in self.errors]
        if self.warnings:
            result["warnings"] = [w.to_dict() for w in self.warnings]
        if log:
            result["log"] = log
        return result

    @staticmethod
    def _strip_compiler_header(log: str) -> str:
        """Remove the repeated copyright/version banner lines from compiler output

        MSBuild output:
          Microsoft(R) 生成引擎版本 4.8.9221.0
          [Microsoft .NET Framework 版本 4.0.30319.42000]
          版权所有 (C) Microsoft Corporation。保留所有权利。
        dcc32 output:
          Embarcadero Delphi for Win32 compiler version 37.0
          Copyright (c) 1983,2026 Embarcadero Technologies, Inc.
        Useful lines kept:
          256 lines, 0.14 seconds, 1000288 bytes code, 44080 bytes data.
        """
        if not log:
            return log
        lines = log.splitlines(keepends=True)
        keep = []
        for l in lines:
            s = l.strip()
            if not s:
                continue
            # MSBuild version banner
            if s.startswith('Microsoft(') or s.startswith('[Microsoft .NET Framework'):
                continue
            # MSBuild Chinese copyright line
            if s.startswith('版权所有'):
                continue
            # Delphi compiler version + copyright
            if s.startswith('Embarcadero Delphi') or s.startswith('Copyright (c)'):
                continue
            keep.append(l)
        return ''.join(keep)

    def has_errors(self) -> bool:
        """Whether there are errors"""
        return len(self.errors) > 0 or self.status == CompileStatus.FAILED

    def has_warnings(self) -> bool:
        """Whether there are warnings"""
        return len(self.warnings) > 0

    def get_error_count(self) -> int:
        """Get the error count"""
        return len(self.errors)

    def get_warning_count(self) -> int:
        """Get the warning count"""
        return len(self.warnings)

    def get_summary(self) -> str:
        """Get a compile result summary"""
        if self.status == CompileStatus.SUCCESS:
            return f"Compile succeeded, took {self.duration}ms, {self.get_warning_count()} warning(s)"
        elif self.status == CompileStatus.TIMEOUT:
            return f"Compile timed out, took {self.duration}ms"
        else:
            return f"Compile failed, {self.get_error_count()} error(s), {self.get_warning_count()} warning(s), took {self.duration}ms"
