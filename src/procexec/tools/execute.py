"""execute_command tool implementation with security measures."""

import shlex
import subprocess
import time
from pathlib import Path

from mcp.server.fastmcp import Context

from ..server import config, mcp
from ..utils.validation import (
    SanitizedError,
    sanitize_error_message,
    validate_directory,
)
from .schemas import ExecuteCommandInput, ExecuteCommandOutput


def _parse_command_to_args(command: str) -> list[str]:
    """Parse command string into argument list for safe subprocess execution.

    Uses shlex.split() with posix=True to properly remove quotes from arguments.
    This works correctly on both Windows and Unix platforms.

    Args:
        command: Command string to parse

    Returns:
        List of command arguments

    Security:
        - Uses shlex.split instead of manual parsing
        - posix=True removes quotes from arguments (correct behavior for subprocess)
        - Results in argument list for subprocess.run (no shell=True)

    Examples:
        >>> _parse_command_to_args("python --version")
        ['python', '--version']
        >>> _parse_command_to_args('echo "hello world"')
        ['echo', 'hello world']
        >>> _parse_command_to_args('python -c "print(\'test\')"')
        ['python', '-c', "print('test')"]
    """
    # Use posix=True on all platforms for consistent quote removal
    # This is the correct behavior for subprocess.run() which expects
    # arguments without surrounding quotes
    try:
        args = shlex.split(command, posix=True)
        if not args:
            raise ValueError("Command cannot be empty after parsing")
        return args
    except ValueError as e:
        raise SanitizedError(
            f"Failed to parse command: {sanitize_error_message(str(e))}",
            original_error=e,
        )


def _validate_working_directory(working_dir: str | None) -> Path | None:
    """Validate working directory if provided.

    Args:
        working_dir: Working directory path or None

    Returns:
        Validated Path object or None

    Raises:
        SanitizedError: If directory validation fails
    """
    if working_dir is None:
        return None

    try:
        return validate_directory(working_dir)
    except ValueError as e:
        raise SanitizedError(
            f"Invalid working directory: {sanitize_error_message(str(e))}",
            original_error=e,
        )


def _enforce_output_limit(output: str, max_bytes: int) -> tuple[str, bool]:
    """Enforce output size limit to prevent memory exhaustion.

    Args:
        output: Output string to check
        max_bytes: Maximum allowed bytes

    Returns:
        Tuple of (potentially truncated output, was_truncated)

    Examples:
        >>> _enforce_output_limit("short", 1000)
        ('short', False)
        >>> _enforce_output_limit("x" * 2000, 1000)
        ('x' * 1000 + '\\n[Output truncated...]', True)
    """
    output_bytes = output.encode("utf-8", errors="replace")

    if len(output_bytes) <= max_bytes:
        return output, False

    # Truncate to max size
    truncated_bytes = output_bytes[:max_bytes]
    truncated_str = truncated_bytes.decode("utf-8", errors="replace")

    # Add truncation marker
    truncated_str += "\n[Output truncated...]"

    return truncated_str, True


