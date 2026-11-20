"""
Output parser

Parses Delphi / FPC compiler output and extracts errors and warnings.
"""

import re
from typing import List
from ..models.compile_result import CompileMessage
from ..utils.logger import get_logger

logger = get_logger(__name__)


class OutputParser:
    """Delphi / FPC compiler output parser"""

    # Standard format: Error: File.pas(10,5): Error message
    # Format: Warning: File.pas(20,10): Warning message
    # Format: Fatal: File.pas(1,1): Fatal error
    MESSAGE_PATTERN = re.compile(
        r'(?P<type>Error|Warning|Fatal):\s+'
        r'(?P<file>[^(]+)\((?P<line>\d+),(?P<column>\d+)\):\s+'
        r'(?P<message>.+)'
    )

    # FPC format: File.pas(13,3) Fatal: (2003) Syntax error message
    # FPC format: File.pas(13,8) Error: (4001) Incompatible types...
    # FPC format: File.pas(13,10) Error: (5000) Identifier not found...
    FPC_MESSAGE_PATTERN = re.compile(
        r'(?P<file>[^(]+)\((?P<line>\d+),(?P<column>\d+)\)\s+'
        r'(?P<type>Error|Fatal|Warning):\s+'
        r'\(?\d+\)?\s*'
        r'(?P<message>.+)'
    )

    # Fatal error pattern (no line number)
    FATAL_PATTERN = re.compile(
        r'Fatal:\s+(?P<message>.+)'
    )

    # FPC fatal error: Fatal: (1018) Compilation aborted
    FPC_FATAL_PATTERN = re.compile(
        r'Fatal:\s+\(\d+\)\s+(?P<message>.+)'
    )

    def parse(self, output: str) -> List[CompileMessage]:
        """
        Parse compiler output (Delphi and FPC formats supported).

        Args:
            output: Compiler output string

        Returns:
            List of compile messages
        """
        messages = []

        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Delphi: Error: File.pas(10,5): message
            # FPC:    File.pas(13,3) Fatal: (2003) message
            match = (
                self.MESSAGE_PATTERN.match(line)
                or self.FPC_MESSAGE_PATTERN.match(line)
            )
            if match:
                message_type = match.group('type').lower()
                if message_type == 'fatal':
                    message_type = 'error'
                messages.append(CompileMessage(
                    file_path=match.group('file').strip(),
                    line=int(match.group('line')),
                    column=int(match.group('column')),
                    message=match.group('message').strip(),
                    message_type=message_type,
                ))
                continue

            # FPC/Fatal without file info: Fatal: (1018) Compilation aborted
            match = self.FPC_FATAL_PATTERN.match(line)
            if match:
                messages.append(CompileMessage(
                    file_path="", line=0, column=0,
                    message=match.group('message').strip(),
                    message_type='error',
                ))
                continue

            # Delphi/Fatal without file info: Fatal: Some error
            match = self.FATAL_PATTERN.match(line)
            if match:
                messages.append(CompileMessage(
                    file_path="", line=0, column=0,
                    message=match.group('message').strip(),
                    message_type='error',
                ))

        logger.debug(f"Parsed {len(messages)} messages")
        return messages

        logger.debug(f"Parsed {len(messages)} messages")
        return messages

    def parse_errors(self, output: str) -> List[CompileMessage]:
        """
        Parse error messages only.

        Args:
            output: Compiler output string

        Returns:
            List of error messages
        """
        messages = self.parse(output)
        errors = [m for m in messages if m.message_type == 'error']
        logger.debug(f"Parsed {len(errors)} errors")
        return errors

    def parse_warnings(self, output: str) -> List[CompileMessage]:
        """
        Parse warning messages only.

        Args:
            output: Compiler output string

        Returns:
            List of warning messages
        """
        messages = self.parse(output)
        warnings = [m for m in messages if m.message_type == 'warning']
        logger.debug(f"Parsed {len(warnings)} warnings")
        return warnings

    def has_errors(self, output: str) -> bool:
        """
        Check whether the output contains errors.

        Args:
            output: Compiler output string

        Returns:
            Whether there are errors
        """
        # Check for Error or Fatal
        return bool(re.search(r'\b(Error|Fatal)\b:', output))

    def has_warnings(self, output: str) -> bool:
        """
        Check whether the output contains warnings.

        Args:
            output: Compiler output string

        Returns:
            Whether there are warnings
        """
        return bool(re.search(r'\bWarning\b:', output))

    def extract_error_summary(self, output: str) -> str:
        """
        Extract an error summary.

        Args:
            output: Compiler output string

        Returns:
            Error summary string
        """
        errors = self.parse_errors(output)
        if not errors:
            return "No errors"

        summary_lines = []
        for error in errors[:5]:  # Show at most the first 5 errors
            if error.file_path:
                summary_lines.append(f"{error.file_path}({error.line},{error.column}): {error.message}")
            else:
                summary_lines.append(error.message)

        if len(errors) > 5:
            summary_lines.append(f"... and {len(errors) - 5} more errors")

        return '\n'.join(summary_lines)
