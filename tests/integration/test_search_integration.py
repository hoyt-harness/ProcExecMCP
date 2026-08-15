# SPDX-License-Identifier: GPL-3.0-or-later
"""Integration tests for search_file_contents tool with real ripgrep."""

import pytest
from pathlib import Path

# Import the tool function directly for testing
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from procexec.tools.search import search_file_contents


@pytest.mark.asyncio
async def test_search_for_todo_in_test_directory():
    """Test searching for TODO pattern in the test directory itself."""
    # Search for "test" in the current test file
    test_dir = str(Path(__file__).parent)

    result = await search_file_contents(
        pattern="test",
        path=test_dir,
        case_sensitive=False,
        file_types=["py"],
        max_results=100,
        context_lines=1,
    )

    # Verify we got results
    assert result.total_matches > 0, "Should find 'test' in test files"
    assert result.files_searched > 0, "Should have searched files"
    assert result.search_time_ms >= 0, "Search time should be recorded"
    assert len(result.matches) > 0, "Should return at least one match"

    # Verify match structure
    first_match = result.matches[0]
    assert first_match.file_path, "Match should have file path"
    assert first_match.line_number > 0, "Match should have line number"
    assert first_match.line_text, "Match should have line text"


@pytest.mark.asyncio
async def test_search_case_insensitive():
    """Test case-insensitive search."""
    test_dir = str(Path(__file__).parent)

    result = await search_file_contents(
        pattern="TEST",
        path=test_dir,
        case_sensitive=False,
        file_types=["py"],
        max_results=10,
    )

    # Should find matches even though pattern is uppercase
    assert result.total_matches > 0, "Case-insensitive search should find matches"


@pytest.mark.asyncio
async def test_search_with_exclusion():
    """Test search with exclusion patterns."""
    # Search from repo root but exclude tests directory
    repo_root = str(Path(__file__).parent.parent.parent)

    result = await search_file_contents(
        pattern="procexec",
        path=repo_root,
        case_sensitive=False,
        exclude_patterns=["tests", ".git", ".venv"],
        file_types=["py"],
        max_results=50,
    )

    # Should find matches in src but not in tests
    if result.matches:
        for match in result.matches:
            assert "tests" not in match.file_path.lower(), (
                "Should not find matches in excluded 'tests' directory"
            )


@pytest.mark.asyncio
async def test_search_with_context_lines():
    """Test that context lines are included."""
    test_dir = str(Path(__file__).parent)

    result = await search_file_contents(
        pattern="def test",
        path=test_dir,
        case_sensitive=True,
        file_types=["py"],
        max_results=5,
        context_lines=2,
    )

    if result.matches:
        # Note: context may be empty if match is at file boundaries
        # So we just verify the fields exist and are lists
        for match in result.matches:
            assert isinstance(match.context_before, list)
            assert isinstance(match.context_after, list)


@pytest.mark.asyncio
async def test_search_nonexistent_directory_raises_error():
    """Test that searching in non-existent directory raises error."""
    with pytest.raises(Exception) as exc_info:
        await search_file_contents(
            pattern="test",
            path="/nonexistent/directory/that/does/not/exist",
            max_results=10,
        )

    # Should get an error about path not existing
    error_str = str(exc_info.value).lower()
    assert "not exist" in error_str or "invalid" in error_str


@pytest.mark.asyncio
async def test_search_returns_structured_output():
    """Test that output matches expected schema structure."""
    test_dir = str(Path(__file__).parent)

    result = await search_file_contents(
        pattern="import", path=test_dir, file_types=["py"], max_results=10
    )

    # Verify output structure
    assert hasattr(result, "matches")
    assert hasattr(result, "total_matches")
    assert hasattr(result, "files_searched")
    assert hasattr(result, "truncated")
    assert hasattr(result, "search_time_ms")

    assert isinstance(result.matches, list)
    assert isinstance(result.total_matches, int)
    assert isinstance(result.files_searched, int)
    assert isinstance(result.truncated, bool)
    assert isinstance(result.search_time_ms, int)
