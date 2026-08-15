# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for Pydantic schemas."""

import pytest
from pydantic import ValidationError
from src.procexec.tools.schemas import (
    ErrorCategory,
    ToolError,
    SearchFileContentsInput,
    SearchMatch,
    SearchFileContentsOutput,
)


class TestErrorCategory:
    """Tests for ErrorCategory enum."""

    def test_error_category_values(self):
        """Test that all expected error categories exist."""
        assert ErrorCategory.VALIDATION == "validation"
        assert ErrorCategory.PERMISSION == "permission"
        assert ErrorCategory.NOT_FOUND == "not_found"
        assert ErrorCategory.TIMEOUT == "timeout"
        assert ErrorCategory.SECURITY == "security"
        assert ErrorCategory.SYSTEM == "system"
        assert ErrorCategory.UNKNOWN == "unknown"

    def test_error_category_count(self):
        """Test that we have exactly 7 error categories."""
        categories = list(ErrorCategory)
        assert len(categories) == 7


class TestToolError:
    """Tests for ToolError model."""

    def test_tool_error_creation(self):
        """Test creating a valid ToolError."""
        error = ToolError(
            category=ErrorCategory.TIMEOUT,
            message="Operation timed out",
            suggestion="Increase timeout value",
        )
        assert error.category == ErrorCategory.TIMEOUT
        assert error.message == "Operation timed out"
        assert error.suggestion == "Increase timeout value"

    def test_tool_error_without_suggestion(self):
        """Test creating ToolError without suggestion."""
        error = ToolError(category=ErrorCategory.NOT_FOUND, message="File not found")
        assert error.category == ErrorCategory.NOT_FOUND
        assert error.message == "File not found"
        assert error.suggestion is None

    def test_tool_error_validation_requires_category(self):
        """Test that category is required."""
        with pytest.raises(ValidationError):
            ToolError(message="Error message")

    def test_tool_error_validation_requires_message(self):
        """Test that message is required."""
        with pytest.raises(ValidationError):
            ToolError(category=ErrorCategory.UNKNOWN)

    def test_tool_error_json_serialization(self):
        """Test that ToolError can be serialized to JSON."""
        error = ToolError(
            category=ErrorCategory.SECURITY,
            message="Security violation",
            suggestion="Check permissions",
        )
        json_data = error.model_dump()
        assert json_data["category"] == "security"
        assert json_data["message"] == "Security violation"
        assert json_data["suggestion"] == "Check permissions"


class TestSearchFileContentsInput:
    """Tests for SearchFileContentsInput model."""

    def test_valid_input(self):
        """Test creating valid SearchFileContentsInput."""
        input_data = SearchFileContentsInput(
            pattern="TODO",
            path="./src",
            case_sensitive=False,
            file_types=["py"],
            exclude_patterns=["test_*.py"],
            max_results=100,
            context_lines=2,
        )
        assert input_data.pattern == "TODO"
        assert input_data.path == "./src"
        assert input_data.case_sensitive is False
        assert input_data.file_types == ["py"]
        assert input_data.exclude_patterns == ["test_*.py"]
        assert input_data.max_results == 100
        assert input_data.context_lines == 2

    def test_defaults(self):
        """Test default values."""
        input_data = SearchFileContentsInput(pattern="test", path="./src")
        assert input_data.case_sensitive is True
        assert input_data.file_types is None
        assert input_data.exclude_patterns is None
        assert input_data.max_results == 1000
        assert input_data.context_lines == 2

    def test_pattern_validation_empty(self):
        """Test that empty pattern is rejected."""
        with pytest.raises(ValidationError):
            SearchFileContentsInput(pattern="", path="./src")

    def test_pattern_validation_too_long(self):
        """Test that pattern exceeding max length is rejected."""
        long_pattern = "x" * 1001
        with pytest.raises(ValidationError):
            SearchFileContentsInput(pattern=long_pattern, path="./src")

    def test_max_results_validation_too_small(self):
        """Test that max_results < 1 is rejected."""
        with pytest.raises(ValidationError):
            SearchFileContentsInput(pattern="test", path="./src", max_results=0)

    def test_max_results_validation_too_large(self):
        """Test that max_results > 10000 is rejected."""
        with pytest.raises(ValidationError):
            SearchFileContentsInput(pattern="test", path="./src", max_results=10001)

    def test_context_lines_validation_negative(self):
        """Test that negative context_lines is rejected."""
        with pytest.raises(ValidationError):
            SearchFileContentsInput(pattern="test", path="./src", context_lines=-1)

    def test_context_lines_validation_too_large(self):
        """Test that context_lines > 10 is rejected."""
        with pytest.raises(ValidationError):
            SearchFileContentsInput(pattern="test", path="./src", context_lines=11)