def _execute_subprocess(
    args: list[str], cwd: Path | None, timeout_seconds: float, capture_output: bool
) -> tuple[str, str, int, bool]:
    """Execute command via subprocess with security measures.

    Args:
        args: Command arguments list
        cwd: Working directory or None
        timeout_seconds: Timeout in seconds
        capture_output: Whether to capture stdout/stderr

    Returns:
        Tuple of (stdout, stderr, exit_code, timed_out)

    Raises:
        SanitizedError: If command execution fails

    Security:
        - NEVER uses shell=True
        - Enforces timeout
        - Handles all exception types
        - Sanitizes error messages
    """
    try:
        # noqa justification: arbitrary command execution is this tool's
        # documented purpose; shell=False + list-form args (no shell
        # parsing) is the mitigation, not an oversight.
        result = subprocess.run(  # noqa: S603
            args,
            capture_output=capture_output,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            cwd=str(cwd) if cwd else None,
            shell=False,  # CRITICAL: Never use shell=True
            check=False,  # Don't raise on non-zero exit
            stdin=subprocess.DEVNULL,  # Prevent stdin hang on Windows
        )

        stdout = result.stdout if result.stdout else ""
        stderr = result.stderr if result.stderr else ""
        exit_code = result.returncode

        return stdout, stderr, exit_code, False

    except subprocess.TimeoutExpired:
        # Command exceeded timeout
        return "", f"Command exceeded timeout of {timeout_seconds}s", -1, True

    except FileNotFoundError:
        # Command not found
        raise SanitizedError(
            f"Command not found: {args[0]}. "
            "Ensure the command is installed and in PATH.",
            original_error=None,
        )

    except PermissionError as e:
        # Permission denied
        raise SanitizedError(
            f"Permission denied executing command: {sanitize_error_message(str(e))}",
            original_error=e,
        )

    except OSError as e:
        # Other OS errors
        raise SanitizedError(
            f"OS error executing command: {sanitize_error_message(str(e))}",
            original_error=e,
        )

    except Exception as e:
        # Unexpected errors
        raise SanitizedError(
            f"Unexpected error executing command: {type(e).__name__}", original_error=e
        )


@mcp.tool()
async def execute_command(
    command: str,
    working_directory: str | None = None,
    timeout_ms: int = 30000,
    capture_output: bool = True,
    ctx: Context | None = None,
) -> ExecuteCommandOutput:
    """Execute a command safely with timeout and output limits.

    This tool executes commands without shell injection vulnerabilities.
    Commands are parsed into argument lists and executed directly via
    subprocess without shell=True.

    Args:
        command: Command to execute (e.g., "python --version", "npm test")
        working_directory: Working directory for execution (default: current)
        timeout_ms: Timeout in milliseconds (default: 30000, max: 300000)
        capture_output: Whether to capture stdout/stderr (default: True)
        ctx: MCP context for logging (optional)

    Returns:
        ExecuteCommandOutput with stdout, stderr, exit code, and timing

    Raises:
        ValueError: If input validation fails
        SanitizedError: If command execution fails

    Security:
        - No shell=True (prevents shell injection)
        - Command parsed with shlex.split (safe parsing)
        - Mandatory timeout enforcement
        - Output size limits (prevents memory exhaustion)
        - Path validation for working directory
        - Sanitized error messages (no information leakage)

    Examples:
        >>> result = await execute_command("python --version")
        >>> print(result.stdout)  # "Python 3.11.5"
        >>> print(result.exit_code)  # 0

        >>> result = await execute_command(
        ...     "npm test",
        ...     working_directory="./myproject",
        ...     timeout_ms=60000
        ... )
    """
    start_time = time.time()

    # Validate inputs via Pydantic
    input_data = ExecuteCommandInput(
        command=command,
        working_directory=working_directory,
        timeout_ms=timeout_ms,
        capture_output=capture_output,
    )

    if ctx:
        await ctx.info(f"Executing command: {input_data.command}")

    # Parse command into argument list (security critical)
    args = _parse_command_to_args(input_data.command)

    # Validate working directory if provided
    cwd = _validate_working_directory(input_data.working_directory)

    # Execute command with timeout
    timeout_seconds = input_data.timeout_ms / 1000.0
    stdout, stderr, exit_code, timed_out = _execute_subprocess(
        args=args,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        capture_output=input_data.capture_output,
    )

    # Enforce output size limits
    max_output = config.max_output_bytes
    stdout, stdout_truncated = _enforce_output_limit(stdout, max_output)
    stderr, stderr_truncated = _enforce_output_limit(stderr, max_output)
    output_truncated = stdout_truncated or stderr_truncated

    # Calculate execution time
    execution_time_ms = int((time.time() - start_time) * 1000)

    if ctx:
        await ctx.info(
            f"Command completed: exit_code={exit_code}, "
            f"time={execution_time_ms}ms, timed_out={timed_out}"
        )

    return ExecuteCommandOutput(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        execution_time_ms=execution_time_ms,
        timed_out=timed_out,
        output_truncated=output_truncated,
    )
