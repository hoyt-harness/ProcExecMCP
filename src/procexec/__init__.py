"""ProcExecMCP - Stateless command execution and process management MCP server.

This package provides four MCP tools for Claude to perform architectural code review:
- search_file_contents: Search for patterns in file contents using ripgrep
- execute_command: Execute commands safely with timeout and output limits
- list_processes: List running processes with filtering and sorting
- kill_process: Terminate processes by PID

Security is paramount: no shell injection, mandatory timeouts, resource limits,
path validation, and sanitized error messages.
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("procexec")
except PackageNotFoundError:
    __version__ = "unknown"
__all__ = [
    "search_file_contents",
    "execute_command",
    "list_processes",
    "kill_process",
]
