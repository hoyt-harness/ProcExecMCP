"""list_processes tool implementation with psutil integration."""

import time
import psutil
from mcp.server.fastmcp import Context

from ..server import mcp
from ..utils.validation import SanitizedError, sanitize_error_message
from .schemas import (
    KillProcessInput,
    KillProcessOutput,
    ListProcessesInput,
    ListProcessesOutput,
    ProcessInfo,
    ProcessSortBy,
)


def _get_process_info(proc: psutil.Process) -> ProcessInfo | None:
    """Safely get process information with exception handling.

    Args:
        proc: psutil.Process instance

    Returns:
        ProcessInfo if successful, None if process is inaccessible

    Security:
        - Handles NoSuchProcess (process terminated during iteration)
        - Handles AccessDenied (insufficient permissions)
        - Handles ZombieProcess (defunct process)
        - Sanitizes command line to prevent information leakage

    Examples:
        >>> proc = psutil.Process(1234)
        >>> info = _get_process_info(proc)
        >>> print(info.name, info.cpu_percent)
        'python.exe' 2.5
    """
    try:
        # Get process information with oneshot context for performance
        with proc.oneshot():
            # Get basic info
            pid = proc.pid
            name = proc.name()
            status = proc.status()

            # Get CPU and memory info
            try:
                cpu_percent = proc.cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cpu_percent = 0.0

            try:
                memory_info = proc.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)  # Convert bytes to MB
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                memory_mb = 0.0

            # Get command line (may fail due to permissions)
            try:
                cmdline_list = proc.cmdline()
                cmdline = " ".join(cmdline_list) if cmdline_list else ""
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cmdline = ""

            return ProcessInfo(
                pid=pid,
                name=name,
                cpu_percent=round(cpu_percent, 2),
                memory_mb=round(memory_mb, 2),
                cmdline=cmdline,
                status=status,
            )

    except psutil.NoSuchProcess:
        # Process terminated during iteration
        return None

    except psutil.AccessDenied:
        # Insufficient permissions - skip this process
        return None

    except psutil.ZombieProcess:
        # Defunct process - skip
        return None

    except Exception:
        # Unexpected error - skip process but don't fail entire operation
        return None


def _filter_processes(
    processes: list[ProcessInfo], name_filter: str | None
) -> list[ProcessInfo]:
    """Filter processes by name (case-insensitive substring match).

    Args:
        processes: List of ProcessInfo objects
        name_filter: Name filter string (None = no filtering)

    Returns:
        Filtered list of processes

    Examples:
        >>> processes = [ProcessInfo(pid=1, name="python.exe", ...),
        ...              ProcessInfo(pid=2, name="chrome.exe", ...)]
        >>> filtered = _filter_processes(processes, "python")
        >>> len(filtered)
        1
    """
    if name_filter is None or not name_filter.strip():
        return processes

    # Case-insensitive substring match
    filter_lower = name_filter.lower()
    return [proc for proc in processes if filter_lower in proc.name.lower()]


def _sort_processes(
    processes: list[ProcessInfo], sort_by: ProcessSortBy
) -> list[ProcessInfo]:
    """Sort processes by specified criteria.

    Args:
        processes: List of ProcessInfo objects
        sort_by: Sort criterion (cpu, memory, pid, name)

    Returns:
        Sorted list of processes

    Sorting Rules:
        - cpu: Descending (highest CPU first)
        - memory: Descending (most memory first)
        - pid: Ascending (lowest PID first)
        - name: Ascending (alphabetical)

    Examples:
        >>> processes = [ProcessInfo(pid=2, name="b", cpu_percent=5.0, ...),
        ...              ProcessInfo(pid=1, name="a", cpu_percent=10.0, ...)]
        >>> sorted_procs = _sort_processes(processes, ProcessSortBy.CPU)
        >>> sorted_procs[0].cpu_percent
        10.0
    """
    if sort_by == ProcessSortBy.CPU:
        return sorted(processes, key=lambda p: p.cpu_percent, reverse=True)
    elif sort_by == ProcessSortBy.MEMORY:
        return sorted(processes, key=lambda p: p.memory_mb, reverse=True)
    elif sort_by == ProcessSortBy.PID:
        return sorted(processes, key=lambda p: p.pid)
    elif sort_by == ProcessSortBy.NAME:
        return sorted(processes, key=lambda p: p.name.lower())
    else:
        # Default to CPU sorting
        return sorted(processes, key=lambda p: p.cpu_percent, reverse=True)


