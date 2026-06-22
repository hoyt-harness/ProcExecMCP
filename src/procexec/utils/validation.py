"""Input validation and error sanitization utilities."""

import os
import re
from pathlib import Path


# Default sensitive paths to block (configurable via PROCEXEC_BLOCKED_PATHS)
DEFAULT_BLOCKED_PATHS = [
    "/etc/shadow",
    "/etc/passwd",
    "C:\\Windows\\System32\\config",
    "C:\\Windows\\System32\\drivers",
]


def sanitize_path(path_str: str) -> str:
    """Remove sensitive components from a path for safe error messages.

    Args:
        path_str: Path string to sanitize

    Returns:
        Sanitized path with only basename or placeholder

    Examples:
        >>> sanitize_path("/home/user/project/file.py")
        'file.py'
        >>> sanitize_path("C:\\Users\\Alice\\Documents\\report.txt")
        'report.txt'
    """
    try:
        # Split on both separators explicitly: Path() only recognizes the
        # host OS's separator, so a Windows-style path string ("C:\foo\bar")
        # parsed on POSIX (or vice versa) returns the whole string as a
        # single unsplit component instead of the basename.
        name = path_str.replace("\\", "/").rsplit("/", 1)[-1]
        return name if name else "[path]"
    except Exception:
        return "[path]"


def sanitize_error_message(message: str) -> str:
    """Remove sensitive information from error messages.

    Removes:
    - Absolute paths (Windows and Unix)
    - Usernames
    - IP addresses
    - Home directories

    Args:
        message: Error message to sanitize

    Returns:
        Sanitized error message without sensitive information

    Examples:
        >>> sanitize_error_message("File not found: /home/alice/secret.txt")
        'File not found: secret.txt'
        >>> sanitize_error_message("Connection to 192.168.1.100 failed")
        'Connection to [IP] failed'
    """
    # Replace absolute Windows paths
    message = re.sub(r"[A-Z]:\\[^\s]+", lambda m: sanitize_path(m.group(0)), message)

    # Replace absolute Unix paths
    message = re.sub(
        r"/(?:home|root|Users)/[^\s]+", lambda m: sanitize_path(m.group(0)), message
    )

    # Remove usernames
    message = re.sub(r"user\s+[\w]+", "user [redacted]", message, flags=re.IGNORECASE)

    # Remove IP addresses
    message = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[IP]", message)

    return message


class SanitizedError(Exception):
    """Exception with automatically sanitized error message.

    This exception class automatically sanitizes the error message to remove
    sensitive information like paths, usernames, and IP addresses.

    Args:
        message: The error message to sanitize
        original_error: Optional original exception for debugging

    Attributes:
        original_error: The original exception if provided
    """

    def __init__(self, message: str, original_error: Exception | None = None):
        sanitized = sanitize_error_message(message)
        super().__init__(sanitized)
        self.original_error = original_error


def _get_blocked_paths() -> list[str]:
    """Get list of blocked paths from environment or defaults.

    Returns:
        List of absolute paths to block access to
    """
    env_blocked = os.getenv("PROCEXEC_BLOCKED_PATHS", "")
    if env_blocked:
        paths = [p.strip() for p in env_blocked.split(",") if p.strip()]
        return paths if paths else DEFAULT_BLOCKED_PATHS
    return DEFAULT_BLOCKED_PATHS


def validate_path(path_str: str, must_exist: bool = True) -> Path:
    """Validate a path for security and existence.

    Performs security checks:
    - Resolves to absolute path
    - Checks for path traversal attempts
    - Validates against blocked paths
    - Optionally checks existence

    Args:
        path_str: Path string to validate
        must_exist: Whether path must exist (default: True)

    Returns:
        Resolved absolute Path object

    Raises:
        ValueError: If path is invalid, contains traversal, or is blocked

    Examples:
        >>> validate_path("./src/file.py")
        PosixPath('/absolute/path/to/src/file.py')
        >>> validate_path("../../etc/passwd")
        ValueError: Path traversal not allowed
    """
    try:
        # Resolve to absolute path
        path = Path(path_str).resolve(strict=False)

        # Check if path exists (if required)
        if must_exist and not path.exists():
            raise ValueError(f"Path does not exist: {sanitize_path(str(path))}")

        # Check for traversal attempts (after resolution)
        # Note: This checks if ".." is in the parts, which would indicate traversal
        # even after resolution (unusual but possible with symlinks)
        path_parts = path.parts
        if ".." in path_parts:
            raise ValueError(f"Path traversal not allowed: {sanitize_path(str(path))}")

        # Check against blocked paths
        path_str_normalized = str(path).lower()
        blocked_paths = _get_blocked_paths()
        for blocked in blocked_paths:
            if path_str_normalized.startswith(blocked.lower()):
                raise ValueError(
                    f"Access to sensitive path not allowed: {sanitize_path(str(path))}"
                )

        return path

    except (OSError, RuntimeError) as e:
        raise ValueError(f"Invalid path: {sanitize_error_message(str(e))}")


def validate_directory(path_str: str) -> Path:
    """Validate that a path is a directory.

    Args:
        path_str: Path string to validate

    Returns:
        Resolved absolute Path object

    Raises:
        ValueError: If path is invalid or not a directory

    Examples:
        >>> validate_directory("./src")
        PosixPath('/absolute/path/to/src')
        >>> validate_directory("./file.py")
        ValueError: Path is not a directory
    """
    path = validate_path(path_str, must_exist=True)
    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {sanitize_path(str(path))}")
    return path


def validate_file(path_str: str) -> Path:
    """Validate that a path is a file.

    Args:
        path_str: Path string to validate

    Returns:
        Resolved absolute Path object

    Raises:
        ValueError: If path is invalid or not a file

    Examples:
        >>> validate_file("./src/file.py")
        PosixPath('/absolute/path/to/src/file.py')
        >>> validate_file("./src")
        ValueError: Path is not a file
    """
    path = validate_path(path_str, must_exist=True)
    if not path.is_file():
        raise ValueError(f"Path is not a file: {sanitize_path(str(path))}")
    return path
