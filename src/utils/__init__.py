"""
Utility functions package

Common utility functions such as encoding detection and path handling.
"""

import ctypes
import locale
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_console_encoding(oem: bool = False) -> str:
    """Get the actual encoding of the current console.

    On Windows, the console code page (GetConsoleOutputCP) may differ from the system
    ANSI encoding (locale.getpreferredencoding). For example, when Python runs in
    UTF-8 mode the console code page is 65001 (UTF-8), while the ANSI encoding is
    still cp936 (GBK).

    Use the console code page (oem=False) when decoding subprocess output, so that
    Chinese text displays correctly. Use the OEM code page (oem=True) when writing
    batch files, because cmd.exe only recognizes OEM encodings.

    Args:
        oem: True returns the OEM code page (for batch files); False returns the console code page

    Returns:
        An encoding name string, e.g. 'cp65001', 'cp936', 'utf-8', etc.
    """
    try:
        if oem:
            cp = ctypes.windll.kernel32.GetOEMCP()
        else:
            cp = ctypes.windll.kernel32.GetConsoleOutputCP()
        if cp > 0:
            return f'cp{cp}'
    except Exception as e:
        logger.debug("Failed to get console encoding (falling back to ANSI encoding): %s", e)
    return locale.getpreferredencoding()