class TestSearchMatch:
    """Tests for SearchMatch model."""

    def test_valid_search_match(self):
        """Test creating valid SearchMatch."""
        match = SearchMatch(
            file_path="/project/src/main.py",
            line_number=42,
            line_text="# TODO: Fix this",
            context_before=["def foo():", "    pass"],
            context_after=["    return None"],
        )
        assert match.file_path == "/project/src/main.py"
        assert match.line_number == 42
        assert match.line_text == "# TODO: Fix this"
        assert len(match.context_before) == 2
        assert len(match.context_after) == 1

    def test_search_match_defaults(self):
        """Test default values for optional fields."""
        match = SearchMatch(file_path="/test.py", line_number=1, line_text="test")
        assert match.context_before == []
        assert match.context_after == []

    def test_line_number_validation(self):
        """Test that line_number must be >= 1."""
        with pytest.raises(ValidationError):
            SearchMatch(file_path="/test.py", line_number=0, line_text="test")


class TestSearchFileContentsOutput:
    """Tests for SearchFileContentsOutput model."""

    def test_valid_output(self):
        """Test creating valid SearchFileContentsOutput."""
        matches = [SearchMatch(file_path="/test.py", line_number=1, line_text="test")]
        output = SearchFileContentsOutput(
            matches=matches,
            total_matches=1,
            files_searched=1,
            truncated=False,
            search_time_ms=123,
        )
        assert len(output.matches) == 1
        assert output.total_matches == 1
        assert output.files_searched == 1
        assert output.truncated is False
        assert output.search_time_ms == 123

    def test_empty_results(self):
        """Test output with no matches."""
        output = SearchFileContentsOutput(
            matches=[],
            total_matches=0,
            files_searched=5,
            truncated=False,
            search_time_ms=50,
        )
        assert len(output.matches) == 0
        assert output.total_matches == 0
        assert output.files_searched == 5

    def test_truncated_results(self):
        """Test output with truncated results."""
        matches = [
            SearchMatch(file_path=f"/test{i}.py", line_number=1, line_text="test")
            for i in range(10)
        ]
        output = SearchFileContentsOutput(
            matches=matches,
            total_matches=1000,  # More than returned
            files_searched=50,
            truncated=True,
            search_time_ms=5000,
        )
        assert len(output.matches) == 10
        assert output.total_matches == 1000
        assert output.truncated is True

    def test_validation_negative_values(self):
        """Test that negative values are rejected."""
        with pytest.raises(ValidationError):
            SearchFileContentsOutput(
                matches=[],
                total_matches=-1,
                files_searched=0,
                truncated=False,
                search_time_ms=100,
            )

        with pytest.raises(ValidationError):
            SearchFileContentsOutput(
                matches=[],
                total_matches=0,
                files_searched=-1,
                truncated=False,
                search_time_ms=100,
            )

        with pytest.raises(ValidationError):
            SearchFileContentsOutput(
                matches=[],
                total_matches=0,
                files_searched=0,
                truncated=False,
                search_time_ms=-1,
            )
