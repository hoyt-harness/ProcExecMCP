# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for validation utilities."""

import pytest
from pathlib import Path
from src.procexec.utils.validation import (
    validate_path,
    validate_directory,
    validate_file,
    sanitize_path,
    sanitize_error_message,
    SanitizedError,
)


class TestValidatePath:
    """Tests for validate_path function."""

    def test_validate_existing_directory(self, tmp_path):
        """Test validation of existing directory."""
        result = validate_path(str(tmp_path), must_exist=True)
        assert isinstance(result, Path)
        assert result.exists()
        assert result.is_absolute()

    def test_validate_existing_file(self, tmp_path):
        """Test validation of existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = validate_path(str(test_file), must_exist=True)
        assert isinstance(result, Path)
        assert result.exists()
        assert result.is_file()

    def test_validate_nonexistent_path_with_must_exist(self):
        """Test that nonexistent path raises error when must_exist=True."""
        with pytest.raises(ValueError, match="Path does not exist"):
            validate_path("/nonexistent/path", must_exist=True)

    def test_validate_nonexistent_path_without_must_exist(self):
        """Test that nonexistent path is accepted when must_exist=False."""
        result = validate_path("/nonexistent/path", must_exist=False)
        assert isinstance(result, Path)

    def test_validate_relative_path_resolves_to_absolute(self, tmp_path):
        """Test that relative paths are resolved to absolute."""
        test_dir = tmp_path / "subdir"
        test_dir.mkdir()

        # Use relative path
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = validate_path("subdir", must_exist=True)
            assert result.is_absolute()
        finally:
            os.chdir(old_cwd)


class TestValidateDirectory:
    """Tests for validate_directory function."""

    def test_validate_existing_directory(self, tmp_path):
        """Test validation of existing directory."""
        result = validate_directory(str(tmp_path))
        assert isinstance(result, Path)
        assert result.is_dir()

    def test_validate_file_as_directory_fails(self, tmp_path):
        """Test that file path fails directory validation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        with pytest.raises(ValueError, match="Path is not a directory"):
            validate_directory(str(test_file))

    def test_validate_nonexistent_directory_fails(self):
        """Test that nonexistent directory fails validation."""
        with pytest.raises(ValueError):
            validate_directory("/nonexistent/directory")


class TestValidateFile:
    """Tests for validate_file function."""

    def test_validate_existing_file(self, tmp_path):
        """Test validation of existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = validate_file(str(test_file))
        assert isinstance(result, Path)
        assert result.is_file()

    def test_validate_directory_as_file_fails(self, tmp_path):
        """Test that directory path fails file validation."""
        with pytest.raises(ValueError, match="Path is not a file"):
            validate_file(str(tmp_path))

    def test_validate_nonexistent_file_fails(self):
        """Test that nonexistent file fails validation."""
        with pytest.raises(ValueError):
            validate_file("/nonexistent/file.txt")


class TestSanitizePath:
    """Tests for sanitize_path function."""

    def test_sanitize_absolute_windows_path(self):
        """Test sanitization of Windows absolute path."""
        path = r"C:\Users\john\projects\myapp\src\main.py"
        result = sanitize_path(path)
        assert "Users" not in result
        assert "john" not in result
        # Should return basename or sanitized version
        assert len(result) < len(path)

    def test_sanitize_absolute_unix_path(self):
        """Test sanitization of Unix absolute path."""
        path = "/home/john/projects/myapp/src/main.py"
        result = sanitize_path(path)
        assert "home" not in result
        assert "john" not in result
        # Should return basename or sanitized version
        assert len(result) < len(path)

    def test_sanitize_relative_path(self):
        """Test that relative paths are minimally changed."""
        path = "src/main.py"
        result = sanitize_path(path)
        assert result == "main.py" or "src" in result


class TestSanitizeErrorMessage:
    """Tests for sanitize_error_message function."""

    def test_sanitize_windows_path_in_message(self):
        """Test removal of Windows paths from error messages."""
        message = "Error reading file C:\\Users\\john\\project\\config.json"
        result = sanitize_error_message(message)
        assert "C:\\Users\\john" not in result
        assert "[path]" in result or "config.json" in result

    def test_sanitize_unix_path_in_message(self):
        """Test removal of Unix paths from error messages."""
        message = "Error reading file /home/john/project/config.json"
        result = sanitize_error_message(message)
        assert "/home/john" not in result
        assert "[path]" in result or "config.json" in result

    def test_sanitize_username_in_message(self):
        """Test removal of usernames from error messages."""
        message = "Permission denied for user john_doe"
        result = sanitize_error_message(message)
        assert "john_doe" not in result
        assert "[redacted]" in result.lower()

    def test_sanitize_ip_address_in_message(self):
        """Test removal of IP addresses from error messages."""
        message = "Connection failed to 192.168.1.100"
        result = sanitize_error_message(message)
        assert "192.168.1.100" not in result
        assert "[IP]" in result

    def test_sanitize_multiple_sensitive_items(self):
        """Test removal of multiple sensitive items."""
        message = "User alice failed to connect to 10.0.0.5 at /home/alice/app.py"
        result = sanitize_error_message(message)
        assert "alice" not in result
        assert "10.0.0.5" not in result
        assert "/home/alice" not in result


class TestSanitizedError:
    """Tests for SanitizedError exception class."""

    def test_sanitized_error_sanitizes_message(self):
        """Test that SanitizedError sanitizes the message."""
        original_msg = "Error in C:\\Users\\john\\file.py"
        error = SanitizedError(original_msg)

        error_str = str(error)
        assert "C:\\Users\\john" not in error_str
        assert "[path]" in error_str or "file.py" in error_str

    def test_sanitized_error_preserves_original_error(self):
        """Test that original error is preserved if provided."""
        original_error = ValueError("original error")
        sanitized = SanitizedError("Sanitized message", original_error=original_error)

        assert sanitized.original_error is original_error
        assert isinstance(sanitized.original_error, ValueError)

    def test_sanitized_error_without_original(self):
        """Test SanitizedError without original error."""
        sanitized = SanitizedError("Sanitized message")
        assert sanitized.original_error is None

    def test_sanitized_error_can_be_raised(self):
        """Test that SanitizedError can be raised and caught."""
        with pytest.raises(SanitizedError, match="test"):
            raise SanitizedError("This is a test error message")