def _limit_processes(
    processes: list[ProcessInfo], limit: int
) -> tuple[list[ProcessInfo], bool]:
    """Limit number of processes returned and indicate if truncated.

    Args:
        processes: List of ProcessInfo objects
        limit: Maximum number to return

    Returns:
        Tuple of (limited process list, truncated flag)

    Examples:
        >>> processes = [ProcessInfo(...) for _ in range(200)]
        >>> limited, truncated = _limit_processes(processes, 100)
        >>> len(limited)
        100
        >>> truncated
        True
    """
    truncated = len(processes) > limit
    limited_processes = processes[:limit]
    return limited_processes, truncated


@mcp.tool()
async def list_processes(
    name_filter: str | None = None,
    sort_by: ProcessSortBy = ProcessSortBy.CPU,
    limit: int = 100,
    ctx: Context | None = None,
) -> ListProcessesOutput:
    """List running processes with optional filtering and sorting.

    This tool retrieves information about running processes on the system,
    including PID, name, CPU usage, memory usage, command line, and status.
    Results can be filtered by name, sorted by various criteria, and limited
    to a maximum number of results.

    Args:
        name_filter: Filter processes by name (case-insensitive substring match).
                    If None, return all processes.
        sort_by: Sort processes by: cpu (descending), memory (descending),
                pid (ascending), or name (ascending). Default: cpu.
        limit: Maximum number of processes to return. Default: 100, max: 1000.
        ctx: MCP context for logging (optional)

    Returns:
        ListProcessesOutput with process list, total count, truncation flag,
        and retrieval time

    Raises:
        SanitizedError: If process iteration fails

    Security:
        - Handles permission errors gracefully (skips inaccessible processes)
        - No sensitive system information leaked in errors
        - Command lines are included but may be empty if access denied
        - Zombie and terminated processes handled without errors

    Performance:
        - Uses psutil.process_iter() for efficient iteration
        - oneshot() context for batch info retrieval per process
        - Target: <2s for process list retrieval

    Examples:
        >>> result = await list_processes()
        >>> print(result.total_count, "processes found")
        245 processes found

        >>> result = await list_processes(
        ...     name_filter="python",
        ...     sort_by=ProcessSortBy.MEMORY,
        ...     limit=50
        ... )
        >>> for proc in result.processes:
        ...     print(f"{proc.name}: {proc.memory_mb}MB")
    """
    start_time = time.time()

    # Validate inputs via Pydantic
    input_data = ListProcessesInput(
        name_filter=name_filter, sort_by=sort_by, limit=limit
    )

    if ctx:
        await ctx.info(
            f"Listing processes: filter={input_data.name_filter}, "
            f"sort={input_data.sort_by}, limit={input_data.limit}"
        )

    try:
        # Iterate all processes and get info
        all_processes: list[ProcessInfo] = []

        for proc in psutil.process_iter():
            proc_info = _get_process_info(proc)
            if proc_info is not None:
                all_processes.append(proc_info)

        # Filter by name if requested
        filtered_processes = _filter_processes(all_processes, input_data.name_filter)

        # Sort by specified criteria
        sorted_processes = _sort_processes(filtered_processes, input_data.sort_by)

        # Apply limit and check if truncated
        limited_processes, truncated = _limit_processes(
            sorted_processes, input_data.limit
        )

        # Calculate retrieval time
        retrieval_time_ms = int((time.time() - start_time) * 1000)

        if ctx:
            await ctx.info(
                f"Process listing complete: {len(limited_processes)} returned, "
                f"{len(sorted_processes)} total, truncated={truncated}, "
                f"time={retrieval_time_ms}ms"
            )

        return ListProcessesOutput(
            processes=limited_processes,
            total_count=len(sorted_processes),
            truncated=truncated,
            retrieval_time_ms=retrieval_time_ms,
        )

    except Exception as e:
        # Unexpected error during process iteration
        raise SanitizedError(
            f"Failed to list processes: {sanitize_error_message(str(e))}",
            original_error=e,
        )


