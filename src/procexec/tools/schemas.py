"""Pydantic schemas for tool input/output validation and error handling."""

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ErrorCategory(str, Enum):
    """Error categories for tool execution failures."""

    VALIDATION = "validation"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    SECURITY = "security"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class ToolError(BaseModel):
    """Standardized error response for tool failures.

    Attributes:
        category: Error category for programmatic handling
        message: Sanitized, human-readable error message
        suggestion: Optional suggestion for resolving the error
    """

    category: ErrorCategory = Field(
        description="Error category for programmatic handling"
    )

    message: str = Field(description="Sanitized, human-readable error message")

    suggestion: str | None = Field(
        default=None, description="Optional suggestion for how to resolve the error"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "category": "timeout",
                    "message": "Command exceeded timeout limit of 30 seconds",
                    "suggestion": (
                        "Try increasing the timeout_ms parameter "
                        "or optimizing the command"
                    ),
                }
            ]
        }
    )


# Input/Output schemas for User Story 1 (search_file_contents)


class SearchFileContentsInput(BaseModel):
    """Input schema for search_file_contents tool."""

    pattern: str = Field(
        description="Regular expression pattern to search for",
        min_length=1,
        max_length=1000,
        examples=["TODO", r"def\s+\w+", r"import\s+\w+"],
    )

    path: str = Field(
        description="File or directory path to search in",
        examples=["C:\\projects\\myapp", "/home/user/code", "./src"],
    )

    case_sensitive: bool = Field(
        default=True, description="Whether the search should be case-sensitive"
    )

    file_types: list[str] | None = Field(
        default=None,
        description=(
            "File type filters (e.g., ['py', 'js', 'ts']). If None, search all files."
        ),
        examples=[["py", "pyi"], ["js", "ts", "tsx"]],
    )

    exclude_patterns: list[str] | None = Field(
        default=None,
        description="Glob patterns to exclude (e.g., ['*.min.js', 'node_modules'])",
        examples=[["node_modules", "*.min.js"], ["venv", "__pycache__"]],
    )

    max_results: int = Field(
        default=1000,
        description="Maximum number of match results to return",
        ge=1,
        le=10000,
    )

    context_lines: int = Field(
        default=2,
        description="Number of lines to include before and after each match",
        ge=0,
        le=10,
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "pattern": "TODO",
                    "path": "./src",
                    "case_sensitive": False,
                    "file_types": ["py"],
                    "exclude_patterns": ["test_*.py", "venv"],
                    "max_results": 100,
                    "context_lines": 2,
                }
            ]
        }
    )


class SearchMatch(BaseModel):
    """Single search match result."""

    file_path: str = Field(description="Absolute path to file containing the match")

    line_number: int = Field(description="Line number of the match (1-indexed)", ge=1)

    line_text: str = Field(description="Content of the matched line")

    context_before: list[str] = Field(
        description="Lines before the match (for context)", default_factory=list
    )

    context_after: list[str] = Field(
        description="Lines after the match (for context)", default_factory=list
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "file_path": "/home/user/project/src/main.py",
                    "line_number": 42,
                    "line_text": "    # TODO: Implement error handling",
                    "context_before": [
                        "def process_data(data):",
                        "    result = transform(data)",
                    ],
                    "context_after": ["    return result", ""],
                }
            ]
        }
    )


class SearchFileContentsOutput(BaseModel):
    """Output schema for search_file_contents tool."""

    matches: list[SearchMatch] = Field(description="List of search matches found")

    total_matches: int = Field(
        description=(
            "Total number of matches found (may exceed returned matches if limited)"
        ),
        ge=0,
    )

    files_searched: int = Field(description="Number of files searched", ge=0)

    truncated: bool = Field(
        description="Whether results were truncated due to max_results limit"
    )

    search_time_ms: int = Field(
        description="Time taken to complete search in milliseconds", ge=0
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "matches": [
                        {
                            "file_path": "/project/src/main.py",
                            "line_number": 42,
                            "line_text": "# TODO: Fix this",
                            "context_before": [],
                            "context_after": [],
                        }
                    ],
                    "total_matches": 1,
                    "files_searched": 15,
                    "truncated": False,
                    "search_time_ms": 234,
                }
            ]
        }
    )


# Input/Output schemas for User Story 2 (execute_command)


class ExecuteCommandInput(BaseModel):
    """Input schema for execute_command tool."""

    command: str = Field(
        description=(
            "Command to execute (will be parsed into argument list for security)"
        ),
        min_length=1,
        max_length=5000,
        examples=["python --version", "npm test", "git status"],
    )

    working_directory: str | None = Field(
        default=None,
        description=(
            "Working directory for command execution. If None, uses current directory."
        ),
        examples=["C:\\projects\\myapp", "/home/user/code"],
    )

    timeout_ms: int = Field(
        default=30000,
        description="Timeout in milliseconds (overrides server default)",
        ge=1000,
        le=300000,  # Max 5 minutes
    )

    capture_output: bool = Field(
        default=True, description="Whether to capture stdout and stderr"
    )

    @field_validator("command")
    @classmethod
    def validate_command_not_empty(cls, v: str) -> str:
        """Ensure command is not just whitespace."""
        if not v.strip():
            raise ValueError("Command cannot be empty or whitespace")
        return v.strip()

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "command": "python -m pytest tests/",
                    "working_directory": "./myproject",
                    "timeout_ms": 60000,
                    "capture_output": True,
                }
            ]
        }
    )


