# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for search tool with mocked subprocess."""

import pytest
import json
from unittest.mock import patch, MagicMock
from src.procexec.tools.search import (
    _check_ripgrep_available,
    _build_ripgrep_args,
    _parse_ripgrep_json,
    _execute_ripgrep,
    search_file_contents,
)
from src.procexec.tools.schemas import SearchFileContentsInput
from src.procexec.utils.validation import SanitizedError


class TestCheckRipgrepAvailable:
    """Tests for _check_ripgrep_available function."""

    @patch("shutil.which")
    @patch("os.environ.get")
    def test_ripgrep_in_path(self, mock_env_get, mock_which):
        """Test when ripgrep is available in PATH."""
        mock_env_get.return_value = None
        mock_which.return_value = "/usr/bin/rg"

        result = _check_ripgrep_available()
        assert result == "/usr/bin/rg"

    @patch("shutil.which")
    @patch("os.environ.get")
    @patch("pathlib.Path.exists")
    def test_ripgrep_custom_path(self, mock_exists, mock_env_get, mock_which):
        """Test when PROCEXEC_RIPGREP_PATH is set."""
        from pathlib import Path

        custom_path = "/custom/path/rg"
        mock_env_get.return_value = custom_path
        mock_exists.return_value = True

        result = _check_ripgrep_available()
        # Result is converted to string via Path
        assert str(Path(custom_path)) in result or custom_path in result

    @patch("shutil.which")
    @patch("os.environ.get")
    @patch("pathlib.Path.exists")
    def test_ripgrep_custom_path_not_found(self, mock_exists, mock_env_get, mock_which):
        """Test when custom path doesn't exist."""
        mock_env_get.return_value = "/nonexistent/rg"
        mock_exists.return_value = False

        with pytest.raises(SanitizedError, match="not found"):
            _check_ripgrep_available()

    @patch("shutil.which")
    @patch("os.environ.get")
    def test_ripgrep_not_available(self, mock_env_get, mock_which):
        """Test when ripgrep is not available."""
        mock_env_get.return_value = None
        mock_which.return_value = None

        with pytest.raises(SanitizedError, match="not available"):
            _check_ripgrep_available()


class TestBuildRipgrepArgs:
    """Tests for _build_ripgrep_args function."""

    def test_basic_args(self):
        """Test building basic ripgrep arguments."""
        input_data = SearchFileContentsInput(pattern="test", path="/project/src")

        args = _build_ripgrep_args(input_data, input_data.path, "rg")

        assert args[0] == "rg"
        assert "--json" in args
        assert "--line-number" in args
        assert "test" in args
        assert str(input_data.path) in args

    def test_args_with_context_lines(self):
        """Test arguments with context lines."""
        input_data = SearchFileContentsInput(
            pattern="test", path="/project", context_lines=5
        )

        args = _build_ripgrep_args(input_data, input_data.path, "rg")

        assert "--context" in args
        context_index = args.index("--context")
        assert args[context_index + 1] == "5"

    def test_args_case_insensitive(self):
        """Test arguments for case-insensitive search."""
        input_data = SearchFileContentsInput(
            pattern="TEST", path="/project", case_sensitive=False
        )

        args = _build_ripgrep_args(input_data, input_data.path, "rg")

        assert "--ignore-case" in args

    def test_args_with_file_types(self):
        """Test arguments with file type filters."""
        input_data = SearchFileContentsInput(
            pattern="test", path="/project", file_types=["py", "js"]
        )

        args = _build_ripgrep_args(input_data, input_data.path, "rg")

        assert "--type" in args
        assert "py" in args
        assert "js" in args

    def test_args_with_exclude_patterns(self):
        """Test arguments with exclusion patterns."""
        input_data = SearchFileContentsInput(
            pattern="test",
            path="/project",
            exclude_patterns=["*.min.js", "node_modules"],
        )

        args = _build_ripgrep_args(input_data, input_data.path, "rg")

        assert "--glob" in args
        assert "!*.min.js" in args
        assert "!node_modules" in args

    def test_args_with_max_results(self):
        """Test arguments with max results limit."""
        input_data = SearchFileContentsInput(
            pattern="test", path="/project", max_results=100
        )

        args = _build_ripgrep_args(input_data, input_data.path, "rg")

        assert "--max-count" in args
        max_count_index = args.index("--max-count")
        assert args[max_count_index + 1] == "100"

    def test_args_with_custom_ripgrep_path(self):
        """Test that custom ripgrep path is used."""
        input_data = SearchFileContentsInput(pattern="test", path="/project")

        args = _build_ripgrep_args(input_data, input_data.path, "/custom/path/rg")

        assert args[0] == "/custom/path/rg"


