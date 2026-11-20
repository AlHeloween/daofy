"""
Command-line argument model

Defines the data models related to command-line arguments.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


@dataclass
class CommandArgs:
    """Command-line arguments"""
    compiler_executable: str
    project_file: str
    arguments: List[str]
    full_command: str
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary"""
        return asdict(self)

    def has_warnings(self) -> bool:
        """Whether there are warnings"""
        return len(self.warnings) > 0

    def get_argument_string(self) -> str:
        """Get the argument string (excluding the compiler path)"""
        return " ".join(self.arguments)