class ExecuteCommandOutput(BaseModel):
    """Output schema for execute_command tool."""

    stdout: str = Field(description="Standard output from the command")

    stderr: str = Field(description="Standard error from the command")

    exit_code: int = Field(
        description="Exit code returned by the command (0 typically means success)"
    )

    execution_time_ms: int = Field(
        description="Time taken to execute command in milliseconds", ge=0
    )

    timed_out: bool = Field(
        description="Whether the command was terminated due to timeout"
    )

    output_truncated: bool = Field(
        description="Whether output was truncated due to size limit"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "stdout": "Python 3.11.5\\n",
                    "stderr": "",
                    "exit_code": 0,
                    "execution_time_ms": 123,
                    "timed_out": False,
                    "output_truncated": False,
                }
            ]
        }
    )


# Input/Output schemas for User Story 3 (list_processes)


class ProcessSortBy(str, Enum):
    """Sort options for process listing."""

    CPU = "cpu"
    MEMORY = "memory"
    PID = "pid"
    NAME = "name"


class ListProcessesInput(BaseModel):
    """Input schema for list_processes tool."""

    name_filter: str | None = Field(
        default=None,
        description=(
            "Filter processes by name (case-insensitive substring match). "
            "If None, return all processes."
        ),
        examples=["python", "chrome", "node"],
    )

    sort_by: ProcessSortBy = Field(
        default=ProcessSortBy.CPU,
        description=(
            "Sort processes by: cpu (descending), memory (descending), "
            "pid (ascending), or name (ascending)"
        ),
    )

    limit: int = Field(
        default=100, description="Maximum number of processes to return", ge=1, le=1000
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"name_filter": "python", "sort_by": "memory", "limit": 50}]
        }
    )


class ProcessInfo(BaseModel):
    """Information about a single process."""

    pid: int = Field(description="Process ID", ge=0)

    name: str = Field(description="Process name")

    cpu_percent: float = Field(description="CPU usage percentage (0.0-100.0+)", ge=0.0)

    memory_mb: float = Field(description="Memory usage in megabytes", ge=0.0)

    cmdline: str = Field(
        description="Command line used to start the process (empty if unavailable)"
    )

    status: str = Field(description="Process status (running, sleeping, zombie, etc.)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "pid": 1234,
                    "name": "python.exe",
                    "cpu_percent": 2.5,
                    "memory_mb": 125.3,
                    "cmdline": "python -m pytest tests/",
                    "status": "running",
                }
            ]
        }
    )


class ListProcessesOutput(BaseModel):
    """Output schema for list_processes tool."""

    processes: list[ProcessInfo] = Field(description="List of process information")

    total_count: int = Field(
        description="Total number of processes found (before limit applied)", ge=0
    )

    truncated: bool = Field(description="Whether results were truncated due to limit")

    retrieval_time_ms: int = Field(
        description="Time taken to retrieve process information in milliseconds", ge=0
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "processes": [
                        {
                            "pid": 1234,
                            "name": "python.exe",
                            "cpu_percent": 5.2,
                            "memory_mb": 150.5,
                            "cmdline": "python script.py",
                            "status": "running",
                        }
                    ],
                    "total_count": 245,
                    "truncated": True,
                    "retrieval_time_ms": 345,
                }
            ]
        }
    )


# Input/Output schemas for User Story 4 (kill_process)


class KillProcessInput(BaseModel):
    """Input schema for kill_process tool."""

    pid: int = Field(description="Process ID to terminate", ge=1, examples=[1234, 5678])

    force: bool = Field(
        default=False,
        description=(
            "If True, forcefully kill the process (SIGKILL/TerminateProcess). "
            "If False, attempt graceful termination (SIGTERM/WM_CLOSE)"
        ),
    )

    timeout_seconds: float = Field(
        default=5.0,
        description=(
            "Timeout in seconds to wait for graceful termination before "
            "returning error. Ignored if force=True."
        ),
        ge=0.1,
        le=30.0,
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"pid": 1234, "force": False, "timeout_seconds": 5.0},
                {"pid": 5678, "force": True, "timeout_seconds": 5.0},
            ]
        }
    )


class KillProcessOutput(BaseModel):
    """Output schema for kill_process tool."""

    success: bool = Field(description="Whether the process was successfully terminated")

    pid: int = Field(description="Process ID that was targeted for termination", ge=1)

    message: str = Field(
        description="Human-readable status message describing the outcome"
    )

    termination_time_ms: int = Field(
        description="Time taken to terminate the process in milliseconds", ge=0
    )

    forced: bool = Field(description="Whether forced termination (SIGKILL) was used")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "success": True,
                    "pid": 1234,
                    "message": "Process 1234 terminated successfully",
                    "termination_time_ms": 123,
                    "forced": False,
                },
                {
                    "success": False,
                    "pid": 5678,
                    "message": "Process 5678 does not exist",
                    "termination_time_ms": 5,
                    "forced": False,
                },
            ]
        }
    )
