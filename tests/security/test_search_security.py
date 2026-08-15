# SPDX-License-Identifier: GPL-3.0-or-later
"""Security tests for search_file_contents tool."""

import pytest
from src.procexec.tools.search import search_file_contents
from src.procexec.utils.validation import SanitizedError


class TestSearchPathTraversal:
    """Tests to prevent path traversal in search operations."""

    @pytest.mark.asyncio
    async def test_search_with_traversal_path(self):
        """Test that path traversal in search path is blocked."""
        dangerous_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\Windows\\System32\\config",
        ]

        for path in dangerous_paths:
            with pytest.raises((ValueError, SanitizedError)):
                await search_file_contents(pattern="test", path=path)

    @pytest.mark.asyncio
    async def test_search_sensitive_system_paths(self):
        """Test that searches in sensitive paths are blocked."""
        sensitive_paths = [
            "/etc/shadow",
            "/etc/passwd",
            "C:\\Windows\\System32\\config",
            "C:\\Windows\\System32\\drivers",
        ]

        for path in sensitive_paths:
            with pytest.raises((ValueError, SanitizedError)):
                await search_file_contents(pattern="test", path=path)


class TestSearchRegexLimits:
    """Tests for regex pattern length limits to prevent ReDoS."""

    @pytest.mark.asyncio
    async def test_pattern_length_limit(self, tmp_path):
        """Test that excessively long patterns are rejected."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Pattern exceeding max length (1000 chars)
        long_pattern = "a" * 1001

        with pytest.raises((ValueError, SanitizedError)):
            await search_file_contents(pattern=long_pattern, path=str(tmp_path))

    @pytest.mark.asyncio
    async def test_empty_pattern_rejected(self, tmp_path):
        """Test that empty patterns are rejected."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        with pytest.raises((ValueError, SanitizedError)):
            await search_file_contents(pattern="", path=str(tmp_path))

    @pytest.mark.asyncio
    async def test_max_pattern_length_accepted(self, tmp_path):
        """Test that patterns at max length (1000 chars) are accepted."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Pattern at exactly max length
        max_pattern = "a" * 1000

        # Should not raise exception
        result = await search_file_contents(pattern=max_pattern, path=str(tmp_path))

        assert result is not None
        assert hasattr(result, "matches")


class TestSearchMaxResultsEnforcement:
    """Tests for max_results enforcement to prevent memory exhaustion."""

    @pytest.mark.asyncio
    async def test_max_results_limit_enforced(self, tmp_path):
        """Test that max_results limit is enforced."""
        # Create multiple test files with matches
        for i in range(20):
            test_file = tmp_path / f"test{i}.txt"
            # Write 100 lines with "MATCH" keyword
            content = "\n".join([f"Line {j} MATCH content" for j in range(100)])
            test_file.write_text(content)

        # Search with max_results=50
        result = await search_file_contents(
            pattern="MATCH", path=str(tmp_path), max_results=50
        )

        # Should return at most 50 matches
        assert len(result.matches) <= 50
        assert result.total_matches >= 50
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_max_results_minimum_validation(self, tmp_path):
        """Test that max_results must be at least 1."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        with pytest.raises((ValueError, SanitizedError)):
            await search_file_contents(
                pattern="test", path=str(tmp_path), max_results=0
            )

    @pytest.mark.asyncio
    async def test_max_results_maximum_validation(self, tmp_path):
        """Test that max_results cannot exceed 10000."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        with pytest.raises((ValueError, SanitizedError)):
            await search_file_contents(
                pattern="test", path=str(tmp_path), max_results=10001
            )


class TestSearchLargeResultSets:
    """Tests for handling large result sets without memory exhaustion."""

    @pytest.mark.asyncio
    async def test_search_with_many_matches(self, tmp_path):
        """Test searching files with many matches doesn't exhaust memory."""
        # Create a large file with many matches
        test_file = tmp_path / "large.txt"
        # 10,000 lines with the search pattern
        content = "\n".join([f"Line {i} with FINDME pattern" for i in range(10000)])
        test_file.write_text(content)

        # Search with default max_results (1000)
        result = await search_file_contents(pattern="FINDME", path=str(tmp_path))

        # Should be truncated
        assert len(result.matches) <= 1000
        assert result.truncated is True
        assert result.total_matches >= 1000

    @pytest.mark.asyncio
    async def test_search_in_many_files(self, tmp_path):
        """Test searching across many files doesn't exhaust memory."""
        # Create 100 files
        for i in range(100):
            test_file = tmp_path / f"file{i}.txt"
            test_file.write_text(f"Content {i} with PATTERN here")

        # Search across all files
        result = await search_file_contents(
            pattern="PATTERN",
            path=str(tmp_path),
            max_results=50,  # Limit results
        )

        # Should handle gracefully
        assert len(result.matches) <= 50
        assert result.files_searched > 0


