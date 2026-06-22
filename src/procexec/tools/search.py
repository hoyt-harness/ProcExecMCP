"""search_file_contents tool implementation using ripgrep."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from mcp.server.fastmcp import Context

from ..server import config, mcp
from ..utils.validation import SanitizedError, sanitize_error_message, validate_path
from .schemas import SearchFileContentsInput, SearchFileContentsOutput, SearchMatch


def _check_ripgrep_available() -> str:
    """Check if ripgrep binary is available and return its path.

    First checks PROCEXEC_RIPGREP_PATH environment variable for custom path.
    Falls back to searching PATH for 'rg' binary.

    Returns:
        Path to ripgrep binary (absolute or command name)

    Raises:
        SanitizedError: If ripgrep binary not found
    """
    # Check for custom ripgrep path in environment variable
    custom_path = os.environ.get("PROCEXEC_RIPGREP_PATH")
    if custom_path:
        # Validate that the custom path exists and is executable
        custom_path_obj = Path(custom_path)
        if custom_path_obj.exists():
            return str(custom_path_obj)
        else:
            raise SanitizedError(
                "Custom ripgrep path specified in PROCEXEC_RIPGREP_PATH "
                f"not found: {custom_path}",
                original_error=None,
            )

    # Fall back to checking PATH
    rg_path = shutil.which("rg")
    if not rg_path:
        raise SanitizedError(
            "Search tool (ripgrep) not available on system. "
            "Please install ripgrep: "
            "https://github.com/BurntSushi/ripgrep#installation "
            "or set PROCEXEC_RIPGREP_PATH environment variable to the "
            "full path to ripgrep binary.",
            original_error=None,
        )

    return rg_path


def _build_ripgrep_args(
    input: SearchFileContentsInput, path: Path, ripgrep_path: str
) -> list[str]:
    """Build ripgrep command arguments from input parameters.

    Args:
        input: Validated search input parameters
        path: Resolved absolute path to search in
        ripgrep_path: Path to ripgrep binary

    Returns:
        List of ripgrep command arguments
    """
    args = [
        ripgrep_path,
        "--json",  # Structured JSON output
        "--line-number",  # Include line numbers
        "--no-heading",  # Format for JSON parsing
        "--color",
        "never",  # No ANSI color codes
    ]

    # Context lines
    if input.context_lines > 0:
        args.extend(["--context", str(input.context_lines)])

    # Case sensitivity
    if not input.case_sensitive:
        args.append("--ignore-case")

    # File type filters
    if input.file_types:
        for file_type in input.file_types:
            args.extend(["--type", file_type])

    # Exclusion patterns
    if input.exclude_patterns:
        for pattern in input.exclude_patterns:
            args.extend(["--glob", f"!{pattern}"])

    # Max results (approximate via max-count per file)
    # Note: This is per-file, so actual total may exceed max_results
    # We'll handle truncation in parsing
    max_count_per_file = min(input.max_results, 1000)
    args.extend(["--max-count", str(max_count_per_file)])

    # Pattern and path
    args.append(input.pattern)
    args.append(str(path))

    return args


def _parse_ripgrep_json(
    json_output: str, max_results: int
) -> tuple[list[SearchMatch], int, int]:
    """Parse ripgrep JSON output into SearchMatch objects.

    Args:
        json_output: Raw JSON output from ripgrep
        max_results: Maximum number of results to return

    Returns:
        Tuple of (matches, total_count, files_searched)
    """
    matches: list[SearchMatch] = []
    files_searched = set()
    total_count = 0

    # Current match being built (with context)
    current_match: dict | None = None
    context_before: list[str] = []
    context_after: list[str] = []

    for line in json_output.splitlines():
        if not line.strip():
            continue

        try:
            data = json.loads(line)
            msg_type = data.get("type")

            if msg_type == "begin":
                # New file
                file_path = data["data"]["path"]["text"]
                files_searched.add(file_path)

            elif msg_type == "match":
                # Match found
                match_data = data["data"]
                file_path = match_data["path"]["text"]
                files_searched.add(file_path)

                # If we have a previous match, finalize it before starting new one
                if current_match:
                    matches.append(
                        SearchMatch(
                            file_path=current_match["file_path"],
                            line_number=current_match["line_number"],
                            line_text=current_match["line_text"],
                            context_before=context_before.copy(),
                            context_after=context_after.copy(),
                        )
                    )
                    context_before = []
                    context_after = []

                # Start new match
                line_number = match_data["line_number"]
                line_text = match_data["lines"]["text"].rstrip("\n")

                current_match = {
                    "file_path": file_path,
                    "line_number": line_number,
                    "line_text": line_text,
                }
                total_count += 1

                # Check if we've hit max results
                if len(matches) >= max_results:
                    break

            elif msg_type == "context":
                # Context line (before or after match)
                context_data = data["data"]
                line_text = context_data["lines"]["text"].rstrip("\n")
                line_number = context_data["line_number"]

                if current_match:
                    # Determine if this is before or after the match
                    if line_number < current_match["line_number"]:
                        context_before.append(line_text)
                    else:
                        context_after.append(line_text)

        except (json.JSONDecodeError, KeyError):
            # Skip malformed JSON lines
            continue

    # Finalize last match if exists
    if current_match and len(matches) < max_results:
        matches.append(
            SearchMatch(
                file_path=current_match["file_path"],
                line_number=current_match["line_number"],
                line_text=current_match["line_text"],
                context_before=context_before,
                context_after=context_after,
            )
        )

    return matches, total_count, len(files_searched)


def _execute_ripgrep(args: list[str], timeout_ms: int) -> str:
    """Execute ripgrep command and return output.

    Args:
        args: Ripgrep command arguments
        timeout_ms: Timeout in milliseconds

    Returns:
        Raw stdout from ripgrep

    Raises:
        SanitizedError: If execution fails or times out
    """
    try:
        # noqa justification: args are built internally from validated
        # search parameters (see _build_ripgrep_args), not raw user
        # input; shell=False avoids shell-injection regardless.
        result = subprocess.run(  # noqa: S603
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_ms / 1000.0,  # Convert to seconds
            shell=False,  # SECURITY: Never use shell=True
            stdin=subprocess.DEVNULL,  # Prevent stdin hang on Windows
        )

        # ripgrep exit codes:
        # 0 = matches found
        # 1 = no matches found (not an error)
        # 2 = error occurred
        if result.returncode == 2:
            error_msg = (
                result.stderr.strip() if result.stderr else "Search operation failed"
            )
            raise SanitizedError(sanitize_error_message(error_msg))

        return result.stdout

    except subprocess.TimeoutExpired:
        raise SanitizedError(
            f"Search operation exceeded timeout limit of {timeout_ms}ms",
            original_error=None,
        )
    except FileNotFoundError:
        raise SanitizedError(
            "Search tool (ripgrep) not found in PATH. Please install ripgrep.",
            original_error=None,
        )
    except Exception as e:
        raise SanitizedError(
            f"Search operation failed: {type(e).__name__}", original_error=e
        )


@mcp.tool()
async def search_file_contents(
    pattern: str,
    path: str,
    case_sensitive: bool = True,
    file_types: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    max_results: int = 1000,
    context_lines: int = 2,
    ctx: Context | None = None,
) -> SearchFileContentsOutput:
    """Search for patterns in file contents across a directory or file.

    This tool uses ripgrep to efficiently search for regex patterns in files.
    It returns matches with line numbers and surrounding context lines.

    Args:
        pattern: Regular expression pattern to search for
        path: File or directory path to search in
        case_sensitive: Whether search should be case-sensitive (default: True)
        file_types: File type filters (e.g., ['py', 'js']). None = all files
        exclude_patterns: Glob patterns to exclude (e.g., ['node_modules'])
        max_results: Maximum number of results to return (1-10000)
        context_lines: Lines of context before/after match (0-10)
        ctx: MCP context for logging (optional)

    Returns:
        SearchFileContentsOutput with matches and metadata

    Raises:
        ValueError: If input validation fails
        SanitizedError: If search execution fails

    Examples:
        >>> result = search_file_contents("TODO", "./src", case_sensitive=False)
        >>> print(f"Found {len(result.matches)} TODO comments")
    """
    start_time = time.time()

    # Validate inputs via Pydantic
    input = SearchFileContentsInput(
        pattern=pattern,
        path=path,
        case_sensitive=case_sensitive,
        file_types=file_types,
        exclude_patterns=exclude_patterns,
        max_results=max_results,
        context_lines=context_lines,
    )

    if ctx:
        await ctx.info(f"Searching for pattern '{input.pattern}' in {input.path}")

    # Check ripgrep availability and get path
    ripgrep_path = _check_ripgrep_available()

    # Validate and resolve path
    try:
        resolved_path = validate_path(input.path, must_exist=True)
    except ValueError as e:
        raise SanitizedError(str(e), original_error=e)

    # Build ripgrep arguments
    rg_args = _build_ripgrep_args(input, resolved_path, ripgrep_path)

    # Execute ripgrep
    timeout = config.timeout_ms
    json_output = _execute_ripgrep(rg_args, timeout)

    # Parse results
    matches, total_count, files_searched = _parse_ripgrep_json(
        json_output, input.max_results
    )

    # Calculate timing
    search_time_ms = int((time.time() - start_time) * 1000)

    # Determine if results were truncated
    truncated = total_count > input.max_results or len(matches) >= input.max_results

    if ctx:
        await ctx.info(
            f"Search complete: {len(matches)} matches in {files_searched} files "
            f"({search_time_ms}ms)"
        )

    return SearchFileContentsOutput(
        matches=matches,
        total_matches=total_count,
        files_searched=files_searched,
        truncated=truncated,
        search_time_ms=search_time_ms,
    )
