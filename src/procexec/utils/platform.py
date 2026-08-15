# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-platform utility functions for detecting and handling platform differences."""

import platform


def get_platform() -> str:
    """Get the current platform.

    Returns:
        "windows" if running on Windows, "unix" otherwise (Linux, macOS, etc.)

    Examples:
        >>> get_platform()
        'windows'  # on Windows
        'unix'     # on Linux/macOS
    """
    return "windows" if platform.system() == "Windows" else "unix"


def is_windows() -> bool:
    """Check if running on Windows.

    Returns:
        True if running on Windows, False otherwise

    Examples:
        >>> is_windows()
        True  # on Windows
        False # on Unix
    """
    return platform.system() == "Windows"


def is_unix() -> bool:
    """Check if running on Unix (Linux, macOS, etc.).

    Returns:
        True if running on Unix, False if on Windows

    Examples:
        >>> is_unix()
        False  # on Windows
        True   # on Linux/macOS
    """
    return not is_windows()