class TestSearchContextLinesValidation:
    """Tests for context_lines parameter validation."""

    @pytest.mark.asyncio
    async def test_context_lines_negative_rejected(self, tmp_path):
        """Test that negative context_lines is rejected."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        with pytest.raises((ValueError, SanitizedError)):
            await search_file_contents(
                pattern="test", path=str(tmp_path), context_lines=-1
            )

    @pytest.mark.asyncio
    async def test_context_lines_too_large_rejected(self, tmp_path):
        """Test that context_lines > 10 is rejected."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        with pytest.raises((ValueError, SanitizedError)):
            await search_file_contents(
                pattern="test", path=str(tmp_path), context_lines=11
            )

    @pytest.mark.asyncio
    async def test_context_lines_maximum_accepted(self, tmp_path):
        """Test that context_lines=10 is accepted."""
        test_file = tmp_path / "test.txt"
        # Create file with enough lines for context
        content = "\n".join([f"Line {i}" for i in range(50)])
        test_file.write_text(content)

        result = await search_file_contents(
            pattern="Line 25", path=str(tmp_path), context_lines=10
        )

        assert result is not None


class TestSearchExclusionPatterns:
    """Tests for exclusion pattern handling."""

    @pytest.mark.asyncio
    async def test_exclusion_prevents_traversal(self, tmp_path):
        """Test that exclusion patterns can't be used for traversal."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Exclusion patterns with traversal attempts should still be safe
        # because the search path itself is validated
        result = await search_file_contents(
            pattern="test", path=str(tmp_path), exclude_patterns=["../../etc/passwd"]
        )

        # Should execute without error (path validation happens on search path)
        assert result is not None

    @pytest.mark.asyncio
    async def test_valid_exclusion_patterns(self, tmp_path):
        """Test that valid exclusion patterns work correctly."""
        # Create test files
        (tmp_path / "include.txt").write_text("FIND this")
        (tmp_path / "exclude.txt").write_text("FIND this too")

        result = await search_file_contents(
            pattern="FIND", path=str(tmp_path), exclude_patterns=["exclude.txt"]
        )

        # Should only find in include.txt
        assert len(result.matches) == 1
        assert "include.txt" in result.matches[0].file_path


class TestSearchTimeout:
    """Tests for timeout handling in search operations."""

    @pytest.mark.asyncio
    async def test_search_completes_within_reasonable_time(self, tmp_path):
        """Test that search operations complete within reasonable time."""
        # Create a moderate-sized test set
        for i in range(20):
            test_file = tmp_path / f"file{i}.txt"
            content = "\n".join([f"Line {j}" for j in range(100)])
            test_file.write_text(content)

        import time

        start = time.time()

        result = await search_file_contents(
            pattern="Line", path=str(tmp_path), max_results=100
        )

        elapsed = time.time() - start

        # Should complete in reasonable time (< 30 seconds default timeout)
        assert elapsed < 30
        assert result is not None