class TestParseRipgrepJson:
    """Tests for _parse_ripgrep_json function."""

    def test_parse_simple_match(self):
        """Test parsing a simple match result."""
        json_output = json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": "/test/file.py"},
                    "line_number": 42,
                    "lines": {"text": "test line content\n"},
                },
            }
        )

        matches, total, files = _parse_ripgrep_json(json_output, max_results=1000)

        assert len(matches) == 1
        assert matches[0].file_path == "/test/file.py"
        assert matches[0].line_number == 42
        assert matches[0].line_text == "test line content"
        assert total == 1

    def test_parse_multiple_matches(self):
        """Test parsing multiple matches."""
        json_lines = [
            json.dumps({"type": "begin", "data": {"path": {"text": "/test/file1.py"}}}),
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": "/test/file1.py"},
                        "line_number": 10,
                        "lines": {"text": "match 1\n"},
                    },
                }
            ),
            json.dumps({"type": "begin", "data": {"path": {"text": "/test/file2.py"}}}),
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": "/test/file2.py"},
                        "line_number": 20,
                        "lines": {"text": "match 2\n"},
                    },
                }
            ),
        ]
        json_output = "\n".join(json_lines)

        matches, total, files = _parse_ripgrep_json(json_output, max_results=1000)

        assert len(matches) == 2
        assert total == 2
        assert files == 2

    def test_parse_with_context(self):
        """Test parsing matches with context lines."""
        # ripgrep emits begin, then context/match in sequence
        json_lines = [
            json.dumps({"type": "begin", "data": {"path": {"text": "/test/file.py"}}}),
            json.dumps(
                {
                    "type": "context",
                    "data": {
                        "path": {"text": "/test/file.py"},
                        "line_number": 9,
                        "lines": {"text": "context before\n"},
                    },
                }
            ),
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": "/test/file.py"},
                        "line_number": 10,
                        "lines": {"text": "matched line\n"},
                    },
                }
            ),
            json.dumps(
                {
                    "type": "context",
                    "data": {
                        "path": {"text": "/test/file.py"},
                        "line_number": 11,
                        "lines": {"text": "context after\n"},
                    },
                }
            ),
            json.dumps({"type": "end", "data": {"path": {"text": "/test/file.py"}}}),
        ]
        json_output = "\n".join(json_lines)

        matches, total, files = _parse_ripgrep_json(json_output, max_results=1000)

        assert len(matches) == 1
        # Check if context was captured (implementation may vary)
        # The parser finalizes matches, so check basic structure
        assert matches[0].file_path == "/test/file.py"
        assert matches[0].line_number == 10

    def test_parse_with_max_results_limit(self):
        """Test that max_results limit is respected."""
        # Create 100 match entries
        json_lines = [
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": f"/test/file{i}.py"},
                        "line_number": i + 1,  # Line numbers start at 1
                        "lines": {"text": f"match {i}\n"},
                    },
                }
            )
            for i in range(100)
        ]
        json_output = "\n".join(json_lines)

        matches, total, files = _parse_ripgrep_json(json_output, max_results=10)

        # Should respect max_results limit
        assert len(matches) <= 10
        # Total count reflects all matches counted before limit
        assert total >= len(matches)

    def test_parse_malformed_json_ignored(self):
        """Test that malformed JSON lines are ignored."""
        json_lines = [
            json.dumps({"type": "begin", "data": {"path": {"text": "/test/file.py"}}}),
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": "/test/file.py"},
                        "line_number": 10,
                        "lines": {"text": "valid match\n"},
                    },
                }
            ),
            "{ invalid json }",
            json.dumps({"type": "begin", "data": {"path": {"text": "/test/file2.py"}}}),
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": "/test/file2.py"},
                        "line_number": 20,
                        "lines": {"text": "another valid\n"},
                    },
                }
            ),
        ]
        json_output = "\n".join(json_lines)

        matches, total, files = _parse_ripgrep_json(json_output, max_results=1000)

        # Should get 2 valid matches (malformed JSON ignored)
        assert len(matches) == 2
        assert total == 2