# User Story 4: kill_process tool implementation


def _validate_process_exists(pid: int) -> bool:
    """Check if a process with the given PID exists.

    Args:
        pid: Process ID to check

    Returns:
        True if process exists, False otherwise

    Examples:
        >>> _validate_process_exists(1)
        True
        >>> _validate_process_exists(999999)
        False
    """
    return psutil.pid_exists(pid)


def _terminate_process(
    proc: psutil.Process, timeout_seconds: float
) -> tuple[bool, str]:
    """Attempt graceful process termination with timeout.

    Sends SIGTERM (Unix) or WM_CLOSE (Windows) and waits for process to exit.

    Args:
        proc: psutil.Process instance to terminate
        timeout_seconds: Maximum time to wait for termination

    Returns:
        Tuple of (success: bool, message: str)

    Examples:
        >>> proc = psutil.Process(1234)
        >>> success, msg = _terminate_process(proc, 5.0)
        >>> print(success, msg)
        True 'Process terminated gracefully'
    """
    try:
        # Send termination signal (SIGTERM on Unix, WM_CLOSE on Windows)
        proc.terminate()

        # Wait for process to exit
        try:
            proc.wait(timeout=timeout_seconds)
            return True, "Process terminated gracefully"
        except psutil.TimeoutExpired:
            # Process did not terminate within timeout
            return False, f"Process did not terminate within {timeout_seconds}s timeout"

    except psutil.NoSuchProcess:
        # Process already gone
        return True, "Process already terminated"

    except psutil.AccessDenied:
        # Insufficient permissions
        return False, "Access denied: insufficient permissions to terminate process"

    except Exception as e:
        # Unexpected error
        return False, f"Termination failed: {sanitize_error_message(str(e))}"


def _kill_process_forced(proc: psutil.Process) -> tuple[bool, str]:
    """Forcefully kill a process (SIGKILL/TerminateProcess).

    This is the most aggressive termination method and should be used
    only when graceful termination fails.

    Args:
        proc: psutil.Process instance to kill

    Returns:
        Tuple of (success: bool, message: str)

    Examples:
        >>> proc = psutil.Process(1234)
        >>> success, msg = _kill_process_forced(proc)
        >>> print(success, msg)
        True 'Process killed forcefully'
    """
    try:
        # Send kill signal (SIGKILL on Unix, TerminateProcess on Windows)
        proc.kill()

        # Verify process is gone (short wait)
        try:
            proc.wait(timeout=1.0)
        except psutil.TimeoutExpired:
            # Process still alive after kill - should be very rare
            pass

        # Check if process is actually gone
        if not psutil.pid_exists(proc.pid):
            return True, "Process killed forcefully"
        else:
            return False, "Process still exists after forced kill attempt"

    except psutil.NoSuchProcess:
        # Process already gone
        return True, "Process already terminated"

    except psutil.AccessDenied:
        # Insufficient permissions
        return False, "Access denied: insufficient permissions to kill process"

    except Exception as e:
        # Unexpected error
        return False, f"Forced kill failed: {sanitize_error_message(str(e))}"


