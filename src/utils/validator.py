"""
Validation utilities

Provides common validation helpers.
"""

import os
from pathlib import Path
from typing import Tuple
from ..utils.logger import get_logger

logger = get_logger(__name__)


class Validator:
    """Validation helper class."""

    @staticmethod
    def validate_project_path(path: str) -> Tuple[bool, str]:
        """
        Validate a project path.

        Args:
            path: Project file path

        Returns:
            (is_valid, error_message)
        """
        if not path:
            return False, "Project path must not be empty"

        # Use Path.parts to detect path traversal (more accurate than a plain ".." in path)
        if ".." in Path(path).parts:
            return False, "Project path must not contain '..'"

        # Check that the file exists
        if not os.path.exists(path):
            return False, f"Project file does not exist: {path}"

        # Check that the path is a file
        if not os.path.isfile(path):
            return False, f"Project path is not a file: {path}"

        # Check the file extension
        if not (path.endswith('.dproj') or path.endswith('.dpr')):
            return False, f"Project file must be a .dproj or .dpr file"

        logger.debug(f"Project path validated: {path}")
        return True, ""

    @staticmethod
    def validate_file_path(path: str) -> Tuple[bool, str]:
        """
        Validate a file path.

        Args:
            path: File path

        Returns:
            (is_valid, error_message)
        """
        if not path:
            return False, "File path must not be empty"

        # Use Path.parts to detect path traversal
        if ".." in Path(path).parts:
            return False, "File path must not contain '..'"

        # Check that the file exists
        if not os.path.exists(path):
            return False, f"File does not exist: {path}"

        # Check that the path is a file
        if not os.path.isfile(path):
            return False, f"Path is not a file: {path}"

        # Check the file extension
        if not path.endswith('.pas'):
            return False, f"File must be a .pas file"

        logger.debug(f"File path validated: {path}")
        return True, ""

    @staticmethod
    def validate_compiler_path(path: str) -> Tuple[bool, str]:
        """
        Validate a compiler path.

        Args:
            path: Compiler executable path

        Returns:
            (is_valid, error_message)
        """
        if not path:
            return False, "Compiler path must not be empty"

        # Strip trailing whitespace (paths read from the registry may carry extra spaces)
        path = path.strip()

        # Use Path.parts to detect path traversal
        if ".." in Path(path).parts:
            return False, "Compiler path must not contain '..'"

        # Check that the file exists
        if not os.path.exists(path):
            return False, f"Compiler file does not exist: {path}"

        # Check that the path is a file
        if not os.path.isfile(path):
            return False, f"Compiler path is not a file: {path}"

        # Check that it is an executable (case-insensitive; .EXE is equally valid on Windows)
        if not (path.lower().endswith('.exe') or path.lower().endswith('.bat') or path.lower().endswith('.cmd')):
            return False, f"Compiler must be an executable (.exe, .bat, .cmd), current path: {path}"

        logger.debug(f"Compiler path validated: {path}")
        return True, ""

    @staticmethod
    def validate_output_path(path: str) -> Tuple[bool, str]:
        """
        Validate an output path.

        Args:
            path: Output directory path

        Returns:
            (is_valid, error_message)
        """
        if not path:
            return True, ""  # Output path is optional; the default path is used when empty

        # Use Path.parts to detect path traversal
        if ".." in Path(path).parts:
            return False, "Output path must not contain '..'"

        # Check that the directory exists
        if not os.path.exists(path):
            return False, f"Output directory does not exist: {path}"

        # Check that the path is a directory
        if not os.path.isdir(path):
            return False, f"Output path is not a directory: {path}"

        # Check write permission
        if not os.access(path, os.W_OK):
            return False, f"Output directory is not writable: {path}"

        logger.debug(f"Output path validated: {path}")
        return True, ""

    @staticmethod
    def validate_search_paths(paths: list) -> Tuple[bool, str]:
        """
        Validate a list of search paths.

        Args:
            paths: List of search paths

        Returns:
            (is_valid, error_message)
        """
        if not paths:
            return True, ""  # Search paths are optional

        for path in paths:
            # Use Path.parts to detect path traversal
            if ".." in Path(path).parts:
                return False, f"Search path must not contain '..': {path}"

            # Check that the directory exists
            if not os.path.exists(path):
                logger.warning(f"Search path does not exist: {path}")
                # Do not block the build; record a warning only

        logger.debug(f"Search paths validated")
        return True, ""

    @staticmethod
    def validate_timeout(timeout: int) -> Tuple[bool, str]:
        """
        Validate a timeout value.

        Args:
            timeout: Timeout in seconds

        Returns:
            (is_valid, error_message)
        """
        if timeout <= 0:
            return False, f"Timeout must be a positive number: {timeout}"

        if timeout > 3600:  # Maximum 1 hour
            return False, f"Timeout must not exceed 3600 seconds: {timeout}"

        logger.debug(f"Timeout validated: {timeout}")
        return True, ""

    @staticmethod
    def validate_warning_level(level: int) -> Tuple[bool, str]:
        """
        Validate a warning level.

        Args:
            level: Warning level (0-4)

        Returns:
            (is_valid, error_message)
        """
        if not 0 <= level <= 4:
            return False, f"Warning level must be between 0 and 4: {level}"

        logger.debug(f"Warning level validated: {level}")
        return True, ""