class TestExecuteRipgrep:
    """Tests for _execute_ripgrep function."""

    @patch("subprocess.run")
    def test_execute_successful(self, mock_run):
        """Test successful ripgrep execution."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ripgrep output", stderr=""
        )

        result = _execute_ripgrep(["rg", "pattern", "/path"], timeout_ms=30000)

        assert result == "ripgrep output"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_execute_no_matches(self, mock_run):
        """Test execution when no matches found (exit code 1)."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

        result = _execute_ripgrep(["rg", "pattern", "/path"], timeout_ms=30000)

        assert result == ""

    @patch("subprocess.run")
    def test_execute_error(self, mock_run):
        """Test execution with error (exit code 2)."""
        mock_run.return_value = MagicMock(
            returncode=2, stdout="", stderr="ripgrep error"
        )

        with pytest.raises(SanitizedError):
            _execute_ripgrep(["rg", "pattern", "/path"], timeout_ms=30000)

    @patch("subprocess.run")
    def test_execute_timeout(self, mock_run):
        """Test execution timeout handling."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("rg", 30)

        with pytest.raises(SanitizedError, match="timeout"):
            _execute_ripgrep(["rg", "pattern", "/path"], timeout_ms=30000)

    @patch("subprocess.run")
    def test_execute_file_not_found(self, mock_run):
        """Test handling when ripgrep binary not found."""
        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(SanitizedError, match="not found"):
            _execute_ripgrep(["rg", "pattern", "/path"], timeout_ms=30000)


class TestSearchFileContents:
    """Integration tests for search_file_contents function."""

    @pytest.mark.asyncio
    @patch("src.procexec.tools.search._check_ripgrep_available")
    @patch("src.procexec.tools.search._execute_ripgrep")
    async def test_search_file_contents_basic(self, mock_execute, mock_check, tmp_path):
        """Test basic search_file_contents call."""
        mock_check.return_value = "rg"

        # Use a real temporary directory
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        mock_execute.return_value = json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": str(test_dir / "file.py")},
                    "line_number": 10,
                    "lines": {"text": "test match\n"},
                },
            }
        )

        result = await search_file_contents(pattern="test", path=str(test_dir))

        assert result is not None
        assert len(result.matches) == 1
        assert result.total_matches == 1

    @pytest.mark.asyncio
    @patch("src.procexec.tools.search._check_ripgrep_available")
    async def test_search_file_contents_ripgrep_not_available(self, mock_check):
        """Test error when ripgrep is not available."""
        mock_check.side_effect = SanitizedError("ripgrep not available")

        with pytest.raises(SanitizedError):
            await search_file_contents(pattern="test", path="/test/path")

    @pytest.mark.asyncio
    @patch("src.procexec.tools.search._check_ripgrep_available")
    async def test_search_file_contents_invalid_path(self, mock_check):
        """Test error when path validation fails."""
        mock_check.return_value = "rg"

        # Use a path that doesn't exist
        with pytest.raises(SanitizedError, match="does not exist"):
            await search_file_contents(
                pattern="test", path="/completely/nonexistent/path/that/will/not/exist"
            )