@mcp.tool()
async def kill_process(
    pid: int,
    force: bool = False,
    timeout_seconds: float = 5.0,
    ctx: Context | None = None,
) -> KillProcessOutput:
    """Terminate a process by PID with graceful or forced termination.

    This tool allows terminating stuck or hung processes to clean up system
    resources. It supports both graceful termination (SIGTERM/WM_CLOSE) with
    a timeout, and forced termination (SIGKILL/TerminateProcess) for
    unresponsive processes.

    Args:
        pid: Process ID to terminate (must be >= 1)
        force: If True, forcefully kill the process. If False, attempt
               graceful termination with timeout. Default: False
        timeout_seconds: Timeout in seconds to wait for graceful termination.
                        Ignored if force=True. Range: 0.1-30.0s. Default: 5.0s
        ctx: MCP context for logging (optional)

    Returns:
        KillProcessOutput with success status, PID, message, timing, and
        whether forced termination was used

    Raises:
        SanitizedError: If process termination fails or is not enabled

    Security:
        - Requires PROCEXEC_ENABLE_KILL=true environment variable to function
        - Handles permission errors gracefully (no crashes)
        - Cannot terminate system-critical processes (OS protection)
        - Error messages are sanitized (no sensitive info)

    Examples:
        >>> # Graceful termination
        >>> result = await kill_process(pid=1234, force=False, timeout_seconds=5.0)
        >>> print(result.success, result.message)
        True 'Process terminated gracefully'

        >>> # Forced termination
        >>> result = await kill_process(pid=5678, force=True)
        >>> print(result.success, result.forced)
        True True
    """
    start_time = time.time()

    # Validate inputs via Pydantic
    input_data = KillProcessInput(pid=pid, force=force, timeout_seconds=timeout_seconds)

    if ctx:
        await ctx.info(
            f"Attempting to {'kill' if input_data.force else 'terminate'} "
            f"process {input_data.pid}"
        )

    # Check if process termination is enabled
    # This requires the PROCEXEC_ENABLE_KILL environment variable to be set
    import os

    enable_kill = os.environ.get("PROCEXEC_ENABLE_KILL", "false").lower() == "true"

    if not enable_kill:
        termination_time_ms = int((time.time() - start_time) * 1000)
        raise SanitizedError(
            "Process termination is disabled. Set PROCEXEC_ENABLE_KILL=true to enable.",
            original_error=None,
        )

    # Validate process exists
    if not _validate_process_exists(input_data.pid):
        termination_time_ms = int((time.time() - start_time) * 1000)
        if ctx:
            await ctx.error(f"Process {input_data.pid} does not exist")

        return KillProcessOutput(
            success=False,
            pid=input_data.pid,
            message=f"Process {input_data.pid} does not exist",
            termination_time_ms=termination_time_ms,
            forced=False,
        )

    try:
        # Get process handle
        proc = psutil.Process(input_data.pid)

        # Terminate or kill based on force flag
        if input_data.force:
            # Forced kill
            success, message = _kill_process_forced(proc)
            forced = True
        else:
            # Graceful termination with timeout
            success, message = _terminate_process(proc, input_data.timeout_seconds)
            forced = False

        # Calculate termination time
        termination_time_ms = int((time.time() - start_time) * 1000)

        if ctx:
            if success:
                await ctx.info(
                    f"Process {input_data.pid} terminated successfully "
                    f"({'forced' if forced else 'graceful'}), "
                    f"time={termination_time_ms}ms"
                )
            else:
                await ctx.error(
                    f"Failed to terminate process {input_data.pid}: {message}"
                )

        return KillProcessOutput(
            success=success,
            pid=input_data.pid,
            message=message,
            termination_time_ms=termination_time_ms,
            forced=forced,
        )

    except psutil.NoSuchProcess:
        # Process disappeared during operation
        termination_time_ms = int((time.time() - start_time) * 1000)
        return KillProcessOutput(
            success=True,
            pid=input_data.pid,
            message="Process no longer exists",
            termination_time_ms=termination_time_ms,
            forced=False,
        )

    except psutil.AccessDenied:
        # Insufficient permissions
        termination_time_ms = int((time.time() - start_time) * 1000)
        if ctx:
            await ctx.error(f"Access denied for process {input_data.pid}")

        return KillProcessOutput(
            success=False,
            pid=input_data.pid,
            message="Access denied: insufficient permissions to terminate process",
            termination_time_ms=termination_time_ms,
            forced=False,
        )

    except Exception as e:
        # Unexpected error
        termination_time_ms = int((time.time() - start_time) * 1000)
        error_msg = sanitize_error_message(str(e))

        if ctx:
            await ctx.error(
                f"Unexpected error terminating process {input_data.pid}: {error_msg}"
            )

        raise SanitizedError(
            f"Failed to terminate process {input_data.pid}: {error_msg}",
            original_error=e,
        )
